from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class EmployeeBase(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=180)
    document_id: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str | None = "active"
    employee_type: str | None = "operator"
    role: str | None = "operator"
    telegram_user_id: str | None = None
    telegram_username: str | None = None
    hire_date: str | None = None
    hourly_rate_regular: Decimal | None = Decimal("0")
    hourly_rate_extra: Decimal | None = Decimal("0")
    deduction_1: Decimal | None = Decimal("0")
    deduction_2: Decimal | None = Decimal("0")
    notes: str | None = None


class EmployeeCreate(EmployeeBase):
    company_id: UUID
    full_name: str = Field(min_length=2, max_length=180)


class EmployeeUpdate(EmployeeBase):
    pass


class EmployeeOut(BaseModel):
    id: UUID
    company_id: UUID
    full_name: str
    document_id: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str
    employee_type: str
    role: str | None = None
    telegram_user_id: str | None = None
    telegram_username: str | None = None
    hire_date: str | None = None
    hourly_rate_regular: Decimal = Decimal("0")
    hourly_rate_extra: Decimal = Decimal("0")
    deduction_1: Decimal = Decimal("0")
    deduction_2: Decimal = Decimal("0")
    notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
