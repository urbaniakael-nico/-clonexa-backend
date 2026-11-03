"""Nomina y tiempos segun EE. UU. (FLSA) - interruptor us_payroll (settings del modulo
payroll, apagado por defecto; hoy solo VOLTAGE).

Con el interruptor encendido, calculate_period_snapshot (la funcion que usan Nomina,
Reportes, el PDF, el CSV, los KPIs y el bot) toma sus numeros de aqui, y todos salen de
app.services.us_time (una sola regla). Apagado: nada cambia.

- Lee las marcaciones guardadas (workforce_attendance_events) sin cambiarlas.
- Hora y zona del LUGAR de trabajo de cada persona (Virginia = America/New_York,
  Alabama = America/Chicago) con su sigla (ET / CT); sin lugar, la zona de la empresa y
  el aviso "Sin lugar asignado".
- Valor por hora: si falta, el dinero queda "Pendiente" (nunca $0.00). El overtime se
  paga a 1.5x la tarifa regular (regla guardada; sin tarifa no hay valor).
- Turnos cerrados por el sistema o de mas horas que el limite: igual que siempre,
  quedan "por confirmar" (049D) hasta registrar la hora real.
Toda consulta filtra por company_id.
"""
from __future__ import annotations

import contextlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import us_time

KEY = "us_payroll"
RULES_KEY = "us_payroll_rules"
MODULE = "payroll"
MONEY = Decimal("0.01")
PUNCHES = ("check_in", "break_start", "break_end", "check_out")
SYSTEM_NOTES = ("clx:", "ubicación gps validada", "ubicacion gps validada", "turno cerrado por supervisor", "ubicación compartida", "ubicacion compartida")
GPS_LABEL = {"inside": "En perímetro", "outside": "Fuera de perímetro", "unconfigured": "Sin perímetro", "none": "Sin ubicación"}
GPS_WINDOW = timedelta(minutes=3)


def _json(value: Any) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value or "{}")
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


# ------------------------------------------------------------------ interruptor y reglas
async def _settings(db: AsyncSession, company_id: Any) -> Optional[dict]:
    sql = text("""
        SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND lower(m.code) = :m LIMIT 1
    """)
    params = {"c": str(company_id), "m": MODULE}
    try:
        row = (await db.execute(sql, params)).first()
    except Exception:
        # Una consulta anterior pudo dejar la transaccion abortada (p. ej. una tabla
        # opcional que no existe): se limpia y se lee otra vez, para no caer en
        # silencio al calculo viejo. Sin base usable: apagado.
        try:
            await db.rollback()
            row = (await db.execute(sql, params)).first()
        except Exception:
            with contextlib.suppress(Exception):
                await db.rollback()
            return None
    if not row or row[0] is False:
        return None
    return _json(row[1])


async def is_on(db: AsyncSession, company_id: Any) -> bool:
    settings = await _settings(db, company_id)
    return bool(settings) and settings.get(KEY) is True


async def rules(db: AsyncSession, company_id: Any) -> dict:
    return us_time.rules_of((await _settings(db, company_id) or {}).get(RULES_KEY))


# ------------------------------------------------------------------ lectura
def _kind(ev: dict) -> str:
    from app.api.v1.endpoints.payroll import attendance_event_kind

    return attendance_event_kind(ev)


