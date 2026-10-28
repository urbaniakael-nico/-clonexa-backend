"""Menu video: remasterizado de fotos y clips de 3 s, en el servidor y sin IA.

Todo es Pillow + ffmpeg (nada se inventa: el clip usa SOLO las fotos reales
del plato). Funciones puras (bytes -> bytes): no tocan la base ni el bucket;
eso lo hace app.services.menu_video.

- detect_dish(): donde esta el plato (OpenCV: circulo/elipse; si no, la
  zona con mas color y contraste; si no, el centro). Nunca falla.
- remaster(): luz y balance de blancos, contraste y saturacion suaves,
  nitidez ligera y recorte vertical 3:4 SOLO si el plato completo cabe,
  WebP. La original se guarda aparte, siempre (normalize()).
- Camino 2, make_clip(): anima UNA foto (la principal; nunca un pase de
  fotos) con un estilo suave (Vida, Acercamiento, Giro suave, Paneo, Brillo o
  Automatico), 720 x 1280, 25 fps, H.264 sin audio, faststart, 3 s en bucle
  sin salto (curvas ease-in-out que vuelven al punto de partida), < 600 KB,
  mas su portada. La foto ENTERA cabe en el cuadro (relleno: la misma foto
  difuminada), centro del plato a ~38 % del alto; el plato nunca sale.
- Camino 1, make_video_clip(): el video real del plato (MP4/MOV, HEVC de
  iPhone incluido, max. 30 s y 150 MB, sin audio): estabilizado (vidstab o,
  sin el, deshake), luz/color/ruido/nitidez, fondo (desenfocar, oscurecer o
  sin cambios), velocidad y tramo, 3 s en bucle con fundido final, < 1 MB.
- Una foto dañada o un formato raro -> MediaRejected (error controlado).
- Sin ffmpeg -> MediaUnavailable (la cola marca el trabajo en error).
"""
from __future__ import annotations

import io
import math
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from app.services.brand_media import MAX_PIXELS, sniff

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ORIGINAL_MAX_PX = 2048
REMASTER_MAX_H = 1080
REMASTER_RATIO = 3 / 4  # ancho / alto
CLIP_W, CLIP_H, CLIP_FPS, CLIP_SECONDS = 720, 1280, 25, 3
CLIP_TARGET_BYTES = 600 * 1024
CANVAS_SCALE = 1.2      # el lienzo se arma un poco mas grande: el acercamiento queda nitido
MAX_ZOOM = 1.08         # acercamiento maximo (8 %)
DISH_Y = 0.38           # centro del plato a ~38 % del alto (encima de la tarjeta del precio)
DISH_MARGIN = 0.06      # aire alrededor del plato que nunca sale del cuadro
VISIBLE_H = 0.68        # la foto cabe en el 68 % de arriba: la tarjeta del precio nunca tapa el plato
GALLERY_MAX = 6         # "Más fotos (galería)" del boton Detalle


class MediaRejected(ValueError):
    """La foto no se puede usar (dañada, vacia, muy pesada o no es imagen)."""


class MediaUnavailable(RuntimeError):
    """ffmpeg no esta instalado o fallo al codificar."""


# ------------------------------------------------------------------ ffmpeg ---
@lru_cache(maxsize=1)
def ffmpeg_path() -> Optional[str]:
    """FFMPEG_BIN, luego el del sistema (Railway: apt) y, solo en equipos de
    desarrollo, el binario de imageio-ffmpeg."""
    env = os.getenv("FFMPEG_BIN", "").strip()
    if env and os.path.exists(env):
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # pragma: no cover - solo en desarrollo
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


