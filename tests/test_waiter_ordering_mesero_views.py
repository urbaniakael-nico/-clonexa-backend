"""Fase 2: "ventas-hoy" and "mis-mesas" must only ever show the logged-in
mesero's own orders (never another waiter's, never another company's --
company scoping is the query's WHERE company_id, tenant auth already
guarantees the row is this company).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from app.api.v1.endpoints import waiter_ordering


def _user(daily_goal=100000):
    return SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Laura Mesera",
        role="mesero",
        settings_json={"mini_panel": {"daily_goal": daily_goal}},
    )


class FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


@pytest.mark.asyncio
async def test_ventas_hoy_computes_progress_against_own_daily_goal():
    company_id = uuid.uuid4()
    user = _user(daily_goal=50000)
    db = SimpleNamespace(execute=AsyncMock(return_value=FakeResult({"total": 25000, "orders_count": 3})))

    result = await waiter_ordering.waiter_sales_today(company_id, db=db, user=user)

    assert result["waiter_id"] == str(user.id)
    assert result["total_today"] == 25000
    assert result["orders_count"] == 3
    assert result["daily_goal"] == 50000
    assert result["goal_progress_percent"] == 50

    statement, params = db.execute.await_args.args
    assert "metadata->'waiter'->>'id' = :user_id" in str(statement)
    assert params["user_id"] == str(user.id)
    assert params["company_id"] == str(company_id)


@pytest.mark.asyncio
async def test_ventas_hoy_with_no_daily_goal_configured_reports_zero_progress():
    db = SimpleNamespace(execute=AsyncMock(return_value=FakeResult({"total": 25000, "orders_count": 1})))

    result = await waiter_ordering.waiter_sales_today(uuid.uuid4(), db=db, user=_user(daily_goal=0))

    assert result["daily_goal"] == 0
    assert result["goal_progress_percent"] == 0


@pytest.mark.asyncio
async def test_mis_mesas_excludes_orders_from_other_meseros(monkeypatch):
    company_id = uuid.uuid4()
    user = _user()
    other_waiter_id = str(uuid.uuid4())

    orders = {
        "orders": [
            {
                "table_key": "mesa-5", "table_number": "5", "total": 20000, "status": "pendiente",
                "metadata": {"waiter": {"id": str(user.id)}},
            },
            {
                "table_key": "mesa-7", "table_number": "7", "total": 15000, "status": "entregado",
                "metadata": {"waiter": {"id": other_waiter_id}},
            },
        ]
    }
    monkeypatch.setattr(waiter_ordering, "list_hospitality_orders", AsyncMock(return_value=orders))
    db = SimpleNamespace()

    result = await waiter_ordering.waiter_my_tables(company_id, db=db, user=user)

    tables = result["tables"]
    assert len(tables) == 1
    assert tables[0]["table_number"] == "5"
    assert tables[0]["status"] == "enviado_a_cocina"


@pytest.mark.asyncio
async def test_mis_mesas_marks_ready_to_carry_when_nothing_is_pending(monkeypatch):
    company_id = uuid.uuid4()
    user = _user()
    orders = {
        "orders": [
            {
                "table_key": "mesa-3", "table_number": "3", "total": 9000, "status": "entregado",
                "metadata": {"waiter": {"id": str(user.id)}},
            },
        ]
    }
    monkeypatch.setattr(waiter_ordering, "list_hospitality_orders", AsyncMock(return_value=orders))
    db = SimpleNamespace()

    result = await waiter_ordering.waiter_my_tables(company_id, db=db, user=user)

    assert result["tables"][0]["status"] == "listo_para_llevar"
