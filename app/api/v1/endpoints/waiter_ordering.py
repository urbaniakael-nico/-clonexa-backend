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
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_company_user_for_tenant, require_enabled_module
from app.models.auth import CompanyUser
from app.services import media_storage, whatsapp_delivery
from app.services.access_sessions import ip_allowed_for_scope

from app.api.v1.endpoints.company_users import (
    cx_kitchen_roster_action_044d,
    cx_kitchen_roster_payload_044d,
    require_company_user_admin_access,
)
from app.api.v1.endpoints.hospitality import (
    ACTIVE_STATUSES,
    HospitalityCloseIn,
    HospitalityOrderCreateIn,
    HospitalityOrderItemIn,
    HospitalityStatusIn,
    STATUS_CLOSED,
    STATUS_PENDING,
    STATUS_PREPARING,
    STATUS_SERVED,
    _adjust_pending_order_inventory,
    _build_order_items,
    _clean,
    _closing_payment_method,
    _fetch_order,
    _hsp_report_zone,
    _money,
    _now,
    _num,
    _payload,
    _status,
    _table_key,
    close_hospitality_order,
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
                "has_image": bool(product.get("has_image")),
            }
        )

    for group in portion_groups.values():
        group["portions"].sort(key=lambda item: item["position"])
        # The group card has no inventory id of its own: show the photo of
        # the first portion that has one (uploaded per product in Admin V2).
        with_image = next((portion for portion in group["portions"] if portion.get("has_image")), None)
        group["has_image"] = bool(with_image)
        if with_image:
            group["image_item_id"] = with_image["inventory_item_id"]

    return list(portion_groups.values()) + singles


# ---------------------------------------------------------------------------
# Cantidad por botones (1/4, 1/2, 3/4, 1, 2 -- configurable per company in
# the waiter_ordering module settings, off by default). Price rule, always
# resolved on the server:
#   1. The product belongs to an Admin V2 portion group that has a member
#      whose label is that exact fraction -> that member's own inventory item
#      and own configured price.
#   2. Otherwise -> the fraction of the base product's price ("1"/"entero"
#      member for a group, the product itself when ungrouped), rounded to
#      the currency unit. Stock is deducted as that fraction of the product.
# ---------------------------------------------------------------------------

QUANTITY_BUTTONS_FLAG = "quantity_buttons_enabled"
QUANTITY_BUTTONS_KEY = "quantity_buttons"
DEFAULT_QUANTITY_BUTTONS = ["1/4", "1/2", "3/4", "1", "2"]
MAX_FRACTION = Decimal("50")

_FRACTION_WORDS = {
    "entero": "1", "entera": "1", "completo": "1", "completa": "1", "unidad": "1",
    "medio": "1/2", "media": "1/2", "mitad": "1/2",
    "cuarto": "1/4",
}


def _parse_fraction(label: Any) -> Decimal | None:
    """"1/4" -> 0.25, "2" -> 2, "1.5" -> 1.5. None for anything else."""
    raw = _clean(str(label or "")).lower().replace(",", ".").replace(" ", "")
    if not raw:
        return None
    try:
        if "/" in raw:
            num, den = raw.split("/", 1)
            value = Decimal(num) / Decimal(den)
        else:
            value = Decimal(raw)
    except (InvalidOperation, ZeroDivisionError, ValueError):
        return None
    if not value.is_finite() or value <= 0 or value > MAX_FRACTION:
        return None
    return value


def _portion_label_fraction(label: Any) -> Decimal | None:
    """Fraction a portion-group member's label stands for: "1/4", "1/4 pollo",
    "Medio", "Entero"... None when the label is not a fraction (e.g.
    "Familiar"), so it is never mistaken for one."""
    words = _clean(str(label or "")).lower().split()
    if not words:
        return None
    first = unicodedata.normalize("NFKD", words[0]).encode("ascii", "ignore").decode("ascii")
    return _parse_fraction(_FRACTION_WORDS.get(first, first))


