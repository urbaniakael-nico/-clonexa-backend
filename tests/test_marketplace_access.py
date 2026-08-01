from pathlib import Path
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.marketplace import (
    normalize_phone,
    normalize_username,
    validate_password,
    verification_hash,
)
from app.api.v1.endpoints.module_catalog_v1 import MODULE_CATALOG_ES
from app.api.v1.router import api_router


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_HTML = (ROOT / "app" / "web" / "marketplace_public.html").read_text(encoding="utf-8")
PUBLIC_JS = (ROOT / "app" / "web" / "marketplace_public.js").read_text(encoding="utf-8")
CLIENT_JS = (ROOT / "app" / "web" / "client.js").read_text(encoding="utf-8")
CLIENT_ROUTES = (ROOT / "app" / "web" / "client_routes.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("300 123 4567", "+573001234567"),
        ("+57 315-987-6543", "+573159876543"),
        ("1 202 555 0198", "+12025550198"),
    ],
)
def test_marketplace_phone_normalization(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["123", "abcdef", ""])
def test_marketplace_rejects_invalid_phone(raw):
    with pytest.raises(HTTPException):
        normalize_phone(raw)


def test_marketplace_username_has_display_and_unique_key():
    assert normalize_username("  Nicolás  87 ") == ("Nicolás 87", "nicolas_87")


def test_marketplace_verification_hash_is_tenant_and_purpose_scoped(monkeypatch):
    monkeypatch.setenv("CLONEXA_JWT_SECRET", "test-secret")
    company_id = uuid.uuid4()
    first = verification_hash(company_id, "+573001234567", "register", "123456")
    assert first == verification_hash(company_id, "+573001234567", "register", "123456")
    assert first != verification_hash(company_id, "+573001234567", "reset", "123456")


def test_marketplace_password_minimum_is_enforced():
    with pytest.raises(HTTPException):
        validate_password("corta")
    assert validate_password("segura-123") == "segura-123"


def test_marketplace_api_and_catalog_are_registered():
    paths = {getattr(route, "path", "") for route in api_router.routes}
    assert "/marketplace/companies/{company_id}/public" in paths
    assert "/marketplace/companies/{company_id}/auth/register" in paths
    assert MODULE_CATALOG_ES["marketplace_access"]["badge"] == "MKT"


def test_public_marketplace_browses_without_login_but_gates_participation():
    assert "Explorar artículos" in PUBLIC_HTML
    assert 'data-auth-action="publish"' in PUBLIC_HTML
    assert "registration_requires_login" not in PUBLIC_JS
    assert "clonexa_marketplace_token:" in PUBLIC_JS
    assert 'openAuth(action)' in PUBLIC_JS


def test_marketplace_registration_contains_required_fast_fields():
    for field in ('name="username"', 'name="phone"', 'name="verification_code"', 'name="password"'):
        assert field in PUBLIC_HTML
    assert 'data-send-code="register"' in PUBLIC_HTML


def test_marketplace_public_route_and_company_panel_exist():
    assert '@app.get("/mercado"' in CLIENT_ROUTES
    assert "renderMarketplaceAccessModule030H" in CLIENT_JS
    assert "/mercado?company_id=" in CLIENT_JS
    assert 'marketplace_access: ["Acceso Marketplace"' in CLIENT_JS
