"""Horario de la semana por operacion, aviso de salida del bot y cierre con motivo (071A).

Interruptor por empresa ``work_schedule`` (settings del modulo workforce), apagado por defecto.
Hoy solo VOLTAGE. Necesita work_locations (el horario es de cada operacion) y open_shift_alert
(el cierre de turnos del portal y su auditoria).

Reglas que este modulo sostiene en el servidor:
- Cada operacion tiene "Horario 1" y, si el dueño agrega, Horario 2, 3...: dias, entrada, salida y
  almuerzo de REFERENCIA en la hora local de la operacion (ET / CT), con dias puntuales distintos.
- El horario es por semana (lunes a domingo). Sin cambios para una semana, vale la ultima semana
  anterior guardada: cada semana copia la anterior sola. Una operacion sin nada guardado no tiene
  horario: el bot no le pregunta a nadie hasta que el dueño lo configure.
- Cada persona usa un horario (Horario 1 por defecto) y se evalua con el suyo.
- El almuerzo es solo de referencia: nunca se descuenta ni genera alertas. Las pausas solo cuentan
  cuando la persona las marca (eso lo sigue haciendo us_time, que no se toca aqui).
- Aviso del bot 15 min despues de SU salida con [Finalizar ahora] [Sigo trabajando]. "Sigo
  trabajando" pide el motivo y vuelve a preguntar cada 2 h. Sin respuesta en 30 min: "Fuera de
  horario" y un solo aviso al supervisor de su operacion (al rol dueño si no hay supervisor).
  Un turno que ya llevaba mas de STALE_HOURS pasado su horario cuando se mira por primera vez
  (turnos viejos al encender el interruptor) queda Fuera de horario en silencio: sin mensajes.
- El aviso de turno abierto de 15 h (open_shift_alert) sigue igual, como red de seguridad.
Toda consulta filtra por company_id.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("clonexa.work_schedule")

KEY = "work_schedule"
MODULE = "workforce"
LOOP_SECONDS = 60
PROMPT_AFTER_MINUTES = 15
NO_REPLY_MINUTES = 30
REASK_HOURS = 2
STALE_HOURS = 3
MAX_SLOTS = 6
REASON_MIN = 3
REASON_MAX = 500
DETAIL_MIN = 5
PENDING_ACTION = "work_schedule_reason"
CALLBACK_FINISH = "clx:ws:fin"
CALLBACK_WORKING = "clx:ws:sigo"
DAY_NAMES = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
DEFAULT_SLOT = {"slot": 1, "name": "Horario 1", "days": [0, 1, 2, 3, 4], "start": "07:00", "end": "17:00",
                "lunch_start": "12:00", "lunch_end": "13:00", "overrides": {}}
REASONS = {"olvido": "Olvidó finalizar", "salida_real": "Salida real confirmada", "otro": "Otro"}
OWNER_ROLES = {"company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"}
# Estados de un aviso: asked (preguntado), finish (toco Finalizar ahora), reason (toco Sigo
# trabajando y falta el motivo), working (dio el motivo; se repregunta en next_ask_at), out (Fuera
# de horario).
WAITING = ("asked", "finish", "reason")

TEXTS = {
    "es": {
        "ask": "⏰ Tu turno terminó a las {time} ¿Ya saliste?",
        "btn_finish": "Finalizar ahora", "btn_working": "Sigo trabajando",
        "why": "Escribe en un solo mensaje por qué sigues trabajando.",
        "thanks": "📝 Anotado. Te vuelvo a preguntar en 2 horas si tu turno sigue abierto.",
        "closed": "Tu turno fue cerrado a las {time} por {name}.",
        "boss": "⏰ Fuera de horario\n👤 {name}\n📍 {place}\n🕐 Salida programada: {time}\n\nNo respondió al aviso del bot. Si ya salió, cierra el turno en CRM Campo (Cerrar turno) o en el panel del líder.",
        "no_place": "Sin lugar asignado",
    },
    "en": {
        "ask": "⏰ Your shift ended at {time}. Did you already leave?",
        "btn_finish": "End now", "btn_working": "Still working",
        "why": "Write in one message why you are still working.",
        "thanks": "📝 Noted. I'll ask again in 2 hours if your shift is still open.",
        "closed": "Your shift was closed at {time} by {name}.",
        "boss": "⏰ Outside schedule\n👤 {name}\n📍 {place}\n🕐 Scheduled end: {time}\n\nThey did not answer the bot. If they already left, close the shift in CRM Campo (Close shift) or in the lead panel.",
        "no_place": "No work location",
    },
    "fr": {
        "ask": "⏰ Votre service s'est terminé à {time}. Êtes-vous déjà parti ?",
        "btn_finish": "Terminer maintenant", "btn_working": "Je continue",
        "why": "Écrivez en un seul message pourquoi vous continuez à travailler.",
        "thanks": "📝 Noté. Je vous redemande dans 2 heures si votre service est toujours ouvert.",
        "closed": "Votre service a été fermé à {time} par {name}.",
        "boss": "⏰ Hors horaire\n👤 {name}\n📍 {place}\n🕐 Fin prévue : {time}\n\nLa personne n'a pas répondu au bot. Si elle est partie, fermez le service dans CRM Campo ou dans le panneau du responsable.",
        "no_place": "Sans lieu de travail",
    },
}


class Invalid(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def tr(language: Any, key: str, **kwargs: Any) -> str:
    return TEXTS[language if language in TEXTS else "es"][key].format(**kwargs)


# ------------------------------------------------------------------ reglas puras
def zone(tz_name: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(tz_name or "America/New_York"))
    except Exception:
        return ZoneInfo("America/New_York")


def week_start(day: date) -> date:
    """El lunes de la semana de `day`."""
    return day - timedelta(days=day.weekday())


def parse_week(value: Any, today: date) -> date:
    if not value:
        return week_start(today)
    try:
        return week_start(date.fromisoformat(str(value)[:10]))
    except ValueError:
        raise Invalid("week", "Semana no válida.") from None


def parse_hhmm(value: Any) -> Optional[time]:
    raw = str(value or "").strip()
    try:
        hh, mm = raw.split(":")
        return time(int(hh), int(mm))
    except (ValueError, TypeError):
        return None


def hhmm(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def clock_label(value: Any, language: Any = "es") -> str:
    """'17:00' o un datetime local -> '5:00 p. m.' (es), '5:00 PM' (en), '17 h 00' (fr)."""
    t = value if isinstance(value, time) else (value.timetz() if isinstance(value, datetime) else parse_hhmm(value))
    if t is None:
        return "—"
    if language == "fr":
        return f"{t.hour} h {t.minute:02d}"
    h12 = t.hour % 12 or 12
    if language == "en":
        return f"{h12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"
    return f"{h12}:{t.minute:02d} {'a. m.' if t.hour < 12 else 'p. m.'}"


def local_clock(at: datetime, tz_name: Any, language: Any = "es") -> str:
    return clock_label(at.astimezone(zone(tz_name)), language)


def _clean_hours(raw: dict, where: str, *, lunch: bool) -> dict:
    start, end = parse_hhmm(raw.get("start")), parse_hhmm(raw.get("end"))
    if start is None or end is None:
        raise Invalid("slots", f"{where}: indica la entrada y la salida (HH:MM).")
    if start == end:
        raise Invalid("slots", f"{where}: la salida debe ser distinta de la entrada.")
    out = {"start": hhmm(start), "end": hhmm(end)}
    if lunch:
        ls, le = parse_hhmm(raw.get("lunch_start")), parse_hhmm(raw.get("lunch_end"))
        if (ls is None) != (le is None) or (raw.get("lunch_start") and ls is None) or (raw.get("lunch_end") and le is None):
            raise Invalid("slots", f"{where}: el almuerzo necesita inicio y fin (HH:MM), o dejarlo vacío.")
        if ls is not None and le <= ls:
            raise Invalid("slots", f"{where}: el fin del almuerzo debe ser después del inicio.")
        out.update({"lunch_start": hhmm(ls) if ls else None, "lunch_end": hhmm(le) if le else None})
    return out


def clean_slots(raw: Any, week: date) -> list[dict]:
    """Lo que manda el portal -> la lista guardada. Los dias puntuales fuera de esa semana se
    descartan (no pasan a la semana siguiente). Los numeros se reasignan 1, 2, 3..."""
    items = raw if isinstance(raw, list) else []
    if not items:
        raise Invalid("slots", "Agrega al menos un horario.")
    if len(items) > MAX_SLOTS:
        raise Invalid("slots", f"Máximo {MAX_SLOTS} horarios por operación.")
    days_of_week = {(week + timedelta(days=i)).isoformat() for i in range(7)}
    out = []
    for index, item in enumerate(items, start=1):
        item = item if isinstance(item, dict) else {}
        name = f"Horario {index}"
        try:
            days = sorted({int(d) for d in item.get("days") or []})
        except (TypeError, ValueError):
            raise Invalid("slots", f"{name}: días no válidos.") from None
        if not days or any(d < 0 or d > 6 for d in days):
            raise Invalid("slots", f"{name}: elige al menos un día.")
        slot = {"slot": index, "name": name, "days": days, **_clean_hours(item, name, lunch=True), "overrides": {}}
        overrides = item.get("overrides") if isinstance(item.get("overrides"), dict) else {}
        for key, value in sorted(overrides.items()):
            if key not in days_of_week or not isinstance(value, dict):
                continue
            label = f"{name}, {key}"
            slot["overrides"][key] = {"off": True} if value.get("off") is True else _clean_hours(value, label, lunch=False)
        out.append(slot)
    return out


def slot_of(slots: list[dict], number: Any) -> dict:
    try:
        wanted = int(number or 1)
    except (TypeError, ValueError):
        wanted = 1
    return next((s for s in slots if int(s.get("slot") or 0) == wanted), slots[0] if slots else DEFAULT_SLOT)


def day_plan(slot: dict, day: date) -> Optional[dict]:
    """Entrada y salida de un dia, o None si ese dia no trabaja. Un dia puntual manda."""
    override = (slot.get("overrides") or {}).get(day.isoformat())
    if isinstance(override, dict):
        return None if override.get("off") else {"start": override["start"], "end": override["end"], "special": True}
    if day.weekday() not in (slot.get("days") or []):
        return None
    return {"start": slot["start"], "end": slot["end"], "special": False,
            "lunch_start": slot.get("lunch_start"), "lunch_end": slot.get("lunch_end")}


def scheduled_end(slot: dict, check_in: datetime, tz_name: Any) -> Optional[datetime]:
    """La salida programada del turno que empezo en `check_in`, en UTC; None si ese dia no
    trabaja o si entro despues de su hora de salida (trabajo fuera de su horario)."""
    tz = zone(tz_name)
    local = check_in.astimezone(tz)
    plan = day_plan(slot, local.date())
    if not plan:
        return None
    start, end = parse_hhmm(plan["start"]), parse_hhmm(plan["end"])
    end_at = datetime.combine(local.date(), end, tz)
    if end <= start:  # turno de noche: sale al dia siguiente
        end_at += timedelta(days=1)
    if check_in >= end_at:
        return None
    return end_at.astimezone(timezone.utc)


def week_days(slot: dict, week: date) -> list[dict]:
    """Los 7 dias de la semana de un horario, para la pantalla y el panel del lider."""
    out = []
    for i in range(7):
        day = week + timedelta(days=i)
        plan = day_plan(slot, day)
        out.append({"date": day.isoformat(), "weekday": i, "name": DAY_NAMES[i], "off": plan is None,
                    "start": plan["start"] if plan else None, "end": plan["end"] if plan else None,
                    "special": bool(plan and plan["special"]) or day.isoformat() in (slot.get("overrides") or {}),
                    "label": f"{clock_label(plan['start'])} – {clock_label(plan['end'])}" if plan else "Libre"})
    return out


def close_reason(body: Any) -> tuple[str, str, str]:
    """(codigo, detalle, nota del cierre). Motivo obligatorio; "Otro" pide detalle."""
    body = body if isinstance(body, dict) else {}
    code = str(body.get("reason_code") or "").strip()
    if code not in REASONS:
        raise Invalid("reason_code", "Elige el motivo del cierre.")
    detail = " ".join(str(body.get("reason_detail") or "").split())[:REASON_MAX]
    if code == "otro" and len(detail) < DETAIL_MIN:
        raise Invalid("reason_detail", f"Escribe el detalle del motivo (mínimo {DETAIL_MIN} caracteres).")
    note = f"Otro: {detail}" if code == "otro" else (f"{REASONS[code]} · {detail}" if detail else REASONS[code])
    return code, detail, note


def default_end(end_at: Optional[datetime], now: datetime) -> datetime:
    """Hora de salida por defecto del cierre: la programada si ya paso; si no, ahora."""
    return end_at if end_at is not None and end_at <= now else now


def prompt_keyboard(language: Any) -> dict:
    return {"inline_keyboard": [[{"text": tr(language, "btn_finish"), "callback_data": CALLBACK_FINISH},
                                 {"text": tr(language, "btn_working"), "callback_data": CALLBACK_WORKING}]]}


def settings_dict(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _json(raw: Any, fallback: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return fallback
    return raw if raw is not None else fallback


def aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def iso(value: Any) -> Optional[str]:
    value = aware(value)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


# ------------------------------------------------------------------ interruptor
async def is_on(db: Optional[AsyncSession], company_id: Any) -> bool:
    """Nunca falla: ante cualquier error, apagado (todo sigue como antes)."""
    if db is None or not company_id:
        return False
    try:
        raw = (await db.execute(text("""
            SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:c AS uuid) AND lower(m.code) = :m AND COALESCE(cm.enabled, true) IS TRUE
            LIMIT 1
        """), {"c": str(company_id), "m": MODULE})).scalar()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return False
    return settings_dict(raw).get(KEY) is True


async def companies_on(db: AsyncSession) -> list[str]:
    rows = (await db.execute(text("""
        SELECT cm.company_id::text FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE lower(m.code) = :m AND COALESCE(cm.enabled, true) IS TRUE AND (cm.settings::jsonb ->> :k) = 'true'
    """), {"m": MODULE, "k": KEY})).all()
    return [str(r[0]) for r in rows]


# ------------------------------------------------------------------ horario de la semana
async def location(db: AsyncSession, company_id: Any, location_id: Any) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT id::text AS id, name, timezone FROM work_locations WHERE company_id = CAST(:c AS uuid) AND id::text = :l
    """), {"c": str(company_id), "l": str(location_id)})).mappings().first()
    return dict(row) if row else None


