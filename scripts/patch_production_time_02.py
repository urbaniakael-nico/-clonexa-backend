from pathlib import Path

path = Path("app/api/v1/endpoints/production_v1.py")
src = path.read_text(encoding="utf-8-sig")

if "from datetime import datetime, timezone" not in src:
    src = src.replace(
        "from __future__ import annotations\n",
        "from __future__ import annotations\n\nfrom datetime import datetime, timezone\n",
        1,
    )

helper = r'''

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
          AND closed_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
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
            op_key = _prod_operator_key(
                row.get("employee_id"),
                row.get("employee_name"),
                row.get("telegram_user_id"),
                ref_key,
            )

            qty = intval(row.get("quantity_finished"))
            ref_out[ref_key] = ref_out.get(ref_key, 0) + qty
            op_out[op_key] = op_out.get(op_key, 0) + qty

        merged = {}
        merged.update(ref_out)
        merged.update(op_out)
        return merged

    return build(period_rows), build(all_rows)
'''

if "PRODUCTION_TIME_02_DIRECT_SESSIONS" not in src:
    marker = "\n\nasync def sessions_summary("
    if marker not in src:
        raise SystemExit("No encontré sessions_summary")
    src = src.replace(marker, helper + marker, 1)

start = src.find("async def sessions_summary(")
end = src.find("\n\ndef build_summary(", start)

if start == -1 or end == -1:
    raise SystemExit("No pude ubicar sessions_summary")

new_sessions = r'''async def sessions_summary(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any]:
    now_value = datetime.now(timezone.utc)

    active_sessions = intval(await safe_scalar(
        db,
        """
        SELECT count(*)
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND (lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL)
        """,
        {"company_id": company_id},
    ))

    # Consulta directa y segura. No depende de JOIN con product_references.
    sessions = await safe_rows(
        db,
        """
        SELECT
            id,
            COALESCE(employee_id, '') AS employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, 'Sin referencia') AS reference_name,
            '' AS size,
            started_at::text AS started_at,
            ended_at::text AS ended_at,
            COALESCE(status, '') AS status,
            GREATEST(COALESCE(duration_minutes, 0) * 60, 0)::int AS stored_seconds
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND (
                started_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
                OR (ended_at IS NOT NULL AND ended_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date))
                OR lower(COALESCE(status, '')) = 'active'
                OR ended_at IS NULL
          )
        ORDER BY started_at ASC
        LIMIT 2000
        """,
        {
            "company_id": company_id,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
        },
    )

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
        end_for_calc = ended_at or now_value

        effective_seconds = await _prod_effective_seconds(
            db,
            company_id,
            employee_id,
            telegram_user_id,
            employee_name,
            started_at,
            end_for_calc,
        )

        if effective_seconds <= 0 and intval(session.get("stored_seconds")) > 0:
            effective_seconds = intval(session.get("stored_seconds"))

        total_effective_seconds += effective_seconds

        ref_key = _prod_ref_key(reference_id, reference_name, size)
        op_key = _prod_operator_key(employee_id, employee_name, telegram_user_id, ref_key)

        ref_item = by_reference.setdefault(ref_key, {
            "reference_key": ref_key,
            "reference_id": reference_id,
            "reference_name": reference_name,
            "size": size,
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
            "reference_id": reference_id,
            "reference_name": reference_name,
            "size": size,
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

        op_item["sessions_count"] += 1
        op_item["active_sessions"] += 1 if is_active else 0
        op_item["effective_seconds"] += effective_seconds
        op_item["is_active"] = bool(op_item["is_active"] or is_active)

    for item in by_reference.values():
        item["operators_count"] = len(item.pop("operators", set()))
        item["total_effective_minutes"] = round(item["total_effective_seconds"] / 60, 2)
        item["total_effective_label"] = _prod_format_seconds(item["total_effective_seconds"])

        if item["finished_quantity_period"] > 0:
            item["seconds_per_unit_period"] = round(item["total_effective_seconds"] / item["finished_quantity_period"], 2)

        if item["finished_quantity_all_time"] > 0:
            item["seconds_per_unit_all_time"] = round(item["total_effective_seconds"] / item["finished_quantity_all_time"], 2)

    for item in by_operator_reference.values():
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
        "total_effective_seconds_period": total_effective_seconds,
        "total_effective_label_period": _prod_format_seconds(total_effective_seconds),
        "total_minutes_period": round(total_effective_seconds / 60, 2),
        "time_rule": "pause_excluded_from_shift_and_reference",
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
'''

src = src[:start] + new_sessions + src[end:]

if '"effective_seconds_period": sessions.get("total_effective_seconds_period", 0)' not in src:
    src = src.replace(
        '''            "minutes_period": sessions.get("total_minutes_period", 0),''',
        '''            "minutes_period": sessions.get("total_minutes_period", 0),
            "effective_seconds_period": sessions.get("total_effective_seconds_period", 0),
            "effective_label_period": sessions.get("total_effective_label_period", "00:00:00"),''',
        1,
    )

if '"time_by_reference": sessions.get("time_by_reference", [])' not in src:
    src = src.replace(
        '''        "sessions": sessions,
        "time_rule": "pause_excluded_from_shift_and_reference",''',
        '''        "sessions": sessions,
        "time_by_reference": sessions.get("time_by_reference", []),
        "time_by_operator_reference": sessions.get("time_by_operator_reference", []),
        "time_rule": "pause_excluded_from_shift_and_reference",''',
        1,
    )

path.write_text(src, encoding="utf-8")

print("PRODUCTION_TIME_02_OK")
