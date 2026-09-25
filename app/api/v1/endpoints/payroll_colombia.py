"""Nomina con normativa laboral colombiana (049A): parametros y configuracion.

Capacidad general: el modulo "nomina_colombia" del catalogo de Admin V2 es
el interruptor "APLICAR NORMATIVA LABORAL COLOMBIANA" de cada empresa
(apagado por defecto; sin el, la nomina calcula exactamente como hoy). El
calculo vive en app/services/payroll_colombia.py y se usa desde
payroll.calculate_period_snapshot.

- /payroll-co/params: parametros de ley por año. Son datos de referencia
  nacionales (no de un tenant), por eso no llevan company_id; solo Admin V2
  los lee y edita.
- /payroll-co/companies/{company_id}/config: nivel ARL, exoneracion y
  salario base de cada empleado. Administradores de la empresa o Admin V2,
  con el modulo activo; todo filtra por company_id.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.services import payroll_colombia as engine
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()

MODULE_CODE = "nomina_colombia"
PAYROLL_CO_ADMIN_ROLES = ADMIN_ROLES | {
    "manager", "gerencia", "gerente", "dueno", "dueño", "owner", "propietario",
}


def _json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return value


# ---------------------------------------------------------------- auth ---
async def require_admin_v2(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    if not await active_admin_v2_session(request, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin_v2_session_required")


async def require_payroll_co_admin(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> str:
    """Administradores de ESTA empresa (o Admin V2), con el modulo activo."""
    if await active_admin_v2_session(request, db):
        await require_enabled_module(db, company_id, MODULE_CODE)
        return "Admin V2"
    user = await require_company_user_for_tenant(
        db, authorization, company_id, allowed_roles=PAYROLL_CO_ADMIN_ROLES, module_codes=MODULE_CODE,
    )
    return str(getattr(user, "full_name", "") or getattr(user, "email", "") or "Usuario")


# ------------------------------------------------------------ lecturas ---
async def load_params_by_year(db: AsyncSession) -> dict[int, dict]:
    result = await db.execute(text("SELECT year, params, changes FROM payroll_co_params ORDER BY year"))
    return {
        int(row["year"]): {"params": _json(row["params"], {}), "changes": _json(row["changes"], [])}
        for row in result.mappings().all()
    }


async def load_company_config(db: AsyncSession, company_id: uuid.UUID) -> dict:
    result = await db.execute(
        text("SELECT arl_level, exonerated FROM payroll_co_company WHERE company_id = CAST(:company_id AS uuid)"),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    return {
        "arl_level": int(row["arl_level"]) if row else 1,
        "exonerated": bool(row["exonerated"]) if row else False,
    }


async def load_employee_config(db: AsyncSession, company_id: uuid.UUID) -> dict[str, dict]:
    result = await db.execute(
        text("""
            SELECT employee_id, monthly_salary, arl_level
            FROM payroll_co_employee
            WHERE company_id = CAST(:company_id AS uuid)
        """),
        {"company_id": str(company_id)},
    )
    return {
        str(row["employee_id"]): {
            "monthly_salary": Decimal(str(row["monthly_salary"] or 0)),
            "arl_level": int(row["arl_level"]) if row["arl_level"] else None,
        }
        for row in result.mappings().all()
    }


# ----------------------------------------------------------- parametros ---
@router.get("/params")
async def list_params(db: AsyncSession = Depends(get_db), _admin: None = Depends(require_admin_v2)) -> dict:
    rows = await load_params_by_year(db)
    return {
        "fields": [{"key": key, "label": label, "kind": kind} for key, label, kind in engine.PARAM_FIELDS],
        "years": [{"year": year, **row} for year, row in sorted(rows.items())],
    }


@router.get("/params/{year}/template")
async def params_template(year: int, db: AsyncSession = Depends(get_db), _admin: None = Depends(require_admin_v2)) -> dict:
    """Borrador para un año nuevo a partir del anterior (no guarda nada)."""
    rows = await load_params_by_year(db)
    if year in rows:
        return {"year": year, **rows[year], "exists": True}
    previous = rows.get(year - 1)
    if not previous:
        raise HTTPException(status_code=404, detail=f"No hay parametros de {year - 1} para copiar.")
    return {"year": year, **engine.carry_forward(previous, year), "exists": False}


@router.put("/params/{year}")
async def save_params(
    year: int, request: Request, payload: dict | None = None,
    db: AsyncSession = Depends(get_db), _admin: None = Depends(require_admin_v2),
) -> dict:
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="year_invalid")
    data = payload or {}
    row = {"params": data.get("params"), "changes": data.get("changes") or []}
    errors = engine.validate_year_row(row)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    for change in row["changes"]:
        if int(str(change["from"])[:4]) < year:
            raise HTTPException(status_code=400, detail=f"El cambio {change['from']} es anterior a {year}.")
    await db.execute(
        text("""
            INSERT INTO payroll_co_params (year, params, changes, updated_by, updated_at)
            VALUES (:year, CAST(:params AS jsonb), CAST(:changes AS jsonb), 'Admin V2', now())
            ON CONFLICT (year) DO UPDATE
               SET params = EXCLUDED.params, changes = EXCLUDED.changes,
                   updated_by = EXCLUDED.updated_by, updated_at = now()
        """),
        {"year": year, "params": json.dumps(row["params"]), "changes": json.dumps(row["changes"])},
    )
    await db.commit()
    return {"year": year, **row}


# ------------------------------------------------------ config empresa ---
async def _company_employees(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT id, full_name, role
            FROM employees
            WHERE company_id = CAST(:company_id AS uuid)
              AND COALESCE(status, 'active') != 'archived'
            ORDER BY full_name
        """),
        {"company_id": str(company_id)},
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/companies/{company_id}/config")
async def get_company_config(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _actor: str = Depends(require_payroll_co_admin),
) -> dict:
    company = await load_company_config(db, company_id)
    by_employee = await load_employee_config(db, company_id)
    employees = []
    for employee in await _company_employees(db, company_id):
        config = by_employee.get(str(employee["id"]), {})
        employees.append({
            "id": str(employee["id"]),
            "name": employee.get("full_name") or "Colaborador",
            "role": employee.get("role") or "",
            "monthly_salary": float(config.get("monthly_salary") or 0),
            "arl_level": config.get("arl_level"),
        })
    return {**company, "employees": employees}