async def week(db: AsyncSession, company_id: Any, location_id: Any, start: date) -> dict:
    """El horario de una operacion para la semana del lunes `start`: el de esa semana, o el de la
    ultima semana anterior guardada (copia automatica). Sin nada guardado: configured False y el
    Horario 1 de ejemplo para llenar el formulario."""
    row = (await db.execute(text("""
        SELECT week_start, slots, updated_by, updated_at FROM work_schedule_weeks
        WHERE company_id = CAST(:c AS uuid) AND work_location_id = CAST(:l AS uuid) AND week_start <= :w
        ORDER BY week_start DESC LIMIT 1
    """), {"c": str(company_id), "l": str(location_id), "w": start})).mappings().first()
    if not row:
        return {"week_start": start.isoformat(), "configured": False, "source": "none", "copied_from": None,
                "slots": [json.loads(json.dumps(DEFAULT_SLOT))], "updated_by": None, "updated_at": None}
    saved = row["week_start"]
    slots = [s for s in _json(row["slots"], []) if isinstance(s, dict)] or [json.loads(json.dumps(DEFAULT_SLOT))]
    if saved != start:  # copiada: los dias puntuales eran de esa otra semana
        slots = [{**s, "overrides": {}} for s in slots]
    return {"week_start": start.isoformat(), "configured": True, "source": "week" if saved == start else "copied",
            "copied_from": None if saved == start else saved.isoformat(), "slots": slots,
            "updated_by": row["updated_by"], "updated_at": iso(row["updated_at"])}


