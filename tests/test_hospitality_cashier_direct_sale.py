"""Caja: facturacion directa (switch cashier_direct_sale, off by default).

Runs through Hospitality's REAL transitions and close-table, and the REAL
kitchen board, on the in-memory hospitality_orders fake from the kitchen
columns tests. Only order insertion and inventory I/O are faked.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import hospitality, waiter_ordering
from tests.test_hospitality_waiter_kitchen_columns import COMPANY_ID, FakeOrdersDb, install_fake_orders


CATALOG = [
    {"id": "carne", "name": "CARNE Asada", "price": 25000, "active": True},
    {"id": "gaseosa", "name": "GASEOSA Postobon", "price": 4000, "active": True},
]


class SaleDb(FakeOrdersDb):
    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if "jsonb_build_object('cashier_sale'" in sql:
            row = self.rows[params["order_id"]]
            row["metadata"]["cashier_sale"] = json.loads(params["sale"])
            row["table_number"] = params["label"]
            row["table_key"] = params["table_key"]
            return self._result(rowcount=1)
        return await super().execute(stmt, params)


@pytest.fixture
def db(monkeypatch):
    fake = install_fake_orders(monkeypatch, SaleDb())
    counter = {"n": 0}

    async def create_order(company_id, payload, _db):
        counter["n"] += 1
        order_id = fake.add(table=payload.table, status="pendiente")
        row = fake.rows[str(order_id)]
        row["order_number"] = f"QR-20260923-{counter['n']:03d}"
        row["items"] = [
            {"id": f"line_{i}", "name": item.name, "quantity": item.quantity, "unit_price": item.unit_price,
             "subtotal": item.quantity * item.unit_price, "station": item.station}
            for i, item in enumerate(payload.items)
        ]
        row["total"] = sum(i["subtotal"] for i in row["items"])
        row["metadata"] = {"waiter": {"id": payload.waiter_id, "name": payload.waiter_name}}
        return {"ok": True, "order": fake.payload(order_id)}

    monkeypatch.setattr(waiter_ordering, "create_hospitality_order", create_order)
    monkeypatch.setattr(waiter_ordering, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": [dict(p) for p in CATALOG]}))
    monkeypatch.setattr(waiter_ordering, "_category_rows", AsyncMock(return_value={}))
    monkeypatch.setattr(waiter_ordering, "_portion_membership", AsyncMock(return_value={}))
    monkeypatch.setattr(
        waiter_ordering, "_module_settings",
        AsyncMock(return_value={"cashier_direct_sale": True, "kitchen_board_columns": True}),
    )
    return fake


def _caja():
    return SimpleNamespace(id=uuid.uuid4(), full_name="Caja Uno", role="caja", settings_json={})


def _cook():
    return SimpleNamespace(id=uuid.uuid4(), full_name="Pedro", role="cocina", settings_json={})


def _sale(**kwargs):
    kwargs.setdefault("items", [waiter_ordering.WaiterOrderItemIn(inventory_item_id="gaseosa", quantity=2)])
    return waiter_ordering.CashierSaleIn(**kwargs)


async def _board(db):
    return await waiter_ordering.waiter_ordering_kitchen_board(COMPANY_ID, db=db, user=_cook())


@pytest.mark.asyncio
async def test_independent_sale_without_kitchen_is_charged_on_the_spot(db):
    result = await waiter_ordering.create_cashier_sale(
        COMPANY_ID, _sale(payment_method="cash"), db=db, user=_caja(),
    )
    assert result["charged"] is True
    assert result["label"] == "Venta 001"
    row = db.rows[result["order"]["id"]]
    assert row["status"] == "cerrado"
    assert row["table_number"] == "Venta 001"
    assert row["metadata"]["cashier_sale"]["kind"] == "independiente"
    assert row["total"] == 8000                      # server price x 2
    board = await _board(db)
    assert board["counts"] == {"nuevo": 0, "preparando": 0, "listo": 0}


@pytest.mark.asyncio
async def test_independent_sale_needs_a_valid_payment_method_before_anything_is_created(db):
    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.create_cashier_sale(COMPANY_ID, _sale(payment_method=None), db=db, user=_caja())
    assert exc.value.status_code == 422
    assert db.rows == {}


@pytest.mark.asyncio
async def test_independent_sale_sent_to_kitchen_waits_in_pedido_nuevo_then_is_charged(db):
    cook = _cook()
    result = await waiter_ordering.create_cashier_sale(
        COMPANY_ID, _sale(send_to_kitchen=True, items=[waiter_ordering.WaiterOrderItemIn(inventory_item_id="carne", quantity=1)]),
        db=db, user=_caja(),
    )
    order_id = uuid.UUID(result["order"]["id"])
    assert result["charged"] is False
    assert db.rows[str(order_id)]["status"] == "pendiente"
    board = await _board(db)
    assert [c["table_number"] for c in board["columns"]["nuevo"]] == ["Venta 001"]

    # Not chargeable until the kitchen finishes it...
    with pytest.raises(HTTPException):
        await hospitality.close_hospitality_order(COMPANY_ID, order_id, hospitality.HospitalityCloseIn(payment_method="cash"), db=db)
    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)
    closed = await hospitality.close_hospitality_order(COMPANY_ID, order_id, hospitality.HospitalityCloseIn(payment_method="card"), db=db)
    assert closed["order"]["status"] == "cerrado"


@pytest.mark.asyncio
async def test_adding_to_a_table_without_kitchen_is_ready_to_charge_with_the_table(db):
    result = await waiter_ordering.create_cashier_sale(COMPANY_ID, _sale(table="Mesa 3"), db=db, user=_caja())
    row = db.rows[result["order"]["id"]]
    assert row["status"] == "entregado"               # joins the table's bill, not charged yet
    assert row["table_number"] == "Mesa 3"
    assert row["metadata"]["cashier_sale"]["kind"] == "mesa"
    assert result["charged"] is False
    assert (await _board(db))["counts"]["nuevo"] == 0


@pytest.mark.asyncio
async def test_adding_to_a_table_through_the_kitchen_shows_on_the_board(db):
    result = await waiter_ordering.create_cashier_sale(
        COMPANY_ID, _sale(table="Mesa 3", send_to_kitchen=True), db=db, user=_caja(),
    )
    assert db.rows[result["order"]["id"]]["status"] == "pendiente"
    assert [c["table_number"] for c in (await _board(db))["columns"]["nuevo"]] == ["Mesa 3"]


@pytest.mark.asyncio
async def test_sale_rejects_a_product_outside_the_catalog(db):
    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.create_cashier_sale(
            COMPANY_ID, _sale(items=[waiter_ordering.WaiterOrderItemIn(inventory_item_id="ghost", quantity=1)], payment_method="cash"),
            db=db, user=_caja(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_direct_sale_is_off_without_the_company_switch(db, monkeypatch):
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value={}))
    # Domicilios por WhatsApp off too: the caja config reports it.
    monkeypatch.setattr(waiter_ordering.whatsapp_delivery, "module_settings", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.create_cashier_sale(COMPANY_ID, _sale(payment_method="cash"), db=db, user=_caja())
    assert exc.value.status_code == 404
    config = await waiter_ordering.cashier_config(COMPANY_ID, db=db, _user=_caja())
    assert config["direct_sale"] is False and config["delivery"] is False


def test_empty_sale_is_rejected():
    with pytest.raises(Exception):
        waiter_ordering.CashierSaleIn(items=[])


def test_sale_endpoints_require_a_caja_session():
    from fastapi.params import Depends as DependsParam
    import inspect

    for endpoint in (waiter_ordering.create_cashier_sale, waiter_ordering.cashier_config):
        deps = [p.default.dependency for p in inspect.signature(endpoint).parameters.values() if isinstance(p.default, DependsParam)]
        assert waiter_ordering._require_caja in deps, endpoint.__name__
