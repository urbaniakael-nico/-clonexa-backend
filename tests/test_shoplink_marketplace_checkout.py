from pathlib import Path

from app.api.v1.endpoints import shoplink


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = (ROOT / "app" / "web" / "shoplink_public.js").read_text(encoding="utf-8")
PUBLIC_CSS = (ROOT / "app" / "web" / "shoplink_public.css").read_text(encoding="utf-8")
PUBLIC_HTML = (ROOT / "app" / "web" / "shoplink_public.html").read_text(encoding="utf-8")


def campaign(**overrides):
    value = {
        "slug": "lanzamiento",
        "coupon_code": "FUTURO20",
        "discount_type": "percent",
        "discount_value": 20,
        "min_order": 0,
        "max_uses": 0,
        "product_ids": [],
    }
    value.update(overrides)
    return value


def items(product_id="product-1", subtotal=100_000):
    return [{"product_id": product_id, "subtotal": subtotal}]


def test_coupon_quote_validates_code_and_calculates_server_discount():
    quote = shoplink._campaign_coupon_quote(campaign(), items(), 100_000, " futuro20 ")

    assert quote["valid"] is True
    assert quote["discount_amount"] == 20_000


def test_coupon_quote_enforces_minimum_products_and_usage_limit():
    below_minimum = shoplink._campaign_coupon_quote(
        campaign(min_order=150_000), items(), 100_000, "FUTURO20"
    )
    wrong_product = shoplink._campaign_coupon_quote(
        campaign(product_ids=["product-2"]), items(), 100_000, "FUTURO20"
    )
    exhausted = shoplink._campaign_coupon_quote(
        campaign(max_uses=2), items(), 100_000, "FUTURO20", uses=2
    )

    assert below_minimum["valid"] is False
    assert "desde una compra" in below_minimum["message"]
    assert wrong_product["valid"] is False
    assert "productos" in wrong_product["message"]
    assert exhausted["valid"] is False
    assert "limite" in exhausted["message"]


def test_public_campaign_hides_coupon_code_but_announces_requirement():
    output = shoplink._shoplink_campaign_out(
        campaign(id="campaign-1", title="Lanzamiento", company_id="company-1"),
        {},
        include_private=False,
    )

    assert output["coupon_code"] == ""
    assert output["coupon_required"] is True


def test_checkout_items_use_catalog_prices_instead_of_browser_prices():
    catalog = {
        "product-1": {
            "id": "product-1",
            "name": "Tenis",
            "price": 540_000,
            "stock": 5,
        }
    }

    checkout_items, total = shoplink._shoplink_checkout_items(
        catalog,
        [{"product_id": "product-1", "qty": 2, "price": 1}],
    )

    assert total == 1_080_000
    assert checkout_items[0]["unit_price"] == 540_000


def test_campaign_keeps_full_catalog_categories_and_only_scopes_featured_products():
    products = [
        {"id": "shoplink:shoe-1", "name": "Metcon", "category": "TENIS"},
        {"id": "shoplink:vitamin-1", "name": "Magnesio", "category": "VITAMINAS"},
    ]
    settings = {"categories": ["GORRAS", "TENIS", "RELOJES", "VITAMINAS"]}

    categories = shoplink._shoplink_public_categories(settings, products)
    featured = shoplink._shoplink_campaign_featured(
        campaign(product_ids=["shoplink:shoe-1"]),
        products,
    )

    assert categories == ["GORRAS", "TENIS", "RELOJES", "VITAMINAS"]
    assert [product["name"] for product in featured] == ["Metcon"]
    assert len(products) == 2


def test_public_checkout_has_explicit_coupon_payment_and_mobile_marketplace_ui():
    assert "data-shoplink-apply-coupon" in PUBLIC_JS
    assert "/coupons/validate" in PUBLIC_JS
    assert "coupon_code: state.coupon.status === \"valid\"" in PUBLIC_JS
    assert "campaign()?.coupon_code" not in PUBLIC_JS
    assert "data-shoplink-payment" in PUBLIC_JS
    assert "payment_method: state.paymentMethod" in PUBLIC_JS
    assert "data-shoplink-cart-open" in PUBLIC_JS
    assert "categoryCount(category)" in PUBLIC_JS
    assert ".sl-cart-dock" in PUBLIC_CSS
    assert 'body[data-theme="retail_neon"]::before' in PUBLIC_CSS
    assert "032D_FULL_CATALOG_NEON_MARKETPLACE" in PUBLIC_HTML

