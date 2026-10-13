"""Reportes v2 (interruptor reports_v2 del modulo reports; hoy solo VOLTAGE).

No cambia ningun calculo de Reportes: toma el payload de siempre
(build_report_payload) y agrupa lo que la pantalla nueva y su PDF muestran:
- seis cifras (en turno, horas, nomina neta, fuera de perimetro, material
  pendiente y stock bajo);
- horas por dia (ordinarias y extra) a partir de los turnos de nomina;
- alertas: marcacion fuera de perimetro, colaborador que pasa las horas
  semanales de la empresa, orden entregada hace mas de 2 dias sin devolucion
  ni consigna y material en cero;
- materiales en cuatro cajas (solicitadas, entregadas, consignadas, devueltas);
- inventario bajo minimo y una tarjeta por colaborador con su detalle por turno.
Acceso: con reports_v2 solo el dueno (company_admin / admin_empresa / dueno /
owner / propietario) y el director (gerencia / director) abren Reportes y el PDF.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SWITCH = "reports_v2"
MODULE = "reports"
OWNER_ROLES = {"company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"}
DIRECTOR_ROLES = {"gerencia", "director"}
DENIED = "Reportes es solo del dueño y del director"
DEFAULT_WEEKLY_HOURS = 48.0
STALE_DELIVERY_DAYS = 2

OPEN_ORDER = {"pending", "pendiente", "approved", "aprobado", "aprobada", "requested", "solicitado", "solicitada"}
DELIVERED = {"delivered", "entregado", "entregada"}
CONSIGNED = {"consigned", "consigned_partial", "consignado", "consignada", "installed", "instalado"}
RETURNED = {"returned", "returned_partial", "devuelto", "devuelta"}
CLOSED_ORDER = {"rejected", "rechazado", "cancelled", "canceled", "cancelado"}


def _settings(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


async def is_on(db: AsyncSession, company_id: Any) -> bool:
    row = (await db.execute(text("""
        SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :c AND m.code = :m AND cm.enabled IS TRUE LIMIT 1
    """), {"c": str(company_id), "m": MODULE})).mappings().first()
    return bool(row) and _settings(row["settings"]).get(SWITCH) is True


def role_allowed(role: Any) -> bool:
    value = str(role or "").strip().lower()
    return value in OWNER_ROLES or value in DIRECTOR_ROLES


async def weekly_limit_minutes(db: AsyncSession, company_id: Any) -> int:
    row = (await db.execute(text("SELECT settings_json FROM companies WHERE id::text = :c"), {"c": str(company_id)})).mappings().first()
    payroll = (_settings(row["settings_json"]).get("client_settings") or {}).get("payroll") if row else {}
    try:
        hours = float((payroll or {}).get("ordinary_hours_limit") or DEFAULT_WEEKLY_HOURS)
    except (TypeError, ValueError):
        hours = DEFAULT_WEEKLY_HOURS
    return int(round(hours * 60))


async def role_codes(db: AsyncSession, company_id: Any) -> dict[str, str]:
    rows = (await db.execute(text("SELECT id::text AS id, role FROM employees WHERE company_id::text = :c"), {"c": str(company_id)})).mappings().all()
    return {r["id"]: str(r["role"] or "").strip().lower() for r in rows}


# ----------------------------------------------------------------- utilidades
def _dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    return int(round(_num(value)))


def hm(minutes: Any) -> str:
    """Horas como "X h YY min"."""
    m = max(0, _int(minutes))
    return f"{m // 60} h {m % 60:02d} min"


def _status(value: Any) -> str:
    return str(value or "").strip().lower()


def _local_day(value: Any, tz: ZoneInfo) -> Optional[date]:
    d = _dt(value)
    return d.astimezone(tz).date() if d else None


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


# ----------------------------------------------------------------- agrupacion
def build_insights(payload: dict, tz: ZoneInfo, weekly_limit: int, now: datetime, codes: Optional[dict] = None) -> dict:
    """Todo lo de la pantalla y el PDF de Reportes v2, desde el payload de siempre. Funcion pura."""
    codes = codes or {}
    summary = payload.get("summary") or {}
    details = payload.get("details") or {}
    employees = [e for e in details.get("employees") or [] if _status(e.get("status")) not in ("archived", "deleted")]
    payroll_rows = details.get("payroll") or []
    materials = details.get("materials") or []
    inventory = details.get("inventory_items") or []
    gps = details.get("gps") or []
    attendance = details.get("attendance") or []
    by_emp_payroll = {str(r.get("employee_id")): r for r in payroll_rows}
    by_emp_summary = {str(r.get("employee_id")): r for r in details.get("employee_summary") or []}

    # En turno: el ultimo evento de asistencia de cada persona.
    last: dict[str, dict] = {}
    for ev in attendance:
        eid = str(ev.get("employee_id") or "")
        at = _dt(ev.get("occurred_at") or ev.get("created_at"))
        if eid and at and (eid not in last or at > last[eid]["at"]):
            last[eid] = {"at": at, "type": _status(ev.get("event_type"))}
    shift_state = {eid: ("working" if v["type"] in ("check_in", "break_end", "resume") else "break" if v["type"] == "break_start" else "off")
                   for eid, v in last.items()}
    att = summary.get("attendance") or {}
    in_shift = _int(att.get("active_now")) + _int(att.get("paused_now"))
    if not in_shift and shift_state:
        in_shift = sum(1 for s in shift_state.values() if s != "off")

    # Horas por dia (ordinarias y extra) y por semana, con los turnos de nomina.
    period = (summary.get("period") or {})
    start_day = _local_day(period.get("start") or (payload.get("filters") or {}).get("start"), tz)
    end_day = _local_day(period.get("end") or (payload.get("filters") or {}).get("end"), tz)
    per_day: dict[date, dict] = {}
    weeks: dict[tuple, int] = {}
    for row in payroll_rows:
        eid = str(row.get("employee_id"))
        for sh in row.get("shifts") or []:
            day = _local_day(sh.get("start"), tz)
            if not day:
                continue
            reg, ext = _int(sh.get("regular_minutes")), _int(sh.get("extra_minutes"))
            d = per_day.setdefault(day, {"regular": 0, "extra": 0})
            d["regular"] += reg
            d["extra"] += ext
            weeks[(eid, _monday(day))] = weeks.get((eid, _monday(day)), 0) + reg + ext
    days = []
    if start_day and end_day and (end_day - start_day).days <= 62:
        cursor = start_day
        while cursor <= end_day:
            d = per_day.get(cursor, {"regular": 0, "extra": 0})
            days.append({"date": cursor.isoformat(), **d})
            cursor += timedelta(days=1)
    else:
        days = [{"date": k.isoformat(), **v} for k, v in sorted(per_day.items())]

    # Alertas.
    name_of = {str(e.get("id")): e.get("full_name") or "" for e in employees}
    alerts: list[dict] = []
    for g in gps:
        st = _status(g.get("gps_status") or g.get("status"))
        if st in ("outside", "fuera", "out"):
            alerts.append({"kind": "gps_outside", "level": "warning", "employee": g.get("employee_name") or name_of.get(str(g.get("employee_id")), ""),
                           "at": g.get("occurred_at") or g.get("created_at"), "detail": g.get("event_label") or ""})
    for (eid, monday), minutes in sorted(weeks.items(), key=lambda kv: (kv[0][1], name_of.get(kv[0][0], ""))):
        if minutes > weekly_limit:
            alerts.append({"kind": "weekly_hours", "level": "warning", "employee": name_of.get(eid) or (by_emp_payroll.get(eid) or {}).get("employee_name") or "",
                           "week": monday.isoformat(), "minutes": minutes, "limit": weekly_limit})
    stale = now - timedelta(days=STALE_DELIVERY_DAYS)
    for m in materials:
        st = _status(m.get("status"))
        delivered = _dt(m.get("delivered_at"))
        if st in DELIVERED and delivered and delivered < stale:
            alerts.append({"kind": "stale_delivery", "level": "warning", "employee": m.get("employee_name") or "", "order": m.get("order_number") or "",
                           "material": m.get("material_name") or "", "at": m.get("delivered_at")})
    for item in inventory:
        if _num(item.get("current_stock")) <= 0 and _status(item.get("status")) not in ("archived", "inactive"):
            alerts.append({"kind": "zero_stock", "level": "danger", "material": item.get("name") or item.get("name_reference") or ""})

    # Materiales en cuatro cajas.
    def order_view(m: dict) -> dict:
        return {"order": m.get("order_number") or "", "material": m.get("material_name") or "", "quantity": _num(m.get("quantity")),
                "returned": _num(m.get("quantity_returned")), "unit": m.get("unit") or "", "employee": m.get("employee_name") or "",
                "status": _status(m.get("status")), "requested_at": m.get("requested_at") or m.get("created_at"), "delivered_at": m.get("delivered_at"),
                "returned_at": m.get("returned_at")}
    live = [m for m in materials if _status(m.get("status")) not in CLOSED_ORDER]
    boxes = {
        "requested": [order_view(m) for m in live],
        "delivered": [order_view(m) for m in live if m.get("delivered_at") or _status(m.get("status")) in DELIVERED | CONSIGNED | RETURNED],
        "consigned": [order_view(m) for m in live if _status(m.get("status")) in CONSIGNED],
        "returned": [order_view(m) for m in live if _status(m.get("status")) in RETURNED],
    }
    pending_materials = sum(1 for m in live if _status(m.get("status")) in OPEN_ORDER
                            or (_status(m.get("status")) in DELIVERED | {"returned_partial", "consigned_partial"}))

    # Inventario bajo minimo.
    low = []
    for item in inventory:
        stock, minimum = _num(item.get("current_stock")), _num(item.get("min_stock"))
        if stock <= 0:
            label = "zero"
        elif minimum > 0 and stock < minimum:
            label = "low"
        else:
            continue
        low.append({"material": item.get("name") or item.get("name_reference") or "", "stock": stock, "min": minimum, "label": label})
    low.sort(key=lambda x: (x["label"] != "zero", x["material"].lower()))

    # Personal: una tarjeta por colaborador.
    people = []
    for e in employees:
        eid = str(e.get("id"))
        pr = by_emp_payroll.get(eid) or {}
        sm = by_emp_summary.get(eid) or {}
        code = codes.get(eid, "")
        shifts = [{"start": sh.get("start"), "end": sh.get("end"), "regular": _int(sh.get("regular_minutes")), "extra": _int(sh.get("extra_minutes")),
                   "pause": _int(sh.get("pause_minutes")), "gross": _num(sh.get("gross_amount"))} for sh in pr.get("shifts") or []]
        people.append({
            "employee_id": eid, "name": e.get("full_name") or "", "role": e.get("role") or "", "role_code": code,
            "state": shift_state.get(eid, "off"), "regular": _int(pr.get("regular_minutes")), "extra": _int(pr.get("extra_minutes")),
            "gps_outside": _int(sm.get("gps_fuera")), "orders_requested": _int(sm.get("materiales")) if code == "supervisor" else None,
            "deliveries": _int(sm.get("material_entregado")) if code in ("inventario", "logistica") else None,
            "net": _num(pr.get("net_amount")), "shifts": sorted(shifts, key=lambda x: str(x["start"] or "")),
        })
    people.sort(key=lambda p: (p["state"] == "off", p["name"].lower()))

    inv = summary.get("inventory") or {}
    pay = summary.get("payroll") or {}
    emp = summary.get("employees") or {}
    return {
        "figures": {
            "in_shift": in_shift, "active": _int(emp.get("active")) or len(employees),
            "regular_minutes": _int(pay.get("regular_minutes")), "extra_minutes": _int(pay.get("extra_minutes")),
            "net": _num(pay.get("net_amount")), "gps_outside": _int((summary.get("gps") or {}).get("outside")),
            "materials_pending": pending_materials, "low_stock": _int(inv.get("low_stock")), "zero_stock": _int(inv.get("zero_stock")),
        },
        "hours_by_day": days, "alerts": alerts, "materials": boxes, "inventory_low": low, "people": people,
        "weekly_limit_minutes": weekly_limit, "period": {"start": start_day.isoformat() if start_day else None, "end": end_day.isoformat() if end_day else None},
    }


async def insights_for(db: AsyncSession, company_id: Any, payload: dict, now: Optional[datetime] = None) -> dict:
    from app.services import company_locale

    return build_insights(payload, company_locale.current_zone(), await weekly_limit_minutes(db, company_id),
                          now or datetime.now(timezone.utc), await role_codes(db, company_id))


# ----------------------------------------------------------------- PDF (carta, para imprimir)
STATUS_LABEL = {
    "pending": "Pendiente", "pendiente": "Pendiente", "approved": "Aprobada", "aprobado": "Aprobada", "requested": "Solicitada",
    "delivered": "Entregada", "entregado": "Entregada", "consigned": "Consignada", "consigned_partial": "Consignada parcial",
    "returned": "Devuelta", "returned_partial": "Devuelta parcial", "rejected": "Rechazada", "cancelled": "Cancelada",
    "working": "En turno", "break": "En pausa", "off": "Fuera de turno",
}
ALERT_TEXT = {
    "gps_outside": "Marcación fuera de perímetro: {employee} · {at}",
    "weekly_hours": "{employee} pasó las {limit} de la semana del {week}: {hours}",
    "stale_delivery": "Orden {order} ({material}) entregada hace más de 2 días sin devolución ni consigna · {employee}",
    "zero_stock": "Material en cero: {material}",
}
MONTHS = {
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "fr": ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
}


def _lang() -> str:
    from app.services import pdf_i18n

    return pdf_i18n.language()


def fmt_day(value: Any, tz: ZoneInfo, with_time: bool = False) -> str:
    """Fecha (y hora) en el idioma de la empresa y en su zona horaria."""
    clock = ""
    if isinstance(value, datetime) or (isinstance(value, str) and len(value) > 10):
        d = _dt(value)
        if d is None:
            return "—"
        local = d.astimezone(tz)
        day, clock = local.date(), local.strftime("%H:%M")
    elif isinstance(value, date):
        day = value
    else:
        try:
            day = date.fromisoformat(str(value)[:10])
        except ValueError:
            return "—"
    lang = _lang()
    month = MONTHS.get(lang, MONTHS["es"])[day.month - 1]
    text_day = f"{month} {day.day}, {day.year}" if lang == "en" else f"{day.day} {month} {day.year}"
    return f"{text_day} {clock}".strip() if with_time and clock else text_day


def money(value: Any) -> str:
    from app.services import company_locale

    from decimal import ROUND_HALF_UP, Decimal

    # En COP, el formato de siempre ("$ 1.234"), redondeando .5 hacia arriba como el portal.
    return company_locale.money_here(value, lambda v: f"$ {int(Decimal(str(_num(v))).quantize(Decimal(1), rounding=ROUND_HALF_UP)):,}".replace(",", "."))


def build_pdf(payload: dict, ins: dict, tz: ZoneInfo, logo_reader=None) -> bytes:
    import io

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    from app.services import pdf_i18n

    tr = pdf_i18n.tr
    width, height = letter
    margin = 46  # ~0,65 in: margen de impresion
    ink, soft, line = (0.07, 0.09, 0.15), (0.38, 0.42, 0.5), (0.85, 0.87, 0.9)
    company = payload.get("company") or {}

    class Numbered(canvas.Canvas):
        """Pie "Página X de Y": se dibuja al final, cuando ya se sabe el total."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self.setFont("Helvetica", 8)
                self.setFillColorRGB(*soft)
                self.drawRightString(width - margin, 24, f"Página {self._pageNumber} de {total}")
                self.drawString(margin, 24, f"{company.get('name') or ''} · Reportes")
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

    buf = io.BytesIO()
    c = Numbered(buf, pagesize=letter)
    fig = ins["figures"]
    y = height - margin

    def ensure(space: float) -> None:
        nonlocal y
        if y - space < margin + 20:
            c.showPage()
            y = height - margin

    def fit(text_value: Any, size: float, maxw: float, font: str = "Helvetica") -> str:
        s = str(tr(str(text_value)) if text_value is not None else "")
        while s and stringWidth(s, font, size) > maxw:
            s = s[:-2] + "…" if len(s) > 2 else ""
        return s

    def note(message: str) -> None:
        nonlocal y
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*soft)
        c.drawString(margin, y, message)
        y -= 16

    def section(title: str) -> None:
        nonlocal y
        ensure(44)
        y -= 10
        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(*ink)
        c.drawString(margin, y, title)
        y -= 6
        c.setStrokeColorRGB(*line)
        c.line(margin, y, width - margin, y)
        y -= 14

    def table(headers: list, rows: list, widths: list, aligns: list) -> None:
        nonlocal y
        total_w = width - 2 * margin
        cols = [w * total_w for w in widths]

        def head() -> None:
            nonlocal y
            c.setFont("Helvetica-Bold", 8)
            c.setFillColorRGB(*soft)
            x = margin
            for h_, w, a in zip(headers, cols, aligns):
                label = fit(h_, 8, w - 4, "Helvetica-Bold")
                if a == "r":
                    c.drawRightString(x + w - 2, y, label)
                else:
                    c.drawString(x + 2, y, label)
                x += w
            y -= 12

        ensure(30)
        head()
        for i, r in enumerate(rows):
            if y < margin + 30:
                c.showPage()
                y = height - margin
                head()
            if i % 2 == 0:
                c.setFillColorRGB(0.96, 0.97, 0.98)
                c.rect(margin, y - 3, total_w, 13, stroke=0, fill=1)
            c.setFont("Helvetica", 9)
            c.setFillColorRGB(*ink)
            x = margin
            for v, w, a in zip(r, cols, aligns):
                cell = fit(v, 9, w - 4)
                if a == "r":
                    c.drawRightString(x + w - 2, y, cell)
                else:
                    c.drawString(x + 2, y, cell)
                x += w
            y -= 13
        y -= 4

    # Encabezado: logo, empresa, titulo y periodo (fondo blanco).
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    left = margin
    if logo_reader is not None:
        try:
            c.drawImage(logo_reader, margin, y - 40, width=40, height=40, preserveAspectRatio=True, mask="auto")
            left = margin + 50
        except Exception:
            pass
    c.setFillColorRGB(*ink)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y - 14, fit(company.get("name") or "", 16, width / 2 - left, "Helvetica-Bold"))
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(*soft)
    c.drawString(left, y - 30, "Reporte general")
    per = ins.get("period") or {}
    period_text = f"{fmt_day(per.get('start'), tz)} – {fmt_day(per.get('end'), tz)}" if per.get("start") else "—"
    c.drawRightString(width - margin, y - 14, f"{tr('Periodo')}: {period_text}")
    c.drawRightString(width - margin, y - 30, f"{tr('Generado:')} {fmt_day(datetime.now(timezone.utc), tz, True)}")
    y -= 58

    section("Cifras del periodo")
    tiles = [
        ("En turno ahora", f"{fig['in_shift']} / {fig['active']}"),
        ("Horas trabajadas", hm(fig["regular_minutes"] + fig["extra_minutes"])),
        ("Nómina del periodo (neto)", money(fig["net"])),
        ("Fuera de perímetro", str(fig["gps_outside"])),
        ("Material pendiente", str(fig["materials_pending"])),
        ("Stock bajo", f"{fig['low_stock']} · {fig['zero_stock']} {tr('en cero')}"),
    ]
    tile_w = (width - 2 * margin - 2 * 8) / 3
    for i, (label, value) in enumerate(tiles):
        col, row = i % 3, i // 3
        x0, y0 = margin + col * (tile_w + 8), y - row * 46
        c.setStrokeColorRGB(*line)
        c.roundRect(x0, y0 - 34, tile_w, 40, 5, stroke=1, fill=0)
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(*soft)
        c.drawString(x0 + 8, y0 - 6, fit(label, 8, tile_w - 16))
        c.setFont("Helvetica-Bold", 13)
        c.setFillColorRGB(*ink)
        c.drawString(x0 + 8, y0 - 24, fit(value, 13, tile_w - 16, "Helvetica-Bold"))
    y -= 98

    section("Horas por día")
    worked = [d for d in ins["hours_by_day"] if d["regular"] or d["extra"]]
    if worked:
        table(["Fecha", "Ordinarias", "Extra", "Total"],
              [[fmt_day(d["date"], tz), hm(d["regular"]), hm(d["extra"]), hm(d["regular"] + d["extra"])] for d in worked],
              [0.4, 0.2, 0.2, 0.2], ["l", "r", "r", "r"])
    else:
        note("Sin horas en el periodo.")

    section("Alertas")
    if ins["alerts"]:
        for a in ins["alerts"]:
            ensure(14)
            values = {"employee": a.get("employee") or "—", "at": fmt_day(a.get("at"), tz, True), "week": fmt_day(a.get("week"), tz),
                      "limit": hm(a.get("limit", 0)), "hours": hm(a.get("minutes", 0)), "order": a.get("order") or "", "material": a.get("material") or ""}
            c.setFont("Helvetica", 9)
            c.setFillColorRGB(*ink)
            c.drawString(margin, y, fit("• " + tr(ALERT_TEXT[a["kind"]]).format(**values), 9, width - 2 * margin))
            y -= 13
    else:
        note("Sin alertas.")

    section("Materiales")
    boxes = ins["materials"]
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*ink)
    c.drawString(margin, y, f"{tr('Solicitadas')} {len(boxes['requested'])} → {tr('Entregadas')} {len(boxes['delivered'])} → "
                            f"{tr('Consignadas/instaladas')} {len(boxes['consigned'])} → {tr('Devueltas')} {len(boxes['returned'])}")
    y -= 16
    if boxes["requested"]:
        table(["Orden", "Material", "Cantidad", "Colaborador", "Estado"],
              [[o["order"], o["material"], f"{o['quantity']:g} {o['unit']}".strip(), o["employee"], STATUS_LABEL.get(o["status"], o["status"])]
               for o in boxes["requested"]],
              [0.16, 0.3, 0.14, 0.24, 0.16], ["l", "l", "r", "l", "l"])

    section("Inventario bajo mínimo")
    if ins["inventory_low"]:
        table(["Material", "Stock", "Mínimo", "Estado"],
              [[i["material"], f"{i['stock']:g}", f"{i['min']:g}", "Cero" if i["label"] == "zero" else "Bajo"] for i in ins["inventory_low"]],
              [0.5, 0.15, 0.15, 0.2], ["l", "r", "r", "l"])
    else:
        note("Sin materiales bajo el mínimo.")

    section("Personal")
    table(["Colaborador", "Rol", "Estado", "Horas", "Extra", "Fuera de perímetro", "Neto"],
          [[p["name"], p["role"], STATUS_LABEL.get(p["state"], p["state"]), hm(p["regular"] + p["extra"]), hm(p["extra"]), str(p["gps_outside"]), money(p["net"])]
           for p in ins["people"]],
          [0.22, 0.13, 0.13, 0.13, 0.12, 0.14, 0.13], ["l", "l", "l", "r", "r", "r", "r"])
    c.showPage()
    c.save()
    return buf.getvalue()
