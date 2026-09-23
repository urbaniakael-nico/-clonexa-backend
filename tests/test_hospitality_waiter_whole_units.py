"""Fracciones solo donde aplican: inventory "Permite porciones"
(allows_portions, off by default).

- On (pollo): the mesero gets 1/4, 1/2, 3/4, 1, 2 with prices and the order
  deducts the fraction from stock.
- Off (carne, gaseosa, hamburguesa): no fraction buttons, whole units only,
  enforced on the server too.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import waiter_ordering


ENABLED = {"quantity_buttons_enabled": True, "quantity_buttons": ["1/4", "1/2", "3/4", "1", "2"]}

POLLO = {"id": "pollo", "name": "POLLO Asado", "price": 40000, "active": True, "allows_portions": True}
CARNE = {"id": "carne", "name": "CARNE Churrasco", "price": 29000, "active": True, "allows_portions": False}
GASEOSA = {"id": "gaseosa", "name": "GASEOSA Coca Cola", "price": 4500, "active": True}   # never set -> off
# An Admin V2 portion group where only the whole member was flagged.
ALITAS_6 = {"id": "alitas-6", "name": "ALITAS x6", "price": 18000, "active": True, "allows_portions": True}
ALITAS_12 = {"id": "alitas-12", "name": "ALITAS x12", "price": 32000, "active": True}
GROUP = {
    "alitas-6": {"group_key": "alitas", "group_label": "Alitas", "portion_label": "1", "position": 0},
    "alitas-12": {"group_key": "alitas", "group_label": "Alitas", "portion_label": "2", "position": 1},
}
INVENTORY = [POLLO, CARNE, GASEOSA, ALITAS_6, ALITAS_12]


def _patch(monkeypatch, settings=ENABLED):
    monkeypatch.setattr(waiter_ordering, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": [dict(p) for p in INVENTORY]}))
    monkeypatch.setattr(waiter_ordering, "_category_rows", AsyncMock(return_value={}))
    monkeypatch.setattr(waiter_ordering, "_portion_membership", AsyncMock(return_value=GROUP))
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value=settings))


def _mesero():
    return SimpleNamespace(id=uuid.uuid4(), full_name="Laura", role="mesero")


async def _menu(monkeypatch):
    _patch(monkeypatch)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))))
    menu = await waiter_ordering.waiter_ordering_menu(uuid.uuid4(), db=db, _user=_mesero())
    return {p["id"]: p for cat in menu["categories"] for p in cat["products"]}


async def _order(monkeypatch, items):
    _patch(monkeypatch)
    create_order = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(waiter_ordering, "create_hospitality_order", create_order)
    payload = waiter_ordering.WaiterOrderCreateIn(table="Mesa 5", items=[waiter_ordering.WaiterOrderItemIn(**i) for i in items])
    await waiter_ordering.create_waiter_order(uuid.uuid4(), payload, db=SimpleNamespace(), user=_mesero())
    return create_order.await_args.args[1].items


@pytest.mark.asyncio
async def test_only_products_that_allow_portions_get_fraction_buttons(monkeypatch):
    products = await _menu(monkeypatch)
    assert products["pollo"]["allows_portions"] is True
    assert [o["label"] for o in products["pollo"]["quantity_options"]] == ["1/4", "1/2", "3/4", "1", "2"]
    for product_id in ("carne", "gaseosa"):
        assert products[product_id]["allows_portions"] is False
        assert "quantity_options" not in products[product_id]


@pytest.mark.asyncio
async def test_a_portion_group_allows_portions_if_one_member_does(monkeypatch):
    products = await _menu(monkeypatch)
    assert products["alitas"]["allows_portions"] is True
    assert "quantity_options" in products["alitas"]


@pytest.mark.asyncio
async def test_a_product_with_portions_deducts_the_fraction(monkeypatch):
    items = await _order(monkeypatch, [{"inventory_item_id": "pollo", "fraction": "1/4"}])
    assert items[0].quantity == 0.25          # what create_hospitality_order deducts from stock
    assert items[0].line_total == 10000


@pytest.mark.asyncio
async def test_a_product_without_portions_is_sold_and_deducted_in_whole_units(monkeypatch):
    items = await _order(monkeypatch, [{"inventory_item_id": "gaseosa", "quantity": 3}, {"inventory_item_id": "carne", "quantity": 1}])
    assert [(i.inventory_item_id, i.quantity, i.unit_price) for i in items] == [("gaseosa", 3, 4500), ("carne", 1, 29000)]
    assert all(i.line_total is None for i in items)


@pytest.mark.asyncio
async def test_a_fraction_of_a_product_without_portions_is_rejected(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _order(monkeypatch, [{"inventory_item_id": "carne", "fraction": "1/2"}])
    assert exc.value.status_code == 422
    assert "no se vende por porciones" in exc.value.detail


@pytest.mark.asyncio
async def test_a_decimal_quantity_of_a_product_without_portions_is_rejected(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _order(monkeypatch, [{"inventory_item_id": "gaseosa", "quantity": 1.5}])
    assert exc.value.status_code == 422
    assert "unidades enteras" in exc.value.detail
