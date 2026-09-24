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
    safeRender();
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

  async function loadCashierConfig() {
    try {
      const data = await waiterApi("/caja/config");
      state.directSale = data.direct_sale === true;
    } catch (_) {
      state.directSale = false;
    }
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
      addLabel: "Agregar a la venta",
      menuProductId: Kit.findMenuProduct(state.menu, product.id) ? product.id : undefined,
      onAdd: (line) => {
        if (editIndex === null || editIndex === undefined) state.sale.items.push(line);
        else state.sale.items[editIndex] = line;
        safeRender();
      },
    });
  }

  function openSaleProduct(productId) {
    const category = saleCategory();
    const product = (category ? category.products || [] : []).find((item) => item.id === productId);
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
    state.sale = { items: [], table: table || "", toKitchen: false, category: "" };
    goto("sale");
  }

  function openSaleCategory(key) {
    state.sale.category = key || "";
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
      state.tables = sortTablesByAge(Array.from(groups.values()), Date.now());
      state.tablesLoaded = true;
      const detected = cajaAlerts(alertMemory, state.tables);
      alertMemory = detected.memory;
      if (Alerts) detected.alerts.forEach((alert) => Alerts.notify(alert));
      // Never redraw the sale screens from the 4s poll: it would close the
      // destination list or a product sheet mid-choice.
      if (!/^sale/.test(state.screen)) safeRender();
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
    else if (state.screen === "sale") html = screenSale();
    else if (state.screen === "sale_products") html = screenSaleProducts();
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
      if (window.confirm("¿Cerrar tu jornada? Se registran tus horas y se cierra la sesión.")) shiftAction("finish");
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
