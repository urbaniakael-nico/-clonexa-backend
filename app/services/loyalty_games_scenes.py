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
    l, t, r, b = _font(el["size"]).getbbox(el["s"], anchor=el.get("anchor", "mm"))
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


# ================================================================ escenas v2: Bar y Concierto
# Personas armadas por partes con atributos al azar (semilla fija por escena para la
# imagen base). Diferencias CLARAS: gorra o sombrero, gafas, camisa de otro color
# (Delta E >= 35), brazo arriba con celular, pelo de otro color o forma, objeto que
# aparece o desaparece y letra cambiada en un letrero. Nunca solo un tono parecido.
SKINS = ["#f1c27d", "#e0ac69", "#c68642", "#8d5524", "#ffdbac", "#a1665e"]
HAIRS = ["#1b1b1b", "#4a2e16", "#d9b24c", "#a0391e", "#9a9a9a", "#2b1d12"]
SHIRTS = ["#c0392b", "#27ae60", "#2e6fd8", "#f1c40f", "#e67e22", "#8e44ad", "#ecf0f1", "#16a085", "#e84393", "#34495e"]
# Cambio claro de camisa: rojo<->verde, azul<->amarillo, etc. (Delta E >= 35, se prueba).
SHIRT_SWAP = {"#c0392b": "#27ae60", "#27ae60": "#c0392b", "#2e6fd8": "#f1c40f", "#f1c40f": "#2e6fd8", "#e67e22": "#2e6fd8",
              "#8e44ad": "#f1c40f", "#ecf0f1": "#c0392b", "#16a085": "#e84393", "#e84393": "#16a085", "#34495e": "#e67e22"}
HAIR_SWAP = {"#1b1b1b": "#d9b24c", "#4a2e16": "#d9b24c", "#d9b24c": "#1b1b1b", "#a0391e": "#1b1b1b", "#9a9a9a": "#a0391e", "#2b1d12": "#d9b24c"}
NIGHT = "#120e1a"


def shade(color: str, t: float, to: str = NIGHT) -> str:
    """Mezcla un color con la noche del fondo (profundidad: atras mas oscuro)."""
    a, b = _hex(color), _hex(to)
    return _to_hex(tuple(x + (y - x) * t for x, y in zip(a, b)))


def T2(i, x, y, s, size, fill, anchor="mm"):  # noqa: N802
    e = T(i, x, y, s, size, fill)
    e["anchor"] = anchor
    return e


