(() => {
  "use strict";

  const API = {
    health: "/health",
    healthFallback: "/api/v1/health",
    companies: "/api/v1/companies",
    company: (id) => `/api/v1/companies/${encodeURIComponent(id)}`,
    packages: "/api/v1/packages",
    modules: "/api/v1/modules",
    companyModules: (id) => `/api/v1/companies/${encodeURIComponent(id)}/modules`,
    activatePackage: (id) => `/api/v1/companies/${encodeURIComponent(id)}/activate-package`,
    companyUsers: (id) => `/api/v1/companies/${encodeURIComponent(id)}/users`,
    companyUser: (companyId, userId) => `/api/v1/companies/${encodeURIComponent(companyId)}/users/${encodeURIComponent(userId)}`,
    resetPassword: (companyId, userId) => `/api/v1/companies/${encodeURIComponent(companyId)}/users/${encodeURIComponent(userId)}/reset-password`,
    unlockUser: (companyId, userId) => `/api/v1/companies/${encodeURIComponent(companyId)}/users/${encodeURIComponent(userId)}/unlock`,
    experience: (id) => `/api/v1/companies/${encodeURIComponent(id)}/experience`,
    ensureExperience: (id) => `/api/v1/companies/${encodeURIComponent(id)}/experience/ensure-defaults`,
  };

  const state = {
    health: null,
    companies: [],
    packages: [],
    modules: [],
    companyModules: new Map(),
    companyUsers: new Map(),
    selectedCompanyId: "",
    selectedCompany: null,
    sectionErrors: {},
    lastRefresh: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const DOM = {
    apiBadge: "#apiBadge",
    apiBadgeText: "#apiBadgeText",
    refreshBtn: "#refreshBtn",
    openCreateCompanyBtn: "#openCreateCompanyBtn",
    mCompanies: "#mCompanies",
    mPackages: "#mPackages",
    mModules: "#mModules",
    mActiveCompanies: "#mActiveCompanies",
    mApi: "#mApi",
    mRefresh: "#mRefresh",
    hApi: "#hApi",
    hDb: "#hDb",
    hCompanies: "#hCompanies",
    hPackages: "#hPackages",
    hModules: "#hModules",
    hRefresh: "#hRefresh",
    frontendErrors: "#frontendErrors",
    createCompanyForm: "#createCompanyForm",
    companyName: "#companyName",
    companySlug: "#companySlug",
    companyTimezone: "#companyTimezone",
    packageSelect: "#packageSelect",
    clearForm: "#clearForm",
    companiesBody: "#companiesBody",
    companiesCount: "#companiesCount",
    detailName: "#detailName",
    detailStatus: "#detailStatus",
    detailContent: "#detailContent",
    packagesGrid: "#packagesGrid",
    packagesCount: "#packagesCount",
    modulesGroups: "#modulesGroups",
    modulesCount: "#modulesCount",
    toastHost: "#toastHost",
    brandLogo: "#brandLogo",
    brandFallback: "#brandFallback",
  };

  function el(keyOrSelector) {
    return $(DOM[keyOrSelector] || keyOrSelector);
  }

  function text(value, fallback = "—") {
    return value === null || value === undefined || value === "" ? fallback : String(value);
  }

  function escapeHtml(value) {
    return text(value, "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function safeArray(value, keys = []) {
    if (Array.isArray(value)) return value;
    if (!value || typeof value !== "object") return [];
    const candidates = [
      ...keys,
      "items",
      "data",
      "results",
      "companies",
      "packages",
      "modules",
      "users",
      "company_users",
      "companyModules",
      "company_modules",
      "active_modules",
    ];
    for (const key of candidates) {
      if (Array.isArray(value[key])) return value[key];
    }
    return [];
  }

  function idOf(item) {
    return item?.id || item?.company_id || item?.uuid || item?.companyId || "";
  }

  function codeOf(item) {
    return item?.code || item?.module_code || item?.package_code || item?.slug || item?.name || "";
  }

  function statusOf(item) {
    const raw = String(item?.status ?? item?.state ?? "").toLowerCase();
    const flag = item?.is_active ?? item?.active ?? item?.enabled;
    if (["active", "activo", "ready", "online", "live"].includes(raw) || flag === true) return "active";
    if (["inactive", "inactivo", "disabled"].includes(raw) || flag === false) return "inactive";
    return raw || "active";
  }

  function companyName(company) {
    return company?.name || company?.company_name || company?.legal_name || "Empresa";
  }

  function companySlug(company) {
    return company?.slug || company?.company_slug || "";
  }

  function companyPlan(company) {
    return company?.plan || company?.package_code || company?.current_package_code || company?.subscription_plan || "—";
  }

  function companyTimezone(company) {
    return company?.timezone || company?.tz || "America/Bogota";
  }

  function moduleCode(item) {
    return item?.code || item?.module_code || item?.module?.code || item?.module?.module_code || item?.name || "";
  }

  function moduleName(item) {
    return item?.name || item?.module_name || item?.module?.name || moduleCode(item);
  }

  function moduleCategory(item) {
    const explicit = item?.category || item?.module?.category;
    if (explicit) return explicit;
    const code = String(moduleCode(item)).toLowerCase();
    if (["core", "workforce"].includes(code)) return "core";
    if (["field", "gps", "materials"].includes(code)) return "field";
    if (["hospitality", "orders", "tables", "stock", "loyalty", "qr", "day_closing"].includes(code)) return "hospitality";
    if (["retail", "stores", "sales", "requests", "commercial_closing"].includes(code)) return "retail";
    if (["production", "references", "costs"].includes(code)) return "production";
    if (code === "inventory") return "inventory";
    if (code === "payroll") return "finance";
    if (code === "bots") return "input";
    if (["crm", "kpis", "reports"].includes(code)) return "read_model";
    return "uncategorized";
  }

  function setText(selectorOrId, value) {
    const node = selectorOrId.startsWith("#") || selectorOrId.startsWith(".") ? $(selectorOrId) : el(selectorOrId);
    if (node) node.textContent = text(value);
  }

  function setError(section, message) {
    state.sectionErrors[section] = message;
    renderErrors();
  }

  function clearError(section) {
    delete state.sectionErrors[section];
    renderErrors();
  }

  function clearAdminError() {
    state.sectionErrors = {};
    renderErrors();
  }

  function showAdminError(message) {
    setError("admin", message);
  }

  function renderErrors() {
    const box = el("frontendErrors");
    if (!box) return;
    const messages = Object.entries(state.sectionErrors).filter(([, msg]) => msg);
    if (!messages.length) {
      box.classList.add("hidden");
      box.innerHTML = "";
      return;
    }
    box.classList.remove("hidden");
    box.innerHTML = messages.map(([section, msg]) => `<div><b>${escapeHtml(section)}</b>: ${escapeHtml(msg)}</div>`).join("");
  }

  function toast(type, title, message) {
    let host = el("toastHost");
    if (!host) {
      host = document.createElement("div");
      host.id = "toastHost";
      host.className = "toastHost";
      document.body.appendChild(host);
    }
    const item = document.createElement("div");
    item.className = `toast ${type || "info"}`;
    item.innerHTML = `<b>${escapeHtml(title || "CLONEXA")}</b><span>${escapeHtml(message || "")}</span>`;
    host.appendChild(item);
    setTimeout(() => {
      item.style.opacity = "0";
      item.style.transform = "translateY(8px)";
      item.style.transition = ".18s";
      setTimeout(() => item.remove(), 220);
    }, 4200);
  }

  async function apiFetch(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
    const raw = await response.text();
    let payload = null;
    try {
      payload = raw ? JSON.parse(raw) : null;
    } catch {
      payload = raw;
    }
    if (!response.ok) {
      const detail = payload?.detail || payload?.message || payload?.error || payload?.raw || raw || `${response.status} ${response.statusText}`;
      const error = new Error(String(detail));
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  const apiGet = (path) => apiFetch(path);
  const apiPost = (path, body = {}) => apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });
  const apiPut = (path, body = {}) => apiFetch(path, { method: "PUT", body: JSON.stringify(body || {}) });

  async function postFallback(path, payloads) {
    let lastError = null;
    for (const payload of payloads) {
      try {
        return await apiPost(path, payload);
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error("POST falló");
  }

  async function loadHealth() {
    try {
      let health;
      try {
        health = await apiGet(API.health);
      } catch {
        health = await apiGet(API.healthFallback);
      }
      state.health = health || { ok: true };
      clearError("health");
      return state.health;
    } catch (error) {
      state.health = null;
      setError("health", `No se pudo cargar health: ${error.message}`);
      return null;
    }
  }

  async function loadCompanies() {
    try {
      const payload = await apiGet(API.companies);
      state.companies = safeArray(payload, ["companies"]);
      clearError("companies");
      return state.companies;
    } catch (error) {
      state.companies = [];
      setError("companies", `No se pudieron cargar empresas: ${error.message}`);
      return [];
    }
  }

  async function loadModules() {
    try {
      const payload = await apiGet(API.modules);
      state.modules = safeArray(payload, ["modules"]);
      clearError("modules");
      return state.modules;
    } catch (error) {
      state.modules = [];
      setError("modules", `No se pudieron cargar módulos: ${error.message}`);
      return [];
    }
  }

  async function loadPackages() {
    try {
      const payload = await apiGet(API.packages);
      state.packages = safeArray(payload, ["packages"]);
      clearError("packages");
      return state.packages;
    } catch (error) {
      state.packages = [];
      setError("packages", `No se pudieron cargar paquetes: ${error.message}`);
      return [];
    }
  }

  async function loadCompanyModules(companyId) {
    if (!companyId) return [];
    try {
      const payload = await apiGet(API.companyModules(companyId));
      const rows = safeArray(payload, ["modules", "company_modules", "active_modules"]);
      state.companyModules.set(String(companyId), rows);
      clearError(`modules:${companyId}`);
      return rows;
    } catch (error) {
      state.companyModules.set(String(companyId), []);
      setError(`modules:${companyId}`, `Módulos de empresa no disponibles: ${error.message}`);
      return [];
    }
  }

  async function loadCompanyUsers(companyId) {
    if (!companyId) return [];
    try {
      const payload = await apiGet(API.companyUsers(companyId));
      const rows = safeArray(payload, ["users", "company_users"]);
      state.companyUsers.set(String(companyId), rows);
      clearError(`users:${companyId}`);
      return rows;
    } catch (error) {
      state.companyUsers.set(String(companyId), []);
      if (error.status === 404 || error.status === 405) {
        clearError(`users:${companyId}`);
      } else {
        setError(`users:${companyId}`, `Usuarios no disponibles: ${error.message}`);
      }
      return [];
    }
  }

  async function loadAdminDashboard() {
    clearAdminError();
    await Promise.allSettled([loadHealth(), loadCompanies(), loadPackages(), loadModules()]);
    state.lastRefresh = new Date();

    await Promise.allSettled(state.companies.map((company) => loadCompanyModules(idOf(company))));

    const selectedStillExists = state.companies.some((company) => String(idOf(company)) === String(state.selectedCompanyId));
    if (!selectedStillExists) {
      const first = state.companies[0];
      state.selectedCompanyId = first ? idOf(first) : "";
    }
    state.selectedCompany = state.companies.find((company) => String(idOf(company)) === String(state.selectedCompanyId)) || null;

    renderDashboard();
  }

  function renderDashboard() {
    renderHealth();
    renderMetrics();
    renderPackageSelect();
    renderCompanies();
    renderPackages();
    renderModules();
    if (state.selectedCompany) {
      renderCompanyDetail(state.selectedCompany);
    } else {
      const content = el("detailContent");
      if (content) content.innerHTML = `<div class="emptyBox">No hay empresa seleccionada.</div>`;
    }
  }

  function renderHealth() {
    const live = !!state.health;
    const badge = el("apiBadge");
    const apiText = el("apiBadgeText");
    if (badge) {
      badge.classList.toggle("loading", !live);
      badge.classList.toggle("ok", live);
    }
    if (apiText) apiText.textContent = live ? "LIVE" : "OFFLINE";
    setText("hApi", live ? "LIVE" : "OFFLINE");
    setText("hDb", live ? "Indirecto vía API" : "Sin respuesta");
    setText("hCompanies", state.companies.length);
    setText("hPackages", state.packages.length);
    setText("hModules", state.modules.length);
    setText("hRefresh", state.lastRefresh ? state.lastRefresh.toLocaleTimeString() : "—");
  }

  function renderMetrics() {
    const activeCompanies = state.companies.filter((company) => statusOf(company) === "active").length;
    setText("mCompanies", state.companies.length);
    setText("mPackages", state.packages.length);
    setText("mModules", state.modules.length);
    setText("mActiveCompanies", activeCompanies);
    setText("mApi", state.health ? "LIVE" : "OFFLINE");
    setText("mRefresh", state.lastRefresh ? state.lastRefresh.toLocaleTimeString() : "—");
    setText("companiesCount", `${state.companies.length} empresas`);
    setText("packagesCount", `${state.packages.length} paquetes`);
    setText("modulesCount", `${state.modules.length} módulos`);
  }

  function renderPackageSelect() {
    const select = el("packageSelect");
    if (!select) return;
    const current = select.value;
    select.innerHTML = `<option value="">Sin paquete</option>` + state.packages.map((pkg) => {
      const code = pkg.code || pkg.package_code || pkg.id || "";
      return `<option value="${escapeHtml(code)}">${escapeHtml(pkg.name || code)} · ${escapeHtml(code)}</option>`;
    }).join("");
    if (current) select.value = current;
  }

  function packageForCompany(company) {
    const direct = company?.package_code || company?.current_package_code || company?.active_package_code || company?.package?.code || company?.plan;
    if (direct && String(direct) !== "—") return String(direct);
    const modules = state.companyModules.get(String(idOf(company))) || [];
    const codes = new Set(modules.map((m) => String(moduleCode(m)).toLowerCase()));

    const packageSignatures = [
      ["field_pro_usa", ["field", "gps", "materials"]],
      ["hospitality_pro", ["hospitality", "orders", "tables"]],
      ["retail_ops", ["retail", "stores", "sales"]],
      ["production_pro", ["production", "references"]],
    ];
    for (const [pkg, required] of packageSignatures) {
      if (required.every((code) => codes.has(code))) return pkg;
    }
    return "—";
  }

  function activeModuleCount(company) {
    const rows = state.companyModules.get(String(idOf(company))) || [];
    if (!rows.length) return 0;
    return rows.filter((row) => row.enabled !== false && statusOf(row) !== "inactive").length;
  }

  function renderCompanies() {
    const body = el("companiesBody");
    if (!body) return;
    if (!state.companies.length) {
      body.innerHTML = `<tr><td colspan="9" class="empty">No hay empresas cargadas. Revisa /api/v1/companies.</td></tr>`;
      return;
    }

    body.innerHTML = state.companies.map((company) => {
      const cid = idOf(company);
      const selected = String(cid) === String(state.selectedCompanyId);
      const pkg = packageForCompany(company);
      const count = activeModuleCount(company);
      return `
        <tr class="${selected ? "selected" : ""}">
          <td><strong>${escapeHtml(companyName(company))}</strong></td>
          <td>${escapeHtml(companySlug(company))}</td>
          <td><span class="mini ${statusOf(company) === "active" ? "ok" : ""}">${escapeHtml(statusOf(company))}</span></td>
          <td>${escapeHtml(companyPlan(company))}</td>
          <td>${escapeHtml(companyTimezone(company))}</td>
          <td><code>${escapeHtml(cid)}</code></td>
          <td>${escapeHtml(pkg)}</td>
          <td>${count}</td>
          <td>
            <button class="btn tiny" data-admin-action="select-company" data-company-id="${escapeHtml(cid)}">Ver detalle</button>
            <button class="btn tiny ghost" data-admin-action="copy-id" data-copy="${escapeHtml(cid)}">Copiar ID</button>
            <button class="btn tiny accent" data-admin-action="configure-crm" data-company-id="${escapeHtml(cid)}">Configurar CRM</button>
          </td>
        </tr>
      `;
    }).join("");
  }

  function renderPackages() {
    const grid = el("packagesGrid");
    if (!grid) return;
    if (!state.packages.length) {
      grid.innerHTML = `<div class="emptyBox">No se pudieron cargar paquetes o no existen paquetes registrados.</div>`;
      return;
    }
    grid.innerHTML = state.packages.map((pkg) => {
      const code = pkg.code || pkg.package_code || pkg.id || "";
      const modules = safeArray(pkg.modules || pkg.package_modules || pkg.items).map(moduleCode).filter(Boolean);
      return `
        <article class="packageCard">
          <div class="titleRow">
            <div><span class="eyebrow">${escapeHtml(code)}</span><h3>${escapeHtml(pkg.name || code)}</h3></div>
            <span class="mini ${statusOf(pkg) === "active" ? "ok" : ""}">${escapeHtml(statusOf(pkg))}</span>
          </div>
          <p>${escapeHtml(pkg.description || "Paquete SaaS CLONEXA")}</p>
          <div class="chips">${modules.length ? modules.slice(0, 12).map((m) => `<span>${escapeHtml(m)}</span>`).join("") : "<span>Módulos vía paquete</span>"}</div>
          <button class="btn ghost" data-admin-action="package-info" data-package-code="${escapeHtml(code)}">Ver</button>
        </article>
      `;
    }).join("");
  }

  function renderModules() {
    const groups = el("modulesGroups");
    if (!groups) return;
    if (!state.modules.length) {
      groups.innerHTML = `<div class="emptyBox">No se pudieron cargar módulos o no existen módulos registrados.</div>`;
      return;
    }

    const byCategory = new Map();
    for (const module of state.modules) {
      const category = moduleCategory(module);
      if (!byCategory.has(category)) byCategory.set(category, []);
      byCategory.get(category).push(module);
    }

    groups.innerHTML = Array.from(byCategory.entries()).map(([category, modules]) => `
      <section class="moduleGroup">
        <h3>${escapeHtml(category)}</h3>
        <div class="moduleGrid">
          ${modules.map((module) => `
            <article>
              <b>${escapeHtml(moduleCode(module))}</b>
              <span>${escapeHtml(moduleName(module))}</span>
              <small>${escapeHtml(statusOf(module))}</small>
            </article>
          `).join("")}
        </div>
      </section>
    `).join("");
  }

  async function selectCompany(companyId) {
    state.selectedCompanyId = String(companyId || "");
    state.selectedCompany = state.companies.find((company) => String(idOf(company)) === state.selectedCompanyId) || null;
    if (!state.selectedCompany) return;
    await Promise.allSettled([loadCompanyModules(state.selectedCompanyId), loadCompanyUsers(state.selectedCompanyId)]);
    renderCompanies();
    renderCompanyDetail(state.selectedCompany);
  }

  async function loadCompanyDetail(companyId) {
    return selectCompany(companyId);
  }

  function renderCompanyModules(companyId) {
    const modules = state.companyModules.get(String(companyId)) || [];
    if (!modules.length) {
      return `<div class="emptyBox">No se pudieron cargar módulos activos para esta empresa.</div>`;
    }
    return `
      <div class="modulePills">
        ${modules.map((row) => {
          const code = moduleCode(row);
          const enabled = row.enabled !== false && statusOf(row) !== "inactive";
          return `<span class="${enabled ? "on" : "off"}">${escapeHtml(code)}</span>`;
        }).join("")}
      </div>
    `;
  }

  function renderCompanyUsers(companyId) {
    const users = state.companyUsers.get(String(companyId));
    if (!users) {
      return `<div class="emptyBox">Cargando usuarios de acceso…</div>`;
    }

    const userRows = users.length ? users.map((user) => `
      <tr>
        <td>${escapeHtml(user.email)}</td>
        <td>${escapeHtml(user.full_name || user.name || "")}</td>
        <td>${escapeHtml(user.role || "company_admin")}</td>
        <td>${escapeHtml(user.status || "active")}</td>
        <td>${user.must_change_password ? "Sí" : "No"}</td>
        <td>${escapeHtml(user.failed_login_attempts ?? 0)}</td>
        <td>${escapeHtml(user.locked_until || "—")}</td>
        <td>${escapeHtml(user.last_login_at || "—")}</td>
        <td>
          <button class="btn tiny ghost" data-admin-action="reset-user-password" data-company-id="${escapeHtml(companyId)}" data-user-id="${escapeHtml(user.id)}">Reset password</button>
          <button class="btn tiny ghost" data-admin-action="unlock-user" data-company-id="${escapeHtml(companyId)}" data-user-id="${escapeHtml(user.id)}">Desbloquear</button>
          <button class="btn tiny ghost" data-admin-action="toggle-user-status" data-company-id="${escapeHtml(companyId)}" data-user-id="${escapeHtml(user.id)}" data-status="${escapeHtml(user.status === "active" ? "inactive" : "active")}">${user.status === "active" ? "Desactivar" : "Activar"}</button>
        </td>
      </tr>
    `).join("") : `<tr><td colspan="9" class="empty">No hay usuarios o la gestión de usuarios no está disponible en este entorno.</td></tr>`;

    return `
      <div class="companyUsers">
        <div class="titleRow">
          <div><span class="eyebrow">ACCESS CONTROL</span><h3>Usuarios de acceso</h3></div>
          <span class="mini">${users.length} usuarios</span>
        </div>
        <form id="accessUserForm" class="form accessUserForm" data-company-id="${escapeHtml(companyId)}">
          <label><span>Email</span><input name="email" type="email" placeholder="admin@empresa.com" required /></label>
          <label><span>Nombre</span><input name="full_name" placeholder="Empresa Admin" required /></label>
          <label><span>Rol</span>
            <select name="role">
              <option value="company_admin">company_admin</option>
              <option value="manager">manager</option>
              <option value="operator">operator</option>
              <option value="viewer">viewer</option>
            </select>
          </label>
          <label><span>Status</span>
            <select name="status">
              <option value="active">active</option>
              <option value="inactive">inactive</option>
              <option value="blocked">blocked</option>
            </select>
          </label>
          <label><span>Contraseña temporal</span><input name="password" placeholder="Temporal123!" required /></label>
          <div class="actions">
            <button class="btn accent" type="submit">Crear usuario</button>
            <button class="btn ghost" type="button" data-admin-action="generate-temp-password">Generar contraseña</button>
          </div>
        </form>
        <div class="tableWrap">
          <table>
            <thead>
              <tr><th>Email</th><th>Nombre</th><th>Rol</th><th>Estado</th><th>Cambio requerido</th><th>Intentos</th><th>Bloqueado hasta</th><th>Último login</th><th>Acciones</th></tr>
            </thead>
            <tbody>${userRows}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderCompanyDetail(company) {
    const title = el("detailName");
    const status = el("detailStatus");
    const content = el("detailContent");
    if (!company || !content) return;
    const cid = idOf(company);
    if (title) title.textContent = companyName(company);
    if (status) status.textContent = statusOf(company).toUpperCase();

    const pkg = packageForCompany(company);
    const modulesHtml = renderCompanyModules(cid);
    const usersHtml = renderCompanyUsers(cid);

    content.innerHTML = `
      <div class="detailStack">
        <section class="detailHero">
          <div>
            <span class="eyebrow">${escapeHtml(companySlug(company))}</span>
            <h3>${escapeHtml(companyName(company))}</h3>
            <p>Company ID: <code>${escapeHtml(cid)}</code></p>
          </div>
          <div class="actions">
            <button class="btn accent" data-admin-action="configure-crm" data-company-id="${escapeHtml(cid)}">Configurar CRM</button>
            <button class="btn ghost" data-admin-action="copy-id" data-copy="${escapeHtml(cid)}">Copiar company_id</button>
            <button class="btn ghost" data-admin-action="reload-company-detail" data-company-id="${escapeHtml(cid)}">Ver módulos</button>
          </div>
        </section>
        <section class="detailGrid">
          <div><span>Estado</span><b>${escapeHtml(statusOf(company))}</b></div>
          <div><span>Plan</span><b>${escapeHtml(companyPlan(company))}</b></div>
          <div><span>Timezone</span><b>${escapeHtml(companyTimezone(company))}</b></div>
          <div><span>Paquete detectado</span><b>${escapeHtml(pkg)}</b></div>
          <div><span>Módulos activos</span><b>${activeModuleCount(company)}</b></div>
        </section>
        <section>
          <div class="titleRow"><div><span class="eyebrow">ACTIVE MODULES</span><h3>Módulos activos</h3></div></div>
          ${modulesHtml}
        </section>
        <section class="packageActivator">
          <div class="titleRow"><div><span class="eyebrow">PACKAGE OPS</span><h3>Activar paquete</h3></div></div>
          <div class="inlineForm">
            <select id="detailPackageSelect">${state.packages.map((pkg) => {
              const code = pkg.code || pkg.package_code || pkg.id || "";
              return `<option value="${escapeHtml(code)}">${escapeHtml(pkg.name || code)} · ${escapeHtml(code)}</option>`;
            }).join("")}</select>
            <button class="btn accent" data-admin-action="activate-selected-package" data-company-id="${escapeHtml(cid)}">Activar paquete</button>
          </div>
        </section>
        ${usersHtml}
      </div>
    `;
  }

  async function createCompany(event) {
    event.preventDefault();
    const nameNode = el("companyName");
    const slugNode = el("companySlug");
    const timezoneNode = el("companyTimezone");
    const packageNode = el("packageSelect");
    const submit = event.submitter || event.target.querySelector("button[type='submit']");

    const name = nameNode?.value?.trim();
    const slug = slugNode?.value?.trim();
    const timezone = timezoneNode?.value?.trim() || "America/Bogota";
    const packageCode = packageNode?.value?.trim();

    if (!name || !slug) {
      toast("error", "Datos incompletos", "Nombre y slug son obligatorios.");
      return;
    }

    if (submit) {
      submit.disabled = true;
      submit.textContent = "Creando…";
    }

    try {
      const payloads = [
        { name, slug, timezone, status: "active", plan: packageCode || "custom" },
        { name, slug, timezone },
        { company: { name, slug, timezone, status: "active", plan: packageCode || "custom" } },
      ];
      const created = await postFallback(API.companies, payloads);
      const company = created?.company || created?.data || created;
      const companyId = idOf(company);
      if (!companyId) throw new Error("La API creó la empresa pero no retornó id/company_id.");

      if (packageCode) {
        await activateCompanyPackage(companyId, packageCode, { silent: true });
      }

      toast("success", "Empresa creada", `${name} fue creada correctamente.`);
      event.target.reset();
      if (timezoneNode) timezoneNode.value = "America/Bogota";
      await loadAdminDashboard();
      await selectCompany(companyId);
      $("#companies")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      const duplicate = /unique|duplicate|already|existe|exist/i.test(error.message);
      toast("error", duplicate ? "Empresa ya existe" : "Error creando empresa", duplicate ? "La empresa o slug ya existe." : error.message);
      showAdminError(`Crear empresa falló: ${error.message}`);
    } finally {
      if (submit) {
        submit.disabled = false;
        submit.textContent = "Crear y activar";
      }
    }
  }

  async function activateCompanyPackage(companyId, packageCode, options = {}) {
    if (!companyId || !packageCode) return;
    await postFallback(API.activatePackage(companyId), [
      { package_code: packageCode, settings: {} },
      { code: packageCode, settings: {} },
      { package_id: packageCode, settings: {} },
    ]);
    await loadCompanyModules(companyId);
    if (!options.silent) {
      toast("success", "Paquete activado", `${packageCode} fue activado.`);
      renderCompanies();
      if (String(companyId) === String(state.selectedCompanyId)) renderCompanyDetail(state.selectedCompany);
    }
  }

  async function createCompanyUser(companyId, form) {
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      await apiPost(API.companyUsers(companyId), {
        email: data.email,
        full_name: data.full_name,
        role: data.role || "company_admin",
        password: data.password,
        status: data.status || "active",
      });
      toast("success", "Usuario creado", data.email);
      form.reset();
      await loadCompanyUsers(companyId);
      renderCompanyDetail(state.selectedCompany);
    } catch (error) {
      toast("error", "No se pudo crear usuario", error.message);
    }
  }

  async function resetCompanyUserPassword(companyId, userId) {
    const custom = prompt("Contraseña temporal opcional. Deja vacío para generar una automáticamente.");
    try {
      const payload = custom ? { password: custom } : {};
      const result = await apiPost(API.resetPassword(companyId, userId), payload);
      const password = result?.temporary_password || custom || "Generada por el backend";
      await loadCompanyUsers(companyId);
      renderCompanyDetail(state.selectedCompany);
      showTemporaryPassword(password);
    } catch (error) {
      toast("error", "Reset falló", error.message);
    }
  }

  async function unlockCompanyUser(companyId, userId) {
    try {
      await apiPost(API.unlockUser(companyId, userId), {});
      toast("success", "Usuario desbloqueado", "Intentos y bloqueo fueron limpiados.");
      await loadCompanyUsers(companyId);
      renderCompanyDetail(state.selectedCompany);
    } catch (error) {
      toast("error", "Unlock falló", error.message);
    }
  }

  async function toggleCompanyUserStatus(companyId, userId, status) {
    try {
      await apiPut(API.companyUser(companyId, userId), { status });
      toast("success", "Usuario actualizado", `Nuevo estado: ${status}`);
      await loadCompanyUsers(companyId);
      renderCompanyDetail(state.selectedCompany);
    } catch (error) {
      toast("error", "No se pudo actualizar", error.message);
    }
  }

  function showTemporaryPassword(password) {
    let modal = $("#temp-password-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "temp-password-modal";
      modal.style.cssText = "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;padding:20px;";
      modal.innerHTML = `
        <div class="panel card" style="width:min(520px,100%);">
          <div class="titleRow"><div><span class="eyebrow">ACCESS PASSWORD</span><h2>Contraseña temporal generada</h2></div></div>
          <p>Esta contraseña solo se muestra una vez.</p>
          <input id="tempPasswordValue" readonly style="width:100%;margin:12px 0;" />
          <div class="actions">
            <button class="btn accent" data-admin-action="copy-temp-password">Copiar</button>
            <button class="btn ghost" data-admin-action="close-temp-password">Cerrar</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    $("#tempPasswordValue", modal).value = password;
    modal.style.display = "flex";
  }

  function generateTemporaryPassword() {
    const random = Math.random().toString(36).slice(2, 8).toUpperCase();
    return `Clonexa-${random}-${new Date().getFullYear()}!`;
  }

  async function copyText(value) {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    toast("success", "Copiado", "Texto copiado al portapapeles.");
  }

  function slugify(value) {
    return String(value || "")
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function ensureCrmModal() {
    let modal = $("#admin-crm-lite-modal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "admin-crm-lite-modal";
    modal.style.cssText = "position:fixed;inset:0;z-index:99990;background:rgba(0,0,0,.72);display:none;align-items:center;justify-content:center;padding:20px;";
    modal.innerHTML = `
      <div class="panel card" style="width:min(980px,100%);max-height:90vh;overflow:auto;">
        <div class="titleRow">
          <div><span class="eyebrow">CRM BUILDER</span><h2 id="crmLiteTitle">Configurar CRM</h2></div>
          <div class="actions">
            <button class="btn accent" data-admin-action="crm-ensure-defaults">Regenerar defaults</button>
            <button class="btn ghost" data-admin-action="crm-close">Cerrar</button>
          </div>
        </div>
        <div id="crmLiteContent" class="emptyBox">Cargando experiencia…</div>
      </div>
    `;
    document.body.appendChild(modal);
    return modal;
  }

  async function openCrmBuilder(companyId) {
    const company = state.companies.find((row) => String(idOf(row)) === String(companyId));
    const modal = ensureCrmModal();
    const title = $("#crmLiteTitle", modal);
    const content = $("#crmLiteContent", modal);
    modal.dataset.companyId = companyId;
    if (title) title.textContent = `Configurar CRM · ${companyName(company)}`;
    modal.style.display = "flex";
    if (content) content.innerHTML = "Cargando experiencia…";

    try {
      const experience = await apiGet(API.experience(companyId));
      const launchpad = safeArray(experience?.launchpad_cards || experience?.launchpadCards);
      const widgets = safeArray(experience?.widgets || experience?.crm_widgets);
      const sections = safeArray(experience?.sections || experience?.crm_sections);
      const actions = safeArray(experience?.actions || experience?.crm_actions);
      const fieldConfigs = safeArray(experience?.field_configs || experience?.fieldConfigs);
      const alerts = safeArray(experience?.alert_rules || experience?.alerts);
      const branding = experience?.branding || {};

      if (content) {
        content.innerHTML = `
          <div class="detailGrid">
            <div><span>Branding</span><b>${escapeHtml(branding.visual_preset || branding.industry_theme || "default")}</b></div>
            <div><span>Launchpad</span><b>${launchpad.length}</b></div>
            <div><span>Widgets</span><b>${widgets.length}</b></div>
            <div><span>Secciones</span><b>${sections.length}</b></div>
            <div><span>Acciones</span><b>${actions.length}</b></div>
            <div><span>Campos</span><b>${fieldConfigs.length}</b></div>
            <div><span>Alertas</span><b>${alerts.length}</b></div>
          </div>
          <div class="emptyBox" style="margin-top:12px;">
            CRM Builder activo. Este modal no bloquea la carga de empresas, paquetes ni módulos. Si los datos de experience están vacíos, usa Regenerar defaults.
          </div>
        `;
      }
    } catch (error) {
      if (content) {
        content.innerHTML = `<div class="emptyBox">No se pudo cargar experience: ${escapeHtml(error.message)}<br/>Admin Console seguirá funcionando.</div>`;
      }
    }
  }

  async function ensureCrmDefaults(companyId) {
    try {
      await apiPost(API.ensureExperience(companyId), {});
      toast("success", "Defaults regenerados", "La experiencia fue preparada.");
      await openCrmBuilder(companyId);
    } catch (error) {
      toast("error", "No se pudieron regenerar defaults", error.message);
    }
  }

  function bindEvents() {
    const logo = el("brandLogo");
    const fallback = el("brandFallback");
    if (logo && fallback) {
      logo.addEventListener("error", () => {
        logo.style.display = "none";
        fallback.style.display = "block";
      });
    }

    el("refreshBtn")?.addEventListener("click", async () => {
      const btn = el("refreshBtn");
      btn.disabled = true;
      btn.textContent = "Refrescando…";
      await loadAdminDashboard();
      btn.disabled = false;
      btn.textContent = "Refrescar";
      toast("success", "Refresh completo", "Datos actualizados.");
    });

    el("openCreateCompanyBtn")?.addEventListener("click", () => {
      $("#createPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
      setTimeout(() => el("companyName")?.focus(), 250);
    });

    el("createCompanyForm")?.addEventListener("submit", createCompany);
    el("clearForm")?.addEventListener("click", () => {
      el("createCompanyForm")?.reset();
      if (el("companyTimezone")) el("companyTimezone").value = "America/Bogota";
    });

    el("companyName")?.addEventListener("input", () => {
      const slug = el("companySlug");
      if (slug && !slug.dataset.touched) slug.value = slugify(el("companyName").value);
    });
    el("companySlug")?.addEventListener("input", () => {
      const slug = el("companySlug");
      slug.dataset.touched = "1";
      slug.value = slugify(slug.value);
    });

    document.addEventListener("submit", async (event) => {
      if (event.target?.id === "accessUserForm") {
        event.preventDefault();
        const companyId = event.target.dataset.companyId || state.selectedCompanyId;
        await createCompanyUser(companyId, event.target);
      }
    });

    document.addEventListener("click", async (event) => {
      const actionEl = event.target.closest("[data-admin-action]");
      if (!actionEl) {
        const nav = event.target.closest("[data-target]");
        if (nav) {
          $$(".navBtn").forEach((button) => button.classList.remove("active"));
          nav.classList.add("active");
          $(nav.dataset.target)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        return;
      }

      const action = actionEl.dataset.adminAction;
      const companyId = actionEl.dataset.companyId || state.selectedCompanyId;
      const userId = actionEl.dataset.userId;

      try {
        if (action === "select-company") {
          await selectCompany(companyId);
          $(".detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
        } else if (action === "copy-id") {
          await copyText(actionEl.dataset.copy || companyId);
        } else if (action === "configure-crm") {
          await openCrmBuilder(companyId);
        } else if (action === "reload-company-detail") {
          await selectCompany(companyId);
        } else if (action === "activate-selected-package") {
          const select = $("#detailPackageSelect");
          await activateCompanyPackage(companyId, select?.value || "");
        } else if (action === "package-info") {
          toast("info", "Paquete", actionEl.dataset.packageCode || "Paquete SaaS");
        } else if (action === "generate-temp-password") {
          const input = $("#accessUserForm input[name='password']");
          if (input) input.value = generateTemporaryPassword();
        } else if (action === "reset-user-password") {
          await resetCompanyUserPassword(companyId, userId);
        } else if (action === "unlock-user") {
          await unlockCompanyUser(companyId, userId);
        } else if (action === "toggle-user-status") {
          await toggleCompanyUserStatus(companyId, userId, actionEl.dataset.status || "inactive");
        } else if (action === "copy-temp-password") {
          await copyText($("#tempPasswordValue")?.value || "");
        } else if (action === "close-temp-password") {
          const modal = $("#temp-password-modal");
          if (modal) modal.style.display = "none";
        } else if (action === "crm-close") {
          const modal = $("#admin-crm-lite-modal");
          if (modal) modal.style.display = "none";
        } else if (action === "crm-ensure-defaults") {
          const modal = $("#admin-crm-lite-modal");
          await ensureCrmDefaults(modal?.dataset.companyId || companyId);
        }
      } catch (error) {
        toast("error", "Acción falló", error.message);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    bindEvents();
    await loadAdminDashboard();
  });

  window.ClonexaAdmin = {
    state,
    apiGet,
    apiPost,
    apiPut,
    loadHealth,
    loadCompanies,
    loadModules,
    loadPackages,
    loadAdminDashboard,
    selectCompany,
    loadCompanyDetail,
    loadCompanyModules,
    loadCompanyUsers,
    renderCompanyUsers,
    createCompany,
    activateCompanyPackage,
    createCompanyUser,
    resetCompanyUserPassword,
    unlockCompanyUser,
    showAdminError,
    clearAdminError,
  };
})();
