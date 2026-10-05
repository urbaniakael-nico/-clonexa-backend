"""Comprobante de pago en PDF (reportlab). No es factura electronica.

Datos de Clonexa por variables de entorno (nunca en el repo):
CLONEXA_BILLING_ISSUER_NAME, CLONEXA_BILLING_ISSUER_ID (NIT),
CLONEXA_BILLING_ISSUER_CONTACT. Sin ellas: "Clonexa".
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.services import billing

LEGEND = "Comprobante de pago. No es factura electrónica."
LOGO = Path(__file__).resolve().parent.parent / "web" / "assets" / "clonexa-logo.png"


def issuer() -> dict:
    return {"name": os.getenv("CLONEXA_BILLING_ISSUER_NAME", "").strip() or "Clonexa",
            "id": os.getenv("CLONEXA_BILLING_ISSUER_ID", "").strip(),
            "contact": os.getenv("CLONEXA_BILLING_ISSUER_CONTACT", "").strip()}


def fmt_money(value: Any, currency: str) -> str:
    d = Decimal(str(value or 0))
    whole = f"{d:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if whole.endswith(",00"):
        whole = whole[:-3]
    return f"{currency} {whole}"


def fmt_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(billing.TZ).strftime("%d/%m/%Y %H:%M")
    if value is None:
        return "—"
    try:
        return value.strftime("%d/%m/%Y")
    except AttributeError:
        return str(value)


def render(r: dict) -> bytes:
    """PDF de un comprobante (fila de billing.receipt)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    code = billing.receipt_code(r["number"])
    c.setTitle(f"Comprobante {code}")
    c.setAuthor(issuer()["name"])
    width, height = A4
    left, top = 22 * mm, height - 24 * mm
    ink, muted, accent = colors.HexColor("#1b1d24"), colors.HexColor("#5f6472"), colors.HexColor("#8a6d2f")

    # Encabezado: logo (o marca CX) y datos de Clonexa
    if LOGO.exists():
        try:
            c.drawImage(str(LOGO), left, top - 14 * mm, width=30 * mm, height=14 * mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    else:
        c.setFillColor(ink)
        c.roundRect(left, top - 13 * mm, 13 * mm, 13 * mm, 2.5 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(left + 6.5 * mm, top - 8.6 * mm, "CX")
    who = issuer()
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(width - left, top - 4 * mm, who["name"].upper())
    c.setFont("Helvetica", 9)
    c.setFillColor(muted)
    y = top - 9 * mm
    for line in (f"NIT {who['id']}" if who["id"] else "", who["contact"]):
        if line:
            c.drawRightString(width - left, y, line)
            y -= 4.5 * mm

    # Titulo y numero
    y = top - 30 * mm
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, y, "Comprobante de pago")
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(accent)
    c.drawRightString(width - left, y, f"N.º {code}")
    c.setStrokeColor(colors.HexColor("#d9d4c7"))
    c.line(left, y - 4 * mm, width - left, y - 4 * mm)

    rows = [
        ("Empresa", r["company_name"]),
        ("Periodo", f"{billing.period_label(r['period'])} (cuota {r['seq']})"),
        ("Valor", fmt_money(r["amount"], r.get("currency") or "COP")),
        ("Medio de pago", billing.METHODS.get(r["method"], r["method"])),
        ("Referencia", r.get("reference") or "—"),
        ("Fecha del pago", fmt_dt(r.get("paid_on"))),
        ("Validado el", fmt_dt(r.get("validated_at"))),
    ]
    y -= 14 * mm
    for label, value in rows:
        c.setFont("Helvetica", 9.5)
        c.setFillColor(muted)
        c.drawString(left, y, label.upper())
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(ink)
        c.drawString(left + 45 * mm, y, str(value)[:70])
        y -= 9 * mm

    if r.get("status") == "anulado":
        c.saveState()
        c.setFillColor(colors.HexColor("#b3261e"))
        c.setFont("Helvetica-Bold", 54)
        c.translate(width / 2, height / 2 - 20 * mm)
        c.rotate(24)
        c.drawCentredString(0, 0, "ANULADO")
        c.restoreState()
        c.setFont("Helvetica", 9.5)
        c.setFillColor(colors.HexColor("#b3261e"))
        c.drawString(left, y - 2 * mm, f"Anulado el {fmt_dt(r.get('voided_at'))}. Motivo: {str(r.get('void_reason') or '')[:90]}")

    c.setFont("Helvetica-Oblique", 9.5)
    c.setFillColor(muted)
    c.drawString(left, 20 * mm, LEGEND)
    c.drawRightString(width - left, 20 * mm, code)
    c.showPage()
    c.save()
    return buf.getvalue()
