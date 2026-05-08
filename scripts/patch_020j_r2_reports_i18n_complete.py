from pathlib import Path
import re

path = Path("app/web/client_reports_i18n_safe.js")
js = path.read_text(encoding="utf-8-sig")

# Reemplazo completo del script Reportes por versión ampliada R2.
js = r'''
(function clonexaSafeReportsI18n020JR2() {
  "use strict";

  if (window.__CLONEXA_020J_R2_REPORTS_I18N__) return;
  window.__CLONEXA_020J_R2_REPORTS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const DICT = {
    es: {
      settings: "Ajustes",
      logout: "Cerrar sesión",

      moduleEyebrow: "Módulo Reportes",
      moduleTitle: "Reportes",
      generalReport: "Reporte general",
      moduleSubtitle: "Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta.",

      type: "Tipo",
      from: "Desde",
      to: "Hasta",
      period: "Periodo",
      employee: "Empleado",
      smartSearch: "Lupa inteligente",
      module: "Módulo",
      status: "Estado",

      generate: "Generar",
      csv: "CSV",
      back: "Volver",
      dashboard: "Dashboard",
      kpis: "KPIs",

      general: "General",
      all: "Todos",
      sevenDays: "7 días",
      fifteenDays: "15 días",
      month: "Mes",
      custom: "Personalizado",

      searchPlaceholder: "Buscar empleado, MAT, GPS, stock, nómina...",

      reportHelp: "El reporte general consolida toda la empresa. Por persona filtra al colaborador seleccionado.",

      executiveSummary: "Resumen ejecutivo",
      periodIndicators: "Indicadores del periodo",

      activeStaff: "Personal activo",
      shiftsStarted: "Turnos iniciados",
      regularHours: "Horas ordinarias",
      totalPayroll: "Total nómina",
      gpsOutside: "GPS fuera",
      materialOrders: "Órdenes material",
      consignments: "Consignas",
      lowStock: "Stock bajo",
      zeroStock: "Stock cero",
      alerts: "Alertas",

      workforce: "Workforce",
      payroll: "Nómina",
      materials: "Materiales",
      inventory: "Inventario",
      gps: "GPS",
      generalLower: "general",

      activityByDay: "Actividad por día",
      materialsByStatus: "Materiales por estado",

      delivered: "Entregado",
      returnedPartial: "Devuelto parcial",
      returned: "Devuelto",
      pending: "Pendiente",
      approved: "Aprobado",
      rejected: "Rechazado",
      consigned: "Consignado",

      activeTenant: "Tenant activo",
      noData: "Sin datos para los filtros seleccionados.",
      partialData: "Algunos bloques no tenían datos o no aplican:",
      loadError: "No se pudo cargar Reportes."
    },

    en: {
      settings: "Settings",
      logout: "Log out",

      moduleEyebrow: "Reports module",
      moduleTitle: "Reports",
      generalReport: "General report",
      moduleSubtitle: "Consolidated history of Staff, GPS, Materials, Inventory and Payroll. It does not modify data; it only audits and exports.",

      type: "Type",
      from: "From",
      to: "To",
      period: "Period",
      employee: "Employee",
      smartSearch: "Smart search",
      module: "Module",
      status: "Status",

      generate: "Generate",
      csv: "CSV",
      back: "Back",
      dashboard: "Dashboard",
      kpis: "KPIs",

      general: "General",
      all: "All",
      sevenDays: "7 days",
      fifteenDays: "15 days",
      month: "Month",
      custom: "Custom",

      searchPlaceholder: "Search employee, MAT, GPS, stock, payroll...",

      reportHelp: "The general report consolidates the entire company. Person view filters by the selected collaborator.",

      executiveSummary: "Executive summary",
      periodIndicators: "Period indicators",

      activeStaff: "Active staff",
      shiftsStarted: "Shifts started",
      regularHours: "Regular hours",
      totalPayroll: "Total payroll",
      gpsOutside: "GPS outside",
      materialOrders: "Material orders",
      consignments: "Consignments",
      lowStock: "Low stock",
      zeroStock: "Zero stock",
      alerts: "Alerts",

      workforce: "Workforce",
      payroll: "Payroll",
      materials: "Materials",
      inventory: "Inventory",
      gps: "GPS",
      generalLower: "general",

      activityByDay: "Activity by day",
      materialsByStatus: "Materials by status",

      delivered: "Delivered",
      returnedPartial: "Partially returned",
      returned: "Returned",
      pending: "Pending",
      approved: "Approved",
      rejected: "Rejected",
      consigned: "Consigned",

      activeTenant: "Active tenant",
      noData: "No data for the selected filters.",
      partialData: "Some blocks had no data or do not apply:",
      loadError: "Could not load Reports."
    },

    fr: {
      settings: "Configuration",
      logout: "Quitter",

      moduleEyebrow: "Module rapports",
      moduleTitle: "Rapports",
      generalReport: "Rapport général",
      moduleSubtitle: "Historique consolidé du Personnel, GPS, Matériaux, Inventaire et Paie. Ne modifie pas les données; il audite et exporte uniquement.",

      type: "Type",
      from: "De",
      to: "À",
      period: "Période",
      employee: "Employé",
      smartSearch: "Recherche intelligente",
      module: "Module",
      status: "Statut",

      generate: "Générer",
      csv: "CSV",
      back: "Retour",
      dashboard: "Tableau de bord",
      kpis: "KPIs",

      general: "Général",
      all: "Tous",
      sevenDays: "7 jours",
      fifteenDays: "15 jours",
      month: "Mois",
      custom: "Personnalisé",

      searchPlaceholder: "Rechercher employé, MAT, GPS, stock, paie...",

      reportHelp: "Le rapport général consolide toute l’entreprise. La vue par personne filtre le collaborateur sélectionné.",

      executiveSummary: "Résumé exécutif",
      periodIndicators: "Indicateurs de la période",

      activeStaff: "Personnel actif",
      shiftsStarted: "Services démarrés",
      regularHours: "Heures normales",
      totalPayroll: "Paie totale",
      gpsOutside: "GPS hors périmètre",
      materialOrders: "Commandes matériel",
      consignments: "Consignes",
      lowStock: "Stock faible",
      zeroStock: "Stock zéro",
      alerts: "Alertes",

      workforce: "Workforce",
      payroll: "Paie",
      materials: "Matériaux",
      inventory: "Inventaire",
      gps: "GPS",
      generalLower: "général",

      activityByDay: "Activité par jour",
      materialsByStatus: "Matériaux par statut",

      delivered: "Livré",
      returnedPartial: "Retour partiel",
      returned: "Retourné",
      pending: "En attente",
      approved: "Approuvé",
      rejected: "Rejeté",
      consigned: "Consigné",

      activeTenant: "Tenant actif",
      noData: "Aucune donnée pour les filtres sélectionnés.",
      partialData: "Certains blocs n’avaient pas de données ou ne s’appliquent pas :",
      loadError: "Impossible de charger les rapports."
    }
  };

  const ALIASES = {};

  function norm(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function addAlias(text, key) {
    ALIASES[norm(text)] = key;
  }

  Object.keys(DICT).forEach((language) => {
    Object.keys(DICT[language]).forEach((key) => {
      addAlias(DICT[language][key], key);
      addAlias(String(DICT[language][key]).toUpperCase(), key);
    });
  });

  [
    ["Modulo Reportes", "moduleEyebrow"],
    ["Módulo Reportes", "moduleEyebrow"],
    ["REPORTES MODULE", "moduleEyebrow"],
    ["REPORTS MODULE", "moduleEyebrow"],

    ["Reportes", "moduleTitle"],
    ["Reports", "moduleTitle"],

    ["Reporte general", "generalReport"],
    ["General report", "generalReport"],

    ["Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta.", "moduleSubtitle"],
    ["Historico consolidado de Personal, GPS, Materiales, Inventario y Nomina. No modifica datos; solo audita y exporta.", "moduleSubtitle"],

    ["TIPO", "type"],
    ["Tipo", "type"],
    ["FROM", "from"],
    ["TO", "to"],
    ["PERIOD", "period"],
    ["EMPLOYEE", "employee"],
    ["LUPA INTELIGENTE", "smartSearch"],
    ["Lupa inteligente", "smartSearch"],
    ["MODULE", "module"],
    ["Módulo", "module"],
    ["Modulo", "module"],
    ["STATUS", "status"],
    ["Estado", "status"],

    ["Generar", "generate"],
    ["Generate", "generate"],
    ["CSV", "csv"],
    ["Back", "back"],
    ["Volver", "back"],

    ["General", "general"],
    ["All", "all"],
    ["Todos", "all"],
    ["7 days", "sevenDays"],
    ["7 días", "sevenDays"],
    ["7 dias", "sevenDays"],
    ["15 days", "fifteenDays"],
    ["15 días", "fifteenDays"],
    ["15 dias", "fifteenDays"],
    ["Mes", "month"],
    ["Personalizado", "custom"],

    ["Buscar empleado, MAT, GPS, stock, nómina...", "searchPlaceholder"],
    ["Buscar empleado, MAT, GPS, stock, nomina...", "searchPlaceholder"],

    ["RESUMEN EJECUTIVO", "executiveSummary"],
    ["Resumen ejecutivo", "executiveSummary"],
    ["Indicadores del periodo", "periodIndicators"],
    ["INDICADORES DEL PERIODO", "periodIndicators"],

    ["PERSONAL ACTIVO", "activeStaff"],
    ["Personal activo", "activeStaff"],
    ["TURNOS INICIADOS", "shiftsStarted"],
    ["Turnos iniciados", "shiftsStarted"],
    ["REGULAR HOURS", "regularHours"],
    ["Regular hours", "regularHours"],
    ["Horas ordinarias", "regularHours"],
    ["TOTAL NÓMINA", "totalPayroll"],
    ["TOTAL NOMINA", "totalPayroll"],
    ["Total nómina", "totalPayroll"],
    ["Total nomina", "totalPayroll"],
    ["GPS OUTSIDE", "gpsOutside"],
    ["GPS fuera", "gpsOutside"],
    ["ÓRDENES MATERIAL", "materialOrders"],
    ["ORDENES MATERIAL", "materialOrders"],
    ["Órdenes material", "materialOrders"],
    ["Ordenes material", "materialOrders"],
    ["CONSIGNAS", "consignments"],
    ["Consignas", "consignments"],
    ["LOW STOCK", "lowStock"],
    ["Low stock", "lowStock"],
    ["Stock bajo", "lowStock"],
    ["STOCK CERO", "zeroStock"],
    ["Stock cero", "zeroStock"],
    ["ALERTAS", "alerts"],
    ["Alertas", "alerts"],

    ["Workforce", "workforce"],
    ["Payroll", "payroll"],
    ["Nómina", "payroll"],
    ["Nomina", "payroll"],
    ["Materials", "materials"],
    ["Materiales", "materials"],
    ["Inventory", "inventory"],
    ["Inventario", "inventory"],
    ["general", "generalLower"],

    ["Actividad por día", "activityByDay"],
    ["Actividad por dia", "activityByDay"],
    ["Materiales por estado", "materialsByStatus"],

    ["Delivered", "delivered"],
    ["delivered", "delivered"],
    ["Entregado", "delivered"],
    ["returned_partial", "returnedPartial"],
    ["Returned partial", "returnedPartial"],
    ["Partially returned", "returnedPartial"],
    ["returned", "returned"],
    ["Returned", "returned"],
    ["pending", "pending"],
    ["Pending", "pending"],
    ["approved", "approved"],
    ["Approved", "approved"],
    ["rejected", "rejected"],
    ["Rejected", "rejected"],
    ["consigned", "consigned"],
    ["Consigned", "consigned"],

    ["The general report consolidates the entire company. Person view filters by the selected collaborator.", "reportHelp"],
    ["Reporte general consolida toda la empresa. Por persona filtra al colaborador seleccionado.", "reportHelp"],

    ["Sin datos para los filtros seleccionados.", "noData"],
    ["No data for the selected filters.", "noData"],
    ["No se pudo cargar Reportes.", "loadError"]
  ].forEach(([text, key]) => addAlias(text, key));

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
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
    if (app.querySelector(".cx-reports-table")) return true;
    if (app.querySelector(".cx-reports-toolbar")) return true;
    if (app.querySelector(".cx-reports-tabs")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Reports module") ||
      text.includes("Módulo Reportes") ||
      text.includes("Modulo Reportes") ||
      text.includes("General report") ||
      text.includes("Reporte general") ||
      text.includes("Indicadores del periodo") ||
      text.includes("Activity by day")
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
    timer = setTimeout(translateReports, 120);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateReports();
      if (count >= 12) clearInterval(id);
    }, 200);
  }

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 350);
    setTimeout(schedule, 900);
    setTimeout(schedule, 1500);
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

path.write_text(js, encoding="utf-8")
print("PATCH_OK: 020J-R2 Reports i18n expanded")
