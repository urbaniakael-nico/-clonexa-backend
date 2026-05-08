
from __future__ import annotations

import json
import re
from datetime import datetime, date as date_cls
from decimal import Decimal
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


EVENT_TABLES = [
    "work_events",
    "operation_events",
    "workforce_attendance_events",
    "attendance_events",
    "employee_events",
    "bot_events",
    "telegram_events",
]

MATERIAL_TABLES = [
    "material_requests",
    "field_material_requests",
]

INVENTORY_TABLES = [
    "inventory_items",
]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""

    # Repara textos tipo instalaciÃ³n cuando vienen mal decodificados.
    if "Ã" in raw or "Â" in raw:
        try:
            return raw.encode("latin1").decode("utf-8")
        except Exception:
            return raw

    return raw


def _json_load(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return fallback
    try:
        parsed = json.loads(str(value))
        return parsed
    except Exception:
        return fallback


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date_cls)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _validate_date(value: str) -> str:
    value = _clean(value)
    try:
        date_cls.fromisoformat(value)
    except Exception:
        raise HTTPException(status_code=422, detail="Fecha inválida. Usa YYYY-MM-DD.")
    return value


def _validate_time(value: str, field: str) -> str:
    value = _clean(value)[:5]
    if not re.match(r"^\d{2}:\d{2}$", value):
        raise HTTPException(status_code=422, detail=f"{field} inválida. Usa HH:MM.")
    hh, mm = value.split(":")
    if int(hh) > 23 or int(mm) > 59:
        raise HTTPException(status_code=422, detail=f"{field} fuera de rango.")
    return value


def _range_utc(date_value: str, start_time: str, end_time: str, tz_name: str) -> tuple[datetime, datetime]:
    try:
        tz = ZoneInfo(tz_name or "America/Bogota")
    except Exception:
        raise HTTPException(status_code=422, detail="Zona horaria inválida.")

    start_local = datetime.fromisoformat(f"{date_value}T{start_time}:00").replace(tzinfo=tz)
    end_local = datetime.fromisoformat(f"{date_value}T{end_time}:00").replace(tzinfo=tz)

    if end_local <= start_local:
        raise HTTPException(status_code=422, detail="La hora fin debe ser mayor a la hora inicio.")

    return (
        start_local.astimezone(ZoneInfo("UTC")),
        end_local.astimezone(ZoneInfo("UTC")),
    )


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name})
    return bool(result.scalar())


async def _columns(db: AsyncSession, table_name: str) -> set[str]:
    result = await db.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
        """),
        {"table_name": table_name},
    )
    return {str(row[0]) for row in result.all()}


def _select(cols: set[str], col: str, alias: str | None = None, default: str = "NULL") -> str:
    alias = alias or col
    if col not in cols:
        return f"{default} AS {alias}"

    if col in {"id", "company_id", "employee_id", "bot_instance_id", "inventory_item_id", "attendance_event_id"}:
        return f"{col}::text AS {alias}"

    return f"{col} AS {alias}"


async def _active_modules(db: AsyncSession, company_id: str) -> list[str]:
    try:
        if not await _table_exists(db, "company_modules") or not await _table_exists(db, "modules"):
            return []

        result = await db.execute(
            text("""
                SELECT DISTINCT m.code
                FROM company_modules cm
                JOIN modules m ON m.id = cm.module_id
                WHERE cm.company_id::text = :company_id
                  AND COALESCE(cm.enabled, true) IS TRUE
                  AND COALESCE(m.is_active, true) IS TRUE
                ORDER BY m.code
            """),
            {"company_id": company_id},
        )
        return [_clean(row[0]) for row in result.all() if _clean(row[0])]
    except Exception:
        await db.rollback()
        return []


async def _ensure_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS day_closing_v1 (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            closure_date text NOT NULL,
            start_time text NOT NULL,
            end_time text NOT NULL,
            timezone text NOT NULL DEFAULT 'America/Bogota',
            responsible text NULL,
            notes text NULL,
            status text NOT NULL DEFAULT 'generated',
            summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_modules_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_day_closing_v1_company_date
        ON day_closing_v1 (company_id, closure_date, created_at DESC)
    """))

    await db.commit()


def _row_dict(row: Any, source_table: str) -> dict[str, Any]:
    data = dict(row)
    data["source_table"] = source_table

    for key in ["payload_json", "metadata_json", "settings"]:
        if key in data:
            data[key] = _json_load(data.get(key), {})

    for key in ["detail", "notes", "event_label", "employee_name", "employee_role", "material_name", "name_reference"]:
        if key in data:
            data[key] = _clean(data.get(key))

    return _jsonable(data)


