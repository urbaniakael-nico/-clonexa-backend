"""7 diferencias (Juegos en vivo): escenas ilustradas por el servidor.

Cada escena es una lista de formas vectoriales (rectangulos, elipses, poligonos,
lineas y texto) en un lienzo de 800x600 que el servidor dibuja con Pillow (con
supermuestreo para bordes suaves) y entrega como PNG. NO se manda el dibujo
vectorial al celular: comparando el codigo de dos SVG se verian las diferencias
sin mirar. Nada se guarda en Postgres; las imagenes viven en una cache corta.

Cada escena define 19 diferencias candidatas pequenas (quitar o agregar un
objeto, cambiar un tono a uno cercano, reflejar un detalle, cambiar un numero
o letra, mover unos pixeles, cambiar una franja, agregar un reflejo o
estrella). Por ronda se eligen 7 con la semilla: todas en zonas distintas de la
imagen (rejilla 3x3) y separadas. La zona de cada una se calcula de la forma que
cambia; nunca viaja al celular hasta acertarla.
"""
from __future__ import annotations

import io
import math
import random
from functools import lru_cache
from typing import Any, Callable, Optional

W, H = 800, 600
OUT_W, OUT_H = 1000, 750  # PNG final (zoom en el celular sin verse borroso)
SS = 2  # supermuestreo
MIN_ZONE_R = 40  # zona >= ~1 % de la imagen
MAX_ZONE_R = 66  # zona <= ~3 % de la imagen
HIT_TOLERANCE = 4
MIN_SEPARATION = 110
GRID = 3


# ---------------------------------------------------------------- color (sRGB <-> Lab, para tonos cercanos)
def _full(c: str) -> str:
    c = c.lstrip("#")
    return "".join(ch * 2 for ch in c) if len(c) in (3, 4) else c


def _hex(c: str) -> tuple[int, int, int]:
    c = _full(c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _to_hex(rgb: tuple) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(v)))):02x}" for v in rgb)


def rgb_to_lab(rgb: tuple) -> tuple[float, float, float]:
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(float(x)) for x in rgb)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def lab_to_rgb(lab: tuple) -> tuple[float, float, float]:
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def inv(t):
        return t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116) / 7.787
    x, y, z = inv(fx) * 0.95047, inv(fy), inv(fz) * 1.08883
    r = x * 3.2406 + y * -1.5372 + z * -0.4986
    g = x * -0.9689 + y * 1.8758 + z * 0.0415
    bb = x * 0.0557 + y * -0.2040 + z * 1.0570

    def gam(v):
        v = max(0.0, min(1.0, v))
        return 255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)
    return gam(r), gam(g), gam(bb)


def delta_e(c1: str, c2: str) -> float:
    a, b = rgb_to_lab(_hex(c1)), rgb_to_lab(_hex(c2))
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def near_tone(color: str, target: float = 11.0) -> str:
    """Un tono cercano (no opuesto): mueve el color en Lab hasta quedar a ~target de distancia."""
    lab = rgb_to_lab(_hex(color))
    best, best_gap = color, 99.0
    for ang in range(0, 360, 15):
        for dl in (-6, -3, 0, 3, 6):
            for k in (0.6, 0.8, 1.0, 1.2, 1.4):
                cand = _to_hex(lab_to_rgb((lab[0] + dl * k, lab[1] + target * k * math.cos(math.radians(ang)), lab[2] + target * k * math.sin(math.radians(ang)))))
                gap = abs(delta_e(color, cand) - target)
                if gap < best_gap:
                    best, best_gap = cand, gap
    return best


# ---------------------------------------------------------------- formas
def R(i, x0, y0, x1, y1, fill, r=0, outline=None, w=0):  # noqa: N802
    return {"id": i, "t": "rect", "box": (x0, y0, x1, y1), "fill": fill, "r": r, "outline": outline, "w": w}


def E(i, cx, cy, rx, ry, fill, outline=None, w=0):  # noqa: N802
    return {"id": i, "t": "ell", "box": (cx - rx, cy - ry, cx + rx, cy + ry), "fill": fill, "outline": outline, "w": w}


def P(i, pts, fill, outline=None, w=0):  # noqa: N802
    return {"id": i, "t": "poly", "pts": [tuple(p) for p in pts], "fill": fill, "outline": outline, "w": w}


def L(i, pts, fill, w=2):  # noqa: N802
    return {"id": i, "t": "line", "pts": [tuple(p) for p in pts], "fill": fill, "w": w}


def T(i, x, y, s, size, fill):  # noqa: N802
    return {"id": i, "t": "text", "xy": (x, y), "s": s, "size": size, "fill": fill}


def star(i, cx, cy, r, fill):
    pts = []
    for k in range(10):
        rr = r if k % 2 == 0 else r * 0.42
        a = math.radians(-90 + k * 36)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return P(i, pts, fill)


def _font(size: float):
    from PIL import ImageFont

    return ImageFont.load_default(size=max(6, int(size)))


def bbox(el: dict) -> tuple[float, float, float, float]:
    if el["t"] in ("rect", "ell"):
        x0, y0, x1, y1 = el["box"]
        pad = el.get("w", 0)
        return x0 - pad, y0 - pad, x1 + pad, y1 + pad
    if el["t"] in ("poly", "line"):
        xs, ys = [p[0] for p in el["pts"]], [p[1] for p in el["pts"]]
        pad = el.get("w", 0)
        return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    x, y = el["xy"]
    l, t, r, b = _font(el["size"]).getbbox(el["s"], anchor="mm")
    return x + l - 2, y + t - 2, x + r + 2, y + b + 2