def person(pid: str, x: float, y: float, s: float, a: dict, depth: float = 0.0) -> list:
    """Una persona (hombros en y). a: skin, hair, hair_style (short/long/bun/curly/bald), shirt,
    hat (None/cap/hat), glasses, arm (down/phone/drink), back (de espaldas)."""
    c = lambda col: shade(col, depth) if depth else col  # noqa: E731
    out = []
    hx, hy = x, y - 10 * s
    style = a.get("hair_style", "short")
    if style == "long" and a.get("hair_style") != "bald":
        out.append(R(f"{pid}.hairback", hx - 9.5 * s, hy - 7 * s, hx + 9.5 * s, y + 9 * s, c(a["hair"]), r=4 * s))
    out.append(R(f"{pid}.body", x - 13 * s, y, x + 13 * s, y + 34 * s, c(a["shirt"]), r=7 * s))
    out.append(R(f"{pid}.neck", x - 3 * s, y - 3 * s, x + 3 * s, y + 2 * s, c(a["skin"])))
    out.append(E(f"{pid}.head", hx, hy, 8 * s, 9 * s, c(a["skin"])))
    if a.get("back"):
        if style != "bald":
            out.append(E(f"{pid}.hair", hx, hy - 1 * s, 8.4 * s, 8.6 * s, c(a["hair"])))
    else:
        if style in ("short", "long", "bun"):
            out.append(P(f"{pid}.hair", [(hx - 8.5 * s, hy - 1 * s), (hx - 7 * s, hy - 8 * s), (hx, hy - 10.5 * s), (hx + 7 * s, hy - 8 * s), (hx + 8.5 * s, hy - 1 * s),
                                          (hx + 5 * s, hy - 5 * s), (hx - 5 * s, hy - 5 * s)], c(a["hair"])))
        elif style == "curly":
            for k, (dx, dy) in enumerate([(-7, -4), (-4, -9), (1, -10), (6, -8), (8, -3)]):
                out.append(E(f"{pid}.hair{k}", hx + dx * s, hy + dy * s, 3.6 * s, 3.6 * s, c(a["hair"])))
        if style == "bun":
            out.append(E(f"{pid}.bun", hx, hy - 12 * s, 3.8 * s, 3.4 * s, c(a["hair"])))
        out += [E(f"{pid}.eyeL", hx - 3 * s, hy + 0.5 * s, 1 * s, 1.1 * s, c("#1b1b1b")), E(f"{pid}.eyeR", hx + 3 * s, hy + 0.5 * s, 1 * s, 1.1 * s, c("#1b1b1b")),
                L(f"{pid}.mouth", [(hx - 2 * s, hy + 4.5 * s), (hx + 2 * s, hy + 4.5 * s)], c("#6b2f2f"), max(1, 0.8 * s))]
        if a.get("glasses"):
            out += [E(f"{pid}.glassL", hx - 3.3 * s, hy + 0.5 * s, 2.9 * s, 2.4 * s, c("#111111")), E(f"{pid}.glassR", hx + 3.3 * s, hy + 0.5 * s, 2.9 * s, 2.4 * s, c("#111111")),
                    L(f"{pid}.glassB", [(hx - 0.6 * s, hy), (hx + 0.6 * s, hy)], c("#111111"), max(1, 0.8 * s))]
    hat = a.get("hat")
    if hat == "cap":
        out += [E(f"{pid}.cap", hx, hy - 6 * s, 9 * s, 6.5 * s, c(a.get("hat_color", "#1f2a44"))),
                R(f"{pid}.capbrim", hx - 2 * s, hy - 6 * s, hx + 14 * s, hy - 3 * s, c(a.get("hat_color", "#1f2a44")), r=1.5 * s)]
    elif hat == "hat":
        out += [R(f"{pid}.hatcrown", hx - 9 * s, hy - 22 * s, hx + 9 * s, hy - 6 * s, c(a.get("hat_color", "#3b2a1a")), r=2.5 * s),
                R(f"{pid}.hatband", hx - 9 * s, hy - 10 * s, hx + 9 * s, hy - 7.5 * s, c("#c9a24a")),
                E(f"{pid}.hatbrim", hx, hy - 6 * s, 19 * s, 4.2 * s, c(a.get("hat_color", "#3b2a1a")))]
    arm = a.get("arm", "down")
    out.append(L(f"{pid}.armL", [(x - 12 * s, y + 4 * s), (x - 15 * s, y + 28 * s)], c(a["shirt"]), 5 * s))
    if arm == "phone":
        out += [L(f"{pid}.armR", [(x + 11 * s, y + 4 * s), (x + 17 * s, y - 22 * s)], c(a["shirt"]), 5 * s),
                E(f"{pid}.hand", x + 17 * s, y - 23 * s, 2.8 * s, 2.8 * s, c(a["skin"])),
                R(f"{pid}.phone", x + 13 * s, y - 37 * s, x + 21 * s, y - 24 * s, c("#111111"), r=1.4 * s),
                R(f"{pid}.screen", x + 14 * s, y - 36 * s, x + 20 * s, y - 25.5 * s, "#cfe8ff" if depth < 0.5 else shade("#cfe8ff", depth * 0.6), r=1 * s)]
    else:
        out += [L(f"{pid}.armR", [(x + 12 * s, y + 4 * s), (x + 15 * s, y + 28 * s)], c(a["shirt"]), 5 * s),
                E(f"{pid}.hand", x + 15 * s, y + 29 * s, 2.8 * s, 2.8 * s, c(a["skin"]))]
        if arm == "drink":
            out += [R(f"{pid}.drink", x + 13 * s, y + 18 * s, x + 21 * s, y + 31 * s, c("#e3b23c"), r=1 * s),
                    R(f"{pid}.foam", x + 13 * s, y + 17 * s, x + 21 * s, y + 20 * s, c("#f7f3ea"), r=1 * s)]
    return out


