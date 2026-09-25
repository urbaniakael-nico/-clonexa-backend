"""Domicilios por WhatsApp (module domicilios_whatsapp, only ASADERO today).

Covers what the owner asked to be proven:
  - out of hours the customer line answers the configured message + schedule;
  - the link is personal, single use and expires in 30 minutes;
  - the order reaches kitchen and caja marked as DOMICILIO and deducts
    inventory through hospitality's own create_hospitality_order;
  - a QR payment stays "por verificar" until the caja confirms it (no
    closing, no dispatch before that);
  - sending it to the domiciliario records who and when;
  - a company without the module sees nothing.
"""
from __future__ import annotations

import ast
import json
import uuid
from datetime import datetime
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
from app.api.v1.endpoints import delivery_whatsapp as dw
from app.api.v1.endpoints import hospitality, waiter_ordering
from app.api.v1.endpoints.hospitality import HospitalityOrderItemIn
from app.services import whatsapp_customer_line, whatsapp_delivery as wd
from app.web import admin_v2_routes

client = TestClient(app_main.app)
ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
BOGOTA = ZoneInfo("America/Bogota")
OPEN_ALL_WEEK = {day: [{"from": "11:00", "to": "22:00"}] for day in wd.DAYS}
SETTINGS = wd.normalize_settings({"schedule": OPEN_ALL_WEEK, "delivery_fee": 5000, "eta_minutes": 40})


class FakeDb:
    """Answers each SQL by the first matching substring handler."""

    def __init__(self, handlers=None):
        self.handlers = list(handlers or [])
        self.calls: list[tuple[str, dict]] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    def on(self, needle, rows):
        self.handlers.append((needle, rows))
        return self

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = dict(params or {})
        self.calls.append((sql, params))
        rows: list = []
        for needle, handler in self.handlers:
            if needle in sql:
                rows = handler(params) if callable(handler) else handler
                break
        rows = [dict(r) for r in rows]
        mapped = SimpleNamespace(all=lambda: rows, first=lambda: rows[0] if rows else None)
        return SimpleNamespace(
            mappings=lambda: mapped,
            first=lambda: rows[0] if rows else None,
            scalar=lambda: next(iter(rows[0].values())) if rows else None,
            fetchall=lambda: [SimpleNamespace(_mapping=r) for r in rows],
        )

    def sql(self, needle):
        return [(sql, params) for sql, params in self.calls if needle in sql]


@pytest.fixture(autouse=True)
def _no_real_db_in_middlewares(monkeypatch):
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    yield
    app_main.app.dependency_overrides.pop(get_db, None)


def use_db(db):
    async def _override():
        yield db

    app_main.app.dependency_overrides[get_db] = _override
    return db


def login(monkeypatch, company_id, role="caja"):
    user = SimpleNamespace(company_id=uuid.UUID(company_id), role=role, status="active", full_name=f"Usuario {role}")
    monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(return_value=user))
    monkeypatch.setattr(dw, "ip_allowed_for_scope", AsyncMock(return_value=True))
    return {"Authorization": "Bearer token"}


# ------------------------------------------------------------- schedule ---
def test_schedule_open_and_overnight_slots():
    schedule = wd.normalize_settings({"schedule": {"fri": [{"from": "18:00", "to": "02:00"}], "sat": [{"from": "11:00", "to": "15:00"}]}})["schedule"]
    friday_night = datetime(2026, 9, 25, 23, 30, tzinfo=BOGOTA)
    saturday_1am = datetime(2026, 9, 26, 1, 0, tzinfo=BOGOTA)
    saturday_3am = datetime(2026, 9, 26, 3, 0, tzinfo=BOGOTA)
    saturday_noon = datetime(2026, 9, 26, 12, 0, tzinfo=BOGOTA)
    friday_noon = datetime(2026, 9, 25, 12, 0, tzinfo=BOGOTA)
    assert wd.is_open(schedule, friday_night)
    assert wd.is_open(schedule, saturday_1am), "18:00-02:00 del viernes sigue abierto el sabado a la 1"
    assert not wd.is_open(schedule, saturday_3am)
    assert wd.is_open(schedule, saturday_noon)
    assert not wd.is_open(schedule, friday_noon)
    assert wd.schedule_text(wd.normalize_settings({"schedule": OPEN_ALL_WEEK})["schedule"]) == "Lunes a Domingo: 11:00-22:00"


