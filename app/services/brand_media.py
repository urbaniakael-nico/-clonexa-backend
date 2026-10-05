"""Imagenes de marca en el bucket de Railway (clonexa-media).

- Solo PNG, JPG y WebP, reconocidos por su firma (nunca por el nombre ni el
  tipo que manda el navegador). SVG y todo lo demas se rechaza.
- Cada imagen se vuelve a codificar (sin metadatos), se reduce a un maximo
  de lado y se guarda en WebP, mas una version liviana para equipos lentos.
- Tope de peso por archivo y de espacio por empresa.
- Las claves llevan el company_id y se derivan de ids validados:
  brand/{company_id}/{image_id}.webp y brand/{company_id}/{image_id}-lite.webp.
  Leer o borrar exige que la fila de company_brand_images sea de ESA empresa.
- Si faltan las variables del bucket o el bucket no responde, el backend
  arranca igual: solo falla la subida, con StorageUnavailable (503 claro).

Limites configurables por variable de entorno (valores aprobados por el dueño):
CLONEXA_BRAND_MAX_UPLOAD_MB=5, CLONEXA_BRAND_MAX_PX=1920,
CLONEXA_BRAND_LITE_PX=640, CLONEXA_BRAND_QUOTA_MB=25.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

ENV_PREFIX = "CLONEXA_BUCKET_"
REQUIRED_ENV = ("NAME", "ENDPOINT", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY")
MAX_PIXELS = 40_000_000  # defensa contra imagenes "bomba" (p. ej. 20000 x 20000)


class StorageUnavailable(Exception):
    """El bucket no esta configurado o no responde."""


class ImageRejected(ValueError):
    """La imagen no cumple las reglas (tipo, peso, tope de la empresa)."""


def _env_number(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(str(os.getenv(name, "")).strip() or default)
    except ValueError:
        return default
    return min(high, max(low, value))


@dataclass(frozen=True)
class Limits:
    max_upload_bytes: int
    max_px: int
    lite_px: int
    quota_bytes: int


def limits() -> Limits:
    return Limits(
        max_upload_bytes=int(_env_number("CLONEXA_BRAND_MAX_UPLOAD_MB", 5, 0.1, 50) * 1024 * 1024),
        max_px=int(_env_number("CLONEXA_BRAND_MAX_PX", 1920, 64, 4096)),
        lite_px=int(_env_number("CLONEXA_BRAND_LITE_PX", 640, 32, 2048)),
        quota_bytes=int(_env_number("CLONEXA_BRAND_QUOTA_MB", 25, 1, 1024) * 1024 * 1024),
    )


# ------------------------------------------------------------------ bucket ---
class Backend(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, keys: list[str]) -> None: ...
    def list(self, prefix: str) -> list[str]: ...


class S3Backend:
    def __init__(self) -> None:
        missing = [k for k in REQUIRED_ENV if not os.getenv(ENV_PREFIX + k, "").strip()]
        if missing:
            raise StorageUnavailable("El almacenamiento de imágenes no está configurado.")
        try:
            import boto3
            from botocore.config import Config
        except ImportError as error:  # pragma: no cover - boto3 esta en requirements
            raise StorageUnavailable("El almacenamiento de imágenes no está disponible.") from error
        self.bucket = os.environ[ENV_PREFIX + "NAME"].strip()
        self.client = boto3.client(
            "s3",
            endpoint_url=os.environ[ENV_PREFIX + "ENDPOINT"].strip(),
            region_name=os.getenv(ENV_PREFIX + "REGION", "auto").strip() or "auto",
            aws_access_key_id=os.environ[ENV_PREFIX + "ACCESS_KEY_ID"].strip(),
            aws_secret_access_key=os.environ[ENV_PREFIX + "SECRET_ACCESS_KEY"].strip(),
            config=Config(connect_timeout=4, read_timeout=10, retries={"max_attempts": 2}, s3={"addressing_style": "virtual"}),
        )

    def _call(self, fn, **kwargs):
        try:
            return fn(Bucket=self.bucket, **kwargs)
        except Exception as error:
            log.warning("bucket de marca: %s", type(error).__name__)
            raise StorageUnavailable("El almacenamiento de imágenes no responde. Intenta de nuevo en un momento.") from error

    def put(self, key: str, data: bytes, content_type: str = "image/webp", private: bool = False) -> None:
        cache = "private, no-store" if private else "public, max-age=31536000, immutable"
        self._call(self.client.put_object, Key=key, Body=data, ContentType=content_type, CacheControl=cache)

    def get(self, key: str) -> bytes:
        return self._call(self.client.get_object, Key=key)["Body"].read()

    def delete(self, keys: list[str]) -> None:
        for start in range(0, len(keys), 1000):
            chunk = keys[start:start + 1000]
            if chunk:
                self._call(self.client.delete_objects, Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True})

    def list(self, prefix: str) -> list[str]:
        keys: list[str] = []
        token: Optional[str] = None
        while True:
            kwargs = {"Prefix": prefix, **({"ContinuationToken": token} if token else {})}
            page = self._call(self.client.list_objects_v2, **kwargs)
            keys += [o["Key"] for o in page.get("Contents", [])]
            if not page.get("IsTruncated"):
                return keys
            token = page.get("NextContinuationToken")


_backend: Optional[Backend] = None


def backend() -> Backend:
    """El bucket real, creado al primer uso (nunca al arrancar)."""
    global _backend
    if _backend is None:
        _backend = S3Backend()
    return _backend


def set_backend(value: Optional[Backend]) -> None:
    """Para pruebas: un bucket en memoria (None vuelve al real)."""
    global _backend
    _backend = value


def configured() -> bool:
    return all(os.getenv(ENV_PREFIX + k, "").strip() for k in REQUIRED_ENV) or (_backend is not None and not isinstance(_backend, S3Backend))


# ------------------------------------------------------------------ claves ---
def _uuid(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ImageRejected("Identificador inválido.") from None


def keys_for(company_id: Any, image_id: Any) -> tuple[str, str]:
    cid, iid = _uuid(company_id), _uuid(image_id)
    return f"brand/{cid}/{iid}.webp", f"brand/{cid}/{iid}-lite.webp"


# ----------------------------------------------------------------- imagen ---
def sniff(raw: bytes) -> Optional[str]:
    """PNG, JPEG o WEBP por su firma; None para todo lo demas (SVG incluido)."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if raw.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "WEBP"
    return None


