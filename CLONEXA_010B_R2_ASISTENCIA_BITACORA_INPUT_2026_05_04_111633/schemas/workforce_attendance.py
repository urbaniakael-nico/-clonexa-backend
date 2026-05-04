from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WorkforceAttendanceEventOut(BaseModel):
    id: UUID
    company_id: UUID
    employee_id: UUID
    event_type: str
    event_label: str
    employee_name: str | None = None
    employee_role: str | None = None
    status_after: str
    source: str
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkforceAttendanceTodayOut(BaseModel):
    employee_id: UUID
    company_id: UUID
    employee_name: str
    employee_role: str | None = None
    employee_status: str | None = None
    status: str
    last_event_type: str | None = None
    last_event_at: datetime | None = None
    check_in_at: datetime | None = None
    break_started_at: datetime | None = None
    check_out_at: datetime | None = None
    worked_minutes: int = 0
    break_minutes: int = 0
