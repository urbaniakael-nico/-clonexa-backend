"""Recordatorio de pago en el panel: acceso validado en el SERVIDOR.

Solo dueño o admin con la sesion del panel principal (scope "client"). Un
token de mini panel (aunque el usuario sea admin), un mesero, cocina, caja,
operario, gerente o consulta reciben 403; sin token, 401. La empresa sale del
token, nunca de la URL.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.api.v1.endpoints import billing_reminder as ep
from app.services import billing_contracts as bc
from app.services import brand_media as media
from app.services import company_locale

CID = str(uuid.uuid4())
URL = "/api/v1/billing-reminder"


class FakeDB:
    async def execute(self, *a, **kw):
        return SimpleNamespace(scalar=lambda: "Bar Demo")


@pytest.fixture
def client(monkeypatch):
    async def fake_db():
        yield FakeDB()

    app_main.app.dependency_overrides[get_db] = fake_db
    tokens = {
        "owner": ({"scope": "client", "company_id": CID}, "company_admin"),
        "dueno": ({"scope": "client", "company_id": CID}, "dueño"),
        "mini_admin": ({"scope": "mini_panel", "mini_panel": True, "panel_type": "cashier", "company_id": CID}, "company_admin"),
        "mesero": ({"scope": "mini_panel", "mini_panel": True, "panel_type": "waiter", "company_id": CID}, "mesero"),
    }
    for role in ("mesero", "cocina", "caja", "barman", "operario", "manager", "gerente", "viewer", "supervisor"):
        tokens[f"client_{role}"] = ({"scope": "client", "company_id": CID}, role)

    def decode(token):
        if token not in tokens:
            raise HTTPException(status_code=401, detail="Token inválido o expirado.")
        return tokens[token][0]

    async def current_user(db, token):
        return SimpleNamespace(company_id=uuid.UUID(CID), role=tokens[token][1], email="persona@demo.test", full_name="Persona")

    monkeypatch.setattr(ep, "decode_access_token", decode)
    monkeypatch.setattr(ep, "get_current_company_user", current_user)

    async def locale(db, cid):
        return {"timezone": "America/Bogota", "language": "es", "currency": "COP"}

    monkeypatch.setattr(company_locale, "get_company_locale", locale)
    seen = {}

    async def reminder(db, cid, today):
        seen["company"] = cid
        return {"installment_id": "i1", "period": date(2026, 10, 1), "amount": Decimal("220000"), "balance": Decimal("220000"), "partial": False,
                "due_date": date(2026, 10, 20), "state": "open", "currency": "COP"}

    async def provider(db):
        return {"trade_name": "CLONEXA", "has_qr": True}

    async def theme(db, cid):
        return {"primary": "#123456", "secondary": "#00ff88", "background": "#050509", "text": "#f8fafc"}

    monkeypatch.setattr(bc, "reminder", reminder)
    monkeypatch.setattr(bc, "get_provider", provider)
    monkeypatch.setattr(ep, "panel_theme", theme)
    yield SimpleNamespace(c=TestClient(app_main.app, base_url="https://testserver"), seen=seen, mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


def _auth(name):
    return {"Authorization": f"Bearer {name}"}


def test_owner_sees_the_reminder_for_its_own_company(client):
    for who in ("owner", "dueno"):
        r = client.c.get(URL, headers=_auth(who))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["show"] and data["company_name"] == "Bar Demo" and data["balance"] == 220000 and data["theme"]["primary"] == "#123456"
        assert r.headers["cache-control"] == "no-store"
        assert client.seen["company"] == CID, "la empresa sale del token"
    body = r.text.lower()
    assert "suspend" not in body and "bloque" not in body


def test_other_roles_and_mini_panels_get_403_and_no_token_401(client):
    for path, method in ((URL, "get"), (f"{URL}/qr", "get"), (f"{URL}/paid", "post")):
        assert getattr(client.c, method)(path).status_code == 401, path
        assert getattr(client.c, method)(path, headers=_auth("desconocido")).status_code == 401
        for who in ("mini_admin", "mesero", "client_mesero", "client_cocina", "client_caja", "client_barman", "client_operario",
                    "client_manager", "client_gerente", "client_viewer", "client_supervisor"):
            assert getattr(client.c, method)(path, headers=_auth(who)).status_code == 403, (path, who)


def test_paid_route_validates_size_and_type(client):
    client.mp.setattr(media, "configured", lambda: True)
    calls = {}

    async def report(db, cid, raw, amount, actor, today, put):
        calls.update(cid=cid, size=len(raw), amount=amount, actor=actor)
        if not raw.startswith(b"%PDF-"):
            raise bc.BillingInvalid("archivo", "solo imagen (PNG, JPG, WebP) o PDF")
        return {"id": "p1", "amount": Decimal("220000"), "installment_id": "i1"}

    client.mp.setattr(bc, "report_payment", report)
    ok = client.c.post(f"{URL}/paid?amount=220000", content=b"%PDF-1.4\n%%EOF\n", headers={**_auth("owner"), "Content-Type": "application/pdf"})
    assert ok.status_code == 200 and calls["cid"] == CID and calls["amount"] == "220000" and calls["actor"] == "persona@demo.test"
    bad = client.c.post(f"{URL}/paid", content=b"<html>", headers={**_auth("owner"), "Content-Type": "text/html"})
    assert bad.status_code == 422
    big = client.c.post(f"{URL}/paid", content=b"%PDF-" + b"0" * (5 * 1024 * 1024 + 10), headers={**_auth("owner"), "Content-Type": "application/pdf"})
    assert big.status_code == 413


def test_the_endpoint_is_not_open():
    from app.services.console_catalog import _route_has_auth

    routes = [r for r in app_main.app.routes if str(getattr(r, "path", "")).startswith(URL)]
    assert len(routes) == 3 and all(_route_has_auth(r) for r in routes)
