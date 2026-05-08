from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_kpis_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaSafeKpisI18n020KR1() {
  "use strict";

  if (window.__CLONEXA_020K_R1_KPIS_I18N__) return;
  window.__CLONEXA_020K_R1_KPIS_I18N__ = true;

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
      staffWorkforce: "Personal / Workforce",
      operationalStatus: "Estado operativo",
      activeStaff: "Personal activo",
      activeNow: "Activos ahora",
      onBreak: "En pausa",
      periodEvents: "Eventos del periodo",

      gps: "GPS",
      locationPerimeters: "Ubicación y perímetros",
      sentLocations: "Ubicaciones enviadas",
      gpsInside: "GPS dentro",
      gpsOutside: "GPS fuera",
      insidePerimeter: "Dentro de perímetro",
      outsidePerimeter: "Fuera de perímetro",
      activePerimeters: "Perímetros activos",

      materials: "Materiales",
      ordersMovements: "Órdenes y movimientos",
      periodRequests: "Solicitudes del periodo",
      materialRequests: "Solicitudes material",
      delivered: "Entregadas",
      deliveredMaterial: "Material entregado",
      returned: "Devueltas",
      returnedMaterial: "Material devuelto",
      consignments: "Consignas",
      pending: "Pendientes",
      approved: "Aprobadas",
      rejected: "Rechazadas",
      noRequestsPeriod: "Sin solicitudes en el periodo.",

      inventory: "Inventario",
      availability: "Disponibilidad",
      activeItems: "Ítems activos",
      lowStock: "Stock bajo",
      zeroStock: "Stock en cero",
      stockUnits: "Unidades en stock",

      payroll: "Nómina",
      payrollCut: "Corte y cálculo",
      regularHours: "Horas ordinarias",
      extraHours: "Horas extra",
      grossPayroll: "Nómina bruta",
      estimatedPayroll: "Nómina estimada",
      discounts: "Descuentos",
      netTotal: "Total neto",
      estimatedTotal: "Total estimado",

      alerts: "Alertas",
      operationalRisks: "Riesgos operativos",
      noCriticalAlerts: "Sin alertas críticas en el periodo.",

      reports: "Reportes",
      crm: "CRM Campo",
      bots: "Bots",
      general: "General",
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
      staffWorkforce: "Staff / Workforce",
      operationalStatus: "Operating status",
      activeStaff: "Active staff",
      activeNow: "Active now",
      onBreak: "On break",
      periodEvents: "Period events",

      gps: "GPS",
      locationPerimeters: "Location and perimeters",
      sentLocations: "Locations sent",
      gpsInside: "GPS inside",
      gpsOutside: "GPS outside",
      insidePerimeter: "Inside perimeter",
      outsidePerimeter: "Outside perimeter",
      activePerimeters: "Active perimeters",

      materials: "Materials",
      ordersMovements: "Orders and movements",
      periodRequests: "Period requests",
      materialRequests: "Material requests",
      delivered: "Delivered",
      deliveredMaterial: "Delivered material",
      returned: "Returned",
      returnedMaterial: "Returned material",
      consignments: "Consignments",
      pending: "Pending",
      approved: "Approved",
      rejected: "Rejected",
      noRequestsPeriod: "No requests in the period.",

      inventory: "Inventory",
      availability: "Availability",
      activeItems: "Active items",
      lowStock: "Low stock",
      zeroStock: "Zero stock",
      stockUnits: "Units in stock",

      payroll: "Payroll",
      payrollCut: "Cutoff and calculation",
      regularHours: "Regular hours",
      extraHours: "Extra hours",
      grossPayroll: "Gross payroll",
      estimatedPayroll: "Estimated payroll",
      discounts: "Discounts",
      netTotal: "Net total",
      estimatedTotal: "Estimated total",

      alerts: "Alerts",
      operationalRisks: "Operational risks",
      noCriticalAlerts: "No critical alerts in the period.",

      reports: "Reports",
      crm: "Field CRM",
      bots: "Bots",
      general: "General",
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
      staffWorkforce: "Personnel / Workforce",
      operationalStatus: "État opérationnel",
      activeStaff: "Personnel actif",
      activeNow: "Actifs maintenant",
      onBreak: "En pause",
      periodEvents: "Événements de la période",

      gps: "GPS",
      locationPerimeters: "Position et périmètres",
      sentLocations: "Positions envoyées",
      gpsInside: "GPS dans le périmètre",
      gpsOutside: "GPS hors périmètre",
      insidePerimeter: "Dans le périmètre",
      outsidePerimeter: "Hors périmètre",
      activePerimeters: "Périmètres actifs",

      materials: "Matériaux",
      ordersMovements: "Commandes et mouvements",
      periodRequests: "Demandes de la période",
      materialRequests: "Demandes matériel",
      delivered: "Livrées",
      deliveredMaterial: "Matériel livré",
      returned: "Retournées",
      returnedMaterial: "Matériel retourné",
      consignments: "Consignes",
      pending: "En attente",
      approved: "Approuvées",
      rejected: "Rejetées",
      noRequestsPeriod: "Aucune demande dans la période.",

      inventory: "Inventaire",
      availability: "Disponibilité",
      activeItems: "Articles actifs",
      lowStock: "Stock faible",
      zeroStock: "Stock zéro",
      stockUnits: "Unités en stock",

      payroll: "Paie",
      payrollCut: "Clôture et calcul",
      regularHours: "Heures normales",
      extraHours: "Heures supplémentaires",
      grossPayroll: "Paie brute",
      estimatedPayroll: "Paie estimée",
      discounts: "Remises",
      netTotal: "Total net",
      estimatedTotal: "Total estimé",

      alerts: "Alertes",
      operationalRisks: "Risques opérationnels",
      noCriticalAlerts: "Aucune alerte critique dans la période.",

      reports: "Rapports",
      crm: "CRM terrain",
      bots: "Bots",
      general: "Général",
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
    ALIASES[norm(text)] = key;
  }

  Object.keys(DICT).forEach((language) => {
    Object.keys(DICT[language]).forEach((key) => {
      addAlias(DICT[language][key], key);
      addAlias(String(DICT[language][key]).toUpperCase(), key);
    });
  });

  [
    ["Módulo KPIs", "moduleEyebrow"],
    ["Modulo KPIs", "moduleEyebrow"],
    ["KPIS MODULE", "moduleEyebrow"],
    ["KPIs Operativos", "moduleTitle"],
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

    ["Resumen ejecutivo", "executiveSummary"],
    ["RESUMEN EJECUTIVO", "executiveSummary"],
    ["Operación viva", "liveOperation"],
    ["Operacion viva", "liveOperation"],
    ["Live operation", "liveOperation"],
    ["módulos activos", "activeModules"],
    ["modulos activos", "activeModules"],
    ["active modules", "activeModules"],

    ["Mostrar en panel", "showOnPanel"],
    ["Visible en panel", "visibleOnPanel"],

    ["Personal / Workforce", "staffWorkforce"],
    ["Estado operativo", "operationalStatus"],
    ["Personal activo", "activeStaff"],
    ["PERSONAL ACTIVO", "activeStaff"],
    ["Activos ahora", "activeNow"],
    ["ACTIVOS AHORA", "activeNow"],
    ["En pausa", "onBreak"],
    ["EN PAUSA", "onBreak"],
    ["Eventos del periodo", "periodEvents"],
    ["EVENTOS DEL PERIODO", "periodEvents"],

    ["GPS", "gps"],
    ["Ubicación y perímetros", "locationPerimeters"],
    ["Ubicacion y perimetros", "locationPerimeters"],
    ["Ubicaciones enviadas", "sentLocations"],
    ["UBICACIONES ENVIADAS", "sentLocations"],
    ["GPS dentro", "gpsInside"],
    ["GPS DENTRO", "gpsInside"],
    ["GPS fuera", "gpsOutside"],
    ["GPS FUERA", "gpsOutside"],
    ["Dentro de perímetro", "insidePerimeter"],
    ["Dentro de perimetro", "insidePerimeter"],
    ["Fuera de perímetro", "outsidePerimeter"],
    ["Fuera de perimetro", "outsidePerimeter"],
    ["Perímetros activos", "activePerimeters"],
    ["Perimetros activos", "activePerimeters"],

    ["Materiales", "materials"],
    ["Órdenes y movimientos", "ordersMovements"],
    ["Ordenes y movimientos", "ordersMovements"],
    ["Solicitudes del periodo", "periodRequests"],
    ["SOLICITUDES MATERIAL", "materialRequests"],
    ["Solicitudes material", "materialRequests"],
    ["Entregadas", "delivered"],
    ["Entregada", "delivered"],
    ["Delivered", "delivered"],
    ["Material entregado", "deliveredMaterial"],
    ["MATERIAL ENTREGADO", "deliveredMaterial"],
    ["Devueltas", "returned"],
    ["Devuelta", "returned"],
    ["Returned", "returned"],
    ["Material devuelto", "returnedMaterial"],
    ["Consignas", "consignments"],
    ["CONSIGNAS", "consignments"],
    ["Pendientes", "pending"],
    ["Pendiente", "pending"],
    ["Aprobadas", "approved"],
    ["Aprobada", "approved"],
    ["Rechazadas", "rejected"],
    ["Rechazada", "rejected"],
    ["Sin solicitudes en el periodo.", "noRequestsPeriod"],

    ["Inventario", "inventory"],
    ["Disponibilidad", "availability"],
    ["Items activos", "activeItems"],
    ["Ítems activos", "activeItems"],
    ["Stock bajo", "lowStock"],
    ["LOW STOCK", "lowStock"],
    ["Stock en cero", "zeroStock"],
    ["STOCK CERO", "zeroStock"],
    ["Unidades en stock", "stockUnits"],

    ["Nómina", "payroll"],
    ["Nomina", "payroll"],
    ["Payroll", "payroll"],
    ["Corte y cálculo", "payrollCut"],
    ["Corte y calculo", "payrollCut"],
    ["Horas ordinarias", "regularHours"],
    ["Regular hours", "regularHours"],
    ["Horas extra", "extraHours"],
    ["Extra hours", "extraHours"],
    ["Nómina bruta", "grossPayroll"],
    ["Nomina bruta", "grossPayroll"],
    ["Nómina estimada", "estimatedPayroll"],
    ["Nomina estimada", "estimatedPayroll"],
    ["Descuentos", "discounts"],
    ["Total neto", "netTotal"],
    ["Total estimado", "estimatedTotal"],

    ["Alertas", "alerts"],
    ["ALERTAS", "alerts"],
    ["Riesgos operativos", "operationalRisks"],
    ["Sin alertas críticas en el periodo.", "noCriticalAlerts"],
    ["Sin alertas criticas en el periodo.", "noCriticalAlerts"],

    ["Reportes", "reports"],
    ["CRM Campo", "crm"],
    ["Bots", "bots"],
    ["General", "general"],
    ["Estado", "status"],
    ["Módulo", "module"],
    ["Modulo", "module"],
    ["Tenant activo", "activeTenant"],

    ["No se pudieron cargar KPIs.", "loadError"],
    ["Workforce", "workforce"]
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
    if (modulesMatch) {
      return raw.replace(clean, `${modulesMatch[1]} ${t("activeModules")}`);
    }

    const liveMatch = clean.match(/^(.+?)\s*\/\s*(operaci[oó]n viva|live operation|opération en direct)$/i);
    if (liveMatch) {
      return raw.replace(clean, `${liveMatch[1]} / ${t("liveOperation")}`);
    }

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
      text.includes("Résumé exécutif") ||
      text.includes("Resumen ejecutivo")
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

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_kpis_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

reports_matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_reports_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if reports_matches:
    last = reports_matches[-1]
    src = last.group(1)
    safe_src = re.sub(r'client_reports_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_kpis_i18n_safe.js?v=020KR1', src)
    html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
else:
    crm_matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client_crm_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE,
    ))
    if crm_matches:
        last = crm_matches[-1]
        src = last.group(1)
        safe_src = re.sub(r'client_crm_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_kpis_i18n_safe.js?v=020KR1', src)
        html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/client-static/client_kpis_i18n_safe.js?v=020KR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020K-R1 safe external KPIs i18n added")