def random_person(rnd: random.Random, back: bool = False) -> dict:
    return {"skin": rnd.choice(SKINS), "hair": rnd.choice(HAIRS), "hair_style": rnd.choice(["short", "short", "long", "bun", "curly", "bald"]),
            "shirt": rnd.choice(SHIRTS), "hat": rnd.choice([None, None, None, "cap", "hat"]), "hat_color": rnd.choice(["#1f2a44", "#3b2a1a", "#6b1d2f", "#1b1b1b"]),
            "glasses": rnd.random() < 0.25, "arm": rnd.choice(["down", "down", "down", "phone", "drink"]), "back": back}


def tag(op, kind: str, target: str, people: bool = False, color: Optional[tuple] = None):
    op.kind, op.target, op.people = kind, target, people
    if color:
        op.color = color
    return op


def op_person(people: dict, pid: str, kind: str, **change):
    """Cambia atributos de UNA persona: se vuelve a dibujar con los atributos nuevos.
    La zona sale solo de las partes que cambian."""
    x, y, s, a, depth = people[pid]
    new_attrs = {**a, **change}
    old = {e["id"]: e for e in person(pid, x, y, s, a, depth)}
    new = {e["id"]: e for e in person(pid, x, y, s, new_attrs, depth)}

    def run(els):
        idx = [k for k, e in enumerate(els) if e["id"].startswith(pid + ".")]
        if not idx:
            return els
        return els[: idx[0]] + list(new.values()) + [e for e in els[idx[0]:] if not e["id"].startswith(pid + ".")]
    run.touch = tuple(i for i in old if i not in new or old[i] != new[i])
    run.adds = tuple(e for i, e in new.items() if i not in old or old[i] != e)
    color = None
    if kind == "shirt":
        color = (shade(a["shirt"], depth), shade(new_attrs["shirt"], depth))
    if kind == "hair" and "hair" in change:
        color = (shade(a["hair"], depth), shade(new_attrs["hair"], depth))
    return tag(run, kind, pid, True, color)


def _bottle(pid, x, base, h, col, cap):
    return [R(f"{pid}.body", x - 9, base - h, x + 9, base, col, r=4), R(f"{pid}.neck", x - 3, base - h - 14, x + 3, base - h + 2, col),
            R(f"{pid}.cap", x - 4, base - h - 18, x + 4, base - h - 13, cap, r=1), R(f"{pid}.label", x - 7, base - h * 0.6, x + 7, base - h * 0.6 + 12, "#efe6d2", r=1)]


