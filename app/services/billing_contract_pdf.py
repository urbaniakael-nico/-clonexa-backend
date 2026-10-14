"""PDF del contrato redactado (reportlab/platypus, tamano carta).

Banda superior con el logo NUEVO de Clonexa (app/web/brand_assets), titulo,
numero, version y verificacion en CADA pagina; tarjetas de Proveedor, Cliente
(con SU logo, el de panel_logo), Vigencia y Pago; franja de precios con el
compromiso minimo; modulos como etiquetas; clausulas de la plantilla; tabla de
cuotas; anexos y firmas; pie con numero, "Pagina X de Y" y contacto.
Sin paginas en blanco: no hay saltos forzados al final y render() devuelve
cuantos bloques del cuerpo cayeron en cada pagina (las pruebas lo revisan).
Un dato opcional vacio sale como linea para llenar, resaltada en amarillo suave.
"""
from __future__ import annotations

import io
from typing import Optional
from xml.sax.saxutils import escape

INK = "#1b1530"
BAND = "#14111f"
PINK = "#ff2e93"
RED = "#ff3b3b"
MUTED = "#5f6472"
SOFT = "#f6f4fb"
LINE = "#e3dff0"
FILL = "#fff4bf"
BLANK_MARKUP = f'<font backColor="{FILL}">&nbsp;______________________&nbsp;</font>'
SHORT_MARKUP = f'<font backColor="{FILL}">&nbsp;________&nbsp;</font>'


def seg_markup(segments) -> str:
    return "".join(BLANK_MARKUP if kind == "b" else SHORT_MARKUP if kind == "s" else escape(str(txt)) for kind, txt in segments)


def val_markup(value) -> str:
    return BLANK_MARKUP if value in (None, "") else escape(str(value))


