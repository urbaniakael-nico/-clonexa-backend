"""PDF y CSV del Board de gerencia (interruptor reports_board). Salen de reports_board.build:
mismas cifras que la pantalla y que Nomina. Sin dinero: tarifa, bruto y neto estan en Nomina."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from typing import Any, Iterable

from app.services.reports_board import GPS_LABEL, MARK_LABEL, NOTE_KINDS, _marks_of

STATE_LABEL = {"working": "Trabajando", "on_break": "En pausa", "no_shift": "Sin turno hoy", "to_confirm": "Por confirmar", "done": "Terminó"}
ALERT_TITLE = {"outside": "Fuera de perímetro", "no_location": "Sin ubicación", "to_confirm": "Turno por confirmar", "near_overtime": "Cerca de overtime"}
WEEKDAY_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
BOM = "﻿"


def hm(minutes: Any) -> str:
    m = max(0, int(minutes or 0))
    return f"{m // 60} h {m % 60:02d}"


def day_label(iso_day: str) -> str:
    d = date.fromisoformat(iso_day)
    return f"{WEEKDAY_ES[d.weekday()]} {d.day:02d}/{d.month:02d}"


def safe_cell(value: Any) -> str:
    """Texto libre en un CSV: que Excel no lo tome como formula."""
    s = str(value if value is not None else "")
    return f"'{s}" if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def op_label(o: dict) -> str:
    return f"{o['name']} ({o['abbr']})" if o.get("abbr") else o["name"]


def perimeter_text(mark: dict) -> str:
    if not mark.get("s"):
        return ""
    label = GPS_LABEL.get(mark["s"], "")
    return f"{label}: {mark['n']}" if mark.get("n") else label


def now_text(now: dict) -> str:
    state = now.get("state")
    label = STATE_LABEL.get(state, "")
    if state in ("working", "on_break"):
        return f"{label} {hm(now.get('minutes'))}"
    if state == "done" and now.get("end"):
        return f"{label} {now['end']['t']} {now['end']['a']}"
    return label


def alert_text(a: dict) -> str:
    who = f"{a.get('employee') or ''} · {day_label(a['d'])} {a['t']} {a['a']}"
    if a["kind"] in ("outside", "no_location"):
        return f"{ALERT_TITLE[a['kind']]}: {who} ({a.get('mark') or ''})"
    if a["kind"] == "to_confirm":
        return f"{'Turno abierto' if a.get('open') else 'Por confirmar'} {hm(a.get('minutes'))}: {who}"
    return f"{ALERT_TITLE['near_overtime']} ({hm(a.get('minutes'))} en la semana): {who}"


# ------------------------------------------------------------------ CSV
def build_marks_csv(board: dict) -> str:
    """Una fila por marca: operacion, empleado, documento, fecha, hora local, tipo, lat, lng, perimetro, nota."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["operacion", "empleado", "documento", "fecha", "hora_local", "tipo", "latitud", "longitud", "perimetro", "nota"])
    for o in board["operations"]:
        for p in o["people"]:
            for d in sorted(p["days"], key=lambda x: x["date"]):
                for s in d["shifts"]:
                    closing = " | ".join(n["text"] for n in s["notes"] if n["kind"] in NOTE_KINDS)
                    for m in _marks_of(s):
                        w.writerow([op_label(o), safe_cell(p["name"]), safe_cell(p["document"]), m["d"], f"{m['t']} {m['a']}", MARK_LABEL[m["k"]],
                                    m.get("lat", ""), m.get("lng", ""), perimeter_text(m), safe_cell(closing) if m["k"] == "out" else ""])
    return BOM + buf.getvalue()


