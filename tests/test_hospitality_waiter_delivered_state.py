"""Mesero "Mis mesas": when the kitchen marks the comanda Entregado the
table shows as delivered (check, nothing left to do for the mesero) while it
stays open for the caja, and it disappears once the caja charges it.
Runs the real kitchen and close-table code on the orders fake."""
from __future__ import annotations

from types import SimpleNamespace
import uuid

import pytest

from app.api.v1.endpoints import hospitality, waiter_ordering
from tests.test_hospitality_waiter_kitchen_columns import COMPANY_ID, install_fake_orders


@pytest.fixture
def db(monkeypatch):
    return install_fake_orders(monkeypatch)


def _person(role, name):
    return SimpleNamespace(id=uuid.uuid4(), full_name=name, role=role, settings_json={})


async def _my_tables(db, mesero):
    return {t["table_number"]: t["status"] for t in (await waiter_ordering.waiter_my_tables(COMPANY_ID, db=db, user=mesero))["tables"]}


@pytest.mark.asyncio
async def test_the_mesero_sees_sent_ready_then_delivered_and_then_it_is_gone(db):
    mesero, cook = _person("mesero", "Laura"), _person("cocina", "Pedro")
    order_id = db.add(table="Mesa 7", waiter=mesero)

    assert await _my_tables(db, mesero) == {"Mesa 7": "enviado_a_cocina"}
    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)
    assert await _my_tables(db, mesero) == {"Mesa 7": "listo_para_llevar"}
    await waiter_ordering.mark_waiter_order_delivered(COMPANY_ID, order_id, db=db, user=cook)
    assert await _my_tables(db, mesero) == {"Mesa 7": "entregada"}      # check: nothing left to do

    # still open for the caja until it is charged
    assert db.rows[str(order_id)]["status"] == "entregado"
    await hospitality.close_hospitality_order(COMPANY_ID, order_id, hospitality.HospitalityCloseIn(payment_method="cash"), db=db)
    assert await _my_tables(db, mesero) == {}


@pytest.mark.asyncio
async def test_a_table_is_delivered_only_when_every_comanda_is(db):
    mesero, cook = _person("mesero", "Laura"), _person("cocina", "Pedro")
    first = db.add(table="Mesa 4", waiter=mesero)
    second = db.add(table="Mesa 4", waiter=mesero)
    for order_id in (first, second):
        await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)
    await waiter_ordering.mark_waiter_order_delivered(COMPANY_ID, first, db=db, user=cook)
    assert await _my_tables(db, mesero) == {"Mesa 4": "listo_para_llevar"}
    await waiter_ordering.mark_waiter_order_delivered(COMPANY_ID, second, db=db, user=cook)
    assert await _my_tables(db, mesero) == {"Mesa 4": "entregada"}


def test_status_rules():
    delivered = {"status": "entregado", "metadata": {"kitchen": {"ready_at": "t", "delivered_at": "t"}}}
    ready = {"status": "entregado", "metadata": {"kitchen": {"ready_at": "t"}}}
    pending = {"status": "alistando", "metadata": {}}
    assert waiter_ordering._my_table_status([delivered]) == "entregada"
    assert waiter_ordering._my_table_status([delivered, ready]) == "listo_para_llevar"
    assert waiter_ordering._my_table_status([delivered, pending]) == "enviado_a_cocina"
