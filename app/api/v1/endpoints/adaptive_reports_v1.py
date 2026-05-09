from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


def clean(value: Any) -> str:
    return str(value or "").strip()


def num(value: Any) -> float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return 0


def intval(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


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


async def workforce_block(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any]:
    params = {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()}

    employees_active = 0
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

    events = 0
    checkins = 0
    checkouts = 0
    breaks = 0
    by_day: list[dict[str, Any]] = []

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

        breaks = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM workforce_attendance_events
            WHERE company_id::text = :company_id
              AND COALESCE(occurred_at, created_at)::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
              AND lower(COALESCE(event_type, '')) IN ('break_start', 'break_end', 'pausa', 'retorno')
            """,
            params,
        ))

        by_day = await safe_rows(
            db,
            """
            SELECT
                COALESCE(occurred_at, created_at)::date::text AS day,
                count(*) AS total
            FROM workforce_attendance_events
            WHERE company_id::text = :company_id
              AND COALESCE(occurred_at, created_at)::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
            GROUP BY COALESCE(occurred_at, created_at)::date
            ORDER BY day ASC
            """,
            params,
        )

    active_now = 0
    if await table_exists(db, "workforce_attendance_status"):
        active_now = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM workforce_attendance_status
            WHERE company_id::text = :company_id
              AND lower(COALESCE(status, '')) IN ('working', 'on_break')
            """,
            params,
        ))

    return {
        "code": "workforce",
        "title": "Personal",
        "enabled": True,
        "kpis": [
            {"label": "Personal activo", "value": employees_active},
            {"label": "Trabajando ahora", "value": active_now},
            {"label": "Eventos", "value": events},
            {"label": "Turnos iniciados", "value": checkins},
            {"label": "Turnos cerrados", "value": checkouts},
            {"label": "Pausas/retornos", "value": breaks},
        ],
        "by_day": [{"label": row.get("day"), "value": intval(row.get("total"))} for row in by_day],
    }


