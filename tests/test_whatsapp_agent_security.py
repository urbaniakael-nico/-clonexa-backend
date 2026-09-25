"""SECURITY (2026-09-24): agente de WhatsApp y endpoints de bots.

- Los 12 endpoints de administración de bots.py y los 4 de WhatsApp de
  shoplink.py exigen sesión (Admin V2 o usuario de la empresa; los que
  actúan en nombre del negocio, administrador/dueño).
- La entrada del puente (/whatsapp-web/inbound) solo acepta la clave del
  puente; el webhook viejo de Telegram, solo la secret_token de Telegram.
- Línea interna: responde solo al chat propio del número y a teléfonos de
  Workforce con "puede consultar por WhatsApp". A cualquier otro, silencio.
- Línea de clientes: nunca llega al agente interno, y su módulo no importa
  nada de nómina, CRM ni producción.
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import bots, shoplink
from app.services import whatsapp_agent_access as access
from app.web import admin_v2_routes

client = TestClient(app_main.app)
SECRET = "bridge-secret-test"

BOTS = "/api/v1/bots/companies/{cid}"
SHOP = "/api/v1/shoplink/companies/{cid}"

# (method, url template, body) -- company admin endpoints
ADMIN_ONLY = [
    ("put", BOTS + "/telegram", {"name": "Bot"}),
    ("post", BOTS + "/telegram/test", None),
    ("post", BOTS + "/telegram/listener/start", None),
    ("post", BOTS + "/telegram/deactivate", None),
    ("post", BOTS + "/telegram/poll", None),
    ("get", BOTS + "/whatsapp-web", None),
    ("post", BOTS + "/whatsapp-web/start", None),
    ("post", BOTS + "/whatsapp-web/logout", None),
    ("post", BOTS + "/whatsapp-web/test", {"to": "3001234567"}),
    ("get", BOTS + "/whatsapp-web/access", None),
    ("put", BOTS + "/whatsapp-web/access/" + str(uuid.uuid4()), {"enabled": True}),
    ("get", SHOP + "/whatsapp-web", None),
    ("post", SHOP + "/whatsapp-web/start", None),
    ("post", SHOP + "/whatsapp-web/logout", None),
    ("post", SHOP + "/whatsapp-web/test", {"message": "hola"}),
]
# Read-only for any user of the company (the dashboard shows the bot state).
ANY_USER = [("get", BOTS + "/telegram", None)]


def _call(method, template, body, company_id, headers=None):
    return client.request(
        method.upper(), template.format(cid=company_id), json=body, headers=headers or {}
    )


@pytest.fixture(autouse=True)
def _no_real_db_in_middlewares(monkeypatch):
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))


@pytest.fixture
def session_as(monkeypatch):
    def _login(user_company, role="company_admin"):
        user = SimpleNamespace(company_id=uuid.UUID(user_company), role=role, status="active", full_name="Dueno")
        monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(return_value=user))
        return {"Authorization": "Bearer token"}

    return _login


class _FakeDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.commit = AsyncMock()
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        rows = self.rows
        mapped = SimpleNamespace(all=lambda: rows, first=lambda: rows[0] if rows else None)
        return SimpleNamespace(mappings=lambda: mapped, scalar_one_or_none=lambda: None)


@pytest.fixture
def fake_db():
    db = _FakeDb()

    async def _override():
        yield db

    app_main.app.dependency_overrides[get_db] = _override
    yield db
    app_main.app.dependency_overrides.pop(get_db, None)


# ------------------------------------------------------------ endpoints ---
@pytest.mark.parametrize("method,template,body", ADMIN_ONLY + ANY_USER)
def test_bot_endpoint_rejects_no_credentials(method, template, body):
    response = _call(method, template, body, str(uuid.uuid4()))
    assert response.status_code in (401, 403), f"{method} {template} -> {response.status_code}"


@pytest.mark.parametrize("method,template,body", ADMIN_ONLY + ANY_USER)
def test_bot_endpoint_rejects_another_company(method, template, body, session_as):
    headers = session_as(str(uuid.uuid4()))
    response = _call(method, template, body, str(uuid.uuid4()), headers)
    assert response.status_code == 403, response.text
    assert "tenant_not_allowed" in response.text


@pytest.mark.parametrize("role", ["mesero", "caja", "cocina", "operador"])
@pytest.mark.parametrize("method,template,body", ADMIN_ONLY)
def test_bot_admin_endpoint_rejects_staff_roles(method, template, body, role, session_as):
    company_id = str(uuid.uuid4())
    response = _call(method, template, body, company_id, session_as(company_id, role))
    assert response.status_code == 403, response.text
    assert "role_not_allowed" in response.text


def test_whatsapp_test_endpoint_only_sends_the_fixed_welcome(session_as, fake_db, monkeypatch):
    company_id = str(uuid.uuid4())
    company = SimpleNamespace(id=uuid.UUID(company_id), name="Asadero")
    monkeypatch.setattr(bots, "ensure_company_exists", AsyncMock(return_value=company))
    sent = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(bots, "whatsapp_send", sent)
    response = _call(
        "post", BOTS + "/whatsapp-web/test",
        {"to": "3001234567", "message": "Tu pedido tiene un cobro pendiente, paga aqui: http://estafa"},
        company_id, session_as(company_id),
    )
    assert response.status_code == 200, response.text
    _, to, message = sent.await_args.args
    assert to == "3001234567"
    assert "estafa" not in message
    assert message == bots._whatsapp_agent_welcome(company)


def test_whatsapp_status_for_own_admin_uses_the_requested_line(session_as, fake_db, monkeypatch):
    company_id = str(uuid.uuid4())
    monkeypatch.setattr(bots, "ensure_company_exists", AsyncMock(return_value=SimpleNamespace(id=uuid.UUID(company_id), name="A")))
    status = AsyncMock(return_value={"status": "connected", "connected_phone": "573001112233"})
    monkeypatch.setattr(bots, "whatsapp_status", status)
    response = _call("get", BOTS + "/whatsapp-web?line=clientes", None, company_id, session_as(company_id))
    assert response.status_code == 200, response.text
    assert status.await_args.args == (company_id, "clientes")
    assert response.json()["line"] == "clientes"


def test_legacy_telegram_webhook_requires_the_secret(fake_db, monkeypatch):
    company_id = str(uuid.uuid4())
    monkeypatch.setattr(bots, "get_telegram_instance", AsyncMock(return_value=None))
    response = client.post(f"/api/v1/bots/telegram/{company_id}/webhook", json={"update_id": 1})
    assert response.status_code == 403
    row = SimpleNamespace(config_json={"webhook_secret": "s3cret"})
    monkeypatch.setattr(bots, "get_telegram_instance", AsyncMock(return_value=row))
    bad = client.post(
        f"/api/v1/bots/telegram/{company_id}/webhook", json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "otra"},
    )
    assert bad.status_code == 403


# -------------------------------------------------------------- inbound ---
@pytest.fixture
def inbound(monkeypatch, fake_db):
    monkeypatch.setenv("WHATSAPP_INBOUND_SECRET", SECRET)
    company_id = str(uuid.uuid4())
    monkeypatch.setattr(bots, "ensure_company_exists", AsyncMock(return_value=SimpleNamespace(id=uuid.UUID(company_id), name="Asadero")))
    agent = AsyncMock(return_value="Nomina de Asadero: total a pagar $1.000.000")
    monkeypatch.setattr(bots, "_whatsapp_agent_reply", agent)

    def _post(body, secret=SECRET):
        headers = {"x-clonexa-whatsapp-secret": secret} if secret is not None else {}
        return client.post("/api/v1/bots/whatsapp-web/inbound", json={"company_id": company_id, **body}, headers=headers)

    return SimpleNamespace(post=_post, agent=agent, company_id=company_id)


def test_inbound_requires_the_bridge_secret(inbound):
    assert inbound.post({"text": "nomina"}, secret=None).status_code == 403
    assert inbound.post({"text": "nomina"}, secret="adivinada").status_code == 403


def test_inbound_fails_closed_without_any_configured_secret(inbound, monkeypatch):
    monkeypatch.delenv("WHATSAPP_INBOUND_SECRET", raising=False)
    monkeypatch.setattr(bots, "get_settings", lambda: SimpleNamespace(JWT_SECRET_KEY=""))
    assert inbound.post({"text": "nomina"}, secret="").status_code == 403


def test_internal_line_stays_silent_to_an_unknown_number(inbound, monkeypatch):
    monkeypatch.setattr(bots, "is_agent_phone_authorized", AsyncMock(return_value=False))
    for text in ("cuanto es el pago de la quincena", "quien esta de turno", "produccion", "hola", "modulos"):
        response = inbound.post({"line": "interno", "from_phone": "573009998877", "text": text})
        assert response.status_code == 200
        assert response.json()["reply"] == ""
    inbound.agent.assert_not_awaited()


def test_internal_line_answers_the_owner_chat_and_granted_phones(inbound, monkeypatch):
    authorized = AsyncMock(return_value=False)
    monkeypatch.setattr(bots, "is_agent_phone_authorized", authorized)
    owner = inbound.post({"line": "interno", "is_self_chat": True, "from_phone": "573001112233", "text": "nomina"})
    assert "Nomina" in owner.json()["reply"]

    authorized.return_value = True
    staff = inbound.post({"line": "interno", "from_phone": "573004445566", "text": "nomina"})
    assert "Nomina" in staff.json()["reply"]
    assert authorized.await_args.args[1:] == (uuid.UUID(inbound.company_id), "573004445566")


def test_customer_line_never_reaches_the_internal_agent(inbound, monkeypatch):
    monkeypatch.setattr(bots, "is_agent_phone_authorized", AsyncMock(side_effect=AssertionError("no aplica")))
    customer = AsyncMock(return_value="")
    monkeypatch.setattr(bots, "customer_line_reply", customer)
    for body in (
        {"line": "clientes", "from_phone": "573009998877", "text": "nomina"},
        {"line": "clientes", "is_self_chat": True, "from_phone": "573001112233", "text": "nomina"},
        {"line": "clientes", "event_type": "connected", "text": "__clonexa_whatsapp_connected__"},
    ):
        response = inbound.post(body)
        assert response.status_code == 200
        assert response.json()["reply"] == ""
    inbound.agent.assert_not_awaited()
    assert customer.await_count == 3


def test_customer_line_module_imports_nothing_internal():
    path = Path(__file__).resolve().parent.parent / "app" / "services" / "whatsapp_customer_line.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported += [f"{node.module}.{alias.name}" for alias in node.names]
    forbidden = ("payroll", "crm", "production", "workforce", "employee", "bots", "whatsapp_agent_access", "company_users")
    leaks = [name for name in imported if any(word in name.lower() for word in forbidden)]
    assert not leaks, leaks


# --------------------------------------------------------- access grants ---
@pytest.mark.parametrize("raw,expected", [
    ("300 123 4567", "573001234567"),
    ("+57 300-123-4567", "573001234567"),
    ("0057 3001234567", "573001234567"),
    ("", ""),
])
def test_normalize_phone_matches_the_bridge(raw, expected):
    assert access.normalize_phone(raw) == expected


@pytest.mark.asyncio
async def test_grant_stops_working_if_the_employee_phone_changes():
    company_id = uuid.uuid4()
    same = _FakeDb([{"phone": "300 123 4567"}])
    assert await access.is_agent_phone_authorized(same, company_id, "573001234567") is True
    # /employees is still open: someone edited the phone after the grant.
    changed = _FakeDb([{"phone": "3119990000"}])
    assert await access.is_agent_phone_authorized(changed, company_id, "573001234567") is False
    assert await access.is_agent_phone_authorized(_FakeDb([]), company_id, "573001234567") is False
    assert await access.is_agent_phone_authorized(_FakeDb([{"phone": ""}]), company_id, "") is False
    sql, params = same.calls[0]
    assert "a.company_id = :company_id" in sql and params["company_id"] == str(company_id)


@pytest.mark.asyncio
async def test_grant_for_an_employee_of_another_company_is_rejected():
    from fastapi import HTTPException

    db = _FakeDb([])  # the employee is not in this company
    with pytest.raises(HTTPException) as exc:
        await access.set_agent_access(db, uuid.uuid4(), uuid.uuid4(), enabled=True, granted_by="x")
    assert exc.value.status_code == 404
    db.commit.assert_not_awaited()
