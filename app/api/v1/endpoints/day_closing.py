
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _as_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower_blob(row: dict[str, Any]) -> str:
    payload = _as_json(row.get("payload_json"))
    parts = [
        row.get("event_label"),
        row.get("event_type"),
        row.get("action"),
        row.get("status"),
        row.get("status_after"),
        row.get("module_code"),
        row.get("detail"),
        row.get("notes"),
        json.dumps(payload, ensure_ascii=False),
    ]
    return " ".join(_clean(x) for x in parts).lower()


def _event_time(row: dict[str, Any]) -> str:
    return _clean(row.get("occurred_at") or row.get("created_at") or row.get("updated_at"))


def _employee_name(row: dict[str, Any]) -> str:
    return _clean(row.get("employee_name") or row.get("employee") or row.get("name") or "Sin nombre")


def _employee_role(row: dict[str, Any]) -> str:
    return _clean(row.get("employee_role") or row.get("role") or "")


def _summary_text(row: dict[str, Any]) -> str:
    payload = _as_json(row.get("payload_json"))
    candidates = [
        payload.get("summary"),
        payload.get("end_shift_summary"),
        payload.get("management_summary"),
        payload.get("shift_summary"),
        payload.get("text"),
        payload.get("message"),
        row.get("summary"),
        row.get("notes"),
        row.get("detail"),
        row.get("description"),
    ]

    generic = {
        "turno finalizado",
        "shift ended",
        "finalizar turno",
        "end shift",
        "checked_out",
        "working",
        "registered",
        "clx:cmd:finalizar",
        "clx:cmd:cerrar",
    }

    for item in candidates:
        value = _clean(item)
        if not value:
            continue
        if value.lower() in generic:
            continue
        if value.lower().startswith("clx:cmd"):
            continue
        if len(value) < 4:
            continue
        return value

    return ""


def _is_shift_start(row: dict[str, Any]) -> bool:
    blob = _lower_blob(row)
    return (
        "inicio de turno" in blob
        or "shift_started" in blob
        or "shift start" in blob
        or "check_in" in blob
        or "checked_in" in blob
        or "entrada" in blob
    )


def _is_shift_end(row: dict[str, Any]) -> bool:
    blob = _lower_blob(row)
    return (
        "finalizar turno" in blob
        or "turno finalizado" in blob
        or "shift_ended" in blob
        or "shift ended" in blob
        or "checked_out" in blob
        or "end shift" in blob
        or "cierre de jornada" in blob
    )


def _is_break(row: dict[str, Any]) -> bool:
    blob = _lower_blob(row)
    return "pausa" in blob or "break" in blob or "on_break" in blob


def _is_gps(row: dict[str, Any]) -> bool:
    blob = _lower_blob(row)
    return "gps" in blob or "ubicación" in blob or "ubicacion" in blob or "location" in blob


def _is_material(row: dict[str, Any]) -> bool:
    blob = _lower_blob(row)
    return "material" in blob or row.get("module_code") == "materials"


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:name)"), {"name": table_name})
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


def _select_col(cols: set[str], col: str, alias: str | None = None, default: str = "NULL") -> str:
    alias = alias or col
    if col in cols:
        if col.endswith("_id") or col == "id":
            return f"{col}::text AS {alias}"
        return f"{col} AS {alias}"
    return f"{default} AS {alias}"


async def _ensure_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS day_closures (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL,
            closure_type varchar(60) NOT NULL DEFAULT 'day_closing',
            closure_date date NOT NULL,
            start_time varchar(8) NOT NULL,
            end_time varchar(8) NOT NULL,
            responsible text NULL,
            status varchar(40) NOT NULL DEFAULT 'generated',
            notes text NULL,
            summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_modules jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    alters = [
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS closure_type varchar(60) NOT NULL DEFAULT 'day_closing'",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS closure_date date",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS start_time varchar(8)",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS end_time varchar(8)",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS responsible text NULL",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS status varchar(40) NOT NULL DEFAULT 'generated'",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS notes text NULL",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS summary_json jsonb NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS source_modules jsonb NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()",
        "ALTER TABLE day_closures ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()",
    ]

    for statement in alters:
        await db.execute(text(statement))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_day_closures_company_date
        ON day_closures (company_id, closure_date DESC, start_time, end_time)
    """))
    await db.commit()


async def _active_module_codes(db: AsyncSession, company_id: UUID) -> list[str]:
    if not await _table_exists(db, "company_modules"):
        return []

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
                SELECT DISTINCT cm.module_code AS code
                FROM company_modules cm
                WHERE cm.company_id = :company_id
                {active_clause}
            """),
            {"company_id": str(company_id)},
        )
        return [_clean(row.code) for row in result.mappings().all() if _clean(row.code)]

    joins = [
        ("modules", "module_id"),
        ("global_modules", "global_module_id"),
    ]

    for table_name, fk in joins:
        if fk not in cm_cols or not await _table_exists(db, table_name):
            continue

        mod_cols = await _columns(db, table_name)
        if "id" not in mod_cols or "code" not in mod_cols:
            continue

        result = await db.execute(
            text(f"""
                SELECT DISTINCT m.code AS code
                FROM company_modules cm
                JOIN {table_name} m ON m.id = cm.{fk}
                WHERE cm.company_id = :company_id
                {active_clause}
            """),
            {"company_id": str(company_id)},
        )
        return [_clean(row.code) for row in result.mappings().all() if _clean(row.code)]

    return []


