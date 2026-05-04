from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    slug: str = Field(min_length=2, max_length=80)
    timezone: str = "America/Bogota"
    plan: str = "starter"
    settings_json: dict[str, Any] = Field(default_factory=dict)


class CompanyOut(BaseModel):
    id: UUID
    name: str
    slug: str
    timezone: str
    status: str
    plan: str
    settings_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
