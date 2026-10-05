"""Estudio de marca · etapa 2: lo que se sirve.

- Sin marca publicada, /client, /login, /mini-panel y los paneles de
  restaurante sirven EXACTAMENTE lo mismo que antes (con y sin el interruptor
  brand_everywhere).
- Con marca publicada, el portal recibe window.__CX_PORTAL_BRAND__ y la hoja
  del servidor; client.js no inyecta su hoja vieja (prueba en node).
- Los paneles solo cambian si la marca se aplica a los paneles.
- Que pantallas tiene cada empresa (restaurante y mini paneles solo si los usa).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import brand_screens
from app.services import brand_theme as bt
from app.web import brand_inject

WEB = Path("app/web")
A = str(uuid.uuid4())
NODE = shutil.which("node")


class NoDb:
    async def execute(self, *a, **k):
        raise AssertionError("no deberia consultar la base")

    async def rollback(self):
        pass


@pytest.fixture
def client(monkeypatch):
    async def fake_db():
        yield NoDb()

    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(c=TestClient(app_main.app), mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("url,file", [
    ("/client", "client.html"), (f"/client?company_id={A}", "client.html"),
    ("/login", "login.html"), (f"/login?company_id={A}", "login.html"),
    (f"/mini-panel/login?company_id={A}&type=sales", "mini_panel.html"), (f"/mini-panel?company_id={A}", "mini_panel.html"),
    (f"/mini-panel/caja?company_id={A}", "hsp_cashier.html"), (f"/mini-panel/mesero/login?company_id={A}", "hsp_waiter.html"),
    (f"/mini-panel/cocina?company_id={A}", "hsp_kitchen.html"),
])
def test_without_published_brand_everything_is_served_as_before(client, url, file):
    client.mp.setattr(brand_inject, "published_theme", AsyncMock(return_value=None))
    client.mp.setattr(brand_inject, "company_brand", AsyncMock(return_value=None))
    client.mp.setattr("app.web.client_routes.active_admin_v2_session", AsyncMock(return_value=False))
    res = client.c.get(url)
    assert res.status_code == 200
    assert res.text == (WEB / file).read_text(encoding="utf-8")
    assert res.headers["cache-control"] == "no-store, max-age=0"


@pytest.mark.asyncio
@pytest.mark.parametrize("file", ["client.html", "login.html", "mini_panel.html", "hsp_cashier.html", "domicilio.html", "carta_qr.html"])
async def test_without_published_brand_render_matches_old_inject(monkeypatch, file):
    html = (WEB / file).read_text(encoding="utf-8")
    monkeypatch.setattr(brand_inject, "published_theme", AsyncMock(return_value=None))
    old = {"primary_color": "#ff0000"}
    monkeypatch.setattr(brand_inject, "company_brand", AsyncMock(return_value=old))
    expected = html if file in ("client.html", "login.html") else brand_inject.inject(html, old)
    assert await brand_inject.render(html, None, A, file) == expected


@pytest.mark.asyncio
async def test_published_brand_on_portal_login_and_panels_scope(monkeypatch):
    tokens = bt.from_branding({"primary_color": "#123456", "font_family": "Sora"}, panels=False)
    monkeypatch.setattr(brand_inject, "published_theme", AsyncMock(return_value=tokens))
    monkeypatch.setattr(brand_inject, "company_brand", AsyncMock(return_value=None))
    client_html = (WEB / "client.html").read_text(encoding="utf-8")
    out = await brand_inject.render(client_html, None, A, "client.html")
    assert "window.__CX_PORTAL_BRAND__=" in out and '<style id="cxBrandTheme">' in out and "brand_lite.js" in out
    data = json.loads(out.split("window.__CX_PORTAL_BRAND__=", 1)[1].split(";</script>", 1)[0])
    assert data["branding"]["primary_color"] == "#123456" and "portal.barra_lateral" in data["pieces"]
    assert "client-sidebar" in out.split('<style id="cxBrandTheme">', 1)[1], "la hoja del servidor trae la estructura del portal"
    login = await brand_inject.render((WEB / "login.html").read_text(encoding="utf-8"), None, A, "login.html")
    assert '<style id="cxBrandTheme">' in login and "__CX_PORTAL_BRAND__" not in login
    # La marca no se aplica a los paneles: salen igual que antes.
    for file in ("hsp_cashier.html", "mini_panel.html"):
        html = (WEB / file).read_text(encoding="utf-8")
        assert await brand_inject.render(html, None, A, file) == html
    tokens["theme"]["panels"] = True
    html = (WEB / "mini_panel.html").read_text(encoding="utf-8")
    assert '<style id="cxBrandTheme">' in await brand_inject.render(html, None, A, "mini_panel.html")


@pytest.mark.asyncio
async def test_public_pages_only_take_brand_colors_when_they_use_the_brand_today(monkeypatch):
    tokens = bt.from_branding({"primary_color": "#123456"}, panels=True)
    monkeypatch.setattr(brand_inject, "published_theme", AsyncMock(return_value=tokens))
    html = (WEB / "domicilio.html").read_text(encoding="utf-8")
    monkeypatch.setattr(brand_inject, "company_brand", AsyncMock(return_value=None))
    assert await brand_inject.render(html, None, A, "domicilio.html") == html, "sin brand_everywhere: como hoy"
    monkeypatch.setattr(brand_inject, "company_brand", AsyncMock(return_value={"primary_color": "#ff0000"}))
    out = await brand_inject.render(html, None, A, "domicilio.html")
    assert '"primary_color": "#123456"' in out and "cxBrandTheme" not in out, "solo los colores de la marca publicada"


@pytest.mark.asyncio
async def test_broken_published_brand_serves_the_usual_portal(monkeypatch):
    tokens = bt.from_branding({})
    tokens["theme"]["colors"]["primary"] = "#000;}</style><script>"
    monkeypatch.setattr(brand_inject, "published_theme", AsyncMock(return_value=tokens))
    html = (WEB / "client.html").read_text(encoding="utf-8")
    assert await brand_inject.render(html, None, A, "client.html") == html


# ------------------------------------------------------------ client.js
CLIENT_NODE = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[process.argv.length - 1], 'utf8');
function grab(name) {
  const start = src.indexOf(`  function ${name}(`);
  let depth = 0, i = src.indexOf(') {', start) + 2;
  for (; i < src.length; i++) { if (src[i] === '{') depth++; else if (src[i] === '}') { depth--; if (depth === 0) break; } }
  return src.slice(start, i + 1);
}
const code = 'let cxBrandObserver050A = null;\n' + ['validHex', 'normalizeBranding', 'brandingBackground', 'fontProfile', 'cardProfile',
  'cxPortalBrand050A', 'cxPortalBrandMerge050A', 'cxBrandTagPieces050A', 'cxBrandWatch050A', 'cxPortalBrandApply050A', 'applyBranding'].map(grab).join('\n');
function run(windowObj) {
  const els = {};
  const tagged = [];
  const nodes = { '.client-sidebar': [{ attrs: {}, hasAttribute(k) { return k in this.attrs; }, setAttribute(k, v) { this.attrs[k] = v; tagged.push(v); } }] };
  const app = { querySelectorAll: (sel) => nodes[sel] || [] };
  const old = { removed: false, remove() { this.removed = true; } };
  const document = { head: { appendChild: (el) => { els[el.id] = el; } }, createElement: () => ({}), getElementById: (id) => (id === 'app' ? app : id === 'clientBrandingDynamicStyle' ? old : null) };
  const $ = (id) => els[id] || null;
  const state = { branding: { primary_color: '#ff0000', logo_url: 'viejo.png' } };
  const MutationObserver = function () { this.observe = () => {}; };
  new Function('document', '$', 'state', 'window', 'MutationObserver', code + '\napplyBranding();')(document, $, state, windowObj, MutationObserver);
  return { injected: Boolean(els.clientBrandingDynamicStyle), oldRemoved: old.removed, branding: state.branding, tagged };
}
const withBrand = run({ __CX_PORTAL_BRAND__: { branding: { primary_color: '#123456', logo_url: '/brand-media/x.webp' }, pieces: { 'portal.barra_lateral': '.client-sidebar' } }, requestAnimationFrame: (f) => f() });
const without = run({});
process.stdout.write(JSON.stringify({ withBrand, without }));
"""


