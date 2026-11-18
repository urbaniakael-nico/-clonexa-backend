"""Ajuste de horas de Virginia del 01 al 14 de noviembre de 2026 (VOLTAGE) para 11 personas, segun la
tabla del supervisor. Pedido por el dueno el 2026-11-18. Hora de Virginia (America/New_York).

Para cada una de las 11 personas y cada dia del domingo 01/11 00:00 al sabado 14/11 23:59, sus horas
quedan EXACTAMENTE como la tabla. Todo lo demas que tengan en ese rango (horas del bot, turnos
abiertos, por confirmar) se reemplaza; dias sin horas en la tabla quedan sin horas. Del domingo 15
en adelante no se toca nada. Las demas personas de Virginia, Alabama y otras empresas no se tocan.

Horario de cada dia (la tabla solo trae horas): 12 h = 7:00, almuerzo 12:00-12:30, salida 19:30;
10 h = salida 17:30; 8 h = salida 15:30; 2 h = 7:00-9:00 sin almuerzo.

No borra nada: las marcaciones quedan como "reemplazada_por_ajuste"; el ajuste son marcaciones nuevas
con origen "ajuste_masivo". Respaldo en workforce_attendance_adjustments (lote BATCH), auditoria en
admin_audit_log. Repetirlo no duplica. No envia mensajes.

Uso, con la base de produccion (por defecto PRUEBA: solo lee):
    railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026.py
    railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026.py --apply --expected 11
    railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026.py --verify
    railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026.py --undo
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
PLACE = "Virginia"
TZ = "America/New_York"
ET = ZoneInfo(TZ)
BATCH = "virginia-2026-11-01-14"
SOURCE = "ajuste_masivo"
NOTE = "ajuste Virginia tabla supervisor 01-14/11 (pedido del dueño)"
ACTOR = "Claude (script ajuste Virginia 01-14 nov, pedido del dueño)"
PUNCHES = ("check_in", "break_start", "break_end", "check_out")
FIRST_DAY, LAST_DAY = date(2026, 11, 1), date(2026, 11, 14)
DAYS = [FIRST_DAY + timedelta(days=i) for i in range((LAST_DAY - FIRST_DAY).days + 1)]
SHAPES = {
    12: (("check_in", 7, 0), ("break_start", 12, 0), ("break_end", 12, 30), ("check_out", 19, 30)),
    10: (("check_in", 7, 0), ("break_start", 12, 0), ("break_end", 12, 30), ("check_out", 17, 30)),
    8: (("check_in", 7, 0), ("break_start", 12, 0), ("break_end", 12, 30), ("check_out", 15, 30)),
    2: (("check_in", 7, 0), ("check_out", 9, 0)),
}
# Persona -> nombres validos (todas las palabras, sin mayusculas ni tildes; vale cualquiera).
PEOPLE = {
    "Helen Omonte": [("helen", "omonte"), ("helen", "villca")],
    "Kewin Rios": [("kewin", "rios"), ("kevin", "rios")],
    "Jose Cardenas": [("jose", "cardenas")],
    "Luis Rodriguez": [("luis", "vladimir", "rodriguez", "ortiz")],
    "Kerim Munoz": [("kerim", "munoz")],
    "Roberto Camacho": [("roberto", "camacho")],
    "Mery Rondal": [("mery", "rondal")],
    "Yessenia Ortiz": [("yessenia", "ortiz"), ("yesenia", "ortiz")],
    "Jesus Castellon": [("jesus", "castellon")],
    "Jhoselin Vasquez": [("jhoselin", "vasquez"), ("jhoselin", "vazquez")],
    "Jacob Lopez": [("jacob", "lopez")],
}
_COLS = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13]  # dom 01 ... sab 07 | lun 09 ... vie 13
_TABLE = {
    "Helen Omonte":     [0, 12, 12, 12, 12, 12, 10, 12, 12, 12, 12, 0],
    "Kewin Rios":       [0, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12],
    "Jose Cardenas":    [0, 12, 12, 12, 12, 0, 12, 12, 12, 12, 12, 0],
    "Luis Rodriguez":   [8, 0, 0, 8, 8, 8, 0, 8, 8, 8, 8, 8],
    "Kerim Munoz":      [8, 12, 12, 12, 8, 2, 0, 8, 8, 8, 8, 8],
    "Roberto Camacho":  [0, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12],
    "Mery Rondal":      [0, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12],
    "Yessenia Ortiz":   [0, 12, 12, 0, 0, 0, 0, 0, 0, 0, 0, 8],
    "Jesus Castellon":  [0, 12, 12, 0, 0, 0, 0, 0, 0, 0, 0, 8],
    "Jhoselin Vasquez": [8, 0, 0, 8, 8, 8, 0, 0, 8, 8, 8, 8],
    "Jacob Lopez":      [0, 8, 12, 12, 12, 12, 0, 12, 12, 12, 8, 8],
}
HOURS = {who: {date(2026, 11, d): h for d, h in zip(_COLS, row) if h} for who, row in _TABLE.items()}
# Totales esperados del corte 01-14 nov (horas): total, regular, overtime, semana 01-07, semana 08-14
EXPECTED = {
    "Helen Omonte": (118, 80, 38, 70, 48), "Kewin Rios": (132, 80, 52, 72, 60), "Jose Cardenas": (108, 80, 28, 60, 48),
    "Luis Rodriguez": (72, 72, 0, 32, 40), "Kerim Munoz": (94, 80, 14, 54, 40), "Roberto Camacho": (132, 80, 52, 72, 60),
    "Mery Rondal": (132, 80, 52, 72, 60), "Yessenia Ortiz": (32, 32, 0, 24, 8), "Jesus Castellon": (32, 32, 0, 24, 8),
    "Jhoselin Vasquez": (64, 64, 0, 32, 32), "Jacob Lopez": (108, 80, 28, 56, 52),
}
EXPECTED_TOTAL = (1024, 760, 264)
LABELS = {"check_in": "Entrada (ajuste)", "break_start": "Pausa (ajuste)", "break_end": "Retomar (ajuste)", "check_out": "Salida (ajuste)"}
STATUS_AFTER = {"check_in": "working", "break_start": "on_break", "break_end": "working", "check_out": "checked_out"}
OPEN_STATES = ("working", "on_break")
PENDING_ACTIONS = ("gps_punch", "end_shift_summary")
WINDOW_START = datetime.combine(FIRST_DAY, datetime.min.time(), tzinfo=ET)
WINDOW_END = datetime.combine(LAST_DAY + timedelta(days=1), datetime.min.time(), tzinfo=ET)  # dom 15 00:00 ET


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
    return datetime.combine(day, datetime.min.time(), tzinfo=ET).replace(hour=hour, minute=minute)


def jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        return float(value)
    return str(value)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=jsonable)


def hm(minutes: Optional[int]) -> str:
    return "-" if minutes is None else f"{minutes // 60}:{minutes % 60:02d}"


def schedule_minutes(target: Optional[tuple]) -> tuple[int, int]:
    if not target:
        return 0, 0
    t = {k: h * 60 + m for k, h, m in target}
    pause = t.get("break_end", 0) - t.get("break_start", 0)
    return t["check_out"] - t["check_in"] - pause, pause


async def virginia_people(db, company_id: str) -> list[dict]:
    from sqlalchemy import text

    rows = (await db.execute(text("""
        SELECT e.id::text AS id, COALESCE(e.full_name, '') AS full_name, e.role, w.id::text AS place_id
        FROM employees e
        JOIN work_locations w ON w.id = e.work_location_id AND w.company_id = e.company_id
        WHERE e.company_id = CAST(:c AS uuid) AND w.name = :p AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')
        ORDER BY lower(trim(e.full_name))
    """), {"c": company_id, "p": PLACE})).mappings().all()
    return [dict(r) for r in rows]


def match(everyone: list[dict]) -> dict[str, dict]:
    """Etiqueta de la tabla -> la persona de Virginia. Cada una debe calzar con UNA sola persona."""
    out, problems = {}, []
    for label, names in PEOPLE.items():
        hits = [p for p in everyone if any(set(n) <= words(p["full_name"]) for n in names)]
        if len(hits) != 1:
            problems.append(f"'{label}' calza con {len(hits)} personas activas de Virginia: {[h['full_name'] for h in hits]}")
            continue
        out[label] = hits[0]
    used = [p["id"] for p in out.values()]
    if len(set(used)) != len(used):
        problems.append("Dos nombres de la tabla calzan con la misma persona")
    if problems:
        raise NeedsReview("; ".join(problems))
    return out


async def cohort(db, company_id: str) -> list[dict]:
    """Las 11 personas de la tabla, con su etiqueta."""
    found = match(await virginia_people(db, company_id))
    return [{**p, "label": label} for label, p in found.items()]


def target_for(label: str, day: date) -> Optional[tuple]:
    hours = HOURS[label].get(day)
    return SHAPES[hours] if hours else None


async def plan(db, company_id: str = VOLTAGE) -> list[PersonDay]:
    """Lo que se haria, por persona y dia (01 a 14 nov). Solo lee."""
    from sqlalchemy import text

    from app.services import us_payroll

    people = await cohort(db, company_id)
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
            today = [e for e in events if e["occurred_at"].astimezone(ET).date() == day and e["id"] not in used]
            item = PersonDay(employee=person, day=day, target=target_for(person["label"], day), events=today, done=(person["id"], day) in done)
            if today and today[0]["kind"] != "check_in" and not item.done:
                problems.append(f"{person['full_name'].strip()} {day}: el dia empieza con {today[0]['kind']} (turno de otro dia)")
            if today and today[-1]["kind"] != "check_out":  # salida despues de la medianoche: es de este turno
                later = [e for e in events if e["occurred_at"].astimezone(ET).date() == day + timedelta(days=1)]
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


def last_shift(label: str) -> Optional[tuple[datetime, datetime]]:
    days = sorted(HOURS[label])
    if not days:
        return None
    shape = SHAPES[HOURS[label][days[-1]]]
    return at_local(days[-1], *shape[0][1:]), at_local(days[-1], *shape[-1][1:])


async def _close_current(db, company_id: str, person: dict) -> dict:
    """Si el estado actual de la persona es de un turno de los dias ajustados (o un turno abierto
    viejo), queda con la ultima salida de la tabla. Un turno desde el domingo 15 no se toca."""
    from sqlalchemy import text

    employee_id = person["id"]
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
        raise NeedsReview(f"{person['full_name']}: turno abierto desde antes del 1 de noviembre")
    last = last_shift(person["label"])
    start, end = last if last else (None, None)
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
        """), {"c": company_id, "e": employee_id, "end": end or WINDOW_END})).scalars().all()
        rows = (await db.execute(text("""
            SELECT id::text AS id, expires_at FROM company_telegram_pending_actions
             WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND action = ANY(:a) AND (expires_at IS NULL OR expires_at > now())
        """), {"c": company_id, "e": employee_id, "a": list(PENDING_ACTIONS)})).mappings().all()
        pending = [dict(r) for r in rows]
        if pending:
            await db.execute(text("UPDATE company_telegram_pending_actions SET expires_at = now(), updated_at = now() WHERE id = ANY(CAST(:ids AS uuid[])) AND company_id = CAST(:c AS uuid)"),
                             {"ids": [p["id"] for p in pending], "c": company_id})
    return {"status": before, "gps_sessions": list(sessions), "pending": pending, "set_to": [start, end]}