def _location(ev: Optional[dict], gps: Optional[dict] = None) -> dict:
    """Ubicacion de una marcacion: la suya, o el punto GPS mas cercano (+-3 min)."""
    if not ev:
        return {"status": "none", "label": GPS_LABEL["none"], "lat": None, "lng": None, "map": None, "perimeter": None}
    payload = _json(ev.get("payload_json"))
    punch = payload.get("punch_location") if isinstance(payload.get("punch_location"), dict) else {}
    lat = ev.get("latitude") if ev.get("latitude") is not None else punch.get("latitude")
    lng = ev.get("longitude") if ev.get("longitude") is not None else punch.get("longitude")
    status = punch.get("gps_status") or payload.get("gps_status")
    perimeter = punch.get("matched_perimeter_name") or payload.get("matched_perimeter_name")
    if (lat is None or lng is None) and gps:
        gp = _json(gps.get("payload_json"))
        lat, lng = gps.get("latitude"), gps.get("longitude")
        status = status or gp.get("gps_status")
        perimeter = perimeter or gp.get("matched_perimeter_name")
    if lat is None or lng is None:
        return {"status": "none", "label": GPS_LABEL["none"], "lat": None, "lng": None, "map": None, "perimeter": None}
    key = str(status or "unconfigured").strip().lower()
    key = "inside" if key in ("inside", "dentro", "in") else "outside" if key in ("outside", "fuera", "out") else "unconfigured"
    lat, lng = float(lat), float(lng)
    return {"status": key, "label": GPS_LABEL[key], "lat": lat, "lng": lng, "perimeter": perimeter,
            "map": f"https://www.google.com/maps?q={lat:.6f},{lng:.6f}"}


def _note_text(ev: dict) -> str:
    payload = _json(ev.get("payload_json"))
    for value in (payload.get("args"), ev.get("detail"), ev.get("notes"), payload.get("text")):
        value = str(value or "").strip()
        if value and not value.lower().startswith(SYSTEM_NOTES):
            return value
    return ""


