from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.saas import CompanyModule, Module, PackageModule
from app.schemas.saas import ModuleCreate, ModuleOut
from app.web.admin_v2_routes import _valid_session

router = APIRouter()


@router.get("", response_model=list[ModuleOut])
async def list_modules(
    db: AsyncSession = Depends(get_db),
    active_only: bool = False,
) -> list[Module]:
    stmt = select(Module).order_by(Module.category.asc().nullslast(), Module.code.asc())
    if active_only:
        stmt = stmt.where(Module.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=ModuleOut, status_code=status.HTTP_201_CREATED)
async def create_module(
    payload: ModuleCreate,
    db: AsyncSession = Depends(get_db),
) -> Module:
    existing = await db.execute(select(Module.id).where(Module.code == payload.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="module_code_already_exists")

    module = Module(**payload.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


@router.delete("/{module_code}")
async def delete_module(
    module_code: str,
    request: Request,
    confirm: str = Query(..., min_length=2, max_length=80),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int | bool]:
    if not _valid_session(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin_v2_session_required")

    code = module_code.strip()
    if confirm.strip() != code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="module_delete_confirmation_mismatch")

    result = await db.execute(select(Module).where(Module.code == code))
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="module_not_found")

    company_links = await db.scalar(
        select(func.count()).select_from(CompanyModule).where(CompanyModule.module_id == module.id)
    ) or 0
    package_links = await db.scalar(
        select(func.count()).select_from(PackageModule).where(PackageModule.module_id == module.id)
    ) or 0
    if company_links or package_links:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "module_in_use",
                "company_links": int(company_links),
                "package_links": int(package_links),
            },
        )

    await db.delete(module)
    await db.commit()
    return {"ok": True, "deleted_code": code, "company_links": 0, "package_links": 0}
