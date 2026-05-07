from pathlib import Path

path = Path("app/web/client.js")
text = path.read_text(encoding="utf-8-sig")

marker = "/* CLONEXA 020A-2 CLIENT GLOBAL I18N + BRANDING BINDING */"

if marker in text:
    print("OK: 020A-2 ya existe en client.js")
    raise SystemExit(0)

append = r'''

/* CLONEXA 020A-2 CLIENT GLOBAL I18N + BRANDING BINDING */
(function clonexaClientGlobalI18nBranding() {
  "use strict";

  const STORAGE_LANG = "clonexa_client_language";

  const DICT = {
    es: {
      settings: "Configuración",
      logout: "Salir",
      close: "Cerrar",
      save: "Guardar",
      saveChanges: "Guardar cambios",
      cancel: "Cancelar",
      search: "Buscar",
      status: "Estado",
      company: "Empresa",
      dashboard: "Dashboard",
      active: "Activo",
      inactive: "Inactivo",
      archived: "Archivado",
      actions: "Acciones",
      name: "Nombre",
      fullName: "Nombre completo",
      role: "Rol",
      phone: "Teléfono",
      email: "Correo",
      telegramId: "Telegram ID",
      hireDate: "Fecha ingreso",
      regularHour: "Hora ordinaria",
      extraHour: "Hora extra",
      discount1: "Descuento 1",
      discount2: "Descuento 2",
      activate: "Activar",
      deactivate: "Inactivar",
      delete: "Eliminar",
      addStaff: "Agregar personal",
      seeBot: "Ver bot",
      seeCrm: "Ver CRM",
      seePayroll: "Ver nómina",
      inventory: "Inventario",
      seeKpis: "Ver KPIs",
      seeReports: "Ver reportes",
      seeOperation: "Ver operación",
      activeStaff: "Personal activo",
      channels: "Canales",
      reports: "Reportes",
      sales: "Ventas",
      stores: "Tiendas",
      activeModules: "Módulos activos",
      modules: "Módulos",
      live: "LIVE",
      core: "Core",
      coreDesc: "base operativa",
      workforce: "Personal",
      workforceDesc: "personal operativo",
      fieldOps: "Campo",
      fieldOpsDesc: "operación en campo",
      technicians: "Técnicos",
      techniciansDesc: "inicio turno y estados",
      gps: "GPS",
      gpsDesc: "ubicación y rutas",
      tasks: "Tareas / Solicitudes",
      tasksDesc: "solicitudes operativas",
      requests: "Solicitudes",
      requestsDesc: "flujo de aprobación",
      materials: "Materiales",
      materialsDesc: "solicitud y devolución",
      payroll: "Nómina",
      payrollDesc: "corte y cálculo",
      payrollBiweekly: "Nómina Quincenal",
      currentCut: "corte actual",
      billing: "Facturación",
      billingDesc: "cobros y facturación",
      reportsDesc: "métricas y auditoría",
      kpis: "KPIs",
      kpisDesc: "indicadores operativos",
      crmField: "CRM Campo",
      crmDesc: "operación en vivo",
      tenantSettings: "ajustes del tenant",
      production: "Producción",
      productionDesc: "referencias y costos",
      retail: "Retail",
      retailDesc: "tiendas y ventas",
      salesDesc: "actividad comercial",
      storesDesc: "puntos de venta",
      hospitality: "Hospitality",
      hospitalityDesc: "pedidos e inventario",
      bots: "Bots",
      botsDesc: "Telegram / WhatsApp",
      noHistory: "No hay registros de historial para los filtros seleccionados.",
      accountSettings: "Configuración de cuenta",
      firstLogin: "Primer ingreso: cambia tu contraseña",
      account: "Cuenta",
      newEmail: "Nuevo correo",
      currentPassword: "Contraseña actual",
      newPassword: "Nueva contraseña",
      confirmPassword: "Confirmar contraseña",
      language: "Idioma",
      session: "Sesión",
      timeout: "Tiempo de ventana abierta",
      saved: "Configuración guardada.",
      passwordRequired: "Debes cambiar la contraseña para continuar.",
      sessionExpired: "Sesión expirada por inactividad.",
      clientPanel: "Panel cliente CLONEXA",
      passwordHelp: "Deja nueva contraseña vacía si no deseas cambiarla.",
      emailHelp: "Deja nuevo correo vacío si no deseas cambiarlo."
    },
    en: {
      settings: "Settings",
      logout: "Log out",
      close: "Close",
      save: "Save",
      saveChanges: "Save changes",
      cancel: "Cancel",
      search: "Search",
      status: "Status",
      company: "Company",
      dashboard: "Dashboard",
      active: "Active",
      inactive: "Inactive",
      archived: "Archived",
      actions: "Actions",
      name: "Name",
      fullName: "Full name",
      role: "Role",
      phone: "Phone",
      email: "Email",
      telegramId: "Telegram ID",
      hireDate: "Hire date",
      regularHour: "Regular hour",
      extraHour: "Extra hour",
      discount1: "Discount 1",
      discount2: "Discount 2",
      activate: "Activate",
      deactivate: "Deactivate",
      delete: "Delete",
      addStaff: "Add staff",
      seeBot: "View bot",
      seeCrm: "View CRM",
      seePayroll: "View payroll",
      inventory: "Inventory",
      seeKpis: "View KPIs",
      seeReports: "View reports",
      seeOperation: "View operation",
      activeStaff: "Active staff",
      channels: "Channels",
      reports: "Reports",
      sales: "Sales",
      stores: "Stores",
      activeModules: "Active modules",
      modules: "Modules",
      live: "LIVE",
      core: "Core",
      coreDesc: "operational base",
      workforce: "Staff",
      workforceDesc: "operational staff",
      fieldOps: "Field Ops",
      fieldOpsDesc: "field operation",
      technicians: "Technicians",
      techniciansDesc: "shift start and status",
      gps: "GPS",
      gpsDesc: "location and routes",
      tasks: "Tasks / Requests",
      tasksDesc: "operational requests",
      requests: "Requests",
      requestsDesc: "approval flow",
      materials: "Materials",
      materialsDesc: "request and return",
      payroll: "Payroll",
      payrollDesc: "cutoff and calculation",
      payrollBiweekly: "Biweekly Payroll",
      currentCut: "current cutoff",
      billing: "Billing",
      billingDesc: "charges and invoicing",
      reportsDesc: "metrics and audit",
      kpis: "KPIs",
      kpisDesc: "operational indicators",
      crmField: "Field CRM",
      crmDesc: "live operation",
      tenantSettings: "tenant settings",
      production: "Production",
      productionDesc: "references and costs",
      retail: "Retail",
      retailDesc: "stores and sales",
      salesDesc: "commercial activity",
      storesDesc: "points of sale",
      hospitality: "Hospitality",
      hospitalityDesc: "orders and inventory",
      bots: "Bots",
      botsDesc: "Telegram / WhatsApp",
      noHistory: "No history records match the selected filters.",
      accountSettings: "Account settings",
      firstLogin: "First login: change your password",
      account: "Account",
      newEmail: "New email",
      currentPassword: "Current password",
      newPassword: "New password",
      confirmPassword: "Confirm password",
      language: "Language",
      session: "Session",
      timeout: "Open session window",
      saved: "Settings saved.",
      passwordRequired: "You must change your password to continue.",
      sessionExpired: "Session expired due to inactivity.",
      clientPanel: "CLONEXA client panel",
      passwordHelp: "Leave new password empty if you do not want to change it.",
      emailHelp: "Leave new email empty if you do not want to change it."
    },
    fr: {
      settings: "Configuration",
      logout: "Quitter",
      close: "Fermer",
      save: "Enregistrer",
      saveChanges: "Enregistrer",
      cancel: "Annuler",
      search: "Rechercher",
      status: "Statut",
      company: "Entreprise",
      dashboard: "Tableau de bord",
      active: "Actif",
      inactive: "Inactif",
      archived: "Archivé",
      actions: "Actions",
      name: "Nom",
      fullName: "Nom complet",
      role: "Rôle",
      phone: "Téléphone",
      email: "E-mail",
      telegramId: "Telegram ID",
      hireDate: "Date d’entrée",
      regularHour: "Heure normale",
      extraHour: "Heure supplémentaire",
      discount1: "Remise 1",
      discount2: "Remise 2",
      activate: "Activer",
      deactivate: "Désactiver",
      delete: "Supprimer",
      addStaff: "Ajouter du personnel",
      seeBot: "Voir le bot",
      seeCrm: "Voir CRM",
      seePayroll: "Voir paie",
      inventory: "Inventaire",
      seeKpis: "Voir KPIs",
      seeReports: "Voir rapports",
      seeOperation: "Voir opération",
      activeStaff: "Personnel actif",
      channels: "Canaux",
      reports: "Rapports",
      sales: "Ventes",
      stores: "Magasins",
      activeModules: "Modules actifs",
      modules: "Modules",
      live: "LIVE",
      core: "Core",
      coreDesc: "base opérationnelle",
      workforce: "Personnel",
      workforceDesc: "personnel opérationnel",
      fieldOps: "Terrain",
      fieldOpsDesc: "opération terrain",
      technicians: "Techniciens",
      techniciansDesc: "début de service et états",
      gps: "GPS",
      gpsDesc: "localisation et itinéraires",
      tasks: "Tâches / Demandes",
      tasksDesc: "demandes opérationnelles",
      requests: "Demandes",
      requestsDesc: "flux d’approbation",
      materials: "Matériaux",
      materialsDesc: "demande et retour",
      payroll: "Paie",
      payrollDesc: "coupe et calcul",
      payrollBiweekly: "Paie bimensuelle",
      currentCut: "coupe actuelle",
      billing: "Facturation",
      billingDesc: "encaissements et facturation",
      reportsDesc: "métriques et audit",
      kpis: "KPIs",
      kpisDesc: "indicateurs opérationnels",
      crmField: "CRM Terrain",
      crmDesc: "opération en direct",
      tenantSettings: "paramètres du tenant",
      production: "Production",
      productionDesc: "références et coûts",
      retail: "Retail",
      retailDesc: "magasins et ventes",
      salesDesc: "activité commerciale",
      storesDesc: "points de vente",
      hospitality: "Hospitality",
      hospitalityDesc: "commandes et inventaire",
      bots: "Bots",
      botsDesc: "Telegram / WhatsApp",
      noHistory: "Aucun historique ne correspond aux filtres sélectionnés.",
      accountSettings: "Configuration du compte",
      firstLogin: "Première connexion : changez votre mot de passe",
      account: "Compte",
      newEmail: "Nouvel e-mail",
      currentPassword: "Mot de passe actuel",
      newPassword: "Nouveau mot de passe",
      confirmPassword: "Confirmer le mot de passe",
      language: "Langue",
      session: "Session",
      timeout: "Fenêtre de session ouverte",
      saved: "Configuration enregistrée.",
      passwordRequired: "Vous devez changer votre mot de passe pour continuer.",
      sessionExpired: "Session expirée pour inactivité.",
      clientPanel: "Panneau client CLONEXA",
      passwordHelp: "Laissez le nouveau mot de passe vide si vous ne souhaitez pas le changer.",
      emailHelp: "Laissez le nouvel e-mail vide si vous ne souhaitez pas le changer."
    }
  };

  const PHRASE_TO_KEY = {};
  Object.keys(DICT).forEach((lang) => {
    Object.keys(DICT[lang]).forEach((key) => {
      PHRASE_TO_KEY[String(DICT[lang][key]).trim()] = key;
    });
  });

  [
    ["Configuracion", "settings"],
    ["Dashboard", "dashboard"],
    ["Personal", "workforce"],
    ["Workforce", "workforce"],
    ["Inventario", "inventory"],
    ["Materiales", "materials"],
    ["Reportes", "reports"],
    ["Nomina", "payroll"],
    ["Nómina", "payroll"],
    ["Produccion", "production"],
    ["Producción", "production"],
    ["GPS", "gps"],
    ["CRM Campo", "crmField"],
    ["KPIs", "kpis"],
    ["Guardar", "save"],
    ["Cancelar", "cancel"],
    ["Buscar", "search"],
    ["Estado", "status"],
    ["Empresa", "company"],
    ["Acciones", "actions"],
    ["Correo", "email"],
    ["Telefono", "phone"],
    ["Teléfono", "phone"],
    ["Eliminar", "delete"],
    ["Activar", "activate"],
    ["Inactivar", "deactivate"]
  ].forEach(([phrase, key]) => {
    PHRASE_TO_KEY[phrase] = key;
  });

  function currentLang() {
    const stored = String(localStorage.getItem(STORAGE_LANG) || document.documentElement.lang || "es").toLowerCase();
    return ["es", "en", "fr"].includes(stored) ? stored : "es";
  }

  function t(key) {
    const lang = currentLang();
    return (DICT[lang] && DICT[lang][key]) || DICT.es[key] || key;
  }

  function translateString(value) {
    if (typeof value !== "string") return value;

    const raw = value;
    const trimmed = raw.trim();

    if (!trimmed) return raw;
    if (/^[\d\s.,:$%#@/_-]+$/.test(trimmed)) return raw;
    if (/^[a-f0-9-]{24,}$/i.test(trimmed)) return raw;

    const key = PHRASE_TO_KEY[trimmed];
    if (!key) return raw;

    const translated = t(key);
    return raw.replace(trimmed, translated);
  }

  function shouldSkipElement(el) {
    if (!el || !el.tagName) return false;

    const tag = el.tagName.toLowerCase();

    if (["script", "style", "code", "pre", "textarea"].includes(tag)) return true;
    if (el.closest && el.closest("[data-clx-no-i18n]")) return true;

    return false;
  }

  function translateNode(root) {
    const target = root || document.body;
    if (!target) return;

    if (target.nodeType === Node.TEXT_NODE) {
      const next = translateString(target.nodeValue || "");
      if (next !== target.nodeValue) target.nodeValue = next;
      return;
    }

    if (target.nodeType !== Node.ELEMENT_NODE && target.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;

    const element = target.nodeType === Node.ELEMENT_NODE ? target : null;

    if (element && shouldSkipElement(element)) return;

    if (element) {
      ["placeholder", "title", "aria-label"].forEach((attr) => {
        if (element.hasAttribute && element.hasAttribute(attr)) {
          const current = element.getAttribute(attr);
          const next = translateString(current || "");
          if (next !== current) element.setAttribute(attr, next);
        }
      });

      if (
        element.tagName &&
        element.tagName.toLowerCase() === "input" &&
        ["button", "submit", "reset"].includes(String(element.type || "").toLowerCase())
      ) {
        element.value = translateString(element.value || "");
      }
    }

    const walker = document.createTreeWalker(
      target,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || shouldSkipElement(parent)) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    textNodes.forEach((node) => {
      const next = translateString(node.nodeValue || "");
      if (next !== node.nodeValue) node.nodeValue = next;
    });

    if (target.querySelectorAll) {
      target.querySelectorAll("[placeholder], [title], [aria-label], input[type='button'], input[type='submit']").forEach((el) => {
        if (shouldSkipElement(el)) return;

        ["placeholder", "title", "aria-label"].forEach((attr) => {
          if (el.hasAttribute(attr)) {
            const current = el.getAttribute(attr);
            const next = translateString(current || "");
            if (next !== current) el.setAttribute(attr, next);
          }
        });

        if (el.matches("input[type='button'], input[type='submit']")) {
          el.value = translateString(el.value || "");
        }
      });
    }

    document.documentElement.lang = currentLang();
  }

  function installBrandingOverrides() {
    let style = document.getElementById("clx-i18n-branding-overrides");
    if (!style) {
      style = document.createElement("style");
      style.id = "clx-i18n-branding-overrides";
      document.head.appendChild(style);
    }

    style.textContent = `
      .clx-account-bar {
        top: 16px !important;
        right: 16px !important;
      }

      .clx-account-pill,
      .clx-account-pill.secondary {
        background: linear-gradient(135deg, var(--cx-secondary, #00ff88), var(--cx-primary, #ff2bd6)) !important;
        color: #020617 !important;
        border: 1px solid rgba(255,255,255,.28) !important;
        box-shadow: 0 0 34px color-mix(in srgb, var(--cx-primary, #ff2bd6) 45%, transparent), 0 18px 44px rgba(0,0,0,.28) !important;
        font-weight: 1000 !important;
      }

      .clx-account-overlay {
        background:
          radial-gradient(circle at 0% 0%, color-mix(in srgb, var(--cx-primary, #ff2bd6) 34%, transparent), transparent 34%),
          radial-gradient(circle at 100% 0%, color-mix(in srgb, var(--cx-secondary, #00ff88) 28%, transparent), transparent 34%),
          rgba(2, 6, 23, .76) !important;
      }

      .clx-account-modal {
        background:
          linear-gradient(145deg, rgba(255,255,255,.12), rgba(255,255,255,.06)),
          var(--cx-bg, #050509) !important;
        color: var(--cx-text, #f8fafc) !important;
        border: 1px solid color-mix(in srgb, var(--cx-primary, #ff2bd6) 44%, rgba(255,255,255,.12)) !important;
        box-shadow: 0 0 52px color-mix(in srgb, var(--cx-primary, #ff2bd6) 30%, transparent), 0 32px 90px rgba(0,0,0,.48) !important;
        backdrop-filter: blur(24px) saturate(1.25) !important;
      }

      .clx-account-section {
        background: rgba(255,255,255,.055) !important;
        border-color: rgba(255,255,255,.14) !important;
      }

      .clx-account-muted {
        color: color-mix(in srgb, var(--cx-text, #f8fafc) 72%, transparent) !important;
      }

      .clx-account-grid input,
      .clx-account-grid select {
        background: rgba(0,0,0,.24) !important;
        color: var(--cx-text, #f8fafc) !important;
        border-color: rgba(255,255,255,.16) !important;
      }

      .clx-account-grid select option {
        color: #020617 !important;
      }

      .clx-account-btn.primary {
        background: linear-gradient(135deg, var(--cx-secondary, #00ff88), var(--cx-primary, #ff2bd6)) !important;
        color: #020617 !important;
        box-shadow: 0 0 30px color-mix(in srgb, var(--cx-primary, #ff2bd6) 40%, transparent) !important;
      }

      .clx-account-btn.ghost {
        background: rgba(255,255,255,.09) !important;
        color: var(--cx-text, #f8fafc) !important;
        border: 1px solid rgba(255,255,255,.14) !important;
      }
    `;
  }

  let translateTimer = null;

  function scheduleTranslate() {
    if (translateTimer) clearTimeout(translateTimer);
    translateTimer = setTimeout(() => {
      installBrandingOverrides();
      translateNode(document.body);
    }, 80);
  }

  function setLanguage(lang) {
    if (!["es", "en", "fr"].includes(lang)) return;
    localStorage.setItem(STORAGE_LANG, lang);
    document.documentElement.lang = lang;
    scheduleTranslate();
  }

  window.CLX_I18N = {
    t,
    translate: () => translateNode(document.body),
    setLanguage,
    lang: currentLang,
    dict: DICT
  };

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!target) return;

    if (target.id === "clxAccountLanguage") {
      setLanguage(String(target.value || "es").toLowerCase());
    }
  }, true);

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!target) return;

    if (target.id === "clxAccountSaveBtn") {
      setTimeout(() => {
        const select = document.getElementById("clxAccountLanguage");
        if (select && select.value) setLanguage(String(select.value).toLowerCase());
        scheduleTranslate();
      }, 350);
    }
  }, true);

  const observer = new MutationObserver((mutations) => {
    if (!mutations.length) return;
    scheduleTranslate();
  });

  function init() {
    installBrandingOverrides();
    translateNode(document.body);

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label", "value"]
    });

    scheduleTranslate();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
'''

text += append
path.write_text(text, encoding="utf-8")

print("PATCH_OK: 020A-2 global i18n + branding binding appended")