async def load(db: AsyncSession, company_id: Any, lo: datetime, hi: datetime, employee_id: Any = None) -> dict:
    """Personas, lugares y turnos CERRADOS (con pausas, ubicaciones y notas) entre lo y hi."""
    cid = str(company_id)
    has_places = bool((await db.execute(text("SELECT to_regclass('work_locations') IS NOT NULL"))).scalar())
    place_cols = "e.work_location_id::text AS work_location_id, wl.name AS place_name, wl.timezone AS place_tz" if has_places else \
        "NULL::text AS work_location_id, NULL::text AS place_name, NULL::text AS place_tz"
    place_join = "LEFT JOIN work_locations wl ON wl.id = e.work_location_id AND wl.company_id = e.company_id" if has_places else ""
    emp_filter = "AND e.id = CAST(:e AS uuid)" if employee_id else ""
    params = {"c": cid, "e": str(employee_id) if employee_id else None}
    people = {str(r["id"]): dict(r) for r in (await db.execute(text(f"""
        SELECT e.id::text AS id, COALESCE(e.full_name, '') AS full_name, COALESCE(e.role, '') AS role, COALESCE(e.status, 'active') AS status,
               e.hourly_rate_regular, e.deduction_1, e.deduction_2, {place_cols}
        FROM employees e {place_join}
        WHERE e.company_id = CAST(:c AS uuid) {emp_filter}
    """), params)).mappings().all()}
    company_tz = None
    try:
        company_tz = (await db.execute(text("SELECT timezone FROM companies WHERE id = CAST(:c AS uuid)"), {"c": cid})).scalar()
    except Exception:
        await db.rollback()
    if not company_tz:
        from app.services import company_locale

        company_tz = str(company_locale.current_zone().key)
    ev_filter = "AND ev.employee_id = CAST(:e AS uuid)" if employee_id else ""
    events = [dict(r) for r in (await db.execute(text(f"""
        SELECT ev.id::text AS id, ev.employee_id::text AS employee_id, ev.event_type, ev.event_label, ev.status_after, ev.source,
               ev.source_channel, ev.detail, ev.notes, ev.payload_json, ev.metadata_json, ev.latitude, ev.longitude,
               COALESCE(ev.occurred_at, ev.created_at) AS occurred_at
        FROM workforce_attendance_events ev
        WHERE ev.company_id = CAST(:c AS uuid) {ev_filter}
          AND ev.employee_id IS NOT NULL AND ev.event_type <> 'gps_location'
          AND COALESCE(ev.occurred_at, ev.created_at) >= :lo AND COALESCE(ev.occurred_at, ev.created_at) <= :hi
        ORDER BY COALESCE(ev.occurred_at, ev.created_at) ASC, ev.id
    """), {**params, "lo": lo, "hi": hi})).mappings().all()]
    for ev in events:
        ev["occurred_at"] = _dt(ev["occurred_at"])
        ev["kind"] = _kind(ev)

    # Punto GPS mas cercano para las marcaciones sin coordenadas (flujo viejo del bot).
    need = [ev for ev in events if ev["kind"] in PUNCHES and (ev.get("latitude") is None or ev.get("longitude") is None)
            and not (_json(ev.get("payload_json")).get("punch_location"))]
    nearest: dict[str, dict] = {}
    if need:
        rows = (await db.execute(text("""
            SELECT p.ref, g.latitude, g.longitude, g.payload_json, COALESCE(g.occurred_at, g.created_at) AS at, p.at AS punch_at
            FROM (SELECT unnest(CAST(:refs AS text[])) AS ref, unnest(CAST(:eids AS text[])) AS eid, unnest(CAST(:ats AS timestamptz[])) AS at) p
            JOIN workforce_attendance_events g
              ON g.company_id = CAST(:c AS uuid) AND g.employee_id::text = p.eid AND g.event_type = 'gps_location'
             AND g.latitude IS NOT NULL AND COALESCE(g.occurred_at, g.created_at) BETWEEN p.at - CAST(:w AS interval) AND p.at + CAST(:w AS interval)
        """), {"c": cid, "refs": [e["id"] for e in need], "eids": [e["employee_id"] for e in need],
               "ats": [e["occurred_at"] for e in need], "w": GPS_WINDOW})).mappings().all()
        for r in rows:
            gap = abs((_dt(r["at"]) - _dt(r["punch_at"])).total_seconds())
            if r["ref"] not in nearest or gap < nearest[r["ref"]]["gap"]:
                nearest[r["ref"]] = {**dict(r), "gap": gap}

    shifts, open_ = [], {}
    for ev in events:
        eid, kind, at = ev["employee_id"], ev["kind"], ev["occurred_at"]
        if not at:
            continue
        if kind == "check_in":
            open_[eid] = {"employee_id": eid, "start": at, "check_in": ev, "breaks": [], "break_events": [], "pause_open": None, "notes": []}
            continue
        s = open_.get(eid)
        if not s:
            continue
        if kind == "break_start":
            if not s["pause_open"]:
                s["pause_open"] = ev
            continue
        if kind == "break_end":
            if s["pause_open"]:
                s["breaks"].append((s["pause_open"]["occurred_at"], at))
                s["break_events"].append((s["pause_open"], ev))
                s["pause_open"] = None
            continue
        if kind == "check_out":
            if s["pause_open"]:
                s["breaks"].append((s["pause_open"]["occurred_at"], at))
                s["break_events"].append((s["pause_open"], None))
                s["pause_open"] = None
            s["end"], s["check_out"] = at, ev
            shifts.append(open_.pop(eid))
            continue
        note = _note_text(ev)
        if note:
            s["notes"].append({"kind": "material" if "material" in str(ev.get("event_type") or "") else "note", "at": at, "text": note,
                               "label": ev.get("event_label") or ""})
    for s in shifts:
        person = people.get(s["employee_id"]) or {}
        s["tz"] = person.get("place_tz") or company_tz
        s["place"] = person.get("place_name")
        s["place_missing"] = not person.get("place_name")
        s["gps"] = {ev_id: nearest.get(ev_id) for ev_id in [s["check_in"]["id"], s["check_out"]["id"]] +
                    [b[0]["id"] for b in s["break_events"]] + [b[1]["id"] for b in s["break_events"] if b[1]]}
    return {"people": people, "shifts": shifts, "company_tz": company_tz}


# ------------------------------------------------------------------ vista de un turno
def _punch_view(ev: Optional[dict], gps: Optional[dict], tz_name: str, at: Optional[datetime] = None) -> Optional[dict]:
    if not ev and not at:
        return None
    when = us_time.minute(at or ev["occurred_at"])
    local = when.astimezone(us_time.zone(tz_name))
    return {"at": iso(when), "local": local.strftime("%H:%M"), "date": local.date().isoformat(), "abbr": us_time.abbr(tz_name, when),
            "location": _location(ev, gps)}


