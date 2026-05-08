from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_core_settings_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaCoreSettingsI18n020OR2() {
  "use strict";

  if (window.__CLONEXA_020O_R2_CORE_SETTINGS_I18N__) return;
  window.__CLONEXA_020O_R2_CORE_SETTINGS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const TEXTS = {
    es: {
      eyebrow: "Ajustes del núcleo",
      title: "Ajustes",
      subtitle: "Configuración núcleo del portal cliente para esta empresa.",

      panelPreferences: "Preferencias del panel",
      language: "Idioma",
      inactivityLock: "Bloqueo por inactividad",
      currency: "Moneda",
      detectedTimezone: "Zona horaria detectada",
      saveSettings: "Guardar ajustes",

      changeEmail: "Cambiar correo",
      newEmail: "Nuevo correo",
      currentPassword: "Contraseña actual",

      changePassword: "Cambiar contraseña",
      newPassword: "Nueva contraseña",
      confirmNewPassword: "Confirmar nueva contraseña",

      session: "Sesión",
      sessionHelp: "El cierre por inactividad se aplica en este navegador según el tiempo configurado. El botón Cerrar sesión limpia la sesión local y regresa al login.",
      logout: "Cerrar sesión",

      spanish: "Español",
      english: "English",
      french: "Français",
      min15: "15 minutos",
      min30: "30 minutos",
      min60: "60 minutos",

      emailPlaceholder: "nuevo@empresa.com"
    },

    en: {
      eyebrow: "Core settings",
      title: "Settings",
      subtitle: "Core configuration for this company client portal.",

      panelPreferences: "Panel preferences",
      language: "Language",
      inactivityLock: "Inactivity lock",
      currency: "Currency",
      detectedTimezone: "Detected time zone",
      saveSettings: "Save settings",

      changeEmail: "Change email",
      newEmail: "New email",
      currentPassword: "Current password",

      changePassword: "Change password",
      newPassword: "New password",
      confirmNewPassword: "Confirm new password",

      session: "Session",
      sessionHelp: "Inactivity logout applies in this browser according to the configured time. The Log out button clears the local session and returns to login.",
      logout: "Log out",

      spanish: "Spanish",
      english: "English",
      french: "French",
      min15: "15 minutes",
      min30: "30 minutes",
      min60: "60 minutes",

      emailPlaceholder: "new@company.com"
    },

    fr: {
      eyebrow: "Configuration du noyau",
      title: "Configuration",
      subtitle: "Configuration du noyau du portail client pour cette entreprise.",

      panelPreferences: "Préférences du panneau",
      language: "Langue",
      inactivityLock: "Verrouillage par inactivité",
      currency: "Devise",
      detectedTimezone: "Fuseau horaire détecté",
      saveSettings: "Enregistrer les paramètres",

      changeEmail: "Changer l’e-mail",
      newEmail: "Nouvel e-mail",
      currentPassword: "Mot de passe actuel",

      changePassword: "Changer le mot de passe",
      newPassword: "Nouveau mot de passe",
      confirmNewPassword: "Confirmer le nouveau mot de passe",

      session: "Session",
      sessionHelp: "La déconnexion par inactivité s’applique dans ce navigateur selon le temps configuré. Le bouton Quitter efface la session locale et revient à la connexion.",
      logout: "Quitter",

      spanish: "Espagnol",
      english: "Anglais",
      french: "Français",
      min15: "15 minutes",
      min30: "30 minutes",
      min60: "60 minutes",

      emailPlaceholder: "nouveau@entreprise.com"
    }
  };

  const ALIAS = new Map();

  function norm(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function alias(key, values) {
    values.forEach((value) => {
      ALIAS.set(norm(value), key);
      ALIAS.set(norm(String(value).toUpperCase()), key);
    });
  }

  alias("eyebrow", ["CORE SETTINGS", "Core settings", "Ajustes del núcleo", "Ajustes del nucleo", "Configuration du noyau"]);
  alias("title", ["Ajustes", "Settings", "Configuration"]);
  alias("subtitle", [
    "Configuración núcleo del portal cliente para esta empresa.",
    "Configuracion nucleo del portal cliente para esta empresa.",
    "Core configuration for this company client portal.",
    "Configuration du noyau du portail client pour cette entreprise."
  ]);

  alias("panelPreferences", ["Preferencias del panel", "Panel preferences", "Préférences du panneau"]);
  alias("language", ["IDIOMA", "Idioma", "Language", "Langue"]);
  alias("inactivityLock", ["BLOQUEO POR INACTIVIDAD", "Bloqueo por inactividad", "Inactivity lock", "Verrouillage par inactivité"]);
  alias("currency", ["MONEDA", "Moneda", "Currency", "Devise"]);
  alias("detectedTimezone", ["ZONA HORARIA DETECTADA", "Zona horaria detectada", "Detected time zone", "Fuseau horaire détecté"]);
  alias("saveSettings", ["Guardar ajustes", "Save settings", "Enregistrer les paramètres"]);

  alias("changeEmail", ["Cambiar correo", "Change email", "Changer l’e-mail"]);
  alias("newEmail", ["NUEVO CORREO", "Nuevo correo", "New email", "Nouvel e-mail"]);
  alias("currentPassword", ["CONTRASEÑA ACTUAL", "Contraseña actual", "Current password", "Mot de passe actuel"]);

  alias("changePassword", ["Cambiar contraseña", "Cambiar contrasena", "Change password", "Changer le mot de passe"]);
  alias("newPassword", ["NUEVA CONTRASEÑA", "Nueva contraseña", "Nueva contrasena", "New password", "Nouveau mot de passe"]);
  alias("confirmNewPassword", ["CONFIRMAR NUEVA CONTRASEÑA", "Confirmar nueva contraseña", "Confirmar nueva contrasena", "Confirm new password", "Confirmer le nouveau mot de passe"]);

  alias("session", ["Sesión", "Sesion", "Session"]);
  alias("sessionHelp", [
    "El cierre por inactividad se aplica en este navegador según el tiempo configurado. El botón Cerrar sesión limpia la sesión local y regresa al login.",
    "El cierre por inactividad se aplica en este navegador segun el tiempo configurado. El boton Cerrar sesion limpia la sesion local y regresa al login.",
    "Inactivity logout applies in this browser according to the configured time. The Log out button clears the local session and returns to login.",
    "La déconnexion par inactivité s’applique dans ce navigateur selon le temps configuré. Le bouton Quitter efface la session locale et revient à la connexion."
  ]);
  alias("logout", ["Cerrar sesión", "Cerrar sesion", "Log out", "Quitter"]);

  alias("spanish", ["Español", "Espanol", "Spanish", "Espagnol"]);
  alias("english", ["English", "Inglés", "Ingles", "Anglais"]);
  alias("french", ["Français", "Francais", "French", "Francés", "Frances"]);

  alias("min15", ["15 minutos", "15 minutes"]);
  alias("min30", ["30 minutos", "30 minutes"]);
  alias("min60", ["60 minutos", "60 minutes"]);

  alias("emailPlaceholder", ["nuevo@empresa.com", "new@company.com", "nouveau@entreprise.com"]);

  function getLangFromStorage() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function getLangFromModal(root) {
    const selects = Array.from(root.querySelectorAll("select"));

    for (const select of selects) {
      const selected = String(select.selectedOptions && select.selectedOptions[0] ? select.selectedOptions[0].textContent : "").toLowerCase();
      const value = String(select.value || "").toLowerCase();

      if (["es", "en", "fr"].includes(value)) return value;

      if (selected.includes("english") || selected.includes("inglés") || selected.includes("ingles")) return "en";
      if (selected.includes("français") || selected.includes("francais") || selected.includes("french") || selected.includes("francés") || selected.includes("frances")) return "fr";
      if (selected.includes("español") || selected.includes("espanol") || selected.includes("spanish")) return "es";
    }

    return getLangFromStorage();
  }

  function t(key, root) {
    const language = getLangFromModal(root);
    return TEXTS[language][key] || TEXTS.es[key] || key;
  }

  function getVisibleText(el) {
    return String(el && el.textContent ? el.textContent : "");
  }

  function findSettingsRoot() {
    const candidates = Array.from(document.querySelectorAll("body *")).filter((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.width < 600 || rect.height < 500) return false;

      const text = getVisibleText(el);
      return (
        text.includes("CORE SETTINGS") ||
        text.includes("Core settings") ||
        text.includes("Ajustes") ||
        text.includes("Preferencias del panel") ||
        text.includes("Cambiar correo") ||
        text.includes("Cambiar contraseña") ||
        text.includes("Panel preferences") ||
        text.includes("Change email") ||
        text.includes("Change password")
      );
    });

    if (!candidates.length) return null;

    candidates.sort((a, b) => {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();

      const aScore = Math.abs(ar.width - window.innerWidth) + Math.abs(ar.height - window.innerHeight);
      const bScore = Math.abs(br.width - window.innerWidth) + Math.abs(br.height - window.innerHeight);

      return aScore - bScore;
    });

    return candidates[0];
  }

  function skipElement(el) {
    if (!el || !el.tagName) return true;
    const tag = el.tagName.toLowerCase();
    return ["script", "style", "code", "pre"].includes(tag);
  }

  function translateText(raw, root) {
    const clean = String(raw || "").replace(/\s+/g, " ").trim();
    if (!clean) return raw;

    const key = ALIAS.get(norm(clean));
    if (!key) return raw;

    return String(raw).replace(clean, t(key, root));
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

  function translateOptions(root) {
    root.querySelectorAll("select").forEach((select) => {
      Array.from(select.options || []).forEach((option) => {
        const current = option.textContent || "";
        const next = translateText(current, root);
        if (next !== current) option.textContent = next;
      });
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
      translateOptions(root);

      document.documentElement.lang = getLangFromModal(root);
    } catch (error) {
      console.warn("CLONEXA Core Settings i18n R2 skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateSettings, 60);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateSettings();
      if (count >= 30) clearInterval(id);
    }, 120);
  }

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 200);
    setTimeout(schedule, 500);
    setTimeout(schedule, 1000);
    setTimeout(schedule, 1800);
  }, true);

  document.addEventListener("change", () => {
    schedule();
    setTimeout(schedule, 200);
    setTimeout(schedule, 600);
    setTimeout(schedule, 1200);
  }, true);

  document.addEventListener("input", schedule, true);
  document.addEventListener("keydown", schedule, true);

  const observer = new MutationObserver(schedule);

  function init() {
    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
    }

    schedule();
    burst();

    setInterval(() => {
      if (findSettingsRoot()) translateSettings();
    }, 800);
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
    r'\s*<script[^>]+src=["\'][^"\']*client_core_settings_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE
)

matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_core_settings\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE
))

if matches:
    last = matches[-1]
    src = last.group(1)
    i18n_src = re.sub(
        r'client_core_settings\.js(?:\?v=[^"\']*)?',
        'client_core_settings_i18n_safe.js?v=020OR2',
        src
    )
    html = html[:last.end()] + f'\n<script src="{i18n_src}"></script>\n' + html[last.end():]
else:
    html = html.replace("</body>", '<script src="/client-static/client_core_settings_i18n_safe.js?v=020OR2"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020O-R2 Core Settings clean i18n installed")
