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

  // Lo que pasó, en lenguaje claro ("Publicó la marca de Velvet"), no la ruta técnica.
  const switchLabel = (key) => {
    const reg = window.CxSwitchRegistry;
    const sw = reg && reg.get ? reg.get(key) : null;
    return (sw && sw.label) || String(key).replace(/_/g, " ");
  };
  const truthy = (v) => v === true || v === "true" || v === "True";
  const RULES = [
    [/\/brand\/[^/]+\/publish$/, null, (d, w) => `Publicó la marca de ${w}${d.version ? ` (versión ${d.version})` : ""}`],
    [/\/brand\/[^/]+\/rollback\/(\d+)$/, null, (d, w, x) => `Volvió la marca de ${w} a la versión ${x[1]}`],
    [/\/brand\/[^/]+\/unpublish$/, null, (d, w) => `Quitó la marca publicada de ${w}`],
    [/\/brand\/[^/]+\/share$/, "POST", (d, w) => `Compartió la vista previa de la marca de ${w}`],
    [/\/brand\/[^/]+\/share\/[^/]+$/, "DELETE", (d, w) => `Revocó un enlace de vista previa de ${w}`],
    [/\/brand\/[^/]+\/copy-from\//, null, (d, w) => `Copió la marca de ${d.origen || "otra empresa"} a ${w}`],
    [/\/brand\/[^/]+\/images$/, "POST", (d, w) => `Subió una imagen de marca a ${w}`],
    [/\/brand\/[^/]+\/images\/[^/]+$/, "DELETE", (d, w) => `Borró una imagen de marca de ${w}`],
    [/\/billing\/companies\/[^/]+\/contract$/, null, (d, w) => `Guardó el contrato de ${w}`],
    [/\/billing\/companies\/[^/]+\/contract-file$/, null, (d, w) => `Adjuntó el contrato de ${w}`],
    [/\/billing\/companies\/[^/]+\/payments$/, "POST", (d, w) => `Registró un pago de ${w}${d.valor ? ` por ${d.valor}` : ""}`],
    [/\/billing\/companies\/[^/]+\/payments\/[^/]+\/validate$/, null, (d, w) => `Validó un pago de ${w}${d.comprobante ? ` (comprobante ${d.comprobante})` : ""}`],
    [/\/billing\/companies\/[^/]+\/payments\/[^/]+\/void$/, null, (d, w) => `Anuló un pago de ${w}${d.comprobante ? ` (comprobante ${d.comprobante})` : ""}`],
    [/\/billing\/companies\/[^/]+\/receipts\/[^/]+\/link$/, null, (d, w) => `Compartió un comprobante de pago de ${w}`],
    [/\/billing\/contract-types$/, null, () => "Agregó un tipo de contrato"],
    [/\/modules\/([^/]+)\/(activate|deactivate)$/, null, (d, w, x) => {
      if (d.interruptor) return `${truthy(d.valor) ? "Encendió" : "Apagó"} ${switchLabel(d.interruptor)} en ${w}`;
      if (d.ajuste === "qr_config") return `Cambió la configuración QR de ${w}`;
      return x[2] === "activate" ? `Encendió o ajustó el módulo ${x[1]} en ${w}` : `Apagó el módulo ${x[1]} en ${w}`;
    }],
    [/\/workforce-sessions\/companies\/[^/]+\/policy$/, null, (d, w) => `Cambió el corte diario de sesiones de ${w}`],
    [/\/companies\/[^/]+\/kind$/, null, (d, w) => `Cambió el tipo de ${w}`],
    [/\/companies\/[^/]+\/clone-demo$/, null, (d, w) => `Clonó ${w} como demo`],
    [/\/companies\/[^/]+\/purge$/, null, (d, w) => (d.deleted_rows !== undefined ? `Eliminó definitivamente ${w}` : `Simuló eliminar ${w}`)],
    [/\/companies\/[^/]+\/users$/, "POST", (d, w) => `Creó un acceso en ${w}`],
    [/\/users\/[^/]+\/reset-password$/, null, (d, w) => `Generó una clave temporal en ${w}`],
    [/\/users\/[^/]+\/unlock$/, null, (d, w) => `Desbloqueó un usuario de ${w}`],
    [/\/users\/[^/]+\/status$/, null, (d, w) => `Cambió el estado de un usuario de ${w}`],
    [/\/access-sessions(\/[^/]+)?\/close$/, null, (d, w) => `Cerró sesiones de ${w}`],
    [/\/admin-v2\/api\/sessions\/[^/]+\/close$/, null, () => "Cerró una sesión de la consola"],
    [/\/packages(\/[^/]+)?(\/mini-panel-settings)?$/, null, (d, w, x, m) => (m === "DELETE" ? "Borró un paquete" : "Guardó un paquete")],
    [/\/modules(\/[^/]+)?$/, null, (d, w, x, m) => (m === "DELETE" ? "Borró un módulo del catálogo" : "Creó un módulo del catálogo")],
    [/\/payroll-co\/params\/(\d{4})$/, null, (d, w, x) => `Guardó los parámetros de nómina de ${x[1]}`],
  ];
  const VERBS = { POST: "Hizo un cambio", PUT: "Cambió", PATCH: "Cambió", DELETE: "Borró" };

  function describe(e, names = {}) {
    const path = String((e && e.path) || "").split("?")[0];
    const method = String((e && e.method) || "").toUpperCase();
    const d = (e && e.detail && typeof e.detail === "object") ? e.detail : {};
    const who = d.company_name || (e && e.company_id && names[e.company_id]) || "una empresa";
    const fail = Number(e && e.status_code) >= 400 ? " (no se completó)" : "";
    for (const [re, only, fn] of RULES) {
      if (only && only !== method) continue;
      const x = path.match(re);
      if (x) return fn(d, who, x, method) + fail;
    }
    const tail = path.split("/").filter((p) => p && !/^[0-9a-f-]{36}$/i.test(p) && !["api", "v1", "admin-v2", "companies"].includes(p)).slice(-2).join(" ").replace(/[-_]/g, " ");
    return `${VERBS[method] || "Cambió"} ${tail || "algo"}${e && e.company_id ? ` en ${who}` : ""}${fail}`;
  }

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
        <td><b>${h(describe(e, names))}</b><br><small class="vp-mono-muted">${h(e.method)} ${h(e.path)}</small></td>
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

  window.CxConsoleAudit = { view, mountInto, table, query, panel, load, describe, when, companyNames };
})();