async def _audit(db, company_id: str, action: str, detail: dict, actor: str) -> None:
    from sqlalchemy import text

    await db.execute(text("""
        INSERT INTO admin_audit_log (at, actor, ip, method, path, company_id, status_code, surface, detail)
        VALUES (now(), :a, '', 'POST', :p, CAST(:c AS uuid), 200, 'script', CAST(:d AS jsonb))
    """), {"a": actor, "p": f"/scripts/ajuste_virginia_01_14_nov_2026/{action}", "c": company_id, "d": dumps(detail)})


KEEP = ("id", "event_type", "event_label", "status_after", "source", "source_channel", "source_ref", "detail", "notes", "payload_json", "latitude", "longitude", "occurred_at")


async def apply(db, company_id: str = VOLTAGE, *, actor: str = ACTOR, now: Optional[datetime] = None, expected: Optional[int] = None) -> dict:
    from sqlalchemy import text

    now = now or datetime.now(timezone.utc)
    if now < WINDOW_END:
        raise NeedsReview("Todavía no termina el sábado 14 de noviembre (hora de Virginia).")
    items = await plan(db, company_id)
    people = {i.employee["id"]: i.employee for i in items}
    if expected is not None and len(people) != expected:
        raise NeedsReview(f"Se aprobaron {expected} personas y hoy son {len(people)}.")
    pending = [i for i in items if i.changes]
    created, replaced = 0, 0
    current: dict[str, dict] = {}
    for employee_id in sorted({i.employee["id"] for i in pending}):
        current[employee_id] = await _close_current(db, company_id, people[employee_id])
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
    closed_open = sum(1 for c in current.values() if (c.get("status") or {}).get("status") in OPEN_STATES)
    result = {"people": len(people), "person_days": len(pending), "already_done": sum(1 for i in items if i.done), "new_events": created,
              "replaced_events": replaced, "days_left_empty": sum(1 for i in pending if not i.target), "open_shifts_closed": closed_open,
              "bot_steps_expired": sum(len(c.get("pending") or []) for c in current.values())}
    if pending:
        await _audit(db, company_id, "apply", {"motivo": NOTE, "lote": BATCH, **result}, actor)
    await db.commit()
    return result


