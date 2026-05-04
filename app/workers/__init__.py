from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import EmployeeCurrentStatus, WorkEvent, WorkSession


ACTIVE_SESSION_STATUS = "active"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def minutes_between(started_at: datetime, ended_at: datetime) -> Decimal:
    diff = max(0.0, (ended_at - started_at).total_seconds() / 60)
    return Decimal(str(round(diff, 2)))


class WorkforceEngine:
    async def get_active_session(
        self,
        db: AsyncSession,
        company_id: UUID,
        employee_id: UUID,
    ) -> WorkSession | None:
        result = await db.execute(
            select(WorkSession)
            .where(
                WorkSession.company_id == company_id,
                WorkSession.employee_id == employee_id,
                WorkSession.status == ACTIVE_SESSION_STATUS,
            )
            .order_by(WorkSession.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_current_status(
        self,
        db: AsyncSession,
        company_id: UUID,
        employee_id: UUID,
    ) -> EmployeeCurrentStatus | None:
        result = await db.execute(
            select(EmployeeCurrentStatus).where(
                EmployeeCurrentStatus.company_id == company_id,
                EmployeeCurrentStatus.employee_id == employee_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_current_status(
        self,
        db: AsyncSession,
        company_id: UUID,
        employee_id: UUID,
        status: str,
        module: str | None,
        active_session_id: UUID | None,
        active_since: datetime | None,
        event: WorkEvent,
        metadata: dict,
    ) -> EmployeeCurrentStatus:
        current = await self.get_current_status(db, company_id, employee_id)

        if current is None:
            current = EmployeeCurrentStatus(
                company_id=company_id,
                employee_id=employee_id,
                status=status,
                module=module,
                active_session_id=active_session_id,
                active_since=active_since,
                last_event_id=event.event_id,
                last_event_at=event.occurred_at,
                metadata_json=metadata,
            )
            db.add(current)
            await db.flush()
            return current

        current.status = status
        current.module = module
        current.active_session_id = active_session_id
        current.active_since = active_since
        current.last_event_id = event.event_id
        current.last_event_at = event.occurred_at
        current.metadata_json = metadata
        await db.flush()
        return current

    async def start_session(self, db: AsyncSession, event: WorkEvent) -> dict:
        if event.employee_id is None:
            raise ValueError("employee_id is required for shift start")

        active = await self.get_active_session(db, event.company_id, event.employee_id)
        if active:
            await self.upsert_current_status(
                db=db,
                company_id=event.company_id,
                employee_id=event.employee_id,
                status="active",
                module=active.module,
                active_session_id=active.id,
                active_since=active.started_at,
                event=event,
                metadata={"already_active": True},
            )
            return {"ok": True, "already_active": True, "session_id": str(active.id)}

        session = WorkSession(
            company_id=event.company_id,
            employee_id=event.employee_id,
            start_event_db_id=event.id,
            module=event.module,
            status=ACTIVE_SESSION_STATUS,
            started_at=event.occurred_at,
            work_type=event.payload_json.get("work_type"),
            reference_type=event.payload_json.get("reference_type"),
            reference_id=event.payload_json.get("reference_id"),
            location_id=event.payload_json.get("location_id"),
            notes=event.payload_json.get("notes"),
        )
        db.add(session)
        await db.flush()

        await self.upsert_current_status(
            db=db,
            company_id=event.company_id,
            employee_id=event.employee_id,
            status="active",
            module=event.module,
            active_session_id=session.id,
            active_since=session.started_at,
            event=event,
            metadata=event.payload_json,
        )

        return {"ok": True, "session_id": str(session.id), "status": "active"}

    async def close_active_session(self, db: AsyncSession, event: WorkEvent, closed_status: str) -> dict:
        if event.employee_id is None:
            raise ValueError("employee_id is required for shift close")

        active = await self.get_active_session(db, event.company_id, event.employee_id)
        if not active:
            await self.upsert_current_status(
                db=db,
                company_id=event.company_id,
                employee_id=event.employee_id,
                status=closed_status,
                module=event.module,
                active_session_id=None,
                active_since=None,
                event=event,
                metadata={"no_active_session": True},
            )
            return {"ok": True, "no_active_session": True, "status": closed_status}

        ended_at = event.occurred_at
        active.ended_at = ended_at
        active.end_event_db_id = event.id
        active.status = closed_status
        active.duration_minutes = minutes_between(active.started_at, ended_at)
        if event.payload_json.get("notes"):
            active.notes = event.payload_json["notes"]
        await db.flush()

        await self.upsert_current_status(
            db=db,
            company_id=event.company_id,
            employee_id=event.employee_id,
            status=closed_status,
            module=event.module,
            active_session_id=None,
            active_since=None,
            event=event,
            metadata={
                **event.payload_json,
                "closed_session_id": str(active.id),
                "duration_minutes": float(active.duration_minutes or 0),
            },
        )

        return {
            "ok": True,
            "session_id": str(active.id),
            "status": closed_status,
            "duration_minutes": float(active.duration_minutes or 0),
        }

    async def handle(self, db: AsyncSession, event: WorkEvent) -> dict:
        handlers = {
            "shift_started": lambda: self.start_session(db, event),
            "shift_resumed": lambda: self.start_session(db, event),
            "shift_lunch_ended": lambda: self.start_session(db, event),
            "shift_paused": lambda: self.close_active_session(db, event, "paused"),
            "shift_lunch_started": lambda: self.close_active_session(db, event, "lunch"),
            "shift_ended": lambda: self.close_active_session(db, event, "finalized"),
            "shift_force_closed": lambda: self.close_active_session(db, event, "force_closed"),
        }

        handler = handlers.get(event.event_type)
        if handler is None:
            return {"ok": True, "ignored_by_workforce": True}

        return await handler()