def test_invalid_slots_are_dropped():
    settings = wd.normalize_settings({"schedule": {"mon": [{"from": "25:00", "to": "10:00"}, {"from": "08:00", "to": "08:00"}, {"from": "08:00", "to": "12:00"}]}})
    assert settings["schedule"]["mon"] == [{"from": "08:00", "to": "12:00"}]


# ---------------------------------------------------------- customer line ---
def _line_db(settings=SETTINGS, recent=False):
    return (
        FakeDb()
        .on("FROM company_modules cm", [{"settings": json.dumps(settings)}] if settings is not None else [])
        .on("FROM companies WHERE id", [{"name": "Asadero El Socio", "timezone": "America/Bogota"}])
        .on("SELECT 1 FROM whatsapp_delivery_sessions", [{"x": 1}] if recent else [])
    )


@pytest.mark.asyncio
async def test_out_of_hours_answers_the_configured_message_and_schedule():
    settings = wd.normalize_settings({
        "schedule": {"mon": [{"from": "11:00", "to": "15:00"}]},
        "closed_message": "Hola{nombre}, por el momento no hay servicio a domicilio.",
    })
    db = _line_db(settings)
    monday_night = datetime(2026, 9, 28, 21, 0, tzinfo=BOGOTA)
    reply = await wd.customer_reply(db, company_id=uuid.UUID(ASADERO), from_phone="3001234567", push_name="Ana", now=monday_night)
    assert reply.startswith("Hola Ana, por el momento no hay servicio a domicilio.")
    assert "Lunes: 11:00-15:00" in reply
    assert "domicilio?c=" not in reply, "fuera de horario nunca entrega link"
    insert = db.sql("INSERT INTO whatsapp_delivery_sessions")[0][1]
    assert insert["kind"] == "closed" and insert["phone"] == "573001234567"


@pytest.mark.asyncio
async def test_in_hours_sends_a_personal_link_that_expires_in_30_minutes():
    db = _line_db()
    monday_noon = datetime(2026, 9, 28, 12, 0, tzinfo=BOGOTA)
    reply = await wd.customer_reply(db, company_id=uuid.UUID(ASADERO), from_phone="573001234567", push_name="", now=monday_noon)
    assert "Bienvenido a Asadero El Socio" in reply
    assert f"/domicilio?c={ASADERO}&s=" in reply
    token = reply.split("&s=")[1].split()[0]
    insert = db.sql("INSERT INTO whatsapp_delivery_sessions")[0][1]
    assert insert["kind"] == "link" and insert["minutes"] == 30
    assert insert["phone"] == "573001234567"
    assert insert["token_hash"] == wd.token_hash(token) and token not in json.dumps(insert), "solo se guarda el hash"


@pytest.mark.asyncio
async def test_chat_without_visible_phone_still_gets_its_link():
    # Newer WhatsApp chats arrive as "<id>@lid": the link goes back in the
    # same chat and later notices are sent to that chat id.
    db = _line_db()
    monday_noon = datetime(2026, 9, 28, 12, 0, tzinfo=BOGOTA)
    reply = await wd.customer_reply(db, company_id=uuid.UUID(ASADERO), from_phone="", from_jid="123456789012345@lid", now=monday_noon)
    assert "/domicilio?c=" in reply
    assert db.sql("INSERT INTO whatsapp_delivery_sessions")[0][1]["phone"] == "123456789012345@lid"
    assert wd.contact_key("", "algo@s.whatsapp.net") == "" and wd.display_phone("123456789012345@lid") == ""
    assert "por WhatsApp" in wd.driver_message("A", {"order_number": "1", "items": []}, {"customer_name": "Ana", "customer_phone": "123456789012345@lid", "address": "x", "total": 1})


