"""Auditoria de la consola maestra (admin_audit_log).

Middleware ASGI que registra SOLO las escrituras (POST/PUT/PATCH/DELETE)
hechas con una sesion de Admin V2 valida (validada en el servidor ANTES de
atender la peticion). Guarda quien, desde donde, que ruta, que empresa y que
respondio el servidor. NUNCA guarda cuerpos de peticion, query strings ni
claves.

- Todo va en try/except: un fallo del registro nunca bloquea ni cambia la
  respuesta (el registro se escribe despues de responder).
- Las acciones nuevas de v2+ (cambiar tipo, clonar, eliminar definitivo)
  agregan un detalle corto con attach_detail (nombre de la empresa, filas).
- Retencion: 180 dias (se poda como mucho una vez cada 12 h por proceso).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text

log = logging.getLogger("clonexa.admin_audit")
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
RETENTION_DAYS = 180
PRUNE_EVERY_SECONDS = 12 * 60 * 60
WRITE_TIMEOUT_SECONDS = 3.0
BOGOTA = ZoneInfo("America/Bogota")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_DETAIL_KEYS = 8
_DETAIL_TEXT = 200
_last_prune = 0.0


# --------------------------------------------------------------- helpers ---
def company_id_from_path(path: str) -> Optional[str]:
    parts = [p for p in (path or "").split("/") if p]
    for index, part in enumerate(parts):
        if part == "companies" and index + 1 < len(parts) and _UUID.match(parts[index + 1]):
            return parts[index + 1].lower()
    return None


def surface_of(referer: str, path: str) -> str:
    """Desde que consola llego la escritura (v2+, Admin V2 u otra)."""
    from urllib.parse import urlparse

    try:
        ref = urlparse(referer or "").path
    except Exception:
        ref = ""
    for candidate in (ref, path or ""):
        if candidate.startswith("/admin-v2plus"):
            return "v2plus"
        if candidate.startswith("/admin-v2"):
            return "v2"
    return "api"


def client_ip(headers: dict[str, str], client: Any) -> str:
    # El proxy de Railway agrega la IP real AL FINAL (misma regla que el login de Admin V2).
    forwarded = [p.strip() for p in str(headers.get("x-forwarded-for") or "").split(",") if p.strip()]
    if forwarded:
        return forwarded[-1][:120]
    return str(getattr(client, "host", "") or (client[0] if isinstance(client, (tuple, list)) and client else ""))[:120]


def clean_detail(detail: Any) -> Optional[dict]:
    """Detalle corto: pocas claves, textos cortos, sin nada con forma de secreto."""
    if not isinstance(detail, dict) or not detail:
        return None
    from app.services.company_lifecycle import SECRET_KEY

    out: dict[str, Any] = {}
    for key, value in list(detail.items())[:_DETAIL_KEYS]:
        if SECRET_KEY.search(str(key)):
            continue
        if isinstance(value, (int, float, bool)) or value is None:
            out[str(key)[:40]] = value
        else:
            out[str(key)[:40]] = str(value)[:_DETAIL_TEXT]
    return out or None


def attach_detail(request: Any, **detail: Any) -> None:
    """Las rutas nuevas dejan aqui su detalle corto; el middleware lo guarda."""
    try:
        request.state.cx_audit_detail = clean_detail(detail)
    except Exception:  # nunca rompe la accion
        pass


# ------------------------------------------------------------- escritura ---
async def write_entry(entry: dict) -> None:
    from app.core.database import AsyncSessionLocal

    global _last_prune
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO admin_audit_log (actor, ip, method, path, company_id, status_code, surface, detail)
            VALUES (:actor, :ip, :method, :path, CAST(:company_id AS uuid), :status_code, :surface, CAST(:detail AS jsonb))
        """), {**entry, "detail": json.dumps(entry["detail"], ensure_ascii=False) if entry.get("detail") else None})
        now = time.monotonic()
        if now - _last_prune > PRUNE_EVERY_SECONDS:
            _last_prune = now
            await db.execute(text(
                f"DELETE FROM admin_audit_log WHERE at < NOW() - INTERVAL '{RETENTION_DAYS} days'"))
        await db.commit()


