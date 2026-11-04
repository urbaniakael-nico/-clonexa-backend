"""PDF y CSV de Nomina con reglas de EE. UU. (interruptor us_payroll). Salen del MISMO
snapshot de calculate_period_snapshot (app.services.us_time): mismas cifras que la
pantalla, el bot y Reportes. Sin tarifa: "Pendiente" (nunca $0.00).

063A: Nomina = solo horas y valores, separada por operacion (lugar de trabajo:
Virginia ET, Alabama CT...). PDF: resumen de cada operacion y una tabla por operacion
con su total. CSV: una fila por persona y dia. Ubicacion, mapa, notas y bitacora del
turno quedan en Reportes."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

PENDING = "Pendiente"
NO_PLACE = "Sin lugar asignado"
DAY_ES = {"sunday": "domingo", "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles", "thursday": "jueves", "friday": "viernes", "saturday": "sábado"}
WEEKDAY_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def hm(minutes: Any) -> str:
    m = max(0, int(minutes or 0))
    return f"{m // 60}:{m % 60:02d}"


def money(value: Any, pending: bool) -> str:
    if pending or value is None:
        return PENDING
    return f"${float(value):,.2f}"


def day_label(iso_day: str) -> str:
    d = date.fromisoformat(iso_day)
    return f"{WEEKDAY_ES[d.weekday()]} {d.day:02d}/{d.month:02d}"


def rules_line(snapshot: dict) -> str:
    r = (snapshot.get("us_payroll") or {}).get("rules") or {}
    return (f"Semana laboral: {DAY_ES.get(r.get('week_start_day'), r.get('week_start_day'))} {r.get('week_start_time')} (hora del lugar) · "
            f"Overtime: más de {hm(r.get('overtime_after_minutes'))} h por semana a {r.get('overtime_factor')}x · Pausas sin pago · Minutos exactos")


def punch(p: dict | None) -> str:
    if not p:
        return "—"
    return f"{p['local']} {p['abbr']}"


# Detalle de un turno (ubicacion, pausas, notas): lo usa el PDF de Reportes, no la Nomina.
def where(p: dict | None) -> str:
    if not p:
        return ""
    loc = p.get("location") or {}
    text_ = loc.get("label") or ""
    if loc.get("perimeter"):
        text_ += f" ({loc['perimeter']})"
    return text_


def pauses_text(t: dict) -> str:
    out = []
    for b in t.get("pauses") or []:
        out.append(f"{punch(b['start'])}–{punch(b['end']) if b.get('end') else '—'} ({b['minutes']} min)")
    return "; ".join(out) or "Sin pausas"


def notes_text(t: dict) -> str:
    return " | ".join(f"{n.get('label') or n.get('kind')}: {' '.join(str(n.get('text') or '').split())}" for n in t.get("notes") or [] if n.get("text"))


def closed_by(t: dict) -> str:
    if t.get("adjusted"):
        return "Ajustado"
    m = t.get("manual_close")
    if m:
        return f"Cerrado por {m.get('by') or 'supervisor'}"
    if t.get("confirmed"):
        return "Salida confirmada en Nómina"
    if t.get("system_cutoff"):
        return "Cerrado por el sistema"
    return "Panel PIN" if (t.get("check_out") or {}).get("origin") == "pin" else "Bot"


# ------------------------------------------------------------------ operaciones
def _zone(name: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(name))
    except Exception:
        return ZoneInfo("America/Chicago")


def _iso_dt(value: Any) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _status(pending_count: int) -> str:
    if not pending_count:
        return "OK"
    return f"{pending_count} {'salida' if pending_count == 1 else 'salidas'} por confirmar"


def operations(snapshot: dict) -> list[dict]:
    """Personas agrupadas por operacion (lugar de trabajo), de este a oeste; al final
    "Sin lugar asignado" solo si hay alguien. Los totales son de toda la operacion."""
    us = snapshot.get("us_payroll") or {}
    rows = snapshot.get("rows") or []
    pending = snapshot.get("unverified_shifts") or []
    order = [o.get("name") for o in us.get("operations") or [] if o.get("name")]
    abbr = {o.get("name"): o.get("abbr") or "" for o in us.get("operations") or []}
    place_of: dict[str, Optional[str]] = {}
    for r in rows:
        u = r.get("us") or {}
        place_of[str(r.get("employee_id"))] = u.get("place")
        if u.get("place") and u["place"] not in order:
            order.append(u["place"])
            abbr[u["place"]] = u.get("abbr") or ""
    for p in pending:
        eid = str(p.get("employee_id") or "")
        place_of.setdefault(eid, p.get("place"))
        if p.get("place") and p["place"] not in order:
            order.append(p["place"])
            abbr[p["place"]] = p.get("abbr") or ""
    ops: dict[Optional[str], dict] = {}

    def op(name: Optional[str]) -> dict:
        if name not in ops:
            ops[name] = {"name": name or NO_PLACE, "place": name, "abbr": abbr.get(name, "") if name else us.get("company_abbr") or "",
                         "people": [], "pending": [], "rate_pending": False,
                         "totals": {"payable": 0, "regular": 0, "overtime": 0, "pause": 0, "connected": 0, "gross": 0.0, "net": 0.0,
                                    "pending_count": 0, "pending_minutes": 0}}
        return ops[name]

    for r in rows:
        u = r.get("us") or {}
        o = op(u.get("place"))
        o["people"].append(r)
        t = o["totals"]
        for k, src in (("payable", "payable_minutes"), ("regular", "regular_minutes"), ("overtime", "overtime_minutes"),
                       ("pause", "pause_minutes"), ("connected", "connected_minutes")):
            t[k] += int(u.get(src) or 0)
        if r.get("rate_pending"):
            o["rate_pending"] = True
        t["gross"] += float(u.get("gross") or 0)
        t["net"] += float(u.get("net") or 0)
    for p in pending:
        o = op(place_of.get(str(p.get("employee_id") or "")))
        o["pending"].append(p)
        o["totals"]["pending_count"] += 1
        o["totals"]["pending_minutes"] += int(p.get("minutes") or 0)
    names = [n for n in order if n in ops] + ([None] if None in ops else [])
    out = [ops[n] for n in names]
    for o in out:
        o["totals"]["gross"] = round(o["totals"]["gross"], 2)
        o["totals"]["net"] = round(o["totals"]["net"], 2)
        o["people"].sort(key=lambda r: str(r.get("employee_name") or "").lower())
    return out


def person_pending(snapshot: dict, employee_id: Any) -> list[dict]:
    return [p for p in snapshot.get("unverified_shifts") or [] if str(p.get("employee_id")) == str(employee_id)]


def person_days(row: dict) -> list[dict]:
    """Un renglon por dia trabajado: entrada / salida (hora del lugar) y las horas del dia
    tal como las reparte la regla (un turno que cruza la medianoche cae en dos dias)."""
    u = row.get("us") or {}
    tz = _zone(u.get("tz"))
    abbr = u.get("abbr") or ""
    days: dict[str, dict] = {}
    for w in u.get("weeks") or []:
        for d in w.get("days") or []:
            x = days.setdefault(d["date"], {"date": d["date"], "in": None, "out": None, "payable": 0, "pause": 0, "regular": 0, "overtime": 0})
            for k in ("payable", "pause", "regular", "overtime"):
                x[k] += int(d.get(k) or 0)
    for s in row.get("shifts") or []:
        a, b = _iso_dt(s.get("start")), _iso_dt(s.get("end"))
        if not a:
            continue
        la = a.astimezone(tz)
        x = days.setdefault(la.date().isoformat(), {"date": la.date().isoformat(), "in": None, "out": None, "payable": 0, "pause": 0, "regular": 0, "overtime": 0})
        if x["in"] is None or a < x["in"]:
            x["in"] = a
        if b and (x["out"] is None or b > x["out"]):
            x["out"] = b
    out = []
    for key in sorted(days):
        x = days[key]
        x["connected"] = x["payable"] + x["pause"]
        x["in_text"] = f"{x['in'].astimezone(tz):%H:%M} {abbr}".strip() if x["in"] else "—"
        if x["out"]:
            lo = x["out"].astimezone(tz)
            x["out_text"] = f"{lo:%H:%M} {abbr}".strip() + (f" ({lo:%d/%m})" if lo.date().isoformat() != key else "")
        else:
            x["out_text"] = "—"
        out.append(x)
    return out


def _day_money(row: dict, regular: int, overtime: int) -> Optional[float]:
    u = row.get("us") or {}
    if row.get("rate_pending") or not u.get("rate"):
        return None
    rate = Decimal(str(u.get("rate")))
    ot = Decimal(str(u.get("overtime_rate") or 0))
    value = Decimal(regular) / Decimal(60) * rate + Decimal(overtime) / Decimal(60) * ot
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ------------------------------------------------------------------ CSV
CSV_HEAD = ["operacion", "empleado", "documento", "fecha", "entrada", "salida", "en_turno", "pausas", "pagables", "regulares", "overtime",
            "tarifa", "bruto", "neto", "estado"]


def build_csv(snapshot: dict, documents: Optional[dict] = None) -> str:
    """Una fila por persona y dia (horas en h:mm, hora del lugar) y una fila "Total" por persona."""
    docs = documents or {}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEAD)
    for o in operations(snapshot):
        label = f"{o['name']} ({o['abbr']})" if o["abbr"] else o["name"]
        for r in o["people"]:
            u = r.get("us") or {}
            pend = bool(r.get("rate_pending"))
            rate = "Tarifa pendiente" if pend else money(u.get("rate"), False)
            doc = docs.get(str(r.get("employee_id"))) or ""
            held = person_pending(snapshot, r.get("employee_id"))
            held_days = {}
            tz = _zone(u.get("tz"))
            for p in held:
                d = _iso_dt(p.get("start"))
                if d:
                    held_days[d.astimezone(tz).date().isoformat()] = held_days.get(d.astimezone(tz).date().isoformat(), 0) + 1
            for x in person_days(r):
                value = _day_money(r, x["regular"], x["overtime"])
                state = _status(held_days.get(x["date"], 0))
                w.writerow([label, r.get("employee_name"), doc, x["date"], x["in_text"], x["out_text"], hm(x["connected"]), hm(x["pause"]),
                            hm(x["payable"]), hm(x["regular"]), hm(x["overtime"]), rate, money(value, value is None), money(value, value is None), state])
            w.writerow([label, r.get("employee_name"), doc, "Total", "", "", hm(u.get("connected_minutes")), hm(u.get("pause_minutes")),
                        hm(u.get("payable_minutes")), hm(u.get("regular_minutes")), hm(u.get("overtime_minutes")), rate,
                        money(u.get("gross"), pend), money(u.get("net"), pend), _status(len(held))])
        # Personas con solo turnos por confirmar (aun sin horas en la nomina).
        listed = {str(r.get("employee_id")) for r in o["people"]}
        for p in o["pending"]:
            if str(p.get("employee_id")) in listed:
                continue
            d = _iso_dt(p.get("start"))
            w.writerow([label, p.get("employee_name"), docs.get(str(p.get("employee_id"))) or "", d.date().isoformat() if d else "", "", "",
                        "", "", hm(0), hm(0), hm(0), "", "", "", f"Salida por confirmar ({hm(p.get('minutes'))} h fuera de la nómina)"])
    return "﻿" + buf.getvalue()


# ------------------------------------------------------------------ PDF
def build_pdf(snapshot: dict, company_name: str) -> bytes:
    """Carta horizontal: resumen por operacion y una tabla por operacion con su total."""
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    width, height = landscape(letter)
    margin = 36
    ink, soft = (0.07, 0.09, 0.15), (0.38, 0.42, 0.5)
    accents = [(0.06, 0.46, 0.43), (0.71, 0.33, 0.04), (0.23, 0.32, 0.62), (0.45, 0.45, 0.5)]  # verde agua, ambar, azul, gris
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    y = height - margin
    page = [1]

    def footer() -> None:
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(*soft)
        c.drawString(margin, 20, f"{company_name} · Nómina (reglas EE. UU.) · Solo horas y valores. Ubicación, notas y bitácora están en Reportes.")
        c.drawRightString(width - margin, 20, f"Página {page[0]}")

    def new_page() -> None:
        nonlocal y
        footer()
        c.showPage()
        page[0] += 1
        y = height - margin

    def ensure(space: float) -> None:
        if y - space < margin + 16:
            new_page()

    def fit(value: Any, size: float, maxw: float, font: str = "Helvetica") -> str:
        s = str(value if value is not None else "")
        while s and stringWidth(s, font, size) > maxw:
            s = s[:-2] + "…" if len(s) > 2 else ""
        return s

    def text_line(value: str, size: float = 9, bold: bool = False, color=ink, indent: float = 0) -> None:
        nonlocal y
        ensure(size + 4)
        font = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(font, size)
        c.setFillColorRGB(*color)
        c.drawString(margin + indent, y, fit(value, size, width - 2 * margin - indent, font))
        y -= size + 4

    total_w = width - 2 * margin

    def table(headers: list, rows: list, widths: list, aligns: list, accent, total_row: Optional[list] = None, size: float = 7.5) -> None:
        nonlocal y
        cols = [w_ * total_w for w_ in widths]

        def cells(values, font, color) -> None:
            c.setFont(font, size)
            c.setFillColorRGB(*color)
            x = margin
            for v, w_, a in zip(values, cols, aligns):
                cell = fit(v, size, w_ - 4, font)
                (c.drawRightString(x + w_ - 3, y, cell) if a == "r" else c.drawString(x + 3, y, cell))
                x += w_

        def head() -> None:
            nonlocal y
            c.setFillColorRGB(*accent)
            c.rect(margin, y - 4, total_w, size + 7, stroke=0, fill=1)
            cells(headers, "Helvetica-Bold", (1, 1, 1))
            y -= size + 8

        ensure(40)
        head()
        for i, r in enumerate(rows):
            if y < margin + 28:
                new_page()
                head()
            if i % 2 == 1:
                c.setFillColorRGB(0.96, 0.97, 0.98)
                c.rect(margin, y - 3, total_w, size + 5, stroke=0, fill=1)
            cells(r, "Helvetica", ink)
            y -= size + 5
        if total_row:
            ensure(size + 8)
            c.setStrokeColorRGB(*accent)
            c.setLineWidth(1)
            c.line(margin, y + size + 2, margin + total_w, y + size + 2)
            cells(total_row, "Helvetica-Bold", ink)
            y -= size + 6
        y -= 8

    def summary(o: dict, accent) -> None:
        nonlocal y
        t = o["totals"]
        ensure(46)
        c.setFillColorRGB(*accent)
        c.rect(margin, y - 30, 4, 40, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 12)
        c.setFillColorRGB(*ink)
        title = f"{o['name']}" + (f" ({o['abbr']})" if o["abbr"] else "") + f" · {len(o['people'])} {'persona' if len(o['people']) == 1 else 'personas'}"
        c.drawString(margin + 12, y, fit(title, 12, total_w - 12, "Helvetica-Bold"))
        stats = [("Horas pagables", hm(t["payable"])), ("Regulares", hm(t["regular"])), ("Overtime", hm(t["overtime"])), ("Pausas", hm(t["pause"])),
                 ("Bruto", "Tarifa pendiente" if o["rate_pending"] and not t["gross"] else money(t["gross"], False) + (" + pendiente" if o["rate_pending"] else "")),
                 ("Por confirmar", f"{t['pending_count']} ({hm(t['pending_minutes'])} h)" if t["pending_count"] else "0")]
        step = (total_w - 12) / len(stats)
        for i, (k, v) in enumerate(stats):
            x = margin + 12 + i * step
            c.setFont("Helvetica", 7)
            c.setFillColorRGB(*soft)
            c.drawString(x, y - 14, k)
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(*ink)
            c.drawString(x, y - 27, fit(v, 10, step - 6, "Helvetica-Bold"))
        y -= 44

    per = snapshot.get("period") or {}
    c.setFont("Helvetica-Bold", 15)
    c.setFillColorRGB(*ink)
    c.drawString(margin, y - 12, fit(f"{company_name} · Nómina semanal" if company_name else "Nómina semanal", 15, width / 2, "Helvetica-Bold"))
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*soft)
    c.drawString(margin, y - 26, "Overtime por encima de 40 h · Pausas sin pago · Hora local de cada operación")
    c.drawRightString(width - margin, y - 12, f"Periodo: {per.get('period_start')} a {per.get('period_end')}")
    c.drawRightString(width - margin, y - 26, f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    y -= 44
    text_line(rules_line(snapshot), 8, color=soft)
    pending = snapshot.get("unverified_shifts") or []
    if pending:
        mins = sum(int(p.get("minutes") or 0) for p in pending)
        text_line(f"Atención: {len(pending)} {'turno' if len(pending) == 1 else 'turnos'} por confirmar · {hm(mins)} h no entran a la nómina hasta registrar la salida real", 8.5, bold=True)
    y -= 4

    ops = operations(snapshot)
    for i, o in enumerate(ops):
        summary(o, accents[i % len(accents)] if o["place"] else accents[-1])
    headers = ["Empleado", "Rol", "Días", "En turno", "Pausas", "Pagables", "Regulares", "Overtime", "Tarifa", "Bruto", "Neto", "Estado"]
    widths = [0.19, 0.08, 0.04, 0.065, 0.06, 0.065, 0.065, 0.065, 0.075, 0.08, 0.08, 0.12]
    aligns = ["l", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "l"]
    for i, o in enumerate(ops):
        accent = accents[i % len(accents)] if o["place"] else accents[-1]
        ensure(60)
        y -= 2
        text_line(f"{o['name']}" + (f" ({o['abbr']})" if o["abbr"] else ""), 11, bold=True, color=accent)
        rows = []
        listed = set()
        for r in o["people"]:
            u = r.get("us") or {}
            pend = bool(r.get("rate_pending"))
            listed.add(str(r.get("employee_id")))
            rows.append([r.get("employee_name"), r.get("employee_role") or "—", u.get("days_worked") or 0, hm(u.get("connected_minutes")),
                         hm(u.get("pause_minutes")), hm(u.get("payable_minutes")), hm(u.get("regular_minutes")), hm(u.get("overtime_minutes")),
                         PENDING if pend else money(u.get("rate"), False), money(u.get("gross"), pend), money(u.get("net"), pend),
                         _status(len(person_pending(snapshot, r.get("employee_id"))))])
        extra: dict[str, list] = {}
        for p in o["pending"]:
            if str(p.get("employee_id")) not in listed:
                extra.setdefault(str(p.get("employee_id")), []).append(p)
        for items in extra.values():
            p = items[0]
            rows.append([p.get("employee_name"), p.get("employee_role") or "—", 0, "0:00", "0:00", "0:00", "0:00", "0:00", "—", "—", "—", _status(len(items))])
        t = o["totals"]
        allp = o["rate_pending"] and not t["gross"]
        table(headers, rows, widths, aligns, accent,
              total_row=[f"Total {o['name']}", "", "", hm(t["connected"]), hm(t["pause"]), hm(t["payable"]), hm(t["regular"]), hm(t["overtime"]), "",
                         PENDING if allp else money(t["gross"], False), PENDING if allp else money(t["net"], False),
                         _status(t["pending_count"])])
    tt = snapshot.get("totals") or {}
    text_line(f"Total {company_name or 'empresa'}: pagables {hm(tt.get('payable_minutes'))} · overtime {hm(tt.get('extra_minutes'))} · "
              f"por confirmar {len(pending)}", 9.5, bold=True)
    footer()
    c.save()
    return buf.getvalue()
