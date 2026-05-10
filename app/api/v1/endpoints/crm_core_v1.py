from __future__ import annotations

import json

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

START_EVENTS = {"check_in", "entrada", "start_shift", "shift_start", "inicio_turno", "clock_in"}
PAUSE_START_EVENTS = {"break_start", "pause_start", "pause", "pausa", "break", "on_break"}
PAUSE_END_EVENTS = {"break_end", "pause_end", "resume", "return", "retorno", "reanudar", "clock_resume"}
END_EVENTS = {"check_out", "salida", "end_shift", "shift_end", "fin_turno", "clock_out"}

CARD_CATALOG = [
    {"code": "core_active", "label": "Activos", "module": "core"},
    {"code": "core_break", "label": "En pausa", "module": "core"},
    {"code": "core_out", "label": "Fuera", "module": "core"},
    {"code": "production_reference", "label": "Con referencia", "module": "production"},
    {"code": "production_on", "label": "Producción", "module": "production"},
    {"code": "gps_on", "label": "GPS", "module": "gps"},
    {"code": "materials_on", "label": "Materiales", "module": "materials"},
    {"code": "inventory_on", "label": "Inventario", "module": "inventory"},
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def intval(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Any) -> datetime | None:
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


def dt_text(value: datetime | None) -> str | None:
    if not value:
        return None

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def seconds_between(start: datetime | None, end: datetime | None) -> int:
    if not start or not end:
        return 0

    return max(int((end - start).total_seconds()), 0)


def overlap_seconds(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)

    if end <= start:
        return 0

    return int((end - start).total_seconds())


async def safe_rows(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        result = await db.execute(text(sql), params)
        return [dict(row) for row in result.mappings().all()]
    except Exception:
        await db.rollback()
        return []


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name})
    return bool(result.scalar())


