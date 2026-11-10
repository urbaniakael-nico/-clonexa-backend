"""Anuncio visual de Nexa (plan B de contenido): una sola imagen 1080x1350 con Pillow, sin navegador.

Misma composicion que nexa-escenas/_estudio/anuncio.py (que usaba Playwright): foto de fondo oscurecida,
logotipo y etiqueta del rubro, titular grande (maximo 8 palabras, parte final en degradado
#ff3b4e -> #ff2d8a), subtitulo, portatil y celular con pantallas REALES de Clonexa, 2 tarjetas
flotantes, 4-5 funciones con emoji y botones "Pide tu demo gratis" + WhatsApp.

Solo pantallas de empresas demo: las capturas viven en app/assets/nexa_ads/screens y se eligen por
ESCENA de un catalogo cerrado (SCENES). La peticion no puede traer imagenes propias ni rutas; las
tarjetas flotantes salen de la escena (datos que se ven en esas mismas pantallas demo), no del modelo.
Emoji: set curado de Twemoji (CC-BY 4.0) en app/assets/nexa_ads/emoji; uno desconocido se cambia por ✅.

render(spec) -> (png, layout); layout dice donde quedo cada bloque para las pruebas.
"""
from __future__ import annotations

import io
import os
from functools import lru_cache
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from app.services.nexa_carousel import Run, _tokens, draw_tracked, font, text_w, wrap_tokens

W, H = 1080, 1350
M = 60
BG = (10, 7, 16)
G1, G2 = (255, 59, 78), (255, 45, 138)
BTN1, BTN2 = (255, 59, 78), (242, 11, 109)
MAX_TITLE_WORDS = 8

_HERE = os.path.dirname(os.path.dirname(__file__))
ADS = os.path.join(_HERE, "assets", "nexa_ads")

# escena -> capturas (solo empresas demo), fondo y 2 tarjetas con datos visibles en esas pantallas
SCENES: dict[str, dict[str, Any]] = {
    "restaurante-cocina": {
        "rubro": "Restaurantes: pedido de la mesa/QR a la cocina, domicilios, caja", "tag": "RESTAURANTES Y BARES",
        "laptop": "rest-cocina.webp", "phone": "rest-mesero.webp", "bg": "restaurante.jpg",
        "cards": [("PEDIDO NUEVO", "Mesa 7 · 2 min", "p"), ("CIERRE DE CAJA", "$ 1.162.000", "g")],
    },
    "restaurante-caja": {
        "rubro": "Restaurantes: cierre de caja, pedidos por QR desde la mesa, ventas del día", "tag": "RESTAURANTES",
        "laptop": "rest-cierre.webp", "phone": "rest-qr.webp", "bg": "restaurante.jpg",
        "cards": [("PEDIDO POR QR", "Mesa 7 · $ 65.000", "p"), ("VENTAS DEL DÍA", "$ 1.162.000", "g")],
    },
    "bar": {
        "rubro": "Bares y discotecas: barra, mesas, pedidos por QR, cuentas por mesa", "tag": "BARES Y DISCOTECAS",
        "laptop": "bar-barra.webp", "phone": "rest-qr.webp", "bg": "restaurante.jpg",
        "cards": [("PEDIDO QR", "Mesa 4 · $ 84.000", "p"), ("CUENTA MESA 7", "$ 81.000", "g")],
    },
    "campo": {
        "rubro": "Equipos en campo: turnos con GPS, colaboradores en vivo, nómina por horas", "tag": "EQUIPOS EN CAMPO",
        "laptop": "campo-inicio.webp", "phone": None, "bg": "campo.jpg",
        "cards": [("OPERACIÓN EN VIVO", "5 activos · GPS ON", "g"), ("EN PAUSA", "1 colaborador", "p")],
    },
    "campo-materiales": {
        "rubro": "Obras y campo: órdenes de materiales, inventario, entregas por obra", "tag": "OBRAS Y MATERIALES",
        "laptop": "campo-materiales.webp", "phone": None, "bg": "campo.jpg",
        "cards": [("ÓRDENES DE MATERIAL", "1 por aprobar", "p"), ("ENTREGADAS", "2 órdenes", "g")],
    },
    "callcenter": {
        "rubro": "Transporte y call center: llamadas, agentes, cotizaciones, tickets", "tag": "TRANSPORTE Y CALL CENTER",
        "laptop": "ej-callcenter.webp", "phone": None, "bg": None,
        "cards": [("LLAMADAS DEL PERIODO", "38", "g"), ("DURACIÓN PROMEDIO", "4m 11s", "p")],
    },
}

