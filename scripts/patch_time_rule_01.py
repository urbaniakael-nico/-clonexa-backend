from pathlib import Path
import re

crm_path = Path("app/api/v1/endpoints/crm_live_v1.py")
prod_path = Path("app/api/v1/endpoints/production_v1.py")
client_path = Path("app/web/client.js")


# =========================================================
# 1) CRM BACKEND: effective seconds excluding pauses
# =========================================================

crm_src = crm_path.read_text(encoding="utf-8-sig")

insert_after = '''
def normalize_status(status: str) -> str:
    value = clean(status).lower()

    if value in {"working", "on_break", "checked_out"}:
        return value

    return "sin_turno"
'''

helpers = r'''

def iso_to_timestamp_expr(value_name: str) -> str:
    return f"CAST(:{value_name} AS timestamptz)"


async def pause_intervals_for_employee(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    start_at: str | None,
    end_at: str | None = None,
) -> list[dict[str, Any]]:
    if not start_at:
        return []

    if not await table_exists(db, "workforce_attendance_events"):
        return []

    rows = await safe_rows(
        db,
        """
        SELECT
            lower(COALESCE(event_type, '')) AS event_type,
            COALESCE(occurred_at, created_at)::text AS event_at
        FROM workforce_attendance_events
        WHERE company_id::text = :company_id
          AND employee_id::text = :employee_id
          AND COALESCE(occurred_at, created_at) >= CAST(:start_at AS timestamptz)
          AND (:end_at IS NULL OR COALESCE(occurred_at, created_at) <= CAST(:end_at AS timestamptz))
          AND lower(COALESCE(event_type, '')) IN (
            'break_start',
            'pause_start',
            'pause',
            'pausa',
            'break',
            'break_end',
            'pause_end',
            'resume',
            'return',
            'retorno',
            'reanudar'
          )
        ORDER BY COALESCE(occurred_at, created_at) ASC
        """,
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "start_at": start_at,
            "end_at": end_at or None,
        },
    )

    intervals = []
    open_pause = None

    start_types = {"break_start", "pause_start", "pause", "pausa", "break"}
    end_types = {"break_end", "pause_end", "resume", "return", "retorno", "reanudar"}

    for row in rows:
        event_type = clean(row.get("event_type")).lower()
        event_at = row.get("event_at")

        if event_type in start_types and not open_pause:
            open_pause = event_at
            continue

        if event_type in end_types and open_pause:
            intervals.append({"start_at": open_pause, "end_at": event_at})
            open_pause = None

    if open_pause:
        intervals.append({"start_at": open_pause, "end_at": None})

    return intervals


async def effective_seconds_between(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    start_at: str | None,
    end_at: str | None = None,
) -> int:
    if not start_at:
        return 0

    result = await safe_rows(
        db,
        """
        WITH bounds AS (
            SELECT
                CAST(:start_at AS timestamptz) AS start_at,
                COALESCE(CAST(:end_at AS timestamptz), now()) AS end_at
        ),
        pause_events AS (
            SELECT
                lower(COALESCE(event_type, '')) AS event_type,
                COALESCE(occurred_at, created_at) AS event_at
            FROM workforce_attendance_events, bounds
            WHERE company_id::text = :company_id
              AND employee_id::text = :employee_id
              AND COALESCE(occurred_at, created_at) >= bounds.start_at
              AND COALESCE(occurred_at, created_at) <= bounds.end_at
              AND lower(COALESCE(event_type, '')) IN (
                'break_start',
                'pause_start',
                'pause',
                'pausa',
                'break',
                'break_end',
                'pause_end',
                'resume',
                'return',
                'retorno',
                'reanudar'
              )
            ORDER BY event_at ASC
        ),
        pause_starts AS (
            SELECT
                event_at AS start_at,
                row_number() OVER (ORDER BY event_at ASC) AS rn
            FROM pause_events
            WHERE event_type IN ('break_start','pause_start','pause','pausa','break')
        ),
        pause_ends AS (
            SELECT
                event_at AS end_at,
                row_number() OVER (ORDER BY event_at ASC) AS rn
            FROM pause_events
            WHERE event_type IN ('break_end','pause_end','resume','return','retorno','reanudar')
        ),
        pause_pairs AS (
            SELECT
                ps.start_at,
                COALESCE(pe.end_at, bounds.end_at) AS end_at
            FROM pause_starts ps
            CROSS JOIN bounds
            LEFT JOIN pause_ends pe ON pe.rn = ps.rn
            WHERE COALESCE(pe.end_at, bounds.end_at) > ps.start_at
        ),
        pause_total AS (
            SELECT COALESCE(sum(EXTRACT(EPOCH FROM (end_at - start_at))), 0) AS pause_seconds
            FROM pause_pairs
        )
        SELECT
            GREATEST(
                EXTRACT(EPOCH FROM (bounds.end_at - bounds.start_at)) - pause_total.pause_seconds,
                0
            )::int AS effective_seconds
        FROM bounds, pause_total
        """,
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "start_at": start_at,
            "end_at": end_at or None,
        },
    )

    return intval(rows[0].get("effective_seconds")) if (rows := result) else 0
'''

