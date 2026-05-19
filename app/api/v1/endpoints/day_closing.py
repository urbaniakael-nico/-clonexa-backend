from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

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


class DayClosingSubmitIn(BaseModel):
    closure_date: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=3000)
    connection_snapshot: dict[str, Any] | None = Field(default=None)


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


def _area(panel_type: Any) -> str:
    panel = _panel(panel_type)
    if panel == "sales":
        return "ventas"
    if panel == "stores":
        return "tiendas"
    return panel or "operacion"


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


def _parse_closure_date(value: Any) -> date:
    raw = _clean(value)
    if not raw:
        return datetime.now(timezone.utc).date()
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        raise HTTPException(status_code=422, detail="closure_date debe tener formato YYYY-MM-DD.")


def _date_bounds(value: date, timezone_name: str = "America/Bogota") -> tuple[datetime, datetime]:
    try:
        local_tz = ZoneInfo(timezone_name or "America/Bogota")
    except Exception:
        local_tz = ZoneInfo("America/Bogota")
    start_local = datetime.combine(value, time.min, tzinfo=local_tz)
    end_local = datetime.combine(value, time.max, tzinfo=local_tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def _company_timezone(conn: asyncpg.Connection, company_id: uuid.UUID) -> str:
    try:
        value = await conn.fetchval(
            "SELECT COALESCE(NULLIF(timezone, ''), 'America/Bogota') FROM companies WHERE id = $1::uuid LIMIT 1",
            company_id,
        )
        return _clean(value) or "America/Bogota"
    except Exception:
        return "America/Bogota"


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


def _access_user_id(access: dict[str, Any] | None) -> uuid.UUID | None:
    if not isinstance(access, dict):
        return None
    raw = access.get("user_id") or access.get("sub") or access.get("id")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except Exception:
        return None


def _access_label(access: dict[str, Any] | None) -> str:
    if not isinstance(access, dict):
        return ""
    return _clean(access.get("full_name") or access.get("email") or "Usuario mini panel")


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}"))


