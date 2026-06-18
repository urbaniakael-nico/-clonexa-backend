from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


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
    notes: str | None = Field(default="", max_length=1200)


def _clean(value: Any, limit: int = 255) -> str:
    return str(value or "").strip()[:limit]


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
        "CREATE INDEX IF NOT EXISTS ix_transport_call_logs_company_created ON transport_call_logs (company_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transport_call_logs_company_advisor ON transport_call_logs (company_id, advisor_name)",
    ]:
        await db.execute(text(statement))


@router.get("/companies/{company_id}/calls")
async def list_transport_calls(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=80, ge=1, le=250),
    search: str = Query(default="", max_length=120),
) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    query = f"%{_clean(search, 120).lower()}%"
    result = await db.execute(
        text(
            """
            SELECT *
            FROM transport_call_logs
            WHERE company_id = :company_id
              AND (
                :query = '%%'
                OR LOWER(advisor_name) LIKE :query
                OR LOWER(customer_name) LIKE :query
                OR LOWER(phone) LIKE :query
                OR LOWER(origin) LIKE :query
                OR LOWER(destination) LIKE :query
                OR LOWER(result) LIKE :query
              )
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"company_id": str(company_id), "query": query, "limit": int(limit)},
    )
    rows = [_row(row) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "calls": rows, "count": len(rows)}


@router.get("/companies/{company_id}/summary")
async def transport_calls_summary(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_calls_storage(db)
    result = await db.execute(
        text(
            """
            WITH today AS (
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
                COALESCE((SELECT ROUND(AVG(duration_seconds))::integer FROM today), 0) AS avg_duration_today,
                (SELECT COUNT(*) FROM today WHERE quote_requested IS TRUE) AS quotes_today,
                (SELECT COUNT(*) FROM today WHERE ticket_requested IS TRUE) AS tickets_today,
                (SELECT COUNT(*) FROM latest_advisor) AS advisors_total,
                (SELECT COUNT(*) FROM latest_advisor WHERE advisor_status = 'available') AS advisors_available,
                (SELECT COUNT(*) FROM latest_advisor WHERE advisor_status = 'in_call') AS advisors_in_call,
                (SELECT COUNT(*) FROM latest_advisor WHERE advisor_status IN ('break', 'bathroom', 'lunch')) AS advisors_paused,
                (SELECT COUNT(*) FROM today WHERE call_status = 'missed') AS missed_today
            """
        ),
        {"company_id": str(company_id)},
    )
    summary = _row(result.first() or {})
    return {"ok": True, "company_id": str(company_id), "summary": summary}


@router.post("/companies/{company_id}/calls", status_code=status.HTTP_201_CREATED)
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
            "notes": _clean(payload.notes, 1200),
        },
    )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "call": _row(result.first())}
