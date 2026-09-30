"""049W: el Z suma exactamente las ventas que el panel de caja muestra como
cobradas. Regresion del Z en $0: se cobran ventas reales por el flujo de la
caja (efectivo, transferencia, tarjeta y una mesa) y el Z debe reflejarlas y
cuadrar con los indicadores, aunque quede un pedido de ayer sin cierre diario
(lo que antes mandaba todo lo de hoy a la "jornada" de ayer)."""
from __future__ import annotations

import copy
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from app.api.v1.endpoints import cash_count, hospitality, waiter_ordering as wo
from app.services import owner_report
from tests.test_hospitality_cashier_direct_sale import SaleDb
from tests.test_hospitality_waiter_kitchen_columns import COMPANY_ID, install_fake_orders

TZ = ZoneInfo("America/Bogota")
CATALOG = [
    {"id": "pollo", "name": "POLLO Asado", "price": 42000, "active": True},
    {"id": "gaseosa", "name": "GASEOSA Coca Cola", "price": 4500, "active": True},
    {"id": "carne", "name": "CARNE Asada", "price": 28000, "active": True},
]


class CajaDb(SaleDb):
    """El fake de pedidos + lo que leen/escriben los indicadores y el Z."""

    def __init__(self):
        super().__init__()
        self.z_rows = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        if "SET status = 'cerrado'" in sql and "payment_method = :payment_method" in sql:
            row = self.rows.get(str(params.get("order_id")))
            if row and row["company_id"] == str(params.get("company_id")):
                row.update(status="cerrado", payment_method=params["payment_method"],
                           closed_at=row.get("closed_at") or datetime.now(timezone.utc))
            return self._result(rowcount=1 if row else 0)
        if "FROM hospitality_orders" in sql and "OR (closed_at >= :start" in sql:  # sales_ledger.load_orders
            end = params.get("end")

            def inside(moment):
                return bool(moment) and moment >= params["start"] and (end is None or moment < end)

            rows = [copy.deepcopy(r) for r in self.rows.values()
                    if r["company_id"] == str(params["company_id"])
                    and (inside(r["created_at"]) or inside(r.get("closed_at")))]
            return self._result(rows)
        if "INSERT INTO cashier_z_reports" in sql:
            row = {"id": params["id"], "number": len(self.z_rows) + 1, "business_day": params["day"],
                   "cashier_name": params["cashier_name"], "total": params["total"],
                   "summary": json.loads(params["summary"]), "created_at": datetime.now(timezone.utc)}
            self.z_rows.append(row)
            return self._result([row])
        if "FROM cashier_z_reports" in sql:
            return self._result([])
        if "FROM companies" in sql:
            return self._result([{"name": "ASADERO EL SOCIO"}])
        if "jsonb_build_object('closed_by'" in sql:
            return self._result(rowcount=1)
        return await super().execute(stmt, params)