@lru_cache(maxsize=1)
def ffmpeg_version() -> Optional[str]:
    path = ffmpeg_path()
    if not path:
        return None
    try:
        out = subprocess.run([path, "-hide_banner", "-version"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return None
    first = (out or "").splitlines()[0] if out else ""
    parts = first.split()
    return parts[2] if len(parts) >= 3 and parts[0] == "ffmpeg" else (first or None)


# ------------------------------------------------------------------ fotos ---
def load(raw: bytes):
    """Imagen RGB lista para trabajar (rotada segun EXIF) o MediaRejected."""
    from PIL import Image, ImageOps

    if not raw:
        raise MediaRejected("La foto está vacía.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise MediaRejected("La foto pesa más de 15 MB.")
    kind = sniff(raw)
    if kind is None:
        raise MediaRejected("La foto está dañada o no es JPG, PNG o WebP.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format != kind or image.width * image.height > MAX_PIXELS:
            raise MediaRejected("La foto está dañada o no es JPG, PNG o WebP.")
        image.load()
        image = ImageOps.exif_transpose(image)
    except MediaRejected:
        raise
    except Exception:
        raise MediaRejected("La foto está dañada o no se puede leer.") from None
    if image.width < 160 or image.height < 160:
        raise MediaRejected("La foto es muy pequeña (mínimo 160 px por lado).")
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[-1])
        return flat
    return image.convert("RGB")


def webp(image, quality: int = 82) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=4)  # sin EXIF ni metadatos
    return buffer.getvalue()


def normalize(image) -> tuple[bytes, int, int]:
    """La ORIGINAL que se guarda: misma foto, sin metadatos, maximo 2048 px."""
    copy = image.copy()
    copy.thumbnail((ORIGINAL_MAX_PX, ORIGINAL_MAX_PX))
    return webp(copy, 90), copy.width, copy.height


def _mean_rgb(image) -> tuple[float, float, float]:
    from PIL import ImageStat

    small = image.copy()
    small.thumbnail((128, 128))
    r, g, b = ImageStat.Stat(small).mean[:3]
    return r, g, b


# ------------------------------------------------------------------- plato ---
@dataclass(frozen=True)
class Dish:
    """Donde esta el plato en la foto (fracciones 0..1) y como se encontro."""
    cx: float
    cy: float
    w: float
    h: float
    source: str  # "plato" (circulo/elipse) | "color" (mas color y contraste) | "centro"


CENTER = Dish(0.5, 0.5, 0.86, 0.86, "centro")


def _detect_cv(image) -> Optional[Dish]:
    """Circulo o elipse del plato con OpenCV (sin IA). None si no lo encuentra."""
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    small = image.copy()
    small.thumbnail((480, 480))
    w, h = small.size
    gray = cv2.GaussianBlur(cv2.cvtColor(np.asarray(small.convert("RGB")), cv2.COLOR_RGB2GRAY), (7, 7), 1.6)
    side = min(w, h)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.3, minDist=side, param1=110, param2=46,
                               minRadius=int(side * 0.22), maxRadius=int(side * 0.62))
    if circles is not None and len(circles[0]):
        x, y, r = max(circles[0], key=lambda c: c[2])
        if 0 <= x < w and 0 <= y < h:
            x0, x1 = max(0.0, x - r), min(float(w), x + r)
            y0, y1 = max(0.0, y - r), min(float(h), y + r)
            return Dish((x0 + x1) / 2 / w, (y0 + y1) / 2 / h, (x1 - x0) / w, (y1 - y0) / h, "plato")
    edges = cv2.dilate(cv2.Canny(gray, 50, 140), np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = max(contours, key=cv2.contourArea, default=None)
    if best is not None and len(best) >= 5 and cv2.contourArea(best) > 0.12 * w * h:
        (ex, ey), (ea, eb), _angle = cv2.fitEllipse(best)
        bx, by, bw, bh = cv2.boundingRect(best)
        if 0 < bw < w * 0.995 or 0 < bh < h * 0.995:
            return Dish((bx + bw / 2) / w, (by + bh / 2) / h, bw / w, bh / h, "plato")
    return None


def _detect_color(image) -> Optional[Dish]:
    """La zona con mas color y contraste (respaldo sin OpenCV)."""
    from PIL import ImageFilter

    small = image.copy()
    small.thumbnail((96, 96))
    sat = small.convert("HSV").split()[1].tobytes()
    edges = small.convert("L").filter(ImageFilter.FIND_EDGES).tobytes()
    w, h = small.size
    xs, ys, total = [], [], 0.0
    for index in range(w * h):
        weight = sat[index] * 0.6 + edges[index] * 0.4
        if weight > 60:
            xs.append(index % w)
            ys.append(index // w)
            total += weight
    if total <= 0 or len(xs) < w * h * 0.04:
        return None
    xs.sort()
    ys.sort()
    q = lambda arr, p: arr[min(len(arr) - 1, int(p * len(arr)))]  # noqa: E731
    x0, x1, y0, y1 = q(xs, 0.08), q(xs, 0.92) + 1, q(ys, 0.08), q(ys, 0.92) + 1
    return Dish((x0 + x1) / 2 / w, (y0 + y1) / 2 / h, (x1 - x0) / w, (y1 - y0) / h, "color")


def detect_dish(image) -> Dish:
    """Plato -> zona de color -> centro de la foto. Nunca falla."""
    for finder in (_detect_cv, _detect_color):
        try:
            found = finder(image)
        except Exception:
            found = None
        if found and 0.05 < found.w <= 1 and 0.05 < found.h <= 1:
            return found
    return CENTER


def dish_center(image) -> tuple[float, float]:
    dish = detect_dish(image)
    return dish.cx, dish.cy


def crop_vertical(image, center: tuple[float, float], ratio: float = REMASTER_RATIO):
    """La ventana vertical (ancho/alto = ratio) mas grande posible, centrada
    en el plato y sin salirse de la foto."""
    w, h = image.size
    if w / h > ratio:
        cw, ch = round(h * ratio), h
    else:
        cw, ch = w, round(w / ratio)
    left = min(max(round(center[0] * w - cw / 2), 0), w - cw)
    top = min(max(round(center[1] * h - ch / 2), 0), h - ch)
    return image.crop((left, top, left + cw, top + ch))


def safe_crop(image, dish: Dish, ratio: float = REMASTER_RATIO):
    """Recorte 3:4 SOLO si el plato completo cabe; si no, la foto entera."""
    cropped = crop_vertical(image, (dish.cx, dish.cy), ratio)
    w, h = image.size
    if dish.source != "centro" and (dish.w * w > cropped.width * 1.0 or dish.h * h > cropped.height * 1.0):
        return image
    if dish.source == "centro" and cropped.size != image.size:
        return image  # sin saber donde esta el plato no se corta nada
    return cropped


def enhance(image):
    """Luz, balance de blancos, contraste, saturacion y nitidez: todo suave."""
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    r, g, b = _mean_rgb(image)
    gray = (r + g + b) / 3 or 1
    # balance de blancos "mundo gris" al 60 %, con tope (no lava los colores de la comida)
    gains = [min(1.2, max(0.85, 1 + 0.6 * (gray / max(c, 1) - 1))) for c in (r, g, b)]
    channels = [band.point(lambda v, k=k: min(255, round(v * k))) for band, k in zip(image.split(), gains)]
    image = Image.merge("RGB", channels)
    # luz: lleva el brillo medio hacia 0.5 con una curva gamma suave
    lum = sum(_mean_rgb(image)) / 3 / 255
    if 0.02 < lum < 0.98:
        target_gamma = math.log(0.5) / math.log(lum)
        gamma = 1 + (min(1.35, max(0.72, target_gamma)) - 1) * 0.6
        table = [min(255, round(255 * ((v / 255) ** gamma))) for v in range(256)]
        image = image.point(table * 3)
    # contraste: autocontraste con 1 % de corte, mezclado a la mitad
    image = Image.blend(image, ImageOps.autocontrast(image, cutoff=1), 0.5)
    image = ImageEnhance.Contrast(image).enhance(1.05)
    image = ImageEnhance.Color(image).enhance(1.12)
    return image.filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=3))


@dataclass
class Remastered:
    image: object
    data: bytes
    width: int
    height: int


def remaster(image) -> Remastered:
    cropped = safe_crop(image, detect_dish(image))
    if cropped.height > REMASTER_MAX_H:
        cropped = cropped.resize((round(REMASTER_MAX_H * cropped.width / cropped.height), REMASTER_MAX_H), resample=3)
    if cropped.width > 1440:
        cropped = cropped.resize((1440, round(1440 * cropped.height / cropped.width)), resample=3)
    out = enhance(cropped)
    return Remastered(image=out, data=webp(out, 84), width=out.width, height=out.height)


def clip_source(image, use_remaster: bool = True):
    """Lo que entra al clip: la foto COMPLETA (nunca recortada), con la misma
    mejora de luz y color si se eligio la remasterizada."""
    copy = image.copy()
    copy.thumbnail((1600, 1600))
    return enhance(copy) if use_remaster else copy


# ------------------------------------------------------------------- clip ---
def _cover(image, w: int, h: int):
    scale = max(w / image.width, h / image.height)
    resized = image.resize((max(w, round(image.width * scale)), max(h, round(image.height * scale))), resample=3)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _blur_fill(image, w: int, h: int, dim: float = 0.7):
    """Relleno: la MISMA foto agrandada, difuminada y un poco oscura (barato:
    se difumina en pequeño y se agranda)."""
    from PIL import ImageEnhance, ImageFilter

    small = _cover(image, max(8, w // 8), max(8, h // 8)).filter(ImageFilter.GaussianBlur(radius=4))
    return ImageEnhance.Brightness(small.resize((w, h), resample=2)).enhance(dim)


def _dish_mask(size: tuple, dish: "Dish", pad: float = 0.14, feather: float = 0.08):
    """Mascara suave (L) del plato: 255 dentro, 0 fuera, borde difuminado."""
    from PIL import Image, ImageDraw, ImageFilter

    w, h = size
    small = (max(16, w // 4), max(16, h // 4))
    mask = Image.new("L", small, 0)
    sw, sh = small
    rx, ry = dish.w * sw * (1 + pad) / 2, dish.h * sh * (1 + pad) / 2
    cx, cy = dish.cx * sw, dish.cy * sh
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(1.0, feather * min(sw, sh))))
    return mask.resize((w, h), resample=2)


def apply_background(image, dish: "Dish", mode: str):
    """Fondo fuera del plato: "desenfocar" (desenfoque + oscurecido suave),
    "oscurecer" o "ninguno". Sin saber donde esta el plato no se toca."""
    from PIL import Image, ImageEnhance, ImageFilter

    if mode not in ("desenfocar", "oscurecer") or dish.source == "centro":
        return image
    mask = _dish_mask(image.size, dish)
    if mode == "desenfocar":
        small = image.resize((max(8, image.width // 4), max(8, image.height // 4)), resample=2)
        out = small.filter(ImageFilter.GaussianBlur(radius=3)).resize(image.size, resample=2)
        out = ImageEnhance.Brightness(out).enhance(0.8)
    else:
        out = ImageEnhance.Brightness(image).enhance(0.62)
    return Image.composite(image, out, mask)


@dataclass
class Shot:
    """La foto armada en el cuadro vertical: fondo (relleno difuminado), la
    foto entera encima, centro del plato y su acercamiento maximo seguro."""
    canvas: object          # fondo + foto (sin movimiento)
    background: object      # solo el relleno difuminado
    photo: object           # la foto (ya con su fondo elegido) al tamaño del cuadro
    cx: float
    cy: float
    zmax: float
    photo_box: tuple
    dish_box: tuple
    source: str
    round_center: bool = False
    photo_rgba: object = None


def compose(image, dish: Optional[Dish] = None, scale: float = CANVAS_SCALE, background: str = "ninguno") -> Shot:
    """La foto ENTERA dentro del cuadro 9:16; arriba y abajo, la misma foto
    agrandada y difuminada (nunca bordes negros). El centro del plato queda a
    ~38 % del alto (encima de la tarjeta del precio del modo video)."""
    dish = dish or detect_dish(image)
    W, H = round(CLIP_W * scale), round(CLIP_H * scale)
    fill = _blur_fill(image, W, H)
    fit = min(W / image.width, VISIBLE_H * H / image.height)
    pw, ph = round(image.width * fit), round(image.height * fit)
    x0 = (W - pw) // 2
    y0 = round(min(max(DISH_Y * H - dish.cy * ph, 0), H - ph))
    photo = apply_background(image, dish, background).resize((pw, ph), resample=3)
    canvas = fill.copy()
    canvas.paste(photo, (x0, y0))
    dcx, dcy = x0 + dish.cx * pw, y0 + dish.cy * ph
    dw, dh = dish.w * pw * (1 + DISH_MARGIN), dish.h * ph * (1 + DISH_MARGIN)
    zmax = max(1.0, min(MAX_ZOOM, W / max(dw, 1), H / max(dh, 1)))
    aspect = (dish.w * image.width) / max(1.0, dish.h * image.height)
    round_center = dish.source == "plato" and abs(dish.cx - 0.5) < 0.14 and abs(dish.cy - 0.5) < 0.14 and 0.75 < aspect < 1.33
    return Shot(canvas=canvas, background=fill, photo=photo, cx=dcx, cy=dcy, zmax=zmax, photo_box=(x0, y0, x0 + pw, y0 + ph),
                dish_box=(dcx - dish.w * pw / 2, dcy - dish.h * ph / 2, dcx + dish.w * pw / 2, dcy + dish.h * ph / 2),
                source=dish.source, round_center=round_center)


def view_box(shot: Shot, zoom: float, center: Optional[tuple] = None) -> tuple[float, float, float, float]:
    """Recorte del lienzo con acercamiento `zoom` hacia el plato (o hacia
    `center`), sin salirse del lienzo."""
    W, H = shot.canvas.size
    cw, ch = W / zoom, H / zoom
    px, py = center if center else (shot.cx, shot.cy)
    left = min(max(px - cw / 2, 0.0), W - cw)
    top = min(max(py - ch / 2, 0.0), H - ch)
    return left, top, left + cw, top + ch


def render(shot: Shot, zoom: float, center: Optional[tuple] = None, angle: float = 0.0, canvas=None):
    source = canvas if canvas is not None else (_rotated(shot, angle) if angle else shot.canvas)
    return source.resize((CLIP_W, CLIP_H), resample=3, box=view_box(shot, zoom, center))


def _rotated(shot: Shot, angle: float):
    """Gira SOLO la foto alrededor del plato (el relleno queda quieto): nunca
    aparecen esquinas negras y la foto no pierde bordes (expand)."""
    if shot.photo_rgba is None:
        shot.photo_rgba = shot.photo.convert("RGBA")
    from PIL import Image

    x0, y0, x1, y1 = shot.photo_box
    turned = shot.photo_rgba.rotate(angle, resample=Image.BILINEAR, expand=True)
    # el centro del plato queda en el mismo punto del cuadro
    px, py = shot.cx - x0 - (x1 - x0) / 2, shot.cy - y0 - (y1 - y0) / 2
    rad = math.radians(angle)
    rx, ry = px * math.cos(rad) + py * math.sin(rad), -px * math.sin(rad) + py * math.cos(rad)
    left = round(shot.cx - (turned.width / 2 + rx))
    top = round(shot.cy - (turned.height / 2 + ry))
    out = shot.background.copy()
    out.paste(turned, (left, top), turned)
    return out


def _ease(x: float) -> float:
    return (1 - math.cos(math.pi * min(1.0, max(0.0, x)))) / 2


def _wave(u: float) -> float:
    """0 -> 1 -> 0 en una vuelta, con curva suave (ease-in-out): el ultimo
    cuadro empalma con el primero (bucle sin salto)."""
    return (1 - math.cos(2 * math.pi * u)) / 2


def zoom_at(shot: Shot, u: float, limit: float = MAX_ZOOM) -> float:
    """Arranca con el plato completo, se acerca suave (max. `limit`) y vuelve."""
    return 1 + (min(shot.zmax, limit) - 1) * _wave(u)


# Estilos de la foto (Camino 2): todos suaves, 3 s en bucle sin salto, una sola foto.
STYLES = {
    "vida": "Vida",
    "zoom": "Acercamiento",
    "giro": "Giro suave",
    "paneo": "Paneo",
    "brillo": "Brillo",
    "auto": "Automático",
}
BACKGROUNDS = {"desenfocar": "Desenfocar fondo", "oscurecer": "Oscurecer fondo", "ninguno": "Sin cambios"}
SPEEDS = {"lento": "Más lento", "normal": "Normal", "rapido": "Más rápido"}
DEFAULT_STYLE, DEFAULT_BACKGROUND, DEFAULT_SPEED = "vida", "ninguno", "normal"
LIFE_ZOOM, LIFE_ANGLE, SPIN_ANGLE, SPIN_ZOOM, PAN_ZOOM = 1.06, 1.5, 3.0, 1.03, 1.10


def resolve_style(style: str = "auto", image=None, shot: Optional[Shot] = None) -> str:
    """"auto" elige por la forma de la foto: horizontal -> paneo; plato redondo
    centrado -> giro suave; el resto -> vida. Un estilo viejo o raro -> vida."""
    style = style if style in STYLES else ("vida" if style in ("suave", "front_side", "") else "auto")
    if style != "auto":
        return style
    if image is not None and image.width / max(1, image.height) >= 1.25:
        return "paneo"
    if shot is not None and shot.round_center:
        return "giro"
    return "vida"


def _pan_span(shot: Shot, zoom: float) -> float:
    """Cuanto se puede mover la vista de lado a lado sin sacar el plato del cuadro."""
    W, _H = shot.canvas.size
    vw = W / zoom
    x0, _y0, x1, _y1 = shot.dish_box
    margin = (x1 - x0) * DISH_MARGIN / 2
    lo, hi = x1 + margin - vw / 2, x0 - margin + vw / 2   # centros de vista con el plato entero dentro
    lo, hi = max(lo, vw / 2), min(hi, W - vw / 2)          # sin salirse del lienzo
    if hi <= lo:
        return 0.0
    return min((hi - lo) / 2, W * 0.07)


def _shine(shot: Shot):
    """Mascara del plato para el reflejo de "Brillo" (al tamaño del cuadro final)."""
    from PIL import Image

    x0, y0, x1, y1 = shot.dish_box
    W, H = shot.canvas.size
    dish = Dish(((x0 + x1) / 2) / W, ((y0 + y1) / 2) / H, (x1 - x0) / W, (y1 - y0) / H, shot.source)
    return _dish_mask((CLIP_W, CLIP_H), dish, pad=0.0, feather=0.05) if shot.source != "centro" else Image.new("L", (CLIP_W, CLIP_H), 200)


def _keep_dish(shot: Shot, zoom: float, center: tuple) -> tuple:
    """Corrige el centro de la vista para que el plato completo (con su aire)
    quede SIEMPRE dentro del cuadro."""
    W, H = shot.canvas.size
    vw, vh = W / zoom, H / zoom
    x0, y0, x1, y1 = shot.dish_box
    mx, my = (x1 - x0) * DISH_MARGIN / 2, (y1 - y0) * DISH_MARGIN / 2
    px, py = center
    lo_x, hi_x = x1 + mx - vw / 2, x0 - mx + vw / 2
    lo_y, hi_y = y1 + my - vh / 2, y0 - my + vh / 2
    px = min(max(px, lo_x), hi_x) if lo_x <= hi_x else (x0 + x1) / 2
    py = min(max(py, lo_y), hi_y) if lo_y <= hi_y else (y0 + y1) / 2
    return px, py


def frame_geometry(shot: Shot, style: str, u: float) -> tuple[float, tuple, float]:
    """(acercamiento, centro de la vista, giro en grados) del estilo en el
    instante u (0..1). Todo vuelve al punto de partida en u = 1."""
    W, H = shot.canvas.size
    s = _wave(u)
    if style == "zoom":
        zoom = zoom_at(shot, u, MAX_ZOOM)
        return zoom, _keep_dish(shot, zoom, (shot.cx, shot.cy)), 0.0
    if style == "giro":
        zoom = 1 + (min(shot.zmax, 1 + SPIN_ZOOM) - 1) * s
        return zoom, _keep_dish(shot, zoom, (shot.cx, shot.cy)), SPIN_ANGLE * math.sin(2 * math.pi * u)
    if style == "paneo":
        zoom = min(shot.zmax, PAN_ZOOM)
        span = _pan_span(shot, zoom)
        return zoom, _keep_dish(shot, zoom, (shot.cx + span * math.sin(2 * math.pi * u), shot.cy)), 0.0
    if style == "brillo":
        return 1.0, (W / 2, H / 2), 0.0
    # "vida": acercamiento lento (max 6 %), giro leve de 1,5° y paneo pequeño hacia el plato, y vuelve
    zoom = 1 + (min(shot.zmax, LIFE_ZOOM) - 1) * s
    center = (W / 2 + (shot.cx - W / 2) * s, H / 2 + (shot.cy - H / 2) * s)
    return zoom, _keep_dish(shot, zoom, center), LIFE_ANGLE * s


def style_frame(shot: Shot, style: str, u: float, shine_mask=None):
    """Cuadro en el instante u (0..1) del bucle de 3 s para un estilo."""
    from PIL import Image, ImageChops

    if style == "brillo":
        base = render(shot, 1.0)
        band = _band(u)
        if band is None:
            return base
        light = ImageChops.multiply(band, shine_mask if shine_mask is not None else _shine(shot))
        return Image.composite(ImageChops.screen(base, Image.new("RGB", base.size, (255, 248, 235))), base, light)
    zoom, center, angle = frame_geometry(shot, style, u)
    return render(shot, zoom, center=center, angle=angle)


def _band(u: float):
    """Reflejo de luz diagonal que cruza el plato entre el 15 % y el 75 % del
    bucle (antes y despues no se ve: el bucle no salta)."""
    from PIL import Image, ImageDraw, ImageFilter

    a, b = 0.15, 0.75
    if not a < u < b:
        return None
    t = (u - a) / (b - a)
    strength = math.sin(math.pi * t)  # entra y sale suave
    small = Image.new("L", (CLIP_W // 4, CLIP_H // 4), 0)
    sw, sh = small.size
    x = -sw * 0.6 + t * sw * 2.2
    ImageDraw.Draw(small).polygon([(x, 0), (x + sw * 0.22, 0), (x + sw * 0.22 - sh * 0.35, sh), (x - sh * 0.35, sh)],
                                  fill=round(110 * strength))
    return small.filter(ImageFilter.GaussianBlur(radius=10)).resize((CLIP_W, CLIP_H), resample=2)


def frame_at(shots: list, index: int, total: int = CLIP_FPS * CLIP_SECONDS, style: str = "zoom"):
    """Cuadro `index` de `total` (una sola foto: Camino 2 nunca mezcla fotos)."""
    return style_frame(shots[0], style, index / total)


@dataclass
class Clip:
    video: bytes
    poster: bytes
    style: str
    seconds: float
    encode_ms: int
    attempts: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    stabilizer: str = ""
    speed: float = 1.0
    background: str = ""


def _encode(frames: list, crf: int, maxrate: str) -> bytes:
    exe = ffmpeg_path()
    if not exe:
        raise MediaUnavailable("ffmpeg no está instalado en el servidor.")
    with tempfile.TemporaryDirectory(prefix="cx_clip_") as folder:
        out = os.path.join(folder, "clip.mp4")
        args = [exe, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{CLIP_W}x{CLIP_H}", "-r", str(CLIP_FPS), "-i", "-",
                "-an", "-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-pix_fmt", "yuv420p",
                "-crf", str(crf), "-maxrate", maxrate, "-bufsize", maxrate, "-g", str(CLIP_FPS * CLIP_SECONDS),
                "-movflags", "+faststart", out]
        try:
            proc = subprocess.run(args, input=b"".join(f.tobytes() for f in frames), capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise MediaUnavailable("ffmpeg no pudo crear el clip.") from error
        if proc.returncode != 0 or not os.path.exists(out):
            raise MediaUnavailable("ffmpeg no pudo crear el clip.")
        with open(out, "rb") as handle:
            return handle.read()


def _encode_under(frames: list, target: int, tries) -> tuple[bytes, list]:
    attempts, video = [], b""
    for crf, maxrate in tries:
        video = _encode(frames, crf, maxrate)
        attempts.append({"crf": crf, "bytes": len(video)})
        if len(video) <= target:
            break
    return video, attempts


PHOTO_TRIES = ((24, "1500k"), (27, "1300k"), (30, "1100k"), (34, "900k"))


def make_clip(images, side_image=None, style: str = "auto", background: str = DEFAULT_BACKGROUND) -> Clip:
    """Camino 2 "Subir foto": anima UNA foto (la principal). Si llegan varias,
    solo se usa la primera: las demas son galeria del boton "Detalle" y NUNCA
    se mezclan en el video (sin pases de foto)."""
    if isinstance(images, (list, tuple)):
        images = [i for i in images if i is not None]
        image = images[0] if images else None
    else:
        image = images
    if image is None:
        raise MediaRejected("El plato no tiene foto principal.")
    background = background if background in BACKGROUNDS else DEFAULT_BACKGROUND
    started = time.perf_counter()
    shot = compose(image, background=background)
    chosen = resolve_style(style, image, shot)
    total = CLIP_FPS * CLIP_SECONDS
    mask = _shine(shot) if chosen == "brillo" else None
    frames = [style_frame(shot, chosen, i / total, mask).convert("RGB") for i in range(total)]
    video, attempts = _encode_under(frames, CLIP_TARGET_BYTES, PHOTO_TRIES)
    poster = webp(render(shot, 1.0), 80)  # portada: el plato completo
    return Clip(video=video, poster=poster, style=chosen, seconds=float(CLIP_SECONDS),
                encode_ms=round((time.perf_counter() - started) * 1000), attempts=attempts, sources=[shot.source],
                background=background)


# ---------------------------------------------------- video del plato (Camino 1) ---
VIDEO_MAX_BYTES = 150 * 1024 * 1024
VIDEO_MAX_SECONDS = 30.0
VIDEO_TARGET_BYTES = 1024 * 1024 - 24 * 1024   # < 1 MB con margen
VIDEO_LOOP_FADE = 0.4                           # fundido del final con el inicio
VIDEO_TRIES = ((23, "2200k"), (26, "1800k"), (29, "1400k"), (32, "1100k"), (35, "900k"))
SPEED_FACTORS = {"lento": 0.7, "normal": 1.0, "rapido": 1.4}
VIDEO_KINDS = ("mp4", "mov", "m4v", "3gp")


@lru_cache(maxsize=1)
def stabilizer() -> str:
    """"vidstab" si el ffmpeg del servidor lo trae; si no, "deshake"."""
    exe = ffmpeg_path()
    if not exe:
        return ""
    try:
        out = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=15).stdout or ""
    except Exception:
        return "deshake"
    return "vidstab" if "vidstabdetect" in out and "vidstabtransform" in out else "deshake"


def sniff_video(raw: bytes) -> Optional[str]:
    """MP4/MOV/3GP (caja ftyp/moov/mdat al inicio). Nada mas se acepta."""
    head = raw[:64]
    if len(head) >= 12 and head[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"):
        brand = head[8:12]
        return "mov" if brand == b"qt  " or head[4:8] != b"ftyp" else "mp4"
    return None


def check_video_size(size: int) -> None:
    if size <= 0:
        raise MediaRejected("El video está vacío.")
    if size > VIDEO_MAX_BYTES:
        raise MediaRejected(f"El video pesa {size / 1024 / 1024:.0f} MB: el máximo es 150 MB. Grábalo más corto (5 a 10 segundos).")


def _video_info(exe: str, path: str) -> dict:
    proc = subprocess.run([exe, "-hide_banner", "-i", path], capture_output=True, text=True, timeout=30)
    info = proc.stderr or ""
    import re

    out: dict = {"has_video": "Video:" in info, "codec": ""}
    codec = re.search(r"Video: (\w+)", info)
    if codec:
        out["codec"] = codec.group(1)
    dur = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", info)
    out["seconds"] = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else 0.0
    return out


def inspect_video(raw: bytes) -> dict:
    """Revision rapida al subir (antes de guardar): formato, peso y duracion.
    Mensajes claros si pasa de 30 s o 150 MB."""
    check_video_size(len(raw or b""))
    if not sniff_video(raw):
        raise MediaRejected("El video debe ser MP4 o MOV (el del celular).")
    exe = ffmpeg_path()
    if not exe:
        raise MediaUnavailable("ffmpeg no está instalado en el servidor.")
    import re

    with tempfile.TemporaryDirectory(prefix="cx_vin_") as folder:
        src = os.path.join(folder, "in.mov")
        with open(src, "wb") as handle:
            handle.write(raw)
        info = _video_info(exe, src)
        proc = subprocess.run([exe, "-hide_banner", "-i", src], capture_output=True, text=True, timeout=30)
    if not info["has_video"]:
        raise MediaRejected("El archivo no tiene video.")
    if info["seconds"] > VIDEO_MAX_SECONDS + 0.5:
        raise MediaRejected(f"El video dura {info['seconds']:.0f} s: el máximo es 30 s. Graba de 5 a 10 segundos.")
    if info["seconds"] < 1.0:
        raise MediaRejected("El video es muy corto: graba de 5 a 10 segundos.")
    size = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", proc.stderr or "")
    if size:
        info["width"], info["height"] = int(size.group(1)), int(size.group(2))
    return info


def _grab(exe: str, path: str, at: float) -> object:
    """Un cuadro (ya girado segun el celular) como imagen."""
    from PIL import Image

    proc = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, at):.3f}", "-i", path,
                           "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        raise MediaRejected("No se pudo leer el video (formato no compatible).")
    return Image.open(io.BytesIO(proc.stdout)).convert("RGB")


def _even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)


def white_gains(image) -> list:
    """Balance de blancos con lo blanco de la escena (el plato, casi siempre):
    los pixeles mas claros y poco saturados. Sin ellos, "mundo gris" al 30 %.
    Con tope suave: una mesa de madera nunca vuelve azul el plato."""
    import numpy as np

    small = image.copy()
    small.thumbnail((160, 160))
    px = np.asarray(small.convert("RGB"), dtype=np.float64).reshape(-1, 3)
    sat = np.asarray(small.convert("HSV"))[:, :, 1].reshape(-1)
    neutral = px[sat < 40]
    top = neutral[np.argsort(neutral.sum(axis=1))[::-1][: max(1, len(px) // 50)]] if len(neutral) >= len(px) // 100 else neutral[:0]
    if len(top) and top.sum(axis=1).mean() > 300:
        ref = [float(v) for v in top.mean(axis=0)]
        strength = 0.8
    else:
        ref = list(_mean_rgb(image))
        strength = 0.3
    gray = sum(ref) / 3 or 1
    return [min(1.15, max(0.88, 1 + strength * (gray / max(c, 1) - 1))) for c in ref]


def tone_luts(image) -> list:
    """Niveles automaticos, balance de blancos y luz de UN cuadro, como tablas
    por canal: se aplican IGUAL a todo el video (sin parpadeo)."""
    from PIL import Image

    gains = white_gains(image)
    balanced = Image.merge("RGB", [band.point(lambda v, k=k: min(255, round(v * k))) for band, k in zip(image.split(), gains)])
    lum = sum(_mean_rgb(balanced)) / 3 / 255
    gamma = 1.0
    if 0.02 < lum < 0.98:
        gamma = 1 + (min(1.35, max(0.72, math.log(0.5) / math.log(lum))) - 1) * 0.6
    hist = balanced.convert("L").histogram()
    total = sum(hist) or 1
    acc, lo, hi = 0, 0, 255
    for i, n in enumerate(hist):
        acc += n
        if acc >= total * 0.01:
            lo = i
            break
    acc = 0
    for i in range(255, -1, -1):
        acc += hist[i]
        if acc >= total * 0.01:
            hi = i
            break
    span = max(32, hi - lo)
    luts = []
    for k in gains:
        table = []
        for v in range(256):
            x = min(255.0, v * k)
            stretched = min(1.0, max(0.0, (x - lo) / span))
            x = (x / 255) * 0.5 + stretched * 0.5          # niveles al 50 % (suave)
            table.append(min(255, max(0, round(255 * (x ** gamma)))))
        luts.append(table)
    return luts


def video_fit(sample, dish: Dish) -> tuple[int, int]:
    """Tamaño del video en el cuadro 720x1280: lo mas grande posible con el
    PLATO completo (y su aire) arriba de la tarjeta del precio; nunca mas alto
    que el cuadro. Lo que sobre del video a los lados puede quedar fuera; el
    plato no. Si no se sabe donde esta el plato, el video entero cabe."""
    w, h = sample.size
    whole = min(CLIP_W / w, VISIBLE_H * CLIP_H / h)
    if dish.source == "centro":
        scale = whole
    else:
        by_w = CLIP_W * (1 - 2 * DISH_MARGIN) / max(1.0, dish.w * w)
        by_h = 2 * (VISIBLE_H - DISH_Y) * CLIP_H * (1 - DISH_MARGIN) / max(1.0, dish.h * h)
        scale = max(whole, min(CLIP_H / h, CLIP_W * 1.6 / w, by_w, by_h))
    return _even(w * scale), _even(h * scale)


def _place(ideal: float, size: int, room: int) -> int:
    """Posicion del video: la ideal (plato centrado / a 38 %) sin dejar huecos
    si el video es mas grande que el cuadro, ni salirse si es mas chico."""
    if size >= room:
        return round(min(0, max(room - size, ideal)))
    return (room - size) // 2  # mas angosto que el cuadro: centrado (sin bordes corridos)


def _vf_chain(fps: float, pw: int, ph: int, stab: str, trf: Optional[str]) -> str:
    parts = [f"fps={fps:.5f}", f"scale={pw}:{ph}:flags=lanczos"]
    if stab == "vidstab" and trf:
        parts.append(f"vidstabtransform=input={trf}:smoothing=12:zoom=0:optzoom=0:crop=keep:interpol=bicubic")
    elif stab == "deshake":
        parts.append("deshake=edge=mirror")
    parts += ["hqdn3d=1.5:1.5:5:5", "eq=contrast=1.05:saturation=1.10", "unsharp=5:5:0.55:5:5:0.0"]
    return ",".join(parts)


def make_video_clip(raw: bytes, background: str = "desenfocar", speed: str = DEFAULT_SPEED,
                    start: Optional[float] = None, length: Optional[float] = None) -> Clip:
    """Camino 1 "Subir video": el video REAL del plato (base giratoria o
    caminando alrededor), estabilizado, con luz y color corregidos, fondo a
    elegir, plato completo centrado (~38 % del alto) y 3 s en bucle sin salto
    (fundido corto del final con el inicio). Sin audio, < 1 MB."""
    from PIL import Image

    check_video_size(len(raw or b""))
    if not sniff_video(raw):
        raise MediaRejected("El video debe ser MP4 o MOV (el del celular).")
    exe = ffmpeg_path()
    if not exe:
        raise MediaUnavailable("ffmpeg no está instalado en el servidor.")
    background = background if background in BACKGROUNDS else "desenfocar"
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="cx_vid_") as folder:
        src = os.path.join(folder, "in.mov")
        with open(src, "wb") as handle:
            handle.write(raw)
        info = _video_info(exe, src)
        if not info["has_video"]:
            raise MediaRejected("El archivo no tiene video.")
        duration = info["seconds"]
        if duration > VIDEO_MAX_SECONDS + 0.5:
            raise MediaRejected(f"El video dura {duration:.0f} s: el máximo es 30 s. Graba de 5 a 10 segundos.")
        if duration < 1.0:
            raise MediaRejected("El video es muy corto: graba de 5 a 10 segundos.")
        # tramo elegido (por defecto, todo) y velocidad: la vuelta completa cabe en 3 s
        s0 = min(max(0.0, float(start or 0.0)), max(0.0, duration - 1.0))
        tramo = min(max(1.0, float(length or (duration - s0))), duration - s0)
        base = min(4.0, max(1.0, tramo / CLIP_SECONDS))
        factor = base * SPEED_FACTORS.get(speed, 1.0)
        need = CLIP_SECONDS + VIDEO_LOOP_FADE
        factor = max(0.5, min(factor, (duration - s0) / need - 1e-3))
        seg = need * factor
        total, fade = CLIP_FPS * CLIP_SECONDS, round(CLIP_FPS * VIDEO_LOOP_FADE)
        frames_needed = total + fade

        sample = _grab(exe, src, s0 + seg / 2)
        pw, ph = video_fit(sample, detect_dish(sample))
        fps = frames_needed / seg

        stab = stabilizer()
        trf = None
        if stab == "vidstab":
            trf_path = os.path.join(folder, "t.trf")
            detect = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-ss", f"{s0:.3f}", "-t", f"{seg + 0.2:.3f}", "-i", src,
                                     "-an", "-vf", f"fps={fps:.5f},scale={pw}:{ph},vidstabdetect=shakiness=6:accuracy=12:result=t.trf",
                                     "-f", "null", "-"], capture_output=True, timeout=300, cwd=folder)
            if detect.returncode == 0 and os.path.exists(trf_path):
                trf = "t.trf"
            else:
                stab = "deshake"
        vf = _vf_chain(fps, pw, ph, stab, trf)
        proc = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-ss", f"{s0:.3f}", "-t", f"{seg + 0.2:.3f}", "-i", src,
                               "-an", "-vf", vf, "-frames:v", str(frames_needed), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                              capture_output=True, timeout=600, cwd=folder)
        if proc.returncode != 0 or not proc.stdout:
            raise MediaRejected("No se pudo leer el video (formato no compatible).")
    step = pw * ph * 3
    count = len(proc.stdout) // step
    if count < total // 2:
        raise MediaRejected("El video es muy corto: graba de 5 a 10 segundos.")
    raw_frames = [Image.frombuffer("RGB", (pw, ph), proc.stdout[i * step:(i + 1) * step], "raw", "RGB", 0, 1) for i in range(count)]
    while len(raw_frames) < frames_needed:  # video justo: repite el ultimo (sin saltos raros)
        raw_frames.append(raw_frames[-1])

    middle = raw_frames[len(raw_frames) // 2]
    luts = tone_luts(middle)
    raw_frames = [f.point(luts[0] + luts[1] + luts[2]) for f in raw_frames]
    dish = detect_dish(raw_frames[len(raw_frames) // 2])
    mask = _dish_mask((pw, ph), dish) if background != "ninguno" and dish.source != "centro" else None
    x0 = _place(CLIP_W / 2 - dish.cx * pw, pw, CLIP_W)
    # alto: el plato SIEMPRE a ~38 % (lo que quede arriba o abajo lo cubre el relleno difuminado)
    y0 = round(DISH_Y * CLIP_H - dish.cy * ph)

    def place(frame):
        from PIL import ImageEnhance, ImageFilter

        if mask is not None:
            if background == "desenfocar":
                soft = frame.resize((max(8, pw // 4), max(8, ph // 4)), resample=2).filter(ImageFilter.GaussianBlur(radius=3)).resize((pw, ph), resample=2)
                soft = ImageEnhance.Brightness(soft).enhance(0.8)
            else:
                soft = ImageEnhance.Brightness(frame).enhance(0.62)
            frame = Image.composite(frame, soft, mask)
        canvas = _blur_fill(frame, CLIP_W, CLIP_H)
        canvas.paste(frame, (x0, y0))
        return canvas

    placed = [place(f) for f in raw_frames[:frames_needed]]
    frames = []
    for i in range(total):
        if i < fade:  # fundido del final con el inicio: el bucle no salta
            a = _ease((i + 1) / (fade + 1))
            frames.append(Image.blend(placed[total + i], placed[i], a))
        else:
            frames.append(placed[i])
    video, attempts = _encode_under(frames, VIDEO_TARGET_BYTES, VIDEO_TRIES)
    poster = webp(placed[fade], 80)
    return Clip(video=video, poster=poster, style="video", seconds=float(CLIP_SECONDS),
                encode_ms=round((time.perf_counter() - started) * 1000), attempts=attempts, sources=[dish.source],
                stabilizer=stab, speed=round(factor, 2), background=background)


def probe(video: bytes) -> dict:
    """Ancho, alto, fps y duracion del clip (para las pruebas y la salud)."""
    exe = ffmpeg_path()
    if not exe:
        raise MediaUnavailable("ffmpeg no está instalado en el servidor.")
    with tempfile.TemporaryDirectory(prefix="cx_probe_") as folder:
        path = os.path.join(folder, "c.mp4")
        with open(path, "wb") as handle:
            handle.write(video)
        proc = subprocess.run([exe, "-hide_banner", "-i", path], capture_output=True, text=True, timeout=30)
    info = proc.stderr or ""
    out: dict = {"audio": "Audio:" in info}
    import re

    size = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", info)
    if size:
        out["width"], out["height"] = int(size.group(1)), int(size.group(2))
    fps = re.search(r"(\d+(?:\.\d+)?) fps", info)
    if fps:
        out["fps"] = float(fps.group(1))
    dur = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", info)
    if dur:
        out["seconds"] = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3))
    out["h264"] = "h264" in info
    return out