EMOJI = {  # caracter -> archivo Twemoji (sin FE0F)
    "🎬": "1f3ac", "📲": "1f4f2", "👨‍🍳": "1f468-200d-1f373", "🛵": "1f6f5", "💵": "1f4b5", "📍": "1f4cd", "🤖": "1f916",
    "📦": "1f4e6", "🗺": "1f5fa", "⏱": "23f1", "📊": "1f4ca", "🧾": "1f9fe", "🍹": "1f379", "🎵": "1f3b5", "📞": "1f4de",
    "📋": "1f4cb", "✅": "2705", "⚡": "26a1", "💬": "1f4ac", "🍽": "1f37d", "🛒": "1f6d2", "📈": "1f4c8", "🔔": "1f514",
    "🧵": "1f9f5", "👕": "1f455", "🏭": "1f3ed", "🕒": "1f552", "📅": "1f4c5", "💳": "1f4b3", "🎮": "1f3ae", "🏆": "1f3c6",
    "🎯": "1f3af", "🚚": "1f69a", "🔒": "1f512", "☁": "2601", "📱": "1f4f1", "💻": "1f4bb", "🧮": "1f9ee", "🍺": "1f37a",
    "🥤": "1f964", "🎧": "1f3a7", "👥": "1f465", "💰": "1f4b0", "🚛": "1f69b", "👷": "1f477", "📝": "1f4dd", "🏪": "1f3ea",
    "🍕": "1f355", "🍔": "1f354", "🍗": "1f357",
}


def norm_emoji(e: str) -> str:
    e = (e or "").replace("️", "").strip()
    return e if e in EMOJI else "✅"


@lru_cache(maxsize=128)
def emoji_img(e: str, size: int) -> Image.Image:
    im = Image.open(os.path.join(ADS, "emoji", EMOJI[norm_emoji(e)] + ".png")).convert("RGBA")
    return im.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=16)
def asset(kind: str, name: str) -> Image.Image:
    return Image.open(os.path.join(ADS, kind, name)).convert("RGB")


@lru_cache(maxsize=1)
def wordmark() -> Image.Image:
    im = Image.open(os.path.join(ADS, "wordmark.png")).convert("RGBA")
    h = 44
    return im.resize((int(im.width * h / im.height), h), Image.LANCZOS)


# ------------------------------------------------------------------ utilidades de dibujo
def lin_gradient(size: tuple[int, int], c1, c2) -> Image.Image:
    w, h = max(1, size[0]), max(1, size[1])
    line = Image.new("L", (256, 1))
    line.putdata(list(range(256)))
    return Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), line.resize((w, h), Image.BILINEAR))