def shift_view(s: dict) -> dict:
    """Linea de tiempo de un turno: entrada, pausas, salida, cierre manual, notas y totales."""
    tz = s["tz"]
    out_ev = s.get("check_out") or {}
    out_payload = _json(out_ev.get("payload_json"))
    manual = None
    if out_ev.get("source_channel") == "portal_manual_close" or out_payload.get("manual_close"):
        manual = {"by": out_payload.get("closed_by") or "", "note": out_payload.get("note") or "", "closed_at": out_payload.get("closed_at")}
    confirmed = s.get("confirmed")
    pauses = []
    lo_, hi_ = s["split"]["start"], s["split"]["end"]
    for (b0, b1), (e0, e1) in zip(s.get("breaks") or [], s.get("break_events") or []):
        a, b = max(us_time.minute(b0), lo_), min(us_time.minute(b1), hi_)
        if b <= a:
            continue  # pausa fuera del turno confirmado
        pauses.append({"start": _punch_view(e0, s["gps"].get(e0["id"]) if e0 else None, tz, a),
                       "end": _punch_view(e1, s["gps"].get(e1["id"]) if e1 else None, tz, b),
                       "minutes": us_time._mins(a, b), "closed_by_checkout": e1 is None})
    notes = list(s.get("notes") or [])
    summary = _note_text(out_ev) if out_ev and not manual else ""
    if summary:
        notes.append({"kind": "summary", "at": out_ev["occurred_at"], "text": summary, "label": "Resumen de la jornada"})
    if manual and manual["note"]:
        notes.append({"kind": "manual_close", "at": _dt(manual["closed_at"]) or out_ev.get("occurred_at"), "text": manual["note"], "label": "Nota del cierre"})
    if confirmed:
        notes.append({"kind": "confirmed", "at": _dt(confirmed.get("confirmed_at")) or s["end"], "text": confirmed.get("note") or "",
                      "label": "Salida confirmada en Nómina"})
    return {
        "employee_id": s["employee_id"], "tz": tz, "abbr": us_time.abbr(tz, s["start"]), "place": s.get("place"), "place_missing": s.get("place_missing"),
        "check_in": _punch_view(s.get("check_in"), s["gps"].get((s.get("check_in") or {}).get("id")), tz, s["split"]["start"]),
        "check_out": _punch_view(out_ev or None, s["gps"].get(out_ev.get("id")) if out_ev else None, tz, s["split"]["end"]),
        "manual_close": manual, "system_cutoff": bool(out_payload.get("system_cutoff")), "confirmed": bool(confirmed),
        "pauses": pauses,
        "notes": [{**n, "at": iso(n["at"]), "local": n["at"].astimezone(us_time.zone(tz)).strftime("%H:%M") if isinstance(n["at"], datetime) else ""}
                  for n in sorted(notes, key=lambda n: n["at"] or s["end"])],
        "connected_minutes": s["connected"], "pause_minutes": s["pause"], "payable_minutes": s["payable"],
        "regular_minutes": s["regular"], "overtime_minutes": s["overtime"],
        "days": [{"date": d["date"].isoformat(), "week_start": d["week_start"].date().isoformat(), "payable": d["payable"], "pause": d["pause"],
                  "regular": d["regular"], "overtime": d["overtime"]} for d in s["days"]],
    }


# ------------------------------------------------------------------ periodo (Nomina / Reportes)
def _bounds(start_day: date, end_day: date) -> tuple[datetime, datetime]:
    # 8 dias antes: la semana laboral completa para el overtime; 2 despues: zonas al oeste.
    lo = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=8)
    hi = datetime.combine(end_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=2)
    return lo, hi


