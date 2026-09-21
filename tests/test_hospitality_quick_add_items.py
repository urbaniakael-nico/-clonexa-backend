import json
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import hospitality


class MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


def _order(status="entregado", inventory_deducted=True, archived_at=None):
    return {
        "id": str(uuid.uuid4()),
        "order_number": "HSP-1",
        "table_number": "Mesa 3",
        "status": status,
        "inventory_deducted": inventory_deducted,
        "archived_at": archived_at,
        "total": 10000,
        "items": [{"inventory_item_id": "aguila", "name": "CERVEZA Aguila", "quantity": 2, "unit_price": 5000, "subtotal": 10000}],
        "people": [{"id": "p1", "name": "Juan", "total": 10000,
                    "items": [{"inventory_item_id": "aguila", "name": "CERVEZA Aguila", "quantity": 2, "unit_price": 5000, "subtotal": 10000}]}],
    }


POKER = {"inventory_item_id": "poker", "name": "CERVEZA Poker", "quantity": 3, "unit_price": 4000, "subtotal": 12000}


def _setup(monkeypatch, order):
    executed = []

    async def execute(sql, params=None):
        executed.append((str(sql), params or {}))
        return MappingResult(order)

    db = AsyncMock()
    db.execute.side_effect = execute
    deduct = AsyncMock()
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_payload", lambda row: dict(row))
    monkeypatch.setattr(hospitality, "_build_order_items", AsyncMock(return_value=[dict(POKER)]))
    monkeypatch.setattr(hospitality, "_deduct_inventory", deduct)
    monkeypatch.setattr(hospitality, "_fetch_order", AsyncMock(return_value={"id": order["id"]}))
    return db, executed, deduct


def _payload():
    return hospitality.HospitalityBarAccountItemsIn(items=[{"inventory_item_id": "poker", "name": "CERVEZA Poker", "quantity": 3}])


@pytest.mark.asyncio
async def test_quick_add_appends_and_keeps_existing_items(monkeypatch):
    order = _order()
    db, executed, deduct = _setup(monkeypatch, order)

    await hospitality.add_hospitality_order_items(uuid.uuid4(), uuid.UUID(order["id"]), _payload(), db)

    assert "FOR UPDATE" in executed[0][0]
    update = next(params for sql, params in executed if "UPDATE hospitality_orders" in sql)
    names = {item["name"] for item in json.loads(update["items"])}
    assert names == {"CERVEZA Aguila", "CERVEZA Poker"}
    assert update["total"] == 22000
    people = json.loads(update["people"])
    assert people[0]["name"] == "Juan" and people[0]["total"] == 10000
    assert people[-1]["name"] == hospitality.QUICK_ADD_PERSON_NAME and people[-1]["total"] == 12000
    deducted_items = deduct.await_args.args[2]["items"]
    assert [item["name"] for item in deducted_items] == ["CERVEZA Poker"]
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_quick_add_twice_merges_into_same_barra_person(monkeypatch):
    order = _order()
    order["people"].append({"id": hospitality.QUICK_ADD_PERSON_ID, "name": hospitality.QUICK_ADD_PERSON_NAME,
                            "total": 12000, "items": [dict(POKER)]})
    db, executed, _ = _setup(monkeypatch, order)

    await hospitality.add_hospitality_order_items(uuid.uuid4(), uuid.UUID(order["id"]), _payload(), db)

    update = next(params for sql, params in executed if "UPDATE hospitality_orders" in sql)
    people = json.loads(update["people"])
    barra = [p for p in people if p["id"] == hospitality.QUICK_ADD_PERSON_ID]
    assert len(barra) == 1 and barra[0]["total"] == 24000


@pytest.mark.asyncio
async def test_quick_add_defers_stock_when_order_not_yet_deducted(monkeypatch):
    order = _order(status="alistando", inventory_deducted=False)
    db, _, deduct = _setup(monkeypatch, order)

    await hospitality.add_hospitality_order_items(uuid.uuid4(), uuid.UUID(order["id"]), _payload(), db)

    deduct.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,archived", [("cerrado", None), ("cancelado", None), ("entregado", "2026-09-20T08:16:31Z")])
async def test_quick_add_rejects_closed_tables(monkeypatch, status, archived):
    order = _order(status=status, archived_at=archived)
    db, executed, deduct = _setup(monkeypatch, order)

    with pytest.raises(HTTPException) as exc:
        await hospitality.add_hospitality_order_items(uuid.uuid4(), uuid.UUID(order["id"]), _payload(), db)

    assert exc.value.status_code == 409
    assert not any("UPDATE hospitality_orders" in sql for sql, _ in executed)
    deduct.assert_not_awaited()
