"""Mesero menu art: the menu_emojis switch reaches the panel (off by
default), and a photo uploaded for any portion of an Admin V2 portion group
shows on the group card (which has no inventory id of its own)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from app.api.v1.endpoints import waiter_ordering


INVENTORY = [
    {"id": "pollo-1", "name": "POLLO Entero", "price": 40000, "active": True},
    {"id": "pollo-12", "name": "POLLO 1/2", "price": 19000, "active": True},
    {"id": "gaseosa", "name": "GASEOSA Coca", "price": 4000, "active": True},
]
PORTIONS = {
    "pollo-1": {"group_key": "pollo", "group_label": "Pollo", "portion_label": "Entero", "position": 0},
    "pollo-12": {"group_key": "pollo", "group_label": "Pollo", "portion_label": "1/2", "position": 1},
}


async def _menu(monkeypatch, settings, with_image=()):
    monkeypatch.setattr(waiter_ordering, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": [dict(p) for p in INVENTORY]}))
    monkeypatch.setattr(waiter_ordering, "_category_rows", AsyncMock(return_value={}))
    monkeypatch.setattr(waiter_ordering, "_portion_membership", AsyncMock(return_value=PORTIONS))
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value=settings))
    rows = [{"inventory_item_id": item_id} for item_id in with_image]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))))
    menu = await waiter_ordering.waiter_ordering_menu(uuid.uuid4(), db=db, _user=SimpleNamespace(id=uuid.uuid4()))
    return menu, {p["id"]: p for cat in menu["categories"] for p in cat["products"]}


@pytest.mark.asyncio
async def test_menu_emojis_are_off_by_default_and_on_with_the_switch(monkeypatch):
    menu, _ = await _menu(monkeypatch, {})
    assert menu["menu_emojis"] is False
    menu, _ = await _menu(monkeypatch, {"menu_emojis": True})
    assert menu["menu_emojis"] is True


@pytest.mark.asyncio
async def test_a_portion_photo_shows_on_its_group_card(monkeypatch):
    _, products = await _menu(monkeypatch, {}, with_image=["pollo-12"])
    group = products["pollo"]
    assert group["has_image"] is True
    assert group["image_item_id"] == "pollo-12"
    assert products["gaseosa"]["has_image"] is False


@pytest.mark.asyncio
async def test_a_group_without_any_photo_has_none(monkeypatch):
    _, products = await _menu(monkeypatch, {})
    assert products["pollo"]["has_image"] is False
    assert "image_item_id" not in products["pollo"]
