from pathlib import Path
import re

prod = Path("app/api/v1/endpoints/production_v1.py")
client = Path("app/web/client.js")

src = prod.read_text(encoding="utf-8-sig")

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
          AND (lower(COALESCE(status::text, '')) = 'active' OR ended_at IS NULL)
        """,
        {"company_id": company_id},
    ))

    # Lectura robusta: trae la fila completa como JSONB para no romper por columnas antiguas/nuevas.
    raw_rows = await safe_rows(
        db,
        """
        SELECT to_jsonb(s) AS row
        FROM reference_work_sessions s
        WHERE s.company_id::text = :company_id
          AND (
                s.started_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
                OR (s.ended_at IS NOT NULL AND s.ended_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date))
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
        },
    )

    query_strategy = "period_or_active_jsonb"

    # Fallback: si hay sesiones activas pero el filtro anterior no devolvió filas,
    # lee directo las sesiones activas. Esto protege Producción contra esquemas legacy.
    if not raw_rows and active_sessions > 0:
        raw_rows = await safe_rows(
            db,
            """
            SELECT to_jsonb(s) AS row
            FROM reference_work_sessions s
            WHERE s.company_id::text = :company_id
              AND (lower(COALESCE(s.status::text, '')) = 'active' OR s.ended_at IS NULL)
            ORDER BY s.started_at ASC
            LIMIT 2000
            """,
            {"company_id": company_id},
        )
        query_strategy = "active_jsonb_fallback"

    # Fallback final: si aun así viene vacío, trae últimas sesiones de la empresa.
    # No se usa para inventar datos; solo para que el dashboard pueda mostrar sesiones existentes.
    if not raw_rows and active_sessions > 0:
        raw_rows = await safe_rows(
            db,
            """
            SELECT to_jsonb(s) AS row
            FROM reference_work_sessions s
            WHERE s.company_id::text = :company_id
            ORDER BY COALESCE(s.updated_at, s.created_at, s.started_at) DESC
            LIMIT 2000
            """,
            {"company_id": company_id},
        )
        query_strategy = "company_recent_jsonb_fallback"

    sessions = []
    for wrapper in raw_rows:
        row = wrapper.get("row") if isinstance(wrapper, dict) else None
        if isinstance(row, dict):
            sessions.append(row)

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

        stored_seconds = intval(session.get("duration_minutes")) * 60
        if effective_seconds <= 0 and stored_seconds > 0:
            effective_seconds = stored_seconds

        if effective_seconds <= 0:
            continue

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
        "query_strategy": query_strategy,
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

prod.write_text(src, encoding="utf-8")

# =========================
# FRONTEND DEDUPE
# =========================

js = client.read_text(encoding="utf-8-sig")

def remove_extra_sections(text: str, title: str, function_name: str) -> str:
    pattern = re.compile(
        r'''
        \n\s*<section\s+class="client-panel">\s*
        <div\s+class="client-section-kicker">Tiempos</div>\s*
        <h2>''' + re.escape(title) + r'''</h2>\s*
        <p\s+class="client-muted">.*?</p>\s*
        \$\{''' + re.escape(function_name) + r'''\(.*?\)\}\s*
        </section>
        ''',
        re.S | re.X,
    )

    matches = list(pattern.finditer(text))
    if len(matches) <= 1:
        return text

    # Borra desde la última hacia la segunda, conserva la primera.
    for match in reversed(matches[1:]):
        text = text[:match.start()] + text[match.end():]

    return text

js = remove_extra_sections(js, "Tiempo total por referencia", "productionTimeByReferenceTable")
js = remove_extra_sections(js, "Tiempo por operario y referencia", "productionTimeByOperatorTable")

client.write_text(js, encoding="utf-8")

print("PRODUCTION_TIME_FINAL_OK")
