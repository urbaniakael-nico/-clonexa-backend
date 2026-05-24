from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.api.v1.endpoints.mini_panel_sales import (
    _clean,
    _connect,
    _json,
    _norm,
    _panel,
    _require_access,
    _scope_label,
    _scope_user_id,
)


router = APIRouter()


class RequestItemIn(BaseModel):
    reference_id: str | None = Field(default=None, max_length=120)
    name: str = Field(..., max_length=220)
    sku: str | None = Field(default="", max_length=120)
    category: str | None = Field(default="", max_length=160)
    size: str | None = Field(default="", max_length=120)
    color: str | None = Field(default="", max_length=120)
    quantity: float = Field(default=1, ge=0)
    sold_quantity: float | None = Field(default=None, ge=0)
    note: str | None = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str:
        name = _clean(value)
        if not name:
            raise ValueError("El articulo es obligatorio.")
        return name[:220]


class RequestCreateIn(BaseModel):
    panel_type: str | None = Field(default=None, max_length=50)
    store_label: str | None = Field(default="", max_length=180)
    notes: str | None = Field(default="", max_length=900)
    items: list[RequestItemIn] = Field(default_factory=list)
    store_employee_id: str | None = Field(default=None, max_length=120)
    store_employee_name: str | None = Field(default=None, max_length=180)
    store_user_id: str | None = Field(default=None, max_length=120)
    store_slot_id: str | None = Field(default=None, max_length=40)
    store_slot_name: str | None = Field(default=None, max_length=120)

    @field_validator("items")
    @classmethod
    def clean_items(cls, value: list[RequestItemIn]) -> list[RequestItemIn]:
        rows = [item for item in (value or []) if _clean(item.name) and float(item.quantity or 0) > 0]
        if not rows:
            raise ValueError("Agrega al menos un articulo con cantidad.")
        return rows[:80]


class RequestUpdateIn(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    prepared_by: str | None = Field(default="", max_length=180)
    notes: str | None = Field(default=None, max_length=900)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _num(value: Any) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except Exception:
        return 0.0


def _status(value: Any) -> str:
    normalized = _norm(value or "sent")
    aliases = {
        "enviada": "sent",
        "enviado": "sent",
        "sent": "sent",
        "submitted": "sent",
        "alistando": "preparing",
        "preparing": "preparing",
        "preparando": "preparing",
        "lista": "ready",
        "listo": "ready",
        "ready": "ready",
        "recibida": "received",
        "recibido": "received",
        "received": "received",
        "archivada": "archived",
        "archivado": "archived",
        "archived": "archived",
    }
    return aliases.get(normalized, "sent")


def _status_label(value: str) -> str:
    return {
        "sent": "Enviada",
        "preparing": "Alistando",
        "ready": "Lista",
        "received": "Recibida",
        "archived": "Archivada",
    }.get(value, "Enviada")


def _timeline(status_value: str, by: str = "", note: str = "") -> list[dict[str, Any]]:
    status_clean = _status(status_value)
    return [
        {
            "status": status_clean,
            "label": _status_label(status_clean),
            "at": _now().isoformat(),
            "by": _clean(by),
            "note": _clean(note),
        }
    ]


def _append_timeline(current: Any, status_value: str, by: str = "", note: str = "") -> list[dict[str, Any]]:
    rows = _json(current, [])
    if not isinstance(rows, list):
        rows = []
    return rows + _timeline(status_value, by=by, note=note)


def _items_payload(items: list[RequestItemIn]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "reference_id": _clean(item.reference_id),
                "name": _clean(item.name),
                "sku": _clean(item.sku),
                "category": _clean(item.category),
                "size": _clean(item.size),
                "color": _clean(item.color),
                "quantity": round(_num(item.quantity), 2),
                "sold_quantity": round(_num(item.sold_quantity), 2) if item.sold_quantity is not None else 0,
                "note": _clean(item.note),
            }
        )
    return rows