async def _fetch_event_rows(
    db: AsyncSession,
    company_id: str,
    start_utc: str,
    end_utc: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for table_name in EVENT_TABLES:
        try:
            if not await _table_exists(db, table_name):
                continue

            cols = await _columns(db, table_name)
            if "company_id" not in cols:
                continue

            ts_col = None
            for candidate in ["occurred_at", "created_at", "updated_at"]:
                if candidate in cols:
                    ts_col = candidate
                    break

            if not ts_col:
                continue

            select_parts = [
                _select(cols, "id"),
                _select(cols, "company_id"),
                _select(cols, "employee_id"),
                _select(cols, "event_type"),
                _select(cols, "event_label"),
                _select(cols, "employee_name"),
                _select(cols, "employee_role"),
                _select(cols, "status_after"),
                _select(cols, "module_code"),
                _select(cols, "source_channel"),
                _select(cols, "source_ref"),
                _select(cols, "bot_instance_id"),
                _select(cols, "detail"),
                _select(cols, "notes"),
                _select(cols, "payload_json", default="'{}'::jsonb"),
                _select(cols, "metadata_json", default="'{}'::jsonb"),
                _select(cols, "latitude"),
                _select(cols, "longitude"),
                _select(cols, "evidence_url"),
                _select(cols, "occurred_at"),
                _select(cols, "created_at"),
                _select(cols, "updated_at"),
            ]

            result = await db.execute(
                text(f"""
                    SELECT {", ".join(select_parts)}
                    FROM {table_name}
                    WHERE company_id::text = :company_id
                      AND {ts_col} >= CAST(:start_utc AS timestamptz)
                      AND {ts_col} <= CAST(:end_utc AS timestamptz)
                    ORDER BY {ts_col} ASC
                    LIMIT 3000
                """),
                {
                    "company_id": company_id,
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                },
            )

            for row in result.mappings().all():
                rows.append(_row_dict(row, table_name))

        except Exception as exc:
            await db.rollback()
            warnings.append(f"{table_name}: {type(exc).__name__}: {exc}")

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _clean(row.get("id")) or json.dumps(row, sort_keys=True, ensure_ascii=False)
        deduped[key] = row

    return list(deduped.values()), warnings


async def _fetch_material_rows(
    db: AsyncSession,
    company_id: str,
    start_utc: str,
    end_utc: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for table_name in MATERIAL_TABLES:
        try:
            if not await _table_exists(db, table_name):
                continue

            cols = await _columns(db, table_name)
            if "company_id" not in cols:
                continue

            time_cols = [
                col for col in [
                    "requested_at",
                    "created_at",
                    "approved_at",
                    "delivered_at",
                    "returned_at",
                    "consigned_at",
                    "status_updated_at",
                    "updated_at",
                ]
                if col in cols
            ]

            if not time_cols:
                continue

            time_filter = " OR ".join(
                f"({col} >= CAST(:start_utc AS timestamptz) AND {col} <= CAST(:end_utc AS timestamptz))"
                for col in time_cols
            )

            select_parts = [
                _select(cols, "id"),
                _select(cols, "company_id"),
                _select(cols, "order_number"),
                _select(cols, "employee_id"),
                _select(cols, "employee_name"),
                _select(cols, "employee_role"),
                _select(cols, "inventory_item_id"),
                _select(cols, "material_name"),
                _select(cols, "name_reference"),
                _select(cols, "item_size"),
                _select(cols, "size", alias="item_size_alt"),
                _select(cols, "color"),
                _select(cols, "quantity"),
                _select(cols, "quantity_returned"),
                _select(cols, "unit"),
                _select(cols, "destination"),
                _select(cols, "notes"),
                _select(cols, "operation_notes"),
                _select(cols, "status"),
                _select(cols, "source_channel"),
                _select(cols, "source_ref"),
                _select(cols, "attendance_event_id"),
                _select(cols, "requested_at"),
                _select(cols, "approved_at"),
                _select(cols, "delivered_at"),
                _select(cols, "returned_at"),
                _select(cols, "consigned_at"),
                _select(cols, "status_updated_at"),
                _select(cols, "created_at"),
                _select(cols, "updated_at"),
            ]

            order_candidates = [
                col for col in [
                    "status_updated_at",
                    "delivered_at",
                    "requested_at",
                    "created_at",
                    "updated_at",
                ]
                if col in cols
            ]

            order_expr = "COALESCE(" + ", ".join(order_candidates) + ")" if order_candidates else "1"

            result = await db.execute(
                text(f"""
                    SELECT {", ".join(select_parts)}
                    FROM {table_name}
                    WHERE company_id::text = :company_id
                      AND ({time_filter})
                    ORDER BY {order_expr} ASC NULLS LAST
                    LIMIT 3000
                """),
                {
                    "company_id": company_id,
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                },
            )

            for row in result.mappings().all():
                data = _row_dict(row, table_name)
                if not data.get("material_name") and data.get("name_reference"):
                    data["material_name"] = data["name_reference"]
                if not data.get("item_size") and data.get("item_size_alt"):
                    data["item_size"] = data["item_size_alt"]
                rows.append(data)

        except Exception as exc:
            await db.rollback()
            warnings.append(f"{table_name}: {type(exc).__name__}: {exc}")

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _clean(row.get("id")) or json.dumps(row, sort_keys=True, ensure_ascii=False)
        deduped[key] = row

    return list(deduped.values()), warnings


async def _fetch_inventory_rows(db: AsyncSession, company_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []

    for table_name in INVENTORY_TABLES:
        try:
            if not await _table_exists(db, table_name):
                continue

            cols = await _columns(db, table_name)
            if "company_id" not in cols:
                continue

            select_parts = [
                _select(cols, "id"),
                _select(cols, "company_id"),
                _select(cols, "sku"),
                _select(cols, "name"),
                _select(cols, "name_reference"),
                _select(cols, "size"),
                _select(cols, "color"),
                _select(cols, "category"),
                _select(cols, "unit"),
                _select(cols, "min_stock"),
                _select(cols, "current_stock"),
                _select(cols, "status"),
                _select(cols, "alert_low"),
                _select(cols, "created_at"),
                _select(cols, "updated_at"),
            ]

            result = await db.execute(
                text(f"""
                    SELECT {", ".join(select_parts)}
                    FROM {table_name}
                    WHERE company_id::text = :company_id
                    ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST
                    LIMIT 3000
                """),
                {"company_id": company_id},
            )

            return [_row_dict(row, table_name) for row in result.mappings().all()], warnings

        except Exception as exc:
            await db.rollback()
            warnings.append(f"{table_name}: {type(exc).__name__}: {exc}")

    return [], warnings


async def _fetch_employee_rows(db: AsyncSession, company_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []

    try:
        if not await _table_exists(db, "employees"):
            return [], warnings

        cols = await _columns(db, "employees")
        if "company_id" not in cols:
            return [], warnings

        select_parts = [
            _select(cols, "id"),
            _select(cols, "company_id"),
            _select(cols, "full_name"),
            _select(cols, "role"),
            _select(cols, "employee_type"),
            _select(cols, "status"),
            _select(cols, "telegram_user_id"),
            _select(cols, "telegram_username"),
            _select(cols, "created_at"),
            _select(cols, "updated_at"),
        ]

        result = await db.execute(
            text(f"""
                SELECT {", ".join(select_parts)}
                FROM employees
                WHERE company_id::text = :company_id
                ORDER BY full_name ASC NULLS LAST
                LIMIT 3000
            """),
            {"company_id": company_id},
        )

        return [_row_dict(row, "employees") for row in result.mappings().all()], warnings

    except Exception as exc:
        await db.rollback()
        warnings.append(f"employees: {type(exc).__name__}: {exc}")
        return [], warnings


def _event_time(row: dict[str, Any]) -> str:
    return _clean(row.get("occurred_at") or row.get("created_at") or row.get("updated_at"))


def _employee_key(row: dict[str, Any]) -> str:
    return _clean(row.get("employee_id")) or _clean(row.get("employee_name")) or "unknown"


def _employee_name(row: dict[str, Any]) -> str:
    return _clean(row.get("employee_name")) or "Sin nombre"


def _employee_role(row: dict[str, Any]) -> str:
    return _clean(row.get("employee_role")) or _clean(row.get("role")) or ""


def _event_type(row: dict[str, Any]) -> str:
    return _clean(row.get("event_type")).lower()


def _module_code(row: dict[str, Any]) -> str:
    return _clean(row.get("module_code")).lower()


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _json_load(row.get("payload_json"), {})
    return payload if isinstance(payload, dict) else {}


def _gps_status(row: dict[str, Any]) -> str:
    payload = _payload(row)
    metadata = _json_load(row.get("metadata_json"), {})
    if not isinstance(metadata, dict):
        metadata = {}
    return _clean(payload.get("gps_status") or metadata.get("gps_status") or row.get("gps_status")).lower()


def _summary_text(row: dict[str, Any]) -> str:
    payload = _payload(row)

    candidates = [
        payload.get("text"),
        payload.get("args"),
        payload.get("summary"),
        payload.get("end_shift_summary"),
        payload.get("management_summary"),
        row.get("detail"),
        row.get("notes"),
    ]

    generic = {
        "clx:cmd:pausa",
        "clx:cmd:reanudar",
        "clx:cmd:entrada",
        "clx:cmd:salida",
        "turno finalizado",
        "finalizar turno",
        "shift ended",
        "end shift",
        "checked_out",
        "working",
        "registered",
    }

    for candidate in candidates:
        value = _clean(candidate)
        if not value:
            continue
        if value.lower().startswith("clx:cmd"):
            continue
        if value.lower() in generic:
            continue
        if len(value) < 4:
            continue
        return value

    return ""


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    output: dict[str, int] = {}
    for row in rows:
        status = _clean(row.get("status") or "unknown").lower()
        output[status] = output.get(status, 0) + 1
    return output


def _build_people(events: list[dict[str, Any]], materials: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    people: dict[str, dict[str, Any]] = {}
    summaries: list[dict[str, Any]] = []

    def touch(key: str, name: str, role: str) -> dict[str, Any]:
        if key not in people:
            people[key] = {
                "employee_id": key if key != name else "",
                "name": name,
                "role": role,
                "events": 0,
                "shift_starts": 0,
                "shift_ends": 0,
                "breaks": 0,
                "gps": 0,
                "gps_inside": 0,
                "gps_outside": 0,
                "materials": 0,
                "first_event": "",
                "last_event": "",
                "summaries": [],
            }
        return people[key]

    for event in events:
        key = _employee_key(event)
        name = _employee_name(event)
        role = _employee_role(event)
        person = touch(key, name, role)

        person["events"] += 1

        ts = _event_time(event)
        if ts:
            if not person["first_event"]:
                person["first_event"] = ts
            person["last_event"] = ts

        event_type = _event_type(event)
        module_code = _module_code(event)
        gps_status = _gps_status(event)

        if event_type == "check_in":
            person["shift_starts"] += 1
        if event_type == "check_out":
            person["shift_ends"] += 1
        if event_type in {"break_start", "break_end"}:
            person["breaks"] += 1
        if module_code == "gps" or event_type == "gps_location" or event.get("latitude") or event.get("longitude"):
            person["gps"] += 1
            if gps_status == "inside":
                person["gps_inside"] += 1
            elif gps_status == "outside":
                person["gps_outside"] += 1

        summary = _summary_text(event)
        if summary and event_type == "check_out":
            item = {
                "employee_id": key if key != name else "",
                "employee": name,
                "role": role,
                "time": ts,
                "summary": summary,
                "source_channel": _clean(event.get("source_channel")),
                "source_ref": _clean(event.get("source_ref")),
            }
            person["summaries"].append(item)
            summaries.append(item)

    for material in materials:
        key = _clean(material.get("employee_id")) or _clean(material.get("employee_name")) or "unknown"
        name = _clean(material.get("employee_name")) or "Sin nombre"
        role = _clean(material.get("employee_role"))
        person = touch(key, name, role)

        person["events"] += 1
        person["materials"] += 1

        ts = _clean(
            material.get("requested_at")
            or material.get("created_at")
            or material.get("delivered_at")
            or material.get("updated_at")
        )
        if ts:
            if not person["first_event"]:
                person["first_event"] = ts
            person["last_event"] = ts

    return list(people.values()), summaries


def _build_inventory_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    active = [item for item in items if _clean(item.get("status") or "active").lower() == "active"]

    low_stock = 0
    zero_stock = 0
    total_units = 0.0
    critical_items = []

    for item in active:
        current = float(item.get("current_stock") or 0)
        minimum = float(item.get("min_stock") or 0)
        total_units += current

        if current <= 0:
            zero_stock += 1

        if minimum > 0 and current <= minimum:
            low_stock += 1
            critical_items.append(item)

    return {
        "items": len(items),
        "active": len(active),
        "low_stock": low_stock,
        "zero_stock": zero_stock,
        "total_stock_units": total_units,
        "critical_items": critical_items,
    }


def _build_material_summary(materials: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = _status_counts(materials)

    return {
        "total": len(materials),
        "pending": by_status.get("pending", 0),
        "approved": by_status.get("approved", 0),
        "delivered": by_status.get("delivered", 0),
        "returned": by_status.get("returned", 0),
        "returned_partial": by_status.get("returned_partial", 0),
        "consigned": by_status.get("consigned", 0),
        "consigned_partial": by_status.get("consigned_partial", 0),
        "rejected": by_status.get("rejected", 0),
        "by_status": by_status,
        "requests": materials,
    }


def _build_gps_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    gps_rows = [
        event for event in events
        if _module_code(event) == "gps"
        or _event_type(event) == "gps_location"
        or event.get("latitude")
        or event.get("longitude")
    ]

    inside = 0
    outside = 0
    unconfigured = 0

    locations = []

    for event in gps_rows:
        status = _gps_status(event)

        if status == "inside":
            inside += 1
        elif status == "outside":
            outside += 1
        else:
            unconfigured += 1

        locations.append({
            "employee_id": _employee_key(event),
            "employee": _employee_name(event),
            "time": _event_time(event),
            "latitude": event.get("latitude") or _payload(event).get("latitude"),
            "longitude": event.get("longitude") or _payload(event).get("longitude"),
            "status": status or "unknown",
            "detail": _clean(event.get("detail") or event.get("notes")),
            "source_ref": _clean(event.get("source_ref")),
        })

    return {
        "locations": len(gps_rows),
        "inside": inside,
        "outside": outside,
        "unconfigured": unconfigured,
        "rows": locations,
    }


def _build_attendance_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    checkins = sum(1 for event in events if _event_type(event) == "check_in")
    checkouts = sum(1 for event in events if _event_type(event) == "check_out")
    breaks = sum(1 for event in events if _event_type(event) in {"break_start", "break_end"})

    return {
        "events": len(events),
        "checkins": checkins,
        "checkouts": checkouts,
        "breaks": breaks,
    }


async def _preview_payload(
    db: AsyncSession,
    company_id: str,
    date_value: str,
    start_time: str,
    end_time: str,
    timezone: str,
) -> dict[str, Any]:
    date_value = _validate_date(date_value)
    start_time = _validate_time(start_time, "Hora inicio")
    end_time = _validate_time(end_time, "Hora fin")
    timezone = _clean(timezone) or "America/Bogota"

    start_utc, end_utc = _range_utc(date_value, start_time, end_time, timezone)

    active_modules = await _active_modules(db, company_id)
    if active_modules and "day_closing" not in active_modules:
        raise HTTPException(status_code=403, detail="day_closing no está activo para esta empresa.")

    events, event_warnings = await _fetch_event_rows(db, company_id, start_utc, end_utc)
    materials, material_warnings = await _fetch_material_rows(db, company_id, start_utc, end_utc)
    inventory_items, inventory_warnings = await _fetch_inventory_rows(db, company_id)
    employees, employee_warnings = await _fetch_employee_rows(db, company_id)

    people, closing_summaries = _build_people(events, materials)
    inventory_summary = _build_inventory_summary(inventory_items)
    material_summary = _build_material_summary(materials)
    gps_summary = _build_gps_summary(events)
    attendance_summary = _build_attendance_summary(events)

    metrics = {
        "people": len([person for person in people if person["name"] != "Sin nombre"]),
        "events": len(events) + len(materials),
        "attendance_events": len(events),
        "material_events": len(materials),
        "shift_starts": attendance_summary["checkins"],
        "shift_ends": attendance_summary["checkouts"],
        "breaks": attendance_summary["breaks"],
        "gps_locations": gps_summary["locations"],
        "gps_inside": gps_summary["inside"],
        "gps_outside": gps_summary["outside"],
        "materials_total": material_summary["total"],
        "materials_delivered": material_summary["delivered"],
        "materials_returned_partial": material_summary["returned_partial"],
        "inventory_items": inventory_summary["items"],
        "inventory_low_stock": inventory_summary["low_stock"],
        "inventory_zero_stock": inventory_summary["zero_stock"],
        "active_employees": len([e for e in employees if _clean(e.get("status")).lower() == "active"]),
        "archived_employees": len([e for e in employees if _clean(e.get("status")).lower() == "archived"]),
    }

    return {
        "company_id": company_id,
        "date": date_value,
        "start_time": start_time,
        "end_time": end_time,
        "timezone": timezone,
        "range_utc": {
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
        },
        "active_modules": active_modules,
        "metrics": metrics,
        "attendance": attendance_summary,
        "gps": gps_summary,
        "materials": material_summary,
        "inventory": inventory_summary,
        "people": people,
        "closing_summaries": closing_summaries,
        "employees": {
            "total": len(employees),
            "active": metrics["active_employees"],
            "archived": metrics["archived_employees"],
            "rows": employees,
        },
        "raw": {
            "events": events,
            "materials": materials,
        },
        "source_health": {
            "warnings": event_warnings + material_warnings + inventory_warnings + employee_warnings,
            "event_tables_checked": EVENT_TABLES,
            "material_tables_checked": MATERIAL_TABLES,
            "inventory_tables_checked": INVENTORY_TABLES,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/companies/{company_id}/preview")
async def preview_day_closing(
    company_id: str,
    date_value: str = Query(..., alias="date"),
    start_time: str = Query("07:00"),
    end_time: str = Query("18:00"),
    timezone: str = Query("America/Bogota"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await _preview_payload(db, company_id, date_value, start_time, end_time, timezone)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"day_closing_preview_failed: {type(exc).__name__}: {exc}")


@router.post("/companies/{company_id}/save")
async def save_day_closing(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)

    date_value = _validate_date(_clean(payload.get("date") or payload.get("closure_date")))
    start_time = _validate_time(_clean(payload.get("start_time") or "07:00"), "Hora inicio")
    end_time = _validate_time(_clean(payload.get("end_time") or "18:00"), "Hora fin")
    timezone = _clean(payload.get("timezone") or "America/Bogota")
    responsible = _clean(payload.get("responsible"))
    notes = _clean(payload.get("notes"))
    status = _clean(payload.get("status") or "generated")

    summary = await _preview_payload(db, company_id, date_value, start_time, end_time, timezone)

    # El preview consulta fuentes opcionales. Si alguna falla y fue capturada,
    # PostgreSQL puede dejar la transacción en aborted. Limpiamos antes de guardar.
    await db.rollback()

    summary["responsible"] = responsible
    summary["notes"] = notes
    summary["status"] = status

    closure_id = str(uuid4())

    try:
        await db.execute(
            text("""
                INSERT INTO day_closing_v1 (
                    id,
                    company_id,
                    closure_date,
                    start_time,
                    end_time,
                    timezone,
                    responsible,
                    notes,
                    status,
                    summary_json,
                    source_modules_json,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :closure_date,
                    :start_time,
                    :end_time,
                    :timezone,
                    :responsible,
                    :notes,
                    :status,
                    CAST(:summary_json AS jsonb),
                    CAST(:source_modules_json AS jsonb),
                    now(),
                    now()
                )
            """),
            {
                "id": closure_id,
                "company_id": company_id,
                "closure_date": date_value,
                "start_time": start_time,
                "end_time": end_time,
                "timezone": timezone,
                "responsible": responsible,
                "notes": notes,
                "status": status,
                "summary_json": json.dumps(_jsonable(summary), ensure_ascii=False),
                "source_modules_json": json.dumps(summary.get("active_modules") or [], ensure_ascii=False),
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"day_closing_save_failed: {type(exc).__name__}: {exc}")

    return {
        "id": closure_id,
        "company_id": company_id,
        "date": date_value,
        "start_time": start_time,
        "end_time": end_time,
        "timezone": timezone,
        "status": status,
        "saved_at": datetime.utcnow().isoformat() + "Z",
        "metrics": summary.get("metrics") or {},
    }


@router.get("/companies/{company_id}/history")
async def history_day_closing(
    company_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _ensure_storage(db)

    try:
        result = await db.execute(
            text("""
                SELECT
                    id,
                    company_id,
                    closure_date,
                    start_time,
                    end_time,
                    timezone,
                    responsible,
                    notes,
                    status,
                    summary_json,
                    source_modules_json,
                    created_at::text AS created_at,
                    updated_at::text AS updated_at
                FROM day_closing_v1
                WHERE company_id = :company_id
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {
                "company_id": company_id,
                "limit": limit,
            },
        )

        rows = []
        for row in result.mappings().all():
            item = dict(row)
            item["date"] = item.pop("closure_date", "")
            item["summary"] = _jsonable(item.pop("summary_json", {}) or {})
            item["source_modules"] = _jsonable(item.pop("source_modules_json", []) or [])
            rows.append(item)

        return rows

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"day_closing_history_failed: {type(exc).__name__}: {exc}")