def scene_pub() -> tuple[list, dict]:
    """Bar: estanteria iluminada, barman, clientes en la barra, mesas con gente y velas, lamparas y neon."""
    rnd = random.Random(2026)
    els = [R("bg", 0, 0, W, H, "#1a1410")] + _wood("wall", 0, 0, W, 260, 12, "#2a1f17", "#251b14")
    els += [R("shelfglow", 40, 52, 560, 196, "#f5b04122", r=8)]
    people: dict = {}
    cands: dict = {}
    # neon y lamparas
    els += [R("neonbox", 290, 8, 510, 44, "#1a1320", r=8, outline="#3a2a44", w=2), R("neonglow", 296, 14, 504, 38, "#ff6fb033", r=6),
            T("neon", 400, 26, "TTM BAR", 26, "#ff8fc4")]
    for k, x in enumerate((90, 220, 600, 700)):
        els += [L(f"lamp{k}.cord", [(x, 0), (x, 40)], "#3a3a3a", 2), P(f"lamp{k}.shade", [(x - 16, 56), (x + 16, 56), (x + 9, 40), (x - 9, 40)], "#b07d3a"),
                E(f"lamp{k}.bulb", x, 58, 6, 4, "#fff3c4"), E(f"lamp{k}.glow", x, 80, 34, 22, "#fff3c418")]
    # estanteria con botellas
    cols = ["#2f6b3a", "#6b2f2f", "#3a4f7a", "#8a6a2a", "#5b3a6b", "#2a6b66", "#7a4a2a", "#4a5a2a"]
    for sidx, base in enumerate((96, 146, 196)):
        els.append(R(f"shelf{sidx}", 46, base, 556, base + 6, "#6b4a2b", r=2))
        for b in range(11):
            bx = 66 + b * 46 + rnd.randint(-3, 3)
            els += _bottle(f"bt{sidx}_{b}", bx, base, rnd.choice((26, 30, 34)), cols[(b + sidx * 3) % len(cols)], "#c9a24a" if b % 2 else "#9aa3ab")
    # barman detras de la barra
    bar_a = {"skin": "#c68642", "hair": "#1b1b1b", "hair_style": "short", "shirt": "#ecf0f1", "hat": None, "glasses": False, "arm": "down", "back": False}
    people["barman"] = (300, 182, 1.6, bar_a, 0.0)
    els += person("barman", *people["barman"][:4])
    els += [R("apron", 284, 205, 316, 238, "#2b2b2b", r=3), R("shaker", 324, 196, 336, 222, "#c9c9d6", r=4), R("shakercap", 326, 190, 334, 198, "#aeb3bd", r=2),
            R("rag", 262, 214, 276, 232, "#c0392b", r=2)]
    # barra
    els += [R("counter", 26, 226, 590, 242, "#6b4428"), R("counterlip", 26, 240, 590, 246, "#3e2817")] + _wood("cfront", 26, 246, 590, 300, 9, "#3a2617", "#33221a")
    for k, x in enumerate((80, 210, 400, 520)):  # objetos sobre la barra
        els += [R(f"cglass{k}", x - 6, 206, x + 6, 226, "#cfe3ea", r=2), R(f"cglass{k}.liq", x - 5, 214, x + 5, 225, ["#e3b23c", "#c06c84", "#7fb069", "#e07a5f"][k], r=1)]
    els += [R("beerc", 455, 204, 469, 226, "#e3b23c", r=2), R("beerc.foam", 455, 201, 469, 207, "#f7f3ea", r=2),
            R("tap", 548, 186, 588, 226, "#9aa3ab", r=4), R("tap.top", 544, 180, 592, 190, "#c9c9d6", r=3),
            R("tap.h1", 552, 168, 558, 186, "#b03a2e", r=2), R("tap.h2", 565, 166, 571, 186, "#2e86c1", r=2), R("tap.h3", 578, 168, 584, 186, "#e3b23c", r=2)]
    # clientes en butacos (de espaldas)
    for k in range(7):
        x = 70 + k * 76
        pid = f"cust{k}"
        a = random_person(rnd, back=True)
        a["arm"] = "down"
        people[pid] = (x, 232, 1.45, a, 0.0)
        els += person(pid, *people[pid][:4])
        els += [E(f"stool{k}", x, 288, 18, 5, "#8a2f2f"), L(f"stool{k}.leg1", [(x - 10, 290), (x - 14, 330)], "#9aa3ab", 3), L(f"stool{k}.leg2", [(x + 10, 290), (x + 14, 330)], "#9aa3ab", 3)]
    # gente de pie a la derecha (2 filas)
    for k in range(12):
        row, idx = (0, k) if k < 6 else (1, k - 6)
        x = 618 + idx * 34 + (17 if row else 0)
        y = 150 if row == 0 else 196
        s = 1.05 if row == 0 else 1.3
        pid = f"stand{k}"
        a = random_person(rnd)
        people[pid] = (x, y, s, a, 0.25 if row == 0 else 0.0)
        els += person(pid, *people[pid])
    # mesas con gente, velas, copas, cervezas y platos
    tables = [(110, 420, 4), (330, 395, 3), (560, 430, 4), (220, 545, 3), (470, 548, 4)]
    for t, (tx, ty, n) in enumerate(tables):
        seats = [(-34, -34), (34, -34), (-66, -6), (66, -6)][:n]
        for k, (dx, dy) in enumerate(seats):
            pid = f"t{t}p{k}"
            a = random_person(rnd)
            people[pid] = (tx + dx, ty + dy, 1.75, a, 0.0)
            els += person(pid, *people[pid][:4])
        els += [E(f"table{t}", tx, ty + 12, 62, 20, "#5a3a22"), E(f"candle{t}.glow", tx, ty - 8, 26, 20, "#ffb34740"), E(f"table{t}.top", tx, ty + 9, 60, 17, "#6b4428"),
                R(f"candle{t}", tx - 4, ty - 6, tx + 4, ty + 8, "#efe6d2", r=2), P(f"candle{t}.flame", [(tx, ty - 18), (tx + 4, ty - 8), (tx, ty - 5), (tx - 4, ty - 8)], "#f5b041"),
                E(f"plate{t}", tx - 30, ty + 10, 14, 5, "#e8e2d4"), E(f"plate{t}.food", tx - 30, ty + 8, 7, 3, "#b5651d"),
                R(f"beer{t}", tx + 22, ty - 6, tx + 32, ty + 10, "#e3b23c", r=2), R(f"beer{t}.foam", tx + 22, ty - 9, tx + 32, ty - 4, "#f7f3ea", r=2),
                P(f"wine{t}", [(tx + 38, ty - 8), (tx + 50, ty - 8), (tx + 44, ty + 2)], "#6b1d2f"), L(f"wine{t}.stem", [(tx + 44, ty + 2), (tx + 44, ty + 10)], "#bcd0d6", 2)]
    # candidatas: objetos y letreros
    bottles = lambda *ids: tuple(f"{b}.{p}" for b in ids for p in ("body", "neck", "cap", "label"))  # noqa: E731
    cands["pub-o01"] = tag(op_text("neon", "TMM BAR"), "text", "neon")
    cands["pub-o02"] = tag(op_remove(*bottles("bt0_1", "bt0_2")), "object", "bt0_1")
    cands["pub-o03"] = tag(op_remove(*bottles("bt1_8", "bt1_9")), "object", "bt1_8")
    cands["pub-o04"] = tag(op_remove(*bottles("bt2_5", "bt2_6")), "object", "bt2_5")
    cands["pub-o05"] = tag(op_remove("lamp0.cord", "lamp0.shade", "lamp0.bulb", "lamp0.glow"), "object", "lamp0")
    cands["pub-o06"] = tag(op_remove("lamp3.cord", "lamp3.shade", "lamp3.bulb", "lamp3.glow"), "object", "lamp3")
    cands["pub-o07"] = tag(op_remove("tap", "tap.top", "tap.h1", "tap.h2", "tap.h3"), "object", "tap")
    for t in range(5):
        cands[f"pub-o{8 + t:02d}"] = tag(op_remove(f"candle{t}", f"candle{t}.flame", f"candle{t}.glow"), "object", f"candle{t}")
    cands["pub-o13"] = tag(op_add("table4.top", R("bottle_new", 448, 512, 464, 556, "#2f6b3a", r=4), R("bottle_new.neck", 452, 496, 460, 514, "#2f6b3a"),
                                  R("bottle_new.label", 449, 528, 463, 542, "#efe6d2"), P("glass_new", [(470, 526), (488, 526), (479, 540)], "#cfe3ea"),
                                  L("glass_new.stem", [(479, 540), (479, 552)], "#cfe3ea", 2)), "object", "table4")
    cands["pub-o14"] = tag(op_remove(*bottles("bt0_7", "bt0_8")), "object", "bt0_7")
    # candidatas: personas (cambios claros)
    for pid in ("t0p0", "t1p1", "t2p2", "t3p0", "t4p1", "t0p3", "stand10", "cust1", "cust4", "t2p0", "t4p3", "cust6", "t1p0"):
        x, y, s, a, depth = people[pid]
        n = len([c for c in cands if c.startswith("pub-p")]) + 1
        if pid.startswith("cust"):
            cands[f"pub-p{n:02d}"] = op_person(people, pid, "shirt", shirt=SHIRT_SWAP[a["shirt"]])
        elif n % 3 == 1:
            cands[f"pub-p{n:02d}"] = op_person(people, pid, "shirt", shirt=SHIRT_SWAP[a["shirt"]])
        elif n % 3 == 2:
            cands[f"pub-p{n:02d}"] = op_person(people, pid, "arm", arm="down" if a["arm"] == "phone" else "phone")
        else:
            cands[f"pub-p{n:02d}"] = op_person(people, pid, "hat", hat=None if a.get("hat") == "hat" else "hat")
    return els, cands


