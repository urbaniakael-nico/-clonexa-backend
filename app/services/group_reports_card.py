"""Tarjeta PNG de los cortes de entrada y salida (whatsapp_group_reports, 073A).

Solo Pillow y las fuentes Vera que ya trae reportlab (tildes y ñ incluidas); sin navegador. Vertical,
1080 px de ancho, fondo oscuro, alto segun la cantidad de nombres. TODOS los nombres se dibujan
(sin "+N mas"): si no caben en una columna, la columna se parte en dos mas angostas y los nombres
largos pasan a dos lineas. render() devuelve (png, layout) y layout dice donde quedo cada nombre,
para poder probar que nada se corta ni se sale de la imagen.
"""
from __future__ import annotations

import io
import os
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

W = 1080
M = 60
GAP = 30
BG = (15, 23, 42)
INK = (226, 232, 240)
SOFT = (148, 163, 184)
GREEN_BOX, GREEN_NUM, GREEN_CHIP, GREEN_TXT, GREEN_BAR = (6, 78, 59), (110, 231, 183), (6, 59, 47), (209, 250, 229), (16, 185, 129)
RED_BOX, RED_NUM, RED_CHIP, RED_TXT = (127, 29, 29), (252, 165, 165), (76, 21, 24), (254, 202, 202)
AMBER_BOX, AMBER_NUM, AMBER_CHIP, AMBER_TXT = (120, 53, 15), (253, 230, 138), (69, 39, 8), (253, 224, 138)
NOTE_BOX, NOTE_TXT = (66, 32, 6), (253, 230, 138)
YELLOW = (250, 204, 21)
PILL_BG, PILL_TXT = (30, 64, 175), (191, 219, 254)
LONG_SHIFT_MIN = 12 * 60
SPLIT_AFTER = 12  # mas nombres que esto en una columna con pocos del otro lado: dos columnas angostas


def _font_dir() -> str:
    import reportlab

    return os.path.join(os.path.dirname(reportlab.__file__), "fonts")


_FONTS: dict[tuple[bool, int], Any] = {}


def font(size: int, bold: bool = False):
    key = (bold, size)
    if key not in _FONTS:
        try:
            _FONTS[key] = ImageFont.truetype(os.path.join(_font_dir(), "VeraBd.ttf" if bold else "Vera.ttf"), size)
        except OSError:  # sin reportlab: la fuente de Pillow, que igual escala
            _FONTS[key] = ImageFont.load_default(size)
    return _FONTS[key]


def text_w(draw: ImageDraw.ImageDraw, s: str, f) -> float:
    return draw.textlength(s, font=f)


def wrap(draw: ImageDraw.ImageDraw, s: str, f, width: float) -> list[str]:
    """Parte en lineas que caben; una palabra mas ancha que todo se parte por letras (nunca se corta)."""
    lines, cur = [], ""
    for word in [w for w in s.split(" ") if w]:  # el espacio duro ( ) no parte: "10 h 51 min" va junto
        trial = f"{cur} {word}".strip()
        if text_w(draw, trial, f) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = ""
        while text_w(draw, word, f) > width:
            cut = len(word)
            while cut > 1 and text_w(draw, word[:cut], f) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


# ------------------------------------------------------------------ iconos (sin emoji: dibujados)
def icon_check(d: ImageDraw.ImageDraw, x: float, y: float, s: float) -> None:
    d.rounded_rectangle([x, y, x + s, y + s], radius=s * 0.22, fill=GREEN_BAR)
    d.line([(x + s * 0.24, y + s * 0.52), (x + s * 0.43, y + s * 0.72), (x + s * 0.78, y + s * 0.3)], fill=(255, 255, 255), width=max(3, int(s * 0.13)))


