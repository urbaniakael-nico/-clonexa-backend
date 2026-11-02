"""Lugares de trabajo (interruptor work_locations del modulo workforce).

Rutas en /work-locations/companies/{company_id}/...; todas exigen sesion valida
desde el primer dia: Admin V2 o un usuario de ESA empresa con un rol permitido
(validado aqui, no en la pantalla). Sin el interruptor: 404, y Personal y CRM
Campo siguen como siempre.
- GET  ""                         lugares + lugar de cada empleado + permisos
- PUT  "/locations"               administrar lugares (solo dueno / admin)
- POST "/assign"                  asignar lugar a uno o varios empleados
- GET  "/employees/{id}/history"  traslados de un empleado
- GET  "/board"                   CRM Campo agrupado por lugar (una sola llamada)
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import work_locations as svc

router = APIRouter()
OFF = "Lugares de trabajo no está activo para esta empresa."


async def actor(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    """Quien entra. Sin sesion: 401. Otra empresa: 403. Rol sin acceso: 403. Interruptor apagado: 404."""
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = {"role": "owner", "name": "Admin V2", "user_id": None}
    else:
        from app.api.deps import require_company_user_for_tenant

        user = await require_company_user_for_tenant(db, authorization, company_id)
        who = {"role": svc.role_of(getattr(user, "role", "")),
               "name": str(getattr(user, "full_name", "") or getattr(user, "email", "") or "usuario"),
               "user_id": str(getattr(user, "id", "") or "") or None}
    if who["role"] not in svc.READ_ROLES:
        raise HTTPException(status_code=403, detail="Tu rol no tiene acceso a Lugares de trabajo.")
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return who


def _bad(exc: svc.Invalid) -> HTTPException:
    return HTTPException(status_code=422, detail=exc.message)


@router.get("/companies/{company_id}")
async def get_locations(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return {
        "ok": True,
        "locations": await svc.list_locations(db, company_id),
        "assignments": await svc.assignments(db, company_id),
        "can_manage": who["role"] in svc.MANAGE_ROLES,
        "can_assign": who["role"] in svc.ASSIGN_ROLES,
    }


@router.put("/companies/{company_id}/locations")
async def put_locations(company_id: UUID, body: dict = Body(...), who: dict = Depends(actor),
                        db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if who["role"] not in svc.MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="Solo el dueño o el administrador de la empresa administra los lugares.")
    try:
        return {"ok": True, "locations": await svc.save_locations(db, company_id, body)}
    except svc.Invalid as exc:
        await db.rollback()
        raise _bad(exc) from None


@router.post("/companies/{company_id}/assign")
async def post_assign(company_id: UUID, body: dict = Body(...), who: dict = Depends(actor),
                      db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if who["role"] not in svc.ASSIGN_ROLES:
        raise HTTPException(status_code=403, detail="Tu rol no puede asignar lugares de trabajo.")
    try:
        result = await svc.assign(db, company_id, body.get("employee_ids"), body.get("work_location_id"),
                                  actor=who["name"], actor_user_id=who["user_id"], source=str(body.get("source") or "personal"))
    except svc.Invalid as exc:
        await db.rollback()
        raise _bad(exc) from None
    return {"ok": True, **result}


@router.get("/companies/{company_id}/employees/{employee_id}/history")
async def get_history(company_id: UUID, employee_id: UUID, who: dict = Depends(actor),
                      db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return {"ok": True, "changes": await svc.history(db, company_id, employee_id)}


@router.get("/companies/{company_id}/board")
async def get_board(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await svc.board(db, company_id)
