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
    stack: ["tables"],
    offline: false,
    offlineReason: "",
  };

  let pollHandle = null;

  // .replace(/x/g) instead of .replaceAll: replaceAll throws on older
  // Android WebViews and h() runs on every render.
  function h(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function money(value) {
    const number = Number(value || 0);
    try {
      return new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 }).format(number);
    } catch (_) {
      return `$${Math.round(number).toLocaleString("es-CO")}`;
    }
  }

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
    storeSet("sessionStorage", navKey, JSON.stringify({ stack: state.stack, activeTableKey: state.activeTableKey }));
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
    } catch (error) {
      state.error = error.message || "No se pudo iniciar sesión.";
    } finally {
      state.busy = false;
      render();
    }
  }

  async function loadMenu() {
    try {
      const data = await waiterApi("/menu");
      state.menu = Array.isArray(data.categories) ? data.categories : [];
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
      orders.forEach((order) => {
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
      state.tables = Array.from(groups.values()).sort((a, b) => String(a.table_number).localeCompare(String(b.table_number)));
      state.tablesLoaded = true;
      safeRender();
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

  function tableStatusLabel(table) {
    const hasPending = table.orders.some((o) => o.status === "pendiente" || o.status === "alistando");
    if (hasPending) return "En cocina";
    return "Lista para cobrar";
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

  async function chargeTable(paymentMethod) {
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
      state.toast = `Mesa ${table.table_number} cobrada.`;
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

  function screenTables() {
    return `
      <section class="csh-shell">
        <header class="csh-header">
          <h1>Mesas abiertas</h1>
          <button class="csh-btn csh-btn-mini" type="button" data-csh-register-network>Registrar la red actual del local</button>
          <button class="csh-logout" type="button" data-csh-logout aria-label="Salir">⏻</button>
        </header>
        ${state.toast ? `<div class="csh-toast">${h(state.toast)}</div>` : ""}
        <div class="csh-grid-tables">
          ${state.tables.map((table) => `
            <button class="csh-tile" type="button" data-csh-open-table="${h(table.key)}">
              <div class="csh-tile-top">
                <b>${h(table.table_number)}</b>
                <span class="csh-status">${h(tableStatusLabel(table))}</span>
              </div>
              <div class="csh-tile-mid">${table.waiter ? `Mesero: ${h(table.waiter)}` : ""}</div>
              <strong>${h(money(table.total))}</strong>
            </button>`).join("") || `<div class="csh-empty">No hay mesas abiertas.</div>`}
        </div>
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
    return `
      <section class="csh-shell">
        <header class="csh-header">
          <button class="csh-back" type="button" data-csh-back aria-label="Volver">‹</button>
          <h1>${h(table.table_number)}</h1>
          <button class="csh-logout" type="button" data-csh-logout aria-label="Salir">⏻</button>
        </header>
        <div class="csh-account-label">CUENTA - NO ES FACTURA</div>
        <div class="csh-cart-list">
          ${allItems.map((item) => `
            <div class="csh-cart-row">
              <div><b>${h(item.quantity)} x ${h(item.name)}</b>${item.observations ? `<div class="csh-note">${h(item.observations)}</div>` : ""}</div>
              <strong>${h(money((item.unit_price || 0) * (item.quantity || 0)))}</strong>
            </div>`).join("") || `<div class="csh-empty">Sin productos todavía.</div>`}
        </div>
        <div class="csh-cart-total"><span>Total</span><strong>${h(money(table.total))}</strong></div>
        <button class="csh-btn" type="button" data-csh-add-product>+ Agregar producto</button>
        ${canCharge ? `
          <div class="csh-pay-block">
            <div class="csh-pay-title">Cobrar mesa (método de pago obligatorio)</div>
            <div class="csh-pay-options">
              ${PAYMENT_METHODS.map((pm) => `<button class="csh-btn csh-btn-primary" type="button" data-csh-pay="${pm.value}" ${state.paying ? "disabled" : ""}>${h(pm.label)}</button>`).join("")}
            </div>
          </div>` : `<div class="csh-hint">Entrega el pedido pendiente antes de cobrar.</div>`}
      </section>`;
  }

  function render() {
    safeRender();
  }

  // One failing screen must not blank the whole panel.
  function safeRender() {
    try {
      renderScreen();
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
    if (state.screen === "login") html = screenLogin();
    else if (state.screen === "tables") html = screenTables();
    else if (state.screen === "table") html = screenTable();
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
      openProductPicker();
      return;
    }

    const payBtn = target.closest("[data-csh-pay]");
    if (payBtn && !payBtn.disabled) {
      chargeTable(payBtn.getAttribute("data-csh-pay"));
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
    .csh-toast{margin:0 16px 10px;padding:10px 12px;border-radius:12px;background:rgba(34,197,94,.16);color:#bbf7d0;font-weight:800}
    .csh-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;padding:16px;background:rgba(8,7,18,.92);backdrop-filter:blur(6px);border-bottom:1px solid rgba(255,255,255,.08);flex-wrap:wrap}
    .csh-header h1{flex:1;margin:0;font-size:20px}
    .csh-back,.csh-logout{width:40px;height:40px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:18px}
    .csh-grid-tables{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;padding:16px}
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
    .csh-net{position:fixed;left:0;right:0;bottom:0;z-index:80;padding:12px 16px;background:#b45309;color:#fff;font-size:14px;font-weight:900;text-align:center}
    .csh-recover{display:grid;place-items:center;padding:24px}
    .csh-recover-card{max-width:360px;display:grid;gap:12px;padding:22px;border-radius:20px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);text-align:center}
    .csh-recover-card p{margin:0;color:#c9c3e6}
    .csh-sheet-item{display:flex;justify-content:space-between;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#fff}
  `;
  document.head.appendChild(style);

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

  if (!companyId) {
    root.innerHTML = `<section style="min-height:100vh;display:grid;place-items:center;background:#080712;color:#fff"><p>Falta company_id en el enlace.</p></section>`;
  } else if (token()) {
    state.stack = ["tables"];
    state.screen = "tables";
    installHistory();
    startPolling();
    startSessionKeeper();
    loadMenu();
    safeRender();
  } else {
    safeRender();
  }
})();