def icon_x(d: ImageDraw.ImageDraw, x: float, y: float, s: float) -> None:
    d.rounded_rectangle([x, y, x + s, y + s], radius=s * 0.22, fill=(220, 38, 38))
    w = max(3, int(s * 0.13))
    d.line([(x + s * 0.28, y + s * 0.28), (x + s * 0.72, y + s * 0.72)], fill=(255, 255, 255), width=w)
    d.line([(x + s * 0.72, y + s * 0.28), (x + s * 0.28, y + s * 0.72)], fill=(255, 255, 255), width=w)


def icon_warn(d: ImageDraw.ImageDraw, x: float, y: float, s: float) -> None:
    d.polygon([(x + s / 2, y), (x + s, y + s * 0.92), (x, y + s * 0.92)], fill=(245, 158, 11))
    d.line([(x + s / 2, y + s * 0.3), (x + s / 2, y + s * 0.6)], fill=(30, 20, 0), width=max(3, int(s * 0.11)))
    d.ellipse([x + s * 0.44, y + s * 0.68, x + s * 0.56, y + s * 0.8], fill=(30, 20, 0))


def icon_pause(d: ImageDraw.ImageDraw, x: float, y: float, s: float) -> None:
    bw = s * 0.28
    d.rounded_rectangle([x + s * 0.12, y, x + s * 0.12 + bw, y + s], radius=3, fill=YELLOW)
    d.rounded_rectangle([x + s * 0.6, y, x + s * 0.6 + bw, y + s], radius=3, fill=YELLOW)


def icon_party(d: ImageDraw.ImageDraw, x: float, y: float, s: float) -> None:
    d.ellipse([x, y, x + s, y + s], fill=GREEN_BAR)
    d.line([(x + s * 0.24, y + s * 0.52), (x + s * 0.43, y + s * 0.72), (x + s * 0.78, y + s * 0.3)], fill=(255, 255, 255), width=max(3, int(s * 0.12)))


# ------------------------------------------------------------------ columnas de nombres
def _chips(d: Optional[ImageDraw.ImageDraw], items: list[dict], x: float, y: float, width: float, *, size: int, bold: bool,
           layout: list, column: str, draw: bool) -> float:
    """Dibuja (o solo mide si draw=False) una lista de chips. Devuelve el y final."""
    f = font(size, bold)
    pad_x, pad_y, line_h, gap = 18, 12, int(size * 1.3), 10
    measure = d or ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for it in items:
        icon = it.get("icon")
        indent = size * 0.95 if icon else 0
        lines = wrap(measure, it["text"], f, width - 2 * pad_x - indent)
        h = 2 * pad_y + line_h * len(lines)
        if draw:
            d.rounded_rectangle([x, y, x + width, y + h], radius=12, fill=it["bg"])
            if icon == "pause":
                icon_pause(d, x + pad_x, y + pad_y + (line_h - size * 0.8) / 2, size * 0.8)
            for i, line in enumerate(lines):
                d.text((x + pad_x + indent, y + pad_y + i * line_h + (line_h - size) / 2 - 2), line, font=f, fill=it["fg"])
            layout.append({"text": it["text"].replace(" ", " "), "lines": [ln.replace(" ", " ") for ln in lines],
                           "column": column, "box": (x, y, x + width, y + h)})
        y += h + gap
    return y


def _split(items: list[dict]) -> tuple[list[dict], list[dict]]:
    half = (len(items) + 1) // 2
    return items[:half], items[half:]


def _column(d, title: str, icon, color, items: list[dict], x: float, y: float, width: float, *, bold: bool, split: bool,
            layout: list, column: str, draw: bool) -> float:
    if draw:
        icon(d, x, y + 4, 32)
        d.text((x + 44, y), title, font=font(30, True), fill=color)
    y += 56
    if not items:
        if draw:
            d.text((x, y), "—", font=font(28), fill=SOFT)
        return y + 44
    if not split:
        return _chips(d, items, x, y, width, size=28, bold=bold, layout=layout, column=column, draw=draw)
    a, b = _split(items)
    sub = (width - 14) / 2
    return max(_chips(d, a, x, y, sub, size=23, bold=bold, layout=layout, column=column, draw=draw),
               _chips(d, b, x + sub + 14, y, sub, size=23, bold=bold, layout=layout, column=column, draw=draw))


