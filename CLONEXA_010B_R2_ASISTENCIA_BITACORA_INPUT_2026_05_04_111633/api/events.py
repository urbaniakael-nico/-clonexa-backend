from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.core import WorkEvent
from app.schemas.event import EventCreate, EventListItem, EventOut
from app.services.event_engine import EventEngine

router = APIRouter()


@router.post("", response_model=EventOut)
async def create_event(payload: EventCreate, db: AsyncSession = Depends(get_db)) -> EventOut:
    return await EventEngine().process(db, payload)


@router.get("", response_model=list[EventListItem])
async def list_events(
    company_id: UUID = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[WorkEvent]:
    result = await db.execute(
        select(WorkEvent)
        .where(WorkEvent.company_id == company_id)
        .order_by(desc(WorkEvent.occurred_at))
        .limit(limit)
    )
    return list(result.scalars().all())
