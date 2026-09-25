"""Corte diario de sesiones y turnos abiertos (049D). Aplica a TODAS las empresas.

Antes un turno (mini panel de CRM, mesero, cocina, caja, tienda...) o una
entrada de asistencia del bot solo se cerraba cuando la persona marcaba la
salida o se desconectaba; podia quedar abierto dias y esas horas entraban a
la nomina. Ahora, a la hora de corte de cada empresa (00:00 por defecto,
tabla workforce_session_policy), el sistema:

1. cierra los turnos que sigan abiertos con la hora del corte
   (closed_reason = 'corte_diario') y lo refleja en Asistencia;
2. cierra las entradas de asistencia sin salida (evento check_out del sistema);
3. cierra los logins de mini panel abiertos antes del corte (los paneles que
   quedan prendidos de noche ya no abren un turno nuevo solos);
4. deja una fila en workforce_session_closures por turno, con el nombre de
   Workforce, para el aviso del Dashboard y el ajuste de la hora real.

Esas horas no se liquidan hasta que el administrador confirme la hora real
(una sola vez; despues la fila queda bloqueada por un trigger).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("clonexa.session_cutoff")

DEFAULT_CUTOFF = "00:00"
DEFAULT_ALERT_HOURS = 12.0
DEFAULT_TZ = "America/Bogota"
REASON_CUTOFF = "corte_diario"
REASON_AUTO = "cierre_automatico"
REASON_HISTORIC = "historico_largo"
SYSTEM_CLOSE_REASONS = {REASON_CUTOFF, REASON_AUTO, REASON_HISTORIC}
ACCESS_CLOSED_REASON = "Corte diario del sistema: vuelve a entrar con tu usuario y clave."
LOOP_SECONDS = 300
ADVISORY_LOCK_ID = 49004


# ------------------------------------------------------------- helpers ---
def parse_hhmm(value: Any, default: str = DEFAULT_CUTOFF) -> time:
    raw = str(value or default).strip()
    try:
        hours, minutes = raw.split(":")[:2]
        return time(int(hours), int(minutes))
    except (ValueError, TypeError):
        raise ValueError("cutoff_time_invalid")


def zone(name: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or DEFAULT_TZ))
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def aware(value: Any) -> datetime | None:
    if not value:
        return None
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def last_cutoff_instant(now_utc: datetime, cutoff: time, tz: ZoneInfo) -> datetime:
    """El corte mas reciente (hora local de la empresa) en o antes de now."""
    local_now = now_utc.astimezone(tz)
    candidate = datetime.combine(local_now.date(), cutoff, tzinfo=tz)
    if candidate > local_now:
        candidate -= timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def local_hhmm(value: Any, tz: ZoneInfo) -> str:
    dt = aware(value)
    return dt.astimezone(tz).strftime("%H:%M") if dt else ""


def closure_message(row: dict, tz: ZoneInfo) -> str:
    name = row.get("employee_name") or "Colaborador"
    at = local_hhmm(row.get("system_end_at"), tz)
    if row.get("reason") == REASON_CUTOFF:
        return f"{name} fue desconectado por el sistema a las {at}"
    if row.get("reason") == REASON_AUTO:
        return f"A {name} se le cerró el turno automáticamente a las {at}"
    return f"El turno de {name} quedó abierto demasiado tiempo (cerrado a las {at})"


def closure_payload(row: dict, tz: ZoneInfo) -> dict:
    def iso(value: Any) -> str | None:
        dt = aware(value)
        return dt.isoformat() if dt else None

    return {
        "id": str(row.get("id")),
        "employee_id": str(row.get("employee_id") or ""),
        "employee_name": row.get("employee_name") or "Colaborador",
        "panel_type": row.get("panel_type") or "",
        "source": row.get("source") or "",
        "session_ref": row.get("session_ref") or "",
        "reason": row.get("reason") or "",
        "status": row.get("status") or "pending",
        "started_at": iso(row.get("started_at")),
        "system_end_at": iso(row.get("system_end_at")),
        "system_end_local": local_hhmm(row.get("system_end_at"), tz),
        "declared_end_at": iso(row.get("declared_end_at")),
        "declared_by_name": row.get("declared_by_name") or "",
        "declared_at": iso(row.get("declared_at")),
        "real_end_at": iso(row.get("real_end_at")),
        "confirmed_by_name": row.get("confirmed_by_name") or "",
        "confirmed_at": iso(row.get("confirmed_at")),
        "message": closure_message(row, tz),
    }


# ------------------------------------------------------------ politica ---
async def load_policy(db: AsyncSession, company_id: Any) -> dict:
    result = await db.execute(
        text("""
            SELECT c.timezone AS timezone, p.cutoff_time AS cutoff_time, p.alert_after_hours AS alert_after_hours
            FROM companies c
            LEFT JOIN workforce_session_policy p ON p.company_id = c.id
            WHERE c.id = CAST(:company_id AS uuid)
        """),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first() or {}
    return {
        "timezone": row.get("timezone") or DEFAULT_TZ,
        "cutoff_time": row.get("cutoff_time") or DEFAULT_CUTOFF,
        "alert_after_hours": float(row.get("alert_after_hours") or DEFAULT_ALERT_HOURS),
    }


async def _employee_name(db: AsyncSession, company_id: str, employee_id: Any) -> str:
    if not employee_id:
        return ""
    result = await db.execute(
        text("SELECT full_name FROM employees WHERE id = CAST(:employee_id AS uuid) AND company_id = CAST(:company_id AS uuid)"),
        {"employee_id": str(employee_id), "company_id": company_id},
    )
    row = result.mappings().first()
    return str(row.get("full_name") or "") if row else ""


async def insert_closure(db: AsyncSession, **values: Any) -> None:
    await db.execute(
        text("""
            INSERT INTO workforce_session_closures (
                company_id, employee_id, employee_name, source, session_ref, panel_type,
                reason, started_at, system_end_at
            )
            VALUES (
                CAST(:company_id AS uuid), CAST(NULLIF(:employee_id, '') AS uuid), :employee_name, :source,
                :session_ref, :panel_type, :reason, :started_at, :system_end_at
            )
            ON CONFLICT (company_id, source, session_ref) DO NOTHING
        """),
        {
            "company_id": str(values["company_id"]),
            "employee_id": str(values.get("employee_id") or ""),
            "employee_name": str(values.get("employee_name") or "Colaborador")[:180],
            "source": values["source"],
            "session_ref": str(values["session_ref"])[:64],
            "panel_type": str(values.get("panel_type") or "")[:40],
            "reason": values["reason"],
            "started_at": values["started_at"],
            "system_end_at": values["system_end_at"],
        },
    )


async def _attendance_checkout(
    db: AsyncSession, company_id: str, employee_id: str, employee_name: str, cutoff: datetime, payload: dict,
) -> None:
    await db.execute(
        text("""
            INSERT INTO workforce_attendance_events (
                company_id, employee_id, event_type, event_label, employee_name, status_after,
                source, module_code, source_channel, detail, payload_json, metadata_json, occurred_at
            )
            VALUES (
                CAST(:company_id AS uuid), CAST(:employee_id AS uuid), 'check_out', 'Corte diario del sistema',
                :employee_name, 'checked_out', 'system', 'workforce', 'system_cutoff',
                'Turno cerrado por el corte diario del sistema', CAST(:payload AS jsonb), CAST(:payload AS jsonb), :cutoff
            )
        """),
        {"company_id": company_id, "employee_id": employee_id, "employee_name": employee_name[:180],
         "payload": json.dumps({**payload, "system_cutoff": True}), "cutoff": cutoff},
    )
    await db.execute(
        text("""
            UPDATE workforce_attendance_status
               SET status = 'checked_out', last_event_type = 'check_out', last_event_at = :cutoff,
                   check_out_at = :cutoff, break_started_at = NULL, updated_at = now()
             WHERE company_id = CAST(:company_id AS uuid)
               AND employee_id = CAST(:employee_id AS uuid)
               AND status IN ('working', 'on_break')
        """),
        {"company_id": company_id, "employee_id": employee_id, "cutoff": cutoff},
    )


# --------------------------------------------------------------- corte ---
async def run_company_cutoff(db: AsyncSession, company_id: Any, now_utc: datetime) -> dict:
    """Aplica el corte mas reciente de UNA empresa. Idempotente."""
    cid = str(company_id)
    policy = await load_policy(db, cid)
    tz = zone(policy["timezone"])
    cutoff = last_cutoff_instant(now_utc, parse_hhmm(policy["cutoff_time"]), tz)
    counts = {"company_id": cid, "cutoff": cutoff.isoformat(), "sessions": 0, "attendance": 0, "logins": 0}

    sessions = await db.execute(
        text("""
            SELECT s.id, s.employee_id, s.panel_type, s.status, s.started_at, s.active_started_at,
                   s.current_break_started_at, u.full_name AS user_name
            FROM mini_panel_work_sessions s
            LEFT JOIN company_users u ON u.id = s.user_id
            WHERE s.company_id = CAST(:company_id AS uuid)
              AND s.status IN ('active', 'break')
              AND s.started_at < :cutoff
        """),
        {"company_id": cid, "cutoff": cutoff},
    )
    for row in [dict(r) for r in sessions.mappings().all()]:
        status = str(row.get("status") or "")
        active_from = aware(row.get("active_started_at"))
        break_from = aware(row.get("current_break_started_at"))
        active_delta = max(0, int((cutoff - active_from).total_seconds())) if status == "active" and active_from else 0
        break_delta = max(0, int((cutoff - break_from).total_seconds())) if status == "break" and break_from else 0
        updated = await db.execute(
            text("""
                UPDATE mini_panel_work_sessions
                   SET status = 'finished', ended_at = :cutoff,
                       active_seconds = COALESCE(active_seconds, 0) + :active_delta,
                       break_seconds = COALESCE(break_seconds, 0) + :break_delta,
                       active_started_at = NULL, current_break_started_at = NULL,
                       closed_reason = 'corte_diario', updated_at = now()
                 WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)
                   AND status IN ('active', 'break')
            """),
            {"id": str(row["id"]), "company_id": cid, "cutoff": cutoff,
             "active_delta": active_delta, "break_delta": break_delta},
        )
        if not getattr(updated, "rowcount", 1):
            continue  # alguien lo cerro entre tanto
        employee_id = str(row.get("employee_id") or "")
        name = await _employee_name(db, cid, employee_id) or str(row.get("user_name") or "") or "Colaborador"
        await insert_closure(db, company_id=cid, employee_id=employee_id, employee_name=name, source="mini_panel",
                             session_ref=str(row["id"]), panel_type=row.get("panel_type"), reason=REASON_CUTOFF,
                             started_at=row["started_at"], system_end_at=cutoff)
        if employee_id:
            await _attendance_checkout(db, cid, employee_id, name, cutoff, {"mini_panel_session_id": str(row["id"])})
        counts["sessions"] += 1

    attendance = await db.execute(
        text("""
            SELECT st.employee_id, st.check_in_at, e.full_name
            FROM workforce_attendance_status st
            JOIN employees e ON e.id = st.employee_id AND e.company_id = st.company_id
            WHERE st.company_id = CAST(:company_id AS uuid)
              AND st.status IN ('working', 'on_break')
              AND st.check_in_at < :cutoff
        """),
        {"company_id": cid, "cutoff": cutoff},
    )
    for row in [dict(r) for r in attendance.mappings().all()]:
        employee_id = str(row["employee_id"])
        checkin = await db.execute(
            text("""
                SELECT id, payload_json FROM workforce_attendance_events
                WHERE company_id = CAST(:company_id AS uuid) AND employee_id = CAST(:employee_id AS uuid)
                  AND event_type IN ('check_in', 'entrada', 'start_shift', 'shift_start')
                  AND COALESCE(occurred_at, created_at) <= :check_in_at + INTERVAL '1 minute'
                ORDER BY COALESCE(occurred_at, created_at) DESC
                LIMIT 1
            """),
            {"company_id": cid, "employee_id": employee_id, "check_in_at": row["check_in_at"]},
        )
        event = checkin.mappings().first()
        payload = event.get("payload_json") if event else None
        payload = json.loads(payload) if isinstance(payload, str) else (payload or {})
        if isinstance(payload, dict) and payload.get("mini_panel_session_id"):
            # Solo es el reflejo de un turno de mini panel (ese turno ya tiene su
            # propio cierre): se corrige el estado, sin aviso duplicado.
            await db.execute(
                text("""
                    UPDATE workforce_attendance_status
                       SET status = 'checked_out', check_out_at = :cutoff, break_started_at = NULL, updated_at = now()
                     WHERE company_id = CAST(:company_id AS uuid) AND employee_id = CAST(:employee_id AS uuid)
                       AND status IN ('working', 'on_break')
                """),
                {"company_id": cid, "employee_id": employee_id, "cutoff": cutoff},
            )
            continue
        ref = str(event["id"]) if event else f"{employee_id}:{aware(row['check_in_at']).isoformat()}"
        name = str(row.get("full_name") or "Colaborador")
        await _attendance_checkout(db, cid, employee_id, name, cutoff, {"check_in_event_id": ref})
        await insert_closure(db, company_id=cid, employee_id=employee_id, employee_name=name, source="attendance",
                             session_ref=ref, panel_type="asistencia", reason=REASON_CUTOFF,
                             started_at=row["check_in_at"], system_end_at=cutoff)
        counts["attendance"] += 1

    # Cierres automaticos por tiempo maximo (028Q/044D) de los ultimos dias:
    # tambien van al aviso y al ajuste de la hora real.
    autoclosed = await db.execute(
        text("""
            SELECT s.id, s.employee_id, s.panel_type, s.started_at, s.ended_at, u.full_name AS user_name
            FROM mini_panel_work_sessions s
            LEFT JOIN company_users u ON u.id = s.user_id
            WHERE s.company_id = CAST(:company_id AS uuid)
              AND s.closed_reason = 'cierre_automatico'
              AND s.ended_at > :since
              AND NOT EXISTS (
                  SELECT 1 FROM workforce_session_closures c
                  WHERE c.company_id = s.company_id AND c.source = 'mini_panel' AND c.session_ref = s.id::text
              )
        """),
        {"company_id": cid, "since": now_utc - timedelta(days=3)},
    )
    for row in [dict(r) for r in autoclosed.mappings().all()]:
        name = await _employee_name(db, cid, row.get("employee_id")) or str(row.get("user_name") or "") or "Colaborador"
        await insert_closure(db, company_id=cid, employee_id=str(row.get("employee_id") or ""), employee_name=name,
                             source="mini_panel", session_ref=str(row["id"]), panel_type=row.get("panel_type"),
                             reason=REASON_AUTO, started_at=row["started_at"], system_end_at=row["ended_at"])

    logins = await db.execute(
        text("""
            UPDATE clonexa_access_sessions
               SET status = 'closed', closed_at = now(), closed_reason = :reason, last_seen_at = now()
             WHERE company_id = CAST(:company_id AS uuid)
               AND scope = 'mini_panel'
               AND status = 'active'
               AND created_at < :cutoff
        """),
        {"company_id": cid, "cutoff": cutoff, "reason": ACCESS_CLOSED_REASON},
    )
    counts["logins"] = int(getattr(logins, "rowcount", 0) or 0)
    await db.execute(
        text("""
            INSERT INTO workforce_session_policy (company_id, last_cutoff_at)
            VALUES (CAST(:company_id AS uuid), :cutoff)
            ON CONFLICT (company_id) DO UPDATE SET last_cutoff_at = EXCLUDED.last_cutoff_at
        """),
        {"company_id": cid, "cutoff": cutoff},
    )
    await db.commit()
    return counts


async def companies_with_open_work(db: AsyncSession) -> list[str]:
    result = await db.execute(text("""
        SELECT DISTINCT company_id::text AS company_id FROM mini_panel_work_sessions WHERE status IN ('active', 'break')
        UNION
        SELECT DISTINCT company_id::text FROM workforce_attendance_status WHERE status IN ('working', 'on_break')
        UNION
        SELECT DISTINCT company_id::text FROM clonexa_access_sessions
         WHERE scope = 'mini_panel' AND status = 'active' AND company_id IS NOT NULL
    """))
    return [str(row["company_id"]) for row in result.mappings().all()]


async def run_all_cutoffs(db: AsyncSession, now_utc: datetime | None = None) -> list[dict]:
    now_utc = now_utc or datetime.now(timezone.utc)
    done = []
    for company_id in await companies_with_open_work(db):
        try:
            done.append(await run_company_cutoff(db, company_id, now_utc))
        except Exception as exc:  # una empresa con datos raros no frena a las demas
            await db.rollback()
            log.warning("Corte diario fallo para %s: %s", company_id, exc)
    return done


async def cutoff_loop() -> None:
    """Revisa cada 5 minutos; con varias replicas, solo una corre a la vez."""
    from app.core.database import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                locked = (await db.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": ADVISORY_LOCK_ID})).scalar()
                if locked:
                    try:
                        results = await run_all_cutoffs(db)
                        closed = [r for r in results if r["sessions"] or r["attendance"] or r["logins"]]
                        if closed:
                            log.info("Corte diario aplicado: %s", closed)
                    finally:
                        await db.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": ADVISORY_LOCK_ID})
                        await db.commit()
        except Exception as exc:
            log.warning("Corte diario no pudo correr: %s", exc)
        await asyncio.sleep(LOOP_SECONDS)


def start_cutoff_loop() -> None:
    if os.getenv("CLONEXA_DISABLE_SESSION_CUTOFF", "").strip().lower() in {"1", "true", "yes"}:
        return
    asyncio.get_event_loop().create_task(cutoff_loop())
