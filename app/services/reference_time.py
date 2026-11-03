"""Tiempo por referencia (y por persona) en un periodo: UNA sola regla para Produccion v2
(pantalla y PDF), Produccion para las empresas con production_v2 y el CRM VELVET-LAB.

Regla (pedida por el dueño, octubre 2026):
- Periodo = desde las 00:00 del dia "Desde" hasta las 23:59:59 del dia "Hasta", hora
  de Bogota (America/Bogota), ambos dias incluidos: la ventana [inicio, fin).
- Turno = entrada -> salida con sus pausas (el mismo emparejamiento de la Nomina,
  payroll.build_closed_shifts). Trabajado = conectado - pausas (app.services.shift_times).
- Cada segundo TRABAJADO de una persona se atribuye a la referencia de su sesion de
  referencia vigente en ese segundo; si dos sesiones se solapan, la mas reciente manda
  desde que empezo (cambio de referencia: nunca se cuenta doble). Lo trabajado sin
  sesion de referencia es "Sin referencia".
- La atribucion NO depende del periodo; el periodo solo recorta. Por eso ampliar el
  periodo nunca reduce un tiempo, y lo que cruza un borde (sesion, turno o pausa) se
  recorta exactamente en el borde.
- Turno, pausa o sesion abiertos cuentan hasta "ahora" (y la ventana termina en
  min(fin, ahora)): solo suman si el periodo incluye hoy.
- Sin tope de nomina ni prorrateos.

Solo lectura: no cambia ningun dato guardado. Los registros raros (turnos o pausas sin
cierre, sesiones solapadas, sesiones fuera de turno) se listan en `anomalies`.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from app.services import shift_times

TZ = ZoneInfo("America/Bogota")
LOOKBACK = timedelta(days=7)  # turnos y sesiones que empezaron antes del periodo y lo cruzan
LONG_OPEN = timedelta(hours=16)  # un turno o una sesion abiertos mas que esto es raro
NO_REFERENCE = "Sin referencia"
Interval = tuple[datetime, datetime]


# ------------------------------------------------------------------ ventana
def window(start: date, end: date) -> tuple[datetime, datetime]:
    """[00:00 de Desde, 00:00 del dia siguiente a Hasta) en Bogota, en UTC."""
    lo = datetime.combine(start, time.min, tzinfo=TZ)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=TZ)
    return lo.astimezone(timezone.utc), hi.astimezone(timezone.utc)


# ------------------------------------------------------------- intervalos
def _merge(items: Iterable[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for a, b in sorted((a, b) for a, b in items if b > a):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _subtract(base: list[Interval], cuts: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    cuts = _merge(cuts)
    for a, b in base:
        cur = a
        for c, d in cuts:
            if d <= cur or c >= b:
                continue
            if c > cur:
                out.append((cur, c))
            cur = max(cur, d)
            if cur >= b:
                break
        if cur < b:
            out.append((cur, b))
    return out


def _clip(items: Iterable[Interval], lo: datetime, hi: datetime) -> list[Interval]:
    return [(max(a, lo), min(b, hi)) for a, b in items if min(b, hi) > max(a, lo)]


def _seconds(items: Iterable[Interval]) -> int:
    return int(sum((b - a).total_seconds() for a, b in items))


# ------------------------------------------------------------------ turnos
def build_shifts(events: list[dict], now: datetime) -> tuple[dict[str, list[dict]], list[dict]]:
    """Eventos de asistencia -> turnos por persona: {"start", "end" (None si abierto),
    "breaks": [(inicio, fin|None)]}. Mismo emparejamiento que payroll.build_closed_shifts
    (una entrada con un turno abierto reemplaza al anterior; la salida cierra la pausa
    abierta), pero conserva el turno abierto y las pausas como intervalos.
    events: {employee_id, kind: check_in|check_out|break_start|break_end, at}."""
    shifts: dict[str, list[dict]] = {}
    open_: dict[str, dict] = {}
    anomalies: list[dict] = []
    for ev in sorted((e for e in events if e.get("at") and e.get("employee_id")), key=lambda e: e["at"]):
        who, kind, at = str(ev["employee_id"]), ev["kind"], ev["at"]
        cur = open_.get(who)
        if kind == "check_in":
            if cur:
                anomalies.append({"kind": "entrada_sin_salida", "employee_id": who, "at": cur["start"],
                                  "detail": "turno sin salida: lo reemplaza la entrada siguiente (como en la Nomina)"})
                shifts[who].remove(cur)
            cur = {"start": at, "end": None, "breaks": [], "_pause": None}
            open_[who] = cur
            shifts.setdefault(who, []).append(cur)
        elif cur is None:
            if kind in ("check_out", "break_end", "break_start"):
                anomalies.append({"kind": f"{kind}_fuera_de_turno", "employee_id": who, "at": at, "detail": "evento sin turno abierto (no cuenta)"})
        elif kind == "break_start":
            if cur["_pause"] is None:
                cur["_pause"] = at
            else:
                anomalies.append({"kind": "pausa_repetida", "employee_id": who, "at": at, "detail": "pausa dentro de otra pausa (se ignora)"})
        elif kind == "break_end":
            if cur["_pause"] is not None:
                cur["breaks"].append((cur["_pause"], at))
                cur["_pause"] = None
            else:
                anomalies.append({"kind": "retorno_sin_pausa", "employee_id": who, "at": at, "detail": "retorno sin pausa abierta (se ignora)"})
        elif kind == "check_out":
            if cur["_pause"] is not None:
                anomalies.append({"kind": "pausa_sin_fin", "employee_id": who, "at": cur["_pause"], "detail": "pausa sin retorno: la cierra la salida"})
                cur["breaks"].append((cur["_pause"], at))
                cur["_pause"] = None
            cur["end"] = at
            open_.pop(who, None)
    for who, cur in open_.items():
        if cur["_pause"] is not None:
            cur["breaks"].append((cur["_pause"], None))
        if now - cur["start"] > LONG_OPEN:
            anomalies.append({"kind": "turno_sin_cierre", "employee_id": who, "at": cur["start"],
                              "detail": f"turno abierto hace {int((now - cur['start']).total_seconds() // 3600)} h"})
    for items in shifts.values():
        for s in items:
            s.pop("_pause", None)
    return shifts, anomalies


def worked_intervals(shifts: list[dict], now: datetime) -> list[Interval]:
    """Lo trabajado de una persona = cada turno (abierto: hasta ahora) menos sus pausas
    (abierta: hasta el fin del turno). Igual que shift_times: conectado - pausas."""
    out: list[Interval] = []
    for s in shifts:
        end = min(s["end"] or now, now)
        if end <= s["start"]:
            continue
        pauses = [(a, min(b or end, end)) for a, b in s["breaks"] if a]
        out.extend(_subtract([(s["start"], end)], pauses))
    return _merge(out)


# ------------------------------------------------------------------ calculo
def compute(*, start: date, end: date, now: datetime, shifts: dict[str, list[dict]], sessions: list[dict],
            names: Optional[dict[str, str]] = None) -> dict:
    """Calculo puro. sessions: {employee_id, reference_name, started_at, ended_at|None, id?}.
    -> {"by_reference": {ref: s}, "by_person": {persona: {ref|Sin referencia: s}}, "worked": {persona: s},
        "no_reference": s, "total_worked": s, "sessions": {ref: {"sessions", "active", "people"}}, "anomalies": [...]}."""
    lo, hi = window(start, end)
    hi_eff = min(hi, now)
    names = names or {}
    by_person_sessions: dict[str, list[dict]] = {}
    for s in sessions:
        if s.get("started_at") and s.get("employee_id"):
            by_person_sessions.setdefault(str(s["employee_id"]), []).append(s)
    people = set(shifts) | set(by_person_sessions)
    by_reference: dict[str, int] = {}
    by_person: dict[str, dict[str, int]] = {}
    worked_total: dict[str, int] = {}
    stats: dict[str, dict] = {}
    anomalies: list[dict] = []
    for who in sorted(people):
        worked = worked_intervals(shifts.get(who, []), now)
        worked_in = _clip(worked, lo, hi_eff)
        on_shift = _merge((s["start"], min(s["end"] or now, now)) for s in shifts.get(who, []))  # turno con pausas incluidas
        rows = sorted(by_person_sessions.get(who, []), key=lambda r: r["started_at"])
        assigned: list[Interval] = []
        mine: dict[str, int] = {}
        for i, r in enumerate(rows):
            ref = str(r.get("reference_name") or "").strip() or NO_REFERENCE
            s_end = min(r.get("ended_at") or now, now)
            nxt = rows[i + 1]["started_at"] if i + 1 < len(rows) else None
            if nxt is not None and nxt < s_end:
                anomalies.append({"kind": "sesiones_solapadas", "employee_id": who, "at": nxt, "reference": ref,
                                  "detail": f"empieza otra sesion antes de cerrar esta ({int((s_end - nxt).total_seconds() // 60)} min solapados): manda la nueva"})
                s_end = nxt
            if r.get("ended_at") is None and now - r["started_at"] > LONG_OPEN:
                anomalies.append({"kind": "sesion_sin_cierre", "employee_id": who, "at": r["started_at"], "reference": ref,
                                  "detail": f"sesion de referencia abierta hace {int((now - r['started_at']).total_seconds() // 3600)} h"})
            span = [(r["started_at"], s_end)] if s_end > r["started_at"] else []
            inside = _clip(_intersect(span, worked), lo, hi_eff)
            outside = _clip(_subtract(span, on_shift), lo, hi_eff)
            if outside and _seconds(outside) >= 60:
                anomalies.append({"kind": "sesion_fuera_de_turno", "employee_id": who, "at": r["started_at"], "reference": ref,
                                  "seconds": _seconds(outside),
                                  "detail": f"{_seconds(outside) // 60} min de la sesion caen fuera del turno (sin entrada o despues de la salida): no cuentan"})
            secs = _seconds(inside)
            touched = _clip(span, lo, hi_eff) or (r.get("ended_at") is None and r["started_at"] < hi_eff)
            if touched:
                st = stats.setdefault(ref, {"sessions": 0, "active": 0, "people": set()})
                st["sessions"] += 1
                st["active"] += 1 if r.get("ended_at") is None else 0
                st["people"].add(who)
            if secs:
                mine[ref] = mine.get(ref, 0) + secs
                assigned.extend(inside)
        total = _seconds(worked_in)
        free = max(0, total - _seconds(_merge(assigned)))
        if free:
            mine[NO_REFERENCE] = mine.get(NO_REFERENCE, 0) + free
        if mine or total:
            by_person[who] = mine
            worked_total[who] = total
        for ref, secs in mine.items():
            by_reference[ref] = by_reference.get(ref, 0) + secs
    for a in anomalies:
        a["person"] = names.get(a["employee_id"], "")
    return {"window": {"from": lo, "to": hi, "until": hi_eff}, "by_reference": by_reference, "by_person": by_person,
            "worked": worked_total, "no_reference": by_reference.get(NO_REFERENCE, 0), "total_worked": sum(worked_total.values()),
            "sessions": {k: {**v, "people": len(v["people"])} for k, v in stats.items()}, "anomalies": anomalies}


def _intersect(a: list[Interval], b: list[Interval]) -> list[Interval]:
    out = []
    for x, y in a:
        for c, d in b:
            lo, hi = max(x, c), min(y, d)
            if hi > lo:
                out.append((lo, hi))
    return _merge(out)


# ------------------------------------------------------------------ datos
_KIND = {"check_in": "check_in", "check_out": "check_out", "break_start": "break_start", "break_end": "break_end"}


async def load(db: Any, company_id: str, start: date, end: date, now: Optional[datetime] = None) -> dict:
    """Lee asistencia, pausas y sesiones de referencia de la empresa y aplica compute().
    Toda consulta filtra por company_id. No escribe nada."""
    from sqlalchemy import text

    from app.api.v1.endpoints.payroll import attendance_event_kind

    now = now or datetime.now(timezone.utc)
    lo, hi = window(start, end)
    # Todo lo ocurrido hasta AHORA (no hasta el fin del periodo): asi el emparejamiento de turnos y
    # sesiones no depende del periodo elegido y ampliar "Hasta" nunca cambia lo ya atribuido.
    since, until = lo - LOOKBACK, max(now, hi) + timedelta(seconds=1)
    events = []
    for r in (await db.execute(text("""
        SELECT employee_id::text AS employee_id, event_type, event_label, status_after, COALESCE(occurred_at, created_at) AS at
        FROM workforce_attendance_events
        WHERE company_id::text = :c AND employee_id IS NOT NULL
          AND COALESCE(occurred_at, created_at) >= :since AND COALESCE(occurred_at, created_at) < :until
    """), {"c": str(company_id), "since": since, "until": until})).mappings().all():
        kind = _KIND.get(attendance_event_kind(dict(r)))
        if kind:
            events.append({"employee_id": r["employee_id"], "kind": kind, "at": r["at"]})
    shifts, anomalies = build_shifts(events, now)
    sessions = [dict(r) for r in (await db.execute(text("""
        SELECT id::text AS id, employee_id::text AS employee_id, COALESCE(reference_name, '') AS reference_name, started_at, ended_at
        FROM reference_work_sessions
        WHERE company_id::text = :c AND employee_id IS NOT NULL AND started_at < :until
          AND (started_at >= :since OR ended_at IS NULL OR ended_at > :since)
    """), {"c": str(company_id), "since": since, "until": until})).mappings().all()]
    names = {r["id"]: r["name"] for r in (await db.execute(text("""
        SELECT id::text AS id, COALESCE(full_name, '') AS name FROM employees WHERE company_id::text = :c
    """), {"c": str(company_id)})).mappings().all()}
    out = compute(start=start, end=end, now=now, shifts=shifts, sessions=sessions, names=names)
    for a in anomalies:
        a["person"] = names.get(a["employee_id"], "")
    out["anomalies"] = anomalies + out["anomalies"]
    out["names"] = names
    return out


def worked_seconds_between(start: datetime, end: datetime, breaks: Iterable[shift_times.Break], now: datetime) -> int:
    """Atajo a la definicion unica (shift_times) para quien ya tiene un turno armado."""
    return shift_times.worked_seconds_between(start, end, breaks, now)
