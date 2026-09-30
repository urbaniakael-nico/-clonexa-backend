// 049V: tema de la empresa (Admin V2) en los mini paneles de caja, mesero y
// cocina. Solo con el interruptor mini_panel_brand del modulo waiter_ordering
// (el servidor responde /waiter-ordering/panel-theme con enabled=false a las
// demas empresas y aqui no cambia nada).
//
// Los tres paneles traen su hoja de estilos oscura escrita a mano. En vez de
// reescribirlas, este modulo traduce sus colores a la paleta de la marca:
// fondos oscuros -> fondo/superficies de la empresa, texto claro -> su color de
// texto, el degradado rosa de CLONEXA -> su color primario y secundario, y los
// tonos pastel (pensados para fondo negro) a su version oscura cuando el tema
// es claro. Los colores de estado (verde listo, ambar en preparacion, rojo)
// se conservan. El tema queda guardado en el equipo para que la pantalla de
// ingreso tambien salga con la marca.
(() => {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  // 049Z: el link de domicilios trae la empresa en ?c=; el QR de la carta no
  // la trae (el servidor incrusta el tema en window.__CX_BRAND__).
  const companyId = params.get("company_id") || params.get("companyId") || params.get("c") || "";
  const embedded = () => (window.__CX_BRAND__ && typeof window.__CX_BRAND__ === "object" ? window.__CX_BRAND__ : null);
  const cacheKey = `clonexa_panel_brand_${companyId}`;
  const VARS_ID = "cxPanelBrand049V";
  const FONTS = ["Inter", "Manrope", "Sora", "Space Grotesk", "Rajdhani", "Orbitron", "Poppins", "Montserrat"];

  // ------------------------------------------------------------ color math
  function hex6(value, fallback) {
    const v = String(value || "").trim();
    if (/^#[0-9a-f]{6}$/i.test(v)) return v.toLowerCase();
    if (/^#[0-9a-f]{3}$/i.test(v)) return `#${v.slice(1).split("").map((c) => c + c).join("")}`.toLowerCase();
    return fallback;
  }

  function rgb(hex) {
    const v = hex6(hex, "#000000");
    return [parseInt(v.slice(1, 3), 16), parseInt(v.slice(3, 5), 16), parseInt(v.slice(5, 7), 16)];
  }

  function toHex(parts) {
    return `#${parts.map((n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0")).join("")}`;
  }

  // t = cuanto de `b` (0..1).
  function mix(a, b, t) {
    const x = rgb(a);
    const y = rgb(b);
    return toHex(x.map((n, i) => n + (y[i] - n) * t));
  }

  function luminance(hex) {
    const [r, g, b] = rgb(hex).map((n) => {
      const c = n / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  function contrast(a, b) {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  }

  // El color de marca, oscurecido (o aclarado) hasta leerse sobre `bg`.
  function readable(color, bg, min = 4.5) {
    const toward = luminance(bg) > 0.4 ? "#000000" : "#ffffff";
    let out = color;
    for (let step = 1; step <= 10 && contrast(out, bg) < min; step += 1) out = mix(color, toward, step / 10);
    return out;
  }

  function onColor(bg) {
    return contrast("#ffffff", bg) >= contrast("#111111", bg) ? "#ffffff" : "#111111";
  }

  function saturation(hex) {
    const [r, g, b] = rgb(hex).map((n) => n / 255);
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    if (max === min) return 0;
    const l = (max + min) / 2;
    return (max - min) / (l > 0.5 ? 2 - max - min : max + min);
  }

  // ------------------------------------------------------------ palette
  function palette(branding) {
    const b = branding || {};
    const bg = hex6(b.background_color, "#080712");
    const light = luminance(bg) > 0.4;
    const textRaw = hex6(b.text_color, light ? "#111111" : "#f8fafc");
    const ink = contrast(textRaw, bg) >= 4.5 ? textRaw : onColor(bg);
    const primary = hex6(b.primary_color, "#ff2d95");
    const secondary = hex6(b.secondary_color, "#ff7a18");
    const surface = light ? mix(bg, "#ffffff", 0.72) : mix(bg, "#ffffff", 0.06);
    const font = FONTS.includes(String(b.font_family || "").trim()) ? String(b.font_family).trim() : "";
    return {
      mode: light ? "light" : "dark",
      bg,
      bg2: light ? mix(bg, hex6(b.gradient_to, secondary), 0.18) : mix(bg, primary, 0.08),
      page: light
        ? `linear-gradient(160deg, ${mix(bg, hex6(b.gradient_from, primary), 0.22)} 0%, ${bg} 42%, ${mix(bg, hex6(b.gradient_to, secondary), 0.28)} 100%)`
        : `radial-gradient(circle at 12% 0%, ${primary}26, transparent 38%), ${bg}`,
      surface,
      surface2: light ? mix(bg, "#ffffff", 0.45) : mix(bg, "#ffffff", 0.1),
      header: light ? `${mix(bg, "#ffffff", 0.55)}f0` : `${mix(bg, "#000000", 0.2)}eb`,
      field: light ? "#ffffff" : mix(bg, "#000000", 0.35),
      ink,
      inkRgb: rgb(ink).join(","),
      muted: mix(ink, bg, 0.42),
      line: light ? mix(bg, ink, 0.16) : mix(bg, "#ffffff", 0.14),
      primary,
      primaryRgb: rgb(primary).join(","),
      secondary,
      primary2: mix(primary, "#000000", 0.18),
      onPrimary: onColor(primary),
      primaryInk: readable(primary, surface),
      secondaryInk: readable(secondary, surface),
      font,
      logo: /^(data:image\/|https:\/\/|\/)/.test(String(b.logo_url || "")) ? String(b.logo_url) : "",
    };
  }

  // ------------------------------------------------------------ CSS rewrite
  const LIGHT_TEXT = ["#fff", "#ffffff", "#f5f3ff", "#f8fafc", "#e2e8f0", "#e5e7eb"];
  const MUTED_TEXT = ["#c9c3e6", "#8f8aa8", "#a79fcf"];
  // 049Z: tambien los fondos del QR de mesa, la carta QR y el panel generico.
  const PAGE_DARK = ["#080712", "#0a0714", "#0a0716", "#070312", "#050510", "#080813", "#090b16", "#020617"];
  const PAGE_DARK_2 = ["#0d1522", "#150019", "#19102f"];
  const SURFACE_DARK = ["#120e20", "#141225", "#15131f", "#111827", "#101827", "#0f172a"];
  // Pastel sobre negro -> su tono oscuro, legible sobre un fondo claro.
  const PASTEL_DARK = {
    "#86efac": "#15803d", "#bbf7d0": "#166534", "#4ade80": "#15803d",
    "#fecaca": "#b91c1c", "#fca5a5": "#dc2626", "#f87171": "#dc2626",
    "#fde68a": "#a16207", "#ffd166": "#b45309", "#fbbf24": "#b45309",
    "#ffb3d9": "#be185d", "#a5b4fc": "#4338ca", "#7dd3fc": "#0369a1",
    "#bae6fd": "#0369a1", "#e0f2fe": "#075985", "#dbeafe": "#1d4ed8", "#60a5fa": "#1d4ed8",
  };
  const BRAND_HEX = { "#ff2d95": "primary", "#ff7a18": "secondary", "#a855f7": "primary2", "#ff22b8": "primary", "#9333ea": "primary2" };
  // Variables CSS de texto (el resto de variables de color se pintan como fondo).
  const TEXT_VARS = /^--(text|muted|ink|qr-text|qr-muted|fg)$/;
  const COLOR_TOKEN = /#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\(\s*[0-9.]+\s*,\s*[0-9.]+\s*,\s*[0-9.]+\s*(?:,\s*[0-9.]+\s*)?\)/g;

  function parseRgba(token) {
    const parts = token.replace(/rgba?\(|\)/g, "").split(",").map((n) => Number(n.trim()));
    return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
  }

  function isWhiteRgba(token) {
    if (!/^rgba?\(/.test(token)) return false;
    const c = parseRgba(token);
    return c.r === 255 && c.g === 255 && c.b === 255;
  }

  function isNavyRgba(token) {
    if (!/^rgba?\(/.test(token)) return false;
    const c = parseRgba(token);
    return c.r <= 40 && c.g <= 40 && c.b <= 60 && !(c.r === 0 && c.g === 0 && c.b === 0);
  }

  function isDarkRgba(token) {
    if (!/^rgba?\(/.test(token)) return false;
    const c = parseRgba(token);
    return c.r <= 20 && c.g <= 20 && c.b <= 34 && c.a >= 0.5;
  }

  // Un fondo de color de verdad (boton verde, rojo, el degradado de marca):
  // su texto blanco se queda blanco.
  function solidColored(value) {
    const tokens = String(value).match(COLOR_TOKEN) || [];
    return tokens.some((token) => {
      const low = token.toLowerCase();
      if (BRAND_HEX[hex6(low, "")]) return true;
      // Casi negro (los fondos morados oscuros del panel) no es "de color".
      const vivid = (h) => saturation(h) > 0.35 && luminance(h) > 0.04 && luminance(h) < 0.5;
      if (/^rgba?\(/.test(low)) {
        const c = parseRgba(low);
        return c.a >= 0.8 && vivid(toHex([c.r, c.g, c.b]));
      }
      const h6 = hex6(low, "");
      return Boolean(h6) && vivid(h6);
    });
  }

  function hasBrandGradient(value) {
    return (String(value).match(COLOR_TOKEN) || []).some((t) => BRAND_HEX[hex6(t.toLowerCase(), "")]);
  }

  function mapTextColor(token, p, ctx) {
    const low = token.toLowerCase();
    const h6 = hex6(low, "");
    if (LIGHT_TEXT.includes(low) || (h6 && LIGHT_TEXT.includes(h6))) {
      if (ctx.brandBg) return "var(--cxb-on-primary)";
      return ctx.coloredBg ? token : "var(--cxb-ink)";
    }
    if (ctx.coloredBg) return token;
    if (MUTED_TEXT.includes(low) || isWhiteRgba(low)) return "var(--cxb-muted)";
    if (h6 && BRAND_HEX[h6]) return BRAND_HEX[h6] === "secondary" ? "var(--cxb-secondary-ink)" : "var(--cxb-primary-ink)";
    if (p.mode === "light" && h6 && PASTEL_DARK[h6]) return PASTEL_DARK[h6];
    return token;
  }

  function mapPaintColor(token, p, prop) {
    const low = token.toLowerCase();
    const h6 = hex6(low, "");
    if (h6 && PAGE_DARK.includes(h6)) return "var(--cxb-bg)";
    if (h6 && PAGE_DARK_2.includes(h6)) return "var(--cxb-bg2)";
    if (h6 && SURFACE_DARK.includes(h6)) return "var(--cxb-surface)";
    // El degradado de CLONEXA (naranja -> rosa -> morado) pasa a ser el primario
    // de la marca con un tono mas profundo: dos colores de marca mezclados se ensucian.
    if (h6 && BRAND_HEX[h6]) return BRAND_HEX[h6] === "primary2" ? "var(--cxb-primary2)" : "var(--cxb-primary)";
    if (/^rgba?\(/.test(low)) {
      const c = parseRgba(low);
      if (c.r === 247 && c.g === 37 && c.b === 133) return `rgba(${p.primaryRgb},${c.a})`;
      if (c.r === 255 && c.g === 34 && c.b === 184) return `rgba(${p.primaryRgb},${c.a})`;
      if (c.r === 8 && c.g === 7 && c.b === 18) return "var(--cxb-header)";
      if (c.r === 3 && c.g === 7 && c.b === 18) return "var(--cxb-field)";
      if (isDarkRgba(low) && !(c.r === 0 && c.g === 0 && c.b === 0)) return "var(--cxb-surface)";
      // 049Z: velos oscuros (azul pizarra del QR de mesa, etc.)
      if (isNavyRgba(low)) {
        if (c.a >= 0.5) return "var(--cxb-surface)";
        if (p.mode === "light") return `rgba(${p.inkRgb},${(c.a * 0.25).toFixed(3)})`;
      }
      if (isWhiteRgba(low)) {
        if (p.mode === "light" && /^background/.test(prop)) return `rgba(255,255,255,${Math.min(0.92, 0.5 + c.a * 3).toFixed(2)})`;
        return `rgba(${p.inkRgb},${c.a})`;
      }
    }
    return token;
  }

  const PAINT_PROPS = /^(background|background-color|background-image|border|border-(top|right|bottom|left)|border-color|outline|box-shadow)$/;

  function themeRule(decls, p) {
    const list = decls.split(";");
    const bgValue = list
      .map((d) => d.split(":"))
      .filter((pair) => pair.length > 1 && /^\s*background(-color|-image)?\s*$/.test(pair[0]))
      .map((pair) => pair.slice(1).join(":"))
      .join(" ");
    const ctx = { coloredBg: Boolean(bgValue) && solidColored(bgValue), brandBg: Boolean(bgValue) && hasBrandGradient(bgValue) };
    let hasColor = false;
    const out = list.map((decl) => {
      const at = decl.indexOf(":");
      if (at < 0) return decl;
      const prop = decl.slice(0, at).trim().toLowerCase();
      const value = decl.slice(at + 1);
      if (prop === "color") {
        hasColor = true;
        return `${decl.slice(0, at)}:${value.replace(COLOR_TOKEN, (t) => mapTextColor(t, p, ctx))}`;
      }
      if (prop === "color-scheme") return `${decl.slice(0, at)}:${p.mode}`;
      // 049Z: variables CSS con colores (--bg, --card, --qr-card, --text...).
      if (prop.startsWith("--")) {
        if (TEXT_VARS.test(prop)) return `${decl.slice(0, at)}:${value.replace(COLOR_TOKEN, (t) => mapTextColor(t, p, { coloredBg: false, brandBg: false }))}`;
        return `${decl.slice(0, at)}:${value.replace(COLOR_TOKEN, (t) => mapPaintColor(t, p, "background"))}`;
      }
      if (PAINT_PROPS.test(prop)) return `${decl.slice(0, at)}:${value.replace(COLOR_TOKEN, (t) => mapPaintColor(t, p, prop))}`;
      return decl;
    });
    let text = out.join(";");
    // Un fondo de color que heredaba el texto blanco del boton base.
    if (!hasColor && ctx.brandBg) text += `${text.trim().endsWith(";") || !text.trim() ? "" : ";"}color:var(--cxb-on-primary)`;
    else if (!hasColor && ctx.coloredBg) text += `${text.trim().endsWith(";") || !text.trim() ? "" : ";"}color:#fff`;
    return text;
  }

  function themeCss(css, p) {
    return String(css || "").replace(/([^{}]+)\{([^{}]*)\}/g, (_match, selector, decls) => `${selector}{${themeRule(decls, p)}}`);
  }

  function varsCss(p) {
    const logo = p.logo ? `url("${p.logo.replace(/"/g, "%22")}")` : "none";
    return `
      :root{
        --cxb-mode:${p.mode};--cxb-bg:${p.bg};--cxb-bg2:${p.bg2};--cxb-page:${p.page};--cxb-surface:${p.surface};
        --cxb-surface2:${p.surface2};--cxb-header:${p.header};--cxb-field:${p.field};--cxb-ink:${p.ink};--cxb-ink-rgb:${p.inkRgb};
        --cxb-muted:${p.muted};--cxb-line:${p.line};--cxb-primary:${p.primary};--cxb-primary-rgb:${p.primaryRgb};
        --cxb-secondary:${p.secondary};--cxb-primary2:${p.primary2};--cxb-on-primary:${p.onPrimary};
        --cxb-primary-ink:${p.primaryInk};--cxb-secondary-ink:${p.secondaryInk};--cxb-logo:${logo};
        ${p.font ? `--cxb-font:"${p.font}",Inter,system-ui,sans-serif;` : ""}
      }
      html[data-cx-brand] body{background:var(--cxb-page) fixed,var(--cxb-bg) !important;color:var(--cxb-ink)}
      ${p.font ? `html[data-cx-brand] body,html[data-cx-brand] button,html[data-cx-brand] input,html[data-cx-brand] select,html[data-cx-brand] textarea{font-family:var(--cxb-font)}` : ""}
      html[data-cx-brand] input,html[data-cx-brand] select,html[data-cx-brand] textarea{color:var(--cxb-ink);background-color:var(--cxb-field)}
      ${p.logo ? `html[data-cx-brand] .csh-brand,html[data-cx-brand] .wtr-brand,html[data-cx-brand] .ktc-brand{font-size:0 !important;height:64px;background:var(--cxb-logo) left center/contain no-repeat}` : ""}
    `;
  }

  // ------------------------------------------------------------ apply
  const originals = new WeakMap();
  let current = null;
  let observer = null;

  function headStyles() {
    const head = document.head;
    if (!head) return [];
    const list = head.children ? Array.from(head.children) : Array.from(head.querySelectorAll("style"));
    return list.filter((el) => String(el.tagName || "").toLowerCase() === "style" && el.id !== VARS_ID);
  }

  function themeStyle(el) {
    if (!originals.has(el)) originals.set(el, el.textContent || "");
    el.textContent = current ? themeCss(originals.get(el), current) : originals.get(el);
  }

  function ensureFont(p) {
    if (!p.font || p.font === "Inter" || !document.head) return;
    const id = "cxPanelBrandFont049V";
    if (document.getElementById && document.getElementById(id)) return;
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(p.font).replace(/%20/g, "+")}:wght@400;500;600;700;800;900&display=swap`;
    document.head.appendChild(link);
  }

  function watchHead() {
    if (observer || typeof MutationObserver === "undefined" || !document.head) return;
    observer = new MutationObserver((records) => {
      if (!current) return;
      records.forEach((record) => (record.addedNodes || []).forEach((node) => {
        if (String(node.tagName || "").toLowerCase() === "style" && node.id !== VARS_ID && !originals.has(node)) themeStyle(node);
      }));
    });
    observer.observe(document.head, { childList: true });
  }

  // 049Z: las hojas externas propias (/client-static/*.css, p. ej. el panel
  // generico) se copian a un <style> para poder pintarlas con la marca.
  function inlineLinkedSheets() {
    if (!document.head || !document.head.querySelectorAll || typeof fetch !== "function") return;
    Array.from(document.head.querySelectorAll('link[rel="stylesheet"]')).forEach((link) => {
      const href = String(link.getAttribute("href") || "");
      if (!href.startsWith("/client-static/") || link.getAttribute("data-cxb-inlined")) return;
      link.setAttribute("data-cxb-inlined", "1");
      fetch(href).then((r) => (r.ok ? r.text() : "")).then((css) => {
        if (!css) return;
        const style = document.createElement("style");
        style.setAttribute("data-cxb-from", href);
        style.textContent = css;
        document.head.appendChild(style);  // el observador la pinta con la marca
        link.disabled = true;
      }).catch(() => {});
    });
  }

  function apply(branding) {
    current = palette(branding);
    let vars = document.getElementById ? document.getElementById(VARS_ID) : null;
    if (!vars || vars.id !== VARS_ID) {
      vars = document.createElement("style");
      vars.id = VARS_ID;
      document.head.appendChild(vars);
    }
    headStyles().forEach(themeStyle);
    vars.textContent = varsCss(current);
    try {
      document.documentElement.setAttribute("data-cx-brand", current.mode);
    } catch (_) {}
    ensureFont(current);
    watchHead();
    inlineLinkedSheets();
    return current;
  }

  function clear() {
    current = null;
    headStyles().forEach((el) => {
      if (originals.has(el)) el.textContent = originals.get(el);
    });
    const vars = document.getElementById ? document.getElementById(VARS_ID) : null;
    if (vars && vars.id === VARS_ID && vars.remove) vars.remove();
    try {
      document.documentElement.removeAttribute("data-cx-brand");
    } catch (_) {}
  }

  function cached() {
    try {
      const raw = window.localStorage.getItem(cacheKey);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function remember(branding) {
    try {
      if (branding) window.localStorage.setItem(cacheKey, JSON.stringify(branding));
      else window.localStorage.removeItem(cacheKey);
    } catch (_) {}
  }

  // `fetchJson(path)` es el api autenticado del panel (su token de rol).
  async function load(fetchJson) {
    try {
      const data = await fetchJson("/panel-theme");
      if (data && data.enabled && data.branding) {
        remember(data.branding);
        return apply(data.branding);
      }
      // 049Z: el tema que el servidor incrusto en la pagina manda.
      if (embedded()) return apply(embedded());
      remember(null);
      clear();
    } catch (_) {
      // sin red o sin sesion: se queda el tema que ya estaba
    }
    return current;
  }

  function applyCached() {
    // 049Z: primero el tema incrustado por el servidor (sale con la marca
    // desde el primer pintado, incluso en un equipo nuevo); si no, el guardado.
    const fromServer = embedded();
    if (fromServer) {
      if (companyId) remember(fromServer);
      apply(fromServer);
      return;
    }
    const saved = companyId ? cached() : null;
    if (saved) apply(saved);
  }

  if (companyId || embedded()) {
    if (document.readyState === "loading" && document.addEventListener) document.addEventListener("DOMContentLoaded", applyCached);
    else window.setTimeout(applyCached, 0);
  }

  window.CxPanelBrand = { palette, themeCss, apply, clear, load, cached, current: () => current, contrast, readable };
})();