@pytest.mark.asyncio
async def test_a_burst_of_messages_gets_one_answer():
    db = _line_db(recent=True)
    monday_noon = datetime(2026, 9, 28, 12, 0, tzinfo=BOGOTA)
    assert await wd.customer_reply(db, company_id=uuid.UUID(ASADERO), from_phone="3001234567", now=monday_noon) == ""
    assert not db.sql("INSERT INTO whatsapp_delivery_sessions")


@pytest.mark.asyncio
async def test_company_without_the_module_gets_silence_on_the_customer_line():
    db = _line_db(settings=None)
    reply = await whatsapp_customer_line.customer_line_reply(db, company_id=uuid.uuid4(), from_phone="3001234567", text_value="hola")
    assert reply == ""
    assert not db.sql("INSERT")


@pytest.mark.asyncio
async def test_valid_session_only_accepts_unused_unexpired_links():
    db = FakeDb()
    assert await wd.valid_session(db, uuid.UUID(ASADERO), "") is None
    await wd.valid_session(db, uuid.UUID(ASADERO), "abcdefghijklmnop")
    sql, params = db.calls[0]
    assert "used_at IS NULL AND expires_at > NOW()" in sql and "kind = 'link'" in sql
    assert params["company_id"] == ASADERO and params["token_hash"] == wd.token_hash("abcdefghijklmnop")


def test_delivery_modules_import_nothing_internal():
    root = Path(__file__).resolve().parent.parent / "app" / "services"
    forbidden = ("payroll", "crm", "production", "workforce", "employee", "bots", "whatsapp_agent_access", "company_users")
    for name in ("whatsapp_customer_line.py", "whatsapp_delivery.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported += [node.module or ""] + [f"{node.module}.{alias.name}" for alias in node.names]
        assert not [i for i in imported if any(word in i.lower() for word in forbidden)], name


# --------------------------------------------------------- public carta ---
SESSION = {"id": uuid.uuid4(), "phone": "573001234567", "expires_at": datetime(2026, 9, 28, 12, 30, tzinfo=BOGOTA), "location": None}


def test_expired_or_used_link_is_rejected(monkeypatch):
    use_db(FakeDb())
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=SETTINGS))
    monkeypatch.setattr(wd, "valid_session", AsyncMock(return_value=None))
    carta = client.get(f"/api/v1/domicilios/public/{ASADERO}?s=vencido123456")
    assert carta.status_code == 410 and "vencio" in carta.text
    order = client.post(f"/api/v1/domicilios/public/{ASADERO}/orders", json=_order_body())
    assert order.status_code == 410
    qr = client.get(f"/api/v1/domicilios/public/{ASADERO}/payment-qr?s=vencido123456")
    assert qr.status_code == 410


def test_public_carta_shows_the_shared_menu(monkeypatch):
    use_db(FakeDb().on("whatsapp_delivery_payment_qr", [{"x": 1}]))
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=SETTINGS))
    monkeypatch.setattr(wd, "valid_session", AsyncMock(return_value=SESSION))
    monkeypatch.setattr(wd, "company_brief", AsyncMock(return_value={"name": "Asadero El Socio", "timezone": "America/Bogota"}))
    menu = {"categories": [{"key": "pollo", "label": "Pollo", "products": [{"id": "p1", "name": "Pollo asado", "price": 20000}]}], "quantity_buttons": ["1/4"], "menu_emojis": True}
    build = AsyncMock(return_value=menu)
    monkeypatch.setattr(dw, "build_waiter_menu", build)
    monkeypatch.setattr(dw, "whatsapp_status", AsyncMock(return_value={"status": "connected", "connected_phone": "573110000000"}))
    response = client.get(f"/api/v1/domicilios/public/{ASADERO}?s=codigo123456")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["categories"] == menu["categories"] and body["delivery_fee"] == 5000 and body["eta_minutes"] == 40
    assert body["phone_hint"] == "***4567" and body["has_payment_qr"] is True
    assert body["whatsapp_number"] == "573110000000"
    assert build.await_args.args[1] == uuid.UUID(ASADERO)


