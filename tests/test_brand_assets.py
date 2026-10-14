"""Marca Clonexa (logo nuevo, 2026-10): inventario de reemplazos, estaticos con
cache y version, PDF de Clonexa y -sobre todo- que el logo de una EMPRESA
cliente (panel_logo, Estudio de marca) no cambio."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import brand_assets

WEB = Path("app/web")
V = brand_assets.VERSION
# Pantallas con la marca Clonexa (consola v2+ y su login, Admin V2,
# login del portal, portal, mini paneles y sus ingresos).
PAGES = ("admin_v2plus.html", "admin_v2plus_login.html", "admin_v2.html", "login.html", "client.html", "mini_panel.html",
         "hsp_cashier.html", "hsp_kitchen.html", "hsp_waiter.html")


def test_delivered_files_exist_and_svgs_are_clean():
    for name in brand_assets.FILES:
        assert brand_assets.path(name).is_file(), name
    for svg in [n for n in brand_assets.FILES if n.endswith(".svg")]:
        raw = brand_assets.path(svg).read_text(encoding="utf-8").lower()
        assert "<script" not in raw and "onload" not in raw and "href=\"http" not in raw, svg


def test_every_clonexa_page_uses_the_new_files_with_version_and_favicon():
    for page in PAGES:
        html = (WEB / page).read_text(encoding="utf-8")
        assert f"/assets/brand/favicon.ico?v={V}" in html and f"/assets/brand/clonexa-icono-180.png?v={V}" in html, f"favicon/apple-touch-icon: {page}"
        assert re.search(r'rel="apple-touch-icon"', html), page
        refs = re.findall(r"/assets/brand/[^\"' )]+", html)
        assert refs and all(r.endswith(f"?v={V}") for r in refs), (page, refs)


def test_old_logo_and_base64_watermark_are_gone():
    hits = []
    for f in list(WEB.glob("*.html")) + list(WEB.glob("*.js")) + list(Path("app").rglob("*.py")):
        if "clonexa-logo.png" in f.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(f))
    assert hits == [], f"queda el logo viejo en: {hits}"
    login = (WEB / "login.html").read_text(encoding="utf-8")
    assert "data:image/png;base64" not in login and len(login) < 20_000, "la marca de agua es el SVG nuevo"
    assert f'src="/assets/brand/clonexa-icono.svg?v={V}"' in login and "clonexa-logo-horizontal.svg" in login


def test_text_logos_replaced_in_consoles_mini_panels_and_old_menus():
    for page in ("admin_v2plus.html", "admin_v2plus_login.html", "admin_v2.html"):
        html = (WEB / page).read_text(encoding="utf-8")
        assert "clonexa-icono.svg" in html and "clonexa-nombre.svg" in html and '<div class="cx-brand-title">CLONEXA</div>' not in html, page
    client = (WEB / "client.js").read_text(encoding="utf-8")
    assert '<div class="client-logo"><strong>CLONEXA</strong></div>' not in client
    assert client.count("/assets/brand/clonexa-logo-horizontal.svg") >= 2
    for js, cls in (("hsp_cashier.js", "csh"), ("hsp_kitchen.js", "ktc"), ("hsp_waiter.js", "wtr")):
        src = (WEB / js).read_text(encoding="utf-8")
        assert f'<div class="{cls}-brand" data-brand="ingreso.marca"><img src="/assets/brand/clonexa-icono.svg' in src, js
    assert '<div class="mp-kicker">CLONEXA</div>' not in (WEB / "mini_panel.js").read_text(encoding="utf-8")


def test_brand_assets_are_cached_and_other_assets_unchanged(tmp_path):
    (tmp_path / "brand").mkdir()
    (tmp_path / "brand" / "x.svg").write_text("<svg/>")
    (tmp_path / "otro.jpg").write_bytes(b"jpg")
    app = FastAPI()
    app.mount("/assets", brand_assets.CachedAssets(directory=str(tmp_path)), name="assets")
    c = TestClient(app)
    r = c.get("/assets/brand/x.svg?v=cx26a")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "immutable" not in c.get("/assets/otro.jpg").headers.get("cache-control", "")
    real = TestClient(__import__("app.main", fromlist=["app"]).app)
    fav = real.get(f"/assets/brand/favicon.ico?v={V}")
    assert fav.status_code == 200 and "immutable" in fav.headers["cache-control"]
    assert real.get(f"/assets/brand/clonexa-icono.svg?v={V}").headers["content-type"].startswith("image/svg")


def test_clonexa_pdfs_use_the_new_logo():
    from app.api.v1.endpoints import reports
    from app.services import billing_pdf

    assert billing_pdf.LOGO.name == "clonexa-logo-horizontal-fondo-claro.png" and billing_pdf.LOGO.is_file(), "comprobante: fondo claro"
    assert reports.report_pdf_clonexa_icon() is not None


def test_company_logos_are_never_the_clonexa_brand(monkeypatch):
    """panel_logo (Reportes v2, Turnos, contrato del cliente) sigue devolviendo el logo
    de la EMPRESA: publicado del Estudio de marca o el de su experiencia."""
    from app.api.v1.endpoints import companies
    from app.services import brand_store, brand_theme, panel_logo

    cid = "11111111-2222-3333-4444-555555555555"

    async def tokens(db, company_id):
        return {"theme": {"logo": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}}

    monkeypatch.setattr(brand_store, "published_tokens", tokens)
    monkeypatch.setattr(brand_theme, "branding_for_portal", lambda t, c: {"logo_url": f"/brand-media/{c}/{t['theme']['logo']}.webp"})
    got = asyncio.run(panel_logo.panel_logo(None, cid))
    assert got == {"url": f"/brand-media/{cid}/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.webp", "source": "published"}

    async def none(db, company_id):
        return None

    async def company(db, company_id):
        return object()

    monkeypatch.setattr(brand_store, "published_tokens", none)
    monkeypatch.setattr(companies, "_get_company_or_404", company)
    monkeypatch.setattr(companies, "_read_company_branding", lambda c: {"logo_url": "https://empresa.test/logo.png"})
    assert asyncio.run(panel_logo.panel_logo(None, cid)) == {"url": "https://empresa.test/logo.png", "source": "experience"}
    for f in ("app/services/panel_logo.py", "app/services/brand_theme.py", "app/services/brand_store.py", "app/web/hsp_brand.js", "app/web/brand_lite.js"):
        assert "assets/brand" not in Path(f).read_text(encoding="utf-8"), f"{f} no usa la marca Clonexa"


@pytest.mark.parametrize("page", ["hospitality_order.html", "carta_qr.html", "shoplink_public.html", "domicilio.html", "marketplace_public.html"])
def test_customer_facing_pages_keep_the_business_brand(page):
    """Las paginas que ve el cliente final de un negocio (mesa QR, carta, tienda,
    domicilios) muestran la marca del negocio: no se les puso la de Clonexa."""
    assert "/assets/brand/" not in (WEB / page).read_text(encoding="utf-8")
