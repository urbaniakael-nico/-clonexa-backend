(() => {
  const API = "/api/v1";

  const state = {
    health: null,
    companies: [],
    packages: [],
    packageMiniPanelSettings: new Map(),
    modules: [],
    companyModules: new Map(),
    companyUsers: new Map(),
    companyExperience: new Map(),
    companyBotConfigs: new Map(),
    selectedCompanyId: null,
    activeView: "dashboard",
    activeDetailTab: "resumen",
    companyFilter: "visible",
    lastRefresh: null,
    errors: [],
  };

  const el = (selector) => document.querySelector(selector);
  const els = (selector) => Array.from(document.querySelectorAll(selector));

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const truncate = (value, size = 10) => {
    const text = String(value || "");
    return text.length > size ? `${text.slice(0, size)}Ã¢â‚¬Â¦` : text;
  };

  const localTime = () => new Date().toLocaleTimeString("es-CO", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });

  const safeArray = (value) => {
    if (Array.isArray(value)) return value;
    if (!value || typeof value !== "object") return [];
    const keys = ["items", "data", "results", "companies", "packages", "modules", "users", "records"];
    for (const key of keys) {
      if (Array.isArray(value[key])) return value[key];
    }
    return [];
  };

  async function apiRequest(path, options = {}) {
    const response = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });

    const contentType = response.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");
    const payload = isJson ? await response.json().catch(() => ({})) : await response.text();

    if (!response.ok) {
      const detail = typeof payload === "object"
        ? (payload.detail || payload.error || JSON.stringify(payload))
        : payload;
      throw new Error(detail || `HTTP ${response.status}`);
    }

    return payload;
  }

  const apiGet = (path) => apiRequest(path);
  const apiPost = (path, body = {}) => apiRequest(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
  const apiPut = (path, body = {}) => apiRequest(path, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  const apiPatch = (path, body = {}) => apiRequest(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

  function setText(idOrSelector, value) {
    const node = idOrSelector.startsWith("#") || idOrSelector.startsWith(".")
      ? el(idOrSelector)
      : document.getElementById(idOrSelector);
    if (node) node.textContent = value ?? "Ã¢â‚¬â€";
  }

  function showToast(message, type = "ok") {
    const node = el("#toast");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
    node.style.borderColor = type === "error" ? "rgba(255,77,109,.4)" : "rgba(0,255,136,.35)";
    window.clearTimeout(showToast._timer);
    showToast._timer = window.setTimeout(() => {
      node.hidden = true;
    }, 4200);
  }

  function showAdminError(message) {
    const node = el("#globalAlert");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
  }

  function clearAdminError() {
    const node = el("#globalAlert");
    if (!node) return;
    node.hidden = true;
    node.textContent = "";
  }

  function normalizeCompany(raw) {
    return {
      ...raw,
      id: raw.id || raw.company_id || raw.uuid,
      name: raw.name || raw.company_name || raw.nombre || "Empresa sin nombre",
      slug: raw.slug || raw.company_slug || raw.code || "",
      status: raw.status || raw.estado || "active",
      plan: raw.plan || raw.package_code || raw.package || raw.subscription_plan || "Ã¢â‚¬â€",
      timezone: raw.timezone || raw.tz || "America/Bogota",
    };
  }


  function companyStatus(company) {
    return String(company?.status || "active").toLowerCase();
  }

  function isArchivedCompany(company) {
    const s = companyStatus(company);
    return s === "deleted" || s === "archived";
  }

  function isInactiveCompany(company) {
    return companyStatus(company) === "inactive";
  }

  function filteredCompanies() {
    const filter = state.companyFilter || "visible";
    if (filter === "active") return state.companies.filter((c) => companyStatus(c) === "active");
    if (filter === "inactive") return state.companies.filter((c) => companyStatus(c) === "inactive");
    if (filter === "archived") return state.companies.filter(isArchivedCompany);
    if (filter === "all") return state.companies;
    return state.companies.filter((c) => !isArchivedCompany(c));
  }

  function ensureCompanyLifecycleFilters() {
    const body = el("#companiesTableBody");
    const table = body?.closest("table");
    if (!body || !table || document.getElementById("companyLifecycleFilters")) return;

    const controls = document.createElement("div");
    controls.id = "companyLifecycleFilters";
    controls.className = "cx-actions";
    controls.style.margin = "0 0 14px 0";
    controls.innerHTML = `
      <span class="cx-badge cx-badge-primary">Filtro empresas</span>
      <button class="cx-btn cx-btn-small" data-company-filter="visible" type="button">Activas + inactivas</button>
      <button class="cx-btn cx-btn-small" data-company-filter="active" type="button">Activas</button>
      <button class="cx-btn cx-btn-small" data-company-filter="inactive" type="button">Inactivas</button>
      <button class="cx-btn cx-btn-small" data-company-filter="archived" type="button">Archivadas</button>
      <button class="cx-btn cx-btn-small" data-company-filter="all" type="button">Todas</button>
    `;
    table.parentElement?.insertBefore(controls, table);
  }

  function renderCompanyLifecycleActions(company, compact = false) {
    const status = companyStatus(company);
    const archived = isArchivedCompany(company);
    const small = compact ? "cx-btn-small" : "";
    const archiveLabel = compact ? "Eliminar" : "Eliminar empresa";
    if (archived) {
      return `
        <button class="cx-btn ${small}" data-company-status="${escapeHtml(company.id)}" data-status="active" type="button">Reactivar</button>
      `;
    }

    const toggle = status === "active"
      ? `<button class="cx-btn ${small}" data-company-status="${escapeHtml(company.id)}" data-status="inactive" type="button">Desactivar</button>`
      : `<button class="cx-btn ${small}" data-company-status="${escapeHtml(company.id)}" data-status="active" type="button">Reactivar</button>`;

    return `
      ${toggle}
      <button class="cx-btn ${small}" data-archive-company="${escapeHtml(company.id)}" type="button">${archiveLabel}</button>
    `;
  }

  function normalizePackage(raw) {
    return {
      ...raw,
      id: raw.id || raw.package_id || raw.uuid,
      code: raw.code || raw.package_code || "",
      name: raw.name || raw.package_name || raw.nombre || raw.code || "Paquete",
      description: raw.description || raw.descripción || "",
      is_active: raw.is_active !== false && raw.status !== "inactive",
      modules: safeArray(raw.modules || raw.package_modules || raw.packageModules),
    };
  }


  function normalizeModule(input = {}) {
    const source = input.module && typeof input.module === "object" ? input.module : input;
    const code = String(source.code || source.module_code || input.module_code || input.code || "").trim();

    const meta = typeof cxModuleMeta === "function"
      ? cxModuleMeta({ ...source, code })
      : { name: source.name || code || "Módulo", description: source.description || "", category: source.category || "general" };

    return {
      id: source.id || input.module_id || input.id || code,
      company_module_id: input.module ? input.id : null,
      module_id: input.module_id || source.id || input.id || null,
      code,
      name: meta.name || source.name || code || "Módulo",
      description: source.description || input.description || meta.description || "",
      category: source.category || input.category || meta.category || "general",
      is_active: source.is_active !== false,
      enabled: input.enabled !== false,
      settings: input.settings || source.settings || {},
      activated_at: input.activated_at || null,
      raw: input,
    };
  }

  function normalizeUser(raw) {
    return {
      ...raw,
      id: raw.id || raw.user_id || raw.uuid,
      email: raw.email || "",
      full_name: raw.full_name || raw.name || raw.nombre || "",
      role: raw.role || "company_admin",
      status: raw.status || "active",
      must_change_password: Boolean(raw.must_change_password),
      failed_login_attempts: Number(raw.failed_login_attempts || 0),
      locked_until: raw.locked_until || null,
      last_login_at: raw.last_login_at || null,
      last_password_reset_at: raw.last_password_reset_at || null,
      created_at: raw.created_at || null,
    };
  }

  function isFutureDate(value) {
    if (!value) return false;
    const date = new Date(value);
    return !Number.isNaN(date.getTime()) && date.getTime() > Date.now();
  }

  function ownerAccessInfo(users) {
    if (!Array.isArray(users)) {
      return { unavailable: true, owner: null, companyAdmins: [], status: "NO DISPONIBLE", level: "warn" };
    }

    const active = users.filter((user) => String(user.status || "").toLowerCase() === "active");
    const companyAdmins = users.filter((user) => String(user.role || "").toLowerCase() === "company_admin");
    const owner = (
      companyAdmins.find((user) => String(user.status || "").toLowerCase() === "active")
      || companyAdmins[0]
      || active[0]
      || users[0]
      || null
    );

    if (!owner) {
      return { owner: null, companyAdmins, status: "FALTA", level: "danger" };
    }

    const status = String(owner.status || "active").toLowerCase();
    const locked = isFutureDate(owner.locked_until);
    if (companyAdmins.length > 1) return { owner, companyAdmins, status: "MÃƒÅ¡LTIPLE", level: "warn" };
    if (locked || status === "blocked") return { owner, companyAdmins, status: "BLOQUEADO", level: "danger" };
    if (status === "inactive") return { owner, companyAdmins, status: "INACTIVO", level: "danger" };
    return { owner, companyAdmins, status: "OK", level: "ok" };
  }

  function ownerAccessBadge(users) {
    const info = ownerAccessInfo(users);
    const cls = info.level === "ok" ? "cx-badge-live" : info.level === "danger" ? "cx-badge-danger" : "cx-badge-primary";
    return `<span class="cx-badge ${cls}">${escapeHtml(info.status)}</span>`;
  }

  function moduleCodesForCompany(companyId) {
    const rows = state.companyModules.get(companyId) || [];
    return rows.map(normalizeModule).filter((m) => m.enabled !== false).map((m) => m.code).filter(Boolean);
  }

  function packageForCompany(company) {
    if (!company) return "Ã¢â‚¬â€";

    const direct = company.package_code || company.package_name || company.package || company.plan_name;
    if (direct && direct !== "Ã¢â‚¬â€") return direct;

    const activeCodes = new Set(moduleCodesForCompany(company.id));
    if (!activeCodes.size) return company.plan || "Ã¢â‚¬â€";

    let best = null;
    let bestScore = 0;

    for (const pkg of state.packages.map(normalizePackage)) {
      const pkgModules = pkg.modules
        .map((m) => typeof m === "string" ? m : (m.code || m.module_code || m.name))
        .filter(Boolean);

      if (!pkgModules.length) continue;

      const score = pkgModules.filter((code) => activeCodes.has(code)).length;
      if (score > bestScore) {
        best = pkg;
        bestScore = score;
      }
    }

    return best ? best.code || best.name : (company.plan || "Ã¢â‚¬â€");
  }

  async function loadHealth() {
    try {
      const health = await apiGet("/health").catch(() => apiGet(`${API}/health`));
      state.health = health || { ok: true };
      setApiStatus(true);
      return state.health;
    } catch (error) {
      state.health = { ok: false, error: error.message };
      setApiStatus(false);
      throw error;
    }
  }

  async function loadCompanies() {
    const data = await apiGet(`${API}/companies`);
    state.companies = safeArray(data).map(normalizeCompany);
    return state.companies;
  }

  async function loadModules() {
    const data = await apiGet(`${API}/modules`);
    state.modules = safeArray(data).map(normalizeModule);
    return state.modules;
  }

  async function loadPackages() {
    const data = await apiGet(`${API}/packages`);
    const rows = safeArray(data).map(normalizePackage);

    const detailed = await Promise.all(rows.map(async (pkg) => {
      if (!pkg.id) return pkg;
      try {
        const detail = await apiGet(`${API}/packages/${pkg.id}`);
        return normalizePackage(detail);
      } catch (_) {
        return pkg;
      }
    }));

    state.packages = detailed;
    return state.packages;
  }


  async function loadCompanyModules(companyId) {
    if (!companyId) return [];
    try {
      const data = await apiGet(`${API}/companies/${companyId}/modules?enabled_only=false`);
      const rows = safeArray(data).map(normalizeModule);
      state.companyModules.set(companyId, rows);
      return rows;
    } catch (error) {
      state.companyModules.set(companyId, []);
      return [];
    }
  }

  async function loadCompanyUsers(companyId) {
    if (!companyId) return [];
    try {
      const data = await apiGet(`${API}/companies/${companyId}/users`);
      const rows = safeArray(data).map(normalizeUser);
      state.companyUsers.set(companyId, rows);
      return rows;
    } catch (error) {
      state.companyUsers.set(companyId, { unavailable: true, error: error.message });
      return [];
    }
  }

  async function loadCompanyExperience(companyId) {
    if (!companyId) return null;
    try {
      const data = await apiGet(`${API}/companies/${companyId}/experience`);
      state.companyExperience.set(companyId, data || {});
      return data || {};
    } catch (error) {
      state.companyExperience.set(companyId, { unavailable: true, error: error.message });
      return null;
    }
  }

  const botConfigKey = (companyId, channel = "telegram") => `${companyId}:${channel}`;

  function telegramConfig(companyId) {
    return state.companyBotConfigs.get(botConfigKey(companyId, "telegram")) || null;
  }

  async function loadTelegramBotConfig(companyId, force = false) {
    if (!companyId) return null;
    const key = botConfigKey(companyId, "telegram");
    if (!force && state.companyBotConfigs.has(key)) {
      return state.companyBotConfigs.get(key);
    }

    try {
      const baseConfig = await apiGet(`${API}/bots/companies/${companyId}/telegram`);
      let data = baseConfig || {};

      try {
        const webhookStatus = await apiGet(`${API}/company-bots-v1/companies/${companyId}/telegram/status`);
        data = { ...data, ...(webhookStatus || {}) };
      } catch (statusError) {
        // El endpoint dedicado puede no existir en instalaciones antiguas.
      }

      state.companyBotConfigs.set(key, data || {});
      return data || {};
    } catch (error) {
      const fallback = {
        configured: false,
        status: "error",
        last_error: error.message,
      };
      state.companyBotConfigs.set(key, fallback);
      return fallback;
    }
  }

  function telegramBotStatusBadge(config) {
    const status = String(config?.status || (config?.configured ? "configured" : "not_configured"));
    const label = config?.configured
      ? (status === "active" ? "Conectado" : status === "error" ? "Error" : status === "inactive" ? "Inactivo" : "Configurado")
      : "Sin configurar";
    const cls = status === "active" ? "cx-badge-live" : status === "error" ? "cx-badge-danger" : config?.configured ? "cx-badge-primary" : "";
    return `<span class="cx-badge ${cls}">${escapeHtml(label)}</span>`;
  }


  function botFlowLabel(value) {
    const code = String(value || "base").toLowerCase();

    const labels = {
      base: "Base / Workforce",
      velvet_references: "Velvet / Referencias producción",
      field_operations: "Campo / GPS / Materiales",
      retail_sales: "Retail / Ventas",
      hospitality_orders: "Hospitality / Pedidos",
    };

    return labels[code] || code;
  }

  function suggestedBotFlow(company) {
    const codes = moduleCodesForCompany(company.id);

    if (codes.includes("references") && codes.includes("workforce")) return "velvet_references";
    if (codes.includes("gps") || codes.includes("materials") || codes.includes("field")) return "field_operations";
    if (codes.includes("sales") || codes.includes("stores") || codes.includes("retail")) return "retail_sales";
    if (codes.includes("hospitality") || codes.includes("orders") || codes.includes("tables")) return "hospitality_orders";

    return "base";
  }

  function botFlowOptions(company, selected) {
    const codes = moduleCodesForCompany(company.id);
    const options = [
      ["base", "Base / Workforce"],
    ];

    if (codes.includes("references") && codes.includes("workforce")) {
      options.push(["velvet_references", "Velvet / Referencias producción"]);
    }

    if (codes.includes("gps") || codes.includes("materials") || codes.includes("field")) {
      options.push(["field_operations", "Campo / GPS / Materiales"]);
    }

    if (codes.includes("sales") || codes.includes("stores") || codes.includes("retail")) {
      options.push(["retail_sales", "Retail / Ventas"]);
    }

    if (codes.includes("hospitality") || codes.includes("orders") || codes.includes("tables")) {
      options.push(["hospitality_orders", "Hospitality / Pedidos"]);
    }

    const unique = new Map(options);
    const selectedValue = selected || suggestedBotFlow(company);

    return [...unique.entries()]
      .map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === selectedValue ? "selected" : ""}>${escapeHtml(label)}</option>`)
      .join("");
  }

  function botWebhookLabel(config) {
    const mode = String(config?.webhook_mode || "").toLowerCase();

    if (mode === "dedicated") return "Webhook dedicado";
    if (config?.configured) return "Pendiente de activar";

    return "Sin configurar";
  }


  function renderCompanyAccessPanel(company) {
    const config = telegramConfig(company.id);
    const botModuleCodes = moduleCodesForCompany(company.id);
    const botsEnabled = botModuleCodes.includes("bots");
    const botFlowCode = config?.flow_code || suggestedBotFlow(company);
    const botWebhookMode = botWebhookLabel(config);
    const botWebhookUrl = config?.webhook_url || "";
    const botStatus = config?.loading
      ? `<span class="cx-badge">Cargando...</span>`
      : telegramBotStatusBadge(config);

    return `
      <div class="cx-cards-grid" style="margin-bottom:18px">
        <a class="cx-package-card" href="/client?company_id=${escapeHtml(company.id)}" target="_blank" rel="noreferrer"><h3>Portal cliente</h3><p>Vista del tenant.</p></a>
        <a class="cx-package-card" href="/admin" target="_blank" rel="noreferrer"><h3>Admin actual</h3><p>Configurador especializado.</p></a>
        <a class="cx-package-card" href="/docs" target="_blank" rel="noreferrer"><h3>Swagger</h3><p>Documentación API.</p></a>
        <button class="cx-package-card" data-copy="${escapeHtml(company.id)}" type="button"><h3>Copiar Company ID</h3><p>${escapeHtml(company.id)}</p></button>
      </div>

      <section class="cx-panel">
        <div class="cx-card-head">
          <div>
            <h3>Bot Telegram</h3>
            <p>Asocia un bot de Telegram a esta empresa. El token queda vinculado al company_id y no se muestra completo.</p>
          </div>
          ${botStatus}
        </div>

        ${!botsEnabled ? `
          <div class="cx-alert" style="display:block;margin:12px 0">
            El módulo Bots no esta activo para esta empresa. Puedes guardar el token, pero activa Bots para usar captura operativa.
          </div>
        ` : ""}

        <div class="cx-detail-grid" style="margin:14px 0">
          <div class="cx-kv"><span>Empresa</span><strong>${escapeHtml(company.name)}</strong></div>
          <div class="cx-kv"><span>Company ID</span><strong>${escapeHtml(company.id)}</strong></div>
          <div class="cx-kv"><span>Token</span><strong>${escapeHtml(config?.masked_token || "No configurado")}</strong></div>
          <div class="cx-kv"><span>Usuario bot</span><strong>${escapeHtml(config?.bot_username ? `@${config.bot_username}` : "Sin validar")}</strong></div>
          <div class="cx-kv"><span>Flujo</span><strong>${escapeHtml(botFlowLabel(botFlowCode))}</strong></div>
          <div class="cx-kv"><span>Webhook</span><strong>${escapeHtml(botWebhookMode)}</strong></div>
          <div class="cx-kv"><span>Última validación</span><strong>${escapeHtml(config?.last_validated_at || "Sin validar")}</strong></div>
          <div class="cx-kv"><span>Error</span><strong>${escapeHtml(config?.last_error || "Sin error")}</strong></div>
        </div>

        <form class="cx-form" id="telegramBotConfigForm" data-company-id="${escapeHtml(company.id)}">
          <label>Nombre interno
            <input name="name" type="text" value="${escapeHtml(config?.name || `${company.name} Telegram Bot`)}" placeholder="Bot ${escapeHtml(company.name)}" />
          </label>
          <label>Token Telegram BotFather
            <input name="token" type="password" autocomplete="off" placeholder="${config?.configured ? "Pega un token nuevo solo si quieres reemplazarlo" : "Pega aquí el token de BotFather"}" />
          </label>
          <label>Flujo del bot
            <select name="flow_code" data-bot-flow-company="${escapeHtml(company.id)}">
              ${botFlowOptions(company, botFlowCode)}
            </select>
            <small>El flujo se sugiere según los módulos activos de esta empresa.</small>
          </label>
          ${botWebhookUrl ? `<div class="cx-alert" style="display:block;margin:10px 0"><strong>Webhook dedicado:</strong><br>${escapeHtml(botWebhookUrl)}</div>` : ""}
          <div class="cx-actions" style="margin-top:10px;gap:10px;flex-wrap:wrap">
            <button class="cx-btn cx-btn-primary" type="submit">Guardar token</button>
            <button class="cx-btn" type="button" data-test-telegram-bot="${escapeHtml(company.id)}">Probar conexión</button>
            ${config?.configured ? `<button class="cx-btn cx-btn-primary" type="button" data-start-telegram-listener="${escapeHtml(company.id)}">${config?.webhook_mode === "dedicated" ? "Reinstalar webhook dedicado" : "Activar webhook dedicado"}</button>` : ""}
            ${config?.configured ? `<button class="cx-btn" type="button" data-deactivate-telegram-bot="${escapeHtml(company.id)}">Desactivar bot</button>` : ""}
          </div>
          <small>No pegues este token en chats ni documentos. CLONEXA lo guarda por empresa y lo devuelve siempre enmascarado.</small>
        </form>
      </section>
    `;
  }

  async function saveTelegramBotConfig(companyId, event) {
    event.preventDefault();
    const form = event.target;
    const body = Object.fromEntries(new FormData(form).entries());
    body.token = String(body.token || "").trim();
    body.name = String(body.name || "").trim();
    delete body.flow_code;

    try {
      const data = await apiPut(`${API}/bots/companies/${companyId}/telegram`, body);
      state.companyBotConfigs.set(botConfigKey(companyId, "telegram"), data);
      showToast("Token de Telegram guardado para esta empresa.");
      const company = state.companies.find((c) => c.id === companyId);
      if (company) renderCompanyDetailTab(company);
    } catch (error) {
      showToast(`No se pudo guardar el token: ${error.message}`, "error");
    }
  }

  async function testTelegramBotConfig(companyId) {
    try {
      const data = await apiPost(`${API}/bots/companies/${companyId}/telegram/test`, {});
      state.companyBotConfigs.set(botConfigKey(companyId, "telegram"), data);
      showToast(data.ok ? "Bot Telegram validado correctamente." : "Telegram respondio con error.", data.ok ? "ok" : "error");
      const company = state.companies.find((c) => c.id === companyId);
      if (company) renderCompanyDetailTab(company);
    } catch (error) {
      showToast(`No se pudo probar Telegram: ${error.message}`, "error");
    }
  }

  async function startTelegramBotListener(companyId) {
    try {
      const flowSelect = [...document.querySelectorAll("[data-bot-flow-company]")]
        .find((node) => node.dataset.botFlowCompany === companyId);

      const flowCode = String(flowSelect?.value || telegramConfig(companyId)?.flow_code || "base").trim();

      const data = await apiPost(`${API}/company-bots-v1/companies/${companyId}/telegram/activate-webhook`, {
        flow_code: flowCode,
      });

      state.companyBotConfigs.set(botConfigKey(companyId, "telegram"), data);
      showToast("Webhook dedicado activado para esta empresa.");
      const company = state.companies.find((c) => c.id === companyId);
      if (company) renderCompanyDetailTab(company);
    } catch (error) {
      showToast(`No se pudo activar el webhook dedicado: ${error.message}`, "error");
    }
  }

  async function deactivateTelegramBotConfig(companyId) {
    try {
      const data = await apiPost(`${API}/bots/companies/${companyId}/telegram/deactivate`, {});
      state.companyBotConfigs.set(botConfigKey(companyId, "telegram"), data);
      showToast("Bot Telegram desactivado.");
      const company = state.companies.find((c) => c.id === companyId);
      if (company) renderCompanyDetailTab(company);
    } catch (error) {
      showToast(`No se pudo desactivar el bot: ${error.message}`, "error");
    }
  }

  async function loadAdminDashboard() {
    clearAdminError();

    const tasks = [
      loadHealth().catch((error) => {
        state.errors.push(`Health: ${error.message}`);
      }),
      loadCompanies().catch((error) => {
        state.errors.push(`Empresas: ${error.message}`);
        showAdminError(`No se pudieron cargar empresas: ${error.message}`);
      }),
      loadPackages().catch((error) => {
        state.errors.push(`Paquetes: ${error.message}`);
      }),
      loadModules().catch((error) => {
        state.errors.push(`Módulos: ${error.message}`);
      }),
    ];

    await Promise.all(tasks);

    await Promise.all(
      state.companies.map((company) => loadCompanyModules(company.id).catch(() => []))
    );

    await Promise.all(
      state.companies.map((company) => loadCompanyUsers(company.id).catch(() => []))
    );

    state.lastRefresh = localTime();
    renderAll();
    applyOwnerAccessLabels();
  }

  function setApiStatus(ok) {
    const dot = el("#apiStatusDot");
    const label = el("#apiStatusLabel");
    if (dot) {
      dot.classList.toggle("live", Boolean(ok));
      dot.classList.toggle("offline", !ok);
    }
    if (label) label.textContent = ok ? "LIVE" : "OFFLINE";
  }

  function updateMetrics() {
    const active = state.companies.filter((c) => String(c.status || "").toLowerCase() === "active").length;
    setText("metricCompanies", state.companies.length);
    setText("metricPackages", state.packages.length);
    setText("metricModules", state.modules.length);
    setText("metricActiveCompanies", active);
    setText("metricApi", state.health && state.health.ok !== false ? "LIVE" : "OFFLINE");
    setText("metricRefresh", state.lastRefresh || "Ã¢â‚¬â€");
    setText("lastRefreshLabel", state.lastRefresh ? `ÃƒÅ¡ltima actualizaciÃƒÂ³n ${state.lastRefresh}` : "Sin actualizar");
  }

  function renderDashboard() {
    const summary = el("#dashboardSummary");
    if (summary) {
      summary.innerHTML = `
        <div class="cx-detail-grid">
          <div class="cx-kv"><span>Empresas activas</span><strong>${escapeHtml(state.companies.filter(c => c.status === "active").length)}</strong></div>
          <div class="cx-kv"><span>Paquetes SaaS</span><strong>${escapeHtml(state.packages.length)}</strong></div>
          <div class="cx-kv"><span>Módulos globales</span><strong>${escapeHtml(state.modules.length)}</strong></div>
          <div class="cx-kv"><span>Estado</span><strong>${state.health && state.health.ok !== false ? "Operativo" : "Revisar API"}</strong></div>
        </div>
        ${state.errors.length ? `<div class="cx-alert">${escapeHtml(state.errors.slice(-3).join(" Ã‚Â· "))}</div>` : ""}
      `;
    }

    const list = el("#dashboardCompanies");
    if (list) {
      const rows = filteredCompanies().slice(0, 6);
      list.innerHTML = rows.length
        ? rows.map((company) => `
          <button class="cx-mini-card" type="button" data-select-company="${escapeHtml(company.id)}">
            <strong>${escapeHtml(company.name)}</strong>
            <span>${escapeHtml(company.slug)} Ã‚Â· ${escapeHtml(company.status)}</span>
          </button>
        `).join("")
        : `<div class="cx-empty-state">No hay empresas cargadas.</div>`;
    }
  }

  function renderCompanies() {
    const body = el("#companiesTableBody");
    if (!body) return;

    ensureCompanyLifecycleFilters();

    if (!state.companies.length) {
      body.innerHTML = `<tr><td colspan="8">No se encontraron empresas. Verifica /api/v1/companies.</td></tr>`;
      return;
    }

    const rows = filteredCompanies();

    els("[data-company-filter]").forEach((button) => {
      button.classList.toggle("cx-btn-primary", button.dataset.companyFilter === state.companyFilter);
    });

    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="8">No hay empresas para este filtro.</td></tr>`;
      return;
    }

    body.innerHTML = rows.map((company) => {
      const moduleCount = moduleCodesForCompany(company.id).length;
      const pkg = packageForCompany(company);
      const users = state.companyUsers.get(company.id);
      const ownerInfo = ownerAccessInfo(users);
      const owner = ownerInfo.owner;
      const archived = isArchivedCompany(company);
      return `
        <tr>
          <td><strong>${escapeHtml(company.name)}</strong><br><small>${escapeHtml(truncate(company.id, 14))}</small></td>
          <td>${escapeHtml(company.slug)}</td>
          <td>${statusBadge(company.status)}<br><small>Acceso Maestro: ${ownerAccessBadge(users)}</small></td>
          <td>${escapeHtml(company.plan || "Ã¢â‚¬â€")}</td>
          <td>${escapeHtml(company.timezone || "Ã¢â‚¬â€")}</td>
          <td><span class="cx-badge cx-badge-primary">${escapeHtml(pkg)}</span></td>
          <td>${escapeHtml(moduleCount)}</td>
          <td>
            <div class="cx-actions">
              <button class="cx-btn cx-btn-small" data-select-company="${escapeHtml(company.id)}" type="button">Ver detalle</button>
              <button class="cx-btn cx-btn-small" data-copy="${escapeHtml(company.id)}" type="button">Copiar ID</button>
              ${!archived ? `<button class="cx-btn cx-btn-small" data-open-client="${escapeHtml(company.id)}" type="button">Abrir portal</button>` : ""}
              ${renderCompanyLifecycleActions(company, true)}
            </div>
            ${owner ? `<small>${escapeHtml(owner.email)}</small>` : `<small>Esta empresa no tiene acceso maestro creado.</small>`}
            ${ownerInfo.status === "MÃƒÅ¡LTIPLE" ? `<br><small>Hay mÃƒÂºltiples accesos maestros.</small>` : ""}
          </td>
        </tr>
      `;
    }).join("");
  }

  function statusBadge(status) {
    const s = String(status || "active").toLowerCase();
    if (s === "active") return `<span class="cx-badge cx-badge-live">active</span>`;
    if (s === "inactive") return `<span class="cx-badge cx-badge-danger">inactive</span>`;
    if (s === "deleted" || s === "archived") return `<span class="cx-badge cx-badge-danger">Archivada</span>`;
    if (s === "blocked") return `<span class="cx-badge cx-badge-danger">blocked</span>`;
    return `<span class="cx-badge">${escapeHtml(s)}</span>`;
  }

  function cxMiniPanelLoginTemplate(typeCode) {
    const origin = window.location.origin || "";
    return `${origin}/mini-panel/login?company_id={company_id}&type=${encodeURIComponent(typeCode)}`;
  }

  /* CLONEXA_019A_R2_PACKAGE_BUILDER_MINI_PANEL_START */
  const CX_PACKAGE_MINI_PANEL_TYPES = [
    { code: "store", label: "Tiendas" },
    { code: "sales", label: "Ventas" },
    { code: "logistics", label: "Logística" },
    { code: "inventory", label: "Inventarios" },
    { code: "other", label: "Otros" },
  ];

  const CX_PACKAGE_MINI_PANEL_USER_LIMITS = [1, 3, 5, 10, 15];

  function cxPackageMiniPanelDefaultSettings(raw = {}) {
    const source = raw && typeof raw === "object" ? raw : {};
    const rawTypes = source.types && typeof source.types === "object" ? source.types : {};
    const types = {};

    CX_PACKAGE_MINI_PANEL_TYPES.forEach((def) => {
      const current = rawTypes[def.code] && typeof rawTypes[def.code] === "object" ? rawTypes[def.code] : {};
      const enabled = current.enabled === true;
      const usersAllowed = Number.isFinite(Number(current.users_allowed)) ? Number(current.users_allowed) : 0;
      types[def.code] = {
        enabled,
        label: current.label || def.label,
        users_allowed: enabled ? (CX_PACKAGE_MINI_PANEL_USER_LIMITS.includes(usersAllowed) ? usersAllowed : 1) : 0,
        login_template: current.login_template || cxMiniPanelLoginTemplate(def.code),
      };
    });

    return {
      enabled: source.enabled === true,
      types,
      updated_at: source.updated_at || null,
    };
  }

  function cxPackageMiniPanelEnabledSummary(settings) {
    const config = cxPackageMiniPanelDefaultSettings(settings || {});
    const enabledTypes = CX_PACKAGE_MINI_PANEL_TYPES.filter((def) => config.types[def.code]?.enabled);
    if (!config.enabled || !enabledTypes.length) return "Mini panel deshabilitado";
    return enabledTypes.map((def) => `${def.label}: ${config.types[def.code].users_allowed || 0}`).join(" · ");
  }

  function cxPackageHasMiniPanelModule(pkg) {
    return safeArray(pkg?.modules).some((module) => {
      const code = String(typeof module === "string" ? module : (module.code || module.module_code || module.name || "")).toLowerCase();
      const name = String(typeof module === "string" ? module : (module.name || "")).toLowerCase();
      const text = `${code} ${name}`.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
      return text.includes("mini_panel") || text.includes("minipanel") || text.includes("mini panel") || text.includes("creacion mini");
    });
  }

  function cxIsMiniPanelModuleCode(code) {
    const module = state.modules.find((item) => String(item.code || item.module_code || "").trim() === String(code || "").trim());
    const text = [
      code,
      module?.name,
      module?.description,
    ].filter(Boolean).join(" ").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    return text.includes("mini_panel") || text.includes("minipanel") || text.includes("mini panel") || text.includes("creacion mini");
  }

  function cxPackageMiniPanelFromForm(form) {
    const enabled = !!form.querySelector("[name='builder_mini_panel_enabled']")?.checked;
    const payload = {
      enabled,
      types: {},
    };

    CX_PACKAGE_MINI_PANEL_TYPES.forEach((def) => {
      const typeEnabled = !!form.querySelector(`[name='builder_type_enabled_${def.code}']`)?.checked;
      const usersAllowed = Number(form.querySelector(`[name='builder_type_users_${def.code}']`)?.value || 0);
      payload.types[def.code] = {
        enabled: enabled && typeEnabled,
        label: def.label,
        users_allowed: enabled && typeEnabled ? (CX_PACKAGE_MINI_PANEL_USER_LIMITS.includes(usersAllowed) ? usersAllowed : 1) : 0,
      };
    });

    return payload;
  }

  function cxReadPackageBuilderForm(form) {
    const raw = Object.fromEntries(new FormData(form).entries());
    const moduleCodes = Array.from(form.querySelectorAll("[name='module_codes']:checked"))
      .map((input) => String(input.value || "").trim())
      .filter(Boolean);

    return {
      package_payload: {
        code: String(raw.code || "").trim().toLowerCase().replace(/[^a-z0-9_:-]+/g, "_").replace(/^_+|_+$/g, ""),
        name: String(raw.name || "").trim(),
        description: String(raw.description || "").trim(),
        is_active: raw.is_active === "on",
        module_codes: Array.from(new Set(moduleCodes)),
      },
      mini_panel: cxPackageMiniPanelFromForm(form),
    };
  }

  async function loadPackageMiniPanelSettings(packageId, force = false) {
    if (!packageId) return cxPackageMiniPanelDefaultSettings();
    if (!force && state.packageMiniPanelSettings.has(packageId)) {
      return state.packageMiniPanelSettings.get(packageId);
    }

    try {
      const data = await apiGet(`${API}/packages/${packageId}/mini-panel-settings`);
      const normalized = cxPackageMiniPanelDefaultSettings(data && data.mini_panel ? data.mini_panel : data);
      state.packageMiniPanelSettings.set(packageId, normalized);
      return normalized;
    } catch (error) {
      const fallback = cxPackageMiniPanelDefaultSettings();
      fallback.unavailable = true;
      fallback.error = error.message;
      state.packageMiniPanelSettings.set(packageId, fallback);
      return fallback;
    }
  }

  async function savePackageMiniPanelSettings(packageId, payload) {
    const data = await apiPut(`${API}/packages/${packageId}/mini-panel-settings`, payload);
    const normalized = cxPackageMiniPanelDefaultSettings(data && data.mini_panel ? data.mini_panel : data);
    state.packageMiniPanelSettings.set(packageId, normalized);
    return normalized;
  }

  async function cxSavePackageFromBuilder(form) {
    const editingId = form.dataset.editingPackageId || "";
    const { package_payload, mini_panel } = cxReadPackageBuilderForm(form);

    if (!package_payload.name || !package_payload.code) {
      throw new Error("Nombre y código del paquete son obligatorios.");
    }

    let saved;
    if (editingId) {
      saved = await apiPut(`${API}/packages/${editingId}`, package_payload);
    } else {
      saved = await apiPost(`${API}/packages`, package_payload);
    }

    const normalized = normalizePackage(saved);
    const packageId = normalized.id;

    if (package_payload.module_codes.some(cxIsMiniPanelModuleCode)) {
      await savePackageMiniPanelSettings(packageId, mini_panel);
    } else {
      await savePackageMiniPanelSettings(packageId, cxPackageMiniPanelDefaultSettings({ enabled: false }));
    }

    await loadPackages();
    return normalized;
  }

  function cxPackageModuleCodes(pkg) {
    return safeArray(pkg?.modules)
      .map((module) => String(typeof module === "string" ? module : (module.code || module.module_code || "")).trim())
      .filter(Boolean);
  }

  function cxRenderPackageModuleSelector(selectedCodes = []) {
    const selected = new Set(selectedCodes.map(String));
    const modules = state.modules.map(normalizeModule).filter((item) => item.code).sort((a, b) => {
      const ca = String(a.category || "").localeCompare(String(b.category || ""), "es");
      return ca || String(a.name || a.code).localeCompare(String(b.name || b.code), "es");
    });

    if (!modules.length) {
      return `<div class="cx-empty-state">No hay módulos cargados para armar paquetes.</div>`;
    }

    return `
      <div class="cx-module-builder-grid">
        ${modules.map((module) => {
          const meta = typeof cxModuleMeta === "function" ? cxModuleMeta(module) : { name: module.name, badge: module.code, categoryLabel: module.category || "General" };
          const checked = selected.has(module.code);
          return `
            <label class="cx-module-pick ${checked ? "is-selected" : ""}">
              <input type="checkbox" name="module_codes" value="${escapeHtml(module.code)}" ${checked ? "checked" : ""} data-builder-module-code="${escapeHtml(module.code)}">
              <span>
                <strong>${escapeHtml(meta.name || module.name || module.code)}</strong>
                <small>${escapeHtml(module.code)} · ${escapeHtml(meta.categoryLabel || module.category || "General")}</small>
              </span>
            </label>
          `;
        }).join("")}
      </div>
    `;
  }

  function cxRenderPackageMiniPanelBuilder(settings = {}, miniPanelSelected = false) {
    const config = cxPackageMiniPanelDefaultSettings(settings || {});
    const isEnabled = miniPanelSelected && config.enabled;
    const selectedBadges = CX_PACKAGE_MINI_PANEL_TYPES
      .filter((def) => config.types[def.code]?.enabled)
      .map((def) => `<span class="cx-badge cx-badge-live" data-builder-mini-type-badge="${escapeHtml(def.code)}">${escapeHtml(def.label)}</span>`)
      .join("");

    return `
      <section class="cx-mini-card" data-builder-mini-panel-section ${miniPanelSelected ? "" : "hidden"} style="margin-top:14px">
        <div class="cx-card-head">
          <div>
            <strong>Configuración mini_panel</strong>
            <p>Solo aparece cuando el paquete incluye el módulo CREACION MINI_PANEL.</p>
          </div>
          <span class="cx-badge ${isEnabled ? "cx-badge-live" : ""}">${isEnabled ? "Habilitado" : "Pendiente"}</span>
        </div>

        <label style="display:flex;align-items:center;gap:10px">
          <input type="checkbox" name="builder_mini_panel_enabled" ${isEnabled ? "checked" : ""}>
          Habilitar mini_panel en este paquete
        </label>

        <label>Tipos permitidos
          <select data-builder-mini-type-picker>
            <option value="">Seleccionar tipo</option>
            ${CX_PACKAGE_MINI_PANEL_TYPES.map((def) => `<option value="${escapeHtml(def.code)}">${escapeHtml(def.label)}</option>`).join("")}
          </select>
        </label>

        <div class="cx-actions" data-builder-mini-selected-types style="margin:8px 0 12px">
          ${selectedBadges || `<span class="cx-badge">Sin tipos seleccionados</span>`}
        </div>

        <div class="cx-detail-grid" data-builder-mini-types-grid>
          ${CX_PACKAGE_MINI_PANEL_TYPES.map((def) => {
            const row = config.types[def.code] || { enabled: false, users_allowed: 0 };
            const userOptions = CX_PACKAGE_MINI_PANEL_USER_LIMITS
              .map((limit) => `<option value="${limit}" ${Number(row.users_allowed) === limit ? "selected" : ""}>${limit}</option>`)
              .join("");

            return `
              <div class="cx-mini-card" data-builder-mini-type-section="${escapeHtml(def.code)}" ${row.enabled ? "" : "hidden"}>
                <div class="cx-card-head">
                  <div>
                    <strong>${escapeHtml(def.label)}</strong>
                    <p>Capacidad operativa heredada por empresas con este paquete.</p>
                  </div>
                  <span class="cx-badge cx-badge-live">Activo</span>
                </div>
                <label style="display:flex;align-items:center;gap:10px">
                  <input type="checkbox" name="builder_type_enabled_${escapeHtml(def.code)}" ${row.enabled ? "checked" : ""} data-builder-mini-type-enabled="${escapeHtml(def.code)}">
                  Tipo habilitado
                </label>
                <label>Enlace base generado
                  <input value="${escapeHtml(cxMiniPanelLoginTemplate(def.code))}" readonly>
                </label>
                <label>Usuarios permitidos
                  <select name="builder_type_users_${escapeHtml(def.code)}">
                    ${userOptions}
                  </select>
                </label>
              </div>
            `;
          }).join("")}
        </div>
      </section>
    `;
  }

  function cxRenderPackageBuilder(pkg = null) {
    const editing = pkg ? normalizePackage(pkg) : null;
    const packageId = editing?.id || "";
    const selectedCodes = editing ? cxPackageModuleCodes(editing) : [];
    const miniSelected = selectedCodes.some(cxIsMiniPanelModuleCode);
    const miniSettings = packageId ? (state.packageMiniPanelSettings.get(packageId) || cxPackageMiniPanelDefaultSettings()) : cxPackageMiniPanelDefaultSettings();

    return `
      <form class="cx-form cx-package-builder-form" data-package-builder-form data-editing-package-id="${escapeHtml(packageId)}">
        <div class="cx-card-head">
          <div>
            <h3>ARMAR PAQUETES</h3>
            <p>Crea paquetes SaaS seleccionando módulos a gusto. Si incluyes CREACION MINI_PANEL, se habilita su configuracion.</p>
          </div>
          ${editing ? `<span class="cx-badge cx-badge-live">Editando</span>` : `<span class="cx-badge">Nuevo</span>`}
        </div>

        <label>Nombre del paquete
          <input name="name" type="text" required value="${escapeHtml(editing?.name || "")}" placeholder="Retail Mundo Case">
        </label>

        <label>Código del paquete
          <input name="code" type="text" required value="${escapeHtml(editing?.code || "")}" placeholder="retail_mundo_case">
        </label>

        <label>Descripción
          <textarea name="description" rows="3" placeholder="Paquete SaaS para tiendas, ventas y mini paneles.">${escapeHtml(editing?.description || "")}</textarea>
        </label>

        <label style="display:flex;align-items:center;gap:10px">
          <input type="checkbox" name="is_active" ${editing && editing.is_active === false ? "" : "checked"}>
          Paquete activo
        </label>

        <div class="cx-mini-card">
          <div class="cx-card-head">
            <div>
              <strong>Módulos incluidos</strong>
              <p>Selecciona los módulos que tendrá este paquete.</p>
            </div>
            <span class="cx-badge">${escapeHtml(selectedCodes.length)} seleccionados</span>
          </div>
          ${cxRenderPackageModuleSelector(selectedCodes)}
        </div>

        ${cxRenderPackageMiniPanelBuilder(miniSettings, miniSelected)}

        <div class="cx-actions" style="margin-top:14px">
          <button class="cx-btn cx-btn-primary" type="submit">${editing ? "Guardar cambios del paquete" : "Guardar paquete"}</button>
          <button class="cx-btn" type="button" data-package-builder-reset>Limpiar</button>
        </div>
      </form>
    `;
  }

  function cxSyncBuilderMiniPanelVisibility(form) {
    if (!form) return;
    const miniSelected = Array.from(form.querySelectorAll("[name='module_codes']:checked")).some((input) => cxIsMiniPanelModuleCode(input.value));
    const section = form.querySelector("[data-builder-mini-panel-section]");
    if (section) section.hidden = !miniSelected;

    const enabled = form.querySelector("[name='builder_mini_panel_enabled']");
    if (enabled && !miniSelected) enabled.checked = false;
  }

  function cxSyncBuilderMiniBadges(form) {
    if (!form) return;
    const selected = CX_PACKAGE_MINI_PANEL_TYPES
      .filter((def) => form.querySelector(`[name='builder_type_enabled_${def.code}']`)?.checked)
      .map((def) => `<span class="cx-badge cx-badge-live" data-builder-mini-type-badge="${escapeHtml(def.code)}">${escapeHtml(def.label)}</span>`)
      .join("");

    const target = form.querySelector("[data-builder-mini-selected-types]");
    if (target) target.innerHTML = selected || `<span class="cx-badge">Sin tipos seleccionados</span>`;
  }

  function cxRenderPackageCapabilitiesSummary(pkg, settings) {
    const config = cxPackageMiniPanelDefaultSettings(settings || {});
    const modules = cxPackageModuleCodes(pkg);
    const moduleChips = modules.length
      ? modules.map((code) => `<span class="cx-badge">${escapeHtml(code)}</span>`).join("")
      : `<span class="cx-badge">Sin módulos</span>`;

    const miniRows = config.enabled
      ? CX_PACKAGE_MINI_PANEL_TYPES.filter((def) => config.types[def.code]?.enabled).map((def) => `
          <div class="cx-kv">
            <span>${escapeHtml(def.label)}</span>
            <strong>${escapeHtml(config.types[def.code].users_allowed)} usuarios</strong>
          </div>
        `).join("")
      : `<div class="cx-empty-state">Mini panel deshabilitado en este paquete.</div>`;

    return `
      <div class="cx-mini-card">
        <strong>Capacidades heredadas</strong>
        <div class="cx-actions" style="margin:10px 0">${moduleChips}</div>
        <div class="cx-detail-grid">${miniRows}</div>
      </div>
    `;
  }

  function cxFindPackageByCodeOrName(value) {
    const target = String(value || "").trim().toLowerCase();
    if (!target) return null;
    return state.packages.find((pkg) => {
      const normalized = normalizePackage(pkg);
      return String(normalized.code || "").toLowerCase() === target || String(normalized.name || "").toLowerCase() === target;
    }) || null;
  }

  function cxRenderCompanyPackageInheritedCapabilities(company) {
    const current = packageForCompany(company);
    const pkg = cxFindPackageByCodeOrName(current);
    if (!pkg) {
      return `<div class="cx-empty-state" style="margin-top:12px">Selecciona y activa un paquete para ver sus capacidades heredadas.</div>`;
    }

    const settings = state.packageMiniPanelSettings.get(pkg.id) || cxPackageMiniPanelDefaultSettings();
    return `<div style="margin-top:12px">${cxRenderPackageCapabilitiesSummary(pkg, settings)}</div>`;
  }

  function cxBindPackageBuilderEvents() {
    if (window.__cxPackageBuilderEventsBound) return;
    window.__cxPackageBuilderEventsBound = true;

    document.addEventListener("change", (event) => {
      const moduleInput = event.target.closest("[data-builder-module-code]");
      if (moduleInput) {
        const form = moduleInput.closest("[data-package-builder-form]");
        cxSyncBuilderMiniPanelVisibility(form);
        moduleInput.closest(".cx-module-pick")?.classList.toggle("is-selected", moduleInput.checked);
        return;
      }

      const picker = event.target.closest("[data-builder-mini-type-picker]");
      if (picker) {
        const form = picker.closest("[data-package-builder-form]");
        const code = picker.value;
        if (!form || !code) return;

        const enabled = form.querySelector(`[name='builder_type_enabled_${code}']`);
        const section = form.querySelector(`[data-builder-mini-type-section='${code}']`);
        if (enabled) enabled.checked = true;
        if (section) section.hidden = false;

        const users = form.querySelector(`[name='builder_type_users_${code}']`);
        if (users && !users.value) users.value = "1";

        const globalEnabled = form.querySelector("[name='builder_mini_panel_enabled']");
        if (globalEnabled) globalEnabled.checked = true;

        picker.value = "";
        cxSyncBuilderMiniBadges(form);
        return;
      }

      const miniType = event.target.closest("[data-builder-mini-type-enabled]");
      if (miniType) {
        const form = miniType.closest("[data-package-builder-form]");
        const code = miniType.dataset.builderMiniTypeEnabled;
        const section = form?.querySelector(`[data-builder-mini-type-section='${code}']`);
        if (section) section.hidden = !miniType.checked;
        cxSyncBuilderMiniBadges(form);
      }
    });

    document.addEventListener("click", async (event) => {
      const editButton = event.target.closest("[data-package-builder-edit]");
      if (editButton) {
        const packageId = editButton.dataset.packageBuilderEdit;
        const pkg = state.packages.find((item) => String(item.id) === String(packageId));
        if (!pkg) return;

        await loadPackageMiniPanelSettings(packageId, true);
        const holder = document.querySelector("[data-package-builder-holder]");
        if (holder) holder.innerHTML = cxRenderPackageBuilder(pkg);
        holder?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }

      const resetButton = event.target.closest("[data-package-builder-reset]");
      if (resetButton) {
        const holder = document.querySelector("[data-package-builder-holder]");
        if (holder) holder.innerHTML = cxRenderPackageBuilder();
        return;
      }

      const badge = event.target.closest("[data-builder-mini-type-badge]");
      if (badge) {
        const form = badge.closest("[data-package-builder-form]");
        const code = badge.dataset.builderMiniTypeBadge;
        const enabled = form?.querySelector(`[name='builder_type_enabled_${code}']`);
        const section = form?.querySelector(`[data-builder-mini-type-section='${code}']`);
        if (enabled) enabled.checked = false;
        if (section) section.hidden = true;
        cxSyncBuilderMiniBadges(form);
      }
    });

    document.addEventListener("submit", async (event) => {
      const form = event.target.closest("[data-package-builder-form]");
      if (!form) return;

      event.preventDefault();
      const button = form.querySelector("button[type='submit']");
      const originalText = button ? button.textContent : "";

      if (button) {
        button.disabled = true;
        button.textContent = "Guardando...";
      }

      try {
        await cxSavePackageFromBuilder(form);
        showToast("Paquete guardado correctamente.");
        renderPackages();
      } catch (error) {
        showToast(`No se pudo guardar el paquete: ${error.message}`, "error");
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = originalText || "Guardar paquete";
        }
      }
    });
  }

  function renderPackages() {
    const grid = el("#packagesGrid");
    const select = el("#createCompanyPackageSelect");

    if (select) {
      select.innerHTML = `<option value="">Sin paquete inicial</option>` + state.packages
        .map((pkg) => `<option value="${escapeHtml(pkg.code)}">${escapeHtml(pkg.name)} (${escapeHtml(pkg.code)})</option>`)
        .join("");
    }

    if (!grid) return;

    cxBindPackageBuilderEvents();

    const packageCards = state.packages.length ? state.packages.map((pkg) => {
      const normalized = normalizePackage(pkg);
      const settings = state.packageMiniPanelSettings.get(normalized.id) || cxPackageMiniPanelDefaultSettings();
      const modules = cxPackageModuleCodes(normalized);
      const modulePreview = modules.length
        ? modules.slice(0, 7).map((code) => `<span class="cx-badge">${escapeHtml(code)}</span>`).join("")
        : `<span class="cx-badge">Sin módulos</span>`;

      return `
        <article class="cx-package-card">
          <div class="cx-card-head">
            <div>
              <h3>${escapeHtml(normalized.name)}</h3>
              <p>${escapeHtml(normalized.code)}</p>
            </div>
            ${normalized.is_active ? `<span class="cx-badge cx-badge-live">Activo</span>` : `<span class="cx-badge">Inactivo</span>`}
          </div>
          <p>${escapeHtml(normalized.description || "Paquete SaaS disponible para activar por empresa.")}</p>
          <div class="cx-actions" style="margin:10px 0">${modulePreview}</div>
          <div class="cx-kv" style="margin-top:12px">
            <span>Mini paneles</span>
            <strong data-package-mini-summary="${escapeHtml(normalized.id)}">${escapeHtml(cxPackageMiniPanelEnabledSummary(settings))}</strong>
          </div>
          <div class="cx-actions" style="margin-top:12px">
            <button class="cx-btn cx-btn-small" type="button" data-package-builder-edit="${escapeHtml(normalized.id)}">Editar en ARMAR PAQUETES</button>
          </div>
        </article>
      `;
    }).join("") : `<div class="cx-empty-state">No hay paquetes creados. Usa ARMAR PAQUETES para crear el primero.</div>`;

    grid.innerHTML = `
      <div class="cx-layout-two cx-package-builder-layout">
        <section>
          <div class="cx-card-head">
            <div>
              <h3>Paquetes creados</h3>
              <p>Productos SaaS disponibles para asignar a empresas.</p>
            </div>
            <span class="cx-badge">${escapeHtml(state.packages.length)} paquetes</span>
          </div>
          <div class="cx-packages-list">
            ${packageCards}
          </div>
        </section>
        <aside data-package-builder-holder>
          ${cxRenderPackageBuilder()}
        </aside>
      </div>
    `;

    state.packages.forEach((pkg) => {
      const normalized = normalizePackage(pkg);
      loadPackageMiniPanelSettings(normalized.id).then((settings) => {
        const summary = document.querySelector(`[data-package-mini-summary='${CSS.escape(String(normalized.id))}']`);
        if (summary) summary.textContent = cxPackageMiniPanelEnabledSummary(settings);
      });
    });
  }
