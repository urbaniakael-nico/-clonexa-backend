"""Produccion v2 (interruptor production_v2): tablero y PDF con sesion desde el primer dia.

Solo el dueno o admin de ESA empresa (o Admin V2): el tablero muestra la mano de
obra del equipo. Con el interruptor apagado responde 404. Todo por company_id.
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import production_v2 as svc

router = APIRouter()


async def owner(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)) -> None:
    from app.api.v1.endpoints.companies import require_admin_v2_or_tenant_company_admin

    await require_admin_v2_or_tenant_company_admin(company_id, request, authorization, db)
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail="Producción v2 no está activa para esta empresa.")


def _today():
    from app.services import company_locale

    return datetime.now(company_locale.current_zone()).date()


def _period(preset: str, date_from: Optional[str], date_to: Optional[str]):
    try:
        return svc.period(preset, _today(), date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


async def _company(db: AsyncSession, company_id: UUID) -> dict:
    from app.api.v1.endpoints.loyalty_games import brand

    b = await brand(db, company_id)
    return {"name": b.get("name") or "", "logo_url": b.get("logo_url") or "", "language": b.get("language") or "es"}


@router.get("/companies/{company_id}/insights")
async def insights(company_id: UUID, preset: str = Query("week"), date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
                   _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    start, end = _period(preset, date_from, date_to)
    out = await svc.insights(db, str(company_id), start, end, _today())
    out["company"] = await _company(db, company_id)
    return out


@router.get("/companies/{company_id}/export.pdf")
async def export_pdf(company_id: UUID, preset: str = Query("week"), date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
                     disposition: Optional[str] = Query(None), _: None = Depends(owner), db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    from app.api.v1.endpoints.reports import report_pdf_logo_reader
    from app.services import panel_logo

    start, end = _period(preset, date_from, date_to)
    ins = await svc.insights(db, str(company_id), start, end, _today())
    company = await _company(db, company_id)
    logo = await panel_logo.panel_logo(db, company_id)  # el mismo logo del panel inicial
    raw = await panel_logo.panel_logo_bytes(db, company_id, logo["url"])
    reader = report_pdf_logo_reader("data:image/webp;base64," + base64.b64encode(raw).decode()) if raw else report_pdf_logo_reader(logo["url"])
    pdf = svc.build_pdf(ins, company, reader)
    kind = "inline" if str(disposition or "").strip().lower() == "inline" else "attachment"
    filename = f"produccion_{start.isoformat()}_{end.isoformat()}.pdf"
    return StreamingResponse(iter([pdf]), media_type="application/pdf", headers={"Content-Disposition": f'{kind}; filename="{filename}"'})
