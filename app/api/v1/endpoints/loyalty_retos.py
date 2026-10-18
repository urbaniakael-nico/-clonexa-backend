"""Retos para las mesas (interruptor loyalty_retos_v2 del modulo loyalty).

Todas las rutas exigen sesion: Admin V2 o un usuario de la empresa con rol de
dueno/admin o barman (misma regla de Juegos en vivo), validado aqui. Con el
interruptor apagado responden 404 y el portal muestra la pantalla de siempre.
Las mesas siguen participando por las rutas publicas de siempre del QR
(hospitality: inscribirse, pronostico, voto), que exigen la clave de la mesa.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import loyalty_retos as svc
from app.services.loyalty_retos import RetoError

router = APIRouter()
OFF = "Retos para las mesas no está activo para esta empresa."


def _err(exc: RetoError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.code)


async def actor(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    from app.api.v1.endpoints.loyalty_games import effective_role
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = {"role": "admin", "name": "Admin V2"}
    else:
        from app.api.deps import require_company_user_for_tenant

        user = await require_company_user_for_tenant(db, authorization, company_id)
        who = {"role": await effective_role(db, company_id, user), "name": str(getattr(user, "email", "") or "usuario")}
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    if who["role"] not in ("admin", "barman"):
        raise HTTPException(status_code=403, detail="Retos para las mesas: tu rol no puede abrir este panel.")
    return who


async def _ensure(db: AsyncSession) -> None:
    from app.api.v1.endpoints.hospitality import _ensure_storage

    await _ensure_storage(db)


@router.get("/companies/{company_id}/state")
async def state(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    await _ensure(db)
    return await svc.state(db, company_id, who["role"])


@router.post("/companies/{company_id}/retos")
async def create(company_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    await _ensure(db)
    try:
        return await svc.create(db, company_id, body, who["name"])
    except RetoError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/retos/{reto_id}/close")
async def close_now(company_id: UUID, reto_id: UUID, body: dict = Body(default={}), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    await _ensure(db)
    try:
        return await svc.close_now(db, company_id, reto_id, who["name"], answer_key=(body or {}).get("answer_key"))
    except RetoError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/retos/{reto_id}/cancel")
async def cancel(company_id: UUID, reto_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    """Cancelar y reiniciar (dueno, admin o barman): sin ganador, libera el espacio."""
    await _ensure(db)
    try:
        return await svc.cancel(db, company_id, reto_id, who["name"])
    except RetoError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/retos/{reto_id}/score")
async def final_score(company_id: UUID, reto_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    await _ensure(db)
    try:
        return await svc.set_score(db, company_id, reto_id, body.get("score_a"), body.get("score_b"), who["name"])
    except RetoError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/retos/{reto_id}/winner")
async def pick_winner(company_id: UUID, reto_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    await _ensure(db)
    try:
        return await svc.pick_winner(db, company_id, reto_id, str(body.get("key") or ""), who["name"])
    except RetoError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/retos/{reto_id}/tiebreak")
async def tiebreak(company_id: UUID, reto_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    await _ensure(db)
    raw_pairs = body.get("pairs")
    try:
        pairs = int(raw_pairs) if raw_pairs not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="parejas_invalidas") from None
    try:
        return await svc.open_tiebreak(db, company_id, reto_id, str(body.get("kind") or ""), who["name"], pairs=pairs,
                                       scene=str(body.get("scene")) if body.get("scene") else None)
    except RetoError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/retos/{reto_id}/prize")
async def deliver_prize(company_id: UUID, reto_id: UUID, body: dict = Body(default={}), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    """Premio entregado (barman o dueno). Ganador de un desempate: valida su documento primero."""
    await _ensure(db)
    try:
        return await svc.deliver_prize(db, company_id, reto_id, who["name"], document=(body or {}).get("document"))
    except RetoError as exc:
        raise _err(exc) from None
