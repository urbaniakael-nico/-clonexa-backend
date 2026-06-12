from __future__ import annotations

import base64
import csv
import io
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

try:
    from app.api.v1.endpoints.kpis import (
        kpi_summary as kpis_summary_source,
        period_from_params as kpis_period_from_params,
        serialize as kpis_serialize,
    )
except Exception:  # pragma: no cover
    kpis_summary_source = None
    kpis_period_from_params = None
    kpis_serialize = None

try:
    from app.api.v1.endpoints.payroll import (
        calculate_period_snapshot as payroll_calculate_period_snapshot,
        ensure_payroll_storage as payroll_ensure_storage,
    )
except Exception:  # pragma: no cover
    payroll_calculate_period_snapshot = None
    payroll_ensure_storage = None


router = APIRouter()
UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def serialize(value: Any) -> Any:
    if kpis_serialize:
        try:
            return kpis_serialize(value)
        except Exception:
            pass
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize(v) for v in value]
    return value


def row_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    mapping = getattr(row, "_mapping", row)
    return {str(k): serialize(v) for k, v in dict(mapping).items()}


def normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def text_match(value: Any) -> str:
    return str(value or "").strip().lower()


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def int_num(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def minutes_to_hours(minutes: Any) -> float:
    return round(num(minutes) / 60, 2)


def parse_period(
    preset: str | None,
    start_date: date | None,
    end_date: date | None,
) -> tuple[datetime, datetime, str]:
    if kpis_period_from_params:
        try:
            return kpis_period_from_params(preset, start_date, end_date)
        except Exception:
            pass

    now = utcnow()
    end = datetime.combine(end_date, time.max, tzinfo=UTC) if end_date else now
    code = normalize(preset or "7d")
    if start_date:
        start = datetime.combine(start_date, time.min, tzinfo=UTC)
        code = "custom" if not preset else code
    elif code in {"today", "hoy", "day"}:
        start = datetime.combine(now.date(), time.min, tzinfo=UTC)
        code = "today"
    elif code in {"15d", "15", "quincena"}:
        start = now - timedelta(days=15)
        code = "15d"
    elif code in {"30d", "month", "mes"}:
        start = now - timedelta(days=30)
        code = "month"
    else:
        start = now - timedelta(days=7)
        code = "7d"
    if end < start:
        start, end = end, start
    return start, end, code


async def safe_rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception:
        pass


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    try:
        result = await db.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = CAST(:table_name AS text)
                )
            """),
            {"table_name": table_name},
        )
        return bool(result.scalar())
    except Exception:
        await safe_rollback(db)
        return False


async def rows(
    db: AsyncSession,
    sql: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    result = await db.execute(text(sql), params or {})
    return [row_dict(row) for row in result.mappings().all()]


def row_passes_filters(
    row: dict[str, Any],
    *,
    employee_id: str | None = None,
    module_code: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> bool:
    if employee_id:
        rid = str(row.get("employee_id") or "")
        if rid and rid != str(employee_id):
            return False
        if not rid and str(row.get("id") or "") != str(employee_id):
            return False

    if module_code and module_code not in {"all", "general"}:
        mod = normalize(row.get("module_code") or row.get("module") or "")
        if mod != normalize(module_code):
            return False

    if status and status not in {"all", "todos"}:
        row_status = normalize(row.get("status") or row.get("status_after") or row.get("state") or "")
        if normalize(status) not in row_status:
            return False

    if search:
        needle = text_match(search)
        hay = " ".join(str(v or "") for v in row.values()).lower()
        if needle not in hay:
            return False

    return True


def filter_list(
    items: list[dict[str, Any]],
    *,
    employee_id: str | None = None,
    module_code: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if row_passes_filters(item, employee_id=employee_id, module_code=module_code, status=status, search=search)
    ]


async def load_kpis(
    db: AsyncSession,
    company_id: UUID,
    preset: str,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, Any]:
    if not kpis_summary_source:
        return {}
    try:
        return await kpis_summary_source(
            company_id=company_id,
            preset=preset,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )
    except Exception:
        await safe_rollback(db)
        return {}


async def employee_rows(db: AsyncSession, company_id: UUID) -> list[dict[str, Any]]:
    if not await table_exists(db, "employees"):
        return []
    return await rows(
        db,
        """
        SELECT
            id,
            company_id,
            full_name,
            COALESCE(role, employee_type, '') AS role,
            COALESCE(status, 'active') AS status,
            telegram_user_id,
            telegram_username,
            hourly_rate_regular,
            hourly_rate_extra,
            deduction_1,
            deduction_2,
            created_at,
            updated_at
        FROM employees
        WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY full_name ASC
        LIMIT 1000
        """,
        {"company_id": str(company_id)},
    )


async def attendance_rows(db: AsyncSession, company_id: UUID, start: datetime, end: datetime) -> list[dict[str, Any]]:
    if not await table_exists(db, "workforce_attendance_events"):
        return []
    return await rows(
        db,
        """
        SELECT
            ev.id,
            ev.company_id,
            ev.employee_id,
            COALESCE(ev.employee_name, e.full_name, 'Sin empleado') AS employee_name,
            COALESCE(ev.employee_role, e.role, '') AS employee_role,
            COALESCE(ev.event_type, '') AS event_type,
            COALESCE(ev.event_label, '') AS event_label,
            COALESCE(ev.module_code, 'workforce') AS module_code,
            COALESCE(ev.source_channel, ev.source, '') AS source_channel,
            COALESCE(ev.status_after, '') AS status,
            COALESCE(ev.detail, ev.notes, '') AS detail,
            ev.payload_json,
            ev.metadata_json,
            COALESCE(ev.occurred_at, ev.created_at) AS occurred_at,
            ev.created_at
        FROM workforce_attendance_events ev
        LEFT JOIN employees e
          ON e.id = ev.employee_id
         AND e.company_id = ev.company_id
        WHERE ev.company_id = CAST(:company_id AS uuid)
          AND COALESCE(ev.occurred_at, ev.created_at) >= CAST(:start_ts AS timestamptz)
          AND COALESCE(ev.occurred_at, ev.created_at) <= CAST(:end_ts AS timestamptz)
        ORDER BY COALESCE(ev.occurred_at, ev.created_at) DESC
        LIMIT 1500
        """,
        {"company_id": str(company_id), "start_ts": start, "end_ts": end},
    )


async def material_rows(db: AsyncSession, company_id: UUID, start: datetime, end: datetime) -> list[dict[str, Any]]:
    if not await table_exists(db, "material_requests"):
        return []
    return await rows(
        db,
        """
        SELECT
            mr.id,
            mr.company_id,
            mr.employee_id,
            COALESCE(mr.employee_name, e.full_name, 'Sin empleado') AS employee_name,
            COALESCE(mr.employee_role, e.role, '') AS employee_role,
            COALESCE(mr.order_number, 'Sin orden') AS order_number,
            COALESCE(mr.material_name, ii.name_reference, ii.name, ii.reference, '') AS material_name,
            mr.inventory_item_id,
            COALESCE(mr.quantity, 0) AS quantity,
            COALESCE(mr.quantity_returned, 0) AS quantity_returned,
            COALESCE(mr.unit, '') AS unit,
            COALESCE(mr.status, '') AS status,
            COALESCE(mr.destination, '') AS destination,
            COALESCE(mr.notes, '') AS notes,
            COALESCE(mr.source_channel, '') AS source_channel,
            mr.requested_at,
            mr.approved_at,
            mr.delivered_at,
            mr.returned_at,
            mr.created_at,
            mr.updated_at,
            'materials' AS module_code
        FROM material_requests mr
        LEFT JOIN employees e
          ON e.id = mr.employee_id
         AND e.company_id = mr.company_id
        LEFT JOIN inventory_items ii
          ON ii.id = mr.inventory_item_id
         AND ii.company_id = mr.company_id
        WHERE mr.company_id = CAST(:company_id AS uuid)
          AND COALESCE(mr.requested_at, mr.created_at) >= CAST(:start_ts AS timestamptz)
          AND COALESCE(mr.requested_at, mr.created_at) <= CAST(:end_ts AS timestamptz)
        ORDER BY COALESCE(mr.requested_at, mr.created_at) DESC
        LIMIT 1500
        """,
        {"company_id": str(company_id), "start_ts": start, "end_ts": end},
    )


async def inventory_item_rows(db: AsyncSession, company_id: UUID) -> list[dict[str, Any]]:
    if not await table_exists(db, "inventory_items"):
        return []
    return await rows(
        db,
        """
        SELECT
            id,
            company_id,
            COALESCE(name_reference, name, reference, sku, '') AS name_reference,
            COALESCE(name, '') AS name,
            COALESCE(reference, '') AS reference,
            COALESCE(sku, '') AS sku,
            COALESCE(item_size, '') AS item_size,
            COALESCE(color, '') AS color,
            COALESCE(min_stock, minimum_stock, 0) AS min_stock,
            COALESCE(current_stock, stock_actual, stock, 0) AS current_stock,
            COALESCE(status, CASE WHEN COALESCE(is_active, true) THEN 'active' ELSE 'inactive' END) AS status,
            created_at,
            updated_at
        FROM inventory_items
        WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY name_reference ASC
        LIMIT 1500
        """,
        {"company_id": str(company_id)},
    )


async def inventory_movement_rows(db: AsyncSession, company_id: UUID, start: datetime, end: datetime) -> list[dict[str, Any]]:
    if not await table_exists(db, "inventory_movements"):
        return []
    return await rows(
        db,
        """
        SELECT
            mv.id,
            mv.company_id,
            mv.item_id,
            COALESCE(ii.name_reference, ii.name, ii.reference, ii.sku, '') AS item_name,
            COALESCE(mv.movement_type, mv.type, '') AS movement_type,
            COALESCE(mv.quantity_delta, mv.quantity, 0) AS quantity_delta,
            COALESCE(mv.source_module, '') AS source_module,
            COALESCE(mv.source_ref, '') AS source_ref,
            COALESCE(mv.notes, mv.reason, '') AS notes,
            COALESCE(mv.status, '') AS status,
            mv.created_at,
            'inventory' AS module_code
        FROM inventory_movements mv
        LEFT JOIN inventory_items ii
          ON ii.id = mv.item_id
         AND ii.company_id = mv.company_id
        WHERE mv.company_id = CAST(:company_id AS uuid)
          AND mv.created_at >= CAST(:start_ts AS timestamptz)
          AND mv.created_at <= CAST(:end_ts AS timestamptz)
        ORDER BY mv.created_at DESC
        LIMIT 1500
        """,
        {"company_id": str(company_id), "start_ts": start, "end_ts": end},
    )


async def payroll_rows(db: AsyncSession, company_id: UUID, start: datetime, end: datetime) -> list[dict[str, Any]]:
    if payroll_ensure_storage and payroll_calculate_period_snapshot:
        try:
            await payroll_ensure_storage(db)
            snapshot = await payroll_calculate_period_snapshot(db, company_id, start.date(), end.date())
            rows_ = snapshot.get("rows") or []
            out = []
            for item in rows_:
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                row["module_code"] = "payroll"
                row["status"] = row.get("status") or "calculated"
                out.append(serialize(row))
            return out
        except Exception:
            await safe_rollback(db)

    if not await table_exists(db, "payroll_period_items"):
        return []
    return await rows(
        db,
        """
        SELECT
            ppi.id,
            ppi.company_id,
            ppi.employee_id,
            COALESCE(ppi.employee_name, e.full_name, 'Sin empleado') AS employee_name,
            COALESCE(ppi.employee_role, e.role, '') AS employee_role,
            COALESCE(ppi.closed_shifts, 0) AS closed_shifts,
            COALESCE(ppi.regular_minutes, 0) AS regular_minutes,
            COALESCE(ppi.extra_minutes, 0) AS extra_minutes,
            COALESCE(ppi.hourly_rate_regular, 0) AS hourly_rate_regular,
            COALESCE(ppi.hourly_rate_extra, 0) AS hourly_rate_extra,
            COALESCE(ppi.deduction_1, 0) AS deduction_1,
            COALESCE(ppi.deduction_2, 0) AS deduction_2,
            COALESCE(ppi.gross_amount, 0) AS gross_amount,
            COALESCE(ppi.discount_amount, 0) AS discount_amount,
            COALESCE(ppi.net_amount, 0) AS net_amount,
            ppi.created_at,
            'payroll' AS module_code,
            'closed' AS status
        FROM payroll_period_items ppi
        LEFT JOIN employees e
          ON e.id = ppi.employee_id
         AND e.company_id = ppi.company_id
        WHERE ppi.company_id = CAST(:company_id AS uuid)
        ORDER BY ppi.created_at DESC
        LIMIT 1000
        """,
        {"company_id": str(company_id)},
    )


def gps_rows_from_attendance(attendance: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in attendance:
        mod = normalize(row.get("module_code"))
        ev = normalize(row.get("event_type"))
        if mod == "gps" or ev in {"gps_location", "gps_ping", "location", "ubicacion"}:
            data = dict(row)
            payload = data.get("payload_json") or {}
            meta = data.get("metadata_json") or {}
            if isinstance(payload, str):
                payload_txt = payload.lower()
            else:
                payload_txt = str(payload).lower()
            if isinstance(meta, str):
                meta_txt = meta.lower()
            else:
                meta_txt = str(meta).lower()
            status_txt = normalize(data.get("status"))
            if "inside" in status_txt or "dentro" in status_txt or "inside" in payload_txt or "dentro" in payload_txt:
                data["gps_status"] = "inside"
            elif "outside" in status_txt or "fuera" in status_txt or "outside" in payload_txt or "fuera" in payload_txt:
                data["gps_status"] = "outside"
            elif "inside" in meta_txt or "dentro" in meta_txt:
                data["gps_status"] = "inside"
            elif "outside" in meta_txt or "fuera" in meta_txt:
                data["gps_status"] = "outside"
            else:
                data["gps_status"] = data.get("status") or "registered"
            out.append(data)
    return out


def count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "sin_estado").strip() or "sin_estado"
        out[value] = out.get(value, 0) + 1
    return out


def period_days(start: datetime, end: datetime) -> list[str]:
    days = []
    current = start.date()
    final = end.date()
    max_days = 45
    while current <= final and len(days) < max_days:
        days.append(current.isoformat())
        current = current + timedelta(days=1)
    return days


def day_key(value: Any) -> str:
    if not value:
        return ""
    try:
        if isinstance(value, datetime):
            return value.date().isoformat()
        return str(value)[:10]
    except Exception:
        return ""


def build_charts(
    *,
    start: datetime,
    end: datetime,
    attendance: list[dict[str, Any]],
    materials: list[dict[str, Any]],
    gps: list[dict[str, Any]],
    inventory_items: list[dict[str, Any]],
    inventory_movements: list[dict[str, Any]],
    payroll: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    activity = {day: {"date": day, "turnos": 0, "gps": 0, "materiales": 0} for day in period_days(start, end)}

    for row in attendance:
        day = day_key(row.get("occurred_at") or row.get("created_at"))
        if day in activity and normalize(row.get("event_type")) == "check_in":
            activity[day]["turnos"] += 1
    for row in gps:
        day = day_key(row.get("occurred_at") or row.get("created_at"))
        if day in activity:
            activity[day]["gps"] += 1
    for row in materials:
        day = day_key(row.get("requested_at") or row.get("created_at"))
        if day in activity:
            activity[day]["materiales"] += 1

    material_status = [{"label": k, "value": v} for k, v in sorted(count_by(materials, "status").items())]

    gps_inside = len([r for r in gps if normalize(r.get("gps_status")) == "inside"])
    gps_outside = len([r for r in gps if normalize(r.get("gps_status")) == "outside"])
    gps_other = max(0, len(gps) - gps_inside - gps_outside)

    low = len([i for i in inventory_items if num(i.get("current_stock")) > 0 and num(i.get("current_stock")) <= num(i.get("min_stock"))])
    zero = len([i for i in inventory_items if num(i.get("current_stock")) <= 0])
    ok = max(0, len(inventory_items) - low - zero)

    payroll_totals = summary.get("payroll") or {}
    regular_hours = minutes_to_hours(payroll_totals.get("regular_minutes"))
    extra_hours = minutes_to_hours(payroll_totals.get("extra_minutes"))

    movement_in = sum(abs(num(m.get("quantity_delta"))) for m in inventory_movements if num(m.get("quantity_delta")) > 0)
    movement_out = sum(abs(num(m.get("quantity_delta"))) for m in inventory_movements if num(m.get("quantity_delta")) < 0)

    return {
        "activity_by_day": list(activity.values()),
        "materials_by_status": material_status,
        "gps_distribution": [
            {"label": "Dentro", "value": gps_inside},
            {"label": "Fuera", "value": gps_outside},
            {"label": "Sin clasificar", "value": gps_other},
        ],
        "inventory_status": [
            {"label": "OK", "value": ok},
            {"label": "Stock bajo", "value": low},
            {"label": "Stock cero", "value": zero},
        ],
        "payroll_breakdown": [
            {"label": "Horas ordinarias", "value": regular_hours},
            {"label": "Horas extra", "value": extra_hours},
            {"label": "Descuentos", "value": num(payroll_totals.get("discount_amount"))},
            {"label": "Total neto", "value": num(payroll_totals.get("net_amount"))},
        ],
        "inventory_movements": [
            {"label": "Entradas", "value": movement_in},
            {"label": "Salidas", "value": movement_out},
        ],
    }


def build_employee_summary(
    employees: list[dict[str, Any]],
    attendance: list[dict[str, Any]],
    materials: list[dict[str, Any]],
    gps: list[dict[str, Any]],
    payroll: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    people: dict[str, dict[str, Any]] = {}
    name_index: dict[str, str] = {}

    for employee in employees:
        employee_id = str(employee.get("id") or "")
        if not employee_id:
            continue
        people[employee_id] = {
            "employee_id": employee_id,
            "employee_name": employee.get("full_name") or "Sin empleado",
            "employee_role": employee.get("role") or "",
            "status": employee.get("status") or "",
            "turnos": 0,
            "eventos": 0,
            "pausas": 0,
            "gps": 0,
            "gps_fuera": 0,
            "materiales": 0,
            "material_entregado": 0,
            "material_devuelto": 0,
            "consignas": 0,
            "horas_ordinarias": 0.0,
            "horas_extra": 0.0,
            "total_nomina": 0.0,
            "alertas": 0,
        }
        name_index[text_match(employee.get("full_name"))] = employee_id

    def key_for(row: dict[str, Any]) -> str:
        employee_id = str(row.get("employee_id") or "")
        if employee_id:
            return employee_id
        name = text_match(row.get("employee_name"))
        if name in name_index:
            return name_index[name]
        if not name:
            name = "sin_empleado"
        if name not in people:
            people[name] = {
                "employee_id": "",
                "employee_name": row.get("employee_name") or "Sin empleado",
                "employee_role": row.get("employee_role") or "",
                "status": "",
                "turnos": 0,
                "eventos": 0,
                "pausas": 0,
                "gps": 0,
                "gps_fuera": 0,
                "materiales": 0,
                "material_entregado": 0,
                "material_devuelto": 0,
                "consignas": 0,
                "horas_ordinarias": 0.0,
                "horas_extra": 0.0,
                "total_nomina": 0.0,
                "alertas": 0,
            }
        return name

    for row in attendance:
        k = key_for(row)
        people[k]["eventos"] += 1
        ev = normalize(row.get("event_type"))
        if ev == "check_in":
            people[k]["turnos"] += 1
        if ev in {"break_start", "break_end"}:
            people[k]["pausas"] += 1

    for row in gps:
        k = key_for(row)
        people[k]["gps"] += 1
        if normalize(row.get("gps_status")) == "outside":
            people[k]["gps_fuera"] += 1
            people[k]["alertas"] += 1

    for row in materials:
        k = key_for(row)
        people[k]["materiales"] += 1
        status = normalize(row.get("status"))
        if status == "delivered":
            people[k]["material_entregado"] += 1
        if status in {"returned", "returned_partial"}:
            people[k]["material_devuelto"] += 1
        if status in {"consigned", "consigned_partial"}:
            people[k]["consignas"] += 1

    for row in payroll:
        k = key_for(row)
        people[k]["horas_ordinarias"] += minutes_to_hours(row.get("regular_minutes"))
        people[k]["horas_extra"] += minutes_to_hours(row.get("extra_minutes"))
        people[k]["total_nomina"] += num(row.get("net_amount"))

    out = list(people.values())
    for row in out:
        row["horas_ordinarias"] = round(num(row.get("horas_ordinarias")), 2)
        row["horas_extra"] = round(num(row.get("horas_extra")), 2)
        row["total_nomina"] = round(num(row.get("total_nomina")), 2)
    return sorted(out, key=lambda item: (str(item.get("employee_name") or "").lower()))


def build_cards(summary: dict[str, Any], details: dict[str, Any]) -> list[dict[str, Any]]:
    employees = summary.get("employees") or {}
    attendance = summary.get("attendance") or {}
    gps = summary.get("gps") or {}
    materials = summary.get("materials") or {}
    inventory = summary.get("inventory") or {}
    payroll = summary.get("payroll") or {}

    return [
        {"label": "Personal activo", "value": employees.get("active", 0), "module": "workforce"},
        {"label": "Turnos iniciados", "value": attendance.get("checkins", 0), "module": "workforce"},
        {"label": "Horas ordinarias", "value": minutes_to_hours(payroll.get("regular_minutes")), "module": "payroll"},
        {"label": "Total nómina", "value": payroll.get("net_amount", 0), "module": "payroll", "format": "money"},
        {"label": "GPS fuera", "value": gps.get("outside", 0), "module": "gps"},
        {"label": "Órdenes material", "value": materials.get("total", 0), "module": "materials"},
        {"label": "Consignas", "value": (materials.get("consigned", 0) or 0) + (materials.get("consigned_partial", 0) or 0), "module": "materials"},
        {"label": "Stock bajo", "value": inventory.get("low_stock", 0), "module": "inventory"},
        {"label": "Stock cero", "value": inventory.get("zero_stock", 0), "module": "inventory"},
        {"label": "Alertas", "value": len(summary.get("alerts") or []), "module": "general"},
    ]


async def company_report_identity(db: AsyncSession, company_id: UUID) -> dict[str, Any]:
    fallback = {
        "name": "CLONEXA",
        "slug": "",
        "logo_url": "",
        "primary_color": "#7c3cff",
        "secondary_color": "#ff2bd6",
        "background_color": "#111827",
        "card_color": "#1f2937",
        "text_color": "#f8fafc",
        "success_color": "#22c55e",
    }
    if not await table_exists(db, "companies"):
        return fallback

    has_branding = await table_exists(db, "company_branding")
    if has_branding:
        result = await db.execute(
            text("""
                SELECT
                    c.name,
                    c.slug,
                    c.settings_json,
                    b.logo_url,
                    b.primary_color,
                    b.secondary_color,
                    b.background_color,
                    b.card_color,
                    b.text_color,
                    b.success_color
                FROM companies c
                LEFT JOIN company_branding b ON b.company_id = c.id
                WHERE c.id = CAST(:company_id AS uuid)
                LIMIT 1
            """),
            {"company_id": str(company_id)},
        )
    else:
        result = await db.execute(
            text("""
                SELECT name, slug, settings_json
                FROM companies
                WHERE id = CAST(:company_id AS uuid)
                LIMIT 1
            """),
            {"company_id": str(company_id)},
        )

    row = row_dict(result.mappings().first())
    if not row:
        return fallback

    settings = row.get("settings_json") if isinstance(row.get("settings_json"), dict) else {}
    branding = settings.get("branding") if isinstance(settings.get("branding"), dict) else {}
    identity = dict(fallback)
    identity.update({k: v for k, v in row.items() if v not in (None, "") and k != "settings_json"})
    for key in ["logo_url", "primary_color", "secondary_color", "background_color", "card_color", "text_color", "success_color"]:
        if not identity.get(key) and branding.get(key):
            identity[key] = branding.get(key)
    return identity


async def build_report_payload(
    db: AsyncSession,
    company_id: UUID,
    *,
    preset: str,
    start_date: date | None,
    end_date: date | None,
    employee_id: UUID | None,
    module_code: str | None,
    status: str | None,
    search: str | None,
) -> dict[str, Any]:
    start, end, period_code = parse_period(preset, start_date, end_date)

    summary = await load_kpis(db, company_id, period_code, start.date(), end.date())
    if not summary:
        summary = {
            "company_id": str(company_id),
            "period": {"preset": period_code, "start": start.isoformat(), "end": end.isoformat()},
            "modules": [],
            "employees": {},
            "attendance": {},
            "gps": {},
            "inventory": {},
            "materials": {},
            "payroll": {},
            "alerts": [],
            "cards": [],
        }

    try:
        company = await company_report_identity(db, company_id)
    except Exception:
        await safe_rollback(db)
        company = {"name": "CLONEXA", "logo_url": ""}

    details: dict[str, list[dict[str, Any]]] = {
        "employees": [],
        "attendance": [],
        "gps": [],
        "materials": [],
        "inventory_items": [],
        "inventory_movements": [],
        "payroll": [],
        "employee_summary": [],
    }

    errors: list[dict[str, str]] = []

    async def guard(name: str, fn):
        try:
            return await fn()
        except Exception as exc:
            await safe_rollback(db)
            errors.append({"module": name, "error": str(exc)[:240]})
            return []

    employees = await guard("employees", lambda: employee_rows(db, company_id))
    attendance = await guard("attendance", lambda: attendance_rows(db, company_id, start, end))
    materials = await guard("materials", lambda: material_rows(db, company_id, start, end))
    inventory_items = await guard("inventory", lambda: inventory_item_rows(db, company_id))
    inventory_movements = await guard("inventory_movements", lambda: inventory_movement_rows(db, company_id, start, end))
    payroll = await guard("payroll", lambda: payroll_rows(db, company_id, start, end))

    gps = gps_rows_from_attendance(attendance)

    eid = str(employee_id) if employee_id else None
    details["employees"] = filter_list(employees, employee_id=eid, module_code=None, status=status, search=search)
    details["attendance"] = filter_list(attendance, employee_id=eid, module_code=module_code, status=status, search=search)
    details["gps"] = filter_list(gps, employee_id=eid, module_code=None, status=status, search=search)
    details["materials"] = filter_list(materials, employee_id=eid, module_code=module_code, status=status, search=search)
    details["inventory_items"] = filter_list(inventory_items, module_code=None, status=status, search=search)
    details["inventory_movements"] = filter_list(inventory_movements, module_code=module_code, status=status, search=search)
    details["payroll"] = filter_list(payroll, employee_id=eid, module_code=module_code, status=status, search=search)

    employee_summary = build_employee_summary(employees, attendance, materials, gps, payroll)
    details["employee_summary"] = filter_list(employee_summary, employee_id=eid, status=status, search=search)

    charts = build_charts(
        start=start,
        end=end,
        attendance=details["attendance"],
        materials=details["materials"],
        gps=details["gps"],
        inventory_items=details["inventory_items"],
        inventory_movements=details["inventory_movements"],
        payroll=details["payroll"],
        summary=summary,
    )

    payload = {
        "company_id": str(company_id),
        "company": company,
        "mode": "employee" if employee_id else "general",
        "filters": {
            "preset": period_code,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "employee_id": str(employee_id) if employee_id else None,
            "module": module_code or "all",
            "status": status or "all",
            "search": search or "",
        },
        "summary": summary,
        "cards": build_cards(summary, details),
        "charts": charts,
        "details": details,
        "errors": errors,
        "generated_at": utcnow().isoformat(),
    }
    return serialize(payload)


@router.get("/companies/{company_id}/general")
async def general_report(
    company_id: UUID,
    preset: str = Query("7d"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    employee_id: UUID | None = Query(None),
    module: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await build_report_payload(
        db,
        company_id,
        preset=preset,
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
        module_code=module,
        status=status,
        search=search,
    )


@router.get("/companies/{company_id}/employee/{employee_id}")
async def employee_report(
    company_id: UUID,
    employee_id: UUID,
    preset: str = Query("7d"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    module: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await build_report_payload(
        db,
        company_id,
        preset=preset,
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
        module_code=module,
        status=status,
        search=search,
    )


def write_section(writer: csv.writer, title: str, rows_: list[dict[str, Any]], columns: list[str]) -> None:
    writer.writerow([])
    writer.writerow([title])
    writer.writerow(columns)
    for row in rows_:
        writer.writerow([row.get(col, "") for col in columns])


REPORT_PDF_SECTIONS: dict[str, dict[str, Any]] = {
    "employee_summary": {
        "title": "Resumen por empleado",
        "columns": [
            ("employee_name", "Empleado"),
            ("employee_role", "Rol"),
            ("turnos", "Turnos"),
            ("eventos", "Eventos"),
            ("gps", "GPS"),
            ("gps_fuera", "GPS fuera"),
            ("materiales", "Materiales"),
            ("material_devuelto", "Devueltos"),
            ("horas_ordinarias", "Horas ord."),
            ("horas_extra", "Horas extra"),
            ("total_nomina", "Total nomina"),
            ("alertas", "Alertas"),
        ],
    },
    "materials": {
        "title": "Materiales, autorizaciones y devoluciones",
        "columns": [
            ("order_number", "Orden"),
            ("employee_name", "Solicitante"),
            ("material_name", "Material"),
            ("quantity", "Cantidad"),
            ("quantity_returned", "Devuelto"),
            ("status", "Estado"),
            ("destination", "Destino"),
            ("requested_at", "Solicitud"),
            ("approved_at", "Autorizacion"),
            ("delivered_at", "Entrega"),
            ("returned_at", "Devolucion"),
            ("notes", "Notas"),
        ],
    },
    "inventory_items": {
        "title": "Inventario",
        "columns": [
            ("name_reference", "Referencia"),
            ("sku", "SKU"),
            ("item_size", "Tamano"),
            ("color", "Color"),
            ("current_stock", "Stock actual"),
            ("min_stock", "Minimo"),
            ("status", "Estado"),
            ("updated_at", "Actualizado"),
        ],
    },
    "inventory_movements": {
        "title": "Movimientos de inventario",
        "columns": [
            ("item_name", "Material"),
            ("movement_type", "Movimiento"),
            ("quantity_delta", "Cantidad"),
            ("source_module", "Origen"),
            ("source_ref", "Referencia"),
            ("status", "Estado"),
            ("notes", "Notas"),
            ("created_at", "Fecha"),
        ],
    },
    "gps": {
        "title": "GPS",
        "columns": [
            ("employee_name", "Empleado"),
            ("employee_role", "Rol"),
            ("gps_status", "Estado GPS"),
            ("occurred_at", "Fecha/Hora"),
            ("detail", "Detalle"),
            ("status", "Estado"),
        ],
    },
    "payroll": {
        "title": "Nomina",
        "columns": [
            ("employee_name", "Empleado"),
            ("employee_role", "Rol"),
            ("closed_shifts", "Turnos cerrados"),
            ("regular_minutes", "Min. ordinarios"),
            ("extra_minutes", "Min. extra"),
            ("gross_amount", "Bruto"),
            ("discount_amount", "Descuentos"),
            ("net_amount", "Neto"),
        ],
    },
    "attendance": {
        "title": "Asistencia y bitacora",
        "columns": [
            ("occurred_at", "Fecha/Hora"),
            ("employee_name", "Empleado"),
            ("employee_role", "Rol"),
            ("event_type", "Evento"),
            ("source_channel", "Canal"),
            ("module_code", "Modulo"),
            ("status", "Estado"),
            ("detail", "Detalle"),
        ],
    },
}


def report_pdf_sections(detail: str | None) -> list[str]:
    raw = normalize(detail or "all")
    parts = {normalize(part) for part in raw.replace(";", ",").split(",") if normalize(part)}
    if not parts or parts.intersection({"all", "todo", "todos", "super", "super_archivo", "completo", "general"}):
        return list(REPORT_PDF_SECTIONS.keys())

    out: list[str] = []

    def add(*keys: str) -> None:
        for key in keys:
            if key not in out:
                out.append(key)

    for part in parts:
        if part in REPORT_PDF_SECTIONS:
            add(part)

    text_value = " ".join(parts)
    if any(token in text_value for token in ["empleado", "empleados", "personal", "workforce", "persona"]):
        add("employee_summary")
    if any(token in text_value for token in ["material", "materiales", "autorizacion", "autorizaciones", "entrada", "entradas", "salida", "salidas"]):
        add("materials", "inventory_movements")
    if "inventario" in text_value or "inventory" in text_value or "stock" in text_value:
        add("inventory_items", "inventory_movements")
    if "gps" in text_value or "ubicacion" in text_value:
        add("gps")
    if "nomina" in text_value or "payroll" in text_value:
        add("payroll")
    if "asistencia" in text_value or "bitacora" in text_value:
        add("attendance")

    return out or ["employee_summary"]


def report_pdf_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{float(value):,.2f}"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, dict):
        return ", ".join(f"{k}: {report_pdf_value(v)}" for k, v in value.items() if v not in (None, ""))
    if isinstance(value, list):
        return ", ".join(report_pdf_value(item) for item in value[:6])
    return str(value)


def report_pdf_logo_reader(source: str | None):
    raw = str(source or "").strip()
    if not raw:
        return None
    try:
        from reportlab.lib.utils import ImageReader
    except Exception:
        return None
    try:
        if raw.startswith("data:image/"):
            encoded = raw.split(",", 1)[1]
            return ImageReader(io.BytesIO(base64.b64decode(encoded)))
        if len(raw) > 300 and not raw.startswith(("http://", "https://", "/")):
            try:
                return ImageReader(io.BytesIO(base64.b64decode(raw)))
            except Exception:
                pass
        if raw.startswith("/"):
            base_url = str(os.getenv("PUBLIC_BASE_URL") or os.getenv("APP_PUBLIC_URL") or "").strip().rstrip("/")
            if base_url:
                raw = base_url + raw
        if raw.startswith(("http://", "https://")):
            import urllib.request

            with urllib.request.urlopen(raw, timeout=8) as response:
                return ImageReader(io.BytesIO(response.read()))
        if os.path.exists(raw):
            return ImageReader(raw)
    except Exception:
        return None
    return None


def build_report_pdf_bytes(payload: dict[str, Any], detail: str | None) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Motor PDF no disponible. Falta reportlab: {exc}") from exc

    buffer = io.BytesIO()
    page_w, page_h = landscape(letter)
    c = canvas.Canvas(buffer, pagesize=(page_w, page_h))
    margin = 30
    page_no = 0
    y = page_h - margin

    company = payload.get("company") if isinstance(payload.get("company"), dict) else {}
    filters = payload.get("filters") or {}
    company_name = str(company.get("name") or "CLONEXA")
    logo = report_pdf_logo_reader(company.get("logo_url"))

    def pdf_color(value: Any, fallback: str):
        try:
            return colors.HexColor(str(value or fallback))
        except Exception:
            return colors.HexColor(fallback)

    primary = pdf_color(company.get("primary_color"), "#7c3cff")
    secondary = pdf_color(company.get("secondary_color"), "#ff2bd6")
    success = pdf_color(company.get("success_color"), "#22c55e")
    dark = colors.HexColor("#111827")
    muted = colors.HexColor("#64748b")
    border = colors.HexColor("#d8dee9")
    soft = colors.HexColor("#f5f7fb")
    soft_alt = colors.HexColor("#edf2f7")

    def clean_text(value: Any) -> str:
        text_value = report_pdf_value(value).replace("\n", " ").replace("\r", " ").strip()
        return " ".join(text_value.split())

    def fit_text(text_value: Any, width: float, font: str = "Helvetica", size: float = 7) -> str:
        text_clean = clean_text(text_value)
        if stringWidth(text_clean, font, size) <= width:
            return text_clean
        suffix = "..."
        out = text_clean
        while out and stringWidth(out + suffix, font, size) > width:
            out = out[:-1]
        return (out + suffix) if out else suffix

    def metric_value(card: dict[str, Any]) -> str:
        value = card.get("value")
        if card.get("format") == "money" or "nomina" in normalize(card.get("label")):
            try:
                return "$ " + f"{int(round(num(value))):,}".replace(",", ".")
            except Exception:
                return report_pdf_value(value)
        return report_pdf_value(value)

    def draw_footer() -> None:
        c.setFillColor(muted)
        c.setFont("Helvetica", 7)
        c.drawString(margin, 18, "CLONEXA / Reporte operativo generado automaticamente")
        c.drawRightString(page_w - margin, 18, f"Pagina {page_no}")

    def draw_header() -> None:
        nonlocal y, page_no
        page_no += 1
        c.setFillColor(colors.white)
        c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
        c.setFillColor(dark)
        c.rect(0, page_h - 86, page_w, 86, stroke=0, fill=1)
        c.setFillColor(primary)
        c.rect(0, page_h - 90, page_w * 0.58, 4, stroke=0, fill=1)
        c.setFillColor(secondary)
        c.rect(page_w * 0.58, page_h - 90, page_w * 0.42, 4, stroke=0, fill=1)

        if logo is not None:
            try:
                c.drawImage(logo, margin, page_h - 70, width=54, height=42, preserveAspectRatio=True, mask="auto")
            except Exception:
                logo_box()
        else:
            logo_box()

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(margin + 68, page_h - 42, fit_text(company_name, 300, "Helvetica-Bold", 18))
        c.setFont("Helvetica", 8)
        c.drawString(margin + 68, page_h - 58, "Dashboard operativo exportado en PDF")

        c.setFont("Helvetica-Bold", 18)
        c.drawRightString(page_w - margin, page_h - 40, "REPORTE")
        c.setFont("Helvetica", 8)
        c.drawRightString(page_w - margin, page_h - 57, f"Rango: {clean_text(filters.get('start'))[:10]} / {clean_text(filters.get('end'))[:10]}")
        c.drawRightString(page_w - margin, page_h - 70, f"Generado: {clean_text(payload.get('generated_at'))[:19]}")
        draw_footer()
        y = page_h - 116

    def logo_box() -> None:
        c.setFillColor(primary)
        c.roundRect(margin, page_h - 72, 48, 48, 9, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(margin + 24, page_h - 52, "CLX")

    def new_page() -> None:
        c.showPage()
        draw_header()

    def ensure(space: float = 24) -> None:
        if y - space < 40:
            new_page()

    def section_title(title_value: str, subtitle: str = "") -> None:
        nonlocal y
        ensure(34)
        c.setFillColor(primary)
        c.roundRect(margin, y - 20, 5, 20, 2, stroke=0, fill=1)
        c.setFillColor(dark)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin + 12, y - 2, title_value[:92])
        if subtitle:
            c.setFillColor(muted)
            c.setFont("Helvetica", 7)
            c.drawRightString(page_w - margin, y - 2, fit_text(subtitle, 260, "Helvetica", 7))
        y -= 30

    def draw_kpi_cards(cards: list[dict[str, Any]]) -> None:
        nonlocal y
        section_title("Resumen ejecutivo", "Indicadores principales del periodo")
        columns = 5
        gap = 10
        card_w = (page_w - margin * 2 - gap * (columns - 1)) / columns
        card_h = 58
        for index, card in enumerate(cards[:10]):
            col = index % columns
            if col == 0 and index:
                y -= card_h + 10
                ensure(card_h + 14)
            x = margin + col * (card_w + gap)
            yy = y - card_h
            accent = [primary, secondary, success, colors.HexColor("#38bdf8"), colors.HexColor("#f59e0b")][index % 5]
            c.setFillColor(soft)
            c.roundRect(x, yy, card_w, card_h, 9, stroke=0, fill=1)
            c.setStrokeColor(border)
            c.roundRect(x, yy, card_w, card_h, 9, stroke=1, fill=0)
            c.setFillColor(accent)
            c.roundRect(x, yy, 7, card_h, 4, stroke=0, fill=1)
            c.setFillColor(muted)
            c.setFont("Helvetica-Bold", 6.5)
            c.drawString(x + 15, yy + card_h - 16, fit_text(card.get("label"), card_w - 24, "Helvetica-Bold", 6.5).upper())
            c.setFillColor(dark)
            c.setFont("Helvetica-Bold", 17)
            c.drawString(x + 15, yy + 20, fit_text(metric_value(card), card_w - 24, "Helvetica-Bold", 17))
            c.setFillColor(muted)
            c.setFont("Helvetica", 6.5)
            c.drawString(x + 15, yy + 8, fit_text(card.get("module") or "", card_w - 24, "Helvetica", 6.5))
        y -= card_h + 22

    def chart_label_and_value(chart_key: str, item: dict[str, Any]) -> tuple[str, float, str]:
        if chart_key == "activity_by_day":
            value = num(item.get("turnos")) + num(item.get("gps")) + num(item.get("materiales"))
            detail_text = f"T {report_pdf_value(item.get('turnos'))} / GPS {report_pdf_value(item.get('gps'))} / Mat {report_pdf_value(item.get('materiales'))}"
            return str(item.get("date") or "Dia"), value, detail_text
        label = str(item.get("label") or item.get("date") or "Dato")
        value = num(item.get("value"))
        return label, value, report_pdf_value(value)

    def draw_chart_card(chart_key: str, items: list[dict[str, Any]], x: float, yy: float, w: float, h: float) -> None:
        title_map = {
            "activity_by_day": "Actividad por dia",
            "materials_by_status": "Materiales por estado",
            "gps_distribution": "GPS",
            "inventory_status": "Inventario critico",
            "payroll_breakdown": "Nomina",
            "inventory_movements": "Movimientos inventario",
        }
        c.setFillColor(soft)
        c.roundRect(x, yy, w, h, 9, stroke=0, fill=1)
        c.setStrokeColor(border)
        c.roundRect(x, yy, w, h, 9, stroke=1, fill=0)
        c.setFillColor(dark)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 12, yy + h - 18, title_map.get(chart_key, chart_key.replace("_", " ").title()))
        rows_ = [row for row in items if isinstance(row, dict)][:9]
        values = [chart_label_and_value(chart_key, row)[1] for row in rows_]
        maximum = max(values + [1])
        row_y = yy + h - 36
        for index, row in enumerate(rows_):
            label, value, detail_text = chart_label_and_value(chart_key, row)
            pct = 0 if maximum <= 0 else max(0.02, min(1, value / maximum))
            bar_x = x + 120
            bar_w = w - 178
            c.setFillColor(muted)
            c.setFont("Helvetica", 6.5)
            c.drawString(x + 12, row_y, fit_text(label, 96, "Helvetica", 6.5))
            c.setFillColor(colors.HexColor("#e5e7eb"))
            c.roundRect(bar_x, row_y - 2, bar_w, 7, 3, stroke=0, fill=1)
            c.setFillColor([success, primary, secondary, colors.HexColor("#38bdf8")][index % 4])
            c.roundRect(bar_x, row_y - 2, bar_w * pct, 7, 3, stroke=0, fill=1)
            c.setFillColor(dark)
            c.setFont("Helvetica-Bold", 6.5)
            c.drawRightString(x + w - 12, row_y, fit_text(detail_text, 46, "Helvetica-Bold", 6.5))
            row_y -= 12

    def draw_charts(charts: dict[str, Any]) -> None:
        nonlocal y
        if not charts:
            return
        section_title("Graficas", "Resumen visual de actividad")
        gap = 14
        card_w = (page_w - margin * 2 - gap) / 2
        card_h = 148
        col = 0
        for chart_key, items in charts.items():
            rows_ = items if isinstance(items, list) else []
            if not rows_:
                continue
            if col == 0:
                ensure(card_h + 12)
            x = margin + col * (card_w + gap)
            draw_chart_card(chart_key, rows_, x, y - card_h, card_w, card_h)
            if col == 1:
                y -= card_h + 14
            col = 1 - col
        if col == 1:
            y -= card_h + 14

    def draw_table_header(columns: list[tuple[str, str]], widths: list[float], table_y: float, font_size: float) -> None:
        x = margin
        c.setFillColor(dark)
        c.roundRect(margin, table_y - 19, page_w - margin * 2, 19, 4, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", font_size)
        for index, ((_, label), col_w) in enumerate(zip(columns, widths)):
            c.drawString(x + 4, table_y - 12, fit_text(label, col_w - 8, "Helvetica-Bold", font_size))
            if index:
                c.setStrokeColor(colors.HexColor("#334155"))
                c.line(x, table_y - 19, x, table_y)
                c.setFillColor(colors.white)
            x += col_w

    def table_widths(columns: list[tuple[str, str]]) -> list[float]:
        weights = []
        for field, _ in columns:
            if any(token in field for token in ["name", "material", "reference", "detail", "notes", "destination"]):
                weights.append(1.65)
            elif any(token in field for token in ["created", "updated", "occurred", "requested", "approved", "delivered", "returned"]):
                weights.append(1.25)
            else:
                weights.append(1.0)
        total = sum(weights) or 1
        available = page_w - margin * 2
        return [available * weight / total for weight in weights]

    def draw_table_section(key: str, cfg: dict[str, Any], rows_: list[dict[str, Any]]) -> None:
        nonlocal y
        section_title(f"{cfg['title']} ({len(rows_)})")
        columns = cfg["columns"]
        widths = table_widths(columns)
        font_size = 5.8 if len(columns) > 8 else 6.5
        row_h = 18
        ensure(42)
        draw_table_header(columns, widths, y, font_size)
        y -= 19
        if not rows_:
            c.setFillColor(soft)
            c.rect(margin, y - row_h, page_w - margin * 2, row_h, stroke=0, fill=1)
            c.setFillColor(muted)
            c.setFont("Helvetica", 7)
            c.drawString(margin + 8, y - 12, "Sin datos para este filtro.")
            y -= row_h + 12
            return
        for index, row in enumerate(rows_, start=1):
            if y - row_h < 42:
                new_page()
                section_title(f"{cfg['title']} (continuacion)")
                draw_table_header(columns, widths, y, font_size)
                y -= 19
            bg = soft if index % 2 else soft_alt
            c.setFillColor(bg)
            c.rect(margin, y - row_h, page_w - margin * 2, row_h, stroke=0, fill=1)
            c.setStrokeColor(border)
            c.line(margin, y - row_h, page_w - margin, y - row_h)
            x = margin
            c.setFillColor(dark)
            c.setFont("Helvetica", font_size)
            for col_index, (field, _label) in enumerate(columns):
                c.drawString(x + 4, y - 12, fit_text(row.get(field), widths[col_index] - 8, "Helvetica", font_size))
                c.setStrokeColor(colors.HexColor("#e2e8f0"))
                c.line(x, y - row_h, x, y)
                x += widths[col_index]
            c.line(page_w - margin, y - row_h, page_w - margin, y)
            y -= row_h
        y -= 16

    c.setTitle("CLONEXA - Reporte Operativo")
    draw_header()
    draw_kpi_cards(payload.get("cards") or [])
    draw_charts(payload.get("charts") or {})
    details = payload.get("details") or {}
    for key in report_pdf_sections(detail):
        cfg = REPORT_PDF_SECTIONS.get(key)
        if not cfg:
            continue
        draw_table_section(key, cfg, details.get(key) or [])

    c.save()
    return buffer.getvalue()


@router.get("/companies/{company_id}/export.csv")
async def export_report_csv(
    company_id: UUID,
    preset: str = Query("7d"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    employee_id: UUID | None = Query(None),
    module: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    payload = await build_report_payload(
        db,
        company_id,
        preset=preset,
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
        module_code=module,
        status=status,
        search=search,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["CLONEXA - Reporte Operativo"])
    writer.writerow(["company_id", payload.get("company_id")])
    writer.writerow(["modo", payload.get("mode")])
    filters = payload.get("filters") or {}
    writer.writerow(["desde", filters.get("start")])
    writer.writerow(["hasta", filters.get("end")])
    writer.writerow(["generado", payload.get("generated_at")])

    writer.writerow([])
    writer.writerow(["Resumen"])
    writer.writerow(["KPI", "Valor", "Modulo"])
    for card in payload.get("cards") or []:
        writer.writerow([card.get("label"), card.get("value"), card.get("module")])

    details = payload.get("details") or {}
    write_section(
        writer,
        "Resumen por empleado",
        details.get("employee_summary") or [],
        ["employee_name", "employee_role", "turnos", "eventos", "pausas", "gps", "gps_fuera", "materiales", "material_entregado", "material_devuelto", "consignas", "horas_ordinarias", "horas_extra", "total_nomina", "alertas"],
    )
    write_section(
        writer,
        "Materiales",
        details.get("materials") or [],
        ["order_number", "employee_name", "material_name", "quantity", "quantity_returned", "status", "destination", "requested_at", "delivered_at", "returned_at", "notes"],
    )
    write_section(
        writer,
        "Inventario",
        details.get("inventory_items") or [],
        ["name_reference", "sku", "item_size", "color", "current_stock", "min_stock", "status", "updated_at"],
    )
    write_section(
        writer,
        "GPS",
        details.get("gps") or [],
        ["employee_name", "employee_role", "gps_status", "occurred_at", "detail", "status"],
    )
    write_section(
        writer,
        "Nomina",
        details.get("payroll") or [],
        ["employee_name", "employee_role", "closed_shifts", "regular_minutes", "extra_minutes", "gross_amount", "discount_amount", "net_amount"],
    )
    write_section(
        writer,
        "Asistencia",
        details.get("attendance") or [],
        ["occurred_at", "employee_name", "employee_role", "event_type", "event_label", "source_channel", "module_code", "status", "detail"],
    )

    csv_text = output.getvalue()
    filename = f"clonexa_reporte_{payload.get('mode', 'general')}_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/companies/{company_id}/export.pdf")
async def export_report_pdf(
    company_id: UUID,
    preset: str = Query("7d"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    employee_id: UUID | None = Query(None),
    module: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    detail: str | None = Query("all"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    payload = await build_report_payload(
        db,
        company_id,
        preset=preset,
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
        module_code=module,
        status=status,
        search=search,
    )
    pdf_bytes = build_report_pdf_bytes(payload, detail)
    safe_detail = normalize(detail or "all") or "all"
    filename = f"clonexa_reporte_{safe_detail}_{date.today().isoformat()}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
