"""QR y piezas (interruptor carta_qr_piezas del modulo carta, apagado por
defecto): una sola carta (la de video si carta_video esta encendido; si no,
la de fotos) con 4 tipos de QR, y piezas listas para imprimir o publicar.

Tipos (cada uno se enciende/apaga por empresa y su enlace se regenera: el
viejo deja de funcionar):
- "mesa": el QR de cada mesa de siempre (/ordenar?mesa=...&q=...). El pedido
  va a cocina y a la cuenta de la mesa en Caja. Mientras nunca se regenere,
  los QR de mesa ya impresos (sin q) siguen sirviendo.
- "domicilio": carta -> pedido -> datos (nombre, celular, direccion, barrio,
  referencia, pago contra entrega, nota y autorizacion de datos) -> modulo
  Domicilios y cocina. Sin pasarela de pagos.
- "llevar": nombre, celular y hora aproximada de recogida -> Caja y cocina.
- "mesero": la misma carta en el celular del mesero, SOLO con su sesion de
  mesero (validada en el servidor); agrega a la cuenta de su mesa abierta.

QR visual: logo de la empresa al centro, colores de marca, correccion de
errores alta; antes de entregarlo se vuelve a LEER con el lector de QR de
OpenCV. Si no se lee, version oscura sobre claro; si tampoco, sin logo.
Piezas: hablador de mesa (PDF 10x15 cm), sticker de domicilio (PDF 8x8 cm)
y pieza de Instagram (PNG 1080x1350). Todo se arma al pedirlo (nada pesado
se guarda en Postgres ni en el bucket).
"""
from __future__ import annotations

import io
import logging
import os
import secrets
import time
import uuid
import zipfile
from typing import Any, Optional
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("clonexa.carta_links")

FLAG = "carta_qr_piezas"
KINDS = ("mesa", "domicilio", "llevar", "mesero")
LABELS = {"mesa": "Mesa", "domicilio": "Domicilio", "llevar": "Para llevar", "mesero": "Mesero"}
QR_MODULE_CODES = ("qr", "mesa_qr", "mesas_qr", "qr_mesas", "hospitality_qr", "voting_qr")
DPI = 300
POLICY_PATH = "/politica-de-datos"
# limite de pedidos por minuto (Domicilio y Para llevar)
RATE_PER_IP = 4
RATE_PER_PHONE = 2
_RATE: dict[str, list[float]] = {}


def _uuid(value: Any) -> str:
    return str(uuid.UUID(str(value)))


def _token() -> str:
    return secrets.token_urlsafe(18)


# ------------------------------------------------------------- ajustes ---
async def _module(db: AsyncSession, company_id: Any) -> Optional[dict]:
    from app.services import menu_video

    return await menu_video.carta_module(db, company_id)


async def enabled(db: AsyncSession, company_id: Any) -> bool:
    try:
        async with db.begin_nested():
            module = await _module(db, company_id)
    except Exception as exc:
        log.warning("qr y piezas: no se pudo leer el modulo carta: %s", type(exc).__name__)
        return False
    return bool(module and module["enabled"] and module["settings"].get(FLAG) is True)


async def _save(db: AsyncSession, company_id: Any, links: dict) -> None:
    import json

    await db.execute(text("""
        UPDATE company_modules cm SET settings = COALESCE(cm.settings, '{}'::jsonb) || jsonb_build_object('qr_links', CAST(:v AS jsonb))
        FROM modules m WHERE m.id = cm.module_id AND cm.company_id = CAST(:c AS uuid) AND LOWER(m.code) = 'carta'
    """), {"c": _uuid(company_id), "v": json.dumps(links)})


