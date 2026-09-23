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
  };

  const COLUMNS = [
    { key: "nuevo", title: "Pedido nuevo" },
    { key: "preparando", title: "Preparando" },
    { key: "listo", title: "Listo" },
  ];

  let pollHandle = null;

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
      if (response.status === 401 && /otro dispositivo/i.test(String(message))) {
        stopPolling();
        setToken("");
        state.screen = "login";
        state.error = "Tu sesión se abrió en otro dispositivo.";
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
      state.columns = boardColumns(data);
      if (state.view === "board" || !state.columnsEnabled) render();
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
          ${state.columnsEnabled ? `
            <button class="ktc-btn ktc-btn-tab" type="button" data-ktc-view="${state.view === "history" ? "board" : "history"}">
              ${state.view === "history" ? "Volver al tablero" : "Entregadas hoy"}
            </button>` : ""}
          <button class="ktc-logout" type="button" data-ktc-logout aria-label="Salir">⏻</button>
        </header>
        ${state.columnsEnabled
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
      state.view = viewBtn.getAttribute("data-ktc-view") === "history" ? "history" : "board";
      if (state.view === "history") loadHistory();
      else render();
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
    .ktc-history{display:grid;gap:10px;padding:16px}
    .ktc-history-row{display:grid;gap:4px;padding:14px 16px;border-radius:16px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08)}
    .ktc-history-row strong{font-size:22px}
    .ktc-history-meta{font-size:12px;color:#a5b4fc;font-weight:800}
  `;
  document.head.appendChild(style);

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
