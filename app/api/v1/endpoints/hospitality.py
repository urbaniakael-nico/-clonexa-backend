from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
PAYMENT_METHODS = {"cash", "transfer", "card", "other"}
PAYMENT_LABELS = {
    "cash": "Efectivo",
    "transfer": "Transferencia",
    "card": "Tarjeta",
    "other": "Otro",
}


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
    payment_method: str | None = Field(default="other", max_length=40)
    access_code: str | None = Field(default="", max_length=12)
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


class HospitalityCloseIn(BaseModel):
    payment_method: str | None = Field(default=None, max_length=40)


class HospitalityClosureCreateIn(BaseModel):
    cash_total: float = Field(default=0, ge=0)
    transfer_total: float = Field(default=0, ge=0)
    card_total: float = Field(default=0, ge=0)
    other_total: float = Field(default=0, ge=0)
    closed_by: str | None = Field(default="", max_length=180)
    notes: str | None = Field(default="", max_length=900)


class HospitalityLoyaltyCampaignIn(BaseModel):
    title: str | None = Field(default="Reto de consumo", max_length=160)
    prize: str | None = Field(default="", max_length=220)
    description: str | None = Field(default="", max_length=700)
    registration_ends_at: datetime | None = Field(default=None)
    starts_at: datetime
    ends_at: datetime


class HospitalityLoyaltyParticipantIn(BaseModel):
    table: str | None = Field(default="Mesa", max_length=120)
    team_name: str | None = Field(default="", max_length=160)
    accepted: bool = Field(default=True)


class HospitalityScorePoolCampaignIn(BaseModel):
    title: str | None = Field(default="Polla de marcador", max_length=160)
    prize: str | None = Field(default="", max_length=220)
    description: str | None = Field(default="", max_length=700)
    team_a: str = Field(min_length=1, max_length=120)
    team_b: str = Field(min_length=1, max_length=120)


class HospitalityScorePredictionIn(BaseModel):
    table: str | None = Field(default="Mesa", max_length=120)
    team_name: str | None = Field(default="", max_length=160)
    score_a: int = Field(default=0, ge=0, le=99)
    score_b: int = Field(default=0, ge=0, le=99)
    access_code: str | None = Field(default="", max_length=12)


class HospitalityTableAccessIn(BaseModel):
    table: str | None = Field(default="Mesa", max_length=120)
    duration_hours: int = Field(default=12, ge=1, le=24)


class HospitalityTableAccessVerifyIn(BaseModel):
    table: str | None = Field(default="Mesa", max_length=120)
    access_code: str | None = Field(default="", max_length=12)


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


def _payment_method(value: Any) -> str:
    raw = _norm(value or "other")
    aliases = {
        "cash": "cash",
        "efectivo": "cash",
        "efec": "cash",
        "transfer": "transfer",
        "transferencia": "transfer",
        "transf": "transfer",
        "bank": "transfer",
        "card": "card",
        "tarjeta": "card",
        "credito": "card",
        "debito": "card",
        "other": "other",
        "otro": "other",
        "otros": "other",
    }
    return aliases.get(raw, "other")


def _table_key(value: Any) -> str:
    return " ".join(_norm(value or "mesa").split())


def _access_code(value: Any) -> str:
    return "".join(ch for ch in _clean(value).upper() if ch.isalnum())[:12]


def _new_access_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(5))


def _customer_key(value: Any) -> str:
    return " ".join(_norm(value or "cliente").split())