async def undo(db, company_id: str = VOLTAGE, *, actor: str = ACTOR) -> dict:
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
        current = before.get("current") or {}
        status = current.get("status")
        if status:
            end = us_payroll._dt((current.get("set_to") or [None, None])[1])
            changed = await db.execute(text("""
                UPDATE workforce_attendance_status
                   SET status = :st, last_event_type = :let, last_event_at = CAST(:lea AS timestamptz), check_in_at = CAST(:cia AS timestamptz),
                       check_out_at = CAST(:coa AS timestamptz), break_started_at = CAST(:bsa AS timestamptz), updated_at = now()
                 WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND last_event_at IS NOT DISTINCT FROM CAST(:end AS timestamptz)
            """), {"st": status["status"], "let": status.get("last_event_type"), "lea": us_payroll._dt(status.get("last_event_at")),
                   "cia": us_payroll._dt(status.get("check_in_at")), "coa": us_payroll._dt(status.get("check_out_at")),
                   "bsa": us_payroll._dt(status.get("break_started_at")), "c": company_id, "e": row["employee_id"], "end": end})
            if changed.rowcount != 1:
                status_kept.append(row["employee_id"])
            elif status["status"] in OPEN_STATES:
                for sid in current.get("gps_sessions") or []:
                    await db.execute(text("""
                        UPDATE gps_tracking_sessions SET status = 'active', ended_at = NULL, updated_at = now()
                         WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND status = 'closed'
                    """), {"i": sid, "c": company_id})
                for action in current.get("pending") or []:
                    await db.execute(text("UPDATE company_telegram_pending_actions SET expires_at = CAST(:x AS timestamptz), updated_at = now() WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)"),
                                     {"x": us_payroll._dt(action.get("expires_at")), "i": action["id"], "c": company_id})
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
async def figures(db, company_id: str = VOLTAGE, start: date = FIRST_DAY, end: date = LAST_DAY) -> dict[str, dict]:
    from app.services import us_payroll

    snap = await us_payroll.snapshot(db, company_id, start, end)
    out = {r["employee_id"]: {"payable": r["us"]["payable_minutes"], "regular": r["regular_minutes"], "overtime": r["extra_minutes"],
                              "pause": r["us"]["pause_minutes"], "place": r["us"]["place"], "name": r["employee_name"],
                              "weeks": [(w["week_start"], w["payable"], w["overtime"]) for w in r["us"]["weeks"]]}
           for r in snap["rows"]}
    out["_held"] = snap.get("unverified_shifts") or []
    out["_rules"] = (snap.get("us_payroll") or {}).get("rules") or {}
    return out


