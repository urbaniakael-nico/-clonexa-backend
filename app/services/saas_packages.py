import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.core import Company
from app.models.saas import CompanyModule, CompanyPackageAssignment, Module, Package, PackageModule
from app.schemas.saas import ActivatePackageRequest, ActivatePackageResponse, PackageOut


async def get_package_with_modules_or_404(db: AsyncSession, package_id: uuid.UUID) -> Package:
    result = await db.execute(
        select(Package)
        .options(selectinload(Package.module_links).selectinload(PackageModule.module))
        .where(Package.id == package_id)
    )
    package = result.scalar_one_or_none()
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package_not_found")
    return package


async def activate_package_for_company(
    db: AsyncSession,
    company_id: uuid.UUID,
    payload: ActivatePackageRequest,
) -> ActivatePackageResponse:
    now = datetime.now(timezone.utc)

    company_result = await db.execute(select(Company.id).where(Company.id == company_id))
    if company_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")

    package_result = await db.execute(
        select(Package)
        .options(selectinload(Package.module_links).selectinload(PackageModule.module))
        .where(Package.code == payload.package_code, Package.is_active.is_(True))
    )
    package = package_result.scalar_one_or_none()
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package_not_found_or_inactive")

    modules = [link.module for link in package.module_links if link.module and link.module.is_active]
    if not modules:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="package_has_no_active_modules")

    # Regla SaaS: una empresa puede tener un paquete activo.
    await db.execute(
        update(CompanyPackageAssignment)
        .where(
            CompanyPackageAssignment.company_id == company_id,
            CompanyPackageAssignment.package_id != package.id,
            CompanyPackageAssignment.status == "active",
        )
        .values(status="inactive", updated_at=now)
    )

    assignment_result = await db.execute(
        select(CompanyPackageAssignment).where(
            CompanyPackageAssignment.company_id == company_id,
            CompanyPackageAssignment.package_id == package.id,
        )
    )
    assignment = assignment_result.scalar_one_or_none()
    if assignment:
        assignment.status = "active"
        assignment.settings = payload.settings or {}
        assignment.activated_at = assignment.activated_at or now
        assignment.updated_at = now
    else:
        assignment = CompanyPackageAssignment(
            company_id=company_id,
            package_id=package.id,
            status="active",
            settings=payload.settings or {},
            activated_at=now,
        )
        db.add(assignment)

    activated_modules: list[Module] = []

    for module in modules:
        company_module_result = await db.execute(
            select(CompanyModule).where(
                CompanyModule.company_id == company_id,
                CompanyModule.module_id == module.id,
            )
        )
        company_module = company_module_result.scalar_one_or_none()

        if company_module:
            company_module.enabled = True
            company_module.activated_at = company_module.activated_at or now
            company_module.updated_at = now
            if company_module.settings is None:
                company_module.settings = {}
        else:
            db.add(
                CompanyModule(
                    company_id=company_id,
                    module_id=module.id,
                    enabled=True,
                    settings={},
                    activated_at=now,
                )
            )

        activated_modules.append(module)

    await db.commit()

    package_out = PackageOut.model_validate(package)
    modules_out = [module for module in activated_modules]

    return ActivatePackageResponse(
        company_id=company_id,
        package=package_out,
        modules_activated=modules_out,
        assignment_status="active",
        idempotent=True,
    )