def _public_base_url(request: Request, fallback: str | None = None) -> str:
    raw = _clean(fallback).rstrip("/")
    if raw.startswith(("http://", "https://")):
        return raw
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def _json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
                payment_method VARCHAR(40) NOT NULL DEFAULT 'other',
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
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS order_number VARCHAR(80) NOT NULL DEFAULT '';"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS table_number VARCHAR(120) NOT NULL DEFAULT 'Mesa';"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS table_key VARCHAR(120) NOT NULL DEFAULT 'mesa';"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS order_type VARCHAR(40) NOT NULL DEFAULT 'table';"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS source VARCHAR(60) NOT NULL DEFAULT 'client';"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS payment_method VARCHAR(40) NOT NULL DEFAULT 'other';"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'pendiente';"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS customer_name VARCHAR(180);"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS people JSONB NOT NULL DEFAULT '[]'::jsonb;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS items JSONB NOT NULL DEFAULT '[]'::jsonb;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS songs JSONB NOT NULL DEFAULT '[]'::jsonb;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS notes TEXT;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS total NUMERIC(14,2) NOT NULL DEFAULT 0;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS inventory_deducted BOOLEAN NOT NULL DEFAULT FALSE;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS preparing_at TIMESTAMPTZ NULL;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS served_at TIMESTAMPTZ NULL;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ NULL;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_orders_company_status ON hospitality_orders(company_id, status, created_at DESC);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_orders_company_table ON hospitality_orders(company_id, table_key, created_at DESC);"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS hospitality_day_closures (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                closure_number VARCHAR(80) NOT NULL,
                opened_at TIMESTAMPTZ NULL,
                closed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                closed_by VARCHAR(180),
                orders_count INTEGER NOT NULL DEFAULT 0,
                total_sold NUMERIC(14,2) NOT NULL DEFAULT 0,
                cash_total NUMERIC(14,2) NOT NULL DEFAULT 0,
                transfer_total NUMERIC(14,2) NOT NULL DEFAULT 0,
                card_total NUMERIC(14,2) NOT NULL DEFAULT 0,
                other_total NUMERIC(14,2) NOT NULL DEFAULT 0,
                products JSONB NOT NULL DEFAULT '[]'::jsonb,
                tables JSONB NOT NULL DEFAULT '[]'::jsonb,
                songs JSONB NOT NULL DEFAULT '[]'::jsonb,
                summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                order_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS closure_number VARCHAR(80) NOT NULL DEFAULT '';"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS opened_at TIMESTAMPTZ NULL;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS closed_by VARCHAR(180);"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS orders_count INTEGER NOT NULL DEFAULT 0;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS total_sold NUMERIC(14,2) NOT NULL DEFAULT 0;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS cash_total NUMERIC(14,2) NOT NULL DEFAULT 0;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS transfer_total NUMERIC(14,2) NOT NULL DEFAULT 0;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS card_total NUMERIC(14,2) NOT NULL DEFAULT 0;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS other_total NUMERIC(14,2) NOT NULL DEFAULT 0;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS products JSONB NOT NULL DEFAULT '[]'::jsonb;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS tables JSONB NOT NULL DEFAULT '[]'::jsonb;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS songs JSONB NOT NULL DEFAULT '[]'::jsonb;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS summary JSONB NOT NULL DEFAULT '{}'::jsonb;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS order_ids JSONB NOT NULL DEFAULT '[]'::jsonb;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS notes TEXT;"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_day_closures ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_closures_company_closed ON hospitality_day_closures(company_id, closed_at DESC);"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS hospitality_loyalty_campaigns (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                title VARCHAR(160) NOT NULL DEFAULT 'Reto de consumo',
                prize VARCHAR(220) NOT NULL DEFAULT '',
                description TEXT,
                registration_ends_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                starts_at TIMESTAMPTZ NOT NULL,
                ends_at TIMESTAMPTZ NOT NULL,
                status VARCHAR(40) NOT NULL DEFAULT 'active',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS title VARCHAR(160) NOT NULL DEFAULT 'Reto de consumo';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS prize VARCHAR(220) NOT NULL DEFAULT '';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS description TEXT;"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS campaign_type VARCHAR(40) NOT NULL DEFAULT 'consumption';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS team_a VARCHAR(120) NOT NULL DEFAULT '';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS team_b VARCHAR(120) NOT NULL DEFAULT '';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS registration_ends_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS ends_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'active';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_loyalty_campaigns_company_status ON hospitality_loyalty_campaigns(company_id, status, starts_at DESC);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_loyalty_campaigns_company_type ON hospitality_loyalty_campaigns(company_id, campaign_type, status, starts_at DESC);"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS hospitality_loyalty_participants (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                campaign_id UUID NOT NULL REFERENCES hospitality_loyalty_campaigns(id) ON DELETE CASCADE,
                table_key VARCHAR(120) NOT NULL,
                table_number VARCHAR(120) NOT NULL,
                team_name VARCHAR(160) NOT NULL,
                accepted BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    await db.execute(text("ALTER TABLE hospitality_loyalty_participants ADD COLUMN IF NOT EXISTS table_key VARCHAR(120) NOT NULL DEFAULT 'mesa';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_participants ADD COLUMN IF NOT EXISTS table_number VARCHAR(120) NOT NULL DEFAULT 'Mesa';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_participants ADD COLUMN IF NOT EXISTS team_name VARCHAR(160) NOT NULL DEFAULT 'Equipo';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_participants ADD COLUMN IF NOT EXISTS accepted BOOLEAN NOT NULL DEFAULT TRUE;"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_participants ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_participants ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_hospitality_loyalty_participants_campaign_table ON hospitality_loyalty_participants(campaign_id, table_key);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_loyalty_participants_company ON hospitality_loyalty_participants(company_id, campaign_id);"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS hospitality_loyalty_predictions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                campaign_id UUID NOT NULL REFERENCES hospitality_loyalty_campaigns(id) ON DELETE CASCADE,
                table_key VARCHAR(120) NOT NULL,
                table_number VARCHAR(120) NOT NULL,
                team_name VARCHAR(160) NOT NULL DEFAULT '',
                score_a INTEGER NOT NULL DEFAULT 0,
                score_b INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    await db.execute(text("ALTER TABLE hospitality_loyalty_predictions ADD COLUMN IF NOT EXISTS table_key VARCHAR(120) NOT NULL DEFAULT 'mesa';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_predictions ADD COLUMN IF NOT EXISTS table_number VARCHAR(120) NOT NULL DEFAULT 'Mesa';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_predictions ADD COLUMN IF NOT EXISTS team_name VARCHAR(160) NOT NULL DEFAULT '';"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_predictions ADD COLUMN IF NOT EXISTS score_a INTEGER NOT NULL DEFAULT 0;"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_predictions ADD COLUMN IF NOT EXISTS score_b INTEGER NOT NULL DEFAULT 0;"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_predictions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_loyalty_predictions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_hospitality_loyalty_predictions_campaign_table ON hospitality_loyalty_predictions(campaign_id, table_key);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_loyalty_predictions_company ON hospitality_loyalty_predictions(company_id, campaign_id);"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS hospitality_table_access (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                table_key VARCHAR(120) NOT NULL,
                table_number VARCHAR(120) NOT NULL,
                access_code VARCHAR(12) NOT NULL,
                status VARCHAR(40) NOT NULL DEFAULT 'active',
                activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    await db.execute(text("ALTER TABLE hospitality_table_access ADD COLUMN IF NOT EXISTS table_key VARCHAR(120) NOT NULL DEFAULT 'mesa';"))
    await db.execute(text("ALTER TABLE hospitality_table_access ADD COLUMN IF NOT EXISTS table_number VARCHAR(120) NOT NULL DEFAULT 'Mesa';"))
    await db.execute(text("ALTER TABLE hospitality_table_access ADD COLUMN IF NOT EXISTS access_code VARCHAR(12) NOT NULL DEFAULT '00000';"))
    await db.execute(text("ALTER TABLE hospitality_table_access ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'active';"))
    await db.execute(text("ALTER TABLE hospitality_table_access ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_table_access ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_table_access ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("ALTER TABLE hospitality_table_access ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_hospitality_table_access_company_table ON hospitality_table_access(company_id, table_key, status, expires_at DESC);"))


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


async def _next_closure_number(db: AsyncSession, company_id: uuid.UUID) -> str:
    today = _now().strftime("%Y%m%d")
    row = await db.execute(
        text(
            """
            SELECT COUNT(*) + 1
            FROM hospitality_day_closures
            WHERE company_id = :company_id
              AND closure_number LIKE :prefix
            """
        ),
        {"company_id": str(company_id), "prefix": f"ARQ-{today}-%"},
    )
    number = int(row.scalar() or 1)
    return f"ARQ-{today}-{number:04d}"


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
        "payment_method": _payment_method(data.get("payment_method")),
        "payment_label": PAYMENT_LABELS.get(_payment_method(data.get("payment_method")), "Otro"),
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
        "archived_at": _iso(data.get("archived_at")),
    }


def _closure_payload(row: Any) -> dict[str, Any]:
    data = dict(row)
    products = _json(data.get("products"), [])
    tables = _json(data.get("tables"), [])
    songs = _json(data.get("songs"), [])
    summary = _json(data.get("summary"), {})
    order_ids = _json(data.get("order_ids"), [])
    return {
        "id": str(data.get("id")),
        "company_id": str(data.get("company_id")),
        "closure_number": data.get("closure_number") or "",
        "opened_at": _iso(data.get("opened_at")),
        "closed_at": _iso(data.get("closed_at")),
        "closed_by": data.get("closed_by") or "",
        "orders_count": int(data.get("orders_count") or 0),
        "total_sold": _money(data.get("total_sold")),
        "cash_total": _money(data.get("cash_total")),
        "transfer_total": _money(data.get("transfer_total")),
        "card_total": _money(data.get("card_total")),
        "other_total": _money(data.get("other_total")),
        "products": products if isinstance(products, list) else [],
        "tables": tables if isinstance(tables, list) else [],
        "songs": songs if isinstance(songs, list) else [],
        "summary": summary if isinstance(summary, dict) else {},
        "order_ids": order_ids if isinstance(order_ids, list) else [],
        "notes": data.get("notes") or "",
        "created_at": _iso(data.get("created_at")),
        "updated_at": _iso(data.get("updated_at")),
    }


def _campaign_payload(row: Any, leaderboard: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    data = dict(row)
    now = _now()
    registration_ends = data.get("registration_ends_at") or data.get("starts_at")
    starts = data.get("starts_at")
    ends = data.get("ends_at")
    if isinstance(registration_ends, datetime):
        registration_ends = _aware(registration_ends)
    if isinstance(starts, datetime):
        starts = _aware(starts)
    if isinstance(ends, datetime):
        ends = _aware(ends)
    status_value = str(data.get("status") or "active")
    registration_open = status_value == "active" and isinstance(registration_ends, datetime) and now < registration_ends
    tournament_phase = "open"
    if isinstance(starts, datetime) and now < starts:
        tournament_phase = "scheduled"
    if status_value != "active" or (isinstance(ends, datetime) and now >= ends):
        tournament_phase = "closed"
    phase = "registration_open" if registration_open else tournament_phase
    signup_seconds_left = max(int(((registration_ends if isinstance(registration_ends, datetime) else now) - now).total_seconds()), 0)
    tournament_seconds_left = max(int(((ends if isinstance(ends, datetime) else now) - now).total_seconds()), 0)
    rows = leaderboard or []
    winner = rows[0] if tournament_phase == "closed" and rows and _money(rows[0].get("total")) > 0 else None
    return {
        "id": str(data.get("id")),
        "company_id": str(data.get("company_id")),
        "title": data.get("title") or "Reto de consumo",
        "prize": data.get("prize") or "",
        "description": data.get("description") or "",
        "campaign_type": data.get("campaign_type") or "consumption",
        "team_a": data.get("team_a") or "",
        "team_b": data.get("team_b") or "",
        "registration_ends_at": _iso(data.get("registration_ends_at") or data.get("starts_at")),
        "starts_at": _iso(data.get("starts_at")),
        "ends_at": _iso(data.get("ends_at")),
        "status": data.get("status") or "active",
        "phase": phase,
        "registration_open": registration_open,
        "tournament_phase": tournament_phase,
        "signup_seconds_left": signup_seconds_left,
        "tournament_seconds_left": tournament_seconds_left,
        "seconds_left": tournament_seconds_left,
        "winner": winner,
        "leaderboard": rows,
        "created_at": _iso(data.get("created_at")),
        "updated_at": _iso(data.get("updated_at")),
    }


def _table_access_payload(row: Any | None, include_code: bool = False) -> dict[str, Any]:
    if not row:
        return {"active": False, "access_code": "" if include_code else None, "expires_at": ""}
    data = dict(row)
    expires_at = data.get("expires_at")
    if isinstance(expires_at, datetime):
        expires_at = _aware(expires_at)
    active = (data.get("status") or "active") == "active" and isinstance(expires_at, datetime) and expires_at > _now()
    payload = {
        "active": active,
        "table_key": data.get("table_key") or "",
        "table_number": data.get("table_number") or "",
        "expires_at": _iso(data.get("expires_at")),
        "activated_at": _iso(data.get("activated_at")),
    }
    if include_code:
        payload["access_code"] = data.get("access_code") or ""
    return payload


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


async def _create_day_closure(
    db: AsyncSession,
    company_id: uuid.UUID,
    payload: HospitalityClosureCreateIn,
) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT *
            FROM hospitality_orders
            WHERE company_id = :company_id
              AND archived_at IS NULL
            ORDER BY created_at ASC
            """
        ),
        {"company_id": str(company_id)},
    )
    raw_rows = result.mappings().all()
    if not raw_rows:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="no_hay_pedidos_para_cerrar")

    orders = [_payload(row) for row in raw_rows]
    total_sold = _money(sum(_num(order.get("total")) for order in orders))
    method_totals = {method: 0.0 for method in PAYMENT_METHODS}
    product_map: dict[str, dict[str, Any]] = {}
    table_map: dict[str, dict[str, Any]] = {}
    song_map: dict[str, dict[str, Any]] = {}
    opened_at: datetime | None = None
    closed_at = _now()

    for raw, order in zip(raw_rows, orders):
        method = _payment_method(order.get("payment_method"))
        method_totals[method] = _money(method_totals.get(method, 0) + _num(order.get("total")))

        created_at = raw.get("created_at")
        if isinstance(created_at, datetime):
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            opened_at = created_at if opened_at is None or created_at < opened_at else opened_at

        table_name = _clean(order.get("table_number")) or "Barra"
        table_key = _table_key(table_name)
        table_row = table_map.setdefault(
            table_key,
            {"table": table_name, "orders": 0, "items_quantity": 0.0, "total": 0.0},
        )
        table_row["orders"] += 1
        table_row["total"] = _money(table_row["total"] + _num(order.get("total")))

        for item in order.get("items") or []:
            qty = _money(item.get("quantity"))
            subtotal = _money(item.get("subtotal") or qty * _num(item.get("unit_price")))
            table_row["items_quantity"] = _money(table_row["items_quantity"] + qty)
            product_key = _clean(item.get("inventory_item_id") or item.get("product_id") or item.get("sku") or item.get("name")).lower()
            if not product_key:
                continue
            product_row = product_map.setdefault(
                product_key,
                {
                    "name": _clean(item.get("name")) or "Producto",
                    "sku": _clean(item.get("sku")),
                    "quantity": 0.0,
                    "unit_price": _money(item.get("unit_price")),
                    "total": 0.0,
                },
            )
            product_row["quantity"] = _money(product_row["quantity"] + qty)
            product_row["total"] = _money(product_row["total"] + subtotal)
            if not product_row.get("unit_price") and qty:
                product_row["unit_price"] = _money(subtotal / qty)

        for song in order.get("songs") or []:
            clean_song = _clean(song)
            if not clean_song:
                continue
            song_key = clean_song.lower()
            song_row = song_map.setdefault(song_key, {"song": clean_song, "count": 0})
            song_row["count"] += 1

    cash_total = _money(payload.cash_total)
    transfer_total = _money(payload.transfer_total)
    card_total = _money(payload.card_total)
    other_total = _money(payload.other_total)
    if _money(cash_total + transfer_total + card_total + other_total) <= 0 and total_sold > 0:
        cash_total = _money(method_totals.get("cash"))
        transfer_total = _money(method_totals.get("transfer"))
        card_total = _money(method_totals.get("card"))
        other_total = _money(method_totals.get("other"))
        if _money(cash_total + transfer_total + card_total + other_total) <= 0:
            other_total = total_sold

    products = sorted(product_map.values(), key=lambda row: (_num(row.get("total")), _num(row.get("quantity"))), reverse=True)
    tables = sorted(table_map.values(), key=lambda row: _num(row.get("total")), reverse=True)
    songs = sorted(song_map.values(), key=lambda row: int(row.get("count") or 0), reverse=True)
    worked_minutes = 0
    if opened_at:
        worked_minutes = max(int((closed_at - opened_at.astimezone(timezone.utc)).total_seconds() // 60), 0)

    closure_number = await _next_closure_number(db, company_id)
    order_ids = [order["id"] for order in orders if order.get("id")]
    summary = {
        "total_sold": total_sold,
        "payment_total": _money(cash_total + transfer_total + card_total + other_total),
        "payment_difference": _money((cash_total + transfer_total + card_total + other_total) - total_sold),
        "payment_breakdown": {
            "cash": cash_total,
            "transfer": transfer_total,
            "card": card_total,
            "other": other_total,
        },
        "top_product": products[0] if products else None,
        "top_table": tables[0] if tables else None,
        "top_song": songs[0] if songs else None,
        "worked_minutes": worked_minutes,
        "worked_hours": round(worked_minutes / 60, 2) if worked_minutes else 0,
    }

    inserted = await db.execute(
        text(
            """
            INSERT INTO hospitality_day_closures (
                company_id, closure_number, opened_at, closed_at, closed_by,
                orders_count, total_sold, cash_total, transfer_total, card_total, other_total,
                products, tables, songs, summary, order_ids, notes, created_at, updated_at
            )
            VALUES (
                :company_id, :closure_number, :opened_at, NOW(), :closed_by,
                :orders_count, :total_sold, :cash_total, :transfer_total, :card_total, :other_total,
                CAST(:products AS jsonb), CAST(:tables AS jsonb), CAST(:songs AS jsonb),
                CAST(:summary AS jsonb), CAST(:order_ids AS jsonb), :notes, NOW(), NOW()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "closure_number": closure_number,
            "opened_at": opened_at,
            "closed_by": _clean(payload.closed_by)[:180],
            "orders_count": len(orders),
            "total_sold": total_sold,
            "cash_total": cash_total,
            "transfer_total": transfer_total,
            "card_total": card_total,
            "other_total": other_total,
            "products": json.dumps(products, ensure_ascii=False),
            "tables": json.dumps(tables, ensure_ascii=False),
            "songs": json.dumps(songs, ensure_ascii=False),
            "summary": json.dumps(summary, ensure_ascii=False),
            "order_ids": json.dumps(order_ids, ensure_ascii=False),
            "notes": _clean(payload.notes),
        },
    )
    closure = _closure_payload(inserted.mappings().first())

    await db.execute(
        text(
            """
            UPDATE hospitality_orders
            SET archived_at = COALESCE(archived_at, NOW()),
                metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:metadata AS jsonb),
                updated_at = NOW()
            WHERE company_id = :company_id
              AND archived_at IS NULL
            """
        ),
        {
            "company_id": str(company_id),
            "metadata": json.dumps(
                {"closure_id": closure["id"], "closure_number": closure["closure_number"]},
                ensure_ascii=False,
            ),
        },
    )
    await db.execute(
        text(
            """
            UPDATE hospitality_table_access
            SET status = 'closed',
                updated_at = NOW()
            WHERE company_id = :company_id
              AND status = 'active'
            """
        ),
        {"company_id": str(company_id)},
    )
    return closure


async def _active_loyalty_campaign(
    db: AsyncSession,
    company_id: uuid.UUID,
    campaign_type: str = "consumption",
) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            """
            SELECT *
            FROM hospitality_loyalty_campaigns
            WHERE company_id = :company_id
              AND status = 'active'
              AND campaign_type = :campaign_type
            ORDER BY starts_at DESC, created_at DESC
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "campaign_type": _clean(campaign_type) or "consumption"},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _loyalty_leaderboard(db: AsyncSession, campaign: dict[str, Any]) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT p.id,
                   p.table_key,
                   p.table_number,
                   p.team_name,
                   p.accepted,
                   p.created_at AS participant_created_at,
                   o.id AS order_id,
                   o.total AS order_total,
                   o.items AS order_items,
                   o.created_at AS order_created_at
            FROM hospitality_loyalty_participants p
            LEFT JOIN hospitality_orders o
              ON o.company_id = p.company_id
             AND o.table_key = p.table_key
             AND o.created_at >= :starts_at
             AND o.created_at < :ends_at
            WHERE p.company_id = :company_id
              AND p.campaign_id = :campaign_id
              AND p.accepted = TRUE
            ORDER BY p.created_at ASC, o.created_at ASC
            """
        ),
        {
            "company_id": str(campaign["company_id"]),
            "campaign_id": str(campaign["id"]),
            "starts_at": campaign["starts_at"],
            "ends_at": campaign["ends_at"],
        },
    )
    rows = result.mappings().all()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        participant_id = str(row["id"])
        if participant_id not in grouped:
            grouped[participant_id] = {
                "rank": 0,
                "participant_id": participant_id,
                "table_key": row["table_key"] or "",
                "table_number": row["table_number"] or "",
                "team_name": row["team_name"] or "Equipo",
                "total": 0.0,
                "orders_count": 0,
                "products_map": {},
                "products": [],
                "percent": 0,
                "last_order_at": "",
                "joined_at": _iso(row["participant_created_at"]),
                "_joined_sort": row["participant_created_at"],
            }
        target = grouped[participant_id]
        if not row["order_id"]:
            continue
        target["total"] += _money(row["order_total"])
        target["orders_count"] += 1
        target["last_order_at"] = _iso(row["order_created_at"])
        products_map = target["products_map"]
        for item in _json(row["order_items"], []):
            if not isinstance(item, dict):
                continue
            key = _clean(item.get("product_id") or item.get("inventory_item_id") or item.get("sku") or item.get("name") or "producto").lower()
            if key not in products_map:
                products_map[key] = {
                    "name": item.get("name") or item.get("sku") or "Producto",
                    "quantity": 0.0,
                    "total": 0.0,
                }
            product = products_map[key]
            product["quantity"] += _money(item.get("quantity"))
            product["total"] += _money(item.get("subtotal") or (_num(item.get("quantity")) * _num(item.get("unit_price"))))

    leaderboard = list(grouped.values())
    max_total = max((_money(row["total"]) for row in leaderboard), default=0.0)
    leaderboard.sort(key=lambda row: (-_money(row["total"]), -int(row["orders_count"]), row.get("_joined_sort") or _now()))
    for index, row in enumerate(leaderboard, start=1):
        row["rank"] = index
        row["total"] = _money(row["total"])
        row["percent"] = round((row["total"] / max_total) * 100, 1) if max_total > 0 else 0
        row["products"] = sorted(row.pop("products_map", {}).values(), key=lambda item: _money(item["total"]), reverse=True)
        row.pop("_joined_sort", None)
    return leaderboard


async def _score_pool_predictions(db: AsyncSession, campaign: dict[str, Any]) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT id,
                   table_key,
                   table_number,
                   team_name,
                   score_a,
                   score_b,
                   created_at,
                   updated_at
            FROM hospitality_loyalty_predictions
            WHERE company_id = :company_id
              AND campaign_id = :campaign_id
            ORDER BY updated_at DESC, created_at DESC
            """
        ),
        {"company_id": str(campaign["company_id"]), "campaign_id": str(campaign["id"])},
    )
    rows = []
    for row in result.mappings().all():
        rows.append(
            {
                "id": str(row["id"]),
                "table_key": row["table_key"] or "",
                "table_number": row["table_number"] or "",
                "team_name": row["team_name"] or "",
                "score_a": int(row["score_a"] or 0),
                "score_b": int(row["score_b"] or 0),
                "created_at": _iso(row["created_at"]),
                "updated_at": _iso(row["updated_at"]),
            }
        )
    return rows


def _score_pool_payload(row: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    payload = _campaign_payload(row, [])
    payload["predictions"] = predictions
    return payload


async def _loyalty_response(
    db: AsyncSession,
    company_id: uuid.UUID,
    campaign: dict[str, Any] | None = None,
    table: str | None = None,
) -> dict[str, Any]:
    if campaign is None:
        campaign = await _active_loyalty_campaign(db, company_id, "consumption")
    score_campaign = await _active_loyalty_campaign(db, company_id, "score_pool")
    table_key = _table_key(table) if _clean(table) else ""
    campaign_payload = None
    participant = None
    if campaign:
        leaderboard = await _loyalty_leaderboard(db, campaign)
        participant = next((row for row in leaderboard if row["table_key"] == table_key), None) if table_key else None
        campaign_payload = _campaign_payload(campaign, leaderboard)

    score_payload = None
    score_prediction = None
    if score_campaign:
        predictions = await _score_pool_predictions(db, score_campaign)
        score_prediction = next((row for row in predictions if row["table_key"] == table_key), None) if table_key else None
        score_payload = _score_pool_payload(score_campaign, predictions)

    return {
        "ok": True,
        "campaign": campaign_payload,
        "participant": participant,
        "score_campaign": score_payload,
        "score_prediction": score_prediction,
    }


async def _fetch_active_table_access(db: AsyncSession, company_id: uuid.UUID, table: str) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            """
            SELECT *
            FROM hospitality_table_access
            WHERE company_id = :company_id
              AND table_key = :table_key
              AND status = 'active'
              AND expires_at > NOW()
            ORDER BY activated_at DESC
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "table_key": _table_key(table)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _require_table_access(db: AsyncSession, company_id: uuid.UUID, table: str, code: str | None) -> None:
    access = await _fetch_active_table_access(db, company_id, table)
    if not access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="mesa_no_activada")
    if _access_code(access.get("access_code")) != _access_code(code):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="clave_de_mesa_invalida")


async def _close_table_access_if_idle(db: AsyncSession, company_id: uuid.UUID, table_key: str) -> None:
    result = await db.execute(
        text(
            """
            SELECT COUNT(*) AS active_count
            FROM hospitality_orders
            WHERE company_id = :company_id
              AND table_key = :table_key
              AND archived_at IS NULL
              AND status IN ('pendiente', 'alistando', 'entregado')
            """
        ),
        {"company_id": str(company_id), "table_key": _table_key(table_key)},
    )
    active_count = int(result.scalar() or 0)
    if active_count > 0:
        return
    await db.execute(
        text(
            """
            UPDATE hospitality_table_access
            SET status = 'closed',
                updated_at = NOW()
            WHERE company_id = :company_id
              AND table_key = :table_key
              AND status = 'active'
            """
        ),
        {"company_id": str(company_id), "table_key": _table_key(table_key)},
    )


@router.get("/companies/{company_id}/health")
async def hospitality_health(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")
    return {"ok": True, "company_id": str(company_id), "service": "clonexa-hospitality", "modules": ["orders", "qr", "day_closures", "loyalty"]}


@router.get("/companies/{company_id}/loyalty-campaigns/active")
async def get_active_loyalty_campaign(
    company_id: uuid.UUID,
    table: str | None = Query(default=None, max_length=120),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")
    campaign = await _active_loyalty_campaign(db, company_id, "consumption")
    return await _loyalty_response(db, company_id, campaign, table)


@router.post("/companies/{company_id}/loyalty-campaigns", status_code=status.HTTP_201_CREATED)
async def create_loyalty_campaign(
    company_id: uuid.UUID,
    payload: HospitalityLoyaltyCampaignIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    starts_at = _aware(payload.starts_at)
    ends_at = _aware(payload.ends_at)
    registration_ends_at = _aware(payload.registration_ends_at or payload.starts_at)
    if ends_at <= starts_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El cierre debe ser posterior al inicio.")
    if registration_ends_at >= ends_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La inscripcion debe cerrar antes de finalizar el torneo.")

    await db.execute(
        text(
            """
            UPDATE hospitality_loyalty_campaigns
            SET status = 'closed', updated_at = NOW()
            WHERE company_id = :company_id
              AND campaign_type = 'consumption'
              AND status = 'active'
            """
        ),
        {"company_id": str(company_id)},
    )
    result = await db.execute(
        text(
            """
            INSERT INTO hospitality_loyalty_campaigns (
                company_id, title, prize, description, campaign_type, registration_ends_at, starts_at, ends_at, status, created_at, updated_at
            )
            VALUES (
                :company_id, :title, :prize, :description, 'consumption', :registration_ends_at, :starts_at, :ends_at, 'active', NOW(), NOW()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "title": (_clean(payload.title) or "Reto de consumo")[:160],
            "prize": _clean(payload.prize)[:220],
            "description": _clean(payload.description)[:700],
            "registration_ends_at": registration_ends_at,
            "starts_at": starts_at,
            "ends_at": ends_at,
        },
    )
    await db.commit()
    campaign = dict(result.mappings().first())
    return await _loyalty_response(db, company_id, campaign)


@router.delete("/companies/{company_id}/loyalty-campaigns/{campaign_id}")
async def delete_loyalty_campaign(
    company_id: uuid.UUID,
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")
    await db.execute(
        text(
            """
            UPDATE hospitality_loyalty_campaigns
            SET status = 'closed',
                updated_at = NOW()
            WHERE id = :campaign_id
              AND company_id = :company_id
              AND status = 'active'
            """
        ),
        {"campaign_id": str(campaign_id), "company_id": str(company_id)},
    )
    await db.commit()
    return await _loyalty_response(db, company_id, None)


@router.post("/companies/{company_id}/loyalty-score-pools", status_code=status.HTTP_201_CREATED)
async def create_loyalty_score_pool(
    company_id: uuid.UUID,
    payload: HospitalityScorePoolCampaignIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    now = _now()
    ends_at = now + timedelta(days=30)
    await db.execute(
        text(
            """
            UPDATE hospitality_loyalty_campaigns
            SET status = 'closed', updated_at = NOW()
            WHERE company_id = :company_id
              AND campaign_type = 'score_pool'
              AND status = 'active'
            """
        ),
        {"company_id": str(company_id)},
    )
    result = await db.execute(
        text(
            """
            INSERT INTO hospitality_loyalty_campaigns (
                company_id, title, prize, description, campaign_type, team_a, team_b,
                registration_ends_at, starts_at, ends_at, status, created_at, updated_at
            )
            VALUES (
                :company_id, :title, :prize, :description, 'score_pool', :team_a, :team_b,
                :starts_at, :starts_at, :ends_at, 'active', NOW(), NOW()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "title": (_clean(payload.title) or "Polla de marcador")[:160],
            "prize": _clean(payload.prize)[:220],
            "description": _clean(payload.description)[:700],
            "team_a": _clean(payload.team_a)[:120],
            "team_b": _clean(payload.team_b)[:120],
            "starts_at": now,
            "ends_at": ends_at,
        },
    )
    await db.commit()
    return await _loyalty_response(db, company_id, None)


@router.post("/companies/{company_id}/loyalty-score-pools/{campaign_id}/predictions", status_code=status.HTTP_201_CREATED)
async def submit_loyalty_score_prediction(
    company_id: uuid.UUID,
    campaign_id: uuid.UUID,
    payload: HospitalityScorePredictionIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    campaign_result = await db.execute(
        text(
            """
            SELECT *
            FROM hospitality_loyalty_campaigns
            WHERE id = :campaign_id
              AND company_id = :company_id
              AND campaign_type = 'score_pool'
              AND status = 'active'
            LIMIT 1
            """
        ),
        {"campaign_id": str(campaign_id), "company_id": str(company_id)},
    )
    campaign = campaign_result.mappings().first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="polla_no_encontrada")

    table_number = _clean(payload.table) or "Mesa"
    await _require_table_access(db, company_id, table_number, payload.access_code)
    await db.execute(
        text(
            """
            INSERT INTO hospitality_loyalty_predictions (
                company_id, campaign_id, table_key, table_number, team_name, score_a, score_b, created_at, updated_at
            )
            VALUES (
                :company_id, :campaign_id, :table_key, :table_number, :team_name, :score_a, :score_b, NOW(), NOW()
            )
            ON CONFLICT (campaign_id, table_key)
            DO UPDATE SET
                table_number = EXCLUDED.table_number,
                team_name = EXCLUDED.team_name,
                score_a = EXCLUDED.score_a,
                score_b = EXCLUDED.score_b,
                updated_at = NOW()
            """
        ),
        {
            "company_id": str(company_id),
            "campaign_id": str(campaign_id),
            "table_key": _table_key(table_number),
            "table_number": table_number,
            "team_name": (_clean(payload.team_name) or table_number)[:160],
            "score_a": int(payload.score_a),
            "score_b": int(payload.score_b),
        },
    )
    await db.commit()
    active_campaign = await _active_loyalty_campaign(db, company_id, "consumption")
    return await _loyalty_response(db, company_id, active_campaign, table_number)


@router.post("/companies/{company_id}/loyalty-campaigns/{campaign_id}/participants", status_code=status.HTTP_201_CREATED)
async def join_loyalty_campaign(
    company_id: uuid.UUID,
    campaign_id: uuid.UUID,
    payload: HospitalityLoyaltyParticipantIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    campaign_result = await db.execute(
        text(
            """
            SELECT *
            FROM hospitality_loyalty_campaigns
            WHERE id = :campaign_id
              AND company_id = :company_id
              AND campaign_type = 'consumption'
              AND status = 'active'
            LIMIT 1
            """
        ),
        {"campaign_id": str(campaign_id), "company_id": str(company_id)},
    )
    campaign = campaign_result.mappings().first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sorteo_no_encontrado")

    campaign_data = dict(campaign)
    now = _now()
    registration_ends_at = _aware(campaign_data.get("registration_ends_at") or campaign_data["starts_at"])
    if now >= _aware(campaign_data["ends_at"]):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="torneo_finalizado")
    if now >= registration_ends_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="inscripcion_cerrada")

    table_number = _clean(payload.table) or "Mesa"
    team_name = _clean(payload.team_name) or table_number
    await db.execute(
        text(
            """
            INSERT INTO hospitality_loyalty_participants (
                company_id, campaign_id, table_key, table_number, team_name, accepted, created_at, updated_at
            )
            VALUES (
                :company_id, :campaign_id, :table_key, :table_number, :team_name, :accepted, NOW(), NOW()
            )
            ON CONFLICT (campaign_id, table_key)
            DO UPDATE SET
                table_number = EXCLUDED.table_number,
                team_name = EXCLUDED.team_name,
                accepted = EXCLUDED.accepted,
                updated_at = NOW()
            """
        ),
        {
            "company_id": str(company_id),
            "campaign_id": str(campaign_id),
            "table_key": _table_key(table_number),
            "table_number": table_number,
            "team_name": team_name[:160],
            "accepted": bool(payload.accepted),
        },
    )
    await db.commit()
    return await _loyalty_response(db, company_id, campaign_data, table_number)


@router.get("/companies/{company_id}/qr-tables/access")
async def get_hospitality_table_access(
    company_id: uuid.UUID,
    table: str = Query(default="Mesa", max_length=120),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")
    access = await _fetch_active_table_access(db, company_id, table)
    return {"ok": True, "company_id": str(company_id), "table": _clean(table), "access": _table_access_payload(access, include_code=False)}


@router.post("/companies/{company_id}/qr-tables/access", status_code=status.HTTP_201_CREATED)
async def activate_hospitality_table_access(
    company_id: uuid.UUID,
    payload: HospitalityTableAccessIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    table_number = _clean(payload.table) or "Mesa"
    table_key = _table_key(table_number)
    expires_at = _now() + timedelta(hours=int(payload.duration_hours or 12))
    code = _new_access_code()
    await db.execute(
        text(
            """
            UPDATE hospitality_table_access
            SET status = 'closed',
                updated_at = NOW()
            WHERE company_id = :company_id
              AND table_key = :table_key
              AND status = 'active'
            """
        ),
        {"company_id": str(company_id), "table_key": table_key},
    )
    result = await db.execute(
        text(
            """
            INSERT INTO hospitality_table_access (
                company_id, table_key, table_number, access_code, status, activated_at, expires_at, created_at, updated_at
            )
            VALUES (
                :company_id, :table_key, :table_number, :access_code, 'active', NOW(), :expires_at, NOW(), NOW()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "table_key": table_key,
            "table_number": table_number,
            "access_code": code,
            "expires_at": expires_at,
        },
    )
    await db.commit()
    access = result.mappings().first()
    return {"ok": True, "company_id": str(company_id), "table": table_number, "access": _table_access_payload(access, include_code=True)}


@router.post("/companies/{company_id}/qr-tables/access/verify")
async def verify_hospitality_table_access(
    company_id: uuid.UUID,
    payload: HospitalityTableAccessVerifyIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")
    table_number = _clean(payload.table) or "Mesa"
    await _require_table_access(db, company_id, table_number, payload.access_code)
    access = await _fetch_active_table_access(db, company_id, table_number)
    return {"ok": True, "company_id": str(company_id), "table": table_number, "access": _table_access_payload(access, include_code=False)}


@router.get("/companies/{company_id}/qr-tables")
async def hospitality_qr_tables(
    company_id: uuid.UUID,
    request: Request,
    count: int = Query(default=12, ge=1, le=500),
    include_bar: bool = Query(default=True),
    base_url: str | None = Query(default=None, max_length=260),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    rows = await db.execute(
        text(
            """
            SELECT table_key,
                   MIN(table_number) AS table_number,
                   COUNT(*) AS active_orders,
                   COALESCE(SUM(total), 0) AS open_total,
                   MAX(updated_at) AS last_activity
            FROM hospitality_orders
            WHERE company_id = :company_id
              AND archived_at IS NULL
              AND status IN ('pendiente', 'alistando', 'entregado')
            GROUP BY table_key
            """
        ),
        {"company_id": str(company_id)},
    )
    activity = {
        _table_key(row["table_key"]): {
            "table_number": row["table_number"] or "",
            "active_orders": int(row["active_orders"] or 0),
            "open_total": _money(row["open_total"]),
            "last_activity": _iso(row["last_activity"]),
        }
        for row in rows.mappings().all()
    }

    access_rows = await db.execute(
        text(
            """
            SELECT DISTINCT ON (table_key) *
            FROM hospitality_table_access
            WHERE company_id = :company_id
              AND status = 'active'
              AND expires_at > NOW()
            ORDER BY table_key, activated_at DESC
            """
        ),
        {"company_id": str(company_id)},
    )
    access_by_table = {
        _table_key(row["table_key"]): _table_access_payload(row, include_code=True)
        for row in access_rows.mappings().all()
    }

    base = _public_base_url(request, base_url)
    labels = (["Barra"] if include_bar else []) + [f"Mesa {index}" for index in range(1, count + 1)]
    tables: list[dict[str, Any]] = []
    for position, label in enumerate(labels, start=1):
        key = _table_key(label)
        order_url = f"{base}/ordenar?company_id={company_id}&mesa={quote(label)}"
        stats = activity.get(key, {})
        access = access_by_table.get(key) or _table_access_payload(None, include_code=True)
        tables.append(
            {
                "position": position,
                "label": label,
                "table_key": key,
                "order_url": order_url,
                "admin_url": f"{base}/client?company_id={company_id}",
                "active_orders": int(stats.get("active_orders") or 0),
                "open_total": _money(stats.get("open_total")),
                "last_activity": stats.get("last_activity") or "",
                "access_active": bool(access.get("active")),
                "access_code": access.get("access_code") or "",
                "access_expires_at": access.get("expires_at") or "",
            }
        )

    return {
        "ok": True,
        "company_id": str(company_id),
        "base_url": base,
        "tables": tables,
        "summary": {
            "qr_count": len(tables),
            "open_accounts": sum(int(row["active_orders"] or 0) for row in tables),
            "open_total": _money(sum(_num(row["open_total"]) for row in tables)),
        },
    }


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

    columns_result = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'inventory_items'
            """
        )
    )
    columns = {str(row["column_name"]) for row in columns_result.mappings().all()}
    price_columns = [name for name in ("unit_value", "unit_price", "sale_price", "price", "valor_unitario") if name in columns]
    price_expr = "COALESCE(" + ", ".join(price_columns + ["0"]) + ")" if price_columns else "0"

    result = await db.execute(
        text(
            f"""
            SELECT id, sku, name, reference, name_reference, current_stock, status,
                   {price_expr} AS unit_price
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
            "price": _money(row["unit_price"]),
            "unit_price": _money(row["unit_price"]),
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
    include_archived: bool = Query(default=False),
    limit: int = Query(default=180, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    where = ["company_id = :company_id"]
    params: dict[str, Any] = {"company_id": str(company_id), "limit": limit}
    if not include_archived:
        where.append("archived_at IS NULL")
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
        "include_archived": include_archived,
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


@router.get("/companies/{company_id}/day-closures")
async def list_hospitality_day_closures(
    company_id: uuid.UUID,
    limit: int = Query(default=40, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    result = await db.execute(
        text(
            """
            SELECT *
            FROM hospitality_day_closures
            WHERE company_id = :company_id
            ORDER BY closed_at DESC
            LIMIT :limit
            """
        ),
        {"company_id": str(company_id), "limit": limit},
    )
    closures = [_closure_payload(row) for row in result.mappings().all()]
    return {"ok": True, "company_id": str(company_id), "closures": closures}


@router.post("/companies/{company_id}/day-closures", status_code=status.HTTP_201_CREATED)
async def create_hospitality_day_closure(
    company_id: uuid.UUID,
    payload: HospitalityClosureCreateIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")
    closure = await _create_day_closure(db, company_id, payload)
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "closure": closure}


@router.post("/companies/{company_id}/orders", status_code=status.HTTP_201_CREATED)
async def create_hospitality_order(
    company_id: uuid.UUID,
    payload: HospitalityOrderCreateIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    table_number = _clean(payload.table) or "Barra"
    customer_name = _clean(payload.customer) or "Cliente barra"
    source = _clean(payload.source) or "client"
    if _norm(source) == "qr":
        await _require_table_access(db, company_id, table_number, payload.access_code)

    items = await _build_order_items(db, company_id, payload.items)
    total = _money(sum(_num(item.get("subtotal")) for item in items))
    payment_method = _payment_method(payload.payment_method)
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
                company_id, order_number, table_number, table_key, order_type, source, payment_method,
                status, customer_name, people, items, songs, notes, total, metadata,
                created_at, updated_at
            )
            VALUES (
                :company_id, :order_number, :table_number, :table_key, :order_type, :source, :payment_method,
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
            "payment_method": payment_method,
            "customer_name": customer_name,
            "people": json.dumps([person], ensure_ascii=False),
            "items": json.dumps(items, ensure_ascii=False),
            "songs": json.dumps(_songs(payload.songs), ensure_ascii=False),
            "notes": _clean(payload.notes),
            "total": total,
            "metadata": json.dumps({"source_product": "bar-bot-completo.zip", "payment_label": PAYMENT_LABELS.get(payment_method, "Otro")}, ensure_ascii=False),
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

    params = {"order_id": str(order_id), "company_id": str(company_id)}
    if next_status == STATUS_PREPARING:
        await db.execute(
            text(
                """
                UPDATE hospitality_orders
                SET status = 'alistando',
                    preparing_at = COALESCE(preparing_at, NOW()),
                    updated_at = NOW()
                WHERE id = :order_id
                  AND company_id = :company_id
                """
            ),
            params,
        )
    elif next_status == STATUS_SERVED:
        await db.execute(
            text(
                """
                UPDATE hospitality_orders
                SET status = 'entregado',
                    inventory_deducted = TRUE,
                    served_at = COALESCE(served_at, NOW()),
                    updated_at = NOW()
                WHERE id = :order_id
                  AND company_id = :company_id
                """
            ),
            params,
        )
    elif next_status == STATUS_CLOSED:
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
            params,
        )
    if next_status == STATUS_CLOSED:
        await _close_table_access_if_idle(db, company_id, order.get("table_key") or order.get("table_number") or "")
    await db.commit()
    saved = await _fetch_order(db, company_id, order_id)
    return {"ok": True, "order": saved, "table": saved}


@router.post("/companies/{company_id}/orders/{order_id}/close-table")
async def close_hospitality_order(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: HospitalityCloseIn | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    order = await _fetch_order(db, company_id, order_id)
    if _status(order.get("status")) != STATUS_SERVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="solo_se_puede_cerrar_mesa_entregada")

    raw_payment_method = payload.payment_method if payload and _clean(payload.payment_method) else order.get("payment_method")
    payment_method = _payment_method(raw_payment_method)
    await db.execute(
        text(
            """
            UPDATE hospitality_orders
            SET status = 'cerrado',
                payment_method = :payment_method,
                closed_at = COALESCE(closed_at, NOW()),
                updated_at = NOW()
            WHERE id = :order_id
              AND company_id = :company_id
            """
        ),
        {"order_id": str(order_id), "company_id": str(company_id), "payment_method": payment_method},
    )
    await _close_table_access_if_idle(db, company_id, order.get("table_key") or order.get("table_number") or "")
    await db.commit()
    saved = await _fetch_order(db, company_id, order_id)
    return {"ok": True, "order": saved, "table": saved}