async def save_week(db: AsyncSession, company_id: Any, location_id: Any, start: date, raw_slots: Any, *,
                    actor: str, actor_user_id: Optional[str]) -> dict:
    slots = clean_slots(raw_slots, start)
    await db.execute(text("""
        INSERT INTO work_schedule_weeks (company_id, work_location_id, week_start, slots, updated_by, updated_by_user_id, updated_at)
        VALUES (CAST(:c AS uuid), CAST(:l AS uuid), :w, CAST(:s AS jsonb), :by, CAST(:uid AS uuid), now())
        ON CONFLICT (company_id, work_location_id, week_start)
        DO UPDATE SET slots = EXCLUDED.slots, updated_by = EXCLUDED.updated_by, updated_by_user_id = EXCLUDED.updated_by_user_id, updated_at = now()
    """), {"c": str(company_id), "l": str(location_id), "w": start, "s": json.dumps(slots), "by": str(actor or "")[:200] or None,
           "uid": actor_user_id})
    await db.commit()
    return await week(db, company_id, location_id, start)


async def employee_slots(db: AsyncSession, company_id: Any) -> dict[str, int]:
    rows = (await db.execute(text("""
        SELECT employee_id::text, slot FROM employee_schedule_slots WHERE company_id = CAST(:c AS uuid)
    """), {"c": str(company_id)})).all()
    return {str(r[0]): int(r[1] or 1) for r in rows}


