"""Modulo CARTA (049H): insumos con unidades y costo promedio, platos directos
o con receta, descuento por receta, migracion y The Time Machine intacta.
Codigo real del flujo de pedidos (hospitality) y de /carta con una base en memoria."""
from __future__ import annotations

import importlib.util
import json
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import carta as carta_endpoint
from app.api.v1.endpoints import hospitality
from app.services import carta as engine
from app.services import owner_report

ROOT = Path(__file__).resolve().parent.parent
ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"
POLLO_CRUDO, PAPA, ACEITE, GAS, CERVEZA = (str(uuid.uuid4()) for _ in range(5))
POLLO_ASADO, PAPAS_FRITAS, CERVEZA_PLATO = (str(uuid.uuid4()) for _ in range(3))


# ------------------------------------------------------------ motor ---
def test_hospitality_carta_pound_to_grams_is_exact():
    assert engine.standard_factor("libra", "g") == Decimal("453.59237")
    assert engine.standard_factor("kilo", "g") == Decimal("1000")
    assert engine.standard_factor("litro", "ml") == Decimal("1000")
    assert engine.standard_factor("unidad", "g") is None, "cuanto pesa un pollo lo define la empresa"
    assert engine.to_consumption(2, {"units_per_purchase": "453.59237"}) == Decimal("907.1847")
    assert engine.clean_unit("Libras", engine.PURCHASE_UNITS) == "libra"
    with pytest.raises(ValueError):
        engine.clean_unit("arroba", engine.PURCHASE_UNITS)


def test_hospitality_carta_yield_factor_is_applied():
    dish = {"kind": "preparado"}
    lines = [{"inventory_item_id": POLLO_CRUDO, "quantity": 250, "yield_pct": 65},
             {"inventory_item_id": ACEITE, "quantity": 20, "yield_pct": None}]
    entries = engine.consumption(dish, lines, 1)
    assert entries == [{"inventory_item_id": POLLO_CRUDO, "quantity": 384.6154, "blocking": False},
                       {"inventory_item_id": ACEITE, "quantity": 20.0, "blocking": False}], "sin rendimiento = 100%"
    half = engine.consumption(dish, lines, 0.5)
    assert half[0]["quantity"] == 192.3077, "media porcion = media receta"
    direct = engine.consumption({"kind": "directo", "inventory_item_id": CERVEZA, "direct_qty": 1}, [], 3)
    assert direct == [{"inventory_item_id": CERVEZA, "quantity": 3.0, "blocking": True}]


def test_hospitality_carta_weighted_average_cost():
    # 1.000 g a $10 + compra de 1.000 g a $14 = $12 por gramo.
    assert engine.weighted_average(1000, 10, 1000, 14) == Decimal("12")
    assert engine.weighted_average(3000, 10, 1000, 14) == Decimal("11")
    assert engine.weighted_average(0, 10, 500, 14) == Decimal("14"), "sin existencia: el de la compra"
    assert engine.weighted_average(-200, 10, 500, 14) == Decimal("14")


def test_hospitality_carta_dish_cost_margin_and_below_cost_warning():
    insumos = {POLLO_CRUDO: {"name": "Pollo crudo", "avg_cost": "12.5"}, ACEITE: {"name": "Aceite", "avg_cost": "8"},
               PAPA: {"name": "Papa", "avg_cost": 0, "entry_price": 0}}
    lines = [{"inventory_item_id": POLLO_CRUDO, "quantity": 400, "yield_pct": 80}, {"inventory_item_id": ACEITE, "quantity": 25, "yield_pct": 100}]
    ok = engine.dish_summary({"kind": "preparado", "price": 18000}, lines, insumos)
    assert ok["cost"] == 500 * 12.5 + 25 * 8 and ok["margin"] == 18000 - 6450 and ok["below_cost"] is False
    cheap = engine.dish_summary({"kind": "preparado", "price": 5000}, lines, insumos)
    assert cheap["below_cost"] is True
    missing = engine.dish_summary({"kind": "preparado", "price": 9000}, lines + [{"inventory_item_id": PAPA, "quantity": 100}], insumos)
    assert missing["cost"] is None and missing["missing_cost"] == ["Papa"], "sin inventar costo"
    assert engine.dish_summary({"kind": "preparado", "price": 9000}, [], insumos)["no_recipe"] is True


def test_hospitality_carta_consumable_can_never_be_linked():
    with pytest.raises(ValueError, match="consumible"):
        engine.validate_link({"item_type": "consumible"})
    engine.validate_link({"item_type": "ingrediente"})
    engine.validate_link({"item_type": "venta_directa"})


# ---------------------------------------------------- base en memoria ---
class Result:
    def __init__(self, rows=None, scalar=None, rowcount=1):
        self.rows, self._scalar, self.rowcount = rows or [], scalar, rowcount

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return [SimpleNamespace(_mapping=r) for r in self.rows]

    def first(self):
        return self.rows[0] if self.rows else None


