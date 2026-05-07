from pathlib import Path

path = Path("app/web/client.js")
text = path.read_text(encoding="utf-8-sig")

marker = "/* CLONEXA 020A-4 FULL CLIENT RUNTIME I18N ENGINE */"

if marker in text:
    print("OK: 020A-4 ya existe")
    raise SystemExit(0)

engine = r'''
/* CLONEXA 020A-4 FULL CLIENT RUNTIME I18N ENGINE */
(function clonexaFullClientRuntimeI18nEngine() {
  "use strict";

  const LANG_KEY = "clonexa_client_language";

  const T = {
    systemOperatingBusiness: {
      es: "SISTEMA OPERATIVO EMPRESARIAL",
      en: "BUSINESS OPERATING SYSTEM",
      fr: "SYSTÈME OPÉRATIONNEL D’ENTREPRISE",
      a: ["SISTEMA OPERATIVO EMPRESARIAL"]
    },
    panelConnected: {
      es: "Panel operativo independiente conectado a sus módulos activos.",
      en: "Independent operations panel connected to its active modules.",
      fr: "Panneau opérationnel indépendant connecté à ses modules actifs.",
      a: [
        "Panel operativo independiente conectado a sus módulos activos.",
        "Panel operativo independiente conectado a sus m?dulos activos.",
        "Panel operativo independiente conectado a sus mÃ³dulos activos."
      ]
    },
    panelModules: {
      es: "MÓDULOS DEL PANEL",
      en: "PANEL MODULES",
      fr: "MODULES DU PANNEAU",
      a: ["MÓDULOS DEL PANEL", "MODULOS DEL PANEL", "M?DULOS DEL PANEL", "MÃ³DULOS DEL PANEL"]
    },
    activeServices: {
      es: "Servicios activos",
      en: "Active services",
      fr: "Services actifs",
      a: ["Servicios activos"]
    },
    activeTenant: {
      es: "Tenant activo",
      en: "Active tenant",
      fr: "Tenant actif",
      a: ["Tenant activo", "Active tenant"]
    },
    activeNow: {
      es: "Activos ahora",
      en: "Active now",
      fr: "Actifs maintenant",
      a: ["Activos ahora"]
    },
    gpsInside: {
      es: "GPS dentro",
      en: "GPS inside",
      fr: "GPS à l’intérieur",
      a: ["GPS dentro"]
    },
    materialDelivered: {
      es: "Material entregado",
      en: "Delivered material",
      fr: "Matériel livré",
      a: ["Material entregado"]
    },
    lowStock: {
      es: "Stock bajo",
      en: "Low stock",
      fr: "Stock faible",
      a: ["Stock bajo"]
    },
    activeModules: {
      es: "módulos activos",
      en: "active modules",
      fr: "modules actifs",
      a: ["módulos activos", "modulos activos", "m?dulos activos", "mÃ³dulos activos"]
    },

    dashboard: { es: "Dashboard", en: "Dashboard", fr: "Tableau de bord", a: ["Dashboard"] },
    inventory: { es: "Inventario", en: "Inventory", fr: "Inventaire", a: ["Inventario", "Inventory"] },
    fieldCrm: { es: "CRM Campo", en: "Field CRM", fr: "CRM Terrain", a: ["CRM Campo", "Field CRM"] },
    payroll: { es: "Nómina", en: "Payroll", fr: "Paie", a: ["Nómina", "Nomina", "Payroll"] },
    workforce: { es: "Personal", en: "Staff", fr: "Personnel", a: ["Personal", "Workforce", "Staff"] },
    kpis: { es: "KPIs", en: "KPIs", fr: "KPIs", a: ["KPIs"] },
    gps: { es: "GPS", en: "GPS", fr: "GPS", a: ["GPS"] },
    bots: { es: "Bots", en: "Bots", fr: "Bots", a: ["Bots"] },
    materials: { es: "Materiales", en: "Materials", fr: "Matériaux", a: ["Materiales", "Materials"] },
    reports: { es: "Reportes", en: "Reports", fr: "Rapports", a: ["Reportes", "Reports"] },

    stockMaterials: { es: "STOCK Y MATERIALES", en: "STOCK AND MATERIALS", fr: "STOCK ET MATÉRIAUX", a: ["STOCK Y MATERIALES"] },
    liveOperation: { es: "OPERACIÓN EN VIVO", en: "LIVE OPERATION", fr: "OPÉRATION EN DIRECT", a: ["OPERACION EN VIVO", "OPERACIÓN EN VIVO"] },
    payrollCalc: { es: "CORTE Y CÁLCULO", en: "CUTOFF AND CALCULATION", fr: "CLÔTURE ET CALCUL", a: ["CORTE Y CALCULO", "CORTE Y CÁLCULO"] },
    operationalStaff: { es: "PERSONAL OPERATIVO", en: "OPERATIONAL STAFF", fr: "PERSONNEL OPÉRATIONNEL", a: ["PERSONAL OPERATIVO", "OPERATIONAL STAFF"] },
    operationalIndicators: { es: "INDICADORES OPERATIVOS", en: "OPERATIONAL INDICATORS", fr: "INDICATEURS OPÉRATIONNELS", a: ["INDICADORES OPERATIVOS", "OPERATIONAL INDICATORS"] },
    locationRoutes: { es: "UBICACIÓN Y RUTAS", en: "LOCATION AND ROUTES", fr: "LOCALISATION ET ITINÉRAIRES", a: ["UBICACION Y RUTAS", "UBICACIÓN Y RUTAS"] },
    requestReturn: { es: "SOLICITUD Y DEVOLUCIÓN", en: "REQUEST AND RETURN", fr: "DEMANDE ET RETOUR", a: ["SOLICITUD Y DEVOLUCION", "SOLICITUD Y DEVOLUCIÓN"] },
    metricsAudit: { es: "MÉTRICAS Y AUDITORÍA", en: "METRICS AND AUDIT", fr: "MÉTRIQUES ET AUDIT", a: ["METRICAS Y AUDITORIA", "MÉTRICAS Y AUDITORÍA"] },

    moduleInventory: { es: "MÓDULO INVENTARIO", en: "INVENTORY MODULE", fr: "MODULE INVENTAIRE", a: ["MODULO INVENTARIO", "MÓDULO INVENTARIO"] },
    moduleMaterials: { es: "MÓDULO MATERIALES", en: "MATERIALS MODULE", fr: "MODULE MATÉRIAUX", a: ["MODULO MATERIALES", "MÓDULO MATERIALES"] },
    moduleCrm: { es: "MÓDULO CRM CAMPO", en: "FIELD CRM MODULE", fr: "MODULE CRM TERRAIN", a: ["MODULO CRM CAMPO", "MÓDULO CRM CAMPO"] },
    moduleWorkforce: { es: "MÓDULO WORKFORCE", en: "WORKFORCE MODULE", fr: "MODULE PERSONNEL", a: ["MODULO WORKFORCE", "MÓDULO WORKFORCE"] },
    modulePayroll: { es: "MÓDULO NÓMINA", en: "PAYROLL MODULE", fr: "MODULE PAIE", a: ["MODULO NOMINA", "MÓDULO NÓMINA", "MÃ³dulo NÃ³mina"] },
    moduleReports: { es: "MÓDULO REPORTES", en: "REPORTS MODULE", fr: "MODULE RAPPORTS", a: ["MODULO REPORTES", "MÓDULO REPORTES", "MÃ³dulo Reportes"] },
    moduleKpis: { es: "MÓDULO KPIS", en: "KPIS MODULE", fr: "MODULE KPIS", a: ["MODULO KPIS", "MÓDULO KPIS"] },
    moduleGps: { es: "MÓDULO GPS", en: "GPS MODULE", fr: "MODULE GPS", a: ["MODULO GPS", "MÓDULO GPS"] },
    moduleBots: { es: "MÓDULO BOTS", en: "BOTS MODULE", fr: "MODULE BOTS", a: ["MODULO BOTS", "MÓDULO BOTS"] },

    inventoryHero: {
      es: "Catálogo operativo, mínimos y stock actual de solo lectura. Materiales descontará o devolverá stock en la siguiente integración.",
      en: "Operational catalog, minimums and current read-only stock. Materials will deduct or return stock in the next integration.",
      fr: "Catalogue opérationnel, minimums et stock actuel en lecture seule. Les matériaux déduiront ou retourneront le stock lors de la prochaine intégration.",
      a: [
        "Catálogo operativo, mínimos y stock actual de solo lectura. Materiales descontará o devolverá stock en la siguiente integración.",
        "Catalogo operativo, minimos y stock actual de solo lectura. Materiales descontara o devolvera stock en la siguiente integracion."
      ]
    },
    inventoryStatus: { es: "Estado del inventario", en: "Inventory status", fr: "État de l’inventaire", a: ["Estado del inventario"] },
    summary: { es: "RESUMEN", en: "SUMMARY", fr: "RÉSUMÉ", a: ["RESUMEN"] },
    totalRecords: { es: "Total registros", en: "Total records", fr: "Total des enregistrements", a: ["Total registros"] },
    createMaterialProduct: { es: "Crear material / producto", en: "Create material / product", fr: "Créer matériau / produit", a: ["Crear material / producto"] },
    modifyMaterial: { es: "Modificar material", en: "Modify material", fr: "Modifier matériau", a: ["Modificar material"] },
    createMaterialProductUpper: { es: "CREAR MATERIAL / PRODUCTO", en: "CREATE MATERIAL / PRODUCT", fr: "CRÉER MATÉRIAU / PRODUIT", a: ["CREAR MATERIAL / PRODUCTO"] },
    newInventoryRecord: { es: "Nuevo registro de inventario", en: "New inventory record", fr: "Nouvel enregistrement d’inventaire", a: ["Nuevo registro de inventario"] },
    inventoryCreateHelp: {
      es: "El stock actual se crea desde la cantidad inicial como movimiento. Luego solo cambia por entradas, entregas y devoluciones.",
      en: "Current stock is created from the initial quantity as a movement. After that, it only changes through entries, deliveries and returns.",
      fr: "Le stock actuel est créé à partir de la quantité initiale comme mouvement. Ensuite, il ne change que par entrées, livraisons et retours.",
      a: ["El stock actual se crea desde la cantidad inicial como movimiento. Luego solo cambia por entradas, entregas y devoluciones."]
    },
    nameReference: { es: "NOMBRE / REFERENCIA", en: "NAME / REFERENCE", fr: "NOM / RÉFÉRENCE", a: ["NOMBRE / REFERENCIA"] },
    size: { es: "TAMAÑO", en: "SIZE", fr: "TAILLE", a: ["TAMAÑO", "TAMANO"] },
    color: { es: "COLOR", en: "COLOR", fr: "COULEUR", a: ["COLOR"] },
    initialQuantity: { es: "CANTIDAD INICIAL", en: "INITIAL QUANTITY", fr: "QUANTITÉ INITIALE", a: ["CANTIDAD INICIAL"] },
    minimumAlert: { es: "MÍNIMO ALERTA", en: "MINIMUM ALERT", fr: "ALERTE MINIMUM", a: ["MINIMO ALERTA", "MÍNIMO ALERTA"] },
    create: { es: "Crear", en: "Create", fr: "Créer", a: ["Crear"] },
    refresh: { es: "Actualizar", en: "Refresh", fr: "Actualiser", a: ["Actualizar", "Refresh"] },
    back: { es: "Volver", en: "Back", fr: "Retour", a: ["Volver", "Back"] },

    crmHero: {
      es: "Vista viva de colaboradores en turno, pausas y núcleos activos de la empresa.",
      en: "Live view of employees on shift, breaks and active company cores.",
      fr: "Vue en direct des collaborateurs en service, pauses et noyaux actifs de l’entreprise.",
      a: ["Vista viva de colaboradores en turno, pausas y nucleos activos de la empresa.", "Vista viva de colaboradores en turno, pausas y núcleos activos de la empresa."]
    },
    currentOperationalStatus: { es: "ESTADO OPERATIVO ACTUAL", en: "CURRENT OPERATING STATUS", fr: "ÉTAT OPÉRATIONNEL ACTUEL", a: ["ESTADO OPERATIVO ACTUAL"] },
    operationLive: { es: "Operación en vivo", en: "Live operation", fr: "Opération en direct", a: ["Operacion en vivo", "Operación en vivo"] },
    onBreak: { es: "En pausa", en: "On break", fr: "En pause", a: ["En pausa"] },
    collaborators: { es: "COLABORADORES", en: "EMPLOYEES", fr: "COLLABORATEURS", a: ["COLABORADORES"] },
    collaboratorStatus: { es: "Estado por colaborador", en: "Status by employee", fr: "Statut par collaborateur", a: ["Estado por colaborador"] },
    collaborator: { es: "Colaborador", en: "Employee", fr: "Collaborateur", a: ["Colaborador"] },
    offShift: { es: "Fuera de turno", en: "Off shift", fr: "Hors service", a: ["Fuera de turno"] },
    timer: { es: "Cronómetro", en: "Timer", fr: "Chronomètre", a: ["Cronometro", "Cronómetro"] },
    noRequest: { es: "Sin solicitud", en: "No request", fr: "Aucune demande", a: ["Sin solicitud"] },

    staffTitle: { es: "Registro de personal operativo", en: "Operational staff registry", fr: "Registre du personnel opérationnel", a: ["Registro de personal operativo"] },
    staffSubtitle: { es: "administra su personal de forma independiente.", en: "manages its staff independently.", fr: "gère son personnel de manière indépendante.", a: ["administra su personal de forma independiente."] },
    staffHero: {
      es: "Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.",
      en: "Manage employees, technicians, supervisors and roles connected to bot, payroll and operations.",
      fr: "Gérez les employés, techniciens, superviseurs et rôles connectés au bot, à la paie et aux opérations.",
      a: ["Gestiona empleados, tecnicos, supervisores y roles conectados a bot, nomina y operacion.", "Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación."]
    },
    editableTable: { es: "TABLA EDITABLE", en: "EDITABLE TABLE", fr: "TABLEAU MODIFIABLE", a: ["TABLA EDITABLE"] },
    addRow: { es: "Agregar fila", en: "Add row", fr: "Ajouter une ligne", a: ["Agregar fila", "Agregar personal", "Add row"] },
    saveChanges: { es: "Guardar cambios", en: "Save changes", fr: "Enregistrer", a: ["Guardar cambios", "Save changes"] },
    history: { es: "Historial", en: "History", fr: "Historique", a: ["Historial", "History"] },
    all: { es: "Todos", en: "All", fr: "Tous", a: ["Todos", "All"] },
    activePlural: { es: "Activos", en: "Active", fr: "Actifs", a: ["Activos", "Active"] },
    inactivePlural: { es: "Inactivos", en: "Inactive", fr: "Inactifs", a: ["Inactivos", "Inactive"] },
    archivedPlural: { es: "Archivados", en: "Archived", fr: "Archivés", a: ["Archivados", "Archived"] },
    searchMatches: {
      es: "Buscar coincidencias: nombre, rol, teléfono, correo, Telegram, estado...",
      en: "Search matches: name, role, phone, email, Telegram, status...",
      fr: "Rechercher : nom, rôle, téléphone, e-mail, Telegram, statut...",
      a: ["Buscar coincidencias: nombre, rol, teléfono, correo, Telegram, estado...", "Buscar coincidencias: nombre, rol, tel?fono, correo, Telegram, estado..."]
    },

    name: { es: "NOMBRE", en: "NAME", fr: "NOM", a: ["NOMBRE", "Nombre"] },
    role: { es: "ROL", en: "ROLE", fr: "RÔLE", a: ["ROL", "Rol"] },
    phone: { es: "TELÉFONO", en: "PHONE", fr: "TÉLÉPHONE", a: ["TELEFONO", "TELÉFONO", "Telefono", "Teléfono"] },
    email: { es: "CORREO", en: "EMAIL", fr: "E-MAIL", a: ["CORREO", "Correo"] },
    hireDate: { es: "FECHA INGRESO", en: "HIRE DATE", fr: "DATE D’ENTRÉE", a: ["FECHA INGRESO", "Fecha ingreso"] },
    regularHour: { es: "HORA ORDINARIA", en: "REGULAR HOUR", fr: "HEURE NORMALE", a: ["HORA ORDINARIA", "Hora ordinaria"] },
    extraHour: { es: "HORA EXTRA", en: "EXTRA HOUR", fr: "HEURE SUPPLÉMENTAIRE", a: ["HORA EXTRA", "Hora extra"] },
    discount1: { es: "DESCUENTO 1", en: "DISCOUNT 1", fr: "REMISE 1", a: ["DESCUENTO 1", "Descuento 1"] },
    discount2: { es: "DESCUENTO 2", en: "DISCOUNT 2", fr: "REMISE 2", a: ["DESCUENTO 2", "Descuento 2"] },
    status: { es: "ESTADO", en: "STATUS", fr: "STATUT", a: ["ESTADO", "Estado", "STATUS"] },
    actions: { es: "ACCIONES", en: "ACTIONS", fr: "ACTIONS", a: ["ACCIONES", "Acciones", "ACTIONS"] },
    save: { es: "Guardar", en: "Save", fr: "Enregistrer", a: ["Guardar", "Save"] },
    activate: { es: "Activar", en: "Activate", fr: "Activer", a: ["Activar", "Activate"] },
    deactivate: { es: "Inactivar", en: "Deactivate", fr: "Désactiver", a: ["Inactivar", "Deactivate"] },
    delete: { es: "Eliminar", en: "Delete", fr: "Supprimer", a: ["Eliminar", "Delete"] },
    active: { es: "Activo", en: "Active", fr: "Actif", a: ["Activo", "Active"] },
    inactive: { es: "Inactivo", en: "Inactive", fr: "Inactif", a: ["Inactivo", "Inactive"] },
    archived: { es: "Archivado", en: "Archived", fr: "Archivé", a: ["Archivado", "Archived"] },

    materialsHero: {
      es: "Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.",
      en: "Outbound orders connected to Inventory. Delivery deducts stock; return requires an order number.",
      fr: "Ordres de sortie connectés à l’inventaire. La livraison déduit le stock ; le retour exige un numéro d’ordre.",
      a: ["Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.", "Ordenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige numero de orden."]
    },
    operationalCycle: { es: "CICLO OPERATIVO", en: "OPERATING CYCLE", fr: "CYCLE OPÉRATIONNEL", a: ["CICLO OPERATIVO"] },
    materialOrders: { es: "Órdenes de materiales", en: "Material orders", fr: "Ordres de matériaux", a: ["Órdenes de materiales", "Ordenes de materiales"] },
    pending: { es: "Pendientes", en: "Pending", fr: "En attente", a: ["Pendientes"] },
    approved: { es: "Aprobadas", en: "Approved", fr: "Approuvées", a: ["Aprobadas"] },
    delivered: { es: "Entregadas", en: "Delivered", fr: "Livrées", a: ["Entregadas"] },
    consignment: { es: "Consigna", en: "Consignment", fr: "Consigne", a: ["Consigna"] },
    returned: { es: "Devueltas", en: "Returned", fr: "Retournées", a: ["Devueltas"] },
    order: { es: "ORDEN", en: "ORDER", fr: "ORDRE", a: ["ORDEN"] },
    requester: { es: "SOLICITANTE", en: "REQUESTER", fr: "DEMANDEUR", a: ["SOLICITANTE"] },
    material: { es: "MATERIAL", en: "MATERIAL", fr: "MATÉRIEL", a: ["MATERIAL"] },
    quantity: { es: "CANTIDAD", en: "QUANTITY", fr: "QUANTITÉ", a: ["CANTIDAD"] },
    destination: { es: "DESTINO", en: "DESTINATION", fr: "DESTINATION", a: ["DESTINO"] },
    detail: { es: "Detalle", en: "Detail", fr: "Détail", a: ["Detalle", "Detail"] },
    returnAction: { es: "Devolución", en: "Return", fr: "Retour", a: ["Devolución", "Devolucion", "Return"] },
    outputManagement: { es: "GESTIÓN DE SALIDA", en: "OUTPUT MANAGEMENT", fr: "GESTION DE SORTIE", a: ["GESTIÓN DE SALIDA", "GESTION DE SALIDA"] },

    reportsModuleSubtitle: {
      es: "Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta.",
      en: "Consolidated history of Staff, GPS, Materials, Inventory and Payroll. It does not modify data; it only audits and exports.",
      fr: "Historique consolidé du personnel, GPS, matériaux, inventaire et paie. Il ne modifie pas les données ; il audite et exporte uniquement.",
      a: ["HistÃ³rico consolidado de Personal, GPS, Materiales, Inventario y NÃ³mina. No modifica datos; solo audita y exporta.", "Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta."]
    },
    executiveSummary: { es: "Resumen ejecutivo", en: "Executive summary", fr: "Résumé exécutif", a: ["Resumen ejecutivo"] },
    operationalDetail: { es: "Detalle operativo", en: "Operational detail", fr: "Détail opérationnel", a: ["Detalle operativo"] },
    auditableTables: { es: "Tablas auditables", en: "Auditable tables", fr: "Tableaux auditables", a: ["Tablas auditables"] },

    settings: { es: "Configuración", en: "Settings", fr: "Configuration", a: ["Configuración", "Settings"] },
    logout: { es: "Salir", en: "Log out", fr: "Quitter", a: ["Salir", "Log out"] }
  };

  const aliasToKey = new Map();

  Object.keys(T).forEach((key) => {
    const item = T[key];
    ["es", "en", "fr"].forEach((lang) => {
      if (item[lang]) aliasToKey.set(norm(item[lang]), key);
    });
    (item.a || []).forEach((alias) => aliasToKey.set(norm(alias), key));
  });

  const sortedAliases = Array.from(aliasToKey.keys()).sort((a, b) => b.length - a.length);

  function currentLang() {
    const raw = String(localStorage.getItem(LANG_KEY) || document.documentElement.lang || "es").toLowerCase();
    return ["es", "en", "fr"].includes(raw) ? raw : "es";
  }

  function norm(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .replace(/[“”]/g, '"')
      .replace(/[‘’]/g, "'")
      .trim();
  }

  function targetForKey(key) {
    const lang = currentLang();
    return (T[key] && (T[key][lang] || T[key].es)) || key;
  }

  function translatePlain(value) {
    const raw = String(value || "");
    const clean = norm(raw);

    if (!clean) return raw;
    if (/^[\d\s.,:$%#@/_-]+$/.test(clean)) return raw;
    if (clean.includes("@")) return raw;
    if (/^[A-Z]{2,}-\d{4}/.test(clean)) return raw;
    if (/^[a-f0-9-]{24,}$/i.test(clean)) return raw;

    let key = aliasToKey.get(norm(clean));

    if (!key) {
      const activeModulesMatch = clean.match(/^(\d+)\s+(módulos activos|modulos activos|m\?dulos activos|active modules|modules actifs)$/i);
      if (activeModulesMatch) {
        return `${activeModulesMatch[1]} ${targetForKey("activeModules")}`;
      }

      const companyStaff = clean.match(/^(.+?)\s+administra su personal de forma independiente\.?$/i);
      if (companyStaff) {
        const suffix = targetForKey("staffSubtitle");
        return `${companyStaff[1]} ${suffix}`;
      }

      const showing = clean.match(/^Mostrando\s+(.+?)\s+de\s+(.+?)\s+registros\.?$/i);
      if (showing) {
        if (currentLang() === "en") return `Showing ${showing[1]} of ${showing[2]} records.`;
        if (currentLang() === "fr") return `Affichage ${showing[1]} sur ${showing[2]} enregistrements.`;
        return `Mostrando ${showing[1]} de ${showing[2]} registros.`;
      }

      return raw;
    }

    const translated = targetForKey(key);
    return raw.replace(clean, translated);
  }

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function translateHtml(html) {
    let out = String(html || "");

    if (!out || currentLang() === "es") return out;

    for (const alias of sortedAliases) {
      if (!alias || alias.length < 4) continue;
      const key = aliasToKey.get(alias);
      const target = targetForKey(key);
      if (!target || target === alias) continue;

      out = out.replace(new RegExp(escapeRegExp(alias), "g"), target);
    }

    out = out.replace(/(\d+)\s+(módulos activos|modulos activos|m\?dulos activos|mÃ³dulos activos)/gi, function(_, n) {
      return `${n} ${targetForKey("activeModules")}`;
    });

    return out;
  }

  function skipElement(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (["script", "style", "code", "pre", "textarea"].includes(tag)) return true;
    if (el.closest && el.closest("[data-clx-no-i18n]")) return true;
    return false;
  }

  function translateDom(root) {
    const base = root || document.body;
    if (!base) return;

    if (base.nodeType === Node.TEXT_NODE) {
      const next = translatePlain(base.nodeValue);
      if (next !== base.nodeValue) base.nodeValue = next;
      return;
    }

    if (base.nodeType !== Node.ELEMENT_NODE && base.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
    if (base.nodeType === Node.ELEMENT_NODE && skipElement(base)) return;

    const walker = document.createTreeWalker(base, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || skipElement(parent)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });

    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach((node) => {
      const next = translatePlain(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
    });

    if (base.querySelectorAll) {
      base.querySelectorAll("[placeholder], [title], [aria-label], input[type='button'], input[type='submit']").forEach((el) => {
        if (skipElement(el)) return;

        ["placeholder", "title", "aria-label"].forEach((attr) => {
          if (el.hasAttribute(attr)) {
            const current = el.getAttribute(attr);
            const next = translatePlain(current);
            if (next !== current) el.setAttribute(attr, next);
          }
        });

        if (el.matches("input[type='button'], input[type='submit']")) {
          const next = translatePlain(el.value);
          if (next !== el.value) el.value = next;
        }
      });
    }

    const settings = document.getElementById("clxAccountSettingsBtn");
    const logout = document.getElementById("clxAccountLogoutBtn");

    if (settings) settings.textContent = `⚙ ${targetForKey("settings")}`;
    if (logout) logout.textContent = `⏻ ${targetForKey("logout")}`;

    document.documentElement.lang = currentLang();
  }

  function installInnerHtmlInterceptor() {
    const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
    if (!descriptor || !descriptor.set || window.__CLX_FULL_I18N_INNERHTML_INSTALLED__) return;

    window.__CLX_FULL_I18N_INNERHTML_INSTALLED__ = true;

    Object.defineProperty(Element.prototype, "innerHTML", {
      get: descriptor.get,
      set: function(value) {
        const tag = this && this.tagName ? this.tagName.toLowerCase() : "";
        if (["script", "style", "code", "pre", "textarea"].includes(tag)) {
          descriptor.set.call(this, value);
          return;
        }

        descriptor.set.call(this, translateHtml(String(value || "")));
      }
    });
  }

  let timer = null;

  function run() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => translateDom(document.body), 60);
  }

  function setLang(lang) {
    const selected = String(lang || "es").toLowerCase();
    if (!["es", "en", "fr"].includes(selected)) return;

    localStorage.setItem(LANG_KEY, selected);
    document.documentElement.lang = selected;
    run();
  }

  installInnerHtmlInterceptor();

  window.CLX_RUNTIME_I18N = {
    run,
    setLang,
    translateDom,
    translateHtml,
    t: targetForKey,
    lang: currentLang
  };

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (target && target.id === "clxAccountLanguage") {
      setLang(target.value);
    }
  }, true);

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target.id === "clxAccountSaveBtn") {
      setTimeout(() => {
        const langSelect = document.getElementById("clxAccountLanguage");
        if (langSelect) setLang(langSelect.value);
        run();
      }, 250);
    }
  }, true);

  const observer = new MutationObserver(run);

  function init() {
    translateDom(document.body);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label", "value"]
    });
    run();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
'''

text = engine + "\n\n" + text
path.write_text(text, encoding="utf-8")

print("PATCH_OK: 020A-4 full runtime i18n engine inserted at top")