# ---------------------------------------------------------------- operaciones de diferencia
def _find(els: list, ident: str) -> int:
    for k, e in enumerate(els):
        if e["id"] == ident:
            return k
    raise KeyError(ident)


def op_remove(*ids):
    def run(els):
        return [e for e in els if e["id"] not in ids]
    run.touch = ids
    return run


def op_add(after: str, *new):
    def run(els):
        k = _find(els, after)
        return els[: k + 1] + list(new) + els[k + 1:]
    run.adds = new
    return run


def op_recolor(ident: str, target: float = 11.0):
    def run(els):
        out = [dict(e) for e in els]
        k = _find(out, ident)
        out[k]["fill"] = near_tone(out[k]["fill"], target)
        return out
    run.touch = (ident,)
    run.recolor = ident
    return run


def _shift(el, dx, dy):
    e = dict(el)
    if e["t"] in ("rect", "ell"):
        x0, y0, x1, y1 = e["box"]
        e["box"] = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
    elif e["t"] in ("poly", "line"):
        e["pts"] = [(x + dx, y + dy) for x, y in e["pts"]]
    else:
        e["xy"] = (e["xy"][0] + dx, e["xy"][1] + dy)
    return e


def op_move(dx: float, dy: float, *ids):
    def run(els):
        return [_shift(e, dx, dy) if e["id"] in ids else e for e in els]
    run.touch = ids
    run.move = (dx, dy)
    return run


def op_mirror(*ids):
    """Refleja un detalle (poligonos y lineas) sobre su eje vertical."""
    def run(els):
        group = [e for e in els if e["id"] in ids]
        x0 = min(bbox(e)[0] for e in group)
        x1 = max(bbox(e)[2] for e in group)
        cx = (x0 + x1) / 2
        out = []
        for e in els:
            if e["id"] in ids and e["t"] in ("poly", "line"):
                e = dict(e)
                e["pts"] = [(2 * cx - x, y) for x, y in e["pts"]]
            out.append(e)
        return out
    run.touch = ids
    return run


def op_text(ident: str, new: str):
    def run(els):
        out = [dict(e) for e in els]
        out[_find(out, ident)]["s"] = new
        return out
    run.touch = (ident,)
    return run


# ---------------------------------------------------------------- escenas
def _wood(prefix, x0, y0, x1, y1, n, c1, c2, vertical=True):
    out = []
    for k in range(n):
        if vertical:
            a, b = x0 + (x1 - x0) * k / n, x0 + (x1 - x0) * (k + 1) / n
            out.append(R(f"{prefix}{k}", a, y0, b, y1, c1 if k % 2 == 0 else c2))
        else:
            a, b = y0 + (y1 - y0) * k / n, y0 + (y1 - y0) * (k + 1) / n
            out.append(R(f"{prefix}{k}", x0, a, x1, b, c1 if k % 2 == 0 else c2))
    return out


