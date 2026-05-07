from pathlib import Path

path = Path("app/web/client.js")
text = path.read_text(encoding="utf-8-sig")

marker = "/* CLONEXA 020A-3 FULL CLIENT MODULE I18N */"

if marker in text:
    print("OK: 020A-3 ya existe")
    raise SystemExit(0)

append = r'''

/* CLONEXA 020A-3 FULL CLIENT MODULE I18N */
(function clonexaFullClientModuleI18n() {
  "use strict";

  const LANG_KEY = "clonexa_client_language";

  const I18N = {
    es: {
      moduleWorkforce: "MÓDULO WORKFORCE",
      moduleMaterials: "MÓDULO MATERIALES",
      moduleInventory: "MÓDULO INVENTARIO",
      moduleCrm: "MÓDULO CRM CAMPO",
      modulePayroll: "MÓDULO NÓMINA",
      moduleReports: "MÓDULO REPORTES",
      moduleKpis: "MÓDULO KPIS",
      moduleGps: "MÓDULO GPS",
      moduleBots: "MÓDULO BOTS",

      dashboard: "Dashboard",
      inventory: "Inventario",
      fieldCrm: "CRM Campo",
      payroll: "Nómina",
      workforce: "Personal",
      staff: "Personal",
      kpis: "KPIs",
      gps: "GPS",
      bots: "Bots",
      materials: "Materiales",
      reports: "Reportes",

      staffTitle: "Registro de personal operativo",
      staffSubtitle: "{company} administra su personal de forma independiente.",
      staffHeroText: "Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.",
      editableTable: "TABLA EDITABLE",
      addRow: "Agregar fila",
      saveChanges: "Guardar cambios",
      history: "Historial",
      back: "Volver",
      total: "TOTAL",
      activePlural: "ACTIVOS",
      inactivePlural: "INACTIVOS",
      archivedPlural: "ARCHIVADOS",
      searchMatches: "Buscar coincidencias: nombre, rol, teléfono, correo, Telegram, estado...",
      all: "Todos",
      active: "Activos",
      inactive: "Inactivos",
      archived: "Archivados",
      showing: "Mostrando",
      records: "registros",

      name: "NOMBRE",
      role: "ROL",
      phone: "TELÉFONO",
      email: "CORREO",
      telegramId: "TELEGRAM ID",
      hireDate: "FECHA INGRESO",
      regularHour: "HORA ORDINARIA",
      extraHour: "HORA EXTRA",
      discount1: "DESCUENTO 1",
      discount2: "DESCUENTO 2",
      status: "ESTADO",
      actions: "ACCIONES",
      save: "Guardar",
      activate: "Activar",
      deactivate: "Inactivar",
      delete: "Eliminar",
      supervisor: "Supervisor",
      operator: "Operador",
      technician: "Técnico",

      materialsTitle: "Órdenes de materiales",
      materialsHeroText: "Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.",
      operationalCycle: "CICLO OPERATIVO",
      pending: "Pendientes",
      approved: "Aprobadas",
      delivered: "Entregadas",
      consignment: "Consigna",
      returned: "Devueltas",
      order: "ORDEN",
      requester: "SOLICITANTE",
      material: "MATERIAL",
      quantity: "CANTIDAD",
      destination: "DESTINO",
      detail: "Detalle",
      return: "Devolución",
      update: "Actualizar",
      outputManagement: "GESTIÓN DE SALIDA",

      tenantActive: "Tenant activo",
      clientPanel: "Panel cliente",
      settings: "Configuración",
      logout: "Salir",
      csv: "CSV"
    },

    en: {
      moduleWorkforce: "WORKFORCE MODULE",
      moduleMaterials: "MATERIALS MODULE",
      moduleInventory: "INVENTORY MODULE",
      moduleCrm: "FIELD CRM MODULE",
      modulePayroll: "PAYROLL MODULE",
      moduleReports: "REPORTS MODULE",
      moduleKpis: "KPIS MODULE",
      moduleGps: "GPS MODULE",
      moduleBots: "BOTS MODULE",

      dashboard: "Dashboard",
      inventory: "Inventory",
      fieldCrm: "Field CRM",
      payroll: "Payroll",
      workforce: "Staff",
      staff: "Staff",
      kpis: "KPIs",
      gps: "GPS",
      bots: "Bots",
      materials: "Materials",
      reports: "Reports",

      staffTitle: "Operational staff registry",
      staffSubtitle: "{company} manages its staff independently.",
      staffHeroText: "Manage employees, technicians, supervisors and roles connected to bot, payroll and operations.",
      editableTable: "EDITABLE TABLE",
      addRow: "Add row",
      saveChanges: "Save changes",
      history: "History",
      back: "Back",
      total: "TOTAL",
      activePlural: "ACTIVE",
      inactivePlural: "INACTIVE",
      archivedPlural: "ARCHIVED",
      searchMatches: "Search matches: name, role, phone, email, Telegram, status...",
      all: "All",
      active: "Active",
      inactive: "Inactive",
      archived: "Archived",
      showing: "Showing",
      records: "records",

      name: "NAME",
      role: "ROLE",
      phone: "PHONE",
      email: "EMAIL",
      telegramId: "TELEGRAM ID",
      hireDate: "HIRE DATE",
      regularHour: "REGULAR HOUR",
      extraHour: "EXTRA HOUR",
      discount1: "DISCOUNT 1",
      discount2: "DISCOUNT 2",
      status: "STATUS",
      actions: "ACTIONS",
      save: "Save",
      activate: "Activate",
      deactivate: "Deactivate",
      delete: "Delete",
      supervisor: "Supervisor",
      operator: "Operator",
      technician: "Technician",

      materialsTitle: "Material orders",
      materialsHeroText: "Outbound orders connected to Inventory. Delivery deducts stock; return requires an order number.",
      operationalCycle: "OPERATING CYCLE",
      pending: "Pending",
      approved: "Approved",
      delivered: "Delivered",
      consignment: "Consignment",
      returned: "Returned",
      order: "ORDER",
      requester: "REQUESTER",
      material: "MATERIAL",
      quantity: "QUANTITY",
      destination: "DESTINATION",
      detail: "Detail",
      return: "Return",
      update: "Refresh",
      outputManagement: "OUTPUT MANAGEMENT",

      tenantActive: "Active tenant",
      clientPanel: "Client panel",
      settings: "Settings",
      logout: "Log out",
      csv: "CSV"
    },

    fr: {
      moduleWorkforce: "MODULE PERSONNEL",
      moduleMaterials: "MODULE MATÉRIAUX",
      moduleInventory: "MODULE INVENTAIRE",
      moduleCrm: "MODULE CRM TERRAIN",
      modulePayroll: "MODULE PAIE",
      moduleReports: "MODULE RAPPORTS",
      moduleKpis: "MODULE KPIS",
      moduleGps: "MODULE GPS",
      moduleBots: "MODULE BOTS",

      dashboard: "Tableau de bord",
      inventory: "Inventaire",
      fieldCrm: "CRM Terrain",
      payroll: "Paie",
      workforce: "Personnel",
      staff: "Personnel",
      kpis: "KPIs",
      gps: "GPS",
      bots: "Bots",
      materials: "Matériaux",
      reports: "Rapports",

      staffTitle: "Registre du personnel opérationnel",
      staffSubtitle: "{company} gère son personnel de manière indépendante.",
      staffHeroText: "Gérez les employés, techniciens, superviseurs et rôles connectés au bot, à la paie et aux opérations.",
      editableTable: "TABLEAU MODIFIABLE",
      addRow: "Ajouter une ligne",
      saveChanges: "Enregistrer",
      history: "Historique",
      back: "Retour",
      total: "TOTAL",
      activePlural: "ACTIFS",
      inactivePlural: "INACTIFS",
      archivedPlural: "ARCHIVÉS",
      searchMatches: "Rechercher : nom, rôle, téléphone, e-mail, Telegram, statut...",
      all: "Tous",
      active: "Actifs",
      inactive: "Inactifs",
      archived: "Archivés",
      showing: "Affichage",
      records: "enregistrements",

      name: "NOM",
      role: "RÔLE",
      phone: "TÉLÉPHONE",
      email: "E-MAIL",
      telegramId: "TELEGRAM ID",
      hireDate: "DATE D’ENTRÉE",
      regularHour: "HEURE NORMALE",
      extraHour: "HEURE SUPPLÉMENTAIRE",
      discount1: "REMISE 1",
      discount2: "REMISE 2",
      status: "STATUT",
      actions: "ACTIONS",
      save: "Enregistrer",
      activate: "Activer",
      deactivate: "Désactiver",
      delete: "Supprimer",
      supervisor: "Superviseur",
      operator: "Opérateur",
      technician: "Technicien",

      materialsTitle: "Ordres de matériaux",
      materialsHeroText: "Ordres de sortie connectés à l’inventaire. La livraison déduit le stock ; le retour exige un numéro d’ordre.",
      operationalCycle: "CYCLE OPÉRATIONNEL",
      pending: "En attente",
      approved: "Approuvées",
      delivered: "Livrées",
      consignment: "Consigne",
      returned: "Retournées",
      order: "ORDRE",
      requester: "DEMANDEUR",
      material: "MATÉRIEL",
      quantity: "QUANTITÉ",
      destination: "DESTINATION",
      detail: "Détail",
      return: "Retour",
      update: "Actualiser",
      outputManagement: "GESTION DE SORTIE",

      tenantActive: "Tenant actif",
      clientPanel: "Panneau client",
      settings: "Configuration",
      logout: "Quitter",
      csv: "CSV"
    }
  };

  const ALIASES = {
    "MODULO WORKFORCE": "moduleWorkforce",
    "MÓDULO WORKFORCE": "moduleWorkforce",
    "WORKFORCE MODULE": "moduleWorkforce",

    "MODULO MATERIALES": "moduleMaterials",
    "MÓDULO MATERIALES": "moduleMaterials",
    "MATERIALS MODULE": "moduleMaterials",

    "MODULO INVENTARIO": "moduleInventory",
    "MÓDULO INVENTARIO": "moduleInventory",
    "MODULO CRM CAMPO": "moduleCrm",
    "MÓDULO CRM CAMPO": "moduleCrm",
    "MODULO NÓMINA": "modulePayroll",
    "MÓDULO NÓMINA": "modulePayroll",
    "MODULO REPORTES": "moduleReports",
    "MÓDULO REPORTES": "moduleReports",
    "MODULO KPIS": "moduleKpis",
    "MÓDULO KPIS": "moduleKpis",
    "MODULO GPS": "moduleGps",
    "MÓDULO GPS": "moduleGps",
    "MODULO BOTS": "moduleBots",
    "MÓDULO BOTS": "moduleBots",

    "Dashboard": "dashboard",
    "Inventario": "inventory",
    "Inventory": "inventory",
    "CRM Campo": "fieldCrm",
    "Field CRM": "fieldCrm",
    "Nómina": "payroll",
    "Nomina": "payroll",
    "Payroll": "payroll",
    "Personal": "workforce",
    "Workforce": "workforce",
    "Staff": "staff",
    "Materiales": "materials",
    "Materials": "materials",
    "Reportes": "reports",
    "Reports": "reports",

    "Registro de personal operativo": "staffTitle",
    "Operational staff registry": "staffTitle",
    "Gestiona empleados, tecnicos, supervisores y roles conectados a bot, nomina y operacion.": "staffHeroText",
    "Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.": "staffHeroText",

    "TABLA EDITABLE": "editableTable",
    "Agregar fila": "addRow",
    "Agregar personal": "addRow",
    "Guardar cambios": "saveChanges",
    "Historial": "history",
    "Volver": "back",
    "TOTAL": "total",
    "ACTIVOS": "activePlural",
    "INACTIVOS": "inactivePlural",
    "ARCHIVADOS": "archivedPlural",
    "Todos": "all",
    "Activos": "active",
    "Inactivos": "inactive",
    "Archivados": "archived",

    "NOMBRE": "name",
    "ROL": "role",
    "TELEFONO": "phone",
    "TELÉFONO": "phone",
    "CORREO": "email",
    "TELEGRAM ID": "telegramId",
    "FECHA INGRESO": "hireDate",
    "HORA ORDINARIA": "regularHour",
    "HORA EXTRA": "extraHour",
    "DESCUENTO 1": "discount1",
    "DESCUENTO 2": "discount2",
    "ESTADO": "status",
    "ACCIONES": "actions",
    "Guardar": "save",
    "Activar": "activate",
    "Inactivar": "deactivate",
    "Eliminar": "delete",
    "Activo": "active",
    "Inactivo": "inactive",
    "Archivado": "archived",
    "Supervisor": "supervisor",

    "Órdenes de materiales": "materialsTitle",
    "Ordenes de materiales": "materialsTitle",
    "Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.": "materialsHeroText",
    "Ordenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige numero de orden.": "materialsHeroText",
    "CICLO OPERATIVO": "operationalCycle",
    "Pendientes": "pending",
    "Aprobadas": "approved",
    "Entregadas": "delivered",
    "Consigna": "consignment",
    "Devueltas": "returned",
    "ORDEN": "order",
    "SOLICITANTE": "requester",
    "MATERIAL": "material",
    "CANTIDAD": "quantity",
    "STATUS": "status",
    "DESTINO": "destination",
    "Detalle": "detail",
    "Devolución": "return",
    "Devolucion": "return",
    "Actualizar": "update",
    "GESTIÓN DE SALIDA": "outputManagement",
    "GESTION DE SALIDA": "outputManagement",

    "Tenant activo": "tenantActive",
    "Configuración": "settings",
    "Settings": "settings",
    "Salir": "logout",
    "Log out": "logout"
  };

  Object.keys(I18N).forEach((lang) => {
    Object.keys(I18N[lang]).forEach((key) => {
      ALIASES[I18N[lang][key]] = key;
    });
  });

  function lang() {
    const raw = String(localStorage.getItem(LANG_KEY) || document.documentElement.lang || "es").toLowerCase();
    return ["es", "en", "fr"].includes(raw) ? raw : "es";
  }

  function tr(key) {
    return (I18N[lang()] && I18N[lang()][key]) || I18N.es[key] || key;
  }

  function normalizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function translateExact(value) {
    const original = String(value || "");
    const clean = normalizeText(original);

    if (!clean) return original;
    if (/^[\d\s.,:$%#@/_-]+$/.test(clean)) return original;
    if (clean.includes("@")) return original;
    if (/^[A-Z]{2,}-\d{4}/.test(clean)) return original;

    const key = ALIASES[clean];
    if (!key) {
      const showingMatch = clean.match(/^Mostrando\s+(.+?)\s+de\s+(.+?)\s+registros\.?$/i);
      if (showingMatch) {
        if (lang() === "en") return `Showing ${showingMatch[1]} of ${showingMatch[2]} records.`;
        if (lang() === "fr") return `Affichage ${showingMatch[1]} sur ${showingMatch[2]} enregistrements.`;
        return `Mostrando ${showingMatch[1]} de ${showingMatch[2]} registros.`;
      }

      const companySubtitle = clean.match(/^(.+?) administra su personal de forma independiente\.?$/i);
      if (companySubtitle) {
        return tr("staffSubtitle").replace("{company}", companySubtitle[1]);
      }

      return original;
    }

    return original.replace(clean, tr(key));
  }

  function skip(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (["script", "style", "code", "pre", "textarea"].includes(tag)) return true;
    if (el.closest && el.closest("[data-clx-no-i18n]")) return true;
    return false;
  }

  function translateElement(root) {
    const base = root || document.body;
    if (!base) return;

    if (base.nodeType === Node.TEXT_NODE) {
      const next = translateExact(base.nodeValue);
      if (next !== base.nodeValue) base.nodeValue = next;
      return;
    }

    if (base.nodeType !== Node.ELEMENT_NODE && base.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
    if (base.nodeType === Node.ELEMENT_NODE && skip(base)) return;

    const walker = document.createTreeWalker(
      base,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || skip(parent)) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach((node) => {
      const next = translateExact(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
    });

    if (base.querySelectorAll) {
      base.querySelectorAll("[placeholder], [title], [aria-label], input[type='button'], input[type='submit']").forEach((el) => {
        if (skip(el)) return;

        ["placeholder", "title", "aria-label"].forEach((attr) => {
          if (el.hasAttribute(attr)) {
            const current = el.getAttribute(attr);
            const next = translateExact(current);
            if (next !== current) el.setAttribute(attr, next);
          }
        });

        if (el.matches("input[type='button'], input[type='submit']")) {
          const next = translateExact(el.value);
          if (next !== el.value) el.value = next;
        }
      });
    }

    document.documentElement.lang = lang();
  }

  function fixAccountButtons() {
    const settings = document.getElementById("clxAccountSettingsBtn");
    const logout = document.getElementById("clxAccountLogoutBtn");

    if (settings) settings.textContent = `⚙ ${tr("settings")}`;
    if (logout) logout.textContent = `⏻ ${tr("logout")}`;
  }

  let timer = null;

  function run() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      translateElement(document.body);
      fixAccountButtons();
    }, 80);
  }

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (target && target.id === "clxAccountLanguage") {
      const selected = String(target.value || "es").toLowerCase();
      if (["es", "en", "fr"].includes(selected)) {
        localStorage.setItem(LANG_KEY, selected);
        document.documentElement.lang = selected;
        run();
      }
    }
  }, true);

  const observer = new MutationObserver(run);

  function init() {
    translateElement(document.body);
    fixAccountButtons();

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label", "value"]
    });

    run();
  }

  window.CLX_FULL_I18N = {
    run,
    translateElement,
    tr,
    lang
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
'''

text += append
path.write_text(text, encoding="utf-8")
print("PATCH_OK: 020A-3 full client module i18n appended")
