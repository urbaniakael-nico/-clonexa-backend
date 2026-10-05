// Consola v2+ · Ficha de empresa (#empresa/{company_id}).
// Sin configuración operativa: en módulos y mini paneles solo se enciende y
// apaga. Cada escritura usa el MISMO endpoint, método y cuerpo que Admin V2
// (pruebas de contrato en tests/admin_v2plus_company_contract.test.cjs).
(() => {
  "use strict";

  const API = "/api/v1";
  const TABS = [["resumen", "Resumen"], ["paquete", "Paquete"], ["modulos", "Módulos y mini paneles"],
    ["accesos", "Usuarios y accesos"], ["bots", "Bots"], ["datos", "Datos"], ["marca", "Marca"], ["auditoria", "Auditoría"]];
  const ACCESS_SCOPES = [["client", "Panel cliente", "/client"], ["mini_panel", "Mini paneles", "/mini-panel"], ["ordering_qr", "QR / pedidos / votacion", "/ordenar"]];
  const SESSION_SCOPES = [["client", "Panel cliente", "/client", 2, 20], ["mini_panel", "Mini paneles", "/mini-panel", 5, 100]];
  const RESET_SCOPES = [
    { code: "commercial", label: "Comercial", detail: "Ventas, facturas, cortes, cotizaciones y notas." },
    { code: "references", label: "Referencias", detail: "Catalogo, sesiones y cierres de produccion." },
    { code: "workforce", label: "Personal y bot", detail: "Personal, marcaciones, sesiones GPS y datos capturados por bot." },
    { code: "payroll", label: "Nomina", detail: "Periodos, items y resultados de nomina." },
    { code: "inventory", label: "Inventario", detail: "Inventario, materiales, solicitudes y operacion de campo." },
  ];
  // Mini paneles: mismos tipos, etiquetas y máximos por defecto que el bloque R6B de Admin V2.
  const PANEL_DEFS = [
    { type: "sales", label: "Ventas" }, { type: "store", label: "Tiendas" }, { type: "inventory", label: "Inventario", defaultMax: 5 },
    { type: "logistics", label: "Logística" }, { type: "call_center", label: "Call Center", defaultMax: 30 },
    { type: "external", label: "Externo", defaultMax: 20 }, { type: "other", label: "Otro", defaultMax: 10 },
  ];
  const QR_MODES = [{ code: "hospitality", includeBar: true }, { code: "voting", includeBar: false }, { code: "generic", includeBar: false }];

  const blank = () => ({ id: "", tab: "resumen", company: null, modules: null, packages: null, users: null, accessPolicy: null,
    sessionPolicy: null, sessions: null, experience: null, brand: null, telegram: null, reset: null, modal: null, error: "", notice: "", busy: false,
    activity: null, audit: null, userQuery: "", sess: { open: false, query: "", page: 1 },
    board: { query: "", filter: "todos", collapsed: {}, draft: null, dirty: false, pick: null, pickQuery: "", error: "" } });
  let model = blank();
  let ctx = null;
  let bound = false;

  // ------------------------------------------------------------ utilidades
  function h(value) {
    return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }
  const origin = () => (window.location && window.location.origin) || "";
  const arr = (value) => (Array.isArray(value) ? value : []);
  const norm = (value) => String(value || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { "Content-Type": "application/json", Accept: "application/json", ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && String(url).startsWith("/admin-v2")) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) throw new Error((data && (typeof data.detail === "string" ? data.detail : data.message)) || `Respuesta ${response.status}`);
    return data;
  }
  const apiGet = (url) => request(url);
  const apiPost = (url, body) => request(url, { method: "POST", body: JSON.stringify(body) });
  const apiPut = (url, body) => request(url, { method: "PUT", body: JSON.stringify(body) });

  function generateTempPassword(seed = "Tenant") {
    return window.CxConsoleCompanies ? window.CxConsoleCompanies.generateTempPassword(seed) : `Clonexa-${seed}-${Math.random().toString(36).slice(2, 6)}!`;
  }

  // -------------------------------------------- lecturas (mismas que v2)
  const reads = {
    companies: () => apiGet(`${API}/companies`),                                                     // C01
    modules: (id) => apiGet(`${API}/companies/${id}/modules?enabled_only=false`),                     // F01
    packages: () => apiGet(`${API}/packages`),                                                       // F02
    users: (id) => apiGet(`${API}/companies/${id}/users`),                                           // U01
    accessPolicy: (id) => apiGet(`${API}/companies/${id}/access-policy`),                            // A01
    sessionPolicy: (id) => apiGet(`${API}/companies/${id}/session-policy`),                          // A03
    sessions: (id) => apiGet(`${API}/companies/${id}/access-sessions?include_closed=true`),          // A05
    experience: (id) => apiGet(`${API}/companies/${id}/experience`),                                 // B01
    brand: (id) => apiGet(`/admin-v2/api/brand/${encodeURIComponent(id)}/summary`),                   // la marca real (Estudio de marca)
    // Nuevos de v2+ (solo lectura, sesión de Admin V2):
    activity: (id) => apiGet(`/admin-v2/api/companies/${encodeURIComponent(id)}/activity`),
    audit: (id) => apiGet(`/admin-v2/api/audit?company_id=${encodeURIComponent(id)}&limit=5`).then((d) => (d && d.entries) || []),
    async telegram(id) {                                                                             // T01 + T02
      const base = await apiGet(`${API}/bots/companies/${id}/telegram`);
      try { return { ...(base || {}), ...((await apiGet(`${API}/company-bots-v1/companies/${id}/telegram/status`)) || {}) }; }
      catch (_) { return base || {}; }
    },
  };

  // ------------------------------------------ escrituras (contrato con v2)
  const writes = {
    // F04
    activatePackage: (id, code) => apiPost(`${API}/companies/${id}/activate-package`, { package_code: code, settings: {} }),
    // M04
    toggleModule: (id, code, action) => apiPost(`${API}/companies/${id}/modules/${code}/${action}`, { settings: {} }),
    // X02 (mismo cuerpo que saveRemote de Admin V2; aquí sí se revisa la respuesta)
    // Conserva además cualquier clave de mini_panel_modules que la consola no conoce.
    saveMiniPanels: (id, config) => apiPost(`${API}/companies/${encodeURIComponent(id)}/modules/mini_panel/activate`, {
      settings: { mini_panel_modules: { ...(config && typeof config === "object" ? config : {}), enabled: config.enabled === true,
        selected_panel: config.selected_panel || "", panels: config.panels || {}, module_names: config.module_names || {}, updated_at: new Date().toISOString() } },
    }),
    // Encender/apagar mesero, cocina o caja: mismo endpoint que el formulario de
    // pedidos por mesero de Admin V2 (W09); solo "segments", completo.
    setSegment: (id, segments, type, on) => apiPost(`${API}/companies/${encodeURIComponent(id)}/modules/waiter_ordering/activate`,
      window.CxFicha.segmentBody(segments, type, on)),
    // U02
    createUser: (id, fullName, email, password) => apiPost(`${API}/companies/${id}/users`, {
      name: fullName, full_name: fullName, email, password, temporary_password: password, role: "company_admin", status: "active", must_change_password: true,
    }),
    // U03
    resetPassword: (id, userId, typed) => apiPost(`${API}/companies/${id}/users/${userId}/reset-password`, typed ? { password: typed } : {}),
    // U04
    unlockUser: (id, userId) => apiPost(`${API}/companies/${id}/users/${userId}/unlock`, {}),
    // U05
    setUserStatus: (id, userId, status) => apiPut(`${API}/companies/${id}/users/${userId}`, { status }),
    // A02
    saveAccessPolicy: (id, body) => apiPut(`${API}/companies/${id}/access-policy`, body),
    // A04
    saveSessionPolicy: (id, body) => apiPut(`${API}/companies/${id}/session-policy`, body),
    // A06 / A07
    closeSession: (id, key) => apiPost(`${API}/companies/${id}/access-sessions/${key}/close`, {}),
    closeAllSessions: (id) => apiPost(`${API}/companies/${id}/access-sessions/close`, {}),
    // T03 (token y nombre recortados, sin flow_code) · T04 · T05 · T06
    saveTelegram: (id, raw) => { const body = { ...raw }; body.token = String(body.token || "").trim(); body.name = String(body.name || "").trim(); delete body.flow_code; return apiPut(`${API}/bots/companies/${id}/telegram`, body); },
    testTelegram: (id) => apiPost(`${API}/bots/companies/${id}/telegram/test`, {}),
    activateWebhook: (id, flowCode) => apiPost(`${API}/company-bots-v1/companies/${id}/telegram/activate-webhook`, { flow_code: flowCode }),
    deactivateTelegram: (id) => apiPost(`${API}/bots/companies/${id}/telegram/deactivate`, {}),
    // R01
    operationalReset: (id, execute, scopes, confirmSlug, confirmText) => apiPost(`${API}/companies/${encodeURIComponent(id)}/operational-reset`, {
      dry_run: !execute, scopes, confirm_slug: confirmSlug, confirm_text: confirmText,
    }),
  };

  // Formularios → cuerpos, igual que Admin V2.
  function ipList(text) {
    return String(text || "").replaceAll(",", "\n").split(/\n+/).map((item) => item.trim()).filter(Boolean);
  }
  function accessPolicyBody(get) {
    const scopes = {};
    ACCESS_SCOPES.forEach(([code]) => { scopes[code] = { enabled: get(`${code}_enabled`) === "on", allowed_ips: ipList(get(`${code}_ips`)) }; });
    return { enabled: get("enabled") === "on", scopes };
  }
  function sessionPolicyBody(get) {
    const scopes = {};
    SESSION_SCOPES.forEach(([code]) => { scopes[code] = { enabled: get(`${code}_enabled`) === "on", max_sessions: Number(get(`${code}_max`) || 1) }; });
    return { enabled: get("enabled") === "on", mode: String(get("mode") || "replace_oldest"), scopes };
  }

  // ------------------------------------------------- módulos y mini paneles
  function moduleRows(modules) {
    return arr(modules).map((row) => {
      const m = row.module && typeof row.module === "object" ? row.module : row;
      return { code: String(m.code || row.module_code || row.code || ""), name: m.name || m.code || "Módulo", enabled: row.enabled !== false, settings: row.settings || {} };
    }).filter((m) => m.code);
  }
  const enabledCodes = (modules) => moduleRows(modules).filter((m) => m.enabled).map((m) => m.code);

  function panelMax(value, type) {
    const def = PANEL_DEFS.find((p) => p.type === type);
    const fallback = Number.isFinite(Number(def && def.defaultMax)) ? Number(def.defaultMax) : 10;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.min(50, Math.max(1, Math.round(parsed))) : Math.min(50, Math.max(1, fallback));
  }

  function miniPanelConfig(modules) {
    const row = moduleRows(modules).find((m) => norm(m.code) === "mini_panel" || norm(m.name).includes("mini_panel") || norm(m.name).includes("creacion_mini"));
    const settings = row ? row.settings : {};
    const config = settings.mini_panel_modules && typeof settings.mini_panel_modules === "object" ? settings.mini_panel_modules
      : (settings.panels && typeof settings.panels === "object" ? settings : null);
    return { present: Boolean(row && row.enabled), config: config ? JSON.parse(JSON.stringify(config)) : { enabled: false, selected_panel: "", panels: {}, module_names: {} } };
  }

  // Encender/apagar un panel (o todos) sin tocar módulos, links ni máximos guardados.
  function toggledPanels(config, companyId, type, on) {
    const next = { enabled: config.enabled === true, selected_panel: config.selected_panel || "", panels: { ...(config.panels || {}) }, module_names: { ...(config.module_names || {}) } };
    if (type === "*") { next.enabled = on; return next; }
    const current = next.panels[type] && typeof next.panels[type] === "object" ? next.panels[type] : {};
    next.panels[type] = { ...current, enabled: on,
      link: current.link || `${origin()}/mini-panel/login?company_id=${encodeURIComponent(companyId)}&type=${encodeURIComponent(type)}`,
      modules: arr(current.modules), max_users: panelMax(current.max_users ?? current.users_allowed, type) };
    if (on && !next.selected_panel) next.selected_panel = type;
    if (!(next.panels[next.selected_panel] && next.panels[next.selected_panel].enabled)) {
      next.selected_panel = (PANEL_DEFS.find((p) => next.panels[p.type] && next.panels[p.type].enabled) || {}).type || type;
    }
    if (on) next.enabled = true;
    return next;
  }

  // ------------------------------------------- links (los mismos de v2)
  function accessLinks(company, modules) {
    const url = (path) => (/^https?:\/\//i.test(path) ? path : `${origin()}${path.startsWith("/") ? path : `/${path}`}`);
    const id = encodeURIComponent(company.id);
    const links = [{ title: "Panel cliente", href: url(`/client?company_id=${id}`) }, { title: "Login empresa", href: url("/login") }];
    const mini = miniPanelConfig(modules).config;
    if (mini.enabled === true) {
      Object.entries(mini.panels || {}).forEach(([type, panel]) => {
        if (!panel || panel.enabled !== true) return;
        const def = PANEL_DEFS.find((p) => p.type === norm(type));
        links.push({ title: `Mini panel ${def ? def.label : type}`, href: url(panel.link || `/mini-panel/login?company_id=${id}&type=${encodeURIComponent(norm(type))}`) });
      });
    }
    const rows = moduleRows(modules);
    const qr = rows.find((m) => m.enabled && ["qr", "mesa_qr", "mesas_qr", "qr_mesas", "hospitality_qr", "voting_qr"].includes(norm(m.code)));
    if (qr) {
      const raw = qr.settings.qr_config || qr.settings.hospitality_qr || qr.settings;
      const mode = QR_MODES.some((m) => m.code === raw.mode) ? raw.mode : "hospitality";
      const includeBar = typeof raw.include_bar === "boolean" ? raw.include_bar : QR_MODES.find((m) => m.code === mode).includeBar;
      const base = (String(raw.base_url || raw.public_base_url || "").trim().replace(/\/+$/, "").replace(/\/ordenar$/i, "")) || origin();
      const point = mode === "voting" ? "Participante 1" : mode === "generic" ? "QR 1" : includeBar ? "Barra" : "Mesa 1";
      links.push({ title: mode === "voting" ? "QR votacion" : "QR publico", href: `${base}/ordenar?company_id=${id}&mesa=${encodeURIComponent(point)}` });
    }
    const codes = new Set(rows.filter((m) => m.enabled).map((m) => norm(m.code)));
    if (["asamblea", "asambleas", "asambleas_votaciones", "assembly"].some((c) => codes.has(c))) links.push({ title: "Asamblea", href: url(`/client?company_id=${id}`) });
    return links;
  }

  // ------------------------------------------------------------ dibujo
  function pulse() {
    const overview = ctx && ctx.overview ? ctx.overview() : null;
    return (overview && arr(overview.companies).find((c) => c.id === model.id)) || null;
  }
  const kindOf = (c) => (window.CxConsoleCompanies && c ? window.CxConsoleCompanies.kindOf(c, ctx && ctx.overview()) : "demo");
  const statusText = (c) => { const s = String((c && c.status) || "active").toLowerCase(); return s === "deleted" || s === "archived" ? "Archivada" : s === "active" ? "Activa" : "Inactiva"; };

  function header(c, p) {
    const codes = model.modules ? enabledCodes(model.modules) : [];
    return `<header class="vp-head vp-ficha-head">
      <div>
        <p class="vp-eyebrow"><a href="#" data-vpf-back>← Empresas</a> · FICHA DE EMPRESA</p>
        <h1 class="vp-title">${h(c.name)}</h1>
        <p class="vp-ficha-meta"><span class="vp-mono">${h(c.slug)}</span> · <b>${h(kindOf(c) === "demo" ? "Demo" : "Registrada")}</b> · ${h(statusText(c))} · Plan ${h((p && p.plan) || c.plan || "—")}
          · <button class="vp-btn vp-btn-sm" type="button" data-vpf-copy="${h(c.id)}" title="${h(c.id)}">ID ${h(String(c.id).slice(0, 8))} ⧉</button></p>
        <p class="vp-ficha-meta">${codes.length ? `${h(codes.length)} módulos activos: ${codes.slice(0, 8).map(h).join(", ")}${codes.length > 8 ? "…" : ""}` : "Sin módulos activos"}</p>
      </div>
      <div class="vp-head-actions">
        <a class="vp-btn" href="/client?company_id=${encodeURIComponent(c.id)}" target="_blank" rel="noopener">Entrar como empresa</a>
        <button class="vp-btn" type="button" data-vpf-links>Copiar links</button>
        <button class="vp-btn" type="button" data-vpf-close-all>Cerrar sesiones</button>
        <button class="vp-btn" type="button" data-vpf-clone>Clonar como demo</button>
      </div>
    </header>`;
  }

  function tabs() {
    return `<nav class="vp-chips vp-ficha-tabs" role="tablist" aria-label="Secciones de la ficha">
      ${TABS.map(([key, label]) => `<button class="vp-chip ${model.tab === key ? "is-active" : ""}" type="button" role="tab" aria-selected="${model.tab === key}" data-vpf-tab="${key}">${h(label)}</button>`).join("")}
    </nav>`;
  }

  const loading = (what) => `<p class="vp-loading">Cargando ${h(what)}…</p>`;
  const since = (iso) => (window.CxConsolePlus ? window.CxConsolePlus.since(iso) : iso || "—");

  function tabPaquete(p) {
    if (!model.packages) return loading("paquetes");
    const list = arr(model.packages);
    return `<section class="vp-panel vp-section"><h2>Paquete</h2>
      <p class="vp-login-hint">Paquete actual: <b>${h((p && p.plan) || "—")}</b>. Activar un paquete enciende sus módulos (mismo endpoint que Admin V2).</p>
      <form class="vp-form-grid" data-vpf-package-form>
        <label class="vp-field">Paquete<select name="package_code" required><option value="">Elige un paquete</option>${list.map((pk) => `<option value="${h(pk.code)}">${h(pk.name || pk.code)}</option>`).join("")}</select></label>
        <button class="vp-btn vp-btn-primary" type="submit">Activar paquete</button>
      </form></section>`;
  }

  // ---------------------------------------------- Fase 2b: vistas nuevas
  const F = () => window.CxFicha;

  function panelsForSummary() {
    const f = F();
    const counts = (model.activity && model.activity.panels) || {};
    const users = (type) => (counts[type] ? counts[type].users : 0);
    const out = [];
    const rest = f.restaurantState(model.modules);
    ["mesero", "cocina", "caja"].forEach((type) => {
      if (rest.waiterOrdering && rest.segments[type] && rest.segments[type].enabled === true) {
        out.push({ on: true, label: f.RESTAURANT_PANELS.find((p) => p.type === type).label, users: users(type),
          link: `${origin()}/mini-panel/${type}/login?company_id=${encodeURIComponent(model.id)}` });
      }
    });
    if (rest.domicilios) out.push({ on: true, label: "Domicilios", users: users("caja"), note: "Lo atiende la Caja" });
    const mini = miniPanelConfig(model.modules);
    if (mini.present && mini.config.enabled === true) {
      f.GENERAL_PANELS.forEach((def) => {
        const panel = mini.config.panels && mini.config.panels[def.type];
        if (panel && panel.enabled === true) {
          out.push({ on: true, label: def.label, users: users(def.type),
            link: panel.link || `${origin()}/mini-panel/login?company_id=${encodeURIComponent(model.id)}&type=${encodeURIComponent(def.type)}` });
        }
      });
    }
    return out;
  }

  function restaurantLinks() {
    const rest = F().restaurantState(model.modules);
    if (!rest.waiterOrdering) return [];
    return ["mesero", "cocina", "caja"].filter((t) => rest.segments[t] && rest.segments[t].enabled === true)
      .map((t) => ({ title: `Panel ${F().RESTAURANT_PANELS.find((p) => p.type === t).label}`, href: `${origin()}/mini-panel/${t}/login?company_id=${encodeURIComponent(model.id)}` }));
  }

  function tabResumen(c, p) {
    if (!F()) return loading("el resumen");
    const links = model.modules ? [...accessLinks(c, model.modules), ...restaurantLinks()] : [];
    return F().summary({ company: c, pulse: p, modules: model.modules, users: model.users, experience: realExperience(),
      activity: model.activity, audit: model.audit, links, since, kind: kindOf(c), panels: model.modules ? panelsForSummary() : [], switches: switchesOn() });
  }

  // Interruptores encendidos de esta empresa (registro único de Interruptores).
  function switchesOn() {
    const R = window.CxSwitchRegistry;
    if (!R || !model.modules) return null;
    if (!R.data()) { R.load().then(() => draw()).catch(() => null); return null; }
    return R.onFor(model.modules);
  }

  // La marca que la empresa ve hoy (publicada o la de siempre) para la franja de identidad.
  function realExperience() {
    const b = model.brand;
    if (!b || !b.colors) return model.experience;
    const base = (model.experience && (model.experience.branding || model.experience.company_branding)) || {};
    return { branding: { ...base, logo_url: b.logo_url || base.logo_url || "", primary_color: b.colors.primary, secondary_color: b.colors.secondary, background_color: b.colors.background } };
  }

  function boardConfig() {
    return model.board.draft || miniPanelConfig(model.modules).config;
  }

  function tabModulos(c) {
    if (!model.modules || !F()) return loading("módulos");
    const mini = miniPanelConfig(model.modules);
    return `<div class="vp-board">
      ${F().modulesZone(model.modules, model.board)}
      ${F().panelsZone({ modules: model.modules, config: boardConfig(), present: mini.present, counts: (model.activity && model.activity.panels) || {},
        rest: F().restaurantState(model.modules), companyId: c.id, origin: origin(), ui: model.board })}
    </div>
    <p class="vp-login-hint">Solo encender, apagar y asignar módulos a los paneles. La configuración operativa (categorías, estaciones, porciones, imágenes, metas) no vive en la consola.
      <a class="vp-link-muted" href="/admin-v2?company_id=${encodeURIComponent(c.id)}">Configuración avanzada en Admin V2</a></p>
    ${F().picker(model.modules, model.board)}`;
  }

  function userRows(users) {
    return users.map((u) => { const active = String(u.status).toLowerCase() === "active"; return `<tr><td><b>${h(u.full_name)}</b><br><small class="vp-mono-muted">${h(u.email)}</small></td><td>${h(u.role)}</td><td>${h(active ? "Activo" : "Inactivo")}${u.locked_until ? " · bloqueado" : ""}</td><td class="vp-mono">${h(u.last_login_at ? since(u.last_login_at) : "Nunca")}</td>
      <td><div class="vp-actions"><input class="vp-search vp-input-sm" placeholder="Clave (opcional)" data-vpf-reset-input="${h(u.id)}" autocomplete="new-password" aria-label="Clave temporal para ${h(u.email)}">
        <button class="vp-btn vp-btn-sm" type="button" data-vpf-reset="${h(u.id)}">Clave temporal</button>
        <button class="vp-btn vp-btn-sm" type="button" data-vpf-unlock="${h(u.id)}">Desbloquear</button>
        <button class="vp-btn vp-btn-sm" type="button" data-vpf-user-status="${h(u.id)}" data-status="${active ? "inactive" : "active"}">${active ? "Desactivar" : "Activar"}</button></div></td></tr>`; }).join("");
  }

  function tabAccesos(c) {
    const users = model.users ? arr(model.users) : null;
    const ap = model.accessPolicy || { enabled: false, scopes: {} };
    const sp = model.sessionPolicy || { enabled: false, mode: "replace_oldest", scopes: {} };
    const shown = users && F() ? users.filter((u) => F().matches(model.userQuery, u.full_name, u.email, u.role)) : users;
    return `<section class="vp-panel vp-section"><h2>Sesiones</h2>
      ${model.activity ? F().sessionsCard(model.activity.sessions, since) : loading("sesiones")}
      ${model.sess.open ? (model.sessions ? F().sessionsTable(model.sessions.sessions, model.sess, since) : loading("el detalle")) : ""}
    </section>
    <section class="vp-panel vp-section"><h2>Usuarios ${users ? `<small class="vp-mono-muted">${h(users.length)}</small>` : ""}</h2>
      ${users && users.length > 8 ? `<input class="vp-search" type="search" placeholder="Buscar usuario por nombre, email o rol" value="${h(model.userQuery)}" data-vpf-user-search aria-label="Buscar usuario">` : ""}
      ${users === null ? loading("usuarios") : shown.length ? `<div class="vp-table-wrap vp-zone-scroll"><table class="vp-table vp-table-compact"><thead><tr><th>Usuario</th><th>Rol</th><th>Estado</th><th>Último ingreso</th><th><span class="sr-only">Acciones</span></th></tr></thead><tbody>
        ${userRows(shown)}</tbody></table></div>` : `<div class="vp-empty">${users.length ? "Ningún usuario coincide." : "Sin usuarios."}</div>`}
      <details class="vp-fold"><summary>Crear acceso maestro</summary>
      <form class="vp-form-grid" data-vpf-user-form>
        <label class="vp-field">Nombre del encargado<input name="full_name" required></label>
        <label class="vp-field">Email<input name="email" type="email" required></label>
        <label class="vp-field">Clave temporal<span class="vp-inline"><input name="password" autocomplete="new-password"><button class="vp-btn vp-btn-sm" type="button" data-vpf-generate>Generar</button></span></label>
        <button class="vp-btn vp-btn-primary" type="submit">Crear acceso maestro</button>
      </form></details>
    </section>
    <details class="vp-panel vp-section vp-fold"><summary>Política de acceso por IP · ${ap.enabled ? "activa" : "inactiva"}</summary>
      ${model.accessPolicy ? `<p class="vp-login-hint">IP actual: <span class="vp-mono">${h(ap.current_ip || "—")}</span></p>` : loading("política IP")}
      <form class="vp-form-grid" data-vpf-access-form>
        <label class="vp-check"><input type="checkbox" name="enabled" ${ap.enabled ? "checked" : ""}> Política activa</label>
        ${ACCESS_SCOPES.map(([code, label]) => { const s = (ap.scopes && ap.scopes[code]) || {}; return `<div class="vp-field"><label class="vp-check"><input type="checkbox" name="${code}_enabled" ${s.enabled ? "checked" : ""}> ${h(label)}</label>
          <textarea name="${code}_ips" rows="3" placeholder="Una IP o rango CIDR por linea">${h(arr(s.allowed_ips).join("\n"))}</textarea></div>`; }).join("")}
        <button class="vp-btn vp-btn-primary" type="submit">Guardar politica IP</button>
      </form>
    </details>
    <details class="vp-panel vp-section vp-fold"><summary>Política de sesión · ${sp.enabled ? "activa" : "inactiva"}</summary>
      <form class="vp-form-grid" data-vpf-session-form>
        <label class="vp-check"><input type="checkbox" name="enabled" ${sp.enabled ? "checked" : ""}> Límite activo</label>
        <label class="vp-field">Modo<select name="mode"><option value="replace_oldest" ${sp.mode !== "block_new" ? "selected" : ""}>Reemplazar la más antigua</option><option value="block_new" ${sp.mode === "block_new" ? "selected" : ""}>Bloquear la nueva</option></select></label>
        ${SESSION_SCOPES.map(([code, label, , def, max]) => { const s = (sp.scopes && sp.scopes[code]) || {}; return `<div class="vp-field"><label class="vp-check"><input type="checkbox" name="${code}_enabled" ${s.enabled ? "checked" : ""}> ${h(label)}</label>
          <input name="${code}_max" type="number" min="1" max="${max}" value="${h(Number(s.max_sessions || def))}"></div>`; }).join("")}
        <button class="vp-btn vp-btn-primary" type="submit">Guardar límites</button>
      </form>
    </details>`;
  }

  function botFlowOptions(selected) {
    const codes = model.modules ? enabledCodes(model.modules) : [];
    const options = [["base", "Base / Workforce"]];
    if (codes.includes("references") && codes.includes("workforce")) options.push(["velvet_references", "Velvet / Referencias producción"]);
    if (codes.includes("gps") || codes.includes("materials") || codes.includes("field")) options.push(["field_operations", "Campo / GPS / Materiales"]);
    if (codes.includes("sales") || codes.includes("stores") || codes.includes("retail")) options.push(["retail_sales", "Retail / Ventas"]);
    if (codes.includes("hospitality") || codes.includes("orders") || codes.includes("tables")) options.push(["hospitality_orders", "Hospitality / Pedidos"]);
    return options.map(([value, label]) => `<option value="${h(value)}" ${value === selected ? "selected" : ""}>${h(label)}</option>`).join("");
  }

  function tabBots(c) {
    const t = model.telegram;
    if (!t) return loading("bot");
    return `<section class="vp-panel vp-section"><h2>Bot de Telegram</h2>
      <div class="vp-kv-grid"><div class="vp-kv"><span>Estado</span><strong>${h(t.configured ? (t.status || "configurado") : "sin configurar")}</strong></div>
        <div class="vp-kv"><span>Webhook</span><strong>${h(t.webhook_mode || "—")}</strong></div>
        <div class="vp-kv"><span>Última validación</span><strong>${h(t.last_validated_at || "Sin validar")}</strong></div>
        <div class="vp-kv"><span>Error</span><strong>${h(t.last_error || "Sin error")}</strong></div></div>
      <form class="vp-form-grid" data-vpf-bot-form>
        <label class="vp-field">Nombre interno<input name="name" value="${h(t.name || `${c.name} Telegram Bot`)}"></label>
        <label class="vp-field">Token Telegram BotFather<input name="token" type="password" autocomplete="off" placeholder="${t.configured ? "Pega un token nuevo solo si quieres reemplazarlo" : "Pega aquí el token de BotFather"}"></label>
        <label class="vp-field">Flujo del bot<select name="flow_code" data-vpf-flow>${botFlowOptions(t.flow_code || "base")}</select></label>
        <div class="vp-actions">
          <button class="vp-btn vp-btn-primary" type="submit">Guardar token</button>
          <button class="vp-btn" type="button" data-vpf-bot-test>Probar conexión</button>
          ${t.configured ? `<button class="vp-btn vp-btn-primary" type="button" data-vpf-bot-webhook>${t.webhook_mode === "dedicated" ? "Reinstalar webhook dedicado" : "Activar webhook dedicado"}</button>
            <button class="vp-btn" type="button" data-vpf-bot-off>Desactivar bot</button>` : ""}
        </div>
      </form>
      <p class="vp-login-hint">El token nunca se muestra: CLONEXA lo guarda por empresa y lo devuelve enmascarado.</p>
    </section>`;
  }

  function tabDatos(c) {
    const r = model.reset;
    const expected = `RESET ${c.slug}`;
    return `<section class="vp-panel vp-section" data-vpf-reset-form><h2>Reset operativo</h2>
      <p class="vp-login-hint">Elimina datos incorporados al tenant sin borrar la empresa, módulos, paquete, branding ni accesos maestros. Primero la simulación; la ejecución exige slug, frase exacta (${h(expected)}) y una confirmación final.</p>
      <div class="vp-form-grid">${RESET_SCOPES.map((s) => `<label class="vp-check"><input type="checkbox" data-vpf-reset-scope="${h(s.code)}" checked> <span><b>${h(s.label)}</b><br><small>${h(s.detail)}</small></span></label>`).join("")}</div>
      <div class="vp-form-grid">
        <label class="vp-field">Slug exacto<input data-vpf-reset-slug autocomplete="off" placeholder="${h(c.slug)}"></label>
        <label class="vp-field">Frase exacta<input data-vpf-reset-text autocomplete="off" placeholder="${h(expected)}"></label>
      </div>
      <div class="vp-actions"><button class="vp-btn" type="button" data-vpf-reset-run="dry" ${model.busy ? "disabled" : ""}>Simular reset</button>
        <button class="vp-btn vp-btn-danger" type="button" data-vpf-reset-run="execute" ${model.busy ? "disabled" : ""}>Ejecutar reset operativo</button></div>
      ${r ? `<div class="vp-reset-result"><p><b>${r.executed ? "Reset ejecutado" : "Simulación lista"}</b> · ${h(r.total_rows ?? 0)} registros. ${r.executed ? "Datos operativos eliminados según alcance." : "Nada se ha eliminado todavía."}</p>
        <ul class="vp-actions-list">${arr(r.tables).filter((t) => t.rows).map((t) => `<li class="vp-action"><b>${h(t.label || t.table)}</b><small>${h(t.scope_label || "")} · ${h(t.table)} · ${h(t.rows)}</small></li>`).join("") || `<li class="vp-action">No hay registros operativos detectados para el alcance seleccionado.</li>`}</ul></div>` : ""}
    </section>
    <section class="vp-panel vp-section"><h2>Eliminar definitivamente</h2>
      <p class="vp-login-hint">Borra la empresa y todos sus datos e imágenes. Demos en cualquier estado; registradas solo archivadas. Las tres empresas vivas nunca.</p>
      <button class="vp-btn vp-btn-danger" type="button" data-vpf-purge>Eliminar definitivo…</button>
    </section>`;
  }

  const THUMBS = [["mesero", "Mesero"], ["cocina", "Cocina"], ["caja", "Caja"]];
  function thumb(c, screen, label, size) {
    const [w, hh] = size === "big" ? [1280, 800] : [390, 780];
    return `<figure class="vp-brand-thumb-fig vp-brand-thumb-${size}"><div class="vp-brand-thumb-box" data-vpf-thumb="${w}x${hh}">
      <iframe class="vp-brand-thumb-frame" title="Vista de ${h(label)} de ${h(c.name)}" loading="lazy" tabindex="-1"
        src="/admin-v2/brand-preview/${encodeURIComponent(c.id)}?marca=actual&screen=${encodeURIComponent(screen)}"></iframe></div>
      <figcaption>${h(label)}</figcaption></figure>`;
  }

  function tabMarca(c) {
    const b = model.brand;
    if (!b) return loading("la marca");
    if (b.error) return `<section class="vp-panel vp-section"><h2>Marca</h2><div class="vp-alert" role="alert"><span>${h(b.error)}</span></div></section>`;
    const colors = b.colors || {};
    const logo = String(b.logo_url || "");
    const showLogo = /^\/brand-media\//.test(logo) || /^data:image\/(png|jpeg|webp);base64,/i.test(logo);
    const when = b.published && b.published.published_at ? new Date(b.published.published_at).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" }) : "";
    const status = b.published ? `<b class="vp-yes">Marca publicada</b> · versión ${h(b.published.version)}${when ? ` · ${h(when)}` : ""}` : `<b>Sin marca publicada</b>, se ve como siempre`;
    const restaurant = THUMBS.filter(([k]) => arr(b.screens).includes(k));
    const swatches = [["primary", "Primario"], ["secondary", "Secundario"], ["background", "Fondo"], ["surface", "Superficie"], ["text", "Texto"], ["text_muted", "Texto secundario"]];
    return `<section class="vp-panel vp-section"><h2>Marca</h2>
      <div class="vp-brand-ficha">
        <div class="vp-brand-ficha-views">${thumb(c, "portal_dashboard", "Panel principal", "big")}
          ${restaurant.length ? `<div class="vp-brand-ficha-small">${restaurant.map(([k, l]) => thumb(c, k, l, "small")).join("")}</div>` : ""}
          <p class="vp-login-hint">Datos de muestra; la marca es la que ve hoy la empresa.</p></div>
        <aside class="vp-brand-ficha-info">
          ${showLogo ? `<img class="vp-brand-logo" src="${h(logo)}" alt="Logo de ${h(c.name)}">` : `<span class="vp-initials">${h(String(c.name || "?").slice(0, 2).toUpperCase())}</span>`}
          <p class="vp-login-hint">${status}</p>
          ${b.draft_pending ? `<div class="vp-alert vp-alert-warn" role="status"><span>Hay un borrador sin publicar en el Estudio de marca.</span></div>` : ""}
          <div class="vp-brand-dots" aria-label="Paleta">${swatches.map(([k, l]) => `<span class="vp-brand-dotc" title="${h(l)} ${h(colors[k] || "")}"><i data-vpf-swatch="${h(colors[k] || "")}"></i><small>${h(l)}</small></span>`).join("")}</div>
          <div class="vp-kv"><span>Tipografía</span><strong>${h(b.font || "Inter")}</strong></div>
          <p class="vp-brand-sample" data-vpf-font="${h(b.font || "Inter")}">Panel operativo · $ 45.000 · Servicios activos</p>
          <button class="vp-btn vp-btn-primary" type="button" data-vpf-brand-studio>Abrir en Estudio de marca</button>
        </aside>
      </div>
    </section>`;
  }

  function modal(md) {
    if (!md) return "";
    const head = (title) => `<div class="vp-modal-head"><h2>${h(title)}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpf-modal-close aria-label="Cerrar">✕</button></div>`;
    const err = md.error ? `<div class="vp-alert" role="alert"><span>${h(md.error)}</span></div>` : "";
    let body = "";
    if (md.type === "confirm") {
      body = `${head(md.title)}<p class="vp-login-hint">${h(md.message)}</p>${err}<div class="vp-actions"><button class="vp-btn vp-btn-primary ${md.danger ? "vp-btn-danger" : ""}" type="button" data-vpf-confirm-go>${h(md.cta || "Confirmar")}</button><button class="vp-btn" type="button" data-vpf-modal-close>Cancelar</button></div>`;
    } else if (md.type === "password") {
      body = `${head("Clave temporal")}<p class="vp-login-hint">Entrégala por un canal seguro: el usuario deberá cambiarla al entrar. No se volverá a mostrar.</p>
        <label class="vp-field">Clave<span class="vp-inline"><input readonly value="${h(md.password)}" data-vpf-copy-value><button class="vp-btn vp-btn-sm" type="button" data-vpf-copy-password>Copiar</button></span></label>`;
    } else if (md.type === "links") {
      body = `${head("Links de acceso")}<div class="vp-actions"><button class="vp-btn vp-btn-sm vp-btn-primary" type="button" data-vpf-copy-all>Copiar todos</button></div>
        <ul class="vp-actions-list">${md.links.map((l) => `<li class="vp-action vp-toggle-row"><b>${h(l.title)}</b><small class="vp-mono">${h(l.href)}</small><button class="vp-btn vp-btn-sm" type="button" data-vpf-copy="${h(l.href)}">Copiar</button></li>`).join("")}</ul>`;
    } else if (md.type === "clone" || md.type === "purge") {
      body = window.CxConsoleCompanies ? window.CxConsoleCompanies.modal(md).replace(/data-vpc-/g, "data-vpf-c-") : "";
      return body;
    }
    return `<div class="vp-modal" data-vpf-modal><div class="vp-panel vp-modal-card" role="dialog" aria-modal="true">${body}</div></div>`;
  }

  function view() {
    const c = model.company;
    if (model.error && !c) return `<div class="vp-alert" role="alert"><strong>No se pudo abrir la ficha</strong><span>${h(model.error)}</span></div><p><a class="vp-btn" href="#" data-vpf-back>← Empresas</a></p>`;
    if (!c) return loading("la ficha");
    const p = pulse();
    const panes = { resumen: () => tabResumen(c, p), paquete: () => tabPaquete(p), modulos: () => tabModulos(c), accesos: () => tabAccesos(c),
      bots: () => tabBots(c), datos: () => tabDatos(c), marca: () => tabMarca(c),
      auditoria: () => `<section class="vp-panel vp-section"><h2>Auditoría</h2><div data-vpa-host></div></section>` };
    return `${header(c, p)}
      ${model.error ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}
      ${model.notice ? `<p class="vp-ok-text" role="status">${h(model.notice)}</p>` : ""}
      ${tabs()}
      <div data-vpf-pane>${(panes[model.tab] || panes.resumen)()}</div>
      ${modal(model.modal)}`;
  }

  function sizeThumbs(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("[data-vpf-thumb]").forEach((box) => {
      const [w, hh] = String(box.getAttribute("data-vpf-thumb")).split("x").map(Number);
      const frame = box.querySelector("iframe");
      const scale = Math.min(1, (box.clientWidth || 300) / w);
      if (!frame) return;
      frame.style.width = `${w}px`;
      frame.style.height = `${hh}px`;
      frame.style.transform = `scale(${scale})`;
      frame.style.transformOrigin = "top left";
      box.style.height = `${Math.round(hh * scale)}px`;
    });
    root.querySelectorAll("[data-vpf-font]").forEach((el) => {
      const f = el.getAttribute("data-vpf-font");
      if (/^[A-Za-z ]{2,30}$/.test(f)) el.style.fontFamily = `'${f}', system-ui, sans-serif`;
    });
  }

  function paintSwatches(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("[data-vpf-swatch]").forEach((el) => {
      const value = el.getAttribute("data-vpf-swatch") || "";
      if (/^#[0-9a-f]{3}([0-9a-f]{3})?$/i.test(value)) el.style.backgroundColor = value; // CSSOM: permitido por la CSP
    });
  }

  function draw() {
    if (!ctx || !ctx.active()) return;
    const root = ctx.root();
    if (!root) return;
    // Los buscadores filtran mientras se escribe: se conserva el foco y el cursor.
    const active = document.activeElement;
    const keep = active && active.matches && FOCUSABLE.find((sel) => active.matches(sel));
    const caret = keep ? active.selectionStart : null;
    root.innerHTML = view();
    paintSwatches(root);
    sizeThumbs(root);
    if (keep) {
      const again = root.querySelector(keep);
      if (again) { again.focus(); try { again.setSelectionRange(caret, caret); } catch (_) {} }
    }
    const audit = model.tab === "auditoria" && model.company && root.querySelector && root.querySelector("[data-vpa-host]");
    if (audit && window.CxConsoleAudit) window.CxConsoleAudit.mountInto(audit, { company_id: model.id });
  }

  // ------------------------------------------------------------ carga
  const TAB_NEEDS = { resumen: ["users", "modules", "experience", "activity", "audit", "brand"], paquete: ["packages", "modules"], modulos: ["modules", "activity"],
    accesos: ["users", "accessPolicy", "sessionPolicy", "activity"], bots: ["telegram", "modules"], datos: [], marca: ["experience", "brand"], auditoria: [] };

  async function ensure(keys, force = false) {
    const id = model.id;
    await Promise.all(keys.map(async (key) => {
      if (!force && model[key] !== null) return;
      try { model[key] = key === "packages" ? await reads.packages() : await reads[key](id); }
      catch (error) { model[key] = key === "telegram" ? { error: error.message } : (Array.isArray(model[key]) ? model[key] : []); model.error = `No se pudo cargar ${key}: ${error.message}`; }
    }));
    if (model.id === id) draw();
  }

  async function open(id) {
    if (model.id !== id) model = blank();
    model.id = id;
    draw();
    try {
      const list = await reads.companies();
      model.company = arr(list).find((c) => c.id === id) || null;
      if (!model.company) model.error = "Empresa no encontrada.";
    } catch (error) { model.error = error.message; }
    draw();
    if (model.company) ensure(TAB_NEEDS[model.tab] || []);
  }

  // ------------------------------------------------------------ acciones
  function ask(title, message, run, opts = {}) {
    model.modal = { type: "confirm", title, message, run, ...opts };
    draw();
  }

  async function act(run, notice, reload = []) {
    model.busy = true;
    try {
      const result = await run();
      model.modal = null;
      model.notice = notice;
      model.error = "";
      if (reload.length) await ensure(reload, true);
      return result;
    } catch (error) {
      if (model.modal) model.modal.error = error.message; else model.error = error.message;
      return null;
    } finally {
      model.busy = false;
      draw();
    }
  }

  async function copy(text, label = "Copiado.") {
    try { await navigator.clipboard.writeText(text); if (ctx) ctx.toast(label); } catch (_) { if (ctx) ctx.toast("No se pudo copiar."); }
  }

  async function onClick(event) {
    const t = event.target;
    if (!t || !t.closest || !ctx || !ctx.active()) return;
    const id = model.id;
    const c = model.company;
    const tab = t.closest("[data-vpf-tab]");
    if (tab) { model.tab = tab.getAttribute("data-vpf-tab"); model.notice = ""; draw(); ensure(TAB_NEEDS[model.tab] || []); return; }
    if (t.closest("[data-vpf-back]")) { event.preventDefault(); if (ctx.goCompanies) ctx.goCompanies(); return; }
    if (t.closest("[data-vpf-brand-studio]") && model.company && window.CxConsolePlus) {
      window.CxConsolePlus.setView("brand", { companyId: model.id, companyName: model.company.name });
      return;
    }
    if (t.closest("[data-vpf-modal-close]") || t.closest("[data-vpf-c-close]")) { model.modal = null; model.board.pick = null; draw(); return; }
    const cp = t.closest("[data-vpf-copy]");
    if (cp) { copy(cp.getAttribute("data-vpf-copy")); return; }
    if (t.closest("[data-vpf-copy-password]")) { copy((document.querySelector("[data-vpf-copy-value]") || {}).value || "", "Clave copiada."); return; }
    if (t.closest("[data-vpf-copy-all]")) { copy(model.modal.links.map((l) => `${l.title}: ${l.href}`).join("\n"), "Links copiados."); return; }
    if (t.closest("[data-vpf-confirm-go]")) { const md = model.modal; if (md && md.run) md.run(); return; }
    if (t.closest("[data-vpf-generate]")) { const form = t.closest("form"); if (form) form.elements.password.value = generateTempPassword(form.elements.email.value || "empresa"); return; }
    if (!c) return;
    if (t.closest("[data-vpf-links]")) {
      if (model.modules === null) await ensure(["modules"]);
      model.modal = { type: "links", links: accessLinks(c, model.modules) };
      draw();
      return;
    }
    if (t.closest("[data-vpf-close-all]")) {
      ask("Cerrar sesiones", "Cerrar todas las sesiones activas de esta empresa?", () => act(() => writes.closeAllSessions(id), "Sesiones cerradas.", model.sessions ? ["sessions"] : []), { cta: "Cerrar todas", danger: true });
      return;
    }
    if (t.closest("[data-vpf-clone]")) { model.modal = { type: "clone", company: c, password: generateTempPassword(`${c.slug}-demo`) }; draw(); return; }
    if (t.closest("[data-vpf-purge]")) {
      model.modal = { type: "purge", company: c, plan: null };
      draw();
      try { model.modal.plan = await window.CxConsoleCompanies.purge(id, true); } catch (error) { model.modal.error = error.message; }
      draw();
      return;
    }
    if (t.closest("[data-vpf-c-purge-go]")) {
      const typed = (document.querySelector("[data-vpf-c-confirm-input]") || {}).value || "";
      if (typed !== c.name) { model.modal.error = "Escribe el nombre exacto de la empresa."; draw(); return; }
      const done = await act(() => window.CxConsoleCompanies.purge(id, false, typed), `${c.name} eliminada.`);
      if (done && ctx.goCompanies) ctx.goCompanies();
      return;
    }
    const mod = t.closest("[data-vpf-module]");
    if (mod) {
      const code = mod.getAttribute("data-vpf-module");
      const action = mod.getAttribute("data-action");
      ask(action === "activate" ? "Encender módulo" : "Apagar módulo", `${action === "activate" ? "Encender" : "Apagar"} el módulo ${code} en ${c.name}?`,
        () => act(() => writes.toggleModule(id, code, action), `Módulo ${code} ${action === "activate" ? "encendido" : "apagado"}.`, ["modules"]));
      return;
    }
    if (boardClick(t, c)) return;
    const reset = t.closest("[data-vpf-reset]");
    if (reset) {
      const userId = reset.getAttribute("data-vpf-reset");
      const typed = ((document.querySelector(`[data-vpf-reset-input="${userId}"]`) || {}).value || "").trim();
      ask("Clave temporal", "Generar una clave temporal para este usuario? La actual deja de servir.", async () => {
        const data = await act(() => writes.resetPassword(id, userId, typed), "Clave regenerada.", ["users"]);
        if (data) { model.modal = { type: "password", password: data.temporary_password || data.password || typed || "No devuelta" }; draw(); }
      });
      return;
    }
    const unlock = t.closest("[data-vpf-unlock]");
    if (unlock) { ask("Desbloquear", "Desbloquear este acceso?", () => act(() => writes.unlockUser(id, unlock.getAttribute("data-vpf-unlock")), "Acceso desbloqueado.", ["users"])); return; }
    const us = t.closest("[data-vpf-user-status]");
    if (us) {
      const status = us.getAttribute("data-status");
      ask(status === "active" ? "Activar acceso" : "Desactivar acceso", `${status === "active" ? "Activar" : "Desactivar"} este acceso?`,
        () => act(() => writes.setUserStatus(id, us.getAttribute("data-vpf-user-status"), status), "Estado de acceso actualizado.", ["users"]));
      return;
    }
    const close = t.closest("[data-vpf-close-session]");
    if (close) { ask("Cerrar sesión", "Cerrar esta sesión?", () => act(() => writes.closeSession(id, close.getAttribute("data-vpf-close-session")), "Sesión cerrada.", ["sessions"])); return; }
    if (t.closest("[data-vpf-refresh-sessions]")) { ensure(["sessions"], true); return; }
    if (t.closest("[data-vpf-bot-test]")) { act(async () => { model.telegram = await writes.testTelegram(id); }, "Prueba enviada a Telegram."); return; }
    if (t.closest("[data-vpf-bot-webhook]")) {
      const flow = String(((document.querySelector("[data-vpf-flow]") || {}).value) || (model.telegram && model.telegram.flow_code) || "base").trim();
      ask("Webhook dedicado", `Activar el webhook dedicado con el flujo ${flow}?`, () => act(async () => { model.telegram = await writes.activateWebhook(id, flow); }, "Webhook dedicado activado."));
      return;
    }
    if (t.closest("[data-vpf-bot-off]")) { ask("Desactivar bot", "Desactivar el bot de Telegram de esta empresa?", () => act(async () => { model.telegram = await writes.deactivateTelegram(id); }, "Bot Telegram desactivado."), { danger: true }); return; }
    const run = t.closest("[data-vpf-reset-run]");
    if (run) {
      const box = t.closest("[data-vpf-reset-form]");
      const scopes = Array.from(box.querySelectorAll("[data-vpf-reset-scope]")).filter((i) => i.checked).map((i) => i.getAttribute("data-vpf-reset-scope"));
      const confirmSlug = String((box.querySelector("[data-vpf-reset-slug]") || {}).value || "").trim();
      const confirmText = String((box.querySelector("[data-vpf-reset-text]") || {}).value || "").trim();
      const execute = run.getAttribute("data-vpf-reset-run") === "execute";
      const plan = resetPlan(c, scopes, confirmSlug, confirmText, execute);
      if (plan.error) { model.error = plan.error; draw(); return; }
      const go = () => act(async () => { model.reset = await writes.operationalReset(id, execute, scopes, confirmSlug, confirmText); }, execute ? "Reset operativo ejecutado." : "Simulación de reset lista.");
      if (execute) ask("Confirmación final", plan.confirm, go, { cta: "Ejecutar reset", danger: true }); else go();
    }
  }

  // ------------------------------------------------- tablero (Fase 2b)
  const FOCUSABLE = ["[data-vpf-mod-search]", "[data-vpf-pick-search]", "[data-vpf-sess-search]", "[data-vpf-user-search]"];

  function moduleByCode(code) {
    return window.CxFicha.moduleList(model.modules).find((m) => m.code === code) || null;
  }

  function editDraft(change) {
    const before = model.board.draft || miniPanelConfig(model.modules).config;
    const result = change(before);
    if (result && result.error) { model.board.error = result.error; draw(); return false; }
    model.board.draft = result && result.config ? result.config : result;
    model.board.dirty = true;
    model.board.error = "";
    draw();
    return true;
  }

  function assign(type, code) {
    const f = window.CxFicha;
    return editDraft((cfg) => f.assignModule(cfg, type, moduleByCode(code), { companyId: model.id, origin: origin() }));
  }

  function boardClick(t, c) {
    const f = window.CxFicha;
    if (!f) return false;
    const id = model.id;
    const sw = t.closest("[data-vpf-switches]");
    if (sw) { window.CxConsolePlus.setView("switches", { companyId: model.id }); return true; }
    const goto = t.closest("[data-vpf-goto]");
    if (goto) { model.tab = goto.getAttribute("data-vpf-goto"); draw(); ensure(TAB_NEEDS[model.tab] || []); return true; }
    const filter = t.closest("[data-vpf-mod-filter]");
    if (filter) { model.board.filter = filter.getAttribute("data-vpf-mod-filter"); draw(); return true; }
    const group = t.closest("[data-vpf-group]");
    if (group) { const key = group.getAttribute("data-vpf-group"); model.board.collapsed[key] = !model.board.collapsed[key]; draw(); return true; }
    const pick = t.closest("[data-vpf-pick]");
    if (pick) { model.board.pick = pick.getAttribute("data-vpf-pick"); model.board.pickQuery = ""; draw(); return true; }
    const add = t.closest("[data-vpf-assign]");
    if (add) { if (assign(model.board.pick, add.getAttribute("data-vpf-assign"))) { model.board.pick = null; draw(); } return true; }
    const remove = t.closest("[data-vpf-unassign]");
    if (remove) { editDraft((cfg) => f.unassignModule(cfg, remove.getAttribute("data-vpf-unassign"), remove.getAttribute("data-code"))); return true; }
    const toggle = t.closest("[data-vpf-panel-toggle]");
    if (toggle) {
      const on = toggle.getAttribute("data-on") === "1";
      editDraft((cfg) => f.setPanelEnabled(cfg, toggle.getAttribute("data-vpf-panel-toggle"), on, { companyId: id, origin: origin() }));
      return true;
    }
    if (t.closest("[data-vpf-discard]")) { model.board.draft = null; model.board.dirty = false; model.board.error = ""; draw(); return true; }
    if (t.closest("[data-vpf-save-panels]")) {
      const draft = model.board.draft;
      ask("Guardar mini paneles", `Guardar los cambios de los mini paneles de ${c.name}? (paneles encendidos y módulos asignados)`, async () => {
        const done = await act(() => writes.saveMiniPanels(id, draft), "Mini paneles guardados.", ["modules"]);
        if (done !== null) { model.board.draft = null; model.board.dirty = false; draw(); }
      });
      return true;
    }
    const seg = t.closest("[data-vpf-segment]");
    if (seg) {
      const type = seg.getAttribute("data-vpf-segment");
      const on = seg.getAttribute("data-on") === "1";
      const label = (f.RESTAURANT_PANELS.find((p) => p.type === type) || {}).label || type;
      const segments = f.restaurantState(model.modules).segments;
      ask(on ? `Encender panel ${label}` : `Apagar panel ${label}`,
        `${on ? "Encender" : "Apagar"} el panel ${label} en ${c.name}? Usa el mismo interruptor que Admin V2 (pedidos por mesero); no cambia la configuración del restaurante.`,
        () => act(() => writes.setSegment(id, segments, type, on), `Panel ${label} ${on ? "encendido" : "apagado"}.`, ["modules"]));
      return true;
    }
    if (t.closest("[data-vpf-sessions-toggle]")) { model.sess.open = !model.sess.open; draw(); if (model.sess.open) ensure(["sessions"], true); return true; }
    const page = t.closest("[data-vpf-sess-page]");
    if (page) { model.sess.page = Number(page.getAttribute("data-vpf-sess-page")) || 1; draw(); return true; }
    return false;
  }

  function onInput(event) {
    const t = event.target;
    if (!ctx || !ctx.active() || !t || !t.matches) return;
    if (t.matches("[data-vpf-mod-search]")) model.board.query = t.value;
    else if (t.matches("[data-vpf-pick-search]")) model.board.pickQuery = t.value;
    else if (t.matches("[data-vpf-sess-search]")) { model.sess.query = t.value; model.sess.page = 1; }
    else if (t.matches("[data-vpf-user-search]")) model.userQuery = t.value;
    else return;
    draw();
  }

  function onDragStart(event) {
    const card = event.target && event.target.closest && event.target.closest("[data-vpf-drag]");
    if (!card || !ctx || !ctx.active()) return;
    event.dataTransfer.setData("text/plain", card.getAttribute("data-vpf-drag"));
    event.dataTransfer.effectAllowed = "copy";
  }
  function onDragOver(event) {
    const drop = event.target && event.target.closest && event.target.closest("[data-vpf-drop]");
    if (!drop) return;
    event.preventDefault();
    drop.classList.add("is-over");
  }
  function onDragLeave(event) {
    const drop = event.target && event.target.closest && event.target.closest("[data-vpf-drop]");
    if (drop) drop.classList.remove("is-over");
  }
  function onDrop(event) {
    const drop = event.target && event.target.closest && event.target.closest("[data-vpf-drop]");
    if (!drop || !ctx || !ctx.active()) return;
    event.preventDefault();
    drop.classList.remove("is-over");
    assign(drop.getAttribute("data-vpf-drop"), event.dataTransfer.getData("text/plain"));
  }

  // Mismas reglas que runCompanyOperationalReset de Admin V2.
  function resetPlan(company, scopes, confirmSlug, confirmText, execute) {
    if (!scopes.length) return { error: "Selecciona al menos un alcance para el reset." };
    const expected = `RESET ${company.slug}`;
    if (execute && (confirmSlug !== company.slug || confirmText !== expected)) return { error: `Confirmacion invalida. Escribe ${expected}.` };
    return { confirm: `Vas a borrar datos operativos de ${company.name}. La empresa, modulos, accesos y branding se conservan. Continuar?` };
  }

  async function onSubmit(event) {
    const form = event.target;
    if (!ctx || !ctx.active() || !form || !form.matches || !model.company) return;
    const id = model.id;
    const data = new FormData(form);
    const get = (name) => data.get(name);
    if (form.matches("[data-vpf-package-form]")) {
      event.preventDefault();
      const code = String(get("package_code") || "");
      if (!code) return;
      ask("Activar paquete", `Activar el paquete ${code} en ${model.company.name}? Enciende sus módulos.`, () => act(() => writes.activatePackage(id, code), "Paquete activado.", ["modules"]));
    } else if (form.matches("[data-vpf-user-form]")) {
      event.preventDefault();
      const fullName = String(get("full_name") || "").trim();
      const email = String(get("email") || "").trim().toLowerCase();
      const password = String(get("password") || "").trim() || generateTempPassword(email || "empresa");
      if (!fullName || !email) { model.error = "Nombre y email del encargado son requeridos."; draw(); return; }
      ask("Crear acceso maestro", `Crear el acceso de ${email}?`, async () => {
        const done = await act(() => writes.createUser(id, fullName, email, password), "Acceso maestro creado correctamente.", ["users"]);
        if (done) { model.modal = { type: "password", password }; draw(); }
      });
    } else if (form.matches("[data-vpf-access-form]")) {
      event.preventDefault();
      const body = accessPolicyBody(get);
      ask("Política de acceso por IP", "Guardar la política de acceso por IP? Una regla mal puesta puede dejar a la empresa sin entrar.", () => act(async () => { model.accessPolicy = await writes.saveAccessPolicy(id, body); }, "Politica IP guardada para esta empresa."));
    } else if (form.matches("[data-vpf-session-form]")) {
      event.preventDefault();
      const body = sessionPolicyBody(get);
      ask("Política de sesión", "Guardar los límites de sesiones?", () => act(async () => { model.sessionPolicy = await writes.saveSessionPolicy(id, body); }, "Limites de sesiones guardados.", ["sessions"]));
    } else if (form.matches("[data-vpf-bot-form]")) {
      event.preventDefault();
      const raw = Object.fromEntries(data.entries());
      ask("Guardar bot", "Guardar el bot de Telegram de esta empresa?", () => act(async () => { model.telegram = await writes.saveTelegram(id, raw); }, "Token de Telegram guardado para esta empresa."));
    } else if (form.matches("[data-vpf-c-clone-form]")) {
      event.preventDefault();
      const raw = Object.fromEntries(data.entries());
      const done = await act(() => window.CxConsoleCompanies.cloneDemo(id, raw), `${raw.name} creada como demo.`);
      if (done) { model.modal = { type: "password", password: done.temporary_password }; draw(); }
    }
  }

  function mount(context, companyId) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("submit", onSubmit);
      document.addEventListener("input", onInput);
      document.addEventListener("dragstart", onDragStart);
      document.addEventListener("dragover", onDragOver);
      document.addEventListener("dragleave", onDragLeave);
      document.addEventListener("drop", onDrop);
      bound = true;
    }
    if (companyId && companyId !== model.id) { open(companyId); return; }
    draw();
  }

  function refreshPulse() {
    // El pulso solo cambia el Resumen y el encabezado: no se redibujan formularios.
    if (ctx && ctx.active() && model.tab === "resumen" && !model.modal) draw();
  }

  window.CxConsoleCompany = { mount, refreshPulse, view, writes, reads, accessLinks, miniPanelConfig, toggledPanels, accessPolicyBody, sessionPolicyBody,
    resetPlan, moduleRows, botFlowOptions, get model() { return model; }, set model(value) { model = value; } };
})();
