"""Modulo CARTA (049H): insumos con unidades y costo promedio, platos directos
o con receta, descuento por receta, migracion y The Time Machine intacta.
Codigo real del flujo de pedidos (hospitality) y de /carta con una base en memoria."""
from __future__ import annotations

import importlib.util
import json
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
                          "presentation": "500 gr"},
            CERVEZA_PLATO: {"id": uuid.UUID(CERVEZA_PLATO), "company_id": ASADERO, "name": "Cerveza", "price": Decimal("6000"),
                            "category_key": "bebidas", "station": "", "requires_term": False, "allows_portions": False,
                            "kind": "directo", "inventory_item_id": uuid.UUID(CERVEZA), "direct_qty": Decimal("1"), "active": True, "position": 2,
                            "presentation": ""},
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
        if "FROM company_modules cm JOIN modules m" in sql and "cm.settings" not in sql and "JOIN companies c" not in sql:
            return Result([{"code": c} for c in self.modules.get(cid, set())])
        if sql.startswith("SELECT to_regclass"):
            return Result([{"exists": True}], scalar=True)
        if "FROM inventory_items WHERE company_id = CAST(:company_id AS uuid) AND COALESCE(status, 'active') NOT IN" in sql:
            return Result(self._inv_rows(cid))
        if sql.startswith("SELECT id, name, price, category_key, station"):
            return Result([d for d in self.dishes.values() if d["company_id"] == cid])
        if sql.startswith("SELECT carta_item_id, inventory_item_id, component_item_id, quantity, yield_pct, position FROM carta_recipe_lines"):
            return Result([l for l in self.lines if l["company_id"] == cid])
        if sql.startswith("SELECT inventory_item_id FROM hospitality_product_images"):
            return Result([{"inventory_item_id": i} for i in self.images])
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
                               "quantity": Decimal(str(p["quantity"])), "yield_pct": Decimal(str(p["yield_pct"])), "position": p["position"]})
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


# ------------------------------------------- 049J: asistente, combo, foto y QR ---
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


@pytest.mark.parametrize("method,path", [("DELETE", f"/items/{uuid.uuid4()}"), ("POST", "/categories"),
                                          ("POST", f"/items/{uuid.uuid4()}/photo"), ("GET", "/qr"),
                                          ("POST", "/qr/regenerate"), ("GET", "/qr.png")])
def test_hospitality_carta_wizard_endpoints_require_admin_session_and_module(api, method, path):
    assert call(method, ASADERO, path, body={}).status_code == 401
    assert call(method, ASADERO, path, "mesero", body={}).status_code == 403
    assert call(method, ASADERO, path, "ttm", body={}).status_code == 403
    assert call(method, TTM, path, "ttm", body={}).status_code == 403