@pytest.mark.skipif(NODE is None, reason="node no disponible")
def test_client_js_with_published_brand_does_not_inject_old_sheet():
    run = subprocess.run([NODE, "-e", CLIENT_NODE, str(WEB / "client.js")], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    w, wo = out["withBrand"], out["without"]
    assert w["injected"] is False and w["oldRemoved"] is True, "con marca publicada no hay hoja vieja"
    assert w["branding"]["primary_color"] == "#123456" and w["branding"]["logo_url"] == "/brand-media/x.webp"
    assert w["tagged"] == ["portal.barra_lateral"], "marca las piezas con data-brand"
    assert wo["injected"] is True and wo["oldRemoved"] is False and wo["branding"]["primary_color"] == "#ff0000", "sin marca: como siempre"
    assert wo["tagged"] == []


# ------------------------------------------------------------ pantallas
def test_screens_per_company():
    portal = ["portal_dashboard", "portal_modulo", "portal_ingreso"]
    velvet = brand_screens.compute({})
    assert velvet["screens"] == portal and velvet["panels_branded_today"] is False
    wo_off = brand_screens.compute({"waiter_ordering": {"enabled": False, "settings": {"segments": {"caja": {"enabled": True}}}}})
    assert wo_off["screens"] == portal, "waiter_ordering apagado: nada de restaurante"
    asadero = brand_screens.compute({"waiter_ordering": {"enabled": True, "settings": json.dumps({
        "segments": {"mesero": {"enabled": True}, "cocina": {"enabled": False}, "caja": {"enabled": True}}, "mini_panel_brand": True})}})
    assert asadero["screens"] == portal + ["ingreso", "mesero", "caja"], "cada panel solo si su segmento esta encendido"
    assert asadero["panels_branded_today"] is True
    mini = brand_screens.compute({"mini_panel": {"enabled": True, "settings": {"mini_panel_modules": {"panels": {"sales": {"enabled": True}, "store": {"enabled": False}}}}}})
    assert mini["screens"] == portal + ["mini_ingreso", "mini_panel"] and mini["mini_types"] == ["sales"]
    mini_off = brand_screens.compute({"mini_panel": {"enabled": False, "settings": {"panels": {"sales": {"enabled": True}}}}})
    assert mini_off["screens"] == portal


def test_preview_pages_for_each_screen_family():
    from app.web import brand_preview

    mods = ({"code": "workforce", "name": "Workforce"}, {"code": "core_settings", "name": "Ajustes"}, {"code": "production_references", "name": "Refs"})
    dash = brand_preview.page(screen="portal_dashboard", company_id=A, css="", branding={}, mode="studio", screens=("portal_dashboard",), company_name="Velvet", modules=mods)
    assert "client.css" in dash and "Servicios activos" in dash and "Workforce" in dash and "REF" in dash
    assert "Ajustes</button>" in dash and "core_settings" not in dash, "el modulo de ajustes no sale en el menu, como en el portal"
    assert "hsp_brand.js" not in dash and "Panel Caja" not in dash
    login = brand_preview.page(screen="portal_ingreso", company_id=A, css="", branding={}, mode="studio", screens=("portal_ingreso",))
    assert "login.css" in login and "Client Portal" in login and "data:image" not in login
    # Una pantalla que la empresa no tiene cae en el panel principal.
    other = brand_preview.page(screen="caja", company_id=A, css="", branding={}, mode="studio", screens=("portal_dashboard",), company_name="Velvet")
    assert "Servicios activos" in other