def scene_bar() -> tuple[list, dict]:
    """Barra con botellas y copas."""
    rnd = random.Random(11)
    els = [R("bg", 0, 0, W, H, "#1e1712")] + _wood("wall", 0, 40, W, 380, 10, "#2b1f16", "#261b13")
    els += [R("neonbox", 250, 6, 550, 38, "#1a1320", r=8, outline="#3a2a44", w=2), T("neon", 400, 22, "THE TIME BAR", 22, "#ff6fb0"),
            L("neonline", [(270, 33), (530, 33)], "#7a2f57", 2)]
    bottle_colors = ["#2f6b3a", "#6b2f2f", "#3a4f7a", "#8a6a2a", "#5b3a6b", "#2a6b66", "#7a4a2a", "#4a5a2a", "#6b2f55"]
    label_colors = ["#e8dcc0", "#d9c9a3", "#f0e6cc", "#cfd8dc", "#e6cfa8"]
    for s, base in enumerate((140, 245, 350)):
        els.append(R(f"shelf{s}", 20, base, 780, base + 9, "#6b4a2b", r=2))
        els += [R(f"br{s}a", 60, base + 9, 70, base + 24, "#4b3420"), R(f"br{s}b", 730, base + 9, 740, base + 24, "#4b3420")]
        for b in range(9):
            x = 52 + b * 84 + rnd.randint(-4, 4)
            h = rnd.choice((62, 70, 78))
            col = bottle_colors[(b + s * 3) % len(bottle_colors)]
            p = f"s{s}b{b}"
            if (b + s) % 3 == 0:
                els.append(E(f"{p}body", x, base - h / 2 + 4, 17, h / 2 - 4, col))
            else:
                els.append(R(f"{p}body", x - 15, base - h, x + 15, base, col, r=6))
            els += [R(f"{p}neck", x - 5, base - h - 20, x + 5, base - h + 2, col),
                    R(f"{p}cap", x - 7, base - h - 26, x + 7, base - h - 19, "#c9a24a" if b % 2 else "#9aa3ab", r=2),
                    R(f"{p}label", x - 12, base - h * 0.62, x + 12, base - h * 0.62 + 20, label_colors[(b + s) % 5], r=2),
                    L(f"{p}shine", [(x - 10, base - h + 8), (x - 10, base - 12)], "#ffffff22", 2)]
    els += [R("counter", 0, 380, W, 402, "#5a3a22"), R("counterlip", 0, 400, W, 408, "#3e2817")] + _wood("front", 0, 408, W, H, 8, "#33231a", "#2e2017")
    for g in range(6):
        x = 70 + g * 130
        p = f"g{g}"
        els += [E(f"{p}coaster", x, 392, 24, 6, "#7a5a3a" if g % 2 else "#4a6a7a"),
                P(f"{p}bowl", [(x - 26, 318), (x + 26, 318), (x, 352)], "#cfe3ea", outline="#9fb3ba", w=1),
                P(f"{p}drink", [(x - 20, 324), (x + 20, 324), (x, 347)], ["#d9533a", "#e3b23c", "#7fb069", "#c06c84", "#4e9ec2", "#e07a5f"][g]),
                L(f"{p}stem", [(x, 352), (x, 386)], "#bcd0d6", 3), E(f"{p}base", x, 387, 14, 3, "#bcd0d6")]
        if g in (0, 3):
            els += [E(f"{p}lemon", x + 20, 320, 12, 12, "#f2d14b", outline="#c9a52a", w=2), L(f"{p}lemonseg", [(x + 10, 320), (x + 30, 320)], "#c9a52a", 2)]
        if g in (1, 4):
            els.append(L(f"{p}straw", [(x - 6, 300), (x + 4, 340)], "#e5e5e5", 3))
    els += [R("menu", 360, 330, 432, 378, "#efe6d2", r=3, outline="#b9a882", w=1), T("menutitle", 396, 342, "COCTEL", 10, "#5a4630"),
            T("price", 396, 362, "$15", 14, "#7a2f2f"), R("jar", 640, 340, 676, 380, "#cfe3ea", r=5, outline="#9fb3ba", w=1),
            E("coin1", 652, 368, 6, 3, "#c9a24a"), E("coin2", 665, 372, 6, 3, "#c9a24a")]
    for k in range(3):
        x = 160 + k * 240
        els += [E(f"stool{k}seat", x, 470, 52, 14, "#8a2f2f" if k != 1 else "#2f5a8a"), L(f"stool{k}l1", [(x - 30, 478), (x - 40, 590)], "#9aa3ab", 5),
                L(f"stool{k}l2", [(x + 30, 478), (x + 40, 590)], "#9aa3ab", 5), L(f"stool{k}ring", [(x - 36, 545), (x + 36, 545)], "#9aa3ab", 4)]
    els += [E("clock", 140, 22, 17, 17, "#efe6d2", outline="#6b4a2b", w=2), T("clock12", 140, 11, "12", 7, "#2b1f16"), L("clockh", [(140, 22), (140, 12)], "#2b1f16", 2),
            L("clockm", [(140, 22), (152, 27)], "#2b1f16", 2)]
    for k in range(5):  # botellitas de amargo y servilletas sobre la barra
        x = 125 + k * 130
        els += [R(f"bit{k}", x - 5, 360, x + 5, 380, "#5a2a1a" if k % 2 else "#2a3a1a", r=2), R(f"bit{k}cap", x - 3, 354, x + 3, 361, "#c9a24a"),
                R(f"nap{k}", x + 8, 372, x + 22, 380, "#efe6d2")]
    els += [R("shaker", 520, 330, 540, 380, "#c9c9d6", r=6), R("shakercap", 522, 320, 538, 332, "#aeb3bd", r=4), E("cherry", 205, 338, 4, 4, "#a1162b"),
            L("cherrystem", [(205, 334), (209, 326)], "#4a6a2a", 1), T("brand", 560, 22, "EST. 1975", 8, "#b78bab")]
    cands = {
        "bar-01": op_recolor("s0b1body"), "bar-02": op_remove("s0b4body", "s0b4neck", "s0b4cap", "s0b4label", "s0b4shine"), "bar-03": op_recolor("s0b5body"),
        "bar-04": op_move(9, 0, "s0b7body", "s0b7neck", "s0b7cap", "s0b7label", "s0b7shine"), "bar-05": op_recolor("s1b0body", 12),
        "bar-06": op_remove("s2b4label"), "bar-07": op_add("s1b8shine", star("star1", 722, 200, 24, "#fff6d0")), "bar-08": op_remove("g0lemon", "g0lemonseg"),
        "bar-09": op_recolor("menu"), "bar-10": op_recolor("stool2seat", 11), "bar-11": op_remove("g4drink"), "bar-12": op_recolor("g2drink"),
        "bar-13": op_add("front7", E("nuts", 265, 372, 26, 10, "#8a6a3a")), "bar-14": op_recolor("s2b8body", 10), "bar-15": op_remove("clock", "clock12", "clockh", "clockm"),
        "bar-16": op_move(0, 7, "jar", "coin1", "coin2"), "bar-17": op_recolor("stool0seat", 12), "bar-18": op_remove("s1b2label"), "bar-19": op_recolor("stool1seat", 11),
    }
    return els, cands


