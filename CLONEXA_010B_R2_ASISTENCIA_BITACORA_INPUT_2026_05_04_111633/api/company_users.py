from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
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
)

router = APIRouter()


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
