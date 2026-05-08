from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_crm_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaSafeCrmI18n020IR1() {
  "use strict";

  if (window.__CLONEXA_020I_R1_CRM_I18N__) return;
  window.__CLONEXA_020I_R1_CRM_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const DICT = {
    es: {
      settings: "Ajustes",
      logout: "Cerrar sesión",

      moduleEyebrow: "Módulo CRM Campo",
      moduleTitle: "CRM Campo",
      moduleSubtitle: "Vista viva de colaboradores en turno, pausas y núcleos activos de la empresa.",

      back: "Volver",
      refresh: "Actualizar",

      currentStatus: "Estado operativo actual",
      liveOperation: "Operación en vivo",
      active: "Activos",
      onBreak: "En pausa",

      collaborators: "Colaboradores",
      collaboratorStatus: "Estado por colaborador",
      collaborator: "Colaborador",
      chronometer: "Cronómetro",

      statusActive: "Activo",
      statusOnBreak: "En pausa",
      statusCheckedOut: "Fuera de turno",
      statusNotStarted: "Sin turno",
      statusInactive: "Inactivo",
      statusArchived: "Archivado",

      noCollaborators: "No hay colaboradores operativos para mostrar.",

      gps: "GPS",
      field: "Campo",
      materials: "Materiales",
      production: "Producción",
      sales: "Ventas",
      stores: "Tiendas",
      retail: "Retail",
      inventory: "Inventario",
      stock: "Stock",
      orders: "Pedidos",
      requests: "Solicitudes",
      payroll: "Nómina",
      kpis: "KPIs",
      reports: "Reportes",
      modules: "Módulos",
      channels: "Canales",

      noLocation: "Sin ubicación",
      noTask: "Sin tarea",
      noRequest: "Sin solicitud",
      noProduction: "Sin producción",
      noSale: "Sin venta",
      noStore: "Sin punto",
      noActivity: "Sin actividad",
      noMovement: "Sin movimiento",
      noAlert: "Sin alerta",
      noOrder: "Sin pedido",
      noCutoff: "Sin corte",
      noMetric: "Sin métrica",
      assigned: "Asignados",

      shiftStart: "Inicio turno",
      pause: "Pausa",
      resume: "Retomar",
      shiftEnd: "Fin turno",
      materialRequest: "Solicitud material",
      observation: "Observación",
      location: "Ubicación",
      taskStarted: "Tarea iniciada",
      taskCompleted: "Tarea cerrada",
      saleCreated: "Venta",

      insidePerimeter: "Dentro de perímetro",
      outsidePerimeter: "Fuera de perímetro",
      noValidation: "Sin validación"
    },

    en: {
      settings: "Settings",
      logout: "Log out",

      moduleEyebrow: "Field CRM module",
      moduleTitle: "Field CRM",
      moduleSubtitle: "Live view of collaborators on shift, breaks and active company cores.",

      back: "Back",
      refresh: "Refresh",

      currentStatus: "Current operating status",
      liveOperation: "Live operation",
      active: "Active",
      onBreak: "On break",

      collaborators: "Collaborators",
      collaboratorStatus: "Status by collaborator",
      collaborator: "Collaborator",
      chronometer: "Timer",

      statusActive: "Active",
      statusOnBreak: "On break",
      statusCheckedOut: "Off shift",
      statusNotStarted: "No shift",
      statusInactive: "Inactive",
      statusArchived: "Archived",

      noCollaborators: "No operational collaborators to display.",

      gps: "GPS",
      field: "Field",
      materials: "Materials",
      production: "Production",
      sales: "Sales",
      stores: "Stores",
      retail: "Retail",
      inventory: "Inventory",
      stock: "Stock",
      orders: "Orders",
      requests: "Requests",
      payroll: "Payroll",
      kpis: "KPIs",
      reports: "Reports",
      modules: "Modules",
      channels: "Channels",

      noLocation: "No location",
      noTask: "No task",
      noRequest: "No request",
      noProduction: "No production",
      noSale: "No sale",
      noStore: "No store",
      noActivity: "No activity",
      noMovement: "No movement",
      noAlert: "No alert",
      noOrder: "No order",
      noCutoff: "No cutoff",
      noMetric: "No metric",
      assigned: "Assigned",

      shiftStart: "Shift start",
      pause: "Break",
      resume: "Resume",
      shiftEnd: "Shift end",
      materialRequest: "Material request",
      observation: "Observation",
      location: "Location",
      taskStarted: "Task started",
      taskCompleted: "Task completed",
      saleCreated: "Sale",

      insidePerimeter: "Inside perimeter",
      outsidePerimeter: "Outside perimeter",
      noValidation: "No validation"
    },

    fr: {
      settings: "Configuration",
      logout: "Quitter",

      moduleEyebrow: "Module CRM terrain",
      moduleTitle: "CRM terrain",
      moduleSubtitle: "Vue en direct des collaborateurs en service, pauses et noyaux actifs de l’entreprise.",

      back: "Retour",
      refresh: "Actualiser",

      currentStatus: "État opérationnel actuel",
      liveOperation: "Opération en direct",
      active: "Actifs",
      onBreak: "En pause",

      collaborators: "Collaborateurs",
      collaboratorStatus: "État par collaborateur",
      collaborator: "Collaborateur",
      chronometer: "Chronomètre",

      statusActive: "Actif",
      statusOnBreak: "En pause",
      statusCheckedOut: "Hors service",
      statusNotStarted: "Sans service",
      statusInactive: "Inactif",
      statusArchived: "Archivé",

      noCollaborators: "Aucun collaborateur opérationnel à afficher.",

      gps: "GPS",
      field: "Terrain",
      materials: "Matériaux",
      production: "Production",
      sales: "Ventes",
      stores: "Magasins",
      retail: "Retail",
      inventory: "Inventaire",
      stock: "Stock",
      orders: "Commandes",
      requests: "Demandes",
      payroll: "Paie",
      kpis: "KPIs",
      reports: "Rapports",
      modules: "Modules",
      channels: "Canaux",

      noLocation: "Sans position",
      noTask: "Sans tâche",
      noRequest: "Sans demande",
      noProduction: "Sans production",
      noSale: "Sans vente",
      noStore: "Sans point",
      noActivity: "Sans activité",
      noMovement: "Sans mouvement",
      noAlert: "Sans alerte",
      noOrder: "Sans commande",
      noCutoff: "Sans clôture",
      noMetric: "Sans métrique",
      assigned: "Assignés",

      shiftStart: "Début de service",
      pause: "Pause",
      resume: "Reprendre",
      shiftEnd: "Fin de service",
      materialRequest: "Demande de matériel",
      observation: "Observation",
      location: "Position",
      taskStarted: "Tâche démarrée",
      taskCompleted: "Tâche terminée",
      saleCreated: "Vente",

      insidePerimeter: "Dans le périmètre",
      outsidePerimeter: "Hors périmètre",
      noValidation: "Sans validation"
    }
  };

  const ALIASES = {};

  Object.keys(DICT).forEach((language) => {
    Object.keys(DICT[language]).forEach((key) => {
      ALIASES[norm(DICT[language][key])] = key;
    });
  });

  [
    ["Modulo CRM Campo", "moduleEyebrow"],
    ["Módulo CRM Campo", "moduleEyebrow"],
    ["CRM Campo", "moduleTitle"],
    ["Vista viva de colaboradores en turno, pausas y nucleos activos de la empresa.", "moduleSubtitle"],
    ["Vista viva de colaboradores en turno, pausas y núcleos activos de la empresa.", "moduleSubtitle"],

    ["Volver", "back"],
    ["Actualizar", "refresh"],

    ["Estado operativo actual", "currentStatus"],
    ["Operacion en vivo", "liveOperation"],
    ["Operación en vivo", "liveOperation"],
    ["Activos", "active"],
    ["En pausa", "onBreak"],

    ["Colaboradores", "collaborators"],
    ["Estado por colaborador", "collaboratorStatus"],
    ["Colaborador", "collaborator"],
    ["Cronometro", "chronometer"],
    ["Cronómetro", "chronometer"],

    ["Activo", "statusActive"],
    ["Fuera de turno", "statusCheckedOut"],
    ["Sin turno", "statusNotStarted"],
    ["Inactivo", "statusInactive"],
    ["Archivado", "statusArchived"],

    ["No hay colaboradores operativos para mostrar.", "noCollaborators"],

    ["GPS", "gps"],
    ["Campo", "field"],
    ["Materiales", "materials"],
    ["Produccion", "production"],
    ["Producción", "production"],
    ["Ventas", "sales"],
    ["Tiendas", "stores"],
    ["Retail", "retail"],
    ["Inventario", "inventory"],
    ["Stock", "stock"],
    ["Pedidos", "orders"],
    ["Solicitudes", "requests"],
    ["Nomina", "payroll"],
    ["Nómina", "payroll"],
    ["KPIs", "kpis"],
    ["Reportes", "reports"],
    ["Modulos", "modules"],
    ["Módulos", "modules"],
    ["Canales", "channels"],

    ["Sin ubicacion", "noLocation"],
    ["Sin ubicación", "noLocation"],
    ["Sin tarea", "noTask"],
    ["Sin solicitud", "noRequest"],
    ["Sin produccion", "noProduction"],
    ["Sin producción", "noProduction"],
    ["Sin venta", "noSale"],
    ["Sin punto", "noStore"],
    ["Sin actividad", "noActivity"],
    ["Sin movimiento", "noMovement"],
    ["Sin alerta", "noAlert"],
    ["Sin pedido", "noOrder"],
    ["Sin corte", "noCutoff"],
    ["Sin metrica", "noMetric"],
    ["Sin métrica", "noMetric"],
    ["Asignados", "assigned"],

    ["Inicio turno", "shiftStart"],
    ["Pausa", "pause"],
    ["Retomar", "resume"],
    ["Fin turno", "shiftEnd"],
    ["Solicitud material", "materialRequest"],
    ["Observacion", "observation"],
    ["Observación", "observation"],
    ["Ubicacion", "location"],
    ["Ubicación", "location"],
    ["Tarea iniciada", "taskStarted"],
    ["Tarea cerrada", "taskCompleted"],
    ["Venta", "saleCreated"],

    ["Dentro de perímetro", "insidePerimeter"],
    ["Dentro de perimetro", "insidePerimeter"],
    ["Fuera de perímetro", "outsidePerimeter"],
    ["Fuera de perimetro", "outsidePerimeter"],
    ["Sin validación", "noValidation"],
    ["Sin validacion", "noValidation"],

    ["Ajustes", "settings"],
    ["Cerrar sesión", "logout"],
    ["Cerrar sesion", "logout"]
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
    if (/^\d{1,2}:\d{2}/.test(raw)) return true;
    return false;
  }

  function translateText(value) {
    const raw = String(value || "");
    const clean = raw.replace(/\s+/g, " ").trim();

    if (shouldSkipText(clean)) return raw;

    const activeModules = clean.match(/^(\d+)\s+(activos|active|actifs)$/i);
    if (activeModules) {
      if (lang() === "en") return raw.replace(clean, `${activeModules[1]} active`);
      if (lang() === "fr") return raw.replace(clean, `${activeModules[1]} actifs`);
      return raw;
    }

    const key = ALIASES[norm(clean)];
    if (!key) return raw;

    return raw.replace(clean, t(key));
  }

  function isCrmVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    const text = app.textContent || "";

    return (
      text.includes("Modulo CRM Campo") ||
      text.includes("Módulo CRM Campo") ||
      text.includes("Field CRM module") ||
      text.includes("Module CRM terrain") ||
      text.includes("Operacion en vivo") ||
      text.includes("Operación en vivo") ||
      text.includes("Live operation") ||
      text.includes("Opération en direct") ||
      text.includes("Estado por colaborador") ||
      text.includes("Status by collaborator") ||
      text.includes("État par collaborateur")
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

  function translateCrm() {
    try {
      if (!isCrmVisible()) return;

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
      console.warn("CLONEXA CRM i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateCrm, 140);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateCrm();
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
      console.warn("CLONEXA CRM i18n init skipped:", error);
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
    r'\s*<script[^>]+src=["\'][^"\']*client_crm_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

bots_matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_bots_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if bots_matches:
    last = bots_matches[-1]
    src = last.group(1)
    safe_src = re.sub(r'client_bots_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_crm_i18n_safe.js?v=020IR1', src)
    html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
else:
    gps_matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client_gps_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE,
    ))
    if gps_matches:
        last = gps_matches[-1]
        src = last.group(1)
        safe_src = re.sub(r'client_gps_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_crm_i18n_safe.js?v=020IR1', src)
        html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/client-static/client_crm_i18n_safe.js?v=020IR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020I-R1 safe external CRM i18n added")