def scene_stage() -> tuple[list, dict]:
    """Escenario con banda y luces."""
    els = [R("bg", 0, 0, W, H, "#120f1c"), R("truss", 0, 30, W, 44, "#3a3a46")]
    for k in range(16):
        els.append(L(f"tr{k}", [(k * 50, 30), (k * 50 + 25, 44)], "#55556a", 2))
    gels = ["#e85d75", "#f2b134", "#5dade2", "#a569bd", "#58d68d", "#f5b041", "#ec7063", "#5dade2"]
    for k in range(8):
        x = 60 + k * 97
        els += [R(f"spot{k}", x - 16, 44, x + 16, 70, "#2a2a33", r=4), E(f"gel{k}", x, 72, 13, 7, gels[k]),
                P(f"beam{k}", [(x - 10, 78), (x + 10, 78), (x + 46, 300), (x - 46, 300)], "#1d1a2c")]
    els += [R("floor", 0, 420, W, H, "#1f1a14")] + _wood("plank", 0, 420, W, H, 6, "#241e17", "#1f1a14", vertical=False)
    for k in range(2):
        x = 40 if k == 0 else 640
        els += [R(f"amp{k}", x, 250, x + 120, 420, "#202028", r=6, outline="#3a3a46", w=2), R(f"amp{k}grill", x + 10, 290, x + 110, 410, "#2c2c36", r=4)]
        for r in range(3):
            els.append(L(f"amp{k}stripe{r}", [(x + 14, 310 + r * 30), (x + 106, 310 + r * 30)], "#3a3a46", 3))
        for n in range(5):
            els.append(E(f"amp{k}knob{n}", x + 20 + n * 20, 270, 6, 6, "#c9c9d6"))
    els += [E("kick", 400, 360, 60, 60, "#d9d4c7", outline="#7a2f2f", w=6), T("kicklogo", 400, 360, "TTM", 30, "#7a2f2f"),
            E("tom1", 350, 280, 26, 14, "#7a2f2f"), E("tom2", 450, 280, 26, 14, "#7a2f2f"), E("snare", 320, 330, 30, 12, "#c9c9d6"),
            E("crash", 300, 230, 34, 7, "#d4ac0d"), E("ride", 505, 238, 38, 8, "#d4ac0d"), L("crashst", [(300, 237), (300, 420)], "#9aa3ab", 3),
            L("ridest", [(505, 246), (505, 420)], "#9aa3ab", 3), E("throne", 400, 300, 22, 9, "#202028")]
    # guitarrista y bajista (siluetas)
    for k, x in enumerate((210, 590)):
        els += [E(f"head{k}", x, 205, 14, 16, "#2a2233"), P(f"body{k}", [(x - 22, 222), (x + 22, 222), (x + 18, 330), (x - 18, 330)], "#2a2233"),
                L(f"leg{k}a", [(x - 10, 330), (x - 16, 418)], "#2a2233", 10), L(f"leg{k}b", [(x + 10, 330), (x + 16, 418)], "#2a2233", 10),
                P(f"guitar{k}", [(x - 30, 285), (x + 8, 270), (x + 14, 300), (x - 24, 312)], "#b03a2e" if k == 0 else "#2e86c1"),
                L(f"neck{k}", [(x + 10, 284), (x + 62, 252)], "#6e4b2a", 4), E(f"pick{k}", x - 10, 293, 6, 4, "#f5f5f5")]
    els += [L("mic1", [(250, 420), (250, 230)], "#9aa3ab", 3), E("mic1head", 250, 226, 6, 6, "#c9c9d6"),
            L("mic2", [(560, 420), (560, 230)], "#9aa3ab", 3), E("mic2head", 560, 226, 6, 6, "#c9c9d6"),
            R("setlist", 470, 438, 540, 488, "#efe6d2", r=2), T("set1", 505, 452, "1 HIGHWAY", 8, "#222"), T("set2", 505, 466, "2 QUEEN 75", 8, "#222"),
            T("set3", 505, 480, "3 EL TRISTE", 8, "#222"), R("pedal1", 200, 440, 236, 462, "#e5a823", r=3), R("pedal2", 246, 440, 282, 462, "#58a55c", r=3),
            L("cable", [(236, 451), (300, 470), (380, 470), (420, 430)], "#111", 3)]
    for k in range(9):
        els.append(E(f"crowd{k}", 50 + k * 88, 590, 30, 34, "#0b0912"))
    els += [star("spark1", 120, 120, 18, "#fff6d0"), star("spark2", 690, 140, 16, "#fff6d0")]
    els += [R("banner", 320, 92, 480, 124, "#5a1a24", r=3), T("bannert", 400, 108, "TTM LIVE 1975", 14, "#efe6d2"),
            L("bannerl", [(330, 92), (330, 44)], "#55556a", 2), L("bannerr", [(470, 92), (470, 44)], "#55556a", 2)]
    for k, x in enumerate((150, 400, 650)):
        els += [P(f"wedge{k}", [(x - 34, 440), (x + 34, 440), (x + 28, 422), (x - 28, 422)], "#202028"), R(f"wedgegr{k}", x - 22, 426, x + 22, 436, "#2c2c36")]
    for k in range(6):
        x = 120 + k * 22
        els += [R(f"fx{k}", x, 470, x + 18, 492, ["#c0392b", "#2e86c1", "#e5a823", "#7d3c98", "#58a55c", "#9aa3ab"][k], r=2),
                E(f"fx{k}k", x + 9, 477, 3, 3, "#1b1b1b")]
    els += [E("hat1", 535, 300, 24, 5, "#d4ac0d"), E("hat2", 535, 306, 24, 5, "#c29d0b"), L("hatst", [(535, 306), (535, 420)], "#9aa3ab", 3),
            E("ftom", 470, 360, 24, 12, "#7a2f2f"), L("ftomleg", [(470, 372), (470, 420)], "#9aa3ab", 2), E("kickpad", 400, 425, 12, 4, "#9aa3ab")]
    for k, x in enumerate((210, 590)):
        for n in range(3):
            els.append(L(f"str{k}{n}", [(x + 14, 281 + n * 2), (x + 60, 254 + n * 2)], "#d6d6d6", 1))
    for k in range(10):
        x = 6 + k * 88
        els += [E(f"crowdb{k}", x, 560, 24, 26, "#0f0c18"), L(f"hand{k}", [(x + 10, 548), (x + 18, 505)], "#0f0c18", 6)]
        if k % 3 == 0:
            els.append(R(f"phone{k}", x + 12, 492, x + 24, 512, "#b9c7ff", r=2))
    for k, (x, y) in enumerate([(70, 200), (260, 150), (520, 170), (760, 240), (420, 200)]):
        els.append(star(f"twk{k}", x, y, 4, "#d9d4ff"))
    cands = {
        "stg-01": op_recolor("spot1", 11), "stg-02": op_remove("wedge0", "wedgegr0"), "stg-03": op_text("kicklogo", "TTN"), "stg-04": op_mirror("guitar1", "neck1"),
        "stg-05": op_recolor("wedge2", 12), "stg-06": op_recolor("setlist"), "stg-07": op_move(8, 0, "pedal2"), "stg-08": op_recolor("pedal1", 12),
        "stg-09": op_remove("spark1"), "stg-10": op_recolor("tom1"), "stg-11": op_recolor("guitar0", 10),
        "stg-12": op_recolor("head1", 12), "stg-13": op_remove("crowd2"), "stg-14": op_move(0, 8, "crash"), "stg-15": op_add("spark2", star("spark3", 600, 110, 16, "#fff6d0")),
        "stg-16": op_remove("fx3", "fx3k"), "stg-17": op_recolor("throne", 12), "stg-18": op_add("amp1", R("towel", 690, 252, 740, 266, "#d9d4c7", r=2)), "stg-19": op_recolor("spot3", 11),
    }
    return els, cands


