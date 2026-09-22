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
from app.services import media_storage
from app.services.access_sessions import ip_allowed_for_scope

from app.api.v1.endpoints.company_users import require_company_user_admin_access
from app.api.v1.endpoints.hospitality import (
    ACTIVE_STATUSES,
    HospitalityOrderCreateIn,
    HospitalityOrderItemIn,
    HospitalityStatusIn,
    STATUS_CLOSED,
    STATUS_SERVED,
    _adjust_pending_order_inventory,
    _build_order_items,
    _clean,
    _fetch_order,
    _money,
    _now,
    _num,
    _payload,
    create_hospitality_order,
    hospitality_inventory_lite,
    list_hospitality_orders,
    update_hospitality_order_status,
)

router = APIRouter()

MODULE_CODE = "waiter_ordering"
MINI_PANEL_SCOPE = "mini_panel"


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
# Storage: as of Fase 2, hospitality_categories (plus its requires_term
# column), hospitality_product_portions and hospitality_product_images are
# owned by migrations/versions/021d_waiter_ordering_p2.py -- alembic runs
# before the app starts (scripts/start.sh), so by request time the schema
# is already there. This function is now a no-op, kept only so the existing
# call sites below don't need to change.
# ---------------------------------------------------------------------------

async def ensure_waiter_ordering_storage(db: AsyncSession) -> None:
    return None


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
            SELECT category_key, label, station, quick_notes, requires_term,
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
            "requires_term": bool(row["requires_term"]),
            "has_image": bool(row["has_image"]),
        }
    return rows


class CategoryUpsertIn(BaseModel):
    label: str | None = Field(default="", max_length=160)
    station: str | None = Field(default="", max_length=80)
    quick_notes: list[str] = Field(default_factory=list)
    requires_term: bool = Field(default=False)

    @field_validator("quick_notes")
    @classmethod
    def clean_quick_notes(cls, value: list[str] | None) -> list[str]:
        return [_clean(item)[:80] for item in (value or []) if _clean(item)][:8]


# ---------------------------------------------------------------------------
# Product portions (Fase 2): each portion is its OWN inventory item, with its
# own stock/price/SKU -- this table only groups sibling inventory_item_ids
# under one visual product card with portion buttons. Nothing here touches
# inventory_items, _build_order_items or _deduct_inventory: picking "1/4"
# just picks that portion's own inventory_item_id, exactly like any product.
# ---------------------------------------------------------------------------

