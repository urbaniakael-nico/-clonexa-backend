"""Consola v2+ (/admin-v2plus): misma sesion de Admin V2, validada en el
servidor; sin sesion redirige a /admin-v2/login. /admin-v2 no se toca."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.web import admin_v2plus_routes as plus

client = TestClient(app_main.app)


@pytest.fixture
def db_override():
    async def fake_db():
        yield None

    app_main.app.dependency_overrides[get_db] = fake_db
    yield
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path", ["/admin-v2plus", "/admin-v2plus/"])
def test_admin_v2plus_requires_the_admin_v2_session(db_override, monkeypatch, path):
    monkeypatch.setattr(plus, "_active_session", AsyncMock(return_value=False))
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin-v2/login"
    assert "Centro de mando" not in response.text


def test_admin_v2plus_opens_with_the_session(db_override, monkeypatch):
    monkeypatch.setattr(plus, "_active_session", AsyncMock(return_value=True))
    response = client.get("/admin-v2plus")
    assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
    assert "Centro de mando" in response.text and "/admin-v2plus.js" in response.text


def test_admin_v2plus_assets_are_served():
    assert "vp-shell" in client.get("/admin-v2plus.css").text
    assert "CxConsolePlus" in client.get("/admin-v2plus.js").text


def test_admin_v2_is_untouched_and_still_registered():
    paths = {getattr(r, "path", "") for r in app_main.app.routes}
    assert {"/admin-v2", "/admin-v2/login", "/admin-v2/api/overview", "/admin-v2plus"} <= paths


@pytest.mark.parametrize("name", ["consola-fondo.jpg", "consola-panel.jpg"])
def test_admin_v2plus_theme_images_ship_with_the_repo(name):
    response = client.get(f"/admin-v2-assets/{name}")
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert response.content[:3] == b"\xff\xd8\xff", "JPEG real"
