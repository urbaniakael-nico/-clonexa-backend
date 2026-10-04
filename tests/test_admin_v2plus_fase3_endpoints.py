"""Fase 3 · endpoints nuevos de solo lectura, con sesion de Admin V2:
- GET /admin-v2/api/catalog/usage: empresas por paquete; por modulo, paquetes
  y empresas encendidas; candidatos a limpieza con la regla de Admin V2.
- GET /admin-v2/api/health/security: variables presentes SIN valores, cierre
  automatico de sesiones y estimado de endpoints sin sesion.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import console_catalog as cc
from app.web import admin_v2plus_companies as ep


class Result:
    def __init__(self, rows=None, scalar=None):
        self.rows, self._scalar = rows or [], scalar

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def scalar(self):
        return self._scalar


class FakeDb:
    def __init__(self):
        self.sql = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.sql.append(sql)
        if "to_regclass" in sql:
            return Result(scalar=True)
        if "FROM company_package_assignments" in sql:
            assert "NOT IN ('archived', 'deleted')" in sql
            return Result([{"package_id": "p1", "companies": 2}])
        if "FROM modules m LEFT JOIN company_modules" in sql:
            return Result([{"code": "crm", "companies_on": 3, "companies_any": 4}, {"code": "viejo", "companies_on": 0, "companies_any": 0},
                           {"code": "en_paquete", "companies_on": 0, "companies_any": 0}, {"code": "apagado_en_una", "companies_on": 0, "companies_any": 1}])
        if "FROM package_modules" in sql:
            return Result([{"code": "crm", "package_code": "bar", "package_name": "Bar"}, {"code": "en_paquete", "package_code": "bar", "package_name": "Bar"}])
        if "GROUP BY closed_at" in sql:
            assert params == {"reason": "expirada_por_inactividad"}
            return Result([{"closed_at": datetime(2026, 10, 4, 23, 25, tzinfo=timezone.utc), "n": 39}])
        if "closed_at >= NOW() - INTERVAL '7 days'" in sql:
            return Result(scalar=39)
        raise AssertionError(sql)


@pytest.mark.asyncio
async def test_catalog_usage_counts_and_cleanup_rule():
    data = await cc.catalog_usage(FakeDb())
    assert data["packages"] == {"p1": {"companies": 2}}
    m = data["modules"]
    assert m["crm"]["companies_on"] == 3 and m["crm"]["packages"] == [{"code": "bar", "name": "Bar"}]
    assert m["viejo"]["cleanup_candidate"] is True
    assert m["en_paquete"]["cleanup_candidate"] is False, "en un paquete: no se limpia"
    assert m["apagado_en_una"]["cleanup_candidate"] is False, "asignado (aunque apagado) a una empresa: no se limpia, igual que v2"
    assert m["crm"]["cleanup_candidate"] is False


@pytest.mark.asyncio
async def test_security_status_never_returns_values(monkeypatch):
    secret = "super-secreto-que-no-debe-salir"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    monkeypatch.setenv("CLONEXA_ADMIN_V2_PASSWORD_BCRYPT", "$2b$12$" + "x" * 53)
    monkeypatch.delenv("CLONEXA_ADMIN_V2_SECRET", raising=False)
    monkeypatch.setenv("CLONEXA_SESSION_IDLE_HOURS", "72")
    data = await cc.security_status(FakeDb(), app_main.app, master_access_mode="bcrypt")
    flat = repr(data)
    assert secret not in flat and "$2b$12$" not in flat
    present = {v["name"]: v["present"] for v in data["variables"]}
    assert present["JWT_SECRET_KEY"] is True and present["CLONEXA_ADMIN_V2_SECRET"] is False
    assert data["session_idle"]["hours"] == 72 and data["session_idle"]["last_run_closed"] == 39 and data["session_idle"]["closed_7d"] == 39
    est = data["open_endpoints"]
    assert est["estimate"] is True and 0 < est["open"] < est["routes_checked"]


def test_open_endpoints_estimate_sees_guarded_routes():
    est = cc.open_endpoints_estimate(app_main.app)
    from fastapi.routing import APIRoute

    by_path = {r.path: r for r in app_main.app.routes if isinstance(r, APIRoute)}
    assert cc._route_has_auth(by_path["/api/v1/companies/{company_id}/access-policy"]) is True
    assert cc._route_has_auth(by_path["/api/v1/companies/{company_id}/modules/{module_code}/activate"]) is True
    assert est["routes_checked"] > 400


@pytest.fixture
def client(monkeypatch):
    db = FakeDb()

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(c=TestClient(app_main.app), mp=monkeypatch, db=db)
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path", ["/admin-v2/api/catalog/usage", "/admin-v2/api/health/security"])
def test_new_endpoints_require_admin_v2_session(client, path):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    assert client.c.get(path).status_code == 401
    assert client.db.sql == []


def test_new_endpoints_answer_with_session(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    assert client.c.get("/admin-v2/api/catalog/usage").json()["modules"]["crm"]["companies_on"] == 3
    body = client.c.get("/admin-v2/api/health/security").json()
    assert {"master_access_mode", "variables", "session_idle", "open_endpoints"} <= set(body)


def test_new_console_scripts_are_served():
    c = TestClient(app_main.app)
    assert "CxConsoleCatalog" in c.get("/admin-v2plus-catalog.js").text
    assert "CxConsoleAdmin" in c.get("/admin-v2plus-admin.js").text
