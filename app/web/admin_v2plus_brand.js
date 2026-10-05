// Consola v2+ · Estudio de marca (Fase 4, parte 3).
// Tres columnas: árbol (Tema → Fondos → Componentes → Piezas), vista previa
// en vivo de las pantallas reales con datos de muestra (iframe del mismo
// origen) y controles de lo seleccionado. Editar solo cambia el borrador; los
// operarios ven lo publicado. Nada de CSS libre: todo control escribe valores
// (hex, números con rango, opciones) que el servidor vuelve a validar.
// Sin estilos ni scripts en línea: tamaños y colores dinámicos por CSSOM.
(() => {
  "use strict";

  const API = "/admin-v2/api/brand";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const clone = (v) => JSON.parse(JSON.stringify(v));
  const fold = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const FAMILY_ORDER = ["portal", "restaurante", "mini"];
  // Una sola lista de pantallas: las pestañas sobre la vista previa.
  const TAB_ORDER = ["portal_dashboard", "portal_ingreso", "portal_modulo", "ingreso", "mesero", "cocina", "caja", "mini_ingreso", "mini_panel"];
  const TAB_LABELS = { portal_dashboard: "Panel principal", portal_ingreso: "Ingreso", portal_modulo: "Vista de módulo", ingreso: "Ingreso de paneles",
    mesero: "Mesero", cocina: "Cocina", caja: "Caja", mini_ingreso: "Ingreso de mini panel", mini_panel: "Mini panel" };
  // Así lo usa cada quien: el cliente en pantalla grande, el mesero en el celular.
  const defaultSize = (screen) => (String(screen || "").startsWith("portal_") ? "desktop" : "phone");
  // Piezas del panel principal que también están en la vista de módulo.
  const MODULE_VIEW_PIECES = new Set(["portal.barra_lateral", "portal.logo", "portal.nombre", "portal.menu", "portal.menu_activo", "portal.encabezado",
    "portal.accion", "portal.tenant", "portal.ajustes", "portal.cerrar_sesion"]);
  const THEME_ITEMS = [
    ["colors", "Colores", "Primario, fondo, texto y acentos de toda la marca"],
    ["font", "Tipografía", "Letra, tamaño base y peso de los títulos"],
    ["shape", "Forma y efectos", "Esquinas, sombra y brillo por defecto"],
    ["logo", "Logo", "El logo de la empresa y los colores que salen de él"],
    ["portal", "Estilo del panel principal", "Estilo de fondo, tarjetas y modo, como en Admin V2"],
  ];
  const TYPE_DESC = {
    boton_principal: "Todos los botones de acción principal (Entrar, Cobrar, Enviar…)",
    boton_secundario: "Los botones de apoyo (Volver, Ajustes, Cerrar sesión…)",
    tarjeta: "Todas las tarjetas: indicadores, servicios, mesas, comandas",
    encabezado: "La franja de título de cada panel",
    campo: "Las cajas donde se escribe (usuario, clave, búsqueda)",
    chip: "Las etiquetas pequeñas (LIVE, estados, códigos)",
    barra_nav: "Los botones del menú y de navegación",
    barra_lateral: "La columna izquierda del panel principal",
  };
  const BG_STYLE_LABELS = { aurora_boreal: "Aurora boreal", neon_profundo: "Neón profundo", holografico: "Holográfico", cyber_grid: "Cuadrícula cyber",
    corporate_dark: "Corporativo oscuro", corporate_light: "Corporativo claro", classic_dashboard: "Tablero clásico", neutral_slate: "Pizarra neutra" };
  const CARD_STYLE_LABELS = { glass_premium: "Vidrio premium", neon_border: "Borde neón", soft_solid: "Sólido suave", dark_elevated: "Oscuro elevado",
    classic_panel: "Panel clásico", flat_dashboard: "Tablero plano", executive_glass: "Vidrio ejecutivo" };
  const MODE_LABELS = { dark: "Oscuro", light: "Claro", classic: "Clásico", corporate: "Corporativo" };
  const SIZES = [["phone", "Celular", 390, 780], ["tablet", "Tableta", 820, 1080], ["desktop", "Pantalla grande", 1280, 800]];
  const COLOR_LABELS = { primary: "Primario", secondary: "Secundario", background: "Fondo", surface: "Superficie", text: "Texto", text_muted: "Texto secundario", success: "Éxito", warning: "Alerta", danger: "Peligro" };
  const POSITIONS = [["center", "Centro"], ["top", "Arriba"], ["bottom", "Abajo"], ["left", "Izquierda"], ["right", "Derecha"], ["top left", "Arriba izquierda"], ["top right", "Arriba derecha"], ["bottom left", "Abajo izquierda"], ["bottom right", "Abajo derecha"]];
  const MODES = [["cover", "Pantalla completa"], ["watermark", "Marca de agua"], ["pattern", "Patrón repetido"]];
  const HEX = /^#[0-9a-f]{6}$/i;

  async function request(url, options = {}) {
    const isForm = options.body instanceof FormData;
    const response = await fetch(url, { credentials: "same-origin", ...options, headers: { Accept: "application/json", ...(isForm ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) {
      const d = data && data.detail;
      throw new Error((d && (typeof d === "string" ? d : d.message)) || `Respuesta ${response.status}`);
    }
    return data;
  }

  // =========================================================== lógica pura
  // Las piezas llevan punto en su clave (caja.cobrar): "pieces.caja.cobrar.fill"
  // es pieces → "caja.cobrar" → fill.
  function splitPath(path) {
    const parts = String(path).split(".");
    return parts[0] === "pieces" && parts.length >= 3 ? ["pieces", `${parts[1]}.${parts[2]}`, ...parts.slice(3)] : parts;
  }
  function getPath(obj, path) {
    return splitPath(path).reduce((o, k) => (o == null ? undefined : o[k]), obj);
  }
  function setPath(obj, path, value) {
    const keys = splitPath(path);
    let o = obj;
    keys.slice(0, -1).forEach((k) => { if (o[k] == null || typeof o[k] !== "object") o[k] = {}; o = o[k]; });
    if (value === undefined) delete o[keys[keys.length - 1]]; else o[keys[keys.length - 1]] = value;
    return obj;
  }

  // Selección: {kind: theme|background|component|piece, key}
  function selectFromPreview(target, screen) {
    if (target && target.piece) return { kind: "piece", key: target.piece };
    if (target && target.component) return { kind: "component", key: target.component };
    return { kind: "background", key: (target && target.background) || screen || "general" };
  }
  function stylePath(sel) {
    return sel.kind === "piece" ? `pieces.${sel.key}` : `components.${sel.key}`;
  }

  // Degradados: 2 o 3 paradas, ángulo y tipo lineal o radial.
  function defaultGradient(a = "#1a1a2e", b = "#e3122f") {
    return { type: "linear", angle: 135, stops: [{ color: a, at: 0 }, { color: b, at: 100 }] };
  }
  function editGradient(g, change) {
    const out = clone(g || defaultGradient());
    if (change.type) out.type = change.type === "radial" ? "radial" : "linear";
    if (change.angle !== undefined) out.angle = Math.max(0, Math.min(360, Math.round(Number(change.angle) || 0)));
    if (change.addStop && out.stops.length < 3) {
      const [a, b] = [out.stops[0], out.stops[out.stops.length - 1]];
      out.stops.splice(1, 0, { color: mix(a.color, b.color, 0.5), at: 50 });
    }
    if (change.removeStop !== undefined && out.stops.length > 2) out.stops.splice(change.removeStop, 1);
    if (change.stop) {
      const s = out.stops[change.stop.index];
      if (s) {
        if (change.stop.color !== undefined && HEX.test(change.stop.color)) s.color = change.stop.color.toLowerCase();
        if (change.stop.at !== undefined) s.at = Math.max(0, Math.min(100, Math.round(Number(change.stop.at) || 0)));
      }
    }
    out.stops.sort((x, y) => x.at - y.at);
    return out;
  }
  function gradientCss(g) {
    const stops = arr(g && g.stops).map((s) => `${s.color} ${s.at}%`).join(",");
    return g && g.type === "radial" ? `radial-gradient(circle at center,${stops})` : `linear-gradient(${(g && g.angle) || 0}deg,${stops})`;
  }
  function fillCss(f) {
    if (!f) return "transparent";
    return f.kind === "gradient" ? gradientCss(f.gradient) : f.color;
  }

  // Fondo por capas de una pantalla: base, imagen y velo; o heredar el general.
  function backgroundOf(tokens, screen) {
    return getPath(tokens, `backgrounds.${screen}`) || { inherit: true };
  }
  function setBackgroundLayer(tokens, screen, layer, value) {
    const out = clone(tokens);
    let bg = clone(backgroundOf(out, screen));
    if (bg.inherit || bg.own) bg = clone(out.backgrounds.general);
    delete bg.inherit;
    delete bg.own;
    if (layer === "base") bg.base = value;
    else if (layer === "image") bg.image = value;
    else if (layer === "veil") bg.veil = value;
    if (!bg.base) bg.base = { kind: "solid", color: out.theme.colors.background };
    out.backgrounds[screen] = { base: bg.base, image: bg.image || null, veil: bg.veil || null };
    return out;
  }
  // mode: "inherit" (el general), "own" (el fondo propio del panel) o "custom".
  function setBgMode(tokens, screen, mode) {
    const out = clone(tokens);
    if (screen === "general") return out;
    if (mode === "inherit") out.backgrounds[screen] = { inherit: true };
    else if (mode === "own") out.backgrounds[screen] = { own: true };
    else {
      const general = clone(out.backgrounds.general);
      out.backgrounds[screen] = { base: general.base && general.base.kind === "preset" ? { kind: "solid", color: out.theme.colors.background } : general.base,
        image: general.image || null, veil: general.veil || null };
    }
    return out;
  }
  function setInherit(tokens, screen, inherit) {
    const out = clone(tokens);
    if (screen === "general") return out;
    out.backgrounds[screen] = inherit ? { inherit: true } : clone({ ...out.backgrounds.general, inherit: undefined });
    delete out.backgrounds[screen].inherit;
    return out;
  }

  // Paleta desde el logo: se aplica con un clic y se puede deshacer. El
  // color de fondo propuesto también pasa a la base del fondo general (si no,
  // el texto nuevo quedaría sobre el fondo viejo).
  function applyPalette(tokens, colors) {
    const out = clone(tokens);
    const undo = { colors: clone(out.theme.colors), base: clone(out.backgrounds.general.base) };
    Object.keys(out.theme.colors).forEach((k) => { if (HEX.test(colors[k] || "")) out.theme.colors[k] = colors[k].toLowerCase(); });
    if (HEX.test(colors.background || "")) out.backgrounds.general.base = { kind: "solid", color: colors.background.toLowerCase() };
    return { tokens: out, undo };
  }
  function undoPalette(tokens, undo) {
    const out = clone(tokens);
    if (undo && undo.colors) out.theme.colors = clone(undo.colors);
    if (undo && undo.base) out.backgrounds.general.base = clone(undo.base);
    return out;
  }

  // Restablecer a lo heredado.
  function resetSelection(tokens, sel) {
    const out = clone(tokens);
    if (sel.kind === "piece") delete out.pieces[sel.key];
    else if (sel.kind === "component") delete out.components[sel.key];
    else if (sel.kind === "background" && sel.key !== "general") out.backgrounds[sel.key] = { inherit: true };
    return out;
  }

  // -------------------------------------------------------------- color
  function rgb(hex) { const v = String(hex || "#000000"); return [1, 3, 5].map((i) => parseInt(v.slice(i, i + 2), 16) || 0); }
  function toHex(parts) { return `#${parts.map((n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0")).join("")}`; }
  function mix(a, b, t) { const x = rgb(a); const y = rgb(b); return toHex(x.map((n, i) => n + (y[i] - n) * t)); }
  function luminance(hex) {
    const [r, g, b] = rgb(hex).map((n) => { const c = n / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  function contrast(a, b) { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); }
  function onColor(bg) { return contrast("#ffffff", bg) >= contrast("#111111", bg) ? "#ffffff" : "#111111"; }
  function readable(color, bg, min = 4.5) {
    const toward = luminance(bg) > 0.4 ? "#000000" : "#ffffff";
    let out = color;
    for (let step = 1; step <= 10 && contrast(out, bg) < min; step += 1) out = mix(color, toward, step / 10);
    return out;
  }
  function fillColors(f) {
    if (!f) return [];
    return f.kind === "gradient" ? arr(f.gradient && f.gradient.stops).map((s) => s.color) : [f.color];
  }

  // Guardia de lectura (AA 4.5:1). Avisa, no bloquea.
  function contrastIssues(tokens, registry) {
    const issues = [];
    const c = tokens.theme.colors;
    const bgColors = (bg) => {
      const base = bg.base && bg.base.kind === "preset" ? [c.background] : fillColors(bg.base);
      if (bg.image && bg.veil) return arr(bg.veil.gradient && bg.veil.gradient.stops).map((s) => mix(s.color, "#000000", (bg.veil.darken || 0) / 100));
      return base;
    };
    const check = (id, label, text, colors, fix) => {
      const worst = colors.length ? Math.min(...colors.map((x) => contrast(text, x))) : 21;
      if (worst < 4.5) issues.push({ id, label, ratio: Math.round(worst * 10) / 10, fix });
    };
    Object.keys(tokens.backgrounds || {}).forEach((screen) => {
      const bg = tokens.backgrounds[screen];
      if (!bg || bg.inherit || bg.own) return;
      const where = screen === "general" ? "el fondo general" : `el fondo de ${screen}`;
      check(`text-${screen}`, `Texto sobre ${where}`, c.text, bgColors(bg), { kind: "text", screen });
      check(`muted-${screen}`, `Texto secundario sobre ${where}`, c.text_muted, bgColors(bg), { kind: "muted", screen });
    });
    const styles = [...Object.entries(tokens.components || {}).map(([k, v]) => ["component", k, v]), ...Object.entries(tokens.pieces || {}).map(([k, v]) => ["piece", k, v])];
    styles.forEach(([kind, key, st]) => {
      if (!st || !st.fill) return;
      const text = (st.text && st.text.color) || onColor(fillColors(st.fill)[0] || c.background);
      const label = kind === "piece" ? pieceLabel(registry, key) : typeLabel(registry, key);
      check(`${kind}-${key}`, `Texto de «${label}»`, text, fillColors(st.fill), { kind: "style", path: `${kind === "piece" ? "pieces" : "components"}.${key}` });
    });
    return issues;
  }
  function applyFix(tokens, issue) {
    const out = clone(tokens);
    const f = issue.fix;
    if (f.kind === "text" || f.kind === "muted") {
      const bg = f.screen === "general" ? out.backgrounds.general : out.backgrounds[f.screen];
      if (bg && bg.image && bg.veil) {
        bg.veil.darken = Math.max(bg.veil.darken || 0, 55);
        bg.veil.opacity = Math.max(bg.veil.opacity || 0, 85);
        if (contrastIssues(out).some((i) => i.id === issue.id)) out.theme.colors[f.kind === "text" ? "text" : "text_muted"] = onColor(fillColors(bg.veil.gradient ? { kind: "gradient", gradient: bg.veil.gradient } : bg.base)[0]);
        return out;
      }
      const base = (bg.base && bg.base.kind !== "preset" && fillColors(bg.base)[0]) || out.theme.colors.background;
      if (f.kind === "text") out.theme.colors.text = readable(out.theme.colors.text, base);
      else out.theme.colors.text_muted = readable(out.theme.colors.text_muted, base);
      if (contrastIssues(out).some((i) => i.id === issue.id)) out.theme.colors[f.kind === "text" ? "text" : "text_muted"] = onColor(base);
      return out;
    }
    const st = getPath(out, f.path);
    const colors = fillColors(st.fill);
    const best = ["#ffffff", "#111111"].sort((a, b) => Math.min(...colors.map((x) => contrast(b, x))) - Math.min(...colors.map((x) => contrast(a, x))))[0];
    st.text = { ...(st.text || {}), color: best };
    return out;
  }

  // Pantallas que tiene ESTA empresa (las calcula el servidor), por familia.
  function screensFor(data) {
    const reg = (data && data.registry) || { screens: {}, families: {} };
    const available = data && data.available && Array.isArray(data.available.screens) ? data.available.screens : Object.keys(reg.screens || {});
    return available.filter((k) => reg.screens && reg.screens[k])
      .map((k) => ({ key: k, label: TAB_LABELS[k] || reg.screens[k].label, family: reg.screens[k].family }))
      .sort((a, b) => (FAMILY_ORDER.indexOf(a.family) - FAMILY_ORDER.indexOf(b.family)) || (TAB_ORDER.indexOf(a.key) - TAB_ORDER.indexOf(b.key)));
  }
  function piecesFor(reg, screen) {
    const all = arr(reg && reg.pieces);
    if (screen === "portal_modulo") return all.filter((p) => MODULE_VIEW_PIECES.has(p.key));
    return all.filter((p) => p.screen === screen);
  }
  function familyLabel(data, family) {
    const f = data && data.registry && data.registry.families && data.registry.families[family];
    return (f && f.label) || family;
  }

  const typeLabel = (reg, key) => ((reg && reg.types && reg.types[key]) || {}).label || key;
  const pieceLabel = (reg, key) => (arr(reg && reg.pieces).find((p) => p.key === key) || {}).label || key;

  // ============================================================ estado
  const model = {
    companyId: "", company: null, data: null, tokens: null, savedJson: "", sel: { kind: "theme", key: "colors" },
    screen: "portal_dashboard", size: "desktop", guardOpen: false, stateView: "normal", lite: false, undo: null, modal: null, notice: "", error: "",
    busy: false, templates: null, pickerQuery: "", frameReady: false, previewError: "", share: null,
  };
  let ctx = null;
  let bound = false;
  let timer = null;
  const registry = () => (model.data && model.data.registry) || { screens: {}, types: {}, pieces: [] };
  const dirty = () => model.tokens && JSON.stringify(model.tokens) !== model.savedJson;
  const frame = () => (ctx && ctx.root() && ctx.root().querySelector ? ctx.root().querySelector("[data-vpb-frame]") : null);

  function postFrame(message) {
    const f = frame();
    if (f && f.contentWindow && model.frameReady) f.contentWindow.postMessage(message, window.location.origin);
  }
  function selectionTarget() {
    if (model.sel.kind === "piece") return { piece: model.sel.key };
    if (model.sel.kind === "component") return { component: model.sel.key };
    return null;
  }
  function pushPreview() {
    clearTimeout(timer);
    timer = setTimeout(() => postFrame({ type: "tokens", tokens: model.tokens }), 120);
  }
  function syncPreviewState() {
    postFrame({ type: "highlight", target: selectionTarget() });
    postFrame({ type: "state", target: selectionTarget(), state: model.stateView });
    postFrame({ type: "lite", on: model.lite });
  }

  // ============================================================ vistas
  function head() {
    const c = model.company;
    return `<header class="vp-head vp-brand-head"><div><p class="vp-eyebrow">NÚCLEO CLONEXA · ESTUDIO DE MARCA</p><h1 class="vp-title">Estudio de marca</h1>
      ${c ? `<p class="vp-login-hint">Empresa: <b>${h(c.name)}</b> · ${model.data && model.data.published ? `publicada la versión ${h(model.data.published.version)}` : "sin marca publicada (se ve como siempre)"}${dirty() ? ' · <b class="vp-no">cambios sin guardar</b>' : ""}</p>` : ""}</div></header>
      ${c ? `<div class="vp-brand-actions">
        <div class="vp-brand-actions-left">
          <button class="vp-btn" type="button" data-vpb-change-company>Cambiar empresa</button>
          <details class="vp-brand-more"><summary class="vp-btn">Más ▾</summary>
            <div class="vp-panel vp-brand-menu" role="menu">
              <button class="vp-btn" type="button" role="menuitem" data-vpb-open="templates">Plantillas</button>
              <button class="vp-btn" type="button" role="menuitem" data-vpb-open="copy">Copiar de otra empresa</button>
              <button class="vp-btn" type="button" role="menuitem" data-vpb-open="history">Historial</button>
            </div></details>
        </div>
        <div class="vp-brand-actions-right">
          <button class="vp-btn" type="button" data-vpb-open="share">Compartir vista previa</button>
          <button class="vp-btn" type="button" data-vpb-save ${model.busy ? "disabled" : ""}>Guardar borrador</button>
          <button class="vp-btn vp-btn-primary" type="button" data-vpb-open="publish" ${model.busy ? "disabled" : ""}>Publicar</button>
        </div></div>` : ""}
      ${model.notice ? `<p class="vp-ok-text" role="status">${h(model.notice)}</p>` : ""}${model.error ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}`;
  }

  function pickerView() {
    const ov = ctx && ctx.overview ? ctx.overview() : null;
    const list = arr(ov && ov.companies).filter((c) => !["archived", "deleted"].includes(String(c.status || "").toLowerCase()))
      .filter((c) => !model.pickerQuery || fold(`${c.name} ${c.slug}`).includes(fold(model.pickerQuery)));
    return `<section class="vp-panel vp-section"><h2>Elige la empresa</h2>
      <input class="vp-search" type="search" placeholder="Buscar empresa" value="${h(model.pickerQuery)}" data-vpb-pick-search aria-label="Buscar empresa">
      <div class="vp-card-grid vp-zone-scroll">${list.map((c) => `<button class="vp-panel-card vp-brand-pick" type="button" data-vpb-pick="${h(c.id)}"><b>${h(c.name)}</b><small>${h(c.kind === "demo" ? "Demo" : "Registrada")}</small></button>`).join("")
        || `<div class="vp-empty">${ov ? "Ninguna empresa coincide." : "Cargando empresas…"}</div>`}</div></section>`;
  }

  function treeView() {
    const reg = registry();
    const has = (path) => getPath(model.tokens, path) !== undefined;
    const item = (kind, key, label, desc, custom = false) => `<li><button type="button" class="vp-brand-node ${model.sel.kind === kind && model.sel.key === key ? "is-active" : ""}" data-vpb-sel="${kind}|${h(key)}">
      <b>${h(label)}${custom ? ' <span class="vp-brand-dot" title="Personalizado"></span>' : ""}</b><small>${h(desc)}</small></button></li>`;
    const screens = screensFor(model.data);
    const current = screens.find((x) => x.key === model.screen) || screens[0] || { key: model.screen, label: model.screen, family: "portal" };
    const bg = model.tokens.backgrounds[current.key] || { inherit: true };
    const bgDesc = bg.inherit ? "Usa el fondo general" : bg.own ? "Conserva su fondo de siempre" : "Fondo propio de esta pantalla";
    const pieceDesc = (p) => (p.screen === "portal_dashboard" ? "Solo esta pieza, en el panel principal y sus vistas" : `Solo esta pieza, en ${current.label}`);
    const general = THEME_ITEMS.filter(([k]) => k !== "portal" || screens.some((x) => x.family === "portal"));
    return `<nav class="vp-panel vp-brand-tree" aria-label="Qué editar">
      <section class="vp-brand-block"><h3>Marca general</h3><p class="vp-brand-note">Aplica a todas las pantallas.</p>
        <ul>${general.map(([k, l, d]) => item("theme", k, l, d)).join("")}
        ${screens.some((x) => x.family !== "portal") ? item("theme", "scope", "Alcance de la marca", "Si la marca llega a los paneles de restaurante y mini paneles") : ""}</ul></section>
      <section class="vp-brand-block"><h3>Esta pantalla · ${h(current.label)}</h3><p class="vp-brand-note">Solo cambia ${h(current.label)}; cambia con la pestaña de arriba.</p>
        <ul>${item("background", current.key, "Fondo de esta pantalla", bgDesc, !bg.inherit)}
        ${piecesFor(reg, current.key).map((p) => item("piece", p.key, p.label, pieceDesc(p), has(`pieces.${p.key}`))).join("")}</ul></section>
      <section class="vp-brand-block"><h3>Tipos de pieza</h3><p class="vp-brand-note">Aplica a todos los de ese tipo, en todas las pantallas.</p>
        <ul>${Object.entries(reg.types).map(([k, t]) => item("component", k, t.label, TYPE_DESC[k] || "Todos los de este tipo", has(`components.${k}`))).join("")}</ul></section>
    </nav>`;
  }

  function stageTop() {
    const screens = screensFor(model.data);
    const groups = FAMILY_ORDER.map((f) => screens.filter((x) => x.family === f)).filter((g) => g.length);
    const issues = contrastIssues(model.tokens, registry());
    const chip = issues.length ? `<button class="vp-chip vp-brand-guard-chip" type="button" aria-expanded="${model.guardOpen}" data-vpb-guard>⚠ ${issues.length} aviso${issues.length === 1 ? "" : "s"} de lectura</button>` : "";
    const guard = issues.length && model.guardOpen ? `<div class="vp-brand-guard is-open"><ul>${issues.slice(0, 8).map((i) => `<li><span>${h(i.label)} · contraste ${h(String(i.ratio).replace(".", ","))}:1 (mínimo 4,5)</span><button class="vp-btn vp-btn-sm" type="button" data-vpb-fix="${h(i.id)}">Corregir</button></li>`).join("")}</ul></div>` : "";
    return `<div class="vp-brand-tabs" role="tablist" aria-label="Pantalla">${groups.map((g) => g.map((x) => `<button class="vp-brand-tab ${model.screen === x.key ? "is-active" : ""}" type="button" role="tab" aria-selected="${model.screen === x.key}" data-vpb-screen="${h(x.key)}">${h(x.label)}</button>`).join("")).join('<span class="vp-brand-tab-sep" aria-hidden="true"></span>')}</div>
      <div class="vp-toolbar vp-brand-stage-bar"><p class="vp-brand-tip">Toca cualquier parte del panel para editarla.</p>
        <div class="vp-chips" aria-label="Tamaño">${SIZES.map(([k, l]) => `<button class="vp-chip ${model.size === k ? "is-active" : ""}" type="button" data-vpb-size="${k}">${l}</button>`).join("")}
        <button class="vp-chip ${model.lite ? "is-active" : ""}" type="button" data-vpb-lite title="Así se ve en equipos lentos">Modo liviano</button>${chip}</div></div>
      ${guard}
      ${model.previewError ? `<div class="vp-alert" role="alert"><span>${h(model.previewError)}</span></div>` : ""}`;
  }

  function stageView() {
    const current = screensFor(model.data).find((x) => x.key === model.screen) || { label: model.screen };
    return `<section class="vp-panel vp-brand-stage" aria-label="Vista previa">
      <div data-vpb-stage-top>${stageTop()}</div>
      <div class="vp-brand-frame-wrap" data-vpb-wrap><iframe class="vp-brand-frame" data-vpb-frame title="Vista previa: ${h(current.label)}" src="/admin-v2/brand-preview/${encodeURIComponent(model.companyId)}?screen=${encodeURIComponent(model.screen)}"></iframe></div>
      <p class="vp-login-hint">Datos de muestra fijos, nunca los de la empresa.</p></section>`;
  }

  // ------------------------------------------------------------ controles
  function colorField(path, label) {
    const v = getPath(model.tokens, path) || "#000000";
    return `<label class="vp-field vp-brand-color">${h(label)}<span class="vp-inline"><input type="color" value="${h(v)}" data-vpb-path="${h(path)}" data-vpb-kind="color" aria-label="${h(label)}">
      <input class="vp-mono" value="${h(v)}" maxlength="7" data-vpb-path="${h(path)}" data-vpb-kind="hex" aria-label="${h(label)} en hex"></span></label>`;
  }
  function slider(path, label, min, max, step = 1, unit = "", fallback = 0) {
    const v = getPath(model.tokens, path);
    const value = v === undefined ? fallback : v;
    return `<label class="vp-field">${h(label)} <output data-vpb-out="${h(path)}">${h(value)}${h(unit)}</output>
      <input type="range" min="${min}" max="${max}" step="${step}" value="${h(value)}" data-vpb-path="${h(path)}" data-vpb-kind="number" data-vpb-unit="${h(unit)}"></label>`;
  }
  function selectField(path, label, options, fallback) {
    const v = getPath(model.tokens, path) ?? fallback;
    return `<label class="vp-field">${h(label)}<select data-vpb-path="${h(path)}" data-vpb-kind="select">${options.map(([k, l]) => `<option value="${h(k)}" ${String(v) === String(k) ? "selected" : ""}>${h(l)}</option>`).join("")}</select></label>`;
  }
  function gradientEditor(path, label) {
    const g = getPath(model.tokens, path) || defaultGradient();
    return `<fieldset class="vp-brand-group"><legend>${h(label)}</legend>
      <div class="vp-brand-swatch" data-vpb-swatch="${h(gradientCss(g))}"></div>
      <div class="vp-form-grid">${selectField(`${path}.type`, "Tipo", [["linear", "Lineal"], ["radial", "Radial"]], "linear")}
      ${g.type === "radial" ? "" : slider(`${path}.angle`, "Ángulo", 0, 360, 1, "°", 135)}</div>
      ${g.stops.map((s, i) => `<div class="vp-brand-stop">${colorField(`${path}.stops.${i}.color`, `Color ${i + 1}`)}${slider(`${path}.stops.${i}.at`, "Posición", 0, 100, 1, "%", s.at)}
        ${g.stops.length > 2 ? `<button class="vp-btn vp-btn-sm" type="button" data-vpb-grad="${h(path)}|remove|${i}">Quitar</button>` : ""}</div>`).join("")}
      ${g.stops.length < 3 ? `<button class="vp-btn vp-btn-sm" type="button" data-vpb-grad="${h(path)}|add">+ Tercer color</button>` : ""}</fieldset>`;
  }
  function fillEditor(path, label, allowNone = true, allowPreset = false) {
    const f = getPath(model.tokens, path);
    const kind = f ? f.kind : "none";
    const opts = [...(allowNone ? [["none", "Heredado"]] : []), ...(allowPreset ? [["preset", "Estilo del panel principal"]] : []), ["solid", "Color liso"], ["gradient", "Degradado"]];
    return `<fieldset class="vp-brand-group"><legend>${h(label)}</legend>
      <div class="vp-chips">${opts.map(([k, l]) => `<button class="vp-chip ${kind === k ? "is-active" : ""}" type="button" data-vpb-fill="${h(path)}|${k}">${l}</button>`).join("")}</div>
      ${kind === "solid" ? colorField(`${path}.color`, "Color") : kind === "gradient" ? gradientEditor(`${path}.gradient`, "Degradado") : ""}</fieldset>`;
  }

  function imagePicker(path) {
    const images = arr(model.data && model.data.images);
    const current = getPath(model.tokens, path);
    const st = (model.data && model.data.storage) || {};
    return `<div class="vp-brand-images">${images.map((im) => `<button type="button" class="vp-brand-thumb ${current === im.id ? "is-active" : ""}" data-vpb-img="${h(path)}|${h(im.id)}" aria-label="Usar imagen ${h(im.width)}×${h(im.height)}"><img src="${h(im.url.replace(".webp", "-lite.webp"))}" alt="" loading="lazy"></button>`).join("")}</div>
      ${st.configured === false ? `<p class="vp-no">El almacenamiento de imágenes no está configurado: no se pueden subir imágenes.</p>` : `<label class="vp-field">Subir imagen (PNG, JPG o WebP, hasta 5 MB)<input type="file" accept="image/png,image/jpeg,image/webp" data-vpb-upload="${h(path)}"></label>
      <p class="vp-login-hint">Espacio usado: ${h(Math.round((st.used_bytes || 0) / 1024))} KB de ${h(Math.round((st.quota_bytes || 0) / 1048576))} MB.</p>`}`;
  }

  function bgLayers(screen, bg) {
    const p = `backgrounds.${screen}`;
    return `${fillEditor(`${p}.base`, "Capa 1 · Base", false, true)}
      <fieldset class="vp-brand-group"><legend>Capa 2 · Imagen</legend>
        ${bg.image ? `<div class="vp-form-grid">${selectField(`${p}.image.mode`, "Modo", MODES, "cover")}${bg.image.mode !== "cover" ? slider(`${p}.image.size`, "Tamaño", 5, 100, 1, "%", 40) : ""}
          ${bg.image.mode === "watermark" ? selectField(`${p}.image.position`, "Posición", POSITIONS, "center") : ""}${slider(`${p}.image.opacity`, "Opacidad", 0, 100, 1, "%", 100)}</div>
          <button class="vp-btn vp-btn-sm" type="button" data-vpb-layer="${h(screen)}|image|off">Quitar imagen</button>` : `<p class="vp-login-hint">Sin imagen. Elige una o súbela.</p>`}
        ${imagePicker(`${p}.image.id`)}</fieldset>
      <fieldset class="vp-brand-group"><legend>Capa 3 · Velo</legend>
        ${bg.veil ? `${gradientEditor(`${p}.veil.gradient`, "Degradado del velo")}<div class="vp-form-grid">${slider(`${p}.veil.darken`, "Oscurecido", 0, 90, 1, "%", 0)}${slider(`${p}.veil.blur`, "Desenfoque", 0, 20, 1, " px", 0)}${slider(`${p}.veil.opacity`, "Transparencia", 0, 100, 1, "%", 60)}</div>
          <button class="vp-btn vp-btn-sm" type="button" data-vpb-layer="${h(screen)}|veil|off">Quitar velo</button>`
          : `<button class="vp-btn vp-btn-sm" type="button" data-vpb-layer="${h(screen)}|veil|on">+ Agregar velo</button>`}</fieldset>`;
  }

  function backgroundEditor(screen) {
    const spec = model.data && model.data.registry && model.data.registry.screens[screen];
    const label = TAB_LABELS[screen] || (spec ? spec.label : screen);
    const bg = model.tokens.backgrounds[screen] || { inherit: true };
    const inherit = Boolean(bg.inherit);
    const keepsOwn = spec && (spec.family !== "portal" || spec.page === "login");
    const ownLabel = spec && spec.page === "login" ? "El de siempre de Clonexa (como hoy)" : "Su fondo de siempre (como hoy)";
    let body;
    if (inherit) {
      body = `<p class="vp-login-hint">Estás editando el <b>fondo general</b>: cambia en todas las pantallas que lo usan.</p>${bgLayers("general", model.tokens.backgrounds.general)}`;
    } else {
      const choice = keepsOwn ? `<div class="vp-chips" role="radiogroup" aria-label="Fondo propio">${[["own", ownLabel], ["custom", "Personalizado"]].map(([k, l]) => `<button class="vp-chip ${(bg.own ? "own" : "custom") === k ? "is-active" : ""}" type="button" role="radio" aria-checked="${(bg.own ? "own" : "custom") === k}" data-vpb-bgmode="${h(screen)}|${k}">${l}</button>`).join("")}</div>` : "";
      body = `${choice}${bg.own ? "" : bgLayers(screen, bg)}`;
    }
    return `<h2>Fondo de esta pantalla · ${h(label)}</h2>
      <label class="vp-check vp-brand-switch"><input type="checkbox" role="switch" data-vpb-usegeneral="${h(screen)}" ${inherit ? "checked" : ""}> Usar el fondo general</label>${body}`;
  }

  function styleEditor() {
    const sel = model.sel;
    const base = stylePath(sel);
    const reg = registry();
    const label = sel.kind === "piece" ? pieceLabel(reg, sel.key) : typeLabel(reg, sel.key);
    const st = model.stateView === "normal" ? base : `${base}.${model.stateView}`;
    const props = model.stateView === "normal";
    return `<h2>${h(label)}</h2><p class="vp-login-hint">${sel.kind === "piece" ? `Pieza <span class="vp-mono">${h(sel.key)}</span>. Lo que no cambies hereda del componente.` : "Aplica a todos los elementos de este tipo en las cuatro pantallas."}</p>
      <div class="vp-chips" role="tablist" aria-label="Estado">${[["normal", "Normal"], ["hover", "Cursor encima"], ["active", "Presionado"]].map(([k, l]) => `<button class="vp-chip ${model.stateView === k ? "is-active" : ""}" type="button" data-vpb-state="${k}">${l}</button>`).join("")}</div>
      ${fillEditor(`${st}.fill`, "Relleno")}
      <fieldset class="vp-brand-group"><legend>Borde</legend><div class="vp-form-grid">${slider(`${st}.border.width`, "Grosor", 0, 6, 1, " px", 0)}${colorField(`${st}.border.color`, "Color del borde")}</div></fieldset>
      <fieldset class="vp-brand-group"><legend>Efectos</legend><div class="vp-form-grid">${slider(`${st}.glow`, "Brillo", 0, 100, 1, "", 0)}${slider(`${st}.shadow`, "Sombra", 0, 100, 1, "", 0)}${props ? slider(`${base}.radius`, "Radio", 0, 40, 1, " px", model.tokens.theme.radius) : ""}</div></fieldset>
      <fieldset class="vp-brand-group"><legend>Texto</legend><div class="vp-form-grid">${colorField(`${st}.text.color`, "Color del texto")}${selectField(`${st}.text.weight`, "Peso", [400, 500, 600, 700, 800, 900].map((n) => [n, String(n)]), 600)}${slider(`${st}.text.size`, "Tamaño", 10, 32, 1, " px", 15)}</div></fieldset>
      <button class="vp-btn vp-btn-sm" type="button" data-vpb-reset>Restablecer a lo heredado</button>`;
  }

  function themeEditor() {
    const key = model.sel.key;
    if (key === "font") {
      const fonts = arr(model.data && model.data.fonts);
      const fam = model.tokens.theme.font.family;
      return `<h2>Tipografía</h2>${selectField("theme.font.family", "Familia", fonts.map((f) => [f, f]), "Inter")}
        <p class="vp-brand-sample" data-vpb-font="${h(fam)}">Mesa 7 · Confirmar y enviar · $ 45.000</p>
        ${slider("theme.font.size", "Tamaño base", 12, 22, 1, " px", 15)}${selectField("theme.font.heading_weight", "Peso de títulos", [400, 500, 600, 700, 800, 900].map((n) => [n, String(n)]), 700)}`;
    }
    if (key === "portal") {
      const o = (model.data && model.data.portal_options) || {};
      const opts = (list, labels) => arr(list).map((k) => [k, labels[k] || k]);
      return `<h2>Estilo del panel principal</h2><p class="vp-login-hint">Los mismos estilos de Admin V2: el borrador inicial los trae tal como la empresa los ve hoy.</p>
        ${selectField("theme.portal.background_style", "Estilo de fondo", opts(o.background_styles, BG_STYLE_LABELS), "aurora_boreal")}
        ${selectField("theme.portal.card_style", "Estilo de tarjetas", opts(o.card_styles, CARD_STYLE_LABELS), "glass_premium")}
        ${selectField("theme.portal.theme_mode", "Modo", opts(o.theme_modes, MODE_LABELS), "dark")}
        <fieldset class="vp-brand-group"><legend>Colores del degradado</legend>${colorField("theme.portal.gradient_from", "Desde")}${colorField("theme.portal.gradient_to", "Hasta")}${colorField("theme.portal.gradient_extra", "Acento")}</fieldset>`;
    }
    if (key === "scope") {
      const on = model.tokens.theme.panels === true;
      return `<h2>Alcance de la marca</h2><p class="vp-login-hint">El panel principal siempre recibe la marca publicada. Los paneles de restaurante y los mini paneles solo si lo activas aquí; si no, se ven como hoy.</p>
        <label class="vp-check"><input type="checkbox" data-vpb-panels ${on ? "checked" : ""}> Aplicar la marca a los paneles de restaurante y mini paneles</label>`;
    }
    if (key === "shape") return `<h2>Forma y efectos</h2>${slider("theme.radius", "Radio", 0, 32, 1, " px", 14)}${slider("theme.shadow", "Sombra", 0, 100, 1, "", 30)}${slider("theme.glow", "Intensidad de brillo", 0, 100, 1, "", 0)}`;
    if (key === "logo") {
      return `<h2>Logo</h2>${imagePicker("theme.logo")}${model.tokens.theme.logo ? `<button class="vp-btn vp-btn-sm" type="button" data-vpb-logo-off>Quitar logo</button>` : ""}
        <fieldset class="vp-brand-group"><legend>Colores desde el logo</legend><p class="vp-login-hint">Analiza el logo y propone la paleta completa.</p>
        <button class="vp-btn vp-btn-primary" type="button" data-vpb-palette ${model.tokens.theme.logo ? "" : "disabled"}>Proponer colores</button>
        ${model.undo ? `<button class="vp-btn" type="button" data-vpb-undo>Deshacer colores</button>` : ""}</fieldset>`;
    }
    return `<h2>Colores</h2>${Object.keys(COLOR_LABELS).map((k) => colorField(`theme.colors.${k}`, COLOR_LABELS[k])).join("")}
      ${model.undo ? `<button class="vp-btn" type="button" data-vpb-undo>Deshacer colores del logo</button>` : ""}`;
  }

  function controlsView() {
    const sel = model.sel;
    const body = sel.kind === "theme" ? themeEditor() : sel.kind === "background" ? backgroundEditor(sel.key) : styleEditor();
    return `<aside class="vp-panel vp-brand-controls" aria-label="Controles">${body}</aside>`;
  }

  function modalView() {
    const md = model.modal;
    if (!md) return "";
    const err = md.error ? `<div class="vp-alert" role="alert"><span>${h(md.error)}</span></div>` : "";
    const headHtml = `<div class="vp-modal-head"><h2>${h(md.title)}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpb-close aria-label="Cerrar">✕</button></div>`;
    let body = "";
    if (md.type === "templates") {
      body = `<p class="vp-login-hint">Aplicar una plantilla reemplaza el borrador (el logo se conserva).</p><div class="vp-card-grid">${arr(model.templates).map((t) => `<button class="vp-panel-card vp-brand-tpl" type="button" data-vpb-tpl="${h(t.key)}"><b>${h(t.label)}</b><span class="vp-brand-swatch" data-vpb-swatch="${h(fillCss(t.tokens.backgrounds.general.base))}"></span></button>`).join("") || `<p class="vp-loading">Cargando…</p>`}</div>`;
    } else if (md.type === "copy") {
      const ov = ctx && ctx.overview ? ctx.overview() : null;
      const list = arr(ov && ov.companies).filter((c) => c.id !== model.companyId && !["archived", "deleted"].includes(String(c.status || "").toLowerCase()));
      body = `<p class="vp-login-hint">Copia solo los colores, fondos y estilos al borrador de <b>${h(model.company.name)}</b>. Nunca las imágenes de la otra empresa.</p>
        <label class="vp-field">Empresa de origen<select data-vpb-copy-source><option value="">Elige…</option>${list.map((c) => `<option value="${h(c.id)}">${h(c.name)}</option>`).join("")}</select></label>`;
    } else if (md.type === "history") {
      body = `<ul class="vp-actions-list vp-zone-scroll">${arr(model.data.history).map((v) => `<li class="vp-action"><b>Versión ${h(v.version)} · ${h({ draft: "Borrador", published: "Publicada", archived: "Anterior" }[v.status] || v.status)}</b>
        <small>${h(v.published_at ? `Publicada ${window.CxConsolePlus ? window.CxConsolePlus.since(v.published_at) : v.published_at}` : `Creada ${window.CxConsolePlus ? window.CxConsolePlus.since(v.created_at) : v.created_at}`)}</small>
        ${v.status === "archived" ? `<button class="vp-btn vp-btn-sm" type="button" data-vpb-rollback="${h(v.version)}">Volver a esta versión</button>` : ""}</li>`).join("")}</ul>
        ${model.data.published ? `<button class="vp-btn vp-btn-sm vp-btn-danger" type="button" data-vpb-unpublish>Quitar la marca publicada (volver a la de siempre)</button>` : ""}`;
    } else if (md.type === "share") {
      body = shareBody();
    } else {
      body = `<p class="vp-login-hint">${h(md.message)}</p>`;
    }
    const go = md.go ? `<div class="vp-actions"><button class="vp-btn ${md.danger ? "vp-btn-danger" : "vp-btn-primary"}" type="button" data-vpb-go ${md.busy ? "disabled" : ""}>${h(md.cta || "Confirmar")}</button><button class="vp-btn" type="button" data-vpb-close>Cancelar</button></div>` : "";
    return `<div class="vp-modal" data-vpb-modal><div class="vp-panel vp-modal-card" role="dialog" aria-modal="true">${headHtml}${body}${err}${go}</div></div>`;
  }

  function shareBody() {
    const s = model.share;
    if (!s) return `<p class="vp-loading">Cargando…</p>`;
    return `<p class="vp-login-hint">El cliente ve sus pantallas con el borrador guardado y datos de muestra. Solo lectura: no muestra datos reales ni deja entrar al panel. Vence a los 7 días.</p>
      <button class="vp-btn vp-btn-primary" type="button" data-vpb-share-new>Crear enlace nuevo</button>
      ${s.created ? `<label class="vp-field">Enlace (cópialo ahora; no se vuelve a mostrar)<span class="vp-inline"><input readonly value="${h(s.created)}" data-vpb-share-value><button class="vp-btn vp-btn-sm" type="button" data-vpb-share-copy>Copiar</button></span></label>` : ""}
      <ul class="vp-actions-list">${arr(s.links).map((l) => `<li class="vp-action"><b>Enlace ${h(l.id.slice(0, 8))}</b><small>${h(l.revoked_at ? "Revocado" : l.expired ? "Vencido" : `Vence ${window.CxConsolePlus ? window.CxConsolePlus.since(l.expires_at) : l.expires_at}`)}</small>
        ${!l.revoked_at && !l.expired ? `<button class="vp-btn vp-btn-sm vp-btn-danger" type="button" data-vpb-share-revoke="${h(l.id)}">Revocar</button>` : ""}</li>`).join("") || `<li class="vp-empty">Sin enlaces.</li>`}</ul>`;
  }

  function draw(full = true) {
    if (!ctx || !ctx.active() || !ctx.root()) return;
    const root = ctx.root();
    if (!model.companyId) { root.innerHTML = head() + pickerView() + modalView(); return; }
    if (!model.tokens) { root.innerHTML = head() + `<p class="vp-loading">Cargando la marca…</p>`; return; }
    const layout = root.querySelector ? root.querySelector("[data-vpb-layout]") : null;
    if (full || !layout) {
      model.frameReady = false;
      root.innerHTML = `<div data-vpb-head>${head()}</div><div class="vp-brand-layout" data-vpb-layout><div data-vpb-tree>${treeView()}</div><div data-vpb-stage>${stageView()}</div><div data-vpb-controls>${controlsView()}</div></div><div data-vpb-modal-host>${modalView()}</div>`;
    } else {
      root.querySelector("[data-vpb-head]").innerHTML = head();
      root.querySelector("[data-vpb-tree]").innerHTML = treeView();
      root.querySelector("[data-vpb-controls]").innerHTML = controlsView();
      root.querySelector("[data-vpb-modal-host]").innerHTML = modalView();
      const top = root.querySelector("[data-vpb-stage-top]");
      if (top) top.innerHTML = stageTop();
    }
    cssom(root);
  }

  // Tamaños, muestras de color y fuentes: por CSSOM (la CSP no permite estilos en línea).
  function cssom(root) {
    if (!root.querySelectorAll) return;
    root.querySelectorAll("[data-vpb-swatch]").forEach((el) => { el.style.background = el.getAttribute("data-vpb-swatch"); });
    root.querySelectorAll("[data-vpb-font]").forEach((el) => { const f = el.getAttribute("data-vpb-font"); el.style.fontFamily = f === "Sistema" ? "system-ui,sans-serif" : `'${f}',system-ui,sans-serif`; loadFont(f); });
    const wrap = root.querySelector("[data-vpb-wrap]");
    const f = root.querySelector("[data-vpb-frame]");
    if (wrap && f) {
      const [, , w, hgt] = SIZES.find(([k]) => k === model.size);
      const avail = Math.max(260, wrap.clientWidth || 600);
      const scale = Math.min(1, avail / w);
      f.style.width = `${w}px`;
      f.style.height = `${hgt}px`;
      f.style.transform = `scale(${scale})`;
      f.style.transformOrigin = "top center";
      f.style.flex = "none";
      wrap.style.height = `${Math.round(hgt * scale)}px`;
    }
  }
  const loadedFonts = new Set();
  function loadFont(family) {
    if (!family || family === "Sistema" || family === "Inter" || loadedFonts.has(family) || !document.head) return;
    loadedFonts.add(family);
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(family).replace(/%20/g, "+")}:wght@400;600;700;800&display=swap`;
    document.head.appendChild(link);
  }

  // ============================================================ datos
  async function loadCompany(id) {
    model.companyId = id;
    model.screen = "portal_dashboard";
    model.size = defaultSize("portal_dashboard");
    model.sel = { kind: "theme", key: "colors" };
    model.tokens = null;
    model.undo = null;
    model.error = "";
    draw();
    try {
      const data = await request(`${API}/${encodeURIComponent(id)}`);
      model.data = data;
      model.company = data.company;
      model.tokens = clone(data.draft.tokens);
      model.savedJson = JSON.stringify(model.tokens);
    } catch (error) {
      model.error = error.message;
    }
    draw();
  }
  async function reload() {
    const data = await request(`${API}/${encodeURIComponent(model.companyId)}`);
    model.data = data;
    model.tokens = clone(data.draft.tokens);
    model.savedJson = JSON.stringify(model.tokens);
  }
  async function saveDraft() {
    const out = await request(`${API}/${encodeURIComponent(model.companyId)}/draft`, { method: "PUT", body: JSON.stringify({ tokens: model.tokens }) });
    model.tokens = clone(out.tokens);
    model.savedJson = JSON.stringify(model.tokens);
    return out;
  }
  async function act(run, notice, full = false) {
    model.busy = true;
    model.error = "";
    draw(false);
    try { await run(); model.notice = notice; model.modal = null; }
    catch (error) { if (model.modal) model.modal.error = error.message; else model.error = error.message; }
    finally { model.busy = false; draw(full); }
  }

  function change(next, redraw = false) {
    model.tokens = next;
    model.notice = "";
    pushPreview();
    draw(!!redraw && redraw === "full");
  }

  // ============================================================ eventos
  function onMessage(event) {
    const f = frame();
    if (!f || event.source !== f.contentWindow || event.origin !== window.location.origin) return;
    const m = event.data || {};
    if (m.type === "ready") {
      model.frameReady = true;
      const types = Object.fromEntries(Object.entries(registry().types).map(([k, t]) => [k, t.selectors]));
      postFrame({ type: "types", types });
      postFrame({ type: "tokens", tokens: model.tokens });
      syncPreviewState();
    } else if (m.type === "select") {
      model.sel = selectFromPreview(m.target, model.screen);
      model.stateView = "normal";
      draw(false);
      syncPreviewState();
    } else if (m.type === "error") {
      model.previewError = String(m.detail && (m.detail.message || m.detail) || "Valor no válido.");
      draw(false);
    } else if (m.type === "rendered" && model.previewError) {
      model.previewError = "";
      draw(false);
    }
  }

  function onClick(event) {
    if (!ctx || !ctx.active()) return;
    const t = event.target;
    if (!t || !t.closest) return;
    const q = (s) => t.closest(s);
    let el;
    if ((el = q("[data-vpb-pick]"))) { loadCompany(el.getAttribute("data-vpb-pick")); return; }
    if (q("[data-vpb-change-company]")) {
      if (dirty() && !model.modal) { model.modal = { type: "confirm", title: "Cambios sin guardar", message: "Hay cambios sin guardar en el borrador. ¿Salir sin guardarlos?", go: () => { model.modal = null; model.companyId = ""; model.tokens = null; draw(); }, cta: "Salir sin guardar", danger: true }; draw(false); return; }
      model.companyId = ""; model.tokens = null; draw(); return;
    }
    if ((el = q("[data-vpb-sel]"))) { const [kind, key] = el.getAttribute("data-vpb-sel").split("|"); model.sel = { kind, key }; model.stateView = "normal"; draw(false); syncPreviewState(); return; }
    if ((el = q("[data-vpb-screen]"))) { setScreen(el.getAttribute("data-vpb-screen")); return; }
    if (q("[data-vpb-guard]")) { model.guardOpen = !model.guardOpen; draw(false); return; }
    if ((el = q("[data-vpb-size]"))) { model.size = el.getAttribute("data-vpb-size"); draw(false); cssom(ctx.root()); return; }
    if (q("[data-vpb-lite]")) { model.lite = !model.lite; draw(false); syncPreviewState(); return; }
    if ((el = q("[data-vpb-state]"))) { model.stateView = el.getAttribute("data-vpb-state"); draw(false); syncPreviewState(); return; }
    if ((el = q("[data-vpb-fix]"))) {
      const issue = contrastIssues(model.tokens, registry()).find((i) => i.id === el.getAttribute("data-vpb-fix"));
      if (issue) change(applyFix(model.tokens, issue), true);
      return;
    }
    if ((el = q("[data-vpb-grad]"))) {
      const [path, op, idx] = el.getAttribute("data-vpb-grad").split("|");
      const g = editGradient(getPath(model.tokens, path), op === "add" ? { addStop: true } : { removeStop: Number(idx) });
      change(setPath(clone(model.tokens), path, g), true);
      return;
    }
    if ((el = q("[data-vpb-fill]"))) {
      const [path, kind] = el.getAttribute("data-vpb-fill").split("|");
      const c = model.tokens.theme.colors;
      const value = kind === "none" ? undefined : kind === "preset" ? { kind: "preset" } : kind === "solid" ? { kind: "solid", color: c.primary } : { kind: "gradient", gradient: defaultGradient(c.primary, c.secondary) };
      change(setPath(clone(model.tokens), path, value), true);
      return;
    }
    if ((el = q("[data-vpb-layer]"))) {
      const [screen, layer, op] = el.getAttribute("data-vpb-layer").split("|");
      const c = model.tokens.theme.colors;
      const value = op === "off" ? null : layer === "veil" ? { gradient: { type: "linear", angle: 180, stops: [{ color: "#000000", at: 0 }, { color: c.background, at: 100 }] }, darken: 20, blur: 0, opacity: 60 } : null;
      change(setBackgroundLayer(model.tokens, screen, layer, value), true);
      return;
    }
    if ((el = q("[data-vpb-img]"))) {
      const [path, id] = el.getAttribute("data-vpb-img").split("|");
      if (path === "theme.logo") change(setPath(clone(model.tokens), path, id), true);
      else {
        const screen = path.split(".")[1];
        const bg = backgroundOf(model.tokens, screen);
        const prev = (bg && bg.image) || { mode: "cover", size: 40, position: "center", opacity: 100 };
        change(setBackgroundLayer(model.tokens, screen, "image", { ...prev, id }), true);
      }
      return;
    }
    if ((el = q("[data-vpb-bgmode]"))) { const [screen, mode] = el.getAttribute("data-vpb-bgmode").split("|"); change(setBgMode(model.tokens, screen, mode), true); return; }
    if (q("[data-vpb-logo-off]")) { change(setPath(clone(model.tokens), "theme.logo", null), true); return; }
    if (q("[data-vpb-reset]")) { change(resetSelection(model.tokens, model.sel), true); return; }
    if (q("[data-vpb-palette]")) {
      act(async () => {
        const out = await request(`${API}/${encodeURIComponent(model.companyId)}/palette-from-logo`, { method: "POST", body: JSON.stringify({ image_id: model.tokens.theme.logo || "" }) });
        const r = applyPalette(model.tokens, out.colors);
        model.tokens = r.tokens;
        model.undo = r.undo;
        pushPreview();
      }, "Colores propuestos desde el logo aplicados al borrador. Puedes deshacerlos.");
      return;
    }
    if (q("[data-vpb-undo]")) { const prev = model.undo; model.undo = null; change(undoPalette(model.tokens, prev), true); model.notice = "Colores restaurados."; draw(false); return; }
    if (q("[data-vpb-save]")) { act(saveDraft, "Borrador guardado. Los operarios siguen viendo la versión publicada."); return; }
    if ((el = q("[data-vpb-open]"))) { openModal(el.getAttribute("data-vpb-open")); return; }
    if ((el = q("[data-vpb-tpl]"))) {
      const tpl = arr(model.templates).find((x) => x.key === el.getAttribute("data-vpb-tpl"));
      if (!tpl) return;
      model.modal = { type: "confirm", title: `Aplicar «${tpl.label}»`, message: `Reemplaza todo el borrador de ${model.company.name} por la plantilla ${tpl.label} (el logo se conserva). Lo publicado no cambia.`, cta: "Reemplazar el borrador",
        go: () => act(async () => { const next = clone(tpl.tokens); next.theme.logo = model.tokens.theme.logo || null; model.tokens = next; await saveDraft(); }, `Plantilla ${tpl.label} aplicada al borrador.`, true) };
      draw(false);
      return;
    }
    if ((el = q("[data-vpb-rollback]"))) {
      const v = Number(el.getAttribute("data-vpb-rollback"));
      model.modal = { type: "confirm", title: `Volver a la versión ${v}`, message: `Los operarios de ${model.company.name} verán la versión ${v} al recargar. Queda en la auditoría.`, cta: `Volver a la versión ${v}`,
        go: () => act(async () => { await request(`${API}/${encodeURIComponent(model.companyId)}/rollback/${v}`, { method: "POST", body: JSON.stringify({ confirm_name: model.company.name }) }); await reload(); }, `Versión ${v} publicada de nuevo en ${model.company.name}.`, true) };
      draw(false);
      return;
    }
    if (q("[data-vpb-unpublish]")) {
      model.modal = { type: "confirm", title: "Quitar la marca publicada", danger: true, message: `${model.company.name} vuelve a verse como antes del estudio. Queda en la auditoría.`, cta: "Quitar la marca",
        go: () => act(async () => { await request(`${API}/${encodeURIComponent(model.companyId)}/unpublish`, { method: "POST", body: JSON.stringify({ confirm_name: model.company.name }) }); await reload(); }, "Marca publicada retirada.", true) };
      draw(false);
      return;
    }
    if (q("[data-vpb-share-new]")) { act(async () => { const out = await request(`${API}/${encodeURIComponent(model.companyId)}/share`, { method: "POST", body: JSON.stringify({}) }); await loadShare(); model.share.created = `${window.location.origin}${out.url}`; model.modal = { type: "share", title: "Compartir vista previa" }; }, "Enlace creado."); return; }
    if ((el = q("[data-vpb-share-revoke]"))) { act(async () => { await request(`${API}/${encodeURIComponent(model.companyId)}/share/${encodeURIComponent(el.getAttribute("data-vpb-share-revoke"))}`, { method: "DELETE" }); await loadShare(); model.modal = { type: "share", title: "Compartir vista previa" }; }, "Enlace revocado."); return; }
    if (q("[data-vpb-share-copy]")) { const v = model.share && model.share.created; if (v && navigator.clipboard) navigator.clipboard.writeText(v).then(() => ctx.toast("Enlace copiado.")).catch(() => ctx.toast("No se pudo copiar.")); return; }
    if (q("[data-vpb-close]") || (t.matches && t.matches("[data-vpb-modal]"))) { model.modal = null; draw(false); return; }
    if (q("[data-vpb-go]")) { const md = model.modal; if (md && md.go) md.go(); }
  }

  async function loadShare() {
    const out = await request(`${API}/${encodeURIComponent(model.companyId)}/share`);
    model.share = { links: out.links, created: "" };
  }

  // Cambiar de pestaña: la vista previa, el tamaño y el bloque "Esta pantalla"
  // cambian solos; si lo elegido era de la pantalla anterior, pasa al fondo de esta.
  function setScreen(screen) {
    model.screen = screen;
    model.size = defaultSize(screen);
    if (model.sel.kind === "background" || model.sel.kind === "piece") model.sel = { kind: "background", key: screen };
    model.stateView = "normal";
    draw(true);
  }

  function openModal(kind) {
    if (kind === "templates") {
      model.modal = { type: "templates", title: "Plantillas de arranque" };
      if (!model.templates) request(`${API}/templates`).then((out) => { model.templates = out.templates; draw(false); }).catch((e) => { model.modal.error = e.message; draw(false); });
    } else if (kind === "copy") {
      model.modal = { type: "copy", title: "Copiar la marca de otra empresa", cta: "Copiar al borrador",
        go: () => { const src = model.modal.source; if (!src) { model.modal.error = "Elige la empresa de origen."; draw(false); return; }
          act(async () => { await request(`${API}/${encodeURIComponent(model.companyId)}/copy-from/${encodeURIComponent(src)}`, { method: "POST", body: "{}" }); await reload(); }, "Marca copiada al borrador (sin imágenes).", true); } };
    } else if (kind === "history") {
      model.modal = { type: "history", title: `Historial de ${model.company.name}` };
    } else if (kind === "share") {
      model.modal = { type: "share", title: "Compartir vista previa" };
      model.share = null;
      loadShare().then(() => draw(false)).catch((e) => { model.modal.error = e.message; draw(false); });
    } else if (kind === "publish") {
      model.modal = { type: "confirm", title: "Publicar la marca", message: `Publicar la marca en ${model.company.name}. Sus operarios la verán en el ingreso y en los mini paneles al recargar. ${dirty() ? "Antes se guarda el borrador. " : ""}Queda en la auditoría.`, cta: `Publicar en ${model.company.name}`,
        go: () => act(async () => { if (dirty()) await saveDraft(); await request(`${API}/${encodeURIComponent(model.companyId)}/publish`, { method: "POST", body: JSON.stringify({ confirm_name: model.company.name }) }); await reload(); }, `Marca publicada en ${model.company.name}.`, true) };
    }
    draw(false);
  }

  function valueFrom(input) {
    const kind = input.getAttribute("data-vpb-kind");
    if (kind === "number") return Number(input.value);
    if (kind === "select") { const n = Number(input.value); return input.value !== "" && String(n) === input.value ? n : input.value; }
    return String(input.value || "").trim().toLowerCase();
  }

  function onInput(event) {
    if (!ctx || !ctx.active()) return;
    const t = event.target;
    if (!t || !t.matches) return;
    if (t.matches("[data-vpb-pick-search]")) { model.pickerQuery = t.value; draw(); const s = ctx.root().querySelector("[data-vpb-pick-search]"); if (s) { s.focus(); s.setSelectionRange(s.value.length, s.value.length); } return; }
    if (!t.matches("[data-vpb-path]")) return;
    const path = t.getAttribute("data-vpb-path");
    const kind = t.getAttribute("data-vpb-kind");
    const value = valueFrom(t);
    if ((kind === "hex" || kind === "color") && !HEX.test(value)) return;
    model.tokens = setPath(clone(model.tokens), path, value);
    // sincroniza el control gemelo (color ↔ hex) y la salida del deslizador sin redibujar
    const root = ctx.root();
    root.querySelectorAll(`[data-vpb-path="${CSS.escape(path)}"]`).forEach((el) => { if (el !== t && (el.type === "color" || el.getAttribute("data-vpb-kind") === "hex")) el.value = value; });
    const out = root.querySelector(`[data-vpb-out="${CSS.escape(path)}"]`);
    if (out) out.textContent = `${value}${t.getAttribute("data-vpb-unit") || ""}`;
    pushPreview();
  }

  function onChange(event) {
    if (!ctx || !ctx.active()) return;
    const t = event.target;
    if (!t || !t.matches) return;
    if (t.matches("[data-vpb-copy-source]") && model.modal) { model.modal.source = t.value; return; }
    if (t.matches("[data-vpb-usegeneral]")) {
      const screen = t.getAttribute("data-vpb-usegeneral");
      const spec = registry().screens[screen];
      const keepsOwn = spec && (spec.family !== "portal" || spec.page === "login");
      change(setBgMode(model.tokens, screen, t.checked ? "inherit" : keepsOwn ? "own" : "custom"), true);
      return;
    }
    if (t.matches("[data-vpb-inherit]")) { change(setInherit(model.tokens, t.getAttribute("data-vpb-inherit"), t.checked), true); return; }
    if (t.matches("[data-vpb-panels]")) { change(setPath(clone(model.tokens), "theme.panels", t.checked), true); return; }
    if (t.matches("[data-vpb-upload]")) { upload(t); return; }
    if (t.matches("[data-vpb-path]")) draw(false);
  }

  function upload(input) {
    const file = input.files && input.files[0];
    if (!file) return;
    const path = input.getAttribute("data-vpb-upload");
    const form = new FormData();
    form.append("file", file);
    act(async () => {
      const out = await request(`${API}/${encodeURIComponent(model.companyId)}/images`, { method: "POST", body: form });
      model.data.images = [out.image, ...arr(model.data.images)];
      model.data.storage = { ...(model.data.storage || {}), ...out.usage };
      if (path === "theme.logo") model.tokens = setPath(clone(model.tokens), path, out.image.id);
      else {
        const screen = path.split(".")[1];
        const bg = backgroundOf(model.tokens, screen);
        model.tokens = setBackgroundLayer(model.tokens, screen, "image", { ...((bg && bg.image) || { mode: "cover", size: 40, position: "center", opacity: 100 }), id: out.image.id });
      }
      pushPreview();
    }, "Imagen subida (WebP y versión liviana).");
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.brand = {
    mount(context) {
      ctx = context;
      model.notice = "";
      const params = (context && context.params) || {};
      if (!bound && typeof document.addEventListener === "function") {
        document.addEventListener("click", onClick);
        document.addEventListener("input", onInput);
        document.addEventListener("change", onChange);
        window.addEventListener("message", onMessage);
        window.addEventListener("resize", () => { if (ctx && ctx.active() && ctx.root()) cssom(ctx.root()); });
        bound = true;
      }
      if (params.companyId && params.companyId !== model.companyId) { loadCompany(params.companyId); return; }
      draw();
    },
  };
  window.CxBrandStudio = {
    model, getPath, setPath, splitPath, selectFromPreview, screensFor, setBgMode, setScreen, piecesFor, defaultSize, treeView, stageTop, editGradient, gradientCss, fillCss, setBackgroundLayer, setInherit, backgroundOf,
    applyPalette, undoPalette, resetSelection, contrastIssues, applyFix, contrast, onColor, onMessage, onClick, onInput, draw,
    _ctx: (c) => { ctx = c; },
  };
})();
