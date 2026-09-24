"""Cuentas por persona en la mesa QR (servidor), con los mismos pedidos que
tests/hospitality_qr_bar_accounts.test.cjs: dos teléfonos (account_id
distintos) piden desde la misma mesa; cada uno ve su cuenta, la mesa suma
ambas y el cierre cobra el total. Con la carta de bar (qr_bar_menu) quien no
escribe su nombre queda como "Persona N" según el orden en que abrió la mesa.
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


class BarDb:
    """In-memory hospitality_orders + hospitality_table_guests for one
    company (only the SQL these endpoints run)."""

    def __init__(self, company_id, bar_menu=True):
        self.company_id = str(company_id)
        self.bar_menu = bar_menu
        self.access_id = str(uuid.uuid4())
        self.orders: list[dict] = []
        self.guests: list[dict] = []
        self.sql: list[str] = []
        self.commit = AsyncMock()

    def new_activation(self):
        self.access_id = str(uuid.uuid4())

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = params or {}
        self.sql.append(sql)
        if "company_id" in params:
            assert params["company_id"] == self.company_id, "nunca otra empresa"
        if sql.startswith("SELECT cm.settings FROM company_modules"):
            return _Rows([{"settings": {"qr_bar_menu": True} if self.bar_menu else {}}])
        if sql.startswith("SELECT id FROM hospitality_table_access WHERE id = :access_id"):
            assert "FOR UPDATE" in sql and "company_id = :company_id" in sql
            return _Rows([{"id": params["access_id"]}])
        if sql.startswith("SELECT guest_number, name FROM hospitality_table_guests"):
            rows = [
                g for g in self.guests
                if (g["company_id"], g["access_id"], g["account_id"])
                == (params["company_id"], params["access_id"], params["account_id"])
            ]
            return _Rows([{"guest_number": g["guest_number"], "name": g["name"]} for g in rows])
        if sql.startswith("INSERT INTO hospitality_table_guests"):
            assert "COALESCE(MAX(guest_number), 0) + 1" in sql
            same = [g for g in self.guests if (g["company_id"], g["access_id"]) == (params["company_id"], params["access_id"])]
            guest = {
                "company_id": params["company_id"],
                "access_id": params["access_id"],
                "account_id": params["account_id"],
                "guest_number": max([g["guest_number"] for g in same], default=0) + 1,
                "name": params["name"],
            }
            self.guests.append(guest)
            return _Rows([{"guest_number": guest["guest_number"], "name": guest["name"]}])
        if sql.startswith("UPDATE hospitality_table_guests SET name"):
            for g in self.guests:
                if (g["company_id"], g["access_id"], g["account_id"]) == (params["company_id"], params["access_id"], params["account_id"]):
                    g["name"] = params["name"]
            return _Rows([])
        if sql.startswith("INSERT INTO hospitality_orders"):
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
                "archived_at": None,
                "created_at": now,
                "updated_at": now,
            }
            self.orders.append(row)
            return _Rows([row])
        if sql.startswith("UPDATE hospitality_orders SET inventory_deducted"):
            return _Rows([])
        if sql.startswith("SELECT id, people FROM hospitality_orders"):
            assert "metadata->>'account_id' = :account_id" in sql
            assert "status IN ('pendiente', 'alistando', 'entregado')" in sql
            rows = [
                {"id": o["id"], "people": json.dumps(o["people"])}
                for o in self.open_orders(params["table_key"])
                if o["metadata"].get("account_id") == params["account_id"]
            ]
            return _Rows(rows)
        if sql.startswith("UPDATE hospitality_orders SET people"):
            for o in self.orders:
                if str(o["id"]) == params["order_id"]:
                    o["people"] = json.loads(params["people"])
                    o["customer_name"] = params["customer_name"]
            return _Rows([])
        if sql.startswith("SELECT * FROM hospitality_orders WHERE company_id = :company_id AND table_key = :table_key"):
            return _Rows(self.open_orders(params["table_key"]))
        if sql.startswith("UPDATE hospitality_orders SET status = 'cerrado'"):
            for o in self.orders:
                if str(o["id"]) == params["order_id"]:
                    o["status"] = "cerrado"
            return _Rows([])
        raise AssertionError(f"SQL no esperado en la prueba: {sql[:120]}")

    def open_orders(self, table_key):
        return [
            o for o in self.orders
            if o["table_key"] == table_key and o["status"] in ("pendiente", "alistando", "entregado")
        ]


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

    async def active_access(_db, _company_id, _table):
        return {"id": db.access_id, "access_code": "MESA5", "status": "active"}

    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(hospitality, "_require_table_access", AsyncMock())
    monkeypatch.setattr(hospitality, "_fetch_active_table_access", active_access)
    monkeypatch.setattr(hospitality, "_build_order_items", build_items)
    counter = iter(range(1, 100))
    monkeypatch.setattr(hospitality, "_next_order_number", AsyncMock(side_effect=lambda *_: f"QR-{next(counter)}"))
    monkeypatch.setattr(hospitality, "_deduct_inventory", AsyncMock())
    monkeypatch.setattr(hospitality, "_fetch_order", fetch_order)
    monkeypatch.setattr(hospitality, "_close_table_access_if_idle", AsyncMock())


async def _order(db, company_id, account_id, customer, items):
    response = await hospitality.create_hospitality_order(
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
    return response["order"]


async def _account(db, company_id, account_id, customer=None):
    response = await hospitality.get_hospitality_table_account(
        company_id,
        hospitality.HospitalityTableAccessVerifyIn(
            table="Mesa 5", access_code="MESA5", account_id=account_id, customer=customer
        ),
        db,
    )
    return response["account"]


def _names(account):
    return {a["account_id"]: a["name"] for a in account["accounts"]}


AGUILA = [("aguila", "Cerveza Aguila", 2, 6000)]
GUARO = [("guaro", "Aguardiente Antioqueño media", 1, 60000)]
MARLBORO = [("marlboro", "Cigarrillos Marlboro", 1, 1500)]


@pytest.mark.asyncio
async def test_hospitality_two_phones_same_table_keep_separate_accounts_and_close_the_total(monkeypatch):
    company_id = uuid.uuid4()
    db = BarDb(company_id)
    _install(monkeypatch, db)
    laura, nico = "qr_account_laura-phone", "qr_account_nico-phone"

    await _order(db, company_id, laura, "Laura", AGUILA)
    await _order(db, company_id, nico, "Nico", GUARO)
    await _order(db, company_id, laura, "Laura", MARLBORO)

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
    assert by_id[laura]["name"] == "Laura" and by_id[nico]["name"] == "Nico"
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
async def test_hospitality_qr_persona_numbers_follow_scan_order_and_never_repeat(monkeypatch):
    company_id = uuid.uuid4()
    db = BarDb(company_id)
    _install(monkeypatch, db)
    a, b, c, d = (f"qr_account_{x}" for x in "abcd")

    # A, B y C abren la mesa (así llega cada teléfono al activar la clave)
    for phone in (a, b, c):
        await _account(db, company_id, phone)
    assert [(g["account_id"], g["guest_number"]) for g in db.guests] == [(a, 1), (b, 2), (c, 3)]

    # piden sin escribir nombre, en otro orden: el número es el de llegada
    order_b = await _order(db, company_id, b, "", GUARO)
    order_a = await _order(db, company_id, a, "Cliente mesa", AGUILA)  # el texto por defecto no es un nombre
    assert order_b["customer_name"] == "Persona 2"
    assert order_b["people"][0]["name"] == "Persona 2"
    assert order_a["people"][0]["name"] == "Persona 1"

    # C nunca pide; D llega después y NO reutiliza el 3
    await _account(db, company_id, d)
    assert [g["guest_number"] for g in db.guests if g["account_id"] == d] == [4]
    account = await _account(db, company_id, a)
    assert _names(account) == {a: "Persona 1", b: "Persona 2"}
    assert account["current_account"]["name"] == "Persona 1"

    # B escribe su nombre después: reemplaza al automático en sus pedidos
    renamed = await _account(db, company_id, b, customer="Nico")
    assert _names(renamed) == {a: "Persona 1", b: "Nico"}
    assert [o["customer_name"] for o in db.orders if o["metadata"]["account_id"] == b] == ["Nico"]
    assert db.orders[0]["people"][0]["name"] == "Nico"  # lo que ve el panel del barman
    await _order(db, company_id, b, "", MARLBORO)       # sin nombre en el carrito: sigue siendo Nico
    assert db.orders[-1]["people"][0]["name"] == "Nico"
    assert [g["guest_number"] for g in db.guests if g["account_id"] == b] == [2], "el número no cambia"

    # un nombre vacío o por defecto nunca borra el que escribió
    await _account(db, company_id, b, customer="")
    await _account(db, company_id, b, customer="Cliente mesa")
    assert _names(await _account(db, company_id, b)) [b] == "Nico"

    # los números no se reordenan: nuevos teléfonos siguen contando
    await _account(db, company_id, "qr_account_e")
    assert sorted(g["guest_number"] for g in db.guests) == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_hospitality_qr_persona_numbers_restart_with_a_new_table_activation(monkeypatch):
    company_id = uuid.uuid4()
    db = BarDb(company_id)
    _install(monkeypatch, db)
    await _account(db, company_id, "qr_account_x")
    await _account(db, company_id, "qr_account_y")
    db.new_activation()  # el bar cerró la mesa y la volvió a activar: nuevo código, nuevos teléfonos
    order = await _order(db, company_id, "qr_account_z", "", AGUILA)
    assert order["people"][0]["name"] == "Persona 1"


@pytest.mark.asyncio
async def test_hospitality_qr_without_bar_menu_switch_keeps_todays_names(monkeypatch):
    company_id = uuid.uuid4()
    db = BarDb(company_id, bar_menu=False)
    _install(monkeypatch, db)
    order = await _order(db, company_id, "qr_account_a", "Cliente mesa", AGUILA)
    await _account(db, company_id, "qr_account_a", customer="Laura")
    assert order["people"][0]["name"] == "Cliente mesa"
    assert db.guests == []
    assert not any("hospitality_table_guests" in sql for sql in db.sql)
    assert db.orders[0]["customer_name"] == "Cliente mesa"


@pytest.mark.asyncio
async def test_hospitality_qr_accounts_never_mix_another_company(monkeypatch):
    company_id = uuid.uuid4()
    db = BarDb(company_id)
    _install(monkeypatch, db)
    await _order(db, company_id, "qr_account_a", "Laura", [("aguila", "Cerveza Aguila", 1, 6000)])
    # every statement above ran with this company's id (BarDb asserts it)
    db.orders.append({**db.orders[0], "id": uuid.uuid4(), "company_id": str(uuid.uuid4()), "total": 99999})
    db.orders[-1]["table_key"] = "otra empresa"

    account = await _account(db, company_id, "qr_account_a")
    assert account["total"] == 6000.0
    assert account["accounts_count"] == 1


def test_hospitality_qr_table_guests_migration():
    import importlib.util
    from pathlib import Path

    path = Path("migrations/versions/021n_qr_table_guests.py")
    spec = importlib.util.spec_from_file_location("mig_021n", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32
    assert module.down_revision == "021m_qr_bar_menu_ttm"
    source = path.read_text(encoding="utf-8")
    assert "UNIQUE (company_id, access_id, account_id)" in source
    assert "UNIQUE (company_id, access_id, guest_number)" in source