class CartaDb:
    def __init__(self, modules=None):
        self.modules = modules if modules is not None else {ASADERO: {"carta", "waiter_ordering"}, TTM: {"hospitality"}}
        self.inventory = {
            POLLO_CRUDO: self._inv(ASADERO, "Pollo crudo", 5000, "ingrediente", "unidad", "g", 1600, avg="12.5"),
            PAPA: self._inv(ASADERO, "Papa", 3000, "ingrediente", "kilo", "g", 1000, avg="3"),
            ACEITE: self._inv(ASADERO, "Aceite", 1000, "ingrediente", "litro", "ml", 1000, avg="8"),
            GAS: self._inv(ASADERO, "Gas", 10, "consumible", "unidad", "unidad", 1, avg="90000"),
            CERVEZA: self._inv(ASADERO, "Cerveza", 2, "venta_directa", "unidad", "unidad", 1, avg="3000"),
        }
        self.dishes = {
            POLLO_ASADO: {"id": uuid.UUID(POLLO_ASADO), "company_id": ASADERO, "name": "POLLO Asado", "price": Decimal("40000"),
                          "category_key": "", "station": "parrilla", "requires_term": False, "allows_portions": True,
                          "kind": "preparado", "inventory_item_id": None, "direct_qty": Decimal("1"), "active": True, "position": 1,
                          "presentation": "500 gr", "category_id": None},
            CERVEZA_PLATO: {"id": uuid.UUID(CERVEZA_PLATO), "company_id": ASADERO, "name": "Cerveza", "price": Decimal("6000"),
                            "category_key": "bebidas", "station": "", "requires_term": False, "allows_portions": False,
                            "kind": "directo", "inventory_item_id": uuid.UUID(CERVEZA), "direct_qty": Decimal("1"), "active": True, "position": 2,
                            "presentation": "", "category_id": None},
        }
        self.lines = [
            {"carta_item_id": uuid.UUID(POLLO_ASADO), "company_id": ASADERO, "inventory_item_id": uuid.UUID(POLLO_CRUDO), "component_item_id": None, "quantity": Decimal("400"), "yield_pct": Decimal("80"), "position": 0},
            {"carta_item_id": uuid.UUID(POLLO_ASADO), "company_id": ASADERO, "inventory_item_id": uuid.UUID(PAPA), "component_item_id": None, "quantity": Decimal("300"), "yield_pct": Decimal("100"), "position": 1},
            {"carta_item_id": uuid.UUID(POLLO_ASADO), "company_id": ASADERO, "inventory_item_id": uuid.UUID(ACEITE), "component_item_id": None, "quantity": Decimal("30"), "yield_pct": Decimal("100"), "position": 2},
        ]
        self.movements = []
        self.images: set[str] = set()
        self.image_bytes: dict[str, bytes] = {}
        self.settings: dict = {}
        self.categories: dict[str, dict] = {}
        self.equivalences: dict[tuple, Decimal] = {}
        self.waiter_settings: dict = {}
        self.image_stamps: dict[str, datetime] = {}
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    @staticmethod
    def _inv(cid, name, stock, kind, pu, cu, factor, avg="0"):
        return {"id": uuid.uuid4(), "company_id": cid, "name": name, "name_reference": "", "reference": "", "sku": "",
                "current_stock": Decimal(str(stock)), "min_stock": Decimal("0"), "status": "active",
                "entry_price": Decimal("0"), "sale_price": Decimal("0"), "avg_cost": Decimal(avg),
                "item_type": kind, "purchase_unit": pu, "consumption_unit": cu, "units_per_purchase": Decimal(str(factor))}

    def _inv_rows(self, cid):
        return [{**v, "id": uuid.UUID(k)} for k, v in self.inventory.items() if v["company_id"] == cid]

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        cid = str(p.get("company_id", p.get("c", "")))
        if "FROM company_modules cm JOIN modules m" in sql and "cm.settings" not in sql and "JOIN companies c" not in sql and ":code" not in sql:
            return Result([{"code": c} for c in self.modules.get(cid, set())])
        if sql.startswith("SELECT to_regclass"):
            return Result([{"exists": True}], scalar=True)
        if sql.startswith("SELECT inventory_item_id, unit, amount FROM carta_unit_equivalences"):
            return Result([{"inventory_item_id": k[0], "unit": k[1], "amount": v} for k, v in self.equivalences.items() if k[2] == cid])
        if sql.startswith("INSERT INTO carta_unit_equivalences"):
            self.equivalences[(p["i"], p["unit"], cid)] = p["amount"]
            return Result()
        if "FROM inventory_items WHERE company_id = CAST(:company_id AS uuid) AND COALESCE(status, 'active') NOT IN" in sql:
            return Result(self._inv_rows(cid))
        if sql.startswith("SELECT id, name, price, category_key, station"):
            return Result([d for d in self.dishes.values() if d["company_id"] == cid])
        if sql.startswith("SELECT carta_item_id, inventory_item_id, component_item_id, quantity, yield_pct, position, unit FROM carta_recipe_lines"):
            return Result([l for l in self.lines if l["company_id"] == cid])
        if sql.startswith("SELECT inventory_item_id FROM hospitality_product_images WHERE company_id = :company_id"):
            return Result([{"inventory_item_id": i} for i in self.images])
        if sql.startswith("SELECT inventory_item_id, updated_at FROM hospitality_product_images"):
            return Result([{"inventory_item_id": i, "updated_at": self.image_stamps.get(i)} for i in self.images])
        if sql.startswith("SELECT id, parent_id, label, position, station, quick_notes, requires_term FROM carta_categories"):
            rows = [c for c in self.categories.values() if c["company_id"] == cid]
            return Result(sorted(rows, key=lambda c: (c["position"], c["label"].lower())))
        if sql.startswith("INSERT INTO carta_categories"):
            self.categories[p["id"]] = {"id": uuid.UUID(p["id"]), "company_id": cid, "label": p["label"], "position": p["position"],
                                        "parent_id": uuid.UUID(p["parent_id"]) if p.get("parent_id") else None,
                                        "station": "", "quick_notes": [], "requires_term": False}
            return Result()
        if sql.startswith("UPDATE carta_categories SET label"):
            row = self.categories[p["id"]]
            row.update(label=p["label"], station=p["station"], quick_notes=json.loads(p["notes"]), requires_term=p["requires_term"])
            return Result()
        if sql.startswith("DELETE FROM carta_categories"):
            gone = {p["id"], *[k for k, c in self.categories.items() if str(c["parent_id"]) == p["id"]]}
            for key in gone:
                self.categories.pop(key, None)
            return Result()
        if sql.startswith("UPDATE carta_items SET category_key = :label WHERE"):
            ids = {p["id"], *[k for k, c in self.categories.items() if str(c["parent_id"]) == p["id"]]}
            for dish in self.dishes.values():
                if str(dish.get("category_id") or "") in ids:
                    dish["category_key"] = p["label"]
            return Result()
        if sql.startswith("UPDATE carta_items SET category_id"):
            dish = self.dishes[p["id"]]
            dish.update(category_id=uuid.UUID(p["category_id"]) if p["category_id"] else None, category_key=p["label"])
            return Result()
        if sql.startswith("UPDATE carta_items SET name"):
            dish = self.dishes.get(p["id"])
            if not dish or dish["company_id"] != cid:
                return Result(rowcount=0)
            dish.update({k: p[k] for k in ("name", "presentation", "category_key", "station", "requires_term", "allows_portions", "kind", "direct_qty", "active")},
                        price=Decimal(str(p["price"])), category_id=uuid.UUID(p["category_id"]) if p["category_id"] else None,
                        inventory_item_id=uuid.UUID(p["inventory_item_id"]) if p["inventory_item_id"] else None)
            return Result()
        if "FROM company_modules cm JOIN modules m" in sql and "m.code = :code" in sql:
            return Result([{"settings": dict(self.waiter_settings)}] if "waiter_ordering" in self.modules.get(cid, set()) else [])
        if sql.startswith("SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id WHERE cm.company_id"):
            return Result([{"settings": dict(self.settings)}] if "carta" in self.modules.get(cid, set()) else [])
        if sql.startswith("UPDATE company_modules SET settings"):
            self.settings.update(json.loads(p["s"]))
            return Result()
        if sql.startswith("DELETE FROM carta_items"):
            existed = self.dishes.pop(p["id"], None)
            self.lines = [l for l in self.lines if str(l["carta_item_id"]) != p["id"]]
            return Result(rowcount=1 if existed else 0)
        if sql.startswith("DELETE FROM hospitality_product_images"):
            if p["id"] not in self.inventory:
                self.images.discard(p["id"])
                self.image_bytes.pop(p["id"], None)
            return Result()
        if sql.startswith("INSERT INTO hospitality_product_images"):
            return Result()
        if sql.startswith("UPDATE hospitality_product_images SET image_bytes"):
            self.images.add(p["inventory_item_id"])
            self.image_bytes[p["inventory_item_id"]] = p["image_bytes"]
            return Result()
        if sql.startswith("SELECT c.id, c.name FROM company_modules cm JOIN modules m ON m.id = cm.module_id JOIN companies c"):
            if self.settings.get("qr_token") == p["token"]:
                return Result([{"id": uuid.UUID(ASADERO), "name": "ASADERO EL SOCIO"}])
            return Result([])
        if sql.startswith("SELECT id, sku, name, reference, name_reference, current_stock, status FROM inventory_items WHERE id"):
            row = self.inventory.get(str(p["item_id"]))
            return Result([{**row, "id": uuid.UUID(str(p["item_id"]))}] if row and row["company_id"] == cid else [])
        if sql.startswith("SELECT id, current_stock, min_stock, status FROM inventory_items WHERE id"):
            row = self.inventory.get(str(p["item_id"]))
            return Result([{**row, "id": uuid.UUID(str(p["item_id"]))}] if row and row["company_id"] == cid else [])
        if sql.startswith("UPDATE inventory_items SET current_stock = :after"):
            self.inventory[str(p["item_id"])]["current_stock"] = Decimal(str(p["after"]))
            return Result()
        if sql.startswith("INSERT INTO inventory_movements"):
            self.movements.append(p)
            return Result()
        if sql.startswith("UPDATE inventory_items SET item_type = :item_type"):
            row = self.inventory[str(p["id"])]
            ratio = Decimal(str(p["ratio"]))
            row.update(item_type=p["item_type"], purchase_unit=p["purchase_unit"], consumption_unit=p["consumption_unit"],
                       units_per_purchase=Decimal(str(p["factor"])), current_stock=row["current_stock"] * ratio,
                       min_stock=row["min_stock"] * ratio, avg_cost=row["avg_cost"] / ratio)
            return Result()
        if sql.startswith("INSERT INTO carta_items"):
            self.dishes[p["id"]] = {"id": uuid.UUID(p["id"]), "company_id": cid, "name": p["name"], "presentation": p.get("presentation", ""),
                                    "price": Decimal(str(p["price"])),
                                    "category_key": p["category_key"], "station": p["station"], "requires_term": p["requires_term"],
                                    "category_id": uuid.UUID(p["category_id"]) if p.get("category_id") else None,
                                    "allows_portions": p["allows_portions"], "kind": p["kind"],
                                    "inventory_item_id": uuid.UUID(p["inventory_item_id"]) if p["inventory_item_id"] else None,
                                    "direct_qty": Decimal(str(p["direct_qty"])), "active": p["active"], "position": 9}
            return Result()
        if sql.startswith("DELETE FROM carta_recipe_lines"):
            self.lines = [l for l in self.lines if not (l["company_id"] == cid and str(l["carta_item_id"]) == p["i"])]
            return Result()
        if sql.startswith("INSERT INTO carta_recipe_lines"):
            self.lines.append({"carta_item_id": uuid.UUID(p["i"]), "company_id": cid,
                               "inventory_item_id": uuid.UUID(p["insumo"]) if p.get("insumo") else None,
                               "component_item_id": uuid.UUID(p["component"]) if p.get("component") else None,
                               "quantity": Decimal(str(p["quantity"])), "yield_pct": Decimal(str(p["yield_pct"])), "position": p["position"],
                               "unit": p.get("unit") or None})
            return Result()
        raise AssertionError(f"SQL no esperado: {sql[:150]}")


def item_in(product_id, qty, name="", price=0, label=""):
    return hospitality.HospitalityOrderItemIn(inventory_item_id=product_id, name=name, quantity=qty, unit_price=price,
                                              **({"quantity_label": label} if label else {}))


