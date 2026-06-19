import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.api.v1.endpoints.module_catalog_v1 import sync_module_catalog
from app.models.saas import CompanyModule, Module
from app.schemas.saas import ActivatePackageRequest, ActivatePackageResponse, CompanyModuleOut
from app.services.saas_packages import activate_package_for_company

router = APIRouter()


async def get_module_by_code_or_404(db: AsyncSession, module_code: str) -> Module:
    code = str(module_code or "").strip()
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="module_code_required")

    await sync_module_catalog(db)
    result = await db.execute(select(Module).where(Module.code == code))
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="module_not_found")
    return module


async def get_company_module_link(
    db: AsyncSession,
    company_id: uuid.UUID,
    module_id: uuid.UUID,
) -> CompanyModule | None:
    result = await db.execute(
        select(CompanyModule)
        .options(selectinload(CompanyModule.module))
        .where(
            CompanyModule.company_id == company_id,
            CompanyModule.module_id == module_id,
        )
    )
    return result.scalar_one_or_none()


async def get_company_module_out(
    db: AsyncSession,
    company_id: uuid.UUID,
    module_id: uuid.UUID,
) -> CompanyModule:
    result = await db.execute(
        select(CompanyModule)
        .options(selectinload(CompanyModule.module))
        .where(
            CompanyModule.company_id == company_id,
            CompanyModule.module_id == module_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_module_not_found")
    return row


def payload_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    settings = payload.get("settings")
    return settings if isinstance(settings, dict) else {}


@router.get("/{company_id}/modules", response_model=list[CompanyModuleOut])
async def list_company_modules(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    enabled_only: bool = True,
) -> list[CompanyModule]:
    stmt = (
        select(CompanyModule)
        .options(selectinload(CompanyModule.module))
        .where(CompanyModule.company_id == company_id)
        .order_by(CompanyModule.created_at.asc())
    )
    if enabled_only:
        stmt = stmt.where(CompanyModule.enabled.is_(True))

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/{company_id}/modules/{module_code}/activate", response_model=CompanyModuleOut)
async def activate_company_module(
    company_id: uuid.UUID,
    module_code: str,
    payload: dict[str, Any] | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> CompanyModule:
    module = await get_module_by_code_or_404(db, module_code)
    row = await get_company_module_link(db, company_id, module.id)
    now = datetime.now(timezone.utc)
    settings = payload_settings(payload)

    if row:
        row.enabled = True
        row.activated_at = row.activated_at or now
        if settings:
            row.settings = {**(row.settings or {}), **settings}
    else:
        row = CompanyModule(
            company_id=company_id,
            module_id=module.id,
            enabled=True,
            settings=settings,
            activated_at=now,
        )
        db.add(row)

    await db.commit()
    return await get_company_module_out(db, company_id, module.id)


@router.post("/{company_id}/modules/{module_code}/deactivate", response_model=CompanyModuleOut)
async def deactivate_company_module(
    company_id: uuid.UUID,
    module_code: str,
    payload: dict[str, Any] | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> CompanyModule:
    module = await get_module_by_code_or_404(db, module_code)
    row = await get_company_module_link(db, company_id, module.id)
    settings = payload_settings(payload)

    if row:
        row.enabled = False
        if settings:
            row.settings = {**(row.settings or {}), **settings}
    else:
        row = CompanyModule(
            company_id=company_id,
            module_id=module.id,
            enabled=False,
            settings=settings,
            activated_at=None,
        )
        db.add(row)

    await db.commit()
    return await get_company_module_out(db, company_id, module.id)


@router.post("/{company_id}/activate-package", response_model=ActivatePackageResponse)
async def activate_company_package(
    company_id: uuid.UUID,
    payload: ActivatePackageRequest,
    db: AsyncSession = Depends(get_db),
) -> ActivatePackageResponse:
    return await activate_package_for_company(db=db, company_id=company_id, payload=payload)
