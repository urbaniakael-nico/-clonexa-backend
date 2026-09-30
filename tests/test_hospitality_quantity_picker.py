"""049W: selector de cantidad libre (entero + fraccion). Pedir 6 y 1/2 de un
producto que se vende por porciones cobra 6,5 veces el precio y descuenta 6,5
del inventario; un producto sin porciones solo acepta enteros. Tambien: el
interruptor llega a los cuatro canales, y editar un insumo nunca toca la
existencia."""
from __future__ import annotations

import importlib.util
import json
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import hospitality, inventory, waiter_ordering as wo
from app.services import carta as carta_engine

COMPANY_ID = uuid.UUID("7625872c-f941-4479-a27b-f8443be953c5")
CATALOG = [
    {"id": "pollo", "name": "POLLO Asado", "price": 28000, "active": True, "allows_portions": True,
     "carta_kind": "preparado", "station": "Parrilla"},
    {"id": "gaseosa", "name": "GASEOSA Coca Cola", "price": 4500, "active": True, "allows_portions": False,
     "carta_kind": "directo", "station": ""},
]


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr(wo, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": [dict(p) for p in CATALOG]}))
    monkeypatch.setattr(wo, "_portion_membership", AsyncMock(return_value={}))
    monkeypatch.setattr(wo, "_category_rows", AsyncMock(return_value={}))


@pytest.mark.asyncio
async def test_hospitality_six_and_a_half_charges_six_and_a_half_times_the_price(catalog):
    items = await wo._priced_order_items(None, COMPANY_ID, [wo.WaiterOrderItemIn(inventory_item_id="pollo", quantity=6.5)])
    line = items[0]
    assert line.quantity == 6.5
    assert line.unit_price == 28000
    # hospitality._build_order_items guarda subtotal = _money(cantidad x precio unitario)
    assert hospitality._money(line.quantity * line.unit_price) == 182000.0   # "Vas a cobrar $182.000"
    assert line.line_total is None and not line.quantity_label              # sin precio de "fraccion" aparte


@pytest.mark.asyncio
async def test_hospitality_products_without_portions_only_take_whole_units(catalog):
    with pytest.raises(HTTPException) as err:
        await wo._priced_order_items(None, COMPANY_ID, [wo.WaiterOrderItemIn(inventory_item_id="gaseosa", quantity=6.5)])
    assert err.value.status_code == 422 and "unidades enteras" in err.value.detail
    items = await wo._priced_order_items(None, COMPANY_ID, [wo.WaiterOrderItemIn(inventory_item_id="gaseosa", quantity=6)])
    assert items[0].quantity == 6


def test_hospitality_six_and_a_half_discounts_six_and_a_half_from_inventory():
    # Plato preparado: 1 pollo entero de la receta por unidad vendida.
    dish = {"id": "pollo", "kind": "preparado"}
    lines = [{"inventory_item_id": "insumo-pollo", "quantity": 1, "unit": "unidad", "yield_pct": 100}]
    insumos = {"insumo-pollo": {"id": "insumo-pollo", "consumption_unit": "unidad", "units_per_purchase": 1, "current_stock": 40}}
    used = carta_engine.consumption(dish, lines, 6.5, insumos=insumos)
    assert used == [{"inventory_item_id": "insumo-pollo", "quantity": 6.5, "blocking": False}]
    # Venta directa (se descuenta el insumo del plato).
    direct = carta_engine.consumption({"id": "g", "kind": "directo", "inventory_item_id": "insumo-g", "direct_qty": 1}, [], 6)
    assert direct[0]["quantity"] == 6.0


@pytest.mark.asyncio
async def test_hospitality_quantity_picker_switch_reaches_the_menus(monkeypatch):
    monkeypatch.setattr(wo, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": [dict(p) for p in CATALOG]}))
    monkeypatch.setattr(wo, "_carta_on", AsyncMock(return_value=False))
    monkeypatch.setattr(wo, "_category_rows", AsyncMock(return_value={}))
    monkeypatch.setattr(wo, "_portion_membership", AsyncMock(return_value={}))

    class Db:
        async def execute(self, *_a, **_k):
            from types import SimpleNamespace
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))

    monkeypatch.setattr(wo, "_module_settings", AsyncMock(return_value={"quantity_picker": True}))
    assert (await wo.build_waiter_menu(Db(), COMPANY_ID))["quantity_picker"] is True
    monkeypatch.setattr(wo, "_module_settings", AsyncMock(return_value={}))
    assert (await wo.build_waiter_menu(Db(), COMPANY_ID))["quantity_picker"] is False


@pytest.mark.asyncio
async def test_hospitality_qr_menu_reads_the_switch():
    class Row:
        def __init__(self, settings):
            self.settings = settings

    class Db:
        def __init__(self, settings):
            self.settings = settings

        async def execute(self, *_a, **_k):
            from types import SimpleNamespace
            row = {"settings": self.settings} if self.settings is not None else None
            return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))

    assert await hospitality._quantity_picker_049w(Db({"quantity_picker": True}), COMPANY_ID) is True
    assert await hospitality._quantity_picker_049w(Db(json.dumps({"quantity_picker": True})), COMPANY_ID) is True
    assert await hospitality._quantity_picker_049w(Db({}), COMPANY_ID) is False
    assert await hospitality._quantity_picker_049w(Db(None), COMPANY_ID) is False


@pytest.mark.asyncio
async def test_hospitality_editing_an_insumo_never_touches_its_stock():
    """Editar guarda nombre, estado y minimo; la existencia no esta en el
    modelo ni en el UPDATE: solo cambia con compras, ventas y devoluciones."""
    assert "current_stock" not in inventory.InventoryItemUpdate.model_fields
    captured = {}

    class Db:
        async def execute(self, stmt, params=None):
            from types import SimpleNamespace
            captured["sql"] = " ".join(str(stmt).split())
            captured["params"] = params
            row = {"id": params["item_id"], "name_reference": params["name_reference"], "status": params["status"], "current_stock": 12}
            return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))

    payload = inventory.InventoryItemUpdate(name_reference="POLLO Asado entero", status="inactive", color="")
    await inventory._update_inventory_item_record(Db(), uuid.uuid4(), payload, company_id=COMPANY_ID)
    set_clause = captured["sql"].split(" SET ", 1)[1].split(" WHERE ", 1)[0]
    assert "current_stock" not in set_clause
    assert "min_stock = COALESCE(:min_stock, min_stock)" in set_clause         # sin minimo en el envio, se conserva
    assert captured["params"]["name_reference"] == "POLLO Asado entero"
    assert captured["params"]["status"] == "inactive"
    assert captured["params"]["min_stock"] is None


MIGRATION = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "022k_quantity_picker.py"


def test_hospitality_quantity_picker_migration_is_only_for_asadero(monkeypatch):
    spec = importlib.util.spec_from_file_location("qty_picker_mig", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32
    assert module.down_revision == "022j_cashier_redesign"
    statements = []
    monkeypatch.setattr(module, "op", type("Op", (), {"execute": staticmethod(statements.append)}))
    module.upgrade()
    assert f"cm.company_id = '{COMPANY_ID}'::uuid" in statements[0]
    assert json.loads(module.SETTINGS_PATCH) == {"quantity_picker": True}
    module.downgrade()
    assert "- 'quantity_picker'" in statements[1]
