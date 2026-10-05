"""Vista previa de la marca: las pantallas reales con DATOS DE MUESTRA FIJOS.

Nunca muestra datos de la empresa (ni mesas, ni pedidos, ni usuarios): solo
el texto de muestra de aqui abajo. Usa las mismas hojas de estilo de los
mini paneles (copiadas de hsp_*.js, que las traen como texto fijo) y las
mismas clases y data-brand, asi la vista previa se ve como el panel real.

La pagina no permite entrar a ningun panel: los formularios y botones no
hacen nada (brand_preview.js los bloquea) y no carga ningun script de los
paneles, solo hsp_brand.js (colores) y brand_preview.js.
"""
from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path

WEB = Path(__file__).resolve().parent
PANEL_JS = {"ingreso": "hsp_cashier.js", "mesero": "hsp_waiter.js", "cocina": "hsp_kitchen.js", "caja": "hsp_cashier.js"}

# Content-Security-Policy propia de la vista previa (no es /admin-v2plus).
PREVIEW_CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
               "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; "
               "base-uri 'none'; form-action 'none'")


def _static_css(file_name: str, pattern: str) -> str:
    source = (WEB / file_name).read_text(encoding="utf-8")
    match = re.search(pattern, source, re.S)
    css = match.group(1) if match else ""
    if "${" in css or "</style" in css.lower():
        return ""
    return css


@lru_cache(maxsize=8)
def panel_css(file_name: str) -> str:
    """La hoja compartida (hsp_menu_kit.js, que cargan caja y mesero) y la propia del panel."""
    own = _static_css(file_name, r"style\.textContent\s*=\s*`(.*?)`;")
    if file_name == "hsp_kitchen.js":
        return own
    return _static_css("hsp_menu_kit.js", r"const STYLES\s*=\s*`(.*?)`;") + "\n" + own


def _login(prefix: str, title: str) -> str:
    return f"""
      <section class="{prefix}-login">
        <div class="{prefix}-login-card" data-brand="ingreso.tarjeta">
          <div class="{prefix}-brand" data-brand="ingreso.marca">CLONEXA</div>
          <h1 data-brand="ingreso.titulo">{html.escape(title)}</h1>
          <form>
            <label>Usuario<input name="username" value="cajero.demo" readonly /></label>
            <label>Clave<input name="password" type="password" value="muestra" readonly /></label>
            <button type="submit" class="{prefix}-btn {prefix}-btn-primary" data-brand="ingreso.entrar">Entrar</button>
          </form>
        </div>
      </section>"""


def _waiter() -> str:
    tables = "".join(f'<button class="wtr-tile" type="button" data-brand="mesero.mesa">Mesa {n}</button>' for n in range(1, 9))
    return f"""
      <section class="wtr-shell">
        <header class="wtr-header" data-brand="mesero.encabezado">
          <button class="wtr-back" type="button" aria-label="Volver">‹</button>
          <h1>Elige la mesa</h1>
        </header>
        <div class="wtr-grid-tables">{tables}</div>
        <div class="wtr-cart-list">
          <button class="wtr-cart-row" type="button"><div><b>2× Bandeja de muestra</b><div class="wtr-cart-note">Sin cebolla</div></div>
            <div class="wtr-cart-row-actions"><strong>$ 38.000</strong></div></button>
          <button class="wtr-cart-row" type="button"><div><b>1× Limonada de muestra</b></div>
            <div class="wtr-cart-row-actions"><strong>$ 7.000</strong></div></button>
        </div>
        <div class="wtr-cart-total"><span>Total</span><strong>$ 45.000</strong></div>
        <button class="wtr-btn wtr-btn-primary" type="button" data-brand="mesero.enviar_pedido">Confirmar y enviar</button>
      </section>"""


def _kitchen() -> str:
    def card(table: str, minutes: int, cls: str, items: list[tuple[str, bool]]) -> str:
        lines = "".join(
            f'<div class="ktc-item {"is-ready" if ready else ""}"><div class="ktc-item-main"><b>{html.escape(name)}</b></div>'
            + ('<span class="ktc-ready-pill">LISTO</span>' if ready else '<button type="button" class="ktc-btn ktc-btn-mini">LISTO</button>') + "</div>"
            for name, ready in items)
        return f"""
        <article class="ktc-card {cls}" data-brand="cocina.comanda">
          <header><div class="ktc-table">{table}</div><div class="ktc-meta"><span class="ktc-waiter">Mesero de muestra</span><span class="ktc-timer">{minutes} min</span></div></header>
          <div class="ktc-items">{lines}</div>
          <button type="button" class="ktc-btn ktc-btn-primary" data-brand="cocina.listo">COMANDA LISTA</button>
        </article>"""
    return f"""
      <section class="ktc-shell">
        <header class="ktc-header" data-brand="cocina.encabezado">
          <h1>Cocina</h1>
          <div class="ktc-legend"><span class="ktc-dot ktc-timer-green"></span> &lt; 10 min <span class="ktc-dot ktc-timer-yellow"></span> 10-20 <span class="ktc-dot ktc-timer-red"></span> &gt; 20 min</div>
          <button class="ktc-btn ktc-btn-tab" type="button">Entregadas hoy</button>
        </header>
        <div class="ktc-board">
          {card("Mesa 3", 4, "ktc-timer-green", [("1× Bandeja de muestra", False), ("2× Arepa de muestra", True)])}
          {card("Mesa 7", 14, "ktc-timer-yellow", [("3× Plato de muestra", False)])}
          {card("Domicilio", 23, "ktc-timer-red", [("1× Combo de muestra", True)])}
        </div>
      </section>"""


