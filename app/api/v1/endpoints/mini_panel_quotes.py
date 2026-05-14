from __future__ import annotations

import base64
import io
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

try:
    from app.services.auth_service import decode_access_token
except Exception:  # pragma: no cover
    decode_access_token = None


router = APIRouter()

QUOTE_ALIASES = {
    "cotizacion",
    "cotizaciones",
    "quote",
    "quotes",
    "quotation",
    "quotations",
    "cotizar",
    "presupuesto",
    "presupuestos",
}

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
}

VALID_STATUS = {"draft", "issued", "archived", "converted"}
PAYMENT_METHODS = {"efectivo", "transferencia", "cheque", "otro"}


class QuoteItemIn(BaseModel):
    description: str = Field(..., min_length=1, max_length=600)
    quantity: float = Field(default=1, ge=0)
    unit_price: float = Field(default=0, ge=0)


class QuoteDiscountIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    value: float = Field(default=0, ge=0)


class QuotePaymentIn(BaseModel):
    detail: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, max_length=120)
    method: str | None = Field(default="transferencia", max_length=40)
    data: str | None = Field(default=None, max_length=1200)

    @field_validator("method")
    @classmethod
    def _clean_method(cls, value: str | None) -> str:
        clean = _norm(value or "transferencia")
        return clean if clean in PAYMENT_METHODS else "otro"


