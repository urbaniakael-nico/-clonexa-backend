from pathlib import Path
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.marketplace import (
    MARKETPLACE_CATEGORIES,
    MAX_OFFER_IMAGES,
    MAX_PUBLICATION_IMAGES,
    MAX_VIDEO_SECONDS,
    _mp4_duration_seconds,
    _request_origin,
    infer_marketplace_category,
    normalize_marketplace_category,
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
    assert MODULE_CATALOG_ES["marketplace_access"]["badge"] == "PUB"
    assert MODULE_CATALOG_ES["marketplace_access"]["name"] == "Publicaciones"


def test_public_marketplace_browses_without_login_but_gates_participation():
    assert "Explorar artículos" in PUBLIC_HTML
    assert 'data-auth-action="publish"' in PUBLIC_HTML
    assert "registration_requires_login" not in PUBLIC_JS
    assert "clonexa_marketplace_token:" in PUBLIC_JS
    assert 'openAuth(action)' in PUBLIC_JS


def test_marketplace_registration_contains_required_fast_fields():
    for field in ('name="username"', 'name="phone"', 'name="password"'):
        assert field in PUBLIC_HTML
    assert 'name="verification_code"' not in PUBLIC_HTML
    assert 'data-send-code="register"' not in PUBLIC_HTML


def test_marketplace_public_route_and_company_panel_exist():
    assert '@app.get("/mercado"' in CLIENT_ROUTES
    assert "renderMarketplaceAccessModule030H" in CLIENT_JS
    assert "/mercado?company_id=" in CLIENT_JS
    assert 'marketplace_access: ["Publicaciones"' in CLIENT_JS


def test_publication_creation_and_chat_routes_are_registered():
    paths = {getattr(route, "path", "") for route in api_router.routes}
    assert "/marketplace/companies/{company_id}/publications" in paths
    assert "/marketplace/companies/{company_id}/manage/publications" in paths
    assert "/marketplace/companies/{company_id}/publications/{publication_id}/chat" in paths
    assert "/marketplace/companies/{company_id}/publications/{publication_id}/offers" in paths
    assert "/marketplace/companies/{company_id}/auth/offers/{offer_id}/media/{media_id}" in paths
    assert "/marketplace/companies/{company_id}/auth/chats/{conversation_id}/messages" in paths
    assert "/marketplace/companies/{company_id}/profiles/{profile_user_id}" in paths
    assert "/marketplace/companies/{company_id}/profiles/{profile_user_id}/reviews" in paths
    assert "/marketplace/companies/{company_id}/auth/publications" in paths
    assert "/marketplace/companies/{company_id}/publications/{publication_id}" in paths


def test_publication_app_exposes_media_price_specs_and_chat():
    assert MAX_PUBLICATION_IMAGES == 5
    assert MAX_VIDEO_SECONDS == 30
    for field in ('name="price"', 'name="category"', 'name="specifications"', 'name="images"', 'name="video"'):
        assert field in PUBLIC_HTML
    assert 'data-open-publication' in PUBLIC_JS
    assert 'request("/publications"' in PUBLIC_JS
    assert "marketplace_public_app.css" in PUBLIC_HTML


def test_marketplace_article_detail_supports_money_and_change_offers():
    assert MAX_OFFER_IMAGES == 3
    for element_id in ('id="publicationModal"', 'id="offerForm"', 'id="moneyOfferFields"', 'id="changeOfferFields"'):
        assert element_id in PUBLIC_HTML
    assert 'data-offer-type="money"' in PUBLIC_HTML
    assert 'data-offer-type="change"' in PUBLIC_HTML
    assert 'id="offerImages"' in PUBLIC_HTML
    assert 'id="offerVideo"' in PUBLIC_HTML
    assert "openPublicationDetail(publicationId)" in PUBLIC_JS
    assert 'request(`/publications/${encodeURIComponent(currentPublication.id)}/offers`' in PUBLIC_JS
    assert "data-copy-publication" not in PUBLIC_JS
    assert ">Compartir</button>" not in PUBLIC_JS


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("Gorra New Era original", "gorras"),
        ("Taladro inalámbrico con batería", "herramientas"),
        ("Juego PS5 FIFA 26", "juegos_consola"),
        ("Xbox Series S consola", "tecnologia"),
        ("Play 4 con dos controles", "tecnologia"),
        ("Reloj cronógrafo para hombre", "relojes"),
        ("Objeto especial sin descripción", "otros"),
    ],
)
def test_marketplace_category_inference(content, expected):
    assert infer_marketplace_category(content) == expected