def pay(regular: int, overtime: int, rate: Decimal, factor: float, deductions: Decimal) -> dict:
    """Dinero de una persona. Sin tarifa: todo None ("Pendiente"), nunca $0.00."""
    if rate <= 0:
        return {"rate": None, "overtime_rate": None, "regular_amount": None, "overtime_amount": None, "gross": None,
                "deductions": float(deductions), "net": None, "rate_pending": True}
    ot_rate = _money(rate * Decimal(str(factor)))
    regular_amount = _money(Decimal(regular) / Decimal(60) * rate)
    overtime_amount = _money(Decimal(overtime) / Decimal(60) * ot_rate)
    gross = _money(regular_amount + overtime_amount)
    return {"rate": float(rate), "overtime_rate": float(ot_rate), "regular_amount": float(regular_amount), "overtime_amount": float(overtime_amount),
            "gross": float(gross), "deductions": float(deductions), "net": float(max(Decimal("0"), gross - deductions)), "rate_pending": False}


async def snapshot(db: AsyncSession, company_id: Any, period_start: date, period_end: date, employee_id: Any = None) -> dict:
    """El snapshot de nomina de siempre (mismas llaves) con los numeros FLSA y el detalle."""
    from app.api.v1.endpoints import payroll as core

    rule = await rules(db, company_id)
    lo, hi = _bounds(period_start, period_end)
    data = await load(db, company_id, lo, hi, employee_id)
    verification = await core._cx_verification_context_049D(db, company_id)
    payable_shifts, unverified = [], []
    for s in data["shifts"]:
        out_ev = s.get("check_out") or {}
        verdict, closure = core._cx_check_shift_049D(verification, "attendance", s["check_in"]["id"], s["start"], s["end"],
                                                     core._cx_event_system_cutoff_049D(out_ev))
        if verdict == "confirmed":
            real_end = _dt(closure.get("real_end_at"))
            if real_end:
                s = {**s, "end": real_end, "confirmed": {"note": closure.get("note") or closure.get("reason") or "",
                                                         "confirmed_at": closure.get("confirmed_at")}}
        s["_verdict"], s["_closure"] = verdict, closure
        payable_shifts.append(s)
    computed = us_time.compute(payable_shifts, rule)
    # "Por confirmar": fuera del pago y de la cuenta del overtime, como siempre (049D).
    held = [s for s in computed if s["_verdict"] == "hold"]
    good = us_time.compute([s for s in payable_shifts if s["_verdict"] != "hold"], rule)
    for s in us_time.in_period(held, period_start, period_end):
        person = data["people"].get(s["employee_id"]) or {}
        unverified.append(core._cx_unverified_item_049D(
            source="attendance", ref=s["check_in"]["id"], employee={"id": s["employee_id"], "full_name": person.get("full_name")},
            fallback_name=person.get("full_name"), panel_type="asistencia", start=s["start"], end=s["end"],
            minutes=s["payable"], reason=None, closure=s["_closure"]))
    period = us_time.in_period(good, period_start, period_end)

    by_emp: dict[str, list[dict]] = {}
    for s in period:
        by_emp.setdefault(s["employee_id"], []).append(s)
    rows, missing_rate, missing_place = [], [], []
    for eid, items in by_emp.items():
        person = data["people"].get(eid) or {}
        items.sort(key=lambda x: x["start"])
        tot = {k: sum(s[k] for s in items) for k in ("connected", "pause", "payable", "regular", "overtime")}
        deductions = _money(person.get("deduction_1")) + _money(person.get("deduction_2"))
        money = pay(tot["regular"], tot["overtime"], _money(person.get("hourly_rate_regular")), rule["overtime_factor"], deductions)
        weeks = us_time.weeks_of(items)
        views = [shift_view(s) for s in items]
        shift_rows = []
        for s, v in zip(items, views):
            m = pay(s["regular"], s["overtime"], _money(person.get("hourly_rate_regular")), rule["overtime_factor"], Decimal("0"))
            shift_rows.append({
                "start": iso(s["split"]["start"]), "end": iso(s["split"]["end"]), "regular_minutes": s["regular"], "extra_minutes": s["overtime"],
                "gross_amount": str(_money(m["gross"] or 0)), "source": "attendance", "mini_panel_session_id": None,
                "pause_minutes": s["pause"], "connected_minutes": s["connected"], "worked_minutes": s["payable"],
                "rate_pending": m["rate_pending"], "us": v,
            })
        place = person.get("place_name")
        tz = person.get("place_tz") or data["company_tz"]
        if money["rate_pending"]:
            missing_rate.append({"employee_id": eid, "employee_name": person.get("full_name") or "Colaborador", "employee_role": person.get("role") or "",
                                 "minutes": tot["payable"], "missing": ["valor hora"]})
        if not place:
            missing_place.append({"employee_id": eid, "employee_name": person.get("full_name") or "Colaborador"})
        rows.append({
            "employee_id": eid, "employee_name": person.get("full_name") or "Colaborador", "employee_role": person.get("role") or "",
            "closed_shifts": len(items), "regular_minutes": tot["regular"], "extra_minutes": tot["overtime"],
            "hourly_rate_regular": float(_money(person.get("hourly_rate_regular"))), "hourly_rate_extra": money["overtime_rate"] or 0.0,
            "deduction_1": float(_money(person.get("deduction_1"))), "deduction_2": float(_money(person.get("deduction_2"))),
            "regular_amount": money["regular_amount"] or 0.0, "extra_amount": money["overtime_amount"] or 0.0,
            "gross_amount": money["gross"] or 0.0, "discount_amount": money["deductions"], "net_amount": money["net"] or 0.0,
            "rate_pending": money["rate_pending"], **({"rate_missing": ["valor hora"]} if money["rate_pending"] else {}),
            "shifts": shift_rows,
            "us": {
                "place": place, "place_missing": not place, "tz": tz, "abbr": us_time.abbr(tz),
                "days_worked": len({d["date"] for s in items for d in s["days"] if d["payable"] > 0}),
                "connected_minutes": tot["connected"], "pause_minutes": tot["pause"], "payable_minutes": tot["payable"],
                "regular_minutes": tot["regular"], "overtime_minutes": tot["overtime"], **money,
                "weeks": [{"week_start": w["week_start"].date().isoformat(), "week_end": (w["week_start"] + timedelta(days=6)).date().isoformat(),
                           "payable": w["payable"], "pause": w["pause"], "regular": w["regular"], "overtime": w["overtime"],
                           "days": [{"date": d["date"].isoformat(), "payable": d["payable"], "pause": d["pause"], "regular": d["regular"],
                                     "overtime": d["overtime"]} for d in w["days"]]} for w in weeks],
            },
        })
    rows.sort(key=lambda r: str(r["employee_name"]).lower())
    any_pending = any(r["rate_pending"] for r in rows)
    totals = {
        "people": len(rows), "closed_shifts": sum(r["closed_shifts"] for r in rows),
        "regular_minutes": sum(r["regular_minutes"] for r in rows), "extra_minutes": sum(r["extra_minutes"] for r in rows),
        "gross_amount": round(sum(r["gross_amount"] for r in rows), 2), "discount_amount": round(sum(r["discount_amount"] for r in rows), 2),
        "net_amount": round(sum(r["net_amount"] for r in rows), 2),
        "payable_minutes": sum(r["us"]["payable_minutes"] for r in rows), "pause_minutes": sum(r["us"]["pause_minutes"] for r in rows),
        "connected_minutes": sum(r["us"]["connected_minutes"] for r in rows), "rate_pending": any_pending,
    }
    out = {
        "period": {"company_id": str(company_id), "period_start": period_start.isoformat(), "period_end": period_end.isoformat(), "status": "open"},
        "rows": rows, "totals": totals,
        "payroll_rule": {"enabled": True, "limit_scope": "week", "ordinary_minutes_limit": rule["overtime_after_minutes"], "applied_by": "US_PAYROLL_FLSA"},
        "us_payroll": {"rules": rule, "missing_rate": missing_rate, "missing_place": missing_place, "company_tz": data["company_tz"],
                       "company_abbr": us_time.abbr(data["company_tz"])},
    }
    if unverified:
        out["unverified_shifts"] = unverified
    if missing_rate:
        out["missing_rate_employees"] = missing_rate
    return out


