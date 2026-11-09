"""Avisos automaticos por WhatsApp (interruptor whatsapp_group_reports del modulo workforce, 072A).

Portal (sesion valida desde el primer dia, validada aqui): Admin V2 o dueño / admin de ESA empresa.
Cualquier otro rol: 403. Otra empresa: 403. Sin sesion: 401. Interruptor apagado: 404.
- GET  /companies/{company_id}/config              configuracion + operaciones + estado
- PUT  /companies/{company_id}/config              guardar destinatarios, horas y modo prueba
- POST /companies/{company_id}/test/{kind}         "Enviar prueba ahora" (siempre en modo prueba)
- GET  /companies/{company_id}/history             historial de avisos (fecha, tipo, destino, estado)

Maquina a maquina (n8n): sin la cabecera secreta X-Clonexa-Secret correcta -> 401, siempre.
- POST /inbound/{company_id}/classify              que hacer con un mensaje / correo que llego
- POST /inbound/{company_id}/received              la foto ya esta en Drive
- GET  /files/{token}                              PDF / Excel / tarjeta PNG del aviso (enlace firmado de 2 h + cabecera)
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import group_reports as svc
from app.services import work_locations
from app.services import work_schedule

router = APIRouter()
OFF = "Avisos por WhatsApp no está activo para esta empresa."
ONLY_OWNER = "Solo el dueño o el administrador de la empresa ve y cambia los avisos por WhatsApp."


async def owner(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = {"role": "owner", "name": "Admin V2"}
    else:
        from app.api.deps import require_company_user_for_tenant

        user = await require_company_user_for_tenant(db, authorization, company_id)
        who = {"role": work_locations.role_of(getattr(user, "role", "")),
               "name": str(getattr(user, "full_name", "") or getattr(user, "email", "") or "usuario")}
    if who["role"] not in work_schedule.OWNER_ROLES:
        raise HTTPException(status_code=403, detail=ONLY_OWNER)
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return who


def machine(x_clonexa_secret: Optional[str] = Header(default=None)) -> bool:
    if not svc.secret_ok(x_clonexa_secret):
        raise HTTPException(status_code=401, detail="No autorizado.")
    return True


def _bad(exc: svc.Invalid) -> HTTPException:
    return HTTPException(status_code=422, detail=exc.message)


async def _config_payload(db: AsyncSession, company_id: UUID) -> dict[str, Any]:
    import os

    cfg = await svc.get_config(db, company_id)
    return {"ok": True, "config": cfg, "locations": await svc.locations(db, company_id),
            "kinds": [{"key": k, "label": v} for k, v in svc.KINDS.items()], "timezones": list(svc.TIMEZONES),
            "n8n_ready": bool(os.getenv(svc.ENV_URL) and os.getenv(svc.ENV_SECRET))}


@router.get("/companies/{company_id}/config")
async def get_config(company_id: UUID, who: dict = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await _config_payload(db, company_id)


@router.put("/companies/{company_id}/config")
async def put_config(company_id: UUID, body: dict = Body(...), who: dict = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        await svc.save_config(db, company_id, body, actor=who["name"])
    except svc.Invalid as exc:
        await db.rollback()
        raise _bad(exc) from None
    return await _config_payload(db, company_id)


@router.post("/companies/{company_id}/test/{kind}")
async def send_test(company_id: UUID, kind: str, body: Optional[dict] = Body(default=None), who: dict = Depends(owner),
                    db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        out = await svc.send_test(db, company_id, kind, (body or {}).get("location_id"))
    except svc.Invalid as exc:
        await db.rollback()
        raise _bad(exc) from None
    return {"ok": True, **out}


@router.get("/companies/{company_id}/history")
async def get_history(company_id: UUID, limit: int = Query(100), who: dict = Depends(owner), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return {"ok": True, "items": await svc.history(db, company_id, limit)}


@router.post("/inbound/{company_id}/classify")
async def inbound_classify(company_id: UUID, body: dict = Body(...), ok: bool = Depends(machine), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return await svc.classify(db, company_id, body)


@router.post("/inbound/{company_id}/received")
async def inbound_received(company_id: UUID, body: dict = Body(...), ok: bool = Depends(machine), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return await svc.received(db, company_id, body)


@router.get("/files/{token}")
async def get_file(token: str, ok: bool = Depends(machine), db: AsyncSession = Depends(get_db)) -> Response:
    import os

    data = svc.unsign(os.getenv(svc.ENV_SECRET) or "", token)
    if not data or data.get("k") not in ("daily_pdf", "weekly_pdf", "weekly_xlsx", "card_png"):
        raise HTTPException(status_code=404, detail="Enlace vencido o no válido.")
    try:
        cid = str(UUID(str(data.get("c"))))
    except ValueError:
        raise HTTPException(status_code=404, detail="Enlace vencido o no válido.") from None
    if not await svc.is_on(db, cid):
        raise HTTPException(status_code=404, detail=OFF)
    try:
        content, name, mime = await svc.render_file(db, cid, {"kind": data["k"], "from": data.get("f"), "to": data.get("t"),
                                                             "d": data.get("d"), "i": data.get("i")})
    except LookupError:
        raise HTTPException(status_code=404, detail="Enlace vencido o no válido.") from None
    return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})