if helpers not in crm_src:
    crm_src = crm_src.replace(insert_after, insert_after + helpers)

# Add effective fields inside rows.append block.
crm_src = crm_src.replace(
'''        rows.append({
            "employee_id": employee_id,''',
'''        shift_effective_seconds = await effective_seconds_between(
            db,
            company_id,
            employee_id,
            shift_started_at,
            pause_started_at if work_status == "on_break" else None,
        ) if shift_started_at else 0

        normalized_timeline = []
        for item in timeline:
            item_start = item.get("started_at")
            item_end = item.get("ended_at")

            effective_reference_seconds = await effective_seconds_between(
                db,
                company_id,
                employee_id,
                item_start,
                item_end or (pause_started_at if work_status == "on_break" else None),
            ) if item_start else intval(item.get("duration_seconds"))

            row_item = dict(item)
            row_item["effective_seconds"] = effective_reference_seconds
            normalized_timeline.append(row_item)

        rows.append({
            "employee_id": employee_id,''',
1
)

crm_src = crm_src.replace(
'''            "active_reference_started_at": active_reference.get("started_at") if active_reference else None,
            "reference_timeline": timeline,''',
'''            "active_reference_started_at": active_reference.get("started_at") if active_reference else None,
            "shift_effective_seconds": shift_effective_seconds,
            "pause_is_active": work_status == "on_break",
            "reference_timeline": normalized_timeline,''',
1
)

crm_path.write_text(crm_src, encoding="utf-8")


# =========================================================
# 2) PRODUCTION BACKEND: session minutes excluding pauses
# =========================================================

prod_src = prod_path.read_text(encoding="utf-8-sig")

