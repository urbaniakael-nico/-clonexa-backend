from pathlib import Path
import re

crm_path = Path("app/api/v1/endpoints/crm_live_v1.py")
client_path = Path("app/web/client.js")
prod_path = Path("app/api/v1/endpoints/production_v1.py")

crm_source = r'''
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
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


async def active_modules(db: AsyncSession, company_id: str) -> set[str]:
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
    return {clean(row.get("code")).lower() for row in rows}


async def company_profile(db: AsyncSession, company_id: str) -> dict[str, Any]:
    if not await table_exists(db, "companies"):
        return {"id": company_id, "name": "Empresa", "slug": ""}

    cols = await table_columns(db, "companies")
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


async def employees_snapshot(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    if not await table_exists(db, "employees"):
        return []

    employee_cols = await table_columns(db, "employees")

    if "full_name" in employee_cols:
        name_expr = "COALESCE(e.full_name, '')"
    elif "name" in employee_cols:
        name_expr = "COALESCE(e.name, '')"
    else:
        name_expr = "'Empleado'"

    role_expr = "COALESCE(e.role, '')" if "role" in employee_cols else "''"
    telegram_expr = "COALESCE(e.telegram_user_id::text, '')" if "telegram_user_id" in employee_cols else "''"

    status_filter = ""
    if "status" in employee_cols:
        status_filter = "AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')"

    status_join = ""
    status_fields = """
        'sin_turno' AS work_status,
        NULL::text AS status_started_at,
        '' AS last_event_type
    """

    if await table_exists(db, "workforce_attendance_status"):
        status_cols = await table_columns(db, "workforce_attendance_status")
        if {"company_id", "employee_id", "status"}.issubset(status_cols):
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


def normalize_status(status: Any) -> str:
    value = clean(status).lower()

    if value in {"working", "trabajando", "activo"}:
        return "working"

    if value in {"on_break", "break", "pause", "pausa", "en_pausa"}:
        return "on_break"

    if value in {"checked_out", "finished", "turno_finalizado", "salida"}:
        return "checked_out"

    return "sin_turno"


def status_label(status: str) -> str:
    value = normalize_status(status)

    if value == "working":
        return "Activo"

    if value == "on_break":
        return "En pausa"

    return "Fuera de turno"


async def latest_shift_start(db: AsyncSession, company_id: str, employee_id: str) -> str | None:
    if not await table_exists(db, "workforce_attendance_events"):
        return None

    rows = await safe_rows(
        db,
        """
        SELECT COALESCE(occurred_at, created_at)::text AS started_at
        FROM workforce_attendance_events
        WHERE company_id::text = :company_id
          AND employee_id::text = :employee_id
          AND lower(COALESCE(event_type, '')) IN (
            'check_in',
            'entrada',
            'start_shift',
            'shift_start',
            'inicio_turno',
            'clock_in'
          )
        ORDER BY COALESCE(occurred_at, created_at) DESC
        LIMIT 1
        """,
        {"company_id": company_id, "employee_id": employee_id},
    )

    return clean(rows[0].get("started_at")) if rows else None


async def effective_seconds_between(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    start_at: str | None,
    end_at: str | None = None,
) -> int:
    """
    Tiempo efectivo = tiempo bruto - pausas.
    Si end_at es pause_started_at, congela el tiempo en el momento de pausa.
    """
    if not start_at:
        return 0

    if not await table_exists(db, "workforce_attendance_events"):
        rows = await safe_rows(
            db,
            """
            SELECT GREATEST(EXTRACT(EPOCH FROM (COALESCE(CAST(:end_at AS timestamptz), now()) - CAST(:start_at AS timestamptz))), 0)::int AS seconds
            """,
            {"start_at": start_at, "end_at": end_at or None},
        )
        return intval(rows[0].get("seconds")) if rows else 0

    rows = await safe_rows(
        db,
        """
        WITH bounds AS (
            SELECT
                CAST(:start_at AS timestamptz) AS start_at,
                COALESCE(CAST(:end_at AS timestamptz), now()) AS end_at
        ),
        raw_events AS (
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
                'on_break',
                'break_end',
                'pause_end',
                'resume',
                'return',
                'retorno',
                'reanudar',
                'clock_resume'
              )
        ),
        ordered_events AS (
            SELECT
                event_type,
                event_at,
                row_number() OVER (ORDER BY event_at ASC) AS rn
            FROM raw_events
        ),
        pause_starts AS (
            SELECT
                event_at AS pause_start,
                row_number() OVER (ORDER BY event_at ASC) AS pair_id
            FROM ordered_events
            WHERE event_type IN ('break_start','pause_start','pause','pausa','break','on_break')
        ),
        pause_ends AS (
            SELECT
                event_at AS pause_end,
                row_number() OVER (ORDER BY event_at ASC) AS pair_id
            FROM ordered_events
            WHERE event_type IN ('break_end','pause_end','resume','return','retorno','reanudar','clock_resume')
        ),
        pause_pairs AS (
            SELECT
                ps.pause_start,
                COALESCE(pe.pause_end, bounds.end_at) AS pause_end
            FROM pause_starts ps
            CROSS JOIN bounds
            LEFT JOIN pause_ends pe ON pe.pair_id = ps.pair_id
            WHERE COALESCE(pe.pause_end, bounds.end_at) > ps.pause_start
        ),
        pause_total AS (
            SELECT COALESCE(sum(EXTRACT(EPOCH FROM (pause_end - pause_start))), 0) AS pause_seconds
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


def normalize_session_row(row: dict[str, Any]) -> dict[str, Any]:
    status = clean(row.get("status")).lower()
    ended_at = row.get("ended_at")
    is_active = status == "active" or not ended_at

    return {
        "session_id": row.get("id"),
        "employee_id": clean(row.get("employee_id")),
        "employee_name": clean(row.get("employee_name")),
        "telegram_user_id": clean(row.get("telegram_user_id")),
        "reference_id": clean(row.get("reference_id")),
        "reference_name": clean(row.get("reference_name")),
        "started_at": row.get("started_at"),
        "ended_at": ended_at,
        "status": status,
        "is_active": is_active,
        "duration_seconds": intval(row.get("duration_seconds")),
        "effective_seconds": intval(row.get("effective_seconds")),
    }


async def reference_sessions_for_employee(
    db: AsyncSession,
    company_id: str,
    *,
    employee_id: str,
    employee_name: str,
    telegram_user_id: str,
    shift_started_at: str | None,
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
            CASE
                WHEN lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL
                    THEN EXTRACT(EPOCH FROM (now() - started_at))::int
                ELSE GREATEST(COALESCE(duration_minutes, 0) * 60, 0)::int
            END AS duration_seconds,
            GREATEST(COALESCE(duration_minutes, 0) * 60, 0)::int AS effective_seconds
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
                OR :shift_started_at IS NULL
                OR started_at >= CAST(:shift_started_at AS timestamptz)
          )
        ORDER BY started_at ASC
        LIMIT 50
        """,
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "employee_name": employee_name,
            "telegram_user_id": telegram_user_id,
            "shift_started_at": shift_started_at or None,
        },
    )

    return [normalize_session_row(row) for row in rows]


async def all_active_reference_sessions(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
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
            EXTRACT(EPOCH FROM (now() - started_at))::int AS duration_seconds,
            GREATEST(COALESCE(duration_minutes, 0) * 60, 0)::int AS effective_seconds
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND (lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL)
        ORDER BY started_at DESC
        LIMIT 50
        """,
        {"company_id": company_id},
    )

    return [normalize_session_row(row) for row in rows]


@router.get("/companies/{company_id}/snapshot")
async def crm_live_snapshot(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await company_profile(db, company_id)
    modules = await active_modules(db, company_id)
    employees = await employees_snapshot(db, company_id)
    all_active_sessions = await all_active_reference_sessions(db, company_id)

    active_people = [
        employee for employee in employees
        if normalize_status(employee.get("work_status")) in {"working", "on_break"}
    ]

    rows: list[dict[str, Any]] = []
    assigned_fallback_session_ids: set[str] = set()

    for employee in employees:
        employee_id = clean(employee.get("employee_id"))
        employee_name = clean(employee.get("employee_name"))
        telegram_user_id = clean(employee.get("telegram_user_id"))
        work_status = normalize_status(employee.get("work_status"))
        status_started_at = employee.get("status_started_at")

        shift_started_at = None
        pause_started_at = None

        if work_status in {"working", "on_break"}:
            shift_started_at = await latest_shift_start(db, company_id, employee_id) or status_started_at
            if not status_started_at:
                status_started_at = shift_started_at

        if work_status == "on_break":
            pause_started_at = status_started_at

        timeline = await reference_sessions_for_employee(
            db,
            company_id,
            employee_id=employee_id,
            employee_name=employee_name,
            telegram_user_id=telegram_user_id,
            shift_started_at=shift_started_at,
        )

        if not timeline and work_status in {"working", "on_break"} and len(active_people) == 1 and all_active_sessions:
            fallback = [
                session for session in all_active_sessions
                if clean(session.get("session_id")) not in assigned_fallback_session_ids
            ]
            if fallback:
                latest = fallback[0]
                assigned_fallback_session_ids.add(clean(latest.get("session_id")))
                timeline = [latest]

        freeze_end = pause_started_at if work_status == "on_break" else None

        shift_effective_seconds = await effective_seconds_between(
            db,
            company_id,
            employee_id,
            shift_started_at,
            freeze_end,
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
                item_end or freeze_end,
            ) if item_start else intval(item.get("effective_seconds") or item.get("duration_seconds"))

            row_item = dict(item)
            row_item["effective_seconds"] = effective_reference_seconds
            normalized_timeline.append(row_item)

        active_reference = next((item for item in normalized_timeline if item.get("is_active")), None)

        rows.append({
            "employee_id": employee_id,
            "employee_name": employee_name or "Empleado",
            "employee_role": clean(employee.get("employee_role")),
            "telegram_user_id": telegram_user_id,
            "work_status": work_status,
            "work_status_label": status_label(work_status),
            "status_started_at": status_started_at,
            "shift_started_at": shift_started_at,
            "pause_started_at": pause_started_at,
            "pause_is_active": work_status == "on_break",
            "last_event_type": clean(employee.get("last_event_type")),
            "shift_effective_seconds": shift_effective_seconds,
            "has_active_reference": bool(active_reference),
            "active_reference_name": active_reference.get("reference_name") if active_reference else None,
            "active_reference_started_at": active_reference.get("started_at") if active_reference else None,
            "reference_timeline": normalized_timeline,
            "time_rule": "pause_excluded_from_shift_and_reference",
        })

    active_count = sum(1 for row in rows if row["work_status"] == "working")
    break_count = sum(1 for row in rows if row["work_status"] == "on_break")
    with_reference = sum(1 for row in rows if row["has_active_reference"])

    return {
        "ok": True,
        "language": "es",
        "company_id": company_id,
        "company": company,
        "server_time": datetime.utcnow().isoformat() + "Z",
        "active_modules": sorted(modules),
        "module": "crm",
        "crm_mode": "live_shared_module",
        "time_rule": "pause_excluded_from_shift_and_reference",
        "summary": {
            "employees_total": len(rows),
            "active_now": active_count,
            "on_break": break_count,
            "with_active_reference": with_reference,
            "production_enabled": "production" in modules,
            "references_enabled": "references" in modules,
            "payroll_enabled": "payroll" in modules,
            "active_reference_sessions": len(all_active_sessions),
        },
        "employees": rows,
    }
'''