def expected_after(label: str, rules: dict) -> dict:
    from app.services import us_time

    shifts = []
    for day in DAYS:
        target = target_for(label, day)
        if not target:
            continue
        t = {k: at_local(day, h, m) for k, h, m in target}
        breaks = [(t["break_start"], t["break_end"])] if "break_start" in t else []
        shifts.append({"employee_id": label, "start": t["check_in"], "end": t["check_out"], "breaks": breaks, "tz": TZ})
    period = us_time.in_period(us_time.compute(shifts, rules), FIRST_DAY, LAST_DAY)
    weeks = us_time.weeks_of(period)
    return {"payable": sum(s["payable"] for s in period), "regular": sum(s["regular"] for s in period), "overtime": sum(s["overtime"] for s in period),
            "weeks": [(w["week_start"].date().isoformat(), w["payable"], w["overtime"]) for w in weeks]}


async def report(db, company_id: str = VOLTAGE) -> dict:
    """PRUEBA: personas encontradas, dias, antes y despues, abiertos/por confirmar. No escribe."""
    from sqlalchemy import text

    from app.services import us_time

    items = await plan(db, company_id)
    people = await cohort(db, company_id)
    everyone = await virginia_people(db, company_id)
    now = await figures(db, company_id)
    place_id = people[0]["place_id"] if people else None
    rules = us_time.place_rules(now["_rules"], place_id)
    ids = {p["id"] for p in people}
    held = [h for h in now["_held"] if str(h.get("employee_id")) in ids]
    status = {r["employee_id"]: dict(r) for r in (await db.execute(text("""
        SELECT employee_id::text AS employee_id, status, check_in_at FROM workforce_attendance_status
        WHERE company_id = CAST(:c AS uuid) AND employee_id::text = ANY(:ids)
    """), {"c": company_id, "ids": list(ids)})).mappings().all()}
    sunday = await figures(db, company_id, date(2026, 11, 15), date(2026, 11, 15))
    lines, ok, tb, ta = [], True, [0, 0, 0], [0, 0, 0]
    for p in people:
        b = now.get(p["id"], {"payable": 0, "regular": 0, "overtime": 0})
        a = expected_after(p["label"], rules)
        want = EXPECTED[p["label"]]
        good = (a["payable"], a["regular"], a["overtime"]) == tuple(x * 60 for x in want[:3]) and [w[1] for w in a["weeks"]] == [want[3] * 60, want[4] * 60]
        ok = ok and good
        mine = [i for i in items if i.employee["id"] == p["id"]]
        st = status.get(p["id"]) or {}
        open_old = st.get("status") in OPEN_STATES and st.get("check_in_at") and st["check_in_at"] < WINDOW_END
        lines.append({"label": p["label"], "name": " ".join(p["full_name"].split()), "before": (b["payable"], b["regular"], b["overtime"]),
                      "after": (a["payable"], a["regular"], a["overtime"]), "weeks_after": a["weeks"],
                      "days_with_punches": sum(1 for i in mine if i.events and not i.done), "events_replaced": sum(len(i.events) for i in mine if not i.done),
                      "days_to_create": sum(1 for i in mine if i.target and not i.events and not i.done),
                      "days_to_empty": sum(1 for i in mine if not i.target and i.events and not i.done),
                      "held": sum(1 for h in held if str(h.get("employee_id")) == p["id"]), "open_old_shift": bool(open_old),
                      "sunday_15_payable": sunday.get(p["id"], {}).get("payable", 0), "ok": good})
        for k in range(3):
            tb[k] += (b["payable"], b["regular"], b["overtime"])[k]
            ta[k] += (a["payable"], a["regular"], a["overtime"])[k]
    others = [{"name": " ".join(v["name"].split()), "payable": v["payable"]} for k, v in now.items()
              if not k.startswith("_") and k not in ids and v.get("place") == PLACE and v["payable"] > 0]
    dup_luis = [" ".join(p["full_name"].split()) for p in everyone if {"luis", "rodriguez"} <= words(p["full_name"])]
    ok = ok and tuple(ta) == tuple(x * 60 for x in EXPECTED_TOTAL) and rules.get("week_start_day") == "sunday"
    return {"people": lines, "count": len(people), "person_days_to_change": sum(1 for i in items if i.changes), "held_in_range": held,
            "rules": {k: rules.get(k) for k in ("week_start_day", "pay_period")}, "totals": {"before": tb, "after": ta},
            "other_virginia_with_hours": sorted(others, key=lambda x: x["name"].lower()), "luis_rodriguez_records": dup_luis, "matches_expected": ok}


