"""Ajuste masivo de las marcaciones de Alabama del 2 y 3 de noviembre de 2026 (VOLTAGE).

Autorizado por el dueno el 2026-11-03. Solo personal ACTIVO con lugar de trabajo Alabama,
tambien a quien no marco ese dia. Hora de Alabama (America/Chicago).

- Lunes 02/11:  entrada 05:45, pausa 11:00-12:00, salida 16:45 -> pagable 10 h 00
- Martes 03/11: entrada 05:45, pausa 11:00-12:00, salida 17:00 -> pagable 10 h 15

No borra nada. Las marcaciones originales quedan como "reemplazada_por_ajuste" y el ajuste son
marcaciones nuevas con origen "ajuste_masivo"; workforce_attendance_adjustments guarda antes y
despues. Cierra los turnos abiertos de esos dias. Se puede repetir sin duplicar. No envia mensajes.

Uso, con la base de produccion (por defecto no escribe nada):
    railway run -s Postgres py -3.11 scripts/ajuste_alabama_2_3_nov_2026.py
    railway run -s Postgres py -3.11 scripts/ajuste_alabama_2_3_nov_2026.py --apply --expected 24
    railway run -s Postgres py -3.11 scripts/ajuste_alabama_2_3_nov_2026.py --verify
    railway run -s Postgres py -3.11 scripts/ajuste_alabama_2_3_nov_2026.py --undo
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
PLACE = "Alabama"
CT = ZoneInfo("America/Chicago")
BATCH = "alabama-2026-11-02-03"
SOURCE = "ajuste_masivo"
NOTE = "Ajuste masivo autorizado por el dueño - horario 2 y 3 nov Alabama"
ACTOR = "Claude (script ajuste Alabama, autorizado por el dueño)"
PUNCHES = ("check_in", "break_start", "break_end", "check_out")
SCHEDULE = {
    date(2026, 11, 2): (("check_in", 5, 45), ("break_start", 11, 0), ("break_end", 12, 0), ("check_out", 16, 45)),
    date(2026, 11, 3): (("check_in", 5, 45), ("break_start", 11, 0), ("break_end", 12, 0), ("check_out", 17, 0)),
}
PAYABLE = {date(2026, 11, 2): 600, date(2026, 11, 3): 615}
LABELS = {"check_in": "Entrada (ajuste)", "break_start": "Pausa (ajuste)", "break_end": "Retomar (ajuste)", "check_out": "Salida (ajuste)"}
STATUS_AFTER = {"check_in": "working", "break_start": "on_break", "break_end": "working", "check_out": "checked_out"}
OPEN_STATES = ("working", "on_break")
PENDING_ACTIONS = ("gps_punch", "end_shift_summary")
LAST_DAY = max(SCHEDULE)
WINDOW_START = datetime.combine(min(SCHEDULE), datetime.min.time(), tzinfo=CT)
WINDOW_END = datetime.combine(LAST_DAY + timedelta(days=1), datetime.min.time(), tzinfo=CT)


class NeedsReview(RuntimeError):
    """Algo no calza con lo aprobado: no se escribe nada."""


@dataclass
class PersonDay:
    employee: dict
    day: date
    events: list[dict] = field(default_factory=list)
    done: bool = False

    @property
    def without_punches(self) -> bool:
        return not self.events

    @property
    def is_open(self) -> bool:
        return bool(self.events) and self.events[-1]["kind"] != "check_out"


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


def hm(minutes: int | None) -> str:
    return "-" if minutes is None else f"{minutes // 60}:{minutes % 60:02d}"


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


async def plan(db, company_id: str = VOLTAGE) -> list[PersonDay]:
    """Lo que se haria, por persona y dia. Solo lee."""
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
          AND source_channel <> '{SOURCE}'
          AND COALESCE(occurred_at, created_at) >= :lo AND COALESCE(occurred_at, created_at) < :hi
        ORDER BY COALESCE(occurred_at, created_at) ASC, id
    """), {"c": company_id, "ids": ids, "lo": WINDOW_START, "hi": WINDOW_END + timedelta(days=1)})).mappings().all()
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
        for day in sorted(SCHEDULE):
            today = [e for e in events if e["occurred_at"].astimezone(CT).date() == day]
            item = PersonDay(employee=person, day=day, events=today, done=(person["id"], day) in done)
            if today and today[0]["kind"] != "check_in" and not item.done:
                problems.append(f"{person['full_name'].strip()} {day}: el dia empieza con {today[0]['kind']} (turno de otro dia)")
            if item.is_open:  # salida marcada despues de la medianoche: es de este turno
                later = [e for e in events if e["occurred_at"].astimezone(CT).date() == day + timedelta(days=1)]
                if later and later[0]["kind"] == "check_out":
                    item.events = [*today, later[0]]
            out.append(item)
    if problems:
        raise NeedsReview("; ".join(problems))
    return out


