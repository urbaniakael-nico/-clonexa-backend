
(function clonexaDayClosingSafe022BR4() {
  "use strict";

  window.CLONEXA_DAY_CLOSING_BUILD = "022B_R7_CLEAN_HARD_CUTOVER";

  if (window.__CLONEXA_022B_R4_DAY_CLOSING_SAFE__) return;
  window.__CLONEXA_022B_R4_DAY_CLOSING_SAFE__ = true;

  const API = "/api/v1";
  const LANG_KEY = "clonexa_client_language";

  const TXT = {
    es: {
      dashboard: "Dashboard",
      activeTenant: "Tenant activo",
      eyebrow: "Módulo cierre operativo",
      title: "Cierre de día",
      subtitle: "Genera el cierre operativo por fecha y jornada laboral. CLONEXA consolida personal, GPS, materiales, inventario y resúmenes enviados desde el bot.",
      badge: "CIERRE POR JORNADA",
      generate: "Generar cierre",
      save: "Guardar cierre",
      pdf: "PDF",
      csv: "CSV",
      back: "Volver",
      control: "Control de jornada",
      date: "Fecha",
      start: "Hora inicio",
      end: "Hora fin",
      responsible: "Responsable",
      notes: "Observaciones del responsable",
      notesPlaceholder: "Notas internas del responsable del cierre. Los resúmenes del equipo vienen desde el bot.",
      source: "Fuente: eventos reales filtrados por empresa, fecha y rango horario.",
      summary: "Resumen ejecutivo",
      people: "Personas",
      events: "Eventos",
      starts: "Turnos iniciados",
      ends: "Turnos cerrados",
      breaks: "Pausas",
      gps: "GPS",
      materials: "Materiales",
      lowStock: "Stock bajo",
      zeroStock: "Stock cero",
      activity: "Actividad de la jornada",
      peopleSection: "Actividad por persona",
      summaries: "Resúmenes enviados al cerrar turno",
      modules: "Indicadores por módulo activo",
      employee: "Empleado",
      role: "Rol",
      first: "Primer evento",
      last: "Último evento",
      noPeople: "Sin actividad de personal en esta jornada.",
      noSummaries: "No hay resúmenes enviados desde el bot en este rango.",
      saved: "Cierre guardado en PostgreSQL.",
      saveError: "No se pudo guardar el cierre.",
      loadError: "No se pudo generar el cierre.",
      inactiveTitle: "Módulo no activo",
      inactiveMsg: "Cierre de día no está activo para esta empresa.",
      activateFromAdmin: "Actívalo desde Admin V2 > Empresa > Módulos."
    },
    en: {
      dashboard: "Dashboard",
      activeTenant: "Active tenant",
      eyebrow: "Operational closing module",
      title: "Day closing",
      subtitle: "Generate the operational close by date and work shift. CLONEXA consolidates staff, GPS, materials, inventory and summaries sent from the bot.",
      badge: "SHIFT CLOSING",
      generate: "Generate closing",
      save: "Save closing",
      pdf: "PDF",
      csv: "CSV",
      back: "Back",
      control: "Shift control",
      date: "Date",
      start: "Start time",
      end: "End time",
      responsible: "Responsible",
      notes: "Responsible notes",
      notesPlaceholder: "Internal notes from the closing responsible. Team summaries come from the bot.",
      source: "Source: real events filtered by company, date and time range.",
      summary: "Executive summary",
      people: "People",
      events: "Events",
      starts: "Shift starts",
      ends: "Shift ends",
      breaks: "Breaks",
      gps: "GPS",
      materials: "Materials",
      lowStock: "Low stock",
      zeroStock: "Zero stock",
      activity: "Shift activity",
      peopleSection: "Activity by person",
      summaries: "Summaries sent when closing shift",
      modules: "Indicators by active module",
      employee: "Employee",
      role: "Role",
      first: "First event",
      last: "Last event",
      noPeople: "No staff activity for this shift.",
      noSummaries: "No summaries sent from the bot in this range.",
      saved: "Closing saved in PostgreSQL.",
      saveError: "Could not save closing.",
      loadError: "Could not generate closing.",
      inactiveTitle: "Module not active",
      inactiveMsg: "Day closing is not active for this company.",
      activateFromAdmin: "Activate it from Admin V2 > Company > Modules."
    },
    fr: {
      dashboard: "Tableau de bord",
      activeTenant: "Tenant actif",
      eyebrow: "Module de clôture opérationnelle",
      title: "Clôture du jour",
      subtitle: "Générez la clôture opérationnelle par date et journée. CLONEXA consolide le personnel, le GPS, les matériaux, l’inventaire et les résumés envoyés depuis le bot.",
      badge: "CLÔTURE DE JOURNÉE",
      generate: "Générer la clôture",
      save: "Enregistrer",
      pdf: "PDF",
      csv: "CSV",
      back: "Retour",
      control: "Contrôle de journée",
      date: "Date",
      start: "Heure début",
      end: "Heure fin",
      responsible: "Responsable",
      notes: "Notes du responsable",
      notesPlaceholder: "Notes internes du responsable de clôture. Les résumés de l’équipe viennent du bot.",
      source: "Source : événements réels filtrés par entreprise, date et plage horaire.",
      summary: "Résumé exécutif",
      people: "Personnes",
      events: "Événements",
      starts: "Services commencés",
      ends: "Services clôturés",
      breaks: "Pauses",
      gps: "GPS",
      materials: "Matériaux",
      lowStock: "Stock faible",
      zeroStock: "Stock zéro",
      activity: "Activité de la journée",
      peopleSection: "Activité par personne",
      summaries: "Résumés envoyés à la clôture",
      modules: "Indicateurs par module actif",
      employee: "Employé",
      role: "Rôle",
      first: "Premier événement",
      last: "Dernier événement",
      noPeople: "Aucune activité du personnel pour cette journée.",
      noSummaries: "Aucun résumé envoyé depuis le bot dans cette plage.",
      saved: "Clôture enregistrée dans PostgreSQL.",
      saveError: "Impossible d’enregistrer la clôture.",
      loadError: "Impossible de générer la clôture.",
      inactiveTitle: "Module non actif",
      inactiveMsg: "La clôture du jour n’est pas active pour cette entreprise.",
      activateFromAdmin: "Activez-le depuis Admin V2 > Entreprise > Modules."
    }
  };

  const MODULE_TITLES = {
    day_closing: ["Cierre de día", "Day closing", "Clôture du jour"],
    commercial_closing: ["Cierre comercial", "Commercial closing", "Clôture commerciale"],
    workforce: ["Personal", "Staff", "Personnel"],
    gps: ["GPS", "GPS", "GPS"],
    payroll: ["Nómina", "Payroll", "Paie"],
    bots: ["Bots", "Bots", "Bots"],
    inventory: ["Inventario", "Inventory", "Inventaire"],
    materials: ["Materiales", "Materials", "Matériaux"],
    crm: ["CRM Campo", "Field CRM", "CRM terrain"],
    kpis: ["KPIs", "KPIs", "KPIs"],
    reports: ["Reportes", "Reports", "Rapports"]
  };

  let lastReport = null;
  let lastContext = null;

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function t(key) {
    return TXT[lang()][key] || TXT.es[key] || key;
  }

  function moduleTitle(code, fallback) {
    const index = lang() === "en" ? 1 : lang() === "fr" ? 2 : 0;
    return MODULE_TITLES[code] ? MODULE_TITLES[code][index] : fallback || code;
  }

  function h(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function n(value) {
    const num = Number(value || 0);
    return Number.isFinite(num) ? num.toLocaleString() : "0";
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function companyIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || "";
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
      throw new Error(detail || String(response.status));
    }

    if (response.status === 204) return null;
    return response.json();
  }

  async function safeApi(path) {
    try {
      return await api(path);
    } catch (_) {
      return null;
    }
  }

  function normalizeModule(row) {
    const source = row.module || row.module_ref || row.global_module || row;
    const code = String(source.code || source.module_code || row.module_code || row.code || "").trim();
    const enabled = row.enabled ?? source.enabled ?? row.is_active ?? source.is_active ?? true;

    return { code, enabled: !!enabled, title: source.name || source.title || code };
  }

  async function loadContext(companyId) {
    const [companiesPayload, modulesPayload] = await Promise.all([
      safeApi("/companies"),
      safeApi(`/companies/${encodeURIComponent(companyId)}/modules`)
    ]);

    const companies = Array.isArray(companiesPayload) ? companiesPayload : [];
    const modules = Array.isArray(modulesPayload)
      ? modulesPayload.map(normalizeModule).filter((m) => m.code && m.enabled)
      : [];

    const company = companies.find((c) => c.id === companyId || c.company_id === companyId) || {
      id: companyId,
      company_id: companyId,
      name: document.querySelector(".client-company-name")?.textContent || "CLONEXA",
      slug: "tenant"
    };

    return { company, modules, codes: new Set(modules.map((m) => m.code)) };
  }

  function valueDate(row) {
    return String(row.occurred_at || row.created_at || row.updated_at || row.date || row.timestamp || "");
  }

  function minutesFromTime(value) {
    const raw = String(value || "00:00").slice(0, 5);
    const [hh, mm] = raw.split(":").map((x) => Number(x || 0));
    return hh * 60 + mm;
  }

  function eventMinutes(row) {
    const raw = valueDate(row);
    const match = raw.match(/T(\d{2}):(\d{2})/) || raw.match(/\s(\d{2}):(\d{2})/);
    if (!match) return null;
    return Number(match[1]) * 60 + Number(match[2]);
  }

  function inShift(row, date, start, end) {
    const raw = valueDate(row);
    if (raw && raw.slice(0, 10) && raw.slice(0, 10) !== date) return false;

    const m = eventMinutes(row);
    if (m === null) return true;

    return m >= minutesFromTime(start) && m <= minutesFromTime(end);
  }

  function lowerBlob(row) {
    const payload = row.payload_json || row.payload || {};
    return [
      row.event_label,
      row.event_type,
      row.action,
      row.status,
      row.status_after,
      row.module_code,
      row.source_channel,
      row.detail,
      row.notes,
      row.description,
      JSON.stringify(payload)
    ].map((x) => String(x || "")).join(" ").toLowerCase();
  }

  function eventEmployee(row) {
    return String(row.employee_name || row.employee || row.name || row.full_name || "Sin nombre").trim();
  }

  function eventRole(row) {
    return String(row.employee_role || row.role || "").trim();
  }

  function detailText(row) {
    const payload = row.payload_json || row.payload || {};

    const candidates = [
      payload.summary,
      payload.end_shift_summary,
      payload.management_summary,
      payload.shift_summary,
      payload.text,
      payload.message,
      row.summary,
      row.notes,
      row.detail,
      row.description
    ];

    const generic = [
      "turno finalizado",
      "shift ended",
      "finalizar turno",
      "end shift",
      "checked_out",
      "working",
      "registered"
    ];

    for (const item of candidates) {
      const value = String(item || "").trim();
      if (!value) continue;
      if (value.toLowerCase().startsWith("clx:cmd")) continue;
      if (generic.includes(value.toLowerCase())) continue;
      if (value.length < 4) continue;
      return value;
    }

    return "";
  }

  function isStart(row) {
    const blob = lowerBlob(row);
    return blob.includes("inicio de turno") || blob.includes("shift start") || blob.includes("shift_started") || blob.includes("check_in") || blob.includes("entrada");
  }

  function isEnd(row) {
    const blob = lowerBlob(row);
    return blob.includes("finalizar turno") || blob.includes("turno finalizado") || blob.includes("shift ended") || blob.includes("shift_ended") || blob.includes("checked_out") || blob.includes("end shift");
  }

  function isBreak(row) {
    const blob = lowerBlob(row);
    return blob.includes("pausa") || blob.includes("break") || blob.includes("on_break");
  }

  function isGps(row) {
    const blob = lowerBlob(row);
    return blob.includes("gps") || blob.includes("ubicación") || blob.includes("ubicacion") || blob.includes("location");
  }

  async function loadAttendance(companyId, date, start, end) {
    const query = new URLSearchParams({
      company_id: companyId,
      date_from: date,
      date_to: date,
      limit: "1000"
    });

    const payload =
      await safeApi(`/employees/attendance/history?${query.toString()}`) ||
      await safeApi(`/employees/attendance?${query.toString()}`) ||
      [];

    const rows = Array.isArray(payload)
      ? payload
      : Array.isArray(payload.items)
        ? payload.items
        : Array.isArray(payload.events)
          ? payload.events
          : Array.isArray(payload.rows)
            ? payload.rows
            : [];

    return rows.filter((row) => inShift(row, date, start, end));
  }

  async function loadMaterials(companyId, date) {
    const payload = await safeApi(`/materials/companies/${encodeURIComponent(companyId)}/requests?limit=1000`);
    const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.requests) ? payload.requests : [];

    return rows.filter((row) => {
      const raw = String(row.created_at || row.requested_at || row.updated_at || "");
      if (!raw) return true;
      return raw.slice(0, 10) === date;
    });
  }

  async function loadInventory(companyId) {
    const payload = await safeApi(`/inventory/companies/${encodeURIComponent(companyId)}/items?include_inactive=true&limit=1000`);
    return Array.isArray(payload) ? payload : Array.isArray(payload?.items) ? payload.items : [];
  }

  function buildPeople(events) {
    const people = new Map();
    const summaries = [];

    for (const row of events) {
      const name = eventEmployee(row);

      if (!people.has(name)) {
        people.set(name, {
          name,
          role: eventRole(row),
          events: 0,
          shift_starts: 0,
          shift_ends: 0,
          breaks: 0,
          gps: 0,
          first_event: "",
          last_event: "",
          summaries: []
        });
      }

      const person = people.get(name);
      person.events += 1;

      const time = valueDate(row);
      if (time) {
        if (!person.first_event) person.first_event = time;
        person.last_event = time;
      }

      if (isStart(row)) person.shift_starts += 1;
      if (isEnd(row)) person.shift_ends += 1;
      if (isBreak(row)) person.breaks += 1;
      if (isGps(row)) person.gps += 1;

      const summary = detailText(row);
      if (summary && (isEnd(row) || lowerBlob(row).includes("resumen") || lowerBlob(row).includes("summary"))) {
        const item = {
          employee: name,
          role: person.role,
          time,
          summary
        };

        person.summaries.push(item);
        summaries.push(item);
      }
    }

    return { people: Array.from(people.values()).filter((p) => p.name !== "Sin nombre"), summaries };
  }

  function buildReport(context, date, start, end, events, materials, inventory) {
    const peopleData = buildPeople(events);

    const materialStatus = {};
    for (const row of materials) {
      const status = String(row.status || "unknown").toLowerCase();
      materialStatus[status] = (materialStatus[status] || 0) + 1;
    }

    const lowStock = inventory.filter((item) => Number(item.current_stock || 0) <= Number(item.min_stock || 0) && Number(item.min_stock || 0) > 0).length;
    const zeroStock = inventory.filter((item) => Number(item.current_stock || 0) <= 0).length;

    const metrics = {
      people: peopleData.people.length,
      events: events.length,
      shift_starts: events.filter(isStart).length,
      shift_ends: events.filter(isEnd).length,
      breaks: events.filter(isBreak).length,
      gps: events.filter(isGps).length,
      materials: materials.length,
      low_stock: lowStock,
      zero_stock: zeroStock
    };

    return {
      company: context.company,
      source_modules: context.modules.map((m) => m.code),
      date,
      start_time: start,
      end_time: end,
      metrics,
      people: peopleData.people,
      closing_summaries: peopleData.summaries,
      materials: { total: materials.length, by_status: materialStatus, rows: materials },
      inventory: { items: inventory.length, low_stock: lowStock, zero_stock: zeroStock },
      events,
      generated_at: new Date().toISOString()
    };
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
      </aside>
    `;
  }

  function card(label, value) {
    return `<div class="cx-day-kpi"><span>${h(label)}</span><strong>${h(value)}</strong></div>`;
  }

  function row(label, value) {
    return `<div class="cx-day-row"><span>${h(label)}</span><strong>${h(value)}</strong></div>`;
  }

  function bar(label, value, max) {
    const pct = max > 0 ? Math.max(3, Math.round((Number(value || 0) / max) * 100)) : 3;
    return `
      <div class="cx-day-bar-row">
        <span>${h(label)}</span>
        <div class="cx-day-bar"><i style="width:${pct}%"></i></div>
        <strong>${h(n(value))}</strong>
      </div>
    `;
  }

  function fmt(value) {
    if (!value) return "—";
    try { return new Date(value).toLocaleString(); } catch (_) { return String(value); }
  }

  function peopleTable(report) {
    if (!report.people.length) return `<p class="client-muted">${h(t("noPeople"))}</p>`;

    return `
      <div class="client-table-wrap">
        <table class="client-table">
          <thead>
            <tr>
              <th>${h(t("employee"))}</th>
              <th>${h(t("role"))}</th>
              <th>${h(t("events"))}</th>
              <th>${h(t("starts"))}</th>
              <th>${h(t("ends"))}</th>
              <th>${h(t("breaks"))}</th>
              <th>${h(t("gps"))}</th>
              <th>${h(t("first"))}</th>
              <th>${h(t("last"))}</th>
            </tr>
          </thead>
          <tbody>
            ${report.people.map((person) => `
              <tr>
                <td>${h(person.name)}</td>
                <td>${h(person.role || "—")}</td>
                <td>${h(n(person.events))}</td>
                <td>${h(n(person.shift_starts))}</td>
                <td>${h(n(person.shift_ends))}</td>
                <td>${h(n(person.breaks))}</td>
                <td>${h(n(person.gps))}</td>
                <td>${h(fmt(person.first_event))}</td>
                <td>${h(fmt(person.last_event))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function summariesBlock(report) {
    if (!report.closing_summaries.length) return `<p class="client-muted">${h(t("noSummaries"))}</p>`;

    return report.closing_summaries.map((item) => `
      <article class="cx-day-note">
        <strong>${h(item.employee)}</strong>
        <span>${h(item.role || "")} · ${h(fmt(item.time))}</span>
        <p>${h(item.summary)}</p>
      </article>
    `).join("");
  }

  function moduleBlocks(report) {
    const materialStatus = report.materials.by_status || {};

    return `
      <section class="cx-day-block">
        <div class="client-eyebrow">WORKFORCE</div>
        <h2>Workforce</h2>
        <div class="cx-day-list">
          ${row(t("people"), report.metrics.people)}
          ${row(t("starts"), report.metrics.shift_starts)}
          ${row(t("ends"), report.metrics.shift_ends)}
          ${row(t("breaks"), report.metrics.breaks)}
        </div>
      </section>

      <section class="cx-day-block">
        <div class="client-eyebrow">GPS</div>
        <h2>GPS</h2>
        <div class="cx-day-list">
          ${row(t("gps"), report.metrics.gps)}
        </div>
      </section>

      <section class="cx-day-block">
        <div class="client-eyebrow">MATERIALES</div>
        <h2>${h(t("materials"))}</h2>
        <div class="cx-day-list">
          ${row(t("materials"), report.materials.total)}
          ${Object.keys(materialStatus).length
            ? Object.entries(materialStatus).map(([status, count]) => row(status, count)).join("")
            : row("Sin estados", 0)}
        </div>
      </section>

      <section class="cx-day-block">
        <div class="client-eyebrow">INVENTARIO</div>
        <h2>Inventario</h2>
        <div class="cx-day-list">
          ${row("Items", report.inventory.items)}
          ${row(t("lowStock"), report.inventory.low_stock)}
          ${row(t("zeroStock"), report.inventory.zero_stock)}
        </div>
      </section>
    `;
  }

  function ensureStyles() {
    if (document.getElementById("clx-day-closing-r4-styles")) return;

    const style = document.createElement("style");
    style.id = "clx-day-closing-r4-styles";
    style.textContent = `
      .cx-day-toolbar{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:14px;align-items:end;margin-top:18px}
      .cx-day-toolbar label,.cx-day-notes-label{display:grid;gap:8px;color:rgba(255,255,255,.72);font-weight:900;letter-spacing:.08em;text-transform:uppercase;font-size:12px}
      .cx-day-toolbar input,.cx-day-notes-label textarea{width:100%;border:1px solid rgba(255,255,255,.14);background:rgba(0,0,0,.28);color:white;border-radius:16px;padding:13px 14px;font-weight:800;outline:none}
      .cx-day-notes-label textarea{min-height:82px;resize:vertical}
      .cx-day-kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:18px}
      .cx-day-kpi{min-height:84px;border:1px solid rgba(255,255,255,.12);background:linear-gradient(135deg,rgba(255,255,255,.08),rgba(255,0,180,.12));border-radius:18px;padding:15px;display:grid;align-content:center;gap:8px}
      .cx-day-kpi span{color:rgba(255,255,255,.72);font-weight:900;font-size:13px}
      .cx-day-kpi strong{color:white;font-size:30px;line-height:1;font-weight:1000}
      .cx-day-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;margin-top:18px}
      .cx-day-block{border:1px solid rgba(255,255,255,.11);background:linear-gradient(135deg,rgba(255,255,255,.07),rgba(255,0,180,.08));border-radius:22px;padding:20px;box-shadow:0 18px 48px rgba(0,0,0,.18)}
      .cx-day-list{display:grid;gap:10px}
      .cx-day-row{display:flex;justify-content:space-between;gap:12px;align-items:center;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.06);padding:10px 12px;border-radius:13px}
      .cx-day-row span{color:rgba(255,255,255,.76);font-weight:800}
      .cx-day-row strong{color:white;font-weight:1000}
      .cx-day-chart{display:grid;gap:12px}
      .cx-day-bar-row{display:grid;grid-template-columns:160px 1fr 50px;gap:12px;align-items:center}
      .cx-day-bar-row span{font-weight:900;color:rgba(255,255,255,.82)}
      .cx-day-bar{height:13px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden}
      .cx-day-bar i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#20e0a0,#ff22be)}
      .cx-day-note{border:1px solid rgba(255,255,255,.10);background:rgba(255,255,255,.06);border-radius:18px;padding:16px;margin-bottom:10px}
      .cx-day-note strong{display:block;color:white;font-size:16px}
      .cx-day-note span{display:block;color:rgba(255,255,255,.62);margin-top:4px;font-size:12px;font-weight:800}
      .cx-day-note p{margin:10px 0 0;color:rgba(255,255,255,.86);line-height:1.45}
      @media(max-width:980px){.cx-day-toolbar{grid-template-columns:1fr}}
      @media print{
        body *{visibility:hidden!important}
        [data-day-closing-root],[data-day-closing-root] *{visibility:visible!important}
        [data-day-closing-root]{position:absolute;inset:0;background:white!important;color:black!important}
        .client-sidebar,.client-actions,textarea,input{display:none!important}
        .client-main{width:100%!important}
      }
    `;
    document.head.appendChild(style);
  }

  async function generateReport() {
    const companyId = companyIdFromUrl();
    const date = document.querySelector("[data-day-date]")?.value || today();
    const start = document.querySelector("[data-day-start]")?.value || "07:00";
    const end = document.querySelector("[data-day-end]")?.value || "18:00";

    const [events, materials, inventory] = await Promise.all([
      loadAttendance(companyId, date, start, end),
      loadMaterials(companyId, date),
      loadInventory(companyId)
    ]);

    lastReport = buildReport(lastContext, date, start, end, events, materials, inventory);
    renderReport(lastReport);
  }

  function renderReport(report) {
    const max = Math.max(report.metrics.shift_starts, report.metrics.shift_ends, report.metrics.breaks, report.metrics.gps, report.metrics.materials, 1);

    const target = document.querySelector("[data-day-report]");
    if (!target) return;

    target.innerHTML = `
      <section class="client-panel">
        <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start">
          <div>
            <div class="client-eyebrow">${h(t("summary"))}</div>
            <h2>${h(t("summary"))}</h2>
            <p class="client-muted">${h(report.date)} · ${h(report.start_time)} - ${h(report.end_time)}</p>
          </div>
          <span class="client-badge">${h(n(report.metrics.events))} ${h(t("events"))}</span>
        </div>

        <div class="cx-day-kpi-grid">
          ${card(t("people"), report.metrics.people)}
          ${card(t("events"), report.metrics.events)}
          ${card(t("starts"), report.metrics.shift_starts)}
          ${card(t("ends"), report.metrics.shift_ends)}
          ${card(t("breaks"), report.metrics.breaks)}
          ${card(t("gps"), report.metrics.gps)}
          ${card(t("materials"), report.metrics.materials)}
          ${card(t("lowStock"), report.metrics.low_stock)}
        </div>
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("activity"))}</div>
        <h2>${h(t("activity"))}</h2>
        <div class="cx-day-chart">
          ${bar(t("starts"), report.metrics.shift_starts, max)}
          ${bar(t("ends"), report.metrics.shift_ends, max)}
          ${bar(t("breaks"), report.metrics.breaks, max)}
          ${bar(t("gps"), report.metrics.gps, max)}
          ${bar(t("materials"), report.metrics.materials, max)}
        </div>
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("peopleSection"))}</div>
        <h2>${h(t("peopleSection"))}</h2>
        ${peopleTable(report)}
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("summaries"))}</div>
        <h2>${h(t("summaries"))}</h2>
        ${summariesBlock(report)}
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("modules"))}</div>
        <h2>${h(t("modules"))}</h2>
        <div class="cx-day-grid">${moduleBlocks(report)}</div>
      </section>
    `;
  }

  async function renderDayClosing() {
    ensureStyles();

    const companyId = companyIdFromUrl();
    const context = await loadContext(companyId);
    lastContext = context;

    if (!context.codes.has("day_closing")) {
      const app = document.getElementById("app");
      app.innerHTML = `
        <main class="client-shell">
          <div class="client-layout">
            ${sidebar(context.company, context.modules, "dashboard")}
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
      return;
    }

    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
      <main class="client-shell" data-day-closing-root>
        <div class="client-layout">
          ${sidebar(context.company, context.modules, "day_closing")}

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">${h(t("eyebrow"))}</div>
              <h1 class="client-title">${h(t("title"))}</h1>
              <p class="client-muted">${h(t("subtitle"))}</p>
              <span class="client-badge" style="position:absolute;right:28px;top:28px">${h(t("badge"))}</span>

              <div class="client-actions">
                <button class="client-btn" type="button" data-day-generate>${h(t("generate"))}</button>
                <button class="client-btn" type="button" data-day-save>${h(t("save"))}</button>
                <button class="client-btn" type="button" data-day-pdf>${h(t("pdf"))}</button>
                <button class="client-btn" type="button" data-day-csv>${h(t("csv"))}</button>
                <button class="client-btn" type="button" data-clx-day-dashboard>${h(t("back"))}</button>
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">${h(t("control"))}</div>
              <h2>${h(t("control"))}</h2>

              <div class="cx-day-toolbar">
                <label>${h(t("date"))}<input type="date" data-day-date value="${h(today())}"></label>
                <label>${h(t("start"))}<input type="time" data-day-start value="07:00"></label>
                <label>${h(t("end"))}<input type="time" data-day-end value="18:00"></label>
                <label>${h(t("responsible"))}<input type="text" data-day-responsible value="${h(context.company.name || "")}"></label>
              </div>

              <div style="margin-top:18px">
                <label class="cx-day-notes-label">
                  ${h(t("notes"))}
                  <textarea data-day-notes placeholder="${h(t("notesPlaceholder"))}"></textarea>
                </label>
              </div>

              <p class="client-muted" style="margin-top:14px">${h(t("source"))}</p>
            </section>

            <div data-day-report></div>
          </section>
        </div>
      </main>
    `;

    await generateReport();
  }

  function showNotice(message, error = false) {
    const panel = document.querySelector("[data-day-closing-root] .client-panel");
    if (!panel) return;

    const box = document.createElement("div");
    box.className = `personal-toast ${error ? "error" : ""}`;
    box.textContent = message;
    panel.prepend(box);

    setTimeout(() => box.remove(), 3600);
  }

  function payload() {
    if (!lastReport) return null;

    return {
      date: lastReport.date,
      start_time: lastReport.start_time,
      end_time: lastReport.end_time,
      responsible: document.querySelector("[data-day-responsible]")?.value || "",
      notes: document.querySelector("[data-day-notes]")?.value || "",
      status: "generated",
      source_modules: lastReport.source_modules || [],
      summary: {
        metrics: lastReport.metrics,
        people: lastReport.people,
        closing_summaries: lastReport.closing_summaries,
        materials: lastReport.materials,
        inventory: lastReport.inventory,
        generated_at: lastReport.generated_at
      }
    };
  }

  async function saveClosing() {
    const data = payload();
    if (!data) return;

    try {
      const companyId = companyIdFromUrl();
      const response = await api(`/closure-store/companies/${encodeURIComponent(companyId)}/closures`, {
        method: "POST",
        body: JSON.stringify(data)
      });

      showNotice(`${t("saved")} ID: ${response.id}`);
    } catch (error) {
      showNotice(`${t("saveError")} ${error.message || ""}`, true);
    }
  }

  function downloadCsv() {
    const data = payload();
    if (!data) return;

    const rows = [
      ["company_id", companyIdFromUrl()],
      ["date", data.date],
      ["start_time", data.start_time],
      ["end_time", data.end_time],
      ["responsible", data.responsible],
      ["notes", data.notes],
      [],
      ["metric", "value"],
      ...Object.entries(data.summary.metrics || {}),
      [],
      ["employee", "role", "events", "shift_starts", "shift_ends", "breaks", "gps", "first_event", "last_event"],
      ...(data.summary.people || []).map((p) => [p.name, p.role, p.events, p.shift_starts, p.shift_ends, p.breaks, p.gps, p.first_event, p.last_event]),
      [],
      ["closing_summary_employee", "role", "time", "summary"],
      ...(data.summary.closing_summaries || []).map((s) => [s.employee, s.role, s.time, s.summary])
    ];

    const csv = rows.map((row) => row.map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");

    a.href = url;
    a.download = `clonexa_day_closing_${data.date}_${data.start_time.replace(":", "")}_${data.end_time.replace(":", "")}.csv`;
    a.click();

    URL.revokeObjectURL(url);
  }

  document.addEventListener("click", async (event) => {
    const moduleButton = event.target.closest && event.target.closest('[data-client-module="day_closing"]');

    if (moduleButton) {
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      await renderDayClosing();
      return;
    }

    if (event.target.closest && event.target.closest("[data-clx-day-dashboard]")) {
      event.preventDefault();
      window.location.href = `/client?company_id=${encodeURIComponent(companyIdFromUrl())}`;
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-generate]")) {
      event.preventDefault();
      try {
        await generateReport();
      } catch (error) {
        showNotice(`${t("loadError")} ${error.message || ""}`, true);
      }
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-save]")) {
      event.preventDefault();
      await saveClosing();
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-csv]")) {
      event.preventDefault();
      downloadCsv();
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-pdf]")) {
      event.preventDefault();
      window.print();
    }
  }, true);

  window.CLONEXA_RENDER_DAY_CLOSING = renderDayClosing;
})();
