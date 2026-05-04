import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.saas import Module, Package, PackageModule
from app.schemas.saas import PackageCreate, PackageOut, PackageWithModulesOut
from app.services.saas_packages import get_package_with_modules_or_404

router = APIRouter()


def serialize_package_with_modules(package: Package) -> PackageWithModulesOut:
    modules = [link.module for link in package.module_links if link.module]
    data = PackageOut.model_validate(package).model_dump()
    data["modules"] = modules
    return PackageWithModulesOut.model_validate(data)


@router.get("", response_model=list[PackageOut])
async def list_packages(
    db: AsyncSession = Depends(get_db),
    active_only: bool = False,
) -> list[Package]:
    stmt = select(Package).order_by(Package.code.asc())
    if active_only:
        stmt = stmt.where(Package.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=PackageWithModulesOut, status_code=status.HTTP_201_CREATED)
async def create_package(
    payload: PackageCreate,
    db: AsyncSession = Depends(get_db),
) -> PackageWithModulesOut:
    existing = await db.execute(select(Package.id).where(Package.code == payload.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="package_code_already_exists")

    package = Package(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(package)
    await db.flush()

    if payload.module_codes:
        module_result = await db.execute(select(Module).where(Module.code.in_(payload.module_codes)))
        modules = list(module_result.scalars().all())
        found_codes = {m.code for m in modules}
        missing = sorted(set(payload.module_codes) - found_codes)
        if missing:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "modules_not_found", "module_codes": missing},
            )

        for module in modules:
            db.add(PackageModule(package_id=package.id, module_id=module.id, settings={}))

    await db.commit()
    package = await get_package_with_modules_or_404(db, package.id)
    return serialize_package_with_modules(package)


@router.get("/{package_id}", response_model=PackageWithModulesOut)
async def get_package(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PackageWithModulesOut:
    package = await get_package_with_modules_or_404(db, package_id)
    return serialize_package_with_modules(package)
