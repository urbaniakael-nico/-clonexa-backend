"""Board de gerencia de Reportes (interruptor reports_board; hoy solo VOLTAGE).

Todo lo que registran los operarios, por operacion (lugar de trabajo) y en orden A-Z, en
una sola respuesta. Las horas salen de us_payroll.snapshot, la MISMA funcion de Nomina
(app.services.us_time): overtime por encima de 40 h en la semana, pausas sin pago, minutos
exactos y hora del lugar. Reportes NO lleva dinero: aqui no sale tarifa, bruto ni neto.

Las horas cuentan como en Nomina: turnos cerrados y confirmados. Un turno abierto o por
confirmar se ve en "Ahora", en las alertas y en la linea de tiempo, pero no suma horas.
Toda consulta filtra por company_id; un supervisor solo recibe su operacion.
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import us_payroll, us_time, work_location_geo as geo, work_locations

NONE_KEY = work_locations.NONE_KEY
NO_PLACE = "Sin lugar asignado"
LIVE_DAYS = 14  # cuanto hacia atras se busca un turno que siga abierto o por confirmar
MAX_DAYS = 186
GPS_LABEL = us_payroll.GPS_LABEL
MARK_LABEL = {"in": "Entrada", "pause": "Pausa", "resume": "Retomar", "out": "Salida"}
NOTE_KINDS = {"summary", "manual_close", "note", "confirmed"}
ACCESS_ROLES = work_locations.OWNER_ROLES | work_locations.DIRECTOR_ROLES | work_locations.SUPERVISOR_ROLES | {"admin", "administrador"}
ALL_PLACES_ROLES = ACCESS_ROLES - work_locations.SUPERVISOR_ROLES
MANAGE_ROLES = work_locations.MANAGE_ROLES | {"admin", "administrador"}


# ------------------------------------------------------------------ reglas puras
def sort_key(name: Any) -> str:
    """A-Z sin distinguir mayusculas ni tildes, ignorando comillas o signos iniciales."""
    plain = unicodedata.normalize("NFKD", str(name or ""))
    plain = "".join(c for c in plain if not unicodedata.combining(c)).casefold()
    return plain.lstrip(" \"'`´.,-_")


def parse_period(start: Optional[date], end: Optional[date], today: date) -> tuple[date, date]:
    start = start or today
    end = end or start
    if end < start:
        raise ValueError("La fecha final no puede ser antes de la inicial.")
    if (end - start).days > MAX_DAYS:
        raise ValueError(f"El periodo máximo es de {MAX_DAYS} días.")
    return start, end


def _mark(view: Optional[dict], kind: str, has_perimeter: bool, exempt: bool = False) -> Optional[dict]:
    """Una marca compacta. Mientras el lugar no tenga perimetro (o la marca no se haya
    medido con el) dice Sin perimetro; sin coordenadas, Sin ubicacion. exempt: la puso un
    supervisor o el sistema, nadie estaba marcando: no lleva estado de ubicacion."""
    if not view:
        return None
    loc = view.get("location") or {}
    status = loc.get("status") or "none"
    if status not in ("none", "adjusted") and (not has_perimeter or not loc.get("geo")):
        status = "unconfigured"
    out = {"k": kind, "t": view["local"], "d": view["date"], "a": view["abbr"], "at": view["at"], "s": None if exempt else status, "o": view.get("origin") or ("" if exempt else "app")}
    if loc.get("lat") is not None and loc.get("lng") is not None:
        out.update({"lat": loc["lat"], "lng": loc["lng"]})
    if status == "inside" and loc.get("perimeter"):
        out["n"] = loc["perimeter"]
    return out


def shift_out(view: dict, has_perimeter: bool, state: str = "ok") -> dict:
    """Linea de tiempo de un turno (de us_payroll.shift_view) lista para Board, PDF y CSV.
    state: ok | held (por confirmar) | running (abierto)."""
    manual = view.get("manual_close")
    exempt_out = bool(manual or view.get("system_cutoff") or view.get("confirmed"))
    pauses = []
    for p in view.get("pauses") or []:
        auto = bool(p.get("closed_by_checkout"))
        pauses.append({"start": _mark(p.get("start"), "pause", has_perimeter), "end": None if auto else _mark(p.get("end"), "resume", has_perimeter),
                       "minutes": int(p.get("minutes") or 0), "auto": auto})
    notes = []
    for n in view.get("notes") or []:
        if not str(n.get("text") or "").strip():
            continue
        at = us_payroll._dt(n.get("at"))
        day = at.astimezone(us_time.zone(view["tz"])).date().isoformat() if at else None
        notes.append({"kind": n.get("kind"), "label": n.get("label") or "", "text": str(n.get("text")).strip(), "t": n.get("local") or "", "d": day,
                      "a": view["abbr"], "at": n.get("at")})
    return {
        **({"adjusted": True} if view.get("adjusted") else {}), "state": state, "in": _mark(view.get("check_in"), "in", has_perimeter),
        "out": None if state == "running" else _mark(view.get("check_out"), "out", has_perimeter, exempt=exempt_out),
        "pauses": pauses, "notes": notes,
        "manual": {"by": manual.get("by") or "", "note": manual.get("note") or ""} if manual else None,
        "system_cutoff": bool(view.get("system_cutoff")), "confirmed": bool(view.get("confirmed")),
        "connected": int(view.get("connected_minutes") or 0), "pause": int(view.get("pause_minutes") or 0),
        "payable": int(view.get("payable_minutes") or 0), "overtime": int(view.get("overtime_minutes") or 0),
    }


def _marks_of(shift: dict) -> list[dict]:
    out = [shift["in"]] if shift.get("in") else []
    for p in shift.get("pauses") or []:
        out += [m for m in (p.get("start"), p.get("end")) if m]
    if shift.get("out"):
        out.append(shift["out"])
    return out


def now_chip(state: str, **extra: Any) -> dict:
    return {"state": state, **extra}


def recount(people: list[dict]) -> dict:
    """Estado en vivo de un grupo de personas (lo repite el navegador cada 60 s)."""
    states = [p["now"]["state"] for p in people]
    return {"working": states.count("working"), "on_break": states.count("on_break"), "no_shift": states.count("no_shift"),
            "open_over": sum(1 for p in people if p["now"].get("over_limit"))}


def figures_of(people: list[dict]) -> dict:
    live = recount(people)
    keys = ("connected", "pause", "payable", "overtime", "outside", "no_location", "notes", "materials", "held")
    return {**live, **{k: sum(int(p.get(k) or 0) for p in people) for k in keys},
            "to_confirm": sum(int(p.get("held") or 0) for p in people) + live["open_over"]}


def alerts_of(person: dict, weeks: list[dict], near_ot: int, start: date, end: date, tz_name: str) -> list[dict]:
    """Alertas de UNA persona, cada una con hora: fuera de perimetro, sin ubicacion, turno por
    confirmar (mas horas que el limite de la empresa o sin salida) y cerca de overtime."""
    base = {"employee_id": person["id"], "employee": person["name"]}
    out: list[dict] = []
    for day in person["days"]:
        for s in day["shifts"]:
            for m in _marks_of(s):
                if m["s"] == "outside":
                    out.append({**base, "kind": "outside", "mark": MARK_LABEL[m["k"]], "t": m["t"], "d": m["d"], "a": m["a"], "at": m["at"]})
                elif m["s"] == "none":
                    out.append({**base, "kind": "no_location", "mark": MARK_LABEL[m["k"]], "t": m["t"], "d": m["d"], "a": m["a"], "at": m["at"]})
            if s["state"] == "held" and s.get("in"):
                out.append({**base, "kind": "to_confirm", "t": s["in"]["t"], "d": s["in"]["d"], "a": s["in"]["a"], "at": s["in"]["at"], "minutes": s["connected"]})
    live = person["now"]
    if live.get("over_limit") and live.get("since"):
        since = live["since"]
        out.append({**base, "kind": "to_confirm", "open": True, "t": since["t"], "d": since["d"], "a": since["a"], "at": since["at"], "minutes": live.get("minutes") or 0})
    zone = us_time.zone(tz_name)
    for w in weeks:
        first = date.fromisoformat(w["week_start"])
        if first > end or first + timedelta(days=6) < start or w["payable"] < near_ot:
            continue
        last = w["last_end"].astimezone(zone)
        out.append({**base, "kind": "near_overtime", "t": last.strftime("%H:%M"), "d": last.date().isoformat(), "a": us_time.abbr(tz_name, w["last_end"]),
                    "at": us_payroll.iso(w["last_end"]), "minutes": w["payable"], "week_start": w["week_start"]})
    return out


def _period_days(start: date, end: date, per_day: dict[str, dict]) -> list[dict]:
    if (end - start).days > 62:
        return [{"date": k, **v} for k, v in sorted(per_day.items())]
    return [{"date": (start + timedelta(days=i)).isoformat(), **per_day.get((start + timedelta(days=i)).isoformat(), {"payable": 0, "pause": 0})}
            for i in range((end - start).days + 1)]


def order_operations(locations: list[dict]) -> list[dict]:
    """De este a oeste, igual que Nomina; empate por el orden configurado."""
    ref = datetime(2026, 1, 15, tzinfo=timezone.utc)

    def offset(loc: dict) -> float:
        value = ref.astimezone(us_time.zone(loc.get("timezone"))).utcoffset() or timedelta(0)
        return -value.total_seconds()

    return sorted(locations, key=lambda loc: (offset(loc), int(loc.get("sort_order") or 0), str(loc.get("name") or "").casefold()))


# ------------------------------------------------------------------ estado en vivo
async def _policy_hours(db: AsyncSession, company_id: Any) -> float:
    """Limite de turno de la empresa (alert_after_hours), la misma regla de "por confirmar"."""
    from app.api.v1.endpoints import payroll as core

    ctx = await core._cx_verification_context_049D(db, company_id)
    return float(ctx["limit_seconds"]) / 3600


def running_view(s: dict, now: datetime, rule: dict) -> tuple[Optional[dict], Optional[dict]]:
    """Un turno abierto como si cerrara ahora: su vista y sus minutos (no entra a Nomina).
    (None, None) si empezo en este mismo minuto: aun no tiene minutos que contar."""
    pause_open = s.get("pause_open")
    current = {**s, "end": now,
               "breaks": list(s.get("breaks") or []) + ([(pause_open["occurred_at"], now)] if pause_open else []),
               "break_events": list(s.get("break_events") or []) + ([(pause_open, None)] if pause_open else [])}
    computed = us_time.in_period(us_time.compute([current], rule), None, None)
    if not computed:
        return None, None
    return us_payroll.shift_view(computed[0]), computed[0]


async def live_state(db: AsyncSession, company_id: Any, now: datetime, rule: dict) -> dict:
    """Estado de cada persona AHORA, con las marcaciones de los ultimos dias."""
    from app.api.v1.endpoints import payroll as core

    data = await us_payroll.load(db, company_id, now - timedelta(days=LIVE_DAYS), now)
    verification = await core._cx_verification_context_049D(db, company_id)
    limit_min = int(round(float(verification["limit_seconds"]) / 60))
    state: dict[str, dict] = {}
    held: set[str] = set()
    closed_today: dict[str, dict] = {}
    for s in data["shifts"]:
        verdict, _ = core._cx_check_shift_049D(verification, "attendance", s["check_in"]["id"], s["start"], s["end"],
                                               core._cx_event_system_cutoff_049D(s.get("check_out") or {}))
        if verdict == "hold":
            held.add(s["employee_id"])
        zone = us_time.zone(s["tz"])
        if s["end"].astimezone(zone).date() == now.astimezone(zone).date():
            if s["employee_id"] not in closed_today or s["end"] > closed_today[s["employee_id"]]["end"]:
                closed_today[s["employee_id"]] = {"end": s["end"], "tz": s["tz"]}
    open_views: dict[str, dict] = {}
    for s in data["open_shifts"]:
        eid = s["employee_id"]
        view, totals = running_view(s, now, rule)
        totals = totals or {"connected": 0, "payable": 0}
        if view:
            open_views[eid] = view
        start = us_time.minute(s["start"])
        tz, ab = s["tz"], us_time.abbr(s["tz"], start)
        local = start.astimezone(us_time.zone(tz))
        since = {"t": local.strftime("%H:%M"), "d": local.date().isoformat(), "a": ab, "at": us_payroll.iso(start), "o": us_payroll.origin_of(s.get("check_in")) or "app"}
        if totals["connected"] >= limit_min:
            state[eid] = now_chip("to_confirm", minutes=totals["connected"], over_limit=True, since=since)
        elif s.get("pause_open"):
            pause_at = us_time.minute(s["pause_open"]["occurred_at"])
            state[eid] = now_chip("on_break", minutes=us_time._mins(pause_at, us_time.minute(now)), since=since)
        else:
            state[eid] = now_chip("working", minutes=totals["payable"], since=since)
    if data["open_shifts"]:  # 071A: chip Fuera de horario (interruptor work_schedule)
        from app.services import work_schedule

        if await work_schedule.is_on(db, company_id):
            for eid, flag in (await work_schedule.flags(db, company_id, now)).items():
                if flag.get("out_of_schedule") and eid in state:
                    state[eid]["out_of_schedule"] = True
    for eid in held:
        state.setdefault(eid, now_chip("to_confirm"))
    for eid, c in closed_today.items():
        if eid not in state:
            local = c["end"].astimezone(us_time.zone(c["tz"]))
            state[eid] = now_chip("done", end={"t": local.strftime("%H:%M"), "a": us_time.abbr(c["tz"], c["end"])})
    return {"state": state, "open_views": open_views}


# ------------------------------------------------------------------ datos
async def _employees(db: AsyncSession, cid: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT e.id::text AS id, COALESCE(e.full_name, '') AS name, COALESCE(e.document_id, '') AS document, COALESCE(e.role, '') AS role,
               COALESCE(e.status, 'active') AS status, e.work_location_id::text AS work_location_id
        FROM employees e WHERE e.company_id = CAST(:c AS uuid)
    """), {"c": cid})).mappings().all()
    return [{**dict(r), "name": r["name"].strip()} for r in rows]


