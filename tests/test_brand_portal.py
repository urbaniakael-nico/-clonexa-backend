"""Estudio de marca · etapa 2: el portal (/client).

- La hoja base del portal que arma el servidor es IDENTICA a la que arma hoy
  applyBranding() en client.js (se ejecuta el codigo real en node) para todas
  las combinaciones de estilo de fondo, tarjetas, modo y tipografia.
- El borrador inicial conserva colores, degradado y tipografia de
  company_branding (los mismos valores que normalizeBranding()).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from app.services import brand_theme as bt
from app.services import portal_base_css as portal_css

CLIENT_JS = Path("app/web/client.js")
NODE = shutil.which("node")

NODE_SCRIPT = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[process.argv.length - 1], 'utf8');
function grab(name) {
  const start = src.indexOf(`  function ${name}(`);
  if (start < 0) throw new Error('falta ' + name);
  let depth = 0, i = src.indexOf(') {', start) + 2;
  for (; i < src.length; i++) { if (src[i] === '{') depth++; else if (src[i] === '}') { depth--; if (depth === 0) break; } }
  return src.slice(start, i + 1);
}
const code = 'let cxBrandObserver050A = null;\n' + ['validHex', 'normalizeBranding', 'brandingBackground', 'fontProfile', 'cardProfile',
  'cxPortalBrand050A', 'cxPortalBrandMerge050A', 'cxBrandTagPieces050A', 'cxBrandWatch050A', 'cxPortalBrandApply050A', 'applyBranding'].map(grab).join('\n');
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = cases.map((raw) => {
  const els = {};
  const document = { head: { appendChild: (el) => { els[el.id] = el; } }, createElement: () => ({}) };
  const $ = (id) => els[id] || null;
  const state = { branding: raw };
  new Function('document', '$', 'state', 'window', code + '\napplyBranding();')(document, $, state, {});
  return els.clientBrandingDynamicStyle.textContent;
});
process.stdout.write(JSON.stringify(out));
"""


def _cases() -> list[dict]:
    cases = [{}]
    for style in portal_css.BACKGROUND_STYLES:
        cases.append({"background_style": style, "primary_color": "#123456", "secondary_color": "#abcdef", "background_color": "#0a0b0c",
                      "gradient_from": "#111111", "gradient_to": "#222222", "gradient_extra": "#333333"})
    for card in portal_css.CARD_STYLES:
        for mode in portal_css.THEME_MODES:
            cases.append({"card_style": card, "theme_mode": mode, "primary_color": "#ff0066", "secondary_color": "#00ccff"})
    for font in bt.PORTAL_FONTS:
        cases.append({"font_family": font, "visual_preset": "retail_neon", "text_color": "#101010"})
    cases.append({"visual_preset": "executive_light", "color_principal": "#334455", "mode": "light"})
    return cases


