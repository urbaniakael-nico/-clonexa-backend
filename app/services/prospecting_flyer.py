"""Volante GENERAL por zona y nicho (no personalizado por negocio) para imprimir: PDF media carta (5,5 x 8,5 in).

Mismo estilo que los anuncios de Nexa (app/services/nexa_ad.py): fondo oscuro, degradado de la marca #ff3b4e ->
#ff2d8a, captura REAL del producto (empresas demo, app/assets/nexa_ads/screens) y la linea "Tu negocio, en vivo".
El QR es por ZONA y nicho (utm_source=volante, utm_campaign=<zona>-<nicho>) y abre la pagina de la landing del
nicho (o la principal con #seccion si no tiene). Sin precios. Se arma al pedirlo y no se guarda en la base.
"""
from __future__ import annotations

import io
import os
from typing import Optional

import segno
from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.services import prospecting_niches as pn
from app.services.nexa_ad import ADS, lin_gradient, rounded_mask, wordmark
from app.services.nexa_carousel import font, text_w

DPI = 300
W, H = int(5.5 * DPI), int(8.5 * DPI)          # 1650 x 2550 px
PAGE = (5.5 * 72, 8.5 * 72)                   # puntos PDF
M = 110
BG = (10, 7, 16)
G1, G2 = (255, 59, 78), (255, 45, 138)
WHITE, MUTED = (255, 255, 255), (196, 186, 205)
WA = "+57 314 479 8220"

FLYER: dict[str, dict] = {
    "restaurante": {"tag": "RESTAURANTES Y COMIDAS", "title": ["Tu carta en video,", "con QR en la mesa"], "screen": "rest-qr.webp", "phone": True,
                    "bullets": ["Tus clientes ven cada plato en video y piden desde el celular", "El pedido llega directo a la cocina",
                                "Caja, inventario y cierre del día en un solo lugar"]},
    "bar": {"tag": "BARES", "title": ["Tu bar, sin", "fugas de dinero"], "screen": "bar-barra.webp", "phone": False,
            "bullets": ["Pedidos por QR desde la mesa y cuenta exacta por mesa", "Inventario de licores que se descuenta solo",
                        "Cierre de caja por noche, también de madrugada"]},
    "taller": {"tag": "TALLERES Y FÁBRICAS", "title": ["Producción por lote", "y nómina, claras"], "screen": "taller-produccion.webp", "phone": False,
               "bullets": ["Avance de cada lote y costo real por prenda", "Marcación con PIN en una tableta",
                           "Nómina lista desde las horas reales"]},
    "campo": {"tag": "EMPRESAS DE CAMPO", "title": ["Tu equipo en la calle,", "bajo control"], "screen": "campo-inicio.webp", "phone": False,
              "bullets": ["Turnos con GPS desde el celular o un bot", "Cortes por WhatsApp y órdenes de materiales",
                          "Horas listas para la nómina"]},
    "tienda": {"tag": "TIENDAS Y MINIMERCADOS", "title": ["Ventas e inventario", "que sí cuadran"], "screen": "ej-ventas.webp", "phone": False,
               "bullets": ["Ventas del día desde el celular", "Inventario que se descuenta con cada venta",
                           "Turnos del equipo y reportes"]},
}


def flyer_kind(niche: str) -> str:
    return pn.NICHES.get(niche, {}).get("flyer", "restaurante")


def _qr(url: str, size: int) -> Image.Image:
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=10, border=2, dark="#0a0710", light="#ffffff")
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB").resize((size, size), Image.NEAREST)


def _gradient_text(base: Image.Image, xy: tuple[int, int], s: str, f) -> None:
    w = int(text_w(s, f)) + 4
    bbox = f.getbbox(s)
    h = bbox[3] + 8
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((0, 0), s, font=f, fill=255)
    base.paste(lin_gradient((w, h), G1, G2), xy, mask)


def _wrap(s: str, f, width: int) -> list[str]:
    words, lines, cur = s.split(), [], ""
    for wd in words:
        t = f"{cur} {wd}".strip()
        if text_w(t, f) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    return lines + ([cur] if cur else [])