def build_notes_csv(board: dict) -> str:
    """Una fila por nota: operacion, empleado, fecha, hora, texto."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["operacion", "empleado", "fecha", "hora", "texto"])
    for o in board["operations"]:
        for n in o["notes"]:
            w.writerow([op_label(o), safe_cell(n["employee"]), n.get("d") or "", f"{n['t']} {n['a']}".strip(), safe_cell(n["text"])])
    return BOM + buf.getvalue()


# ------------------------------------------------------------------ PDF
def _latin(value: Any) -> str:
    """Las fuentes base del PDF no traen emojis: se quitan sin romper tildes."""
    return " ".join(str(value if value is not None else "").encode("cp1252", "ignore").decode("cp1252").split())


def build_pdf(board: dict, *, max_notes: int = 40, max_alerts: int = 40) -> bytes:
    """Carta horizontal, por operacion: cifras, alertas, tabla A-Z y notas de cierre del periodo."""
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    width, height = landscape(letter)
    margin = 36
    ink, soft, danger = (0.07, 0.09, 0.15), (0.38, 0.42, 0.5), (0.72, 0.11, 0.11)
    accents = {0: (0.06, 0.46, 0.43), 1: (0.71, 0.33, 0.04), "x": (0.35, 0.37, 0.42)}
    company = _latin((board.get("company") or {}).get("name"))
    period = board.get("period") or {}
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    y = height - margin
    page = 1
    total_w = width - 2 * margin

    def footer() -> None:
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(*soft)
        c.drawString(margin, 20, f"{company} · Board de gerencia · Horas iguales a Nómina (turnos cerrados y confirmados). Valores de pago: ver Nómina.")
        c.drawRightString(width - margin, 20, f"Página {page}")

    def new_page() -> None:
        nonlocal y, page
        footer()
        c.showPage()
        page += 1
        y = height - margin

    def ensure(space: float) -> None:
        if y - space < margin + 12:
            new_page()

    def fit(value: Any, size: float, maxw: float, font: str = "Helvetica") -> str:
        s = _latin(value)
        while s and stringWidth(s, font, size) > maxw:
            s = s[:-2] + "…" if len(s) > 2 else ""
        return s

    def line(value: Any, size: float = 9, bold: bool = False, color=ink, indent: float = 0) -> None:
        nonlocal y
        ensure(size + 4)
        font = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(font, size)
        c.setFillColorRGB(*color)
        c.drawString(margin + indent, y, fit(value, size, total_w - indent, font))
        y -= size + 4

    def paragraph(value: Any, size: float = 8.5, indent: float = 0) -> None:
        nonlocal y
        for part in simpleSplit(_latin(value), "Helvetica", size, total_w - indent) or [""]:
            ensure(size + 3)
            c.setFont("Helvetica", size)
            c.setFillColorRGB(*ink)
            c.drawString(margin + indent, y, part)
            y -= size + 3

    def stats(items: Iterable[tuple[str, str]], accent) -> None:
        nonlocal y
        items = list(items)
        ensure(34)
        step = total_w / len(items)
        for i, (k, v) in enumerate(items):
            x = margin + i * step
            c.setFont("Helvetica", 7)
            c.setFillColorRGB(*soft)
            c.drawString(x, y, fit(k, 7, step - 6))
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(*accent)
            c.drawString(x, y - 13, fit(v, 10, step - 6, "Helvetica-Bold"))
        y -= 28

    headers = ["Empleado", "Rol", "Ahora", "Días", "En turno", "Pausas", "Pagables", "Overtime", "Fuera", "Notas", "Mat.", "Última marca"]
    cols = [w * total_w for w in (0.2, 0.09, 0.14, 0.035, 0.07, 0.065, 0.07, 0.07, 0.04, 0.04, 0.035, 0.135)]
    aligns = ["l", "l", "l", "r", "r", "r", "r", "r", "r", "r", "r", "l"]

    def row(values: list, font: str, color, size: float = 7.5, danger_col: int | None = None) -> None:
        x = margin
        c.setFont(font, size)
        for i, (v, w_, a) in enumerate(zip(values, cols, aligns)):
            c.setFillColorRGB(*(danger if i == danger_col else color))
            cell = fit(v, size, w_ - 4, font)
            (c.drawRightString(x + w_ - 3, y, cell) if a == "r" else c.drawString(x + 3, y, cell))
            x += w_

    def table_head(accent) -> None:
        nonlocal y
        c.setFillColorRGB(*accent)
        c.rect(margin, y - 4, total_w, 14, stroke=0, fill=1)
        row(headers, "Helvetica-Bold", (1, 1, 1))
        y -= 15

    c.setFont("Helvetica-Bold", 15)
    c.setFillColorRGB(*ink)
    c.drawString(margin, y - 12, fit(f"{company} · Board de gerencia", 15, width / 2, "Helvetica-Bold"))
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*soft)
    c.drawRightString(width - margin, y - 12, f"Periodo: {period.get('start')} a {period.get('end')}")
    c.drawRightString(width - margin, y - 26, f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    c.drawString(margin, y - 26, "Overtime por encima de 40 h · Pausas sin pago · Hora local de cada operación")
    y -= 42
    f = board["figures"]
    stats([("En turno ahora", str(f["working"])), ("En pausa ahora", str(f["on_break"])), ("Sin turno hoy", str(f["no_shift"])), ("Horas en turno", hm(f["connected"])),
           ("Pausas", hm(f["pause"])), ("Fuera de perímetro", str(f["outside"])), ("Por confirmar", str(f["to_confirm"])), ("Notas del periodo", str(f["notes"]))], ink)

    for o in board["operations"]:
        accent = accents.get(o["color"], accents["x"])
        ensure(90)
        y -= 6
        c.setFillColorRGB(*accent)
        c.rect(margin, y - 3, 4, 16, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 12)
        c.setFillColorRGB(*ink)
        supervisors = ", ".join(o["supervisors"]) or "sin supervisor"
        c.drawString(margin + 10, y, fit(f"{op_label(o)} · {len(o['people'])} personas · Supervisor: {supervisors}", 12, total_w - 10, "Helvetica-Bold"))
        y -= 20
        if o.get("perimeter_missing"):
            line("Perímetro sin configurar: las marcas dicen Sin perímetro.", 8, color=soft)
        fig = o["figures"]
        stats([("En turno", str(fig["working"])), ("En pausa", str(fig["on_break"])), ("Horas en turno", hm(fig["connected"])), ("Pausas", hm(fig["pause"])), ("Pagables", hm(fig["payable"])),
               ("Overtime", hm(fig["overtime"])), ("Fuera de perímetro", str(fig["outside"])), ("Notas", str(fig["notes"]))], accent)

        alerts = o["alerts"]
        line(f"Alertas ({len(alerts)})", 10, bold=True, color=accent)
        if not alerts:
            line("Sin alertas.", 8.5, color=soft)
        for a in alerts[:max_alerts]:
            line(alert_text(a), 8, indent=6)
        if len(alerts) > max_alerts:
            line(f"… y {len(alerts) - max_alerts} más (detalle en pantalla y en el CSV de marcaciones).", 8, color=soft, indent=6)
        y -= 4

        ensure(40)
        table_head(accent)
        for i, p in enumerate(o["people"]):
            if y < margin + 28:
                new_page()
                table_head(accent)
            if i % 2 == 1:
                c.setFillColorRGB(0.96, 0.97, 0.98)
                c.rect(margin, y - 3, total_w, 12, stroke=0, fill=1)
            last = p.get("last_mark")
            row([p["name"], p["role"] or "—", now_text(p["now"]), p["days_worked"], hm(p["connected"]), hm(p["pause"]), hm(p["payable"]), hm(p["overtime"]),
                 p["outside"], p["notes"], p["materials"], f"{day_label(last['d'])} {last['t']} {last['a']}" if last else "—"],
                "Helvetica", ink, danger_col=8 if p["outside"] else None)
            y -= 12
        y -= 8

        notes = o["notes"]
        line(f"Notas de cierre ({len(notes)})", 10, bold=True, color=accent)
        if not notes:
            line("Sin notas en el periodo.", 8.5, color=soft)
        for n in notes[:max_notes]:
            ensure(26)
            line(f"{n['employee']} · {day_label(n['d']) if n.get('d') else ''} {n['t']} {n['a']}" + (f" · {n['label']}" if n.get("label") else ""), 8.5, bold=True, indent=6)
            paragraph(n["text"], indent=6)
            y -= 2
        if len(notes) > max_notes:
            line(f"… y {len(notes) - max_notes} más (todas en el CSV de notas).", 8, color=soft, indent=6)
        y -= 6
    footer()
    c.save()
    return buf.getvalue()
