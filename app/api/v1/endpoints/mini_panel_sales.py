from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

try:
    from app.services.auth_service import decode_access_token
except Exception:  # pragma: no cover
    decode_access_token = None


router = APIRouter()

PANEL_ALIASES = {
    "venta": "sales",
    "ventas": "sales",
    "sales": "sales",
    "store": "stores",
    "stores": "stores",
    "tienda": "stores",
    "tiendas": "stores",
    "inventory": "inventory",
    "inventario": "inventory",
    "logistics": "logistics",
    "logistica": "logistics",
    "field": "logistics",
    "other": "other",
}

OCCUPATION_DEFAULTS: dict[str, list[dict[str, str]]] = {
    "technology": [
        {"category": "Celulares", "image_key": "phone", "icon": "📱"},
        {"category": "Accesorios celular", "image_key": "accessories", "icon": "🧩"},
        {"category": "Audífonos / relojes", "image_key": "wearables", "icon": "🎧"},
        {"category": "Cables", "image_key": "cables", "icon": "🔌"},
        {"category": "Memorias", "image_key": "memory", "icon": "💾"},
        {"category": "Otros", "image_key": "other", "icon": "✨"},
    ],
    "ropa": [
        {"category": "Ropa hombre", "image_key": "men", "icon": "👕"},
        {"category": "Ropa mujer", "image_key": "women", "icon": "👗"},
        {"category": "Camisetas", "image_key": "shirts", "icon": "👚"},
        {"category": "Pantalones", "image_key": "pants", "icon": "👖"},
        {"category": "Chaquetas", "image_key": "jackets", "icon": "🧥"},
        {"category": "Accesorios", "image_key": "fashion_accessories", "icon": "👜"},
    ],
    "accesorios": [
        {"category": "Accesorios", "image_key": "accessories", "icon": "🧩"},
        {"category": "Complementos", "image_key": "addons", "icon": "➕"},
        {"category": "Otros", "image_key": "other", "icon": "✨"},
    ],
    "servicios": [
        {"category": "Servicios", "image_key": "services", "icon": "🛠️"},
        {"category": "Planes", "image_key": "plans", "icon": "📋"},
        {"category": "Otros", "image_key": "other", "icon": "✨"},
    ],
    "custom": [
        {"category": "Principal", "image_key": "main", "icon": "⭐"},
        {"category": "Otros", "image_key": "other", "icon": "✨"},
    ],
}


class SalesConfigIn(BaseModel):
    occupation: str | None = Field(default="technology", max_length=80)
    custom_categories: list[str] | None = Field(default=None)


class SaleItemIn(BaseModel):
    reference_id: str | None = Field(default=None, max_length=120)
    reference_name: str = Field(..., min_length=1, max_length=220)
    reference_category: str | None = Field(default=None, max_length=160)
    reference_size: str | None = Field(default=None, max_length=120)
    reference_color: str | None = Field(default=None, max_length=120)
    quantity: float = Field(default=1, ge=0)
    unit_price: float = Field(default=0, ge=0)
    barcode: str | None = Field(default=None, max_length=180)


class SaleCreateIn(BaseModel):
    reference_id: str | None = Field(default=None, max_length=120)
    reference_name: str | None = Field(default=None, max_length=220)
    reference_category: str | None = Field(default=None, max_length=160)
    reference_size: str | None = Field(default=None, max_length=120)
    reference_color: str | None = Field(default=None, max_length=120)
    quantity: float = Field(default=1, ge=0)
    unit_price: float = Field(default=0, ge=0)
    payment_method: str | None = Field(default="efectivo", max_length=60)
    notes: str | None = Field(default=None, max_length=1000)
    items: list[SaleItemIn] | None = Field(default=None)
    adjustment_type: str | None = Field(default="none", max_length=40)
    adjustment_percent: float = Field(default=0, ge=0, le=20)
    subtotal: float | None = Field(default=None, ge=0)
    adjustment_amount: float | None = Field(default=None, ge=0)
    total_payable: float | None = Field(default=None, ge=0)

    @field_validator("payment_method")
    @classmethod
    def clean_payment_method(cls, value: str | None) -> str:
        raw = _norm(value or "efectivo")
        return raw if raw in {"efectivo", "transferencia", "cheque", "tarjeta", "otro"} else "otro"



class SalePreparedIn(BaseModel):
    prepared: bool = True


class SaleAttachmentIn(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=260)
    file_type: str | None = Field(default="application/octet-stream", max_length=160)
    file_data: str = Field(..., min_length=1, max_length=6000000)


class SaleGuideIn(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=260)
    file_type: str | None = Field(default="application/octet-stream", max_length=160)
    file_data: str = Field(..., min_length=1, max_length=6000000)


class SalesCutConfigIn(BaseModel):
    period_type: str = Field(default="weekly", max_length=40)

    @field_validator("period_type")
    @classmethod
    def clean_period_type(cls, value: str | None) -> str:
        raw = _norm(value or "weekly")
        aliases = {
            "semanal": "weekly",
            "week": "weekly",
            "weekly": "weekly",
            "quincenal": "biweekly",
            "biweekly": "biweekly",
            "15_dias": "biweekly",
            "15dias": "biweekly",
            "mensual": "monthly",
            "month": "monthly",
            "monthly": "monthly",
        }
        return aliases.get(raw, "weekly")


class SalesCutGenerateIn(BaseModel):
    period_type: str = Field(default="weekly", max_length=40)

    @field_validator("period_type")
    @classmethod
    def clean_period_type(cls, value: str | None) -> str:
        return SalesCutConfigIn.clean_period_type(value)


def _database_url() -> str:
    raw = (
        os.getenv("DATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DB_URL")
        or ""
    ).strip()

    if raw:
        raw = raw.replace("postgresql+asyncpg://", "postgresql://")
        raw = raw.replace("postgres+asyncpg://", "postgresql://")
        if raw.startswith("postgres://"):
            raw = "postgresql://" + raw[len("postgres://") :]
        return raw

    host = os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST") or "db"
    port = os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT") or "5432"
    user = os.getenv("POSTGRES_USER") or os.getenv("DB_USER") or "clonexa"
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD") or "clonexa"
    database = os.getenv("POSTGRES_DB") or os.getenv("DB_NAME") or "clonexa"
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def _connect() -> asyncpg.Connection:
    try:
        return await asyncpg.connect(_database_url())
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No fue posible conectar a PostgreSQL: {exc}",
        )