async def table_column_types(db: AsyncSession, table_name: str) -> dict[str, str]:
    result = await db.execute(
        text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
        """),
        {"table_name": table_name},
    )

    return {str(row[0]): str(row[1]) for row in result.all()}


async def company_profile(db: AsyncSession, company_id: str) -> dict[str, Any]:
    if not await table_exists(db, "companies"):
        return {"id": company_id, "name": "Empresa", "slug": ""}

    cols = await table_column_types(db, "companies")
    name_expr = "COALESCE(name, 'Empresa')" if "name" in cols else "'Empresa'"
    slug_expr = "COALESCE(slug, '')" if "slug" in cols else "''"

    rows = await safe_rows(
        db,
        f"""
        SELECT id::text AS id, {name_expr} AS name, {slug_expr} AS slug
        FROM companies
        WHERE id::text = :company_id
        LIMIT 1
        """,
        {"company_id": company_id},
    )

    return rows[0] if rows else {"id": company_id, "name": "Empresa", "slug": ""}


async def active_modules(db: AsyncSession, company_id: str) -> set[str]:
    if not await table_exists(db, "company_modules") or not await table_exists(db, "modules"):
        return set()

    rows = await safe_rows(
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

    return {clean(row.get("code")).lower() for row in rows if clean(row.get("code"))}


async def ensure_card_storage(db: AsyncSession) -> None:
    await db.execute(
        text("""
            CREATE TABLE IF NOT EXISTS crm_card_preferences (
                company_id text NOT NULL,
                scope text NOT NULL DEFAULT 'crm',
                cards jsonb NOT NULL DEFAULT '[]'::jsonb,
                updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (company_id, scope)
            )
        """)
    )
    await db.commit()


def default_card_codes(modules: set[str]) -> list[str]:
    cards = ["core_active", "core_break", "core_out"]

    if {"production", "references"}.issubset(modules):
        cards = ["core_active", "core_break", "production_reference", "production_on"]

    if "gps" in modules and "gps_on" not in cards:
        cards.append("gps_on")

    if "materials" in modules and "materials_on" not in cards:
        cards.append("materials_on")

    if "inventory" in modules and "inventory_on" not in cards:
        cards.append("inventory_on")

    return cards[:6]


def card_available(card: dict[str, Any], modules: set[str]) -> bool:
    module = clean(card.get("module")).lower()

    if module == "core":
        return True

    if module == "production":
        return {"production", "references"}.issubset(modules)

    return module in modules


async def selected_card_codes(db: AsyncSession, company_id: str, modules: set[str]) -> list[str]:
    await ensure_card_storage(db)

    rows = await safe_rows(
        db,
        """
        SELECT cards
        FROM crm_card_preferences
        WHERE company_id = :company_id
          AND scope = 'crm'
        LIMIT 1
        """,
        {"company_id": company_id},
    )

    if not rows:
        return default_card_codes(modules)

    raw = rows[0].get("cards")

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []

    allowed = {
        card["code"]
        for card in CARD_CATALOG
        if card_available(card, modules)
    }

    selected = []
    for item in raw or []:
        code = clean(item)
        if code in allowed and code not in selected:
            selected.append(code)

    return selected[:6] or default_card_codes(modules)


def build_cards(summary: dict[str, Any], modules: set[str], selected: list[str]) -> dict[str, Any]:
    values = {
        "core_active": summary.get("active_now", 0),
        "core_break": summary.get("on_break", 0),
        "core_out": summary.get("out", 0),
        "production_reference": summary.get("with_reference", 0),
        "production_on": "ON" if summary.get("production_adapter") else "OFF",
        "gps_on": "ON" if summary.get("gps_adapter") else "OFF",
        "materials_on": "ON" if summary.get("materials_adapter") else "OFF",
        "inventory_on": "ON" if summary.get("inventory_adapter") else "OFF",
    }

    catalog = [
        {
            **card,
            "available": card_available(card, modules),
            "selected": card["code"] in selected,
            "value": values.get(card["code"], 0),
        }
        for card in CARD_CATALOG
    ]

    visible = [
        {
            "code": item["code"],
            "label": item["label"],
            "value": item["value"],
            "module": item["module"],
        }
        for item in catalog
        if item["available"] and item["selected"]
    ]

    return {
        "catalog": catalog,
        "selected": selected,
        "visible": visible[:6],
    }


async def employees_snapshot(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    if not await table_exists(db, "employees"):
        return []

    cols = await table_column_types(db, "employees")

    if "full_name" in cols:
        name_expr = "COALESCE(e.full_name, '')"
    elif "name" in cols:
        name_expr = "COALESCE(e.name, '')"
    else:
        name_expr = "'Empleado'"

    role_expr = "COALESCE(e.role, '')" if "role" in cols else "''"
    telegram_expr = "COALESCE(e.telegram_user_id::text, '')" if "telegram_user_id" in cols else "''"

    status_filter = ""
    if "status" in cols:
        status_filter = "AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')"

    status_join = ""
    status_fields = """
        'sin_turno' AS work_status,
        NULL::text AS status_started_at,
        '' AS last_event_type
    """

    if await table_exists(db, "workforce_attendance_status"):
        status_cols = await table_column_types(db, "workforce_attendance_status")

        if {"company_id", "employee_id", "status"}.issubset(set(status_cols)):
            last_event_at_expr = "s.last_event_at::text" if "last_event_at" in status_cols else "NULL::text"
            last_event_type_expr = "COALESCE(s.last_event_type, '')" if "last_event_type" in status_cols else "''"

            status_join = """
                LEFT JOIN workforce_attendance_status s
                  ON s.company_id = e.company_id
                 AND s.employee_id = e.id
            """

            status_fields = f"""
                COALESCE(s.status, 'sin_turno') AS work_status,
                {last_event_at_expr} AS status_started_at,
                {last_event_type_expr} AS last_event_type
            """

    return await safe_rows(
        db,
        f"""
        SELECT
            e.id::text AS employee_id,
            {name_expr} AS employee_name,
            {role_expr} AS employee_role,
            {telegram_expr} AS telegram_user_id,
            {status_fields}
        FROM employees e
        {status_join}
        WHERE e.company_id::text = :company_id
        {status_filter}
        ORDER BY employee_name ASC
        """,
        {"company_id": company_id},
    )


def normalize_status(value: Any) -> str:
    raw = clean(value).lower()

    if raw in {"working", "trabajando", "activo"}:
        return "working"

    if raw in {"on_break", "break", "pause", "pausa", "en_pausa"}:
        return "on_break"

    if raw in {"checked_out", "finished", "turno_finalizado", "salida"}:
        return "checked_out"

    return "sin_turno"


def status_label(status: str) -> str:
    normalized = normalize_status(status)

    if normalized == "working":
        return "Activo"

    if normalized == "on_break":
        return "En pausa"

    return "Fuera de turno"


async def attendance_events(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    telegram_user_id: str,
    employee_name: str,
) -> list[dict[str, Any]]:
    if not await table_exists(db, "workforce_attendance_events"):
        return []

    cols = await table_column_types(db, "workforce_attendance_events")

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

    match_parts: list[str] = []

    if "employee_id" in cols:
        match_parts.append("employee_id::text = :employee_id")

    if "telegram_user_id" in cols:
        match_parts.append("(:telegram_user_id <> '' AND telegram_user_id::text = :telegram_user_id)")

    if "employee_name" in cols:
        match_parts.append("(:employee_name <> '' AND lower(COALESCE(employee_name, '')) = lower(:employee_name))")

    if cols.get("payload_json") in {"json", "jsonb"}:
        match_parts.append("(:telegram_user_id <> '' AND payload_json->>'telegram_user_id' = :telegram_user_id)")

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
        ORDER BY {at_expr} ASC
        LIMIT 1000
        """,
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "telegram_user_id": telegram_user_id,
            "employee_name": employee_name,
        },
    )

    parsed = []

    for row in rows:
        event_type = clean(row.get("event_type")).lower()
        event_at = parse_dt(row.get("event_at"))

        if event_type and event_at:
            parsed.append({"event_type": event_type, "event_at": event_at})

    return parsed


