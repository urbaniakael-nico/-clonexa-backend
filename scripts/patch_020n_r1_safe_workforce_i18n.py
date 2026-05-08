from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_workforce_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaSafeWorkforceI18n020NR1() {
  "use strict";

  if (window.__CLONEXA_020N_R1_WORKFORCE_I18N__) return;
  window.__CLONEXA_020N_R1_WORKFORCE_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const ENTRIES = {
    settings: { es:"Ajustes", en:"Settings", fr:"Configuration", aliases:["Ajustes","Settings","Configuration"] },
    logout: { es:"Cerrar sesión", en:"Log out", fr:"Quitter", aliases:["Cerrar sesión","Cerrar sesion","Log out","Quitter"] },
    activeTenant: { es:"Tenant activo", en:"Active tenant", fr:"Tenant actif", aliases:["Tenant activo","Active tenant","Tenant actif"] },

    moduleEyebrow: {
      es:"Módulo Workforce",
      en:"Workforce module",
      fr:"Module Workforce",
      aliases:["Modulo Workforce","Módulo Workforce","WORKFORCE MODULE","Workforce module"]
    },
    moduleTitle: {
      es:"Personal",
      en:"Staff",
      fr:"Personnel",
      aliases:["Personal","Staff","Personnel"]
    },
    moduleSubtitle: {
      es:"Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.",
      en:"Manage employees, technicians, supervisors and roles connected to bot, payroll and operations.",
      fr:"Gérez les employés, techniciens, superviseurs et rôles connectés au bot, à la paie et aux opérations.",
      aliases:[
        "Gestiona empleados, tecnicos, supervisores y roles conectados a bot, nomina y operacion.",
        "Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.",
        "Manage employees, technicians, supervisors and roles connected to bot, payroll and operations."
      ]
    },

    addRow: { es:"+ Agregar fila", en:"+ Add row", fr:"+ Ajouter une ligne", aliases:["+ Agregar fila","+ Add row","+ Ajouter une ligne","Agregar fila","Add row"] },
    saveChanges: { es:"Guardar cambios", en:"Save changes", fr:"Enregistrer les modifications", aliases:["Guardar cambios","Save changes"] },
    history: { es:"Historial", en:"History", fr:"Historique", aliases:["Historial","History","Historique"] },
    back: { es:"Volver", en:"Back", fr:"Retour", aliases:["Volver","Back","Retour"] },
    backToPersonal: { es:"Volver a Personal", en:"Back to Staff", fr:"Retour au personnel", aliases:["Volver a Personal","Back to Staff"] },
    exportCsv: { es:"Exportar CSV", en:"Export CSV", fr:"Exporter CSV", aliases:["Exportar CSV","Export CSV"] },
    csv: { es:"CSV", en:"CSV", fr:"CSV", aliases:["CSV"] },
    dashboard: { es:"Dashboard", en:"Dashboard", fr:"Tableau de bord", aliases:["Dashboard"] },

    searchPlaceholder: {
      es:"Buscar por nombre, rol, teléfono, correo o Telegram...",
      en:"Search by name, role, phone, email or Telegram...",
      fr:"Rechercher par nom, rôle, téléphone, courriel ou Telegram...",
      aliases:[
        "Buscar por nombre, rol, telefono, correo o Telegram...",
        "Buscar por nombre, rol, teléfono, correo o Telegram...",
        "Buscar por nombre, rol, tel?fono, correo o Telegram...",
        "Search by name, role, phone, email or Telegram..."
      ]
    },

    editableTable: { es:"Tabla editable", en:"Editable table", fr:"Table modifiable", aliases:["Tabla editable","Editable table"] },
    operationalStaffRecord: { es:"Registro de personal operativo", en:"Operational staff record", fr:"Registre du personnel opérationnel", aliases:["Registro de personal operativo","Operational staff record"] },
    companyPersonalHelp: {
      es:"Esta empresa administra su personal de forma independiente.",
      en:"This company manages its staff independently.",
      fr:"Cette entreprise gère son personnel de manière indépendante.",
      aliases:["Esta empresa administra su personal de forma independiente.","This company manages its staff independently."]
    },

    name: { es:"Nombre", en:"Name", fr:"Nom", aliases:["Nombre","Name","Nom"] },
    fullName: { es:"Nombre completo", en:"Full name", fr:"Nom complet", aliases:["Nombre completo","Full name","Nom complet"] },
    role: { es:"Rol", en:"Role", fr:"Rôle", aliases:["Rol","Role","Rôle"] },
    phone: { es:"Teléfono", en:"Phone", fr:"Téléphone", aliases:["Telefono","Teléfono","Phone","Téléphone"] },
    email: { es:"Correo", en:"Email", fr:"Courriel", aliases:["Correo","Email","Courriel"] },
    emailPlaceholder: { es:"correo@empresa.com", en:"email@company.com", fr:"courriel@entreprise.com", aliases:["correo@empresa.com","email@company.com","courriel@entreprise.com"] },
    telegramId: { es:"Telegram ID", en:"Telegram ID", fr:"Telegram ID", aliases:["Telegram ID","ID Telegram"] },
    telegramUser: { es:"Telegram usuario", en:"Telegram user", fr:"Utilisateur Telegram", aliases:["Telegram usuario","Telegram user"] },
    hireDate: { es:"Fecha ingreso", en:"Hire date", fr:"Date d’entrée", aliases:["Fecha ingreso","Hire date","Date d’entrée"] },
    regularRate: { es:"Hora ordinaria", en:"Regular rate", fr:"Taux normal", aliases:["Hora ordinaria","Regular rate"] },
    extraRate: { es:"Hora extra", en:"Extra rate", fr:"Taux supplémentaire", aliases:["Hora extra","Extra rate"] },
    discount1: { es:"Descuento 1", en:"Discount 1", fr:"Remise 1", aliases:["Descuento 1","Discount 1"] },
    discount2: { es:"Descuento 2", en:"Discount 2", fr:"Remise 2", aliases:["Descuento 2","Discount 2"] },
    status: { es:"Estado", en:"Status", fr:"Statut", aliases:["Estado","Status","Statut"] },
    actions: { es:"Acciones", en:"Actions", fr:"Actions", aliases:["Acciones","Actions"] },
    document: { es:"Documento", en:"Document", fr:"Document", aliases:["Documento","Document"] },
    employeeType: { es:"Tipo empleado", en:"Employee type", fr:"Type d’employé", aliases:["Tipo empleado","Employee type"] },

    adminCompany: { es:"Admin empresa", en:"Company admin", fr:"Admin entreprise", aliases:["Admin empresa","Company admin"] },
    supervisor: { es:"Supervisor", en:"Supervisor", fr:"Superviseur", aliases:["Supervisor","Superviseur"] },
    technician: { es:"Técnico", en:"Technician", fr:"Technicien", aliases:["Tecnico","Técnico","Technician"] },
    worker: { es:"Operario", en:"Operator", fr:"Opérateur", aliases:["Operario","Operator"] },
    seller: { es:"Vendedor", en:"Salesperson", fr:"Vendeur", aliases:["Vendedor","Salesperson"] },
    bartender: { es:"Barman", en:"Bartender", fr:"Barman", aliases:["Barman","Bartender"] },
    waiter: { es:"Mesero", en:"Waiter", fr:"Serveur", aliases:["Mesero","Waiter"] },
    cashier: { es:"Cajero", en:"Cashier", fr:"Caissier", aliases:["Cajero","Cashier"] },
    inventoryRole: { es:"Inventario", en:"Inventory", fr:"Inventaire", aliases:["Inventario","Inventory"] },
    operator: { es:"Operador", en:"Operator", fr:"Opérateur", aliases:["Operador","Operator"] },

    active: { es:"Activo", en:"Active", fr:"Actif", aliases:["Activo","Active","Actif"] },
    inactive: { es:"Inactivo", en:"Inactive", fr:"Inactif", aliases:["Inactivo","Inactive","Inactif"] },
    archived: { es:"Archivado", en:"Archived", fr:"Archivé", aliases:["Archivado","Archived","Archivé"] },

    save: { es:"Guardar", en:"Save", fr:"Enregistrer", aliases:["Guardar","Save"] },
    activate: { es:"Activar", en:"Activate", fr:"Activer", aliases:["Activar","Activate"] },
    deactivate: { es:"Inactivar", en:"Deactivate", fr:"Désactiver", aliases:["Inactivar","Deactivate"] },
    delete: { es:"Eliminar", en:"Delete", fr:"Supprimer", aliases:["Eliminar","Delete"] },
    restore: { es:"Restaurar", en:"Restore", fr:"Restaurer", aliases:["Restaurar","Restore"] },

    rowAddedNotice: {
      es:"Fila agregada. Completa los datos y guarda.",
      en:"Row added. Complete the data and save.",
      fr:"Ligne ajoutée. Complétez les données et enregistrez.",
      aliases:["Fila agregada. Completa los datos y guarda.","Row added. Complete the data and save."]
    },
    needNameNotice: {
      es:"Agrega al menos un nombre antes de guardar.",
      en:"Add at least one name before saving.",
      fr:"Ajoutez au moins un nom avant d’enregistrer.",
      aliases:["Agrega al menos un nombre antes de guardar.","Add at least one name before saving."]
    },
    savedNotice: {
      es:"Cambios guardados.",
      en:"Changes saved.",
      fr:"Modifications enregistrées.",
      aliases:["Cambios guardados.","Changes saved."]
    },
    rowSavedNotice: {
      es:"Fila guardada.",
      en:"Row saved.",
      fr:"Ligne enregistrée.",
      aliases:["Fila guardada.","Row saved."]
    },
    employeeCreated: { es:"Empleado creado", en:"Employee created", fr:"Employé créé", aliases:["Empleado creado","Employee created","employee_created"] },
    employeeUpdated: { es:"Empleado editado", en:"Employee edited", fr:"Employé modifié", aliases:["Empleado editado","Employee edited","employee_updated"] },
    employeeActivated: { es:"Empleado activado", en:"Employee activated", fr:"Employé activé", aliases:["Empleado activado","Employee activated","employee_activated"] },
    employeeInactivated: { es:"Empleado inactivado", en:"Employee inactivated", fr:"Employé désactivé", aliases:["Empleado inactivado","Employee inactivated","employee_inactivated"] },
    employeeArchived: { es:"Empleado archivado", en:"Employee archived", fr:"Employé archivé", aliases:["Empleado archivado","Employee archived","employee_archived"] },
    employeeRestored: { es:"Empleado restaurado", en:"Employee restored", fr:"Employé restauré", aliases:["Empleado restaurado","Employee restored","employee_restored"] },
    employeeBaseline: { es:"Registro inicial", en:"Initial record", fr:"Enregistrement initial", aliases:["Registro inicial","Initial record","employee_baseline"] },

    event: { es:"Evento", en:"Event", fr:"Événement", aliases:["Evento","Event"] },
    field: { es:"Campo", en:"Field", fr:"Champ", aliases:["Campo","Field"] },
    oldValue: { es:"Valor anterior", en:"Previous value", fr:"Valeur précédente", aliases:["Valor anterior","Previous value"] },
    newValue: { es:"Valor nuevo", en:"New value", fr:"Nouvelle valeur", aliases:["Valor nuevo","New value"] },
    source: { es:"Fuente", en:"Source", fr:"Source", aliases:["Fuente","Source"] },
    notes: { es:"Notas", en:"Notes", fr:"Notes", aliases:["Notas","Notes"] },
    record: { es:"Registro", en:"Record", fr:"Enregistrement", aliases:["Registro","Record"] },
    date: { es:"Fecha", en:"Date", fr:"Date", aliases:["Fecha","Date"] },

    staffHistoryTitle: { es:"Historial de Personal", en:"Staff history", fr:"Historique du personnel", aliases:["Historial de Personal","Staff history"] },
    historySubtitle: {
      es:"Consulta registros, ediciones, activaciones, inactivaciones y archivados por rango de fechas.",
      en:"Review records, edits, activations, inactivations and archived staff by date range.",
      fr:"Consultez les enregistrements, modifications, activations, désactivations et archivages par plage de dates.",
      aliases:[
        "Consulta registros, ediciones, activaciones, inactivaciones y archivados por rango de fechas.",
        "Review records, edits, activations, inactivations and archived staff by date range."
      ]
    },
    operationalAudit: { es:"Auditoría operativa", en:"Operational audit", fr:"Audit opérationnel", aliases:["Auditoria operativa","Auditoría operativa","Operational audit"] },
    searchHistory: { es:"Buscar historial", en:"Search history", fr:"Rechercher l’historique", aliases:["Buscar historial","Search history"] },
    historyHelp: {
      es:"Usa estos filtros para validar datos de 15, 20, 30 días o cualquier rango operativo.",
      en:"Use these filters to validate data for 15, 20, 30 days or any operational range.",
      fr:"Utilisez ces filtres pour valider les données sur 15, 20, 30 jours ou toute plage opérationnelle.",
      aliases:[
        "Usa estos filtros para validar datos de 15, 20, 30 dias o cualquier rango operativo.",
        "Usa estos filtros para validar datos de 15, 20, 30 días o cualquier rango operativo.",
        "Use these filters to validate data for 15, 20, 30 days or any operational range."
      ]
    },

    from: { es:"Desde", en:"From", fr:"De", aliases:["Desde","From"] },
    to: { es:"Hasta", en:"To", fr:"À", aliases:["Hasta","To"] },
    search: { es:"Buscar", en:"Search", fr:"Rechercher", aliases:["Buscar","Search"] },
    all: { es:"Todos", en:"All", fr:"Tous", aliases:["Todos","All","Tous"] },
    searchHistoryPlaceholder: {
      es:"Empleado, evento, rol, estado...",
      en:"Employee, event, role, status...",
      fr:"Employé, événement, rôle, statut...",
      aliases:["Empleado, evento, rol, estado...","Employee, event, role, status..."]
    },

    events: { es:"Eventos", en:"Events", fr:"Événements", aliases:["Eventos","Events"] },
    created: { es:"Creados", en:"Created", fr:"Créés", aliases:["Creados","Created"] },
    edited: { es:"Editados", en:"Edited", fr:"Modifiés", aliases:["Editados","Edited"] },
    archivedPlural: { es:"Archivados", en:"Archived", fr:"Archivés", aliases:["Archivados","Archived"] },
    noHistory: {
      es:"No hay registros de historial para los filtros seleccionados.",
      en:"No history records for the selected filters.",
      fr:"Aucun historique pour les filtres sélectionnés.",
      aliases:["No hay registros de historial para los filtros seleccionados.","No history records for the selected filters."]
    },

    loadPersonalError: { es:"No se pudo cargar personal.", en:"Could not load staff.", fr:"Impossible de charger le personnel.", aliases:["No se pudo cargar personal.","Could not load staff."] },
    operationError: { es:"No se pudo completar la operación.", en:"Could not complete the operation.", fr:"Impossible de terminer l’opération.", aliases:["No se pudo completar la operación.","Could not complete the operation."] },
    company: { es:"Empresa", en:"Company", fr:"Entreprise", aliases:["Empresa","Company"] },
    activeModules: { es:"Módulos activos", en:"Active modules", fr:"Modules actifs", aliases:["Modulos activos","Módulos activos","Active modules"] }
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
    if (/^[a-f0-9-]{20,}$/i.test(raw)) return true;
    if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return true;
    if (/^\d{1,2}:\d{2}/.test(raw)) return true;
    return false;
  }

  function translateText(value) {
    const raw = String(value || "");
    const clean = raw.replace(/\s+/g, " ").trim();

    const companyHelp = clean.match(/^(.+?)\s+administra su personal de forma independiente\.$/i);
    if (companyHelp) {
      return raw.replace(clean, `${companyHelp[1]} ${t("companyPersonalHelp").replace(/^Esta empresa\s+/i, "").replace(/^This company\s+/i, "manages").replace(/^Cette entreprise\s+/i, "gère")}`);
    }

    const key = ALIASES[norm(clean)];
    if (key) return raw.replace(clean, t(key));

    if (shouldSkipText(clean)) return raw;

    return raw;
  }

  function isPersonalVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector("#personalGrid")) return true;
    if (app.querySelector("[data-personal-add-row]")) return true;
    if (app.querySelector("[data-personal-save-all]")) return true;
    if (app.querySelector("[data-personal-history]")) return true;
    if (app.querySelector("[data-personal-search]")) return true;
    if (app.querySelector("[data-personal-history-from]")) return true;
    if (app.querySelector("[data-personal-history-to]")) return true;
    if (app.querySelector("[data-personal-history-search]")) return true;
    if (app.querySelector(".personal-history-grid")) return true;
    if (app.querySelector(".personal-history-toolbar")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Modulo Workforce") ||
      text.includes("Módulo Workforce") ||
      text.includes("Workforce module") ||
      text.includes("Registro de personal operativo") ||
      text.includes("Operational staff record") ||
      text.includes("Buscar historial") ||
      text.includes("Search history")
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

  function translatePersonal() {
    try {
      if (!isPersonalVisible()) return;

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
    timer = setTimeout(translatePersonal, 100);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translatePersonal();
      if (count >= 20) clearInterval(id);
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
    if (isPersonalVisible()) translatePersonal();
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

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_workforce_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

payroll_matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_payroll_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if payroll_matches:
    last = payroll_matches[-1]
    src = last.group(1)
    safe_src = re.sub(r'client_payroll_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_workforce_i18n_safe.js?v=020NR1', src)
    html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
else:
    materials_matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client_materials_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE,
    ))
    if materials_matches:
        last = materials_matches[-1]
        src = last.group(1)
        safe_src = re.sub(r'client_materials_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_workforce_i18n_safe.js?v=020NR1', src)
        html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/client-static/client_workforce_i18n_safe.js?v=020NR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020N-R1 safe external Workforce i18n super dictionary added")
