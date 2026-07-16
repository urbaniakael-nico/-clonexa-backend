from datetime import date, timedelta

from app.api.v1.endpoints import production_v1


def test_reference_time_key_groups_variants_by_reference_name():
    assert production_v1._prod_reference_time_key("Dreamy Jacket") == "name:dreamy jacket"
    assert production_v1._prod_reference_time_key("DREAMY JACKET") == "name:dreamy jacket"


def test_production_period_uses_bogota_business_day_boundaries():
    start, end = production_v1._prod_period_bounds_023r(date(2026, 6, 22), date(2026, 6, 22))

    assert start.isoformat() == "2026-06-22T05:00:00+00:00"
    assert end - start == timedelta(days=1)
    assert end.isoformat() == "2026-06-23T05:00:00+00:00"


def test_reference_detail_is_grouped_and_limited_to_ten_visible_rows():
    source = (production_v1.__file__.replace("\\", "/"))
    assert source.endswith("app/api/v1/endpoints/production_v1.py")

    client_js = (
        __import__("pathlib").Path(production_v1.__file__).parents[3] / "web" / "client.js"
    ).read_text(encoding="utf-8")
    client_html = (
        __import__("pathlib").Path(production_v1.__file__).parents[3] / "web" / "client.html"
    ).read_text(encoding="utf-8")

    assert "const grouped = new Map();" in client_js
    assert "Tiempo general de la referencia" in client_js
    assert ".cx-prod-reference-table" in client_js
    assert "max-height: 704px;" in client_js
    assert "grid-auto-rows: 64px;" in client_js
    assert "033A_PRODUCTION_REFERENCE_RECONCILIATION" in client_html
