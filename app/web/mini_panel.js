(() => {
  "use strict";

  const root = document.getElementById("miniPanelApp");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const panelType = (params.get("type") || params.get("panel_type") || "sales").toLowerCase();
  const isLogin = window.location.pathname.includes("/login");
  const storageKey = `clonexa_mini_panel_token_${companyId}_${panelType}`;

  let timerHandle = null;
  let currentOperational = null;

  const TYPE_LABELS = {
    sales: "Ventas",
    store: "Tiendas",
    stores: "Tiendas",
    inventory: "Inventarios",
    logistics: "LogÃ­stica",
    other: "Otros"
  };

  function h(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function labelType(value) {
    return TYPE_LABELS[value] || value || "Mini Panel";
  }

  function token() {
    return localStorage.getItem(storageKey) || "";
  }

  function authHeaders() {
    const value = token();
    return value ? { Authorization: `Bearer ${value}` } : {};
  }

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || data.message || "Solicitud rechazada.");
    }
    return data;
  }

  function loginUrl() {
    return `/mini-panel/login?company_id=${encodeURIComponent(companyId)}&type=${encodeURIComponent(panelType)}`;
  }

  function shellUrl() {
    return `/mini-panel?company_id=${encodeURIComponent(companyId)}&type=${encodeURIComponent(panelType)}`;
  }

  function formatSeconds(total) {
    const safe = Math.max(0, Math.floor(Number(total || 0)));
    const h = String(Math.floor(safe / 3600)).padStart(2, "0");
    const m = String(Math.floor((safe % 3600) / 60)).padStart(2, "0");
    const s = String(safe % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  function formatMoney(value) {
    const number = Number(value || 0);
    try {
      return new Intl.NumberFormat("es-CO", {
        style: "currency",
        currency: "COP",
        maximumFractionDigits: 0
      }).format(number);
    } catch (_) {
      return `$${Math.round(number).toLocaleString("es-CO")}`;
    }
  }

  function clearTimer() {
    if (timerHandle) {
      window.clearInterval(timerHandle);
      timerHandle = null;
    }
  }

  function setShellMode(enabled) {
    document.body.classList.toggle("mp-shell-body", Boolean(enabled));
  }

  function renderError(message) {
    clearTimer();
    setShellMode(false);
    root.innerHTML = `
      <section class="mp-card">
        <div class="mp-kicker">CLONEXA</div>
        <h1>Mini Panel</h1>
        <p>${h(message || "No fue posible cargar el mini panel.")}</p>
        <button class="mp-button secondary" type="button" data-retry>Reintentar</button>
      </section>
    `;
    root.querySelector("[data-retry]")?.addEventListener("click", () => window.location.reload());
  }

  function renderLogin(message = "") {
    clearTimer();
    setShellMode(false);
    root.innerHTML = `
      <section class="mp-card">
        <div class="mp-kicker">Acceso operativo</div>
        <h1>${h(labelType(panelType))}</h1>
        <p>Ingresa con el usuario y clave generados desde el panel de la empresa.</p>

        <form class="mp-form" id="miniPanelLoginForm">
          <div class="mp-field">
            <label>Usuario</label>
            <input id="miniPanelUsername" autocomplete="username" placeholder="usuario.ventas" required />
          </div>

          <div class="mp-field">
            <label>Clave</label>
            <input id="miniPanelPassword" type="password" autocomplete="current-password" required />
          </div>

          <button class="mp-button" type="submit">Entrar</button>
          <div class="mp-message" id="miniPanelMessage">${h(message)}</div>
        </form>
      </section>
    `;

    const form = document.getElementById("miniPanelLoginForm");
    const msg = document.getElementById("miniPanelMessage");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      msg.textContent = "Validando acceso...";
      msg.classList.add("ok");

      try {
        if (!companyId) throw new Error("Falta company_id en el enlace.");
        const username = document.getElementById("miniPanelUsername").value.trim();
        const password = document.getElementById("miniPanelPassword").value;

        const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password, panel_type: panelType })
        });

        localStorage.setItem(storageKey, data.access_token);
        localStorage.setItem("clonexa_mini_panel_last_session", JSON.stringify({
          company_id: companyId,
          type: panelType,
          at: new Date().toISOString()
        }));

        window.location.href = shellUrl();
      } catch (error) {
        msg.classList.remove("ok");
        msg.textContent = error.message || "No fue posible iniciar sesiÃ³n.";
      }
    });
  }

  function liveValue(kind) {
    if (!currentOperational) return 0;
    const base = Number(currentOperational[`${kind}_seconds`] || 0);
    const syncedAt = Number(currentOperational._synced_at || Date.now());
    const elapsed = Math.max(0, Math.floor((Date.now() - syncedAt) / 1000));

    if (kind === "active" && currentOperational.status === "active") {
      return base + elapsed;
    }
    if (kind === "break" && currentOperational.status === "break") {
      return base + elapsed;
    }
    return base;
  }

  function updateTimers() {
    const activeEl = document.querySelector("[data-active-timer]");
    const breakEl = document.querySelector("[data-break-timer]");
    const paidEl = document.querySelector("[data-paid-timer]");
    const statusEl = document.querySelector("[data-operational-status]");

    if (activeEl) activeEl.textContent = formatSeconds(liveValue("active"));
    if (breakEl) breakEl.textContent = formatSeconds(liveValue("break"));
    if (paidEl) paidEl.textContent = formatSeconds(liveValue("active"));
    if (statusEl && currentOperational) {
      statusEl.textContent = operationalLabel(currentOperational.status);
      statusEl.className = `mp-status-pill ${currentOperational.status || "active"}`;
    }
  }

  function startTimers(operational) {
    clearTimer();
    currentOperational = {
      ...(operational || {}),
      _synced_at: Date.now()
    };
    updateTimers();
    timerHandle = window.setInterval(updateTimers, 1000);
  }

  function operationalLabel(status) {
    if (status === "break") return "En pausa";
    if (status === "finished") return "Finalizado";
    return "Activo";
  }

  async function loadOperationalSession() {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-operational-session?panel_type=${encodeURIComponent(panelType)}`, {
      headers: authHeaders()
    });
  }

  async function operationalAction(action) {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-operational-session/${action}?panel_type=${encodeURIComponent(panelType)}`, {
      method: "POST",
      headers: authHeaders()
    });
  }

  function moduleCard(title, description, tag) {
    return `
      <button class="mp-module-card" type="button" data-module="${h(tag)}">
        <span>${h(tag)}</span>
        <strong>${h(title)}</strong>
        <small>${h(description)}</small>
      </button>
    `;
  }

  function renderShell(session, operational) {
    setShellMode(true);

    const company = session.company || {};
    const user = session.user || {};
    const employee = session.employee || {};
    const mini = session.mini_panel || {};
    const kpis = operational.kpis || {};
    const employeeName = employee.full_name || user.full_name || "usuario";
    const employeeRole = employee.role || user.role || "operador";
    const companyName = company.name || company.slug || "Empresa";
    const locationLabel = operational.location_label || "Trabajo";
    const salesTotal = Number(kpis.monthly_sales_total || 0);
    const goal = Number(kpis.monthly_goal || 0);
    const goalPct = goal > 0 ? Math.min(100, Math.round((salesTotal / goal) * 100)) : 0;

    root.innerHTML = `
      <section class="mp-sales-dashboard">
        <header class="mp-sales-header">
          <div class="mp-header-main">
            <div class="mp-kicker">Mini Panel ${h(mini.type_label || labelType(panelType))}</div>
            <h1>${h(companyName)}</h1>
            <p>Portal operativo personalizado para ${h(employeeName)}.</p>

            <div class="mp-meta compact">
              <span class="mp-chip">Vendedor: ${h(employeeName)}</span>
              <span class="mp-chip">Rol: ${h(employeeRole)}</span>
              <span class="mp-chip">Empresa: ${h(company.slug || companyName)}</span>
              <span class="mp-chip">UbicaciÃ³n: ${h(locationLabel)}</span>
              <span class="mp-chip">Usuario: ${h(mini.username || user.email || "â€”")}</span>
            </div>
          </div>

          <aside class="mp-state-panel">
            <div class="mp-state-row">
              <span>Estado</span>
              <strong data-operational-status class="mp-status-pill ${h(operational.status || "active")}">${h(operationalLabel(operational.status))}</strong>
            </div>

            <div class="mp-actions">
              <button class="mp-button small" type="button" data-action="pause" ${operational.status === "active" ? "" : "disabled"}>Pausa</button>
              <button class="mp-button small secondary" type="button" data-action="resume" ${operational.status === "break" ? "" : "disabled"}>Retomar labores</button>
              <button class="mp-button small danger" type="button" data-action="finish" ${operational.status === "finished" ? "disabled" : ""}>Finalizar sesiÃ³n</button>
            </div>

            <button class="mp-button ghost" type="button" data-logout>Cerrar sesiÃ³n</button>
          </aside>
        </header>

        <section class="mp-time-grid">
          <article class="mp-time-card">
            <span>Tiempo activo</span>
            <strong data-active-timer>${h(formatSeconds(operational.active_seconds || 0))}</strong>
            <small>Tiempo pago acumulado</small>
          </article>

          <article class="mp-time-card pause">
            <span>Tiempo en pausa</span>
            <strong data-break-timer>${h(formatSeconds(operational.break_seconds || 0))}</strong>
            <small>No suma al tiempo pago</small>
          </article>

          <article class="mp-time-card">
            <span>Tiempo pago</span>
            <strong data-paid-timer>${h(formatSeconds(operational.active_seconds || 0))}</strong>
            <small>Activo sin pausas</small>
          </article>

          <article class="mp-time-card">
            <span>Inicio</span>
            <strong>${h(operational.started_label || "Ahora")}</strong>
            <small>${h(locationLabel)}</small>
          </article>
        </section>

        <section class="mp-dashboard-section">
          <div class="mp-section-title">
            <div>
              <div class="mp-kicker">KPIs</div>
              <h2>Ventas y meta</h2>
            </div>
          </div>

          <div class="mp-kpi-grid">
            <article class="mp-kpi-card">
              <span>Total ventas mes</span>
              <strong>${h(formatMoney(salesTotal))}</strong>
              <small>Consolidado del vendedor</small>
            </article>

            <article class="mp-kpi-card">
              <span>Llevas vs meta</span>
              <strong>${h(formatMoney(salesTotal))} / ${h(formatMoney(goal))}</strong>
              <div class="mp-progress"><i style="width:${goalPct}%"></i></div>
              <small>${goalPct}% de cumplimiento</small>
            </article>

            <article class="mp-kpi-card wide">
              <span>Promociones</span>
              <strong>Sin promociones activas</strong>
              <small>Este espacio recibirÃ¡ campaÃ±as enviadas desde el CRM madre Mundo Case.</small>
            </article>
          </div>
        </section>

        <section class="mp-dashboard-section">
          <div class="mp-section-title">
            <div>
              <div class="mp-kicker">MÃ³dulos</div>
              <h2>Acciones operativas</h2>
            </div>
          </div>

          <div class="mp-modules-grid">
            ${moduleCard("CotizaciÃ³n", "Crear cotizaciones para clientes.", "COT")}
            ${moduleCard("Notas", "Registrar notas de seguimiento.", "NOT")}
            ${moduleCard("Registro de venta", "Reportar ventas cerradas.", "VEN")}
            ${moduleCard("Cierre dÃ­a", "Enviar cierre diario del vendedor.", "CIE")}
          </div>

          <div class="mp-message ok" data-panel-message></div>
        </section>
      </section>
    `;

    startTimers(operational);

    root.querySelector("[data-logout]")?.addEventListener("click", () => {
      clearTimer();
      localStorage.removeItem(storageKey);
      window.location.href = loginUrl();
    });

    root.querySelector("[data-action='pause']")?.addEventListener("click", async () => {
      await runOperationalAction("pause", session);
    });

    root.querySelector("[data-action='resume']")?.addEventListener("click", async () => {
      await runOperationalAction("resume", session);
    });

    root.querySelector("[data-action='finish']")?.addEventListener("click", async () => {
      const updated = await operationalAction("finish");
      startTimers(updated.operational_session || updated);
      const msg = root.querySelector("[data-panel-message]");
      if (msg) msg.textContent = "SesiÃ³n operativa finalizada.";
      window.setTimeout(() => {
        clearTimer();
        localStorage.removeItem(storageKey);
        window.location.href = loginUrl();
      }, 900);
    });

    root.querySelectorAll("[data-module]").forEach((button) => {
      button.addEventListener("click", () => {
        const msg = root.querySelector("[data-panel-message]");
        if (msg) msg.textContent = "MÃ³dulo listo para activar en la siguiente fase.";
      });
    });
  }

  async function runOperationalAction(action, session) {
    const msg = root.querySelector("[data-panel-message]");
    try {
      const updated = await operationalAction(action);
      const op = updated.operational_session || updated;
      renderShell(session, op);
    } catch (error) {
      if (msg) {
        msg.classList.remove("ok");
        msg.textContent = error.message || "No fue posible actualizar la sesiÃ³n.";
      }
    }
  }

  async function bootShell() {
    if (!companyId) {
      renderError("El enlace no contiene company_id.");
      return;
    }

    const savedToken = token();
    if (!savedToken) {
      window.location.href = loginUrl();
      return;
    }

    try {
      const session = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-session?panel_type=${encodeURIComponent(panelType)}`, {
        headers: { Authorization: `Bearer ${savedToken}` }
      });

      const operational = await loadOperationalSession();
      renderShell(session, operational.operational_session || operational);
    } catch (error) {
      localStorage.removeItem(storageKey);
      renderLogin(error.message || "SesiÃ³n expirada. Ingresa de nuevo.");
    }
  }

  if (isLogin) {
    renderLogin();
  } else {
    bootShell();
  }
})();