def _norm(value: Any) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    out: list[str] = []
    last_sep = False
    for ch in text:
        if ch.isalnum():
            out.append(ch)
            last_sep = False
        elif not last_sep:
            out.append("_")
            last_sep = True
    return "".join(out).strip("_")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _panel(value: Any) -> str:
    normalized = _norm(value or "sales")
    return PANEL_ALIASES.get(normalized, normalized or "sales")


def _money(value: Any) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except Exception:
        return 0.0


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _extract_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if raw.lower().startswith("bearer "):
        return raw.split(" ", 1)[1].strip()
    return raw


async def _ensure_storage(conn: asyncpg.Connection) -> None:
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    ref_table = await conn.fetchval("SELECT to_regclass('public.product_references')")
    if ref_table:
        await conn.execute("ALTER TABLE product_references ADD COLUMN IF NOT EXISTS sku text NOT NULL DEFAULT '';")
        await conn.execute("ALTER TABLE product_references ADD COLUMN IF NOT EXISTS unit_price numeric(14, 2) NOT NULL DEFAULT 0;")
        await conn.execute("ALTER TABLE product_references ADD COLUMN IF NOT EXISTS archived boolean NOT NULL DEFAULT false;")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_panel_sales_settings (
            company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            occupation VARCHAR(80) NOT NULL DEFAULT 'technology',
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_panel_sales_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            panel_type VARCHAR(50) NOT NULL DEFAULT 'sales',
            reference_id TEXT NULL,
            reference_name VARCHAR(220) NOT NULL,
            reference_category VARCHAR(160),
            reference_size VARCHAR(120),
            reference_color VARCHAR(120),
            quantity NUMERIC(14, 2) NOT NULL DEFAULT 0,
            unit_price NUMERIC(14, 2) NOT NULL DEFAULT 0,
            total NUMERIC(14, 2) NOT NULL DEFAULT 0,
            payment_method VARCHAR(60) NOT NULL DEFAULT 'efectivo',
            notes TEXT,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            created_by UUID NULL,
            created_by_label VARCHAR(180),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS is_prepared BOOLEAN NOT NULL DEFAULT FALSE;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS prepared_at TIMESTAMPTZ NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS prepared_by UUID NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS support_file_name TEXT NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS support_file_type TEXT NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS support_file_data TEXT NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS support_uploaded_at TIMESTAMPTZ NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS support_uploaded_by UUID NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS guide_file_name TEXT NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS guide_file_type TEXT NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS guide_file_data TEXT NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS guide_uploaded_at TIMESTAMPTZ NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS guide_uploaded_by UUID NULL;
        """
    )
    await conn.execute(
        """
        ALTER TABLE mini_panel_sales_records
        ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL;
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_sales_company_prepared
        ON mini_panel_sales_records (company_id, is_prepared, created_at DESC);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_sales_company_archived
        ON mini_panel_sales_records (company_id, archived_at DESC);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_sales_company_panel_user
        ON mini_panel_sales_records (company_id, panel_type, created_by, created_at DESC);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_sales_company_category
        ON mini_panel_sales_records (company_id, lower(reference_category), created_at DESC);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_sales_company_status
        ON mini_panel_sales_records (company_id, status, created_at DESC);
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_panel_sales_cuts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            panel_type VARCHAR(50) NOT NULL DEFAULT 'sales',
            period_type VARCHAR(40) NOT NULL DEFAULT 'weekly',
            period_start TIMESTAMPTZ NOT NULL,
            period_end TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            active_count INTEGER NOT NULL DEFAULT 0,
            top_seller_label VARCHAR(180),
            top_seller_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            top_store_label VARCHAR(180),
            top_store_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            generated_by UUID NULL,
            generated_by_label VARCHAR(180),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_sales_cuts_company_panel
        ON mini_panel_sales_cuts (company_id, panel_type, period_end DESC);
        """
    )


async def _company_exists(conn: asyncpg.Connection, company_id: uuid.UUID) -> bool:
    row = await conn.fetchrow("SELECT id FROM companies WHERE id = $1::uuid LIMIT 1", company_id)
    return bool(row)


async def _require_access(conn: asyncpg.Connection, company_id: uuid.UUID, authorization: str | None) -> dict[str, Any]:
    if not str(authorization or "").strip():
        if await _company_exists(conn, company_id):
            return {
                "company_id": str(company_id),
                "user_id": None,
                "full_name": "Panel principal",
                "email": None,
                "source": "client_universal",
                "mini_panel": False,
            }

    if decode_access_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Servicio de autenticacion no disponible.")

    token = _extract_token(authorization)
    payload = decode_access_token(token)

    raw_company = payload.get("company_id") or payload.get("tenant_id") or payload.get("company")
    if raw_company and str(raw_company) != str(company_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso no autorizado para esta empresa.")

    raw_user_id = payload.get("user_id") or payload.get("sub") or payload.get("id")
    if not raw_user_id:
        return {**payload, "company_id": str(company_id)}

    try:
        user_uuid = uuid.UUID(str(raw_user_id))
    except Exception:
        user_uuid = None

    if not user_uuid:
        return {**payload, "company_id": str(company_id)}

    row = await conn.fetchrow(
        """
        SELECT id, company_id, status, full_name, email
        FROM company_users
        WHERE id = $1::uuid
          AND company_id = $2::uuid
        LIMIT 1
        """,
        user_uuid,
        company_id,
    )

    if row and str(row["status"]).lower() == "active":
        return {
            **payload,
            "company_id": str(row["company_id"]),
            "user_id": str(row["id"]),
            "full_name": row["full_name"] or payload.get("full_name") or "",
            "email": row["email"] or payload.get("email") or "",
            "mini_panel": bool(payload.get("mini_panel") is True or payload.get("panel_type")),
        }

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso no autorizado para esta empresa.")


def _scope_user_id(access: dict[str, Any] | None) -> uuid.UUID | None:
    if not isinstance(access, dict):
        return None
    if str(access.get("source") or "") == "client_universal":
        return None
    if access.get("mini_panel") is not True:
        return None
    raw = access.get("user_id") or access.get("sub") or access.get("id")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except Exception:
        return None


def _scope_label(access: dict[str, Any] | None) -> str:
    if not isinstance(access, dict):
        return ""
    return _clean(access.get("full_name") or access.get("email") or "Usuario mini panel")


def _occupation(value: Any) -> str:
    normalized = _norm(value or "technology")
    if normalized in {"tecnologia", "technology", "tech"}:
        return "technology"
    if normalized in {"ropa", "moda", "clothing", "fashion"}:
        return "ropa"
    if normalized in {"accesorio", "accesorios", "accessories"}:
        return "accesorios"
    if normalized in {"servicio", "servicios", "services"}:
        return "servicios"
    return "custom"


def _category_icon(category: str) -> str:
    normalized = _norm(category)
    if "celular" in normalized or "telefono" in normalized or "phone" in normalized:
        return "📱"
    if "audifono" in normalized or "reloj" in normalized or "watch" in normalized:
        return "🎧"
    if "cable" in normalized:
        return "🔌"
    if "memoria" in normalized:
        return "💾"
    if "hombre" in normalized:
        return "👕"
    if "mujer" in normalized:
        return "👗"
    if "camiseta" in normalized:
        return "👚"
    if "pantalon" in normalized:
        return "👖"
    if "chaqueta" in normalized:
        return "🧥"
    if "servicio" in normalized:
        return "🛠️"
    return "✨"


async def _settings(conn: asyncpg.Connection, company_id: uuid.UUID) -> dict[str, Any]:
    await _ensure_storage(conn)
    row = await conn.fetchrow(
        """
        SELECT occupation, settings
        FROM mini_panel_sales_settings
        WHERE company_id = $1::uuid
        LIMIT 1
        """,
        company_id,
    )
    if not row:
        return {"occupation": "technology", "settings": {}, "custom_categories": []}
    settings = _json(row["settings"], {})
    return {
        "occupation": _occupation(row["occupation"]),
        "settings": settings if isinstance(settings, dict) else {},
        "custom_categories": settings.get("custom_categories") if isinstance(settings, dict) and isinstance(settings.get("custom_categories"), list) else [],
    }


def _cut_period(value: Any) -> str:
    raw = _norm(value or "weekly")
    aliases = {
        "semanal": "weekly",
        "week": "weekly",
        "weekly": "weekly",
        "quincenal": "biweekly",
        "biweekly": "biweekly",
        "15_dias": "biweekly",
        "15dias": "biweekly",
        "mensual": "monthly",
        "month": "monthly",
        "monthly": "monthly",
    }
    return aliases.get(raw, "weekly")


def _cut_period_label(value: Any) -> str:
    labels = {"weekly": "Semanal", "biweekly": "Quincenal", "monthly": "Mensual"}
    return labels.get(_cut_period(value), "Semanal")


def _parse_dt(value: Any) -> datetime | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


async def _sales_cut_config(conn: asyncpg.Connection, company_id: uuid.UUID) -> dict[str, Any]:
    config = await _settings(conn, company_id)
    settings = config.get("settings") if isinstance(config.get("settings"), dict) else {}
    raw_cut = settings.get("sales_cut") if isinstance(settings, dict) else {}
    cut = raw_cut if isinstance(raw_cut, dict) else {}
    period_type = _cut_period(cut.get("period_type") or settings.get("sales_cut_period") or "weekly")
    started_at = _clean(cut.get("started_at") or settings.get("sales_cut_started_at") or "")
    started_dt = _parse_dt(started_at)
    return {
        "period_type": period_type,
        "period_label": _cut_period_label(period_type),
        "started_at": started_dt.isoformat() if started_dt else None,
        "started_at_dt": started_dt,
        "last_cut_id": _clean(cut.get("last_cut_id") or ""),
        "last_generated_at": _clean(cut.get("last_generated_at") or ""),
        "settings": settings,
        "occupation": config.get("occupation") or "technology",
    }


async def _save_sales_cut_config(
    conn: asyncpg.Connection,
    company_id: uuid.UUID,
    period_type: str,
    started_at: datetime | None = None,
    last_cut_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    current = await _settings(conn, company_id)
    settings = current.get("settings") if isinstance(current.get("settings"), dict) else {}
    settings = dict(settings)
    existing_cut = settings.get("sales_cut") if isinstance(settings.get("sales_cut"), dict) else {}
    cut = dict(existing_cut)
    cut["period_type"] = _cut_period(period_type)
    if started_at is not None:
        cut["started_at"] = started_at.isoformat()
        cut["last_generated_at"] = started_at.isoformat()
    if last_cut_id is not None:
        cut["last_cut_id"] = str(last_cut_id)
    settings["sales_cut"] = cut

    await conn.execute(
        """
        INSERT INTO mini_panel_sales_settings (company_id, occupation, settings, created_at, updated_at)
        VALUES ($1::uuid, $2, $3::jsonb, NOW(), NOW())
        ON CONFLICT (company_id) DO UPDATE
        SET settings = EXCLUDED.settings,
            updated_at = NOW()
        """,
        company_id,
        _occupation(current.get("occupation") or "technology"),
        json.dumps(settings, ensure_ascii=False),
    )
    return await _sales_cut_config(conn, company_id)


def _cut_sql_parts(cut_config: dict[str, Any], idx: int) -> tuple[list[str], list[Any], int]:
    started = cut_config.get("started_at_dt") if isinstance(cut_config, dict) else None
    if started:
        return [f"s.created_at >= ${idx}::timestamptz"], [started], idx + 1
    return [], [], idx


async def _sales_cut_summary(
    conn: asyncpg.Connection,
    company_id: uuid.UUID,
    panel_type: str = "all",
    scope_user_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> dict[str, Any]:
    panel = _panel(panel_type)
    cut_config = await _sales_cut_config(conn, company_id)

    where = ["s.company_id = $1::uuid"]
    args: list[Any] = [company_id]
    idx = 2

    if panel not in {"all", "client"}:
        where.append(f"s.panel_type = ${idx}")
        args.append(panel)
        idx += 1

    if not include_archived:
        where.append("s.status <> 'archived'")

    if scope_user_id:
        where.append(f"s.created_by = ${idx}::uuid")
        args.append(scope_user_id)
        idx += 1

    cut_where, cut_args, idx = _cut_sql_parts(cut_config, idx)
    where.extend(cut_where)
    args.extend(cut_args)

    where_sql = " AND ".join(where)

    totals = await conn.fetchrow(
        f"""
        SELECT COALESCE(SUM(s.total), 0) AS total_amount,
               COUNT(*) AS active_count,
               MIN(s.created_at) AS first_sale_at,
               MAX(s.created_at) AS last_sale_at
        FROM mini_panel_sales_records s
        WHERE {where_sql}
        """,
        *args,
    )

    top_seller = await conn.fetchrow(
        f"""
        SELECT COALESCE(NULLIF(s.created_by_label, ''), 'Usuario mini panel') AS label,
               COALESCE(SUM(s.total), 0) AS amount,
               COUNT(*) AS count
        FROM mini_panel_sales_records s
        WHERE {where_sql}
        GROUP BY COALESCE(NULLIF(s.created_by_label, ''), 'Usuario mini panel')
        ORDER BY amount DESC, count DESC, label ASC
        LIMIT 1
        """,
        *args,
    )

    store_where = where + ["s.panel_type IN ('stores', 'store', 'tiendas')"]
    store_sql = " AND ".join(store_where)
    top_store = await conn.fetchrow(
        f"""
        SELECT COALESCE(NULLIF(s.created_by_label, ''), 'Tienda') AS label,
               COALESCE(SUM(s.total), 0) AS amount,
               COUNT(*) AS count
        FROM mini_panel_sales_records s
        WHERE {store_sql}
        GROUP BY COALESCE(NULLIF(s.created_by_label, ''), 'Tienda')
        ORDER BY amount DESC, count DESC, label ASC
        LIMIT 1
        """,
        *args,
    )

    period_start = cut_config.get("started_at") or _iso(totals["first_sale_at"] if totals else None)
    period_end = datetime.now(timezone.utc).isoformat()

    return {
        "company_id": str(company_id),
        "panel_type": panel,
        "period_type": cut_config.get("period_type") or "weekly",
        "period_label": cut_config.get("period_label") or "Semanal",
        "period_started_at": period_start,
        "period_ends_at": period_end,
        "active_count": int(totals["active_count"] or 0) if totals else 0,
        "total_amount": round(_money(totals["total_amount"] if totals else 0), 2),
        "top_seller": {
            "label": _clean(top_seller["label"] if top_seller else "Sin ventas"),
            "amount": round(_money(top_seller["amount"] if top_seller else 0), 2),
            "count": int(top_seller["count"] or 0) if top_seller else 0,
        },
        "top_store": {
            "label": _clean(top_store["label"] if top_store else "Próximamente"),
            "amount": round(_money(top_store["amount"] if top_store else 0), 2),
            "count": int(top_store["count"] or 0) if top_store else 0,
            "status": "connected" if top_store else "pending",
        },
        "last_sale_at": _iso(totals["last_sale_at"] if totals else None),
    }


async def _reference_categories(conn: asyncpg.Connection, company_id: uuid.UUID) -> list[dict[str, Any]]:
    table = await conn.fetchval("SELECT to_regclass('public.product_references')")
    if not table:
        return []

    rows = await conn.fetch(
        """
        SELECT
            COALESCE(NULLIF(category, ''), 'Otros') AS category,
            COUNT(*) AS total
        FROM product_references
        WHERE company_id = $1::text
          AND COALESCE(archived, false) IS NOT TRUE
          AND (
            COALESCE(system_active, false) IS TRUE
            OR COALESCE(channel, '') IN ('system', 'both')
          )
        GROUP BY COALESCE(NULLIF(category, ''), 'Otros')
        ORDER BY total DESC, category ASC
        """,
        str(company_id),
    )

    return [
        {
            "category": _clean(row["category"]),
            "slug": _norm(row["category"]),
            "count": int(row["total"] or 0),
            "icon": _category_icon(row["category"]),
            "source": "references",
        }
        for row in rows
    ]


def _fallback_categories(occupation: str, custom_categories: list[Any] | None = None) -> list[dict[str, Any]]:
    custom = [_clean(item) for item in (custom_categories or []) if _clean(item)]
    if custom:
        return [
            {
                "category": item,
                "slug": _norm(item),
                "count": 0,
                "icon": _category_icon(item),
                "source": "custom",
            }
            for item in custom
        ]

    rows = OCCUPATION_DEFAULTS.get(_occupation(occupation), OCCUPATION_DEFAULTS["custom"])
    return [
        {
            "category": row["category"],
            "slug": _norm(row["category"]),
            "count": 0,
            "icon": row["icon"],
            "image_key": row["image_key"],
            "source": "default",
        }
        for row in rows
    ]


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        if hasattr(row, "keys") and key in row.keys():
            value = row[key]
            return value if value is not None else default
    except Exception:
        pass
    try:
        value = row[key]
        return value if value is not None else default
    except Exception:
        return default


def _panel_label(value: Any) -> str:
    panel = _panel(value)
    labels = {
        "sales": "Mini Panel Ventas",
        "stores": "Mini Panel Tiendas",
        "inventory": "Mini Panel Inventario",
        "logistics": "Mini Panel Logística",
        "other": "Mini Panel Otro",
    }
    return labels.get(panel, f"Mini Panel {str(panel).title()}")


def _iso(value: Any) -> str | None:
    try:
        return value.isoformat() if value else None
    except Exception:
        return None


def _sale_item_payload(raw: Any, fallback_category: str = "") -> dict[str, Any] | None:
    if raw is None:
        return None

    if hasattr(raw, "model_dump"):
        data = raw.model_dump()
    elif isinstance(raw, dict):
        data = raw
    else:
        data = {}

    name = _clean(data.get("reference_name") or data.get("name"))
    if not name:
        return None

    quantity = max(0.0, _money(data.get("quantity", 1)))
    unit_price = max(0.0, _money(data.get("unit_price", 0)))
    total = round(quantity * unit_price, 2)

    return {
        "reference_id": _clean(data.get("reference_id") or data.get("id")),
        "reference_name": name,
        "reference_category": _clean(data.get("reference_category") or data.get("category") or fallback_category),
        "reference_size": _clean(data.get("reference_size") or data.get("size")),
        "reference_color": _clean(data.get("reference_color") or data.get("color")),
        "quantity": quantity,
        "unit_price": unit_price,
        "total": total,
        "barcode": _clean(data.get("barcode") or data.get("code") or data.get("sku")),
    }


def _sale_items_from_payload(payload: SaleCreateIn) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if payload.items:
        for item in payload.items:
            normalized = _sale_item_payload(item, _clean(payload.reference_category))
            if normalized:
                rows.append(normalized)

    if rows:
        return rows

    fallback = _sale_item_payload(
        {
            "reference_id": payload.reference_id,
            "reference_name": payload.reference_name,
            "reference_category": payload.reference_category,
            "reference_size": payload.reference_size,
            "reference_color": payload.reference_color,
            "quantity": payload.quantity,
            "unit_price": payload.unit_price,
        }
    )
    return [fallback] if fallback else []


def _sale_items_from_metadata(row: Any) -> list[dict[str, Any]]:
    metadata = _json(_row_value(row, "metadata", {}), {})
    raw_items = metadata.get("items") if isinstance(metadata, dict) else None

    if isinstance(raw_items, list) and raw_items:
        items = []
        for item in raw_items:
            normalized = _sale_item_payload(item)
            if normalized:
                items.append(normalized)
        if items:
            return items

    return [
        {
            "reference_id": _clean(_row_value(row, "reference_id", "")),
            "reference_name": _clean(_row_value(row, "reference_name", "Venta")),
            "reference_category": _clean(_row_value(row, "reference_category", "")),
            "reference_size": _clean(_row_value(row, "reference_size", "")),
            "reference_color": _clean(_row_value(row, "reference_color", "")),
            "quantity": _money(_row_value(row, "quantity", 0)),
            "unit_price": _money(_row_value(row, "unit_price", 0)),
            "total": _money(_row_value(row, "total", 0)),
            "barcode": "",
        }
    ]



def _adjustment_label(adjustment_type: str) -> str:
    labels = {
        "none": "Sin ajuste",
        "discount": "Descuento",
        "retention": "Retención",
        "iva": "IVA incluido",
        "tax": "Impuesto incluido",
    }
    return labels.get(adjustment_type, "Sin ajuste")


def _adjustment_meta_from_payload(payload: SaleCreateIn, items: list[dict[str, Any]]) -> dict[str, Any]:
    subtotal = round(sum(_money(item.get("total")) for item in items), 2)
    raw_type = _norm(getattr(payload, "adjustment_type", "none") or "none")
    aliases = {
        "ninguno": "none",
        "none": "none",
        "sin_ajuste": "none",
        "descuento": "discount",
        "discount": "discount",
        "retencion": "retention",
        "retention": "retention",
        "iva": "iva",
        "impuesto": "tax",
        "tax": "tax",
    }
    adjustment_type = aliases.get(raw_type, "none")

    try:
        percent = float(getattr(payload, "adjustment_percent", 0) or 0)
    except Exception:
        percent = 0

    if adjustment_type == "none":
        percent = 0
    else:
        percent = min(20.0, max(1.0, percent))

    base_amount = subtotal
    adjustment_amount = 0.0
    total_payable = subtotal
    mode = "none"

    if adjustment_type in {"discount", "retention"}:
        mode = "subtract"
        adjustment_amount = round(subtotal * percent / 100, 2)
        total_payable = round(max(0.0, subtotal - adjustment_amount), 2)
    elif adjustment_type in {"iva", "tax"}:
        mode = "included"
        divisor = 1 + (percent / 100)
        base_amount = round(subtotal / divisor, 2) if divisor else subtotal
        adjustment_amount = round(subtotal - base_amount, 2)
        total_payable = subtotal

    return {
        "type": adjustment_type,
        "label": _adjustment_label(adjustment_type),
        "percent": percent,
        "subtotal": subtotal,
        "base_amount": base_amount,
        "adjustment_amount": adjustment_amount,
        "total_payable": total_payable,
        "mode": mode,
    }


def _file_payload(row: Any, prefix: str) -> dict[str, Any] | None:
    name = _clean(_row_value(row, f"{prefix}_file_name", ""))
    data = _clean(_row_value(row, f"{prefix}_file_data", ""))
    if not name and not data:
        return None
    return {
        "file_name": name,
        "file_type": _clean(_row_value(row, f"{prefix}_file_type", "")) or "application/octet-stream",
        "file_data": data,
        "uploaded_at": _iso(_row_value(row, f"{prefix}_uploaded_at")),
        "uploaded_by": str(_row_value(row, f"{prefix}_uploaded_by")) if _row_value(row, f"{prefix}_uploaded_by") else None,
    }


def _pipeline_status(row: Any) -> str:
    status_value = _clean(_row_value(row, "status", "active")).lower() or "active"
    if status_value == "archived":
        return "archived"
    if _file_payload(row, "guide"):
        return "guide_attached"
    if _file_payload(row, "support"):
        return "support_attached"
    if bool(_row_value(row, "is_prepared", False)):
        return "prepared"
    return status_value


def _sale_payload(row: asyncpg.Record) -> dict[str, Any]:
    metadata = _json(row["metadata"], {})
    if not isinstance(metadata, dict):
        metadata = {}

    items = _sale_items_from_metadata(row)
    subtotal = round(sum(_money(item.get("total")) for item in items), 2)
    raw_adjustment = metadata.get("adjustment") if isinstance(metadata, dict) else None
    adjustment = raw_adjustment if isinstance(raw_adjustment, dict) else {
        "type": "none",
        "label": "Sin ajuste",
        "percent": 0,
        "subtotal": subtotal,
        "base_amount": subtotal,
        "adjustment_amount": 0,
        "total_payable": _money(row["total"]) or subtotal,
        "mode": "none",
    }
    total = round(_money(adjustment.get("total_payable")) or _money(row["total"]) or subtotal, 2)
    quantity = round(sum(_money(item.get("quantity")) for item in items), 2)
    unit_price = _money(row["unit_price"])
    created_by_label = _clean(_row_value(row, "creator_display_label", "")) or _clean(_row_value(row, "created_by_label", ""))
    support = _file_payload(row, "support")
    guide = _file_payload(row, "guide")

    invoice_number = _clean(metadata.get("invoice_number") or "")
    if not invoice_number:
        invoice_number = f"FV-{str(row['id'])[:8].upper()}"

    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "panel_type": row["panel_type"],
        "reference_id": row["reference_id"],
        "reference_name": row["reference_name"],
        "reference_category": row["reference_category"] or "",
        "reference_size": row["reference_size"] or "",
        "reference_color": row["reference_color"] or "",
        "quantity": quantity,
        "unit_price": unit_price,
        "total": total,
        # CLONEXA_022K_R2_SAVE_SALES_ADJUSTMENT_SAFE: expose invoice adjustment persisted in metadata.
        "subtotal": round(_money(adjustment.get("subtotal")) or subtotal, 2),
        "adjustment": adjustment,
        "adjustment_type": _clean(adjustment.get("type") or "none"),
        "adjustment_label": _clean(adjustment.get("label") or _adjustment_label(_clean(adjustment.get("type") or "none"))),
        "adjustment_percent": _money(adjustment.get("percent")),
        "adjustment_amount": _money(adjustment.get("adjustment_amount")),
        "base_amount": _money(adjustment.get("base_amount") or subtotal),
        "total_payable": total,
        "adjustment_mode": _clean(adjustment.get("mode") or "none"),
        "payment_method": row["payment_method"],
        "notes": row["notes"] or "",
        "status": row["status"],
        "pipeline_status": _pipeline_status(row),
        "invoice_number": invoice_number,
        "items": items,
        "item_count": len(items),
        "is_multi_item": len(items) > 1,
        "is_prepared": bool(_row_value(row, "is_prepared", False)),
        "prepared_at": _iso(_row_value(row, "prepared_at")),
        "prepared_by": str(_row_value(row, "prepared_by")) if _row_value(row, "prepared_by") else None,
        "has_support": support is not None,
        "support": support,
        "has_guide": guide is not None,
        "guide": guide,
        "archived_at": _iso(_row_value(row, "archived_at")),
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_by_label": created_by_label or "Usuario mini panel",
        "source_user_label": created_by_label or "Usuario mini panel",
        "source_panel_type": row["panel_type"],
        "source_panel_label": _panel_label(row["panel_type"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


@router.get("/companies/{company_id}/config")
async def get_sales_config(company_id: uuid.UUID) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        if not await _company_exists(conn, company_id):
            raise HTTPException(status_code=404, detail="Empresa no encontrada.")
        config = await _settings(conn, company_id)
        return {
            "company_id": str(company_id),
            "occupation": config["occupation"],
            "custom_categories": config["custom_categories"],
        }
    finally:
        await conn.close()


@router.post("/companies/{company_id}/config")
async def save_sales_config(company_id: uuid.UUID, payload: SalesConfigIn) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        if not await _company_exists(conn, company_id):
            raise HTTPException(status_code=404, detail="Empresa no encontrada.")
        occupation = _occupation(payload.occupation)
        custom_categories = [_clean(item) for item in (payload.custom_categories or []) if _clean(item)]
        settings = {"custom_categories": custom_categories}
        await conn.execute(
            """
            INSERT INTO mini_panel_sales_settings (company_id, occupation, settings, created_at, updated_at)
            VALUES ($1::uuid, $2, $3::jsonb, NOW(), NOW())
            ON CONFLICT (company_id)
            DO UPDATE SET occupation = EXCLUDED.occupation, settings = EXCLUDED.settings, updated_at = NOW()
            """,
            company_id,
            occupation,
            json.dumps(settings),
        )
        return {
            "company_id": str(company_id),
            "occupation": occupation,
            "custom_categories": custom_categories,
            "saved": True,
        }
    finally:
        await conn.close()


@router.get("/companies/{company_id}/categories")
async def list_sales_categories(
    company_id: uuid.UUID,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        config = await _settings(conn, company_id)
        categories = await _reference_categories(conn, company_id)
        if not categories:
            categories = _fallback_categories(config["occupation"], config.get("custom_categories"))
        return {
            "company_id": str(company_id),
            "panel_type": _panel(panel_type),
            "occupation": config["occupation"],
            "count": len(categories),
            "items": categories,
        }
    finally:
        await conn.close()


@router.get("/companies/{company_id}/references")
async def list_sales_references(
    company_id: uuid.UUID,
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)

        table = await conn.fetchval("SELECT to_regclass('public.product_references')")
        if not table:
            return {"company_id": str(company_id), "count": 0, "items": []}

        where = [
            "company_id = $1::text",
            "COALESCE(archived, false) IS NOT TRUE",
            "(COALESCE(system_active, false) IS TRUE OR COALESCE(channel, '') IN ('system', 'both'))",
        ]
        args: list[Any] = [str(company_id)]
        idx = 2

        category_clean = _clean(category)
        if category_clean:
            where.append(f"lower(COALESCE(NULLIF(category, ''), 'Otros')) = lower(${idx})")
            args.append(category_clean)
            idx += 1

        search = _clean(q)
        if search:
            where.append(f"(id ILIKE ${idx} OR name ILIKE ${idx} OR size ILIKE ${idx} OR COALESCE(color, '') ILIKE ${idx} OR COALESCE(category, '') ILIKE ${idx} OR COALESCE(sku, '') ILIKE ${idx})")
            args.append(f"%{search}%")
            idx += 1

        args.append(limit)
        rows = await conn.fetch(
            f"""
            SELECT
                id,
                company_id,
                name,
                COALESCE(category, '') AS category,
                size,
                COALESCE(color, '') AS color,
                COALESCE(sku, '') AS sku,
                COALESCE(unit_price, 0)::float AS unit_price,
                initial_quantity,
                bot_active,
                COALESCE(system_active, false) AS system_active,
                COALESCE(NULLIF(channel, ''), CASE WHEN COALESCE(system_active, false) IS TRUE THEN 'system' ELSE 'bot' END) AS channel
            FROM product_references
            WHERE {" AND ".join(where)}
            ORDER BY name ASC, size ASC, color ASC
            LIMIT ${idx}
            """,
            *args,
        )

        items = [
            {
                "id": _clean(row["id"]),
                "name": _clean(row["name"]),
                "category": _clean(row["category"]),
                "size": _clean(row["size"]),
                "color": _clean(row["color"]),
                "sku": _clean(row["sku"]),
                "barcode": _clean(row["sku"]),
                "unit_price": float(row["unit_price"] or 0),
                "initial_quantity": int(row["initial_quantity"] or 0),
                "channel": _clean(row["channel"]),
                "system_active": bool(row["system_active"]),
                "label": " · ".join(part for part in [_clean(row["name"]), _clean(row["size"]), _clean(row["color"])] if part),
            }
            for row in rows
        ]

        return {"company_id": str(company_id), "count": len(items), "items": items}
    finally:
        await conn.close()


@router.get("/companies/{company_id}/sales")
async def list_sales(
    company_id: uuid.UUID,
    panel_type: str = Query("sales"),
    q: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    include_cut_history: bool = Query(default=False),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        scope_user_id = _scope_user_id(access)
        panel = _panel(panel_type)

        where = ["s.company_id = $1::uuid"]
        args: list[Any] = [company_id]
        idx = 2

        if panel not in {"all", "client"}:
            where.append(f"s.panel_type = ${idx}")
            args.append(panel)
            idx += 1

        if not include_archived:
            where.append("s.status <> 'archived'")

        if scope_user_id:
            where.append(f"s.created_by = ${idx}::uuid")
            args.append(scope_user_id)
            idx += 1

        if not include_cut_history:
            cut_config = await _sales_cut_config(conn, company_id)
            cut_where, cut_args, idx = _cut_sql_parts(cut_config, idx)
            where.extend(cut_where)
            args.extend(cut_args)

        search = _clean(q)
        if search:
            where.append(f"(s.reference_name ILIKE ${idx} OR s.reference_category ILIKE ${idx} OR s.created_by_label ILIKE ${idx} OR s.metadata::text ILIKE ${idx})")
            args.append(f"%{search}%")
            idx += 1

        rows = await conn.fetch(
            f"""
            SELECT
                s.*,
                COALESCE(
                    NULLIF(s.created_by_label, ''),
                    (SELECT NULLIF(cu.full_name, '') FROM company_users cu WHERE cu.id = s.created_by AND cu.company_id = s.company_id LIMIT 1),
                    (SELECT NULLIF(cu.email, '') FROM company_users cu WHERE cu.id = s.created_by AND cu.company_id = s.company_id LIMIT 1),
                    ''
                ) AS creator_display_label
            FROM mini_panel_sales_records s
            WHERE {" AND ".join(where)}
            ORDER BY s.created_at DESC
            LIMIT 500
            """,
            *args,
        )
        items = [_sale_payload(row) for row in rows]
        active_items = [item for item in items if item["status"] != "archived"]
        cut_summary = await _sales_cut_summary(
            conn,
            company_id,
            panel_type=panel,
            scope_user_id=scope_user_id,
            include_archived=include_archived,
        )
        return {
            "company_id": str(company_id),
            "panel_type": panel,
            "count": len(items),
            "active_count": len(active_items),
            "total_amount": round(sum(float(item["total"] or 0) for item in active_items), 2),
            "cut": cut_summary,
            "items": items,
        }
    finally:
        await conn.close()


@router.post("/companies/{company_id}/sales", status_code=status.HTTP_201_CREATED)
async def create_sale(
    company_id: uuid.UUID,
    payload: SaleCreateIn,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        created_by = _scope_user_id(access)
        if not created_by:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Registro de venta requiere usuario de mini panel.")

        items = _sale_items_from_payload(payload)
        if not items:
            raise HTTPException(status_code=422, detail="Agrega al menos un artículo a la factura.")

        sale_id = uuid.uuid4()
        invoice_number = f"FV-{datetime.now(timezone.utc).year}-{str(sale_id).split('-')[0].upper()}"

        adjustment = _adjustment_meta_from_payload(payload, items)
        total = round(_money(adjustment.get("total_payable")), 2)
        quantity = round(sum(_money(item.get("quantity")) for item in items), 2)
        first = items[0]
        categories = []
        for item in items:
            category = _clean(item.get("reference_category"))
            if category and category not in categories:
                categories.append(category)

        reference_name = (
            _clean(first.get("reference_name"))
            if len(items) == 1
            else f"Factura {len(items)} artículos"
        )

        metadata = {
            "source": "registro_venta_multiitem_022h",
            "source_patch": "022J_top10_adjustments_clean_view",
            "invoice_number": invoice_number,
            "item_count": len(items),
            "items": items,
            "adjustment": adjustment,
        }

        row = await conn.fetchrow(
            """
            INSERT INTO mini_panel_sales_records (
                id,
                company_id,
                panel_type,
                reference_id,
                reference_name,
                reference_category,
                reference_size,
                reference_color,
                quantity,
                unit_price,
                total,
                payment_method,
                notes,
                status,
                created_by,
                created_by_label,
                metadata,
                created_at,
                updated_at
            )
            VALUES (
                $1::uuid, $2::uuid, $3,
                $4, $5, $6, $7, $8,
                $9, $10, $11,
                $12, $13, 'active',
                $14::uuid, $15, $16::jsonb, NOW(), NOW()
            )
            RETURNING *
            """,
            sale_id,
            company_id,
            _panel(panel_type),
            _clean(first.get("reference_id")),
            reference_name,
            _clean(", ".join(categories))[:160],
            _clean(first.get("reference_size")) if len(items) == 1 else "",
            _clean(first.get("reference_color")) if len(items) == 1 else "",
            quantity,
            _money(first.get("unit_price")) if len(items) == 1 else 0,
            total,
            _norm(payload.payment_method or "efectivo"),
            _clean(payload.notes),
            created_by,
            _scope_label(access),
            json.dumps(metadata, ensure_ascii=False),
        )

        return {"sale": _sale_payload(row), "created": True, "invoice_number": invoice_number}
    finally:
        await conn.close()


@router.post("/companies/{company_id}/sales/{sale_id}/archive")
async def archive_sale(
    company_id: uuid.UUID,
    sale_id: uuid.UUID,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        scope_user_id = _scope_user_id(access)
        panel = _panel(panel_type)

        if scope_user_id:
            row = await conn.fetchrow(
                """
                UPDATE mini_panel_sales_records
                SET status = 'archived', archived_at = NOW(), updated_at = NOW()
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                  AND panel_type = $3
                  AND created_by = $4::uuid
                RETURNING *
                """,
                sale_id,
                company_id,
                panel,
                scope_user_id,
            )
        else:
            row = await conn.fetchrow(
                """
                UPDATE mini_panel_sales_records
                SET status = 'archived', archived_at = NOW(), updated_at = NOW()
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                RETURNING *
                """,
                sale_id,
                company_id,
            )

        if not row:
            raise HTTPException(status_code=404, detail="Venta no encontrada.")

        return {"sale": _sale_payload(row), "archived": True}
    finally:
        await conn.close()



@router.post("/companies/{company_id}/sales/{sale_id}/prepared")
async def set_sale_prepared(
    company_id: uuid.UUID,
    sale_id: uuid.UUID,
    payload: SalePreparedIn,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        scope_user_id = _scope_user_id(access)
        if not scope_user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Alistamiento requiere usuario de mini panel.")

        row = await conn.fetchrow(
            """
            UPDATE mini_panel_sales_records
            SET
                is_prepared = $1,
                prepared_at = CASE WHEN $1 THEN COALESCE(prepared_at, NOW()) ELSE NULL END,
                prepared_by = CASE WHEN $1 THEN $5::uuid ELSE NULL END,
                status = CASE
                    WHEN $1 AND status = 'active' THEN 'prepared'
                    WHEN NOT $1 AND status = 'prepared' THEN 'active'
                    ELSE status
                END,
                updated_at = NOW()
            WHERE id = $2::uuid
              AND company_id = $3::uuid
              AND panel_type = $4
              AND created_by = $5::uuid
              AND status <> 'archived'
            RETURNING *
            """,
            bool(payload.prepared),
            sale_id,
            company_id,
            _panel(panel_type),
            scope_user_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Venta no encontrada para este usuario.")

        return {"sale": _sale_payload(row), "prepared": bool(payload.prepared)}
    finally:
        await conn.close()


@router.post("/companies/{company_id}/sales/{sale_id}/support")
async def attach_sale_support(
    company_id: uuid.UUID,
    sale_id: uuid.UUID,
    payload: SaleAttachmentIn,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        scope_user_id = _scope_user_id(access)
        if not scope_user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Adjuntar soporte requiere usuario de mini panel.")

        row = await conn.fetchrow(
            """
            UPDATE mini_panel_sales_records
            SET
                is_prepared = TRUE,
                prepared_at = COALESCE(prepared_at, NOW()),
                prepared_by = COALESCE(prepared_by, $7::uuid),
                support_file_name = $1,
                support_file_type = $2,
                support_file_data = $3,
                support_uploaded_at = NOW(),
                support_uploaded_by = $7::uuid,
                status = CASE WHEN status = 'archived' THEN status ELSE 'support_attached' END,
                updated_at = NOW()
            WHERE id = $4::uuid
              AND company_id = $5::uuid
              AND panel_type = $6
              AND created_by = $7::uuid
              AND status <> 'archived'
            RETURNING *
            """,
            _clean(payload.file_name),
            _clean(payload.file_type or "application/octet-stream"),
            payload.file_data,
            sale_id,
            company_id,
            _panel(panel_type),
            scope_user_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Venta no encontrada para este usuario.")

        return {"sale": _sale_payload(row), "support_attached": True}
    finally:
        await conn.close()


@router.post("/companies/{company_id}/sales/{sale_id}/guide")
async def attach_sale_guide(
    company_id: uuid.UUID,
    sale_id: uuid.UUID,
    payload: SaleGuideIn,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        scope_user_id = _scope_user_id(access)

        row = await conn.fetchrow(
            """
            UPDATE mini_panel_sales_records
            SET
                guide_file_name = $1,
                guide_file_type = $2,
                guide_file_data = $3,
                guide_uploaded_at = NOW(),
                guide_uploaded_by = $6::uuid,
                status = CASE WHEN status = 'archived' THEN status ELSE 'guide_attached' END,
                updated_at = NOW()
            WHERE id = $4::uuid
              AND company_id = $5::uuid
            RETURNING *
            """,
            _clean(payload.file_name),
            _clean(payload.file_type or "application/octet-stream"),
            payload.file_data,
            sale_id,
            company_id,
            scope_user_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Venta no encontrada.")

        return {"sale": _sale_payload(row), "guide_attached": True}
    finally:
        await conn.close()


@router.get("/companies/{company_id}/summary")
async def sales_summary(
    company_id: uuid.UUID,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    data = await list_sales(company_id=company_id, panel_type=panel_type, include_archived=False, authorization=authorization)
    latest = data["items"][0] if data["items"] else None
    return {
        "company_id": str(company_id),
        "panel_type": _panel(panel_type),
        "active_count": data["active_count"],
        "total_amount": data["total_amount"],
        "cut": data.get("cut") or {},
        "latest": latest,
    }


@router.get("/companies/{company_id}/cut")
async def get_sales_cut(
    company_id: uuid.UUID,
    panel_type: str = Query("all"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        return await _sales_cut_summary(
            conn,
            company_id,
            panel_type=panel_type,
            scope_user_id=_scope_user_id(access),
            include_archived=False,
        )
    finally:
        await conn.close()


@router.post("/companies/{company_id}/cut/config")
async def save_sales_cut_config(
    company_id: uuid.UUID,
    payload: SalesCutConfigIn,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        config = await _save_sales_cut_config(conn, company_id, payload.period_type)
        return {
            "company_id": str(company_id),
            "period_type": config["period_type"],
            "period_label": config["period_label"],
            "started_at": config["started_at"],
            "saved": True,
        }
    finally:
        await conn.close()


@router.post("/companies/{company_id}/cut/generate")
async def generate_sales_cut(
    company_id: uuid.UUID,
    payload: SalesCutGenerateIn,
    panel_type: str = Query("all"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        period_type = _cut_period(payload.period_type)
        panel = _panel(panel_type)
        summary = await _sales_cut_summary(conn, company_id, panel_type=panel, include_archived=False)
        now = datetime.now(timezone.utc)
        period_start = _parse_dt(summary.get("period_started_at")) or now
        cut_id = uuid.uuid4()

        await conn.execute(
            """
            INSERT INTO mini_panel_sales_cuts (
                id,
                company_id,
                panel_type,
                period_type,
                period_start,
                period_end,
                total_amount,
                active_count,
                top_seller_label,
                top_seller_amount,
                top_store_label,
                top_store_amount,
                generated_by,
                generated_by_label,
                metadata,
                created_at
            )
            VALUES (
                $1::uuid, $2::uuid, $3, $4,
                $5::timestamptz, $6::timestamptz,
                $7, $8,
                $9, $10,
                $11, $12,
                $13::uuid, $14,
                $15::jsonb,
                NOW()
            )
            """,
            cut_id,
            company_id,
            panel,
            period_type,
            period_start,
            now,
            _money(summary.get("total_amount")),
            int(summary.get("active_count") or 0),
            _clean((summary.get("top_seller") or {}).get("label")),
            _money((summary.get("top_seller") or {}).get("amount")),
            _clean((summary.get("top_store") or {}).get("label")),
            _money((summary.get("top_store") or {}).get("amount")),
            _scope_user_id(access),
            _scope_label(access) or "Panel Cliente",
            json.dumps({"summary": summary, "source": "022L_panel_cliente_corte"}, ensure_ascii=False),
        )

        config = await _save_sales_cut_config(conn, company_id, period_type, started_at=now, last_cut_id=cut_id)
        return {
            "company_id": str(company_id),
            "cut_id": str(cut_id),
            "period_type": config["period_type"],
            "period_label": config["period_label"],
            "closed_summary": summary,
            "new_period_started_at": config["started_at"],
            "generated": True,
        }
    finally:
        await conn.close()