async def _ensure_storage(conn: asyncpg.Connection) -> None:
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_panel_requests_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            panel_type VARCHAR(50) NOT NULL DEFAULT 'store',
            request_number VARCHAR(80) NOT NULL,
            requested_by UUID NULL,
            requested_by_label VARCHAR(180),
            store_label VARCHAR(180),
            status VARCHAR(40) NOT NULL DEFAULT 'sent',
            items JSONB NOT NULL DEFAULT '[]'::jsonb,
            notes TEXT,
            prepared_by VARCHAR(180),
            prepared_at TIMESTAMPTZ NULL,
            ready_at TIMESTAMPTZ NULL,
            received_at TIMESTAMPTZ NULL,
            archived_at TIMESTAMPTZ NULL,
            timeline JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_requests_company_status
        ON mini_panel_requests_records (company_id, status, created_at DESC);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_requests_company_panel
        ON mini_panel_requests_records (company_id, panel_type, created_at DESC);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_requests_company_user
        ON mini_panel_requests_records (company_id, requested_by, created_at DESC);
        """
    )


async def _column_exists(conn: asyncpg.Connection, table_name: str, column_name: str) -> bool:
    value = await conn.fetchval(
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
    return bool(value)


def _request_payload(row: asyncpg.Record) -> dict[str, Any]:
    items = _json(row["items"], [])
    timeline = _json(row["timeline"], [])
    metadata = _json(row["metadata"], {})
    status_value = _status(row["status"])
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "panel_type": row["panel_type"],
        "request_number": row["request_number"],
        "requested_by": str(row["requested_by"]) if row["requested_by"] else None,
        "requested_by_label": _clean(row["requested_by_label"]) or "Usuario mini panel",
        "store_label": _clean(row["store_label"]) or _clean(row["requested_by_label"]) or "Tienda",
        "status": status_value,
        "status_label": _status_label(status_value),
        "items": items if isinstance(items, list) else [],
        "items_count": len(items) if isinstance(items, list) else 0,
        "requested_units": round(sum(_num(item.get("quantity")) for item in items if isinstance(item, dict)), 2)
        if isinstance(items, list)
        else 0,
        "notes": _clean(row["notes"]),
        "prepared_by": _clean(row["prepared_by"]),
        "prepared_at": _iso(row["prepared_at"]),
        "ready_at": _iso(row["ready_at"]),
        "received_at": _iso(row["received_at"]),
        "archived_at": _iso(row["archived_at"]),
        "timeline": timeline if isinstance(timeline, list) else [],
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


async def _fetch_request(conn: asyncpg.Connection, company_id: uuid.UUID, request_id: uuid.UUID) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT *
        FROM mini_panel_requests_records
        WHERE company_id::text = $1::text
          AND id = $2::uuid
        LIMIT 1
        """,
        str(company_id),
        request_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada.")
    return row


async def _next_number(conn: asyncpg.Connection, company_id: uuid.UUID) -> str:
    count = await conn.fetchval(
        """
        SELECT COUNT(*) + 1
        FROM mini_panel_requests_records
        WHERE company_id::text = $1::text
        """,
        str(company_id),
    )
    return f"SOL-{_now().strftime('%Y%m')}-{int(count or 1):04d}"