def scene_jukebox() -> tuple[list, dict]:
    """Rocola con discos de vinilo."""
    els = [R("bg", 0, 0, W, H, "#1b1420")]
    for y in range(8):
        for x in range(16):
            els.append(R(f"tile{x}_{y}", x * 50, 440 + y * 20, x * 50 + 50, 460 + y * 20, "#e8e0d0" if (x + y) % 2 == 0 else "#2a2230"))
    els += [R("jbody", 290, 110, 510, 440, "#7a2f2f", r=18), E("jarch", 400, 140, 110, 90, "#8a3a2f"), E("jarch2", 400, 140, 96, 78, "#f2b134"),
            E("jarch3", 400, 140, 82, 66, "#e85d75"), E("jarch4", 400, 140, 68, 54, "#5dade2"), E("jwin", 400, 150, 54, 42, "#1a1420")]
    for k in range(4):
        els.append(E(f"jrec{k}", 372 + k * 18, 160, 16, 16, "#111", outline="#333", w=1))
    els.append(R("jpanel", 310, 230, 490, 320, "#efe6d2", r=6))
    letters = "ABCDE"
    for r in range(3):
        for c in range(5):
            x, y = 330 + c * 35, 248 + r * 26
            els += [R(f"btn{r}{c}", x - 13, y - 9, x + 13, y + 9, "#c9c9d6", r=4), T(f"lbl{r}{c}", x, y, f"{letters[c]}{r + 1}", 9, "#2a2230")]
    els += [R("jgrill", 320, 330, 480, 420, "#3a2230", r=8)]
    for k in range(6):
        els.append(L(f"jg{k}", [(330, 342 + k * 14), (470, 342 + k * 14)], "#5a3a48", 3))
    els += [R("coin", 470, 250, 482, 280, "#9aa3ab", r=3), E("chrome1", 300, 300, 6, 6, "#e5e5e5"), E("chrome2", 500, 300, 6, 6, "#e5e5e5")]
    for k, (x, y, lab) in enumerate([(90, 110, "#e85d75"), (180, 200, "#f2b134"), (90, 300, "#58d68d"), (620, 120, "#5dade2"), (710, 210, "#a569bd"), (620, 310, "#ec7063")]):
        els += [E(f"vin{k}", x, y, 46, 46, "#111", outline="#2a2a2a", w=2), E(f"vin{k}g1", x, y, 36, 36, "#1b1b1b"), E(f"vin{k}g2", x, y, 26, 26, "#151515"),
                E(f"vin{k}lab", x, y, 15, 15, lab), E(f"vin{k}hole", x, y, 3, 3, "#1b1420")]
    els += [R("sleeve1", 200, 60, 260, 120, "#2e86c1", r=2), T("sleeve1t", 230, 90, "45", 16, "#efe6d2"),
            R("sleeve2", 540, 330, 600, 390, "#b03a2e", r=2), T("sleeve2t", 570, 360, "LP", 16, "#efe6d2"),
            P("arrow", [(232, 356), (258, 340), (258, 350), (284, 350), (284, 354), (266, 354), (258, 372)], "#f2b134"),
            star("jstar", 400, 60, 18, "#fff6d0")]
    els += [L("neonp", [(20, 20), (250, 20)], "#ff6fb0", 4), L("neonb", [(550, 20), (780, 20)], "#5dade2", 4),
            R("poster1", 30, 380, 120, 430, "#2a4a6b", r=2), T("poster1t", 75, 396, "ROCK", 12, "#efe6d2"), T("poster1y", 75, 416, "1975", 10, "#f2b134"),
            R("poster2", 680, 30, 770, 80, "#4a2a4a", r=2), T("poster2t", 725, 48, "VINILO", 11, "#efe6d2"), T("poster2s", 725, 66, "33 RPM", 8, "#e85d75")]
    for k in range(12):
        x = 160 + k * 9
        els.append(R(f"spine{k}", x, 380, x + 7, 432, ["#c0392b", "#2e86c1", "#e5a823", "#58a55c", "#7d3c98", "#efe6d2"][k % 6]))
    els += [R("spineshelf", 150, 432, 270, 438, "#6b4a2b"), E("coaster", 560, 420, 18, 6, "#7a5a3a")]
    for k, (x, y) in enumerate([(330, 205), (470, 205), (300, 430), (500, 430)]):
        els.append(E(f"bolt{k}", x, y, 4, 4, "#d9d9e3"))
    cands = {
        "jbx-01": op_recolor("vin0lab", 11), "jbx-02": op_remove("vin1lab"), "jbx-03": op_remove("btn12", "lbl12"), "jbx-04": op_recolor("sleeve1"),
        "jbx-05": op_move(8, 0, "vin3", "vin3g1", "vin3g2", "vin3lab", "vin3hole"), "jbx-06": op_recolor("poster2"), "jbx-07": op_mirror("arrow"),
        "jbx-08": op_recolor("poster1"), "jbx-09": op_remove("jstar"), "jbx-10": op_recolor("tile3_2", 9), "jbx-11": op_remove("spine4", "spine5"),
        "jbx-12": op_recolor("vin5lab", 12), "jbx-13": op_recolor("sleeve2"), "jbx-14": op_recolor("tile13_5", 9),
        "jbx-15": op_add("vin4hole", star("vstar", 730, 180, 18, "#fff6d0")), "jbx-16": op_remove("coin"), "jbx-17": op_recolor("vin2lab", 11),
        "jbx-18": op_remove("jrec1", "jrec2"), "jbx-19": op_recolor("tile8_4", 9),
    }
    return els, cands


