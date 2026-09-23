"""Inventory: delete a product, and the "Permite porciones" field.

- No history at all -> the row is really deleted (and its mesero photo /
  portion-group membership with it).
- Any history (stock movements, hospitality orders, material requests) ->
  soft delete: status 'deleted' + deleted_at; movements are untouched, and
  the product disappears from the inventory list and can't be edited.
- The endpoint needs a real session (Admin V2 or an admin/owner of THAT
  company) from day one.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import inventory


COMPANY_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _no_storage_ddl(monkeypatch):
    monkeypatch.setattr(inventory, "ensure_inventory_storage", AsyncMock())


class InventoryDb:
    def __init__(self, *, movements=0, in_orders=False, in_materials=False, tables=("hospitality_orders", "material_requests", "hospitality_product_images", "hospitality_product_portions")):
        self.item_id = uuid.uuid4()
        self.items = {str(self.item_id): {"id": str(self.item_id), "company_id": str(COMPANY_ID), "name_reference": "CARNE Churrasco", "status": "active"}}
        self.movements = [{"item_id": str(self.item_id)} for _ in range(movements)]
        self.in_orders = in_orders
        self.in_materials = in_materials
        self.tables = set(tables)
        self.deleted_from: list[str] = []
        self.commit = AsyncMock()

    def _result(self, rows=None, scalar=None):
        rows = rows or []
        return SimpleNamespace(
            mappings=lambda: SimpleNamespace(first=lambda: rows[0] if rows else None, all=lambda: rows),
            scalar=lambda: scalar,
        )

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        if sql.startswith(("CREATE", "ALTER", "DO ")):
            return self._result()
        if "to_regclass(:name)" in sql:
            return self._result(scalar=params["name"].split(".", 1)[1] in self.tables)
        if "FOR UPDATE" in sql:
            row = self.items.get(params["item_id"])
            ok = row and row["company_id"] == params["company_id"] and row["status"] != "deleted"
            return self._result([dict(row)] if ok else [])
        if "COUNT(*) FROM inventory_movements" in sql:
            return self._result(scalar=len([m for m in self.movements if m["item_id"] == params["item_id"]]))
        if "FROM hospitality_orders" in sql:
            assert f'"inventory_item_id": "{self.item_id}"' in params["by_inventory"]
            return self._result(scalar=self.in_orders)
        if "FROM material_requests" in sql:
            return self._result(scalar=self.in_materials)
        if sql.startswith("UPDATE inventory_items SET status = 'deleted'"):
            self.items[params["item_id"]]["status"] = "deleted"
            self.items[params["item_id"]]["deleted_at"] = "now"
            return self._result()
        if sql.startswith("DELETE FROM"):
            table = sql.split()[2]
            self.deleted_from.append(table)
            if table == "inventory_items":
                self.items.pop(params["item_id"], None)
            return self._result()
        raise AssertionError(f"unexpected SQL: {sql[:120]}")


async def _delete(db):
    return await inventory.delete_inventory_item(COMPANY_ID, db.item_id, db=db, actor="Dueno")


@pytest.mark.asyncio
async def test_a_product_without_history_is_really_deleted():
    db = InventoryDb()
    result = await _delete(db)
    assert result["mode"] == "deleted"
    assert result["history"] == []
    assert str(db.item_id) not in db.items
    assert db.deleted_from == ["hospitality_product_portions", "hospitality_product_images", "inventory_items"]


@pytest.mark.asyncio
async def test_a_product_with_movements_is_hidden_and_its_history_kept():
    db = InventoryDb(movements=3)
    result = await _delete(db)
    assert result["mode"] == "hidden"
    assert result["history"] == ["movimientos de inventario"]
    assert db.items[str(db.item_id)]["status"] == "deleted"
    assert len(db.movements) == 3                       # history intact
    assert db.deleted_from == []


@pytest.mark.asyncio
async def test_a_product_in_past_orders_is_hidden():
    db = InventoryDb(in_orders=True)
    result = await _delete(db)
    assert result["mode"] == "hidden"
    assert result["history"] == ["pedidos historicos"]


@pytest.mark.asyncio
async def test_a_product_in_material_requests_is_hidden():
    result = await _delete(InventoryDb(in_materials=True))
    assert result["mode"] == "hidden"


@pytest.mark.asyncio
async def test_missing_optional_tables_do_not_break_the_check():
    result = await _delete(InventoryDb(tables=()))
    assert result["mode"] == "deleted"


@pytest.mark.asyncio
async def test_deleting_twice_or_another_companys_product_is_404():
    db = InventoryDb(movements=1)
    await _delete(db)
    with pytest.raises(HTTPException) as exc:
        await _delete(db)                                 # already deleted
    assert exc.value.status_code == 404
    other = InventoryDb()
    other.items[str(other.item_id)]["company_id"] = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        await _delete(other)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Session required from day one
# ---------------------------------------------------------------------------

def _request():
    return SimpleNamespace(cookies={}, headers={})


@pytest.mark.asyncio
async def test_delete_without_a_session_is_rejected(monkeypatch):
    monkeypatch.setattr(inventory, "active_admin_v2_session", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await inventory.require_inventory_admin_045b(COMPANY_ID, _request(), authorization=None, db=SimpleNamespace())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_delete_accepts_admin_v2_and_company_owners_only(monkeypatch):
    monkeypatch.setattr(inventory, "active_admin_v2_session", AsyncMock(return_value={"id": "admin"}))
    assert await inventory.require_inventory_admin_045b(COMPANY_ID, _request(), authorization=None, db=SimpleNamespace()) == "Admin V2"

    monkeypatch.setattr(inventory, "active_admin_v2_session", AsyncMock(return_value=None))
    tenant = AsyncMock(return_value=SimpleNamespace(full_name="Dueno Asadero", email="d@x"))
    monkeypatch.setattr(inventory, "require_company_user_for_tenant", tenant)
    assert await inventory.require_inventory_admin_045b(COMPANY_ID, _request(), authorization="Bearer t", db=SimpleNamespace()) == "Dueno Asadero"
    allowed = tenant.await_args.kwargs["allowed_roles"]
    assert {"dueno", "company_admin", "gerente", "administrador"} <= allowed
    assert "operator" not in allowed and "mesero" not in allowed
    assert tenant.await_args.args[2] == COMPANY_ID          # this company only


def test_the_delete_route_depends_on_the_session_check():
    from fastapi.params import Depends as DependsParam
    import inspect

    deps = [p.default.dependency for p in inspect.signature(inventory.delete_inventory_item).parameters.values() if isinstance(p.default, DependsParam)]
    assert inventory.require_inventory_admin_045b in deps


# ---------------------------------------------------------------------------
# Lists and edits skip deleted products; "Permite porciones" round-trips
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_inventory_list_never_shows_deleted_products(monkeypatch):
    monkeypatch.setattr(inventory, "ensure_inventory_storage", AsyncMock())
    seen = {}

    async def execute(stmt, params=None):
        seen["sql"] = str(stmt)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))

    await inventory.list_inventory_items(COMPANY_ID, include_inactive=True, q=None, limit=10, db=SimpleNamespace(execute=execute))
    assert "COALESCE(status, 'active') <> 'deleted'" in seen["sql"]


@pytest.mark.asyncio
async def test_updates_skip_deleted_products_and_carry_allows_portions():
    seen = {}

    async def execute(stmt, params=None):
        seen["sql"], seen["params"] = str(stmt), params
        row = {"id": params["item_id"], "company_id": str(COMPANY_ID), "status": "active", "allows_portions": True}
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))

    out = await inventory._update_inventory_item_record(
        SimpleNamespace(execute=execute), uuid.uuid4(), inventory.InventoryItemUpdate(allows_portions=True), company_id=COMPANY_ID,
    )
    assert "AND COALESCE(status, 'active') <> 'deleted'" in seen["sql"]
    assert "allows_portions = COALESCE(:allows_portions, allows_portions)" in seen["sql"]
    assert seen["params"]["allows_portions"] is True
    assert out["allows_portions"] is True


def test_allows_portions_is_off_unless_set():
    assert inventory.inventory_item_out({"id": "x", "company_id": "c"})["allows_portions"] is False
    assert inventory.InventoryItemUpdate().allows_portions is None      # untouched on save
