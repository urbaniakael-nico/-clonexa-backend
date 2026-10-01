"""Huella (llaves de acceso WebAuthn) para el acceso maestro de la Consola v2+.

El navegador no entrega la huella: el lector del equipo (Windows Hello, Touch
ID, huella del celular) firma un reto y el servidor verifica la firma con la
llave PUBLICA que guardo al registrar ese equipo. Nada biometrico sale del
equipo ni se guarda aqui.

- Registrar un equipo: solo con la sesion de Admin V2 abierta.
- Entrar: huella O clave (la clave sigue en admin_v2_routes).
- El reto viaja en una cookie firmada (5 minutos, un solo proposito).
- RP ID = el dominio de la consola (CLONEXA_WEBAUTHN_RP_ID lo fija si hace
  falta; CLONEXA_WEBAUTHN_ORIGIN fija el origen esperado).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CHALLENGE_COOKIE = "clonexa_admin_passkey_challenge"
CHALLENGE_SECONDS = 300
RP_NAME = "CLONEXA Consola v2+"


def _secret() -> bytes:
    from app.web.admin_v2_routes import _session_secret

    return _session_secret()


def rp_id(request: Request) -> str:
    configured = os.getenv("CLONEXA_WEBAUTHN_RP_ID", "").strip()
    if configured:
        return configured
    return (request.headers.get("host") or request.url.hostname or "localhost").split(":")[0]


def expected_origin(request: Request) -> str:
    configured = os.getenv("CLONEXA_WEBAUTHN_ORIGIN", "").strip().rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def user_handle(email: str) -> bytes:
    return hashlib.sha256(f"clonexa-admin:{email}".encode("utf-8")).digest()[:16]


# ------------------------------------------------------------ reto firmado
def challenge_cookie(challenge: bytes, purpose: str) -> str:
    payload = base64.urlsafe_b64encode(f"{purpose}|{int(time.time()) + CHALLENGE_SECONDS}|".encode() + challenge).decode()
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def read_challenge(request: Request, purpose: str) -> bytes | None:
    token = request.cookies.get(CHALLENGE_COOKIE, "")
    if "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()):
        return None
    try:
        raw = base64.urlsafe_b64decode(payload.encode())
        found_purpose, expires, challenge = raw.split(b"|", 2)
    except (ValueError, binascii.Error):
        return None
    if found_purpose.decode() != purpose or int(expires) < int(time.time()) or not challenge:
        return None
    return challenge


def set_challenge(response: Response, request: Request, challenge: bytes, purpose: str) -> None:
    from app.web.admin_v2_routes import _is_secure_request

    response.set_cookie(CHALLENGE_COOKIE, challenge_cookie(challenge, purpose), max_age=CHALLENGE_SECONDS,
                        httponly=True, secure=_is_secure_request(request), samesite="strict", path="/admin-v2plus")


def clear_challenge(response: Response) -> None:
    response.delete_cookie(CHALLENGE_COOKIE, path="/admin-v2plus")


# ------------------------------------------------------------ almacenamiento
async def table_ready(db: AsyncSession) -> bool:
    row = (await db.execute(text("SELECT to_regclass('public.admin_v2_passkeys') IS NOT NULL AS ok"))).mappings().first()
    return bool(row and row.get("ok"))


async def list_passkeys(db: AsyncSession) -> list[dict[str, Any]]:
    if not await table_ready(db):
        return []
    rows = (await db.execute(text("""
        SELECT id, credential_id, public_key, sign_count, label, transports, created_at, last_used_at
        FROM admin_v2_passkeys ORDER BY created_at
    """))).mappings().all()
    return [dict(r) for r in rows]


async def find_passkey(db: AsyncSession, credential_id: str) -> dict[str, Any] | None:
    row = (await db.execute(text("SELECT * FROM admin_v2_passkeys WHERE credential_id = :cid"),
                            {"cid": credential_id})).mappings().first()
    return dict(row) if row else None


async def add_passkey(db: AsyncSession, credential_id: str, public_key: bytes, sign_count: int, label: str,
                      transports: list[str]) -> None:
    await db.execute(text("""
        INSERT INTO admin_v2_passkeys (credential_id, public_key, sign_count, label, transports)
        VALUES (:cid, :pk, :sc, :label, CAST(:transports AS jsonb))
        ON CONFLICT (credential_id) DO NOTHING
    """), {"cid": credential_id, "pk": public_key, "sc": int(sign_count), "label": label[:120],
           "transports": json.dumps(transports or [])})
    await db.commit()


async def touch_passkey(db: AsyncSession, credential_id: str, sign_count: int) -> None:
    await db.execute(text("""
        UPDATE admin_v2_passkeys SET sign_count = :sc, last_used_at = now() WHERE credential_id = :cid
    """), {"cid": credential_id, "sc": int(sign_count)})
    await db.commit()


async def delete_passkey(db: AsyncSession, passkey_id: str) -> bool:
    result = await db.execute(text("DELETE FROM admin_v2_passkeys WHERE id = CAST(:id AS uuid)"), {"id": passkey_id})
    await db.commit()
    return bool(getattr(result, "rowcount", 0))


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    def iso(value: Any) -> str | None:
        return value.isoformat() if hasattr(value, "isoformat") else None

    return {"id": str(row["id"]), "label": row.get("label") or "Equipo", "created_at": iso(row.get("created_at")),
            "last_used_at": iso(row.get("last_used_at"))}