async def _materials(db: AsyncSession, cid: str, start: date, end: date) -> dict[str, list[dict]]:
    from app.api.v1.endpoints import reports as core_reports

    lo = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=1)
    hi = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=2)
    out: dict[str, list[dict]] = {}
    for m in await core_reports.material_rows(db, UUID(cid), lo, hi):
        if m.get("employee_id"):
            out.setdefault(str(m["employee_id"]), []).append(m)
    return out


def _material_out(m: dict, tz_name: str) -> Optional[dict]:
    at = us_payroll._dt(m.get("requested_at") or m.get("created_at"))
    if not at:
        return None
    local = at.astimezone(us_time.zone(tz_name))
    try:
        qty = float(m.get("quantity") or 0)
    except (TypeError, ValueError):
        qty = 0.0
    return {"what": str(m.get("material_name") or "").strip() or "Material", "qty": qty, "unit": str(m.get("unit") or ""), "status": str(m.get("status") or ""),
            "t": local.strftime("%H:%M"), "d": local.date().isoformat(), "a": us_time.abbr(tz_name, at), "at": us_payroll.iso(at)}


def _person(emp: dict, role: str, row: Optional[dict], held: list[dict], materials: list[dict], live: dict, open_view: Optional[dict],
            has_perimeter: bool, tz_name: str, start: date, end: date) -> dict:
    """Una persona: fila de la tabla (mismas cifras que Nomina) y su linea de tiempo."""
    us = (row or {}).get("us") or {}
    days: dict[str, dict] = {}

    def day(key: str) -> dict:
        return days.setdefault(key, {"date": key, "shifts": [], "materials": [], "connected": 0, "pause": 0, "payable": 0})

    views: list[dict] = []
    for s in (row or {}).get("shifts") or []:
        if s.get("us"):
            views.append({"view": s["us"], "state": "ok"})
    for item in held:
        if item.get("us"):
            views.append({"view": item["us"], "state": "held"})
    for v in views:
        shift = shift_out(v["view"], has_perimeter, v["state"])
        d = day(shift["in"]["d"] if shift.get("in") else start.isoformat())
        d["shifts"].append(shift)
        if v["state"] == "ok":
            for k in ("connected", "pause", "payable"):
                d[k] += shift[k]
    if open_view:
        running = shift_out(open_view, has_perimeter, "running")
        running_day = running["in"]["d"] if running.get("in") else None
        if running_day and start.isoformat() <= running_day <= end.isoformat():
            day(running_day)["shifts"].append(running)
    material_count = 0
    for m in materials:
        item = _material_out(m, tz_name)
        if item and start.isoformat() <= item["d"] <= end.isoformat():
            day(item["d"])["materials"].append(item)
            material_count += 1
    for d in days.values():
        d["shifts"].sort(key=lambda s: (s.get("in") or {}).get("at") or "")
        d["materials"].sort(key=lambda m: m["at"])
    ordered = [days[k] for k in sorted(days, reverse=True)]
    marks = [m for d in ordered for s in d["shifts"] for m in _marks_of(s)]
    last = max(marks, key=lambda m: m["at"]) if marks else None
    return {
        "id": emp["id"], "name": emp["name"] or "Colaborador", "document": emp.get("document") or "", "role": role or "",
        "work_location_id": emp.get("work_location_id"), "abbr": us_time.abbr(tz_name), "now": live or now_chip("no_shift"),
        "days_worked": int(us.get("days_worked") or 0), "connected": int(us.get("connected_minutes") or 0), "pause": int(us.get("pause_minutes") or 0),
        "payable": int(us.get("payable_minutes") or 0), "regular": int(us.get("regular_minutes") or 0), "overtime": int(us.get("overtime_minutes") or 0),
        "held": len(held), "outside": sum(1 for m in marks if m["s"] == "outside"), "no_location": sum(1 for m in marks if m["s"] == "none"),
        "notes": sum(1 for d in ordered for s in d["shifts"] for n in s["notes"] if n["kind"] in NOTE_KINDS),
        "materials": material_count, "last_mark": {"t": last["t"], "d": last["d"], "a": last["a"], "at": last["at"], "k": last["k"], "o": last.get("o") or ""} if last else None,
        "days": ordered,
    }