def test_company_without_the_module_sees_nothing(monkeypatch):
    use_db(FakeDb())
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=None))
    other = str(uuid.uuid4())
    assert client.get(f"/api/v1/domicilios/public/{other}?s=codigo123456").status_code == 404
    assert client.post(f"/api/v1/domicilios/public/{other}/orders", json=_order_body()).status_code == 404
    headers = login(monkeypatch, other, "company_admin")
    for method, path in (("get", "/settings"), ("get", "/drivers"), ("post", f"/orders/{uuid.uuid4()}/verify-payment")):
        response = client.request(method.upper(), f"/api/v1/domicilios/companies/{other}{path}", headers=headers)
        assert response.status_code == 404, path


def _order_body(**over):
    body = {
        "s": "codigo123456",
        "customer_name": "Ana Perez",
        "address": "Calle 10 # 20-30, apto 401",
        "latitude": 4.60971,
        "longitude": -74.08175,
        "payment_method": "cash",
        "pays_with": 100000,
        "items": [{"inventory_item_id": "p1", "quantity": 2, "observations": "sin sal"}],
    }
    body.update(over)
    return body


@pytest.fixture
def ordering(monkeypatch):
    """Real public endpoint + real create_hospitality_order over a fake DB."""
    stored: dict = {}

    def insert_order(params):
        row = {**params, "id": uuid.uuid4(), "status": "pendiente", "created_at": datetime.now(BOGOTA), "updated_at": None}
        stored["order"] = row
        return [row]

    def select_metadata(params):
        return [{"metadata": stored["order"]["metadata"]}]

    def update_metadata(params):
        meta = json.loads(stored["order"]["metadata"])
        meta["delivery"] = json.loads(params["delivery"])
        stored["order"]["metadata"] = json.dumps(meta)
        return []

    db = use_db(
        FakeDb()
        .on("UPDATE whatsapp_delivery_sessions SET used_at", lambda p: [{"id": p["id"]}])
        .on("INSERT INTO hospitality_orders", insert_order)
        .on("SELECT metadata FROM hospitality_orders", select_metadata)
        .on("jsonb_set(metadata, '{delivery}'", update_metadata)
    )
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=SETTINGS))
    monkeypatch.setattr(wd, "valid_session", AsyncMock(return_value=SESSION))
    monkeypatch.setattr(wd, "company_brief", AsyncMock(return_value={"name": "Asadero El Socio", "timezone": "America/Bogota"}))
    monkeypatch.setattr(wd, "is_open", lambda schedule, now: True)
    priced = [HospitalityOrderItemIn(inventory_item_id="p1", name="Pollo asado", quantity=2, unit_price=20000, station="parrilla", observations="sin sal")]
    monkeypatch.setattr(dw, "_priced_order_items", AsyncMock(return_value=priced))
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(hospitality, "_inventory_lookup", AsyncMock(return_value=None))
    monkeypatch.setattr(hospitality, "_next_order_number", AsyncMock(return_value="HSP-0042"))
    deduct = AsyncMock()
    monkeypatch.setattr(hospitality, "_deduct_inventory", deduct)

    async def fetch_order(db_, company_id, order_id):
        return hospitality._payload(stored["order"])

    monkeypatch.setattr(hospitality, "_fetch_order", fetch_order)
    monkeypatch.setattr(dw, "_fetch_order", fetch_order)
    sent = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(dw, "whatsapp_send", sent)
    return SimpleNamespace(db=db, stored=stored, deduct=deduct, sent=sent,
                           order=lambda: hospitality._payload(stored["order"]))


