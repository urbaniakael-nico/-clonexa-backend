// CRM VELVET-LAB · mini panel de UN usuario en la tableta del taller (interruptor
// crm_velvet_lab). Cada colaborador toca su nombre, escribe su PIN y registra turno
// (Iniciar / Pausa / Reanudar / Fin) y trabajo por referencia (Iniciar, Cambiar y
// Cerrar prendas por talla y cantidad). El servidor usa las MISMAS funciones del bot
// de Telegram (source_channel = crm_lab). A los 20 s sin uso vuelve a la lista.
// Liviano: un solo pedido al tablero cada 5 s. Textos por t().
// 056K: pantalla principal = CRM en vivo (tarjetas por estado con cronómetro), colores
// del tema publicado de la empresa, pantalla completa y todo dentro del alto real.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));

  const STATUS = { working: "Trabajando", on_break: "En pausa", sin_turno: "Sin turno" };
  const ERRORS = {
    pin_incorrecto: "PIN incorrecto.",
    pin_bloqueado: "Demasiados intentos. Espera unos minutos.",
    sin_pin: "Pide tu PIN al administrador.",
    pide_el_pin_otra_vez: "Vuelve a escribir tu PIN.",
    turno_ya_iniciado: "Tu turno ya está iniciado.",
    no_esta_trabajando: "No estás trabajando ahora.",
    no_esta_en_pausa: "No estás en pausa.",
    sin_turno_abierto: "No tienes un turno abierto.",
    inicia_tu_turno: "Inicia tu turno primero.",
    ya_en_esa_referencia: "Ya estás en esa referencia.",
    referencia_no_activa: "Esa referencia no está activa.",
    cantidad_invalida: "Escribe una cantidad válida.",
    colaborador_no_encontrado: "Colaborador no encontrado.",
    elige_una_referencia: "Elige una referencia para iniciar.",
  };
  const IDLE_MS = 20000;
  const POLL_MS = 5000;

  const P = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  // Desde la pantalla de inicio (manifest) el enlace llega sin company_id: la última empresa de este equipo.
  const COMPANY_KEY = "clonexa_crm_lab_company";
  const CID = P.get("company_id") || (() => { try { return window.localStorage.getItem(COMPANY_KEY) || ""; } catch (_) { return ""; } })();
  const API = "/api/v1";
  const KEY = `clonexa_crm_lab_token_${CID}`;
  const DEVICE_KEY = `clonexa_crm_lab_device_${CID}`;

  const st = { token: "", board: null, refs: [], view: "list", query: "", pinFor: null, pin: "", person: null, empToken: "", modal: null, startRef: "", refQuery: "",
    error: "", info: "", busy: false, login: { user: "", pass: "" }, mustChange: false, lastTouch: Date.now(), offset: 0 };

  function store(key, value) {
    try {
      if (value === undefined) return window.localStorage.getItem(key) || "";
      if (value) window.localStorage.setItem(key, value); else window.localStorage.removeItem(key);
    } catch (_) {}
    return "";
  }

  function device() {
    let id = store(DEVICE_KEY);
    if (!id) { id = `tab-${Math.random().toString(36).slice(2, 10)}`; store(DEVICE_KEY, id); }
    return id;
  }

  // "X h YY min" (formato central de horas)
  function hm(minutes) {
    const m = Math.max(0, Math.round(Number(minutes) || 0));
    return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
  }

  async function call(path, method = "GET", body = undefined, withEmployee = false) {
    const headers = { "X-Device-Id": device() };
    if (st.token) headers.Authorization = `Bearer ${st.token}`;
    if (withEmployee && st.empToken) headers["X-Employee-Token"] = st.empToken;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(`${API}${path}`, { method, headers, cache: "no-store", body: body !== undefined ? JSON.stringify(body) : undefined });
    let data = null;
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
      const detail = data && data.detail;
      const code = typeof detail === "string" ? detail : (detail && detail.code) || "";
      const err = new Error(T(ERRORS[code] || (typeof detail === "string" ? detail : "") || "No se pudo completar. Intenta de nuevo."));
      err.code = code;
      err.status = res.status;
      err.extra = detail && typeof detail === "object" ? detail : {};
      throw err;
    }
    return data;
  }
  const crm = (path) => `/crm-lab/companies/${encodeURIComponent(CID)}${path}`;

  // ------------------------------------------------------------ tema del portal y AA
  function rgb(hex) {
    const m = String(hex || "").trim().replace("#", "");
    const full = m.length === 3 ? m.split("").map((c) => c + c).join("") : m;
    return /^[0-9a-f]{6}$/i.test(full) ? [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16)) : null;
  }
  function lum(c) { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); }
  function contrast(a, b) { const x = lum(a) + 0.05; const y = lum(b) + 0.05; return Math.max(x, y) / Math.min(x, y); }
  function readableOn(bg) { return contrast([255, 255, 255], bg) >= contrast([17, 17, 17], bg) ? "#ffffff" : "#111111"; }
  const mix = (a, b, t) => a.map((v, i) => Math.round(v * (1 - t) + b[i] * t));
  const css = (c) => `rgb(${c.join(",")})`;
  const WHITE = [255, 255, 255];
  const BLACK = [0, 0, 0];

  // 056K: variables --crm-* desde el tema que ve el portal (brand.theme del servidor:
  // fondo de branding_background, colores principal, secundario y de fondo). Cada color
  // trae su texto encima (blanco o negro por contraste) y su borde oscuro. Sin tema,
  // los colores del panel inicial (brand.primary / brand.secondary).
  function palette(b) {
    const th = (b && b.theme) || {};
    const primary = rgb(th.primary || (b && b.primary)) || [124, 58, 237];
    const second = rgb(th.secondary || (b && b.secondary)) || mix(primary, WHITE, 0.5);
    const base = rgb(th.bg) || mix(primary, WHITE, 0.8);
    // TRABAJANDO: el color de fondo del tema si es claro (Velvet: aqua); si es oscuro, el secundario.
    const work = lum(base) >= 0.3 ? base : lum(second) >= 0.3 ? second : mix(second, WHITE, 0.55);
    const out = { page: th.background || `linear-gradient(135deg, ${css(base)}, ${css(primary)})`, font: th.font || "inherit" };
    const tone = (name, c, line = true) => {
      out[name] = css(c);
      out[`on-${name}`] = readableOn(c);
      if (line) { const l = mix(c, BLACK, 0.6); out[`${name}-line`] = css(l); out[`on-${name}-line`] = readableOn(l); }
    };
    tone("accent", primary);
    tone("bar", mix(primary, BLACK, 0.55), false);
    tone("work", work);
    const warning = rgb(th.warning);
    if (warning) tone("pause", warning);
    tone("idle", mix(base, WHITE, 0.84));
    tone("surface", mix(base, WHITE, 0.9));
    tone("key", mix(base, WHITE, 0.6), false);
    return out;
  }

  function applyBrand(b) {
    if (!b || typeof document === "undefined") return;
    const root = document.documentElement.style;
    const vars = palette(b);
    Object.keys(vars).forEach((k) => root.setProperty(`--crm-${k}`, vars[k]));
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", vars.bar);
    if (b.language && b.language !== "es" && window.CxI18n && window.CxI18n.setLanguage) window.CxI18n.setLanguage(b.language);
  }

  // ------------------------------------------------------------ utilidades de la pantalla
  const fold = (v) => String(v || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  // Cronómetro h:mm:ss (corre en el navegador entre actualizaciones del tablero).
  function hms(iso) {
    if (!iso) return "";
    const s = Math.max(0, Math.floor((Date.now() + st.offset - new Date(iso).getTime()) / 1000));
    return `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }
  // Trabajando, luego en pausa, luego sin turno; dentro de cada grupo, alfabético.
  const RANK = { working: 0, on_break: 1, sin_turno: 2 };
  function ordered(people) {
    return [...arr(people)].sort((a, b) => (RANK[a.status] ?? 3) - (RANK[b.status] ?? 3) || String(a.name).localeCompare(String(b.name), "es", { sensitivity: "base" }));
  }

  // Pantalla completa (Fullscreen API y su variante webkit). Sin soporte, no hay botón.
  function fsOk() { return typeof document !== "undefined" && !!(document.fullscreenEnabled || document.webkitFullscreenEnabled); }
  function fsOn() { return typeof document !== "undefined" && !!(document.fullscreenElement || document.webkitFullscreenElement); }
  function fsToggle() {
    const d = document;
    const el = d.documentElement;
    try {
      const out = fsOn() ? (d.exitFullscreen || d.webkitExitFullscreen).call(d) : (el.requestFullscreen || el.webkitRequestFullscreen).call(el);
      if (out && out.catch) out.catch(() => {});
    } catch (_) {}
  }

  // ------------------------------------------------------------ vistas
  function logo() {
    const b = (st.board && st.board.brand) || {};
    return b.logo_url ? `<img class="crm-logo" src="${h(b.logo_url)}" alt="">` : `<span class="crm-logo crm-logo-txt" aria-hidden="true">${h(String(b.name || "V").slice(0, 1))}</span>`;
  }

  // Barra superior compacta: logo, empresa, CRM VELVET-LAB, chips y pantalla completa.
  function header() {
    const b = st.board || {};
    const on = fsOn();
    const fs = fsOk() ? `<button type="button" class="crm-fs" data-crm-fs aria-pressed="${on}" aria-label="${h(T(on ? "Salir de pantalla completa" : "Pantalla completa"))}">
      <span aria-hidden="true">${on ? "✕" : "⛶"}</span><span class="crm-fs-txt">${h(T(on ? "Salir de pantalla completa" : "Pantalla completa"))}</span></button>` : "";
    const chips = st.token && !st.mustChange && st.board ? `<p class="crm-chips">
      <span class="crm-chip is-working"><i aria-hidden="true">●</i> ${h(T("{n} trabajando", { n: b.working || 0 }))}</span>
      <span class="crm-chip is-on_break"><i aria-hidden="true">●</i> ${h(T("{n} en pausa", { n: b.paused || 0 }))}</span></p>` : "";
    return `<header class="crm-top">${logo()}<div class="crm-brand"><p class="crm-company">${h((b.brand && b.brand.name) || "")}</p><h1>CRM VELVET-LAB</h1></div>${chips}${fs}</header>`;
  }

  function loginView() {
    return `${header()}<div class="crm-scroll"><form class="crm-card crm-login" data-crm-login>
      <h2>${h(T("Ingreso del panel"))}</h2>
      <label>${h(T("Usuario"))}<input name="user" autocomplete="username" value="${h(st.login.user)}" required></label>
      <label>${h(T("Clave"))}<input name="pass" type="password" autocomplete="current-password" required></label>
      ${st.error ? `<p class="crm-error" role="alert">${h(st.error)}</p>` : ""}
      <button type="submit" class="crm-btn is-primary" ${st.busy ? "disabled" : ""}>${h(T("Entrar"))}</button></form></div>`;
  }

  function changeView() {
    return `${header()}<div class="crm-scroll"><form class="crm-card crm-login" data-crm-change>
      <h2>${h(T("Cambia la clave del panel"))}</h2>
      <label>${h(T("Clave actual"))}<input name="cur" type="password" autocomplete="current-password" required></label>
      <label>${h(T("Clave nueva"))}<input name="next" type="password" autocomplete="new-password" minlength="8" required></label>
      ${st.error ? `<p class="crm-error" role="alert">${h(st.error)}</p>` : ""}
      <button type="submit" class="crm-btn is-primary" ${st.busy ? "disabled" : ""}>${h(T("Guardar"))}</button></form></div>`;
  }

  const TAG = { working: "TRABAJANDO", on_break: "EN PAUSA", sin_turno: "SIN TURNO" };

  // 056L: tiempos del turno calculados en el servidor (worked/pause/connected_seconds al
  // momento de board.now); el navegador solo anima el segundero de lo que corre.
  function secs(s, withSeconds) {
    const v = Math.max(0, Math.floor(Number(s) || 0));
    const base = `${Math.floor(v / 3600)}:${String(Math.floor(v / 60) % 60).padStart(2, "0")}`;
    return withSeconds ? `${base}:${String(v % 60).padStart(2, "0")}` : base;
  }
  function since(s) { return new Date(new Date((st.board && st.board.now) || Date.now()).getTime() - Math.max(0, Number(s) || 0) * 1000).toISOString(); }
  function ticking(s, running, withSeconds, cls) {
    return running ? `<span class="${cls}" data-crm-clock="${h(since(s))}"${withSeconds ? "" : ' data-crm-fmt="hm"'}>${h(secs(s, withSeconds))}</span>`
      : `<span class="${cls}">${h(secs(s, withSeconds))}</span>`;
  }

  function timedBody(p, status) {
    const running = status === "working";
    const pause = status === "on_break"
      ? `<span class="crm-meta is-pausing">${h(T("En pausa"))} ${ticking(p.current_pause_seconds, true, false, "crm-meta-t")} · ${h(T("total pausas"))} ${ticking(p.pause_seconds, true, false, "crm-meta-t")}</span>`
      : `<span class="crm-meta">${h(T("Pausa"))} ${ticking(p.pause_seconds, false, false, "crm-meta-t")}</span>`;
    // El nombre de la referencia se recorta; su tiempo siempre se ve.
    const ref = p.reference_name ? `<span class="crm-meta crm-meta-ref"><span class="crm-meta-n">${h(T("Ref."))} ${h(p.reference_name)}</span>&nbsp;·&nbsp;${ticking(p.reference_worked_seconds, running, false, "crm-meta-t")}</span>`
      : `<span class="crm-meta crm-meta-ref">${h(T("Sin referencia"))}</span>`;
    const prev = p.previous_reference ? `<span class="crm-meta crm-meta-ref"><span class="crm-meta-n">${h(T("Anterior"))}: ${h(T("Ref."))} ${h(p.previous_reference.name)}</span>&nbsp;·&nbsp;<span class="crm-meta-t">${h(secs(p.previous_reference.worked_seconds))}</span></span>` : "";
    return `${pause}${ref}${prev}${ticking(p.worked_seconds, running, true, "crm-clock")}`;
  }

  function tile(p) {
    const status = TAG[p.status] ? p.status : "sin_turno";
    // En pausa, el tiempo en pausa; trabajando, el mismo dato de siempre (referencia o turno).
    const clock = status === "on_break" ? p.paused_since || p.since : p.since;
    const body = status === "sin_turno" ? `<span class="crm-hint">${h(T("Toca para iniciar"))}</span>`
      : p.worked_seconds != null ? timedBody(p, status)
      : `<span class="crm-ref">${h(p.reference_name || T("Sin referencia"))}</span><span class="crm-clock" data-crm-clock="${h(clock || "")}">${h(hms(clock))}</span>`;
    return `<li><button type="button" class="crm-tile is-${status}" data-crm-pick="${h(p.employee_id)}">
      <span class="crm-tag">${h(T(TAG[status]))}</span><span class="crm-name">${h(p.name)}</span>${body}</button></li>`;
  }

  // Pantalla principal = CRM en vivo: barra, buscador y cuadrícula por estado.
  function boardView() {
    const q = fold(st.query.trim());
    const people = ordered(st.board && st.board.people).filter((p) => !q || fold(p.name).includes(q));
    return `${header()}<div class="crm-tools">
      <input class="crm-search" type="search" placeholder="${h(T("Buscar colaborador"))}" aria-label="${h(T("Buscar colaborador"))}" value="${h(st.query)}" data-crm-search>
      <button type="button" class="crm-link" data-crm-logout>${h(T("Salir del panel"))}</button></div>
      ${st.error && !st.pinFor && st.view !== "person" ? `<p class="crm-error" role="alert">${h(st.error)}</p>` : ""}
      <ul class="crm-grid" aria-label="${h(T("Colaboradores"))}">${people.map(tile).join("") || `<li class="crm-empty">${h(T("Sin colaboradores activos."))}</li>`}</ul>`;
  }

  // Ventana sobre la pantalla principal: a la izquierda pasos, persona e instrucción
  // (y abajo los botones); a la derecha el teclado o la lista. En vertical, una columna.
  function dialog(side, main, foot, cls = "") {
    return `<div class="crm-modal" role="dialog" aria-modal="true" aria-labelledby="crmWinT"><div class="crm-win${cls ? ` ${cls}` : ""}">
      <div class="crm-side">${side}</div>${main ? `<div class="crm-main">${main}</div>` : ""}<div class="crm-foot">${foot}</div></div></div>`;
  }

  function who(p, tag = "") {
    const initials = String(p.name || "?").trim().split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    return `<div class="crm-who"><span class="crm-avatar" aria-hidden="true">${h(initials || "?")}</span><div><h2 id="crmWinT">${h(p.name || "")}</h2>${tag}</div></div>`;
  }

  const messages = () => `${st.error ? `<p class="crm-error" role="alert">${h(st.error)}</p>` : ""}${st.info ? `<p class="crm-ok" role="status">${h(st.info)}</p>` : ""}`;

  // Teclado 3 x 4 (1-9, Borrar, 0, OK). attr: data-crm-key (PIN) o data-crm-qkey (cantidad).
  function keypad(attr, okAttrs, okLabel, cls = "") {
    const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"];
    return `<div class="crm-keys${cls}">${keys.map((k) => {
      if (k === "OK") return `<button type="button" class="crm-key is-primary" ${okAttrs}>${h(okLabel)}</button>`;
      return `<button type="button" class="crm-key${k === "⌫" ? " is-soft" : ""}" ${attr}="${h(k)}" ${st.busy ? "disabled" : ""} aria-label="${h(k === "⌫" ? T("Borrar") : k)}">${h(k === "⌫" ? T("Borrar") : k)}</button>`;
    }).join("")}</div>`;
  }

  function pinView() {
    const p = arr(st.board && st.board.people).find((x) => x.employee_id === st.pinFor) || {};
    if (!p.has_pin) {
      return dialog(`${who(p)}<p class="crm-warn">${h(T("Pide tu PIN al administrador."))}</p>`, "",
        `<button type="button" class="crm-btn" data-crm-cancel>${h(T("Volver"))}</button>`, "is-single");
    }
    const side = `${p.status === "sin_turno" ? steps(1) : ""}${who(p)}<p class="crm-say">${h(T("Escribe tu PIN de 4 dígitos"))}</p>
      <p class="crm-dots" aria-label="${h(T("{n} de 4 dígitos", { n: st.pin.length }))}">${[0, 1, 2, 3].map((i) => `<i class="${i < st.pin.length ? "is-on" : ""}"></i>`).join("")}</p>
      ${st.error ? `<p class="crm-error" role="alert">${h(st.error)}</p>` : ""}`;
    const pad = keypad("data-crm-key", `data-crm-key="OK" ${st.busy ? "disabled" : ""} aria-label="${h(T("Entrar"))}"`, "OK");
    return dialog(side, pad, `<button type="button" class="crm-btn crm-cancel" data-crm-cancel>${h(T("✕ Cancelar"))}</button>`, "is-pin");
  }

  // Sin turno, primero la referencia: 1 · PIN → 2 · Referencia → 3 · Iniciar.
  function steps(current) {
    const names = ["PIN", "Referencia", "Iniciar"];
    return `<ol class="crm-steps" aria-label="${h(T("Pasos"))}">${names.map((n, i) => `<li class="${i + 1 === current ? "is-on" : i + 1 < current ? "is-done" : ""}" ${i + 1 === current ? 'aria-current="step"' : ""}>
      ${h(i + 1)} · ${h(T(n))}</li>`).join("")}</ol>`;
  }

  // Buscador más cuadrícula de referencias activas con su pendiente.
  function refGrid(attr, selected, query, searchAttr, radio) {
    const q = fold(String(query || "").trim());
    const refs = st.refs.filter((r) => !q || fold(r.name).includes(q));
    return `<input class="crm-search" type="search" placeholder="${h(T("Buscar referencia"))}" aria-label="${h(T("Buscar referencia"))}" value="${h(query || "")}" ${searchAttr}>
      <ul class="crm-refs"${radio ? ` role="radiogroup" aria-label="${h(T("Referencias activas"))}"` : ""}>${refs.map((r) => `<li><button type="button"${radio ? ` role="radio" aria-checked="${r.id === selected}"` : ""}
        class="crm-refopt${r.id === selected ? " is-on" : ""}" ${attr}="${h(r.id)}"><b>${h(r.name)}</b><small>${h(T("Pendiente {n}", { n: r.pending || 0 }))}</small></button></li>`).join("")
        || `<li class="crm-empty">${h(T("Sin referencias activas."))}</li>`}</ul>`;
  }

  function startView() {
    const p = st.person || {};
    const chosen = st.refs.find((r) => r.id === st.startRef);
    const side = `${steps(chosen ? 3 : 2)}${who(p, `<span class="crm-tag is-sin_turno">${h(T(TAG.sin_turno))}</span>`)}
      <p class="crm-say">${h(T("¿En qué vas a trabajar?"))}</p>${messages()}`;
    const foot = `<button type="button" class="crm-btn is-primary crm-startgo" data-crm-startgo ${!chosen || st.busy ? "disabled" : ""}>
        ${h(chosen ? T("▶ Iniciar turno en {ref}", { ref: chosen.name }) : T("Elige una referencia para iniciar"))}</button>
      <button type="button" class="crm-btn crm-cancel" data-crm-done>${h(T("✕ Cancelar"))}</button>`;
    return dialog(side, refGrid("data-crm-startref", st.startRef, st.refQuery, "data-crm-startsearch", true), foot, "crm-personal crm-start");
  }

  function personView() {
    const p = st.person || {};
    if (p.status === "sin_turno") return startView();
    const m = st.modal;
    const ref = p.reference;
    const tag = `<span class="crm-tag is-${h(p.status)}">${h(T(TAG[p.status] || ""))}</span>`;
    if (m && m.kind === "refs") {
      const side = `${who(p, tag)}<p class="crm-say">${h(T(m.action === "switch_reference" ? "Cambiar referencia" : "Iniciar referencia"))}</p>${messages()}`;
      return dialog(side, refGrid("data-crm-ref", "", m.query, "data-crm-refsearch", false),
        `<button type="button" class="crm-btn crm-cancel" data-crm-close>${h(T("✕ Cancelar"))}</button>`, "crm-personal");
    }
    if (m && m.kind === "close") {
      const sizes = arr(p.sizes);
      const sel = sizes.find((s) => s.reference_id === m.size);
      const side = `${who(p, tag)}<p class="crm-say">${h(T("Cerrar prendas"))} · ${h((ref || {}).name || "")}</p>
        <p class="crm-qtyline">${h(T("Talla"))} <b>${h(sel ? sel.size : "—")}</b> · ${h(T("Cantidad"))} <output class="crm-qty" data-crm-qtyshow>${h(m.qty || "0")}</output></p>
        ${m.over ? `<p class="crm-warn" role="alert">${h(T("Supera el pendiente de esa talla ({n}). ¿Confirmas?", { n: m.over }))}</p>` : ""}${messages()}`;
      const main = `<div class="crm-sizes" role="group" aria-label="${h(T("Elige la talla"))}">${sizes.map((s) => `<button type="button" class="crm-size${m.size === s.reference_id ? " is-on" : ""}" data-crm-size="${h(s.reference_id)}" aria-pressed="${m.size === s.reference_id}">
          <b>${h(s.size)}</b><small>${h(T("Pendiente {n}", { n: s.pending }))}</small></button>`).join("") || `<p class="crm-empty">${h(T("Esta referencia no tiene tallas activas."))}</p>`}</div>
        ${keypad("data-crm-qkey", `data-crm-closego ${!sel || st.busy ? "disabled" : ""}`, T(m.over ? "Sí, confirmar" : "Cerrar"), " is-qty")}`;
      return dialog(side, main, `<button type="button" class="crm-btn crm-cancel" data-crm-close>${h(T("✕ Cancelar"))}</button>`, "crm-personal is-close");
    }
    const btn = (a, label, primary) => `<button type="button" class="crm-btn${primary ? " is-primary" : ""}" data-crm-act="${a}" ${st.busy ? "disabled" : ""}>${h(T(label))}</button>`;
    let shift = "";
    if (p.status === "working") shift = `${btn("pause", "Pausa")}${btn("end_shift", "Fin de turno")}`;
    if (p.status === "on_break") shift = `${btn("resume", "Reanudar", true)}${btn("end_shift", "Fin de turno")}`;
    const work = ref ? `${btn("pick_switch", "Cambiar referencia")}${btn("pick_close", "Cerrar prendas", true)}` : btn("pick_start", "Iniciar referencia", true);
    const side = `${who(p, tag)}
      ${ref ? `<p class="crm-now"><span>🧵 <b>${h(ref.name)}</b></span><span class="crm-clock" data-crm-clock="${h(ref.started_at || "")}">${h(hms(ref.started_at))}</span></p>` : `<p class="crm-say">${h(T("Sin referencia"))}</p>`}
      ${messages()}`;
    return dialog(side, `<div class="crm-acts">${shift}${work}</div>`,
      `<button type="button" class="crm-btn crm-done" data-crm-done>${h(T("Listo · siguiente colaborador"))}</button>`, "crm-personal");
  }

  function view() {
    if (!CID) return `<div class="crm-scroll"><section class="crm-card crm-login"><p>${h(T("Falta la empresa en el enlace."))}</p></section></div>`;
    if (!st.token) return loginView();
    if (st.mustChange) return changeView();
    if (st.view === "person" && st.person) return `${boardView()}${personView()}`;
    return `${boardView()}${st.pinFor ? pinView() : ""}`;
  }

  function draw() {
    const root = typeof document !== "undefined" && document.getElementById("crmApp");
    if (!root) return;
    const active = document.activeElement;
    const keepSearch = active && active.hasAttribute && (active.hasAttribute("data-crm-search") || active.hasAttribute("data-crm-refsearch") || active.hasAttribute("data-crm-startsearch"));
    const attr = keepSearch ? [...active.attributes].map((a) => a.name).find((n) => n.startsWith("data-crm-")) : "";
    root.innerHTML = view();
    if (attr) { const el = root.querySelector(`[${attr}]`); if (el) { el.focus(); const v = el.value; el.value = ""; el.value = v; } }
  }

  // ------------------------------------------------------------ datos
  async function loadBoard() {
    try {
      st.board = await call(crm("/board"));
      st.offset = new Date(st.board.now).getTime() - Date.now();
      applyBrand(st.board.brand);
    } catch (error) {
      if (error.status === 401 || error.status === 403) { st.token = ""; store(KEY, ""); }
      st.error = error.message;
    }
  }

  async function loadRefs() {
    try { st.refs = arr((await call(crm("/references"))).items); } catch (_) { st.refs = []; }
  }

  function backToList() {
    st.view = "list"; st.person = null; st.empToken = ""; st.modal = null; st.pinFor = null; st.pin = ""; st.error = ""; st.info = ""; st.startRef = ""; st.refQuery = "";
  }

  async function act(action, extra = {}) {
    st.busy = true; st.error = ""; st.info = ""; draw();
    try {
      st.person = await call(crm("/action"), "POST", { action, ...extra }, true);
      st.modal = null;
      st.info = T("Listo: quedó registrado.");
      loadBoard().then(draw);
    } catch (error) {
      if (error.code === "supera_el_pendiente" && st.modal) { st.modal.over = (error.extra && error.extra.pending) || 0; }
      else if (error.code === "pide_el_pin_otra_vez") { const id = st.person && st.person.employee_id; backToList(); st.pinFor = id; st.error = error.message; }
      else st.error = error.message;
    }
    st.busy = false;
    draw();
  }

  async function submitPin() {
    if (st.pin.length !== 4) return;
    st.busy = true; st.error = ""; draw();
    try {
      const out = await call(crm("/unlock"), "POST", { employee_id: st.pinFor, pin: st.pin });
      st.empToken = out.employee_token; st.person = out.person; st.view = "person"; st.pinFor = null;
      await loadRefs();  // pendientes frescos para elegir referencia
    } catch (error) {
      st.error = error.code === "pin_incorrecto" && error.extra && error.extra.left !== undefined
        ? T("PIN incorrecto. Te quedan {n} intentos.", { n: error.extra.left }) : error.message;
    }
    st.pin = ""; st.busy = false;
    draw();
  }

  // ------------------------------------------------------------ eventos
  function touch() { st.lastTouch = Date.now(); }

  function onClick(e) {
    const t = e.target;
    if (!t || !t.closest) return;
    touch();
    const attr = (a) => { const el = t.closest(`[${a}]`); return el ? el.getAttribute(a) : null; };
    let v;
    if (t.closest("[data-crm-fs]")) { fsToggle(); return; }
    if (t.closest("[data-crm-logout]")) { st.token = ""; store(KEY, ""); backToList(); draw(); return; }
    if ((v = attr("data-crm-pick"))) { st.pinFor = v; st.pin = ""; st.error = ""; draw(); return; }
    if (t.closest("[data-crm-cancel]")) { st.pinFor = null; st.pin = ""; st.error = ""; draw(); return; }
    if ((v = attr("data-crm-key"))) {
      if (v === "⌫") st.pin = st.pin.slice(0, -1);
      else if (v === "OK") { submitPin(); return; }
      else if (st.pin.length < 4) st.pin += v;
      draw();
      if (st.pin.length === 4 && v !== "⌫") submitPin();
      return;
    }
    if (t.closest("[data-crm-done]")) { backToList(); draw(); return; }
    if ((v = attr("data-crm-act"))) {
      if (v === "pick_start" || v === "pick_switch") { st.modal = { kind: "refs", action: v === "pick_switch" ? "switch_reference" : "start_reference", query: "" }; draw(); return; }
      if (v === "pick_close") { st.modal = { kind: "close", size: (arr(st.person.sizes)[0] || {}).reference_id || "", qty: "", over: 0 }; draw(); return; }
      act(v);
      return;
    }
    if ((v = attr("data-crm-ref")) && st.modal) { act(st.modal.action, { reference_id: v }); return; }
    if ((v = attr("data-crm-startref"))) { st.startRef = st.startRef === v ? "" : v; st.error = ""; draw(); return; }
    if (t.closest("[data-crm-startgo]")) { if (st.startRef) act("start_shift", { reference_id: st.startRef }); return; }
    if ((v = attr("data-crm-size")) && st.modal) { st.modal.size = v; st.modal.over = 0; draw(); return; }
    if ((v = attr("data-crm-qkey")) && st.modal) {
      const qty = String(st.modal.qty || "");
      st.modal.qty = v === "⌫" ? qty.slice(0, -1) : `${qty}${v}`.replace(/^0+/, "").slice(0, 6);
      st.modal.over = 0; draw(); return;
    }
    if (t.closest("[data-crm-closego]") && st.modal) {
      act("close", { size_reference_id: st.modal.size, quantity: Number(st.modal.qty || 0), confirm: st.modal.over ? true : undefined });
      return;
    }
    if (t.closest("[data-crm-close]")) { st.modal = null; st.error = ""; draw(); }
  }

  function onInput(e) {
    const t = e.target;
    touch();
    if (t.hasAttribute && t.hasAttribute("data-crm-search")) { st.query = t.value; draw(); return; }
    if (t.hasAttribute && t.hasAttribute("data-crm-refsearch") && st.modal) { st.modal.query = t.value; draw(); return; }
    if (t.hasAttribute && t.hasAttribute("data-crm-startsearch")) { st.refQuery = t.value; draw(); return; }
  }

  async function onSubmit(e) {
    const f = e.target;
    if (!f || !f.hasAttribute) return;
    if (f.hasAttribute("data-crm-login")) {
      e.preventDefault();
      st.busy = true; st.error = ""; st.login.user = f.elements.namedItem("user").value; draw();
      try {
        const out = await call(`/companies/${encodeURIComponent(CID)}/mini-panel-login`, "POST",
          { username: st.login.user, password: f.elements.namedItem("pass").value, panel_type: "crm_lab", device_id: device() });
        st.token = out.access_token; store(KEY, st.token);
        st.mustChange = !!(out.user && out.user.must_change_password);
        await loadBoard();
      } catch (error) { st.error = error.message; }
      st.busy = false; draw();
      return;
    }
    if (f.hasAttribute("data-crm-change")) {
      e.preventDefault();
      st.busy = true; draw();
      try {
        await call(`/companies/${encodeURIComponent(CID)}/mini-panel-change-password?panel_type=crm_lab`, "POST",
          { current_password: f.elements.namedItem("cur").value, new_password: f.elements.namedItem("next").value, confirm_password: f.elements.namedItem("next").value });
        st.mustChange = false;
        await loadBoard();
      } catch (error) { st.error = error.message; }
      st.busy = false; draw();
    }
  }

  function loops() {
    setInterval(async () => {
      if (!st.token || st.mustChange) return;
      if (st.view === "list" && !st.pinFor) { await loadBoard(); draw(); }
    }, POLL_MS);
    setInterval(() => {
      // A los 20 s sin uso vuelve a la lista (para el siguiente colaborador).
      if ((st.view === "person" || st.pinFor) && Date.now() - st.lastTouch > IDLE_MS) { backToList(); draw(); }
      document.querySelectorAll("[data-crm-clock]").forEach((el) => {
        const text = hms(el.getAttribute("data-crm-clock"));
        el.textContent = el.getAttribute("data-crm-fmt") === "hm" ? text.replace(/:\d{2}$/, "") : text;
      });
    }, 1000);
  }

  async function start() {
    if (typeof document === "undefined" || !document.getElementById("crmApp")) return;
    document.addEventListener("click", onClick);
    document.addEventListener("input", onInput);
    document.addEventListener("submit", onSubmit);
    document.addEventListener("keydown", touch);
    document.addEventListener("fullscreenchange", draw);
    document.addEventListener("webkitfullscreenchange", draw);
    if (CID) {
      try { window.localStorage.setItem(COMPANY_KEY, CID); } catch (_) {}
      if (!P.get("company_id") && window.history && window.history.replaceState) window.history.replaceState(null, "", `${location.pathname}?company_id=${encodeURIComponent(CID)}`);
    }
    st.token = store(KEY);
    if (st.token) await loadBoard();
    draw();
    loops();
  }

  if (typeof window !== "undefined") {
    window.CxCrmLab = { st, view, hm, hms, ordered, palette, readableOn, contrast, backToList, steps, fsOk, IDLE_MS, ERRORS, STATUS };
    if (typeof document !== "undefined" && document.addEventListener) document.addEventListener("DOMContentLoaded", start);
  }
})();
