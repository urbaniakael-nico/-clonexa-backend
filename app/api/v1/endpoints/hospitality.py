from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

STATUS_PENDING = "pendiente"
STATUS_PREPARING = "alistando"
STATUS_SERVED = "entregado"
STATUS_CLOSED = "cerrado"
ACTIVE_STATUSES = {STATUS_PENDING, STATUS_PREPARING, STATUS_SERVED}


class HospitalityOrderItemIn(BaseModel):
    product_id: str | None = Field(default=None, max_length=120)
    inventory_item_id: str | None = Field(default=None, max_length=120)
    sku: str | None = Field(default="", max_length=120)
    name: str | None = Field(default="", max_length=220)
    quantity: float = Field(default=1, ge=0)
    unit: str | None = Field(default="unidad", max_length=80)
    unit_price: float = Field(default=0, ge=0)
    note: str | None = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str:
        return _clean(value)[:220]


class HospitalityOrderCreateIn(BaseModel):
    table: str | None = Field(default="Barra", max_length=120)
    customer: str | None = Field(default="Cliente barra", max_length=180)
    source: str | None = Field(default="client", max_length=60)
    notes: str | None = Field(default="", max_length=900)
    songs: str | list[str] | None = Field(default=None)
    items: list[HospitalityOrderItemIn] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def clean_items(cls, value: list[HospitalityOrderItemIn]) -> list[HospitalityOrderItemIn]:
        rows = [item for item in (value or []) if _num(item.quantity) > 0 and (_clean(item.name) or _clean(item.product_id) or _clean(item.inventory_item_id))]
        if not rows:
            raise ValueError("Agrega al menos un producto.")
        return rows[:80]


class HospitalityStatusIn(BaseModel):
    status: str = Field(..., max_length=40)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return _clean(value).lower().replace("_", " ").strip()


def _num(value: Any) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except Exception:
        return 0.0


def _money(value: Any) -> float:
    return round(_num(value), 2)


def _status(value: Any) -> str:
    raw = _norm(value or STATUS_PENDING)
    aliases = {
        "pending": STATUS_PENDING,
        "pendiente": STATUS_PENDING,
        "preparing": STATUS_PREPARING,
        "alistando": STATUS_PREPARING,
        "served": STATUS_SERVED,
        "entregado": STATUS_SERVED,
        "delivered": STATUS_SERVED,
        "closed": STATUS_CLOSED,
        "cerrado": STATUS_CLOSED,
    }
    return aliases.get(raw, STATUS_PENDING)


def _table_key(value: Any) -> str:
    return " ".join(_norm(value or "mesa").split())


def _customer_key(value: Any) -> str:
    return " ".join(_norm(value or "cliente").split())