def test_order_enters_as_domicilio_deducts_inventory_and_confirms(ordering):
    response = client.post(f"/api/v1/domicilios/public/{ASADERO}/orders", json=_order_body())
    assert response.status_code == 201, response.text
    assert response.json()["total"] == 45000  # 2 x 20.000 + domicilio 5.000

    order = ordering.order()
    assert order["type"] == "domicilio" and order["source"] == "domicilio"
    assert order["table_number"].startswith("Domicilio ")
    delivery = order["metadata"]["delivery"]
    assert delivery["address"] == "Calle 10 # 20-30, apto 401"
    assert delivery["customer_phone"] == "573001234567", "el telefono sale de la sesion, nunca del formulario"
    assert delivery["location_url"] == "https://maps.google.com/?q=4.609710,-74.081750"
    assert delivery["payment_status"] == "contra_entrega"
    assert (delivery["pays_with"], delivery["change"], delivery["total"], delivery["fee"]) == (100000, 55000, 45000, 5000)
    fee_line = [item for item in order["items"] if item["station"] == "domicilio"]
    assert fee_line and fee_line[0]["subtotal"] == 5000

    # Inventory: the same deduction as any other order.
    ordering.deduct.assert_awaited_once()
    assert ordering.db.sql("SET inventory_deducted = TRUE")
    # The link is burnt before the order is created, and linked to it after.
    claim = ordering.db.sql("UPDATE whatsapp_delivery_sessions SET used_at")[0][0]
    assert "used_at IS NULL AND expires_at > NOW()" in claim
    assert ordering.db.sql("UPDATE whatsapp_delivery_sessions SET order_id")

    # One confirmation on the customer line, with total and ETA.
    company_id, phone, message, line = ordering.sent.await_args.args
    assert (company_id, phone, line) == (ASADERO, "573001234567", "clientes")
    assert "$45.000" in message and "40 minutos" in message
    assert order["metadata"]["delivery"]["notified"]["confirmed"]


def test_kitchen_gets_a_domicilio_comanda_without_the_fee_line(ordering):
    client.post(f"/api/v1/domicilios/public/{ASADERO}/orders", json=_order_body())
    comanda = waiter_ordering._comanda(ordering.order(), set())
    assert comanda["delivery"] == {"customer_name": "Ana Perez", "address": "Calle 10 # 20-30, apto 401"}
    assert [item["name"] for item in comanda["items"]] == ["Pollo asado"]
    assert waiter_ordering._comanda({"items": [{"name": "Cerveza"}], "metadata": {}}, set())["delivery"] is None


def test_used_link_cannot_create_a_second_order(ordering):
    ordering.db.handlers.insert(0, ("UPDATE whatsapp_delivery_sessions SET used_at", []))
    response = client.post(f"/api/v1/domicilios/public/{ASADERO}/orders", json=_order_body())
    assert response.status_code == 410
    assert not ordering.db.sql("INSERT INTO hospitality_orders")


def test_cash_amount_below_total_is_rejected(ordering):
    response = client.post(f"/api/v1/domicilios/public/{ASADERO}/orders", json=_order_body(pays_with=20000))
    assert response.status_code == 422 and "$45.000" in response.text
    assert not ordering.db.sql("INSERT INTO hospitality_orders")


def test_public_order_endpoint_of_hospitality_cannot_set_delivery():
    route = next(r for r in app_main.app.routes if getattr(r, "path", "") == "/api/v1/hospitality/companies/{company_id}/orders" and "POST" in r.methods)
    body_fields = {field.name for field in route.dependant.body_params}
    assert "delivery" not in body_fields
    assert any(dep.call is hospitality._internal_only for dep in route.dependant.dependencies)