def rounded_mask(size: tuple[int, int], radius) -> Image.Image:
    """radius int, o (arriba, abajo) para esquinas distintas arriba y abajo."""
    top, bottom = (radius, radius) if isinstance(radius, int) else radius
    w, h = size

    def one(r: int) -> Image.Image:
        m = Image.new("L", size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255) if r else m.paste(255, (0, 0, w, h))
        return m

    if top == bottom:
        return one(top)
    out = one(bottom)
    out.paste(one(top).crop((0, 0, w, h // 2)), (0, 0))
    return out


def shadow(base: Image.Image, box: tuple[int, int, int, int], radius: int, blur: int, alpha: int, dy: int) -> None:
    x0, y0, x1, y1 = box
    pad = blur * 3
    sh = Image.new("L", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), 0)
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad, pad + x1 - x0, pad + y1 - y0), radius=radius, fill=alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    base.paste(Image.new("RGB", sh.size, (0, 0, 0)), (x0 - pad, y0 - pad + dy), sh)


def cover(img: Image.Image, size: tuple[int, int], top_left: bool = True) -> Image.Image:
    return ImageOps.fit(img, size, Image.LANCZOS, centering=(0, 0) if top_left else (0.5, 0))


def blend_rect(base: Image.Image, box, fill_rgba, radius: int, outline=None, width: int = 1) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=fill_rgba, outline=outline, width=width)
    base.alpha_composite(layer)


def background(scene: dict) -> Image.Image:
    if scene.get("bg"):
        im = asset("bg", scene["bg"]).copy()
    else:
        im = Image.new("RGB", (W, H), (22, 12, 26))
    im = im.convert("RGBA")
    # degradado vertical (como el .ov del estudio): .92 -> .45 -> .45 -> .96 -> .96
    stops = [(0.0, 0.92), (0.34, 0.45), (0.58, 0.45), (0.82, 0.96), (1.0, 0.96)]
    col = Image.new("L", (1, H))
    vals = []
    for y in range(H):
        t = y / (H - 1)
        for (a, va), (b, vb) in zip(stops, stops[1:]):
            if a <= t <= b:
                vals.append(int(255 * (va + (vb - va) * (t - a) / (b - a))))
                break
    col.putdata(vals)
    im.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", (W, H), BG).split(), col.resize((W, H)))))
    # brillo rosado arriba a la derecha
    g = Image.radial_gradient("L").resize((1400, 1000), Image.BILINEAR)
    a = g.point(lambda v: int(((max(0, 128 - v) / 128) ** 1.3) * 255 * 0.35))
    glow = Image.new("RGBA", (1400, 1000), (242, 11, 109, 0))
    glow.putalpha(a)
    im.alpha_composite(_crop_glow(glow))
    return im


def _crop_glow(glow: Image.Image) -> Image.Image:
    """El brillo (1400x1000) centrado en (864, 135), recortado al lienzo."""
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(glow, (864 - 700, 135 - 500), glow)
    return out


# ------------------------------------------------------------------ bloques
def title_lines(titulo: str, resaltado: str, remate: str, f, width: float, tr: float) -> list:
    """Como el estudio: si el titulo cabe en una linea, la parte resaltada (+ remate) empieza la segunda."""
    first = wrap_tokens(_tokens([Run(titulo)]), f, width, tr) if titulo.strip() else []
    rest = wrap_tokens(_tokens([Run(resaltado, True), Run(remate)]), f, width, tr) if (resaltado + remate).strip() else []
    if len(first) == 1 and len(rest) <= 1:
        return first + rest
    return wrap_tokens(_tokens([Run(titulo), Run(resaltado, True), Run(remate)]), f, width, tr)


