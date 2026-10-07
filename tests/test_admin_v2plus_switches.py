"""Fase 3 · Interruptores.

- El servidor (POST .../modules/{code}/activate, el mismo de Admin V2) mezcla
  settings: cambiar una clave no altera ninguna otra clave ni otra empresa.
- Registro unico valido; matriz con estado por empresa y bloqueo con motivo.
- GET /admin-v2/api/switches exige sesion de Admin V2.
- El motivo llega a la auditoria por la cabecera X-Cx-Audit-Note.
"""
from __future__ import annotations

import copy
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.api.v1.endpoints import company_modules as cm
from app.services import admin_audit
from app.services import switch_registry as sr
from app.web import admin_v2plus_companies as ep


# ------------------------------------------------------- mezcla del servidor
class Commit:
    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_activate_changes_only_the_sent_key_and_only_that_company(monkeypatch):
    a, b = uuid.uuid4(), uuid.uuid4()
    original = {"segments": {"caja": {"enabled": True}}, "cash_count": True, "quantity_buttons": ["1/2", "1"], "menu_emojis": False}
    rows = {a: SimpleNamespace(enabled=True, activated_at=None, settings=copy.deepcopy(original)),
            b: SimpleNamespace(enabled=True, activated_at=None, settings=copy.deepcopy(original))}
    module = SimpleNamespace(id=uuid.uuid4(), code="waiter_ordering")
    monkeypatch.setattr(cm, "get_module_by_code_or_404", AsyncMock(return_value=module))
    monkeypatch.setattr(cm, "get_company_module_link", AsyncMock(side_effect=lambda db, cid, mid: rows[cid]))
    monkeypatch.setattr(cm, "get_company_module_out", AsyncMock(side_effect=lambda db, cid, mid: rows[cid]))

    await cm.activate_company_module(a, "waiter_ordering", {"settings": {"menu_emojis": True}}, Commit())

    assert rows[a].settings == {**original, "menu_emojis": True}, "solo cambia la clave enviada"
    assert rows[b].settings == original, "la otra empresa no cambia"
    await cm.activate_company_module(a, "waiter_ordering", {"settings": {"menu_emojis": False}}, Commit())
    assert rows[a].settings == original and rows[a].enabled is True, "apagar el interruptor no apaga el modulo"


# ------------------------------------------------------------ registro
def test_registry_is_valid_and_matches_the_approved_inventory():
    data = sr.registry()
    keys = {s["key"] for s in data["switches"]}
    assert len(keys) == 16 and "references_v2" in keys
    delicate = {s["key"] for s in data["switches"] if s.get("delicate")}
    assert {"sales_ledger", "cashier_redesign", "checkout_v2"} <= delicate
    assert sr.required_modules() == ["domicilios_whatsapp", "qr", "references", "waiter_ordering"]
    bad = copy.deepcopy(data)
    bad["switches"][0]["depends_on"] = [{"key": "no_existe", "why": "x"}]
    with pytest.raises(ValueError):
        sr.validate(bad)
    bad = copy.deepcopy(data)
    bad["switches"][1]["delicate"] = True
    bad["switches"][1].pop("delicate_reason", None)
    with pytest.raises(ValueError):
        sr.validate(bad)


def test_flag_constants_in_code_are_registered():
    from app.api.v1.endpoints import cash_count, sale_document, waiter_ordering as wo
    from app.services import sales_ledger, short_links
    from app.web import brand_inject

    keys = {s["key"] for s in sr.registry()["switches"]}
    in_code = {cash_count.FLAG, sale_document.DELIVERY_PRINT_FLAG, sales_ledger.FLAG, short_links.FLAG, brand_inject.FLAG,
               wo.QUANTITY_BUTTONS_FLAG, wo.CASHIER_DIRECT_SALE_FLAG, wo.CASHIER_REDESIGN_FLAG, wo.QUANTITY_PICKER_FLAG,
               wo.MINI_PANEL_BRAND_FLAG, wo.KITCHEN_COLUMNS_FLAG, wo.KITCHEN_ROSTER_FLAG}
    assert in_code <= keys


