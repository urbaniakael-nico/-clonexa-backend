// Consola v2+ · Ficha de empresa, vistas (Fase 2b): Resumen visual, tablero
// de Módulos y mini paneles, y Usuarios y accesos sin el chorro de sesiones.
// Funciones PURAS: reciben datos y devuelven HTML (o un cuerpo a guardar).
// Las escrituras siguen en admin_v2plus_company.js con los mismos endpoints.
// Sin estilos ni scripts en línea (CSP de v2+): los colores de marca se
// pintan después por CSSOM (data-vpf-swatch).
(() => {
  "use strict";

  function h(value) {
    return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }
  const arr = (value) => (Array.isArray(value) ? value : []);

  // ------------------------------------------------------------ buscador
  // Ignora tildes, mayúsculas y signos; coincidencia parcial por palabras.
  function fold(value) {
    return String(value ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }
  function matches(query, ...fields) {
    const words = fold(query).split(" ").filter(Boolean);
    if (!words.length) return true;
    const hay = fold(fields.join(" "));
    const squashed = hay.replace(/ /g, "");
    return words.every((w) => hay.includes(w) || squashed.includes(w));
  }

  // Mismo alias canónico que el bloque R6B de Admin V2 (canonicalModuleCode022A).
  const ALIAS = {
    cotizacion: "cotizacion", cotizaciones: "cotizacion", quote: "cotizacion", quotes: "cotizacion", quotation: "cotizacion",
    presupuesto: "cotizacion", presupuestos: "cotizacion", nota: "notas", notas: "notas", notes: "notas", agenda: "notas",
    recordatorio: "notas", recordatorios: "notas", notas_agenda: "notas", notas_o_agenda: "notas", registro_venta: "registro_venta",
    registro_ventas: "registro_venta", sales_register: "registro_venta", cierre_dia: "day_closing", cierre_de_dia: "day_closing",
    day_closing: "day_closing", commercial_closing: "day_closing",
  };
  function canonicalCode(value) {
    const slug = fold(value).replace(/ /g, "_");
    return ALIAS[slug] || slug;
  }
  // Base del sistema: v2 no las asigna a un panel (SKIP_CODES de R6B).
  const BASE_CODES = new Set(["core", "core_settings", "mini_panel"]);

  const CATEGORY_LABELS = { hospitality: "Restaurante", core: "Núcleo", sales: "Ventas", crm: "CRM", workforce: "Personal",
    operations: "Operación", finance: "Finanzas", inventory: "Inventario", reports: "Reportes", bots: "Bots", general: "General" };
  function categoryLabel(category) {
    const key = fold(category).replace(/ /g, "_") || "general";
    return CATEGORY_LABELS[key] || String(category || "General").replace(/^./, (c) => c.toUpperCase());
  }

  function moduleList(rows) {
    return arr(rows).map((row) => {
      const m = row && row.module && typeof row.module === "object" ? row.module : row || {};
      const code = String(m.code || row.module_code || row.code || "");
      return { code, name: m.name || code, category: m.category || "general", enabled: row.enabled !== false, settings: row.settings || {} };
    }).filter((m) => m.code);
  }

  function filterModules(modules, query = "", filter = "todos") {
    return moduleList(modules).filter((m) => (filter === "encendidos" ? m.enabled : filter === "apagados" ? !m.enabled : true))
      .filter((m) => matches(query, m.name, m.code, m.category, categoryLabel(m.category)));
  }

  function groupByCategory(list) {
    const groups = new Map();
    list.forEach((m) => {
      const key = categoryLabel(m.category);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(m);
    });
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0], "es"));
  }

  // ------------------------------------------------------------ paneles
  const GENERAL_PANELS = [
    { type: "sales", label: "Ventas" }, { type: "store", label: "Tiendas" }, { type: "inventory", label: "Inventario", defaultMax: 5 },
    { type: "logistics", label: "Logística" }, { type: "call_center", label: "Call center", defaultMax: 30 },
    { type: "external", label: "Externo", defaultMax: 20 }, { type: "other", label: "Otro", defaultMax: 10 },
  ];
  const RESTAURANT_PANELS = [
    { type: "mesero", label: "Mesero" }, { type: "cocina", label: "Cocina" }, { type: "caja", label: "Caja" }, { type: "domicilios", label: "Domicilios" },
  ];

  function panelMax(value, type) {
    const def = GENERAL_PANELS.find((p) => p.type === type);
    const fallback = def && Number.isFinite(Number(def.defaultMax)) ? Number(def.defaultMax) : 10;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.min(50, Math.max(1, Math.round(parsed))) : Math.min(50, Math.max(1, fallback));
  }

  // Asignar/quitar un módulo en el borrador (copia), sin tocar link, máximos,
  // module_names ni claves desconocidas. Igual que el bloque R6B de v2: el
  // panel se crea con link y máximo por defecto si no existía.
  function clone(value) { return JSON.parse(JSON.stringify(value || {})); }

  function ensurePanel(config, type, companyId, origin) {
    const panels = config.panels && typeof config.panels === "object" ? config.panels : (config.panels = {});
    const current = panels[type] && typeof panels[type] === "object" ? panels[type] : {};
    panels[type] = { ...current,
      enabled: current.enabled === true,
      link: current.link || `${origin}/mini-panel/login?company_id=${encodeURIComponent(companyId)}&type=${encodeURIComponent(type)}`,
      modules: arr(current.modules).map(canonicalCode).filter((c, i, all) => c && all.indexOf(c) === i),
      max_users: panelMax(current.max_users ?? current.users_allowed, type) };
    return panels[type];
  }

  function assignModule(config, type, module, { companyId = "", origin = "" } = {}) {
    if (!module || !module.enabled) return { config, error: "Solo se asignan módulos encendidos en la empresa." };
    if (BASE_CODES.has(canonicalCode(module.code))) return { config, error: "Los módulos base no se asignan a un panel." };
    const next = clone(config);
    const panel = ensurePanel(next, type, companyId, origin);
    const code = canonicalCode(module.code);
    if (!panel.modules.includes(code)) panel.modules.push(code);
    next.module_names = { ...(next.module_names || {}), [code]: module.name || code };
    return { config: next, error: "" };
  }

  function unassignModule(config, type, code) {
    const next = clone(config);
    const panel = next.panels && next.panels[type];
    if (panel) panel.modules = arr(panel.modules).filter((c) => canonicalCode(c) !== canonicalCode(code));
    return next;
  }

  function setPanelEnabled(config, type, on, { companyId = "", origin = "" } = {}) {
    const next = clone(config);
    if (type === "*") { next.enabled = on; return next; }
    const panel = ensurePanel(next, type, companyId, origin);
    panel.enabled = on;
    if (on && !next.selected_panel) next.selected_panel = type;
    if (!(next.panels[next.selected_panel] && next.panels[next.selected_panel].enabled)) {
      next.selected_panel = (GENERAL_PANELS.find((p) => next.panels[p.type] && next.panels[p.type].enabled) || {}).type || type;
    }
    if (on) next.enabled = true;
    return next;
  }

  // Cuerpo a guardar: el mismo de saveRemote de Admin V2, conservando además
  // cualquier clave de mini_panel_modules que la consola no conoce.
  function miniPanelsBody(config, nowIso) {
    const c = config && typeof config === "object" ? config : {};
    return { settings: { mini_panel_modules: { ...c, enabled: c.enabled === true, selected_panel: c.selected_panel || "",
      panels: c.panels || {}, module_names: c.module_names || {}, updated_at: nowIso || new Date().toISOString() } } };
  }

  // Paneles de restaurante: mesero/cocina/caja son "segmentos" del módulo
  // waiter_ordering (settings.segments.{tipo}.enabled, igual que Admin V2);
  // domicilios es el módulo domicilios_whatsapp y lo atiende la caja.
  function restaurantState(modules) {
    const list = moduleList(modules);
    const wo = list.find((m) => fold(m.code) === "waiter ordering");
    const dom = list.find((m) => fold(m.code) === "domicilios whatsapp");
    const segments = wo && wo.settings && typeof wo.settings.segments === "object" && wo.settings.segments ? wo.settings.segments : {};
    return {
      waiterOrdering: Boolean(wo && wo.enabled), waiterOrderingPresent: Boolean(wo),
      domicilios: Boolean(dom && dom.enabled), domiciliosPresent: Boolean(dom), segments,
    };
  }

  // Cuerpo para encender/apagar un segmento: mismo endpoint que el formulario
  // de pedidos por mesero de Admin V2 (POST …/modules/waiter_ordering/activate).
  // El servidor mezcla settings por clave, así que se manda SOLO "segments",
  // completo y con cada segmento intacto salvo su "enabled".
  function segmentBody(segments, type, on) {
    const next = clone(segments);
    ["mesero", "cocina", "caja"].forEach((t) => {
      const raw = next[t] && typeof next[t] === "object" ? next[t] : {};
      next[t] = { ...raw, enabled: raw.enabled === true, modules: arr(raw.modules) };
    });
    next[type] = { ...next[type], enabled: on };
    return { settings: { segments: next } };
  }

  // ------------------------------------------------------------ gráfico
  // Barras de ingresos por día (SVG propio, sin librerías ni estilos en línea).
  function barChart(days) {
    const list = arr(days);
    const total = list.reduce((sum, d) => sum + Number(d.logins || 0), 0);
    if (!list.length || !total) return `<div class="vp-empty vp-chart-empty" data-vpf-chart-empty>Sin ingresos en los últimos 14 días.</div>`;
    const max = Math.max(...list.map((d) => Number(d.logins || 0)), 1);
    const W = 280, H = 96, gap = 4;
    const bw = (W - gap * (list.length - 1)) / list.length;
    const bars = list.map((d, i) => {
      const v = Number(d.logins || 0);
      const bh = v ? Math.max(3, Math.round((v / max) * (H - 18))) : 0;
      const x = (i * (bw + gap)).toFixed(1);
      const label = `${d.date}: ${v} ingreso${v === 1 ? "" : "s"}`;
      return `<g><title>${h(label)}</title><rect class="vp-bar ${i === list.length - 1 ? "is-today" : ""}" x="${x}" y="${H - 14 - bh}" width="${bw.toFixed(1)}" height="${bh}" rx="2"></rect>`
        + `<rect class="vp-bar-base" x="${x}" y="${H - 13}" width="${bw.toFixed(1)}" height="2"></rect></g>`;
    }).join("");
    const first = list[0].date.slice(5).split("-").reverse().join("/");
    const last = list[list.length - 1].date.slice(5).split("-").reverse().join("/");
    return `<svg class="vp-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Ingresos por día, últimos 14 días: ${h(total)} en total">${bars}`
      + `<text class="vp-chart-axis" x="0" y="${H}">${h(first)}</text><text class="vp-chart-axis" x="${W}" y="${H}" text-anchor="end">${h(last)}</text></svg>`
      + `<p class="vp-chart-total"><b>${h(total)}</b> ingresos · máximo ${h(max)} en un día</p>`;
  }

  // ------------------------------------------------------------ resumen
  const STATE = { conectada: "Conectada", activa_hoy: "Activa hoy", sin_actividad_hoy: "Sin actividad hoy", dormida: "Dormida", riesgo: "En riesgo", inactiva: "Inactiva" };
  const OWNER_ROLES = new Set(["company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"]);

  function people(users) {
    const list = arr(users);
    const active = list.filter((u) => String(u.status || "").toLowerCase() === "active");
    const owner = active.some((u) => OWNER_ROLES.has(String(u.role || "").toLowerCase()));
    return { total: list.length, active: active.length, owner };
  }

  function warnings({ company, pulse, users, modules, activity }) {
    const out = [];
    const p = people(users);
    const status = String((company && company.status) || "").toLowerCase();
    const on = moduleList(modules).filter((m) => m.enabled).length;
    if (users && !p.owner && status === "active") out.push({ kind: "risk", text: "Sin dueño con acceso: nadie puede administrar la empresa." });
    if (status === "inactive" && on) out.push({ kind: "risk", text: `Inactiva con ${on} módulo${on === 1 ? "" : "s"} encendido${on === 1 ? "" : "s"}.` });
    if (pulse && pulse.state === "dormida") out.push({ kind: "dormant", text: `Dormida · ${pulse.state_reason || "más de 7 días sin señal"}.` });
    const stale = activity && activity.sessions ? Number(activity.sessions.stale || 0) : 0;
    if (stale) out.push({ kind: "dormant", text: `${stale} ${stale === 1 ? "sesión" : "sesiones"} vieja${stale === 1 ? "" : "s"} sin cerrar (más de 24 h sin actividad).` });
    return out;
  }

  function card(title, body, extra = "") {
    return `<section class="vp-panel vp-section vp-sum-card ${extra}"><h2>${h(title)}</h2>${body}</section>`;
  }

  function summary(data) {
    const { company: c, pulse: p, modules, users, experience, activity, audit, links, since, kind } = data;
    const b = (experience && (experience.branding || experience.company_branding)) || {};
    const logo = String(b.logo_url || "");
    const showLogo = /^https:\/\//i.test(logo) || (logo.startsWith("/") && !logo.startsWith("//")) || /^data:image\/(png|jpeg|webp);base64,/i.test(logo);
    const list = moduleList(modules || []);
    const on = list.filter((m) => m.enabled);
    const state = p ? p.state : (String(c.status).toLowerCase() === "inactive" ? "inactiva" : "");
    const pe = people(users);
    const sinceText = (iso) => (since ? since(iso) : iso || "—");

    const identity = `<section class="vp-panel vp-sum-identity">
      ${showLogo ? `<img class="vp-sum-logo" src="${h(logo)}" alt="Logo de ${h(c.name)}">` : `<span class="vp-sum-logo vp-initials">${h(String(c.name || "?").slice(0, 2).toUpperCase())}</span>`}
      <div class="vp-sum-id"><h2>${h(c.name)}</h2>
        <p class="vp-ficha-meta"><b>${h(kind === "demo" ? "Demo" : "Registrada")}</b> · ${h(String(c.status).toLowerCase() === "active" ? "Activa" : String(c.status).toLowerCase() === "inactive" ? "Inactiva" : "Archivada")} · Plan ${h((p && p.plan) || c.plan || "—")}</p>
        <div class="vp-sum-colors" aria-label="Colores de marca">${[["Primario", b.primary_color], ["Secundario", b.secondary_color], ["Fondo", b.background_color]]
          .map(([label, value]) => `<span class="vp-color-dot" data-vpf-swatch="${h(value || "")}" title="${h(label)} ${h(value || "")}"></span>`).join("")}</div>
      </div>
      <div class="vp-sum-light vp-light-${h(state || "na")}" role="status"><span class="vp-dot vp-dot-${h(state || "inactiva")}" aria-hidden="true"></span>
        <b>${h(STATE[state] || "Sin datos")}</b><small>${h((p && p.state_reason) || "")}</small></div>
    </section>`;

    const groups = groupByCategory(on);
    const modulesCard = card("Módulos encendidos", modules === null ? `<p class="vp-loading">Cargando…</p>` : `
      <p class="vp-login-hint"><b>${h(on.length)}</b> de ${h(list.length)} encendidos</p>
      <div class="vp-sum-groups">${groups.map(([label, items]) => `<div><small class="vp-sum-group">${h(label)}</small>
        <div class="vp-chip-row">${items.map((m) => `<button class="vp-mini-chip" type="button" data-vpf-goto="modulos" title="${h(m.code)}">${h(m.name)}</button>`).join("")}</div></div>`).join("")
        || `<div class="vp-empty">Ningún módulo encendido.</div>`}</div>`);

    const panelCards = (data.panels || []).filter((x) => x.on);
    const panelsCard = card("Mini paneles", panelCards.length ? `<div class="vp-sum-panels">${panelCards.map((x) => `
      <div class="vp-sum-panel"><b>${h(x.label)}</b><small>${h(x.users)} usuario${x.users === 1 ? "" : "s"}</small>
        ${x.link ? `<button class="vp-btn vp-btn-sm" type="button" data-vpf-copy="${h(x.link)}">Copiar link</button>` : `<small class="vp-mono-muted">${h(x.note || "")}</small>`}</div>`).join("")}</div>`
      : `<div class="vp-empty">Ningún mini panel encendido.</div>`);

    const quick = card("Accesos rápidos", `<ul class="vp-quick-list">${arr(links).map((l) => `
      <li><span><b>${h(l.title)}</b><small class="vp-mono-muted">${h(l.href)}</small></span><button class="vp-btn vp-btn-sm" type="button" data-vpf-copy="${h(l.href)}">Copiar</button></li>`).join("")}</ul>
      <a class="vp-btn vp-btn-primary" href="/client?company_id=${encodeURIComponent(c.id)}" target="_blank" rel="noopener">Entrar como empresa</a>`, "vp-sum-scroll");

    const peopleCard = card("Personas", users === null ? `<p class="vp-loading">Cargando…</p>` : `<div class="vp-kv-grid">
      <div class="vp-kv"><span>Usuarios activos</span><strong>${h(pe.active)} de ${h(pe.total)}</strong></div>
      <div class="vp-kv"><span>Dueño con acceso</span><strong class="${pe.owner ? "vp-yes" : "vp-no"}">${pe.owner ? "Sí" : "No"}</strong></div>
      <div class="vp-kv"><span>Última conexión</span><strong>${h(p ? sinceText(p.last_real_signal_at) : "—")}</strong></div></div>`);

    const changes = card("Últimos cambios", audit === null ? `<p class="vp-loading">Cargando…</p>` : arr(audit).length ? `<ul class="vp-actions-list">${arr(audit).slice(0, 5).map((e) => `
      <li class="vp-action"><b class="vp-mono">${h(e.method)} ${h(String(e.path || "").replace(/^\/(api\/v1|admin-v2\/api)\/companies\/[^/]+/, "") || "/")}</b><small>${h(sinceText(e.at))} · ${h(e.status_code)} · ${h(e.actor || "")}</small></li>`).join("")}</ul>`
      : `<div class="vp-empty">Sin cambios registrados.</div>`);

    const warn = warnings(data);
    const warnCard = card("Avisos de esta empresa", warn.length ? `<ul class="vp-actions-list">${warn.map((w) => `<li class="vp-action vp-action-${w.kind}"><b>${h(w.text)}</b></li>`).join("")}</ul>`
      : `<div class="vp-empty vp-ok-text">Todo en orden.</div>`);

    const sws = data.switches;
    const switchesCard = card("Interruptores encendidos", sws === null || sws === undefined ? `<p class="vp-loading">Cargando…</p>` : `
      ${arr(sws).length ? `<div class="vp-chip-row">${arr(sws).map((s) => `<span class="vp-mini-chip is-on" title="${h(s.description)}">${h(s.label)}</span>`).join("")}</div>` : `<div class="vp-empty">Ningún interruptor encendido.</div>`}
      <button class="vp-btn vp-btn-sm" type="button" data-vpf-switches>Ver en Interruptores</button>`);

    const chart = card("Actividad · últimos 14 días", activity === null ? `<p class="vp-loading">Cargando…</p>` : barChart(activity && activity.days));

    return `<div class="vp-sum-grid">${identity}${warnCard}${chart}${modulesCard}${switchesCard}${panelsCard}${peopleCard}${changes}${quick}</div>`;
  }

  // ------------------------------------------------------------ tablero
  function moduleCard(m, assignable) {
    const reason = !m.enabled ? "Apagado en la empresa: enciéndelo para asignarlo." : BASE_CODES.has(canonicalCode(m.code)) ? "Módulo base: no se asigna a un panel." : "";
    return `<article class="vp-mod ${m.enabled ? "is-on" : "is-off"}" ${assignable && !reason ? `draggable="true" data-vpf-drag="${h(m.code)}"` : ""} title="${h(reason || "Arrástralo a un panel general para asignarlo")}">
      <span class="vp-mod-text"><b>${h(m.name)}</b><small class="vp-mono">${h(m.code)}</small></span>
      <button class="vp-switch-btn ${m.enabled ? "is-on" : ""}" type="button" role="switch" aria-checked="${m.enabled}" aria-label="${m.enabled ? "Apagar" : "Encender"} ${h(m.name)}"
        data-vpf-module="${h(m.code)}" data-action="${m.enabled ? "deactivate" : "activate"}"><span></span></button>
    </article>`;
  }

  function modulesZone(modules, ui) {
    const list = moduleList(modules);
    const shown = filterModules(modules, ui.query, ui.filter);
    const n = { todos: list.length, encendidos: list.filter((m) => m.enabled).length, apagados: list.filter((m) => !m.enabled).length };
    const collapsed = ui.collapsed || {};
    return `<section class="vp-panel vp-section vp-zone" aria-label="Módulos de la empresa">
      <h2>Módulos de la empresa</h2>
      <input class="vp-search" type="search" placeholder="Buscar por nombre, código o categoría" value="${h(ui.query || "")}" data-vpf-mod-search aria-label="Buscar módulo">
      <div class="vp-chips" role="group" aria-label="Filtrar módulos">${[["todos", "Todos"], ["encendidos", "Encendidos"], ["apagados", "Apagados"]].map(([key, label]) => `
        <button class="vp-chip ${ui.filter === key ? "is-active" : ""}" type="button" aria-pressed="${ui.filter === key}" data-vpf-mod-filter="${key}">${label}<b>${h(n[key])}</b></button>`).join("")}</div>
      <div class="vp-zone-scroll" data-vpf-mod-list>${shown.length ? groupByCategory(shown).map(([label, items]) => `
        <div class="vp-group"><button class="vp-group-head" type="button" data-vpf-group="${h(label)}" aria-expanded="${!collapsed[label]}">${collapsed[label] ? "▸" : "▾"} ${h(label)} <small>${h(items.filter((m) => m.enabled).length)}/${h(items.length)}</small></button>
          ${collapsed[label] ? "" : `<div class="vp-mod-grid">${items.map((m) => moduleCard(m, true)).join("")}</div>`}</div>`).join("")
        : `<div class="vp-empty" data-vpf-mod-empty>Ningún módulo coincide con «${h(ui.query || "")}».</div>`}</div>
    </section>`;
  }

  function panelChips(codes, names, removable, type) {
    return arr(codes).length ? `<div class="vp-chip-row">${arr(codes).map((code) => `<span class="vp-mini-chip">${h((names && names[code]) || code)}${removable
      ? ` <button class="vp-chip-x" type="button" data-vpf-unassign="${h(type)}" data-code="${h(code)}" aria-label="Quitar ${h((names && names[code]) || code)}">×</button>` : ""}</span>`).join("")}</div>`
      : `<small class="vp-mono-muted">Sin módulos asignados</small>`;
  }

  function panelsZone(data) {
    const { config, present, counts, rest, companyId, origin, ui } = data;
    // Nombre legible del chip: module_names guardado y, si falta, el nombre del módulo.
    const names = {};
    moduleList(data.modules || []).forEach((m) => { names[canonicalCode(m.code)] = m.name; });
    Object.assign(names, config.module_names || {});
    const users = (type) => (counts && counts[type] ? counts[type].users : 0);
    const restaurant = RESTAURANT_PANELS.map((def) => {
      let on = false, link = "", note = "", action = "";
      if (def.type === "domicilios") {
        on = rest.domicilios;
        note = rest.domiciliosPresent || on ? "Lo atiende la Caja. El cliente entra con un link personal por WhatsApp." : "Requiere el módulo Domicilios por WhatsApp.";
        action = `<button class="vp-btn vp-btn-sm" type="button" data-vpf-module="domicilios_whatsapp" data-action="${on ? "deactivate" : "activate"}">${on ? "Apagar módulo" : "Encender módulo"}</button>`;
      } else {
        on = rest.waiterOrdering && rest.segments[def.type] && rest.segments[def.type].enabled === true;
        link = `${origin}/mini-panel/${def.type}/login?company_id=${encodeURIComponent(companyId)}`;
        note = rest.waiterOrdering ? "" : "Requiere el módulo Pedidos por mesero (waiter_ordering).";
        action = rest.waiterOrdering ? `<button class="vp-btn vp-btn-sm" type="button" data-vpf-segment="${def.type}" data-on="${on ? "0" : "1"}">${on ? "Apagar" : "Encender"}</button>` : "";
      }
      const mods = def.type !== "domicilios" && rest.segments[def.type] ? arr(rest.segments[def.type].modules) : [];
      return `<article class="vp-panel-card ${on ? "is-on" : ""}" data-vpf-panel-card="${def.type}">
        <header><b>${h(def.label)}</b><span class="vp-state-pill ${on ? "is-on" : ""}">${on ? "Encendido" : "Apagado"}</span></header>
        <small>${def.type === "domicilios" ? `${h(users("caja"))} usuario(s) de caja` : `${h(users(def.type))} usuario${users(def.type) === 1 ? "" : "s"}`}</small>
        ${note ? `<small class="vp-mono-muted">${h(note)}</small>` : ""}
        ${def.type !== "domicilios" ? panelChips(mods, names, false, def.type) : ""}
        <div class="vp-actions">${link ? `<button class="vp-btn vp-btn-sm" type="button" data-vpf-copy="${h(link)}">Copiar link</button>` : ""}${action}</div>
      </article>`;
    }).join("");

    const general = !present ? `<div class="vp-empty" data-vpf-no-mini>Esta empresa no tiene encendido el módulo de mini paneles (mini_panel). Enciéndelo en la lista de módulos para usar los paneles generales.</div>`
      : GENERAL_PANELS.map((def) => {
        const panel = (config.panels && config.panels[def.type]) || {};
        const on = config.enabled === true && panel.enabled === true;
        const link = panel.link || `${origin}/mini-panel/login?company_id=${encodeURIComponent(companyId)}&type=${encodeURIComponent(def.type)}`;
        return `<article class="vp-panel-card vp-drop ${on ? "is-on" : ""}" data-vpf-drop="${def.type}" aria-label="Panel ${h(def.label)}">
          <header><b>${h(def.label)}</b><span class="vp-state-pill ${on ? "is-on" : ""}">${on ? "Encendido" : "Apagado"}</span></header>
          <small>${h(users(def.type))} usuario${users(def.type) === 1 ? "" : "s"} · máx. ${h(panelMax(panel.max_users ?? panel.users_allowed, def.type))}</small>
          ${panelChips(panel.modules, names, true, def.type)}
          <div class="vp-actions"><button class="vp-btn vp-btn-sm" type="button" data-vpf-pick="${def.type}">+ Añadir módulo</button>
            <button class="vp-btn vp-btn-sm" type="button" data-vpf-copy="${h(link)}">Copiar link</button>
            <button class="vp-btn vp-btn-sm" type="button" data-vpf-panel-toggle="${def.type}" data-on="${on ? "0" : "1"}">${on ? "Apagar" : "Encender"}</button></div>
        </article>`;
      }).join("");

    return `<section class="vp-panel vp-section vp-zone" aria-label="Mini paneles">
      <div class="vp-zone-head"><h2>Mini paneles</h2>
        ${ui.dirty ? `<span class="vp-dirty" role="status">Cambios sin guardar</span><button class="vp-btn vp-btn-sm" type="button" data-vpf-discard>Descartar</button><button class="vp-btn vp-btn-sm vp-btn-primary" type="button" data-vpf-save-panels>Guardar cambios</button>` : ""}</div>
      ${ui.error ? `<div class="vp-alert" role="alert"><span>${h(ui.error)}</span></div>` : ""}
      <div class="vp-zone-scroll">
        <h3 class="vp-subtitle">Restaurante</h3><div class="vp-panel-grid">${restaurant}</div>
        <h3 class="vp-subtitle">Generales ${present ? `<button class="vp-btn vp-btn-sm" type="button" data-vpf-panel-toggle="*" data-on="${config.enabled ? "0" : "1"}">${config.enabled ? "Apagar todos" : "Encender mini paneles"}</button>` : ""}</h3>
        <div class="vp-panel-grid">${general}</div>
      </div>
    </section>`;
  }

  function picker(modules, ui) {
    if (!ui.pick) return "";
    const label = (GENERAL_PANELS.find((p) => p.type === ui.pick) || {}).label || ui.pick;
    const list = filterModules(modules, ui.pickQuery || "", "todos");
    return `<div class="vp-modal" data-vpf-modal><div class="vp-panel vp-modal-card" role="dialog" aria-modal="true" aria-label="Añadir módulo a ${h(label)}">
      <div class="vp-modal-head"><h2>Añadir módulo a ${h(label)}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpf-modal-close aria-label="Cerrar">✕</button></div>
      <input class="vp-search" type="search" placeholder="Buscar módulo" value="${h(ui.pickQuery || "")}" data-vpf-pick-search aria-label="Buscar módulo para asignar">
      <ul class="vp-actions-list vp-pick-list" data-vpf-pick-list>${list.map((m) => {
        const reason = !m.enabled ? "Apagado en la empresa" : BASE_CODES.has(canonicalCode(m.code)) ? "Módulo base" : "";
        return `<li class="vp-action vp-toggle-row ${reason ? "is-disabled" : ""}"><b>${h(m.name)}</b><small class="vp-mono">${h(m.code)}${reason ? ` · ${h(reason)}` : ""}</small>
          <button class="vp-btn vp-btn-sm" type="button" data-vpf-assign="${h(m.code)}" ${reason ? "disabled" : ""}>Añadir</button></li>`;
      }).join("") || `<li class="vp-empty">Ningún módulo coincide.</li>`}</ul>
    </div></div>`;
  }

  // ------------------------------------------------------------ sesiones
  function sessionsCard(summaryData, since) {
    const s = summaryData || {};
    return `<div class="vp-sess-summary"><div><b>${h(s.open_recent ?? 0)}</b> abiertas · <b>${h(s.connected_now ?? 0)}</b> conectadas ahora · última ${h(s.last_seen_at ? (since ? since(s.last_seen_at) : s.last_seen_at) : "—")}
      ${s.stale ? `<br><small class="vp-mono-muted">${h(s.stale)} sin actividad (más de ${h(s.recent_hours || 24)} h)</small>` : ""}</div>
      <div class="vp-actions"><button class="vp-btn vp-btn-sm vp-btn-danger" type="button" data-vpf-close-all>Cerrar todas</button>
        <button class="vp-btn vp-btn-sm" type="button" data-vpf-sessions-toggle>Ver detalle</button></div></div>`;
  }

  function sessionsTable(sessions, ui, since) {
    const PAGE = 10;
    const list = arr(sessions).filter((s) => matches(ui.query || "", s.subject_label, s.scope, s.status, s.ip_address));
    const pages = Math.max(1, Math.ceil(list.length / PAGE));
    const page = Math.min(Math.max(1, ui.page || 1), pages);
    const rows = list.slice((page - 1) * PAGE, page * PAGE);
    return `<div class="vp-sess-detail">
      <input class="vp-search" type="search" placeholder="Buscar por usuario, panel o IP" value="${h(ui.query || "")}" data-vpf-sess-search aria-label="Buscar sesión">
      <div class="vp-table-wrap vp-zone-scroll"><table class="vp-table vp-table-compact"><thead><tr><th>Quién</th><th>Panel</th><th>Estado</th><th>Última actividad</th><th>IP</th><th><span class="sr-only">Acciones</span></th></tr></thead><tbody>
        ${rows.map((s) => `<tr><td>${h(s.subject_label || "—")}</td><td>${h(s.scope)}</td><td>${h(s.status)}</td><td class="vp-mono">${h(since ? since(s.last_seen_at) : s.last_seen_at)}</td><td class="vp-mono">${h(s.ip_address || "")}</td>
          <td>${String(s.status).toLowerCase() === "active" ? `<button class="vp-btn vp-btn-sm" type="button" data-vpf-close-session="${h(s.session_key)}">Cerrar</button>` : ""}</td></tr>`).join("")
          || `<tr><td colspan="6"><div class="vp-empty">Sin sesiones${ui.query ? " que coincidan" : ""}.</div></td></tr>`}
      </tbody></table></div>
      <div class="vp-pager"><button class="vp-btn vp-btn-sm" type="button" data-vpf-sess-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>‹ Anterior</button>
        <span>Página ${h(page)} de ${h(pages)} · ${h(list.length)} sesiones</span>
        <button class="vp-btn vp-btn-sm" type="button" data-vpf-sess-page="${page + 1}" ${page >= pages ? "disabled" : ""}>Siguiente ›</button></div>
    </div>`;
  }

  window.CxFicha = {
    fold, matches, canonicalCode, moduleList, filterModules, groupByCategory, categoryLabel, assignModule, unassignModule,
    setPanelEnabled, miniPanelsBody, restaurantState, segmentBody, barChart, summary, warnings, people, modulesZone, panelsZone,
    picker, sessionsCard, sessionsTable, GENERAL_PANELS, RESTAURANT_PANELS, BASE_CODES,
  };
})();
