from __future__ import annotations

from uuid import UUID
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.auth import CompanyUser
from app.models.core import Employee
from app.schemas.auth import (
    AdminCreateCompanyUserRequest,
    AdminResetPasswordRequest,
    AdminResetPasswordResponse,
    AdminUpdateCompanyUserRequest,
    CompanyUserOut,
    UnlockUserResponse,
)
from app.services.auth_service import (
    company_user_out_payload,
    create_company_user,
    list_company_users,
    reset_company_user_password,
    unlock_company_user,
    update_company_user,
    generate_temporary_password,
    hash_password,
)

router = APIRouter()

# CLONEXA_019C_SALES_MINIPANEL_USERS_BACKEND_START

class SalesMiniPanelUserCreateRequest(BaseModel):
    employee_id: UUID
    link: Optional[str] = None


MINI_PANEL_ALLOWED_TYPES_019C = {"sales", "store", "inventory", "logistics", "other"}
SALES_ROLE_TOKENS_019C = {"vendedor", "ventas", "sales", "comercial", "asesor_comercial", "asesor comercial"}


def _cx_slug_019c(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    text_value = (
        text_value
        .replace("Ã¡", "a").replace("Ã©", "e").replace("Ã­", "i")
        .replace("Ã³", "o").replace("Ãº", "u").replace("Ã±", "n")
    )
    text_value = re.sub(r"[^a-z0-9]+", ".", text_value).strip(".")
    return text_value or "usuario"


def _cx_employee_is_sales_019c(employee: Employee) -> bool:
    role_value = str(getattr(employee, "role", "") or "").strip().lower()
    employee_type = str(getattr(employee, "employee_type", "") or "").strip().lower()
    normalized = {
        role_value,
        employee_type,
        role_value.replace("_", " "),
        role_value.replace(" ", "_"),
        employee_type.replace("_", " "),
        employee_type.replace(" ", "_"),
    }
    return bool(normalized.intersection(SALES_ROLE_TOKENS_019C))


def _cx_operational_email_019c(company_id: UUID, panel_type: str, employee_id: UUID) -> str:
    return f"mini+{panel_type}+{employee_id.hex}@clonexa.local"


def _cx_operational_username_019c(employee: Employee, panel_type: str) -> str:
    name = _cx_slug_019c(getattr(employee, "full_name", "") or getattr(employee, "phone", ""))
    return f"{name}.{panel_type}"[:80]


def _cx_user_settings_019c(user: CompanyUser) -> Dict[str, Any]:
    raw = getattr(user, "settings_json", None)
    return raw if isinstance(raw, dict) else {}


def _cx_is_minipanel_user_019c(user: CompanyUser, panel_type: Optional[str] = None) -> bool:
    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    if not mini_panel.get("enabled"):
        return False
    if panel_type and str(mini_panel.get("type") or "") != str(panel_type):
        return False
    return True


async def _cx_employee_or_404_019c(db: AsyncSession, company_id: UUID, employee_id: UUID) -> Employee:
    result = await db.execute(
        select(Employee).where(
            Employee.company_id == company_id,
            Employee.id == employee_id,
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empleado no encontrado.")
    return employee


async def _cx_find_minipanel_user_019c(
    db: AsyncSession,
    company_id: UUID,
    employee_id: UUID,
    panel_type: str,
) -> Optional[CompanyUser]:
    result = await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    users = result.scalars().all()
    for user in users:
        settings = _cx_user_settings_019c(user)
        mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
        if (
            mini_panel.get("enabled") is True
            and str(mini_panel.get("type") or "") == panel_type
            and str(mini_panel.get("employee_id") or "") == str(employee_id)
        ):
            return user
    return None


def _cx_minipanel_user_payload_019c(user: CompanyUser, temporary_password: Optional[str] = None) -> Dict[str, Any]:
    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    return {
        "id": str(user.id),
        "company_id": str(user.company_id),
        "email": user.email,
        "username": mini_panel.get("username") or user.email,
        "full_name": user.full_name,
        "role": user.role,
        "status": user.status,
        "panel_type": mini_panel.get("type"),
        "employee_id": mini_panel.get("employee_id"),
        "link": mini_panel.get("link"),
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
        "updated_at": user.updated_at.isoformat() if getattr(user, "updated_at", None) else None,
        "temporary_password": temporary_password,
        "already_exists": temporary_password is None,
    }


@router.get("/{company_id}/mini-panel-users")
async def list_mini_panel_users(
    company_id: UUID,
    panel_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[Dict[str, Any]]:
    clean_type = str(panel_type or "").strip().lower() or None
    if clean_type and clean_type not in MINI_PANEL_ALLOWED_TYPES_019C:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de mini panel invalido.")

    result = await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    users = result.scalars().all()
    filtered = [user for user in users if _cx_is_minipanel_user_019c(user, clean_type)]
    return [_cx_minipanel_user_payload_019c(user) for user in filtered]


@router.post("/{company_id}/mini-panel-users/sales/from-employee")
async def create_sales_mini_panel_user(
    company_id: UUID,
    payload: SalesMiniPanelUserCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    employee = await _cx_employee_or_404_019c(db, company_id, payload.employee_id)

    if not _cx_employee_is_sales_019c(employee):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El empleado debe tener rol vendedor, ventas, comercial o asesor comercial.",
        )

    existing = await _cx_find_minipanel_user_019c(db, company_id, payload.employee_id, "sales")
    if existing:
        return _cx_minipanel_user_payload_019c(existing)

    temp_password = generate_temporary_password()
    now = datetime.now(timezone.utc)
    username = _cx_operational_username_019c(employee, "sales")
    email = _cx_operational_email_019c(company_id, "sales", payload.employee_id)

    user = CompanyUser(
        company_id=company_id,
        email=email,
        password_hash=hash_password(temp_password),
        full_name=str(getattr(employee, "full_name", "") or username),
        role="operator",
        status="active",
        must_change_password=True,
        failed_login_attempts=0,
        locked_until=None,
        last_password_reset_at=now,
        created_at=now,
        updated_at=now,
        settings_json={
            "mini_panel": {
                "enabled": True,
                "type": "sales",
                "employee_id": str(payload.employee_id),
                "username": username,
                "link": str(payload.link or ""),
                "source": "client_sales_module",
            }
        },
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return _cx_minipanel_user_payload_019c(user, temporary_password=temp_password)

# CLONEXA_019C_SALES_MINIPANEL_USERS_BACKEND_END




@router.get("/{company_id}/users", response_model=list[CompanyUserOut])
async def list_users(company_id: UUID, db: AsyncSession = Depends(get_db)):
    users = await list_company_users(db, company_id)
    return [await company_user_out_payload(db, user) for user in users]


@router.post("/{company_id}/users", response_model=CompanyUserOut)
async def create_user(
    company_id: UUID,
    payload: AdminCreateCompanyUserRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await create_company_user(db, company_id, payload)
    return await company_user_out_payload(db, user)


@router.put("/{company_id}/users/{user_id}", response_model=CompanyUserOut)
async def update_user(
    company_id: UUID,
    user_id: UUID,
    payload: AdminUpdateCompanyUserRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await update_company_user(db, company_id, user_id, payload)
    return await company_user_out_payload(db, user)


@router.post("/{company_id}/users/{user_id}/reset-password", response_model=AdminResetPasswordResponse)
async def reset_password(
    company_id: UUID,
    user_id: UUID,
    payload: AdminResetPasswordRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    password = payload.password if payload else None
    return await reset_company_user_password(db, company_id, user_id, password)


@router.post("/{company_id}/users/{user_id}/unlock", response_model=UnlockUserResponse)
async def unlock_user(company_id: UUID, user_id: UUID, db: AsyncSession = Depends(get_db)):
    return await unlock_company_user(db, company_id, user_id)
