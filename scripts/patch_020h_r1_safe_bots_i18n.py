from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_bots_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaSafeBotsI18n020HR1() {
  "use strict";

  if (window.__CLONEXA_020H_R1_BOTS_I18N__) return;
  window.__CLONEXA_020H_R1_BOTS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const DICT = {
    es: {
      settings: "Ajustes",
      logout: "Cerrar sesión",

      moduleEyebrow: "Módulo Bots",
      moduleTitle: "Bots",
      moduleSubtitle: "Estado operativo del canal configurado para esta empresa.",

      back: "Volver",

      operationalChannel: "Canal operativo",
      telegramBot: "Bot Telegram",
      technicalConfig: "Configuración técnica administrada desde CLONEXA Admin V2.",

      status: "Estado",
      channel: "Canal",
      bot: "Bot",

      listening: "Escuchando",
      connected: "Conectado",
      inactive: "Inactivo",
      error: "Error",
      notConfigured: "No configurado",
      noConfigured: "Sin configurar",

      internalBotName: "Nombre interno del bot",
      saveName: "Guardar nombre",

      requiredName: "Nombre interno obligatorio.",
      nameUpdated: "Nombre del bot actualizado.",
      saveError: "No se pudo guardar el nombre.",

      telegram: "Telegram",
      whatsapp: "WhatsApp"
    },

    en: {
      settings: "Settings",
      logout: "Log out",

      moduleEyebrow: "Bots module",
      moduleTitle: "Bots",
      moduleSubtitle: "Operational status of the channel configured for this company.",

      back: "Back",

      operationalChannel: "Operational channel",
      telegramBot: "Telegram bot",
      technicalConfig: "Technical configuration managed from CLONEXA Admin V2.",

      status: "Status",
      channel: "Channel",
      bot: "Bot",

      listening: "Listening",
      connected: "Connected",
      inactive: "Inactive",
      error: "Error",
      notConfigured: "Not configured",
      noConfigured: "Not configured",

      internalBotName: "Internal bot name",
      saveName: "Save name",

      requiredName: "Internal name is required.",
      nameUpdated: "Bot name updated.",
      saveError: "Could not save the name.",

      telegram: "Telegram",
      whatsapp: "WhatsApp"
    },

    fr: {
      settings: "Configuration",
      logout: "Quitter",

      moduleEyebrow: "Module bots",
      moduleTitle: "Bots",
      moduleSubtitle: "État opérationnel du canal configuré pour cette entreprise.",

      back: "Retour",

      operationalChannel: "Canal opérationnel",
      telegramBot: "Bot Telegram",
      technicalConfig: "Configuration technique gérée depuis CLONEXA Admin V2.",

      status: "Statut",
      channel: "Canal",
      bot: "Bot",

      listening: "En écoute",
      connected: "Connecté",
      inactive: "Inactif",
      error: "Erreur",
      notConfigured: "Non configuré",
      noConfigured: "Non configuré",

      internalBotName: "Nom interne du bot",
      saveName: "Enregistrer le nom",

      requiredName: "Le nom interne est obligatoire.",
      nameUpdated: "Nom du bot mis à jour.",
      saveError: "Impossible d’enregistrer le nom.",

      telegram: "Telegram",
      whatsapp: "WhatsApp"
    }
  };

  const ALIASES = {};

  Object.keys(DICT).forEach((language) => {
    Object.keys(DICT[language]).forEach((key) => {
      ALIASES[norm(DICT[language][key])] = key;
    });
  });

  [
    ["Modulo Bots", "moduleEyebrow"],
    ["Módulo Bots", "moduleEyebrow"],
    ["MODULO BOTS", "moduleEyebrow"],
    ["Bots", "moduleTitle"],
    ["Estado operativo del canal configurado para esta empresa.", "moduleSubtitle"],

    ["Volver", "back"],

    ["Canal operativo", "operationalChannel"],
    ["Bot Telegram", "telegramBot"],
    ["Configuracion tecnica administrada desde CLONEXA Admin V2.", "technicalConfig"],
    ["Configuración técnica administrada desde CLONEXA Admin V2.", "technicalConfig"],

    ["Estado", "status"],
    ["Canal", "channel"],
    ["Bot", "bot"],

    ["Escuchando", "listening"],
    ["Conectado", "connected"],
    ["Inactivo", "inactive"],
    ["Error", "error"],
    ["No configurado", "notConfigured"],
    ["Sin configurar", "noConfigured"],

    ["Nombre interno del bot", "internalBotName"],
    ["Guardar nombre", "saveName"],

    ["Nombre interno obligatorio.", "requiredName"],
    ["Nombre del bot actualizado.", "nameUpdated"],
    ["No se pudo guardar el nombre.", "saveError"],

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
    if (raw.includes("@")) return true;
    if (/^[a-f0-9-]{20,}$/i.test(raw)) return true;
    if (/^@[a-z0-9_]{4,}$/i.test(raw)) return true;
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

  function isBotsVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector("[data-bot-name]")) return true;
    if (app.querySelector("[data-bot-save-name]")) return true;
    if (app.querySelector("#botsNotice")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Modulo Bots") ||
      text.includes("Módulo Bots") ||
      text.includes("Bots module") ||
      text.includes("Module bots") ||
      text.includes("Bot Telegram") ||
      text.includes("Telegram bot")
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

  function translateBots() {
    try {
      if (!isBotsVisible()) return;

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
      console.warn("CLONEXA Bots i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateBots, 140);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateBots();
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
      console.warn("CLONEXA Bots i18n init skipped:", error);
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
    r'\s*<script[^>]+src=["\'][^"\']*client_bots_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

gps_matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_gps_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if gps_matches:
    last = gps_matches[-1]
    src = last.group(1)
    safe_src = re.sub(r'client_gps_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_bots_i18n_safe.js?v=020HR1', src)
    html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
else:
    inventory_matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client_inventory_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE,
    ))
    if inventory_matches:
        last = inventory_matches[-1]
        src = last.group(1)
        safe_src = re.sub(r'client_inventory_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_bots_i18n_safe.js?v=020HR1', src)
        html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/client-static/client_bots_i18n_safe.js?v=020HR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020H-R1 safe external Bots i18n added")
