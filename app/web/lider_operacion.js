// Mini panel "Líder de operación" v2 (067A): CRM Campo, Reportes y Marcar con PIN de UNA operación.
// Esta pantalla no decide nada: la operación sale de la sesión y el servidor filtra siempre.
// Las únicas escrituras son marcar con el PIN de una persona y finalizar ahora un turno (desde el
// detalle de la persona, con doble confirmación; nunca desde la tarjeta); el servidor
// pone la hora y responde 403 a cualquier otra. No hay ningún campo para escribir horas.
//
// El PIN solo vive en memoria mientras dura su pantalla: a los 20 s sin tocar vuelve al teclado.
//
// Flecha atrás: cada pantalla es una entrada del historial, misma página y misma sesión:
//   [guard] [inicio] [crm] [pin] [crm + persona] [reportes] [reportes + persona] ...
// Inicio siempre es la entrada 1. Atrás desde ella cae en guard: el panel vuelve a poner Inicio y
// pregunta "¿Salir del panel?". Al entrar, el formulario se reemplaza por guard: nunca se vuelve a él.
(() => {
  "use strict";

  const API = "/api/v1";
  const CRM_MS = 30000;
  const HOME_MS = 60000;
  const LANG_KEY = "cx_lider_lang";
  const THEME_KEY = "cx_lider_theme"; // oscuro por defecto; cada equipo recuerda su elección
  const THEMES = { dark: { bg: "#050b1c", text: "#f2f6ff" }, light: { bg: "#eef3fa", text: "#0f1b33" } };
  const params = new URLSearchParams(window.location.search);
  const CID = params.get("company_id") || "";
  const BOOT = window.__CX_LIDER__ && typeof window.__CX_LIDER__ === "object" ? window.__CX_LIDER__ : { ok: false };
  const TOKEN_KEY = `clonexa_mini_panel_token_${CID}_lider_operacion_${BOOT.slug || ""}`;
  const STATES = [["working", "Trabajando"], ["on_break", "En pausa"], ["to_confirm", "Por confirmar"], ["no_shift", "Sin turno"]];
  const STATE_LABEL = Object.fromEntries(STATES);
  const ACTIONS = { start: "Iniciar turno", pause: "Pausa", resume: "Retomar", end: "Finalizar turno" };
  const DONE = { start: "Inicio de turno registrado", pause: "Pausa registrada", resume: "Regreso registrado", end: "Turno finalizado" };
  const ORIGIN = { app: "App", pin: "PIN", lider: "Líder" };
  const PIN_LENGTH = 4;
  const IDLE_MS = 20000;
  const DONE_MS = 4000;
  const NO_LOCATION = "Activa la ubicación de este equipo";
  const MARK = { in: "Entrada", pause: "Pausa", resume: "Retomar", out: "Salida" };

  const st = { tab: "inicio", person: "", depth: 1, confirmExit: false, boardReady: false, busy: false, notice: "", home: null, crm: null, crmStale: false, query: "", chip: "all", updated: "", pin: null, finish: null, crmNote: null, theme: "dark", close: null, schedule: null };
  let homeTimer = null;
  let pinTimer = null;
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

  // ------------------------------------------------------------ modo claro / oscuro
  function savedTheme() {
    try { return window.localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark"; } catch (_) { return "dark"; }
  }
  function toggleTheme() {
    st.theme = st.theme === "light" ? "dark" : "light";
    try { window.localStorage.setItem(THEME_KEY, st.theme); } catch (_) { /* sin almacenamiento */ }
    applyBrand();
    draw();
  }

  // Lo que responde el servidor viene en español.
  const SERVER = [
    [/^Este panel es solo para el líder de (.+)$/, "Este panel es solo para el líder de {op}"],
    [/^Este PIN no es de (.+)$/, "Este PIN no es de {v}"],
    [/^PIN incorrecto\. Intentos restantes: (\d+)\.$/, "PIN incorrecto. Intentos restantes: {v}."],
    [/^Demasiados intentos\. Este equipo queda bloqueado (\d+) min\.$/, "Demasiados intentos. Este equipo queda bloqueado {v} min."],
    [/^Esa persona no es de (.+)\.$/, "Esa persona no es de {v}."],
    [/^Este turno supera ([\d.]+) horas: lo cierra el dueño en el portal con la hora real\.$/, "Este turno supera {v} horas: lo cierra el dueño en el portal con la hora real."],
  ];
  function serverText(detail) {
    const text = String(detail || "");
    for (const [re, key] of SERVER) { const m = text.match(re); if (m) return T(key, { v: m[1], op: m[1] }); }
    return T(text);
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
    resetPin();
    Object.assign(st, { tab: "inicio", person: "", confirmExit: false, boardReady: false, home: null, crm: null, busy: false, finish: null, crmNote: null, notice: message || "Tu sesión terminó. Vuelve a entrar." });
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
    const sameCrm = st.tab === "crm" && screen === "crm"; // abrir o cerrar un detalle no mueve la lista
    if (screen !== "pin") resetPin();
    st.finish = null;
    st.tab = screen;
    st.person = person || "";
    if (sameBoard && window.CxReportsBoard) { window.CxReportsBoard.setOpen(st.person); return; }
    draw();
    if (!sameCrm) toTop();
    if (screen === "inicio") loadHome();
    if (screen === "crm") loadCrm();
    if (screen === "pin") checkDeviceLocation();
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

  // 401, o 403 de la propia sesión, es sesión perdida. Los demás errores se muestran en pantalla.
  async function send(path, body) {
    const res = await fetch(panelUrl(path), { method: "POST", headers: { Authorization: `Bearer ${token()}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 || (res.status === 403 && /^(Este panel|Esta sesión)/.test(String(data.detail || "")))) { sessionLost(data.detail); return null; }
    if (!res.ok) throw new Error(data.detail || "No se pudo actualizar. Revisa la conexión.");
    return data;
  }

  async function downloadPdf(path, name) {
    const res = await fetch(panelUrl(path), { headers: { Authorization: `Bearer ${token()}` } });
    if (res.status === 401 || res.status === 403) { const data = await res.json().catch(() => ({})); sessionLost(data.detail); return; }
    if (!res.ok) throw new Error("No se pudo generar el archivo.");
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  // La ubicación del equipo del líder, de este momento. Sin ella no se marca ni se finaliza.
  function deviceLocation() {
    return new Promise((resolve) => {
      const geo = navigator.geolocation;
      if (!geo) { resolve(null); return; }
      geo.getCurrentPosition((p) => resolve({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: p.coords.accuracy }), () => resolve(null),
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
    });
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
    if (st.tab === "crm") { drawCrmBody(); drawDetailBody(); }
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
  // El semáforo de una persona: su color, su palabra y su tiempo a la derecha.
  function stateChip(p, limitHours) {
    const state = STATE_LABEL[p.state] ? p.state : "no_shift";
    const label = state === "no_shift" && p.end ? `${T("Terminó")} ${p.end.t} ${p.end.a}` : T(STATE_LABEL[state]);
    const time = state === "working" || state === "on_break" ? hm(p.minutes) : state === "to_confirm" ? (p.minutes ? `+${limitHours || 15} h` : "!") : "—";
    if (p.out_of_schedule && state !== "no_shift") return { cls: `is-${state} is-late`, text: T("Fuera de horario"), time }; // 071A
    return { cls: `is-${state}`, text: label, time };
  }
  function clock(zone) {
    try { return new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date()); } catch (_) { return ""; }
  }
  function today(zone) {
    try { return new Intl.DateTimeFormat(lang() === "en" ? "en-US" : "es-CO", { timeZone: zone, weekday: "short", day: "2-digit", month: "short" }).format(new Date()).replace(/[.,]/g, ""); } catch (_) { return ""; }
  }
  // "Ayer" sale de la fecha local que manda el servidor; hoy no se dice.
  function dayWord(iso) {
    const now = st.crm && st.crm.operation && st.crm.operation.local_date;
    if (!iso || !now || iso === now) return "";
    const back = Math.round((Date.parse(`${now}T00:00:00Z`) - Date.parse(`${iso}T00:00:00Z`)) / 86400000);
    return back === 1 ? T("ayer") : `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  }
  function initials(name) {
    const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    return ((parts[0] || "?")[0] + (parts.length > 1 ? parts[1][0] : "")).toUpperCase();
  }
  const firstName = (name) => String(name || "").trim().split(/\s+/)[0] || "";

  // ------------------------------------------------------------ vistas
  function langPicker() {
    const now = lang();
    return `<div class="lo-lang" role="group" aria-label="${h(T("Idioma"))}">${[["es", "Español"], ["en", "English"]].map(([k, l]) =>
      `<button type="button" data-no-i18n data-lo-lang="${k}" class="${now === k ? "is-on" : ""}" aria-pressed="${now === k}">${l}</button>`).join("")}</div>`;
  }

  function themeButton() {
    const toLight = st.theme !== "light";
    return `<button type="button" class="lo-theme" data-no-i18n data-lo-theme-toggle aria-label="${h(T(toLight ? "Modo claro" : "Modo oscuro"))}">${h(T(toLight ? "Claro" : "Oscuro"))}</button>`;
  }

  function headerText() {
    const op = operation();
    if (!token()) return { kicker: T("Líder de operación"), title: op.name };
    if (st.tab === "crm") return { kicker: `${T("CRM Campo")} · ${op.name}`, title: `${h(T("En vivo"))} · <span data-lo-clock="${h(op.timezone)}">${h(clock(op.timezone))}</span> ${h(op.abbr)}`, html: true };
    if (st.tab === "pin") return { kicker: `${T("Marcación")} · ${op.name}`, title: st.pin && st.pin.person ? `<span data-lo-clock="${h(op.timezone)}">${h(clock(op.timezone))}</span> ${h(op.abbr)}` : h(T("Ingresa tu PIN")), html: true };
    if (st.tab === "reportes") return { kicker: `${T("Reportes")} · ${op.name}`, title: op.name };
    const me = st.home && st.home.me;
    return { kicker: `${T("Líder")} · ${op.name}`, title: me ? T("Hola, {name}", { name: firstName(me.name) }) : op.name };
  }

  function header() {
    const text = headerText();
    const logo = BOOT.brand && /^(https:|data:image\/|\/)/.test(String(BOOT.brand.logo_url || "")) ? `<img class="lo-logo" src="${h(BOOT.brand.logo_url)}" alt="">` : "";
    return `<header class="lo-head">${logo}<div class="lo-head-text"><p class="lo-kicker" data-no-i18n>${h(text.kicker)}</p><h1 data-no-i18n>${text.html ? text.title : h(text.title)}</h1></div>${langPicker()}${themeButton()}</header>`;
  }

  function loginView() {
    if (!BOOT.ok) {
      return `<main class="lo-login"><section class="lo-card"><div class="lo-lang-row">${langPicker()}${themeButton()}</div><h1>${h(T("Líder de operación"))}</h1><p role="alert">${h(T("Este enlace no es válido. Pide el enlace de tu operación."))}</p></section></main>`;
    }
    return `${header()}<main class="lo-login"><form class="lo-card" data-lo-login autocomplete="on">
      ${st.notice ? `<p class="lo-error" role="alert">${h(serverText(st.notice))}</p>` : ""}
      <label>${h(T("Usuario"))}<input name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required></label>
      <label>${h(T("Clave"))}<input name="password" type="password" autocomplete="current-password" required></label>
      <button type="submit" class="lo-primary" ${st.busy ? "disabled" : ""}>${h(T(st.busy ? "Entrando…" : "Entrar"))}</button>
    </form></main>`;
  }

  function counter(key, value) {
    return `<button type="button" class="lo-counter is-${key}" data-lo-counter="${key}"><strong>${h(value)}</strong><span>${h(T(STATE_LABEL[key]))}</span></button>`;
  }

  function homeView(home = st.home) {
    if (!home) return `<main class="lo-main"><p class="lo-card" role="status">${h(T(st.notice || "Cargando…"))}</p></main>`;
    const op = home.operation;
    const crm = home.crm || {};
    const rep = home.reports || {};
    const people = num(crm.total) === 1 ? T("1 persona") : T("{n} personas", { n: num(crm.total) });
    const hours = T("{h} esta semana · {n} notas · {a} alertas", { h: hm(rep.hours_minutes), n: num(rep.notes), a: num(rep.alerts) });
    return `<main class="lo-main lo-home">
      <section class="lo-clockcard" aria-label="${h(T("Hora local"))}"><p class="lo-bigclock"><strong data-lo-clock="${h(op.timezone)}">${h(clock(op.timezone) || op.local_time)}</strong><span>${h(op.abbr)} · ${h(today(op.timezone))}</span></p>
        <p class="lo-who" data-no-i18n>${h(T(home.me.role))} · ${h(people)}</p></section>
      <div class="lo-counters">${STATES.map(([k]) => counter(k, num(crm[k]))).join("")}</div>
      <div class="lo-cards">
        <button type="button" class="lo-module" data-lo-tab="crm"><h3>${h(T("CRM Campo"))}</h3><p>${h(T("Quién está trabajando ahora · lista PDF"))}</p></button>
        <button type="button" class="lo-module" data-lo-tab="reportes"><h3>${h(T("Reportes"))}</h3><p data-no-i18n>${h(hours)}</p></button>
        <button type="button" class="lo-module is-pin" data-lo-tab="pin"><h3>${h(T("Marcar con PIN"))}</h3><p>${h(T("Para quien no tiene Telegram: marca aquí con su PIN de 4 dígitos"))}</p></button>
      </div>
    </main>`;
  }

  function markText(p) {
    const mark = p.last_mark;
    if (!mark) return T("Sin marcas recientes");
    const when = [T(MARK[mark.k] || mark.label), dayWord(mark.d), mark.t].filter(Boolean).join(" ");
    return ORIGIN[p.origin] ? `${when} · ${T(ORIGIN[p.origin])}` : when;
  }

  // La tarjeta solo abre el detalle: finalizar un turno está allá, con doble confirmación.
  function personRow(p, limitHours) {
    const chip = stateChip(p, limitHours);
    return `<li><button type="button" class="lo-person ${chip.cls}" data-lo-person="${h(p.id)}" aria-haspopup="dialog"><span class="lo-dot ${p.state === "working" ? "is-live" : ""}" aria-hidden="true"></span><span class="lo-person-who"><b data-no-i18n>${h(p.name)}</b><small class="lo-st" data-no-i18n>${h(chip.text)}</small><small data-no-i18n>${h(markText(p))}</small></span>
      <span class="lo-time" data-no-i18n>${h(chip.time)}</span></button></li>`;
  }

  // ------------------------------------------------------------ detalle de la persona
  const personOf = (id) => arr(st.crm && st.crm.people).find((p) => p.id === id);
  const originWord = (key) => (ORIGIN[key] ? T(ORIGIN[key]) : "—");
  const markWhen = (m) => (m ? [dayWord(m.d), m.t, m.a].filter(Boolean).join(" ") : "—");
  const detailRow = (label, value) => `<div class="lo-row"><dt>${h(T(label))}</dt><dd data-no-i18n>${value}</dd></div>`;

  function detailBody(p, limitHours) {
    const chip = stateChip(p, limitHours);
    const shift = p.shift || {};
    const pauses = arr(shift.pauses).map((pa) => `<li>${h(pa.start)} – ${h(pa.end || (shift.out ? shift.out.t : T("en curso")))} · ${h(hm(pa.minutes))} · ${h(originWord(pa.o))}</li>`).join("");
    const note = st.crmNote && !st.crmNote.ok ? `<p class="lo-error" role="alert" data-no-i18n>${h(st.crmNote.text)}</p>` : "";
    return `<dl class="lo-rows">
        ${detailRow("Estado", `<span class="lo-state ${chip.cls}"><span class="lo-dot ${p.state === "working" ? "is-live" : ""}" aria-hidden="true"></span>${h(chip.text)}</span>`)}
        ${detailRow("Entrada", h(markWhen(shift.in)))}
        ${detailRow("Pausas", pauses ? `<ul class="lo-pauses">${pauses}</ul>` : h(T("Sin pausas")))}
        ${shift.out ? detailRow("Salida", h(markWhen(shift.out))) : ""}
        ${detailRow("Tiempo", h(chip.time))}
        ${p.scheduled_end ? detailRow("Salida programada", h(p.scheduled_end)) : ""}
        ${p.slot_name ? detailRow("Horario", h(p.slot_name)) : ""}
        ${p.schedule_reason ? detailRow("Sigue trabajando", h(p.schedule_reason)) : ""}
        ${detailRow("Origen", h(originWord(p.origin)))}
      </dl>${note}
      ${p.can_close ? `<div class="lo-sheet-foot"><button type="button" class="lo-close-btn" data-lo-close="${h(p.id)}">${h(T("Cerrar turno"))}</button></div>` : ""}
      ${p.can_finish && !p.can_close ? `<div class="lo-sheet-foot"><button type="button" class="lo-finish-link" data-lo-finish="${h(p.id)}">${h(T("Finalizar turno"))}</button></div>` : ""}`;
  }

  function detailView() {
    const p = personOf(st.person);
    if (!p) return "";
    return `<div class="lo-modal"><section class="lo-sheet" role="dialog" aria-modal="true" aria-labelledby="loDetailTitle">
      <header class="lo-sheet-head"><div><h2 id="loDetailTitle" data-no-i18n>${h(p.name)}</h2>${p.role ? `<p data-no-i18n>${h(T(p.role))}</p>` : ""}</div><button type="button" class="lo-link" data-lo-detail-close>${h(T("Cerrar"))}</button></header>
      <div data-lo-detail-body>${detailBody(p, st.crm.limit_hours)}</div></section></div>`;
  }

  function openDetail(id) {
    st.crmNote = null;
    pushScreen("crm", id);
    show("crm", id);
  }
  function closeDetail() { if (st.person) window.history.back(); }

  // El refresco de 30 s actualiza el detalle, nunca una confirmación a medias.
  function drawDetailBody() {
    if (!st.person || st.finish || st.close) return;
    const p = personOf(st.person);
    const box = document.querySelector("[data-lo-detail-body]");
    if (!p || !box) { draw(); return; }
    box.innerHTML = detailBody(p, st.crm.limit_hours);
  }

  function crmList(crm = st.crm) {
    if (!crm) return `<p class="lo-card" role="status">${h(T("Cargando…"))}</p>`;
    const list = filterPeople(crm.people, st.query, st.chip);
    const counts = crm.counts || {};
    const note = st.crmNote;
    return `<div class="lo-chips" role="group">${STATES.map(([k, l]) => `<button type="button" class="lo-chip is-${k} ${st.chip === k ? "is-on" : ""}" data-lo-chip="${k}" aria-pressed="${st.chip === k}"><span class="lo-dot" aria-hidden="true"></span><span>${h(T(l))}</span> <b>${num(counts[k])}</b></button>`).join("")}</div>
      ${st.crmStale ? `<p class="lo-error" role="alert">${h(T("No se pudo actualizar. Revisa la conexión."))}</p>` : ""}
      ${note ? `<p class="${note.ok ? "lo-ok" : "lo-error"}" role="${note.ok ? "status" : "alert"}" data-no-i18n>${h(note.text)}</p>` : ""}
      <div class="lo-crm-top"><h2 data-no-i18n>${h(num(counts.total) === 1 ? T("1 persona") : T("{n} personas", { n: num(counts.total) }))} · A-Z</h2><span class="lo-crm-actions">${crm.work_schedule ? `<button type="button" class="lo-pdf" data-lo-horario>${h(T("Horario de la semana"))}</button>` : ""}<button type="button" class="lo-pdf" data-lo-pdf="list" ${st.busy ? "disabled" : ""}>${h(T("PDF lista"))}</button></span></div>
      ${list.length ? `<ul class="lo-people">${list.map((p) => personRow(p, crm.limit_hours)).join("")}</ul>` : `<p class="lo-card">${h(T("Ninguna persona coincide."))}</p>`}`;
  }

  function crmView() {
    return `<main class="lo-main lo-crm"><input class="lo-search" type="search" data-lo-search value="${h(st.query)}" placeholder="${h(T("Buscar persona"))}" aria-label="${h(T("Buscar persona"))}" autocomplete="off">
      <div data-lo-crm-body>${crmList()}</div></main>`;
  }

  function finishDialog() {
    const f = st.finish;
    const op = operation();
    const time = `<span data-lo-clock="${h(op.timezone)}">${h(clock(op.timezone))}</span> ${h(op.abbr)}`;
    const title = h(T("¿Finalizar el turno de {name} ahora ({time})?", { name: f.name, time: "\u0001" })).replace("\u0001", time);
    // Cancelar va primero y es el foco por defecto (draw) en los dos pasos.
    const cancel = `<button type="button" data-lo-finish-no ${f.busy ? "disabled" : ""}>${h(T("Cancelar"))}</button>`;
    const second = f.step === 2;
    return `<div class="lo-modal"><div class="lo-dialog" role="alertdialog" aria-modal="true" aria-labelledby="loFinishTitle">
      <h2 id="loFinishTitle" data-no-i18n>${title}</h2><p>${h(T("La salida queda con la hora actual del servidor."))}</p>
      ${second ? `<label class="lo-check"><input type="checkbox" data-lo-confirm ${f.confirmed ? "checked" : ""} ${f.busy ? "disabled" : ""}><span>${h(T("Confirmo que esta persona ya terminó su turno"))}</span></label>` : ""}
      <div class="lo-dialog-actions">${cancel}${second
        ? `<button type="button" class="is-danger" data-lo-finish-yes ${f.confirmed && !f.busy ? "" : "disabled"}>${h(T(f.busy ? "Guardando…" : "Sí, finalizar"))}</button>`
        : `<button type="button" class="lo-next" data-lo-finish-next>${h(T("Continuar"))}</button>`}</div>
    </div></div>`;
  }

  // ------------------------------------------------------------ 071A: cerrar turno Fuera de horario
  const REASONS = [["olvido", "Olvidó finalizar"], ["salida_real", "Salida real confirmada"], ["otro", "Otro"]];

  function closeDialog() {
    const c = st.close;
    const op = operation();
    const now = `<span data-lo-clock="${h(op.timezone)}">${h(clock(op.timezone))}</span> ${h(op.abbr)}`;
    const cancel = `<button type="button" data-lo-close-no ${c.busy ? "disabled" : ""}>${h(T("Cancelar"))}</button>`;
    const err = c.error ? `<p class="lo-error" role="alert" data-no-i18n>${h(c.error)}</p>` : "";
    if (c.step === 2) {
      const when = c.choice === "scheduled" ? `${h(T("Salida programada"))}: ${h(c.scheduled)}` : `${h(T("Hora actual"))}: ${now}`;
      const reason = (REASONS.find(([k]) => k === c.reason) || ["", ""])[1];
      return `<div class="lo-modal"><div class="lo-dialog" role="alertdialog" aria-modal="true" aria-labelledby="loCloseTitle">
        <h2 id="loCloseTitle" data-no-i18n>${h(T("¿Cerrar el turno de {name}?", { name: c.name }))}</h2>
        <p data-no-i18n>${when}<br>${h(T("Motivo"))}: ${h(T(reason))}${c.detail ? ` · ${h(c.detail)}` : ""}</p>
        <label class="lo-check"><input type="checkbox" data-lo-close-confirm ${c.confirmed ? "checked" : ""} ${c.busy ? "disabled" : ""}><span>${h(T("Confirmo la hora de salida y el motivo"))}</span></label>${err}
        <div class="lo-dialog-actions">${cancel}<button type="button" class="is-danger" data-lo-close-yes ${c.confirmed && !c.busy ? "" : "disabled"}>${h(T(c.busy ? "Guardando…" : "Sí, cerrar turno"))}</button></div>
      </div></div>`;
    }
    const radio = (value, label, enabled) => `<label class="lo-radio ${enabled ? "" : "is-off"}"><input type="radio" name="lo-close-choice" value="${value}" ${c.choice === value ? "checked" : ""} ${enabled ? "" : "disabled"}><span data-no-i18n>${label}</span></label>`;
    return `<div class="lo-modal"><div class="lo-dialog" role="alertdialog" aria-modal="true" aria-labelledby="loCloseTitle">
      <h2 id="loCloseTitle" data-no-i18n>${h(T("Cerrar el turno de {name}", { name: c.name }))}</h2>
      <p>${h(T("Elige la hora de salida: no se puede escribir otra."))}</p>
      <fieldset class="lo-close-set"><legend>${h(T("Hora de salida"))}</legend>
        ${radio("scheduled", `${h(T("Salida programada"))}${c.scheduled ? ` · ${h(c.scheduled)}` : ""}`, Boolean(c.scheduled))}
        ${radio("now", `${h(T("Hora actual"))} · ${now}`, true)}</fieldset>
      <label class="lo-field"><span>${h(T("Motivo (obligatorio)"))}</span><select data-lo-close-reason><option value="">${h(T("Elige el motivo"))}</option>${REASONS.map(([k, l]) => `<option value="${k}" ${c.reason === k ? "selected" : ""}>${h(T(l))}</option>`).join("")}</select></label>
      <label class="lo-field"><span>${h(T("Detalle (obligatorio si el motivo es Otro)"))}</span><textarea data-lo-close-detail rows="2" maxlength="500">${h(c.detail || "")}</textarea></label>${err}
      <div class="lo-dialog-actions">${cancel}<button type="button" class="lo-next" data-lo-close-next>${h(T("Continuar"))}</button></div>
    </div></div>`;
  }

  // Lo elegido en el primer paso. Mismas reglas del servidor.
  function closeStep1(values) {
    const c = st.close;
    c.choice = values.choice || c.choice;
    c.reason = values.reason || "";
    c.detail = String(values.detail || "").replace(/\s+/g, " ").trim();
    if (c.choice !== "scheduled" && c.choice !== "now") return T("Elige la salida programada o la hora actual.");
    if (c.choice === "scheduled" && !c.scheduled) return T("Elige la salida programada o la hora actual.");
    if (!REASONS.some(([k]) => k === c.reason)) return T("Elige el motivo del cierre.");
    if (c.reason === "otro" && c.detail.length < 5) return T("Escribe el detalle del motivo (mínimo 5 caracteres).");
    return "";
  }

  function readStep1() {
    const picked = document.querySelector('input[name="lo-close-choice"]:checked');
    const reason = document.querySelector("[data-lo-close-reason]");
    const detail = document.querySelector("[data-lo-close-detail]");
    return { choice: picked ? picked.value : "", reason: reason ? reason.value : "", detail: detail ? detail.value : "" };
  }

  async function closeNow() {
    const c = st.close;
    if (!c || c.busy || c.step !== 2 || !c.confirmed) return; // sin los dos pasos no llega al servidor
    c.busy = true;
    c.error = "";
    draw();
    try {
      const data = await send(`crm/${encodeURIComponent(c.id)}/cerrar`, { choice: c.choice, reason_code: c.reason, reason_detail: c.detail, confirmed: true });
      if (!data) return;
      st.close = null;
      st.crmNote = { ok: true, text: T("Turno de {name} cerrado a las {time}.", { name: data.name, time: data.at }) };
      closeDetail();
      return;
    } catch (error) { c.error = serverText(error.message); }
    c.busy = false;
    c.step = 1;
    draw();
    loadCrm();
  }

  function scheduleView() {
    const sc = st.schedule;
    const body = !sc.data ? `<p role="status">${h(sc.error || T("Cargando…"))}</p>`
      : !sc.data.configured ? `<p>${h(T("Esta operación aún no tiene horario."))}</p>`
        : arr(sc.data.slots).map((slot) => `<section class="lo-sched"><h3 data-no-i18n>${h(slot.name)}</h3>
          ${slot.lunch_start ? `<p class="lo-sched-note">${h(T("Almuerzo de referencia"))}: <span data-no-i18n>${h(slot.lunch_start)} – ${h(slot.lunch_end)}</span></p>` : ""}
          <dl class="lo-rows">${arr(slot.days_view).map((d) => `<div class="lo-row ${d.special ? "is-special" : ""}"><dt>${h(T(d.name))} <span data-no-i18n>${h(String(d.date).slice(8, 10))}</span></dt><dd data-no-i18n>${h(d.off ? T("Libre") : d.label)}</dd></div>`).join("")}</dl></section>`).join("");
    return `<div class="lo-modal"><section class="lo-sheet" role="dialog" aria-modal="true" aria-labelledby="loSchedTitle">
      <header class="lo-sheet-head"><div><h2 id="loSchedTitle">${h(T("Horario de la semana"))}</h2>${sc.data ? `<p data-no-i18n>${h(sc.data.week_start)} – ${h(sc.data.week_end)} · ${h(operation().abbr)}</p>` : ""}</div><button type="button" class="lo-link" data-lo-horario-close>${h(T("Cerrar"))}</button></header>
      ${body}<p class="lo-sched-note">${h(T("El almuerzo es solo de referencia: se descuenta únicamente la pausa que la persona marca."))}</p></section></div>`;
  }

  async function openSchedule() {
    st.schedule = { data: null, error: "" };
    draw();
    try {
      const data = await read("horario");
      if (!data) return;
      if (st.schedule) st.schedule.data = data;
    } catch (error) { if (st.schedule) st.schedule.error = serverText(error.message); }
    draw();
  }

  // ------------------------------------------------------------ marcar con PIN
  function pinState() {
    if (!st.pin) st.pin = { digits: "", person: null, error: "", busy: false, ending: false, summary: "", done: "", located: null };
    return st.pin;
  }
  function clearPinTimer() { if (pinTimer) { clearTimeout(pinTimer); pinTimer = null; } }
  // Borra de la memoria todo lo de la persona: se usa también para volver al teclado.
  function resetPin() {
    clearPinTimer();
    const located = st.pin ? st.pin.located : null;
    st.pin = null;
    if (located !== null) pinState().located = located;
  }
  function backToKeypad() {
    resetPin();
    if (st.tab === "pin") draw();
  }
  // Cualquier toque reinicia los 20 s. Sin nada escrito no hay nada que proteger.
  function touchPin() {
    clearPinTimer();
    const p = st.pin;
    if (st.tab === "pin" && p && (p.digits || p.person) && !p.done) pinTimer = setTimeout(backToKeypad, IDLE_MS);
  }
  async function checkDeviceLocation() {
    const where = await deviceLocation();
    pinState().located = Boolean(where);
    if (st.tab === "pin" && !st.pin.person && !st.pin.done) draw();
  }

  function pressKey(key) {
    const p = pinState();
    if (p.busy || p.person) return;
    p.error = "";
    if (key === "ok") { checkPin(); return; }
    if (key === "del") p.digits = p.digits.slice(0, -1);
    else if (/^\d$/.test(key) && p.digits.length < PIN_LENGTH) p.digits += key;
    touchPin();
    draw();
  }

  async function checkPin() {
    const p = pinState();
    if (p.digits.length !== PIN_LENGTH) { p.error = "El PIN tiene 4 dígitos."; draw(); return; }
    p.busy = true;
    draw();
    try {
      const data = await send("pin/verificar", { pin: p.digits });
      if (!data) return;
      p.person = data.employee;
    } catch (error) {
      p.error = error.message;
      p.digits = "";
    }
    p.busy = false;
    touchPin();
    draw();
  }

  async function punch(action) {
    const p = pinState();
    if (p.busy || !p.person) return;
    if (action === "end" && !p.ending) { p.ending = true; touchPin(); draw(); return; }
    if (action === "end" && !p.summary.trim()) { p.error = "Escribe el resumen de la jornada."; touchPin(); draw(); return; }
    p.busy = true;
    p.error = "";
    draw();
    const where = await deviceLocation();
    p.located = Boolean(where);
    if (!where) { p.busy = false; p.error = NO_LOCATION; touchPin(); draw(); return; }
    try {
      const data = await send("pin/marcar", { pin: p.digits, action, summary: action === "end" ? p.summary : null, lang: lang(), ...where });
      if (!data) return;
      clearPinTimer();
      Object.assign(p, { digits: "", person: null, summary: "", ending: false, busy: false, done: `${T(DONE[action])} · ${data.name} · ${data.at}` });
      pinTimer = setTimeout(backToKeypad, DONE_MS);
    } catch (error) {
      p.busy = false;
      p.error = error.message;
      touchPin();
    }
    draw();
  }

  function pinPersonView(p) {
    const person = p.person;
    const chip = stateChip({ state: person.state });
    const error = p.error ? `<p class="lo-error" role="alert" data-no-i18n>${h(serverText(p.error))}</p>` : "";
    const buttons = p.ending
      ? `<label class="lo-summary">${h(T("Resumen de la jornada"))}<textarea data-lo-summary maxlength="2000" placeholder="${h(T("Escribe el resumen de la jornada."))}">${h(p.summary)}</textarea></label>
         <div class="lo-actions"><button type="button" class="lo-action is-end" data-lo-punch="end" ${p.busy ? "disabled" : ""}>${h(T(p.busy ? "Guardando…" : "Finalizar turno"))}</button></div>`
      : `<div class="lo-actions">${arr(person.actions).map((a) => `<button type="button" class="lo-action is-${h(a)}" data-lo-punch="${h(a)}" ${p.busy ? "disabled" : ""}>${h(T(ACTIONS[a] || a))}</button>`).join("")}</div>`;
    return `<section class="lo-pin lo-person-card"><div class="lo-avatar" aria-hidden="true">${h(initials(person.name))}</div><h2 data-no-i18n>${h(person.name)}</h2>
      <span class="lo-state ${chip.cls}" data-no-i18n><span class="lo-dot" aria-hidden="true"></span>${h(chip.text)}</span>${error}${buttons}
      <button type="button" class="lo-link" data-lo-pin-back>${h(T("Volver al teclado"))}</button>
      <div class="lo-note"><p>${h(T("Vuelve solo al teclado en 20 s."))}</p><p>${h(T("Origen: Panel PIN, con la hora del servidor y la ubicación de este equipo."))}</p></div></section>`;
  }

  function pinView() {
    const p = pinState();
    if (p.person) return `<main class="lo-main">${pinPersonView(p)}</main>`;
    const dots = Array.from({ length: PIN_LENGTH }, (_, i) => `<i class="${i < p.digits.length ? "is-on" : ""}"></i>`).join("");
    const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((k) => `<button type="button" class="lo-key" data-lo-key="${k}">${k}</button>`).join("");
    const where = p.located === false ? T(NO_LOCATION) : T("Ubicación de este equipo: se guarda con la marca");
    return `<main class="lo-main"><section class="lo-pin">
      <p class="lo-pin-hint">${h(T("Cada persona marca con su propio PIN"))}</p>
      <div class="lo-dots" role="img" aria-label="${h(T("{n} de 4 dígitos", { n: p.digits.length }))}">${dots}</div>
      ${p.done ? `<p class="lo-ok" role="status" data-no-i18n>${h(p.done)}</p>` : ""}${p.error ? `<p class="lo-error" role="alert" data-no-i18n>${h(serverText(p.error))}</p>` : ""}
      <div class="lo-keys">${keys}<button type="button" class="lo-key is-word" data-lo-key="del">${h(T("Borrar"))}</button><button type="button" class="lo-key" data-lo-key="0">0</button><button type="button" class="lo-key is-word is-ok" data-lo-key="ok" ${p.busy ? "disabled" : ""}>OK</button></div>
      <div class="lo-note"><p>${h(where)}</p><p>${h(T("5 intentos fallidos = bloqueo de 15 min"))}</p></div>
    </section></main>`;
  }

  function nav() {
    const items = [["inicio", homeWord()], ["crm", "CRM"], ["pin", "PIN"], ["reportes", T("Reportes")]];
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
    const body = st.tab === "crm" ? crmView() : st.tab === "pin" ? pinView() : st.tab === "reportes" ? `<main class="lo-main lo-reports"><div id="loBoardHost"></div></main>` : homeView();
    return `${header()}${body}${nav()}${st.tab === "crm" && st.person ? detailView() : ""}${st.finish ? finishDialog() : ""}${st.close ? closeDialog() : ""}${st.schedule ? scheduleView() : ""}${st.confirmExit ? exitDialog() : ""}`;
  }

  // ------------------------------------------------------------ dibujo
  const appEl = () => document.getElementById("loApp");

  function applyAccent() {
    const el = appEl();
    if (!el) return;
    const accent = operation().accent;
    el.className = `lo-app lo-a${accent === 0 || accent === 1 ? accent : "x"}${st.theme === "light" ? " is-light" : ""}`;
  }

  function applyBrand() {
    // v2: colores del panel, oscuro o claro; de la marca salen el logo y la letra. El Board calcula
    // sus pares de contraste (CxReportsBoard.applyContrast) sobre este mismo fondo.
    const b = BOOT.brand || {};
    const root = document.documentElement.style;
    document.documentElement.setAttribute("data-lo-theme", st.theme);
    root.setProperty("--cx-bg", THEMES[st.theme].bg);
    root.setProperty("--cx-text", THEMES[st.theme].text);
    root.setProperty("--cx-primary", "#16489a");
    root.setProperty("--cx-secondary", "#2ff08f");
    if (b.font_family) root.setProperty("--lo-font", `"${String(b.font_family).replace(/["\\]/g, "")}", Inter, "Segoe UI", system-ui, sans-serif`);
  }

  function mountBoard() {
    if (!window.CxReportsBoard) return;
    const mounted = window.CxReportsBoard.mount({
      companyId: CID, apiBase: API, baseUrl: panelUrl("reportes"), token, readonly: true, pdf: true,
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
    else if (st.finish) { const no = document.querySelector("[data-lo-finish-no]"); if (no) no.focus(); }
    else if (st.close) { const no = document.querySelector("[data-lo-close-no]"); if (no) no.focus(); }
    else if (st.schedule) { const x = document.querySelector("[data-lo-horario-close]"); if (x) x.focus(); }
    else if (st.tab === "crm" && st.person) { const close = document.querySelector("[data-lo-detail-close]"); if (close) close.focus(); }
  }

  function drawCrmBody() {
    const box = document.querySelector("[data-lo-crm-body]");
    if (!box) { draw(); return; }
    box.innerHTML = crmList();
  }

  function tickClock() {
    document.querySelectorAll("[data-lo-clock]").forEach((node) => { const value = clock(node.getAttribute("data-lo-clock")); if (value) node.textContent = value; });
  }

  // ------------------------------------------------------------ eventos
  async function exit() {
    const current = token();
    setToken("");
    stopTimers();
    resetPin();
    Object.assign(st, { tab: "inicio", person: "", confirmExit: false, boardReady: false, home: null, crm: null, notice: "", query: "", chip: "all", finish: null, crmNote: null });
    window.history.replaceState(LOGIN_ENTRY, "");
    draw();
    if (current) { try { await fetch(`${API}/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${current}` } }); } catch (_) { /* el corte diario la cierra */ } }
  }

  async function pdfList() {
    st.busy = true;
    st.crmNote = null;
    drawCrmBody();
    try {
      await downloadPdf(`crm/lista.pdf?lang=${lang()}`, `lista_asistencia_${BOOT.slug || "operacion"}.pdf`);
    } catch (error) { st.crmNote = { ok: false, text: serverText(error.message) }; }
    st.busy = false;
    if (st.tab === "crm") drawCrmBody();
  }

  async function finishNow() {
    const f = st.finish;
    if (!f || f.busy || f.step !== 2 || !f.confirmed) return; // sin los dos pasos no llega al servidor
    f.busy = true;
    draw();
    const where = await deviceLocation();
    if (!where) { st.finish = null; st.crmNote = { ok: false, text: T(NO_LOCATION) }; draw(); return; }
    try {
      const data = await send(`crm/${encodeURIComponent(f.id)}/finalizar`, where);
      if (!data) return;
      st.finish = null;
      st.crmNote = { ok: true, text: T("Turno de {name} finalizado a las {time}.", { name: data.name, time: data.at }) };
      closeDetail(); // al volver a la lista se recarga y muestra el aviso
      return;
    } catch (error) { st.crmNote = { ok: false, text: serverText(error.message) }; }
    st.finish = null;
    draw();
    loadCrm();
  }

  function onClick(event) {
    const t = event.target;
    if (!t || !t.closest) return;
    if (st.tab === "pin") touchPin();
    const attr = (name) => { const el = t.closest(`[${name}]`); return el ? el.getAttribute(name) : null; };
    let v;
    if ((v = attr("data-lo-lang"))) { setLang(v); draw(); return; }
    if (t.closest("[data-lo-theme-toggle]")) { toggleTheme(); return; }
    if ((v = attr("data-lo-tab"))) { go(v); return; }
    if (t.closest("[data-lo-exit-no]")) { st.confirmExit = false; draw(); return; }
    if (t.closest("[data-lo-exit-yes]")) { exit(); return; }
    if ((v = attr("data-lo-chip"))) { st.chip = st.chip === v ? "all" : v; drawCrmBody(); return; }
    if ((v = attr("data-lo-counter"))) { st.chip = v; go("crm"); return; }
    if (t.closest("[data-lo-pdf]")) { pdfList(); return; }
    if ((v = attr("data-lo-person"))) { openDetail(v); return; }
    if (t.closest("[data-lo-detail-close]")) { closeDetail(); return; }
    if ((v = attr("data-lo-finish"))) {
      const person = personOf(v);
      if (person && person.can_finish) { st.crmNote = null; st.finish = { id: person.id, name: person.name, step: 1, confirmed: false, busy: false }; draw(); }
      return;
    }
    if (t.closest("[data-lo-finish-no]")) { st.finish = null; draw(); return; }
    if (t.closest("[data-lo-finish-next]")) { if (st.finish) { st.finish.step = 2; st.finish.confirmed = false; draw(); } return; }
    if (t.closest("[data-lo-finish-yes]")) { finishNow(); return; }
    if ((v = attr("data-lo-close"))) { // 071A
      const person = personOf(v);
      if (person && person.can_close) {
        st.crmNote = null;
        st.close = { id: person.id, name: person.name, scheduled: person.scheduled_end || "", step: 1, choice: person.scheduled_end ? "scheduled" : "now", reason: "", detail: "", confirmed: false, busy: false, error: "" };
        draw();
      }
      return;
    }
    if (t.closest("[data-lo-close-no]")) { st.close = null; draw(); return; }
    if (t.closest("[data-lo-close-next]") && st.close) { const e = closeStep1(readStep1()); st.close.error = e; if (!e) { st.close.step = 2; st.close.confirmed = false; } draw(); return; }
    if (t.closest("[data-lo-close-yes]")) { closeNow(); return; }
    if (t.closest("[data-lo-horario]")) { openSchedule(); return; }
    if (t.closest("[data-lo-horario-close]")) { st.schedule = null; draw(); return; }
    if ((v = attr("data-lo-key"))) { pressKey(v); return; }
    if ((v = attr("data-lo-punch"))) { punch(v); return; }
    if (t.closest("[data-lo-pin-back]")) { backToKeypad(); return; }
    if (t.closest("[data-lo-exit]")) exit();
  }

  function onInput(event) {
    if (event.target && event.target.hasAttribute && event.target.hasAttribute("data-lo-search")) { st.query = event.target.value; drawCrmBody(); }
    if (event.target && event.target.hasAttribute && event.target.hasAttribute("data-lo-summary")) { pinState().summary = event.target.value; touchPin(); }
    if (event.target && event.target.hasAttribute && event.target.hasAttribute("data-lo-close-confirm") && st.close) {
      st.close.confirmed = Boolean(event.target.checked);
      const yes = document.querySelector("[data-lo-close-yes]");
      if (yes) yes.disabled = !st.close.confirmed;
    }
    if (event.target && event.target.hasAttribute && event.target.hasAttribute("data-lo-confirm") && st.finish) {
      st.finish.confirmed = Boolean(event.target.checked);
      const yes = document.querySelector("[data-lo-finish-yes]");
      if (yes) yes.disabled = !st.finish.confirmed;
    }
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
    if (event.key === "Escape" && st.confirmExit) { st.confirmExit = false; draw(); return; }
    if (event.key === "Escape" && st.finish && !st.finish.busy) { st.finish = null; draw(); return; }
    if (event.key === "Escape" && st.close && !st.close.busy) { st.close = null; draw(); return; }
    if (event.key === "Escape" && st.schedule) { st.schedule = null; draw(); return; }
    if (event.key === "Escape" && st.tab === "crm" && st.person && !st.finish && !st.close) { closeDetail(); return; }
    if (st.tab !== "pin" || st.confirmExit || (st.pin && st.pin.person)) return;
    if (/^\d$/.test(event.key)) pressKey(event.key);
    else if (event.key === "Backspace") pressKey("del");
    else if (event.key === "Enter") { event.preventDefault(); pressKey("ok"); }
  }

  async function start() {
    if (!appEl()) return;
    setLang(savedLang(), false);
    st.theme = savedTheme();
    applyBrand();
    document.addEventListener("click", onClick);
    document.addEventListener("input", onInput);
    document.addEventListener("submit", onSubmit);
    document.addEventListener("keydown", onKey);
    window.addEventListener("popstate", onPop);
    clockTimer = setInterval(tickClock, 5000);
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
      if (st.tab === "pin") checkDeviceLocation();
      return;
    }
    enterHistory();
    draw();
    loadHome();
  }

  window.CxLiderOperacion = { st, filterPeople, stateChip, homeView, crmList, loginView, serverText, savedLang, nav, TOKEN_KEY, clockTimer: () => clockTimer, go, onPop, enterHistory, exitDialog,
    pinView, pinState, pressKey, punch, checkPin, resetPin, touchPin, backToKeypad, finishDialog, finishNow, closeDialog, closeStep1, closeNow, scheduleView, openSchedule, stateChip, personRow, detailBody, detailView, openDetail, themeButton, toggleTheme, savedTheme, IDLE_MS };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
