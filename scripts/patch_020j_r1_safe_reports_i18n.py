from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_reports_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaSafeReportsI18n020JR1() {
  "use strict";

  if (window.__CLONEXA_020J_R1_REPORTS_I18N__) return;
  window.__CLONEXA_020J_R1_REPORTS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const DICT = {
    es: {
      settings: "Ajustes",
      logout: "Cerrar sesión",

      moduleEyebrow: "Módulo Reportes",
      moduleTitle: "Reportes",
      moduleSubtitle: "Auditoría general de operación, personal, GPS, materiales, inventario y nómina.",

      dashboard: "Dashboard",
      kpis: "KPIs",
      activeTenant: "Tenant activo",

      back: "Volver",
      refresh: "Actualizar",
      search: "Buscar",
      filter: "Filtrar",
      clear: "Limpiar",
      exportCsv: "Exportar CSV",
      csv: "CSV",

      generalReport: "Reporte general",
      smartFilters: "Filtros inteligentes",
      from: "Desde",
      to: "Hasta",
      period: "Periodo",
      preset: "Rango",
      employee: "Empleado",
      collaborator: "Colaborador",
      module: "Módulo",
      status: "Estado",
      text: "Texto",
      channel: "Canal",
      detail: "Detalle",

      all: "Todos",
      today: "Hoy",
      sevenDays: "7 días",
      fifteenDays: "15 días",
      month: "Mes",
      custom: "Personalizado",

      reportHelp: "Reporte general consolida toda la empresa. Por persona filtra al colaborador seleccionado.",

      employeeSummary: "Resumen por empleado",
      materialsSummary: "Materiales",
      inventorySummary: "Inventario",
      gpsSummary: "GPS",
      payrollSummary: "Nómina",
      eventsSummary: "Eventos operativos",

      employeeName: "Empleado",
      role: "Rol",
      shifts: "Turnos",
      closedShifts: "Turnos cerrados",
      events: "Eventos",
      gpsOutside: "GPS fuera",
      gpsInside: "GPS dentro",
      gpsStatus: "Estado GPS",

      material: "Material",
      materials: "Materiales",
      requested: "Solicitado",
      approved: "Aprobado",
      delivered: "Entregado",
      returned: "Devuelto",
      rejected: "Rechazado",
      pending: "Pendiente",
      consigned: "Consignado",

      nameReference: "Nombre / referencia",
      stock: "Stock",
      currentStock: "Stock actual",
      lowStock: "Stock bajo",
      stockMinimum: "Stock mínimo",
      alert: "Alerta",

      regularHours: "Horas ordinarias",
      extraHours: "Horas extra",
      gross: "Bruto",
      discount: "Descuento",
      netTotal: "Total neto",
      estimatedTotal: "Total estimado",
      payroll: "Nómina",

      date: "Fecha",
      dateTime: "Fecha/hora",
      source: "Fuente",
      sourceChannel: "Canal",
      moduleCode: "Módulo",

      noData: "Sin datos para los filtros seleccionados.",
      partialData: "Algunos bloques no tenían datos o no aplican:",
      loadError: "No se pudo cargar Reportes.",

      workforce: "Workforce",
      gps: "GPS",
      inventory: "Inventario",
      reports: "Reportes",
      bots: "Bots",
      crm: "CRM Campo"
    },

    en: {
      settings: "Settings",
      logout: "Log out",

      moduleEyebrow: "Reports module",
      moduleTitle: "Reports",
      moduleSubtitle: "General audit of operations, staff, GPS, materials, inventory and payroll.",

      dashboard: "Dashboard",
      kpis: "KPIs",
      activeTenant: "Active tenant",

      back: "Back",
      refresh: "Refresh",
      search: "Search",
      filter: "Filter",
      clear: "Clear",
      exportCsv: "Export CSV",
      csv: "CSV",

      generalReport: "General report",
      smartFilters: "Smart filters",
      from: "From",
      to: "To",
      period: "Period",
      preset: "Range",
      employee: "Employee",
      collaborator: "Collaborator",
      module: "Module",
      status: "Status",
      text: "Text",
      channel: "Channel",
      detail: "Detail",

      all: "All",
      today: "Today",
      sevenDays: "7 days",
      fifteenDays: "15 days",
      month: "Month",
      custom: "Custom",

      reportHelp: "The general report consolidates the entire company. Person view filters by the selected collaborator.",

      employeeSummary: "Employee summary",
      materialsSummary: "Materials",
      inventorySummary: "Inventory",
      gpsSummary: "GPS",
      payrollSummary: "Payroll",
      eventsSummary: "Operational events",

      employeeName: "Employee",
      role: "Role",
      shifts: "Shifts",
      closedShifts: "Closed shifts",
      events: "Events",
      gpsOutside: "GPS outside",
      gpsInside: "GPS inside",
      gpsStatus: "GPS status",

      material: "Material",
      materials: "Materials",
      requested: "Requested",
      approved: "Approved",
      delivered: "Delivered",
      returned: "Returned",
      rejected: "Rejected",
      pending: "Pending",
      consigned: "Consigned",

      nameReference: "Name / reference",
      stock: "Stock",
      currentStock: "Current stock",
      lowStock: "Low stock",
      stockMinimum: "Minimum stock",
      alert: "Alert",

      regularHours: "Regular hours",
      extraHours: "Extra hours",
      gross: "Gross",
      discount: "Discount",
      netTotal: "Net total",
      estimatedTotal: "Estimated total",
      payroll: "Payroll",

      date: "Date",
      dateTime: "Date/time",
      source: "Source",
      sourceChannel: "Channel",
      moduleCode: "Module",

      noData: "No data for the selected filters.",
      partialData: "Some blocks had no data or do not apply:",
      loadError: "Could not load Reports.",

      workforce: "Workforce",
      gps: "GPS",
      inventory: "Inventory",
      reports: "Reports",
      bots: "Bots",
      crm: "Field CRM"
    },

    fr: {
      settings: "Configuration",
      logout: "Quitter",

      moduleEyebrow: "Module rapports",
      moduleTitle: "Rapports",
      moduleSubtitle: "Audit général des opérations, personnel, GPS, matériaux, inventaire et paie.",

      dashboard: "Tableau de bord",
      kpis: "KPIs",
      activeTenant: "Tenant actif",

      back: "Retour",
      refresh: "Actualiser",
      search: "Rechercher",
      filter: "Filtrer",
      clear: "Effacer",
      exportCsv: "Exporter CSV",
      csv: "CSV",

      generalReport: "Rapport général",
      smartFilters: "Filtres intelligents",
      from: "De",
      to: "À",
      period: "Période",
      preset: "Plage",
      employee: "Employé",
      collaborator: "Collaborateur",
      module: "Module",
      status: "Statut",
      text: "Texte",
      channel: "Canal",
      detail: "Détail",

      all: "Tous",
      today: "Aujourd’hui",
      sevenDays: "7 jours",
      fifteenDays: "15 jours",
      month: "Mois",
      custom: "Personnalisé",

      reportHelp: "Le rapport général consolide toute l’entreprise. La vue par personne filtre le collaborateur sélectionné.",

      employeeSummary: "Résumé par employé",
      materialsSummary: "Matériaux",
      inventorySummary: "Inventaire",
      gpsSummary: "GPS",
      payrollSummary: "Paie",
      eventsSummary: "Événements opérationnels",

      employeeName: "Employé",
      role: "Rôle",
      shifts: "Services",
      closedShifts: "Services clôturés",
      events: "Événements",
      gpsOutside: "GPS hors périmètre",
      gpsInside: "GPS dans le périmètre",
      gpsStatus: "Statut GPS",

      material: "Matériau",
      materials: "Matériaux",
      requested: "Demandé",
      approved: "Approuvé",
      delivered: "Livré",
      returned: "Retourné",
      rejected: "Rejeté",
      pending: "En attente",
      consigned: "Consigné",

      nameReference: "Nom / référence",
      stock: "Stock",
      currentStock: "Stock actuel",
      lowStock: "Stock faible",
      stockMinimum: "Stock minimum",
      alert: "Alerte",

      regularHours: "Heures normales",
      extraHours: "Heures supplémentaires",
      gross: "Brut",
      discount: "Remise",
      netTotal: "Total net",
      estimatedTotal: "Total estimé",
      payroll: "Paie",

      date: "Date",
      dateTime: "Date/heure",
      source: "Source",
      sourceChannel: "Canal",
      moduleCode: "Module",

      noData: "Aucune donnée pour les filtres sélectionnés.",
      partialData: "Certains blocs n’avaient pas de données ou ne s’appliquent pas :",
      loadError: "Impossible de charger les rapports.",

      workforce: "Workforce",
      gps: "GPS",
      inventory: "Inventaire",
      reports: "Rapports",
      bots: "Bots",
      crm: "CRM terrain"
    }
  };

  const ALIASES = {};

  Object.keys(DICT).forEach((language) => {
    Object.keys(DICT[language]).forEach((key) => {
      ALIASES[norm(DICT[language][key])] = key;
    });
  });

  [
    ["Modulo Reportes", "moduleEyebrow"],
    ["Módulo Reportes", "moduleEyebrow"],
    ["Reportes", "moduleTitle"],
    ["Auditoría general de operación, personal, GPS, materiales, inventario y nómina.", "moduleSubtitle"],
    ["Auditoria general de operacion, personal, GPS, materiales, inventario y nomina.", "moduleSubtitle"],

    ["Dashboard", "dashboard"],
    ["KPIs", "kpis"],
    ["Tenant activo", "activeTenant"],

    ["Volver", "back"],
    ["Actualizar", "refresh"],
    ["Buscar", "search"],
    ["Filtrar", "filter"],
    ["Limpiar", "clear"],
    ["Exportar CSV", "exportCsv"],
    ["CSV", "csv"],

    ["Reporte general", "generalReport"],
    ["Filtros inteligentes", "smartFilters"],
    ["Desde", "from"],
    ["Hasta", "to"],
    ["Periodo", "period"],
    ["Rango", "preset"],
    ["Empleado", "employee"],
    ["Colaborador", "collaborator"],
    ["Módulo", "module"],
    ["Modulo", "module"],
    ["Estado", "status"],
    ["Texto", "text"],
    ["Canal", "channel"],
    ["Detalle", "detail"],

    ["Todos", "all"],
    ["Hoy", "today"],
    ["7 días", "sevenDays"],
    ["7 dias", "sevenDays"],
    ["15 días", "fifteenDays"],
    ["15 dias", "fifteenDays"],
    ["Mes", "month"],
    ["Personalizado", "custom"],

    ["Reporte general consolida toda la empresa. Por persona filtra al colaborador seleccionado.", "reportHelp"],

    ["Resumen por empleado", "employeeSummary"],
    ["Resumen materiales", "materialsSummary"],
    ["Materiales", "materialsSummary"],
    ["Resumen inventario", "inventorySummary"],
    ["Inventario", "inventorySummary"],
    ["Resumen GPS", "gpsSummary"],
    ["GPS", "gpsSummary"],
    ["Nómina", "payrollSummary"],
    ["Nomina", "payrollSummary"],
    ["Eventos operativos", "eventsSummary"],

    ["Rol", "role"],
    ["Turnos", "shifts"],
    ["Turnos cerrados", "closedShifts"],
    ["Eventos", "events"],
    ["GPS fuera", "gpsOutside"],
    ["GPS dentro", "gpsInside"],
    ["Estado GPS", "gpsStatus"],

    ["Material", "material"],
    ["Solicitado", "requested"],
    ["Aprobado", "approved"],
    ["Entregado", "delivered"],
    ["Devuelto", "returned"],
    ["Rechazado", "rejected"],
    ["Pendiente", "pending"],
    ["Consignado", "consigned"],

    ["Nombre / referencia", "nameReference"],
    ["Stock", "stock"],
    ["Stock actual", "currentStock"],
    ["Stock bajo", "lowStock"],
    ["Stock mínimo", "stockMinimum"],
    ["Stock minimo", "stockMinimum"],
    ["Alerta", "alert"],

    ["Horas ordinarias", "regularHours"],
    ["Horas extra", "extraHours"],
    ["Bruto", "gross"],
    ["Descuento", "discount"],
    ["Total neto", "netTotal"],
    ["Total estimado", "estimatedTotal"],

    ["Fecha", "date"],
    ["Fecha/hora", "dateTime"],
    ["Fuente", "source"],
    ["source_channel", "sourceChannel"],
    ["module_code", "moduleCode"],

    ["Sin datos para los filtros seleccionados.", "noData"],
    ["Algunos bloques no tenían datos o no aplican:", "partialData"],
    ["Algunos bloques no tenian datos o no aplican:", "partialData"],
    ["No se pudo cargar Reportes.", "loadError"],

    ["Workforce", "workforce"],
    ["Bots", "bots"],
    ["CRM Campo", "crm"],

    ["delivered", "delivered"],
    ["returned", "returned"],
    ["outside", "gpsOutside"],
    ["pending", "pending"],
    ["approved", "approved"],
    ["rejected", "rejected"]
  ].forEach(([text, key]) => {
    ALIASES[norm(text)] = key;
  });

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function norm(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function t(key) {
    return (DICT[lang()] && DICT[lang()][key]) || DICT.es[key] || key;
  }

  function shouldSkipText(value) {
    const raw = String(value || "").trim();
    if (!raw) return true;
    if (/^[\d\s.,:$%#@/_-]+$/.test(raw)) return true;
    if (/^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$/.test(raw)) return true;
    if (raw.includes("@")) return true;
    if (/^[a-f0-9-]{20,}$/i.test(raw)) return true;
    if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return true;
    if (/^\d{1,2}:\d{2}/.test(raw)) return true;
    return false;
  }

  function translateText(value) {
    const raw = String(value || "");
    const clean = raw.replace(/\s+/g, " ").trim();

    if (shouldSkipText(clean)) return raw;

    const key = ALIASES[norm(clean)];
    if (!key) return raw;

    return raw.replace(clean, t(key));
  }

  function isReportsVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector("[data-reports-search]")) return true;
    if (app.querySelector("[data-reports-tab]")) return true;
    if (app.querySelector("[data-reports-export]")) return true;
    if (app.querySelector("[data-reports-dashboard]")) return true;
    if (app.querySelector(".cx-reports-table")) return true;
    if (app.querySelector(".cx-reports-toolbar")) return true;
    if (app.querySelector(".cx-reports-tabs")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Módulo Reportes") ||
      text.includes("Modulo Reportes") ||
      text.includes("Reports module") ||
      text.includes("Module rapports") ||
      text.includes("Reporte general") ||
      text.includes("General report") ||
      text.includes("Rapport général")
    );
  }

  function skipElement(el) {
    if (!el || !el.tagName) return true;
    const tag = el.tagName.toLowerCase();
    if (["script", "style", "code", "pre"].includes(tag)) return true;
    if (el.closest && el.closest("[data-clx-no-i18n]")) return true;
    return false;
  }

  function translateAttributes(base) {
    base.querySelectorAll("[placeholder], [title], [aria-label], input[type='button'], input[type='submit']").forEach((el) => {
      if (skipElement(el)) return;

      ["placeholder", "title", "aria-label"].forEach((attr) => {
        if (!el.hasAttribute(attr)) return;
        const current = el.getAttribute(attr);
        const next = translateText(current);
        if (next !== current) el.setAttribute(attr, next);
      });

      if (el.matches("input[type='button'], input[type='submit']")) {
        const next = translateText(el.value);
        if (next !== el.value) el.value = next;
      }
    });
  }

  function translateReports() {
    try {
      if (!isReportsVisible()) return;

      const app = document.getElementById("app");
      if (!app) return;

      const walker = document.createTreeWalker(app, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || skipElement(parent)) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      });

      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);

      nodes.forEach((node) => {
        const next = translateText(node.nodeValue);
        if (next !== node.nodeValue) node.nodeValue = next;
      });

      translateAttributes(app);

      const settings = document.getElementById("clxOpenCoreSettings");
      const logout = document.getElementById("clxCoreLogout");

      if (settings) settings.textContent = `⚙ ${t("settings")}`;
      if (logout) logout.textContent = `⏻ ${t("logout")}`;

      document.documentElement.lang = lang();
    } catch (error) {
      console.warn("CLONEXA Reports i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateReports, 140);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateReports();
      if (count >= 8) clearInterval(id);
    }, 220);
  }

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 450);
    setTimeout(schedule, 1000);
  }, true);

  document.addEventListener("input", schedule, true);
  document.addEventListener("change", schedule, true);
  document.addEventListener("keydown", schedule, true);

  const observer = new MutationObserver(schedule);

  function init() {
    try {
      if (document.body) {
        observer.observe(document.body, {
          childList: true,
          subtree: true
        });
      }
      schedule();
      burst();
    } catch (error) {
      console.warn("CLONEXA Reports i18n init skipped:", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
'''

js_path.write_text(js, encoding="utf-8")

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_reports_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

crm_matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_crm_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if crm_matches:
    last = crm_matches[-1]
    src = last.group(1)
    safe_src = re.sub(r'client_crm_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_reports_i18n_safe.js?v=020JR1', src)
    html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
else:
    bots_matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client_bots_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE,
    ))
    if bots_matches:
        last = bots_matches[-1]
        src = last.group(1)
        safe_src = re.sub(r'client_bots_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_reports_i18n_safe.js?v=020JR1', src)
        html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/client-static/client_reports_i18n_safe.js?v=020JR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020J-R1 safe external Reports i18n added")
