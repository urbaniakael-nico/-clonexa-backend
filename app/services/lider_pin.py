"""PIN de marcacion y escrituras del panel del Lider de operacion (067A).

Solo con work_locations y reports_board (lider_operacion.available). El lider tiene exactamente dos
escrituras y ambas viven aqui:
- Prestar su equipo para que una persona de SU operacion marque con su propio PIN. La marca usa
  bots._create_bot_attendance_event, la misma funcion del bot, con origen panel_pin, hora del
  servidor y la ubicacion del equipo.
- Finalizar AHORA el turno abierto de alguien de su operacion que va por debajo del limite de la
  empresa (open_shift_alert.close_shift con origen cerrado_por_lider). Nunca recibe una hora.

El PIN se guarda como HMAC-SHA256 con PIN_PEPPER, una clave propia en el entorno del servidor:
determinista por empresa para que la base impida repetidos (UNIQUE company_id, pin_hash), e inutil
sin la clave si se filtra la base. Un hash sin clave de 10.000 valores posibles se romperia al
instante. No depende del secreto JWT: rotarlo no toca los PIN. Sin PIN_PEPPER no hay respaldo con otra
clave: generar y marcar responden 503. Cambiar PIN_PEPPER si invalida todos los PIN.

El bloqueo (5 fallos = 15 min) se cuenta por usuario lider y operacion, en la base: un identificador
de equipo guardado en el navegador se borra con limpiar los datos y el limite dejaria de existir.
Un acierto NO borra los fallos, para que nadie pueda alternar su PIN con intentos ajenos.

Toda consulta filtra por company_id.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import open_shift_alert, reports_board, us_time

log = logging.getLogger("clonexa.lider_pin")

CHANNEL = "panel_pin"
MAX_FAILURES = 5
LOCK_MINUTES = 15
SUMMARY_MAX = 2000
PEPPER_ENV = "PIN_PEPPER"
PEPPER_MIN_LENGTH = 32
ACTIONS = {"start": "/entrada", "pause": "/pausa", "resume": "/retomar", "end": "/salida"}
NEEDS_LOCATION = "Activa la ubicación de este equipo"
NOTICE = {
    "es": "Tu turno fue finalizado por tu líder a las {time}.",
    "en": "Your shift was ended by your lead at {time}.",
    "fr": "Votre service a été terminé par votre responsable à {time}.",
}


class Denied(Exception):
    """Lo que el panel le muestra a quien marca. status: 422 PIN, 423 bloqueo, 409 estado, 403 otra operacion."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ------------------------------------------------------------------ reglas puras
def pin_hash(company_id: Any, pin: str) -> str:
    pepper = os.environ.get(PEPPER_ENV, "")
    if len(pepper) < PEPPER_MIN_LENGTH:  # nunca con otra clave: esos PIN dejarian de servir al configurarla
        log.error("%s no esta configurada: el PIN de marcacion no funciona.", PEPPER_ENV)
        raise Denied(503, "El PIN de marcación no está disponible. Avísale al administrador.")
    return hmac.new(pepper.encode(), f"punch-pin|{str(company_id).lower()}|{pin}".encode(), hashlib.sha256).hexdigest()


def well_formed(pin: Any) -> bool:
    return isinstance(pin, str) and bool(re.fullmatch(r"[0-9]{4}", pin))


def weak(pin: str) -> bool:
    """Que un PIN generado no sea de los que se adivinan primero."""
    return len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210"


def location_of(body: Any) -> dict:
    """Sin una ubicacion real del equipo no se marca."""
    try:
        lat, lng = float(body.latitude), float(body.longitude)
    except (TypeError, ValueError):
        raise Denied(422, NEEDS_LOCATION) from None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        raise Denied(422, NEEDS_LOCATION)
    accuracy = getattr(body, "accuracy", None)
    return {"latitude": lat, "longitude": lng, "accuracy": float(accuracy) if isinstance(accuracy, (int, float)) else None}


def state_of(status: Any, started: Optional[datetime], limit_hours: float, now: datetime) -> str:
    """El semaforo de la pantalla del PIN, con el mismo limite que CRM Campo."""
    if status not in ("working", "on_break"):
        return "no_shift"
    if started is not None and open_shift_alert.hours_open(open_shift_alert.aware(started), now) >= limit_hours:
        return "to_confirm"
    return str(status)


def clock_text(place: dict, when: datetime) -> str:
    local = when.astimezone(us_time.zone(place["timezone"]))
    return f"{local:%H:%M} {us_time.abbr(place['timezone'], when)}"


