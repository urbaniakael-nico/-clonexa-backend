from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


def clean(value: Any) -> str:
    return str(value or "").strip()


def intval(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def fval(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return 0.0


def today_utc() -> date:
    return datetime.utcnow().date()


def parse_date(value: str | None, fallback: date) -> date:
    raw = clean(value)
    if not raw:
        return fallback
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        return fallback


def date_range(date_from: str | None, date_to: str | None, preset: str | None) -> tuple[date, date]:
    today = today_utc()
    preset_value = clean(preset).lower()

    if preset_value in {"today", "hoy"}:
        return today, today

    if preset_value in {"30d", "30", "30 dias", "30 días"}:
        return today - timedelta(days=29), today

    if preset_value in {"month", "mes"}:
        return today.replace(day=1), today

    default_from = today - timedelta(days=6)
    start = parse_date(date_from, default_from)
    end = parse_date(date_to, today)

    if start > end:
        start, end = end, start

    return start, end


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name})
    return bool(result.scalar())


async def table_columns(db: AsyncSession, table_name: str) -> set[str]:
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


async def safe_scalar(db: AsyncSession, sql: str, params: dict[str, Any], default: Any = 0) -> Any:
    try:
        result = await db.execute(text(sql), params)
        value = result.scalar()
        return default if value is None else value
    except Exception:
        await db.rollback()
        return default


async def safe_rows(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        result = await db.execute(text(sql), params)
        return [dict(row) for row in result.mappings().all()]
    except Exception:
        await db.rollback()
        return []


async def company_profile(db: AsyncSession, company_id: str) -> dict[str, Any]:
    if not await table_exists(db, "companies"):
        return {"name": "Empresa", "currency": "COP"}

    cols = await table_columns(db, "companies")

    name_col = "name" if "name" in cols else "business_name" if "business_name" in cols else None
    slug_col = "slug" if "slug" in cols else None
    currency_col = "currency" if "currency" in cols else "currency_code" if "currency_code" in cols else None

    select_parts = ["id::text AS id"]

    if name_col:
        select_parts.append(f"COALESCE({name_col}, 'Empresa') AS name")
    else:
        select_parts.append("'Empresa' AS name")

    if slug_col:
        select_parts.append(f"COALESCE({slug_col}, '') AS slug")
    else:
        select_parts.append("'' AS slug")

    if currency_col:
        select_parts.append(f"COALESCE({currency_col}, 'COP') AS currency")
    else:
        select_parts.append("'COP' AS currency")

    rows = await safe_rows(
        db,
        f"""
        SELECT {", ".join(select_parts)}
        FROM companies
        WHERE id::text = :company_id
        LIMIT 1
        """,
        {"company_id": company_id},
    )

    if not rows:
        return {"name": "Empresa", "currency": "COP"}

    row = rows[0]

    return {
        "id": row.get("id"),
        "name": clean(row.get("name")) or "Empresa",
        "slug": clean(row.get("slug")),
        "currency": clean(row.get("currency")) or "COP",
    }


async def active_modules(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    rows = await safe_rows(
        db,
        """
        SELECT
            lower(m.code) AS code,
            COALESCE(m.name, m.code) AS name,
            COALESCE(m.category, '') AS category,
            COALESCE(m.config_json, '{}'::jsonb)::text AS config_json_text
        FROM company_modules cm
        JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :company_id
          AND COALESCE(cm.enabled, true) IS TRUE
          AND COALESCE(m.is_active, true) IS TRUE
        ORDER BY m.category ASC, m.name ASC
        """,
        {"company_id": company_id},
    )

    return rows


def has(codes: set[str], *items: str) -> bool:
    return bool(codes.intersection({item.lower() for item in items}))


async def workforce_kpis(db: AsyncSession, company_id: str, start: date, end: date) -> list[dict[str, Any]]:
    params = {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()}

    employees_active = 0
    active_now = 0
    on_break = 0
    events = 0
    checkins = 0
    checkouts = 0

    if await table_exists(db, "employees"):
        employees_active = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM employees
            WHERE company_id::text = :company_id
              AND lower(COALESCE(status, 'active')) IN ('active', 'activo')
            """,
            params,
        ))

    if await table_exists(db, "workforce_attendance_status"):
        active_now = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM workforce_attendance_status
            WHERE company_id::text = :company_id
              AND lower(COALESCE(status, '')) = 'working'
            """,
            params,
        ))

        on_break = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM workforce_attendance_status
            WHERE company_id::text = :company_id
              AND lower(COALESCE(status, '')) = 'on_break'
            """,
            params,
        ))

    if await table_exists(db, "workforce_attendance_events"):
        events = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM workforce_attendance_events
            WHERE company_id::text = :company_id
              AND COALESCE(occurred_at, created_at)::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
            """,
            params,
        ))

        checkins = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM workforce_attendance_events
            WHERE company_id::text = :company_id
              AND COALESCE(occurred_at, created_at)::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
              AND lower(COALESCE(event_type, '')) IN ('check_in', 'entrada')
            """,
            params,
        ))

        checkouts = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM workforce_attendance_events
            WHERE company_id::text = :company_id
              AND COALESCE(occurred_at, created_at)::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
              AND lower(COALESCE(event_type, '')) IN ('check_out', 'salida')
            """,
            params,
        ))

    return [
        {"key": "employees_active", "label": "Personal activo", "value": employees_active, "module": "Personal"},
        {"key": "working_now", "label": "Trabajando ahora", "value": active_now, "module": "Personal"},
        {"key": "on_break", "label": "En pausa", "value": on_break, "module": "Personal"},
        {"key": "events", "label": "Eventos del periodo", "value": events, "module": "Personal"},
        {"key": "checkins", "label": "Turnos iniciados", "value": checkins, "module": "Personal"},
        {"key": "checkouts", "label": "Turnos cerrados", "value": checkouts, "module": "Personal"},
    ]


