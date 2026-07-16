from __future__ import annotations

import json
import uuid

from datetime import datetime, timezone

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.payroll import calculate_period_snapshot

router = APIRouter()
BUSINESS_TIMEZONE = ZoneInfo("America/Bogota")


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
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS archived_at timestamptz NULL
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS archived_by text NULL
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS archive_reason text NULL
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS archived_snapshot_id text NULL
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS production_archive_snapshots (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            reference_id text NULL,
            reference_name text NULL,
            size text NULL,
            snapshot_type text NOT NULL DEFAULT 'reference_archive',
            date_from date NULL,
            date_to date NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_product_references_company_archived
        ON product_references (company_id, archived_at)
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_production_archive_snapshots_company_created
        ON production_archive_snapshots (company_id, created_at DESC)
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


async def reference_rows(db: AsyncSession, company_id: str, view: str = "active") -> list[dict[str, Any]]:
    view = clean(view or "active").lower()
    if view not in {"active", "archived", "all"}:
        view = "active"

    where = ["pr.company_id::text = :company_id"]
    params: dict[str, Any] = {"company_id": company_id}

    if view == "active":
        where.append("pr.archived_at IS NULL")
    elif view == "archived":
        where.append("pr.archived_at IS NOT NULL")

    rows = await safe_rows(
        db,
        f"""
        SELECT
            pr.id,
            pr.name,
            pr.size,
            COALESCE(pr.initial_quantity, 0) AS initial_quantity,
            COALESCE(pr.bot_active, false) AS bot_active,
            pr.activation_date::text AS activation_date,
            pr.archived_at::text AS archived_at,
            COALESCE(pr.archived_by, '') AS archived_by,
            COALESCE(pr.archive_reason, '') AS archive_reason,
            COALESCE(pr.archived_snapshot_id, '') AS archived_snapshot_id,
            COALESCE((
                SELECT sum(c.quantity_finished)
                FROM reference_production_closures c
                WHERE c.company_id::text = :company_id
                  AND (pr.activation_date IS NULL OR c.closed_at >= pr.activation_date)
                  AND (
                    (COALESCE(c.reference_id, '') <> '' AND c.reference_id = pr.id)
                    OR (
                        COALESCE(c.reference_id, '') = ''
                        AND
                        lower(COALESCE(c.reference_name, '')) = lower(COALESCE(pr.name, ''))
                        AND lower(COALESCE(c.size, '')) = lower(COALESCE(pr.size, ''))
                    )
                  )
            ), 0) AS finished_quantity
        FROM product_references pr
        WHERE {" AND ".join(where)}
        ORDER BY
            CASE WHEN pr.archived_at IS NULL THEN 0 ELSE 1 END,
            pr.name ASC,
            pr.size ASC
        """,
        params,
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
            "name": row.get("name"),
            "size": row.get("size"),
            "initial_quantity": initial,
            "finished_quantity": finished,
            "pending_quantity": pending,
            "over_finished_quantity": over_finished,
            "progress_percent": progress,
            "bot_active": bool(row.get("bot_active")),
            "activation_date": row.get("activation_date"),
            "archived": bool(row.get("archived_at")),
            "archived_at": row.get("archived_at"),
            "archived_by": row.get("archived_by"),
            "archive_reason": row.get("archive_reason"),
            "archived_snapshot_id": row.get("archived_snapshot_id"),
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
          AND (closed_at AT TIME ZONE 'America/Bogota')::date
              BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
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


# CLONEXA PRODUCTION_TIME_01
def _prod_parse_dt(value: Any):
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        raw = clean(value)
        if not raw:
            return None

        raw = raw.replace(" ", "T")

        if raw.endswith("+00"):
            raw = raw[:-3] + "+00:00"

        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _prod_dt_text(value) -> str | None:
    if not value:
        return None

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _prod_seconds_between(start_at, end_at) -> int:
    if not start_at or not end_at:
        return 0

    return max(int((end_at - start_at).total_seconds()), 0)


def _prod_overlap_seconds(a_start, a_end, b_start, b_end) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)

    if end <= start:
        return 0

    return int((end - start).total_seconds())


def _prod_format_seconds(seconds: int) -> str:
    seconds = max(int(seconds or 0), 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    return f"{h:02d}:{m:02d}:{s:02d}"


def _prod_period_bounds_023r(start: date, end: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(start, datetime.min.time(), tzinfo=BUSINESS_TIMEZONE)
    local_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=BUSINESS_TIMEZONE)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _prod_identity_keys_023r(employee_id: str, telegram_user_id: str = "", employee_name: str = "") -> list[str]:
    keys: list[str] = []
    employee = clean(employee_id)
    telegram = clean(telegram_user_id)
    name = clean(employee_name).lower()

    if employee:
        keys.append(f"employee:{employee}")
    if telegram:
        keys.append(f"telegram:{telegram}")
    if name:
        keys.append(f"name:{name}")
    return keys


def _prod_primary_session_key_023r(session: dict[str, Any]) -> str:
    keys = _prod_identity_keys_023r(
        clean(session.get("employee_id")),
        clean(session.get("telegram_user_id")),
        clean(session.get("employee_name")),
    )
    return keys[0] if keys else "operator:unknown"


def _prod_attach_next_reference_start_023r(sessions: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        started_at = _prod_parse_dt(session.get("started_at"))
        if not started_at:
            continue
        session["_started_at_023r"] = started_at
        grouped.setdefault(_prod_primary_session_key_023r(session), []).append(session)

    for rows in grouped.values():
        rows.sort(key=lambda item: item.get("_started_at_023r") or datetime.min.replace(tzinfo=timezone.utc))
        for index, session in enumerate(rows[:-1]):
            session["_next_started_at_023r"] = rows[index + 1].get("_started_at_023r")


def _prod_ref_key(reference_id: str, reference_name: str, size: str) -> str:
    rid = clean(reference_id)

    if rid:
        return f"id:{rid}"

    return f"name:{clean(reference_name).lower()}|size:{clean(size).lower()}"


def _prod_reference_time_key(reference_name: str) -> str:
    return f"name:{clean(reference_name).casefold()}"


def _prod_operator_key(employee_id: str, employee_name: str, telegram_user_id: str, ref_key: str) -> str:
    emp = clean(employee_id) or clean(telegram_user_id) or clean(employee_name).lower() or "sin_operario"
    return f"{emp}|{ref_key}"


async def _prod_columns(db: AsyncSession, table_name: str) -> set[str]:
    rows = await safe_rows(
        db,
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
        """,
        {"table_name": table_name},
    )

    return {clean(row.get("column_name")) for row in rows}


async def _prod_pause_intervals(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    telegram_user_id: str,
    employee_name: str,
    start_at,
    end_at,
) -> list[tuple[Any, Any]]:
    if not start_at or not end_at:
        return []

    if not await table_exists(db, "workforce_attendance_events"):
        return []

    cols = await _prod_columns(db, "workforce_attendance_events")

    if "event_type" not in cols or "company_id" not in cols:
        return []

    if "occurred_at" in cols and "created_at" in cols:
        at_expr = "COALESCE(occurred_at, created_at)"
    elif "occurred_at" in cols:
        at_expr = "occurred_at"
    elif "created_at" in cols:
        at_expr = "created_at"
    else:
        return []

    match_parts = []

    if "employee_id" in cols:
        match_parts.append("employee_id::text = :employee_id")

    if "telegram_user_id" in cols:
        match_parts.append("(:telegram_user_id <> '' AND telegram_user_id::text = :telegram_user_id)")

    if "employee_name" in cols:
        match_parts.append("(:employee_name <> '' AND lower(COALESCE(employee_name, '')) = lower(:employee_name))")

    if not match_parts:
        return []

    rows = await safe_rows(
        db,
        f"""
        SELECT
            lower(COALESCE(event_type, '')) AS event_type,
            {at_expr}::text AS event_at
        FROM workforce_attendance_events
        WHERE company_id::text = :company_id
          AND ({' OR '.join(match_parts)})
          AND {at_expr} >= CAST(:start_at AS timestamptz)
          AND {at_expr} <= CAST(:end_at AS timestamptz)
          AND lower(COALESCE(event_type, '')) IN (
            'break_start',
            'pause_start',
            'pause',
            'pausa',
            'break',
            'on_break',
            'break_end',
            'pause_end',
            'resume',
            'return',
            'retorno',
            'reanudar',
            'clock_resume'
          )
        ORDER BY {at_expr} ASC
        LIMIT 1000
        """,
        {
            "company_id": company_id,
            "employee_id": clean(employee_id),
            "telegram_user_id": clean(telegram_user_id),
            "employee_name": clean(employee_name),
            "start_at": _prod_dt_text(start_at),
            "end_at": _prod_dt_text(end_at),
        },
    )

    start_events = {"break_start", "pause_start", "pause", "pausa", "break", "on_break"}
    end_events = {"break_end", "pause_end", "resume", "return", "retorno", "reanudar", "clock_resume"}

    intervals = []
    open_pause = None

    for row in rows:
        event_type = clean(row.get("event_type")).lower()
        event_at = _prod_parse_dt(row.get("event_at"))

        if not event_at:
            continue

        if event_type in start_events:
            if open_pause is None:
                open_pause = event_at
            continue

        if event_type in end_events:
            if open_pause and event_at > open_pause:
                intervals.append((open_pause, event_at))
                open_pause = None
            continue

    # Si la pausa sigue abierta dentro de la sesión, congela hasta el cierre de la ventana.
    if open_pause and end_at > open_pause:
        intervals.append((open_pause, end_at))

    return intervals


async def _prod_effective_seconds(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    telegram_user_id: str,
    employee_name: str,
    start_at,
    end_at,
) -> int:
    if not start_at or not end_at:
        return 0

    raw_seconds = _prod_seconds_between(start_at, end_at)

    pauses = await _prod_pause_intervals(
        db,
        company_id,
        employee_id,
        telegram_user_id,
        employee_name,
        start_at,
        end_at,
    )

    pause_seconds = sum(_prod_overlap_seconds(start_at, end_at, p_start, p_end) for p_start, p_end in pauses)

    return max(raw_seconds - pause_seconds, 0)


async def _prod_closure_totals(db: AsyncSession, company_id: str, start: date, end: date) -> tuple[dict[str, int], dict[str, int]]:
    period_rows = await safe_rows(
        db,
        """
        SELECT
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            COALESCE(size, '') AS size,
            COALESCE(employee_id, '') AS employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(sum(quantity_finished), 0) AS quantity_finished
        FROM reference_production_closures
        WHERE company_id::text = :company_id
          AND (closed_at AT TIME ZONE 'America/Bogota')::date
              BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        GROUP BY reference_id, reference_name, size, employee_id, employee_name, telegram_user_id
        """,
        {
            "company_id": company_id,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
        },
    )

    all_rows = await safe_rows(
        db,
        """
        SELECT
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            COALESCE(size, '') AS size,
            COALESCE(employee_id, '') AS employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(sum(quantity_finished), 0) AS quantity_finished
        FROM reference_production_closures
        WHERE company_id::text = :company_id
        GROUP BY reference_id, reference_name, size, employee_id, employee_name, telegram_user_id
        """,
        {"company_id": company_id},
    )

    def build(rows):
        out: dict[str, int] = {}
        for row in rows:
            ref_key = _prod_ref_key(row.get("reference_id"), row.get("reference_name"), row.get("size"))
            reference_time_key = _prod_reference_time_key(row.get("reference_name"))
            op_key = _prod_operator_key(
                row.get("employee_id"),
                row.get("employee_name"),
                row.get("telegram_user_id"),
                ref_key,
            )
            operator_reference_time_key = _prod_operator_key(
                row.get("employee_id"),
                row.get("employee_name"),
                row.get("telegram_user_id"),
                reference_time_key,
            )

            qty = intval(row.get("quantity_finished"))
            out[ref_key] = out.get(ref_key, 0) + qty
            out[op_key] = out.get(op_key, 0) + qty
            if reference_time_key != ref_key:
                out[reference_time_key] = out.get(reference_time_key, 0) + qty
            if operator_reference_time_key != op_key:
                out[operator_reference_time_key] = out.get(operator_reference_time_key, 0) + qty

        return out

    return build(period_rows), build(all_rows)


# CLONEXA PRODUCTION_TIME_02_DIRECT_SESSIONS
def _prod_parse_dt(value: Any):
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        raw = clean(value)
        if not raw:
            return None

        raw = raw.replace(" ", "T")

        if raw.endswith("+00"):
            raw = raw[:-3] + "+00:00"

        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _prod_dt_text(value) -> str | None:
    if not value:
        return None

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _prod_seconds_between(start_at, end_at) -> int:
    if not start_at or not end_at:
        return 0

    return max(int((end_at - start_at).total_seconds()), 0)


def _prod_overlap_seconds(a_start, a_end, b_start, b_end) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)

    if end <= start:
        return 0

    return int((end - start).total_seconds())


def _prod_format_seconds(seconds: int) -> str:
    seconds = max(int(seconds or 0), 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    return f"{h:02d}:{m:02d}:{s:02d}"


def _prod_ref_key(reference_id: str, reference_name: str, size: str) -> str:
    rid = clean(reference_id)

    if rid:
        return f"id:{rid}"

    return f"name:{clean(reference_name).lower()}|size:{clean(size).lower()}"


def _prod_operator_key(employee_id: str, employee_name: str, telegram_user_id: str, ref_key: str) -> str:
    emp = clean(employee_id) or clean(telegram_user_id) or clean(employee_name).lower() or "sin_operario"
    return f"{emp}|{ref_key}"


async def _prod_columns(db: AsyncSession, table_name: str) -> set[str]:
    rows = await safe_rows(
        db,
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
        """,
        {"table_name": table_name},
    )

    return {clean(row.get("column_name")) for row in rows}


async def _prod_pause_intervals(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    telegram_user_id: str,
    employee_name: str,
    start_at,
    end_at,
) -> list[tuple[Any, Any]]:
    if not start_at or not end_at:
        return []

    if not await table_exists(db, "workforce_attendance_events"):
        return []

    cols = await _prod_columns(db, "workforce_attendance_events")

    if "event_type" not in cols or "company_id" not in cols:
        return []

    if "occurred_at" in cols and "created_at" in cols:
        at_expr = "COALESCE(occurred_at, created_at)"
    elif "occurred_at" in cols:
        at_expr = "occurred_at"
    elif "created_at" in cols:
        at_expr = "created_at"
    else:
        return []

    match_parts = []

    if "employee_id" in cols:
        match_parts.append("employee_id::text = :employee_id")

    if "telegram_user_id" in cols:
        match_parts.append("(:telegram_user_id <> '' AND telegram_user_id::text = :telegram_user_id)")

    if "employee_name" in cols:
        match_parts.append("(:employee_name <> '' AND lower(COALESCE(employee_name, '')) = lower(:employee_name))")

    if not match_parts:
        return []

    rows = await safe_rows(
        db,
        f"""
        SELECT
            lower(COALESCE(event_type, '')) AS event_type,
            {at_expr}::text AS event_at
        FROM workforce_attendance_events
        WHERE company_id::text = :company_id
          AND ({' OR '.join(match_parts)})
          AND {at_expr} >= CAST(:start_at AS timestamptz)
          AND {at_expr} <= CAST(:end_at AS timestamptz)
          AND lower(COALESCE(event_type, '')) IN (
            'break_start',
            'pause_start',
            'pause',
            'pausa',
            'break',
            'on_break',
            'break_end',
            'pause_end',
            'resume',
            'return',
            'retorno',
            'reanudar',
            'clock_resume'
          )
        ORDER BY {at_expr} ASC
        LIMIT 1000
        """,
        {
            "company_id": company_id,
            "employee_id": clean(employee_id),
            "telegram_user_id": clean(telegram_user_id),
            "employee_name": clean(employee_name),
            "start_at": _prod_dt_text(start_at),
            "end_at": _prod_dt_text(end_at),
        },
    )

    start_events = {"break_start", "pause_start", "pause", "pausa", "break", "on_break"}
    end_events = {"break_end", "pause_end", "resume", "return", "retorno", "reanudar", "clock_resume"}

    intervals = []
    open_pause = None

    for row in rows:
        event_type = clean(row.get("event_type")).lower()
        event_at = _prod_parse_dt(row.get("event_at"))

        if not event_at:
            continue

        if event_type in start_events:
            if open_pause is None:
                open_pause = event_at
            continue

        if event_type in end_events:
            if open_pause and event_at > open_pause:
                intervals.append((open_pause, event_at))
                open_pause = None
            continue

    if open_pause and end_at > open_pause:
        intervals.append((open_pause, end_at))

    return intervals


async def _prod_effective_seconds(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    telegram_user_id: str,
    employee_name: str,
    start_at,
    end_at,
) -> int:
    if not start_at or not end_at:
        return 0

    raw_seconds = _prod_seconds_between(start_at, end_at)

    pauses = await _prod_pause_intervals(
        db,
        company_id,
        employee_id,
        telegram_user_id,
        employee_name,
        start_at,
        end_at,
    )

    pause_seconds = sum(_prod_overlap_seconds(start_at, end_at, p_start, p_end) for p_start, p_end in pauses)

    return max(raw_seconds - pause_seconds, 0)


async def _prod_closure_totals(db: AsyncSession, company_id: str, start: date, end: date) -> tuple[dict[str, int], dict[str, int]]:
    if not await table_exists(db, "reference_production_closures"):
        return {}, {}

    period_rows = await safe_rows(
        db,
        """
        SELECT
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            COALESCE(size, '') AS size,
            COALESCE(employee_id, '') AS employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(sum(quantity_finished), 0) AS quantity_finished
        FROM reference_production_closures
        WHERE company_id::text = :company_id
          AND (closed_at AT TIME ZONE 'America/Bogota')::date
              BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        GROUP BY reference_id, reference_name, size, employee_id, employee_name, telegram_user_id
        """,
        {
            "company_id": company_id,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
        },
    )

    all_rows = await safe_rows(
        db,
        """
        SELECT
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            COALESCE(size, '') AS size,
            COALESCE(employee_id, '') AS employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(sum(quantity_finished), 0) AS quantity_finished
        FROM reference_production_closures
        WHERE company_id::text = :company_id
        GROUP BY reference_id, reference_name, size, employee_id, employee_name, telegram_user_id
        """,
        {"company_id": company_id},
    )

    def build(rows):
        ref_out: dict[str, int] = {}
        op_out: dict[str, int] = {}

        for row in rows:
            ref_key = _prod_ref_key(row.get("reference_id"), row.get("reference_name"), row.get("size"))
            reference_time_key = _prod_reference_time_key(row.get("reference_name"))
            op_key = _prod_operator_key(
                row.get("employee_id"),
                row.get("employee_name"),
                row.get("telegram_user_id"),
                ref_key,
            )
            operator_reference_time_key = _prod_operator_key(
                row.get("employee_id"),
                row.get("employee_name"),
                row.get("telegram_user_id"),
                reference_time_key,
            )

            qty = intval(row.get("quantity_finished"))
            ref_out[ref_key] = ref_out.get(ref_key, 0) + qty
            op_out[op_key] = op_out.get(op_key, 0) + qty
            if reference_time_key != ref_key:
                ref_out[reference_time_key] = ref_out.get(reference_time_key, 0) + qty
            if operator_reference_time_key != op_key:
                op_out[operator_reference_time_key] = op_out.get(operator_reference_time_key, 0) + qty

        merged = {}
        merged.update(ref_out)
        merged.update(op_out)
        return merged

    return build(period_rows), build(all_rows)


def _prod_merge_intervals_023r(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    cleaned = sorted((start, end) for start, end in intervals if start and end and end > start)
    merged: list[tuple[datetime, datetime]] = []
    for start, end in cleaned:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


async def _prod_work_intervals_023r(
    db: AsyncSession,
    company_id: str,
    start_dt: datetime,
    end_dt: datetime,
    as_of: datetime,
) -> dict[str, list[tuple[datetime, datetime]]]:
    intervals_by_key: dict[str, list[tuple[datetime, datetime]]] = {}

    def add_interval(employee_id: Any, employee_name: Any, telegram_user_id: Any, raw_start: Any, raw_end: Any) -> None:
        started = _prod_parse_dt(raw_start)
        ended = _prod_parse_dt(raw_end) or as_of
        if not started or not ended:
            return
        clipped_start = max(started, start_dt)
        clipped_end = min(ended, end_dt, as_of)
        if clipped_end <= clipped_start:
            return
        for key in _prod_identity_keys_023r(clean(employee_id), clean(telegram_user_id), clean(employee_name)):
            intervals_by_key.setdefault(key, []).append((clipped_start, clipped_end))

    if await table_exists(db, "mini_panel_work_sessions"):
        rows = await safe_rows(
            db,
            """
            SELECT
                s.employee_id::text AS employee_id,
                COALESCE(e.full_name, '') AS employee_name,
                s.started_at::text AS started_at,
                COALESCE(s.ended_at, CAST(:as_of AS timestamptz))::text AS ended_at
            FROM mini_panel_work_sessions s
            LEFT JOIN employees e
              ON e.id = s.employee_id
             AND e.company_id = s.company_id
            WHERE s.company_id::text = :company_id
              AND s.employee_id IS NOT NULL
              AND s.started_at < CAST(:end_dt AS timestamptz)
              AND COALESCE(s.ended_at, CAST(:as_of AS timestamptz)) > CAST(:start_dt AS timestamptz)
            ORDER BY s.started_at ASC
            LIMIT 2000
            """,
            {
                "company_id": company_id,
                "start_dt": _prod_dt_text(start_dt),
                "end_dt": _prod_dt_text(end_dt),
                "as_of": _prod_dt_text(as_of),
            },
        )
        for row in rows:
            add_interval(row.get("employee_id"), row.get("employee_name"), "", row.get("started_at"), row.get("ended_at"))

    if await table_exists(db, "workforce_attendance_events"):
        rows = await safe_rows(
            db,
            """
            SELECT
                ev.employee_id::text AS employee_id,
                COALESCE(ev.employee_name, e.full_name, '') AS employee_name,
                lower(COALESCE(ev.event_type, '')) AS event_type,
                COALESCE(ev.occurred_at, ev.created_at)::text AS event_at
            FROM workforce_attendance_events ev
            LEFT JOIN employees e
              ON e.id = ev.employee_id
             AND e.company_id = ev.company_id
            WHERE ev.company_id::text = :company_id
              AND ev.employee_id IS NOT NULL
              AND COALESCE(ev.occurred_at, ev.created_at) >= CAST(:lookback_dt AS timestamptz)
              AND COALESCE(ev.occurred_at, ev.created_at) <= CAST(:as_of AS timestamptz)
              AND lower(COALESCE(ev.event_type, '')) IN (
                  'check_in', 'entrada', 'start_shift', 'shift_start',
                  'check_out', 'salida', 'end_shift', 'shift_end'
              )
            ORDER BY COALESCE(ev.occurred_at, ev.created_at) ASC
            LIMIT 3000
            """,
            {
                "company_id": company_id,
                "lookback_dt": _prod_dt_text(start_dt - timedelta(days=2)),
                "as_of": _prod_dt_text(as_of),
            },
        )

        starts = {"check_in", "entrada", "start_shift", "shift_start"}
        ends = {"check_out", "salida", "end_shift", "shift_end"}
        open_shifts: dict[str, dict[str, Any]] = {}

        for row in rows:
            employee_id = clean(row.get("employee_id"))
            event_at = _prod_parse_dt(row.get("event_at"))
            event_type = clean(row.get("event_type")).lower()
            if not employee_id or not event_at:
                continue
            if event_type in starts:
                open_shifts[employee_id] = {
                    "employee_id": employee_id,
                    "employee_name": row.get("employee_name"),
                    "started_at": event_at,
                }
                continue
            if event_type in ends:
                opened = open_shifts.pop(employee_id, None)
                if opened:
                    add_interval(employee_id, opened.get("employee_name"), "", opened.get("started_at"), event_at)

        for opened in open_shifts.values():
            add_interval(opened.get("employee_id"), opened.get("employee_name"), "", opened.get("started_at"), as_of)

    return {key: _prod_merge_intervals_023r(value) for key, value in intervals_by_key.items()}


def _prod_matching_work_intervals_023r(
    intervals_by_key: dict[str, list[tuple[datetime, datetime]]],
    employee_id: str,
    telegram_user_id: str,
    employee_name: str,
) -> list[tuple[datetime, datetime]]:
    intervals: list[tuple[datetime, datetime]] = []
    for key in _prod_identity_keys_023r(employee_id, telegram_user_id, employee_name):
        intervals.extend(intervals_by_key.get(key, []))
    return _prod_merge_intervals_023r(intervals)


async def _prod_payroll_caps_023r(
    db: AsyncSession,
    company_id: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    try:
        snapshot = await calculate_period_snapshot(db, uuid.UUID(str(company_id)), start, end)
    except Exception:
        await db.rollback()
        return {"caps": {}, "total_seconds": 0, "source": "unavailable"}

    caps: dict[str, int] = {}
    total_seconds = 0
    for row in snapshot.get("rows") or []:
        seconds = max(0, (intval(row.get("regular_minutes")) + intval(row.get("extra_minutes"))) * 60)
        if seconds <= 0:
            continue
        total_seconds += seconds
        for key in _prod_identity_keys_023r(
            clean(row.get("employee_id")),
            "",
            clean(row.get("employee_name")),
        ):
            caps[key] = max(caps.get(key, 0), seconds)

    return {"caps": caps, "total_seconds": total_seconds, "source": "payroll_calculate_period"}


def _prod_cap_operator_reference_seconds_023r(
    by_operator_reference: dict[str, dict[str, Any]],
    payroll_caps: dict[str, int],
) -> tuple[bool, int]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in by_operator_reference.values():
        keys = _prod_identity_keys_023r(
            clean(item.get("employee_id")),
            clean(item.get("telegram_user_id")),
            clean(item.get("employee_name")),
        )
        cap_key = next((key for key in keys if key in payroll_caps), keys[0] if keys else "")
        if cap_key:
            grouped.setdefault(cap_key, []).append(item)

    applied = False
    capped_total = 0
    for key, rows in grouped.items():
        raw_total = sum(int(row.get("effective_seconds") or 0) for row in rows)
        cap = int(payroll_caps.get(key) or 0)
        if raw_total <= 0:
            continue
        if cap > 0 and raw_total > cap:
            ratio = cap / raw_total
            applied = True
            remaining = cap
            for index, row in enumerate(sorted(rows, key=lambda item: int(item.get("effective_seconds") or 0), reverse=True)):
                if index == len(rows) - 1:
                    new_seconds = max(0, remaining)
                else:
                    new_seconds = max(0, int(round(int(row.get("effective_seconds") or 0) * ratio)))
                    remaining -= new_seconds
                row["raw_effective_seconds"] = int(row.get("effective_seconds") or 0)
                row["effective_seconds"] = new_seconds
                row["payroll_cap_applied"] = True
        capped_total += sum(int(row.get("effective_seconds") or 0) for row in rows)

    return applied, capped_total


async def sessions_summary(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any]:
    now_value = datetime.now(timezone.utc)
    period_start_dt, period_end_dt = _prod_period_bounds_023r(start, end)
    as_of = min(now_value, period_end_dt)
    work_intervals = await _prod_work_intervals_023r(db, company_id, period_start_dt, period_end_dt, as_of)
    payroll_cap_data = await _prod_payroll_caps_023r(db, company_id, start, end)
    session_cols = await _prod_columns(db, "reference_work_sessions")

    def session_expr(column: str, default: str = "") -> str:
        if column not in session_cols:
            return f"'{default}' AS {column}"
        return f"COALESCE(s.{column}::text, '{default}') AS {column}"

    def session_number_expr(column: str) -> str:
        if column not in session_cols:
            return f"0 AS {column}"
        return f"COALESCE(s.{column}, 0) AS {column}"

    session_select = ",\n            ".join([
        session_expr("id"),
        session_expr("company_id"),
        session_expr("employee_id"),
        session_expr("employee_name"),
        session_expr("telegram_user_id"),
        session_expr("reference_id"),
        session_expr("reference_name"),
        session_expr("started_at"),
        session_expr("ended_at"),
        session_number_expr("duration_minutes"),
        session_expr("status"),
        session_expr("source_channel"),
        session_expr("created_at"),
        session_expr("updated_at"),
    ])

    active_sessions = intval(await safe_scalar(
        db,
        """
        SELECT count(*)
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND (lower(COALESCE(status::text, '')) = 'active' OR ended_at IS NULL)
        """,
        {"company_id": company_id},
    ))

    # Column-based read: in some legacy/runtime paths, to_jsonb(s) does not
    # arrive as a dict and the panel ends up showing only active sessions.
    raw_rows = await safe_rows(
        db,
        f"""
        SELECT
            {session_select}
        FROM reference_work_sessions s
        WHERE s.company_id::text = :company_id
          AND (
                s.started_at < CAST(:period_end AS timestamptz)
                AND COALESCE(s.ended_at, CAST(:as_of AS timestamptz)) > CAST(:period_start AS timestamptz)
                OR lower(COALESCE(s.status::text, '')) = 'active'
                OR s.ended_at IS NULL
          )
        ORDER BY s.started_at ASC
        LIMIT 2000
        """,
        {
            "company_id": company_id,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "period_start": _prod_dt_text(period_start_dt),
            "period_end": _prod_dt_text(period_end_dt),
            "as_of": _prod_dt_text(as_of),
        },
    )

    query_strategy = "period_or_active_columns"

    # If date casting/filtering fails on legacy rows, prefer the complete
    # company session history over active-only data so the accumulated summary
    # does not collapse to "current" production.
    if not raw_rows:
        raw_rows = await safe_rows(
            db,
            f"""
            SELECT
                {session_select}
            FROM reference_work_sessions s
            WHERE s.company_id::text = :company_id
            ORDER BY COALESCE(s.started_at, s.created_at, s.updated_at) ASC
            LIMIT 2000
            """,
            {"company_id": company_id},
        )
        query_strategy = "company_all_columns_fallback"

    # Final fallback: if it is still empty but active sessions are known to
    # exist, read active sessions directly to keep Production usable.
    if not raw_rows and active_sessions > 0:
        raw_rows = await safe_rows(
            db,
            f"""
            SELECT
                {session_select}
            FROM reference_work_sessions s
            WHERE s.company_id::text = :company_id
              AND (lower(COALESCE(s.status::text, '')) = 'active' OR s.ended_at IS NULL)
            ORDER BY s.started_at ASC
            LIMIT 2000
            """,
            {"company_id": company_id},
        )
        query_strategy = "active_columns_fallback"

    sessions = raw_rows
    _prod_attach_next_reference_start_023r(sessions)

    closure_period, closure_all = await _prod_closure_totals(db, company_id, start, end)

    by_reference: dict[str, dict[str, Any]] = {}
    by_operator_reference: dict[str, dict[str, Any]] = {}

    total_effective_seconds = 0

    for session in sessions:
        employee_id = clean(session.get("employee_id"))
        employee_name = clean(session.get("employee_name")) or "Sin operario"
        telegram_user_id = clean(session.get("telegram_user_id"))
        reference_id = clean(session.get("reference_id"))
        reference_name = clean(session.get("reference_name")) or "Sin referencia"
        size = clean(session.get("size"))
        status = clean(session.get("status")).lower()

        started_at = _prod_parse_dt(session.get("started_at"))
        ended_at = _prod_parse_dt(session.get("ended_at"))
        is_active = status == "active" or ended_at is None

        if not started_at:
            continue

        stored_seconds = intval(session.get("duration_minutes")) * 60
        next_started_at = session.get("_next_started_at_023r")
        end_for_calc = ended_at or next_started_at or now_value
        if stored_seconds > 0 and not ended_at and not next_started_at and not is_active:
            end_for_calc = started_at + timedelta(seconds=stored_seconds)

        base_start = max(started_at, period_start_dt)
        base_end = min(end_for_calc, period_end_dt, now_value)
        if base_end <= base_start:
            continue

        matching_work = _prod_matching_work_intervals_023r(work_intervals, employee_id, telegram_user_id, employee_name)
        segments = [
            (max(base_start, work_start), min(base_end, work_end))
            for work_start, work_end in matching_work
            if min(base_end, work_end) > max(base_start, work_start)
        ]
        if not segments and not matching_work:
            segments = [(base_start, base_end)]

        effective_seconds = 0
        for segment_start, segment_end in segments:
            effective_seconds += await _prod_effective_seconds(
                db,
                company_id,
                employee_id,
                telegram_user_id,
                employee_name,
                segment_start,
                segment_end,
            )

        if effective_seconds <= 0:
            continue

        total_effective_seconds += effective_seconds

        # El bot marca una referencia por nombre y no solicita talla al iniciar
        # o cambiar. Por eso el tiempo debe agruparse a nivel de referencia,
        # mientras las cantidades cerradas sí permanecen separadas por talla.
        ref_key = _prod_reference_time_key(reference_name)
        op_key = _prod_operator_key(employee_id, employee_name, telegram_user_id, ref_key)

        ref_item = by_reference.setdefault(ref_key, {
            "reference_key": ref_key,
            "reference_id": "",
            "reference_name": reference_name,
            "size": "",
            "reference_scope": "name",
            "source_reference_ids": set(),
            "operators": set(),
            "operators_count": 0,
            "sessions_count": 0,
            "active_sessions": 0,
            "total_effective_seconds": 0,
            "total_effective_minutes": 0.0,
            "total_effective_label": "00:00:00",
            "finished_quantity_period": closure_period.get(ref_key, 0),
            "finished_quantity_all_time": closure_all.get(ref_key, 0),
            "seconds_per_unit_period": None,
            "seconds_per_unit_all_time": None,
        })

        operator_identity = employee_id or telegram_user_id or employee_name
        if reference_id:
            ref_item["source_reference_ids"].add(reference_id)
        ref_item["operators"].add(operator_identity)
        ref_item["sessions_count"] += 1
        ref_item["active_sessions"] += 1 if is_active else 0
        ref_item["total_effective_seconds"] += effective_seconds

        op_item = by_operator_reference.setdefault(op_key, {
            "operator_key": op_key,
            "employee_id": employee_id,
            "employee_name": employee_name,
            "telegram_user_id": telegram_user_id,
            "reference_key": ref_key,
            "reference_id": "",
            "reference_name": reference_name,
            "size": "",
            "reference_scope": "name",
            "source_reference_ids": set(),
            "sessions_count": 0,
            "active_sessions": 0,
            "effective_seconds": 0,
            "effective_minutes": 0.0,
            "effective_label": "00:00:00",
            "finished_quantity_period": closure_period.get(op_key, 0),
            "finished_quantity_all_time": closure_all.get(op_key, 0),
            "seconds_per_unit_period": None,
            "seconds_per_unit_all_time": None,
            "is_active": False,
        })

        if reference_id:
            op_item["source_reference_ids"].add(reference_id)
        op_item["sessions_count"] += 1
        op_item["active_sessions"] += 1 if is_active else 0
        op_item["effective_seconds"] += effective_seconds
        op_item["is_active"] = bool(op_item["is_active"] or is_active)

    raw_effective_seconds = total_effective_seconds
    payroll_cap_applied, capped_total = _prod_cap_operator_reference_seconds_023r(
        by_operator_reference,
        payroll_cap_data.get("caps") if isinstance(payroll_cap_data.get("caps"), dict) else {},
    )
    if payroll_cap_applied:
        total_effective_seconds = capped_total
        for item in by_reference.values():
            item["raw_total_effective_seconds"] = item["total_effective_seconds"]
            item["total_effective_seconds"] = 0
        for op_item in by_operator_reference.values():
            ref_item = by_reference.get(op_item.get("reference_key"))
            if ref_item:
                ref_item["total_effective_seconds"] += int(op_item.get("effective_seconds") or 0)

    for item in by_reference.values():
        item["source_reference_ids"] = sorted(item.get("source_reference_ids") or set())
        item["operators_count"] = len(item.pop("operators", set()))
        item["total_effective_minutes"] = round(item["total_effective_seconds"] / 60, 2)
        item["total_effective_label"] = _prod_format_seconds(item["total_effective_seconds"])

        if item["finished_quantity_period"] > 0:
            item["seconds_per_unit_period"] = round(item["total_effective_seconds"] / item["finished_quantity_period"], 2)

        if item["finished_quantity_all_time"] > 0:
            item["seconds_per_unit_all_time"] = round(item["total_effective_seconds"] / item["finished_quantity_all_time"], 2)

    for item in by_operator_reference.values():
        item["source_reference_ids"] = sorted(item.get("source_reference_ids") or set())
        item["effective_minutes"] = round(item["effective_seconds"] / 60, 2)
        item["effective_label"] = _prod_format_seconds(item["effective_seconds"])

        if item["finished_quantity_period"] > 0:
            item["seconds_per_unit_period"] = round(item["effective_seconds"] / item["finished_quantity_period"], 2)

        if item["finished_quantity_all_time"] > 0:
            item["seconds_per_unit_all_time"] = round(item["effective_seconds"] / item["finished_quantity_all_time"], 2)

    time_by_reference = sorted(
        by_reference.values(),
        key=lambda x: x["total_effective_seconds"],
        reverse=True,
    )

    time_by_operator_reference = sorted(
        by_operator_reference.values(),
        key=lambda x: x["effective_seconds"],
        reverse=True,
    )

    return {
        "active_sessions": active_sessions,
        "total_sessions_period": len(sessions),
        "raw_sessions_found": len(sessions),
        "query_strategy": query_strategy,
        "total_effective_seconds_period": total_effective_seconds,
        "total_effective_label_period": _prod_format_seconds(total_effective_seconds),
        "total_minutes_period": round(total_effective_seconds / 60, 2),
        "raw_effective_seconds_period": raw_effective_seconds,
        "raw_effective_label_period": _prod_format_seconds(raw_effective_seconds),
        "payroll_cap_applied": payroll_cap_applied,
        "payroll_cap_seconds_period": int(payroll_cap_data.get("total_seconds") or 0),
        "payroll_cap_label_period": _prod_format_seconds(int(payroll_cap_data.get("total_seconds") or 0)),
        "time_rule": "023R_reference_time_clipped_to_worked_sessions_and_payroll_cap",
        "by_reference": [
            {
                "reference_name": item["reference_name"],
                "size": item["size"],
                "minutes": item["total_effective_minutes"],
                "sessions": item["sessions_count"],
                "operators_count": item["operators_count"],
                "effective_seconds": item["total_effective_seconds"],
                "effective_label": item["total_effective_label"],
            }
            for item in time_by_reference[:20]
        ],
        "time_by_reference": time_by_reference[:100],
        "time_by_operator_reference": time_by_operator_reference[:200],
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
            "effective_seconds_period": sessions.get("total_effective_seconds_period", 0),
            "effective_label_period": sessions.get("total_effective_label_period", "00:00:00"),
            "effective_seconds_period": sessions.get("total_effective_seconds_period", 0),
            "effective_label_period": sessions.get("total_effective_label_period", "00:00:00"),
        },
        "references": refs,
        "closures_period": closures_period,
        "closures_display": graph_rows,
        "closures_all_time": closures_all,
        "by_employee_period": sorted(by_employee_map.values(), key=lambda x: x["finished_quantity"], reverse=True),
        "by_reference_period": sorted(by_reference_period.values(), key=lambda x: x["finished_quantity"], reverse=True),
        "graph_source": "period" if closures_period else "all_time_fallback",
        "sessions": sessions,
        "time_by_reference": sessions.get("time_by_reference", []),
        "time_by_operator_reference": sessions.get("time_by_operator_reference", []),
        "time_rule": "pause_excluded_from_shift_and_reference",
    }


@router.get("/companies/{company_id}/summary")
async def production_summary(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    view: str | None = Query("active"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    start, end = date_range(date_from, date_to, preset)
    modules = await active_modules(db, company_id)
    refs = await reference_rows(db, company_id, view or "active")
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




@router.post("/companies/{company_id}/references/{reference_id}/archive")
async def production_archive_reference(
    company_id: str,
    reference_id: str,
    payload: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    reason = clean(payload.get("reason")) or "Archivado desde Producción"
    archived_by = clean(payload.get("archived_by")) or "client_panel"
    preset = clean(payload.get("preset")) or "7d"
    date_from = clean(payload.get("date_from")) or None
    date_to = clean(payload.get("date_to")) or None

    ref_rows = await safe_rows(
        db,
        """
        SELECT to_jsonb(pr) AS row
        FROM product_references pr
        WHERE pr.company_id::text = :company_id
          AND pr.id::text = :reference_id
        LIMIT 1
        """,
        {
            "company_id": company_id,
            "reference_id": reference_id,
        },
    )

    if not ref_rows or not isinstance(ref_rows[0].get("row"), dict):
        raise HTTPException(status_code=404, detail="Referencia no encontrada.")

    ref = ref_rows[0]["row"]
    reference_name = clean(ref.get("name"))
    size = clean(ref.get("size"))

    snapshot_id = str(uuid.uuid4())

    # Snapshot antes de archivar. Usa view=all para no perder contexto.
    snapshot_payload = await production_summary(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        view="all",
        db=db,
    )

    await db.execute(
        text("""
            INSERT INTO production_archive_snapshots (
                id,
                company_id,
                reference_id,
                reference_name,
                size,
                snapshot_type,
                date_from,
                date_to,
                payload,
                created_at
            )
            VALUES (
                :id,
                :company_id,
                :reference_id,
                :reference_name,
                :size,
                'reference_archive',
                CAST(:date_from AS date),
                CAST(:date_to AS date),
                CAST(:payload AS jsonb),
                now()
            )
        """),
        {
            "id": snapshot_id,
            "company_id": company_id,
            "reference_id": reference_id,
            "reference_name": reference_name,
            "size": size,
            "date_from": snapshot_payload.get("date_from"),
            "date_to": snapshot_payload.get("date_to"),
            "payload": json.dumps(snapshot_payload, default=str),
        },
    )

    # Cierra sesiones activas de esta referencia para que no sigan corriendo.
    await db.execute(
        text("""
            UPDATE reference_work_sessions
            SET
                ended_at = COALESCE(ended_at, now()),
                status = CASE
                    WHEN lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL THEN 'closed'
                    ELSE status
                END,
                duration_minutes = CASE
                    WHEN ended_at IS NULL THEN GREATEST(
                        COALESCE(duration_minutes, 0),
                        CEIL(EXTRACT(EPOCH FROM (now() - started_at)) / 60.0)::int
                    )
                    ELSE COALESCE(duration_minutes, 0)
                END,
                updated_at = now()
            WHERE company_id::text = :company_id
              AND (
                    reference_id::text = :reference_id
                    OR lower(COALESCE(reference_name, '')) = lower(:reference_name)
              )
              AND (lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL)
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
            "reference_name": reference_name,
        },
    )

    # Archivar = ocultar del panel operativo y apagar del bot.
    await db.execute(
        text("""
            UPDATE product_references
            SET
                bot_active = false,
                archived_at = now(),
                archived_by = :archived_by,
                archive_reason = :reason,
                archived_snapshot_id = :snapshot_id,
                updated_at = now()
            WHERE company_id::text = :company_id
              AND id::text = :reference_id
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
            "archived_by": archived_by,
            "reason": reason,
            "snapshot_id": snapshot_id,
        },
    )

    await db.commit()

    return {
        "ok": True,
        "action": "reference_archived",
        "company_id": company_id,
        "reference_id": reference_id,
        "reference_name": reference_name,
        "size": size,
        "snapshot_id": snapshot_id,
        "panel_visible": False,
        "bot_active": False,
        "message": "Referencia archivada. No se borró información; quedó disponible en histórico/reportes.",
    }


@router.post("/companies/{company_id}/references/{reference_id}/restore")
async def production_restore_reference(
    company_id: str,
    reference_id: str,
    payload: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    bot_active = bool(payload.get("bot_active", True))

    result = await db.execute(
        text("""
            UPDATE product_references
            SET
                archived_at = NULL,
                archived_by = NULL,
                archive_reason = NULL,
                archived_snapshot_id = NULL,
                bot_active = :bot_active,
                updated_at = now()
            WHERE company_id::text = :company_id
              AND id::text = :reference_id
            RETURNING id, name, size, bot_active
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
            "bot_active": bot_active,
        },
    )

    row = result.mappings().first()
    if not row:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Referencia no encontrada.")

    await db.commit()

    return {
        "ok": True,
        "action": "reference_restored",
        "company_id": company_id,
        "reference_id": row["id"],
        "reference_name": row["name"],
        "size": row["size"],
        "bot_active": bool(row["bot_active"]),
        "panel_visible": True,
    }


@router.get("/companies/{company_id}/archive-snapshots")
async def production_archive_snapshots(
    company_id: str,
    limit: int = Query(100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    rows = await safe_rows(
        db,
        """
        SELECT
            id,
            company_id,
            reference_id,
            reference_name,
            size,
            snapshot_type,
            date_from::text AS date_from,
            date_to::text AS date_to,
            created_at::text AS created_at
        FROM production_archive_snapshots
        WHERE company_id::text = :company_id
        ORDER BY created_at DESC
        LIMIT :limit
        """,
        {
            "company_id": company_id,
            "limit": limit,
        },
    )

    return {
        "ok": True,
        "company_id": company_id,
        "items": rows,
    }

@router.get("/companies/{company_id}/export.csv")
async def production_export_csv(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    view: str | None = Query("active"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    data = await production_summary(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        view=view,
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
