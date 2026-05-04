from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WorkforcePersonnelHistoryOut(BaseModel):
    id: UUID
    company_id: UUID
    employee_id: UUID | None = None
    event_type: str
    event_label: str
    employee_name: str | None = None
    employee_role: str | None = None
    employee_status: str | None = None
    old_values_json: dict = Field(default_factory=dict)
    new_values_json: dict = Field(default_factory=dict)
    changed_fields_json: list[dict] = Field(default_factory=list)
    actor_user_id: UUID | None = None
    source: str
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