@pytest.fixture
def db(monkeypatch):
    fake = install_fake_orders(monkeypatch, CajaDb())
    counter = {"n": 0}

    async def create_order(company_id, payload, _db):
        counter["n"] += 1
        order_id = fake.add(table=payload.table, status="pendiente", created_minutes_ago=0)
        row = fake.rows[str(order_id)]
        row["order_number"] = f"QR-20260929-{counter['n']:05d}"
        row["items"] = [{"id": f"l{i}", "name": it.name, "quantity": it.quantity, "unit_price": it.unit_price,
                         "subtotal": it.quantity * it.unit_price, "station": it.station} for i, it in enumerate(payload.items)]
        row["total"] = sum(i["subtotal"] for i in row["items"])
        row["metadata"] = {"waiter": {"id": payload.waiter_id, "name": payload.waiter_name}}
        return {"ok": True, "order": fake.payload(order_id)}

    monkeypatch.setattr(wo, "create_hospitality_order", create_order)
    monkeypatch.setattr(wo, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": [dict(p) for p in CATALOG]}))
    monkeypatch.setattr(wo, "_category_rows", AsyncMock(return_value={}))
    monkeypatch.setattr(wo, "_portion_membership", AsyncMock(return_value={}))
    monkeypatch.setattr(wo, "_module_settings", AsyncMock(return_value={"cashier_direct_sale": True, "cashier_redesign": True}))
    monkeypatch.setattr(cash_count, "cash_count_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(wo, "_company_clock", AsyncMock(return_value=("America/Bogota", TZ, None, datetime.now(TZ).date())))
    return fake


def _caja():
    return SimpleNamespace(id=uuid.uuid4(), full_name="Caja Uno", role="caja", settings_json={})


def _sale(items, method):
    return wo.CashierSaleIn(items=[wo.WaiterOrderItemIn(inventory_item_id=i, quantity=q) for i, q in items], payment_method=method)


async def _charge_everything(db, user):
    # Tres ventas directas cobradas en el momento, cada una con su metodo.
    await wo.create_cashier_sale(COMPANY_ID, _sale([("pollo", 1)], "cash"), db=db, user=user)            # 42.000
    await wo.create_cashier_sale(COMPANY_ID, _sale([("gaseosa", 2)], "transfer"), db=db, user=user)      # 9.000
    await wo.create_cashier_sale(COMPANY_ID, _sale([("carne", 1), ("gaseosa", 1)], "card"), db=db, user=user)  # 32.500
    await wo.create_cashier_sale(COMPANY_ID, _sale([("carne", 1)], "cash"), db=db, user=user)            # 28.000
    # Una mesa del mesero, cobrada con tarjeta desde la caja.
    mesa = db.add(table="Mesa 7", status="entregado", created_minutes_ago=30)
    db.rows[str(mesa)]["total"] = 75000
    await hospitality.close_hospitality_order(COMPANY_ID, mesa, hospitality.HospitalityCloseIn(payment_method="card"), db=db)
    # Una mesa aun abierta: por cobrar, no entra en el Z.
    abierta = db.add(table="Mesa 2", status="entregado", created_minutes_ago=10)
    db.rows[str(abierta)]["total"] = 46000


@pytest.mark.asyncio
@pytest.mark.parametrize("shift_open", [True, False])
async def test_hospitality_z_reflects_the_sales_the_panel_shows_as_charged(db, monkeypatch, shift_open):
    user = _caja()
    started = datetime.now(timezone.utc) - timedelta(hours=3)
    monkeypatch.setattr(cash_count, "open_cashier_session",
                        AsyncMock(return_value={"id": "s1", "started_at": started} if shift_open else None))
    # El pedido de ayer que nunca tuvo cierre diario (el que rompia el Z).
    old = db.add(table="Mesa 9", status="entregado", created_minutes_ago=60 * 30)
    await _charge_everything(db, user)

    panel = await wo.cashier_shift_summary(COMPANY_ID, db=db, user=user)
    preview = await wo.cashier_z_preview(COMPANY_ID, db=db, user=user)
    saved = await wo.cashier_z_register(COMPANY_ID, db=db, user=user)

    expected = {"cash": 70000.0, "transfer": 9000.0, "card": 107500.0}
    for z in (preview["z"], saved["summary"]):
        assert z["total"] == 186500.0
        assert {m["method"]: m["total"] for m in z["methods"]} == expected
        assert {m["method"]: m["count"] for m in z["methods"]} == {"cash": 2, "transfer": 1, "card": 2}
        assert z["sales"] == 5 and z["orders"] == 5
        assert z["products"] == 7.0                              # 1 + 2 + 1 + 1 + 1 carne + la mesa (1 linea)
        assert (z["open_count"], z["open_total"]) == (1, 46000.0)
        # Cuadra con lo que el panel muestra como cobrado, metodo por metodo.
        assert z["total"] == panel["charged"]
        assert {m["method"]: m["total"] for m in z["methods"]} == {m["method"]: m["total"] for m in panel["methods"]}
    paid_sales = [r for r in panel["direct_sales"] if r["paid"]]
    assert sorted(r["total"] for r in paid_sales) == [9000.0, 28000.0, 32500.0, 42000.0]
    assert sum(r["total"] for r in paid_sales) + 75000 == saved["summary"]["total"]
    assert saved["total"] == 186500.0 and len(db.z_rows) == 1
    assert str(old) not in {str(r["id"]) for r in panel["direct_sales"]}


@pytest.mark.asyncio
async def test_hospitality_old_jornada_rule_explains_the_zero_z(db, monkeypatch):
    """Documenta la causa: con un pedido de ayer sin cierre diario, la regla de
    jornada de Reportes fecha las ventas de hoy en la jornada de ayer."""
    monkeypatch.setattr(cash_count, "open_cashier_session", AsyncMock(return_value=None))
    db.add(table="Mesa 9", status="entregado", created_minutes_ago=60 * 30)
    await _charge_everything(db, _caja())
    orders = list(db.rows.values())
    resolve = owner_report.jornada_resolver(orders, [], TZ, None)
    today = datetime.now(TZ).date()
    assert all(resolve(o) != today for o in orders)          # la regla vieja: nada es "de hoy"
    z = (await wo.cashier_z_preview(COMPANY_ID, db=db, user=_caja()))["z"]
    assert z["total"] == 186500.0                              # la ventana de la caja: si