def scene_concert() -> tuple[list, dict]:
    """Concierto: truss y focos con haces de luz, banda de 3, amplificadores, letrero y publico en 5 filas."""
    rnd = random.Random(1975)
    els = [R("bg", 0, 0, W, H, "#0d0a16"), R("backdrop", 0, 40, W, 320, "#151024")]
    cands: dict = {}
    people: dict = {}
    els += [R("truss", 0, 10, W, 26, "#3a3a46")] + [L(f"tr{k}", [(k * 40, 10), (k * 40 + 20, 26)], "#55556a", 2) for k in range(21)]
    gels = ["#ff4d6d", "#ffd166", "#4cc9f0", "#b388eb", "#06d6a0", "#ff9f1c", "#f72585", "#4361ee"]
    for k in range(8):
        x = 55 + k * 98
        els += [R(f"spot{k}", x - 14, 26, x + 14, 48, "#24242e", r=4), E(f"spot{k}.gel", x, 50, 11, 6, gels[k]),
                P(f"spot{k}.beam", [(x - 9, 54), (x + 9, 54), (x + 60, 318), (x - 60, 318)], gels[k] + "2c")]
    els += [R("sign", 300, 58, 500, 96, "#1d1030", r=6, outline="#ff4d6d", w=2), T("signt", 400, 77, "ROCK NIGHT", 24, "#ffd166")]
    els += [R("stage", 0, 300, W, 330, "#2a2234"), R("stagefront", 0, 326, W, 334, "#3a3046")]
    for k, x in enumerate((40, 660)):
        els += [R(f"amp{k}", x, 196, x + 100, 300, "#1c1c24", r=6, outline="#3a3a46", w=2), R(f"amp{k}.grill", x + 8, 226, x + 92, 294, "#2a2a34", r=4),
                T(f"amp{k}.logo", x + 50, 211, "VOLT", 30, "#c9c9d6")]
    # bateria
    els += [E("kick", 400, 268, 34, 34, "#e8e2d4", outline="#b03a2e", w=5), T("kicklogo", 400, 268, "TTM", 30, "#b03a2e"),
            E("tom1", 368, 222, 17, 9, "#b03a2e"), E("tom2", 432, 222, 17, 9, "#b03a2e"), E("snare", 352, 252, 18, 7, "#c9c9d6"),
            E("crash", 335, 192, 24, 5, "#d4ac0d"), L("crash.stand", [(335, 197), (335, 300)], "#9aa3ab", 2),
            E("ride", 470, 198, 26, 5, "#d4ac0d"), L("ride.stand", [(470, 203), (470, 300)], "#9aa3ab", 2), E("hihat", 320, 236, 16, 4, "#d4ac0d")]
    band = {"band_g": (220, 196, 1.9, {"skin": "#e0ac69", "hair": "#1b1b1b", "hair_style": "long", "shirt": "#1b1b1b", "hat": None, "glasses": False, "arm": "down"}),
            "band_d": (400, 190, 1.5, {"skin": "#8d5524", "hair": "#1b1b1b", "hair_style": "curly", "shirt": "#c0392b", "hat": None, "glasses": True, "arm": "down"}),
            "band_s": (585, 196, 1.9, {"skin": "#ffdbac", "hair": "#d9b24c", "hair_style": "short", "shirt": "#2e6fd8", "hat": None, "glasses": False, "arm": "down"})}
    for pid, (x, y, s, a) in band.items():
        if pid == "band_d":
            continue
        people[pid] = (x, y, s, a, 0.0)
        els += person(pid, x, y, s, a)
    people["band_d"] = (*band["band_d"], 0.0)
    kick_at = els.index(next(e for e in els if e["id"] == "kick"))
    els = els[:kick_at] + person("band_d", *band["band_d"]) + els[kick_at:]
    els += [P("guitar", [(196, 238), (238, 226), (244, 252), (204, 264)], "#b03a2e"), L("guitar.neck", [(240, 236), (292, 210)], "#6e4b2a", 4),
            P("bass", [(560, 240), (602, 230), (608, 256), (566, 266)], "#2e86c1"), L("bass.neck", [(562, 248), (512, 216)], "#6e4b2a", 4),
            L("mic", [(626, 300), (626, 178)], "#9aa3ab", 3), E("mic.head", 622, 176, 5, 6, "#c9c9d6"),
            P("wedge0", [(160, 330), (230, 330), (222, 312), (168, 312)], "#4a4a5c"), P("wedge1", [(560, 330), (630, 330), (622, 312), (568, 312)], "#4a4a5c"),
            R("setlist", 470, 300, 516, 330, "#efe6d2", r=2), L("setlist.l1", [(476, 308), (508, 308)], "#555", 2), L("setlist.l2", [(476, 316), (504, 316)], "#555", 2),
            L("ball.string", [(700, 26), (700, 62)], "#9aa3ab", 2), E("ball", 700, 80, 19, 19, "#c9c9d6"), E("ball.shine", 694, 74, 6, 5, "#ffffff"),
            R("bucket", 52, 162, 92, 196, "#9aa3ab", r=4), R("bucket.b1", 58, 146, 66, 166, "#2f6b3a", r=2), R("bucket.b2", 70, 142, 78, 166, "#6b2f2f", r=2),
            R("bucket.b3", 81, 148, 89, 166, "#2f6b3a", r=2)]
    # publico: 5 filas con profundidad (atras mas pequenas y oscuras)
    rows = [(342, 0.62, 25, 0.62), (378, 0.8, 23, 0.46), (420, 1.0, 21, 0.3), (470, 1.25, 18, 0.14), (532, 1.7, 14, 0.0)]
    for r_i, (y, s, n, depth) in enumerate(rows):
        span = W + 40
        for k in range(n):
            x = -20 + (k + 0.5) * span / n + (rnd.uniform(-6, 6) if r_i < 4 else 0)
            pid = f"r{r_i}p{k}"
            a = random_person(rnd)
            people[pid] = (x, y + rnd.uniform(-4, 4), s, a, depth)
            els += person(pid, *people[pid])
    # candidatas: objetos y letreros
    cands["con-o01"] = tag(op_text("kicklogo", "TMM"), "text", "kicklogo")
    cands["con-o02"] = tag(op_text("signt", "ROCK MIGHT"), "text", "signt")
    cands["con-o03"] = tag(op_remove("ball.string", "ball", "ball.shine"), "object", "ball")
    cands["con-o04"] = tag(op_remove("bucket", "bucket.b1", "bucket.b2", "bucket.b3"), "object", "bucket")
    cands["con-o05"] = tag(op_remove("setlist", "setlist.l1", "setlist.l2"), "object", "setlist")
    cands["con-o06"] = tag(op_remove("crash", "crash.stand"), "object", "crash")
    cands["con-o07"] = tag(op_remove("ride", "ride.stand"), "object", "ride")
    cands["con-o08"] = tag(op_remove("mic", "mic.head"), "object", "mic")
    cands["con-o10"] = tag(op_text("amp1.logo", "VOIT"), "text", "amp1.logo")
    cands["con-o12"] = tag(op_text("amp0.logo", "VALT"), "text", "amp0.logo")
    def recolor_strong(ident, new):  # noqa: E306
        old = next(e["fill"] for e in els if e["id"] == ident)

        def run(items):
            return [{**e, "fill": new} if e["id"] == ident else e for e in items]
        run.touch = (ident,)
        return tag(run, "color", ident, False, (old, new))
    cands["con-o13"] = recolor_strong("guitar", "#2e86c1")
    cands["con-o14"] = recolor_strong("bass", "#f1c40f")
    # candidatas: personas (banda y publico de las filas de adelante)
    plist = ["band_g", "band_s", "r4p1", "r4p4", "r4p7", "r4p10", "r4p12", "r4p2", "r3p8", "r4p5", "r3p3", "r3p14"]
    for n, pid in enumerate(plist, 1):
        x, y, s, a, depth = people[pid]
        if pid.startswith("r3"):
            cands[f"con-p{n:02d}"] = op_person(people, pid, "shirt", shirt=SHIRT_SWAP[a["shirt"]])
        elif pid == "band_g":
            cands[f"con-p{n:02d}"] = op_person(people, pid, "hair", hair=HAIR_SWAP[a["hair"]])
        elif pid == "band_s":
            cands[f"con-p{n:02d}"] = op_person(people, pid, "hat", hat="hat")
        elif n % 3 == 0:
            cands[f"con-p{n:02d}"] = op_person(people, pid, "shirt", shirt=SHIRT_SWAP[a["shirt"]])
        elif n % 3 == 1:
            cands[f"con-p{n:02d}"] = op_person(people, pid, "arm", arm="down" if a["arm"] == "phone" else "phone")
        else:
            cands[f"con-p{n:02d}"] = op_person(people, pid, "hat", hat=None if a.get("hat") == "hat" else "hat")
    return els, cands


