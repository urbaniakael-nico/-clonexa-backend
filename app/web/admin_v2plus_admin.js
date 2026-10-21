// Consola v2+ · Accesos y sesiones (N-09, U01–U05, N-11, H03, H04, Z01),
// Salud y seguridad (H01, H02 + datos nuevos de solo lectura), Landing (L01)
// y Estudio de marca (próximamente). Lo migrado usa el MISMO endpoint, método
// y cuerpo que Admin V2; las acciones de usuarios reutilizan las de la Ficha
// (CxConsoleCompany.writes, ya con prueba de contrato). Sin estilos en línea.
(() => {
  "use strict";

  const API = "/api/v1";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const fold = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const matches = (q, ...f) => { const w = fold(q).split(" ").filter(Boolean); const hay = fold(f.join(" ")); return w.every((x) => hay.includes(x) || hay.replace(/ /g, "").includes(x)); };
  const since = (iso) => (window.CxConsolePlus ? window.CxConsolePlus.since(iso) : iso || "—");
  const OWNER_ROLES = new Set(["company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"]);

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options, headers: { "Content-Type": "application/json", Accept: "application/json", ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && String(url).startsWith("/admin-v2")) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) throw new Error((data && (typeof data.detail === "string" ? data.detail : data.message)) || `Respuesta ${response.status}`);
    return data;
  }
  const apiGet = (u) => request(u);
  const apiPost = (u, b) => request(u, { method: "POST", body: JSON.stringify(b) });

  // ------------------------------------------------ contrato con Admin V2
  const consoleApi = {
    sessions: () => apiGet("/admin-v2/api/sessions"),                                                 // H03
    closeSession: (key) => apiPost(`/admin-v2/api/sessions/${key}/close`, {}),                       // H04
    // Z01: igual que v2 (POST sin cuerpo), pero vuelve a la entrada de v2+.
    // El servidor cierra la sesión (access_sessions) y borra la cookie. Si no
    // responde, se lanza el error: la sesión no se da por cerrada sin el servidor.
    async logout() {
      const response = await fetch("/admin-v2/logout", { method: "POST", credentials: "same-origin", redirect: "manual" });
      const done = response && (response.ok || response.type === "opaqueredirect" || response.status === 303 || response.status === 0);
      if (!done) throw new Error("No se pudo cerrar la sesión en el servidor. Intenta de nuevo.");
      // replace: el botón Atrás no vuelve a la consola.
      if (typeof window.location.replace === "function") window.location.replace("/admin-v2plus/login");
      else window.location.href = "/admin-v2plus/login";
    },
    // H01 con respaldo H02, igual que loadHealth de v2.
    health: () => apiGet("/health").catch(() => apiGet(`${API}/health`)),
    // L01: mismos parámetros y en el mismo orden que loadLandingAnalytics025R.
    landingUrl(filters = {}) {
      const params = new URLSearchParams({ days: filters.days || "30", limit: "40" });
      if (filters.source) params.set("source", filters.source);
      if (filters.campaign) params.set("campaign", filters.campaign);
      if (filters.device) params.set("device", filters.device);
      return `${API}/landing-analytics/summary?${params.toString()}`;
    },
    landing(filters) { return apiGet(consoleApi.landingUrl(filters)); },
    // Redes sociales de Nexa (solo Admin V2): cifras que manda n8n + embudo a la landing.
    socialUrl: (days) => `${API}/social-metrics/summary?days=${encodeURIComponent(days || "30")}`,
    social(days) { return apiGet(consoleApi.socialUrl(days)); },
    passkeys: () => apiGet("/admin-v2plus/api/passkeys"),
    deletePasskey: (id) => request(`/admin-v2plus/api/passkeys/${encodeURIComponent(id)}`, { method: "DELETE" }),
  };
  const companyWrites = () => (window.CxConsoleCompany && window.CxConsoleCompany.writes) || null;
  const kindOf = (c, ov) => (window.CxConsoleCompanies ? window.CxConsoleCompanies.kindOf(c, ov) : "demo");
  const isArchived = (c) => ["archived", "deleted"].includes(String((c && c.status) || "").toLowerCase());

  // ------------------------------------------------------------ estado
  const model = {
    access: { tab: "maestro", companies: null, users: {}, modules: {}, query: "", kind: "registrada", onlyNoOwner: false, sessions: null, passkeys: null, loading: false },
    health: { status: null, security: null, error: "", audit: null },
    landing: { data: null, filters: { days: "30", source: "", campaign: "", device: "" }, error: "", loading: false, tab: "visitas" },
    social: { days: "30", data: null, error: "", query: "" },
    modal: null, notice: "", error: "", view: "",
  };
  let ctx = null;
  let bound = false;

  // ------------------------------------------------------------ Accesos
  function owners(users) { return arr(users).filter((u) => OWNER_ROLES.has(String(u.role || "").toLowerCase())); }

  function maestroTab() {
    const a = model.access;
    if (!a.companies) return `<p class="vp-loading">Cargando empresas y accesos…</p>`;
    const ov = ctx && ctx.overview ? ctx.overview() : null;
    const rows = a.companies.filter((c) => !isArchived(c))
      .filter((c) => a.kind === "todas" || kindOf(c, ov) === a.kind)
      .filter((c) => { const us = a.users[c.id]; return !a.onlyNoOwner || (us && !owners(us).some((u) => String(u.status).toLowerCase() === "active")); })
      .filter((c) => matches(a.query, c.name, c.slug, owners(a.users[c.id]).map((u) => `${u.full_name} ${u.email}`).join(" ")));
    return `<div class="vp-toolbar"><input class="vp-search" type="search" placeholder="Buscar empresa, dueño o email" value="${h(a.query)}" data-vpx-search aria-label="Buscar acceso">
        <div class="vp-chips">${[["registrada", "Registradas"], ["demo", "Demos"], ["todas", "Todas"]].map(([k, l]) => `<button class="vp-chip ${a.kind === k ? "is-active" : ""}" type="button" data-vpx-kind="${k}">${l}</button>`).join("")}
        <button class="vp-chip ${a.onlyNoOwner ? "is-active" : ""}" type="button" data-vpx-no-owner>Sin dueño activo</button></div></div>
      <div class="vp-table-wrap vp-zone-scroll"><table class="vp-table vp-table-compact"><thead><tr><th>Empresa</th><th>Dueño</th><th>Estado</th><th>Último ingreso</th><th><span class="sr-only">Acciones</span></th></tr></thead><tbody>
      ${rows.map((c) => { const us = a.users[c.id]; const os = owners(us);
        if (!us) return `<tr><td><a href="#empresa/${encodeURIComponent(c.id)}"><b>${h(c.name)}</b></a></td><td colspan="4"><span class="vp-loading">Cargando…</span></td></tr>`;
        if (!os.length) return `<tr><td><a href="#empresa/${encodeURIComponent(c.id)}"><b>${h(c.name)}</b></a></td><td colspan="3"><span class="vp-no">Sin acceso maestro</span></td>
          <td><button class="vp-btn vp-btn-sm vp-btn-primary" type="button" data-vpx-create="${h(c.id)}">Crear acceso</button></td></tr>`;
        return os.map((u, i) => { const active = String(u.status).toLowerCase() === "active"; return `<tr>
          <td>${i ? "" : `<a href="#empresa/${encodeURIComponent(c.id)}"><b>${h(c.name)}</b></a><br><small class="vp-mono-muted">${h(c.slug)}</small>`}</td>
          <td><b>${h(u.full_name)}</b><br><small class="vp-mono-muted">${h(u.email)}</small></td>
          <td>${active ? "Activo" : "Inactivo"}${u.locked_until ? " · bloqueado" : ""}</td><td class="vp-mono">${h(u.last_login_at ? since(u.last_login_at) : "Nunca")}</td>
          <td><div class="vp-actions"><button class="vp-btn vp-btn-sm" type="button" data-vpx-reset="${h(c.id)}" data-user="${h(u.id)}">Clave temporal</button>
            <button class="vp-btn vp-btn-sm" type="button" data-vpx-unlock="${h(c.id)}" data-user="${h(u.id)}">Desbloquear</button>
            <button class="vp-btn vp-btn-sm" type="button" data-vpx-status="${h(c.id)}" data-user="${h(u.id)}" data-status="${active ? "inactive" : "active"}">${active ? "Desactivar" : "Activar"}</button>
            ${i ? "" : `<button class="vp-btn vp-btn-sm" type="button" data-vpx-create="${h(c.id)}">+ Acceso</button>`}</div></td></tr>`; }).join("");
      }).join("") || `<tr><td colspan="5"><div class="vp-empty">Ninguna empresa coincide.</div></td></tr>`}</tbody></table></div>`;
  }

  function linksTab() {
    const a = model.access;
    if (!a.companies) return `<p class="vp-loading">Cargando…</p>`;
    const C = window.CxConsoleCompany;
    const ov = ctx && ctx.overview ? ctx.overview() : null;
    const list = a.companies.filter((c) => !isArchived(c) && (a.kind === "todas" || kindOf(c, ov) === a.kind) && matches(a.query, c.name, c.slug));
    return `<div class="vp-toolbar"><input class="vp-search" type="search" placeholder="Buscar empresa" value="${h(a.query)}" data-vpx-search aria-label="Buscar empresa">
      <div class="vp-chips">${[["registrada", "Registradas"], ["demo", "Demos"], ["todas", "Todas"]].map(([k, l]) => `<button class="vp-chip ${a.kind === k ? "is-active" : ""}" type="button" data-vpx-kind="${k}">${l}</button>`).join("")}</div></div>
      <div class="vp-card-grid vp-zone-scroll">${list.map((c) => { const mods = a.modules[c.id]; const links = mods && C ? C.accessLinks(c, mods) : null; return `<article class="vp-panel-card">
        <header><b>${h(c.name)}</b><a class="vp-btn vp-btn-sm" href="#empresa/${encodeURIComponent(c.id)}">Ficha</a></header>
        ${links ? `<ul class="vp-quick-list">${links.map((l) => `<li><span><b>${h(l.title)}</b><small class="vp-mono-muted">${h(l.href)}</small></span><button class="vp-btn vp-btn-sm" type="button" data-vpx-copy="${h(l.href)}">Copiar</button></li>`).join("")}</ul>` : `<p class="vp-loading">Cargando links…</p>`}
      </article>`; }).join("") || `<div class="vp-empty">Ninguna empresa coincide.</div>`}</div>`;
  }

  function sessionsTab() {
    const a = model.access;
    const s = a.sessions;
    const list = s ? arr(s.sessions) : [];
    return `<section class="vp-panel vp-section"><h2>Sesiones de la consola</h2>
      ${s === null ? `<p class="vp-loading">Cargando…</p>` : `<p class="vp-login-hint"><b>${h(s.active || 0)}</b> activas de ${h(list.length)} recientes.</p>
      <div class="vp-table-wrap vp-zone-scroll"><table class="vp-table vp-table-compact"><thead><tr><th>Sesión</th><th>Estado</th><th>Última actividad</th><th>IP</th><th><span class="sr-only">Acciones</span></th></tr></thead><tbody>
        ${list.map((x) => `<tr><td>${h(x.subject_label || "Acceso maestro")}${x.session_key === s.current_session ? ` <span class="vp-state-pill is-on">esta</span>` : ""}</td><td>${h(x.status)}</td><td class="vp-mono">${h(since(x.last_seen_at))}</td><td class="vp-mono">${h(x.ip_address || "")}</td>
          <td>${String(x.status).toLowerCase() === "active" ? `<button class="vp-btn vp-btn-sm" type="button" data-vpx-close-admin="${h(x.session_key)}">Cerrar</button>` : ""}</td></tr>`).join("")}
      </tbody></table></div>`}</section>
    <section class="vp-panel vp-section"><h2>Llaves de acceso (huellas)</h2>
      ${a.passkeys === null ? `<p class="vp-loading">Cargando…</p>` : arr(a.passkeys).length ? `<ul class="vp-actions-list">${arr(a.passkeys).map((k) => `<li class="vp-action vp-toggle-row"><b>${h(k.label)}</b>
        <small>Registrada ${h(since(k.created_at))} · último uso ${h(k.last_used_at ? since(k.last_used_at) : "nunca")}</small><button class="vp-btn vp-btn-sm" type="button" data-vpx-passkey-delete="${h(k.id)}">Quitar</button></li>`).join("")}</ul>`
        : `<div class="vp-empty">No hay huellas registradas. Regístralas con "Huella de este equipo".</div>`}
    </section>
    <section class="vp-panel vp-section"><h2>Mi sesión</h2><button class="vp-btn vp-btn-danger" type="button" data-vpx-logout>Cerrar mi sesión</button></section>`;
  }

  function accessView() {
    const a = model.access;
    const tabs = [["maestro", "Acceso Maestro"], ["links", "Links por empresa"], ["consola", "Sesiones de la consola"]];
    const pane = a.tab === "links" ? linksTab() : a.tab === "consola" ? sessionsTab() : `<section class="vp-panel vp-section">${maestroTab()}</section>`;
    return `<header class="vp-head"><div><p class="vp-eyebrow">NÚCLEO CLONEXA · ACCESOS</p><h1 class="vp-title">Accesos y sesiones</h1></div></header>
      ${banner()}<nav class="vp-chips" role="tablist">${tabs.map(([k, l]) => `<button class="vp-chip ${a.tab === k ? "is-active" : ""}" type="button" role="tab" aria-selected="${a.tab === k}" data-vpx-tab="${k}">${l}</button>`).join("")}</nav>${pane}`;
  }

  // ------------------------------------------------------------ Salud
  function healthView() {
    const s = model.health;
    const ov = ctx && ctx.overview ? ctx.overview() : null;
    const hb = (ov && ov.health) || {};
    const db = hb.database || {};
    const sec = s.security;
    const risk = ((ov && ov.companies) || []).filter((c) => c.state === "riesgo");
    const status = s.status;
    const idle = sec && sec.session_idle;
    return `<header class="vp-head"><div><p class="vp-eyebrow">NÚCLEO CLONEXA · SALUD</p><h1 class="vp-title">Salud y seguridad</h1></div>
      <div class="vp-head-actions"><button class="vp-btn" type="button" data-vpx-health-refresh>Refrescar</button></div></header>${banner()}
      <div class="vp-sum-grid">
        <section class="vp-panel vp-section"><h2>Sistema</h2><div class="vp-kv-grid">
          <div class="vp-kv"><span>Estado</span><strong class="${status && status.ok ? "vp-yes" : "vp-no"}">${status === null ? "…" : status.ok ? "En línea" : "Con problemas"}</strong></div>
          <div class="vp-kv"><span>Servicio</span><strong>${h((status && (status.service || status.status)) || "—")}</strong></div>
          <div class="vp-kv"><span>Commit desplegado</span><strong class="vp-mono">${h((hb.deploy && hb.deploy.commit) || "—")}</strong></div>
          <div class="vp-kv"><span>Empresas demo</span><strong>${h(hb.demo_companies ?? "—")}</strong></div></div></section>
        <section class="vp-panel vp-section"><h2>Base de datos</h2>
          <div class="vp-kv-grid"><div class="vp-kv"><span>Usado</span><strong class="${db.warn ? "vp-no" : ""}">${h(db.used_mb ?? "—")} MB de ${h(db.limit_mb || 500)} MB</strong></div>
          <div class="vp-kv"><span>Ocupación</span><strong>${h(db.used_pct ?? "—")} %</strong></div></div>
          <div class="vp-meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${h(db.used_pct || 0)}"><span data-vpx-meter="${h(Math.min(100, Number(db.used_pct || 0)))}" class="${db.warn ? "is-warn" : ""}"></span></div>
          ${db.warn ? `<p class="vp-no">Por encima del 80 %: antes de guardar más datos pesados, el siguiente paso es un bucket de objetos.</p>` : ""}</section>
        <section class="vp-panel vp-section"><h2>Acceso maestro</h2>${sec ? `<div class="vp-kv"><span>Modo de la clave</span><strong class="${sec.master_access_mode === "bcrypt" ? "vp-yes" : "vp-no"}">${h(sec.master_access_mode)}</strong></div>
          <ul class="vp-actions-list">${arr(sec.variables).map((v) => `<li class="vp-action vp-toggle-row"><b>${h(v.label)}</b><small class="vp-mono">${h(v.name)}</small><span class="vp-state-pill ${v.present ? "is-on" : ""}">${v.present ? "Definida" : "Falta"}</span></li>`).join("")}</ul>
          <p class="vp-login-hint">Solo se indica si la variable existe; nunca su valor.</p>` : `<p class="vp-loading">Cargando…</p>`}</section>
        <section class="vp-panel vp-section"><h2>Cierre automático de sesiones</h2>${idle ? `<div class="vp-kv-grid">
          <div class="vp-kv"><span>Horas sin actividad</span><strong>${idle.hours ? `${h(idle.hours)} h` : "Apagado"}</strong></div>
          <div class="vp-kv"><span>Última corrida que cerró sesiones</span><strong>${idle.last_run_at ? `${h(idle.last_run_closed)} · ${h(since(idle.last_run_at))}` : "Ninguna todavía"}</strong></div>
          <div class="vp-kv"><span>Cerradas en 7 días</span><strong>${h(idle.closed_7d)}</strong></div></div>
          <p class="vp-login-hint">Variable CLONEXA_SESSION_IDLE_HOURS · motivo <span class="vp-mono">${h(idle.reason)}</span>.</p>` : `<p class="vp-loading">Cargando…</p>`}</section>
        <section class="vp-panel vp-section"><h2>Empresas en riesgo</h2>${risk.length ? `<ul class="vp-actions-list">${risk.map((c) => `<li class="vp-action vp-action-risk"><b><a href="#empresa/${encodeURIComponent(c.id)}">${h(c.name)}</a></b><small>${h(c.state_reason || "")}${c.kind === "demo" ? " · demo" : ""}</small></li>`).join("")}</ul>` : `<div class="vp-empty vp-ok-text">Ninguna empresa en riesgo.</div>`}</section>
        ${auditBlock()}
        <section class="vp-panel vp-section"><h2>Endpoints sin sesión</h2>${sec && sec.open_endpoints ? `<p><b>${h(sec.open_endpoints.open)}</b> de ${h(sec.open_endpoints.routes_checked)} rutas de /api/v1 sin una sesión visible en su definición.</p>
          <p class="vp-login-hint">Estimado informativo (lee las rutas en memoria, no hace peticiones). Incluye las públicas a propósito (ingreso, QR, carta, webhooks).</p>
          <div class="vp-chip-row">${Object.entries(sec.open_endpoints.by_area || {}).map(([k, n]) => `<span class="vp-mini-chip">${h(k)} · ${h(n)}</span>`).join("")}</div>` : `<p class="vp-loading">Cargando…</p>`}</section>
      </div>`;
  }

  // Últimos 5 registros de la auditoría, en lenguaje claro.
  function auditBlock() {
    const A = window.CxConsoleAudit;
    const list = model.health.audit;
    const names = A && A.companyNames ? A.companyNames() : {};
    const body = list === null ? `<p class="vp-loading">Cargando…</p>` : list.error ? `<div class="vp-alert" role="alert"><span>${h(list.error)}</span></div>`
      : arr(list).length ? `<ul class="vp-actions-list">${arr(list).slice(0, 5).map((e) => `<li class="vp-action"><b>${h(A ? A.describe(e, names) : e.path)}</b><small>${h(since(e.at))} · ${h(e.actor || "")}</small></li>`).join("")}</ul>`
        : `<div class="vp-empty">Sin registros todavía.</div>`;
    return `<section class="vp-panel vp-section" id="vpx-audit-block" data-vpx-audit-block><div class="vp-row-between"><h2>Auditoría</h2>
      <button class="vp-btn vp-btn-sm vp-btn-link" type="button" data-vpx-audit-all>Ver todo</button></div>${body}
      <p class="vp-login-hint">Escrituras hechas con sesión de Admin V2. Se guardan 180 días.</p></section>`;
  }

  // ------------------------------------------------------------ Landing
  // Redes de Nexa: mismo criterio que social_metrics.network_of en el servidor
  // (utm_source con el nombre de la red, o el dominio del referrer sin www./m.).
  const SOCIAL = [
    { key: "instagram", label: "Instagram", domains: ["instagram.com", "l.instagram.com"] },
    { key: "facebook", label: "Facebook", domains: ["facebook.com", "l.facebook.com", "lm.facebook.com"] },
    { key: "youtube", label: "YouTube", domains: ["youtube.com", "youtu.be"] },
    { key: "linkedin", label: "LinkedIn", domains: ["linkedin.com", "lnkd.in"] },
    { key: "tiktok", label: "TikTok", domains: ["tiktok.com"] },
  ];
  const LANDING_URL = "https://clonexa-landing-production.up.railway.app/";
  const socialLink = (key) => `${LANDING_URL}?utm_source=${key}&utm_medium=social&utm_campaign=nexa-bio`;
  function socialNetworkOf(source) {
    const s = String(source ?? "").trim().toLowerCase();
    const direct = SOCIAL.find((n) => n.key === s);
    if (direct) return direct;
    const bare = s.split(":")[0].replace(/^www\./, "").replace(/^m\./, "");
    return SOCIAL.find((n) => n.domains.includes(bare)) || null;
  }
  // Fuentes de la pestaña Visitas: los dominios de una red se suman bajo su nombre
  // (m.facebook.com + www.facebook.com = Facebook). Solo presentación.
  function groupSources(rows) {
    const out = new Map();
    arr(rows).forEach((r) => {
      const net = socialNetworkOf(r.label);
      const label = net ? net.label : r.label;
      out.set(label, (out.get(label) || 0) + Number(r.total || 0));
    });
    return Array.from(out, ([label, total]) => ({ label, total })).sort((a, b) => b.total - a.total || String(a.label).localeCompare(String(b.label)));
  }

  function landingView() {
    const L = model.landing;
    const tabs = [["visitas", "Visitas"], ["redes", "Redes sociales"]];
    return `<header class="vp-head"><div><p class="vp-eyebrow">NÚCLEO CLONEXA · LANDING</p><h1 class="vp-title">Landing</h1></div></header>${banner()}
      <nav class="vp-chips" role="tablist">${tabs.map(([k, l]) => `<button class="vp-chip ${L.tab === k ? "is-active" : ""}" type="button" role="tab" aria-selected="${L.tab === k}" data-vpx-landing-tab="${k}">${l}</button>`).join("")}</nav>
      ${L.tab === "redes" ? socialPane() : visitsPane()}`;
  }

  function visitsPane() {
    const L = model.landing;
    const d = L.data;
    const o = (d && d.options) || {};
    const t = (d && d.totals) || {};
    const list = (title, rows) => `<section class="vp-panel vp-section"><h2>${h(title)}</h2>${arr(rows).length ? `<ul class="vp-actions-list vp-zone-scroll">${arr(rows).map((r) => `<li class="vp-action vp-toggle-row"><b>${h(r.label)}</b><span class="vp-mono">${h(r.total)}</span></li>`).join("")}</ul>` : `<div class="vp-empty">Sin datos.</div>`}</section>`;
    const sel = (name, label, values, all) => `<label class="vp-field">${h(label)}<select name="${name}"><option value="">${h(all)}</option>${arr(values).map((v) => { const val = typeof v === "string" ? v : (v.label || v.value); return `<option ${L.filters[name] === val ? "selected" : ""}>${h(val)}</option>`; }).join("")}</select></label>`;
    return `<form class="vp-panel vp-section vp-form-grid" data-vpx-landing-form>
        <label class="vp-field">Periodo<select name="days">${[["7", "7 días"], ["30", "30 días"], ["90", "90 días"], ["365", "1 año"]].map(([v, l]) => `<option value="${v}" ${L.filters.days === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        ${sel("source", "Fuente", o.sources, "Todas")}${sel("campaign", "Campaña", o.campaigns, "Todas")}${sel("device", "Dispositivo", o.devices, "Todos")}
        <div class="vp-actions"><button class="vp-btn vp-btn-primary" type="submit">Filtrar</button><button class="vp-btn" type="button" data-vpx-landing-reset>Limpiar filtros</button></div>
      </form>
      ${L.error ? `<div class="vp-alert" role="alert"><span>${h(L.error)}</span></div>` : ""}
      ${!d ? `<p class="vp-loading">Cargando analítica…</p>` : `<section class="vp-cards">${[["Visitas", t.total_visits], ["Visitantes únicos", t.unique_visitors], ["Sesiones", t.sessions], ["Últimas 24 h", t.last_24h]].map(([l, v]) => `<div class="vp-panel vp-card"><span>${h(l)}</span><strong>${h(v ?? 0)}</strong></div>`).join("")}
        <div class="vp-panel vp-card"><span>Última visita</span><strong class="vp-card-small">${h(t.last_visit_at ? since(t.last_visit_at) : "—")}</strong></div></section>
        <div class="vp-sum-grid">${list("Fuentes", groupSources(d.sources))}${list("Campañas", d.campaigns)}${list("Páginas", d.paths)}${list("Dispositivos", d.devices)}${list("Ubicación", d.geo)}
        <section class="vp-panel vp-section"><h2>Visitas recientes</h2><ul class="vp-actions-list vp-zone-scroll">${arr(d.recent).map((r) => `<li class="vp-action"><b>${h(r.path || "/")}</b><small>${h(since(r.created_at))} · ${h(r.source || "directo")}${r.campaign ? ` · ${h(r.campaign)}` : ""} · ${h(r.device || "")}</small></li>`).join("") || `<li class="vp-empty">Sin visitas.</li>`}</ul></section></div>`}`;
  }

  // ------------------------------------------------------ Redes sociales
  const ICONS = {
    instagram: `<rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="17.4" cy="6.6" r="1.3" fill="currentColor"/>`,
    facebook: `<path fill="currentColor" d="M13.5 21v-7.5H16l.4-3h-2.9V8.6c0-.9.3-1.5 1.5-1.5h1.5V4.4c-.3 0-1.2-.1-2.2-.1-2.2 0-3.7 1.3-3.7 3.8v2.4H8v3h2.6V21z"/>`,
    youtube: `<rect x="2" y="5" width="20" height="14" rx="4" fill="currentColor"/><path class="vp-soc-cut" d="M10 9l5.2 3-5.2 3z"/>`,
    linkedin: `<rect x="3" y="3" width="18" height="18" rx="3" fill="currentColor"/><path class="vp-soc-cut" d="M6.8 10h2.5v7.2H6.8zM8.05 6a1.45 1.45 0 110 2.9 1.45 1.45 0 010-2.9zM10.9 10h2.4v1c.4-.7 1.3-1.2 2.4-1.2 2 0 2.7 1.3 2.7 3.3v4.1h-2.5v-3.6c0-.9-.2-1.7-1.1-1.7-1 0-1.4.7-1.4 1.7v3.6h-2.5z"/>`,
    tiktok: `<path fill="currentColor" d="M14.2 3h2.9c.2 1.8 1.4 3.2 3.1 3.5v2.9a6.6 6.6 0 01-3.1-.9v6a5.6 5.6 0 11-5.6-5.6c.3 0 .6 0 .9.1v3a2.6 2.6 0 101.8 2.5z"/>`,
  };
  const icon = (key) => `<svg class="vp-soc-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[key] || ""}</svg>`;
  const num = (v) => (v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("es-CO"));
  const shortDate = (iso) => { const [y, m, d] = String(iso || "").slice(0, 10).split("-"); return d ? `${d}/${m}` : "—"; };
  function postDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleDateString("es-CO", { timeZone: "America/Bogota", day: "2-digit", month: "short", year: "numeric" }); } catch (_) { return String(iso).slice(0, 10); }
  }

  // Vistas por día (7 días) o por semana (bloques de 7 días que terminan hoy),
  // apiladas por red. Devuelve [{label, total, parts: [{key, value}]}].
  function viewBuckets(networks, days) {
    const series = arr(networks).map((n) => ({ key: n.network, points: arr(n.series) }));
    const length = series.length ? series[0].points.length : 0;
    const size = Number(days) <= 7 ? 1 : 7;
    const out = [];
    for (let end = length; end > 0; end -= size) {
      const start = Math.max(0, end - size);
      const parts = series.map((s) => ({ key: s.key, value: s.points.slice(start, end).reduce((t, p) => t + Number(p.views || 0), 0) })).filter((p) => p.value > 0);
      const first = series.length ? series[0].points[start] : null;
      out.unshift({ label: first ? shortDate(first.date) : "", total: parts.reduce((t, p) => t + p.value, 0), parts });
    }
    return out;
  }

  function viewsChart(networks, days) {
    const buckets = viewBuckets(networks, days);
    const max = Math.max(0, ...buckets.map((b) => b.total));
    if (!max) return `<div class="vp-empty">Aún sin vistas diarias.</div>`;
    const W = 600, H = 200, gap = 6, bw = (W - gap * (buckets.length - 1)) / buckets.length;
    const bars = buckets.map((b, i) => {
      let y = H;
      return b.parts.map((p) => { const ph = (p.value / max) * (H - 4); y -= ph;
        return `<rect class="vp-soc-mark is-${h(p.key)}" x="${(i * (bw + gap)).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${ph.toFixed(1)}"><title>${h(b.label)} · ${h(p.key)}: ${h(num(p.value))}</title></rect>`; }).join("");
    }).join("");
    return `<div class="vp-soc-chart"><span class="vp-soc-max">${h(num(max))}</span><svg class="vp-soc-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Vistas ${Number(days) <= 7 ? "por día" : "por semana"}">${bars}</svg>
      <div class="vp-soc-axis"><span>${h(buckets[0].label)}</span><span>${h(buckets[buckets.length - 1].label)}</span></div></div>`;
  }

  function followersChart(networks) {
    const lines = arr(networks).map((n) => ({ key: n.network, pts: arr(n.series).map((p, i) => [i, p.followers]).filter((p) => p[1] !== null && p[1] !== undefined) })).filter((l) => l.pts.length);
    if (!lines.length) return `<div class="vp-empty">Aún sin seguidores registrados.</div>`;
    const length = Math.max(1, arr(networks[0] && networks[0].series).length - 1);
    const values = lines.flatMap((l) => l.pts.map((p) => Number(p[1])));
    const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    const W = 600, H = 200;
    const xy = ([i, v]) => `${((i / length) * W).toFixed(1)},${(H - 6 - ((Number(v) - lo) / span) * (H - 12)).toFixed(1)}`;
    const paths = lines.map((l) => `<polyline class="vp-soc-line is-${h(l.key)}" points="${(l.pts.length === 1 ? [l.pts[0], [length, l.pts[0][1]]] : l.pts).map(xy).join(" ")}" vector-effect="non-scaling-stroke"><title>${h(l.key)}: ${h(num(l.pts[l.pts.length - 1][1]))}</title></polyline>`).join("");
    const series = arr(networks[0] && networks[0].series);
    return `<div class="vp-soc-chart"><span class="vp-soc-max">${h(num(hi))}</span><svg class="vp-soc-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Seguidores por día">${paths}</svg>
      <div class="vp-soc-axis"><span>${h(shortDate(series[0] && series[0].date))}</span><span>mín. ${h(num(lo))}</span><span>${h(shortDate(series.length && series[series.length - 1].date))}</span></div></div>`;
  }

  function netCard(n) {
    const pending = n.network === "tiktok";
    const ch = n.followers_change;
    const delta = ch === null || ch === undefined ? "" : `<span class="vp-soc-delta ${ch > 0 ? "is-up" : ch < 0 ? "is-down" : ""}">${ch > 0 ? "▲" : ch < 0 ? "▼" : "="} ${h(num(Math.abs(ch)))}</span>`;
    const body = n.has_data
      ? `<div class="vp-soc-followers"><strong>${h(num(n.followers))}</strong>${delta}</div><small>seguidores</small>
        <dl class="vp-soc-kv"><div><dt>Vistas</dt><dd>${h(num(n.views))}</dd></div><div><dt>Interacciones</dt><dd>${h(num(n.engagements))}</dd></div><div><dt>Publicaciones</dt><dd>${h(num(n.posts))}</dd></div></dl>`
      : `<p class="vp-soc-nodata">${pending ? "Pendiente de aprobación" : "Aún sin datos"}</p>`;
    return `<article class="vp-panel vp-soc-net is-${h(n.network)}${n.has_data ? "" : " is-empty"}"><header>${icon(n.network)}<b>${h(n.label)}</b></header>${body}</article>`;
  }

  function socialPane() {
    const S = model.social;
    const d = S.data;
    const bar = `<section class="vp-panel vp-section vp-soc-bar"><div class="vp-chips" role="group" aria-label="Periodo">${["7", "30", "90"].map((v) => `<button class="vp-chip ${S.days === v ? "is-active" : ""}" type="button" aria-pressed="${S.days === v}" data-vpx-social-days="${v}">${v} días</button>`).join("")}</div>
      ${d ? `<small class="vp-mono-muted">${h(shortDate(d.start))} – ${h(shortDate(d.end))}</small>` : ""}</section>`;
    const links = `<section class="vp-panel vp-section"><h2>Enlaces con etiqueta</h2><p class="vp-login-hint">Para la bio o la descripción de cada red. Las visitas que entren por aquí se cuentan en el embudo.</p>
      <ul class="vp-quick-list">${SOCIAL.map((n) => `<li><span class="vp-soc-linkname">${icon(n.key)}<span><b>${h(n.label)}</b><small class="vp-mono-muted vp-soc-url">${h(socialLink(n.key))}</small></span></span><button class="vp-btn vp-btn-sm" type="button" data-vpx-copy="${h(socialLink(n.key))}">Copiar</button></li>`).join("")}</ul></section>`;
    if (!d) return `${bar}${S.error ? `<div class="vp-alert" role="alert"><span>${h(S.error)}</span></div>` : `<p class="vp-loading">Cargando redes…</p>`}${links}`;
    const nets = arr(d.networks);
    const f = d.funnel || {};
    const pct = (a, b) => (b ? `${(Math.round((a / b) * 1000) / 10).toLocaleString("es-CO")} %` : "—");
    const posts = arr(d.posts).filter((p) => matches(S.query, p.tema, p.label, p.network, p.utm_campaign));
    const small = (title, rows, label, empty) => `<section class="vp-panel vp-section"><h2>${h(title)}</h2>${arr(rows).length ? `<ul class="vp-actions-list">${arr(rows).map((r) => `<li class="vp-action vp-toggle-row"><b>${h(label(r))}</b><span class="vp-mono">${h(num(r.visits))} · ${h(num(r.unique_visitors))} únicos</span></li>`).join("")}</ul>` : `<div class="vp-empty">${h(empty)}</div>`}</section>`;
    return `${bar}${S.error ? `<div class="vp-alert" role="alert"><span>${h(S.error)}</span></div>` : ""}
      <section class="vp-soc-nets">${nets.map(netCard).join("")}</section>
      <section class="vp-panel vp-section"><h2>Embudo</h2><ol class="vp-soc-funnel">
        <li><span>Vistas en redes</span><strong>${h(num(f.social_views || 0))}</strong></li>
        <li><span>Visitas a la landing desde redes</span><strong>${h(num(f.landing_visits || 0))}</strong><small>${h(pct(f.landing_visits || 0, f.social_views || 0))} de las vistas</small></li>
        <li><span>Visitantes únicos</span><strong>${h(num(f.unique_visitors || 0))}</strong><small>${h(pct(f.unique_visitors || 0, f.landing_visits || 0))} de las visitas</small></li></ol></section>
      <div class="vp-soc-charts"><section class="vp-panel vp-section"><h2>Vistas ${Number(S.days) <= 7 ? "por día" : "por semana"}</h2>${viewsChart(nets, S.days)}</section>
        <section class="vp-panel vp-section"><h2>Seguidores</h2>${followersChart(nets)}</section></div>
      <div class="vp-soc-legend">${nets.map((n) => `<span class="is-${h(n.network)}"><i></i>${h(n.label)}</span>`).join("")}</div>
      <div class="vp-soc-charts">${small("Visitas a la landing por red", d.landing_by_network, (r) => r.label || r.network, "Ninguna visita desde redes todavía.")}${small("Campañas de Nexa", d.landing_by_campaign, (r) => r.campaign, "Ninguna visita con campaña nexa-* todavía.")}</div>
      <section class="vp-panel vp-section"><div class="vp-toolbar"><h2>Publicaciones</h2><input class="vp-search" type="search" placeholder="Buscar tema, red o campaña" value="${h(S.query)}" data-vpx-social-search aria-label="Buscar publicación"></div>
        ${posts.length ? `<div class="vp-table-wrap"><table class="vp-table vp-table-compact vp-soc-posts"><thead><tr><th>Fecha</th><th>Red</th><th>Tema</th><th>Vistas</th><th>Likes</th><th>Comentarios</th><th>Compartidos</th><th><span class="sr-only">Enlace</span></th></tr></thead><tbody>
          ${posts.map((p) => `<tr><td data-label="Fecha" class="vp-mono">${h(postDate(p.published_at))}</td><td data-label="Red"><span class="vp-soc-netname is-${h(p.network)}">${icon(p.network)}${h(p.label || p.network)}</span></td><td data-label="Tema">${h(p.tema || "—")}</td>
            <td data-label="Vistas" class="vp-mono">${h(num(p.views))}</td><td data-label="Likes" class="vp-mono">${h(num(p.likes))}</td><td data-label="Comentarios" class="vp-mono">${h(num(p.comments))}</td><td data-label="Compartidos" class="vp-mono">${h(num(p.shares))}</td>
            <td>${/^https?:\/\//i.test(String(p.url || "")) ? `<a class="vp-btn vp-btn-sm" href="${h(p.url)}" target="_blank" rel="noopener noreferrer">Ver</a>` : ""}</td></tr>`).join("")}</tbody></table></div>`
          : `<div class="vp-empty">${arr(d.posts).length ? "Ninguna publicación coincide." : "Aún no hay publicaciones en este periodo."}</div>`}</section>
      ${links}`;
  }

  // ------------------------------------------------------- Estudio de marca
  function brandView() {
    const p = (ctx && ctx.params) || {};
    return `<header class="vp-head"><div><p class="vp-eyebrow">NÚCLEO CLONEXA · MARCA</p><h1 class="vp-title">Estudio de marca</h1></div></header>
      <section class="vp-panel vp-soon"><h2>Próximamente</h2><p>El editor de marca se construye en la fase siguiente.${p.companyName ? ` Empresa elegida: <b>${h(p.companyName)}</b>.` : ""} Mientras tanto, la marca se ve en la Ficha de cada empresa y se edita en Admin V2.</p>
        ${p.companyId ? `<a class="vp-btn" href="#empresa/${encodeURIComponent(p.companyId)}">← Volver a la Ficha</a>` : ""}</section>`;
  }

  // ------------------------------------------------------------ comunes
  function banner() {
    return `${model.notice ? `<p class="vp-ok-text" role="status">${h(model.notice)}</p>` : ""}${model.error ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}`;
  }

  function modal(md) {
    if (!md) return "";
    const head = `<div class="vp-modal-head"><h2>${h(md.title)}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpx-modal-close aria-label="Cerrar">✕</button></div>`;
    const err = md.error ? `<div class="vp-alert" role="alert"><span>${h(md.error)}</span></div>` : "";
    let body = "";
    if (md.type === "audit") {
      return `<div class="vp-modal" data-vpx-modal><div class="vp-panel vp-modal-card vp-modal-wide" role="dialog" aria-modal="true">${head}<div class="vp-audit-window" data-vpa-host></div></div></div>`;
    }
    if (md.type === "password") body = `<p class="vp-login-hint">Entrégala por un canal seguro: se pide cambiarla al entrar. No se vuelve a mostrar.</p>
      <label class="vp-field">Clave temporal<span class="vp-inline"><input readonly value="${h(md.password)}" data-vpx-copy-value><button class="vp-btn vp-btn-sm" type="button" data-vpx-copy-password>Copiar</button></span></label>`;
    else if (md.type === "create") body = `${err}<form class="vp-form-grid" data-vpx-create-form>
      <label class="vp-field">Nombre del encargado<input name="full_name" required></label><label class="vp-field">Email<input name="email" type="email" required></label>
      <label class="vp-field">Clave temporal<span class="vp-inline"><input name="password" autocomplete="new-password" value="${h(md.password || "")}"></span></label>
      <button class="vp-btn vp-btn-primary" type="submit">Crear acceso maestro</button></form>`;
    else if (md.type === "reset") body = `<p class="vp-login-hint">Genera una clave temporal para este acceso; la actual deja de servir.</p>${err}
      <label class="vp-field">Clave (opcional; vacía = la genera el servidor)<input data-vpx-reset-input autocomplete="new-password"></label>
      <div class="vp-actions"><button class="vp-btn vp-btn-primary" type="button" data-vpx-confirm-go>Generar clave</button><button class="vp-btn" type="button" data-vpx-modal-close>Cancelar</button></div>`;
    else body = `<p class="vp-login-hint">${h(md.message)}</p>${err}<div class="vp-actions"><button class="vp-btn ${md.danger ? "vp-btn-danger" : "vp-btn-primary"}" type="button" data-vpx-confirm-go>${h(md.cta || "Confirmar")}</button><button class="vp-btn" type="button" data-vpx-modal-close>Cancelar</button></div>`;
    return `<div class="vp-modal" data-vpx-modal><div class="vp-panel vp-modal-card" role="dialog" aria-modal="true">${head}${body}</div></div>`;
  }

  function view() {
    const v = model.view;
    const body = v === "health" ? healthView() : v === "landing" ? landingView() : v === "brand" ? brandView() : accessView();
    return body + modal(model.modal);
  }

  const FOCUS = ["[data-vpx-search]", "[data-vpx-social-search]"];
  function draw() {
    if (!ctx || !ctx.active() || !ctx.root()) return;
    const active = document.activeElement;
    const keep = active && active.matches && FOCUS.find((s) => active.matches(s));
    const caret = keep ? active.selectionStart : null;
    ctx.root().innerHTML = view();
    if (keep) { const el = ctx.root().querySelector(keep); if (el) { el.focus(); try { el.setSelectionRange(caret, caret); } catch (_) {} } }
    const auditHost = model.modal && model.modal.type === "audit" && ctx.root().querySelector ? ctx.root().querySelector("[data-vpa-host]") : null;
    if (auditHost && window.CxConsoleAudit) window.CxConsoleAudit.mountInto(auditHost, {});
    ctx.root().querySelectorAll && ctx.root().querySelectorAll("[data-vpx-meter]").forEach((el) => { el.style.width = `${Number(el.getAttribute("data-vpx-meter")) || 0}%`; }); // CSSOM
  }

  // ------------------------------------------------------------ carga
  async function loadAccess(force = false) {
    const a = model.access;
    if (a.loading) return;
    a.loading = true;
    try {
      if (!a.companies || force) a.companies = arr(await apiGet(`${API}/companies`));                         // C01
      const live = a.companies.filter((c) => !isArchived(c));
      await Promise.all(live.map(async (c) => {
        if (a.tab === "links") { if (!a.modules[c.id] || force) a.modules[c.id] = await apiGet(`${API}/companies/${c.id}/modules?enabled_only=false`).catch(() => []); } // F01
        else if (!a.users[c.id] || force) a.users[c.id] = await apiGet(`${API}/companies/${c.id}/users`).catch(() => []);              // U01
        draw();
      }));
      if (a.tab === "consola") {
        a.sessions = await consoleApi.sessions().catch((e) => ({ sessions: [], error: e.message }));
        a.passkeys = (await consoleApi.passkeys().catch(() => ({ passkeys: [] }))).passkeys || [];
      }
    } catch (error) { model.error = error.message; }
    finally { a.loading = false; draw(); }
  }

  async function loadHealth() {
    const s = model.health;
    s.status = await consoleApi.health().catch((e) => ({ ok: false, error: e.message }));
    s.security = await apiGet("/admin-v2/api/health/security").catch((e) => { s.error = e.message; return null; });
    s.audit = window.CxConsoleAudit ? await window.CxConsoleAudit.load({ limit: 5 }).catch((e) => ({ error: e.message })) : [];
    draw();
    if (ctx && ctx.params && ctx.params.focus === "audit" && ctx.root() && ctx.root().querySelector) {
      const el = ctx.root().querySelector("[data-vpx-audit-block]");
      if (el && el.scrollIntoView) el.scrollIntoView({ block: "start" });
    }
  }

  async function loadLanding() {
    const L = model.landing;
    try { L.data = await consoleApi.landing(L.filters); L.error = ""; } catch (error) { L.error = error.message; }
    draw();
  }

  async function loadSocial() {
    const S = model.social;
    try { S.data = await consoleApi.social(S.days); S.error = ""; } catch (error) { S.error = error.message; }
    draw();
  }

  // ------------------------------------------------------------ eventos
  function ask(title, message, run, opts = {}) { model.modal = { type: "confirm", title, message, run, ...opts }; draw(); }
  async function act(run, notice, after) {
    try { const out = await run(); model.modal = null; model.notice = notice; model.error = ""; if (after) await after(out); return out; }
    catch (error) { if (model.modal) model.modal.error = error.message; else model.error = error.message; return null; }
    finally { draw(); }
  }
  const generate = (seed) => (window.CxConsoleCompanies ? window.CxConsoleCompanies.generateTempPassword(seed) : `Clonexa-${seed}-${Math.random().toString(36).slice(2, 6)}!`);
  const reloadUsers = (cid) => async () => { model.access.users[cid] = arr(await apiGet(`${API}/companies/${cid}/users`).catch(() => [])); };
  const companyName = (cid) => ((model.access.companies || []).find((c) => c.id === cid) || {}).name || "la empresa";

  async function copy(text, label) {
    try { await navigator.clipboard.writeText(text); if (ctx) ctx.toast(label || "Copiado."); } catch (_) { if (ctx) ctx.toast("No se pudo copiar."); }
  }

  async function onClick(event) {
    const t = event.target;
    if (!t || !t.closest) return;
    if (!ctx || !ctx.active()) return;
    if (t.closest("[data-vpx-logout]")) {
      ask("Cerrar mi sesión", "¿Cerrar tu sesión de la consola en este equipo?", () => act(() => consoleApi.logout(), ""), { cta: "Cerrar sesión", danger: true });
      return;
    }
    const a = model.access;
    if (t.closest("[data-vpx-modal-close]")) { model.modal = null; draw(); return; }
    if (t.closest("[data-vpx-confirm-go]")) {
      const md = model.modal;
      if (md.type === "reset") {
        const typed = String((document.querySelector("[data-vpx-reset-input]") || {}).value || "").trim();
        const data = await act(() => companyWrites().resetPassword(md.cid, md.uid, typed), "Clave regenerada.", reloadUsers(md.cid));
        if (data) { model.modal = { type: "password", title: "Clave temporal", password: data.temporary_password || data.password || typed || "No devuelta" }; draw(); }
      } else if (md.run) md.run();
      return;
    }
    if (t.closest("[data-vpx-copy-password]")) { copy((document.querySelector("[data-vpx-copy-value]") || {}).value || "", "Clave copiada."); return; }
    const cp = t.closest("[data-vpx-copy]");
    if (cp) { copy(cp.getAttribute("data-vpx-copy"), "Link copiado."); return; }
    const tab = t.closest("[data-vpx-tab]");
    if (tab) { a.tab = tab.getAttribute("data-vpx-tab"); model.notice = ""; draw(); loadAccess(); return; }
    const kind = t.closest("[data-vpx-kind]");
    if (kind) { a.kind = kind.getAttribute("data-vpx-kind"); draw(); return; }
    if (t.closest("[data-vpx-no-owner]")) { a.onlyNoOwner = !a.onlyNoOwner; draw(); return; }
    const create = t.closest("[data-vpx-create]");
    if (create) { const cid = create.getAttribute("data-vpx-create"); model.modal = { type: "create", title: `Crear acceso maestro · ${companyName(cid)}`, cid, password: generate(companyName(cid)) }; draw(); return; }
    const reset = t.closest("[data-vpx-reset]");
    if (reset) { model.modal = { type: "reset", title: `Clave temporal · ${companyName(reset.getAttribute("data-vpx-reset"))}`, cid: reset.getAttribute("data-vpx-reset"), uid: reset.getAttribute("data-user") }; draw(); return; }
    const unlock = t.closest("[data-vpx-unlock]");
    if (unlock) { const cid = unlock.getAttribute("data-vpx-unlock"); ask("Desbloquear acceso", `Desbloquear este acceso de ${companyName(cid)}?`, () => act(() => companyWrites().unlockUser(cid, unlock.getAttribute("data-user")), "Acceso desbloqueado.", reloadUsers(cid))); return; }
    const st = t.closest("[data-vpx-status]");
    if (st) { const cid = st.getAttribute("data-vpx-status"); const status = st.getAttribute("data-status");
      ask(status === "active" ? "Activar acceso" : "Desactivar acceso", `${status === "active" ? "Activar" : "Desactivar"} este acceso de ${companyName(cid)}?`, () => act(() => companyWrites().setUserStatus(cid, st.getAttribute("data-user"), status), "Estado de acceso actualizado.", reloadUsers(cid)), { danger: status !== "active" }); return; }
    const closeAdmin = t.closest("[data-vpx-close-admin]");
    if (closeAdmin) {
      const key = closeAdmin.getAttribute("data-vpx-close-admin");
      const mine = a.sessions && key === a.sessions.current_session;
      ask("Cerrar sesión de la consola", mine ? "Es tu sesión actual: tendrás que volver a entrar." : "Cerrar esa sesión de la consola?",
        () => act(() => consoleApi.closeSession(key), "Sesión cerrada.", async () => { if (mine) window.location.href = "/admin-v2plus/login"; else a.sessions = await consoleApi.sessions(); }), { danger: true });
      return;
    }
    const pk = t.closest("[data-vpx-passkey-delete]");
    if (pk) { ask("Quitar huella", "Quitar esta llave de acceso? Ese equipo ya no podrá entrar con huella.", () => act(() => consoleApi.deletePasskey(pk.getAttribute("data-vpx-passkey-delete")), "Huella quitada.", async (d) => { a.passkeys = (d && d.passkeys) || []; }), { danger: true }); return; }
    if (t.closest("[data-vpx-audit-all]")) { model.modal = { type: "audit", title: "Auditoría · todos los registros" }; draw(); return; }
    if (t.closest("[data-vpx-health-refresh]")) { loadHealth(); if (ctx.reloadOverview) ctx.reloadOverview(); return; }
    if (t.closest("[data-vpx-landing-reset]")) { model.landing.filters = { days: "30", source: "", campaign: "", device: "" }; loadLanding(); return; }
    const ltab = t.closest("[data-vpx-landing-tab]");
    if (ltab) { model.landing.tab = ltab.getAttribute("data-vpx-landing-tab"); draw(); if (model.landing.tab === "redes" && !model.social.data) loadSocial(); return; }
    const sdays = t.closest("[data-vpx-social-days]");
    if (sdays) { model.social.days = sdays.getAttribute("data-vpx-social-days"); model.social.data = null; draw(); loadSocial(); }
  }

  function onInput(event) {
    const t = event.target;
    if (!ctx || !ctx.active() || !t || !t.matches) return;
    if (t.matches("[data-vpx-social-search]")) { model.social.query = t.value; draw(); return; }
    if (!t.matches("[data-vpx-search]")) return;
    model.access.query = t.value;
    draw();
  }

  function onSubmit(event) {
    const form = event.target;
    if (!ctx || !ctx.active() || !form || !form.matches) return;
    if (form.matches("[data-vpx-landing-form]")) {
      event.preventDefault();
      const d = new FormData(form);
      model.landing.filters = { days: String(d.get("days") || "30"), source: String(d.get("source") || ""), campaign: String(d.get("campaign") || ""), device: String(d.get("device") || "") };
      loadLanding();
      return;
    }
    if (form.matches("[data-vpx-create-form]")) {
      event.preventDefault();
      const md = model.modal;
      const d = new FormData(form);
      const fullName = String(d.get("full_name") || "").trim();
      const email = String(d.get("email") || "").trim().toLowerCase();
      const password = String(d.get("password") || "").trim() || generate(email || "empresa");
      if (!fullName || !email) { md.error = "Nombre y email del encargado son requeridos."; draw(); return; }
      act(() => companyWrites().createUser(md.cid, fullName, email, password), "Acceso maestro creado correctamente.", reloadUsers(md.cid))
        .then((done) => { if (done) { model.modal = { type: "password", title: "Clave temporal", password }; draw(); } });
    }
  }

  function make(viewName, loader) {
    return {
      mount(context) {
        ctx = context;
        model.view = viewName;
        model.notice = "";
        if (!bound && typeof document.addEventListener === "function") {
          document.addEventListener("click", onClick);
          document.addEventListener("input", onInput);
          document.addEventListener("submit", onSubmit);
          bound = true;
        }
        draw();
        if (loader) loader();
      },
      refreshPulse() { if (ctx && ctx.active() && viewName === "health" && !model.modal) draw(); },
    };
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.access = make("access", () => loadAccess());
  window.CxConsoleSections.health = make("health", loadHealth);
  window.CxConsoleSections.landing = make("landing", () => { loadLanding(); if (model.landing.tab === "redes") loadSocial(); });
  window.CxConsoleSections.brand = make("brand", null);
  window.CxConsoleAdmin = { model, view, consoleApi, owners, maestroTab, healthView, landingView, brandView, socialPane, groupSources, socialNetworkOf, viewBuckets, socialLink };
})();
