
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


def clean(value: Any) -> str:
    return str(value or "").strip()


def safe_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


async def ensure_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS clonexa_closure_store (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            module_code text NOT NULL DEFAULT 'day_closing',
            closure_date text NOT NULL,
            start_time text NOT NULL,
            end_time text NOT NULL,
            responsible text NULL,
            notes text NULL,
            status text NOT NULL DEFAULT 'generated',
            summary_text text NOT NULL DEFAULT '{}',
            source_modules_text text NOT NULL DEFAULT '[]',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_clonexa_closure_store_company_module
        ON clonexa_closure_store (company_id, module_code, created_at DESC)
    """))

    await db.commit()


@router.post("/companies/{company_id}/day")
async def save_day_closure(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    closure_date = clean(payload.get("date") or payload.get("closure_date"))
    start_time = clean(payload.get("start_time") or "07:00")[:5]
    end_time = clean(payload.get("end_time") or "18:00")[:5]

    if not closure_date:
        raise HTTPException(status_code=422, detail="Fecha requerida.")
    if ":" not in start_time:
        raise HTTPException(status_code=422, detail="Hora inicio inválida.")
    if ":" not in end_time:
        raise HTTPException(status_code=422, detail="Hora fin inválida.")

    closure_id = str(uuid4())

    try:
        await db.execute(
            text("""
                INSERT INTO clonexa_closure_store (
                    id,
                    company_id,
                    module_code,
                    closure_date,
                    start_time,
                    end_time,
                    responsible,
                    notes,
                    status,
                    summary_text,
                    source_modules_text,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :company_id,
                    'day_closing',
                    :closure_date,
                    :start_time,
                    :end_time,
                    :responsible,
                    :notes,
                    :status,
                    :summary_text,
                    :source_modules_text,
                    now(),
                    now()
                )
            """),
            {
                "id": closure_id,
                "company_id": company_id,
                "closure_date": closure_date,
                "start_time": start_time,
                "end_time": end_time,
                "responsible": clean(payload.get("responsible")),
                "notes": clean(payload.get("notes")),
                "status": clean(payload.get("status") or "generated"),
                "summary_text": json.dumps(payload.get("summary") or {}, ensure_ascii=False),
                "source_modules_text": json.dumps(payload.get("source_modules") or [], ensure_ascii=False),
            },
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"closure_store_insert_failed: {type(exc).__name__}: {exc}")

    return {
        "id": closure_id,
        "company_id": company_id,
        "module_code": "day_closing",
        "date": closure_date,
        "start_time": start_time,
        "end_time": end_time,
        "status": clean(payload.get("status") or "generated"),
        "saved_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/companies/{company_id}/day")
async def list_day_closures(
    company_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await ensure_storage(db)

    limit = max(1, min(int(limit or 20), 100))

    result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                module_code,
                closure_date,
                start_time,
                end_time,
                responsible,
                notes,
                status,
                summary_text,
                source_modules_text,
                created_at::text AS created_at,
                updated_at::text AS updated_at
            FROM clonexa_closure_store
            WHERE company_id = :company_id
              AND module_code = 'day_closing'
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"company_id": company_id, "limit": limit},
    )

    rows = []

    for row in result.mappings().all():
        item = dict(row)
        item["date"] = item.pop("closure_date", "")
        item["summary"] = safe_json(item.pop("summary_text", "{}"), {})
        item["source_modules"] = safe_json(item.pop("source_modules_text", "[]"), [])
        rows.append(item)

    return rows
