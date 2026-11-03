"""062A seguridad: calcular / listar / ver / cerrar periodos de nomina respondian SIN sesion
en empresas sin el modulo de meseros (VOLTAGE incluida). Ahora, sin meseros: Admin V2 o
un usuario de ESA empresa con rol de dueno / administrador / direccion.
Con meseros: la regla de siempre (cualquier usuario de la empresa menos "administrador").

Por HTTP (TestClient) con el router real; la base y la sesion se simulan."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import company_users, payroll

COMPANY = uuid.uuid4()
OTHER = uuid.uuid4()
USERS = {
    "owner": SimpleNamespace(company_id=COMPANY, role="company_admin", full_name="Dueño"),
    "gerencia": SimpleNamespace(company_id=COMPANY, role="gerencia", full_name="Directora"),
    "operator": SimpleNamespace(company_id=COMPANY, role="operator", full_name="Operario"),
    "mesero": SimpleNamespace(company_id=COMPANY, role="mesero", full_name="Mesero"),
    "administrador": SimpleNamespace(company_id=COMPANY, role="administrador", full_name="Adm"),
    "other_owner": SimpleNamespace(company_id=OTHER, role="company_admin", full_name="Dueño otra"),
}
ROUTES = [
    ("post", "/api/v1/payroll/companies/{c}/periods/calculate", {"period_start": "2026-11-01", "period_end": "2026-11-07"}),
    ("get", "/api/v1/payroll/companies/{c}/periods", None),
    ("get", "/api/v1/payroll/companies/{c}/periods/" + str(uuid.uuid4()), None),
    ("post", "/api/v1/payroll/companies/{c}/periods/close", {"period_start": "2026-11-01", "period_end": "2026-11-07"}),
]


@pytest.fixture()
def client(monkeypatch):
    state = {"waiter": False}

    async def fake_user(db, token):
        if not token:
            raise HTTPException(status_code=401, detail="missing_token")
        if token not in USERS:
            raise HTTPException(status_code=401, detail="invalid_token")
        return USERS[token]

    async def fake_module(db, company_id, module_codes):
        codes = deps._normalize_codes(module_codes)
        if codes and "waiter_ordering" in codes and not state["waiter"]:
            raise HTTPException(status_code=403, detail="module_not_enabled")

    async def no_admin_v2(request, db):
        return False

    async def no_co(db, company_id):
        return None

    async def snapshot(db, company_id, start, end):
        return {"period": {"period_start": str(start), "period_end": str(end)}, "rows": [], "totals": {}}

    async def nothing(*a, **k):
        return None

    async def period(db, company_id, data):
        from datetime import date
        return date(2026, 11, 1), date(2026, 11, 7)

    monkeypatch.setattr(deps, "get_current_company_user", fake_user)
    monkeypatch.setattr(deps, "require_enabled_module", fake_module)
    monkeypatch.setattr(company_users, "require_enabled_module", fake_module, raising=False)
    monkeypatch.setattr(payroll, "active_admin_v2_session", no_admin_v2)
    from app.web import admin_v2_routes

    monkeypatch.setattr(admin_v2_routes, "_active_session", no_admin_v2)
    monkeypatch.setattr(payroll, "_cx_co_state_049A", no_co)
    monkeypatch.setattr(payroll, "ensure_payroll_storage", nothing)
    monkeypatch.setattr(payroll, "calculate_period_snapshot", snapshot)
    monkeypatch.setattr(payroll, "period_from_payload_049L", period)
    monkeypatch.setattr(payroll.cx_employee_roles_051a, "load_config", nothing)
    monkeypatch.setattr(payroll.cx_employee_roles_051a, "relabel", lambda snap, cfg: snap)

    app = FastAPI()
    app.include_router(payroll.router, prefix="/api/v1/payroll")

    async def fake_db():
        yield SimpleNamespace()

    app.dependency_overrides[deps.get_db] = fake_db
    app.dependency_overrides[payroll.get_db] = fake_db
    c = TestClient(app, raise_server_exceptions=False)
    c.state = state
    return c


def call(client, method, path, body, token=None, company=COMPANY):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = path.format(c=company)
    return client.post(url, json=body or {}, headers=headers) if method == "post" else client.get(url, headers=headers)


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_without_waiters_no_session_is_401(client, method, path, body):
    assert call(client, method, path, body).status_code == 401


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_without_waiters_other_company_or_role_is_403(client, method, path, body):
    assert call(client, method, path, body, token="other_owner").status_code == 403, "dueño de OTRA empresa"
    assert call(client, method, path, body, token="operator").status_code == 403, "usuario de la empresa sin rol de dueño"
    assert call(client, method, path, body, token="mesero").status_code == 403


def test_without_waiters_owner_and_director_get_200_on_calculate(client):
    method, path, body = ROUTES[0]
    for token in ("owner", "gerencia"):
        res = call(client, method, path, body, token=token)
        assert res.status_code == 200, (token, res.text)
        assert res.json()["source"] == "calculated"


def test_with_waiters_the_rule_is_exactly_as_before(client):
    client.state["waiter"] = True
    method, path, body = ROUTES[0]
    assert call(client, method, path, body).status_code == 401, "sin sesión: 401 como siempre"
    assert call(client, method, path, body, token="mesero").status_code == 200, "con meseros: cualquier usuario de la empresa"
    assert call(client, method, path, body, token="operator").status_code == 200
    assert call(client, method, path, body, token="owner").status_code == 200
    assert call(client, method, path, body, token="administrador").status_code == 403, "menos el rol administrador"
    assert call(client, method, path, body, token="other_owner").status_code == 403, "otra empresa"


def test_every_payroll_route_requires_a_session():
    """Ninguna ruta de nomina queda sin una dependencia de sesion."""
    from app.api.v1.endpoints import payroll_v2

    guards = {payroll._require_payroll_owner_062A, payroll._require_period_reader_049L, payroll._require_period_admin_049L}
    for router in (payroll.router, payroll_v2.router):
        for r in router.routes:
            calls = {d.call for d in r.dependant.dependencies}
            assert calls & guards, f"{r.path} sin sesión"


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_operator_only_where_the_company_allows_it_and_always_with_session(client, monkeypatch, method, path, body):
    """payroll_operator_access (hoy solo Velvet): el operario de ESA empresa entra; sin
    sesion sigue en 401 y otra empresa en 403. Donde no esta, el operario queda en 403."""
    allowed = {str(COMPANY)}

    async def access(db, company_id):
        return str(company_id) in allowed

    monkeypatch.setattr(payroll, "_payroll_operator_access_062A", access)
    assert call(client, method, path, body).status_code == 401, "sin sesión: 401 también en la empresa con acceso"
    assert call(client, method, path, body, token="other_owner").status_code == 403, "otra empresa: 403"
    assert call(client, method, path, body, token="mesero").status_code == 403, "solo operator, no otros roles"
    if method == "post" and path.endswith("/calculate"):
        assert call(client, method, path, body, token="operator").status_code == 200, "operario con acceso de su empresa"
    else:
        assert call(client, method, path, body, token="operator").status_code != 403, "pasa la sesión (lo demás es de la ruta)"
    allowed.clear()
    assert call(client, method, path, body, token="operator").status_code == 403, "sin el permiso de la empresa: 403"


def test_operator_access_reads_the_payroll_module_settings():
    import asyncio

    class Res:
        def __init__(self, row):
            self.row = row

        def first(self):
            return self.row

    class Db:
        def __init__(self, settings):
            self.settings = settings

        async def execute(self, sql, params):
            assert "lower(m.code) = 'payroll'" in str(sql) and params["c"] == str(COMPANY)
            return Res((self.settings,) if self.settings is not None else None)

    run = lambda settings: asyncio.run(payroll._payroll_operator_access_062A(Db(settings), COMPANY))  # noqa: E731
    assert run({"payroll_operator_access": True}) is True
    assert run('{"payroll_operator_access": true}') is True
    assert run({"payroll_operator_access": "true"}) is False and run({}) is False and run(None) is False
