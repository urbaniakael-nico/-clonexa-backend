"""/docs, /redoc y /openapi.json solo con sesion de Admin V2 (validada en el
servidor). Antes eran publicos: /openapi.json es el mapa completo de la API.
Nada propio consume /openapi.json; Admin V2 solo enlaza a /docs."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.web import admin_v2_routes


@pytest.fixture
def client(monkeypatch):
    async def fake_db():
        yield None

    app_main.app.dependency_overrides[get_db] = fake_db
    yield TestClient(app_main.app), monkeypatch
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_doc_pages_redirect_to_admin_login_without_session(client, path):
    c, mp = client
    mp.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    response = c.get(path, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin-v2/login"
    assert "swagger" not in response.text.lower() and "redoc" not in response.text.lower()


def test_schema_is_401_without_session(client):
    c, mp = client
    mp.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    response = c.get("/openapi.json")
    assert response.status_code == 401 and "paths" not in response.text


def test_a_broken_session_check_never_opens_the_docs(client):
    c, mp = client
    mp.setattr(admin_v2_routes, "_active_session", AsyncMock(side_effect=RuntimeError("sin base")))
    assert c.get("/openapi.json").status_code == 401
    assert c.get("/docs", follow_redirects=False).status_code == 303


def test_with_admin_v2_session_everything_works(client):
    c, mp = client
    mp.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=True))
    schema = c.get("/openapi.json")
    assert schema.status_code == 200 and "no-store" in schema.headers["cache-control"]
    paths = schema.json()["paths"]
    assert "/api/v1/companies" in paths and "/health" in paths
    assert not any(p in paths for p in ("/docs", "/redoc", "/openapi.json")), "las rutas de docs no se listan a si mismas"
    docs = c.get("/docs")
    assert docs.status_code == 200 and 'url: "/openapi.json"' in docs.text.replace("'", '"')
    redoc = c.get("/redoc")
    assert redoc.status_code == 200 and "/openapi.json" in redoc.text


def test_health_stays_public(client):
    c, mp = client
    mp.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    assert c.get("/health").json()["ok"] is True


def test_no_own_code_fetches_the_schema():
    hits = []
    for path in Path("app").rglob("*"):
        if path.suffix in {".js", ".html", ".py"} and "__pycache__" not in path.parts and path.name != "main.py":
            if "openapi.json" in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(path))
    assert hits == [], hits