def latest_shift_start_from_events(events: list[dict[str, Any]]) -> datetime | None:
    active_start = None

    for event in events:
        event_type = clean(event.get("event_type")).lower()
        event_at = event.get("event_at")

        if event_type in START_EVENTS:
            active_start = event_at
            continue

        if event_type in END_EVENTS:
            active_start = None
            continue

    return active_start


def pause_intervals_from_events(
    events: list[dict[str, Any]],
    *,
    shift_start: datetime | None,
    current_status: str,
    status_started_at: datetime | None,
    now_value: datetime,
) -> tuple[list[tuple[datetime, datetime]], datetime | None]:
    if not shift_start:
        return [], None

    intervals: list[tuple[datetime, datetime]] = []
    open_pause = None

    for event in events:
        event_type = clean(event.get("event_type")).lower()
        event_at = event.get("event_at")

        if not event_at or event_at < shift_start:
            continue

        if event_type in END_EVENTS:
            open_pause = None
            break

        if event_type in PAUSE_START_EVENTS:
            if open_pause is None:
                open_pause = event_at
            continue

        if event_type in PAUSE_END_EVENTS:
            if open_pause and event_at > open_pause:
                intervals.append((open_pause, event_at))
                open_pause = None
            continue

    current_pause_started = None

    if current_status == "on_break":
        current_pause_started = open_pause or status_started_at or now_value

        if current_pause_started < shift_start:
            current_pause_started = shift_start

        if now_value > current_pause_started:
            intervals.append((current_pause_started, now_value))

    return intervals, current_pause_started


def effective_seconds_for_interval(
    start: datetime | None,
    end: datetime | None,
    pause_intervals: list[tuple[datetime, datetime]],
) -> int:
    if not start or not end:
        return 0

    raw = seconds_between(start, end)
    paused = sum(overlap_seconds(start, end, p_start, p_end) for p_start, p_end in pause_intervals)

    return max(raw - paused, 0)


