"""Cantidad por botones (1/4, 1/2, 3/4, 1, 2) in the mesero panel.

Price rule, resolved on the server (the client never sends money):
- product in an Admin V2 portion group with that exact portion -> that
  portion's own inventory item and configured price;
- otherwise -> fraction of the base product's price, rounded to the peso.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import hospitality, waiter_ordering


ENABLED = {"quantity_buttons_enabled": True, "quantity_buttons": ["1/4", "1/2", "3/4", "1", "2"]}

CARNE = {"id": "carne", "name": "CARNE Asada", "price": 25000, "active": True}
ODD = {"id": "odd", "name": "CHORIZO Grande", "price": 12345, "active": True}
# Admin V2 portion group "Pollo": 1/2 has its own configured price (cheaper
# than half of the whole), 1/4 is NOT configured.
POLLO_ENTERO = {"id": "pollo-1", "name": "POLLO Entero", "price": 40000, "active": True}
POLLO_MEDIO = {"id": "pollo-12", "name": "POLLO 1/2", "price": 19000, "active": True}
PORTIONS = {
    "pollo-1": {"group_key": "pollo", "group_label": "Pollo", "portion_label": "Entero", "position": 0},
    "pollo-12": {"group_key": "pollo", "group_label": "Pollo", "portion_label": "1/2", "position": 1},
}
# A group with no whole ("1") member can only sell what it has configured.
COSTILLA_MEDIA = {"id": "cost-12", "name": "COSTILLA 1/2", "price": 30000, "active": True}
COSTILLA_PORTIONS = {"cost-12": {"group_key": "costilla", "group_label": "Costilla", "portion_label": "1/2", "position": 0}}

INVENTORY = [CARNE, ODD, POLLO_ENTERO, POLLO_MEDIO, COSTILLA_MEDIA]
BY_ID = {p["id"]: p for p in INVENTORY}
ALL_PORTIONS = {**PORTIONS, **COSTILLA_PORTIONS}


def _resolve(product_id, label):
    return waiter_ordering._resolve_fraction(BY_ID[product_id], label, BY_ID, ALL_PORTIONS)


@pytest.mark.parametrize(
    "label, quantity, total",
    [("1/4", 0.25, 6250), ("1/2", 0.5, 12500), ("3/4", 0.75, 18750), ("1", 1.0, 25000), ("2", 2.0, 50000)],
)
def test_fraction_of_an_ungrouped_product_price(label, quantity, total):
    resolved = _resolve("carne", label)
    assert resolved["product"]["id"] == "carne"
    assert resolved["quantity"] == quantity
    assert resolved["line_total"] == total


def test_fraction_price_is_rounded_to_the_currency_unit():
    assert _resolve("odd", "1/4")["line_total"] == 3086   # 3086.25
    assert _resolve("odd", "1/2")["line_total"] == 6173   # 6172.5 -> half up
    assert _resolve("odd", "3/4")["line_total"] == 9259   # 9258.75


def test_configured_portion_price_wins_over_the_fraction_math():
    resolved = _resolve("pollo-1", "1/2")
    assert resolved["product"]["id"] == "pollo-12"   # its own inventory item
    assert resolved["line_total"] == 19000            # not 40000 / 2
    assert resolved["quantity"] == 1.0


def test_a_portion_not_configured_falls_back_to_the_fraction_of_the_whole():
    resolved = _resolve("pollo-12", "1/4")   # any member resolves the group
    assert resolved["product"]["id"] == "pollo-1"
    assert resolved["quantity"] == 0.25
    assert resolved["line_total"] == 10000


def test_whole_and_double_of_a_group_use_the_entero_member():
    assert _resolve("pollo-12", "1")["product"]["id"] == "pollo-1"
    assert _resolve("pollo-12", "1")["line_total"] == 40000
    assert _resolve("pollo-12", "2")["line_total"] == 80000


def test_a_group_with_no_whole_member_cannot_price_a_missing_fraction():
    assert _resolve("cost-12", "1/2")["line_total"] == 30000
    assert _resolve("cost-12", "1/4") is None


def test_portion_labels_are_read_as_fractions_only_when_they_are_one():
    assert waiter_ordering._portion_label_fraction("1/4 de pollo") == waiter_ordering.Decimal("0.25")
    assert waiter_ordering._portion_label_fraction("Medio") == waiter_ordering.Decimal("0.5")
    assert waiter_ordering._portion_label_fraction("Entero") == waiter_ordering.Decimal("1")
    assert waiter_ordering._portion_label_fraction("Familiar") is None


def test_buttons_are_off_by_default_and_configurable_per_company():
    assert waiter_ordering._quantity_buttons_config({}) == []
    assert waiter_ordering._quantity_buttons_config({"quantity_buttons_enabled": True}) == ["1/4", "1/2", "3/4", "1", "2"]
    assert waiter_ordering._quantity_buttons_config(
        {"quantity_buttons_enabled": True, "quantity_buttons": ["1/2", "1", "basura", "1/0"]}
    ) == ["1/2", "1"]


# ---------------------------------------------------------------------------
# Through the real endpoints
# ---------------------------------------------------------------------------

def _patch_catalog(monkeypatch, settings, portions=ALL_PORTIONS):
    monkeypatch.setattr(waiter_ordering, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": [dict(p) for p in INVENTORY]}))
    monkeypatch.setattr(waiter_ordering, "_category_rows", AsyncMock(return_value={}))
    monkeypatch.setattr(waiter_ordering, "_portion_membership", AsyncMock(return_value=portions))
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value=settings))


def _mesero():
    return SimpleNamespace(id=uuid.uuid4(), full_name="Laura", role="mesero")


@pytest.mark.asyncio
async def test_menu_shows_each_button_price_before_adding(monkeypatch):
    _patch_catalog(monkeypatch, ENABLED)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))))

    menu = await waiter_ordering.waiter_ordering_menu(uuid.uuid4(), db=db, _user=_mesero())

    assert menu["quantity_buttons"] == ["1/4", "1/2", "3/4", "1", "2"]
    products = {p["id"]: p for cat in menu["categories"] for p in cat["products"]}
    assert [o["price"] for o in products["carne"]["quantity_options"]] == [6250, 12500, 18750, 25000, 50000]
    pollo = products["pollo"]
    assert pollo["quantity_ref_id"] in {"pollo-1", "pollo-12"}
    assert {o["label"]: o["price"] for o in pollo["quantity_options"]}["1/2"] == 19000
    costilla = {o["label"]: o for o in products["costilla"]["quantity_options"]}
    assert costilla["1/4"]["available"] is False


@pytest.mark.asyncio
async def test_menu_has_no_buttons_when_the_company_switch_is_off(monkeypatch):
    _patch_catalog(monkeypatch, {})
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))))

    menu = await waiter_ordering.waiter_ordering_menu(uuid.uuid4(), db=db, _user=_mesero())

    assert menu["quantity_buttons"] == []
    assert all("quantity_options" not in p for cat in menu["categories"] for p in cat["products"])


async def _order(monkeypatch, settings, items):
    _patch_catalog(monkeypatch, settings)
    create_order = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(waiter_ordering, "create_hospitality_order", create_order)
    payload = waiter_ordering.WaiterOrderCreateIn(
        table="Mesa 5", items=[waiter_ordering.WaiterOrderItemIn(**item) for item in items],
    )
    await waiter_ordering.create_waiter_order(uuid.uuid4(), payload, db=SimpleNamespace(), user=_mesero())
    return create_order.await_args.args[1].items


@pytest.mark.asyncio
async def test_order_with_a_fraction_charges_the_rounded_fraction(monkeypatch):
    items = await _order(monkeypatch, ENABLED, [{"inventory_item_id": "odd", "fraction": "3/4"}])
    assert items[0].inventory_item_id == "odd"
    assert items[0].quantity == 0.75          # stock: 3/4 of the product
    assert items[0].line_total == 9259
    assert items[0].quantity_label == "3/4"


@pytest.mark.asyncio
async def test_order_with_a_configured_portion_uses_its_own_item_and_price(monkeypatch):
    items = await _order(monkeypatch, ENABLED, [{"inventory_item_id": "pollo-1", "fraction": "1/2"}])
    assert items[0].inventory_item_id == "pollo-12"
    assert items[0].name == "POLLO 1/2"
    assert items[0].quantity == 1
    assert items[0].line_total == 19000


@pytest.mark.asyncio
async def test_order_ignores_any_client_price(monkeypatch):
    items = await _order(monkeypatch, ENABLED, [{"inventory_item_id": "carne", "fraction": "1/2"}])
    assert items[0].line_total == 12500


@pytest.mark.asyncio
async def test_order_rejects_a_fraction_the_company_did_not_enable(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _order(monkeypatch, {"quantity_buttons_enabled": True, "quantity_buttons": ["1/2", "1"]},
                     [{"inventory_item_id": "carne", "fraction": "1/4"}])
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_order_rejects_fractions_when_the_switch_is_off(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _order(monkeypatch, {}, [{"inventory_item_id": "carne", "fraction": "1/2"}])
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_order_rejects_a_fraction_that_has_no_price(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _order(monkeypatch, ENABLED, [{"inventory_item_id": "cost-12", "fraction": "1/4"}])
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_order_without_fraction_is_unchanged(monkeypatch):
    items = await _order(monkeypatch, ENABLED, [{"inventory_item_id": "carne", "quantity": 3}])
    assert items[0].quantity == 3
    assert items[0].unit_price == 25000
    assert items[0].line_total is None


# ---------------------------------------------------------------------------
# hospitality._build_order_items honours the fixed line total
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_order_items_uses_line_total_and_keeps_the_label(monkeypatch):
    monkeypatch.setattr(hospitality, "_inventory_lookup", AsyncMock(return_value=None))
    rows = await hospitality._build_order_items(
        SimpleNamespace(), uuid.uuid4(),
        [hospitality.HospitalityOrderItemIn(inventory_item_id="odd", name="CHORIZO", quantity=0.75,
                                            unit_price=12345, line_total=9259, quantity_label="3/4")],
    )
    assert rows[0]["subtotal"] == 9259
    assert rows[0]["quantity"] == 0.75
    assert rows[0]["quantity_label"] == "3/4"


@pytest.mark.asyncio
async def test_build_order_items_without_the_new_fields_is_byte_for_byte_as_before(monkeypatch):
    monkeypatch.setattr(hospitality, "_inventory_lookup", AsyncMock(return_value=None))
    rows = await hospitality._build_order_items(
        SimpleNamespace(), uuid.uuid4(),
        [hospitality.HospitalityOrderItemIn(inventory_item_id="x", name="Cerveza", quantity=2, unit_price=5000)],
    )
    assert rows[0]["subtotal"] == 10000
    assert "quantity_label" not in rows[0]