def _round_currency(value: Decimal) -> float:
    return float(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _quantity_buttons_config(module_settings: dict[str, Any]) -> list[str]:
    """Configured buttons when the company turned the feature on, else []."""
    if module_settings.get(QUANTITY_BUTTONS_FLAG) is not True:
        return []
    raw = module_settings.get(QUANTITY_BUTTONS_KEY)
    labels = raw if isinstance(raw, list) and raw else DEFAULT_QUANTITY_BUTTONS
    clean: list[str] = []
    for label in labels:
        text_label = _clean(str(label))[:10]
        if _parse_fraction(text_label) is not None and text_label not in clean:
            clean.append(text_label)
    return clean[:8]


def _group_members(
    group_key: str,
    by_id: dict[str, dict[str, Any]],
    portion_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    members = [
        {**by_id[item_id], "_portion_label": membership["portion_label"], "_position": membership["position"]}
        for item_id, membership in portion_map.items()
        if membership["group_key"] == group_key and item_id in by_id
    ]
    members.sort(key=lambda member: member["_position"])
    return members


def _resolve_fraction(
    product: dict[str, Any],
    fraction_label: str,
    by_id: dict[str, dict[str, Any]],
    portion_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Which inventory item, quantity and price one button press means.
    None when the fraction can't be priced for this product (a portion group
    with neither that exact portion nor a whole "1" member to divide)."""
    fraction = _parse_fraction(fraction_label)
    if fraction is None:
        return None

    base = product
    membership = portion_map.get(str(product.get("id")))
    if membership:
        members = _group_members(membership["group_key"], by_id, portion_map)
        exact = next((m for m in members if _portion_label_fraction(m["_portion_label"]) == fraction), None)
        if exact:
            price = _money(exact.get("price"))
            return {
                "product": exact,
                "quantity": 1.0,
                "unit_price": price,
                "line_total": price,
                "quantity_label": "",
                "from_portion": True,
            }
        base = next((m for m in members if _portion_label_fraction(m["_portion_label"]) == Decimal("1")), None)
        if base is None:
            return None

    unit_price = _money(base.get("price"))
    line_total = _round_currency(Decimal(str(unit_price)) * fraction)
    return {
        "product": base,
        "quantity": float(fraction),
        "unit_price": unit_price,
        "line_total": line_total,
        "quantity_label": _clean(fraction_label)[:10],
        "from_portion": False,
    }


def _allows_portions(
    product: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    portion_map: dict[str, dict[str, Any]],
) -> bool:
    """Inventory "Permite porciones" (off by default). For an Admin V2
    portion group it is enough that one of its portions allows it."""
    if product.get("allows_portions"):
        return True
    membership = portion_map.get(str(product.get("id")))
    if not membership:
        return False
    return any(
        bool(by_id[item_id].get("allows_portions"))
        for item_id, other in portion_map.items()
        if other["group_key"] == membership["group_key"] and item_id in by_id
    )


def _quantity_options(
    product: dict[str, Any],
    buttons: list[str],
    by_id: dict[str, dict[str, Any]],
    portion_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Menu preview so the mesero sees the exact price before adding. Uses
    the very same _resolve_fraction the order endpoint charges with."""
    options = []
    for label in buttons:
        resolved = _resolve_fraction(product, label, by_id, portion_map)
        options.append(
            {
                "label": label,
                "available": resolved is not None,
                "price": resolved["line_total"] if resolved else None,
            }
        )
    return options


@router.get("/{company_id}/waiter-ordering/menu")
async def waiter_ordering_menu(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: CompanyUser = Depends(_require_menu_reader),
) -> dict[str, Any]:
    return await build_waiter_menu(db, company_id)


async def build_waiter_menu(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    """The carta (categories with photo/emoji, products with photo, price
    and portions; only active products, i.e. with stock above the minimum).
    Shared by the mesero/caja panels and the domicilios public carta."""
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

    module_settings = await _module_settings(db, company_id)
    quantity_buttons = _quantity_buttons_config(module_settings)
    if quantity_buttons:
        by_id = {str(item.get("id")): item for item in active_products}
        for product in merged_products:
            # A portion-group card has no inventory id of its own: any member
            # resolves to the same group server-side, so send the first one.
            ref_id = product["portions"][0]["inventory_item_id"] if product.get("is_portioned") else str(product.get("id"))
            product["allows_portions"] = _allows_portions(by_id[ref_id], by_id, portion_map)
            # Fraction buttons only where the product allows portions (pollo);
            # carne, gaseosa... are sold in whole units (the panel shows a
            # simple 1, 2, 3 selector for them).
            if product["allows_portions"]:
                product["quantity_ref_id"] = ref_id
                product["quantity_options"] = _quantity_options(by_id[ref_id], quantity_buttons, by_id, portion_map)

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

    return {
        "ok": True,
        "company_id": str(company_id),
        "categories": list(grouped.values()),
        "quantity_buttons": quantity_buttons,
        # Emoji per category/product in the mesero panel (off by default).
        "menu_emojis": module_settings.get("menu_emojis") is True,
    }


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
    # Cantidad por botones: "1/4", "1/2", ... When set, the server picks the
    # inventory item and price (see _resolve_fraction); `quantity` then
    # counts how many of that fraction (the mesero app always sends 1).
    fraction: str | None = Field(default=None, max_length=10)

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


async def _priced_order_items(db: AsyncSession, company_id: uuid.UUID, items: list[Any]) -> list[HospitalityOrderItemIn]:
    """Server-side name, price, station and cooking term for each line, from
    the company's own catalog -- the client never sends money. Shared by
    order creation and correction so both charge exactly the same way
    (including cantidad por botones fractions)."""
    inventory = await hospitality_inventory_lite(company_id, limit=500, db=db)
    by_id = {str(row.get("id")): row for row in (inventory.get("inventory") or [])}
    categories = await _category_rows(db, company_id)
    portion_map = await _portion_membership(db, company_id)
    quantity_buttons: list[str] | None = None

    order_items: list[HospitalityOrderItemIn] = []
    for item in items:
        product = by_id.get(_clean(item.inventory_item_id))
        if not product:
            raise HTTPException(status_code=422, detail="Producto no disponible en el catalogo.")
        fraction_label = _clean(getattr(item, "fraction", None))
        resolved = None
        allows_portions = _allows_portions(product, by_id, portion_map)
        if not fraction_label and not allows_portions and Decimal(str(item.quantity)) % 1 != 0:
            raise HTTPException(status_code=422, detail=f"{product.get('name') or 'Este producto'} se vende por unidades enteras.")
        if fraction_label:
            if not allows_portions:
                raise HTTPException(status_code=422, detail=f"{product.get('name') or 'Este producto'} no se vende por porciones.")
            if quantity_buttons is None:
                quantity_buttons = _quantity_buttons_config(await _module_settings(db, company_id))
            allowed = {_parse_fraction(label) for label in quantity_buttons}
            if _parse_fraction(fraction_label) not in allowed:
                raise HTTPException(status_code=422, detail="Esa cantidad no esta habilitada para esta empresa.")
            resolved = _resolve_fraction(product, fraction_label, by_id, portion_map)
            if resolved is None:
                raise HTTPException(status_code=422, detail=f"No hay precio configurado para {fraction_label} de este producto.")
            product = resolved["product"]
        # A portion's own inventory name (e.g. "Pollo 1/4") may not start
        # with the same word as its group's display label -- resolve the
        # category from the group label when this item belongs to one, so
        # it lands in the same category/station the menu already showed it
        # under.
        membership = portion_map.get(str(product["id"]))
        category_source = membership["group_label"] if membership else product.get("name")
        category = categories.get(_category_key(category_source))
        term = _clean(item.term) if (category or {}).get("requires_term") else ""
        if resolved:
            count = Decimal(str(item.quantity))
            price_fields = {
                "quantity": float(Decimal(str(resolved["quantity"])) * count),
                "unit_price": resolved["unit_price"],
                "line_total": _money(Decimal(str(resolved["line_total"])) * count),
                "quantity_label": resolved["quantity_label"] if count == 1 else "",
            }
        else:
            price_fields = {"quantity": item.quantity, "unit_price": _money(product.get("price"))}
        order_items.append(
            HospitalityOrderItemIn(
                inventory_item_id=str(product["id"]),
                name=str(product.get("name") or ""),
                observations=item.observations,
                quick_notes=item.quick_notes,
                station=(category or {}).get("station", ""),
                term=term,
                **price_fields,
            )
        )
    return order_items


@router.post("/{company_id}/waiter-ordering/orders", status_code=status.HTTP_201_CREATED)
async def create_waiter_order(
    company_id: uuid.UUID,
    payload: WaiterOrderCreateIn,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_mesero),
) -> dict[str, Any]:
    await ensure_waiter_ordering_storage(db)
    order_items = await _priced_order_items(db, company_id, payload.items)

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
# Caja: facturacion directa (opt-in per company, off by default). The cashier
# sells from the whole active catalog, either as an independent sale
# ("Venta 012", no table) or added to a table, and chooses per sale whether
# it goes to the kitchen:
#   - send_to_kitchen=False: the order is walked pendiente -> alistando ->
#     entregado right away (never shows on the kitchen board); an
#     independent sale is also charged on the spot with the chosen method.
#   - send_to_kitchen=True: it lands in "Pedido nuevo" like a mesero's order
#     and is charged once the kitchen marks it ready (status entregado),
#     from the same caja table list as any other table.
# Prices, names and stations always come from the server's catalog.
# ---------------------------------------------------------------------------

CASHIER_DIRECT_SALE_FLAG = "cashier_direct_sale"


class CashierSaleIn(BaseModel):
    table: str | None = Field(default="", max_length=120)
    items: list[WaiterOrderItemIn] = Field(default_factory=list)
    send_to_kitchen: bool = False
    payment_method: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default="", max_length=900)

    @field_validator("items")
    @classmethod
    def clean_items(cls, value: list[WaiterOrderItemIn] | None) -> list[WaiterOrderItemIn]:
        rows = [item for item in (value or []) if _clean(item.inventory_item_id) and item.quantity > 0]
        if not rows:
            raise ValueError("Agrega al menos un producto.")
        return rows[:80]


@router.get("/{company_id}/waiter-ordering/caja/config")
async def cashier_config(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: CompanyUser = Depends(_require_caja),
) -> dict[str, Any]:
    settings = await _module_settings(db, company_id)
    return {
        "ok": True,
        "direct_sale": settings.get(CASHIER_DIRECT_SALE_FLAG) is True,
        # Domicilios por WhatsApp: the caja shows its own section for them.
        "delivery": await whatsapp_delivery.module_settings(db, company_id) is not None,
    }


def _independent_sale_label(order_number: Any) -> str:
    tail = str(order_number or "").rsplit("-", 1)[-1].strip()
    return f"Venta {tail}" if tail else "Venta caja"


@router.post("/{company_id}/waiter-ordering/caja/ventas", status_code=status.HTTP_201_CREATED)
async def create_cashier_sale(
    company_id: uuid.UUID,
    payload: CashierSaleIn,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_caja),
) -> dict[str, Any]:
    await _require_feature(db, company_id, CASHIER_DIRECT_SALE_FLAG)
    table = _clean(payload.table)
    independent = not table
    charge_now = independent and not payload.send_to_kitchen
    # Validate the payment method BEFORE creating anything, so a bad method
    # never leaves a half-made sale behind.
    payment_method = _closing_payment_method(payload.payment_method) if charge_now else None

    order_items = await _priced_order_items(db, company_id, payload.items)
    created = await create_hospitality_order(
        company_id,
        HospitalityOrderCreateIn(
            # Unique placeholder so two sales in flight never merge into one
            # "table"; renamed to "Venta <n>" right below.
            table=table or f"Venta caja {uuid.uuid4().hex[:8]}",
            customer=user.full_name or "Caja",
            source="table_manual",
            payment_method="other",
            notes=payload.notes,
            items=order_items,
            waiter_id=str(user.id),
            waiter_name=user.full_name or "",
        ),
        db,
    )
    order = created.get("order") or {}
    order_id = uuid.UUID(str(order["id"]))

    sale_meta = {
        "by": {"id": str(user.id), "name": user.full_name or ""},
        "kind": "independiente" if independent else "mesa",
        "send_to_kitchen": bool(payload.send_to_kitchen),
        "at": _now().isoformat(),
    }
    label = _independent_sale_label(order.get("order_number")) if independent else order.get("table_number")
    await db.execute(
        text(
            """
            UPDATE hospitality_orders
            SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('cashier_sale', CAST(:sale AS jsonb)),
                table_number = :label,
                table_key = :table_key,
                updated_at = NOW()
            WHERE id = :order_id AND company_id = :company_id
            """
        ),
        {
            "sale": json.dumps(sale_meta, ensure_ascii=False),
            "label": label,
            "table_key": _table_key(label),
            "order_id": str(order_id),
            "company_id": str(company_id),
        },
    )
    await db.commit()

    if not payload.send_to_kitchen:
        await update_hospitality_order_status(company_id, order_id, HospitalityStatusIn(status=STATUS_PREPARING), db)
        await update_hospitality_order_status(company_id, order_id, HospitalityStatusIn(status=STATUS_SERVED), db)
    if charge_now:
        await close_hospitality_order(company_id, order_id, HospitalityCloseIn(payment_method=payment_method), db)

    saved = await _fetch_order(db, company_id, order_id)
    return {"ok": True, "order": saved, "charged": charge_now, "label": label}


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