def people_count(scene_id: str) -> int:
    return len({e["id"].split(".")[0] for e in scene(scene_id)[0] if e["id"].endswith(".head")})


# Todas las escenas se pueden DIBUJAR (una ronda abierta antes de un cambio termina con su escena),
# pero solo las de OFFERED se ofrecen al abrir una ronda nueva.
SCENES: dict[str, Callable[[], tuple[list, dict]]] = {"bar": scene_bar, "stage": scene_stage, "jukebox": scene_jukebox, "cards": scene_cards,
                                                      "pub": scene_pub, "concert": scene_concert}
LEGACY_NAMES = {"bar": "Barra con botellas y copas", "stage": "Escenario con banda y luces", "jukebox": "Rocola con discos de vinilo", "cards": "Mesa con velas y cartas"}
OFFERED = {"pub": "Bar", "concert": "Concierto"}
SCENE_NAMES = OFFERED
DEFAULT_SCENE = "pub"
# Escenas v2: zona ajustada a lo que cambia (radio de acierto justo entre la multitud).
META = {"pub": {"v": 2, "min_r": 18, "max_r": 110}, "concert": {"v": 2, "min_r": 18, "max_r": 110}}
MAX_PEOPLE = 4
MIN_SEPARATION_V2 = 70


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
    meta = META.get(scene_id, {})
    r = max(meta.get("min_r", MIN_ZONE_R), min(meta.get("max_r", MAX_ZONE_R), math.hypot(x1 - x0, y1 - y0) / 2 + 6))
    return {"id": diff_id, "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "r": r}


def cell_of(z: dict) -> tuple[int, int]:
    return min(GRID - 1, int(z["cx"] / (W / GRID))), min(GRID - 1, int(z["cy"] / (H / GRID)))


def choose(scene_id: str, seed: int, count: int = 7) -> list[str]:
    """7 diferencias al azar con la semilla de la ronda (iguales para todos en la ronda)."""
    if META.get(scene_id, {}).get("v") == 2:
        return choose_v2(scene_id, seed, count)
    return choose_legacy(scene_id, seed, count)


def choose_v2(scene_id: str, seed: int, count: int = 7) -> list[str]:
    """Escenas v2: maximo 4 en personas; nunca 2 en la misma persona u objeto; repartidas
    en zonas distintas de la rejilla 3x3 (1 por celda si se puede) y separadas."""
    _, cands = scene(scene_id)
    ids = sorted(cands)
    rnd = random.Random(int(seed) ^ 0x7D1FF)
    zones = {i: zone(scene_id, i) for i in ids}
    for per_cell in (1, 2):
        for _attempt in range(300):
            rnd.shuffle(ids)
            picked: list[str] = []
            for i in ids:
                op, z = cands[i], zones[i]
                if sum(1 for p in picked if cands[p].people) >= MAX_PEOPLE and op.people:
                    continue
                if any(cands[p].target == op.target for p in picked):
                    continue
                if sum(1 for p in picked if cell_of(zones[p]) == cell_of(z)) >= per_cell:
                    continue
                if any(math.hypot(z["cx"] - zones[p]["cx"], z["cy"] - zones[p]["cy"]) < MIN_SEPARATION_V2 for p in picked):
                    continue
                picked.append(i)
                if len(picked) == count:
                    return picked
    raise ValueError(f"la escena {scene_id} no tiene {count} diferencias separadas")


def choose_legacy(scene_id: str, seed: int, count: int = 7) -> list[str]:
    """Escenas de antes: cada una en una zona distinta de la rejilla 3x3 y separadas."""
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
            d.text((e["xy"][0] * k, e["xy"][1] * k), e["s"], fill=fill, font=_font(e["size"] * k), anchor=e.get("anchor", "mm"))
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
    xs: list = []
    ys: list = []
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
                xs.append(x)
                ys.append(y)
                if math.hypot(x / k - z["cx"], y / k - z["cy"]) > z["r"] + 4:
                    outside += 1
    des.sort()
    els, cands = scene(scene_id)
    rec = getattr(cands[diff_id], "recolor", None)
    recolor_de = None
    if rec:
        fill = next(e for e in els if e["id"] == rec)["fill"]
        recolor_de = round(delta_e(fill, near_tone(fill, 11.0)), 2)
    bbox_pct = ((max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)) / (OUT_W * OUT_H) * 100 if xs else 0.0
    return {"area_pct": len(des) / (OUT_W * OUT_H) * 100, "bbox_pct": bbox_pct, "p90_de": des[int(len(des) * 0.9)] if des else 0.0, "outside": outside,
            "zone_pct": math.pi * z["r"] ** 2 / (W * H) * 100, "recolor_de": recolor_de, "cell": cell_of(z)}
