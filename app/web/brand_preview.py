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


# ------------------------------------------------------------ portal (/client)
@lru_cache(maxsize=1)
def portal_module_catalog() -> tuple[dict, frozenset]:
    """MODULE_UI y los codigos ocultos de client.js, leidos del propio archivo:
    la muestra arma el menu y las tarjetas con la misma tabla que el portal."""
    src = (WEB / "client.js").read_text(encoding="utf-8")
    start = src.index("const MODULE_UI = {")
    block = src[start: src.index("};", start)]
    catalog = {m.group(1): (m.group(2), m.group(3), m.group(4))
               for m in re.finditer(r'^\s*([a-z0-9_]+): \["([^"]*)", "([^"]*)", "([^"]*)"\]', block, re.M)}
    hidden = set()
    for name in ("const CLIENT_HIDDEN_MODULE_CODES = new Set([", "const CX_HIDDEN_CLIENT_MODULE_CODES_017H = new Set(["):
        i = src.index(name)
        hidden |= set(re.findall(r'"([a-z0-9_]+)"', src[i: src.index("]", i)]))
    return catalog, frozenset(hidden)


def portal_modules(modules: list[dict]) -> list[dict]:
    """Lo mismo que normalizeClientModule + visibleClientModules de client.js."""
    catalog, hidden = portal_module_catalog()
    out = []
    for index, m in enumerate(modules or []):
        code = str(m.get("code") or "").strip()
        key = re.sub(r"^_+|_+$", "", re.sub(r"[^a-z0-9]+", "_", code.lower()))
        if not code or key in hidden or "core_settings" in key or "tenant_settings" in key or "company_settings" in key:
            continue
        meta = catalog.get(code) or catalog.get(key) or (m.get("name") or code, m.get("category") or "servicio activo", (code or str(index + 1))[:3].upper())
        out.append({"code": code, "title": meta[0], "subtitle": meta[1], "badge": meta[2]})
    return out


def _portal_sidebar(company_name: str, modules: list[dict], active: str) -> str:
    nav = [f'<button class="{"active" if active == "dashboard" else ""}" type="button" data-brand="{"portal.menu_activo" if active == "dashboard" else "portal.menu"}">Dashboard</button>']
    for m in modules:
        if m["code"] == "nomina_colombia":
            continue
        is_active = m["code"] == active
        nav.append(f'<button class="{"active" if is_active else ""}" type="button" data-brand="{"portal.menu_activo" if is_active else "portal.menu"}">{html.escape(m["title"])}</button>')
    initial = html.escape((company_name or "C")[:1].upper())
    return f"""
          <aside class="client-sidebar" data-brand="portal.barra_lateral">
            <div class="client-logo" data-brand="portal.logo"><span data-cxpv-logo>{initial}</span></div>
            <h2 class="client-company-name" data-brand="portal.nombre">{html.escape(company_name or "Empresa")}</h2>
            <div class="client-muted">empresa-de-muestra</div>
            <nav class="client-nav">{"".join(nav)}</nav>
            <div class="client-footer-id" data-brand="portal.tenant"><strong>Tenant activo</strong><br>00000000-0000-0000-0000-000000000000</div>
            <div class="clx-core-actions" id="clxCoreActions">
              <button class="clx-core-action-btn" id="clxOpenCoreSettings" type="button" data-brand="portal.ajustes">⚙ Ajustes</button>
              <button class="clx-core-action-btn clx-core-logout" id="clxCoreLogout" type="button" data-brand="portal.cerrar_sesion">⏻ Cerrar sesión</button>
            </div>
          </aside>"""


def _portal_dashboard(company_name: str, modules: list[dict]) -> str:
    cards = "".join(f"""
                  <button class="client-module-card" type="button" data-brand="portal.servicio">
                    <div class="client-badge" data-brand="portal.servicio_codigo">{html.escape(m["badge"])}</div>
                    <strong>{html.escape(m["title"])}</strong>
                    <small>{html.escape(m["subtitle"])}</small>
                  </button>""" for m in modules) or """
                  <div class="client-module-card"><div class="client-badge">OFF</div><strong>Sin modulos activos</strong><small>Activa un paquete desde Admin V2</small></div>"""
    kpis = "".join(f'<div class="client-kpi" data-brand="portal.indicador"><span>{label}</span><strong>{value}</strong></div>'
                   for label, value in (("Personal activo", "12"), ("Canales", "3"), ("Módulos", str(len(modules))), ("Estado", "Activo")))
    return f"""
      <main id="clientDashboardRoot030D" class="client-shell">
        <div class="client-layout">{_portal_sidebar(company_name, modules, "dashboard")}
          <section class="client-main">
            <header class="client-hero" data-brand="portal.encabezado">
              <div class="cxpv-row">
                <div>
                  <div class="client-eyebrow">Sistema operativo empresarial</div>
                  <h1 class="client-title">{html.escape(company_name or "Empresa")}</h1>
                  <p class="client-muted">Panel operativo independiente conectado a sus modulos activos.</p>
                </div>
                <span class="client-badge" data-brand="portal.chip">LIVE</span>
              </div>
              <div class="client-kpi-grid">{kpis}</div>
              <div class="client-actions">
                <button class="client-btn" type="button" data-brand="portal.accion">Ver reportes</button>
                <button class="client-btn" type="button" data-brand="portal.accion">Nuevo registro</button>
              </div>
            </header>
            <section class="client-panel">
              <div class="cxpv-row cxpv-gap">
                <div><div class="client-eyebrow">Modulos del panel</div><h2>Servicios activos</h2></div>
                <span class="client-badge" data-brand="portal.chip">{len(modules)} modulos activos</span>
              </div>
              <div class="client-module-grid">{cards}</div>
            </section>
          </section>
        </div>
      </main>"""


