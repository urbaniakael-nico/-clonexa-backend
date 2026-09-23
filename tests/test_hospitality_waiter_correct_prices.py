"""PATCH /orders/{id}/correct used to rebuild each line with only
inventory_item_id/quantity: unit_price defaulted to 0, so every corrected
line was stored with subtotal $0 and the table would have been charged
nothing for it. It must price lines from the catalog exactly like a new
order -- through Hospitality's real _build_order_items."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import hospitality, waiter_ordering


CATALOG = [
    {"id": "carne", "name": "CARNE Asada", "price": 25000},
    {"id": "cerveza", "name": "CERVEZA Aguila", "price": 5000},
    {"id": "odd", "name": "CHORIZO Grande", "price": 12345, "allows_portions": True},
]


def _setup(monkeypatch, settings=None):
    order = {"id": "o1", "status": "pendiente", "items": [{"id": "line_1", "name": "Carne", "subtotal": 25000}], "metadata": {}}
    monkeypatch.setattr(waiter_ordering, "_lock_order_for_edit", AsyncMock(return_value=order))
    monkeypatch.setattr(waiter_ordering, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": [dict(p) for p in CATALOG]}))
    monkeypatch.setattr(
        waiter_ordering, "_category_rows",
        AsyncMock(return_value={"cerveza": {"key": "cerveza", "station": "bebidas", "requires_term": False}}),
    )
    monkeypatch.setattr(waiter_ordering, "_portion_membership", AsyncMock(return_value={}))
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value=settings or {}))
    monkeypatch.setattr(waiter_ordering, "_adjust_pending_order_inventory", AsyncMock())
    monkeypatch.setattr(waiter_ordering, "_fetch_order", AsyncMock(return_value={"id": "o1"}))
    # Real _build_order_items; only its per-line inventory lookup is faked.
    monkeypatch.setattr(hospitality, "_inventory_lookup", AsyncMock(return_value=None))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    return db


def _saved(db):
    _statement, params = db.execute.await_args.args
    return json.loads(params["items"]), params["total"]


def _user():
    return SimpleNamespace(id=uuid.uuid4(), full_name="Caja", role="caja")


@pytest.mark.asyncio
async def test_corrected_lines_keep_their_catalog_price(monkeypatch):
    db = _setup(monkeypatch)
    payload = waiter_ordering.CorrectOrderIn(items=[
        waiter_ordering.CorrectOrderItemIn(inventory_item_id="carne", quantity=2),
        waiter_ordering.CorrectOrderItemIn(inventory_item_id="cerveza", quantity=3),
    ], reason="agregaron cervezas")

    await waiter_ordering.correct_waiter_order(uuid.uuid4(), uuid.uuid4(), payload, db=db, user=_user())

    items, total = _saved(db)
    assert [(i["name"], i["unit_price"], i["subtotal"]) for i in items] == [
        ("CARNE Asada", 25000, 50000),
        ("CERVEZA Aguila", 5000, 15000),
    ]
    assert total == 65000
    assert all(i["subtotal"] > 0 for i in items)


@pytest.mark.asyncio
async def test_station_comes_from_the_category_not_from_the_client(monkeypatch):
    db = _setup(monkeypatch)
    payload = waiter_ordering.CorrectOrderIn(items=[
        waiter_ordering.CorrectOrderItemIn(inventory_item_id="cerveza", quantity=1, station="parrilla"),
    ])
    await waiter_ordering.correct_waiter_order(uuid.uuid4(), uuid.uuid4(), payload, db=db, user=_user())
    items, _ = _saved(db)
    assert items[0]["station"] == "bebidas"


@pytest.mark.asyncio
async def test_a_corrected_fraction_line_is_priced_like_on_creation(monkeypatch):
    db = _setup(monkeypatch, {"quantity_buttons_enabled": True, "quantity_buttons": ["1/2", "3/4", "1"]})
    payload = waiter_ordering.CorrectOrderIn(items=[
        waiter_ordering.CorrectOrderItemIn(inventory_item_id="odd", quantity=1, fraction="3/4"),
    ])
    await waiter_ordering.correct_waiter_order(uuid.uuid4(), uuid.uuid4(), payload, db=db, user=_user())
    items, total = _saved(db)
    assert items[0]["quantity"] == 0.75
    assert items[0]["subtotal"] == 9259
    assert items[0]["quantity_label"] == "3/4"
    assert total == 9259


@pytest.mark.asyncio
async def test_correcting_to_a_product_outside_the_catalog_is_rejected(monkeypatch):
    db = _setup(monkeypatch)
    payload = waiter_ordering.CorrectOrderIn(items=[
        waiter_ordering.CorrectOrderItemIn(inventory_item_id="ghost", quantity=1),
    ])
    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.correct_waiter_order(uuid.uuid4(), uuid.uuid4(), payload, db=db, user=_user())
    assert exc.value.status_code == 422
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_zero_quantity_lines_are_removed_not_priced(monkeypatch):
    db = _setup(monkeypatch)
    payload = waiter_ordering.CorrectOrderIn(items=[
        waiter_ordering.CorrectOrderItemIn(inventory_item_id="carne", quantity=0),
        waiter_ordering.CorrectOrderItemIn(inventory_item_id="cerveza", quantity=1),
    ])
    await waiter_ordering.correct_waiter_order(uuid.uuid4(), uuid.uuid4(), payload, db=db, user=_user())
    items, total = _saved(db)
    assert [i["name"] for i in items] == ["CERVEZA Aguila"]
    assert total == 5000
