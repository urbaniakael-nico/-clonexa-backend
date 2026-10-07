"""Referencias v2: toda ruta nueva exige sesion (Admin V2 o usuario de ESA
empresa); un usuario de otra empresa recibe 403. Las rutas de siempre no
cambian (no se les agrego nada)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.web import admin_v2_routes as v2

A, B = str(uuid.uuid4()), str(uuid.uuid4())
R = str(uuid.uuid4())
PREFIX = "/api/v1/references-v1/companies"
ROUTES = [("get", f"{PREFIX}/{A}/v2/catalog"), ("post", f"{PREFIX}/{A}/v2/references/{R}/classify"), ("post", f"{PREFIX}/{A}/v2/movements"),
          ("post", f"{PREFIX}/{A}/v2/movements/{R}/void"), ("get", f"{PREFIX}/{A}/v2/references/{R}/balance"), ("get", f"{PREFIX}/{A}/v2/board"),
          ("post", f"{PREFIX}/{A}/v2/catalog-create"), ("post", f"{PREFIX}/{A}/v2/references/{R}/add-size")]


class Db:
    async def execute(self, *a, **k):
        raise AssertionError("sin sesion no se toca la base")

    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.fixture
def client(monkeypatch):
    async def fake_db():
        yield Db()

    app_main.app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(v2, "_active_session", AsyncMock(return_value=False))
    yield SimpleNamespace(c=TestClient(app_main.app, base_url="https://testserver"), mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


def test_new_routes_require_a_session(client):
    for method, path in ROUTES:
        res = getattr(client.c, method)(path, **({"json": {}} if method == "post" else {}))
        assert res.status_code == 401, (path, res.status_code)
    registered = {r.path for r in app_main.app.routes if "/references-v1/" in getattr(r, "path", "") and "/v2/" in r.path}
    assert len(registered) == 8, "si se agrega una ruta nueva, se agrega aqui con su prueba de sesion"


def test_a_user_of_another_company_gets_403(client):
    async def user_of_b(db, token):
        return SimpleNamespace(company_id=B, role="company_admin", full_name="Otra", status="active")

    client.mp.setattr(deps, "get_current_company_user", user_of_b)
    for method, path in ROUTES:
        res = getattr(client.c, method)(path, headers={"Authorization": "Bearer x"}, **({"json": {}} if method == "post" else {}))
        assert res.status_code == 403, (path, res.status_code)


def test_bot_routes_did_not_gain_anything():
    """Rutas de siempre: mismas firmas (sin dependencias nuevas)."""
    from app.api.v1.endpoints import references_v1 as refs
    import inspect

    assert list(inspect.signature(refs.bot_reference_options).parameters) == ["company_id", "db"]
    assert list(inspect.signature(refs.bot_reference_sizes).parameters) == ["company_id", "name", "db"]
    assert list(inspect.signature(refs.list_references).parameters) == ["company_id", "q", "date_from", "date_to", "bot_active", "channel", "db"]