# ------------------------------------------------------------------ Workforce
async def status(db: AsyncSession, company_id: Any) -> dict[str, dict]:
    """Por empleado: si tiene PIN y si tiene Telegram. Nunca el PIN ni su hash."""
    rows = (await db.execute(text("""
        SELECT e.id::text AS id, COALESCE(e.telegram_user_id::text, '') <> '' AS has_telegram, p.employee_id IS NOT NULL AS has_pin
        FROM employees e LEFT JOIN employee_punch_pins p ON p.company_id = e.company_id AND p.employee_id = e.id
        WHERE e.company_id = CAST(:c AS uuid)
    """), {"c": str(company_id)})).mappings().all()
    return {r["id"]: {"has_pin": bool(r["has_pin"]), "has_telegram": bool(r["has_telegram"])} for r in rows}


async def _employee(db: AsyncSession, company_id: Any, employee_id: Any) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT id::text AS id, COALESCE(full_name, '') AS name, COALESCE(status, 'active') AS status, work_location_id::text AS work_location_id,
               COALESCE(telegram_user_id::text, '') AS telegram_user_id
        FROM employees WHERE company_id = CAST(:c AS uuid) AND id = CAST(:e AS uuid)
    """), {"c": str(company_id), "e": str(employee_id)})).mappings().first()
    return dict(row) if row else None


async def _audit(db: AsyncSession, company_id: Any, person: dict, action: str, actor: str) -> None:
    await db.execute(text("""
        INSERT INTO employee_punch_pin_audit (company_id, employee_id, employee_name, action, actor)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :n, :a, :by)
    """), {"c": str(company_id), "e": person["id"], "n": person["name"][:200], "a": action, "by": str(actor or "")[:200]})


async def generate(db: AsyncSession, company_id: Any, employee_id: Any, actor: str) -> dict:
    """Genera un PIN nuevo, unico en la empresa. Es la UNICA vez que el PIN sale del servidor."""
    person = await _employee(db, company_id, employee_id)
    if not person:
        raise Denied(404, "Esa persona no es de esta empresa.")
    if str(person["status"]).strip().lower() not in ("active", "activo"):
        raise Denied(422, "Esa persona no está activa.")
    if not person["work_location_id"]:
        raise Denied(422, "Asigna primero un lugar de trabajo: el PIN solo sirve en el panel de su operación.")
    params = {"c": str(company_id), "e": person["id"], "by": str(actor or "")[:200]}
    for _ in range(50):
        pin = f"{secrets.randbelow(10000):04d}"
        if weak(pin):
            continue
        try:
            async with db.begin_nested():
                await db.execute(text("""
                    INSERT INTO employee_punch_pins (company_id, employee_id, pin_hash, created_by, created_at)
                    VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :h, :by, now())
                    ON CONFLICT (company_id, employee_id) DO UPDATE SET pin_hash = EXCLUDED.pin_hash, created_by = EXCLUDED.created_by, created_at = now()
                """), {**params, "h": pin_hash(company_id, pin)})
        except IntegrityError:
            continue  # ya es de otra persona de la empresa
        await _audit(db, company_id, person, "generated", actor)
        await db.commit()
        return {"pin": pin, "employee_id": person["id"], "name": person["name"]}
    await db.rollback()
    raise Denied(409, "No se pudo generar un PIN libre. Intenta de nuevo.")


async def remove(db: AsyncSession, company_id: Any, employee_id: Any, actor: str) -> dict:
    person = await _employee(db, company_id, employee_id)
    if not person:
        raise Denied(404, "Esa persona no es de esta empresa.")
    removed = (await db.execute(text("""
        DELETE FROM employee_punch_pins WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) RETURNING employee_id
    """), {"c": str(company_id), "e": person["id"]})).first()
    if removed:
        await _audit(db, company_id, person, "removed", actor)
    await db.commit()
    return {"removed": bool(removed)}


# ------------------------------------------------------------------ intentos
async def _serialize(db: AsyncSession, key: str) -> None:
    """Un intento a la vez por lider y operacion, para que 5 sean 5 aunque lleguen juntos. Se suelta
    al confirmar o revertir."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key})


