"""Tiempos de turno segun las reglas de EE. UU. (FLSA): UNA sola funcion para el bot,
Reportes, Nomina, PDF y CSV (interruptor us_payroll; hoy solo VOLTAGE).

Funcion pura, sin base de datos. Reglas:
- Cada marcacion cuenta al minuto que se ve (06:45:41 -> 06:45). Asi la entrada, las
  pausas y la salida que ve la persona suman exacto, sin redondeos a 15 min.
- Todas las pausas son sin pago.
- Pagable = (salida - entrada) - pausas.
- Semana laboral fija de 7 dias; empieza el dia y la hora configurados (domingo 00:00
  por defecto) en la hora LOCAL del lugar de trabajo.
- Overtime = minutos pagables por encima del limite semanal (40 h), asignados en orden
  cronologico: los minutos despues de la hora 40 son overtime. No hay extra por dia.
- Un turno que cruza la medianoche o el inicio de semana se reparte por dia y por
  semana en la hora local.
Nada aqui guarda ni cambia marcaciones: se calcula sobre las existentes.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_RULES = {"week_start_day": "sunday", "week_start_time": "00:00", "overtime_after_minutes": 40 * 60, "overtime_factor": 1.5}
ABBR = {
    "America/New_York": "ET", "America/Detroit": "ET", "America/Indiana/Indianapolis": "ET", "America/Kentucky/Louisville": "ET",
    "America/Chicago": "CT", "America/Indiana/Knox": "CT", "America/Menominee": "CT",
    "America/Denver": "MT", "America/Boise": "MT", "America/Phoenix": "MT",
    "America/Los_Angeles": "PT", "America/Anchorage": "AKT", "Pacific/Honolulu": "HT",
}


def rules_of(raw: Any) -> dict:
    """Reglas validadas con sus valores por defecto (lo que no sirve, se ignora)."""
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_RULES)
    day = str(raw.get("week_start_day") or "").strip().lower()
    if day in DAYS:
        out["week_start_day"] = day
    clock = str(raw.get("week_start_time") or "").strip()
    try:
        hh, mm = clock.split(":")
        if 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
            out["week_start_time"] = f"{int(hh):02d}:{int(mm):02d}"
    except ValueError:
        pass
    try:
        limit = int(raw.get("overtime_after_minutes"))
        if 60 <= limit <= 7 * 24 * 60:
            out["overtime_after_minutes"] = limit
    except (TypeError, ValueError):
        pass
    try:
        factor = float(raw.get("overtime_factor"))
        if 1 <= factor <= 3:
            out["overtime_factor"] = factor
    except (TypeError, ValueError):
        pass
    return out


def zone(name: Any, fallback: str = "America/Chicago") -> ZoneInfo:
    for candidate in (name, fallback, "America/Chicago"):
        try:
            if candidate:
                return ZoneInfo(str(candidate))
        except Exception:
            continue
    return ZoneInfo("UTC")


def abbr(tz_name: Any, at: Optional[datetime] = None) -> str:
    """ET / CT / MT / PT para EE. UU.; si no, la sigla que da la zona."""
    name = str(tz_name or "")
    if name in ABBR:
        return ABBR[name]
    local = (at or datetime.now(timezone.utc)).astimezone(zone(name))
    return local.tzname() or name


def minute(value: datetime) -> datetime:
    """La marcacion al minuto que se ve (sin segundos)."""
    value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0)


def week_start(local: datetime, rules: dict) -> datetime:
    """Inicio (aware, hora local) de la semana laboral que contiene `local`."""
    tz = local.tzinfo
    ws = DAYS.index(rules["week_start_day"])
    hh, mm = (int(x) for x in rules["week_start_time"].split(":"))
    back = (local.weekday() - ws) % 7
    start_day = local.date() - timedelta(days=back)
    start = datetime.combine(start_day, time(hh, mm), tzinfo=tz)
    if start > local:
        start = datetime.combine(start_day - timedelta(days=7), time(hh, mm), tzinfo=tz)
    return start


def _cuts(start: datetime, end: datetime, tz: ZoneInfo, rules: dict) -> list[datetime]:
    """Instantes (UTC) de medianoche local y de inicio de semana dentro de (start, end)."""
    hh, mm = (int(x) for x in rules["week_start_time"].split(":"))
    ws = DAYS.index(rules["week_start_day"])
    out = set()
    day = start.astimezone(tz).date()
    last = end.astimezone(tz).date() + timedelta(days=1)
    while day <= last:
        for local in [datetime.combine(day, time(0, 0), tzinfo=tz)] + ([datetime.combine(day, time(hh, mm), tzinfo=tz)] if day.weekday() == ws else []):
            instant = local.astimezone(timezone.utc)
            if start < instant < end:
                out.add(instant)
        day += timedelta(days=1)
    return sorted(out)


def _merge(breaks: Iterable[tuple[datetime, datetime]], start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    spans = sorted((max(a, start), min(b, end)) for a, b in breaks if a and b and min(b, end) > max(a, start))
    out: list[list[datetime]] = []
    for a, b in spans:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _mins(a: datetime, b: datetime) -> int:
    return max(0, int((b - a).total_seconds() // 60))


def split_shift(start: datetime, end: datetime, breaks: Iterable[tuple[datetime, Optional[datetime]]], tz_name: Any, rules: dict) -> dict:
    """Un turno cerrado -> totales y piezas por dia/semana local. Minutos enteros exactos."""
    tz = zone(tz_name)
    start, end = minute(start), minute(end)
    if end < start:
        end = start
    clean = _merge([(minute(a), minute(b if b else end)) for a, b in breaks if a], start, end)
    edges = [start] + _cuts(start, end, tz, rules) + [end]
    pieces = []
    for a, b in zip(edges, edges[1:]):
        if b <= a:
            continue
        connected = _mins(a, b)
        pause = sum(_mins(max(a, x), min(b, y)) for x, y in clean if min(b, y) > max(a, x))
        local = a.astimezone(tz)
        pieces.append({"start": a, "end": b, "date": local.date(), "week_start": week_start(local, rules),
                       "connected": connected, "pause": pause, "payable": max(0, connected - pause)})
    connected = _mins(start, end)
    pause = sum(_mins(x, y) for x, y in clean)
    return {"start": start, "end": end, "tz": str(tz.key), "breaks": clean, "pieces": pieces,
            "connected": connected, "pause": pause, "payable": max(0, connected - pause)}


def compute(shifts: list[dict], rules: Optional[dict] = None) -> list[dict]:
    """Reparte regular / overtime en orden cronologico por persona y semana laboral.

    Entrada: dicts con employee_id, start, end, breaks [(ini, fin)], tz (y cualquier otro
    dato, que se conserva). Salida: los mismos turnos con `split` (ver split_shift) y en
    cada pieza `regular` y `overtime`."""
    rules = rules_of(rules)
    limit = int(rules["overtime_after_minutes"])
    out = []
    for s in shifts:
        out.append({**s, "split": split_shift(s["start"], s["end"], s.get("breaks") or [], s.get("tz"), rules)})
    by_emp: dict[str, list[dict]] = {}
    for s in out:
        for p in s["split"]["pieces"]:
            by_emp.setdefault(str(s.get("employee_id")), []).append(p)
    for pieces in by_emp.values():
        used: dict[str, int] = {}
        for p in sorted(pieces, key=lambda x: x["start"]):
            key = p["week_start"].isoformat()
            before = used.get(key, 0)
            p["regular"] = max(0, min(p["payable"], limit - before))
            p["overtime"] = p["payable"] - p["regular"]
            used[key] = before + p["payable"]
    return out


def in_period(shifts: list[dict], start_day: Optional[date], end_day: Optional[date]) -> list[dict]:
    """Turnos con alguna pieza en [start_day, end_day] (dia local); cada turno trae
    `days` (solo las piezas del periodo) y sus totales del periodo."""
    out = []
    for s in shifts:
        days: dict[date, dict] = {}
        for p in s["split"]["pieces"]:
            if (start_day and p["date"] < start_day) or (end_day and p["date"] > end_day):
                continue
            d = days.setdefault(p["date"], {"date": p["date"], "week_start": p["week_start"], "connected": 0, "pause": 0, "payable": 0, "regular": 0, "overtime": 0})
            for k in ("connected", "pause", "payable", "regular", "overtime"):
                d[k] += p[k]
        if not days:
            continue
        rows = [days[k] for k in sorted(days)]
        totals = {k: sum(r[k] for r in rows) for k in ("connected", "pause", "payable", "regular", "overtime")}
        out.append({**s, "days": rows, **totals})
    return out


def weeks_of(period_shifts: list[dict]) -> list[dict]:
    """Semanas laborales de UNA persona: dias, pagable, regular (hasta 40) y overtime."""
    weeks: dict[str, dict] = {}
    for s in period_shifts:
        for d in s["days"]:
            key = d["week_start"].isoformat()
            w = weeks.setdefault(key, {"week_start": d["week_start"], "week_end": d["week_start"] + timedelta(days=7) - timedelta(minutes=1),
                                       "days": {}, "pause": 0, "payable": 0, "regular": 0, "overtime": 0})
            day = w["days"].setdefault(d["date"], {"date": d["date"], "payable": 0, "pause": 0, "regular": 0, "overtime": 0})
            for k in ("payable", "pause", "regular", "overtime"):
                day[k] += d[k]
                w[k] += d[k]
    out = []
    for key in sorted(weeks):
        w = weeks[key]
        out.append({**w, "days": [w["days"][k] for k in sorted(w["days"])]})
    return out


def hm(minutes: Any) -> str:
    m = max(0, int(minutes or 0))
    return f"{m // 60} h {m % 60:02d} min"
