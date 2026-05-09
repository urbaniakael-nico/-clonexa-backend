from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.adaptive_reports_v1 import adaptive_report_summary

router = APIRouter()


def clean(value: Any) -> str:
    return str(value or "").strip()


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


async def safe_rows(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        result = await db.execute(text(sql), params)
        return [dict(row) for row in result.mappings().all()]
    except Exception:
        await db.rollback()
        return []


async def safe_scalar(db: AsyncSession, sql: str, params: dict[str, Any], default: Any = 0) -> Any:
    try:
        result = await db.execute(text(sql), params)
        value = result.scalar()
        return default if value is None else value
    except Exception:
        await db.rollback()
        return default


async def workforce_section(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any] | None:
    if not await table_exists(db, "workforce_attendance_events"):
        return None

    params = {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()}

    rows = await safe_rows(
        db,
        """
        SELECT
            COALESCE(occurred_at, created_at)::text AS fecha,
            COALESCE(employee_name, '') AS empleado,
            COALESCE(event_type, '') AS tipo,
            COALESCE(event_label, '') AS evento,
            COALESCE(detail, '') AS observacion
        FROM workforce_attendance_events
        WHERE company_id::text = :company_id
          AND COALESCE(occurred_at, created_at)::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        ORDER BY COALESCE(occurred_at, created_at) DESC
        LIMIT 300
        """,
        params,
    )

    chart = await safe_rows(
        db,
        """
        SELECT
            COALESCE(event_type, 'sin_tipo') AS label,
            count(*) AS value
        FROM workforce_attendance_events
        WHERE company_id::text = :company_id
          AND COALESCE(occurred_at, created_at)::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        GROUP BY event_type
        ORDER BY value DESC
        LIMIT 12
        """,
        params,
    )

    return {
        "code": "workforce",
        "title": "Personal y jornada",
        "summary": [
            {"label": "Eventos", "value": len(rows)},
        ],
        "chart": [{"label": clean(row.get("label")), "value": intval(row.get("value"))} for row in chart],
        "columns": ["fecha", "empleado", "tipo", "evento", "observacion"],
        "rows": rows,
    }


async def production_section(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any] | None:
    if not await table_exists(db, "reference_production_closures"):
        return None

    params = {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()}

    rows = await safe_rows(
        db,
        """
        SELECT
            closed_at::text AS fecha,
            COALESCE(employee_name, '') AS empleado,
            COALESCE(reference_name, '') AS referencia,
            COALESCE(size, '') AS talla,
            COALESCE(quantity_finished, 0) AS total
        FROM reference_production_closures
        WHERE company_id = :company_id
          AND closed_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        ORDER BY closed_at DESC
        LIMIT 300
        """,
        params,
    )

    total = intval(await safe_scalar(
        db,
        """
        SELECT COALESCE(sum(quantity_finished), 0)
        FROM reference_production_closures
        WHERE company_id = :company_id
          AND closed_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        """,
        params,
    ))

    chart = await safe_rows(
        db,
        """
        SELECT
            COALESCE(reference_name, 'Sin referencia') || ' ' || COALESCE(size, '') AS label,
            COALESCE(sum(quantity_finished), 0) AS value
        FROM reference_production_closures
        WHERE company_id = :company_id
          AND closed_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        GROUP BY reference_name, size
        ORDER BY value DESC
        LIMIT 12
        """,
        params,
    )

    return {
        "code": "production",
        "title": "Producción por referencia",
        "summary": [
            {"label": "Registros", "value": len(rows)},
            {"label": "Total terminado", "value": total},
        ],
        "chart": [{"label": clean(row.get("label")), "value": intval(row.get("value"))} for row in chart],
        "columns": ["fecha", "empleado", "referencia", "talla", "total"],
        "rows": rows,
    }


def pick(cols: set[str], candidates: list[str]) -> str | None:
    for item in candidates:
        if item in cols:
            return item
    return None


async def generic_section(
    db: AsyncSession,
    *,
    company_id: str,
    code: str,
    title: str,
    table_candidates: list[str],
    columns_map: dict[str, list[str]],
    date_from: date,
    date_to: date,
) -> dict[str, Any] | None:
    table = ""

    for candidate in table_candidates:
        if await table_exists(db, candidate):
            table = candidate
            break

    if not table:
        return None

    cols = await table_columns(db, table)

    if "company_id" not in cols:
        return None

    date_col = pick(cols, ["created_at", "occurred_at", "updated_at", "closed_at", "requested_at"])

    selected: list[str] = []
    output_cols: list[str] = []

    if date_col:
        selected.append(f"{date_col}::text AS fecha")
        output_cols.append("fecha")

    for out_name, candidates in columns_map.items():
        col = pick(cols, candidates)
        if col:
            selected.append(f"COALESCE({col}::text, '') AS {out_name}")
            output_cols.append(out_name)

    if not selected:
        selected.append("id::text AS id")
        output_cols.append("id")

    params = {"company_id": company_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()}

    date_filter = ""
    if date_col:
        date_filter = f"AND {date_col}::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)"

    rows = await safe_rows(
        db,
        f"""
        SELECT {", ".join(selected)}
        FROM {table}
        WHERE company_id::text = :company_id
        {date_filter}
        ORDER BY {date_col if date_col else "id"} DESC
        LIMIT 300
        """,
        params,
    )

    chart_col = pick(cols, ["status", "state", "event_type", "type", "category"])

    chart = []
    if chart_col:
        chart_rows = await safe_rows(
            db,
            f"""
            SELECT COALESCE({chart_col}::text, 'Sin clasificar') AS label, count(*) AS value
            FROM {table}
            WHERE company_id::text = :company_id
            {date_filter}
            GROUP BY {chart_col}
            ORDER BY value DESC
            LIMIT 12
            """,
            params,
        )
        chart = [{"label": clean(row.get("label")), "value": intval(row.get("value"))} for row in chart_rows]

    return {
        "code": code,
        "title": title,
        "summary": [
            {"label": "Registros", "value": len(rows)},
        ],
        "chart": chart,
        "columns": output_cols,
        "rows": rows,
    }


@router.get("/companies/{company_id}/detail")
async def adaptive_report_detail(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    start, end = date_range(date_from, date_to, preset)

    base = await adaptive_report_summary(
        company_id=company_id,
        date_from=start.isoformat(),
        date_to=end.isoformat(),
        preset=preset,
        db=db,
    )

    active_codes = set(base.get("active_modules") or [])
    sections = []

    if "workforce" in active_codes:
        section = await workforce_section(db, company_id, start, end)
        if section:
            sections.append(section)

    if "references" in active_codes or "production" in active_codes:
        section = await production_section(db, company_id, start, end)
        if section:
            sections.append(section)

    if "materials" in active_codes:
        section = await generic_section(
            db,
            company_id=company_id,
            code="materials",
            title="Materiales y solicitudes",
            table_candidates=["material_requests", "materials_requests", "company_material_requests"],
            columns_map={
                "empleado": ["employee_name", "requested_by", "responsible", "created_by"],
                "material": ["material_name", "item_name", "name", "description"],
                "cantidad": ["quantity", "qty", "amount"],
                "estado": ["status", "state"],
                "observacion": ["notes", "observation", "observations", "detail", "comments"],
            },
            date_from=start,
            date_to=end,
        )
        if section:
            sections.append(section)

    if "inventory" in active_codes or "stock" in active_codes:
        section = await generic_section(
            db,
            company_id=company_id,
            code="inventory",
            title="Inventario y stock",
            table_candidates=["inventory_items", "stock_items", "company_inventory_items"],
            columns_map={
                "item": ["item_name", "material_name", "name", "description"],
                "cantidad": ["quantity", "stock", "current_stock"],
                "minimo": ["minimum_stock", "min_stock"],
                "estado": ["status", "state"],
                "observacion": ["notes", "observation", "observations", "detail"],
            },
            date_from=start,
            date_to=end,
        )
        if section:
            sections.append(section)

    if "gps" in active_codes:
        section = await generic_section(
            db,
            company_id=company_id,
            code="gps",
            title="GPS y ubicaciones",
            table_candidates=["gps_events", "company_gps_events", "location_events", "employee_locations"],
            columns_map={
                "empleado": ["employee_name", "user_name", "responsible"],
                "latitud": ["latitude", "lat"],
                "longitud": ["longitude", "lng", "lon"],
                "estado": ["status", "state"],
                "observacion": ["notes", "observation", "observations", "detail"],
            },
            date_from=start,
            date_to=end,
        )
        if section:
            sections.append(section)

    total_rows = sum(len(section.get("rows") or []) for section in sections)

    return {
        **base,
        "report_mode": "detailed_adaptive_report",
        "total_rows": total_rows,
        "sections": sections,
    }


@router.get("/companies/{company_id}/detail.csv")
async def adaptive_report_detail_csv(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    data = await adaptive_report_detail(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        db=db,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["CLONEXA - Reporte adaptativo"])
    writer.writerow(["empresa", company_id])
    writer.writerow(["desde", data.get("date_from")])
    writer.writerow(["hasta", data.get("date_to")])
    writer.writerow(["registros", data.get("total_rows")])
    writer.writerow([])

    for section in data.get("sections") or []:
        writer.writerow([section.get("title")])
        cols = section.get("columns") or []
        writer.writerow(cols)

        for row in section.get("rows") or []:
            writer.writerow([row.get(col, "") for col in cols])

        writer.writerow([])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="clonexa_reporte_detallado_{company_id}.csv"'
        },
    )
