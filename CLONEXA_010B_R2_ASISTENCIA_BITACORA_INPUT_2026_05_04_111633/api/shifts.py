from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.event import EventOut
from app.schemas.shift import ShiftAction
from app.services.event_engine import EventEngine

router = APIRouter()


@router.post("/start", response_model=EventOut)
async def start_shift(payload: ShiftAction, db: AsyncSession = Depends(get_db)) -> EventOut:
    return await EventEngine().process(db, payload.to_event("shift_started"))


@router.post("/pause", response_model=EventOut)
async def pause_shift(payload: ShiftAction, db: AsyncSession = Depends(get_db)) -> EventOut:
    return await EventEngine().process(db, payload.to_event("shift_paused"))


@router.post("/resume", response_model=EventOut)
async def resume_shift(payload: ShiftAction, db: AsyncSession = Depends(get_db)) -> EventOut:
    return await EventEngine().process(db, payload.to_event("shift_resumed"))


@router.post("/lunch/start", response_model=EventOut)
async def start_lunch(payload: ShiftAction, db: AsyncSession = Depends(get_db)) -> EventOut:
    return await EventEngine().process(db, payload.to_event("shift_lunch_started"))


@router.post("/lunch/end", response_model=EventOut)
async def end_lunch(payload: ShiftAction, db: AsyncSession = Depends(get_db)) -> EventOut:
    return await EventEngine().process(db, payload.to_event("shift_lunch_ended"))


@router.post("/end", response_model=EventOut)
async def end_shift(payload: ShiftAction, db: AsyncSession = Depends(get_db)) -> EventOut:
    return await EventEngine().process(db, payload.to_event("shift_ended"))


@router.post("/force-close", response_model=EventOut)
async def force_close_shift(payload: ShiftAction, db: AsyncSession = Depends(get_db)) -> EventOut:
    return await EventEngine().process(db, payload.to_event("shift_force_closed"))
