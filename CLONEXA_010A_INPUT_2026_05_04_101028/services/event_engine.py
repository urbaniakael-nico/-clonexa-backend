from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import WorkEvent
from app.schemas.event import EventCreate, EventOut
from app.services.workforce_engine import WorkforceEngine


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


WORKFORCE_EVENTS = {
    "shift_started",
    "shift_paused",
    "shift_resumed",
    "shift_lunch_started",
    "shift_lunch_ended",
    "shift_ended",
    "shift_force_closed",
}


class EventEngine:
    def __init__(self) -> None:
        self.workforce = WorkforceEngine()

    async def process(self, db: AsyncSession, payload: EventCreate) -> EventOut:
        existing_result = await db.execute(
            select(WorkEvent).where(
                WorkEvent.company_id == payload.company_id,
                WorkEvent.event_id == payload.event_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return EventOut(
                id=existing.id,
                company_id=existing.company_id,
                employee_id=existing.employee_id,
                event_id=existing.event_id,
                module=existing.module,
                event_type=existing.event_type,
                source_channel=existing.source_channel,
                status=existing.status,
                duplicate=True,
                occurred_at=existing.occurred_at,
                processed_at=existing.processed_at,
                result={"duplicate": True},
            )

        event = WorkEvent(
            company_id=payload.company_id,
            employee_id=payload.employee_id,
            event_id=payload.event_id,
            module=payload.module,
            event_type=payload.event_type,
            source_channel=payload.source_channel,
            source_ref=payload.source_ref,
            payload_json=payload.payload,
            metadata_json=payload.metadata,
            occurred_at=payload.occurred_at or utcnow(),
            status="processing",
        )

        db.add(event)

        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            duplicate_result = await db.execute(
                select(WorkEvent).where(
                    WorkEvent.company_id == payload.company_id,
                    WorkEvent.event_id == payload.event_id,
                )
            )
            duplicate = duplicate_result.scalar_one()
            return EventOut(
                id=duplicate.id,
                company_id=duplicate.company_id,
                employee_id=duplicate.employee_id,
                event_id=duplicate.event_id,
                module=duplicate.module,
                event_type=duplicate.event_type,
                source_channel=duplicate.source_channel,
                status=duplicate.status,
                duplicate=True,
                occurred_at=duplicate.occurred_at,
                processed_at=duplicate.processed_at,
                result={"duplicate": True},
            )

        result = {"ok": True}

        try:
            if event.event_type in WORKFORCE_EVENTS:
                result = await self.workforce.handle(db, event)

            event.status = "processed"
            event.processed_at = utcnow()
            await db.commit()
            await db.refresh(event)

            return EventOut(
                id=event.id,
                company_id=event.company_id,
                employee_id=event.employee_id,
                event_id=event.event_id,
                module=event.module,
                event_type=event.event_type,
                source_channel=event.source_channel,
                status=event.status,
                duplicate=False,
                occurred_at=event.occurred_at,
                processed_at=event.processed_at,
                result=result,
            )

        except Exception as exc:
            event.status = "failed"
            event.error_message = str(exc)
            event.processed_at = utcnow()
            await db.commit()
            raise
