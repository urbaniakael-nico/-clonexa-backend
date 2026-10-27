"""Videos y fotos de prueba de Menu video (sinteticos, sin datos reales):
un plato redondo con comida de colores que gira sobre una mesa, con un
temblor leve de la mano, en vertical, horizontal o HEVC (como el iPhone)."""
from __future__ import annotations

import io
import math
import os
import random
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter

from app.services import menu_media as mm


def plate_image(w: int = 900, h: int = 700, angle: float = 0.0, plate: float = 0.62, cx: float = 0.5, cy: float = 0.52) -> Image.Image:
    img = Image.new("RGB", (w, h), (92, 64, 44))
    d = ImageDraw.Draw(img)
    for i in range(0, w, 40):  # vetas de la mesa
        d.line([(i, 0), (i + 60, h)], fill=(104, 72, 50), width=6)
    r = plate * min(w, h) / 2
    x, y = cx * w, cy * h
    d.ellipse((x - r, y - r, x + r, y + r), fill=(238, 236, 230), outline=(170, 170, 170), width=4)
    food = Image.new("RGBA", (int(2 * r), int(2 * r)), (0, 0, 0, 0))
    fd = ImageDraw.Draw(food)
    rr = r * 0.62
    fd.ellipse((r - rr, r - rr, r + rr, r + rr), fill=(196, 110, 40, 255))
    rnd = random.Random(7)
    for _ in range(26):
        a, dist = rnd.random() * 2 * math.pi, rnd.random() * rr * 0.8
        px, py = r + dist * math.cos(a), r + dist * math.sin(a)
        s = 6 + rnd.random() * 16
        fd.ellipse((px - s, py - s, px + s, py + s), fill=rnd.choice([(46, 140, 60, 255), (210, 40, 40, 255), (250, 210, 60, 255)]))
    food = food.rotate(angle, resample=Image.BICUBIC)
    img.paste(food, (int(x - r), int(y - r)), food)
    return img


def dish_video(kind: str = "vertical", seconds: float = 6.0, fps: int = 30, shake: float = 6.0, hevc: bool = False,
               audio: bool = True) -> bytes:
    """MP4 (H.264) o MOV (HEVC) del plato dando una vuelta en `seconds`."""
    w, h = (720, 1280) if kind == "vertical" else (1280, 720)
    frames = int(seconds * fps)
    rnd = random.Random(3)
    exe = mm.ffmpeg_path()
    with tempfile.TemporaryDirectory(prefix="cx_fx_") as folder:
        out = os.path.join(folder, "in.mov" if hevc else "in.mp4")
        args = [exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                "-r", str(fps), "-i", "-"]
        if audio:
            args += ["-f", "lavfi", "-t", f"{seconds}", "-i", "anullsrc=r=44100:cl=mono", "-c:a", "aac", "-shortest"]
        if hevc:
            args += ["-c:v", "libx265", "-tag:v", "hvc1", "-x265-params", "log-level=error", "-preset", "ultrafast", "-crf", "30"]
        else:
            args += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"]
        args += ["-pix_fmt", "yuv420p", out]
        big = plate_image(int(w * 1.1), int(h * 1.1), plate=0.55 if kind == "vertical" else 0.75)
        payload = bytearray()
        for i in range(frames):
            angle = 360.0 * i / frames
            frame = plate_image(int(w * 1.1), int(h * 1.1), angle, plate=0.55 if kind == "vertical" else 0.75)
            dx, dy = rnd.uniform(-shake, shake), rnd.uniform(-shake, shake)
            left, top = int(w * 0.05 + dx), int(h * 0.05 + dy)
            payload += frame.crop((left, top, left + w, top + h)).tobytes()
        del big
        proc = subprocess.run(args, input=bytes(payload), capture_output=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-400:]
        with open(out, "rb") as handle:
            return handle.read()


def long_video(seconds: float = 31.0) -> bytes:
    exe = mm.ffmpeg_path()
    with tempfile.TemporaryDirectory(prefix="cx_fx_") as folder:
        out = os.path.join(folder, "long.mp4")
        subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=orange:s=160x284:d={seconds}:r=5",
                        "-c:v", "libx264", "-preset", "ultrafast", out], check=True, capture_output=True, timeout=120)
        with open(out, "rb") as handle:
            return handle.read()


def jpeg(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def frames_of(video: bytes, w: int = 180, h: int = 320) -> list:
    """Cuadros del clip en pequeño (para medir saltos y bordes)."""
    exe = mm.ffmpeg_path()
    with tempfile.TemporaryDirectory(prefix="cx_fx_") as folder:
        path = os.path.join(folder, "c.mp4")
        with open(path, "wb") as handle:
            handle.write(video)
        proc = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-i", path, "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                               "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=120)
    step = w * h * 3
    return [Image.frombytes("RGB", (w, h), proc.stdout[i:i + step]) for i in range(0, len(proc.stdout) - step + 1, step)]


def diff(a: Image.Image, b: Image.Image) -> float:
    """Diferencia media 0..255 entre dos cuadros."""
    from PIL import ImageChops, ImageStat

    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def blur(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(2))