# -------------------------------------------------------------- QR payment ---
def test_qr_payment_stays_pending_until_the_caja_verifies(ordering, monkeypatch):
    response = client.post(f"/api/v1/domicilios/public/{ASADERO}/orders", json=_order_body(payment_method="qr", pays_with=None))
    assert response.json()["payment_status"] == "por_verificar"
    order = ordering.order()
    assert order["metadata"]["delivery"]["payment_status"] == "por_verificar"
    assert "comprobante" in ordering.sent.await_args.args[2]
    order_id = order["id"]

    # Nobody closes it as paid while it is pending (not even via close-table).
    ordering.stored["order"]["status"] = "entregado"
    with pytest.raises(HTTPException) as exc:
        import asyncio

        asyncio.run(hospitality.close_hospitality_order(uuid.UUID(ASADERO), uuid.UUID(order_id), None, ordering.db))
    assert exc.value.status_code == 409 and exc.value.detail == "pago_por_verificar"

    # A mesero cannot verify it.
    mesero = login(monkeypatch, ASADERO, "mesero")
    denied = client.post(f"/api/v1/domicilios/companies/{ASADERO}/orders/{order_id}/verify-payment", headers=mesero)
    assert denied.status_code == 403

    # Nor dispatch it before verifying.
    caja = login(monkeypatch, ASADERO, "caja")
    blocked = client.post(f"/api/v1/domicilios/companies/{ASADERO}/orders/{order_id}/dispatched", headers=caja)
    assert blocked.status_code == 409 and "Confirma el pago" in blocked.text

    verified = client.post(f"/api/v1/domicilios/companies/{ASADERO}/orders/{order_id}/verify-payment", headers=caja)
    assert verified.status_code == 200, verified.text
    delivery = ordering.order()["metadata"]["delivery"]
    assert delivery["payment_status"] == "verificado" and delivery["payment_verified_by"] == "Usuario caja"
    assert client.post(f"/api/v1/domicilios/companies/{ASADERO}/orders/{order_id}/verify-payment", headers=caja).status_code == 409


# ---------------------------------------------------------- domiciliario ---
def test_sending_to_the_domiciliario_records_who_and_when(ordering, monkeypatch):
    client.post(f"/api/v1/domicilios/public/{ASADERO}/orders", json=_order_body())
    order_id = ordering.order()["id"]
    driver_id = uuid.uuid4()
    ordering.db.handlers.insert(0, ("FROM employees", [{"id": driver_id, "full_name": "Pedro Moto", "phone": "311 222 3344"}]))
    caja = login(monkeypatch, ASADERO, "caja")

    drivers = client.get(f"/api/v1/domicilios/companies/{ASADERO}/drivers", headers=caja)
    assert drivers.json()["drivers"] == [{"employee_id": str(driver_id), "name": "Pedro Moto", "phone": "573112223344"}]
    role_sql = ordering.db.sql("FROM employees")[0]
    assert role_sql[1] == {"company_id": ASADERO, "role": "domiciliario"}

    response = client.post(f"/api/v1/domicilios/companies/{ASADERO}/orders/{order_id}/assign", headers=caja, json={"employee_id": str(driver_id)})
    assert response.status_code == 200, response.text
    _, phone, message, line = ordering.sent.await_args.args
    assert (phone, line) == ("573112223344", "clientes")
    for expected in ("Calle 10 # 20-30", "2 x Pollo asado (sin sal)", "maps.google.com/?q=4.609710,-74.081750", "COBRAR $45.000", "paga con $100.000, cambio $55.000", "Total: $45.000"):
        assert expected in message, expected
    assert "Valor domicilio" not in message.split("Productos:")[1].split("Total:")[0]
    driver = ordering.order()["metadata"]["delivery"]["driver"]
    assert driver["employee_id"] == str(driver_id) and driver["name"] == "Pedro Moto"
    assert driver["assigned_by"] == "Usuario caja" and driver["assigned_at"] and driver["whatsapp_sent"] is True

    # "Salio": one message to the customer, never twice.
    ordering.sent.reset_mock()
    first = client.post(f"/api/v1/domicilios/companies/{ASADERO}/orders/{order_id}/dispatched", headers=caja)
    assert first.status_code == 200 and "va en camino" in ordering.sent.await_args.args[2]
    again = client.post(f"/api/v1/domicilios/companies/{ASADERO}/orders/{order_id}/dispatched", headers=caja)
    assert again.json().get("already_notified") is True
    assert ordering.sent.await_count == 1