# ---------------------------------------------------- venta y descuento ---
@pytest.mark.asyncio
async def test_hospitality_carta_selling_a_recipe_dish_deducts_each_ingredient_in_grams():
    db = CartaDb()
    rows = await hospitality._build_order_items(db, uuid.UUID(ASADERO), [item_in(POLLO_ASADO, 2, "POLLO Asado", 40000)])
    row = rows[0]
    assert row["menu_item_id"] == POLLO_ASADO and row["carta_kind"] == "preparado"
    assert [(c["inventory_item_id"], c["quantity"]) for c in row["consumption"]] == [
        (POLLO_CRUDO, 1000.0),  # 2 x 400 g / 80 %
        (PAPA, 600.0), (ACEITE, 60.0)]
    # costo congelado: 1000 g x 12.5 + 600 g x 3 + 60 ml x 8
    assert row["cost"] == 12500 + 1800 + 480
    await hospitality._deduct_inventory(db, uuid.UUID(ASADERO), {"id": "o1", "order_number": "001", "items": rows})
    assert db.inventory[POLLO_CRUDO]["current_stock"] == Decimal("4000")
    assert db.inventory[PAPA]["current_stock"] == Decimal("2400")
    assert db.inventory[ACEITE]["current_stock"] == Decimal("940")
    assert len(db.movements) == 3 and all(m["delta"] < 0 for m in db.movements)


@pytest.mark.asyncio
async def test_hospitality_carta_prepared_dish_never_blocks_but_direct_dish_does():
    db = CartaDb()
    db.inventory[POLLO_CRUDO]["current_stock"] = Decimal("100")
    rows = await hospitality._build_order_items(db, uuid.UUID(ASADERO), [item_in(POLLO_ASADO, 1, "POLLO Asado", 40000)])
    await hospitality._deduct_inventory(db, uuid.UUID(ASADERO), {"id": "o1", "items": rows})
    assert db.inventory[POLLO_CRUDO]["current_stock"] == Decimal("-400"), "queda en negativo y el Dashboard avisa"
    beer = await hospitality._build_order_items(db, uuid.UUID(ASADERO), [item_in(CERVEZA_PLATO, 3, "Cerveza", 6000)])
    with pytest.raises(HTTPException) as exc:
        await hospitality._deduct_inventory(db, uuid.UUID(ASADERO), {"id": "o2", "items": beer})
    assert exc.value.status_code == 409 and "Stock insuficiente" in exc.value.detail


@pytest.mark.asyncio
async def test_hospitality_carta_merged_lines_add_their_consumption():
    db = CartaDb()
    rows = await hospitality._build_order_items(db, uuid.UUID(ASADERO), [item_in(POLLO_ASADO, 1, "POLLO Asado", 40000),
                                                                        item_in(POLLO_ASADO, 1, "POLLO Asado", 40000)])
    merged = hospitality._merge_hospitality_items(rows)
    assert len(merged) == 1 and merged[0]["quantity"] == 2
    assert {c["inventory_item_id"]: c["quantity"] for c in merged[0]["consumption"]}[POLLO_CRUDO] == 1000.0
    assert merged[0]["cost"] == 2 * (6250 + 900 + 240)
    quantities = hospitality._hospitality_item_quantities(merged)
    assert quantities[POLLO_CRUDO] == 1000.0 and POLLO_ASADO not in quantities, "la edicion de pedidos mueve insumos, no platos"


@pytest.mark.asyncio
async def test_hospitality_carta_menu_only_shows_dishes_never_a_consumable():
    db = CartaDb()
    menu = await hospitality.hospitality_inventory_lite(uuid.UUID(ASADERO), limit=500, db=_with_company(db))
    names = [i["name"] for i in menu["inventory"]]
    assert names == ["POLLO Asado 500 gr", "Cerveza"], "nombre visible con su presentacion"
    assert "Gas" not in names and "Aceite" not in names and "Pollo crudo" not in names
    pollo = menu["inventory"][0]
    assert pollo["active"] is True and pollo["station"] == "parrilla" and pollo["carta_kind"] == "preparado"


def _with_company(db):
    original = db.execute

    async def execute(statement, params=None):
        sql = " ".join(str(statement).split())
        if "FROM companies" in sql and "LIMIT 1" in sql or sql.startswith("SELECT 1 FROM companies") or sql.startswith("SELECT id FROM companies"):
            return Result([{"id": params.get("company_id") if params else None}], scalar=1)
        if sql.startswith("SELECT column_name FROM information_schema.columns"):
            return Result([{"column_name": c} for c in ("sale_price", "allows_portions", "current_stock", "min_stock", "status", "updated_at")])
        if sql.startswith("UPDATE inventory_items SET status = 'inactive'"):
            return Result()
        return await original(statement, params)

    db.execute = execute
    return db


# -------------------------------------------------------- The Time Machine ---
@pytest.mark.asyncio
async def test_hospitality_carta_the_time_machine_does_not_change_at_all():
    db = CartaDb()
    ttm_beer = str(uuid.uuid4())
    db.inventory[ttm_beer] = CartaDb._inv(TTM, "Club Colombia", 50, "venta_directa", "unidad", "unidad", 1)
    rows = await hospitality._build_order_items(db, uuid.UUID(TTM), [item_in(ttm_beer, 2, "Club Colombia", 8000)])
    assert "consumption" not in rows[0] and "menu_item_id" not in rows[0] and "cost" not in rows[0], "misma linea de siempre"
    await hospitality._deduct_inventory(db, uuid.UUID(TTM), {"id": "t1", "items": rows})
    assert db.inventory[ttm_beer]["current_stock"] == Decimal("48"), "descuenta el producto uno a uno, como hoy"
    assert not await carta_endpoint.carta_enabled(db, TTM)
    migration = (ROOT / "migrations/versions/021w_carta_module.py").read_text(encoding="utf-8")
    assert TTM not in migration and 'TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"' in migration


# ------------------------------------------------------------ migracion ---
def test_hospitality_carta_migration_keeps_the_same_ids_and_only_touches_the_asadero():
    spec = importlib.util.spec_from_file_location("mig_021w", ROOT / "migrations/versions/021w_carta_module.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = (ROOT / "migrations/versions/021w_carta_module.py").read_text(encoding="utf-8")
    assert len(module.revision) <= 32 and module.down_revision == "021v_owner_report_idx"
    assert "SELECT id, company_id," in source and "'directo', id, 1" in source, "plato directo con el MISMO id del insumo"
    assert "ON CONFLICT (id) DO NOTHING" in source
    assert source.count("CAST(:c AS uuid)") >= 3 and "WHERE company_id = CAST(:c AS uuid)" in source
    for column in ("item_type", "purchase_unit", "consumption_unit", "units_per_purchase", "avg_cost"):
        assert f'("{column}",' in source
    assert "DEFAULT 'venta_directa'" in source and "DEFAULT 'unidad'" in source and "DEFAULT 1" in source


def test_hospitality_carta_historical_orders_and_reports_keep_their_numbers():
    bog = ZoneInfo("America/Bogota")
    inv_id = str(uuid.uuid4())
    inventory = {inv_id: {"name": "POLLO Asado", "entry_price": 20000, "avg_cost": 20000, "current_stock": 5}}
    created = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    old_line = {"inventory_item_id": inv_id, "name": "POLLO Asado", "quantity": 1, "subtotal": 40000}
    new_line = {**old_line, "menu_item_id": inv_id, "consumption": [{"inventory_item_id": inv_id, "quantity": 1, "unit_cost": 21000}], "cost": 21000}
    orders = [
        {"id": "a", "created_at": created, "closed_at": created, "status": "cerrado", "order_type": "table", "total": 40000,
         "table_key": "m1", "table_number": "Mesa 1", "items": [old_line], "metadata": {}, "archived_at": created},
        {"id": "b", "created_at": created, "closed_at": created, "status": "cerrado", "order_type": "table", "total": 40000,
         "table_key": "m2", "table_number": "Mesa 2", "items": [new_line], "metadata": {}, "archived_at": created},
    ]
    per = owner_report.resolve_period("custom", date(2026, 9, 25), date(2026, 9, 1), date(2026, 9, 20))
    rep = owner_report.Report(orders=orders, closures=[], inventory=inventory, portions={}, tz=bog, period=per)
    kpis = rep.kpis()
    margin = {c["key"]: c for c in kpis["cards"]}["margin"]["value"]
    assert margin == (40000 - 20000) + (40000 - 21000), "historico estimado igual que antes; lo nuevo con su costo real"
    assert kpis["costing"]["real_sales"] == 40000 and kpis["costing"]["estimated_sales"] == 40000
    pollo = rep.menu()["products"][0]
    assert pollo["name"] == "POLLO Asado" and pollo["units_text"] == "2", "mismo plato en el historico y en lo nuevo"


# ------------------------------------------------------------ endpoints ---
USERS = {
    "admin": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="administrador", full_name="Adm", email=""),
    "mesero": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="mesero", full_name="Pedro", email=""),
    "ttm": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(TTM), role="company_admin", full_name="T", email=""),
}
client = TestClient(app_main.app)