async def set_employee_slot(db: AsyncSession, company_id: Any, employee_id: Any, slot: Any, *, actor: str) -> int:
    try:
        number = int(slot)
    except (TypeError, ValueError):
        raise Invalid("slot", "Horario no válido.") from None
    if number < 1 or number > MAX_SLOTS:
        raise Invalid("slot", "Horario no válido.")
    found = (await db.execute(text("""
        SELECT 1 FROM employees WHERE company_id = CAST(:c AS uuid) AND id = CAST(:e AS uuid)
    """), {"c": str(company_id), "e": str(employee_id)})).first()
    if not found:
        raise Invalid("employee_id", "Esa persona no es de esta empresa.")
    await db.execute(text("""
        INSERT INTO employee_schedule_slots (company_id, employee_id, slot, updated_by, updated_at)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :s, :by, now())
        ON CONFLICT (company_id, employee_id) DO UPDATE SET slot = EXCLUDED.slot, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": str(company_id), "e": str(employee_id), "s": number, "by": str(actor or "")[:200] or None})
    await db.commit()
    return number


async def location_people(db: AsyncSession, company_id: Any, location_id: Any) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT e.id::text AS id, COALESCE(e.full_name, '') AS name, COALESCE(s.slot, 1) AS slot
        FROM employees e LEFT JOIN employee_schedule_slots s ON s.company_id = e.company_id AND s.employee_id = e.id
        WHERE e.company_id = CAST(:c AS uuid) AND e.work_location_id::text = :l
          AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')
        ORDER BY lower(COALESCE(e.full_name, ''))
    """), {"c": str(company_id), "l": str(location_id)})).mappings().all()
    return [{"id": r["id"], "name": r["name"].strip(), "slot": int(r["slot"] or 1)} for r in rows]


