import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModuleCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=80)
    name: str = Field(..., min_length=2, max_length=160)
    description: str | None = None
    category: str | None = Field(default=None, max_length=80)
    is_active: bool = True


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    category: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PackageCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=80)
    name: str = Field(..., min_length=2, max_length=180)
    description: str | None = None
    is_active: bool = True
    module_codes: list[str] = Field(default_factory=list)


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PackageWithModulesOut(PackageOut):
    modules: list[ModuleOut] = Field(default_factory=list)


class CompanyModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    module_id: uuid.UUID
    enabled: bool
    settings: dict[str, Any] = Field(default_factory=dict)
    activated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    module: ModuleOut


class ActivatePackageRequest(BaseModel):
    package_code: str = Field(..., min_length=2, max_length=80)
    settings: dict[str, Any] = Field(default_factory=dict)


class ActivatePackageResponse(BaseModel):
    company_id: uuid.UUID
    package: PackageOut
    modules_activated: list[ModuleOut]
    assignment_status: str = "active"
    idempotent: bool = True