def scene_cards() -> tuple[list, dict]:
    """Mesa con velas y cartas."""
    els = [R("bg", 0, 0, W, H, "#140f0c")] + _wood("table", 0, 0, W, H, 12, "#3a2617", "#33221a", vertical=False)
    for k, (x, y) in enumerate([(110, 120), (690, 110), (400, 520)]):
        els += [E(f"cplate{k}", x, y + 50, 34, 9, "#9aa3ab"), R(f"candle{k}", x - 14, y - 10, x + 14, y + 50, "#efe6d2", r=4),
                L(f"wick{k}", [(x, y - 10), (x, y - 18)], "#222", 2), P(f"flame{k}", [(x, y - 42), (x + 8, y - 22), (x, y - 16), (x - 8, y - 22)], "#f5b041"),
                P(f"flamein{k}", [(x, y - 32), (x + 4, y - 22), (x, y - 19), (x - 4, y - 22)], "#fff3c4"), R(f"drip{k}", x + 6, y - 6, x + 11, y + 14, "#e3d9c3", r=2)]
    cards = [("A", "♥", 250, 260, "#c0392b"), ("7", "♠", 330, 250, "#1b1b1b"), ("K", "♦", 410, 255, "#c0392b"), ("Q", "♣", 490, 262, "#1b1b1b"), ("9", "♥", 570, 258, "#c0392b")]
    for k, (rank, suit, x, y, col) in enumerate(cards):
        els += [R(f"card{k}", x - 32, y - 46, x + 32, y + 46, "#f7f3ea", r=6, outline="#c9c0ac", w=1), T(f"rank{k}", x - 20, y - 32, rank, 14, col),
                T(f"rankb{k}", x + 20, y + 32, rank, 14, col)]
        if suit in ("♥", "♦"):
            els.append(P(f"suit{k}", [(x, y - 14), (x + 14, y), (x, y + 16), (x - 14, y)] if suit == "♦" else [(x - 13, y - 6), (x - 7, y - 13), (x, y - 7), (x + 7, y - 13), (x + 13, y - 6), (x, y + 13)], col))
        else:
            els += [E(f"suit{k}", x, y - 3, 11, 11, col), P(f"suitst{k}", [(x - 5, y + 14), (x + 5, y + 14), (x, y + 2)], col)]
    for k, (x, y, c) in enumerate([(150, 330, "#c0392b"), (210, 360, "#2e86c1"), (600, 380, "#27ae60"), (660, 350, "#1b1b1b")]):
        for n in range(4):
            els += [E(f"chip{k}_{n}", x, y - n * 7, 26, 9, c, outline="#f7f3ea", w=2)]
        els.append(E(f"chiptop{k}", x, y - 21, 13, 4, "#f7f3ea"))
    for k, (x, y, face) in enumerate([(300, 420, 5), (360, 430, 3)]):
        els.append(R(f"die{k}", x - 20, y - 20, x + 20, y + 20, "#f7f3ea", r=6, outline="#c9c0ac", w=1))
        spots = {5: [(-10, -10), (10, -10), (0, 0), (-10, 10), (10, 10)], 3: [(-10, -10), (0, 0), (10, 10)]}[face]
        for n, (dx, dy) in enumerate(spots):
            els.append(E(f"pip{k}_{n}", x + dx, y + dy, 3.5, 3.5, "#1b1b1b"))
    for k, (x, y) in enumerate([(560, 120), (240, 120)]):
        els += [P(f"wglass{k}", [(x - 22, y - 30), (x + 22, y - 30), (x + 14, y + 6), (x - 14, y + 6)], "#cfe3ea", outline="#9fb3ba", w=1),
                P(f"wine{k}", [(x - 18, y - 14), (x + 18, y - 14), (x + 13, y + 3), (x - 13, y + 3)], "#6b1d2f"),
                L(f"wstem{k}", [(x, y + 6), (x, y + 40)], "#bcd0d6", 3), E(f"wbase{k}", x, y + 41, 16, 4, "#bcd0d6")]
    els += [R("note", 655, 452, 745, 516, "#efe6d2", r=2), T("note1", 700, 472, "MESA 12", 11, "#5a4630"), T("note2", 700, 494, "21:30", 11, "#5a4630"),
            star("tstar", 470, 470, 7, "#f2d14b")]
    grain = []
    for k in range(10):
        y = 30 + k * 58
        grain.append(L(f"grain{k}", [(0, y), (200, y + 6), (420, y - 4), (620, y + 5), (800, y)], "#2c1d13", 1))
    els = els[:13] + grain + els[13:]
    for k in range(5):
        els.append(R(f"deck{k}", 40 + k * 2, 420 - k * 2, 100 + k * 2, 500 - k * 2, "#7a1d2a" if k == 4 else "#f7f3ea", r=5, outline="#c9c0ac", w=1))
    els += [L("deckpat1", [(52, 412), (100, 470)], "#a63a4a", 2), L("deckpat2", [(100, 412), (52, 470)], "#a63a4a", 2)]
    for k, (x, y, c) in enumerate([(440, 140, "#c0392b"), (612, 196, "#2e86c1"), (180, 470, "#27ae60"), (740, 300, "#1b1b1b"), (110, 250, "#c0392b")]):
        els += [E(f"loose{k}", x, y, 16, 16, c, outline="#f7f3ea", w=2), E(f"loosec{k}", x, y, 6, 6, "#f7f3ea")]
    for k in range(6):
        els.append(E(f"coinx{k}", 620 + k * 9, 560 - (k % 2) * 6, 8, 8, "#c9a24a", outline="#8a6a2a", w=1))
    els += [E("watch", 250, 540, 22, 22, "#d4ac0d"), E("watchface", 250, 540, 17, 17, "#f7f3ea"), L("watchh", [(250, 540), (250, 528)], "#1b1b1b", 2),
            L("watchm", [(250, 540), (260, 546)], "#1b1b1b", 2), R("matchbox", 470, 160, 520, 190, "#b03a2e", r=2), T("matchboxt", 495, 175, "FOX", 9, "#efe6d2"),
            R("whisky", 680, 230, 720, 280, "#cfe3ea", r=4, outline="#9fb3ba", w=1), R("whiskyliq", 683, 254, 717, 277, "#c9862b", r=3),
            R("ice1", 688, 250, 700, 262, "#e8f4f8", r=2), R("ice2", 701, 246, 712, 257, "#e8f4f8", r=2)]
    cands = {
        "crd-01": op_remove("suit1", "suitst1"), "crd-02": op_move(7, 0, "die0", "pip0_0", "pip0_1", "pip0_2", "pip0_3", "pip0_4"), "crd-03": op_recolor("chip0_3", 11),
        "crd-04": op_recolor("card0", 9), "crd-05": op_remove("candle1", "wick1", "flame1", "flamein1", "drip1"),
        "crd-06": op_add("loosec4", E("addchip", 180, 205, 14, 14, "#2e86c1", outline="#f7f3ea", w=2)), "crd-07": op_recolor("wine0", 12),
        "crd-08": op_recolor("note"), "crd-09": op_move(7, 0, "die1", "pip1_0", "pip1_1", "pip1_2"), "crd-10": op_recolor("loose3", 12),
        "crd-11": op_remove("cplate2"), "crd-12": op_recolor("deck4"), "crd-13": op_remove("watch", "watchface", "watchh", "watchm"), "crd-14": op_recolor("cplate1", 10),
        "crd-15": op_add("loosec4", E("addchip2", 190, 60, 14, 14, "#c0392b", outline="#f7f3ea", w=2)), "crd-16": op_remove("chip3_3", "chiptop3"),
        "crd-17": op_recolor("card2", 9), "crd-18": op_move(8, 0, "whisky", "whiskyliq", "ice1", "ice2"), "crd-19": op_recolor("matchbox", 11),
    }
    return els, cands


