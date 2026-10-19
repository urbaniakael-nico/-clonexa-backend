// CRM VELVET-LAB · mini panel de UN usuario en la tableta del taller (interruptor
// crm_velvet_lab). Cada colaborador toca su nombre, escribe su PIN y registra turno
// (Iniciar / Pausa / Reanudar / Fin) y trabajo por referencia (Iniciar, Cambiar y
// Cerrar prendas por talla y cantidad). El servidor usa las MISMAS funciones del bot
// de Telegram (source_channel = crm_lab). A los 20 s sin uso vuelve a la lista.
// Liviano: un solo pedido al tablero cada 5 s. Textos por t().
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
  };
  const IDLE_MS = 20000;
  const POLL_MS = 5000;

  const P = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const CID = P.get("company_id") || "";
  const API = "/api/v1";
  const KEY = `clonexa_crm_lab_token_${CID}`;
  const DEVICE_KEY = `clonexa_crm_lab_device_${CID}`;

  const st = { token: "", board: null, refs: [], view: "list", query: "", pinFor: null, pin: "", person: null, empToken: "", modal: null,
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
  function since(iso) {
    if (!iso) return "";
    const ms = Date.now() + st.offset - new Date(iso).getTime();
    return hm(ms / 60000);
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

  // ------------------------------------------------------------ marca (panel inicial) y AA
  function rgb(hex) {
    const m = String(hex || "").trim().replace("#", "");
    const full = m.length === 3 ? m.split("").map((c) => c + c).join("") : m;
    return /^[0-9a-f]{6}$/i.test(full) ? [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16)) : null;
  }
  function lum(c) { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); }
  function contrast(a, b) { const x = lum(a) + 0.05; const y = lum(b) + 0.05; return Math.max(x, y) / Math.min(x, y); }
  function readableOn(bg) { return contrast([255, 255, 255], bg) >= contrast([17, 17, 17], bg) ? "#ffffff" : "#111111"; }
  function applyBrand(b) {
    if (!b || typeof document === "undefined") return;
    const root = document.documentElement.style;
    const primary = rgb(b.primary) || [124, 58, 237];
    root.setProperty("--crm-accent", `rgb(${primary.join(",")})`);
    root.setProperty("--crm-on-accent", readableOn(primary));
    const second = rgb(b.secondary);
    if (second) { root.setProperty("--crm-accent-2", `rgb(${second.join(",")})`); root.setProperty("--crm-on-accent-2", readableOn(second)); }
    if (b.language && b.language !== "es" && window.CxI18n && window.CxI18n.setLanguage) window.CxI18n.setLanguage(b.language);
  }

  // ------------------------------------------------------------ vistas
  function header() {
    const b = (st.board && st.board.brand) || {};
    const logo = b.logo_url ? `<img class="crm-logo" src="${h(b.logo_url)}" alt="">` : `<span class="crm-logo crm-logo-txt">${h(String(b.name || "V").slice(0, 1))}</span>`;
    return `<header class="crm-head">${logo}<div><p class="crm-company">${h(b.name || "")}</p><h1>CRM VELVET-LAB</h1></div>
      ${st.token ? `<button type="button" class="crm-link" data-crm-logout>${h(T("Salir del panel"))}</button>` : ""}</header>`;
  }

  function loginView() {
    return `${header()}<form class="crm-card crm-login" data-crm-login>
      <h2>${h(T("Ingreso del panel"))}</h2>
      <label>${h(T("Usuario"))}<input name="user" autocomplete="username" value="${h(st.login.user)}" required></label>
      <label>${h(T("Clave"))}<input name="pass" type="password" autocomplete="current-password" required></label>
      <button type="submit" class="crm-btn is-primary" ${st.busy ? "disabled" : ""}>${h(T("Entrar"))}</button></form>`;
  }

  function changeView() {
    return `${header()}<form class="crm-card crm-login" data-crm-change>
      <h2>${h(T("Cambia la clave del panel"))}</h2>
      <label>${h(T("Clave actual"))}<input name="cur" type="password" autocomplete="current-password" required></label>
      <label>${h(T("Clave nueva"))}<input name="next" type="password" autocomplete="new-password" minlength="8" required></label>
      <button type="submit" class="crm-btn is-primary" ${st.busy ? "disabled" : ""}>${h(T("Guardar"))}</button></form>`;
  }

  function liveStrip() {
    const b = st.board || {};
    const live = arr(b.live);
    return `<section class="crm-live" aria-label="${h(T("En vivo"))}">
      <p class="crm-counts"><b>${h(b.working || 0)}</b> ${h(T("trabajando"))} · <b>${h(b.paused || 0)}</b> ${h(T("en pausa"))}</p>
      <ul class="crm-ribbon">${live.map((p) => `<li class="is-${h(p.status)}"><i aria-hidden="true"></i><b>${h(p.name)}</b>
        <span>${h(p.reference_name || T("Sin referencia"))}</span><small data-crm-since="${h(p.since || "")}">${h(since(p.since))}</small></li>`).join("")
        || `<li class="crm-empty">${h(T("Nadie trabajando ahora."))}</li>`}</ul></section>`;
  }

  function listView() {
    const q = st.query.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    const people = arr(st.board && st.board.people).filter((p) => !q || String(p.name).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").includes(q));
    return `${header()}${liveStrip()}<section class="crm-card" aria-labelledby="crmPeople">
      <div class="crm-row"><h2 id="crmPeople">${h(T("Colaboradores"))}</h2>
        <input class="crm-search" type="search" placeholder="${h(T("Buscar colaborador"))}" aria-label="${h(T("Buscar colaborador"))}" value="${h(st.query)}" data-crm-search></div>
      <ul class="crm-people">${people.map((p) => `<li><button type="button" class="crm-person is-${h(p.status)}" data-crm-pick="${h(p.employee_id)}">
        <span class="crm-name">${h(p.name)}</span><span class="crm-pill is-${h(p.status)}">${h(T(STATUS[p.status] || p.status))}</span>
        ${p.reference_name ? `<small>${h(p.reference_name)} · ${h(since(p.since))}</small>` : ""}</button></li>`).join("")
        || `<li class="crm-empty">${h(T("Sin colaboradores activos."))}</li>`}</ul></section>`;
  }

  function pinView() {
    const p = arr(st.board && st.board.people).find((x) => x.employee_id === st.pinFor) || {};
    if (!p.has_pin) {
      return `<div class="crm-modal" role="dialog" aria-modal="true" aria-labelledby="crmPinT"><div class="crm-card crm-pin">
        <h2 id="crmPinT">${h(p.name || "")}</h2><p class="crm-warn">${h(T("Pide tu PIN al administrador."))}</p>
        <button type="button" class="crm-btn" data-crm-cancel>${h(T("Volver"))}</button></div></div>`;
    }
    const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"];
    return `<div class="crm-modal" role="dialog" aria-modal="true" aria-labelledby="crmPinT"><div class="crm-card crm-pin">
      <h2 id="crmPinT">${h(p.name || "")}</h2><p>${h(T("Escribe tu PIN de 4 dígitos"))}</p>
      <p class="crm-dots" aria-label="${h(T("{n} de 4 dígitos", { n: st.pin.length }))}">${[0, 1, 2, 3].map((i) => `<i class="${i < st.pin.length ? "is-on" : ""}"></i>`).join("")}</p>
      ${st.error ? `<p class="crm-error" role="alert">${h(st.error)}</p>` : ""}
      <div class="crm-keys">${keys.map((k) => `<button type="button" class="crm-key${k === "OK" ? " is-primary" : ""}" data-crm-key="${h(k)}" ${st.busy ? "disabled" : ""}
        aria-label="${h(k === "⌫" ? T("Borrar") : k === "OK" ? T("Entrar") : k)}">${h(k === "OK" ? T("Entrar") : k)}</button>`).join("")}</div>
      <button type="button" class="crm-btn" data-crm-cancel>${h(T("Cancelar"))}</button></div></div>`;
  }

  function personView() {
    const p = st.person || {};
    const ref = p.reference;
    const btn = (a, label, primary) => `<button type="button" class="crm-btn crm-big${primary ? " is-primary" : ""}" data-crm-act="${a}" ${st.busy ? "disabled" : ""}>${h(T(label))}</button>`;
    let shift = "";
    if (p.status === "sin_turno") shift = btn("start_shift", "Iniciar turno", true);
    if (p.status === "working") shift = `${btn("pause", "Pausa")}${btn("end_shift", "Fin de turno")}`;
    if (p.status === "on_break") shift = `${btn("resume", "Reanudar", true)}${btn("end_shift", "Fin de turno")}`;
    const work = p.status === "sin_turno" ? `<p class="crm-muted">${h(T("Inicia tu turno para registrar referencias."))}</p>`
      : ref ? `${btn("pick_switch", "Cambiar referencia")}${btn("pick_close", "Cerrar prendas", true)}` : btn("pick_start", "Iniciar referencia", true);
    return `${header()}<section class="crm-card crm-personal" aria-labelledby="crmMe">
      <div class="crm-row"><h2 id="crmMe">${h(p.name || "")}</h2><span class="crm-pill is-${h(p.status)}">${h(T(STATUS[p.status] || ""))}</span></div>
      ${ref ? `<p class="crm-now">🧵 <b>${h(ref.name)}</b> · ${h(since(ref.started_at))}</p>` : ""}
      ${st.error ? `<p class="crm-error" role="alert">${h(st.error)}</p>` : ""}${st.info ? `<p class="crm-ok" role="status">${h(st.info)}</p>` : ""}
      <h3>${h(T("Turno"))}</h3><div class="crm-actions">${shift}</div>
      <h3>${h(T("Referencia"))}</h3><div class="crm-actions">${work}</div>
      <button type="button" class="crm-btn crm-done" data-crm-done>${h(T("Listo · siguiente colaborador"))}</button></section>${modalView()}`;
  }

  function modalView() {
    const m = st.modal;
    if (!m) return "";
    if (m.kind === "refs") {
      const q = (m.query || "").toLowerCase();
      const refs = st.refs.filter((r) => !q || String(r.name).toLowerCase().includes(q));
      return `<div class="crm-modal" role="dialog" aria-modal="true" aria-labelledby="crmRefT"><div class="crm-card crm-sheet">
        <h2 id="crmRefT">${h(T(m.action === "switch_reference" ? "Cambiar referencia" : "Iniciar referencia"))}</h2>
        <input class="crm-search" type="search" placeholder="${h(T("Buscar referencia"))}" aria-label="${h(T("Buscar referencia"))}" value="${h(m.query || "")}" data-crm-refsearch>
        <ul class="crm-list">${refs.map((r) => `<li><button type="button" class="crm-btn" data-crm-ref="${h(r.id)}">${h(r.name)}</button></li>`).join("")
          || `<li class="crm-empty">${h(T("Sin referencias activas."))}</li>`}</ul>
        <button type="button" class="crm-btn" data-crm-close>${h(T("Cancelar"))}</button></div></div>`;
    }
    const sizes = arr(st.person && st.person.sizes);
    const sel = sizes.find((s) => s.reference_id === m.size);
    return `<div class="crm-modal" role="dialog" aria-modal="true" aria-labelledby="crmCloseT"><div class="crm-card crm-sheet">
      <h2 id="crmCloseT">${h(T("Cerrar prendas"))} · ${h((st.person.reference || {}).name || "")}</h2>
      <p>${h(T("Elige la talla"))}</p>
      <div class="crm-sizes">${sizes.map((s) => `<button type="button" class="crm-size${m.size === s.reference_id ? " is-on" : ""}" data-crm-size="${h(s.reference_id)}" aria-pressed="${m.size === s.reference_id}">
        <b>${h(s.size)}</b><small>${h(T("Pendiente {n}", { n: s.pending }))}</small></button>`).join("") || `<p class="crm-empty">${h(T("Esta referencia no tiene tallas activas."))}</p>`}</div>
      <label class="crm-qty">${h(T("Cantidad"))}<input type="number" min="1" max="100000" inputmode="numeric" value="${h(m.qty || "")}" data-crm-qty></label>
      ${m.over ? `<p class="crm-warn" role="alert">${h(T("Supera el pendiente de esa talla ({n}). ¿Confirmas?", { n: m.over }))}</p>` : ""}
      ${st.error ? `<p class="crm-error" role="alert">${h(st.error)}</p>` : ""}
      <div class="crm-actions"><button type="button" class="crm-btn is-primary crm-big" data-crm-closego ${!sel || st.busy ? "disabled" : ""}>${h(T(m.over ? "Sí, confirmar" : "Cerrar prendas"))}</button>
        <button type="button" class="crm-btn" data-crm-close>${h(T("Cancelar"))}</button></div></div></div>`;
  }

  function view() {
    if (!CID) return `<section class="crm-card"><p>${h(T("Falta la empresa en el enlace."))}</p></section>`;
    if (!st.token) return loginView();
    if (st.mustChange) return changeView();
    if (st.view === "person" && st.person) return personView();
    return `${listView()}${st.pinFor ? pinView() : ""}`;
  }

  function draw() {
    const root = typeof document !== "undefined" && document.getElementById("crmApp");
    if (!root) return;
    const active = document.activeElement;
    const keepSearch = active && active.hasAttribute && (active.hasAttribute("data-crm-search") || active.hasAttribute("data-crm-refsearch") || active.hasAttribute("data-crm-qty"));
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
    st.view = "list"; st.person = null; st.empToken = ""; st.modal = null; st.pinFor = null; st.pin = ""; st.error = ""; st.info = "";
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
      if (!st.refs.length) await loadRefs();
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
    if ((v = attr("data-crm-size")) && st.modal) { st.modal.size = v; st.modal.over = 0; draw(); return; }
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
    if (t.hasAttribute && t.hasAttribute("data-crm-qty") && st.modal) { st.modal.qty = t.value; st.modal.over = 0; }
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
      document.querySelectorAll("[data-crm-since]").forEach((el) => { el.textContent = since(el.getAttribute("data-crm-since")); });
    }, 1000);
  }

  async function start() {
    if (typeof document === "undefined" || !document.getElementById("crmApp")) return;
    document.addEventListener("click", onClick);
    document.addEventListener("input", onInput);
    document.addEventListener("submit", onSubmit);
    document.addEventListener("keydown", touch);
    st.token = store(KEY);
    if (st.token) await loadBoard();
    draw();
    loops();
  }

  if (typeof window !== "undefined") {
    window.CxCrmLab = { st, view, hm, readableOn, contrast, backToList, IDLE_MS, ERRORS, STATUS };
    if (typeof document !== "undefined" && document.addEventListener) document.addEventListener("DOMContentLoaded", start);
  }
})();