async def _column_exists(conn: asyncpg.Connection, table_name: str, column_name: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = $1
              AND column_name = $2
            LIMIT 1
            """,
            table_name,
            column_name,
        )
    )


async def _ensure_storage(conn: asyncpg.Connection) -> None:
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_closures (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            panel_type VARCHAR(50) NOT NULL DEFAULT 'sales',
            area VARCHAR(80) NOT NULL DEFAULT 'ventas',
            closure_date DATE NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'submitted',
            submitted_by UUID NULL,
            submitted_by_label VARCHAR(180),
            submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sales_count INTEGER NOT NULL DEFAULT 0,
            invoices_count INTEGER NOT NULL DEFAULT 0,
            units_sold NUMERIC(14, 2) NOT NULL DEFAULT 0,
            total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            cash_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            transfer_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            check_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            other_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            quotes_count INTEGER NOT NULL DEFAULT 0,
            quotes_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            requests_count INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            connection_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            users_summary JSONB NOT NULL DEFAULT '[]'::jsonb,
            snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, panel_type, closure_date)
        );
        """
    )
    # Column-safe evolution if a previous table existed with fewer fields.
    for ddl in [
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS area VARCHAR(80) NOT NULL DEFAULT 'ventas';",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW();",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS sales_count INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS invoices_count INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS units_sold NUMERIC(14, 2) NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS cash_amount NUMERIC(14, 2) NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS transfer_amount NUMERIC(14, 2) NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS check_amount NUMERIC(14, 2) NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS other_amount NUMERIC(14, 2) NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS quotes_count INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS quotes_amount NUMERIC(14, 2) NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS requests_count INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS connection_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS users_summary JSONB NOT NULL DEFAULT '[]'::jsonb;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb;",
        "ALTER TABLE daily_closures ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();",
    ]:
        await conn.execute(ddl)
    await conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_daily_closures_company_panel_date
        ON daily_closures (company_id, panel_type, closure_date);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_daily_closures_company_date
        ON daily_closures (company_id, closure_date DESC);
        """
    )


def _empty_user(label: str = "Sin usuario", user_id: str = "") -> dict[str, Any]:
    return {
        "user_id": user_id,
        "label": label or "Sin usuario",
        "username": "",
        "email": "",
        "sales_count": 0,
        "invoices_count": 0,
        "units_sold": 0.0,
        "total_amount": 0.0,
        "cash_amount": 0.0,
        "transfer_amount": 0.0,
        "check_amount": 0.0,
        "other_amount": 0.0,
        "quotes_count": 0,
        "quotes_amount": 0.0,
        "requests_count": 0,
    }


def _user_key(user_id: Any, label: Any) -> str:
    raw = _clean(user_id)
    if raw:
        return raw
    return f"label::{_clean(label).lower() or 'sin_usuario'}"


def _merge_user(users: dict[str, dict[str, Any]], user_id: Any, label: Any) -> dict[str, Any]:
    key = _user_key(user_id, label)
    if key not in users:
        users[key] = _empty_user(_clean(label) or "Sin usuario", _clean(user_id))
    return users[key]


async def _sales_rows(
    conn: asyncpg.Connection,
    company_id: uuid.UUID,
    panel_type: str,
    start_at: datetime,
    end_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not await _table_exists(conn, "mini_panel_sales_records"):
        return [], {}

    rows = await conn.fetch(
        """
        SELECT
            COALESCE(s.created_by::text, '') AS user_id,
            COALESCE(
                NULLIF(s.created_by_label, ''),
                NULLIF(cu.full_name, ''),
                NULLIF(cu.email, ''),
                'Sin usuario'
            ) AS label,
            COUNT(*)::int AS invoices_count,
            COUNT(*)::int AS sales_count,
            COALESCE(SUM(s.quantity), 0)::float AS units_sold,
            COALESCE(SUM(s.total), 0)::float AS total_amount,
            COALESCE(SUM(CASE WHEN lower(COALESCE(s.payment_method, '')) IN ('efectivo', 'cash') THEN s.total ELSE 0 END), 0)::float AS cash_amount,
            COALESCE(SUM(CASE WHEN lower(COALESCE(s.payment_method, '')) IN ('transferencia', 'transfer', 'bank_transfer') THEN s.total ELSE 0 END), 0)::float AS transfer_amount,
            COALESCE(SUM(CASE WHEN lower(COALESCE(s.payment_method, '')) IN ('cheque', 'check') THEN s.total ELSE 0 END), 0)::float AS check_amount,
            COALESCE(SUM(CASE WHEN lower(COALESCE(s.payment_method, '')) NOT IN ('efectivo', 'cash', 'transferencia', 'transfer', 'bank_transfer', 'cheque', 'check') THEN s.total ELSE 0 END), 0)::float AS other_amount
        FROM mini_panel_sales_records s
        LEFT JOIN company_users cu
          ON cu.id = s.created_by
         AND cu.company_id = s.company_id
        WHERE s.company_id = $1::uuid
          AND s.panel_type = $2
          AND s.created_at >= $3
          AND s.created_at <= $4
          AND COALESCE(s.status, '') <> 'archived'
        GROUP BY s.created_by, s.created_by_label, cu.full_name, cu.email
        ORDER BY total_amount DESC, label ASC
        """,
        company_id,
        panel_type,
        start_at,
        end_at,
    )

    items = [dict(row) for row in rows]
    totals = {
        "sales_count": sum(int(row.get("sales_count") or 0) for row in items),
        "invoices_count": sum(int(row.get("invoices_count") or 0) for row in items),
        "units_sold": round(sum(_money(row.get("units_sold")) for row in items), 2),
        "total_amount": round(sum(_money(row.get("total_amount")) for row in items), 2),
        "cash_amount": round(sum(_money(row.get("cash_amount")) for row in items), 2),
        "transfer_amount": round(sum(_money(row.get("transfer_amount")) for row in items), 2),
        "check_amount": round(sum(_money(row.get("check_amount")) for row in items), 2),
        "other_amount": round(sum(_money(row.get("other_amount")) for row in items), 2),
    }
    return items, totals


async def _quote_rows(
    conn: asyncpg.Connection,
    company_id: uuid.UUID,
    panel_type: str,
    start_at: datetime,
    end_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not await _table_exists(conn, "mini_panel_quotes"):
        return [], {}

    rows = await conn.fetch(
        """
        SELECT
            COALESCE(q.created_by::text, '') AS user_id,
            COALESCE(
                NULLIF(q.created_by_label, ''),
                NULLIF(cu.full_name, ''),
                NULLIF(cu.email, ''),
                'Sin usuario'
            ) AS label,
            COUNT(*)::int AS quotes_count,
            COALESCE(SUM(q.total), 0)::float AS quotes_amount
        FROM mini_panel_quotes q
        LEFT JOIN company_users cu
          ON cu.id = q.created_by
         AND cu.company_id = q.company_id
        WHERE q.company_id = $1::uuid
          AND q.panel_type = $2
          AND q.created_at >= $3
          AND q.created_at <= $4
          AND COALESCE(q.status, '') <> 'archived'
        GROUP BY q.created_by, q.created_by_label, cu.full_name, cu.email
        ORDER BY quotes_amount DESC, label ASC
        """,
        company_id,
        panel_type,
        start_at,
        end_at,
    )

    items = [dict(row) for row in rows]
    totals = {
        "quotes_count": sum(int(row.get("quotes_count") or 0) for row in items),
        "quotes_amount": round(sum(_money(row.get("quotes_amount")) for row in items), 2),
    }
    return items, totals


async def _request_rows(
    conn: asyncpg.Connection,
    company_id: uuid.UUID,
    panel_type: str,
    start_at: datetime,
    end_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Requests todavía puede no existir. Se detecta de forma defensiva para no romper cierre diario.
    candidate_tables = ["mini_panel_requests", "store_requests", "requests", "company_requests"]
    for table in candidate_tables:
        if not await _table_exists(conn, table):
            continue

        has_company = await _column_exists(conn, table, "company_id")
        has_created = await _column_exists(conn, table, "created_at")
        if not has_company or not has_created:
            continue

        has_panel = await _column_exists(conn, table, "panel_type")
        has_created_by = await _column_exists(conn, table, "created_by")
        has_label = await _column_exists(conn, table, "created_by_label")

        user_expr = "COALESCE(created_by::text, '')" if has_created_by else "''"
        label_expr = "COALESCE(NULLIF(created_by_label, ''), 'Sin usuario')" if has_label else "'Sin usuario'"

        if has_panel:
            rows = await conn.fetch(
                f"""
                SELECT
                    {user_expr} AS user_id,
                    {label_expr} AS label,
                    COUNT(*)::int AS requests_count
                FROM {table}
                WHERE company_id = $1::uuid
                  AND panel_type = $2
                  AND created_at >= $3
                  AND created_at <= $4
                GROUP BY user_id, label
                ORDER BY requests_count DESC, label ASC
                """,
                company_id,
                panel_type,
                start_at,
                end_at,
            )
        else:
            rows = await conn.fetch(
                f"""
                SELECT
                    {user_expr} AS user_id,
                    {label_expr} AS label,
                    COUNT(*)::int AS requests_count
                FROM {table}
                WHERE company_id = $1::uuid
                  AND created_at >= $2
                  AND created_at <= $3
                GROUP BY user_id, label
                ORDER BY requests_count DESC, label ASC
                """,
                company_id,
                start_at,
                end_at,
            )
        items = [dict(row) for row in rows]
        return items, {"requests_count": sum(int(row.get("requests_count") or 0) for row in items)}

    return [], {"requests_count": 0}


def _closure_payload(row: asyncpg.Record | dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    return {
        "id": str(data.get("id") or ""),
        "company_id": str(data.get("company_id") or ""),
        "panel_type": _clean(data.get("panel_type")),
        "area": _clean(data.get("area")),
        "closure_date": data.get("closure_date").isoformat() if hasattr(data.get("closure_date"), "isoformat") else _clean(data.get("closure_date")),
        "status": _clean(data.get("status") or "submitted"),
        "submitted_by": str(data.get("submitted_by") or "") if data.get("submitted_by") else "",
        "submitted_by_label": _clean(data.get("submitted_by_label")),
        "submitted_at": data.get("submitted_at").isoformat() if hasattr(data.get("submitted_at"), "isoformat") else _clean(data.get("submitted_at")),
        "notes": _clean(data.get("notes")),
        "totals": {
            "sales_count": int(data.get("sales_count") or 0),
            "invoices_count": int(data.get("invoices_count") or 0),
            "units_sold": _money(data.get("units_sold")),
            "total_amount": _money(data.get("total_amount")),
            "cash_amount": _money(data.get("cash_amount")),
            "transfer_amount": _money(data.get("transfer_amount")),
            "check_amount": _money(data.get("check_amount")),
            "other_amount": _money(data.get("other_amount")),
            "quotes_count": int(data.get("quotes_count") or 0),
            "quotes_amount": _money(data.get("quotes_amount")),
            "requests_count": int(data.get("requests_count") or 0),
        },
        "connection_snapshot": _json(data.get("connection_snapshot"), {}),
        "users": _json(data.get("users_summary"), []),
        "snapshot": _json(data.get("snapshot_json"), {}),
    }


async def _build_summary(
    conn: asyncpg.Connection,
    company_id: uuid.UUID,
    panel_type: str,
    closure_date_value: date,
) -> dict[str, Any]:
    await _ensure_storage(conn)
    panel = _panel(panel_type)
    area = _area(panel)
    timezone_name = await _company_timezone(conn, company_id)
    start_at, end_at = _date_bounds(closure_date_value, timezone_name)

    existing = await conn.fetchrow(
        """
        SELECT *
        FROM daily_closures
        WHERE company_id = $1::uuid
          AND panel_type = $2
          AND closure_date = $3
        LIMIT 1
        """,
        company_id,
        panel,
        closure_date_value,
    )

    if existing:
        payload = _closure_payload(existing) or {}
        return {
            "company_id": str(company_id),
            "panel_type": panel,
            "area": area,
            "closure_date": closure_date_value.isoformat(),
            "status": payload.get("status") or "submitted",
            "locked": True,
            "submitted_at": payload.get("submitted_at"),
            "submitted_by_label": payload.get("submitted_by_label"),
            "notes": payload.get("notes"),
            "totals": payload.get("totals") or {},
            "users": payload.get("users") or [],
            "connection_snapshot": payload.get("connection_snapshot") or {},
            "timezone": timezone_name,
            "closure": payload,
        }

    users: dict[str, dict[str, Any]] = {}

    sales_rows, sales_totals = await _sales_rows(conn, company_id, panel, start_at, end_at)
    for row in sales_rows:
        user = _merge_user(users, row.get("user_id"), row.get("label"))
        for key in ["sales_count", "invoices_count"]:
            user[key] += int(row.get(key) or 0)
        for key in ["units_sold", "total_amount", "cash_amount", "transfer_amount", "check_amount", "other_amount"]:
            user[key] = round(_money(user.get(key)) + _money(row.get(key)), 2)

    quote_rows, quote_totals = await _quote_rows(conn, company_id, panel, start_at, end_at)
    for row in quote_rows:
        user = _merge_user(users, row.get("user_id"), row.get("label"))
        user["quotes_count"] += int(row.get("quotes_count") or 0)
        user["quotes_amount"] = round(_money(user.get("quotes_amount")) + _money(row.get("quotes_amount")), 2)

    request_rows, request_totals = await _request_rows(conn, company_id, panel, start_at, end_at)
    for row in request_rows:
        user = _merge_user(users, row.get("user_id"), row.get("label"))
        user["requests_count"] += int(row.get("requests_count") or 0)

    totals = {
        "sales_count": int(sales_totals.get("sales_count") or 0),
        "invoices_count": int(sales_totals.get("invoices_count") or 0),
        "units_sold": _money(sales_totals.get("units_sold")),
        "total_amount": _money(sales_totals.get("total_amount")),
        "cash_amount": _money(sales_totals.get("cash_amount")),
        "transfer_amount": _money(sales_totals.get("transfer_amount")),
        "check_amount": _money(sales_totals.get("check_amount")),
        "other_amount": _money(sales_totals.get("other_amount")),
        "quotes_count": int(quote_totals.get("quotes_count") or 0),
        "quotes_amount": _money(quote_totals.get("quotes_amount")),
        "requests_count": int(request_totals.get("requests_count") or 0),
    }

    user_rows = sorted(
        users.values(),
        key=lambda item: (_money(item.get("total_amount")), int(item.get("quotes_count") or 0), _clean(item.get("label"))),
        reverse=True,
    )

    return {
        "company_id": str(company_id),
        "panel_type": panel,
        "area": area,
        "closure_date": closure_date_value.isoformat(),
        "status": "open",
        "locked": False,
        "totals": totals,
        "users": user_rows,
        "connection_snapshot": {},
        "timezone": timezone_name,
        "closure": None,
    }


@router.get("/companies/{company_id}/mini-panel/summary")
async def mini_panel_day_closing_summary(
    company_id: uuid.UUID,
    panel_type: str = Query("sales"),
    closure_date: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        target_date = _parse_closure_date(closure_date)
        return await _build_summary(conn, company_id, panel_type, target_date)
    finally:
        await conn.close()


@router.post("/companies/{company_id}/mini-panel/submit", status_code=status.HTTP_201_CREATED)
async def submit_mini_panel_day_closing(
    company_id: uuid.UUID,
    payload: DayClosingSubmitIn,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        target_date = _parse_closure_date(payload.closure_date)
        panel = _panel(panel_type)
        area = _area(panel)

        existing = await conn.fetchrow(
            """
            SELECT *
            FROM daily_closures
            WHERE company_id = $1::uuid
              AND panel_type = $2
              AND closure_date = $3
            LIMIT 1
            """,
            company_id,
            panel,
            target_date,
        )
        if existing:
            raise HTTPException(status_code=409, detail="El cierre diario de este panel ya fue enviado.")

        summary = await _build_summary(conn, company_id, panel, target_date)
        totals = summary.get("totals") if isinstance(summary.get("totals"), dict) else {}
        users_summary = summary.get("users") if isinstance(summary.get("users"), list) else []
        submitted_by = _access_user_id(access)
        submitted_by_label = _access_label(access)
        connection_snapshot = payload.connection_snapshot if isinstance(payload.connection_snapshot, dict) else {}

        snapshot = {
            "source": "day_closing_mini_panel_023e",
            "company_id": str(company_id),
            "panel_type": panel,
            "area": area,
            "closure_date": target_date.isoformat(),
            "totals": totals,
            "users": users_summary,
            "connection_snapshot": connection_snapshot,
            "submitted_by_label": submitted_by_label,
        }

        row = await conn.fetchrow(
            """
            INSERT INTO daily_closures (
                company_id,
                panel_type,
                area,
                closure_date,
                status,
                submitted_by,
                submitted_by_label,
                submitted_at,
                sales_count,
                invoices_count,
                units_sold,
                total_amount,
                cash_amount,
                transfer_amount,
                check_amount,
                other_amount,
                quotes_count,
                quotes_amount,
                requests_count,
                notes,
                connection_snapshot,
                users_summary,
                snapshot_json,
                created_at,
                updated_at
            )
            VALUES (
                $1::uuid, $2, $3, $4, 'submitted',
                $5::uuid, $6, NOW(),
                $7, $8, $9, $10, $11, $12, $13, $14,
                $15, $16, $17, $18,
                $19::jsonb, $20::jsonb, $21::jsonb,
                NOW(), NOW()
            )
            RETURNING *
            """,
            company_id,
            panel,
            area,
            target_date,
            submitted_by,
            submitted_by_label,
            int(totals.get("sales_count") or 0),
            int(totals.get("invoices_count") or 0),
            _money(totals.get("units_sold")),
            _money(totals.get("total_amount")),
            _money(totals.get("cash_amount")),
            _money(totals.get("transfer_amount")),
            _money(totals.get("check_amount")),
            _money(totals.get("other_amount")),
            int(totals.get("quotes_count") or 0),
            _money(totals.get("quotes_amount")),
            int(totals.get("requests_count") or 0),
            _clean(payload.notes),
            json.dumps(connection_snapshot, ensure_ascii=False),
            json.dumps(users_summary, ensure_ascii=False),
            json.dumps(snapshot, ensure_ascii=False),
        )

        closure = _closure_payload(row)
        return {
            "company_id": str(company_id),
            "panel_type": panel,
            "area": area,
            "closure_date": target_date.isoformat(),
            "status": "submitted",
            "locked": True,
            "closure": closure,
            "totals": closure.get("totals") if closure else totals,
            "users": closure.get("users") if closure else users_summary,
        }
    finally:
        await conn.close()


@router.get("/companies/{company_id}/mini-panel/history")
async def mini_panel_day_closing_history(
    company_id: uuid.UUID,
    panel_type: str = Query("sales"),
    limit: int = Query(default=30, ge=1, le=200),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        panel = _panel(panel_type)
        rows = await conn.fetch(
            """
            SELECT *
            FROM daily_closures
            WHERE company_id = $1::uuid
              AND panel_type = $2
            ORDER BY closure_date DESC, submitted_at DESC
            LIMIT $3
            """,
            company_id,
            panel,
            limit,
        )
        items = [_closure_payload(row) for row in rows]
        return {
            "company_id": str(company_id),
            "panel_type": panel,
            "count": len(items),
            "items": items,
        }
    finally:
        await conn.close()
