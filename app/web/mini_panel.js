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
  let currentModuleConfig = null;

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


  // CLONEXA_019F_R1_PASSWORD_HELPERS_START
  async function changePasswordRequest(currentPassword, newPassword, confirmPassword) {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-change-password?panel_type=${encodeURIComponent(panelType)}`, {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword
      })
    });
  }
  // CLONEXA_019F_R1_PASSWORD_HELPERS_END


  /* CLONEXA_019H_R1_SAFE_DYNAMIC_MODULES_START */
  const PANEL_TYPE_ALIASES_019H = {
    "sales": "sales",
    "venta": "sales",
    "ventas": "sales",
    "store": "store",
    "stores": "store",
    "tienda": "store",
    "tiendas": "store",
    "inventory": "inventory",
    "inventario": "inventory",
    "logistics": "logistics",
    "logistica": "logistics",
    "field": "logistics",
    "other": "other"
  };

  const MODULE_DEFS_019H = {
    "cotizacion": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "cotizaciones": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "quote": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "quotes": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },

    "notas_o_agenda": { title: "Notas", description: "Registrar notas de seguimiento.", tag: "NOT" },
    "notes": { title: "Notas", description: "Registrar notas de seguimiento.", tag: "NOT" },
    "notas": { title: "Notas", description: "Registrar notas de seguimiento.", tag: "NOT" },

    "registro_venta": { title: "Registro ventas", description: "Reportar ventas cerradas.", tag: "VEN" },
    "registro_ventas": { title: "Registro ventas", description: "Reportar ventas cerradas.", tag: "VEN" },
    "sales_register": { title: "Registro ventas", description: "Reportar ventas cerradas.", tag: "VEN" },
    "sales": { title: "Registro ventas", description: "Reportar ventas cerradas.", tag: "VEN" },

    "day_closing": { title: "Realizar cierre", description: "Enviar cierre diario del vendedor.", tag: "CIE" },
    "cierre_dia": { title: "Realizar cierre", description: "Enviar cierre diario del vendedor.", tag: "CIE" },
    "cierre_de_dia": { title: "Realizar cierre", description: "Enviar cierre diario del vendedor.", tag: "CIE" },
    "commercial_closing": { title: "Realizar cierre", description: "Enviar cierre diario del vendedor.", tag: "CIE" },

    "kpis": { title: "KPIs", description: "Consultar indicadores asignados.", tag: "KPI" },
    "requests": { title: "Solicitudes", description: "Crear y consultar solicitudes operativas.", tag: "REQ" },
    "stores": { title: "Tiendas", description: "Operacion asignada a tiendas.", tag: "STR" },
    "inventory": { title: "Inventario", description: "Consultar y registrar movimientos de inventario.", tag: "INV" },
    "materials": { title: "Materiales", description: "Gestionar materiales asignados.", tag: "MAT" },
    "reports": { title: "Reportes", description: "Consultar reportes operativos asignados.", tag: "REP" },
    "workforce": { title: "Personal", description: "Consultar personal operativo asignado.", tag: "WRK" },
    "gps": { title: "GPS", description: "Consultar ubicacion y control operativo.", tag: "GPS" },
    "crm": { title: "CRM Campo", description: "Consultar operacion en campo.", tag: "CRM" },
    "field": { title: "Operacion en campo", description: "Consultar actividades en campo.", tag: "FLD" },
    "bots": { title: "Bots", description: "Consultar canales automatizados.", tag: "BOT" }
  };

  function normalizePanelType019H(value) {
    const raw = String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    return PANEL_TYPE_ALIASES_019H[raw] || raw || "sales";
  }

  function normalizeModuleCode019H(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function titleFromCode019H(code, moduleNames = {}) {
    const normalized = normalizeModuleCode019H(code);
    const rawName = moduleNames[code] || moduleNames[normalized] || "";
    const clean = String(rawName || normalized || "Modulo").replace(/_/g, " ").trim();
    return clean.replace(/\w\S*/g, (part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase());
  }

  function moduleDefinition019H(code, moduleNames = {}) {
    const normalized = normalizeModuleCode019H(code);
    const def = MODULE_DEFS_019H[normalized];
    if (def) return { ...def, code: normalized };

    const title = titleFromCode019H(normalized, moduleNames);
    return {
      code: normalized,
      title,
      description: "Modulo asignado desde Admin V2.",
      tag: normalized.slice(0, 3).toUpperCase() || "MOD"
    };
  }

  function extractMiniPanelSettings019H(companyModules) {
    const rows = Array.isArray(companyModules) ? companyModules : [];
    const miniRow = rows.find((row) => {
      const code = normalizeModuleCode019H(row?.module?.code || row?.code || row?.module_code || "");
      const name = normalizeModuleCode019H(row?.module?.name || row?.name || "");
      return code === "mini_panel" || name.includes("mini_panel") || name.includes("creacion_mini");
    });

    const settings = miniRow && typeof miniRow.settings === "object" && miniRow.settings ? miniRow.settings : {};

    if (settings.mini_panel_modules && typeof settings.mini_panel_modules === "object") {
      return settings.mini_panel_modules;
    }

    if (settings.panels && typeof settings.panels === "object") {
      return settings;
    }

    return { enabled: false, panels: {}, module_names: {} };
  }

  function panelConfig019H(config, typeValue) {
    const type = normalizePanelType019H(typeValue);
    const panels = config && typeof config.panels === "object" && config.panels ? config.panels : {};
    return panels[type] || panels[`${type}s`] || panels[type === "stores" ? "store" : ""] || {};
  }

  function assignedModuleCodes019H(config, typeValue) {
    const panel = panelConfig019H(config, typeValue);
    const modules = Array.isArray(panel.modules) ? panel.modules : [];
    return modules
      .map((code) => normalizeModuleCode019H(code))
      .filter(Boolean)
      .filter((code, index, arr) => arr.indexOf(code) === index);
  }

  async function loadMiniPanelModuleConfig019H() {
    const empty = { enabled: false, modules: [], module_names: {}, raw: null };
    try {
      if (!companyId) return empty;

      const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/modules?enabled_only=true`, {
        headers: authHeaders()
      });

      const config = extractMiniPanelSettings019H(data);
      const panel = panelConfig019H(config, panelType);
      const codes = assignedModuleCodes019H(config, panelType);
      const moduleNames = config && typeof config.module_names === "object" && config.module_names ? config.module_names : {};

      return {
        enabled: config.enabled === true || panel.enabled === true || codes.length > 0,
        selected_panel: normalizePanelType019H(panelType),
        modules: codes,
        module_names: moduleNames,
        raw: config
      };
    } catch (error) {
      console.warn("CLONEXA 019H-R1 modules fallback:", error);
      return {
        ...empty,
        error: error && error.message ? error.message : String(error)
      };
    }
  }

  function buildDynamicMiniPanelModules019H(moduleConfig) {
    const config = moduleConfig || {};
    const codes = Array.isArray(config.modules) ? config.modules : [];
    return codes
      .map((code) => moduleDefinition019H(code, config.module_names || {}))
      .filter((item) => item && item.code);
  }

  function renderDynamicModulesHtml019H(dynamicModules) {
    if (!dynamicModules.length) {
      return `
        <div class="mp-modules-empty-019h">
          <strong>No hay modulos asignados a este mini panel.</strong>
          <small>Agrega modulos desde Admin V2 - Empresa - Modulos - Modulos para Mini Panel.</small>
        </div>
      `;
    }

    return dynamicModules.map((item) => moduleCard(item.title, item.description, item.tag, item.code)).join("");
  }
  /* CLONEXA_019H_R1_SAFE_DYNAMIC_MODULES_END */