async def production_kpis(db: AsyncSession, company_id: str, start: date, end: date) -> list[dict[str, Any]]:
    params = {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()}

    refs = 0
    bot_active = 0
    initial_qty = 0
    finished_qty = 0
    closures = 0
    active_sessions = 0

    if await table_exists(db, "product_references"):
        refs = intval(await safe_scalar(
            db,
            "SELECT count(*) FROM product_references WHERE company_id = :company_id",
            params,
        ))
        bot_active = intval(await safe_scalar(
            db,
            "SELECT count(*) FROM product_references WHERE company_id = :company_id AND bot_active IS TRUE",
            params,
        ))
        initial_qty = intval(await safe_scalar(
            db,
            "SELECT COALESCE(sum(initial_quantity), 0) FROM product_references WHERE company_id = :company_id",
            params,
        ))

    if await table_exists(db, "reference_production_closures"):
        finished_qty = intval(await safe_scalar(
            db,
            """
            SELECT COALESCE(sum(quantity_finished), 0)
            FROM reference_production_closures
            WHERE company_id = :company_id
              AND closed_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
            """,
            params,
        ))

        closures = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM reference_production_closures
            WHERE company_id = :company_id
              AND closed_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
            """,
            params,
        ))

    if await table_exists(db, "reference_work_sessions"):
        active_sessions = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM reference_work_sessions
            WHERE company_id = :company_id
              AND status = 'active'
            """,
            params,
        ))

    pending = max(initial_qty - finished_qty, 0)
    progress = round((finished_qty / initial_qty) * 100, 2) if initial_qty > 0 else 0

    return [
        {"key": "references_total", "label": "Referencias", "value": refs, "module": "Producción"},
        {"key": "references_bot", "label": "Visibles en bot", "value": bot_active, "module": "Producción"},
        {"key": "initial_qty", "label": "Cantidad inicial", "value": initial_qty, "module": "Producción"},
        {"key": "finished_qty", "label": "Terminadas", "value": finished_qty, "module": "Producción"},
        {"key": "pending_qty", "label": "Pendientes", "value": pending, "module": "Producción"},
        {"key": "progress", "label": "Avance", "value": f"{progress}%", "module": "Producción"},
        {"key": "closures", "label": "Cierres producción", "value": closures, "module": "Producción"},
        {"key": "active_sessions", "label": "Sesiones activas", "value": active_sessions, "module": "Producción"},
    ]