def _normalize(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for kind in KINDS:
        entry = raw.get(kind) if isinstance(raw.get(kind), dict) else {}
        out[kind] = {"on": entry.get("on", True) is not False, "token": str(entry.get("token") or ""),
                     "rotated": entry.get("rotated") is True}
    return out


async def links(db: AsyncSession, company_id: Any, create: bool = True) -> dict:
    """Estado de los 4 tipos; crea los enlaces que falten (una sola vez)."""
    module = await _module(db, company_id) or {"settings": {}}
    current = _normalize(module["settings"].get("qr_links"))
    if create and any(not current[k]["token"] for k in KINDS):
        for kind in KINDS:
            current[kind]["token"] = current[kind]["token"] or _token()
        await _save(db, company_id, current)
    return current


async def set_on(db: AsyncSession, company_id: Any, kind: str, on: bool) -> dict:
    current = await links(db, company_id)
    current[kind]["on"] = bool(on)
    await _save(db, company_id, current)
    return current


async def regenerate(db: AsyncSession, company_id: Any, kind: str) -> dict:
    """Enlace nuevo: el anterior (y, en mesa, los QR viejos sin codigo) deja de servir."""
    current = await links(db, company_id)
    current[kind]["token"] = _token()
    current[kind]["rotated"] = True
    await _save(db, company_id, current)
    return current


async def by_token(db: AsyncSession, token: str, kinds: tuple = ("domicilio", "llevar", "mesero")) -> Optional[dict]:
    """Empresa y tipo de un enlace publico. None si no existe, esta apagado o
    la empresa no tiene el interruptor."""
    token = str(token or "").strip()
    if len(token) < 16 or len(token) > 64:
        return None
    for kind in kinds:
        row = (await db.execute(text("""
            SELECT cm.company_id::text AS company_id, cm.settings
            FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE LOWER(m.code) = 'carta' AND cm.enabled = TRUE
              AND cm.settings->'qr_links'->:k->>'token' = :t
            LIMIT 1
        """), {"k": kind, "t": token})).mappings().first()
        if not row:
            continue
        settings = row["settings"] if isinstance(row["settings"], dict) else {}
        if settings.get(FLAG) is not True:
            return None
        entry = _normalize(settings.get("qr_links"))[kind]
        if not entry["on"]:
            return {"company_id": row["company_id"], "kind": kind, "off": True}
        return {"company_id": row["company_id"], "kind": kind, "off": False}
    return None


class LinkRefused(Exception):
    def __init__(self, message: str, status: int = 403):
        super().__init__(message)
        self.status = status


async def mesa_guard(db: AsyncSession, company_id: Any, code: Optional[str]) -> None:
    """QR de mesa: solo para empresas con el interruptor. Apagado -> no se
    pide; regenerado -> solo el enlace nuevo. Sin interruptor, como hoy."""
    if not await enabled(db, company_id):
        return
    entry = (await links(db, company_id, create=False))["mesa"]
    if not entry["on"]:
        raise LinkRefused("El pedido por el QR de la mesa está apagado en este restaurante. Pídele al mesero.")
    if entry["rotated"] and entry["token"] and str(code or "") != entry["token"]:
        raise LinkRefused("Este QR ya no es válido. Escanea el QR nuevo de la mesa.")


def rate_ok(*keys: str, limit: int, window: float = 60.0) -> bool:
    """Ventana deslizante en memoria (por IP o por celular)."""
    now = time.monotonic()
    ok = True
    for key in keys:
        hits = [t for t in _RATE.get(key, []) if now - t < window]
        if len(hits) >= limit:
            ok = False
        _RATE[key] = hits
    if ok:
        for key in keys:
            _RATE[key].append(now)
    return ok


# --------------------------------------------------------------- mesas ---
async def mesa_labels(db: AsyncSession, company_id: Any) -> list[str]:
    """Las mesas configuradas (mismo dato que el QR de mesas del portal; 12 por defecto)."""
    rows = (await db.execute(text("""
        SELECT LOWER(m.code) AS code, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND cm.enabled = TRUE
    """), {"c": _uuid(company_id)})).mappings().all()
    count = 12
    for row in rows:
        code = "".join(ch if ch.isalnum() else "_" for ch in str(row["code"] or "")).strip("_")
        if code not in QR_MODULE_CODES:
            continue
        settings = row["settings"] if isinstance(row["settings"], dict) else {}
        raw = settings.get("qr_config") if isinstance(settings.get("qr_config"), dict) else (
            settings.get("hospitality_qr") if isinstance(settings.get("hospitality_qr"), dict) else settings)
        try:
            cap = int(float(raw.get("max_capacity") or raw.get("capacity") or raw.get("limit") or raw.get("table_count") or raw.get("count") or 12))
            want = int(float(raw.get("table_count") or raw.get("count") or raw.get("visible_count") or cap))
            count = max(1, min(cap, want, 200))
        except (TypeError, ValueError):
            count = 12
        break
    return [f"Mesa {i}" for i in range(1, count + 1)]


def urls(base: str, company_id: str, current: dict, tables: list[str]) -> dict:
    base = base.rstrip("/")
    out = {
        "domicilio": f"{base}/pedir?k={current['domicilio']['token']}",
        "llevar": f"{base}/pedir?k={current['llevar']['token']}",
        "mesero": f"{base}/carta-mesero?company_id={company_id}&k={current['mesero']['token']}",
        "mesas": [{"label": t, "url": f"{base}/ordenar?company_id={company_id}&mesa={quote(t)}&q={current['mesa']['token']}"} for t in tables],
    }
    return out


# ------------------------------------------------------------- color ---
def _rgb(value: str, default=(17, 17, 17)) -> tuple:
    value = str(value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return default


def _lum(rgb: tuple) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple, b: tuple) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(bg: tuple) -> tuple:
    return (255, 255, 255) if contrast(bg, (255, 255, 255)) >= contrast(bg, (17, 17, 17)) else (17, 17, 17)


def _hex(rgb: tuple) -> str:
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb[:3])


