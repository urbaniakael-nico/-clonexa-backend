"""Turnos (modulo shifts): panel de malla, configuracion y cambios de turno.

Rutas en /turnos (las de /shifts son el registro de turnos de siempre y no cambian).
Todas exigen sesion valida de la empresa (o Admin V2) y el modulo activo.
Permisos en el servidor:
- dueno y director: ven todo, configuran, arman y publican; NO crean cambios;
- supervisor: todo y es el UNICO que crea cambios de turno;
- operario, logistica y demas: 403 (por bot solo "Mis turnos" y responder propuestas).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import shifts as svc

router = APIRouter()
DENIED = "Turnos: tu rol no tiene acceso a este panel."
ONLY_SUPERVISOR = "Turnos: solo el supervisor crea cambios de turno."


async def actor(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    """Quien entra y con que rol de Turnos. Sin sesion: 401. Modulo apagado: 404. Rol sin panel: 403."""
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = {"role": "owner", "name": "Admin V2"}
    else:
        from app.api.deps import require_company_user_for_tenant

        user = await require_company_user_for_tenant(db, authorization, company_id)
        who = {"role": await effective_role(db, company_id, user), "name": str(getattr(user, "email", "") or getattr(user, "full_name", "") or "usuario")}
    if not await svc.module_on(db, company_id):
        raise HTTPException(status_code=404, detail="Turnos no está activo para esta empresa.")
    if who["role"] not in {"owner", "director", "supervisor"}:
        raise HTTPException(status_code=403, detail=DENIED)
    return who


async def effective_role(db: AsyncSession, company_id: UUID, user: Any) -> str:
    """owner / director / supervisor / other. Usa el rol del usuario y, si es un mini panel
    ligado a un empleado de Personal, el rol de ese empleado."""
    role = svc.role_of(getattr(user, "role", ""))
    if role in svc.OWNER_ROLES:
        return "owner"
    if role in svc.DIRECTOR_ROLES:
        return "director"
    if role in svc.SUPERVISOR_ROLES:
        return "supervisor"
    settings = getattr(user, "settings_json", None)
    mini = (settings or {}).get("mini_panel") if isinstance(settings, dict) else None
    employee_id = str((mini or {}).get("employee_id") or "").strip() if isinstance(mini, dict) else ""
    if employee_id:
        from sqlalchemy import text

        emp_role = (await db.execute(text("""SELECT lower(COALESCE(role, '')) FROM employees
            WHERE company_id::text = :c AND id::text = :e AND lower(COALESCE(status, 'active')) = 'active'"""),
                                     {"c": str(company_id), "e": employee_id})).scalar()
        if emp_role in svc.DIRECTOR_ROLES:
            return "director"
        if emp_role in svc.SUPERVISOR_ROLES:
            return "supervisor"
    return "other"


def _bad(exc: svc.Invalid) -> HTTPException:
    return HTTPException(status_code=422, detail={"field": exc.field, "message": exc.message})


def _supervisor(who: dict) -> None:
    if who["role"] != "supervisor":
        raise HTTPException(status_code=403, detail=ONLY_SUPERVISOR)


def _day(value: Optional[str], db_tz) -> date:
    if value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=422, detail="fecha inválida") from None
    return datetime.now(db_tz).date()


def _fmt_t(t) -> dict:
    return {"id": t.id, "code": t.code, "name": t.name, "start": t.start.strftime("%H:%M"), "end": t.end.strftime("%H:%M"),
            "color": t.color, "active": t.active, "night": t.night, "minutes": t.minutes}


async def _context(db: AsyncSession, company_id: UUID, who: dict) -> dict:
    from app.services import employee_roles, panel_logo

    await svc.ensure_defaults(db, company_id)
    _, raw = await svc.rules(db, company_id)
    config = await employee_roles.load_config(db, company_id)
    emps = await svc.employees(db, company_id)
    roles = sorted({e.role for e in emps if e.role})
    return {
        "role": who["role"], "can": {"configure": True, "build": True, "publish": True, "create_change": who["role"] == "supervisor"},
        "logo_url": (await panel_logo.panel_logo(db, company_id))["url"],
        "templates": [_fmt_t(t) for t in await svc.templates(db, company_id)],
        "rules": raw,
        "coverage": [{"template_id": t, "role": r, "min": n} for (t, r), n in sorted((await svc.coverage(db, company_id)).items())],
        "roles": [{"code": r, "label": employee_roles.display(config, r)} for r in roles],
        "employees": [{"id": e.id, "name": e.name, "role": e.role, "role_label": employee_roles.display(config, e.role), "telegram": e.telegram} for e in emps],
    }


@router.get("/companies/{company_id}/context")
async def context(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    return await _context(db, company_id, who)


@router.put("/companies/{company_id}/config")
async def save_config(company_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await svc.save_config(db, company_id, body, who["name"])
    except svc.Invalid as exc:
        raise _bad(exc) from None
    return await _context(db, company_id, who)


@router.get("/companies/{company_id}/week")
async def week(company_id: UUID, start: Optional[str] = None, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    await svc.ensure_defaults(db, company_id)
    return await svc.week_view(db, company_id, _day(start, await svc.zone(db, company_id)))


@router.post("/companies/{company_id}/week/build")
async def build(company_id: UUID, start: Optional[str] = None, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    day = _day(start, await svc.zone(db, company_id))
    try:
        await svc.build_draft(db, company_id, day)
    except svc.Invalid as exc:
        raise _bad(exc) from None
    return await svc.week_view(db, company_id, day)


@router.post("/companies/{company_id}/week/publish")
async def publish(company_id: UUID, start: Optional[str] = None, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    day = _day(start, await svc.zone(db, company_id))
    try:
        sent = await svc.publish(db, company_id, day)
    except svc.Invalid as exc:
        raise _bad(exc) from None
    return {**(await svc.week_view(db, company_id, day)), "sent": sent}


@router.get("/companies/{company_id}/changes")
async def changes(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    from app.api.v1.endpoints.reports import serialize

    return {"items": serialize(await svc.list_changes(db, company_id))}


@router.post("/companies/{company_id}/changes/proposal")
async def proposal(company_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    _supervisor(who)
    try:
        return await svc.proposal(db, company_id, str(body.get("assignment_id") or ""))
    except svc.Invalid as exc:
        raise _bad(exc) from None


@router.post("/companies/{company_id}/changes")
async def create_change(company_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    _supervisor(who)
    try:
        made = await svc.create_change(db, company_id, str(body.get("assignment_id") or ""), who["name"])
        if body.get("send") and made["candidates"]:
            await svc.start(db, company_id, made["id"])
    except svc.Invalid as exc:
        raise _bad(exc) from None
    from app.api.v1.endpoints.reports import serialize

    return serialize(await svc.change(db, company_id, made["id"]))


@router.post("/companies/{company_id}/changes/{change_id}/send")
async def send_change(company_id: UUID, change_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    _supervisor(who)
    try:
        await svc.start(db, company_id, str(change_id))
    except svc.Invalid as exc:
        raise _bad(exc) from None
    from app.api.v1.endpoints.reports import serialize

    return serialize(await svc.change(db, company_id, str(change_id)))


@router.post("/companies/{company_id}/changes/{change_id}/reply")
async def manual_reply(company_id: UUID, change_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    """El supervisor registra a mano la respuesta del candidato actual (queda en la bitacora)."""
    _supervisor(who)
    ch = await svc.change(db, company_id, str(change_id))
    if not ch or ch["status"] != "waiting" or ch["current_index"] is None:
        raise HTTPException(status_code=409, detail="Este cambio no está esperando respuesta.")
    cand = ch["candidates"][ch["current_index"]]
    result = await svc.respond(db, company_id, str(change_id), str(cand["employee_id"]), int(ch["current_index"]), bool(body.get("accept")),
                               via="manual", actor=who["name"])
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail="Este cambio ya no está vigente.")
    from app.api.v1.endpoints.reports import serialize

    return serialize(await svc.change(db, company_id, str(change_id)))


@router.post("/companies/{company_id}/changes/{change_id}/cancel")
async def cancel_change(company_id: UUID, change_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    _supervisor(who)
    try:
        return await svc.cancel(db, company_id, str(change_id), who["name"])
    except svc.Invalid as exc:
        raise _bad(exc) from None