async def payroll_kpis(db: AsyncSession, company_id: str, start: date, end: date, currency: str) -> list[dict[str, Any]]:
    amount = 0.0
    records = 0

    candidate_tables = ["payroll_records", "payroll_entries", "payroll_results", "payroll_runs"]
    table = ""

    for candidate in candidate_tables:
        if await table_exists(db, candidate):
            table = candidate
            break

    if table:
        cols = await table_columns(db, table)
        amount_col = "total_amount" if "total_amount" in cols else "total_pay" if "total_pay" in cols else "net_pay" if "net_pay" in cols else None
        date_col = "created_at" if "created_at" in cols else "period_start" if "period_start" in cols else None

        if "company_id" in cols and amount_col:
            date_filter = ""
            params = {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()}

            if date_col:
                date_filter = f"AND {date_col}::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)"

            amount = fval(await safe_scalar(
                db,
                f"""
                SELECT COALESCE(sum({amount_col}), 0)
                FROM {table}
                WHERE company_id::text = :company_id
                {date_filter}
                """,
                params,
            ))

            records = intval(await safe_scalar(
                db,
                f"""
                SELECT count(*)
                FROM {table}
                WHERE company_id::text = :company_id
                {date_filter}
                """,
                params,
            ))

    return [
        {
            "key": "payroll_total",
            "label": f"Total nómina ({currency})",
            "value": amount,
            "format": "currency",
            "currency": currency,
            "module": "Nómina",
        },
        {
            "key": "payroll_records",
            "label": "Registros nómina",
            "value": records,
            "module": "Nómina",
        },
    ]


async def simple_table_count_kpis(
    db: AsyncSession,
    *,
    company_id: str,
    code: str,
    title: str,
    table_candidates: list[str],
    label: str,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    table = ""

    for candidate in table_candidates:
        if await table_exists(db, candidate):
            table = candidate
            break

    total = 0

    if table:
        cols = await table_columns(db, table)
        date_col = "created_at" if "created_at" in cols else "occurred_at" if "occurred_at" in cols else "updated_at" if "updated_at" in cols else None

        if "company_id" in cols:
            params = {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()}
            date_filter = ""

            if date_col:
                date_filter = f"AND {date_col}::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)"

            total = intval(await safe_scalar(
                db,
                f"""
                SELECT count(*)
                FROM {table}
                WHERE company_id::text = :company_id
                {date_filter}
                """,
                params,
            ))

    return [
        {"key": f"{code}_total", "label": label, "value": total, "module": title},
    ]


@router.get("/companies/{company_id}/summary")
async def adaptive_kpis_summary(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    start, end = date_range(date_from, date_to, preset)
    company = await company_profile(db, company_id)
    modules = await active_modules(db, company_id)
    codes = {clean(row.get("code")).lower() for row in modules}
    currency = clean(company.get("currency")) or "COP"

    sections: list[dict[str, Any]] = []

    if has(codes, "workforce"):
        sections.append({
            "code": "workforce",
            "title": "Personal",
            "items": await workforce_kpis(db, company_id, start, end),
        })

    if has(codes, "references", "production"):
        sections.append({
            "code": "production",
            "title": "Referencias y producción",
            "items": await production_kpis(db, company_id, start, end),
        })

    if has(codes, "payroll"):
        sections.append({
            "code": "payroll",
            "title": "Nómina",
            "items": await payroll_kpis(db, company_id, start, end, currency),
        })

    if has(codes, "materials"):
        sections.append({
            "code": "materials",
            "title": "Materiales",
            "items": await simple_table_count_kpis(
                db,
                company_id=company_id,
                code="materials",
                title="Materiales",
                table_candidates=["material_requests", "materials_requests", "company_material_requests"],
                label="Solicitudes de materiales",
                start=start,
                end=end,
            ),
        })

    if has(codes, "gps"):
        sections.append({
            "code": "gps",
            "title": "GPS",
            "items": await simple_table_count_kpis(
                db,
                company_id=company_id,
                code="gps",
                title="GPS",
                table_candidates=["gps_events", "company_gps_events", "location_events", "employee_locations"],
                label="Ubicaciones",
                start=start,
                end=end,
            ),
        })

    flat_items: list[dict[str, Any]] = []

    for section in sections:
        for item in section.get("items", []):
            flat_items.append(item)

    return {
        "ok": True,
        "language": "es",
        "company_id": company_id,
        "company_name": company.get("name"),
        "currency": currency,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "active_modules": sorted(codes),
        "transversal_module": "kpis",
        "kpi_mode": "adaptive_by_active_modules",
        "items": flat_items,
        "sections": sections,
    }
