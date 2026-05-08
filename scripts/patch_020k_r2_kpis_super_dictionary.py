from pathlib import Path
import re

js_path = Path("app/web/client_kpis_i18n_safe.js")
html_path = Path("app/web/client.html")

js = r'''
(function clonexaSafeKpisI18n020KR2() {
  "use strict";

  if (window.__CLONEXA_020K_R2_KPIS_I18N__) return;
  window.__CLONEXA_020K_R2_KPIS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const DICT = {
    es: {
      settings: "Ajustes",
      logout: "Cerrar sesión",

      moduleEyebrow: "Módulo KPIs",
      moduleTitle: "KPIs Operativos",
      moduleSubtitle: "Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nómina según módulos activos.",
      liveInfo: "Actualización automática cada 60s · Fuente: datos reales por módulo",

      period: "Periodo",
      from: "Desde",
      to: "Hasta",
      searchKpi: "Buscar KPI",
      searchPlaceholder: "Buscar: nómina, horas, GPS, stock, materiales, devueltas...",

      refresh: "Actualizar",
      csv: "CSV",
      back: "Volver",

      sevenDays: "7 días",
      fifteenDays: "15 días",
      month: "Mes",
      today: "Hoy",
      custom: "Personalizado",

      executiveSummary: "Resumen ejecutivo",
      liveOperation: "Operación viva",
      activeModules: "módulos activos",

      showOnPanel: "Mostrar en panel",
      visibleOnPanel: "Visible en panel",

      workforce: "Workforce",
      materials: "Materiales",
      inventory: "Inventario",
      payroll: "Nómina",
      gps: "GPS",
      reports: "Reportes",
      crm: "CRM Campo",
      bots: "Bots",
      general: "General",

      activeStaff: "Personal activo",
      activeNow: "Activos ahora",
      onBreak: "En pausa",
      periodEvents: "Eventos del periodo",

      sentLocations: "Ubicaciones enviadas",
      gpsInside: "GPS dentro",
      gpsOutside: "GPS fuera",

      materialRequests: "Solicitudes material",
      deliveredMaterial: "Material entregado",
      returnedMaterial: "Material devuelto",
      materialConsigned: "Material en consigna",
      materialPending: "Material pendiente",
      materialApproved: "Material aprobado",
      materialRejected: "Material rechazado",

      inventoryItems: "Ítems inventario",
      inventoryOutputs: "Salidas inventario",
      lowStock: "Stock bajo",
      zeroStock: "Stock cero",

      regularHours: "Horas ordinarias",
      extraHours: "Horas extra",
      shiftsWithCutoff: "Turnos con corte",
      grossPayroll: "Bruto nómina",
      payrollDiscounts: "Descuentos nómina",
      estimatedPayroll: "Nómina estimada",

      alerts: "Alertas",
      operationalRisks: "Riesgos operativos",
      noCriticalAlerts: "Sin alertas críticas en el periodo.",

      activeItems: "Ítems activos",
      stockUnits: "Unidades en stock",
      ordersMovements: "Órdenes y movimientos",
      locationPerimeters: "Ubicación y perímetros",
      availability: "Disponibilidad",
      cutoffCalculation: "Corte y cálculo",
      periodRequests: "Solicitudes del periodo",

      status: "Estado",
      module: "Módulo",
      activeTenant: "Tenant activo",
      loadError: "No se pudieron cargar KPIs."
    },

    en: {
      settings: "Settings",
      logout: "Log out",

      moduleEyebrow: "KPIs module",
      moduleTitle: "Operational KPIs",
      moduleSubtitle: "Executive indicators calculated from Workforce, GPS, Materials, Inventory and Payroll based on active modules.",
      liveInfo: "Automatic refresh every 60s · Source: real data by module",

      period: "Period",
      from: "From",
      to: "To",
      searchKpi: "Search KPI",
      searchPlaceholder: "Search: payroll, hours, GPS, stock, materials, returns...",

      refresh: "Refresh",
      csv: "CSV",
      back: "Back",

      sevenDays: "7 days",
      fifteenDays: "15 days",
      month: "Month",
      today: "Today",
      custom: "Custom",

      executiveSummary: "Executive summary",
      liveOperation: "Live operation",
      activeModules: "active modules",

      showOnPanel: "Show on panel",
      visibleOnPanel: "Visible on panel",

      workforce: "Workforce",
      materials: "Materials",
      inventory: "Inventory",
      payroll: "Payroll",
      gps: "GPS",
      reports: "Reports",
      crm: "Field CRM",
      bots: "Bots",
      general: "General",

      activeStaff: "Active staff",
      activeNow: "Active now",
      onBreak: "On break",
      periodEvents: "Period events",

      sentLocations: "Locations sent",
      gpsInside: "GPS inside",
      gpsOutside: "GPS outside",

      materialRequests: "Material requests",
      deliveredMaterial: "Delivered material",
      returnedMaterial: "Returned material",
      materialConsigned: "Consigned material",
      materialPending: "Pending material",
      materialApproved: "Approved material",
      materialRejected: "Rejected material",

      inventoryItems: "Inventory items",
      inventoryOutputs: "Inventory outputs",
      lowStock: "Low stock",
      zeroStock: "Zero stock",

      regularHours: "Regular hours",
      extraHours: "Extra hours",
      shiftsWithCutoff: "Shifts with cutoff",
      grossPayroll: "Gross payroll",
      payrollDiscounts: "Payroll discounts",
      estimatedPayroll: "Estimated payroll",

      alerts: "Alerts",
      operationalRisks: "Operational risks",
      noCriticalAlerts: "No critical alerts in the period.",

      activeItems: "Active items",
      stockUnits: "Units in stock",
      ordersMovements: "Orders and movements",
      locationPerimeters: "Location and perimeters",
      availability: "Availability",
      cutoffCalculation: "Cutoff and calculation",
      periodRequests: "Period requests",

      status: "Status",
      module: "Module",
      activeTenant: "Active tenant",
      loadError: "Could not load KPIs."
    },

    fr: {
      settings: "Configuration",
      logout: "Quitter",

      moduleEyebrow: "Module KPIs",
      moduleTitle: "KPIs opérationnels",
      moduleSubtitle: "Indicateurs exécutifs calculés depuis Workforce, GPS, Matériaux, Inventaire et Paie selon les modules actifs.",
      liveInfo: "Actualisation automatique toutes les 60s · Source : données réelles par module",

      period: "Période",
      from: "De",
      to: "À",
      searchKpi: "Rechercher KPI",
      searchPlaceholder: "Rechercher : paie, heures, GPS, stock, matériaux, retours...",

      refresh: "Actualiser",
      csv: "CSV",
      back: "Retour",

      sevenDays: "7 jours",
      fifteenDays: "15 jours",
      month: "Mois",
      today: "Aujourd’hui",
      custom: "Personnalisé",

      executiveSummary: "Résumé exécutif",
      liveOperation: "Opération en direct",
      activeModules: "modules actifs",

      showOnPanel: "Afficher sur le panneau",
      visibleOnPanel: "Visible sur le panneau",

      workforce: "Workforce",
      materials: "Matériaux",
      inventory: "Inventaire",
      payroll: "Paie",
      gps: "GPS",
      reports: "Rapports",
      crm: "CRM terrain",
      bots: "Bots",
      general: "Général",

      activeStaff: "Personnel actif",
      activeNow: "Actifs maintenant",
      onBreak: "En pause",
      periodEvents: "Événements de la période",

      sentLocations: "Positions envoyées",
      gpsInside: "GPS dans le périmètre",
      gpsOutside: "GPS hors périmètre",

      materialRequests: "Demandes matériel",
      deliveredMaterial: "Matériel livré",
      returnedMaterial: "Matériel retourné",
      materialConsigned: "Matériel consigné",
      materialPending: "Matériel en attente",
      materialApproved: "Matériel approuvé",
      materialRejected: "Matériel rejeté",

      inventoryItems: "Articles inventaire",
      inventoryOutputs: "Sorties inventaire",
      lowStock: "Stock faible",
      zeroStock: "Stock zéro",

      regularHours: "Heures normales",
      extraHours: "Heures supplémentaires",
      shiftsWithCutoff: "Services avec clôture",
      grossPayroll: "Paie brute",
      payrollDiscounts: "Remises paie",
      estimatedPayroll: "Paie estimée",

      alerts: "Alertes",
      operationalRisks: "Risques opérationnels",
      noCriticalAlerts: "Aucune alerte critique dans la période.",

      activeItems: "Articles actifs",
      stockUnits: "Unités en stock",
      ordersMovements: "Commandes et mouvements",
      locationPerimeters: "Position et périmètres",
      availability: "Disponibilité",
      cutoffCalculation: "Clôture et calcul",
      periodRequests: "Demandes de la période",

      status: "Statut",
      module: "Module",
      activeTenant: "Tenant actif",
      loadError: "Impossible de charger les KPIs."
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
    if (!text) return;
    ALIASES[norm(text)] = key;
    ALIASES[norm(String(text).toUpperCase())] = key;
  }

  Object.keys(DICT).forEach((language) => {
    Object.keys(DICT[language]).forEach((key) => {
      addAlias(DICT[language][key], key);
    });
  });

  [
    ["Módulo KPIs", "moduleEyebrow"],
    ["Modulo KPIs", "moduleEyebrow"],
    ["KPIS MODULE", "moduleEyebrow"],
    ["KPIs Operativos", "moduleTitle"],
    ["Operational KPIs", "moduleTitle"],

    ["Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nómina según módulos activos.", "moduleSubtitle"],
    ["Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nomina segun modulos activos.", "moduleSubtitle"],

    ["Actualización automática cada 60s · Fuente: datos reales por módulo", "liveInfo"],
    ["Actualizacion automatica cada 60s · Fuente: datos reales por modulo", "liveInfo"],

    ["PERIODO", "period"],
    ["PERÍODO", "period"],
    ["Periodo", "period"],
    ["DESDE", "from"],
    ["Desde", "from"],
    ["HASTA", "to"],
    ["Hasta", "to"],
    ["BUSCAR KPI", "searchKpi"],
    ["Buscar KPI", "searchKpi"],
    ["Buscar: nómina, horas, gps, stock, materiales, devueltas...", "searchPlaceholder"],
    ["Buscar: nomina, horas, gps, stock, materiales, devueltas...", "searchPlaceholder"],

    ["Actualizar", "refresh"],
    ["CSV", "csv"],
    ["Volver", "back"],

    ["7 días", "sevenDays"],
    ["7 dias", "sevenDays"],
    ["7 days", "sevenDays"],
    ["15 días", "fifteenDays"],
    ["15 dias", "fifteenDays"],
    ["15 days", "fifteenDays"],
    ["Mes", "month"],
    ["Hoy", "today"],
    ["Personalizado", "custom"],

    ["RESUMEN EJECUTIVO", "executiveSummary"],
    ["Resumen ejecutivo", "executiveSummary"],
    ["OPERACION VIVA", "liveOperation"],
    ["OPERACIÓN VIVA", "liveOperation"],
    ["Operación viva", "liveOperation"],
    ["Operacion viva", "liveOperation"],
    ["Live operation", "liveOperation"],

    ["módulos activos", "activeModules"],
    ["modulos activos", "activeModules"],
    ["active modules", "activeModules"],

    ["Mostrar en panel", "showOnPanel"],
    ["Show on panel", "showOnPanel"],
    ["Visible en panel", "visibleOnPanel"],
    ["Visible on panel", "visibleOnPanel"],

    ["Workforce", "workforce"],
    ["Materials", "materials"],
    ["Materiales", "materials"],
    ["Inventory", "inventory"],
    ["Inventario", "inventory"],
    ["Payroll", "payroll"],
    ["Nómina", "payroll"],
    ["Nomina", "payroll"],
    ["GPS", "gps"],
    ["Reportes", "reports"],
    ["Reports", "reports"],
    ["CRM Campo", "crm"],
    ["Bots", "bots"],
    ["General", "general"],

    ["PERSONAL ACTIVO", "activeStaff"],
    ["Personal activo", "activeStaff"],
    ["ACTIVE STAFF", "activeStaff"],
    ["ACTIVOS AHORA", "activeNow"],
    ["Activos ahora", "activeNow"],
    ["ACTIVE NOW", "activeNow"],
    ["EN PAUSA", "onBreak"],
    ["En pausa", "onBreak"],
    ["ON BREAK", "onBreak"],
    ["EVENTOS DEL PERIODO", "periodEvents"],
    ["Eventos del periodo", "periodEvents"],
    ["PERIOD EVENTS", "periodEvents"],

    ["UBICACIONES ENVIADAS", "sentLocations"],
    ["Ubicaciones enviadas", "sentLocations"],
    ["LOCATIONS SENT", "sentLocations"],
    ["GPS DENTRO", "gpsInside"],
    ["GPS dentro", "gpsInside"],
    ["GPS INSIDE", "gpsInside"],
    ["GPS FUERA", "gpsOutside"],
    ["GPS fuera", "gpsOutside"],
    ["GPS OUTSIDE", "gpsOutside"],

    ["SOLICITUDES MATERIAL", "materialRequests"],
    ["Solicitudes material", "materialRequests"],
    ["MATERIAL REQUESTS", "materialRequests"],
    ["MATERIAL ENTREGADO", "deliveredMaterial"],
    ["Material entregado", "deliveredMaterial"],
    ["DELIVERED MATERIAL", "deliveredMaterial"],
    ["RETURNED MATERIAL", "returnedMaterial"],
    ["Material devuelto", "returnedMaterial"],
    ["MATERIAL DEVUELTO", "returnedMaterial"],
    ["MATERIAL EN CONSIGNA", "materialConsigned"],
    ["Material en consigna", "materialConsigned"],
    ["MATERIAL CONSIGNED", "materialConsigned"],
    ["CONSIGNED MATERIAL", "materialConsigned"],
    ["MATERIAL PENDIENTE", "materialPending"],
    ["Material pendiente", "materialPending"],
    ["PENDING MATERIAL", "materialPending"],
    ["MATERIAL APROBADO", "materialApproved"],
    ["Material aprobado", "materialApproved"],
    ["APPROVED MATERIAL", "materialApproved"],
    ["MATERIAL RECHAZADO", "materialRejected"],
    ["Material rechazado", "materialRejected"],
    ["REJECTED MATERIAL", "materialRejected"],

    ["ITEMS INVENTARIO", "inventoryItems"],
    ["Ítems inventario", "inventoryItems"],
    ["Items inventario", "inventoryItems"],
    ["INVENTORY ITEMS", "inventoryItems"],
    ["SALIDAS INVENTARIO", "inventoryOutputs"],
    ["Salidas inventario", "inventoryOutputs"],
    ["INVENTORY OUTPUTS", "inventoryOutputs"],
    ["LOW STOCK", "lowStock"],
    ["Stock bajo", "lowStock"],
    ["STOCK BAJO", "lowStock"],
    ["ZERO STOCK", "zeroStock"],
    ["Stock cero", "zeroStock"],
    ["STOCK CERO", "zeroStock"],

    ["REGULAR HOURS", "regularHours"],
    ["Horas ordinarias", "regularHours"],
    ["HORAS ORDINARIAS", "regularHours"],
    ["EXTRA HOURS", "extraHours"],
    ["Horas extra", "extraHours"],
    ["HORAS EXTRA", "extraHours"],
    ["TURNOS CON CORTE", "shiftsWithCutoff"],
    ["Turnos con corte", "shiftsWithCutoff"],
    ["SHIFTS WITH CUTOFF", "shiftsWithCutoff"],
    ["BRUTO NÓMINA", "grossPayroll"],
    ["BRUTO NOMINA", "grossPayroll"],
    ["Bruto nómina", "grossPayroll"],
    ["GROSS PAYROLL", "grossPayroll"],
    ["DESCUENTOS NÓMINA", "payrollDiscounts"],
    ["DESCUENTOS NOMINA", "payrollDiscounts"],
    ["Descuentos nómina", "payrollDiscounts"],
    ["PAYROLL DISCOUNTS", "payrollDiscounts"],
    ["ESTIMATED PAYROLL", "estimatedPayroll"],
    ["Nómina estimada", "estimatedPayroll"],
    ["Nomina estimada", "estimatedPayroll"],
    ["NÓMINA ESTIMADA", "estimatedPayroll"],
    ["NOMINA ESTIMADA", "estimatedPayroll"],

    ["ALERTAS", "alerts"],
    ["Alertas", "alerts"],
    ["ALERTS", "alerts"],
    ["Riesgos operativos", "operationalRisks"],
    ["Operational risks", "operationalRisks"],
    ["Sin alertas críticas en el periodo.", "noCriticalAlerts"],
    ["Sin alertas criticas en el periodo.", "noCriticalAlerts"],

    ["Estado", "status"],
    ["STATUS", "status"],
    ["Módulo", "module"],
    ["Modulo", "module"],
    ["MODULE", "module"],
    ["Tenant activo", "activeTenant"],

    ["No se pudieron cargar KPIs.", "loadError"]
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
    if (/^\$?\d+([.,]\d+)?(\s?[A-Z]{2,4})?$/.test(raw)) return true;
    return false;
  }

  function translateText(value) {
    const raw = String(value || "");
    const clean = raw.replace(/\s+/g, " ").trim();

    if (shouldSkipText(clean)) return raw;

    const modulesMatch = clean.match(/^(\d+)\s+(m[oó]dulos activos|active modules|modules actifs)$/i);
    if (modulesMatch) return raw.replace(clean, `${modulesMatch[1]} ${t("activeModules")}`);

    const liveMatch = clean.match(/^(.+?)\s*\/\s*(operaci[oó]n viva|live operation|opération en direct)$/i);
    if (liveMatch) return raw.replace(clean, `${liveMatch[1]} / ${t("liveOperation")}`);

    const key = ALIASES[norm(clean)];
    if (!key) return raw;

    return raw.replace(clean, t(key));
  }

  function isKpisVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector("[data-kpis-root]")) return true;
    if (app.querySelector(".cx-kpis-live")) return true;
    if (app.querySelector(".cx-kpis-block")) return true;
    if (app.querySelector(".cx-kpis-list")) return true;
    if (app.querySelector(".cx-kpis-section-grid")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Módulo KPIs") ||
      text.includes("Modulo KPIs") ||
      text.includes("KPIs Operativos") ||
      text.includes("Operational KPIs") ||
      text.includes("Resumen ejecutivo") ||
      text.includes("Executive summary")
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

  function translateKpis() {
    try {
      if (!isKpisVisible()) return;

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
      console.warn("CLONEXA KPIs i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateKpis, 120);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateKpis();
      if (count >= 14) clearInterval(id);
    }, 180);
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
      console.warn("CLONEXA KPIs i18n init skipped:", error);
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

html = html_path.read_text(encoding="utf-8-sig")
html = re.sub(
    r"client_kpis_i18n_safe\.js(?:\?v=[^\"']*)?",
    "client_kpis_i18n_safe.js?v=020KR2",
    html,
    flags=re.IGNORECASE,
)
html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020K-R2 KPIs super dictionary applied")
