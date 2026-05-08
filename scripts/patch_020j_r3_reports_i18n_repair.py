from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_reports_i18n_safe.js")

js = r'''
(function clonexaSafeReportsI18n020JR3() {
  "use strict";

  if (window.__CLONEXA_020J_R3_REPORTS_I18N__) return;
  window.__CLONEXA_020J_R3_REPORTS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const ENTRIES = {
    settings: { es:"Ajustes", en:"Settings", fr:"Configuration", aliases:["Ajustes","Settings","Configuration"] },
    logout: { es:"Cerrar sesión", en:"Log out", fr:"Quitter", aliases:["Cerrar sesión","Cerrar sesion","Log out","Quitter"] },

    moduleEyebrow: { es:"Módulo Reportes", en:"Reports module", fr:"Module rapports", aliases:["MÓDULO REPORTES","MODULO REPORTES","Módulo Reportes","Modulo Reportes","REPORTS MODULE","Reports module"] },
    moduleTitle: { es:"Reportes", en:"Reports", fr:"Rapports", aliases:["Reportes","Reports","Rapports"] },
    generalReport: { es:"Reporte general", en:"General report", fr:"Rapport général", aliases:["Reporte general","General report","Rapport général"] },
    moduleSubtitle: {
      es:"Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta.",
      en:"Consolidated history of Staff, GPS, Materials, Inventory and Payroll. It does not modify data; it only audits and exports.",
      fr:"Historique consolidé du Personnel, GPS, Matériaux, Inventaire et Paie. Ne modifie pas les données; il audite et exporte uniquement.",
      aliases:[
        "Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta.",
        "Historico consolidado de Personal, GPS, Materiales, Inventario y Nomina. No modifica datos; solo audita y exporta.",
        "Consolidated history of Staff, GPS, Materials, Inventory and Payroll. It does not modify data; it only audits and exports."
      ]
    },

    type:{ es:"Tipo", en:"Type", fr:"Type", aliases:["TIPO","Tipo","Type"] },
    from:{ es:"Desde", en:"From", fr:"De", aliases:["FROM","From","DESDE","Desde"] },
    to:{ es:"Hasta", en:"To", fr:"À", aliases:["TO","To","HASTA","Hasta"] },
    period:{ es:"Periodo", en:"Period", fr:"Période", aliases:["PERIOD","Period","PERIODO","PERÍODO","Periodo"] },
    employee:{ es:"Empleado", en:"Employee", fr:"Employé", aliases:["EMPLEADO","Empleado","EMPLOYEE","Employee"] },
    smartSearch:{ es:"Lupa inteligente", en:"Smart search", fr:"Recherche intelligente", aliases:["LUPA INTELIGENTE","Lupa inteligente","SMART SEARCH","Smart search"] },
    module:{ es:"Módulo", en:"Module", fr:"Module", aliases:["MODULE","Module","MÓDULO","MODULO","Módulo","Modulo"] },
    status:{ es:"Estado", en:"Status", fr:"Statut", aliases:["STATUS","Status","ESTADO","Estado"] },

    generate:{ es:"Generar", en:"Generate", fr:"Générer", aliases:["Generar","Generate","Générer"] },
    csv:{ es:"CSV", en:"CSV", fr:"CSV", aliases:["CSV"] },
    back:{ es:"Volver", en:"Back", fr:"Retour", aliases:["Volver","Back","Retour"] },
    dashboard:{ es:"Dashboard", en:"Dashboard", fr:"Tableau de bord", aliases:["Dashboard"] },
    kpis:{ es:"KPIs", en:"KPIs", fr:"KPIs", aliases:["KPIs"] },

    general:{ es:"General", en:"General", fr:"Général", aliases:["General"] },
    all:{ es:"Todos", en:"All", fr:"Tous", aliases:["Todos","All","Tous"] },
    sevenDays:{ es:"7 días", en:"7 days", fr:"7 jours", aliases:["7 días","7 dias","7 days","7 jours"] },
    fifteenDays:{ es:"15 días", en:"15 days", fr:"15 jours", aliases:["15 días","15 dias","15 days","15 jours"] },
    month:{ es:"Mes", en:"Month", fr:"Mois", aliases:["Mes","Month","Mois"] },
    custom:{ es:"Personalizado", en:"Custom", fr:"Personnalisé", aliases:["Personalizado","Custom","Personnalisé"] },

    searchPlaceholder:{
      es:"Buscar empleado, MAT, GPS, stock, nómina...",
      en:"Search employee, MAT, GPS, stock, payroll...",
      fr:"Rechercher employé, MAT, GPS, stock, paie...",
      aliases:["Buscar empleado, MAT, GPS, stock, nómina...","Buscar empleado, MAT, GPS, stock, nomina...","Search employee, MAT, GPS, stock, payroll..."]
    },

    reportHelp:{
      es:"Reporte general consolida toda la empresa. Por persona filtra al colaborador seleccionado.",
      en:"The general report consolidates the entire company. Person view filters by the selected collaborator.",
      fr:"Le rapport général consolide toute l’entreprise. La vue par personne filtre le collaborateur sélectionné.",
      aliases:[
        "Reporte general consolida toda la empresa. Por persona filtra al colaborador seleccionado.",
        "The general report consolidates the entire company. Person view filters by the selected collaborator."
      ]
    },

    executiveSummary:{ es:"Resumen ejecutivo", en:"Executive summary", fr:"Résumé exécutif", aliases:["RESUMEN EJECUTIVO","Resumen ejecutivo","EXECUTIVE SUMMARY","Executive summary"] },
    periodIndicators:{ es:"Indicadores del periodo", en:"Period indicators", fr:"Indicateurs de la période", aliases:["Indicadores del periodo","INDICADORES DEL PERIODO","Period indicators"] },

    activeStaff:{ es:"Personal activo", en:"Active staff", fr:"Personnel actif", aliases:["PERSONAL ACTIVO","Personal activo","ACTIVE STAFF","Active staff"] },
    shiftsStarted:{ es:"Turnos iniciados", en:"Shifts started", fr:"Services démarrés", aliases:["TURNOS INICIADOS","Turnos iniciados","SHIFTS STARTED","Shifts started"] },
    regularHours:{ es:"Horas ordinarias", en:"Regular hours", fr:"Heures normales", aliases:["REGULAR HOURS","Regular hours","HORAS ORDINARIAS","Horas ordinarias"] },
    totalPayroll:{ es:"Total nómina", en:"Total payroll", fr:"Paie totale", aliases:["TOTAL NÓMINA","TOTAL NOMINA","Total nómina","Total nomina","TOTAL PAYROLL","Total payroll"] },
    gpsOutside:{ es:"GPS fuera", en:"GPS outside", fr:"GPS hors périmètre", aliases:["GPS OUTSIDE","GPS outside","GPS FUERA","GPS fuera"] },
    materialOrders:{ es:"Órdenes material", en:"Material orders", fr:"Commandes matériel", aliases:["ÓRDENES MATERIAL","ORDENES MATERIAL","Órdenes material","Ordenes material","MATERIAL ORDERS","Material orders"] },
    consignments:{ es:"Consignas", en:"Consignments", fr:"Consignes", aliases:["CONSIGNAS","Consignas","CONSIGNMENTS","Consignments"] },
    lowStock:{ es:"Stock bajo", en:"Low stock", fr:"Stock faible", aliases:["LOW STOCK","Low stock","STOCK BAJO","Stock bajo"] },
    zeroStock:{ es:"Stock cero", en:"Zero stock", fr:"Stock zéro", aliases:["ZERO STOCK","Zero stock","STOCK CERO","Stock cero"] },
    alerts:{ es:"Alertas", en:"Alerts", fr:"Alertes", aliases:["ALERTAS","Alertas","ALERTS","Alerts"] },

    workforce:{ es:"Workforce", en:"Workforce", fr:"Workforce", aliases:["Workforce"] },
    payroll:{ es:"Nómina", en:"Payroll", fr:"Paie", aliases:["Nómina","Nomina","Payroll","PAYROLL"] },
    materials:{ es:"Materiales", en:"Materials", fr:"Matériaux", aliases:["Materiales","Materials","MATERIALS"] },
    inventory:{ es:"Inventario", en:"Inventory", fr:"Inventaire", aliases:["Inventario","Inventory","INVENTORY"] },
    gps:{ es:"GPS", en:"GPS", fr:"GPS", aliases:["GPS"] },

    activityByDay:{ es:"Actividad por día", en:"Activity by day", fr:"Activité par jour", aliases:["Actividad por día","Actividad por dia","Activity by day"] },
    materialsByStatus:{ es:"Materiales por estado", en:"Materials by status", fr:"Matériaux par statut", aliases:["Materiales por estado","Materials by status"] },

    delivered:{ es:"Entregado", en:"Delivered", fr:"Livré", aliases:["Delivered","delivered","Entregado"] },
    returnedPartial:{ es:"Devuelto parcial", en:"Partially returned", fr:"Retour partiel", aliases:["returned_partial","Returned partial","Partially returned","Devuelto parcial"] },
    returned:{ es:"Devuelto", en:"Returned", fr:"Retourné", aliases:["returned","Returned","Devuelto"] },
    pending:{ es:"Pendiente", en:"Pending", fr:"En attente", aliases:["pending","Pending","Pendiente"] },
    approved:{ es:"Aprobado", en:"Approved", fr:"Approuvé", aliases:["approved","Approved","Aprobado"] },
    rejected:{ es:"Rechazado", en:"Rejected", fr:"Rejeté", aliases:["rejected","Rejected","Rechazado"] },
    consigned:{ es:"Consignado", en:"Consigned", fr:"Consigné", aliases:["consigned","Consigned","Consignado"] },

    noData:{ es:"Sin datos para los filtros seleccionados.", en:"No data for the selected filters.", fr:"Aucune donnée pour les filtres sélectionnés.", aliases:["Sin datos para los filtros seleccionados.","No data for the selected filters."] },
    loadError:{ es:"No se pudo cargar Reportes.", en:"Could not load Reports.", fr:"Impossible de charger les rapports.", aliases:["No se pudo cargar Reportes.","Could not load Reports."] }
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
      text.includes("Módulo Reportes") ||
      text.includes("Modulo Reportes") ||
      text.includes("Reports module") ||
      text.includes("Reporte general") ||
      text.includes("General report") ||
      text.includes("Indicadores del periodo") ||
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
    timer = setTimeout(translateReports, 100);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateReports();
      if (count >= 18) clearInterval(id);
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

  setInterval(() => {
    if (isReportsVisible()) translateReports();
  }, 1500);

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

html = html_path.read_text(encoding="utf-8-sig")

# Quitar cualquier tag viejo de Reports
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_reports_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

# Insertar Reports antes de KPIs si existe KPIs; si no después de CRM
kpis_match = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_kpis_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE
))

if kpis_match:
    first = kpis_match[0]
    src = first.group(1)
    reports_src = re.sub(r'client_kpis_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_reports_i18n_safe.js?v=020JR3', src)
    html = html[:first.start()] + f'<script src="{reports_src}"></script>\n' + html[first.start():]
else:
    crm_match = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client_crm_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE
    ))
    if crm_match:
      last = crm_match[-1]
      src = last.group(1)
      reports_src = re.sub(r'client_crm_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_reports_i18n_safe.js?v=020JR3', src)
      html = html[:last.end()] + f'\n<script src="{reports_src}"></script>\n' + html[last.end():]
    else:
      html = html.replace("</body>", '<script src="/client-static/client_reports_i18n_safe.js?v=020JR3"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020J-R3 Reports i18n repaired and reinserted")
