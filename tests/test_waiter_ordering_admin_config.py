"""Fase 2 Admin V2: setting a mesero's own daily sales goal (used by the
home screen's goal-vs-today's-sale progress bar). Mirrors the existing
cocina-users/{id}/stations admin endpoint's shape.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import waiter_ordering


class FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


@pytest.mark.asyncio
async def test_set_mesero_daily_goal_stores_it_under_mini_panel_settings():
    company_id = uuid.uuid4()
    user_id = uuid.uuid4()
    execute_calls = []

    async def execute(stmt, params=None):
        execute_calls.append((str(stmt), params))
        if "SELECT id, company_id, settings_json" in str(stmt):
            return FakeResult({"id": user_id, "company_id": company_id, "settings_json": {"mini_panel": {"type": "mesero"}}})
        return None

    db = SimpleNamespace(execute=execute, commit=AsyncMock())

    result = await waiter_ordering.set_mesero_daily_goal(
        company_id, user_id, waiter_ordering.MeseroDailyGoalIn(daily_goal=150000), db=db, _admin=None,
    )

    assert result["daily_goal"] == 150000
    update_call = next(c for c in execute_calls if "UPDATE company_users" in c[0])
    import json
    saved = json.loads(update_call[1]["settings"])
    assert saved["mini_panel"]["daily_goal"] == 150000


@pytest.mark.asyncio
async def test_set_mesero_daily_goal_404s_for_an_unknown_user():
    async def execute(stmt, params=None):
        return FakeResult(None)

    db = SimpleNamespace(execute=execute, commit=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.set_mesero_daily_goal(
            uuid.uuid4(), uuid.uuid4(), waiter_ordering.MeseroDailyGoalIn(daily_goal=1000), db=db, _admin=None,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_set_mesero_daily_goal_rejects_a_negative_value():
    with pytest.raises(Exception):
        waiter_ordering.MeseroDailyGoalIn(daily_goal=-500)