def _portal_module(company_name: str, modules: list[dict]) -> str:
    module = modules[0] if modules else {"code": "modulo", "title": "Módulo", "subtitle": "vista de módulo"}
    rows = "".join(f"<tr><td>Registro de muestra {n}</td><td>Activo</td><td>$ {n * 12}.000</td></tr>" for n in range(1, 6))
    return f"""
      <main class="client-shell">
        <div class="client-layout">{_portal_sidebar(company_name, modules, module["code"])}
          <section class="client-main">
            <header class="client-hero" data-brand="portal.encabezado">
              <div class="client-eyebrow">Modulo {html.escape(module["title"])}</div>
              <h1 class="client-title">{html.escape(module["title"])}</h1>
              <p class="client-muted">{html.escape(module["subtitle"])} · datos de muestra.</p>
              <div class="client-actions"><button class="client-btn" type="button" data-brand="portal.accion">Nuevo</button>
                <button class="client-btn" type="button" data-brand="portal.accion">Exportar CSV</button></div>
            </header>
            <section class="client-panel">
              <div class="client-eyebrow">Listado</div><h2>Registros de muestra</h2>
              <table class="cxpv-table"><thead><tr><th>Nombre</th><th>Estado</th><th>Valor</th></tr></thead><tbody>{rows}</tbody></table>
            </section>
          </section>
        </div>
      </main>"""


@lru_cache(maxsize=1)
def login_inline_css() -> str:
    """El <style> propio de login.html (sin la imagen de fondo, que no se copia)."""
    src = (WEB / "login.html").read_text(encoding="utf-8")
    match = re.search(r"<style>(.*?)</style>", src, re.S)
    css = match.group(1) if match else ""
    return "" if ("url(" in css or "</style" in css.lower()) else css


def _portal_login() -> str:
    return """
  <div class="grid"></div>
  <main class="login-shell">
    <section class="login-card" data-brand="portal.ingreso_tarjeta">
      <div class="brand"><span class="wordmark">CLONEXA</span><span class="status"><i></i> LIVE ACCESS</span></div>
      <h1>Client Portal</h1>
      <p>Acceso empresarial seguro al sistema operativo en tiempo real.</p>
      <form>
        <label>Email</label><input type="email" value="admin@empresa-de-muestra.com" readonly />
        <label>Contraseña</label><input type="password" value="muestra" readonly />
        <button type="submit" data-brand="portal.ingreso_entrar">Entrar</button>
      </form>
      <footer>CLONEXA SaaS Control Layer</footer>
    </section>
  </main>"""


# ------------------------------------------------------------ mini paneles
def _mini_login(type_label: str) -> str:
    return f"""
  <main id="miniPanelApp" class="mp-root">
      <section class="mp-card" data-brand="mini.ingreso_tarjeta">
        <div class="mp-kicker">Acceso operativo</div>
        <h1>{html.escape(type_label)}</h1>
        <p>Ingresa con el usuario y clave generados desde el panel de la empresa.</p>
        <form class="mp-form">
          <div class="mp-field"><label>Usuario</label><input value="usuario.muestra" readonly /></div>
          <div class="mp-field"><label>Clave</label><input type="password" value="muestra" readonly /></div>
          <button class="mp-button" type="submit" data-brand="mini.ingreso_entrar">Entrar</button>
        </form>
      </section>
  </main>"""


def _mini_panel(type_label: str, company_name: str) -> str:
    chips = "".join(f'<span class="mp-chip" data-brand="mini.chip">{c}</span>' for c in ("Vendedor: Usuario de muestra", "Rol: operador", "Ubicación: Tienda de muestra"))
    kpis = "".join(f'<article class="mp-kpi-card" data-brand="mini.indicador"><span>{a}</span><strong>{b}</strong><small>{c}</small></article>'
                   for a, b, c in (("Ventas del mes", "$ 4.250.000", "meta $ 6.000.000"), ("Avance", "71 %", "de la meta"), ("Turno", "05:42:10", "activo")))
    return f"""
  <main id="miniPanelApp" class="mp-root">
      <section class="mp-sales-dashboard mp-sales-dashboard-r1 mp-sales-dashboard-r2 mp-sales-dashboard-r3">
        <header class="mp-sales-header mp-sales-header-r1 mp-sales-header-r2 mp-sales-header-r3" data-brand="mini.encabezado">
          <section class="mp-header-main mp-header-main-r1 mp-header-main-r2 mp-header-main-r3">
            <div class="mp-kicker">Mini Panel {html.escape(type_label)}</div>
            <h1>{html.escape(company_name or "Empresa")}</h1>
            <p>Portal operativo personalizado para Usuario de muestra.</p>
            <div class="mp-meta compact">{chips}</div>
          </section>
        </header>
        <section class="mp-dashboard-section"><div class="mp-kpi-grid">{kpis}</div>
          <button class="mp-button" type="button">Registrar venta</button></section>
      </section>
  </main>"""