# ------------------------------------------------------------------ tarjeta
def _model(card: dict) -> dict:
    """Textos, colores y listas de la tarjeta segun sea entrada o salida."""
    if card.get("type") == "checkout":
        still = [{"text": f"{n} · {str(hm).replace(' ', chr(160))}", "bg": RED_CHIP if int(m or 0) > LONG_SHIFT_MIN else AMBER_CHIP,
                  "fg": RED_TXT if int(m or 0) > LONG_SHIFT_MIN else AMBER_TXT} for n, m, hm in card.get("still") or []]
        done = [{"text": n, "bg": GREEN_CHIP, "fg": GREEN_TXT} for n in card.get("done") or []]
        return {"tag": "SALIDA · CHECK-OUT", "good": len(done), "bad": len(still),
                "good_label": "Ya cerraron / Clocked out", "bad_label": "Siguen conectados / Still clocked in",
                "bad_box": AMBER_BOX, "bad_num": AMBER_NUM, "bar_bad": (245, 158, 11),
                "left": ("Siguen conectados", icon_warn, AMBER_TXT, still), "right": ("Ya cerraron", icon_check, GREEN_TXT, done),
                "all_ok": ("Todos cerraron", "Everyone clocked out"),
                "note": ("Cierra tu turno en el bot ahora.", "Close your shift in the bot now."), "bad_icon": icon_warn}
    connected = [{"text": n, "bg": GREEN_CHIP, "fg": YELLOW if paused else GREEN_TXT, "icon": "pause" if paused else None}
                 for n, paused in card.get("connected") or []]
    missing = [{"text": n, "bg": RED_CHIP, "fg": RED_TXT} for n in card.get("missing") or []]
    return {"tag": "ENTRADA · CHECK-IN", "good": len(connected), "bad": len(missing),
            "good_label": "Conectados / Connected", "bad_label": "Sin conectar / Not connected",
            "bad_box": RED_BOX, "bad_num": RED_NUM, "bar_bad": (153, 27, 27),
            "left": ("Sin conectar", icon_x, RED_TXT, missing), "right": ("Conectados", icon_check, GREEN_TXT, connected),
            "all_ok": ("Todos conectados", "Everyone is clocked in"),
            "note": ("Si ya estás trabajando, abre el bot y marca Iniciar turno.", "If you're already working, open the bot and tap Start shift."),
            "bad_icon": icon_x}


