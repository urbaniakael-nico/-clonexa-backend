"""Laminas de carrusel de Nexa (plan B de contenido) con la plantilla de marca de Clonexa.

Solo Pillow y las fuentes Inter del repo (app/assets/fonts, licencia OFL); sin navegador. Cada lamina
mide 1080x1350 (4:5, lo que pide Instagram para carrusel): fondo oscuro con brillos, logotipo arriba a
la izquierda, contador "n/N" arriba a la derecha, puntos de avance y "Desliza ->" abajo.

Estructura (6 o 7 laminas): portada (categoria, titulo con parte resaltada en degradado #ff3b4e ->
#f20b6d, subtitulo) + 4 o 5 puntos (numero grande, titulo, cuadros HOY / CON CLONEXA) + cierre (icono,
titulo resaltado, texto y boton "Comenta DEMO y te escribo").

render(spec) devuelve [(png_bytes, layout)]: layout dice donde quedo cada bloque para poder probar que
nada se sale de la lamina ni se monta sobre otro bloque. Los textos largos bajan de tamano hasta caber.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
M = 72  # margen lateral
TOP_SAFE = 150  # debajo del logotipo
BOTTOM_SAFE = 1225  # encima de los puntos
CENTER_Y = 680
G1 = (255, 59, 78)  # #ff3b4e
G2 = (242, 11, 109)  # #f20b6d
BG = (11, 9, 16)
WHITE = (246, 243, 248)
SOFT = (214, 210, 221)
GRAY = (160, 155, 168)
DOT = (66, 62, 74)
PINK_TXT = (255, 84, 140)
CTA = "Comenta DEMO y te escribo"
HANDLE = "@clonexaapp"

_HERE = os.path.dirname(os.path.dirname(__file__))
FONT_DIR = os.path.join(_HERE, "assets", "fonts")
BRAND_DIR = os.path.join(_HERE, "assets", "brand")
_WEIGHTS = {"regular": "Inter-Regular.ttf", "semibold": "Inter-SemiBold.ttf", "bold": "Inter-Bold.ttf", "extrabold": "Inter-ExtraBold.ttf", "black": "Inter-Black.ttf"}


@lru_cache(maxsize=64)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, _WEIGHTS[weight]), size)


# ------------------------------------------------------------------ texto con tracking y resaltado
def text_w(s: str, f, tracking: float = 0.0) -> float:
    return f.getlength(s) + max(0, len(s) - 1) * tracking


def draw_tracked(d: ImageDraw.ImageDraw, x: float, y: float, s: str, f, fill, tracking: float = 0.0) -> None:
    if not tracking:
        d.text((x, y), s, font=f, fill=fill)
        return
    for i, ch in enumerate(s):
        d.text((x + f.getlength(s[:i]) + i * tracking, y), ch, font=f, fill=fill)


@dataclass
class Run:
    text: str
    hl: bool = False


def _tokens(runs: list[Run]) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for r in runs:
        out += [(w, r.hl) for w in r.text.split() if w]
    return out


def wrap_tokens(tokens: list[tuple[str, bool]], f, width: float, tracking: float = 0.0) -> list[list[tuple[str, bool]]]:
    """Lineas de palabras; una palabra mas ancha que la linea se parte por letras (nunca se corta)."""
    lines: list[list[tuple[str, bool]]] = []
    cur: list[tuple[str, bool]] = []
    space = f.getlength(" ")

    def width_of(ws: list[tuple[str, bool]]) -> float:
        return sum(text_w(w, f, tracking) for w, _ in ws) + space * max(0, len(ws) - 1)

    for word, hl in tokens:
        while text_w(word, f, tracking) > width:
            cut = len(word)
            while cut > 1 and text_w(word[:cut], f, tracking) > width:
                cut -= 1
            if cur:
                lines.append(cur)
                cur = []
            lines.append([(word[:cut], hl)])
            word = word[cut:]
        if cur and width_of(cur + [(word, hl)]) > width:
            lines.append(cur)
            cur = []
        cur.append((word, hl))
    if cur:
        lines.append(cur)
    return lines or [[("", False)]]


@dataclass
class TextBlock:
    lines: list[list[tuple[str, bool]]]
    f: Any
    line_h: int
    tracking: float
    color: tuple
    width: float

    @property
    def height(self) -> int:
        return self.line_h * len(self.lines)


def make_block(runs: list[Run], weight: str, size: int, width: float, line_k: float, tracking_em: float, color) -> TextBlock:
    f = font(weight, size)
    tr = size * tracking_em
    return TextBlock(wrap_tokens(_tokens(runs), f, width, tr), f, int(round(size * line_k)), tr, color, width)


def fit_block(runs: list[Run], weight: str, sizes: range | list[int], width: float, line_k: float, tracking_em: float, color, max_lines: int) -> TextBlock:
    """El tamano mas grande (de la lista) que cabe en max_lines lineas; si ninguno, el mas pequeno."""
    sizes = list(sizes)
    b = None
    for s in sizes:
        b = make_block(runs, weight, s, width, line_k, tracking_em, color)
        if len(b.lines) <= max_lines:
            return b
    return b  # type: ignore[return-value]


class Canvas:
    def __init__(self) -> None:
        self.im = background().copy()
        self.d = ImageDraw.Draw(self.im)
        self.hl_mask = Image.new("L", (W, H), 0)  # lo que se pinta con el degradado
        self.hd = ImageDraw.Draw(self.hl_mask)
        self.layout: list[dict] = []

    def add(self, kind: str, box: tuple[float, float, float, float], **extra) -> None:
        self.layout.append({"kind": kind, "box": tuple(int(round(v)) for v in box), **extra})

    def text_block(self, b: TextBlock, x: float, y: float, kind: str) -> float:
        space = b.f.getlength(" ")
        asc = b.f.getmetrics()[0]
        # Inter deja aire arriba: se sube el texto para que la caja visual empiece en y
        top_pad = int(round(asc - b.f.size * 0.76))
        maxw = 0.0
        for i, line in enumerate(b.lines):
            cx = x
            ly = y + i * b.line_h - top_pad
            for j, (word, hl) in enumerate(line):
                if hl:
                    draw_tracked(self.hd, cx, ly, word, b.f, 255, b.tracking)
                else:
                    draw_tracked(self.d, cx, ly, word, b.f, b.color, b.tracking)
                cx += text_w(word, b.f, b.tracking) + (space if j < len(line) - 1 else 0)
            maxw = max(maxw, cx - x)
        self.add(kind, (x, y, x + maxw, y + b.height), lines=len(b.lines), size=b.f.size)
        return y + b.height

    def finish(self) -> bytes:
        grad = gradient((W, H), G1, G2)
        self.im.paste(grad, (0, 0), self.hl_mask)
        buf = io.BytesIO()
        self.im.convert("RGB").save(buf, format="PNG", optimize=True)
        return buf.getvalue()


# ------------------------------------------------------------------ fondo, degradados, marca
def gradient(size: tuple[int, int], c1, c2) -> Image.Image:
    """Degradado horizontal de c1 (izquierda) a c2 (derecha)."""
    w, h = max(1, size[0]), max(1, size[1])
    line = Image.new("L", (256, 1))
    line.putdata(list(range(256)))
    mask = line.resize((w, h), Image.BILINEAR)
    return Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), mask)


def _glow(base: Image.Image, center: tuple[int, int], radius: int, color, strength: float) -> None:
    # radial_gradient: 0 en el centro y 128 en el borde del circulo inscrito; fuera del circulo, nada
    g = Image.radial_gradient("L").resize((radius * 2, radius * 2), Image.BILINEAR)
    alpha = g.point(lambda v: int(((max(0, 128 - v) / 128) ** 1.25) * 255 * strength))
    layer = Image.new("RGB", (radius * 2, radius * 2), color)
    base.paste(layer, (center[0] - radius, center[1] - radius), alpha)


@lru_cache(maxsize=1)
def background() -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    _glow(im, (W + 40, -60), 900, (92, 8, 48), 0.95)
    _glow(im, (-100, H + 100), 700, (78, 18, 28), 0.85)
    return im


@lru_cache(maxsize=1)
def wordmark() -> Image.Image:
    im = Image.open(os.path.join(BRAND_DIR, "nexa-wordmark.png")).convert("RGBA")
    h = 33
    return im.resize((int(im.width * h / im.height), h), Image.LANCZOS)


@lru_cache(maxsize=1)
def icon() -> Image.Image:
    im = Image.open(os.path.join(BRAND_DIR, "nexa-icon.png")).convert("RGBA")
    return im.resize((128, 128), Image.LANCZOS)


def chrome(c: Canvas, idx: int, total: int) -> None:
    wm = wordmark()
    c.im.paste(wm, (M + 4, 61), wm)
    c.add("logo", (M + 4, 61, M + 4 + wm.width, 61 + wm.height))
    f = font("semibold", 26)
    s = f"{idx}/{total}"
    w = f.getlength(s)
    c.d.text((W - M - w, 60), s, font=f, fill=GRAY)
    c.add("counter", (W - M - w, 60, W - M, 90))
    # puntos de avance
    x, cy = M, 1279
    for i in range(1, total + 1):
        if i == idx:
            pill = gradient((34, 12), G1, G2)
            m = Image.new("L", (34, 12), 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, 33, 11), radius=6, fill=255)
            c.im.paste(pill, (x, cy - 6), m)
            x += 34 + 11
        else:
            c.d.ellipse((x, cy - 5, x + 10, cy + 5), fill=DOT)
            x += 11 + 11
    c.add("dots", (M, cy - 6, x, cy + 6))
    last = idx == total
    s = HANDLE if last else "Desliza →"
    w = f.getlength(s)
    c.d.text((W - M - w, 1263), s, font=f, fill=GRAY)
    c.add("footer", (W - M - w, 1263, W - M, 1297))


# ------------------------------------------------------------------ laminas
def _start_y(total_h: float) -> float:
    y = CENTER_Y - total_h / 2
    return max(TOP_SAFE + 30, min(y, BOTTOM_SAFE - 20 - total_h))


def cover(c: Canvas, data: dict) -> None:
    inner = W - 2 * M
    cat = (data.get("categoria") or "").strip().upper()
    fcat = font("semibold", 25)
    tr_cat = 4.0
    title = fit_block([Run(data.get("titulo", "")), Run(data.get("resaltado", ""), True)], "extrabold", range(96, 39, -4), inner, 1.03, -0.035, WHITE, 4)
    sub = fit_block([Run(data.get("subtitulo", ""))], "regular", [38, 36, 34, 32], inner, 1.34, 0, SOFT, 4)
    pill_h = 56 if cat else 0
    gap1 = 44 if cat else 0
    total = pill_h + gap1 + title.height + (34 + sub.height if sub.lines[0][0][0] else 0)
    y = _start_y(total)
    if cat:
        tw = min(text_w(cat, fcat, tr_cat), inner - 48)
        c.d.rounded_rectangle((M, y, M + tw + 48, y + pill_h), radius=pill_h // 2, fill=(40, 9, 25), outline=(122, 16, 58), width=2)
        draw_tracked(c.d, M + 24, y + 13, cat, fcat, PINK_TXT, tr_cat)
        c.add("category", (M, y, M + tw + 48, y + pill_h))
        y += pill_h + gap1
    y = c.text_block(title, M, y, "title")
    if sub.lines[0][0][0]:
        c.text_block(sub, M, y + 34, "subtitle")


def point(c: Canvas, n: int, data: dict) -> None:
    inner = W - 2 * M
    num = f"{n:02d}"
    fnum = font("black", 200)
    trn = -8.0
    title = fit_block([Run(data.get("titulo", ""))], "extrabold", range(72, 39, -4), inner, 1.1, -0.03, WHITE, 3)
    pad_x, pad_y = 36, 30
    box_w = inner - 2 * pad_x

    def box_text(s: str, size: int) -> TextBlock:
        return make_block([Run(s)], "regular", size, box_w, 1.34, 0, (232, 228, 236))

    size = 36
    while True:
        hoy = box_text(data.get("hoy", ""), size)
        con = box_text(data.get("con_clonexa", ""), size)
        num_h = 150
        box1 = pad_y * 2 + 24 + 16 + hoy.height
        box2 = pad_y * 2 + 24 + 16 + con.height
        total = num_h + 30 + title.height + 44 + box1 + 22 + box2
        if total <= BOTTOM_SAFE - TOP_SAFE - 50 or size <= 26:
            break
        size -= 2
    y = _start_y(total)
    # numero grande en degradado (caja visual de ~150 px de alto)
    asc = fnum.getmetrics()[0]
    top_pad = int(round(asc - fnum.size * 0.73))
    draw_tracked(c.hd, M - 4, y - top_pad, num, fnum, 255, trn)
    c.add("number", (M, y, M + text_w(num, fnum, trn), y + num_h))
    y += num_h + 30
    y = c.text_block(title, M, y, "title")
    y += 44
    flab = font("semibold", 23)
    for label, blk, bh, fill, outline, lab_color in (
        ("HOY", hoy, box1, (24, 22, 30), (44, 41, 52), (165, 160, 172)),
        ("CON CLONEXA", con, box2, (58, 12, 32), (124, 18, 56), PINK_TXT),
    ):
        c.d.rounded_rectangle((M, y, W - M, y + bh), radius=28, fill=fill, outline=outline, width=2)
        draw_tracked(c.d, M + pad_x, y + pad_y - 4, label, flab, lab_color, 3.5)
        c.text_block(blk, M + pad_x, y + pad_y + 24 + 16, "box_text")
        c.add("box", (M, y, W - M, y + bh), label=label)
        y += bh + 22


def closing(c: Canvas, data: dict) -> None:
    inner = W - 2 * M
    title = fit_block([Run(data.get("titulo", "")), Run(data.get("resaltado", ""), True)], "extrabold", range(86, 39, -4), inner, 1.06, -0.035, WHITE, 3)
    txt = fit_block([Run(data.get("texto", ""))], "regular", [38, 36, 34, 32], inner, 1.34, 0, SOFT, 4)
    fcta = font("extrabold", 44)
    cta_w = fcta.getlength(CTA) + 80
    cta_h = 104
    ic = icon()
    has_txt = bool(txt.lines[0][0][0])
    total = ic.height + 40 + title.height + (30 + txt.height if has_txt else 0) + 48 + cta_h
    y = _start_y(total)
    c.im.paste(ic, (M, int(y)), ic)
    c.add("icon", (M, y, M + ic.width, y + ic.height))
    y += ic.height + 40
    y = c.text_block(title, M, y, "title")
    if has_txt:
        y = c.text_block(txt, M, y + 30, "text")
    y += 48
    btn = gradient((int(cta_w), cta_h), G1, G2)
    m = Image.new("L", btn.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, btn.width - 1, btn.height - 1), radius=26, fill=255)
    c.im.paste(btn, (M, int(y)), m)
    asc = fcta.getmetrics()[0]
    c.d.text((M + 40, y + (cta_h - fcta.size * 0.76) / 2 - (asc - fcta.size * 0.76)), CTA, font=fcta, fill=(255, 255, 255))
    c.add("cta", (M, y, M + cta_w, y + cta_h))


def render(spec: dict) -> list[tuple[bytes, list[dict]]]:
    """spec = {portada:{categoria,titulo,resaltado,subtitulo}, puntos:[{titulo,hoy,con_clonexa}] (4-5),
    cierre:{titulo,resaltado,texto}} -> 6 o 7 laminas PNG con su layout."""
    puntos = list(spec.get("puntos") or [])
    total = len(puntos) + 2
    out: list[tuple[bytes, list[dict]]] = []
    for i in range(1, total + 1):
        c = Canvas()
        chrome(c, i, total)
        if i == 1:
            cover(c, spec.get("portada") or {})
        elif i == total:
            closing(c, spec.get("cierre") or {})
        else:
            point(c, i - 1, puntos[i - 2])
        out.append((c.finish(), c.layout))
    return out


def to_jpeg(raw: bytes, quality: int = 92) -> bytes:
    """Cualquier imagen -> JPEG RGB del mismo tamano (la transparencia queda sobre el fondo de marca)."""
    im = Image.open(io.BytesIO(raw))
    im.load()
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        base = Image.new("RGB", im.size, BG)
        base.paste(im, (0, 0), im)
        im = base
    else:
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()
