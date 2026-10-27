"""Menu video: remasterizado de fotos y clips de 3 s, en el servidor y sin IA.

Todo es Pillow + ffmpeg (nada se inventa: el clip usa SOLO las fotos reales
del plato). Funciones puras (bytes -> bytes): no tocan la base ni el bucket;
eso lo hace app.services.menu_video.

- detect_dish(): donde esta el plato (OpenCV: circulo/elipse; si no, la
  zona con mas color y contraste; si no, el centro). Nunca falla.
- remaster(): luz y balance de blancos, contraste y saturacion suaves,
  nitidez ligera y recorte vertical 3:4 SOLO si el plato completo cabe,
  WebP. La original se guarda aparte, siempre (normalize()).
- make_clip(): 720 x 1280, 25 fps, H.264 sin audio, faststart, 3 s en bucle
  sin salto, idealmente menos de 600 KB, mas su portada (plato completo).
  La foto ENTERA cabe en el cuadro (relleno: la misma foto agrandada y
  difuminada), centro del plato a ~38 % del alto, acercamiento suave de
  maximo 8 % que nunca saca el plato del cuadro; 1 a 3 fotos (desde arriba ->
  frente -> perfil) con fundido de 0,3 s.
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
FADE_SECONDS = 0.3      # fundido entre fotos
ROLES = ("top", "front", "side")  # orden del clip: desde arriba -> frente -> perfil
ROLE_LABELS = {"top": "Desde arriba", "front": "Frente", "side": "Perfil"}
STYLES = {"suave": "Acercamiento suave"}


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


@dataclass
class Shot:
    """Una foto armada en el cuadro vertical: lienzo, centro del plato y su
    acercamiento maximo seguro (el plato nunca sale del cuadro)."""
    canvas: object
    cx: float
    cy: float
    zmax: float
    photo_box: tuple
    dish_box: tuple
    source: str


def compose(image, dish: Optional[Dish] = None, scale: float = CANVAS_SCALE) -> Shot:
    """La foto ENTERA dentro del cuadro 9:16; arriba y abajo, la misma foto
    agrandada y difuminada (nunca bordes negros). El centro del plato queda a
    ~38 % del alto (encima de la tarjeta del precio del modo video)."""
    from PIL import ImageEnhance, ImageFilter

    dish = dish or detect_dish(image)
    W, H = round(CLIP_W * scale), round(CLIP_H * scale)
    background = _cover(image, W, H).filter(ImageFilter.GaussianBlur(radius=round(26 * scale)))
    background = ImageEnhance.Brightness(background).enhance(0.7)
    fit = min(W / image.width, VISIBLE_H * H / image.height)
    pw, ph = round(image.width * fit), round(image.height * fit)
    x0 = (W - pw) // 2
    y0 = round(min(max(DISH_Y * H - dish.cy * ph, 0), H - ph))
    background.paste(image.resize((pw, ph), resample=3), (x0, y0))
    dcx, dcy = x0 + dish.cx * pw, y0 + dish.cy * ph
    dw, dh = dish.w * pw * (1 + DISH_MARGIN), dish.h * ph * (1 + DISH_MARGIN)
    zmax = max(1.0, min(MAX_ZOOM, W / max(dw, 1), H / max(dh, 1)))
    return Shot(canvas=background, cx=dcx, cy=dcy, zmax=zmax, photo_box=(x0, y0, x0 + pw, y0 + ph),
                dish_box=(dcx - dish.w * pw / 2, dcy - dish.h * ph / 2, dcx + dish.w * pw / 2, dcy + dish.h * ph / 2),
                source=dish.source)


def view_box(shot: Shot, zoom: float) -> tuple[float, float, float, float]:
    """Recorte del lienzo con acercamiento `zoom` hacia el plato, sin salirse."""
    W, H = shot.canvas.size
    cw, ch = W / zoom, H / zoom
    left = min(max(shot.cx - cw / 2, 0.0), W - cw)
    top = min(max(shot.cy - ch / 2, 0.0), H - ch)
    return left, top, left + cw, top + ch


def render(shot: Shot, zoom: float):
    return shot.canvas.resize((CLIP_W, CLIP_H), resample=3, box=view_box(shot, zoom))


def _ease(x: float) -> float:
    return (1 - math.cos(math.pi * min(1.0, max(0.0, x)))) / 2


def zoom_at(shot: Shot, u: float) -> float:
    """Arranca con el plato completo, se acerca suave (max. 8 %) y vuelve."""
    return 1 + (shot.zmax - 1) * (1 - math.cos(2 * math.pi * u)) / 2


def frame_at(shots: list, index: int, total: int = CLIP_FPS * CLIP_SECONDS):
    """Cuadro `index` de `total`. Cada foto ocupa total/n cuadros; entre fotos,
    fundido de ~0,3 s. El ultimo cuadro empalma con el primero (bucle sin salto)."""
    from PIL import Image

    n = len(shots)
    seg = total / n
    k = min(n - 1, int(index // seg))
    u = (index - k * seg) / seg
    current = render(shots[k], zoom_at(shots[k], u))
    if n == 1:
        return current
    fade = CLIP_FPS * FADE_SECONDS
    into = index - k * seg
    if into < fade:
        prev = shots[(k - 1) % n]
        # la anterior sigue su movimiento justo donde termino (vista completa): sin saltos
        return Image.blend(render(prev, zoom_at(prev, into / seg)), current, _ease(into / fade))
    return current


def resolve_style(style: str = "auto", has_side: bool = False) -> str:
    """Un solo movimiento (acercamiento suave, max. 8 %); los estilos viejos
    ("zoom", "pan", "front_side") se rehacen con el proceso nuevo."""
    return "suave"


@dataclass
class Clip:
    video: bytes
    poster: bytes
    style: str
    seconds: float
    encode_ms: int
    attempts: list = field(default_factory=list)
    sources: list = field(default_factory=list)


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


def make_clip(images, side_image=None, style: str = "auto") -> Clip:
    """images: las fotos del plato YA en orden (desde arriba -> frente ->
    perfil), 1 a 3. Acepta tambien make_clip(frente, perfil) por compatibilidad."""
    if not isinstance(images, (list, tuple)):
        images = [images] + ([side_image] if side_image is not None else [])
    images = [i for i in images if i is not None][:3]
    if not images:
        raise MediaRejected("El plato no tiene fotos.")
    started = time.perf_counter()
    shots = [compose(image) for image in images]
    total = CLIP_FPS * CLIP_SECONDS
    frames = [frame_at(shots, i, total).convert("RGB") for i in range(total)]
    attempts = []
    video = b""
    for crf, maxrate in ((24, "1500k"), (27, "1300k"), (30, "1100k"), (34, "900k")):
        video = _encode(frames, crf, maxrate)
        attempts.append({"crf": crf, "bytes": len(video)})
        if len(video) <= CLIP_TARGET_BYTES:
            break
    poster = webp(render(shots[0], 1.0), 80)  # portada: el primer plato completo
    return Clip(video=video, poster=poster, style=resolve_style(style), seconds=float(CLIP_SECONDS),
                encode_ms=round((time.perf_counter() - started) * 1000), attempts=attempts, sources=[s.source for s in shots])


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