async def references_production_block(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any]:
    params = {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()}

    references_total = 0
    bot_active = 0
    initial_qty = 0

    if await table_exists(db, "product_references"):
        references_total = intval(await safe_scalar(
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

    finished_qty = 0
    closures = 0
    by_reference: list[dict[str, Any]] = []

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

        by_reference = await safe_rows(
            db,
            """
            SELECT
                COALESCE(reference_name, 'Sin referencia') AS label,
                COALESCE(size, '') AS size,
                COALESCE(sum(quantity_finished), 0) AS value
            FROM reference_production_closures
            WHERE company_id = :company_id
              AND closed_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
            GROUP BY reference_name, size
            ORDER BY value DESC, label ASC
            LIMIT 20
            """,
            params,
        )

    active_sessions = 0
    minutes = 0

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

        minutes = intval(await safe_scalar(
            db,
            """
            SELECT COALESCE(sum(duration_minutes), 0)
            FROM reference_work_sessions
            WHERE company_id = :company_id
              AND started_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
            """,
            params,
        ))

    pending = max(initial_qty - finished_qty, 0)
    progress = round((finished_qty / initial_qty) * 100, 2) if initial_qty > 0 else 0

    return {
        "code": "production",
        "title": "Referencias y producción",
        "enabled": True,
        "kpis": [
            {"label": "Referencias", "value": references_total},
            {"label": "Visibles en bot", "value": bot_active},
            {"label": "Cantidad inicial", "value": initial_qty},
            {"label": "Terminadas", "value": finished_qty},
            {"label": "Pendientes", "value": pending},
            {"label": "Avance", "value": f"{progress}%"},
            {"label": "Cierres", "value": closures},
            {"label": "Sesiones activas", "value": active_sessions},
            {"label": "Minutos producidos", "value": minutes},
        ],
        "by_reference": [
            {
                "label": f"{clean(row.get('label'))} {clean(row.get('size'))}".strip(),
                "value": intval(row.get("value")),
            }
            for row in by_reference
        ],
    }


async def materials_block(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any]:
    table = ""
    for candidate in ["material_requests", "materials_requests", "company_material_requests"]:
        if await table_exists(db, candidate):
            table = candidate
            break

    total = 0
    if table:
        cols = await table_columns(db, table)
        date_col = "created_at" if "created_at" in cols else "updated_at" if "updated_at" in cols else None
        if "company_id" in cols and date_col:
            total = intval(await safe_scalar(
                db,
                f"""
                SELECT count(*)
                FROM {table}
                WHERE company_id::text = :company_id
                  AND {date_col}::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
                """,
                {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()},
            ))

    return {
        "code": "materials",
        "title": "Materiales",
        "enabled": True,
        "kpis": [
            {"label": "Solicitudes", "value": total},
        ],
        "by_status": [],
    }


async def inventory_block(db: AsyncSession, company_id: str) -> dict[str, Any]:
    table = ""
    for candidate in ["inventory_items", "stock_items", "company_inventory_items"]:
        if await table_exists(db, candidate):
            table = candidate
            break

    items = 0
    low = 0
    zero = 0

    if table:
        cols = await table_columns(db, table)
        if "company_id" in cols:
            items = intval(await safe_scalar(
                db,
                f"SELECT count(*) FROM {table} WHERE company_id::text = :company_id",
                {"company_id": company_id},
            ))

            qty_col = "quantity" if "quantity" in cols else "stock" if "stock" in cols else "current_stock" if "current_stock" in cols else None
            min_col = "minimum_stock" if "minimum_stock" in cols else "min_stock" if "min_stock" in cols else None

            if qty_col:
                zero = intval(await safe_scalar(
                    db,
                    f"SELECT count(*) FROM {table} WHERE company_id::text = :company_id AND COALESCE({qty_col}, 0) <= 0",
                    {"company_id": company_id},
                ))

            if qty_col and min_col:
                low = intval(await safe_scalar(
                    db,
                    f"SELECT count(*) FROM {table} WHERE company_id::text = :company_id AND COALESCE({qty_col}, 0) <= COALESCE({min_col}, 0)",
                    {"company_id": company_id},
                ))

    return {
        "code": "inventory",
        "title": "Inventario",
        "enabled": True,
        "kpis": [
            {"label": "Ítems", "value": items},
            {"label": "Stock bajo", "value": low},
            {"label": "Stock cero", "value": zero},
        ],
    }


async def gps_block(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any]:
    table = ""
    for candidate in ["gps_events", "company_gps_events", "location_events", "employee_locations"]:
        if await table_exists(db, candidate):
            table = candidate
            break

    total = 0
    if table:
        cols = await table_columns(db, table)
        date_col = "created_at" if "created_at" in cols else "occurred_at" if "occurred_at" in cols else None
        if "company_id" in cols and date_col:
            total = intval(await safe_scalar(
                db,
                f"""
                SELECT count(*)
                FROM {table}
                WHERE company_id::text = :company_id
                  AND {date_col}::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
                """,
                {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()},
            ))

    return {
        "code": "gps",
        "title": "GPS",
        "enabled": True,
        "kpis": [
            {"label": "Ubicaciones", "value": total},
        ],
    }


@router.get("/companies/{company_id}/summary")
async def adaptive_report_summary(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    start, end = date_range(date_from, date_to, preset)

    modules = await active_modules(db, company_id)
    codes = {clean(row.get("code")).lower() for row in modules}

    blocks: list[dict[str, Any]] = []

    if has(codes, "workforce"):
        blocks.append(await workforce_block(db, company_id, start, end))

    if has(codes, "references", "production"):
        blocks.append(await references_production_block(db, company_id, start, end))

    if has(codes, "materials"):
        blocks.append(await materials_block(db, company_id, start, end))

    if has(codes, "inventory", "stock"):
        blocks.append(await inventory_block(db, company_id))

    if has(codes, "gps"):
        blocks.append(await gps_block(db, company_id, start, end))

    executive_kpis: list[dict[str, Any]] = []
    for block in blocks:
        for item in block.get("kpis", [])[:4]:
            executive_kpis.append({
                "module": block.get("title"),
                "label": item.get("label"),
                "value": item.get("value"),
            })

    return {
        "ok": True,
        "company_id": company_id,
        "language": "es",
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "active_modules": sorted(codes),
        "transversal_module": "reports",
        "report_mode": "adaptive_by_active_modules",
        "executive_kpis": executive_kpis[:16],
        "blocks": blocks,
    }


@router.get("/companies/{company_id}/export.csv")
async def adaptive_report_csv(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    data = await adaptive_report_summary(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        db=db,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["empresa", company_id])
    writer.writerow(["desde", data["date_from"]])
    writer.writerow(["hasta", data["date_to"]])
    writer.writerow([])
    writer.writerow(["modulo", "indicador", "valor"])

    for item in data.get("executive_kpis", []):
        writer.writerow([item.get("module"), item.get("label"), item.get("value")])

    writer.writerow([])
    writer.writerow(["bloques activos"])
    for block in data.get("blocks", []):
        writer.writerow([block.get("title")])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="clonexa_reporte_adaptativo_{company_id}.csv"'
        },
    )
