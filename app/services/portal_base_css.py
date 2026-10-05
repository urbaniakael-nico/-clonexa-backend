"""Hoja base del portal (/client) generada en el servidor (Estudio de marca, etapa 2).

La plantilla es COPIA TEXTUAL de la que arma applyBranding() en client.js
(misma estructura: rejilla, barra lateral, encabezado, tarjetas), con sus 11
valores reemplazados por marcadores @@nombre@@. Con marca publicada el portal
usa esta hoja (y applyBranding no inyecta la suya); sin marca, nada cambia.
Una prueba (tests/test_brand_portal.py) ejecuta el applyBranding real en node
y verifica que, con los mismos valores, las dos hojas son identicas.

Los valores llegan ya validados (hex, listas cerradas); este modulo solo los
combina igual que lo hace client.js. Generado desde client.js (no editar la
plantilla a mano: regenerarla si applyBranding cambia).
"""
from __future__ import annotations

TEMPLATE = r'''
      :root {
        --cx-primary: @@primary@@;
        --cx-secondary: @@secondary@@;
        --cx-bg: @@background@@;
        --cx-text: @@text@@;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-height: 100vh;
        color: @@text@@;
        background: @@body_bg@@ !important;
        font-family: @@font_family@@ !important;
        overflow-x: hidden;
      }

      #app, #app * {
        font-family: @@font_family@@ !important;
      }

      .client-shell {
        min-height: 100vh;
        padding: 18px;
        background:
          radial-gradient(circle at 10% 0%, @@primary@@18, transparent 28%),
          radial-gradient(circle at 90% 0%, @@secondary@@12, transparent 28%);
      }

      .client-layout {
        display: grid;
        grid-template-columns: 232px 1fr;
        gap: 18px;
        max-width: 1660px;
        margin: 0 auto;
      }

      .client-sidebar,
      .client-panel,
      .client-kpi,
      .client-module-card,
      .client-action-card {
        background: @@card_bg@@;
        border: @@card_border@@;
        box-shadow: @@card_shadow@@;
        backdrop-filter: blur(22px) saturate(1.25);
      }

      .client-sidebar {
        min-height: calc(100vh - 36px);
        border-radius: 22px;
        padding: 18px;
        position: sticky;
        top: 18px;
      }

      .client-logo {
        width: 62px;
        height: 62px;
        border-radius: 18px;
        display: grid;
        place-items: center;
        overflow: hidden;
        background: linear-gradient(145deg, @@primary@@, @@secondary@@);
        color: #020617;
        font-weight: 1000;
        box-shadow: 0 16px 34px @@primary@@3d;
      }

      .client-company-name,
      .client-title,
      .client-panel h2,
      .client-kpi strong,
      .client-module-card strong {
        letter-spacing: -.02em;
        font-weight: 900;
        text-transform: @@font_transform@@;
        text-shadow: 0 12px 32px rgba(0,0,0,.16);
        -webkit-text-stroke: 0 transparent;
        transform: none;
      }

      .client-company-name {
        margin: 14px 0 4px;
        font-size: 22px;
        line-height: 1.05;
      }

      .client-muted {
        color: @@muted@@;
        font-size: 14px;
        line-height: 1.45;
      }

      .client-nav {
        display: grid;
        gap: 9px;
        margin-top: 22px;
      }

      .client-nav button {
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.075);
        color: @@text@@;
        border-radius: 14px;
        padding: 12px 13px;
        text-align: left;
        cursor: pointer;
        font-size: 14px;
        font-weight: 850;
      }

      .client-nav button.active {
        border-color: @@secondary@@;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 12px 30px @@secondary@@24;
      }

      .client-main {
        display: grid;
        gap: 16px;
      }

      .client-hero {
        border-radius: 24px;
        padding: 22px 26px;
        background:
          radial-gradient(circle at 0% 0%, @@primary@@32, transparent 30%),
          radial-gradient(circle at 100% 0%, @@secondary@@22, transparent 30%),
          rgba(255,255,255,.052);
        border: 1px solid rgba(255,255,255,.14);
        box-shadow: 0 18px 54px rgba(0,0,0,.24);
      }

      .client-eyebrow,
      .client-label,
      .client-module-card small {
        letter-spacing: .18em;
        text-transform: uppercase;
        font-weight: 1000;
        color: @@secondary@@;
      }

      .client-eyebrow,
      .client-label {
        font-size: 11px;
        line-height: 1.2;
      }

      .client-title {
        font-size: clamp(34px, 4vw, 62px);
        line-height: .96;
        margin: 8px 0;
      }

      .client-kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(150px, 1fr));
        gap: 12px;
        margin-top: 16px;
      }

      .client-kpi {
        border-radius: 18px;
        padding: 15px 16px;
        min-height: 96px;
        overflow: hidden;
        color:inherit;
        font:inherit;
        text-align:left;
      }

      button.client-kpi{width:100%;cursor:pointer;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}
      button.client-kpi:hover{transform:translateY(-2px);border-color:color-mix(in srgb,var(--cx-primary,#38bdf8) 62%,#fff 12%)}
      .hsp-dashboard-kpi-030d small{display:block;margin-top:7px;color:color-mix(in srgb,var(--cx-text,#fff) 72%,transparent);font-size:11px;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .hsp-dashboard-kpi-030d strong:not(:empty){color:var(--cx-text,#fff)}

      .client-kpi span {
        display: block;
        opacity: .74;
        margin-bottom: 8px;
        font-size: 13px;
        line-height: 1.2;
      }

      .client-kpi strong {
        font-size: clamp(25px, 2.15vw, 33px);
        line-height: 1.02;
        display: block;
      }

      .client-actions {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-top: 18px;
      }

      .client-btn {
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 14px;
        padding: 12px 16px;
        color: #020617;
        background: linear-gradient(135deg, @@secondary@@, @@primary@@);
        box-shadow: 0 14px 34px @@primary@@35;
        font-size: 14px;
        font-weight: 950;
        cursor: pointer;
      }

      .client-panel {
        border-radius: 22px;
        padding: 20px;
      }

      .client-panel h2 {
        margin: 10px 0 16px;
        font-size: clamp(23px, 2vw, 32px);
        line-height: 1.05;
      }

      .client-module-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(176px, 1fr));
        gap: 12px;
      }

      .client-module-card {
        min-height: 110px;
        border-radius: 18px;
        padding: 15px 16px;
        width: 100%;
        color: inherit;
        text-align: left;
        cursor: pointer;
        border: 1px solid rgba(255,255,255,.12);
        font: inherit;
        display: grid;
        grid-template-rows: auto auto 1fr;
        align-content: start;
        gap: 10px;
        background: linear-gradient(145deg, rgba(255,255,255,.105), rgba(255,255,255,.045));
        box-shadow: inset 0 1px 0 rgba(255,255,255,.10), 0 14px 34px rgba(0,0,0,.16);
        transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
      }

      .client-module-card strong {
        display: block;
        margin-top: 4px;
        font-size: 16px;
        line-height: 1.08;
      }

      .client-module-card small {
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
        max-width: 20ch;
        font-size: 10px;
        line-height: 1.34;
      }

      .client-module-card:hover {
        transform: translateY(-1px);
        border-color: rgba(255,255,255,.22);
        box-shadow: inset 0 1px 0 rgba(255,255,255,.13), 0 18px 42px rgba(0,0,0,.22);
      }

      .client-status-list {
        display: grid;
        gap: 12px;
      }

      .client-status-row {
        display: flex;
        justify-content: space-between;
        gap: 16px;
        padding: 12px 0;
        border-bottom: 1px solid rgba(255,255,255,.1);
      }

      .client-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        padding: 8px 11px;
        min-width: 44px;
        background: @@secondary@@;
        color: #020617;
        font-size: 12px;
        line-height: 1;
        font-weight: 1000;
        box-shadow: 0 12px 26px @@secondary@@35;
      }

      .client-footer-id {
        margin-top: auto;
        padding: 12px;
        border-radius: 14px;
        background: rgba(0,0,0,.2);
        border: 1px solid rgba(255,255,255,.1);
        word-break: break-all;
        font-size: 12px;
      }

      @media (max-width: 900px) {
        .client-layout {
          grid-template-columns: 1fr;
        }

        .client-sidebar {
          position: static;
          min-height: auto;
        }

        .client-kpi-grid {
          grid-template-columns: 1fr 1fr;
        }
      }
    '''