async def _references(conn: asyncpg.Connection, company_id: uuid.UUID, limit: int = 80) -> list[dict[str, Any]]:
    table = await conn.fetchval("SELECT to_regclass('public.product_references')")
    if not table:
        return []
    cols = {
        "archived": await _column_exists(conn, "product_references", "archived"),
        "sku": await _column_exists(conn, "product_references", "sku"),
        "unit_price": await _column_exists(conn, "product_references", "unit_price"),
        "channel": await _column_exists(conn, "product_references", "channel"),
        "bot_active": await _column_exists(conn, "product_references", "bot_active"),
        "system_active": await _column_exists(conn, "product_references", "system_active"),
        "category": await _column_exists(conn, "product_references", "category"),
        "size": await _column_exists(conn, "product_references", "size"),
        "color": await _column_exists(conn, "product_references", "color"),
    }
    archived_filter = "AND COALESCE(archived, false) IS FALSE" if cols["archived"] else ""
    active_terms: list[str] = []
    if cols["system_active"]:
        active_terms.append("COALESCE(system_active, false) IS TRUE")
    if cols["bot_active"]:
        active_terms.append("COALESCE(bot_active, false) IS TRUE")
    channel_filter = f"AND ({' OR '.join(active_terms)})" if active_terms else ""
    select_category = "COALESCE(category, '')" if cols["category"] else "''"
    select_size = "COALESCE(size, '')" if cols["size"] else "''"
    select_color = "COALESCE(color, '')" if cols["color"] else "''"
    select_sku = "COALESCE(sku, '')" if cols["sku"] else "''"
    select_price = "COALESCE(unit_price, 0)" if cols["unit_price"] else "0"
    select_channel = "COALESCE(channel, '')" if cols["channel"] else "''"
    select_bot = "COALESCE(bot_active, false)" if cols["bot_active"] else "false"
    select_system = "COALESCE(system_active, false)" if cols["system_active"] else "false"
    rows = await conn.fetch(
        f"""
        SELECT id,
               name,
               {select_category} AS category,
               {select_size} AS size,
               {select_color} AS color,
               {select_sku} AS sku,
               {select_price} AS unit_price,
               {select_channel} AS channel,
               {select_bot} AS bot_active,
               {select_system} AS system_active
        FROM product_references
        WHERE company_id::text = $1::text
          {archived_filter}
          {channel_filter}
        ORDER BY created_at DESC, name ASC
        LIMIT $2
        """,
        str(company_id),
        max(10, min(int(limit or 80), 200)),
    )
    return [
        {
            "reference_id": str(row["id"]),
            "name": _clean(row["name"]),
            "category": _clean(row["category"]),
            "size": _clean(row["size"]),
            "color": _clean(row["color"]),
            "sku": _clean(row["sku"]),
            "unit_price": round(_num(row["unit_price"]), 2),
            "channel": _clean(row["channel"]),
            "bot_active": bool(row["bot_active"]),
            "system_active": bool(row["system_active"]),
        }
        for row in rows
    ]


