
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


async def _ensure_day_closing_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS day_closures (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL,
            closure_type varchar(60) NOT NULL DEFAULT 'day_closing',
            closure_date date NOT NULL,
            start_time varchar(8) NOT NULL,
            end_time varchar(8) NOT NULL,
            responsible text NULL,
            status varchar(40) NOT NULL DEFAULT 'draft',
            notes text NULL,
            summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_modules jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_day_closures_company_date
        ON day_closures (company_id, closure_date DESC, start_time, end_time)
    """))
    await db.commit()


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("SELECT to_regclass(:name) AS exists"),
        {"name": table_name},
    )
    return bool(result.scalar())


async def _columns(db: AsyncSession, table_name: str) -> set[str]:
    result = await db.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
        """),
        {"table_name": table_name},
    )
    return {str(row[0]) for row in result.all()}


async def _company_has_module(db: AsyncSession, company_id: UUID, code: str) -> bool:
    """
    Validación flexible para no romper esquemas existentes.
    Si no logra detectar la relación, permite continuar porque el frontend
    ya oculta módulos no activos. Si detecta relación y no está activo, bloquea.
    """
    if not await _table_exists(db, "company_modules"):
        return True

    cm_cols = await _columns(db, "company_modules")
    active_clause = ""
    if "enabled" in cm_cols:
        active_clause = " AND COALESCE(cm.enabled, true) IS TRUE "
    elif "is_active" in cm_cols:
        active_clause = " AND COALESCE(cm.is_active, true) IS TRUE "
    elif "active" in cm_cols:
        active_clause = " AND COALESCE(cm.active, true) IS TRUE "

    if "module_code" in cm_cols:
        result = await db.execute(
            text(f"""
                SELECT 1
                FROM company_modules cm
                WHERE cm.company_id = :company_id
                  AND cm.module_code = :code
                  {active_clause}
                LIMIT 1
            """),
            {"company_id": str(company_id), "code": code},
        )
        return result.scalar() is not None

    if "code" in cm_cols:
        result = await db.execute(
            text(f"""
                SELECT 1
                FROM company_modules cm
                WHERE cm.company_id = :company_id
                  AND cm.code = :code
                  {active_clause}
                LIMIT 1
            """),
            {"company_id": str(company_id), "code": code},
        )
        return result.scalar() is not None

    joins = [
        ("modules", "module_id"),
        ("global_modules", "global_module_id"),
    ]

    for table_name, fk in joins:
        if fk not in cm_cols:
            continue
        if not await _table_exists(db, table_name):
            continue
        mod_cols = await _columns(db, table_name)
        if "id" not in mod_cols or "code" not in mod_cols:
            continue

        result = await db.execute(
            text(f"""
                SELECT 1
                FROM company_modules cm
                JOIN {table_name} m ON m.id = cm.{fk}
                WHERE cm.company_id = :company_id
                  AND m.code = :code
                  {active_clause}
                LIMIT 1
            """),
            {"company_id": str(company_id), "code": code},
        )
        return result.scalar() is not None

    return True


def _validate_time(value: Any, field: str) -> str:
    value = str(value or "").strip()
    if not re_match_time(value):
        raise HTTPException(status_code=422, detail=f"{field} inválido. Usa HH:MM.")
    return value[:5]


def re_match_time(value: str) -> bool:
    import re
    return bool(re.match(r"^\d{2}:\d{2}(:\d{2})?$", value or ""))


@router.post("/companies/{company_id}/closures")
async def save_day_closure(
    company_id: UUID,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_day_closing_storage(db)

    if not await _company_has_module(db, company_id, "day_closing"):
        raise HTTPException(status_code=403, detail="day_closing no está activo para esta empresa.")

    raw_date = payload.get("date") or payload.get("closure_date")
    try:
        closure_date = date.fromisoformat(str(raw_date))
    except Exception:
        raise HTTPException(status_code=422, detail="Fecha inválida.")

    start_time = _validate_time(payload.get("start_time"), "start_time")
    end_time = _validate_time(payload.get("end_time"), "end_time")

    closure_id = uuid4()
    status_value = str(payload.get("status") or "draft").strip()[:40]
    responsible = str(payload.get("responsible") or "").strip() or None
    notes = str(payload.get("notes") or "").strip() or None
    summary_json = payload.get("summary") or {}
    source_modules = payload.get("source_modules") or []

    await db.execute(
        text("""
            INSERT INTO day_closures (
                id,
                company_id,
                closure_type,
                closure_date,
                start_time,
                end_time,
                responsible,
                status,
                notes,
                summary_json,
                source_modules,
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
                :status,
                :notes,
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
            "status": status_value,
            "notes": notes,
            "summary_json": __import__("json").dumps(summary_json, ensure_ascii=False),
            "source_modules": __import__("json").dumps(source_modules, ensure_ascii=False),
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
async def list_day_closures(
    company_id: UUID,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _ensure_day_closing_storage(db)

    limit = max(1, min(int(limit or 30), 100))

    result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                closure_date,
                start_time,
                end_time,
                responsible,
                status,
                notes,
                summary_json,
                source_modules,
                created_at,
                updated_at
            FROM day_closures
            WHERE company_id = :company_id
            ORDER BY closure_date DESC, created_at DESC
            LIMIT :limit
        """),
        {"company_id": str(company_id), "limit": limit},
    )

    return [dict(row) for row in result.mappings().all()]