BACKGROUND_STYLES = ("aurora_boreal", "neon_profundo", "holografico", "cyber_grid", "corporate_dark", "corporate_light", "classic_dashboard", "neutral_slate")
CARD_STYLES = ("glass_premium", "neon_border", "soft_solid", "dark_elevated", "classic_panel", "flat_dashboard", "executive_glass")
THEME_MODES = ("dark", "light", "classic", "corporate")


def branding_background(b: dict) -> str:
    """Port de brandingBackground(b) de client.js."""
    p, s, bg = b["primary_color"], b["secondary_color"], b["background_color"]
    gf, gt, ge = b["gradient_from"], b["gradient_to"], b["gradient_extra"]
    style = b["background_style"]
    if style == "corporate_light":
        return f"""
        radial-gradient(circle at 0% 0%, {s}22, transparent 32%),
        radial-gradient(circle at 100% 0%, {p}12, transparent 32%),
        linear-gradient(135deg, {gf}, {gt})
      """
    if style == "corporate_dark":
        return f"""
        radial-gradient(circle at 8% 0%, {s}1f, transparent 30%),
        radial-gradient(circle at 100% 4%, {p}24, transparent 34%),
        linear-gradient(135deg, {bg}, #020617 72%)
      """
    if style == "classic_dashboard":
        return f"""
        linear-gradient(135deg, {gf}, {gt}),
        radial-gradient(circle at 80% 0%, {ge}44, transparent 35%)
      """
    if style == "neutral_slate":
        return f"""
        radial-gradient(circle at 10% 0%, {p}1f, transparent 30%),
        radial-gradient(circle at 90% 0%, {s}1f, transparent 30%),
        linear-gradient(135deg, #020617, #111827 52%, {bg})
      """
    if style == "holografico":
        return f"""
        radial-gradient(circle at 0% 0%, {p}88, transparent 32%),
        radial-gradient(circle at 100% 0%, {s}66, transparent 34%),
        radial-gradient(circle at 50% 100%, {bg}88, transparent 40%),
        linear-gradient(135deg, {bg}, {p})
      """
    if style == "cyber_grid":
        return f"""
        linear-gradient(rgba(255,255,255,.055) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px),
        radial-gradient(circle at 85% 0%, {s}55, transparent 34%),
        linear-gradient(135deg, {bg}, #020617)
      """
    if style == "neon_profundo":
        return f"""
        radial-gradient(circle at 12% 8%, {p}66, transparent 34%),
        radial-gradient(circle at 88% 12%, {s}44, transparent 34%),
        linear-gradient(135deg, {bg}, #050509)
      """
    return f"""
      radial-gradient(circle at 0% 0%, {p}55, transparent 32%),
      radial-gradient(circle at 100% 0%, {s}44, transparent 32%),
      linear-gradient(135deg, {bg}, {s}22)
    """


