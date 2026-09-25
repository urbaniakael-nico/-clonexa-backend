(() => {
  "use strict";

  const root = document.getElementById("app");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const PANEL_TYPE = "cocina";
  const storageKey = `clonexa_kitchen_token_${companyId}`;
  const POLL_MS = 2000;

  const state = {
    screen: "login",
    error: "",
    busy: false,
    comandas: [],
    thresholds: { green_max_minutes: 10, yellow_max_minutes: 20 },
    stations: [],
    // Tablero en 3 columnas: only when the company has the switch on (the
    // server says so in columns_enabled); otherwise the classic board.
    columnsEnabled: false,
    columns: { nuevo: [], preparando: [], listo: [] },
    view: "board",
    history: [],
    // Registro entrada: only with the company's kitchen_roster switch on.
    rosterEnabled: false,
    roster: [],
    rosterLoadedAt: 0,
  };

  const COLUMNS = [
    { key: "nuevo", title: "Pedido nuevo" },
    { key: "preparando", title: "Preparando" },
    { key: "listo", title: "Listo" },
  ];

  let pollHandle = null;
  // "Pedido nuevo": sound + vibration + card until closed (hsp_alerts.js).
  const Alerts = window.CxAlerts ? window.CxAlerts.create("cocina") : null;
  let seenComandas = null;   // null = first load: nothing is announced

  function comandaSummary(comanda) {
    return (comanda.items || [])
      .map((item) => `${item.quantity_label || `${item.quantity}×`} ${item.name}`)
      .join(" · ");
  }

  // New comandas since the last poll, announced once each.
  function newComandaAlerts(comandas) {
    const ids = comandas.map((c) => c.order_id);
    const fresh = window.CxAlerts ? window.CxAlerts.newIds(seenComandas, ids) : [];
    seenComandas = new Set([...(seenComandas || []), ...ids]);
    return comandas
      .filter((c) => fresh.includes(c.order_id))
      .map((c) => ({ kind: "new_order", title: `Pedido nuevo · ${c.table_number || "Mesa"}`, message: comandaSummary(c) }));
  }

  function h(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function token() {
    return sessionStorage.getItem(storageKey) || "";
  }

  function setToken(value) {
    if (value) sessionStorage.setItem(storageKey, value);
    else sessionStorage.removeItem(storageKey);
  }

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    const tok = token();
    if (tok) headers.Authorization = `Bearer ${tok}`;
    const response = await fetch(path, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data.detail || data.message || "Solicitud rechazada.";
      // 048Q: cualquier 401 con sesion (otro dispositivo, corte diario del
      // sistema, cerrada desde Admin V2) vuelve al login con usuario y clave.
      if (response.status === 401 && tok) {
        stopPolling();
        setToken("");
        state.screen = "login";
        state.error = /otro dispositivo/i.test(String(message))
          ? "Tu sesión se abrió en otro dispositivo."
          : /corte diario/i.test(String(message))
            ? "El sistema cerró la sesión en el corte diario. Vuelve a entrar con tu usuario y clave."
            : "Tu sesión terminó. Vuelve a entrar con tu usuario y clave.";
        render();
      }
      throw new Error(message);
    }
    return data;
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
        body: JSON.stringify({ username, password, panel_type: PANEL_TYPE }),
      });
      setToken(data.access_token || "");
      state.screen = "board";
      startPolling();
    } catch (error) {
      state.error = error.message || "No se pudo iniciar sesión.";
    } finally {
      state.busy = false;
      render();
    }
  }

  async function refreshBoard() {
    try {
      const data = await waiterApi("/kitchen");
      state.comandas = Array.isArray(data.comandas) ? data.comandas : [];
      state.thresholds = data.timer_thresholds || state.thresholds;
      state.stations = Array.isArray(data.stations) ? data.stations : [];
      state.columnsEnabled = data.columns_enabled === true;
      state.rosterEnabled = data.roster_enabled === true;
      state.columns = boardColumns(data);
      const alerts = newComandaAlerts(state.comandas);
      if (Alerts) alerts.forEach((alert) => Alerts.notify(alert));
      if (state.view === "board") render();
      else if (state.view === "roster" && Date.now() - state.rosterLoadedAt > 15000) loadRoster();
      else if (state.view === "roster") render();   // keeps the shift timers ticking
    } catch (_) {
      // keep last board on transient errors; the 401 handler already redirects on session kick
    }
  }

  // Oldest first inside every column: new/preparing by when the order came
  // in, Listo by when the kitchen finished it.
  function boardColumns(data) {
    const cols = (data && data.columns) || {};
    const byTime = (key) => (a, b) => String(a[key] || a.created_at || "").localeCompare(String(b[key] || b.created_at || ""));
    return {
      nuevo: (Array.isArray(cols.nuevo) ? cols.nuevo : []).slice().sort(byTime("created_at")),
      preparando: (Array.isArray(cols.preparando) ? cols.preparando : []).slice().sort(byTime("created_at")),
      listo: (Array.isArray(cols.listo) ? cols.listo : []).slice().sort(byTime("ready_at")),
    };
  }

  function columnAction(columnKey) {
    if (columnKey === "nuevo") return { label: "EMPEZAR", path: "start", cls: "ktc-btn-start" };
    if (columnKey === "preparando") return { label: "COMANDA LISTA", path: "ready", cls: "ktc-btn-primary" };
    if (columnKey === "listo") return { label: "ENTREGADO", path: "delivered", cls: "ktc-btn-deliver" };
    return null;
  }

  async function advanceComanda(orderId, path, button) {
    button.disabled = true;
    try {
      await waiterApi(`/orders/${encodeURIComponent(orderId)}/${path}`, { method: "PATCH" });
      await refreshBoard();
    } catch (error) {
      button.disabled = false;
      state.error = error.message || "No se pudo mover la comanda.";
      render();
    }
  }

  async function loadRoster() {
    try {
      const data = await waiterApi("/kitchen-team");
      state.roster = Array.isArray(data.members) ? data.members : [];
      state.rosterLoadedAt = Date.now();
    } catch (error) {
      state.error = error.message || "No se pudo cargar el registro de entrada.";
    }
    render();
  }

  async function rosterAction(employeeId, action, button) {
    button.disabled = true;
    try {
      const data = await waiterApi(`/kitchen-team/${encodeURIComponent(employeeId)}/${action}`, { method: "POST" });
      const member = data.member;
      if (member) state.roster = state.roster.map((m) => (m.employee_id === member.employee_id ? member : m));
      render();
    } catch (error) {
      button.disabled = false;
      state.error = error.message || "No se pudo actualizar el turno.";
      render();
    }
  }

  // Which buttons each person gets: Iniciar when out (or to come back from
  // a pause), Pausar while working, Salir turno whenever a shift is open.
  function rosterButtons(member) {
    if (member.state === "working") return ["pausar", "salir"];
    if (member.state === "on_break") return ["iniciar", "salir"];
    return ["iniciar"];
  }

  // Worked time, live: the server's active_seconds plus what has run since
  // it answered while the person is working.
  function workedSeconds(member, nowMs) {
    const session = member.session;
    if (!session) return 0;
    let seconds = Number(session.active_seconds || 0);
    if (member.state === "working") {
      const serverTime = Date.parse(session.server_time || "");
      if (Number.isFinite(serverTime)) seconds += Math.max(0, (nowMs - serverTime) / 1000);
    }
    return Math.floor(seconds);
  }

  function formatWorked(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds || 0)));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  }

  async function loadHistory() {
    try {
      const data = await waiterApi("/kitchen/entregadas");
      state.history = Array.isArray(data.comandas) ? data.comandas : [];
    } catch (error) {
      state.history = [];
      state.error = error.message || "No se pudo cargar el historial.";
    }
    render();
  }

  function startPolling() {
    stopPolling();
    refreshBoard();
    pollHandle = window.setInterval(refreshBoard, POLL_MS);
  }

  function stopPolling() {
    if (pollHandle) window.clearInterval(pollHandle);
    pollHandle = null;
  }

  function minutesOpen(createdAt) {
    const start = Date.parse(createdAt || "");
    if (!Number.isFinite(start)) return 0;
    return Math.max(0, (Date.now() - start) / 60000);
  }

  function timerClass(minutes) {
    const t = state.thresholds || {};
    const green = Number(t.green_max_minutes ?? 10);
    const yellow = Number(t.yellow_max_minutes ?? 20);
    if (minutes < green) return "ktc-timer-green";
    if (minutes < yellow) return "ktc-timer-yellow";
    return "ktc-timer-red";
  }

  async function markItemReady(orderId, itemId, button) {
    button.disabled = true;
    try {
      await waiterApi(`/orders/${encodeURIComponent(orderId)}/items/${encodeURIComponent(itemId)}/ready`, { method: "PATCH" });
      await refreshBoard();
    } catch (error) {
      button.disabled = false;
      state.error = error.message || "No se pudo marcar el producto.";
      render();
    }
  }

  async function markComandaReady(orderId, button) {
    button.disabled = true;
    try {
      await waiterApi(`/orders/${encodeURIComponent(orderId)}/ready`, { method: "PATCH" });
      await refreshBoard();
    } catch (error) {
      button.disabled = false;
      state.error = error.message || "No se pudo marcar la comanda.";
      render();
    }
  }

  function screenLogin() {
    return `
      <section class="ktc-login">
        <div class="ktc-login-card">
          <div class="ktc-brand">CLONEXA</div>
          <h1>Panel Cocina</h1>
          ${state.error ? `<div class="ktc-alert">${h(state.error)}</div>` : ""}
          <form id="ktcLoginForm">
            <label>Usuario<input name="username" autocomplete="username" required /></label>
            <label>Clave<input name="password" type="password" autocomplete="current-password" required /></label>
            <button type="submit" class="ktc-btn ktc-btn-primary" ${state.busy ? "disabled" : ""}>${state.busy ? "Entrando..." : "Entrar"}</button>
          </form>
        </div>
      </section>`;
  }

  function itemLine(item) {
    // High-contrast, from-a-distance line: "1/2 POLLO ASADO — BIEN COCINADO".
    // The portion (if any) already lives in the product's own name (each
    // portion is its own inventory item, see hospitality_product_portions),
    // so this only appends the cooking term the mesero picked.
    const name = String(item.name || "").toUpperCase();
    const term = String(item.term || "").toUpperCase();
    return term ? `${name} — ${term}` : name;
  }

  // "1/4" for a fraction line (cantidad por botones), otherwise "2×".
  function itemQuantity(item) {
    return item.quantity_label ? String(item.quantity_label) : `${item.quantity}×`;
  }

  // Domicilios por WhatsApp: not a table -- say so and where it goes.
  function deliveryTag(comanda) {
    const delivery = comanda.delivery;
    if (!delivery) return "";
    return `<div class="ktc-delivery">🛵 DOMICILIO · ${h(delivery.customer_name || "")}<small>${h(delivery.address || "")}</small></div>`;
  }

  function comandaCard(comanda) {
    const minutes = minutesOpen(comanda.created_at);
    const cls = timerClass(minutes);
    const waiterName = comanda.waiter && comanda.waiter.name ? comanda.waiter.name : "";
    const allReady = (comanda.items || []).every((item) => item.ready);
    return `
      <article class="ktc-card ${cls}">
        <header>
          <div class="ktc-table">${h(comanda.table_number || "Mesa")}</div>
          <div class="ktc-meta">
            ${waiterName ? `<span class="ktc-waiter">${h(waiterName)}</span>` : ""}
            <span class="ktc-timer">${Math.floor(minutes)} min</span>
          </div>
        </header>
        ${deliveryTag(comanda)}
        <div class="ktc-items">
          ${(comanda.items || []).map((item) => `
            <div class="ktc-item ${item.ready ? "is-ready" : ""}">
              <div class="ktc-item-main">
                <b>${h(itemQuantity(item))} ${h(itemLine(item))}</b>
                ${item.observations ? `<div class="ktc-note">⚠ ${h(item.observations)}</div>` : ""}
                ${(item.quick_notes || []).length ? `<div class="ktc-note">⚠ ${item.quick_notes.map(h).join(" · ")}</div>` : ""}
              </div>
              ${item.ready
                ? `<span class="ktc-ready-pill">LISTO</span>`
                : `<button type="button" class="ktc-btn ktc-btn-mini" data-ktc-item-ready="${h(comanda.order_id)}" data-item-id="${h(item.id)}">LISTO</button>`}
            </div>`).join("")}
        </div>
        ${comanda.notes ? `<div class="ktc-order-note">⚠ ${h(comanda.notes)}</div>` : ""}
        <button type="button" class="ktc-btn ktc-btn-primary" data-ktc-order-ready="${h(comanda.order_id)}" ${allReady ? "" : "disabled"}>
          COMANDA LISTA
        </button>
      </article>`;
  }

  function columnCard(comanda, columnKey) {
    const action = columnAction(columnKey);
    const isListo = columnKey === "listo";
    const minutes = minutesOpen(isListo ? comanda.ready_at : comanda.created_at);
    const cls = isListo ? "ktc-card-listo" : timerClass(minutes);
    const waiterName = comanda.waiter && comanda.waiter.name ? comanda.waiter.name : "";
    return `
      <article class="ktc-card ktc-card-col ${cls}">
        <header>
          <div class="ktc-table">${h(comanda.table_number || "Mesa")}</div>
          <div class="ktc-meta">
            ${waiterName ? `<span class="ktc-waiter">${h(waiterName)}</span>` : ""}
            <span class="ktc-timer">${isListo ? "lista hace " : ""}${Math.floor(minutes)} min</span>
          </div>
        </header>
        ${deliveryTag(comanda)}
        <div class="ktc-items">
          ${(comanda.items || []).map((item) => `
            <div class="ktc-item ${item.ready && columnKey === "preparando" ? "is-ready" : ""}">
              <div class="ktc-item-main">
                <b>${h(itemQuantity(item))} ${h(itemLine(item))}</b>
                ${item.observations ? `<div class="ktc-note">⚠ ${h(item.observations)}</div>` : ""}
                ${(item.quick_notes || []).length ? `<div class="ktc-note">⚠ ${item.quick_notes.map(h).join(" · ")}</div>` : ""}
              </div>
              ${columnKey === "preparando" && !item.ready
                ? `<button type="button" class="ktc-btn ktc-btn-mini" data-ktc-item-ready="${h(comanda.order_id)}" data-item-id="${h(item.id)}">LISTO</button>`
                : ""}
            </div>`).join("")}
        </div>
        ${comanda.notes ? `<div class="ktc-order-note">⚠ ${h(comanda.notes)}</div>` : ""}
        ${action ? `<button type="button" class="ktc-btn ${action.cls}" data-ktc-advance="${h(comanda.order_id)}" data-ktc-path="${action.path}">${action.label}</button>` : ""}
      </article>`;
  }

  function screenColumns() {
    return `
      <div class="ktc-columns">
        ${COLUMNS.map((col) => {
          const rows = state.columns[col.key] || [];
          return `
            <section class="ktc-column ktc-column-${col.key}">
              <h2>${h(col.title)} <span class="ktc-count">${rows.length}</span></h2>
              ${rows.map((comanda) => columnCard(comanda, col.key)).join("") || `<div class="ktc-empty">Nada aquí.</div>`}
            </section>`;
        }).join("")}
      </div>`;
  }

  function historyTime(value) {
    const date = new Date(value || "");
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
  }

  function screenHistory() {
    return `
      <div class="ktc-history">
        ${state.history.map((comanda) => `
          <div class="ktc-history-row">
            <strong>${h(comanda.table_number || "Mesa")}</strong>
            <span>${(comanda.items || []).map((item) => `${h(itemQuantity(item))} ${h(item.name)}`).join(" · ")}</span>
            <span class="ktc-history-meta">${comanda.waiter && comanda.waiter.name ? `${h(comanda.waiter.name)} · ` : ""}entregada ${h(historyTime(comanda.delivered_at))}</span>
          </div>`).join("") || `<div class="ktc-empty">Todavía no hay comandas entregadas hoy.</div>`}
      </div>`;
  }

  function screenRoster() {
    const labels = { iniciar: "INICIAR", pausar: "PAUSAR", salir: "SALIR TURNO" };
    const states = { working: "Trabajando", on_break: "En pausa", off: "Fuera de turno" };
    const now = Date.now();
    return `
      <div class="ktc-roster">
        ${state.roster.map((member) => `
          <div class="ktc-roster-row ktc-roster-${h(member.state)}">
            <div class="ktc-roster-who">
              <strong>${h(member.full_name)}</strong>
              <span>${h(member.role || "Cocina")}</span>
            </div>
            <div class="ktc-roster-state">
              <span class="ktc-roster-chip">${h(states[member.state] || member.state)}</span>
              ${member.session ? `<span class="ktc-roster-time">${h(formatWorked(workedSeconds(member, now)))}</span>` : ""}
            </div>
            <div class="ktc-roster-actions">
              ${rosterButtons(member).map((action) => `
                <button type="button" class="ktc-btn ktc-roster-btn ktc-roster-${action}" data-ktc-roster="${h(member.employee_id)}" data-ktc-roster-action="${action}">${labels[action]}</button>`).join("")}
            </div>
          </div>`).join("") || `<div class="ktc-empty">No hay personas asignadas a cocina en Workforce.</div>`}
      </div>`;
  }

  function screenBoard() {
    return `
      <section class="ktc-shell">
        <header class="ktc-header">
          <h1>Cocina</h1>
          <div class="ktc-legend">
            <span class="ktc-dot ktc-timer-green"></span> &lt; ${h(state.thresholds.green_max_minutes)} min
            <span class="ktc-dot ktc-timer-yellow"></span> ${h(state.thresholds.green_max_minutes)}-${h(state.thresholds.yellow_max_minutes)}
            <span class="ktc-dot ktc-timer-red"></span> &gt; ${h(state.thresholds.yellow_max_minutes)} min
          </div>
          ${state.view !== "board" ? `
            <button class="ktc-btn ktc-btn-tab" type="button" data-ktc-view="board">Volver al tablero</button>` : ""}
          ${state.columnsEnabled && state.view !== "history" ? `
            <button class="ktc-btn ktc-btn-tab" type="button" data-ktc-view="history">Entregadas hoy</button>` : ""}
          ${state.rosterEnabled && state.view !== "roster" ? `
            <button class="ktc-btn ktc-btn-tab" type="button" data-ktc-view="roster">Registro entrada</button>` : ""}
          <button class="ktc-logout" type="button" data-ktc-logout aria-label="Salir">⏻</button>
        </header>
        ${state.view === "roster" && state.rosterEnabled
          ? screenRoster()
          : state.columnsEnabled
            ? (state.view === "history" ? screenHistory() : screenColumns())
            : `<div class="ktc-board">
          ${state.comandas.map(comandaCard).join("") || `<div class="ktc-empty">Sin comandas pendientes en tus estaciones.</div>`}
        </div>`}
      </section>`;
  }

  function render() {
    root.innerHTML = state.screen === "login" ? screenLogin() : screenBoard();
    if (state.error && state.screen !== "login") {
      const banner = document.createElement("div");
      banner.className = "ktc-alert ktc-alert-floating";
      banner.textContent = state.error;
      root.appendChild(banner);
      window.setTimeout(() => { state.error = ""; }, 4000);
    }
  }

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("#ktcLoginForm");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    doLogin(String(data.get("username") || ""), String(data.get("password") || ""));
  });

  document.addEventListener("click", (event) => {
    const target = event.target;

    const logout = target.closest("[data-ktc-logout]");
    if (logout) {
      stopPolling();
      setToken("");
      state.screen = "login";
      render();
      return;
    }

    const itemReady = target.closest("[data-ktc-item-ready]");
    if (itemReady) {
      markItemReady(itemReady.getAttribute("data-ktc-item-ready"), itemReady.getAttribute("data-item-id"), itemReady);
      return;
    }

    const advance = target.closest("[data-ktc-advance]");
    if (advance && !advance.disabled) {
      advanceComanda(advance.getAttribute("data-ktc-advance"), advance.getAttribute("data-ktc-path"), advance);
      return;
    }

    const viewBtn = target.closest("[data-ktc-view]");
    if (viewBtn) {
      const view = viewBtn.getAttribute("data-ktc-view");
      state.view = view === "history" || view === "roster" ? view : "board";
      if (state.view === "history") loadHistory();
      else if (state.view === "roster") loadRoster();
      else render();
      return;
    }

    const rosterBtn = target.closest("[data-ktc-roster]");
    if (rosterBtn && !rosterBtn.disabled) {
      rosterAction(rosterBtn.getAttribute("data-ktc-roster"), rosterBtn.getAttribute("data-ktc-roster-action"), rosterBtn);
      return;
    }

    const orderReady = target.closest("[data-ktc-order-ready]");
    if (orderReady && !orderReady.disabled) {
      markComandaReady(orderReady.getAttribute("data-ktc-order-ready"), orderReady);
    }
  });

  const style = document.createElement("style");
  style.textContent = `
    :root{color-scheme:dark}
    *{box-sizing:border-box}
    body{margin:0;background:#080712;color:#f5f3ff;font-family:Inter,system-ui,sans-serif}
    .ktc-login{min-height:100vh;display:grid;place-items:center;padding:20px;
      background:radial-gradient(circle at 20% 15%,rgba(247,37,133,.25),transparent 35%),linear-gradient(135deg,#0a0714,#0d1522 70%,#150019)}
    .ktc-login-card{width:100%;max-width:360px;padding:28px 22px;border-radius:22px;border:1px solid rgba(255,255,255,.12);background:rgba(15,12,28,.85)}
    .ktc-brand{font-size:12px;font-weight:900;letter-spacing:.2em;color:#ff2d95}
    .ktc-login-card h1{margin:6px 0 18px;font-size:26px}
    .ktc-login-card form{display:grid;gap:14px}
    .ktc-login-card label{display:grid;gap:6px;font-size:13px;font-weight:800;color:#c9c3e6}
    .ktc-login-card input{padding:14px;border-radius:14px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff;font-size:16px}
    .ktc-btn{min-height:52px;border-radius:14px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:16px;font-weight:900;cursor:pointer;letter-spacing:.02em}
    .ktc-btn-primary{border:none;background:linear-gradient(135deg,#22c55e,#16a34a);width:100%;min-height:60px;font-size:18px}
    .ktc-btn-primary:disabled{opacity:.35;cursor:not-allowed}
    .ktc-btn-mini{min-height:48px;padding:0 16px;font-size:15px;background:rgba(34,197,94,.14);border-color:rgba(34,197,94,.4)}
    .ktc-alert{margin-top:10px;padding:10px 12px;border-radius:12px;background:rgba(239,68,68,.16);color:#fecaca;font-size:13px;font-weight:800}
    .ktc-alert-floating{position:fixed;left:16px;right:16px;bottom:16px;z-index:50}
    .ktc-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;padding:16px;background:rgba(8,7,18,.92);backdrop-filter:blur(6px);border-bottom:1px solid rgba(255,255,255,.08);flex-wrap:wrap}
    .ktc-header h1{margin:0;font-size:20px}
    .ktc-legend{flex:1;display:flex;gap:10px;align-items:center;font-size:11px;color:#c9c3e6;flex-wrap:wrap}
    .ktc-dot{width:10px;height:10px;border-radius:50%;display:inline-block}
    .ktc-logout{width:40px;height:40px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:18px}
    .ktc-board{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;padding:16px}
    .ktc-card{border-radius:22px;padding:16px;display:grid;gap:12px;background:#0a0716;border:3px solid rgba(255,255,255,.12)}
    .ktc-card.ktc-timer-green{border-color:#22c55e}
    .ktc-card.ktc-timer-yellow{border-color:#eab308}
    .ktc-card.ktc-timer-red{border-color:#ef4444;animation:ktcPulse 1.4s ease-in-out infinite}
    @keyframes ktcPulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.4)}50%{box-shadow:0 0 0 10px rgba(239,68,68,0)}}
    .ktc-card header{display:flex;justify-content:space-between;align-items:baseline;gap:10px;border-bottom:1px solid rgba(255,255,255,.1);padding-bottom:10px}
    .ktc-table{font-size:44px;font-weight:1000;line-height:1;letter-spacing:-.02em}
    .ktc-meta{display:flex;flex-direction:column;align-items:flex-end;gap:2px}
    .ktc-delivery{display:grid;gap:2px;margin:6px 0;padding:8px 10px;border-radius:12px;background:rgba(56,189,248,.18);color:#bae6fd;font-weight:900}
    .ktc-delivery small{font-size:12px;font-weight:700;color:#e0f2fe}
    .ktc-waiter{font-size:13px;color:#a5b4fc;font-weight:800}
    .ktc-timer{font-weight:1000;font-variant-numeric:tabular-nums;font-size:22px}
    .ktc-timer-green .ktc-timer{color:#86efac}
    .ktc-timer-yellow .ktc-timer{color:#fde68a}
    .ktc-timer-red .ktc-timer{color:#fca5a5}
    .ktc-dot.ktc-timer-green{background:#22c55e}
    .ktc-dot.ktc-timer-yellow{background:#eab308}
    .ktc-dot.ktc-timer-red{background:#ef4444}
    .ktc-items{display:grid;gap:10px}
    .ktc-item{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px;border-radius:14px;background:rgba(255,255,255,.06)}
    .ktc-item.is-ready{opacity:.4}
    .ktc-item-main b{font-size:19px;line-height:1.3;letter-spacing:.01em}
    .ktc-note{margin-top:4px;padding:4px 8px;border-radius:8px;display:inline-block;font-size:14px;font-weight:900;color:#1a1206;background:#ffd166}
    .ktc-ready-pill{padding:6px 14px;border-radius:999px;background:rgba(34,197,94,.22);color:#86efac;font-size:13px;font-weight:1000}
    .ktc-order-note{padding:8px 10px;border-radius:10px;font-size:14px;font-weight:900;color:#1a1206;background:#ffd166}
    .ktc-empty{grid-column:1/-1;text-align:center;padding:40px;color:#8f8aa8}
    .ktc-btn-tab{min-height:40px;padding:0 14px;font-size:13px}
    .ktc-columns{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:14px;align-items:start}
    @media (max-width:900px){.ktc-columns{grid-template-columns:1fr}}
    .ktc-column{display:grid;gap:12px;align-content:start;min-width:0;padding:12px;border-radius:20px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08)}
    .ktc-column h2{margin:0;display:flex;align-items:center;justify-content:space-between;font-size:18px;text-transform:uppercase;letter-spacing:.06em}
    .ktc-count{min-width:40px;height:40px;padding:0 10px;border-radius:999px;display:inline-grid;place-items:center;font-size:20px;font-weight:1000;background:rgba(255,255,255,.1)}
    .ktc-column-nuevo .ktc-count{background:#2563eb}
    .ktc-column-preparando .ktc-count{background:#d97706}
    .ktc-column-listo .ktc-count{background:#16a34a}
    .ktc-card-col .ktc-table{font-size:34px}
    .ktc-card.ktc-card-listo{border-color:#16a34a}
    .ktc-btn-start{border:none;width:100%;min-height:60px;font-size:18px;background:linear-gradient(135deg,#3b82f6,#2563eb)}
    .ktc-btn-deliver{border:none;width:100%;min-height:60px;font-size:18px;background:linear-gradient(135deg,#a855f7,#7c3aed)}
    .ktc-roster{display:grid;gap:10px;padding:16px}
    .ktc-roster-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:14px;align-items:center;padding:14px 16px;border-radius:18px;background:rgba(255,255,255,.05);border:2px solid rgba(255,255,255,.08)}
    @media (max-width:700px){.ktc-roster-row{grid-template-columns:1fr}}
    .ktc-roster-row.ktc-roster-working{border-color:#16a34a}
    .ktc-roster-row.ktc-roster-on_break{border-color:#d97706}
    .ktc-roster-who{display:grid;gap:2px;min-width:0}
    .ktc-roster-who strong{font-size:20px}
    .ktc-roster-who span{font-size:12px;color:#a5b4fc;font-weight:800;text-transform:capitalize}
    .ktc-roster-state{display:grid;gap:4px;justify-items:end}
    .ktc-roster-chip{padding:4px 12px;border-radius:999px;font-size:12px;font-weight:900;background:rgba(255,255,255,.1)}
    .ktc-roster-working .ktc-roster-chip{background:rgba(34,197,94,.22);color:#86efac}
    .ktc-roster-on_break .ktc-roster-chip{background:rgba(217,119,6,.25);color:#fde68a}
    .ktc-roster-time{font-size:20px;font-weight:1000;font-variant-numeric:tabular-nums}
    .ktc-roster-actions{display:flex;gap:8px;flex-wrap:wrap}
    .ktc-roster-btn{min-height:52px;padding:0 18px;font-size:15px;border:none}
    .ktc-roster-iniciar{background:linear-gradient(135deg,#22c55e,#16a34a)}
    .ktc-roster-pausar{background:linear-gradient(135deg,#f59e0b,#d97706)}
    .ktc-roster-salir{background:linear-gradient(135deg,#ef4444,#b91c1c)}
    .ktc-history{display:grid;gap:10px;padding:16px}
    .ktc-history-row{display:grid;gap:4px;padding:14px 16px;border-radius:16px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08)}
    .ktc-history-row strong{font-size:22px}
    .ktc-history-meta{font-size:12px;color:#a5b4fc;font-weight:800}
  `;
  document.head.appendChild(style);
  if (Alerts) Alerts.install();

  if (!companyId) {
    root.innerHTML = `<section style="min-height:100vh;display:grid;place-items:center;background:#080712;color:#fff"><p>Falta company_id en el enlace.</p></section>`;
  } else if (token()) {
    state.screen = "board";
    startPolling();
    render();
  } else {
    render();
  }
})();