def test_marketplace_category_can_be_selected_or_inferred():
    assert "juegos_consola" in MARKETPLACE_CATEGORIES
    assert normalize_marketplace_category("ropa", "Taladro") == "ropa"
    assert normalize_marketplace_category("auto", "Camiseta deportiva") == "ropa"
    with pytest.raises(HTTPException):
        normalize_marketplace_category("categoria_inventada", "Articulo")


def test_marketplace_catalog_renders_category_sections_and_filters():
    assert 'id="marketCategoryChips"' in PUBLIC_HTML
    assert 'value="juegos_consola"' in PUBLIC_HTML
    assert "renderCategoryChips" in PUBLIC_JS
    assert "market-category-section" in PUBLIC_JS
    assert "suggestCategory" in PUBLIC_JS


def test_marketplace_profiles_are_public_shareable_and_reviewable():
    for element_id in ('id="profileView"', 'id="publicProfilePublications"', 'id="reviewForm"', 'id="shareProfileButton"'):
        assert element_id in PUBLIC_HTML
    assert "openProfile(profileUserId)" in PUBLIC_JS
    assert "data-profile-user" in PUBLIC_JS
    assert 'request(`/profiles/${encodeURIComponent(currentProfileId)}/reviews`' in PUBLIC_JS


def test_marketplace_owner_can_edit_own_publications():
    assert 'id="myPublicationsList"' in PUBLIC_HTML
    assert "data-edit-publication" in PUBLIC_JS
    assert 'method:"PATCH"' in PUBLIC_JS


def test_marketplace_async_forms_keep_stable_form_reference_and_backend_deduplicates_retries():
    assert "const formElement = event.currentTarget" in PUBLIC_JS
    assert "event.currentTarget.reset()" not in PUBLIC_JS
    source = (ROOT / "app" / "api" / "v1" / "endpoints" / "marketplace.py").read_text(encoding="utf-8")
    assert "interval '90 seconds'" in source
    assert '"deduplicated": True' in source


def test_marketplace_shared_links_respect_railway_forwarded_https():
    class RequestStub:
        headers = {"x-forwarded-proto": "https", "x-forwarded-host": "clonexa.example.com"}
        url = type("URL", (), {"scheme": "http", "netloc": "internal:8080"})()

    assert _request_origin(RequestStub()) == "https://clonexa.example.com"


def test_marketplace_short_link_resolves_tenant_and_preserves_company_on_native_submit():
    assert "RedirectResponse" in CLIENT_ROUTES
    assert "m.code = 'marketplace_access'" in CLIENT_ROUTES
    assert 'status_code=307' in CLIENT_ROUTES
    assert 'id="publishCompanyId"' in PUBLIC_HTML
    assert 'name="company_id"' in PUBLIC_HTML
    assert "030L_ARTICLE_OFFERS" in PUBLIC_HTML


def test_mp4_duration_reader_rejects_over_thirty_second_metadata():
    payload = bytearray(40)
    payload[4:8] = b"mvhd"
    payload[8] = 0
    payload[20:24] = (1000).to_bytes(4, "big")
    payload[24:28] = (31_000).to_bytes(4, "big")
    assert _mp4_duration_seconds(bytes(payload)) == 31.0