async def _fetch_events(db: AsyncSession, company_id: UUID, closure_date: date, start_time: str, end_time: str) -> list[dict[str, Any]]:
    table = "workforce_attendance_events"
    if not await _table_exists(db, table):
        return []

    cols = await _columns(db, table)
    if "company_id" not in cols:
        return []

    ts_col = "occurred_at" if "occurred_at" in cols else "created_at" if "created_at" in cols else "updated_at" if "updated_at" in cols else None
    if not ts_col:
        return []

    select_parts = [
        _select_col(cols, "id"),
        _select_col(cols, "company_id"),
        _select_col(cols, "employee_id"),
        _select_col(cols, "employee_name"),
        _select_col(cols, "employee_role"),
        _select_col(cols, "event_type"),
        _select_col(cols, "event_label"),
        _select_col(cols, "module_code"),
        _select_col(cols, "source_channel"),
        _select_col(cols, "detail"),
        _select_col(cols, "notes"),
        _select_col(cols, "status"),
        _select_col(cols, "status_after"),
        _select_col(cols, "payload_json", default="'{}'::jsonb"),
        f"{ts_col} AS occurred_at",
        _select_col(cols, "created_at"),
        _select_col(cols, "updated_at"),
    ]

    start_ts = f"{closure_date.isoformat()} {start_time}:00"
    end_ts = f"{closure_date.isoformat()} {end_time}:00"

    result = await db.execute(
        text(f"""
            SELECT {", ".join(select_parts)}
            FROM {table}
            WHERE company_id = :company_id
              AND (
                    ({ts_col} >= CAST(:start_ts AS timestamptz) AND {ts_col} <= CAST(:end_ts AS timestamptz))
                    OR ({ts_col}::date = CAST(:day AS date))
                  )
            ORDER BY {ts_col} ASC
            LIMIT 2000
        """),
        {
            "company_id": str(company_id),
            "start_ts": start_ts,
            "end_ts": end_ts,
            "day": closure_date.isoformat(),
        },
    )

    rows = []
    for row in result.mappings().all():
        data = dict(row)
        data["payload_json"] = _as_json(data.get("payload_json"))
        rows.append(_jsonable(data))

    return rows


async def _fetch_materials(db: AsyncSession, company_id: UUID, closure_date: date) -> dict[str, Any]:
    if not await _table_exists(db, "material_requests"):
        return {"total": 0, "by_status": {}, "rows": []}

    cols = await _columns(db, "material_requests")
    if "company_id" not in cols:
        return {"total": 0, "by_status": {}, "rows": []}

    ts_col = "created_at" if "created_at" in cols else "requested_at" if "requested_at" in cols else "updated_at" if "updated_at" in cols else None
    status_col = "status" if "status" in cols else None

    select_parts = [
        _select_col(cols, "id"),
        _select_col(cols, "order_number"),
        _select_col(cols, "employee_name"),
        _select_col(cols, "employee_role"),
        _select_col(cols, "material_name"),
        _select_col(cols, "quantity"),
        _select_col(cols, "status"),
        _select_col(cols, "notes"),
    ]

    if ts_col:
        select_parts.append(f"{ts_col} AS created_at")
        where_date = f"AND {ts_col}::date = CAST(:day AS date)"
    else:
        select_parts.append("NULL AS created_at")
        where_date = ""

    result = await db.execute(
        text(f"""
            SELECT {", ".join(select_parts)}
            FROM material_requests
            WHERE company_id = :company_id
            {where_date}
            ORDER BY created_at DESC NULLS LAST
            LIMIT 1000
        """),
        {"company_id": str(company_id), "day": closure_date.isoformat()},
    )

    rows = [_jsonable(dict(row)) for row in result.mappings().all()]
    by_status: dict[str, int] = {}

    for row in rows:
        status = _clean(row.get("status") or "unknown").lower()
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "total": len(rows),
        "by_status": by_status,
        "rows": rows,
    }