@pytest.mark.skipif(NODE is None, reason="node no disponible")
def test_portal_base_sheet_is_identical_to_client_js_applybranding():
    cases = _cases()
    run = subprocess.run([NODE, "-e", NODE_SCRIPT, str(CLIENT_JS)], input=json.dumps(cases), capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert run.returncode == 0, run.stderr
    js = json.loads(run.stdout)
    assert len(js) == len(cases)
    for raw, expected in zip(cases, js):
        got = portal_css.render(bt.normalize_branding(raw))
        assert got == expected, f"distinto para {raw}"


@pytest.mark.skipif(NODE is None, reason="node no disponible")
def test_initial_draft_published_gives_todays_portal_sheet():
    """Publicar el borrador inicial sin cambios = la misma hoja de hoy."""
    cid = str(uuid.uuid4())
    raw = {"primary_color": "#7c3aed", "secondary_color": "#22d3ee", "background_color": "#0b1020", "text_color": "#f1f5f9",
           "background_style": "neon_profundo", "card_style": "executive_glass", "theme_mode": "dark", "font_family": "Poppins"}
    run = subprocess.run([NODE, "-e", NODE_SCRIPT, str(CLIENT_JS)], input=json.dumps([raw]), capture_output=True, text=True, encoding="utf-8", timeout=120)
    today = " ".join(json.loads(run.stdout)[0].split())
    css = bt.css_for(bt.from_branding(raw), cid, page="portal")
    assert today in css, "la hoja de hoy esta completa dentro de la del servidor"
    extra = css.replace(today, "")
    assert "--cxb-primary:#7c3aed" in extra
    # Sin cambios, el borrador no agrega fondos, componentes ni piezas en el portal.
    assert "data-brand" not in css and "::before" not in css and "isolation" not in css


def test_initial_draft_keeps_colors_gradient_and_font():
    raw = {"primary_color": "#123456", "secondary_color": "#abcdef", "background_color": "#ffffff", "text_color": "#111111",
           "font_family": "Sora", "card_style": "classic_panel", "theme_mode": "classic", "background_style": "classic_dashboard",
           "gradient_from": "#101010", "gradient_to": "#202020", "gradient_extra": "#303030", "gradient_angle": 90, "logo_url": "javascript:x"}
    t = bt.from_branding(raw)
    c, p = t["theme"]["colors"], t["theme"]["portal"]
    assert (c["primary"], c["secondary"], c["background"], c["text"]) == ("#123456", "#abcdef", "#ffffff", "#111111")
    assert t["theme"]["font"]["family"] == "Sora" and t["theme"]["font"]["size"] is None
    assert p == {"background_style": "classic_dashboard", "card_style": "classic_panel", "theme_mode": "classic", "gradient_from": "#101010",
                 "gradient_to": "#202020", "gradient_extra": "#303030", "gradient_angle": 90}
    assert t["backgrounds"]["general"]["base"] == {"kind": "preset"}
    assert t["theme"]["logo"] is None and t["theme"]["panels"] is False
    assert t["backgrounds"]["portal_dashboard"] == {"inherit": True}
    assert t["backgrounds"]["caja"] == {"own": True} and t["backgrounds"]["mini_panel"] == {"own": True}
    assert t["backgrounds"]["portal_ingreso"] == {"own": True}, "el ingreso del portal sigue siendo el de Clonexa"
    login = bt.css_for(t, str(uuid.uuid4()), page="login")
    assert ".login-shell{" not in login.replace("html body ", "") and "isolation" not in login
    # Valores invalidos caen en los mismos valores por defecto que client.js.
    junk = bt.from_branding({"primary_color": "rojo", "font_family": "Comic Sans", "card_style": "x", "visual_preset": "boardroom_dark"})
    assert junk["theme"]["colors"]["primary"] == "#ff2bd6" and junk["theme"]["font"]["family"] == "Inter"
    assert junk["theme"]["portal"]["background_style"] == "corporate_dark" and junk["theme"]["portal"]["card_style"] == "glass_premium"


def test_panels_follow_brand_only_when_enabled():
    cid = str(uuid.uuid4())
    t = bt.from_branding({"primary_color": "#123456"}, panels=False)
    assert bt.applies_to(t, "portal") and not bt.applies_to(t, "panels") and not bt.applies_to(t, "mini")
    t2 = bt.from_branding({"primary_color": "#123456"}, panels=True)
    assert bt.applies_to(t2, "panels")
    # Con fondo propio, el borrador inicial no pinta los paneles.
    css = bt.css_for(t2, cid, page="panels")
    assert ".csh-login{" not in css.replace("html body ", "") and "isolation" not in css


def test_portal_pieces_have_selectors_for_the_runtime_tagger():
    sel = bt.portal_piece_selectors()
    for key in ("portal.barra_lateral", "portal.menu", "portal.menu_activo", "portal.logo", "portal.nombre", "portal.encabezado",
                "portal.indicador", "portal.accion", "portal.servicio", "portal.servicio_codigo", "portal.chip", "portal.tenant",
                "portal.ajustes", "portal.cerrar_sesion"):
        assert key in sel, key
    assert list(sel).index("portal.servicio_codigo") < list(sel).index("portal.chip"), "el codigo del servicio se marca antes que los chips"


def test_old_tokens_from_stage_one_still_validate():
    """Las marcas creadas antes (Radio Despecho) siguen validas y se aplican a los paneles."""
    old = {"theme": {"colors": dict(bt.CLONEXA_DEFAULT), "font": {"family": "Inter", "size": 15, "heading_weight": 700}, "radius": 14, "shadow": 30, "glow": 0, "logo": None},
           "backgrounds": {"general": {"base": {"kind": "solid", "color": "#000000"}, "image": None, "veil": None},
                           "ingreso": {"inherit": True}, "mesero": {"inherit": True}, "cocina": {"inherit": True}, "caja": {"inherit": True}},
           "components": {}, "pieces": {}}
    t = bt.validate(old)
    assert t["theme"]["panels"] is True and t["backgrounds"]["portal_dashboard"] == {"inherit": True}
    assert t["theme"]["portal"]["background_style"] == "aurora_boreal"


@pytest.mark.parametrize("bad,field", [
    ({"own": True}, "backgrounds.portal_dashboard.own"),
    ({"base": {"kind": "preset"}, "image": None, "veil": None, "inherit": "si"}, "backgrounds.portal_dashboard.inherit"),
])
def test_portal_screens_cannot_keep_a_panel_background(bad, field):
    t = bt.from_branding({})
    t["backgrounds"]["portal_dashboard"] = bad
    with pytest.raises(bt.BrandInvalid) as info:
        bt.validate(t)
    assert info.value.path == field


def test_portal_fields_reject_injection():
    t = bt.from_branding({})
    t["theme"]["portal"]["background_style"] = "aurora_boreal;}</style>"
    with pytest.raises(bt.BrandInvalid):
        bt.validate(t)
    t = bt.from_branding({})
    t["theme"]["panels"] = "true"
    with pytest.raises(bt.BrandInvalid):
        bt.validate(t)
    for tpl in bt.templates():
        css = bt.css_for(tpl["tokens"], str(uuid.uuid4()))
        assert not re.search(r"[<>\\]|javascript|expression\(", css)
