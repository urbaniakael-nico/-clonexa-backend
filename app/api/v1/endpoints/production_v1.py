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


async def ensure_storage(db: AsyncSession) -> None:
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS product_references (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            name text NOT NULL,
            size text NOT NULL,
            initial_quantity integer NOT NULL DEFAULT 0,
            activation_date timestamptz NULL,
            bot_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_production_closures (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
            reference_id text NULL,
            reference_name text NOT NULL,
            size text NOT NULL,
            quantity_finished integer NOT NULL DEFAULT 0,
            notes text NULL,
            closed_at timestamptz NOT NULL DEFAULT now(),
            source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_work_sessions (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
            reference_id text NULL,
            reference_name text NOT NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz NULL,
            duration_minutes numeric NOT NULL DEFAULT 0,
            status text NOT NULL DEFAULT 'active',
            source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_reference_production_closures_company_closed
        ON reference_production_closures (company_id, closed_at DESC)
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_reference_work_sessions_company_status
        ON reference_work_sessions (company_id, status)
    """))


async def active_modules(db: AsyncSession, company_id: str) -> set[str]:
    return {
        clean(row.get("code")).lower()
        for row in await safe_rows(
            db,
            """
            SELECT lower(m.code) AS code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id::text = :company_id
              AND COALESCE(cm.enabled, true) IS TRUE
              AND COALESCE(m.is_active, true) IS TRUE
            """,
            {"company_id": company_id},
        )
    }


async def reference_rows(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    rows = await safe_rows(
        db,
        """
        SELECT
            pr.id,
            pr.name,
            pr.size,
            COALESCE(pr.initial_quantity, 0) AS initial_quantity,
            COALESCE(pr.bot_active, false) AS bot_active,
            pr.activation_date::text AS activation_date,
            COALESCE((
                SELECT sum(c.quantity_finished)
                FROM reference_production_closures c
                WHERE c.company_id::text = :company_id
                  AND (
                    c.reference_id = pr.id
                    OR (
                        lower(COALESCE(c.reference_name, '')) = lower(COALESCE(pr.name, ''))
                        AND lower(COALESCE(c.size, '')) = lower(COALESCE(pr.size, ''))
                    )
                  )
            ), 0) AS finished_quantity
        FROM product_references pr
        WHERE pr.company_id::text = :company_id
        ORDER BY pr.name ASC, pr.size ASC
        """,
        {"company_id": company_id},
    )

    output = []

    for row in rows:
        initial = intval(row.get("initial_quantity"))
        finished = intval(row.get("finished_quantity"))
        pending = max(initial - finished, 0)
        over_finished = max(finished - initial, 0)
        progress = round((finished / initial) * 100, 2) if initial > 0 else 0

        output.append({
            "id": row.get("id"),
            "name": clean(row.get("name")),
            "size": clean(row.get("size")),
            "initial_quantity": initial,
            "finished_quantity": finished,
            "pending_quantity": pending,
            "over_finished_quantity": over_finished,
            "progress_percent": progress,
            "bot_active": bool(row.get("bot_active")),
            "activation_date": row.get("activation_date"),
        })

    return output


async def closures_rows(db: AsyncSession, company_id: str, start: date, end: date, limit: int = 300) -> list[dict[str, Any]]:
    return await safe_rows(
        db,
        """
        SELECT
            id,
            company_id,
            employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            COALESCE(size, '') AS size,
            COALESCE(quantity_finished, 0) AS quantity_finished,
            COALESCE(notes, '') AS notes,
            closed_at::text AS closed_at,
            COALESCE(source_channel, '') AS source_channel
        FROM reference_production_closures
        WHERE company_id::text = :company_id
          AND closed_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        ORDER BY closed_at DESC
        LIMIT :limit
        """,
        {
            "company_id": company_id,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "limit": limit,
        },
    )


async def closures_all_time_rows(db: AsyncSession, company_id: str, limit: int = 300) -> list[dict[str, Any]]:
    return await safe_rows(
        db,
        """
        SELECT
            id,
            company_id,
            employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            COALESCE(size, '') AS size,
            COALESCE(quantity_finished, 0) AS quantity_finished,
            COALESCE(notes, '') AS notes,
            closed_at::text AS closed_at,
            COALESCE(source_channel, '') AS source_channel
        FROM reference_production_closures
        WHERE company_id::text = :company_id
        ORDER BY closed_at DESC
        LIMIT :limit
        """,
        {
            "company_id": company_id,
            "limit": limit,
        },
    )


async def sessions_summary(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any]:
    active_sessions = intval(await safe_scalar(
        db,
        """
        SELECT count(*)
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND status = 'active'
        """,
        {"company_id": company_id},
    ))

    total_sessions = intval(await safe_scalar(
        db,
        """
        SELECT count(*)
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND started_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        """,
        {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()},
    ))

    total_minutes = round(fval(await safe_scalar(
        db,
        """
        SELECT COALESCE(sum(duration_minutes), 0)
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND started_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        """,
        {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()},
    )), 2)

    by_reference = await safe_rows(
        db,
        """
        SELECT
            COALESCE(reference_name, 'Sin referencia') AS reference_name,
            COALESCE(sum(duration_minutes), 0) AS minutes,
            count(*) AS sessions
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND started_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        GROUP BY reference_name
        ORDER BY minutes DESC, reference_name ASC
        LIMIT 20
        """,
        {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()},
    )

    return {
        "active_sessions": active_sessions,
        "total_sessions_period": total_sessions,
        "total_minutes_period": total_minutes,
        "by_reference": [
            {
                "reference_name": clean(row.get("reference_name")),
                "minutes": round(fval(row.get("minutes")), 2),
                "sessions": intval(row.get("sessions")),
            }
            for row in by_reference
        ],
    }


def build_summary(
    *,
    company_id: str,
    modules: set[str],
    start: date,
    end: date,
    refs: list[dict[str, Any]],
    closures_period: list[dict[str, Any]],
    closures_all: list[dict[str, Any]],
    sessions: dict[str, Any],
) -> dict[str, Any]:
    initial_total = sum(intval(row.get("initial_quantity")) for row in refs)
    finished_total = sum(intval(row.get("finished_quantity")) for row in refs)
    pending_total = sum(intval(row.get("pending_quantity")) for row in refs)
    over_finished_total = sum(intval(row.get("over_finished_quantity")) for row in refs)

    progress = round((finished_total / initial_total) * 100, 2) if initial_total > 0 else 0

    period_finished = sum(intval(row.get("quantity_finished")) for row in closures_period)

    by_employee_map: dict[str, dict[str, Any]] = {}
    by_reference_period: dict[str, dict[str, Any]] = {}

    graph_rows = closures_period if closures_period else closures_all

    for row in graph_rows:
        employee = clean(row.get("employee_name")) or clean(row.get("employee_id")) or "Sin empleado"
        emp = by_employee_map.setdefault(employee, {"employee": employee, "closures": 0, "finished_quantity": 0})
        emp["closures"] += 1
        emp["finished_quantity"] += intval(row.get("quantity_finished"))

        ref_key = f"{clean(row.get('reference_name'))} / {clean(row.get('size'))}".strip(" /")
        ref = by_reference_period.setdefault(ref_key, {"reference": ref_key, "closures": 0, "finished_quantity": 0})
        ref["closures"] += 1
        ref["finished_quantity"] += intval(row.get("quantity_finished"))

    return {
        "ok": True,
        "company_id": company_id,
        "language": "es",
        "module": "production",
        "module_active": "production" in modules,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "totals": {
            "references_total": len(refs),
            "bot_active_total": sum(1 for row in refs if row.get("bot_active")),
            "initial_quantity_total": initial_total,
            "finished_quantity_total": finished_total,
            "pending_quantity_total": pending_total,
            "over_finished_quantity_total": over_finished_total,
            "progress_percent": progress,
            "closures_total": len(closures_all),
            "closures_period": len(closures_period),
            "finished_quantity_period": period_finished,
            "active_sessions": sessions.get("active_sessions", 0),
            "sessions_period": sessions.get("total_sessions_period", 0),
            "minutes_period": sessions.get("total_minutes_period", 0),
        },
        "references": refs,
        "closures_period": closures_period,
        "closures_display": graph_rows,
        "closures_all_time": closures_all,
        "by_employee_period": sorted(by_employee_map.values(), key=lambda x: x["finished_quantity"], reverse=True),
        "by_reference_period": sorted(by_reference_period.values(), key=lambda x: x["finished_quantity"], reverse=True),
        "graph_source": "period" if closures_period else "all_time_fallback",
        "sessions": sessions,
        "time_rule": "pause_excluded_from_shift_and_reference",
    }


@router.get("/companies/{company_id}/summary")
async def production_summary(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    start, end = date_range(date_from, date_to, preset)
    modules = await active_modules(db, company_id)
    refs = await reference_rows(db, company_id)
    closures_period = await closures_rows(db, company_id, start, end, 500)
    closures_all = await closures_all_time_rows(db, company_id, 500)
    sessions = await sessions_summary(db, company_id, start, end)

    return build_summary(
        company_id=company_id,
        modules=modules,
        start=start,
        end=end,
        refs=refs,
        closures_period=closures_period,
        closures_all=closures_all,
        sessions=sessions,
    )


@router.get("/companies/{company_id}/closures")
async def production_closures(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    start, end = date_range(date_from, date_to, preset)
    rows = await closures_rows(db, company_id, start, end, 1000)

    return {
        "ok": True,
        "company_id": company_id,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "count": len(rows),
        "items": rows,
    }


@router.get("/companies/{company_id}/export.csv")
async def production_export_csv(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    data = await production_summary(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        db=db,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["CLONEXA - Producción"])
    writer.writerow(["empresa", company_id])
    writer.writerow(["desde", data["date_from"]])
    writer.writerow(["hasta", data["date_to"]])
    writer.writerow([])

    writer.writerow(["Resumen"])
    for key, value in data["totals"].items():
        writer.writerow([key, value])

    writer.writerow([])
    writer.writerow(["Referencias"])
    writer.writerow(["referencia", "talla", "inicial", "terminada", "pendiente", "sobreproducida", "avance", "bot"])
    for row in data["references"]:
        writer.writerow([
            row.get("name"),
            row.get("size"),
            row.get("initial_quantity"),
            row.get("finished_quantity"),
            row.get("pending_quantity"),
            row.get("over_finished_quantity"),
            row.get("progress_percent"),
            row.get("bot_active"),
        ])

    writer.writerow([])
    writer.writerow(["Cierres del periodo"])
    writer.writerow(["fecha", "empleado", "referencia", "talla", "total", "canal", "notas"])
    for row in data["closures_period"]:
        writer.writerow([
            row.get("closed_at"),
            row.get("employee_name"),
            row.get("reference_name"),
            row.get("size"),
            row.get("quantity_finished"),
            row.get("source_channel"),
            row.get("notes"),
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="clonexa_produccion_{company_id}.csv"'
        },
    )
