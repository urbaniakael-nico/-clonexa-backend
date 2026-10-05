"""Enlace de vista previa de la marca para el cliente (Fase 4, parte 4).

Token = "{link_id}.{secreto}.{firma}":
- secreto: 32 bytes aleatorios (secrets.token_urlsafe); en la base solo su sha256.
- firma: HMAC-SHA256 con una clave DERIVADA de la de Admin V2 solo para este
  uso; un token alterado se rechaza sin tocar la base.
- Vence a los 7 dias; se puede revocar. Solo lo aceptan la pagina
  /vista-marca/{token} y las imagenes de esa empresa: no es un JWT ni una
  sesion, y ningun endpoint de /api/v1 lo reconoce.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TTL = timedelta(days=7)
COOKIE = "cx_brand_preview"


def _key() -> bytes:
    from app.web import admin_v2_routes as v2

    return hmac.new(v2._session_secret(), b"clonexa-brand-share-v1", hashlib.sha256).digest()


def _sign(link_id: str, secret: str) -> str:
    return hmac.new(_key(), f"{link_id}.{secret}".encode("ascii"), hashlib.sha256).hexdigest()[:32]


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def parse(token: str) -> Optional[tuple[str, str]]:
    """(link_id, secreto) si el token tiene forma y firma validas; si no, None."""
    parts = str(token or "").split(".")
    if len(parts) != 3 or len(token) > 200:
        return None
    link_id, secret, signature = parts
    try:
        link_id = str(uuid.UUID(link_id))
        secret.encode("ascii")
    except (ValueError, UnicodeEncodeError):
        return None
    if not hmac.compare_digest(signature, _sign(link_id, secret)):
        return None
    return link_id, secret


async def create(db: AsyncSession, company_id: str) -> dict:
    link_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + TTL
    await db.execute(text("""
        INSERT INTO company_brand_share_links (id, company_id, secret_hash, expires_at)
        VALUES (CAST(:i AS uuid), CAST(:c AS uuid), :h, :e)
    """), {"i": link_id, "c": company_id, "h": _hash(secret), "e": expires})
    await db.commit()
    token = f"{link_id}.{secret}.{_sign(link_id, secret)}"
    return {"id": link_id, "token": token, "url": f"/vista-marca/{token}", "expires_at": expires.isoformat()}


async def list_links(db: AsyncSession, company_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, created_at, expires_at, revoked_at FROM company_brand_share_links
        WHERE company_id = CAST(:c AS uuid) ORDER BY created_at DESC LIMIT 20
    """), {"c": company_id})).mappings().all()
    now = datetime.now(timezone.utc)
    iso = lambda v: v.isoformat() if v else None  # noqa: E731
    return [{"id": r["id"], "created_at": iso(r["created_at"]), "expires_at": iso(r["expires_at"]), "revoked_at": iso(r["revoked_at"]),
             "expired": bool(r["expires_at"] and r["expires_at"] <= now)} for r in rows]


async def revoke(db: AsyncSession, company_id: str, link_id: str) -> bool:
    try:
        link_id = str(uuid.UUID(str(link_id)))
    except ValueError:
        return False
    done = (await db.execute(text("""
        UPDATE company_brand_share_links SET revoked_at = now()
        WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid) AND revoked_at IS NULL
    """), {"i": link_id, "c": company_id})).rowcount
    await db.commit()
    return bool(done)


async def resolve(db: AsyncSession, token: str) -> Optional[dict[str, Any]]:
    """{company_id, link_id, expires_at} de un enlace vigente; None si no sirve."""
    parsed = parse(token)
    if not parsed:
        return None
    link_id, secret = parsed
    row = (await db.execute(text("""
        SELECT company_id::text AS company_id, secret_hash, expires_at, revoked_at FROM company_brand_share_links WHERE id = CAST(:i AS uuid)
    """), {"i": link_id})).mappings().first()
    if not row or row["revoked_at"] is not None or row["expires_at"] <= datetime.now(timezone.utc):
        return None
    if not hmac.compare_digest(str(row["secret_hash"]), _hash(secret)):
        return None
    return {"company_id": row["company_id"], "link_id": link_id, "expires_at": row["expires_at"]}