async def admin_actor(request: Any) -> Optional[str]:
    """Email del acceso maestro si la sesion de Admin V2 es valida; si no, None."""
    from app.core.database import AsyncSessionLocal
    from app.web import admin_v2_routes as v2

    payload = v2._session_payload(request)  # firma y vencimiento, sin base de datos
    if not payload:
        return None
    async with AsyncSessionLocal() as db:
        if not await v2._active_session(request, db):
            return None
    return str(payload.get("email") or v2.ADMIN_V2_EMAIL)


class AdminAuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or str(scope.get("method") or "").upper() not in WRITE_METHODS:
            await self.app(scope, receive, send)
            return
        actor = None
        try:
            from starlette.requests import Request

            actor = await asyncio.wait_for(admin_actor(Request(scope)), WRITE_TIMEOUT_SECONDS)
        except Exception as exc:
            log.warning("Auditoria: no se pudo validar la sesion (no bloquea): %s", exc)
        if not actor:
            await self.app(scope, receive, send)
            return

        status = {"code": 0}

        async def send_spy(message):
            if message.get("type") == "http.response.start":
                status["code"] = int(message.get("status") or 0)
            await send(message)

        try:
            await self.app(scope, receive, send_spy)
        finally:
            try:
                headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
                path = str(scope.get("path") or "")[:500]
                state = scope.get("state") or {}
                entry = {
                    "actor": actor[:200], "ip": client_ip(headers, scope.get("client")),
                    "method": str(scope.get("method")).upper(), "path": path,
                    "company_id": company_id_from_path(path), "status_code": status["code"] or 500,
                    "surface": surface_of(headers.get("referer", ""), path),
                    "detail": clean_detail(state.get("cx_audit_detail") if isinstance(state, dict) else None),
                }
                await asyncio.wait_for(write_entry(entry), WRITE_TIMEOUT_SECONDS)
            except Exception as exc:
                log.warning("Auditoria: no se pudo registrar (la respuesta no cambia): %s", exc)


# --------------------------------------------------------------- lectura ---
def _day_start(value: str, end: bool = False) -> Optional[datetime]:
    try:
        day = date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    start = datetime.combine(day, dtime.min, BOGOTA).astimezone(timezone.utc)
    return start + timedelta(days=1) if end else start


def build_query(*, company_id: str = "", date_from: str = "", date_to: str = "", action: str = "", limit: int = 100) -> tuple[str, dict]:
    where, params = [], {"limit": max(1, min(int(limit or 100), 500))}
    if company_id:
        if not _UUID.match(company_id):
            raise ValueError("company_id invalido")
        where.append("company_id = CAST(:company_id AS uuid)")
        params["company_id"] = company_id.lower()
    start, end = _day_start(date_from), _day_start(date_to, end=True)
    if start:
        where.append("at >= :date_from")
        params["date_from"] = start
    if end:
        where.append("at < :date_to")
        params["date_to"] = end
    act = str(action or "").strip()
    if act.upper() in WRITE_METHODS:
        where.append("method = :method")
        params["method"] = act.upper()
    elif act:
        where.append("path ILIKE :action")
        params["action"] = f"%{act[:60].replace('%', '').replace('_', '')}%"
    sql = ("SELECT id::text AS id, at, actor, ip, method, path, company_id::text AS company_id, status_code, surface, detail "
           "FROM admin_audit_log" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY at DESC LIMIT :limit")
    return sql, params


async def list_entries(db, **filters) -> list[dict]:
    exists = (await db.execute(text("SELECT to_regclass('public.admin_audit_log') IS NOT NULL"))).scalar()
    if not exists:
        return []
    sql, params = build_query(**filters)
    rows = (await db.execute(text(sql), params)).mappings().all()
    out = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("at"), datetime):
            item["at"] = item["at"].isoformat()
        if isinstance(item.get("detail"), str):
            try:
                item["detail"] = json.loads(item["detail"])
            except ValueError:
                item["detail"] = None
        out.append(item)
    return out
