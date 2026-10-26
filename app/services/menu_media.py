"""Menu video: remasterizado de fotos y clips de 3 s, en el servidor y sin IA.

Todo es Pillow + ffmpeg (nada se inventa: el clip usa SOLO las fotos reales
del plato). Funciones puras (bytes -> bytes): no tocan la base ni el bucket;
eso lo hace app.services.menu_video.

- remaster(): luz y balance de blancos, contraste y saturacion suaves,
  nitidez ligera y recorte vertical 3:4 centrado en el plato (maximo
  810 x 1080), WebP. La original se guarda aparte, siempre (normalize()).
- make_clip(): 540 x 960, 25 fps, H.264 sin audio, faststart, ~3 s en bucle
  sin salto, idealmente menos de 400 KB, mas su portada WebP.
  Estilos: "zoom" (Acercamiento), "front_side" (Frente a perfil, necesita dos
  fotos) y "pan" (Paneo). "auto" = Frente a perfil con dos fotos, si no
  Acercamiento.
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
CLIP_W, CLIP_H, CLIP_FPS, CLIP_SECONDS = 540, 960, 25, 3
CLIP_TARGET_BYTES = 400 * 1024
STYLES = {"zoom": "Acercamiento", "front_side": "Frente a perfil", "pan": "Paneo"}


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


def dish_center(image) -> tuple[float, float]:
    """Centro aproximado del plato (0..1): donde hay mas color y mas bordes,
    mezclado con el centro de la foto para nunca irse a una esquina."""
    from PIL import ImageFilter

    small = image.copy()
    small.thumbnail((96, 96))
    sat = small.convert("HSV").split()[1]
    edges = small.convert("L").filter(ImageFilter.FIND_EDGES)
    w, h = small.size
    sat_px, edge_px = sat.tobytes(), edges.tobytes()  # modo L: un byte por pixel
    total = sx = sy = 0.0
    for index in range(w * h):
        weight = sat_px[index] * 0.6 + edge_px[index] * 0.4
        if weight <= 40:
            continue
        x, y = index % w, index // w
        total += weight
        sx += weight * (x + 0.5)
        sy += weight * (y + 0.5)
    if total <= 0:
        return 0.5, 0.5
    cx, cy = sx / total / w, sy / total / h
    return 0.5 + (cx - 0.5) * 0.6, 0.5 + (cy - 0.5) * 0.6


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
    cropped = crop_vertical(image, dish_center(image))
    if cropped.height > REMASTER_MAX_H:
        cropped = cropped.resize((round(REMASTER_MAX_H * cropped.width / cropped.height), REMASTER_MAX_H), resample=3)
    out = enhance(cropped)
    return Remastered(image=out, data=webp(out, 84), width=out.width, height=out.height)


def clip_source(image, use_remaster: bool = True):
    """Lo que entra al clip: la foto COMPLETA (el cuadro 9:16 la rellena con su
    propio fondo desenfocado, asi el plato nunca queda cortado), con la misma
    mejora de luz y color si se eligio la remasterizada."""
    copy = image.copy()
    copy.thumbnail((1440, 1440))
    return enhance(copy) if use_remaster else copy


# ------------------------------------------------------------------- clip ---
def _cover(image, w: int, h: int):
    scale = max(w / image.width, h / image.height)
    resized = image.resize((max(w, round(image.width * scale)), max(h, round(image.height * scale))), resample=3)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def compose(image, scale: float = 1.5):
    """Cuadro vertical 9:16 sin cortar el plato: la foto completa al ancho y,
    detras, la misma foto ampliada, desenfocada y oscurecida. Se arma a 1.5x
    para que el acercamiento se vea nitido."""
    from PIL import ImageEnhance, ImageFilter

    w, h = round(CLIP_W * scale), round(CLIP_H * scale)
    background = _cover(image, w, h).filter(ImageFilter.GaussianBlur(radius=round(22 * scale)))
    background = ImageEnhance.Brightness(background).enhance(0.55)
    fg_w = w
    fg_h = round(image.height * fg_w / image.width)
    if fg_h > h:
        fg_h = h
        fg_w = round(image.width * fg_h / image.height)
    foreground = image.resize((fg_w, fg_h), resample=3)
    background.paste(foreground, ((w - fg_w) // 2, (h - fg_h) // 2))
    return background


def _view(canvas, zoom: float, dx: float = 0.0):
    """Recorte del lienzo con acercamiento `zoom` y desplazamiento horizontal
    dx (fraccion del ancho), a 540 x 960 (subpixel: movimiento suave)."""
    w, h = canvas.size
    cw, ch = w / zoom, h / zoom
    cx = w / 2 + dx * w
    left = min(max(cx - cw / 2, 0.0), w - cw)
    top = (h - ch) / 2
    return canvas.resize((CLIP_W, CLIP_H), resample=3, box=(left, top, left + cw, top + ch))


def _ease(x: float) -> float:
    return (1 - math.cos(math.pi * min(1.0, max(0.0, x)))) / 2


def frame_at(style: str, t: float, front, side=None):
    """Cuadro en el instante t (0..1). En t=0 y t=1 el cuadro es el mismo:
    el bucle no salta."""
    from PIL import Image

    if style == "pan":
        return _view(front, 1.14, 0.055 * math.sin(2 * math.pi * t))
    if style == "front_side" and side is not None:
        if t < 0.4:
            return _view(front, 1 + 0.08 * _ease(t / 0.4))
        if t < 0.5:
            return Image.blend(_view(front, 1.08), _view(side, 1.08), _ease((t - 0.4) / 0.1))
        if t < 0.85:
            return _view(side, 1.08 - 0.08 * _ease((t - 0.5) / 0.35))
        return Image.blend(_view(side, 1.0), _view(front, 1.0), _ease((t - 0.85) / 0.15))
    return _view(front, 1 + 0.10 * (1 - math.cos(2 * math.pi * t)) / 2)


def resolve_style(style: str, has_side: bool) -> str:
    style = style if style in STYLES else "auto"
    if style == "auto":
        return "front_side" if has_side else "zoom"
    if style == "front_side" and not has_side:
        return "zoom"
    return style


@dataclass
class Clip:
    video: bytes
    poster: bytes
    style: str
    seconds: float
    encode_ms: int
    attempts: list = field(default_factory=list)


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
            proc = subprocess.run(args, input=b"".join(f.tobytes() for f in frames), capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise MediaUnavailable("ffmpeg no pudo crear el clip.") from error
        if proc.returncode != 0 or not os.path.exists(out):
            raise MediaUnavailable("ffmpeg no pudo crear el clip.")
        with open(out, "rb") as handle:
            return handle.read()


def make_clip(front_image, side_image=None, style: str = "auto") -> Clip:
    """front_image/side_image: las fotos ya elegidas (remasterizada u original)."""
    started = time.perf_counter()
    chosen = resolve_style(style, side_image is not None)
    front = compose(front_image)
    side = compose(side_image) if side_image is not None and chosen == "front_side" else None
    total = CLIP_FPS * CLIP_SECONDS
    frames = [frame_at(chosen, i / total, front, side).convert("RGB") for i in range(total)]
    attempts = []
    video = b""
    for crf, maxrate in ((26, "1000k"), (30, "800k"), (34, "600k")):
        video = _encode(frames, crf, maxrate)
        attempts.append({"crf": crf, "bytes": len(video)})
        if len(video) <= CLIP_TARGET_BYTES:
            break
    poster = webp(frames[0], 78)
    return Clip(video=video, poster=poster, style=chosen, seconds=float(CLIP_SECONDS),
                encode_ms=round((time.perf_counter() - started) * 1000), attempts=attempts)


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
