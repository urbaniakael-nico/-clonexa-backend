from pathlib import Path
import re

endpoint_path = Path("app/api/v1/endpoints/day_closing.py")
router_path = Path("app/api/v1/router.py")
client_path = Path("app/web/client_day_closing.js")

endpoint_code = r'''
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
'''

client_code = r'''
(function clonexaDayClosingRealFix022BR3() {
  "use strict";

  if (window.__CLONEXA_022B_R3_DAY_CLOSING__) return;
  window.__CLONEXA_022B_R3_DAY_CLOSING__ = true;

  const API = "/api/v1";
  const LANG_KEY = "clonexa_client_language";

  const TXT = {
    es: {
      dashboard: "Dashboard",
      activeTenant: "Tenant activo",
      eyebrow: "Módulo cierre operativo",
      title: "Cierre de día",
      subtitle: "Genera el cierre operativo por fecha y jornada laboral. CLONEXA consolida eventos reales, personal, GPS, materiales, inventario y resúmenes enviados desde el bot.",
      live: "CIERRE POR JORNADA",

      generate: "Generar cierre",
      save: "Guardar cierre",
      pdf: "PDF",
      csv: "CSV",
      back: "Volver",

      control: "Control de jornada",
      date: "Fecha",
      startTime: "Hora inicio",
      endTime: "Hora fin",
      responsible: "Responsable",
      notes: "Observaciones del responsable",
      notesPlaceholder: "Notas internas del responsable del cierre. Esto no reemplaza los resúmenes enviados por el equipo desde el bot.",
      source: "Fuente: eventos reales filtrados por empresa, fecha y rango horario.",

      summary: "Resumen ejecutivo",
      people: "Personas con actividad",
      events: "Eventos",
      shiftStarts: "Turnos iniciados",
      shiftEnds: "Turnos cerrados",
      breaks: "Pausas",
      gps: "GPS enviados",
      materials: "Solicitudes material",
      lowStock: "Stock bajo",
      zeroStock: "Stock cero",

      activityChart: "Actividad de la jornada",
      personActivity: "Actividad por persona",
      teamSummaries: "Resúmenes enviados al cerrar turno",
      moduleBlocks: "Indicadores por módulo activo",

      employee: "Empleado",
      role: "Rol",
      first: "Primer evento",
      last: "Último evento",
      noPeople: "Sin actividad de personal en esta jornada.",
      noSummaries: "No hay resúmenes enviados desde el bot en este rango.",

      materialStatus: "Materiales por estado",
      inventoryStatus: "Inventario",
      workforce: "Workforce",
      saved: "Cierre guardado en PostgreSQL.",
      saveError: "No se pudo guardar el cierre.",
      loadError: "No se pudo generar el cierre.",

      inactiveTitle: "Módulo no activo",
      inactiveMsg: "Cierre de día no está activo para esta empresa.",
      activateFromAdmin: "Actívalo desde Admin V2 > Empresa > Módulos."
    },

    en: {
      dashboard: "Dashboard",
      activeTenant: "Active tenant",
      eyebrow: "Operational closing module",
      title: "Day closing",
      subtitle: "Generate the operational close by date and work shift. CLONEXA consolidates real events, staff, GPS, materials, inventory and summaries sent from the bot.",
      live: "SHIFT CLOSING",

      generate: "Generate closing",
      save: "Save closing",
      pdf: "PDF",
      csv: "CSV",
      back: "Back",

      control: "Shift control",
      date: "Date",
      startTime: "Start time",
      endTime: "End time",
      responsible: "Responsible",
      notes: "Responsible notes",
      notesPlaceholder: "Internal notes from the closing responsible. This does not replace team summaries sent from the bot.",
      source: "Source: real events filtered by company, date and time range.",

      summary: "Executive summary",
      people: "People with activity",
      events: "Events",
      shiftStarts: "Shift starts",
      shiftEnds: "Shift ends",
      breaks: "Breaks",
      gps: "GPS sent",
      materials: "Material requests",
      lowStock: "Low stock",
      zeroStock: "Zero stock",

      activityChart: "Shift activity",
      personActivity: "Activity by person",
      teamSummaries: "Summaries sent when closing shift",
      moduleBlocks: "Indicators by active module",

      employee: "Employee",
      role: "Role",
      first: "First event",
      last: "Last event",
      noPeople: "No staff activity for this shift.",
      noSummaries: "No summaries sent from the bot in this range.",

      materialStatus: "Materials by status",
      inventoryStatus: "Inventory",
      workforce: "Workforce",
      saved: "Closing saved in PostgreSQL.",
      saveError: "Could not save closing.",
      loadError: "Could not generate closing.",

      inactiveTitle: "Module not active",
      inactiveMsg: "Day closing is not active for this company.",
      activateFromAdmin: "Activate it from Admin V2 > Company > Modules."
    },

    fr: {
      dashboard: "Tableau de bord",
      activeTenant: "Tenant actif",
      eyebrow: "Module de clôture opérationnelle",
      title: "Clôture du jour",
      subtitle: "Générez la clôture opérationnelle par date et journée de travail. CLONEXA consolide les événements réels, le personnel, le GPS, les matériaux, l’inventaire et les résumés envoyés depuis le bot.",
      live: "CLÔTURE DE JOURNÉE",

      generate: "Générer la clôture",
      save: "Enregistrer la clôture",
      pdf: "PDF",
      csv: "CSV",
      back: "Retour",

      control: "Contrôle de journée",
      date: "Date",
      startTime: "Heure début",
      endTime: "Heure fin",
      responsible: "Responsable",
      notes: "Notes du responsable",
      notesPlaceholder: "Notes internes du responsable de clôture. Cela ne remplace pas les résumés envoyés par l’équipe depuis le bot.",
      source: "Source : événements réels filtrés par entreprise, date et plage horaire.",

      summary: "Résumé exécutif",
      people: "Personnes avec activité",
      events: "Événements",
      shiftStarts: "Services commencés",
      shiftEnds: "Services clôturés",
      breaks: "Pauses",
      gps: "GPS envoyés",
      materials: "Demandes de matériaux",
      lowStock: "Stock faible",
      zeroStock: "Stock zéro",

      activityChart: "Activité de la journée",
      personActivity: "Activité par personne",
      teamSummaries: "Résumés envoyés à la clôture",
      moduleBlocks: "Indicateurs par module actif",

      employee: "Employé",
      role: "Rôle",
      first: "Premier événement",
      last: "Dernier événement",
      noPeople: "Aucune activité du personnel pour cette journée.",
      noSummaries: "Aucun résumé envoyé depuis le bot dans cette plage.",

      materialStatus: "Matériaux par statut",
      inventoryStatus: "Inventaire",
      workforce: "Workforce",
      saved: "Clôture enregistrée dans PostgreSQL.",
      saveError: "Impossible d’enregistrer la clôture.",
      loadError: "Impossible de générer la clôture.",

      inactiveTitle: "Module non actif",
      inactiveMsg: "La clôture du jour n’est pas active pour cette entreprise.",
      activateFromAdmin: "Activez-le depuis Admin V2 > Entreprise > Modules."
    }
  };

  const MODULE_TITLES = {
    day_closing: ["Cierre de día", "Day closing", "Clôture du jour"],
    commercial_closing: ["Cierre comercial", "Commercial closing", "Clôture commerciale"],
    workforce: ["Personal", "Staff", "Personnel"],
    gps: ["GPS", "GPS", "GPS"],
    payroll: ["Nómina", "Payroll", "Paie"],
    bots: ["Bots", "Bots", "Bots"],
    inventory: ["Inventario", "Inventory", "Inventaire"],
    materials: ["Materiales", "Materials", "Matériaux"],
    crm: ["CRM Campo", "Field CRM", "CRM terrain"],
    kpis: ["KPIs", "KPIs", "KPIs"],
    reports: ["Reportes", "Reports", "Rapports"]
  };

  let lastReport = null;
  let lastContext = null;

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function t(key) {
    return TXT[lang()][key] || TXT.es[key] || key;
  }

  function moduleTitle(code, fallback) {
    const index = lang() === "en" ? 1 : lang() === "fr" ? 2 : 0;
    return MODULE_TITLES[code] ? MODULE_TITLES[code][index] : fallback || code;
  }

  function h(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function n(value) {
    const num = Number(value || 0);
    return Number.isFinite(num) ? num.toLocaleString() : "0";
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function companyIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || "";
  }

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });

    if (!response.ok) {
      let detail = "";
      try {
        const payload = await response.json();
        detail = payload.detail || payload.message || "";
      } catch (_) {}
      throw new Error(detail || `${response.status}`);
    }

    if (response.status === 204) return null;
    return response.json();
  }

  function normalizeModule(row) {
    const source = row.module || row.module_ref || row.global_module || row;
    const code = String(source.code || source.module_code || row.module_code || row.code || "").trim();
    const enabled = row.enabled ?? source.enabled ?? row.is_active ?? source.is_active ?? true;

    return {
      code,
      enabled: !!enabled,
      title: source.name || source.title || code
    };
  }

  async function loadContext(companyId) {
    const [companiesResult, modulesResult] = await Promise.allSettled([
      api("/companies"),
      api(`/companies/${encodeURIComponent(companyId)}/modules`)
    ]);

    const companies = companiesResult.status === "fulfilled" && Array.isArray(companiesResult.value)
      ? companiesResult.value
      : [];

    const company = companies.find((item) => item.id === companyId || item.company_id === companyId) || {
      id: companyId,
      company_id: companyId,
      name: document.querySelector(".client-company-name")?.textContent || "CLONEXA",
      slug: "tenant"
    };

    const modules = modulesResult.status === "fulfilled" && Array.isArray(modulesResult.value)
      ? modulesResult.value.map(normalizeModule).filter((item) => item.code && item.enabled)
      : [];

    return {
      company,
      modules,
      codes: new Set(modules.map((item) => item.code))
    };
  }

  function sidebar(company, modules, activeCode = "day_closing") {
    const visible = modules.filter((m) => !["core", "core_settings", "settings"].includes(m.code));

    return `
      <aside class="client-sidebar">
        <div class="client-logo">${h((company.name || "CLONEXA").slice(0, 2).toUpperCase())}</div>
        <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
        <div class="client-muted">${h(company.slug || "tenant")}</div>

        <nav class="client-nav">
          <button type="button" data-clx-day-dashboard>${h(t("dashboard"))}</button>
          ${visible.map((module) => `
            <button class="${module.code === activeCode ? "active" : ""}" type="button" data-client-module="${h(module.code)}">
              ${h(moduleTitle(module.code, module.title))}
            </button>
          `).join("")}
        </nav>

        <div class="client-footer-id">
          <strong>${h(t("activeTenant"))}</strong><br>${h(company.id || company.company_id || companyIdFromUrl())}
        </div>
      </aside>
    `;
  }

  function card(label, value) {
    return `
      <div class="cx-day-kpi">
        <span>${h(label)}</span>
        <strong>${h(value)}</strong>
      </div>
    `;
  }

  function row(label, value) {
    return `
      <div class="cx-day-row">
        <span>${h(label)}</span>
        <strong>${h(value)}</strong>
      </div>
    `;
  }

  function bar(label, value, max) {
    const pct = max > 0 ? Math.max(3, Math.round((Number(value || 0) / max) * 100)) : 3;

    return `
      <div class="cx-day-bar-row">
        <span>${h(label)}</span>
        <div class="cx-day-bar"><i style="width:${pct}%"></i></div>
        <strong>${h(n(value))}</strong>
      </div>
    `;
  }

  function fmtTime(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString();
    } catch (_) {
      return String(value);
    }
  }

  function peopleTable(report) {
    const people = report.people || [];

    if (!people.length) {
      return `<p class="client-muted">${h(t("noPeople"))}</p>`;
    }

    return `
      <div class="client-table-wrap">
        <table class="client-table">
          <thead>
            <tr>
              <th>${h(t("employee"))}</th>
              <th>${h(t("role"))}</th>
              <th>${h(t("events"))}</th>
              <th>${h(t("shiftStarts"))}</th>
              <th>${h(t("shiftEnds"))}</th>
              <th>${h(t("breaks"))}</th>
              <th>${h(t("gps"))}</th>
              <th>${h(t("first"))}</th>
              <th>${h(t("last"))}</th>
            </tr>
          </thead>
          <tbody>
            ${people.map((person) => `
              <tr>
                <td>${h(person.name)}</td>
                <td>${h(person.role || "—")}</td>
                <td>${h(n(person.events))}</td>
                <td>${h(n(person.shift_starts))}</td>
                <td>${h(n(person.shift_ends))}</td>
                <td>${h(n(person.breaks))}</td>
                <td>${h(n(person.gps))}</td>
                <td>${h(fmtTime(person.first_event))}</td>
                <td>${h(fmtTime(person.last_event))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function summariesBlock(report) {
    const summaries = report.closing_summaries || [];

    if (!summaries.length) {
      return `<p class="client-muted">${h(t("noSummaries"))}</p>`;
    }

    return summaries.map((item) => `
      <article class="cx-day-note">
        <strong>${h(item.employee)}</strong>
        <span>${h(item.role || "")} · ${h(fmtTime(item.time))}</span>
        <p>${h(item.summary)}</p>
      </article>
    `).join("");
  }

  function moduleBlocks(report) {
    const metrics = report.metrics || {};
    const materials = report.materials || {};
    const inventory = report.inventory || {};
    const materialStatus = materials.by_status || {};

    return `
      <section class="cx-day-block">
        <div class="client-eyebrow">WORKFORCE</div>
        <h2>${h(t("workforce"))}</h2>
        <div class="cx-day-list">
          ${row(t("people"), metrics.people)}
          ${row(t("shiftStarts"), metrics.shift_starts)}
          ${row(t("shiftEnds"), metrics.shift_ends)}
          ${row(t("breaks"), metrics.breaks)}
        </div>
      </section>

      <section class="cx-day-block">
        <div class="client-eyebrow">GPS</div>
        <h2>GPS</h2>
        <div class="cx-day-list">
          ${row(t("gps"), metrics.gps)}
        </div>
      </section>

      <section class="cx-day-block">
        <div class="client-eyebrow">MATERIALES</div>
        <h2>${h(t("materialStatus"))}</h2>
        <div class="cx-day-list">
          ${row(t("materials"), materials.total || 0)}
          ${Object.keys(materialStatus).length
            ? Object.entries(materialStatus).map(([status, count]) => row(status, count)).join("")
            : row("Sin estados", 0)}
        </div>
      </section>

      <section class="cx-day-block">
        <div class="client-eyebrow">INVENTARIO</div>
        <h2>${h(t("inventoryStatus"))}</h2>
        <div class="cx-day-list">
          ${row("Items", inventory.items || 0)}
          ${row(t("lowStock"), inventory.low_stock || 0)}
          ${row(t("zeroStock"), inventory.zero_stock || 0)}
        </div>
      </section>
    `;
  }

  function ensureStyles() {
    if (document.getElementById("clx-day-closing-r3-styles")) return;

    const style = document.createElement("style");
    style.id = "clx-day-closing-r3-styles";
    style.textContent = `
      .cx-day-toolbar {
        display:grid;
        grid-template-columns: repeat(4, minmax(150px, 1fr));
        gap:14px;
        align-items:end;
        margin-top:18px;
      }

      .cx-day-toolbar label,
      .cx-day-notes-label {
        display:grid;
        gap:8px;
        color:rgba(255,255,255,.72);
        font-weight:900;
        letter-spacing:.08em;
        text-transform:uppercase;
        font-size:12px;
      }

      .cx-day-toolbar input,
      .cx-day-notes-label textarea {
        width:100%;
        border:1px solid rgba(255,255,255,.14);
        background:rgba(0,0,0,.28);
        color:white;
        border-radius:16px;
        padding:13px 14px;
        font-weight:800;
        outline:none;
      }

      .cx-day-notes-label textarea {
        min-height:82px;
        resize:vertical;
      }

      .cx-day-kpi-grid {
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
        gap:12px;
        margin-top:18px;
      }

      .cx-day-kpi {
        min-height:88px;
        border:1px solid rgba(255,255,255,.12);
        background:linear-gradient(135deg,rgba(255,255,255,.08),rgba(255,0,180,.12));
        border-radius:18px;
        padding:16px;
        display:grid;
        align-content:center;
        gap:8px;
      }

      .cx-day-kpi span {
        color:rgba(255,255,255,.72);
        font-weight:900;
        font-size:13px;
      }

      .cx-day-kpi strong {
        color:white;
        font-size:30px;
        line-height:1;
        font-weight:1000;
      }

      .cx-day-grid {
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
        gap:16px;
        margin-top:18px;
      }

      .cx-day-block {
        border:1px solid rgba(255,255,255,.11);
        background:linear-gradient(135deg,rgba(255,255,255,.07),rgba(255,0,180,.08));
        border-radius:22px;
        padding:20px;
        box-shadow:0 18px 48px rgba(0,0,0,.18);
      }

      .cx-day-list {
        display:grid;
        gap:10px;
      }

      .cx-day-row {
        display:flex;
        justify-content:space-between;
        gap:12px;
        align-items:center;
        border:1px solid rgba(255,255,255,.08);
        background:rgba(255,255,255,.06);
        padding:10px 12px;
        border-radius:13px;
      }

      .cx-day-row span {
        color:rgba(255,255,255,.76);
        font-weight:800;
      }

      .cx-day-row strong {
        color:white;
        font-weight:1000;
      }

      .cx-day-chart {
        display:grid;
        gap:12px;
      }

      .cx-day-bar-row {
        display:grid;
        grid-template-columns: 170px 1fr 50px;
        gap:12px;
        align-items:center;
      }

      .cx-day-bar-row span {
        font-weight:900;
        color:rgba(255,255,255,.82);
      }

      .cx-day-bar {
        height:13px;
        border-radius:999px;
        background:rgba(255,255,255,.12);
        overflow:hidden;
      }

      .cx-day-bar i {
        display:block;
        height:100%;
        border-radius:999px;
        background:linear-gradient(90deg,#20e0a0,#ff22be);
      }

      .cx-day-note {
        border:1px solid rgba(255,255,255,.10);
        background:rgba(255,255,255,.06);
        border-radius:18px;
        padding:16px;
        margin-bottom:10px;
      }

      .cx-day-note strong {
        display:block;
        color:white;
        font-size:16px;
      }

      .cx-day-note span {
        display:block;
        color:rgba(255,255,255,.62);
        margin-top:4px;
        font-size:12px;
        font-weight:800;
      }

      .cx-day-note p {
        margin:10px 0 0;
        color:rgba(255,255,255,.86);
        line-height:1.45;
      }

      @media (max-width: 980px) {
        .cx-day-toolbar {
          grid-template-columns:1fr;
        }
      }

      @media print {
        body * { visibility:hidden !important; }
        [data-day-closing-root], [data-day-closing-root] * { visibility:visible !important; }
        [data-day-closing-root] {
          position:absolute;
          inset:0;
          background:white !important;
          color:black !important;
        }
        .client-sidebar, .client-actions, textarea, input { display:none !important; }
        .client-main { width:100% !important; }
      }
    `;
    document.head.appendChild(style);
  }

  async function fetchJourney() {
    const companyId = companyIdFromUrl();
    const date = document.querySelector("[data-day-date]")?.value || today();
    const startTime = document.querySelector("[data-day-start]")?.value || "07:00";
    const endTime = document.querySelector("[data-day-end]")?.value || "18:00";

    const query = new URLSearchParams({
      date,
      start_time: startTime,
      end_time: endTime
    });

    const report = await api(`/day-closing/companies/${encodeURIComponent(companyId)}/journey?${query.toString()}`);
    lastReport = report;
    renderReport(report);
  }

  function renderReport(report) {
    const metrics = report.metrics || {};
    const max = Math.max(
      metrics.shift_starts || 0,
      metrics.shift_ends || 0,
      metrics.breaks || 0,
      metrics.gps || 0,
      metrics.materials || 0,
      1
    );

    const chart = [
      bar(t("shiftStarts"), metrics.shift_starts, max),
      bar(t("shiftEnds"), metrics.shift_ends, max),
      bar(t("breaks"), metrics.breaks, max),
      bar(t("gps"), metrics.gps, max),
      bar(t("materials"), metrics.materials, max)
    ].join("");

    const target = document.querySelector("[data-day-report]");
    if (!target) return;

    target.innerHTML = `
      <section class="client-panel">
        <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start">
          <div>
            <div class="client-eyebrow">${h(t("summary"))}</div>
            <h2>${h(t("summary"))}</h2>
            <p class="client-muted">${h(report.date)} · ${h(report.start_time)} - ${h(report.end_time)}</p>
          </div>
          <span class="client-badge">${h(n(metrics.events))} ${h(t("events"))}</span>
        </div>

        <div class="cx-day-kpi-grid">
          ${card(t("people"), metrics.people)}
          ${card(t("events"), metrics.events)}
          ${card(t("shiftStarts"), metrics.shift_starts)}
          ${card(t("shiftEnds"), metrics.shift_ends)}
          ${card(t("breaks"), metrics.breaks)}
          ${card(t("gps"), metrics.gps)}
          ${card(t("materials"), metrics.materials)}
          ${card(t("lowStock"), metrics.low_stock)}
        </div>
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("activityChart"))}</div>
        <h2>${h(t("activityChart"))}</h2>
        <div class="cx-day-chart">${chart}</div>
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("personActivity"))}</div>
        <h2>${h(t("personActivity"))}</h2>
        ${peopleTable(report)}
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("teamSummaries"))}</div>
        <h2>${h(t("teamSummaries"))}</h2>
        ${summariesBlock(report)}
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("moduleBlocks"))}</div>
        <h2>${h(t("moduleBlocks"))}</h2>
        <div class="cx-day-grid">${moduleBlocks(report)}</div>
      </section>
    `;
  }

  function renderInactive(company, modules) {
    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          ${sidebar(company, modules, "dashboard")}
          <section class="client-main">
            <section class="client-panel" style="max-width:900px;margin:12vh auto">
              <div class="client-eyebrow">${h(t("eyebrow"))}</div>
              <h1>${h(t("inactiveTitle"))}</h1>
              <p>${h(t("inactiveMsg"))}</p>
              <p class="client-muted">${h(t("activateFromAdmin"))}</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-clx-day-dashboard>${h(t("back"))}</button>
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }

  async function renderDayClosing() {
    ensureStyles();

    const companyId = companyIdFromUrl();
    const context = await loadContext(companyId);
    lastContext = context;

    if (!context.codes.has("day_closing")) {
      renderInactive(context.company, context.modules);
      return;
    }

    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
      <main class="client-shell" data-day-closing-root>
        <div class="client-layout">
          ${sidebar(context.company, context.modules, "day_closing")}

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">${h(t("eyebrow"))}</div>
              <h1 class="client-title">${h(t("title"))}</h1>
              <p class="client-muted">${h(t("subtitle"))}</p>
              <span class="client-badge" style="position:absolute;right:28px;top:28px">${h(t("live"))}</span>

              <div class="client-actions">
                <button class="client-btn" type="button" data-day-generate>${h(t("generate"))}</button>
                <button class="client-btn" type="button" data-day-save>${h(t("save"))}</button>
                <button class="client-btn" type="button" data-day-pdf>${h(t("pdf"))}</button>
                <button class="client-btn" type="button" data-day-csv>${h(t("csv"))}</button>
                <button class="client-btn" type="button" data-clx-day-dashboard>${h(t("back"))}</button>
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">${h(t("control"))}</div>
              <h2>${h(t("control"))}</h2>

              <div class="cx-day-toolbar">
                <label>${h(t("date"))}<input type="date" data-day-date value="${h(today())}"></label>
                <label>${h(t("startTime"))}<input type="time" data-day-start value="07:00"></label>
                <label>${h(t("endTime"))}<input type="time" data-day-end value="18:00"></label>
                <label>${h(t("responsible"))}<input type="text" data-day-responsible value="${h(context.company.name || "")}"></label>
              </div>

              <div style="margin-top:18px">
                <label class="cx-day-notes-label">
                  ${h(t("notes"))}
                  <textarea data-day-notes placeholder="${h(t("notesPlaceholder"))}"></textarea>
                </label>
              </div>

              <p class="client-muted" style="margin-top:14px">${h(t("source"))}</p>
            </section>

            <div data-day-report></div>
          </section>
        </div>
      </main>
    `;

    await fetchJourney();
  }

  function showNotice(message, error = false) {
    const panel = document.querySelector("[data-day-closing-root] .client-panel");
    if (!panel) return;

    const box = document.createElement("div");
    box.className = `personal-toast ${error ? "error" : ""}`;
    box.textContent = message;
    panel.prepend(box);
    setTimeout(() => box.remove(), 3600);
  }

  function payload() {
    if (!lastReport) return null;

    return {
      date: lastReport.date,
      start_time: lastReport.start_time,
      end_time: lastReport.end_time,
      responsible: document.querySelector("[data-day-responsible]")?.value || "",
      notes: document.querySelector("[data-day-notes]")?.value || "",
      status: "generated",
      source_modules: lastReport.active_modules || [],
      summary: {
        metrics: lastReport.metrics || {},
        people: lastReport.people || [],
        closing_summaries: lastReport.closing_summaries || [],
        materials: lastReport.materials || {},
        inventory: lastReport.inventory || {},
        generated_at: lastReport.generated_at
      }
    };
  }

  async function saveClosing() {
    const data = payload();
    if (!data) return;

    try {
      const companyId = companyIdFromUrl();
      const response = await api(`/day-closing/companies/${encodeURIComponent(companyId)}/closures`, {
        method: "POST",
        body: JSON.stringify(data)
      });
      showNotice(`${t("saved")} ID: ${response.id}`);
    } catch (error) {
      showNotice(`${t("saveError")} ${error.message || ""}`, true);
    }
  }

  function downloadCsv() {
    const data = payload();
    if (!data) return;

    const people = data.summary.people || [];
    const summaries = data.summary.closing_summaries || [];

    const rows = [
      ["company_id", companyIdFromUrl()],
      ["date", data.date],
      ["start_time", data.start_time],
      ["end_time", data.end_time],
      ["responsible", data.responsible],
      ["notes", data.notes],
      [],
      ["metric", "value"],
      ...Object.entries(data.summary.metrics || {}),
      [],
      ["employee", "role", "events", "shift_starts", "shift_ends", "breaks", "gps", "first_event", "last_event"],
      ...people.map((person) => [
        person.name,
        person.role,
        person.events,
        person.shift_starts,
        person.shift_ends,
        person.breaks,
        person.gps,
        person.first_event,
        person.last_event
      ]),
      [],
      ["closing_summary_employee", "role", "time", "summary"],
      ...summaries.map((item) => [item.employee, item.role, item.time, item.summary])
    ];

    const csv = rows.map((row) => row.map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");

    a.href = url;
    a.download = `clonexa_day_closing_${data.date}_${data.start_time.replace(":", "")}_${data.end_time.replace(":", "")}.csv`;
    a.click();

    URL.revokeObjectURL(url);
  }

  document.addEventListener("click", async (event) => {
    const moduleButton = event.target.closest && event.target.closest('[data-client-module="day_closing"]');

    if (moduleButton) {
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      await renderDayClosing();
      return;
    }

    if (event.target.closest && event.target.closest("[data-clx-day-dashboard]")) {
      event.preventDefault();
      window.location.href = `/client?company_id=${encodeURIComponent(companyIdFromUrl())}`;
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-generate]")) {
      event.preventDefault();
      try {
        await fetchJourney();
      } catch (error) {
        showNotice(`${t("loadError")} ${error.message || ""}`, true);
      }
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-save]")) {
      event.preventDefault();
      await saveClosing();
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-csv]")) {
      event.preventDefault();
      downloadCsv();
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-pdf]")) {
      event.preventDefault();
      window.print();
      return;
    }
  }, true);

  window.CLONEXA_RENDER_DAY_CLOSING = renderDayClosing;
})();
'''

endpoint_path.write_text(endpoint_code, encoding="utf-8")
client_path.write_text(client_code, encoding="utf-8")

router = router_path.read_text(encoding="utf-8-sig")
if "day_closing_router" not in router:
    router += '''

# CLONEXA day closing router
from app.api.v1.endpoints import day_closing as day_closing_router
api_router.include_router(day_closing_router.router, prefix="/day-closing", tags=["day_closing"])
'''
router_path.write_text(router, encoding="utf-8")

print("PATCH_OK: 022B-R3 Day Closing real fix installed")
