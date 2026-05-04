from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.saas import Module
from app.schemas.saas import ModuleCreate, ModuleOut

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
