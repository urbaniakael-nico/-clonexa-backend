"""Recordatorio de pago en el panel principal del cliente (/billing-reminder).

Acceso (validado aqui, no en la pantalla): SOLO el dueño o admin de la empresa
con la sesion del PANEL PRINCIPAL (token scope "client"). Un token de mini
panel (mesero, cocina, caja, barman...) recibe 403 aunque su usuario sea
admin, igual que cualquier otro rol (operario, gerente, consulta...). Los bots
no tienen token de usuario: 401.
La empresa sale del token (nunca de la URL): cada consulta filtra por ese
company_id. Nada se bloquea ni se suspende desde aqui: solo informa y deja
reportar un pago ("Ya pagué"), que queda POR VALIDAR en Facturacion.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import extract_bearer_token, get_db
from app.services import billing, billing_contracts, company_locale
from app.services import brand_media as media
from app.services.auth_service import decode_access_token, get_current_company_user

router = APIRouter()

OWNER_ROLES = {"company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"}
NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


async def require_panel_owner(authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)) -> dict:
    token = extract_bearer_token(authorization)
    claims = decode_access_token(token)
    if claims.get("scope") != "client" or claims.get("mini_panel") or claims.get("panel_type"):
        raise HTTPException(status_code=403, detail="role_not_allowed")
    user = await get_current_company_user(db, token)
    if str(getattr(user, "company_id", "")) != str(claims.get("company_id") or getattr(user, "company_id", "")):
        raise HTTPException(status_code=403, detail="tenant_not_allowed")
    role = str(getattr(user, "role", "") or "").strip().lower().replace(" ", "_")
    if role not in OWNER_ROLES:
        raise HTTPException(status_code=403, detail="role_not_allowed")
    return {"company_id": str(user.company_id), "actor": str(getattr(user, "email", "") or getattr(user, "full_name", "") or "cliente")}


async def _local_today(db: AsyncSession, company_id: str):
    locale = await company_locale.get_company_locale(db, company_id)
    zone = company_locale.zone(locale.get("timezone"))
    return datetime.now(timezone.utc).astimezone(zone).date(), locale


async def panel_theme(db: AsyncSession, company_id: str) -> dict:
    """Colores del panel principal de la empresa (misma regla que panel_logo:
    marca publicada del Estudio de marca o, sin ella, la experiencia). Solo lee."""
    async def read() -> dict:
        from app.services import brand_store, brand_theme

        tokens = await brand_store.published_tokens(db, company_id)
        if tokens:
            return brand_theme.branding_for_portal(tokens, company_id)
        from app.api.v1.endpoints.companies import _get_company_or_404, _read_company_branding

        return _read_company_branding(await _get_company_or_404(db, company_id))

    raw = await billing_contracts.safely(db, read, {}) or {}

    def hex_or(value: Any, default: str) -> str:
        value = str(value or "").strip()
        return value if len(value) == 7 and value.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in value[1:]) else default

    return {"primary": hex_or(raw.get("primary_color"), "#ff2bd6"), "secondary": hex_or(raw.get("secondary_color"), "#00ff88"),
            "background": hex_or(raw.get("background_color"), "#050509"), "text": hex_or(raw.get("text_color"), "#f8fafc")}


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "is_finite"):  # Decimal
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@router.get("")
async def reminder(who: dict = Depends(require_panel_owner), db: AsyncSession = Depends(get_db)):
    cid = who["company_id"]
    today, locale = await _local_today(db, cid)
    state = await billing_contracts.reminder(db, cid, today)
    if not state:
        return JSONResponse({"show": False}, headers=NO_STORE)
    name = (await db.execute(text("SELECT name FROM companies WHERE id = CAST(:c AS uuid)"), {"c": cid})).scalar() or ""
    provider = await billing_contracts.get_provider(db)
    return JSONResponse(_plain({"show": True, **state, "company_name": name, "today": today, "has_qr": bool(provider.get("has_qr")),
                                "timezone": locale.get("timezone"), "language": locale.get("language"),
                                "provider_name": provider.get("trade_name") or "CLONEXA", "theme": await panel_theme(db, cid)}), headers=NO_STORE)


@router.get("/qr")
async def reminder_qr(who: dict = Depends(require_panel_owner), db: AsyncSession = Depends(get_db)):
    if not media.configured():
        raise HTTPException(status_code=404, detail="Sin QR de pago.")

    async def get(key: str) -> bytes:
        return await asyncio.to_thread(media.backend().get, key)

    got = await billing_contracts.provider_qr(db, get)
    if not got:
        raise HTTPException(status_code=404, detail="Sin QR de pago.")
    return Response(got[0], media_type=got[1], headers=NO_STORE)


@router.post("/paid")
async def reminder_paid(request: Request, amount: str | None = Query(default=None, max_length=20),
                        who: dict = Depends(require_panel_owner), db: AsyncSession = Depends(get_db)):
    """Cuerpo = la foto o el PDF del comprobante (crudo, max 5 MB). ?amount= opcional."""
    if not media.configured():
        raise HTTPException(status_code=503, detail="storage_unavailable")
    limit = billing_contracts.MAX_PROOF_BYTES
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + 4096:
        raise HTTPException(status_code=413, detail="El comprobante pesa más de 5 MB.")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail="El comprobante pesa más de 5 MB.")
        chunks.append(chunk)
    cid = who["company_id"]
    today, _locale = await _local_today(db, cid)

    async def put(key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(media.put_private, key, data, content_type)

    try:
        saved = await billing_contracts.report_payment(db, cid, b"".join(chunks), amount, who["actor"], today, put)
    except billing.BillingInvalid as error:
        raise HTTPException(status_code=422, detail={"field": error.field, "message": error.message}) from None
    except billing.BillingConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except media.StorageUnavailable:
        raise HTTPException(status_code=503, detail="storage_unavailable") from None
    return JSONResponse(_plain({"ok": True, "payment": saved}), headers=NO_STORE)