async def reference_sessions_for_employee(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    employee_name: str,
    telegram_user_id: str,
    shift_start: datetime | None,
) -> list[dict[str, Any]]:
    if not await table_exists(db, "reference_work_sessions"):
        return []

    rows = await safe_rows(
        db,
        """
        SELECT
            id,
            COALESCE(employee_id, '') AS employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            started_at::text AS started_at,
            ended_at::text AS ended_at,
            COALESCE(status, '') AS status,
            GREATEST(COALESCE(duration_minutes, 0) * 60, 0)::int AS stored_seconds
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND (
                employee_id::text = :employee_id
                OR (:telegram_user_id <> '' AND telegram_user_id::text = :telegram_user_id)
                OR (:employee_name <> '' AND lower(COALESCE(employee_name, '')) = lower(:employee_name))
          )
          AND (
                lower(COALESCE(status, '')) = 'active'
                OR ended_at IS NULL
                OR :shift_start IS NULL
                OR started_at >= CAST(:shift_start AS timestamptz)
          )
        ORDER BY started_at ASC
        LIMIT 80
        """,
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "employee_name": employee_name,
            "telegram_user_id": telegram_user_id,
            "shift_start": dt_text(shift_start),
        },
    )

    output = []

    for row in rows:
        started_at = parse_dt(row.get("started_at"))
        ended_at = parse_dt(row.get("ended_at"))
        status = clean(row.get("status")).lower()
        is_active = status == "active" or ended_at is None

        output.append({
            "session_id": row.get("id"),
            "employee_id": clean(row.get("employee_id")),
            "employee_name": clean(row.get("employee_name")),
            "telegram_user_id": clean(row.get("telegram_user_id")),
            "reference_id": clean(row.get("reference_id")),
            "reference_name": clean(row.get("reference_name")),
            "started_at": dt_text(started_at),
            "ended_at": dt_text(ended_at),
            "status": status,
            "is_active": is_active,
            "stored_seconds": intval(row.get("stored_seconds")),
        })

    return output


def normalize_reference_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []

    for row in rows:
        started_at = parse_dt(row.get("started_at"))
        ended_at = parse_dt(row.get("ended_at"))
        status = clean(row.get("status")).lower()
        is_active = status == "active" or ended_at is None

        output.append({
            "session_id": row.get("id") or row.get("session_id"),
            "employee_id": clean(row.get("employee_id")),
            "employee_name": clean(row.get("employee_name")),
            "telegram_user_id": clean(row.get("telegram_user_id")),
            "reference_id": clean(row.get("reference_id")),
            "reference_name": clean(row.get("reference_name")),
            "started_at": dt_text(started_at),
            "ended_at": dt_text(ended_at),
            "status": status,
            "is_active": is_active,
            "stored_seconds": intval(row.get("stored_seconds")),
        })

    return output


