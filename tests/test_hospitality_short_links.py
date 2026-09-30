"""Links cortos /c/CODIGO (049Y): el corto abre el panel correcto, el largo
sigue funcionando, nunca redirige fuera ni a otra empresa, el portal los pide
con sesion y el link de domicilios del cliente es corto con el interruptor."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import short_links as endpoint
from app.services import short_links as sl
from app.services import whatsapp_delivery as wd

ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"
client = TestClient(app_main.app)


class Result:
    def __init__(self, rows=None):
        self.rows = rows or []

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def first(self):
        return self.rows[0] if self.rows else None


class LinkDb:
    def __init__(self):
        self.flags = {ASADERO: {"short_links": True}, TTM: {}}
        self.links: dict[str, dict] = {}
        self.delivery: dict[str, str] = {}  # token_hash -> company
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        if sql.startswith("SELECT cm.settings FROM company_modules cm") and "waiter_ordering" in sql:
            cid = str(p["company_id"])
            return Result([{"settings": self.flags[cid]}] if cid in self.flags else [])
        if sql.startswith("SELECT code FROM short_links WHERE company_id"):
            return Result([{"code": c} for c, r in self.links.items() if r["company_id"] == p["c"] and r["target"] == p["t"]][:1])
        if sql.startswith("INSERT INTO short_links"):
            if p["code"] in self.links or any(r["company_id"] == p["c"] and r["target"] == p["t"] for r in self.links.values()):
                return Result([])
            self.links[p["code"]] = {"company_id": p["c"], "target": p["t"]}
            return Result([{"code": p["code"]}])
        if sql.startswith("SELECT company_id, target FROM short_links WHERE code"):
            row = self.links.get(p["code"])
            return Result([{"company_id": uuid.UUID(row["company_id"]), "target": row["target"]}] if row else [])
        if sql.startswith("SELECT company_id FROM whatsapp_delivery_sessions WHERE token_hash"):
            cid = self.delivery.get(p["h"])
            return Result([{"company_id": uuid.UUID(cid)}] if cid else [])
        raise AssertionError(f"SQL no esperado: {sql[:160]}")


USERS = {
    "dueno": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="company_admin", full_name="Dueño", settings_json={}),
    "ttm": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(TTM), role="company_admin", full_name="T", settings_json={}),
}


@pytest.fixture
def fake(monkeypatch):
    db = LinkDb()

    async def get_user(_db, token):
        user = USERS.get(token)
        if not user:
            raise HTTPException(status_code=401, detail="Token requerido.")
        return user

    async def fake_db():
        yield db

    monkeypatch.setattr(deps, "get_current_company_user", get_user)
    monkeypatch.setattr(endpoint, "active_admin_v2_session", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    yield db
    app_main.app.dependency_overrides.pop(get_db, None)


def ask(links, token="dueno", company=ASADERO):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(f"/api/v1/short-links/companies/{company}/mini-panels", json={"links": links}, headers=headers)


def test_hospitality_short_link_codes_are_short_and_unambiguous():
    code = sl.new_code()
    assert len(code) == 6 and all(ch in sl.ALPHABET for ch in code)
    assert not set("01OIL") & set(sl.ALPHABET)
    assert sl.clean_code(" abc234 ") == "ABC234"
    assert sl.clean_code("../../x") == "" and sl.clean_code("") == ""


def test_hospitality_short_link_only_targets_this_company_mini_panels():
    assert sl.panel_target(ASADERO, f"https://x.up.railway.app/mini-panel/caja?company_id={ASADERO}") == f"/mini-panel/caja?company_id={ASADERO}"
    assert sl.panel_target(ASADERO, f"/mini-panel/login?company_id={ASADERO}&type=store") == f"/mini-panel/login?company_id={ASADERO}&type=store"
    assert sl.panel_target(ASADERO, f"/mini-panel/caja?company_id={TTM}") == "", "nunca otra empresa"
    assert sl.panel_target(ASADERO, f"/client?company_id={ASADERO}") == "", "solo mini paneles"
    assert sl.panel_target(ASADERO, f"//evil.com/mini-panel/caja?company_id={ASADERO}").startswith("/mini-panel/"), "siempre ruta interna"
    assert sl.panel_target(ASADERO, f"/mini-panel/../admin?company_id={ASADERO}") == ""
    assert sl.panel_target(ASADERO, f"/mini-panel/caja?company_id={ASADERO}&next=https://evil.com") == f"/mini-panel/caja?company_id={ASADERO}"


def test_hospitality_short_link_portal_gets_the_same_code_every_time(fake):
    long_caja = f"https://clonexa.app/mini-panel/caja?company_id={ASADERO}"
    long_mesero = f"https://clonexa.app/mini-panel/mesero?company_id={ASADERO}"
    first = ask([long_caja, long_mesero, f"/mini-panel/caja?company_id={TTM}"])
    assert first.status_code == 200 and first.json()["enabled"] is True
    links = first.json()["links"]
    assert set(links) == {long_caja, long_mesero}, "el link de otra empresa se ignora"
    assert links[long_caja].startswith("/c/") and len(links[long_caja]) == 9
    assert links[long_caja] != links[long_mesero]
    assert ask([long_caja]).json()["links"][long_caja] == links[long_caja], "el mismo codigo siempre"


def test_hospitality_short_link_opens_the_right_panel_and_the_long_one_still_works(fake):
    long_caja = f"/mini-panel/caja?company_id={ASADERO}"
    short = ask([long_caja]).json()["links"][long_caja]
    res = client.get(short, follow_redirects=False)
    assert res.status_code == 302 and res.headers["location"] == long_caja
    assert client.get(short.lower(), follow_redirects=False).headers["location"] == long_caja, "sin importar mayusculas"
    assert client.get(long_caja).status_code == 200, "el link largo sigue funcionando"
    missing = client.get("/c/ZZZZZZ", follow_redirects=False)
    assert missing.status_code == 404 and "no existe" in missing.text


def test_hospitality_short_link_delivery_code_opens_the_customer_carta(fake):
    code = sl.new_code(sl.DELIVERY_CODE_LENGTH)
    fake.delivery[wd.token_hash(code)] = ASADERO
    res = client.get(f"/c/{code}", follow_redirects=False)
    assert res.status_code == 302 and res.headers["location"] == f"/domicilio?c={ASADERO}&s={code}"


def test_hospitality_short_link_portal_endpoint_requires_session_and_the_switch(fake):
    link = f"/mini-panel/caja?company_id={ASADERO}"
    assert ask([link], token=None).status_code == 401
    assert ask([link], token="ttm").status_code in (401, 403), "nunca de otra empresa"
    off = ask([f"/mini-panel/caja?company_id={TTM}"], token="ttm", company=TTM)
    assert off.status_code == 200 and off.json() == {"enabled": False, "links": {}}, "sin el interruptor, el link largo de siempre"
    assert not fake.links


class LineDb:
    def __init__(self, short):
        self.short = short
        self.calls = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.calls.append((sql, params or {}))
        if "waiter_ordering" in sql:
            return Result([{"settings": {"short_links": self.short}}])
        if "FROM company_modules cm" in sql:
            settings = wd.normalize_settings({"schedule": {d: [{"from": "00:00", "to": "23:59"}] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}})
            return Result([{"settings": json.dumps(settings)}])
        if "FROM companies WHERE id" in sql:
            return Result([{"name": "Asadero El Socio", "timezone": "America/Bogota"}])
        return Result([])


@pytest.mark.asyncio
@pytest.mark.parametrize("short", [True, False])
async def test_hospitality_short_link_customer_gets_a_short_delivery_link(short):
    db = LineDb(short)
    now = datetime(2026, 9, 28, 12, 0, tzinfo=ZoneInfo("America/Bogota"))
    reply = await wd.customer_reply(db, company_id=uuid.UUID(ASADERO), from_phone="3001234567", now=now)
    insert = next(p for sql, p in db.calls if sql.startswith("INSERT INTO whatsapp_delivery_sessions"))
    if short:
        code = reply.split("/c/")[1].split()[0]
        assert len(code) == sl.DELIVERY_CODE_LENGTH and "domicilio?c=" not in reply
        assert insert["token_hash"] == wd.token_hash(code), "el codigo no se guarda en claro"
    else:
        assert f"/domicilio?c={ASADERO}&s=" in reply and "/c/" not in reply


def test_hospitality_short_link_migration():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "migrations/versions/022m_short_links.py"
    spec = importlib.util.spec_from_file_location("mig_022m", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "022l_cash_close_incidents"
    source = path.read_text(encoding="utf-8")
    assert module.TARGET_COMPANY_ID == ASADERO and '"short_links": true' in source
