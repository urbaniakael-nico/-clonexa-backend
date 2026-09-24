"""Cuentas por persona en la mesa QR (servidor), con los mismos pedidos que
tests/hospitality_qr_bar_accounts.test.cjs: dos teléfonos (account_id
distintos) piden desde la misma mesa; cada uno ve su cuenta, la mesa suma
ambas y el cierre cobra el total.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import hospitality


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class OrdersDb:
    """In-memory hospitality_orders for one company (only the SQL these
    endpoints run)."""

    def __init__(self, company_id):
        self.company_id = str(company_id)
        self.orders: list[dict] = []
        self.commit = AsyncMock()

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = params or {}
        if sql.startswith("INSERT INTO hospitality_orders"):
            assert params["company_id"] == self.company_id
            now = datetime.now(timezone.utc)
            row = {
                "id": uuid.uuid4(),
                "company_id": params["company_id"],
                "order_number": params["order_number"],
                "table_number": params["table_number"],
                "table_key": params["table_key"],
                "source": params["source"],
                "status": "pendiente",
                "customer_name": params["customer_name"],
                "people": json.loads(params["people"]),
                "items": json.loads(params["items"]),
                "metadata": json.loads(params["metadata"]),
                "total": params["total"],
                "payment_method": params["payment_method"],
                "created_at": now,
                "updated_at": now,
            }
            self.orders.append(row)
            return _Rows([row])
        if sql.startswith("UPDATE hospitality_orders SET inventory_deducted"):
            return _Rows([])
        if sql.startswith("SELECT * FROM hospitality_orders WHERE company_id = :company_id AND table_key = :table_key"):
            assert "status IN ('pendiente', 'alistando', 'entregado')" in sql
            rows = [
                o for o in self.orders
                if o["company_id"] == params["company_id"]
                and o["table_key"] == params["table_key"]
                and o["status"] in ("pendiente", "alistando", "entregado")
            ]
            return _Rows(rows)
        if sql.startswith("UPDATE hospitality_orders SET status = 'cerrado'"):
            assert "AND company_id = :company_id" in sql
            for o in self.orders:
                if str(o["id"]) == params["order_id"] and o["company_id"] == params["company_id"]:
                    o["status"] = "cerrado"
                    o["payment_method"] = params["payment_method"]
            return _Rows([])
        raise AssertionError(f"SQL no esperado en la prueba: {sql[:120]}")


def _install(monkeypatch, db):
    async def build_items(_db, _company_id, items):
        return [
            {
                "inventory_item_id": item.inventory_item_id,
                "name": item.name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.quantity * item.unit_price,
            }
            for item in items
        ]

    async def fetch_order(_db, company_id, order_id):
        return next(o for o in db.orders if str(o["id"]) == str(order_id) and o["company_id"] == str(company_id))

    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(hospitality, "_require_table_access", AsyncMock())
    monkeypatch.setattr(hospitality, "_build_order_items", build_items)
    counter = iter(range(1, 100))
    monkeypatch.setattr(hospitality, "_next_order_number", AsyncMock(side_effect=lambda *_: f"QR-{next(counter)}"))
    monkeypatch.setattr(hospitality, "_deduct_inventory", AsyncMock())
    monkeypatch.setattr(hospitality, "_fetch_order", fetch_order)
    monkeypatch.setattr(hospitality, "_close_table_access_if_idle", AsyncMock())


async def _order(db, company_id, account_id, customer, items):
    return await hospitality.create_hospitality_order(
        company_id,
        hospitality.HospitalityOrderCreateIn(
            table="Mesa 5",
            customer=customer,
            source="qr",
            access_code="MESA5",
            account_id=account_id,
            items=[
                hospitality.HospitalityOrderItemIn(inventory_item_id=i, product_id=i, name=n, quantity=q, unit_price=p)
                for i, n, q, p in items
            ],
        ),
        db,
    )


async def _account(db, company_id, account_id):
    response = await hospitality.get_hospitality_table_account(
        company_id,
        hospitality.HospitalityTableAccessVerifyIn(table="Mesa 5", access_code="MESA5", account_id=account_id),
        db,
    )
    return response["account"]


@pytest.mark.asyncio
async def test_hospitality_two_phones_same_table_keep_separate_accounts_and_close_the_total(monkeypatch):
    company_id = uuid.uuid4()
    db = OrdersDb(company_id)
    _install(monkeypatch, db)
    laura, nico = "qr_account_laura-phone", "qr_account_nico-phone"

    await _order(db, company_id, laura, "Laura", [("aguila", "Cerveza Aguila", 2, 6000)])
    await _order(db, company_id, nico, "Nico", [("guaro", "Aguardiente Antioqueño media", 1, 60000)])
    await _order(db, company_id, laura, "Laura", [("marlboro", "Cigarrillos Marlboro", 1, 1500)])

    # cada pedido queda guardado con la cuenta del teléfono que lo hizo
    assert [o["people"][0]["account_id"] for o in db.orders] == [laura, nico, laura]
    assert [o["metadata"]["account_id"] for o in db.orders] == [laura, nico, laura]

    # vista de Laura
    account = await _account(db, company_id, laura)
    assert account["total"] == 73500.0
    assert account["orders_count"] == 3
    assert account["accounts_count"] == 2
    assert account["current_total"] == 13500.0
    by_id = {a["account_id"]: a for a in account["accounts"]}
    assert by_id[laura]["total"] == 13500.0 and by_id[laura]["orders_count"] == 2 and by_id[laura]["is_current"]
    assert by_id[nico]["total"] == 60000.0 and by_id[nico]["orders_count"] == 1 and not by_id[nico]["is_current"]
    assert sorted((i["name"], i["quantity"]) for i in by_id[laura]["items"]) == [
        ("Cerveza Aguila", 2.0),
        ("Cigarrillos Marlboro", 1.0),
    ]
    assert [(i["name"], i["quantity"]) for i in by_id[nico]["items"]] == [("Aguardiente Antioqueño media", 1.0)]
    assert sum(a["total"] for a in account["accounts"]) == account["total"]

    # vista de Nico: mismo total de mesa, su propia cuenta marcada
    account_nico = await _account(db, company_id, nico)
    assert account_nico["total"] == 73500.0
    assert account_nico["current_total"] == 60000.0
    assert account_nico["accounts"][0]["account_id"] == nico

    # cierre de mesa (el barman cierra los pedidos de la mesa, ya entregados)
    for o in db.orders:
        o["status"] = "entregado"
    for o in list(db.orders):
        await hospitality.close_hospitality_order(
            company_id, o["id"], hospitality.HospitalityCloseIn(payment_method="cash"), db
        )
    assert all(o["status"] == "cerrado" for o in db.orders)
    assert sum(o["total"] for o in db.orders if o["status"] == "cerrado") == 73500.0
    # la cuenta de la mesa queda en cero para la siguiente activación
    assert (await _account(db, company_id, laura))["total"] == 0.0


@pytest.mark.asyncio
async def test_hospitality_qr_accounts_never_mix_another_company(monkeypatch):
    company_id = uuid.uuid4()
    db = OrdersDb(company_id)
    _install(monkeypatch, db)
    await _order(db, company_id, "qr_account_a", "Laura", [("aguila", "Cerveza Aguila", 1, 6000)])
    db.orders.append({**db.orders[0], "id": uuid.uuid4(), "company_id": str(uuid.uuid4()), "total": 99999})

    account = await _account(db, company_id, "qr_account_a")
    assert account["total"] == 6000.0
    assert account["accounts_count"] == 1