def title_block(c: "Ad", titulo: str, resaltado: str, remate: str = "") -> int:
    width = W - 2 * M
    lines = None
    for size in range(84, 63, -2):  # 1) corte antes del resaltado, como el estudio
        f = font("black", size)
        tr = -size * 0.024
        first = wrap_tokens(_tokens([Run(titulo)]), f, width, tr) if titulo.strip() else []
        rest = wrap_tokens(_tokens([Run(resaltado, True), Run(remate)]), f, width, tr) if (resaltado + remate).strip() else []
        if len(first) == 1 and len(rest) == 1:
            lines = first + rest
            break
    if lines is None:  # 2) ajuste normal en 2 lineas
        for size in range(84, 51, -4):
            f = font("black", size)
            tr = -size * 0.024
            lines = title_lines(titulo, resaltado, remate, f, width, tr)
            if len(lines) <= 2:
                break
    lh = int(size * 1.0)
    y0 = 140
    asc = f.getmetrics()[0]
    top_pad = int(round(asc - size * 0.76))
    space = f.getlength(" ")
    txt = Image.new("L", (W, H), 0)
    hl = Image.new("L", (W, H), 0)
    dt, dh = ImageDraw.Draw(txt), ImageDraw.Draw(hl)
    maxw = 0.0
    for i, line in enumerate(lines):
        x = float(M)
        for j, (word, is_hl) in enumerate(line):
            draw_tracked(dh if is_hl else dt, x, y0 + i * lh - top_pad, word, f, 255, tr)
            x += text_w(word, f, tr) + (space if j < len(line) - 1 else 0)
        maxw = max(maxw, x - M)
    both = Image.composite(Image.new("L", (W, H), 255), txt, hl)
    sh = both.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.6))
    c.im.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 6), sh)
    c.im.paste(Image.new("RGBA", (W, H), (255, 255, 255, 255)), (0, 0), txt)
    c.im.paste(lin_gradient((W, H), G1, G2).convert("RGBA"), (0, 0), hl)
    bottom = y0 + lh * len(lines)
    c.add("title", (M, y0, M + maxw, bottom), lines=len(lines), size=size)
    return bottom


def wrap_plain(s: str, f, width: float) -> list[str]:
    return [" ".join(w for w, _ in ln) for ln in wrap_tokens(_tokens([Run(s)]), f, width)]


class Ad:
    def __init__(self, scene: dict) -> None:
        self.im = background(scene)
        self.d = ImageDraw.Draw(self.im)
        self.layout: list[dict] = []

    def add(self, kind: str, box, **extra) -> None:
        self.layout.append({"kind": kind, "box": tuple(int(round(v)) for v in box), **extra})


def top_row(c: Ad, tag: str) -> None:
    wm = wordmark()
    c.im.alpha_composite(wm, (M, 58))
    c.add("logo", (M, 58, M + wm.width, 58 + wm.height))
    f = font("extrabold", 24)
    tr = 2.0
    tw = text_w(tag, f, tr)
    w, h = int(tw + 44), 54
    x1 = W - M
    x0 = x1 - w
    y0 = 80 - h // 2
    blend_rect(c.im, (x0, y0, x1, y0 + h), (242, 11, 109, 51), 30, outline=(255, 90, 140, 180), width=2)
    draw_tracked(c.d, x0 + 22, y0 + 13, tag, f, (255, 143, 179), tr)
    c.add("tag", (x0, y0, x1, y0 + h))


def laptop(c: Ad, shot: Image.Image, wide: bool) -> tuple[int, int, int, int]:
    left, width, top = (110, 860, 460) if wide else (60, 760, 460)
    pad, img_h = 16, 430
    sx0, sy0, sx1, sy1 = left, top, left + width, top + pad * 2 + img_h
    base_y1 = sy1 + 26
    shadow(c.im, (sx0, sy0, sx1, base_y1), 22, 30, 180, 30)
    frame = Image.new("RGBA", (width, sy1 - sy0), (17, 17, 17, 255))
    fm = rounded_mask(frame.size, (22, 0))
    c.im.paste(frame, (sx0, sy0), fm)
    ImageDraw.Draw(c.im).rounded_rectangle((sx0, sy0, sx1 - 1, sy1 + 6), radius=22, outline=(58, 58, 68), width=2)
    c.im.paste((17, 17, 17, 255), (sx0 + 2, sy1 - 2, sx1 - 2, sy1 + 8))
    screen = cover(shot, (width - 2 * pad, img_h)).convert("RGBA")
    c.im.paste(screen, (sx0 + pad, sy0 + pad), rounded_mask(screen.size, 8))
    base = Image.new("RGB", (width + 80, 26))
    base = Image.composite(Image.new("RGB", base.size, (141, 143, 152)), Image.new("RGB", base.size, (207, 208, 214)),
                           Image.linear_gradient("L").resize(base.size))
    c.im.paste(base.convert("RGBA"), (sx0 - 40, sy1), rounded_mask(base.size, (0, 30)))
    c.add("laptop", (sx0 - 40, sy0, sx1 + 40, base_y1))
    return (sx0, sy0, sx1, base_y1)


