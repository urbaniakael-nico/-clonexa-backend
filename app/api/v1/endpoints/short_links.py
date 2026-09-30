"""Links cortos de los mini paneles para el portal (049Y).

Exige sesion de la empresa (o Admin V2). Con el interruptor "short_links"
apagado responde enabled=false y el portal sigue mostrando el link largo.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_company_user_for_tenant
from app.services import short_links
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()


class PanelLinksIn(BaseModel):
    links: list[str] = Field(default_factory=list, max_length=40)


async def require_portal_user(company_id: uuid.UUID, request: Request, authorization: str | None = Header(default=None),
                              db: AsyncSession = Depends(get_db)) -> None:
    if await active_admin_v2_session(request, db):
        return
    await require_company_user_for_tenant(db, authorization, company_id)


@router.post("/companies/{company_id}/mini-panels")
async def mini_panel_short_links(company_id: uuid.UUID, payload: PanelLinksIn, db: AsyncSession = Depends(get_db),
                                 _user: None = Depends(require_portal_user)) -> dict:
    """{link largo -> /c/CODIGO} para los links de mini panel de esta empresa.
    Un link de otra empresa u otra pagina se ignora (nunca redirige afuera)."""
    if not await short_links.enabled(db, company_id):
        return {"enabled": False, "links": {}}
    targets: dict[str, str] = {}
    for link in payload.links:
        target = short_links.panel_target(company_id, link)
        if target:
            targets[link] = target
    if not targets:
        return {"enabled": True, "links": {}}
    try:
        codes = await short_links.panel_links(db, company_id, sorted(set(targets.values())))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail="No se pudieron generar los links cortos.") from exc
    return {"enabled": True, "links": {link: f"/c/{codes[t]}" for link, t in targets.items() if t in codes}}
