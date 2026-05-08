from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_workforce_history_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaWorkforceHistoryRepair020NR3() {
  "use strict";

  if (window.__CLONEXA_020N_R3_WORKFORCE_HISTORY_REPAIR__) return;
  window.__CLONEXA_020N_R3_WORKFORCE_HISTORY_REPAIR__ = true;

  const LANG_KEY = "clonexa_client_language";

  const ENTRIES = {
    attendance: {
      es: "Asistencia",
      en: "Attendance",
      fr: "Assistance",
      aliases: ["Asistencia", "Attendance", "Assistance"]
    },

    staffHistorySubtitle: {
      es: "Consulta registros, ediciones, activaciones, inactivaciones y archivados por rango de fechas.",
      en: "Review records, edits, activations, inactivations and archived staff by date range.",
      fr: "Consultez les enregistrements, modifications, activations, désactivations et archivages par plage de dates.",
      aliases: [
        "Consulta registros, ediciones, activaciones, inactivaciones y archivados por rango de fechas.",
        "Review records, edits, activations, inactivations and archived staff by date range."
      ]
    },

    historyFilterHelp: {
      es: "Usa estos filtros para validar datos de 15, 20, 30 días o cualquier rango operativo.",
      en: "Use these filters to validate data for 15, 20, 30 days or any operational range.",
      fr: "Utilisez ces filtres pour valider les données sur 15, 20, 30 jours ou toute plage opérationnelle.",
      aliases: [
        "Usa estos filtros para validar datos de 15, 20, 30 días o cualquier rango operativo.",
        "Usa estos filtros para validar datos de 15, 20, 30 dias o cualquier rango operativo.",
        "Use these filters to validate data for 15, 20, 30 days or any operational range."
      ]
    },

    historySearchPlaceholder: {
      es: "Empleado, evento, rol, estado...",
      en: "Employee, event, role, status...",
      fr: "Employé, événement, rôle, statut...",
      aliases: [
        "Empleado, evento, rol, estado...",
        "Employee, event, role, status..."
      ]
    },

    registerField: {
      es: "Registro",
      en: "Record",
      fr: "Enregistrement",
      aliases: ["Registro", "Record", "Enregistrement"]
    },

    clientSource: {
      es: "cliente",
      en: "Client",
      fr: "Client",
      aliases: ["client", "cliente", "Client"]
    },

    archivedFrom: {
      es: "Archivado desde Workforce / Personal.",
      en: "Archived from Workforce / Staff.",
      fr: "Archivé depuis Workforce / Personnel.",
      aliases: ["Archivado desde Workforce / Personal.", "Archived from Workforce / Staff."]
    },

    activatedFrom: {
      es: "Activado desde Workforce / Personal.",
      en: "Activated from Workforce / Staff.",
      fr: "Activé depuis Workforce / Personnel.",
      aliases: ["Activado desde Workforce / Personal.", "Activated from Workforce / Staff."]
    },

    editedFrom: {
      es: "Editado desde Workforce / Personal.",
      en: "Edited from Workforce / Staff.",
      fr: "Modifié depuis Workforce / Personnel.",
      aliases: ["Editado desde Workforce / Personal.", "Edited from Workforce / Staff."]
    },

    inactivatedFrom: {
      es: "Inactivado desde Workforce / Personal.",
      en: "Inactivated from Workforce / Staff.",
      fr: "Désactivé depuis Workforce / Personnel.",
      aliases: ["Inactivado desde Workforce / Personal.", "Inactivated from Workforce / Staff."]
    },

    restoredFrom: {
      es: "Restaurado desde Workforce / Personal.",
      en: "Restored from Workforce / Staff.",
      fr: "Restauré depuis Workforce / Personnel.",
      aliases: ["Restaurado desde Workforce / Personal.", "Restored from Workforce / Staff."]
    },

    createdFrom: {
      es: "Creado desde Workforce / Personal.",
      en: "Created from Workforce / Staff.",
      fr: "Créé depuis Workforce / Personnel.",
      aliases: ["Creado desde Workforce / Personal.", "Created from Workforce / Staff."]
    },

    employeeActivatedValue: {
      es: "Empleado activado",
      en: "Employee activated",
      fr: "Employé activé",
      aliases: ["Empleado activado", "Employee activated"]
    },

    employeeArchivedValue: {
      es: "Empleado archivado",
      en: "Employee archived",
      fr: "Employé archivé",
      aliases: ["Empleado archivado", "Employee archived"]
    },

    employeeEditedValue: {
      es: "Empleado editado",
      en: "Employee edited",
      fr: "Employé modifié",
      aliases: ["Empleado editado", "Employee edited"]
    },

    employeeInactivatedValue: {
      es: "Empleado inactivado",
      en: "Employee inactivated",
      fr: "Employé désactivé",
      aliases: ["Empleado inactivado", "Employee inactivated"]
    },

    employeeRestoredValue: {
      es: "Empleado restaurado",
      en: "Employee restored",
      fr: "Employé restauré",
      aliases: ["Empleado restaurado", "Employee restored"]
    },

    previousActive: {
      es: "Activo",
      en: "Active",
      fr: "Actif",
      aliases: ["Activo", "Active", "Actif"]
    },

    previousArchived: {
      es: "Archivado",
      en: "Archived",
      fr: "Archivé",
      aliases: ["Archivado", "Archived", "Archivé"]
    },

    previousInactive: {
      es: "Inactivo",
      en: "Inactive",
      fr: "Inactif",
      aliases: ["Inactivo", "Inactive", "Inactif"]
    }
  };

  const ALIASES = {};

  function norm(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
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

  function t(key) {
    const entry = ENTRIES[key];
    return entry ? entry[lang()] || entry.es || key : key;
  }

  function shouldSkipText(value) {
    const raw = String(value || "").trim();
    if (!raw) return true;
    if (/^[\d\s.,:$%#@/_-]+$/.test(raw)) return true;
    if (/^[a-f0-9-]{20,}$/i.test(raw)) return true;
    if (raw.includes("@")) return true;
    return false;
  }

  function normalizeMeridiem(raw) {
    if (lang() !== "en") return raw;
    return raw
      .replace(/\ba\.\s*m\./gi, "AM")
      .replace(/\bp\.\s*m\./gi, "PM");
  }

  function translateKnownPhrases(raw) {
    let next = raw;

    const replacements = [
      ["Archivado desde Workforce / Personal.", t("archivedFrom")],
      ["Activado desde Workforce / Personal.", t("activatedFrom")],
      ["Editado desde Workforce / Personal.", t("editedFrom")],
      ["Inactivado desde Workforce / Personal.", t("inactivatedFrom")],
      ["Restaurado desde Workforce / Personal.", t("restoredFrom")],
      ["Creado desde Workforce / Personal.", t("createdFrom")],

      ["Consulta registros, ediciones, activaciones, inactivaciones y archivados por rango de fechas.", t("staffHistorySubtitle")],
      ["Usa estos filtros para validar datos de 15, 20, 30 días o cualquier rango operativo.", t("historyFilterHelp")],
      ["Usa estos filtros para validar datos de 15, 20, 30 dias o cualquier rango operativo.", t("historyFilterHelp")]
    ];

    replacements.forEach(([from, to]) => {
      next = next.split(from).join(to);
    });

    return next;
  }

  function translateText(value) {
    const raw = String(value || "");
    let next = normalizeMeridiem(raw);
    next = translateKnownPhrases(next);

    const clean = next.replace(/\s+/g, " ").trim();

    const key = ALIASES[norm(clean)];
    if (key) {
      return next.replace(clean, t(key));
    }

    if (shouldSkipText(clean)) return next;

    return next;
  }

  function isWorkforceHistoryVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector("[data-personal-history-from]")) return true;
    if (app.querySelector("[data-personal-history-to]")) return true;
    if (app.querySelector("[data-personal-history-search]")) return true;
    if (app.querySelector(".personal-history-grid")) return true;
    if (app.querySelector(".personal-history-toolbar")) return true;

    const text = app.textContent || "";

    return (
      text.includes("Staff history") ||
      text.includes("Historial de Personal") ||
      text.includes("Search history") ||
      text.includes("Operational audit") ||
      text.includes("Consulta registros") ||
      text.includes("Usa estos filtros") ||
      text.includes("Archivado desde Workforce") ||
      text.includes("Editado desde Workforce")
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

        if (norm(current) === norm("Empleado, evento, rol, estado...")) {
          next = t("historySearchPlaceholder");
        }

        if (next !== current) el.setAttribute(attr, next);
      });

      if (el.matches("input[type='button'], input[type='submit']")) {
        const next = translateText(el.value);
        if (next !== el.value) el.value = next;
      }
    });
  }

  function translateHistory() {
    try {
      if (!isWorkforceHistoryVisible()) return;

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
      if (settings) settings.textContent = "⚙ " + (lang() === "fr" ? "Configuration" : lang() === "en" ? "Settings" : "Ajustes");
      if (logout) logout.textContent = "⏻ " + (lang() === "fr" ? "Quitter" : lang() === "en" ? "Log out" : "Cerrar sesión");

      document.documentElement.lang = lang();
    } catch (error) {
      console.warn("CLONEXA Workforce History repair skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateHistory, 80);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateHistory();
      if (count >= 24) clearInterval(id);
    }, 150);
  }

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 250);
    setTimeout(schedule, 650);
    setTimeout(schedule, 1200);
    setTimeout(schedule, 2000);
  }, true);

  document.addEventListener("input", schedule, true);
  document.addEventListener("change", schedule, true);
  document.addEventListener("keydown", schedule, true);

  const observer = new MutationObserver(schedule);

  setInterval(() => {
    if (isWorkforceHistoryVisible()) translateHistory();
  }, 1000);

  function init() {
    try {
      if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
      }
      schedule();
      burst();
    } catch (error) {
      console.warn("CLONEXA Workforce History repair init skipped:", error);
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

# Quitar tag viejo R3 history si existe
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_workforce_history_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE
)

# Insertar justo después del i18n principal de Workforce
matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_workforce_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE
))

if matches:
    last = matches[-1]
    src = last.group(1)
    repair_src = re.sub(
        r'client_workforce_i18n_safe\.js(?:\?v=[^"\']*)?',
        'client_workforce_history_i18n_safe.js?v=020NR3',
        src
    )
    html = html[:last.end()] + f'\n<script src="{repair_src}"></script>\n' + html[last.end():]
else:
    html = html.replace("</body>", '<script src="/client-static/client_workforce_history_i18n_safe.js?v=020NR3"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020N-R3 Workforce history repair layer added")