def phone(c: Ad, shot: Image.Image) -> tuple[int, int, int, int]:
    w, h = 270, 560
    x1 = W - 62
    x0, y0 = x1 - w, 500
    shadow(c.im, (x0, y0, x1, y0 + h), 44, 30, 200, 30)
    body = Image.new("RGBA", (w, h), (11, 11, 15, 255))
    c.im.paste(body, (x0, y0), rounded_mask((w, h), 44))
    ImageDraw.Draw(c.im).rounded_rectangle((x0, y0, x1 - 1, y0 + h - 1), radius=44, outline=(64, 64, 74), width=3)
    inner = cover(shot, (w - 30, h - 30)).convert("RGBA")
    c.im.paste(inner, (x0 + 15, y0 + 15), rounded_mask(inner.size, 34))
    c.add("phone", (x0, y0, x1, y0 + h))
    return (x0, y0, x1, y0 + h)


def card(c: Ad, x: int, y: int, k: str, v: str, cls: str) -> tuple[int, int, int, int]:
    fk, fv = font("extrabold", 17), font("black", 30)
    kw, vw = text_w(k, fk, 2.0), fv.getlength(v)
    w, h = int(max(kw, vw) + 44), 18 + 17 + 8 + 34 + 18
    x = min(x, W - 20 - w)
    shadow(c.im, (x, y, x + w, y + h), 22, 22, 130, 18)
    ImageDraw.Draw(c.im).rounded_rectangle((x, y, x + w, y + h), radius=22, fill=(255, 255, 255))
    draw_tracked(c.d, x + 22, y + 16, k, fk, (138, 123, 134), 2.0)
    color = (20, 160, 91) if cls == "g" else (229, 23, 79)
    asc = fv.getmetrics()[0]
    c.d.text((x + 22, y + 18 + 17 + 8 - (asc - int(30 * 0.76))), v, font=fv, fill=color)
    c.add("card", (x, y, x + w, y + h))
    return (x, y, x + w, y + h)


