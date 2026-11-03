"""Turnos abiertos y "Cerrar turno" (interruptor open_shift_alert del modulo workforce).

Rutas en /open-shifts/companies/{company_id}/...; todas exigen sesion valida desde el
primer dia: Admin V2 o un usuario de ESA empresa con un rol permitido (validado aqui,
no en la pantalla). Sin el interruptor: 404, y CRM Campo y Personal siguen igual.
- GET  ""                              SOLO turnos que pasan el limite (alert_after_hours
                                        de la empresa) + permiso de cerrar
- POST "/employees/{employee_id}/close" cerrar con hora real de salida y nota obligatoria;
                                        un turno que no pasa el limite: 400, no se cierra
- GET  "/closes"                        auditoria de cierres manuales
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import open_shift_alert as svc
from app.services import work_locations

router = APIRouter()
OFF = "Aviso de turno abierto no está activo para esta empresa."


async def actor(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    """Sin sesion: 401. Otra empresa: 403. Rol sin acceso: 403. Interruptor apagado: 404."""
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = {"role": "owner", "name": "Admin V2", "user_id": None}
    else:
        from app.api.deps import require_company_user_for_tenant

        user = await require_company_user_for_tenant(db, authorization, company_id)
        who = {"role": svc.role_of(getattr(user, "role", "")),
               "name": str(getattr(user, "full_name", "") or getattr(user, "email", "") or "usuario"),
               "user_id": str(getattr(user, "id", "") or "") or None}
    if who["role"] not in work_locations.READ_ROLES:
        raise HTTPException(status_code=403, detail="Tu rol no tiene acceso a los turnos abiertos.")
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return who


@router.get("/companies/{company_id}")
async def get_open_shifts(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    hours = await svc.alert_hours(db, company_id)
    shifts = [svc.shift_out(s) for s in await svc.open_shifts(db, company_id, older_than_hours=hours)]
    return {"ok": True, "alert_hours": hours, "can_close": who["role"] in svc.CLOSE_ROLES,
            "shifts": shifts, "long_open": len(shifts)}


@router.post("/companies/{company_id}/employees/{employee_id}/close")
async def post_close(company_id: UUID, employee_id: UUID, body: dict = Body(...), who: dict = Depends(actor),
                     db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if who["role"] not in svc.CLOSE_ROLES:
        raise HTTPException(status_code=403, detail="Solo supervisor, dirección o dueño pueden cerrar un turno.")
    min_hours = await svc.alert_hours(db, company_id)
    try:
        result = await svc.close_shift(db, company_id, employee_id, body, actor=who["name"], actor_user_id=who["user_id"],
                                       min_hours=min_hours)
    except svc.TooEarly as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=exc.message) from None
    except svc.Invalid as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=exc.message) from None
    return {"ok": True, "closed": result}


@router.get("/companies/{company_id}/closes")
async def get_closes(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return {"ok": True, "closes": await svc.recent_closes(db, company_id)}
