// Mini panel "Líder de operación" (064B): CRM Campo y Reportes de UNA operación, solo lectura.
// Esta pantalla no decide nada: la operación sale de la sesión y el servidor filtra siempre.
// Aquí no hay botones de escritura; aunque los hubiera, el servidor responde 403.
//
// Flecha atrás: cada pantalla es una entrada del historial, misma página y misma sesión:
//   [guard] [inicio] [crm] [reportes] [reportes + persona] ...
// Inicio siempre es la entrada 1. Atrás desde ella cae en guard: el panel vuelve a poner Inicio y
// pregunta "¿Salir del panel?". Al entrar, el formulario se reemplaza por guard: nunca se vuelve a él.
(() => {
  "use strict";

  const API = "/api/v1";
  const CRM_MS = 30000;
  const HOME_MS = 60000;
  const LANG_KEY = "cx_lider_lang";
  const params = new URLSearchParams(window.location.search);
  const CID = params.get("company_id") || "";
  const BOOT = window.__CX_LIDER__ && typeof window.__CX_LIDER__ === "object" ? window.__CX_LIDER__ : { ok: false };
  const TOKEN_KEY = `clonexa_mini_panel_token_${CID}_lider_operacion_${BOOT.slug || ""}`;
  const CHIPS = [["all", "Todos"], ["working", "Trabajando"], ["on_break", "En pausa"], ["no_shift", "Sin turno"], ["to_confirm", "Por confirmar"]];
  const MARK = { in: "Entrada", pause: "Pausa", resume: "Retomar", out: "Salida" };

  const st = { tab: "inicio", person: "", depth: 1, confirmExit: false, boardReady: false, busy: false, notice: "", home: null, crm: null, crmStale: false, query: "", chip: "all", updated: "" };
  let homeTimer = null;
  let crmTimer = null;
  let clockTimer = null;

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => Number(v || 0) || 0;
  const T = (s, vars) => (window.CxI18n && window.CxI18n.t ? window.CxI18n.t(s, vars) : String(s).replace(/\{(\w+)\}/g, (m, k) => (vars && vars[k] !== undefined ? vars[k] : m)));
  const norm = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  const hm = (minutes) => { const m = Math.max(0, Math.round(num(minutes))); return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`; };

  // ------------------------------------------------------------ idioma
  function savedLang() {
    let saved = "";
    try { saved = window.localStorage.getItem(LANG_KEY) || ""; } catch (_) { /* sin almacenamiento */ }
    if (saved === "es" || saved === "en") return saved;
    return String(navigator.language || "").toLowerCase().startsWith("en") ? "en" : "es";
  }
  const lang = () => (window.CxI18n && window.CxI18n.lang ? window.CxI18n.lang() : "es");
  function setLang(value, remember = true) {
    if (window.CxI18n) window.CxI18n.setLanguage(value);
    document.documentElement.setAttribute("lang", value);
    if (remember) { try { window.localStorage.setItem(LANG_KEY, value); } catch (_) { /* sin almacenamiento */ } }
  }
  const homeWord = () => (lang() === "en" ? "Home" : "Inicio");

  // Lo que responde el servidor viene en español.
  function serverText(detail) {
    const text = String(detail || "");
    const only = text.match(/^Este panel es solo para el líder de (.+)$/);
    return only ? T("Este panel es solo para el líder de {op}", { op: only[1] }) : T(text);
  }

  // ------------------------------------------------------------ sesión y datos
  function token() { try { return window.sessionStorage.getItem(TOKEN_KEY) || ""; } catch (_) { return ""; } }
  function setToken(value) {
    try { if (value) window.sessionStorage.setItem(TOKEN_KEY, value); else window.sessionStorage.removeItem(TOKEN_KEY); } catch (_) { /* sin almacenamiento */ }
  }
  const panelUrl = (path) => `${API}/lider-operacion/companies/${encodeURIComponent(CID)}/${path}`;

  function stopTimers() {
    if (homeTimer) clearInterval(homeTimer);
    if (crmTimer) clearInterval(crmTimer);
    homeTimer = null;
    crmTimer = null;
  }

  function sessionLost(message) {
    setToken("");
    stopTimers();
    Object.assign(st, { tab: "inicio", person: "", confirmExit: false, boardReady: false, home: null, crm: null, busy: false, notice: message || "Tu sesión terminó. Vuelve a entrar." });
    window.history.replaceState(LOGIN_ENTRY, "");
    draw();
  }

  // ------------------------------------------------------------ historial
  const LOGIN_ENTRY = { lo: 1, screen: "login" };
  const GUARD_ENTRY = { lo: 1, screen: "guard", depth: 0 };
  const entry = (screen, person, depth) => ({ lo: 1, screen, person: person || "", depth });

  function pushScreen(screen, person = "") {
    st.depth += 1;
    window.history.pushState(entry(screen, person, st.depth), "");
  }

  function toTop() { if (window.scrollTo) window.scrollTo(0, 0); }

  // Dibuja una pantalla sin tocar el historial.
  function show(screen, person = "") {
    const sameBoard = st.tab === "reportes" && screen === "reportes";
    st.tab = screen;
    st.person = person || "";
    if (sameBoard && window.CxReportsBoard) { window.CxReportsBoard.setOpen(st.person); return; }
    draw();
    toTop();
    if (screen === "inicio") loadHome();
    if (screen === "crm") loadCrm();
  }

  // Desde la barra o las tarjetas. Inicio no se apila: es volver a la entrada 1.
  function go(screen) {
    if (screen === "inicio") {
      if (st.depth > 1) window.history.go(1 - st.depth);
      else show("inicio");
      return;
    }
    if (st.tab === screen && !st.person) return;
    pushScreen(screen);
    show(screen);
  }

  function onPop(event) {
    if (!token()) {
      window.history.replaceState(LOGIN_ENTRY, "");
      st.confirmExit = false;
      draw();
      return;
    }
    const state = event.state;
    if (!state || !state.lo || state.screen === "guard" || state.screen === "login") {
      st.depth = 1;
      window.history.pushState(entry("inicio", "", 1), "");
      st.confirmExit = true;
      st.tab = "inicio";
      st.person = "";
      draw();
      return;
    }
    st.depth = Number(state.depth) || 1;
    st.confirmExit = false;
    show(state.screen, state.person);
  }

  function enterHistory() {
    window.history.replaceState(GUARD_ENTRY, "");
    st.depth = 1;
    window.history.pushState(entry("inicio", "", 1), "");
    st.tab = "inicio";
    st.person = "";
  }

  async function read(path) {
    const res = await fetch(panelUrl(path), { headers: { Authorization: `Bearer ${token()}` } });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403) { sessionLost(data.detail); return null; }
    if (!res.ok) throw new Error(data.detail || String(res.status));
    return data;
  }

  async function loadHome() {
    try {
      const data = await read("inicio");
      if (data) { st.home = data; applyAccent(); if (st.tab === "inicio") draw(); }
    } catch (_) {
      if (!st.home) st.notice = "No se pudo actualizar. Revisa la conexión.";
      if (st.tab === "inicio") draw();
    }
  }

  async function loadCrm() {
    try {
      const data = await read("crm");
      if (!data) return;
      st.crm = data;
      st.crmStale = false;
      st.updated = data.operation.local_time;
    } catch (_) { st.crmStale = true; }
    if (st.tab === "crm") drawCrmBody();
  }

  function startTimers() {
    stopTimers();
    homeTimer = setInterval(() => { if (st.tab === "inicio" && !document.hidden && token()) loadHome(); }, HOME_MS);
    crmTimer = setInterval(() => { if (st.tab === "crm" && !document.hidden && token()) loadCrm(); }, CRM_MS);
  }

  // ------------------------------------------------------------ reglas de pantalla
  function operation() {
    const live = st.home && st.home.operation;
    return live || { name: BOOT.name || "", accent: BOOT.accent, abbr: BOOT.abbr || "", timezone: BOOT.timezone || "" };
  }
  function filterPeople(people, query, chip) {
    const q = norm(query);
    return arr(people).filter((p) => (chip === "all" || p.state === chip) && (!q || norm(p.name).includes(q) || norm(p.role).includes(q)));
  }
  function stateChip(p) {
    if (p.state === "working") return { cls: "is-working", text: `${T("Trabajando")} ${hm(p.minutes)}` };
    if (p.state === "on_break") return { cls: "is-break", text: `${T("En pausa")} ${hm(p.minutes)}` };
    if (p.state === "to_confirm") return { cls: "is-confirm", text: p.minutes ? `${T("Por confirmar")} ${hm(p.minutes)}` : T("Por confirmar") };
    if (p.end) return { cls: "is-off", text: `${T("Terminó")} ${p.end.t} ${p.end.a}` };
    return { cls: "is-off", text: T("Sin turno") };
  }
  function clock(zone) {
    try { return new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date()); } catch (_) { return ""; }
  }

  // ------------------------------------------------------------ vistas
  function langPicker() {
    const now = lang();
    return `<div class="lo-lang" role="group" aria-label="${h(T("Idioma"))}">${[["es", "Español"], ["en", "English"]].map(([k, l]) =>
      `<button type="button" data-no-i18n data-lo-lang="${k}" class="${now === k ? "is-on" : ""}" aria-pressed="${now === k}">${l}</button>`).join("")}</div>`;
  }

  function header() {
    const op = operation();
    const logo = BOOT.brand && /^(https:|data:image\/|\/)/.test(String(BOOT.brand.logo_url || "")) ? `<img class="lo-logo" src="${h(BOOT.brand.logo_url)}" alt="">` : "";
    return `<header class="lo-head">${logo}<div class="lo-head-text"><p class="lo-kicker">${h(T("Líder de operación"))}</p><h1 data-no-i18n>${h(op.name)}</h1></div>${langPicker()}</header>`;
  }

  function loginView() {
    if (!BOOT.ok) {
      return `<main class="lo-login"><section class="lo-card"><div class="lo-lang-row">${langPicker()}</div><h1>${h(T("Líder de operación"))}</h1><p role="alert">${h(T("Este enlace no es válido. Pide el enlace de tu operación."))}</p></section></main>`;
    }
    return `${header()}<main class="lo-login"><form class="lo-card" data-lo-login autocomplete="on">
      ${st.notice ? `<p class="lo-error" role="alert">${h(serverText(st.notice))}</p>` : ""}
      <label>${h(T("Usuario"))}<input name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required></label>
      <label>${h(T("Clave"))}<input name="password" type="password" autocomplete="current-password" required></label>
      <button type="submit" class="lo-primary" ${st.busy ? "disabled" : ""}>${h(T(st.busy ? "Entrando…" : "Entrar"))}</button>
    </form></main>`;
  }

  function tile(label, value, cls = "") { return `<div class="lo-tile ${cls}"><span>${h(T(label))}</span><strong>${h(value)}</strong></div>`; }

  function homeView(home = st.home) {
    if (!home) return `<main class="lo-main"><p class="lo-card" role="status">${h(T(st.notice || "Cargando…"))}</p></main>`;
    const op = home.operation;
    const crm = home.crm || {};
    const rep = home.reports || {};
    const people = num(crm.total) === 1 ? T("1 persona") : T("{n} personas", { n: num(crm.total) });
    return `<main class="lo-main lo-home">
      <section class="lo-hello"><h2 data-no-i18n>${h(T("Hola, {name}", { name: home.me.name }))}</h2><p data-no-i18n>${h(T(home.me.role))} · <span>${h(people)}</span></p>
        <p class="lo-clock" aria-label="${h(T("Hora local"))}"><span data-lo-clock="${h(op.timezone)}">${h(clock(op.timezone) || op.local_time)}</span> ${h(op.abbr)}</p></section>
      <div class="lo-cards">
        <button type="button" class="lo-module" data-lo-tab="crm"><h3>${h(T("CRM Campo"))}</h3><div class="lo-tiles">${tile("Trabajando", num(crm.working))}${tile("En pausa", num(crm.on_break))}${tile("Sin turno", num(crm.no_shift))}</div></button>
        <button type="button" class="lo-module" data-lo-tab="reportes"><h3>${h(T("Reportes"))}</h3><div class="lo-tiles">${tile("Horas de la semana", hm(rep.hours_minutes))}${tile("Alertas", num(rep.alerts), num(rep.alerts) ? "is-warn" : "")}${tile("Notas de hoy", num(rep.notes_today))}</div></button>
      </div>
      <p class="lo-scope">${h(T("Este panel solo muestra {op}. Nómina, tarifas y la otra operación no están disponibles aquí.", { op: op.name }))}</p>
    </main>`;
  }

  function personRow(p) {
    const chip = stateChip(p);
    const mark = p.last_mark;
    const last = mark
      ? `${T("Última marca")}: ${T(MARK[mark.k] || mark.label)} ${mark.t} ${mark.a}${mark.place ? ` · ${T(mark.place)}` : ""}`
      : T("Sin marcas recientes");
    return `<li class="lo-person"><div class="lo-person-who"><b data-no-i18n>${h(p.name)}</b>${p.role ? `<small>${h(T(p.role))}</small>` : ""}<small data-no-i18n>${h(last)}</small></div>
      <span class="lo-state ${chip.cls}" data-no-i18n>${h(chip.text)}</span></li>`;
  }

  function crmList(crm = st.crm) {
    if (!crm) return `<p class="lo-card" role="status">${h(T("Cargando…"))}</p>`;
    const list = filterPeople(crm.people, st.query, st.chip);
    const counts = crm.counts || {};
    const count = (k) => (k === "all" ? num(counts.total) : num(counts[k]));
    return `<div class="lo-chips" role="group">${CHIPS.map(([k, l]) => `<button type="button" class="lo-chip ${st.chip === k ? "is-on" : ""}" data-lo-chip="${k}" aria-pressed="${st.chip === k}"><span>${h(T(l))}</span> <b>${count(k)}</b></button>`).join("")}</div>
      ${st.crmStale ? `<p class="lo-error" role="alert">${h(T("No se pudo actualizar. Revisa la conexión."))}</p>` : ""}
      ${list.length ? `<ul class="lo-people">${list.map(personRow).join("")}</ul>` : `<p class="lo-card">${h(T("Ninguna persona coincide."))}</p>`}`;
  }

  function crmView() {
    return `<main class="lo-main lo-crm"><div class="lo-crm-top"><h2>${h(T("CRM Campo"))}</h2><span class="lo-live" data-lo-updated role="status">${h(st.updated ? T("Actualizado {t}", { t: `${st.updated} ${operation().abbr}` }) : T("En vivo"))}</span></div>
      <input class="lo-search" type="search" data-lo-search value="${h(st.query)}" placeholder="${h(T("Buscar persona"))}" aria-label="${h(T("Buscar persona"))}" autocomplete="off">
      <div data-lo-crm-body>${crmList()}</div></main>`;
  }

  function nav() {
    const items = [["inicio", homeWord()], ["crm", "CRM"], ["reportes", T("Reportes")]];
    return `<nav class="lo-nav" aria-label="${h(T("Navegación"))}">${items.map(([k, l]) => `<button type="button" data-no-i18n data-lo-tab="${k}" class="${st.tab === k ? "is-on" : ""}" ${st.tab === k ? 'aria-current="page"' : ""}>${h(l)}</button>`).join("")}
      <button type="button" data-lo-exit>${h(T("Salir"))}</button></nav>`;
  }

  function exitDialog() {
    return `<div class="lo-modal"><div class="lo-dialog" role="alertdialog" aria-modal="true" aria-labelledby="loExitTitle">
      <h2 id="loExitTitle">${h(T("¿Salir del panel?"))}</h2>
      <div class="lo-dialog-actions"><button type="button" data-lo-exit-no>${h(T("No"))}</button><button type="button" class="lo-primary" data-lo-exit-yes>${h(T("Sí"))}</button></div>
    </div></div>`;
  }

  function panelView() {
    const body = st.tab === "crm" ? crmView() : st.tab === "reportes" ? `<main class="lo-main lo-reports"><div id="loBoardHost"></div></main>` : homeView();
    return `${header()}${body}${nav()}${st.confirmExit ? exitDialog() : ""}`;
  }

  // ------------------------------------------------------------ dibujo
  const appEl = () => document.getElementById("loApp");

  function applyAccent() {
    const el = appEl();
    if (!el) return;
    const accent = operation().accent;
    el.className = `lo-app lo-a${accent === 0 || accent === 1 ? accent : "x"}`;
  }

  function applyBrand() {
    const b = BOOT.brand || {};
    const root = document.documentElement.style;
    root.setProperty("--cx-bg", b.background_color || "#0f172a");
    root.setProperty("--cx-text", b.text_color || "#ffffff");
    root.setProperty("--cx-primary", b.primary_color || "#1e293b");
    root.setProperty("--cx-secondary", b.secondary_color || b.primary_color || "#334155");
    if (b.font_family) root.setProperty("--lo-font", `"${String(b.font_family).replace(/["\\]/g, "")}", Inter, "Segoe UI", system-ui, sans-serif`);
  }

  function mountBoard() {
    if (!window.CxReportsBoard) return;
    const mounted = window.CxReportsBoard.mount({
      companyId: CID, apiBase: API, baseUrl: panelUrl("reportes"), token, readonly: true,
      host: () => document.getElementById("loBoardHost"), back: () => {},
      today: () => (st.home && st.home.operation && st.home.operation.local_date) || "",
      onLost: () => sessionLost(),
      keep: st.boardReady,
      // Abrir o cerrar una persona es una entrada más del historial.
      onOpen: (id) => { st.person = id || ""; pushScreen("reportes", st.person); },
    });
    st.boardReady = true;
    if (!st.person) return;
    const wanted = st.person;
    Promise.resolve(mounted).then(() => { if (st.tab === "reportes" && st.person === wanted) window.CxReportsBoard.setOpen(wanted); });
  }

  function draw() {
    const el = appEl();
    if (!el) return;
    applyAccent();
    el.innerHTML = token() ? panelView() : loginView();
    if (window.CxReportsBoard) window.CxReportsBoard.applyContrast(el);
    if (token() && st.tab === "reportes") mountBoard();
    if (st.confirmExit) { const no = document.querySelector("[data-lo-exit-no]"); if (no) no.focus(); }
  }

  function drawCrmBody() {
    const box = document.querySelector("[data-lo-crm-body]");
    if (!box) { draw(); return; }
    box.innerHTML = crmList();
    const updated = document.querySelector("[data-lo-updated]");
    if (updated && st.updated) updated.textContent = T("Actualizado {t}", { t: `${st.updated} ${operation().abbr}` });
  }

  function tickClock() {
    document.querySelectorAll("[data-lo-clock]").forEach((node) => { const value = clock(node.getAttribute("data-lo-clock")); if (value) node.textContent = value; });
  }

  // ------------------------------------------------------------ eventos
  async function exit() {
    const current = token();
    setToken("");
    stopTimers();
    Object.assign(st, { tab: "inicio", person: "", confirmExit: false, boardReady: false, home: null, crm: null, notice: "", query: "", chip: "all" });
    window.history.replaceState(LOGIN_ENTRY, "");
    draw();
    if (current) { try { await fetch(`${API}/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${current}` } }); } catch (_) { /* el corte diario la cierra */ } }
  }

  function onClick(event) {
    const t = event.target;
    if (!t || !t.closest) return;
    const attr = (name) => { const el = t.closest(`[${name}]`); return el ? el.getAttribute(name) : null; };
    let v;
    if ((v = attr("data-lo-lang"))) { setLang(v); draw(); return; }
    if ((v = attr("data-lo-tab"))) { go(v); return; }
    if (t.closest("[data-lo-exit-no]")) { st.confirmExit = false; draw(); return; }
    if (t.closest("[data-lo-exit-yes]")) { exit(); return; }
    if ((v = attr("data-lo-chip"))) { st.chip = v; drawCrmBody(); return; }
    if (t.closest("[data-lo-exit]")) exit();
  }

  function onInput(event) {
    if (event.target && event.target.hasAttribute && event.target.hasAttribute("data-lo-search")) { st.query = event.target.value; drawCrmBody(); }
  }

  async function onSubmit(event) {
    const form = event.target;
    if (!form || !form.hasAttribute || !form.hasAttribute("data-lo-login")) return;
    event.preventDefault();
    const username = form.elements.namedItem("username").value;
    const password = form.elements.namedItem("password").value;
    st.busy = true;
    st.notice = "";
    draw();
    const again = form.ownerDocument.querySelector("[data-lo-login]");
    if (again) again.elements.namedItem("username").value = username;
    try {
      const res = await fetch(`${API}/companies/${encodeURIComponent(CID)}/mini-panel-login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, panel_type: "lider_operacion", lugar: BOOT.slug }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { st.notice = data.detail || "No se pudo actualizar. Revisa la conexión."; st.busy = false; draw(); return; }
      setToken(data.access_token);
      st.busy = false;
      enterHistory();
      startTimers();
      draw();
      await loadHome();
    } catch (_) {
      st.notice = "No se pudo actualizar. Revisa la conexión.";
      st.busy = false;
      draw();
    }
  }

  function onKey(event) {
    if (event.key === "Escape" && st.confirmExit) { st.confirmExit = false; draw(); }
  }

  async function start() {
    if (!appEl()) return;
    setLang(savedLang(), false);
    applyBrand();
    document.addEventListener("click", onClick);
    document.addEventListener("input", onInput);
    document.addEventListener("submit", onSubmit);
    document.addEventListener("keydown", onKey);
    window.addEventListener("popstate", onPop);
    clockTimer = setInterval(tickClock, 20000);
    if (!token()) {
      window.history.replaceState(LOGIN_ENTRY, "");
      draw();
      return;
    }
    startTimers();
    const state = window.history.state;
    if (state && state.lo && state.screen !== "guard" && state.screen !== "login") {
      // Recargó la página: sigue en la misma pantalla.
      st.depth = Number(state.depth) || 1;
      st.tab = state.screen;
      st.person = state.person || "";
      await loadHome();
      draw();
      if (st.tab === "crm") loadCrm();
      return;
    }
    enterHistory();
    draw();
    loadHome();
  }

  window.CxLiderOperacion = { st, filterPeople, stateChip, homeView, crmList, loginView, serverText, savedLang, nav, TOKEN_KEY, clockTimer: () => clockTimer, go, onPop, enterHistory, exitDialog };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