def week_out(data: dict, place: dict) -> dict:
    start = date.fromisoformat(data["week_start"])
    return {**data, "week_end": (start + timedelta(days=6)).isoformat(), "location": place,
            "slots": [{**s, "days_view": week_days(s, start)} for s in data["slots"]]}


class Schedules:
    """Horarios ya leidos en una pasada (una consulta por operacion y semana)."""

    def __init__(self, db: AsyncSession, company_id: Any):
        self.db, self.cid = db, str(company_id)
        self.weeks: dict[tuple[str, date], dict] = {}
        self.slots: Optional[dict[str, int]] = None

    async def of_shift(self, shift: dict) -> Optional[dict]:
        """{end, slot, slot_name, week_start} del turno, o None si su operacion no tiene horario o
        ese dia no le toca."""
        place, started = shift.get("work_location_id"), aware(shift.get("check_in_at"))
        if not place or started is None:
            return None
        if self.slots is None:
            self.slots = await employee_slots(self.db, self.cid)
        start = week_start(started.astimezone(zone(shift.get("tz"))).date())
        key = (str(place), start)
        if key not in self.weeks:
            self.weeks[key] = await week(self.db, self.cid, place, start)
        data = self.weeks[key]
        if not data["configured"]:
            return None
        slot = slot_of(data["slots"], self.slots.get(str(shift["employee_id"]), 1))
        end_at = scheduled_end(slot, started, shift.get("tz"))
        if end_at is None:
            return None
        return {"end": end_at, "slot": int(slot["slot"]), "slot_name": slot["name"], "week_start": start.isoformat(),
                "plan": day_plan(slot, started.astimezone(zone(shift.get("tz"))).date())}


# ------------------------------------------------------------------ avisos por turno
async def prompts(db: AsyncSession, company_id: Any) -> dict[tuple[str, datetime], dict]:
    rows = (await db.execute(text("""
        SELECT employee_id::text AS employee_id, shift_started_at, scheduled_end_at, slot, state, asked_at, asks, next_ask_at,
               reasons, out_of_schedule_at, boss_notified_at, silent
        FROM shift_schedule_prompts WHERE company_id = CAST(:c AS uuid) AND updated_at > now() - interval '30 days'
    """), {"c": str(company_id)})).mappings().all()
    return {(r["employee_id"], aware(r["shift_started_at"])): {**dict(r), "reasons": _json(r["reasons"], [])} for r in rows}


async def flags(db: AsyncSession, company_id: Any, now: Optional[datetime] = None) -> dict[str, dict]:
    """Por empleado con turno abierto: salida programada, horario y si esta Fuera de horario."""
    from app.services import open_shift_alert

    now = now or datetime.now(timezone.utc)
    schedules = Schedules(db, company_id)
    found = await prompts(db, company_id)
    out = {}
    for shift in await open_shift_alert.open_shifts(db, company_id, now_utc=now):
        sch = await schedules.of_shift(shift)
        row = found.get((shift["employee_id"], shift["check_in_at"]))
        reasons = (row or {}).get("reasons") or []
        out[shift["employee_id"]] = {
            "shift_started_at": iso(shift["check_in_at"]), "tz": shift["tz"],
            "scheduled_end_at": iso(sch["end"]) if sch else None,
            "scheduled_end_label": local_clock(sch["end"], shift["tz"]) if sch else None,
            "slot": sch["slot"] if sch else None, "slot_name": sch["slot_name"] if sch else None,
            "out_of_schedule": bool(row and row.get("out_of_schedule_at")),
            "state": (row or {}).get("state"), "reason": reasons[-1]["text"] if reasons else None,
        }
    return out