class MiniPanelQuoteCreate(BaseModel):
    client_name: str = Field(..., min_length=1, max_length=220)
    client_document: str | None = Field(default=None, max_length=80)
    client_address: str | None = Field(default=None, max_length=260)
    client_phone: str | None = Field(default=None, max_length=80)
    client_email: str | None = Field(default=None, max_length=180)
    items: list[QuoteItemIn] = Field(default_factory=list)
    discounts: list[QuoteDiscountIn] = Field(default_factory=list)
    payment: QuotePaymentIn | None = None
    notes: str | None = Field(default=None, max_length=2500)
    signature_data_url: str | None = Field(default=None, max_length=2_500_000)

    @field_validator("client_name")
    @classmethod
    def _clean_client_name(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not clean:
            raise ValueError("El nombre o razon social es obligatorio.")
        return clean


class MiniPanelQuoteUpdate(MiniPanelQuoteCreate):
    status: str | None = None

    @field_validator("status")
    @classmethod
    def _clean_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = _norm(value)
        if clean not in VALID_STATUS:
            raise ValueError("Estado invalido.")
        return clean


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


def _panel(value: str) -> str:
    normalized = _norm(value)
    return PANEL_ALIASES.get(normalized, normalized or "sales")


# CLONEXA_021F_R1_CROSS_PANEL_BACKEND_START
def _is_cross_panel_quotes_021f(panel_type: str | None) -> bool:
    normalized = _norm(panel_type or "")
    return normalized in {"", "all", "client", "main", "principal", "universal", "global", "*"}


def _quote_panel_for_action_021f(panel_type: str | None) -> str:
    return "all" if _is_cross_panel_quotes_021f(panel_type) else _panel(panel_type or "sales")
# CLONEXA_021F_R1_CROSS_PANEL_BACKEND_END


def _json(value: Any, fallback: Any = None) -> Any:
    if fallback is None:
        fallback = {}
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return fallback


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return round(float(value), 2)
    except Exception:
        return 0.0


def _clean_text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _extract_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido.")
    if raw.lower().startswith("bearer "):
        return raw.split(" ", 1)[1].strip()
    return raw


async def _ensure_storage(conn: asyncpg.Connection) -> None:
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_panel_quotes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            panel_type VARCHAR(50) NOT NULL DEFAULT 'sales',
            quote_number VARCHAR(80) NOT NULL,
            client_name VARCHAR(220) NOT NULL,
            client_document VARCHAR(80),
            client_address VARCHAR(260),
            client_phone VARCHAR(80),
            client_email VARCHAR(180),
            items JSONB NOT NULL DEFAULT '[]'::jsonb,
            discounts JSONB NOT NULL DEFAULT '[]'::jsonb,
            payment JSONB NOT NULL DEFAULT '{}'::jsonb,
            notes TEXT,
            signature_data_url TEXT,
            subtotal NUMERIC(14, 2) NOT NULL DEFAULT 0,
            discount_total NUMERIC(14, 2) NOT NULL DEFAULT 0,
            total NUMERIC(14, 2) NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'issued',
            converted_at TIMESTAMPTZ,
            archived_at TIMESTAMPTZ,
            created_by UUID NULL,
            created_by_label VARCHAR(180),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, quote_number)
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_quotes_company_panel_status
        ON mini_panel_quotes (company_id, panel_type, status, created_at DESC);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_quotes_company_panel_client
        ON mini_panel_quotes (company_id, panel_type, client_name);
        """
    )


async def _require_access(conn: asyncpg.Connection, company_id: uuid.UUID, authorization: str | None) -> dict[str, Any]:
    # CLONEXA_021D_UNIVERSAL_ACCESS_START
    # /client no maneja token de mini panel. Para módulos universales se permite
    # acceso operativo por company_id cuando la empresa existe. La habilitación real
    # del módulo se valida después en _require_*_enabled.
    if not str(authorization or "").strip():
        company_row = await conn.fetchrow(
            "SELECT id, name, slug FROM companies WHERE id = $1::uuid LIMIT 1",
            company_id,
        )
        if company_row:
            return {
                "company_id": str(company_row["id"]),
                "user_id": None,
                "full_name": "Panel principal",
                "email": None,
                "source": "client_universal",
            }
    # CLONEXA_021D_UNIVERSAL_ACCESS_END
    if decode_access_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Servicio de autenticacion no disponible.")

    token = _extract_token(authorization)
    payload = decode_access_token(token)

    raw_company = payload.get("company_id") or payload.get("tenant_id") or payload.get("company")
    if raw_company and str(raw_company) == str(company_id):
        return payload

    raw_user_id = payload.get("sub") or payload.get("user_id") or payload.get("id")
    if raw_user_id:
        try:
            user_uuid = uuid.UUID(str(raw_user_id))
        except Exception:
            user_uuid = None

        if user_uuid:
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
                    "full_name": row["full_name"],
                    "email": row["email"],
                }

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso no autorizado para esta empresa.")



# CLONEXA_021D_UNIVERSAL_ACCESS_START
async def _company_has_universal_quotes_module_021d(conn: asyncpg.Connection, company_id: uuid.UUID) -> bool:
    rows = await conn.fetch(
        """
        SELECT m.code, m.name
        FROM company_modules cm
        JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = $1::uuid
          AND cm.enabled = TRUE
        """,
        company_id,
    )

    for row in rows:
        code = _norm(row["code"])
        name = _norm(row["name"])
        if code in QUOTE_ALIASES or name in QUOTE_ALIASES:
            return True

    return False
# CLONEXA_021D_UNIVERSAL_ACCESS_END

async def _require_quotes_enabled(conn: asyncpg.Connection, company_id: uuid.UUID, panel_type: str) -> None:
    # CLONEXA_021D_UNIVERSAL_ACCESS_START
    # Si el módulo está activo en el panel principal de la empresa, también queda
    # funcional en /client y disponible para mini paneles adaptables.
    if await _company_has_universal_quotes_module_021d(conn, company_id):
        return
    # CLONEXA_021D_UNIVERSAL_ACCESS_END
    row = await conn.fetchrow(
        """
        SELECT cm.settings
        FROM company_modules cm
        JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = $1::uuid
          AND cm.enabled = TRUE
          AND (
            lower(m.code) = 'mini_panel'
            OR lower(m.name) LIKE '%mini%panel%'
            OR lower(m.name) LIKE '%creacion%mini%'
            OR lower(m.name) LIKE '%creaciÃ³n%mini%'
          )
        LIMIT 1
        """,
        company_id,
    )

    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mini Panel no esta activo para esta empresa.")

    settings = _json(row["settings"], {})
    config = settings.get("mini_panel_modules") if isinstance(settings.get("mini_panel_modules"), dict) else settings
    panels = config.get("panels") if isinstance(config.get("panels"), dict) else {}
    selected = _panel(panel_type)

    panel = (
        panels.get(selected)
        or panels.get(f"{selected}s")
        or panels.get("store" if selected == "stores" else "")
        or {}
    )

    modules = panel.get("modules") if isinstance(panel.get("modules"), list) else []
    normalized = {_norm(item) for item in modules}
    if not (normalized & QUOTE_ALIASES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cotizaciones no esta asignado a este mini panel.")


async def _company_profile(conn: asyncpg.Connection, company_id: uuid.UUID) -> dict[str, Any]:
    row = await conn.fetchrow("SELECT * FROM companies WHERE id = $1::uuid LIMIT 1", company_id)
    if not row:
        return {}

    profile = dict(row)
    store = _json(profile.get("settings_json"), {})

    # CLONEXA_021C_COMPANY_PROFILE_LOGO_SOURCES_START
    company_settings_json: dict[str, Any] = {}
    company_branding_row: dict[str, Any] = {}

    try:
        settings_row = await conn.fetchrow(
            '''
            SELECT settings_json
            FROM company_settings
            WHERE company_id = $1::uuid
            LIMIT 1
            ''',
            company_id,
        )
        if settings_row:
            company_settings_json = _json(settings_row["settings_json"], {})
    except Exception:
        company_settings_json = {}

    try:
        branding_row = await conn.fetchrow(
            '''
            SELECT *
            FROM company_branding
            WHERE company_id = $1::uuid
            LIMIT 1
            ''',
            company_id,
        )
        if branding_row:
            company_branding_row = dict(branding_row)
    except Exception:
        company_branding_row = {}
    # CLONEXA_021C_COMPANY_PROFILE_LOGO_SOURCES_END

    branding_candidates: list[Any] = [
        profile.get("branding"),
        profile.get("company_branding"),
        profile.get("branding_json"),
        company_branding_row,
        store.get("branding") if isinstance(store, dict) else None,
        store.get("company_branding") if isinstance(store, dict) else None,
        (store.get("experience") or {}).get("branding")
        if isinstance(store, dict) and isinstance(store.get("experience"), dict)
        else None,
        company_settings_json.get("branding") if isinstance(company_settings_json, dict) else None,
        company_settings_json.get("company_branding") if isinstance(company_settings_json, dict) else None,
        (company_settings_json.get("experience") or {}).get("branding")
        if isinstance(company_settings_json, dict) and isinstance(company_settings_json.get("experience"), dict)
        else None,
    ]

    branding: dict[str, Any] = {}
    for candidate in branding_candidates:
        if isinstance(candidate, dict) and candidate:
            branding = candidate
            break

    logo_url = (
        str(
            branding.get("logo_url")
            or branding.get("logo")
            or branding.get("brand_logo_url")
            or branding.get("logo_data_url")
            or branding.get("logo_base64")
            or branding.get("image_url")
            or ""
        ).strip()
        if isinstance(branding, dict)
        else ""
    )

    profile["branding"] = branding
    profile["company_branding"] = branding
    profile["company_settings_json"] = company_settings_json
    profile["company_branding_row"] = company_branding_row
    profile["logo_url"] = logo_url
    profile["brand_logo_url"] = logo_url
    return profile


def _sanitize_items(items: list[QuoteItemIn]) -> tuple[list[dict[str, Any]], float]:
    sanitized: list[dict[str, Any]] = []
    subtotal = 0.0

    for item in items:
        description = _clean_text(item.description, 600)
        if not description:
            continue
        quantity = max(0.0, _money(item.quantity))
        unit_price = max(0.0, _money(item.unit_price))
        line_total = round(quantity * unit_price, 2)
        subtotal += line_total
        sanitized.append(
            {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "total": line_total,
            }
        )

    if not sanitized:
        raise HTTPException(status_code=400, detail="La cotizacion debe tener al menos un concepto.")

    return sanitized, round(subtotal, 2)


def _sanitize_discounts(discounts: list[QuoteDiscountIn], subtotal: float) -> tuple[list[dict[str, Any]], float]:
    sanitized: list[dict[str, Any]] = []
    total = 0.0

    for discount in (discounts or [])[:2]:
        value = max(0.0, _money(discount.value))
        if value <= 0 and not _clean_text(discount.name, 120) and not _clean_text(discount.description, 500):
            continue
        total += value
        sanitized.append(
            {
                "name": _clean_text(discount.name, 120),
                "description": _clean_text(discount.description, 500),
                "value": value,
            }
        )

    total = min(round(total, 2), max(0.0, subtotal))
    return sanitized, total


def _payment_payload(payment: QuotePaymentIn | None) -> dict[str, Any]:
    if payment is None:
        return {"detail": "", "name": "", "method": "transferencia", "data": ""}
    return {
        "detail": _clean_text(payment.detail, 500),
        "name": _clean_text(payment.name, 120),
        "method": _norm(payment.method or "transferencia") or "transferencia",
        "data": _clean_text(payment.data, 1200),
    }


def _signature(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if not raw.startswith("data:image/"):
        return None
    if len(raw) > 2_500_000:
        raise HTTPException(status_code=400, detail="La firma digital es demasiado grande.")
    return raw


def _account_number_from_quote_number(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        year = datetime.now(timezone.utc).year
        return f"CB-{year}-0001"

    upper = raw.upper()
    for prefix in ("COT-", "CT-", "COTIZACION-", "COTIZACIÓN-"):
        if upper.startswith(prefix):
            return "CB-" + raw[len(prefix):]

    if upper.startswith("CB-"):
        return raw

    return f"CB-{raw}"


def _quote_number_for_account_base(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    upper = raw.upper()
    if upper.startswith("CB-"):
        return "CT-" + raw[3:]
    return raw


def _quote_payload(row: asyncpg.Record) -> dict[str, Any]:
    items = _json(row["items"], [])
    discounts = _json(row["discounts"], [])
    payment = _json(row["payment"], {})
    status_value = row["status"]
    quote_number = row["quote_number"]
    is_account = str(status_value or "").lower() == "converted"
    account_number = _account_number_from_quote_number(quote_number)

    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "panel_type": row["panel_type"],
        "quote_number": quote_number,
        "account_number": account_number,
        "document_number": account_number if is_account else quote_number,
        "document_type": "account" if is_account else "quote",
        "document_label": "Cuenta de cobro" if is_account else "Cotización",
        "client_name": row["client_name"],
        "client_document": row["client_document"] or "",
        "client_address": row["client_address"] or "",
        "client_phone": row["client_phone"] or "",
        "client_email": row["client_email"] or "",
        "items": items if isinstance(items, list) else [],
        "discounts": discounts if isinstance(discounts, list) else [],
        "payment": payment if isinstance(payment, dict) else {},
        "notes": row["notes"] or "",
        "signature_data_url": row["signature_data_url"] or "",
        "subtotal": _money(row["subtotal"]),
        "discount_total": _money(row["discount_total"]),
        "total": _money(row["total"]),
        "status": status_value,
        "converted_at": row["converted_at"].isoformat() if row["converted_at"] else None,
        "archived_at": row["archived_at"].isoformat() if row["archived_at"] else None,
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_by_label": row["created_by_label"] or "",
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }

async def _next_quote_number(conn: asyncpg.Connection, company_id: uuid.UUID) -> str:
    year = datetime.now(timezone.utc).year
    rows = await conn.fetch(
        """
        SELECT quote_number
        FROM mini_panel_quotes
        WHERE company_id = $1::uuid
          AND (quote_number LIKE $2 OR quote_number LIKE $3)
        ORDER BY quote_number DESC
        LIMIT 200
        """,
        company_id,
        f"CT-{year}-%",
        f"COT-{year}-%",
    )

    max_num = 0
    for row in rows:
        raw = str(row["quote_number"] or "")
        try:
            max_num = max(max_num, int(raw.split("-")[-1]))
        except Exception:
            continue

    return f"CT-{year}-{max_num + 1:04d}"

async def _insert_or_update_quote(
    conn: asyncpg.Connection,
    company_id: uuid.UUID,
    panel_type: str,
    payload: MiniPanelQuoteCreate | MiniPanelQuoteUpdate,
    user: dict[str, Any],
    quote_id: uuid.UUID | None = None,
) -> asyncpg.Record:
    items, subtotal = _sanitize_items(payload.items)
    discounts, discount_total = _sanitize_discounts(payload.discounts, subtotal)
    total = round(max(0.0, subtotal - discount_total), 2)
    payment = _payment_payload(payload.payment)
    signature = _signature(payload.signature_data_url)

    raw_user_id = user.get("user_id") or user.get("sub") or user.get("id")
    created_by = None
    try:
        created_by = uuid.UUID(str(raw_user_id)) if raw_user_id else None
    except Exception:
        created_by = None

    if quote_id is None:
        quote_number = await _next_quote_number(conn, company_id)
        return await conn.fetchrow(
            """
            INSERT INTO mini_panel_quotes (
                company_id,
                panel_type,
                quote_number,
                client_name,
                client_document,
                client_address,
                client_phone,
                client_email,
                items,
                discounts,
                payment,
                notes,
                signature_data_url,
                subtotal,
                discount_total,
                total,
                status,
                created_by,
                created_by_label,
                metadata,
                created_at,
                updated_at
            )
            VALUES (
                $1::uuid, $2, $3, $4, $5, $6, $7, $8,
                $9::jsonb, $10::jsonb, $11::jsonb, $12, $13,
                $14, $15, $16, 'issued',
                $17::uuid, $18, '{}'::jsonb, NOW(), NOW()
            )
            RETURNING *
            """,
            company_id,
            _panel(panel_type),
            quote_number,
            payload.client_name,
            payload.client_document,
            payload.client_address,
            payload.client_phone,
            payload.client_email,
            json.dumps(items, ensure_ascii=False),
            json.dumps(discounts, ensure_ascii=False),
            json.dumps(payment, ensure_ascii=False),
            payload.notes,
            signature,
            subtotal,
            discount_total,
            total,
            created_by,
            user.get("full_name") or user.get("email") or "",
        )

    status_value = getattr(payload, "status", None) or "issued"
    if status_value not in VALID_STATUS:
        status_value = "issued"

    return await conn.fetchrow(
        """
        UPDATE mini_panel_quotes
        SET client_name = $4,
            client_document = $5,
            client_address = $6,
            client_phone = $7,
            client_email = $8,
            items = $9::jsonb,
            discounts = $10::jsonb,
            payment = $11::jsonb,
            notes = $12,
            signature_data_url = COALESCE($13, signature_data_url),
            subtotal = $14,
            discount_total = $15,
            total = $16,
            status = $17,
            updated_at = NOW()
        WHERE id = $1::uuid
          AND company_id = $2::uuid
          AND panel_type = $3
        RETURNING *
        """,
        quote_id,
        company_id,
        _panel(panel_type),
        payload.client_name,
        payload.client_document,
        payload.client_address,
        payload.client_phone,
        payload.client_email,
        json.dumps(items, ensure_ascii=False),
        json.dumps(discounts, ensure_ascii=False),
        json.dumps(payment, ensure_ascii=False),
        payload.notes,
        signature,
        subtotal,
        discount_total,
        total,
        status_value,
    )



@router.get("/companies/{company_id}/summary")
async def get_quotes_summary(
    company_id: uuid.UUID,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        await _require_quotes_enabled(conn, company_id, panel_type)

        if _is_cross_panel_quotes_021f(panel_type):
            row = await conn.fetchrow(
                """
                SELECT
                  COUNT(*) FILTER (WHERE status <> 'archived') AS active_count,
                  COALESCE(SUM(total) FILTER (WHERE status <> 'archived'), 0) AS total_amount,
                  MAX(created_at) AS last_created_at
                FROM mini_panel_quotes
                WHERE company_id = $1::uuid
                """,
                company_id,
            )

            latest = await conn.fetchrow(
                """
                SELECT *
                FROM mini_panel_quotes
                WHERE company_id = $1::uuid
                  AND status <> 'archived'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                company_id,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT
                  COUNT(*) FILTER (WHERE status <> 'archived') AS active_count,
                  COALESCE(SUM(total) FILTER (WHERE status <> 'archived'), 0) AS total_amount,
                  MAX(created_at) AS last_created_at
                FROM mini_panel_quotes
                WHERE company_id = $1::uuid
                  AND panel_type = $2
                """,
                company_id,
                _panel(panel_type),
            )

            latest = await conn.fetchrow(
                """
                SELECT *
                FROM mini_panel_quotes
                WHERE company_id = $1::uuid
                  AND panel_type = $2
                  AND status <> 'archived'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                company_id,
                _panel(panel_type),
            )

        return {
            "active_count": int(row["active_count"] or 0) if row else 0,
            "total_amount": _money(row["total_amount"] if row else 0),
            "latest": _quote_payload(latest) if latest else None,
            "panel_scope": _quote_panel_for_action_021f(panel_type),
        }
    finally:
        await conn.close()


