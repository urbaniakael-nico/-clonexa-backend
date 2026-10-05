"""Consola v2+ · la pestaña Marca de la Ficha muestra la marca REAL.

- /admin-v2/api/brand/{id}/summary y la miniatura ?marca=actual exigen sesion.
- Sin marca publicada, la miniatura del panel principal lleva exactamente la
  hoja de hoy (no el borrador); con marca publicada, la publicada.
- Se avisa cuando hay un borrador sin publicar.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import brand_screens, brand_store
from app.services import brand_theme as bt
from app.services import portal_base_css as portal_css
from app.web import admin_v2plus_companies as ep
from app.web import brand_routes

A = str(uuid.uuid4())
BRANDING = {"primary_color": "#a600ff", "secondary_color": "#8cff00", "background_color": "#00ffe1", "text_color": "#000000",
            "background_style": "holografico", "font_family": "Sora", "card_style": "glass_premium", "theme_mode": "dark",
            "logo_url": "data:image/png;base64,iVBORw0KGgo="}


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return SimpleNamespace(first=lambda: self.rows[0] if self.rows else None, all=lambda: self.rows)


class Db:
    def __init__(self, published=None):
        self.published = published

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if sql.startswith("SELECT version, published_at FROM company_brand_themes"):
            from datetime import datetime, timezone

            return Rows([{"version": 4, "published_at": datetime(2026, 10, 5, tzinfo=timezone.utc)}] if self.published else [])
        if "FROM companies WHERE id" in sql:
            return Rows([{"id": params["id"], "name": "Velvet", "slug": "velvet", "status": "active", "settings_json": {}}])
        raise AssertionError(sql)


@pytest.fixture
def client(monkeypatch):
    holder = SimpleNamespace(db=Db())

    async def fake_db():
        yield holder.db

    app_main.app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(brand_routes, "_branding", AsyncMock(return_value=BRANDING))
    monkeypatch.setattr(brand_screens, "for_company", AsyncMock(return_value=brand_screens.compute({})))
    monkeypatch.setattr(brand_screens, "enabled_modules", AsyncMock(return_value=[{"code": "crm", "name": "CRM", "category": ""}]))
    yield SimpleNamespace(c=TestClient(app_main.app), mp=monkeypatch, holder=holder)
    app_main.app.dependency_overrides.pop(get_db, None)


def test_summary_and_ficha_preview_require_session(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    client.mp.setattr(brand_routes.v2, "_active_session", AsyncMock(return_value=False))
    assert client.c.get(f"/admin-v2/api/brand/{A}/summary").status_code == 401
    assert client.c.get(f"/admin-v2/brand-preview/{A}?marca=actual").status_code == 401


def test_without_published_brand_the_ficha_shows_todays_look(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    client.mp.setattr(brand_routes.v2, "_active_session", AsyncMock(return_value=True))
    edited = bt.from_branding(BRANDING)
    edited["theme"]["colors"]["primary"] = "#000001"
    client.mp.setattr(brand_store, "draft_tokens", AsyncMock(return_value=edited))
    client.mp.setattr(brand_store, "published_tokens", AsyncMock(return_value=None))
    s = client.c.get(f"/admin-v2/api/brand/{A}/summary").json()
    assert s["source"] == "siempre" and s["published"] is None and s["draft_pending"] is True
    assert s["colors"]["primary"] == "#a600ff", "la de siempre, no el borrador"
    assert s["logo_url"].startswith("data:image/png;base64,") and s["font"] == "Sora"
    html = client.c.get(f"/admin-v2/brand-preview/{A}?marca=actual&screen=portal_dashboard").text
    today = portal_css.render(bt.normalize_branding(BRANDING))
    assert today.replace("</", "<\\/") in html, "la miniatura lleva exactamente la hoja de hoy"
    assert "#000001" not in html and 'data-cx-preview="ficha"' in html


def test_published_brand_is_shown_with_its_version(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    client.mp.setattr(brand_routes.v2, "_active_session", AsyncMock(return_value=True))
    published = bt.from_branding(BRANDING)
    published["theme"]["colors"]["primary"] = "#123456"
    client.holder.db = Db(published=True)
    client.mp.setattr(brand_store, "published_tokens", AsyncMock(return_value=published))
    client.mp.setattr(brand_store, "draft_tokens", AsyncMock(return_value=published))
    s = client.c.get(f"/admin-v2/api/brand/{A}/summary").json()
    assert s["source"] == "published" and s["published"]["version"] == 4 and s["draft_pending"] is False
    assert s["colors"]["primary"] == "#123456"
    html = client.c.get(f"/admin-v2/brand-preview/{A}?marca=actual").text
    assert "--cxb-primary:#123456" in html


def test_today_logo_only_accepts_safe_values():
    assert brand_routes._today_logo({"logo_url": "javascript:alert(1)"}) == ""
    assert brand_routes._today_logo({"logo_url": "data:image/svg+xml;base64,PHN2Zz4="}) == ""
    assert brand_routes._today_logo({"logo_url": "//evil.example/x.png"}) == ""
    assert brand_routes._today_logo({"logo_url": "/client-static/x.png"}) == "/client-static/x.png"
    assert brand_routes._today_logo({"logo_url": "data:image/webp;base64,AAAA"}) == "data:image/webp;base64,AAAA"
