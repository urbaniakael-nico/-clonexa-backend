// Consola v2+ · Catálogo: Paquetes (P01–P04, F03, N-13), Módulos globales
// (M01–M03, N-12) y Parámetros de nómina Colombia (N01–N03).
// Lo que guarda usa el MISMO endpoint, método y cuerpo que Admin V2 (pruebas de
// contrato en tests/admin_v2plus_catalog_contract.test.cjs). Sin estilos en línea.
(() => {
  "use strict";

  const API = "/api/v1";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const fold = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const matches = (q, ...fields) => { const words = fold(q).split(" ").filter(Boolean); const hay = fold(fields.join(" ")); return words.every((w) => hay.includes(w) || hay.replace(/ /g, "").includes(w)); };
  const origin = () => (window.location && window.location.origin) || "";

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options, headers: { "Content-Type": "application/json", Accept: "application/json", ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && String(url).startsWith("/admin-v2")) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) throw new Error((data && (typeof data.detail === "string" ? data.detail : data.message)) || `Respuesta ${response.status}`);
    return data;
  }
  const apiGet = (u) => request(u);
  const apiPost = (u, b) => request(u, { method: "POST", body: JSON.stringify(b) });
  const apiPut = (u, b) => request(u, { method: "PUT", body: JSON.stringify(b) });

  // ------------------------------------------------ paquetes (igual que v2)
  const MINI_TYPES = [{ code: "store", label: "Tiendas" }, { code: "sales", label: "Ventas" }, { code: "logistics", label: "Logística" },
    { code: "inventory", label: "Inventarios" }, { code: "other", label: "Otros" }];
  const USER_LIMITS = [1, 3, 5, 10, 15];

  function loginTemplate(type) { return `${origin()}/mini-panel/login?company_id={company_id}&type=${encodeURIComponent(type)}`; }

  // cxPackageMiniPanelDefaultSettings de Admin V2.
  function miniDefaults(raw = {}) {
    const source = raw && typeof raw === "object" ? raw : {};
    const rawTypes = source.types && typeof source.types === "object" ? source.types : {};
    const types = {};
    MINI_TYPES.forEach((def) => {
      const current = rawTypes[def.code] && typeof rawTypes[def.code] === "object" ? rawTypes[def.code] : {};
      const enabled = current.enabled === true;
      const users = Number.isFinite(Number(current.users_allowed)) ? Number(current.users_allowed) : 0;
      types[def.code] = { enabled, label: current.label || def.label, users_allowed: enabled ? (USER_LIMITS.includes(users) ? users : 1) : 0,
        login_template: current.login_template || loginTemplate(def.code) };
    });
    return { enabled: source.enabled === true, types, updated_at: source.updated_at || null };
  }

  // cxPackageMiniPanelFromForm de Admin V2 (desde el estado del builder).
  function miniFromBuilder(mini) {
    const enabled = Boolean(mini && mini.enabled);
    const payload = { enabled, types: {} };
    MINI_TYPES.forEach((def) => {
      const t = (mini && mini.types && mini.types[def.code]) || {};
      const typeOn = t.enabled === true;
      const users = Number(t.users_allowed || 0);
      payload.types[def.code] = { enabled: enabled && typeOn, label: def.label, users_allowed: enabled && typeOn ? (USER_LIMITS.includes(users) ? users : 1) : 0 };
    });
    return payload;
  }

  function isMiniPanelModule(code, modules) {
    const m = arr(modules).find((x) => String(x.code || "").trim() === String(code || "").trim());
    const text = [code, m && m.name, m && m.description].filter(Boolean).join(" ").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    return text.includes("mini_panel") || text.includes("minipanel") || text.includes("mini panel") || text.includes("creacion mini");
  }

  // cxReadPackageBuilderForm de Admin V2 (desde el estado del builder).
  function packagePayload(b) {
    return {
      code: String(b.code || "").trim().toLowerCase().replace(/[^a-z0-9_:-]+/g, "_").replace(/^_+|_+$/g, ""),
      name: String(b.name || "").trim(),
      description: String(b.description || "").trim(),
      is_active: b.is_active === true,
      module_codes: Array.from(new Set(arr(b.module_codes).map((c) => String(c || "").trim()).filter(Boolean))),
    };
  }

  // cxSavePackageFromBuilder: P03/P04 y luego P02, igual que v2.
  async function savePackage(builder, modules) {
    const payload = packagePayload(builder);
    if (!payload.name || !payload.code) throw new Error("Nombre y código del paquete son obligatorios.");
    const saved = builder.id ? await apiPut(`${API}/packages/${builder.id}`, payload) : await apiPost(`${API}/packages`, payload);
    const id = (saved && (saved.id || (saved.package && saved.package.id))) || builder.id;
    if (payload.module_codes.some((c) => isMiniPanelModule(c, modules))) await apiPut(`${API}/packages/${id}/mini-panel-settings`, miniFromBuilder(builder.mini));
    else await apiPut(`${API}/packages/${id}/mini-panel-settings`, miniDefaults({ enabled: false }));
    return saved;
  }

  const packageModuleCodes = (pkg) => arr(pkg && pkg.modules).map((m) => String(typeof m === "string" ? m : (m.code || m.module_code || "")).trim()).filter(Boolean);

  // ------------------------------------------------- módulos (igual que v2)
  function modulePayload(raw) {
    return {
      code: String(raw.code || "").trim().toLowerCase().replace(/[^a-z0-9_]/g, "_"),
      name: String(raw.name || "").trim(),
      description: String(raw.description || "").trim() || null,
      category: String(raw.category || "").trim() || "custom",
      is_active: true,
    };
  }
  const createModule = (raw) => apiPost(`${API}/modules`, modulePayload(raw));                          // M02
  const deleteModule = (code) => request(`${API}/modules/${encodeURIComponent(code)}?confirm=${encodeURIComponent(code)}`, { method: "DELETE" }); // M03

  // ------------------------------------------ parámetros de nómina (v2)
  const payco = {
    load: () => apiGet(`${API}/payroll-co/params`),                                    // N01
    template: (year) => apiGet(`${API}/payroll-co/params/${year}/template`),          // N02
    save: (year, body) => apiPut(`${API}/payroll-co/params/${year}`, body),           // N03
  };
  function paycoValue(field, value) {
    if (field.kind === "json") return JSON.stringify(value ?? (field.key === "extra_holidays" ? [] : null));
    return value ?? "";
  }
  // cxPayCoAdminReadForm048O de Admin V2.
  function paycoBody(fields, get) {
    const params = {};
    arr(fields).forEach((field) => {
      const raw = String(get(field.key) ?? "").trim();
      if (field.kind === "json") params[field.key] = raw ? JSON.parse(raw) : null;
      else if (field.kind === "time") params[field.key] = raw;
      else params[field.key] = Number(raw.replace(",", "."));
    });
    if (params.extra_holidays === null) params.extra_holidays = [];
    const changes = JSON.parse(String(get("changes") || "[]"));
    return { params, changes };
  }

  // ------------------------------------------------------------ estado
  const model = { tab: "paquetes", packages: null, modules: null, usage: null, error: "", notice: "", busy: false,
    pkgQuery: "", modQuery: "", modCategory: "todas", modUse: "todos", builder: null, modal: null,
    payco: { fields: [], years: [], year: null, draft: null, loaded: false, error: "", message: "" } };
  let ctx = null;
  let bound = false;

  const categoryLabel = (c) => (window.CxFicha ? window.CxFicha.categoryLabel(c) : String(c || "General"));

  // ------------------------------------------------------------ dibujo
  function packagesTab() {
    if (!model.packages) return `<p class="vp-loading">Cargando paquetes…</p>`;
    const usage = (model.usage && model.usage.packages) || {};
    const list = arr(model.packages).filter((p) => matches(model.pkgQuery, p.name, p.code, p.description));
    return `<section class="vp-panel vp-section">
      <div class="vp-toolbar"><input class="vp-search" type="search" placeholder="Buscar paquete" value="${h(model.pkgQuery)}" data-vpk-pkg-search aria-label="Buscar paquete">
        <button class="vp-btn vp-btn-primary" type="button" data-vpk-new-package>+ Nuevo paquete</button></div>
      <div class="vp-card-grid vp-zone-scroll">${list.map((p) => `<article class="vp-panel-card ${p.is_active ? "is-on" : ""}">
        <header><b>${h(p.name)}</b><span class="vp-state-pill ${p.is_active ? "is-on" : ""}">${p.is_active ? "Activo" : "Inactivo"}</span></header>
        <small class="vp-mono">${h(p.code)}</small>
        ${p.description ? `<small>${h(p.description)}</small>` : ""}
        <small><b>${h((usage[p.id] && usage[p.id].companies) || 0)}</b> empresa(s) lo usan</small>
        <div class="vp-actions"><button class="vp-btn vp-btn-sm" type="button" data-vpk-edit="${h(p.id)}">Editar</button></div>
      </article>`).join("") || `<div class="vp-empty">Ningún paquete coincide.</div>`}</div>
    </section>`;
  }

  function builderView() {
    const b = model.builder;
    const mods = arr(model.modules);
    const inPkg = new Set(b.module_codes);
    const available = mods.filter((m) => !inPkg.has(m.code) && matches(b.query || "", m.name, m.code, m.category, categoryLabel(m.category)));
    const groups = {};
    available.forEach((m) => { const k = categoryLabel(m.category); (groups[k] = groups[k] || []).push(m); });
    const hasMini = b.module_codes.some((c) => isMiniPanelModule(c, mods));
    const names = Object.fromEntries(mods.map((m) => [m.code, m.name]));
    return `<section class="vp-board" aria-label="Builder de paquete">
      <section class="vp-panel vp-section vp-zone"><h2>Módulos</h2>
        <input class="vp-search" type="search" placeholder="Buscar módulo" value="${h(b.query || "")}" data-vpk-builder-search aria-label="Buscar módulo para el paquete">
        <div class="vp-zone-scroll">${Object.keys(groups).sort().map((k) => `<div class="vp-group"><div class="vp-group-head">${h(k)} <small>${h(groups[k].length)}</small></div>
          <div class="vp-mod-grid">${groups[k].map((m) => `<article class="vp-mod" draggable="true" data-vpk-drag="${h(m.code)}">
            <span class="vp-mod-text"><b>${h(m.name)}</b><small class="vp-mono">${h(m.code)}</small></span>
            <button class="vp-btn vp-btn-sm" type="button" data-vpk-add="${h(m.code)}" aria-label="Añadir ${h(m.name)}">+ Añadir</button></article>`).join("")}</div></div>`).join("")
          || `<div class="vp-empty">No quedan módulos por añadir${b.query ? " con ese filtro" : ""}.</div>`}</div>
      </section>
      <section class="vp-panel vp-section vp-zone vp-drop" data-vpk-drop aria-label="Paquete">
        <div class="vp-zone-head"><h2>${b.id ? "Editar paquete" : "Nuevo paquete"}</h2>
          <button class="vp-btn vp-btn-sm" type="button" data-vpk-builder-close>Cancelar</button>
          <button class="vp-btn vp-btn-sm vp-btn-primary" type="button" data-vpk-builder-save ${model.busy ? "disabled" : ""}>Guardar paquete</button></div>
        <div class="vp-form-grid">
          <label class="vp-field">Código<input data-vpk-field="code" value="${h(b.code)}" ${b.id ? "" : ""} required></label>
          <label class="vp-field">Nombre<input data-vpk-field="name" value="${h(b.name)}" required></label>
          <label class="vp-field">Descripción<input data-vpk-field="description" value="${h(b.description)}"></label>
          <label class="vp-check"><input type="checkbox" data-vpk-field="is_active" ${b.is_active ? "checked" : ""}> Activo</label>
        </div>
        <h3 class="vp-subtitle">Módulos del paquete (${h(b.module_codes.length)})</h3>
        <div class="vp-chip-row vp-zone-scroll vp-pkg-chips">${b.module_codes.map((c) => `<span class="vp-mini-chip">${h(names[c] || c)} <button class="vp-chip-x" type="button" data-vpk-remove="${h(c)}" aria-label="Quitar ${h(names[c] || c)}">×</button></span>`).join("")
          || `<small class="vp-mono-muted">Arrastra módulos aquí o usa "+ Añadir".</small>`}</div>
        ${hasMini ? `<h3 class="vp-subtitle">Mini paneles del paquete</h3>
          <label class="vp-check"><input type="checkbox" data-vpk-mini-enabled ${b.mini.enabled ? "checked" : ""}> Mini panel habilitado</label>
          <div class="vp-form-grid">${MINI_TYPES.map((def) => { const t = b.mini.types[def.code] || {}; return `<div class="vp-field">
            <label class="vp-check"><input type="checkbox" data-vpk-mini-type="${def.code}" ${t.enabled ? "checked" : ""}> ${h(def.label)}</label>
            <select data-vpk-mini-users="${def.code}" aria-label="Usuarios de ${h(def.label)}">${USER_LIMITS.map((n) => `<option value="${n}" ${Number(t.users_allowed) === n ? "selected" : ""}>${n} usuario(s)</option>`).join("")}</select></div>`; }).join("")}</div>` : ""}
        ${model.error ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}
      </section>
    </section>`;
  }

  function modulesTab() {
    if (!model.modules) return `<p class="vp-loading">Cargando módulos…</p>`;
    const usage = (model.usage && model.usage.modules) || {};
    const cats = Array.from(new Set(arr(model.modules).map((m) => categoryLabel(m.category)))).sort();
    const list = arr(model.modules).filter((m) => matches(model.modQuery, m.name, m.code, m.category, categoryLabel(m.category), m.description))
      .filter((m) => model.modCategory === "todas" || categoryLabel(m.category) === model.modCategory)
      .filter((m) => { const u = usage[m.code] || {}; return model.modUse === "todos" || (model.modUse === "en_uso" ? u.companies_on > 0 : !u.companies_on); });
    const groups = {};
    list.forEach((m) => { const k = categoryLabel(m.category); (groups[k] = groups[k] || []).push(m); });
    const cleanup = arr(model.modules).filter((m) => usage[m.code] && usage[m.code].cleanup_candidate);
    return `<section class="vp-panel vp-section">
      <div class="vp-toolbar"><input class="vp-search" type="search" placeholder="Buscar módulo por nombre, código o categoría" value="${h(model.modQuery)}" data-vpk-mod-search aria-label="Buscar módulo">
        <label class="vp-field">Categoría<select data-vpk-mod-category><option value="todas">Todas</option>${cats.map((c) => `<option ${model.modCategory === c ? "selected" : ""}>${h(c)}</option>`).join("")}</select></label>
        <div class="vp-chips">${[["todos", "Todos"], ["en_uso", "Encendidos en alguna empresa"], ["sin_uso", "Sin empresas"]].map(([k, l]) => `<button class="vp-chip ${model.modUse === k ? "is-active" : ""}" type="button" aria-pressed="${model.modUse === k}" data-vpk-mod-use="${k}">${l}</button>`).join("")}</div></div>
      <div class="vp-zone-scroll">${Object.keys(groups).sort().map((k) => `<div class="vp-group"><div class="vp-group-head">${h(k)} <small>${h(groups[k].length)}</small></div>
        <div class="vp-card-grid">${groups[k].map((m) => { const u = usage[m.code] || { packages: [] }; return `<article class="vp-panel-card ${u.companies_on ? "is-on" : ""}">
          <header><b>${h(m.name)}</b><span class="vp-state-pill ${u.companies_on ? "is-on" : ""}">${h(u.companies_on || 0)} empresa(s)</span></header>
          <small class="vp-mono">${h(m.code)}</small>${m.description ? `<small>${h(m.description)}</small>` : ""}
          <div class="vp-chip-row">${arr(u.packages).map((p) => `<span class="vp-mini-chip">${h(p.name || p.code)}</span>`).join("") || `<small class="vp-mono-muted">En ningún paquete</small>`}</div>
        </article>`; }).join("")}</div></div>`).join("") || `<div class="vp-empty">Ningún módulo coincide.</div>`}</div>
    </section>
    <section class="vp-panel vp-section"><h2>Limpieza segura</h2>
      <p class="vp-login-hint">Módulos sin ninguna empresa (en cualquier estado) ni paquete: la misma regla de Admin V2. Eliminar pide escribir el código.</p>
      <div class="vp-chip-row">${cleanup.map((m) => `<span class="vp-mini-chip">${h(m.name)} · <span class="vp-mono">${h(m.code)}</span> <button class="vp-chip-x" type="button" data-vpk-delete="${h(m.code)}" aria-label="Eliminar ${h(m.code)}">×</button></span>`).join("") || `<small class="vp-mono-muted">No hay módulos libres para limpiar.</small>`}</div>
    </section>
    <details class="vp-panel vp-section vp-fold"><summary>Crear módulo global</summary>
      <p class="vp-login-hint">Úsalo solo para módulos nuevos reales. Para pruebas o duplicados, elimina los libres desde Limpieza segura.</p>
      <form class="vp-form-grid" data-vpk-module-form>
        <label class="vp-field">Código<input name="code" required></label><label class="vp-field">Nombre<input name="name" required></label>
        <label class="vp-field">Categoría<input name="category" placeholder="custom"></label><label class="vp-field">Descripción<input name="description"></label>
        <button class="vp-btn vp-btn-primary" type="submit">Crear módulo</button></form>
    </details>`;
  }

  function paycoTab() {
    const s = model.payco;
    if (!s.loaded) return s.error ? `<div class="vp-alert" role="alert"><span>${h(s.error)}</span></div>` : `<p class="vp-loading">Cargando parámetros…</p>`;
    const years = s.years.map((r) => r.year);
    const next = (years.length ? Math.max(...years) : new Date().getFullYear() - 1) + 1;
    const d = s.draft;
    return `<section class="vp-panel vp-section"><h2>Parámetros de ley por año</h2>
      <p class="vp-login-hint">SMMLV, auxilio de transporte, jornada, recargos, aportes y provisiones. Configuración global de Clonexa: aplica a todas las empresas con la normativa colombiana encendida. Actualízalos cada enero.</p>
      ${s.error ? `<div class="vp-alert" role="alert"><span>${h(s.error)}</span></div>` : ""}${s.message ? `<p class="vp-ok-text" role="status">${h(s.message)}</p>` : ""}
      <div class="vp-chips">${years.map((y) => `<button class="vp-chip ${s.year === y ? "is-active" : ""}" type="button" data-vpk-year="${h(y)}">${h(y)}</button>`).join("")}
        <button class="vp-chip" type="button" data-vpk-year-new="${h(next)}">Preparar ${h(next)}</button></div>
      ${d ? `<form class="vp-form-grid" data-vpk-payco-form>${arr(s.fields).map((f) => `<label class="vp-field">${h(f.label)}${f.kind === "json"
        ? `<textarea name="${h(f.key)}" rows="2">${h(paycoValue(f, (d.params || {})[f.key]))}</textarea>` : `<input name="${h(f.key)}" value="${h(paycoValue(f, (d.params || {})[f.key]))}">`}</label>`).join("")}
        <label class="vp-field vp-field-wide">Cambios con fecha dentro del año<textarea name="changes" rows="4">${h(JSON.stringify(d.changes || [], null, 1))}</textarea></label>
        <button class="vp-btn vp-btn-primary" type="submit">Guardar ${h(d.year)}</button></form>` : `<p class="vp-login-hint">Selecciona un año.</p>`}
    </section>`;
  }

  function modal(md) {
    if (!md) return "";
    const err = md.error ? `<div class="vp-alert" role="alert"><span>${h(md.error)}</span></div>` : "";
    const body = md.type === "delete"
      ? `<p class="vp-login-hint">Eliminar el módulo global <b>${h(md.code)}</b>. No está en ninguna empresa ni paquete. No se puede deshacer.</p>${err}
         <label class="vp-field">Escribe exactamente el código: <b>${h(md.code)}</b><input data-vpk-confirm-input autocomplete="off"></label>
         <div class="vp-actions"><button class="vp-btn vp-btn-danger" type="button" data-vpk-confirm-go>Eliminar módulo</button><button class="vp-btn" type="button" data-vpk-modal-close>Cancelar</button></div>`
      : `<p class="vp-login-hint">${h(md.message)}</p>${err}<div class="vp-actions"><button class="vp-btn vp-btn-primary" type="button" data-vpk-confirm-go>${h(md.cta || "Confirmar")}</button><button class="vp-btn" type="button" data-vpk-modal-close>Cancelar</button></div>`;
    return `<div class="vp-modal" data-vpk-modal><div class="vp-panel vp-modal-card" role="dialog" aria-modal="true"><div class="vp-modal-head"><h2>${h(md.title)}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpk-modal-close aria-label="Cerrar">✕</button></div>${body}</div></div>`;
  }

  function view() {
    const tabs = [["paquetes", "Paquetes"], ["modulos", "Módulos"], ["nomina", "Parámetros de nómina"]];
    const pane = model.builder ? builderView() : model.tab === "modulos" ? modulesTab() : model.tab === "nomina" ? paycoTab() : packagesTab();
    return `<header class="vp-head"><div><p class="vp-eyebrow">NÚCLEO CLONEXA · CATÁLOGO</p><h1 class="vp-title">Catálogo</h1></div></header>
      ${model.notice ? `<p class="vp-ok-text" role="status">${h(model.notice)}</p>` : ""}${!model.builder && model.error ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}
      <nav class="vp-chips" role="tablist">${tabs.map(([k, l]) => `<button class="vp-chip ${model.tab === k ? "is-active" : ""}" type="button" role="tab" aria-selected="${model.tab === k}" data-vpk-tab="${k}">${l}</button>`).join("")}</nav>
      ${pane}${modal(model.modal)}`;
  }

  // ------------------------------------------------------------ app
  const FOCUS = ["[data-vpk-pkg-search]", "[data-vpk-mod-search]", "[data-vpk-builder-search]"];
  function draw() {
    if (!ctx || !ctx.active() || !ctx.root()) return;
    const active = document.activeElement;
    const keep = active && active.matches && FOCUS.find((s) => active.matches(s));
    const caret = keep ? active.selectionStart : null;
    ctx.root().innerHTML = view();
    if (keep) { const el = ctx.root().querySelector(keep); if (el) { el.focus(); try { el.setSelectionRange(caret, caret); } catch (_) {} } }
  }

  async function reload() {
    try {
      const [packages, modules, usage] = await Promise.all([apiGet(`${API}/packages`), apiGet(`${API}/modules`), apiGet("/admin-v2/api/catalog/usage").catch(() => null)]);
      model.packages = arr(packages); model.modules = arr(modules); model.usage = usage; model.error = "";
    } catch (error) { model.error = error.message; }
    draw();
  }

  async function loadPayco(year) {
    const s = model.payco;
    try {
      const data = await payco.load();
      s.fields = data.fields || []; s.years = data.years || []; s.loaded = true; s.error = "";
      const y = year || s.year || (s.years.slice(-1)[0] || {}).year;
      s.year = y || null; s.draft = s.years.find((r) => r.year === y) || null;
    } catch (error) { s.error = `No se pudieron cargar los parámetros: ${error.message}`; s.loaded = false; }
    draw();
  }

  function ask(title, message, run, cta) { model.modal = { type: "confirm", title, message, run, cta }; draw(); }

  async function act(run, notice, after) {
    model.busy = true;
    try { await run(); model.modal = null; model.notice = notice; model.error = ""; if (after) await after(); }
    catch (error) { if (model.modal) model.modal.error = error.message; else model.error = error.message; }
    finally { model.busy = false; draw(); }
  }

  async function openBuilder(id) {
    if (!id) { model.builder = { id: "", code: "", name: "", description: "", is_active: true, module_codes: [], mini: miniDefaults({}), query: "" }; draw(); return; }
    try {
      const [pkg, mini] = await Promise.all([apiGet(`${API}/packages/${id}`), apiGet(`${API}/packages/${id}/mini-panel-settings`).catch(() => ({}))]); // F03 + P01
      model.builder = { id, code: pkg.code || "", name: pkg.name || "", description: pkg.description || "", is_active: pkg.is_active !== false,
        module_codes: packageModuleCodes(pkg), mini: miniDefaults(mini && mini.mini_panel ? mini.mini_panel : mini), query: "" };
    } catch (error) { model.error = error.message; }
    draw();
  }

  function addToPackage(code) {
    const b = model.builder;
    if (b && code && !b.module_codes.includes(code)) b.module_codes.push(code);
    draw();
  }

  async function onClick(event) {
    const t = event.target;
    if (!t || !t.closest || !ctx || !ctx.active()) return;
    const tab = t.closest("[data-vpk-tab]");
    if (tab) { model.tab = tab.getAttribute("data-vpk-tab"); model.builder = null; model.notice = ""; draw(); if (model.tab === "nomina" && !model.payco.loaded) loadPayco(); return; }
    if (t.closest("[data-vpk-modal-close]")) { model.modal = null; draw(); return; }
    if (t.closest("[data-vpk-confirm-go]")) {
      const md = model.modal;
      if (md.type === "delete") {
        const typed = (document.querySelector("[data-vpk-confirm-input]") || {}).value || "";
        if (typed !== md.code) { md.error = "Escribe exactamente el código."; draw(); return; }
        act(() => deleteModule(md.code), `Módulo ${md.code} eliminado.`, reload);
      } else if (md.run) md.run();
      return;
    }
    if (t.closest("[data-vpk-new-package]")) { openBuilder(""); return; }
    const edit = t.closest("[data-vpk-edit]");
    if (edit) { openBuilder(edit.getAttribute("data-vpk-edit")); return; }
    if (t.closest("[data-vpk-builder-close]")) { model.builder = null; model.error = ""; draw(); return; }
    const add = t.closest("[data-vpk-add]");
    if (add) { addToPackage(add.getAttribute("data-vpk-add")); return; }
    const rm = t.closest("[data-vpk-remove]");
    if (rm) { model.builder.module_codes = model.builder.module_codes.filter((c) => c !== rm.getAttribute("data-vpk-remove")); draw(); return; }
    if (t.closest("[data-vpk-builder-save]")) {
      const b = model.builder;
      ask(b.id ? "Guardar paquete" : "Crear paquete", `${b.id ? "Guardar los cambios de" : "Crear"} el paquete ${b.name || b.code} con ${b.module_codes.length} módulo(s)? Las empresas que ya lo tienen no cambian hasta volver a activarlo.`,
        () => act(() => savePackage(b, model.modules), `Paquete ${b.name || b.code} guardado.`, async () => { model.builder = null; await reload(); }), "Guardar paquete");
      return;
    }
    const use = t.closest("[data-vpk-mod-use]");
    if (use) { model.modUse = use.getAttribute("data-vpk-mod-use"); draw(); return; }
    const del = t.closest("[data-vpk-delete]");
    if (del) { model.modal = { type: "delete", title: "Eliminar módulo global", code: del.getAttribute("data-vpk-delete") }; draw(); return; }
    const year = t.closest("[data-vpk-year]");
    if (year) { const y = Number(year.getAttribute("data-vpk-year")); model.payco.year = y; model.payco.draft = model.payco.years.find((r) => r.year === y) || null; model.payco.message = ""; draw(); return; }
    const ny = t.closest("[data-vpk-year-new]");
    if (ny) {
      const y = Number(ny.getAttribute("data-vpk-year-new"));
      try { const tpl = await payco.template(y); Object.assign(model.payco, { year: y, draft: { year: y, params: tpl.params, changes: tpl.changes }, message: `Borrador ${y} copiado de ${y - 1}: actualiza SMMLV y auxilio y guarda.`, error: "" }); }
      catch (error) { model.payco.error = `No se pudo preparar ${y}: ${error.message}`; }
      draw();
    }
  }

  function onInput(event) {
    const t = event.target;
    if (!ctx || !ctx.active() || !t || !t.matches) return;
    if (t.matches("[data-vpk-pkg-search]")) model.pkgQuery = t.value;
    else if (t.matches("[data-vpk-mod-search]")) model.modQuery = t.value;
    else if (t.matches("[data-vpk-builder-search]")) model.builder.query = t.value;
    else if (t.matches("[data-vpk-field]") && model.builder) { const k = t.getAttribute("data-vpk-field"); model.builder[k] = t.type === "checkbox" ? t.checked : t.value; return; }
    else return;
    draw();
  }

  function onChange(event) {
    const t = event.target;
    if (!ctx || !ctx.active() || !t || !t.matches) return;
    const b = model.builder;
    if (t.matches("[data-vpk-mod-category]")) { model.modCategory = t.value; draw(); return; }
    if (!b) return;
    if (t.matches("[data-vpk-field]")) { const k = t.getAttribute("data-vpk-field"); b[k] = t.type === "checkbox" ? t.checked : t.value; return; }
    if (t.matches("[data-vpk-mini-enabled]")) { b.mini.enabled = t.checked; return; }
    if (t.matches("[data-vpk-mini-type]")) { const c = t.getAttribute("data-vpk-mini-type"); b.mini.types[c] = { ...(b.mini.types[c] || {}), enabled: t.checked, users_allowed: Number((b.mini.types[c] || {}).users_allowed) || 1 }; return; }
    if (t.matches("[data-vpk-mini-users]")) { const c = t.getAttribute("data-vpk-mini-users"); b.mini.types[c] = { ...(b.mini.types[c] || {}), users_allowed: Number(t.value) }; }
  }

  function onSubmit(event) {
    const form = event.target;
    if (!ctx || !ctx.active() || !form || !form.matches) return;
    if (form.matches("[data-vpk-module-form]")) {
      event.preventDefault();
      const raw = Object.fromEntries(new FormData(form).entries());
      const p = modulePayload(raw);
      if (!p.code || !p.name) { model.error = "Código y nombre son obligatorios."; draw(); return; }
      ask("Crear módulo global", `Crear el módulo ${p.name} (${p.code}) en el catálogo de Clonexa?`, () => act(() => createModule(raw), `Módulo ${p.code} creado.`, reload), "Crear módulo");
      return;
    }
    if (form.matches("[data-vpk-payco-form]")) {
      event.preventDefault();
      const data = new FormData(form);
      const y = model.payco.year;
      let body;
      try { body = paycoBody(model.payco.fields, (k) => data.get(k)); } catch (error) { model.payco.error = `JSON inválido: ${error.message}`; draw(); return; }
      ask(`Guardar parámetros ${y}`, `Guardar los parámetros de nómina ${y}? Aplican a todas las empresas con la normativa colombiana encendida.`,
        () => act(() => payco.save(y, body), `Parámetros ${y} guardados.`, () => loadPayco(y)), `Guardar ${y}`);
    }
  }

  function onDrag(event) {
    const t = event.target;
    if (!ctx || !ctx.active() || !model.builder || !t || !t.closest) return;
    if (event.type === "dragstart") { const card = t.closest("[data-vpk-drag]"); if (card) event.dataTransfer.setData("text/plain", card.getAttribute("data-vpk-drag")); return; }
    const drop = t.closest("[data-vpk-drop]");
    if (!drop) return;
    if (event.type === "dragover") { event.preventDefault(); drop.classList.add("is-over"); }
    if (event.type === "dragleave") drop.classList.remove("is-over");
    if (event.type === "drop") { event.preventDefault(); drop.classList.remove("is-over"); addToPackage(event.dataTransfer.getData("text/plain")); }
  }

  function mount(context) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      ["click"].forEach((e) => document.addEventListener(e, onClick));
      document.addEventListener("input", onInput);
      document.addEventListener("change", onChange);
      document.addEventListener("submit", onSubmit);
      ["dragstart", "dragover", "dragleave", "drop"].forEach((e) => document.addEventListener(e, onDrag));
      bound = true;
    }
    if (context.params && context.params.tab) model.tab = context.params.tab;
    draw();
    if (context.params && context.params.editPackage) openBuilder(context.params.editPackage);
    if (!model.packages) reload();
    if (model.tab === "nomina" && !model.payco.loaded) loadPayco();
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.catalog = { mount };
  window.CxConsoleCatalog = { model, view, miniDefaults, miniFromBuilder, packagePayload, savePackage, isMiniPanelModule, packageModuleCodes,
    modulePayload, createModule, deleteModule, payco, paycoBody, paycoValue, MINI_TYPES };
})();
