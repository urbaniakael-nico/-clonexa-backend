"""Order creation from the mesero app must resolve price/name from the
server's own catalog (never trust the client for money), stamp the
authenticated user as the waiter (never trust the client for identity), and
resolve each item's kitchen station from the admin-configured category -- all
by calling straight into hospitality.create_hospitality_order, not a copy of
its inventory-deduction logic.

Marking an item ready is scoped to that single line inside the order's items
array and does not touch the order's own pendiente/alistando/entregado status.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import waiter_ordering


def _user(full_name="Laura Mesera"):
    return SimpleNamespace(id=uuid.uuid4(), full_name=full_name, role="mesero")


@pytest.mark.asyncio
async def test_create_waiter_order_resolves_price_station_and_waiter_identity(monkeypatch):
    company_id = uuid.uuid4()
    user = _user()

    monkeypatch.setattr(waiter_ordering, "ensure_waiter_ordering_storage", AsyncMock())
    monkeypatch.setattr(
        waiter_ordering, "hospitality_inventory_lite",
        AsyncMock(return_value={"inventory": [{"id": "inv-1", "name": "CERVEZA Aguila", "price": 5000}]}),
    )
    monkeypatch.setattr(
        waiter_ordering, "_category_rows",
        AsyncMock(return_value={"cerveza": {"key": "cerveza", "station": "bebidas", "quick_notes": [], "requires_term": False}}),
    )
    monkeypatch.setattr(waiter_ordering, "_portion_membership", AsyncMock(return_value={}))
    create_order = AsyncMock(return_value={"ok": True, "order": {"id": "order-1"}})
    monkeypatch.setattr(waiter_ordering, "create_hospitality_order", create_order)

    payload = waiter_ordering.WaiterOrderCreateIn(
        table="Mesa 5",
        items=[waiter_ordering.WaiterOrderItemIn(inventory_item_id="inv-1", quantity=2, observations="sin hielo")],
    )

    result = await waiter_ordering.create_waiter_order(company_id, payload, db=SimpleNamespace(), user=user)

    assert result["order"]["id"] == "order-1"
    create_order.assert_awaited_once()
    called_company_id, hospitality_payload, _db = create_order.await_args.args
    assert called_company_id == company_id
    # Client never sends unit_price/name for a real product; the server fills
    # them in from its own catalog.
    item = hospitality_payload.items[0]
    assert item.name == "CERVEZA Aguila"
    assert item.unit_price == 5000
    assert item.station == "bebidas"
    assert item.observations == "sin hielo"
    # The authenticated mesero, not anything the client could claim to be.
    assert hospitality_payload.waiter_id == str(user.id)
    assert hospitality_payload.waiter_name == "Laura Mesera"


@pytest.mark.asyncio
async def test_create_waiter_order_rejects_a_product_outside_the_catalog(monkeypatch):
    company_id = uuid.uuid4()
    monkeypatch.setattr(waiter_ordering, "ensure_waiter_ordering_storage", AsyncMock())
    monkeypatch.setattr(waiter_ordering, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": []}))
    monkeypatch.setattr(waiter_ordering, "_category_rows", AsyncMock(return_value={}))
    monkeypatch.setattr(waiter_ordering, "_portion_membership", AsyncMock(return_value={}))

    payload = waiter_ordering.WaiterOrderCreateIn(
        table="Mesa 5",
        items=[waiter_ordering.WaiterOrderItemIn(inventory_item_id="ghost-item", quantity=1)],
    )
    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.create_waiter_order(company_id, payload, db=SimpleNamespace(), user=_user())
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# Marking a single item ready
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_item_ready_only_flips_that_one_line(monkeypatch):
    company_id = uuid.uuid4()
    order_id = uuid.uuid4()
    order = {
        "id": str(order_id),
        "items": [
            {"id": "line_1", "name": "Carne", "ready": False},
            {"id": "line_2", "name": "Papas", "ready": False},
        ],
    }
    fetch_order = AsyncMock(side_effect=[order, {**order, "items": [{"id": "line_1", "ready": True}, {"id": "line_2", "ready": False}]}])
    monkeypatch.setattr(waiter_ordering, "_fetch_order", fetch_order)
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    result = await waiter_ordering.mark_waiter_order_item_ready(company_id, order_id, "line_1", db=db, _user=_user())

    update_call = db.execute.await_args
    statement = str(update_call.args[0])
    assert "UPDATE hospitality_orders SET items" in statement
    import json
    sent_items = json.loads(update_call.args[1]["items"])
    assert sent_items[0]["ready"] is True
    assert sent_items[0]["ready_at"] is not None
    assert sent_items[1]["ready"] is False
    assert result["order"]["items"][0]["ready"] is True


@pytest.mark.asyncio
async def test_mark_item_ready_404s_for_an_unknown_line(monkeypatch):
    company_id = uuid.uuid4()
    order_id = uuid.uuid4()
    monkeypatch.setattr(waiter_ordering, "_fetch_order", AsyncMock(return_value={"id": str(order_id), "items": [{"id": "line_1"}]}))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.mark_waiter_order_item_ready(company_id, order_id, "line_missing", db=db, _user=_user())
    assert exc.value.status_code == 404
