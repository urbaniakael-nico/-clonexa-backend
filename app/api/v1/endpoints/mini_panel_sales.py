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


class SaleCreateIn(BaseModel):
    reference_id: str | None = Field(default=None, max_length=80)
    reference_name: str = Field(..., min_length=1, max_length=220)
    reference_category: str | None = Field(default=None, max_length=160)
    reference_size: str | None = Field(default=None, max_length=120)
    reference_color: str | None = Field(default=None, max_length=120)
    quantity: float = Field(default=1, ge=0)
    unit_price: float = Field(default=0, ge=0)
    payment_method: str | None = Field(default="efectivo", max_length=60)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("payment_method")
    @classmethod
    def clean_payment_method(cls, value: str | None) -> str:
        raw = _norm(value or "efectivo")
        return raw if raw in {"efectivo", "transferencia", "cheque", "tarjeta", "otro"} else "otro"


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
        "settings": settings,
        "custom_categories": settings.get("custom_categories") if isinstance(settings.get("custom_categories"), list) else [],
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


def _sale_payload(row: asyncpg.Record) -> dict[str, Any]:
    total = _money(row["total"])
    quantity = _money(row["quantity"])
    unit_price = _money(row["unit_price"])
    created_by_label = _clean(_row_value(row, "creator_display_label", "")) or _clean(_row_value(row, "created_by_label", ""))
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
        "payment_method": row["payment_method"],
        "notes": row["notes"] or "",
        "status": row["status"],
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_by_label": created_by_label or "Usuario mini panel",
        "source_user_label": created_by_label or "Usuario mini panel",
        "source_panel_type": row["panel_type"],
        "source_panel_label": _panel_label(row["panel_type"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
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
            where.append(f"(name ILIKE ${idx} OR size ILIKE ${idx} OR COALESCE(color, '') ILIKE ${idx} OR COALESCE(category, '') ILIKE ${idx})")
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

        search = _clean(q)
        if search:
            where.append(f"(s.reference_name ILIKE ${idx} OR s.reference_category ILIKE ${idx} OR s.created_by_label ILIKE ${idx})")
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
        return {
            "company_id": str(company_id),
            "panel_type": panel,
            "count": len(items),
            "active_count": len(active_items),
            "total_amount": round(sum(float(item["total"] or 0) for item in active_items), 2),
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

        quantity = max(0.0, _money(payload.quantity))
        unit_price = max(0.0, _money(payload.unit_price))
        total = round(quantity * unit_price, 2)
        sale_id = uuid.uuid4()

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
                $14::uuid, $15, '{}'::jsonb, NOW(), NOW()
            )
            RETURNING *
            """,
            sale_id,
            company_id,
            _panel(panel_type),
            _clean(payload.reference_id),
            _clean(payload.reference_name),
            _clean(payload.reference_category),
            _clean(payload.reference_size),
            _clean(payload.reference_color),
            quantity,
            unit_price,
            total,
            _norm(payload.payment_method or "efectivo"),
            _clean(payload.notes),
            created_by,
            _scope_label(access),
        )

        return {"sale": _sale_payload(row), "created": True}
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
                SET status = 'archived', updated_at = NOW()
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
                SET status = 'archived', updated_at = NOW()
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
        "latest": latest,
    }
