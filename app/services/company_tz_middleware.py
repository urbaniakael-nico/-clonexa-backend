"""Fase A: en cada peticion que nombra una empresa (en la ruta .../companies/{id}/...
o en ?company_id=), la zona horaria de ESA empresa queda en
company_locale.CURRENT_TZ mientras se atiende. Asi "hoy", los limites de dias y
los AT TIME ZONE salen en la zona de la empresa sin pasar la empresa por cada
funcion. Sin empresa (o si algo falla): Bogota, como siempre.

Cache en memoria de 60 s por empresa; Ajustes la invalida al guardar.
"""
from __future__ import annotations

import re
import time
from urllib.parse import parse_qs

from app.services import company_locale

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
TTL_SECONDS = 60
_cache: dict[str, tuple[float, dict]] = {}


def company_id_of(path: str, query: bytes | str) -> str | None:
    parts = [p for p in (path or "").split("/") if p]
    for i, part in enumerate(parts[:-1]):
        if part == "companies" and _UUID.match(parts[i + 1]):
            return parts[i + 1].lower()
    raw = query.decode("latin-1") if isinstance(query, bytes) else str(query or "")
    value = (parse_qs(raw).get("company_id") or [""])[0]
    return value.lower() if _UUID.match(value) else None


def invalidate(company_id: str) -> None:
    _cache.pop(str(company_id).lower(), None)


_down_until = 0.0


async def locale_cached(company_id: str) -> dict:
    """Con la base caida (o sin base, como en las pruebas) no insiste: 60 s de Bogota."""
    global _down_until
    now = time.monotonic()
    hit = _cache.get(company_id)
    if hit and hit[0] > now:
        return hit[1]
    if _down_until > now:
        return company_locale.normalize()
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text("""
                SELECT s.currency, s.timezone AS settings_tz, s.language, c.timezone AS company_tz
                FROM companies c LEFT JOIN company_core_settings s ON s.company_id = c.id
                WHERE c.id = CAST(:company_id AS uuid) LIMIT 1
            """), {"company_id": company_id})).mappings().first()
    except Exception:
        _down_until = now + TTL_SECONDS
        return company_locale.normalize()
    row = dict(row) if row else {}
    data = company_locale.normalize(row.get("currency"), row.get("settings_tz") or row.get("company_tz"), row.get("language"))
    _cache[company_id] = (now + TTL_SECONDS, data)
    return data


class CompanyTzMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        tokens = None
        try:
            cid = company_id_of(scope.get("path") or "", scope.get("query_string") or b"")
            if cid:
                tokens = company_locale.use(await locale_cached(cid))
        except Exception:
            tokens = None  # nunca rompe la peticion: queda Bogota y COP
        try:
            return await self.app(scope, receive, send)
        finally:
            if tokens is not None:
                company_locale.reset(tokens)
