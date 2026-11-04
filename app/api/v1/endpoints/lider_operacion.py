"""Mini panel Lider de operacion: sesion obligatoria desde el primer dia, validada en el servidor.

Panel (solo el JWT de lider de ESA empresa; sin token 401, otro panel u otra empresa 403, otra
operacion 403, interruptor apagado 404):
- GET "/companies/{id}/inicio"    saludo y cifras de su operacion
- GET "/companies/{id}/crm"       CRM Campo de su operacion
- GET "/companies/{id}/reportes"  Board de su operacion (?start&end) o estado en vivo (?part=live)
- GET "/companies/{id}/crm/lista.pdf"       Lista de asistencia
- GET "/companies/{id}/reportes/export.pdf" Reporte del periodo
- POST "/companies/{id}/pin/verificar"      el PIN de una persona de su operacion y que puede marcar
- POST "/companies/{id}/pin/marcar"         la marca de esa persona, con la ubicacion del equipo
- POST "/companies/{id}/crm/{empleado}/finalizar"  finalizar AHORA un turno de menos del limite

Consola v2+ (solo sesion de Admin V2):
- GET  "/consola/companies/{id}"          operaciones, enlaces, supervisores y lideres
- POST "/consola/companies/{id}/lideres"  crear un lider (la clave nunca va por correo)

Workforce (Admin V2, o dueno / admin de la empresa):
- GET    "/workforce/companies/{id}/pins"                 quien tiene PIN y quien tiene Telegram
- POST   "/workforce/companies/{id}/employees/{e}/pin"    generar (el PIN sale UNA sola vez)
- DELETE "/workforce/companies/{id}/employees/{e}/pin"    quitar

El ingreso es el de todos los mini paneles (POST /companies/{id}/mini-panel-login), que aqui
llama a login().
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import extract_bearer_token, get_db
from app.api.v1.endpoints.reports_board import _json_response, _period
from app.models.auth import CompanyUser
from app.services import auth_service, lider_operacion as svc, lider_pin, short_links
from app.services.access_sessions import register_access_session

router = APIRouter()
OFF = "El panel de líder de operación no está activo para esta empresa."
NOT_FOR_YOU = "Este panel es solo para el líder de operación."
USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{2,39}")
MIN_PASSWORD = 8


class LeaderCreate(BaseModel):
    work_location_id: UUID
    employee_id: UUID
    username: str
    password: Optional[str] = None


async def leader(company_id: UUID, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)) -> dict:
    """La sesion del lider y SU operacion. Se revisa en cada peticion, no solo al entrar."""
    claims = auth_service.decode_access_token(extract_bearer_token(authorization))
    if claims.get("scope") != "mini_panel" or claims.get("panel_type") != svc.PANEL_TYPE or str(claims.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail=NOT_FOR_YOU)
    if not claims.get("sid"):
        raise HTTPException(status_code=401, detail="Token inválido.")
    user = await auth_service.user_from_token_claims(db, claims)
    if str(user.company_id) != str(company_id):
        raise HTTPException(status_code=403, detail=NOT_FOR_YOU)
    if not await svc.available(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    place = next((p for p in await svc.places(db, company_id) if p["id"] == str(claims.get("work_location_id") or "")), None)
    if not place:
        raise HTTPException(status_code=403, detail=NOT_FOR_YOU)
    if not await svc.qualifies(db, company_id, user, place):
        raise HTTPException(status_code=403, detail=svc.denied_message(place["name"]))
    return {"user": user, "place": place}


def only_mine(who: dict, work_location_id: Optional[str] = None, lugar: Optional[str] = None) -> dict:
    """Pedir otra operacion es 403, no una respuesta vacia ni los datos propios en silencio."""
    place = who["place"]
    if work_location_id and work_location_id.strip().casefold() != place["id"]:
        raise HTTPException(status_code=403, detail=f"Este panel solo muestra {place['name']}.")
    if lugar and svc.resolve_place([place], lugar) is None:
        raise HTTPException(status_code=403, detail=f"Este panel solo muestra {place['name']}.")
    return who


def _mine(who: dict = Depends(leader), work_location_id: Optional[str] = Query(None), lugar: Optional[str] = Query(None)) -> dict:
    return only_mine(who, work_location_id, lugar)


@router.get("/companies/{company_id}/inicio")
async def get_inicio(company_id: UUID, who: dict = Depends(_mine), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await svc.inicio(db, company_id, who["user"], who["place"])


@router.get("/companies/{company_id}/crm")
async def get_crm(company_id: UUID, who: dict = Depends(_mine), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await svc.crm(db, company_id, who["place"])


@router.get("/companies/{company_id}/reportes")
async def get_reportes(company_id: UUID, request: Request, start: Optional[date] = Query(None), end: Optional[date] = Query(None),
                       part: Optional[str] = Query(None), who: dict = Depends(_mine), db: AsyncSession = Depends(get_db)) -> Response:
    if part == "live":
        return _json_response(request, await svc.reportes_live(db, company_id, who["place"]))
    first, last = _period(start, end)
    return _json_response(request, await svc.reportes(db, company_id, who["place"], first, last))


def _pdf(body: bytes, name: str) -> Response:
    return Response(content=body, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.get("/companies/{company_id}/crm/lista.pdf")
async def get_attendance_pdf(company_id: UUID, lang: str = Query("es"), who: dict = Depends(_mine), db: AsyncSession = Depends(get_db)) -> Response:
    body = await svc.attendance_pdf(db, company_id, who["user"], who["place"], lang)
    return _pdf(body, f"lista_asistencia_{who['place']['slug']}.pdf")


@router.get("/companies/{company_id}/reportes/export.pdf")
async def get_report_pdf(company_id: UUID, start: Optional[date] = Query(None), end: Optional[date] = Query(None), lang: str = Query("es"),
                         who: dict = Depends(_mine), db: AsyncSession = Depends(get_db)) -> Response:
    first, last = _period(start, end)
    body = await svc.report_pdf(db, company_id, who["user"], who["place"], first, last, lang)
    return _pdf(body, f"reporte_{who['place']['slug']}_{first}_{last}.pdf")


# ------------------------------------------------------------------ sus dos escrituras
class PinCheck(BaseModel):
    pin: str = ""


class PinPunch(BaseModel):
    pin: str = ""
    action: str = ""
    summary: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    lang: Optional[str] = None


class DeviceLocation(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None


async def _leader_of(who: dict, db: AsyncSession, company_id: UUID) -> dict:
    user = who["user"]
    return {"user_id": str(user.id), "device": str(user.id), "name": (await svc._person_of(db, company_id, user))["name"]}


def _denied(exc: lider_pin.Denied) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.message)


@router.post("/companies/{company_id}/pin/verificar")
async def post_pin_check(company_id: UUID, body: PinCheck, who: dict = Depends(_mine), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return await lider_pin.verify(db, company_id, who["place"], str(who["user"].id), body.pin)
    except lider_pin.Denied as exc:
        raise _denied(exc) from None


@router.post("/companies/{company_id}/pin/marcar")
async def post_pin_punch(company_id: UUID, body: PinPunch, who: dict = Depends(_mine), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    leader_info = await _leader_of(who, db, company_id)
    try:
        return await lider_pin.mark(db, company_id, who["place"], leader_info, body.pin, body.action, body.summary, body, "en" if body.lang == "en" else "es")
    except lider_pin.Denied as exc:
        raise _denied(exc) from None


@router.post("/companies/{company_id}/crm/{employee_id}/finalizar")
async def post_finish(company_id: UUID, employee_id: UUID, body: DeviceLocation, who: dict = Depends(_mine), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    leader_info = await _leader_of(who, db, company_id)
    try:
        return await lider_pin.finish(db, company_id, who["place"], leader_info, employee_id, body)
    except lider_pin.Denied as exc:
        raise _denied(exc) from None


# ------------------------------------------------------------------ Workforce: PIN de marcacion
async def pin_manager(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)) -> str:
    """Admin V2 o dueno / admin de la empresa. El lider no llega aqui: lo para la lista blanca."""
    from app.api.deps import require_company_user_for_tenant
    from app.api.v1.endpoints.company_users import MINI_PANEL_MANAGER_ROLES, active_admin_v2_session

    if await active_admin_v2_session(request, db):
        name = "Admin V2"
    else:
        user = await require_company_user_for_tenant(db, authorization, company_id, allowed_roles=MINI_PANEL_MANAGER_ROLES)
        name = str(user.full_name or user.email or "admin")
    if not await svc.available(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return name


@router.get("/workforce/companies/{company_id}/pins")
async def get_pins(company_id: UUID, who: str = Depends(pin_manager), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return {"ok": True, "employees": await lider_pin.status(db, company_id)}


@router.post("/workforce/companies/{company_id}/employees/{employee_id}/pin")
async def post_pin(company_id: UUID, employee_id: UUID, who: str = Depends(pin_manager), db: AsyncSession = Depends(get_db)) -> Response:
    try:
        data = await lider_pin.generate(db, company_id, employee_id, who)
    except lider_pin.Denied as exc:
        raise _denied(exc) from None
    return JSONResponse({"ok": True, **data}, headers={"Cache-Control": "no-store"})


@router.delete("/workforce/companies/{company_id}/employees/{employee_id}/pin")
async def delete_pin(company_id: UUID, employee_id: UUID, who: str = Depends(pin_manager), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"ok": True, **await lider_pin.remove(db, company_id, employee_id, who)}
    except lider_pin.Denied as exc:
        raise _denied(exc) from None


# ------------------------------------------------------------------ ingreso
async def _login_candidate(db: AsyncSession, company_id: UUID, username: str) -> Optional[CompanyUser]:
    """Primero un usuario de este panel; si no, cualquier usuario de la empresa con ese nombre:
    con su clave correcta recibe el aviso de que el panel es solo para el lider."""
    from app.api.v1.endpoints import company_users as cu

    users = (await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))).scalars().all()
    login = str(username or "").strip().lower()
    if not login:
        return None
    for user in users:
        if cu._cx_minipanel_user_matches_login_019d(user, login, svc.PANEL_TYPE):
            return user
    for user in users:
        if login in {str(user.email or "").strip().lower(), str(svc.leader_settings(user).get("username") or "").strip().lower()}:
            return user
    return None


async def login(db: AsyncSession, company_id: UUID, payload: Any, request: Request) -> dict[str, Any]:
    """Usuario y clave como los demas mini paneles, con el bloqueo del portal: 5 intentos fallidos
    y 15 minutos. La operacion sale del enlace y debe ser la del usuario."""
    from app.api.v1.endpoints import company_users as cu

    company = await cu._cx_company_or_404_019d(db, company_id)
    if not await svc.available(db, company_id):
        raise HTTPException(status_code=403, detail=OFF)
    place = svc.resolve_place(await svc.places(db, company_id), getattr(payload, "lugar", None))
    if not place:
        raise HTTPException(status_code=400, detail="Este enlace no tiene una operación válida.")
    user = await _login_candidate(db, company_id, payload.username)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o clave inválidos.")
    if str(user.status or "").lower() not in {"active", "activo"}:
        raise HTTPException(status_code=403, detail="Usuario inactivo o bloqueado.")
    if auth_service.is_locked(user):
        raise HTTPException(status_code=403, detail="Usuario temporalmente bloqueado.")
    if not auth_service.verify_password(payload.password, user.password_hash):
        auth_service.note_failed_login(user)
        await db.commit()
        raise HTTPException(status_code=401, detail="Usuario o clave inválidos.")
    allowed = await svc.qualifies(db, company_id, user, place)
    user.failed_login_attempts = 0
    user.locked_until = None
    if allowed:
        user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    if not allowed:
        raise HTTPException(status_code=403, detail=svc.denied_message(place["name"]))

    minutes = auth_service.get_access_token_expire_minutes()
    session_key = await register_access_session(
        db, company_id=company_id, scope="mini_panel", subject_id=user.id,
        subject_label=f"{user.full_name or user.email or 'líder'} / {svc.PANEL_TYPE} / {place['name']}"[:200], request=request,
        metadata={"panel_type": svc.PANEL_TYPE, "work_location_id": place["id"]},
    )
    token = auth_service.create_access_token({
        "sub": str(user.id), "user_id": str(user.id), "company_id": str(company_id), "role": user.role, "mini_panel": True,
        "panel_type": svc.PANEL_TYPE, "scope": "mini_panel", "sid": session_key, "work_location_id": place["id"],
    }, expires_minutes=minutes)
    return {"ok": True, "access_token": token, "token_type": "bearer", "expires_in": minutes * 60,
            "company": {"id": str(company.id), "name": company.name}, "operation": {"id": place["id"], "name": place["name"], "accent": place["accent"]}}


# ------------------------------------------------------------------ consola v2+
async def admin_only(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)) -> dict:
    from app.web.admin_v2_routes import _active_session

    if not await _active_session(request, db):
        raise HTTPException(status_code=403 if authorization else 401, detail="Solo la consola v2+ administra los líderes de operación.")
    if not await svc.available(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return {"name": "Admin V2"}


def _leader_out(user: CompanyUser) -> dict:
    mini = svc.leader_settings(user)
    return {"user_id": str(user.id), "username": mini.get("username") or user.email, "full_name": user.full_name or "", "status": user.status,
            "employee_id": str(mini.get("employee_id") or ""), "work_location_id": str(mini.get("work_location_id") or "")}


async def _leaders(db: AsyncSession, company_id: UUID) -> list[CompanyUser]:
    users = (await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))).scalars().all()
    return [u for u in users if svc.leader_settings(u).get("type") == svc.PANEL_TYPE and svc.leader_settings(u).get("enabled") is True]


async def _short_links(db: AsyncSession, company_id: UUID, places: list[dict]) -> dict[str, str]:
    """/c/CODIGO por operacion, el mismo siempre. Si falla, la consola muestra el enlace largo."""
    targets = {p["id"]: short_links.panel_target(company_id, svc.entry_link(company_id, p)) for p in places}
    try:
        codes = await short_links.panel_links(db, company_id, sorted(t for t in targets.values() if t), length=short_links.LEADER_CODE_LENGTH)
    except Exception:
        await db.rollback()
        return {}
    return {pid: f"/c/{codes[t]}" for pid, t in targets.items() if t in codes}


@router.get("/consola/companies/{company_id}")
async def get_console(company_id: UUID, who: dict = Depends(admin_only), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    # Primero los enlaces: crear uno confirma o revierte la sesion y venceria a los usuarios ya cargados.
    places = await svc.places(db, company_id)
    shorts = await _short_links(db, company_id, places)
    leaders = await _leaders(db, company_id)
    out = []
    for place in places:
        candidates = await svc.supervisors(db, company_id, place["id"])
        valid = {c["id"] for c in candidates}
        mine = [{**_leader_out(u), "valid": str(svc.leader_settings(u).get("employee_id")) in valid} for u in leaders if svc.is_leader_of(u, place["id"])]
        out.append({"id": place["id"], "name": place["name"], "code": place.get("code"), "abbr": place["abbr"], "accent": place["accent"],
                    "link": svc.entry_link(company_id, place), "short_link": shorts.get(place["id"]), "supervisors": candidates, "leaders": mine})
    return {"ok": True, "label": svc.LABEL, "places": out}


@router.post("/consola/companies/{company_id}/lideres")
async def create_leader(company_id: UUID, body: LeaderCreate, who: dict = Depends(admin_only), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    place = next((p for p in await svc.places(db, company_id) if p["id"] == str(body.work_location_id)), None)
    if not place:
        raise HTTPException(status_code=422, detail="Esa operación no es de esta empresa o está desactivada.")
    employee = next((s for s in await svc.supervisors(db, company_id, place["id"]) if s["id"] == str(body.employee_id)), None)
    if not employee:
        raise HTTPException(status_code=422, detail=f"Esa persona no tiene rol Supervisor en {place['name']}.")
    username = str(body.username or "").strip().lower()
    if not USERNAME.fullmatch(username):
        raise HTTPException(status_code=422, detail="El usuario lleva de 3 a 40 letras, números, punto, guion o guion bajo.")
    typed = body.password or ""
    if typed and len(typed) < MIN_PASSWORD:
        raise HTTPException(status_code=422, detail=f"La clave lleva al menos {MIN_PASSWORD} caracteres.")
    users = (await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))).scalars().all()
    for user in users:
        if username in {str(user.email or "").strip().lower(), str(svc.leader_settings(user).get("username") or "").strip().lower()}:
            raise HTTPException(status_code=409, detail="Ese usuario ya existe en esta empresa.")
        if svc.is_leader_of(user, place["id"]) and str(svc.leader_settings(user).get("employee_id")) == employee["id"]:
            raise HTTPException(status_code=409, detail=f"{employee['name']} ya es líder de {place['name']}. Usa Clave temporal si necesita una clave nueva.")
    password = typed or auth_service.generate_temporary_password()
    now = datetime.now(timezone.utc)
    user = CompanyUser(
        company_id=company_id, email=f"mini+{svc.PANEL_TYPE}+{uuid4().hex}@clonexa.local", password_hash=auth_service.hash_password(password),
        full_name=employee["name"], role=svc.PANEL_TYPE, status="active", must_change_password=False, failed_login_attempts=0, locked_until=None,
        last_password_reset_at=now, created_at=now, updated_at=now,
        settings_json={"mini_panel": {"enabled": True, "type": svc.PANEL_TYPE, "employee_id": employee["id"], "work_location_id": place["id"], "username": username,
                                      "link": svc.entry_link(company_id, place), "source": "consola_v2plus", "created_by": who["name"]}},
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # Una clave escrita en la consola no se devuelve; una generada se muestra una sola vez.
    return {"ok": True, "leader": _leader_out(user), **({} if typed else {"temporary_password": password})}
