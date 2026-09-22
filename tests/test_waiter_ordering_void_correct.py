"""Fase 2: anular/corregir un pedido enviado.

The safety property under test is that stock is only ever adjusted once per
void/correct: _lock_order_for_edit's SELECT ... FOR UPDATE is what a second,
concurrent call would block on in real Postgres, so here we pin the logic
that runs *after* that lock is held -- status is checked against the locked
row, not a stale read, and a terminal order short-circuits before touching
_adjust_pending_order_inventory at all.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import waiter_ordering


def _user(role="mesero"):
    return SimpleNamespace(id=uuid.uuid4(), full_name="Laura Mesera", role=role)


def _order(status="pendiente", items=None, metadata=None):
    return {
        "id": str(uuid.uuid4()),
        "status": status,
        "items": items if items is not None else [{"id": "line_1", "name": "Carne", "subtotal": 10000}],
        "metadata": metadata or {},
    }


@pytest.mark.asyncio
async def test_void_returns_stock_exactly_once_and_records_audit_metadata(monkeypatch):
    company_id = uuid.uuid4()
    order_id = uuid.uuid4()
    order = _order()
    user = _user()

    monkeypatch.setattr(waiter_ordering, "_lock_order_for_edit", AsyncMock(return_value=order))
    adjust = AsyncMock()
    monkeypatch.setattr(waiter_ordering, "_adjust_pending_order_inventory", adjust)
    fetched = {**order, "status": "cancelado", "items": []}
    monkeypatch.setattr(waiter_ordering, "_fetch_order", AsyncMock(return_value=fetched))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    result = await waiter_ordering.void_waiter_order(
        company_id, order_id, waiter_ordering.VoidOrderIn(reason="cliente se fue"), db=db, user=user,
    )

    adjust.assert_awaited_once_with(db, company_id, order, [])
    db.execute.assert_awaited_once()
    _statement, params = db.execute.await_args.args
    import json
    metadata = json.loads(params["metadata"])
    assert metadata["voided_by"]["by"]["id"] == str(user.id)
    assert metadata["voided_by"]["by"]["role"] == "mesero"
    assert metadata["voided_by"]["reason"] == "cliente se fue"
    assert result["order"] == fetched


@pytest.mark.asyncio
async def test_void_blocked_once_table_is_charged(monkeypatch):
    company_id = uuid.uuid4()
    order_id = uuid.uuid4()
    order = _order(status="cerrado")
    monkeypatch.setattr(waiter_ordering, "_lock_order_for_edit", AsyncMock(return_value=order))
    adjust = AsyncMock()
    monkeypatch.setattr(waiter_ordering, "_adjust_pending_order_inventory", adjust)
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.void_waiter_order(
            company_id, order_id, waiter_ordering.VoidOrderIn(), db=db, user=_user(),
        )

    assert exc.value.status_code == 409
    adjust.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_void_on_an_already_cancelled_order_is_a_noop_second_time(monkeypatch):
    """The row lock means a second void call always observes the terminal
    state the first one left -- this is what prevents a double stock return."""
    company_id = uuid.uuid4()
    order_id = uuid.uuid4()
    order = _order(status="cancelado", items=[])
    monkeypatch.setattr(waiter_ordering, "_lock_order_for_edit", AsyncMock(return_value=order))
    adjust = AsyncMock()
    monkeypatch.setattr(waiter_ordering, "_adjust_pending_order_inventory", adjust)
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    result = await waiter_ordering.void_waiter_order(
        company_id, order_id, waiter_ordering.VoidOrderIn(), db=db, user=_user(),
    )

    adjust.assert_not_awaited()
    db.execute.assert_not_awaited()
    assert result["already_voided"] is True


@pytest.mark.asyncio
async def test_void_404s_for_an_unknown_order(monkeypatch):
    monkeypatch.setattr(waiter_ordering, "_lock_order_for_edit", AsyncMock(return_value=None))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.void_waiter_order(
            uuid.uuid4(), uuid.uuid4(), waiter_ordering.VoidOrderIn(), db=db, user=_user(),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_correct_adjusts_inventory_by_the_delta_and_logs_the_diff(monkeypatch):
    company_id = uuid.uuid4()
    order_id = uuid.uuid4()
    order = _order()
    user = _user(role="caja")

    monkeypatch.setattr(waiter_ordering, "_lock_order_for_edit", AsyncMock(return_value=order))
    new_items = [{"id": "line_2", "name": "Papas", "subtotal": 4000}]
    monkeypatch.setattr(waiter_ordering, "_build_order_items", AsyncMock(return_value=new_items))
    adjust = AsyncMock()
    monkeypatch.setattr(waiter_ordering, "_adjust_pending_order_inventory", adjust)
    fetched = {**order, "items": new_items}
    monkeypatch.setattr(waiter_ordering, "_fetch_order", AsyncMock(return_value=fetched))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    payload = waiter_ordering.CorrectOrderIn(
        items=[waiter_ordering.CorrectOrderItemIn(inventory_item_id="inv-2", quantity=1)],
        reason="cliente cambio de plato",
    )
    result = await waiter_ordering.correct_waiter_order(company_id, order_id, payload, db=db, user=user)

    adjust.assert_awaited_once_with(db, company_id, order, new_items)
    _statement, params = db.execute.await_args.args
    assert params["total"] == 4000
    import json
    metadata = json.loads(params["metadata"])
    assert metadata["corrections"][-1]["by"]["role"] == "caja"
    assert metadata["corrections"][-1]["diff"]["after"] == new_items
    assert result["order"] == fetched


@pytest.mark.asyncio
async def test_correct_blocked_once_table_is_charged(monkeypatch):
    order = _order(status="cerrado")
    monkeypatch.setattr(waiter_ordering, "_lock_order_for_edit", AsyncMock(return_value=order))
    adjust = AsyncMock()
    monkeypatch.setattr(waiter_ordering, "_adjust_pending_order_inventory", adjust)
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.correct_waiter_order(
            uuid.uuid4(), uuid.uuid4(), waiter_ordering.CorrectOrderIn(), db=db, user=_user(),
        )
    assert exc.value.status_code == 409
    adjust.assert_not_awaited()


@pytest.mark.asyncio
async def test_correct_blocked_on_an_already_cancelled_order(monkeypatch):
    order = _order(status="cancelado")
    monkeypatch.setattr(waiter_ordering, "_lock_order_for_edit", AsyncMock(return_value=order))
    adjust = AsyncMock()
    monkeypatch.setattr(waiter_ordering, "_adjust_pending_order_inventory", adjust)
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.correct_waiter_order(
            uuid.uuid4(), uuid.uuid4(), waiter_ordering.CorrectOrderIn(), db=db, user=_user(),
        )
    assert exc.value.status_code == 409
    adjust.assert_not_awaited()