def render(c: dict, client_logo: Optional[bytes] = None, qr: Optional[bytes] = None) -> tuple[bytes, dict]:
    """-> (pdf, {"pages": N, "body": {pagina: bloques}, "stamped": {pagina: texto del pie}})."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, PageTemplate, Paragraph, Spacer,
                                    Table, TableStyle)

    from app.web import brand_assets

    W, H = letter
    LM = RM = 18 * mm
    BAND_H = 22 * mm
    info = {"pages": 0, "body": {}, "stamped": {}}
    number, version, verification = c["number"], c["version"], c["verification"]
    stamp = f"Contrato {number} · Versión {version} · Verificación {verification}"
    logo_dark = ImageReader(str(brand_assets.pdf_logo_dark()))

    def band(cv, page_no: int, total: int) -> None:
        cv.saveState()
        cv.setFillColor(colors.HexColor(BAND))
        cv.rect(0, H - BAND_H, W, BAND_H, stroke=0, fill=1)
        cv.setFillColor(colors.HexColor(PINK))
        cv.rect(0, H - BAND_H - 1.2 * mm, W * 0.62, 1.2 * mm, stroke=0, fill=1)
        cv.setFillColor(colors.HexColor(RED))
        cv.rect(W * 0.62, H - BAND_H - 1.2 * mm, W * 0.38, 1.2 * mm, stroke=0, fill=1)
        cv.drawImage(logo_dark, LM, H - BAND_H + 6.5 * mm, width=51 * mm, height=9 * mm, preserveAspectRatio=True, mask="auto")
        cv.setFillColor(colors.white)
        cv.setFont("Helvetica-Bold", 9.5)
        cv.drawRightString(W - RM, H - 9.5 * mm, "CONTRATO DE SERVICIO")
        cv.setFont("Helvetica", 7.5)
        cv.setFillColor(colors.HexColor("#d9d4ea"))
        cv.drawRightString(W - RM, H - 14 * mm, f"N.º {number} · Versión {version} · Verificación {verification}")
        # pie
        cv.setStrokeColor(colors.HexColor(LINE))
        cv.setLineWidth(0.6)
        cv.line(LM, 15 * mm, W - RM, 15 * mm)
        cv.setFont("Helvetica", 7.2)
        cv.setFillColor(colors.HexColor(MUTED))
        cv.drawString(LM, 10.5 * mm, stamp)
        cv.drawRightString(W - RM, 10.5 * mm, f"Página {page_no} de {total}")
        cv.drawString(LM, 6.8 * mm, c.get("contact") or "CLONEXA")
        cv.restoreState()
        info["stamped"][page_no] = f"{stamp} · Página {page_no} de {total}"

    class Numbered(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._states = []

        def showPage(self):
            self._states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._states)
            info["pages"] = total
            for i, state in enumerate(self._states, start=1):
                self.__dict__.update(state)
                band(self, i, total)
                super().showPage()
            super().save()

    class Doc(BaseDocTemplate):
        def afterFlowable(self, flowable):
            if getattr(flowable, "_cx_body", False):
                info["body"][self.page] = info["body"].get(self.page, 0) + 1

    buf = io.BytesIO()
    doc = Doc(buf, pagesize=letter, leftMargin=LM, rightMargin=RM, topMargin=BAND_H + 9 * mm, bottomMargin=21 * mm,
              title=f"Contrato {number} v{version}", author="CLONEXA", subject=c["company_name"], invariant=1)
    frame = Frame(LM, doc.bottomMargin, W - LM - RM, H - doc.topMargin - doc.bottomMargin, id="body", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame])])

    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.2, leading=13, textColor=colors.HexColor(INK), alignment=TA_JUSTIFY)
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=10.5, alignment=0)
    label = ParagraphStyle("label", parent=small, fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.HexColor(PINK))
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=15.5, leading=19, alignment=TA_CENTER)
    subtitle = ParagraphStyle("subtitle", parent=base, fontSize=9.5, leading=13, alignment=TA_CENTER, textColor=colors.HexColor(MUTED))
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=7, spaceAfter=3, alignment=0)
    cell = ParagraphStyle("cell", parent=small, fontSize=7.8, leading=10)
    cell_b = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")
    cell_w = ParagraphStyle("cellw", parent=cell_b, textColor=colors.white)
    big = ParagraphStyle("big", parent=base, fontName="Helvetica-Bold", fontSize=12, leading=15, alignment=TA_CENTER)
    tag = ParagraphStyle("tag", parent=cell_b, alignment=TA_CENTER, textColor=colors.HexColor("#b0156a"))
    usable = W - LM - RM
    story = []

    def mark(f):
        f._cx_body = True
        for inner in getattr(f, "_content", None) or []:
            mark(inner)

    def body(f):
        mark(f)
        story.append(f)
        return f

    # ---- titulo
    body(Paragraph(escape(c["title"]), title))
    body(Paragraph(seg_markup(c["subtitle"]), subtitle))
    story.append(Spacer(1, 4 * mm))

    # ---- tarjetas
    def card(head: str, rows: list, logo: Optional[bytes] = None):
        content = [[Paragraph(escape(head), label)]]
        if logo:
            try:
                img = Image(io.BytesIO(logo))
                ratio = img.imageHeight / float(img.imageWidth or 1)
                img.drawWidth, img.drawHeight = (12 * mm / ratio, 12 * mm) if ratio >= 0.4 else (30 * mm, 30 * mm * ratio)
                img.hAlign = "LEFT"
                content.append([img])
            except Exception:
                pass
        for k, v in rows:
            content.append([Paragraph(f"<font color='{MUTED}'>{escape(k)}:</font> {val_markup(v)}" if k else f"<b>{val_markup(v)}</b>", cell)])
        t = Table(content, colWidths=[usable / 2 - 6 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SOFT)), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
                               ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
                               ("LINEBEFORE", (0, 0), (0, -1), 2.2, colors.HexColor(PINK))]))
        return t

    p, cl, v, pay = c["provider"], c["client"], c["vigencia"], c["pago"]
    prov_card = card("PROVEEDOR", [("", f"{p.get('name') or ''} · {p.get('trade_name') or 'CLONEXA'}".strip(" ·")), ("NIT/documento", p.get("doc_id")),
                                   ("Correo", p.get("email")), ("Teléfonos", p.get("phones")), ("Ciudad", p.get("city"))])
    cli_card = card("CLIENTE", [("", c["company_name"]), ("Razón social", cl.get("legal_name")), ("NIT o CC", cl.get("doc_id")),
                                ("Representante", cl.get("representative")), ("Dirección", cl.get("address")), ("Correo", cl.get("email")),
                                ("Teléfono", cl.get("phone"))], client_logo)
    vig_card = card("VIGENCIA", [("Modalidad", v["type"]), ("Inicio del servicio", v["start"]), ("Prueba", v["trial"]),
                                 ("Primer período pagado", v["paid_start"]),
                                 ("Permanencia mínima", f"{v['min_months']} meses (hasta el {v['end']})" if v["min_months"] else "Sin permanencia: mes a mes")])
    pay_rows = [("Moneda", pay["currency"]), ("Ventana de pago", pay["window"]), ("Canal", pay["channel"])]
    if c.get("surcharge"):
        pay_rows.append(("Recargo por ajustes nuevos", f"{c['surcharge']['amount_text']} por mes con ajustes, desde el período {c['surcharge']['from_month']}"))
    pay_card = card("PAGO", pay_rows)
    grid = Table([[prov_card, cli_card], [vig_card, pay_card]], colWidths=[usable / 2, usable / 2])
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm), ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    body(grid)

    # ---- franja de precios
    cells = [[Paragraph(escape(t["label"].upper()), cell_w) for t in c["tiers"]] + [Paragraph("COMPROMISO MÍNIMO", cell_w)],
             [Paragraph(f"{escape(t['amount_text'])}<br/><font size='7' color='{MUTED}'>por mes</font>", big) for t in c["tiers"]]
             + [Paragraph(f"{escape(c['commitment_text'])}<br/><font size='7' color='{MUTED}'>{v['min_months']} meses mínimos</font>" if v["min_months"]
                          else f"Mes a mes<br/><font size='7' color='{MUTED}'>sin permanencia</font>", big)]]
    n = len(cells[0])
    strip = Table(cells, colWidths=[usable / n] * n)
    strip.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BAND)), ("BACKGROUND", (-1, 0), (-1, 0), colors.HexColor(PINK)),
                               ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor(SOFT)), ("BACKGROUND", (-1, 1), (-1, 1), colors.HexColor("#ffe6f2")),
                               ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LINEAFTER", (0, 0), (-2, -1), 1.5, colors.white), ("TOPPADDING", (0, 1), (-1, 1), 6), ("BOTTOMPADDING", (0, 1), (-1, 1), 6)]))
    body(strip)
    story.append(Spacer(1, 2 * mm))
    body(Paragraph(f"<font color='{MUTED}'>Compromiso mínimo en letras:</font> {escape(c['commitment_words'])}." if v["min_months"]
                   else f"<font color='{MUTED}'>Sin permanencia mínima: se paga cada período prestado.</font>", small))
    story.append(Spacer(1, 3 * mm))

    # ---- modulos como etiquetas
    body(Paragraph("MÓDULOS HABILITADOS", label))
    story.append(Spacer(1, 1.5 * mm))
    per_row = 4
    names = [m["name"] for m in c["modules"]]
    rows = [names[i:i + per_row] for i in range(0, len(names), per_row)] or [[]]
    rows = [[Paragraph(escape(x), tag) for x in r] + [""] * (per_row - len(r)) for r in rows]
    tags = Table(rows, colWidths=[usable / per_row] * per_row)
    style = [("LINEBELOW", (0, 0), (-1, -1), 3, colors.white), ("LINEAFTER", (0, 0), (-1, -1), 3, colors.white),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for ri, r in enumerate(rows):
        for ci, x in enumerate(r):
            if x != "":
                style.append(("BACKGROUND", (ci, ri), (ci, ri), colors.HexColor("#fbe3f0")))
    tags.setStyle(TableStyle(style))
    body(tags)
    story.append(Spacer(1, 3 * mm))

    # ---- bloques del sistema
    def schedule():
        head = [Paragraph(x, cell_w) for x in ("No.", "Período", "Ventana de pago", "Tarifa", "Observación")]
        data = [head] + [[Paragraph(str(r["seq"]), cell), Paragraph(escape(r["period"]), cell), Paragraph(escape(r["window"]), cell),
                          Paragraph(escape(r["amount_text"]), cell_b), Paragraph(escape(r["note"]), cell)] for r in c["schedule"]]
        t = Table(data, colWidths=[usable * x for x in (0.07, 0.2, 0.21, 0.2, 0.32)], repeatRows=1)
        st = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BAND)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        st += [("BACKGROUND", (0, i), (-1, i), colors.HexColor(SOFT)) for i in range(2, len(data), 2)]
        t.setStyle(TableStyle(st))
        return t

    def two_col(rows, head_bg=BAND):
        data = [[Paragraph(escape(k.upper()), cell_w), Paragraph(val_markup(v), cell)] for k, v in rows]
        t = Table(data, colWidths=[usable * 0.32, usable * 0.68])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor(head_bg)), ("BACKGROUND", (1, 0), (1, -1), colors.HexColor(SOFT)),
                               ("LINEBELOW", (0, 0), (-1, -1), 1.2, colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return t

    def qr_block():
        out = []
        if qr:
            try:
                img = Image(io.BytesIO(qr))
                ratio = img.imageHeight / float(img.imageWidth or 1)
                side = 52 * mm
                img.drawWidth, img.drawHeight = (side, side * ratio) if ratio <= 1.4 else (side / ratio * 1.4, side * 1.4)
                img.hAlign = "CENTER"
                out.append(Paragraph(f"<font color='{PINK}'><b>QR DE PAGO · CLONEXA</b></font>", ParagraphStyle("qrh", parent=small, alignment=TA_CENTER)))
                out.append(Spacer(1, 2 * mm))
                out.append(img)
            except Exception:
                out.append(Paragraph(f"QR de pago: {BLANK_MARKUP}", small))
        else:
            out.append(Paragraph(f"QR de pago: {BLANK_MARKUP} (EL PROVEEDOR lo entregará por escrito).", small))
        out.append(Spacer(1, 2 * mm))
        out.append(Paragraph(escape(c["qr_caption"]), ParagraphStyle("cap", parent=small, alignment=TA_CENTER, textColor=colors.HexColor(MUTED))))
        out.append(Paragraph("<b>IMPORTANTE:</b> confirme el nombre del destinatario y el valor antes de autorizar la transferencia.",
                             ParagraphStyle("imp", parent=small, alignment=TA_CENTER)))
        return KeepTogether(out)

    def signatures():
        sp, sc = c["signatures"]["provider"], c["signatures"]["client"]
        data = [[Paragraph("EL PROVEEDOR", cell_w), Paragraph("EL CLIENTE", cell_w)],
                [Paragraph("Firma: ______________________________", cell), Paragraph("Firma: ______________________________", cell)]]
        for (k1, v1), (k2, v2) in zip(sp, sc):
            data.append([Paragraph(f"{escape(k1)}: {val_markup(v1)}", cell), Paragraph(f"{escape(k2)}: {val_markup(v2)}", cell)])
        t = Table(data, colWidths=[usable / 2, usable / 2], rowHeights=[None, 16 * mm] + [None] * len(sp))
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), colors.HexColor(BAND)), ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(PINK)),
                               ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor(SOFT)), ("LINEBELOW", (0, 0), (-1, -1), 1.2, colors.white),
                               ("LINEAFTER", (0, 0), (0, -1), 1.2, colors.white), ("VALIGN", (0, 1), (-1, 1), "BOTTOM"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return KeepTogether([t])

    blocks = {"CUOTAS": schedule, "ACCESOS": lambda: two_col(c["access"]), "QR": qr_block, "FIRMAS": signatures,
              "MODULOS": lambda: KeepTogether([Paragraph(f"• <b>{escape(m['name'])}</b>: {escape(m['line'])}", ParagraphStyle(
                  "li", parent=base, leftIndent=8, spaceAfter=1.5)) for m in c["modules"]])}

    # ---- clausulas
    for sec in c["sections"]:
        parts = []
        if sec["title"] != "PARTES":
            if sec["title"].startswith("ANEXO") or sec["title"] == "FIRMAS":
                story.append(CondPageBreak(60 * mm))
            parts.append(Paragraph(escape(sec["title"]), h2))
        for b in sec["blocks"]:
            if b["type"] == "block":
                parts.append(blocks[b["name"]]())
                parts.append(Spacer(1, 2.5 * mm))
            else:
                parts.append(Paragraph(seg_markup(b["segments"]), ParagraphStyle("p", parent=base, spaceAfter=4)))
        if not parts:
            continue
        if len(parts) >= 2:
            body(KeepTogether(parts[:2]))
            for f in parts[2:]:
                body(f)
        else:
            body(parts[0])

    doc.build(story, canvasmaker=Numbered)
    return buf.getvalue(), info
