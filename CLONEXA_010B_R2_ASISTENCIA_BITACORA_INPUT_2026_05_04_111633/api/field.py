from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.field import (
    FieldBillingProjectCreate,
    FieldBillingProjectOut,
    FieldBillingProjectUpdate,
    FieldDashboardSummaryOut,
    FieldMaterialCreate,
    FieldMaterialIssueRequest,
    FieldMaterialLostRequest,
    FieldMaterialMovementOut,
    FieldMaterialOut,
    FieldMaterialRequestCreate,
    FieldMaterialRequestOut,
    FieldMaterialReturnRequest,
    FieldMaterialUpdate,
    FieldMaterialUseRequest,
    FieldTechnicianCreate,
    FieldTechnicianOut,
    FieldTechnicianUpdate,
)
from app.services import field_engine
from app.services.auth_service import get_current_company_user

router = APIRouter()


async def current_company_user(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token requerido.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return await get_current_company_user(db, token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido.")


def company_id_from_user(user):
    company_id = getattr(user, "company_id", None)
    if not company_id:
        raise HTTPException(status_code=401, detail="Usuario sin empresa.")
    return company_id


@router.get("/summary", response_model=FieldDashboardSummaryOut)
async def get_summary(db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.get_field_dashboard_summary(db, company_id_from_user(user))


@router.get("/billing-projects", response_model=List[FieldBillingProjectOut])
async def get_billing_projects(db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.list_billing_projects(db, company_id_from_user(user))


@router.post("/billing-projects", response_model=FieldBillingProjectOut)
async def post_billing_project(payload: FieldBillingProjectCreate, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.create_billing_project(db, company_id_from_user(user), payload)


@router.patch("/billing-projects/{billing_id}", response_model=FieldBillingProjectOut)
async def patch_billing_project(billing_id: UUID, payload: FieldBillingProjectUpdate, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.update_billing_project(db, company_id_from_user(user), billing_id, payload)


@router.get("/technicians", response_model=List[FieldTechnicianOut])
async def get_technicians(db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.list_technicians(db, company_id_from_user(user))


@router.post("/technicians", response_model=FieldTechnicianOut)
async def post_technician(payload: FieldTechnicianCreate, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.create_technician(db, company_id_from_user(user), payload)


@router.patch("/technicians/{technician_id}", response_model=FieldTechnicianOut)
async def patch_technician(technician_id: UUID, payload: FieldTechnicianUpdate, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.update_technician(db, company_id_from_user(user), technician_id, payload)


@router.get("/materials", response_model=List[FieldMaterialOut])
async def get_materials(db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.list_materials(db, company_id_from_user(user))


@router.post("/materials", response_model=FieldMaterialOut)
async def post_material(payload: FieldMaterialCreate, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.create_material(db, company_id_from_user(user), payload)


@router.patch("/materials/{material_id}", response_model=FieldMaterialOut)
async def patch_material(material_id: UUID, payload: FieldMaterialUpdate, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.update_material(db, company_id_from_user(user), material_id, payload)


@router.get("/material-requests", response_model=List[FieldMaterialRequestOut])
async def get_material_requests(db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.list_material_requests(db, company_id_from_user(user))


@router.post("/material-requests", response_model=FieldMaterialRequestOut)
async def post_material_request(payload: FieldMaterialRequestCreate, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.create_material_request(db, company_id_from_user(user), payload)


@router.post("/material-requests/{request_id}/approve", response_model=FieldMaterialRequestOut)
async def approve_request(request_id: UUID, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.approve_material_request(db, company_id_from_user(user), request_id)


@router.post("/material-requests/{request_id}/deliver", response_model=FieldMaterialRequestOut)
async def deliver_request(request_id: UUID, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.deliver_material_request(db, company_id_from_user(user), request_id)


@router.get("/material-movements", response_model=List[FieldMaterialMovementOut])
async def get_material_movements(db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.list_material_movements(db, company_id_from_user(user))


@router.post("/materials/issue", response_model=FieldMaterialMovementOut)
async def post_issue_material(payload: FieldMaterialIssueRequest, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.issue_material(db, company_id_from_user(user), payload)


@router.post("/materials/use", response_model=FieldMaterialMovementOut)
async def post_use_material(payload: FieldMaterialUseRequest, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.use_material(db, company_id_from_user(user), payload)


@router.post("/materials/return", response_model=FieldMaterialMovementOut)
async def post_return_material(payload: FieldMaterialReturnRequest, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.return_material(db, company_id_from_user(user), payload)


@router.post("/materials/lost", response_model=FieldMaterialMovementOut)
async def post_lost_material(payload: FieldMaterialLostRequest, db: AsyncSession = Depends(get_db), user=Depends(current_company_user)):
    return await field_engine.lost_material(db, company_id_from_user(user), payload)