# Tablero de cocina en 3 columnas + "Entregado" (opt-in per company via the
# module setting below, off by default). How "entregado" is kept apart from
# the cashier: Hospitality's own order status "entregado" is what the caja
# charges (close-table only accepts status == entregado), so "Comanda lista"
# moves the order to that status exactly like before. The kitchen's own
# "Entregado" button never touches the status: it only stamps
# metadata.kitchen.delivered_at, which takes the comanda off the board and
# into the day's history while the caja still sees and charges the table.
KITCHEN_COLUMNS_FLAG = "kitchen_board_columns"


async def _feature_enabled(db: AsyncSession, company_id: uuid.UUID, flag: str) -> bool:
    return (await _module_settings(db, company_id)).get(flag) is True


async def _require_feature(db: AsyncSession, company_id: uuid.UUID, flag: str) -> dict[str, Any]:
    settings = await _module_settings(db, company_id)
    if settings.get(flag) is not True:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="funcion_no_habilitada")
    return settings


def _kitchen_meta(order: dict[str, Any]) -> dict[str, Any]:
    meta = (order.get("metadata") or {}).get("kitchen")
    return meta if isinstance(meta, dict) else {}


def _station_set(user: CompanyUser) -> tuple[list[str], set[str]]:
    settings = _cocina_user_settings(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    stations = mini_panel.get("stations") if isinstance(mini_panel.get("stations"), list) else []
    return stations, {_clean(item).lower() for item in stations if _clean(item)}


def _comanda(order: dict[str, Any], station_set: set[str]) -> dict[str, Any] | None:
    items = [
        item for item in (order.get("items") or [])
        # The delivery fee line of a domicilio is charged, never cooked.
        if _clean(item.get("station")).lower() != "domicilio"
        and (not station_set or _clean(item.get("station")).lower() in station_set)
    ]
    if not items:
        return None
    kitchen = _kitchen_meta(order)
    delivery = (order.get("metadata") or {}).get("delivery") or {}
    return {
        "order_id": order.get("id"),
        "table_number": order.get("table_number"),
        "status": order.get("status"),
        "waiter": (order.get("metadata") or {}).get("waiter") or {},
        # Domicilio: the kitchen sees it is not a table and where it goes.
        "delivery": {"customer_name": delivery.get("customer_name") or "", "address": delivery.get("address") or ""} if delivery else None,
        "notes": order.get("notes"),
        "created_at": order.get("created_at"),
        "preparing_at": order.get("preparing_at"),
        "ready_at": kitchen.get("ready_at"),
        "delivered_at": kitchen.get("delivered_at"),
        "items": items,
    }


def _local_day_start(module_settings: dict[str, Any]) -> datetime:
    """Start of today in the company's timezone (America/Bogota by default),
    as an aware UTC datetime -- so "hoy" doesn't roll over at 7pm local."""
    zone = _hsp_report_zone(module_settings.get("timezone") or "America/Bogota")
    local_now = datetime.now(timezone.utc).astimezone(zone)
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


async def _patch_kitchen_meta(
    db: AsyncSession,
    company_id: uuid.UUID,
    order_id: uuid.UUID | str,
    patch: dict[str, Any],
    extra_where: str = "",
    extra_params: dict[str, Any] | None = None,
) -> int:
    """Merge `patch` into metadata.kitchen only -- never rewrites the rest of
    metadata (waiter, corrections, voided_by...) that other flows own."""
    result = await db.execute(
        text(
            f"""
            UPDATE hospitality_orders
            SET metadata = jsonb_set(
                    COALESCE(metadata, '{{}}'::jsonb),
                    '{{kitchen}}',
                    COALESCE(metadata->'kitchen', '{{}}'::jsonb) || CAST(:patch AS jsonb)
                ),
                updated_at = NOW()
            WHERE id = :order_id AND company_id = :company_id {extra_where}
            """
        ),
        {
            "patch": json.dumps(patch, ensure_ascii=False),
            "order_id": str(order_id),
            "company_id": str(company_id),
            **(extra_params or {}),
        },
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def _ready_unclaimed_orders(db: AsyncSession, company_id: uuid.UUID, since: datetime) -> list[dict[str, Any]]:
    """Column 3 "Listo": marked ready by the kitchen, not yet delivered. Also
    keeps a comanda the caja already charged (cerrado) until the kitchen
    presses Entregado -- charging must never make it vanish unseen."""
    result = await db.execute(
        text(
            """
            SELECT *
            FROM hospitality_orders
            WHERE company_id = :company_id
              AND status IN ('entregado', 'cerrado')
              AND metadata->'kitchen'->>'ready_at' IS NOT NULL
              AND metadata->'kitchen'->>'delivered_at' IS NULL
              AND created_at >= :since
            ORDER BY created_at ASC
            LIMIT 200
            """
        ),
        {"company_id": str(company_id), "since": since},
    )
    return [_payload(row) for row in result.mappings().all()]


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
    columns_enabled = module_settings.get(KITCHEN_COLUMNS_FLAG) is True

    stations, station_set = _station_set(user)

    data = await list_hospitality_orders(company_id, status_filter="active", include_archived=False, limit=500, db=db)
    comandas = []
    for order in data.get("orders") or []:
        if order.get("status") not in {STATUS_PENDING, STATUS_PREPARING}:
            continue
        comanda = _comanda(order, station_set)
        if comanda:
            comandas.append(comanda)

    # list_hospitality_orders (shared with the rest of Hospitality, where
    # newest-first is the right default) sorts created_at DESC -- the kitchen
    # board needs the opposite: oldest ticket first, so nothing waits behind
    # a newer one.
    comandas.sort(key=lambda comanda: str(comanda.get("created_at") or ""))

    response: dict[str, Any] = {
        "ok": True,
        "company_id": str(company_id),
        "stations": stations,
        "comandas": comandas,
        "timer_thresholds": timer_thresholds,
        "columns_enabled": columns_enabled,
        "roster_enabled": module_settings.get(KITCHEN_ROSTER_FLAG) is True,
    }
    if columns_enabled:
        ready_rows = await _ready_unclaimed_orders(db, company_id, datetime.now(timezone.utc) - timedelta(hours=24))
        listos = [c for c in (_comanda(order, station_set) for order in ready_rows) if c]
        listos.sort(key=lambda comanda: str(comanda.get("ready_at") or comanda.get("created_at") or ""))
        response["columns"] = {
            "nuevo": [c for c in comandas if c["status"] == STATUS_PENDING],
            "preparando": [c for c in comandas if c["status"] == STATUS_PREPARING],
            "listo": listos,
        }
        response["counts"] = {key: len(rows) for key, rows in response["columns"].items()}
    return response


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


@router.patch("/{company_id}/waiter-ordering/orders/{order_id}/start")
async def start_waiter_order(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: CompanyUser = Depends(_require_cocina),
) -> dict[str, Any]:
    """Column 1 -> 2: "Empezar" (pendiente -> alistando). Idempotent."""
    await _require_feature(db, company_id, KITCHEN_COLUMNS_FLAG)
    order = await _fetch_order(db, company_id, order_id)
    current = _status(order.get("status"))
    if current == STATUS_PREPARING:
        return {"ok": True, "order": order, "already": True}
    if current != STATUS_PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta comanda ya no esta en Pedido nuevo.")
    return await update_hospitality_order_status(company_id, order_id, HospitalityStatusIn(status=STATUS_PREPARING), db)


def _table_ready_message(table_number: Any) -> str:
    table = _clean(str(table_number or "")) or "?"
    prefix = "" if table.lower().startswith("mesa") else "Mesa "
    return f"{prefix}{table} lista para llevar"


@router.patch("/{company_id}/waiter-ordering/orders/{order_id}/ready")
async def mark_waiter_order_ready(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_cocina),
) -> dict[str, Any]:
    """"Comanda lista": -> entregado (the status the caja charges), plus a
    "Mesa X lista para llevar" notice for the mesero who took the order.

    Hospitality only allows pendiente -> alistando -> entregado, so a comanda
    still in pendiente walks through alistando first (it used to jump
    straight to entregado and fail with "Transicion no permitida")."""
    order = await _fetch_order(db, company_id, order_id)
    current = _status(order.get("status"))
    if current == STATUS_PENDING:
        await update_hospitality_order_status(company_id, order_id, HospitalityStatusIn(status=STATUS_PREPARING), db)
        current = STATUS_PREPARING
    if current == STATUS_PREPARING:
        result = await update_hospitality_order_status(company_id, order_id, HospitalityStatusIn(status=STATUS_SERVED), db)
    elif current == STATUS_SERVED:
        result = {"ok": True, "order": order, "table": order}
    else:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta comanda ya no esta activa en cocina.")

    if not _kitchen_meta(order).get("ready_at"):
        waiter = (order.get("metadata") or {}).get("waiter") or {}
        await _patch_kitchen_meta(
            db,
            company_id,
            order_id,
            {
                "ready_at": _now().isoformat(),
                "ready_by": {"id": str(user.id), "name": user.full_name or ""},
                "notice": {
                    "waiter_id": str(waiter.get("id") or ""),
                    "message": _table_ready_message(order.get("table_number")),
                },
            },
        )
        await db.commit()
        result = {**result, "order": await _fetch_order(db, company_id, order_id)}
    return result


@router.patch("/{company_id}/waiter-ordering/orders/{order_id}/delivered")
async def mark_waiter_order_delivered(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_cocina),
) -> dict[str, Any]:
    """Column 3 -> history. Status is NOT changed: the table stays open
    (entregado) for the caja to charge exactly as today."""
    await _require_feature(db, company_id, KITCHEN_COLUMNS_FLAG)
    order = await _lock_order_for_edit(db, company_id, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pedido_no_encontrado")
    kitchen = _kitchen_meta(order)
    if kitchen.get("delivered_at"):
        await db.commit()
        return {"ok": True, "order": order, "already": True}
    if not kitchen.get("ready_at") or _status(order.get("status")) not in {STATUS_SERVED, STATUS_CLOSED}:
        await db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Marca primero la comanda como lista.")
    await _patch_kitchen_meta(
        db,
        company_id,
        order_id,
        {"delivered_at": _now().isoformat(), "delivered_by": {"id": str(user.id), "name": user.full_name or ""}},
    )
    await db.commit()
    return {"ok": True, "order": await _fetch_order(db, company_id, order_id)}


# Registro entrada (switch kitchen_roster, off by default): the kitchen
# tablet lists everyone assigned to cocina with Iniciar / Pausar / Salir
# turno; each person's shift feeds Workforce attendance (CRM) and payroll
# on its own. See company_users.cx_kitchen_roster_* for the storage.
KITCHEN_ROSTER_FLAG = "kitchen_roster"


@router.get("/{company_id}/waiter-ordering/kitchen-team")
async def kitchen_team(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: CompanyUser = Depends(_require_cocina),
) -> dict[str, Any]:
    await _require_feature(db, company_id, KITCHEN_ROSTER_FLAG)
    return {"ok": True, **(await cx_kitchen_roster_payload_044d(db, company_id))}


@router.post("/{company_id}/waiter-ordering/kitchen-team/{employee_id}/{action}")
async def kitchen_team_action(
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    action: str,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_cocina),
) -> dict[str, Any]:
    await _require_feature(db, company_id, KITCHEN_ROSTER_FLAG)
    member = await cx_kitchen_roster_action_044d(db, company_id, str(employee_id), action, user)
    return {"ok": True, "member": member}


