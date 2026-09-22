"""Fase 2: portions are pure grouping/labeling over independent inventory
items (each portion keeps its own inventory_item_id/stock/price -- see
migrations/versions/021d_waiter_ordering_p2.py's hospitality_product_portions
table). These tests cover the admin-facing group CRUD: correct grouping on
read, and the 409 when a product is added to two groups at once (the
UNIQUE(company_id, inventory_item_id) constraint at the DB level).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import waiter_ordering


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_list_portions_groups_members_under_their_product_group_key():
    company_id = uuid.uuid4()
    rows = [
        {"product_group_key": "pollo_asado", "group_label": "Pollo Asado", "inventory_item_id": uuid.uuid4(), "portion_label": "1/4", "position": 0},
        {"product_group_key": "pollo_asado", "group_label": "Pollo Asado", "inventory_item_id": uuid.uuid4(), "portion_label": "Entero", "position": 1},
        {"product_group_key": "costilla", "group_label": "Costilla BBQ", "inventory_item_id": uuid.uuid4(), "portion_label": "1/2", "position": 0},
    ]
    db = SimpleNamespace(execute=AsyncMock(return_value=FakeResult(rows)))

    result = await waiter_ordering.list_waiter_ordering_portions(company_id, db=db, _admin=None)

    groups = {g["group_key"]: g for g in result["groups"]}
    assert len(groups) == 2
    assert len(groups["pollo_asado"]["members"]) == 2
    assert [m["portion_label"] for m in groups["pollo_asado"]["members"]] == ["1/4", "Entero"]
    assert len(groups["costilla"]["members"]) == 1


@pytest.mark.asyncio
async def test_upsert_portion_group_replaces_the_whole_group_atomically():
    company_id = uuid.uuid4()
    calls = []

    async def execute(stmt, params=None):
        calls.append((str(stmt), params))
        return SimpleNamespace()

    db = SimpleNamespace(execute=execute, commit=AsyncMock(), rollback=AsyncMock())

    payload = waiter_ordering.PortionGroupUpsertIn(
        group_label="Pollo Asado",
        members=[
            waiter_ordering.PortionMemberIn(inventory_item_id=str(uuid.uuid4()), portion_label="1/4", position=0),
            waiter_ordering.PortionMemberIn(inventory_item_id=str(uuid.uuid4()), portion_label="Entero", position=1),
        ],
    )

    result = await waiter_ordering.upsert_waiter_ordering_portion_group(
        company_id, "Pollo Asado", payload, db=db, _admin=None,
    )

    assert result["ok"] is True
    delete_calls = [c for c in calls if "DELETE FROM hospitality_product_portions" in c[0]]
    insert_calls = [c for c in calls if "INSERT INTO hospitality_product_portions" in c[0]]
    assert len(delete_calls) == 1
    assert len(insert_calls) == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_portion_group_rejects_a_product_already_in_another_group():
    company_id = uuid.uuid4()
    item_already_grouped = str(uuid.uuid4())

    async def execute(stmt, params=None):
        text = str(stmt)
        if "INSERT INTO hospitality_product_portions" in text:
            raise Exception("duplicate key value violates unique constraint")
        return SimpleNamespace()

    db = SimpleNamespace(execute=execute, commit=AsyncMock(), rollback=AsyncMock())

    payload = waiter_ordering.PortionGroupUpsertIn(
        group_label="Costilla BBQ",
        members=[waiter_ordering.PortionMemberIn(inventory_item_id=item_already_grouped, portion_label="1/2", position=0)],
    )

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.upsert_waiter_ordering_portion_group(company_id, "costilla", payload, db=db, _admin=None)

    assert exc.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_portion_group_with_empty_members_ungroups_everything():
    company_id = uuid.uuid4()
    calls = []

    async def execute(stmt, params=None):
        calls.append(str(stmt))
        return SimpleNamespace()

    db = SimpleNamespace(execute=execute, commit=AsyncMock(), rollback=AsyncMock())

    payload = waiter_ordering.PortionGroupUpsertIn(group_label="Pollo Asado", members=[])
    result = await waiter_ordering.upsert_waiter_ordering_portion_group(company_id, "pollo_asado", payload, db=db, _admin=None)

    assert result["ok"] is True
    assert not any("INSERT INTO hospitality_product_portions" in c for c in calls)
    assert any("DELETE FROM hospitality_product_portions" in c for c in calls)


def test_merge_portions_into_products_groups_siblings_and_leaves_singles_untouched():
    pollo_quarter_id = str(uuid.uuid4())
    pollo_whole_id = str(uuid.uuid4())
    beer_id = str(uuid.uuid4())

    products = [
        {"id": pollo_quarter_id, "name": "Pollo 1/4", "price": 12000, "stock": 5},
        {"id": pollo_whole_id, "name": "Pollo Entero", "price": 40000, "stock": 2},
        {"id": beer_id, "name": "Cerveza Aguila", "price": 5000, "stock": 30},
    ]
    portion_map = {
        pollo_quarter_id: {"group_key": "pollo_asado", "group_label": "Pollo Asado", "portion_label": "1/4", "position": 0},
        pollo_whole_id: {"group_key": "pollo_asado", "group_label": "Pollo Asado", "portion_label": "Entero", "position": 1},
    }

    merged = waiter_ordering._merge_portions_into_products(products, portion_map)

    grouped = next(p for p in merged if p.get("is_portioned"))
    singles = [p for p in merged if not p.get("is_portioned")]
    assert grouped["name"] == "Pollo Asado"
    assert [m["label"] for m in grouped["portions"]] == ["1/4", "Entero"]
    assert len(singles) == 1
    assert singles[0]["id"] == beer_id
