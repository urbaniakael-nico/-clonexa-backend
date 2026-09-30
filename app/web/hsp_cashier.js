(() => {
  "use strict";

  const root = document.getElementById("app");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const PANEL_TYPE = "caja";
  const storageKey = `clonexa_cashier_token_${companyId}`;
  const navKey = `clonexa_cashier_nav_${companyId}`;
  const deviceKey = "clonexa_mini_panel_device_id";
  const POLL_MS = 4000;
  const TOKEN_REFRESH_MS = 25 * 60 * 1000;
  const RECONNECT_MS = 5000;
  const PAYMENT_METHODS = [
    { value: "cash", label: "Efectivo" },
    { value: "transfer", label: "Transferencia" },
    { value: "card", label: "Tarjeta" },
  ];

  const state = {
    screen: "login",
    error: "",
    toast: "",
    busy: false,
    tables: [],
    activeTableKey: "",
    menu: [],
    paying: false,
    tablesLoaded: false,
    // Facturacion directa: only when the company has the switch on (the
    // server answers /caja/config); otherwise the panel is exactly as before.
    directSale: false,
    knownTables: [],
    sale: { items: [], table: "", toKitchen: false, category: "" },
    saleBusy: false,
    quantityButtons: [],
    // 049W: selector de cantidad libre (entero + fraccion), interruptor quantity_picker.
    quantityPicker: false,
    menuEmojis: false,
    printing: false,
    // Last table/sale charged, so its cuenta can still be printed from the
    // tables list once it disappeared from it.
    lastCharged: null,
    stack: ["tables"],
    offline: false,
    offlineReason: "",
    // Turno de la caja (pausa / retomar / cerrar jornada), igual que el
    // mesero: mini_panel_work_sessions -> asistencia (CRM) y nomina.
    operational: null,
    operationalAt: 0,
    shiftOpen: false,
    shiftBusy: false,
    // Domicilios por WhatsApp (module domicilios_whatsapp): their own
    // section, one card per order, never mixed with the tables.
    delivery: false,
    deliveries: [],
    activeDeliveryId: "",
    drivers: [],
    driversOpen: false,
    deliveryBusy: false,
    // 048U/049M: arqueo a ciegas al cerrar la jornada (antes del modulo
    // Costos; ahora propio de la caja, hoy ASADERO). Sin el arqueo, nada cambia.
    costos: false,
    denominations: [],
    arqueo: null,
    // 049V: rediseno (interruptor cashier_redesign; apagado = panel de antes):
    // franja de indicadores del turno, secciones Mesas / Domicilios / Ventas
    // de caja, el Z del dia y la nueva venta en una sola pantalla.
    redesign: false,
    summary: null,
    summaryAt: 0,
    z: null,
    moreOpen: false,
  };

  let pollHandle = null;

  // Shared with the mesero panel (hsp_menu_kit.js) and the printable
  // document (sale_document.js); both load before this file.
  const Kit = window.CxMenuKit;
  const SaleDoc = window.CxSaleDocument;
  const { h, money, tableTitle } = Kit;
  // Sound + vibration + on-screen card until closed (hsp_alerts.js).
  const Alerts = window.CxAlerts ? window.CxAlerts.create("caja") : null;
  let alertMemory = null;   // what the last poll saw (null = first load)

  // ---------------------------------------------------------------------
  // Storage: same fix as the mesero panel. The session lives in
  // localStorage (sessionStorage was lost whenever the browser unloaded the
  // tab or the link was reopened, and the new login then kicked the
  // cashier's own open panel). Every access is wrapped: private modes throw.
  // ---------------------------------------------------------------------
  function storeGet(area, key) {
    try {
      return window[area].getItem(key);
    } catch (_) {
      return null;
    }
  }

  function storeSet(area, key, value) {
    try {
      if (value === null || value === undefined || value === "") window[area].removeItem(key);
      else window[area].setItem(key, value);
    } catch (_) {}
  }

  function storeJson(area, key) {
    try {
      const raw = storeGet(area, key);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function token() {
    const saved = storeGet("localStorage", storageKey);
    if (saved) return saved;
    const legacy = storeGet("sessionStorage", storageKey);
    if (legacy) {
      storeSet("localStorage", storageKey, legacy);
      storeSet("sessionStorage", storageKey, "");
    }
    return legacy || "";
  }

  function setToken(value) {
    storeSet("localStorage", storageKey, value || "");
    storeSet("sessionStorage", storageKey, "");
  }

  function deviceId() {
    let id = storeGet("localStorage", deviceKey);
    if (id && /^[A-Za-z0-9_-]{8,80}$/.test(id)) return id;
    let random = "";
    try {
      const bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      random = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    } catch (_) {
      random = `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
    }
    id = `d${random}`.slice(0, 40);
    storeSet("localStorage", deviceKey, id);
    return id;
  }

  // ---------------------------------------------------------------------
  // Connection: a dropped WiFi shows a bar and retries by itself; it never
  // logs the cashier out.
  // ---------------------------------------------------------------------
  let reconnectHandle = null;

  function markOffline(reason) {
    const changed = !state.offline || state.offlineReason !== reason;
    state.offline = true;
    state.offlineReason = reason || "network";
    if (changed) renderConnection();
    if (!reconnectHandle) reconnectHandle = window.setInterval(tryReconnect, RECONNECT_MS);
  }

  function markOnline() {
    if (!state.offline) return;
    state.offline = false;
    state.offlineReason = "";
    if (reconnectHandle) window.clearInterval(reconnectHandle);
    reconnectHandle = null;
    renderConnection();
    if (!state.menu.length) loadMenu();
    refreshTables();
  }

  function tryReconnect() {
    if (token()) refreshTables();
  }

  function connectionMessage(reason) {
    if (reason === "wifi") return "Sin conexión al WiFi del restaurante. Reintentando…";
    return "Sin conexión. Reintentando…";
  }

  function renderConnection() {
    const current = document.getElementById("cshNet");
    if (current) current.remove();
    if (!state.offline || state.screen === "login") return;
    const bar = document.createElement("div");
    bar.id = "cshNet";
    bar.className = "csh-net";
    bar.setAttribute("role", "status");
    bar.textContent = connectionMessage(state.offlineReason);
    document.body.appendChild(bar);
  }

  function sessionLostMessage(message) {
    if (/corte diario/i.test(String(message))) return "El sistema cerró tu turno en el corte diario. Vuelve a entrar con tu usuario y clave.";
    if (/otro dispositivo/i.test(String(message))) return "Tu sesión se abrió en otro dispositivo.";
    return "Tu sesión terminó. Vuelve a entrar.";
  }

  function handleSessionLost(message) {
    stopPolling();
    stopSessionKeeper();
    setToken("");
    state.offline = false;
    renderConnection();
    state.screen = "login";
    state.error = sessionLostMessage(message);
    safeRender();
  }

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    const tok = token();
    if (tok) headers.Authorization = `Bearer ${tok}`;
    let response;
    try {
      response = await fetch(path, { ...options, headers });
    } catch (_) {
      markOffline("network");
      throw new Error("Sin conexión. Reintentando…");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data.detail || data.message || "Solicitud rechazada.";
      if (response.status === 401 && tok && !options.isLogin) {
        handleSessionLost(message);
      } else if (response.status === 403 && /wifi/i.test(String(message))) {
        markOffline("wifi");
      } else if (response.status >= 500) {
        markOffline("network");
      } else {
        markOnline();
      }
      throw new Error(message);
    }
    markOnline();
    return data;
  }

  // ---------------------------------------------------------------------
  // Session keeper: renews the token every 25 min and when the screen comes
  // back, while the cashier's shift is open.
  // ---------------------------------------------------------------------
  let sessionKeeperHandle = null;

  async function refreshToken() {
    const sent = token();
    if (!sent) return;
    try {
      const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-refresh?panel_type=${PANEL_TYPE}`, { method: "POST" });
      // A renewal answering after a 401/logout must not revive the session.
      if (data && data.access_token && token() === sent) setToken(data.access_token);
    } catch (_) {
      // 409 turno_cerrado / offline: keep the current token.
    }
  }

  function startSessionKeeper() {
    stopSessionKeeper();
    refreshToken();
    sessionKeeperHandle = window.setInterval(refreshToken, TOKEN_REFRESH_MS);
  }

  function stopSessionKeeper() {
    if (sessionKeeperHandle) window.clearInterval(sessionKeeperHandle);
    sessionKeeperHandle = null;
  }

  // ---------------------------------------------------------------------
  // Navigation: every screen is a browser history entry, so the phone's
  // back button returns mesa -> mesas instead of leaving the app. Entries:
  // [base] [tables, depth 0] [depth 1] ...
  // ---------------------------------------------------------------------
  let historyReady = false;
  let ignorePops = 0;

  function persistNav() {
    storeSet("sessionStorage", navKey, JSON.stringify({ stack: state.stack, activeTableKey: state.activeTableKey, activeDeliveryId: state.activeDeliveryId }));
  }

  function historyPush(depth) {
    try {
      window.history.pushState({ cshDepth: depth }, "");
    } catch (_) {}
  }

  function installHistory() {
    try {
      const current = window.history.state;
      if (current && typeof current.cshDepth === "number") {
        const nav = storeJson("sessionStorage", navKey);
        if (nav && Array.isArray(nav.stack) && nav.stack[0] === "tables" && nav.stack.length === current.cshDepth + 1) {
          state.stack = nav.stack;
          state.screen = nav.stack[nav.stack.length - 1];
          state.activeTableKey = nav.activeTableKey || "";
          state.activeDeliveryId = nav.activeDeliveryId || "";
        } else if (current.cshDepth > 0) {
          ignorePops += 1;
          window.history.go(-current.cshDepth);
        }
      } else {
        if (!current || !current.cshBase) window.history.replaceState({ cshBase: true }, "");
        historyPush(0);
      }
      historyReady = true;
    } catch (_) {
      historyReady = false;
    }
  }

  function goto(screen) {
    state.stack.push(screen);
    state.screen = screen;
    persistNav();
    if (historyReady) {
      const current = window.history.state;
      if (current && current.cshBase) historyPush(0);
      historyPush(state.stack.length - 1);
    }
    safeRender();
  }

  function back() {
    if (historyReady) {
      window.history.back();
      return;
    }
    if (state.stack.length > 1) state.stack.pop();
    state.screen = state.stack[state.stack.length - 1];
    persistNav();
    safeRender();
  }

  function resetToTables() {
    const steps = state.stack.length - 1;
    state.stack = ["tables"];
    state.screen = "tables";
    state.activeTableKey = "";
    persistNav();
    if (historyReady && steps > 0) {
      ignorePops += 1;
      window.history.go(-steps);
    }
    safeRender();
  }

  function closeOpenSheets() {
    const sheets = document.querySelectorAll(".csh-sheet-backdrop");
    sheets.forEach((sheet) => sheet.remove());
    return sheets.length > 0;
  }

  function popAction(historyState, stackLength, screen, sheetOpen) {
    if (screen === "login") return { type: "ignore" };
    if (sheetOpen) return { type: "close_sheet", depth: stackLength - 1 };
    if (historyState && typeof historyState.cshDepth === "number") {
      return { type: "go", depth: Math.max(0, Math.min(historyState.cshDepth, stackLength - 1)) };
    }
    return { type: "leave" };
  }

  function onPopState(event) {
    if (ignorePops > 0) {
      ignorePops -= 1;
      return;
    }
    const sheetOpen = document.querySelectorAll(".csh-sheet-backdrop").length > 0;
    const action = popAction(event.state, state.stack.length, state.screen, sheetOpen);
    if (action.type === "close_sheet") {
      closeOpenSheets();
      historyPush(action.depth);
      return;
    }
    if (action.type === "go") {
      state.stack = state.stack.slice(0, action.depth + 1);
      state.screen = state.stack[action.depth];
      if (state.screen === "tables") state.activeTableKey = "";
      persistNav();
      safeRender();
      return;
    }
    if (action.type === "leave") window.history.back();
  }

  function hspApi(path, options) {
    return api(`/api/v1/hospitality/companies/${encodeURIComponent(companyId)}${path}`, options);
  }

  function waiterApi(path, options) {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}/waiter-ordering${path}`, options);
  }

  function mpApi(path, options) {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}${path}`, options);
  }

  // ---------------------------------------------------------------------
  // Turno: entering the panel opens (or reuses) the cashier's work session,
  // exactly like the mesero; the server syncs every change to Workforce
  // attendance, which feeds the CRM and payroll.
  // ---------------------------------------------------------------------
  function setOperational(data) {
    state.operational = (data && data.operational_session) || null;
    state.operationalAt = Date.now();
  }

  async function loadOperational() {
    try {
      setOperational(await mpApi(`/mini-panel-operational-session?panel_type=${PANEL_TYPE}`));
    } catch (_) {
      // transient: keep the last snapshot
    }
    backgroundRender049X();
  }

  function liveShiftSeconds() {
    const op = state.operational;
    if (!op) return { active: 0, pause: 0 };
    const elapsed = Math.max(0, Math.floor((Date.now() - state.operationalAt) / 1000));
    const onBreak = op.status === "break";
    return {
      active: Number(op.active_seconds || 0) + (onBreak ? 0 : elapsed),
      pause: Number(op.break_seconds || 0) + (onBreak ? elapsed : 0),
    };
  }

  function clockLabel(totalSeconds) {
    const seconds = Math.max(0, Math.floor(Number(totalSeconds || 0)));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  }

  function shiftBarHtml() {
    const op = state.operational;
    if (!op) return "";
    const onBreak = op.status === "break";
    const live = liveShiftSeconds();
    return `
      <div class="csh-shift ${onBreak ? "is-break" : ""}">
        <button class="csh-shift-chip" type="button" data-csh-shift-toggle aria-expanded="${state.shiftOpen ? "true" : "false"}">
          <span>${onBreak ? "⏸ En pausa" : "⏱ En turno"}</span>
          <strong data-csh-shift-clock>${h(clockLabel(onBreak ? live.pause : live.active))}</strong>
          <small>${state.shiftOpen ? "▲" : "▾"}</small>
        </button>
        ${state.shiftOpen ? `
          <div class="csh-shift-panel">
            <div class="csh-shift-times">
              <div><span>Activo</span><strong data-csh-active-clock>${h(clockLabel(live.active))}</strong></div>
              <div><span>Pausa</span><strong data-csh-break-clock>${h(clockLabel(live.pause))}</strong></div>
            </div>
            <div class="csh-shift-actions">
              ${onBreak
                ? `<button class="csh-btn csh-btn-primary" type="button" data-csh-shift-resume ${state.shiftBusy ? "disabled" : ""}>Retomar</button>`
                : `<button class="csh-btn" type="button" data-csh-shift-pause ${state.shiftBusy ? "disabled" : ""}>Pausa</button>`}
              <button class="csh-btn csh-btn-danger" type="button" data-csh-shift-finish ${state.shiftBusy ? "disabled" : ""}>Cerrar jornada</button>
            </div>
          </div>` : ""}
      </div>`;
  }

  function tickShiftClock() {
    if (!state.operational || state.screen === "login") return;
    const live = liveShiftSeconds();
    const onBreak = state.operational.status === "break";
    const set = (selector, value) => {
      const node = root.querySelector ? root.querySelector(selector) : null;
      if (node) node.textContent = clockLabel(value);
    };
    set("[data-csh-shift-clock]", onBreak ? live.pause : live.active);
    set("[data-csh-active-clock]", live.active);
    set("[data-csh-break-clock]", live.pause);
  }

  async function shiftAction(action) {
    if (state.shiftBusy) return;
    state.shiftBusy = true;
    safeRender();
    try {
      setOperational(await mpApi(`/mini-panel-operational-session/${action}?panel_type=${PANEL_TYPE}`, { method: "POST" }));
      if (action === "finish") {
        // Jornada cerrada: log out so the next login opens a new one.
        stopPolling();
        stopSessionKeeper();
        setToken("");
        state.operational = null;
        state.shiftOpen = false;
        state.screen = "login";
        state.error = "Jornada cerrada. Tus horas quedaron registradas.";
      }
    } catch (error) {
      state.error = error.message || "No se pudo actualizar el turno.";
    } finally {
      state.shiftBusy = false;
      safeRender();
    }
  }

  async function doLogin(username, password) {
    state.busy = true;
    state.error = "";
    render();
    try {
      const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-login`, {
        method: "POST",
        isLogin: true,
        body: JSON.stringify({ username, password, panel_type: PANEL_TYPE, device_id: deviceId() }),
      });
      setToken(data.access_token || "");
      state.stack = ["tables"];
      state.screen = "tables";
      installHistory();
      startPolling();
      startSessionKeeper();
      loadMenu();
      loadCashierConfig();
      loadOperational();
    } catch (error) {
      state.error = error.message || "No se pudo iniciar sesión.";
    } finally {
      state.busy = false;
      render();
    }
  }

  function costosApi048U(path, options) {
    return api(`/api/v1/caja-arqueo/companies/${encodeURIComponent(companyId)}${path}`, options);
  }

  async function loadCostosConfig048U() {
    try {
      const data = await costosApi048U("/caja/config");
      state.costos = data.enabled === true;
      state.denominations = Array.isArray(data.denominations) ? data.denominations : [];
    } catch (_) {
      state.costos = false;
    }
  }

  async function openArqueo048U() {
    state.arqueo = { step: "loading", busy: false, result: null, message: "", failed: false, draft: { total: "", dens: {}, obs: "" } };
    safeRender();
    try {
      const current = await costosApi048U("/caja/arqueo");
      // 049Y: si el turno ya tiene arqueo no se pide contar otra vez: se
      // muestra el registrado y se sigue directo al cierre.
      if (current && current.count) {
        state.arqueo.result = { ...current.count, already_registered: true };
        state.arqueo.step = "result";
      } else {
        state.arqueo.step = "count";
      }
    } catch (_) {
      if (state.arqueo) state.arqueo.step = "count";
    }
    safeRender();
  }

  function money048U(value) {
    return `$${Math.round(Number(value) || 0).toLocaleString("es-CO")}`;
  }

  function costosOverlay048U() {
    const a = state.arqueo;
    if (a) {
      if (a.step !== "count" && a.step !== "result") return closeOverlay049Y(a);
      if (a.step === "count") {
        return `<div class="csh-modal-048u" data-csh-arqueo>
          <div class="csh-modal-card-048u">
            <h2>Arqueo de caja</h2>
            <p>Cuenta el efectivo del cajón y escribe cuánto hay. <b>No vas a ver cuánto debería haber</b> hasta registrar tu conteo, y el conteo no se puede cambiar después.</p>
            <label>Total contado<input type="text" inputmode="numeric" autocomplete="off" data-csh-arq-total placeholder="$ contado" value="${h(arqDraft049X().total)}"></label>
            <small class="csh-arq-read-049x" data-csh-arq-read>${h(arqReading049X(arqDraft049X().total))}</small>
            <details><summary>Contar por billetes y monedas (opcional)</summary>
              <div class="csh-den-048u">${state.denominations.map((d) => `<label>${money048U(d)}<input type="text" inputmode="numeric" autocomplete="off" data-csh-den="${d}" placeholder="0" value="${h(arqDraft049X().dens[d] || "")}"></label>`).join("")}</div>
            </details>
            ${a.message ? `<div class="csh-alert">${h(a.message)}</div>` : ""}
            <div class="csh-modal-actions-048u">
              <button class="csh-btn" type="button" data-csh-arq-cancel ${a.busy ? "disabled" : ""}>Volver</button>
              <button class="csh-btn csh-btn-primary" type="button" data-csh-arq-submit ${a.busy ? "disabled" : ""}>Registrar conteo</button>
            </div>
            ${a.failed ? `<div class="csh-modal-actions-048u"><button class="csh-btn csh-btn-danger" type="button" data-csh-arq-skip ${a.busy ? "disabled" : ""}>Continuar al cierre sin arqueo</button></div>
            <small>Queda anotado lo que pasó para que el administrador haga el arqueo de este turno.</small>` : ""}
          </div></div>`;
      }
      const r = a.result || {};
      const diff = Number(r.difference || 0);
      return `<div class="csh-modal-048u" data-csh-arqueo>
        <div class="csh-modal-card-048u">
          <h2>${r.already_registered ? "Arqueo ya registrado" : "Resultado del arqueo"}</h2>
          ${r.already_registered ? `<p>Este turno ya tiene su arqueo${r.created_at ? ` (${h(new Date(r.created_at).toLocaleString("es-CO"))})` : ""}. No hay que contar otra vez: sigue al cierre.</p>` : ""}
          <div class="csh-arq-rows-048u">
            <div><span>Contaste</span><b>${money048U(r.counted)}</b></div>
            <div><span>Debía haber</span><b>${money048U(r.expected)}</b></div>
            <small>Base ${money048U(r.base)} + ventas en efectivo ${money048U(r.cash_sales)}${Number(r.drawer_expenses || 0) || Number(r.withdrawals || 0) ? ` − gastos del cajón ${money048U(r.drawer_expenses)} − retiros ${money048U(r.withdrawals)}` : ""}</small>
            <div class="${diff < 0 ? "bad" : diff > 0 ? "warn" : "ok"}"><span>${diff === 0 ? "Cuadra" : diff < 0 ? "Faltante" : "Sobrante"}</span><b>${money048U(Math.abs(diff))}</b></div>
          </div>
          ${r.needs_observation ? `<label>Explica la diferencia (obligatorio)<textarea data-csh-arq-obs rows="3">${h(arqDraft049X().obs)}</textarea></label>` : ""}
          ${a.message ? `<div class="csh-alert">${h(a.message)}</div>` : ""}
          <div class="csh-modal-actions-048u">
            ${r.needs_observation
              ? `<button class="csh-btn csh-btn-primary" type="button" data-csh-arq-save-obs ${a.busy ? "disabled" : ""}>Guardar y continuar</button>`
              : `<button class="csh-btn csh-btn-danger" type="button" data-csh-arq-finish ${a.busy ? "disabled" : ""}>Continuar al cierre</button>`}
            ${r.needs_observation && a.failed ? `<button class="csh-btn" type="button" data-csh-arq-finish ${a.busy ? "disabled" : ""}>Continuar sin observación</button>` : ""}
          </div>
        </div></div>`;
    }
    return "";
  }

  // 049X: lo escrito en el arqueo vive en el estado, no solo en la pantalla:
  // ningún redibujo (el sondeo de mesas cada 4 s) lo puede borrar. Solo
  // dígitos; el formato de pesos se muestra aparte y nunca toca el campo.
  function arqDraft049X() {
    const a = state.arqueo;
    if (!a) return { total: "", dens: {}, obs: "" };
    if (!a.draft) a.draft = { total: "", dens: {}, obs: "" };
    return a.draft;
  }

  function digits049X(value) {
    return String(value ?? "").replace(/[^0-9]/g, "");
  }

  function arqReading049X(total) {
    const clean = digits049X(total);
    return clean ? `Son ${money048U(Number(clean))}` : "";
  }

  async function submitCount048U() {
    const a = state.arqueo;
    const draft = arqDraft049X();
    const denominations = {};
    Object.entries(draft.dens).forEach(([d, v]) => { const n = Number(digits049X(v) || 0); if (n > 0) denominations[d] = n; });
    const total = digits049X(draft.total);
    if (!Object.keys(denominations).length && total === "") {
      a.message = "Escribe cuánto efectivo contaste.";
      safeRender();
      return;
    }
    a.busy = true;
    safeRender();
    try {
      const body = Object.keys(denominations).length ? { denominations } : { counted: Number(total) };
      a.result = await costosApi048U("/caja/arqueo", { method: "POST", body: JSON.stringify(body) });
      a.step = "result";
      a.message = "";
      a.failed = false;
    } catch (error) {
      // 049Y: un error nunca deja al cajero atrapado: puede seguir al cierre.
      a.message = `${error.message || "No se pudo registrar el conteo."} Puedes intentar de nuevo o continuar al cierre.`;
      a.failed = true;
    } finally {
      a.busy = false;
      safeRender();
    }
  }

  async function saveObservation048U() {
    const a = state.arqueo;
    const observation = String(arqDraft049X().obs || "").trim();
    if (!observation) {
      a.message = "La observación es obligatoria cuando hay diferencia.";
      safeRender();
      return;
    }
    a.busy = true;
    safeRender();
    try {
      await costosApi048U(`/caja/arqueo/${encodeURIComponent(a.result.id)}/observation`, { method: "POST", body: JSON.stringify({ observation }) });
      a.busy = false;
      continueClose049Y();
    } catch (error) {
      a.message = `${error.message || "No se pudo guardar la observación."} Puedes continuar al cierre igual.`;
      a.failed = true;
      a.busy = false;
      recordIncident049Y("observacion", error.message || "", null);
      safeRender();
    }
  }

  // ------------------------------------------------ 049Y: cierre de jornada
  // Arqueo (si falta) -> Z (se puede sacar e imprimir cuantas veces se
  // quiera) -> cerrar sesion. Ningun paso bloquea: si algo falla se dice, se
  // anota para el dueño y el cajero puede seguir.
  function recordIncident049Y(step, error, counted) {
    const body = { step: String(step || ""), error: String(error || "").slice(0, 1000) };
    if (counted !== null && counted !== undefined && counted !== "") body.counted = Number(counted);
    return costosApi048U("/caja/cierre/incidencia", { method: "POST", body: JSON.stringify(body) }).catch(() => null);
  }

  function skipCount049Y() {
    const a = state.arqueo;
    if (!a) return;
    const total = digits049X(arqDraft049X().total);
    recordIncident049Y("arqueo", a.message || "No se pudo registrar el arqueo.", total === "" ? null : Number(total));
    continueClose049Y();
  }

  async function continueClose049Y() {
    const a = state.arqueo || (state.arqueo = { step: "", busy: false, result: null, message: "", failed: false, draft: { total: "", dens: {}, obs: "" } });
    a.message = "";
    a.failed = false;
    if (!state.redesign) {
      a.step = "closing";
      finishClose049Y();
      return;
    }
    a.step = "z";
    a.zData = null;
    a.zSaved = null;
    a.zLoading = true;
    safeRender();
    try {
      a.zData = await waiterApi("/caja/z");
    } catch (error) {
      a.message = `${error.message || "No se pudo calcular el Z."} Puedes cerrar la jornada igual.`;
      recordIncident049Y("z", error.message || "", null);
    } finally {
      a.zLoading = false;
      safeRender();
    }
  }

  async function takeZ049Y() {
    const a = state.arqueo;
    if (!a || a.busy) return;
    a.busy = true;
    a.message = "";
    safeRender();
    try {
      const saved = await waiterApi("/caja/z", { method: "POST" });
      a.zSaved = saved;
      if (a.zData && Array.isArray(a.zData.history)) a.zData.history.unshift(saved);
      printZ049V(saved);
    } catch (error) {
      a.message = `${error.message || "No se pudo sacar el Z."} Puedes intentar de nuevo o cerrar la jornada igual.`;
      recordIncident049Y("z", error.message || "", null);
    } finally {
      a.busy = false;
      safeRender();
    }
  }

  function logoutAfterClose049Y(message) {
    stopPolling();
    stopSessionKeeper();
    setToken("");
    state.operational = null;
    state.shiftOpen = false;
    state.arqueo = null;
    state.z = null;
    state.screen = "login";
    state.error = message;
    safeRender();
  }

  async function finishClose049Y() {
    const a = state.arqueo;
    if (a) { a.step = "closing"; a.busy = true; a.message = ""; }
    safeRender();
    try {
      setOperational(await mpApi(`/mini-panel-operational-session/finish?panel_type=${PANEL_TYPE}`, { method: "POST" }));
      logoutAfterClose049Y("Jornada cerrada. Tus horas quedaron registradas.");
    } catch (error) {
      recordIncident049Y("cierre", error.message || "", null);
      if (!state.arqueo) return;
      state.arqueo.busy = false;
      state.arqueo.message = `${error.message || "No se pudo cerrar el turno."} Puedes reintentar o salir igual (queda anotado).`;
      safeRender();
    }
  }

  function closeOverlay049Y(a) {
    let inner = "";
    let title = "Cerrar jornada";
    if (a.step === "loading") inner = `<p>Revisando el arqueo del turno…</p>`;
    else if (a.step === "z") {
      title = "🧾 Cierre de caja · Z";
      const d = a.zData;
      const saved = a.zSaved;
      inner = `
        ${a.zLoading ? `<p>Calculando el Z del día…</p>` : ""}
        ${saved ? `<div class="cx5-z-done">✓ Z #${h(String(saved.number || "").padStart(4, "0"))} registrado · ${h(saved.created_local || "")} · ${h(saved.cashier_name || "")}</div>` : ""}
        ${d ? `<p class="cx5-hint">Ventas cobradas desde ${h(d.since_local || "")} · Cajero: <b>${h(d.cashier_name || "")}</b></p>${zBody049V((saved && saved.summary) || d.z || {})}` : ""}
        ${a.message ? `<div class="csh-alert">${h(a.message)}</div>` : ""}
        <p class="cx5-hint">El Z se puede sacar las veces que quieras: cada uno queda con su número, fecha, hora y cajero. Sacarlo no es obligatorio para cerrar.</p>
        ${d ? zHistory049V(d.history) : ""}
        <div class="csh-modal-actions-048u">
          ${d ? `<button class="csh-btn" type="button" data-csh-close-z ${a.busy ? "disabled" : ""}>${a.busy ? "Registrando…" : saved ? "🧾 Sacar otro Z" : "🧾 Sacar e imprimir Z"}</button>` : ""}
          ${saved ? `<button class="csh-btn" type="button" data-csh-close-z-print ${a.busy ? "disabled" : ""}>🖨 Imprimir de nuevo</button>` : ""}
          <button class="csh-btn csh-btn-danger" type="button" data-csh-close-finish ${a.busy ? "disabled" : ""}>Cerrar jornada</button>
        </div>`;
    } else if (a.step === "closing") {
      inner = `
        ${a.busy ? `<p>Cerrando la jornada…</p>` : ""}
        ${a.message ? `<div class="csh-alert">${h(a.message)}</div>` : ""}
        ${a.busy ? "" : `<div class="csh-modal-actions-048u">
          <button class="csh-btn" type="button" data-csh-close-finish>Reintentar</button>
          <button class="csh-btn csh-btn-danger" type="button" data-csh-close-leave>Salir igual</button>
        </div>`}`;
    }
    return `<div class="csh-modal-048u" data-csh-arqueo>
      <div class="csh-modal-card-048u" role="dialog" aria-label="${h(title)}">
        <h2>${h(title)}</h2>
        ${inner}
      </div></div>`;
  }

  async function loadCashierConfig() {
    loadCostosConfig048U();
    try {
      const data = await waiterApi("/caja/config");
      state.directSale = data.direct_sale === true;
      state.delivery = data.delivery === true;
      state.redesign = data.redesign === true;
    } catch (_) {
      state.directSale = false;
      state.delivery = false;
      state.redesign = false;
    }
    // 049V: colores y tema de la empresa (solo con su interruptor).
    if (window.CxPanelBrand) window.CxPanelBrand.load((path) => waiterApi(path)).then(() => safeRender());
    if (state.redesign) loadSummary049V();
    if (state.directSale) {
      try {
        const data = await hspApi("/qr-tables?count=30&include_bar=false");
        state.knownTables = (Array.isArray(data.tables) ? data.tables : []).map((t) => String(t.label || "")).filter(Boolean);
      } catch (_) {
        state.knownTables = [];
      }
    }
    safeRender();
  }

  // 049V: indicadores del turno + ventas de caja del turno (servidor). Se
  // piden al entrar, cada 15 s con el sondeo y enseguida despues de cobrar.
  const SUMMARY_MS = 15000;
  let summaryInFlight = false;

  async function loadSummary049V() {
    if (!state.redesign || summaryInFlight) return;
    summaryInFlight = true;
    try {
      state.summary = await waiterApi("/caja/resumen");
      state.summaryAt = Date.now();
    } catch (_) {
      // se queda la ultima franja
    } finally {
      summaryInFlight = false;
    }
    if (state.screen === "tables") backgroundRender049X();
  }

  function staleSummary049V() {
    state.summaryAt = 0;
  }

  // ---------------------------------------------------------------------
  // Nueva venta: the SAME flow as the mesero panel (categories with photo or
  // emoji -> products -> product sheet with fractions only where the
  // product allows portions, observations -> cart), built from the shared
  // kit. The caja keeps its own: destino, "Enviar a cocina" and cobro.
  // ---------------------------------------------------------------------
  function kitOptions(attr) {
    return { companyId, emojis: state.menuEmojis, attr };
  }

  function saleTotal(sale) {
    return Kit.cartTotal(sale.items);
  }

  function saleCategory() {
    return state.menu.find((cat) => cat.key === state.sale.category) || null;
  }

  function openSaleItemSheet(product, category, portionLabel, prefill, editIndex) {
    Kit.openItemSheet({
      product,
      category,
      portionLabel,
      prefill,
      quantityButtons: state.quantityButtons,
      quantityPicker: state.quantityPicker,
      addLabel: "Agregar a la venta",
      menuProductId: Kit.findMenuProduct(state.menu, product.id) ? product.id : undefined,
      onAdd: (line) => {
        if (editIndex === null || editIndex === undefined) state.sale.items.push(line);
        else state.sale.items[editIndex] = line;
        syncKitchen049V();
        safeRender();
      },
    });
  }

  function openSaleProduct(productId) {
    let category = saleCategory();
    let product = (category ? category.products || [] : []).find((item) => item.id === productId);
    if (!product && state.redesign) {
      // 049V: el buscador muestra platos de todas las categorias.
      const found = Kit.findMenuProduct(state.menu, productId);
      if (found) ({ product, category } = found);
    }
    if (!product) return;
    if (Kit.productOpenMode(product, state.quantityButtons) === "portions") {
      Kit.openPortionSheet(product, (portionProduct, label) => openSaleItemSheet(portionProduct, category, label));
    } else {
      openSaleItemSheet(product, category, null);
    }
  }

  function editSaleLine(index) {
    const line = state.sale.items[index];
    if (!line) return;
    const found = line.menu_product_id ? Kit.findMenuProduct(state.menu, line.menu_product_id) : null;
    if (found) openSaleItemSheet(found.product, found.category, null, line, index);
    else openSaleItemSheet({ id: line.inventory_item_id, name: line.name, price: line.unit_price }, null, line.portion_label || null, line, index);
  }

  // What the bottom of the sale screen offers: an independent sale that is
  // not going to the kitchen is charged right here (payment buttons);
  // anything else is a single "send" button.
  function saleMode(sale) {
    if (!sale.table && !sale.toKitchen) return "charge";
    return sale.toKitchen ? "kitchen" : "table";
  }

  function salePayload(sale, paymentMethod) {
    return {
      table: sale.table || "",
      send_to_kitchen: Boolean(sale.toKitchen),
      payment_method: saleMode(sale) === "charge" ? paymentMethod : null,
      items: sale.items.map(Kit.orderItemPayload),
    };
  }

  function saleDoneMessage(result, sale) {
    if (result && result.charged) return `${result.label || "Venta"} cobrada.`;
    if (sale.toKitchen) return `${result && result.label ? result.label : sale.table} enviado a cocina.`;
    return `Agregado a ${sale.table}.`;
  }

  function openSale(table) {
    state.sale = { items: [], table: table || "", toKitchen: false, category: "", kitchenTouched: false, query: "" };
    goto("sale");
  }

  function openSaleCategory(key) {
    state.sale.category = key || "";
    if (state.redesign) {
      // 049V: categorias y platos en la misma pantalla (sin otra pagina).
      state.sale.query = "";
      safeRender();
      return;
    }
    goto("sale_products");
  }

  async function submitSale(paymentMethod, cash) {
    const sale = state.sale;
    if (!sale.items.length || state.saleBusy) return;
    state.saleBusy = true;
    safeRender();
    try {
      const result = await waiterApi("/caja/ventas", { method: "POST", body: JSON.stringify(salePayload(sale, paymentMethod)) });
      state.toast = `${saleDoneMessage(result, sale)}${cash && result && result.charged ? ` Cambio: ${money(cash.change)}.` : ""}`;
      if (result && result.charged && result.order && result.order.id) {
        state.lastCharged = { order_ids: [result.order.id], label: result.label || "Venta" };
      }
      state.sale = { items: [], table: "", toKitchen: false, category: "" };
      staleSummary049V();
      resetToTables();
      await refreshTables();
    } catch (error) {
      // The sale stays on screen so the cashier can retry.
      state.error = error.message || "No se pudo registrar la venta.";
    } finally {
      state.saleBusy = false;
      safeRender();
    }
  }

  async function loadMenu() {
    try {
      const data = await waiterApi("/menu");
      state.menu = Array.isArray(data.categories) ? data.categories : [];
      state.quantityButtons = Array.isArray(data.quantity_buttons) ? data.quantity_buttons : [];
      state.quantityPicker = data.quantity_picker === true;
      state.menuEmojis = data.menu_emojis === true;
    } catch (_) {
      state.menu = [];
    }
  }

  function normKey(value) {
    return String(value || "").trim().toLowerCase();
  }

  async function refreshTables() {
    try {
      const data = await hspApi("/orders?status=active");
      const orders = Array.isArray(data.orders) ? data.orders : [];
      const groups = new Map();
      const deliveries = [];
      orders.forEach((order) => {
        if (isDelivery(order)) {
          deliveries.push(order);
          return;
        }
        const key = normKey(order.table_key || order.table_number);
        if (!groups.has(key)) {
          groups.set(key, { key, table_number: order.table_number, orders: [], total: 0, waiter: "" });
        }
        const bucket = groups.get(key);
        bucket.orders.push(order);
        bucket.total += Number(order.total || 0);
        const waiter = order.metadata && order.metadata.waiter ? order.metadata.waiter.name : "";
        if (waiter && !bucket.waiter) bucket.waiter = waiter;
      });
      state.tables = sortTablesByAge(Array.from(groups.values()), Date.now());
      state.deliveries = deliveries.sort((a, b) => (Date.parse(a.created_at) || 0) - (Date.parse(b.created_at) || 0));
      state.tablesLoaded = true;
      if (state.redesign && Date.now() - state.summaryAt > SUMMARY_MS) loadSummary049V();
      const detected = cajaAlerts(alertMemory, [...state.tables, ...state.deliveries.map(deliveryAsTable)]);
      alertMemory = detected.memory;
      if (Alerts) detected.alerts.forEach((alert) => Alerts.notify(alert));
      // Never redraw the sale screens from the 4s poll: it would close the
      // destination list or a product sheet mid-choice.
      if (!/^sale/.test(state.screen)) backgroundRender049X();
    } catch (_) {
      // keep last board on transient errors
    }
  }

  function startPolling() {
    stopPolling();
    refreshTables();
    pollHandle = window.setInterval(refreshTables, POLL_MS);
  }

  function stopPolling() {
    if (pollHandle) window.clearInterval(pollHandle);
    pollHandle = null;
  }

  function activeTable() {
    return state.tables.find((t) => t.key === state.activeTableKey) || null;
  }

  // ---------------------------------------------------------------------
  // Mesas abiertas: one card per table with its timer (since its first
  // order), mesero, total and its state FOR THE CAJA:
  //   - "En preparación": some comanda still pendiente/alistando.
  //   - "Listo para cobrar": everything left the kitchen -- whether or not
  //     the kitchen already marked it Entregado at the table. It stays like
  //     this until the caja confirms the payment method and closes it; only
  //     then it leaves the board. The caja never shows "Entregado".
  // Oldest table first.
  // ---------------------------------------------------------------------
  const TABLE_STATES = {
    preparing: "En preparación",
    ready: "Listo para cobrar",
  };

  function tableState(table) {
    const orders = table.orders || [];
    return orders.some((o) => o.status === "pendiente" || o.status === "alistando") ? "preparing" : "ready";
  }

  // What changed since the last poll, for the caja alerts:
  //   - new_sale: an order that wasn't there before (from a mesero or the QR;
  //     the caja's own sales are not announced back to it);
  //   - to_charge: a table that went from "En preparación" to "Listo para
  //     cobrar".
  // The first load only records what is already on screen.
  function cajaAlerts(memory, tables) {
    const orderIds = [];
    const states = {};
    tables.forEach((table) => {
      states[table.key] = tableState(table);
      (table.orders || []).forEach((order) => {
        if (!(order.metadata && order.metadata.cashier_sale)) orderIds.push(order.id);
      });
    });
    const alerts = [];
    if (memory) {
      tables.forEach((table) => {
        const fresh = (table.orders || []).filter((o) => orderIds.includes(o.id) && !memory.orderIds.has(o.id));
        if (fresh.length) {
          alerts.push({
            kind: "new_sale",
            title: `Venta nueva · ${tableTitle(table.table_number)}`,
            message: `${table.waiter ? `${table.waiter} · ` : ""}${money(fresh.reduce((sum, o) => sum + Number(o.total || 0), 0))}`,
          });
        }
        if (states[table.key] === "ready" && memory.states[table.key] === "preparing") {
          alerts.push({ kind: "to_charge", title: `${tableTitle(table.table_number)} lista para cobrar`, message: money(table.total) });
        }
      });
    }
    const seen = new Set(memory ? memory.orderIds : []);
    orderIds.forEach((id) => seen.add(id));
    return { alerts, memory: { orderIds: seen, states } };
  }

  // ---------------------------------------------------------------------
  // Cobro en efectivo: amount received, change in big letters while typing,
  // quick Colombian bills, "monto exacto", and "Enviar" locked (with how
  // much is missing) until the amount covers the total. Only for Efectivo:
  // Transferencia and Tarjeta charge directly.
  // ---------------------------------------------------------------------
  const CASH_BILLS = [10000, 20000, 50000, 100000];

  function parseCash(value) {
    const digits = String(value ?? "").replace(/[^0-9]/g, "");
    return digits ? Number(digits) : 0;
  }

  function cashChange(total, received) {
    const due = Math.round(Number(total || 0));
    const got = Math.round(Number(received || 0));
    return got >= due ? { ok: true, change: got - due, missing: 0 } : { ok: false, change: 0, missing: due - got };
  }

  function cashStatusHtml(total, received) {
    const result = cashChange(total, received);
    if (result.ok) return `<span>Cambio</span><strong>${h(money(result.change))}</strong>`;
    return `<span>Faltan</span><strong class="csh-cash-missing">${h(money(result.missing))}</strong>`;
  }

  function openCashSheet({ total, label, onConfirm }) {
    let received = 0;
    const sheet = document.createElement("div");
    sheet.className = "csh-sheet-backdrop csh-cash-backdrop";
    sheet.innerHTML = `
      <div class="csh-sheet csh-cash">
        <h2>Cobro en efectivo · ${h(label)}</h2>
        <div class="csh-cash-total"><span>Total a cobrar</span><strong>${h(money(total))}</strong></div>
        <label class="csh-cash-label">Monto recibido
          <input id="cshCashReceived" inputmode="numeric" autocomplete="off" placeholder="0" />
        </label>
        <div class="csh-cash-bills">
          ${CASH_BILLS.map((bill) => `<button type="button" class="csh-btn" data-cash-bill="${bill}">+ ${h(money(bill))}</button>`).join("")}
          <button type="button" class="csh-btn" data-cash-exact>Monto exacto</button>
          <button type="button" class="csh-btn csh-btn-mini" data-cash-clear>Borrar</button>
        </div>
        <div class="csh-cash-change" id="cshCashChange">${cashStatusHtml(total, 0)}</div>
        <div class="csh-cash-actions">
          <button type="button" class="csh-btn" data-sheet-cancel>Cancelar</button>
          <button type="button" class="csh-btn csh-btn-primary" data-cash-send disabled>Enviar</button>
        </div>
      </div>`;
    document.body.appendChild(sheet);

    const input = sheet.querySelector("#cshCashReceived");
    const status = sheet.querySelector("#cshCashChange");
    const send = sheet.querySelector("[data-cash-send]");
    const update = (fromTyping) => {
      if (!fromTyping) input.value = received ? money(received).replace(/[^0-9.]/g, "") : "";
      status.innerHTML = cashStatusHtml(total, received);
      send.disabled = !cashChange(total, received).ok;
      send.textContent = send.disabled ? `Faltan ${money(cashChange(total, received).missing)}` : "Enviar";
    };
    input.addEventListener("input", () => {
      received = parseCash(input.value);
      update(true);
    });
    CASH_BILLS.forEach((bill) => {
      sheet.querySelector(`[data-cash-bill="${bill}"]`).addEventListener("click", () => {
        received += bill;
        update(false);
      });
    });
    sheet.querySelector("[data-cash-exact]").addEventListener("click", () => {
      received = Math.round(Number(total || 0));
      update(false);
    });
    sheet.querySelector("[data-cash-clear]").addEventListener("click", () => {
      received = 0;
      update(false);
    });
    sheet.querySelector("[data-sheet-cancel]").addEventListener("click", () => sheet.remove());
    send.addEventListener("click", () => {
      const result = cashChange(total, received);
      if (!result.ok) return;
      sheet.remove();
      onConfirm({ received, change: result.change });
    });
    update(false);
    return sheet;
  }

  function chargeableTotal(table) {
    return (table.orders || []).filter((o) => o.status === "entregado").reduce((sum, o) => sum + Number(o.total || 0), 0);
  }

  function tableStartedMs(table) {
    const times = (table.orders || []).map((o) => Date.parse(o.created_at || "")).filter(Number.isFinite);
    return times.length ? Math.min(...times) : Number.POSITIVE_INFINITY;
  }

  function sortTablesByAge(tables, nowMs) {
    return tables.slice().sort((a, b) => tableStartedMs(a) - tableStartedMs(b) || String(a.table_number).localeCompare(String(b.table_number)));
  }

  function elapsedLabel(startedMs, nowMs) {
    if (!Number.isFinite(startedMs)) return "—";
    const minutes = Math.max(0, Math.floor((nowMs - startedMs) / 60000));
    if (minutes < 1) return "< 1 min";
    if (minutes < 60) return `${minutes} min`;
    return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
  }

  // "Mesa 11" -> caption "Mesa", big "11"; "Venta 012" -> "Venta", "012".
  function tableNumberParts(label) {
    const clean = String(label || "").trim();
    const match = clean.match(/^(mesa|venta)\s+(.+)$/i);
    if (match) return { caption: match[1][0].toUpperCase() + match[1].slice(1).toLowerCase(), number: match[2] };
    return { caption: /^\d+$/.test(clean) ? "Mesa" : "", number: clean || "—" };
  }

  function tableCardHtml(table, nowMs) {
    const parts = tableNumberParts(table.table_number);
    const stateKey = tableState(table);
    return `
      <button class="csh-card csh-card-${stateKey}" type="button" data-csh-open-table="${h(table.key)}">
        <div class="csh-card-top">
          <div class="csh-card-number">${parts.caption ? `<small>${h(parts.caption)}</small>` : ""}<b>${h(parts.number)}</b></div>
          <span class="csh-card-timer">⏱ ${h(elapsedLabel(tableStartedMs(table), nowMs))}</span>
        </div>
        <span class="csh-card-state">${h(TABLE_STATES[stateKey])}</span>
        <div class="csh-card-waiter">${table.waiter ? `Mesero: ${h(table.waiter)}` : "Sin mesero"}</div>
        <strong class="csh-card-total">${h(money(table.total))}</strong>
      </button>`;
  }

  // "3/4", "2×": the portion/fraction label when there is one.
  function lineQuantity(item) {
    if (item.quantity_label) return String(item.quantity_label);
    const qty = Number(item.quantity || 0);
    return `${Number.isInteger(qty) ? qty : qty.toFixed(2)}×`;
  }

  function lineAmount(item) {
    const subtotal = Number(item.subtotal);
    return Number.isFinite(subtotal) && item.subtotal !== undefined && item.subtotal !== null
      ? subtotal
      : Number(item.unit_price || 0) * Number(item.quantity || 0);
  }

  async function printAccount(orderIds) {
    if (!orderIds || !orderIds.length || state.printing) return;
    state.printing = true;
    safeRender();
    try {
      const data = await waiterApi("/caja/documento", { method: "POST", body: JSON.stringify({ order_ids: orderIds }) });
      if (data && data.document && SaleDoc) SaleDoc.printDocument(data.document);
    } catch (error) {
      state.error = error.message || "No se pudo preparar la cuenta para imprimir.";
    } finally {
      state.printing = false;
      safeRender();
    }
  }

  async function addProductToTable(product, quantity) {
    const table = activeTable();
    if (!table) return;
    const servedOrder = table.orders.find((o) => o.status === "entregado");
    try {
      if (servedOrder) {
        await hspApi(`/orders/${encodeURIComponent(servedOrder.id)}/items`, {
          method: "POST",
          body: JSON.stringify({ items: [{ inventory_item_id: product.id, name: product.name, quantity, unit_price: product.price }] }),
        });
      } else {
        const created = await waiterApi("/orders", {
          method: "POST",
          body: JSON.stringify({ table: table.table_number, items: [{ inventory_item_id: product.id, quantity }] }),
        });
        const orderId = created.order && created.order.id;
        if (orderId) {
          await hspApi(`/orders/${encodeURIComponent(orderId)}/status`, { method: "PATCH", body: JSON.stringify({ status: "alistando" }) });
          await hspApi(`/orders/${encodeURIComponent(orderId)}/status`, { method: "PATCH", body: JSON.stringify({ status: "entregado" }) });
        }
      }
      state.toast = `${quantity} x ${product.name} agregado.`;
      await refreshTables();
    } catch (error) {
      state.error = error.message || "No se pudo agregar el producto.";
      render();
    }
  }

  async function chargeTable(paymentMethod, cash) {
    const table = activeTable();
    if (!table) return;
    state.paying = true;
    render();
    try {
      const served = table.orders.filter((o) => o.status === "entregado");
      for (const order of served) {
        await hspApi(`/orders/${encodeURIComponent(order.id)}/close-table`, {
          method: "POST",
          body: JSON.stringify({ payment_method: paymentMethod }),
        });
      }
      const label = String(table.table_number || "").trim();
      state.toast = `${/^(mesa|venta)\b/i.test(label) ? label : `Mesa ${label}`} cobrada.${cash ? ` Cambio: ${money(cash.change)}.` : ""}`;
      state.lastCharged = { order_ids: served.map((o) => o.id), label: /^(mesa|venta)\b/i.test(label) ? label : `Mesa ${label}` };
      staleSummary049V();
      resetToTables();
      await refreshTables();
    } catch (error) {
      state.error = error.message || "No se pudo cobrar la mesa.";
    } finally {
      state.paying = false;
      render();
    }
  }

  async function registerNetwork() {
    try {
      const data = await waiterApi("/network/register", { method: "POST" });
      state.toast = `Red registrada: ${data.ip}`;
      render();
    } catch (error) {
      state.error = error.message || "Conectate al WiFi del restaurante.";
      render();
    }
  }

  function screenLogin() {
    return `
      <section class="csh-login">
        <div class="csh-login-card">
          <div class="csh-brand">CLONEXA</div>
          <h1>Panel Caja</h1>
          ${state.error ? `<div class="csh-alert">${h(state.error)}</div>` : ""}
          <form id="cshLoginForm">
            <label>Usuario<input name="username" autocomplete="username" required /></label>
            <label>Clave<input name="password" type="password" autocomplete="current-password" required /></label>
            <button type="submit" class="csh-btn csh-btn-primary" ${state.busy ? "disabled" : ""}>${state.busy ? "Entrando..." : "Entrar"}</button>
          </form>
        </div>
      </section>`;
  }

  function saleTableOptions() {
    return Array.from(new Set(state.tables.map((t) => String(t.table_number)).concat(state.knownTables)))
      .filter((label) => !/^venta /i.test(label));
  }

  function saleHeaderHtml(title) {
    const sale = state.sale;
    return `
      <header class="csh-header">
        <button class="csh-back" type="button" data-csh-back aria-label="Volver">‹</button>
        <h1>${h(title)}</h1>
      </header>
      <div class="csh-sale-dest">
        <label>Destino
          <select id="cshSaleTable" data-csh-sale-table>
            <option value="" ${sale.table ? "" : "selected"}>Venta independiente</option>
            ${saleTableOptions().map((label) => `<option value="${h(label)}" ${sale.table === label ? "selected" : ""}>${h(label)}</option>`).join("")}
          </select>
        </label>
        <label class="csh-check"><input type="checkbox" data-csh-sale-kitchen ${sale.toKitchen ? "checked" : ""}> Enviar a cocina</label>
      </div>`;
  }

  function saleCartHtml() {
    const sale = state.sale;
    const mode = saleMode(sale);
    return `
      <aside class="csh-sale-cart">
        <div class="csh-sale-cart-title">Venta${sale.table ? ` · ${h(sale.table)}` : ""}</div>
        ${sale.items.map((item, index) => `
          <div class="csh-line">
            <button type="button" class="csh-line-main" data-csh-sale-edit="${index}">
              <b>${Kit.cartLineLabel(item)}</b>
              ${item.term ? `<small>${h(item.term)}</small>` : ""}
              ${item.observations ? `<small>${h(item.observations)}</small>` : ""}
              ${item.quick_notes && item.quick_notes.length ? `<small>${item.quick_notes.map(h).join(" · ")}</small>` : ""}
            </button>
            <strong>${h(money(Number(item.unit_price || 0) * Number(item.quantity || 0)))}</strong>
            <button type="button" class="csh-line-remove" data-csh-sale-remove="${index}" aria-label="Quitar">✕</button>
          </div>`).join("") || `<div class="csh-empty">Elige una categoría y agrega productos.</div>`}
        <div class="csh-cart-total"><span>Total</span><strong>${h(money(saleTotal(sale)))}</strong></div>
        ${mode === "charge" ? `
          <div class="csh-pay-block">
            <div class="csh-pay-title">Cobrar venta (método de pago obligatorio)</div>
            <div class="csh-pay-options">
              ${PAYMENT_METHODS.map((pm) => `<button class="csh-btn csh-btn-primary" type="button" data-csh-sale-pay="${pm.value}" ${state.saleBusy || !sale.items.length ? "disabled" : ""}>${h(pm.label)}</button>`).join("")}
            </div>
          </div>` : `
          <button class="csh-btn csh-btn-primary csh-sale-send" type="button" data-csh-sale-send ${state.saleBusy || !sale.items.length ? "disabled" : ""}>
            ${state.saleBusy ? "Enviando..." : mode === "kitchen" ? "Enviar a cocina" : `Agregar a ${h(sale.table)}`}
          </button>
          ${mode === "kitchen" && !sale.table ? `<div class="csh-hint">Se cobra cuando cocina la marque lista.</div>` : ""}`}
      </aside>`;
  }

  function screenSale() {
    return `
      <section class="csh-shell">
        ${saleHeaderHtml("Nueva venta")}
        <div class="csh-sale-layout">
          <div class="csh-sale-menu">${Kit.categoryGridHtml(state.menu, kitOptions("data-csh-cat"))}</div>
          ${saleCartHtml()}
        </div>
      </section>`;
  }

  function screenSaleProducts() {
    const category = saleCategory();
    return `
      <section class="csh-shell">
        ${saleHeaderHtml(category ? category.label : "Productos")}
        <div class="csh-sale-layout">
          <div class="csh-sale-menu">${Kit.productGridHtml(category ? category.products : [], kitOptions("data-csh-product"))}</div>
          ${saleCartHtml()}
        </div>
      </section>`;
  }

  // ---------------------------------------------------------------------
  // Domicilios por WhatsApp. A QR payment arrives "por verificar": the
  // receipt photo can be faked, so only the caja -- after seeing the money
  // in the bank -- marks it paid; until then it can't be dispatched or
  // closed (the server enforces both).
  // ---------------------------------------------------------------------
  function isDelivery(order) {
    return Boolean(order && order.metadata && order.metadata.delivery);
  }

  function deliveryOf(order) {
    return (order && order.metadata && order.metadata.delivery) || {};
  }

  function deliveryAsTable(order) {
    return { key: `domicilio:${order.id}`, table_number: order.table_number, orders: [order], total: Number(order.total || 0), waiter: "" };
  }

  function activeDelivery() {
    return state.deliveries.find((o) => String(o.id) === state.activeDeliveryId) || null;
  }

  function deliveryNumber(order) {
    const tail = String(order.order_number || "").split("-").pop();
    return tail ? `#${tail}` : "";
  }

  function clockTime(iso) {
    const date = new Date(iso);
    if (!iso || Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
  }

  function deliveryStage(order) {
    const d = deliveryOf(order);
    if (d.dispatched_at) return { key: "sent", label: "En camino" };
    if (d.driver) return { key: "assigned", label: `Asignado a ${d.driver.name}` };
    if (order.status === "pendiente" || order.status === "alistando") return { key: "kitchen", label: "En cocina" };
    return { key: "ready", label: "Listo para despachar" };
  }

  function paymentBadge(d) {
    if (d.payment_method === "qr" && d.payment_status === "por_verificar") return `<span class="csh-pay-warn">⚠ Pago QR por verificar</span>`;
    if (d.payment_method === "qr") return `<span class="csh-pay-ok">QR verificado ✓</span>`;
    return `<span class="csh-pay-cod">${d.payment_method === "card" ? "Datáfono" : "Efectivo"} contra entrega</span>`;
  }

  function deliveryCardHtml(order, nowMs) {
    const d = deliveryOf(order);
    const stage = deliveryStage(order);
    return `
      <button class="csh-card csh-card-delivery csh-delivery-${stage.key}" type="button" data-csh-open-delivery="${h(order.id)}">
        <div class="csh-card-top">
          <div class="csh-card-number"><small>Domicilio</small><b>${h(deliveryNumber(order))}</b></div>
          <span class="csh-card-timer">⏱ ${h(elapsedLabel(Date.parse(order.created_at) || nowMs, nowMs))}</span>
        </div>
        <span class="csh-card-state">${h(stage.label)}</span>
        <div class="csh-card-waiter">${h(d.customer_name || "")} · ${h(d.address || "")}</div>
        ${paymentBadge(d)}
        <strong class="csh-card-total">${h(money(order.total))}</strong>
      </button>`;
  }

  function deliverySectionHtml() {
    if (!state.delivery && !state.deliveries.length) return "";
    const now = Date.now();
    return `
      <h2 class="csh-section-title">🛵 Domicilios</h2>
      <div class="csh-grid-tables">
        ${state.deliveries.map((order) => deliveryCardHtml(order, now)).join("") || `<div class="csh-empty">No hay domicilios abiertos.</div>`}
      </div>`;
  }

  function deliveryApi(path, options) {
    return api(`/api/v1/domicilios/companies/${encodeURIComponent(companyId)}${path}`, options);
  }

  async function deliveryAction(path, body, okMessage) {
    const order = activeDelivery();
    if (!order || state.deliveryBusy) return;
    state.deliveryBusy = true;
    safeRender();
    try {
      const result = await deliveryApi(`/orders/${encodeURIComponent(order.id)}/${path}`, {
        method: "POST",
        body: JSON.stringify(body || {}),
      });
      state.toast = result && result.detail ? result.detail : okMessage;
      state.driversOpen = false;
      await refreshTables();
    } catch (error) {
      state.error = error.message || "No se pudo completar la acción.";
    } finally {
      state.deliveryBusy = false;
      safeRender();
    }
  }

  async function toggleDrivers() {
    state.driversOpen = !state.driversOpen;
    if (state.driversOpen) {
      try {
        const data = await deliveryApi("/drivers");
        state.drivers = Array.isArray(data.drivers) ? data.drivers : [];
      } catch (error) {
        state.drivers = [];
        state.error = error.message || "No se pudo cargar los domiciliarios.";
      }
    }
    safeRender();
  }

  async function chargeDelivery(paymentMethod, cash) {
    const order = activeDelivery();
    if (!order) return;
    state.paying = true;
    safeRender();
    try {
      await hspApi(`/orders/${encodeURIComponent(order.id)}/close-table`, {
        method: "POST",
        body: JSON.stringify({ payment_method: paymentMethod }),
      });
      state.toast = `Domicilio ${deliveryNumber(order)} cerrado.${cash ? ` Cambio: ${money(cash.change)}.` : ""}`;
      state.lastCharged = { order_ids: [order.id], label: `Domicilio ${deliveryNumber(order)}` };
      staleSummary049V();
      resetToTables();
      await refreshTables();
    } catch (error) {
      state.error = error.message || "No se pudo cerrar el domicilio.";
    } finally {
      state.paying = false;
      safeRender();
    }
  }

  function screenDelivery() {
    const order = activeDelivery();
    if (!order) {
      if (!state.tablesLoaded) return `<section class="csh-shell"><div class="csh-empty">Cargando domicilio…</div></section>`;
      state.stack = ["tables"];
      state.screen = "tables";
      state.activeDeliveryId = "";
      persistNav();
      return state.redesign ? screenTables049V() : screenTables();
    }
    const d = deliveryOf(order);
    const stage = deliveryStage(order);
    const pending = d.payment_method === "qr" && d.payment_status === "por_verificar";
    const pinUrl = (d.whatsapp_location && d.whatsapp_location.url) || d.location_url || "";
    const served = order.status === "entregado";
    const busy = state.deliveryBusy ? "disabled" : "";
    return `
      <section class="csh-shell">
        <header class="csh-header">
          <button class="csh-back" type="button" data-csh-back aria-label="Volver">‹</button>
          <h1>Domicilio ${h(deliveryNumber(order))}</h1>
          <span class="csh-card-state">${h(stage.label)}</span>
          <button class="csh-logout" type="button" data-csh-logout aria-label="Salir">⏻</button>
        </header>
        <div class="csh-detail">
          ${pending ? `
            <div class="csh-qr-warning">
              <strong>⚠ PAGO POR QR SIN VERIFICAR</strong>
              <span>El cliente envió un comprobante al WhatsApp. Un comprobante se puede falsificar: confirma en la cuenta del banco que el dinero llegó antes de despachar.</span>
              <button class="csh-btn csh-btn-primary" type="button" data-csh-verify-payment ${busy}>Ya confirmé el pago en el banco</button>
            </div>` : ""}
          <div class="csh-delivery-info">
            <div><span>Cliente</span><b>${h(d.customer_name || "")}</b> · ${h(/^\d+$/.test(String(d.customer_phone || "")) ? d.customer_phone : "por WhatsApp")}</div>
            <div><span>Dirección</span><b>${h(d.address || "")}</b>${d.address_notes ? ` · ${h(d.address_notes)}` : ""}</div>
            ${pinUrl ? `<div><span>Ubicación</span><a href="${h(pinUrl)}" target="_blank" rel="noopener">Abrir en el mapa</a></div>` : ""}
            <div><span>Pago</span>${paymentBadge(d)}${d.payment_method === "cash" && d.pays_with ? ` · Paga con ${h(money(d.pays_with))}, cambio ${h(money(d.change))}` : ""}</div>
            ${d.payment_verified_at ? `<div><span>Verificado</span>${h(d.payment_verified_by || "")} a las ${h(clockTime(d.payment_verified_at))}</div>` : ""}
          </div>
          <table class="csh-detail-lines">
            <thead><tr><th>Cant.</th><th>Producto</th><th>Valor</th></tr></thead>
            <tbody>
              ${(order.items || []).map((item) => `
                <tr>
                  <td>${h(lineQuantity(item))}</td>
                  <td>${h(item.name)}${item.term ? ` <small>· ${h(item.term)}</small>` : ""}${item.observations ? `<div class="csh-note">${h(item.observations)}</div>` : ""}</td>
                  <td>${h(money(lineAmount(item)))}</td>
                </tr>`).join("")}
            </tbody>
            <tfoot><tr><td colspan="2">Total</td><td>${h(money(order.total))}</td></tr></tfoot>
          </table>
          <div class="csh-delivery-driver">
            ${d.driver ? `<div>🛵 <b>${h(d.driver.name)}</b> · asignado a las ${h(clockTime(d.driver.assigned_at))} por ${h(d.driver.assigned_by || "")}${d.driver.whatsapp_sent === false ? ` <span class="csh-pay-warn">WhatsApp no enviado</span>` : ""}</div>` : ""}
            <button class="csh-btn" type="button" data-csh-drivers-toggle ${busy}>${d.driver ? "Reenviar a otro domiciliario" : "Enviar a domiciliario"} ▾</button>
            ${state.driversOpen ? `
              <div class="csh-driver-list">
                ${state.drivers.map((driver) => `
                  <button class="csh-btn" type="button" data-csh-assign-driver="${h(driver.employee_id)}" ${busy}>${h(driver.name)} · ${h(driver.phone)}</button>`).join("")
                  || `<div class="csh-empty">No hay domiciliarios activos con teléfono en Workforce (rol Domiciliario).</div>`}
              </div>` : ""}
            <button class="csh-btn csh-btn-primary" type="button" data-csh-dispatched ${pending || !d.driver || d.dispatched_at || state.deliveryBusy ? "disabled" : ""}>
              ${d.dispatched_at ? `Salió a las ${h(clockTime(d.dispatched_at))}` : "Salió a domicilio (avisar al cliente)"}
            </button>
          </div>
          ${served && !pending ? `
            <div class="csh-pay-block">
              <div class="csh-pay-title">Cerrar domicilio</div>
              <div class="csh-pay-options">
                ${d.payment_method === "qr"
                  ? `<button class="csh-btn csh-btn-primary" type="button" data-csh-delivery-pay="transfer" ${state.paying ? "disabled" : ""}>Cerrar (pagado por QR)</button>`
                  : PAYMENT_METHODS.map((pm) => `<button class="csh-btn csh-btn-primary" type="button" data-csh-delivery-pay="${pm.value}" ${state.paying ? "disabled" : ""}>${h(pm.label)}</button>`).join("")}
              </div>
            </div>` : `<div class="csh-hint">${pending ? "Verifica el pago antes de cerrar." : "La cocina aún no entrega este pedido."}</div>`}
        </div>
      </section>`;
  }

  function screenTables() {
    return `
      <section class="csh-shell">
        <header class="csh-header">
          <h1>Mesas abiertas</h1>
          ${state.directSale ? `<button class="csh-btn csh-btn-primary" type="button" data-csh-new-sale>+ Nueva venta</button>` : ""}
          <button class="csh-btn csh-btn-mini" type="button" data-csh-register-network>Registrar la red actual del local</button>
          <button class="csh-logout" type="button" data-csh-logout aria-label="Salir">⏻</button>
        </header>
        ${shiftBarHtml()}
        ${state.toast ? `<div class="csh-toast">${h(state.toast)}</div>` : ""}
        ${state.lastCharged ? `
          <div class="csh-last">
            <span>Última cobrada: <b>${h(state.lastCharged.label)}</b></span>
            <button class="csh-btn csh-btn-mini" type="button" data-csh-print-last ${state.printing ? "disabled" : ""}>🖨 Imprimir cuenta</button>
          </div>` : ""}
        <div class="csh-grid-tables">
          ${state.tables.map((table) => tableCardHtml(table, Date.now())).join("") || `<div class="csh-empty">No hay mesas abiertas.</div>`}
        </div>
        ${deliverySectionHtml()}
      </section>`;
  }

  function screenTable() {
    const table = activeTable();
    if (!table) {
      // First paint after a reload: the tables haven't arrived yet.
      if (!state.tablesLoaded) return `<section class="csh-shell"><div class="csh-empty">Cargando mesa…</div></section>`;
      // Charged/closed meanwhile (another device): back to the list.
      state.stack = ["tables"];
      state.screen = "tables";
      state.activeTableKey = "";
      persistNav();
      return screenTables();
    }
    const allItems = table.orders.flatMap((o) => o.items || []);
    const canCharge = table.orders.some((o) => o.status === "entregado");
    const stateKey = tableState(table);
    return `
      <section class="csh-shell">
        <header class="csh-header">
          <button class="csh-back" type="button" data-csh-back aria-label="Volver">‹</button>
          <h1>${h(tableTitle(table.table_number))}</h1>
          <span class="csh-card-state csh-state-${stateKey}">${h(TABLE_STATES[stateKey])}</span>
          <button class="csh-logout" type="button" data-csh-logout aria-label="Salir">⏻</button>
        </header>
        <div class="csh-detail">
          <div class="csh-detail-meta">
            <span>⏱ ${h(elapsedLabel(tableStartedMs(table), Date.now()))}</span>
            ${table.waiter ? `<span>Mesero: ${h(table.waiter)}</span>` : ""}
            <span>${h(table.orders.length)} comanda${table.orders.length === 1 ? "" : "s"}</span>
          </div>
          <table class="csh-detail-lines">
            <thead><tr><th>Cant.</th><th>Producto</th><th>Valor</th></tr></thead>
            <tbody>
              ${allItems.map((item) => `
                <tr>
                  <td>${h(lineQuantity(item))}</td>
                  <td>${h(item.name)}${item.term ? ` <small>· ${h(item.term)}</small>` : ""}${item.observations ? `<div class="csh-note">${h(item.observations)}</div>` : ""}</td>
                  <td>${h(money(lineAmount(item)))}</td>
                </tr>`).join("") || `<tr><td colspan="3" class="csh-empty">Sin productos todavía.</td></tr>`}
            </tbody>
            <tfoot><tr><td colspan="2">Total</td><td>${h(money(table.total))}</td></tr></tfoot>
          </table>
          <div class="csh-detail-actions">
            <button class="csh-btn" type="button" data-csh-add-product>+ Agregar producto</button>
            <button class="csh-btn" type="button" data-csh-print ${state.printing || !allItems.length ? "disabled" : ""}>🖨 Imprimir cuenta</button>
          </div>
          ${canCharge ? `
            <div class="csh-pay-block">
              <div class="csh-pay-title">Datos de cobro · método de pago obligatorio</div>
              <div class="csh-pay-options">
                ${PAYMENT_METHODS.map((pm) => `<button class="csh-btn csh-btn-primary" type="button" data-csh-pay="${pm.value}" ${state.paying ? "disabled" : ""}>${h(pm.label)}</button>`).join("")}
              </div>
            </div>` : `<div class="csh-hint">Entrega el pedido pendiente antes de cobrar.</div>`}
        </div>
      </section>`;
  }

  // =====================================================================
  // 049V: REDISENO DE LA CAJA (interruptor cashier_redesign). Nada de esto
  // se dibuja sin el interruptor: el panel de antes queda intacto.
  // =====================================================================
  const METHOD_ICONS_049V = { cash: "💵", transfer: "🏦", card: "💳", other: "🧾" };

  function brandLogo049V() {
    const current = window.CxPanelBrand && window.CxPanelBrand.current ? window.CxPanelBrand.current() : null;
    return Boolean(current && current.logo);
  }

  function isCashierSale049V(order) {
    const sale = order && order.metadata && order.metadata.cashier_sale;
    return Boolean(sale && sale.kind === "independiente");
  }

  // Mesas abiertas vs ventas de caja abiertas ("Venta 012" que espera cocina).
  function splitTables049V(tables) {
    const mesas = [];
    const ventas = [];
    (tables || []).forEach((table) => {
      const orders = table.orders || [];
      if (orders.length && orders.every(isCashierSale049V)) ventas.push(table);
      else mesas.push(table);
    });
    return { mesas, ventas };
  }

  // Un plato que se prepara (Carta: tipo preparado; sin Carta: tiene
  // estacion de cocina) vs algo listo para entregar (una gaseosa).
  function lineNeedsKitchen049V(line) {
    const found = line && line.menu_product_id ? Kit.findMenuProduct(state.menu, line.menu_product_id) : null;
    if (!found) return false;
    const { product, category } = found;
    if (product.carta_kind) return product.carta_kind !== "directo";
    return Boolean(String(product.station || (category && category.station) || "").trim());
  }

  function productNeedsKitchen049V(product, category) {
    if (product.carta_kind) return product.carta_kind !== "directo";
    return Boolean(String(product.station || (category && category.station) || "").trim());
  }

  function saleNeedsKitchen049V(sale) {
    return (sale.items || []).some(lineNeedsKitchen049V);
  }

  // Mientras el cajero no elija a mano, la venta sigue la sugerencia.
  function syncKitchen049V() {
    if (!state.redesign || state.sale.kitchenTouched) return;
    state.sale.toKitchen = saleNeedsKitchen049V(state.sale);
  }

  function lateClass049V(startedMs, nowMs) {
    if (!Number.isFinite(startedMs)) return "";
    const minutes = (nowMs - startedMs) / 60000;
    if (minutes >= 90) return "is-late";
    if (minutes >= 45) return "is-slow";
    return "";
  }

  // ------------------------------------------------------------ barra superior
  function shiftLine049V() {
    const op = state.operational;
    if (!op) return "";
    const onBreak = op.status === "break";
    const live = liveShiftSeconds();
    const busy = state.shiftBusy ? "disabled" : "";
    return `
      <div class="cx5-shift ${onBreak ? "is-break" : ""}" role="group" aria-label="Tu turno">
        <span class="cx5-shift-dot" aria-hidden="true"></span>
        <span class="cx5-shift-time">${onBreak ? "En pausa" : "Activo"} <b data-csh-active-clock>${h(clockLabel(live.active))}</b></span>
        <span class="cx5-shift-time is-pause">Pausa <b data-csh-break-clock>${h(clockLabel(live.pause))}</b></span>
        ${onBreak
          ? `<button class="cx5-mini" type="button" data-csh-shift-resume ${busy}>▶ Retomar</button>`
          : `<button class="cx5-mini" type="button" data-csh-shift-pause ${busy}>⏸ Pausa</button>`}
        <button class="cx5-mini is-danger" type="button" data-csh-shift-finish ${busy}>Cerrar jornada</button>
      </div>`;
  }

  function topBar049V() {
    return `
      <header class="cx5-top">
        <div class="cx5-id">
          ${brandLogo049V() ? `<span class="cx5-logo" aria-hidden="true"></span>` : `<span class="cx5-mark" aria-hidden="true">$</span>`}
          <div><strong>Caja</strong><small>${h(new Date().toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long" }))}</small></div>
        </div>
        ${shiftLine049V()}
        <div class="cx5-actions">
          <button class="cx5-btn cx5-btn-z" type="button" data-csh-z-open>🧾 Sacar Z</button>
          ${state.directSale ? `<button class="cx5-btn cx5-btn-primary" type="button" data-csh-new-sale>＋ Nueva venta</button>` : ""}
          <div class="cx5-more">
            <button class="cx5-icon" type="button" data-csh-more aria-label="Más opciones" aria-expanded="${state.moreOpen ? "true" : "false"}">⋯</button>
            ${state.moreOpen ? `
              <div class="cx5-menu" role="menu">
                <button type="button" role="menuitem" data-csh-register-network>📶 Registrar la red actual del local</button>
                <button type="button" role="menuitem" data-csh-logout>⏻ Salir del panel</button>
              </div>` : ""}
          </div>
        </div>
      </header>`;
  }

  // ------------------------------------------------------------ indicadores
  function kpiStrip049V() {
    const s = state.summary;
    const dash = "—";
    const methods = (s && Array.isArray(s.methods) ? s.methods : [
      { method: "cash", label: "Efectivo", total: 0 }, { method: "transfer", label: "Transferencia", total: 0 }, { method: "card", label: "Tarjeta", total: 0 },
    ]);
    const top = Math.max(1, ...methods.map((m) => Number(m.total || 0)));
    return `
      <section class="cx5-kpis" aria-label="Cómo va tu turno">
        <div class="cx5-kpi cx5-kpi-main">
          <span>Total vendido</span>
          <strong data-cx5-kpi="sold">${s ? h(money(s.sold)) : dash}</strong>
          <small>${s ? `Cobrado ${h(money(s.charged))} · Por cobrar ${h(money(s.pending))}` : "Cargando el turno…"}</small>
        </div>
        <div class="cx5-kpi"><span>Pedidos</span><strong data-cx5-kpi="orders">${s ? h(s.orders) : dash}</strong><small>${s ? `${h(s.accounts)} cuenta${s.accounts === 1 ? "" : "s"}` : ""}</small></div>
        <div class="cx5-kpi"><span>Ticket promedio</span><strong data-cx5-kpi="ticket">${s ? h(money(s.ticket)) : dash}</strong><small>por cuenta</small></div>
        <div class="cx5-kpi"><span>Domicilios</span><strong data-cx5-kpi="deliveries">${s ? h(s.deliveries) : dash}</strong><small>recibidos</small></div>
        <div class="cx5-kpi"><span>Mesas atendidas</span><strong data-cx5-kpi="tables">${s ? h(s.tables) : dash}</strong><small>en el turno</small></div>
        <div class="cx5-kpi cx5-kpi-pay">
          <span>Cobrado por método</span>
          ${methods.map((m) => `
            <div class="cx5-pay-row" data-cx5-method="${h(m.method)}">
              <em>${METHOD_ICONS_049V[m.method] || "🧾"} ${h(m.label)}</em>
              <i style="--w:${Math.round((Number(m.total || 0) / top) * 100)}%"></i>
              <b>${s ? h(money(m.total)) : dash}</b>
            </div>`).join("")}
        </div>
      </section>
      ${s ? `<p class="cx5-kpi-note">${s.shift_open && s.since ? `Tu turno desde las ${h(clockTime(s.since))}` : "Jornada de hoy"} · se actualiza solo</p>` : ""}`;
  }

  // ------------------------------------------------------------ secciones
  function section049V({ key, icon, title, count, empty, body }) {
    return `
      <section class="cx5-sec cx5-sec-${key} ${count ? "" : "is-empty"}" aria-label="${h(title)}">
        <header class="cx5-sec-head">
          <span class="cx5-sec-icon" aria-hidden="true">${icon}</span>
          <h2>${h(title)}</h2>
          <span class="cx5-count" data-cx5-count="${key}">${h(count)}</span>
          ${count ? "" : `<small class="cx5-sec-empty">${h(empty)}</small>`}
        </header>
        ${count ? body : ""}
      </section>`;
  }

  function tableCard049V(table, nowMs) {
    const parts = tableNumberParts(table.table_number);
    const stateKey = tableState(table);
    const started = tableStartedMs(table);
    return `
      <button class="cx5-card cx5-st-${stateKey}" type="button" data-csh-open-table="${h(table.key)}">
        <div class="cx5-card-row">
          <span class="cx5-cap">${h(parts.caption || "Mesa")}</span>
          <span class="cx5-timer ${lateClass049V(started, nowMs)}">⏱ ${h(elapsedLabel(started, nowMs))}</span>
        </div>
        <b class="cx5-num">${h(parts.number)}</b>
        <span class="cx5-pill">${h(TABLE_STATES[stateKey])}</span>
        <div class="cx5-card-foot">
          <span class="cx5-who">${table.waiter ? `👤 ${h(table.waiter)}` : "Sin mesero"}</span>
          <strong>${h(money(table.total))}</strong>
        </div>
      </button>`;
  }

  function deliveryCard049V(order, nowMs) {
    const d = deliveryOf(order);
    const stage = deliveryStage(order);
    const started = Date.parse(order.created_at) || nowMs;
    return `
      <button class="cx5-card cx5-delivery cx5-dl-${stage.key}" type="button" data-csh-open-delivery="${h(order.id)}">
        <div class="cx5-card-row">
          <span class="cx5-cap">Domicilio ${h(deliveryNumber(order))}</span>
          <span class="cx5-timer ${lateClass049V(started, nowMs)}">⏱ ${h(elapsedLabel(started, nowMs))}</span>
        </div>
        <div class="cx5-dl-who"><b>${h(d.customer_name || "Cliente")}</b></div>
        <div class="cx5-dl-addr">📍 ${h(d.address || "Sin dirección")}${d.address_notes ? ` · ${h(d.address_notes)}` : ""}</div>
        <div class="cx5-dl-badges"><span class="cx5-pill">${h(stage.label)}</span>${paymentBadge(d)}</div>
        <div class="cx5-card-foot"><span></span><strong>${h(money(order.total))}</strong></div>
      </button>`;
  }

  function openSaleRow049V(table) {
    const stateKey = tableState(table);
    return `
      <button class="cx5-row cx5-st-${stateKey}" type="button" data-csh-open-table="${h(table.key)}">
        <span class="cx5-row-main"><b>${h(table.table_number)}</b><small>${stateKey === "ready" ? "Lista: toca para cobrar" : "En cocina"}</small></span>
        <span class="cx5-pill">${h(TABLE_STATES[stateKey])}</span>
        <strong>${h(money(table.total))}</strong>
      </button>`;
  }

  function paidSaleRow049V(row) {
    return `
      <div class="cx5-row is-paid" data-cx5-sale="${h(row.id)}">
        <span class="cx5-row-main"><b>${h(row.label)}</b><small>${h(clockTime(row.closed_at || row.created_at))} · ${METHOD_ICONS_049V[row.method] || ""} ${h(row.method_label || "")} · ${h(row.products)} producto${row.products === 1 ? "" : "s"}</small></span>
        <span class="cx5-pill is-paid">Cobrada</span>
        <strong>${h(money(row.total))}</strong>
        <button class="cx5-icon cx5-print" type="button" data-csh-print-order="${h(row.id)}" aria-label="Imprimir cuenta" ${state.printing ? "disabled" : ""}>🖨</button>
      </div>`;
  }

  function screenTables049V() {
    const now = Date.now();
    const { mesas, ventas } = splitTables049V(state.tables);
    const paid = state.summary && Array.isArray(state.summary.direct_sales) ? state.summary.direct_sales.filter((r) => r.paid) : [];
    const showDelivery = state.delivery || state.deliveries.length > 0;
    const showSales = state.directSale || ventas.length > 0 || paid.length > 0;
    return `
      <section class="cx5 cx5-home">
        ${topBar049V()}
        ${kpiStrip049V()}
        ${state.toast ? `<div class="cx5-toast" role="status">${h(state.toast)}</div>` : ""}
        ${state.lastCharged ? `
          <div class="cx5-last">
            <span>Última cobrada: <b>${h(state.lastCharged.label)}</b></span>
            <button class="cx5-mini" type="button" data-csh-print-last ${state.printing ? "disabled" : ""}>🖨 Imprimir cuenta</button>
          </div>` : ""}
        ${mesas.length || state.deliveries.length ? `<div class="cx5-board ${showDelivery || showSales ? "" : "is-single"}">
          ${section049V({
            key: "mesas", icon: "🍽", title: "Mesas", count: mesas.length, empty: "No hay mesas abiertas",
            body: `<div class="cx5-grid">${mesas.map((t) => tableCard049V(t, now)).join("")}</div>`,
          })}
          ${showDelivery || showSales ? `<div class="cx5-side">
            ${showDelivery ? section049V({
              key: "domicilios", icon: "🛵", title: "Domicilios", count: state.deliveries.length, empty: "Sin domicilios abiertos",
              body: `<div class="cx5-grid cx5-grid-dl">${state.deliveries.map((o) => deliveryCard049V(o, now)).join("")}</div>`,
            }) : ""}
            ${showSales ? section049V({
              key: "ventas", icon: "🧾", title: "Ventas de caja", count: ventas.length + paid.length, empty: "Aún no hay ventas directas en tu turno",
              body: `<div class="cx5-rows">${ventas.map(openSaleRow049V).join("")}${paid.map(paidSaleRow049V).join("")}</div>`,
            }) : ""}
          </div>` : ""}
        </div>` : idleBoard049Y({ showDelivery, showSales, ventas, paid })}
      </section>`;
  }

  // 049Y: sin mesas ni domicilios abiertos el tablero no deja media pantalla
  // vacia: las secciones vacias van en una franja y el resto lo ocupa un
  // aviso con las acciones de siempre (solo con el rediseno de caja).
  function idleBoard049Y({ showDelivery, showSales, ventas, paid }) {
    const salesCount = ventas.length + paid.length;
    const salesSection = showSales ? section049V({
      key: "ventas", icon: "🧾", title: "Ventas de caja", count: salesCount, empty: "Aún no hay ventas directas en tu turno",
      body: `<div class="cx5-rows">${ventas.map(openSaleRow049V).join("")}${paid.map(paidSaleRow049V).join("")}</div>`,
    }) : "";
    return `
        <div class="cx5-board is-idle" data-cx5-idle>
          <div class="cx5-idle-strip">
            ${section049V({ key: "mesas", icon: "🍽", title: "Mesas", count: 0, empty: "No hay mesas abiertas", body: "" })}
            ${showDelivery ? section049V({ key: "domicilios", icon: "🛵", title: "Domicilios", count: 0, empty: "Sin domicilios abiertos", body: "" }) : ""}
            ${salesCount ? "" : salesSection}
          </div>
          ${salesCount ? salesSection : ""}
          <div class="cx5-idle">
            <span class="cx5-idle-icon" aria-hidden="true">✓</span>
            <strong>Todo al día</strong>
            <p>No hay mesas ni domicilios abiertos. Los pedidos nuevos aparecen aquí solos.</p>
            <div class="cx5-idle-actions">
              ${state.directSale ? `<button class="cx5-btn cx5-btn-primary" type="button" data-csh-new-sale>＋ Nueva venta</button>` : ""}
              <button class="cx5-btn" type="button" data-csh-z-open>🧾 Sacar Z</button>
            </div>
          </div>
        </div>`;
  }

  // ------------------------------------------------------------ mesa (detalle)
  function screenTable049V() {
    const table = activeTable();
    if (!table) {
      if (!state.tablesLoaded) return `<section class="cx5"><p class="cx5-pick">Cargando mesa…</p></section>`;
      state.stack = ["tables"];
      state.screen = "tables";
      state.activeTableKey = "";
      persistNav();
      return screenTables049V();
    }
    const allItems = table.orders.flatMap((o) => o.items || []);
    const canCharge = table.orders.some((o) => o.status === "entregado");
    const stateKey = tableState(table);
    const due = chargeableTotal(table);
    return `
      <section class="cx5">
        <header class="cx5-top">
          <button class="cx5-icon" type="button" data-csh-back aria-label="Volver">‹</button>
          <div class="cx5-id"><div><strong>${h(tableTitle(table.table_number))}</strong><small>⏱ ${h(elapsedLabel(tableStartedMs(table), Date.now()))}${table.waiter ? ` · 👤 ${h(table.waiter)}` : ""} · ${h(table.orders.length)} comanda${table.orders.length === 1 ? "" : "s"}</small></div></div>
          <span class="cx5-pill cx5-st-${stateKey}">${h(TABLE_STATES[stateKey])}</span>
        </header>
        <div class="cx5-detail">
          <div class="cx5-panel">
            <table class="csh-detail-lines">
              <thead><tr><th>Cant.</th><th>Producto</th><th>Valor</th></tr></thead>
              <tbody>
                ${allItems.map((item) => `
                  <tr>
                    <td>${h(lineQuantity(item))}</td>
                    <td>${h(item.name)}${item.term ? ` <small>· ${h(item.term)}</small>` : ""}${item.observations ? `<div class="csh-note">${h(item.observations)}</div>` : ""}</td>
                    <td>${h(money(lineAmount(item)))}</td>
                  </tr>`).join("") || `<tr><td colspan="3" class="csh-empty">Sin productos todavía.</td></tr>`}
              </tbody>
            </table>
          </div>
          <aside class="cx5-panel cx5-charge">
            <div class="cx5-total"><span>Total de la cuenta</span><strong>${h(money(table.total))}</strong></div>
            <div class="cx5-charge-actions">
              <button class="cx5-btn" type="button" data-csh-add-product>＋ Agregar producto</button>
              <button class="cx5-btn" type="button" data-csh-print ${state.printing || !allItems.length ? "disabled" : ""}>🖨 Imprimir cuenta</button>
            </div>
            ${canCharge ? `
              <div class="cx5-step"><span>✓</span>Cobrar ${h(money(due))} · elige el método</div>
              <div class="cx5-methods">
                ${PAYMENT_METHODS.map((pm) => `<button class="cx5-method" type="button" data-csh-pay="${pm.value}" ${state.paying ? "disabled" : ""}><i>${METHOD_ICONS_049V[pm.value]}</i>${h(pm.label)}</button>`).join("")}
              </div>
              ${due < Number(table.total || 0) ? `<p class="cx5-hint">Lo que sigue en cocina (${h(money(Number(table.total || 0) - due))}) se cobra cuando la marquen lista.</p>` : ""}` : `<p class="cx5-hint">La cocina aún no entrega este pedido: se cobra cuando esté listo.</p>`}
          </aside>
        </div>
      </section>`;
  }

  // ------------------------------------------------------------ nueva venta
  function catArt049V(cat) {
    const art = Kit.tileArt("category", cat, kitOptions("data-csh-cat"));
    if (art.type === "image") {
      // La imagen completa, nunca recortada, sobre su propio fondo difuminado.
      return `<span class="cx5-art" style="--img:url('${art.url}')"><img src="${art.url}" alt="" loading="lazy"></span>`;
    }
    return `<span class="cx5-art is-emoji">${art.emoji || "🍽️"}</span>`;
  }

  function categoryTiles049V() {
    const active = state.sale.category;
    const compact = Boolean(active || state.sale.query);
    return `
      <div class="cx5-cats ${compact ? "is-compact" : ""}" role="tablist" aria-label="Categorías">
        ${compact ? `<button class="cx5-cat is-all" type="button" data-csh-cat-all><span class="cx5-art is-emoji">▦</span><span class="cx5-cat-name">Todas</span></button>` : ""}
        ${state.menu.map((cat) => `
          <button class="cx5-cat ${cat.key === active ? "is-active" : ""}" type="button" role="tab" aria-selected="${cat.key === active ? "true" : "false"}" data-csh-cat="${h(cat.key)}">
            ${catArt049V(cat)}
            <span class="cx5-cat-name">${h(cat.label)}</span>
            <small>${h((cat.products || []).length)} producto${(cat.products || []).length === 1 ? "" : "s"}</small>
          </button>`).join("") || `<div class="cx5-empty">Sin categorías todavía.</div>`}
      </div>`;
  }

  function productTile049V(product, category) {
    const art = Kit.tileArt("product", product, kitOptions("data-csh-product"));
    const kitchen = productNeedsKitchen049V(product, category);
    return `
      <button class="cx5-prod" type="button" data-csh-product="${h(product.id)}">
        ${art.type === "image" ? `<span class="cx5-prod-art"><img src="${art.url}" alt="" loading="lazy"></span>` : art.type === "emoji" ? `<span class="cx5-prod-art is-emoji">${art.emoji}</span>` : ""}
        <span class="cx5-prod-name">${h(product.name)}</span>
        <span class="cx5-prod-foot">
          <strong>${product.is_portioned ? "Elegir porción" : h(money(product.price))}</strong>
          <em class="cx5-tag ${kitchen ? "is-kitchen" : "is-ready"}">${kitchen ? "🍳 Cocina" : "⚡ Listo"}</em>
        </span>
      </button>`;
  }

  function productsHtml049V() {
    const query = String(state.sale.query || "").trim().toLowerCase();
    if (query) {
      const hits = [];
      state.menu.forEach((cat) => (cat.products || []).forEach((p) => {
        if (String(p.name || "").toLowerCase().includes(query)) hits.push(productTile049V(p, cat));
      }));
      return `<div class="cx5-prods">${hits.join("") || `<div class="cx5-empty">Ningún producto coincide con “${h(state.sale.query)}”.</div>`}</div>`;
    }
    const category = saleCategory();
    if (!category) {
      // Sin categoria elegida: toda la carta, por categorias (nunca pantalla vacia).
      return state.menu.filter((cat) => (cat.products || []).length).map((cat) => `
        <h3 class="cx5-sub">${h(cat.label)}</h3>
        <div class="cx5-prods">${(cat.products || []).map((p) => productTile049V(p, cat)).join("")}</div>`).join("")
        || `<p class="cx5-pick">Sin productos activos en la carta.</p>`;
    }
    const subs = Array.isArray(category.subcategories) ? category.subcategories.filter((sub) => (sub.products || []).length) : [];
    if (subs.length) {
      const inSub = new Set(subs.flatMap((sub) => (sub.products || []).map((p) => p.id)));
      const loose = (category.products || []).filter((p) => !inSub.has(p.id));
      return subs.map((sub) => `
        <h3 class="cx5-sub">${h(sub.label)}</h3>
        <div class="cx5-prods">${(sub.products || []).map((p) => productTile049V(p, category)).join("")}</div>`).join("")
        + (loose.length ? `<h3 class="cx5-sub">Otros</h3><div class="cx5-prods">${loose.map((p) => productTile049V(p, category)).join("")}</div>` : "");
    }
    return `<div class="cx5-prods">${(category.products || []).map((p) => productTile049V(p, category)).join("") || `<div class="cx5-empty">Sin productos en esta categoría.</div>`}</div>`;
  }

  function routeHint049V(sale) {
    const where = sale.table ? ` y se suma a la cuenta de ${sale.table}` : "";
    if (sale.toKitchen) {
      return sale.table
        ? `Va a la pantalla de cocina${where}.`
        : "Va a la pantalla de cocina. La cobras en «Ventas de caja» cuando la marquen lista.";
    }
    return sale.table ? `Se entrega ya${where}.` : "Productos listos para entregar (ej. una gaseosa): se cobra ahora mismo.";
  }

  function suggestion049V(sale) {
    const cooking = (sale.items || []).filter(lineNeedsKitchen049V).map((line) => line.name);
    if (cooking.length) return `Sugerido: tiene platos que se preparan (${Array.from(new Set(cooking)).slice(0, 3).join(", ")}).`;
    return "Sugerido: todo está listo para entregar.";
  }

  function saleCart049V() {
    const sale = state.sale;
    const mode = saleMode(sale);
    const busy = state.saleBusy ? "disabled" : "";
    const count = sale.items.reduce((sum, item) => sum + (item.fraction || !Number.isInteger(Number(item.quantity)) ? 1 : Number(item.quantity || 0)), 0);
    return `
      <aside class="cx5-cart" aria-label="Resumen de la venta">
        <div class="cx5-cart-head">
          <strong>Resumen de la venta</strong>
          <span class="cx5-count">${h(count)}</span>
        </div>
        <div class="cx5-cart-dest">${sale.table ? `Para <b>${h(sale.table)}</b>` : "Venta independiente"}</div>
        <div class="cx5-lines">
          ${sale.items.map((item, index) => `
            <div class="cx5-line">
              <button type="button" class="cx5-line-main" data-csh-sale-edit="${index}">
                <b>${Kit.cartLineLabel(item)}</b>
                ${item.term ? `<small>${h(item.term)}</small>` : ""}
                ${item.observations ? `<small>${h(item.observations)}</small>` : ""}
                ${item.quick_notes && item.quick_notes.length ? `<small>${item.quick_notes.map(h).join(" · ")}</small>` : ""}
              </button>
              ${item.fraction || !Number.isInteger(Number(item.quantity)) ? `<span></span>` : `
                <span class="cx5-stepper">
                  <button type="button" data-csh-sale-step="${index}:-1" aria-label="Uno menos">−</button>
                  <b>${h(item.quantity)}</b>
                  <button type="button" data-csh-sale-step="${index}:1" aria-label="Uno más">＋</button>
                </span>`}
              <strong>${h(money(Number(item.unit_price || 0) * Number(item.quantity || 0)))}</strong>
              <button type="button" class="cx5-x" data-csh-sale-remove="${index}" aria-label="Quitar">✕</button>
            </div>`).join("") || `<div class="cx5-cart-empty"><span>🛒</span>Toca un producto para empezar la venta.</div>`}
        </div>
        <div class="cx5-cart-total"><span>Total</span><strong data-cx5-sale-total>${h(money(saleTotal(sale)))}</strong></div>
        ${sale.items.length ? `
          <div class="cx5-step"><span>1</span>¿Cómo sale?</div>
          <div class="cx5-route" role="radiogroup" aria-label="Preparación">
            <button type="button" role="radio" aria-checked="${sale.toKitchen ? "true" : "false"}" class="${sale.toKitchen ? "is-on" : ""}" data-csh-sale-route="kitchen">🍳 Preparar en cocina</button>
            <button type="button" role="radio" aria-checked="${sale.toKitchen ? "false" : "true"}" class="${sale.toKitchen ? "" : "is-on"}" data-csh-sale-route="now">⚡ Entregar ya</button>
          </div>
          <p class="cx5-hint">${h(routeHint049V(sale))}${sale.kitchenTouched ? "" : `<br><small>${h(suggestion049V(sale))}</small>`}</p>
          <div class="cx5-step"><span>2</span>${mode === "charge" ? `Cobrar ${h(money(saleTotal(sale)))} · método de pago` : mode === "kitchen" ? "Enviar" : "Agregar a la cuenta"}</div>
          ${mode === "charge" ? `
            <div class="cx5-methods">
              ${PAYMENT_METHODS.map((pm) => `<button class="cx5-method" type="button" data-csh-sale-pay="${pm.value}" ${busy}><i>${METHOD_ICONS_049V[pm.value]}</i>${h(pm.label)}</button>`).join("")}
            </div>` : `
            <button class="cx5-btn cx5-btn-primary cx5-send" type="button" data-csh-sale-send ${busy}>
              ${state.saleBusy ? "Enviando…" : mode === "kitchen" ? "🍳 Enviar a cocina" : `Agregar a ${h(sale.table)}`}
            </button>`}` : ""}
      </aside>`;
  }

  function screenSale049V() {
    const sale = state.sale;
    return `
      <section class="cx5 cx5-sale-screen">
        <header class="cx5-top">
          <button class="cx5-icon" type="button" data-csh-back aria-label="Volver">‹</button>
          <div class="cx5-id"><div><strong>Nueva venta</strong><small>Arma la venta, elige cómo sale y cobra.</small></div></div>
          <label class="cx5-dest">Para
            <select data-csh-sale-table>
              <option value="" ${sale.table ? "" : "selected"}>Venta independiente</option>
              ${saleTableOptions().map((label) => `<option value="${h(label)}" ${sale.table === label ? "selected" : ""}>${h(label)}</option>`).join("")}
            </select>
          </label>
        </header>
        <div class="cx5-sale">
          <div class="cx5-sale-main">
            <label class="cx5-search"><span aria-hidden="true">🔎</span><input type="search" data-csh-sale-search placeholder="Buscar producto…" value="${h(sale.query || "")}" autocomplete="off"></label>
            ${categoryTiles049V()}
            <div id="cx5Products" class="cx5-products">${productsHtml049V()}</div>
          </div>
          ${saleCart049V()}
        </div>
      </section>`;
  }

  // ------------------------------------------------------------ Z del dia
  async function openZ049V() {
    state.z = { step: "loading", data: null, saved: null, busy: false, message: "" };
    state.moreOpen = false;
    safeRender();
    try {
      const data = await waiterApi("/caja/z");
      state.z = { step: "preview", data, saved: null, busy: false, message: "" };
    } catch (error) {
      state.z = { step: "error", data: null, saved: null, busy: false, message: error.message || "No se pudo calcular el Z." };
    }
    safeRender();
  }

  async function registerZ049V() {
    const z = state.z;
    if (!z || z.busy) return;
    z.busy = true;
    safeRender();
    try {
      const saved = await waiterApi("/caja/z", { method: "POST" });
      z.saved = saved;
      z.step = "done";
      z.message = "";
      if (z.data && Array.isArray(z.data.history)) z.data.history.unshift(saved);
      printZ049V(saved);
    } catch (error) {
      z.message = error.message || "No se pudo registrar el Z.";
    } finally {
      z.busy = false;
      safeRender();
    }
  }

  async function reprintZ049V(id) {
    try {
      printZ049V(await waiterApi(`/caja/z/${encodeURIComponent(id)}`));
    } catch (error) {
      state.error = error.message || "No se pudo reimprimir el Z.";
      safeRender();
    }
  }

  function methodRows049V(methods, top) {
    return (methods || []).map((m) => `
      <div class="cx5-pay-row"><em>${METHOD_ICONS_049V[m.method] || "🧾"} ${h(m.label)} <small>(${h(m.count || 0)})</small></em>
        <i style="--w:${Math.round((Number(m.total || 0) / Math.max(1, top)) * 100)}%"></i><b>${h(money(m.total))}</b></div>`).join("");
  }

  function zBody049V(z) {
    const top = Math.max(1, ...(z.methods || []).map((m) => Number(m.total || 0)));
    return `
      <div class="cx5-z-total"><span>Total de ventas del día</span><strong data-cx5-z="total">${h(money(z.total))}</strong></div>
      <div class="cx5-z-stats">
        <div><span>Ventas</span><b data-cx5-z="sales">${h(z.sales)}</b></div>
        <div><span>Productos vendidos</span><b data-cx5-z="products">${h(z.products)}</b></div>
        <div><span>Pedidos cobrados</span><b>${h(z.orders)}</b></div>
      </div>
      <div class="cx5-z-methods">${methodRows049V(z.methods, top)}</div>
      ${(z.channels || []).length ? `<div class="cx5-z-channels">${z.channels.map((c) => `<span>${h(c.label)}: <b>${h(c.count)}</b> · ${h(money(c.total))}</span>`).join("")}</div>` : ""}
      ${z.open_count ? `<p class="cx5-z-warn">⚠ Quedan ${h(z.open_count)} pedido${z.open_count === 1 ? "" : "s"} sin cobrar por ${h(money(z.open_total))}: no entran en este Z.</p>` : ""}
      ${z.cancelled_count ? `<p class="cx5-hint">Cancelados: ${h(z.cancelled_count)} por ${h(money(z.cancelled_total))} (no suman).</p>` : ""}`;
  }

  function zOverlay049V() {
    const z = state.z;
    if (!z) return "";
    let inner = "";
    if (z.step === "loading") inner = `<p class="cx5-pick">Calculando el Z del día…</p>`;
    else if (z.step === "error") inner = `<div class="csh-alert">${h(z.message)}</div><div class="cx5-modal-actions"><button class="cx5-btn" type="button" data-csh-z-close>Cerrar</button></div>`;
    else if (z.step === "preview") {
      const d = z.data || {};
      inner = `
        <p class="cx5-hint">Ventas cobradas desde ${h(d.since_local || "")} (las mismas del panel) · ${h(d.now_local || "")} · Cajero: <b>${h(d.cashier_name || "")}</b></p>
        ${zBody049V(d.z || {})}
        ${z.message ? `<div class="csh-alert">${h(z.message)}</div>` : ""}
        <p class="cx5-hint">Al sacarlo queda registrado con fecha, hora, número y tu nombre, y se imprime.</p>
        ${zHistory049V(d.history)}
        <div class="cx5-modal-actions">
          <button class="cx5-btn" type="button" data-csh-z-close ${z.busy ? "disabled" : ""}>Cancelar</button>
          <button class="cx5-btn cx5-btn-primary" type="button" data-csh-z-register ${z.busy ? "disabled" : ""}>${z.busy ? "Registrando…" : "🧾 Sacar e imprimir Z"}</button>
        </div>`;
    } else if (z.step === "done") {
      const saved = z.saved || {};
      inner = `
        <div class="cx5-z-done">✓ Z #${h(String(saved.number || "").padStart(4, "0"))} registrado · ${h(saved.created_local || "")} · ${h(saved.cashier_name || "")}</div>
        ${zBody049V(saved.summary || {})}
        ${zHistory049V(z.data && z.data.history)}
        <div class="cx5-modal-actions">
          <button class="cx5-btn" type="button" data-csh-z-print>🖨 Imprimir de nuevo</button>
          <button class="cx5-btn cx5-btn-primary" type="button" data-csh-z-close>Listo</button>
        </div>`;
    }
    return `
      <div class="cx5-modal" data-csh-z>
        <div class="cx5-modal-card" role="dialog" aria-label="Cierre de caja del día (Z)">
          <h2>🧾 Cierre de caja del día · Z</h2>
          ${inner}
        </div>
      </div>`;
  }

  function zHistory049V(history) {
    const rows = Array.isArray(history) ? history : [];
    if (!rows.length) return "";
    return `
      <div class="cx5-z-history"><span>Z sacados hoy</span>
        ${rows.map((row) => `<div><b>#${h(String(row.number || "").padStart(4, "0"))}</b><small>${h(row.created_local || "")} · ${h(row.cashier_name || "")}</small><em>${h(money(row.total))}</em><button class="cx5-icon" type="button" data-csh-z-reprint="${h(row.id)}" aria-label="Reimprimir">🖨</button></div>`).join("")}
      </div>`;
  }

  // Tirilla de 80 mm (misma impresion por iframe oculto que la cuenta).
  function zTicketHtml049V(saved) {
    const z = saved.summary || {};
    const line = (label, value) => `<div class="r"><span>${h(label)}</span><b>${h(value)}</b></div>`;
    return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Z ${h(saved.number)}</title>
<style>@page{size:80mm auto;margin:3mm}body{margin:0;font:12px/1.35 monospace;color:#000;background:#fff;width:74mm}
h1{font-size:15px;text-align:center;margin:0 0 1mm}h2{font-size:12px;margin:2mm 0 1mm;border-bottom:1px dashed #000}
.c{text-align:center}.r{display:flex;justify-content:space-between;gap:2mm}.big{font-size:16px;font-weight:900}
table{width:100%;border-collapse:collapse}td{vertical-align:top}td:last-child{text-align:right;white-space:nowrap}</style></head><body>
<h1>${h(z.company_name || saved.company_name || "")}</h1>
<div class="c"><b>CIERRE DE CAJA · Z #${h(String(saved.number || "").padStart(4, "0"))}</b></div>
${line("Fecha y hora", saved.created_local || "")}
${line("Desde", z.since_local || saved.business_day || "")}
${line("Cajero", saved.cashier_name || "")}
<h2>VENTAS DEL DÍA</h2>
${line("Ventas", z.sales || 0)}
${line("Pedidos cobrados", z.orders || 0)}
${line("Productos vendidos", z.products || 0)}
<div class="r big"><span>TOTAL</span><span>${h(money(z.total))}</span></div>
<h2>POR MÉTODO DE PAGO</h2>
${(z.methods || []).map((m) => line(`${m.label} (${m.count || 0})`, money(m.total))).join("")}
${(z.channels || []).length ? `<h2>POR CANAL</h2>${z.channels.map((c) => line(`${c.label} (${c.count})`, money(c.total))).join("")}` : ""}
${(z.items || []).length ? `<h2>PRODUCTOS</h2><table>${z.items.map((i) => `<tr><td>${h(i.units)} ${h(i.name)}</td><td>${h(money(i.total))}</td></tr>`).join("")}</table>` : ""}
${z.open_count ? `<h2>SIN COBRAR (no suman)</h2>${line(`${z.open_count} pedido(s)`, money(z.open_total))}` : ""}
${z.cancelled_count ? line(`Cancelados: ${z.cancelled_count}`, money(z.cancelled_total)) : ""}
<p class="c">_______________________<br>Firma cajero</p>
</body></html>`;
  }

  function printZ049V(saved) {
    if (!saved) return null;
    const frame = document.createElement("iframe");
    frame.setAttribute("aria-hidden", "true");
    frame.style.position = "fixed";
    frame.style.right = "0";
    frame.style.bottom = "0";
    frame.style.width = "0";
    frame.style.height = "0";
    frame.style.border = "0";
    document.body.appendChild(frame);
    const win = frame.contentWindow;
    win.document.open();
    win.document.write(zTicketHtml049V(saved));
    win.document.close();
    const go = () => {
      try {
        win.focus();
        win.print();
      } finally {
        window.setTimeout(() => frame.remove(), 1000);
      }
    };
    if (win.document.readyState === "complete") window.setTimeout(go, 50);
    else frame.onload = go;
    return frame;
  }

  function render() {
    safeRender();
  }

  // 049X: un refresco de fondo (sondeo de mesas, indicadores, turno) no
  // redibuja mientras el cajero escribe: ni con el arqueo abierto, ni con el
  // foco en un campo del panel. Lo aplaza al siguiente sondeo.
  function typing049X() {
    if (state.arqueo) return true;
    const active = typeof document !== "undefined" ? document.activeElement : null;
    if (!active || !root.contains || !root.contains(active)) return false;
    return /^(INPUT|TEXTAREA|SELECT)$/.test(String(active.tagName || "").toUpperCase());
  }

  function backgroundRender049X() {
    if (!typing049X()) safeRender();
  }

  // One failing screen must not blank the whole panel.
  function focusedField049X() {
    const active = typeof document !== "undefined" ? document.activeElement : null;
    if (!active || !root.contains || !root.contains(active) || !active.attributes) return null;
    const attr = Array.from(active.attributes).find((a) => /^data-csh-/.test(a.name));
    if (!attr) return null;
    let start = null;
    let end = null;
    try { start = active.selectionStart; end = active.selectionEnd; } catch (_) {}
    return { selector: attr.value ? `[${attr.name}="${attr.value}"]` : `[${attr.name}]`, start, end };
  }

  function restoreField049X(saved) {
    if (!saved || !root.querySelector) return;
    const again = root.querySelector(saved.selector);
    if (!again || typeof again.focus !== "function") return;
    again.focus();
    if (saved.start !== null) {
      try { again.setSelectionRange(saved.start, saved.end); } catch (_) {}
    }
  }

  function safeRender() {
    const focused = focusedField049X();
    try {
      renderScreen();
      restoreField049X(focused);
    } catch (error) {
      try { console.error("[caja] render", error); } catch (_) {}
      root.innerHTML = `
        <section class="csh-shell csh-recover">
          <div class="csh-recover-card">
            <strong>Algo falló al mostrar esta pantalla.</strong>
            <p>Tu sesión sigue abierta.</p>
            <button class="csh-btn csh-btn-primary" type="button" data-csh-recover>Volver a mesas</button>
          </div>
        </section>`;
    }
    renderConnection();
  }

  function renderScreen() {
    let html = "";
    // 049V: con el interruptor, el tablero, la mesa y la venta rediseñados.
    const cx5 = state.redesign && state.screen !== "login";
    if (state.screen === "login") html = screenLogin();
    else if (state.screen === "tables") html = cx5 ? screenTables049V() : screenTables();
    else if (state.screen === "table") html = cx5 ? screenTable049V() : screenTable();
    else if (state.screen === "delivery") html = screenDelivery();
    else if (state.screen === "sale") html = cx5 ? screenSale049V() : screenSale();
    else if (state.screen === "sale_products") html = cx5 ? screenSale049V() : screenSaleProducts();
    if (Alerts && Alerts.setVisible) Alerts.setVisible(state.screen !== "login");
    if (state.screen !== "login") html += costosOverlay048U();
    if (cx5) html += zOverlay049V();
    if (cx5) root.setAttribute("data-cx5", "1");
    else if (root.removeAttribute) root.removeAttribute("data-cx5");
    root.innerHTML = html;
    if (state.error && state.screen !== "login") {
      const banner = document.createElement("div");
      banner.className = "csh-alert csh-alert-floating";
      banner.textContent = state.error;
      root.appendChild(banner);
      window.setTimeout(() => { state.error = ""; }, 4000);
    }
    if (state.toast) window.setTimeout(() => { state.toast = ""; }, 3000);
  }

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("[data-csh-sale-table]")) {
      state.sale.table = String(target.value || "");
      safeRender();
    } else if (target.closest("[data-csh-sale-kitchen]")) {
      state.sale.toKitchen = Boolean(target.checked);
      safeRender();
    }
  });

  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!target || !target.closest || !state.arqueo) return;
    const draft = arqDraft049X();
    if (target.closest("[data-csh-arq-total]")) {
      draft.total = digits049X(target.value);
      if (target.value !== draft.total) keepCaret049X(target, draft.total);
      const read = document.querySelector ? document.querySelector("[data-csh-arq-read]") : null;
      if (read) read.textContent = arqReading049X(draft.total);
    } else if (target.closest("[data-csh-den]")) {
      const clean = digits049X(target.value);
      draft.dens[target.getAttribute("data-csh-den")] = clean;
      if (target.value !== clean) keepCaret049X(target, clean);
    } else if (target.closest("[data-csh-arq-obs]")) {
      draft.obs = String(target.value || "");
    }
  });

  // Quita lo que no es dígito sin mandar el cursor al final.
  function keepCaret049X(input, clean) {
    let pos = null;
    try { pos = input.selectionStart; } catch (_) {}
    const before = pos === null ? null : digits049X(String(input.value).slice(0, pos)).length;
    input.value = clean;
    if (before !== null) {
      try { input.setSelectionRange(before, before); } catch (_) {}
    }
  }

  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!target || !target.closest || !target.closest("[data-csh-sale-search]")) return;
    state.sale.query = String(target.value || "");
    const box = document.getElementById("cx5Products");
    if (box) box.innerHTML = productsHtml049V();
    const cats = root.querySelector ? root.querySelector(".cx5-cats") : null;
    if (cats && cats.classList) cats.classList.toggle("is-compact", Boolean(state.sale.query.trim() || state.sale.category));
  });

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("#cshLoginForm");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    doLogin(String(data.get("username") || ""), String(data.get("password") || ""));
  });

  document.addEventListener("click", (event) => {
    try {
      handleClick(event);
    } catch (error) {
      try { console.error("[caja] click", error); } catch (_) {}
      state.error = "No se pudo completar esa acción. Intenta de nuevo.";
      safeRender();
    }
  });

  function handleClick(event) {
    const target = event.target;

    // 049V: el menu "⋯" se cierra al tocar cualquier otra cosa.
    if (state.moreOpen && !target.closest("[data-csh-more]")) {
      state.moreOpen = false;
      if (!target.closest("[data-csh-register-network]") && !target.closest("[data-csh-logout]")) safeRender();
    }

    const recover = target.closest("[data-csh-recover]");
    if (recover) {
      closeOpenSheets();
      resetToTables();
      return;
    }

    const logout = target.closest("[data-csh-logout]");
    if (logout) {
      stopPolling();
      stopSessionKeeper();
      setToken("");
      state.screen = "login";
      render();
      return;
    }

    const backBtn = target.closest("[data-csh-back]");
    if (backBtn) {
      back();
      return;
    }

    if (target.closest("[data-csh-shift-toggle]")) {
      state.shiftOpen = !state.shiftOpen;
      safeRender();
      return;
    }
    if (target.closest("[data-csh-shift-pause]")) {
      shiftAction("pause");
      return;
    }
    if (target.closest("[data-csh-shift-resume]")) {
      shiftAction("resume");
      return;
    }
    if (target.closest("[data-csh-shift-finish]")) {
      // 048U: con Costos, cerrar la jornada pasa primero por el arqueo a ciegas.
      if (state.costos) {
        openArqueo048U();
        return;
      }
      if (window.confirm("¿Cerrar tu jornada? Se registran tus horas y se cierra la sesión.")) shiftAction("finish");
      return;
    }
    if (target.closest("[data-csh-more]")) { state.moreOpen = !state.moreOpen; safeRender(); return; }
    if (target.closest("[data-csh-z-open]")) { openZ049V(); return; }
    if (target.closest("[data-csh-z-register]")) { registerZ049V(); return; }
    if (target.closest("[data-csh-z-close]")) { state.z = null; safeRender(); return; }
    if (target.closest("[data-csh-z-print]")) { if (state.z && state.z.saved) printZ049V(state.z.saved); return; }
    const zReprint = target.closest("[data-csh-z-reprint]");
    if (zReprint) { reprintZ049V(zReprint.getAttribute("data-csh-z-reprint") || ""); return; }
    const printOrder = target.closest("[data-csh-print-order]");
    if (printOrder && !printOrder.disabled) { printAccount([printOrder.getAttribute("data-csh-print-order")]); return; }
    if (target.closest("[data-csh-cat-all]")) { state.sale.category = ""; state.sale.query = ""; safeRender(); return; }
    const saleRoute = target.closest("[data-csh-sale-route]");
    if (saleRoute) {
      state.sale.toKitchen = saleRoute.getAttribute("data-csh-sale-route") === "kitchen";
      state.sale.kitchenTouched = true;
      safeRender();
      return;
    }
    const saleStep = target.closest("[data-csh-sale-step]");
    if (saleStep) {
      const [index, delta] = String(saleStep.getAttribute("data-csh-sale-step") || "").split(":");
      const line = state.sale.items[Number(index)];
      if (line && !line.fraction && Number.isInteger(Number(line.quantity))) line.quantity = Kit.stepQuantity(line.quantity, Number(delta));
      safeRender();
      return;
    }
    if (target.closest("[data-csh-arq-cancel]")) { state.arqueo = null; safeRender(); return; }
    if (target.closest("[data-csh-arq-submit]")) { submitCount048U(); return; }
    if (target.closest("[data-csh-arq-save-obs]")) { saveObservation048U(); return; }
    if (target.closest("[data-csh-arq-finish]")) {
      const a = state.arqueo;
      if (a && a.result && a.result.needs_observation) recordIncident049Y("observacion", "Cerro sin guardar la observacion de la diferencia.", null);
      continueClose049Y();
      return;
    }
    if (target.closest("[data-csh-arq-skip]")) { skipCount049Y(); return; }
    if (target.closest("[data-csh-close-z]")) { takeZ049Y(); return; }
    if (target.closest("[data-csh-close-z-print]")) { if (state.arqueo && state.arqueo.zSaved) printZ049V(state.arqueo.zSaved); return; }
    if (target.closest("[data-csh-close-finish]")) { finishClose049Y(); return; }
    if (target.closest("[data-csh-close-leave]")) {
      logoutAfterClose049Y("Saliste del panel. El turno no se pudo cerrar en el servidor: avísale al administrador.");
      return;
    }

    const openDelivery = target.closest("[data-csh-open-delivery]");
    if (openDelivery) {
      state.activeDeliveryId = openDelivery.getAttribute("data-csh-open-delivery") || "";
      state.driversOpen = false;
      goto("delivery");
      return;
    }
    if (target.closest("[data-csh-verify-payment]")) {
      if (window.confirm("¿Confirmaste en la cuenta del banco que el dinero llegó? Un comprobante se puede falsificar.")) {
        deliveryAction("verify-payment", {}, "Pago confirmado.");
      }
      return;
    }
    if (target.closest("[data-csh-drivers-toggle]")) {
      toggleDrivers();
      return;
    }
    const assignDriver = target.closest("[data-csh-assign-driver]");
    if (assignDriver && !assignDriver.disabled) {
      deliveryAction("assign", { employee_id: assignDriver.getAttribute("data-csh-assign-driver") }, "Pedido enviado al domiciliario.");
      return;
    }
    const dispatched = target.closest("[data-csh-dispatched]");
    if (dispatched && !dispatched.disabled) {
      deliveryAction("dispatched", {}, "Avisamos al cliente que su pedido va en camino.");
      return;
    }
    const deliveryPay = target.closest("[data-csh-delivery-pay]");
    if (deliveryPay && !deliveryPay.disabled) {
      const method = deliveryPay.getAttribute("data-csh-delivery-pay");
      const order = activeDelivery();
      if (method === "cash" && order) {
        openCashSheet({ total: Number(order.total || 0), label: `Domicilio ${deliveryNumber(order)}`, onConfirm: (cash) => chargeDelivery("cash", cash) });
      } else {
        chargeDelivery(method);
      }
      return;
    }

    const openTable = target.closest("[data-csh-open-table]");
    if (openTable) {
      state.activeTableKey = openTable.getAttribute("data-csh-open-table") || "";
      goto("table");
      return;
    }

    const registerNet = target.closest("[data-csh-register-network]");
    if (registerNet) {
      registerNetwork();
      return;
    }

    const addProduct = target.closest("[data-csh-add-product]");
    if (addProduct) {
      const table = activeTable();
      if (state.directSale && table) openSale(String(table.table_number));
      else openProductPicker();
      return;
    }

    const newSale = target.closest("[data-csh-new-sale]");
    if (newSale) {
      openSale("");
      return;
    }

    const saleCat = target.closest("[data-csh-cat]");
    if (saleCat) {
      openSaleCategory(saleCat.getAttribute("data-csh-cat") || "");
      return;
    }

    const saleProduct = target.closest("[data-csh-product]");
    if (saleProduct) {
      openSaleProduct(saleProduct.getAttribute("data-csh-product") || "");
      return;
    }

    const saleRemove = target.closest("[data-csh-sale-remove]");
    if (saleRemove) {
      state.sale.items.splice(Number(saleRemove.getAttribute("data-csh-sale-remove")), 1);
      syncKitchen049V();
      safeRender();
      return;
    }

    const saleEdit = target.closest("[data-csh-sale-edit]");
    if (saleEdit) {
      editSaleLine(Number(saleEdit.getAttribute("data-csh-sale-edit")));
      return;
    }

    const printBtn = target.closest("[data-csh-print]");
    if (printBtn && !printBtn.disabled) {
      const table = activeTable();
      if (table) printAccount(table.orders.map((o) => o.id));
      return;
    }

    const printLast = target.closest("[data-csh-print-last]");
    if (printLast && !printLast.disabled) {
      if (state.lastCharged) printAccount(state.lastCharged.order_ids);
      return;
    }

    const salePay = target.closest("[data-csh-sale-pay]");
    if (salePay && !salePay.disabled) {
      const method = salePay.getAttribute("data-csh-sale-pay");
      if (method === "cash") {
        openCashSheet({ total: saleTotal(state.sale), label: "Venta", onConfirm: (cash) => submitSale("cash", cash) });
      } else {
        submitSale(method);
      }
      return;
    }

    const saleSend = target.closest("[data-csh-sale-send]");
    if (saleSend && !saleSend.disabled) {
      submitSale(null);
      return;
    }

    const payBtn = target.closest("[data-csh-pay]");
    if (payBtn && !payBtn.disabled) {
      const method = payBtn.getAttribute("data-csh-pay");
      const table = activeTable();
      if (method === "cash" && table) {
        openCashSheet({ total: chargeableTotal(table), label: tableTitle(table.table_number), onConfirm: (cash) => chargeTable("cash", cash) });
      } else {
        chargeTable(method);
      }
    }
  }

  function openProductPicker() {
    const sheet = document.createElement("div");
    sheet.className = "csh-sheet-backdrop";
    const products = state.menu.flatMap((cat) => cat.products || []);
    sheet.innerHTML = `
      <div class="csh-sheet">
        <h2>Agregar producto</h2>
        <input id="cshSheetSearch" placeholder="Buscar producto..." />
        <div class="csh-sheet-list" id="cshSheetList">
          ${products.map((p) => `<button type="button" class="csh-sheet-item" data-product-id="${h(p.id)}"><span>${h(p.name)}</span><strong>${h(money(p.price))}</strong></button>`).join("")}
        </div>
        <button type="button" class="csh-btn" data-sheet-cancel>Cerrar</button>
      </div>`;
    document.body.appendChild(sheet);
    sheet.querySelector("#cshSheetSearch").addEventListener("input", (event) => {
      const q = String(event.target.value || "").toLowerCase();
      sheet.querySelectorAll(".csh-sheet-item").forEach((btn) => {
        const text = btn.textContent.toLowerCase();
        btn.style.display = text.includes(q) ? "" : "none";
      });
    });
    sheet.querySelector("[data-sheet-cancel]").addEventListener("click", () => sheet.remove());
    sheet.querySelectorAll("[data-product-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const product = products.find((p) => p.id === btn.getAttribute("data-product-id"));
        if (!product) return;
        sheet.remove();
        addProductToTable(product, 1);
      });
    });
  }

  const style = document.createElement("style");
  style.textContent = `
    :root{color-scheme:dark}
    *{box-sizing:border-box}
    body{margin:0;background:#080712;color:#f5f3ff;font-family:Inter,system-ui,sans-serif}
    .csh-login{min-height:100vh;display:grid;place-items:center;padding:20px;
      background:radial-gradient(circle at 20% 15%,rgba(247,37,133,.25),transparent 35%),linear-gradient(135deg,#0a0714,#0d1522 70%,#150019)}
    .csh-login-card{width:100%;max-width:360px;padding:28px 22px;border-radius:22px;border:1px solid rgba(255,255,255,.12);background:rgba(15,12,28,.85)}
    .csh-brand{font-size:12px;font-weight:900;letter-spacing:.2em;color:#ff2d95}
    .csh-login-card h1{margin:6px 0 18px;font-size:26px}
    .csh-login-card form{display:grid;gap:14px}
    .csh-login-card label{display:grid;gap:6px;font-size:13px;font-weight:800;color:#c9c3e6}
    .csh-login-card input{padding:14px;border-radius:14px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff;font-size:16px}
    .csh-btn{min-height:46px;border-radius:14px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:14px;font-weight:900;cursor:pointer;padding:0 14px}
    .csh-btn-primary{border:none;background:linear-gradient(135deg,#ff7a18,#ff2d95 55%,#a855f7)}
    .csh-btn-mini{min-height:36px;font-size:12px}
    .csh-alert{margin-top:10px;padding:10px 12px;border-radius:12px;background:rgba(239,68,68,.16);color:#fecaca;font-size:13px;font-weight:800}
    .csh-alert-floating{position:fixed;left:16px;right:16px;bottom:16px;z-index:50}
    .csh-modal-048u{position:fixed;inset:0;z-index:60;background:rgba(0,0,0,.72);display:grid;place-items:center;padding:16px;overflow:auto}
    .csh-modal-card-048u{width:min(520px,100%);display:grid;gap:12px;padding:18px;border-radius:18px;background:#141225;border:1px solid rgba(255,255,255,.14);color:#fff}
    .csh-modal-card-048u h2{margin:0;font-size:22px}
    .csh-modal-card-048u p{margin:0;opacity:.85;line-height:1.4}
    .csh-modal-card-048u label{display:grid;gap:6px;font-weight:800;font-size:14px}
    .csh-modal-card-048u input,.csh-modal-card-048u select,.csh-modal-card-048u textarea{min-height:46px;border-radius:12px;padding:8px 12px;font-size:18px}
    .csh-den-048u{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:8px}
    .csh-den-048u input{font-size:16px}
    .csh-arq-read-049x{min-height:18px;font-weight:800;opacity:.85}
    .csh-modal-actions-048u{display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap}
    .csh-arq-rows-048u{display:grid;gap:8px}
    .csh-arq-rows-048u div{display:flex;justify-content:space-between;font-size:18px}
    .csh-arq-rows-048u small{opacity:.7}
    .csh-arq-rows-048u .bad{color:#f87171;font-size:22px}.csh-arq-rows-048u .warn{color:#fbbf24;font-size:22px}.csh-arq-rows-048u .ok{color:#4ade80;font-size:22px}
    .csh-toast{margin:0 16px 10px;padding:10px 12px;border-radius:12px;background:rgba(34,197,94,.16);color:#bbf7d0;font-weight:800}
    .csh-shift{margin:10px 16px 0;border:1px solid rgba(34,197,94,.45);border-radius:14px;background:rgba(22,163,74,.12)}
    .csh-shift.is-break{border-color:rgba(245,158,11,.55);background:rgba(245,158,11,.14)}
    .csh-shift-chip{width:100%;display:flex;align-items:center;gap:12px;padding:10px 14px;border:0;background:none;color:inherit;font:inherit;cursor:pointer;min-height:48px}
    .csh-shift-chip span{font-weight:900}
    .csh-shift-chip strong{margin-left:auto;font-size:20px;font-variant-numeric:tabular-nums}
    .csh-shift-panel{display:grid;gap:10px;padding:0 14px 14px}
    .csh-shift-times{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .csh-shift-times div{display:grid;gap:2px;padding:8px 10px;border-radius:10px;background:rgba(0,0,0,.25)}
    .csh-shift-times span{font-size:12px;opacity:.75}
    .csh-shift-times strong{font-size:18px;font-variant-numeric:tabular-nums}
    .csh-shift-actions{display:flex;gap:8px;flex-wrap:wrap}
    .csh-btn-danger{background:#b91c1c;border-color:#b91c1c;color:#fff}
    .csh-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;padding:16px;background:rgba(8,7,18,.92);backdrop-filter:blur(6px);border-bottom:1px solid rgba(255,255,255,.08);flex-wrap:wrap}
    .csh-header h1{flex:1;margin:0;font-size:20px}
    .csh-back,.csh-logout{width:40px;height:40px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:18px}
    .csh-grid-tables{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;padding:16px}
    .csh-tile{display:grid;gap:6px;text-align:left;border-radius:18px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff;padding:14px}
    .csh-tile-top{display:flex;justify-content:space-between;align-items:center}
    .csh-status{font-size:10px;font-weight:900;text-transform:uppercase;color:#a5b4fc}
    .csh-tile-mid{font-size:11px;color:#c9c3e6}
    .csh-account-label{margin:12px 16px 0;font-size:11px;font-weight:900;letter-spacing:.08em;color:#ffb3d9;text-transform:uppercase}
    .csh-cart-list{display:grid;gap:10px;padding:16px}
    .csh-cart-row{display:flex;justify-content:space-between;gap:10px;padding:12px;border-radius:16px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04)}
    .csh-note{font-size:12px;color:#ffb3d9}
    .csh-cart-total{display:flex;justify-content:space-between;padding:0 16px;font-size:18px;font-weight:900;margin-bottom:14px}
    .csh-shell > .csh-btn{margin:0 16px 12px;width:calc(100% - 32px)}
    .csh-pay-block{margin:0 16px;padding:14px;border-radius:18px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1)}
    .csh-pay-title{font-size:12px;font-weight:900;color:#c9c3e6;margin-bottom:10px}
    .csh-pay-options{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
    .csh-hint{margin:0 16px;color:#8f8aa8;font-size:13px}
    .csh-empty{padding:20px;color:#8f8aa8;text-align:center;grid-column:1/-1}
    .csh-sheet-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);display:grid;align-items:end;z-index:60}
    .csh-sheet{background:#120e20;border-radius:24px 24px 0 0;padding:22px;display:grid;gap:12px;max-height:80vh}
    .csh-sheet h2{margin:0}
    .csh-sheet input{padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff}
    .csh-sheet-list{display:grid;gap:8px;overflow-y:auto;max-height:50vh}
    .csh-sale-dest{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end;padding:12px 16px 0}
    .csh-sale-dest label{display:grid;gap:6px;font-size:12px;font-weight:900;color:#c9c3e6}
    .csh-sale-dest select{padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.16);background:#120e20;color:#fff;font-size:15px}
    .csh-check{display:flex !important;align-items:center;gap:8px;font-size:14px !important;padding:12px;border-radius:12px;background:rgba(255,255,255,.05)}
    .csh-check input{width:20px;height:20px}
    .csh-sale-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,380px);gap:0;align-items:start;padding-right:16px}
    @media (max-width:860px){.csh-sale-layout{grid-template-columns:1fr;padding:0 16px}}
    .csh-sale-cart{position:sticky;top:72px;display:grid;gap:10px;min-width:0;margin:16px 0;padding:16px;border-radius:20px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04)}
    .csh-sale-cart-title{font-size:13px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#c9c3e6}
    .csh-line{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.08)}
    .csh-line-main{display:grid;gap:2px;text-align:left;background:none;border:none;color:#fff;padding:0;cursor:pointer;font:inherit}
    .csh-line-main small{color:#ffb3d9;font-size:11px}
    .csh-line-remove{width:30px;height:30px;border-radius:10px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff}
    .csh-section-title{margin:22px 16px 0;font-size:20px;font-weight:1000}
    .csh-card-delivery{border-color:#38bdf8}
    .csh-pay-warn{display:inline-block;padding:4px 8px;border-radius:10px;background:rgba(239,68,68,.22);color:#fecaca;font-size:12px;font-weight:900}
    .csh-pay-ok{display:inline-block;padding:4px 8px;border-radius:10px;background:rgba(34,197,94,.22);color:#86efac;font-size:12px;font-weight:900}
    .csh-pay-cod{display:inline-block;padding:4px 8px;border-radius:10px;background:rgba(255,209,102,.16);color:#ffd166;font-size:12px;font-weight:900}
    .csh-qr-warning{display:grid;gap:10px;padding:14px;border-radius:18px;border:2px solid #ef4444;background:rgba(239,68,68,.14);color:#fecaca}
    .csh-qr-warning strong{font-size:16px;color:#fff}
    .csh-delivery-info{display:grid;gap:8px;padding:14px;border-radius:18px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);font-size:14px}
    .csh-delivery-info span{display:inline-block;min-width:88px;color:#8f8aa8;font-size:12px;font-weight:800}
    .csh-delivery-info a{color:#7dd3fc;font-weight:900}
    .csh-delivery-driver{display:grid;gap:10px}
    .csh-driver-list{display:grid;gap:8px}
    .csh-card{display:grid;gap:6px;text-align:left;border-radius:20px;border:2px solid rgba(255,255,255,.12);background:rgba(255,255,255,.05);color:#fff;padding:14px;cursor:pointer}
    .csh-card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
    .csh-card-number{display:grid;line-height:1}
    .csh-card-number small{font-size:11px;font-weight:900;letter-spacing:.1em;text-transform:uppercase;color:#a5b4fc}
    .csh-card-number b{font-size:40px;font-weight:1000;letter-spacing:-.02em}
    .csh-card-timer{font-size:13px;font-weight:900;font-variant-numeric:tabular-nums;color:#fde68a;white-space:nowrap}
    .csh-card-state{justify-self:start;white-space:nowrap;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.04em;background:rgba(255,255,255,.1)}
    .csh-card-preparing{border-color:#d97706}.csh-card-preparing .csh-card-state,.csh-state-preparing{background:rgba(217,119,6,.25);color:#fde68a}
    .csh-card-ready{border-color:#16a34a}.csh-card-ready .csh-card-state,.csh-state-ready{background:rgba(34,197,94,.22);color:#86efac}
    .csh-cash{max-width:560px;margin:0 auto;width:100%}
    .csh-cash-total{display:flex;justify-content:space-between;align-items:baseline;font-size:15px;font-weight:900;color:#c9c3e6}
    .csh-cash-total strong{font-size:26px;color:#fff}
    .csh-cash-label{display:grid;gap:6px;font-size:13px;font-weight:900;color:#c9c3e6}
    .csh-cash-label input{font-size:30px !important;font-weight:1000;text-align:right;padding:14px !important}
    .csh-cash-bills{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}
    .csh-cash-change{display:flex;justify-content:space-between;align-items:baseline;padding:14px 16px;border-radius:16px;background:rgba(34,197,94,.14);font-weight:900}
    .csh-cash-change span{font-size:16px;color:#bbf7d0}
    .csh-cash-change strong{font-size:44px;line-height:1;color:#86efac;font-variant-numeric:tabular-nums}
    .csh-cash-change strong.csh-cash-missing{color:#fca5a5}
    .csh-cash-actions{display:grid;grid-template-columns:1fr 2fr;gap:10px}
    .csh-cash-actions .csh-btn{min-height:56px;font-size:17px}
    .csh-cash-actions .csh-btn-primary:disabled{opacity:.55;cursor:not-allowed}
    .csh-card-waiter{font-size:12px;color:#c9c3e6}
    .csh-card-total{font-size:20px;color:#ffd166}
    .csh-last{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:0 16px 10px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.05);font-size:13px}
    .csh-detail{display:grid;gap:12px;padding:12px 16px 24px;max-width:820px}
    .csh-detail-meta{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;font-weight:800;color:#c9c3e6}
    .csh-detail-lines{width:100%;border-collapse:collapse;font-size:14px}
    .csh-detail-lines th{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#8f8aa8;border-bottom:1px solid rgba(255,255,255,.12);padding:6px 4px}
    .csh-detail-lines td{padding:7px 4px;border-bottom:1px solid rgba(255,255,255,.06);vertical-align:top}
    .csh-detail-lines td:first-child{width:56px;font-weight:900;color:#ffd166;white-space:nowrap}
    .csh-detail-lines td:last-child,.csh-detail-lines th:last-child{text-align:right;white-space:nowrap}
    .csh-detail-lines tfoot td{font-size:18px;font-weight:1000;border-bottom:none;padding-top:10px}
    .csh-detail-actions{display:flex;gap:8px;flex-wrap:wrap}
    .csh-detail .csh-pay-block,.csh-detail .csh-hint{margin:0}    .csh-sale-cart .csh-cart-total{padding:0}
    .csh-sale-cart .csh-pay-block{margin:0}
    .csh-sale-cart .csh-pay-options{grid-template-columns:1fr}
    .csh-qty{display:flex;align-items:center;gap:10px}
    .csh-qty .csh-btn-mini{width:40px;padding:0;font-size:18px}
    .csh-sale-send{width:100%;min-height:56px;font-size:16px}
    .csh-net{position:fixed;left:0;right:0;bottom:0;z-index:80;padding:12px 16px;background:#b45309;color:#fff;font-size:14px;font-weight:900;text-align:center}
    .csh-recover{display:grid;place-items:center;padding:24px}
    .csh-recover-card{max-width:360px;display:grid;gap:12px;padding:22px;border-radius:20px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);text-align:center}
    .csh-recover-card p{margin:0;color:#c9c3e6}
    .csh-sheet-item{display:flex;justify-content:space-between;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#fff}
    /* 049V: rediseno de la caja. Colores de la marca por variables (hsp_brand.js); sin marca, oscuro de siempre. */
    #app[data-cx5]{--k-surface:var(--cxb-surface,#15131f);--k-surface2:var(--cxb-surface2,#1d1a2b);--k-ink:var(--cxb-ink,#f5f3ff);--k-ink-rgb:var(--cxb-ink-rgb,245,243,255);--k-muted:var(--cxb-muted,#a19cbc);--k-line:var(--cxb-line,#2a2638);--k-primary:var(--cxb-primary,#ff2d95);--k-primary-rgb:var(--cxb-primary-rgb,255,45,149);--k-secondary:var(--cxb-secondary,#ff7a18);--k-on-primary:var(--cxb-on-primary,#fff);--k-primary-ink:var(--cxb-primary-ink,#ff7ab8);--k-field:var(--cxb-field,#0e0c18);--k-header:var(--cxb-header,rgba(11,10,20,.92))}
    .cx5{min-height:100vh;color:var(--k-ink);padding-bottom:28px}
    .cx5-home{display:flex;flex-direction:column}
    .cx5 button:focus-visible,.cx5 select:focus-visible,.cx5 input:focus-visible{outline:3px solid rgba(var(--k-primary-rgb),.45);outline-offset:2px}
    .cx5-top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:10px 20px;background:var(--k-header);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--k-line)}
    .cx5-id{display:flex;align-items:center;gap:10px;min-width:0;margin-right:auto}
    .cx5-id strong{display:block;font-size:19px;font-weight:800;letter-spacing:-.01em}
    .cx5-id small{display:block;font-size:12px;color:var(--k-muted)}
    .cx5-id small::first-letter{text-transform:uppercase}
    .cx5-logo{flex:0 0 auto;width:48px;height:48px;border-radius:12px;background:var(--cxb-logo) center/contain no-repeat}
    .cx5-mark{flex:0 0 auto;width:42px;height:42px;border-radius:12px;display:grid;place-items:center;background:var(--k-primary);color:var(--k-on-primary);font-weight:900;font-size:20px}
    .cx5-shift{display:flex;align-items:center;gap:10px;padding:5px 6px 5px 12px;border-radius:999px;border:1px solid var(--k-line);background:var(--k-surface);font-size:13px;white-space:nowrap}
    .cx5-shift-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.22)}
    .cx5-shift.is-break .cx5-shift-dot{background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,.25)}
    .cx5-shift-time{color:var(--k-muted)}
    .cx5-shift-time b{color:var(--k-ink);font-weight:700;font-variant-numeric:tabular-nums}
    .cx5-mini{min-height:30px;padding:0 12px;border-radius:999px;border:1px solid var(--k-line);background:transparent;color:var(--k-ink);font:inherit;font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap}
    .cx5-mini.is-danger{color:#fca5a5;border-color:rgba(220,38,38,.4)}
    .cx5-mini:disabled{opacity:.5}
    .cx5-actions{display:flex;align-items:center;gap:8px}
    .cx5-btn{min-height:44px;padding:0 16px;border-radius:12px;border:1px solid var(--k-line);background:var(--k-surface);color:var(--k-ink);font:inherit;font-size:14px;font-weight:700;cursor:pointer;white-space:nowrap}
    .cx5-btn:disabled{opacity:.55;cursor:not-allowed}
    .cx5-btn-primary{border-color:transparent;background:var(--k-primary);color:var(--k-on-primary);box-shadow:0 6px 18px rgba(var(--k-primary-rgb),.28)}
    .cx5-btn-z{border:1.5px solid var(--k-primary-ink);color:var(--k-primary-ink)}
    .cx5-icon{width:44px;height:44px;flex:0 0 auto;display:grid;place-items:center;border-radius:12px;border:1px solid var(--k-line);background:var(--k-surface);color:var(--k-ink);font:inherit;font-size:20px;cursor:pointer}
    .cx5-more{position:relative}
    .cx5-menu{position:absolute;right:0;top:calc(100% + 6px);z-index:30;min-width:280px;display:grid;padding:6px;border-radius:14px;background:var(--k-surface);border:1px solid var(--k-line);box-shadow:0 18px 40px rgba(0,0,0,.25)}
    .cx5-menu button{padding:12px;border-radius:10px;border:0;background:none;color:var(--k-ink);font:inherit;font-weight:600;text-align:left;cursor:pointer}
    .cx5-menu button:hover{background:rgba(var(--k-ink-rgb),.06)}
    .cx5-kpis{display:grid;grid-template-columns:minmax(0,1.3fr) repeat(4,minmax(0,1fr)) minmax(270px,1.7fr);gap:12px;padding:16px 20px 0}
    .cx5-kpi{display:grid;align-content:start;gap:4px;min-width:0;padding:14px 16px;border-radius:16px;background:var(--k-surface);border:1px solid var(--k-line)}
    .cx5-kpi>span{font-size:12px;font-weight:600;color:var(--k-muted)}
    .cx5-kpi strong{font-size:24px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .cx5-kpi small{font-size:12px;color:var(--k-muted)}
    .cx5-kpi-main{border-color:transparent;background:var(--k-primary);color:var(--k-on-primary);box-shadow:inset 0 -5px 0 var(--k-secondary)}
    .cx5-kpi-main>span,.cx5-kpi-main small{color:inherit;opacity:.85}
    .cx5-kpi-main strong{font-size:28px}
    .cx5-kpi-pay{gap:7px}
    .cx5-pay-row{display:grid;grid-template-columns:minmax(118px,auto) minmax(40px,1fr) auto;align-items:center;gap:10px;font-size:13px}
    .cx5-pay-row em{font-style:normal;font-weight:600;white-space:nowrap}
    .cx5-pay-row em small{color:var(--k-muted);font-weight:500}
    .cx5-pay-row i{position:relative;height:6px;border-radius:99px;overflow:hidden;background:rgba(var(--k-ink-rgb),.1)}
    .cx5-pay-row i::after{content:"";position:absolute;left:0;top:0;bottom:0;width:var(--w,0%);border-radius:inherit;background:var(--k-primary)}
    .cx5-pay-row b{font-variant-numeric:tabular-nums}
    .cx5-kpi-note{margin:6px 20px 0;font-size:12px;color:var(--k-muted)}
    .cx5-toast{margin:12px 20px 0;padding:10px 14px;border-radius:12px;background:rgba(22,163,74,.16);color:#bbf7d0;font-weight:700}
    .cx5-last{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:10px 20px 0;padding:8px 8px 8px 14px;border-radius:12px;background:var(--k-surface);border:1px solid var(--k-line);font-size:13px}
    .cx5-board{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(340px,1fr);gap:16px;align-items:start;padding:16px 20px}
    .cx5-board.is-single{grid-template-columns:minmax(0,1fr)}
    .cx5-board.is-idle{flex:1 0 auto;display:flex;flex-direction:column;align-items:stretch}
    .cx5-board.is-idle>.cx5-idle{flex:1 0 240px}
    .cx5-idle-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
    .cx5-idle{display:grid;place-content:center;justify-items:center;gap:8px;padding:32px 20px;text-align:center;border-radius:24px;border:1.5px dashed var(--k-line);background:rgba(var(--k-ink-rgb),.02)}
    .cx5-idle-icon{width:64px;height:64px;display:grid;place-items:center;border-radius:50%;background:rgba(var(--k-primary-rgb),.14);color:var(--k-primary);font-size:30px;font-weight:800}
    .cx5-idle strong{font-size:22px;font-weight:800}
    .cx5-idle p{margin:0;max-width:420px;color:var(--k-muted);font-size:15px}
    .cx5-idle-actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:8px}
    .cx5-side{display:grid;gap:16px;min-width:0}
    .cx5-sec{min-width:0;padding:14px;border-radius:20px;background:var(--k-surface2);border:1px solid var(--k-line)}
    .cx5-sec.is-empty{padding:9px 14px}
    .cx5-sec-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
    .cx5-sec.is-empty .cx5-sec-head{margin:0}
    .cx5-sec-head h2{margin:0;font-size:17px;font-weight:800}
    .cx5-sec-icon{width:34px;height:34px;display:grid;place-items:center;border-radius:10px;background:rgba(var(--k-primary-rgb),.16);font-size:18px}
    .cx5-sec.is-empty .cx5-sec-icon{width:28px;height:28px;font-size:15px}
    .cx5-count{min-width:28px;height:24px;padding:0 8px;display:inline-grid;place-items:center;border-radius:999px;background:var(--k-primary);color:var(--k-on-primary);font-size:13px;font-weight:800}
    .cx5-sec.is-empty .cx5-count{background:rgba(var(--k-ink-rgb),.1);color:var(--k-muted)}
    .cx5-sec-empty{margin-left:2px;font-size:13px;color:var(--k-muted)}
    .cx5-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(188px,1fr));gap:12px}
    .cx5-side .cx5-grid-dl{grid-template-columns:minmax(0,1fr)}
    .cx5-card{position:relative;display:grid;gap:8px;min-width:0;padding:14px 14px 12px 18px;border-radius:16px;border:1px solid var(--k-line);background:var(--k-surface);color:var(--k-ink);font:inherit;text-align:left;cursor:pointer;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.06);transition:transform .12s ease,box-shadow .12s ease}
    .cx5-card::before,.cx5-row::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--st,transparent)}
    .cx5-card:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(0,0,0,.14)}
    .cx5-st-preparing{--st:#d97706}.cx5-st-ready{--st:#16a34a}
    .cx5-delivery{--st:#0ea5e9}.cx5-dl-kitchen{--st:#d97706}.cx5-dl-ready{--st:#16a34a}
    .cx5-card-row{display:flex;justify-content:space-between;align-items:center;gap:8px}
    .cx5-cap{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--k-muted)}
    .cx5-timer{padding:3px 8px;border-radius:999px;background:rgba(var(--k-ink-rgb),.07);font-size:12px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
    .cx5-timer.is-slow{background:rgba(217,119,6,.2);color:#fde68a}
    .cx5-timer.is-late{background:rgba(220,38,38,.2);color:#fca5a5}
    .cx5-num{font-size:40px;line-height:1;font-weight:800;letter-spacing:-.03em}
    .cx5-pill{justify-self:start;padding:4px 10px;border-radius:999px;background:rgba(var(--k-ink-rgb),.08);font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;white-space:nowrap}
    .cx5-st-preparing .cx5-pill,.cx5-pill.cx5-st-preparing,.cx5-dl-kitchen .cx5-pill{background:rgba(217,119,6,.2);color:#fde68a}
    .cx5-st-ready .cx5-pill,.cx5-pill.cx5-st-ready,.cx5-dl-ready .cx5-pill,.cx5-pill.is-paid{background:rgba(22,163,74,.18);color:#86efac}
    .cx5-dl-assigned .cx5-pill,.cx5-dl-sent .cx5-pill{background:rgba(14,165,233,.18);color:#7dd3fc}
    .cx5-card-foot{display:flex;justify-content:space-between;align-items:baseline;gap:8px;min-width:0}
    .cx5-who{min-width:0;overflow:hidden;font-size:13px;color:var(--k-muted);white-space:nowrap;text-overflow:ellipsis}
    .cx5-card-foot strong{font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}
    .cx5-dl-who b{font-size:16px}
    .cx5-dl-addr{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:13px;color:var(--k-muted)}
    .cx5-dl-badges{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
    .cx5-rows{display:grid;gap:8px}
    .cx5-row{position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:10px;padding:10px 12px 10px 16px;border-radius:12px;border:1px solid var(--k-line);background:var(--k-surface);color:var(--k-ink);font:inherit;text-align:left;cursor:pointer;overflow:hidden}
    .cx5-row.is-paid{grid-template-columns:minmax(0,1fr) auto auto auto;--st:#16a34a;cursor:default}
    .cx5-row-main{display:grid;min-width:0}
    .cx5-row-main b{font-weight:700}
    .cx5-row-main small{overflow:hidden;font-size:12px;color:var(--k-muted);white-space:nowrap;text-overflow:ellipsis}
    .cx5-row strong{font-variant-numeric:tabular-nums}
    .cx5-print{width:36px;height:36px;font-size:16px}
    .cx5-detail{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:16px;align-items:start;padding:16px 20px}
    .cx5-panel{min-width:0;padding:16px;border-radius:18px;background:var(--k-surface);border:1px solid var(--k-line)}
    .cx5-charge{position:sticky;top:84px;display:grid;gap:12px}
    .cx5-total{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
    .cx5-total span{font-size:13px;font-weight:600;color:var(--k-muted)}
    .cx5-total strong{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums}
    .cx5-charge-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .cx5-step{display:flex;align-items:center;gap:8px;margin-top:4px;font-size:13px;font-weight:700;color:var(--k-muted)}
    .cx5-step span{flex:0 0 auto;width:22px;height:22px;display:grid;place-items:center;border-radius:50%;background:var(--k-primary);color:var(--k-on-primary);font-size:12px}
    .cx5-methods{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
    .cx5-method{display:grid;justify-items:center;gap:4px;min-height:80px;padding:10px 6px;border-radius:14px;border:1.5px solid var(--k-line);background:var(--k-surface2);color:var(--k-ink);font:inherit;font-size:14px;font-weight:700;cursor:pointer}
    .cx5-method i{font-style:normal;font-size:26px}
    .cx5-method:hover{border-color:var(--k-primary)}
    .cx5-method:disabled{opacity:.5}
    .cx5-hint{margin:0;font-size:13px;line-height:1.45;color:var(--k-muted)}
    .cx5-hint small{font-size:12px}
    .cx5-empty{padding:14px;color:var(--k-muted);grid-column:1/-1}
    .cx5-dest{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:var(--k-muted)}
    .cx5-dest select{min-height:42px;padding:0 12px;border-radius:12px;border:1px solid var(--k-line);background:var(--k-field);color:var(--k-ink);font:inherit;font-size:14px}
    .cx5-sale{display:grid;grid-template-columns:minmax(0,1fr) 400px;min-height:calc(100vh - 66px)}
    .cx5-sale-main{min-width:0;padding:16px 20px 28px}
    .cx5-search{display:flex;align-items:center;gap:8px;max-width:520px;margin-bottom:14px;padding:0 14px;border-radius:14px;border:1px solid var(--k-line);background:var(--k-field)}
    .cx5-search input{flex:1;min-width:0;min-height:46px;border:0;outline:0;background:transparent;color:var(--k-ink);font:inherit;font-size:15px}
    .cx5-cats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}
    .cx5-cats>.cx5-cat{max-width:320px}
    .cx5-cat{display:grid;gap:4px;min-width:0;padding:0 0 12px;border-radius:18px;border:1px solid var(--k-line);background:var(--k-surface);color:var(--k-ink);font:inherit;text-align:center;cursor:pointer;overflow:hidden;transition:border-color .12s ease,box-shadow .12s ease}
    .cx5-cat:hover,.cx5-prod:hover{border-color:var(--k-primary)}
    .cx5-cat.is-active{border-color:var(--k-primary);box-shadow:0 0 0 3px rgba(var(--k-primary-rgb),.3)}
    .cx5-art{position:relative;display:grid;place-items:center;aspect-ratio:4/3;overflow:hidden;background:var(--k-surface2)}
    .cx5-art::before{content:"";position:absolute;inset:-18px;background:var(--img) center/cover no-repeat;filter:blur(18px);opacity:.5}
    .cx5-art img{position:absolute;inset:0;display:block;width:100%;height:100%;object-fit:contain}
    .cx5-art.is-emoji{font-size:54px;line-height:1}
    .cx5-art.is-emoji::before{display:none}
    .cx5-cat-name{padding:0 8px;font-size:15px;font-weight:700}
    .cx5-cat small{font-size:12px;color:var(--k-muted)}
    .cx5-cats.is-compact{display:flex;gap:10px;overflow-x:auto;padding:2px 2px 8px;scroll-snap-type:x proximity}
    .cx5-cats.is-compact .cx5-cat{flex:0 0 118px;padding-bottom:8px;scroll-snap-align:start}
    .cx5-cats.is-compact .cx5-cat-name{font-size:13px}
    .cx5-cats.is-compact .cx5-cat small{display:none}
    .cx5-cats.is-compact .cx5-art.is-emoji{font-size:34px}
    .cx5-products{margin-top:14px}
    .cx5-pick{padding:18px 0;color:var(--k-muted)}
    .cx5-sub{margin:16px 0 8px;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--k-muted)}
    .cx5-prods{display:grid;grid-template-columns:repeat(auto-fill,minmax(172px,1fr));gap:10px}
    .cx5-prod{display:grid;align-content:space-between;gap:8px;min-width:0;min-height:108px;padding:12px;border-radius:14px;border:1px solid var(--k-line);background:var(--k-surface);color:var(--k-ink);font:inherit;text-align:left;cursor:pointer}
    .cx5-prod:active{transform:scale(.98)}
    .cx5-prod-art{position:relative;display:grid;place-items:center;aspect-ratio:16/10;overflow:hidden;border-radius:10px;background:var(--k-surface2)}
    .cx5-prod-art img{position:absolute;inset:0;display:block;width:100%;height:100%;object-fit:contain}
    .cx5-prod-art.is-emoji{justify-items:start;aspect-ratio:auto;background:none;font-size:30px;line-height:1}
    .cx5-prod-name{font-size:14px;font-weight:600;line-height:1.25}
    .cx5-prod-foot{display:flex;justify-content:space-between;align-items:center;gap:6px}
    .cx5-prod-foot strong{font-weight:800;font-variant-numeric:tabular-nums}
    .cx5-tag{padding:2px 7px;border-radius:999px;font-size:11px;font-style:normal;font-weight:700;white-space:nowrap}
    .cx5-tag.is-kitchen{background:rgba(217,119,6,.18);color:#fde68a}
    .cx5-tag.is-ready{background:rgba(14,165,233,.16);color:#7dd3fc}
    .cx5-cart{position:sticky;top:66px;align-self:start;display:flex;flex-direction:column;gap:10px;height:calc(100vh - 66px);padding:16px 18px;overflow:auto;border-left:1px solid var(--k-line);background:var(--k-surface)}
    .cx5-cart-head{display:flex;align-items:center;gap:8px}
    .cx5-cart-head strong{margin-right:auto;font-size:16px;font-weight:800}
    .cx5-cart-dest{font-size:13px;color:var(--k-muted)}
    .cx5-lines{display:grid}
    .cx5-line{display:grid;grid-template-columns:minmax(0,1fr) auto auto auto;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--k-line)}
    .cx5-line-main{display:grid;gap:2px;padding:0;border:0;background:none;color:var(--k-ink);font:inherit;text-align:left;cursor:pointer}
    .cx5-line-main b{font-size:14px;font-weight:600}
    .cx5-line-main small{font-size:11px;color:var(--k-muted)}
    .cx5-stepper{display:inline-flex;align-items:center;gap:4px;padding:2px;border-radius:999px;border:1px solid var(--k-line)}
    .cx5-stepper button{width:30px;height:30px;border-radius:50%;border:0;background:rgba(var(--k-ink-rgb),.08);color:var(--k-ink);font-size:16px;cursor:pointer}
    .cx5-stepper b{min-width:18px;font-size:13px;text-align:center}
    .cx5-line strong{font-size:14px;font-variant-numeric:tabular-nums}
    .cx5-x{width:28px;height:28px;border-radius:8px;border:0;background:none;color:var(--k-muted);cursor:pointer}
    .cx5-cart-empty{display:grid;justify-items:center;gap:8px;padding:34px 10px;text-align:center;color:var(--k-muted)}
    .cx5-cart-empty span{font-size:34px}
    .cx5-cart-total{display:flex;justify-content:space-between;align-items:baseline;padding:8px 0}
    .cx5-cart-total span{font-weight:700;color:var(--k-muted)}
    .cx5-cart-total strong{font-size:28px;font-weight:800;font-variant-numeric:tabular-nums}
    .cx5-route{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .cx5-route button{min-height:52px;padding:0 8px;border-radius:12px;border:1.5px solid var(--k-line);background:var(--k-surface2);color:var(--k-ink);font:inherit;font-weight:700;cursor:pointer}
    .cx5-route button.is-on{border-color:var(--k-primary);background:rgba(var(--k-primary-rgb),.14);box-shadow:inset 0 0 0 1px var(--k-primary)}
    .cx5-send{width:100%;min-height:56px;font-size:16px}
    .cx5-modal{position:fixed;inset:0;z-index:70;display:grid;place-items:center;padding:16px;overflow:auto;background:rgba(0,0,0,.5)}
    .cx5-modal-card{width:min(620px,100%);display:grid;gap:14px;padding:22px;border-radius:22px;border:1px solid var(--k-line);background:var(--k-surface);color:var(--k-ink);box-shadow:0 30px 80px rgba(0,0,0,.35)}
    .cx5-modal-card h2{margin:0;font-size:20px}
    .cx5-z-total{display:grid;gap:2px;padding:16px;border-radius:16px;background:var(--k-primary);box-shadow:inset 0 -5px 0 var(--k-secondary);color:var(--k-on-primary)}
    .cx5-z-total span{font-size:13px;opacity:.85}
    .cx5-z-total strong{font-size:34px;font-weight:800;font-variant-numeric:tabular-nums}
    .cx5-z-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
    .cx5-z-stats div{display:grid;padding:10px 12px;border-radius:12px;background:var(--k-surface2)}
    .cx5-z-stats span{font-size:12px;color:var(--k-muted)}
    .cx5-z-stats b{font-size:20px;font-variant-numeric:tabular-nums}
    .cx5-z-methods{display:grid;gap:8px}
    .cx5-z-channels{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;color:var(--k-muted)}
    .cx5-z-warn{margin:0;padding:10px 12px;border-radius:12px;background:rgba(217,119,6,.16);color:#fde68a;font-size:13px;font-weight:600}
    .cx5-z-done{padding:10px 12px;border-radius:12px;background:rgba(22,163,74,.16);color:#86efac;font-weight:700}
    .cx5-z-history{display:grid;gap:6px;font-size:13px}
    .cx5-z-history>span{font-weight:700;color:var(--k-muted)}
    .cx5-z-history div{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:10px}
    .cx5-z-history small{color:var(--k-muted)}
    .cx5-z-history em{font-style:normal;font-weight:700}
    .cx5-z-history .cx5-icon{width:34px;height:34px;font-size:15px}
    .cx5-modal-actions{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:8px}
    #app[data-cx5] .csh-detail-lines td,#app[data-cx5] .csh-detail-lines th{padding:9px 4px}
    @media (max-width:1280px){
      .cx5-kpis{grid-template-columns:minmax(0,1.3fr) repeat(4,minmax(0,1fr))}
      .cx5-kpi-pay{grid-column:1/-1;display:grid;grid-template-columns:auto repeat(3,minmax(0,1fr));align-items:center;gap:8px 18px}
    }
    @media (max-width:1100px){
      .cx5-board{grid-template-columns:minmax(0,1fr)}
      .cx5-side{grid-template-columns:repeat(auto-fit,minmax(320px,1fr));align-items:start}
      .cx5-shift{order:3;width:100%}
    }
    @media (max-width:900px){
      .cx5-detail{grid-template-columns:minmax(0,1fr)}
      .cx5-charge{position:static}
      .cx5-sale{grid-template-columns:minmax(0,1fr)}
      .cx5-cart{position:sticky;top:auto;bottom:0;height:auto;max-height:60vh;border-left:0;border-top:1px solid var(--k-line);border-radius:20px 20px 0 0;box-shadow:0 -12px 30px rgba(0,0,0,.18)}
      .cx5-cart-empty{padding:6px 10px;grid-auto-flow:column;justify-content:center}
      .cx5-cart-empty span{font-size:20px}
    }
    @media (max-width:760px){
      .cx5-top{padding:10px 14px}
      .cx5-kpis{grid-template-columns:repeat(2,minmax(0,1fr));padding:12px 14px 0}
      .cx5-kpi-main{grid-column:1/-1}
      .cx5-kpi-pay{grid-template-columns:minmax(0,1fr)}
      .cx5-board,.cx5-detail,.cx5-sale-main{padding-left:14px;padding-right:14px}
      .cx5-side{grid-template-columns:minmax(0,1fr)}
      .cx5-shift{flex-wrap:wrap;border-radius:14px}
      .cx5-actions{width:100%}
      .cx5-actions .cx5-btn{flex:1}
    }
  `;
  document.head.appendChild(style);
  if (Kit) Kit.injectStyles();
  if (Alerts) Alerts.install();

  window.addEventListener("popstate", (event) => {
    try {
      onPopState(event);
    } catch (error) {
      try { console.error("[caja] popstate", error); } catch (_) {}
    }
  });
  window.addEventListener("online", () => { tryReconnect(); });
  window.addEventListener("offline", () => { markOffline("network"); });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && token()) {
      refreshToken();
      refreshTables();
    }
  });
  window.addEventListener("error", (event) => {
    try { console.error("[caja] error", event.error || event.message); } catch (_) {}
  });
  window.addEventListener("unhandledrejection", (event) => {
    try { console.error("[caja] promesa", event.reason); } catch (_) {}
    if (event && typeof event.preventDefault === "function") event.preventDefault();
  });

  window.setInterval(() => {
    try { tickShiftClock(); } catch (_) {}
  }, 1000);
  window.setInterval(() => {
    if (state.screen !== "login" && token()) loadOperational();
  }, 60000);

  if (!companyId) {
    root.innerHTML = `<section style="min-height:100vh;display:grid;place-items:center;background:#080712;color:#fff"><p>Falta company_id en el enlace.</p></section>`;
  } else if (token()) {
    state.stack = ["tables"];
    state.screen = "tables";
    installHistory();
    startPolling();
    startSessionKeeper();
    loadMenu();
    loadCashierConfig();
    loadOperational();
    safeRender();
  } else {
    safeRender();
  }
})();
