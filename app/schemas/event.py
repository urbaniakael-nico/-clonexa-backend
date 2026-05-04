from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    company_id: UUID
    employee_id: UUID | None = None
    event_id: str = Field(min_length=8, max_length=160)
    module: str = Field(min_length=2, max_length=50)
    event_type: str = Field(min_length=2, max_length=100)
    source_channel: str = "api"
    source_ref: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class EventOut(BaseModel):
    id: UUID
    company_id: UUID
    employee_id: UUID | None
    event_id: str
    module: str
    event_type: str
    source_channel: str
    status: str
    duplicate: bool = False
    occurred_at: datetime
    processed_at: datetime | None
    result: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class EventListItem(BaseModel):
    id: UUID
    employee_id: UUID | None
    event_id: str
    module: str
    event_type: str
    source_channel: str
    status: str
    occurred_at: datetime

    model_config = {"from_attributes": True}