def chips(c: Ad, items: list[tuple[str, str]], top: int, bottom_limit: int) -> int:
    for size in (25, 23, 21, 19):
        f = font("bold", size)
        e = int(size * 1.15)
        ph, pv, gap = 20, 12, 12
        h = pv * 2 + max(e, int(size * 1.2))
        rows, x, y, placed = 1, M, top, []
        for emo, txt in items:
            w = ph * 2 + e + 10 + int(f.getlength(txt))
            if x + w > W - M and x > M:
                rows += 1
                x, y = M, y + h + gap
            placed.append((x, y, w, emo, txt))
            x += w + gap
        if y + h <= bottom_limit:
            break
    for x, y, w, emo, txt in placed:
        blend_rect(c.im, (x, y, x + w, y + h), (255, 255, 255, 26), 16, outline=(255, 255, 255, 56), width=1)
        ei = emoji_img(emo, e)
        c.im.alpha_composite(ei, (x + ph, y + (h - e) // 2))
        asc = f.getmetrics()[0]
        c.d.text((x + ph + e + 10, y + (h - size * 0.76) / 2 - (asc - size * 0.76)), txt, font=f, fill=(255, 255, 255))
        c.add("chip", (x, y, x + w, y + h))
    return y + h


def cta(c: Ad, label: str) -> None:
    y1 = H - 52
    h = 96
    y0 = y1 - h
    fw = font("extrabold", 30)
    e = 34
    wa_w = int(30 * 2 + e + 10 + fw.getlength("WhatsApp"))
    wx1 = W - M
    wx0 = wx1 - wa_w
    bx0, bx1 = M, wx0 - 16
    # boton principal con brillo
    glow = Image.new("L", (bx1 - bx0 + 120, h + 120), 0)
    ImageDraw.Draw(glow).rounded_rectangle((60, 72, 60 + bx1 - bx0, 72 + h), radius=24, fill=115)
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    c.im.paste(Image.new("RGBA", glow.size, (242, 11, 109, 255)), (bx0 - 60, y0 - 60), glow)
    grad = lin_gradient((bx1 - bx0, h), BTN1, BTN2).convert("RGBA")
    c.im.paste(grad, (bx0, y0), rounded_mask(grad.size, 24))
    fb = None
    for size in (36, 34, 32, 30, 28):
        fb = font("black", size)
        if fb.getlength(label) <= bx1 - bx0 - 40:
            break
    asc = fb.getmetrics()[0]
    tw = fb.getlength(label)
    c.d.text((bx0 + (bx1 - bx0 - tw) / 2, y0 + (h - fb.size * 0.76) / 2 - (asc - fb.size * 0.76)), label, font=fb, fill=(255, 255, 255))
    c.add("cta", (bx0, y0, bx1, y1))
    ImageDraw.Draw(c.im).rounded_rectangle((wx0, y0, wx1, y1), radius=24, fill=(24, 169, 87))
    c.im.alpha_composite(emoji_img("💬", e), (wx0 + 30, y0 + (h - e) // 2))
    asc = fw.getmetrics()[0]
    c.d.text((wx0 + 30 + e + 10, y0 + (h - 30 * 0.76) / 2 - (asc - 30 * 0.76)), "WhatsApp", font=fw, fill=(255, 255, 255))
    c.add("whatsapp", (wx0, y0, wx1, y1))


def title_words(titulo: str, resaltado: str, remate: str = "") -> int:
    return len(" ".join((titulo, resaltado, remate)).split())


def render(spec: dict) -> tuple[bytes, list[dict]]:
    """spec = {escena, tag?, titulo, resaltado, remate?, subtitulo, funciones: [{emoji, texto}] (4-5), cta?}."""
    scene = SCENES[spec["escena"]]
    c = Ad(scene)
    top_row(c, (spec.get("tag") or scene["tag"]).upper()[:28])
    tb = title_block(c, spec.get("titulo", ""), spec.get("resaltado", ""), spec.get("remate", ""))
    fs = font("semibold", 32)
    sub_w = W - M - 300
    sub_lines = wrap_plain(spec.get("subtitulo", ""), fs, sub_w)[:2]
    sy = max(340, tb + 26)
    for i, ln in enumerate(sub_lines):
        c.d.text((M, sy + i * 42 - (fs.getmetrics()[0] - int(32 * 0.76))), ln, font=fs, fill=(241, 228, 236))
    if sub_lines and sub_lines[0]:
        c.add("subtitle", (M, sy, M + max(fs.getlength(l) for l in sub_lines), sy + 42 * len(sub_lines)))
    has_phone = bool(scene.get("phone"))
    laptop(c, asset("screens", scene["laptop"]), wide=not has_phone)
    if has_phone:
        phone(c, asset("screens", scene["phone"]))
    (k1, v1, c1), (k2, v2, c2) = scene["cards"]
    if has_phone:
        card(c, 520, 420, k1, v1, c1)
        card(c, 40, 930, k2, v2, c2)
    else:
        card(c, 600, 415, k1, v1, c1)
        card(c, 40, 935, k2, v2, c2)
    items = [(norm_emoji(x.get("emoji", "")), str(x.get("texto", "")).strip()[:28]) for x in spec.get("funciones", [])][:5]
    chips(c, items, 1062, H - 52 - 96 - 14)
    cta(c, (spec.get("cta") or "Pide tu demo gratis")[:30])
    buf = io.BytesIO()
    c.im.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue(), c.layout