/* CLONEXA_019A_R2_PACKAGE_BUILDER_MINI_PANEL_END */


  const CX_MODULE_META = {
    core: ["Nucleo", "Base operativa del tenant. Habilita estructura principal, estado de empresa y servicios base.", "Core", "COR"],
    workforce: ["Personal", "Gestion de personal operativo, roles internos y disponibilidad por empresa.", "Core", "WRK"],
    field: ["Operación en campo", "Control para equipos externos, rutas, evidencias y actividad operativa.", "Campo", "FLD"],
    gps: ["GPS", "Ubicacion, rutas y control de equipos en campo.", "Campo", "GPS"],
    payroll: ["Nómina", "Calculo de horas, cortes y pagos operativos.", "Finanzas", "PAY"],
    day_closing: ["Cierre de dia", "Resumen diario de ventas, pedidos, inventario y operacion.", "Hospitality", "DAY"],
    hospitality: ["Hospitality", "Motor para bares, restaurantes, mesas, pedidos y atencion comercial.", "Hospitality", "HSP"],
    loyalty: ["Fidelización", "Clientes recurrentes, beneficios y seguimiento comercial.", "Hospitality", "LOY"],
    orders: ["Pedidos", "Creación, seguimiento y estados de pedidos.", "Hospitality", "ORD"],
    tables: ["Mesas", "Gestion de mesas, cuentas y sesiones por QR.", "Hospitality", "TBL"],
    bots: ["Bots", "Entrada por Telegram, WhatsApp y automatizaciones.", "Input", "BOT"],
    qr: ["QR", "Accesos por QR para mesas, operaciones o formularios.", "Input", "QR"],
    inventory: ["Inventario", "Stock, existencias y control operativo de productos o materiales.", "Inventario", "INV"],
    materials: ["Materiales", "Solicitud, entrega, devolucion y control de materiales.", "Inventario", "MAT"],
    stock: ["Stock", "Existencias, minimos y alertas de disponibilidad.", "Inventario", "STK"],
    costs: ["Costos", "Costeo por referencia, produccion, servicio o pedido.", "Producción", "CST"],
    production: ["Producción", "Control de tiempos, referencias, productividad y costos.", "Producción", "PRD"],
    references: ["Referencias", "Catálogo de referencias, productos o servicios medibles.", "Producción", "REF"],
    crm: ["CRM Campo", "Vista operativa para seguimiento, control y acciones por empresa.", "Reportes", "CRM"],
    kpis: ["KPIs", "Indicadores ejecutivos y metricas por módulo.", "Reportes", "KPI"],
    reports: ["Reportes", "Reportes operativos, historicos y auditoria.", "Reportes", "REP"],
    commercial_closing: ["Cierre comercial", "Seguimiento de ventas, cierres y resultados comerciales.", "Retail", "COM"],
    requests: ["Solicitudes", "Solicitudes internas, aprobaciones y estados.", "Retail", "REQ"],
    retail: ["Retail", "Control de tiendas, ventas, solicitudes e inventario.", "Retail", "RTL"],
    sales: ["Ventas", "Actividad comercial, ventas y conversion.", "Retail", "SAL"],
    stores: ["Tiendas", "Sucursales, puntos de venta y operacion retail.", "Retail", "STR"],
  };

  function cxModuleMeta(module) {
    const code = String(module?.code || module?.module_code || "").trim();
    const fallbackName = module?.name || code || "Módulo";
    const fallbackCategory = module?.category || "general";
    const meta = CX_MODULE_META[code] || [fallbackName, module?.description || "Módulo operativo disponible para asignar por empresa.", fallbackCategory, code.slice(0, 3).toUpperCase() || "MOD"];

    return {
      code,
      name: meta[0],
      description: module?.description || meta[1],
      category: module?.category || meta[2],
      categoryLabel: meta[2],
      badge: meta[3],
    };
  }

  async function cxJsonRequest(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  function cxCompanyModuleRowMap(companyId) {
    const rows = state.companyModules && state.companyModules.get ? state.companyModules.get(companyId) : [];
    const map = new Map();

    safeArray(rows).forEach((row) => {
      const normalized = normalizeModule(row);
      if (normalized.code) map.set(normalized.code, normalized);
    });

    return map;
  }

  function cxBindModuleManagementEvents() {
    if (window.__cxModuleManagementEventsBound) return;
    window.__cxModuleManagementEventsBound = true;

    document.addEventListener("click", async (event) => {
      const infoButton = event.target.closest("[data-cx-module-info]");
      if (infoButton) {
        const code = infoButton.dataset.moduleCode;
        const module = state.modules.find((item) => item.code === code) || { code };
        const meta = cxModuleMeta(module);
        alert(`${meta.name}\n\n${meta.description}\n\nCategoría: ${meta.categoryLabel}\nCódigo: ${meta.code}`);
        return;
      }

      const toggleButton = event.target.closest("[data-cx-company-module-toggle]");
      if (!toggleButton) return;

      const companyId = toggleButton.dataset.companyId;
      const moduleCode = toggleButton.dataset.moduleCode;
      const action = toggleButton.dataset.action;

      if (!companyId || !moduleCode || !["activate", "deactivate"].includes(action)) return;

      toggleButton.disabled = true;
      toggleButton.textContent = action === "activate" ? "Activando..." : "Desactivando...";

      try {
        await cxJsonRequest(`/companies/${companyId}/modules/${moduleCode}/${action}`, {
          method: "POST",
          body: JSON.stringify({ settings: {} }),
        });

        await loadCompanyModules(companyId);

        if (typeof renderCompanies === "function") renderCompanies();
        if (typeof renderModules === "function") renderModules();
      } catch (error) {
        alert(`No se pudo ${action === "activate" ? "activar" : "desactivar"} el módulo: ${error.message}`);
      } finally {
        toggleButton.disabled = false;
      }
    });

    document.addEventListener("submit", async (event) => {
      const form = event.target.closest("#createModuleForm");
      if (!form) return;

      event.preventDefault();

      const data = new FormData(form);
      const payload = {
        code: String(data.get("code") || "").trim().toLowerCase().replace(/[^a-z0-9_]/g, "_"),
        name: String(data.get("name") || "").trim(),
        description: String(data.get("description") || "").trim() || null,
        category: String(data.get("category") || "").trim() || "custom",
        is_active: true,
      };

      if (!payload.code || !payload.name) {
        alert("Código y nombre son obligatorios.");
        return;
      }

      const button = form.querySelector("button[type='submit']");
      if (button) {
        button.disabled = true;
        button.textContent = "Creando...";
      }

      try {
        await cxJsonRequest("/modules", {
          method: "POST",
          body: JSON.stringify(payload),
        });

        await loadModules();
        renderModules();
        form.reset();
      } catch (error) {
        alert(`No se pudo crear el módulo: ${error.message}`);
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = "Crear módulo";
        }
      }
    });
  }

  cxBindModuleManagementEvents();



  function renderModules() {
    const grid = el("#modulesGrid");
    if (!grid) return;

    if (!state.modules.length) {
      grid.innerHTML = `<div class="cx-empty-state">No se pudieron cargar módulos.</div>`;
      return;
    }

    const selectedCodes = new Set(state.selectedCompanyId ? moduleCodesForCompany(state.selectedCompanyId) : []);
    const categories = new Map();

    state.modules.forEach((module) => {
      const normalized = normalizeModule(module);
      const meta = cxModuleMeta(normalized);
      const group = meta.categoryLabel || normalized.category || "General";
      if (!categories.has(group)) categories.set(group, []);
      categories.get(group).push({ ...normalized, meta });
    });

    grid.innerHTML = `
      <section class="cx-panel" style="grid-column:1/-1;margin-bottom:18px">
        <div class="cx-card-head">
          <div>
            <h3>Crear módulo</h3>
            <p>Agrega un módulo global reutilizable para paquetes y empresas.</p>
          </div>
          <span class="cx-badge cx-badge-primary">${escapeHtml(state.modules.length)} módulos</span>
        </div>

        <form class="cx-form" id="createModuleForm" style="display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:12px;align-items:end">
          <label>Código
            <input name="code" placeholder="tecnicos_field" required />
          </label>
          <label>Nombre
            <input name="name" placeholder="Tecnicos Field" required />
          </label>
          <label>Categoría
            <select name="category">
              <option value="core">Core</option>
              <option value="field">Campo</option>
              <option value="inventory">Inventario</option>
              <option value="production">Producción</option>
              <option value="finance">Finanzas</option>
              <option value="hospitality">Hospitality</option>
              <option value="retail">Retail</option>
              <option value="read_model">Reportes</option>
              <option value="input">Input</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          <button class="cx-btn cx-btn-primary" type="submit">Crear módulo</button>
          <label style="grid-column:1/-1">Descripción
            <input name="description" placeholder="Que ejecuta este módulo dentro de CLONEXA" />
          </label>
        </form>
      </section>

      ${Array.from(categories.entries()).map(([category, modules]) => `
        <section style="grid-column:1/-1">
          <div class="cx-section-title">
            <h3>${escapeHtml(category)}</h3>
            <p>${escapeHtml(modules.length)} módulos disponibles</p>
          </div>

          <div class="cx-module-grid">
            ${modules.map(({ meta, ...module }) => {
              const activeForCompany = selectedCodes.has(module.code);
              return `
                <article class="cx-module-chip">
                  <div class="cx-card-head">
                    <div>
                      <strong>${escapeHtml(meta.name)}</strong>
                      <p>${escapeHtml(module.code)}</p>
                    </div>
                    <span class="cx-badge">${escapeHtml(meta.badge)}</span>
                  </div>
                  <p>${escapeHtml(meta.description)}</p>
                  <div class="cx-actions">
                    <span class="cx-badge">${escapeHtml(meta.categoryLabel)}</span>
                    ${activeForCompany ? `<span class="cx-badge cx-badge-live">Activo tenant</span>` : ""}
                    <button class="cx-btn" type="button" data-cx-module-info data-module-code="${escapeHtml(module.code)}">Info</button>
                  </div>
                </article>
              `;
            }).join("")}
          </div>
        </section>
      `).join("")}
    `;
  }

  function renderAccess() {
    const grid = el("#accessGrid");
    if (!grid) return;

    const links = [
      { title: "Admin actual", subtitle: "Consola previa", href: "/admin" },
      { title: "Portal cliente", subtitle: "Panel empresa", href: "/client" },
      { title: "Swagger / Docs", subtitle: "API docs", href: "/docs" },
      { title: "Health", subtitle: "Estado API", href: "/health" },
      { title: "Login", subtitle: "Acceso cliente", href: "/login" },
    ];

    grid.innerHTML = links.map((item) => `
      <a class="cx-package-card" href="${escapeHtml(item.href)}" target="_blank" rel="noreferrer">
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.subtitle)}</p>
        <span class="cx-badge cx-badge-primary">${escapeHtml(item.href)}</span>
      </a>
    `).join("");
  }

  function renderHealth() {
    const content = el("#healthContent");
    if (!content) return;

    content.innerHTML = `
      <div class="cx-detail-grid">
        <div class="cx-kv"><span>API</span><strong>${state.health && state.health.ok !== false ? "LIVE" : "OFFLINE"}</strong></div>
        <div class="cx-kv"><span>Empresas</span><strong>${escapeHtml(state.companies.length)}</strong></div>
        <div class="cx-kv"><span>Paquetes</span><strong>${escapeHtml(state.packages.length)}</strong></div>
        <div class="cx-kv"><span>Módulos</span><strong>${escapeHtml(state.modules.length)}</strong></div>
        <div class="cx-kv"><span>ÃƒÅ¡ltimo refresh</span><strong>${escapeHtml(state.lastRefresh || "Ã¢â‚¬â€")}</strong></div>
        <div class="cx-kv"><span>PostgreSQL</span><strong>${state.health && state.health.ok !== false ? "Derivado OK" : "No verificado"}</strong></div>
      </div>
      <pre class="cx-secret">${escapeHtml(JSON.stringify(state.health || {}, null, 2))}</pre>
    `;
  }

  function renderCrmView() {
    const node = el("#crmViewContent");
    if (!node) return;

    if (!state.companies.length) {
      node.innerHTML = `<div class="cx-empty-state">Carga empresas para revisar CRM / Panel Empresa.</div>`;
      return;
    }

    node.innerHTML = state.companies.map((company) => {
      const exp = state.companyExperience.get(company.id);
      const branding = exp && !exp.unavailable ? (exp.branding || {}) : {};
      return `
        <div class="cx-mini-card">
          <div class="cx-card-head">
            <div>
              <strong>${escapeHtml(company.name)}</strong>
              <p>${escapeHtml(company.slug)} Ã‚Â· ${escapeHtml(packageForCompany(company))}</p>
            </div>
            <button class="cx-btn cx-btn-small" data-select-company="${escapeHtml(company.id)}" data-detail-tab="crm" type="button">Ver CRM</button>
          </div>
          <div class="cx-actions">
            <span class="cx-badge">Preset: ${escapeHtml(branding.visual_preset || "Ã¢â‚¬â€")}</span>
            <span class="cx-badge">Tema: ${escapeHtml(branding.industry_theme || "Ã¢â‚¬â€")}</span>
            <span class="cx-badge">Color: ${escapeHtml(branding.primary_color || "Ã¢â‚¬â€")}</span>
          </div>
        </div>
      `;
    }).join("");
  }

  async function selectCompany(companyId, tab = "resumen") {
    state.selectedCompanyId = companyId;
    state.activeDetailTab = tab || "resumen";
    await loadCompanyDetail(companyId);
    setView("companies");
  }

  async function loadCompanyDetail(companyId) {
    const company = state.companies.find((item) => item.id === companyId);
    if (!company) return;

    await Promise.all([
      loadCompanyModules(companyId),
      loadCompanyUsers(companyId),
      loadCompanyExperience(companyId),
    ]);

    renderCompanyDetail(company);
    renderModules();
    renderUsersGlobalView();
    renderCrmView();
  }

  function renderCompanyDetail(company) {
    const card = el("#companyDetailCard");
    if (!card) return;

    const tabs = [
      ["resumen", "Resumen"],
      ["usuarios", "Acceso Maestro"],
      ["módulos", "Módulos"],
      ["paquete", "Paquete"],
      ["branding", "Branding"],
      ["crm", "CRM"],
      ["accesos", "Accesos"],
    ];

    card.innerHTML = `
      <div class="cx-card-head">
        <div>
          <h2>${escapeHtml(company.name)}</h2>
          <p>${escapeHtml(company.slug)} Ã‚Â· ${escapeHtml(company.id)}</p>
        </div>
        <div class="cx-actions">
          <button class="cx-btn cx-btn-small" data-copy="${escapeHtml(company.id)}" type="button">Copiar ID</button>
          ${!isArchivedCompany(company) ? `<a class="cx-btn cx-btn-small" href="/client?company_id=${escapeHtml(company.id)}" target="_blank" rel="noreferrer">Abrir /client</a>` : ""}
          <a class="cx-btn cx-btn-small" href="/admin" target="_blank" rel="noreferrer">Configurar CRM</a>
          ${renderCompanyLifecycleActions(company, true)}
        </div>
      </div>
      <div class="cx-detail-tabs">
        ${tabs.map(([key, label]) => `<button class="cx-tab ${state.activeDetailTab === key ? "active" : ""}" data-detail-tab="${key}" type="button">${label}</button>`).join("")}
      </div>
      <div id="companyDetailContent"></div>
    `;

    renderCompanyDetailTab(company);
  }

  /* CLONEXA_BRANDING_STUDIO_RENDER_HELPERS */
  const CX_BRANDING_PALETTES = [
    { name: "CLONEXA Dark", primary_color: "#ff2bd6", secondary_color: "#00ff88", background_color: "#050509", text_color: "#f8fafc", visual_preset: "clonexa_dark", theme_mode: "dark", background_mode: "iridescent", gradient_from: "#ff2bd6", gradient_to: "#00ff88", gradient_extra: "#2563eb", gradient_angle: 135, surface_style: "neon" },
    { name: "Voltage Field", primary_color: "#2563eb", secondary_color: "#00ff88", background_color: "#05070a", text_color: "#f8fafc", visual_preset: "field_ops_dark", theme_mode: "dark", background_mode: "gradient", gradient_from: "#2563eb", gradient_to: "#00ff88", gradient_extra: "#05070a", gradient_angle: 145, surface_style: "glass" },
    { name: "Retail Neon", primary_color: "#f97316", secondary_color: "#22c55e", background_color: "#09090b", text_color: "#ffffff", visual_preset: "retail_neon", theme_mode: "dark", background_mode: "iridescent", gradient_from: "#f97316", gradient_to: "#22c55e", gradient_extra: "#7c3aed", gradient_angle: 135, surface_style: "neon" },
    { name: "Hospitality Gold", primary_color: "#f59e0b", secondary_color: "#ef4444", background_color: "#07310f", text_color: "#fff7ed", visual_preset: "hospitality_gold", theme_mode: "dark", background_mode: "iridescent", gradient_from: "#f59e0b", gradient_to: "#ef4444", gradient_extra: "#14532d", gradient_angle: 120, surface_style: "glass" },
    { name: "Minimal Light", primary_color: "#111827", secondary_color: "#2563eb", background_color: "#f8fafc", text_color: "#111827", visual_preset: "minimal_light", theme_mode: "light", background_mode: "gradient", gradient_from: "#f8fafc", gradient_to: "#dbeafe", gradient_extra: "#2563eb", gradient_angle: 135, surface_style: "soft" },
  ];

  function cxValidHex(value, fallback = "#000000") {
    const raw = String(value || "").trim();
    return /^#[0-9a-fA-F]{3}$/.test(raw) || /^#[0-9a-fA-F]{6}$/.test(raw) ? raw : fallback;
  }



  function cxBackgroundStyleFromFormRaw(raw = {}) {
    const direct = String(raw.background_style || raw.backgroundStyle || "").trim();
    const mode = String(raw.background_mode || raw.backgroundMode || "").trim();
    const surface = String(raw.surface_style || raw.surfaceStyle || "").trim();

    const allowed = ["aurora_boreal", "neon_profundo", "holografico", "cyber_grid"];
    if (allowed.includes(direct) && !mode && !surface) return direct;

    if (mode === "iridescent") return "holografico";
    if (mode === "gradient") return "aurora_boreal";

    if (surface === "neon") return "holografico";
    if (surface === "soft") return "cyber_grid";
    if (surface === "default") return "neon_profundo";

    if (mode === "solid") return "neon_profundo";

    return allowed.includes(direct) ? direct : "aurora_boreal";
  }


  function cxResolveBackgroundStyle(raw = {}) {
    const direct = String(raw.background_style || raw.backgroundStyle || "").trim();
    const preset = String(raw.visual_preset || raw.preset_visual || raw.preset || "").trim();
    const mode = String(raw.background_mode || raw.backgroundMode || "").trim();
    const surface = String(raw.surface_style || raw.surfaceStyle || "").trim();

    const allowed = ["aurora_boreal", "neon_profundo", "holografico", "cyber_grid"];

    if (allowed.includes(direct)) return direct;

    const byPreset = {
      clonexa_dark: "aurora_boreal",
      field_ops_dark: "aurora_boreal",
      voltage_field: "aurora_boreal",
      retail_neon: "holografico",
      hospitality_gold: "neon_profundo",
      production_neon: "cyber_grid",
      minimal_light: "cyber_grid",
      custom: "aurora_boreal",
    };

    if (byPreset[preset]) return byPreset[preset];

    if (surface === "neon") return "holografico";
    if (surface === "soft") return "cyber_grid";

    if (mode === "iridescent") return "holografico";
    if (mode === "gradient") return "aurora_boreal";
    if (mode === "solid") return "neon_profundo";

    return "aurora_boreal";
  }



  function cxNormalizeBranding(raw = {}) {
    const styleRaw = String(raw.background_style || raw.backgroundStyle || "").trim();
    const allowedStyles = ["aurora_boreal", "neon_profundo", "holografico", "cyber_grid"];
    const style = allowedStyles.includes(styleRaw) ? styleRaw : "aurora_boreal";

    const fontRaw = String(raw.font_family || raw.fontFamily || "Inter").trim();
    const allowedFonts = ["Inter", "Manrope", "Sora", "Space Grotesk", "Rajdhani", "Orbitron", "Poppins", "Montserrat"];
    const font = allowedFonts.includes(fontRaw) ? fontRaw : "Inter";

    const cardRaw = String(raw.card_style || raw.cardStyle || "glass_premium").trim();
    const allowedCards = ["glass_premium", "neon_border", "soft_solid", "dark_elevated"];
    const card = allowedCards.includes(cardRaw) ? cardRaw : "glass_premium";

    return {
      logo_url: String(raw.logo_url || raw.logoUrl || raw.logo || "").trim(),
      primary_color: cxValidHex(raw.primary_color || raw.color_principal || raw.primaryColor, "#ff2bd6"),
      secondary_color: cxValidHex(raw.secondary_color || raw.color_secundario || raw.secondaryColor, "#00ff88"),
      background_color: cxValidHex(raw.background_color || raw.color_fondo || raw.backgroundColor, "#050509"),
      text_color: cxValidHex(raw.text_color || raw.color_texto || raw.textColor, "#f8fafc"),
      visual_preset: "custom",
      background_style: style,
      font_family: font,
      card_style: card,
      mode: "dark",
      theme_mode: "dark",

      background_mode: style === "holografico" ? "iridescent" : style === "neon_profundo" ? "solid" : "gradient",
      surface_style: card === "neon_border" ? "neon" : card === "soft_solid" ? "soft" : "glass",
      gradient_from: cxValidHex(raw.gradient_from || raw.primary_color, "#ff2bd6"),
      gradient_to: cxValidHex(raw.gradient_to || raw.secondary_color, "#00ff88"),
      gradient_extra: cxValidHex(raw.gradient_extra || raw.background_color, "#050509"),
      gradient_angle: Number(raw.gradient_angle || 135) || 135,
    };
  }

  function cxBrandingBackground(branding) {
    const b = cxNormalizeBranding(branding);

    if (b.background_style === "holografico") {
      return `
        radial-gradient(circle at 0% 0%, ${b.primary_color}88, transparent 34%),
        radial-gradient(circle at 100% 0%, ${b.secondary_color}66, transparent 32%),
        radial-gradient(circle at 50% 100%, ${b.background_color}88, transparent 42%),
        linear-gradient(135deg, ${b.background_color}, ${b.primary_color})
      `;
    }

    if (b.background_style === "cyber_grid") {
      return `
        linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px),
        radial-gradient(circle at 80% 0%, ${b.secondary_color}44, transparent 34%),
        linear-gradient(135deg, ${b.background_color}, #020617)
      `;
    }

    if (b.background_style === "neon_profundo") {
      return `
        radial-gradient(circle at 12% 8%, ${b.primary_color}55, transparent 32%),
        radial-gradient(circle at 90% 12%, ${b.secondary_color}44, transparent 32%),
        linear-gradient(135deg, ${b.background_color}, #050509)
      `;
    }

    return `
      radial-gradient(circle at 0% 0%, ${b.primary_color}55, transparent 32%),
      radial-gradient(circle at 100% 0%, ${b.secondary_color}44, transparent 32%),
      linear-gradient(135deg, ${b.background_color}, ${b.secondary_color}22)
    `;
  }



  function cxFontVisualProfile(fontFamily) {
    const map = {
      Inter: { family: "Inter, system-ui, sans-serif", heading: "-.04em", label: ".18em", weight: "800", transform: "none" },
      Manrope: { family: "Manrope, Inter, system-ui, sans-serif", heading: "-.035em", label: ".14em", weight: "850", transform: "none" },
      Sora: { family: "Sora, Inter, system-ui, sans-serif", heading: "-.025em", label: ".2em", weight: "800", transform: "none" },
      "Space Grotesk": { family: "'Space Grotesk', Inter, system-ui, sans-serif", heading: "-.02em", label: ".22em", weight: "800", transform: "uppercase" },
      Rajdhani: { family: "Rajdhani, Inter, system-ui, sans-serif", heading: ".02em", label: ".24em", weight: "900", transform: "uppercase" },
      Orbitron: { family: "Orbitron, Rajdhani, Inter, system-ui, sans-serif", heading: ".035em", label: ".28em", weight: "900", transform: "uppercase" },
      Poppins: { family: "Poppins, Inter, system-ui, sans-serif", heading: "-.035em", label: ".14em", weight: "800", transform: "none" },
      Montserrat: { family: "Montserrat, Inter, system-ui, sans-serif", heading: "-.02em", label: ".18em", weight: "900", transform: "uppercase" },
    };
    return map[fontFamily] || map.Inter;
  }

  function cxSurfaceStyle(branding) {
    const b = cxNormalizeBranding(branding);

    if (b.card_style === "neon_border") {
      return `
        background:linear-gradient(145deg, ${b.primary_color}1f, rgba(255,255,255,.055), ${b.secondary_color}14);
        border:1px solid ${b.primary_color}88;
        box-shadow:0 0 42px ${b.primary_color}3f, inset 0 0 0 1px rgba(255,255,255,.08);
        backdrop-filter:blur(18px) saturate(1.35);
      `;
    }

    if (b.card_style === "soft_solid") {
      return `
        background:linear-gradient(145deg, rgba(255,255,255,.82), rgba(255,255,255,.52));
        color:#0f172a;
        border:1px solid rgba(255,255,255,.72);
        box-shadow:0 24px 80px rgba(15,23,42,.16);
      `;
    }

    if (b.card_style === "dark_elevated") {
      return `
        background:linear-gradient(145deg, rgba(2,6,23,.88), rgba(15,23,42,.72));
        border:1px solid rgba(255,255,255,.12);
        box-shadow:0 28px 90px rgba(0,0,0,.42);
      `;
    }

    return `
      background:linear-gradient(145deg, rgba(255,255,255,.105), rgba(255,255,255,.04));
      border:1px solid rgba(255,255,255,.14);
      backdrop-filter:blur(22px) saturate(1.25);
      box-shadow:0 24px 80px rgba(0,0,0,.28), inset 0 0 0 1px rgba(255,255,255,.035);
    `;
  }

  function cxRenderLogo(company, branding) {
    const b = cxNormalizeBranding(branding);
    const initials = escapeHtml(cxCompanyInitials(company));

    if (!b.logo_url) return initials;

    return `
      <img src="${escapeHtml(b.logo_url)}"
        alt="logo"
        style="width:100%;height:100%;object-fit:contain;border-radius:16px;padding:7px"
        onerror="this.style.display='none';this.parentElement.dataset.logoFallback='${initials}';this.parentElement.textContent='${initials}';"
      />
    `;
  }

  function cxResizeLogoToDataUrl(file, maxSize = 512, quality = 0.86) {
    return new Promise((resolve, reject) => {
      if (!file) return reject(new Error("No se seleccionó archivo."));
      if (!/^image\/(png|jpeg|jpg|webp|svg\+xml)$/.test(file.type)) {
        return reject(new Error("Formato no soportado. Usa PNG, JPG, WEBP o SVG."));
      }

      const reader = new FileReader();

      reader.onload = () => {
        if (file.type === "image/svg+xml") {
          resolve(String(reader.result));
          return;
        }

        const img = new Image();

        img.onload = () => {
          const scale = Math.min(1, maxSize / Math.max(img.width, img.height));
          const width = Math.max(1, Math.round(img.width * scale));
          const height = Math.max(1, Math.round(img.height * scale));

          const canvas = document.createElement("canvas");
          canvas.width = width;
          canvas.height = height;

          const ctx = canvas.getContext("2d");
          ctx.clearRect(0, 0, width, height);
          ctx.drawImage(img, 0, 0, width, height);

          resolve(canvas.toDataURL("image/webp", quality));
        };

        img.onerror = () => reject(new Error("No se pudo procesar la imagen."));
        img.src = String(reader.result);
      };

      reader.onerror = () => reject(new Error("No se pudo leer el archivo."));
      reader.readAsDataURL(file);
    });
  }

  function cxCompanyInitials(company) {
    return String(company?.name || "CX")
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0] || "")
      .join("")
      .toUpperCase() || "CX";
  }

  function cxBrandingPreview(company, branding, large = false) {
    const b = cxNormalizeBranding(branding);
    const logo = cxRenderLogo(company, b);
    const fontProfile = cxFontVisualProfile(b.font_family);

    return `
      <div class="cx-brand-preview-shell" style="
        background:${cxBrandingBackground(b)};
        color:${escapeHtml(b.text_color)};
        font-family:${escapeHtml(fontProfile.family)};
        border:1px solid rgba(255,255,255,.14);
        border-radius:26px;
        overflow:hidden;
        min-height:${large ? "520px" : "360px"};
        box-shadow:0 30px 100px rgba(0,0,0,.32);
      ">
        <div style="display:grid;grid-template-columns:210px 1fr;min-height:inherit">
          <aside style="padding:20px;border-right:1px solid rgba(255,255,255,.12);background:linear-gradient(180deg,rgba(255,255,255,.08),rgba(255,255,255,.02))">
            <div style="
              width:58px;
              height:58px;
              border-radius:18px;
              display:grid;
              place-items:center;
              font-weight:900;
              background:${escapeHtml(b.primary_color)};
              color:white;
              margin-bottom:18px;
              box-shadow:0 0 34px ${escapeHtml(b.primary_color)}77;
            ">${logo}</div>
            <strong>${escapeHtml(company?.name || "Empresa")}</strong>
            <p style="margin:6px 0 18px;opacity:.68">${escapeHtml(b.visual_preset)}</p>
            <div style="display:grid;gap:9px">
              ${["Dashboard", "Personal", "Inventario", "Tareas", "Reportes"].map((item, index) => `
                <div style="
                  padding:11px 12px;
                  border-radius:14px;
                  background:${index === 0 ? `${b.primary_color}30` : "rgba(255,255,255,.07)"};
                  border:${index === 0 ? `1px solid ${b.primary_color}` : "1px solid rgba(255,255,255,.10)"};
                  box-shadow:${index === 0 ? `0 0 26px ${b.primary_color}33` : "none"};
                  backdrop-filter:blur(12px);
                ">${escapeHtml(item)}</div>
              `).join("")}
            </div>
          </aside>

          <main style="padding:22px">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:20px">
              <div>
                <div style="letter-spacing:.16em;text-transform:uppercase;color:${escapeHtml(b.secondary_color)};font-weight:900;font-size:12px">Panel cliente</div>
                <h2 style="margin:8px 0 0;font-size:${large ? "36px" : "28px"}">Operación en tiempo real</h2>
              </div>
              <span style="
                display:inline-flex;
                border-radius:999px;
                padding:7px 12px;
                background:${escapeHtml(b.secondary_color)};
                color:#03110a;
                font-weight:900;
              ">LIVE</span>
            </div>

            <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:18px">
              ${[
                ["Personal activo", "18"],
                ["Tareas abiertas", "7"],
                ["Inventario", "OK"],
                ["Actividad hoy", "92%"],
              ].map(([label, value]) => `
                <div style="padding:16px;border-radius:18px;border:1px solid rgba(255,255,255,.14);${cxSurfaceStyle(b)}">
                  <small style="display:block;opacity:.68;margin-bottom:8px">${escapeHtml(label)}</small>
                  <strong style="font-size:25px">${escapeHtml(value)}</strong>
                </div>
              `).join("")}
            </div>

            <button type="button" style="
              border:0;
              border-radius:16px;
              padding:13px 18px;
              font-weight:900;
              color:white;
              background:${escapeHtml(b.primary_color)};
              box-shadow:0 15px 42px ${escapeHtml(b.primary_color)}55;
            ">Crear tarea operativa</button>

            <div style="margin-top:18px;padding:15px;border-radius:18px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12)">
              ${[
                ["Supervisor asignado", "Activo"],
                ["Material pendiente", "3 solicitudes"],
                ["Último check-in", "Hace 8 min"],
              ].map(([left, right]) => `
                <div style="display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.08)">
                  <span>${escapeHtml(left)}</span>
                  <strong style="color:${escapeHtml(b.secondary_color)}">${escapeHtml(right)}</strong>
                </div>
              `).join("")}
            </div>
          </main>
        </div>
      </div>
    `;
  }



  function renderBrandingStudio(company, branding) {
    const b = cxNormalizeBranding(branding);

    const colorControl = (key, label, value) => `
      <div style="padding:13px;border:1px solid rgba(255,255,255,.1);border-radius:18px;background:rgba(0,0,0,.18)">
        <label style="display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:rgba(248,250,252,.68);margin-bottom:8px">${escapeHtml(label)}</label>
        <div style="display:grid;grid-template-columns:56px 1fr;gap:10px;align-items:center">
          <input type="color" value="${escapeHtml(value)}" data-branding-color="${escapeHtml(key)}" style="width:56px;height:42px;border:0;background:transparent">
          <input class="cx-input" name="${escapeHtml(key)}" data-branding-hex="${escapeHtml(key)}" type="text" value="${escapeHtml(value)}">
        </div>
      </div>
    `;

    const styleOption = (value, label) => `
      <option value="${escapeHtml(value)}" ${b.background_style === value ? "selected" : ""}>${escapeHtml(label)}</option>
    `;

    const fontOption = (value) => `
      <option value="${escapeHtml(value)}" ${b.font_family === value ? "selected" : ""}>${escapeHtml(value)}</option>
    `;

    const cardOption = (value, label) => `
      <option value="${escapeHtml(value)}" ${b.card_style === value ? "selected" : ""}>${escapeHtml(label)}</option>
    `;

    const logoPreview = b.logo_url
      ? `<div style="display:flex;align-items:center;gap:12px">
          <div style="width:64px;height:64px;border-radius:18px;display:grid;place-items:center;background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.12);overflow:hidden">
            ${cxRenderLogo(company, b)}
          </div>
          <div>
            <strong>Logo cargado</strong>
            <p class="cx-muted" style="margin:4px 0 0;font-size:12px">Puedes reemplazarlo con una URL o archivo nuevo.</p>
          </div>
        </div>`
      : `<div class="cx-muted">Sin logo cargado. Se usar? la inicial de la empresa.</div>`;

    return `
      <section style="
        padding:20px;
        border:1px solid rgba(255,255,255,.12);
        border-radius:26px;
        background:
          radial-gradient(circle at 0% 0%, ${escapeHtml(b.primary_color)}22, transparent 34%),
          radial-gradient(circle at 100% 0%, ${escapeHtml(b.secondary_color)}16, transparent 34%),
          rgba(255,255,255,.035);
      ">
        <div class="cx-card-head">
          <div>
            <h2>Branding Studio</h2>
            <p>Configura logo, colores, estilo visual, fuente y tarjetas del panel cliente.</p>
          </div>
          <button class="cx-btn cx-btn-small" type="button" data-open-branding-preview>Ver as? quedar?</button>
        </div>

        <form id="brandingForm" style="display:grid;gap:14px">
          <input type="hidden" name="visual_preset" value="custom" />
          <input type="hidden" name="mode" value="dark" />
          <input type="hidden" name="theme_mode" value="dark" />

          <section style="padding:16px;border:1px solid rgba(255,255,255,.12);border-radius:22px;background:rgba(255,255,255,.035);display:grid;gap:12px">
            <div class="cx-card-head">
              <div>
                <h3>Logo</h3>
                <p>Imagen del panel cliente. Se ajusta autom?ticamente sin deformarse.</p>
              </div>
            </div>

            ${logoPreview}

            <label>Logo URL
              <input name="logo_url" type="text" value="${escapeHtml(b.logo_url)}" data-branding-basic placeholder="https://... o /static/logo.png" />
            </label>

            <label>Subir logo
              <input id="brandingLogoUpload" type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" />
            </label>
          </section>

          <section style="padding:16px;border:1px solid rgba(255,255,255,.12);border-radius:22px;background:rgba(255,255,255,.035);display:grid;gap:12px">
            <div>
              <h3>Colores</h3>
              <p class="cx-muted">Paleta principal aplicada al panel cliente y tarjetas.</p>
            </div>

            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px">
              ${colorControl("primary_color", "Color principal", b.primary_color)}
              ${colorControl("secondary_color", "Color secundario", b.secondary_color)}
              ${colorControl("background_color", "Color fondo", b.background_color)}
              ${colorControl("text_color", "Color texto", b.text_color)}
            </div>
          </section>

          <section style="padding:16px;border:1px solid rgba(255,255,255,.12);border-radius:22px;background:rgba(255,255,255,.035);display:grid;gap:12px">
            <div>
              <h3>Estilo visual</h3>
              <p class="cx-muted">Se guarda como background_style y define el fondo general del panel.</p>
            </div>

            <label>Estilo del panel cliente
              <select name="background_style" data-branding-basic>
                ${styleOption("aurora_boreal", "Aurora boreal / degradado futurista")}
                ${styleOption("neon_profundo", "Ne?n profundo / s?lido premium")}
                ${styleOption("holografico", "Tornasol hologr?fico")}
                ${styleOption("cyber_grid", "Cyber grid / tecnol?gico")}
              </select>
            </label>
          </section>

          <section style="padding:16px;border:1px solid rgba(255,255,255,.12);border-radius:22px;background:rgba(255,255,255,.035);display:grid;gap:12px">
            <div>
              <h3>Fuente y tarjetas</h3>
              <p class="cx-muted">Se aplica al preview, CRM y /client por empresa.</p>
            </div>

            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px">
              <label>Fuente del panel
                <select name="font_family" data-branding-basic>
                  ${fontOption("Inter")}
                  ${fontOption("Manrope")}
                  ${fontOption("Sora")}
                  ${fontOption("Space Grotesk")}
                  ${fontOption("Rajdhani")}
                  ${fontOption("Orbitron")}
                  ${fontOption("Poppins")}
                  ${fontOption("Montserrat")}
                </select>
              </label>

              <label>Estilo de tarjetas
                <select name="card_style" data-branding-basic>
                  ${cardOption("glass_premium", "Glass premium")}
                  ${cardOption("neon_border", "Neon border")}
                  ${cardOption("soft_solid", "Soft solid")}
                  ${cardOption("dark_elevated", "Dark elevated")}
                </select>
              </label>
            </div>
          </section>

          <button class="cx-btn cx-btn-primary" type="submit">Guardar branding</button>
        </form>

        <div style="margin-top:20px">
          <h3>Vista previa del panel cliente</h3>
          <div id="brandingLivePreview">${cxBrandingPreview(company, b, false)}</div>
        </div>
      </section>

      <dialog id="brandingPreviewModal" style="
        width:min(1120px,calc(100vw - 40px));
        border:1px solid rgba(255,255,255,.18);
        border-radius:28px;
        padding:0;
        background:#050509;
        color:white;
      ">
        <div style="padding:18px">
          <div class="cx-card-head">
            <div>
              <h2>As? quedar? el panel cliente</h2>
              <p>Preview visual con el branding actual del formulario.</p>
            </div>
            <button class="cx-btn cx-btn-small" type="button" data-close-branding-preview>Cerrar</button>
          </div>
          <div id="brandingModalPreview">${cxBrandingPreview(company, b, true)}</div>
        </div>
      </dialog>
    `;
  }

  function cxBrandingFromForm() {
    const form = el("#brandingForm");
    if (!form) return cxNormalizeBranding({});

    const raw = Object.fromEntries(new FormData(form).entries());
    const b = cxNormalizeBranding(raw);

    return {
      logo_url: b.logo_url,
      primary_color: b.primary_color,
      secondary_color: b.secondary_color,
      background_color: b.background_color,
      text_color: b.text_color,
      visual_preset: "custom",
      background_style: b.background_style,
      font_family: b.font_family,
      card_style: b.card_style,
      mode: "dark",
      theme_mode: "dark",
    };
  }

  function cxUpdateBrandingPreview() {
    const form = el("#brandingForm");
    const box = el("#brandingLivePreview");
    if (!form || !box) return;

    const company = state.companies.find((c) => c.id === state.selectedCompanyId) || {};
    const branding = cxBrandingFromForm();
    box.innerHTML = cxBrandingPreview(company, branding, false);

    const modalBox = el("#brandingModalPreview");
    if (modalBox) modalBox.innerHTML = cxBrandingPreview(company, branding, true);
  }

  function renderCompanyCrmPreview(company, exp, branding) {
    const b = cxNormalizeBranding(branding || {});
    const modulesCount = moduleCodesForCompany(company.id).length;

    return `
      <section style="
        padding:18px;
        border:1px solid rgba(255,255,255,.12);
        border-radius:26px;
        background:rgba(255,255,255,.035);
      ">
        <div class="cx-card-head">
          <div>
            <h2>Así se verá el panel cliente</h2>
            <p>Preview CRM aplicada con el branding guardado por empresa.</p>
          </div>
          <a class="cx-btn cx-btn-primary" href="/client?company_id=${escapeHtml(company.id)}" target="_blank" rel="noreferrer">Abrir /client</a>
        </div>

        ${cxBrandingPreview(company, b, true)}

        <div class="cx-detail-grid" style="margin-top:18px">
          <div class="cx-kv"><span>Empresa</span><strong>${escapeHtml(company.name)}</strong></div>
          <div class="cx-kv"><span>Slug</span><strong>${escapeHtml(company.slug)}</strong></div>
          <div class="cx-kv"><span>Paquete</span><strong>${escapeHtml(packageForCompany(company))}</strong></div>
          <div class="cx-kv"><span>Módulos activos</span><strong>${escapeHtml(modulesCount)}</strong></div>
          <div class="cx-kv"><span>Fuente</span><strong>${escapeHtml(b.font_family)}</strong></div>
          <div class="cx-kv"><span>Tarjetas</span><strong>${escapeHtml(b.card_style)}</strong></div>
          <div class="cx-kv"><span>URL cliente</span><strong>/client</strong></div>
          <div class="cx-kv"><span>Branding</span><strong>${b.visual_preset && b.primary_color ? "Configurado" : "Pendiente"}</strong></div>
        </div>

        <div class="cx-actions" style="margin-top:14px">
          <button class="cx-btn" data-detail-tab="branding" type="button">Editar branding</button>
          <button class="cx-btn" data-ensure-defaults="${escapeHtml(company.id)}" type="button">Regenerar defaults CRM</button>
        </div>
      </section>
    `;
  }

  document.addEventListener("click", (event) => {
    const paletteButton = event.target.closest("[data-branding-palette]");
    if (paletteButton && el("#brandingForm")) {
      const palette = CX_BRANDING_PALETTES[Number(paletteButton.dataset.brandingPalette)];
      if (!palette) return;

      Object.entries(palette).forEach(([key, value]) => {
        const input = el(`#brandingForm [name="${key}"]`);
        if (input) {
          input.value = value;
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });

      cxUpdateBrandingPreview();
      return;
    }

    const openPreview = event.target.closest("[data-open-branding-preview]");
    if (openPreview) {
      const modal = el("#brandingPreviewModal");
      if (modal) {
        cxUpdateBrandingPreview();
        modal.showModal();
      }
      return;
    }

    const closePreview = event.target.closest("[data-close-branding-preview]");
    if (closePreview) {
      el("#brandingPreviewModal")?.close();
      return;
    }
  });

  document.addEventListener("input", (event) => {
    const color = event.target.closest("[data-branding-color]");
    if (color) {
      const key = color.dataset.brandingColor;
      const hex = el(`#brandingForm [data-branding-hex="${key}"]`);
      if (hex) hex.value = color.value;
      cxUpdateBrandingPreview();
      return;
    }

    const hex = event.target.closest("[data-branding-hex]");
    if (hex) {
      const key = hex.dataset.brandingHex;
      const value = cxValidHex(hex.value, "");
      const color = el(`#brandingForm [data-branding-color="${key}"]`);
      if (value && color) color.value = value;
      cxUpdateBrandingPreview();
      return;
    }

    if (event.target.closest("#brandingForm")) {
      cxUpdateBrandingPreview();
    }
  });

  document.addEventListener("change", async (event) => {
    if (event.target && event.target.id === "brandingLogoUpload") {
      try {
        const file = event.target.files && event.target.files[0];
        const dataUrl = await cxResizeLogoToDataUrl(file);
        const logoInput = el(`#brandingForm [name="logo_url"]`);
        if (logoInput) {
          logoInput.value = dataUrl;
          logoInput.dispatchEvent(new Event("input", { bubbles: true }));
          logoInput.dispatchEvent(new Event("change", { bubbles: true }));
        }
        cxUpdateBrandingPreview();
        showToast("Logo cargado y ajustado.");
      } catch (error) {
        showToast(error.message || "No se pudo cargar el logo.", "error");
      }
      return;
    }
  });
  document.addEventListener("change", (event) => {
    if (event.target.closest("#brandingForm")) {
      cxUpdateBrandingPreview();
    }
  });

  


  function renderCompanyDetailTab(company) {
    const node = el("#companyDetailContent");
    if (!node) return;

    const modules = state.companyModules.get(company.id) || [];
    const users = state.companyUsers.get(company.id);
    const experience = state.companyExperience.get(company.id);
    const tab = state.activeDetailTab;

    if (tab === "resumen") {
      node.innerHTML = `
        <div class="cx-detail-grid">
          <div class="cx-kv"><span>Empresa</span><strong>${escapeHtml(company.name)}</strong></div>
          <div class="cx-kv"><span>Slug</span><strong>${escapeHtml(company.slug)}</strong></div>
          <div class="cx-kv"><span>Estado</span><strong>${escapeHtml(company.status)}</strong></div>
          <div class="cx-kv"><span>Plan</span><strong>${escapeHtml(company.plan || "Ã¢â‚¬â€")}</strong></div>
          <div class="cx-kv"><span>Timezone</span><strong>${escapeHtml(company.timezone)}</strong></div>
          <div class="cx-kv"><span>Paquete detectado</span><strong>${escapeHtml(packageForCompany(company))}</strong></div>
          <div class="cx-kv"><span>Módulos activos</span><strong>${escapeHtml(moduleCodesForCompany(company.id).length)}</strong></div>
          <div class="cx-kv"><span>Acceso Maestro</span><strong>${ownerAccessBadge(users)}</strong></div>
        </div>
      `;
      return;
    }

    if (tab === "usuarios") {
      renderCompanyUsersPanel(node, company, users);
      return;
    }

    
    
    
    
    
    
  window.__cxCompanyModuleUx = window.__cxCompanyModuleUx || {
    search: new Map(),
    filter: new Map(),
  };

  const CX_MODULE_KEYWORDS = {
    core: "base nucleo estructura empresa tenant sistema principal",
    workforce: "personal empleados operarios trabajadores usuarios agregar personal crear personal equipo humano",
    field: "campo operacion campo tecnico ruta evidencia actividad externo cuadrilla",
    gps: "gps ubicacion ubicaciones mapa ruta seguimiento localizacion geolocalizacion tecnico campo",
    payroll: "nomina pago pagos quincena quincenal salario horas extras corte liquidacion",
    day_closing: "cierre dia cierre diario ventas resumen caja turno",
    hospitality: "bar restaurante hospitality mesas pedidos mesero cuenta",
    loyalty: "fidelizacion clientes puntos beneficios lealtad recurrentes",
    orders: "pedidos ordenes comandas compra solicitud cliente mesa",
    tables: "mesas mesa cuenta qr restaurante bar",
    bots: "bot bots telegram whatsapp automatizacion mensajes entrada",
    qr: "qr código mesa escanear acceso link",
    inventory: "inventario stock existencias productos materiales almacen",
    materials: "materiales material solicitud entregar devolver herramientas stock tecnico",
    stock: "stock inventario minimo existencias alerta",
    costs: "costos costo produccion gasto margen referencia",
    production: "produccion fabricar referencias tiempos productividad costos",
    references: "referencias productos servicios catálogo sku",
    crm: "crm panel cliente seguimiento gestion comercial campo",
    kpis: "kpi kpis indicadores metricas rendimiento tablero",
    reports: "reportes informes historicos auditoria exportar",
    commercial_closing: "cierre comercial ventas resultados seguimiento comercial",
    requests: "solicitudes solicitud requerimientos aprobaciones pedir material",
    retail: "retail tiendas ventas mostrador solicitudes inventario",
    sales: "ventas venta comercial ingresos pedidos",
    stores: "tiendas sucursales puntos venta locales",
  };

  function cxGetCompanyModuleFilter(companyId) {
    return window.__cxCompanyModuleUx.filter.get(companyId) || "all";
  }

  function cxGetCompanyModuleSearch(companyId) {
    return window.__cxCompanyModuleUx.search.get(companyId) || "";
  }

  function cxSetCompanyModuleFilter(companyId, value) {
    window.__cxCompanyModuleUx.filter.set(companyId, value || "all");
  }

  function cxSetCompanyModuleSearch(companyId, value) {
    window.__cxCompanyModuleUx.search.set(companyId, value || "");
  }

  function cxModuleSearchText(module, meta) {
    const code = String(module?.code || "").trim();
    return [
      code,
      meta?.name,
      meta?.description,
      meta?.categoryLabel,
      module?.name,
      module?.description,
      module?.category,
      CX_MODULE_KEYWORDS[code] || "",
    ].filter(Boolean).join(" ").toLowerCase();
  }

  function cxBindCompanyModulesUxEvents() {
    if (window.__cxCompanyModulesUxEventsBound) return;
    window.__cxCompanyModulesUxEventsBound = true;

    document.addEventListener("input", (event) => {
      const input = event.target.closest("[data-cx-company-module-search]");
      if (!input) return;

      const companyId = input.dataset.companyId;
      cxSetCompanyModuleSearch(companyId, input.value || "");

      if (typeof renderCompanies === "function") renderCompanies();
    });

    document.addEventListener("click", (event) => {
      const filterButton = event.target.closest("[data-cx-company-module-filter]");
      if (!filterButton) return;

      const companyId = filterButton.dataset.companyId;
      const filter = filterButton.dataset.filter || "all";

      cxSetCompanyModuleFilter(companyId, filter);

      if (typeof renderCompanies === "function") renderCompanies();
    });
  }

  cxBindCompanyModulesUxEvents();


    
    if (tab === "módulos") {
      const companyRows = cxCompanyModuleRowMap(company.id);
      const allModules = state.modules.length ? state.modules.map(normalizeModule) : modules.map(normalizeModule);
      const activeModules = allModules.filter((module) => {
        const row = companyRows.get(module.code);
        return !!row && row.enabled !== false;
      });

      const searchValue = cxGetCompanyModuleSearch(company.id);
      const activeFilter = cxGetCompanyModuleFilter(company.id);
      const query = String(searchValue || "").trim().toLowerCase();

      const visibleModules = allModules.filter((module) => {
        const meta = cxModuleMeta(module);
        const row = companyRows.get(module.code);
        const enabled = !!row && row.enabled !== false;

        if (activeFilter === "active" && !enabled) return false;
        if (activeFilter === "inactive" && enabled) return false;

        if (!query) return true;

        return cxModuleSearchText(module, meta).includes(query);
      });

      node.innerHTML = `
        <div class="cx-card-head" style="margin-bottom:16px">
          <div>
            <h3>Módulos de ${escapeHtml(company.name)}</h3>
            <p>Activa o desactiva servicios para esta empresa. Los cambios afectan el CRM y el portal cliente.</p>
          </div>
          <span class="cx-badge cx-badge-primary">${escapeHtml(activeModules.length)} activos</span>
        </div>

        <section class="cx-panel" style="margin-bottom:18px">
          <div class="cx-card-head">
            <div>
              <h3>Módulos activos</h3>
              <p>Servicios prendidos actualmente para ${escapeHtml(company.name)}.</p>
            </div>
            <span class="cx-badge cx-badge-live">${escapeHtml(activeModules.length)} activos</span>
          </div>

          <div class="cx-actions" style="margin-top:14px;gap:10px;flex-wrap:wrap">
            ${activeModules.length ? activeModules.map((module) => {
              const meta = cxModuleMeta(module);
              return `
                <button
                  class="cx-btn"
                  type="button"
                  title="Desactivar ${escapeHtml(meta.name)}"
                  data-cx-company-module-toggle
                  data-company-id="${escapeHtml(company.id)}"
                  data-module-code="${escapeHtml(module.code)}"
                  data-action="deactivate"
                >
                  ${escapeHtml(meta.badge)} ? ${escapeHtml(meta.name)} ?
                </button>
              `;
            }).join("") : `
              <span class="cx-empty-state">No hay módulos activos. Activa servicios desde el catálogo inferior.</span>
            `}
          </div>
        </section>

        <section class="cx-panel" style="margin-bottom:18px">
          <div class="cx-card-head">
            <div>
              <h3>Buscar módulo</h3>
              <p>Busca por nombre, categoría o necesidad operativa.</p>
            </div>
          </div>

          <div style="display:grid;grid-template-columns:1fr auto;gap:12px;margin-top:14px;align-items:center">
            <label style="position:relative;display:block">
              <span style="position:absolute;left:16px;top:50%;transform:translateY(-50%);opacity:.7">?</span>
              <input
                data-cx-company-module-search
                data-company-id="${escapeHtml(company.id)}"
                value="${escapeHtml(searchValue)}"
                placeholder="Buscar: agregar personal, nomina, ubicacion, materiales, pedidos, qr..."
                style="width:100%;padding-left:44px"
              />
            </label>

            <div class="cx-actions" style="gap:8px">
              ${["all", "active", "inactive"].map((filter) => {
                const label = filter === "all" ? "Todos" : filter === "active" ? "Activos" : "Inactivos";
                const activeClass = activeFilter === filter ? "cx-btn-primary" : "";
                return `
                  <button
                    class="cx-btn ${activeClass}"
                    type="button"
                    data-cx-company-module-filter
                    data-company-id="${escapeHtml(company.id)}"
                    data-filter="${escapeHtml(filter)}"
                  >
                    ${escapeHtml(label)}
                  </button>
                `;
              }).join("")}
            </div>
          </div>

          <p style="margin-top:12px;opacity:.72">
            Mostrando ${escapeHtml(visibleModules.length)} de ${escapeHtml(allModules.length)} módulos.
          </p>
        </section>

        <div class="cx-module-grid">
          ${visibleModules.length ? visibleModules.map((module) => {
            const meta = cxModuleMeta(module);
            const row = companyRows.get(module.code);
            const enabled = !!row && row.enabled !== false;
            const action = enabled ? "deactivate" : "activate";

            return `
              <article class="cx-module-chip">
                <div class="cx-card-head">
                  <div>
                    <strong>${escapeHtml(meta.name)}</strong>
                    <p>${escapeHtml(module.code)}</p>
                  </div>
                  <span class="cx-badge">${escapeHtml(meta.badge)}</span>
                </div>

                <p>${escapeHtml(meta.description)}</p>

                <div class="cx-actions">
                  ${enabled ? `<span class="cx-badge cx-badge-live">Activo</span>` : `<span class="cx-badge">Inactivo</span>`}
                  <span class="cx-badge">${escapeHtml(meta.categoryLabel)}</span>
                  <button class="cx-btn" type="button" data-cx-module-info data-module-code="${escapeHtml(module.code)}">Info</button>
                  <button
                    class="cx-btn ${enabled ? "" : "cx-btn-primary"}"
                    type="button"
                    data-cx-company-module-toggle
                    data-company-id="${escapeHtml(company.id)}"
                    data-module-code="${escapeHtml(module.code)}"
                    data-action="${escapeHtml(action)}"
                  >
                    ${enabled ? "Desactivar" : "Activar"}
                  </button>
                </div>
              </article>
            `;
          }).join("") : `
            <div class="cx-empty-state" style="grid-column:1/-1">
              No hay resultados para la busqueda actual.
            </div>
          `}
        </div>
      `;
      return;
    }

    if (tab === "paquete") {
      const detectedPackageCode = packageForCompany(company);
      const currentPkg = cxFindPackageByCodeOrName(detectedPackageCode);
      const needsPackageCapabilities = currentPkg && !state.packageMiniPanelSettings.has(currentPkg.id);

      const packageOptions = state.packages.map((pkg) => {
        const normalized = normalizePackage(pkg);
        const selected = String(normalized.code || "").toLowerCase() === String(detectedPackageCode || "").toLowerCase()
          || String(normalized.name || "").toLowerCase() === String(detectedPackageCode || "").toLowerCase();
        return `<option value="${escapeHtml(normalized.code)}" ${selected ? "selected" : ""}>${escapeHtml(normalized.name)} (${escapeHtml(normalized.code)})</option>`;
      }).join("");

      const inheritedCapabilities = needsPackageCapabilities
        ? `<div class="cx-empty-state" style="margin-top:12px">Cargando capacidades heredadas del paquete...</div>`
        : cxRenderCompanyPackageInheritedCapabilities(company);

      node.innerHTML = `
        <section class="cx-mini-card">
          <div class="cx-card-head">
            <div>
              <strong>Asignar paquete a empresa</strong>
              <p>Esta seccion solo aplica paquetes ya creados desde Admin V2 -> Paquetes. No arma paquetes aqui.</p>
            </div>
            <span class="cx-badge">${escapeHtml(detectedPackageCode || "Sin paquete")}</span>
          </div>

          <form class="cx-form" id="activatePackageForm" style="margin-top:12px">
            <label>Seleccionar paquete creado para ${escapeHtml(company.name)}
              <select name="package_code" required>
                <option value="">Seleccionar paquete</option>
                ${packageOptions}
              </select>
            </label>
            <button class="cx-btn cx-btn-primary" type="submit">Activar paquete</button>
          </form>
        </section>

        <section class="cx-mini-card" style="margin-top:12px">
          <strong>Paquete detectado actual</strong>
          <p>${escapeHtml(detectedPackageCode || "Sin paquete")}</p>
        </section>

        ${inheritedCapabilities}
      `;

      if (needsPackageCapabilities) {
        loadPackageMiniPanelSettings(currentPkg.id).then(() => {
          if (state.selectedCompanyId === company.id && state.activeDetailTab === "paquete") {
            renderCompanyDetailTab(company);
          }
        }).catch(() => null);
      }
      return;
    }

    if (tab === "branding") {
      const branding = cxNormalizeBranding(experience && !experience.unavailable ? (experience.branding || {}) : {});
      node.innerHTML = renderBrandingStudio(company, branding);
      setTimeout(cxUpdateBrandingPreview, 0);
      return;
    }
    if (tab === "crm") {
      const exp = experience && !experience.unavailable ? experience : {};
      const branding = cxNormalizeBranding(exp.branding || {});
      node.innerHTML = renderCompanyCrmPreview(company, exp, branding);
      return;
    }
    if (tab === "accesos") {
      const key = botConfigKey(company.id, "telegram");
      if (!state.companyBotConfigs.has(key)) {
        state.companyBotConfigs.set(key, { loading: true });
        loadTelegramBotConfig(company.id, true).then(() => {
          if (state.selectedCompanyId === company.id && state.activeDetailTab === "accesos") {
            renderCompanyDetailTab(company);
          }
        });
      }
      node.innerHTML = renderCompanyAccessPanel(company);
      return;
    }
  }

  function renderCompanyUsersPanel(node, company, users) {
    if (!Array.isArray(users)) {
      node.innerHTML = `
        <div class="cx-empty-state">
          No se pudo cargar el acceso maestro de esta empresa.
          <br><small>La consola sigue operativa aunque este endpoint no responda.</small>
        </div>
      `;
      return;
    }

    const info = ownerAccessInfo(users);
    const owner = info.owner;
    const warning = info.companyAdmins && info.companyAdmins.length > 1
      ? `<div class="cx-alert" style="display:block;margin-bottom:14px">Hay mÃƒÂ¡s de un acceso maestro. Se recomienda dejar solo uno.</div>`
      : "";

    const explanation = `
      <div class="cx-empty-state" style="text-align:left;margin-bottom:14px">
        <strong>Usuario dueÃƒÂ±o / encargado</strong><br>
        Este acceso pertenece al dueÃƒÂ±o o encargado de la empresa.
        El personal operativo se gestiona desde el panel de la empresa.
      </div>
    `;

    if (!owner) {
      node.innerHTML = `
        ${explanation}
        <div class="cx-layout-two">
          <div>
            <div class="cx-empty-state">Esta empresa no tiene acceso maestro creado.</div>
          </div>
          <aside>
            <form class="cx-form" id="createUserForm">
              <h3>Crear acceso maestro</h3>
              <input name="role" type="hidden" value="company_admin" />
              <input name="status" type="hidden" value="active" />
              <label>Nombre del encargado
                <input name="full_name" type="text" required placeholder="${escapeHtml(company.name)} Admin" />
              </label>
              <label>Email
                <input name="email" type="email" required placeholder="admin@empresa.com" />
              </label>
              <label>ContraseÃƒÂ±a temporal
                <div style="display:flex;gap:8px;align-items:center">
                  <input name="password" type="text" required value="${escapeHtml(generateTempPassword(company.slug))}" />
                  <button class="cx-btn cx-btn-small" data-generate-password-for-form="#createUserForm" type="button">Generar clave</button>
                </div>
              </label>
              <button class="cx-btn cx-btn-primary" type="submit">Crear acceso maestro</button>
            </form>
          </aside>
        </div>
      `;
      return;
    }

    const nextStatus = String(owner.status || "active").toLowerCase() === "active" ? "inactive" : "active";
    const nextStatusLabel = nextStatus === "inactive" ? "Desactivar acceso" : "Activar acceso";

    node.innerHTML = `
      ${warning}
      ${explanation}
      <div class="cx-layout-two">
        <article class="cx-user-card">
          <div class="cx-card-head">
            <div>
              <strong>${escapeHtml(owner.email)}</strong>
              <p>${escapeHtml(owner.full_name || "Encargado")} Ã‚Â· dueÃƒÂ±o / encargado</p>
            </div>
            ${ownerAccessBadge(users)}
          </div>
          <div class="cx-detail-grid">
            <div class="cx-kv"><span>Rol</span><strong>${escapeHtml(owner.role || "company_admin")}</strong></div>
            <div class="cx-kv"><span>Estado</span><strong>${escapeHtml(owner.status || "active")}</strong></div>
            <div class="cx-kv"><span>Cambio de clave requerido</span><strong>${owner.must_change_password ? "SÃƒÂ­" : "No"}</strong></div>
            <div class="cx-kv"><span>Intentos fallidos</span><strong>${escapeHtml(owner.failed_login_attempts || 0)}</strong></div>
            <div class="cx-kv"><span>Bloqueado hasta</span><strong>${escapeHtml(owner.locked_until || "Ã¢â‚¬â€")}</strong></div>
            <div class="cx-kv"><span>ÃƒÅ¡ltimo login</span><strong>${escapeHtml(owner.last_login_at || "Ã¢â‚¬â€")}</strong></div>
            <div class="cx-kv"><span>ÃƒÅ¡ltimo reset</span><strong>${escapeHtml(owner.last_password_reset_at || "Ã¢â‚¬â€")}</strong></div>
            <div class="cx-kv"><span>Empresa</span><strong>${escapeHtml(company.name)}</strong></div>
          </div>
          <div class="cx-actions" style="margin-top:12px">
            <button class="cx-btn cx-btn-small" data-copy="${escapeHtml(owner.email)}" type="button">Copiar email</button>
            <button class="cx-btn cx-btn-small" data-reset-password="${escapeHtml(owner.id)}" type="button">Regenerar clave</button>
            <button class="cx-btn cx-btn-small" data-unlock-user="${escapeHtml(owner.id)}" type="button">Desbloquear acceso</button>
            <button class="cx-btn cx-btn-small" data-toggle-user="${escapeHtml(owner.id)}" data-status="${escapeHtml(nextStatus)}" type="button">${nextStatusLabel}</button>
          </div>
        </article>
        <aside>
          <form class="cx-form" data-owner-reset-form="${escapeHtml(owner.id)}">
            <h3>Clave temporal</h3>
            <p>Entrega esta clave al dueÃƒÂ±o/encargado. Al ingresar podrÃƒÂ¡ cambiarla.</p>
            <label>Clave temporal
              <input data-owner-reset-input="${escapeHtml(owner.id)}" type="text" value="${escapeHtml(generateTempPassword(company.slug))}" />
            </label>
            <button class="cx-btn cx-btn-primary" data-reset-password="${escapeHtml(owner.id)}" type="button">Regenerar clave</button>
          </form>
        </aside>
      </div>
    `;
  }

  function renderUsersGlobalView() {
    const node = el("#usersGlobalView");
    if (!node) return;

    if (!state.selectedCompanyId) {
      node.innerHTML = `<div class="cx-empty-state">Selecciona una empresa en la secciÃƒÂ³n Empresas para gestionar el Acceso Maestro.</div>`;
      return;
    }

    const company = state.companies.find((c) => c.id === state.selectedCompanyId);
    const users = state.companyUsers.get(state.selectedCompanyId);
    const wrapper = document.createElement("div");
    renderCompanyUsersPanel(wrapper, company, users);
    node.innerHTML = wrapper.innerHTML;
  }


  function getCreatedCompanyId(payload) {
    if (!payload || typeof payload !== "object") return "";
    return payload.id
      || payload.company_id
      || payload.companyId
      || payload.data?.id
      || payload.data?.company_id
      || payload.company?.id
      || payload.company?.company_id
      || "";
  }

  function ensureCreateCompanyOwnerFields() {
    const form = el("#createCompanyForm");
    if (!form || form.querySelector("[data-owner-create-section]")) return;

    const submit = form.querySelector("button[type='submit']");
    if (submit) submit.textContent = "Crear empresa y acceso";

    const section = document.createElement("section");
    section.setAttribute("data-owner-create-section", "true");
    section.innerHTML = `
      <div class="cx-empty-state" style="text-align:left;margin:14px 0">
        <strong>Acceso Maestro</strong><br>
        Este serÃƒÂ¡ el usuario dueÃƒÂ±o o encargado que entrarÃƒÂ¡ al panel de la empresa.
        El personal operativo se gestiona desde el panel de la empresa.
      </div>
      <label>Nombre del encargado
        <input name="owner_full_name" type="text" placeholder="Empresa Admin" autocomplete="off" />
      </label>
      <label>Email del encargado
        <input name="owner_email" type="email" placeholder="admin@empresa.com" autocomplete="off" />
      </label>
      <label>ContraseÃƒÂ±a temporal
        <div style="display:flex;gap:8px;align-items:center">
          <input name="owner_password" type="text" placeholder="Clonexa-empresa-a7k2!" autocomplete="off" />
          <button class="cx-btn cx-btn-small" data-generate-create-owner-password type="button">Generar clave</button>
        </div>
      </label>
      <small>Cambio de clave requerido en el primer ingreso.</small>
      <div id="createCompanyResult" class="cx-empty-state" hidden style="text-align:left;margin-top:12px"></div>
    `;

    if (submit) {
      form.insertBefore(section, submit);
    } else {
      form.appendChild(section);
    }

    const slugInput = form.querySelector("input[name='slug']");
    const passwordInput = form.querySelector("input[name='owner_password']");
    if (passwordInput && !passwordInput.value) {
      passwordInput.value = generateTempPassword(slugInput?.value || "empresa");
    }
  }

  function renderCreateCompanyResult({ company, ownerEmail, temporaryPassword, packageWarning, ownerWarning }) {
    const box = el("#createCompanyResult");
    if (!box) return;

    const companyId = company?.id || "";
    box.hidden = false;
    box.innerHTML = `
      <strong>Empresa creada correctamente.</strong><br>
      <span>Empresa: ${escapeHtml(company?.name || "Ã¢â‚¬â€")}</span><br>
      <span>Slug: ${escapeHtml(company?.slug || "Ã¢â‚¬â€")}</span><br>
      <span>Email acceso maestro: ${escapeHtml(ownerEmail || "Ã¢â‚¬â€")}</span><br>
      <span>Clave temporal: <strong>${escapeHtml(temporaryPassword || "Ã¢â‚¬â€")}</strong></span>
      ${packageWarning ? `<br><span class="cx-badge cx-badge-danger">${escapeHtml(packageWarning)}</span>` : ""}
      ${ownerWarning ? `<br><span class="cx-badge cx-badge-danger">${escapeHtml(ownerWarning)}</span>` : ""}
      <div class="cx-actions" style="margin-top:10px">
        <button class="cx-btn cx-btn-small" data-copy="${escapeHtml(ownerEmail || "")}" type="button">Copiar email</button>
        <button class="cx-btn cx-btn-small" data-copy="${escapeHtml(temporaryPassword || "")}" type="button">Copiar clave</button>
        <a class="cx-btn cx-btn-small" href="/login" target="_blank" rel="noreferrer">Abrir /login</a>
        <a class="cx-btn cx-btn-small" href="/client?company_id=${escapeHtml(company.id)}" target="_blank" rel="noreferrer">Abrir /client</a>
        ${companyId ? `<button class="cx-btn cx-btn-small" data-select-company="${escapeHtml(companyId)}" data-detail-tab="usuarios" type="button">Ver Acceso Maestro</button>` : ""}
      </div>
    `;
  }

  function generateTempPassword(seed = "Tenant") {
    const part = Math.random().toString(36).replace(/[^a-z0-9]/g, "").slice(2, 6) || "a7k2";
    const clean = String(seed || "Tenant").toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "").slice(0, 18) || "tenant";
    return `Clonexa-${clean}-${part}!`;
  }

  async function createCompany(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const raw = Object.fromEntries(new FormData(form).entries());

    const packageCode = raw.package_code;
    const ownerFullName = String(raw.owner_full_name || "").trim();
    const ownerEmail = String(raw.owner_email || "").trim().toLowerCase();
    const ownerPassword = String(raw.owner_password || "").trim() || generateTempPassword(raw.slug || raw.name || "empresa");

    const companyBody = {
      name: raw.name,
      slug: raw.slug,
      timezone: raw.timezone || "America/Bogota",
      plan: raw.plan || "standard",
    };

    if (!companyBody.name || !companyBody.slug) {
      showToast("Nombre y slug son requeridos para crear empresa.", "error");
      return;
    }

    if (!ownerFullName || !ownerEmail) {
      showToast("Nombre y email del Acceso Maestro son requeridos.", "error");
      return;
    }

    try {
      const created = await apiPost(`${API}/companies`, companyBody);
      const company = normalizeCompany(created.company || created.data || created);
      const companyId = getCreatedCompanyId(created) || company.id;

      if (!companyId) {
        throw new Error("La empresa fue creada, pero no se pudo detectar company_id.");
      }

      let packageWarning = "";
      let ownerWarning = "";

      if (packageCode) {
        try {
          await activateCompanyPackage(companyId, packageCode, false);
        } catch (error) {
          packageWarning = "La empresa fue creada, pero no se pudo activar el paquete.";
          showToast(`${packageWarning} ${error.message}`, "error");
        }
      }

      try {
        await apiPost(`${API}/companies/${companyId}/users`, {
          email: ownerEmail,
          full_name: ownerFullName,
          role: "company_admin",
          password: ownerPassword,
          status: "active",
        });
      } catch (error) {
        ownerWarning = "La empresa fue creada, pero no se pudo crear el acceso maestro.";
        showToast(`${ownerWarning} ${error.message}`, "error");
      }

      renderCreateCompanyResult({
        company: { ...company, id: companyId },
        ownerEmail,
        temporaryPassword: ownerPassword,
        packageWarning,
        ownerWarning,
      });

      await loadAdminDashboard();
      await loadCompanyUsers(companyId).catch(() => null);
      await selectCompany(companyId);
      state.activeDetailTab = "usuarios";
      const selected = state.companies.find((c) => c.id === companyId) || { ...company, id: companyId };
      renderCompanyDetail(selected);
      renderCompanies();

      if (!ownerWarning) {
        showTemporaryPassword(ownerPassword);
        showToast(packageWarning ? "Empresa creada con advertencias." : "Empresa, paquete y acceso maestro creados correctamente.");
      }
    } catch (error) {
      showToast(`No se pudo crear la empresa: ${error.message}`, "error");
    }
  }

  async function activateCompanyPackage(companyId, packageCode, reload = true) {
    if (!companyId || !packageCode) return;
    await apiPost(`${API}/companies/${companyId}/activate-package`, { package_code: packageCode, settings: {} });
    if (reload) {
      await loadCompanyModules(companyId);
      renderCompanies();
      const company = state.companies.find((c) => c.id === companyId);
      if (company) renderCompanyDetail(company);
      renderModules();
      showToast("Paquete activado.");
    }
  }

  async function createCompanyUser(companyId, event) {
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }

    const form = event?.target?.matches?.("#createUserForm")
      ? event.target
      : document.getElementById("createUserForm");

    if (!form) {
      showToast("No se encontrÃ³ el formulario de acceso maestro.", "error");
      console.error("[CLONEXA Admin V2] createUserForm not found");
      return;
    }

    const effectiveCompanyId = companyId || state.selectedCompanyId;
    if (!effectiveCompanyId) {
      showToast("No se encontrÃ³ la empresa seleccionada.", "error");
      return;
    }

    const fullName = String(form.querySelector('[name="full_name"]')?.value || "").trim();
    const email = String(form.querySelector('[name="email"]')?.value || "").trim().toLowerCase();
    const passwordInput = form.querySelector('[name="password"]');
    const password = String(passwordInput?.value || "").trim() || generateTempPassword(email || "empresa");

    if (!fullName) {
      showToast("Nombre del encargado requerido.", "error");
      return;
    }

    if (!email) {
      showToast("Email del encargado requerido.", "error");
      return;
    }

    if (!password) {
      showToast("ContraseÃ±a temporal requerida.", "error");
      return;
    }

    const body = {
      name: fullName,
      full_name: fullName,
      email: email,
      password: password,
      temporary_password: password,
      role: "company_admin",
      status: "active",
      must_change_password: true
    };

    try {
      await apiPost(`${API}/companies/${effectiveCompanyId}/users`, body);
      await loadCompanyUsers(effectiveCompanyId);

      const company = state.companies.find((c) => {
        if (typeof getCompanyId === "function") return getCompanyId(c) === effectiveCompanyId;
        return c.id === effectiveCompanyId || c.company_id === effectiveCompanyId;
      }) || state.selectedCompany;

      state.selectedCompanyId = effectiveCompanyId;
      state.selectedCompany = company;

      renderCompanyDetail(company);
      renderUsersGlobalView();
      showTemporaryPassword(password);
      showToast("Acceso maestro creado correctamente.");
    } catch (error) {
      console.error("[CLONEXA Admin V2] owner access create failed", error);
      showToast(`No se pudo crear el acceso maestro: ${error.message}`, "error");
    }
  }
  async function resetCompanyUserPassword(companyId, userId) {
    try {
      const input = document.querySelector(`[data-owner-reset-input="${CSS.escape(userId)}"]`);
      const typedPassword = input && input.value ? input.value.trim() : "";
      const body = typedPassword ? { password: typedPassword } : {};
      const response = await apiPost(`${API}/companies/${companyId}/users/${userId}/reset-password`, body);
      const password = response.temporary_password || response.password || typedPassword || "No devuelta";
      showTemporaryPassword(password);
      await loadCompanyUsers(companyId);
      renderCompanyDetail(state.companies.find((c) => c.id === companyId));
      renderUsersGlobalView();
      renderCompanies();
      showToast("Clave regenerada correctamente.");
    } catch (error) {
      showToast(`No se pudo regenerar la clave: ${error.message}`, "error");
    }
  }

  async function unlockCompanyUser(companyId, userId) {
    try {
      await apiPost(`${API}/companies/${companyId}/users/${userId}/unlock`, {});
      await loadCompanyUsers(companyId);
      renderCompanyDetail(state.companies.find((c) => c.id === companyId));
      renderUsersGlobalView();
      showToast("Acceso desbloqueado.");
    } catch (error) {
      showToast(`No se pudo desbloquear el acceso: ${error.message}`, "error");
    }
  }

  async function toggleCompanyUser(companyId, userId, status) {
    try {
      await apiPut(`${API}/companies/${companyId}/users/${userId}`, { status });
      await loadCompanyUsers(companyId);
      renderCompanyDetail(state.companies.find((c) => c.id === companyId));
      renderUsersGlobalView();
      showToast("Estado de acceso actualizado.");
    } catch (error) {
      showToast(`Activar/desactivar acceso no estÃƒÂ¡ disponible todavÃƒÂ­a: ${error.message}`, "error");
    }
  }

  async function saveBranding(companyId, event) {
    event.preventDefault();

    const form = event?.target?.matches?.("#brandingForm")
      ? event.target
      : el("#brandingForm");

    if (!form) {
      showToast("No se encontró el formulario de branding.", "error");
      return;
    }

    const body = cxBrandingFromForm();

    try {
      await apiPut(`${API}/companies/${companyId}/experience/branding`, body);
      await loadCompanyExperience(companyId);

      const company = state.companies.find((c) => c.id === companyId);
      if (company) {
        renderCompanyDetail(company);
      }

      renderCrmView();
      showToast("Branding guardado.");
    } catch (error) {
      showToast(`No se pudo guardar branding: ${error.message}`, "error");
    }
  }
  async function ensureDefaults(companyId) {
    try {
      await apiPost(`${API}/companies/${companyId}/experience/ensure-defaults`, {});
      await loadCompanyExperience(companyId);
      renderCompanyDetail(state.companies.find((c) => c.id === companyId));
      renderCrmView();
      showToast("Defaults CRM regenerados.");
    } catch (error) {
      showToast(`No se pudieron regenerar defaults: ${error.message}`, "error");
    }
  }


  async function updateCompanyStatus(companyId, status) {
    if (!companyId || !status) return;
    const body = { status };

    const attempts = [
      () => apiPatch(`${API}/companies/${companyId}/status`, body),
      () => apiPatch(`${API}/companies/${companyId}`, body),
      () => apiPut(`${API}/companies/${companyId}`, body),
    ];

    let lastError = null;
    for (const attempt of attempts) {
      try {
        return await attempt();
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error("No existe endpoint seguro para actualizar status de empresa.");
  }

  async function setCompanyStatus(companyId, status) {
    const company = state.companies.find((c) => c.id === companyId);
    if (!company) return;

    try {
      await updateCompanyStatus(companyId, status);
      const message = status === "active"
        ? "Empresa reactivada correctamente."
        : status === "inactive"
          ? "Empresa desactivada correctamente."
          : "Empresa archivada correctamente.";
      showToast(message);
      await loadAdminDashboard();

      if (status === "deleted" || status === "archived") {
        if (state.selectedCompanyId === companyId) {
          state.selectedCompanyId = null;
          const card = el("#companyDetailCard");
          if (card) card.innerHTML = `<div class="cx-empty-state">Empresa archivada correctamente. Activa el filtro Archivadas para verla.</div>`;
        }
      } else {
        await selectCompany(companyId);
      }
    } catch (error) {
      showToast(`No se pudo actualizar el estado de la empresa: ${error.message}`, "error");
    }
  }

  function showArchiveCompanyDialog(company) {
    if (!company) return;

    let dialog = el("#archiveCompanyDialog");
    if (!dialog) {
      dialog = document.createElement("dialog");
      dialog.id = "archiveCompanyDialog";
      dialog.className = "cx-modal";
      document.body.appendChild(dialog);
    }

    dialog.innerHTML = `
      <form method="dialog" class="cx-form" style="min-width:min(560px,92vw)">
        <h2>Eliminar / archivar empresa</h2>
        <div class="cx-empty-state" style="text-align:left">
          Esta acciÃƒÂ³n archivarÃƒÂ¡ la empresa y bloquearÃƒÂ¡ su acceso. No se eliminarÃƒÂ¡n datos fÃƒÂ­sicos.
        </div>
        <div class="cx-detail-grid">
          <div class="cx-kv"><span>Empresa</span><strong>${escapeHtml(company.name)}</strong></div>
          <div class="cx-kv"><span>Slug</span><strong>${escapeHtml(company.slug)}</strong></div>
          <div class="cx-kv"><span>Company ID</span><strong>${escapeHtml(company.id)}</strong></div>
        </div>
        <label>Escribe el slug para confirmar
          <input id="archiveCompanySlugInput" type="text" autocomplete="off" placeholder="${escapeHtml(company.slug)}" />
        </label>
        <div class="cx-actions">
          <button class="cx-btn" value="cancel" type="submit">Cancelar</button>
          <button class="cx-btn cx-btn-primary" id="archiveCompanyConfirmBtn" type="button" disabled>Archivar empresa</button>
        </div>
      </form>
    `;

    const input = dialog.querySelector("#archiveCompanySlugInput");
    const confirm = dialog.querySelector("#archiveCompanyConfirmBtn");
    input?.addEventListener("input", () => {
      confirm.disabled = input.value !== company.slug;
    });
    confirm?.addEventListener("click", async () => {
      dialog.close();
      await setCompanyStatus(company.id, "deleted");
    });

    if (typeof dialog.showModal === "function") {
      dialog.showModal();
      input?.focus();
    } else {
      const typed = window.prompt(`Escribe el slug exacto para archivar ${company.name}:`);
      if (typed === company.slug) setCompanyStatus(company.id, "deleted");
    }
  }

  function showTemporaryPassword(password) {
    setText("temporaryPasswordValue", password);
    const modal = el("#temporaryPasswordModal");
    if (modal && typeof modal.showModal === "function") {
      modal.showModal();
    } else {
      alert(`Clave temporal: ${password}`);
    }
  }

  function applyOwnerAccessLabels() {
    const navUsers = document.querySelector('[data-view="users"]');
    if (navUsers) navUsers.textContent = "Acceso Maestro";

    const usersPanelTitle = document.querySelector('[data-view-panel="users"] h2');
    if (usersPanelTitle) usersPanelTitle.textContent = "Acceso Maestro";

    const usersPanelText = document.querySelector('[data-view-panel="users"] p');
    if (usersPanelText) {
      usersPanelText.textContent = "Usuario dueÃƒÂ±o/encargado de cada empresa. El personal operativo se gestiona desde el panel de la empresa.";
    }

    document.querySelectorAll("th, h2, h3, p, button, span, small, label").forEach((node) => {
      const text = node.textContent ? node.textContent.trim() : "";
      if (text === "Usuarios") node.textContent = "Acceso Maestro";
      if (text === "Usuarios de acceso") node.textContent = "Usuario dueÃƒÂ±o / encargado";
      if (text === "Crear usuario") node.textContent = "Crear acceso maestro";
      if (text === "Reset password") node.textContent = "Regenerar clave";
      if (text === "ContraseÃƒÂ±a temporal generada") node.textContent = "Clave temporal generada";
      if (text === "Desbloquear usuario") node.textContent = "Desbloquear acceso";
      if (text === "Desactivar usuario") node.textContent = "Desactivar acceso";
      if (text === "Activar usuario") node.textContent = "Activar acceso";
    });
  }

  function setView(view) {
    state.activeView = view;

    els("[data-view-panel]").forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.viewPanel === view);
    });

    els(".cx-nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === view);
    });

    const titles = {
      dashboard: ["Dashboard", "Control central de empresas, módulos, paquetes, accesos y paneles cliente."],
      companies: ["Empresas", "GestiÃƒÂ³n de tenants, paquetes, módulos, Acceso Maestro y CRM."],
      users: ["Acceso Maestro", "Usuario dueÃƒÂ±o/encargado, regeneraciÃƒÂ³n de clave y desbloqueo."],
      packages: ["Paquetes", "CatÃƒÂ¡logo de paquetes SaaS listos para activar."],
      modules: ["Módulos", "CatÃƒÂ¡logo global y módulos activos por tenant."],
      access: ["Accesos", "Rutas operativas rápidas del ecosistema."],
      crm: ["CRM / Panel Empresa", "Estado resumido de branding, experiencia y panel cliente."],
      health: ["Health / Estado del sistema", "Estado de API y conteos principales."]
    };

    const [title, subtitle] = titles[view] || titles.dashboard;
    setText("viewTitle", title);
    setText("viewSubtitle", subtitle);
  }

  function renderAll() {
    updateMetrics();
    renderDashboard();
    renderCompanies();
    renderPackages();
    renderModules();
    renderAccess();
    renderHealth();
    renderCrmView();
    renderUsersGlobalView();

    if (state.selectedCompanyId) {
      const company = state.companies.find((c) => c.id === state.selectedCompanyId);
      if (company) renderCompanyDetail(company);
    }
  }

  function bindEvents() {
    document.addEventListener("click", async (event) => {
      const nav = event.target.closest("[data-view]");
      if (nav) {
        setView(nav.dataset.view);
        return;
      }

      const navView = event.target.closest("[data-nav-view]");
      if (navView) {
        setView(navView.dataset.navView);
        return;
      }

      const select = event.target.closest("[data-select-company]");
      if (select) {
        const tab = select.dataset.detailTab || "resumen";
        await selectCompany(select.dataset.selectCompany, tab);
        return;
      }

      const tab = event.target.closest("[data-detail-tab]");
      if (tab && state.selectedCompanyId) {
        state.activeDetailTab = tab.dataset.detailTab;
        const company = state.companies.find((c) => c.id === state.selectedCompanyId);
        if (company) renderCompanyDetail(company);
        return;
      }

      const copy = event.target.closest("[data-copy]");
      if (copy) {
        await navigator.clipboard.writeText(copy.dataset.copy);
        showToast("Copiado al portapapeles.");
        return;
      }

      const filter = event.target.closest("[data-company-filter]");
      if (filter) {
        state.companyFilter = filter.dataset.companyFilter || "visible";
        renderCompanies();
        renderDashboard();
        return;
      }

      const statusButton = event.target.closest("[data-company-status]");
      if (statusButton) {
        await setCompanyStatus(statusButton.dataset.companyStatus, statusButton.dataset.status);
        return;
      }

      const archiveButton = event.target.closest("[data-archive-company]");
      if (archiveButton) {
        const company = state.companies.find((c) => c.id === archiveButton.dataset.archiveCompany);
        showArchiveCompanyDialog(company);
        return;
      }

      const generateCreateOwnerPassword = event.target.closest("[data-generate-create-owner-password]");
      if (generateCreateOwnerPassword) {
        const form = el("#createCompanyForm");
        const slug = form?.querySelector("input[name='slug']")?.value || form?.querySelector("input[name='name']")?.value || "empresa";
        const input = form?.querySelector("input[name='owner_password']");
        if (input) input.value = generateTempPassword(slug);
        return;
      }

      const generatePasswordForForm = event.target.closest("[data-generate-password-for-form]");
      if (generatePasswordForForm) {
        const targetForm = document.querySelector(generatePasswordForForm.dataset.generatePasswordForForm);
        const company = state.companies.find((c) => c.id === state.selectedCompanyId);
        const input = targetForm?.querySelector("input[name='password']");
        if (input) input.value = generateTempPassword(company?.slug || "empresa");
        return;
      }

      if (event.target.closest("[data-open-client]")) {
        window.open("/client", "_blank");
        return;
      }

      const reset = event.target.closest("[data-reset-password]");
      if (reset && state.selectedCompanyId) {
        await resetCompanyUserPassword(state.selectedCompanyId, reset.dataset.resetPassword);
        return;
      }

      const unlock = event.target.closest("[data-unlock-user]");
      if (unlock && state.selectedCompanyId) {
        await unlockCompanyUser(state.selectedCompanyId, unlock.dataset.unlockUser);
        return;
      }

      const toggle = event.target.closest("[data-toggle-user]");
      if (toggle && state.selectedCompanyId) {
        await toggleCompanyUser(state.selectedCompanyId, toggle.dataset.toggleUser, toggle.dataset.status);
        return;
      }

      const telegramTest = event.target.closest("[data-test-telegram-bot]");
      if (telegramTest) {
        await testTelegramBotConfig(telegramTest.dataset.testTelegramBot);
        return;
      }

      const telegramStartListener = event.target.closest("[data-start-telegram-listener]");
      if (telegramStartListener) {
        await startTelegramBotListener(telegramStartListener.dataset.startTelegramListener);
        return;
      }

      const telegramDeactivate = event.target.closest("[data-deactivate-telegram-bot]");
      if (telegramDeactivate) {
        await deactivateTelegramBotConfig(telegramDeactivate.dataset.deactivateTelegramBot);
        return;
      }

      const ensure = event.target.closest("[data-ensure-defaults]");
      if (ensure) {
        await ensureDefaults(ensure.dataset.ensureDefaults);
        return;
      }
    });

    el("#refreshBtn")?.addEventListener("click", async () => {
      state.errors = [];
      await loadAdminDashboard();
      showToast("Datos actualizados.");
    });

    el("#healthRefreshBtn")?.addEventListener("click", async () => {
      await loadHealth().catch(() => null);
      state.lastRefresh = localTime();
      updateMetrics();
      renderHealth();
    });

    el("#openAdminLegacyBtn")?.addEventListener("click", () => window.open("/admin", "_blank"));
    el("#openClientBtn")?.addEventListener("click", () => window.open("/client", "_blank"));
    el("#newCompanyFocusBtn")?.addEventListener("click", () => el("#createCompanyForm input[name='name']")?.focus());

    el("#createCompanyForm")?.addEventListener("submit", createCompany);
    el("#createCompanyForm input[name='slug']")?.addEventListener("input", (event) => {
      const form = el("#createCompanyForm");
      const input = form?.querySelector("input[name='owner_password']");
      if (input && (!input.dataset.touched || input.value.startsWith("Clonexa-"))) {
        input.value = generateTempPassword(event.target.value || "empresa");
      }
    });
    el("#createCompanyForm input[name='owner_password']")?.addEventListener("input", (event) => {
      event.target.dataset.touched = "true";
    });

    document.addEventListener("submit", async (event) => {
      if (event.target.matches("#activatePackageForm") && state.selectedCompanyId) {
        event.preventDefault();
        const body = Object.fromEntries(new FormData(event.target).entries());
        await activateCompanyPackage(state.selectedCompanyId, body.package_code);
      }

      if (event.target.matches("#createUserForm") && state.selectedCompanyId) {
        await createCompanyUser(state.selectedCompanyId, event);
      }

      if (event.target.matches("#brandingForm") && state.selectedCompanyId) {
        await saveBranding(state.selectedCompanyId, event);
      }

      if (event.target.matches("#telegramBotConfigForm")) {
        const companyId = event.target.dataset.companyId || state.selectedCompanyId;
        await saveTelegramBotConfig(companyId, event);
      }
    });

    el("#closeTempPasswordModal")?.addEventListener("click", () => el("#temporaryPasswordModal")?.close());
    el("#copyTempPasswordBtn")?.addEventListener("click", async () => {
      await navigator.clipboard.writeText(el("#temporaryPasswordValue")?.textContent || "");
      showToast("Clave temporal copiada.");
    });
  }

  async function bootstrap() {
    ensureCreateCompanyOwnerFields();
    bindEvents();
    applyOwnerAccessLabels();
    setView("dashboard");

    try {
      await loadAdminDashboard();
    } catch (error) {
      showAdminError(`Admin V2 cargÃƒÂ³ con errores parciales: ${error.message}`);
    }
  }

  document.addEventListener("DOMContentLoaded", bootstrap);
})();


  /* CLONEXA_CLIENT_COMPANY_ID_ROUTING_R2 */
  document.addEventListener("click", (event) => {
    const openClient = event.target.closest("[data-open-client]");
    if (!openClient) return;

    const companyId = openClient.dataset.openClient;
    if (!companyId) return;

    event.preventDefault();
    event.stopPropagation();

    window.open(`/client?company_id=${encodeURIComponent(companyId)}`, "_blank", "noopener,noreferrer");
  }, true);