@pytest.fixture
def api(monkeypatch):
    fake = CartaDb()

    async def get_user(_db, token):
        user = USERS.get(token)
        if not user:
            raise HTTPException(status_code=401, detail="Token requerido.")
        return user

    async def fake_db():
        yield fake

    monkeypatch.setattr(deps, "get_current_company_user", get_user)
    monkeypatch.setattr(carta_endpoint, "active_admin_v2_session", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    yield fake
    app_main.app.dependency_overrides.pop(get_db, None)


def call(method, company, path="", token=None, body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, f"/api/v1/carta/companies/{company}{path}", json=body, headers=headers)


@pytest.mark.parametrize("method,path", [("GET", ""), ("GET", "/alerts"), ("POST", "/items"), ("PUT", f"/items/{uuid.uuid4()}"),
                                          ("PUT", f"/items/{uuid.uuid4()}/recipe"), ("PUT", f"/insumos/{uuid.uuid4()}")])
def test_hospitality_carta_endpoints_require_admin_session_and_module(api, method, path):
    assert call(method, ASADERO, path, body={}).status_code == 401
    assert call(method, ASADERO, path, "mesero", body={}).status_code == 403
    assert call(method, ASADERO, path, "ttm", body={}).status_code == 403
    no_module = call(method, TTM, path, "ttm", body={})
    assert no_module.status_code == 403 and "module_not_enabled_for_tenant" in no_module.text


def test_hospitality_carta_screen_shows_cost_margin_and_alerts(api):
    data = call("GET", ASADERO, "", "admin").json()
    pollo = next(i for i in data["items"] if i["name"] == "POLLO Asado")
    assert pollo["cost"] == 6250 + 900 + 240 and pollo["margin"] == 40000 - 7390 and pollo["below_cost"] is False
    assert [l["insumo"] for l in pollo["recipe"]] == ["Pollo crudo", "Papa", "Aceite"]
    api.inventory[ACEITE]["current_stock"] = Decimal("-50")
    alerts = call("GET", ASADERO, "/alerts", "admin").json()
    assert alerts["negative_stock"] == [{"name": "Aceite", "stock": -50.0, "unit": "ml"}]


def test_hospitality_carta_rejects_consumables_in_dishes_and_recipes(api):
    bad_dish = call("POST", ASADERO, "/items", "admin", {"name": "Gas", "price": 1000, "kind": "directo", "inventory_item_id": GAS})
    assert bad_dish.status_code == 400 and "consumible" in bad_dish.text
    bad_line = call("PUT", ASADERO, f"/items/{POLLO_ASADO}/recipe", "admin", {"lines": [{"inventory_item_id": GAS, "quantity": 1}]})
    assert bad_line.status_code == 400 and "consumible" in bad_line.text
    to_consumable = call("PUT", ASADERO, f"/insumos/{CERVEZA}", "admin",
                         {"item_type": "consumible", "purchase_unit": "unidad", "consumption_unit": "unidad", "units_per_purchase": 1})
    assert to_consumable.status_code == 409 and "Cerveza" in to_consumable.text
    ok = call("POST", ASADERO, "/items", "admin", {"name": "Papas fritas", "price": 7000, "kind": "preparado"})
    assert ok.status_code == 200 and any(i["name"] == "Papas fritas" and i["no_recipe"] for i in ok.json()["items"])


def test_hospitality_carta_unit_change_keeps_physical_stock_and_value(api):
    # Cerveza: 2 unidades a $3.000. Pasa a comprarse por "unidad" y consumirse en ml (330 ml por botella).
    before_value = api.inventory[CERVEZA]["current_stock"] * api.inventory[CERVEZA]["avg_cost"]
    res = call("PUT", ASADERO, f"/insumos/{CERVEZA}", "admin",
               {"item_type": "venta_directa", "purchase_unit": "unidad", "consumption_unit": "ml", "units_per_purchase": 330})
    assert res.status_code == 200, res.text
    row = api.inventory[CERVEZA]
    assert row["current_stock"] == Decimal("660") and row["units_per_purchase"] == Decimal("330")
    assert (row["current_stock"] * row["avg_cost"]).quantize(Decimal("1")) == before_value
    libra = call("PUT", ASADERO, f"/insumos/{PAPA}", "admin", {"item_type": "ingrediente", "purchase_unit": "libra", "consumption_unit": "g"})
    assert libra.status_code == 200 and api.inventory[PAPA]["units_per_purchase"] == Decimal("453.59237")


# ------------------------------- 049J/049K: asistente, categorias, combo y QR ---
def _png(width, height):
    import io as _io

    from PIL import Image

    image = Image.new("RGB", (width, height))
    for x in range(0, width, 8):  # degradado: una foto "real", no ruido
        for y in range(0, height, 8):
            image.paste((x * 255 // width, y * 255 // height, 120), (x, y, x + 8, y + 8))
    buffer = _io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def _cat(data, label, parent=None):
    nodes = data["categories"] if parent is None else next(c for c in data["categories"] if c["label"] == parent)["children"]
    return next(c for c in nodes if c["label"] == label)


@pytest.mark.parametrize("method,path", [("DELETE", f"/items/{uuid.uuid4()}"), ("POST", "/categories"),
                                          ("PUT", f"/categories/{uuid.uuid4()}"), ("DELETE", f"/categories/{uuid.uuid4()}"),
                                          ("POST", f"/categories/{uuid.uuid4()}/image"), ("PUT", "/items-category"),
                                          ("GET", "/qr"), ("POST", "/qr/regenerate"), ("GET", "/qr.png")])
def test_hospitality_carta_wizard_endpoints_require_admin_session_and_module(api, method, path):
    assert call(method, ASADERO, path, body={}).status_code == 401
    assert call(method, ASADERO, path, "mesero", body={}).status_code == 403
    assert call(method, ASADERO, path, "ttm", body={}).status_code == 403
    assert call(method, TTM, path, "ttm", body={}).status_code == 403


def test_hospitality_carta_categories_two_levels_with_station(api):
    data = call("GET", ASADERO, "", "admin").json()
    assert [c["label"] for c in data["categories"]] == ["BEBIDAS", "PLATOS A LA CARTA", "POLLO", "COMIDAS RÁPIDAS", "PORCIONES"]
    assert _cat(data, "BEBIDAS")["hint"] == "gaseosas, jugos, energizantes, cerveza"
    platos = _cat(data, "PLATOS A LA CARTA")["id"]
    res = call("POST", ASADERO, "/categories", "admin", {"label": "carnes", "parent_id": platos})
    assert res.status_code == 200, res.text
    carnes = res.json()["created_category_id"]
    assert _cat(res.json(), "CARNES", "PLATOS A LA CARTA")["id"] == carnes
    assert call("POST", ASADERO, "/categories", "admin", {"label": "Carnes", "parent_id": platos}).status_code == 409
    third = call("POST", ASADERO, "/categories", "admin", {"label": "Res", "parent_id": carnes})
    assert third.status_code == 400 and "subcategoría" in third.text, "solo dos niveles"
    upd = call("PUT", ASADERO, f"/categories/{platos}", "admin",
               {"label": "Platos a la carta", "station": "parrilla", "quick_notes": ["sin sal", " "], "requires_term": True})
    node = _cat(upd.json(), "PLATOS A LA CARTA")
    assert node["station"] == "parrilla" and node["quick_notes"] == ["sin sal"] and node["requires_term"] is True
    # un plato en la subcategoria hereda la estacion de su categoria
    dish = call("POST", ASADERO, "/items", "admin", {"name": "Churrasco", "presentation": "275 gr", "price": 32000,
                                                       "category_id": carnes, "kind": "preparado"}).json()
    row = next(i for i in dish["items"] if i["id"] == dish["created_id"])
    assert row["category_label"] == "PLATOS A LA CARTA" and row["subcategory_label"] == "CARNES"
    assert row["effective_station"] == "parrilla"
    busy = call("DELETE", ASADERO, f"/categories/{platos}", "admin")
    assert busy.status_code == 409 and "Churrasco" in busy.text, "no se borra una categoria con platos"
    bad = call("POST", ASADERO, "/items", "admin", {"name": "X", "price": 1, "category_id": str(uuid.uuid4()), "kind": "preparado"})
    assert bad.status_code == 400


def test_hospitality_carta_wizard_creates_a_full_dish(api):
    """Lo que manda el asistente al terminar: plato (sin foto) y receta; el
    resumen trae costo y margen."""
    rapidas = _cat(call("GET", ASADERO, "", "admin").json(), "COMIDAS RÁPIDAS")["id"]
    created = call("POST", ASADERO, "/items", "admin", {"name": "Hamburguesa", "presentation": "125 gr", "price": 18000,
                                                          "category_id": rapidas, "kind": "preparado", "requires_term": True})
    assert created.status_code == 200, created.text
    dish_id = created.json()["created_id"]
    recipe = call("PUT", ASADERO, f"/items/{dish_id}/recipe", "admin",
                  {"lines": [{"inventory_item_id": POLLO_CRUDO, "quantity": 125}, {"inventory_item_id": PAPA, "quantity": 3}]})
    assert recipe.status_code == 200, recipe.text
    dish = next(i for i in recipe.json()["items"] if i["id"] == dish_id)
    assert dish["display_name"] == "Hamburguesa 125 gr" and dish["category_id"] == rapidas
    assert dish["cost"] == 125 * 12.5 + 3 * 3 and dish["margin"] == 18000 - 1571.5
    assert "has_image" not in dish, "los platos ya no llevan foto"
    assert api.dishes[dish_id]["category_key"] == "COMIDAS RÁPIDAS"
    # editar conserva todo lo demas
    edit = call("PUT", ASADERO, f"/items/{dish_id}", "admin", {"name": "Hamburguesa", "presentation": "150 gr", "price": 19000,
                                                                 "category_id": rapidas, "kind": "preparado"})
    assert edit.status_code == 200 and next(i for i in edit.json()["items"] if i["id"] == dish_id)["display_name"] == "Hamburguesa 150 gr"


def test_hospitality_carta_direct_product_brings_its_sale_price(api):
    api.inventory[CERVEZA]["sale_price"] = Decimal("6500")
    insumos = call("GET", ASADERO, "", "admin").json()["insumos"]
    assert next(i for i in insumos if i["id"] == CERVEZA)["sale_price"] == 6500
    assert all(i["item_type"] != "consumible" or i["name"] == "Gas" for i in insumos)


def test_hospitality_carta_category_image_fits_whole_without_cropping(api):
    from PIL import Image
    import io as _io

    cat = _cat(call("GET", ASADERO, "", "admin").json(), "POLLO")["id"]
    for size, expected in (((1600, 400), (800, 200)), ((600, 1200), (400, 800)), ((3000, 3000), (800, 800)), ((300, 200), (300, 200))):
        res = client.post(f"/api/v1/carta/companies/{ASADERO}/categories/{cat}/image", headers={"Authorization": "Bearer admin"},
                          files={"image": ("foto.png", _png(*size), "image/png")})
        assert res.status_code == 200, res.text
        stored = Image.open(_io.BytesIO(api.image_bytes[cat]))
        assert stored.size == expected and stored.format == "JPEG", (size, stored.size)
        assert len(api.image_bytes[cat]) <= 200 * 1024
    raw = _png(1600, 400)
    client.post(f"/api/v1/carta/companies/{ASADERO}/categories/{cat}/image", headers={"Authorization": "Bearer admin"},
                files={"image": ("foto.png", raw, "image/png")})
    assert api.image_bytes[cat] == carta_endpoint.fit_to_box(raw), "se guarda tal cual: sin una segunda compresion que la emborrone"
    assert _cat(call("GET", ASADERO, "", "admin").json(), "POLLO")["has_image"] is True
    bad = client.post(f"/api/v1/carta/companies/{ASADERO}/categories/{cat}/image", headers={"Authorization": "Bearer admin"},
                      files={"image": ("x.png", b"no es una imagen", "image/png")})
    assert bad.status_code == 422


def test_hospitality_carta_move_many_dishes_at_once(api):
    data = call("GET", ASADERO, "", "admin").json()
    pollo = _cat(data, "POLLO")["id"]
    res = call("PUT", ASADERO, "/items-category", "admin", {"item_ids": [POLLO_ASADO, CERVEZA_PLATO, str(uuid.uuid4())], "category_id": pollo})
    assert res.status_code == 200 and res.json()["moved"] == 2
    assert {i["id"]: i["category_label"] for i in res.json()["items"]} == {POLLO_ASADO: "POLLO", CERVEZA_PLATO: "POLLO"}
    back = call("PUT", ASADERO, "/items-category", "admin", {"item_ids": [CERVEZA_PLATO], "category_id": None})
    assert next(i for i in back.json()["items"] if i["id"] == CERVEZA_PLATO)["category_id"] is None


def test_hospitality_carta_combo_deducts_its_parts_not_its_own_stock(api):
    combo = call("POST", ASADERO, "/items", "admin", {"name": "Combo Socio", "price": 45000, "kind": "combo"}).json()["created_id"]
    res = call("PUT", ASADERO, f"/items/{combo}/recipe", "admin",
               {"lines": [{"component_item_id": POLLO_ASADO, "quantity": 1}, {"component_item_id": CERVEZA_PLATO, "quantity": 2}]})
    assert res.status_code == 200, res.text
    dish = next(i for i in res.json()["items"] if i["id"] == combo)
    assert dish["kind"] == "combo" and dish["inventory_item_id"] is None, "sin existencia propia"
    assert dish["cost"] == 7390 + 2 * 3000 and dish["available"] is True
    rows = asyncio_run(hospitality._build_order_items(api, uuid.UUID(ASADERO), [item_in(combo, 1, "Combo Socio", 45000)]))
    assert {c["inventory_item_id"]: c["quantity"] for c in rows[0]["consumption"]} == {
        POLLO_CRUDO: 500.0, PAPA: 300.0, ACEITE: 30.0, CERVEZA: 2.0}
    asyncio_run(hospitality._deduct_inventory(api, uuid.UUID(ASADERO), {"id": "c1", "items": rows}))
    assert api.inventory[POLLO_CRUDO]["current_stock"] == Decimal("4500") and api.inventory[CERVEZA]["current_stock"] == Decimal("0")
    nested = call("PUT", ASADERO, f"/items/{POLLO_ASADO}/recipe", "admin", {"lines": [{"component_item_id": CERVEZA_PLATO, "quantity": 1}]})
    assert nested.status_code == 400 and "combo" in nested.text, "solo un combo lleva otros platos"
    in_use = call("DELETE", ASADERO, f"/items/{POLLO_ASADO}", "admin")
    assert in_use.status_code == 409 and "Combo Socio" in in_use.text


def test_hospitality_carta_delete_dish(api):
    dish_id = call("POST", ASADERO, "/items", "admin", {"name": "Salchipapa", "price": 12000, "kind": "preparado"}).json()["created_id"]
    res = call("DELETE", ASADERO, f"/items/{dish_id}", "admin")
    assert res.status_code == 200 and dish_id not in [i["id"] for i in res.json()["items"]]
    assert call("DELETE", ASADERO, f"/items/{dish_id}", "admin").status_code == 404


# ------------------------------------- 049K: de punta a punta y las demas ---
def _menu_env(monkeypatch, db, inventory_categories=None):
    """build_waiter_menu / _priced_order_items con la base en memoria; las
    categorias "de inventario" se simulan para probar que no se cuelan."""
    from app.api.v1.endpoints import waiter_ordering

    monkeypatch.setattr(waiter_ordering, "ensure_waiter_ordering_storage", AsyncMock())
    monkeypatch.setattr(waiter_ordering, "_category_rows", AsyncMock(return_value=inventory_categories or {}))
    monkeypatch.setattr(waiter_ordering, "_portion_membership", AsyncMock(return_value={}))
    _with_company(db)
    return waiter_ordering


def test_hospitality_carta_dish_goes_end_to_end_mesero_cocina_caja_inventario_reportes(api, monkeypatch):
    wo = _menu_env(monkeypatch, api, {"pollo": {"key": "pollo", "label": "Pollo viejo", "station": "otra", "quick_notes": [],
                                             "requires_term": False, "has_image": True}})
    data = call("GET", ASADERO, "", "admin").json()
    platos = _cat(data, "PLATOS A LA CARTA")["id"]
    call("PUT", ASADERO, f"/categories/{platos}", "admin", {"label": "PLATOS A LA CARTA", "station": "parrilla",
                                                            "quick_notes": ["sin sal"], "requires_term": True})
    carnes = call("POST", ASADERO, "/categories", "admin", {"label": "CARNES", "parent_id": platos}).json()["created_category_id"]
    dish_id = call("POST", ASADERO, "/items", "admin", {"name": "Churrasco", "presentation": "275 gr", "price": 32000,
                                                          "category_id": carnes, "kind": "preparado"}).json()["created_id"]
    call("PUT", ASADERO, f"/items/{dish_id}/recipe", "admin", {"lines": [{"inventory_item_id": POLLO_CRUDO, "quantity": 275}]})

    # 1. el mesero lo ve: solo categorias de Carta, en tres niveles
    menu = asyncio_run(wo.build_waiter_menu(api, uuid.UUID(ASADERO)))
    assert menu["carta"] is True
    labels = [c["label"] for c in menu["categories"]]
    assert "Pollo viejo" not in labels and "PLATOS A LA CARTA" in labels, "nada de las categorias del inventario"
    platos_menu = next(c for c in menu["categories"] if c["label"] == "PLATOS A LA CARTA")
    assert platos_menu["image_fit"] == "contain" and platos_menu["image_item_id"] == platos
    sub = platos_menu["subcategories"][0]
    assert sub["label"] == "CARNES" and [p["name"] for p in sub["products"]] == ["Churrasco 275 gr"]
    product = sub["products"][0]
    assert product["has_image"] is False and product["station"] == "parrilla" and product["quick_notes"] == ["sin sal"]
    assert all(p["has_image"] is False for c in menu["categories"] for p in c["products"])

    # 2. el pedido llega con precio del servidor, estacion y observaciones
    items = asyncio_run(wo._priced_order_items(api, uuid.UUID(ASADERO), [
        wo.WaiterOrderItemIn(inventory_item_id=dish_id, quantity=2, observations="bien asado", quick_notes=["sin sal"], term="3/4")]))
    line = items[0]
    assert (line.name, line.unit_price, line.station, line.term, line.observations) == ("Churrasco 275 gr", 32000, "parrilla", "3/4", "bien asado")

    # 3. se arma y descuenta inventario con su receta
    rows = asyncio_run(hospitality._build_order_items(api, uuid.UUID(ASADERO), items))
    assert rows[0]["menu_item_id"] == dish_id and rows[0]["cost"] == 2 * 275 * 12.5
    asyncio_run(hospitality._deduct_inventory(api, uuid.UUID(ASADERO), {"id": "o1", "items": rows}))
    assert api.inventory[POLLO_CRUDO]["current_stock"] == Decimal("5000") - 550

    # 4. cocina: la cocina de parrilla la recibe (antes la estacion quedaba vacia y no llegaba)
    order = {"id": "o1", "table_number": "Mesa 3", "status": "pendiente", "items": rows, "metadata": {}}
    comanda = wo._comanda(order, {"parrilla"})
    assert comanda and comanda["items"][0]["observations"] == "bien asado" and comanda["items"][0]["term"] == "3/4"
    assert wo._comanda(order, {"bebidas"}) is None

    # 5. caja y reportes: la venta cerrada entra con su costo real
    bog = ZoneInfo("America/Bogota")
    closed = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    report = owner_report.Report(
        orders=[{**order, "created_at": closed, "closed_at": closed, "status": "cerrado", "order_type": "table",
                 "total": sum(r["subtotal"] for r in rows), "table_key": "m3", "archived_at": closed}],
        closures=[], inventory={}, portions={}, tz=bog,
        period=owner_report.resolve_period("custom", date(2026, 9, 25), date(2026, 9, 1), date(2026, 9, 20)))
    churrasco = report.menu()["products"][0]
    assert churrasco["name"] == "Churrasco 275 gr" and churrasco["sales"] == 64000 and churrasco["cost"] == 6875


def test_hospitality_carta_inventory_categories_are_closed_for_the_asadero_only(api, monkeypatch):
    from app.api.v1.endpoints import waiter_ordering

    monkeypatch.setattr(waiter_ordering, "ensure_waiter_ordering_storage", AsyncMock())
    listed = asyncio_run(waiter_ordering.list_waiter_ordering_categories(uuid.UUID(ASADERO), db=api, _admin=None))
    assert listed["managed_by_carta"] is True and listed["categories"] == []
    with pytest.raises(HTTPException) as exc:
        asyncio_run(waiter_ordering.upsert_waiter_ordering_category(uuid.UUID(ASADERO), "pollo",
                                                                    waiter_ordering.CategoryUpsertIn(label="Pollo"), db=api, _admin=None))
    assert exc.value.status_code == 409 and "Carta" in exc.value.detail


def test_hospitality_carta_the_time_machine_menu_is_unchanged(api, monkeypatch):
    """TTM: mismo menu de siempre (categoria por la primera palabra, con su
    estacion e imagen de inventario), sin la marca de Carta."""
    wo = _menu_env(monkeypatch, api, {"club": {"key": "club", "label": "Cervezas", "station": "barra", "quick_notes": [],
                                             "requires_term": False, "has_image": True}})
    beer = str(uuid.uuid4())
    monkeypatch.setattr(wo, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": [
        {"id": beer, "name": "Club Colombia", "price": 8000, "active": True}]}))
    api.images.add(beer)
    menu = asyncio_run(wo.build_waiter_menu(api, uuid.UUID(TTM)))
    assert "carta" not in menu
    assert [(c["key"], c["label"], c["station"], c["has_image"]) for c in menu["categories"]] == [("club", "Cervezas", "barra", True)]
    assert menu["categories"][0]["products"][0]["has_image"] is True and "subcategories" not in menu["categories"][0]