async def _check_lock(db: AsyncSession, company_id: Any, place_id: str, device: str, now: datetime) -> None:
    until = (await db.execute(text("""
        SELECT locked_until FROM lider_pin_attempts
        WHERE company_id = CAST(:c AS uuid) AND work_location_id = CAST(:l AS uuid) AND device_key = :d
    """), {"c": str(company_id), "l": place_id, "d": device})).scalar()
    until = open_shift_alert.aware(until)
    if until and until > now:
        minutes = max(1, int((until - now).total_seconds() // 60) + 1)
        raise Denied(423, f"Demasiados intentos. Este equipo queda bloqueado {minutes} min.")


async def _fail(db: AsyncSession, company_id: Any, place_id: str, device: str, now: datetime, message: Optional[str] = None) -> Denied:
    """Suma el fallo, lo confirma y devuelve el error que toca."""
    row = (await db.execute(text("""
        INSERT INTO lider_pin_attempts AS a (company_id, work_location_id, device_key, failures, first_failure_at, locked_until)
        VALUES (CAST(:c AS uuid), CAST(:l AS uuid), :d, 1, :now, NULL)
        ON CONFLICT (company_id, work_location_id, device_key) DO UPDATE SET
            failures = CASE WHEN a.first_failure_at IS NULL OR a.first_failure_at <= :window OR a.locked_until <= :now THEN 1 ELSE a.failures + 1 END,
            locked_until = CASE WHEN a.first_failure_at IS NULL OR a.first_failure_at <= :window OR a.locked_until <= :now THEN NULL
                                WHEN a.failures + 1 >= :max THEN CAST(:until AS timestamptz) ELSE NULL END,
            first_failure_at = CASE WHEN a.first_failure_at IS NULL OR a.first_failure_at <= :window OR a.locked_until <= :now THEN :now ELSE a.first_failure_at END
        RETURNING failures, locked_until
    """), {"c": str(company_id), "l": place_id, "d": device, "now": now, "window": now - timedelta(minutes=LOCK_MINUTES), "max": MAX_FAILURES,
           "until": now + timedelta(minutes=LOCK_MINUTES)})).mappings().first()
    await db.commit()
    if row["locked_until"]:
        return Denied(423, f"Demasiados intentos. Este equipo queda bloqueado {LOCK_MINUTES} min.")
    return Denied(422, message or f"PIN incorrecto. Intentos restantes: {MAX_FAILURES - int(row['failures'])}.")


async def check_pin(db: AsyncSession, company_id: Any, place: dict, device: str, pin: Any, now: datetime) -> dict:
    """La persona dueña del PIN, si es de ESTA operacion. PIN de otra operacion tambien cuenta como
    fallo: si no, serviria para descubrir PIN validos sin limite."""
    await _serialize(db, f"pin|{company_id}|{place['id']}|{device}")
    await _check_lock(db, company_id, place["id"], device, now)
    if not well_formed(pin):
        raise await _fail(db, company_id, place["id"], device, now)
    row = (await db.execute(text("""
        SELECT e.id::text AS id, COALESCE(e.full_name, '') AS name, COALESCE(e.role, '') AS role, COALESCE(e.status, 'active') AS status,
               e.work_location_id::text AS work_location_id, s.status AS shift_status, s.check_in_at
        FROM employee_punch_pins p
        JOIN employees e ON e.id = p.employee_id AND e.company_id = p.company_id
        LEFT JOIN workforce_attendance_status s ON s.company_id = e.company_id AND s.employee_id = e.id
        WHERE p.company_id = CAST(:c AS uuid) AND p.pin_hash = :h
    """), {"c": str(company_id), "h": pin_hash(company_id, pin)})).mappings().first()
    if not row or str(row["status"]).strip().lower() not in ("active", "activo"):
        raise await _fail(db, company_id, place["id"], device, now)
    if row["work_location_id"] != place["id"]:
        raise await _fail(db, company_id, place["id"], device, now, f"Este PIN no es de {place['name']}")
    return dict(row)


def possible_actions(current: Any) -> list[str]:
    """Las mismas transiciones del bot."""
    from app.api.v1.endpoints import bots

    return [key for key, command in ACTIONS.items() if bots._validate_turn_transition(current=current, command_config=bots.TELEGRAM_COMMANDS[command], language="es")[0]]


async def verify(db: AsyncSession, company_id: Any, place: dict, device: str, pin: Any, now: Optional[datetime] = None) -> dict:
    from app.api.v1.endpoints import bots

    now = now or datetime.now(timezone.utc)
    person = await check_pin(db, company_id, place, device, pin, now)
    limit = await reports_board._policy_hours(db, company_id)
    current = await bots._get_current_attendance_status(db, UUID(str(company_id)), UUID(person["id"]))
    await db.commit()
    return {"ok": True, "employee": {"name": person["name"].strip() or "Colaborador", "role": person["role"],
                                     "state": state_of(person["shift_status"], person["check_in_at"], limit, now), "actions": possible_actions(current)}}


async def _clear_bot_pending(db: AsyncSession, company_id: Any, employee_id: str) -> None:
    """Si la persona dejo a medias "Finalizar" en el bot, su siguiente mensaje no debe cerrar otra vez."""
    if (await db.execute(text("SELECT to_regclass('company_telegram_pending_actions') IS NOT NULL"))).scalar():
        await db.execute(text("""
            DELETE FROM company_telegram_pending_actions
            WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND action IN ('end_shift_summary', 'gps_punch')
        """), {"c": str(company_id), "e": employee_id})


async def mark(db: AsyncSession, company_id: Any, place: dict, leader: dict, pin: Any, action: Any, summary: Any, body: Any, language: str = "es") -> dict:
    """La marcacion con PIN. Revisa el PIN en cada llamada: el navegador no recibe ninguna credencial
    que dure mas que su pantalla de 20 s."""
    from app.api.v1.endpoints import bots
    from app.models.core import Employee
    from app.models.workforce_attendance import WorkforceAttendanceEvent

    now = datetime.now(timezone.utc)
    person = await check_pin(db, company_id, place, leader["device"], pin, now)
    if action not in ACTIONS:
        await db.rollback()
        raise Denied(422, "Esa acción no existe.")
    try:
        where = location_of(body)
    except Denied:
        await db.rollback()
        raise
    note = str(summary or "").strip()[:SUMMARY_MAX]
    if action == "end" and not note:
        await db.rollback()
        raise Denied(422, "Escribe el resumen de la jornada.")
    cid, eid = UUID(str(company_id)), UUID(person["id"])
    await _serialize(db, f"punch|{cid}|{eid}")
    employee = await db.get(Employee, eid)
    current = await bots._get_current_attendance_status(db, cid, eid)
    config = bots.TELEGRAM_COMMANDS[ACTIONS[action]]
    ok, error = bots._validate_turn_transition(current=current, command_config=config, language=language)
    if not ok:
        await db.rollback()
        raise Denied(409, error or "Esa acción no es posible ahora.")

    geo = await bots._validate_gps_location_for_company(db, company_id=cid, latitude=where["latitude"], longitude=where["longitude"], employee_id=eid)
    source_ref = f"{CHANNEL}:{uuid4().hex}"
    leader_note = {"panel_leader": leader["name"], "panel_leader_user_id": leader["user_id"]}
    db.add(WorkforceAttendanceEvent(  # como el bot: el CRM Campo del portal lee la ubicacion de este evento
        company_id=cid, employee_id=eid, event_type="gps_location", event_label="Ubicación GPS", employee_name=employee.full_name, employee_role=employee.role,
        status_after="registered", source=CHANNEL, source_channel=CHANNEL, source_ref=f"{source_ref}:gps", module_code="gps", detail=f"{where['latitude']},{where['longitude']}",
        notes="Ubicación del equipo del líder.", latitude=Decimal(str(where["latitude"])), longitude=Decimal(str(where["longitude"])),
        payload_json={"latitude": where["latitude"], "longitude": where["longitude"], "horizontal_accuracy": where["accuracy"], **leader_note, **geo},
        metadata_json={"source": CHANNEL, "module_code": "gps", **geo}, occurred_at=now))
    punch = {"located_at": now.isoformat(), "latitude": where["latitude"], "longitude": where["longitude"], "horizontal_accuracy": where["accuracy"],
             "gps_status": geo.get("gps_status") or "unconfigured", "gps_status_label": geo.get("gps_status_label") or "Sin perímetro",
             "matched_perimeter_name": geo.get("matched_perimeter_name"), "device": "leader", **({"geo_source": geo["geo_source"]} if geo.get("geo_source") else {})}
    created, _reply = await bots._create_bot_attendance_event(  # _reply puede traer pago: no se muestra en el equipo del lider
        db, bot=SimpleNamespace(id=None, bot_username=None), employee=employee, update={}, message={}, command=ACTIONS[action], args=note, command_config=config,
        language=language, punch_location=punch, origin={"channel": CHANNEL, "source_ref": source_ref, "payload": leader_note})
    if not created:
        await db.rollback()
        raise Denied(409, "Esa acción no es posible ahora.")
    if action == "end":
        await _clear_bot_pending(db, cid, person["id"])
    await db.commit()
    return {"ok": True, "action": action, "name": person["name"].strip() or "Colaborador", "at": clock_text(place, now)}


# ------------------------------------------------------------------ el lider finaliza un turno
async def _notify(db: AsyncSession, company_id: Any, telegram_user_id: str, at: str) -> bool:
    """Aviso por el bot en el idioma de la persona. Si falla, el turno igual queda cerrado."""
    if not telegram_user_id:
        return False
    from app.api.v1.endpoints import bots
    from app.services import bot_punch_gps

    try:
        token = await bot_punch_gps.bot_token(db, str(company_id))
        if not token:
            return False
        language = await bots._get_user_language(db, UUID(str(company_id)), telegram_user_id)
        await bots._send_telegram_message(token, telegram_user_id, NOTICE.get(language, NOTICE["es"]).format(time=at))
        return True
    except Exception as exc:
        await db.rollback()
        log.warning("Aviso de turno finalizado no se pudo enviar (%s): %s", company_id, type(exc).__name__)
        return False


async def finish(db: AsyncSession, company_id: Any, place: dict, leader: dict, employee_id: Any, body: Any, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    where = location_of(body)
    person = await _employee(db, company_id, employee_id)
    if not person or person["work_location_id"] != place["id"]:
        raise Denied(403, f"Esa persona no es de {place['name']}.")
    limit = await reports_board._policy_hours(db, company_id)
    try:
        closed = await open_shift_alert.close_shift(
            db, company_id, person["id"], {"note": f"Finalizado por {leader['name']}"}, actor=leader["name"], actor_user_id=leader["user_id"], now_utc=now,
            leader={"max_hours": limit, **where})
    except open_shift_alert.Invalid as exc:
        await db.rollback()
        raise Denied(409, exc.message) from None
    await _clear_bot_pending(db, company_id, person["id"])
    await db.commit()
    at = clock_text(place, now)
    return {"ok": True, "name": closed["employee_name"], "at": at, "original_status": closed["original_status"],
            "notified": await _notify(db, company_id, person["telegram_user_id"], at)}


# ------------------------------------------------------------------ 071A: cerrar un turno Fuera de horario
CLOSE_CHOICES = ("scheduled", "now")


async def close_out_of_schedule(db: AsyncSession, company_id: Any, place: dict, leader: dict, employee_id: Any, body: Any,
                                now: Optional[datetime] = None) -> dict:
    """Solo con work_schedule y solo un turno Fuera de horario de SU operacion. La hora la decide el
    servidor: la salida programada de su horario o la hora actual; el lider nunca escribe otra."""
    from app.services import work_schedule

    now = now or datetime.now(timezone.utc)
    if not await work_schedule.is_on(db, company_id):
        raise Denied(404, "El horario de la semana no está activo para esta empresa.")
    body = body if isinstance(body, dict) else {}
    if body.get("confirmed") is not True:
        raise Denied(422, "Confirma el cierre dos veces antes de guardarlo.")
    choice = str(body.get("choice") or "")
    if choice not in CLOSE_CHOICES:
        raise Denied(422, "Elige la salida programada o la hora actual.")
    try:
        code, detail, note = work_schedule.close_reason(body)
    except work_schedule.Invalid as exc:
        raise Denied(422, exc.message) from None
    person = await _employee(db, company_id, employee_id)
    if not person or person["work_location_id"] != place["id"]:
        raise Denied(403, f"Esa persona no es de {place['name']}.")
    ctx = await work_schedule.shift_context(db, company_id, person["id"], now)
    if ctx is None:
        raise Denied(409, "Esa persona no tiene un turno abierto.")
    if not ctx["out_of_schedule"]:
        raise Denied(409, "Solo se cierran desde aquí los turnos Fuera de horario.")
    sch = ctx.get("schedule") or {}
    if choice == "scheduled":
        if not sch.get("end") or sch["end"] > now:
            raise Denied(409, "Su salida programada aún no llega: usa la hora actual.")
        end_at = sch["end"]
    else:
        end_at = now
    origin = {"channel": open_shift_alert.LEADER_CHANNEL, "label": "Turno cerrado por el líder", "source": open_shift_alert.LEADER_CHANNEL,
              "payload": {"closed_by_leader": True, "leader_choice": choice}}
    audit = {"reason_code": code, "reason_detail": detail, "schedule": {**work_schedule.schedule_audit(ctx), "choice": choice},
             "closed_via": "lider"}
    try:
        closed = await open_shift_alert.close_shift(db, company_id, person["id"], {"end_at": end_at.isoformat(), "note": note}, actor=leader["name"],
                                                    actor_user_id=leader["user_id"], now_utc=now, origin=origin, audit=audit)
    except open_shift_alert.Invalid as exc:
        await db.rollback()
        raise Denied(409, exc.message) from None
    await _clear_bot_pending(db, company_id, person["id"])
    await db.commit()
    return {"ok": True, "name": closed["employee_name"], "at": clock_text(place, end_at), "choice": choice, "reason": note,
            "notified": await work_schedule.notify_closed(db, company_id, person["id"], end_at, place["timezone"], leader["name"])}