def test_unknown_driver_is_rejected(ordering, monkeypatch):
    client.post(f"/api/v1/domicilios/public/{ASADERO}/orders", json=_order_body())
    order_id = ordering.order()["id"]
    ordering.db.handlers.insert(0, ("FROM employees", []))
    caja = login(monkeypatch, ASADERO, "caja")
    response = client.post(f"/api/v1/domicilios/companies/{ASADERO}/orders/{order_id}/assign", headers=caja, json={"employee_id": str(uuid.uuid4())})
    assert response.status_code == 404


# ------------------------------------------------------------------ auth ---
AUTHED = [
    ("get", "/settings", None),
    ("put", "/settings", {"delivery_fee": 1000}),
    ("get", "/payment-qr", None),
    ("get", "/drivers", None),
    ("post", "/orders/{oid}/verify-payment", None),
    ("post", "/orders/{oid}/assign", {"employee_id": str(uuid.uuid4())}),
    ("post", "/orders/{oid}/dispatched", None),
]


@pytest.mark.parametrize("method,path,body", AUTHED)
def test_endpoints_require_a_session(method, path, body, monkeypatch):
    use_db(FakeDb())
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=SETTINGS))
    url = f"/api/v1/domicilios/companies/{ASADERO}" + path.format(oid=uuid.uuid4())
    assert client.request(method.upper(), url, json=body).status_code in (401, 403)
    other = login(monkeypatch, str(uuid.uuid4()), "company_admin")
    assert client.request(method.upper(), url, json=body, headers=other).status_code == 403


@pytest.mark.parametrize("method,path,body", AUTHED[:3])
def test_configuration_is_for_admins_only(method, path, body, monkeypatch):
    use_db(FakeDb())
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=SETTINGS))
    caja = login(monkeypatch, ASADERO, "caja")
    response = client.request(method.upper(), f"/api/v1/domicilios/companies/{ASADERO}{path}", json=body, headers=caja)
    assert response.status_code == 403


def test_caja_role_outside_the_restaurant_network_is_rejected(monkeypatch):
    use_db(FakeDb())
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=SETTINGS))
    caja = login(monkeypatch, ASADERO, "caja")
    monkeypatch.setattr(dw, "ip_allowed_for_scope", AsyncMock(return_value=False))
    response = client.get(f"/api/v1/domicilios/companies/{ASADERO}/drivers", headers=caja)
    assert response.status_code == 403 and "WiFi" in response.text


def test_admin_saves_schedule_fee_and_messages(monkeypatch):
    db = use_db(FakeDb())
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=SETTINGS))
    admin = login(monkeypatch, ASADERO, "company_admin")
    body = {
        "schedule": {"mon": [{"from": "11:00", "to": "15:00"}], "sat": [{"from": "18:00", "to": "02:00"}]},
        "delivery_fee": 6000, "eta_minutes": 50,
        "greeting_message": "Hola! Pide aqui: {link}", "closed_message": "Cerrado. {horario}",
    }
    response = client.put(f"/api/v1/domicilios/companies/{ASADERO}/settings", json=body, headers=admin)
    assert response.status_code == 200, response.text
    saved = json.loads(db.sql("UPDATE company_modules")[0][1]["settings"])
    assert saved["schedule"]["mon"] == [{"from": "11:00", "to": "15:00"}] and saved["schedule"]["tue"] == []
    assert saved["delivery_fee"] == 6000 and saved["eta_minutes"] == 50
    assert db.sql("UPDATE company_modules")[0][1]["company_id"] == ASADERO
    assert "numero dedicado" in response.json()["warning"]


def test_caja_config_reports_the_delivery_section_only_with_the_module(monkeypatch):
    import asyncio

    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value={}))
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=None))
    off = asyncio.run(waiter_ordering.cashier_config(uuid.uuid4(), FakeDb(), None))
    assert off["delivery"] is False
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value=SETTINGS))
    on = asyncio.run(waiter_ordering.cashier_config(uuid.UUID(ASADERO), FakeDb(), None))
    assert on["delivery"] is True
