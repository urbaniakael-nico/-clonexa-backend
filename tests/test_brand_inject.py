"""Fase 4 · Parte 5: la marca publicada en el ingreso y los mini paneles.

- Sin marca publicada, el ingreso y los mini paneles sirven EXACTAMENTE el
  mismo HTML que antes (con y sin el interruptor brand_everywhere).
- Con marca publicada: colores por __CX_BRAND__, CSS del generador al final
  del body y modo liviano; nunca datos de otra empresa. Un borrador no cambia
  lo servido. /panel-theme prefiere la marca publicada.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.web import brand_inject
from tests.test_brand_publish import A, B, IMG_A, Db, tokens_with_image

WEB = Path("app/web")


@pytest.mark.asyncio
@pytest.mark.parametrize("page", ["hsp_waiter.html", "hsp_kitchen.html", "hsp_cashier.html", "mini_panel.html", "domicilio.html", "carta_qr.html", "hospitality_order.html"])
async def test_without_published_theme_html_is_identical(monkeypatch, page):
    html = (WEB / page).read_text(encoding="utf-8")
    monkeypatch.setattr(brand_inject, "published_theme", AsyncMock(return_value=None))
    # sin interruptor: el archivo tal cual
    monkeypatch.setattr(brand_inject, "company_brand", AsyncMock(return_value=None))
    assert await brand_inject.render(html, None, A, page) == html
    # con brand_everywhere: exactamente lo que servia antes
    old = {"primary_color": "#ff0000", "logo_url": "/x.png"}
    monkeypatch.setattr(brand_inject, "company_brand", AsyncMock(return_value=old))
    assert await brand_inject.render(html, None, A, page) == brand_inject.inject(html, old)


@pytest.mark.asyncio
async def test_published_theme_is_applied_only_to_its_company(monkeypatch):
    html = (WEB / "hsp_cashier.html").read_text(encoding="utf-8")
    published = {A: tokens_with_image(IMG_A)}
    monkeypatch.setattr(brand_inject, "published_theme", AsyncMock(side_effect=lambda db, cid: published.get(str(cid))))
    monkeypatch.setattr(brand_inject, "company_brand", AsyncMock(return_value=None))
    out = await brand_inject.render(html, None, A, "hsp_cashier.html")
    assert "window.__CX_BRAND__=" in out and '<style id="cxBrandTheme">' in out
    assert out.index('<style id="cxBrandTheme">') > out.index("</main>"), "al final del body, fuera del head"
    assert "brand_lite.js" in out
    assert f"/brand-media/{A}/{IMG_A}.webp" in out and B not in out
    other = await brand_inject.render(html, None, B, "hsp_cashier.html")
    assert other == html, "otra empresa sin marca: igual que siempre, nada de A"
    # fuera del alcance de esta fase (p. ej. domicilio) no se aplica
    dom = (WEB / "domicilio.html").read_text(encoding="utf-8")
    assert await brand_inject.render(dom, None, A, "domicilio.html") == dom


@pytest.mark.asyncio
async def test_tampered_published_theme_falls_back_to_the_usual_page():
    html = (WEB / "hsp_waiter.html").read_text(encoding="utf-8")
    bad = tokens_with_image(IMG_A)
    bad["theme"]["colors"]["primary"] = "#000;}</style><script>"
    assert brand_inject.inject_theme(html, bad, A) == html


@pytest.mark.asyncio
async def test_draft_does_not_change_what_is_served_publish_does(monkeypatch):
    db = Db()
    html = (WEB / "hsp_kitchen.html").read_text(encoding="utf-8")
    monkeypatch.setattr(brand_inject, "company_brand", AsyncMock(return_value=None))
    db.themes.append({"company_id": A, "status": "draft", "tokens": tokens_with_image(IMG_A)})
    assert await brand_inject.render(html, db, A, "hsp_kitchen.html") == html, "un borrador no cambia lo servido"
    db.themes[0]["status"] = "published"
    assert '<style id="cxBrandTheme">' in await brand_inject.render(html, db, A, "hsp_kitchen.html")


def test_panel_theme_prefers_published():
    from app.api.v1.endpoints import waiter_ordering as wo

    src = Path(wo.__file__).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "published = await brand_store.published_tokens(db, str(company_id))" in src
    assert src.index("published_tokens") < src.index('if settings.get(MINI_PANEL_BRAND_FLAG) is not True:\n        return {"ok": True, "enabled": False')
