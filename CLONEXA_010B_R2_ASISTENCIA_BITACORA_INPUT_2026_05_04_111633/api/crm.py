from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.crm import ActiveEmployeeCard, CRMOverview
from app.services.crm_service import CRMService

router = APIRouter()


@router.get("/overview", response_model=CRMOverview)
async def crm_overview(
    company_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> CRMOverview:
    return await CRMService().overview(db, company_id)


@router.get("/active-employees", response_model=list[ActiveEmployeeCard])
async def active_employees(
    company_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[ActiveEmployeeCard]:
    return await CRMService().active_employees(db, company_id)