async def _portion_membership(db: AsyncSession, company_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    """inventory_item_id -> {group_key, group_label, portion_label, position}."""
    result = await db.execute(
        text(
            """
            SELECT inventory_item_id, product_group_key, group_label, portion_label, position
            FROM hospitality_product_portions
            WHERE company_id = :company_id
            """
        ),
        {"company_id": str(company_id)},
    )
    return {
        str(row["inventory_item_id"]): {
            "group_key": row["product_group_key"],
            "group_label": row["group_label"],
            "portion_label": row["portion_label"],
            "position": row["position"],
        }
        for row in result.mappings().all()
    }


class PortionMemberIn(BaseModel):
    inventory_item_id: str = Field(..., max_length=120)
    portion_label: str = Field(..., min_length=1, max_length=40)
    position: int = Field(default=0)


class PortionGroupUpsertIn(BaseModel):
    group_label: str = Field(..., min_length=1, max_length=160)
    members: list[PortionMemberIn] = Field(default_factory=list)


@router.get("/{company_id}/waiter-ordering/portions")
async def list_waiter_ordering_portions(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_company_user_admin_access),
) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT product_group_key, group_label, inventory_item_id, portion_label, position
            FROM hospitality_product_portions
            WHERE company_id = :company_id
            ORDER BY product_group_key, position
            """
        ),
        {"company_id": str(company_id)},
    )
    groups: dict[str, dict[str, Any]] = {}
    for row in result.mappings().all():
        group = groups.setdefault(
            row["product_group_key"],
            {"group_key": row["product_group_key"], "group_label": row["group_label"], "members": []},
        )
        group["members"].append(
            {
                "inventory_item_id": str(row["inventory_item_id"]),
                "portion_label": row["portion_label"],
                "position": row["position"],
            }
        )
    return {"ok": True, "company_id": str(company_id), "groups": list(groups.values())}


@router.put("/{company_id}/waiter-ordering/portions/{product_group_key}")
async def upsert_waiter_ordering_portion_group(
    company_id: uuid.UUID,
    product_group_key: str,
    payload: PortionGroupUpsertIn,
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_company_user_admin_access),
) -> dict[str, Any]:
    key = _category_key(product_group_key)
    # Replace the whole group atomically: clear its current members, then
    # insert the new set. An empty members list ungroups everything (the
    # products just go back to being normal single-quantity items).
    await db.execute(
        text("DELETE FROM hospitality_product_portions WHERE company_id = :company_id AND product_group_key = :key"),
        {"company_id": str(company_id), "key": key},
    )
    seen_items: set[str] = set()
    for member in payload.members[:12]:
        item_id = _clean(member.inventory_item_id)
        if not item_id or item_id in seen_items:
            continue
        seen_items.add(item_id)
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO hospitality_product_portions
                        (company_id, product_group_key, group_label, inventory_item_id, portion_label, position)
                    VALUES (:company_id, :key, :group_label, CAST(:item_id AS uuid), :portion_label, :position)
                    """
                ),
                {
                    "company_id": str(company_id),
                    "key": key,
                    "group_label": payload.group_label[:160],
                    "item_id": item_id,
                    "portion_label": member.portion_label[:40],
                    "position": member.position,
                },
            )
        except Exception:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ese producto ya pertenece a otro grupo de porciones.",
            )
    await db.commit()
    return {"ok": True, "group_key": key}


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
            INSERT INTO hospitality_categories (company_id, category_key, label, station, quick_notes, requires_term)
            VALUES (:company_id, :category_key, :label, :station, CAST(:quick_notes AS jsonb), :requires_term)
            ON CONFLICT (company_id, category_key) DO UPDATE
            SET label = EXCLUDED.label,
                station = EXCLUDED.station,
                quick_notes = EXCLUDED.quick_notes,
                requires_term = EXCLUDED.requires_term,
                updated_at = NOW()
            """
        ),
        {
            "company_id": str(company_id),
            "category_key": key,
            "label": label[:160],
            "station": _clean(payload.station)[:80],
            "quick_notes": json.dumps(payload.quick_notes, ensure_ascii=False),
            "requires_term": bool(payload.requires_term),
        },
    )
    await db.commit()
    rows = await _category_rows(db, company_id)
    return {"ok": True, "category": rows.get(key)}


async def _ensure_category_row(db: AsyncSession, company_id: uuid.UUID, key: str) -> None:
    """Upsert the row with no image change, so media_storage.save_image always
    has an existing row to UPDATE."""
    await db.execute(
        text(
            """
            INSERT INTO hospitality_categories (company_id, category_key, label)
            VALUES (:company_id, :category_key, :label)
            ON CONFLICT (company_id, category_key) DO NOTHING
            """
        ),
        {"company_id": str(company_id), "category_key": key, "label": _pretty_label(key)},
    )


@router.post("/{company_id}/waiter-ordering/categories/{category_key}/image")
async def upload_waiter_ordering_category_image(
    company_id: uuid.UUID,
    category_key: str,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_company_user_admin_access),
) -> dict[str, Any]:
    key = _category_key(category_key)
    content = await image.read()
    await _ensure_category_row(db, company_id, key)
    await media_storage.save_image(
        db,
        table="hospitality_categories",
        key_columns={"company_id": str(company_id), "category_key": key},
        raw=content,
        content_type=(image.content_type or "").lower(),
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
    found = await media_storage.get_image(
        db,
        table="hospitality_categories",
        key_columns={"company_id": str(company_id), "category_key": _category_key(category_key)},
    )
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sin_imagen")
    content, content_type = found
    return Response(content=content, media_type=content_type)


async def _ensure_product_image_row(db: AsyncSession, company_id: uuid.UUID, inventory_item_id: str) -> None:
    await db.execute(
        text(
            """
            INSERT INTO hospitality_product_images (company_id, inventory_item_id)
            VALUES (:company_id, CAST(:item_id AS uuid))
            ON CONFLICT (company_id, inventory_item_id) DO NOTHING
            """
        ),
        {"company_id": str(company_id), "item_id": inventory_item_id},
    )


@router.post("/{company_id}/waiter-ordering/products/{inventory_item_id}/image")
async def upload_waiter_ordering_product_image(
    company_id: uuid.UUID,
    inventory_item_id: uuid.UUID,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_company_user_admin_access),
) -> dict[str, Any]:
    content = await image.read()
    await _ensure_product_image_row(db, company_id, str(inventory_item_id))
    await media_storage.save_image(
        db,
        table="hospitality_product_images",
        key_columns={"company_id": str(company_id), "inventory_item_id": str(inventory_item_id)},
        raw=content,
        content_type=(image.content_type or "").lower(),
    )
    await db.commit()
    return {"ok": True, "inventory_item_id": str(inventory_item_id)}


@router.get("/{company_id}/waiter-ordering/products/{inventory_item_id}/image")
async def get_waiter_ordering_product_image(
    company_id: uuid.UUID,
    inventory_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    # Same reasoning as the category image endpoint: no auth, non-sensitive
    # decorative photo, needs to load from a plain <img> tag.
    found = await media_storage.get_image(
        db,
        table="hospitality_product_images",
        key_columns={"company_id": str(company_id), "inventory_item_id": str(inventory_item_id)},
    )
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sin_imagen")
    content, content_type = found
    return Response(content=content, media_type=content_type)


# ---------------------------------------------------------------------------
# Menu (mesero + caja product picker)
# ---------------------------------------------------------------------------

def _merge_portions_into_products(
    products: list[dict[str, Any]],
    portion_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse sibling inventory items that share a portion group into one
    product card with a `portions` list; everything else passes through
    unchanged. Each portion keeps its own inventory_item_id/price/stock, so
    picking one is picking a normal product -- no fraction math anywhere."""
    portion_groups: dict[str, dict[str, Any]] = {}
    singles: list[dict[str, Any]] = []

    for product in products:
        membership = portion_map.get(str(product.get("id")))
        if not membership:
            singles.append(product)
            continue
        group = portion_groups.setdefault(
            membership["group_key"],
            {
                "id": membership["group_key"],
                "name": membership["group_label"],
                "is_portioned": True,
                "portions": [],
            },
        )
        group["portions"].append(
            {
                "inventory_item_id": str(product.get("id")),
                "label": membership["portion_label"],
                "position": membership["position"],
                "price": product.get("price"),
                "stock": product.get("stock"),
            }
        )

    for group in portion_groups.values():
        group["portions"].sort(key=lambda item: item["position"])

    return list(portion_groups.values()) + singles


