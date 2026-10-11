"""Consola v2+ · Ficha de empresa · pestaña Roles (/admin-v2/api/companies/{id}/employee-roles).

Roles de EMPLEADO por empresa (capa B). Las cuentas de acceso no se tocan.
Las dos rutas exigen la sesion de Admin V2 (GUARD, validada en el servidor).
Guardar queda en la auditoria (middleware de admin_audit + detalle corto) y
nunca cambia el rol de un empleado: si un rol apagado lo tienen empleados, se
avisa cuantos y quedan marcados "rol no habilitado".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import employee_roles as roles
from app.web.admin_v2plus_companies import GUARD, _audit, _json, _uuid, load_company

router = APIRouter()


@router.get("/admin-v2/api/companies/{company_id}/employee-roles", include_in_schema=False, dependencies=GUARD)
async def company_employee_roles(company_id: str, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    config = await roles.load_config(db, company["id"])
    return _json({"company_id": company["id"], **roles.view(config, await roles.role_counts(db, company["id"]))})


@router.put("/admin-v2/api/companies/{company_id}/employee-roles", include_in_schema=False, dependencies=GUARD)
async def save_company_employee_roles(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Cuerpo inválido.") from None
    if isinstance(body, dict) and body.get("reset") is True:
        config = None  # volver a "todos los roles como siempre"
    else:
        try:
            config = roles.validate_body(body)
        except roles.Invalid as error:
            raise HTTPException(status_code=422, detail={"field": error.field, "message": error.message}) from None
    stored = config if config is not None else {"roles": None, "updated_at": None}
    if not await roles.save_config(db, company["id"], stored):
        raise HTTPException(status_code=409, detail="La empresa no tiene el módulo Personal (workforce).")
    counts = await roles.role_counts(db, company["id"])
    enabled = set(roles.labels(config)) if config else None
    not_enabled = {code: n for code, n in counts.items() if enabled is not None and code not in enabled and n}
    await _audit(request, company=company["name"], action="roles_empleado",
                 roles=", ".join(f"{r['code']}={r['label']}" for r in (config or {}).get("roles") or []) or "todos (sin configuración)",
                 empleados_rol_no_habilitado=sum(not_enabled.values()))
    return _json({"ok": True, "company_id": company["id"], "not_enabled_employees": not_enabled,
                  **roles.view(config, counts)})