def test_hospitality_carta_qr_opens_the_right_carta_and_never_costs(api, monkeypatch):
    from app.api.v1.endpoints import waiter_ordering

    seen = []

    async def fake_menu(_db, company_id):
        seen.append(str(company_id))
        return {"menu_emojis": False, "categories": [
            {"key": "c1", "label": "POLLO", "has_image": True, "image_item_id": "c1", "image_version": "7", "image_fit": "contain",
             "station": "parrilla", "subcategories": [{"key": "s1", "label": "ASADO", "has_image": True, "image_item_id": "s1",
                                                       "image_fit": "contain", "products": [{"id": POLLO_ASADO, "name": "POLLO Asado"}]}],
             "products": [{"id": POLLO_ASADO, "name": "POLLO Asado 500 gr", "price": 40000, "has_image": False, "cost": 7390, "stock": 12,
                           "subcategory_key": "s1"}]},
            {"key": "vacia", "label": "VACIA", "products": []}]}

    monkeypatch.setattr(waiter_ordering, "build_waiter_menu", fake_menu)
    info = call("GET", ASADERO, "/qr", "admin").json()
    token = info["url"].split("t=")[1]
    assert call("GET", ASADERO, "/qr", "admin").json()["url"] == info["url"], "el mismo QR hasta que se cambie"
    png = call("GET", ASADERO, "/qr.png", "admin")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    public = client.get(f"/api/v1/carta/public/{token}")
    assert public.status_code == 200 and seen == [ASADERO]
    body = public.json()
    assert body["company_name"] == "ASADERO EL SOCIO" and [c["label"] for c in body["categories"]] == ["POLLO"]
    pollo = body["categories"][0]
    assert (pollo["image_item_id"], pollo["image_version"], pollo["image_fit"]) == ("c1", "7", "contain")
    assert pollo["subcategories"][0]["label"] == "ASADO" and pollo["products"][0]["subcategory_key"] == "s1"
    assert "cost" not in public.text and "stock" not in public.text and "parrilla" not in public.text
    assert client.get("/api/v1/carta/public/codigo-inventado-que-no-existe-123").status_code == 404
    new = call("POST", ASADERO, "/qr/regenerate", "admin").json()["url"]
    assert new != info["url"] and client.get(f"/api/v1/carta/public/{token}").status_code == 404, "el QR viejo deja de servir"
    page = client.get("/carta-qr")
    assert page.status_code == 200 and "carta_qr.js" in page.text


