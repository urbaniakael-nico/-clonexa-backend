"""reference_lifecycle: toda ruta exige sesion de administrador de ESA empresa (o Admin V2), desde el primer dia."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import companies
from app.services import reference_lifecycle as svc
from app.web import admin_v2_routes as v2

A, B = str(uuid.uuid4()), str(uuid.uuid4())
R = str(uuid.uuid4())
PREFIX = f"/api/v1/reference-lifecycle/companies/{A}"
ROUTES = [("get", f"{PREFIX}/state"), ("get", f"{PREFIX}/search?q=x"), ("get", f"{PREFIX}/account?key=x"), ("post", f"{PREFIX}/produced-correction"),
          ("post", f"{PREFIX}/rename"), ("post", f"{PREFIX}/close-size"), ("post", f"{PREFIX}/reopen"), ("post", f"{PREFIX}/requests/{R}/approve")]


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
    monkeypatch.setattr(companies, "admin_v2_or_company_preview", AsyncMock(return_value=False))
    yield SimpleNamespace(c=TestClient(app_main.app, base_url="https://testserver"), mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


def _call(client, method, path, **kwargs):
    return getattr(client.c, method)(path, **({"json": {}} if method == "post" else {}), **kwargs)


def test_las_rutas_exigen_sesion(client):
    for method, path in ROUTES:
        assert _call(client, method, path).status_code == 401, path
    registered = {r.path for r in app_main.app.routes if "/reference-lifecycle/" in getattr(r, "path", "")}
    assert len(registered) == len(ROUTES), "si se agrega una ruta, se agrega aqui con su prueba de sesion"


def test_usuario_de_otra_empresa_recibe_403(client):
    async def user_of_b(db, token):
        return SimpleNamespace(company_id=B, role="company_admin", full_name="Otra", status="active")

    client.mp.setattr(deps, "get_current_company_user", user_of_b)
    for method, path in ROUTES:
        assert _call(client, method, path, headers={"Authorization": "Bearer x"}).status_code == 403, path


def test_un_mesero_de_la_empresa_no_puede(client):
    async def waiter(db, token):
        return SimpleNamespace(company_id=A, role="waiter", full_name="Mesero", status="active")

    client.mp.setattr(deps, "get_current_company_user", waiter)
    for method, path in ROUTES:
        assert _call(client, method, path, headers={"Authorization": "Bearer x"}).status_code == 403, path


def test_con_el_interruptor_apagado_responde_404(client):
    client.mp.setattr(companies, "admin_v2_or_company_preview", AsyncMock(return_value=True))
    client.mp.setattr(svc, "is_on", AsyncMock(return_value=False))
    for method, path in ROUTES:
        assert _call(client, method, path).status_code == 404, path
