"""CRM VELVET-LAB (interruptor crm_velvet_lab): rutas con sesion, siempre por company_id.

- Tableta (/companies/{id}/board|unlock|person|action): JWT de mini panel de ESA
  empresa con panel_type crm_lab (o Admin V2). Cada accion ademas exige el token
  corto del colaborador que se obtiene con su PIN (X-Employee-Token).
- PIN (/companies/{id}/pins, .../employees/{eid}/pin): dueno o admin de la empresa
  (o Admin V2), desde Personal.
Con el interruptor apagado todo responde 404.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import crm_lab as svc
from app.services.crm_lab import CrmError

router = APIRouter()
OFF = "CRM VELVET-LAB no está activo para esta empresa."


def _err(exc: CrmError) -> HTTPException:
    if exc.extra:
        return HTTPException(status_code=exc.status, detail={"code": exc.code, **exc.extra})
    return HTTPException(status_code=exc.status, detail=exc.code)


def _ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    return (forwarded.split(",")[0].strip() or (request.client.host if request.client else "") or "")[:120]


async def panel(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    """El mini panel CRM VELVET-LAB de ESA empresa (o Admin V2)."""
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = {"name": "Admin V2"}
    else:
        from app.api.deps import extract_bearer_token
        from app.services.auth_service import decode_access_token, get_current_company_user

        token = extract_bearer_token(authorization)
        user = await get_current_company_user(db, token)
        claims = decode_access_token(token)
        if str(getattr(user, "company_id", "")) != str(company_id):
            raise HTTPException(status_code=403, detail="tenant_not_allowed")
        if claims.get("scope") != "mini_panel" or claims.get("panel_type") != svc.PANEL_TYPE:
            raise HTTPException(status_code=403, detail="Este equipo no es el CRM VELVET-LAB.")
        who = {"name": str(user.full_name or user.email or "CRM VELVET-LAB")}
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return who


async def owner(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    """Dueno o admin de la empresa (o Admin V2): asignan y reinician los PIN."""
    from app.api.v1.endpoints.companies import require_admin_v2_or_tenant_company_admin
    from app.web.admin_v2_routes import _active_session

    await require_admin_v2_or_tenant_company_admin(company_id, request, authorization, db)
    name = "Admin V2"
    if not await _active_session(request, db):
        from app.api.deps import extract_bearer_token
        from app.services.auth_service import get_current_company_user

        user = await get_current_company_user(db, extract_bearer_token(authorization))
        name = str(user.full_name or user.email or "admin")
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return {"name": name}


# ---------------------------------------------------------------- tableta
@router.get("/companies/{company_id}/board")
async def board(company_id: UUID, who: dict = Depends(panel), db: AsyncSession = Depends(get_db)) -> dict:
    """En vivo + lista de colaboradores. Liviano: una consulta para el equipo."""
    out = await svc.team(db, str(company_id))
    out["panel_user"] = who["name"]
    out["brand"] = await brand(db, company_id)
    return out


async def brand(db: AsyncSession, company_id: UUID) -> dict:
    """Nombre, logo (panel_logo), colores, idioma y zona del panel inicial; en cache 60 s."""
    from app.api.v1.endpoints.loyalty_games import brand as base_brand

    return await base_brand(db, company_id)


@router.get("/companies/{company_id}/references")
async def references(company_id: UUID, who: dict = Depends(panel), db: AsyncSession = Depends(get_db)) -> dict:
    return {"items": await svc.references(db, str(company_id))}


@router.post("/companies/{company_id}/unlock")
async def unlock(company_id: UUID, request: Request, body: dict = Body(...), who: dict = Depends(panel), db: AsyncSession = Depends(get_db)) -> dict:
    cid = str(company_id)
    try:
        employee = await svc.check_pin(db, cid, str(body.get("employee_id") or ""), body.get("pin"))
    except CrmError as exc:
        raise _err(exc) from None
    await svc.log(db, cid, employee["employee_id"], employee["employee_name"], "pin_ok", "Entró con su PIN", who["name"], _ip(request),
                  str(request.headers.get("x-device-id") or "")[:200])
    await db.commit()
    return {"employee_token": svc.employee_token(cid, employee["employee_id"], who["name"]), "person": await svc.person(db, cid, employee["employee_id"])}


@router.get("/companies/{company_id}/person")
async def person(company_id: UUID, x_employee_token: str = Header(default=""), who: dict = Depends(panel), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return await svc.person(db, str(company_id), svc.employee_from_token(str(company_id), x_employee_token))
    except CrmError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/action")
async def action(company_id: UUID, request: Request, body: dict = Body(...), x_employee_token: str = Header(default=""),
                 who: dict = Depends(panel), db: AsyncSession = Depends(get_db)) -> dict:
    cid = str(company_id)
    try:
        employee_id = svc.employee_from_token(cid, x_employee_token)
        return await svc.act(db, cid, employee_id, str(body.get("action") or ""), body, who["name"], _ip(request),
                             str(request.headers.get("x-device-id") or "")[:200])
    except CrmError as exc:
        await db.rollback()
        raise _err(exc) from None


# ---------------------------------------------------------------- usuario del panel (consola v2+)
@router.get("/companies/{company_id}/panel-user")
async def panel_user(company_id: UUID, who: dict = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    user = await _crm_user(db, company_id)
    return {"exists": bool(user), **(_crm_user_payload(user, company_id) if user else {"link": _link(company_id)})}


@router.post("/companies/{company_id}/panel-user")
async def create_panel_user(company_id: UUID, who: dict = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    """Crea el UNICO usuario del CRM (un panel compartido en la tableta). La clave
    temporal se muestra una sola vez; despues se regenera con Regenerar clave."""
    from datetime import datetime, timezone

    from app.models.auth import CompanyUser
    from app.services.auth_service import generate_temporary_password, hash_password

    existing = await _crm_user(db, company_id)
    if existing:
        return {"created": False, **_crm_user_payload(existing, company_id)}
    temp = generate_temporary_password()
    now = datetime.now(timezone.utc)
    user = CompanyUser(company_id=company_id, email=f"mini+crm_lab+{company_id.hex}@clonexa.local", password_hash=hash_password(temp),
                       full_name="CRM VELVET-LAB", role="operator", status="active", must_change_password=True, failed_login_attempts=0,
                       locked_until=None, last_password_reset_at=now, created_at=now, updated_at=now,
                       settings_json={"mini_panel": {"enabled": True, "type": svc.PANEL_TYPE, "username": "crm-velvet-lab", "link": _link(company_id),
                                                     "source": "consola_v2plus", "created_by": who["name"]}})
    db.add(user)
    await svc.log(db, str(company_id), None, "", "usuario_creado", "Usuario del CRM creado", who["name"])
    await db.commit()
    await db.refresh(user)
    return {"created": True, "temporary_password": temp, **_crm_user_payload(user, company_id)}


def _link(company_id: UUID) -> str:
    return f"/mini-panel/login?company_id={company_id}&type={svc.PANEL_TYPE}"


async def _crm_user(db: AsyncSession, company_id: UUID):
    from sqlalchemy import select

    from app.models.auth import CompanyUser

    users = (await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))).scalars().all()
    for user in users:
        mini = (user.settings_json or {}).get("mini_panel") if isinstance(user.settings_json, dict) else None
        if isinstance(mini, dict) and mini.get("enabled") is True and str(mini.get("type") or "") == svc.PANEL_TYPE:
            return user
    return None


def _crm_user_payload(user, company_id: UUID) -> dict:
    mini = (user.settings_json or {}).get("mini_panel") or {}
    return {"user_id": str(user.id), "username": mini.get("username") or user.email, "status": user.status, "link": _link(company_id)}


# ---------------------------------------------------------------- PIN (Personal)
@router.get("/companies/{company_id}/pins")
async def pins(company_id: UUID, who: dict = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return {"pins": await svc.pin_status(db, str(company_id))}


@router.put("/companies/{company_id}/employees/{employee_id}/pin")
async def set_pin(company_id: UUID, employee_id: UUID, body: dict = Body(...), who: dict = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return await svc.set_pin(db, str(company_id), str(employee_id), body.get("pin"), who["name"])
    except CrmError as exc:
        raise _err(exc) from None


@router.delete("/companies/{company_id}/employees/{employee_id}/pin")
async def clear_pin(company_id: UUID, employee_id: UUID, who: dict = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict:
    return await svc.clear_pin(db, str(company_id), str(employee_id), who["name"])