def _cashier() -> str:
    def table(n: int, state: str, label: str, total: str) -> str:
        return f"""
        <button class="csh-card csh-card-{state}" type="button" data-brand="caja.mesa">
          <div class="csh-card-top"><div class="csh-card-number"><small>Mesa</small><b>{n}</b></div><span class="csh-card-timer">⏱ 25 min</span></div>
          <span class="csh-card-state">{label}</span><div class="csh-card-waiter">Mesero de muestra</div><strong class="csh-card-total">{total}</strong>
        </button>"""
    pay = "".join(f'<button class="csh-btn csh-btn-primary" type="button" data-brand="caja.cobrar">{m}</button>' for m in ("Efectivo", "Tarjeta", "Transferencia"))
    return f"""
      <section class="csh-shell">
        <header class="csh-header" data-brand="caja.encabezado">
          <button class="csh-back" type="button" aria-label="Volver">‹</button>
          <h1>Caja · muestra</h1>
          <button class="csh-logout" type="button" aria-label="Salir">⏻</button>
        </header>
        <div class="csh-grid-tables">
          {table(2, "entregado", "Entregado", "$ 54.000")}{table(5, "preparando", "En preparación", "$ 31.500")}{table(9, "pendiente", "Pendiente", "$ 12.000")}
        </div>
        <div class="csh-detail">
          <table class="csh-detail-lines"><thead><tr><th>Cant.</th><th>Producto</th><th>Valor</th></tr></thead>
            <tbody><tr><td>2×</td><td>Bandeja de muestra</td><td>$ 38.000</td></tr><tr><td>1×</td><td>Limonada de muestra</td><td>$ 7.000</td></tr></tbody>
            <tfoot><tr><td colspan="2">Total</td><td>$ 45.000</td></tr></tfoot></table>
          <div class="csh-detail-actions"><button class="csh-btn" type="button">+ Agregar producto</button><button class="csh-btn" type="button">🖨 Imprimir cuenta</button></div>
          <div class="csh-pay-block"><div class="csh-pay-title">Datos de cobro · método de pago obligatorio</div><div class="csh-pay-options">{pay}</div></div>
        </div>
      </section>"""


SCREENS = {
    "ingreso": lambda: _login("csh", "Panel Caja"),
    "mesero": _waiter,
    "cocina": _kitchen,
    "caja": _cashier,
}


def page(*, screen: str, company_id: str, css: str, branding: dict, mode: str, banner: str = "", nav_token: str = "") -> str:
    """HTML de la vista previa. `css` ya viene del generador (css_for)."""
    screen = screen if screen in SCREENS else "ingreso"
    data = json.dumps({"company_id": company_id, "screen": screen, "mode": mode, "branding": branding},
                      ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    safe_css = css.replace("</", "<\\/")  # el generador ya no emite "<"; doble seguro
    nav = ""
    if nav_token:
        from urllib.parse import quote

        labels = {"ingreso": "Ingreso", "mesero": "Mesero", "cocina": "Cocina", "caja": "Caja"}
        nav = '<nav class="cxpv-nav" aria-label="Pantallas">' + "".join(
            f'<a class="cxpv-link{" is-active" if key == screen else ""}" href="/vista-marca/{quote(nav_token, safe=".-_")}?screen={key}">{label}</a>'
            for key, label in labels.items()) + "</nav>"
    strip = f'<div class="cxpv-banner" role="status"><span>{html.escape(banner)}</span>{nav}</div>' if banner else ""
    return f"""<!doctype html>
<html lang="es" data-cx-preview="{html.escape(mode)}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta name="robots" content="noindex" />
  <title>Vista previa de marca</title>
  <style>{panel_css(PANEL_JS[screen])}</style>
  <link rel="stylesheet" href="/client-static/brand_preview.css" />
</head>
<body>
  {strip}
  <main id="app">{SCREENS[screen]()}</main>
  <script type="application/json" id="cxPreviewData">{data}</script>
  <style id="cxBrandTheme">{safe_css}</style>
  <script src="/client-static/hsp_brand.js?v=049V_BRAND"></script>
  <script src="/client-static/brand_preview.js?v=FASE4"></script>
</body>
</html>"""