def original_summary(events: list[dict]) -> str:
    """El resumen de la jornada que escribio la persona sigue visible en el turno ajustado."""
    from app.services import us_payroll

    for ev in reversed(events):
        payload = us_payroll._json(ev.get("payload_json"))
        if ev["kind"] == "check_out" and ev.get("source_channel") != "portal_manual_close" and not payload.get("manual_close"):
            return us_payroll._note_text(ev)
    return ""


async def _replace_events(db, company_id: str, item: PersonDay) -> list[str]:
    from sqlalchemy import text

    from app.services import us_payroll

    for ev in item.events:
        mark = {"replaced_by_adjustment": {"batch": BATCH, "event_type": ev["event_type"], "event_label": ev["event_label"], "status_after": ev["status_after"]}}
        await db.execute(text("""
            UPDATE workforce_attendance_events
               SET event_type = :st, status_after = :st, event_label = 'Reemplazada por ajuste',
                   metadata_json = COALESCE(metadata_json, '{}'::jsonb) || CAST(:m AS jsonb)
             WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
        """), {"st": us_payroll.EVENT_REPLACED, "m": dumps(mark), "i": ev["id"], "c": company_id})
    summary = original_summary(item.events)
    new_ids = []
    for kind, hour, minute in SCHEDULE[item.day]:
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
    """Deja el estado actual de la persona con el ultimo dia ajustado y cierra lo que siga abierto.
    Un turno que empezo despues de los dias del ajuste no se toca."""
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
    """), {"a": actor, "p": f"/scripts/ajuste_alabama_2_3_nov_2026/{action}", "c": company_id, "d": dumps(detail)})


async def apply(db, company_id: str = VOLTAGE, *, actor: str = ACTOR, now: datetime | None = None, expected: int | None = None) -> dict:
    """Aplica lo que falte, en una sola transaccion. Repetirlo no duplica."""
    from sqlalchemy import text

    now = now or datetime.now(timezone.utc)
    last_out = at_local(LAST_DAY, *SCHEDULE[LAST_DAY][-1][1:])
    if now < last_out:
        raise NeedsReview("Todavía no son las 17:00 CT del 3 de noviembre.")
    items = await plan(db, company_id)
    people = {i.employee["id"] for i in items}
    if expected is not None and len(people) != expected:
        raise NeedsReview(f"Se aprobaron {expected} personas y hoy son {len(people)}.")
    pending = [i for i in items if not i.done]
    created, replaced, closed = 0, 0, []
    current: dict[str, dict] = {}
    for employee_id in sorted({i.employee["id"] for i in pending}):
        current[employee_id] = await _close_current(db, company_id, employee_id)
        status = current[employee_id].get("status")
        if status and status["status"] in OPEN_STATES:
            closed.append(employee_id)
    for item in pending:
        new_ids = await _replace_events(db, company_id, item)
        keep = ("id", "event_type", "event_label", "status_after", "source", "source_channel", "source_ref", "detail", "notes", "payload_json", "latitude", "longitude", "occurred_at")
        before = {"events": [{k: e.get(k) for k in keep} for e in item.events], "without_punches": item.without_punches, "was_open": item.is_open}
        if item.day == LAST_DAY or item.employee["id"] not in {i.employee["id"] for i in pending if i.day == LAST_DAY}:
            before["current"] = current[item.employee["id"]]
        after = {"events": new_ids, "times": [f"{h:02d}:{m:02d}" for _, h, m in SCHEDULE[item.day]], "payable_minutes": PAYABLE[item.day], "note": NOTE}
        await db.execute(text("""
            INSERT INTO workforce_attendance_adjustments (company_id, batch, employee_id, work_date, reason, actor, before_json, after_json)
            VALUES (CAST(:c AS uuid), :b, CAST(:e AS uuid), :d, :r, :a, CAST(:bj AS jsonb), CAST(:aj AS jsonb))
        """), {"c": company_id, "b": BATCH, "e": item.employee["id"], "d": item.day, "r": NOTE, "a": actor, "bj": dumps(before), "aj": dumps(after)})
        created += len(new_ids)
        replaced += len(item.events)
    result = {"people": len(people), "person_days": len(pending), "already_done": len(items) - len(pending), "new_events": created, "replaced_events": replaced,
              "closed_open_shifts": len(closed), "created_shifts": sum(1 for i in pending if i.without_punches)}
    if pending:
        await _audit(db, company_id, "apply", {"motivo": NOTE, "lote": BATCH, **result}, actor)
    await db.commit()
    return result


async def undo(db, company_id: str = VOLTAGE, *, actor: str = ACTOR) -> dict:
    """Vuelve a las marcaciones originales. Las del ajuste quedan guardadas como deshechas."""
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
            end = at_local(LAST_DAY, *SCHEDULE[LAST_DAY][-1][1:])
            changed = await db.execute(text("""
                UPDATE workforce_attendance_status
                   SET status = :st, last_event_type = :let, last_event_at = CAST(:lea AS timestamptz), check_in_at = CAST(:cia AS timestamptz),
                       check_out_at = CAST(:coa AS timestamptz), break_started_at = CAST(:bsa AS timestamptz), updated_at = now()
                 WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND last_event_at = :end
            """), {"st": status["status"], "let": status.get("last_event_type"), "lea": us_payroll._dt(status.get("last_event_at")), "cia": us_payroll._dt(status.get("check_in_at")),
                   "coa": us_payroll._dt(status.get("check_out_at")), "bsa": us_payroll._dt(status.get("break_started_at")), "c": company_id, "e": row["employee_id"], "end": end})
            if changed.rowcount != 1:
                status_kept.append(row["employee_id"])  # ya marco un turno nuevo: su estado de hoy no se pisa
            elif status["status"] in OPEN_STATES:
                for sid in current.get("gps_sessions") or []:
                    await db.execute(text("""
                        UPDATE gps_tracking_sessions SET status = 'active', ended_at = NULL, updated_at = now()
                         WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND status = 'closed'
                           AND NOT EXISTS (SELECT 1 FROM gps_tracking_sessions g WHERE g.company_id = CAST(:c AS uuid) AND g.employee_id = CAST(:e AS uuid) AND g.status = 'active')
                    """), {"i": sid, "c": company_id, "e": row["employee_id"]})
                for action in current.get("pending") or []:
                    await db.execute(text("""
                        UPDATE company_telegram_pending_actions SET expires_at = CAST(:x AS timestamptz), updated_at = now()
                         WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
                    """), {"x": us_payroll._dt(action.get("expires_at")), "i": action["id"], "c": company_id})
        await db.execute(text("""
            UPDATE workforce_attendance_adjustments SET undone_at = now(), undone_by = :a
             WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND undone_at IS NULL
        """), {"a": actor, "i": row["id"], "c": company_id})
    result = {"person_days": len(rows), "restored_events": restored, "undone_events": undone, "status_not_restored": len(status_kept)}
    if rows:
        await _audit(db, company_id, "undo", {"lote": BATCH, **result}, actor)
    await db.commit()
    return result


async def day_figures(db, company_id: str = VOLTAGE) -> dict[str, dict]:
    """Minutos pagables por persona como los ve Nomina y Reportes (misma funcion)."""
    from app.services import us_payroll

    snap = await us_payroll.snapshot(db, company_id, min(SCHEDULE) - timedelta(days=1), LAST_DAY + timedelta(days=4))  # semana laboral dom-sab
    out = {}
    for row in snap["rows"]:
        days: dict[str, int] = {}
        week = 0
        for w in row["us"]["weeks"]:
            week += int(w["payable"])
            for d in w["days"]:
                days[d["date"]] = int(d["payable"])
        out[row["employee_id"]] = {"name": row["employee_name"].strip(), "days": days, "week": week}
    return out


def print_plan(items: list[PersonDay]) -> None:
    for item in items:
        where = "YA APLICADO" if item.done else "SIN MARCACION: se crea el turno" if item.without_punches else "ABIERTO: se cierra" if item.is_open else f"{len(item.events)} marcaciones"
        print(f"{item.employee['full_name'].strip():40} {item.day} -> {hm(PAYABLE[item.day]):5} | {where}")


async def verify(db, company_id: str = VOLTAGE, sample: int = 3) -> None:
    from decimal import Decimal

    from app.services import reports_board, us_payroll

    people = await cohort(db, company_id)
    payroll = await day_figures(db, company_id)
    board = await reports_board.build(db, company_id, min(SCHEDULE), LAST_DAY)
    by_board = {p["id"]: p for o in board["operations"] for p in o["people"]}
    wrong = [p["full_name"].strip() for p in people if {d.isoformat(): m for d, m in PAYABLE.items()} != {k: v for k, v in payroll.get(p["id"], {"days": {}})["days"].items() if k in {d.isoformat() for d in SCHEDULE}}]
    print(f"Personas: {len(people)} | con cifras distintas a 10:00 y 10:15 en Nomina: {wrong or 'ninguna'}")
    for person in random.sample(people, min(sample, len(people))):
        pid = person["id"]
        figures = payroll[pid]
        chart = {d["date"]: int(d["payable"]) for d in by_board[pid]["chart"]} if "chart" in by_board[pid] else {d["date"]: int(d.get("payable") or 0) for d in by_board[pid]["days"]}
        ended = at_local(LAST_DAY, *SCHEDULE[LAST_DAY][-1][1:])
        bot = await us_payroll.bot_summary(db, company_id, pid, ended, "es", lambda v: f"${Decimal(v):.2f}", name=figures["name"])
        lines = {"hoy": next((x for x in (bot or "").splitlines() if "pagable" in x), ""), "semana": next((x for x in (bot or "").splitlines() if "Semana" in x), "")}
        print(f"- {figures['name']}\n  Nomina   lun {hm(figures['days'].get('2026-11-02'))} mar {hm(figures['days'].get('2026-11-03'))} semana {hm(figures['week'])}"
              f"\n  Reportes lun {hm(chart.get('2026-11-02'))} mar {hm(chart.get('2026-11-03'))}\n  Bot      {lines['hoy']} | {lines['semana']}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="aplica el ajuste")
    parser.add_argument("--undo", action="store_true", help="vuelve a las marcaciones originales")
    parser.add_argument("--verify", action="store_true", help="compara Nomina, Reportes y el bot de 3 personas al azar")
    parser.add_argument("--expected", type=int, help="numero de personas aprobado; si no coincide, no escribe")
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
                print(await apply(db, expected=args.expected))
            elif args.undo:
                print(await undo(db))
            elif args.verify:
                await verify(db)
            else:
                print_plan(await plan(db))
                print("Solo lectura. Para aplicar: --apply --expected N")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