def _arl_level(value: Any, *, allow_none: bool = False) -> int | None:
    if allow_none and (value is None or value == ""):
        return None
    try:
        level = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="arl_level_invalid")
    if level < 1 or level > 5:
        raise HTTPException(status_code=400, detail="arl_level_invalid")
    return level


@router.put("/companies/{company_id}/config")
async def save_company_config(
    company_id: uuid.UUID, payload: dict | None = None,
    db: AsyncSession = Depends(get_db), _actor: str = Depends(require_payroll_co_admin),
) -> dict:
    data = payload or {}
    await db.execute(
        text("""
            INSERT INTO payroll_co_company (company_id, arl_level, exonerated, updated_at)
            VALUES (CAST(:company_id AS uuid), :arl_level, :exonerated, now())
            ON CONFLICT (company_id) DO UPDATE
               SET arl_level = EXCLUDED.arl_level, exonerated = EXCLUDED.exonerated, updated_at = now()
        """),
        {"company_id": str(company_id), "arl_level": _arl_level(data.get("arl_level", 1)),
         "exonerated": bool(data.get("exonerated"))},
    )
    own = {str(e["id"]) for e in await _company_employees(db, company_id)}
    for item in data.get("employees") or []:
        employee_id = str(item.get("id") or "")
        if employee_id not in own:
            continue  # nunca escribir sobre empleados de otra empresa
        try:
            salary = Decimal(str(item.get("monthly_salary") or 0))
        except InvalidOperation:
            raise HTTPException(status_code=400, detail="monthly_salary_invalid")
        if salary < 0:
            raise HTTPException(status_code=400, detail="monthly_salary_invalid")
        await db.execute(
            text("""
                INSERT INTO payroll_co_employee (company_id, employee_id, monthly_salary, arl_level, updated_at)
                VALUES (CAST(:company_id AS uuid), CAST(:employee_id AS uuid), :monthly_salary, :arl_level, now())
                ON CONFLICT (company_id, employee_id) DO UPDATE
                   SET monthly_salary = EXCLUDED.monthly_salary, arl_level = EXCLUDED.arl_level, updated_at = now()
            """),
            {"company_id": str(company_id), "employee_id": employee_id, "monthly_salary": str(salary),
             "arl_level": _arl_level(item.get("arl_level"), allow_none=True)},
        )
    await db.commit()
    return await get_company_config(company_id, db, _actor)
