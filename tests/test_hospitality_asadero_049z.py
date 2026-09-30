"""049Z (solo ASADERO): transferencia en domicilios, ubicacion por WhatsApp
y el tema de la empresa en todo lo que abre un cliente o un empleado."""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import whatsapp_delivery as wd
from app.web import brand_inject
from tests.test_hospitality_domicilios_whatsapp import SETTINGS, _order_body, ordering  # noqa: F401 (fixture)

ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
client = TestClient(app_main.app)
ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------ domicilios: pago ---
@pytest.fixture
def v2(monkeypatch):
    monkeypatch.setattr(wd, "module_settings", AsyncMock(return_value={**SETTINGS, "checkout_v2": True}))


def test_hospitality_delivery_transfer_stays_por_verificar_and_bot_asks_location(ordering, v2):
    response = client.post(f"/api/v1/domicilios/public/{ASADERO}/orders",
                           json=_order_body(payment_method="transfer", pays_with=None))
    assert response.status_code == 201, response.text
    assert response.json()["payment_status"] == "por_verificar"
    delivery = ordering.order()["metadata"]["delivery"]
    assert delivery["payment_method"] == "qr", "misma ruta de verificacion que el QR"
    assert delivery["payment_kind"] == "transfer" and delivery["payment_status"] == "por_verificar"
    assert delivery["location_url"] == "", "la ubicacion ya no sale del formulario"
    message = ordering.sent.await_args.args[2]
    assert "comprobante" in message
    assert "compartenos tu ubicacion por este chat" in message
    assert wd.payment_line(delivery).startswith("Transferencia: POR VERIFICAR")


def test_hospitality_delivery_transfer_needs_the_switch(ordering):
    response = client.post(f"/api/v1/domicilios/public/{ASADERO}/orders",
                           json=_order_body(payment_method="transfer", pays_with=None))
    assert response.status_code == 422


def test_hospitality_delivery_without_switch_keeps_location_and_message(ordering):
    client.post(f"/api/v1/domicilios/public/{ASADERO}/orders", json=_order_body())
    delivery = ordering.order()["metadata"]["delivery"]
    assert delivery["location_url"].startswith("https://maps.google.com/")
    assert "ubicacion por este chat" not in ordering.sent.await_args.args[2]


def test_hospitality_delivery_settings_keep_the_switch():
    assert wd.normalize_settings({"checkout_v2": True})["checkout_v2"] is True
    assert wd.normalize_settings({})["checkout_v2"] is False


# ------------------------------------------------------------- branding ---
BRAND = {"primary_color": "#b91c1c", "background_color": "#fff7ed", "logo_url": "</script><script>alert(1)</script>"}


def test_hospitality_brand_is_embedded_safely():
    html = "<html><head><title>x</title></head><body></body></html>"
    out = brand_inject.inject(html, BRAND)
    assert "window.__CX_BRAND__=" in out and "hsp_brand.js" in out
    assert "</script><script>alert(1)" not in out, "el logo no puede cerrar el script"
    assert out.index("window.__CX_BRAND__") < out.index("</head>")
    assert brand_inject.inject(html, None) == html, "sin interruptor, la pagina de siempre"
    already = "<head><script src=\"/client-static/hsp_brand.js?v=1\"></script></head>"
    assert brand_inject.inject(already, BRAND).count("hsp_brand.js") == 1


class BrandDb:
    def __init__(self, on=True):
        self.on = on

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "waiter_ordering" in sql:
            rows = [{"settings": {"brand_everywhere": self.on}}]
        elif "qr_token" in sql:
            rows = [{"id": uuid.UUID(ASADERO), "name": "Asadero"}]
        else:
            rows = []
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: rows[0] if rows else None, all=lambda: rows),
                               first=lambda: rows[0] if rows else None)

    async def rollback(self):
        pass


@pytest.fixture
def brand_db(monkeypatch):
    holder = {"db": BrandDb()}

    async def fake_db():
        yield holder["db"]

    from app.api.v1.endpoints import companies

    monkeypatch.setattr(companies, "_get_company_or_404", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(companies, "_read_company_branding", lambda _c: {"primary_color": "#b91c1c", "background_color": "#fff7ed"})
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    app_main.app.dependency_overrides[get_db] = fake_db
    yield holder
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path", [
    f"/domicilio?c={ASADERO}&s=K7PM2QX9HD",
    "/carta-qr?t=abcdefghijklmnopqrstuvwxyz",
    f"/ordenar?company_id={ASADERO}&mesa=4",
    f"/mini-panel/caja?company_id={ASADERO}",
    f"/mini-panel/mesero/login?company_id={ASADERO}",
    f"/mini-panel/cocina?company_id={ASADERO}",
    f"/mini-panel/login?company_id={ASADERO}&type=store",
])
def test_hospitality_every_customer_and_employee_page_carries_the_brand(brand_db, path):
    page = client.get(path)
    assert page.status_code == 200
    assert "window.__CX_BRAND__=" in page.text and "#b91c1c" in page.text
    assert "hsp_brand.js" in page.text


def test_hospitality_pages_without_the_switch_are_unchanged(brand_db):
    brand_db["db"] = BrandDb(on=False)
    page = client.get(f"/domicilio?c={ASADERO}&s=K7PM2QX9HD")
    assert page.status_code == 200 and "__CX_BRAND__" not in page.text


def test_hospitality_049z_migration():
    path = ROOT / "migrations/versions/022n_asadero_sales_brand.py"
    spec = importlib.util.spec_from_file_location("mig_022n", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "022m_short_links"
    assert module.TARGET_COMPANY_ID == ASADERO
    assert json.loads(module.PATCHES["waiter_ordering"]) == {"sales_ledger": True, "brand_everywhere": True}
    assert json.loads(module.PATCHES["domicilios_whatsapp"]) == {"checkout_v2": True}