async def _sold_items(
    conn: asyncpg.Connection,
    company_id: uuid.UUID,
    panel_type: str,
    scope_user: uuid.UUID | None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    table = await conn.fetchval("SELECT to_regclass('public.mini_panel_sales_records')")
    if not table:
        return []
    where = ["company_id = $1::uuid", "created_at >= NOW() - INTERVAL '30 days'"]
    args: list[Any] = [company_id]
    idx = 2
    panel = _panel(panel_type)
    if panel not in {"all", "client"}:
        panel_aliases = [panel]
        if panel == "stores":
            panel_aliases = ["stores", "store", "tienda", "tiendas"]
        elif panel == "sales":
            panel_aliases = ["sales", "venta", "ventas"]
        where.append(f"panel_type = ANY(${idx}::text[])")
        args.append(panel_aliases)
        idx += 1
    if scope_user and panel != "stores":
        where.append(f"(created_by = ${idx}::uuid OR metadata->'store_actor'->>'user_id' = ${idx}::text)")
        args.append(str(scope_user))
        idx += 1
    where_sql = " AND ".join(where)
    rows = await conn.fetch(
        f"""
        WITH sales_scope AS (
            SELECT *
            FROM mini_panel_sales_records
            WHERE {where_sql}
        ),
        expanded AS (
            SELECT
                COALESCE(NULLIF(item.value->>'reference_id', ''), NULLIF(s.reference_id, ''), '') AS reference_id,
                COALESCE(NULLIF(item.value->>'reference_name', ''), NULLIF(item.value->>'name', ''), NULLIF(s.reference_name, ''), 'Articulo vendido') AS reference_name,
                COALESCE(NULLIF(item.value->>'reference_category', ''), NULLIF(item.value->>'category', ''), COALESCE(s.reference_category, '')) AS category,
                COALESCE(NULLIF(item.value->>'reference_size', ''), NULLIF(item.value->>'size', ''), COALESCE(s.reference_size, '')) AS size,
                COALESCE(NULLIF(item.value->>'reference_color', ''), NULLIF(item.value->>'color', ''), COALESCE(s.reference_color, '')) AS color,
                COALESCE(NULLIF(item.value->>'sku', ''), NULLIF(item.value->>'barcode', ''), '') AS sku,
                CASE
                    WHEN COALESCE(item.value->>'quantity', '') ~ '^[0-9]+(\\.[0-9]+)?$'
                        THEN GREATEST((item.value->>'quantity')::numeric, 0)
                    ELSE COALESCE(s.quantity, 0)
                END AS quantity,
                s.created_at
            FROM sales_scope s
            LEFT JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(s.metadata->'items') = 'array'
                        THEN s.metadata->'items'
                    ELSE '[]'::jsonb
                END
            ) AS item(value) ON TRUE
        ),
        normalized AS (
            SELECT
                COALESCE(NULLIF(reference_id, ''), lower(reference_name || '|' || category || '|' || size || '|' || color)) AS key,
                reference_id,
                reference_name,
                category,
                size,
                color,
                sku,
                quantity,
                created_at
            FROM expanded
            WHERE NULLIF(reference_name, '') IS NOT NULL
        )
        SELECT key,
               MAX(reference_id) AS reference_id,
               reference_name,
               category,
               size,
               color,
               MAX(sku) AS sku,
               COALESCE(SUM(quantity), 0) AS sold_quantity,
               MAX(created_at) AS last_sold_at
        FROM normalized
        GROUP BY key, reference_name, category, size, color
        ORDER BY sold_quantity DESC, last_sold_at DESC, reference_name ASC
        LIMIT {max(5, min(int(limit or 50), 100))}
        """,
        *args,
    )
    return [
        {
            "reference_id": _clean(row["reference_id"]),
            "name": _clean(row["reference_name"]),
            "category": _clean(row["category"]),
            "size": _clean(row["size"]),
            "color": _clean(row["color"]),
            "sku": _clean(row["sku"]),
            "sold_quantity": round(_num(row["sold_quantity"]), 2),
            "last_sold_at": _iso(row["last_sold_at"]),
        }
        for row in rows
    ]


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    sent = sum(1 for item in items if item.get("status") == "sent")
    preparing = sum(1 for item in items if item.get("status") == "preparing")
    ready = sum(1 for item in items if item.get("status") == "ready")
    received = sum(1 for item in items if item.get("status") == "received")
    archived = sum(1 for item in items if item.get("status") == "archived")
    units = sum(_num(item.get("requested_units")) for item in items)
    return {
        "total": len(items),
        "sent": sent,
        "preparing": preparing,
        "ready": ready,
        "received": received,
        "archived": archived,
        "active": sent + preparing + ready + received,
        "requested_units": round(units, 2),
    }


@router.get("/companies/{company_id}/suggestions")
async def request_suggestions(
    company_id: uuid.UUID,
    panel_type: str = Query(default="store"),
    limit: int = Query(default=80, ge=5, le=200),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        scope_user = _scope_user_id(access)
        try:
            references = await _references(conn, company_id, limit=limit)
        except Exception:
            references = []
        try:
            sold_items = await _sold_items(conn, company_id, panel_type, scope_user, limit=limit)
        except Exception:
            sold_items = []
        return {
            "references": references,
            "sold_items": sold_items,
        }
    finally:
        await conn.close()


@router.get("/companies/{company_id}")
async def list_requests(
    company_id: uuid.UUID,
    panel_type: str = Query(default="all"),
    status_filter: str = Query(default="active", alias="status"),
    q: str = Query(default=""),
    limit: int = Query(default=160, ge=1, le=500),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        scope_user = _scope_user_id(access)

        where = ["company_id = $1::uuid"]
        args: list[Any] = [company_id]
        idx = 2

        panel = _panel(panel_type)
        if panel not in {"all", "client"}:
            where.append(f"panel_type = ${idx}")
            args.append(panel)
            idx += 1

        status_clean = _norm(status_filter or "active")
        if status_clean == "active":
            where.append("status <> 'archived'")
        elif status_clean != "all":
            where.append(f"status = ${idx}")
            args.append(_status(status_filter))
            idx += 1

        if scope_user:
            where.append(f"requested_by = ${idx}::uuid")
            args.append(scope_user)
            idx += 1

        search = _clean(q)
        if search:
            where.append(
                f"""(
                    request_number ILIKE ${idx}
                    OR requested_by_label ILIKE ${idx}
                    OR store_label ILIKE ${idx}
                    OR notes ILIKE ${idx}
                    OR items::text ILIKE ${idx}
                )"""
            )
            args.append(f"%{search}%")
            idx += 1

        rows = await conn.fetch(
            f"""
            SELECT *
            FROM mini_panel_requests_records
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC
            LIMIT {int(limit)}
            """,
            *args,
        )
        items = [_request_payload(row) for row in rows]
        return {"items": items, "summary": _summary(items)}
    finally:
        await conn.close()


@router.get("/companies/{company_id}/{request_id}")
async def get_request(
    company_id: uuid.UUID,
    request_id: uuid.UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        await _require_access(conn, company_id, authorization)
        return _request_payload(await _fetch_request(conn, company_id, request_id))
    finally:
        await conn.close()


@router.post("/companies/{company_id}", status_code=status.HTTP_201_CREATED)
async def create_request(
    company_id: uuid.UUID,
    payload: RequestCreateIn,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        requested_by = _scope_user_id(access)
        if not requested_by:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo un mini panel puede enviar solicitudes.")

        panel = _panel(payload.panel_type or access.get("panel_type") or "store")
        requester = _scope_label(access) or "Usuario mini panel"
        actor_name = _clean(payload.store_employee_name)
        store_label = _clean(payload.store_label) or _clean(payload.store_slot_name) or requester
        items = _items_payload(payload.items)
        request_number = await _next_number(conn, company_id)
        timeline = _timeline("sent", by=actor_name or requester, note="Solicitud enviada desde mini panel.")
        actor = {
            "employee_id": _clean(payload.store_employee_id),
            "name": actor_name,
            "user_id": _clean(payload.store_user_id),
            "store_id": _clean(payload.store_slot_id),
            "store_name": _clean(payload.store_slot_name),
        }
        actor = {key: value for key, value in actor.items() if value}
        metadata = {
            "source": "mini_panel",
            "created_by_panel_type": panel,
            "items_count": len(items),
            "store_actor": actor,
        }

        row = await conn.fetchrow(
            """
            INSERT INTO mini_panel_requests_records (
                company_id, panel_type, request_number, requested_by, requested_by_label,
                store_label, status, items, notes, timeline, metadata
            )
            VALUES ($1::uuid, $2, $3, $4::uuid, $5, $6, 'sent', $7::jsonb, $8, $9::jsonb, $10::jsonb)
            RETURNING *
            """,
            company_id,
            panel,
            request_number,
            requested_by,
            actor_name or requester,
            store_label,
            json.dumps(items, ensure_ascii=False),
            _clean(payload.notes),
            json.dumps(timeline, ensure_ascii=False),
            json.dumps(metadata, ensure_ascii=False),
        )
        return _request_payload(row)
    finally:
        await conn.close()


@router.patch("/companies/{company_id}/{request_id}")
async def update_request(
    company_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: RequestUpdateIn,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        row = await _fetch_request(conn, company_id, request_id)
        next_status = _status(payload.status or row["status"])
        actor = _scope_label(access) or "Panel cliente"
        prepared_by = _clean(payload.prepared_by) or _clean(row["prepared_by"])
        note = _clean(payload.notes) if payload.notes is not None else _clean(row["notes"])
        timeline_note = ""
        prepared_at = row["prepared_at"]
        ready_at = row["ready_at"]
        received_at = row["received_at"]

        if next_status == "preparing":
            if not prepared_by:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Indica quien esta alistando.")
            prepared_at = prepared_at or _now()
            timeline_note = f"Alistando por {prepared_by}."
        elif next_status == "ready":
            ready_at = ready_at or _now()
            timeline_note = "Solicitud lista para entrega."
        elif next_status == "received":
            received_at = received_at or _now()
            timeline_note = "Solicitud recibida."

        timeline = _append_timeline(row["timeline"], next_status, by=actor, note=timeline_note)

        updated = await conn.fetchrow(
            """
            UPDATE mini_panel_requests_records
            SET status = $3,
                prepared_by = $4,
                prepared_at = $5,
                ready_at = $6,
                received_at = $7,
                notes = $8,
                timeline = $9::jsonb,
                updated_at = NOW()
            WHERE company_id = $1::uuid
              AND id = $2::uuid
            RETURNING *
            """,
            company_id,
            request_id,
            next_status,
            prepared_by,
            prepared_at,
            ready_at,
            received_at,
            note,
            json.dumps(timeline, ensure_ascii=False),
        )
        return _request_payload(updated)
    finally:
        await conn.close()


@router.post("/companies/{company_id}/{request_id}/received")
async def confirm_received(
    company_id: uuid.UUID,
    request_id: uuid.UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        scope_user = _scope_user_id(access)
        if not scope_user:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el mini panel puede confirmar recibido.")
        row = await _fetch_request(conn, company_id, request_id)
        if row["requested_by"] and str(row["requested_by"]) != str(scope_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Esta solicitud pertenece a otro usuario.")
        actor = _scope_label(access) or "Mini panel"
        timeline = _append_timeline(row["timeline"], "received", by=actor, note="Tienda confirma recibido.")
        updated = await conn.fetchrow(
            """
            UPDATE mini_panel_requests_records
            SET status = 'received',
                received_at = COALESCE(received_at, NOW()),
                timeline = $3::jsonb,
                updated_at = NOW()
            WHERE company_id = $1::uuid
              AND id = $2::uuid
            RETURNING *
            """,
            company_id,
            request_id,
            json.dumps(timeline, ensure_ascii=False),
        )
        return _request_payload(updated)
    finally:
        await conn.close()


@router.post("/companies/{company_id}/{request_id}/archive")
async def archive_request(
    company_id: uuid.UUID,
    request_id: uuid.UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        await _ensure_storage(conn)
        access = await _require_access(conn, company_id, authorization)
        row = await _fetch_request(conn, company_id, request_id)
        actor = _scope_label(access) or "Panel cliente"
        metadata = _json(row["metadata"], {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["previous_status"] = row["status"]
        metadata["archived_by_label"] = actor
        timeline = _append_timeline(row["timeline"], "archived", by=actor, note="Solicitud guardada y archivada.")
        updated = await conn.fetchrow(
            """
            UPDATE mini_panel_requests_records
            SET status = 'archived',
                archived_at = COALESCE(archived_at, NOW()),
                metadata = $3::jsonb,
                timeline = $4::jsonb,
                updated_at = NOW()
            WHERE company_id = $1::uuid
              AND id = $2::uuid
            RETURNING *
            """,
            company_id,
            request_id,
            json.dumps(metadata, ensure_ascii=False),
            json.dumps(timeline, ensure_ascii=False),
        )
        return _request_payload(updated)
    finally:
        await conn.close()