prod_helpers = r'''

async def effective_session_seconds(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    start_at: str | None,
    end_at: str | None = None,
) -> int:
    if not start_at:
        return 0

    if not await table_exists(db, "workforce_attendance_events"):
        return 0

    rows = await safe_rows(
        db,
        """
        WITH bounds AS (
            SELECT
                CAST(:start_at AS timestamptz) AS start_at,
                COALESCE(CAST(:end_at AS timestamptz), now()) AS end_at
        ),
        pause_events AS (
            SELECT
                lower(COALESCE(event_type, '')) AS event_type,
                COALESCE(occurred_at, created_at) AS event_at
            FROM workforce_attendance_events, bounds
            WHERE company_id::text = :company_id
              AND employee_id::text = :employee_id
              AND COALESCE(occurred_at, created_at) >= bounds.start_at
              AND COALESCE(occurred_at, created_at) <= bounds.end_at
              AND lower(COALESCE(event_type, '')) IN (
                'break_start',
                'pause_start',
                'pause',
                'pausa',
                'break',
                'break_end',
                'pause_end',
                'resume',
                'return',
                'retorno',
                'reanudar'
              )
            ORDER BY event_at ASC
        ),
        pause_starts AS (
            SELECT
                event_at AS start_at,
                row_number() OVER (ORDER BY event_at ASC) AS rn
            FROM pause_events
            WHERE event_type IN ('break_start','pause_start','pause','pausa','break')
        ),
        pause_ends AS (
            SELECT
                event_at AS end_at,
                row_number() OVER (ORDER BY event_at ASC) AS rn
            FROM pause_events
            WHERE event_type IN ('break_end','pause_end','resume','return','retorno','reanudar')
        ),
        pause_pairs AS (
            SELECT
                ps.start_at,
                COALESCE(pe.end_at, bounds.end_at) AS end_at
            FROM pause_starts ps
            CROSS JOIN bounds
            LEFT JOIN pause_ends pe ON pe.rn = ps.rn
            WHERE COALESCE(pe.end_at, bounds.end_at) > ps.start_at
        ),
        pause_total AS (
            SELECT COALESCE(sum(EXTRACT(EPOCH FROM (end_at - start_at))), 0) AS pause_seconds
            FROM pause_pairs
        )
        SELECT
            GREATEST(
                EXTRACT(EPOCH FROM (bounds.end_at - bounds.start_at)) - pause_total.pause_seconds,
                0
            )::int AS effective_seconds
        FROM bounds, pause_total
        """,
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "start_at": start_at,
            "end_at": end_at or None,
        },
    )

    return intval(rows[0].get("effective_seconds")) if rows else 0
'''

if "async def effective_session_seconds(" not in prod_src:
    marker = "\n\nasync def sessions_summary("
    prod_src = prod_src.replace(marker, prod_helpers + marker, 1)

start = prod_src.find("async def sessions_summary(")
end = prod_src.find("\n\n\ndef build_summary", start)

if start != -1 and end != -1:
    new_sessions_summary = r'''async def sessions_summary(db: AsyncSession, company_id: str, start: date, end: date) -> dict[str, Any]:
    sessions = await safe_rows(
        db,
        """
        SELECT
            id,
            employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(reference_name, 'Sin referencia') AS reference_name,
            started_at::text AS started_at,
            ended_at::text AS ended_at,
            COALESCE(status, '') AS status,
            COALESCE(duration_minutes, 0) AS duration_minutes
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND started_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
        ORDER BY started_at ASC
        LIMIT 1000
        """,
        {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()},
    )

    active_sessions = 0
    total_effective_seconds = 0
    by_reference_map: dict[str, dict[str, Any]] = {}

    for session in sessions:
        status = clean(session.get("status")).lower()
        ended_at = session.get("ended_at")
        is_active = status == "active" or not ended_at

        if is_active:
            active_sessions += 1

        effective_seconds = await effective_session_seconds(
            db,
            company_id,
            clean(session.get("employee_id")),
            session.get("started_at"),
            None if is_active else ended_at,
        )

        if effective_seconds <= 0:
            effective_seconds = intval(session.get("duration_minutes")) * 60

        total_effective_seconds += effective_seconds

        reference_name = clean(session.get("reference_name")) or "Sin referencia"
        item = by_reference_map.setdefault(reference_name, {
            "reference_name": reference_name,
            "seconds": 0,
            "minutes": 0,
            "sessions": 0,
        })
        item["seconds"] += effective_seconds
        item["minutes"] = round(item["seconds"] / 60, 2)
        item["sessions"] += 1

    return {
        "active_sessions": active_sessions,
        "total_sessions_period": len(sessions),
        "total_minutes_period": round(total_effective_seconds / 60, 2),
        "time_rule": "pause_excluded",
        "by_reference": sorted(
            by_reference_map.values(),
            key=lambda x: x["seconds"],
            reverse=True,
        )[:20],
    }'''
    prod_src = prod_src[:start] + new_sessions_summary + prod_src[end:]

