"""PDF y CSV de Nomina con reglas de EE. UU. (interruptor us_payroll). Salen del MISMO
snapshot de calculate_period_snapshot (app.services.us_time): mismas cifras que la
pantalla, el bot y Reportes. Una linea por turno con entrada, pausas, salida y notas,
para responder reclamos con pruebas. Sin tarifa: "Pendiente" (nunca $0.00)."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from typing import Any

PENDING = "Pendiente"
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
    m = t.get("manual_close")
    if m:
        return f"Cerrado por {m.get('by') or 'supervisor'}"
    if t.get("confirmed"):
        return "Salida confirmada en Nómina"
    if t.get("system_cutoff"):
        return "Cerrado por el sistema"
    return "Bot"


# ------------------------------------------------------------------ CSV
CSV_HEAD = ["tipo", "persona", "lugar", "zona", "fecha", "semana", "entrada", "ubicacion_entrada", "mapa_entrada", "pausas", "salida",
            "ubicacion_salida", "mapa_salida", "cierre", "en_turno_min", "pausas_min", "pagable_min", "regular_min", "overtime_min",
            "tarifa", "bruto_regular", "bruto_overtime", "deducciones", "neto", "notas"]


def build_csv(snapshot: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEAD)
    for r in snapshot.get("rows") or []:
        u = r.get("us") or {}
        place = u.get("place") or "Sin lugar asignado"
        pend = bool(r.get("rate_pending"))
        for s in r.get("shifts") or []:
            t = s.get("us") or {}
            day = (t.get("check_in") or {}).get("date") or ""
            week = next((d.get("week_start") for d in t.get("days") or []), "")
            w.writerow(["turno", r.get("employee_name"), place, t.get("abbr"), day, week, punch(t.get("check_in")), where(t.get("check_in")),
                        ((t.get("check_in") or {}).get("location") or {}).get("map") or "", pauses_text(t), punch(t.get("check_out")),
                        where(t.get("check_out")), ((t.get("check_out") or {}).get("location") or {}).get("map") or "", closed_by(t),
                        t.get("connected_minutes"), t.get("pause_minutes"), t.get("payable_minutes"), t.get("regular_minutes"),
                        t.get("overtime_minutes"), "", "", "", "", "", notes_text(t)])
        for wk in u.get("weeks") or []:
            w.writerow(["semana", r.get("employee_name"), place, u.get("abbr"), "", wk["week_start"], "", "", "", "", "", "", "", "",
                        "", wk["pause"], wk["payable"], wk["regular"], wk["overtime"], "", "", "", "", "", ""])
        w.writerow(["total", r.get("employee_name"), place, u.get("abbr"), "", "", "", "", "", "", "", "", "", f"{u.get('days_worked', 0)} días",
                    u.get("connected_minutes"), u.get("pause_minutes"), u.get("payable_minutes"), u.get("regular_minutes"), u.get("overtime_minutes"),
                    "Tarifa pendiente" if pend else money(u.get("rate"), False), money(u.get("regular_amount"), pend),
                    money(u.get("overtime_amount"), pend), money(u.get("deductions"), pend), money(u.get("net"), pend), ""])
    return "﻿" + buf.getvalue()


# ------------------------------------------------------------------ PDF
def build_pdf(snapshot: dict, company_name: str) -> bytes:
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    width, height = landscape(letter)
    margin = 36
    ink, soft, line = (0.07, 0.09, 0.15), (0.38, 0.42, 0.5), (0.85, 0.87, 0.9)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    y = height - margin
    page = [1]

    def footer() -> None:
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(*soft)
        c.drawString(margin, 20, f"{company_name} · Nómina (reglas EE. UU.)")
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

    def table(headers: list, rows: list, widths: list, aligns: list, size: float = 7.5) -> None:
        nonlocal y
        total = width - 2 * margin
        cols = [w_ * total for w_ in widths]

        def head() -> None:
            nonlocal y
            c.setFont("Helvetica-Bold", size)
            c.setFillColorRGB(*soft)
            x = margin
            for h_, w_, a in zip(headers, cols, aligns):
                (c.drawRightString(x + w_ - 2, y, fit(h_, size, w_ - 4, "Helvetica-Bold")) if a == "r" else c.drawString(x + 2, y, fit(h_, size, w_ - 4, "Helvetica-Bold")))
                x += w_
            y -= size + 5

        ensure(30)
        head()
        for i, r in enumerate(rows):
            if y < margin + 24:
                new_page()
                head()
            if i % 2 == 0:
                c.setFillColorRGB(0.96, 0.97, 0.98)
                c.rect(margin, y - 3, total, size + 5, stroke=0, fill=1)
            c.setFont("Helvetica", size)
            c.setFillColorRGB(*ink)
            x = margin
            for v, w_, a in zip(r, cols, aligns):
                cell = fit(v, size, w_ - 4)
                (c.drawRightString(x + w_ - 2, y, cell) if a == "r" else c.drawString(x + 2, y, cell))
                x += w_
            y -= size + 5
        y -= 4

    per = snapshot.get("period") or {}
    c.setFont("Helvetica-Bold", 15)
    c.setFillColorRGB(*ink)
    c.drawString(margin, y - 12, fit(company_name, 15, width / 2))
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*soft)
    c.drawString(margin, y - 26, "Nómina desglosada · reglas de EE. UU. (FLSA)")
    c.drawRightString(width - margin, y - 12, f"Periodo: {per.get('period_start')} a {per.get('period_end')}")
    c.drawRightString(width - margin, y - 26, f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    y -= 44
    text_line(rules_line(snapshot), 8, color=soft)
    us = snapshot.get("us_payroll") or {}
    if us.get("missing_rate"):
        names = ", ".join(m["employee_name"] for m in us["missing_rate"])
        text_line(f"{len(us['missing_rate'])} empleados sin tarifa: {names}", 8, bold=True)
    if us.get("missing_place"):
        text_line(f"Sin lugar asignado (hora de la empresa, {us.get('company_abbr')}): " + ", ".join(m["employee_name"] for m in us["missing_place"]), 8)
    y -= 4
    rows = snapshot.get("rows") or []
    text_line("Resumen por persona", 11, bold=True)
    table(["Persona", "Lugar", "Días", "En turno", "Pausas (sin pago)", "Pagables", "Regulares", "Overtime", "Tarifa", "Bruto regular",
           "Bruto overtime (1.5x)", "Deducciones", "Neto"],
          [[r["employee_name"], (r.get("us") or {}).get("place") or "Sin lugar asignado", (r.get("us") or {}).get("days_worked"),
            hm((r.get("us") or {}).get("connected_minutes")), hm((r.get("us") or {}).get("pause_minutes")), hm((r.get("us") or {}).get("payable_minutes")),
            hm(r.get("regular_minutes")), hm(r.get("extra_minutes")),
            "Tarifa pendiente" if r.get("rate_pending") else money((r.get("us") or {}).get("rate"), False),
            money((r.get("us") or {}).get("regular_amount"), r.get("rate_pending")), money((r.get("us") or {}).get("overtime_amount"), r.get("rate_pending")),
            money((r.get("us") or {}).get("deductions"), r.get("rate_pending")), money((r.get("us") or {}).get("net"), r.get("rate_pending"))] for r in rows],
          [0.15, 0.07, 0.04, 0.06, 0.07, 0.06, 0.06, 0.06, 0.08, 0.08, 0.09, 0.08, 0.1], ["l", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"])
    t = snapshot.get("totals") or {}
    text_line(f"Totales: pagables {hm(t.get('payable_minutes'))} · regulares {hm(t.get('regular_minutes'))} · overtime {hm(t.get('extra_minutes'))} · "
              f"pausas {hm(t.get('pause_minutes'))} · neto {money(t.get('net_amount'), t.get('rate_pending'))}", 9, bold=True)

    for r in rows:
        u = r.get("us") or {}
        ensure(80)
        y -= 6
        c.setStrokeColorRGB(*line)
        c.line(margin, y + 10, width - margin, y + 10)
        text_line(f"{r['employee_name']} · {u.get('place') or 'Sin lugar asignado'} · hora {u.get('abbr')}", 11, bold=True)
        for wk in u.get("weeks") or []:
            days = " · ".join(f"{day_label(d['date'])} {hm(d['payable'])}" for d in wk.get("days") or [])
            text_line(f"Semana {wk['week_start']} a {wk['week_end']}: {days} = {hm(wk['payable'])} (regular {hm(wk['regular'])}, overtime {hm(wk['overtime'])})", 8)
        table(["Fecha", "Entrada", "Ubicación", "Pausas", "Salida", "Ubicación", "Cierre", "En turno", "Pausas", "Pagable", "Overtime"],
              [[day_label((s.get("us") or {}).get("check_in", {}).get("date") or s["start"][:10]), punch((s.get("us") or {}).get("check_in")),
                where((s.get("us") or {}).get("check_in")), pauses_text(s.get("us") or {}), punch((s.get("us") or {}).get("check_out")),
                where((s.get("us") or {}).get("check_out")), closed_by(s.get("us") or {}), hm(s.get("connected_minutes")), hm(s.get("pause_minutes")),
                hm(s.get("worked_minutes")), hm(s.get("extra_minutes"))] for s in r.get("shifts") or []],
              [0.07, 0.07, 0.1, 0.26, 0.07, 0.1, 0.11, 0.055, 0.055, 0.055, 0.055], ["l", "l", "l", "l", "l", "l", "l", "r", "r", "r", "r"])
        for s in r.get("shifts") or []:
            notes = notes_text(s.get("us") or {})
            if notes:
                text_line(f"Notas {day_label((s.get('us') or {}).get('check_in', {}).get('date') or s['start'][:10])}: {notes}", 7.5, color=soft, indent=8)
    footer()
    c.save()
    return buf.getvalue()
