from __future__ import annotations

import csv
import io
import unicodedata
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, READ_ROLES, WRITE_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()

TRANSPORT_CALL_MANAGER_ROLES = ADMIN_ROLES | {"manager", "gerencia", "gerente", "supervisor", "tesoreria"}


def _authorization_from_query_028s(authorization: str | None, access_token: str | None = "") -> str | None:
    token = str(access_token or "").strip()
    return authorization or (f"Bearer {token}" if token else None)


async def require_transport_calls_read(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str = Query(default="", max_length=2048),
    db: AsyncSession = Depends(get_db),
) -> None:
    if await active_admin_v2_session(request, db):
        await require_enabled_module(db, company_id, "transport_calls")
        return
    await require_company_user_for_tenant(
        db,
        _authorization_from_query_028s(authorization, access_token),
        company_id,
        allowed_roles=READ_ROLES,
        module_codes="transport_calls",
    )


async def require_transport_calls_write(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    if await active_admin_v2_session(request, db):
        await require_enabled_module(db, company_id, "transport_calls")
        return
    await require_company_user_for_tenant(
        db,
        authorization,
        company_id,
        allowed_roles=WRITE_ROLES,
        module_codes="transport_calls",
    )


async def require_transport_calls_manage(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str = Query(default="", max_length=2048),
    db: AsyncSession = Depends(get_db),
) -> None:
    if await active_admin_v2_session(request, db):
        await require_enabled_module(db, company_id, "transport_calls")
        return
    await require_company_user_for_tenant(
        db,
        _authorization_from_query_028s(authorization, access_token),
        company_id,
        allowed_roles=TRANSPORT_CALL_MANAGER_ROLES,
        module_codes="transport_calls",
    )


class TransportCallIn(BaseModel):
    advisor_name: str | None = Field(default="", max_length=180)
    advisor_status: str | None = Field(default="available", max_length=40)
    customer_name: str | None = Field(default="", max_length=180)
    customer_type: str | None = Field(default="person", max_length=40)
    phone: str | None = Field(default="", max_length=80)
    origin: str | None = Field(default="", max_length=160)
    destination: str | None = Field(default="", max_length=160)
    trip_type: str | None = Field(default="", max_length=80)
    call_direction: str | None = Field(default="inbound", max_length=20)
    call_status: str | None = Field(default="completed", max_length=40)
    result: str | None = Field(default="follow_up", max_length=80)
    duration_seconds: int | None = Field(default=0, ge=0)
    duration_minutes: float | None = Field(default=None, ge=0)
    quote_requested: bool | None = False
    ticket_requested: bool | None = False
    contract_code: str | None = Field(default="", max_length=120)
    source: str | None = Field(default="manual", max_length=40)
    twilio_call_sid: str | None = Field(default="", max_length=120)
    batch_row_id: str | None = Field(default="", max_length=80)
    notes: str | None = Field(default="", max_length=1200)


def _clean(value: Any, limit: int = 255) -> str:
    return str(value or "").strip()[:limit]


def _csv_value(row: dict[str, Any], *names: str, limit: int = 255) -> str:
    normalized = {
        unicodedata.normalize("NFKD", str(key or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_"): value
        for key, value in row.items()
    }
    for name in names:
        key = (
            unicodedata.normalize("NFKD", name)
            .encode("ascii", "ignore")
            .decode("ascii")
            .strip()
            .lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("-", "_")
        )
        if key in normalized and normalized[key] not in (None, ""):
            return _clean(normalized[key], limit)
    return ""


def _role_tokens(*values: Any) -> set[str]:
    raw = " ".join(str(value or "") for value in values)
    normalized = (
        unicodedata.normalize("NFKD", raw)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .replace("/", " ")
        .replace("-", " ")
        .replace("_", " ")
    )
    compact = normalized.replace(" ", "")
    return set(normalized.split()) | ({compact} if compact else set())


def _is_call_agent_role(role: Any, employee_type: Any = "") -> bool:
    tokens = _role_tokens(role, employee_type)
    allowed = {
        "agente", "asesor", "operario", "vendedor", "agente_call", "agentecall",
        "call", "callcenter", "asesorcall", "agenteexterno", "externo",
    }
    return bool(tokens & allowed)


def _duration_seconds(payload: TransportCallIn) -> int:
    if payload.duration_minutes is not None:
        return max(0, int(float(payload.duration_minutes or 0) * 60))
    return max(0, int(payload.duration_seconds or 0))


def _row(row: Any) -> dict[str, Any]:
    data = dict(row._mapping if hasattr(row, "_mapping") else row)
    for key, value in list(data.items()):
        if isinstance(value, (datetime,)):
            data[key] = value.isoformat()
        elif isinstance(value, uuid.UUID):
            data[key] = str(value)
    return data


async def ensure_transport_calls_storage(db: AsyncSession) -> None:
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS transport_call_logs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id uuid NOT NULL,
                advisor_name varchar(180) NOT NULL DEFAULT '',
                advisor_status varchar(40) NOT NULL DEFAULT 'available',
                customer_name varchar(180) NOT NULL DEFAULT '',
                customer_type varchar(40) NOT NULL DEFAULT 'person',
                phone varchar(80) NOT NULL DEFAULT '',
                origin varchar(160) NOT NULL DEFAULT '',
                destination varchar(160) NOT NULL DEFAULT '',
                trip_type varchar(80) NOT NULL DEFAULT '',
                call_direction varchar(20) NOT NULL DEFAULT 'inbound',
                call_status varchar(40) NOT NULL DEFAULT 'completed',
                result varchar(80) NOT NULL DEFAULT 'follow_up',
                duration_seconds integer NOT NULL DEFAULT 0,
                quote_requested boolean NOT NULL DEFAULT false,
                ticket_requested boolean NOT NULL DEFAULT false,
                contract_code varchar(120) NOT NULL DEFAULT '',
                notes text NOT NULL DEFAULT '',
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    for statement in [
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS advisor_status varchar(40) NOT NULL DEFAULT 'available'",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS contract_code varchar(120) NOT NULL DEFAULT ''",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS source varchar(40) NOT NULL DEFAULT 'manual'",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS twilio_call_sid varchar(120) NOT NULL DEFAULT ''",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS batch_row_id UUID NULL",
        "CREATE INDEX IF NOT EXISTS ix_transport_call_logs_company_created ON transport_call_logs (company_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transport_call_logs_company_advisor ON transport_call_logs (company_id, advisor_name)",
        "CREATE INDEX IF NOT EXISTS ix_transport_call_logs_company_twilio ON transport_call_logs (company_id, twilio_call_sid)",
    ]:
        await db.execute(text(statement))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS transport_call_batches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL,
            file_name VARCHAR(240) NOT NULL DEFAULT '',
            assigned_employee_id UUID NULL,
            assigned_agent_name VARCHAR(180) NOT NULL DEFAULT '',
            assigned_agent_role VARCHAR(80) NOT NULL DEFAULT '',
            assigned_user_id UUID NULL,
            record_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(40) NOT NULL DEFAULT 'active',
            created_by_label VARCHAR(180) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            archived_at TIMESTAMPTZ NULL
        )
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS transport_call_batch_rows (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id UUID NOT NULL REFERENCES transport_call_batches(id) ON DELETE CASCADE,
            company_id UUID NOT NULL,
            row_number INTEGER NOT NULL DEFAULT 0,
            customer_name VARCHAR(180) NOT NULL DEFAULT '',
            customer_type VARCHAR(40) NOT NULL DEFAULT 'person',
            phone VARCHAR(80) NOT NULL DEFAULT '',
            email VARCHAR(160) NOT NULL DEFAULT '',
            document_id VARCHAR(80) NOT NULL DEFAULT '',
            contract_code VARCHAR(120) NOT NULL DEFAULT '',
            origin VARCHAR(160) NOT NULL DEFAULT '',
            destination VARCHAR(160) NOT NULL DEFAULT '',
            trip_type VARCHAR(80) NOT NULL DEFAULT '',
            call_direction VARCHAR(20) NOT NULL DEFAULT '',
            call_status VARCHAR(40) NOT NULL DEFAULT '',
            result VARCHAR(80) NOT NULL DEFAULT '',
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            quote_requested BOOLEAN NOT NULL DEFAULT false,
            ticket_requested BOOLEAN NOT NULL DEFAULT false,
            twilio_call_sid VARCHAR(120) NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            managed_by VARCHAR(180) NOT NULL DEFAULT '',
            managed_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    for statement in [
        "CREATE INDEX IF NOT EXISTS ix_transport_call_batches_company ON transport_call_batches(company_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_transport_call_batches_agent ON transport_call_batches(company_id, assigned_employee_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_transport_call_batch_rows_batch ON transport_call_batch_rows(batch_id, row_number)",
        "CREATE INDEX IF NOT EXISTS ix_transport_call_batch_rows_company ON transport_call_batch_rows(company_id, managed_at)",
    ]:
        await db.execute(text(statement))


@router.get("/companies/{company_id}/calls", dependencies=[Depends(require_transport_calls_read)])
async def list_transport_calls(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=80, ge=1, le=250),
    search: str = Query(default="", max_length=120),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    query = f"%{_clean(search, 120).lower()}%"
    result = await db.execute(
        text(
            """
            SELECT *
            FROM transport_call_logs
            WHERE company_id = :company_id
              AND (:start_date = '' OR created_at >= CAST(:start_date AS date))
              AND (:end_date = '' OR created_at < (CAST(:end_date AS date) + INTERVAL '1 day'))
              AND (
                :query = '%%'
                OR LOWER(advisor_name) LIKE :query
                OR LOWER(customer_name) LIKE :query
                OR LOWER(phone) LIKE :query
                OR LOWER(contract_code) LIKE :query
                OR LOWER(twilio_call_sid) LIKE :query
                OR LOWER(origin) LIKE :query
                OR LOWER(destination) LIKE :query
                OR LOWER(result) LIKE :query
                OR LOWER(notes) LIKE :query
              )
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {
            "company_id": str(company_id),
            "query": query,
            "limit": int(limit),
            "start_date": _clean(start_date, 20),
            "end_date": _clean(end_date, 20),
        },
    )
    rows = [_row(row) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "calls": rows, "count": len(rows)}


@router.get("/companies/{company_id}/summary", dependencies=[Depends(require_transport_calls_read)])
async def transport_calls_summary(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    search: str = Query(default="", max_length=120),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    query = f"%{_clean(search, 120).lower()}%"
    result = await db.execute(
        text(
            """
            WITH period AS (
                SELECT *
                FROM transport_call_logs
                WHERE company_id = :company_id
                  AND (:start_date = '' OR created_at >= CAST(:start_date AS date))
                  AND (:end_date = '' OR created_at < (CAST(:end_date AS date) + INTERVAL '1 day'))
                  AND (
                    :query = '%%'
                    OR LOWER(advisor_name) LIKE :query
                    OR LOWER(customer_name) LIKE :query
                    OR LOWER(phone) LIKE :query
                    OR LOWER(contract_code) LIKE :query
                    OR LOWER(origin) LIKE :query
                    OR LOWER(destination) LIKE :query
                    OR LOWER(result) LIKE :query
                    OR LOWER(notes) LIKE :query
                  )
            ),
            today AS (
                SELECT *
                FROM transport_call_logs
                WHERE company_id = :company_id
                  AND created_at >= date_trunc('day', now())
            ),
            latest_advisor AS (
                SELECT DISTINCT ON (LOWER(advisor_name))
                    advisor_name,
                    advisor_status,
                    created_at
                FROM transport_call_logs
                WHERE company_id = :company_id
                  AND TRIM(advisor_name) <> ''
                ORDER BY LOWER(advisor_name), created_at DESC
            )
            SELECT
                (SELECT COUNT(*) FROM today) AS calls_today,
                (SELECT COUNT(*) FROM transport_call_logs WHERE company_id = :company_id) AS calls_total,
                COALESCE((SELECT SUM(duration_seconds) FROM today), 0) AS duration_today,
                COALESCE((SELECT ROUND(AVG(NULLIF(duration_seconds, 0)))::integer FROM today), 0) AS avg_duration_today,
                (SELECT COUNT(*) FROM today WHERE quote_requested IS TRUE) AS quotes_today,
                (SELECT COUNT(*) FROM today WHERE ticket_requested IS TRUE) AS tickets_today,
                (SELECT COUNT(*) FROM period) AS calls_period,
                COALESCE((SELECT SUM(duration_seconds) FROM period), 0) AS duration_period,
                COALESCE((SELECT ROUND(AVG(NULLIF(duration_seconds, 0)))::integer FROM period), 0) AS avg_duration_period,
                (SELECT COUNT(*) FROM period WHERE quote_requested IS TRUE) AS quotes_period,
                (SELECT COUNT(*) FROM period WHERE ticket_requested IS TRUE) AS tickets_period,
                (SELECT COUNT(*) FROM latest_advisor) AS advisors_total,
                (SELECT COUNT(*) FROM latest_advisor WHERE advisor_status = 'available') AS advisors_available,
                (SELECT COUNT(*) FROM latest_advisor WHERE advisor_status = 'in_call') AS advisors_in_call,
                (SELECT COUNT(*) FROM latest_advisor WHERE advisor_status IN ('break', 'bathroom', 'lunch')) AS advisors_paused,
                (SELECT COUNT(*) FROM today WHERE call_status = 'missed') AS missed_today,
                (SELECT COUNT(*) FROM period WHERE call_status IN ('missed','no_answer','failed')) AS missed_period
            """
        ),
        {
            "company_id": str(company_id),
            "query": query,
            "start_date": _clean(start_date, 20),
            "end_date": _clean(end_date, 20),
        },
    )
    summary = _row(result.first() or {})
    return {"ok": True, "company_id": str(company_id), "summary": summary}


@router.post("/companies/{company_id}/calls", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_transport_calls_write)])
async def create_transport_call(
    company_id: uuid.UUID,
    payload: TransportCallIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    result = await db.execute(
        text(
            """
            INSERT INTO transport_call_logs (
                company_id,
                advisor_name,
                advisor_status,
                customer_name,
                customer_type,
                phone,
                origin,
                destination,
                trip_type,
                call_direction,
                call_status,
                result,
                duration_seconds,
                quote_requested,
                ticket_requested,
                contract_code,
                source,
                twilio_call_sid,
                batch_row_id,
                notes,
                created_at,
                updated_at
            )
            VALUES (
                :company_id,
                :advisor_name,
                :advisor_status,
                :customer_name,
                :customer_type,
                :phone,
                :origin,
                :destination,
                :trip_type,
                :call_direction,
                :call_status,
                :result,
                :duration_seconds,
                :quote_requested,
                :ticket_requested,
                :contract_code,
                :source,
                :twilio_call_sid,
                CAST(NULLIF(:batch_row_id, '') AS uuid),
                :notes,
                now(),
                now()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "advisor_name": _clean(payload.advisor_name, 180),
            "advisor_status": _clean(payload.advisor_status or "available", 40),
            "customer_name": _clean(payload.customer_name, 180),
            "customer_type": _clean(payload.customer_type or "person", 40),
            "phone": _clean(payload.phone, 80),
            "origin": _clean(payload.origin, 160),
            "destination": _clean(payload.destination, 160),
            "trip_type": _clean(payload.trip_type, 80),
            "call_direction": _clean(payload.call_direction or "inbound", 20),
            "call_status": _clean(payload.call_status or "completed", 40),
            "result": _clean(payload.result or "follow_up", 80),
            "duration_seconds": _duration_seconds(payload),
            "quote_requested": bool(payload.quote_requested),
            "ticket_requested": bool(payload.ticket_requested),
            "contract_code": _clean(payload.contract_code, 120),
            "source": _clean(payload.source or "manual", 40),
            "twilio_call_sid": _clean(payload.twilio_call_sid, 120),
            "batch_row_id": _clean(payload.batch_row_id, 80),
            "notes": _clean(payload.notes, 1200),
        },
    )
    row = result.first()
    if _clean(payload.batch_row_id, 80):
        await db.execute(
            text(
                """
                UPDATE transport_call_batch_rows
                SET customer_name = COALESCE(NULLIF(:customer_name, ''), customer_name),
                    customer_type = COALESCE(NULLIF(:customer_type, ''), customer_type),
                    phone = COALESCE(NULLIF(:phone, ''), phone),
                    contract_code = COALESCE(NULLIF(:contract_code, ''), contract_code),
                    origin = COALESCE(NULLIF(:origin, ''), origin),
                    destination = COALESCE(NULLIF(:destination, ''), destination),
                    trip_type = COALESCE(NULLIF(:trip_type, ''), trip_type),
                    call_direction = :call_direction,
                    call_status = :call_status,
                    result = :result,
                    duration_seconds = :duration_seconds,
                    quote_requested = :quote_requested,
                    ticket_requested = :ticket_requested,
                    twilio_call_sid = :twilio_call_sid,
                    notes = :notes,
                    managed_by = :advisor_name,
                    managed_at = now(),
                    updated_at = now()
                WHERE id = CAST(:batch_row_id AS uuid)
                  AND company_id = CAST(:company_id AS uuid)
                """
            ),
            {
                "company_id": str(company_id),
                "batch_row_id": _clean(payload.batch_row_id, 80),
                "customer_name": _clean(payload.customer_name, 180),
                "customer_type": _clean(payload.customer_type or "person", 40),
                "phone": _clean(payload.phone, 80),
                "contract_code": _clean(payload.contract_code, 120),
                "origin": _clean(payload.origin, 160),
                "destination": _clean(payload.destination, 160),
                "trip_type": _clean(payload.trip_type, 80),
                "call_direction": _clean(payload.call_direction or "inbound", 20),
                "call_status": _clean(payload.call_status or "completed", 40),
                "result": _clean(payload.result or "follow_up", 80),
                "duration_seconds": _duration_seconds(payload),
                "quote_requested": bool(payload.quote_requested),
                "ticket_requested": bool(payload.ticket_requested),
                "twilio_call_sid": _clean(payload.twilio_call_sid, 120),
                "notes": _clean(payload.notes, 1200),
                "advisor_name": _clean(payload.advisor_name, 180),
            },
        )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "call": _row(row)}


@router.get("/companies/{company_id}/customers", dependencies=[Depends(require_transport_calls_read)])
async def transport_customer_suggestions(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    search: str = Query(default="", max_length=120),
    employee_id: str = Query(default="", max_length=80),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    query = f"%{_clean(search, 120).lower()}%"
    if _clean(employee_id, 80):
        assigned = await db.execute(
            text(
                """
                SELECT r.*, b.file_name AS batch_file_name, b.assigned_agent_name
                FROM transport_call_batch_rows r
                JOIN transport_call_batches b ON b.id = r.batch_id
                WHERE r.company_id = CAST(:company_id AS uuid)
                  AND b.status = 'active'
                  AND b.assigned_employee_id = CAST(:employee_id AS uuid)
                  AND r.managed_at IS NULL
                  AND (
                    :query = '%%'
                    OR LOWER(r.customer_name) LIKE :query
                    OR LOWER(r.phone) LIKE :query
                    OR LOWER(r.contract_code) LIKE :query
                    OR LOWER(r.origin) LIKE :query
                    OR LOWER(r.destination) LIKE :query
                  )
                ORDER BY b.created_at DESC, r.row_number ASC
                LIMIT :limit
                """
            ),
            {"company_id": str(company_id), "employee_id": _clean(employee_id, 80), "query": query, "limit": int(limit)},
        )
        rows = []
        for row in assigned.fetchall():
            data = _row(row)
            rows.append({
                "batch_row_id": data.get("id", ""),
                "batch_id": data.get("batch_id", ""),
                "batch_file_name": data.get("batch_file_name", ""),
                "row_number": data.get("row_number", 0),
                "source": "assigned_batch",
                "customer_name": data.get("customer_name", ""),
                "customer_type": data.get("customer_type", "person"),
                "phone": data.get("phone", ""),
                "email": data.get("email", ""),
                "document_id": data.get("document_id", ""),
                "contract_code": data.get("contract_code", ""),
                "origin": data.get("origin", ""),
                "destination": data.get("destination", ""),
                "trip_type": data.get("trip_type", ""),
                "notes": data.get("notes", ""),
            })
        return {"ok": True, "company_id": str(company_id), "customers": rows, "count": len(rows)}
    result = await db.execute(
        text(
            """
            SELECT DISTINCT ON (
                NULLIF(LOWER(TRIM(phone)), ''),
                NULLIF(LOWER(TRIM(customer_name)), ''),
                NULLIF(LOWER(TRIM(contract_code)), '')
            )
                customer_name,
                customer_type,
                phone,
                contract_code,
                origin,
                destination,
                created_at
            FROM transport_call_logs
            WHERE company_id = :company_id
              AND (
                :query = '%%'
                OR LOWER(customer_name) LIKE :query
                OR LOWER(phone) LIKE :query
                OR LOWER(contract_code) LIKE :query
              )
              AND (
                TRIM(customer_name) <> ''
                OR TRIM(phone) <> ''
                OR TRIM(contract_code) <> ''
              )
            ORDER BY
                NULLIF(LOWER(TRIM(phone)), ''),
                NULLIF(LOWER(TRIM(customer_name)), ''),
                NULLIF(LOWER(TRIM(contract_code)), ''),
                created_at DESC
            LIMIT :limit
            """
        ),
        {"company_id": str(company_id), "query": query, "limit": int(limit)},
    )
    rows = [_row(row) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "customers": rows, "count": len(rows)}


@router.get("/companies/{company_id}/agents", dependencies=[Depends(require_transport_calls_manage)])
async def list_transport_call_agents(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    result = await db.execute(
        text(
            """
            SELECT e.id::text AS id, e.full_name, e.phone, e.email, e.role, e.employee_type, e.status,
                   u.id::text AS user_id, COALESCE(u.email, '') AS username
            FROM employees e
            LEFT JOIN company_users u ON u.company_id = e.company_id
              AND u.settings_json->'mini_panel'->>'employee_id' = e.id::text
              AND u.status = 'active'
            WHERE e.company_id = CAST(:company_id AS uuid)
              AND LOWER(COALESCE(e.status, 'active')) <> 'archived'
            ORDER BY e.full_name ASC
            """
        ),
        {"company_id": str(company_id)},
    )
    agents = [_row(row) for row in result.fetchall()]
    agents = [agent for agent in agents if _is_call_agent_role(agent.get("role"), agent.get("employee_type"))]
    return {"ok": True, "company_id": str(company_id), "agents": agents, "count": len(agents)}


@router.get("/companies/{company_id}/batches", dependencies=[Depends(require_transport_calls_manage)])
async def list_transport_call_batches(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    status_filter: str = Query(default="active", alias="status", max_length=40),
    limit: int = Query(default=80, ge=1, le=200),
) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    result = await db.execute(
        text(
            """
            SELECT b.*,
                   COUNT(r.id)::int AS rows_total,
                   COUNT(r.id) FILTER (WHERE r.managed_at IS NOT NULL)::int AS rows_managed
            FROM transport_call_batches b
            LEFT JOIN transport_call_batch_rows r ON r.batch_id = b.id
            WHERE b.company_id = CAST(:company_id AS uuid)
              AND (:status = 'all' OR b.status = :status)
            GROUP BY b.id
            ORDER BY b.created_at DESC
            LIMIT :limit
            """
        ),
        {"company_id": str(company_id), "status": _clean(status_filter or "active", 40), "limit": int(limit)},
    )
    rows = [_row(row) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "batches": rows, "count": len(rows)}


@router.post("/companies/{company_id}/batches/import-csv", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_transport_calls_manage)])
async def import_transport_call_batch_csv(
    company_id: uuid.UUID,
    assigned_employee_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    employee = await db.execute(
        text(
            """
            SELECT id::text, full_name, role, employee_type
            FROM employees
            WHERE company_id = CAST(:company_id AS uuid)
              AND id = CAST(:employee_id AS uuid)
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "employee_id": _clean(assigned_employee_id, 80)},
    )
    employee_row = _row(employee.first() or {})
    if not employee_row:
        raise HTTPException(status_code=404, detail="agent_not_found")
    if not _is_call_agent_role(employee_row.get("role"), employee_row.get("employee_type")):
        raise HTTPException(status_code=400, detail="employee_is_not_call_agent")
    active_batch = await db.execute(
        text(
            """
            SELECT id::text
            FROM transport_call_batches
            WHERE company_id = CAST(:company_id AS uuid)
              AND assigned_employee_id = CAST(:employee_id AS uuid)
              AND status = 'active'
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "employee_id": _clean(assigned_employee_id, 80)},
    )
    if active_batch.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="agent_has_active_batch")
    user = await db.execute(
        text(
            """
            SELECT id::text
            FROM company_users
            WHERE company_id = CAST(:company_id AS uuid)
              AND settings_json->'mini_panel'->>'employee_id' = :employee_id
              AND status = 'active'
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "employee_id": _clean(assigned_employee_id, 80)},
    )
    user_id = user.scalar_one_or_none() or ""
    raw = await file.read()
    try:
        body = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        body = raw.decode("latin-1")
    rows = list(csv.DictReader(io.StringIO(body)))
    if not rows:
        raise HTTPException(status_code=400, detail="empty_csv")
    batch = await db.execute(
        text(
            """
            INSERT INTO transport_call_batches (
                company_id, file_name, assigned_employee_id, assigned_agent_name,
                assigned_agent_role, assigned_user_id, record_count, created_by_label
            ) VALUES (
                CAST(:company_id AS uuid), :file_name, CAST(:employee_id AS uuid), :agent_name,
                :agent_role, CAST(NULLIF(:user_id, '') AS uuid), :record_count, 'Admin V2'
            )
            RETURNING id
            """
        ),
        {
            "company_id": str(company_id),
            "file_name": _clean(file.filename or "base_llamadas.csv", 240),
            "employee_id": _clean(assigned_employee_id, 80),
            "agent_name": _clean(employee_row.get("full_name"), 180),
            "agent_role": _clean(employee_row.get("role") or employee_row.get("employee_type"), 80),
            "user_id": _clean(user_id, 80),
            "record_count": len(rows),
        },
    )
    batch_id = str(batch.scalar_one())
    for index, row in enumerate(rows, start=1):
        await db.execute(
            text(
                """
                INSERT INTO transport_call_batch_rows (
                    batch_id, company_id, row_number, customer_name, customer_type, phone, email,
                    document_id, contract_code, origin, destination, trip_type, notes
                ) VALUES (
                    CAST(:batch_id AS uuid), CAST(:company_id AS uuid), :row_number, :customer_name, :customer_type, :phone, :email,
                    :document_id, :contract_code, :origin, :destination, :trip_type, :notes
                )
                """
            ),
            {
                "batch_id": batch_id,
                "company_id": str(company_id),
                "row_number": index,
                "customer_name": _csv_value(row, "cliente", "customer_name", "nombre", "empresa", "razon_social", limit=180),
                "customer_type": _csv_value(row, "tipo_cliente", "customer_type", limit=40) or "person",
                "phone": _csv_value(row, "telefono", "phone", "celular", "whatsapp", limit=80),
                "email": _csv_value(row, "correo", "email", "mail", limit=160),
                "document_id": _csv_value(row, "documento", "nit", "cc", "id", limit=80),
                "contract_code": _csv_value(row, "contrato", "aval", "contrato_aval", "numero_contrato", limit=120),
                "origin": _csv_value(row, "origen", "ciudad_origen", limit=160),
                "destination": _csv_value(row, "destino", "ciudad_destino", limit=160),
                "trip_type": _csv_value(row, "tipo_viaje", "servicio", "ruta", limit=80),
                "notes": _csv_value(row, "notas", "observaciones", "comentarios", limit=1200),
            },
        )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "batch_id": batch_id, "record_count": len(rows)}


@router.post("/companies/{company_id}/batches/{batch_id}/archive", dependencies=[Depends(require_transport_calls_manage)])
async def archive_transport_call_batch(company_id: uuid.UUID, batch_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    await db.execute(
        text(
            """
            UPDATE transport_call_batches
            SET status = 'archived', archived_at = now(), updated_at = now()
            WHERE company_id = CAST(:company_id AS uuid)
              AND id = CAST(:batch_id AS uuid)
            """
        ),
        {"company_id": str(company_id), "batch_id": str(batch_id)},
    )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "batch_id": str(batch_id)}


@router.delete("/companies/{company_id}/batches/{batch_id}", dependencies=[Depends(require_transport_calls_manage)])
async def delete_transport_call_batch(company_id: uuid.UUID, batch_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    await db.execute(
        text(
            """
            DELETE FROM transport_call_batches
            WHERE company_id = CAST(:company_id AS uuid)
              AND id = CAST(:batch_id AS uuid)
            """
        ),
        {"company_id": str(company_id), "batch_id": str(batch_id)},
    )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "batch_id": str(batch_id)}


@router.get("/companies/{company_id}/batches/{batch_id}/export.csv", dependencies=[Depends(require_transport_calls_manage)])
async def export_transport_call_batch_csv(company_id: uuid.UUID, batch_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    await ensure_transport_calls_storage(db)
    result = await db.execute(
        text(
            """
            SELECT b.file_name, b.assigned_agent_name, r.*
            FROM transport_call_batches b
            JOIN transport_call_batch_rows r ON r.batch_id = b.id
            WHERE b.company_id = CAST(:company_id AS uuid)
              AND b.id = CAST(:batch_id AS uuid)
            ORDER BY r.row_number ASC
            """
        ),
        {"company_id": str(company_id), "batch_id": str(batch_id)},
    )
    rows = [_row(row) for row in result.fetchall()]
    output = io.StringIO()
    fieldnames = [
        "archivo", "agente", "fila", "cliente", "tipo_cliente", "telefono", "correo", "documento", "contrato",
        "origen", "destino", "tipo_viaje", "direccion_llamada", "estado_llamada", "resultado", "duracion_segundos",
        "genero_cotizacion", "genero_ticket", "id_twilio", "notas", "gestionado_por", "gestionado_en",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "archivo": row.get("file_name") or "",
            "agente": row.get("assigned_agent_name") or "",
            "fila": row.get("row_number") or "",
            "cliente": row.get("customer_name") or "",
            "tipo_cliente": row.get("customer_type") or "",
            "telefono": row.get("phone") or "",
            "correo": row.get("email") or "",
            "documento": row.get("document_id") or "",
            "contrato": row.get("contract_code") or "",
            "origen": row.get("origin") or "",
            "destino": row.get("destination") or "",
            "tipo_viaje": row.get("trip_type") or "",
            "direccion_llamada": row.get("call_direction") or "",
            "estado_llamada": row.get("call_status") or "",
            "resultado": row.get("result") or "",
            "duracion_segundos": row.get("duration_seconds") or 0,
            "genero_cotizacion": "si" if row.get("quote_requested") else "no",
            "genero_ticket": "si" if row.get("ticket_requested") else "no",
            "id_twilio": row.get("twilio_call_sid") or "",
            "notas": row.get("notes") or "",
            "gestionado_por": row.get("managed_by") or "",
            "gestionado_en": row.get("managed_at") or "",
        })
    filename = "gestion_llamadas.csv"
    if rows and rows[0].get("file_name"):
        filename = f"gestion_{str(rows[0]['file_name']).replace(' ', '_')}"
        if not filename.lower().endswith(".csv"):
            filename += ".csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _twilio_direction(value: Any) -> str:
    raw = _clean(value, 40).lower()
    if "out" in raw:
        return "outbound"
    return "inbound"


def _twilio_status(value: Any) -> str:
    raw = _clean(value, 40).lower()
    if raw in {"no-answer", "busy", "failed", "canceled", "cancelled"}:
        return "missed"
    if raw in {"ringing", "queued", "initiated", "in-progress"}:
        return "pending"
    return "completed"


@router.post("/companies/{company_id}/twilio/status")
async def transport_twilio_status_webhook(
    company_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    if "application/json" in _clean(request.headers.get("content-type"), 120).lower():
        form = await request.json()
    else:
        raw_body = (await request.body()).decode("utf-8", errors="ignore")
        parsed = parse_qs(raw_body)
        form = {key: values[-1] if values else "" for key, values in parsed.items()}

    call_sid = _clean(form.get("CallSid") or form.get("call_sid"), 120)
    if not call_sid:
        return {"ok": False, "detail": "missing_call_sid"}

    direction = _twilio_direction(form.get("Direction"))
    status_value = _twilio_status(form.get("CallStatus"))
    duration = max(0, int(float(form.get("CallDuration") or form.get("Duration") or 0)))
    phone = _clean(form.get("From") or form.get("Caller") or "", 80)
    notes = _clean(form.get("To") or "", 1200)

    existing = await db.execute(
        text(
            """
            SELECT id
            FROM transport_call_logs
            WHERE company_id = :company_id
              AND twilio_call_sid = :call_sid
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "call_sid": call_sid},
    )
    row = existing.first()

    if row:
        result = await db.execute(
            text(
                """
                UPDATE transport_call_logs
                SET call_direction = :direction,
                    call_status = :status,
                    duration_seconds = CASE WHEN :duration > 0 THEN :duration ELSE duration_seconds END,
                    phone = CASE WHEN TRIM(phone) = '' THEN :phone ELSE phone END,
                    source = 'twilio',
                    updated_at = now()
                WHERE id = :id
                RETURNING *
                """
            ),
            {
                "id": row._mapping["id"],
                "direction": direction,
                "status": status_value,
                "duration": duration,
                "phone": phone,
            },
        )
    else:
        result = await db.execute(
            text(
                """
                INSERT INTO transport_call_logs (
                    company_id,
                    advisor_status,
                    customer_type,
                    phone,
                    call_direction,
                    call_status,
                    duration_seconds,
                    source,
                    twilio_call_sid,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (
                    :company_id,
                    :advisor_status,
                    'person',
                    :phone,
                    :direction,
                    :status,
                    :duration,
                    'twilio',
                    :call_sid,
                    :notes,
                    now(),
                    now()
                )
                RETURNING *
                """
            ),
            {
                "company_id": str(company_id),
                "advisor_status": "in_call" if status_value == "pending" else "available",
                "phone": phone,
                "direction": direction,
                "status": status_value,
                "duration": duration,
                "call_sid": call_sid,
                "notes": notes,
            },
        )

    await db.commit()
    return {"ok": True, "company_id": str(company_id), "call": _row(result.first())}
