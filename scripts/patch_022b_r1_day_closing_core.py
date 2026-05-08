from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_day_closing.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaDayClosingCore022BR1() {
  "use strict";

  if (window.__CLONEXA_022B_R1_DAY_CLOSING__) return;
  window.__CLONEXA_022B_R1_DAY_CLOSING__ = true;

  const API = "/api/v1";
  const LANG_KEY = "clonexa_client_language";

  const TXT = {
    es: {
      dashboard: "Dashboard",
      settings: "Ajustes",
      logout: "Cerrar sesión",
      activeTenant: "Tenant activo",

      eyebrow: "Módulo cierre operativo",
      title: "Cierre de día",
      subtitle: "Resumen operativo diario configurable según los módulos activos de esta empresa.",
      live: "PRE-CIERRE",

      back: "Volver",
      refresh: "Actualizar",
      exportCsv: "CSV",
      saveDraft: "Guardar pre-cierre",

      control: "Control de cierre",
      date: "Fecha",
      responsible: "Responsable",
      status: "Estado",
      statusDraft: "Preliminar",
      notes: "Observaciones del día",
      notesPlaceholder: "Escribe pendientes, novedades, alertas o decisiones del cierre...",
      draftSaved: "Pre-cierre guardado localmente.",
      noData: "Sin datos disponibles para este bloque.",

      summary: "Resumen ejecutivo",
      activeModules: "módulos activos",
      dataSource: "Fuente: módulos activos de la empresa",

      workforce: "Workforce",
      workforceTitle: "Personal y turnos",
      activeStaff: "Personal activo",
      activeNow: "Activos ahora",
      pausedNow: "En pausa",
      periodEvents: "Eventos del día",
      closedShifts: "Turnos cerrados",

      gps: "GPS",
      gpsTitle: "Ubicación y perímetros",
      locations: "Ubicaciones enviadas",
      inside: "Dentro de perímetro",
      outside: "Fuera de perímetro",
      perimeters: "Perímetros activos",

      materials: "Materiales",
      materialsTitle: "Órdenes y movimientos",
      materialRequests: "Solicitudes del día",
      delivered: "Entregadas",
      returned: "Devueltas",
      consigned: "En consigna",
      pending: "Pendientes",

      inventory: "Inventario",
      inventoryTitle: "Disponibilidad",
      activeItems: "Items activos",
      lowStock: "Stock bajo",
      zeroStock: "Stock cero",
      stockUnits: "Unidades en stock",

      payroll: "Nómina",
      payrollTitle: "Estimado operativo",
      regularHours: "Horas ordinarias",
      extraHours: "Horas extra",
      gross: "Bruto",
      discounts: "Descuentos",
      estimatedTotal: "Total estimado",

      bots: "Bots",
      botsTitle: "Canales automáticos",
      botStatus: "Estado bot",
      configured: "Configurado",
      notConfigured: "No configurado",

      pendingBlocks: "Bloques futuros",
      pendingBlocksHelp: "Estos bloques aparecerán cuando la empresa active y construya esos módulos.",
      production: "Producción",
      field: "Operación en campo",
      retail: "Retail / ventas",
      commercial: "Cierre comercial",

      inactiveTitle: "Módulo no activo",
      inactiveMsg: "Cierre de día no está activo para esta empresa.",
      activateFromAdmin: "Actívalo desde Admin V2 > Empresa > Módulos.",

      loadError: "No se pudo cargar el cierre de día."
    },

    en: {
      dashboard: "Dashboard",
      settings: "Settings",
      logout: "Log out",
      activeTenant: "Active tenant",

      eyebrow: "Operational closing module",
      title: "Day closing",
      subtitle: "Configurable daily operational summary based on this company's active modules.",
      live: "PRE-CLOSE",

      back: "Back",
      refresh: "Refresh",
      exportCsv: "CSV",
      saveDraft: "Save pre-close",

      control: "Closing control",
      date: "Date",
      responsible: "Responsible",
      status: "Status",
      statusDraft: "Preliminary",
      notes: "Day notes",
      notesPlaceholder: "Write pending items, updates, alerts or closing decisions...",
      draftSaved: "Pre-close saved locally.",
      noData: "No data available for this block.",

      summary: "Executive summary",
      activeModules: "active modules",
      dataSource: "Source: company active modules",

      workforce: "Workforce",
      workforceTitle: "Staff and shifts",
      activeStaff: "Active staff",
      activeNow: "Active now",
      pausedNow: "On break",
      periodEvents: "Day events",
      closedShifts: "Closed shifts",

      gps: "GPS",
      gpsTitle: "Location and perimeters",
      locations: "Locations sent",
      inside: "Inside perimeter",
      outside: "Outside perimeter",
      perimeters: "Active perimeters",

      materials: "Materials",
      materialsTitle: "Orders and movements",
      materialRequests: "Day requests",
      delivered: "Delivered",
      returned: "Returned",
      consigned: "In consignment",
      pending: "Pending",

      inventory: "Inventory",
      inventoryTitle: "Availability",
      activeItems: "Active items",
      lowStock: "Low stock",
      zeroStock: "Zero stock",
      stockUnits: "Units in stock",

      payroll: "Payroll",
      payrollTitle: "Operational estimate",
      regularHours: "Regular hours",
      extraHours: "Extra hours",
      gross: "Gross",
      discounts: "Discounts",
      estimatedTotal: "Estimated total",

      bots: "Bots",
      botsTitle: "Automated channels",
      botStatus: "Bot status",
      configured: "Configured",
      notConfigured: "Not configured",

      pendingBlocks: "Future blocks",
      pendingBlocksHelp: "These blocks will appear when the company activates and builds those modules.",
      production: "Production",
      field: "Field operations",
      retail: "Retail / sales",
      commercial: "Commercial closing",

      inactiveTitle: "Module not active",
      inactiveMsg: "Day closing is not active for this company.",
      activateFromAdmin: "Activate it from Admin V2 > Company > Modules.",

      loadError: "Could not load day closing."
    },

    fr: {
      dashboard: "Tableau de bord",
      settings: "Configuration",
      logout: "Quitter",
      activeTenant: "Tenant actif",

      eyebrow: "Module de clôture opérationnelle",
      title: "Clôture du jour",
      subtitle: "Résumé opérationnel quotidien configurable selon les modules actifs de cette entreprise.",
      live: "PRÉ-CLÔTURE",

      back: "Retour",
      refresh: "Actualiser",
      exportCsv: "CSV",
      saveDraft: "Enregistrer la pré-clôture",

      control: "Contrôle de clôture",
      date: "Date",
      responsible: "Responsable",
      status: "Statut",
      statusDraft: "Préliminaire",
      notes: "Notes du jour",
      notesPlaceholder: "Écrivez les éléments en attente, nouveautés, alertes ou décisions de clôture...",
      draftSaved: "Pré-clôture enregistrée localement.",
      noData: "Aucune donnée disponible pour ce bloc.",

      summary: "Résumé exécutif",
      activeModules: "modules actifs",
      dataSource: "Source : modules actifs de l’entreprise",

      workforce: "Workforce",
      workforceTitle: "Personnel et services",
      activeStaff: "Personnel actif",
      activeNow: "Actifs maintenant",
      pausedNow: "En pause",
      periodEvents: "Événements du jour",
      closedShifts: "Services clôturés",

      gps: "GPS",
      gpsTitle: "Position et périmètres",
      locations: "Positions envoyées",
      inside: "Dans le périmètre",
      outside: "Hors périmètre",
      perimeters: "Périmètres actifs",

      materials: "Matériaux",
      materialsTitle: "Commandes et mouvements",
      materialRequests: "Demandes du jour",
      delivered: "Livrées",
      returned: "Retournées",
      consigned: "En consigne",
      pending: "En attente",

      inventory: "Inventaire",
      inventoryTitle: "Disponibilité",
      activeItems: "Articles actifs",
      lowStock: "Stock faible",
      zeroStock: "Stock zéro",
      stockUnits: "Unités en stock",

      payroll: "Paie",
      payrollTitle: "Estimation opérationnelle",
      regularHours: "Heures normales",
      extraHours: "Heures supplémentaires",
      gross: "Brut",
      discounts: "Remises",
      estimatedTotal: "Total estimé",

      bots: "Bots",
      botsTitle: "Canaux automatisés",
      botStatus: "Statut du bot",
      configured: "Configuré",
      notConfigured: "Non configuré",

      pendingBlocks: "Blocs futurs",
      pendingBlocksHelp: "Ces blocs apparaîtront lorsque l’entreprise activera et construira ces modules.",
      production: "Production",
      field: "Opérations terrain",
      retail: "Retail / ventes",
      commercial: "Clôture commerciale",

      inactiveTitle: "Module non actif",
      inactiveMsg: "La clôture du jour n’est pas active pour cette entreprise.",
      activateFromAdmin: "Activez-le depuis Admin V2 > Entreprise > Modules.",

      loadError: "Impossible de charger la clôture du jour."
    }
  };

  const MODULE_TITLES = {
    core: ["Núcleo", "Core", "Noyau"],
    core_settings: ["Ajustes", "Settings", "Configuration"],
    workforce: ["Personal", "Staff", "Personnel"],
    gps: ["GPS", "GPS", "GPS"],
    payroll: ["Nómina", "Payroll", "Paie"],
    bots: ["Bots", "Bots", "Bots"],
    inventory: ["Inventario", "Inventory", "Inventaire"],
    materials: ["Materiales", "Materials", "Matériaux"],
    crm: ["CRM Campo", "Field CRM", "CRM terrain"],
    kpis: ["KPIs", "KPIs", "KPIs"],
    reports: ["Reportes", "Reports", "Rapports"],
    day_closing: ["Cierre de día", "Day closing", "Clôture du jour"],
    commercial_closing: ["Cierre comercial", "Commercial closing", "Clôture commerciale"],
    field: ["Operación en campo", "Field operations", "Opérations terrain"],
    production: ["Producción", "Production", "Production"],
    retail: ["Retail", "Retail", "Retail"]
  };

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function t(key) {
    const l = lang();
    return TXT[l][key] || TXT.es[key] || key;
  }

  function moduleTitle(code, fallback) {
    const index = lang() === "en" ? 1 : lang() === "fr" ? 2 : 0;
    const arr = MODULE_TITLES[String(code || "").trim()];
    return arr ? arr[index] : fallback || String(code || "");
  }

  function h(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function number(value, decimals = 0) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return decimals ? "0.0" : "0";
    return n.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
  }

  function money(value) {
    const n = Number(value || 0);
    return n.toLocaleString(undefined, {
      style: "currency",
      currency: localStorage.getItem("clonexa_client_currency") || "USD",
      maximumFractionDigits: 2
    });
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function companyIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || params.get("tenant") || "";
  }

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });

    if (!response.ok) {
      let detail = "";
      try {
        const payload = await response.json();
        detail = payload.detail || payload.message || "";
      } catch (_) {}
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }

    if (response.status === 204) return null;
    return response.json();
  }

  function normalizeModule(row) {
    const source = row.module || row.module_ref || row.global_module || row;
    const code = String(source.code || source.module_code || row.module_code || row.code || "").trim();
    const enabled = row.enabled ?? source.enabled ?? row.is_active ?? source.is_active ?? true;

    return {
      code,
      enabled: !!enabled,
      title: source.name || source.title || code,
      category: source.category || row.category || "",
      raw: row
    };
  }

  async function loadCompanyContext(companyId) {
    const [companiesResult, modulesResult] = await Promise.allSettled([
      api("/companies"),
      api(`/companies/${encodeURIComponent(companyId)}/modules`)
    ]);

    const companies = companiesResult.status === "fulfilled" && Array.isArray(companiesResult.value)
      ? companiesResult.value
      : [];

    const company = companies.find((item) => item.id === companyId || item.company_id === companyId) || {
      id: companyId,
      company_id: companyId,
      name: document.querySelector(".client-company-name")?.textContent || "CLONEXA",
      slug: "tenant"
    };

    const modules = modulesResult.status === "fulfilled" && Array.isArray(modulesResult.value)
      ? modulesResult.value.map(normalizeModule).filter((item) => item.code && item.enabled)
      : [];

    return { company, modules, codes: new Set(modules.map((item) => item.code)) };
  }

  function noteKey(companyId, date) {
    return `clx_day_closing_notes_${companyId}_${date}`;
  }

  function draftKey(companyId, date) {
    return `clx_day_closing_draft_${companyId}_${date}`;
  }

  function readNotes(companyId, date) {
    return localStorage.getItem(noteKey(companyId, date)) || "";
  }

  function writeNotes(companyId, date, value) {
    localStorage.setItem(noteKey(companyId, date), String(value || ""));
  }

  async function loadDaySummary(companyId, codes, date) {
    const summary = {
      modules: Array.from(codes),
      employees: {},
      attendance: {},
      gps: {},
      materials: {},
      inventory: {},
      payroll: {},
      bot: {}
    };

    if (codes.has("kpis")) {
      try {
        const kpi = await api(`/kpis/companies/${encodeURIComponent(companyId)}/summary?preset=today&start_date=${encodeURIComponent(date)}&end_date=${encodeURIComponent(date)}`);
        Object.assign(summary, kpi || {});
      } catch (error) {
        summary.kpis_error = error.message || "kpis_error";
      }
    }

    if (codes.has("workforce") && !summary.employees?.active) {
      try {
        const employees = await api(`/employees?company_id=${encodeURIComponent(companyId)}&include_archived=true`);
        if (Array.isArray(employees)) {
          summary.employees = {
            ...(summary.employees || {}),
            total: employees.length,
            active: employees.filter((item) => String(item.status || "").toLowerCase() === "active").length,
            inactive: employees.filter((item) => String(item.status || "").toLowerCase() === "inactive").length,
            archived: employees.filter((item) => String(item.status || "").toLowerCase() === "archived").length
          };
        }
      } catch (error) {}
    }

    if (codes.has("materials")) {
      try {
        const materials = await api(`/materials/companies/${encodeURIComponent(companyId)}/requests?limit=800`);
        const rows = Array.isArray(materials) ? materials : Array.isArray(materials.requests) ? materials.requests : [];
        const dated = rows.filter((row) => String(row.created_at || row.requested_at || "").slice(0, 10) === date || !row.created_at);
        const group = (status) => dated.filter((row) => String(row.status || "").toLowerCase() === status).length;
        summary.materials = {
          ...(summary.materials || {}),
          total: summary.materials?.total ?? dated.length,
          pending: summary.materials?.pending ?? group("pending"),
          approved: summary.materials?.approved ?? group("approved"),
          delivered: summary.materials?.delivered ?? group("delivered"),
          returned: summary.materials?.returned ?? group("returned"),
          returned_partial: summary.materials?.returned_partial ?? group("returned_partial"),
          consigned: summary.materials?.consigned ?? group("consigned"),
          consigned_partial: summary.materials?.consigned_partial ?? group("consigned_partial")
        };
      } catch (error) {}
    }

    if (codes.has("inventory")) {
      try {
        const inventory = await api(`/inventory/companies/${encodeURIComponent(companyId)}/items?include_inactive=true&limit=1000`);
        const rows = Array.isArray(inventory) ? inventory : Array.isArray(inventory.items) ? inventory.items : [];
        summary.inventory = {
          ...(summary.inventory || {}),
          active: summary.inventory?.active ?? rows.filter((item) => String(item.status || "active").toLowerCase() === "active").length,
          low_stock: summary.inventory?.low_stock ?? rows.filter((item) => Number(item.current_stock || 0) <= Number(item.min_stock || 0) && Number(item.min_stock || 0) > 0).length,
          zero_stock: summary.inventory?.zero_stock ?? rows.filter((item) => Number(item.current_stock || 0) <= 0).length,
          total_stock_units: summary.inventory?.total_stock_units ?? rows.reduce((acc, item) => acc + Number(item.current_stock || 0), 0)
        };
      } catch (error) {}
    }

    if (codes.has("bots")) {
      try {
        const bot = await api(`/bots/companies/${encodeURIComponent(companyId)}/telegram`);
        summary.bot = {
          configured: !!bot?.configured,
          status: bot?.status || (bot?.configured ? "configured" : "not_configured")
        };
      } catch (error) {
        summary.bot = { configured: false, status: "error" };
      }
    }

    return summary;
  }

  function sidebar(company, modules, activeCode = "day_closing") {
    const visible = modules.filter((m) => !["core", "core_settings", "settings"].includes(m.code));

    return `
      <aside class="client-sidebar">
        <div class="client-logo">${h((company.name || "CLONEXA").slice(0, 2).toUpperCase())}</div>
        <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
        <div class="client-muted">${h(company.slug || "tenant")}</div>

        <nav class="client-nav">
          <button type="button" data-clx-day-dashboard>${h(t("dashboard"))}</button>
          ${visible.map((module) => `
            <button class="${module.code === activeCode ? "active" : ""}" type="button" data-client-module="${h(module.code)}">
              ${h(moduleTitle(module.code, module.title))}
            </button>
          `).join("")}
        </nav>

        <div class="client-footer-id">
          <strong>${h(t("activeTenant"))}</strong><br>${h(company.id || company.company_id || companyIdFromUrl())}
        </div>

        <button class="client-btn" type="button" id="clxOpenCoreSettings" style="width:100%;margin-top:14px">⚙ ${h(t("settings"))}</button>
        <button class="client-btn ghost" type="button" id="clxCoreLogout" style="width:100%;margin-top:10px">⏻ ${h(t("logout"))}</button>
      </aside>
    `;
  }

  function heroCard(label, value) {
    return `
      <div class="client-kpi">
        <span>${h(label)}</span>
        <strong>${h(value)}</strong>
      </div>
    `;
  }

  function row(label, value) {
    return `
      <div class="cx-day-row">
        <span>${h(label)}</span>
        <strong>${h(value)}</strong>
      </div>
    `;
  }

  function block(eyebrow, title, rows, searchable = "") {
    return `
      <section class="cx-day-block" data-day-searchable="${h(searchable)}">
        <div class="client-eyebrow">${h(eyebrow)}</div>
        <h2>${h(title)}</h2>
        <div class="cx-day-list">
          ${rows.length ? rows.join("") : `<div class="client-muted">${h(t("noData"))}</div>`}
        </div>
      </section>
    `;
  }

  function futureBlock(title) {
    return `<span class="client-badge ghost">${h(title)}</span>`;
  }

  function buildBlocks(summary, codes) {
    const employees = summary.employees || {};
    const attendance = summary.attendance || {};
    const gps = summary.gps || {};
    const materials = summary.materials || {};
    const inventory = summary.inventory || {};
    const payroll = summary.payroll || {};
    const bot = summary.bot || {};

    const blocks = [];

    if (codes.has("workforce")) {
      blocks.push(block(t("workforce"), t("workforceTitle"), [
        row(t("activeStaff"), number(employees.active)),
        row(t("activeNow"), number(attendance.active_now)),
        row(t("pausedNow"), number(attendance.paused_now)),
        row(t("periodEvents"), number(attendance.events)),
        row(t("closedShifts"), number(payroll.closed_shifts || attendance.closed_shifts))
      ], "workforce staff personal turnos asistencia"));
    }

    if (codes.has("gps")) {
      blocks.push(block(t("gps"), t("gpsTitle"), [
        row(t("locations"), number(gps.locations || gps.sent_location || gps.total)),
        row(t("inside"), number(gps.inside)),
        row(t("outside"), number(gps.outside)),
        row(t("perimeters"), number(gps.perimeters))
      ], "gps location perimeter"));
    }

    if (codes.has("materials")) {
      blocks.push(block(t("materials"), t("materialsTitle"), [
        row(t("materialRequests"), number(materials.total)),
        row(t("delivered"), number(materials.delivered)),
        row(t("returned"), number((materials.returned || 0) + (materials.returned_partial || 0))),
        row(t("consigned"), number((materials.consigned || 0) + (materials.consigned_partial || 0))),
        row(t("pending"), number(materials.pending))
      ], "materials requests orders"));
    }

    if (codes.has("inventory")) {
      blocks.push(block(t("inventory"), t("inventoryTitle"), [
        row(t("activeItems"), number(inventory.active)),
        row(t("lowStock"), number(inventory.low_stock)),
        row(t("zeroStock"), number(inventory.zero_stock)),
        row(t("stockUnits"), number(inventory.total_stock_units))
      ], "inventory stock"));
    }

    if (codes.has("payroll")) {
      blocks.push(block(t("payroll"), t("payrollTitle"), [
        row(t("regularHours"), number((payroll.regular_minutes || 0) / 60, 1)),
        row(t("extraHours"), number((payroll.extra_minutes || 0) / 60, 1)),
        row(t("gross"), money(payroll.gross_amount)),
        row(t("discounts"), money(payroll.discount_amount)),
        row(t("estimatedTotal"), money(payroll.net_amount))
      ], "payroll nomina hours"));
    }

    if (codes.has("bots")) {
      blocks.push(block(t("bots"), t("botsTitle"), [
        row(t("botStatus"), bot.configured ? t("configured") : t("notConfigured"))
      ], "bots telegram whatsapp"));
    }

    const futures = [];
    if (!codes.has("production")) futures.push(futureBlock(t("production")));
    if (!codes.has("field")) futures.push(futureBlock(t("field")));
    if (!codes.has("retail") && !codes.has("sales") && !codes.has("stores")) futures.push(futureBlock(t("retail")));
    if (!codes.has("commercial_closing")) futures.push(futureBlock(t("commercial")));

    blocks.push(`
      <section class="cx-day-block">
        <div class="client-eyebrow">${h(t("pendingBlocks"))}</div>
        <h2>${h(t("pendingBlocks"))}</h2>
        <p class="client-muted">${h(t("pendingBlocksHelp"))}</p>
        <div class="client-actions">${futures.join("")}</div>
      </section>
    `);

    return blocks.join("");
  }

  function buildCsv(company, date, summary, codes, notes) {
    const rows = [
      ["company", company.name || ""],
      ["company_id", company.id || company.company_id || companyIdFromUrl()],
      ["date", date],
      ["status", t("statusDraft")],
      ["modules", Array.from(codes).join("|")],
      ["notes", notes || ""],
      [],
      ["section", "metric", "value"]
    ];

    const pushGroup = (section, data = {}) => {
      Object.keys(data || {}).forEach((key) => {
        if (typeof data[key] === "object") return;
        rows.push([section, key, data[key]]);
      });
    };

    pushGroup("employees", summary.employees);
    pushGroup("attendance", summary.attendance);
    pushGroup("gps", summary.gps);
    pushGroup("materials", summary.materials);
    pushGroup("inventory", summary.inventory);
    pushGroup("payroll", summary.payroll);
    pushGroup("bot", summary.bot);

    return rows
      .map((row) => row.map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`).join(","))
      .join("\n");
  }

  function downloadCsv(company, date, summary, codes, notes) {
    const blob = new Blob([buildCsv(company, date, summary, codes, notes)], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_day_closing_${company.slug || company.name || "company"}_${date}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function ensureStyles() {
    if (document.getElementById("clx-day-closing-styles")) return;

    const style = document.createElement("style");
    style.id = "clx-day-closing-styles";
    style.textContent = `
      .cx-day-toolbar {
        display:grid;
        grid-template-columns: minmax(160px, 220px) minmax(160px, 1fr) minmax(160px, 220px);
        gap:14px;
        align-items:end;
        margin-top:18px;
      }

      .cx-day-toolbar label {
        display:grid;
        gap:8px;
        color:rgba(255,255,255,.72);
        font-weight:900;
        letter-spacing:.08em;
        text-transform:uppercase;
        font-size:12px;
      }

      .cx-day-toolbar input,
      .cx-day-toolbar textarea {
        width:100%;
        border:1px solid rgba(255,255,255,.14);
        background:rgba(0,0,0,.28);
        color:white;
        border-radius:16px;
        padding:13px 14px;
        font-weight:800;
        outline:none;
      }

      .cx-day-grid {
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
        gap:16px;
        margin-top:18px;
      }

      .cx-day-block {
        border:1px solid rgba(255,255,255,.11);
        background:linear-gradient(135deg,rgba(255,255,255,.07),rgba(255,0,180,.08));
        border-radius:24px;
        padding:22px;
        box-shadow:0 18px 48px rgba(0,0,0,.18);
        min-height:210px;
      }

      .cx-day-block h2 {
        margin:8px 0 16px;
      }

      .cx-day-list {
        display:grid;
        gap:10px;
      }

      .cx-day-row {
        display:flex;
        justify-content:space-between;
        gap:12px;
        align-items:center;
        border:1px solid rgba(255,255,255,.08);
        background:rgba(255,255,255,.06);
        padding:12px 14px;
        border-radius:14px;
      }

      .cx-day-row span {
        color:rgba(255,255,255,.76);
        font-weight:800;
      }

      .cx-day-row strong {
        color:white;
        font-weight:1000;
      }

      .cx-day-notes {
        min-height:110px;
        resize:vertical;
      }

      .client-badge.ghost {
        background:rgba(255,255,255,.08);
        color:rgba(255,255,255,.74);
        box-shadow:none;
      }

      @media (max-width: 900px) {
        .cx-day-toolbar {
          grid-template-columns:1fr;
        }
      }
    `;
    document.head.appendChild(style);
  }

  async function renderDayClosing() {
    const companyId = companyIdFromUrl();
    if (!companyId) return;

    ensureStyles();

    let context;
    try {
      context = await loadCompanyContext(companyId);
    } catch (error) {
      renderError(error);
      return;
    }

    const { company, modules, codes } = context;

    if (!codes.has("day_closing")) {
      renderInactive(company, modules);
      return;
    }

    const date = document.querySelector("[data-day-closing-date]")?.value || today();
    let summary = {};
    let loadError = "";

    try {
      summary = await loadDaySummary(companyId, codes, date);
      window.__clxDayClosingSummary = summary;
      window.__clxDayClosingContext = context;
    } catch (error) {
      loadError = error.message || t("loadError");
      summary = {};
    }

    const notes = readNotes(companyId, date);
    const totalModules = modules.filter((m) => !["core", "core_settings", "settings"].includes(m.code)).length;

    const heroCards = [
      heroCard(t("activeModules"), `${totalModules}`),
      heroCard(t("activeStaff"), number(summary.employees?.active)),
      heroCard(t("periodEvents"), number(summary.attendance?.events)),
      heroCard(t("materialRequests"), number(summary.materials?.total))
    ].join("");

    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
      <main class="client-shell" data-day-closing-root>
        <div class="client-layout">
          ${sidebar(company, modules, "day_closing")}

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">${h(t("eyebrow"))}</div>
              <h1 class="client-title">${h(t("title"))}</h1>
              <p class="client-muted">${h(t("subtitle"))}</p>

              <span class="client-badge" style="position:absolute;right:28px;top:28px">${h(t("live"))}</span>

              <div class="client-kpis">
                ${heroCards}
              </div>

              <div class="client-actions">
                <button class="client-btn" type="button" data-day-closing-refresh>${h(t("refresh"))}</button>
                <button class="client-btn" type="button" data-day-closing-save>${h(t("saveDraft"))}</button>
                <button class="client-btn" type="button" data-day-closing-export>${h(t("exportCsv"))}</button>
                <button class="client-btn" type="button" data-clx-day-dashboard>${h(t("back"))}</button>
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">${h(t("control"))}</div>
              <h2>${h(t("control"))}</h2>

              ${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}

              <div class="cx-day-toolbar">
                <label>
                  ${h(t("date"))}
                  <input type="date" data-day-closing-date value="${h(date)}">
                </label>

                <label>
                  ${h(t("responsible"))}
                  <input type="text" data-day-closing-responsible value="${h(company.name || "")}">
                </label>

                <label>
                  ${h(t("status"))}
                  <input type="text" value="${h(t("statusDraft"))}" readonly>
                </label>
              </div>

              <div style="margin-top:18px">
                <label style="display:grid;gap:8px;color:rgba(255,255,255,.72);font-weight:900;letter-spacing:.08em;text-transform:uppercase;font-size:12px">
                  ${h(t("notes"))}
                  <textarea class="cx-day-notes" data-day-closing-notes placeholder="${h(t("notesPlaceholder"))}">${h(notes)}</textarea>
                </label>
              </div>

              <p class="client-muted" style="margin-top:14px">${h(t("dataSource"))}</p>
            </section>

            <section class="client-panel">
              <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start">
                <div>
                  <div class="client-eyebrow">${h(t("summary"))}</div>
                  <h2>${h(t("summary"))}</h2>
                </div>
                <span class="client-badge">${h(totalModules)} ${h(t("activeModules"))}</span>
              </div>

              <div class="cx-day-grid">
                ${buildBlocks(summary, codes)}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }

  function renderInactive(company, modules) {
    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          ${sidebar(company, modules, "dashboard")}
          <section class="client-main">
            <section class="client-panel" style="max-width:900px;margin:12vh auto">
              <div class="client-eyebrow">${h(t("eyebrow"))}</div>
              <h1>${h(t("inactiveTitle"))}</h1>
              <p>${h(t("inactiveMsg"))}</p>
              <p class="client-muted">${h(t("activateFromAdmin"))}</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-clx-day-dashboard>${h(t("back"))}</button>
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }

  function renderError(error) {
    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
      <main class="client-shell">
        <section class="client-panel" style="max-width:900px;margin:12vh auto">
          <div class="client-eyebrow">CLONEXA</div>
          <h1>${h(t("loadError"))}</h1>
          <p>${h(error?.message || error)}</p>
        </section>
      </main>
    `;
  }

  function showNotice(message) {
    const target = document.querySelector("[data-day-closing-root] .client-panel");
    if (!target) return;

    const box = document.createElement("div");
    box.className = "personal-toast";
    box.textContent = message;
    target.prepend(box);

    setTimeout(() => box.remove(), 2600);
  }

  function handleDayModuleClick(event) {
    const trigger = event.target && event.target.closest && event.target.closest('[data-client-module="day_closing"]');
    if (!trigger) return;

    event.preventDefault();
    event.stopPropagation();
    if (event.stopImmediatePropagation) event.stopImmediatePropagation();

    renderDayClosing();
  }

  document.addEventListener("click", handleDayModuleClick, true);

  document.addEventListener("click", async (event) => {
    const target = event.target;

    if (target.closest && target.closest("[data-clx-day-dashboard]")) {
      event.preventDefault();
      window.location.href = `/client?company_id=${encodeURIComponent(companyIdFromUrl())}`;
      return;
    }

    if (target.closest && target.closest("[data-day-closing-refresh]")) {
      event.preventDefault();
      await renderDayClosing();
      return;
    }

    if (target.closest && target.closest("[data-day-closing-save]")) {
      event.preventDefault();
      const companyId = companyIdFromUrl();
      const date = document.querySelector("[data-day-closing-date]")?.value || today();
      const notes = document.querySelector("[data-day-closing-notes]")?.value || "";
      const responsible = document.querySelector("[data-day-closing-responsible]")?.value || "";

      writeNotes(companyId, date, notes);
      localStorage.setItem(draftKey(companyId, date), JSON.stringify({
        company_id: companyId,
        date,
        responsible,
        notes,
        saved_at: new Date().toISOString()
      }));

      showNotice(t("draftSaved"));
      return;
    }

    if (target.closest && target.closest("[data-day-closing-export]")) {
      event.preventDefault();
      const companyId = companyIdFromUrl();
      const date = document.querySelector("[data-day-closing-date]")?.value || today();
      const notes = document.querySelector("[data-day-closing-notes]")?.value || "";
      const context = window.__clxDayClosingContext || await loadCompanyContext(companyId);
      const summary = window.__clxDayClosingSummary || await loadDaySummary(companyId, context.codes, date);
      downloadCsv(context.company, date, summary, context.codes, notes);
      return;
    }
  }, true);

  document.addEventListener("change", async (event) => {
    if (event.target && event.target.matches && event.target.matches("[data-day-closing-date]")) {
      await renderDayClosing();
    }
  }, true);

  window.CLONEXA_RENDER_DAY_CLOSING = renderDayClosing;
})();
'''

js_path.write_text(js, encoding="utf-8")

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_day_closing\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE
)

# Insertar después de client.js y antes de i18n/core si existe.
matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE
))

if matches:
    first = matches[0]
    html = html[:first.end()] + '\n<script src="/client-static/client_day_closing.js?v=022BR1"></script>\n' + html[first.end():]
else:
    html = html.replace("</body>", '<script src="/client-static/client_day_closing.js?v=022BR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 022B-R1 external Day Closing module installed")