async def _claim_new(db: AsyncSession, cid: str, shift: dict, sch: dict, now: datetime, stale: bool) -> bool:
    row = (await db.execute(text("""
        INSERT INTO shift_schedule_prompts (company_id, employee_id, shift_started_at, scheduled_end_at, slot, state, asked_at, asks,
                                            out_of_schedule_at, silent, updated_at)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :s, :end, :slot, :state, :now, :asks, :out, :silent, :now)
        ON CONFLICT (company_id, employee_id, shift_started_at) DO NOTHING
        RETURNING employee_id
    """), {"c": cid, "e": shift["employee_id"], "s": shift["check_in_at"], "end": sch["end"], "slot": sch["slot"],
           "state": "out" if stale else "asked", "now": now, "asks": 0 if stale else 1, "out": now if stale else None,
           "silent": stale})).first()
    await db.commit()
    return row is not None


async def _timeout(db: AsyncSession, cid: str, row: dict, now: datetime) -> bool:
    """Sin respuesta en 30 min: Fuera de horario. True si hay que avisar al jefe (una sola vez)."""
    done = (await db.execute(text("""
        UPDATE shift_schedule_prompts
           SET state = 'out', out_of_schedule_at = COALESCE(out_of_schedule_at, :now),
               boss_notified_at = COALESCE(boss_notified_at, CASE WHEN silent THEN NULL ELSE :now END), updated_at = :now
         WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND shift_started_at = :s
           AND state IN ('asked', 'finish', 'reason') AND asked_at = :asked
        RETURNING (boss_notified_at = :now) AS notify
    """), {"c": cid, "e": row["employee_id"], "s": row["shift_started_at"], "asked": row["asked_at"], "now": now})).first()
    await db.commit()
    return bool(done and done[0])


async def _reask(db: AsyncSession, cid: str, row: dict, now: datetime) -> bool:
    done = (await db.execute(text("""
        UPDATE shift_schedule_prompts SET state = 'asked', asked_at = :now, asks = asks + 1, next_ask_at = NULL, updated_at = :now
         WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND shift_started_at = :s
           AND state = 'working' AND next_ask_at = :next
        RETURNING employee_id
    """), {"c": cid, "e": row["employee_id"], "s": row["shift_started_at"], "next": row["next_ask_at"], "now": now})).first()
    await db.commit()
    return done is not None


async def run_company(db: AsyncSession, company_id: Any, *, send: Callable[..., Awaitable[None]],
                      language_of: Callable[[str], Awaitable[str]], now: Optional[datetime] = None) -> dict:
    """Una pasada del aviso de salida para UNA empresa. `send(chat_id, text, reply_markup=None)`.
    Cada paso se reclama de forma atomica en la base: dos copias corriendo no duplican mensajes."""
    from app.services import open_shift_alert

    now = now or datetime.now(timezone.utc)
    cid = str(company_id)
    schedules = Schedules(db, cid)
    found = await prompts(db, cid)
    stats = {"asked": 0, "silent": 0, "out": 0, "bosses": 0, "reasked": 0}
    for shift in await open_shift_alert.open_shifts(db, cid, now_utc=now):
        sch = await schedules.of_shift(shift)
        if not sch:
            continue
        ask_at = sch["end"] + timedelta(minutes=PROMPT_AFTER_MINUTES)
        if now < ask_at:
            continue
        row = found.get((shift["employee_id"], shift["check_in_at"]))
        tg = shift.get("telegram_user_id") or ""
        if row is None:
            stale = now - ask_at > timedelta(hours=STALE_HOURS)
            if not await _claim_new(db, cid, shift, sch, now, stale):
                continue
            if stale:
                stats["silent"] += 1
                continue
            stats["asked"] += 1
            if tg:
                lang = await language_of(tg)
                await send(tg, tr(lang, "ask", time=local_clock(sch["end"], shift["tz"], lang)), reply_markup=prompt_keyboard(lang))
            continue
        if row["state"] in WAITING and row.get("asked_at") and now >= aware(row["asked_at"]) + timedelta(minutes=NO_REPLY_MINUTES):
            notify = await _timeout(db, cid, row, now)
            stats["out"] += 1
            if notify:
                # supervisores de su operacion; si no hay, direccion y rol dueño
                boss_list = await open_shift_alert.bosses(db, cid, shift.get("work_location_id"), shift["employee_id"], owner=True)
                await db.execute(text("""
                    UPDATE shift_schedule_prompts SET recipients = CAST(:r AS jsonb)
                     WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND shift_started_at = :s
                """), {"r": json.dumps([b["name"] for b in boss_list]), "c": cid, "e": shift["employee_id"], "s": shift["check_in_at"]})
                await db.commit()
                for boss in boss_list:
                    lang = await language_of(boss["telegram_user_id"])
                    await send(boss["telegram_user_id"], tr(lang, "boss", name=shift["employee_name"] or "—",
                                                            place=shift.get("work_location_name") or tr(lang, "no_place"),
                                                            time=local_clock(sch["end"], shift["tz"], lang)))
                    stats["bosses"] += 1
            continue
        if row["state"] == "working" and row.get("next_ask_at") and now >= aware(row["next_ask_at"]):
            if await _reask(db, cid, row, now):
                stats["reasked"] += 1
                if tg:
                    lang = await language_of(tg)
                    await send(tg, tr(lang, "ask", time=local_clock(sch["end"], shift["tz"], lang)), reply_markup=prompt_keyboard(lang))
    return stats