function moduleCard(title, description, tag, code = "") {
    return `
      <button class="mp-module-card" type="button" data-module="${h(code || tag)}" data-module-title="${h(title)}">
        <span>${h(tag)}</span>
        <strong>${h(title)}</strong>
        <small>${h(description)}</small>
      </button>
    `;
  }

  function renderShell(session, operational, moduleConfig = null) {
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
    const isFinished = operational.status === "finished";
    const dynamicModules019H = buildDynamicMiniPanelModules019H(moduleConfig || currentModuleConfig);
    const modulesHtml019H = renderDynamicModulesHtml019H(dynamicModules019H);

    root.innerHTML = `
      <section class="mp-sales-dashboard mp-sales-dashboard-r1 mp-sales-dashboard-r2 mp-sales-dashboard-r3">
        <header class="mp-sales-header mp-sales-header-r1 mp-sales-header-r2 mp-sales-header-r3">
          <section class="mp-header-main mp-header-main-r1 mp-header-main-r2 mp-header-main-r3">
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
          </section>

          <section class="mp-time-panel-r3">
            <div class="mp-mini-panel-title-r3">
              <span>Tiempos</span>
              <strong data-operational-status class="mp-status-pill ${h(operational.status || "active")}">${h(operationalLabel(operational.status))}</strong>
            </div>

            <div class="mp-time-stack-r3">
              <article class="mp-time-card-r3">
                <span>Activo</span>
                <strong data-active-timer>${h(formatSeconds(operational.active_seconds || 0))}</strong>
              </article>

              <article class="mp-time-card-r3 pause">
                <span>Pausa</span>
                <strong data-break-timer>${h(formatSeconds(operational.break_seconds || 0))}</strong>
              </article>
            </div>
          </section>

          <section class="mp-action-panel-r3">
            <div class="mp-mini-panel-title-r3">
              <span>Acciones</span>
            </div>

            <div class="mp-action-stack-r3">
              <button class="mp-button small" type="button" data-action="pause" ${operational.status === "active" ? "" : "disabled"}>Pausa</button>
              <button class="mp-button small secondary" type="button" data-action="resume" ${operational.status === "break" ? "" : "disabled"}>Retomar labores</button>
              <button class="mp-button small danger" type="button" data-action="finish" ${isFinished ? "disabled" : ""}>Finalizar turno</button>
              <button class="mp-button small ghost" type="button" data-change-password>Cambiar contraseÃ±a</button>
            </div>
          </section>
        </header>

        <section class="mp-dashboard-section">
          <div class="mp-section-title">
            <div>
              <div class="mp-kicker">KPIs</div>
              <h2>Ventas y meta</h2>
            </div>
          </div>

          <div class="mp-kpi-grid mp-kpi-grid-r3">
            <article class="mp-kpi-card">
              <span>Total ventas mes</span>
              <strong>${h(formatMoney(salesTotal))}</strong>
              <small>Sumatoria de registros de venta</small>
            </article>

            <article class="mp-kpi-card">
              <span>Llevas vs meta</span>
              <strong>${h(formatMoney(salesTotal))} / ${h(formatMoney(goal))}</strong>
              <div class="mp-progress"><i style="width:${goalPct}%"></i></div>
              <small>${goalPct}% de cumplimiento</small>
            </article>

            <article class="mp-kpi-card notes">
              <span>Notas</span>
              <strong>PrÃ³ximo</strong>
              <small>Notas internas pendientes de activar.</small>
            </article>

            <article class="mp-kpi-card wide">
              <span>Promociones / mensaje</span>
              <strong>Sin promociones activas</strong>
              <small>Este espacio recibirÃ¡ campaÃ±as enviadas desde el CRM madre Mundo Case.</small>
            </article>
          </div>
        </section>

        <section class="mp-dashboard-section mp-modules-section-r1 mp-modules-section-r3">
          <div class="mp-section-title">
            <div>
              <div class="mp-kicker">MÃ³dulos</div>
              <h2>Acciones operativas</h2>
            </div>
          </div>

          <div class="mp-modules-grid mp-modules-grid-r3">
            ${modulesHtml019H}
          </div>

          <div class="mp-message ok" data-panel-message></div>
        </section>

        <div class="mp-modal" data-password-modal hidden>
          <div class="mp-modal-backdrop" data-password-close></div>
          <section class="mp-modal-card">
            <div class="mp-kicker">Seguridad</div>
            <h2>Cambiar contraseÃ±a</h2>
            <p>Actualiza tu clave de acceso al mini panel.</p>

            <form class="mp-form" id="miniPanelPasswordForm">
              <div class="mp-field">
                <label>Clave actual</label>
                <input id="mpCurrentPassword" type="password" autocomplete="current-password" required />
              </div>

              <div class="mp-field">
                <label>Nueva clave</label>
                <input id="mpNewPassword" type="password" autocomplete="new-password" minlength="8" required />
              </div>

              <div class="mp-field">
                <label>Confirmar nueva clave</label>
                <input id="mpConfirmPassword" type="password" autocomplete="new-password" minlength="8" required />
              </div>

              <div class="mp-modal-actions">
                <button class="mp-button secondary" type="button" data-password-close>Cancelar</button>
                <button class="mp-button" type="submit">Guardar contraseÃ±a</button>
              </div>

              <div class="mp-message" id="miniPanelPasswordMessage"></div>
            </form>
          </section>
        </div>
      </section>
    `;

    startTimers(operational);

    root.querySelector("[data-action='pause']")?.addEventListener("click", async () => {
      await runOperationalAction("pause", session);
    });

    root.querySelector("[data-action='resume']")?.addEventListener("click", async () => {
      await runOperationalAction("resume", session);
    });

    root.querySelector("[data-action='finish']")?.addEventListener("click", async () => {
      const msg = root.querySelector("[data-panel-message]");
      try {
        const updated = await operationalAction("finish");
        startTimers(updated.operational_session || updated);
        if (msg) msg.textContent = "Turno finalizado.";
        window.setTimeout(() => {
          clearTimer();
          localStorage.removeItem(storageKey);
          window.location.href = loginUrl();
        }, 900);
      } catch (error) {
        if (msg) {
          msg.classList.remove("ok");
          msg.textContent = error.message || "No fue posible finalizar el turno.";
        }
      }
    });

    const modal = root.querySelector("[data-password-modal]");
    const passwordForm = root.querySelector("#miniPanelPasswordForm");
    const passwordMsg = root.querySelector("#miniPanelPasswordMessage");

    function closePasswordModal() {
      if (modal) modal.hidden = true;
      if (passwordForm) passwordForm.reset();
      if (passwordMsg) {
        passwordMsg.classList.remove("ok");
        passwordMsg.textContent = "";
      }
    }

    root.querySelector("[data-change-password]")?.addEventListener("click", () => {
      if (modal) modal.hidden = false;
    });

    root.querySelectorAll("[data-password-close]").forEach((button) => {
      button.addEventListener("click", closePasswordModal);
    });

    passwordForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const currentPassword = root.querySelector("#mpCurrentPassword")?.value || "";
      const newPassword = root.querySelector("#mpNewPassword")?.value || "";
      const confirmPassword = root.querySelector("#mpConfirmPassword")?.value || "";

      if (passwordMsg) {
        passwordMsg.classList.add("ok");
        passwordMsg.textContent = "Actualizando contraseÃ±a...";
      }

      try {
        await changePasswordRequest(currentPassword, newPassword, confirmPassword);
        if (passwordMsg) {
          passwordMsg.classList.add("ok");
          passwordMsg.textContent = "ContraseÃ±a actualizada.";
        }
        window.setTimeout(closePasswordModal, 900);
      } catch (error) {
        if (passwordMsg) {
          passwordMsg.classList.remove("ok");
          passwordMsg.textContent = error.message || "No fue posible cambiar la contraseÃ±a.";
        }
      }
    });

    root.querySelectorAll("[data-module]").forEach((button) => {
      button.addEventListener("click", () => {
        const msg = root.querySelector("[data-panel-message]");
        if (msg) {
          msg.classList.add("ok");
          msg.textContent = "MÃ³dulo listo para activar en la siguiente fase.";
        }
      });
    });
  }


  async function runOperationalAction(action, session) {
    const msg = root.querySelector("[data-panel-message]");
    try {
      const updated = await operationalAction(action);
      const op = updated.operational_session || updated;
      renderShell(session, op, currentModuleConfig);
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
      currentModuleConfig = await loadMiniPanelModuleConfig019H().catch((error) => {
        console.warn("CLONEXA 019H-R1 config fallback:", error);
        return { enabled: false, modules: [], module_names: {}, error: error?.message || String(error) };
      });
      renderShell(session, operational.operational_session || operational, currentModuleConfig);
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
// CLONEXA_FORCE_BUILD_019H_R1_20260513224440
