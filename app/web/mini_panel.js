(() => {
  "use strict";

  const root = document.getElementById("miniPanelApp");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const panelType = (params.get("type") || params.get("panel_type") || "sales").toLowerCase();
  const isLogin = window.location.pathname.includes("/login");
  const storageKey = `clonexa_mini_panel_token_${companyId}_${panelType}`;

  const TYPE_LABELS = {
    sales: "Ventas",
    store: "Tiendas",
    stores: "Tiendas",
    inventory: "Inventarios",
    logistics: "Logística",
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

  function renderError(message) {
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
        msg.textContent = error.message || "No fue posible iniciar sesión.";
      }
    });
  }

  function renderShell(session) {
    const company = session.company || {};
    const user = session.user || {};
    const employee = session.employee || {};
    const mini = session.mini_panel || {};

    root.innerHTML = `
      <section class="mp-shell">
        <div class="mp-topbar">
          <div>
            <div class="mp-kicker">Mini Panel ${h(mini.type_label || labelType(panelType))}</div>
            <h1>${h(company.name || "Empresa")}</h1>
            <p>Portal operativo personalizado para ${h(user.full_name || employee.full_name || "usuario")}.</p>
          </div>
          <button class="mp-button secondary" type="button" data-logout>Cerrar sesión</button>
        </div>

        <div class="mp-meta">
          <span class="mp-chip">Tipo: ${h(mini.type_label || labelType(panelType))}</span>
          <span class="mp-chip">Estado: ${h(user.status || "activo")}</span>
          <span class="mp-chip">Usuario: ${h(mini.username || user.email || "—")}</span>
        </div>

        <div class="mp-grid">
          <div class="mp-tile">
            <span>Colaborador</span>
            <strong>${h(employee.full_name || user.full_name || "—")}</strong>
          </div>

          <div class="mp-tile">
            <span>Rol</span>
            <strong>${h(employee.role || user.role || "—")}</strong>
          </div>

          <div class="mp-tile">
            <span>Empresa</span>
            <strong>${h(company.slug || company.name || "—")}</strong>
          </div>

          <div class="mp-tile">
            <span>Estado del acceso</span>
            <strong>Activo</strong>
          </div>
        </div>

        <div class="mp-card" style="max-width:none;margin-top:18px">
          <div class="mp-kicker">Siguiente fase</div>
          <h2>Panel operativo listo</h2>
          <p>En la siguiente etapa se activan jornada, pausa, cotizaciones y cierre diario para este mini panel.</p>
        </div>
      </section>
    `;

    root.querySelector("[data-logout]")?.addEventListener("click", () => {
      localStorage.removeItem(storageKey);
      window.location.href = loginUrl();
    });
  }

  async function bootShell() {
    if (!companyId) {
      renderError("El enlace no contiene company_id.");
      return;
    }

    const token = localStorage.getItem(storageKey);
    if (!token) {
      window.location.href = loginUrl();
      return;
    }

    try {
      const session = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-session?panel_type=${encodeURIComponent(panelType)}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      renderShell(session);
    } catch (error) {
      localStorage.removeItem(storageKey);
      renderLogin(error.message || "Sesión expirada. Ingresa de nuevo.");
    }
  }

  if (isLogin) {
    renderLogin();
  } else {
    bootShell();
  }
})();
