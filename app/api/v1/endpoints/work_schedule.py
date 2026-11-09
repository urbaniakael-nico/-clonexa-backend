"""Horario de la semana por operacion (interruptor work_schedule del modulo workforce, 071A).

Rutas en /work-schedule/companies/{company_id}/...; todas exigen sesion valida desde el primer
dia: Admin V2 o un usuario de ESA empresa con un rol de lectura del portal (validado aqui, no en
la pantalla). Editar: solo dueño / admin de la empresa (y Admin V2). Sin el interruptor: 404.
El panel del lider lee su horario por /lider-operacion (solo lectura).
- GET "/locations/{location_id}?week=AAAA-MM-DD"  horario de esa semana (o el copiado de la anterior)
- PUT "/locations/{location_id}"                   guardar el horario de UNA semana
- GET "/employees"                                 horario de cada persona y horarios por operacion
- PUT "/employees/{employee_id}"                   cambiar el horario de una persona
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import work_locations
from app.services import work_schedule as svc

router = APIRouter()
OFF = "Horario de la semana no está activo para esta empresa."
EDIT_ONLY = "Solo el dueño o el administrador de la empresa cambia el horario."


async def actor(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    """Sin sesion: 401. Otra empresa: 403. Rol sin acceso: 403. Interruptor apagado: 404."""
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = {"role": "owner", "name": "Admin V2", "user_id": None}
    else:
        from app.api.deps import require_company_user_for_tenant

        user = await require_company_user_for_tenant(db, authorization, company_id)
        who = {"role": work_locations.role_of(getattr(user, "role", "")),
               "name": str(getattr(user, "full_name", "") or getattr(user, "email", "") or "usuario"),
               "user_id": str(getattr(user, "id", "") or "") or None}
    if who["role"] not in work_locations.READ_ROLES:
        raise HTTPException(status_code=403, detail="Tu rol no tiene acceso al horario de la semana.")
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    who["can_edit"] = who["role"] in svc.OWNER_ROLES
    return who


async def _place(db: AsyncSession, company_id: UUID, location_id: UUID) -> dict:
    place = await svc.location(db, company_id, location_id)
    if not place:
        raise HTTPException(status_code=404, detail="Esa operación no existe en esta empresa.")
    return place


def _bad(exc: svc.Invalid) -> HTTPException:
    return HTTPException(status_code=422, detail=exc.message)


async def _week_payload(db: AsyncSession, company_id: UUID, place: dict, start, who: dict) -> dict[str, Any]:
    data = await svc.week(db, company_id, place["id"], start)
    return {"ok": True, **svc.week_out(data, place), "can_edit": who["can_edit"],
            "people": await svc.location_people(db, company_id, place["id"])}


@router.get("/companies/{company_id}/locations/{location_id}")
async def get_week(company_id: UUID, location_id: UUID, week: Optional[str] = Query(None), who: dict = Depends(actor),
                   db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    place = await _place(db, company_id, location_id)
    today = datetime.now(timezone.utc).astimezone(svc.zone(place["timezone"])).date()
    try:
        start = svc.parse_week(week, today)
    except svc.Invalid as exc:
        raise _bad(exc) from None
    return await _week_payload(db, company_id, place, start, who)


@router.put("/companies/{company_id}/locations/{location_id}")
async def put_week(company_id: UUID, location_id: UUID, body: dict = Body(...), who: dict = Depends(actor),
                   db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if not who["can_edit"]:
        raise HTTPException(status_code=403, detail=EDIT_ONLY)
    place = await _place(db, company_id, location_id)
    today = datetime.now(timezone.utc).astimezone(svc.zone(place["timezone"])).date()
    try:
        start = svc.parse_week(body.get("week_start"), today)
        await svc.save_week(db, company_id, place["id"], start, body.get("slots"), actor=who["name"], actor_user_id=who["user_id"])
    except svc.Invalid as exc:
        await db.rollback()
        raise _bad(exc) from None
    return await _week_payload(db, company_id, place, start, who)


@router.get("/companies/{company_id}/employees")
async def get_employees(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    places = {}
    for loc in await work_locations.list_locations(db, company_id):
        today = now.astimezone(svc.zone(loc.get("timezone"))).date()
        data = await svc.week(db, company_id, loc["id"], svc.week_start(today))
        places[loc["id"]] = [{"slot": s["slot"], "name": s["name"]} for s in data["slots"]] if data["configured"] else []
    return {"ok": True, "can_edit": who["can_edit"], "slots": await svc.employee_slots(db, company_id), "locations": places}


@router.put("/companies/{company_id}/employees/{employee_id}")
async def put_employee(company_id: UUID, employee_id: UUID, body: dict = Body(...), who: dict = Depends(actor),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if not who["can_edit"]:
        raise HTTPException(status_code=403, detail=EDIT_ONLY)
    try:
        slot = await svc.set_employee_slot(db, company_id, employee_id, body.get("slot"), actor=who["name"])
    except svc.Invalid as exc:
        await db.rollback()
        raise _bad(exc) from None
    return {"ok": True, "employee_id": str(employee_id), "slot": slot}