@router.get("/{company_id}/waiter-ordering/kitchen/entregadas")
async def waiter_ordering_kitchen_delivered_today(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_cocina),
) -> dict[str, Any]:
    """Historial del dia: comandas the kitchen delivered since local midnight."""
    module_settings = await _require_feature(db, company_id, KITCHEN_COLUMNS_FLAG)
    since = _local_day_start(module_settings)
    _stations, station_set = _station_set(user)
    result = await db.execute(
        text(
            """
            SELECT *
            FROM hospitality_orders
            WHERE company_id = :company_id
              AND metadata->'kitchen'->>'delivered_at' IS NOT NULL
              AND CAST(metadata->'kitchen'->>'delivered_at' AS timestamptz) >= :since
            ORDER BY CAST(metadata->'kitchen'->>'delivered_at' AS timestamptz) DESC
            LIMIT 300
            """
        ),
        {"company_id": str(company_id), "since": since},
    )
    comandas = [c for c in (_comanda(_payload(row), station_set) for row in result.mappings().all()) if c]
    return {"ok": True, "company_id": str(company_id), "since": since.isoformat(), "comandas": comandas}


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
    # Ignored: the station is resolved from the admin-configured category,
    # exactly like on creation. Kept so existing callers don't get a 422.
    station: str | None = Field(default="", max_length=80)
    fraction: str | None = Field(default=None, max_length=10)


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

    # Used to build lines with only inventory_item_id/quantity, so every
    # corrected line came back with unit_price 0 and subtotal $0 -- a
    # corrected table would have been charged nothing for those products.
    # Price them from the catalog exactly like a new order.
    hospitality_items = await _priced_order_items(
        db, company_id, [item for item in payload.items if item.quantity > 0],
    )
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
                "status": _my_table_status(bucket["orders"]),
            }
        )
    return {"ok": True, "tables": result}


