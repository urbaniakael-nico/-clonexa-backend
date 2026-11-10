"""Ubicacion aproximada de una IP con una base OFFLINE gratuita (DB-IP Lite City, CC BY 4.0).

- La base (.mmdb) la descarga el Dockerfile al construir la imagen (no va en el repo ni en Postgres).
  Ruta: IP_GEO_DB o /app/data/geo/dbip-city-lite.mmdb. Si no esta, todo sigue igual sin ubicacion.
- Precision: ciudad, NO barrio. Las coordenadas son las de la ciudad que da la base.
- La IP completa NO se guarda despues de ubicarla: se guarda recortada (IPv4 /24, IPv6 /48) y un
  hash HMAC (para contar visitantes sin poder volver a la IP).
- Atribucion obligatoria donde se muestren los datos: "IP Geolocation by DB-IP" (https://db-ip.com).
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("clonexa.ip_geo")

DEFAULT_PATH = "/app/data/geo/dbip-city-lite.mmdb"
ATTRIBUTION = "IP Geolocation by DB-IP"
ATTRIBUTION_URL = "https://db-ip.com"

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"reader": None, "path": None, "failed": False}


def db_path() -> str:
    return os.getenv("IP_GEO_DB", "").strip() or DEFAULT_PATH


def _reader():
    """Lector perezoso y compartido (mmap: no carga la base en memoria)."""
    path = db_path()
    if _STATE["reader"] is not None and _STATE["path"] == path:
        return _STATE["reader"]
    if _STATE["failed"] and _STATE["path"] == path:
        return None
    with _LOCK:
        if _STATE["reader"] is not None and _STATE["path"] == path:
            return _STATE["reader"]
        _STATE["path"] = path
        if not Path(path).is_file():
            _STATE["failed"] = True
            log.info("ip_geo sin base en %s: las visitas quedan sin ubicacion", path)
            return None
        try:
            import maxminddb

            _STATE["reader"] = maxminddb.open_database(path, maxminddb.MODE_MMAP)
            _STATE["failed"] = False
        except Exception as exc:  # noqa: BLE001 - sin base no se rompe nada
            _STATE["failed"] = True
            log.warning("ip_geo no pudo abrir la base (%s)", type(exc).__name__)
            return None
    return _STATE["reader"]


def set_reader(reader) -> None:
    """Para pruebas: un lector falso con .get(ip)."""
    _STATE["reader"] = reader
    _STATE["path"] = db_path()
    _STATE["failed"] = reader is None


def parse_ip(raw: str) -> Optional[ipaddress._BaseAddress]:
    value = (raw or "").strip()
    if not value:
        return None
    if value.startswith("[") and "]" in value:
        value = value[1:value.index("]")]
    elif value.count(":") == 1 and "." in value:  # 1.2.3.4:5678
        value = value.split(":")[0]
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip


def is_public(ip) -> bool:
    return bool(ip) and ip.is_global and not ip.is_multicast


def truncate(raw: str) -> str:
    """IPv4 -> a.b.c.0 ; IPv6 -> prefijo /48. Lo que no es IP queda vacio."""
    ip = parse_ip(raw)
    if ip is None:
        return ""
    if ip.version == 4:
        return str(ipaddress.ip_network(f"{ip}/24", strict=False).network_address)
    return str(ipaddress.ip_network(f"{ip}/48", strict=False).network_address) + "/48"


def _salt() -> bytes:
    base = os.getenv("LANDING_IP_SALT", "").strip() or os.getenv("JWT_SECRET_KEY", "").strip() or "clonexa-landing"
    return hashlib.sha256(("landing-ip|" + base).encode("utf-8")).digest()


def ip_hash(raw: str) -> str:
    ip = parse_ip(raw)
    if ip is None:
        return ""
    return hmac.new(_salt(), str(ip).encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _name(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    names = node.get("names") or {}
    return str(names.get("es") or names.get("en") or next(iter(names.values()), "") or "")[:120]


def lookup(raw: str) -> dict:
    """{country, region, city, lat, lng} o {} si no hay base, la IP no es publica o no aparece."""
    ip = parse_ip(raw)
    if ip is None or not is_public(ip):
        return {}
    reader = _reader()
    if reader is None:
        return {}
    try:
        rec = reader.get(str(ip)) or {}
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(rec, dict) or not rec:
        return {}
    country = (rec.get("country") or {}).get("iso_code") or ""
    subdivisions = rec.get("subdivisions") or []
    region = _name(subdivisions[0]) if subdivisions else ""
    city = _name(rec.get("city"))
    loc = rec.get("location") or {}
    lat, lng = loc.get("latitude"), loc.get("longitude")
    out = {"country": str(country)[:20].upper(), "region": region, "city": city,
           "lat": float(lat) if isinstance(lat, (int, float)) else None,
           "lng": float(lng) if isinstance(lng, (int, float)) else None}
    return out if (out["country"] or out["city"]) else {}


def locate_and_mask(raw: str) -> dict:
    """Lo que se guarda de una visita: ubicacion + IP recortada + hash. Nunca la IP completa."""
    geo = lookup(raw)
    return {
        "ip_address": truncate(raw),
        "ip_hash": ip_hash(raw),
        "country": geo.get("country", ""),
        "region": geo.get("region", ""),
        "city": geo.get("city", ""),
        "lat": geo.get("lat"),
        "lng": geo.get("lng"),
        "geo_source": "dbip" if geo else "",
    }
