"""Oficina 3D · piso del bar aprobado: personajes y animaciones de Mixamo desde el bucket PRIVADO.

Licencia de Mixamo (Adobe): se pueden usar dentro del producto, pero NO redistribuir los archivos sueltos.
Por eso:
- Nunca estan en el repositorio (es publico). La prueba tests/test_oficina_bar.py falla si entra uno.
- Se suben al bucket privado de Clonexa (el mismo de las imagenes de marca, clonexa-media) con
  ops/oficina/subir_recursos_bar.py, bajo PREFIX, con un manifest.json (archivo -> bytes y sha256).
- El backend los sirve SOLO con sesion de Admin V2 (oficina_routes), con lista blanca del manifiesto, se
  verifica la huella y se guardan en memoria (tope CACHE_MAX) para no ir al bucket en cada visita.
- Si el bucket no responde, el piso abre igual sin personas (aviso en pantalla): nunca se rompe la oficina.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import OrderedDict
from typing import Optional

from app.services import brand_media

PREFIX = "oficina/bar/v1/"
MANIFEST_KEY = PREFIX + "manifest.json"
NAME_RE = re.compile(r"^(personajes|animaciones)/[A-Za-z0-9_]{1,40}\.glb$")
CACHE_MAX = 48 * 1024 * 1024
FILE_MAX = 8 * 1024 * 1024
MANIFEST_TTL = 600.0


class Unavailable(Exception):
    """El bucket no esta configurado, no responde o el archivo no coincide con su huella."""


_manifest: dict = {"at": 0.0, "data": None}
_cache: "OrderedDict[str, bytes]" = OrderedDict()


def reset() -> None:
    _manifest.update(at=0.0, data=None)
    _cache.clear()


def valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name or "")) and ".." not in name


def clean_manifest(raw: dict) -> dict:
    """Solo entradas con nombre valido, peso razonable y huella sha256."""
    files = {}
    for name, meta in ((raw or {}).get("files") or {}).items():
        if not valid_name(name) or not isinstance(meta, dict):
            continue
        sha, size = str(meta.get("sha") or ""), meta.get("bytes")
        if re.fullmatch(r"[0-9a-f]{64}", sha) and isinstance(size, int) and 0 < size <= FILE_MAX:
            files[name] = {"bytes": size, "sha": sha}
    return {"files": files, "version": str((raw or {}).get("version") or "")[:40]}


async def manifest() -> dict:
    if _manifest["data"] is not None and time.monotonic() - _manifest["at"] < MANIFEST_TTL:
        return _manifest["data"]
    try:
        raw = await asyncio.to_thread(brand_media.backend().get, MANIFEST_KEY)
        data = clean_manifest(json.loads(raw.decode("utf-8")))
    except (brand_media.StorageUnavailable, ValueError, UnicodeDecodeError) as error:
        raise Unavailable("Los personajes del bar no están disponibles ahora.") from error
    _manifest.update(at=time.monotonic(), data=data)
    return data


def _remember(name: str, data: bytes) -> None:
    _cache[name] = data
    _cache.move_to_end(name)
    while sum(len(v) for v in _cache.values()) > CACHE_MAX and len(_cache) > 1:
        _cache.popitem(last=False)


async def read(name: str) -> Optional[tuple[bytes, str]]:
    """(bytes, sha) del archivo; None si no esta en la lista blanca del manifiesto."""
    if not valid_name(name):
        return None
    meta = (await manifest())["files"].get(name)
    if not meta:
        return None
    hit = _cache.get(name)
    if hit is not None:
        _cache.move_to_end(name)
        return hit, meta["sha"]
    try:
        data = await asyncio.to_thread(brand_media.backend().get, PREFIX + name)
    except brand_media.StorageUnavailable as error:
        raise Unavailable("Los personajes del bar no están disponibles ahora.") from error
    if hashlib.sha256(data).hexdigest() != meta["sha"] or data[:4] != b"glTF":
        raise Unavailable("Un archivo del bar no coincide con su huella.")
    _remember(name, data)
    return data, meta["sha"]
