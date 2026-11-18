"""Segunda parte del ajuste de Virginia, corte 01/11-14/11/2026 (VOLTAGE). Pedido del dueno 2026-11-18.
Mismo mecanismo que scripts/ajuste_virginia_01_14_nov_2026.py (lote anterior "virginia-2026-11-01-14",
que NO se toca), con lote nuevo BATCH y su propio --undo.

1) 4 personas mas segun la tabla del supervisor (entrada 6:00, almuerzo 12:00-12:30 sin pago, salida
   segun la tabla): Diego Ruiz, Jaime Marca, Noe Ponce, Mijail Illanes. Dias sin fila: sin horas.
2) Todas las demas personas de Virginia (las que no son las 11 de la primera parte ni estas 4): 0 horas
   del 01 al 14/11. Solo se reemplazan sus marcaciones; la persona y su estado no se borran.
3) Turnos sin cerrar del primer corte, para TODA la empresa: abiertos, conectados sin cerrar (entrada
   sin salida) y por confirmar que empezaron dentro del primer corte de su operacion (Virginia 01-14/11
   ET, Alabama 02-15/11 CT) se quitan. Lo que ya es de un ajuste (origen ajuste_masivo) no se toca.
   Ningun estado del bot queda "en turno" con un turno de antes del 15/11 (Virginia) o del 16/11
   (Alabama); un turno del corte actual no se toca.

Nada se borra: las marcaciones quedan como "reemplazada_por_ajuste"; respaldo en
workforce_attendance_adjustments (lote BATCH), auditoria en admin_audit_log. Repetirlo no duplica.

Uso (por defecto PRUEBA, solo lee):
    railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026_b.py
    railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026_b.py --apply --expected 15
    railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026_b.py --verify
    railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026_b.py --undo
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _first_part():
    name = "ajuste_virginia_01_14_parte1"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "ajuste_virginia_01_14_nov_2026.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


A = _first_part()
VOLTAGE = A.VOLTAGE
BATCH = "virginia-2026-11-01-14-b"
SOURCE = A.SOURCE
NOTE = "ajuste Virginia tabla supervisor 01-14/11 parte 2 (4 personas, resto en 0, turnos sin cerrar) - pedido del dueño"
ACTOR = "Claude (script ajuste Virginia 01-14 nov parte 2, pedido del dueño)"
ET, CT = ZoneInfo("America/New_York"), ZoneInfo("America/Chicago")
PUNCHES = A.PUNCHES
DAYS = A.DAYS  # 01-14 nov
FIRST_CUT = {"Virginia": (date(2026, 11, 1), date(2026, 11, 14), ET), "Alabama": (date(2026, 11, 2), date(2026, 11, 15), CT)}
STATUS_AFTER, LABELS, OPEN_STATES = A.STATUS_AFTER, A.LABELS, A.OPEN_STATES
WINDOW_START, WINDOW_END = A.WINDOW_START, A.WINDOW_END  # Virginia 01/11 00:00 ET - 15/11 00:00 ET


def _exit(hhmm: str) -> tuple:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return (("check_in", 6, 0), ("break_start", 12, 0), ("break_end", 12, 30), ("check_out", hh, mm))


NEW_PEOPLE = {
    "Diego Ruiz": [("diego", "ruiz")],
    "Jaime Marca": [("jaime", "marca")],
    "Noe Ponce": [("noe", "ponce")],
    "Mijail Illanes": [("mijail", "illanes")],
}
_NOV = lambda d: date(2026, 11, d)  # noqa: E731
SCHEDULE = {
    "Diego Ruiz": {_NOV(d): _exit("18:30") for d in (2, 3, 4, 5, 6, 9, 10, 11, 13)},
    "Jaime Marca": {_NOV(d): _exit("18:30") for d in (2, 3)},
    "Noe Ponce": {_NOV(2): _exit("14:30"), _NOV(3): _exit("15:55"), _NOV(4): _exit("15:00"), _NOV(5): _exit("15:00"), _NOV(6): _exit("15:00"),
                  _NOV(9): _exit("15:00"), _NOV(10): _exit("15:00"), _NOV(11): _exit("14:30"), _NOV(12): _exit("14:30"), _NOV(13): _exit("14:30")},
    "Mijail Illanes": {_NOV(1): _exit("20:30"), _NOV(2): _exit("18:30"), _NOV(3): _exit("18:30"), _NOV(10): _exit("14:30"), _NOV(11): _exit("14:30"),
                       _NOV(12): _exit("18:30"), _NOV(13): _exit("18:30"), _NOV(14): _exit("18:30")},
}
# total, regular, overtime, semana 01-07, semana 08-14 (minutos)
EXPECTED = {"Diego Ruiz": (6480, 4800, 1680, 3600, 2880), "Jaime Marca": (1440, 1440, 0, 1440, 0),
            "Noe Ponce": (5035, 4800, 235, 2575, 2460), "Mijail Illanes": (5400, 4680, 720, 2280, 3120)}
EXPECTED_FIRST_PART = (1024 * 60, 760 * 60, 264 * 60)
EXPECTED_VIRGINIA = (1329 * 60 + 55, 1022 * 60, 307 * 60 + 55)
EXPECTED_ALABAMA = (2724 * 60 + 30, 1977 * 60, 747 * 60 + 30)
EXPECTED_PEOPLE = 15


class NeedsReview(RuntimeError):
    """Algo no calza con lo pedido: no se escribe nada."""


@dataclass
class Fix:
    """Una persona y un dia: lo que se reemplaza y lo que queda (target None = sin horas)."""
    employee: dict
    day: date
    kind: str  # "tabla" | "cero" | "sin_cerrar"
    target: Optional[tuple] = None
    events: list[dict] = field(default_factory=list)
    done: bool = False

    @property
    def changes(self) -> bool:
        return not self.done and (bool(self.events) or self.target is not None)


# ------------------------------------------------------------------ quienes
async def people_of(db, company_id: str) -> list[dict]:
    """Toda la gente de VOLTAGE con lugar Virginia o Alabama (cualquier estado)."""
    from sqlalchemy import text

    rows = (await db.execute(text("""
        SELECT e.id::text AS id, COALESCE(e.full_name, '') AS full_name, e.role, COALESCE(e.status, 'active') AS status,
               w.id::text AS place_id, w.name AS place
        FROM employees e JOIN work_locations w ON w.id = e.work_location_id AND w.company_id = e.company_id
        WHERE e.company_id = CAST(:c AS uuid) AND w.name IN ('Virginia', 'Alabama')
        ORDER BY w.name, lower(trim(e.full_name))
    """), {"c": company_id})).mappings().all()
    return [dict(r) for r in rows]


def match_new(virginia_active: list[dict]) -> dict[str, dict]:
    out, problems = {}, []
    for label, names in NEW_PEOPLE.items():
        hits = [p for p in virginia_active if any(set(n) <= A.words(p["full_name"]) for n in names)]
        if len(hits) != 1:
            problems.append(f"'{label}' calza con {len(hits)} personas activas de Virginia: {[h['full_name'] for h in hits]}")
        else:
            out[label] = hits[0]
    if problems:
        raise NeedsReview("; ".join(problems))
    return out


async def groups(db, company_id: str) -> dict:
    """first: las 11 de la primera parte; new: las 4 de la tabla; zero: el resto de Virginia; all: todos."""
    everyone = await people_of(db, company_id)
    va_active = [p for p in everyone if p["place"] == "Virginia" and A.fold(p["status"]) in ("active", "activo")]
    first = {p["id"]: {**p, "label": label} for label, p in A.match(va_active).items()}
    new = {p["id"]: {**p, "label": label} for label, p in match_new(va_active).items()}
    if set(first) & set(new):
        raise NeedsReview("Una persona de la tabla nueva ya estaba en la primera parte")
    zero = {p["id"]: {**p, "label": "cero"} for p in everyone if p["place"] == "Virginia" and p["id"] not in first and p["id"] not in new}
    return {"first": first, "new": new, "zero": zero, "all": {p["id"]: p for p in everyone}}


# ------------------------------------------------------------------ lectura de marcaciones
async def punches(db, company_id: str, ids: list[str], lo: datetime, hi: datetime) -> dict[str, list[dict]]:
    from sqlalchemy import text

    from app.services import us_payroll

    rows = (await db.execute(text(f"""
        SELECT id::text AS id, employee_id::text AS employee_id, event_type, event_label, status_after, source, source_channel, source_ref,
               detail, notes, payload_json, metadata_json, latitude, longitude, COALESCE(occurred_at, created_at) AS occurred_at
        FROM workforce_attendance_events
        WHERE company_id = CAST(:c AS uuid) AND employee_id::text = ANY(:ids) AND event_type <> 'gps_location'
          AND COALESCE(status_after, '') NOT IN ('{us_payroll.EVENT_REPLACED}', '{us_payroll.EVENT_UNDONE}')
          AND COALESCE(occurred_at, created_at) >= :lo AND COALESCE(occurred_at, created_at) < :hi
        ORDER BY COALESCE(occurred_at, created_at) ASC, id
    """), {"c": company_id, "ids": ids, "lo": lo, "hi": hi})).mappings().all()
    out: dict[str, list[dict]] = {}
    for row in rows:
        ev = dict(row)
        ev["occurred_at"] = us_payroll._dt(ev["occurred_at"])
        ev["kind"] = us_payroll._kind(ev)
        if ev["kind"] in PUNCHES:
            out.setdefault(ev["employee_id"], []).append(ev)
    return out


def segments(events: list[dict]) -> list[list[dict]]:
    """Turnos como los arma Nomina: desde cada entrada hasta su salida (o hasta la proxima entrada)."""
    out, cur = [], None
    for ev in events:
        if ev["kind"] == "check_in":
            if cur:
                out.append(cur)
            cur = [ev]
        elif cur is not None:
            cur.append(ev)
            if ev["kind"] == "check_out":
                out.append(cur)
                cur = None
    if cur:
        out.append(cur)
    return out


def by_day(person: dict, events: list[dict], tz, days: list[date], target_of, kind: str, done: set) -> list[Fix]:
    """Reemplazo por dia (como la primera parte): lo del dia, y la salida despues de la medianoche."""
    out, used, problems = [], set(), []
    for day in days:
        today = [e for e in events if e["occurred_at"].astimezone(tz).date() == day and e["id"] not in used]
        item = Fix(employee=person, day=day, kind=kind, target=target_of(day), events=today, done=(person["id"], day) in done)
        if today and today[0]["kind"] != "check_in" and not item.done:
            problems.append(f"{person['full_name'].strip()} {day}: el dia empieza con {today[0]['kind']} (turno de otro dia)")
        if today and today[-1]["kind"] != "check_out":
            tail = []
            for e in [e for e in events if e["occurred_at"].astimezone(tz).date() == day + timedelta(days=1)]:
                if e["kind"] == "check_in":
                    break
                tail.append(e)
            item.events = [*today, *tail]
        used.update(e["id"] for e in item.events)
        out.append(item)
    if problems:
        raise NeedsReview("; ".join(problems))
    return out


async def plan(db, company_id: str = VOLTAGE) -> dict:
    """Todo lo que se haria. Solo lee."""
    from sqlalchemy import text

    from app.api.v1.endpoints import payroll as core

    g = await groups(db, company_id)
    done = {(r["employee_id"], r["work_date"]) for r in (await db.execute(text("""
        SELECT employee_id::text AS employee_id, work_date FROM workforce_attendance_adjustments
        WHERE company_id = CAST(:c AS uuid) AND batch = :b AND undone_at IS NULL
    """), {"c": company_id, "b": BATCH})).mappings().all()}
    fixes: list[Fix] = []
    # 1) y 2) Virginia: las 4 de la tabla y el resto en 0 (por dia, 01-14 ET)
    va_ids = list(g["new"]) + list(g["zero"])
    ev_va = await punches(db, company_id, va_ids, WINDOW_START, WINDOW_END + timedelta(hours=12))
    for pid, person in {**g["new"], **g["zero"]}.items():
        mine = [e for e in ev_va.get(pid, []) if not str(e.get("source_ref") or "").startswith(f"{SOURCE}:{BATCH}:")]
        if pid in g["new"]:
            sched = SCHEDULE[person["label"]]
            fixes += by_day(person, mine, ET, DAYS, lambda d, s=sched: s.get(d), "tabla", done)
        else:
            fixes += by_day(person, mine, ET, DAYS, lambda d: None, "cero", done)
    handled = {e["id"] for f in fixes for e in f.events}
    # 3) Turnos sin cerrar del primer corte, toda la empresa (los de 1 y 2 ya se reemplazan enteros)
    verification = await core._cx_verification_context_049D(db, company_id)
    rest = [pid for pid in g["all"] if pid not in g["new"] and pid not in g["zero"]]
    lo = datetime.combine(date(2026, 11, 1), datetime.min.time(), tzinfo=ET) - timedelta(days=1)
    hi = datetime(2026, 11, 20, tzinfo=timezone.utc)
    ev_all = await punches(db, company_id, rest, lo, hi)
    unclosed: dict[tuple[str, date], Fix] = {}
    for pid in rest:
        person = g["all"][pid]
        start_day, end_day, tz = FIRST_CUT[person["place"]]
        for seg in segments(ev_all.get(pid, [])):
            ci = seg[0]
            if ci.get("source_channel") == SOURCE or any(e["id"] in handled for e in seg):
                continue  # ya es de un ajuste
            local_day = ci["occurred_at"].astimezone(tz).date()
            if not (start_day <= local_day <= end_day):
                continue  # del corte actual (o de antes): no se toca
            closed = seg[-1]["kind"] == "check_out"
            if closed:
                verdict, closure = core._cx_check_shift_049D(verification, "attendance", ci["id"], ci["occurred_at"], seg[-1]["occurred_at"],
                                                             core._cx_event_system_cutoff_049D(seg[-1]))
                if verdict != "hold" or core._cx_is_admin_closed_068C(closure):
                    continue  # turno normal (o ya pagado por fuera): se queda
            key = (pid, local_day)
            item = unclosed.setdefault(key, Fix(employee=person, day=local_day, kind="sin_cerrar", done=key in done))
            item.events += seg
    fixes += list(unclosed.values())
    return {"groups": g, "fixes": fixes}


# ------------------------------------------------------------------ escritura
async def _replace(db, company_id: str, item: Fix) -> list[str]:
    from sqlalchemy import text

    from app.services import us_payroll

    for ev in item.events:
        mark = {"replaced_by_adjustment": {"batch": BATCH, "event_type": ev["event_type"], "event_label": ev["event_label"], "status_after": ev["status_after"]}}
        changed = await db.execute(text("""
            UPDATE workforce_attendance_events
               SET event_type = :st, status_after = :st, event_label = 'Reemplazada por ajuste',
                   metadata_json = COALESCE(metadata_json, '{}'::jsonb) || CAST(:m AS jsonb)
             WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND status_after <> :st
        """), {"st": us_payroll.EVENT_REPLACED, "m": A.dumps(mark), "i": ev["id"], "c": company_id})
        if changed.rowcount != 1:
            raise NeedsReview(f"La marcación {ev['id']} cambió mientras corría el ajuste.")
    if not item.target:
        return []
    summary = A.original_summary(item.events)
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
               "p": A.dumps(payload), "at": A.at_local(item.day, hour, minute)})).scalar())
    return new_ids


def _first_cut_end(person: dict) -> datetime:
    _, end_day, tz = FIRST_CUT[person["place"]]
    return datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=tz)


def _last_table_shift(person: dict) -> tuple[Optional[datetime], Optional[datetime]]:
    sched = SCHEDULE.get(person.get("label") or "") or {}
    if not sched:
        return None, None
    day = max(sched)
    return A.at_local(day, *sched[day][0][1:]), A.at_local(day, *sched[day][-1][1:])


async def _close_status(db, company_id: str, person: dict) -> Optional[dict]:
    """El estado del bot no queda "en turno" con un turno del primer corte. Un turno del corte actual
    no se toca. Devuelve lo de antes (para --undo) o None si no cambia."""
    from sqlalchemy import text

    row = (await db.execute(text("""
        SELECT status, last_event_type, last_event_at, check_in_at, check_out_at, break_started_at FROM workforce_attendance_status
        WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) FOR UPDATE
    """), {"c": company_id, "e": person["id"]})).mappings().first()
    if not row:
        return None
    before = dict(row)
    if before["check_in_at"] and before["check_in_at"] >= _first_cut_end(person):
        return None
    is_table = person.get("label") in SCHEDULE
    if not is_table and before["status"] not in OPEN_STATES:
        return None  # ya cerrado: nada que hacer
    start, end = _last_table_shift(person) if is_table else (before["check_in_at"], before["check_in_at"])
    if is_table and before["status"] not in OPEN_STATES and not start:
        return None
    await db.execute(text("""
        UPDATE workforce_attendance_status
           SET status = 'checked_out', last_event_type = 'check_out', last_event_at = :end, check_in_at = :start, check_out_at = :end,
               break_started_at = NULL, updated_at = now()
         WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)
    """), {"c": company_id, "e": person["id"], "start": start, "end": end})
    sessions, pending = [], []
    if before["status"] in OPEN_STATES:
        sessions = (await db.execute(text("""
            UPDATE gps_tracking_sessions SET status = 'closed', ended_at = COALESCE(:end, now()), updated_at = now()
             WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND status = 'active' RETURNING id::text
        """), {"c": company_id, "e": person["id"], "end": end})).scalars().all()
        rows = (await db.execute(text("""
            SELECT id::text AS id, expires_at FROM company_telegram_pending_actions
             WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND action = ANY(:a) AND (expires_at IS NULL OR expires_at > now())
        """), {"c": company_id, "e": person["id"], "a": list(A.PENDING_ACTIONS)})).mappings().all()
        pending = [dict(r) for r in rows]
        if pending:
            await db.execute(text("UPDATE company_telegram_pending_actions SET expires_at = now(), updated_at = now() WHERE id = ANY(CAST(:ids AS uuid[])) AND company_id = CAST(:c AS uuid)"),
                             {"ids": [p["id"] for p in pending], "c": company_id})
    return {"status": before, "gps_sessions": list(sessions), "pending": pending, "set_to": [start, end]}


async def _audit(db, company_id: str, action: str, detail: dict) -> None:
    from sqlalchemy import text

    await db.execute(text("""
        INSERT INTO admin_audit_log (at, actor, ip, method, path, company_id, status_code, surface, detail)
        VALUES (now(), :a, '', 'POST', :p, CAST(:c AS uuid), 200, 'script', CAST(:d AS jsonb))
    """), {"a": ACTOR, "p": f"/scripts/ajuste_virginia_01_14_nov_2026_b/{action}", "c": company_id, "d": A.dumps(detail)})


async def apply(db, company_id: str = VOLTAGE, *, now: Optional[datetime] = None, expected: Optional[int] = None) -> dict:
    from sqlalchemy import text

    from app.services import us_payroll

    now = now or datetime.now(timezone.utc)
    if now < datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc):
        raise NeedsReview("Todavía no termina el primer corte de Alabama (domingo 15/11 CT).")
    p = await plan(db, company_id)
    g = p["groups"]
    with_hours = len(g["first"]) + len(g["new"])
    if expected is not None and with_hours != expected:
        raise NeedsReview(f"Se esperaban {expected} personas con horas en Virginia y son {with_hours}.")
    pending = [f for f in p["fixes"] if f.changes]
    # estados del bot: las de la tabla y cualquiera con un turno abierto del primer corte
    touched = {f.employee["id"]: f.employee for f in pending}
    status_before: dict[str, dict] = {}
    for pid, person in sorted({**g["all"], **touched}.items()):
        person = {**person, **(g["new"].get(pid) or {})}
        if pid in g["first"]:
            continue  # la primera parte ya dejo su estado
        got = await _close_status(db, company_id, person)
        if got:
            status_before[pid] = got
    statuses_closed = len(status_before)
    first_of: dict[str, Fix] = {}
    for item in pending:
        first_of.setdefault(item.employee["id"], item)
    created = replaced = 0
    for item in pending:
        new_ids = await _replace(db, company_id, item)
        before = {"kind": item.kind, "events": [{k: e.get(k) for k in A.KEEP} for e in item.events], "without_punches": not item.events}
        if first_of[item.employee["id"]] is item and item.employee["id"] in status_before:
            before["current"] = status_before.pop(item.employee["id"])
        payable, pause = A.schedule_minutes(item.target)
        after = {"events": new_ids, "times": [f"{h:02d}:{m:02d}" for _, h, m in (item.target or ())], "payable_minutes": payable, "pause_minutes": pause, "note": NOTE}
        await db.execute(text("""
            INSERT INTO workforce_attendance_adjustments (company_id, batch, employee_id, work_date, reason, actor, before_json, after_json)
            VALUES (CAST(:c AS uuid), :b, CAST(:e AS uuid), :d, :r, :a, CAST(:bj AS jsonb), CAST(:aj AS jsonb))
        """), {"c": company_id, "b": BATCH, "e": item.employee["id"], "d": item.day, "r": NOTE, "a": ACTOR, "bj": A.dumps(before), "aj": A.dumps(after)})
        created += len(new_ids)
        replaced += len(item.events)
    # estados cerrados de personas sin dias que cambiar: su propia fila de respaldo (dia = su entrada)
    for pid, cur in status_before.items():
        person = g["all"][pid]
        ci = us_payroll._dt(cur["status"].get("check_in_at"))
        _, _, tz = FIRST_CUT[person["place"]]
        day = ci.astimezone(tz).date() if ci else date(2026, 11, 14)
        await db.execute(text("""
            INSERT INTO workforce_attendance_adjustments (company_id, batch, employee_id, work_date, reason, actor, before_json, after_json)
            VALUES (CAST(:c AS uuid), :b, CAST(:e AS uuid), :d, :r, :a, CAST(:bj AS jsonb), CAST(:aj AS jsonb))
            ON CONFLICT DO NOTHING
        """), {"c": company_id, "b": BATCH, "e": pid, "d": day, "r": NOTE, "a": ACTOR,
               "bj": A.dumps({"kind": "estado", "events": [], "current": cur}), "aj": A.dumps({"events": [], "note": NOTE})})
    by_kind = {k: sum(1 for f in pending if f.kind == k) for k in ("tabla", "cero", "sin_cerrar")}
    unclosed_by_place = {pl: sum(1 for f in pending if f.kind == "sin_cerrar" and f.employee["place"] == pl) for pl in ("Virginia", "Alabama")}
    result = {"person_days": len(pending), "by_kind": by_kind, "unclosed_by_place": unclosed_by_place, "new_events": created, "replaced_events": replaced,
              "statuses_closed": statuses_closed}
    if pending:
        await _audit(db, company_id, "apply", {"motivo": NOTE, "lote": BATCH, **result})
    await db.commit()
    return result


async def undo(db, company_id: str = VOLTAGE) -> dict:
    """Vuelve a como estaba antes de ESTE lote. El lote anterior no se toca."""
    from sqlalchemy import text

    from app.services import us_payroll

    rows = (await db.execute(text("""
        SELECT id::text AS id, employee_id::text AS employee_id, work_date, before_json, after_json FROM workforce_attendance_adjustments
        WHERE company_id = CAST(:c AS uuid) AND batch = :b AND undone_at IS NULL ORDER BY employee_id, work_date
    """), {"c": company_id, "b": BATCH})).mappings().all()
    restored = undone = 0
    kept = []
    for row in rows:
        before, after = us_payroll._json(row["before_json"]), us_payroll._json(row["after_json"])
        for ev in before.get("events") or []:
            res = await db.execute(text("""
                UPDATE workforce_attendance_events
                   SET event_type = :t, event_label = :l, status_after = :s, metadata_json = metadata_json - 'replaced_by_adjustment'
                 WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND status_after = :rep
            """), {"t": ev["event_type"], "l": ev["event_label"], "s": ev["status_after"], "i": ev["id"], "c": company_id, "rep": us_payroll.EVENT_REPLACED})
            if res.rowcount != 1:
                raise NeedsReview(f"La marcación original {ev['id']} no está como reemplazada.")
            restored += 1
        undone += (await db.execute(text("""
            UPDATE workforce_attendance_events SET event_type = :u, status_after = :u, event_label = 'Ajuste deshecho'
             WHERE id = ANY(CAST(:ids AS uuid[])) AND company_id = CAST(:c AS uuid) AND source_channel = :src
        """), {"u": us_payroll.EVENT_UNDONE, "ids": after.get("events") or [], "c": company_id, "src": SOURCE})).rowcount
        cur = before.get("current") or {}
        st = cur.get("status")
        if st:
            end = us_payroll._dt((cur.get("set_to") or [None, None])[1])
            res = await db.execute(text("""
                UPDATE workforce_attendance_status
                   SET status = :st, last_event_type = :let, last_event_at = CAST(:lea AS timestamptz), check_in_at = CAST(:cia AS timestamptz),
                       check_out_at = CAST(:coa AS timestamptz), break_started_at = CAST(:bsa AS timestamptz), updated_at = now()
                 WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND last_event_at IS NOT DISTINCT FROM CAST(:end AS timestamptz)
            """), {"st": st["status"], "let": st.get("last_event_type"), "lea": us_payroll._dt(st.get("last_event_at")),
                   "cia": us_payroll._dt(st.get("check_in_at")), "coa": us_payroll._dt(st.get("check_out_at")),
                   "bsa": us_payroll._dt(st.get("break_started_at")), "c": company_id, "e": row["employee_id"], "end": end})
            if res.rowcount != 1:
                kept.append(row["employee_id"])
            elif st["status"] in OPEN_STATES:
                for sid in cur.get("gps_sessions") or []:
                    await db.execute(text("UPDATE gps_tracking_sessions SET status = 'active', ended_at = NULL, updated_at = now() WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND status = 'closed'"),
                                     {"i": sid, "c": company_id})
                for action in cur.get("pending") or []:
                    await db.execute(text("UPDATE company_telegram_pending_actions SET expires_at = CAST(:x AS timestamptz), updated_at = now() WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)"),
                                     {"x": us_payroll._dt(action.get("expires_at")), "i": action["id"], "c": company_id})
        await db.execute(text("UPDATE workforce_attendance_adjustments SET undone_at = now(), undone_by = :a WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND undone_at IS NULL"),
                         {"a": ACTOR, "i": row["id"], "c": company_id})
    result = {"rows": len(rows), "restored_events": restored, "undone_events": undone, "status_not_restored": len(kept)}
    if rows:
        await _audit(db, company_id, "undo", {"lote": BATCH, **result})
    await db.commit()
    return result


# ------------------------------------------------------------------ PRUEBA / verificacion
async def figures(db, company_id: str, start: date, end: date) -> dict:
    from app.services import us_payroll

    snap = await us_payroll.snapshot(db, company_id, start, end)
    out = {r["employee_id"]: {"payable": r["us"]["payable_minutes"], "regular": r["regular_minutes"], "overtime": r["extra_minutes"],
                              "place": r["us"]["place"], "name": " ".join(str(r["employee_name"]).split()),
                              "weeks": [w["payable"] for w in r["us"]["weeks"]]} for r in snap["rows"]}
    return {"rows": out, "held": snap.get("unverified_shifts") or [], "rules": (snap.get("us_payroll") or {}).get("rules") or {}}


def table_after(label: str, rules: dict) -> dict:
    from app.services import us_time

    shifts = []
    for day, target in sorted(SCHEDULE[label].items()):
        t = {k: A.at_local(day, h, m) for k, h, m in target}
        shifts.append({"employee_id": label, "start": t["check_in"], "end": t["check_out"], "breaks": [(t["break_start"], t["break_end"])], "tz": A.TZ})
    period = us_time.in_period(us_time.compute(shifts, rules), date(2026, 11, 1), date(2026, 11, 14))
    return {"payable": sum(s["payable"] for s in period), "regular": sum(s["regular"] for s in period), "overtime": sum(s["overtime"] for s in period),
            "weeks": [w["payable"] for w in us_time.weeks_of(period)]}


def _tot(rows: dict, ids) -> tuple[int, int, int]:
    return tuple(sum(rows.get(i, {}).get(k, 0) for i in ids) for k in ("payable", "regular", "overtime"))


async def open_statuses(db, company_id: str, g: dict) -> dict:
    """Personas con el estado del bot "en turno" con un turno del primer corte (por operacion)."""
    from sqlalchemy import text

    rows = (await db.execute(text("""
        SELECT employee_id::text AS employee_id, status, check_in_at FROM workforce_attendance_status
        WHERE company_id = CAST(:c AS uuid) AND status = ANY(:s)
    """), {"c": company_id, "s": list(OPEN_STATES)})).mappings().all()
    out = {"Virginia": [], "Alabama": []}
    for r in rows:
        person = g["all"].get(r["employee_id"])
        if person and r["check_in_at"] and r["check_in_at"] < _first_cut_end(person):
            out[person["place"]].append(" ".join(person["full_name"].split()))
    return out


async def report(db, company_id: str = VOLTAGE) -> dict:
    from app.services import us_time

    p = await plan(db, company_id)
    g, fixes = p["groups"], p["fixes"]
    va = await figures(db, company_id, date(2026, 11, 1), date(2026, 11, 14))
    al = await figures(db, company_id, date(2026, 11, 2), date(2026, 11, 15))
    place_id = next(iter(g["new"].values()))["place_id"]
    rules = us_time.place_rules(va["rules"], place_id)
    new_lines, ok = [], rules.get("week_start_day") == "sunday"
    for pid, person in g["new"].items():
        b = va["rows"].get(pid, {"payable": 0, "regular": 0, "overtime": 0})
        a = table_after(person["label"], rules)
        want = EXPECTED[person["label"]]
        good = (a["payable"], a["regular"], a["overtime"]) == want[:3] and a["weeks"] == [w for w in want[3:] if w]
        ok = ok and good
        mine = [f for f in fixes if f.employee["id"] == pid and f.changes]
        new_lines.append({"label": person["label"], "name": " ".join(person["full_name"].split()), "before": (b["payable"], b["regular"], b["overtime"]),
                          "after": (a["payable"], a["regular"], a["overtime"]), "weeks_after": a["weeks"],
                          "days_replaced": sum(1 for f in mine if f.events), "days_created": sum(1 for f in mine if f.target and not f.events),
                          "days_emptied": sum(1 for f in mine if not f.target and f.events), "ok": good})
    zero_lines = [{"name": " ".join(z["full_name"].split()), "status": z["status"], "before": va["rows"].get(pid, {}).get("payable", 0),
                   "days": sum(1 for f in fixes if f.employee["id"] == pid and f.changes)} for pid, z in g["zero"].items()]
    zero_lines = [z for z in zero_lines if z["days"] or z["before"]]
    first_tot = _tot(va["rows"], g["first"])
    new_after = tuple(sum(x["after"][k] for x in new_lines) for k in range(3))
    va_after = tuple(first_tot[k] + new_after[k] for k in range(3))
    al_ids = [pid for pid, x in g["all"].items() if x["place"] == "Alabama"]
    al_tot = _tot(al["rows"], al_ids)
    al_people = sum(1 for pid in al_ids if al["rows"].get(pid, {}).get("payable"))
    unclosed = [f for f in fixes if f.kind == "sin_cerrar" and f.changes]
    ok = ok and first_tot == EXPECTED_FIRST_PART and va_after == EXPECTED_VIRGINIA and al_tot == EXPECTED_ALABAMA and al_people == 25
    ok = ok and len(g["first"]) + len(g["new"]) == EXPECTED_PEOPLE
    return {"new": new_lines, "zero": zero_lines, "first_part": first_tot, "virginia_after": va_after, "alabama": al_tot, "alabama_people": al_people,
            "unclosed": {pl: [{"name": " ".join(f.employee["full_name"].split()), "day": f.day.isoformat(), "events": len(f.events),
                               "open": f.events[-1]["kind"] != "check_out"} for f in unclosed if f.employee["place"] == pl] for pl in ("Virginia", "Alabama")},
            "open_statuses": await open_statuses(db, company_id, g), "people_with_hours": len(g["first"]) + len(g["new"]),
            "person_days": sum(1 for f in fixes if f.changes), "matches_expected": ok}


def print_report(r: dict) -> None:
    hm = A.hm
    print(f"Persona-dias a cambiar: {r['person_days']} · personas de Virginia con horas: {r['people_with_hours']}")
    print(f"{'Tabla':15} {'Nombre en el sistema':30} {'antes pag/reg/OT':>21} {'despues pag/reg/OT':>21} reemplazar/crear/vaciar  semanas")
    for x in r["new"]:
        b, a = x["before"], x["after"]
        print(f"{x['label']:15} {x['name'][:30]:30} {hm(b[0]):>7}/{hm(b[1]):>6}/{hm(b[2]):>6} {hm(a[0]):>7}/{hm(a[1]):>6}/{hm(a[2]):>6} "
              f"{x['days_replaced']:>4}/{x['days_created']:>3}/{x['days_emptied']:>3}  {' / '.join(hm(w) for w in x['weeks_after'])}  {'OK' if x['ok'] else 'NO CUADRA'}")
    print("Quedan en 0 (Virginia, 01-14/11):")
    for z in r["zero"]:
        print(f"   - {z['name']} ({z['status']}): tenia {hm(z['before'])} · {z['days']} dias")
    fp, va, al = r["first_part"], r["virginia_after"], r["alabama"]
    print(f"Primera parte (11): {hm(fp[0])}/{hm(fp[1])}/{hm(fp[2])}")
    print(f"TOTAL VIRGINIA 01-14 despues: {hm(va[0])}/{hm(va[1])}/{hm(va[2])}")
    print(f"ALABAMA 02-15 ({r['alabama_people']} personas): {hm(al[0])}/{hm(al[1])}/{hm(al[2])}")
    for pl in ("Virginia", "Alabama"):
        items = r["unclosed"][pl]
        print(f"Turnos sin cerrar del primer corte en {pl}: {len(items)}")
        for u in items:
            print(f"   - {u['name']} {u['day']} ({'abierto' if u['open'] else 'por confirmar'}, {u['events']} marcas)")
    print(f"Estados del bot en turno con un turno del primer corte: {r['open_statuses']}")
    print("CUADRA con los totales esperados" if r["matches_expected"] else "NO CUADRA: no aplicar")


async def verify(db, company_id: str = VOLTAGE) -> dict:
    g = await groups(db, company_id)
    va = await figures(db, company_id, date(2026, 11, 1), date(2026, 11, 14))
    al = await figures(db, company_id, date(2026, 11, 2), date(2026, 11, 15))
    wrong = []
    for pid, person in g["new"].items():
        want, got = EXPECTED[person["label"]], va["rows"].get(pid, {})
        if (got.get("payable"), got.get("regular"), got.get("overtime")) != want[:3]:
            wrong.append((person["label"], got.get("payable"), got.get("regular"), got.get("overtime")))
    zero_left = [z["full_name"] for pid, z in g["zero"].items() if va["rows"].get(pid, {}).get("payable")]
    va_ids = list(g["first"]) + list(g["new"])
    al_ids = [pid for pid, x in g["all"].items() if x["place"] == "Alabama"]
    held = {pl: sum(1 for h in (va if pl == "Virginia" else al)["held"] if (g["all"].get(str(h.get("employee_id"))) or {}).get("place") == pl) for pl in ("Virginia", "Alabama")}
    va2 = await figures(db, company_id, date(2026, 11, 15), date(2026, 11, 28))
    al2 = await figures(db, company_id, date(2026, 11, 16), date(2026, 11, 29))
    return {"wrong": wrong, "zero_with_hours": zero_left, "virginia_01_14": _tot(va["rows"], va_ids),
            "virginia_people": sum(1 for pid in va_ids if va["rows"].get(pid, {}).get("payable")),
            "alabama_02_15": _tot(al["rows"], al_ids), "held_first_cut": held, "open_statuses": await open_statuses(db, company_id, g),
            "virginia_15_28_payable": sum(v["payable"] for v in va2["rows"].values() if v["place"] == "Virginia"),
            "alabama_16_29_payable": sum(v["payable"] for v in al2["rows"].values() if v["place"] == "Alabama")}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--expected", type=int)
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
                print(A.dumps(await apply(db, expected=args.expected)))
            elif args.undo:
                print(A.dumps(await undo(db)))
            elif args.verify:
                print(A.dumps(await verify(db)))
            else:
                print_report(await report(db))
                print("PRUEBA: solo lectura. Para aplicar: --apply --expected 15")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