def test_hospitality_carta_wizard_creates_a_full_dish(api):
    """Lo que manda el asistente al terminar: plato, receta y foto; el resumen
    trae costo y margen."""
    cats = call("GET", ASADERO, "", "admin").json()["categories"]
    assert [c["label"] for c in cats][:5] == ["BEBIDAS", "PLATOS A LA CARTA", "POLLO", "COMIDAS RÁPIDAS", "PORCIONES"]
    added = call("POST", ASADERO, "/categories", "admin", {"label": "desayunos"}).json()
    assert "DESAYUNOS" in [c["label"] for c in added["categories"]]
    created = call("POST", ASADERO, "/items", "admin", {"name": "Churrasco", "presentation": "275 gr", "price": 32000,
                                                          "category_key": "Platos a la carta", "kind": "preparado",
                                                          "requires_term": True, "allows_portions": False})
    assert created.status_code == 200, created.text
    dish_id = created.json()["created_id"]
    recipe = call("PUT", ASADERO, f"/items/{dish_id}/recipe", "admin",
                  {"lines": [{"inventory_item_id": POLLO_CRUDO, "quantity": 125}, {"inventory_item_id": PAPA, "quantity": 3}]})
    assert recipe.status_code == 200, recipe.text
    photo = client.post(f"/api/v1/carta/companies/{ASADERO}/items/{dish_id}/photo", headers={"Authorization": "Bearer admin"},
                        files={"image": ("foto.png", _png(1200, 400), "image/png")})
    assert photo.status_code == 200, photo.text
    dish = next(i for i in photo.json()["items"] if i["id"] == dish_id)
    assert dish["display_name"] == "Churrasco 275 gr" and dish["category_key"] == "PLATOS A LA CARTA"
    assert dish["cost"] == 125 * 12.5 + 3 * 3 and dish["margin"] == 32000 - 1571.5 and dish["has_image"] is True
    assert dish["requires_term"] is True
    lite = asyncio_run(carta_endpoint.carta_inventory_lite(api, ASADERO))
    row = next(r for r in lite if r["id"] == dish_id)
    assert row["category_key"] == "platos_a_la_carta" and row["category_label"] == "PLATOS A LA CARTA"


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def test_hospitality_carta_photo_is_cropped_to_the_standard_frame(api):
    from PIL import Image
    import io as _io

    for size in ((1200, 400), (500, 900), (3000, 2250)):
        res = client.post(f"/api/v1/carta/companies/{ASADERO}/items/{POLLO_ASADO}/photo", headers={"Authorization": "Bearer admin"},
                          files={"image": ("foto.png", _png(*size), "image/png")})
        assert res.status_code == 200, res.text
        stored = Image.open(_io.BytesIO(api.image_bytes[POLLO_ASADO]))
        assert stored.size == carta_endpoint.PHOTO_FRAME == (800, 600) and stored.format == "JPEG", size
    assert len(api.image_bytes[POLLO_ASADO]) <= 200 * 1024
    bad = client.post(f"/api/v1/carta/companies/{ASADERO}/items/{POLLO_ASADO}/photo", headers={"Authorization": "Bearer admin"},
                      files={"image": ("x.png", b"no es una imagen", "image/png")})
    assert bad.status_code == 422


def test_hospitality_carta_combo_deducts_its_parts_not_its_own_stock(api):
    combo = call("POST", ASADERO, "/items", "admin", {"name": "Combo Socio", "price": 45000, "kind": "combo",
                                                        "category_key": "POLLO"}).json()["created_id"]
    res = call("PUT", ASADERO, f"/items/{combo}/recipe", "admin",
               {"lines": [{"component_item_id": POLLO_ASADO, "quantity": 1}, {"component_item_id": CERVEZA_PLATO, "quantity": 2}]})
    assert res.status_code == 200, res.text
    dish = next(i for i in res.json()["items"] if i["id"] == combo)
    assert dish["kind"] == "combo" and dish["inventory_item_id"] is None, "sin existencia propia"
    assert dish["cost"] == 7390 + 2 * 3000 and dish["available"] is True
    assert [l["insumo"] for l in dish["recipe"]] == ["POLLO Asado 500 gr", "Cerveza"]

    rows = asyncio_run(hospitality._build_order_items(api, uuid.UUID(ASADERO), [item_in(combo, 1, "Combo Socio", 45000)]))
    assert {c["inventory_item_id"]: c["quantity"] for c in rows[0]["consumption"]} == {
        POLLO_CRUDO: 500.0, PAPA: 300.0, ACEITE: 30.0, CERVEZA: 2.0}
    asyncio_run(hospitality._deduct_inventory(api, uuid.UUID(ASADERO), {"id": "c1", "items": rows}))
    assert api.inventory[POLLO_CRUDO]["current_stock"] == Decimal("4500") and api.inventory[CERVEZA]["current_stock"] == Decimal("0")

    nested = call("PUT", ASADERO, f"/items/{POLLO_ASADO}/recipe", "admin", {"lines": [{"component_item_id": CERVEZA_PLATO, "quantity": 1}]})
    assert nested.status_code == 400 and "combo" in nested.text, "solo un combo lleva otros platos"
    inner = call("POST", ASADERO, "/items", "admin", {"name": "Combo 2", "price": 1, "kind": "combo"}).json()["created_id"]
    combo_in_combo = call("PUT", ASADERO, f"/items/{inner}/recipe", "admin", {"lines": [{"component_item_id": combo, "quantity": 1}]})
    assert combo_in_combo.status_code == 400
    in_use = call("DELETE", ASADERO, f"/items/{POLLO_ASADO}", "admin")
    assert in_use.status_code == 409 and "Combo Socio" in in_use.text