async def build(db: AsyncSession, company_id: Any, start: date, end: date, *, places: Optional[list[str]] = None, now: Optional[datetime] = None) -> dict:
    """Todo el Board. places=None: todas las operaciones; una lista: solo esas (supervisor)."""
    from app.services import employee_roles

    cid = str(company_id)
    now = now or datetime.now(timezone.utc)
    rule = await us_payroll.rules(db, cid)
    snap = await us_payroll.snapshot(db, cid, start, end, board=True)
    live = await live_state(db, cid, now, rule)
    locations = await work_locations.list_locations(db, cid)
    employees = await _employees(db, cid)
    settings = await geo.module_settings(db, cid)
    perimeters = await geo.perimeters_by_place(db, cid)
    supervisors = await geo.supervisors_by_place(db, cid)
    materials = await _materials(db, cid, start, end)
    config = await employee_roles.load_config(db, cid)
    near_ot = geo.near_ot_minutes(settings)
    company_tz = (snap.get("us_payroll") or {}).get("company_tz")
    rows = {str(r["employee_id"]): r for r in snap.get("rows") or []}
    held: dict[str, list[dict]] = {}
    for item in snap.get("unverified_shifts") or []:
        held.setdefault(str(item.get("employee_id")), []).append(item)
    week_totals = (snap.get("us_payroll") or {}).get("week_totals") or {}
    known = {loc["id"]: loc for loc in locations}

    buckets: dict[str, list[dict]] = {}
    for emp in employees:
        active = str(emp["status"]).strip().lower() in ("active", "activo")
        has_data = emp["id"] in rows or emp["id"] in held
        if not active and not has_data:
            continue
        key = emp["work_location_id"] if emp["work_location_id"] in known else NONE_KEY
        if places is not None and key not in places:
            continue
        loc = known.get(key)
        tz_name = (loc or {}).get("timezone") or company_tz or "America/Chicago"
        person = _person(emp, employee_roles.display(config, emp["role"]) if config else emp["role"], rows.get(emp["id"]), held.get(emp["id"], []),
                         materials.get(emp["id"], []), live["state"].get(emp["id"]), live["open_views"].get(emp["id"]), bool(perimeters.get(key)), tz_name, start, end)
        person["alerts"] = alerts_of(person, week_totals.get(emp["id"], []), near_ot, start, end, tz_name)
        buckets.setdefault(key, []).append(person)

    operations = []
    role_supervisors = {}
    for emp in employees:
        if work_locations.role_of(emp["role"]) in work_locations.SUPERVISOR_ROLES and str(emp["status"]).strip().lower() in ("active", "activo") and emp["work_location_id"]:
            role_supervisors.setdefault(emp["work_location_id"], []).append(emp["name"])
    ordered_locs = [loc for loc in order_operations(locations) if (places is None or loc["id"] in places) and (loc["is_active"] or buckets.get(loc["id"]))]
    for index, loc in enumerate(ordered_locs):
        operations.append(_operation(loc["id"], loc["name"], loc.get("code"), loc["timezone"], index, buckets.get(loc["id"], []), start, end, now,
                                     perimeters.get(loc["id"], []), [s["name"] for s in supervisors.get(loc["id"], [])] or sorted(role_supervisors.get(loc["id"], []), key=sort_key)))
    if buckets.get(NONE_KEY):
        operations.append(_operation(NONE_KEY, NO_PLACE, None, company_tz or "America/Chicago", -1, buckets[NONE_KEY], start, end, now, [], []))
    everyone = [p for o in operations for p in o["people"]]
    company = (await db.execute(text("SELECT name FROM companies WHERE id = CAST(:c AS uuid)"), {"c": cid})).scalar()
    return {
        "ok": True, "company": {"id": cid, "name": company or ""}, "period": {"start": start.isoformat(), "end": end.isoformat()},
        "server_time": us_payroll.iso(now), "rules": {k: rule[k] for k in ("week_start_day", "week_start_time", "overtime_after_minutes")},
        "near_ot_minutes": near_ot, "shift_limit_hours": await _policy_hours(db, cid),
        "figures": figures_of(everyone), "people_total": len(everyone), "operations": operations,
    }