@dataclass(frozen=True)
class Encoded:
    full: bytes
    lite: bytes
    width: int
    height: int


def encode(raw: bytes, lim: Optional[Limits] = None) -> Encoded:
    from PIL import Image, ImageOps

    lim = lim or limits()
    if not raw:
        raise ImageRejected("El archivo está vacío.")
    if len(raw) > lim.max_upload_bytes:
        raise ImageRejected(f"La imagen pesa más de {lim.max_upload_bytes // (1024 * 1024)} MB.")
    kind = sniff(raw)
    if kind is None:
        raise ImageRejected("Solo se aceptan imágenes PNG, JPG o WebP.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in {"PNG", "JPEG", "WEBP"} or image.format != kind:
            raise ImageRejected("Solo se aceptan imágenes PNG, JPG o WebP.")
        if image.width * image.height > MAX_PIXELS:
            raise ImageRejected("La imagen es demasiado grande.")
        image.load()
        image = ImageOps.exif_transpose(image)
    except ImageRejected:
        raise
    except Exception:
        raise ImageRejected("No se pudo leer la imagen.") from None
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
    image = image.convert("RGBA" if has_alpha else "RGB")

    def webp(img, side: int, quality: int) -> tuple[bytes, int, int]:
        copy = img.copy()
        copy.thumbnail((side, side), Image.LANCZOS)
        buffer = io.BytesIO()
        copy.save(buffer, format="WEBP", quality=quality, method=4)  # sin EXIF ni otros metadatos
        return buffer.getvalue(), copy.width, copy.height

    full, width, height = webp(image, lim.max_px, 82)
    lite, _, _ = webp(image, lim.lite_px, 60)
    return Encoded(full=full, lite=lite, width=width, height=height)


# ------------------------------------------------------------- operaciones ---
async def usage(db: AsyncSession, company_id: Any) -> dict:
    cid = _uuid(company_id)
    row = (await db.execute(text("""
        SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes + lite_bytes), 0) AS used
        FROM company_brand_images WHERE company_id = CAST(:c AS uuid)
    """), {"c": cid})).mappings().first() or {}
    lim = limits()
    used = int(row.get("used") or 0)
    return {"images": int(row.get("n") or 0), "used_bytes": used, "quota_bytes": lim.quota_bytes,
            "free_bytes": max(0, lim.quota_bytes - used)}


async def list_images(db: AsyncSession, company_id: Any) -> list[dict]:
    cid = _uuid(company_id)
    rows = (await db.execute(text("""
        SELECT id::text AS id, size_bytes, lite_bytes, width, height, created_at
        FROM company_brand_images WHERE company_id = CAST(:c AS uuid) ORDER BY created_at DESC
    """), {"c": cid})).mappings().all()
    return [{**dict(r), "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
             "url": f"/brand-media/{cid}/{r['id']}.webp"} for r in rows]


async def owns(db: AsyncSession, company_id: Any, image_id: Any) -> bool:
    try:
        cid, iid = _uuid(company_id), _uuid(image_id)
    except ImageRejected:
        return False
    return bool((await db.execute(text("""
        SELECT 1 FROM company_brand_images WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"i": iid, "c": cid})).first())


async def upload(db: AsyncSession, company_id: Any, raw: bytes) -> dict:
    cid = _uuid(company_id)
    if not configured():
        raise StorageUnavailable("El almacenamiento de imágenes no está configurado.")
    encoded = await asyncio.to_thread(encode, raw)
    current = await usage(db, cid)
    size = len(encoded.full) + len(encoded.lite)
    if current["used_bytes"] + size > current["quota_bytes"]:
        raise ImageRejected(f"La empresa llegó a su tope de {current['quota_bytes'] // (1024 * 1024)} MB de imágenes. Borra alguna antes de subir otra.")
    image_id = str(uuid.uuid4())
    full_key, lite_key = keys_for(cid, image_id)
    store = backend()
    await asyncio.to_thread(store.put, full_key, encoded.full)
    try:
        await asyncio.to_thread(store.put, lite_key, encoded.lite)
        await db.execute(text("""
            INSERT INTO company_brand_images (id, company_id, size_bytes, lite_bytes, width, height)
            VALUES (CAST(:i AS uuid), CAST(:c AS uuid), :s, :l, :w, :h)
        """), {"i": image_id, "c": cid, "s": len(encoded.full), "l": len(encoded.lite), "w": encoded.width, "h": encoded.height})
        await db.commit()
    except Exception:
        await db.rollback()
        try:
            await asyncio.to_thread(store.delete, [full_key, lite_key])
        except StorageUnavailable:
            log.warning("bucket de marca: no se pudo limpiar %s tras un fallo", image_id)
        raise
    return {"id": image_id, "url": f"/brand-media/{cid}/{image_id}.webp", "size_bytes": len(encoded.full),
            "lite_bytes": len(encoded.lite), "width": encoded.width, "height": encoded.height}


async def read(db: AsyncSession, company_id: Any, image_id: Any, lite: bool = False) -> Optional[bytes]:
    """Bytes de UNA imagen de ESA empresa; None si no es suya o no existe."""
    if not await owns(db, company_id, image_id):
        return None
    full_key, lite_key = keys_for(company_id, image_id)
    return await asyncio.to_thread(backend().get, lite_key if lite else full_key)


async def delete(db: AsyncSession, company_id: Any, image_id: Any) -> bool:
    if not await owns(db, company_id, image_id):
        return False
    await asyncio.to_thread(backend().delete, list(keys_for(company_id, image_id)))
    await db.execute(text("DELETE FROM company_brand_images WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)"),
                     {"i": _uuid(image_id), "c": _uuid(company_id)})
    await db.commit()
    return True


def put_private(key: str, data: bytes, content_type: str) -> None:
    """Zona privada (billing/...): nunca la sirve una ruta publica y no se cachea."""
    store = backend()
    if isinstance(store, S3Backend):
        store.put(key, data, content_type=content_type, private=True)
    else:
        store.put(key, data)


def delete_company(company_id: Any) -> int:
    """Borra del bucket todo lo de la empresa (despues del purge): imagenes de
    marca y, en la zona privada, sus contratos y comprobantes."""
    if not configured():
        return 0
    store = backend()
    cid = _uuid(company_id)
    keys = store.list(f"brand/{cid}/") + store.list(f"billing/{cid}/")
    store.delete(keys)
    return len(keys)
