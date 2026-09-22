"""Fase 1: pedidos por mesero -> cocina -> caja.

Everything here sits behind the "waiter_ordering" company module, which only
ASADERO EL SOCIO has enabled (see migrations/versions/021c_waiter_ordering_ttm.py).
Every endpoint re-checks the module, the mesero/cocina/caja role and, when the
company turned it on, the local-network IP allowlist -- in the endpoint
itself, not only on the page load, per CLAUDE.md's per-company switch rule.

Order storage, inventory deduction and table closing are NOT reimplemented
here: this module calls straight into app.api.v1.endpoints.hospitality's
existing functions (create_hospitality_order, update_hospitality_order_status,
list_hospitality_orders, hospitality_inventory_lite, _fetch_order, _payload)
so the mesero/cocina/caja flow behaves exactly like the rest of Hospitality.
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_company_user_for_tenant, require_enabled_module
from app.models.auth import CompanyUser
from app.services.access_sessions import ip_allowed_for_scope

from app.api.v1.endpoints.company_users import require_company_user_admin_access
from app.api.v1.endpoints.hospitality import (
    HospitalityOrderCreateIn,
    HospitalityOrderItemIn,
    HospitalityStatusIn,
    STATUS_SERVED,
    _clean,
    _fetch_order,
    _money,
    _now,
    _payload,
    create_hospitality_order,
    hospitality_inventory_lite,
    list_hospitality_orders,
    update_hospitality_order_status,
)

router = APIRouter()

MODULE_CODE = "waiter_ordering"
MINI_PANEL_SCOPE = "mini_panel"
MAX_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


# ---------------------------------------------------------------------------
# Category / station name rules (server-side twin of hospitality_order.js's
# productCategory()/prettyLabel(), so mesero, cocina and the QR client agree
# on the same category for the same product name).
# ---------------------------------------------------------------------------

def _pretty_label(value: str) -> str:
    clean = re.sub(r"[^\w\sÀ-ſ]", " ", str(value or "Otros"), flags=re.UNICODE)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return "Otros"
    return " ".join(part[:1].upper() + part[1:].lower() for part in clean.split(" "))


def _category_key(name: str) -> str:
    label = _pretty_label(str(name or "").strip().split(" ")[0] if str(name or "").strip() else "Otros")
    ascii_text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    return key or "otros"


# ---------------------------------------------------------------------------
# Storage (lazy CREATE TABLE IF NOT EXISTS, same convention as hospitality.py)
# ---------------------------------------------------------------------------

async def ensure_waiter_ordering_storage(db: AsyncSession) -> None:
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS hospitality_categories (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                category_key VARCHAR(120) NOT NULL,
                label VARCHAR(160) NOT NULL DEFAULT '',
                station VARCHAR(80) NOT NULL DEFAULT '',
                quick_notes JSONB NOT NULL DEFAULT '[]'::jsonb,
                image_bytes BYTEA NULL,
                image_content_type VARCHAR(80) NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (company_id, category_key)
            );
            """
        )
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Auth: module + role + local-network IP, all enforced in the endpoint.
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()[:120]
    if request.client and request.client.host:
        return request.client.host[:120]
    return ""


