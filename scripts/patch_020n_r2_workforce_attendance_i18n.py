from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_workforce_i18n_safe.js")

js = r'''
(function clonexaSafeWorkforceI18n020NR2() {
  "use strict";

  if (window.__CLONEXA_020N_R2_WORKFORCE_I18N__) return;
  window.__CLONEXA_020N_R2_WORKFORCE_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const ENTRIES = {
    settings:{es:"Ajustes",en:"Settings",fr:"Configuration",aliases:["Ajustes","Settings","Configuration"]},
    logout:{es:"Cerrar sesión",en:"Log out",fr:"Quitter",aliases:["Cerrar sesión","Cerrar sesion","Log out","Quitter"]},
    activeTenant:{es:"Tenant activo",en:"Active tenant",fr:"Tenant actif",aliases:["Tenant activo","Active tenant"]},

    moduleEyebrow:{es:"Módulo Workforce",en:"Workforce module",fr:"Module Workforce",aliases:["Modulo Workforce","Módulo Workforce","WORKFORCE MODULE","Workforce module"]},
    moduleTitle:{es:"Personal",en:"Staff",fr:"Personnel",aliases:["Personal","Staff","Personnel"]},
    moduleSubtitle:{
      es:"Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.",
      en:"Manage employees, technicians, supervisors and roles connected to bot, payroll and operations.",
      fr:"Gérez les employés, techniciens, superviseurs et rôles connectés au bot, à la paie et aux opérations.",
      aliases:[
        "Gestiona empleados, tecnicos, supervisores y roles conectados a bot, nomina y operacion.",
        "Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.",
        "Manage employees, technicians, supervisors and roles connected to bot, payroll and operations."
      ]
    },

    addRow:{es:"+ Agregar fila",en:"+ Add row",fr:"+ Ajouter une ligne",aliases:["+ Agregar fila","+ Add row","Agregar fila","Add row"]},
    saveChanges:{es:"Guardar cambios",en:"Save changes",fr:"Enregistrer les modifications",aliases:["Guardar cambios","Save changes"]},
    history:{es:"Historial",en:"History",fr:"Historique",aliases:["Historial","History"]},
    attendance:{es:"Asistencia",en:"Attendance",fr:"Assistance",aliases:["Asistencia","Attendance"]},
    back:{es:"Volver",en:"Back",fr:"Retour",aliases:["Volver","Back","Retour"]},
    backToStaff:{es:"Volver a Personal",en:"Back to Staff",fr:"Retour au personnel",aliases:["Volver a Personal","Back to Staff"]},
    refresh:{es:"Actualizar",en:"Refresh",fr:"Actualiser",aliases:["Actualizar","Refresh","Actualiser"]},
    search:{es:"Buscar",en:"Search",fr:"Rechercher",aliases:["Buscar","Search"]},
    exportCsv:{es:"Exportar CSV",en:"Export CSV",fr:"Exporter CSV",aliases:["Exportar CSV","Export CSV"]},
    csv:{es:"CSV",en:"CSV",fr:"CSV",aliases:["CSV"]},

    editableTable:{es:"Tabla editable",en:"Editable table",fr:"Table modifiable",aliases:["Tabla editable","Editable table"]},
    operationalStaffRecord:{es:"Registro de personal operativo",en:"Operational staff record",fr:"Registre du personnel opérationnel",aliases:["Registro de personal operativo","Operational staff record"]},
    companyPersonalHelp:{es:"administra su personal de forma independiente.",en:"manages its staff independently.",fr:"gère son personnel de manière indépendante.",aliases:["administra su personal de forma independiente.","manages its staff independently.","managesmanages its staff independently."]},

    total:{es:"Total",en:"Total",fr:"Total",aliases:["TOTAL","Total"]},
    activePlural:{es:"Activos",en:"Active",fr:"Actifs",aliases:["ACTIVOS","Activos"]},
    inactivePlural:{es:"Inactivos",en:"Inactive",fr:"Inactifs",aliases:["INACTIVOS","Inactivos"]},
    archivedPlural:{es:"Archivados",en:"Archived",fr:"Archivés",aliases:["ARCHIVADOS","Archivados","ARCHIVED","Archived"]},
    all:{es:"Todos",en:"All",fr:"Tous",aliases:["Todos","All","Tous"]},

    searchPlaceholder:{
      es:"Buscar coincidencias: nombre, rol, teléfono, correo, Telegram, estado...",
      en:"Search matches: name, role, phone, email, Telegram, status...",
      fr:"Rechercher : nom, rôle, téléphone, courriel, Telegram, statut...",
      aliases:[
        "Buscar coincidencias: nombre, rol, teléfono, correo, Telegram, estado...",
        "Buscar coincidencias: nombre, rol, telefono, correo, Telegram, estado...",
        "Buscar coincidencias: nombre, rol, tel?fono, correo, Telegram, estado...",
        "Search matches: name, role, phone, email, Telegram, status..."
      ]
    },

    showingRecords:{es:"Mostrando {a} de {b} registros.",en:"Showing {a} of {b} records.",fr:"Affichage de {a} sur {b} enregistrements.",aliases:[]},

    name:{es:"Nombre",en:"Name",fr:"Nom",aliases:["NOMBRE","Nombre","NAME","Name"]},
    fullName:{es:"Nombre completo",en:"Full name",fr:"Nom complet",aliases:["Nombre completo","Full name"]},
    role:{es:"Rol",en:"Role",fr:"Rôle",aliases:["ROL","Rol","ROLE","Role"]},
    phone:{es:"Teléfono",en:"Phone",fr:"Téléphone",aliases:["TELEFONO","TELÉFONO","Telefono","Teléfono","PHONE","Phone"]},
    email:{es:"Correo",en:"Email",fr:"Courriel",aliases:["CORREO","Correo","EMAIL","Email"]},
    telegramId:{es:"Telegram ID",en:"Telegram ID",fr:"Telegram ID",aliases:["TELEGRAM ID","Telegram ID","ID Telegram"]},
    hireDate:{es:"Fecha ingreso",en:"Hire date",fr:"Date d’entrée",aliases:["FECHA INGRESO","Fecha ingreso","HIRE DATE","Hire date"]},
    regularRate:{es:"Hora ordinaria",en:"Regular rate",fr:"Taux normal",aliases:["HORA ORDINARIA","Hora ordinaria","REGULAR RATE","Regular rate"]},
    extraRate:{es:"Hora extra",en:"Extra rate",fr:"Taux supplémentaire",aliases:["HORA EXTRA","Hora extra","EXTRA RATE","Extra rate"]},
    discount1:{es:"Descuento 1",en:"Discount 1",fr:"Remise 1",aliases:["DESCUENTO 1","Descuento 1","DISCOUNT 1","Discount 1"]},
    discount2:{es:"Descuento 2",en:"Discount 2",fr:"Remise 2",aliases:["DESCUENTO 2","Descuento 2","DISCOUNT 2","Discount 2"]},
    status:{es:"Estado",en:"Status",fr:"Statut",aliases:["ESTADO","Estado","STATUS","Status"]},
    actions:{es:"Acciones",en:"Actions",fr:"Actions",aliases:["ACCIONES","Acciones","ACTIONS","Actions"]},

    adminCompany:{es:"Admin empresa",en:"Company admin",fr:"Admin entreprise",aliases:["Admin empresa","Company admin"]},
    supervisor:{es:"Supervisor",en:"Supervisor",fr:"Superviseur",aliases:["Supervisor"]},
    technician:{es:"Técnico",en:"Technician",fr:"Technicien",aliases:["Tecnico","Técnico","Technician"]},
    worker:{es:"Operario",en:"Operator",fr:"Opérateur",aliases:["Operario","Operator"]},
    seller:{es:"Vendedor",en:"Salesperson",fr:"Vendeur",aliases:["Vendedor","Salesperson"]},
    bartender:{es:"Barman",en:"Bartender",fr:"Barman",aliases:["Barman","Bartender"]},
    waiter:{es:"Mesero",en:"Waiter",fr:"Serveur",aliases:["Mesero","Waiter"]},
    cashier:{es:"Cajero",en:"Cashier",fr:"Caissier",aliases:["Cajero","Cashier"]},
    inventoryRole:{es:"Inventario",en:"Inventory",fr:"Inventaire",aliases:["Inventario","Inventory"]},
    operator:{es:"Operador",en:"Operator",fr:"Opérateur",aliases:["Operador","Operator"]},

    active:{es:"Activo",en:"Active",fr:"Actif",aliases:["Activo","Active"]},
    inactive:{es:"Inactivo",en:"Inactive",fr:"Inactif",aliases:["Inactivo","Inactive"]},
    archived:{es:"Archivado",en:"Archived",fr:"Archivé",aliases:["Archivado","Archived"]},

    save:{es:"Guardar",en:"Save",fr:"Enregistrer",aliases:["Guardar","Save"]},
    activate:{es:"Activar",en:"Activate",fr:"Activer",aliases:["Activar","Activate"]},
    deactivate:{es:"Inactivar",en:"Deactivate",fr:"Désactiver",aliases:["Inactivar","Deactivate"]},
    delete:{es:"Eliminar",en:"Delete",fr:"Supprimer",aliases:["Eliminar","Delete"]},

    staffHistoryTitle:{es:"Historial de Personal",en:"Staff history",fr:"Historique du personnel",aliases:["Historial de Personal","Staff history"]},
    operationalAudit:{es:"Auditoría operativa",en:"Operational audit",fr:"Audit opérationnel",aliases:["Auditoria operativa","Auditoría operativa","Operational audit"]},
    searchHistory:{es:"Buscar historial",en:"Search history",fr:"Rechercher l’historique",aliases:["Buscar historial","Search history"]},
    from:{es:"Desde",en:"From",fr:"De",aliases:["DESDE","Desde","FROM","From"]},
    to:{es:"Hasta",en:"To",fr:"À",aliases:["HASTA","Hasta","TO","To"]},
    event:{es:"Evento",en:"Event",fr:"Événement",aliases:["EVENTO","Evento","EVENT","Event"]},
    date:{es:"Fecha",en:"Date",fr:"Date",aliases:["FECHA","Fecha","DATE","Date"]},
    employee:{es:"Empleado",en:"Employee",fr:"Employé",aliases:["EMPLEADO","Empleado","EMPLOYEE","Employee"]},
    field:{es:"Campo",en:"Field",fr:"Champ",aliases:["CAMPO","Campo","FIELD","Field"]},
    oldValue:{es:"Valor anterior",en:"Previous value",fr:"Valeur précédente",aliases:["VALOR ANTERIOR","Valor anterior","Previous value"]},
    newValue:{es:"Valor nuevo",en:"New value",fr:"Nouvelle valeur",aliases:["VALOR NUEVO","Valor nuevo","New value"]},
    source:{es:"Fuente",en:"Source",fr:"Source",aliases:["FUENTE","Fuente","Source"]},
    notes:{es:"Notas",en:"Notes",fr:"Notes",aliases:["NOTAS","Notas","Notes"]},

    employeeBaseline:{es:"Registro inicial",en:"Initial record",fr:"Enregistrement initial",aliases:["Registro inicial","Initial record","employee_baseline"]},
    employeeCreated:{es:"Empleado creado",en:"Employee created",fr:"Employé créé",aliases:["Empleado creado","Employee created","employee_created"]},
    employeeUpdated:{es:"Empleado editado",en:"Employee edited",fr:"Employé modifié",aliases:["Empleado editado","Employee edited","employee_updated"]},
    employeeActivated:{es:"Empleado activado",en:"Employee activated",fr:"Employé activé",aliases:["Empleado activado","Employee activated","employee_activated"]},
    employeeInactivated:{es:"Empleado inactivado",en:"Employee inactivated",fr:"Employé désactivé",aliases:["Empleado inactivado","Employee inactivated","employee_inactivated"]},
    employeeArchived:{es:"Empleado archivado",en:"Employee archived",fr:"Employé archivé",aliases:["Empleado archivado","Employee archived","employee_archived"]},
    employeeRestored:{es:"Empleado restaurado",en:"Employee restored",fr:"Employé restauré",aliases:["Empleado restaurado","Employee restored","employee_restored"]},

    events:{es:"Eventos",en:"Events",fr:"Événements",aliases:["EVENTOS","Eventos","Events"]},
    created:{es:"Creados",en:"Created",fr:"Créés",aliases:["Creados","Created"]},
    edited:{es:"Editados",en:"Edited",fr:"Modifiés",aliases:["Editados","Edited"]},
    noHistory:{es:"No hay registros de historial para los filtros seleccionados.",en:"No history records for the selected filters.",fr:"Aucun historique pour les filtres sélectionnés.",aliases:["No hay registros de historial para los filtros seleccionados.","No history records for the selected filters."]},

    attendanceTitle:{es:"Asistencia",en:"Attendance",fr:"Assistance",aliases:["Asistencia","Attendance"]},
    attendanceSubtitle:{
      es:"Bitácora operativa de marcaciones e interacciones del personal: bot, panel, QR, solicitudes, observaciones y eventos por empresa.",
      en:"Operational log of staff check-ins and interactions: bot, panel, QR, requests, observations and company events.",
      fr:"Journal opérationnel des pointages et interactions du personnel : bot, panneau, QR, demandes, observations et événements par entreprise.",
      aliases:[
        "Bitácora operativa de marcaciones e interacciones del personal: bot, panel, QR, solicitudes, observaciones y eventos por empresa.",
        "Bitacora operativa de marcaciones e interacciones del personal: bot, panel, QR, solicitudes, observaciones y eventos por empresa.",
        "Operational log of staff check-ins and interactions: bot, panel, QR, requests, observations and company events."
      ]
    },
    attendanceLogTitle:{es:"Bitácora de asistencia e interacciones",en:"Attendance and interactions log",fr:"Journal d’assistance et d’interactions",aliases:["Bitácora de asistencia e interacciones","Bitacora de asistencia e interacciones","Attendance and interactions log"]},
    attendanceHelp:{
      es:"Consulta registros de 15, 20, 30 días o cualquier rango. CRM, Nómina, KPIs, Materiales y GPS consumirán estos eventos sin mezclarse visualmente.",
      en:"Review records for 15, 20, 30 days or any range. CRM, Payroll, KPIs, Materials and GPS will consume these events without visual mixing.",
      fr:"Consultez les enregistrements de 15, 20, 30 jours ou toute plage. CRM, Paie, KPIs, Matériaux et GPS utiliseront ces événements sans mélange visuel.",
      aliases:[
        "Consulta registros de 15, 20, 30 días o cualquier rango. CRM, Nómina, KPIs, Materiales y GPS consumirán estos eventos sin mezclarse visualmente.",
        "Consulta registros de 15, 20, 30 dias o cualquier rango. CRM, Nomina, KPIs, Materiales y GPS consumiran estos eventos sin mezclarse visualmente.",
        "Review records for 15, 20, 30 days or any range. CRM, Payroll, KPIs, Materials and GPS will consume these events without visual mixing."
      ]
    },
    channel:{es:"Canal",en:"Channel",fr:"Canal",aliases:["CANAL","Canal","CHANNEL","Channel"]},
    module:{es:"Módulo",en:"Module",fr:"Module",aliases:["MÓDULO","MODULO","Módulo","Modulo","MODULE","Module"]},
    detail:{es:"Detalle",en:"Detail",fr:"Détail",aliases:["DETALLE","Detalle","DETAIL","Detail"]},
    dateTime:{es:"Fecha / hora",en:"Date / time",fr:"Date / heure",aliases:["FECHA / HORA","Fecha / hora","DATE / TIME","Date / time"]},

    totalEvents:{es:"Total eventos",en:"Total events",fr:"Total événements",aliases:["TOTAL EVENTOS","Total eventos","TOTAL EVENTS","Total events"]},
    checkIns:{es:"Entradas",en:"Check-ins",fr:"Entrées",aliases:["ENTRADAS","Entradas","Check-ins"]},
    checkOuts:{es:"Salidas",en:"Check-outs",fr:"Sorties",aliases:["SALIDAS","Salidas","Check-outs"]},
    breaks:{es:"Pausas",en:"Breaks",fr:"Pauses",aliases:["PAUSAS","Pausas","Breaks"]},
    requests:{es:"Solicitudes",en:"Requests",fr:"Demandes",aliases:["SOLICITUDES","Solicitudes","Requests"]},
    bot:{es:"Bot",en:"Bot",fr:"Bot",aliases:["BOT","Bot"]},

    shiftStart:{es:"Inicio de turno",en:"Shift start",fr:"Début de service",aliases:["Inicio de turno","Shift start"]},
    shiftEnd:{es:"Finalizar turno",en:"End shift",fr:"Fin de service",aliases:["Finalizar turno","End shift"]},
    resumeWork:{es:"Retomar labores",en:"Resume work",fr:"Reprendre le travail",aliases:["Retomar labores","Resume work"]},
    breakEvent:{es:"Pausa",en:"Break",fr:"Pause",aliases:["Pausa","Break"]},
    gpsLocation:{es:"Ubicación GPS",en:"GPS location",fr:"Position GPS",aliases:["Ubicación GPS","Ubicacion GPS","GPS location"]},
    materialRequest:{es:"Solicitar material",en:"Request material",fr:"Demander du matériel",aliases:["Solicitar material","Request material"]},
    validatedGps:{es:"Ubicación GPS validada",en:"Validated GPS location",fr:"Position GPS validée",aliases:["Ubicación GPS validada","Ubicacion GPS validada","Validated GPS location"]},

    working:{es:"Trabajando",en:"Working",fr:"En service",aliases:["working","Working"]},
    registered:{es:"Registrado",en:"Registered",fr:"Enregistré",aliases:["registered","Registered"]},
    checkedOut:{es:"Turno cerrado",en:"Checked out",fr:"Service clôturé",aliases:["checked_out","Checked out"]},
    onBreak:{es:"En pausa",en:"On break",fr:"En pause",aliases:["on_break","On break","En pausa"]},
    telegram:{es:"Telegram",en:"Telegram",fr:"Telegram",aliases:["Telegram"]},
    workforce:{es:"Workforce",en:"Workforce",fr:"Workforce",aliases:["workforce","Workforce"]},
    gps:{es:"GPS",en:"GPS",fr:"GPS",aliases:["gps","GPS"]},

    attendanceSearchPlaceholder:{es:"Empleado, evento, detalle, canal...",en:"Employee, event, detail, channel...",fr:"Employé, événement, détail, canal...",aliases:["Empleado, evento, detalle, canal...","Employee, event, detail, channel..."]}
  };

  const ALIASES = {};

  function norm(value) {
    return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
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
    if (/^[a-f0-9-]{20,}$/i.test(raw)) return true;
    if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return true;
    if (/^\d{1,2}:\d{2}/.test(raw)) return true;
    if (raw.includes("@")) return true;
    return false;
  }

  function translateText(value) {
    const raw = String(value || "");
    const clean = raw.replace(/\s+/g, " ").trim();

    const companyMatch = clean.match(/^(.+?)\s+(administra su personal de forma independiente\.|manages its staff independently\.|managesmanages its staff independently\.|gère son personnel de manière indépendante\.)$/i);
    if (companyMatch) {
      return raw.replace(clean, `${companyMatch[1]} ${t("companyPersonalHelp")}`);
    }

    const showing = clean.match(/^Mostrando\s+(\d+)\s+de\s+(\d+)\s+registros\.$/i) || clean.match(/^Showing\s+(\d+)\s+of\s+(\d+)\s+records\.$/i);
    if (showing) {
      return raw.replace(clean, t("showingRecords").replace("{a}", showing[1]).replace("{b}", showing[2]));
    }

    const key = ALIASES[norm(clean)];
    if (key) return raw.replace(clean, t(key));

    if (shouldSkipText(clean)) return raw;
    return raw;
  }

  function isWorkforceVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector("#personalGrid")) return true;
    if (app.querySelector("[data-personal-add-row]")) return true;
    if (app.querySelector("[data-personal-save-all]")) return true;
    if (app.querySelector("[data-personal-history]")) return true;
    if (app.querySelector("[data-personal-history-from]")) return true;
    if (app.querySelector("[data-personal-history-search]")) return true;
    if (app.querySelector(".personal-history-grid")) return true;
    if (app.querySelector(".personal-history-toolbar")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Workforce module") ||
      text.includes("Modulo Workforce") ||
      text.includes("Módulo Workforce") ||
      text.includes("Registro de personal operativo") ||
      text.includes("Operational staff record") ||
      text.includes("Bitácora de asistencia") ||
      text.includes("Bitacora de asistencia") ||
      text.includes("Attendance and interactions log") ||
      text.includes("TOTAL EVENTOS") ||
      text.includes("Inicio de turno") ||
      text.includes("Ubicación GPS")
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
        let next = translateText(current);

        if (norm(current) === norm("Empleado, evento, detalle, canal...")) {
          next = t("attendanceSearchPlaceholder");
        }

        if (next !== current) el.setAttribute(attr, next);
      });

      if (el.matches("input[type='button'], input[type='submit']")) {
        const next = translateText(el.value);
        if (next !== el.value) el.value = next;
      }
    });
  }

  function translateWorkforce() {
    try {
      if (!isWorkforceVisible()) return;

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
      console.warn("CLONEXA Workforce i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateWorkforce, 100);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateWorkforce();
      if (count >= 24) clearInterval(id);
    }, 160);
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
    if (isWorkforceVisible()) translateWorkforce();
  }, 1200);

  function init() {
    try {
      if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
      }
      schedule();
      burst();
    } catch (error) {
      console.warn("CLONEXA Workforce i18n init skipped:", error);
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
    r"client_workforce_i18n_safe\.js(?:\?v=[^\"']*)?",
    "client_workforce_i18n_safe.js?v=020NR2",
    html,
    flags=re.IGNORECASE,
)
html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020N-R2 Workforce attendance/history dictionary applied")