def _json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _songs(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").split(",")
    return [_clean(item)[:120] for item in raw if _clean(item)][:3]


async def _ensure_storage(db: AsyncSession) -> None:
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS hospitality_orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                order_number VARCHAR(80) NOT NULL,
                table_number VARCHAR(120) NOT NULL,
                table_key VARCHAR(120) NOT NULL,
                order_type VARCHAR(40) NOT NULL DEFAULT 'table',
                source VARCHAR(60) NOT NULL DEFAULT 'client',
                status VARCHAR(40) NOT NULL DEFAULT 'pendiente',
                customer_name VARCHAR(180),
                people JSONB NOT NULL DEFAULT '[]'::jsonb,
                items JSONB NOT NULL DEFAULT '[]'::jsonb,
                songs JSONB NOT NULL DEFAULT '[]'::jsonb,
                notes TEXT,
                total NUMERIC(14,2) NOT NULL DEFAULT 0,
                inventory_deducted BOOLEAN NOT NULL DEFAULT FALSE,
                preparing_at TIMESTAMPTZ NULL,
                served_at TIMESTAMPTZ NULL,
                closed_at TIMESTAMPTZ NULL,
                archived_at TIMESTAMPTZ NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_orders_company_status ON hospitality_orders(company_id, status, created_at DESC);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_orders_company_table ON hospitality_orders(company_id, table_key, created_at DESC);"))


async def _company_exists(db: AsyncSession, company_id: uuid.UUID) -> bool:
    row = await db.execute(text("SELECT id FROM companies WHERE id = :company_id LIMIT 1"), {"company_id": str(company_id)})
    return row.first() is not None


async def _next_order_number(db: AsyncSession, company_id: uuid.UUID) -> str:
    today = _now().strftime("%Y%m%d")
    row = await db.execute(
        text(
            """
            SELECT COUNT(*) + 1
            FROM hospitality_orders
            WHERE company_id = :company_id
              AND order_number LIKE :prefix
            """
        ),
        {"company_id": str(company_id), "prefix": f"QR-{today}-%"},
    )
    number = int(row.scalar() or 1)
    return f"QR-{today}-{number:05d}"


async def _inventory_lookup(db: AsyncSession, company_id: uuid.UUID, raw_id: str | None) -> dict[str, Any] | None:
    item_id = _clean(raw_id)
    if not item_id:
        return None
    try:
        uuid.UUID(item_id)
    except Exception:
        return None

    exists = await db.execute(text("SELECT to_regclass('public.inventory_items')"))
    if not exists.scalar():
        return None

    result = await db.execute(
        text(
            """
            SELECT id, sku, name, reference, name_reference, current_stock, status
            FROM inventory_items
            WHERE id = :item_id
              AND company_id = :company_id
            LIMIT 1
            """
        ),
        {"item_id": item_id, "company_id": str(company_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _build_order_items(
    db: AsyncSession,
    company_id: uuid.UUID,
    raw_items: list[HospitalityOrderItemIn],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in raw_items:
        inventory_id = _clean(item.inventory_item_id or item.product_id)
        inventory = await _inventory_lookup(db, company_id, inventory_id)
        quantity = _money(item.quantity)
        unit_price = _money(item.unit_price)
        name = _clean(item.name)

        if inventory:
            name = name or _clean(inventory.get("name_reference")) or _clean(inventory.get("name")) or _clean(inventory.get("reference"))
            inventory_id = str(inventory["id"])
            sku = _clean(item.sku) or _clean(inventory.get("sku"))
        else:
            sku = _clean(item.sku)

        if not name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Producto sin nombre.")

        rows.append(
            {
                "id": f"line_{uuid.uuid4()}",
                "product_id": inventory_id,
                "inventory_item_id": inventory_id,
                "sku": sku,
                "name": name[:220],
                "quantity": quantity,
                "unit": _clean(item.unit) or "unidad",
                "unit_price": unit_price,
                "subtotal": _money(quantity * unit_price),
                "note": _clean(item.note),
                "created_at": _now().isoformat(),
            }
        )
    return rows


def _payload(row: Any) -> dict[str, Any]:
    data = dict(row)
    people = _json(data.get("people"), [])
    items = _json(data.get("items"), [])
    songs = _json(data.get("songs"), [])
    metadata = _json(data.get("metadata"), {})
    return {
        "id": str(data.get("id")),
        "company_id": str(data.get("company_id")),
        "order_number": data.get("order_number") or "",
        "table_number": data.get("table_number") or "",
        "table_key": data.get("table_key") or "",
        "type": data.get("order_type") or "table",
        "source": data.get("source") or "client",
        "status": _status(data.get("status")),
        "customer_name": data.get("customer_name") or "",
        "people": people if isinstance(people, list) else [],
        "items": items if isinstance(items, list) else [],
        "songs": songs if isinstance(songs, list) else [],
        "notes": data.get("notes") or "",
        "total": _money(data.get("total")),
        "inventory_deducted": bool(data.get("inventory_deducted")),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": _iso(data.get("created_at")),
        "updated_at": _iso(data.get("updated_at")),
        "preparing_at": _iso(data.get("preparing_at")),
        "served_at": _iso(data.get("served_at")),
        "closed_at": _iso(data.get("closed_at")),
    }


async def _fetch_order(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT *
            FROM hospitality_orders
            WHERE id = :order_id
              AND company_id = :company_id
            LIMIT 1
            """
        ),
        {"order_id": str(order_id), "company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pedido_no_encontrado")
    return _payload(row)


async def _deduct_inventory(db: AsyncSession, company_id: uuid.UUID, order: dict[str, Any]) -> None:
    if order.get("inventory_deducted"):
        return

    exists = await db.execute(text("SELECT to_regclass('public.inventory_items')"))
    if not exists.scalar():
        return

    for item in order.get("items") or []:
        item_id = _clean(item.get("inventory_item_id") or item.get("product_id"))
        if not item_id:
            continue
        try:
            uuid.UUID(item_id)
        except Exception:
            continue

        qty = _money(item.get("quantity"))
        if qty <= 0:
            continue

        row = await db.execute(
            text(
                """
                SELECT id, current_stock
                FROM inventory_items
                WHERE id = :item_id
                  AND company_id = :company_id
                LIMIT 1
                """
            ),
            {"item_id": item_id, "company_id": str(company_id)},
        )
        inventory = row.mappings().first()
        if not inventory:
            continue

        before = _money(inventory["current_stock"])
        if before < qty:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Stock insuficiente para {item.get('name')}. Disponible: {before}.")

        after = _money(before - qty)
        await db.execute(
            text(
                """
                UPDATE inventory_items
                SET current_stock = :after,
                    updated_at = NOW()
                WHERE id = :item_id
                  AND company_id = :company_id
                """
            ),
            {"after": after, "item_id": item_id, "company_id": str(company_id)},
        )

        movement_exists = await db.execute(text("SELECT to_regclass('public.inventory_movements')"))
        if movement_exists.scalar():
            await db.execute(
                text(
                    """
                    INSERT INTO inventory_movements (
                        id, company_id, item_id, movement_type, quantity_delta,
                        stock_before, stock_after, source_module, source_ref, notes, created_at, updated_at
                    )
                    VALUES (
                        :id, :company_id, :item_id, 'hospitality_sale', :delta,
                        :before, :after, 'hospitality_orders', :source_ref, :notes, NOW(), NOW()
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "company_id": str(company_id),
                    "item_id": item_id,
                    "delta": -qty,
                    "before": before,
                    "after": after,
                    "source_ref": order.get("order_number") or order.get("id"),
                    "notes": f"{order.get('table_number') or 'Mesa'} / {item.get('name') or 'Producto'}",
                },
            )


@router.get("/companies/{company_id}/health")
async def hospitality_health(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")
    return {"ok": True, "company_id": str(company_id), "service": "clonexa-hospitality", "modules": ["orders"]}


@router.get("/companies/{company_id}/inventory-lite")
async def hospitality_inventory_lite(
    company_id: uuid.UUID,
    limit: int = Query(default=120, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    exists = await db.execute(text("SELECT to_regclass('public.inventory_items')"))
    if not exists.scalar():
        return {"ok": True, "company_id": str(company_id), "inventory": []}

    result = await db.execute(
        text(
            """
            SELECT id, sku, name, reference, name_reference, current_stock, status
            FROM inventory_items
            WHERE company_id = :company_id
              AND COALESCE(status, 'active') = 'active'
            ORDER BY lower(COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), NULLIF(reference, ''), sku, id::text))
            LIMIT :limit
            """
        ),
        {"company_id": str(company_id), "limit": limit},
    )
    inventory = [
        {
            "id": str(row["id"]),
            "sku": row["sku"] or "",
            "name": row["name_reference"] or row["name"] or row["reference"] or row["sku"] or str(row["id"]),
            "price": 0,
            "stock": _money(row["current_stock"]),
            "active": (row["status"] or "active") == "active",
        }
        for row in result.mappings().all()
    ]
    return {"ok": True, "company_id": str(company_id), "inventory": inventory}


@router.get("/companies/{company_id}/orders")
async def list_hospitality_orders(
    company_id: uuid.UUID,
    status_filter: str = Query(default="active", alias="status"),
    limit: int = Query(default=180, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    where = ["company_id = :company_id"]
    params: dict[str, Any] = {"company_id": str(company_id), "limit": limit}
    clean_status = _status(status_filter)
    if _norm(status_filter) == "active":
        where.append("status IN ('pendiente', 'alistando', 'entregado')")
    elif _norm(status_filter) not in {"all", "todos"}:
        where.append("status = :status")
        params["status"] = clean_status

    result = await db.execute(
        text(
            f"""
            SELECT *
            FROM hospitality_orders
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        params,
    )
    orders = [_payload(row) for row in result.mappings().all()]
    counts = {STATUS_PENDING: 0, STATUS_PREPARING: 0, STATUS_SERVED: 0, STATUS_CLOSED: 0}
    total_open = 0.0
    for order in orders:
        counts[_status(order.get("status"))] = counts.get(_status(order.get("status")), 0) + 1
        if order.get("status") in ACTIVE_STATUSES:
            total_open += _money(order.get("total"))

    return {
        "ok": True,
        "company_id": str(company_id),
        "orders": orders,
        "tables": orders,
        "summary": {
            "pending": counts[STATUS_PENDING],
            "preparing": counts[STATUS_PREPARING],
            "served": counts[STATUS_SERVED],
            "closed": counts[STATUS_CLOSED],
            "open_total": _money(total_open),
            "total": len(orders),
        },
    }


@router.post("/companies/{company_id}/orders", status_code=status.HTTP_201_CREATED)
async def create_hospitality_order(
    company_id: uuid.UUID,
    payload: HospitalityOrderCreateIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    items = await _build_order_items(db, company_id, payload.items)
    total = _money(sum(_num(item.get("subtotal")) for item in items))
    table_number = _clean(payload.table) or "Barra"
    customer_name = _clean(payload.customer) or "Cliente barra"
    source = _clean(payload.source) or "client"
    order_type = "bar_sale" if _table_key(table_number) == "barra" or source in {"bar_manual", "barra"} else "table"
    order_number = await _next_order_number(db, company_id)
    person = {
        "id": f"person_{uuid.uuid4()}",
        "name": customer_name,
        "customer_key": _customer_key(customer_name),
        "total": total,
        "items": items,
    }

    result = await db.execute(
        text(
            """
            INSERT INTO hospitality_orders (
                company_id, order_number, table_number, table_key, order_type, source,
                status, customer_name, people, items, songs, notes, total, metadata,
                created_at, updated_at
            )
            VALUES (
                :company_id, :order_number, :table_number, :table_key, :order_type, :source,
                'pendiente', :customer_name, CAST(:people AS jsonb), CAST(:items AS jsonb),
                CAST(:songs AS jsonb), :notes, :total, CAST(:metadata AS jsonb), NOW(), NOW()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "order_number": order_number,
            "table_number": table_number,
            "table_key": _table_key(table_number),
            "order_type": order_type,
            "source": source,
            "customer_name": customer_name,
            "people": json.dumps([person], ensure_ascii=False),
            "items": json.dumps(items, ensure_ascii=False),
            "songs": json.dumps(_songs(payload.songs), ensure_ascii=False),
            "notes": _clean(payload.notes),
            "total": total,
            "metadata": json.dumps({"source_product": "bar-bot-completo.zip"}, ensure_ascii=False),
        },
    )
    await db.commit()
    order = _payload(result.mappings().first())
    return {"ok": True, "order": order, "table": order}


@router.patch("/companies/{company_id}/orders/{order_id}/status")
async def update_hospitality_order_status(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: HospitalityStatusIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    order = await _fetch_order(db, company_id, order_id)
    current = _status(order.get("status"))
    next_status = _status(payload.status)
    allowed = {
        STATUS_PENDING: {STATUS_PREPARING},
        STATUS_PREPARING: {STATUS_SERVED},
        STATUS_SERVED: {STATUS_CLOSED},
        STATUS_CLOSED: set(),
    }
    if next_status not in allowed.get(current, set()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Transicion no permitida: {current} -> {next_status}")

    if next_status == STATUS_SERVED:
        await _deduct_inventory(db, company_id, order)

    timestamp_column = {
        STATUS_PREPARING: "preparing_at",
        STATUS_SERVED: "served_at",
        STATUS_CLOSED: "closed_at",
    }.get(next_status)

    await db.execute(
        text(
            f"""
            UPDATE hospitality_orders
            SET status = :status,
                inventory_deducted = CASE WHEN :status = 'entregado' THEN TRUE ELSE inventory_deducted END,
                {timestamp_column} = COALESCE({timestamp_column}, NOW()),
                updated_at = NOW()
            WHERE id = :order_id
              AND company_id = :company_id
            """
        ),
        {"status": next_status, "order_id": str(order_id), "company_id": str(company_id)},
    )
    await db.commit()
    saved = await _fetch_order(db, company_id, order_id)
    return {"ok": True, "order": saved, "table": saved}


@router.post("/companies/{company_id}/orders/{order_id}/close-table")
async def close_hospitality_order(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    order = await _fetch_order(db, company_id, order_id)
    if _status(order.get("status")) != STATUS_SERVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="solo_se_puede_cerrar_mesa_entregada")

    await db.execute(
        text(
            """
            UPDATE hospitality_orders
            SET status = 'cerrado',
                closed_at = COALESCE(closed_at, NOW()),
                updated_at = NOW()
            WHERE id = :order_id
              AND company_id = :company_id
            """
        ),
        {"order_id": str(order_id), "company_id": str(company_id)},
    )
    await db.commit()
    saved = await _fetch_order(db, company_id, order_id)
    return {"ok": True, "order": saved, "table": saved}
