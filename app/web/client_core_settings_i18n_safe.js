
(function clonexaCoreSettingsI18n020OR1() {
  "use strict";

  if (window.__CLONEXA_020O_R1_CORE_SETTINGS_I18N__) return;
  window.__CLONEXA_020O_R1_CORE_SETTINGS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const ENTRIES = {
    eyebrow: {
      es: "Ajustes del núcleo",
      en: "Core settings",
      fr: "Configuration du noyau",
      aliases: ["CORE SETTINGS", "Core settings", "Ajustes del núcleo", "Ajustes del nucleo"]
    },
    title: {
      es: "Ajustes",
      en: "Settings",
      fr: "Configuration",
      aliases: ["Ajustes", "Settings", "Configuration"]
    },
    subtitle: {
      es: "Configuración núcleo del portal cliente para esta empresa.",
      en: "Core configuration for this company client portal.",
      fr: "Configuration du noyau du portail client pour cette entreprise.",
      aliases: [
        "Configuración núcleo del portal cliente para esta empresa.",
        "Configuracion nucleo del portal cliente para esta empresa.",
        "Core configuration for this company client portal."
      ]
    },

    panelPreferences: {
      es: "Preferencias del panel",
      en: "Panel preferences",
      fr: "Préférences du panneau",
      aliases: ["Preferencias del panel", "Panel preferences"]
    },
    language: {
      es: "Idioma",
      en: "Language",
      fr: "Langue",
      aliases: ["IDIOMA", "Idioma", "Language"]
    },
    inactivityLock: {
      es: "Bloqueo por inactividad",
      en: "Inactivity lock",
      fr: "Verrouillage par inactivité",
      aliases: ["BLOQUEO POR INACTIVIDAD", "Bloqueo por inactividad", "Inactivity lock"]
    },
    currency: {
      es: "Moneda",
      en: "Currency",
      fr: "Devise",
      aliases: ["MONEDA", "Moneda", "Currency"]
    },
    detectedTimezone: {
      es: "Zona horaria detectada",
      en: "Detected time zone",
      fr: "Fuseau horaire détecté",
      aliases: ["ZONA HORARIA DETECTADA", "Zona horaria detectada", "Detected time zone"]
    },
    saveSettings: {
      es: "Guardar ajustes",
      en: "Save settings",
      fr: "Enregistrer les paramètres",
      aliases: ["Guardar ajustes", "Save settings"]
    },

    changeEmail: {
      es: "Cambiar correo",
      en: "Change email",
      fr: "Changer l’e-mail",
      aliases: ["Cambiar correo", "Change email"]
    },
    newEmail: {
      es: "Nuevo correo",
      en: "New email",
      fr: "Nouvel e-mail",
      aliases: ["NUEVO CORREO", "Nuevo correo", "New email"]
    },
    currentPassword: {
      es: "Contraseña actual",
      en: "Current password",
      fr: "Mot de passe actuel",
      aliases: ["CONTRASEÑA ACTUAL", "Contraseña actual", "Current password"]
    },

    changePassword: {
      es: "Cambiar contraseña",
      en: "Change password",
      fr: "Changer le mot de passe",
      aliases: ["Cambiar contraseña", "Cambiar contrasena", "Change password"]
    },
    newPassword: {
      es: "Nueva contraseña",
      en: "New password",
      fr: "Nouveau mot de passe",
      aliases: ["NUEVA CONTRASEÑA", "Nueva contraseña", "Nueva contrasena", "New password"]
    },
    confirmNewPassword: {
      es: "Confirmar nueva contraseña",
      en: "Confirm new password",
      fr: "Confirmer le nouveau mot de passe",
      aliases: ["CONFIRMAR NUEVA CONTRASEÑA", "Confirmar nueva contraseña", "Confirmar nueva contrasena", "Confirm new password"]
    },

    session: {
      es: "Sesión",
      en: "Session",
      fr: "Session",
      aliases: ["Sesión", "Sesion", "Session"]
    },
    sessionHelp: {
      es: "El cierre por inactividad se aplica en este navegador según el tiempo configurado. El botón Cerrar sesión limpia la sesión local y regresa al login.",
      en: "Inactivity logout applies in this browser according to the configured time. The Log out button clears the local session and returns to login.",
      fr: "La déconnexion par inactivité s’applique dans ce navigateur selon le temps configuré. Le bouton Quitter efface la session locale et revient à la connexion.",
      aliases: [
        "El cierre por inactividad se aplica en este navegador según el tiempo configurado. El botón Cerrar sesión limpia la sesión local y regresa al login.",
        "El cierre por inactividad se aplica en este navegador segun el tiempo configurado. El boton Cerrar sesion limpia la sesion local y regresa al login.",
        "Inactivity logout applies in this browser according to the configured time. The Log out button clears the local session and returns to login."
      ]
    },
    logout: {
      es: "Cerrar sesión",
      en: "Log out",
      fr: "Quitter",
      aliases: ["Cerrar sesión", "Cerrar sesion", "Log out", "Quitter"]
    },

    spanish: {
      es: "Español",
      en: "Spanish",
      fr: "Espagnol",
      aliases: ["Español", "Espanol", "Spanish", "Espagnol"]
    },
    english: {
      es: "English",
      en: "English",
      fr: "Anglais",
      aliases: ["English", "Inglés", "Ingles", "Anglais"]
    },
    french: {
      es: "Français",
      en: "French",
      fr: "Français",
      aliases: ["Français", "Francais", "French", "Francés", "Frances"]
    },

    fifteenMinutes: {
      es: "15 minutos",
      en: "15 minutes",
      fr: "15 minutes",
      aliases: ["15 minutos", "15 minutes"]
    },
    thirtyMinutes: {
      es: "30 minutos",
      en: "30 minutes",
      fr: "30 minutes",
      aliases: ["30 minutos", "30 minutes"]
    },
    sixtyMinutes: {
      es: "60 minutos",
      en: "60 minutes",
      fr: "60 minutes",
      aliases: ["60 minutos", "60 minutes"]
    },

    emailPlaceholder: {
      es: "nuevo@empresa.com",
      en: "new@company.com",
      fr: "nouveau@entreprise.com",
      aliases: ["nuevo@empresa.com", "new@company.com", "nouveau@entreprise.com"]
    },

    settingsSaved: {
      es: "Ajustes guardados.",
      en: "Settings saved.",
      fr: "Paramètres enregistrés.",
      aliases: ["Ajustes guardados.", "Settings saved."]
    },
    emailUpdated: {
      es: "Correo actualizado.",
      en: "Email updated.",
      fr: "E-mail mis à jour.",
      aliases: ["Correo actualizado.", "Email updated."]
    },
    passwordUpdated: {
      es: "Contraseña actualizada.",
      en: "Password updated.",
      fr: "Mot de passe mis à jour.",
      aliases: ["Contraseña actualizada.", "Contrasena actualizada.", "Password updated."]
    },
    passwordMismatch: {
      es: "Las contraseñas no coinciden.",
      en: "Passwords do not match.",
      fr: "Les mots de passe ne correspondent pas.",
      aliases: ["Las contraseñas no coinciden.", "Las contrasenas no coinciden.", "Passwords do not match."]
    },
    currentPasswordRequired: {
      es: "La contraseña actual es obligatoria.",
      en: "Current password is required.",
      fr: "Le mot de passe actuel est obligatoire.",
      aliases: ["La contraseña actual es obligatoria.", "La contrasena actual es obligatoria.", "Current password is required."]
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

  function currentLanguageFromModal(root) {
    if (!root) return null;

    const selects = Array.from(root.querySelectorAll("select"));
    for (const select of selects) {
      const optionsText = Array.from(select.options || []).map((o) => `${o.value} ${o.textContent}`).join(" ").toLowerCase();
      const selectedText = String(select.selectedOptions && select.selectedOptions[0] ? select.selectedOptions[0].textContent : "").toLowerCase();
      const value = String(select.value || "").toLowerCase();

      if (["es", "en", "fr"].includes(value)) return value;

      if (
        optionsText.includes("español") ||
        optionsText.includes("espanol") ||
        optionsText.includes("english") ||
        optionsText.includes("français") ||
        optionsText.includes("francais") ||
        optionsText.includes("spanish") ||
        optionsText.includes("french")
      ) {
        if (selectedText.includes("english") || selectedText.includes("inglés") || selectedText.includes("ingles")) return "en";
        if (selectedText.includes("français") || selectedText.includes("francais") || selectedText.includes("french") || selectedText.includes("francés") || selectedText.includes("frances")) return "fr";
        if (selectedText.includes("español") || selectedText.includes("espanol") || selectedText.includes("spanish")) return "es";
      }
    }

    return null;
  }

  function lang(root) {
    const modalLang = currentLanguageFromModal(root);
    if (modalLang) return modalLang;

    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function t(key, root) {
    const entry = ENTRIES[key];
    const l = lang(root);
    return entry ? entry[l] || entry.es || key : key;
  }

  function findSettingsRoot() {
    const selectors = [
      "#clxCoreSettingsModal",
      "#coreSettingsModal",
      "[data-core-settings]",
      "[data-clx-core-settings]",
      "[role='dialog']",
      "dialog",
      ".modal",
      ".clx-modal",
      ".settings-modal",
      "section",
      "div"
    ];

    const nodes = [];

    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => {
        if (!node || nodes.includes(node)) return;
        const rect = node.getBoundingClientRect();
        if (rect.width < 360 || rect.height < 240) return;

        const text = node.textContent || "";
        const isSettings =
          text.includes("CORE SETTINGS") ||
          text.includes("Core settings") ||
          text.includes("Ajustes") ||
          text.includes("Preferencias del panel") ||
          text.includes("Cambiar correo") ||
          text.includes("Cambiar contraseña") ||
          text.includes("Panel preferences") ||
          text.includes("Change email") ||
          text.includes("Change password");

        if (!isSettings) return;

        nodes.push(node);
      });
    });

    if (!nodes.length) return null;

    nodes.sort((a, b) => {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      return (ar.width * ar.height) - (br.width * br.height);
    });

    return nodes[0];
  }

  function skipElement(el) {
    if (!el || !el.tagName) return true;
    const tag = el.tagName.toLowerCase();
    if (["script", "style", "code", "pre"].includes(tag)) return true;
    if (el.closest && el.closest("[data-clx-no-i18n]")) return true;
    return false;
  }

  function shouldSkipText(value) {
    const raw = String(value || "").trim();
    if (!raw) return true;
    if (/^[\d\s.,:$%#@/_-]+$/.test(raw)) return true;
    if (/^[A-Z]{2,4}$/.test(raw) && !ALIASES[norm(raw)]) return true;
    if (raw.includes("@") && !ALIASES[norm(raw)]) return true;
    return false;
  }

  function translateText(value, root) {
    const raw = String(value || "");
    const clean = raw.replace(/\s+/g, " ").trim();

    const key = ALIASES[norm(clean)];
    if (key) return raw.replace(clean, t(key, root));

    if (shouldSkipText(clean)) return raw;

    return raw;
  }

  function translateSelectOptions(root) {
    root.querySelectorAll("select").forEach((select) => {
      Array.from(select.options || []).forEach((option) => {
        const current = option.textContent || "";
        const next = translateText(current, root);
        if (next !== current) option.textContent = next;
      });
    });
  }

  function translateAttributes(root) {
    root.querySelectorAll("[placeholder], [title], [aria-label], input[type='button'], input[type='submit']").forEach((el) => {
      if (skipElement(el)) return;

      ["placeholder", "title", "aria-label"].forEach((attr) => {
        if (!el.hasAttribute(attr)) return;
        const current = el.getAttribute(attr);
        const next = translateText(current, root);
        if (next !== current) el.setAttribute(attr, next);
      });

      if (el.matches("input[type='button'], input[type='submit']")) {
        const next = translateText(el.value, root);
        if (next !== el.value) el.value = next;
      }
    });
  }

  function translateSettings() {
    try {
      const root = findSettingsRoot();
      if (!root) return;

      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || skipElement(parent)) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      });

      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);

      nodes.forEach((node) => {
        const next = translateText(node.nodeValue, root);
        if (next !== node.nodeValue) node.nodeValue = next;
      });

      translateAttributes(root);
      translateSelectOptions(root);

      document.documentElement.lang = lang(root);
    } catch (error) {
      console.warn("CLONEXA Core Settings i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateSettings, 80);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateSettings();
      if (count >= 20) clearInterval(id);
    }, 150);
  }

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 250);
    setTimeout(schedule, 650);
    setTimeout(schedule, 1200);
    setTimeout(schedule, 2000);
  }, true);

  document.addEventListener("change", () => {
    schedule();
    setTimeout(schedule, 300);
    setTimeout(schedule, 900);
  }, true);

  document.addEventListener("input", schedule, true);
  document.addEventListener("keydown", schedule, true);

  const observer = new MutationObserver(schedule);

  function init() {
    try {
      if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
      }

      schedule();
      burst();

      setInterval(() => {
        if (findSettingsRoot()) translateSettings();
      }, 1200);
    } catch (error) {
      console.warn("CLONEXA Core Settings i18n init skipped:", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
