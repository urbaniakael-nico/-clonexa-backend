"""Tiempo de una referencia: UNA sola regla que no depende de las fechas elegidas (068A).

Cada sesion se convierte primero en sus tramos trabajados, sin mirar ningun rango:
  sesion ∩ turno de esa persona (entrada a salida, o a la hora real confirmada) - pausas.
Despues, "En el periodo" es la parte de esos tramos que cae dentro de las fechas. Asi:
  - El total de la referencia es fijo.
  - Ampliar el rango nunca baja la cifra, porque solo agrega tramos.
  - El total del equipo es exactamente la suma de las filas por operario.

Sin cerrar (se muestran y NO se suman hasta que se cierren o confirmen):
  - la sesion sigue abierta;
  - la sesion termino con un turno que nomina retiene sin confirmar (cerrado por el sistema o
    mas largo que la jornada: la misma regla _cx_check_shift_049D de nomina).
Un tramo de ese mismo turno con hora de cambio real (la persona cambio de referencia) si cuenta.

No hay ningun tope repartido en proporcion: ese fue el origen de la fluctuacion.
Funciones puras salvo load(). Todo por company_id.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

OPEN = "abierta"
HOLD = "turno_sin_confirmar"
# Una sesion que termina con el turno lleva la hora de salida del turno: margen por el orden de los eventos.
END_WITH_SHIFT_MARGIN = timedelta(minutes=2)
Segment = tuple[datetime, datetime]


def as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def build_shifts(events: Iterable[dict], classify, check_shift, is_system_cutoff, verification: dict) -> dict[str, list[dict]]:
    """Turnos por persona con sus pausas y el veredicto de nomina.

    classify(ev) -> check_in | break_start | break_end | check_out | otro.
    Un turno sin salida sigue abierto (end None) hasta la siguiente entrada de esa persona."""
    shifts: dict[str, list[dict]] = {}
    current: dict[str, dict] = {}
    for ev in sorted((e for e in events if as_utc(e.get("occurred_at"))), key=lambda e: as_utc(e["occurred_at"])):
        emp = str(ev.get("employee_id") or "")
        at = as_utc(ev["occurred_at"])
        kind = classify(ev)
        if not emp:
            continue
        if kind == "check_in":
            abandoned = current.get(emp)
            if abandoned:
                abandoned["end"] = at  # entro de nuevo sin marcar salida: ese turno no sigue abierto para siempre
            shift = {"start": at, "end": None, "breaks": [], "pause": None, "ref": str(ev.get("id") or ""), "verdict": "open", "real_end": None}
            shifts.setdefault(emp, []).append(shift)
            current[emp] = shift
            continue
        shift = current.get(emp)
        if not shift:
            continue
        if kind == "break_start":
            shift["pause"] = shift["pause"] or at
        elif kind == "break_end" and shift["pause"]:
            shift["breaks"].append((shift["pause"], at))
            shift["pause"] = None
        elif kind == "check_out":
            if shift["pause"]:
                shift["breaks"].append((shift["pause"], at))
                shift["pause"] = None
            shift["end"] = at
            verdict, closure = check_shift(verification, "attendance", shift["ref"], shift["start"], at, is_system_cutoff(ev))
            shift["verdict"] = verdict
            shift["real_end"] = as_utc((closure or {}).get("real_end_at")) if verdict == "confirmed" else None
            current.pop(emp, None)
    for items in shifts.values():
        for shift in items:
            if shift["pause"]:
                shift["breaks"].append((shift["pause"], None))  # pausa abierta: corre hasta el fin de la sesion
    return shifts


def subtract_breaks(lo: datetime, hi: datetime, breaks: Iterable[tuple[datetime, Optional[datetime]]]) -> list[Segment]:
    """[lo, hi] sin las pausas. Una pausa sin fin llega hasta hi."""
    pieces: list[Segment] = []
    cursor = lo
    for b_start, b_end in sorted(breaks, key=lambda b: b[0]):
        b_end = b_end or hi
        if b_end <= cursor or b_start >= hi:
            continue
        if b_start > cursor:
            pieces.append((cursor, b_start))
        cursor = max(cursor, b_end)
    if cursor < hi:
        pieces.append((cursor, hi))
    return pieces


def session_segments(start: datetime, end: datetime, shifts: list[dict]) -> tuple[list[Segment], Optional[str]]:
    """Tramos trabajados de una sesion cerrada y, si hay parte sin confirmar, ese motivo."""
    overlapping = [s for s in shifts if s["start"] < end and (s["end"] is None or s["end"] > start)]
    if not overlapping:
        return [(start, end)], None  # sesion sin turno registrado: cuenta tal cual
    out: list[Segment] = []
    reason = None
    for shift in overlapping:
        if shift["verdict"] == "hold" and end >= shift["end"] - END_WITH_SHIFT_MARGIN:
            reason = HOLD
            continue
        limit = shift["real_end"] if shift["verdict"] == "confirmed" and shift["real_end"] else (shift["end"] or end)
        lo, hi = max(start, shift["start"]), min(end, limit)
        if hi > lo:
            out.extend(subtract_breaks(lo, hi, shift["breaks"]))
    return out, reason


def resolve_sessions(sessions: Iterable[dict], shifts_by_employee: dict[str, list[dict]], key_of) -> list[dict]:
    """Cada sesion con sus tramos. Si dos sesiones de la misma persona se pisan, el tiempo
    repetido cuenta una sola vez (duplicados)."""
    out: list[dict] = []
    ordered = sorted((s for s in sessions if as_utc(s.get("started_at"))), key=lambda s: (str(s.get("employee_id") or ""), as_utc(s["started_at"])))
    cursor_emp, cursor = None, None
    for s in ordered:
        emp = str(s.get("employee_id") or "")
        if emp != cursor_emp:
            cursor_emp, cursor = emp, None
        started, ended = as_utc(s["started_at"]), as_utc(s.get("ended_at"))
        item = {"employee_id": emp, "person": str(s.get("employee_name") or "").strip() or "—", "key": key_of(s.get("reference_name")),
                "name": str(s.get("reference_name") or ""), "started": started, "ended": ended, "segments": [], "unclosed": None}
        if ended is None or str(s.get("status") or "").strip().lower() == "active":
            item["unclosed"] = OPEN
            out.append(item)
            continue
        start = max(started, cursor) if cursor else started
        cursor = max(cursor, ended) if cursor else ended
        if ended > start:
            item["segments"], item["unclosed"] = session_segments(start, ended, shifts_by_employee.get(emp, []))
        out.append(item)
    return out


def overlap_seconds(segments: Iterable[Segment], lo: Optional[datetime] = None, hi: Optional[datetime] = None) -> float:
    total = 0.0
    for a, b in segments:
        x, y = max(a, lo) if lo else a, min(b, hi) if hi else b
        if y > x:
            total += (y - x).total_seconds()
    return total


def summarize(items: list[dict], lo: Optional[datetime], hi: Optional[datetime]) -> dict[str, dict]:
    """{key: {name, total_seconds, period_seconds, people, unclosed, sessions}}.
    Los totales del equipo son la suma de las filas por operario, ya en segundos enteros."""
    out: dict[str, dict] = {}
    raw: dict[str, dict[str, dict]] = {}
    for it in items:
        ref = out.setdefault(it["key"], {"key": it["key"], "name": it["name"], "total_seconds": 0, "period_seconds": 0, "people": [], "unclosed": [],
                                         "sessions": 0, "first": None, "last": None})
        ref["sessions"] += 1
        ref["first"] = min(ref["first"], it["started"]) if ref["first"] else it["started"]
        last = it["ended"] or it["started"]
        ref["last"] = max(ref["last"], last) if ref["last"] else last
        person = raw.setdefault(it["key"], {}).setdefault(it["employee_id"] or it["person"], {"employee_id": it["employee_id"], "name": it["person"], "total": 0.0, "period": 0.0})
        person["total"] += overlap_seconds(it["segments"])
        person["period"] += overlap_seconds(it["segments"], lo, hi)
        if it["unclosed"]:
            ref["unclosed"].append({"name": it["person"], "started": it["started"].isoformat(), "ended": it["ended"].isoformat() if it["ended"] else None,
                                    "reason": it["unclosed"]})
    for key, ref in out.items():
        rows = [{"employee_id": p["employee_id"], "name": p["name"], "total_seconds": int(p["total"]), "period_seconds": int(p["period"])} for p in raw[key].values()]
        rows.sort(key=lambda r: (-r["total_seconds"], r["name"].lower()))
        ref["people"] = [r for r in rows if r["total_seconds"] > 0]
        ref["total_seconds"] = sum(r["total_seconds"] for r in rows)
        ref["period_seconds"] = sum(r["period_seconds"] for r in rows)
        ref["first"] = ref["first"].isoformat() if ref["first"] else None
        ref["last"] = ref["last"].isoformat() if ref["last"] else None
    return out


def period_bounds(start: date, end: date, tz) -> tuple[datetime, datetime]:
    """Del inicio del primer dia al inicio del dia siguiente al ultimo, en la zona de la empresa (Bogota)."""
    lo = datetime.combine(start, datetime.min.time(), tzinfo=tz)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    return lo.astimezone(timezone.utc), hi.astimezone(timezone.utc)


def _classifier():
    from app.api.v1.endpoints import payroll as core

    def classify(ev: dict) -> str:
        kind = core.attendance_event_kind(ev)
        if core.is_check_in(kind):
            return "check_in"
        if core.is_break_start(kind):
            return "break_start"
        if core.is_break_end(kind):
            return "break_end"
        if core.is_check_out(kind):
            return "check_out"
        return "other"

    return classify, core


async def load(db: AsyncSession, company_id: str) -> list[dict]:
    """Las sesiones de la empresa ya resueltas en tramos. Sin LIMIT: lo que entra no depende del rango."""
    from app.services.references_v2 import group_key

    classify, core = _classifier()
    sessions = [dict(r) for r in (await db.execute(text("""
        SELECT employee_id, employee_name, reference_name, started_at, ended_at, status
        FROM reference_work_sessions WHERE company_id = :c
    """), {"c": str(company_id)})).mappings().all()]
    events = [dict(r) for r in (await db.execute(text("""
        SELECT id, employee_id, event_type, event_label, status_after, detail, payload_json, metadata_json,
               COALESCE(occurred_at, created_at) AS occurred_at
        FROM workforce_attendance_events WHERE company_id::text = :c
    """), {"c": str(company_id)})).mappings().all()]
    verification = await core._cx_verification_context_049D(db, company_id)
    shifts = build_shifts(events, classify, core._cx_check_shift_049D, core._cx_event_system_cutoff_049D, verification)
    return resolve_sessions(sessions, shifts, group_key)