def _operation(key: str, name: str, code: Any, tz_name: str, index: int, people: list[dict], start: date, end: date, now: datetime,
               perimeters: list[dict], supervisors: list[str]) -> dict:
    people = sorted(people, key=lambda p: sort_key(p["name"]))
    per_day: dict[str, dict] = {}
    notes: list[dict] = []
    alerts: list[dict] = []
    for p in people:
        alerts += p["alerts"]
        for d in p["days"]:
            bucket = per_day.setdefault(d["date"], {"payable": 0, "pause": 0})
            bucket["payable"] += d["payable"]
            bucket["pause"] += d["pause"]
            for s in d["shifts"]:
                for n in s["notes"]:
                    if n["kind"] in NOTE_KINDS:
                        notes.append({**n, "employee_id": p["id"], "employee": p["name"]})
    alerts.sort(key=lambda a: a.get("at") or "", reverse=True)
    notes.sort(key=lambda n: n.get("at") or "", reverse=True)
    local = now.astimezone(us_time.zone(tz_name))
    return {
        "key": key, "name": name, "code": code, "tz": tz_name, "abbr": us_time.abbr(tz_name, now), "color": index if 0 <= index <= 1 else "x",
        "local_time": local.strftime("%H:%M"), "supervisors": supervisors, "perimeters": len(perimeters),
        "perimeter_missing": key != NONE_KEY and not perimeters, "figures": figures_of(people), "hours_by_day": _period_days(start, end, per_day),
        "alerts": alerts, "notes": notes, "people": people,
    }


async def live_block(db: AsyncSession, company_id: Any, *, places: Optional[list[str]] = None, now: Optional[datetime] = None) -> dict:
    """Lo unico que cambia cada 60 s: el chip de cada persona y la hora de cada operacion."""
    cid = str(company_id)
    now = now or datetime.now(timezone.utc)
    live = await live_state(db, cid, now, await us_payroll.rules(db, cid))
    locations = await work_locations.list_locations(db, cid)
    known = {loc["id"] for loc in locations}
    people = {}
    for emp in await _employees(db, cid):
        key = emp["work_location_id"] if emp["work_location_id"] in known else NONE_KEY
        if places is None or key in places:
            people[emp["id"]] = live["state"].get(emp["id"]) or now_chip("no_shift")
    clocks = {loc["id"]: {"local_time": now.astimezone(us_time.zone(loc["timezone"])).strftime("%H:%M")} for loc in locations if places is None or loc["id"] in places}
    return {"ok": True, "server_time": us_payroll.iso(now), "people": people, "clocks": clocks}