# ------------------------------------------------------------------ bot ("Turno finalizado")
BOT_TEXTS = {
    "es": {
        "head": "Feliz descanso, {name}.",
        "times": "🕐 Entrada {start} · Salida {end}",
        "pauses": "⏸ Pausas: {pause} (sin pago)",
        "today": "✅ Tiempo pagable de hoy: {payable}",
        "week": "📅 Semana: {week} de {limit}",
        "overtime": "⏱ Overtime de la semana: {ot}",
        "pay": "💵 Proyección de la semana: {amount}",
        "pending": "💵 Pago: según tarifa (pendiente)",
        "no_place": "📍 Sin lugar asignado (hora de la empresa)",
    },
    "en": {
        "head": "Rest well, {name}.",
        "times": "🕐 In {start} · Out {end}",
        "pauses": "⏸ Breaks: {pause} (unpaid)",
        "today": "✅ Payable time today: {payable}",
        "week": "📅 Week: {week} of {limit}",
        "overtime": "⏱ Overtime this week: {ot}",
        "pay": "💵 Projected pay this week: {amount}",
        "pending": "💵 Pay: per hourly rate (pending)",
        "no_place": "📍 No work location (company time)",
    },
}


def bot_hm(minutes: int, lang: str) -> str:
    m = max(0, int(minutes))
    return f"{m // 60} h {m % 60:02d} min"