crm_path.write_text(crm_source, encoding="utf-8")


client_src = client_path.read_text(encoding="utf-8-sig")


def replace_between(source: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = source.find(start_marker)
    end = source.find(end_marker)

    if start == -1 or end == -1 or end < start:
        raise SystemExit(f"No encontré bloque {start_marker} / {end_marker}")

    end += len(end_marker)
    return source[:start] + replacement + source[end:]


client_block = r'''/* CX_CRM_LIVE_01_START */
  function crmLiveParseDate(value) {
    if (!value) return null;

    let raw = String(value).trim();
    if (!raw) return null;

    raw = raw.replace(" ", "T");
    raw = raw.replace(/(\.\d{3})\d+/, "$1");
    raw = raw.replace(/([+-]\d{2})$/, "$1:00");

    if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)) {
      raw = `${raw}Z`;
    }

    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return null;

    return date;
  }

  function crmLiveFormatDuration(ms) {
    if (!Number.isFinite(ms) || ms < 0) ms = 0;

    const totalSeconds = Math.floor(ms / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return [
      String(hours).padStart(2, "0"),
      String(minutes).padStart(2, "0"),
      String(seconds).padStart(2, "0"),
    ].join(":");
  }

  function crmLiveStopTimers() {
    if (window.__cxCrmLiveRefreshInterval) {
      clearInterval(window.__cxCrmLiveRefreshInterval);
      window.__cxCrmLiveRefreshInterval = null;
    }

    if (window.__cxCrmLiveTimerInterval) {
      clearInterval(window.__cxCrmLiveTimerInterval);
      window.__cxCrmLiveTimerInterval = null;
    }
  }

  function crmLiveUpdateTimers() {
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

    document.querySelectorAll("[data-live-seconds]").forEach((node) => {
      const seconds = Number(node.dataset.liveSeconds || 0);
      node.textContent = crmLiveFormatDuration(seconds * 1000);
    });
  }

  function crmStatusBadge(row) {
    const status = String(row.work_status || "").toLowerCase();

    if (status === "working") {
      return `<span style="padding:8px 12px;border-radius:999px;background:rgba(0,255,180,.14);border:1px solid rgba(0,255,180,.35);color:#adffe8">Activo</span>`;
    }

    if (status === "on_break") {
      return `<span style="padding:8px 12px;border-radius:999px;background:rgba(255,172,28,.16);border:1px solid rgba(255,172,28,.4);color:#ffd58a">En pausa</span>`;
    }

    return `<span style="padding:8px 12px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);color:#dbe7ff">Fuera de turno</span>`;
  }

  function crmLiveKpis(summary) {
    const cards = [
      ["Activos", summary?.active_now ?? 0],
      ["En pausa", summary?.on_break ?? 0],
      ["Con referencia", summary?.with_active_reference ?? 0],
      ["Sesiones ref.", summary?.active_reference_sessions ?? 0],
      ["Producción", summary?.production_enabled ? "ON" : "OFF"],
    ];

    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px">
        ${cards.map(([label, value]) => `
          <div style="padding:16px;border-radius:18px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)">
            <div style="font-size:12px;opacity:.75;text-transform:uppercase;letter-spacing:.08em">${h(label)}</div>
            <strong style="display:block;margin-top:8px;font-size:30px;line-height:1">${h(value)}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function crmEffectiveCounterMarkup(seconds, running) {
    return `
      <strong
        style="font-size:26px"
        data-effective-counter="${h(seconds || 0)}"
        data-effective-running="${running ? "true" : "false"}"
        data-effective-sync="${h(new Date().toISOString())}"
      >00:00:00</strong>
    `;
  }

  function crmTurnRow(row) {
    const status = String(row.work_status || "").toLowerCase();

    if (status === "on_break") {
      return `
        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong style="color:#ffd58a">Pausa activa</strong>
            <div class="client-muted">Tiempo en pausa</div>
          </div>
          <strong style="font-size:26px;color:#ffd58a" data-live-since="${h(row.pause_started_at || row.status_started_at || "")}">00:00:00</strong>
        </div>

        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong>Turno efectivo</strong>
            <div class="client-muted">Congelado durante la pausa</div>
          </div>
          ${crmEffectiveCounterMarkup(row.shift_effective_seconds || 0, false)}
        </div>
      `;
    }

    if (status === "working") {
      return `
        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong>Turno efectivo</strong>
            <div class="client-muted">Tiempo pagable / productivo</div>
          </div>
          ${crmEffectiveCounterMarkup(row.shift_effective_seconds || 0, true)}
        </div>
      `;
    }

    return `
      <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
        <div>
          <strong>Fuera de turno</strong>
          <div class="client-muted">Sin jornada activa</div>
        </div>
        <strong style="font-size:26px">00:00:00</strong>
      </div>
    `;
  }

  function crmReferenceTimeline(row) {
    const timeline = Array.isArray(row.reference_timeline) ? row.reference_timeline : [];
    const isPaused = String(row.work_status || "").toLowerCase() === "on_break";
    const isWorking = String(row.work_status || "").toLowerCase() === "working";

    if (!timeline.length) {
      return `
        <div style="padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <strong>Producción actual</strong>
          <div class="client-muted">Sin referencia activa</div>
        </div>
      `;
    }

    return `
      <div style="padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
        <strong>Producción del turno</strong>
        <div style="margin-top:10px;display:grid;gap:10px">
          ${timeline.map((item) => {
            const active = !!item.is_active;
            const running = active && isWorking;
            const label = active
              ? (isPaused ? "Referencia activa · pausada" : "Referencia activa · corriendo")
              : "Referencia cerrada";

            const counter = active
              ? crmEffectiveCounterMarkup(item.effective_seconds || 0, running)
              : `<strong style="font-size:22px" data-live-seconds="${h(item.effective_seconds || item.duration_seconds || 0)}">00:00:00</strong>`;

            return `
              <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:12px;border-radius:16px;background:${active ? "rgba(0,255,180,.10)" : "rgba(255,255,255,.06)"};border:1px solid ${active ? "rgba(0,255,180,.25)" : "rgba(255,255,255,.1)"}">
                <div>
                  <strong>${h(item.reference_name || "Referencia")}</strong>
                  <div class="client-muted">${h(label)}</div>
                </div>
                ${counter}
              </div>
            `;
          }).join("")}
        </div>
      </div>
    `;
  }

  function crmLiveEmployeeCard(row) {
    return `
      <article style="padding:20px;border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.11),rgba(255,255,255,.045));border:1px solid rgba(255,255,255,.14);box-shadow:0 20px 45px rgba(0,0,0,.22)">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px">
          <div>
            <div class="client-muted">Colaborador</div>
            <h2 style="margin:4px 0 4px;font-size:28px;letter-spacing:.04em">${h(row.employee_name || "Empleado")}</h2>
            ${row.employee_role ? `<div class="client-muted">${h(row.employee_role)}</div>` : ""}
          </div>
          ${crmStatusBadge(row)}
        </div>

        ${crmTurnRow(row)}
        ${crmReferenceTimeline(row)}
      </article>
    `;
  }

  async function loadCrmLiveSnapshot() {
    return await api(`/crm-live-v1/companies/${state.companyId}/snapshot`);
  }

  async function renderCrmLiveModule() {
    crmLiveStopTimers();

    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});

    let snapshot = null;
    let loadError = "";

    try {
      snapshot = await loadCrmLiveSnapshot();
    } catch (error) {
      loadError = error.message || "No se pudo cargar CRM en vivo.";
      snapshot = null;
    }

    $("app").innerHTML = `
      <main class="client-shell" data-crm-live-root>
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, b)}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("crm")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
            <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo compartido · tiempo real</div>
              <h1 class="client-title">CRM Campo</h1>
              <p class="client-muted">
                Vista viva de colaboradores, pausa, turno efectivo y referencia sin sumar tiempo muerto.
              </p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn client-btn-primary" type="button" data-crm-live-refresh>Actualizar</button>
              </div>
            </header>

            ${loadError ? `<section class="client-panel"><strong>${h(loadError)}</strong></section>` : ""}

            <section class="client-panel">
              <div class="client-section-kicker">Estado operativo actual</div>
              <h2>Operación en vivo</h2>
              ${crmLiveKpis(snapshot?.summary || {})}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Colaboradores</div>
              <h2>Estado por colaborador</h2>
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px">
                ${(snapshot?.employees || []).map(crmLiveEmployeeCard).join("") || `<div class="client-muted">Sin colaboradores activos.</div>`}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;

    crmLiveUpdateTimers();

    window.__cxCrmLiveTimerInterval = setInterval(crmLiveUpdateTimers, 1000);

    window.__cxCrmLiveRefreshInterval = setInterval(async () => {
      if (!document.querySelector("[data-crm-live-root]")) {
        crmLiveStopTimers();
        return;
      }

      await renderCrmLiveModule();
    }, 20000);
  }

  if (!window.__cxCrmLive01Bound) {
    window.__cxCrmLive01Bound = true;

    document.addEventListener("click", async (event) => {
      const moduleTrigger = event.target.closest('[data-client-module="crm"]');
      const actionTrigger = event.target.closest('[data-client-action="crm:open"]');

      if ((moduleTrigger || actionTrigger) && isClientModuleActive("crm")) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        await renderCrmLiveModule();
        return;
      }

      const refresh = event.target.closest("[data-crm-live-refresh]");
      if (refresh) {
        event.preventDefault();
        await renderCrmLiveModule();
      }
    }, true);
  }
  /* CX_CRM_LIVE_01_END */'''

if "/* CX_CRM_LIVE_01_START */" not in client_src or "/* CX_CRM_LIVE_01_END */" not in client_src:
    raise SystemExit("No encontré bloque CX_CRM_LIVE_01 en client.js")

client_src = replace_between(
    client_src,
    "/* CX_CRM_LIVE_01_START */",
    "/* CX_CRM_LIVE_01_END */",
    client_block,
)

# Limpieza defensiva de textos viejos visibles en el bloque general.
for old, new in {
    "FIELD CRM": "CRM Campo",
    "LIVE OPERATION": "Operación en vivo",
    "Current operating status": "Estado operativo actual",
    "STATUS BY COLLABORATOR": "Estado por colaborador",
    "Collaborators": "Colaboradores",
    "Collaborator": "Colaborador",
    "Off shift": "Fuera de turno",
    "On break": "En pausa",
    "Back": "Volver",
    "Refresh": "Actualizar",
}.items():
    client_src = client_src.replace(old, new)

client_path.write_text(client_src, encoding="utf-8")


# Producción: si existe, marca regla para mostrar tiempo limpio en sesiones.
if prod_path.exists():
    prod_src = prod_path.read_text(encoding="utf-8-sig")
    if '"time_rule": "pause_excluded_from_shift_and_reference"' not in prod_src:
        prod_src = prod_src.replace(
            '''        "sessions": sessions,''',
            '''        "sessions": sessions,
        "time_rule": "pause_excluded_from_shift_and_reference",''',
            1,
        )
    prod_path.write_text(prod_src, encoding="utf-8")

print("CRM_TIME_FINAL_01_OK")