SCREENS = {
    "ingreso": lambda **_: _login("csh", "Panel Caja"),
    "mesero": lambda **_: _waiter(),
    "cocina": lambda **_: _kitchen(),
    "caja": lambda **_: _cashier(),
    "portal_dashboard": lambda company_name="", modules=(), **_: _portal_dashboard(company_name, portal_modules(list(modules))),
    "portal_modulo": lambda company_name="", modules=(), **_: _portal_module(company_name, portal_modules(list(modules))),
    "portal_ingreso": lambda **_: _portal_login(),
    "mini_ingreso": lambda mini_label="Ventas", **_: _mini_login(mini_label),
    "mini_panel": lambda mini_label="Ventas", company_name="", **_: _mini_panel(mini_label, company_name),
}


def _head_and_body(screen: str, body: str) -> tuple[str, str, str]:
    """(estilos del head, atributos del body, contenido del body) segun la familia."""
    from app.services import brand_theme as bt

    page_kind = bt.registry()["screens"][screen]["page"]
    if page_kind == "portal":
        core = _static_css("client_core_settings.js", r"style\.textContent\s*=\s*`(.*?)`;")
        head = f'<link rel="stylesheet" href="/client-static/client.css" />\n  <style>{core}</style>'
        return head, "", f'<div class="grid"></div>\n  <main id="app" class="client-shell">{body}</main>'
    if page_kind == "login":
        return f'<link rel="stylesheet" href="/client-static/login.css" />\n  <style>{login_inline_css()}</style>', "", body
    if page_kind == "mini":
        cls = ' class="mp-shell-body"' if screen == "mini_panel" else ""
        return '<link rel="stylesheet" href="/client-static/mini_panel.css" />', cls, body
    return f"<style>{panel_css(PANEL_JS[screen])}</style>", "", f'<main id="app">{body}</main>'


def page(*, screen: str, company_id: str, css: str, branding: dict, mode: str, banner: str = "", nav_token: str = "",
         screens: tuple[str, ...] = ("ingreso", "mesero", "cocina", "caja"), company_name: str = "", modules: tuple = (),
         mini_label: str = "Ventas", logo_url: str = "") -> str:
    """HTML de la vista previa. `css` ya viene del generador (css_for)."""
    from app.services import brand_theme as bt

    reg = bt.registry()
    allowed = [k for k in (screens or ()) if k in SCREENS and k in reg["screens"]] or ["portal_dashboard"]
    screen = screen if screen in allowed else allowed[0]
    page_kind = reg["screens"][screen]["page"]
    data = json.dumps({"company_id": company_id, "screen": screen, "mode": mode, "branding": branding if page_kind in ("panels", "mini") else None,
                       "logo": logo_url if page_kind == "portal" else ""},
                      ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    safe_css = css.replace("</", "<\\/")  # el generador ya no emite "<"; doble seguro
    nav = ""
    if nav_token:
        from urllib.parse import quote

        nav = '<nav class="cxpv-nav" aria-label="Pantallas">' + "".join(
            f'<a class="cxpv-link{" is-active" if key == screen else ""}" href="/vista-marca/{quote(nav_token, safe=".-_")}?screen={key}">{html.escape(reg["screens"][key]["label"])}</a>'
            for key in screens if key in SCREENS) + "</nav>"
    strip = f'<div class="cxpv-banner" role="status"><span>{html.escape(banner)}</span>{nav}</div>' if banner else ""
    head, body_attr, body = _head_and_body(screen, SCREENS[screen](company_name=company_name, modules=modules, mini_label=mini_label))
    brand_js = '<script src="/client-static/hsp_brand.js?v=049V_BRAND"></script>' if page_kind in ("panels", "mini") else ""
    return f"""<!doctype html>
<html lang="es" data-cx-preview="{html.escape(mode)}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta name="robots" content="noindex" />
  <title>Vista previa de marca</title>
  {head}
  <link rel="stylesheet" href="/client-static/brand_preview.css" />
</head>
<body{body_attr}>
  {strip}
  {body}
  <script type="application/json" id="cxPreviewData">{data}</script>
  <style id="cxBrandTheme">{safe_css}</style>
  {brand_js}
  <script src="/client-static/brand_preview.js?v=ETAPA2"></script>
</body>
</html>"""