@router.get("/companies/{company_id}")
async def list_quotes(
    company_id: uuid.UUID,
    panel_type: str = Query("sales"),
    q: str | None = Query(default=None),
    include_archived: bool = Query(False),
    document_type: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        await _require_quotes_enabled(conn, company_id, panel_type)

        query = f"%{_clean_text(q, 120)}%"
        status_filter = "" if include_archived else "AND status <> 'archived'"

        doc = _norm(document_type or "")
        document_filter = ""
        if doc in {"account", "accounts", "cuenta", "cuentas", "cuenta_cobro", "cuentas_cobro", "cobro", "cb"}:
            document_filter = "AND status = 'converted'"
        elif doc in {"quote", "quotes", "cotizacion", "cotizaciones", "cotizar", "ct", "cot"}:
            document_filter = "AND status <> 'converted'"

        # CLONEXA_021G_R1_CROSS_PANEL_LIST_500_FIX_START
        # En modo universal/cross-panel NO se puede dejar un placeholder SQL $2 sin tipo
        # y luego usar $3 para la busqueda. asyncpg rompe con:
        # "could not determine data type of parameter $2".
        if _is_cross_panel_quotes_021f(panel_type):
            rows = await conn.fetch(
                f"""
                SELECT *
                FROM mini_panel_quotes
                WHERE company_id = $1::uuid
                  {status_filter}
                  {document_filter}
                  AND (
                    $2::text = '%%'
                    OR client_name ILIKE $2::text
                    OR quote_number ILIKE $2::text
                    OR ('CB-' || regexp_replace(quote_number, '^(COT-|CT-|CB-)', '')) ILIKE $2::text
                    OR client_document ILIKE $2::text
                    OR client_email ILIKE $2::text
                    OR CASE WHEN status = 'converted' THEN 'cuenta de cobro' ELSE 'cotizacion' END ILIKE $2::text
                  )
                ORDER BY created_at DESC
                LIMIT 100
                """,
                company_id,
                query,
            )
        else:
            rows = await conn.fetch(
                f"""
                SELECT *
                FROM mini_panel_quotes
                WHERE company_id = $1::uuid
                  AND panel_type = $2::text
                  {status_filter}
                  {document_filter}
                  AND (
                    $3::text = '%%'
                    OR client_name ILIKE $3::text
                    OR quote_number ILIKE $3::text
                    OR ('CB-' || regexp_replace(quote_number, '^(COT-|CT-|CB-)', '')) ILIKE $3::text
                    OR client_document ILIKE $3::text
                    OR client_email ILIKE $3::text
                    OR CASE WHEN status = 'converted' THEN 'cuenta de cobro' ELSE 'cotizacion' END ILIKE $3::text
                  )
                ORDER BY created_at DESC
                LIMIT 100
                """,
                company_id,
                _panel(panel_type),
                query,
            )
        # CLONEXA_021G_R1_CROSS_PANEL_LIST_500_FIX_END

        payload = [_quote_payload(row) for row in rows]
        return {
            "items": payload,
            "quotes": payload,
            "panel_scope": _quote_panel_for_action_021f(panel_type),
        }
    finally:
        await conn.close()


@router.get("/companies/{company_id}/{quote_id}")
async def get_quote(
    company_id: uuid.UUID,
    quote_id: uuid.UUID,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        await _require_quotes_enabled(conn, company_id, panel_type)

        if _is_cross_panel_quotes_021f(panel_type):
            row = await conn.fetchrow(
                """
                SELECT *
                FROM mini_panel_quotes
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                LIMIT 1
                """,
                quote_id,
                company_id,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM mini_panel_quotes
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                  AND panel_type = $3
                LIMIT 1
                """,
                quote_id,
                company_id,
                _panel(panel_type),
            )

        if not row:
            raise HTTPException(status_code=404, detail="Cotizacion no encontrada.")
        return {"quote": _quote_payload(row)}
    finally:
        await conn.close()

@router.post("/companies/{company_id}", status_code=status.HTTP_201_CREATED)
async def create_quote(
    company_id: uuid.UUID,
    payload: MiniPanelQuoteCreate,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        user = await _require_access(conn, company_id, authorization)
        await _require_quotes_enabled(conn, company_id, panel_type)
        row = await _insert_or_update_quote(conn, company_id, panel_type, payload, user)
        return {"ok": True, "quote": _quote_payload(row)}
    finally:
        await conn.close()


@router.patch("/companies/{company_id}/{quote_id}")
async def update_quote(
    company_id: uuid.UUID,
    quote_id: uuid.UUID,
    payload: MiniPanelQuoteUpdate,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        user = await _require_access(conn, company_id, authorization)
        await _require_quotes_enabled(conn, company_id, panel_type)
        existing = await conn.fetchrow(
            """
            SELECT *
            FROM mini_panel_quotes
            WHERE id = $1::uuid
              AND company_id = $2::uuid
              AND panel_type = $3
            LIMIT 1
            """,
            quote_id,
            company_id,
            _panel(panel_type),
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Cotizacion no encontrada.")
        row = await _insert_or_update_quote(conn, company_id, panel_type, payload, user, quote_id=quote_id)
        return {"ok": True, "quote": _quote_payload(row)}
    finally:
        await conn.close()



@router.post("/companies/{company_id}/{quote_id}/archive")
async def archive_quote(
    company_id: uuid.UUID,
    quote_id: uuid.UUID,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        await _require_quotes_enabled(conn, company_id, panel_type)

        # CLONEXA_021G_R1_CROSS_PANEL_ARCHIVE_500_FIX_START
        if _is_cross_panel_quotes_021f(panel_type):
            row = await conn.fetchrow(
                """
                UPDATE mini_panel_quotes
                SET status = 'archived',
                    archived_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                RETURNING *
                """,
                quote_id,
                company_id,
            )
        else:
            row = await conn.fetchrow(
                """
                UPDATE mini_panel_quotes
                SET status = 'archived',
                    archived_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                  AND panel_type = $3::text
                RETURNING *
                """,
                quote_id,
                company_id,
                _panel(panel_type),
            )
        # CLONEXA_021G_R1_CROSS_PANEL_ARCHIVE_500_FIX_END

        if not row:
            raise HTTPException(status_code=404, detail="Cotizacion no encontrada.")
        return {"ok": True, "quote": _quote_payload(row)}
    finally:
        await conn.close()


@router.post("/companies/{company_id}/{quote_id}/convert")
async def convert_quote(
    company_id: uuid.UUID,
    quote_id: uuid.UUID,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        await _require_quotes_enabled(conn, company_id, panel_type)

        # CLONEXA_021G_R1_CROSS_PANEL_CONVERT_500_FIX_START
        if _is_cross_panel_quotes_021f(panel_type):
            row = await conn.fetchrow(
                """
                UPDATE mini_panel_quotes
                SET status = 'converted',
                    converted_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                  AND status <> 'archived'
                RETURNING *
                """,
                quote_id,
                company_id,
            )
        else:
            row = await conn.fetchrow(
                """
                UPDATE mini_panel_quotes
                SET status = 'converted',
                    converted_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                  AND panel_type = $3::text
                  AND status <> 'archived'
                RETURNING *
                """,
                quote_id,
                company_id,
                _panel(panel_type),
            )
        # CLONEXA_021G_R1_CROSS_PANEL_CONVERT_500_FIX_END

        if not row:
            raise HTTPException(status_code=404, detail="Cotizacion no encontrada.")
        return {"ok": True, "quote": _quote_payload(row)}
    finally:
        await conn.close()


def _load_image_reader(source: str):
    if not source:
        return None

    try:
        from reportlab.lib.utils import ImageReader
    except Exception:
        return None

    raw = str(source or "").strip()
    if not raw:
        return None

    try:
        if raw.startswith("data:image/"):
            encoded = raw.split(",", 1)[1]
            return ImageReader(io.BytesIO(base64.b64decode(encoded)))

        # CLONEXA_021C_RAW_BASE64_IMAGE_SUPPORT_START
        if len(raw) > 300 and not raw.startswith(("http://", "https://", "/")):
            try:
                return ImageReader(io.BytesIO(base64.b64decode(raw)))
            except Exception:
                pass
        # CLONEXA_021C_RAW_BASE64_IMAGE_SUPPORT_END

        if raw.startswith("/"):
            base_url = str(os.getenv("PUBLIC_BASE_URL") or os.getenv("APP_PUBLIC_URL") or "").strip().rstrip("/")
            if base_url:
                raw = base_url + raw

        if raw.startswith("http://") or raw.startswith("https://"):
            import urllib.request

            with urllib.request.urlopen(raw, timeout=8) as response:
                return ImageReader(io.BytesIO(response.read()))

        if os.path.exists(raw):
            return ImageReader(raw)
    except Exception:
        return None

    return None


def _format_cop(value: Any) -> str:
    number = int(round(_money(value)))
    return "$ " + f"{number:,}".replace(",", ".")


def _signature_reader(signature_data_url: str):
    return _load_image_reader(signature_data_url)


def _document_type_for_pdf(requested: str | None, quote: dict[str, Any]) -> str:
    doc = _norm(requested or "")
    if doc in {"account", "accounts", "cuenta", "cuenta_cobro", "cobro", "cb"}:
        return "account"
    if doc in {"quote", "quotes", "cotizacion", "cotizaciones", "ct", "cot"}:
        return "quote"
    return "account" if str(quote.get("status") or "").lower() == "converted" else "quote"


def _document_number_for_pdf(quote: dict[str, Any], document_type: str) -> str:
    if document_type == "account":
        return _account_number_from_quote_number(quote.get("quote_number") or quote.get("document_number"))
    return _quote_number_for_account_base(quote.get("quote_number") or quote.get("document_number")) or str(quote.get("quote_number") or "")


def _company_logo_url(company: dict[str, Any]) -> str:
    settings = _json(company.get("settings_json"), {})
    company_settings = _json(company.get("company_settings_json"), {})
    branding_row = _json(company.get("company_branding_row"), {})

    # CLONEXA_021C_COMPANY_LOGO_URL_SOURCES_START
    branding_candidates = [
        company.get("branding"),
        company.get("company_branding"),
        company.get("branding_json"),
        branding_row,
        settings.get("branding") if isinstance(settings, dict) else None,
        settings.get("company_branding") if isinstance(settings, dict) else None,
        (settings.get("experience") or {}).get("branding")
        if isinstance(settings, dict) and isinstance(settings.get("experience"), dict)
        else None,
        company_settings.get("branding") if isinstance(company_settings, dict) else None,
        company_settings.get("company_branding") if isinstance(company_settings, dict) else None,
        (company_settings.get("experience") or {}).get("branding")
        if isinstance(company_settings, dict) and isinstance(company_settings.get("experience"), dict)
        else None,
    ]

    logo_keys = ("logo_url", "logo", "brand_logo_url", "logo_data_url", "logo_base64", "image_url", "avatar_url")
    for candidate in branding_candidates:
        if isinstance(candidate, dict):
            for key in logo_keys:
                logo = str(candidate.get(key) or "").strip()
                if logo:
                    return logo

    for key in logo_keys:
        logo = str(company.get(key) or "").strip()
        if logo:
            return logo

    return ""
    # CLONEXA_021C_COMPANY_LOGO_URL_SOURCES_END


def _build_quote_pdf(quote: dict[str, Any], company: dict[str, Any], document_type: str = "quote") -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Motor PDF no disponible. Falta instalar reportlab: {exc}",
        )

    document_type = "account" if document_type == "account" else "quote"
    is_account = document_type == "account"
    document_title = "CUENTA DE COBRO" if is_account else "COTIZACIÓN"
    document_subtitle = "Cuenta de cobro generada desde CLONEXA" if is_account else "Cotización comercial emitida desde CLONEXA"
    document_number = _document_number_for_pdf(quote, document_type)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    margin = 42
    y = height - margin

    company_name = str(company.get("name") or company.get("slug") or "CLONEXA")
    logo_url = _company_logo_url(company)
    logo = _load_image_reader(logo_url)

    def draw_watermark() -> None:
        if logo is None:
            return

        c.saveState()
        try:
            c.setFillAlpha(0.055)
            c.setStrokeAlpha(0.04)
        except Exception:
            pass

        try:
            c.drawImage(
                logo,
                width / 2 - 170,
                height / 2 - 128,
                width=340,
                height=256,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass
        c.restoreState()

    def draw_header() -> None:
        nonlocal y
        draw_watermark()
        c.setFillColor(colors.HexColor("#141428"))
        c.rect(0, height - 112, width, 112, fill=1, stroke=0)

        if logo is not None:
            try:
                c.drawImage(logo, margin, height - 94, width=78, height=58, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass

        text_x = margin + 94 if logo is not None else margin
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(text_x, height - 50, company_name[:44])
        c.setFont("Helvetica", 9)
        c.drawString(text_x, height - 69, document_subtitle)

        c.setFillColor(colors.HexColor("#ff2ebd"))
        c.setFont("Helvetica-Bold", 18)
        c.drawRightString(width - margin, height - 48, document_title)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(width - margin, height - 68, document_number)
        c.setFont("Helvetica", 9)
        created = str(quote.get("created_at") or "")[:10]
        c.drawRightString(width - margin, height - 84, f"Fecha: {created}")

        y = height - 140

    def draw_label_value(label: str, value: str, x: float, yy: float, w: float) -> None:
        c.setFillColor(colors.HexColor("#6b6b82"))
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x, yy, label.upper())
        c.setFillColor(colors.HexColor("#17172d"))
        c.setFont("Helvetica", 9)
        safe = str(value or "-")[:90]
        c.drawString(x, yy - 13, safe)

    def draw_wrapped(text: str, x: float, yy: float, max_width: float, font: str = "Helvetica", size: int = 8) -> float:
        c.setFont(font, size)
        words = str(text or "").split()
        line = ""
        yline = yy
        for word in words:
            candidate = f"{line} {word}".strip()
            if stringWidth(candidate, font, size) <= max_width:
                line = candidate
            else:
                c.drawString(x, yline, line)
                yline -= size + 3
                line = word
        if line:
            c.drawString(x, yline, line)
            yline -= size + 3
        return yline

    draw_header()

    c.setFillColor(colors.HexColor("#f3f4ff"))
    c.roundRect(margin, y - 84, width - margin * 2, 74, 10, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#17172d"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin + 14, y - 24, "Datos del cliente")
    draw_label_value("Nombre / razón social", quote.get("client_name", ""), margin + 14, y - 44, 210)
    draw_label_value("CC / NIT", quote.get("client_document", ""), margin + 238, y - 44, 90)
    draw_label_value("Teléfono", quote.get("client_phone", ""), margin + 348, y - 44, 95)
    draw_label_value("Correo", quote.get("client_email", ""), margin + 455, y - 44, 120)
    draw_label_value("Dirección", quote.get("client_address", ""), margin + 14, y - 70, 500)
    y -= 112

    c.setFillColor(colors.HexColor("#17172d"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Conceptos")
    y -= 20

    col_x = [margin, margin + 285, margin + 350, margin + 445]
    c.setFillColor(colors.HexColor("#242442"))
    c.roundRect(margin, y - 18, width - margin * 2, 22, 6, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(col_x[0] + 8, y - 10, "Detalle")
    c.drawString(col_x[1], y - 10, "Cant.")
    c.drawString(col_x[2], y - 10, "Valor unit.")
    c.drawString(col_x[3], y - 10, "Total")
    y -= 30

    c.setFillColor(colors.HexColor("#17172d"))
    for item in quote.get("items") or []:
        if y < 150:
            c.showPage()
            draw_header()
        start_y = y
        y_after = draw_wrapped(str(item.get("description") or ""), col_x[0] + 8, y, 260, size=8)
        c.setFont("Helvetica", 8)
        c.drawString(col_x[1], start_y, str(item.get("quantity") or 0))
        c.drawRightString(col_x[2] + 72, start_y, _format_cop(item.get("unit_price")))
        c.drawRightString(width - margin - 8, start_y, _format_cop(item.get("total")))
        y = min(y_after, start_y - 18)
        c.setStrokeColor(colors.HexColor("#e1e1ef"))
        c.line(margin, y + 8, width - margin, y + 8)
        y -= 4

    y -= 8
    totals_x = width - margin - 220
    c.setFillColor(colors.HexColor("#17172d"))
    c.setFont("Helvetica", 9)
    c.drawRightString(totals_x + 120, y, "Subtotal")
    c.drawRightString(width - margin, y, _format_cop(quote.get("subtotal")))
    y -= 18

    for discount in quote.get("discounts") or []:
        c.setFillColor(colors.HexColor("#7c2d12"))
        c.drawRightString(totals_x + 120, y, f"Descuento {discount.get('name') or ''}"[:28])
        c.drawRightString(width - margin, y, "- " + _format_cop(discount.get("value")))
        y -= 16

    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(totals_x + 120, y - 4, "TOTAL")
    c.setFillColor(colors.HexColor("#ff2ebd"))
    c.drawRightString(width - margin, y - 4, _format_cop(quote.get("total")))
    y -= 48

    if y < 170:
        c.showPage()
        draw_header()

    c.setFillColor(colors.HexColor("#f3f4ff"))
    c.roundRect(margin, y - 94, width - margin * 2, 82, 10, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#17172d"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin + 14, y - 28, "Detalles de pago")
    payment = quote.get("payment") or {}
    c.setFont("Helvetica", 9)
    c.drawString(margin + 14, y - 46, f"Detalle: {payment.get('detail') or '-'}")
    c.drawString(margin + 14, y - 62, f"Nombre: {payment.get('name') or '-'}")
    c.drawString(margin + 260, y - 62, f"Forma: {payment.get('method') or '-'}")
    c.drawString(margin + 14, y - 78, f"Datos: {payment.get('data') or '-'}")
    y -= 118

    if quote.get("notes"):
        c.setFillColor(colors.HexColor("#17172d"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, "Observaciones")
        y = draw_wrapped(quote.get("notes") or "", margin, y - 16, width - margin * 2, size=8)
        y -= 18

    c.setStrokeColor(colors.HexColor("#d1d5db"))
    c.line(margin, 92, margin + 190, 92)
    c.setFillColor(colors.HexColor("#17172d"))
    c.setFont("Helvetica", 8)
    c.drawString(margin, 78, "Firma / recibido")

    sig = _signature_reader(quote.get("signature_data_url") or "")
    if sig is not None:
        try:
            c.drawImage(sig, margin, 98, width=175, height=55, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    c.setFillColor(colors.HexColor("#6b6b82"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(width / 2, 30, f"{document_title} generado por CLONEXA · Mini Panel Ventas")
    c.save()
    buffer.seek(0)
    return buffer.getvalue()



@router.get("/companies/{company_id}/{quote_id}/pdf")
async def quote_pdf(
    company_id: uuid.UUID,
    quote_id: uuid.UUID,
    panel_type: str = Query("sales"),
    document_type: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> Response:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        await _require_quotes_enabled(conn, company_id, panel_type)

        if _is_cross_panel_quotes_021f(panel_type):
            row = await conn.fetchrow(
                """
                SELECT *
                FROM mini_panel_quotes
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                LIMIT 1
                """,
                quote_id,
                company_id,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM mini_panel_quotes
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                  AND panel_type = $3
                LIMIT 1
                """,
                quote_id,
                company_id,
                _panel(panel_type),
            )

        if not row:
            raise HTTPException(status_code=404, detail="Cotizacion no encontrada.")

        company = await _company_profile(conn, company_id)
        quote = _quote_payload(row)
        doc_type = _document_type_for_pdf(document_type, quote)
        pdf = _build_quote_pdf(quote, company, doc_type)
        filename = f"{_document_number_for_pdf(quote, doc_type)}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        await conn.close()

# CLONEXA_021C_PDF_LEGACY_AMP_ROUTE_START
@router.get("/companies/{company_id}/{quote_id}/pdf&document_type={document_type_value}")
async def quote_pdf_legacy_amp_document_type(
    company_id: uuid.UUID,
    quote_id: uuid.UUID,
    document_type_value: str,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> Response:
    # Compatibilidad defensiva para URLs antiguas generadas como:
    # /pdf&document_type=account?panel_type=sales
    # La ruta correcta es:
    # /pdf?document_type=account&panel_type=sales
    return await quote_pdf(
        company_id=company_id,
        quote_id=quote_id,
        panel_type=panel_type,
        document_type=document_type_value,
        authorization=authorization,
    )
# CLONEXA_021C_PDF_LEGACY_AMP_ROUTE_END