def test_hospitality_carta_delete_dish_removes_it_and_its_photo(api):
    dish_id = call("POST", ASADERO, "/items", "admin", {"name": "Salchipapa", "price": 12000, "kind": "preparado"}).json()["created_id"]
    client.post(f"/api/v1/carta/companies/{ASADERO}/items/{dish_id}/photo", headers={"Authorization": "Bearer admin"},
                files={"image": ("foto.png", _png(900, 600), "image/png")})
    assert dish_id in api.images
    res = call("DELETE", ASADERO, f"/items/{dish_id}", "admin")
    assert res.status_code == 200 and dish_id not in [i["id"] for i in res.json()["items"]]
    assert dish_id not in api.images, "no quedan bytes huerfanos en la base"
    assert call("DELETE", ASADERO, f"/items/{dish_id}", "admin").status_code == 404


def test_hospitality_carta_qr_opens_the_right_carta_and_never_costs(api, monkeypatch):
    from app.api.v1.endpoints import waiter_ordering

    seen = []

    async def fake_menu(_db, company_id):
        seen.append(str(company_id))
        return {"menu_emojis": False, "categories": [
            {"key": "pollo", "label": "POLLO", "has_image": False, "station": "parrilla", "products": [
                {"id": POLLO_ASADO, "name": "POLLO Asado 500 gr", "price": 40000, "has_image": True, "cost": 7390, "stock": 12,
                 "is_portioned": False, "portions": []}]},
            {"key": "vacia", "label": "VACIA", "products": []}]}

    monkeypatch.setattr(waiter_ordering, "build_waiter_menu", fake_menu)
    info = call("GET", ASADERO, "/qr", "admin").json()
    assert "/carta-qr?t=" in info["url"]
    token = info["url"].split("t=")[1]
    assert call("GET", ASADERO, "/qr", "admin").json()["url"] == info["url"], "el mismo QR hasta que se cambie"
    png = call("GET", ASADERO, "/qr.png", "admin")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n" and "qr_carta.png" in png.headers["content-disposition"]

    public = client.get(f"/api/v1/carta/public/{token}")
    assert public.status_code == 200 and seen == [ASADERO]
    body = public.json()
    assert body["company_name"] == "ASADERO EL SOCIO" and [c["label"] for c in body["categories"]] == ["POLLO"]
    assert "cost" not in public.text and "stock" not in public.text, "el cliente nunca ve costos ni existencias"
    assert client.get("/api/v1/carta/public/codigo-inventado-que-no-existe-123").status_code == 404
    assert client.get("/api/v1/carta/public/corto").status_code == 404

    new = call("POST", ASADERO, "/qr/regenerate", "admin").json()["url"]
    assert new != info["url"] and client.get(f"/api/v1/carta/public/{token}").status_code == 404, "el QR viejo deja de servir"
    page = client.get("/carta-qr")
    assert page.status_code == 200 and "carta_qr.js" in page.text


def test_hospitality_carta_wizard_migration_is_short_and_only_touches_carta_tables():
    spec = importlib.util.spec_from_file_location("mig_021y", ROOT / "migrations/versions/021y_carta_wizard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "021x_costos_module"
    source = (ROOT / "migrations/versions/021y_carta_wizard.py").read_text(encoding="utf-8")
    touched = {line.split("TABLE ")[1].split()[0] for line in source.splitlines() if "ALTER TABLE" in line}
    assert touched == {"carta_items", "carta_recipe_lines"}


def test_hospitality_carta_other_companies_keep_their_menu_categories():
    from app.api.v1.endpoints import waiter_ordering

    source = (ROOT / "app/api/v1/endpoints/waiter_ordering.py").read_text(encoding="utf-8")
    # sin category_key (todas las empresas sin Carta) la categoria sigue saliendo del nombre
    assert 'key = product.get("category_key") or _category_key(product.get("name"))' in source
    assert waiter_ordering._category_key("Club Colombia") == "club"
