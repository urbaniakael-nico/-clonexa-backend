from pathlib import Path
import re

js_path = Path("app/web/client_kpis_i18n_safe.js")
html_path = Path("app/web/client.html")

js = r'''
(function clonexaSafeKpisI18n020KR3() {
  "use strict";

  if (window.__CLONEXA_020K_R3_KPIS_I18N__) return;
  window.__CLONEXA_020K_R3_KPIS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const ENTRIES = {
    settings: {
      es: "Ajustes",
      en: "Settings",
      fr: "Configuration",
      aliases: ["Ajustes", "Settings", "Configuration"]
    },
    logout: {
      es: "Cerrar sesión",
      en: "Log out",
      fr: "Quitter",
      aliases: ["Cerrar sesión", "Cerrar sesion", "Log out", "Quitter"]
    },

    moduleEyebrow: {
      es: "Módulo KPIs",
      en: "KPIs module",
      fr: "Module KPIs",
      aliases: ["Módulo KPIs", "Modulo KPIs", "KPIS MODULE", "KPIs module", "Module KPIs"]
    },
    moduleTitle: {
      es: "KPIs Operativos",
      en: "Operational KPIs",
      fr: "KPIs opérationnels",
      aliases: ["KPIs Operativos", "Operational KPIs", "KPIs opérationnels"]
    },
    moduleSubtitle: {
      es: "Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nómina según módulos activos.",
      en: "Executive indicators calculated from Workforce, GPS, Materials, Inventory and Payroll based on active modules.",
      fr: "Indicateurs exécutifs calculés depuis Workforce, GPS, Matériaux, Inventaire et Paie selon les modules actifs.",
      aliases: [
        "Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nómina según módulos activos.",
        "Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nomina segun modulos activos.",
        "Executive indicators calculated from Workforce, GPS, Materials, Inventory and Payroll based on active modules."
      ]
    },
    liveInfo: {
      es: "Actualización automática cada 60s · Fuente: datos reales por módulo",
      en: "Automatic refresh every 60s · Source: real data by module",
      fr: "Actualisation automatique toutes les 60s · Source : données réelles par module",
      aliases: [
        "Actualización automática cada 60s · Fuente: datos reales por módulo",
        "Actualizacion automatica cada 60s · Fuente: datos reales por modulo",
        "Automatic refresh every 60s · Source: real data by module"
      ]
    },

    period: { es: "Periodo", en: "Period", fr: "Période", aliases: ["PERIODO", "PERÍODO", "Periodo", "Period"] },
    from: { es: "Desde", en: "From", fr: "De", aliases: ["DESDE", "Desde", "From"] },
    to: { es: "Hasta", en: "To", fr: "À", aliases: ["HASTA", "Hasta", "To"] },
    searchKpi: { es: "Buscar KPI", en: "Search KPI", fr: "Rechercher KPI", aliases: ["BUSCAR KPI", "Buscar KPI", "Search KPI"] },
    refresh: { es: "Actualizar", en: "Refresh", fr: "Actualiser", aliases: ["Actualizar", "Refresh", "Actualiser"] },
    csv: { es: "CSV", en: "CSV", fr: "CSV", aliases: ["CSV"] },
    back: { es: "Volver", en: "Back", fr: "Retour", aliases: ["Volver", "Back", "Retour"] },

    sevenDays: { es: "7 días", en: "7 days", fr: "7 jours", aliases: ["7 días", "7 dias", "7 days", "7 jours"] },
    fifteenDays: { es: "15 días", en: "15 days", fr: "15 jours", aliases: ["15 días", "15 dias", "15 days", "15 jours"] },
    month: { es: "Mes", en: "Month", fr: "Mois", aliases: ["Mes", "Month", "Mois"] },
    today: { es: "Hoy", en: "Today", fr: "Aujourd’hui", aliases: ["Hoy", "Today", "Aujourd’hui"] },
    custom: { es: "Personalizado", en: "Custom", fr: "Personnalisé", aliases: ["Personalizado", "Custom", "Personnalisé"] },

    executiveSummary: { es: "Resumen ejecutivo", en: "Executive summary", fr: "Résumé exécutif", aliases: ["RESUMEN EJECUTIVO", "Resumen ejecutivo", "Executive summary"] },
    liveOperation: { es: "Operación viva", en: "Live operation", fr: "Opération en direct", aliases: ["OPERACION VIVA", "OPERACIÓN VIVA", "Operación viva", "Operacion viva", "Live operation"] },
    activeModules: { es: "módulos activos", en: "active modules", fr: "modules actifs", aliases: ["módulos activos", "modulos activos", "active modules", "modules actifs"] },

    showOnPanel: { es: "Mostrar en panel", en: "Show on panel", fr: "Afficher sur le panneau", aliases: ["Mostrar en panel", "Show on panel", "Afficher sur le panneau"] },
    visibleOnPanel: { es: "Visible en panel", en: "Visible on panel", fr: "Visible sur le panneau", aliases: ["Visible en panel", "Visible on panel", "Visible sur le panneau"] },

    workforce: { es: "Workforce", en: "Workforce", fr: "Workforce", aliases: ["Workforce"] },
    materials: { es: "Materiales", en: "Materials", fr: "Matériaux", aliases: ["Materiales", "Materials", "MATERIALS", "Matériaux"] },
    inventory: { es: "Inventario", en: "Inventory", fr: "Inventaire", aliases: ["Inventario", "Inventory", "INVENTORY", "Inventaire"] },
    payroll: { es: "Nómina", en: "Payroll", fr: "Paie", aliases: ["Nómina", "Nomina", "Payroll", "PAYROLL", "Paie"] },
    gps: { es: "GPS", en: "GPS", fr: "GPS", aliases: ["GPS"] },
    reports: { es: "Reportes", en: "Reports", fr: "Rapports", aliases: ["Reportes", "Reports", "Rapports"] },
    crm: { es: "CRM Campo", en: "Field CRM", fr: "CRM terrain", aliases: ["CRM Campo", "Field CRM", "CRM terrain"] },
    bots: { es: "Bots", en: "Bots", fr: "Bots", aliases: ["Bots"] },
    general: { es: "General", en: "General", fr: "Général", aliases: ["General", "general", "GENERAL"] },

    activeStaff: { es: "Personal activo", en: "Active staff", fr: "Personnel actif", aliases: ["PERSONAL ACTIVO", "Personal activo", "ACTIVE STAFF", "Active staff"] },
    activeNow: { es: "Activos ahora", en: "Active now", fr: "Actifs maintenant", aliases: ["ACTIVOS AHORA", "Activos ahora", "ACTIVE NOW", "Active now"] },
    onBreak: { es: "En pausa", en: "On break", fr: "En pause", aliases: ["EN PAUSA", "En pausa", "ON BREAK", "On break"] },
    periodEvents: { es: "Eventos del periodo", en: "Period events", fr: "Événements de la période", aliases: ["EVENTOS DEL PERIODO", "Eventos del periodo", "PERIOD EVENTS", "Period events"] },

    sentLocations: { es: "Ubicaciones enviadas", en: "Locations sent", fr: "Positions envoyées", aliases: ["UBICACIONES ENVIADAS", "Ubicaciones enviadas", "LOCATIONS SENT", "Locations sent"] },
    gpsInside: { es: "GPS dentro", en: "GPS inside", fr: "GPS dans le périmètre", aliases: ["GPS DENTRO", "GPS dentro", "GPS INSIDE", "GPS inside"] },
    gpsOutside: { es: "GPS fuera", en: "GPS outside", fr: "GPS hors périmètre", aliases: ["GPS FUERA", "GPS fuera", "GPS OUTSIDE", "GPS outside"] },
    insidePerimeter: { es: "Dentro de perímetro", en: "Inside perimeter", fr: "Dans le périmètre", aliases: ["Dentro de perímetro", "Dentro de perimetro", "Inside perimeter"] },
    outsidePerimeter: { es: "Fuera de perímetro", en: "Outside perimeter", fr: "Hors périmètre", aliases: ["Fuera de perímetro", "Fuera de perimetro", "Outside perimeter", "outside perimeter"] },
    activePerimeters: { es: "Perímetros activos", en: "Active perimeters", fr: "Périmètres actifs", aliases: ["Perímetros activos", "Perimetros activos", "Active perimeters"] },

    materialRequests: { es: "Solicitudes material", en: "Material requests", fr: "Demandes matériel", aliases: ["SOLICITUDES MATERIAL", "Solicitudes material", "MATERIAL REQUESTS", "Material requests"] },
    deliveredMaterial: { es: "Material entregado", en: "Delivered material", fr: "Matériel livré", aliases: ["MATERIAL ENTREGADO", "Material entregado", "DELIVERED MATERIAL", "Delivered material"] },
    returnedMaterial: { es: "Material devuelto", en: "Returned material", fr: "Matériel retourné", aliases: ["RETURNED MATERIAL", "Returned material", "Material devuelto", "MATERIAL DEVUELTO"] },
    materialConsigned: { es: "Material en consigna", en: "Consigned material", fr: "Matériel consigné", aliases: ["MATERIAL EN CONSIGNA", "Material en consigna", "En consigna", "CONSIGNED MATERIAL", "Consigned material", "MATERIAL CONSIGNED"] },
    materialPending: { es: "Material pendiente", en: "Pending material", fr: "Matériel en attente", aliases: ["MATERIAL PENDIENTE", "Material pendiente", "PENDING MATERIAL", "Pending material"] },
    materialApproved: { es: "Material aprobado", en: "Approved material", fr: "Matériel approuvé", aliases: ["MATERIAL APROBADO", "Material aprobado", "APPROVED MATERIAL", "Approved material"] },
    materialRejected: { es: "Material rechazado", en: "Rejected material", fr: "Matériel rejeté", aliases: ["MATERIAL RECHAZADO", "Material rechazado", "REJECTED MATERIAL", "Rejected material"] },
    delivered: { es: "Entregadas", en: "Delivered", fr: "Livrées", aliases: ["Entregadas", "Entregada", "Delivered", "DELIVERED"] },
    returned: { es: "Devueltas", en: "Returned", fr: "Retournées", aliases: ["Devueltas", "Devuelta", "Returned", "RETURNED"] },
    consigned: { es: "En consigna", en: "Consigned", fr: "Consigné", aliases: ["En consigna", "Consigned", "CONSIGNED"] },
    pending: { es: "Pendientes", en: "Pending", fr: "En attente", aliases: ["Pendientes", "Pendiente", "Pending", "PENDING"] },
    approved: { es: "Aprobadas", en: "Approved", fr: "Approuvées", aliases: ["Aprobadas", "Aprobada", "Approved", "APPROVED"] },
    rejected: { es: "Rechazadas", en: "Rejected", fr: "Rejetées", aliases: ["Rechazadas", "Rechazada", "Rejected", "REJECTED"] },

    ordersMovements: { es: "Órdenes y movimientos", en: "Orders and movements", fr: "Commandes et mouvements", aliases: ["Órdenes y movimientos", "Ordenes y movimientos", "Orders and movements"] },
    periodRequests: { es: "Solicitudes del periodo", en: "Period requests", fr: "Demandes de la période", aliases: ["Solicitudes del periodo", "Period requests"] },
    noRequestsPeriod: { es: "Sin solicitudes en el periodo.", en: "No requests in the period.", fr: "Aucune demande dans la période.", aliases: ["Sin solicitudes en el periodo.", "No requests in the period."] },

    inventoryItems: { es: "Ítems inventario", en: "Inventory items", fr: "Articles inventaire", aliases: ["ITEMS INVENTARIO", "Ítems inventario", "Items inventario", "INVENTORY ITEMS", "Inventory items"] },
    inventoryOutputs: { es: "Salidas inventario", en: "Inventory outputs", fr: "Sorties inventaire", aliases: ["SALIDAS INVENTARIO", "Salidas inventario", "INVENTORY OUTPUTS", "Inventory outputs"] },
    activeItems: { es: "Ítems activos", en: "Active items", fr: "Articles actifs", aliases: ["Items activos", "Ítems activos", "Active items"] },
    lowStock: { es: "Stock bajo", en: "Low stock", fr: "Stock faible", aliases: ["LOW STOCK", "Low stock", "Stock bajo", "STOCK BAJO"] },
    zeroStock: { es: "Stock cero", en: "Zero stock", fr: "Stock zéro", aliases: ["ZERO STOCK", "Zero stock", "Stock cero", "STOCK CERO", "Stock en cero"] },
    stockUnits: { es: "Unidades en stock", en: "Units in stock", fr: "Unités en stock", aliases: ["Unidades en stock", "Units in stock"] },
    availability: { es: "Disponibilidad", en: "Availability", fr: "Disponibilité", aliases: ["Disponibilidad", "Availability"] },

    payrollEstimate: { es: "Estimado del periodo", en: "Period estimate", fr: "Estimation de la période", aliases: ["Estimado del periodo", "Period estimate"] },
    regularHours: { es: "Horas ordinarias", en: "Regular hours", fr: "Heures normales", aliases: ["REGULAR HOURS", "Regular hours", "Horas ordinarias", "HORAS ORDINARIAS"] },
    extraHours: { es: "Horas extra", en: "Extra hours", fr: "Heures supplémentaires", aliases: ["EXTRA HOURS", "Extra hours", "Horas extra", "HORAS EXTRA"] },
    shiftsWithCutoff: { es: "Turnos con corte", en: "Shifts with cutoff", fr: "Services avec clôture", aliases: ["TURNOS CON CORTE", "Turnos con corte", "SHIFTS WITH CUTOFF", "Shifts with cutoff"] },
    grossPayroll: { es: "Bruto nómina", en: "Gross payroll", fr: "Paie brute", aliases: ["BRUTO NÓMINA", "BRUTO NOMINA", "Bruto nómina", "Bruto", "Gross payroll", "GROSS PAYROLL"] },
    payrollDiscounts: { es: "Descuentos nómina", en: "Payroll discounts", fr: "Remises paie", aliases: ["DESCUENTOS NÓMINA", "DESCUENTOS NOMINA", "Descuentos nómina", "Descuentos", "Payroll discounts", "PAYROLL DISCOUNTS"] },
    estimatedPayroll: { es: "Nómina estimada", en: "Estimated payroll", fr: "Paie estimée", aliases: ["ESTIMATED PAYROLL", "Estimated payroll", "Nómina estimada", "Nomina estimada", "NÓMINA ESTIMADA", "NOMINA ESTIMADA"] },
    totalEstimated: { es: "Total estimado", en: "Estimated total", fr: "Total estimé", aliases: ["Total estimado", "TOTAL ESTIMADO", "Estimated total"] },
    source: { es: "Fuente", en: "Source", fr: "Source", aliases: ["Fuente", "FUENTE", "Source"] },
    livePayrollCalculation: { es: "cálculo nómina en vivo", en: "live payroll calculation", fr: "calcul paie en direct", aliases: ["live_payroll_calculation", "live payroll calculation"] },
    cutoffCalculation: { es: "Corte y cálculo", en: "Cutoff and calculation", fr: "Clôture et calcul", aliases: ["Corte y cálculo", "Corte y calculo", "Cutoff and calculation"] },

    operationalTop: { es: "Top operativo", en: "Operational top", fr: "Top opérationnel", aliases: ["TOP OPERATIVO", "Top operativo", "Operational top"] },
    mostRequestedMaterials: { es: "Materiales más solicitados", en: "Most requested materials", fr: "Matériaux les plus demandés", aliases: ["Materiales más solicitados", "Materiales mas solicitados", "Most requested materials"] },

    alerts: { es: "Alertas", en: "Alerts", fr: "Alertes", aliases: ["ALERTAS", "Alertas", "ALERTS", "Alerts"] },
    operationalRisks: { es: "Riesgos operativos", en: "Operational risks", fr: "Risques opérationnels", aliases: ["Riesgos operativos", "Operational risks"] },
    noCriticalAlerts: { es: "Sin alertas críticas en el periodo.", en: "No critical alerts in the period.", fr: "Aucune alerte critique dans la période.", aliases: ["Sin alertas críticas en el periodo.", "Sin alertas criticas en el periodo.", "No critical alerts in the period."] },

    status: { es: "Estado", en: "Status", fr: "Statut", aliases: ["Estado", "STATUS", "Status"] },
    module: { es: "Módulo", en: "Module", fr: "Module", aliases: ["Módulo", "Modulo", "MODULE", "Module"] },
    activeTenant: { es: "Tenant activo", en: "Active tenant", fr: "Tenant actif", aliases: ["Tenant activo", "Active tenant"] },
    loadError: { es: "No se pudieron cargar KPIs.", en: "Could not load KPIs.", fr: "Impossible de charger les KPIs.", aliases: ["No se pudieron cargar KPIs.", "Could not load KPIs."] }
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

  Object.keys(ENTRIES).forEach((key) => {
    const entry = ENTRIES[key];
    addAlias(entry.es, key);
    addAlias(entry.en, key);
    addAlias(entry.fr, key);
    (entry.aliases || []).forEach((alias) => addAlias(alias, key));
  });

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function t(key) {
    const entry = ENTRIES[key];
    return entry ? entry[lang()] || entry.es || key : key;
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
      text.includes("Executive summary") ||
      text.includes("Orders and movements")
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
    timer = setTimeout(translateKpis, 100);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateKpis();
      if (count >= 16) clearInterval(id);
    }, 170);
  }

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 300);
    setTimeout(schedule, 750);
    setTimeout(schedule, 1300);
    setTimeout(schedule, 2200);
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
    "client_kpis_i18n_safe.js?v=020KR3",
    html,
    flags=re.IGNORECASE,
)
html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020K-R3 KPIs lower block dictionary applied")