async def _require_waiter_ordering_user(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None,
    db: AsyncSession,
    allowed_roles: set[str],
) -> CompanyUser:
    await require_enabled_module(db, company_id, MODULE_CODE)
    ip_value = _client_ip(request)
    if not await ip_allowed_for_scope(db, company_id, MINI_PANEL_SCOPE, ip_value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conectate al WiFi del restaurante.")
    return await require_company_user_for_tenant(
        db, authorization, company_id, allowed_roles=allowed_roles, module_codes=MODULE_CODE,
    )


async def _require_mesero(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CompanyUser:
    return await _require_waiter_ordering_user(company_id, request, authorization, db, {"mesero", "caja"})


async def _require_cocina(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CompanyUser:
    return await _require_waiter_ordering_user(company_id, request, authorization, db, {"cocina"})


async def _require_caja(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CompanyUser:
    return await _require_waiter_ordering_user(company_id, request, authorization, db, {"caja"})


async def _require_menu_reader(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CompanyUser:
    return await _require_waiter_ordering_user(company_id, request, authorization, db, {"mesero", "cocina", "caja"})


# ---------------------------------------------------------------------------
# Category catalog (admin-configured image / station / quick notes)
# ---------------------------------------------------------------------------

async def _category_rows(db: AsyncSession, company_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT category_key, label, station, quick_notes,
                   (image_bytes IS NOT NULL) AS has_image
            FROM hospitality_categories
            WHERE company_id = :company_id
            """
        ),
        {"company_id": str(company_id)},
    )
    rows: dict[str, dict[str, Any]] = {}
    for row in result.mappings().all():
        quick_notes = row["quick_notes"]
        if isinstance(quick_notes, str):
            try:
                quick_notes = json.loads(quick_notes)
            except Exception:
                quick_notes = []
        rows[row["category_key"]] = {
            "key": row["category_key"],
            "label": row["label"] or _pretty_label(row["category_key"]),
            "station": row["station"] or "",
            "quick_notes": quick_notes if isinstance(quick_notes, list) else [],
            "has_image": bool(row["has_image"]),
        }
    return rows


class CategoryUpsertIn(BaseModel):
    label: str | None = Field(default="", max_length=160)
    station: str | None = Field(default="", max_length=80)
    quick_notes: list[str] = Field(default_factory=list)

    @field_validator("quick_notes")
    @classmethod
    def clean_quick_notes(cls, value: list[str] | None) -> list[str]:
        return [_clean(item)[:80] for item in (value or []) if _clean(item)][:8]


@router.get("/{company_id}/waiter-ordering/categories")
async def list_waiter_ordering_categories(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_company_user_admin_access),
) -> dict[str, Any]:
    await ensure_waiter_ordering_storage(db)
    configured = await _category_rows(db, company_id)

    menu = await hospitality_inventory_lite(company_id, limit=500, db=db)
    discovered: dict[str, str] = {}
    for item in menu.get("inventory") or []:
        key = _category_key(item.get("name"))
        discovered.setdefault(key, _pretty_label(str(item.get("name") or "").split(" ")[0] if item.get("name") else "Otros"))

    categories = []
    for key, label in discovered.items():
        row = configured.get(key)
        categories.append(row or {"key": key, "label": label, "station": "", "quick_notes": [], "has_image": False})
    for key, row in configured.items():
        if key not in discovered:
            categories.append(row)

    return {"ok": True, "company_id": str(company_id), "categories": categories}


@router.put("/{company_id}/waiter-ordering/categories/{category_key}")
async def upsert_waiter_ordering_category(
    company_id: uuid.UUID,
    category_key: str,
    payload: CategoryUpsertIn,
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_company_user_admin_access),
) -> dict[str, Any]:
    await ensure_waiter_ordering_storage(db)
    key = _category_key(category_key)
    label = _clean(payload.label) or _pretty_label(key)
    await db.execute(
        text(
            """
            INSERT INTO hospitality_categories (company_id, category_key, label, station, quick_notes)
            VALUES (:company_id, :category_key, :label, :station, CAST(:quick_notes AS jsonb))
            ON CONFLICT (company_id, category_key) DO UPDATE
            SET label = EXCLUDED.label,
                station = EXCLUDED.station,
                quick_notes = EXCLUDED.quick_notes,
                updated_at = NOW()
            """
        ),
        {
            "company_id": str(company_id),
            "category_key": key,
            "label": label[:160],
            "station": _clean(payload.station)[:80],
            "quick_notes": json.dumps(payload.quick_notes, ensure_ascii=False),
        },
    )
    await db.commit()
    rows = await _category_rows(db, company_id)
    return {"ok": True, "category": rows.get(key)}


@router.post("/{company_id}/waiter-ordering/categories/{category_key}/image")
async def upload_waiter_ordering_category_image(
    company_id: uuid.UUID,
    category_key: str,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_company_user_admin_access),
) -> dict[str, Any]:
    await ensure_waiter_ordering_storage(db)
    content_type = (image.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="Formato de imagen no soportado (usa PNG, JPG o WEBP).")
    content = await image.read()
    if not content:
        raise HTTPException(status_code=422, detail="imagen_vacia")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="La imagen supera 2MB.")

    key = _category_key(category_key)
    await db.execute(
        text(
            """
            INSERT INTO hospitality_categories (company_id, category_key, label, image_bytes, image_content_type)
            VALUES (:company_id, :category_key, :label, :image_bytes, :content_type)
            ON CONFLICT (company_id, category_key) DO UPDATE
            SET image_bytes = EXCLUDED.image_bytes,
                image_content_type = EXCLUDED.image_content_type,
                updated_at = NOW()
            """
        ),
        {
            "company_id": str(company_id),
            "category_key": key,
            "label": _pretty_label(key),
            "image_bytes": content,
            "content_type": content_type,
        },
    )
    await db.commit()
    return {"ok": True, "category_key": key}


@router.get("/{company_id}/waiter-ordering/categories/{category_key}/image")
async def get_waiter_ordering_category_image(
    company_id: uuid.UUID,
    category_key: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    # No mini-panel/admin auth here on purpose: it is a decorative category
    # photo (not guest or order data), scoped by company_id in the query
    # below, and both the mesero <img> tag and the Admin V2 CSS
    # background-image preview need to load it without attaching a bearer
    # token.
    result = await db.execute(
        text(
            """
            SELECT image_bytes, image_content_type
            FROM hospitality_categories
            WHERE company_id = :company_id AND category_key = :category_key
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "category_key": _category_key(category_key)},
    )
    row = result.mappings().first()
    if not row or not row["image_bytes"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sin_imagen")
    return Response(content=bytes(row["image_bytes"]), media_type=row["image_content_type"] or "image/png")


# ---------------------------------------------------------------------------
# Menu (mesero + caja product picker)
# ---------------------------------------------------------------------------

@router.get("/{company_id}/waiter-ordering/menu")
async def waiter_ordering_menu(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: CompanyUser = Depends(_require_menu_reader),
) -> dict[str, Any]:
    await ensure_waiter_ordering_storage(db)
    inventory = await hospitality_inventory_lite(company_id, limit=500, db=db)
    configured = await _category_rows(db, company_id)

    grouped: dict[str, dict[str, Any]] = {}
    for item in inventory.get("inventory") or []:
        if not item.get("active"):
            continue
        key = _category_key(item.get("name"))
        bucket = grouped.setdefault(
            key,
            {
                **(configured.get(key) or {"key": key, "label": _pretty_label(str(item.get("name") or "").split(" ")[0]), "station": "", "quick_notes": [], "has_image": False}),
                "products": [],
            },
        )
        bucket["products"].append(item)

    return {"ok": True, "company_id": str(company_id), "categories": list(grouped.values())}


# ---------------------------------------------------------------------------
# Order creation (mesero / caja) -- thin wrapper over hospitality's own
# create_hospitality_order, so inventory deduction and order storage are not
# duplicated.
# ---------------------------------------------------------------------------

class WaiterOrderItemIn(BaseModel):
    inventory_item_id: str = Field(..., max_length=120)
    quantity: float = Field(default=1, gt=0)
    observations: str | None = Field(default="", max_length=300)
    quick_notes: list[str] = Field(default_factory=list)

    @field_validator("quick_notes")
    @classmethod
    def clean_quick_notes(cls, value: list[str] | None) -> list[str]:
        return [_clean(item)[:80] for item in (value or []) if _clean(item)][:8]


class WaiterOrderCreateIn(BaseModel):
    table: str = Field(..., min_length=1, max_length=120)
    notes: str | None = Field(default="", max_length=900)
    items: list[WaiterOrderItemIn] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def clean_items(cls, value: list[WaiterOrderItemIn] | None) -> list[WaiterOrderItemIn]:
        rows = [item for item in (value or []) if _clean(item.inventory_item_id) and item.quantity > 0]
        if not rows:
            raise ValueError("Agrega al menos un producto.")
        return rows[:80]


@router.post("/{company_id}/waiter-ordering/orders", status_code=status.HTTP_201_CREATED)
async def create_waiter_order(
    company_id: uuid.UUID,
    payload: WaiterOrderCreateIn,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_mesero),
) -> dict[str, Any]:
    await ensure_waiter_ordering_storage(db)
    inventory = await hospitality_inventory_lite(company_id, limit=500, db=db)
    by_id = {str(row.get("id")): row for row in (inventory.get("inventory") or [])}
    categories = await _category_rows(db, company_id)

    order_items: list[HospitalityOrderItemIn] = []
    for item in payload.items:
        product = by_id.get(_clean(item.inventory_item_id))
        if not product:
            raise HTTPException(status_code=422, detail="Producto no disponible en el catalogo.")
        category = categories.get(_category_key(product.get("name")))
        order_items.append(
            HospitalityOrderItemIn(
                inventory_item_id=str(product["id"]),
                name=str(product.get("name") or ""),
                quantity=item.quantity,
                unit_price=_money(product.get("price")),
                observations=item.observations,
                quick_notes=item.quick_notes,
                station=(category or {}).get("station", ""),
            )
        )

    hospitality_payload = HospitalityOrderCreateIn(
        table=payload.table,
        customer=user.full_name or "Mesero",
        source="table_manual",
        payment_method="other",
        notes=payload.notes,
        items=order_items,
        waiter_id=str(user.id),
        waiter_name=user.full_name or "",
    )
    return await create_hospitality_order(company_id, hospitality_payload, db)


# ---------------------------------------------------------------------------
# Cocina: stations per user + kitchen board + mark item/comanda ready
# ---------------------------------------------------------------------------

class CocinaStationsIn(BaseModel):
    stations: list[str] = Field(default_factory=list)

    @field_validator("stations")
    @classmethod
    def clean_stations(cls, value: list[str] | None) -> list[str]:
        return [_clean(item)[:80] for item in (value or []) if _clean(item)][:20]


def _cocina_user_settings(user: CompanyUser) -> dict[str, Any]:
    raw = getattr(user, "settings_json", None)
    return raw if isinstance(raw, dict) else {}


@router.put("/{company_id}/waiter-ordering/cocina-users/{user_id}/stations")
async def set_cocina_user_stations(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: CocinaStationsIn,
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_company_user_admin_access),
) -> dict[str, Any]:
    result = await db.execute(
        text("SELECT id, company_id, settings_json FROM company_users WHERE id = :user_id AND company_id = :company_id LIMIT 1"),
        {"user_id": str(user_id), "company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario de cocina no encontrado.")

    settings = row["settings_json"] if isinstance(row["settings_json"], dict) else {}
    mini_panel = dict(settings.get("mini_panel") or {})
    mini_panel["stations"] = payload.stations
    settings = {**settings, "mini_panel": mini_panel}
    await db.execute(
        text("UPDATE company_users SET settings_json = CAST(:settings AS jsonb), updated_at = NOW() WHERE id = :user_id"),
        {"settings": json.dumps(settings, ensure_ascii=False), "user_id": str(user_id)},
    )
    await db.commit()
    return {"ok": True, "user_id": str(user_id), "stations": payload.stations}


async def _module_settings(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT cm.settings
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = :company_id AND m.code = :code AND cm.enabled IS TRUE
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "code": MODULE_CODE},
    )
    row = result.mappings().first()
    settings = row["settings"] if row else None
    return settings if isinstance(settings, dict) else {}


DEFAULT_TIMER_THRESHOLDS = {"green_max_minutes": 10, "yellow_max_minutes": 20}


@router.get("/{company_id}/waiter-ordering/kitchen")
async def waiter_ordering_kitchen_board(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_cocina),
) -> dict[str, Any]:
    module_settings = await _module_settings(db, company_id)
    timer_thresholds = module_settings.get("timer_thresholds")
    if not isinstance(timer_thresholds, dict):
        timer_thresholds = DEFAULT_TIMER_THRESHOLDS

    settings = _cocina_user_settings(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    stations = mini_panel.get("stations") if isinstance(mini_panel.get("stations"), list) else []
    station_set = {_clean(item).lower() for item in stations if _clean(item)}

    data = await list_hospitality_orders(company_id, status_filter="active", include_archived=False, limit=500, db=db)
    comandas = []
    for order in data.get("orders") or []:
        if order.get("status") not in {"pendiente", "alistando"}:
            continue
        items = [
            item for item in (order.get("items") or [])
            if not station_set or _clean(item.get("station")).lower() in station_set
        ]
        if not items:
            continue
        comandas.append({
            "order_id": order.get("id"),
            "table_number": order.get("table_number"),
            "status": order.get("status"),
            "waiter": (order.get("metadata") or {}).get("waiter") or {},
            "notes": order.get("notes"),
            "created_at": order.get("created_at"),
            "items": items,
        })

    return {
        "ok": True,
        "company_id": str(company_id),
        "stations": stations,
        "comandas": comandas,
        "timer_thresholds": timer_thresholds,
    }


@router.patch("/{company_id}/waiter-ordering/orders/{order_id}/items/{item_id}/ready")
async def mark_waiter_order_item_ready(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    _user: CompanyUser = Depends(_require_cocina),
) -> dict[str, Any]:
    order = await _fetch_order(db, company_id, order_id)
    items = order.get("items") or []
    found = False
    for item in items:
        if isinstance(item, dict) and item.get("id") == item_id:
            item["ready"] = True
            item["ready_at"] = _now().isoformat()
            found = True
            break
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item_no_encontrado")

    await db.execute(
        text("UPDATE hospitality_orders SET items = CAST(:items AS jsonb), updated_at = NOW() WHERE id = :order_id AND company_id = :company_id"),
        {"items": json.dumps(items, ensure_ascii=False), "order_id": str(order_id), "company_id": str(company_id)},
    )
    await db.commit()
    saved = await _fetch_order(db, company_id, order_id)
    return {"ok": True, "order": saved}


@router.patch("/{company_id}/waiter-ordering/orders/{order_id}/ready")
async def mark_waiter_order_ready(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: CompanyUser = Depends(_require_cocina),
) -> dict[str, Any]:
    return await update_hospitality_order_status(company_id, order_id, HospitalityStatusIn(status=STATUS_SERVED), db)


# ---------------------------------------------------------------------------
# Caja: register the local network's current public IP
# ---------------------------------------------------------------------------

@router.post("/{company_id}/waiter-ordering/network/register")
async def register_local_network(
    company_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: CompanyUser = Depends(_require_caja),
) -> dict[str, Any]:
    ip_value = _client_ip(request)
    if not ip_value:
        raise HTTPException(status_code=422, detail="No se pudo detectar la IP actual. Conectate al WiFi del restaurante.")

    result = await db.execute(
        text("SELECT settings_json FROM companies WHERE id = CAST(:company_id AS uuid)"),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    store = dict(row["settings_json"]) if row and isinstance(row["settings_json"], dict) else {}
    security = dict(store.get("security") or {})
    ip_allowlist = dict(security.get("ip_allowlist") or {})
    scopes = dict(ip_allowlist.get("scopes") or {})
    mini_panel_scope = dict(scopes.get(MINI_PANEL_SCOPE) or {})
    allowed_ips = list(mini_panel_scope.get("allowed_ips") or [])
    if ip_value not in allowed_ips:
        allowed_ips.append(ip_value)
    mini_panel_scope["allowed_ips"] = allowed_ips
    mini_panel_scope["enabled"] = True
    scopes[MINI_PANEL_SCOPE] = mini_panel_scope
    ip_allowlist["scopes"] = scopes
    # Leave ip_allowlist["enabled"] (the company-wide switch) untouched: only
    # Admin V2's "Restringir a la red del local" toggle turns enforcement on.
    security["ip_allowlist"] = ip_allowlist
    store["security"] = security

    await db.execute(
        text("UPDATE companies SET settings_json = CAST(:settings AS jsonb), updated_at = NOW() WHERE id = CAST(:company_id AS uuid)"),
        {"settings": json.dumps(store, ensure_ascii=False), "company_id": str(company_id)},
    )
    await db.commit()
    return {"ok": True, "ip": ip_value, "allowed_ips": allowed_ips}