prod_path.write_text(prod_src, encoding="utf-8")


# =========================================================
# 3) CLIENT: live counters with pause freeze
# =========================================================

client_src = client_path.read_text(encoding="utf-8-sig")

client_src = client_src.replace(
'''  function crmLiveUpdateTimers() {
    const root = document.querySelector("[data-crm-live-root]");
    if (!root) {
      crmLiveStopTimers();
      return;
    }

    document.querySelectorAll("[data-live-since]").forEach((node) => {
      const startedAt = crmLiveParseDate(node.dataset.liveSince || "");
      if (!startedAt) {
        node.textContent = "00:00:00";
        return;
      }

      node.textContent = crmLiveFormatDuration(Date.now() - startedAt.getTime());
    });

    document.querySelectorAll("[data-live-seconds]").forEach((node) => {
      const seconds = Number(node.dataset.liveSeconds || 0);
      node.textContent = crmLiveFormatDuration(seconds * 1000);
    });
  }''',
'''  function crmLiveUpdateTimers() {
    const root = document.querySelector("[data-crm-live-root]");
    if (!root) {
      crmLiveStopTimers();
      return;
    }

    document.querySelectorAll("[data-live-since]").forEach((node) => {
      const startedAt = crmLiveParseDate(node.dataset.liveSince || "");
      if (!startedAt) {
        node.textContent = "00:00:00";
        return;
      }

      node.textContent = crmLiveFormatDuration(Date.now() - startedAt.getTime());
    });

    document.querySelectorAll("[data-live-seconds]").forEach((node) => {
      const seconds = Number(node.dataset.liveSeconds || 0);
      node.textContent = crmLiveFormatDuration(seconds * 1000);
    });

    document.querySelectorAll("[data-effective-counter]").forEach((node) => {
      const baseSeconds = Number(node.dataset.effectiveCounter || 0);
      const running = String(node.dataset.effectiveRunning || "false") === "true";
      const sync = crmLiveParseDate(node.dataset.effectiveSync || "");

      let seconds = baseSeconds;

      if (running && sync) {
        seconds += Math.max(Math.floor((Date.now() - sync.getTime()) / 1000), 0);
      }

      node.textContent = crmLiveFormatDuration(seconds * 1000);
    });
  }'''
)

client_src = client_src.replace(
'''<strong style="font-size:22px" data-live-since="${h(row.shift_started_at || "")}">00:00:00</strong>''',
'''<strong style="font-size:22px" data-effective-counter="${h(row.shift_effective_seconds || 0)}" data-effective-running="false">00:00:00</strong>'''
)

client_src = client_src.replace(
'''<strong style="font-size:26px" data-live-since="${h(row.shift_started_at || row.status_started_at || row.reference_timeline?.[0]?.started_at || "")}">00:00:00</strong>''',
'''<strong style="font-size:26px" data-effective-counter="${h(row.shift_effective_seconds || 0)}" data-effective-running="true" data-effective-sync="${h(new Date().toISOString())}">00:00:00</strong>'''
)

client_src = client_src.replace(
'''<strong style="font-size:22px" ${item.is_active ? `data-live-since="${h(item.started_at || "")}"` : `data-live-seconds="${h(item.duration_seconds || 0)}"`}>00:00:00</strong>''',
'''<strong style="font-size:22px" ${item.is_active ? `data-effective-counter="${h(item.effective_seconds || 0)}" data-effective-running="${row.work_status === "working" ? "true" : "false"}" data-effective-sync="${h(new Date().toISOString())}"` : `data-live-seconds="${h(item.effective_seconds || item.duration_seconds || 0)}"`}>00:00:00</strong>'''
)

client_src = client_src.replace(
    "Referencia activa · corriendo",
    '${row.work_status === "on_break" ? "Referencia activa · pausada" : "Referencia activa · corriendo"}'
)

client_path.write_text(client_src, encoding="utf-8")

print("TIME_RULE_01_OK")