async def active_reference_sessions_company(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    if not await table_exists(db, "reference_work_sessions"):
        return []

    rows = await safe_rows(
        db,
        """
        SELECT
            id,
            COALESCE(employee_id, '') AS employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            started_at::text AS started_at,
            ended_at::text AS ended_at,
            COALESCE(status, '') AS status,
            GREATEST(COALESCE(duration_minutes, 0) * 60, 0)::int AS stored_seconds
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND (lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL)
        ORDER BY started_at DESC
        LIMIT 100
        """,
        {"company_id": company_id},
    )

    return normalize_reference_rows(rows)


def session_matches_employee(session: dict[str, Any], employee_id: str, employee_name: str, telegram_user_id: str) -> bool:
    if clean(session.get("employee_id")) == employee_id:
        return True

    if telegram_user_id and clean(session.get("telegram_user_id")) == telegram_user_id:
        return True

    if employee_name and clean(session.get("employee_name")).lower() == employee_name.lower():
        return True

    return False


def earliest_active_reference_start(sessions: list[dict[str, Any]]) -> datetime | None:
    starts = [
        parse_dt(item.get("started_at"))
        for item in sessions
        if item.get("is_active") and parse_dt(item.get("started_at"))
    ]

    starts = [item for item in starts if item]

    return min(starts) if starts else None


def production_adapter(
    modules: set[str],
    employee_status: str,
    sessions: list[dict[str, Any]],
    pause_intervals: list[tuple[datetime, datetime]],
    now_value: datetime,
) -> dict[str, Any] | None:
    if not {"production", "references"}.issubset(modules):
        return None

    items = []

    for session in sessions:
        started_at = parse_dt(session.get("started_at"))
        ended_at = parse_dt(session.get("ended_at"))
        is_active = bool(session.get("is_active"))

        end_for_calc = ended_at or now_value
        effective_seconds = effective_seconds_for_interval(started_at, end_for_calc, pause_intervals)
        running = is_active and employee_status == "working"

        items.append({
            **session,
            "effective_seconds": effective_seconds,
            "running": running,
            "label": "Referencia activa · corriendo" if running else (
                "Referencia activa · pausada" if is_active else "Referencia cerrada"
            ),
        })

    if not items:
        return None

    return {
        "code": "production_references",
        "title": "Producción del turno",
        "enabled": True,
        "items": items,
    }




@router.get("/companies/{company_id}/cards")
async def get_crm_cards(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    modules = await active_modules(db, company_id)
    selected = await selected_card_codes(db, company_id, modules)

    empty_summary = {
        "active_now": 0,
        "on_break": 0,
        "out": 0,
        "with_reference": 0,
        "production_adapter": {"production", "references"}.issubset(modules),
        "gps_adapter": "gps" in modules,
        "materials_adapter": "materials" in modules,
        "inventory_adapter": "inventory" in modules,
    }

    return {
        "ok": True,
        "company_id": company_id,
        "cards": build_cards(empty_summary, modules, selected),
    }


@router.put("/companies/{company_id}/cards")
async def put_crm_cards(
    company_id: str,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_card_storage(db)

    modules = await active_modules(db, company_id)

    allowed = {
        card["code"]
        for card in CARD_CATALOG
        if card_available(card, modules)
    }

    raw_cards = payload.get("cards", [])
    if not isinstance(raw_cards, list):
        raw_cards = []

    selected = []
    for item in raw_cards:
        code = clean(item)
        if code in allowed and code not in selected:
            selected.append(code)

    selected = selected[:6] or default_card_codes(modules)

    await db.execute(
        text("""
            INSERT INTO crm_card_preferences (company_id, scope, cards, updated_at)
            VALUES (:company_id, 'crm', CAST(:cards AS jsonb), now())
            ON CONFLICT (company_id, scope)
            DO UPDATE SET cards = EXCLUDED.cards, updated_at = now()
        """),
        {
            "company_id": company_id,
            "cards": json.dumps(selected),
        },
    )
    await db.commit()

    return {
        "ok": True,
        "company_id": company_id,
        "selected": selected,
    }

@router.get("/companies/{company_id}/snapshot")
async def crm_core_snapshot(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    now_value = now_utc()
    company = await company_profile(db, company_id)
    modules = await active_modules(db, company_id)
    employees = await employees_snapshot(db, company_id)
    company_active_sessions = await active_reference_sessions_company(db, company_id)

    active_people = [
        employee for employee in employees
        if normalize_status(employee.get("work_status")) in {"working", "on_break"}
    ]

    rows = []
    consumed_session_ids: set[str] = set()

    for employee in employees:
        employee_id = clean(employee.get("employee_id"))
        employee_name = clean(employee.get("employee_name")) or "Empleado"
        telegram_user_id = clean(employee.get("telegram_user_id"))
        employee_status = normalize_status(employee.get("work_status"))
        status_started_at = parse_dt(employee.get("status_started_at"))

        events = await attendance_events(
            db,
            company_id,
            employee_id,
            telegram_user_id,
            employee_name,
        )

        preliminary_sessions = await reference_sessions_for_employee(
            db,
            company_id,
            employee_id,
            employee_name,
            telegram_user_id,
            None,
        )

        if not preliminary_sessions and employee_status in {"working", "on_break"}:
            preliminary_sessions = [
                session for session in company_active_sessions
                if session_matches_employee(session, employee_id, employee_name, telegram_user_id)
            ]

        if not preliminary_sessions and employee_status in {"working", "on_break"} and len(active_people) == 1:
            preliminary_sessions = [
                session for session in company_active_sessions
                if clean(session.get("session_id")) not in consumed_session_ids
            ]

        for session in preliminary_sessions:
            sid = clean(session.get("session_id"))
            if sid:
                consumed_session_ids.add(sid)

        shift_start = latest_shift_start_from_events(events)

        ref_start = earliest_active_reference_start(preliminary_sessions)

        if employee_status in {"working", "on_break"}:
            if ref_start and (shift_start is None or ref_start < shift_start):
                shift_start = ref_start

            if shift_start is None:
                shift_start = status_started_at
        else:
            shift_start = None

        sessions = await reference_sessions_for_employee(
            db,
            company_id,
            employee_id,
            employee_name,
            telegram_user_id,
            shift_start,
        )

        if not sessions and preliminary_sessions:
            sessions = preliminary_sessions

        pause_intervals, current_pause_started = pause_intervals_from_events(
            events,
            shift_start=shift_start,
            current_status=employee_status,
            status_started_at=status_started_at,
            now_value=now_value,
        )

        shift_effective_seconds = (
            effective_seconds_for_interval(shift_start, now_value, pause_intervals)
            if employee_status in {"working", "on_break"}
            else 0
        )

        pause_accumulated_seconds = sum(seconds_between(start, end) for start, end in pause_intervals)
        current_pause_seconds = seconds_between(current_pause_started, now_value) if current_pause_started else 0

        adapters = []

        production = production_adapter(
            modules,
            employee_status,
            sessions,
            pause_intervals,
            now_value,
        )

        if production:
            adapters.append(production)

        if "gps" in modules:
            adapters.append({
                "code": "gps",
                "title": "GPS",
                "enabled": True,
                "items": [],
                "placeholder": "GPS activo para ubicación, rutas y perímetros.",
            })

        if "materials" in modules:
            adapters.append({
                "code": "materials",
                "title": "Materiales",
                "enabled": True,
                "items": [],
                "placeholder": "Materiales activo para solicitudes, entregas y devoluciones.",
            })

        if "inventory" in modules:
            adapters.append({
                "code": "inventory",
                "title": "Inventario",
                "enabled": True,
                "items": [],
                "placeholder": "Inventario activo para stock y disponibilidad.",
            })

        rows.append({
            "employee_id": employee_id,
            "employee_name": employee_name,
            "employee_role": clean(employee.get("employee_role")),
            "telegram_user_id": telegram_user_id,
            "core": {
                "status": employee_status,
                "status_label": status_label(employee_status),
                "last_event_type": clean(employee.get("last_event_type")),
                "shift_started_at": dt_text(shift_start),
                "status_started_at": dt_text(status_started_at),
                "pause_started_at": dt_text(current_pause_started),
                "shift_effective_seconds": shift_effective_seconds,
                "pause_accumulated_seconds": pause_accumulated_seconds,
                "current_pause_seconds": current_pause_seconds,
                "shift_running": employee_status == "working",
                "pause_running": employee_status == "on_break",
                "time_rule": "pause_excluded_from_shift_payroll_production",
            },
            "adapters": adapters,
        })

    production_enabled = {"production", "references"}.issubset(modules)

    summary = {
        "employees_total": len(rows),
        "active_now": sum(1 for row in rows if row["core"]["status"] == "working"),
        "on_break": sum(1 for row in rows if row["core"]["status"] == "on_break"),
        "out": sum(1 for row in rows if row["core"]["status"] not in {"working", "on_break"}),
        "production_adapter": production_enabled,
        "gps_adapter": "gps" in modules,
        "materials_adapter": "materials" in modules,
        "inventory_adapter": "inventory" in modules,
        "with_reference": sum(
            1
            for row in rows
            for adapter in row["adapters"]
            if adapter.get("code") == "production_references"
            for item in adapter.get("items", [])
            if item.get("is_active")
        ) if production_enabled else 0,
    }

    selected = await selected_card_codes(db, company_id, modules)
    cards = build_cards(summary, modules, selected)

    return {
        "ok": True,
        "company_id": company_id,
        "company": company,
        "language": "es",
        "module": "crm",
        "mode": "crm_core_with_adapters",
        "server_time": dt_text(now_value),
        "active_modules": sorted(modules),
        "summary": summary,
        "cards": cards,
        "employees": rows,
    }