def test_hospitality_carta_tree_migration_reorganizes_only_the_asadero():
    spec = importlib.util.spec_from_file_location("mig_021z", ROOT / "migrations/versions/021z_carta_tree.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "021y_carta_wizard"
    assert module.TARGET_COMPANY_ID == ASADERO
    source = (ROOT / "migrations/versions/021z_carta_tree.py").read_text(encoding="utf-8")
    assert TTM not in source
    for sql in re.findall(r"(?:UPDATE|DELETE FROM) (?:carta_items|carta_recipe_lines|inventory_items)[^\n]*\n[^\n]*", source):
        assert "company_id = CAST(:c AS uuid)" in sql, sql
    # los 12 platos de la lista, en su categoria
    assert module.REASSIGN == {
        "carneasada": "PLATOS A LA CARTA", "carnechurrasco": "PLATOS A LA CARTA",
        "gaseosacocacola": "BEBIDAS", "gaseosamanzana": "BEBIDAS", "gaseosacolombiana": "BEBIDAS", "jugonaturalaguamaracuya": "BEBIDAS",
        "polloasado": "POLLO", "pollobroaster": "POLLO", "pollofrito": "POLLO",
        "papafrancesa": "PORCIONES", "papasalada": "PORCIONES", "hamburguesaranchera": "COMIDAS RÁPIDAS"}

    def norm(name):
        return re.sub(r"[^a-z0-9]", "", name.lower().translate(str.maketrans("áéíóúüñ", "aeiouun")))

    names = ["CARNE Asada", "CARNE Churrasco", "GASEOSA Cocacola", "GASEOSA Manzana", "GASEOSA Colombiana",
             "JUGO NATURAL Agua maracuyá", "POLLO Asado", "POLLO Broaster", "POLLO frito", "PAPA FRANCESA", "PAPA SALADA",
             "HAMBURGUESA ranchera"]
    assert all(norm(n) in module.REASSIGN for n in names), "el SQL normaliza igual: sin tildes, espacios ni signos"
    assert norm("COMBO 1/2 pollo + papa + gaseosa").startswith("combo") and norm("COMBO 1 pollo + papa + plátano + gaseosa").startswith("combo")
    assert "LIKE 'combo%'" in source and "DELETE FROM carta_items" in source


def test_hospitality_carta_wizard_migration_is_short_and_only_touches_carta_tables():
    spec = importlib.util.spec_from_file_location("mig_021y", ROOT / "migrations/versions/021y_carta_wizard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "021x_costos_module"


# ------------------------------------------ 049N: unidades en la receta ---
TOMATE = {"consumption_unit": "g", "purchase_unit": "kilo", "units_per_purchase": Decimal("1000")}


@pytest.mark.parametrize("unit,insumo,expected", [
    ("g", TOMATE, Decimal("1")), ("kg", TOMATE, Decimal("1000")), ("lb", TOMATE, Decimal("453.59237")),
    ("ml", {"consumption_unit": "ml", "purchase_unit": "litro", "units_per_purchase": 1000}, Decimal("1")),
    ("l", {"consumption_unit": "ml", "purchase_unit": "litro", "units_per_purchase": 1000}, Decimal("1000")),
    ("unidad", {"consumption_unit": "g", "purchase_unit": "unidad", "units_per_purchase": 1600}, Decimal("1600")),
    ("par", {"consumption_unit": "unidad", "purchase_unit": "unidad", "units_per_purchase": 1}, Decimal("2")),
    ("g", {"consumption_unit": "unidad", "purchase_unit": "kilo", "units_per_purchase": 10}, Decimal("0.01")),
    ("ml", TOMATE, None), ("g", {"consumption_unit": "unidad", "purchase_unit": "unidad", "units_per_purchase": 1}, None),
])
def test_hospitality_carta_recipe_units_convert_both_ways(unit, insumo, expected):
    factor = engine.line_factor(unit, insumo)
    assert factor == expected, (unit, factor)


def test_hospitality_carta_recipe_units_in_consumption_and_cost():
    insumos = {POLLO_CRUDO: {**TOMATE, "name": "Tomate", "avg_cost": Decimal("4")}}  # $4.000 el kilo
    dish = {"kind": "preparado", "price": 18000}
    for line in ({"quantity": 3, "unit": "g"}, {"quantity": Decimal("0.003"), "unit": "kg"}):
        entries = engine.consumption(dish, [{"inventory_item_id": POLLO_CRUDO, "yield_pct": 100, **line}], 1, insumos=insumos)
        assert entries[0]["quantity"] == 3.0, line
    summary = engine.dish_summary(dish, [{"inventory_item_id": POLLO_CRUDO, "quantity": 3, "unit": "g", "yield_pct": 100}], insumos)
    assert summary["cost"] == 12.0, "3 gr de un tomate de $4.000 el kilo = $12"
    legacy = engine.consumption(dish, [{"inventory_item_id": POLLO_CRUDO, "quantity": 250, "yield_pct": 100}], 1, insumos=insumos)
    assert legacy[0]["quantity"] == 250.0, "las lineas de antes (sin unidad) siguen en la unidad del inventario"


def test_hospitality_carta_three_grams_of_tomato_from_five_kilos(api):
    tomato = str(uuid.uuid4())
    api.inventory[tomato] = CartaDb._inv(ASADERO, "Tomate", 5000, "ingrediente", "kilo", "g", 1000, avg="4")  # 5 kg
    dish_id = call("POST", ASADERO, "/items", "admin", {"name": "Hamburguesa", "price": 18000, "kind": "preparado"}).json()["created_id"]
    res = call("PUT", ASADERO, f"/items/{dish_id}/recipe", "admin", {"lines": [
        {"inventory_item_id": tomato, "quantity": 3, "unit": "gr"},
        {"inventory_item_id": ACEITE, "quantity": 0.02, "unit": "litros"},
        {"inventory_item_id": POLLO_CRUDO, "quantity": 125, "unit": "g"}]})
    assert res.status_code == 200, res.text
    dish = next(i for i in res.json()["items"] if i["id"] == dish_id)
    lines = {l["insumo"]: l for l in dish["recipe"]}
    assert (lines["Tomate"]["unit"], lines["Tomate"]["unit_label"], lines["Tomate"]["cost"]) == ("g", "gr", 12.0)
    assert (lines["Aceite"]["unit"], lines["Aceite"]["stock_quantity"], lines["Aceite"]["cost"]) == ("l", 20.0, 160.0)
    assert lines["Pollo crudo"]["cost"] == 125 * 12.5
    assert dish["cost"] == 12 + 160 + 1562.5, "el costo del plato suma sus ingredientes"
    assert lines["Pollo crudo"]["share_pct"] == 90.1 and lines["Tomate"]["share_pct"] == 0.7, "se ve cual pesa mas"
    rows = asyncio_run(hospitality._build_order_items(api, uuid.UUID(ASADERO), [item_in(dish_id, 1, "Hamburguesa", 18000)]))
    asyncio_run(hospitality._deduct_inventory(api, uuid.UUID(ASADERO), {"id": "h1", "items": rows}))
    assert api.inventory[tomato]["current_stock"] == Decimal("4997"), "5 kg - 3 gr = 4,997 kg"
    assert api.inventory[ACEITE]["current_stock"] == Decimal("980"), "0,02 litros = 20 ml"
    assert rows[0]["cost"] == 12 + 160 + 1562.5


def test_hospitality_carta_unit_without_equivalence_is_allowed_and_flagged(api):
    ok = call("PUT", ASADERO, f"/items/{POLLO_ASADO}/recipe", "admin",
              {"lines": [{"inventory_item_id": CERVEZA, "quantity": 250, "unit": "ml"}]})
    assert ok.status_code == 200, "se permite; la pantalla pide la equivalencia"
    dish = next(i for i in ok.json()["items"] if i["id"] == POLLO_ASADO)
    line = dish["recipe"][0]
    assert line["needs_equivalence"] is True and line["cost"] is None and line["stock_quantity"] is None
    assert dish["missing_equivalence"] == ["Cerveza"] and dish["cost"] is None, "sin cifra inventada"
    rows = asyncio_run(hospitality._build_order_items(api, uuid.UUID(ASADERO), [item_in(POLLO_ASADO, 1, "POLLO Asado", 40000)]))
    assert rows[0]["consumption"] == [] and rows[0]["cost"] is None, "ni descuenta ni congela un costo falso"
    unknown = call("PUT", ASADERO, f"/items/{POLLO_ASADO}/recipe", "admin",
                   {"lines": [{"inventory_item_id": PAPA, "quantity": 1, "unit": "vaso"}]})
    assert unknown.status_code == 400 and "Unidad inválida" in unknown.text


def test_hospitality_carta_recipe_units_migration_keeps_existing_quantities():
    path = ROOT / "migrations/versions/022d_recipe_units.py"
    spec = importlib.util.spec_from_file_location("mig_022d", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = path.read_text(encoding="utf-8")
    assert len(module.revision) <= 32 and module.down_revision == "022c_fixed_expenses"
    assert "CASE WHEN i.consumption_unit IN ('g', 'ml') THEN i.consumption_unit ELSE 'unidad' END" in source
    assert "i.company_id = l.company_id" in source and "quantity" not in source.split("def upgrade")[1].split("def downgrade")[0]


# ---------------------------- 049O: equivalencias y costos desproporcionados ---
def _carne(api, **kwargs):
    carne = str(uuid.uuid4())
    api.inventory[carne] = CartaDb._inv(ASADERO, "Carne de res", 20, "ingrediente", kwargs.get("pu", "unidad"),
                                        kwargs.get("cu", "unidad"), kwargs.get("f", 1), avg=kwargs.get("avg", "14000"))
    return carne


def test_hospitality_carta_275g_of_meat_bought_at_14000_the_pound(api):
    # Como esta hoy en el Asadero: el inventario cuenta la carne por "unidad" a $14.000 (una libra)
    carne = _carne(api)
    dish_id = call("POST", ASADERO, "/items", "admin", {"name": "CARNE Asada", "price": 32000, "kind": "preparado"}).json()["created_id"]
    call("PUT", ASADERO, f"/items/{dish_id}/recipe", "admin", {"lines": [{"inventory_item_id": carne, "quantity": 275, "unit": "gr"}]})
    before = next(i for i in call("GET", ASADERO, "", "admin").json()["items"] if i["id"] == dish_id)
    assert before["recipe"][0]["needs_equivalence"] is True and before["cost"] is None, "sin equivalencia: se pide, no se inventa"
    # una sola vez: "1 unidad de carne = 1 lb"
    eq = call("PUT", ASADERO, f"/insumos/{carne}/equivalences", "admin", {"unit": "lb", "amount": 1})
    assert eq.status_code == 200, eq.text
    assert next(i for i in eq.json()["insumos"] if i["id"] == carne)["equivalences"] == {"lb": 1.0}
    dish = next(i for i in eq.json()["items"] if i["id"] == dish_id)
    assert dish["recipe"][0]["cost"] == 8488.2, "275 gr a $14.000 la libra ≈ $8.500"
    assert dish["cost"] == 8488.2 and dish["cost_suspect"] == []
    # se reutiliza: otro plato en onzas o kilos, sin volver a preguntar
    other = call("POST", ASADERO, "/items", "admin", {"name": "Churrasco", "price": 40000, "kind": "preparado"}).json()["created_id"]
    res = call("PUT", ASADERO, f"/items/{other}/recipe", "admin", {"lines": [{"inventory_item_id": carne, "quantity": 0.5, "unit": "kg"}]})
    churrasco = next(i for i in res.json()["items"] if i["id"] == other)
    assert churrasco["recipe"][0]["needs_equivalence"] is False and churrasco["cost"] == 15432.2, "0,5 kg = 1,1023 lb"
    rows = asyncio_run(hospitality._build_order_items(api, uuid.UUID(ASADERO), [item_in(dish_id, 1, "CARNE Asada", 32000)]))
    asyncio_run(hospitality._deduct_inventory(api, uuid.UUID(ASADERO), {"id": "c1", "items": rows}))
    assert api.inventory[carne]["current_stock"] == Decimal("19.3937"), "descuenta 275 gr = 0,6063 libras de la carne"


def test_hospitality_carta_meat_in_pounds_in_inventory_needs_no_equivalence(api):
    # carne comprada por libra y consumida en gramos: $14.000 / 453,59 g
    carne = _carne(api, pu="libra", cu="g", f="453.59237", avg=str(Decimal("14000") / Decimal("453.59237")))
    dish_id = call("POST", ASADERO, "/items", "admin", {"name": "CARNE Asada", "price": 32000, "kind": "preparado"}).json()["created_id"]
    res = call("PUT", ASADERO, f"/items/{dish_id}/recipe", "admin", {"lines": [{"inventory_item_id": carne, "quantity": 275, "unit": "g"}]})
    assert next(i for i in res.json()["items"] if i["id"] == dish_id)["cost"] == 8487.8


def test_hospitality_carta_disproportionate_cost_triggers_the_alert(api):
    # la receta vieja: 275 "unidades" de carne de $14.000 = $3.850.000 en un plato de $32.000
    carne = _carne(api)
    dish_id = call("POST", ASADERO, "/items", "admin", {"name": "CARNE Asada", "price": 32000, "kind": "preparado"}).json()["created_id"]
    res = call("PUT", ASADERO, f"/items/{dish_id}/recipe", "admin", {"lines": [{"inventory_item_id": carne, "quantity": 275, "unit": "unidad"}]})
    dish = next(i for i in res.json()["items"] if i["id"] == dish_id)
    assert dish["cost_suspect"] == ["Carne de res"], "avisa en vez de mostrar la cifra como correcta"
    assert dish["cost"] is None and dish["margin"] is None and dish["below_cost"] is False
    assert dish["recipe"][0]["cost_suspect"] is True
    rows = asyncio_run(hospitality._build_order_items(api, uuid.UUID(ASADERO), [item_in(dish_id, 1, "CARNE Asada", 32000)]))
    assert rows[0]["cost"] is None, "los reportes no reciben $3.850.000 de costo"
    assert engine.SUSPECT_SHARE_OF_PRICE == 3


def test_hospitality_carta_every_insumo_offers_the_same_units():
    assert list(engine.RECIPE_UNITS.values()) == ["gr", "kg", "lb", "onza", "ml", "litros", "unidad", "par", "docena",
                                                   "paquete", "cucharada", "pizca"]
    sal = {"consumption_unit": "g", "purchase_unit": "kilo", "units_per_purchase": 1000}
    assert engine.line_factor("cucharada", sal) is None, "cuantos gramos tiene una cucharada: se pide"
    assert engine.line_factor("cucharada", {**sal, "equivalences": {"cucharada": Decimal("12")}}) == Decimal("12")
    assert engine.line_factor("cucharada", {"consumption_unit": "ml", "purchase_unit": "litro", "units_per_purchase": 1000}) == Decimal("15"), "1 cucharada = 15 ml"
    assert engine.line_factor("oz", sal) == Decimal("28.349523125")
    assert engine.line_factor("docena", {"consumption_unit": "unidad"}) == Decimal("12")
    assert engine.line_factor("paquete", {"consumption_unit": "unidad", "equivalences": {"paquete": Decimal("24")}}) == Decimal("24")


def test_hospitality_carta_equivalences_migration():
    path = ROOT / "migrations/versions/022e_unit_equivalences.py"
    spec = importlib.util.spec_from_file_location("mig_022e", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = path.read_text(encoding="utf-8")
    assert len(module.revision) <= 32 and module.down_revision == "022d_recipe_units"
    assert "PRIMARY KEY (company_id, inventory_item_id, unit)" in source
    assert "COALESCE(i.consumption_unit, 'unidad') = 'unidad' AND l.unit = 'unidad' AND l.quantity >= :n" in source
    assert "i.company_id = l.company_id" in source and module.SUSPECT_UNITS == 20


def test_hospitality_carta_meat_configured_as_one_gram_per_unit_is_the_real_bug(api):
    """El caso del Asadero: carne comprada por "unidad" a $14.000 (una libra),
    consumida en gramos y "1 unidad = 1 g". Antes: 275 g x $14.000 = $3.850.000."""
    carne = _carne(api, pu="unidad", cu="g", f=1)
    dish_id = call("POST", ASADERO, "/items", "admin", {"name": "CARNE Asada", "price": 32000, "kind": "preparado"}).json()["created_id"]
    res = call("PUT", ASADERO, f"/items/{dish_id}/recipe", "admin", {"lines": [{"inventory_item_id": carne, "quantity": 275, "unit": "g"}]})
    insumo = next(i for i in res.json()["insumos"] if i["id"] == carne)
    assert insumo["purchase_weight_missing"] is True and insumo["avg_cost"] is None, "no se muestra $14.000 por gramo"
    dish = next(i for i in res.json()["items"] if i["id"] == dish_id)
    assert dish["recipe"][0]["needs_equivalence"] is True and dish["cost"] is None, "se pregunta cuanto pesa 1 unidad"
    rows = asyncio_run(hospitality._build_order_items(api, uuid.UUID(ASADERO), [item_in(dish_id, 1, "CARNE Asada", 32000)]))
    assert rows[0]["consumption"] == [] and rows[0]["cost"] is None, "ni descuenta 275 de 20 ni congela millones"
    # no se puede volver a guardar "1 unidad = 1 g"
    again = call("PUT", ASADERO, f"/insumos/{carne}", "admin",
                 {"item_type": "ingrediente", "purchase_unit": "unidad", "consumption_unit": "g", "units_per_purchase": 1})
    assert again.status_code == 400 and "453,6 g" in again.text
    # la respuesta: 1 unidad de compra = 1 libra (453,59 g); costo y existencia se reexpresan
    fixed = call("PUT", ASADERO, f"/insumos/{carne}", "admin",
                 {"item_type": "ingrediente", "purchase_unit": "unidad", "consumption_unit": "g", "units_per_purchase": 453.59237})
    assert fixed.status_code == 200, fixed.text
    assert api.inventory[carne]["current_stock"] == Decimal("20") * Decimal("453.59237"), "20 libras = 9.071,8 g"
    dish = next(i for i in fixed.json()["items"] if i["id"] == dish_id)
    assert dish["cost"] == 8487.8 and dish["recipe"][0]["cost"] == 8487.8, "275 gr a $14.000 la libra ≈ $8.500"