async def run_all(db: AsyncSession) -> int:
    from uuid import UUID

    from app.api.v1.endpoints import bots
    from app.services import bot_punch_gps

    total = 0
    for cid in await companies_on(db):
        try:
            token = await bot_punch_gps.bot_token(db, cid)

            async def send(chat_id: str, message: str, reply_markup: Optional[dict] = None, _token=token, _cid=cid) -> None:
                if not _token:
                    return
                try:
                    await bots._send_telegram_message(_token, chat_id, message, reply_markup=reply_markup)
                except Exception as exc:
                    log.warning("Aviso de salida no se pudo enviar (%s): %s", _cid, type(exc).__name__)

            async def language_of(tg: str, _cid=cid) -> str:
                try:
                    lang = await bots._get_user_language(db, UUID(_cid), tg)
                except Exception:
                    await db.rollback()
                    return "es"
                return lang if lang in TEXTS else "es"

            stats = await run_company(db, cid, send=send, language_of=language_of)
            total += sum(stats.values())
        except Exception as exc:  # una empresa con datos raros no frena a las demas
            await db.rollback()
            log.warning("Aviso de salida fallo para %s: %s", cid, type(exc).__name__)
    return total


# ------------------------------------------------------------------ respuestas en el bot
async def _current(db: AsyncSession, cid: str, employee_id: str) -> Optional[dict]:
    """El aviso del turno abierto de la persona (el mas reciente)."""
    row = (await db.execute(text("""
        SELECT p.employee_id::text AS employee_id, p.shift_started_at, p.state, p.reasons, p.asked_at
        FROM shift_schedule_prompts p
        JOIN workforce_attendance_status s ON s.company_id = p.company_id AND s.employee_id = p.employee_id
        WHERE p.company_id = CAST(:c AS uuid) AND p.employee_id = CAST(:e AS uuid) AND s.status IN ('working', 'on_break')
        ORDER BY p.shift_started_at DESC LIMIT 1
    """), {"c": cid, "e": employee_id})).mappings().first()
    return dict(row) if row else None


async def answer(db: AsyncSession, company_id: Any, employee_id: Any, choice: str, now: Optional[datetime] = None) -> bool:
    """Boton del aviso: finish (Finalizar ahora) o reason (Sigo trabajando, falta el motivo).
    Reinicia los 30 min: si no termina de finalizar ni manda el motivo, queda Fuera de horario."""
    now = now or datetime.now(timezone.utc)
    cid, eid = str(company_id), str(employee_id)
    row = await _current(db, cid, eid)
    if not row:
        return False
    await db.execute(text("""
        UPDATE shift_schedule_prompts SET state = :st, asked_at = :now, updated_at = :now
         WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND shift_started_at = :s
    """), {"st": "finish" if choice == "finish" else "reason", "now": now, "c": cid, "e": eid, "s": row["shift_started_at"]})
    await db.commit()
    return True


async def save_reason(db: AsyncSession, company_id: Any, employee_id: Any, reason: Any, now: Optional[datetime] = None) -> Optional[dict]:
    """El motivo de "Sigo trabajando": se guarda y se vuelve a preguntar en 2 h."""
    now = now or datetime.now(timezone.utc)
    cid, eid = str(company_id), str(employee_id)
    note = " ".join(str(reason or "").split())[:REASON_MAX]
    if len(note) < REASON_MIN:
        return None
    row = await _current(db, cid, eid)
    if not row:
        return None
    reasons = _json(row["reasons"], []) + [{"at": iso(now), "text": note}]
    next_at = now + timedelta(hours=REASK_HOURS)
    await db.execute(text("""
        UPDATE shift_schedule_prompts SET state = 'working', reasons = CAST(:r AS jsonb), next_ask_at = :next, updated_at = :now
         WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND shift_started_at = :s
    """), {"r": json.dumps(reasons), "next": next_at, "now": now, "c": cid, "e": eid, "s": row["shift_started_at"]})
    await db.commit()
    return {"next_ask_at": iso(next_at), "reasons": reasons}