SCENES: dict[str, Callable[[], tuple[list, dict]]] = {"bar": scene_bar, "stage": scene_stage, "jukebox": scene_jukebox, "cards": scene_cards}
SCENE_NAMES = {"bar": "Barra con botellas y copas", "stage": "Escenario con banda y luces", "jukebox": "Rocola con discos de vinilo", "cards": "Mesa con velas y cartas"}


@lru_cache(maxsize=8)
def scene(scene_id: str) -> tuple[list, dict]:
    if scene_id not in SCENES:
        raise KeyError(scene_id)
    return SCENES[scene_id]()


# ---------------------------------------------------------------- zonas y eleccion
def _apply(els: list, ops: list) -> list:
    out = list(els)
    for op in ops:
        out = op(out)
    return out


def zone(scene_id: str, diff_id: str) -> dict:
    """Zona de una diferencia (centro y radio en el lienzo 800x600): la caja de lo que cambia."""
    els, cands = scene(scene_id)
    op = cands[diff_id]
    boxes = []
    touched = set(getattr(op, "touch", ()))
    for e in els:
        if e["id"] in touched:
            boxes.append(bbox(e))
    for e in op(list(els)):
        if e["id"] in touched or e in getattr(op, "adds", ()):
            boxes.append(bbox(e))
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    r = max(MIN_ZONE_R, min(MAX_ZONE_R, math.hypot(x1 - x0, y1 - y0) / 2 + 6))
    return {"id": diff_id, "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "r": r}


def cell_of(z: dict) -> tuple[int, int]:
    return min(GRID - 1, int(z["cx"] / (W / GRID))), min(GRID - 1, int(z["cy"] / (H / GRID)))


def choose(scene_id: str, seed: int, count: int = 7) -> list[str]:
    """7 diferencias al azar con la semilla de la ronda: cada una en una zona distinta
    de la rejilla 3x3 y separadas entre si. Todos juegan lo mismo."""
    _, cands = scene(scene_id)
    ids = sorted(cands)
    rnd = random.Random(int(seed) ^ 0x5EED)
    for _attempt in range(200):
        rnd.shuffle(ids)
        picked: list[dict] = []
        for i in ids:
            z = zone(scene_id, i)
            if any(cell_of(z) == cell_of(p) for p in picked):
                continue
            if any(math.hypot(z["cx"] - p["cx"], z["cy"] - p["cy"]) < MIN_SEPARATION for p in picked):
                continue
            picked.append(z)
            if len(picked) == count:
                return [p["id"] for p in picked]
    raise ValueError(f"la escena {scene_id} no tiene {count} diferencias separadas")


def pick_scene(active: list[str], seed: int) -> str:
    pool = sorted(s for s in active if s in SCENES) or sorted(SCENES)
    return random.Random(int(seed) ^ 0xC0FFEE).choice(pool)


def hit(scene_id: str, diff_ids: list[str], found: list[str], x: float, y: float) -> Optional[dict]:
    """Toque normalizado (0-1) -> la diferencia no encontrada cuya zona lo contiene."""
    px, py = float(x) * W, float(y) * H
    best = None
    for d in diff_ids:
        if d in found:
            continue
        z = zone(scene_id, d)
        dist = math.hypot(px - z["cx"], py - z["cy"])
        if dist <= z["r"] + HIT_TOLERANCE and (best is None or dist < best[0]):
            best = (dist, z)
    return best[1] if best else None


def public_zone(z: dict) -> dict:
    """Zona normalizada (0-1) para dibujar el circulo cuando ya se acerto."""
    return {"id": z["id"], "x": round(z["cx"] / W, 4), "y": round(z["cy"] / H, 4), "r": round(z["r"] / W, 4)}


# ---------------------------------------------------------------- dibujo
def _draw(els: list, out_w: int = OUT_W, out_h: int = OUT_H) -> Any:
    from PIL import Image, ImageDraw

    k = out_w * SS / W
    img = Image.new("RGB", (out_w * SS, out_h * SS), "#000000")
    d = ImageDraw.Draw(img, "RGBA")

    def col(c):
        c = _full(c)
        return tuple(int(c[i:i + 2], 16) for i in range(0, len(c), 2))

    for e in els:
        fill = col(e["fill"]) if e.get("fill") else None
        outline = col(e["outline"]) if e.get("outline") else None
        w = max(1, int(round(e.get("w", 0) * k))) if e.get("w") else 0
        if e["t"] == "rect":
            box = [v * k for v in e["box"]]
            if e.get("r"):
                d.rounded_rectangle(box, radius=e["r"] * k, fill=fill, outline=outline, width=w)
            else:
                d.rectangle(box, fill=fill, outline=outline, width=w)
        elif e["t"] == "ell":
            d.ellipse([v * k for v in e["box"]], fill=fill, outline=outline, width=w)
        elif e["t"] == "poly":
            d.polygon([(x * k, y * k) for x, y in e["pts"]], fill=fill, outline=outline, width=w or 1)
        elif e["t"] == "line":
            d.line([(x * k, y * k) for x, y in e["pts"]], fill=fill, width=max(1, int(round(e["w"] * k))), joint="curve")
        else:
            d.text((e["xy"][0] * k, e["xy"][1] * k), e["s"], fill=fill, font=_font(e["size"] * k), anchor="mm")
    return img.resize((out_w, out_h), Image.LANCZOS)


def render(scene_id: str, diff_ids: tuple = (), out_w: int = OUT_W, out_h: int = OUT_H) -> Any:
    els, cands = scene(scene_id)
    return _draw(_apply(els, [cands[d] for d in diff_ids]), out_w, out_h)


@lru_cache(maxsize=24)
def png(scene_id: str, diff_ids: tuple = ()) -> bytes:
    """PNG de la escena (A = sin cambios, B = con las 7 diferencias). Cache corta en memoria."""
    buf = io.BytesIO()
    render(scene_id, tuple(diff_ids)).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def element_count(scene_id: str) -> int:
    return len(scene(scene_id)[0])


# ---------------------------------------------------------------- medicion (pruebas y control de calidad)
def diff_stats(scene_id: str, diff_id: str, base: Any = None) -> dict:
    """Mide una diferencia comparando pixeles de A y B: area cambiada (% de la imagen),
    diferencia de color (percentil 90 de Delta E de los pixeles cambiados), pixeles
    cambiados FUERA de su zona y, si es un cambio de tono, su Delta E exacto."""
    from PIL import ImageChops

    a = base if base is not None else render(scene_id)
    b = render(scene_id, (diff_id,))
    diff = ImageChops.difference(a, b).convert("L")
    k = OUT_W / W
    z = zone(scene_id, diff_id)
    pa, pb, pd = a.load(), b.load(), diff.load()
    box = diff.getbbox()
    des, outside = [], 0
    if box:
        for y in range(box[1], box[3]):
            for x in range(box[0], box[2]):
                if pd[x, y] == 0:
                    continue
                la, lb = rgb_to_lab(pa[x, y]), rgb_to_lab(pb[x, y])
                de = math.sqrt(sum((u - v) ** 2 for u, v in zip(la, lb)))
                if de <= 2.0:
                    continue
                des.append(de)
                if math.hypot(x / k - z["cx"], y / k - z["cy"]) > z["r"] + 4:
                    outside += 1
    des.sort()
    els, cands = scene(scene_id)
    rec = getattr(cands[diff_id], "recolor", None)
    recolor_de = None
    if rec:
        fill = next(e for e in els if e["id"] == rec)["fill"]
        recolor_de = round(delta_e(fill, near_tone(fill, 11.0)), 2)
    return {"area_pct": len(des) / (OUT_W * OUT_H) * 100, "p90_de": des[int(len(des) * 0.9)] if des else 0.0, "outside": outside,
            "zone_pct": math.pi * z["r"] ** 2 / (W * H) * 100, "recolor_de": recolor_de, "cell": cell_of(z)}
