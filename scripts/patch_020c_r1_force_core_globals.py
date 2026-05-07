from pathlib import Path
import re

js_path = Path("app/web/client_core_settings.js")
html_path = Path("app/web/client.html")

js = js_path.read_text(encoding="utf-8-sig")
html = html_path.read_text(encoding="utf-8-sig")

marker = "/* CLONEXA 020C-R1 FORCE CORE GLOBALS */"

# Idempotente: limpia versión anterior si existe
js = re.sub(
    r"\n?/\* CLONEXA 020C-R1 FORCE CORE GLOBALS \*/[\s\S]*?/\* END CLONEXA 020C-R1 FORCE CORE GLOBALS \*/\n?",
    "\n",
    js,
    flags=re.MULTILINE,
)

runtime = r'''
/* CLONEXA 020C-R1 FORCE CORE GLOBALS */
(function clonexaForceCoreGlobals020CR1() {
  "use strict";

  const API = "/api/v1";
  const LANG_KEY = "clonexa_client_language";
  const SESSION_KEY = "clonexa_session_timeout_minutes";

  function companyId() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || params.get("tenant") || "";
  }

  function detectedTimezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Bogota";
    } catch (_) {
      return "America/Bogota";
    }
  }

  function normalizeLanguage(value) {
    const lang = String(value || "es").toLowerCase();
    return ["es", "en", "fr"].includes(lang) ? lang : "es";
  }

  function normalizeTimeout(value) {
    const n = Number(value || 30);
    return [15, 30, 60].includes(n) ? n : 30;
  }

  function normalizeCurrency(value) {
    const c = String(value || "COP").toUpperCase();
    return ["COP", "USD", "EUR", "MXN", "CLP", "PEN"].includes(c) ? c : "COP";
  }

  function currencyKey(id) {
    return `clonexa_currency_${id || companyId() || "unknown"}`;
  }

  function timezoneKey(id) {
    return `clonexa_timezone_${id || companyId() || "unknown"}`;
  }

  const I18N = {
    es: {
      "dashboard.eyebrow": "SISTEMA OPERATIVO EMPRESARIAL",
      "dashboard.title": "Dashboard",
      "dashboard.subtitle": "Panel operativo independiente conectado a sus módulos activos.",
      "module.inventory": "Inventario",
      "module.crm": "CRM Campo",
      "module.payroll": "Nómina",
      "module.workforce": "Workforce",
      "module.personal": "Personal",
      "module.kpis": "KPIs",
      "module.gps": "GPS",
      "module.bots": "Bots",
      "module.materials": "Materiales",
      "module.reports": "Reportes",
      "app.settings": "Ajustes",
      "app.logout": "Cerrar sesión",
      "app.save": "Guardar",
      "app.back": "Volver",
      "app.refresh": "Actualizar"
    },
    en: {
      "dashboard.eyebrow": "BUSINESS OPERATING SYSTEM",
      "dashboard.title": "Dashboard",
      "dashboard.subtitle": "Independent operations panel connected to its active modules.",
      "module.inventory": "Inventory",
      "module.crm": "Field CRM",
      "module.payroll": "Payroll",
      "module.workforce": "Workforce",
      "module.personal": "Staff",
      "module.kpis": "KPIs",
      "module.gps": "GPS",
      "module.bots": "Bots",
      "module.materials": "Materials",
      "module.reports": "Reports",
      "app.settings": "Settings",
      "app.logout": "Log out",
      "app.save": "Save",
      "app.back": "Back",
      "app.refresh": "Refresh"
    },
    fr: {
      "dashboard.eyebrow": "SYSTÈME OPÉRATIONNEL D’ENTREPRISE",
      "dashboard.title": "Tableau de bord",
      "dashboard.subtitle": "Panneau opérationnel indépendant connecté à ses modules actifs.",
      "module.inventory": "Inventaire",
      "module.crm": "CRM Terrain",
      "module.payroll": "Paie",
      "module.workforce": "Workforce",
      "module.personal": "Personnel",
      "module.kpis": "KPIs",
      "module.gps": "GPS",
      "module.bots": "Bots",
      "module.materials": "Matériaux",
      "module.reports": "Rapports",
      "app.settings": "Configuration",
      "app.logout": "Quitter",
      "app.save": "Enregistrer",
      "app.back": "Retour",
      "app.refresh": "Actualiser"
    }
  };

  function localSettings() {
    const id = companyId();

    return {
      company_id: id || null,
      language: normalizeLanguage(localStorage.getItem(LANG_KEY) || "es"),
      session_timeout_minutes: normalizeTimeout(localStorage.getItem(SESSION_KEY) || 30),
      currency: normalizeCurrency(localStorage.getItem(currencyKey(id)) || "COP"),
      timezone: localStorage.getItem(timezoneKey(id)) || detectedTimezone(),
      loaded: false,
      source: "local"
    };
  }

  function persist(settings) {
    const id = settings.company_id || companyId();

    localStorage.setItem(LANG_KEY, normalizeLanguage(settings.language));
    localStorage.setItem(SESSION_KEY, String(normalizeTimeout(settings.session_timeout_minutes)));
    localStorage.setItem(currencyKey(id), normalizeCurrency(settings.currency));
    localStorage.setItem(timezoneKey(id), settings.timezone || detectedTimezone());

    document.documentElement.lang = normalizeLanguage(settings.language);
  }

  function setSettings(settings) {
    const merged = {
      ...localSettings(),
      ...(window.CLX_CORE_SETTINGS || {}),
      ...(settings || {})
    };

    merged.language = normalizeLanguage(merged.language);
    merged.session_timeout_minutes = normalizeTimeout(merged.session_timeout_minutes);
    merged.currency = normalizeCurrency(merged.currency);
    merged.timezone = merged.timezone || detectedTimezone();

    window.CLX_CORE_SETTINGS = merged;
    persist(merged);

    window.dispatchEvent(new CustomEvent("clonexa:core-settings-changed", {
      detail: { ...merged }
    }));

    return merged;
  }

  async function fetchCoreSettings() {
    const id = companyId();

    if (!id) {
      return setSettings({ ...localSettings(), loaded: true, source: "local-no-company" });
    }

    try {
      const response = await fetch(`${API}/companies/${encodeURIComponent(id)}/core-settings`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();

      return setSettings({
        ...localSettings(),
        ...data,
        company_id: id,
        loaded: true,
        source: "remote"
      });
    } catch (error) {
      return setSettings({
        ...localSettings(),
        company_id: id,
        loaded: true,
        source: "local-fallback",
        error: error.message || "core settings unavailable"
      });
    }
  }

  async function saveCoreSettings(partial) {
    const current = setSettings({
      ...(window.CLX_CORE_SETTINGS || localSettings()),
      ...(partial || {})
    });

    if (!current.company_id) return current;

    try {
      const response = await fetch(`${API}/companies/${encodeURIComponent(current.company_id)}/core-settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          language: current.language,
          session_timeout_minutes: current.session_timeout_minutes,
          currency: current.currency,
          timezone: current.timezone
        })
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();

      return setSettings({
        ...current,
        ...data,
        loaded: true,
        source: "remote-save"
      });
    } catch (error) {
      return setSettings({
        ...current,
        loaded: true,
        source: "local-save-fallback",
        error: error.message || "core settings save unavailable"
      });
    }
  }

  function getLanguage() {
    return normalizeLanguage((window.CLX_CORE_SETTINGS && window.CLX_CORE_SETTINGS.language) || localStorage.getItem(LANG_KEY) || "es");
  }

  function t(key, params) {
    const lang = getLanguage();
    let value = (I18N[lang] && I18N[lang][key]) || (I18N.es && I18N.es[key]) || key;

    Object.keys(params || {}).forEach((paramKey) => {
      value = value.replaceAll(`{${paramKey}}`, String(params[paramKey]));
    });

    return value;
  }

  async function setLanguage(language, options) {
    const settings = await saveCoreSettings({ language: normalizeLanguage(language) });

    if (options && options.reload === true) {
      window.location.reload();
    }

    return settings;
  }

  function formatMoney(value, currency) {
    const settings = window.CLX_CORE_SETTINGS || localSettings();
    const activeCurrency = normalizeCurrency(currency || settings.currency || "COP");
    const lang = getLanguage();

    const locale =
      lang === "fr" ? "fr-FR" :
      lang === "en" ? "en-US" :
      "es-CO";

    try {
      return new Intl.NumberFormat(locale, {
        style: "currency",
        currency: activeCurrency,
        maximumFractionDigits: activeCurrency === "COP" || activeCurrency === "CLP" ? 0 : 2
      }).format(Number(value || 0));
    } catch (_) {
      return `${activeCurrency} ${Number(value || 0).toLocaleString(locale)}`;
    }
  }

  function formatDateTime(value) {
    const settings = window.CLX_CORE_SETTINGS || localSettings();
    const lang = getLanguage();

    const locale =
      lang === "fr" ? "fr-FR" :
      lang === "en" ? "en-US" :
      "es-CO";

    try {
      return new Intl.DateTimeFormat(locale, {
        timeZone: settings.timezone || detectedTimezone(),
        dateStyle: "short",
        timeStyle: "short"
      }).format(value ? new Date(value) : new Date());
    } catch (_) {
      return String(value || new Date());
    }
  }

  window.CLX_CORE_TRANSLATIONS = I18N;
  window.CLX_CORE_SETTINGS = window.CLX_CORE_SETTINGS || setSettings(localSettings());

  window.CLX_LOAD_CORE_SETTINGS = fetchCoreSettings;
  window.CLX_SAVE_CORE_SETTINGS = saveCoreSettings;
  window.CLX_GET_LANGUAGE = getLanguage;
  window.CLX_SET_LANGUAGE = setLanguage;
  window.CLX_T = t;
  window.CLX_FORMAT_MONEY = formatMoney;
  window.CLX_FORMAT_DATETIME = formatDateTime;

  fetchCoreSettings().then((settings) => {
    window.dispatchEvent(new CustomEvent("clonexa:core-settings-ready", {
      detail: { ...settings }
    }));
  });
})();
/* END CLONEXA 020C-R1 FORCE CORE GLOBALS */
'''

js = js.rstrip() + "\n\n" + runtime + "\n"
js_path.write_text(js, encoding="utf-8")

# Asegurar script cargado y cache bump
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_i18n\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE
)

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_google_translate\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE
)

html = re.sub(
    r'client_core_settings\.js(?:\?v=[^"\']*)?',
    'client_core_settings.js?v=020CR1',
    html,
    flags=re.IGNORECASE
)

if "client_core_settings.js" not in html:
    matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE
    ))

    if matches:
        last = matches[-1]
        src = last.group(1)
        settings_src = re.sub(r'client\.js(?:\?v=[^"\']*)?', 'client_core_settings.js?v=020CR1', src)
        html = html[:last.end()] + f'\n<script src="{settings_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/static/client_core_settings.js?v=020CR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020C-R1 force core globals applied")
