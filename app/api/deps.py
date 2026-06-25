from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import CompanyUser
from app.services.auth_service import get_current_company_user


ADMIN_ROLES = {"company_admin", "admin_empresa"}
WRITE_ROLES = {
    "company_admin",
    "admin_empresa",
    "manager",
    "gerencia",
    "gerente",
    "management",
    "operator",
    "operador",
    "operario",
    "supervisor",
    "staff",
    "agente_call",
    "agent_call",
    "agente_externo",
    "external_agent",
    "externo",
    "tesoreria",
    "treasury",
}
READ_ROLES = {*WRITE_ROLES, "viewer", "consulta"}

MODULE_ALIASES = {
    "transport_calls": {
        "transport_calls", "transport_call", "tra", "transport", "transporte", "transportation",
        "call", "calls", "call_center", "callcenter", "call_center_llamadas",
        "call_center_llamada", "cal", "llamadas", "llamada",
    },
    "transport_contracts": {
        "transport_contracts", "transport_contract", "con", "contrato", "aval", "contracts",
        "contract", "contracts_avales", "contracts_aval", "contratos_avales", "contratos", "avales",
    },
    "transport_quotes_tickets": {
        "transport_quotes_tickets", "transport_tickets", "quotes_tickets", "tickets_cotizaciones",
        "cot", "tkt", "tickets", "ticket", "cotizaciones_tickets", "cotizacion_ticket",
        "cotizacion_tickets", "quote_ticket", "ticket_quote", "ticket_quotes", "cotizaciones",
        "cotizacion", "quote", "quotes",
    },
    "transport_payments": {
        "transport_payments", "transport_payment", "pay", "pag", "tes", "payments", "payment",
        "tesoreria", "tesoreria_pagos", "pagos", "facturacion", "billing", "cartera", "treasury",
    },
}

def _normalize_role(role: str | None) -> str:
    return str(role or "").strip().lower().replace(" ", "_")


def _normalize_codes(codes: str | Iterable[str] | None) -> set[str]:
    if not codes:
        return set()
    values = [codes] if isinstance(codes, str) else list(codes)
    normalized: set[str] = set()
    for value in values:
        key = str(value or "").strip().lower()
        if not key:
            continue
        normalized.add(key)
        normalized.update(MODULE_ALIASES.get(key, set()))
    return normalized


def extract_bearer_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requerido.",
        )
    if not raw.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization Bearer inválido.",
        )
    token = raw.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization Bearer inválido.",
        )
    return token


def require_role(user: CompanyUser, allowed_roles: set[str] | None = None) -> None:
    if not allowed_roles:
        return
    role = _normalize_role(getattr(user, "role", ""))
    if role in ADMIN_ROLES or role in allowed_roles:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="role_not_allowed",
    )


async def require_enabled_module(
    db: AsyncSession,
    company_id: UUID,
    module_codes: str | Iterable[str] | None,
) -> None:
    codes = _normalize_codes(module_codes)
    if not codes:
        return
    result = await db.execute(
        text(
            """
            SELECT LOWER(m.code) AS code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:company_id AS uuid)
              AND cm.enabled IS TRUE
              AND COALESCE(m.is_active, TRUE) IS TRUE
            """
        ),
        {"company_id": str(company_id)},
    )
    active = {str(row._mapping["code"] or "").lower() for row in result.fetchall()}
    if active.intersection(codes):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="module_not_enabled_for_tenant",
    )


async def require_company_user_for_tenant(
    db: AsyncSession,
    authorization: str | None,
    company_id: UUID,
    *,
    allowed_roles: set[str] | None = None,
    module_codes: str | Iterable[str] | None = None,
) -> CompanyUser:
    user = await get_current_company_user(db, extract_bearer_token(authorization))
    if str(getattr(user, "company_id", "")) != str(company_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_not_allowed",
        )
    require_role(user, allowed_roles)
    await require_enabled_module(db, company_id, module_codes)
    return user


__all__ = [
    "ADMIN_ROLES",
    "READ_ROLES",
    "WRITE_ROLES",
    "extract_bearer_token",
    "get_db",
    "require_company_user_for_tenant",
    "require_enabled_module",
    "require_role",
]
