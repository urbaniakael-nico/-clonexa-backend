// Fase B · idioma del portal y de los mini paneles (es, en, fr) con UN solo
// diccionario. El texto base es el español: la clave ES el texto en español,
// así que si falta una traducción se ve el español (nunca una clave).
// - Con la empresa en español (todas las de Colombia) no hace NADA: el portal
//   se ve exactamente igual que antes.
// - En inglés o francés traduce lo que las pantallas dibujan (textos,
//   placeholder, title, aria-label) con coincidencia exacta y unos patrones
//   para frases con números. Nunca toca lo que la persona escribe (inputs)
//   ni nada dentro de [data-no-i18n].
// - t("texto", {var}) para el código que prefiera traducir al construir.
// El idioma sale de Ajustes (company_locale, vía CxLocale).
(() => {
  "use strict";

  const DICT = window.CX_I18N_DICT || { en: {}, fr: {} };
  const PATTERNS = window.CX_I18N_PATTERNS || { en: [], fr: [] };
  const LOCALES = { es: "es-CO", en: "en-US", fr: "fr-FR" };
  const ATTRS = ["placeholder", "title", "aria-label"];
  let forced = "";
  let observer = null;

  function lang() {
    const l = forced || (window.CxLocale && window.CxLocale.loaded && window.CxLocale.language) || "es";
    return l === "en" || l === "fr" ? l : "es";
  }

  function fill(text, vars) {
    return vars ? String(text).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(text);
  }

  function single(es, l) {
    const table = DICT[l] || {};
    if (Object.prototype.hasOwnProperty.call(table, es)) return table[es];
    for (const [re, out] of PATTERNS[l] || []) {
      const m = es.match(re);
      if (m) return typeof out === "function" ? out(...m) : es.replace(re, out);
    }
    return null;
  }

  // Traducción de un texto en español (exacta, por patrón o por partes
  // separadas con "·" o "›", ej. "Pantalón · Mujer · Talla 4 → 30"); null si no hay.
  function lookup(es, l = lang()) {
    if (l === "es" || !es) return null;
    const whole = single(es, l);
    if (whole !== null) return whole;
    if (!/[·›]/.test(es)) return null;
    let changed = false;
    const out = es.split(/(\s*[·›]\s*)/).map((part) => {
      const core = part.trim();
      if (!core || /^[·›]$/.test(core)) return part;
      const tr = single(core, l);
      if (tr === null || tr === core) return part;
      changed = true;
      return part.replace(core, tr);
    }).join("");
    return changed ? out : null;
  }

  function t(es, vars) {
    return fill(lookup(es) ?? es, vars);
  }

  // Lo que la persona escribe (textarea, contenteditable) no se toca; sus
  // atributos (placeholder, title) sí se traducen.
  function skip(node, attrs = false) {
    const el = node.nodeType === 1 ? node : node.parentElement;
    if (!el || !el.closest) return true;
    return Boolean(el.closest(attrs ? "[data-no-i18n],script,style" : "[data-no-i18n],script,style,textarea,[contenteditable='true']"));
  }

  function translateText(node) {
    const raw = node.nodeValue;
    const trimmed = raw && raw.trim();
    if (!trimmed || skip(node)) return;
    const out = lookup(trimmed);
    if (out !== null && out !== trimmed) node.nodeValue = raw.replace(trimmed, out);
  }

  function translateAttrs(el) {
    if (skip(el, true)) return;
    for (const attr of ATTRS) {
      const value = el.getAttribute && el.getAttribute(attr);
      if (!value) continue;
      const out = lookup(value.trim());
      if (out !== null && out !== value) el.setAttribute(attr, out);
    }
  }

  function translate(root = document.body) {
    if (lang() === "es" || !root) return;
    if (root.nodeType === 3) { translateText(root); return; }
    if (root.nodeType !== 1) return;
    translateAttrs(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      if (node.nodeType === 3) translateText(node); else translateAttrs(node);
      node = walker.nextNode();
    }
    if (document.documentElement) document.documentElement.setAttribute("lang", lang());
  }

  function watch() {
    if (observer || typeof MutationObserver === "undefined" || !document.body) return;
    observer = new MutationObserver((records) => {
      if (lang() === "es") return;
      for (const r of records) {
        if (r.type === "characterData") translateText(r.target);
        else if (r.type === "attributes") translateAttrs(r.target);
        else r.addedNodes.forEach((n) => translate(n));
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }

  // Arranca cuando el idioma de la empresa ya se conoce (CxLocale cargado).
  let tries = 0;
  function start() {
    if (lang() === "es") {
      // Espera a que cargue el idioma de la empresa (unos segundos como mucho).
      if (!(window.CxLocale && window.CxLocale.loaded) && tries < 60) { tries += 1; setTimeout(start, 300); }
      return;
    }
    translate(document.body);
    watch();
  }

  window.CxI18n = {
    t, lookup, translate, lang, start,
    locale: () => LOCALES[lang()],
    setLanguage(l) { forced = l || ""; start(); },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
