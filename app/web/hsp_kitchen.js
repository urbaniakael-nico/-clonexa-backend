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
  };

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
      render();
    } catch (_) {
      // keep last board on transient errors; the 401 handler already redirects on session kick
    }
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

  function comandaCard(comanda) {
    const minutes = minutesOpen(comanda.created_at);
    const cls = timerClass(minutes);
    const waiterName = comanda.waiter && comanda.waiter.name ? comanda.waiter.name : "";
    const allReady = (comanda.items || []).every((item) => item.ready);
    return `
      <article class="ktc-card ${cls}">
        <header>
          <div>
            <div class="ktc-table">${h(comanda.table_number || "Mesa")}</div>
            ${waiterName ? `<div class="ktc-waiter">Mesero: ${h(waiterName)}</div>` : ""}
          </div>
          <div class="ktc-timer">${Math.floor(minutes)} min</div>
        </header>
        <div class="ktc-items">
          ${(comanda.items || []).map((item) => `
            <div class="ktc-item ${item.ready ? "is-ready" : ""}">
              <div>
                <b>${h(item.quantity)} x ${h(item.name)}</b>
                ${item.observations ? `<div class="ktc-note">${h(item.observations)}</div>` : ""}
                ${(item.quick_notes || []).length ? `<div class="ktc-note">${item.quick_notes.map(h).join(" · ")}</div>` : ""}
              </div>
              ${item.ready
                ? `<span class="ktc-ready-pill">Listo</span>`
                : `<button type="button" class="ktc-btn ktc-btn-mini" data-ktc-item-ready="${h(comanda.order_id)}" data-item-id="${h(item.id)}">Listo</button>`}
            </div>`).join("")}
        </div>
        ${comanda.notes ? `<div class="ktc-order-note">${h(comanda.notes)}</div>` : ""}
        <button type="button" class="ktc-btn ktc-btn-primary" data-ktc-order-ready="${h(comanda.order_id)}" ${allReady ? "" : "disabled"}>
          Comanda lista
        </button>
      </article>`;
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
          <button class="ktc-logout" type="button" data-ktc-logout aria-label="Salir">⏻</button>
        </header>
        <div class="ktc-board">
          ${state.comandas.map(comandaCard).join("") || `<div class="ktc-empty">Sin comandas pendientes en tus estaciones.</div>`}
        </div>
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
    .ktc-btn{min-height:44px;border-radius:14px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:14px;font-weight:900;cursor:pointer}
    .ktc-btn-primary{border:none;background:linear-gradient(135deg,#22c55e,#16a34a);width:100%}
    .ktc-btn-primary:disabled{opacity:.35;cursor:not-allowed}
    .ktc-btn-mini{min-height:34px;padding:0 12px}
    .ktc-alert{margin-top:10px;padding:10px 12px;border-radius:12px;background:rgba(239,68,68,.16);color:#fecaca;font-size:13px;font-weight:800}
    .ktc-alert-floating{position:fixed;left:16px;right:16px;bottom:16px;z-index:50}
    .ktc-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;padding:16px;background:rgba(8,7,18,.92);backdrop-filter:blur(6px);border-bottom:1px solid rgba(255,255,255,.08);flex-wrap:wrap}
    .ktc-header h1{margin:0;font-size:20px}
    .ktc-legend{flex:1;display:flex;gap:10px;align-items:center;font-size:11px;color:#c9c3e6;flex-wrap:wrap}
    .ktc-dot{width:10px;height:10px;border-radius:50%;display:inline-block}
    .ktc-logout{width:40px;height:40px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:18px}
    .ktc-board{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;padding:16px}
    .ktc-card{border-radius:20px;padding:14px;display:grid;gap:10px;background:rgba(3,7,18,.5);border:2px solid rgba(255,255,255,.1)}
    .ktc-card.ktc-timer-green{border-color:#22c55e}
    .ktc-card.ktc-timer-yellow{border-color:#eab308}
    .ktc-card.ktc-timer-red{border-color:#ef4444;animation:ktcPulse 1.4s ease-in-out infinite}
    @keyframes ktcPulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.4)}50%{box-shadow:0 0 0 8px rgba(239,68,68,0)}}
    .ktc-card header{display:flex;justify-content:space-between;align-items:start}
    .ktc-table{font-size:20px;font-weight:900}
    .ktc-waiter{font-size:12px;color:#a5b4fc}
    .ktc-timer{font-weight:900;font-variant-numeric:tabular-nums}
    .ktc-timer-green .ktc-timer,.ktc-dot.ktc-timer-green{color:#86efac;background:#22c55e}
    .ktc-timer-yellow .ktc-timer,.ktc-dot.ktc-timer-yellow{color:#fde68a;background:#eab308}
    .ktc-timer-red .ktc-timer,.ktc-dot.ktc-timer-red{color:#fca5a5;background:#ef4444}
    .ktc-items{display:grid;gap:8px}
    .ktc-item{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px;border-radius:14px;background:rgba(255,255,255,.05)}
    .ktc-item.is-ready{opacity:.5}
    .ktc-note{font-size:12px;color:#ffb3d9}
    .ktc-ready-pill{padding:4px 10px;border-radius:999px;background:rgba(34,197,94,.2);color:#86efac;font-size:11px;font-weight:900}
    .ktc-order-note{font-size:12px;color:#c9c3e6;font-style:italic}
    .ktc-empty{grid-column:1/-1;text-align:center;padding:40px;color:#8f8aa8}
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