/* CLONEXA 010B-R4 ? Company Modules Smart Search Sort
   Objetivo:
   - No rompe render.
   - No toca backend.
   - No oculta por busqueda.
   - Ordena los módulos por relevancia y pone primero el mas parecido.
*/
;(() => {
  if (window.__cxCompanyModuleSmartSearchR4) return;
  window.__cxCompanyModuleSmartSearchR4 = true;

  const keywordMap = {
    core: "nucleo base estructura empresa tenant sistema principal",
    personal: "personal empleado empleados operario operarios trabajador trabajadores equipo humano agregar personal crear personal workforce usuarios",
    workforce: "personal empleado empleados operario operarios trabajador trabajadores equipo humano agregar personal crear personal workforce usuarios",
    field: "campo operacion tecnico tecnicos ruta evidencia actividad cuadrilla externo",
    gps: "gps ubicacion ubicaciones geolocalizacion localizacion mapa ruta seguimiento tecnico campo",
    payroll: "nomina pago pagos quincena quincenal salario horas extras corte liquidacion payroll",
    nomina: "nomina pago pagos quincena quincenal salario horas extras corte liquidacion payroll",
    day_closing: "cierre dia cierre diario ventas resumen caja turno",
    hospitality: "bar restaurante hospitality mesas pedidos mesero cuenta",
    loyalty: "fidelizacion clientes puntos beneficios lealtad recurrentes",
    orders: "pedidos pedido orden ordenes comandas compra solicitud cliente mesa",
    pedidos: "pedidos pedido orden ordenes comandas compra solicitud cliente mesa",
    tables: "mesas mesa cuenta qr restaurante bar",
    bots: "bot bots telegram whatsapp automatizacion mensajes entrada",
    qr: "qr código mesa escanear acceso link",
    inventory: "inventario stock existencias productos materiales almacen",
    inventario: "inventario stock existencias productos materiales almacen",
    materials: "materiales material solicitud entregar devolver herramientas stock tecnico pedir material",
    materiales: "materiales material solicitud entregar devolver herramientas stock tecnico pedir material",
    stock: "stock inventario minimo existencias alerta",
    costs: "costos costo produccion gasto margen referencia",
    production: "produccion fabricar referencias tiempos productividad costos",
    references: "referencias productos servicios catálogo sku",
    crm: "crm panel cliente seguimiento gestion comercial campo",
    kpis: "kpi kpis indicadores metricas rendimiento tablero",
    reports: "reportes informes historicos auditoria exportar",
    requests: "solicitudes solicitud requerimientos aprobaciones pedir material",
    retail: "retail tiendas ventas mostrador solicitudes inventario",
    sales: "ventas venta comercial ingresos pedidos",
    stores: "tiendas sucursales puntos venta locales",
  };

  function normalizeText(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9_ ]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function tokens(value) {
    return normalizeText(value)
      .split(" ")
      .map((x) => x.trim())
      .filter(Boolean);
  }

  function cardEnabled(card) {
    const text = normalizeText(card.textContent || "");
    if (text.includes("inactivo")) return false;
    if (text.includes("activo")) return true;
    return false;
  }

  function cardSearchText(card) {
    const raw = normalizeText(card.textContent || "");
    let extra = "";

    Object.entries(keywordMap).forEach(([key, words]) => {
      if (raw.includes(key) || raw.includes(normalizeText(key))) {
        extra += " " + words;
      }
    });

    if (raw.includes("personal") || raw.includes("workforce")) extra += " " + keywordMap.personal;
    if (raw.includes("nomina") || raw.includes("payroll")) extra += " " + keywordMap.payroll;
    if (raw.includes("gps") || raw.includes("ubicacion")) extra += " " + keywordMap.gps;
    if (raw.includes("material") || raw.includes("inventario")) extra += " " + keywordMap.materials + " " + keywordMap.inventory;
    if (raw.includes("pedido") || raw.includes("orders")) extra += " " + keywordMap.orders;
    if (raw.includes("qr")) extra += " " + keywordMap.qr;

    return `${raw} ${normalizeText(extra)}`;
  }

  function scoreCard(card, query) {
    const q = normalizeText(query);
    if (!q) return 0;

    const text = cardSearchText(card);
    const qTokens = tokens(q);
    let score = 0;

    if (text.includes(q)) score += 200;

    qTokens.forEach((token) => {
      if (!token) return;

      const strong = normalizeText(card.querySelector("strong")?.textContent || "");
      const code = normalizeText(card.querySelector("p")?.textContent || "");

      if (strong === token || code === token) score += 120;
      if (strong.startsWith(token) || code.startsWith(token)) score += 80;
      if (strong.includes(token) || code.includes(token)) score += 60;
      if (text.includes(token)) score += 25;
    });

    return score;
  }

  function currentCompanyIdFromInput(input) {
    return input?.dataset?.companyId || "";
  }

  function getFilter(companyId) {
    const ux = window.__cxCompanyModuleUx;
    if (ux?.filter?.get) return ux.filter.get(companyId) || "all";

    const activeButton = document.querySelector(`[data-cx-company-module-filter][data-company-id="${companyId}"].cx-btn-primary`);
    return activeButton?.dataset?.filter || "all";
  }

  function setFilter(companyId, filter) {
    const ux = window.__cxCompanyModuleUx;
    if (ux?.filter?.set) ux.filter.set(companyId, filter || "all");
  }

  function setSearch(companyId, value) {
    const ux = window.__cxCompanyModuleUx;
    if (ux?.search?.set) ux.search.set(companyId, value || "");
  }

  function applySmartSearch(companyId) {
    const input = document.querySelector(`[data-cx-company-module-search][data-company-id="${companyId}"]`);
    if (!input) return;

    const query = input.value || "";
    const filter = getFilter(companyId);

    const searchPanel = input.closest(".cx-panel");
    const grid = searchPanel?.nextElementSibling;
    if (!grid || !grid.classList.contains("cx-module-grid")) return;

    const cards = Array.from(grid.querySelectorAll(".cx-module-chip"));
    if (!cards.length) return;

    cards.forEach((card, index) => {
      if (!card.dataset.originalIndex) card.dataset.originalIndex = String(index);
    });

    const ranked = cards.map((card) => {
      const enabled = cardEnabled(card);
      const score = scoreCard(card, query);

      let hidden = false;
      if (filter === "active" && !enabled) hidden = true;
      if (filter === "inactive" && enabled) hidden = true;

      return {
        card,
        enabled,
        score,
        originalIndex: Number(card.dataset.originalIndex || 0),
        hidden,
      };
    });

    ranked.sort((a, b) => {
      if (a.hidden !== b.hidden) return a.hidden ? 1 : -1;

      if (query) {
        if (b.score !== a.score) return b.score - a.score;
        if ((b.score > 0) !== (a.score > 0)) return b.score > 0 ? 1 : -1;
      }

      if (filter === "all") {
        if (a.enabled !== b.enabled) return a.enabled ? -1 : 1;
      }

      return a.originalIndex - b.originalIndex;
    });

    ranked.forEach((item) => {
      item.card.style.display = item.hidden ? "none" : "";
      item.card.style.opacity = query && item.score === 0 ? ".45" : "";
      item.card.style.transform = query && item.score > 0 ? "translateY(-2px)" : "";
      item.card.style.outline = query && item.score > 0 ? "1px solid rgba(255,43,214,.55)" : "";
      item.card.style.boxShadow = query && item.score > 0 ? "0 0 28px rgba(255,43,214,.20)" : "";
      grid.appendChild(item.card);
    });

    const visibleCount = ranked.filter((item) => !item.hidden).length;
    const info = searchPanel.querySelector("p[style*='margin-top']");
    if (info) {
      info.textContent = `Mostrando ${visibleCount} de ${cards.length} módulos. ${query ? "Resultados ordenados por relevancia." : ""}`;
    }
  }

  document.addEventListener("input", (event) => {
    const input = event.target.closest("[data-cx-company-module-search]");
    if (!input) return;

    const companyId = currentCompanyIdFromInput(input);
    setSearch(companyId, input.value || "");

    setTimeout(() => applySmartSearch(companyId), 0);
    setTimeout(() => applySmartSearch(companyId), 80);
  });

  document.addEventListener("click", (event) => {
    const filterButton = event.target.closest("[data-cx-company-module-filter]");
    if (!filterButton) return;

    const companyId = filterButton.dataset.companyId || "";
    const filter = filterButton.dataset.filter || "all";
    setFilter(companyId, filter);

    setTimeout(() => applySmartSearch(companyId), 0);
    setTimeout(() => applySmartSearch(companyId), 80);
  });

  window.cxApplyCompanyModuleSmartSearch = applySmartSearch;
})();