# ---------------------------------------------------------------- QR ---
def read_qr(image) -> str:
    """Lo que lee el lector de QR de OpenCV en la imagen ("" si no lee)."""
    try:
        import cv2
        import numpy as np
    except Exception:  # pragma: no cover
        return ""
    gray = np.asarray(image.convert("L"))
    _t, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    detector = cv2.QRCodeDetector()
    for base in (gray, binary):
        for scale in (1.0, 0.5, 0.35):
            candidate = base if scale == 1.0 else cv2.resize(base, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            try:
                value, _points, _ = detector.detectAndDecode(candidate)
            except Exception:
                value = ""
            if value:
                return value
    return ""


def read_piece(image) -> str:
    """Lee el QR de una pieza ya armada: la pieza entera y, si no, la zona del
    QR con su margen (como la enfoca la camara del celular)."""
    value = read_qr(image)
    box = getattr(image, "qr_box", None)
    if value or not box:
        return value
    x0, y0, x1, y1 = box
    pad = int((x1 - x0) * 0.12)
    return read_qr(image.crop((max(0, x0 - pad), max(0, y0 - pad), min(image.width, x1 + pad), min(image.height, y1 + pad))))


def _logo_image(logo: Optional[bytes]):
    if not logo:
        return None
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(logo))
        img.load()
        return img.convert("RGBA")
    except Exception:
        return None


