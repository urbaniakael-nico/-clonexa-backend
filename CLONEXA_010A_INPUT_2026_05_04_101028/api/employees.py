from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.core import Company, Employee
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate

router = APIRouter()


def clean_empty(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def normalize_employee_payload(data: dict) -> dict:
    clean = {}
    for key, value in data.items():
        clean[key] = clean_empty(value)

    if clean.get("role") and not clean.get("employee_type"):
        clean["employee_type"] = clean["role"]

    if clean.get("employee_type") and not clean.get("role"):
        clean["role"] = clean["employee_type"]

    if not clean.get("role"):
        clean["role"] = "operator"

    if not clean.get("employee_type"):
        clean["employee_type"] = clean["role"]

    if not clean.get("status"):
        clean["status"] = "active"

    for money_field in ["hourly_rate_regular", "hourly_rate_extra", "deduction_1", "deduction_2"]:
        if clean.get(money_field) is None:
            clean[money_field] = 0

    return clean


async def get_employee_or_404(db: AsyncSession, employee_id: UUID) -> Employee:
    employee = await db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="employee_not_found")
    return employee


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(payload: EmployeeCreate, db: AsyncSession = Depends(get_db)) -> Employee:
    company = await db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company_not_found")

    data = normalize_employee_payload(payload.model_dump())
    employee = Employee(**data)

    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return employee


@router.get("", response_model=list[EmployeeOut])
async def list_employees(
    company_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    include_archived: bool = False,
) -> list[Employee]:
    stmt = (
        select(Employee)
        .where(Employee.company_id == company_id)
        .order_by(Employee.full_name.asc())
    )

    if not include_archived:
        stmt = stmt.where(Employee.status != "archived")

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: UUID, db: AsyncSession = Depends(get_db)) -> Employee:
    return await get_employee_or_404(db, employee_id)


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
) -> Employee:
    employee = await get_employee_or_404(db, employee_id)
    data = normalize_employee_payload(payload.model_dump(exclude_unset=True))

    for key, value in data.items():
        if hasattr(employee, key):
            setattr(employee, key, value)

    await db.commit()
    await db.refresh(employee)
    return employee


@router.post("/{employee_id}/activate", response_model=EmployeeOut)
async def activate_employee(employee_id: UUID, db: AsyncSession = Depends(get_db)) -> Employee:
    employee = await get_employee_or_404(db, employee_id)
    employee.status = "active"
    await db.commit()
    await db.refresh(employee)
    return employee


@router.post("/{employee_id}/deactivate", response_model=EmployeeOut)
async def deactivate_employee(employee_id: UUID, db: AsyncSession = Depends(get_db)) -> Employee:
    employee = await get_employee_or_404(db, employee_id)
    employee.status = "inactive"
    await db.commit()
    await db.refresh(employee)
    return employee


@router.post("/{employee_id}/archive", response_model=EmployeeOut)
async def archive_employee(employee_id: UUID, db: AsyncSession = Depends(get_db)) -> Employee:
    employee = await get_employee_or_404(db, employee_id)
    employee.status = "archived"
    await db.commit()
    await db.refresh(employee)
    return employee
