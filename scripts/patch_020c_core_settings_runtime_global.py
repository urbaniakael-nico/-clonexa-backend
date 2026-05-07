from pathlib import Path
import re

client_core_path = Path("app/web/client_core_settings.js")
client_html_path = Path("app/web/client.html")

js = client_core_path.read_text(encoding="utf-8-sig")
html = client_html_path.read_text(encoding="utf-8-sig")

marker = "/* CLONEXA 020C CORE SETTINGS RUNTIME GLOBAL */"

# Reemplazo idempotente si se vuelve a correr.
js = re.sub(
    r"\n?/\* CLONEXA 020C CORE SETTINGS RUNTIME GLOBAL \*/[\s\S]*?\n/\* END CLONEXA 020C CORE SETTINGS RUNTIME GLOBAL \*/\n?",
    "\n",
    js,
    flags=re.MULTILINE,
)

runtime = r'''
/* CLONEXA 020C CORE SETTINGS RUNTIME GLOBAL */
(function clonexaCoreSettingsRuntimeGlobal() {
  "use strict";

  if (window.__CLONEXA_020C_CORE_RUNTIME__) return;
  window.__CLONEXA_020C_CORE_RUNTIME__ = true;

  const API = "/api/v1";
  const LANG_KEY = "clonexa_client_language";
  const SESSION_KEY = "clonexa_session_timeout_minutes";
  const CURRENCY_KEY_PREFIX = "clonexa_currency_";
  const TZ_KEY_PREFIX = "clonexa_timezone_";

  const DEFAULT_SETTINGS = {
    company_id: null,
    language: "es",
    session_timeout_minutes: 30,
    currency: "COP",
    timezone: null,
    loaded: false,
    source: "default",
    updated_at: null
  };

  const I18N = {
    es: {
      "app.settings": "Ajustes",
      "app.logout": "Cerrar sesión",
      "app.save": "Guardar",
      "app.cancel": "Cancelar",
      "app.refresh": "Actualizar",
      "app.back": "Volver",
      "app.loading": "Cargando",
      "app.search": "Buscar",
      "app.status": "Estado",
      "app.actions": "Acciones",
      "app.active": "Activo",
      "app.inactive": "Inactivo",
      "app.archived": "Archivado",

      "dashboard.title": "Dashboard",
      "dashboard.eyebrow": "SISTEMA OPERATIVO EMPRESARIAL",
      "dashboard.subtitle": "Panel operativo independiente conectado a sus módulos activos.",
      "dashboard.modules": "Módulos del panel",
      "dashboard.active_services": "Servicios activos",
      "dashboard.active_now": "Activos ahora",
      "dashboard.gps_inside": "GPS dentro",
      "dashboard.material_delivered": "Material entregado",
      "dashboard.low_stock": "Stock bajo",

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

      "settings.title": "Ajustes",
      "settings.subtitle": "Configuración núcleo del portal cliente para esta empresa.",
      "settings.language": "Idioma",
      "settings.timeout": "Bloqueo por inactividad",
      "settings.currency": "Moneda",
      "settings.timezone": "Zona horaria detectada",
      "settings.save": "Guardar ajustes",
      "settings.saved": "Ajustes guardados correctamente."
    },

    en: {
      "app.settings": "Settings",
      "app.logout": "Log out",
      "app.save": "Save",
      "app.cancel": "Cancel",
      "app.refresh": "Refresh",
      "app.back": "Back",
      "app.loading": "Loading",
      "app.search": "Search",
      "app.status": "Status",
      "app.actions": "Actions",
      "app.active": "Active",
      "app.inactive": "Inactive",
      "app.archived": "Archived",

      "dashboard.title": "Dashboard",
      "dashboard.eyebrow": "BUSINESS OPERATING SYSTEM",
      "dashboard.subtitle": "Independent operations panel connected to its active modules.",
      "dashboard.modules": "Panel modules",
      "dashboard.active_services": "Active services",
      "dashboard.active_now": "Active now",
      "dashboard.gps_inside": "GPS inside",
      "dashboard.material_delivered": "Delivered material",
      "dashboard.low_stock": "Low stock",

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

      "settings.title": "Settings",
      "settings.subtitle": "Core configuration of the client portal for this company.",
      "settings.language": "Language",
      "settings.timeout": "Inactivity lock",
      "settings.currency": "Currency",
      "settings.timezone": "Detected timezone",
      "settings.save": "Save settings",
      "settings.saved": "Settings saved successfully."
    },

    fr: {
      "app.settings": "Configuration",
      "app.logout": "Quitter",
      "app.save": "Enregistrer",
      "app.cancel": "Annuler",
      "app.refresh": "Actualiser",
      "app.back": "Retour",
      "app.loading": "Chargement",
      "app.search": "Rechercher",
      "app.status": "Statut",
      "app.actions": "Actions",
      "app.active": "Actif",
      "app.inactive": "Inactif",
      "app.archived": "Archivé",

      "dashboard.title": "Tableau de bord",
      "dashboard.eyebrow": "SYSTÈME OPÉRATIONNEL D’ENTREPRISE",
      "dashboard.subtitle": "Panneau opérationnel indépendant connecté à ses modules actifs.",
      "dashboard.modules": "Modules du panneau",
      "dashboard.active_services": "Services actifs",
      "dashboard.active_now": "Actifs maintenant",
      "dashboard.gps_inside": "GPS à l’intérieur",
      "dashboard.material_delivered": "Matériel livré",
      "dashboard.low_stock": "Stock faible",

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

      "settings.title": "Configuration",
      "settings.subtitle": "Configuration noyau du portail client pour cette entreprise.",
      "settings.language": "Langue",
      "settings.timeout": "Verrouillage par inactivité",
      "settings.currency": "Devise",
      "settings.timezone": "Fuseau horaire détecté",
      "settings.save": "Enregistrer",
      "settings.saved": "Paramètres enregistrés correctement."
    }
  };

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

  function currencyKey(id = companyId()) {
    return `${CURRENCY_KEY_PREFIX}${id || "unknown"}`;
  }

  function timezoneKey(id = companyId()) {
    return `${TZ_KEY_PREFIX}${id || "unknown"}`;
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

  function localSettings() {
    const id = companyId();

    return {
      company_id: id || null,
      language: normalizeLanguage(localStorage.getItem(LANG_KEY) || "es"),
      session_timeout_minutes: normalizeTimeout(localStorage.getItem(SESSION_KEY) || 30),
      currency: normalizeCurrency(localStorage.getItem(currencyKey(id)) || "COP"),
      timezone: localStorage.getItem(timezoneKey(id)) || detectedTimezone(),
      loaded: false,
      source: "local",
      updated_at: null
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

  function setRuntimeSettings(settings) {
    const merged = {
      ...DEFAULT_SETTINGS,
      ...window.CLX_CORE_SETTINGS,
      ...settings,
      company_id: settings.company_id || companyId() || null,
      language: normalizeLanguage(settings.language),
      session_timeout_minutes: normalizeTimeout(settings.session_timeout_minutes),
      currency: normalizeCurrency(settings.currency),
      timezone: settings.timezone || detectedTimezone(),
      loaded: Boolean(settings.loaded),
      source: settings.source || "runtime"
    };

    window.CLX_CORE_SETTINGS = merged;
    persist(merged);

    window.dispatchEvent(new CustomEvent("clonexa:core-settings-changed", {
      detail: { ...merged }
    }));

    return merged;
  }

  async function fetchJson(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });

    let data = null;

    try {
      data = await response.json();
    } catch (_) {
      data = null;
    }

    if (!response.ok) {
      const detail = data && (data.detail || data.message);
      throw new Error(detail || `HTTP ${response.status}`);
    }

    return data || {};
  }

  async function loadCoreSettings() {
    const id = companyId();
    const local = localSettings();

    if (!id) {
      const settings = setRuntimeSettings({ ...local, loaded: true, source: "local-no-company" });
      window.dispatchEvent(new CustomEvent("clonexa:core-settings-ready", { detail: { ...settings } }));
      return settings;
    }

    try {
      const remote = await fetchJson(`/companies/${encodeURIComponent(id)}/core-settings`);
      const settings = setRuntimeSettings({
        ...local,
        ...remote,
        company_id: id,
        loaded: true,
        source: "remote"
      });

      window.dispatchEvent(new CustomEvent("clonexa:core-settings-ready", { detail: { ...settings } }));
      return settings;
    } catch (error) {
      const settings = setRuntimeSettings({
        ...local,
        company_id: id,
        loaded: true,
        source: "local-fallback",
        error: error.message || "core settings unavailable"
      });

      window.dispatchEvent(new CustomEvent("clonexa:core-settings-ready", { detail: { ...settings } }));
      return settings;
    }
  }

  async function saveCoreSettings(partial = {}) {
    const current = {
      ...localSettings(),
      ...window.CLX_CORE_SETTINGS,
      ...partial
    };

    const clean = {
      company_id: current.company_id || companyId() || null,
      language: normalizeLanguage(current.language),
      session_timeout_minutes: normalizeTimeout(current.session_timeout_minutes),
      currency: normalizeCurrency(current.currency),
      timezone: current.timezone || detectedTimezone()
    };

    persist(clean);

    if (clean.company_id) {
      try {
        const remote = await fetchJson(`/companies/${encodeURIComponent(clean.company_id)}/core-settings`, {
          method: "PUT",
          body: JSON.stringify({
            language: clean.language,
            session_timeout_minutes: clean.session_timeout_minutes,
            currency: clean.currency,
            timezone: clean.timezone
          })
        });

        return setRuntimeSettings({
          ...clean,
          ...remote,
          loaded: true,
          source: "remote-save"
        });
      } catch (error) {
        return setRuntimeSettings({
          ...clean,
          loaded: true,
          source: "local-save-fallback",
          error: error.message || "core settings save unavailable"
        });
      }
    }

    return setRuntimeSettings({
      ...clean,
      loaded: true,
      source: "local-save"
    });
  }

  function getLanguage() {
    return normalizeLanguage((window.CLX_CORE_SETTINGS && window.CLX_CORE_SETTINGS.language) || localStorage.getItem(LANG_KEY) || "es");
  }

  function translate(key, params = {}) {
    const lang = getLanguage();
    const pack = I18N[lang] || I18N.es;
    let value = pack[key] || I18N.es[key] || key;

    Object.keys(params || {}).forEach((paramKey) => {
      value = value.replaceAll(`{${paramKey}}`, String(params[paramKey]));
    });

    return value;
  }

  async function setLanguage(language, options = {}) {
    const lang = normalizeLanguage(language);
    const settings = await saveCoreSettings({ language: lang });

    if (options.reload === true) {
      window.location.reload();
    }

    return settings;
  }

  function formatMoney(value, currency = null) {
    const settings = window.CLX_CORE_SETTINGS || localSettings();
    const activeCurrency = normalizeCurrency(currency || settings.currency || "COP");
    const lang = getLanguage();

    const locale =
      lang === "fr" ? "fr-FR" :
      lang === "en" ? "en-US" :
      "es-CO";

    const amount = Number(value || 0);

    try {
      return new Intl.NumberFormat(locale, {
        style: "currency",
        currency: activeCurrency,
        maximumFractionDigits: activeCurrency === "COP" || activeCurrency === "CLP" ? 0 : 2
      }).format(amount);
    } catch (_) {
      return `${activeCurrency} ${amount.toLocaleString(locale)}`;
    }
  }

  function formatDateTime(value, options = {}) {
    const settings = window.CLX_CORE_SETTINGS || localSettings();
    const lang = getLanguage();

    const locale =
      lang === "fr" ? "fr-FR" :
      lang === "en" ? "en-US" :
      "es-CO";

    const date = value ? new Date(value) : new Date();

    try {
      return new Intl.DateTimeFormat(locale, {
        timeZone: settings.timezone || detectedTimezone(),
        dateStyle: options.dateStyle || "short",
        timeStyle: options.timeStyle || "short"
      }).format(date);
    } catch (_) {
      return date.toLocaleString();
    }
  }

  function patchSettingsModalLabels() {
    const lang = getLanguage();

    const labels = [
      ["#clxOpenCoreSettings", `⚙ ${translate("app.settings")}`],
      ["#clxCoreLogout", `⏻ ${translate("app.logout")}`],
      ["#clxCoreLogoutFromModal", translate("app.logout")],
      ["#clxSaveCorePreferences", translate("settings.save")]
    ];

    labels.forEach(([selector, text]) => {
      const el = document.querySelector(selector);
      if (el) el.textContent = text;
    });

    const modal = document.getElementById("clxCoreSettingsModal");
    if (!modal) return;

    const h2 = modal.querySelector(".clx-core-modal-head h2");
    const p = modal.querySelector(".clx-core-modal-head p");

    if (h2) h2.textContent = translate("settings.title");
    if (p) p.textContent = translate("settings.subtitle");

    const fieldMap = [
      ["#clxCoreLanguage", "settings.language"],
      ["#clxCoreTimeout", "settings.timeout"],
      ["#clxCoreCurrency", "settings.currency"],
      ["#clxCoreTimezone", "settings.timezone"]
    ];

    fieldMap.forEach(([selector, key]) => {
      const input = modal.querySelector(selector);
      const label = input && input.closest(".clx-core-field");
      const span = label && label.querySelector("span");
      if (span) span.textContent = translate(key);
    });

    const status = document.getElementById("clxCorePreferencesStatus");
    if (status && /Ajustes guardados|Settings saved|Paramètres enregistrés/i.test(status.textContent || "")) {
      status.textContent = translate("settings.saved");
    }

    document.documentElement.lang = lang;
  }

  function installDomBindings() {
    document.addEventListener("change", function (event) {
      const target = event.target;
      if (!target || target.id !== "clxCoreLanguage") return;

      const next = normalizeLanguage(target.value);
      setRuntimeSettings({
        ...(window.CLX_CORE_SETTINGS || localSettings()),
        language: next,
        loaded: true,
        source: "ui-preview"
      });

      patchSettingsModalLabels();
    }, true);

    document.addEventListener("click", function (event) {
      const target = event.target;
      if (!target) return;

      if (target.id === "clxSaveCorePreferences") {
        setTimeout(function () {
          loadCoreSettings().then(patchSettingsModalLabels).catch(patchSettingsModalLabels);
        }, 700);
      }

      if (target.id === "clxOpenCoreSettings") {
        setTimeout(patchSettingsModalLabels, 180);
        setTimeout(patchSettingsModalLabels, 600);
      }
    }, true);

    const observer = new MutationObserver(function () {
      patchSettingsModalLabels();
    });

    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }

  window.CLX_CORE_TRANSLATIONS = I18N;
  window.CLX_CORE_SETTINGS = {
    ...DEFAULT_SETTINGS,
    ...localSettings()
  };

  window.CLX_LOAD_CORE_SETTINGS = loadCoreSettings;
  window.CLX_SAVE_CORE_SETTINGS = saveCoreSettings;
  window.CLX_T = translate;
  window.CLX_SET_LANGUAGE = setLanguage;
  window.CLX_GET_LANGUAGE = getLanguage;
  window.CLX_FORMAT_MONEY = formatMoney;
  window.CLX_FORMAT_DATETIME = formatDateTime;

  document.documentElement.lang = window.CLX_CORE_SETTINGS.language;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      installDomBindings();
      loadCoreSettings().then(patchSettingsModalLabels).catch(patchSettingsModalLabels);
    });
  } else {
    installDomBindings();
    loadCoreSettings().then(patchSettingsModalLabels).catch(patchSettingsModalLabels);
  }
})();
/* END CLONEXA 020C CORE SETTINGS RUNTIME GLOBAL */
'''

js = js.rstrip() + "\n\n" + runtime + "\n"
client_core_path.write_text(js, encoding="utf-8")

# Bump cache version de client_core_settings.
html = re.sub(
    r'client_core_settings\.js(?:\?v=[^"\']*)?',
    'client_core_settings.js?v=020C',
    html,
    flags=re.IGNORECASE,
)

client_html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020C runtime global injected")
