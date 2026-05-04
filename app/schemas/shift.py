import uuid
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.event import EventCreate


class ShiftAction(BaseModel):
    company_id: UUID
    employee_id: UUID
    module: str = "core"
    source_channel: str = "api"
    event_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_event(self, event_type: str) -> EventCreate:
        return EventCreate(
            company_id=self.company_id,
            employee_id=self.employee_id,
            event_id=self.event_id or f"{self.employee_id}-{event_type}-{uuid.uuid4().hex[:16]}",
            module=self.module,
            event_type=event_type,
            source_channel=self.source_channel,
            payload=self.payload,
        )
