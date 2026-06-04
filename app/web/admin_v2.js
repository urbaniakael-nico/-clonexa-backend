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
    companyAccessPolicies: new Map(),
    companySessionPolicies: new Map(),
    companyAccessSessions: new Map(),
    adminV2Sessions: null,
    companyActivity: new Map(),
    companyResetPreviews: new Map(),
    companyResetBusy: false,
    dashboardActivityErrors: [],
    selectedCompanyId: null,
    activeView: "dashboard",
    activeDetailTab: "resumen",
    companyFilter: "visible",
    moduleFilters: {
      search: "",
      status: "all",
      category: "all",
      assignment: "all",
      company: "all",
    },
    masterAccessFilters: {
      search: "",
      status: "all",
    },
    landingAnalytics: null,
    landingFilters: {
      days: "30",
      source: "",
      campaign: "",
      device: "",
    },
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

  function ensureAdminV2SecurityControls025R() {
    const actions = el(".cx-topbar-actions");
    if (actions && !el("#adminV2LogoutBtn025R")) {
      const button = document.createElement("button");
      button.id = "adminV2LogoutBtn025R";
      button.type = "button";
      button.className = "cx-btn cx-btn-danger";
      button.dataset.adminV2Logout = "true";
      button.textContent = "Cerrar sesion";
      actions.appendChild(button);
    }

    const nav = el(".cx-nav");
    if (nav && !nav.querySelector('[data-view="landing"]')) {
      const button = document.createElement("button");
      button.className = "cx-nav-item";
      button.type = "button";
      button.dataset.view = "landing";
      button.textContent = "Landing";
      nav.appendChild(button);
    }

    const main = el(".cx-main");
    if (main && !main.querySelector('[data-view-panel="landing"]')) {
      const section = document.createElement("section");
      section.className = "cx-view";
      section.dataset.viewPanel = "landing";
      section.innerHTML = `
        <article class="cx-card cx-landing-hero-025S">
          <div class="cx-card-head">
            <div>
              <h2>Analitica landing</h2>
              <p>Visitas reales, fuentes, campanas y comportamiento de la landing publica.</p>
            </div>
            <button class="cx-btn cx-btn-small" data-refresh-landing-analytics type="button">Actualizar</button>
          </div>
          <form class="cx-landing-filters-025S" id="landingFilters025S">
            <label>Periodo
              <select id="landingDays025S" name="days">
                <option value="7">7 dias</option>
                <option value="30" selected>30 dias</option>
                <option value="90">90 dias</option>
                <option value="365">365 dias</option>
              </select>
            </label>
            <label>Fuente
              <select id="landingSource025S" name="source"></select>
            </label>
            <label>Campana
              <select id="landingCampaign025S" name="campaign"></select>
            </label>
            <label>Dispositivo
              <select id="landingDevice025S" name="device"></select>
            </label>
            <button class="cx-btn cx-btn-primary" type="submit">Aplicar</button>
            <button class="cx-btn cx-btn-ghost" data-reset-landing-filters type="button">Limpiar</button>
          </form>
          <div class="cx-grid-metrics cx-landing-metrics-025S" id="landingMetrics025R"></div>
        </article>
        <div class="cx-landing-grid-025S">
          <article class="cx-card">
            <h3>Visitas por dia</h3>
            <div class="cx-landing-bars-025S" id="landingDaily025S"></div>
          </article>
          <article class="cx-card">
            <h3>Fuentes</h3>
            <div class="cx-landing-bars-025S" id="landingSources025R"></div>
          </article>
          <article class="cx-card">
            <h3>Campanas</h3>
            <div class="cx-landing-bars-025S" id="landingCampaigns025R"></div>
          </article>
          <article class="cx-card">
            <h3>Dispositivos</h3>
            <div class="cx-landing-bars-025S" id="landingDevices025S"></div>
          </article>
          <article class="cx-card cx-landing-wide-025S">
            <h3>Rutas visitadas</h3>
            <div class="cx-landing-bars-025S" id="landingPaths025S"></div>
          </article>
          <article class="cx-card cx-landing-wide-025S">
            <h3>Ultimas visitas</h3>
            <div class="cx-table-wrap">
              <table class="cx-table cx-landing-table-025S">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Fuente</th>
                    <th>Campana</th>
                    <th>Ruta</th>
                    <th>Dispositivo</th>
                    <th>Idioma / zona</th>
                  </tr>
                </thead>
                <tbody id="landingRecent025R"></tbody>
              </table>
            </div>
          </article>
        </div>
      `;
      main.appendChild(section);
    }
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
    if (companyAdmins.length > 1) return { owner, companyAdmins, status: "MULTIPLE", level: "warn" };
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

  const CX_DASHBOARD_ACTIVITY_LIMIT_023A = 12;
  const CX_DASHBOARD_MODULE_LABELS_023A = {
    sales: "Registro Venta",
    quotes: "Cotizaciones",
    notes: "Notas",
    references: "Referencias",
  };

  function cxDashboardNumber023A(value) {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }

  function cxDashboardTimestamp023A(...values) {
    let latest = 0;
    values.flat().forEach((value) => {
      if (!value) return;
      const date = new Date(value);
      if (!Number.isNaN(date.getTime())) latest = Math.max(latest, date.getTime());
    });
    return latest;
  }

  function cxDashboardDateLabel023A(value) {
    if (!value) return "Sin datos";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Sin datos";
    try {
      return new Intl.DateTimeFormat("es-CO", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
    } catch (_) {
      return date.toISOString().slice(0, 16).replace("T", " ");
    }
  }

  function cxDashboardClientUrl023A(company) {
    const origin = window.location.origin || "";
    return `${origin}/client?company_id=${encodeURIComponent(company?.id || "")}`;
  }

  function cxDashboardProbeCompanies023A() {
    return state.companies
      .filter((company) => !isArchivedCompany(company))
      .sort((a, b) => cxDashboardTimestamp023A(b.updated_at, b.created_at) - cxDashboardTimestamp023A(a.updated_at, a.created_at))
      .slice(0, CX_DASHBOARD_ACTIVITY_LIMIT_023A);
  }

  function cxDashboardExpectedUnavailable023A(message) {
    const text = String(message || "").toLowerCase();
    return (
      text.includes("no esta asignado")
      || text.includes("no está asignado")
      || text.includes("no esta activo")
      || text.includes("no está activo")
      || text.includes("not assigned")
      || text.includes("not active")
    );
  }

  function cxDashboardProbeValue023A(result, label, errors) {
    if (result.status === "fulfilled") return result.value || {};
    const message = result.reason?.message || "No disponible";
    if (!cxDashboardExpectedUnavailable023A(message)) {
      errors.push(`${label}: ${message}`);
    }
    return {};
  }

  async function loadCompanyActivity023A(company) {
    const companyId = company?.id;
    if (!companyId) return null;

    const encoded = encodeURIComponent(companyId);
    const probes = await Promise.allSettled([
      apiGet(`${API}/mini-panel-sales/companies/${encoded}/summary?panel_type=sales`),
      apiGet(`${API}/mini-panel-quotes/companies/${encoded}/summary?panel_type=all`),
      apiGet(`${API}/mini-panel-notes/companies/${encoded}/summary?panel_type=sales`),
      apiGet(`${API}/references-v1/companies/${encoded}/summary`),
    ]);

    const errors = [];
    const sales = cxDashboardProbeValue023A(probes[0], "Registro Venta", errors);
    const quotes = cxDashboardProbeValue023A(probes[1], "Cotizaciones", errors);
    const notes = cxDashboardProbeValue023A(probes[2], "Notas", errors);
    const references = cxDashboardProbeValue023A(probes[3], "Referencias", errors);
    const counts = {
      sales: cxDashboardNumber023A(sales.active_count ?? sales.count),
      quotes: cxDashboardNumber023A(quotes.active_count ?? quotes.count),
      notes: cxDashboardNumber023A(notes.count ?? notes.active_count),
      references: cxDashboardNumber023A(references.references_total ?? references.count),
    };
    const latestAt = cxDashboardTimestamp023A(
      sales.latest?.created_at,
      quotes.latest?.created_at,
      notes.next?.created_at,
      notes.next?.note_date,
      company.updated_at,
      company.created_at,
    );
    const moduleScores = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const topSignal = moduleScores[0] && moduleScores[0][1] > 0 ? moduleScores[0][0] : "";
    const totalSignals = Object.values(counts).reduce((sum, value) => sum + value, 0);
    const availableSignals = probes.filter((result) => result.status === "fulfilled").length;
    const activity = {
      company_id: companyId,
      counts,
      totalSignals,
      availableSignals,
      topSignal,
      latestAt,
      latestLabel: cxDashboardDateLabel023A(latestAt),
      errors,
    };

    state.companyActivity.set(companyId, activity);
    return activity;
  }

  async function loadDashboardActivity023A() {
    state.dashboardActivityErrors = [];
    state.companyActivity.clear();

    const companies = cxDashboardProbeCompanies023A();
    const results = await Promise.allSettled(companies.map(loadCompanyActivity023A));
    results.forEach((result) => {
      if (result.status === "rejected") {
        state.dashboardActivityErrors.push(result.reason?.message || "Error cargando actividad");
      }
    });
  }

  function cxDashboardActivities023A() {
    return [...state.companyActivity.values()];
  }

  function cxDashboardTopModule023A(activities = cxDashboardActivities023A()) {
    const totals = { sales: 0, quotes: 0, notes: 0, references: 0 };
    activities.forEach((activity) => {
      Object.keys(totals).forEach((key) => {
        totals[key] += cxDashboardNumber023A(activity.counts?.[key]);
      });
    });
    const [code, value] = Object.entries(totals).sort((a, b) => b[1] - a[1])[0] || ["", 0];
    return value > 0 ? CX_DASHBOARD_MODULE_LABELS_023A[code] || code : "Sin actividad";
  }

  function cxDashboardAlerts023A() {
    const alerts = [];
    const visibleCompanies = state.companies.filter((company) => !isArchivedCompany(company));
    const activeCompanies = visibleCompanies.filter((company) => companyStatus(company) === "active");
    const activities = cxDashboardActivities023A();

    if (!state.health || state.health.ok === false) {
      alerts.push({ level: "danger", title: "API en revision", detail: state.health?.error || "Health no disponible." });
    }

    const withoutOwner = activeCompanies.filter((company) => ownerAccessInfo(state.companyUsers.get(company.id)).level === "danger");
    if (withoutOwner.length) {
      alerts.push({ level: "danger", title: "Empresas sin acceso maestro", detail: `${withoutOwner.length} tenant(s) activos requieren revision de acceso.` });
    }

    const withoutModules = activeCompanies.filter((company) => moduleCodesForCompany(company.id).length === 0);
    if (withoutModules.length) {
      alerts.push({ level: "warn", title: "Empresas sin modulos activos", detail: `${withoutModules.length} tenant(s) activos no tienen modulos visibles.` });
    }

    const idleCompanies = activities.filter((activity) => {
      const company = state.companies.find((item) => item.id === activity.company_id);
      return company && companyStatus(company) === "active" && activity.availableSignals > 0 && activity.totalSignals === 0;
    });
    if (idleCompanies.length) {
      alerts.push({ level: "warn", title: "Empresas activas sin actividad", detail: `${idleCompanies.length} tenant(s) muestreados no tienen registros operativos.` });
    }

    const partialData = activities.filter((activity) => activity.errors?.length).length + state.dashboardActivityErrors.length;
    if (partialData) {
      alerts.push({ level: "warn", title: "Datos operativos parciales", detail: `${partialData} consulta(s) no respondieron o no estan disponibles.` });
    }

    if (!alerts.length) {
      alerts.push({ level: "ok", title: "Sin alertas criticas", detail: "No se detectaron bloqueos SaaS en la muestra actual." });
    }

    return alerts;
  }

  function cxDashboardOverview023A() {
    const activities = cxDashboardActivities023A();
    const activeCompanyIds = new Set(state.companies.filter((company) => companyStatus(company) === "active").map((company) => company.id));
    const withActivity = activities.filter((activity) => activity.totalSignals > 0).length;
    const withoutActivity = activities.filter((activity) => (
      activeCompanyIds.has(activity.company_id)
      && activity.availableSignals > 0
      && activity.totalSignals === 0
    )).length;
    const totalSignals = activities.reduce((sum, activity) => sum + activity.totalSignals, 0);
    const alerts = cxDashboardAlerts023A();

    return {
      activities,
      withActivity,
      withoutActivity,
      totalSignals,
      topModule: cxDashboardTopModule023A(activities),
      alerts,
      probed: activities.length,
      totalVisible: state.companies.filter((company) => !isArchivedCompany(company)).length,
    };
  }

  function cxDashboardSignalPills023A(counts = {}) {
    return Object.entries(CX_DASHBOARD_MODULE_LABELS_023A)
      .map(([code, label]) => `<span class="cx-signal-pill">${escapeHtml(label)} <strong>${escapeHtml(cxDashboardNumber023A(counts[code]))}</strong></span>`)
      .join("");
  }

  function cxDashboardActivityBadge023A(activity) {
    if (!activity || activity.availableSignals === 0) return `<span class="cx-badge cx-badge-warning">Sin datos</span>`;
    if (activity.totalSignals > 0) return `<span class="cx-badge cx-badge-live">Con actividad</span>`;
    return `<span class="cx-badge">Sin actividad</span>`;
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

  async function loadLandingAnalytics025R() {
    try {
      const filters = state.landingFilters || {};
      const params = new URLSearchParams({
        days: filters.days || "30",
        limit: "40",
      });
      if (filters.source) params.set("source", filters.source);
      if (filters.campaign) params.set("campaign", filters.campaign);
      if (filters.device) params.set("device", filters.device);
      state.landingAnalytics = await apiGet(`${API}/landing-analytics/summary?${params.toString()}`);
    } catch (error) {
      state.landingAnalytics = { ok: false, error: error.message };
      state.errors.push(`Landing: ${error.message}`);
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

  const ACCESS_POLICY_SCOPES_026G = [
    ["client", "Panel cliente", "/client"],
    ["mini_panel", "Mini paneles", "/mini-panel"],
    ["ordering_qr", "QR / pedidos / votacion", "/ordenar"],
  ];

  function defaultAccessPolicy026G() {
    return {
      enabled: false,
      current_ip: "",
      scopes: Object.fromEntries(ACCESS_POLICY_SCOPES_026G.map(([code, label]) => [
        code,
        { label, enabled: false, allowed_ips: [] },
      ])),
    };
  }

  function accessPolicyForCompany026G(companyId) {
    const current = state.companyAccessPolicies.get(companyId);
    if (current && !current.loading) {
      const base = defaultAccessPolicy026G();
      const scopes = current.scopes && typeof current.scopes === "object" ? current.scopes : {};
      ACCESS_POLICY_SCOPES_026G.forEach(([code, label]) => {
        const scoped = scopes[code] || {};
        base.scopes[code] = {
          label: scoped.label || label,
          enabled: !!scoped.enabled,
          allowed_ips: Array.isArray(scoped.allowed_ips) ? scoped.allowed_ips : [],
        };
      });
      return { ...base, ...current, scopes: base.scopes };
    }
    return current || defaultAccessPolicy026G();
  }

  async function loadCompanyAccessPolicy026G(companyId, force = false) {
    if (!companyId) return null;
    if (!force && state.companyAccessPolicies.has(companyId)) {
      return state.companyAccessPolicies.get(companyId);
    }
    try {
      const data = await apiGet(`${API}/companies/${companyId}/access-policy`);
      state.companyAccessPolicies.set(companyId, data || defaultAccessPolicy026G());
      return data || defaultAccessPolicy026G();
    } catch (error) {
      const fallback = { ...defaultAccessPolicy026G(), unavailable: true, error: error.message };
      state.companyAccessPolicies.set(companyId, fallback);
      return fallback;
    }
  }

  function accessPolicyIpsText026G(policy, scope) {
    const scoped = policy?.scopes?.[scope] || {};
    return Array.isArray(scoped.allowed_ips) ? scoped.allowed_ips.join("\n") : "";
  }

  function renderCompanyIpAccessPolicy026G(company, policy) {
    const loading = policy?.loading;
    const unavailable = policy?.unavailable;
    const enabled = !!policy?.enabled;
    const currentIp = policy?.current_ip || "No detectada";
    const activeScopes = ACCESS_POLICY_SCOPES_026G.filter(([code]) => policy?.scopes?.[code]?.enabled).length;
    const totalIps = ACCESS_POLICY_SCOPES_026G.reduce((sum, [code]) => (
      sum + (Array.isArray(policy?.scopes?.[code]?.allowed_ips) ? policy.scopes[code].allowed_ips.length : 0)
    ), 0);

    return `
      <section class="cx-panel" style="margin-top:18px">
        <div class="cx-card-head">
          <div>
            <h3>Seguridad por IP</h3>
            <p>Define desde que IP publica se permite abrir el portal cliente, mini paneles y QR de esta empresa.</p>
          </div>
          <span class="cx-badge ${enabled ? "cx-badge-live" : ""}">${enabled ? "Bloqueo activo" : "Sin bloqueo"}</span>
        </div>

        ${loading ? `<div class="cx-empty-state">Cargando politica de accesos...</div>` : ""}
        ${unavailable ? `<div class="cx-alert" style="display:block;margin:12px 0">No se pudo cargar la politica IP: ${escapeHtml(policy.error || "error desconocido")}</div>` : ""}

        <div class="cx-detail-grid" style="margin:14px 0">
          <div class="cx-kv"><span>IP detectada ahora</span><strong>${escapeHtml(currentIp)}</strong></div>
          <div class="cx-kv"><span>Alcances protegidos</span><strong>${activeScopes}</strong></div>
          <div class="cx-kv"><span>IPs/CIDR guardadas</span><strong>${totalIps}</strong></div>
          <div class="cx-kv"><span>Admin V2</span><strong>No se bloquea aqui</strong></div>
        </div>

        <form class="cx-form" id="companyIpAccessPolicyForm026G" data-company-id="${escapeHtml(company.id)}">
          <label class="cx-reset-scope" style="margin:4px 0 10px">
            <input name="enabled" type="checkbox" ${enabled ? "checked" : ""} />
            <span>
              <strong>Activar bloqueo por IP para esta empresa</strong>
              <small>Si esta apagado, las listas quedan guardadas pero no restringen acceso.</small>
            </span>
          </label>

          <div class="cx-detail-grid">
            ${ACCESS_POLICY_SCOPES_026G.map(([code, label, path]) => {
              const scoped = policy?.scopes?.[code] || {};
              return `
                <div class="cx-kv" style="align-items:stretch">
                  <label class="cx-reset-scope" style="margin:0 0 10px">
                    <input name="${escapeHtml(code)}_enabled" type="checkbox" ${scoped.enabled ? "checked" : ""} />
                    <span>
                      <strong>${escapeHtml(label)}</strong>
                      <small>${escapeHtml(path)}</small>
                    </span>
                  </label>
                  <textarea name="${escapeHtml(code)}_ips" rows="4" placeholder="Una IP o rango CIDR por linea. Ej: ${escapeHtml(currentIp)}">${escapeHtml(accessPolicyIpsText026G(policy, code))}</textarea>
                </div>
              `;
            }).join("")}
          </div>

          <div class="cx-alert" style="display:block;margin:14px 0">
            Recomendacion: primero copia la IP detectada, guardala en el alcance correcto y prueba desde otro navegador. No uses esta regla para Admin V2 hasta tener un metodo de recuperacion.
          </div>

          <div class="cx-actions" style="gap:10px;flex-wrap:wrap">
            <button class="cx-btn cx-btn-primary" type="submit">Guardar politica IP</button>
            <button class="cx-btn" type="button" data-copy="${escapeHtml(currentIp)}">Copiar IP actual</button>
          </div>
        </form>
      </section>
    `;
  }

  function ipListFromTextarea026G(form, name) {
    return String(form.get(name) || "")
      .replaceAll(",", "\n")
      .split(/\n+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function saveCompanyAccessPolicy026G(companyId, event) {
    event.preventDefault();
    const form = event.target;
    const data = new FormData(form);
    const scopes = {};
    ACCESS_POLICY_SCOPES_026G.forEach(([code]) => {
      scopes[code] = {
        enabled: data.get(`${code}_enabled`) === "on",
        allowed_ips: ipListFromTextarea026G(data, `${code}_ips`),
      };
    });

    try {
      const policy = await apiPut(`${API}/companies/${companyId}/access-policy`, {
        enabled: data.get("enabled") === "on",
        scopes,
      });
      state.companyAccessPolicies.set(companyId, policy);
      showToast("Politica IP guardada para esta empresa.");
      const company = state.companies.find((c) => c.id === companyId);
      if (company) renderCompanyDetailTab(company);
    } catch (error) {
      showToast(`No se pudo guardar la politica IP: ${error.message}`, "error");
    }
  }

  const SESSION_POLICY_SCOPES_026H = [
    ["client", "Panel cliente", "/client", 2, 20],
    ["mini_panel", "Mini paneles", "/mini-panel", 5, 100],
  ];

  function defaultSessionPolicy026H() {
    return {
      enabled: false,
      mode: "replace_oldest",
      scopes: Object.fromEntries(SESSION_POLICY_SCOPES_026H.map(([code, label, path, defaultMax]) => [
        code,
        { label, path, enabled: false, max_sessions: defaultMax },
      ])),
    };
  }

  function sessionPolicyForCompany026H(companyId) {
    const current = state.companySessionPolicies.get(companyId);
    if (current && !current.loading) {
      const base = defaultSessionPolicy026H();
      const scopes = current.scopes && typeof current.scopes === "object" ? current.scopes : {};
      SESSION_POLICY_SCOPES_026H.forEach(([code, label, path, defaultMax]) => {
        const scoped = scopes[code] || {};
        base.scopes[code] = {
          label: scoped.label || label,
          path,
          enabled: !!scoped.enabled,
          max_sessions: Number(scoped.max_sessions || defaultMax),
        };
      });
      return { ...base, ...current, scopes: base.scopes };
    }
    return current || defaultSessionPolicy026H();
  }

  async function loadCompanySessionPolicy026H(companyId, force = false) {
    if (!companyId) return null;
    if (!force && state.companySessionPolicies.has(companyId)) {
      return state.companySessionPolicies.get(companyId);
    }
    try {
      const data = await apiGet(`${API}/companies/${companyId}/session-policy`);
      state.companySessionPolicies.set(companyId, data || defaultSessionPolicy026H());
      return data || defaultSessionPolicy026H();
    } catch (error) {
      const fallback = { ...defaultSessionPolicy026H(), unavailable: true, error: error.message };
      state.companySessionPolicies.set(companyId, fallback);
      return fallback;
    }
  }

  async function loadCompanyAccessSessions026H(companyId, force = false) {
    if (!companyId) return null;
    if (!force && state.companyAccessSessions.has(companyId)) {
      return state.companyAccessSessions.get(companyId);
    }
    try {
      const data = await apiGet(`${API}/companies/${companyId}/access-sessions?include_closed=true`);
      state.companyAccessSessions.set(companyId, data || { sessions: [] });
      return data || { sessions: [] };
    } catch (error) {
      const fallback = { sessions: [], unavailable: true, error: error.message };
      state.companyAccessSessions.set(companyId, fallback);
      return fallback;
    }
  }

  async function loadAdminV2Sessions026H(force = false) {
    if (!force && state.adminV2Sessions) return state.adminV2Sessions;
    try {
      state.adminV2Sessions = await apiGet("/admin-v2/api/sessions");
      return state.adminV2Sessions;
    } catch (error) {
      state.adminV2Sessions = { sessions: [], unavailable: true, error: error.message };
      return state.adminV2Sessions;
    }
  }

  function sessionDate026H(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
  }

  function sessionStatusBadge026H(status) {
    const clean = String(status || "").toLowerCase();
    if (clean === "active") return `<span class="cx-badge cx-badge-live">Activa</span>`;
    return `<span class="cx-badge cx-badge-danger">Cerrada</span>`;
  }

  function sessionCountByScope026H(sessions, scope) {
    return (sessions || []).filter((item) => (
      String(item.scope || "") === scope
      && String(item.status || "").toLowerCase() === "active"
    )).length;
  }

  function renderSessionRows026H(companyId, sessions) {
    const rows = (sessions || []).slice(0, 24);
    if (!rows.length) {
      return `<div class="cx-empty-state">No hay sesiones registradas todavia.</div>`;
    }
    return `
      <div class="cx-session-list-026h">
        ${rows.map((item) => {
          const active = String(item.status || "").toLowerCase() === "active";
          return `
            <article class="cx-session-row-026h">
              <div>
                <strong>${escapeHtml(item.subject_label || item.scope || "Sesion")}</strong>
                <small>${escapeHtml(item.scope || "")} · ${escapeHtml(item.ip_address || "sin IP")} · ${escapeHtml(sessionDate026H(item.last_seen_at))}</small>
              </div>
              <div class="cx-session-row-actions-026h">
                ${sessionStatusBadge026H(item.status)}
                <button class="cx-btn cx-btn-small" type="button" data-close-access-session="${escapeHtml(item.session_key)}" data-company-id="${escapeHtml(companyId)}" ${active ? "" : "disabled"}>Cerrar</button>
              </div>
            </article>
          `;
        }).join("")}
      </div>
    `;
  }

  function renderCompanySessionAccess026H(company, policy, sessionPayload) {
    const loading = policy?.loading || sessionPayload?.loading;
    const sessions = Array.isArray(sessionPayload?.sessions) ? sessionPayload.sessions : [];
    const activeTotal = sessions.filter((item) => String(item.status || "").toLowerCase() === "active").length;
    const enabled = !!policy?.enabled;
    const mode = policy?.mode || "replace_oldest";

    return `
      <section class="cx-panel" style="margin-top:18px">
        <div class="cx-card-head">
          <div>
            <h3>Limite de sesiones por panel</h3>
            <p>Controla cuantas sesiones activas puede tener esta empresa en portal cliente y mini paneles.</p>
          </div>
          <span class="cx-badge ${enabled ? "cx-badge-live" : ""}">${enabled ? "Limite activo" : "Sin limite"}</span>
        </div>

        ${loading ? `<div class="cx-empty-state">Cargando sesiones...</div>` : ""}
        ${policy?.unavailable ? `<div class="cx-alert" style="display:block;margin:12px 0">No se pudo cargar politica de sesiones: ${escapeHtml(policy.error || "error")}</div>` : ""}
        ${sessionPayload?.unavailable ? `<div class="cx-alert" style="display:block;margin:12px 0">No se pudo cargar sesiones: ${escapeHtml(sessionPayload.error || "error")}</div>` : ""}

        <div class="cx-detail-grid" style="margin:14px 0">
          <div class="cx-kv"><span>Sesiones activas</span><strong>${escapeHtml(activeTotal)}</strong></div>
          <div class="cx-kv"><span>Modo al exceder</span><strong>${mode === "reject_new" ? "Rechazar nuevo login" : "Cerrar la mas antigua"}</strong></div>
          ${SESSION_POLICY_SCOPES_026H.map(([code, label]) => `
            <div class="cx-kv"><span>${escapeHtml(label)}</span><strong>${escapeHtml(sessionCountByScope026H(sessions, code))} abiertas</strong></div>
          `).join("")}
        </div>

        <form class="cx-form" id="companySessionPolicyForm026H" data-company-id="${escapeHtml(company.id)}">
          <label class="cx-reset-scope" style="margin:4px 0 10px">
            <input name="enabled" type="checkbox" ${enabled ? "checked" : ""} />
            <span>
              <strong>Activar limite de sesiones</strong>
              <small>Si esta apagado, solo se monitorean sesiones sin bloquear nuevos ingresos.</small>
            </span>
          </label>
          <label>Cuando se supere el limite
            <select name="mode">
              <option value="replace_oldest" ${mode === "replace_oldest" ? "selected" : ""}>Cerrar automaticamente la sesion mas antigua</option>
              <option value="reject_new" ${mode === "reject_new" ? "selected" : ""}>Rechazar el nuevo ingreso</option>
            </select>
          </label>
          <div class="cx-session-scope-grid-026h">
            ${SESSION_POLICY_SCOPES_026H.map(([code, label, path, defaultMax, max]) => {
              const scoped = policy?.scopes?.[code] || {};
              return `
                <div class="cx-kv">
                  <label class="cx-reset-scope" style="margin:0 0 10px">
                    <input name="${escapeHtml(code)}_enabled" type="checkbox" ${scoped.enabled ? "checked" : ""} />
                    <span>
                      <strong>${escapeHtml(label)}</strong>
                      <small>${escapeHtml(path)}</small>
                    </span>
                  </label>
                  <label>Maximo de sesiones
                    <input name="${escapeHtml(code)}_max" type="number" min="1" max="${escapeHtml(max)}" value="${escapeHtml(scoped.max_sessions || defaultMax)}" />
                  </label>
                </div>
              `;
            }).join("")}
          </div>
          <div class="cx-actions" style="gap:10px;flex-wrap:wrap">
            <button class="cx-btn cx-btn-primary" type="submit">Guardar limites</button>
            <button class="cx-btn" type="button" data-refresh-access-sessions="${escapeHtml(company.id)}">Actualizar sesiones</button>
            <button class="cx-btn cx-btn-danger" type="button" data-close-company-sessions="${escapeHtml(company.id)}">Cerrar todas</button>
          </div>
        </form>

        <div class="cx-session-panel-026h">
          <div class="cx-access-section-head-026b">
            <div>
              <span class="cx-kicker">Sesiones</span>
              <h3>Actividad reciente</h3>
            </div>
          </div>
          ${renderSessionRows026H(company.id, sessions)}
        </div>
      </section>
    `;
  }

  async function saveCompanySessionPolicy026H(companyId, event) {
    event.preventDefault();
    const data = new FormData(event.target);
    const scopes = {};
    SESSION_POLICY_SCOPES_026H.forEach(([code]) => {
      scopes[code] = {
        enabled: data.get(`${code}_enabled`) === "on",
        max_sessions: Number(data.get(`${code}_max`) || 1),
      };
    });

    try {
      const policy = await apiPut(`${API}/companies/${companyId}/session-policy`, {
        enabled: data.get("enabled") === "on",
        mode: String(data.get("mode") || "replace_oldest"),
        scopes,
      });
      state.companySessionPolicies.set(companyId, policy);
      await loadCompanyAccessSessions026H(companyId, true);
      showToast("Limites de sesiones guardados.");
      const company = state.companies.find((c) => c.id === companyId);
      if (company) renderCompanyDetailTab(company);
    } catch (error) {
      showToast(`No se pudo guardar limites de sesiones: ${error.message}`, "error");
    }
  }

  async function refreshCompanySessions026H(companyId) {
    await loadCompanyAccessSessions026H(companyId, true);
    const company = state.companies.find((c) => c.id === companyId);
    if (company && state.selectedCompanyId === companyId && state.activeDetailTab === "accesos") {
      renderCompanyDetailTab(company);
    }
    showToast("Sesiones actualizadas.");
  }

  async function closeCompanySession026H(companyId, sessionKey) {
    await apiPost(`${API}/companies/${companyId}/access-sessions/${sessionKey}/close`, {});
    await loadCompanyAccessSessions026H(companyId, true);
    const company = state.companies.find((c) => c.id === companyId);
    if (company && state.selectedCompanyId === companyId && state.activeDetailTab === "accesos") {
      renderCompanyDetailTab(company);
    }
    showToast("Sesion cerrada.");
  }

  async function closeAllCompanySessions026H(companyId) {
    if (!window.confirm("Cerrar todas las sesiones activas de esta empresa?")) return;
    await apiPost(`${API}/companies/${companyId}/access-sessions/close`, {});
    await loadCompanyAccessSessions026H(companyId, true);
    const company = state.companies.find((c) => c.id === companyId);
    if (company && state.selectedCompanyId === companyId && state.activeDetailTab === "accesos") {
      renderCompanyDetailTab(company);
    }
    showToast("Sesiones de la empresa cerradas.");
  }

  function renderAdminV2SessionMonitor026H() {
    const payload = state.adminV2Sessions || { loading: true, sessions: [] };
    const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
    const active = sessions.filter((item) => String(item.status || "").toLowerCase() === "active").length;
    return `
      <section class="cx-access-section-026b">
        <div class="cx-access-section-head-026b">
          <div>
            <span class="cx-kicker">Admin V2</span>
            <h3>Control de sesiones de la consola</h3>
            <p class="cx-muted">Aqui ves y cierras accesos abiertos a la super consola.</p>
          </div>
          <button class="cx-btn cx-btn-small" type="button" data-refresh-admin-v2-sessions>Actualizar</button>
        </div>
        <div class="cx-access-summary-026b">
          <div class="cx-kv"><span>Sesiones activas</span><strong>${escapeHtml(active)}</strong></div>
          <div class="cx-kv"><span>Actual</span><strong>${escapeHtml(truncate(payload.current_session || "-", 14))}</strong></div>
          <div class="cx-kv"><span>Historial mostrado</span><strong>${escapeHtml(sessions.length)}</strong></div>
          <div class="cx-kv"><span>Estado</span><strong>${payload.unavailable ? "Error" : "OK"}</strong></div>
        </div>
        ${payload.unavailable ? `<div class="cx-alert" style="display:block;margin:10px 0">No se pudo cargar sesiones V2: ${escapeHtml(payload.error || "error")}</div>` : ""}
        ${sessions.length ? `
          <div class="cx-session-list-026h">
            ${sessions.slice(0, 12).map((item) => {
              const isCurrent = item.session_key === payload.current_session;
              const activeRow = String(item.status || "").toLowerCase() === "active";
              return `
                <article class="cx-session-row-026h">
                  <div>
                    <strong>${escapeHtml(isCurrent ? "Esta consola" : (item.subject_label || "Admin V2"))}</strong>
                    <small>${escapeHtml(item.ip_address || "sin IP")} · ${escapeHtml(sessionDate026H(item.last_seen_at))} · ${escapeHtml(truncate(item.session_key, 12))}</small>
                  </div>
                  <div class="cx-session-row-actions-026h">
                    ${sessionStatusBadge026H(item.status)}
                    <button class="cx-btn cx-btn-small" type="button" data-close-admin-v2-session="${escapeHtml(item.session_key)}" ${activeRow ? "" : "disabled"}>${isCurrent ? "Cerrar esta" : "Cerrar"}</button>
                  </div>
                </article>
              `;
            }).join("")}
          </div>
        ` : `<div class="cx-empty-state">No hay sesiones V2 registradas.</div>`}
      </section>
    `;
  }

  async function refreshAdminV2Sessions026H() {
    await loadAdminV2Sessions026H(true);
    if (state.activeView === "access") renderAccess();
    showToast("Sesiones V2 actualizadas.");
  }

  async function closeAdminV2Session026H(sessionKey) {
    const closesCurrent = sessionKey === state.adminV2Sessions?.current_session;
    await apiPost(`/admin-v2/api/sessions/${sessionKey}/close`, {});
    if (closesCurrent) {
      showToast("Sesion V2 cerrada.");
      window.location.href = "/admin-v2/login";
      return;
    }
    await loadAdminV2Sessions026H(true);
    if (state.activeView === "access") renderAccess();
    showToast("Sesion V2 cerrada.");
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
    const accessPolicy = accessPolicyForCompany026G(company.id);
    const sessionPolicy = sessionPolicyForCompany026H(company.id);
    const accessSessions = state.companyAccessSessions.get(company.id) || { sessions: [] };
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

      ${renderCompanyIpAccessPolicy026G(company, accessPolicy)}
      ${renderCompanySessionAccess026H(company, sessionPolicy, accessSessions)}

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

  const CX_OPERATIONAL_RESET_SCOPES = [
    { code: "commercial", label: "Comercial", detail: "Ventas, facturas, cortes, cotizaciones y notas." },
    { code: "references", label: "Referencias", detail: "Catalogo, sesiones y cierres de produccion." },
    { code: "workforce", label: "Personal y bot", detail: "Personal, marcaciones, sesiones GPS y datos capturados por bot." },
    { code: "payroll", label: "Nomina", detail: "Periodos, items y resultados de nomina." },
    { code: "inventory", label: "Inventario", detail: "Inventario, materiales, solicitudes y operacion de campo." },
  ];

  function renderCompanyOperationalResetPanel(company) {
    const preview = state.companyResetPreviews.get(company.id);
    const expectedText = `RESET ${company.slug}`;
    const busy = state.companyResetBusy;

    return `
      <section class="cx-reset-panel" data-company-reset-form="${escapeHtml(company.id)}">
        <div class="cx-reset-head">
          <div>
            <span class="cx-kicker">Zona critica</span>
            <h3>Reset operativo por empresa</h3>
            <p>Elimina datos incorporados al tenant sin borrar el software, la empresa, modulos, paquete, branding ni accesos maestros.</p>
          </div>
          <span class="cx-badge cx-badge-danger">Confirmacion requerida</span>
        </div>

        <div class="cx-reset-preserved">
          <strong>Se conserva:</strong>
          <span>empresa</span>
          <span>modulos</span>
          <span>paquetes</span>
          <span>branding</span>
          <span>CRM layout</span>
          <span>acceso maestro</span>
          <span>bot configurado</span>
        </div>

        <div class="cx-reset-scope-grid">
          ${CX_OPERATIONAL_RESET_SCOPES.map((scope) => `
            <label class="cx-reset-scope">
              <input type="checkbox" data-reset-scope="${escapeHtml(scope.code)}" checked />
              <span>
                <strong>${escapeHtml(scope.label)}</strong>
                <small>${escapeHtml(scope.detail)}</small>
              </span>
            </label>
          `).join("")}
        </div>

        <div class="cx-reset-confirm-grid">
          <label>Slug exacto
            <input data-reset-confirm-slug type="text" autocomplete="off" placeholder="${escapeHtml(company.slug)}" />
          </label>
          <label>Frase exacta
            <input data-reset-confirm-text type="text" autocomplete="off" placeholder="${escapeHtml(expectedText)}" />
          </label>
        </div>

        <div class="cx-actions cx-reset-actions">
          <button class="cx-btn" data-reset-dry-run="${escapeHtml(company.id)}" type="button" ${busy ? "disabled" : ""}>Simular reset</button>
          <button class="cx-btn cx-btn-danger" data-reset-execute="${escapeHtml(company.id)}" type="button" ${busy ? "disabled" : ""}>Ejecutar reset operativo</button>
        </div>
        <small class="cx-reset-note">Ejecuta primero la simulacion. La ejecucion real exige slug y frase exacta: ${escapeHtml(expectedText)}</small>

        <div class="cx-reset-result">
          ${renderCompanyOperationalResetResult(preview)}
        </div>
      </section>
    `;
  }

  function renderCompanyOperationalResetResult(result) {
    if (!result) {
      return `
        <div class="cx-empty-state">
          Aun no hay simulacion. CLONEXA revisara las tablas operativas disponibles y mostrara cuantos registros se afectarian.
        </div>
      `;
    }

    const tables = Array.isArray(result.tables) ? result.tables : [];
    const rows = tables
      .filter((item) => item.available || Number(item.rows || 0) > 0)
      .map((item) => `
        <tr>
          <td>${escapeHtml(item.scope_label || item.scope || "-")}</td>
          <td>${escapeHtml(item.label || item.table || "-")}</td>
          <td><code>${escapeHtml(item.table || "-")}</code></td>
          <td>${item.available ? `<span class="cx-badge">Disponible</span>` : `<span class="cx-badge cx-badge-warning">No existe</span>`}</td>
          <td><strong>${escapeHtml(item.rows ?? 0)}</strong></td>
        </tr>
      `).join("");

    const preserved = Array.isArray(result.preserved) ? result.preserved : [];
    return `
      <div class="cx-reset-summary ${result.executed ? "is-executed" : ""}">
        <div>
          <span>${result.executed ? "Reset ejecutado" : "Simulacion lista"}</span>
          <strong>${escapeHtml(result.total_rows ?? 0)} registros</strong>
        </div>
        <small>${result.executed ? "Datos operativos eliminados segun alcance." : "Nada se ha eliminado todavia."}</small>
      </div>
      <div class="cx-reset-table-wrap">
        <table class="cx-table cx-reset-table">
          <thead>
            <tr>
              <th>Alcance</th>
              <th>Dato</th>
              <th>Tabla</th>
              <th>Estado</th>
              <th>Registros</th>
            </tr>
          </thead>
          <tbody>
            ${rows || `<tr><td colspan="5">No hay registros operativos detectados para el alcance seleccionado.</td></tr>`}
          </tbody>
        </table>
      </div>
      <div class="cx-reset-preserved compact">
        <strong>Protegido:</strong>
        ${preserved.slice(0, 10).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
    `;
  }

  function selectedOperationalResetScopes(container) {
    return Array.from(container.querySelectorAll("[data-reset-scope]:checked"))
      .map((input) => input.dataset.resetScope)
      .filter(Boolean);
  }

  async function runCompanyOperationalReset(companyId, execute = false) {
    const company = state.companies.find((item) => item.id === companyId);
    const container = document.querySelector(`[data-company-reset-form="${companyId}"]`);
    if (!company || !container) return;

    const scopes = selectedOperationalResetScopes(container);
    if (!scopes.length) {
      showToast("Selecciona al menos un alcance para el reset.", "error");
      return;
    }

    const confirmSlug = String(container.querySelector("[data-reset-confirm-slug]")?.value || "").trim();
    const confirmText = String(container.querySelector("[data-reset-confirm-text]")?.value || "").trim();
    const expectedText = `RESET ${company.slug}`;

    if (execute) {
      if (confirmSlug !== company.slug || confirmText !== expectedText) {
        showToast(`Confirmacion invalida. Escribe ${expectedText}.`, "error");
        return;
      }

      const accepted = window.confirm(`Vas a borrar datos operativos de ${company.name}. La empresa, modulos, accesos y branding se conservan. Continuar?`);
      if (!accepted) return;
    }

    state.companyResetBusy = true;
    renderCompanyDetailTab(company);

    try {
      const result = await apiPost(`${API}/companies/${encodeURIComponent(companyId)}/operational-reset`, {
        dry_run: !execute,
        scopes,
        confirm_slug: confirmSlug,
        confirm_text: confirmText,
      });
      state.companyResetPreviews.set(companyId, result);
      showToast(execute ? "Reset operativo ejecutado." : "Simulacion de reset lista.");
      if (execute) {
        await loadAdminDashboard();
        state.selectedCompanyId = companyId;
        state.activeDetailTab = "reset";
      } else {
        renderCompanyDetailTab(company);
      }
    } catch (error) {
      showToast(`No se pudo procesar el reset operativo: ${error.message}`, "error");
    } finally {
      state.companyResetBusy = false;
      const current = state.companies.find((item) => item.id === companyId);
      if (current && state.selectedCompanyId === companyId && state.activeDetailTab === "reset") {
        renderCompanyDetailTab(current);
      }
    }
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
    state.errors = [];

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
      loadLandingAnalytics025R(),
    ];

    await Promise.all(tasks);

    await Promise.all(
      state.companies.map((company) => loadCompanyModules(company.id).catch(() => []))
    );

    await Promise.all(
      state.companies.map((company) => loadCompanyUsers(company.id).catch(() => []))
    );

    await loadDashboardActivity023A().catch((error) => {
      state.dashboardActivityErrors.push(error.message || "No se pudo cargar actividad SaaS");
    });

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
    const overview = cxDashboardOverview023A();
    const apiOk = state.health && state.health.ok !== false;
    setText("metricActiveUse", overview.withActivity);
    setText("metricActiveUseHint", `Muestra ${overview.probed}/${overview.totalVisible || 0} tenants`);
    setText("metricIdleCompanies", overview.probed ? overview.withoutActivity : "Sin datos");
    setText("metricRecentSignals", overview.totalSignals);
    setText("metricTopModule", overview.topModule);
    setText("metricSaasAlerts", overview.alerts.filter((item) => item.level !== "ok").length);
    setText("metricApi", state.health && state.health.ok !== false ? "LIVE" : "OFFLINE");
    setText("metricApiHint", apiOk ? "Health operativo" : "Revisar health");
    setText("lastRefreshLabel", state.lastRefresh ? `Ultima actualizacion ${state.lastRefresh}` : "Sin actualizar");
  }

  function cxLandingNumber025S(value) {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function cxLandingTopLabel025S(rows = [], emptyLabel = "Sin datos") {
    const first = rows[0] || {};
    return first.label || emptyLabel;
  }

  function cxLandingSelectOptions025S(selector, rows = [], selectedValue = "", emptyLabel = "Todos") {
    const select = el(selector);
    if (!select) return;
    const values = new Set();
    const options = [`<option value="">${escapeHtml(emptyLabel)}</option>`];
    rows.forEach((item) => {
      const label = String(item.label || "");
      if (!label || values.has(label)) return;
      values.add(label);
      options.push(`<option value="${escapeHtml(label)}">${escapeHtml(label)} (${escapeHtml(item.total || 0)})</option>`);
    });
    if (selectedValue && !values.has(selectedValue)) {
      options.push(`<option value="${escapeHtml(selectedValue)}">${escapeHtml(selectedValue)}</option>`);
    }
    select.innerHTML = options.join("");
    select.value = selectedValue || "";
  }

  function cxLandingSyncFilters025S(analytics = {}) {
    const filters = state.landingFilters || {};
    const days = el("#landingDays025S");
    if (days) days.value = filters.days || String(analytics.days || 30);
    const options = analytics.options || {};
    cxLandingSelectOptions025S("#landingSource025S", options.sources || analytics.sources || [], filters.source || "", "Todas");
    cxLandingSelectOptions025S("#landingCampaign025S", options.campaigns || analytics.campaigns || [], filters.campaign || "", "Todas");
    cxLandingSelectOptions025S("#landingDevice025S", options.devices || analytics.devices || [], filters.device || "", "Todos");
  }

  function cxLandingGroup025R(rows = [], config = {}) {
    const max = Math.max(1, ...rows.map((item) => Number(item.total || 0)));
    return rows.length
      ? rows.map((item) => {
        const total = Number(item.total || 0);
        const width = Math.max(4, Math.round((total / max) * 100));
        const share = config.base ? Math.round((total / Math.max(1, config.base)) * 100) : 0;
        return `
          <div class="cx-landing-bar-row-025S">
            <div>
              <strong>${escapeHtml(item.label || "sin dato")}</strong>
              <small>${escapeHtml(total)} visita(s)${share ? ` - ${escapeHtml(share)}%` : ""}</small>
            </div>
            <div class="cx-progress"><span style="width:${escapeHtml(width)}%"></span></div>
          </div>
        `;
      }).join("")
      : `<div class="cx-empty-state">Aun no hay datos capturados.</div>`;
  }

  function renderLandingAnalytics025R() {
    const analytics = state.landingAnalytics || {};
    const totals = analytics.totals || {};
    const totalVisits = cxLandingNumber025S(totals.total_visits);
    const sourcesRows = analytics.sources || [];
    const campaignsRows = analytics.campaigns || [];
    const devicesRows = analytics.devices || [];
    cxLandingSyncFilters025S(analytics);
    const metrics = el("#landingMetrics025R");
    if (metrics) {
      metrics.innerHTML = analytics.ok === false
        ? `<article class="cx-metric-card"><span>Estado</span><strong>Error</strong><small>${escapeHtml(analytics.error || "No disponible")}</small></article>`
        : `
          <article class="cx-metric-card"><span>Visitas</span><strong>${escapeHtml(totalVisits)}</strong><small>Ultimos ${escapeHtml(analytics.days || 30)} dias</small></article>
          <article class="cx-metric-card"><span>Visitantes</span><strong>${escapeHtml(totals.unique_visitors || 0)}</strong><small>IDs unicos</small></article>
          <article class="cx-metric-card"><span>Sesiones</span><strong>${escapeHtml(totals.sessions || 0)}</strong><small>Sesiones detectadas</small></article>
          <article class="cx-metric-card"><span>Ultimas 24h</span><strong>${escapeHtml(totals.last_24h || 0)}</strong><small>Actividad reciente</small></article>
          <article class="cx-metric-card"><span>Fuente top</span><strong>${escapeHtml(cxLandingTopLabel025S(sourcesRows))}</strong><small>${escapeHtml(sourcesRows[0]?.total || 0)} visita(s)</small></article>
          <article class="cx-metric-card"><span>Dispositivo top</span><strong>${escapeHtml(cxLandingTopLabel025S(devicesRows))}</strong><small>${escapeHtml(devicesRows[0]?.total || 0)} visita(s)</small></article>
        `;
    }

    const daily = el("#landingDaily025S");
    if (daily) daily.innerHTML = analytics.ok === false ? `<div class="cx-empty-state">No disponible.</div>` : cxLandingGroup025R(analytics.daily || [], { base: totalVisits });

    const sources = el("#landingSources025R");
    if (sources) sources.innerHTML = analytics.ok === false ? `<div class="cx-empty-state">No disponible.</div>` : cxLandingGroup025R(sourcesRows, { base: totalVisits });

    const campaigns = el("#landingCampaigns025R");
    if (campaigns) campaigns.innerHTML = analytics.ok === false ? `<div class="cx-empty-state">No disponible.</div>` : cxLandingGroup025R(campaignsRows, { base: totalVisits });

    const devices = el("#landingDevices025S");
    if (devices) devices.innerHTML = analytics.ok === false ? `<div class="cx-empty-state">No disponible.</div>` : cxLandingGroup025R(devicesRows, { base: totalVisits });

    const paths = el("#landingPaths025S");
    if (paths) paths.innerHTML = analytics.ok === false ? `<div class="cx-empty-state">No disponible.</div>` : cxLandingGroup025R(analytics.paths || [], { base: totalVisits });

    const recent = el("#landingRecent025R");
    if (recent) {
      const rows = analytics.recent || [];
      recent.innerHTML = rows.length
        ? rows.map((item) => `
          <tr>
            <td>${escapeHtml(item.created_at || "")}</td>
            <td><strong>${escapeHtml(item.source || "directo")}</strong><br><small>${escapeHtml(item.referrer_domain || item.medium || "")}</small></td>
            <td>${escapeHtml(item.campaign || "sin campana")}</td>
            <td>${escapeHtml(item.path || "/")}</td>
            <td>${escapeHtml(item.device || "sin dato")}<br><small>${escapeHtml(item.viewport || "")}</small></td>
            <td>${escapeHtml(item.language || "sin dato")}<br><small>${escapeHtml(item.timezone || "")}</small></td>
          </tr>
        `).join("")
        : `<tr><td colspan="6">Aun no hay visitas capturadas.</td></tr>`;
    }
  }

  function renderDashboard() {
    const overview = cxDashboardOverview023A();
    const summary = el("#dashboardSummary");
    if (summary) {
      const rows = cxDashboardProbeCompanies023A()
        .map((company) => ({
          company,
          activity: state.companyActivity.get(company.id) || {
            company_id: company.id,
            counts: {},
            totalSignals: 0,
            availableSignals: 0,
            topSignal: "",
            latestAt: cxDashboardTimestamp023A(company.updated_at, company.created_at),
            latestLabel: cxDashboardDateLabel023A(cxDashboardTimestamp023A(company.updated_at, company.created_at)),
            errors: [],
          },
        }))
        .sort((a, b) => (b.activity.totalSignals - a.activity.totalSignals) || (b.activity.latestAt - a.activity.latestAt));

      summary.innerHTML = rows.length
        ? `
          <div class="cx-dashboard-table-wrap">
            <table class="cx-table cx-dashboard-table">
              <thead>
                <tr>
                  <th>Empresa</th>
                  <th>Estado</th>
                  <th>Ultima senal</th>
                  <th>Modulos</th>
                  <th>Uso detectado</th>
                  <th>Alertas</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                ${rows.map(({ company, activity }) => {
                  const moduleCount = moduleCodesForCompany(company.id).length;
                  const ownerInfo = ownerAccessInfo(state.companyUsers.get(company.id));
                  const rowAlerts = [];
                  if (ownerInfo.level === "danger") rowAlerts.push("Sin acceso maestro");
                  if (moduleCount === 0) rowAlerts.push("Sin modulos");
                  if (activity.availableSignals > 0 && activity.totalSignals === 0) rowAlerts.push("Sin actividad");
                  if (activity.errors?.length) rowAlerts.push("Datos parciales");
                  const topSignal = activity.topSignal ? CX_DASHBOARD_MODULE_LABELS_023A[activity.topSignal] : "Sin actividad";
                  return `
                    <tr>
                      <td><strong>${escapeHtml(company.name)}</strong><br><small>${escapeHtml(company.slug || truncate(company.id, 14))}</small></td>
                      <td>${statusBadge(company.status)}<br><small>Acceso: ${ownerAccessBadge(state.companyUsers.get(company.id))}</small></td>
                      <td>${escapeHtml(activity.latestLabel || "Sin datos")}</td>
                      <td><strong>${escapeHtml(moduleCount)}</strong><br><small>${escapeHtml(packageForCompany(company))}</small></td>
                      <td>
                        ${cxDashboardActivityBadge023A(activity)}
                        <div class="cx-signal-grid">${cxDashboardSignalPills023A(activity.counts)}</div>
                        <small>Top: ${escapeHtml(topSignal)}</small>
                      </td>
                      <td>${rowAlerts.length ? rowAlerts.map((item) => `<span class="cx-badge cx-badge-warning">${escapeHtml(item)}</span>`).join(" ") : `<span class="cx-badge cx-badge-live">OK</span>`}</td>
                      <td>
                        <div class="cx-actions">
                          <button class="cx-btn cx-btn-small" data-open-client="${escapeHtml(company.id)}" type="button">Ver panel</button>
                          <button class="cx-btn cx-btn-small" data-select-company="${escapeHtml(company.id)}" type="button">Gestionar</button>
                          <button class="cx-btn cx-btn-small" data-copy="${escapeHtml(cxDashboardClientUrl023A(company))}" type="button">Copiar URL</button>
                        </div>
                      </td>
                    </tr>
                  `;
                }).join("")}
              </tbody>
            </table>
          </div>
          <small class="cx-dashboard-note">Lectura defensiva de hasta ${escapeHtml(CX_DASHBOARD_ACTIVITY_LIMIT_023A)} empresas visibles. Si un endpoint falla, el dashboard conserva el resto de datos.</small>
        `
        : `<div class="cx-empty-state">No hay empresas visibles para analizar.</div>`;
    }

    const list = el("#dashboardCompanies");
    if (list) {
      const rows = [...filteredCompanies()]
        .filter((company) => !isArchivedCompany(company))
        .sort((a, b) => {
          const activityA = state.companyActivity.get(a.id);
          const activityB = state.companyActivity.get(b.id);
          return cxDashboardTimestamp023A(activityB?.latestAt, b.updated_at, b.created_at) - cxDashboardTimestamp023A(activityA?.latestAt, a.updated_at, a.created_at);
        })
        .slice(0, 6);
      list.innerHTML = rows.length
        ? rows.map((company) => {
          const activity = state.companyActivity.get(company.id);
          const moduleCount = moduleCodesForCompany(company.id).length;
          return `
          <button class="cx-mini-card cx-dashboard-company-card" type="button" data-select-company="${escapeHtml(company.id)}">
            <strong>${escapeHtml(company.name)}</strong>
            <span>${escapeHtml(company.slug || "sin-slug")} - ${escapeHtml(company.status)}</span>
            <small>${escapeHtml(activity?.latestLabel || cxDashboardDateLabel023A(cxDashboardTimestamp023A(company.updated_at, company.created_at)))}</small>
            <small>${escapeHtml(moduleCount)} modulos activos - ${escapeHtml(activity?.totalSignals || 0)} senales</small>
          </button>
        `;
        }).join("")
        : `<div class="cx-empty-state">No hay empresas cargadas.</div>`;
    }

    const alerts = el("#dashboardAlerts");
    if (alerts) {
      alerts.innerHTML = overview.alerts.map((item) => {
        const cls = item.level === "danger" ? "cx-badge-danger" : item.level === "warn" ? "cx-badge-warning" : "cx-badge-live";
        return `
          <div class="cx-dashboard-alert-item">
            <span class="cx-badge ${cls}">${escapeHtml(item.level === "ok" ? "OK" : item.level === "danger" ? "Critica" : "Revision")}</span>
            <div>
              <strong>${escapeHtml(item.title)}</strong>
              <small>${escapeHtml(item.detail)}</small>
            </div>
          </div>
        `;
      }).join("");
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
      const activity = state.companyActivity.get(company.id);
      const selected = state.selectedCompanyId === company.id;
      return `
        <tr class="${selected ? "is-selected" : ""}">
          <td>
            <div class="cx-company-cell">
              <strong>${escapeHtml(company.name)}</strong>
              <small>${owner ? escapeHtml(owner.email) : "Sin acceso maestro"}</small>
            </div>
          </td>
          <td><code>${escapeHtml(company.slug || "-")}</code></td>
          <td>${statusBadge(company.status)}<br><small>Acceso Maestro: ${ownerAccessBadge(users)}</small></td>
          <td>${escapeHtml(company.plan || "Ã¢â‚¬â€")}</td>
          <td>${escapeHtml(company.timezone || "Ã¢â‚¬â€")}</td>
          <td><span class="cx-badge cx-badge-primary">${escapeHtml(pkg)}</span></td>
          <td>
            <strong>${escapeHtml(moduleCount)}</strong>
            <small>${activity ? `Actividad: ${escapeHtml(activity.totalSignals || 0)}` : "Actividad: sin datos"}</small>
          </td>
          <td>
            <div class="cx-company-row-actions">
              <button class="cx-btn cx-btn-primary cx-btn-small" data-select-company="${escapeHtml(company.id)}" type="button">Gestionar</button>
              ${archived ? `<span class="cx-badge cx-badge-danger">Archivada</span>` : `<span class="cx-badge">Command Center</span>`}
            </div>
            ${ownerInfo.status === "MULTIPLE" ? `<br><small>Hay multiples accesos maestros.</small>` : ""}
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

  /* CLONEXA_025N_QR_CONFIG_V2_START */
  const CX_COMPANY_QR_COUNT_OPTIONS_025N = [10, 15, 20, 30, 40, 50, 70, 100, 120, 150, 200, 300, 500];
  const CX_COMPANY_QR_MODES_025N = [
    { code: "hospitality", label: "Mesas / bar", includeBar: true },
    { code: "voting", label: "Votacion / participantes", includeBar: false },
    { code: "generic", label: "Generico", includeBar: false },
  ];

  function cxQrNorm025N(value = "") {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function cxIsQrModuleCode025N(code = "") {
    return ["qr", "mesa_qr", "mesas_qr", "qr_mesas", "hospitality_qr", "voting_qr"].includes(cxQrNorm025N(code));
  }

  function cxFindCompanyQrModule025N(companyId, enabledOnly = true) {
    const rows = safeArray(state.companyModules.get(companyId)).map(normalizeModule);
    return rows.find((row) => cxIsQrModuleCode025N(row.code) && (!enabledOnly || row.enabled !== false)) || null;
  }

  function cxCleanQrBaseUrl025N(value = "") {
    let text = String(value || "").trim();
    if (!text) return window.location.origin || "";
    text = text.replace(/\/+$/, "");
    text = text.replace(/\/ordenar$/i, "");
    return text || window.location.origin || "";
  }

  function cxClampQrOption025N(value, fallback = 10) {
    const number = Math.round(Number(value || fallback));
    if (!Number.isFinite(number)) return fallback;
    return Math.min(500, Math.max(1, number));
  }

  function cxNormalizeCompanyQrSettings025N(moduleRow = {}) {
    const source = moduleRow?.settings && typeof moduleRow.settings === "object" ? moduleRow.settings : {};
    const raw = source.qr_config && typeof source.qr_config === "object"
      ? source.qr_config
      : (source.hospitality_qr && typeof source.hospitality_qr === "object" ? source.hospitality_qr : source);
    const mode = CX_COMPANY_QR_MODES_025N.some((item) => item.code === raw.mode) ? raw.mode : "hospitality";
    const modeDef = CX_COMPANY_QR_MODES_025N.find((item) => item.code === mode) || CX_COMPANY_QR_MODES_025N[0];
    const maxCapacity = cxClampQrOption025N(raw.max_capacity || raw.capacity || raw.limit || raw.table_count || raw.count || 12, 12);
    const count = Math.min(
      maxCapacity,
      cxClampQrOption025N(raw.table_count || raw.count || raw.visible_count || maxCapacity, maxCapacity)
    );
    const includeBar = typeof raw.include_bar === "boolean" ? raw.include_bar : modeDef.includeBar;

    return {
      mode,
      max_capacity: maxCapacity,
      table_count: count,
      include_bar: includeBar,
      base_url: cxCleanQrBaseUrl025N(raw.base_url || raw.public_base_url || window.location.origin || ""),
      updated_at: raw.updated_at || "",
    };
  }

  function cxQrSelectOptions025N(value, options = CX_COMPANY_QR_COUNT_OPTIONS_025N) {
    const current = Number(value);
    const merged = Array.from(new Set([...options, current].filter((item) => Number.isFinite(Number(item)))))
      .map(Number)
      .filter((item) => item > 0 && item <= 500)
      .sort((a, b) => a - b);
    return merged.map((item) => `<option value="${item}" ${item === current ? "selected" : ""}>${item}</option>`).join("");
  }

  function cxRenderCompanyQrConfig025N(company) {
    const activeQr = cxFindCompanyQrModule025N(company.id, true);
    const anyQr = activeQr || cxFindCompanyQrModule025N(company.id, false);

    if (!activeQr) {
      return `
        <section class="cx-mini-card cx-qr-config-025n" style="margin-top:12px">
          <div class="cx-card-head">
            <div>
              <strong>Configuracion QR por empresa</strong>
              <p>Activa el modulo QR para definir cantidad, capacidad maxima y enlace publico.</p>
            </div>
            <span class="cx-badge ${anyQr ? "cx-badge-warning" : "cx-badge-danger"}">${anyQr ? "QR inactivo" : "Sin QR"}</span>
          </div>
          <div class="cx-empty-state">Esta configuracion solo se desbloquea cuando la empresa tiene el modulo QR activo.</div>
        </section>
      `;
    }

    const settings = cxNormalizeCompanyQrSettings025N(activeQr);
    const modeOptions = CX_COMPANY_QR_MODES_025N.map((mode) => `
      <option value="${escapeHtml(mode.code)}" ${settings.mode === mode.code ? "selected" : ""}>${escapeHtml(mode.label)}</option>
    `).join("");
    const estimatedTotal = settings.table_count + (settings.include_bar ? 1 : 0);
    const capacityText = settings.max_capacity >= 300
      ? "Capacidad alta: el backend lo soporta; para imprimir o revisar muchos QR conviene trabajar por bloques."
      : "Capacidad operativa normal para panel y plantilla de impresion.";

    return `
      <section class="cx-mini-card cx-qr-config-025n" style="margin-top:12px">
        <div class="cx-card-head">
          <div>
            <strong>Configuracion QR por empresa</strong>
            <p>V2 define cuantos QR puede generar/imprimir esta empresa y a que dominio conectan.</p>
          </div>
          <span class="cx-badge cx-badge-live">QR activo</span>
        </div>

        <form class="cx-form cx-qr-form-025n" id="companyQrConfigForm025N" data-module-code="${escapeHtml(activeQr.code)}">
          <div class="cx-qr-grid-025n">
            <label>Uso del QR
              <select name="mode">
                ${modeOptions}
              </select>
            </label>
            <label>Capacidad maxima
              <select name="max_capacity">
                ${cxQrSelectOptions025N(settings.max_capacity)}
              </select>
            </label>
            <label>QR / mesas a generar
              <select name="table_count">
                ${cxQrSelectOptions025N(settings.table_count)}
              </select>
            </label>
            <label>URL publica base
              <input name="base_url" type="url" value="${escapeHtml(settings.base_url)}" placeholder="https://clonexa-backend-production.up.railway.app">
            </label>
          </div>

          <label class="cx-qr-check-025n">
            <input name="include_bar" type="checkbox" ${settings.include_bar ? "checked" : ""}>
            Incluir QR adicional de Barra
          </label>

          <div class="cx-qr-summary-025n">
            <div><span>Se veran en cliente</span><strong>${escapeHtml(estimatedTotal)} QR</strong></div>
            <div><span>Tope tecnico configurado</span><strong>${escapeHtml(settings.max_capacity)}</strong></div>
            <div><span>Lectura publica</span><strong>${escapeHtml(settings.base_url)}/ordenar</strong></div>
          </div>
          <p class="cx-qr-note-025n">${escapeHtml(capacityText)}</p>
          <button class="cx-btn cx-btn-primary" type="submit">Guardar configuracion QR</button>
        </form>
      </section>
    `;
  }

  async function cxSaveCompanyQrConfig025N(companyId, event) {
    event.preventDefault();
    const form = event.target;
    const moduleCode = form.dataset.moduleCode || "qr";
    const raw = Object.fromEntries(new FormData(form).entries());
    const modeDef = CX_COMPANY_QR_MODES_025N.find((item) => item.code === raw.mode) || CX_COMPANY_QR_MODES_025N[0];
    const maxCapacity = cxClampQrOption025N(raw.max_capacity, 10);
    const tableCount = Math.min(maxCapacity, cxClampQrOption025N(raw.table_count, maxCapacity));
    const includeBar = raw.include_bar === "on";
    const payload = {
      mode: modeDef.code,
      max_capacity: maxCapacity,
      table_count: tableCount,
      include_bar: includeBar,
      base_url: cxCleanQrBaseUrl025N(raw.base_url || window.location.origin || ""),
      updated_at: new Date().toISOString(),
    };

    const button = form.querySelector("button[type='submit']");
    const original = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Guardando...";
    }

    try {
      await cxJsonRequest(`/companies/${encodeURIComponent(companyId)}/modules/${encodeURIComponent(moduleCode)}/activate`, {
        method: "POST",
        body: JSON.stringify({ settings: { qr_config: payload } }),
      });
      await loadCompanyModules(companyId);
      const company = state.companies.find((item) => String(item.id) === String(companyId));
      if (company && state.selectedCompanyId === companyId && state.activeDetailTab === "paquete") {
        renderCompanyDetailTab(company);
      }
      showToast("Configuracion QR guardada.");
    } catch (error) {
      showToast(`No se pudo guardar QR: ${error.message}`, "error");
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = original || "Guardar configuracion QR";
      }
    }
  }
  /* CLONEXA_025N_QR_CONFIG_V2_END */

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
    const qrConfig = cxRenderCompanyQrConfig025N(company);
    if (!pkg) {
      return `
        <div style="margin-top:12px">
          <div class="cx-empty-state">Selecciona y activa un paquete para ver sus capacidades heredadas.</div>
          ${qrConfig}
        </div>
      `;
    }

    const settings = state.packageMiniPanelSettings.get(pkg.id) || cxPackageMiniPanelDefaultSettings();
    return `<div style="margin-top:12px">${cxRenderPackageCapabilitiesSummary(pkg, settings)}${qrConfig}</div>`;
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
    core_settings: ["Ajustes", "Idioma, moneda, branding, claves y preferencias generales por empresa.", "Core", "SET"],
    mini_panel: ["Mini Paneles", "Links operativos, usuarios de panel y accesos por rol.", "Core", "MIN"],
    workforce: ["Personal", "Gestion de personal operativo, roles internos y disponibilidad por empresa.", "Core", "WRK"],
    field: ["Operación en campo", "Control para equipos externos, rutas, evidencias y actividad operativa.", "Campo", "FLD"],
    gps: ["GPS", "Ubicacion, rutas y control de equipos en campo.", "Campo", "GPS"],
    login: ["Login tiendas", "Acceso de tienda, turnos y sesiones de colaboradores.", "Campo", "LOG"],
    cotizacion: ["Cotizaciones", "Captura y seguimiento de cotizaciones del tenant.", "Retail", "COT"],
    payroll: ["Nómina", "Calculo de horas, cortes y pagos operativos.", "Finanzas", "PAY"],
    registro_venta: ["Registro Venta", "Captura directa de ventas, facturas y medios de pago.", "Retail", "REG"],
    day_closing: ["Cierre de dia", "Resumen diario de ventas, pedidos, inventario y operacion.", "Hospitality", "DAY"],
    hospitality: ["Hospitality", "Motor para bares, restaurantes, mesas, pedidos y atencion comercial.", "Hospitality", "HSP"],
    loyalty: ["Fidelización", "Clientes recurrentes, beneficios y seguimiento comercial.", "Hospitality", "LOY"],
    orders: ["Pedidos", "Creación, seguimiento y estados de pedidos.", "Hospitality", "ORD"],
    tables: ["Mesas", "Gestion de mesas, cuentas y sesiones por QR.", "Hospitality", "TBL"],
    bots: ["Bots", "Entrada por Telegram, WhatsApp y automatizaciones.", "Input", "BOT"],
    qr: ["QR", "Accesos por QR para mesas, operaciones o formularios.", "Input", "QR"],
    asamblea: ["Asambleas / votaciones", "Configura eventos, quorum, agenda, asistencia, preguntas y votaciones apoyadas en QR.", "Input", "ASA"],
    asambleas: ["Asambleas / votaciones", "Configura eventos, quorum, agenda, asistencia, preguntas y votaciones apoyadas en QR.", "Input", "ASA"],
    asambleas_votaciones: ["Asambleas / votaciones", "Configura eventos, quorum, agenda, asistencia, preguntas y votaciones apoyadas en QR.", "Input", "ASA"],
    assembly: ["Asambleas / votaciones", "Configura eventos, quorum, agenda, asistencia, preguntas y votaciones apoyadas en QR.", "Input", "ASA"],
    inventory: ["Inventario", "Stock, existencias y control operativo de productos o materiales.", "Inventario", "INV"],
    materials: ["Materiales", "Solicitud, entrega, devolucion y control de materiales.", "Inventario", "MAT"],
    stock: ["Stock", "Existencias, minimos y alertas de disponibilidad.", "Inventario", "STK"],
    costs: ["Costos", "Costeo por referencia, produccion, servicio o pedido.", "Producción", "CST"],
    production: ["Producción", "Control de tiempos, referencias, productividad y costos.", "Producción", "PRD"],
    references: ["Referencias", "Catálogo de referencias, productos o servicios medibles.", "Producción", "REF"],
    crm: ["CRM Campo", "Vista operativa para seguimiento, control y acciones por empresa.", "Reportes", "CRM"],
    kpis: ["KPIs", "Indicadores ejecutivos y metricas por módulo.", "Reportes", "KPI"],
    reports: ["Reportes", "Reportes operativos, historicos y auditoria.", "Reportes", "REP"],
    notas___agenda: ["Notas / Agenda", "Notas internas, recordatorios y seguimiento operativo.", "Reportes", "NOT"],
    commercial_closing: ["Cierre comercial", "Seguimiento de ventas, cierres y resultados comerciales.", "Retail", "COM"],
    requests: ["Solicitudes", "Solicitudes internas, aprobaciones y estados.", "Retail", "REQ"],
    retail: ["Retail", "Control de tiendas, ventas, solicitudes e inventario.", "Retail", "RTL"],
    landing: ["Catálogo / Tienda pública", "Tienda pública ShopLink con catálogo, categorías, destacados y WhatsApp.", "Retail", "LAN"],
    shoplink: ["ShopLink", "Catálogo público modular para ventas por redes y WhatsApp.", "Retail", "SHL"],
    sales: ["Ventas", "Actividad comercial, ventas y conversion.", "Retail", "SAL"],
    stores: ["Tiendas", "Sucursales, puntos de venta y operacion retail.", "Retail", "STR"],
    creacion_usuarios: ["Creacion usuarios", "Alta de usuarios operativos y accesos internos.", "Core", "USR"],
  };

  const CX_MODULE_STATUS_025M = {
    core: ["base", "Base", "Infraestructura del tenant; no es pantalla diaria."],
    core_settings: ["functional", "Funcional", "Pantalla y configuracion por empresa."],
    mini_panel: ["functional", "Funcional", "Crea y administra links de mini panel."],
    workforce: ["functional", "Funcional", "Pantalla Workforce operativa."],
    gps: ["functional", "Funcional", "Pantalla GPS operativa."],
    login: ["functional", "Funcional", "Login de tiendas y control de turno."],
    cotizacion: ["functional", "Funcional", "Modulo universal de cotizaciones."],
    payroll: ["functional", "Funcional", "Nomina conectada a tiempos y configuracion."],
    registro_venta: ["functional", "Funcional", "Registro de venta operativo."],
    crm: ["functional", "Funcional", "CRM Campo con datos vivos por area."],
    kpis: ["functional", "Funcional", "KPIs dinamicos del panel cliente."],
    reports: ["functional", "Funcional", "Reportes/lecturas operativas disponibles."],
    hospitality: ["functional", "Funcional", "Dashboard Hospitality operativo."],
    orders: ["functional", "Funcional", "Pedidos/barra/flujo de estados operativo."],
    bots: ["functional", "Funcional", "Configuracion y canales de captura."],
    qr: ["functional", "Funcional", "Mesas QR, claves e impresion."],
    inventory: ["functional", "Funcional", "Inventario y existencias operativo."],
    materials: ["functional", "Funcional", "Materiales y devoluciones operativo."],
    stock: ["functional", "Funcional", "Stock desde inventario con alertas."],
    production: ["functional", "Funcional", "Produccion y tiempos operativos."],
    references: ["functional", "Funcional", "Catalogo maestro operativo."],
    commercial_closing: ["functional", "Funcional", "Cierre comercial con consolidados reales."],
    loyalty: ["functional", "Funcional", "Sorteos y fidelizacion Hospitality."],
    sales: ["functional", "Funcional", "Mini panel y modulo de ventas."],
    stores: ["functional", "Funcional", "Tiendas, metas y login tienda."],
    requests: ["functional", "Funcional", "Solicitudes con seguimiento e impresion."],
    landing: ["functional", "Funcional", "ShopLink público con configuración, catálogo real y enlace WhatsApp."],
    shoplink: ["functional", "Funcional", "ShopLink público con configuración, catálogo real y enlace WhatsApp."],
    notas___agenda: ["functional", "Funcional", "Modulo universal de notas y agenda."],
    asamblea: ["functional", "Funcional", "Asambleas con eventos, quorum, agenda, preguntas y votaciones."],
    asambleas: ["functional", "Funcional", "Asambleas con eventos, quorum, agenda, preguntas y votaciones."],
    asambleas_votaciones: ["functional", "Funcional", "Asambleas con eventos, quorum, agenda, preguntas y votaciones."],
    assembly: ["functional", "Funcional", "Asambleas con eventos, quorum, agenda, preguntas y votaciones."],
    day_closing: ["integrated", "Integrado", "Funciona como consolidado/flujo dentro de cierres."],
    tables: ["integrated", "Integrado", "Las mesas viven dentro de QR y Pedidos."],
    retail: ["integrated", "Integrado", "Vertical agrupadora de ventas, tiendas y solicitudes."],
    field: ["pending", "Pendiente", "Catalogo existe, falta pantalla independiente estable."],
    costs: ["pending", "Pendiente", "Catalogo existe, falta pantalla operativa."],
    creacion_usuarios: ["pending", "Pendiente", "Catalogo existe, falta flujo independiente."],
  };

  const CX_MODULE_STATUS_LABEL_025M = {
    functional: "Funcionales",
    integrated: "Integrados",
    base: "Base",
    pending: "Sin funcionamiento",
  };

  const CX_MODULE_STATUS_ORDER_025M = {
    functional: 0,
    integrated: 1,
    base: 2,
    pending: 3,
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

      const deleteButton = event.target.closest("[data-cx-module-delete]");
      if (deleteButton) {
        const code = deleteButton.dataset.moduleCode;
        const module = state.modules.find((item) => item.code === code) || { code };
        const normalized = normalizeModule(module);
        const candidate = {
          ...normalized,
          assignments: cxModuleAssignments025M(code),
          packageAssignments: cxModulePackageAssignments025T(code),
        };

        if (!cxModuleCanDelete025T(candidate)) {
          alert(`No se puede eliminar este modulo porque esta en uso: ${cxModuleDeleteHint025T(candidate)}.`);
          return;
        }

        const confirmation = prompt(`Para eliminar el modulo global "${code}", escribe exactamente el codigo:`);
        if (confirmation !== code) return;

        deleteButton.disabled = true;
        deleteButton.textContent = "Eliminando...";
        try {
          await cxJsonRequest(`/modules/${encodeURIComponent(code)}?confirm=${encodeURIComponent(code)}`, {
            method: "DELETE",
          });
          await loadModules();
          await loadPackages();
          await Promise.all(state.companies.map((company) => loadCompanyModules(company.id).catch(() => [])));
          renderModules();
          renderPackages();
          showToast("Modulo eliminado.");
        } catch (error) {
          alert(`No se pudo eliminar el modulo: ${error.message}`);
        } finally {
          deleteButton.disabled = false;
          deleteButton.textContent = "Eliminar";
        }
        return;
      }

      const resetModuleFilters = event.target.closest("[data-reset-module-filters]");
      if (resetModuleFilters) {
        state.moduleFilters = {
          search: "",
          status: "all",
          category: "all",
          assignment: "all",
          company: "all",
        };
        renderModules();
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
      const filterForm = event.target.closest("#moduleFilters025T");
      if (filterForm) {
        event.preventDefault();
        const data = new FormData(filterForm);
        state.moduleFilters = {
          search: String(data.get("search") || "").trim(),
          status: String(data.get("status") || "all"),
          category: String(data.get("category") || "all"),
          assignment: String(data.get("assignment") || "all"),
          company: String(data.get("company") || "all"),
        };
        renderModules();
        return;
      }

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



  function cxModuleStatus025M(module = {}) {
    const code = String(module.code || module.module_code || "").trim();
    const row = CX_MODULE_STATUS_025M[code] || ["pending", "Pendiente", "No tiene pantalla o flujo confirmado en el cliente."];
    return { key: row[0], label: row[1], detail: row[2] };
  }

  function cxModuleAssignments025M(code = "") {
    const active = [];
    const inactive = [];
    const archived = [];

    state.companies.forEach((company) => {
      const rows = safeArray(state.companyModules.get(company.id)).map(normalizeModule);
      const row = rows.find((item) => item.code === code);
      if (!row) return;

      const label = company.name || company.slug || "Empresa";
      if (isArchivedCompany(company)) {
        archived.push(label);
      } else if (row.enabled === false) {
        inactive.push(label);
      } else {
        active.push(label);
      }
    });

    return { active, inactive, archived };
  }

  function cxModuleAssignmentChips025M(assignments) {
    if (!assignments.active.length && !assignments.inactive.length && !assignments.archived.length) {
      return `<span class="cx-badge">Sin asignacion</span>`;
    }

    const active = assignments.active.length
      ? assignments.active.map((name) => `<span class="cx-badge cx-badge-live">${escapeHtml(name)}</span>`).join("")
      : `<span class="cx-badge">Sin empresas activas</span>`;
    const inactive = assignments.inactive.length
      ? `<span class="cx-badge">${escapeHtml(assignments.inactive.length)} apagada(s)</span>`
      : "";
    const archived = assignments.archived.length
      ? `<span class="cx-badge cx-badge-warning">${escapeHtml(assignments.archived.length)} archivada(s)</span>`
      : "";

    return `${active}${inactive}${archived}`;
  }

  function cxModulePackageAssignments025T(code = "") {
    const normalizedCode = String(code || "").trim();
    if (!normalizedCode) return [];
    return state.packages
      .filter((pkg) => safeArray(pkg.modules).some((module) => {
        const moduleCode = String(typeof module === "string" ? module : (module.code || module.module_code || "")).trim();
        return moduleCode === normalizedCode;
      }))
      .map((pkg) => pkg.name || pkg.code || "Paquete");
  }

  function cxModuleAssignmentTotal025T(assignments) {
    return safeArray(assignments?.active).length + safeArray(assignments?.inactive).length + safeArray(assignments?.archived).length;
  }

  function cxModuleCanDelete025T(module) {
    const assignmentCount = cxModuleAssignmentTotal025T(module.assignments || {});
    const packageCount = safeArray(module.packageAssignments).length;
    return assignmentCount === 0 && packageCount === 0;
  }

  function cxModuleDeleteHint025T(module) {
    const assignmentCount = cxModuleAssignmentTotal025T(module.assignments || {});
    const packageCount = safeArray(module.packageAssignments).length;
    if (assignmentCount || packageCount) {
      return `${assignmentCount} empresa(s) / ${packageCount} paquete(s)`;
    }
    return "Libre para limpiar";
  }

  function cxModuleMatchesFilters025T(module) {
    const filters = state.moduleFilters || {};
    const search = String(filters.search || "").trim().toLowerCase();
    const category = String(filters.category || "all");
    const status = String(filters.status || "all");
    const assignment = String(filters.assignment || "all");
    const companyId = String(filters.company || "all");
    const meta = module.meta || {};
    const assignments = module.assignments || { active: [], inactive: [], archived: [] };
    const packageAssignments = safeArray(module.packageAssignments);
    const assignedTotal = cxModuleAssignmentTotal025T(assignments);

    if (search) {
      const haystack = [
        module.code,
        meta.name,
        meta.description,
        meta.categoryLabel,
        module.status?.label,
        module.status?.detail,
        ...assignments.active,
        ...assignments.inactive,
        ...assignments.archived,
        ...packageAssignments,
      ].join(" ").toLowerCase();
      if (!haystack.includes(search)) return false;
    }

    if (status !== "all" && module.status.key !== status) return false;
    if (category !== "all" && String(meta.categoryLabel || module.category || "General") !== category) return false;

    if (assignment === "assigned" && assignedTotal === 0) return false;
    if (assignment === "unassigned" && assignedTotal > 0) return false;
    if (assignment === "inactive" && !assignments.inactive.length) return false;
    if (assignment === "archived" && !assignments.archived.length) return false;
    if (assignment === "package" && !packageAssignments.length) return false;

    if (companyId !== "all") {
      const company = state.companies.find((item) => String(item.id) === companyId);
      const label = company?.name || company?.slug || "";
      if (!label) return false;
      const names = [...assignments.active, ...assignments.inactive, ...assignments.archived];
      if (!names.includes(label)) return false;
    }

    return true;
  }

  function cxModuleFilterOptions025T(modules = []) {
    const categories = Array.from(new Set(modules.map((module) => module.meta?.categoryLabel || module.category || "General"))).sort((a, b) => a.localeCompare(b, "es"));
    const categoryOptions = categories.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("");
    const companyOptions = state.companies
      .filter((company) => !isArchivedCompany(company))
      .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "es"))
      .map((company) => `<option value="${escapeHtml(company.id)}">${escapeHtml(company.name || company.slug || "Empresa")}</option>`)
      .join("");
    const filters = state.moduleFilters || {};
    return `
      <form class="cx-module-filters-025t" id="moduleFilters025T">
        <label>Buscar
          <input name="search" value="${escapeHtml(filters.search || "")}" placeholder="Modulo, codigo, empresa..." />
        </label>
        <label>Estado
          <select name="status">
            <option value="all">Todos</option>
            <option value="functional">Funcionales</option>
            <option value="integrated">Integrados</option>
            <option value="base">Base</option>
            <option value="pending">Sin funcionamiento</option>
          </select>
        </label>
        <label>Vertical
          <select name="category">
            <option value="all">Todas</option>
            ${categoryOptions}
          </select>
        </label>
        <label>Uso
          <select name="assignment">
            <option value="all">Todos</option>
            <option value="assigned">Asignados</option>
            <option value="unassigned">Sin asignar</option>
            <option value="inactive">Apagados</option>
            <option value="archived">Archivados</option>
            <option value="package">En paquetes</option>
          </select>
        </label>
        <label>Empresa
          <select name="company">
            <option value="all">Todas</option>
            ${companyOptions}
          </select>
        </label>
        <button class="cx-btn cx-btn-primary" type="submit">Filtrar</button>
        <button class="cx-btn cx-btn-ghost" data-reset-module-filters type="button">Limpiar</button>
      </form>
    `;
  }

  function cxModuleApplyFilterValues025T() {
    const filters = state.moduleFilters || {};
    const form = el("#moduleFilters025T");
    if (!form) return;
    ["status", "category", "assignment", "company"].forEach((name) => {
      const node = form.querySelector(`[name='${name}']`);
      if (node) node.value = filters[name] || "all";
    });
  }

  function cxModuleMiniBar025T(label, value, max, cls = "") {
    const percent = Math.max(4, Math.round((Number(value || 0) / Math.max(1, Number(max || 1))) * 100));
    return `
      <div class="cx-module-statbar-025t ${cls}">
        <div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value || 0)}</span></div>
        <div class="cx-progress"><span style="width:${escapeHtml(percent)}%"></span></div>
      </div>
    `;
  }

  function cxModuleStatusBadge025M(status) {
    const cls = status.key === "functional"
      ? "cx-badge-live"
      : status.key === "pending"
        ? "cx-badge-danger"
        : status.key === "integrated"
          ? "cx-badge-warning"
          : "cx-badge-primary";
    return `<span class="cx-badge ${cls}">${escapeHtml(status.label)}</span>`;
  }

  function cxModuleCreateForm025M() {
    return `
      <details class="cx-module-create-025m">
        <summary>Crear modulo global</summary>
        <form class="cx-form" id="createModuleForm">
          <div class="cx-module-create-grid-025m">
            <label>Codigo
              <input name="code" placeholder="tecnicos_field" required />
            </label>
            <label>Nombre
              <input name="name" placeholder="Tecnicos Field" required />
            </label>
            <label>Categoria
              <select name="category">
                <option value="core">Core</option>
                <option value="field">Campo</option>
                <option value="inventory">Inventario</option>
                <option value="production">Produccion</option>
                <option value="finance">Finanzas</option>
                <option value="hospitality">Hospitality</option>
                <option value="retail">Retail</option>
                <option value="read_model">Reportes</option>
                <option value="input">Input</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <button class="cx-btn cx-btn-primary" type="submit">Crear modulo</button>
          </div>
          <label>Descripcion
            <input name="description" placeholder="Que ejecuta este modulo dentro de CLONEXA" />
          </label>
        </form>
      </details>
    `;
  }

  function renderModules() {
    const grid = el("#modulesGrid");
    if (!grid) return;

    if (!state.modules.length) {
      grid.innerHTML = `<div class="cx-empty-state">No se pudieron cargar modulos.</div>`;
      return;
    }

    const modules = state.modules
      .map((module) => {
        const normalized = normalizeModule(module);
        const meta = cxModuleMeta(normalized);
        const status = cxModuleStatus025M(normalized);
        const assignments = cxModuleAssignments025M(normalized.code);
        const packageAssignments = cxModulePackageAssignments025T(normalized.code);
        return { ...normalized, meta, status, assignments, packageAssignments };
      })
      .sort((a, b) => {
        const statusDiff = (CX_MODULE_STATUS_ORDER_025M[a.status.key] ?? 9) - (CX_MODULE_STATUS_ORDER_025M[b.status.key] ?? 9);
        if (statusDiff) return statusDiff;
        return String(a.meta.name || a.code).localeCompare(String(b.meta.name || b.code), "es");
      });

    const activeCompanyCount = state.companies.filter((company) => !isArchivedCompany(company)).length;
    const counts = modules.reduce((acc, module) => {
      acc[module.status.key] = (acc[module.status.key] || 0) + 1;
      acc.activeAssignments += module.assignments.active.length;
      acc.inactiveAssignments += module.assignments.inactive.length;
      acc.archivedAssignments += module.assignments.archived.length;
      acc.packageLinks += module.packageAssignments.length;
      if (cxModuleAssignmentTotal025T(module.assignments) === 0) acc.unassigned += 1;
      if (cxModuleCanDelete025T(module)) acc.cleanup += 1;
      return acc;
    }, { functional: 0, integrated: 0, base: 0, pending: 0, activeAssignments: 0, inactiveAssignments: 0, archivedAssignments: 0, packageLinks: 0, unassigned: 0, cleanup: 0 });

    const filteredModules = modules.filter(cxModuleMatchesFilters025T);
    const maxStatus = Math.max(1, counts.functional || 0, counts.integrated || 0, counts.base || 0, counts.pending || 0);
    const categoryCounts = modules.reduce((acc, module) => {
      const label = module.meta.categoryLabel || module.category || "General";
      acc[label] = (acc[label] || 0) + 1;
      return acc;
    }, {});
    const topCompanies = state.companies
      .filter((company) => !isArchivedCompany(company))
      .map((company) => {
        const rows = safeArray(state.companyModules.get(company.id)).map(normalizeModule);
        return {
          name: company.name || company.slug || "Empresa",
          total: rows.filter((row) => row.enabled !== false).length,
        };
      })
      .filter((item) => item.total > 0)
      .sort((a, b) => b.total - a.total)
      .slice(0, 5);
    const cleanupCandidates = modules.filter(cxModuleCanDelete025T).slice(0, 8);

    const grouped = new Map();
    filteredModules.forEach((module) => {
      const label = CX_MODULE_STATUS_LABEL_025M[module.status.key] || "Otros";
      if (!grouped.has(label)) grouped.set(label, []);
      grouped.get(label).push(module);
    });

    grid.innerHTML = `
      <section class="cx-module-command-025m cx-module-command-025t">
        <div class="cx-card-head">
          <div>
            <h2>Centro de mando modular</h2>
            <p>Estado funcional, asignaciones, paquetes y limpieza controlada del catalogo global.</p>
          </div>
          <div class="cx-actions">
            <span class="cx-badge cx-badge-primary">${escapeHtml(modules.length)} modulos globales</span>
            <span class="cx-badge">${escapeHtml(filteredModules.length)} visibles</span>
          </div>
        </div>

        <div class="cx-module-summary-025m">
          <div><span>Total catalogo</span><strong>${escapeHtml(modules.length)}</strong><small>${escapeHtml(activeCompanyCount)} empresas activas</small></div>
          <div><span>Funcionales</span><strong>${escapeHtml(counts.functional || 0)}</strong><small>Listos para operar</small></div>
          <div><span>Asignaciones</span><strong>${escapeHtml(counts.activeAssignments || 0)}</strong><small>${escapeHtml(counts.inactiveAssignments || 0)} apagadas - ${escapeHtml(counts.archivedAssignments || 0)} archivadas</small></div>
          <div><span>Limpieza segura</span><strong>${escapeHtml(counts.cleanup || 0)}</strong><small>Sin empresa ni paquete</small></div>
        </div>
        ${cxModuleFilterOptions025T(modules)}
      </section>

      <section class="cx-module-layout-025t">
        <aside class="cx-module-side-025t">
          <article class="cx-panel">
            <span class="cx-kicker">Estado del mapa</span>
            ${cxModuleMiniBar025T("Funcionales", counts.functional || 0, maxStatus, "is-live")}
            ${cxModuleMiniBar025T("Integrados", counts.integrated || 0, maxStatus, "is-warning")}
            ${cxModuleMiniBar025T("Base", counts.base || 0, maxStatus, "is-base")}
            ${cxModuleMiniBar025T("Sin funcionamiento", counts.pending || 0, maxStatus, "is-danger")}
          </article>
          <article class="cx-panel">
            <span class="cx-kicker">Verticales</span>
            ${Object.entries(categoryCounts).sort((a, b) => b[1] - a[1]).map(([label, total]) => cxModuleMiniBar025T(label, total, modules.length)).join("")}
          </article>
          <article class="cx-panel">
            <span class="cx-kicker">Empresas con mas modulos</span>
            ${topCompanies.length ? topCompanies.map((item) => cxModuleMiniBar025T(item.name, item.total, modules.length, "is-live")).join("") : `<div class="cx-empty-state">Sin empresas con modulos activos.</div>`}
          </article>
          <article class="cx-panel">
            <span class="cx-kicker">Se puede eliminar</span>
            ${cleanupCandidates.length
              ? cleanupCandidates.map((module) => `<button class="cx-module-clean-line-025t" type="button" data-cx-module-delete data-module-code="${escapeHtml(module.code)}"><strong>${escapeHtml(module.meta.name)}</strong><span>${escapeHtml(module.code)}</span></button>`).join("")
              : `<div class="cx-empty-state">No hay modulos libres para limpiar.</div>`}
          </article>
        </aside>

        <div class="cx-module-catalog-025t">
          ${filteredModules.length ? Array.from(grouped.entries()).map(([group, rows]) => `
            <section class="cx-module-section-025m">
              <div class="cx-section-title">
                <h3>${escapeHtml(group)}</h3>
                <p>${escapeHtml(rows.length)} modulo(s)</p>
              </div>
              <div class="cx-module-card-grid-025t">
                ${rows.map((module) => {
                  const canDelete = cxModuleCanDelete025T(module);
                  const packageChips = module.packageAssignments.length
                    ? module.packageAssignments.slice(0, 4).map((name) => `<span class="cx-badge cx-badge-primary">${escapeHtml(name)}</span>`).join("")
                    : `<span class="cx-badge">Sin paquete</span>`;
                  return `
                    <article class="cx-module-card-025t cx-module-status-${escapeHtml(module.status.key)}">
                      <div class="cx-module-card-top-025t">
                        <span class="cx-module-mark-025t">${escapeHtml(module.meta.badge)}</span>
                        <div>
                          <strong>${escapeHtml(module.meta.name)}</strong>
                          <small>${escapeHtml(module.code)} - ${escapeHtml(module.meta.categoryLabel || module.category || "General")}</small>
                        </div>
                        ${cxModuleStatusBadge025M(module.status)}
                      </div>
                      <p>${escapeHtml(module.status.detail)}</p>
                      <div class="cx-module-card-meta-025t">
                        <div><span>Empresas</span><strong>${escapeHtml(cxModuleAssignmentTotal025T(module.assignments))}</strong></div>
                        <div><span>Paquetes</span><strong>${escapeHtml(module.packageAssignments.length)}</strong></div>
                        <div><span>Estado</span><strong>${escapeHtml(module.is_active ? "Activo" : "Inactivo")}</strong></div>
                      </div>
                      <div class="cx-module-card-block-025t">
                        <span>Asignado a</span>
                        <div>${cxModuleAssignmentChips025M(module.assignments)}</div>
                      </div>
                      <div class="cx-module-card-block-025t">
                        <span>Paquetes</span>
                        <div>${packageChips}</div>
                      </div>
                      <div class="cx-module-card-actions-025t">
                        <button class="cx-btn cx-btn-small" type="button" data-cx-module-info data-module-code="${escapeHtml(module.code)}">Info</button>
                        ${canDelete
                          ? `<button class="cx-btn cx-btn-danger cx-btn-small" type="button" data-cx-module-delete data-module-code="${escapeHtml(module.code)}">Eliminar</button>`
                          : `<button class="cx-btn cx-btn-small" type="button" disabled title="${escapeHtml(cxModuleDeleteHint025T(module))}">En uso</button>`}
                      </div>
                    </article>
                  `;
                }).join("")}
              </div>
            </section>
          `).join("") : `<div class="cx-empty-state">No hay modulos para este filtro.</div>`}
        </div>
      </section>

      <section class="cx-module-section-025m">
        <div class="cx-module-create-shell-025t">
          <div>
            <span class="cx-kicker">Administracion del catalogo</span>
            <h3>Crear modulo global</h3>
            <p>Usalo solo para nuevos modulos reales. Para pruebas o duplicados, elimina los libres desde limpieza segura.</p>
          </div>
          ${cxModuleCreateForm025M()}
        </div>
      </section>
    `;
    cxModuleApplyFilterValues025T();
  }

  function cxAccessUrl026B(path = "") {
    const value = String(path || "");
    if (/^https?:\/\//i.test(value)) return value;
    const clean = value.startsWith("/") ? value : `/${value}`;
    return `${window.location.origin || ""}${clean}`;
  }

  function cxAccessModuleSet026B(companyId) {
    return new Set(moduleCodesForCompany(companyId).map((code) => cxQrNorm025N(code)));
  }

  function cxAccessHasModule026B(moduleSet, codes = []) {
    return codes.some((code) => moduleSet.has(cxQrNorm025N(code)));
  }

  function cxAccessQrLabel026B(settings = {}) {
    if (settings.mode === "voting") return "Participante 1";
    if (settings.mode === "generic") return "QR 1";
    return settings.include_bar ? "Barra" : "Mesa 1";
  }

  function cxAccessQrUrl026B(company, settings = {}) {
    const base = cxCleanQrBaseUrl025N(settings.base_url || window.location.origin || "");
    const point = cxAccessQrLabel026B(settings);
    return `${base}/ordenar?company_id=${encodeURIComponent(company.id)}&mesa=${encodeURIComponent(point)}`;
  }

  function cxAccessLinkCard026B(item) {
    const url = cxAccessUrl026B(item.href);
    return `
      <article class="cx-access-card-026b">
        <div>
          <span class="cx-badge ${item.badgeClass || "cx-badge-primary"}">${escapeHtml(item.badge || item.href)}</span>
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.subtitle || "")}</p>
        </div>
        <div class="cx-access-actions-026b">
          <a class="cx-btn cx-btn-small" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">Abrir</a>
          <button class="cx-btn cx-btn-small" type="button" data-copy="${escapeHtml(url)}">Copiar</button>
        </div>
      </article>
    `;
  }

  function cxAccessCompanyLinks026B(company) {
    const encodedId = encodeURIComponent(company.id);
    const modules = cxAccessModuleSet026B(company.id);
    const links = [
      { title: "Panel cliente", href: `/client?company_id=${encodedId}`, subtitle: "Operacion del tenant", badge: "/client" },
      { title: "Login empresa", href: "/login", subtitle: "Acceso dueno / encargado", badge: "/login" },
    ];

    if (cxAccessHasModule026B(modules, ["mini_panel", "sales", "registro_venta", "cotizacion", "requests"])) {
      links.push({
        title: "Mini panel ventas",
        href: `/mini-panel/login?company_id=${encodedId}&type=sales`,
        subtitle: "Entrada vendedor / comercial",
        badge: "sales",
      });
    }

    if (cxAccessHasModule026B(modules, ["stores", "login", "retail"])) {
      links.push({
        title: "Mini panel tiendas",
        href: `/mini-panel/login?company_id=${encodedId}&type=store`,
        subtitle: "Entrada tienda / cajero",
        badge: "store",
      });
    }

    const qrModule = cxFindCompanyQrModule025N(company.id, true);
    if (qrModule) {
      const settings = cxNormalizeCompanyQrSettings025N(qrModule);
      links.push({
        title: settings.mode === "voting" ? "QR votacion" : "QR publico",
        href: cxAccessQrUrl026B(company, settings),
        subtitle: `${settings.table_count}/${settings.max_capacity} habilitados`,
        badge: settings.mode,
        badgeClass: "cx-badge-live",
      });
    }

    if (cxAccessHasModule026B(modules, ["asamblea", "asambleas", "asambleas_votaciones", "assembly"])) {
      links.push({
        title: "Asamblea",
        href: `/client?company_id=${encodedId}`,
        subtitle: "Configurar evento, quorum y votaciones",
        badge: "ASA",
      });
    }

    return links;
  }

  function cxAccessModulePreview026B(companyId) {
    const codes = moduleCodesForCompany(companyId);
    if (!codes.length) return "Sin modulos activos";
    const labels = codes.slice(0, 5).map((code) => (CX_MODULE_META[code] ? CX_MODULE_META[code][0] : code));
    const extra = codes.length > labels.length ? ` +${codes.length - labels.length}` : "";
    return `${labels.join(", ")}${extra}`;
  }

  function cxAccessCompanyCard026B(company) {
    const modules = cxAccessModuleSet026B(company.id);
    const users = state.companyUsers.get(company.id);
    const ownerInfo = ownerAccessInfo(users);
    const owner = ownerInfo.owner;
    const qrModule = cxFindCompanyQrModule025N(company.id, true);
    const qrSettings = qrModule ? cxNormalizeCompanyQrSettings025N(qrModule) : null;
    const status = companyStatus(company);
    const statusClass = status === "active" ? "cx-badge-live" : "cx-badge-danger";
    const links = cxAccessCompanyLinks026B(company);

    const miniPanels = [
      cxAccessHasModule026B(modules, ["mini_panel", "sales", "registro_venta"]) ? "ventas" : "",
      cxAccessHasModule026B(modules, ["stores", "login", "retail"]) ? "tiendas" : "",
    ].filter(Boolean).join(" / ") || "sin mini panel";

    return `
      <article class="cx-access-company-card-026b">
        <div class="cx-access-company-head-026b">
          <div>
            <span class="cx-badge ${statusClass}">${escapeHtml(status)}</span>
            <h3>${escapeHtml(company.name)}</h3>
            <p>${escapeHtml(company.slug || company.id)}</p>
          </div>
          <button class="cx-btn cx-btn-small" type="button" data-select-company="${escapeHtml(company.id)}" data-detail-tab="accesos">Gestionar</button>
        </div>
        <div class="cx-access-kv-grid-026b">
          <div><span>Paquete</span><strong>${escapeHtml(packageForCompany(company))}</strong></div>
          <div><span>Acceso maestro</span><strong>${escapeHtml(owner ? (owner.email || owner.name || ownerInfo.status) : ownerInfo.status)}</strong></div>
          <div><span>Mini panel</span><strong>${escapeHtml(miniPanels)}</strong></div>
          <div><span>QR</span><strong>${escapeHtml(qrSettings ? `${qrSettings.table_count}/${qrSettings.max_capacity} ${qrSettings.mode}` : "no activo")}</strong></div>
        </div>
        <p class="cx-access-modules-026b">${escapeHtml(cxAccessModulePreview026B(company.id))}</p>
        <div class="cx-access-link-list-026b">
          ${links.map((link) => {
            const url = cxAccessUrl026B(link.href);
            return `
              <div class="cx-access-row-026b">
                <div>
                  <strong>${escapeHtml(link.title)}</strong>
                  <small>${escapeHtml(link.subtitle || url)}</small>
                </div>
                <div class="cx-access-actions-026b">
                  <a class="cx-btn cx-btn-small" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">Abrir</a>
                  <button class="cx-btn cx-btn-small" type="button" data-copy="${escapeHtml(url)}">Copiar</button>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      </article>
    `;
  }

  function renderAccess() {
    const grid = el("#accessGrid");
    if (!grid) return;

    const title = grid.closest(".cx-card")?.querySelector(".cx-card-head h2");
    const subtitle = grid.closest(".cx-card")?.querySelector(".cx-card-head p");
    if (title) title.textContent = "Centro de accesos operativos";
    if (subtitle) subtitle.textContent = "Mapa de entrada por herramienta, empresa y modulo activo.";

    const companies = state.companies.filter((company) => !isArchivedCompany(company));
    const qrCompanies = companies.filter((company) => cxFindCompanyQrModule025N(company.id, true)).length;
    const miniPanelCompanies = companies.filter((company) => {
      const modules = cxAccessModuleSet026B(company.id);
      return cxAccessHasModule026B(modules, ["mini_panel", "sales", "stores", "login", "retail"]);
    }).length;
    const totalLinks = companies.reduce((count, company) => count + cxAccessCompanyLinks026B(company).length, 0);

    const globalLinks = [
      { title: "Admin V2", subtitle: "Super consola SaaS", href: "/admin-v2", badge: "/admin-v2", badgeClass: "cx-badge-live" },
      { title: "Panel cliente", subtitle: "Entrada general de tenants", href: "/client", badge: "/client" },
      { title: "Login empresa", subtitle: "Acceso dueno / encargado", href: "/login", badge: "/login" },
      { title: "Mini panel", subtitle: "Login operativo por rol", href: "/mini-panel/login", badge: "/mini-panel" },
      { title: "Ordenar QR", subtitle: "Entrada publica QR", href: "/ordenar", badge: "/ordenar" },
      { title: "Docs API", subtitle: "Swagger operativo", href: "/docs", badge: "/docs" },
      { title: "Health", subtitle: "Estado de produccion", href: "/health", badge: "/health", badgeClass: "cx-badge-live" },
      { title: "Landing", subtitle: "Web publica comercial", href: "https://clonexa-landing-production.up.railway.app/", badge: "landing" },
    ];

    if (!state.adminV2Sessions) {
      state.adminV2Sessions = { loading: true, sessions: [] };
      loadAdminV2Sessions026H(true)
        .then(() => {
          if (state.activeView === "access") renderAccess();
        })
        .catch(() => null);
    }

    grid.innerHTML = `
      <div class="cx-access-summary-026b">
        <div class="cx-kv"><span>Empresas visibles</span><strong>${escapeHtml(companies.length)}</strong></div>
        <div class="cx-kv"><span>Accesos tenant</span><strong>${escapeHtml(totalLinks)}</strong></div>
        <div class="cx-kv"><span>Mini panel activo</span><strong>${escapeHtml(miniPanelCompanies)}</strong></div>
        <div class="cx-kv"><span>QR activo</span><strong>${escapeHtml(qrCompanies)}</strong></div>
      </div>

      <section class="cx-access-section-026b">
        <div class="cx-access-section-head-026b">
          <div>
            <span class="cx-kicker">Global</span>
            <h3>Entradas base del sistema</h3>
          </div>
        </div>
        <div class="cx-access-grid-026b">
          ${globalLinks.map(cxAccessLinkCard026B).join("")}
        </div>
      </section>

      ${renderAdminV2SessionMonitor026H()}

      <section class="cx-access-section-026b">
        <div class="cx-access-section-head-026b">
          <div>
            <span class="cx-kicker">Empresas</span>
            <h3>Accesos por tenant</h3>
          </div>
          <button class="cx-btn cx-btn-small" type="button" data-nav-view="companies">Gestionar empresas</button>
        </div>
        ${companies.length ? `
          <div class="cx-access-company-grid-026b">
            ${companies.map(cxAccessCompanyCard026B).join("")}
          </div>
        ` : `<div class="cx-empty-state">No hay empresas visibles para mostrar accesos.</div>`}
      </section>
    `;
  }

  function cxHealthBadge026C(level = "ok", label = "OK") {
    const cls = level === "danger"
      ? "cx-badge-danger"
      : level === "warn"
        ? "cx-badge-warning"
        : "cx-badge-live";
    return `<span class="cx-badge ${cls}">${escapeHtml(label)}</span>`;
  }

  function cxHealthServiceCard026C(item) {
    return `
      <article class="cx-health-service-026c cx-health-${escapeHtml(item.level || "ok")}-026c">
        <div>
          ${cxHealthBadge026C(item.level, item.badge)}
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.detail || "")}</p>
        </div>
        ${item.href ? `
          <div class="cx-access-actions-026b">
            <a class="cx-btn cx-btn-small" href="${escapeHtml(cxAccessUrl026B(item.href))}" target="_blank" rel="noreferrer">Abrir</a>
            <button class="cx-btn cx-btn-small" type="button" data-copy="${escapeHtml(cxAccessUrl026B(item.href))}">Copiar</button>
          </div>
        ` : ""}
      </article>
    `;
  }

  function cxHealthCompanyRisk026C(company) {
    const status = companyStatus(company);
    const owner = ownerAccessInfo(state.companyUsers.get(company.id));
    const modules = moduleCodesForCompany(company.id);
    const activity = state.companyActivity.get(company.id);
    const risks = [];

    if (status !== "active") risks.push(status === "inactive" ? "Empresa inactiva" : "Estado no activo");
    if (owner.level === "danger") risks.push("Acceso maestro pendiente");
    if (owner.level === "warn") risks.push("Acceso maestro revisar");
    if (!modules.length && status === "active") risks.push("Sin modulos activos");
    if (activity?.errors?.length) risks.push(`${activity.errors.length} consulta(s) parciales`);

    const qr = cxFindCompanyQrModule025N(company.id, true);
    const qrText = qr ? (() => {
      const settings = cxNormalizeCompanyQrSettings025N(qr);
      return `${settings.table_count}/${settings.max_capacity} ${settings.mode}`;
    })() : "sin QR";

    return {
      risks,
      owner,
      modules,
      activity,
      qrText,
      level: risks.some((item) => item.toLowerCase().includes("pendiente") || item.toLowerCase().includes("sin modulos"))
        ? "danger"
        : risks.length
          ? "warn"
          : "ok",
    };
  }

  function cxHealthCompanyRow026C(company) {
    const info = cxHealthCompanyRisk026C(company);
    const statusLabel = info.level === "ok" ? "OK" : info.level === "warn" ? "Revisar" : "Riesgo";
    const activityLabel = info.activity
      ? `${info.activity.totalSignals || 0} senales`
      : "sin muestra";

    return `
      <article class="cx-health-company-026c">
        <div>
          <h3>${escapeHtml(company.name)}</h3>
          <p>${escapeHtml(company.slug || company.id)}</p>
        </div>
        <div class="cx-health-company-meta-026c">
          ${cxHealthBadge026C(info.level, statusLabel)}
          <span>${escapeHtml(info.modules.length)} modulos</span>
          <span>${escapeHtml(info.qrText)}</span>
          <span>${escapeHtml(activityLabel)}</span>
        </div>
        <div class="cx-health-company-risks-026c">
          ${info.risks.length ? info.risks.map((risk) => `<span class="cx-badge cx-badge-warning">${escapeHtml(risk)}</span>`).join("") : `<span class="cx-badge cx-badge-live">Sin riesgos detectados</span>`}
        </div>
        <button class="cx-btn cx-btn-small" type="button" data-select-company="${escapeHtml(company.id)}">Gestionar</button>
      </article>
    `;
  }

  function renderHealth() {
    const content = el("#healthContent");
    if (!content) return;

    const title = content.closest(".cx-card")?.querySelector(".cx-card-head h2");
    const subtitle = content.closest(".cx-card")?.querySelector(".cx-card-head p");
    if (title) title.textContent = "Centro de salud operativa";
    if (subtitle) subtitle.textContent = "Semaforos de produccion, tenants, modulos, accesos y riesgos.";

    const apiOk = !!state.health && state.health.ok !== false;
    const visibleCompanies = state.companies.filter((company) => !isArchivedCompany(company));
    const activeCompanies = visibleCompanies.filter((company) => companyStatus(company) === "active");
    const inactiveCompanies = visibleCompanies.filter((company) => companyStatus(company) !== "active");
    const ownerRisks = activeCompanies.filter((company) => ownerAccessInfo(state.companyUsers.get(company.id)).level !== "ok");
    const noModules = activeCompanies.filter((company) => !moduleCodesForCompany(company.id).length);
    const qrActive = visibleCompanies.filter((company) => cxFindCompanyQrModule025N(company.id, true)).length;
    const pendingModules = state.modules.map(normalizeModule).filter((module) => cxModuleStatus025M(module).key === "pending");
    const alerts = cxDashboardAlerts023A();
    const errors = [...new Set([...(state.errors || []), ...(state.dashboardActivityErrors || [])].filter(Boolean))];
    const riskCompanies = visibleCompanies
      .map((company) => ({ company, info: cxHealthCompanyRisk026C(company) }))
      .sort((a, b) => (b.info.risks.length - a.info.risks.length) || a.company.name.localeCompare(b.company.name));

    const services = [
      {
        title: "API produccion",
        badge: apiOk ? "LIVE" : "OFFLINE",
        level: apiOk ? "ok" : "danger",
        detail: apiOk ? "Health responde correctamente." : (state.health?.error || "Health no disponible."),
        href: "/health",
      },
      {
        title: "PostgreSQL",
        badge: apiOk ? "Derivado OK" : "No verificado",
        level: apiOk ? "ok" : "warn",
        detail: "Estado inferido desde API y lecturas principales de V2.",
      },
      {
        title: "Tenants",
        badge: `${activeCompanies.length}/${visibleCompanies.length} activos`,
        level: inactiveCompanies.length ? "warn" : "ok",
        detail: `${inactiveCompanies.length} tenant(s) visibles no activos.`,
        href: "/admin-v2",
      },
      {
        title: "Acceso Maestro",
        badge: ownerRisks.length ? `${ownerRisks.length} revisar` : "OK",
        level: ownerRisks.length ? "danger" : "ok",
        detail: "Control de dueno/encargado por empresa.",
      },
      {
        title: "Modulos",
        badge: `${state.modules.length} catalogo`,
        level: noModules.length || pendingModules.length ? "warn" : "ok",
        detail: `${pendingModules.length} modulo(s) pendientes y ${noModules.length} empresa(s) sin modulos.`,
      },
      {
        title: "QR configurado",
        badge: `${qrActive} empresa(s)`,
        level: qrActive ? "ok" : "warn",
        detail: "Empresas con modulo QR activo y disponible para operar.",
      },
    ];

    content.innerHTML = `
      <section class="cx-health-hero-026c">
        <div>
          <span class="cx-kicker">Estado general</span>
          <h2>${apiOk && !ownerRisks.length && !noModules.length ? "Sistema operativo" : "Sistema con puntos por revisar"}</h2>
          <p>${escapeHtml(state.health?.service || "clonexa-backend")} · Ultimo refresh ${escapeHtml(state.lastRefresh || "sin refresh")}</p>
        </div>
        ${cxHealthBadge026C(apiOk ? "ok" : "danger", apiOk ? "LIVE" : "OFFLINE")}
      </section>

      <div class="cx-health-kpis-026c">
        <div class="cx-kv"><span>API</span><strong>${apiOk ? "LIVE" : "OFFLINE"}</strong></div>
        <div class="cx-kv"><span>Tenants activos</span><strong>${escapeHtml(activeCompanies.length)}</strong></div>
        <div class="cx-kv"><span>Riesgos acceso</span><strong>${escapeHtml(ownerRisks.length)}</strong></div>
        <div class="cx-kv"><span>Sin modulos</span><strong>${escapeHtml(noModules.length)}</strong></div>
        <div class="cx-kv"><span>QR activos</span><strong>${escapeHtml(qrActive)}</strong></div>
        <div class="cx-kv"><span>Errores carga</span><strong>${escapeHtml(errors.length)}</strong></div>
      </div>

      <section class="cx-health-section-026c">
        <div class="cx-health-section-head-026c">
          <div>
            <span class="cx-kicker">Servicios</span>
            <h3>Semaforos principales</h3>
          </div>
          <button class="cx-btn cx-btn-small" type="button" data-nav-view="access">Ver accesos</button>
        </div>
        <div class="cx-health-services-026c">
          ${services.map(cxHealthServiceCard026C).join("")}
        </div>
      </section>

      <section class="cx-health-section-026c">
        <div class="cx-health-section-head-026c">
          <div>
            <span class="cx-kicker">Alertas</span>
            <h3>Checklist de riesgo SaaS</h3>
          </div>
        </div>
        <div class="cx-health-alerts-026c">
          ${alerts.map((alert) => `
            <article class="cx-health-alert-026c">
              ${cxHealthBadge026C(alert.level, alert.level === "ok" ? "OK" : alert.level === "danger" ? "Riesgo" : "Revision")}
              <div>
                <strong>${escapeHtml(alert.title)}</strong>
                <p>${escapeHtml(alert.detail)}</p>
              </div>
            </article>
          `).join("")}
        </div>
      </section>

      <section class="cx-health-section-026c">
        <div class="cx-health-section-head-026c">
          <div>
            <span class="cx-kicker">Tenants</span>
            <h3>Estado por empresa</h3>
          </div>
          <button class="cx-btn cx-btn-small" type="button" data-nav-view="companies">Ir a empresas</button>
        </div>
        ${riskCompanies.length ? `<div class="cx-health-company-grid-026c">${riskCompanies.map((item) => cxHealthCompanyRow026C(item.company)).join("")}</div>` : `<div class="cx-empty-state">No hay empresas para revisar.</div>`}
      </section>

      <section class="cx-health-section-026c">
        <div class="cx-health-section-head-026c">
          <div>
            <span class="cx-kicker">Diagnostico</span>
            <h3>Errores y respuesta cruda</h3>
          </div>
          <button class="cx-btn cx-btn-small" type="button" data-copy="${escapeHtml(JSON.stringify(state.health || {}))}">Copiar health</button>
        </div>
        ${errors.length ? `
          <div class="cx-health-error-list-026c">
            ${errors.map((error) => `<div>${escapeHtml(error)}</div>`).join("")}
          </div>
        ` : `<div class="cx-empty-state">No hay errores de carga en la ultima lectura.</div>`}
        <pre class="cx-secret">${escapeHtml(JSON.stringify(state.health || {}, null, 2))}</pre>
      </section>
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
            <button class="cx-btn cx-btn-small" data-select-company="${escapeHtml(company.id)}" data-detail-tab="branding" type="button">Ver branding</button>
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
  }

  function renderCompanyDetail(company) {
    const card = el("#companyDetailCard");
    if (!card) return;

    const tabs = [
      ["resumen", "Resumen"],
      ["módulos", "Módulos"],
      ["paquete", "Paquete"],
      ["branding", "Branding"],
      ["accesos", "Accesos"],
      ["reset", "Reset operativo"],
    ];
    const visibleTabKeys = new Set(tabs.map(([key]) => key));
    if (!visibleTabKeys.has(state.activeDetailTab)) {
      state.activeDetailTab = "resumen";
    }
    const users = state.companyUsers.get(company.id);
    const ownerInfo = ownerAccessInfo(users);
    const modulesCount = moduleCodesForCompany(company.id).length;
    const activity = state.companyActivity.get(company.id);
    const activityLabel = activity ? `${activity.totalSignals || 0} registros detectados` : "Sin datos";

    card.innerHTML = `
      <section class="cx-company-command-hero">
        <div class="cx-company-command-main">
          <span class="cx-kicker">Company Command Center</span>
          <h2>${escapeHtml(company.name)}</h2>
          <p>${escapeHtml(company.slug)} - ${escapeHtml(company.id)}</p>
          <div class="cx-command-pill-row">
            ${statusBadge(company.status)}
            <span class="cx-badge">${escapeHtml(packageForCompany(company))}</span>
            <span class="cx-badge">${escapeHtml(modulesCount)} modulos</span>
            <span class="cx-badge">${escapeHtml(activityLabel)}</span>
          </div>
        </div>
        <div class="cx-command-side">
          <div class="cx-command-stat"><span>Acceso maestro</span><strong>${ownerAccessBadge(users)}</strong></div>
          <div class="cx-command-stat"><span>Encargado</span><strong>${escapeHtml(ownerInfo.owner?.email || "No creado")}</strong></div>
          <div class="cx-command-actions">
            ${!isArchivedCompany(company) ? `<a class="cx-btn cx-btn-small" href="/client?company_id=${escapeHtml(company.id)}" target="_blank" rel="noreferrer">Abrir /client</a>` : ""}
            <button class="cx-btn cx-btn-small" data-copy="${escapeHtml(company.id)}" type="button">Copiar ID</button>
            <button class="cx-btn cx-btn-danger cx-btn-small" data-select-company="${escapeHtml(company.id)}" data-detail-tab="reset" type="button">Reset operativo</button>
            ${renderCompanyLifecycleActions(company, true)}
          </div>
        </div>
      </section>
      <div class="cx-detail-tabs">
        ${tabs.map(([key, label]) => `<button class="cx-tab ${state.activeDetailTab === key ? "active" : ""}" data-detail-tab="${key}" type="button">${label}</button>`).join("")}
      </div>
      <div id="companyDetailContent"></div>
    `;

    renderCompanyDetailTab(company);
  }

  /* CLONEXA_BRANDING_STUDIO_RENDER_HELPERS */
  const CX_BRANDING_PALETTES = [
    { name: "CLONEXA Dark", description: "SaaS futurista con energia comercial.", primary_color: "#ff2bd6", secondary_color: "#00ff88", background_color: "#050509", text_color: "#f8fafc", visual_preset: "clonexa_dark", theme_mode: "dark", background_style: "aurora_boreal", card_style: "glass_premium", font_family: "Inter", background_mode: "iridescent", gradient_from: "#ff2bd6", gradient_to: "#00ff88", gradient_extra: "#2563eb", gradient_angle: 135, surface_style: "glass" },
    { name: "Boardroom Dark", description: "Panel serio para gerencia y operaciones.", primary_color: "#38bdf8", secondary_color: "#f8fafc", background_color: "#0b1220", text_color: "#f8fafc", visual_preset: "boardroom_dark", theme_mode: "corporate", background_style: "corporate_dark", card_style: "executive_glass", font_family: "Manrope", background_mode: "solid", gradient_from: "#0f172a", gradient_to: "#164e63", gradient_extra: "#111827", gradient_angle: 140, surface_style: "glass" },
    { name: "Executive Light", description: "Dashboard claro, limpio y corporativo.", primary_color: "#0f172a", secondary_color: "#2563eb", background_color: "#f8fafc", text_color: "#0f172a", visual_preset: "executive_light", theme_mode: "light", background_style: "corporate_light", card_style: "flat_dashboard", font_family: "Inter", background_mode: "gradient", gradient_from: "#f8fafc", gradient_to: "#e0f2fe", gradient_extra: "#dbeafe", gradient_angle: 135, surface_style: "soft" },
    { name: "Classic Office", description: "Empresa tradicional, sobria y estable.", primary_color: "#1f2937", secondary_color: "#b45309", background_color: "#f3f4f6", text_color: "#111827", visual_preset: "classic_office", theme_mode: "classic", background_style: "classic_dashboard", card_style: "classic_panel", font_family: "Montserrat", background_mode: "solid", gradient_from: "#f3f4f6", gradient_to: "#e5e7eb", gradient_extra: "#d6d3d1", gradient_angle: 135, surface_style: "soft" },
    { name: "Neutral Slate", description: "Oscuro sobrio para salas de control.", primary_color: "#94a3b8", secondary_color: "#22d3ee", background_color: "#020617", text_color: "#e5e7eb", visual_preset: "neutral_slate", theme_mode: "dark", background_style: "neutral_slate", card_style: "dark_elevated", font_family: "Sora", background_mode: "gradient", gradient_from: "#020617", gradient_to: "#1e293b", gradient_extra: "#0f766e", gradient_angle: 150, surface_style: "glass" },
    { name: "Retail Neon", description: "Ventas, tiendas y energia de vitrina.", primary_color: "#f97316", secondary_color: "#22c55e", background_color: "#09090b", text_color: "#ffffff", visual_preset: "retail_neon", theme_mode: "dark", background_style: "holografico", card_style: "neon_border", font_family: "Poppins", background_mode: "iridescent", gradient_from: "#f97316", gradient_to: "#22c55e", gradient_extra: "#7c3aed", gradient_angle: 135, surface_style: "neon" },
    { name: "Hospitality Gold", description: "Bares, restaurantes y servicio premium.", primary_color: "#f59e0b", secondary_color: "#ef4444", background_color: "#07310f", text_color: "#fff7ed", visual_preset: "hospitality_gold", theme_mode: "dark", background_style: "neon_profundo", card_style: "executive_glass", font_family: "Manrope", background_mode: "iridescent", gradient_from: "#f59e0b", gradient_to: "#ef4444", gradient_extra: "#14532d", gradient_angle: 120, surface_style: "glass" },
    { name: "Voltage Field", description: "Operacion tecnica, campo y fuerza movil.", primary_color: "#2563eb", secondary_color: "#00ff88", background_color: "#05070a", text_color: "#f8fafc", visual_preset: "field_ops_dark", theme_mode: "dark", background_style: "cyber_grid", card_style: "glass_premium", font_family: "Sora", background_mode: "gradient", gradient_from: "#2563eb", gradient_to: "#00ff88", gradient_extra: "#05070a", gradient_angle: 145, surface_style: "glass" },
    { name: "Minimal Light", description: "Claro minimalista para administracion diaria.", primary_color: "#111827", secondary_color: "#14b8a6", background_color: "#f8fafc", text_color: "#111827", visual_preset: "minimal_light", theme_mode: "light", background_style: "corporate_light", card_style: "soft_solid", font_family: "Inter", background_mode: "gradient", gradient_from: "#f8fafc", gradient_to: "#ccfbf1", gradient_extra: "#dbeafe", gradient_angle: 135, surface_style: "soft" },
  ];

  function cxValidHex(value, fallback = "#000000") {
    const raw = String(value || "").trim();
    return /^#[0-9a-fA-F]{3}$/.test(raw) || /^#[0-9a-fA-F]{6}$/.test(raw) ? raw : fallback;
  }



  function cxBackgroundStyleFromFormRaw(raw = {}) {
    const direct = String(raw.background_style || raw.backgroundStyle || "").trim();
    const mode = String(raw.background_mode || raw.backgroundMode || "").trim();
    const surface = String(raw.surface_style || raw.surfaceStyle || "").trim();

    const allowed = ["aurora_boreal", "neon_profundo", "holografico", "cyber_grid", "corporate_dark", "corporate_light", "classic_dashboard", "neutral_slate"];
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

    const allowed = ["aurora_boreal", "neon_profundo", "holografico", "cyber_grid", "corporate_dark", "corporate_light", "classic_dashboard", "neutral_slate"];

    if (allowed.includes(direct)) return direct;

    const byPreset = {
      clonexa_dark: "aurora_boreal",
      field_ops_dark: "aurora_boreal",
      voltage_field: "aurora_boreal",
      retail_neon: "holografico",
      hospitality_gold: "neon_profundo",
      production_neon: "cyber_grid",
      boardroom_dark: "corporate_dark",
      executive_light: "corporate_light",
      classic_office: "classic_dashboard",
      neutral_slate: "neutral_slate",
      minimal_light: "corporate_light",
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
    const allowedStyles = ["aurora_boreal", "neon_profundo", "holografico", "cyber_grid", "corporate_dark", "corporate_light", "classic_dashboard", "neutral_slate"];
    const style = cxResolveBackgroundStyle(raw);

    const fontRaw = String(raw.font_family || raw.fontFamily || "Inter").trim();
    const allowedFonts = ["Inter", "Manrope", "Sora", "Space Grotesk", "Rajdhani", "Orbitron", "Poppins", "Montserrat"];
    const font = allowedFonts.includes(fontRaw) ? fontRaw : "Inter";

    const cardRaw = String(raw.card_style || raw.cardStyle || "glass_premium").trim();
    const allowedCards = ["glass_premium", "neon_border", "soft_solid", "dark_elevated", "classic_panel", "flat_dashboard", "executive_glass"];
    const card = allowedCards.includes(cardRaw) ? cardRaw : "glass_premium";
    const presetRaw = String(raw.visual_preset || raw.preset_visual || raw.preset || "custom").trim();
    const allowedPresets = ["custom", ...CX_BRANDING_PALETTES.map((item) => item.visual_preset)];
    const visualPreset = allowedPresets.includes(presetRaw) ? presetRaw : "custom";
    const themeRaw = String(raw.theme_mode || raw.mode || "dark").trim();
    const allowedThemes = ["dark", "light", "classic", "corporate"];
    const themeMode = allowedThemes.includes(themeRaw) ? themeRaw : "dark";

    return {
      logo_url: String(raw.logo_url || raw.logoUrl || raw.logo || "").trim(),
      primary_color: cxValidHex(raw.primary_color || raw.color_principal || raw.primaryColor, "#ff2bd6"),
      secondary_color: cxValidHex(raw.secondary_color || raw.color_secundario || raw.secondaryColor, "#00ff88"),
      background_color: cxValidHex(raw.background_color || raw.color_fondo || raw.backgroundColor, "#050509"),
      text_color: cxValidHex(raw.text_color || raw.color_texto || raw.textColor, "#f8fafc"),
      visual_preset: visualPreset,
      background_style: allowedStyles.includes(style) ? style : "aurora_boreal",
      font_family: font,
      card_style: card,
      mode: themeMode,
      theme_mode: themeMode,

      background_mode: style === "holografico" ? "iridescent" : style === "neon_profundo" ? "solid" : "gradient",
      surface_style: card === "neon_border" ? "neon" : card === "soft_solid" || card === "flat_dashboard" || card === "classic_panel" ? "soft" : "glass",
      gradient_from: cxValidHex(raw.gradient_from || raw.primary_color, "#ff2bd6"),
      gradient_to: cxValidHex(raw.gradient_to || raw.secondary_color, "#00ff88"),
      gradient_extra: cxValidHex(raw.gradient_extra || raw.background_color, "#050509"),
      gradient_angle: Number(raw.gradient_angle || 135) || 135,
    };
  }

  function cxBrandingBackground(branding) {
    const b = cxNormalizeBranding(branding);

    if (b.background_style === "corporate_light") {
      return `
        radial-gradient(circle at 0% 0%, ${b.secondary_color}22, transparent 32%),
        radial-gradient(circle at 100% 0%, ${b.primary_color}12, transparent 32%),
        linear-gradient(135deg, ${b.gradient_from}, ${b.gradient_to})
      `;
    }

    if (b.background_style === "corporate_dark") {
      return `
        radial-gradient(circle at 8% 0%, ${b.secondary_color}1f, transparent 30%),
        radial-gradient(circle at 100% 4%, ${b.primary_color}24, transparent 34%),
        linear-gradient(135deg, ${b.background_color}, #020617 72%)
      `;
    }

    if (b.background_style === "classic_dashboard") {
      return `
        linear-gradient(135deg, ${b.gradient_from}, ${b.gradient_to}),
        radial-gradient(circle at 80% 0%, ${b.gradient_extra}44, transparent 35%)
      `;
    }

    if (b.background_style === "neutral_slate") {
      return `
        radial-gradient(circle at 10% 0%, ${b.primary_color}1f, transparent 30%),
        radial-gradient(circle at 90% 0%, ${b.secondary_color}1f, transparent 30%),
        linear-gradient(135deg, #020617, #111827 52%, ${b.background_color})
      `;
    }

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

    if (b.card_style === "classic_panel") {
      return `
        background:linear-gradient(145deg, rgba(255,255,255,.78), rgba(241,245,249,.58));
        color:#111827;
        border:1px solid rgba(15,23,42,.16);
        box-shadow:0 18px 54px rgba(15,23,42,.14);
      `;
    }

    if (b.card_style === "flat_dashboard") {
      return `
        background:linear-gradient(145deg, rgba(255,255,255,.9), rgba(248,250,252,.72));
        color:#0f172a;
        border:1px solid rgba(15,23,42,.12);
        box-shadow:0 14px 40px rgba(15,23,42,.12);
      `;
    }

    if (b.card_style === "executive_glass") {
      return `
        background:linear-gradient(145deg, rgba(15,23,42,.76), rgba(255,255,255,.07));
        border:1px solid rgba(255,255,255,.17);
        box-shadow:0 24px 84px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.1);
        backdrop-filter:blur(20px) saturate(1.18);
      `;
    }

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
      <div class="cx-brand-color-026d">
        <label>${escapeHtml(label)}</label>
        <div>
          <input type="color" value="${escapeHtml(value)}" data-branding-color="${escapeHtml(key)}">
          <input name="${escapeHtml(key)}" data-branding-hex="${escapeHtml(key)}" type="text" value="${escapeHtml(value)}">
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

    const themeOption = (value, label) => `
      <option value="${escapeHtml(value)}" ${b.theme_mode === value ? "selected" : ""}>${escapeHtml(label)}</option>
    `;

    const paletteCards = CX_BRANDING_PALETTES.map((palette, index) => `
      <button class="cx-brand-preset-026d ${b.visual_preset === palette.visual_preset ? "is-active" : ""}" type="button" data-branding-palette="${index}">
        <span class="cx-brand-preset-swatches-026d">
          <i style="background:${escapeHtml(palette.primary_color)}"></i>
          <i style="background:${escapeHtml(palette.secondary_color)}"></i>
          <i style="background:${escapeHtml(palette.background_color)}"></i>
        </span>
        <strong>${escapeHtml(palette.name)}</strong>
        <small>${escapeHtml(palette.description || "")}</small>
      </button>
    `).join("");

    const logoPreview = b.logo_url
      ? `<div class="cx-brand-logo-preview-026d">
          <div>
            ${cxRenderLogo(company, b)}
          </div>
          <span>
            <strong>Logo cargado</strong>
            <small>Puedes reemplazarlo con una URL o archivo nuevo.</small>
          </span>
        </div>`
      : `<div class="cx-brand-empty-026d">Sin logo cargado. Se usara la inicial de la empresa.</div>`;

    return `
      <section class="cx-branding-studio-026d" style="
        --brand-primary:${escapeHtml(b.primary_color)};
        --brand-secondary:${escapeHtml(b.secondary_color)};
        --brand-bg:${escapeHtml(b.background_color)};
        --brand-text:${escapeHtml(b.text_color)};
      ">
        <div class="cx-card-head">
          <div>
            <h2>Branding Studio</h2>
            <p>Configura identidad visual, modo de panel, paletas, tipografia y tarjetas por empresa.</p>
          </div>
          <button class="cx-btn cx-btn-small" type="button" data-open-branding-preview>Vista ampliada</button>
        </div>

        <form id="brandingForm" class="cx-branding-layout-026d">
          <input type="hidden" name="visual_preset" value="${escapeHtml(b.visual_preset)}" />
          <input type="hidden" name="mode" value="${escapeHtml(b.theme_mode)}" />
          <input type="hidden" name="gradient_angle" value="${escapeHtml(b.gradient_angle)}" />

          <div class="cx-branding-main-026d">
            <section class="cx-brand-section-026d cx-brand-section-tight-026d">
              <div>
                <h3>Catalogo visual</h3>
                <p>Elige una base y ajusta colores finos si hace falta.</p>
              </div>
              <div class="cx-brand-preset-grid-026d">${paletteCards}</div>
            </section>

            <section class="cx-brand-section-026d">
              <div>
                <h3>Identidad</h3>
                <p>Logo compacto, sin deformar, aplicado al panel cliente.</p>
              </div>
              <div class="cx-brand-logo-grid-026d">
                ${logoPreview}
                <label class="cx-brand-field-026d">Logo URL
                  <input name="logo_url" type="text" value="${escapeHtml(b.logo_url)}" data-branding-basic placeholder="https://... o /static/logo.png" />
                </label>
                <label class="cx-brand-field-026d">Subir logo
                  <input id="brandingLogoUpload" type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" />
                </label>
              </div>
            </section>

            <section class="cx-brand-section-026d">
              <div>
                <h3>Modo y estructura</h3>
                <p>Define si la empresa se ve futurista, seria, clara o clasica.</p>
              </div>
              <div class="cx-brand-select-grid-026d">
                <label class="cx-brand-field-026d">Modo visual
                  <select name="theme_mode" data-branding-basic>
                    ${themeOption("dark", "Futurista oscuro")}
                    ${themeOption("corporate", "Corporativo serio")}
                    ${themeOption("light", "Claro ejecutivo")}
                    ${themeOption("classic", "Clasico empresarial")}
                  </select>
                </label>
                <label class="cx-brand-field-026d">Fondo del panel
                  <select name="background_style" data-branding-basic>
                    ${styleOption("aurora_boreal", "Aurora moderna")}
                    ${styleOption("neon_profundo", "Oscuro premium")}
                    ${styleOption("holografico", "Tornasol futurista")}
                    ${styleOption("cyber_grid", "Grid tecnico")}
                    ${styleOption("corporate_dark", "Corporativo oscuro")}
                    ${styleOption("corporate_light", "Corporativo claro")}
                    ${styleOption("classic_dashboard", "Panel clasico")}
                    ${styleOption("neutral_slate", "Dashboard sobrio")}
                  </select>
                </label>
                <label class="cx-brand-field-026d">Fuente del panel
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
                <label class="cx-brand-field-026d">Tarjetas
                  <select name="card_style" data-branding-basic>
                    ${cardOption("glass_premium", "Glass premium")}
                    ${cardOption("executive_glass", "Glass ejecutivo")}
                    ${cardOption("neon_border", "Borde neon")}
                    ${cardOption("dark_elevated", "Oscuro elevado")}
                    ${cardOption("soft_solid", "Solido suave")}
                    ${cardOption("flat_dashboard", "Dashboard plano")}
                    ${cardOption("classic_panel", "Panel clasico")}
                  </select>
                </label>
              </div>
            </section>

            <section class="cx-brand-section-026d">
              <div>
                <h3>Sistema de color</h3>
                <p>Paleta principal, fondo, texto y degradado base.</p>
              </div>
              <div class="cx-brand-color-grid-026d">
                ${colorControl("primary_color", "Principal", b.primary_color)}
                ${colorControl("secondary_color", "Secundario", b.secondary_color)}
                ${colorControl("background_color", "Fondo", b.background_color)}
                ${colorControl("text_color", "Texto", b.text_color)}
                ${colorControl("gradient_from", "Gradiente A", b.gradient_from)}
                ${colorControl("gradient_to", "Gradiente B", b.gradient_to)}
                ${colorControl("gradient_extra", "Acento extra", b.gradient_extra)}
              </div>
            </section>
          </div>

          <aside class="cx-branding-preview-rail-026d">
            <div class="cx-branding-preview-card-026d">
              <div class="cx-card-head">
                <div>
                  <h3>Vista previa</h3>
                  <p>Preview en vivo antes de guardar.</p>
                </div>
                <span class="cx-badge">${escapeHtml(b.theme_mode)}</span>
              </div>
              <div id="brandingLivePreview">${cxBrandingPreview(company, b, false)}</div>
              <div class="cx-branding-save-row-026d">
                <button class="cx-btn cx-btn-primary" type="submit">Guardar branding</button>
                <a class="cx-btn" href="/client?company_id=${escapeHtml(company.id)}" target="_blank" rel="noreferrer">Abrir cliente</a>
              </div>
            </div>
          </aside>
        </form>
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
              <h2>Asi quedara el panel cliente</h2>
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
      visual_preset: b.visual_preset,
      background_style: b.background_style,
      font_family: b.font_family,
      card_style: b.card_style,
      mode: b.theme_mode,
      theme_mode: b.theme_mode,
      background_mode: b.background_mode,
      surface_style: b.surface_style,
      gradient_from: b.gradient_from,
      gradient_to: b.gradient_to,
      gradient_extra: b.gradient_extra,
      gradient_angle: b.gradient_angle,
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

      document.querySelectorAll("[data-branding-palette]").forEach((button) => {
        button.classList.toggle("is-active", button === paletteButton);
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
    const activity = state.companyActivity.get(company.id);

    if (tab === "resumen") {
      const ownerInfo = ownerAccessInfo(users);
      node.innerHTML = `
        <div class="cx-command-grid">
          <section class="cx-panel">
            <div class="cx-card-head">
              <div>
                <h3>Identidad SaaS</h3>
                <p>Datos base del tenant y su estado de acceso.</p>
              </div>
              ${statusBadge(company.status)}
            </div>
            <div class="cx-detail-grid">
              <div class="cx-kv"><span>Empresa</span><strong>${escapeHtml(company.name)}</strong></div>
              <div class="cx-kv"><span>Slug</span><strong>${escapeHtml(company.slug)}</strong></div>
              <div class="cx-kv"><span>Plan</span><strong>${escapeHtml(company.plan || "-")}</strong></div>
              <div class="cx-kv"><span>Timezone</span><strong>${escapeHtml(company.timezone || "-")}</strong></div>
              <div class="cx-kv"><span>Paquete</span><strong>${escapeHtml(packageForCompany(company))}</strong></div>
              <div class="cx-kv"><span>Modulos activos</span><strong>${escapeHtml(moduleCodesForCompany(company.id).length)}</strong></div>
            </div>
          </section>

          <section class="cx-panel">
            <div class="cx-card-head">
              <div>
                <h3>Senales operativas</h3>
                <p>Lectura defensiva desde los endpoints ya existentes.</p>
              </div>
              <span class="cx-badge">${activity ? "Detectado" : "Sin datos"}</span>
            </div>
            <div class="cx-detail-grid">
              <div class="cx-kv"><span>Ventas</span><strong>${escapeHtml(activity?.counts?.sales ?? "Sin datos")}</strong></div>
              <div class="cx-kv"><span>Cotizaciones</span><strong>${escapeHtml(activity?.counts?.quotes ?? "Sin datos")}</strong></div>
              <div class="cx-kv"><span>Notas</span><strong>${escapeHtml(activity?.counts?.notes ?? "Sin datos")}</strong></div>
              <div class="cx-kv"><span>Referencias</span><strong>${escapeHtml(activity?.counts?.references ?? "Sin datos")}</strong></div>
              <div class="cx-kv"><span>Total senales</span><strong>${escapeHtml(activity?.totalSignals ?? "Sin datos")}</strong></div>
              <div class="cx-kv"><span>Ultima senal</span><strong>${escapeHtml(activity?.latestLabel || "Sin datos")}</strong></div>
            </div>
          </section>

          <section class="cx-panel">
            <div class="cx-card-head">
              <div>
                <h3>Control rapido</h3>
                <p>Acciones administrativas de esta empresa.</p>
              </div>
              <span class="cx-badge">Seguro</span>
            </div>
            <div class="cx-detail-grid">
              <div class="cx-kv"><span>Acceso maestro</span><strong>${ownerAccessBadge(users)}</strong></div>
              <div class="cx-kv"><span>Encargado</span><strong>${escapeHtml(ownerInfo.owner?.email || "No creado")}</strong></div>
              <div class="cx-kv"><span>Company ID</span><code>${escapeHtml(company.id)}</code></div>
            </div>
            <div class="cx-actions" style="margin-top:14px">
              <button class="cx-btn cx-btn-primary" data-select-company="${escapeHtml(company.id)}" data-detail-tab="módulos" type="button">Gestionar modulos</button>
              <button class="cx-btn cx-btn-danger" data-select-company="${escapeHtml(company.id)}" data-detail-tab="reset" type="button">Reset operativo</button>
            </div>
          </section>
        </div>
      `;
      return;
    }

    if (tab === "usuarios") {
      renderCompanyUsersPanel(node, company, users);
      return;
    }

    if (tab === "reset") {
      node.innerHTML = renderCompanyOperationalResetPanel(company);
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
      if (!state.companyAccessPolicies.has(company.id)) {
        state.companyAccessPolicies.set(company.id, { ...defaultAccessPolicy026G(), loading: true });
        loadCompanyAccessPolicy026G(company.id, true).then(() => {
          if (state.selectedCompanyId === company.id && state.activeDetailTab === "accesos") {
            renderCompanyDetailTab(company);
          }
        });
      }
      if (!state.companySessionPolicies.has(company.id)) {
        state.companySessionPolicies.set(company.id, { ...defaultSessionPolicy026H(), loading: true });
        loadCompanySessionPolicy026H(company.id, true).then(() => {
          if (state.selectedCompanyId === company.id && state.activeDetailTab === "accesos") {
            renderCompanyDetailTab(company);
          }
        });
      }
      if (!state.companyAccessSessions.has(company.id)) {
        state.companyAccessSessions.set(company.id, { sessions: [], loading: true });
        loadCompanyAccessSessions026H(company.id, true).then(() => {
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
      ? `<div class="cx-alert" style="display:block;margin-bottom:14px">Hay mas de un acceso maestro. Se recomienda dejar solo uno.</div>`
      : "";

    const explanation = `
      <div class="cx-empty-state" style="text-align:left;margin-bottom:14px">
        <strong>Usuario dueno / encargado</strong><br>
        Este acceso pertenece al dueno o encargado de la empresa.
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
              <label>Contrasena temporal
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
              <p>${escapeHtml(owner.full_name || "Encargado")} - dueno / encargado</p>
            </div>
            ${ownerAccessBadge(users)}
          </div>
          <div class="cx-detail-grid">
            <div class="cx-kv"><span>Rol</span><strong>${escapeHtml(owner.role || "company_admin")}</strong></div>
            <div class="cx-kv"><span>Estado</span><strong>${escapeHtml(owner.status || "active")}</strong></div>
            <div class="cx-kv"><span>Cambio de clave requerido</span><strong>${owner.must_change_password ? "Si" : "No"}</strong></div>
            <div class="cx-kv"><span>Intentos fallidos</span><strong>${escapeHtml(owner.failed_login_attempts || 0)}</strong></div>
            <div class="cx-kv"><span>Bloqueado hasta</span><strong>${escapeHtml(owner.locked_until || "-")}</strong></div>
            <div class="cx-kv"><span>Ultimo login</span><strong>${escapeHtml(owner.last_login_at || "-")}</strong></div>
            <div class="cx-kv"><span>Ultimo reset</span><strong>${escapeHtml(owner.last_password_reset_at || "-")}</strong></div>
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
            <p>Entrega esta clave al dueno/encargado. Al ingresar podra cambiarla.</p>
            <label>Clave temporal
              <input data-owner-reset-input="${escapeHtml(owner.id)}" type="text" value="${escapeHtml(generateTempPassword(company.slug))}" />
            </label>
            <button class="cx-btn cx-btn-primary" data-reset-password="${escapeHtml(owner.id)}" type="button">Regenerar clave</button>
          </form>
        </aside>
      </div>
    `;
  }

  function masterAccessRows025Y() {
    return state.companies
      .filter((company) => !isArchivedCompany(company))
      .map((company) => {
        const users = state.companyUsers.get(company.id);
        const info = ownerAccessInfo(users);
        return { company, users, info, owner: info.owner || null };
      });
  }

  function masterAccessMatches025Y(row) {
    const filters = state.masterAccessFilters || {};
    const query = String(filters.search || "").toLowerCase().trim();
    const status = filters.status || "all";
    const haystack = [
      row.company.name,
      row.company.slug,
      row.company.id,
      row.owner?.email,
      row.owner?.full_name,
      row.info.status,
      packageForCompany(row.company),
    ].join(" ").toLowerCase();

    if (query && !haystack.includes(query)) return false;
    if (status === "ok") return row.info.level === "ok";
    if (status === "risk") return row.info.level !== "ok";
    if (status === "missing") return row.info.status === "FALTA";
    if (status === "blocked") return row.info.status === "BLOQUEADO";
    if (status === "multiple") return row.info.status === "MULTIPLE";
    return true;
  }

  function masterAccessStats025Y(rows) {
    return {
      total: rows.length,
      ok: rows.filter((row) => row.info.level === "ok").length,
      risk: rows.filter((row) => row.info.level !== "ok").length,
      missing: rows.filter((row) => row.info.status === "FALTA").length,
      blocked: rows.filter((row) => row.info.status === "BLOQUEADO").length,
      multiple: rows.filter((row) => row.info.status === "MULTIPLE").length,
    };
  }

  function masterAccessDate025Y(value) {
    if (!value) return "Sin registro";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("es-CO", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "America/Bogota",
    }).format(date);
  }

  function masterAccessSelectedHtml025Y(company) {
    if (!company) {
      return `<div class="cx-empty-state">Selecciona una empresa para crear o administrar su Acceso Maestro.</div>`;
    }
    const wrapper = document.createElement("div");
    renderCompanyUsersPanel(wrapper, company, state.companyUsers.get(company.id));
    return wrapper.innerHTML;
  }

  function renderUsersGlobalView() {
    const node = el("#usersGlobalView");
    if (!node) return;

    const allRows = masterAccessRows025Y();
    if (!allRows.length) {
      node.innerHTML = `<div class="cx-empty-state">No hay empresas visibles para gestionar Acceso Maestro.</div>`;
      return;
    }

    if (!state.selectedCompanyId) {
      const firstRisk = allRows.find((row) => row.info.level !== "ok") || allRows[0];
      state.selectedCompanyId = firstRisk.company.id;
    }

    const filters = state.masterAccessFilters || {};
    const rows = allRows.filter(masterAccessMatches025Y);
    const stats = masterAccessStats025Y(allRows);
    const selectedCompany = state.companies.find((company) => company.id === state.selectedCompanyId) || allRows[0]?.company || null;

    node.innerHTML = `
      <section class="cx-master-access-command-025Y">
        <div>
          <span class="cx-kicker">Gobierno de acceso SaaS</span>
          <h3>Acceso Maestro por empresa</h3>
          <p>Controla el usuario dueno/encargado del panel cliente. El personal operativo sigue separado dentro de cada tenant.</p>
        </div>
        <div class="cx-master-access-metrics-025Y">
          <div><span>Empresas</span><strong>${escapeHtml(stats.total)}</strong></div>
          <div><span>OK</span><strong>${escapeHtml(stats.ok)}</strong></div>
          <div><span>Revisar</span><strong>${escapeHtml(stats.risk)}</strong></div>
          <div><span>Sin acceso</span><strong>${escapeHtml(stats.missing)}</strong></div>
          <div><span>Bloqueadas</span><strong>${escapeHtml(stats.blocked)}</strong></div>
        </div>
      </section>

      <form class="cx-master-access-filters-025Y" id="masterAccessFilters025Y">
        <label>Buscar empresa o email
          <input name="search" type="search" value="${escapeHtml(filters.search || "")}" placeholder="Mundo Case, admin@empresa.com..." autocomplete="off" />
        </label>
        <label>Estado
          <select name="status">
            <option value="all" ${filters.status === "all" ? "selected" : ""}>Todos</option>
            <option value="risk" ${filters.status === "risk" ? "selected" : ""}>Requieren revision</option>
            <option value="missing" ${filters.status === "missing" ? "selected" : ""}>Sin acceso maestro</option>
            <option value="blocked" ${filters.status === "blocked" ? "selected" : ""}>Bloqueados</option>
            <option value="multiple" ${filters.status === "multiple" ? "selected" : ""}>Multiples</option>
            <option value="ok" ${filters.status === "ok" ? "selected" : ""}>OK</option>
          </select>
        </label>
        <button class="cx-btn cx-btn-primary" type="submit">Filtrar</button>
        <button class="cx-btn cx-btn-ghost" data-master-access-clear type="button">Limpiar</button>
      </form>

      <section class="cx-master-access-layout-025Y">
        <article class="cx-master-access-list-025Y">
          <div class="cx-card-head">
            <div>
              <h3>Empresas</h3>
              <p>${escapeHtml(rows.length)} de ${escapeHtml(allRows.length)} visibles</p>
            </div>
            <span class="cx-badge ${stats.risk ? "cx-badge-warning" : "cx-badge-live"}">${stats.risk ? "Revision pendiente" : "Todo OK"}</span>
          </div>
          <div class="cx-master-access-rows-025Y">
            ${rows.length ? rows.map((row) => {
              const isSelected = selectedCompany && selectedCompany.id === row.company.id;
              const ownerLabel = row.owner
                ? `${row.owner.full_name || "Encargado"} - ${row.owner.email}`
                : "Sin usuario dueno/encargado";
              const levelClass = row.info.level === "ok" ? "is-ok" : row.info.level === "danger" ? "is-danger" : "is-warn";
              return `
                <div class="cx-master-access-row-025Y ${levelClass} ${isSelected ? "is-selected" : ""}">
                  <div>
                    <strong>${escapeHtml(row.company.name)}</strong>
                    <small>${escapeHtml(row.company.slug || truncate(row.company.id, 18))} - ${escapeHtml(packageForCompany(row.company))}</small>
                    <p>${escapeHtml(ownerLabel)}</p>
                  </div>
                  <div class="cx-master-access-row-side-025Y">
                    ${ownerAccessBadge(row.users)}
                    <small>Ultimo login: ${escapeHtml(masterAccessDate025Y(row.owner?.last_login_at))}</small>
                    <div class="cx-actions">
                      <button class="cx-btn cx-btn-small" data-master-access-company="${escapeHtml(row.company.id)}" type="button">Gestionar</button>
                      <button class="cx-btn cx-btn-small" data-open-client="${escapeHtml(row.company.id)}" type="button">Abrir /client</button>
                    </div>
                  </div>
                </div>
              `;
            }).join("") : `<div class="cx-empty-state">No hay empresas para este filtro.</div>`}
          </div>
        </article>

        <aside class="cx-master-access-panel-025Y">
          <div class="cx-card-head">
            <div>
              <span class="cx-kicker">Empresa seleccionada</span>
              <h3>${escapeHtml(selectedCompany?.name || "Sin seleccion")}</h3>
              <p>${escapeHtml(selectedCompany?.slug || "")}</p>
            </div>
            ${selectedCompany ? `<button class="cx-btn cx-btn-small" data-copy="${escapeHtml(selectedCompany.id)}" type="button">Copiar ID</button>` : ""}
          </div>
          ${masterAccessSelectedHtml025Y(selectedCompany)}
        </aside>
      </section>
    `;
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
        Este sera el usuario dueno o encargado que entrara al panel de la empresa.
        El personal operativo se gestiona desde el panel de la empresa.
      </div>
      <label>Nombre del encargado
        <input name="owner_full_name" type="text" placeholder="Empresa Admin" autocomplete="off" />
      </label>
      <label>Email del encargado
        <input name="owner_email" type="email" placeholder="admin@empresa.com" autocomplete="off" />
      </label>
      <label>Contrasena temporal
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
      <span>Empresa: ${escapeHtml(company?.name || "-")}</span><br>
      <span>Slug: ${escapeHtml(company?.slug || "-")}</span><br>
      <span>Email acceso maestro: ${escapeHtml(ownerEmail || "-")}</span><br>
      <span>Clave temporal: <strong>${escapeHtml(temporaryPassword || "-")}</strong></span>
      ${packageWarning ? `<br><span class="cx-badge cx-badge-danger">${escapeHtml(packageWarning)}</span>` : ""}
      ${ownerWarning ? `<br><span class="cx-badge cx-badge-danger">${escapeHtml(ownerWarning)}</span>` : ""}
      <div class="cx-actions" style="margin-top:10px">
        <button class="cx-btn cx-btn-small" data-copy="${escapeHtml(ownerEmail || "")}" type="button">Copiar email</button>
        <button class="cx-btn cx-btn-small" data-copy="${escapeHtml(temporaryPassword || "")}" type="button">Copiar clave</button>
        <a class="cx-btn cx-btn-small" href="/login" target="_blank" rel="noreferrer">Abrir /login</a>
        <a class="cx-btn cx-btn-small" href="/client?company_id=${escapeHtml(company.id)}" target="_blank" rel="noreferrer">Abrir /client</a>
        ${companyId ? `<button class="cx-btn cx-btn-small" data-master-access-company="${escapeHtml(companyId)}" type="button">Abrir Acceso Maestro</button>` : ""}
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
      usersPanelText.textContent = "Control central de duenos/encargados por empresa: crear, regenerar clave, desbloquear y revisar estado.";
    }

    document.querySelectorAll("th, h2, h3, p, button, span, small, label").forEach((node) => {
      const text = node.textContent ? node.textContent.trim() : "";
      if (text === "Usuarios") node.textContent = "Acceso Maestro";
      if (text === "Usuarios de acceso") node.textContent = "Usuario dueno / encargado";
      if (text === "Crear usuario") node.textContent = "Crear acceso maestro";
      if (text === "Reset password") node.textContent = "Regenerar clave";
      if (text === "Contrasena temporal generada" || text === "ContraseÃƒÂ±a temporal generada") node.textContent = "Clave temporal generada";
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
      dashboard: ["Dashboard", "Control SaaS de empresas, actividad, alertas y salud operativa."],
      companies: ["Empresas", "Gestion de tenants, paquetes, modulos y control operativo."],
      users: ["Acceso Maestro", "Usuario dueno/encargado, regeneracion de clave y desbloqueo."],
      packages: ["Paquetes", "CatÃƒÂ¡logo de paquetes SaaS listos para activar."],
      modules: ["Modulos", "Mapa funcional, asignaciones por empresa y pendientes sin pantalla."],
      access: ["Accesos", "Centro operativo de rutas, enlaces por empresa y copiado rapido."],
      landing: ["Landing", "Analitica comercial de visitas, fuentes, campanas y dispositivos."],
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
    renderLandingAnalytics025R();
    renderHealth();
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

      const masterAccessCompany = event.target.closest("[data-master-access-company]");
      if (masterAccessCompany) {
        const companyId = masterAccessCompany.dataset.masterAccessCompany;
        state.selectedCompanyId = companyId;
        state.activeDetailTab = "usuarios";
        await loadCompanyUsers(companyId).catch(() => null);
        setView("users");
        renderUsersGlobalView();
        return;
      }

      const masterAccessClear = event.target.closest("[data-master-access-clear]");
      if (masterAccessClear) {
        state.masterAccessFilters = { search: "", status: "all" };
        renderUsersGlobalView();
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
        const targetForm = generatePasswordForForm.closest("form") || document.querySelector(generatePasswordForForm.dataset.generatePasswordForForm);
        const company = state.companies.find((c) => c.id === state.selectedCompanyId);
        const input = targetForm?.querySelector("input[name='password']");
        if (input) input.value = generateTempPassword(company?.slug || "empresa");
        return;
      }

      if (event.target.closest("[data-open-client]")) {
        window.open("/client", "_blank");
        return;
      }

      const resetDryRun = event.target.closest("[data-reset-dry-run]");
      if (resetDryRun) {
        await runCompanyOperationalReset(resetDryRun.dataset.resetDryRun, false);
        return;
      }

      const resetExecute = event.target.closest("[data-reset-execute]");
      if (resetExecute) {
        await runCompanyOperationalReset(resetExecute.dataset.resetExecute, true);
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

      const refreshLanding = event.target.closest("[data-refresh-landing-analytics]");
      if (refreshLanding) {
        await loadLandingAnalytics025R();
        renderLandingAnalytics025R();
        showToast("Analitica de landing actualizada.");
        return;
      }

      const resetLandingFilters = event.target.closest("[data-reset-landing-filters]");
      if (resetLandingFilters) {
        state.landingFilters = {
          days: "30",
          source: "",
          campaign: "",
          device: "",
        };
        await loadLandingAnalytics025R();
        renderLandingAnalytics025R();
        showToast("Filtros de landing limpiados.");
        return;
      }

      const refreshAccessSessions = event.target.closest("[data-refresh-access-sessions]");
      if (refreshAccessSessions) {
        await refreshCompanySessions026H(refreshAccessSessions.dataset.refreshAccessSessions);
        return;
      }

      const closeAccessSession = event.target.closest("[data-close-access-session]");
      if (closeAccessSession) {
        await closeCompanySession026H(closeAccessSession.dataset.companyId, closeAccessSession.dataset.closeAccessSession);
        return;
      }

      const closeCompanySessions = event.target.closest("[data-close-company-sessions]");
      if (closeCompanySessions) {
        await closeAllCompanySessions026H(closeCompanySessions.dataset.closeCompanySessions);
        return;
      }

      const refreshAdminV2Sessions = event.target.closest("[data-refresh-admin-v2-sessions]");
      if (refreshAdminV2Sessions) {
        await refreshAdminV2Sessions026H();
        return;
      }

      const closeAdminV2Session = event.target.closest("[data-close-admin-v2-session]");
      if (closeAdminV2Session) {
        const sessionKey = closeAdminV2Session.dataset.closeAdminV2Session;
        await closeAdminV2Session026H(sessionKey);
        if (sessionKey === state.adminV2Sessions?.current_session) {
          window.location.href = "/admin-v2/login";
        }
        return;
      }

      const logout = event.target.closest("[data-admin-v2-logout]");
      if (logout) {
        await fetch("/admin-v2/logout", { method: "POST" }).catch(() => null);
        window.location.href = "/admin-v2/login";
        return;
      }
    });

    document.addEventListener("submit", async (event) => {
      const form = event.target.closest("#landingFilters025S");
      if (!form) return;
      event.preventDefault();
      const data = new FormData(form);
      state.landingFilters = {
        days: String(data.get("days") || "30"),
        source: String(data.get("source") || ""),
        campaign: String(data.get("campaign") || ""),
        device: String(data.get("device") || ""),
      };
      await loadLandingAnalytics025R();
      renderLandingAnalytics025R();
      showToast("Landing filtrada.");
    });

    el("#refreshBtn")?.addEventListener("click", async () => {
      state.errors = [];
      await loadAdminDashboard();
      showToast("Datos actualizados.");
    });

    el("#healthRefreshBtn")?.addEventListener("click", async (event) => {
      event.currentTarget.disabled = true;
      try {
        await loadAdminDashboard();
        showToast("Estado del sistema actualizado.");
      } finally {
        event.currentTarget.disabled = false;
      }
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
      if (event.target.matches("#masterAccessFilters025Y")) {
        event.preventDefault();
        const data = new FormData(event.target);
        state.masterAccessFilters = {
          search: String(data.get("search") || "").trim(),
          status: String(data.get("status") || "all"),
        };
        renderUsersGlobalView();
        return;
      }

      if (event.target.matches("#activatePackageForm") && state.selectedCompanyId) {
        event.preventDefault();
        const body = Object.fromEntries(new FormData(event.target).entries());
        await activateCompanyPackage(state.selectedCompanyId, body.package_code);
      }

      if (event.target.matches("#companyQrConfigForm025N") && state.selectedCompanyId) {
        await cxSaveCompanyQrConfig025N(state.selectedCompanyId, event);
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

      if (event.target.matches("#companyIpAccessPolicyForm026G")) {
        const companyId = event.target.dataset.companyId || state.selectedCompanyId;
        await saveCompanyAccessPolicy026G(companyId, event);
      }

      if (event.target.matches("#companySessionPolicyForm026H")) {
        const companyId = event.target.dataset.companyId || state.selectedCompanyId;
        await saveCompanySessionPolicy026H(companyId, event);
      }
    });

    el("#closeTempPasswordModal")?.addEventListener("click", () => el("#temporaryPasswordModal")?.close());
    el("#copyTempPasswordBtn")?.addEventListener("click", async () => {
      await navigator.clipboard.writeText(el("#temporaryPasswordValue")?.textContent || "");
      showToast("Clave temporal copiada.");
    });
  }

  async function bootstrap() {
    ensureAdminV2SecurityControls025R();
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
