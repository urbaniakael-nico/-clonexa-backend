// Consola v2+ · Auditoría: escrituras hechas con la sesión de Admin V2
// (GET /admin-v2/api/audit), con filtros por empresa, fecha y acción.
// Se usa en el menú "Auditoría" y en la pestaña "Auditoría" de la Ficha.
(() => {
  "use strict";

  const URL_AUDIT = "/admin-v2/api/audit";
  const hosts = new Map(); // elemento -> { fixed, filters, entries, error, loading }

  function h(value) {
    return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function query(filters) {
    const params = [];
    ["company_id", "date_from", "date_to", "action", "limit"].forEach((key) => {
      const value = String((filters && filters[key]) || "").trim();
      if (value) params.push(`${key}=${encodeURIComponent(value)}`);
    });
    return params.length ? `${URL_AUDIT}?${params.join("&")}` : URL_AUDIT;
  }

  async function load(filters) {
    const response = await fetch(query(filters), { credentials: "same-origin", headers: { Accept: "application/json" } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) throw new Error((data && data.detail) || `Respuesta ${response.status}`);
    return Array.isArray(data.entries) ? data.entries : [];
  }

  function when(iso) {
    const t = Date.parse(iso || "");
    if (!Number.isFinite(t)) return "—";
    try { return new Date(t).toLocaleString("es-CO", { timeZone: "America/Bogota", dateStyle: "short", timeStyle: "medium" }); } catch (_) { return String(iso); }
  }

  const SURFACES = { v2plus: "Consola v2+", v2: "Admin V2", api: "API" };

  function detailText(detail) {
    if (!detail || typeof detail !== "object") return "";
    return Object.entries(detail).map(([k, v]) => `${k}: ${v}`).join(" · ");
  }

  function table(entries, names = {}, showCompany = true) {
    if (!entries.length) return `<div class="vp-empty" data-vpa-empty>Sin escrituras registradas con estos filtros.</div>`;
    return `<div class="vp-table-wrap"><table class="vp-table vp-audit-table">
      <thead><tr><th>Fecha (Bogotá)</th><th>Acción</th>${showCompany ? "<th>Empresa</th>" : ""}<th>Resultado</th><th>Quién y desde dónde</th><th>Detalle</th></tr></thead>
      <tbody>${entries.map((e) => `<tr>
        <td class="vp-mono">${h(when(e.at))}</td>
        <td><b class="vp-mono">${h(e.method)}</b> <span class="vp-mono-muted">${h(e.path)}</span></td>
        ${showCompany ? `<td>${e.company_id ? `<a href="#empresa/${encodeURIComponent(e.company_id)}">${h(names[e.company_id] || String(e.company_id).slice(0, 8))}</a>` : "—"}</td>` : ""}
        <td class="vp-mono ${Number(e.status_code) >= 400 ? "vp-audit-fail" : ""}">${h(e.status_code)}</td>
        <td><small>${h(e.actor)} · ${h(e.ip)} · ${h(SURFACES[e.surface] || e.surface || "")}</small></td>
        <td><small>${h(detailText(e.detail))}</small></td>
      </tr>`).join("")}</tbody></table></div>`;
  }

  function filtersForm(state) {
    const f = state.filters;
    return `<form class="vp-form-grid vp-audit-filters" data-vpa-form>
      ${state.fixed.company_id ? "" : `<label class="vp-field">Empresa (ID)<input name="company_id" value="${h(f.company_id || "")}" placeholder="todas" autocomplete="off"></label>`}
      <label class="vp-field">Desde<input name="date_from" type="date" value="${h(f.date_from || "")}"></label>
      <label class="vp-field">Hasta<input name="date_to" type="date" value="${h(f.date_to || "")}"></label>
      <label class="vp-field">Acción<input name="action" value="${h(f.action || "")}" placeholder="POST, purge, kind, status…" autocomplete="off"></label>
      <button class="vp-btn vp-btn-primary" type="submit">Filtrar</button>
    </form>`;
  }

  function panel(state, names) {
    return `${filtersForm(state)}
      ${state.error ? `<div class="vp-alert" role="alert"><span>${h(state.error)}</span></div>` : ""}
      <p class="vp-login-hint">Solo escrituras hechas con sesión de Admin V2 (nunca cuerpos ni claves). Se guardan 180 días.</p>
      <div data-vpa-table>${state.loading ? `<p class="vp-loading">Cargando auditoría…</p>` : table(state.entries, names, !state.fixed.company_id)}</div>`;
  }

  function companyNames() {
    const plus = window.CxConsolePlus;
    const overview = plus && plus.state ? plus.state.overview : null;
    const out = {};
    ((overview && overview.companies) || []).forEach((c) => { out[c.id] = c.name; });
    return out;
  }

  function draw(el) {
    const state = hosts.get(el);
    if (state && el.isConnected !== false) el.innerHTML = panel(state, companyNames());
  }

  async function refresh(el) {
    const state = hosts.get(el);
    if (!state) return;
    state.loading = true;
    draw(el);
    try { state.entries = await load({ ...state.filters, ...state.fixed }); state.error = ""; }
    catch (error) { state.error = error.message; }
    finally { state.loading = false; draw(el); }
  }

  function mountInto(el, fixed = {}) {
    if (!el) return;
    const previous = hosts.get(el);
    if (!previous || JSON.stringify(previous.fixed) !== JSON.stringify(fixed)) {
      hosts.set(el, { fixed: { ...fixed }, filters: {}, entries: [], error: "", loading: false });
    }
    refresh(el);
  }

  function view() {
    return `<header class="vp-head"><div><p class="vp-eyebrow">NÚCLEO CLONEXA · SEGURIDAD</p><h1 class="vp-title">Auditoría</h1></div></header>
      <section class="vp-panel vp-section" data-vpa-host></section>`;
  }

  function onSubmit(event) {
    const form = event.target;
    if (!form || !form.matches || !form.matches("[data-vpa-form]")) return;
    event.preventDefault();
    const el = form.closest("[data-vpa-host]");
    const state = el && hosts.get(el);
    if (!state) return;
    state.filters = Object.fromEntries(new FormData(form).entries());
    refresh(el);
  }

  if (typeof document.addEventListener === "function") document.addEventListener("submit", onSubmit);

  window.CxConsoleAudit = { view, mountInto, table, query, panel, load };
})();