# ------------------------------------------------------------------ cierre con motivo
async def shift_context(db: AsyncSession, company_id: Any, employee_id: Any, now: Optional[datetime] = None) -> Optional[dict]:
    """El turno abierto de una persona con su horario y su aviso, o None si no tiene turno abierto."""
    from app.services import open_shift_alert

    now = now or datetime.now(timezone.utc)
    shift = next((s for s in await open_shift_alert.open_shifts(db, company_id, now_utc=now) if s["employee_id"] == str(employee_id)), None)
    if not shift:
        return None
    sch = await Schedules(db, company_id).of_shift(shift)
    row = (await prompts(db, company_id)).get((shift["employee_id"], shift["check_in_at"]))
    return {"shift": shift, "schedule": sch, "prompt": row, "out_of_schedule": bool(row and row.get("out_of_schedule_at")),
            "default_end": default_end(sch["end"] if sch else None, now)}


def schedule_audit(ctx: dict) -> dict:
    sch = ctx.get("schedule") or {}
    return {"slot": sch.get("slot"), "slot_name": sch.get("slot_name"), "week_start": sch.get("week_start"),
            "scheduled_end_at": iso(sch.get("end")), "plan": sch.get("plan"),
            "out_of_schedule": bool(ctx.get("out_of_schedule")), "timezone": ctx["shift"].get("tz")}


async def notify_closed(db: AsyncSession, company_id: Any, employee_id: Any, end_at: datetime, tz_name: Any, by: str) -> bool:
    """"Tu turno fue cerrado a las 5:00 p. m. por <nombre>", en el idioma de la persona. Si falla,
    el turno igual queda cerrado."""
    from uuid import UUID

    from app.api.v1.endpoints import bots
    from app.services import bot_punch_gps

    try:
        tg = (await db.execute(text("""
            SELECT COALESCE(telegram_user_id::text, '') FROM employees WHERE company_id = CAST(:c AS uuid) AND id = CAST(:e AS uuid)
        """), {"c": str(company_id), "e": str(employee_id)})).scalar()
        token = await bot_punch_gps.bot_token(db, str(company_id)) if tg else None
        if not tg or not token:
            return False
        lang = await bots._get_user_language(db, UUID(str(company_id)), tg)
        lang = lang if lang in TEXTS else "es"
        await bots._send_telegram_message(token, tg, tr(lang, "closed", time=local_clock(end_at, tz_name, lang), name=by or "—"))
        return True
    except Exception as exc:
        await db.rollback()
        log.warning("Aviso de turno cerrado no se pudo enviar (%s): %s", company_id, type(exc).__name__)
        return False


# ------------------------------------------------------------------ CRM Campo
async def decorate_board(db: AsyncSession, company_id: Any, board: dict, now: Optional[datetime] = None) -> dict:
    """Agrega a CRM Campo el horario de hoy de cada operacion y, por persona, su horario y el
    chip Fuera de horario. No cambia nada mas del tablero."""
    now = now or datetime.now(timezone.utc)
    marks = await flags(db, company_id, now)
    slots = await employee_slots(db, company_id)
    places = {str(p.get("id")): p for p in board.get("locations") or []}
    for group in board.get("groups") or []:
        place = places.get(str(group.get("key")))
        info = None
        if place:
            tz = place.get("timezone")
            today = now.astimezone(zone(tz)).date()
            data = await week(db, company_id, place["id"], week_start(today))
            info = {"configured": data["configured"], "week_start": data["week_start"],
                    "slots": [{"slot": s["slot"], "name": s["name"], "today": week_days(s, week_start(today))[today.weekday()]["label"]}
                              for s in data["slots"]] if data["configured"] else []}
        group["schedule"] = info
        many = bool(info and len(info["slots"]) > 1)
        for row in group.get("people") or []:
            eid = str(row.get("employee_id"))
            flag = marks.get(eid) or {}
            row["schedule"] = {"slot": slots.get(eid, 1), "slot_name": f"Horario {slots.get(eid, 1)}" if many else None,
                               "out_of_schedule": bool(flag.get("out_of_schedule")),
                               "scheduled_end_label": flag.get("scheduled_end_label"), "reason": flag.get("reason")}
    board["work_schedule"] = True
    return board