def qr_image(url: str, primary: str = "#111111", logo: Optional[bytes] = None, size: int = 1000) -> tuple[Any, dict]:
    """QR con logo al centro y color de marca (correccion H), YA verificado con
    el lector. Variantes en orden: marca+logo -> oscuro+logo -> oscuro sin logo."""
    import segno
    from PIL import Image, ImageDraw

    brand = _rgb(primary)
    dark = brand if contrast(brand, (255, 255, 255)) >= 4.5 else (17, 17, 17)
    logo_img = _logo_image(logo)
    variants = []
    if logo_img is not None:
        variants += [("marca_logo", dark, True), ("oscuro_logo", (17, 17, 17), True)]
    else:
        variants += [("marca", dark, False)]
    variants.append(("oscuro", (17, 17, 17), False))
    seen = set()
    for name, color, with_logo in variants:
        if (color, with_logo) in seen:
            continue
        seen.add((color, with_logo))
        qr = segno.make(url, error="h", micro=False)
        buf = io.BytesIO()
        qr.save(buf, kind="png", scale=20, border=4, dark=_hex(color), light="#ffffff")
        img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB").resize((size, size), Image.NEAREST)
        if with_logo and logo_img is not None:
            box = int(size * 0.22)
            pad = int(box * 0.12)
            plate = Image.new("RGBA", (box + 2 * pad, box + 2 * pad), (0, 0, 0, 0))
            ImageDraw.Draw(plate).rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=int(box * 0.18), fill=(255, 255, 255, 255))
            mark = logo_img.copy()
            mark.thumbnail((box, box))
            plate.paste(mark, ((plate.width - mark.width) // 2, (plate.height - mark.height) // 2), mark)
            img.paste(plate, ((size - plate.width) // 2, (size - plate.height) // 2), plate)
        if read_qr(img) == url:
            return img, {"variant": name, "verified": True, "color": _hex(color)}
    return img, {"variant": "oscuro", "verified": False, "color": "#111111"}


def png(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------ piezas ---
def _font(size: int, bold: bool = True):
    from PIL import ImageFont

    try:
        import reportlab

        folder = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
        return ImageFont.truetype(os.path.join(folder, "VeraBd.ttf" if bold else "Vera.ttf"), size)
    except Exception:  # pragma: no cover
        return ImageFont.load_default()


def _fit_text(draw, text_value: str, width: int, start: int, bold: bool = True):
    size = start
    while size > 14:
        font = _font(size, bold)
        if draw.textlength(text_value, font=font) <= width:
            return font
        size -= 4
    return _font(14, bold)


def _center(draw, y: int, text_value: str, width: int, font, fill) -> int:
    w = draw.textlength(text_value, font=font)
    draw.text(((width - w) / 2, y), text_value, font=font, fill=fill)
    box = draw.textbbox((0, 0), text_value, font=font)
    return y + (box[3] - box[1])


def _paste_logo(canvas, logo: Optional[bytes], box: tuple, plate_color=(255, 255, 255)):
    from PIL import Image, ImageDraw

    img = _logo_image(logo)
    if img is None:
        return False
    x0, y0, x1, y1 = box
    mark = img.copy()
    mark.thumbnail((x1 - x0, y1 - y0))
    plate = Image.new("RGBA", (mark.width + 24, mark.height + 24), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=18, fill=plate_color + (255,))
    plate.paste(mark, (12, 12), mark)
    canvas.paste(plate, (x0 + (x1 - x0 - plate.width) // 2, y0 + (y1 - y0 - plate.height) // 2), plate)
    return True


def _cm(value: float) -> int:
    return round(value / 2.54 * DPI)


def hablador(company: dict, table: str, url: str, qr) -> Any:
    """Hablador de mesa 10x15 cm: logo, "Mesa N", "Escanea y pide desde tu celular", QR."""
    from PIL import Image, ImageDraw

    W, H = _cm(10), _cm(15)
    brand = _rgb(company.get("primary"))
    ink = text_on(brand)
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    band = int(H * 0.30)
    d.rectangle((0, 0, W, band), fill=brand)
    if not _paste_logo(img, company.get("logo"), (W // 2 - 170, 40, W // 2 + 170, 260)):
        _center(d, 110, company.get("name") or "", W, _fit_text(d, company.get("name") or "", W - 120, 72), ink)
    y = _center(d, band - 170, table, W, _fit_text(d, table, W - 120, 150), ink)
    _ = y
    qr_size = int(W * 0.72)
    img.paste(qr.resize((qr_size, qr_size), 0), ((W - qr_size) // 2, band + 60))
    img.qr_box = ((W - qr_size) // 2, band + 60, (W + qr_size) // 2, band + 60 + qr_size)
    y = band + 60 + qr_size + 40
    y = _center(d, y, "Escanea y pide", W, _font(76), (17, 17, 17)) + 20
    _center(d, y, "desde tu celular", W, _font(60, False), (60, 60, 60))
    _center(d, H - 90, company.get("name") or "", W, _fit_text(d, company.get("name") or "", W - 120, 44, False), (90, 90, 90))
    return img


def sticker(company: dict, url: str, qr) -> Any:
    """Sticker de domicilio 8x8 cm: "Pide a domicilio" y el QR."""
    from PIL import Image, ImageDraw

    W = H = _cm(8)
    brand = _rgb(company.get("primary"))
    ink = text_on(brand)
    img = Image.new("RGB", (W, H), brand)
    d = ImageDraw.Draw(img)
    y = _center(d, 50, "Pide a domicilio", W, _fit_text(d, "Pide a domicilio", W - 80, 96), ink)
    qr_size = int(W * 0.62)
    top = y + 40
    d.rounded_rectangle(((W - qr_size) // 2 - 22, top - 22, (W + qr_size) // 2 + 22, top + qr_size + 22), radius=36, fill=(255, 255, 255))
    img.paste(qr.resize((qr_size, qr_size), 0), ((W - qr_size) // 2, top))
    img.qr_box = ((W - qr_size) // 2, top, (W + qr_size) // 2, top + qr_size)
    _center(d, top + qr_size + 46, company.get("name") or "", W, _fit_text(d, company.get("name") or "", W - 80, 54), ink)
    return img


def instagram(company: dict, url: str, qr, photo: Optional[bytes] = None, dish: str = "") -> Any:
    """Pieza de Instagram 1080x1350: foto o portada de un plato destacado, "Pide aquí" y el QR."""
    from PIL import Image, ImageDraw, ImageFilter, ImageOps

    W, H = 1080, 1350
    brand = _rgb(company.get("primary"))
    ink = text_on(brand)
    img = Image.new("RGB", (W, H), brand)
    top = 830
    pic = None
    if photo:
        try:
            pic = Image.open(io.BytesIO(photo))
            pic.load()
            pic = ImageOps.exif_transpose(pic).convert("RGB")
        except Exception:
            pic = None
    if pic is not None:
        img.paste(ImageOps.fit(pic, (W, top), method=Image.LANCZOS), (0, 0))
        shade = Image.new("L", (W, 180), 0)
        for i in range(180):
            shade.putpixel((0, i), int(170 * i / 179))
        shade = shade.resize((W, 180))
        img.paste(Image.new("RGB", (W, 180), (0, 0, 0)), (0, top - 180), shade)
    d = ImageDraw.Draw(img)
    if dish and pic is not None:
        d.text((48, top - 110), dish[:40], font=_fit_text(d, dish[:40], W - 96, 60), fill=(255, 255, 255))
    _paste_logo(img, company.get("logo"), (36, 36, 236, 236))
    qr_size = 400
    qx, qy = W - qr_size - 60, top + 30
    d.rounded_rectangle((qx - 18, qy - 18, qx + qr_size + 18, qy + qr_size + 18), radius=30, fill=(255, 255, 255))
    img.paste(qr.resize((qr_size, qr_size), 0), (qx, qy))
    img.qr_box = (qx, qy, qx + qr_size, qy + qr_size)
    d.text((60, top + 80), "Pide aquí", font=_font(110), fill=ink)
    d.text((60, top + 230), "Escanea el código", font=_font(44, False), fill=ink)
    name = company.get("name") or ""
    d.text((60, top + 300), name[:28], font=_fit_text(d, name[:28], qx - 100, 50), fill=ink)
    _ = ImageFilter
    return img


def pdf(images: list, cm_w: float, cm_h: float) -> bytes:
    """PDF del tamaño exacto (cm) con una pagina por imagen (300 dpi)."""
    buf = io.BytesIO()
    first, rest = images[0], images[1:]
    first.save(buf, format="PDF", resolution=DPI, save_all=True, append_images=rest)
    return buf.getvalue()


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def slug(value: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return "-".join("".join(ch if ch.isalnum() else " " for ch in plain).split()) or "pieza"


def policy_html(company_name: str) -> str:
    """Politica de tratamiento de datos del pedido (Ley 1581 de 2012). El
    responsable es el restaurante; Clonexa es la plataforma que lo procesa."""
    import html as _html

    name = _html.escape(company_name or "el restaurante")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Política de datos · {name}</title>
<style>body{{margin:0;background:#f8fafc;color:#111827;font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:680px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:24px;line-height:1.25}}h2{{font-size:18px;margin-top:24px}}</style></head>
<body><main>
<h1>Política de tratamiento de datos personales de los pedidos</h1>
<p><b>Responsable:</b> {name}. Los pedidos se hacen por la plataforma Clonexa, que trata los datos por cuenta del restaurante.</p>
<h2>Qué datos usamos</h2>
<p>Nombre, celular, dirección, barrio y referencia de entrega (domicilio), hora de recogida (para llevar), la forma de pago elegida y la nota del pedido. No pedimos datos de tarjetas.</p>
<h2>Para qué</h2>
<p>Solo para gestionar tu pedido: prepararlo, entregarlo o tenerlo listo para recoger, contactarte si hace falta y llevar el registro de la venta del restaurante.</p>
<h2>Tus derechos</h2>
<p>Como titular de los datos (Ley 1581 de 2012 y sus normas reglamentarias) puedes conocer, actualizar, rectificar y pedir que se supriman tus datos, revocar la autorización y pedir prueba de ella, saber cómo se han usado y presentar quejas ante la Superintendencia de Industria y Comercio. Para ejercerlos, comunícate directamente con {name}.</p>
<h2>Autorización</h2>
<p>Al marcar la casilla «Autorizo el tratamiento de mis datos para gestionar mi pedido» aceptas este uso. Sin esa autorización no se puede enviar un pedido a domicilio.</p>
</main></body></html>"""
