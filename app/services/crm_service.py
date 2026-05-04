from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Employee, EmployeeCurrentStatus, WorkEvent
from app.schemas.crm import ActiveEmployeeCard, CRMOverview


class CRMService:
    async def overview(self, db: AsyncSession, company_id: UUID) -> CRMOverview:
        total_employees = await db.scalar(
            select(func.count(Employee.id)).where(Employee.company_id == company_id, Employee.status == "active")
        )
        status_rows = await db.execute(
            select(EmployeeCurrentStatus.status, func.count(EmployeeCurrentStatus.id))
            .where(EmployeeCurrentStatus.company_id == company_id)
            .group_by(EmployeeCurrentStatus.status)
        )
        counts = {status: count for status, count in status_rows.all()}

        cards = await self.active_employees(db, company_id)

        last_event_rows = await db.execute(
            select(WorkEvent)
            .where(WorkEvent.company_id == company_id)
            .order_by(desc(WorkEvent.occurred_at))
            .limit(10)
        )
        last_events: list[dict[str, Any]] = [
            {
                "id": str(event.id),
                "event_id": event.event_id,
                "event_type": event.event_type,
                "module": event.module,
                "status": event.status,
                "occurred_at": event.occurred_at.isoformat(),
            }
            for event in last_event_rows.scalars().all()
        ]

        return CRMOverview(
            company_id=company_id,
            total_employees=total_employees or 0,
            active=counts.get("active", 0),
            paused=counts.get("paused", 0),
            lunch=counts.get("lunch", 0),
            idle=counts.get("idle", 0),
            last_events=last_events,
            active_employees=cards,
        )

    async def active_employees(self, db: AsyncSession, company_id: UUID) -> list[ActiveEmployeeCard]:
        result = await db.execute(
            select(EmployeeCurrentStatus, Employee)
            .join(Employee, Employee.id == EmployeeCurrentStatus.employee_id)
            .where(
                EmployeeCurrentStatus.company_id == company_id,
                EmployeeCurrentStatus.status.in_(["active", "paused", "lunch"]),
            )
            .order_by(EmployeeCurrentStatus.status, Employee.full_name)
        )

        cards: list[ActiveEmployeeCard] = []
        for status, employee in result.all():
            cards.append(
                ActiveEmployeeCard(
                    employee_id=employee.id,
                    full_name=employee.full_name,
                    status=status.status,
                    module=status.module,
                    active_since=status.active_since,
                    active_session_id=status.active_session_id,
                    metadata=status.metadata_json,
                )
            )
        return cards