@router.get("/{company_id}/waiter-ordering/menu")
async def waiter_ordering_menu(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: CompanyUser = Depends(_require_menu_reader),
) -> dict[str, Any]:
    await ensure_waiter_ordering_storage(db)
    inventory = await hospitality_inventory_lite(company_id, limit=500, db=db)
    configured = await _category_rows(db, company_id)
    portion_map = await _portion_membership(db, company_id)

    image_rows = await db.execute(
        text(
            "SELECT inventory_item_id FROM hospitality_product_images "
            "WHERE company_id = :company_id AND image_bytes IS NOT NULL"
        ),
        {"company_id": str(company_id)},
    )
    products_with_image = {str(row["inventory_item_id"]) for row in image_rows.mappings().all()}

    active_products = [item for item in (inventory.get("inventory") or []) if item.get("active")]
    for product in active_products:
        product["has_image"] = str(product.get("id")) in products_with_image
    merged_products = _merge_portions_into_products(active_products, portion_map)

    grouped: dict[str, dict[str, Any]] = {}
    for product in merged_products:
        key = _category_key(product.get("name"))
        bucket = grouped.setdefault(
            key,
            {
                **(configured.get(key) or {"key": key, "label": _pretty_label(str(product.get("name") or "").split(" ")[0]), "station": "", "quick_notes": [], "requires_term": False, "has_image": False}),
                "products": [],
            },
        )
        bucket["products"].append(product)

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
    term: str | None = Field(default="", max_length=40)

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
    portion_map = await _portion_membership(db, company_id)

    order_items: list[HospitalityOrderItemIn] = []
    for item in payload.items:
        product = by_id.get(_clean(item.inventory_item_id))
        if not product:
            raise HTTPException(status_code=422, detail="Producto no disponible en el catalogo.")
        # A portion's own inventory name (e.g. "Pollo 1/4") may not start
        # with the same word as its group's display label -- resolve the
        # category from the group label when this item belongs to one, so
        # it lands in the same category/station the menu already showed it
        # under.
        membership = portion_map.get(str(product["id"]))
        category_source = membership["group_label"] if membership else product.get("name")
        category = categories.get(_category_key(category_source))
        term = _clean(item.term) if (category or {}).get("requires_term") else ""
        order_items.append(
            HospitalityOrderItemIn(
                inventory_item_id=str(product["id"]),
                name=str(product.get("name") or ""),
                quantity=item.quantity,
                unit_price=_money(product.get("price")),
                observations=item.observations,
                quick_notes=item.quick_notes,
                station=(category or {}).get("station", ""),
                term=term,
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


class MeseroDailyGoalIn(BaseModel):
    daily_goal: float = Field(default=0, ge=0)


@router.put("/{company_id}/waiter-ordering/mesero-users/{user_id}/daily-goal")
async def set_mesero_daily_goal(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MeseroDailyGoalIn,
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_company_user_admin_access),
) -> dict[str, Any]:
    result = await db.execute(
        text("SELECT id, company_id, settings_json FROM company_users WHERE id = :user_id AND company_id = :company_id LIMIT 1"),
        {"user_id": str(user_id), "company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario de mesero no encontrado.")

    settings = row["settings_json"] if isinstance(row["settings_json"], dict) else {}
    mini_panel = dict(settings.get("mini_panel") or {})
    mini_panel["daily_goal"] = _money(payload.daily_goal)
    settings = {**settings, "mini_panel": mini_panel}
    await db.execute(
        text("UPDATE company_users SET settings_json = CAST(:settings AS jsonb), updated_at = NOW() WHERE id = :user_id"),
        {"settings": json.dumps(settings, ensure_ascii=False), "user_id": str(user_id)},
    )
    await db.commit()
    return {"ok": True, "user_id": str(user_id), "daily_goal": mini_panel["daily_goal"]}


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

    # list_hospitality_orders (shared with the rest of Hospitality, where
    # newest-first is the right default) sorts created_at DESC -- the kitchen
    # board needs the opposite: oldest ticket first, so nothing waits behind
    # a newer one.
    comandas.sort(key=lambda comanda: str(comanda.get("created_at") or ""))

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
# Void / correct a sent order -- mesero, caja, or portal-complete staff.
# Stock is only ever returned once: the order row is locked (SELECT ... FOR
# UPDATE) before its status is checked, so a second void/correct on the same
# order always sees the state the first one left behind and short-circuits
# without touching inventory again. Blocked once the table is cerrado
# (charged). Every change is recorded in metadata: who, what, when.
# ---------------------------------------------------------------------------

ORDER_EDIT_ROLES = {
    "mesero", "caja", "dueno", "gerente", "administrador",
    "company_admin", "admin_empresa", "manager", "gerencia",
}


async def _require_order_editor(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CompanyUser:
    return await _require_waiter_ordering_user(company_id, request, authorization, db, ORDER_EDIT_ROLES)


class VoidOrderIn(BaseModel):
    reason: str | None = Field(default="", max_length=500)


class CorrectOrderItemIn(BaseModel):
    inventory_item_id: str = Field(..., max_length=120)
    quantity: float = Field(default=1, ge=0)
    observations: str | None = Field(default="", max_length=300)
    quick_notes: list[str] = Field(default_factory=list)
    term: str | None = Field(default="", max_length=40)
    station: str | None = Field(default="", max_length=80)


class CorrectOrderIn(BaseModel):
    items: list[CorrectOrderItemIn] = Field(default_factory=list)
    reason: str | None = Field(default="", max_length=500)


async def _lock_order_for_edit(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID) -> dict[str, Any] | None:
    """SELECT ... FOR UPDATE: the row lock is what makes void/correct safe
    against double stock-return. A second concurrent call waits here until
    the first COMMITs, then sees the already-updated status and stops."""
    result = await db.execute(
        text("SELECT * FROM hospitality_orders WHERE id = :order_id AND company_id = :company_id LIMIT 1 FOR UPDATE"),
        {"order_id": str(order_id), "company_id": str(company_id)},
    )
    row = result.mappings().first()
    return _payload(row) if row else None


def _order_edit_audit(user: CompanyUser, reason: str | None, diff: Any = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "by": {"id": str(user.id), "name": user.full_name or "", "role": user.role or ""},
        "at": _now().isoformat(),
        "reason": _clean(reason)[:500],
    }
    if diff is not None:
        entry["diff"] = diff
    return entry


@router.post("/{company_id}/waiter-ordering/orders/{order_id}/void")
async def void_waiter_order(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: VoidOrderIn,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_order_editor),
) -> dict[str, Any]:
    order = await _lock_order_for_edit(db, company_id, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pedido_no_encontrado")

    current_status = order.get("status")
    if current_status == STATUS_CLOSED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La mesa ya esta cobrada, no se puede anular.")
    if current_status not in ACTIVE_STATUSES:
        # Already cancelled (or otherwise terminal): nothing left to void,
        # and critically nothing left to return to inventory a second time.
        await db.commit()
        return {"ok": True, "already_voided": True, "order": order}

    await _adjust_pending_order_inventory(db, company_id, order, [])

    metadata = dict(order.get("metadata") or {})
    metadata["voided_by"] = _order_edit_audit(user, payload.reason, diff={"removed_items": order.get("items") or []})
    await db.execute(
        text(
            """
            UPDATE hospitality_orders
            SET items = '[]'::jsonb,
                total = 0,
                status = 'cancelado',
                cancelled_at = COALESCE(cancelled_at, NOW()),
                metadata = CAST(:metadata AS jsonb),
                updated_at = NOW()
            WHERE id = :order_id AND company_id = :company_id
            """
        ),
        {
            "order_id": str(order_id),
            "company_id": str(company_id),
            "metadata": json.dumps(metadata, ensure_ascii=False),
        },
    )
    await db.commit()
    saved = await _fetch_order(db, company_id, order_id)
    return {"ok": True, "order": saved}


@router.patch("/{company_id}/waiter-ordering/orders/{order_id}/correct")
async def correct_waiter_order(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: CorrectOrderIn,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_order_editor),
) -> dict[str, Any]:
    order = await _lock_order_for_edit(db, company_id, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pedido_no_encontrado")

    current_status = order.get("status")
    if current_status == STATUS_CLOSED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La mesa ya esta cobrada, no se puede corregir.")
    if current_status not in ACTIVE_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este pedido ya no se puede corregir.")

    hospitality_items = [
        HospitalityOrderItemIn(
            inventory_item_id=item.inventory_item_id,
            quantity=item.quantity,
            observations=item.observations,
            quick_notes=item.quick_notes,
            term=item.term,
            station=item.station,
        )
        for item in payload.items
        if item.quantity > 0
    ]
    new_items = await _build_order_items(db, company_id, hospitality_items)
    await _adjust_pending_order_inventory(db, company_id, order, new_items)

    total = _money(sum(_num(row.get("subtotal")) for row in new_items))
    metadata = dict(order.get("metadata") or {})
    corrections = list(metadata.get("corrections") or [])
    corrections.append(
        _order_edit_audit(user, payload.reason, diff={"before": order.get("items") or [], "after": new_items})
    )
    metadata["corrections"] = corrections[-20:]

    await db.execute(
        text(
            """
            UPDATE hospitality_orders
            SET items = CAST(:items AS jsonb),
                total = :total,
                metadata = CAST(:metadata AS jsonb),
                updated_at = NOW()
            WHERE id = :order_id AND company_id = :company_id
            """
        ),
        {
            "items": json.dumps(new_items, ensure_ascii=False),
            "total": total,
            "metadata": json.dumps(metadata, ensure_ascii=False),
            "order_id": str(order_id),
            "company_id": str(company_id),
        },
    )
    await db.commit()
    saved = await _fetch_order(db, company_id, order_id)
    return {"ok": True, "order": saved}


# ---------------------------------------------------------------------------
# Ventas de hoy + mis mesas (mesero)
# ---------------------------------------------------------------------------

@router.get("/{company_id}/waiter-ordering/mesero/ventas-hoy")
async def waiter_sales_today(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_mesero),
) -> dict[str, Any]:
    settings = _cocina_user_settings(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    daily_goal = _money(mini_panel.get("daily_goal") or 0)

    result = await db.execute(
        text(
            """
            SELECT COALESCE(SUM(total), 0) AS total, COUNT(*) AS orders_count
            FROM hospitality_orders
            WHERE company_id = :company_id
              AND archived_at IS NULL
              AND status <> 'cancelado'
              AND metadata->'waiter'->>'id' = :user_id
              AND created_at >= date_trunc('day', NOW())
              AND created_at < date_trunc('day', NOW()) + INTERVAL '1 day'
            """
        ),
        {"company_id": str(company_id), "user_id": str(user.id)},
    )
    row = result.mappings().first() or {}
    total_today = _money(row.get("total"))
    return {
        "ok": True,
        "waiter_id": str(user.id),
        "total_today": total_today,
        "orders_count": int(row.get("orders_count") or 0),
        "daily_goal": daily_goal,
        "goal_progress_percent": (
            max(0, min(100, round((total_today / daily_goal) * 100))) if daily_goal > 0 else 0
        ),
    }


@router.get("/{company_id}/waiter-ordering/mesero/mis-mesas")
async def waiter_my_tables(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_mesero),
) -> dict[str, Any]:
    data = await list_hospitality_orders(company_id, status_filter="active", include_archived=False, limit=500, db=db)
    mine = [
        order for order in (data.get("orders") or [])
        if str((order.get("metadata") or {}).get("waiter", {}).get("id") or "") == str(user.id)
    ]

    tables: dict[str, dict[str, Any]] = {}
    for order in mine:
        key = order.get("table_key") or order.get("table_number") or ""
        bucket = tables.setdefault(
            key,
            {"table_number": order.get("table_number"), "total": 0.0, "has_pending": False, "orders": []},
        )
        bucket["total"] = _money(bucket["total"] + _num(order.get("total")))
        if order.get("status") in {"pendiente", "alistando"}:
            bucket["has_pending"] = True
        bucket["orders"].append(order)

    result = []
    for bucket in tables.values():
        result.append(
            {
                "table_number": bucket["table_number"],
                "total": bucket["total"],
                "status": "enviado_a_cocina" if bucket["has_pending"] else "listo_para_llevar",
            }
        )
    return {"ok": True, "tables": result}


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