async def bot_summary(db: AsyncSession, company_id: Any, employee_id: Any, ended_at: datetime, language: str,
                      money_label: Callable[[Decimal], str], name: str = "") -> Optional[str]:
    """Resumen del turno recien cerrado con la misma regla de Nomina (semana laboral)."""
    lang = language if language in BOT_TEXTS else "es"
    t = BOT_TEXTS[lang]
    rule = await rules(db, company_id)
    lo, hi = ended_at - timedelta(days=8), ended_at + timedelta(minutes=1)
    data = await load(db, company_id, lo, hi, employee_id)
    if not data["shifts"]:
        return None
    computed = us_time.compute(data["shifts"], rule)
    last = max(computed, key=lambda s: s["end"])
    week_key = last["split"]["pieces"][-1]["week_start"] if last["split"]["pieces"] else None
    week_pieces = [p for s in computed for p in s["split"]["pieces"] if week_key is not None and p["week_start"] == week_key]
    week_payable = sum(p["payable"] for p in week_pieces)
    week_regular = sum(p["regular"] for p in week_pieces)
    week_ot = sum(p["overtime"] for p in week_pieces)
    tz = last["tz"]
    zone_ = us_time.zone(tz)
    start_l, end_l = last["split"]["start"].astimezone(zone_), last["split"]["end"].astimezone(zone_)
    ab = us_time.abbr(tz, last["split"]["start"])
    lines = [t["head"].format(name=name or "colaborador"),
             t["times"].format(start=f"{start_l:%H:%M} {ab}", end=f"{end_l:%H:%M} {ab}" + (f" ({end_l:%d/%m})" if end_l.date() != start_l.date() else "")),
             t["pauses"].format(pause=bot_hm(last["split"]["pause"], lang)),
             t["today"].format(payable=bot_hm(last["split"]["payable"], lang)),
             t["week"].format(week=bot_hm(week_payable, lang), limit=bot_hm(rule["overtime_after_minutes"], lang).replace(" 00 min", ""))]
    if week_ot > 0:
        lines.append(t["overtime"].format(ot=bot_hm(week_ot, lang)))
    person = data["people"].get(str(employee_id)) or {}
    money = pay(week_regular, week_ot, _money(person.get("hourly_rate_regular")), rule["overtime_factor"], Decimal("0"))
    lines.append(t["pending"] if money["rate_pending"] else t["pay"].format(amount=money_label(Decimal(str(money["gross"])))))
    if last.get("place_missing"):
        lines.append(t["no_place"])
    return "\n".join(lines)