def print_report(r: dict) -> None:
    print(f"Reglas de Virginia: semana {r['rules'].get('week_start_day')} · corte {r['rules'].get('pay_period')}")
    print(f"Personas encontradas: {r['count']} · persona-dias a cambiar: {r['person_days_to_change']}")
    print(f"{'Tabla':17} {'Nombre en el sistema':34} {'antes pag/reg/OT':>21} {'despues pag/reg/OT':>21} dias/marcas/crear/vaciar abierto pc dom15")
    for x in r["people"]:
        b, a = x["before"], x["after"]
        print(f"{x['label']:17} {x['name'][:34]:34} {hm(b[0]):>7}/{hm(b[1]):>6}/{hm(b[2]):>6} {hm(a[0]):>7}/{hm(a[1]):>6}/{hm(a[2]):>6} "
              f"{x['days_with_punches']:>4}/{x['events_replaced']:>4}/{x['days_to_create']:>3}/{x['days_to_empty']:>3}   {'SI' if x['open_old_shift'] else 'no':>3} {x['held']:>2} "
              f"{hm(x['sunday_15_payable']):>6}  {'OK' if x['ok'] else 'NO CUADRA'}")
    tb, ta = r["totals"]["before"], r["totals"]["after"]
    print(f"{'TOTAL':52} {hm(tb[0]):>7}/{hm(tb[1]):>6}/{hm(tb[2]):>6} {hm(ta[0]):>7}/{hm(ta[1]):>6}/{hm(ta[2]):>6}")
    for h in r["held_in_range"]:
        print(f"Por confirmar en el rango (queda reemplazado): {h.get('employee_name')} {h.get('start')} ({hm(h.get('minutes'))})")
    print(f"Registros 'Luis Rodriguez' en Virginia: {r['luis_rodriguez_records']}")
    print(f"Otras personas de Virginia con horas del bot en 01-14/11 (no se tocan): {len(r['other_virginia_with_hours'])}")
    for o in r["other_virginia_with_hours"]:
        print(f"   - {o['name']} ({hm(o['payable'])})")
    print("CUADRA con los totales esperados" if r["matches_expected"] else "NO CUADRA: no aplicar")


