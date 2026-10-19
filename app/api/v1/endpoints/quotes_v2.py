"""Cotizaciones y cuentas de cobro v2 (interruptor quotes_v2): rutas con sesion desde el primer dia.

Solo el dueno o admin de ESA empresa (o Admin V2): son documentos de cobro. Con el
interruptor apagado responde 404. Todo por company_id. El mini panel de
cotizaciones (mini_panel.js) y sus rutas /mini-panel-quotes no cambian.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import quotes_v2 as svc

router = APIRouter()


async def owner(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)) -> None:
    from app.api.v1.endpoints.companies import require_admin_v2_or_tenant_company_admin

    await require_admin_v2_or_tenant_company_admin(company_id, request, authorization, db)
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail="Cotizaciones v2 no está activo para esta empresa.")


async def _actor(db: AsyncSession, company_id: UUID, authorization: Optional[str]) -> tuple[str, Optional[str]]:
    """Quien emite (para la bitacora del documento y el Cierre de dia)."""
    raw = str(authorization or "")
    token = raw.split(" ", 1)[1].strip() if raw.lower().startswith("bearer ") else ""
    if token:
        try:
            from app.services.auth_service import decode_access_token

            data = decode_access_token(token) or {}
            uid = str(data.get("sub") or data.get("user_id") or "")
            row = (await db.execute(text("""SELECT id::text AS id, COALESCE(NULLIF(full_name, ''), email, '') AS label FROM company_users
                WHERE id::text = :u AND company_id = :c LIMIT 1"""), {"u": uid, "c": company_id})).mappings().first()
            if row:
                return row["label"] or "Panel principal", row["id"]
        except Exception:  # noqa: BLE001 - sesion de Admin V2 (ya validada por owner)
            await db.rollback()
    return "Admin V2", None


def _err(exc: svc.QuoteError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.detail)


def _period(date_from: Optional[str], date_to: Optional[str]) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat(str(date_from)), date.fromisoformat(str(date_to))
    except ValueError:
        raise HTTPException(status_code=422, detail="fechas_invalidas") from None
    if end < start:
        start, end = end, start
    if (end - start).days > 366:
        raise HTTPException(status_code=422, detail="rango_maximo_366_dias")
    return start, end


@router.get("/companies/{company_id}/defaults")
async def defaults(company_id: UUID, _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    from app.api.v1.endpoints.loyalty_games import brand

    out = await svc.defaults(db, str(company_id))
    b = await brand(db, company_id)  # logo del panel inicial y nombre
    out["company"] = {"name": b.get("name") or "", "logo_url": b.get("logo_url") or ""}
    return out


@router.get("/companies/{company_id}/from-production")
async def from_production(company_id: UUID, date_from: str = Query(...), date_to: str = Query(...),
                          _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    start, end = _period(date_from, date_to)
    return await svc.from_production(db, str(company_id), start, end)


@router.get("/companies/{company_id}/references")
async def references(company_id: UUID, _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    return {"references": await svc.reference_options(db, str(company_id))}


@router.get("/companies/{company_id}/documents")
async def documents(company_id: UUID, q: str = Query(""), status: str = Query("active"),
                    _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    return await svc.history(db, str(company_id), q, status)


@router.get("/companies/{company_id}/report")
async def report(company_id: UUID, date_from: str = Query(...), date_to: str = Query(...),
                 _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    start, end = _period(date_from, date_to)
    return await svc.report(db, str(company_id), start, end)


@router.post("/companies/{company_id}/documents", status_code=201)
async def create(company_id: UUID, body: dict[str, Any] = Body(...), authorization: Optional[str] = Header(default=None),
                 _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    label, uid = await _actor(db, company_id, authorization)
    try:
        return {"ok": True, "document": await svc.create(db, str(company_id), body, label, uid)}
    except svc.QuoteError as exc:
        raise _err(exc) from None


@router.get("/companies/{company_id}/documents/{quote_id}")
async def detail(company_id: UUID, quote_id: str, _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"document": await svc.get(db, str(company_id), quote_id)}
    except svc.QuoteError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/documents/{quote_id}/archive")
async def archive(company_id: UUID, quote_id: str, _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, "document": await svc.archive(db, str(company_id), quote_id)}
    except svc.QuoteError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/documents/{quote_id}/convert")
async def convert(company_id: UUID, quote_id: str, _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return {"ok": True, "document": await svc.convert(db, str(company_id), quote_id)}
    except svc.QuoteError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/documents/{quote_id}/paid")
async def paid(company_id: UUID, quote_id: str, body: dict[str, Any] = Body(default={}), authorization: Optional[str] = Header(default=None),
               _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    label, _uid = await _actor(db, company_id, authorization)
    try:
        return {"ok": True, "document": await svc.mark_paid(db, str(company_id), quote_id, label, body.get("paid", True) is not False)}
    except svc.QuoteError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/signatures", status_code=201)
async def signature(company_id: UUID, body: dict[str, Any] = Body(...), authorization: Optional[str] = Header(default=None),
                    _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    label, _uid = await _actor(db, company_id, authorization)
    try:
        return {"ok": True, "signature": await svc.save_signature(db, str(company_id), str(body.get("data_url") or ""), label)}
    except svc.QuoteError as exc:
        raise _err(exc) from None


@router.get("/companies/{company_id}/documents/{quote_id}/pdf")
async def pdf(company_id: UUID, quote_id: str, document_type: Optional[str] = Query(None), disposition: Optional[str] = Query(None),
              _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    from app.api.v1.endpoints import mini_panel_quotes as mpq

    conn = await mpq._connect()
    try:
        company = await mpq._company_profile(conn, company_id)  # el mismo encabezado y logo del PDF de siempre
    finally:
        await conn.close()
    try:
        data, filename = await svc.pdf(db, str(company_id), quote_id, document_type, company)
    except svc.QuoteError as exc:
        raise _err(exc) from None
    kind = "inline" if str(disposition or "").lower() == "inline" else "attachment"
    return StreamingResponse(iter([data]), media_type="application/pdf", headers={"Content-Disposition": f'{kind}; filename="{filename}"'})

