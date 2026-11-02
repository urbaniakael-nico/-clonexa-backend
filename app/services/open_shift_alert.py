"""Aviso de turno abierto y "Cerrar turno" del portal (interruptor open_shift_alert, 060C).

Interruptor por empresa ``open_shift_alert`` (settings del modulo workforce), apagado
por defecto. Hoy solo VOLTAGE. El turno vive en el servidor: si el celular se apaga
sigue abierto y no se pierde nada.
- Tarea periodica (cada 5 min, dentro del ciclo del bot): un turno abierto hace mas de
  N horas (workforce_session_policy.alert_after_hours de la empresa, 12 por defecto)
  recibe UN aviso al colaborador por el bot y UN aviso a los supervisores de su lugar
  de trabajo (al director si no hay supervisor): nombre, lugar, hora de inicio y horas
  abiertas. Un aviso por turno (tabla open_shift_alerts). Nunca cierra el turno.
- Portal (CRM Campo y Personal): el supervisor / direccion / dueno cierra el turno de
  alguien con la hora real de salida y una nota obligatoria; queda en
  shift_manual_closes (quien, cuando, hora de inicio, hora puesta, estado original).
Toda consulta filtra por company_id.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("clonexa.open_shift_alert")

KEY = "open_shift_alert"
MODULE = "workforce"
LOOP_SECONDS = 300
DEFAULT_HOURS = 12.0
NOTE_MIN = 5
NOTE_MAX = 500
SUPERVISOR_ROLES = {"supervisor"}
DIRECTOR_ROLES = {"gerencia", "director", "gerente", "manager", "management"}
OWNER_ROLES = {"company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"}
CLOSE_ROLES = OWNER_ROLES | DIRECTOR_ROLES | SUPERVISOR_ROLES

TEXTS = {
    "es": {
        "worker": "⏰ Tu turno sigue abierto desde {start} ({hours} h).\nSi ya terminaste, toca «Finalizar turno» en el menú. Si no puedes, avisa a tu supervisor para que lo cierre con tu hora real de salida.",
        "boss": "⏰ Turno abierto hace {hours} h\n👤 {name}\n📍 {place}\n🕐 Inicio: {start}\n\nSi ya salió, ciérralo en el portal (CRM Campo o Personal › Cerrar turno) con la hora real de salida.",
        "no_place": "Sin lugar asignado",
    },
    "en": {
        "worker": "⏰ Your shift is still open since {start} ({hours} h).\nIf you're done, tap \"End shift\" in the menu. If you can't, ask your supervisor to close it with your real end time.",
        "boss": "⏰ Shift open for {hours} h\n👤 {name}\n📍 {place}\n🕐 Started: {start}\n\nIf they already left, close it in the portal (CRM Campo or Personal › Close shift) with the real end time.",
        "no_place": "No work location",
    },
}


class Invalid(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class TooEarly(Invalid):
    """El turno aun no pasa el limite de horas de la empresa: no se cierra (400)."""

    def __init__(self, hours: float):
        super().__init__("employee_id", f"Este turno aún no supera {hours_number(hours)} horas")


def hours_number(value: float) -> str:
    """12.0 -> "12"; 12.5 -> "12.5"."""
    return f"{float(value):g}"


def tr(language: str | None, key: str, **kwargs: Any) -> str:
    return TEXTS[language if language in TEXTS else "es"][key].format(**kwargs)


def role_of(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def aware(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def hours_open(started_at: datetime, now_utc: datetime) -> float:
    return max(0.0, (now_utc - started_at).total_seconds() / 3600.0)


def hours_label(value: float) -> str:
    whole = int(value)
    minutes = int(round((value - whole) * 60))
    if minutes == 60:
        whole, minutes = whole + 1, 0
    return f"{whole}" if minutes == 0 else f"{whole}:{minutes:02d}"


def local_label(value: datetime, tz_name: str | None) -> str:
    try:
        tz = ZoneInfo(str(tz_name or "America/Bogota"))
    except Exception:
        tz = ZoneInfo("America/Bogota")
    local = value.astimezone(tz)
    return f"{local:%d/%m %H:%M} ({local.tzname()})"


def settings_dict(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


async def is_on(db: AsyncSession, company_id: Any) -> bool:
    try:
        row = (await db.execute(text("""
            SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:c AS uuid) AND lower(m.code) = :m LIMIT 1
        """), {"c": str(company_id), "m": MODULE})).first()
    except Exception:
        await db.rollback()
        return False
    return bool(row) and row[0] is not False and settings_dict(row[1]).get(KEY) is True


async def companies_on(db: AsyncSession) -> list[str]:
    rows = (await db.execute(text("""
        SELECT cm.company_id::text FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE lower(m.code) = :m AND COALESCE(cm.enabled, true) IS TRUE
          AND (cm.settings::jsonb ->> :k) = 'true'
    """), {"m": MODULE, "k": KEY})).all()
    return [str(r[0]) for r in rows]


async def alert_hours(db: AsyncSession, company_id: Any) -> float:
    try:
        value = (await db.execute(text("""
            SELECT alert_after_hours FROM workforce_session_policy WHERE company_id = CAST(:c AS uuid) LIMIT 1
        """), {"c": str(company_id)})).scalar()
    except Exception:
        await db.rollback()
        return DEFAULT_HOURS
    try:
        hours = float(value) if value is not None else DEFAULT_HOURS
    except (TypeError, ValueError):
        return DEFAULT_HOURS
    return hours if hours > 0 else DEFAULT_HOURS


async def _has_table(db: AsyncSession, name: str) -> bool:
    return bool((await db.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": name})).scalar())


async def open_shifts(db: AsyncSession, company_id: Any, *, older_than_hours: float = 0.0,
                      now_utc: datetime | None = None) -> list[dict[str, Any]]:
    """Turnos abiertos (trabajando o en pausa) de la empresa, del mas viejo al mas nuevo."""
    now_utc = now_utc or datetime.now(timezone.utc)
    places = await _has_table(db, "work_locations")
    place_cols = ("e.work_location_id::text AS work_location_id, wl.name AS work_location_name, wl.timezone AS work_location_tz"
                  if places else "NULL::text AS work_location_id, NULL::text AS work_location_name, NULL::text AS work_location_tz")
    place_join = "LEFT JOIN work_locations wl ON wl.id = e.work_location_id AND wl.company_id = e.company_id" if places else ""
    rows = (await db.execute(text(f"""
        SELECT s.employee_id::text AS employee_id, COALESCE(e.full_name, '') AS employee_name, COALESCE(e.role, '') AS employee_role,
               COALESCE(e.telegram_user_id::text, '') AS telegram_user_id, s.status, s.check_in_at, c.timezone AS company_tz,
               {place_cols}
        FROM workforce_attendance_status s
        JOIN employees e ON e.id = s.employee_id AND e.company_id = s.company_id
        JOIN companies c ON c.id = s.company_id
        {place_join}
        WHERE s.company_id = CAST(:c AS uuid) AND s.status IN ('working', 'on_break') AND s.check_in_at IS NOT NULL
          AND s.check_in_at <= :limit
        ORDER BY s.check_in_at ASC
    """), {"c": str(company_id), "limit": now_utc - timedelta(hours=older_than_hours)})).mappings().all()
    out = []
    for row in rows:
        started = aware(row["check_in_at"])
        out.append({**dict(row), "check_in_at": started, "hours_open": round(hours_open(started, now_utc), 2),
                    "tz": row.get("work_location_tz") or row.get("company_tz") or "America/Bogota"})
    return out


async def bosses(db: AsyncSession, company_id: Any, work_location_id: str | None, exclude_employee_id: str) -> list[dict[str, Any]]:
    """Supervisores del lugar del colaborador con Telegram; si no hay, la direccion."""
    rows = (await db.execute(text("""
        SELECT e.id::text AS employee_id, COALESCE(e.full_name, '') AS name, COALESCE(e.role, '') AS role,
               COALESCE(e.telegram_user_id::text, '') AS telegram_user_id,
               """ + ("e.work_location_id::text" if await _has_table(db, "work_locations") else "NULL::text") + """ AS work_location_id
        FROM employees e
        WHERE e.company_id = CAST(:c AS uuid) AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')
          AND COALESCE(e.telegram_user_id::text, '') <> '' AND e.id::text <> :x
    """), {"c": str(company_id), "x": str(exclude_employee_id)})).mappings().all()
    people = [dict(r) for r in rows]
    supervisors = [p for p in people if role_of(p["role"]) in SUPERVISOR_ROLES and work_location_id and p["work_location_id"] == work_location_id]
    if supervisors:
        return supervisors
    return [p for p in people if role_of(p["role"]) in DIRECTOR_ROLES]


async def claim(db: AsyncSession, company_id: Any, employee_id: str, started_at: datetime, hours: float, recipients: list[str]) -> bool:
    row = (await db.execute(text("""
        INSERT INTO open_shift_alerts (company_id, employee_id, shift_started_at, hours_open, recipients)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :s, :h, CAST(:r AS jsonb))
        ON CONFLICT (company_id, employee_id, shift_started_at) DO NOTHING
        RETURNING employee_id
    """), {"c": str(company_id), "e": employee_id, "s": started_at, "h": round(hours, 2), "r": json.dumps(recipients)})).first()
    await db.commit()
    return row is not None


async def run_company(db: AsyncSession, company_id: Any, *, send, language_of, now_utc: datetime | None = None) -> int:
    """Avisa los turnos de UNA empresa que pasaron el limite. Devuelve cuantos turnos avisó.
    `send(chat_id, text)` y `language_of(telegram_user_id)` los pone quien llama."""
    now_utc = now_utc or datetime.now(timezone.utc)
    limit = await alert_hours(db, company_id)
    done = 0
    for shift in await open_shifts(db, company_id, older_than_hours=limit, now_utc=now_utc):
        boss_list = await bosses(db, company_id, shift.get("work_location_id"), shift["employee_id"])
        recipients = [b["name"] for b in boss_list]
        if not await claim(db, company_id, shift["employee_id"], shift["check_in_at"], shift["hours_open"], recipients):
            continue  # ya avisado este turno
        start = local_label(shift["check_in_at"], shift["tz"])
        hours = hours_label(shift["hours_open"])
        if shift["telegram_user_id"]:
            lang = await language_of(shift["telegram_user_id"])
            await send(shift["telegram_user_id"], tr(lang, "worker", start=start, hours=hours))
        for boss in boss_list:
            lang = await language_of(boss["telegram_user_id"])
            await send(boss["telegram_user_id"], tr(lang, "boss", hours=hours, name=shift["employee_name"] or "—",
                                                    place=shift.get("work_location_name") or tr(lang, "no_place"), start=start))
        done += 1
    return done


async def run_all(db: AsyncSession) -> int:
    from uuid import UUID

    from app.api.v1.endpoints import bots
    from app.services import bot_punch_gps

    total = 0
    for cid in await companies_on(db):
        try:
            token = await bot_punch_gps.bot_token(db, cid)

            async def send(chat_id: str, message: str, _token=token) -> None:
                if _token:
                    try:
                        await bots._send_telegram_message(_token, chat_id, message)
                    except Exception as exc:
                        log.warning("Aviso de turno abierto no se pudo enviar (%s): %s", cid, type(exc).__name__)

            async def language_of(tg: str, _cid=cid) -> str:
                try:
                    lang = await bots._get_user_language(db, UUID(_cid), tg)
                except Exception:
                    await db.rollback()
                    return "es"
                return "en" if lang == "en" else "es"

            total += await run_company(db, cid, send=send, language_of=language_of)
        except Exception as exc:  # una empresa con datos raros no frena a las demas
            await db.rollback()
            log.warning("Aviso de turno abierto fallo para %s: %s", cid, type(exc).__name__)
    return total


# ------------------------------------------------------------ cierre manual (portal)
def parse_end_at(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise Invalid("end_at", "Indica la hora real de salida.")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise Invalid("end_at", "Hora de salida no válida.") from None
    if parsed.tzinfo is None:
        raise Invalid("end_at", "La hora de salida debe traer zona horaria.")
    return parsed.astimezone(timezone.utc)


def clean_note(value: Any) -> str:
    note = " ".join(str(value or "").split())
    if len(note) < NOTE_MIN:
        raise Invalid("note", f"La nota es obligatoria (mínimo {NOTE_MIN} caracteres).")
    return note[:NOTE_MAX]


async def close_shift(db: AsyncSession, company_id: Any, employee_id: Any, body: Any, *, actor: str,
                      actor_user_id: str | None, now_utc: datetime | None = None,
                      min_hours: float = 0.0) -> dict[str, Any]:
    """Cierra un turno abierto con la hora real de salida y la nota. Nunca abre ni cambia
    otro turno; si el turno ya se cerro (por el bot) responde que ya no esta abierto.
    Con `min_hours` (el limite del aviso, 12 por defecto) un turno mas nuevo no se cierra:
    TooEarly. El portal siempre lo pasa."""
    now_utc = now_utc or datetime.now(timezone.utc)
    body = body if isinstance(body, dict) else {}
    end_at = parse_end_at(body.get("end_at"))
    note = clean_note(body.get("note"))
    cid, eid = str(company_id), str(employee_id)
    row = (await db.execute(text("""
        SELECT s.status, s.check_in_at, COALESCE(e.full_name, '') AS employee_name
        FROM workforce_attendance_status s
        JOIN employees e ON e.id = s.employee_id AND e.company_id = s.company_id
        WHERE s.company_id = CAST(:c AS uuid) AND s.employee_id = CAST(:e AS uuid)
        FOR UPDATE OF s
    """), {"c": cid, "e": eid})).mappings().first()
    if not row or row["status"] not in {"working", "on_break"}:
        raise Invalid("employee_id", "Esa persona no tiene un turno abierto.")
    started = aware(row["check_in_at"])
    if min_hours > 0 and (started is None or hours_open(started, now_utc) < min_hours):
        raise TooEarly(min_hours)
    if started is not None and end_at <= started:
        raise Invalid("end_at", "La salida debe ser después del inicio del turno.")
    if end_at > now_utc + timedelta(minutes=2):
        raise Invalid("end_at", "La salida no puede estar en el futuro.")
    payload = {"manual_close": True, "note": note, "closed_by": actor, "closed_by_user_id": actor_user_id,
               "original_status": row["status"], "shift_started_at": started.isoformat() if started else None,
               "closed_at": now_utc.isoformat()}
    event_id = (await db.execute(text("""
        INSERT INTO workforce_attendance_events (
            company_id, employee_id, event_type, event_label, employee_name, status_after,
            source, module_code, source_channel, detail, notes, payload_json, metadata_json, occurred_at
        )
        VALUES (
            CAST(:c AS uuid), CAST(:e AS uuid), 'check_out', 'Turno cerrado por supervisor', :n, 'checked_out',
            'portal', 'workforce', 'portal_manual_close', :note, :note, CAST(:p AS jsonb), CAST(:p AS jsonb), :at
        )
        RETURNING id::text
    """), {"c": cid, "e": eid, "n": str(row["employee_name"])[:180], "note": note, "p": json.dumps(payload), "at": end_at})).scalar()
    await db.execute(text("""
        UPDATE workforce_attendance_status
           SET status = 'checked_out', last_event_type = 'check_out', last_event_at = :at,
               check_out_at = :at, break_started_at = NULL, updated_at = now()
         WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND status IN ('working', 'on_break')
    """), {"c": cid, "e": eid, "at": end_at})
    if await _has_table(db, "gps_tracking_sessions"):
        await db.execute(text("""
            UPDATE gps_tracking_sessions SET status = 'closed', ended_at = :at, updated_at = now()
             WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND status = 'active'
        """), {"c": cid, "e": eid, "at": end_at})
    await db.execute(text("""
        INSERT INTO shift_manual_closes (company_id, employee_id, employee_name, original_status, shift_started_at, end_at, note,
                                         closed_by, closed_by_user_id, closed_at, attendance_event_id)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :n, :st, :s, :at, :note, :by, CAST(:uid AS uuid), :now, CAST(:ev AS uuid))
    """), {"c": cid, "e": eid, "n": str(row["employee_name"])[:200], "st": row["status"], "s": started, "at": end_at, "note": note,
           "by": str(actor or "")[:200] or None, "uid": actor_user_id, "now": now_utc, "ev": event_id})
    await db.commit()
    return {"employee_id": eid, "employee_name": row["employee_name"], "shift_started_at": iso(started), "end_at": iso(end_at),
            "original_status": row["status"], "note": note, "closed_by": actor, "attendance_event_id": event_id}


def iso(value: Any) -> str | None:
    value = aware(value)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


async def recent_closes(db: AsyncSession, company_id: Any, limit: int = 50) -> list[dict[str, Any]]:
    rows = (await db.execute(text("""
        SELECT employee_id::text AS employee_id, employee_name, original_status, shift_started_at, end_at, note, closed_by, closed_at
        FROM shift_manual_closes WHERE company_id = CAST(:c AS uuid) ORDER BY closed_at DESC LIMIT :l
    """), {"c": str(company_id), "l": int(limit)})).mappings().all()
    return [{**dict(r), "shift_started_at": iso(r["shift_started_at"]), "end_at": iso(r["end_at"]), "closed_at": iso(r["closed_at"])}
            for r in rows]


def shift_out(shift: dict[str, Any]) -> dict[str, Any]:
    return {"employee_id": shift["employee_id"], "employee_name": shift["employee_name"], "status": shift["status"],
            "shift_started_at": iso(shift["check_in_at"]), "hours_open": shift["hours_open"],
            "work_location_id": shift.get("work_location_id"), "work_location_name": shift.get("work_location_name"),
            "timezone": shift["tz"]}