// CLONEXA_FORCE_BUILD_20260513_161603


// CLONEXA_FORCE_BUILD_019G_R6_20260513_163613


// CLONEXA_FORCE_BUILD_019G_R6_20260513_163650

/* CLONEXA_019G_R6B_RESTORE_FINAL_START */
(function () {
  const SECTION_ID = "cx-mp-r6b-section";
  const STORAGE_PREFIX = "clonexa.miniPanelAssignments.r6b.";
  const API = "/api/v1";

  const PANEL_DEFS = [
    { type: "sales", label: "Ventas", keys: ["ventas", "sales", "sal"] },
    { type: "store", label: "Tiendas", keys: ["tiendas", "stores", "store", "str"] },
    { type: "inventory", label: "Inventario", keys: ["inventario", "inventory", "inv"] },
    { type: "logistics", label: "Logística", keys: ["logistica", "logística", "field", "gps", "fld"] },
    { type: "other", label: "Otro", keys: ["otro", "other"] }
  ];

  const KNOWN = {
    "nucleo": "core",
    "core": "core",
    "ajustes": "core_settings",
    "core_settings": "core_settings",
    "creacion mini_panel": "mini_panel",
    "creacion mini _panel": "mini_panel",
    "mini_panel": "mini_panel",
    "personal": "workforce",
    "workforce": "workforce",
    "gps": "gps",
    "nomina": "payroll",
    "nómina": "payroll",
    "payroll": "payroll",
    "crm campo": "crm",
    "crm": "crm",
    "kpis": "kpis",
    "bots": "bots",
    "cierre comercial": "commercial_closing",
    "commercial_closing": "commercial_closing",
    "ventas": "sales",
    "sales": "sales",
    "tiendas": "stores",
    "stores": "stores",
    "solicitudes": "requests",
    "requests": "requests",
    "inventario": "inventory",
    "inventory": "inventory",
    "materiales": "materials",
    "materials": "materials",
    "reportes": "reports",
    "reports": "reports",
    "cotizaciones": "cotizacion",
    "cotizacion": "cotizacion",
    "cotización": "cotizacion",
    "registro venta": "registro_venta",
    "registro de venta": "registro_venta",
    "cierre de dia": "day_closing",
    "cierre día": "day_closing",
    "day_closing": "day_closing",
    "operacion en campo": "field",
    "operación en campo": "field",
    "field": "field"
  };

  const SKIP_CODES = new Set(["core", "core_settings", "mini_panel"]);

  function norm(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function slug(value) {
    return norm(value).replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  }

  // CLONEXA_022A_HIERARCHY_SOURCE_OF_TRUTH_START
  const MODULE_ALIAS_CANONICAL_022A = {
    "cotizacion": "cotizacion",
    "cotizaciones": "cotizacion",
    "cotización": "cotizacion",
    "quote": "cotizacion",
    "quotes": "cotizacion",
    "quotation": "cotizacion",
    "presupuesto": "cotizacion",
    "presupuestos": "cotizacion",

    "nota": "notas",
    "notas": "notas",
    "notes": "notas",
    "agenda": "notas",
    "recordatorio": "notas",
    "recordatorios": "notas",
    "notas_o_agenda": "notas",

    "registro_venta": "registro_venta",
    "registro_ventas": "registro_venta",
    "registro de venta": "registro_venta",
    "sales_register": "registro_venta",

    "cierre_dia": "day_closing",
    "cierre_de_dia": "day_closing",
    "cierre de dia": "day_closing",
    "cierre dia": "day_closing",
    "day_closing": "day_closing",
    "commercial_closing": "day_closing"
  };

  function canonicalModuleCode022A(value) {
    const code = slug(value);
    return MODULE_ALIAS_CANONICAL_022A[code] || MODULE_ALIAS_CANONICAL_022A[norm(value)] || code;
  }

  function uniqueCodes022A(values) {
    const seen = new Set();
    return (Array.isArray(values) ? values : [])
      .map((code) => canonicalModuleCode022A(code))
      .filter((code) => {
        if (!code || seen.has(code)) return false;
        seen.add(code);
        return true;
      });
  }
  // CLONEXA_022A_HIERARCHY_SOURCE_OF_TRUTH_END

  function getCompanyId() {
    const text = document.body.innerText || "";
    const match = text.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
    return match ? match[0] : "unknown-company";
  }

  function pageText() {
    return norm(document.body.innerText || "");
  }

  function isCompanyModulesTab() {
    const text = pageText();
    return text.includes("modulos activos") && text.includes("buscar modulo");
  }

  function hasMiniPanelActive() {
    const text = pageText();
    return (
      text.includes("mini_panel") ||
      text.includes("mini panel") ||
      text.includes("minipanel") ||
      text.includes("creacion mini")
    );
  }

  function findHeading(label) {
    const target = norm(label);
    return Array.from(document.querySelectorAll("h1,h2,h3,h4,strong,p,span,div"))
      .find((node) => norm(node.textContent) === target) || null;
  }

  function panelLink(companyId, type) {
    return `${window.location.origin}/mini-panel/login?company_id=${encodeURIComponent(companyId)}&type=${encodeURIComponent(type)}`;
  }

  function detectPanels(companyId, config) {
    const text = pageText();
    const panels = [];

    PANEL_DEFS.forEach((panel) => {
      const detected = panel.keys.some((key) => text.includes(norm(key)));
      const already = config?.panels?.[panel.type]?.enabled === true;

      if (detected || already || panel.type === "other") {
        panels.push(panel.type);
      }
    });

    if (!panels.includes("sales") && text.includes("ventas")) panels.push("sales");
    if (!panels.includes("store") && text.includes("tiendas")) panels.push("store");

    return Array.from(new Set(panels));
  }

  function loadConfig(companyId) {
    try {
      const raw = localStorage.getItem(STORAGE_PREFIX + companyId);
      if (raw) return JSON.parse(raw);
    } catch (_) {}

    return {
      enabled: false,
      selected_panel: "",
      panels: {},
      module_names: {}
    };
  }

  function extractRemoteMiniPanelConfig022A(rows) {
    const list = Array.isArray(rows) ? rows : [];
    const miniRow = list.find((row) => {
      const code = canonicalModuleCode022A(row?.module?.code || row?.module_code || row?.code || "");
      const name = slug(row?.module?.name || row?.name || "");
      return code === "mini_panel" || name.includes("mini_panel") || name.includes("creacion_mini");
    });

    const settings = miniRow && typeof miniRow.settings === "object" && miniRow.settings ? miniRow.settings : {};
    const config = settings.mini_panel_modules && typeof settings.mini_panel_modules === "object"
      ? settings.mini_panel_modules
      : (settings.panels && typeof settings.panels === "object" ? settings : null);

    if (!config) return null;

    return {
      enabled: config.enabled === true,
      selected_panel: config.selected_panel || "",
      panels: config.panels || {},
      module_names: config.module_names || {},
      company_id: config.company_id || "",
      updated_at: config.updated_at || ""
    };
  }

  async function loadRemoteConfig022A(companyId) {
    try {
      const response = await fetch(`${API}/companies/${encodeURIComponent(companyId)}/modules?enabled_only=true`, {
        headers: { "Content-Type": "application/json" }
      });

      if (!response.ok) return null;

      const data = await response.json().catch(() => []);
      return extractRemoteMiniPanelConfig022A(data);
    } catch (error) {
      console.warn("CLONEXA 022A remote mini panel load fallback:", error);
      return null;
    }
  }

  function normalizeConfig(companyId, config) {
    const next = config && typeof config === "object" ? { ...config } : {};
    next.enabled = next.enabled === true;
    next.panels = next.panels && typeof next.panels === "object" ? next.panels : {};
    next.module_names = next.module_names && typeof next.module_names === "object" ? next.module_names : {};

    const normalizedNames = {};
    Object.entries(next.module_names || {}).forEach(([code, name]) => {
      const canonical = canonicalModuleCode022A(code);
      if (canonical) normalizedNames[canonical] = name;
    });
    next.module_names = normalizedNames;

    const detected = detectPanels(companyId, next);

    detected.forEach((type) => {
      const current = next.panels[type] && typeof next.panels[type] === "object" ? next.panels[type] : {};
      next.panels[type] = {
        enabled: current.enabled === false ? false : true,
        link: current.link || panelLink(companyId, type),
        modules: uniqueCodes022A(current.modules)
      };
    });

    Object.keys(next.panels).forEach((type) => {
      if (!detected.includes(type)) {
        next.panels[type].enabled = next.panels[type].enabled === true;
        next.panels[type].link = next.panels[type].link || panelLink(companyId, type);
        next.panels[type].modules = uniqueCodes022A(next.panels[type].modules);
      }
    });

    const activePanels = PANEL_DEFS.filter((p) => next.panels[p.type]?.enabled);
    if (!next.selected_panel || !next.panels[next.selected_panel]?.enabled) {
      next.selected_panel = activePanels[0]?.type || "";
    }

    return next;
  }

  function saveLocal(companyId, config) {
    const payload = normalizeConfig(companyId, {
      ...config,
      company_id: companyId,
      updated_at: new Date().toISOString()
    });

    localStorage.setItem(STORAGE_PREFIX + companyId, JSON.stringify(payload));
    return payload;
  }

  async function saveRemote(companyId, config) {
    try {
      await fetch(`${API}/companies/${encodeURIComponent(companyId)}/modules/mini_panel/activate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          settings: {
            mini_panel_modules: {
              enabled: config.enabled === true,
              selected_panel: config.selected_panel || "",
              panels: config.panels || {},
              module_names: config.module_names || {},
              updated_at: new Date().toISOString()
            }
          }
        })
      });
    } catch (error) {
      console.warn("CLONEXA mini panel save fallback:", error);
    }
  }

  function panelLabel(type) {
    return PANEL_DEFS.find((p) => p.type === type)?.label || type;
  }

  function getModuleCards() {
    return Array.from(document.querySelectorAll("article, .cx-card, .cx-module-card, .module-card"))
      .filter((card) => {
        if (card.closest(`#${SECTION_ID}`)) return false;

        const text = norm(card.innerText);
        if (!text) return false;
        if (text.includes("modulos para mini panel")) return false;
        if (text.includes("configuracion por empresa")) return false;
        if (text.includes("buscar modulo")) return false;

        return (
          text.includes("info") &&
          (
            text.includes("activar") ||
            text.includes("desactivar") ||
            text.includes("activo") ||
            text.includes("inactivo")
          )
        );
      });
  }

  function extractModuleName(card) {
    const title = Array.from(card.querySelectorAll("h3,h4,strong,b"))
      .map((node) => String(node.textContent || "").trim())
      .filter(Boolean)[0];

    if (title) return title;

    return String(card.innerText || "")
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean)[0] || "Módulo";
  }

  function extractModuleCode(card) {
    const text = norm(card.innerText);
    const knownCodes = [
      "core_settings", "mini_panel", "commercial_closing",
      "registro_venta", "day_closing", "cotizacion",
      "workforce", "payroll", "requests", "stores", "sales",
      "inventory", "materials", "reports", "field", "gps",
      "crm", "kpis", "bots", "core"
    ];

    for (const code of knownCodes) {
      if (text.includes(code)) return canonicalModuleCode022A(code);
    }

    const name = norm(extractModuleName(card));
    if (KNOWN[name]) return canonicalModuleCode022A(KNOWN[name]);

    for (const [key, code] of Object.entries(KNOWN)) {
      if (name.includes(norm(key))) return canonicalModuleCode022A(code);
    }

    return canonicalModuleCode022A(name);
  }

  function shouldSkip(code, name) {
    const text = norm(`${code} ${name}`);
    return SKIP_CODES.has(code) || text.includes("creacion mini") || text.includes("nucleo") || text.includes("ajustes");
  }

  function activePanels(config) {
    return PANEL_DEFS.filter((panel) => config.panels?.[panel.type]?.enabled);
  }

  function selectedModules(config) {
    const panel = config.panels?.[config.selected_panel];
    return uniqueCodes022A(Array.isArray(panel?.modules) ? panel.modules : []);
  }

  function assignedListHtml(config) {
    const modules = selectedModules(config);
    const label = panelLabel(config.selected_panel);

    if (!config.enabled) {
      return `<div class="cx-mp-r6b-empty">Activa módulos para minipanel para comenzar.</div>`;
    }

    if (!config.selected_panel) {
      return `<div class="cx-mp-r6b-empty">Selecciona un panel destino.</div>`;
    }

    if (!modules.length) {
      return `<div class="cx-mp-r6b-empty">Sin módulos asignados a ${label}.</div>`;
    }

    return `
      <div class="cx-mp-r6b-assigned-list">
        ${modules.map((code) => `
          <div class="cx-mp-r6b-assigned-item">
            <div>
              <strong>${config.module_names?.[code] || code}</strong>
              <small>${code}</small>
            </div>
            <button type="button" data-cx-mp-r6b-remove="${code}">Quitar</button>
          </div>
        `).join("")}
      </div>
    `;
  }

  function buildSection(companyId, config) {
    const panels = activePanels(config);

    return `
      <section id="${SECTION_ID}" class="cx-mp-r6b-section">
        <div class="cx-mp-r6b-head">
          <div>
            <div class="cx-mp-r6b-kicker">CONFIGURACIÓN POR EMPRESA</div>
            <h3>Módulos para Mini Panel</h3>
            <p>Activa esta opción, selecciona el panel destino y agrega módulos existentes de esta empresa.</p>
          </div>

          <button class="cx-mp-r6b-toggle ${config.enabled ? "is-on" : ""}" type="button" data-cx-mp-r6b-toggle>
            ${config.enabled ? "Módulos para minipanel activos" : "Activar módulos para minipanel"}
          </button>
        </div>

        <div class="cx-mp-r6b-summary" data-cx-mp-r6b-summary>
          ${summaryHtml(config)}
        </div>

        <div class="cx-mp-r6b-body" data-cx-mp-r6b-body ${config.enabled ? "" : "hidden"}>
          <div class="cx-mp-r6b-panels">
            ${panels.map((panel) => {
              const row = config.panels[panel.type];
              const selected = config.selected_panel === panel.type;
              const count = Array.isArray(row.modules) ? row.modules.length : 0;

              return `
                <button type="button" class="cx-mp-r6b-panel ${selected ? "is-selected" : ""}" data-cx-mp-r6b-panel="${panel.type}">
                  <span>${panel.label}</span>
                  <small>${count} módulos asignados</small>
                  <code>${row.link}</code>
                </button>
              `;
            }).join("")}
          </div>

          <div class="cx-mp-r6b-selected">
            <div>
              <strong>Panel seleccionado: ${panelLabel(config.selected_panel)}</strong>
              <p>${config.panels?.[config.selected_panel]?.link || ""}</p>
            </div>
          </div>

          <div class="cx-mp-r6b-assigned">
            <strong>Módulos asignados a ${panelLabel(config.selected_panel)}</strong>
            ${assignedListHtml(config)}
          </div>
        </div>
      </section>
    `;
  }

  function summaryHtml(config) {
    if (!config.enabled) return "Desactivado. Activa el botón para asignar módulos existentes.";
    return `Panel destino: <strong>${panelLabel(config.selected_panel)}</strong> · Módulos asignados: <strong>${selectedModules(config).length}</strong>`;
  }

  function renderSection(companyId, config) {
    const section = document.getElementById(SECTION_ID);
    if (!section) return;

    section.outerHTML = buildSection(companyId, config);
  }

  function refreshModuleButtons(companyId, config) {
    const selected = config.selected_panel;
    const label = panelLabel(selected);

    getModuleCards().forEach((card) => {
      const code = extractModuleCode(card);
      const name = extractModuleName(card);

      if (!code || shouldSkip(code, name)) return;

      let slot = card.querySelector("[data-cx-mp-r6b-slot]");
      if (!slot) {
        slot = document.createElement("div");
        slot.setAttribute("data-cx-mp-r6b-slot", "1");
        slot.className = "cx-mp-r6b-slot";
        card.appendChild(slot);
      }

      if (!config.enabled || !selected || !config.panels?.[selected]?.enabled) {
        slot.innerHTML = "";
        return;
      }

      const modules = uniqueCodes022A(selectedModules(config));
      const added = modules.includes(code);

      slot.innerHTML = `
        <button type="button"
          class="cx-mp-r6b-module-btn ${added ? "is-on" : ""}"
          data-cx-mp-r6b-add="${code}"
          data-cx-mp-r6b-name="${String(name).replaceAll('"', '&quot;')}">
          ${added ? `Agregado a ${label}` : `Agregar a mini panel ${label}`}
        </button>
      `;
    });
  }

  function removeOldSections() {
    [
      "cx-company-minipanel-internal-section",
      "cx-company-minipanel-existing-modules-section",
      "cx-mini-panel-modules-final",
      "cx-mini-panel-assignment-final"
    ].forEach((id) => document.getElementById(id)?.remove());

    Array.from(document.querySelectorAll(
      ".cx-mini-internal-section,.cx-mp-existing-section,.cx-mp-final-section,.cx-mp-r5-section,[data-cx-mp-module-slot],[data-cx-mp-final-slot],[data-cx-mp-r5-slot]"
    )).forEach((node) => node.remove());
  }

  async function persistAndRefresh(companyId, config) {
    const saved = saveLocal(companyId, config);
    renderSection(companyId, saved);
    refreshModuleButtons(companyId, saved);
    await saveRemote(companyId, saved);
  }

  async function mount() {
    if (!isCompanyModulesTab()) return;

    removeOldSections();

    if (!hasMiniPanelActive()) {
      document.getElementById(SECTION_ID)?.remove();
      return;
    }

    const companyId = getCompanyId();
    const remote = await loadRemoteConfig022A(companyId);
    let config = normalizeConfig(companyId, remote || loadConfig(companyId));
    config = saveLocal(companyId, config);

    if (!document.getElementById(SECTION_ID)) {
      const anchor = findHeading("Buscar módulo");
      if (!anchor || !anchor.parentNode) return;

      const wrapper = document.createElement("div");
      wrapper.innerHTML = buildSection(companyId, config).trim();
      anchor.parentNode.insertBefore(wrapper.firstElementChild, anchor);
    } else {
      renderSection(companyId, config);
    }

    refreshModuleButtons(companyId, config);
  }

  document.addEventListener("click", async (event) => {
    const companyId = getCompanyId();

    const toggle = event.target.closest("[data-cx-mp-r6b-toggle]");
    if (toggle) {
      let config = normalizeConfig(companyId, loadConfig(companyId));
      config.enabled = !config.enabled;
      await persistAndRefresh(companyId, config);
      return;
    }

    const panelBtn = event.target.closest("[data-cx-mp-r6b-panel]");
    if (panelBtn) {
      let config = normalizeConfig(companyId, loadConfig(companyId));
      config.enabled = true;
      config.selected_panel = panelBtn.getAttribute("data-cx-mp-r6b-panel");
      await persistAndRefresh(companyId, config);
      return;
    }

    const addBtn = event.target.closest("[data-cx-mp-r6b-add]");
    if (addBtn) {
      let config = normalizeConfig(companyId, loadConfig(companyId));
      const panel = config.selected_panel;
      const rawCode = addBtn.getAttribute("data-cx-mp-r6b-add");
      const code = canonicalModuleCode022A(rawCode);
      const name = addBtn.getAttribute("data-cx-mp-r6b-name") || code;

      if (!panel || !code) return;

      config.panels[panel].modules = uniqueCodes022A(config.panels[panel].modules);
      config.module_names[code] = name;

      if (config.panels[panel].modules.includes(code)) {
        config.panels[panel].modules = config.panels[panel].modules.filter((item) => canonicalModuleCode022A(item) !== code);
      } else {
        config.panels[panel].modules.push(code);
      }

      await persistAndRefresh(companyId, config);
      return;
    }

    const removeBtn = event.target.closest("[data-cx-mp-r6b-remove]");
    if (removeBtn) {
      let config = normalizeConfig(companyId, loadConfig(companyId));
      const panel = config.selected_panel;
      const code = canonicalModuleCode022A(removeBtn.getAttribute("data-cx-mp-r6b-remove"));

      if (!panel || !code) return;

      config.panels[panel].modules = (config.panels[panel].modules || []).filter((item) => canonicalModuleCode022A(item) !== code);
      await persistAndRefresh(companyId, config);
    }
  });

  let timer = null;
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => {
      try {
        Promise.resolve(mount()).catch((error) => console.warn("CLONEXA 022A hierarchy:", error));
      } catch (error) {
        console.warn("CLONEXA 022A hierarchy:", error);
      }
    }, 250);
  }

  document.addEventListener("DOMContentLoaded", schedule);
  document.addEventListener("change", schedule);
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });

  schedule();
})();
/* CLONEXA_019G_R6B_RESTORE_FINAL_END */
// CLONEXA_FORCE_BUILD_019G_R6B_20260513_164425

