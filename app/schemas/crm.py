from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ActiveEmployeeCard(BaseModel):
    employee_id: UUID
    full_name: str
    status: str
    module: str | None
    active_since: datetime | None
    active_session_id: UUID | None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CRMOverview(BaseModel):
    company_id: UUID
    total_employees: int
    active: int
    paused: int
    lunch: int
    idle: int
    last_events: list[dict[str, Any]]
    active_employees: list[ActiveEmployeeCard]