FONT_PROFILES = {
    "Inter": ("Inter, system-ui, sans-serif", "none"),
    "Manrope": ("Manrope, Trebuchet MS, system-ui, sans-serif", "none"),
    "Sora": ("Sora, Arial Black, system-ui, sans-serif", "uppercase"),
    "Space Grotesk": ("Courier New, monospace", "uppercase"),
    "Rajdhani": ("Arial Narrow, Impact, system-ui, sans-serif", "uppercase"),
    "Orbitron": ("Courier New, monospace", "uppercase"),
    "Poppins": ("Poppins, Segoe UI, system-ui, sans-serif", "none"),
    "Montserrat": ("Montserrat, Impact, Arial Black, sans-serif", "uppercase"),
}


def card_profile(b: dict) -> dict:
    """Port de cardProfile(b) de client.js."""
    p, s, style = b["primary_color"], b["secondary_color"], b["card_style"]
    if style == "classic_panel":
        return {"bg": "linear-gradient(145deg, rgba(255,255,255,.78), rgba(241,245,249,.58))", "border": "1px solid rgba(15,23,42,.16)", "shadow": "0 18px 54px rgba(15,23,42,.14)"}
    if style == "flat_dashboard":
        return {"bg": "linear-gradient(145deg, rgba(255,255,255,.9), rgba(248,250,252,.72))", "border": "1px solid rgba(15,23,42,.12)", "shadow": "0 14px 40px rgba(15,23,42,.12)"}
    if style == "executive_glass":
        return {"bg": "linear-gradient(145deg, rgba(15,23,42,.76), rgba(255,255,255,.07))", "border": "1px solid rgba(255,255,255,.17)", "shadow": "0 24px 84px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.1)"}
    if style == "neon_border":
        return {"bg": f"linear-gradient(145deg, {p}28, rgba(255,255,255,.075), {s}1f)", "border": f"1px solid {p}cc", "shadow": f"0 0 44px {p}55, 0 28px 92px rgba(0,0,0,.36), inset 0 0 0 1px rgba(255,255,255,.08)"}
    if style == "soft_solid":
        return {"bg": "linear-gradient(145deg, rgba(255,255,255,.88), rgba(255,255,255,.58))", "border": "1px solid rgba(255,255,255,.78)", "shadow": "0 24px 80px rgba(15,23,42,.18)"}
    if style == "dark_elevated":
        return {"bg": "linear-gradient(145deg, rgba(2,6,23,.94), rgba(15,23,42,.78))", "border": "1px solid rgba(255,255,255,.16)", "shadow": "0 32px 110px rgba(0,0,0,.55)"}
    return {"bg": "linear-gradient(145deg, rgba(255,255,255,.13), rgba(255,255,255,.045))", "border": "1px solid rgba(255,255,255,.14)", "shadow": "0 24px 80px rgba(0,0,0,.28), inset 0 0 0 1px rgba(255,255,255,.035)"}


def render(b: dict, body_bg: str | None = None) -> str:
    """La hoja de applyBranding con estos valores (b ya normalizado y validado).
    body_bg reemplaza el fondo calculado (un fondo propio del estudio)."""
    family, transform = FONT_PROFILES.get(b["font_family"], FONT_PROFILES["Inter"])
    cp = card_profile(b)
    light = b["theme_mode"] in ("light", "classic") or b["card_style"] in ("soft_solid", "flat_dashboard", "classic_panel")
    values = {
        "primary": b["primary_color"], "secondary": b["secondary_color"], "background": b["background_color"], "text": b["text_color"],
        "body_bg": body_bg if body_bg is not None else branding_background(b), "font_family": family, "font_transform": transform,
        "card_bg": cp["bg"], "card_border": cp["border"], "card_shadow": cp["shadow"],
        "muted": "rgba(15,23,42,.64)" if light else "rgba(255,255,255,.68)",
    }
    out = TEMPLATE
    for key, value in values.items():
        out = out.replace(f"@@{key}@@", value)
    return out
