"""Corregir producido, renombrar y terminar ciclo por talla (interruptor reference_lifecycle).

Solo el dueno o admin de ESA empresa (o Admin V2), validado en el servidor; con el interruptor
apagado responde 404. Todo filtra por company_id.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import reference_lifecycle as svc

router = APIRouter()


async def actor(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)) -> str:
    """Quien hace la accion. 401/403 sin sesion de administrador de esa empresa; 404 con el interruptor apagado."""
    from app.api.deps import require_company_user_for_tenant
    from app.api.v1.endpoints.companies import COMPANY_ADMIN_ROLES, admin_v2_or_company_preview

    if await admin_v2_or_company_preview(request, db, company_id):
        name = "Admin V2"
    else:
        user = await require_company_user_for_tenant(db, authorization, company_id, allowed_roles=COMPANY_ADMIN_ROLES)
        name = str(getattr(user, "full_name", "") or getattr(user, "email", "") or "Usuario")
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail="Esta función no está activa para esta empresa.")
    return name


def _bad(error: svc.LifecycleError) -> HTTPException:
    return HTTPException(status_code=error.status, detail={"code": error.code, "message": error.message, **error.extra})


@router.get("/companies/{company_id}/state")
async def state(company_id: UUID, _: str = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return {"references": await svc.state(db, str(company_id))}


@router.get("/companies/{company_id}/search")
async def search(company_id: UUID, q: str = Query("", max_length=120), _: str = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return {"items": await svc.search(db, str(company_id), q)}


@router.get("/companies/{company_id}/account")
async def account(company_id: UUID, key: str = Query(..., max_length=200), _: str = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    from app.services import company_locale

    try:
        return await svc.account(db, str(company_id), key, company_locale.current_zone())
    except svc.LifecycleError as error:
        raise _bad(error) from None


@router.post("/companies/{company_id}/produced-correction")
async def produced_correction(company_id: UUID, payload: dict[str, Any], who: str = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return await svc.correct_produced(db, str(company_id), payload, who)
    except svc.LifecycleError as error:
        raise _bad(error) from None


@router.post("/companies/{company_id}/rename")
async def rename(company_id: UUID, payload: dict[str, Any], who: str = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return await svc.rename(db, str(company_id), payload, who)
    except svc.LifecycleError as error:
        raise _bad(error) from None


@router.post("/companies/{company_id}/close-size")
async def close_size(company_id: UUID, payload: dict[str, Any], who: str = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return await svc.close_size(db, str(company_id), payload, who)
    except svc.LifecycleError as error:
        raise _bad(error) from None


@router.post("/companies/{company_id}/finish-cycle")
async def finish_cycle(company_id: UUID, payload: dict[str, Any], who: str = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return await svc.finish_cycle(db, str(company_id), payload, who)
    except svc.LifecycleError as error:
        raise _bad(error) from None


@router.post("/companies/{company_id}/reopen")
async def reopen(company_id: UUID, payload: dict[str, Any], who: str = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return await svc.reopen(db, str(company_id), payload, who)
    except svc.LifecycleError as error:
        raise _bad(error) from None


@router.post("/companies/{company_id}/requests/{request_id}/{decision}")
async def decide(company_id: UUID, request_id: str, decision: str, who: str = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=404, detail="Acción no encontrada.")
    try:
        return await svc.decide_request(db, str(company_id), request_id, decision == "approve", who)
    except svc.LifecycleError as error:
        raise _bad(error) from None
