"""Seguridad de base (Fase 2 · commit 2, TODAS las empresas).

- Cabeceras de seguridad en todas las respuestas, sin bloquear nunca.
- X-Frame-Options excepto la WebApp de Telegram (/webapp/...).
- CSP solo en /admin-v2plus*, sin unsafe-inline en scripts.
- Validacion de marca al guardar (PUT .../experience/branding y PUT .../branding).
"""
from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.api.v1.endpoints import companies
from app.core import security_headers as sh
from app.web import admin_v2plus_routes as plus

client = TestClient(app_main.app)
WEB = Path("app/web")


# ------------------------------------------------------------- cabeceras
def test_every_response_carries_the_base_headers():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert "content-security-policy" not in response.headers


def test_errors_and_api_responses_also_get_headers_and_keep_their_status():
    response = client.get("/api/v1/companies")  # sin sesion: 401, igual que antes
    assert response.status_code == 401
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in response.headers


def test_telegram_webapp_can_still_be_framed_by_telegram_web():
    response = client.get("/webapp/materials")
    assert response.status_code == 200
    assert "x-frame-options" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("path", ["/client", "/mini-panel", "/ordenar", "/admin-v2/login"])
def test_rest_of_the_platform_gets_no_csp_yet(path):
    response = client.get(path, follow_redirects=False)
    assert "content-security-policy" not in response.headers


@pytest.fixture
def db_override():
    async def fake_db():
        yield None

    app_main.app.dependency_overrides[get_db] = fake_db
    yield
    app_main.app.dependency_overrides.pop(get_db, None)


def test_console_plus_gets_a_strict_csp(db_override, monkeypatch):
    monkeypatch.setattr(plus, "_active_session", AsyncMock(return_value=True))
    for path in ("/admin-v2plus", "/admin-v2plus.js", "/admin-v2plus.css", "/admin-v2plus-login.js"):
        csp = client.get(path).headers["content-security-policy"]
        directives = dict(d.strip().split(" ", 1) for d in csp.split(";"))
        assert directives["default-src"] == "'self'"
        assert directives["script-src"] == "'self'"
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
        assert directives["style-src"] == "'self' https://fonts.googleapis.com"
        assert directives["font-src"] == "'self' https://fonts.gstatic.com"
        assert directives["frame-ancestors"] == "'self'"


def test_console_plus_redirect_to_login_also_has_csp(db_override, monkeypatch):
    monkeypatch.setattr(plus, "_active_session", AsyncMock(return_value=False))
    response = client.get("/admin-v2plus", follow_redirects=False)
    assert response.status_code == 303 and "content-security-policy" in response.headers


@pytest.mark.parametrize("name", ["admin_v2plus.html", "admin_v2plus_login.html"])
def test_console_plus_pages_have_no_inline_script_or_handlers(name):
    import re

    page = (WEB / name).read_text(encoding="utf-8")
    assert not re.search(r"\son[a-z]+\s*=", page), "manejador en linea: la CSP lo bloquea"
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page), "script en linea"
    assert "style=" not in page
    for src in re.findall(r'<script[^>]*src="([^"]+)"', page):
        assert src.startswith("/"), src


def test_logo_fallback_moved_to_the_console_scripts():
    for name in ("admin_v2plus.js", "admin_v2plus_login.js"):
        assert "function logoFallback()" in (WEB / name).read_text(encoding="utf-8")


def _mini_app(handler):
    mini = FastAPI()
    mini.add_api_route("/x", handler)
    mini.add_middleware(sh.SecurityHeadersMiddleware)
    return TestClient(mini)


def test_a_route_own_header_is_respected():
    def handler():
        return PlainTextResponse("ok", headers={"X-Frame-Options": "DENY"})

    response = _mini_app(handler).get("/x")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_a_failure_building_headers_never_blocks_the_response(monkeypatch):
    def boom(_path):
        raise RuntimeError("fallo")

    monkeypatch.setattr(sh, "headers_for", boom)
    response = _mini_app(lambda: PlainTextResponse("ok")).get("/x")
    assert response.status_code == 200 and response.text == "ok"


