
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


def _clean(value: Any) -> str:
    return str(value or "").strip()


async def _ensure_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS clonexa_day_closures (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL,
            closure_date date NOT NULL,
            start_time varchar(8) NOT NULL,
            end_time varchar(8) NOT NULL,
            responsible text NULL,
            notes text NULL,
            status varchar(40) NOT NULL DEFAULT 'generated',
            summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_modules jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_clonexa_day_closures_company_date
        ON clonexa_day_closures (company_id, closure_date DESC, start_time, end_time)
    """))
    await db.commit()


@router.post("/companies/{company_id}/closures")
async def save_closure(
    company_id: UUID,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)

    raw_date = payload.get("date") or payload.get("closure_date")
    try:
        closure_date = date.fromisoformat(str(raw_date))
    except Exception:
        raise HTTPException(status_code=422, detail="Fecha inválida.")

    start_time = _clean(payload.get("start_time") or "07:00")[:5]
    end_time = _clean(payload.get("end_time") or "18:00")[:5]

    if len(start_time) != 5 or ":" not in start_time:
        raise HTTPException(status_code=422, detail="Hora inicio inválida.")
    if len(end_time) != 5 or ":" not in end_time:
        raise HTTPException(status_code=422, detail="Hora fin inválida.")

    closure_id = uuid4()
    summary = payload.get("summary") or {}
    source_modules = payload.get("source_modules") or []
    responsible = _clean(payload.get("responsible")) or None
    notes = _clean(payload.get("notes")) or None
    status_value = _clean(payload.get("status") or "generated")[:40]

    await db.execute(
        text("""
            INSERT INTO clonexa_day_closures (
                id,
                company_id,
                closure_date,
                start_time,
                end_time,
                responsible,
                notes,
                status,
                summary_json,
                source_modules,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :company_id,
                :closure_date,
                :start_time,
                :end_time,
                :responsible,
                :notes,
                :status,
                CAST(:summary_json AS jsonb),
                CAST(:source_modules AS jsonb),
                now(),
                now()
            )
        """),
        {
            "id": str(closure_id),
            "company_id": str(company_id),
            "closure_date": closure_date.isoformat(),
            "start_time": start_time,
            "end_time": end_time,
            "responsible": responsible,
            "notes": notes,
            "status": status_value,
            "summary_json": json.dumps(summary, ensure_ascii=False),
            "source_modules": json.dumps(source_modules, ensure_ascii=False),
        },
    )

    await db.commit()

    return {
        "id": str(closure_id),
        "company_id": str(company_id),
        "date": closure_date.isoformat(),
        "start_time": start_time,
        "end_time": end_time,
        "status": status_value,
        "saved_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/companies/{company_id}/closures")
async def list_closures(
    company_id: UUID,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _ensure_storage(db)

    limit = max(1, min(int(limit or 30), 100))

    result = await db.execute(
        text("""
            SELECT
                id::text AS id,
                company_id::text AS company_id,
                closure_date::text AS date,
                start_time,
                end_time,
                responsible,
                notes,
                status,
                summary_json,
                source_modules,
                created_at::text AS created_at,
                updated_at::text AS updated_at
            FROM clonexa_day_closures
            WHERE company_id = :company_id
            ORDER BY closure_date DESC, created_at DESC
            LIMIT :limit
        """),
        {"company_id": str(company_id), "limit": limit},
    )

    return [dict(row) for row in result.mappings().all()]
