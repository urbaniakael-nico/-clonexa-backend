(() => {
  "use strict";

  const root = document.getElementById("app");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const PANEL_TYPE = "mesero";
  const storageKey = `clonexa_waiter_token_${companyId}`;
  const cartKey = `clonexa_waiter_cart_${companyId}`;
  const profileKey = `clonexa_waiter_profile_${companyId}`;
  const navKey = `clonexa_waiter_nav_${companyId}`;
  const deviceKey = "clonexa_mini_panel_device_id";
  const TOKEN_REFRESH_MS = 25 * 60 * 1000;
  const RECONNECT_MS = 5000;
  // Shared menu pieces (grids, product sheet, cart math): hsp_menu_kit.js,
  // loaded before this file. The caja panel uses the very same kit.
  const Kit = window.CxMenuKit;
  const { h, money, tableTitle, orderItemPayload } = Kit;
  // Sound + vibration + on-screen card until closed (hsp_alerts.js).
  const Alerts = window.CxAlerts ? window.CxAlerts.create("mesero") : null;
  const shownAvisos = new Map();   // order_id -> alert card on screen

  const state = {
    screen: "login",
    stack: ["home"],
    error: "",
    busy: false,
    session: null,
    companyName: "",
    mesero: "",
    tables: [],
    table: "",
    menu: [],
    category: null,
    cart: [],
    sending: false,
    sendError: "",
    lastOrderOk: "",
    shiftExpanded: false,
    operational: null,
    ventasHoy: null,
    misMesas: [],
    // Cantidad por botones: empty unless the company turned it on (the
    // server sends [] otherwise), so the old number field stays as is.
    quantityButtons: [],
    avisos: [],
    avisosEnabled: true,
    menuEmojis: false,
    offline: false,
    offlineReason: "",
  };

  const AVISOS_POLL_MS = 8000;

  function formatHMS(totalSeconds) {
    const seconds = Math.max(0, Number(totalSeconds || 0));
    const h2 = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h2 > 0) return `${h2}h ${String(m).padStart(2, "0")}m`;
    return `${m}m`;
  }

  // ---------------------------------------------------------------------
  // Storage. The session lives in localStorage, NOT sessionStorage: a phone
  // browser that unloads the tab in the background (a call, the screen
  // locking) or the mesero reopening the link in a new tab used to come
  // back with no token -> login again -> the single-device rule kicked his
  // own open panel. Every access is wrapped: private modes can throw.
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
    // One-time move of a token saved by the previous version of this panel.
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

  function persistProfile() {
    storeSet("localStorage", profileKey, JSON.stringify({ companyName: state.companyName, mesero: state.mesero, username: state.username || "" }));
  }

  function restoreProfile() {
    const data = storeJson("localStorage", profileKey) || {};
    state.companyName = data.companyName || state.companyName;
    state.mesero = data.mesero || state.mesero;
    state.username = data.username || state.username || "";
  }

  // ---------------------------------------------------------------------
  // Cart resilience: mirrored to localStorage on every change so a failed
  // send, a reload, a killed tab or a dropped WiFi never loses what the
  // mesero already built. Tagged with its owner so another mesero logging
  // in on the same phone doesn't inherit it.
  // ---------------------------------------------------------------------
  function persistCart() {
    storeSet("localStorage", cartKey, JSON.stringify({ table: state.table, cart: state.cart, owner: state.username || "" }));
  }

  function restoreCart(expectedOwner) {
    const data = storeJson("localStorage", cartKey) || storeJson("sessionStorage", cartKey);
    if (!data || !Array.isArray(data.cart) || !data.cart.length) return;
    if (expectedOwner && data.owner && data.owner !== expectedOwner) {
      clearPersistedCart();
      return;
    }
    state.table = data.table || "";
    state.cart = data.cart;
  }

  function clearPersistedCart() {
    storeSet("localStorage", cartKey, "");
    storeSet("sessionStorage", cartKey, "");
  }

  // Navigation stack per tab (sessionStorage, like the browser history it
  // mirrors), so a reload lands back on the same screen.
  function persistNav() {
    storeSet("sessionStorage", navKey, JSON.stringify({ stack: state.stack, category: state.category, table: state.table }));
  }

  function restoreNav() {
    const data = storeJson("sessionStorage", navKey);
    if (!data || !Array.isArray(data.stack) || !data.stack.length || data.stack[0] !== "home") return null;
    return data;
  }

  // ---------------------------------------------------------------------
  // Connection: a dropped WiFi (or leaving the restaurant's network) shows
  // a "sin conexión" bar and retries by itself -- it never logs the mesero
  // out and never touches the cart.
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
    if (!state.menu.length) loadMenu().then(safeRender);
    refreshHomeWidgets();
  }

  async function tryReconnect() {
    if (!token()) return;
    try {
      await loadOperationalStrict();
    } catch (_) {
      // still offline: the interval keeps trying
    }
  }

  function connectionMessage(reason) {
    if (reason === "wifi") return "Sin conexión al WiFi del restaurante. Reintentando… Tu pedido está guardado.";
    return "Sin conexión. Reintentando… Tu pedido está guardado.";
  }

  function renderConnection() {
    const current = document.getElementById("wtrNet");
    if (current) current.remove();
    if (!state.offline || state.screen === "login") return;
    const bar = document.createElement("div");
    bar.id = "wtrNet";
    bar.className = "wtr-net";
    bar.setAttribute("role", "status");
    bar.textContent = connectionMessage(state.offlineReason);
    document.body.appendChild(bar);
  }

  // Any 401 on an authenticated call means the session is really gone
  // (kicked by a login on another device, closed from Admin V2, expired):
  // back to login, keeping the cart so nothing typed is lost.
  function sessionLostMessage(message) {
    if (/otro dispositivo/i.test(String(message))) return "Tu sesión se abrió en otro dispositivo.";
    return "Tu sesión terminó. Vuelve a entrar: tu pedido sigue guardado.";
  }

  function handleSessionLost(message) {
    setToken("");
    stopSessionKeeper();
    state.session = null;
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
      // Network down (WiFi dropped, airplane mode...): not a session problem.
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
      } else if (response.status >= 500 || response.status === 0) {
        markOffline("network");
      } else {
        markOnline();
      }
      throw new Error(message);
    }
    markOnline();
    return data;
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
  // Nav stack: home is the root; every other screen pushes on top of it so
  // "back" always lands somewhere sensible regardless of how a screen was
  // reached (Tomar pedido -> mesa -> categorias, or Mis mesas -> categorias
  // directly).
  //
  // Every step is also a browser history entry, so the phone's own back
  // button walks producto -> categoria -> mesa -> inicio instead of leaving
  // the app. Entries: [base] [home, depth 0] [depth 1] ... Backing onto
  // "base" means "leave from the home screen": allowed, but it asks first
  // when there is an unsent cart.
  // ---------------------------------------------------------------------
  let historyReady = false;
  let ignorePops = 0;

  function historyPush(depth) {
    try {
      window.history.pushState({ wtrDepth: depth }, "");
    } catch (_) {}
  }

  function installHistory() {
    try {
      const current = window.history.state;
      if (current && typeof current.wtrDepth === "number") {
        // A reload in the middle of the flow: the tab kept its history
        // entries, bring back the stack that matches them.
        const nav = restoreNav();
        if (nav && nav.stack.length === current.wtrDepth + 1) {
          state.stack = nav.stack;
          state.screen = nav.stack[nav.stack.length - 1];
          state.category = nav.category || state.category;
          if (nav.table) state.table = nav.table;
        } else if (current.wtrDepth > 0) {
          ignorePops += 1;
          window.history.go(-current.wtrDepth);
        }
      } else {
        if (!current || !current.wtrBase) window.history.replaceState({ wtrBase: true }, "");
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
      // Still on the base entry (confirmed "salir" but the tab had no page
      // to go back to): put the home entry back first, so the flow stacks
      // on top of it and back keeps returning to inicio.
      const current = window.history.state;
      if (current && current.wtrBase) historyPush(0);
      historyPush(state.stack.length - 1);
    }
    render();
  }

  function back() {
    if (historyReady) {
      window.history.back();
      return;
    }
    if (state.stack.length > 1) state.stack.pop();
    state.screen = state.stack[state.stack.length - 1];
    persistNav();
    render();
  }

  function resetToHome() {
    const steps = state.stack.length - 1;
    state.stack = ["home"];
    state.screen = "home";
    persistNav();
    if (historyReady && steps > 0) {
      ignorePops += 1;
      window.history.go(-steps);
    }
    render();
  }

  function closeOpenSheets() {
    const sheets = document.querySelectorAll(".wtr-sheet-backdrop");
    sheets.forEach((sheet) => sheet.remove());
    return sheets.length > 0;
  }

  function confirmLeave() {
    if (!state.cart.length) return true;
    return window.confirm(`Tienes un pedido sin enviar (${state.cart.length} producto${state.cart.length === 1 ? "" : "s"}). ¿Salir de todas formas? Quedará guardado.`);
  }

  // Pure decision for a popstate, so it can be tested without a browser.
  function popAction(historyState, stackLength, screen, sheetOpen) {
    if (screen === "login") return { type: "ignore" };
    if (sheetOpen) return { type: "close_sheet", depth: stackLength - 1 };
    if (historyState && typeof historyState.wtrDepth === "number") {
      return { type: "go", depth: Math.max(0, Math.min(historyState.wtrDepth, stackLength - 1)) };
    }
    return { type: "leave" };
  }

  function onPopState(event) {
    if (ignorePops > 0) {
      ignorePops -= 1;
      return;
    }
    const sheetOpen = document.querySelectorAll(".wtr-sheet-backdrop").length > 0;
    const action = popAction(event.state, state.stack.length, state.screen, sheetOpen);
    if (action.type === "close_sheet") {
      // Back with a sheet open only closes the sheet.
      closeOpenSheets();
      historyPush(action.depth);
      return;
    }
    if (action.type === "go") {
      state.stack = state.stack.slice(0, action.depth + 1);
      state.screen = state.stack[action.depth];
      persistNav();
      safeRender();
      return;
    }
    if (action.type === "leave") {
      if (confirmLeave()) {
        window.history.back();
      } else {
        historyPush(0);
      }
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
      state.session = data;
      state.companyName = (data.company && data.company.name) || "CLONEXA";
      state.mesero = (data.user && data.user.full_name) || "Mesero";
      state.username = String(username || "").trim().toLowerCase();
      persistProfile();
      restoreCart(state.username);
      state.stack = ["home"];
      state.screen = "home";
      installHistory();
      await enterHome();
      startHomeRefresh();
      startSessionKeeper();
    } catch (error) {
      state.error = error.message || "No se pudo iniciar sesión.";
    } finally {
      state.busy = false;
      render();
    }
  }

  async function enterHome() {
    await Promise.all([loadTables(), loadMenu(), loadOperational(), loadVentasHoy(), loadMisMesas()]);
  }

  // ---------------------------------------------------------------------
  // Session keeper: renews the token every 25 min and whenever the phone
  // comes back to the panel, as long as the mesero's shift is open (the
  // server refuses to renew a closed shift or a kicked session).
  // ---------------------------------------------------------------------
  let sessionKeeperHandle = null;

  async function refreshToken() {
    const sent = token();
    if (!sent) return;
    try {
      const data = await mpApi(`/mini-panel-refresh?panel_type=${PANEL_TYPE}`, { method: "POST" });
      // Only if nothing changed meanwhile: a renewal answering after a 401
      // or a logout must never bring the closed session back.
      if (data && data.access_token && token() === sent) setToken(data.access_token);
    } catch (_) {
      // 409 turno_cerrado / offline: keep the current token; a real 401
      // was already handled by api().
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

  function onVisible() {
    if (document.visibilityState !== "visible" || !token()) return;
    refreshToken();
    loadAvisos();
    refreshHomeWidgets();
  }

  async function loadTables() {
    try {
      const data = await hspApi("/qr-tables?count=30&include_bar=false");
      state.tables = Array.isArray(data.tables) ? data.tables : [];
    } catch (_) {
      state.tables = [];
    }
  }

  async function loadMenu() {
    try {
      const data = await waiterApi("/menu");
      state.menu = Array.isArray(data.categories) ? data.categories : [];
      state.quantityButtons = Array.isArray(data.quantity_buttons) ? data.quantity_buttons : [];
      state.menuEmojis = data.menu_emojis === true;
    } catch (error) {
      state.error = error.message || "No se pudo cargar el menú.";
    }
  }

  async function loadOperationalStrict() {
    const data = await mpApi(`/mini-panel-operational-session?panel_type=${PANEL_TYPE}`);
    state.operational = data.operational_session || null;
  }

  async function loadOperational() {
    try {
      const data = await mpApi(`/mini-panel-operational-session?panel_type=${PANEL_TYPE}`);
      state.operational = data.operational_session || null;
    } catch (_) {
      state.operational = null;
    }
  }

  async function loadVentasHoy() {
    try {
      state.ventasHoy = await waiterApi("/mesero/ventas-hoy");
    } catch (_) {
      state.ventasHoy = null;
    }
  }

  async function loadMisMesas() {
    try {
      const data = await waiterApi("/mesero/mis-mesas");
      state.misMesas = Array.isArray(data.tables) ? data.tables : [];
    } catch (_) {
      state.misMesas = [];
    }
  }

  // "Mesa X lista para llevar": only this mesero's own orders, shown on any
  // screen until he taps OK. The server answers enabled=false for a company
  // without the kitchen columns switch, and polling stops for good.
  async function loadAvisos() {
    if (!state.avisosEnabled || !token()) return;
    try {
      const data = await waiterApi("/mesero/avisos");
      if (data.enabled === false) {
        state.avisosEnabled = false;
        return;
      }
      state.avisos = Array.isArray(data.avisos) ? data.avisos : [];
      renderAvisos();
    } catch (_) {
      // transient: keep the last notices on screen
    }
  }

  async function dismissAviso(orderId) {
    state.avisos = state.avisos.filter((a) => a.order_id !== orderId);
    renderAvisos();
    try {
      await waiterApi(`/mesero/avisos/${encodeURIComponent(orderId)}/visto`, { method: "POST" });
    } catch (_) {
      // it will simply show up again on the next poll
    }
  }

  // "Mesa X lista para llevar": each new notice sounds, vibrates and stays
  // on screen until the mesero closes it (closing = seen on the server). A
  // notice dismissed elsewhere (another poll, logout) leaves the screen.
  function renderAvisos() {
    if (!Alerts) return;
    const current = new Set(state.screen === "login" ? [] : state.avisos.map((a) => a.order_id));
    shownAvisos.forEach((card, orderId) => {
      if (!current.has(orderId)) {
        card.remove();
        shownAvisos.delete(orderId);
      }
    });
    if (state.screen === "login") return;
    state.avisos.forEach((aviso) => {
      if (shownAvisos.has(aviso.order_id)) return;
      const card = Alerts.notify({
        kind: "ready",
        title: aviso.message,
        message: "Recógela en cocina y llévala a la mesa.",
        onClose: () => dismissAviso(aviso.order_id),
      });
      shownAvisos.set(aviso.order_id, card);
    });
  }

  async function refreshHomeWidgets() {
    await Promise.all([loadOperational(), loadVentasHoy(), loadMisMesas()]);
    if (state.screen === "home") render();
  }

  async function shiftAction(action) {
    try {
      const data = await mpApi(`/mini-panel-operational-session/${action}?panel_type=${PANEL_TYPE}`, { method: "POST" });
      state.operational = data.operational_session || null;
      render();
    } catch (error) {
      state.error = error.message || "No se pudo actualizar el turno.";
      render();
    }
  }

  async function changePassword(currentPassword, newPassword, confirmPassword) {
    return mpApi(`/mini-panel-change-password?panel_type=${PANEL_TYPE}`, {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword }),
    });
  }

  function cartTotal() {
    return Kit.cartTotal(state.cart);
  }

  function addOrUpdateCartLine(line, editIndex) {
    if (editIndex === null || editIndex === undefined) state.cart.push(line);
    else state.cart[editIndex] = line;
    persistCart();
  }

  function removeCartLine(index) {
    state.cart.splice(index, 1);
    persistCart();
  }

  async function submitOrder() {
    if (!state.table || !state.cart.length) return;
    state.sending = true;
    state.sendError = "";
    render();
    try {
      await waiterApi("/orders", {
        method: "POST",
        body: JSON.stringify({
          table: state.table,
          items: state.cart.map(orderItemPayload),
        }),
      });
      state.lastOrderOk = `Pedido enviado a ${tableTitle(state.table)}.`;
      state.cart = [];
      state.category = null;
      clearPersistedCart();
      resetToHome();
      refreshHomeWidgets();
    } catch (error) {
      // Cart is intentionally NOT cleared here: it stays in state and in
      // sessionStorage so the mesero can just tap "Enviar pedido" again.
      state.sendError = error.message || "No se pudo enviar el pedido. Revisa la conexión e intenta de nuevo.";
    } finally {
      state.sending = false;
      render();
    }
  }

  // ---------------------------------------------------------------------
  // Screens
  // ---------------------------------------------------------------------

  function screenLogin() {
    return `
      <section class="wtr-login">
        <div class="wtr-login-card">
          <div class="wtr-brand">CLONEXA</div>
          <h1>Panel Mesero</h1>
          ${state.error ? `<div class="wtr-alert">${h(state.error)}</div>` : ""}
          <form id="wtrLoginForm">
            <label>Usuario<input name="username" autocomplete="username" required /></label>
            <label>Clave<input name="password" type="password" autocomplete="current-password" required /></label>
            <button type="submit" class="wtr-btn wtr-btn-primary" ${state.busy ? "disabled" : ""}>${state.busy ? "Entrando..." : "Entrar"}</button>
          </form>
        </div>
      </section>`;
  }

  function screenShiftPanel() {
    const op = state.operational;
    const status = op ? op.status : "active";
    return `
      <div class="wtr-shift-panel">
        <div class="wtr-shift-times">
          <div><span>Activo</span><strong data-wtr-active-timer>${formatHMS(op ? op.active_seconds : 0)}</strong></div>
          <div><span>Pausa</span><strong data-wtr-break-timer>${formatHMS(op ? op.break_seconds : 0)}</strong></div>
        </div>
        <div class="wtr-shift-actions">
          ${status === "break"
            ? `<button class="wtr-btn" type="button" data-wtr-shift-resume>Retomar</button>`
            : `<button class="wtr-btn" type="button" data-wtr-shift-pause>Pausa</button>`}
          <button class="wtr-btn" type="button" data-wtr-shift-finish>Finalizar turno</button>
          <button class="wtr-btn" type="button" data-wtr-change-password>Cambiar contraseña</button>
          <button class="wtr-btn wtr-btn-quiet" type="button" data-wtr-logout>Cerrar sesión</button>
        </div>
      </div>`;
  }

  function screenHome() {
    const goal = state.ventasHoy || {};
    const pct = Math.max(0, Math.min(100, Number(goal.goal_progress_percent || 0)));
    const op = state.operational;
    return `
      <section class="wtr-shell wtr-home">
        <header class="wtr-home-header">
          <div class="wtr-home-titles">
            <span class="wtr-company-name">${h(state.companyName)}</span>
            <span class="wtr-user-name">${h(state.mesero)}</span>
          </div>
          <button class="wtr-shift-toggle" type="button" data-wtr-shift-toggle>
            ${h(formatHMS(op ? op.active_seconds : 0))} ${state.shiftExpanded ? "▲" : "▾"}
          </button>
        </header>
        ${state.shiftExpanded ? screenShiftPanel() : ""}
        ${state.lastOrderOk ? `<div class="wtr-toast">${h(state.lastOrderOk)}</div>` : ""}
        <div class="wtr-goal-card">
          <div class="wtr-goal-row"><span>Meta de hoy</span><strong>${h(money(goal.total_today || 0))} / ${h(money(goal.daily_goal || 0))}</strong></div>
          <div class="wtr-goal-bar"><div class="wtr-goal-fill" style="width:${pct}%"></div></div>
        </div>
        <button class="wtr-btn wtr-btn-primary wtr-btn-huge" type="button" data-wtr-new-order>Tomar pedido</button>
        <h2 class="wtr-section-title">Mis mesas</h2>
        <div class="wtr-mesas-list">
          ${state.misMesas.length ? state.misMesas.map((t) => `
            <button class="wtr-mesa-row" type="button" data-wtr-mesa="${h(t.table_number)}">
              <span>${h(tableTitle(t.table_number))}</span>
              <span class="wtr-mesa-status ${mesaStatusView(t.status).cls}">${h(mesaStatusView(t.status).label)}</span>
            </button>`).join("") : `<div class="wtr-empty">Todavía no tienes mesas activas.</div>`}
        </div>
      </section>`;
  }

  // Mis mesas. "entregada": the kitchen delivered everything -> check, no
  // action left for the mesero (the table only waits for the caja).
  function mesaStatusView(status) {
    if (status === "entregada") return { cls: "is-done", label: "✓ Entregada · sin acción, espera cobro" };
    if (status === "listo_para_llevar") return { cls: "is-ready", label: "Lista para llevar" };
    return { cls: "is-sent", label: "Enviado a cocina" };
  }

  function screenTable() {
    const tables = state.tables.length
      ? state.tables.map((t) => t.label)
      : Array.from({ length: 20 }, (_, i) => `Mesa ${i + 1}`);
    return `
      <section class="wtr-shell">
        ${header("Elige la mesa")}
        <div class="wtr-grid-tables">
          ${tables.map((label) => `<button class="wtr-tile" type="button" data-wtr-table="${h(label)}">${h(label)}</button>`).join("")}
        </div>
      </section>`;
  }

  function kitOptions(attr) {
    return { companyId, emojis: state.menuEmojis, attr };
  }

  function screenCategories() {
    return `
      <section class="wtr-shell">
        ${header(tableTitle(state.table))}
        ${Kit.categoryGridHtml(state.menu, kitOptions("data-wtr-cat"))}
        ${cartFloatingButton()}
      </section>`;
  }

  function screenProducts() {
    const category = state.menu.find((cat) => cat.key === state.category);
    const products = category ? category.products : [];
    return `
      <section class="wtr-shell">
        ${header(category ? category.label : "Productos")}
        ${Kit.productGridHtml(products, kitOptions("data-wtr-product"))}
        ${cartFloatingButton()}
      </section>`;
  }

  function cartFloatingButton() {
    if (!state.cart.length) return "";
    return `<button class="wtr-btn wtr-btn-cart" type="button" data-wtr-goto-cart>Ver pedido (${state.cart.length}) · ${h(money(cartTotal()))}</button>`;
  }

  function cartLineLabel(item) {
    return Kit.cartLineLabel(item);
  }

  function screenCart() {
    return `
      <section class="wtr-shell">
        ${header("Revisar pedido")}
        ${state.sendError ? `<div class="wtr-alert" style="margin:0 16px 10px">${h(state.sendError)}</div>` : ""}
        <div class="wtr-cart-list">
          ${state.cart.map((item, index) => `
            <button class="wtr-cart-row" type="button" data-wtr-edit="${index}">
              <div>
                <b>${cartLineLabel(item)}</b>
                ${item.term ? `<div class="wtr-cart-note wtr-cart-term">${h(item.term)}</div>` : ""}
                ${item.observations ? `<div class="wtr-cart-note">${h(item.observations)}</div>` : ""}
                ${item.quick_notes && item.quick_notes.length ? `<div class="wtr-cart-note">${item.quick_notes.map(h).join(" · ")}</div>` : ""}
              </div>
              <div class="wtr-cart-row-actions">
                <strong>${h(money(item.unit_price * item.quantity))}</strong>
                <span class="wtr-cart-remove" data-wtr-remove="${index}" aria-label="Quitar">✕</span>
              </div>
            </button>`).join("") || `<div class="wtr-empty">Todavía no agregaste productos.</div>`}
        </div>
        <div class="wtr-cart-total"><span>Total</span><strong>${h(money(cartTotal()))}</strong></div>
        <button class="wtr-btn wtr-btn-primary" type="button" data-wtr-send ${state.sending || !state.cart.length ? "disabled" : ""}>
          ${state.sending ? "Enviando..." : state.sendError ? "Reintentar envío" : "Confirmar y enviar"}
        </button>
      </section>`;
  }

  function header(title) {
    return `
      <header class="wtr-header">
        <button class="wtr-back" type="button" data-wtr-back aria-label="Volver">‹</button>
        <h1>${h(title)}</h1>
      </header>`;
  }

  function render() {
    safeRender();
  }

  // A failure while drawing one screen must not blank the whole panel: show
  // a recoverable card instead (the cart and the session stay intact).
  function safeRender() {
    try {
      renderScreen();
    } catch (error) {
      try { console.error("[mesero] render", error); } catch (_) {}
      root.innerHTML = `
        <section class="wtr-shell wtr-recover">
          <div class="wtr-recover-card">
            <strong>Algo falló al mostrar esta pantalla.</strong>
            <p>Tu sesión y tu pedido siguen guardados.</p>
            <button class="wtr-btn wtr-btn-primary" type="button" data-wtr-recover>Volver al inicio</button>
          </div>
        </section>`;
    }
    renderConnection();
  }

  function renderScreen() {
    let html = "";
    if (state.screen === "login") html = screenLogin();
    else if (state.screen === "home") html = screenHome();
    else if (state.screen === "table") html = screenTable();
    else if (state.screen === "categories") html = screenCategories();
    else if (state.screen === "products") html = screenProducts();
    else if (state.screen === "cart") html = screenCart();
    root.innerHTML = html;
    renderAvisos();
    if (state.error && state.screen !== "login") {
      const banner = document.createElement("div");
      banner.className = "wtr-alert wtr-alert-floating";
      banner.textContent = state.error;
      root.appendChild(banner);
      window.setTimeout(() => { state.error = ""; }, 4000);
    }
  }

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("#wtrLoginForm");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    doLogin(String(data.get("username") || ""), String(data.get("password") || ""));
  });

  document.addEventListener("click", (event) => {
    try {
      handleClick(event);
    } catch (error) {
      try { console.error("[mesero] click", error); } catch (_) {}
      state.error = "No se pudo completar esa acción. Intenta de nuevo.";
      safeRender();
    }
  });

  function handleClick(event) {
    const target = event.target;

    const recover = target.closest("[data-wtr-recover]");
    if (recover) {
      closeOpenSheets();
      resetToHome();
      return;
    }

    const logout = target.closest("[data-wtr-logout]");
    if (logout) {
      setToken("");
      stopSessionKeeper();
      state.session = null;
      state.screen = "login";
      render();
      return;
    }

    const back2 = target.closest("[data-wtr-back]");
    if (back2) { back(); return; }

    const shiftToggle = target.closest("[data-wtr-shift-toggle]");
    if (shiftToggle) { state.shiftExpanded = !state.shiftExpanded; render(); return; }

    const shiftPause = target.closest("[data-wtr-shift-pause]");
    if (shiftPause) { shiftAction("pause"); return; }

    const shiftResume = target.closest("[data-wtr-shift-resume]");
    if (shiftResume) { shiftAction("resume"); return; }

    const shiftFinish = target.closest("[data-wtr-shift-finish]");
    if (shiftFinish) {
      if (window.confirm("¿Finalizar tu turno?")) shiftAction("finish");
      return;
    }

    const changePasswordBtn = target.closest("[data-wtr-change-password]");
    if (changePasswordBtn) { openChangePasswordSheet(); return; }

    const newOrder = target.closest("[data-wtr-new-order]");
    if (newOrder) { goto("table"); return; }

    const mesaRow = target.closest("[data-wtr-mesa]");
    if (mesaRow) {
      state.table = mesaRow.getAttribute("data-wtr-mesa") || "";
      goto("categories");
      return;
    }

    const tableBtn = target.closest("[data-wtr-table]");
    if (tableBtn) {
      state.table = tableBtn.getAttribute("data-wtr-table") || "";
      persistCart();
      goto("categories");
      return;
    }

    const catBtn = target.closest("[data-wtr-cat]");
    if (catBtn) {
      state.category = catBtn.getAttribute("data-wtr-cat") || "";
      goto("products");
      return;
    }

    const gotoCart = target.closest("[data-wtr-goto-cart]");
    if (gotoCart) { goto("cart"); return; }

    const removeBtn = target.closest("[data-wtr-remove]");
    if (removeBtn) {
      event.stopPropagation();
      removeCartLine(Number(removeBtn.getAttribute("data-wtr-remove")));
      render();
      return;
    }

    const editBtn = target.closest("[data-wtr-edit]");
    if (editBtn) {
      const index = Number(editBtn.getAttribute("data-wtr-edit"));
      const line = state.cart[index];
      if (line) {
        const found = line.menu_product_id && state.quantityButtons.length ? Kit.findMenuProduct(state.menu, line.menu_product_id) : null;
        if (found) {
          openConfigureSheet(found.product, found.category, null, line, index);
          return;
        }
        const category = state.menu.find((cat) => cat.key === state.category) || findCategoryForLine(line);
        openConfigureSheet({ id: line.inventory_item_id, name: line.name, price: line.unit_price }, category, line.portion_label || null, line, index);
      }
      return;
    }

    const sendBtn = target.closest("[data-wtr-send]");
    if (sendBtn && !sendBtn.disabled) { submitOrder(); return; }

    const productBtn = target.closest("[data-wtr-product]");
    if (productBtn) {
      const category = state.menu.find((cat) => cat.key === state.category);
      const product = (category ? category.products : []).find((item) => item.id === productBtn.getAttribute("data-wtr-product"));
      if (!product) return;
      if (Kit.productOpenMode(product, state.quantityButtons) === "portions") openPortionSheet(product, category);
      else openConfigureSheet(product, category, null);
    }
  }

  function findCategoryForLine(_line) {
    return null;
  }

  function openChangePasswordSheet() {
    const sheet = document.createElement("div");
    sheet.className = "wtr-sheet-backdrop";
    sheet.innerHTML = `
      <div class="wtr-sheet">
        <h2>Cambiar contraseña</h2>
        <label>Contraseña actual<input id="wtrPwCurrent" type="password" autocomplete="current-password" /></label>
        <label>Nueva contraseña<input id="wtrPwNew" type="password" autocomplete="new-password" /></label>
        <label>Confirmar nueva contraseña<input id="wtrPwConfirm" type="password" autocomplete="new-password" /></label>
        <div class="wtr-sheet-status" id="wtrPwStatus"></div>
        <div class="wtr-sheet-actions">
          <button type="button" class="wtr-btn" data-sheet-cancel>Cancelar</button>
          <button type="button" class="wtr-btn wtr-btn-primary" data-sheet-save-pw>Guardar</button>
        </div>
      </div>`;
    document.body.appendChild(sheet);
    sheet.querySelector("[data-sheet-cancel]").addEventListener("click", () => sheet.remove());
    sheet.querySelector("[data-sheet-save-pw]").addEventListener("click", async () => {
      const statusEl = sheet.querySelector("#wtrPwStatus");
      const current = sheet.querySelector("#wtrPwCurrent").value;
      const next = sheet.querySelector("#wtrPwNew").value;
      const confirm = sheet.querySelector("#wtrPwConfirm").value;
      try {
        await changePassword(current, next, confirm);
        sheet.remove();
      } catch (error) {
        statusEl.textContent = error.message || "No se pudo cambiar la contraseña.";
      }
    });
  }

  function openPortionSheet(group, category) {
    Kit.openPortionSheet(group, (portionProduct, portionLabel) => openConfigureSheet(portionProduct, category, portionLabel));
  }

  function openConfigureSheet(product, category, portionLabel, prefill, editIndex) {
    Kit.openItemSheet({
      product,
      category,
      portionLabel,
      prefill,
      quantityButtons: state.quantityButtons,
      menuProductId: Kit.findMenuProduct(state.menu, product.id) ? product.id : undefined,
      onAdd: (line) => {
        addOrUpdateCartLine(line, editIndex);
        render();
      },
    });
  }

  const style = document.createElement("style");
  style.textContent = `
    :root{color-scheme:dark}
    *{box-sizing:border-box}
    body{margin:0;background:#080712;color:#f5f3ff;font-family:Inter,system-ui,sans-serif}
    .wtr-login{min-height:100vh;display:grid;place-items:center;padding:20px;
      background:radial-gradient(circle at 20% 15%,rgba(247,37,133,.25),transparent 35%),linear-gradient(135deg,#0a0714,#0d1522 70%,#150019)}
    .wtr-login-card{width:100%;max-width:360px;padding:28px 22px;border-radius:22px;border:1px solid rgba(255,255,255,.12);background:rgba(15,12,28,.85)}
    .wtr-brand{font-size:12px;font-weight:900;letter-spacing:.2em;color:#ff2d95}
    .wtr-login-card h1{margin:6px 0 18px;font-size:26px}
    .wtr-login-card form{display:grid;gap:14px}
    .wtr-login-card label{display:grid;gap:6px;font-size:13px;font-weight:800;color:#c9c3e6}
    .wtr-login-card input{padding:14px;border-radius:14px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff;font-size:16px}
    .wtr-btn-quiet{background:transparent;border-color:rgba(255,255,255,.08);color:#a79fcf}
    .wtr-btn-huge{margin:14px 16px;height:64px;font-size:19px}
    .wtr-alert{margin-top:10px;padding:10px 12px;border-radius:12px;background:rgba(239,68,68,.16);color:#fecaca;font-size:13px;font-weight:800}
    .wtr-alert-floating{position:fixed;left:16px;right:16px;bottom:16px;z-index:50}
    .wtr-toast{margin:0 16px 10px;padding:10px 12px;border-radius:12px;background:rgba(34,197,94,.16);color:#bbf7d0;font-weight:800}
    .wtr-shell{min-height:100vh;padding-bottom:24px}
    .wtr-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;padding:16px;background:rgba(8,7,18,.92);backdrop-filter:blur(6px);border-bottom:1px solid rgba(255,255,255,.08)}
    .wtr-header h1{flex:1;margin:0;font-size:20px}
    .wtr-back{width:44px;height:44px;border-radius:14px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:20px}
    .wtr-home-header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:18px 16px 6px}
    .wtr-home-titles{display:flex;flex-direction:column;gap:2px}
    .wtr-company-name{font-size:12px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#ff2d95}
    .wtr-user-name{font-size:22px;font-weight:900}
    .wtr-shift-toggle{border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#c9c3e6;border-radius:999px;padding:8px 14px;font-size:12px;font-weight:800;min-height:auto}
    .wtr-shift-panel{margin:0 16px 12px;padding:14px;border-radius:18px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);display:grid;gap:12px}
    .wtr-shift-times{display:flex;gap:20px}
    .wtr-shift-times div{display:flex;flex-direction:column;gap:2px;font-size:12px;color:#8f8aa8}
    .wtr-shift-times strong{font-size:18px;color:#fff}
    .wtr-shift-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .wtr-shift-actions .wtr-btn{min-height:44px;font-size:13px}
    .wtr-goal-card{margin:6px 16px 4px;padding:14px;border-radius:18px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.03)}
    .wtr-goal-row{display:flex;justify-content:space-between;font-size:13px;font-weight:800;color:#c9c3e6;margin-bottom:8px}
    .wtr-goal-bar{height:10px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden}
    .wtr-goal-fill{height:100%;background:linear-gradient(90deg,#ff7a18,#ff2d95,#a855f7);transition:width .3s}
    .wtr-section-title{margin:18px 16px 8px;font-size:14px;color:#8f8aa8;text-transform:uppercase;letter-spacing:.1em}
    .wtr-mesas-list{display:grid;gap:8px;padding:0 16px}
    .wtr-mesa-row{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-radius:16px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#fff;font-weight:800}
    .wtr-mesa-status{font-size:12px;font-weight:900;padding:4px 10px;border-radius:999px}
    .wtr-mesa-status.is-sent{background:rgba(250,204,21,.18);color:#fde68a}
    .wtr-mesa-status.is-ready{background:rgba(34,197,94,.18);color:#bbf7d0}
    .wtr-mesa-status.is-done{background:rgba(148,163,184,.18);color:#e2e8f0}
    .wtr-mesa-row:has(.is-done){opacity:.72}
    .wtr-grid-tables{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:12px;padding:16px}
    .wtr-tile{min-height:72px;border-radius:18px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:16px;font-weight:900}
    .wtr-btn-cart{position:fixed;left:16px;right:16px;bottom:16px}
    .wtr-cart-list{display:grid;gap:10px;padding:16px}
    .wtr-cart-row{display:flex;justify-content:space-between;gap:10px;padding:12px;border-radius:16px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#fff;text-align:left;width:100%}
    .wtr-cart-note{font-size:12px;color:#ffb3d9}
    .wtr-cart-term{color:#ffd166;font-weight:800}
    .wtr-cart-row-actions{display:flex;align-items:center;gap:10px}
    .wtr-cart-remove{width:32px;height:32px;border-radius:10px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;display:grid;place-items:center}
    .wtr-cart-total{display:flex;justify-content:space-between;padding:0 16px;font-size:18px;font-weight:900;margin-bottom:14px}
    .wtr-shell > .wtr-btn-primary{margin:0 16px;width:calc(100% - 32px)}
    .wtr-net{position:fixed;left:0;right:0;bottom:0;z-index:80;padding:12px 16px;background:#b45309;color:#fff;font-size:14px;font-weight:900;text-align:center;box-shadow:0 -6px 20px rgba(0,0,0,.4)}
    .wtr-recover{display:grid;place-items:center;padding:24px}
    .wtr-recover-card{max-width:360px;display:grid;gap:12px;padding:22px;border-radius:20px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);text-align:center}
    .wtr-recover-card p{margin:0;color:#c9c3e6}
  `;
  document.head.appendChild(style);
  Kit.injectStyles();
  if (Alerts) Alerts.install();

  let homeRefreshHandle = null;
  let avisosHandle = null;
  function startHomeRefresh() {
    if (!avisosHandle) {
      loadAvisos();
      avisosHandle = window.setInterval(() => {
        if (state.avisosEnabled) loadAvisos();
        else { window.clearInterval(avisosHandle); }
      }, AVISOS_POLL_MS);
    }
    if (homeRefreshHandle) return;
    homeRefreshHandle = window.setInterval(() => {
      if (state.screen === "home") refreshHomeWidgets();
    }, 20000);
  }

  window.addEventListener("popstate", (event) => {
    try {
      onPopState(event);
    } catch (error) {
      try { console.error("[mesero] popstate", error); } catch (_) {}
    }
  });
  window.addEventListener("online", () => { tryReconnect(); });
  window.addEventListener("offline", () => { markOffline("network"); });
  document.addEventListener("visibilitychange", () => {
    try { onVisible(); } catch (_) {}
  });
  // Last line of defence: a stray error in a timer or a promise shows a
  // short notice instead of leaving the panel dead. Nothing here reloads
  // the page or clears the session.
  window.addEventListener("error", (event) => {
    try { console.error("[mesero] error", event.error || event.message); } catch (_) {}
  });
  window.addEventListener("unhandledrejection", (event) => {
    try { console.error("[mesero] promesa", event.reason); } catch (_) {}
    if (event && typeof event.preventDefault === "function") event.preventDefault();
  });

  if (!companyId) {
    root.innerHTML = `<section style="min-height:100vh;display:grid;place-items:center;background:#080712;color:#fff"><p>Falta company_id en el enlace.</p></section>`;
  } else if (token()) {
    restoreProfile();
    restoreCart(state.username);
    state.stack = ["home"];
    state.screen = "home";
    installHistory();
    safeRender();
    enterHome().then(safeRender, safeRender);
    startHomeRefresh();
    startSessionKeeper();
  } else {
    restoreProfile();
    safeRender();
  }
})();
