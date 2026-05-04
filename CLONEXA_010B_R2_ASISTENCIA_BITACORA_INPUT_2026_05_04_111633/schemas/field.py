from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ClonexaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FieldBillingProjectCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=255)
    client_name: Optional[str] = None
    location: Optional[str] = None
    status: str = "active"
    budget_amount: Decimal = Decimal("0")
    notes: Optional[str] = None
    settings_json: Dict[str, Any] = Field(default_factory=dict)


class FieldBillingProjectUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    client_name: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    budget_amount: Optional[Decimal] = None
    notes: Optional[str] = None
    settings_json: Optional[Dict[str, Any]] = None


class FieldBillingProjectOut(ClonexaSchema):
    id: UUID
    company_id: UUID
    code: str
    name: str
    client_name: Optional[str] = None
    location: Optional[str] = None
    status: str
    budget_amount: Decimal
    notes: Optional[str] = None
    settings_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class FieldTechnicianCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = None
    role: str = "technician"
    status: str = "active"
    is_supervisor: bool = False
    hourly_rate_regular: Decimal = Decimal("0")
    hourly_rate_extra: Decimal = Decimal("0")
    discount_1: Decimal = Decimal("0")
    discount_2: Decimal = Decimal("0")
    default_billing_project_id: Optional[UUID] = None
    notes: Optional[str] = None
    settings_json: Dict[str, Any] = Field(default_factory=dict)


class FieldTechnicianUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    is_supervisor: Optional[bool] = None
    hourly_rate_regular: Optional[Decimal] = None
    hourly_rate_extra: Optional[Decimal] = None
    discount_1: Optional[Decimal] = None
    discount_2: Optional[Decimal] = None
    default_billing_project_id: Optional[UUID] = None
    notes: Optional[str] = None
    settings_json: Optional[Dict[str, Any]] = None


class FieldTechnicianOut(ClonexaSchema):
    id: UUID
    company_id: UUID
    default_billing_project_id: Optional[UUID] = None
    full_name: str
    phone: Optional[str] = None
    role: str
    status: str
    is_supervisor: bool
    hourly_rate_regular: Decimal
    hourly_rate_extra: Decimal
    discount_1: Decimal
    discount_2: Decimal
    notes: Optional[str] = None
    settings_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class FieldMaterialCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    sku: Optional[str] = None
    category: Optional[str] = None
    unit: str = "unit"
    status: str = "active"
    stock_available: Decimal = Decimal("0")
    stock_min: Decimal = Decimal("0")
    stock_in_field: Decimal = Decimal("0")
    stock_damaged: Decimal = Decimal("0")
    unit_cost: Decimal = Decimal("0")
    notes: Optional[str] = None
    settings_json: Dict[str, Any] = Field(default_factory=dict)


class FieldMaterialUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    status: Optional[str] = None
    stock_available: Optional[Decimal] = None
    stock_min: Optional[Decimal] = None
    stock_in_field: Optional[Decimal] = None
    stock_damaged: Optional[Decimal] = None
    unit_cost: Optional[Decimal] = None
    notes: Optional[str] = None
    settings_json: Optional[Dict[str, Any]] = None


class FieldMaterialOut(ClonexaSchema):
    id: UUID
    company_id: UUID
    sku: Optional[str] = None
    name: str
    category: Optional[str] = None
    unit: str
    status: str
    stock_available: Decimal
    stock_min: Decimal
    stock_in_field: Decimal
    stock_damaged: Decimal
    unit_cost: Decimal
    notes: Optional[str] = None
    settings_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class FieldMaterialRequestItemCreate(BaseModel):
    material_id: UUID
    quantity_requested: Decimal = Field(..., gt=0)
    notes: Optional[str] = None


class FieldMaterialRequestCreate(BaseModel):
    requested_by_technician_id: UUID
    billing_project_id: Optional[UUID] = None
    notes: Optional[str] = None
    items: List[FieldMaterialRequestItemCreate] = Field(default_factory=list, min_length=1)


class FieldMaterialRequestItemOut(ClonexaSchema):
    id: UUID
    request_id: UUID
    company_id: UUID
    material_id: UUID
    quantity_requested: Decimal
    quantity_delivered: Decimal
    notes: Optional[str] = None
    created_at: datetime


class FieldMaterialRequestOut(ClonexaSchema):
    id: UUID
    company_id: UUID
    requested_by_technician_id: UUID
    billing_project_id: Optional[UUID] = None
    status: str
    notes: Optional[str] = None
    requested_at: datetime
    approved_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    items: List[FieldMaterialRequestItemOut] = Field(default_factory=list)


class FieldMaterialIssueRequest(BaseModel):
    technician_id: UUID
    material_id: UUID
    billing_project_id: Optional[UUID] = None
    request_id: Optional[UUID] = None
    quantity: Decimal = Field(..., gt=0)
    notes: Optional[str] = None


class FieldMaterialUseRequest(BaseModel):
    technician_id: UUID
    material_id: UUID
    billing_project_id: Optional[UUID] = None
    quantity: Decimal = Field(..., gt=0)
    notes: Optional[str] = None


class FieldMaterialReturnRequest(BaseModel):
    technician_id: UUID
    material_id: UUID
    billing_project_id: Optional[UUID] = None
    quantity: Decimal = Field(..., gt=0)
    condition: str = "good"
    notes: Optional[str] = None


class FieldMaterialLostRequest(BaseModel):
    technician_id: UUID
    material_id: UUID
    billing_project_id: Optional[UUID] = None
    quantity: Decimal = Field(..., gt=0)
    notes: Optional[str] = None


class FieldMaterialMovementOut(ClonexaSchema):
    id: UUID
    company_id: UUID
    material_id: UUID
    technician_id: Optional[UUID] = None
    billing_project_id: Optional[UUID] = None
    request_id: Optional[UUID] = None
    movement_type: str
    quantity: Decimal
    unit_cost: Decimal
    condition: Optional[str] = None
    notes: Optional[str] = None
    created_by_user_id: Optional[UUID] = None
    created_at: datetime


class FieldDashboardSummaryOut(BaseModel):
    technicians_total: int
    technicians_active: int
    supervisors_total: int
    materials_total: int
    stock_low_count: int
    stock_available_total: Decimal
    stock_in_field_total: Decimal
    stock_damaged_total: Decimal
    material_requests_pending: int
    billing_projects_active: int
    inventory_movements_total: int
