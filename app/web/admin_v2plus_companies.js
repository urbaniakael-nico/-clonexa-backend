// Consola v2+ · Empresas: pestañas Registradas y Demos, buscador, filtros de
// Admin V2 y semáforo del Centro de mando.
// - Crear, cambiar estado y archivar usan EXACTAMENTE los mismos endpoints,
//   métodos y cuerpos que Admin V2 (pruebas de contrato en
//   tests/admin_v2plus_companies_contract.test.cjs).
// - Cambiar de tipo, clonar como demo y eliminar definitivo son nuevos
//   (/admin-v2/api/companies/{id}/kind | clone-demo | purge).
(() => {
  "use strict";

  const API = "/api/v1";
  const FILTERS = [["visible", "Visibles"], ["all", "Todas"], ["active", "Activas"], ["inactive", "Inactivas"], ["archived", "Archivadas"]];
  const TABS = [["registrada", "Registradas"], ["demo", "Demos"]];

  const model = { companies: [], packages: [], loaded: false, loading: false, error: "", tab: "registrada", filter: "visible",
    query: "", modal: null, busy: false, notice: "" };

  // ------------------------------------------------------------ utilidades
  function h(value) {
    return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { "Content-Type": "application/json", Accept: "application/json", ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { if (window.location) window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) {
      const error = new Error((data && (typeof data.detail === "string" ? data.detail : data.message)) || `Respuesta ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }
  const apiGet = (url) => request(url);
  const apiPost = (url, body) => request(url, { method: "POST", body: JSON.stringify(body) });
  const apiPut = (url, body) => request(url, { method: "PUT", body: JSON.stringify(body) });
  const apiPatch = (url, body) => request(url, { method: "PATCH", body: JSON.stringify(body) });

  // Igual que generateTempPassword de Admin V2.
  function generateTempPassword(seed = "Tenant") {
    const part = Math.random().toString(36).replace(/[^a-z0-9]/g, "").slice(2, 6) || "a7k2";
    const clean = String(seed || "Tenant").toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "").slice(0, 18) || "tenant";
    return `Clonexa-${clean}-${part}!`;
  }

  // ------------------------------------------------- acciones (contrato v2)
  // C01
  function loadCompanies() { return apiGet(`${API}/companies`); }
  // F02
  function loadPackages() { return apiGet(`${API}/packages`); }

  function createdId(created) {
    const c = (created && (created.company || created.data)) || created || {};
    return c.id || c.company_id || (created && (created.id || created.company_id)) || "";
  }

  // C02 + F04 + C03 (+ tipo, nuevo): mismo orden y cuerpos que createCompany de Admin V2.
  async function createCompanyFlow(raw) {
    const ownerFullName = String(raw.owner_full_name || "").trim();
    const ownerEmail = String(raw.owner_email || "").trim().toLowerCase();
    const ownerPassword = String(raw.owner_password || "").trim() || generateTempPassword(raw.slug || raw.name || "empresa");
    const companyBody = { name: raw.name, slug: raw.slug, timezone: raw.timezone || "America/Bogota", plan: raw.plan || "standard" };
    if (!companyBody.name || !companyBody.slug) throw new Error("Nombre y slug son requeridos para crear empresa.");
    if (!ownerFullName || !ownerEmail) throw new Error("Nombre y email del Acceso Maestro son requeridos.");
    const created = await apiPost(`${API}/companies`, companyBody);
    const companyId = createdId(created);
    if (!companyId) throw new Error("La empresa fue creada, pero no se pudo detectar company_id.");
    const warnings = [];
    if (raw.package_code) {
      try { await apiPost(`${API}/companies/${companyId}/activate-package`, { package_code: raw.package_code, settings: {} }); }
      catch (error) { warnings.push(`La empresa fue creada, pero no se pudo activar el paquete: ${error.message}`); }
    }
    let ownerOk = true;
    try {
      await apiPost(`${API}/companies/${companyId}/users`, { email: ownerEmail, full_name: ownerFullName, role: "company_admin", password: ownerPassword, status: "active" });
    } catch (error) {
      ownerOk = false;
      warnings.push(`La empresa fue creada, pero no se pudo crear el acceso maestro: ${error.message}`);
    }
    // Nuevo en v2+: una empresa sin tipo es demo; "Registrada" se marca aquí.
    if (raw.kind === "registrada") {
      try { await changeKind(companyId, "registrada", true); }
      catch (error) { warnings.push(`La empresa quedó como demo: ${error.message}`); }
    }
    return { companyId, ownerEmail, temporaryPassword: ownerOk ? ownerPassword : "", warnings };
  }

  // C04-C06: el mismo encadenamiento de Admin V2 (ver hallazgo 1 del inventario).
  async function updateCompanyStatus(companyId, status) {
    if (!companyId || !status) return undefined;
    const body = { status };
    const attempts = [
      () => apiPatch(`${API}/companies/${companyId}/status`, body),
      () => apiPatch(`${API}/companies/${companyId}`, body),
      () => apiPut(`${API}/companies/${companyId}`, body),
    ];
    let lastError = null;
    for (const attempt of attempts) {
      try { return await attempt(); } catch (error) { lastError = error; }
    }
    throw lastError || new Error("No existe endpoint seguro para actualizar status de empresa.");
  }

  // Archivar = estado "deleted" tras escribir el slug exacto (igual que v2).
  function archiveCompany(company, typedSlug) {
    if (typedSlug !== company.slug) return Promise.reject(new Error("Escribe el slug exacto para archivar."));
    return updateCompanyStatus(company.id, "deleted");
  }

  // Nuevos (solo v2+).
  function changeKind(companyId, kind, confirm = false) {
    return apiPost(`/admin-v2/api/companies/${encodeURIComponent(companyId)}/kind`, { kind, confirm: Boolean(confirm) });
  }
  function cloneDemo(companyId, body) {
    return apiPost(`/admin-v2/api/companies/${encodeURIComponent(companyId)}/clone-demo`, body);
  }
  function purge(companyId, dryRun, confirmName = "") {
    return apiPost(`/admin-v2/api/companies/${encodeURIComponent(companyId)}/purge`, dryRun ? { dry_run: true } : { dry_run: false, confirm_name: confirmName });
  }

  // ------------------------------------------------------------ datos
  function companyStatus(c) { return String((c && c.status) || "active").toLowerCase(); }
  function isArchived(c) { const s = companyStatus(c); return s === "deleted" || s === "archived"; }

  function kindOf(c, overview) {
    const stored = c && c.settings_json && typeof c.settings_json === "object" ? String(c.settings_json.kind || "").toLowerCase() : "";
    if (stored === "demo" || stored === "registrada") return stored;
    const pulse = overviewMap(overview)[c.id];
    return pulse && pulse.kind ? pulse.kind : "demo";
  }

  function overviewMap(overview) {
    const out = {};
    (overview && Array.isArray(overview.companies) ? overview.companies : []).forEach((c) => { out[c.id] = c; });
    return out;
  }

  // Mismo criterio que filteredCompanies de Admin V2.
  function byFilter(list, filter) {
    if (filter === "active") return list.filter((c) => companyStatus(c) === "active");
    if (filter === "inactive") return list.filter((c) => companyStatus(c) === "inactive");
    if (filter === "archived") return list.filter(isArchived);
    if (filter === "all") return list;
    return list.filter((c) => !isArchived(c));
  }

  function visibleCompanies(companies, overview, { tab = "registrada", filter = "visible", query = "" } = {}) {
    const q = String(query || "").trim().toLowerCase();
    const inTab = (companies || []).filter((c) => kindOf(c, overview) === tab);
    return byFilter(inTab, filter).filter((c) => !q || `${c.name} ${c.slug}`.toLowerCase().includes(q));
  }

  // ------------------------------------------------------------ dibujo
  const STATE_LABELS = { conectada: "Conectada", activa_hoy: "Activa hoy", sin_actividad_hoy: "Sin actividad hoy", dormida: "Dormida", riesgo: "En riesgo", inactiva: "Inactiva" };

  function stateCell(c, pulse) {
    if (isArchived(c)) return `<span class="vp-state"><span class="vp-dot vp-dot-inactiva" aria-hidden="true"></span><b>Archivada</b></span>`;
    if (!pulse) return `<span class="vp-mono-muted">—</span>`;
    return `<span class="vp-state"><span class="vp-dot vp-dot-${h(pulse.state)}" aria-hidden="true"></span><span><b>${h(STATE_LABELS[pulse.state] || pulse.state)}</b><br><small class="vp-mono-muted">${h(pulse.state_reason || "")}</small></span></span>`;
  }

  function rowActions(c, kind) {
    const id = h(c.id);
    const status = companyStatus(c);
    const out = [`<a class="vp-btn vp-btn-sm" href="#empresa/${encodeURIComponent(c.id)}" data-vpc-open="${id}">Ficha</a>`];
    if (isArchived(c)) out.push(`<button class="vp-btn vp-btn-sm" type="button" data-vpc-status="${id}" data-status="active">Reactivar</button>`);
    else {
      out.push(status === "active"
        ? `<button class="vp-btn vp-btn-sm" type="button" data-vpc-status="${id}" data-status="inactive">Desactivar</button>`
        : `<button class="vp-btn vp-btn-sm" type="button" data-vpc-status="${id}" data-status="active">Reactivar</button>`);
      out.push(`<button class="vp-btn vp-btn-sm" type="button" data-vpc-archive="${id}">Archivar</button>`);
    }
    out.push(kind === "demo"
      ? `<button class="vp-btn vp-btn-sm" type="button" data-vpc-kind="${id}" data-kind="registrada">Pasar a registrada</button>`
      : `<button class="vp-btn vp-btn-sm" type="button" data-vpc-kind="${id}" data-kind="demo">Pasar a demo</button>`);
    out.push(`<button class="vp-btn vp-btn-sm" type="button" data-vpc-clone="${id}">Clonar como demo</button>`);
    if (kind === "demo" || isArchived(c)) out.push(`<button class="vp-btn vp-btn-sm vp-btn-danger" type="button" data-vpc-purge="${id}">Eliminar definitivo</button>`);
    return out.join("");
  }

  function companiesTable(list, overview) {
    if (!list.length) return `<div class="vp-empty" data-vpc-empty>Ninguna empresa coincide.</div>`;
    const pulse = overviewMap(overview);
    return `<div class="vp-table-wrap"><table class="vp-table">
      <thead><tr><th>Empresa</th><th>Estado</th><th>Plan</th><th>Semáforo</th><th><span class="sr-only">Acciones</span></th></tr></thead>
      <tbody>${list.map((c) => {
        const kind = kindOf(c, overview);
        return `<tr data-vpc-row="${h(c.id)}">
          <td><div class="vp-company"><span><b>${h(c.name)}</b><small>${h(c.slug)} · ${h(String(c.id).slice(0, 8))}</small></span></div></td>
          <td>${h(isArchived(c) ? "Archivada" : companyStatus(c) === "active" ? "Activa" : "Inactiva")}</td>
          <td>${h((pulse[c.id] && pulse[c.id].plan) || c.plan || "—")}</td>
          <td>${stateCell(c, pulse[c.id])}</td>
          <td><div class="vp-actions">${rowActions(c, kind)}</div></td>
        </tr>`;
      }).join("")}</tbody></table></div>`;
  }

  function counts(companies, overview) {
    const out = { registrada: 0, demo: 0 };
    (companies || []).forEach((c) => { out[kindOf(c, overview)] += 1; });
    return out;
  }

  function createForm(packages) {
    const options = (packages || []).map((p) => `<option value="${h(p.code)}">${h(p.name || p.code)}</option>`).join("");
    return `<form class="vp-panel vp-section vp-form" data-vpc-create>
      <h2>Crear empresa</h2>
      <div class="vp-form-grid">
        <label class="vp-field">Nombre<input name="name" required maxlength="200"></label>
        <label class="vp-field">Slug<input name="slug" required maxlength="120" pattern="[a-z0-9-]+"></label>
        <label class="vp-field">Zona horaria<input name="timezone" value="America/Bogota"></label>
        <label class="vp-field">Plan<input name="plan" value="standard"></label>
        <label class="vp-field">Paquete<select name="package_code"><option value="">Sin paquete</option>${options}</select></label>
        <fieldset class="vp-field vp-kind-pick"><legend>Tipo</legend>
          <label><input type="radio" name="kind" value="demo" checked> Demo</label>
          <label><input type="radio" name="kind" value="registrada"> Registrada</label>
        </fieldset>
        <label class="vp-field">Dueño · nombre<input name="owner_full_name" required maxlength="200"></label>
        <label class="vp-field">Dueño · email<input name="owner_email" type="email" required></label>
        <label class="vp-field">Clave temporal<span class="vp-inline"><input name="owner_password" autocomplete="new-password"><button class="vp-btn vp-btn-sm" type="button" data-vpc-generate>Generar</button></span></label>
      </div>
      <div class="vp-actions"><button class="vp-btn vp-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>Crear empresa</button></div>
    </form>`;
  }

  function view(m, overview) {
    const list = visibleCompanies(m.companies, overview, m);
    const n = counts(m.companies, overview);
    return `
      <header class="vp-head">
        <div><p class="vp-eyebrow">NÚCLEO CLONEXA · EMPRESAS</p><h1 class="vp-title">Empresas</h1></div>
        <div class="vp-head-actions"><button class="vp-btn" type="button" data-vpc-reload>Refrescar</button>
          <button class="vp-btn vp-btn-primary" type="button" data-vpc-new>+ Nueva empresa</button></div>
      </header>
      ${m.error ? `<div class="vp-alert" role="alert"><span>${h(m.error)}</span></div>` : ""}
      ${m.notice ? `<p class="vp-ok-text" role="status">${h(m.notice)}</p>` : ""}
      ${m.showCreate ? createForm(m.packages) : ""}
      <section class="vp-panel vp-section">
        <div class="vp-chips" role="tablist" aria-label="Tipo de empresa">
          ${TABS.map(([key, label]) => `<button class="vp-chip ${m.tab === key ? "is-active" : ""}" type="button" role="tab" aria-selected="${m.tab === key}" data-vpc-tab="${key}">${label}<b>${h(n[key])}</b></button>`).join("")}
        </div>
        <div class="vp-toolbar">
          <input class="vp-search" type="search" placeholder="Buscar por nombre o slug" value="${h(m.query)}" data-vpc-search aria-label="Buscar empresa">
          <div class="vp-chips" role="group" aria-label="Filtrar por estado">
            ${FILTERS.map(([key, label]) => `<button class="vp-chip ${m.filter === key ? "is-active" : ""}" type="button" aria-pressed="${m.filter === key}" data-vpc-filter="${key}">${label}</button>`).join("")}
          </div>
        </div>
        <div data-vpc-table>${m.loaded ? companiesTable(list, overview) : `<p class="vp-loading">Cargando empresas…</p>`}</div>
      </section>
      ${modal(m.modal)}`;
  }

  // ------------------------------------------------------------ modales
  function modal(md) {
    if (!md) return "";
    const c = md.company || {};
    const head = (title) => `<div class="vp-modal-head"><h2>${h(title)}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpc-close aria-label="Cerrar">✕</button></div>`;
    const err = md.error ? `<div class="vp-alert" role="alert"><span>${h(md.error)}</span></div>` : "";
    let body = "";
    if (md.type === "archive") {
      body = `${head("Archivar empresa")}<p class="vp-login-hint">Archivará ${h(c.name)} y bloqueará su acceso. No se eliminan datos.</p>${err}
        <label class="vp-field">Escribe el slug exacto: <b>${h(c.slug)}</b><input data-vpc-confirm-input autocomplete="off"></label>
        <button class="vp-btn vp-btn-primary" type="button" data-vpc-archive-go>Archivar empresa</button>`;
    } else if (md.type === "kind") {
      body = `${head(md.kind === "registrada" ? "Pasar a registrada" : "Pasar a demo")}${err}
        <p class="vp-login-hint">${md.kind === "registrada"
          ? `${h(c.name)} pasará a contar en los totales del Centro de mando y solo se podrá eliminar si está archivada.`
          : `${h(c.name)} dejará de contar en los totales y se podrá eliminar en cualquier estado.`}</p>
        <button class="vp-btn vp-btn-primary" type="button" data-vpc-kind-go>Confirmar</button>`;
    } else if (md.type === "clone") {
      body = `${head(`Clonar ${c.name || ""} como demo`)}${err}
        <p class="vp-login-hint">Copia solo configuración: paquete y módulos, marca, localización, CRM, carta (sin imágenes) y roles. Nunca pedidos, ventas, clientes, empleados, nómina, inventario, sesiones, usuarios, bots ni tokens.</p>
        <form class="vp-form-grid" data-vpc-clone-form>
          <label class="vp-field">Nombre de la demo<input name="name" required value="${h(`${c.name || ""} Demo`)}"></label>
          <label class="vp-field">Slug<input name="slug" required value="${h(`${c.slug || "empresa"}-demo`)}"></label>
          <label class="vp-field">Dueño · nombre<input name="owner_full_name" required></label>
          <label class="vp-field">Dueño · email<input name="owner_email" type="email" required></label>
          <label class="vp-field">Clave temporal<input name="owner_password" value="${h(md.password || "")}" minlength="8" required></label>
          <button class="vp-btn vp-btn-primary" type="submit">Clonar como demo</button>
        </form>`;
    } else if (md.type === "purge") {
      const plan = md.plan;
      body = `${head("Eliminar definitivamente")}${err}
        ${plan ? `<p class="vp-login-hint">Se borrarán <b>${h(plan.total_rows)}</b> filas de ${h(plan.tables.length)} tablas (incluidas sus imágenes) y la empresa. No se puede deshacer.</p>
          <ul class="vp-actions-list vp-purge-list">${plan.tables.map((t) => `<li class="vp-action"><b>${h(t.table)}</b><small>${h(t.rows)} fila(s)${t.images ? " · imágenes" : ""}</small></li>`).join("")}</ul>
          <label class="vp-field">Escribe el nombre exacto: <b>${h(c.name)}</b><input data-vpc-confirm-input autocomplete="off"></label>
          <button class="vp-btn vp-btn-danger" type="button" data-vpc-purge-go>Eliminar definitivamente</button>`
          : `<p class="vp-loading">Simulando…</p>`}`;
    } else if (md.type === "result") {
      body = `${head(md.title || "Listo")}<p class="vp-login-hint">${h(md.message || "")}</p>
        ${md.password ? `<label class="vp-field">Clave temporal<span class="vp-inline"><input readonly value="${h(md.password)}" data-vpc-copy-value><button class="vp-btn vp-btn-sm" type="button" data-vpc-copy>Copiar</button></span></label>` : ""}
        ${(md.warnings || []).map((w) => `<div class="vp-alert" role="alert"><span>${h(w)}</span></div>`).join("")}`;
    }
    return `<div class="vp-modal" data-vpc-modal><div class="vp-panel vp-modal-card" role="dialog" aria-modal="true">${body}</div></div>`;
  }

  // ------------------------------------------------------------ app
  let ctx = null;  // { root, overview(), toast, reloadOverview }

  function draw() {
    if (!ctx || !ctx.root()) return;
    ctx.root().innerHTML = view(model, ctx.overview());
  }

  async function reload() {
    model.loading = true;
    try {
      const [companies, packages] = await Promise.all([loadCompanies(), model.packages.length ? model.packages : loadPackages().catch(() => [])]);
      model.companies = Array.isArray(companies) ? companies : [];
      model.packages = Array.isArray(packages) ? packages : (packages && packages.items) || [];
      model.loaded = true;
      model.error = "";
    } catch (error) {
      model.error = error.message;
    } finally {
      model.loading = false;
      draw();
    }
  }

  function find(id) { return model.companies.find((c) => c.id === id) || null; }

  async function afterChange(notice) {
    model.modal = null;
    model.notice = notice;
    await reload();
    if (ctx && ctx.reloadOverview) ctx.reloadOverview();
  }

  async function onClick(event) {
    const t = event.target;
    if (!t || !t.closest || !ctx || !ctx.active()) return;
    const tab = t.closest("[data-vpc-tab]");
    if (tab) { model.tab = tab.getAttribute("data-vpc-tab"); draw(); return; }
    const filter = t.closest("[data-vpc-filter]");
    if (filter) { model.filter = filter.getAttribute("data-vpc-filter"); draw(); return; }
    if (t.closest("[data-vpc-reload]")) { model.notice = ""; reload(); return; }
    if (t.closest("[data-vpc-new]")) { model.showCreate = !model.showCreate; draw(); return; }
    if (t.closest("[data-vpc-generate]")) {
      const form = t.closest("form");
      if (form) form.elements.owner_password.value = generateTempPassword(form.elements.slug.value || form.elements.name.value || "empresa");
      return;
    }
    if (t.closest("[data-vpc-close]")) { model.modal = null; draw(); return; }
    if (t.closest("[data-vpc-copy]")) {
      const input = document.querySelector("[data-vpc-copy-value]");
      try { await navigator.clipboard.writeText(input ? input.value : ""); ctx.toast("Clave copiada."); } catch (_) { ctx.toast("No se pudo copiar."); }
      return;
    }
    const status = t.closest("[data-vpc-status]");
    if (status) {
      const c = find(status.getAttribute("data-vpc-status"));
      try { await updateCompanyStatus(c.id, status.getAttribute("data-status")); await afterChange(`Estado de ${c.name} actualizado.`); }
      catch (error) { model.error = `No se pudo actualizar el estado de la empresa: ${error.message}`; draw(); }
      return;
    }
    const archive = t.closest("[data-vpc-archive]");
    if (archive) { model.modal = { type: "archive", company: find(archive.getAttribute("data-vpc-archive")) }; draw(); return; }
    if (t.closest("[data-vpc-archive-go]")) {
      const c = model.modal.company;
      const typed = (document.querySelector("[data-vpc-confirm-input]") || {}).value || "";
      try { await archiveCompany(c, typed); await afterChange(`${c.name} archivada.`); }
      catch (error) { model.modal.error = error.message; draw(); }
      return;
    }
    const kind = t.closest("[data-vpc-kind]");
    if (kind) { model.modal = { type: "kind", kind: kind.getAttribute("data-kind"), company: find(kind.getAttribute("data-vpc-kind")) }; draw(); return; }
    if (t.closest("[data-vpc-kind-go]")) {
      const md = model.modal;
      try { await changeKind(md.company.id, md.kind, true); await afterChange(`${md.company.name} ahora es ${md.kind}.`); }
      catch (error) { md.error = error.message; draw(); }
      return;
    }
    const clone = t.closest("[data-vpc-clone]");
    if (clone) {
      const c = find(clone.getAttribute("data-vpc-clone"));
      model.modal = { type: "clone", company: c, password: generateTempPassword(`${c.slug}-demo`) };
      draw();
      return;
    }
    const purgeBtn = t.closest("[data-vpc-purge]");
    if (purgeBtn) {
      const c = find(purgeBtn.getAttribute("data-vpc-purge"));
      model.modal = { type: "purge", company: c, plan: null };
      draw();
      try { model.modal.plan = await purge(c.id, true); } catch (error) { model.modal.error = error.message; }
      draw();
      return;
    }
    if (t.closest("[data-vpc-purge-go]")) {
      const c = model.modal.company;
      const typed = (document.querySelector("[data-vpc-confirm-input]") || {}).value || "";
      if (typed !== c.name) { model.modal.error = "Escribe el nombre exacto de la empresa."; draw(); return; }
      try { const done = await purge(c.id, false, typed); await afterChange(`${c.name} eliminada: ${done.total_rows} filas borradas.`); }
      catch (error) { model.modal.error = error.message; draw(); }
    }
  }

  async function onSubmit(event) {
    const form = event.target;
    if (!ctx || !ctx.active() || !form || !form.matches) return;
    if (form.matches("[data-vpc-create]")) {
      event.preventDefault();
      model.busy = true;
      try {
        const raw = Object.fromEntries(new FormData(form).entries());
        const result = await createCompanyFlow(raw);
        model.showCreate = false;
        await afterChange(`Empresa ${raw.name} creada.`);
        model.modal = { type: "result", title: "Empresa creada", message: `Acceso maestro: ${result.ownerEmail}`, password: result.temporaryPassword, warnings: result.warnings };
      } catch (error) {
        model.error = `No se pudo crear la empresa: ${error.message}`;
      } finally {
        model.busy = false;
        draw();
      }
      return;
    }
    if (form.matches("[data-vpc-clone-form]")) {
      event.preventDefault();
      const md = model.modal;
      const raw = Object.fromEntries(new FormData(form).entries());
      try {
        const done = await cloneDemo(md.company.id, raw);
        await afterChange(`${raw.name} creada como demo.`);
        model.modal = { type: "result", title: "Demo creada", message: `Copiadas ${Object.values(done.copied || {}).reduce((a, b) => a + b, 0)} filas de configuración. Acceso: ${done.owner_email}`, password: done.temporary_password };
        draw();
      } catch (error) { md.error = error.message; draw(); }
    }
  }

  function onInput(event) {
    const t = event.target;
    if (!ctx || !ctx.active() || !t || !t.matches || !t.matches("[data-vpc-search]")) return;
    model.query = t.value;
    const box = ctx.root() && ctx.root().querySelector("[data-vpc-table]");
    if (box) box.innerHTML = companiesTable(visibleCompanies(model.companies, ctx.overview(), model), ctx.overview());
  }

  function refreshPulse() {
    const box = ctx && ctx.active() && ctx.root() && ctx.root().querySelector("[data-vpc-table]");
    if (box && model.loaded) box.innerHTML = companiesTable(visibleCompanies(model.companies, ctx.overview(), model), ctx.overview());
  }

  function mount(context) {
    ctx = context;
    if (!model.bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("submit", onSubmit);
      document.addEventListener("input", onInput);
      model.bound = true;
    }
    draw();
    if (!model.loaded && !model.loading) reload();
  }

  window.CxConsoleCompanies = {
    mount, refreshPulse, view, companiesTable, visibleCompanies, byFilter, kindOf, counts, modal, rowActions,
    loadCompanies, loadPackages, createCompanyFlow, updateCompanyStatus, archiveCompany, changeKind, cloneDemo, purge,
    generateTempPassword, model,
  };
})();