def render_png(zone_name: str, niche: str, url: str) -> tuple[Image.Image, dict]:
    kind = flyer_kind(niche)
    spec = FLYER[kind]
    im = Image.new("RGB", (W, H), BG)
    # brillo del degradado arriba a la derecha y abajo a la izquierda
    glow = Image.new("RGB", (W, H), BG)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W - 900, -500, W + 500, 700), fill=(120, 18, 60))
    gd.ellipse((-600, H - 900, 700, H + 400), fill=(90, 14, 70))
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(260)), 0.9)
    d = ImageDraw.Draw(im)
    layout: dict = {}
    # logotipo
    wm = wordmark()
    wm = wm.resize((int(wm.width * 2.4), int(wm.height * 2.4)), Image.LANCZOS)
    im.paste(wm, (M, M), wm)
    y = M + wm.height + 60
    # etiqueta del nicho
    ft = font("bold", 34)
    tag = spec["tag"]
    tw = int(text_w(tag, ft)) + 56
    pill = lin_gradient((tw, 64), G1, G2)
    im.paste(pill, (M, y), rounded_mask((tw, 64), 32))
    d.text((M + 28, y + 12), tag, font=ft, fill=WHITE)
    layout["tag"] = tag
    y += 110
    # titular (2 lineas) y "Tu negocio, en vivo"
    fh = font("black", 104)
    for line in spec["title"]:
        d.text((M, y), line, font=fh, fill=WHITE)
        y += 122
    _gradient_text(im, (M, y + 6), "Tu negocio, en vivo", font("extrabold", 92))
    layout["live_line"] = "Tu negocio, en vivo"
    y += 150
    # captura real del producto
    shot = Image.open(os.path.join(ADS, "screens", spec["screen"])).convert("RGB")
    fb = font("semibold", 44)
    bullets_h = sum(len(_wrap(b, fb, W - 2 * M - 70)) * 58 + 18 for b in spec["bullets"])
    qs = 420
    qy = H - M - qs - 40
    max_h = qy - 70 - bullets_h - 70 - y       # la captura llena lo que queda sin pisar funciones ni QR
    ph_w = W - 2 * M
    ph_h = int(shot.height * ph_w / shot.width)
    if ph_h > max_h:
        ph_h = max_h
        ph_w = int(shot.width * ph_h / shot.height)
    shot = shot.resize((ph_w, ph_h), Image.LANCZOS)
    x0 = (W - ph_w) // 2
    frame = Image.new("RGB", (ph_w + 16, ph_h + 16), (40, 30, 48))
    im.paste(frame, (x0 - 8, y - 8), rounded_mask(frame.size, 40))
    im.paste(shot, (x0, y), rounded_mask(shot.size, 34))
    layout["screen"] = spec["screen"]
    y += ph_h + 70
    # funciones
    for b in spec["bullets"]:
        lines = _wrap(b, fb, W - 2 * M - 70)
        d.ellipse((M, y + 14, M + 26, y + 40), fill=G2)
        for ln in lines:
            d.text((M + 54, y), ln, font=fb, fill=WHITE)
            y += 58
        y += 18
    layout["bottom_of_content"] = y
    layout["qr_top"] = qy - 20
    # QR por zona y nicho + llamado
    qr = _qr(url, qs)
    card = Image.new("RGB", (qs + 40, qs + 40), WHITE)
    im.paste(card, (W - M - qs - 40, qy - 20), rounded_mask(card.size, 28))
    im.paste(qr, (W - M - qs - 20, qy))
    fc = font("extrabold", 58)
    d.text((M, qy + 10), "Escanea y míralo", font=fc, fill=WHITE)
    d.text((M, qy + 80), "funcionando", font=fc, fill=WHITE)
    fs = font("regular", 36)
    d.text((M, qy + 180), f"Demo gratis · {zone_name}", font=fs, fill=MUTED)
    d.text((M, qy + 232), f"WhatsApp {WA}", font=fs, fill=MUTED)
    d.text((M, qy + 284), "clonexa.com.co", font=font("bold", 36), fill=WHITE)
    layout.update(qr_url=url, qr_box=(W - M - qs - 20, qy, W - M - 20, qy + qs), kind=kind)
    return im, layout


def render_pdf(zone_slug: str, zone_name: str, niche: str, landing: str, *, url: Optional[str] = None) -> tuple[bytes, dict]:
    url = url or pn.flyer_url(landing, zone_slug, niche)
    im, layout = render_png(zone_name, niche, url)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE, pageCompression=1)
    c.setTitle(f"Volante Clonexa · {zone_name} · {pn.NICHES.get(niche, {}).get('label', niche)}")
    c.setAuthor("Clonexa")
    jpg = io.BytesIO()
    im.save(jpg, "JPEG", quality=88, optimize=True)
    c.drawImage(ImageReader(io.BytesIO(jpg.getvalue())), 0, 0, width=PAGE[0], height=PAGE[1])
    c.linkURL(url, (PAGE[0] * layout["qr_box"][0] / W, PAGE[1] * (1 - layout["qr_box"][3] / H),
                    PAGE[0] * layout["qr_box"][2] / W, PAGE[1] * (1 - layout["qr_box"][1] / H)))
    c.showPage()
    c.save()
    return buf.getvalue(), {**layout, "png": im}
