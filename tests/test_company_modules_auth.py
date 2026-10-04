"""POST /companies/{id}/modules/{code}/activate y /deactivate exigen sesion
(2026-10, TODAS las empresas): Admin V2 o un admin/dueño de ESA misma empresa.

Antes no pedian nada: quien conociera un company_id podia encender o apagar
modulos (incluido mini_panel con su asignacion). Hoy solo los llaman Admin V2
y la Consola v2+, que van con la cookie de Admin V2.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.api.v1.endpoints import companies
from app.web import admin_v2_routes

CID = str(uuid.uuid4())


class TouchedDb:
    """Si un endpoint llega a la base, la prueba lo sabe."""

    def __init__(self):
        self.touched = False

    async def execute(self, *a, **k):
        self.touched = True
        raise AssertionError("no debia llegar a la base")


@pytest.fixture
def api(monkeypatch):
    db = TouchedDb()

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    yield SimpleNamespace(db=db, client=TestClient(app_main.app), mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("action", ["activate", "deactivate"])
def test_without_credentials_is_rejected_before_the_database(api, action):
    response = api.client.post(f"/api/v1/companies/{CID}/modules/carta/{action}", json={"settings": {}})
    assert response.status_code == 401
    assert api.db.touched is False


@pytest.mark.parametrize("action", ["activate", "deactivate"])
def test_staff_of_another_company_or_a_waiter_is_rejected(api, action):
    async def tenant(db, authorization, company_id, *, allowed_roles=None, **_):
        raise HTTPException(status_code=403, detail="tenant_not_allowed")

    api.mp.setattr(companies, "require_company_user_for_tenant", tenant)
    response = api.client.post(f"/api/v1/companies/{CID}/modules/carta/{action}", json={"settings": {}},
                               headers={"Authorization": "Bearer otra-empresa"})
    assert response.status_code == 403 and api.db.touched is False


def _route(path):
    return next(r for r in app_main.app.routes if getattr(r, "path", "") == path and "POST" in r.methods)


@pytest.mark.parametrize("action", ["activate", "deactivate"])
def test_guard_is_admin_v2_or_admin_of_that_same_company(action):
    route = _route(f"/api/v1/companies/{{company_id}}/modules/{{module_code}}/{action}")
    calls = [d.call for d in route.dependant.dependencies]
    assert companies.require_admin_v2_or_tenant_company_admin in calls


@pytest.mark.asyncio
async def test_the_guard_accepts_admin_v2_and_company_admins_only(monkeypatch):
    request = SimpleNamespace()
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=True))
    tenant = AsyncMock(side_effect=AssertionError("con Admin V2 no revisa el token"))
    monkeypatch.setattr(companies, "require_company_user_for_tenant", tenant)
    await companies.require_admin_v2_or_tenant_company_admin(uuid.UUID(CID), request, None, SimpleNamespace())

    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    tenant = AsyncMock(return_value=SimpleNamespace(role="owner"))
    monkeypatch.setattr(companies, "require_company_user_for_tenant", tenant)
    await companies.require_admin_v2_or_tenant_company_admin(uuid.UUID(CID), request, "Bearer x", SimpleNamespace())
    kwargs = tenant.await_args.kwargs
    assert kwargs["allowed_roles"] == companies.COMPANY_ADMIN_ROLES
    assert not {"mesero", "cocina", "caja", "cajero"} & set(kwargs["allowed_roles"]), "un mini panel no enciende modulos"


def test_reading_modules_is_unchanged():
    """GET /companies/{id}/modules no se toca en este cambio (sigue igual)."""
    route = next(r for r in app_main.app.routes if getattr(r, "path", "") == "/api/v1/companies/{company_id}/modules")
    assert companies.require_admin_v2_or_tenant_company_admin not in [d.call for d in route.dependant.dependencies]


def test_only_admin_consoles_call_these_endpoints():
    from pathlib import Path
    import re

    callers = []
    for path in Path("app/web").glob("*.js"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"/modules/[^`\"']*/(activate|deactivate)|/modules/\$\{[a-zA-Z]+\}/\$\{action\}", text):
            callers.append(path.name)
    assert sorted(callers) == ["admin_v2.js", "admin_v2plus_company.js"] or sorted(callers) == ["admin_v2.js"], callers