def _my_table_status(orders: list[dict[str, Any]]) -> str:
    """Mesero's view of one of his tables:
    - enviado_a_cocina: some comanda still pendiente/alistando;
    - entregada: the kitchen marked every comanda "Entregado" (food is at the
      table) -- nothing left for the mesero, it only waits for the caja;
    - listo_para_llevar: out of the kitchen, still to be carried."""
    if any(order.get("status") in {"pendiente", "alistando"} for order in orders):
        return "enviado_a_cocina"
    if orders and all(_kitchen_meta(order).get("delivered_at") for order in orders):
        return "entregada"
    return "listo_para_llevar"


@router.get("/{company_id}/waiter-ordering/mesero/avisos")
async def waiter_ready_notices(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_mesero),
) -> dict[str, Any]:
    """"Mesa X lista para llevar" notices for THIS mesero only (the one whose
    id the order was stamped with at creation), not yet dismissed."""
    if not await _feature_enabled(db, company_id, KITCHEN_COLUMNS_FLAG):
        return {"ok": True, "enabled": False, "avisos": []}
    result = await db.execute(
        text(
            """
            SELECT id, table_number, metadata
            FROM hospitality_orders
            WHERE company_id = :company_id
              AND metadata->'kitchen'->'notice'->>'waiter_id' = :user_id
              AND metadata->'kitchen'->>'ready_at' IS NOT NULL
              AND metadata->'kitchen'->>'waiter_seen_at' IS NULL
              AND status <> 'cancelado'
              AND created_at >= :since
            ORDER BY created_at ASC
            LIMIT 50
            """
        ),
        {
            "company_id": str(company_id),
            "user_id": str(user.id),
            "since": datetime.now(timezone.utc) - timedelta(hours=24),
        },
    )
    avisos = []
    for row in result.mappings().all():
        metadata = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"] or "{}")
        kitchen = metadata.get("kitchen") if isinstance(metadata.get("kitchen"), dict) else {}
        notice = kitchen.get("notice") if isinstance(kitchen.get("notice"), dict) else {}
        avisos.append(
            {
                "order_id": str(row["id"]),
                "table_number": row["table_number"] or "",
                "message": notice.get("message") or _table_ready_message(row["table_number"]),
                "ready_at": kitchen.get("ready_at"),
            }
        )
    return {"ok": True, "enabled": True, "avisos": avisos}


@router.post("/{company_id}/waiter-ordering/mesero/avisos/{order_id}/visto")
async def dismiss_waiter_ready_notice(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_mesero),
) -> dict[str, Any]:
    await _require_feature(db, company_id, KITCHEN_COLUMNS_FLAG)
    updated = await _patch_kitchen_meta(
        db,
        company_id,
        order_id,
        {"waiter_seen_at": _now().isoformat()},
        extra_where="AND metadata->'kitchen'->'notice'->>'waiter_id' = :user_id",
        extra_params={"user_id": str(user.id)},
    )
    await db.commit()
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="aviso_no_encontrado")
    return {"ok": True, "order_id": str(order_id)}


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