def test_company_state_locks_when_a_required_module_is_off():
    state = sr.company_state({
        "waiter_ordering": {"enabled": True, "settings": {"cash_count": True, "delivery_print": True}},
        "qr": {"enabled": False, "settings": {"qr_bar_menu": True}},
    })
    assert state["cash_count"] == {"on": True, "locked": False, "missing_modules": []}
    assert state["delivery_print"]["locked"] is True and state["delivery_print"]["missing_modules"] == ["domicilios_whatsapp"]
    assert state["qr_bar_menu"]["on"] is False, "modulo apagado: el interruptor no esta encendido"
    assert state["qr_bar_menu"]["locked"] is True
    assert state["checkout_v2"]["missing_modules"] == ["domicilios_whatsapp"]


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows)


class FakeDb:
    def __init__(self):
        self.sql = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.sql.append((sql, params))
        assert "NOT IN ('archived', 'deleted')" in sql
        assert params == {"codes": ["domicilios_whatsapp", "qr", "references", "waiter_ordering"]}
        base = {"slug": "s", "status": "active", "settings_json": None}
        return Result([
            {**base, "company_id": "c1", "name": "Asadero", "settings_json": {"kind": "registrada"}, "code": "waiter_ordering", "enabled": True,
             "settings": json.dumps({"cash_count": True, "secreto_de_otro_ajuste": "no debe salir"})},
            {**base, "company_id": "c2", "name": "Demo", "settings_json": {"kind": "demo"}, "code": None, "enabled": None, "settings": None},
        ])


@pytest.mark.asyncio
async def test_matrix_returns_only_registered_keys():
    data = await sr.matrix(FakeDb())
    by = {c["id"]: c for c in data["companies"]}
    assert by["c1"]["switches"]["cash_count"]["on"] is True
    assert by["c1"]["kind"] == "registrada" and by["c2"]["kind"] == "demo"
    assert all(s["locked"] for s in by["c2"]["switches"].values())
    assert "no debe salir" not in json.dumps(data)


# ------------------------------------------------------------ endpoint
@pytest.fixture
def client(monkeypatch):
    db = FakeDb()

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(c=TestClient(app_main.app), mp=monkeypatch, db=db)
    app_main.app.dependency_overrides.pop(get_db, None)


def test_switches_endpoint_requires_admin_v2_session(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    assert client.c.get("/admin-v2/api/switches").status_code == 401
    assert client.db.sql == []
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    body = client.c.get("/admin-v2/api/switches").json()
    assert len(body["registry"]["switches"]) == 16 and len(body["companies"]) == 2


def test_switches_script_is_served():
    assert "CxSwitchRegistry" in TestClient(app_main.app).get("/admin-v2plus-switches.js").text


# ------------------------------------------------------------ auditoría
def test_audit_note_header_is_decoded_and_cleaned():
    raw = quote(json.dumps({"interruptor": "sales_ledger", "valor": False, "motivo": "cierre de mes", "password": "x"}))
    note = admin_audit.note_from_header(raw)
    assert note == {"interruptor": "sales_ledger", "valor": False, "motivo": "cierre de mes"}, "nada con forma de secreto"
    assert admin_audit.note_from_header("%%no-json") is None
    assert admin_audit.note_from_header("") is None


@pytest.mark.asyncio
async def test_audit_middleware_stores_the_reason(monkeypatch):
    written = []
    monkeypatch.setattr(admin_audit, "admin_actor", AsyncMock(return_value="admin@clonexa"))
    monkeypatch.setattr(admin_audit, "write_entry", AsyncMock(side_effect=lambda e: written.append(e)))

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    mw = admin_audit.AdminAuditMiddleware(app)
    note = quote(json.dumps({"interruptor": "menu_emojis", "valor": True, "motivo": "lo pidió el dueño"}))
    scope = {"type": "http", "method": "POST", "path": f"/api/v1/companies/{uuid.uuid4()}/modules/waiter_ordering/activate",
             "headers": [(b"x-cx-audit-note", note.encode("latin-1"))], "client": ("1.2.3.4", 1), "state": {}}

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(_):
        pass

    await mw(scope, receive, send)
    assert written and written[0]["detail"] == {"interruptor": "menu_emojis", "valor": True, "motivo": "lo pidió el dueño"}
