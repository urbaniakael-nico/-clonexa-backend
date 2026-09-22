"""Fase 2: a mini-panel shift left open (active or on break) past
shift_max_hours (default 12h) auto-closes with closed_reason='cierre_automatico'
the next time it's loaded. Before this, nothing ever closed a stale shift --
that's how shifts reached 185+ hours open in production. This must only ever
touch a company with waiter_ordering enabled (today: Asadero El Socio).
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import company_users


def _row(status="active", started_at=None, active_started_at=None):
    started_at = started_at or datetime.now(timezone.utc)
    return {
        "id": uuid.uuid4(),
        "status": status,
        "started_at": started_at,
        "active_started_at": active_started_at or started_at,
        "current_break_started_at": None,
        "active_seconds": 0,
        "break_seconds": 0,
    }


@pytest.mark.asyncio
async def test_a_normal_two_hour_shift_is_left_untouched(monkeypatch):
    monkeypatch.setattr(company_users, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_module_settings_026k", AsyncMock(return_value={"shift_max_hours": 12}))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    row = _row(started_at=datetime.now(timezone.utc) - timedelta(hours=2))

    result = await company_users._cx_mp_autoclose_if_stale_028q(
        db, uuid.uuid4(), SimpleNamespace(id=uuid.uuid4()), {}, "mesero", row,
    )

    assert result is row
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_shift_past_shift_max_hours_is_closed_with_cierre_automatico(monkeypatch):
    company_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(company_users, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_module_settings_026k", AsyncMock(return_value={"shift_max_hours": 12}))
    fresh_session = {"id": uuid.uuid4(), "status": "active"}
    create_session = AsyncMock(return_value=fresh_session)
    monkeypatch.setattr(company_users, "_cx_mp_create_session_019f", create_session)
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    row = _row(started_at=datetime.now(timezone.utc) - timedelta(hours=185))

    result = await company_users._cx_mp_autoclose_if_stale_028q(db, company_id, user, {"daily_goal": 0}, "mesero", row)

    db.execute.assert_awaited_once()
    statement, params = db.execute.await_args.args
    assert "closed_reason = 'cierre_automatico'" in str(statement)
    assert params["id"] == str(row["id"])
    db.commit.assert_awaited_once()
    create_session.assert_awaited_once_with(db, company_id, user, {"daily_goal": 0}, "mesero")
    assert result == fresh_session


@pytest.mark.asyncio
async def test_a_shift_on_break_past_max_hours_also_closes(monkeypatch):
    monkeypatch.setattr(company_users, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_module_settings_026k", AsyncMock(return_value={"shift_max_hours": 12}))
    monkeypatch.setattr(company_users, "_cx_mp_create_session_019f", AsyncMock(return_value={"id": uuid.uuid4()}))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    row = _row(status="break", started_at=datetime.now(timezone.utc) - timedelta(hours=20))

    await company_users._cx_mp_autoclose_if_stale_028q(db, uuid.uuid4(), SimpleNamespace(id=uuid.uuid4()), {}, "cocina", row)

    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_never_touches_a_stale_shift_in_a_company_without_waiter_ordering(monkeypatch):
    async def raise_not_enabled(db, company_id, code):
        raise HTTPException(status_code=403, detail="module_not_enabled")

    monkeypatch.setattr(company_users, "require_enabled_module", raise_not_enabled)
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    row = _row(started_at=datetime.now(timezone.utc) - timedelta(hours=500))

    result = await company_users._cx_mp_autoclose_if_stale_028q(
        db, uuid.uuid4(), SimpleNamespace(id=uuid.uuid4()), {}, "mesero", row,
    )

    assert result is row
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_finished_shift_is_never_reopened_or_touched(monkeypatch):
    monkeypatch.setattr(company_users, "require_enabled_module", AsyncMock())
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    row = _row(status="finished", started_at=datetime.now(timezone.utc) - timedelta(hours=500))

    result = await company_users._cx_mp_autoclose_if_stale_028q(
        db, uuid.uuid4(), SimpleNamespace(id=uuid.uuid4()), {}, "mesero", row,
    )

    assert result is row
    db.execute.assert_not_awaited()