def _paint(d: Optional[ImageDraw.ImageDraw], card: dict, mdl: dict, layout: list, draw: bool) -> float:
    inner = W - 2 * M
    y = 56.0
    if draw:
        d.text((M, y + 6), "VOLTAGE" if not card.get("company") else str(card["company"]).upper(), font=font(30, True), fill=SOFT)
        tag_f = font(26, True)
        tw = d.textlength(mdl["tag"], font=tag_f)
        d.rounded_rectangle([W - M - tw - 44, y, W - M, y + 52], radius=26, fill=PILL_BG)
        d.text((W - M - tw - 22, y + 11), mdl["tag"], font=tag_f, fill=PILL_TXT)
    y += 82
    if draw:
        d.text((M, y), card.get("operation") or "", font=font(76, True), fill=INK)
    y += 96
    measure = d or ImageDraw.Draw(Image.new("RGB", (1, 1)))
    sub_lines = wrap(measure, card.get("subtitle") or "", font(30), inner)
    for line in sub_lines:
        if draw:
            d.text((M, y), line, font=font(30), fill=SOFT)
        y += 40
    y += 30
    box_w = (inner - 24) / 2
    rows = max(len(wrap(measure, mdl[k], font(26), box_w - 60 - 40)) for k in ("good_label", "bad_label"))
    for i, (num, label, bg, numc, ic) in enumerate(((mdl["good"], mdl["good_label"], GREEN_BOX, GREEN_NUM, icon_check),
                                                    (mdl["bad"], mdl["bad_label"], mdl["bad_box"], mdl["bad_num"], mdl["bad_icon"]))):
        x = M + i * (box_w + 24)
        lab = wrap(measure, label, font(26), box_w - 60 - 40)
        h = 150 + 34 * rows
        if draw:
            d.rounded_rectangle([x, y, x + box_w, y + h], radius=28, fill=bg)
            d.text((x + 30, y + 24), str(num), font=font(96, True), fill=numc)
            ic(d, x + 30, y + 140, 30)
            for j, line in enumerate(lab):
                d.text((x + 72, y + 138 + 34 * j), line, font=font(26), fill=INK)
        last_h = h
    y += last_h + 36
    total = max(1, mdl["good"] + mdl["bad"])
    pct = mdl["good"] / total
    if draw:
        d.rounded_rectangle([M, y, W - M, y + 22], radius=11, fill=mdl["bar_bad"] if mdl["bad"] else GREEN_BAR)
        if mdl["good"]:
            d.rounded_rectangle([M, y, M + max(22, inner * pct), y + 22], radius=11, fill=GREEN_BAR)
        d.text((W - M - d.textlength(f"{round(pct * 100)}%", font=font(26, True)), y + 32), f"{round(pct * 100)}%", font=font(26, True), fill=INK)
    y += 80
    left_title, left_icon, left_color, left_items = mdl["left"]
    right_title, right_icon, right_color, right_items = mdl["right"]
    if not left_items:
        h = 150
        if draw:
            d.rounded_rectangle([M, y, W - M, y + h], radius=28, fill=GREEN_BOX)
            icon_party(d, M + 34, y + 45, 60)
            d.text((M + 120, y + 30), mdl["all_ok"][0], font=font(44, True), fill=GREEN_NUM)
            d.text((M + 120, y + 88), mdl["all_ok"][1], font=font(30), fill=INK)
        y += h + 36
        if right_items:
            y = _column(d, right_title, right_icon, right_color, right_items, M, y, inner, bold=False, split=True,
                        layout=layout, column="right", draw=draw)
        return y + 10
    col_w = (inner - GAP) / 2
    split = len(right_items) > max(SPLIT_AFTER, len(left_items) + 4)
    left_end = _column(d, left_title, left_icon, left_color, left_items, M, y, col_w, bold=True, split=False,
                       layout=layout, column="left", draw=draw)
    right_end = _column(d, right_title, right_icon, right_color, right_items, M + col_w + GAP, y, col_w, bold=False, split=split,
                        layout=layout, column="right", draw=draw)
    y = max(left_end, right_end) + 26
    note_f, note_b = font(28), font(28, True)
    lines = wrap(measure, mdl["note"][0], note_b, inner - 110) + wrap(measure, mdl["note"][1], note_f, inner - 110)
    h = 48 + 40 * len(lines)
    if draw:
        d.rounded_rectangle([M, y, W - M, y + h], radius=24, fill=NOTE_BOX)
        icon_warn(d, M + 30, y + 26, 34)
        n_es = len(wrap(measure, mdl["note"][0], note_b, inner - 110))
        for i, line in enumerate(lines):
            d.text((M + 80, y + 24 + 40 * i), line, font=note_b if i < n_es else note_f, fill=NOTE_TXT)
    return y + h + 10


def render(card: dict) -> tuple[bytes, dict]:
    """card: {type: checkin|checkout, company, operation, subtitle, connected [[nombre, en_pausa]], missing [nombre],
    done [nombre], still [[nombre, minutos, "10 h 51 min"]]}. Devuelve (PNG, layout)."""
    mdl = _model(card)
    height = int(_paint(None, card, mdl, [], False) + 56)
    img = Image.new("RGB", (W, height), BG)
    d = ImageDraw.Draw(img)
    layout: list = []
    _paint(d, card, mdl, layout, True)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue(), {"width": W, "height": height, "names": layout}