async def _fetch_inventory(db: AsyncSession, company_id: UUID) -> dict[str, Any]:
    if not await _table_exists(db, "inventory_items"):
        return {"items": 0, "low_stock": 0, "zero_stock": 0, "units": 0}

    cols = await _columns(db, "inventory_items")
    if "company_id" not in cols:
        return {"items": 0, "low_stock": 0, "zero_stock": 0, "units": 0}

    current_col = "current_stock" if "current_stock" in cols else None
    min_col = "min_stock" if "min_stock" in cols else "minimum_stock" if "minimum_stock" in cols else None
    status_filter = "AND COALESCE(status, 'active') = 'active'" if "status" in cols else ""

    if not current_col:
        result = await db.execute(
            text(f"""
                SELECT COUNT(*) AS items
                FROM inventory_items
                WHERE company_id = :company_id
                {status_filter}
            """),
            {"company_id": str(company_id)},
        )
        items = int(result.scalar() or 0)
        return {"items": items, "low_stock": 0, "zero_stock": 0, "units": 0}

    low_expr = f"SUM(CASE WHEN COALESCE({current_col},0) <= COALESCE({min_col},0) AND COALESCE({min_col},0) > 0 THEN 1 ELSE 0 END)" if min_col else "0"

    result = await db.execute(
        text(f"""
            SELECT
                COUNT(*) AS items,
                {low_expr} AS low_stock,
                SUM(CASE WHEN COALESCE({current_col},0) <= 0 THEN 1 ELSE 0 END) AS zero_stock,
                COALESCE(SUM(COALESCE({current_col},0)),0) AS units
            FROM inventory_items
            WHERE company_id = :company_id
            {status_filter}
        """),
        {"company_id": str(company_id)},
    )

    row = result.mappings().first() or {}
    return {
        "items": int(row.get("items") or 0),
        "low_stock": int(row.get("low_stock") or 0),
        "zero_stock": int(row.get("zero_stock") or 0),
        "units": float(row.get("units") or 0),
    }


def _build_people(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    people: dict[str, dict[str, Any]] = {}
    summaries: list[dict[str, Any]] = []

    for event in events:
        name = _employee_name(event)
        if name not in people:
            people[name] = {
                "name": name,
                "role": _employee_role(event),
                "events": 0,
                "shift_starts": 0,
                "shift_ends": 0,
                "breaks": 0,
                "gps": 0,
                "materials": 0,
                "first_event": "",
                "last_event": "",
                "summaries": [],
            }

        person = people[name]
        person["events"] += 1

        ts = _event_time(event)
        if ts:
            if not person["first_event"]:
                person["first_event"] = ts
            person["last_event"] = ts

        if _is_shift_start(event):
            person["shift_starts"] += 1
        if _is_shift_end(event):
            person["shift_ends"] += 1
        if _is_break(event):
            person["breaks"] += 1
        if _is_gps(event):
            person["gps"] += 1
        if _is_material(event):
            person["materials"] += 1

        summary = _summary_text(event)
        if summary and (_is_shift_end(event) or "resumen" in _lower_blob(event) or "summary" in _lower_blob(event)):
            item = {
                "employee": name,
                "role": person["role"],
                "time": ts,
                "summary": summary,
            }
            person["summaries"].append(item)
            summaries.append(item)

    return list(people.values()), summaries


@router.get("/companies/{company_id}/journey")
async def generate_day_closing_journey(
    company_id: UUID,
    date_value: date = Query(..., alias="date"),
    start_time: str = "07:00",
    end_time: str = "18:00",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not re.match(r"^\d{2}:\d{2}$", start_time or ""):
        raise HTTPException(status_code=422, detail="start_time inválido. Usa HH:MM.")
    if not re.match(r"^\d{2}:\d{2}$", end_time or ""):
        raise HTTPException(status_code=422, detail="end_time inválido. Usa HH:MM.")

    active_modules = await _active_module_codes(db, company_id)
    events = await _fetch_events(db, company_id, date_value, start_time, end_time)
    people, summaries = _build_people(events)
    materials = await _fetch_materials(db, company_id, date_value)
    inventory = await _fetch_inventory(db, company_id)

    metrics = {
        "people": len([p for p in people if p["name"] != "Sin nombre"]),
        "events": len(events),
        "shift_starts": sum(1 for event in events if _is_shift_start(event)),
        "shift_ends": sum(1 for event in events if _is_shift_end(event)),
        "breaks": sum(1 for event in events if _is_break(event)),
        "gps": sum(1 for event in events if _is_gps(event)),
        "materials": int(materials.get("total") or 0),
        "inventory_items": int(inventory.get("items") or 0),
        "low_stock": int(inventory.get("low_stock") or 0),
        "zero_stock": int(inventory.get("zero_stock") or 0),
    }

    return {
        "company_id": str(company_id),
        "date": date_value.isoformat(),
        "start_time": start_time,
        "end_time": end_time,
        "active_modules": active_modules,
        "metrics": metrics,
        "people": people,
        "closing_summaries": summaries,
        "materials": materials,
        "inventory": inventory,
        "events": events[:300],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.post("/companies/{company_id}/closures")
async def save_day_closure(
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

    if not re.match(r"^\d{2}:\d{2}$", start_time):
        raise HTTPException(status_code=422, detail="start_time inválido.")
    if not re.match(r"^\d{2}:\d{2}$", end_time):
        raise HTTPException(status_code=422, detail="end_time inválido.")

    closure_id = uuid4()
    summary = _jsonable(payload.get("summary") or {})
    source_modules = _jsonable(payload.get("source_modules") or [])
    notes = _clean(payload.get("notes")) or None
    responsible = _clean(payload.get("responsible")) or None
    status_value = _clean(payload.get("status") or "generated")[:40]

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
async def list_day_closures(
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

    return [_jsonable(dict(row)) for row in result.mappings().all()]