async def verify(db, company_id: str = VOLTAGE) -> dict:
    from app.services import us_time

    people = await cohort(db, company_id)
    now = await figures(db, company_id)
    wrong = []
    for p in people:
        want = EXPECTED[p["label"]]
        got = now.get(p["id"], {})
        if (got.get("payable"), got.get("regular"), got.get("overtime")) != tuple(x * 60 for x in want[:3]) or [w[1] for w in got.get("weeks") or []] != [want[3] * 60, want[4] * 60]:
            wrong.append((p["label"], got.get("payable"), got.get("regular"), got.get("overtime"), got.get("weeks")))
    total = [sum(now.get(p["id"], {}).get(k, 0) for p in people) for k in ("payable", "regular", "overtime")]
    al = await figures(db, company_id, date(2026, 11, 2), date(2026, 11, 15))
    al_tot = [sum(v[k] for key, v in al.items() if not key.startswith("_") and v.get("place") == "Alabama") for k in ("payable", "overtime")]
    va_next = await figures(db, company_id, date(2026, 11, 15), date(2026, 11, 28))
    va_next_tot = sum(v["payable"] for key, v in va_next.items() if not key.startswith("_") and v.get("place") == PLACE)
    rules = us_time.place_rules(now["_rules"], people[0]["place_id"]) if people else {}
    return {"people": len(people), "wrong": wrong, "total_01_14": total, "alabama_02_15": al_tot, "virginia_15_28_payable": va_next_tot,
            "virginia_week_start": rules.get("week_start_day")}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--expected", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    public = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL") or ""
    if not public:
        raise SystemExit("Falta DATABASE_PUBLIC_URL (corre con: railway run -s Postgres ...)")
    os.environ["DATABASE_URL"] = public.replace("postgresql+asyncpg://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)
    os.environ.setdefault("JWT_SECRET_KEY", "solo-script")
    os.environ.setdefault("SECRET_KEY", "solo-script")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    writes = args.apply or args.undo
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={} if writes else {"server_settings": {"default_transaction_read_only": "on"}})
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
                if args.json:
                    print(dumps(r))
                else:
                    print_report(r)
                    print("PRUEBA: solo lectura. Para aplicar: --apply --expected 11")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
