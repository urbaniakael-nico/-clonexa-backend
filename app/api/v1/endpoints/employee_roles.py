"""Portal · roles de empleado de la empresa (GET /api/v1/employee-roles/companies/{id}).

Lo usa el selector de rol de Personal. Exige sesion: usuario de ESA empresa
o Admin V2 (el portal abierto desde la consola). Sin configuracion responde
configured=false y el portal muestra la lista de siempre.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_company_user_for_tenant
from app.services import employee_roles as roles

router = APIRouter()


async def require_tenant_session(
    company_id: str, request: Request, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db),
) -> UUID:
    try:
        cid = UUID(str(company_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.") from None
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        return cid
    await require_company_user_for_tenant(db, authorization, cid)
    return cid


@router.get("/companies/{company_id}")
async def company_employee_roles(cid: UUID = Depends(require_tenant_session), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return roles.client_view(await roles.load_config(db, cid))
