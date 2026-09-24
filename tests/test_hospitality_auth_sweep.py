"""SECURITY (2026-09-24): barrido de autenticación de hospitality.py, por pasos.

Cada endpoint de CLOSED exige Admin V2 o una sesión de un usuario de esa
misma empresa (require_admin_v2_or_tenant_company_user). Los mini paneles
(mesero, caja, cocina) son usuarios de la empresa con su token, así que
siguen funcionando. Las rutas de PUBLIC_QR las usa la página pública del QR
sin login y deben seguir abiertas (se protegen con la clave de mesa).

Prueba contra la app ASGI real: sin credenciales y con sesión de otra
empresa se rechaza antes de tocar la base; con la sesión correcta, el
endpoint responde con una base vacía falsa.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import hospitality
from app.web import admin_v2_routes

client = TestClient(app_main.app)
BASE = "/api/v1/hospitality/companies/{cid}"

# (method, path, json body) -- paso 1: claves de mesa
CLOSED = [
    ("get", "/qr-tables?count=3", None),
    ("post", "/qr-tables/access", {"table": "Mesa 1"}),
    ("post", "/qr-tables/access/close", {"table": "Mesa 1"}),
]

PUBLIC_QR = [
    ("GET", "/api/v1/hospitality/companies/{company_id}/qr-tables/access"),
    ("POST", "/api/v1/hospitality/companies/{company_id}/qr-tables/access/verify"),
    ("POST", "/api/v1/hospitality/companies/{company_id}/qr-tables/account"),
    ("POST", "/api/v1/hospitality/companies/{company_id}/song-requests"),
    ("POST", "/api/v1/hospitality/companies/{company_id}/orders"),
    ("GET", "/api/v1/hospitality/companies/{company_id}/inventory-lite"),
    ("GET", "/api/v1/hospitality/companies/{company_id}/loyalty-campaigns/active"),
]


def _call(method, path, body, company_id, headers=None):
    url = BASE.format(cid=company_id) + path
    return client.request(method.upper(), url, json=body if body is not None else None, headers=headers or {})


class _EmptyDb:
    """Any SQL returns no rows (enough for the endpoints to answer)."""

    def __init__(self, company_id):
        self.company_id = company_id
        self.commit = AsyncMock()

    async def execute(self, statement, params=None):
        if params and "company_id" in params:
            assert str(params["company_id"]) == self.company_id, "nunca otra empresa"
        empty = SimpleNamespace(all=lambda: [], first=lambda: None)
        return SimpleNamespace(mappings=lambda: empty, first=lambda: None, scalar=lambda: 0, fetchall=lambda: [])


@pytest.fixture(autouse=True)
def _no_real_db_in_middlewares(monkeypatch):
    # The IP-policy, archived-company and auth-audit middlewares open their
    # own DB session per request; with no test database each one waits for a
    # connection timeout. They are not what these tests measure.
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)


@pytest.fixture
def session_as(monkeypatch):
    """Log in as a user of `user_company` with `role` (no Admin V2)."""

    def _login(user_company, role="company_admin"):
        user = SimpleNamespace(company_id=uuid.UUID(user_company), role=role, status="active")
        monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
        monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(return_value=user))
        return {"Authorization": "Bearer token"}

    return _login


@pytest.mark.parametrize("method,path,body", CLOSED)
def test_hospitality_closed_endpoint_rejects_no_credentials(method, path, body):
    response = _call(method, path, body, str(uuid.uuid4()))
    assert response.status_code in (401, 403), f"{method.upper()} {path} -> {response.status_code}: {response.text}"


@pytest.mark.parametrize("method,path,body", CLOSED)
def test_hospitality_closed_endpoint_rejects_another_company(method, path, body, session_as):
    headers = session_as(str(uuid.uuid4()))
    response = _call(method, path, body, str(uuid.uuid4()), headers)
    assert response.status_code == 403, response.text
    assert "tenant_not_allowed" in response.text


@pytest.mark.parametrize("role", ["company_admin", "operador", "mesero", "caja", "cocina"])
@pytest.mark.parametrize("method,path,body", CLOSED)
def test_hospitality_closed_endpoint_accepts_its_own_company(method, path, body, role, session_as, monkeypatch):
    company_id = str(uuid.uuid4())
    headers = session_as(company_id, role)
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))

    async def fake_db():
        yield _EmptyDb(company_id)

    app_main.app.dependency_overrides[get_db] = fake_db
    try:
        response = _call(method, path, body, company_id, headers)
    finally:
        app_main.app.dependency_overrides.pop(get_db, None)
    assert response.status_code in (200, 201), f"{role} {method.upper()} {path} -> {response.status_code}: {response.text}"


def test_hospitality_admin_v2_session_is_also_accepted(monkeypatch):
    company_id = str(uuid.uuid4())
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=True))
    monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(side_effect=AssertionError("no debe pedir token")))
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))

    async def fake_db():
        yield _EmptyDb(company_id)

    app_main.app.dependency_overrides[get_db] = fake_db
    try:
        response = _call("get", "/qr-tables?count=2", None, company_id)
    finally:
        app_main.app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("method,path", PUBLIC_QR)
def test_hospitality_public_qr_routes_stay_open(method, path):
    route = next(
        r for r in app_main.app.routes
        if getattr(r, "path", "") == path and method in getattr(r, "methods", set())
    )
    names = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
    assert "require_admin_v2_or_tenant_company_user" not in names, path


def test_hospitality_waiter_ordering_direct_calls_still_match_signatures():
    # waiter_ordering.py calls these as plain Python functions; the guard is a
    # trailing keyword parameter with a default, so those calls are unchanged.
    import inspect

    for fn in (hospitality.hospitality_qr_tables, hospitality.activate_hospitality_table_access, hospitality.close_hospitality_table_access):
        params = list(inspect.signature(fn).parameters.values())
        assert params[-1].name == "_actor" and params[-1].default is not inspect.Parameter.empty