# ------------------------------------------------------------- marca
@pytest.mark.parametrize("logo", [
    "javascript:alert(1)", "JAVASCRIPT:alert(1)", " javascript:alert(1)", "data:image/png;base64,AAAA",
    "data:text/html,<script>alert(1)</script>", "http://example.com/logo.png", "//evil.com/logo.png",
    "/\\evil.com/logo.png", "https://", 'https://x.com/a.png" onerror="alert(1)', "vbscript:x", "logo.png",
])
def test_logo_url_rejects_anything_but_https_or_own_path(logo):
    assert companies.branding_logo_url_ok(logo) is False
    with pytest.raises(HTTPException) as error:
        companies.validate_branding_payload({"logo_url": logo})
    assert error.value.status_code == 400 and "logo_url" in error.value.detail


@pytest.mark.parametrize("logo", ["", "https://cdn.clonexa.app/logos/asadero.png", "/admin-v2-assets/clonexa-logo.png", "/assets/x.webp?v=2"])
def test_logo_url_accepts_https_and_own_paths(logo):
    companies.validate_branding_payload({"logo_url": logo})


@pytest.mark.parametrize("payload, field", [
    ({"primary_color": "red"}, "primary_color"),
    ({"gradient_to": "#12345"}, "gradient_to"),
    ({"card_color": "rgb(0,0,0)"}, "card_color"),
    ({"color_principal": "#ff00zz"}, "color_principal"),
    ({"custom_css_json": {"background_color": "url(javascript:x)"}}, "background_color"),
    ({"font_family": "Comic Sans MS"}, "font_family"),
    ({"custom_css_json": {"fontFamily": "x</style><script>"}}, "fontFamily"),
    ({"custom_css_json": {"gradient_angle": "90deg;}"}}, "gradient_angle"),
    ({"custom_css_json": {"gradientAngle": True}}, "gradientAngle"),
    ({"gradient_angle": float("nan")}, "gradient_angle"),
])
def test_colors_fonts_and_angle_are_validated(payload, field):
    with pytest.raises(HTTPException) as error:
        companies.validate_branding_payload(payload)
    assert error.value.status_code == 400 and field in error.value.detail


def test_a_full_admin_v2_style_payload_still_passes():
    companies.validate_branding_payload({
        "logo_url": "https://cdn.example.com/l.png", "primary_color": "#ff2bd6", "secondary_color": "#00FF88",
        "background_color": "#050509", "text_color": "#fff", "visual_preset": "clonexa_dark",
        "background_style": "aurora_boreal", "font_family": "Space Grotesk", "card_style": "glass_premium",
        "mode": "dark", "theme_mode": "dark", "background_mode": "iridescent", "surface_style": "glass",
        "gradient_from": "#ff2bd6", "gradient_to": "#00ff88", "gradient_extra": "#2563eb", "gradient_angle": 135,
    })


def _company(settings=None):
    return SimpleNamespace(id=uuid.uuid4(), slug="demo", name="Demo", settings_json=settings or {}, updated_at=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["update_company_experience_branding", "update_company_branding"])
async def test_both_put_endpoints_reject_before_writing(monkeypatch, endpoint):
    company = _company()
    monkeypatch.setattr(companies, "_get_company_or_404", AsyncMock(return_value=company))
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    payload = companies.CompanyBrandingRequest(logo_url="javascript:alert(document.cookie)")
    with pytest.raises(HTTPException) as error:
        await getattr(companies, endpoint)(company.id, payload, db=db, _admin=None)
    assert error.value.status_code == 400
    db.commit.assert_not_awaited()
    assert company.settings_json == {}


@pytest.mark.asyncio
async def test_a_valid_save_still_works(monkeypatch):
    company = _company()
    monkeypatch.setattr(companies, "_get_company_or_404", AsyncMock(return_value=company))
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    payload = companies.CompanyBrandingRequest(logo_url="/admin-v2-assets/clonexa-logo.png", primary_color="#112233", font_family="Sora")
    result = await companies.update_company_experience_branding(company.id, payload, db=db, _admin=None)
    assert result["branding"]["logo_url"] == "/admin-v2-assets/clonexa-logo.png"
    assert result["branding"]["font_family"] == "Sora"
    db.commit.assert_awaited_once()


def test_stored_values_that_no_longer_pass_are_still_read_as_before():
    stored = {"branding": {"logo_url": "data:image/png;base64,AAAA", "primary_color": "#123456", "font_family": "Comic Sans MS"}}
    branding = companies._read_company_branding(_company(stored))
    assert branding["logo_url"] == "data:image/png;base64,AAAA"  # se lee igual
    assert branding["font_family"] == "Inter"  # igual que antes: la lectura ya lo llevaba a Inter
    assert branding["primary_color"] == "#123456"
