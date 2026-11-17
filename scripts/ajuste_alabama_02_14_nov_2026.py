"""Ajuste masivo de las horas de Alabama del 02 al 14 de noviembre de 2026 (VOLTAGE, semanas de
prueba del bot). Pedido por el dueno el 2026-11-17. Hora de Alabama (America/Chicago).

Personal ACTIVO con lugar de trabajo Alabama. Para cada persona y dia, sus turnos quedan EXACTAMENTE
como la tabla (entrada, almuerzo sin pago, salida); lo que el bot registro ese dia se reemplaza. Dias
sin fila (sab 07 y dom 08) y los dias excluidos (09-11 para Brandon Via Illanes y Giselle Reyna)
quedan sin horas. Del domingo 15 en adelante no se toca nada.

No borra nada. Las marcaciones de esos dias (del bot o del ajuste anterior del 2-3 nov) quedan como
"reemplazada_por_ajuste"; el ajuste son marcaciones nuevas con origen "ajuste_masivo". El respaldo
(antes y despues, fecha y motivo) queda en workforce_attendance_adjustments, lote BATCH, y la
auditoria de la empresa en admin_audit_log. Se puede repetir sin duplicar. No envia mensajes.

Uso, con la base de produccion (por defecto PRUEBA: solo lee y muestra antes/despues):
    railway run -s Postgres py -3.11 scripts/ajuste_alabama_02_14_nov_2026.py
    railway run -s Postgres py -3.11 scripts/ajuste_alabama_02_14_nov_2026.py --apply --expected 25
    railway run -s Postgres py -3.11 scripts/ajuste_alabama_02_14_nov_2026.py --verify
    railway run -s Postgres py -3.11 scripts/ajuste_alabama_02_14_nov_2026.py --undo
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
PLACE = "Alabama"
TZ = "America/Chicago"
CT = ZoneInfo(TZ)
BATCH = "alabama-2026-11-02-14"
SOURCE = "ajuste_masivo"
NOTE = "Ajuste masivo semanas de prueba bot - Alabama 02 al 14 nov 2026 (pedido del dueño)"
ACTOR = "Claude (script ajuste Alabama 02-14 nov, pedido del dueño)"
PUNCHES = ("check_in", "break_start", "break_end", "check_out")
FIRST_DAY, LAST_DAY = date(2026, 11, 2), date(2026, 11, 14)
DAYS = [FIRST_DAY + timedelta(days=i) for i in range((LAST_DAY - FIRST_DAY).days + 1)]


def _t(day: int, start: str, lunch_start: str, lunch_end: str, end: str) -> tuple[date, tuple]:
    hm = lambda s: tuple(int(x) for x in s.split(":"))  # noqa: E731
    return date(2026, 11, day), (("check_in", *hm(start)), ("break_start", *hm(lunch_start)), ("break_end", *hm(lunch_end)), ("check_out", *hm(end)))


SCHEDULE = dict([
    _t(2, "06:00", "12:00", "13:00", "16:30"), _t(3, "06:00", "11:00", "12:00", "18:30"), _t(4, "06:00", "11:00", "12:00", "16:30"),
    _t(5, "06:00", "11:00", "12:00", "16:30"), _t(6, "06:00", "11:00", "12:00", "18:30"), _t(9, "06:00", "11:00", "12:00", "17:30"),
    _t(10, "06:00", "11:00", "12:00", "17:30"), _t(11, "06:00", "11:00", "12:00", "17:30"), _t(12, "07:00", "11:00", "12:00", "17:30"),
    _t(13, "07:00", "11:00", "12:00", "17:30"), _t(14, "07:00", "11:00", "12:00", "17:30"),
])
# Sin horas esos dias: nombre buscado sin mayusculas, tildes ni segundo nombre (todas las palabras).
EXCLUDED = {("brandon", "via", "illanes"): {date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11)},
            ("giselle", "reyna"): {date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11)}}
# Totales esperados del corte 02-15 nov (minutos): pagables, regulares, overtime, pausas
EXPECTED = {"normal": (6690, 4800, 1890, 660), "excluded": (4800, 4110, 690, 480)}
LABELS = {"check_in": "Entrada (ajuste)", "break_start": "Pausa (ajuste)", "break_end": "Retomar (ajuste)", "check_out": "Salida (ajuste)"}
STATUS_AFTER = {"check_in": "working", "break_start": "on_break", "break_end": "working", "check_out": "checked_out"}
OPEN_STATES = ("working", "on_break")
PENDING_ACTIONS = ("gps_punch", "end_shift_summary")
WINDOW_START = datetime.combine(FIRST_DAY, datetime.min.time(), tzinfo=CT)
WINDOW_END = datetime.combine(LAST_DAY + timedelta(days=1), datetime.min.time(), tzinfo=CT)  # dom 15 00:00 CT


class NeedsReview(RuntimeError):
    """Algo no calza con lo pedido: no se escribe nada."""


@dataclass
class PersonDay:
    employee: dict
    day: date
    target: Optional[tuple]
    events: list[dict] = field(default_factory=list)
    done: bool = False

    @property
    def changes(self) -> bool:
        return not self.done and (bool(self.events) or self.target is not None)


def fold(value: str) -> str:
    text_ = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(ch for ch in text_ if unicodedata.category(ch) != "Mn")


def words(value: str) -> set[str]:
    return {w for w in "".join(ch if ch.isalnum() else " " for ch in fold(value)).split() if w}


def at_local(day: date, hour: int, minute: int) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=CT).replace(hour=hour, minute=minute)


def jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "as_tuple"):  # Decimal
        return float(value)
    return str(value)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=jsonable)


def hm(minutes: Optional[int]) -> str:
    return "-" if minutes is None else f"{minutes // 60}:{minutes % 60:02d}"


def schedule_minutes(target: Optional[tuple]) -> tuple[int, int]:
    """(pagables, pausa) de un dia de la tabla."""
    if not target:
        return 0, 0
    t = {k: h * 60 + m for k, h, m in target}
    pause = t["break_end"] - t["break_start"]
    return t["check_out"] - t["check_in"] - pause, pause


async def cohort(db, company_id: str) -> list[dict]:
    from sqlalchemy import text

    rows = (await db.execute(text("""
        SELECT e.id::text AS id, COALESCE(e.full_name, '') AS full_name, e.role
        FROM employees e
        JOIN work_locations w ON w.id = e.work_location_id AND w.company_id = e.company_id
        WHERE e.company_id = CAST(:c AS uuid) AND w.name = :p AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')
        ORDER BY lower(trim(e.full_name))
    """), {"c": company_id, "p": PLACE})).mappings().all()
    return [dict(r) for r in rows]


def exclusions(people: list[dict]) -> dict[str, set[date]]:
    """Persona -> dias sin horas. Cada nombre de la lista debe calzar con UNA sola persona activa."""
    out: dict[str, set[date]] = {}
    for need, days in EXCLUDED.items():
        hits = [p for p in people if set(need) <= words(p["full_name"])]
        if len(hits) != 1:
            raise NeedsReview(f"'{' '.join(need)}' calza con {len(hits)} personas activas de Alabama: {[h['full_name'] for h in hits]}")
        out[hits[0]["id"]] = days
    return out


def target_for(employee_id: str, day: date, excluded: dict[str, set[date]]) -> Optional[tuple]:
    if day in excluded.get(employee_id, set()):
        return None
    return SCHEDULE.get(day)


async def plan(db, company_id: str = VOLTAGE) -> list[PersonDay]:
    """Lo que se haria, por persona y dia (02 a 14 nov). Solo lee."""
    from sqlalchemy import text

    from app.services import us_payroll

    people = await cohort(db, company_id)
    excluded = exclusions(people)
    ids = [p["id"] for p in people]
    done = {(r["employee_id"], r["work_date"]) for r in (await db.execute(text("""
        SELECT employee_id::text AS employee_id, work_date FROM workforce_attendance_adjustments
        WHERE company_id = CAST(:c AS uuid) AND batch = :b AND undone_at IS NULL
    """), {"c": company_id, "b": BATCH})).mappings().all()}
    rows = (await db.execute(text(f"""
        SELECT id::text AS id, employee_id::text AS employee_id, event_type, event_label, status_after, source, source_channel, source_ref,
               detail, notes, payload_json, metadata_json, latitude, longitude, COALESCE(occurred_at, created_at) AS occurred_at
        FROM workforce_attendance_events
        WHERE company_id = CAST(:c AS uuid) AND employee_id::text = ANY(:ids) AND event_type <> 'gps_location'
          AND COALESCE(status_after, '') NOT IN ('{us_payroll.EVENT_REPLACED}', '{us_payroll.EVENT_UNDONE}')
          AND COALESCE(source_ref, '') NOT LIKE :mine
          AND COALESCE(occurred_at, created_at) >= :lo AND COALESCE(occurred_at, created_at) < :hi
        ORDER BY COALESCE(occurred_at, created_at) ASC, id
    """), {"c": company_id, "ids": ids, "mine": f"{SOURCE}:{BATCH}:%", "lo": WINDOW_START, "hi": WINDOW_END + timedelta(hours=12)})).mappings().all()
    by_person: dict[str, list[dict]] = {}
    for row in rows:
        ev = dict(row)
        ev["occurred_at"] = us_payroll._dt(ev["occurred_at"])
        ev["kind"] = us_payroll._kind(ev)
        if ev["kind"] in PUNCHES:
            by_person.setdefault(ev["employee_id"], []).append(ev)
    out, problems = [], []
    for person in people:
        events = by_person.get(person["id"], [])
        used: set[str] = set()
        for day in DAYS:
            today = [e for e in events if e["occurred_at"].astimezone(CT).date() == day and e["id"] not in used]
            item = PersonDay(employee=person, day=day, target=target_for(person["id"], day, excluded), events=today, done=(person["id"], day) in done)
            if today and today[0]["kind"] != "check_in" and not item.done:
                problems.append(f"{person['full_name'].strip()} {day}: el dia empieza con {today[0]['kind']} (turno de otro dia)")
            if today and today[-1]["kind"] != "check_out":  # salida despues de la medianoche: es de este turno
                later = [e for e in events if e["occurred_at"].astimezone(CT).date() == day + timedelta(days=1)]
                if later and later[0]["kind"] != "check_in":
                    tail = []
                    for e in later:
                        if e["kind"] == "check_in":
                            break
                        tail.append(e)
                    item.events = [*today, *tail]
            used.update(e["id"] for e in item.events)
            out.append(item)
    if problems:
        raise NeedsReview("; ".join(problems))
    return out


def original_summary(events: list[dict]) -> str:
    """El resumen de la jornada que escribio la persona sigue visible en el turno ajustado."""
    from app.services import us_payroll

    for ev in reversed(events):
        payload = us_payroll._json(ev.get("payload_json"))
        if ev["kind"] == "check_out" and ev.get("source_channel") not in ("portal_manual_close", SOURCE) and not payload.get("manual_close"):
            return us_payroll._note_text(ev)
    return ""


async def _replace_events(db, company_id: str, item: PersonDay) -> list[str]:
    from sqlalchemy import text

    from app.services import us_payroll

    for ev in item.events:
        mark = {"replaced_by_adjustment": {"batch": BATCH, "event_type": ev["event_type"], "event_label": ev["event_label"], "status_after": ev["status_after"]}}
        changed = await db.execute(text("""
            UPDATE workforce_attendance_events
               SET event_type = :st, status_after = :st, event_label = 'Reemplazada por ajuste',
                   metadata_json = COALESCE(metadata_json, '{}'::jsonb) || CAST(:m AS jsonb)
             WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND status_after <> :st
        """), {"st": us_payroll.EVENT_REPLACED, "m": dumps(mark), "i": ev["id"], "c": company_id})
        if changed.rowcount != 1:
            raise NeedsReview(f"La marcación {ev['id']} cambió mientras corría el ajuste.")
    if not item.target:
        return []
    summary = original_summary(item.events)
    new_ids = []
    for kind, hour, minute in item.target:
        payload = {"adjusted": True, "batch": BATCH, "note": NOTE, "authorized_by": "dueño"}
        if kind == "check_out" and summary:
            payload["args"] = summary
        new_ids.append((await db.execute(text("""
            INSERT INTO workforce_attendance_events (
                company_id, employee_id, event_type, event_label, employee_name, employee_role, status_after,
                source, module_code, source_channel, source_ref, detail, notes, payload_json, metadata_json, occurred_at
            ) VALUES (
                CAST(:c AS uuid), CAST(:e AS uuid), :k, :l, :n, :r, :s,
                :src, 'workforce', :src, :ref, :note, :note, CAST(:p AS jsonb), CAST(:p AS jsonb), :at
            ) RETURNING id::text
        """), {"c": company_id, "e": item.employee["id"], "k": kind, "l": LABELS[kind], "n": item.employee["full_name"][:180], "r": item.employee.get("role"),
               "s": STATUS_AFTER[kind], "src": SOURCE, "ref": f"{SOURCE}:{BATCH}:{item.employee['id']}:{item.day}:{kind}", "note": NOTE,
               "p": dumps(payload), "at": at_local(item.day, hour, minute)})).scalar())
    return new_ids


async def _close_current(db, company_id: str, employee_id: str) -> dict:
    """Si el estado actual de la persona es de un turno de los dias ajustados, queda con la ultima
    salida de la tabla. Un turno que empezo desde el domingo 15 no se toca (es real del bot)."""
    from sqlalchemy import text

    row = (await db.execute(text("""
        SELECT status, last_event_type, last_event_at, check_in_at, check_out_at, break_started_at FROM workforce_attendance_status
        WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) FOR UPDATE
    """), {"c": company_id, "e": employee_id})).mappings().first()
    if not row:
        return {"status": None, "gps_sessions": [], "pending": []}
    before = dict(row)
    if before["check_in_at"] and before["check_in_at"] >= WINDOW_END:
        return {"status": None, "gps_sessions": [], "pending": [], "kept_newer_shift": True}
    if before["status"] in OPEN_STATES and before["check_in_at"] and before["check_in_at"] < WINDOW_START:
        raise NeedsReview(f"{employee_id}: turno abierto desde antes del 2 de noviembre")
    schedule = SCHEDULE[LAST_DAY]
    start, end = at_local(LAST_DAY, *schedule[0][1:]), at_local(LAST_DAY, *schedule[-1][1:])
    await db.execute(text("""
        UPDATE workforce_attendance_status
           SET status = 'checked_out', last_event_type = 'check_out', last_event_at = :end, check_in_at = :start, check_out_at = :end,
               break_started_at = NULL, updated_at = now()
         WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)
    """), {"c": company_id, "e": employee_id, "start": start, "end": end})
    sessions, pending = [], []
    if before["status"] in OPEN_STATES:
        sessions = (await db.execute(text("""
            UPDATE gps_tracking_sessions SET status = 'closed', ended_at = :end, updated_at = now()
             WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND status = 'active' RETURNING id::text
        """), {"c": company_id, "e": employee_id, "end": end})).scalars().all()
        rows = (await db.execute(text("""
            SELECT id::text AS id, expires_at FROM company_telegram_pending_actions
             WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND action = ANY(:a) AND (expires_at IS NULL OR expires_at > now())
        """), {"c": company_id, "e": employee_id, "a": list(PENDING_ACTIONS)})).mappings().all()
        pending = [dict(r) for r in rows]
        if pending:
            await db.execute(text("UPDATE company_telegram_pending_actions SET expires_at = now(), updated_at = now() WHERE id = ANY(CAST(:ids AS uuid[])) AND company_id = CAST(:c AS uuid)"),
                             {"ids": [p["id"] for p in pending], "c": company_id})
    return {"status": before, "gps_sessions": list(sessions), "pending": pending}


async def _audit(db, company_id: str, action: str, detail: dict, actor: str) -> None:
    from sqlalchemy import text

    await db.execute(text("""
        INSERT INTO admin_audit_log (at, actor, ip, method, path, company_id, status_code, surface, detail)
        VALUES (now(), :a, '', 'POST', :p, CAST(:c AS uuid), 200, 'script', CAST(:d AS jsonb))
    """), {"a": actor, "p": f"/scripts/ajuste_alabama_02_14_nov_2026/{action}", "c": company_id, "d": dumps(detail)})


KEEP = ("id", "event_type", "event_label", "status_after", "source", "source_channel", "source_ref", "detail", "notes", "payload_json", "latitude", "longitude", "occurred_at")


async def apply(db, company_id: str = VOLTAGE, *, actor: str = ACTOR, now: Optional[datetime] = None, expected: Optional[int] = None) -> dict:
    """Aplica lo que falte, en una sola transaccion. Repetirlo no duplica."""
    from sqlalchemy import text

    now = now or datetime.now(timezone.utc)
    if now < WINDOW_END:
        raise NeedsReview("Todavía no termina el sábado 14 de noviembre (hora de Alabama).")
    items = await plan(db, company_id)
    people = {i.employee["id"] for i in items}
    if expected is not None and len(people) != expected:
        raise NeedsReview(f"Se aprobaron {expected} personas y hoy son {len(people)}.")
    pending = [i for i in items if i.changes]
    created, replaced = 0, 0
    current: dict[str, dict] = {}
    for employee_id in sorted({i.employee["id"] for i in pending}):
        current[employee_id] = await _close_current(db, company_id, employee_id)
    first_of: dict[str, PersonDay] = {}
    for item in pending:
        first_of.setdefault(item.employee["id"], item)
    for item in pending:
        new_ids = await _replace_events(db, company_id, item)
        before = {"events": [{k: e.get(k) for k in KEEP} for e in item.events], "without_punches": not item.events}
        if first_of[item.employee["id"]] is item:
            before["current"] = current[item.employee["id"]]
        payable, pause = schedule_minutes(item.target)
        after = {"events": new_ids, "times": [f"{h:02d}:{m:02d}" for _, h, m in (item.target or ())], "payable_minutes": payable, "pause_minutes": pause, "note": NOTE}
        await db.execute(text("""
            INSERT INTO workforce_attendance_adjustments (company_id, batch, employee_id, work_date, reason, actor, before_json, after_json)
            VALUES (CAST(:c AS uuid), :b, CAST(:e AS uuid), :d, :r, :a, CAST(:bj AS jsonb), CAST(:aj AS jsonb))
        """), {"c": company_id, "b": BATCH, "e": item.employee["id"], "d": item.day, "r": NOTE, "a": actor, "bj": dumps(before), "aj": dumps(after)})
        created += len(new_ids)
        replaced += len(item.events)
    result = {"people": len(people), "person_days": len(pending), "already_done": sum(1 for i in items if i.done), "new_events": created,
              "replaced_events": replaced, "days_left_empty": sum(1 for i in pending if not i.target)}
    if pending:
        await _audit(db, company_id, "apply", {"motivo": NOTE, "lote": BATCH, **result}, actor)
    await db.commit()
    return result


async def undo(db, company_id: str = VOLTAGE, *, actor: str = ACTOR) -> dict:
    """Vuelve a las marcaciones de antes del ajuste. Las del ajuste quedan guardadas como deshechas."""
    from sqlalchemy import text

    from app.services import us_payroll

    rows = (await db.execute(text("""
        SELECT id::text AS id, employee_id::text AS employee_id, work_date, before_json, after_json FROM workforce_attendance_adjustments
        WHERE company_id = CAST(:c AS uuid) AND batch = :b AND undone_at IS NULL ORDER BY employee_id, work_date
    """), {"c": company_id, "b": BATCH})).mappings().all()
    restored, undone, status_kept = 0, 0, []
    for row in rows:
        before, after = us_payroll._json(row["before_json"]), us_payroll._json(row["after_json"])
        for ev in before.get("events") or []:
            status = await db.execute(text("""
                UPDATE workforce_attendance_events
                   SET event_type = :t, event_label = :l, status_after = :s, metadata_json = metadata_json - 'replaced_by_adjustment'
                 WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND status_after = :rep
            """), {"t": ev["event_type"], "l": ev["event_label"], "s": ev["status_after"], "i": ev["id"], "c": company_id, "rep": us_payroll.EVENT_REPLACED})
            if status.rowcount != 1:
                raise NeedsReview(f"La marcación original {ev['id']} no está como reemplazada.")
            restored += 1
        undone += (await db.execute(text("""
            UPDATE workforce_attendance_events SET event_type = :u, status_after = :u, event_label = 'Ajuste deshecho'
             WHERE id = ANY(CAST(:ids AS uuid[])) AND company_id = CAST(:c AS uuid) AND source_channel = :src
        """), {"u": us_payroll.EVENT_UNDONE, "ids": after.get("events") or [], "c": company_id, "src": SOURCE})).rowcount
        status = (before.get("current") or {}).get("status")
        if status:
            end = at_local(LAST_DAY, *SCHEDULE[LAST_DAY][-1][1:])
            changed = await db.execute(text("""
                UPDATE workforce_attendance_status
                   SET status = :st, last_event_type = :let, last_event_at = CAST(:lea AS timestamptz), check_in_at = CAST(:cia AS timestamptz),
                       check_out_at = CAST(:coa AS timestamptz), break_started_at = CAST(:bsa AS timestamptz), updated_at = now()
                 WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND last_event_at = :end
            """), {"st": status["status"], "let": status.get("last_event_type"), "lea": us_payroll._dt(status.get("last_event_at")),
                   "cia": us_payroll._dt(status.get("check_in_at")), "coa": us_payroll._dt(status.get("check_out_at")),
                   "bsa": us_payroll._dt(status.get("break_started_at")), "c": company_id, "e": row["employee_id"], "end": end})
            if changed.rowcount != 1:
                status_kept.append(row["employee_id"])  # ya marco un turno nuevo: su estado de hoy no se pisa
        await db.execute(text("""
            UPDATE workforce_attendance_adjustments SET undone_at = now(), undone_by = :a
             WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND undone_at IS NULL
        """), {"a": actor, "i": row["id"], "c": company_id})
    result = {"person_days": len(rows), "restored_events": restored, "undone_events": undone, "status_not_restored": len(status_kept)}
    if rows:
        await _audit(db, company_id, "undo", {"lote": BATCH, **result}, actor)
    await db.commit()
    return result


# ------------------------------------------------------------------ PRUEBA / verificacion
async def figures(db, company_id: str = VOLTAGE, start: date = FIRST_DAY, end: date = date(2026, 11, 15)) -> dict[str, dict]:
    """Lo que hoy muestra Nomina (misma funcion) por persona en el corte."""
    from app.services import us_payroll

    snap = await us_payroll.snapshot(db, company_id, start, end)
    out = {r["employee_id"]: {"payable": r["us"]["payable_minutes"], "regular": r["regular_minutes"], "overtime": r["extra_minutes"],
                              "pause": r["us"]["pause_minutes"], "weeks": [(w["week_start"], w["payable"], w["overtime"]) for w in r["us"]["weeks"]]}
           for r in snap["rows"]}
    out["_held"] = snap.get("unverified_shifts") or []
    out["_rules"] = (snap.get("us_payroll") or {}).get("rules") or {}
    return out


def expected_after(employee_id: str, excluded: dict[str, set[date]], rules: dict) -> dict:
    """Cifras de la tabla con la misma regla de Nomina (overtime por semana laboral)."""
    from app.services import us_time

    shifts = []
    for day in DAYS:
        target = target_for(employee_id, day, excluded)
        if not target:
            continue
        t = {k: at_local(day, h, m) for k, h, m in target}
        shifts.append({"employee_id": employee_id, "start": t["check_in"], "end": t["check_out"], "breaks": [(t["break_start"], t["break_end"])], "tz": TZ})
    period = us_time.in_period(us_time.compute(shifts, rules), FIRST_DAY, date(2026, 11, 15))
    weeks = us_time.weeks_of(period)
    return {"payable": sum(s["payable"] for s in period), "regular": sum(s["regular"] for s in period), "overtime": sum(s["overtime"] for s in period),
            "pause": sum(s["pause"] for s in period), "weeks": [(w["week_start"].date().isoformat(), w["payable"], w["overtime"]) for w in weeks]}


async def report(db, company_id: str = VOLTAGE) -> dict:
    """PRUEBA: personas, dias, antes (lo de hoy) y despues (la tabla), por persona y total. No escribe."""
    items = await plan(db, company_id)
    people = await cohort(db, company_id)
    excluded = exclusions(people)
    now = await figures(db, company_id)
    rules = now["_rules"]
    sunday_15 = await figures(db, company_id, date(2026, 11, 15), date(2026, 11, 15))
    held = [h for h in now["_held"] if any(p["id"] == str(h.get("employee_id")) for p in people)]
    lines, ok, totals = [], True, {"before": [0, 0, 0], "after": [0, 0, 0]}
    for p in people:
        b = now.get(p["id"], {"payable": 0, "regular": 0, "overtime": 0})
        a = expected_after(p["id"], excluded, rules)
        want = EXPECTED["excluded" if p["id"] in excluded else "normal"]
        extra = sunday_15.get(p["id"], {}).get("payable", 0)
        good = (a["payable"], a["regular"], a["overtime"], a["pause"]) == want and not extra
        ok = ok and good
        mine = [i for i in items if i.employee["id"] == p["id"]]
        lines.append({"name": " ".join(p["full_name"].split()), "excluded": sorted(d.isoformat() for d in excluded.get(p["id"], set())),
                      "days_with_bot_punches": sum(1 for i in mine if i.events and not i.done), "days_to_create": sum(1 for i in mine if i.target and not i.events and not i.done),
                      "days_to_empty": sum(1 for i in mine if not i.target and i.events and not i.done), "already_done": sum(1 for i in mine if i.done),
                      "before": (b["payable"], b["regular"], b["overtime"]), "after": (a["payable"], a["regular"], a["overtime"]), "weeks_after": a["weeks"],
                      "sunday_15_payable": extra, "ok": good})
        for k, src in (("before", b), ("after", a)):
            totals[k][0] += src["payable"]
            totals[k][1] += src["regular"]
            totals[k][2] += src["overtime"]
    return {"people": lines, "count": len(people), "person_days_to_change": sum(1 for i in items if i.changes), "held_in_range": held,
            "rules": rules, "totals": totals, "matches_expected": ok and rules.get("week_start_day") == "monday"}


def print_report(r: dict) -> None:
    print(f"Reglas: semana {r['rules'].get('week_start_day')} · corte {r['rules'].get('pay_period')}")
    print(f"Personas activas de Alabama: {r['count']} · persona-dias a cambiar: {r['person_days_to_change']}")
    print(f"{'Persona':40} {'antes (pag/reg/OT)':>22} {'despues (pag/reg/OT)':>22}  bot/crear/vaciar  nota")
    for x in r["people"]:
        b, a = x["before"], x["after"]
        note = ("sin horas " + ", ".join(d[8:] for d in x["excluded"]) + " nov" if x["excluded"] else "") + (f" · ¡{hm(x['sunday_15_payable'])} el dom 15!" if x["sunday_15_payable"] else "")
        print(f"{x['name'][:40]:40} {hm(b[0]):>7}/{hm(b[1]):>6}/{hm(b[2]):>6} {hm(a[0]):>7}/{hm(a[1]):>6}/{hm(a[2]):>6}  {x['days_with_bot_punches']:>3}/{x['days_to_create']:>2}/{x['days_to_empty']:>2}  "
              f"{'OK' if x['ok'] else 'NO CUADRA'} {note}")
    tb, ta = r["totals"]["before"], r["totals"]["after"]
    print(f"{'TOTAL':40} {hm(tb[0]):>7}/{hm(tb[1]):>6}/{hm(tb[2]):>6} {hm(ta[0]):>7}/{hm(ta[1]):>6}/{hm(ta[2]):>6}")
    for h in r["held_in_range"]:
        print(f"Por confirmar en el rango (queda reemplazado): {h.get('employee_name')} {h.get('start')} ({hm(h.get('minutes'))})")
    print("CUADRA con los totales esperados" if r["matches_expected"] else "NO CUADRA: no aplicar")


async def verify(db, company_id: str = VOLTAGE) -> dict:
    people = await cohort(db, company_id)
    excluded = exclusions(people)
    now = await figures(db, company_id)
    wrong = []
    for p in people:
        want = EXPECTED["excluded" if p["id"] in excluded else "normal"]
        got = now.get(p["id"], {})
        if (got.get("payable"), got.get("regular"), got.get("overtime"), got.get("pause")) != want:
            wrong.append((p["full_name"].strip(), got.get("payable"), got.get("regular"), got.get("overtime"), got.get("pause")))
    nxt = await figures(db, company_id, date(2026, 11, 16), date(2026, 11, 29))
    return {"people": len(people), "wrong": wrong, "cut_16_29_payable": sum(v["payable"] for k, v in nxt.items() if not k.startswith("_") and any(p["id"] == k for p in people))}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="aplica el ajuste")
    parser.add_argument("--undo", action="store_true", help="vuelve a las marcaciones de antes")
    parser.add_argument("--verify", action="store_true", help="compara Nomina del corte 02-15 con los totales esperados")
    parser.add_argument("--expected", type=int, help="numero de personas aprobado; si no coincide, no escribe")
    parser.add_argument("--json", action="store_true", help="PRUEBA en JSON")
    args = parser.parse_args()
    public = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL") or ""
    if not public:
        raise SystemExit("Falta DATABASE_PUBLIC_URL (corre con: railway run -s Postgres ...)")
    os.environ["DATABASE_URL"] = public.replace("postgresql+asyncpg://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)
    os.environ.setdefault("JWT_SECRET_KEY", "solo-script")
    os.environ.setdefault("SECRET_KEY", "solo-script")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    writes = args.apply or args.undo
    connect = {} if writes else {"server_settings": {"default_transaction_read_only": "on"}}
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args=connect)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            if args.apply:
                print(dumps(await apply(db, expected=args.expected)))
            elif args.undo:
                print(dumps(await undo(db)))
            elif args.verify:
                print(dumps(await verify(db)))
            else:
                r = await report(db)
                print(dumps(r) if args.json else "")
                if not args.json:
                    print_report(r)
                    print("PRUEBA: solo lectura. Para aplicar: --apply --expected N")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
