"""049Z: Reportes ve las ventas de hoy, de extremo a extremo.

Regresion: Reportes no mostraba las ventas de hoy ni de ayer aunque el panel
de caja y el Z si. Mismo origen que el Z en $0 (049W): sin horario de
jornada, Reportes fechaba todo lo que no tenia "cierre de dia" de
hospitality con el pedido MAS ANTIGUO, y el Asadero cierra con el Z. Ahora
Reportes, el panel de caja y el Z leen la venta de una sola forma
(app/services/sales_ledger.py, interruptor sales_ledger).

Se cobran por los flujos reales una mesa, una venta directa de caja y un
domicilio (con un pedido viejo sin cierre diario, el que rompia todo), y las
tres ventas deben aparecer en el reporte de HOY con su valor, cuadrando con
lo cobrado en el panel de caja.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from app.api.v1.endpoints import cash_count, hospitality
from app.api.v1.endpoints import hospitality_owner_report as owner
from app.api.v1.endpoints import waiter_ordering as wo
from app.services import owner_report, sales_ledger
from tests.test_hospitality_cashier_z_matches_panel import CATALOG, CajaDb, _sale
from tests.test_hospitality_waiter_kitchen_columns import COMPANY_ID, install_fake_orders

TZ = ZoneInfo("America/Bogota")


@pytest.fixture
def db(monkeypatch):
    fake = install_fake_orders(monkeypatch, CajaDb())
    counter = {"n": 0}

    async def create_order(company_id, payload, _db):
        counter["n"] += 1
        order_id = fake.add(table=payload.table, status="pendiente", created_minutes_ago=0)
        row = fake.rows[str(order_id)]
        row["order_number"] = f"QR-{counter['n']:05d}"
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
    monkeypatch.setattr(cash_count, "open_cashier_session", AsyncMock(return_value=None))
    monkeypatch.setattr(wo, "_company_clock", AsyncMock(return_value=("America/Bogota", TZ, None, datetime.now(TZ).date())))
    # Reportes: sin horario de jornada (como el Asadero) y sin inventario.
    monkeypatch.setattr(owner, "_hsp_company_report_settings", AsyncMock(return_value=("America/Bogota", None)))
    monkeypatch.setattr(owner, "_inventory_and_portions", AsyncMock(return_value=({}, {})))
    return fake


def _caja():
    return SimpleNamespace(id=uuid.uuid4(), full_name="Caja Uno", role="caja", settings_json={})


async def _charge_one_of_each(db):
    user = _caja()
    # 1. Venta directa de caja, cobrada en el momento: 42.000
    await wo.create_cashier_sale(COMPANY_ID, _sale([("pollo", 1)], "cash"), db=db, user=user)
    # 2. Mesa del mesero, cobrada desde la caja: 75.000 (abierta hace 40 min)
    mesa = db.add(table="Mesa 7", status="entregado", created_minutes_ago=40)
    db.rows[str(mesa)]["total"] = 75000
    await hospitality.close_hospitality_order(COMPANY_ID, mesa, hospitality.HospitalityCloseIn(payment_method="card"), db=db)
    # 3. Domicilio contra entrega, cobrado al volver el domiciliario: 33.000
    dom = db.add(table="Domicilio 4F2A", status="entregado", created_minutes_ago=50)
    row = db.rows[str(dom)]
    row.update(order_type="domicilio", source="domicilio", total=33000,
               metadata={"delivery": {"payment_method": "cash", "payment_status": "contra_entrega"}})
    await hospitality.close_hospitality_order(COMPANY_ID, dom, hospitality.HospitalityCloseIn(payment_method="cash"), db=db)
    return user


def _with_old_unclosed_order(db):
    """Un pedido de hace 3 dias sin "cierre de dia": el que mandaba todo lo
    de hoy a la jornada de ese dia."""
    old = db.add(table="Mesa 9", status="entregado", created_minutes_ago=60 * 72)
    db.rows[str(old)]["total"] = 18000


@pytest.mark.asyncio
async def test_hospitality_report_today_shows_table_cashier_and_delivery_sales(db, monkeypatch):
    monkeypatch.setattr(sales_ledger, "enabled", AsyncMock(return_value=True))
    _with_old_unclosed_order(db)
    user = await _charge_one_of_each(db)

    live = await owner._live(db, COMPANY_ID)
    assert live["has_sales"] is True
    # Las tres ventas cobradas + la mesa vieja que sigue abierta NO es de hoy.
    assert live["sales"] == 42000 + 75000 + 33000
    assert live["orders"] == 3

    # Canal por canal, con su valor.
    now = datetime.now(timezone.utc)
    orders = await sales_ledger.load_orders(db, COMPANY_ID, now - timedelta(days=8), now + timedelta(days=1))
    report = owner_report.Report(orders=orders, closures=[], inventory={}, portions={}, tz=TZ,
                                 period=owner_report.today_period(datetime.now(TZ).date()), by_charge=True)
    by_channel = {}
    for order in report.sales:
        by_channel[owner_report.channel_of(order)] = by_channel.get(owner_report.channel_of(order), 0) + float(order["total"])
    assert by_channel == {"venta_directa": 42000.0, "mesa": 75000.0, "domicilio": 33000.0}

    # La misma cifra que el panel de caja muestra como cobrado.
    panel = await wo.cashier_shift_summary(COMPANY_ID, db=db, user=user)
    assert panel["charged"] == live["sales"]


@pytest.mark.asyncio
async def test_hospitality_report_old_rule_reproduces_the_empty_report(db, monkeypatch):
    """Documenta la causa: con la regla vieja (sin el interruptor) el mismo
    escenario deja HOY vacio."""
    monkeypatch.setattr(sales_ledger, "enabled", AsyncMock(return_value=False))
    _with_old_unclosed_order(db)
    await _charge_one_of_each(db)
    original = db.execute

    async def execute(stmt, params=None):
        sql = " ".join(str(stmt).split())
        if "FROM hospitality_orders WHERE company_id = CAST(:company_id AS uuid) AND created_at >= :start" in sql:
            rows = [dict(r) for r in db.rows.values() if params["start"] <= r["created_at"] < params["end"]]
            return db._result(rows)
        if "FROM hospitality_day_closures" in sql or "SELECT id, created_at FROM hospitality_orders" in sql:
            return db._result([])
        return await original(stmt, params)

    db.execute = execute
    live = await owner._live(db, COMPANY_ID)
    assert live["sales"] == 0, "la regla vieja fecha las ventas de hoy en la jornada del pedido viejo"


@pytest.mark.asyncio
async def test_hospitality_report_sale_counts_on_the_day_it_was_charged(db, monkeypatch):
    """Una mesa abierta ayer y cobrada hoy es venta de HOY (se leen los
    pedidos creados o cobrados en la ventana)."""
    monkeypatch.setattr(sales_ledger, "enabled", AsyncMock(return_value=True))
    yesterday_table = db.add(table="Mesa 3", status="entregado", created_minutes_ago=60 * 26)
    db.rows[str(yesterday_table)]["total"] = 51000
    await hospitality.close_hospitality_order(COMPANY_ID, yesterday_table, hospitality.HospitalityCloseIn(payment_method="cash"), db=db)
    live = await owner._live(db, COMPANY_ID)
    assert live["sales"] == 51000


def test_hospitality_sales_ledger_rules():
    now = datetime(2026, 9, 30, 20, 0, tzinfo=timezone.utc)
    paid = {"status": "cerrado", "created_at": now - timedelta(days=1), "closed_at": now}
    open_ = {"status": "entregado", "created_at": now, "closed_at": None}
    cancelled = {"status": "cancelado", "created_at": now}
    assert sales_ledger.is_paid(paid) and not sales_ledger.is_paid(open_)
    assert sales_ledger.is_sale(open_) and not sales_ledger.is_sale(cancelled)
    assert sales_ledger.sale_moment(paid) == now and sales_ledger.sale_moment(open_) == now
    assert sales_ledger.sale_day(paid, TZ) == now.astimezone(TZ).date()
    overnight = {"overnight": True, "close": datetime(2026, 1, 1, 4, 0).time()}
    at_2am = {"status": "cerrado", "created_at": now, "closed_at": datetime(2026, 10, 1, 7, 0, tzinfo=timezone.utc)}  # 02:00 Bogota
    assert str(sales_ledger.sale_day(at_2am, TZ, overnight)) == "2026-09-30", "de madrugada: jornada anterior"
    # El Z, los indicadores y Reportes usan las mismas reglas.
    from app.services import cashier_summary

    assert cashier_summary.is_paid is not None and cashier_summary.is_paid(paid) is True
    assert owner_report.is_cancelled(cancelled) is True
