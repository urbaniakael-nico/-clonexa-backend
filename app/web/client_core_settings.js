(function clonexaCoreSettingsClientModule() {
  "use strict";

  if (window.__CLONEXA_020B_CORE_SETTINGS__) return;
  window.__CLONEXA_020B_CORE_SETTINGS__ = true;

  const API = "/api/v1";
  const LANG_KEY = "clonexa_client_language";
  const SESSION_KEY = "clonexa_session_timeout_minutes";
  const CURRENCY_KEY_PREFIX = "clonexa_currency_";
  const TZ_KEY_PREFIX = "clonexa_timezone_";

  function companyId() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || params.get("tenant") || "";
  }

  function token() {
    const keys = [
      "clonexa_access_token",
      "clonexa_token",
      "clonexa_client_token",
      "access_token",
      "token",
      "auth_token",
      "jwt",
    ];

    for (const key of keys) {
      const direct = localStorage.getItem(key) || sessionStorage.getItem(key);
      if (direct && direct !== "null" && direct !== "undefined") return direct.replace(/^Bearer\s+/i, "");
    }

    for (const store of [localStorage, sessionStorage]) {
      for (let i = 0; i < store.length; i += 1) {
        const key = store.key(i);
        const raw = store.getItem(key);
        if (!raw || raw[0] !== "{") continue;
        try {
          const data = JSON.parse(raw);
          const value = data.access_token || data.token || data.jwt;
          if (value) return String(value).replace(/^Bearer\s+/i, "");
        } catch (_) {}
      }
    }

    return "";
  }

  function headers(auth = false) {
    const h = { "Content-Type": "application/json" };
    const t = token();
    if (auth && t) h.Authorization = `Bearer ${t}`;
    return h;
  }

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        ...headers(Boolean(options.auth)),
        ...(options.headers || {}),
      },
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

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function detectedTimezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (_) {
      return "";
    }
  }

  function currencyKey() {
    return `${CURRENCY_KEY_PREFIX}${companyId() || "unknown"}`;
  }

  function timezoneKey() {
    return `${TZ_KEY_PREFIX}${companyId() || "unknown"}`;
  }

  async function loadCoreSettings() {
    const id = companyId();
    const local = {
      language: localStorage.getItem(LANG_KEY) || "es",
      session_timeout_minutes: Number(localStorage.getItem(SESSION_KEY) || 30),
      currency: localStorage.getItem(currencyKey()) || "COP",
      timezone: localStorage.getItem(timezoneKey()) || detectedTimezone(),
    };

    if (!id) return local;

    try {
      const remote = await api(`/companies/${encodeURIComponent(id)}/core-settings`);
      const merged = { ...local, ...remote };

      localStorage.setItem(LANG_KEY, merged.language || "es");
      localStorage.setItem(SESSION_KEY, String(merged.session_timeout_minutes || 30));
      localStorage.setItem(currencyKey(), merged.currency || "COP");
      localStorage.setItem(timezoneKey(), merged.timezone || detectedTimezone());

      return merged;
    } catch (_) {
      return local;
    }
  }

  async function saveCoreSettings(payload) {
    const id = companyId();
    const clean = {
      language: String(payload.language || "es").toLowerCase(),
      session_timeout_minutes: Number(payload.session_timeout_minutes || 30),
      currency: String(payload.currency || "COP").toUpperCase(),
      timezone: String(payload.timezone || detectedTimezone() || ""),
    };

    localStorage.setItem(LANG_KEY, clean.language);
    localStorage.setItem(SESSION_KEY, String(clean.session_timeout_minutes));
    localStorage.setItem(currencyKey(), clean.currency);
    localStorage.setItem(timezoneKey(), clean.timezone);

    if (id) {
      await api(`/companies/${encodeURIComponent(id)}/core-settings`, {
        method: "PUT",
        body: JSON.stringify(clean),
      });
    }

    if (token()) {
      try {
        await api("/auth/account/preferences", {
          method: "PATCH",
          auth: true,
          body: JSON.stringify({
            language: clean.language,
            session_timeout_minutes: clean.session_timeout_minutes,
          }),
        });
      } catch (_) {}
    }

    installInactivityGuard();
    return clean;
  }

  function findSidebar() {
    return (
      document.querySelector(".client-sidebar") ||
      document.querySelector("aside") ||
      document.querySelector("[class*='sidebar']") ||
      document.querySelector("[class*='Side']") ||
      null
    );
  }

  function installStyles() {
    if (document.getElementById("clxCoreSettingsStyles")) return;

    const style = document.createElement("style");
    style.id = "clxCoreSettingsStyles";
    style.textContent = `
      .clx-core-actions {
        margin-top: 14px;
        display: grid;
        gap: 10px;
      }

      .clx-core-action-btn {
        width: 100%;
        border: 1px solid rgba(255,255,255,.14);
        background: linear-gradient(135deg, rgba(255, 25, 166, .28), rgba(255,255,255,.06));
        color: inherit;
        border-radius: 16px;
        padding: 12px 14px;
        cursor: pointer;
        font-weight: 900;
        text-align: left;
      }

      .clx-core-action-btn:hover {
        border-color: rgba(255, 43, 172, .75);
        box-shadow: 0 0 24px rgba(255, 43, 172, .22);
      }

      .clx-core-logout {
        background: rgba(255,255,255,.06);
      }

      .clx-core-modal-backdrop {
        position: fixed;
        inset: 0;
        z-index: 99998;
        background: rgba(0,0,0,.72);
        display: grid;
        place-items: center;
        padding: 22px;
      }

      .clx-core-modal {
        width: min(980px, 96vw);
        max-height: 92vh;
        overflow: auto;
        border-radius: 28px;
        border: 1px solid rgba(255,255,255,.14);
        background:
          radial-gradient(circle at 100% 0%, rgba(255, 20, 170, .32), transparent 34%),
          linear-gradient(145deg, rgba(15,18,28,.98), rgba(36,14,42,.96));
        color: #fff;
        box-shadow: 0 28px 100px rgba(0,0,0,.58);
        padding: 26px;
      }

      .clx-core-modal-head {
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: flex-start;
        margin-bottom: 20px;
      }

      .clx-core-modal-head h2 {
        margin: 0;
        font-size: clamp(30px, 4vw, 52px);
        letter-spacing: -0.06em;
      }

      .clx-core-close {
        border: 1px solid rgba(255,255,255,.16);
        border-radius: 999px;
        background: rgba(255,255,255,.08);
        color: #fff;
        padding: 10px 14px;
        cursor: pointer;
        font-weight: 900;
      }

      .clx-core-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
      }

      .clx-core-card {
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 22px;
        background: rgba(255,255,255,.06);
        padding: 18px;
      }

      .clx-core-card h3 {
        margin: 0 0 12px;
        font-size: 18px;
      }

      .clx-core-field {
        display: grid;
        gap: 7px;
        margin: 10px 0;
      }

      .clx-core-field span {
        color: rgba(255,255,255,.68);
        font-size: 11px;
        letter-spacing: .12em;
        text-transform: uppercase;
        font-weight: 900;
      }

      .clx-core-field input,
      .clx-core-field select {
        width: 100%;
        box-sizing: border-box;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(0,0,0,.32);
        color: #fff;
        padding: 12px 13px;
        outline: none;
      }

      .clx-core-save {
        border: 0;
        border-radius: 16px;
        background: linear-gradient(135deg, #ff1aa6, #8b4dff);
        color: #fff;
        padding: 12px 16px;
        cursor: pointer;
        font-weight: 1000;
        margin-top: 10px;
      }

      .clx-core-muted {
        color: rgba(255,255,255,.64);
        font-size: 13px;
        line-height: 1.45;
      }

      .clx-core-status {
        margin-top: 12px;
        min-height: 20px;
        font-weight: 800;
      }

      .clx-core-status.ok { color: #2fff9d; }
      .clx-core-status.err { color: #ff6b96; }

      @media (max-width: 820px) {
        .clx-core-grid {
          grid-template-columns: 1fr;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function insertButtons() {
    installStyles();

    if (document.getElementById("clxCoreActions")) return;

    const sidebar = findSidebar();
    if (!sidebar) return;

    const box = document.createElement("div");
    box.id = "clxCoreActions";
    box.className = "clx-core-actions";
    box.innerHTML = `
      <button class="clx-core-action-btn" id="clxOpenCoreSettings" type="button">⚙ Ajustes</button>
      <button class="clx-core-action-btn clx-core-logout" id="clxCoreLogout" type="button">⏻ Cerrar sesión</button>
    `;

    sidebar.appendChild(box);

    const topSettings = document.getElementById("clxAccountSettingsBtn");
    const topLogout = document.getElementById("clxAccountLogoutBtn");

    if (topSettings) topSettings.style.display = "none";
    if (topLogout) topLogout.style.display = "none";

    document.getElementById("clxOpenCoreSettings")?.addEventListener("click", openModal);
    document.getElementById("clxCoreLogout")?.addEventListener("click", doLogout);
  }

  function status(node, message, type = "ok") {
    if (!node) return;
    node.textContent = message;
    node.className = `clx-core-status ${type}`;
  }

  async function openModal() {
    installStyles();

    const existing = document.getElementById("clxCoreSettingsModal");
    if (existing) existing.remove();

    const settings = await loadCoreSettings();

    const overlay = document.createElement("div");
    overlay.id = "clxCoreSettingsModal";
    overlay.className = "clx-core-modal-backdrop";
    overlay.innerHTML = `
      <div class="clx-core-modal" role="dialog" aria-modal="true">
        <div class="clx-core-modal-head">
          <div>
            <div class="clx-core-muted">CORE SETTINGS</div>
            <h2>Ajustes</h2>
            <p class="clx-core-muted">Configuración núcleo del portal cliente para esta empresa.</p>
          </div>
          <button class="clx-core-close" type="button" data-clx-core-close>✕</button>
        </div>

        <div class="clx-core-grid">
          <section class="clx-core-card">
            <h3>Preferencias del panel</h3>

            <label class="clx-core-field">
              <span>Idioma</span>
              <select id="clxCoreLanguage">
                <option value="es">Español</option>
                <option value="en">English</option>
                <option value="fr">Français</option>
              </select>
            </label>

            <label class="clx-core-field">
              <span>Bloqueo por inactividad</span>
              <select id="clxCoreTimeout">
                <option value="15">15 minutos</option>
                <option value="30">30 minutos</option>
                <option value="60">60 minutos</option>
              </select>
            </label>

            <label class="clx-core-field">
              <span>Moneda</span>
              <select id="clxCoreCurrency">
                <option value="COP">COP</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="MXN">MXN</option>
                <option value="CLP">CLP</option>
                <option value="PEN">PEN</option>
              </select>
            </label>

            <label class="clx-core-field">
              <span>Zona horaria detectada</span>
              <input id="clxCoreTimezone" value="${escapeHtml(settings.timezone || detectedTimezone())}" />
            </label>

            <button class="clx-core-save" id="clxSaveCorePreferences" type="button">Guardar ajustes</button>
            <div class="clx-core-status" id="clxCorePreferencesStatus"></div>
          </section>

          <section class="clx-core-card">
            <h3>Cambiar correo</h3>

            <label class="clx-core-field">
              <span>Nuevo correo</span>
              <input id="clxCoreNewEmail" type="email" placeholder="nuevo@empresa.com" />
            </label>

            <label class="clx-core-field">
              <span>Contraseña actual</span>
              <input id="clxCoreEmailPassword" type="password" autocomplete="current-password" />
            </label>

            <button class="clx-core-save" id="clxSaveCoreEmail" type="button">Cambiar correo</button>
            <div class="clx-core-status" id="clxCoreEmailStatus"></div>
          </section>

          <section class="clx-core-card">
            <h3>Cambiar contraseña</h3>

            <label class="clx-core-field">
              <span>Contraseña actual</span>
              <input id="clxCoreCurrentPassword" type="password" autocomplete="current-password" />
            </label>

            <label class="clx-core-field">
              <span>Nueva contraseña</span>
              <input id="clxCoreNewPassword" type="password" autocomplete="new-password" />
            </label>

            <label class="clx-core-field">
              <span>Confirmar nueva contraseña</span>
              <input id="clxCoreConfirmPassword" type="password" autocomplete="new-password" />
            </label>

            <button class="clx-core-save" id="clxSaveCorePassword" type="button">Cambiar contraseña</button>
            <div class="clx-core-status" id="clxCorePasswordStatus"></div>
          </section>

          <section class="clx-core-card">
            <h3>Sesión</h3>
            <p class="clx-core-muted">
              El cierre por inactividad se aplica en este navegador según el tiempo configurado.
              El botón Cerrar sesión limpia la sesión local y regresa al login.
            </p>
            <button class="clx-core-save" id="clxCoreLogoutFromModal" type="button">Cerrar sesión</button>
          </section>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    const lang = String(settings.language || "es").toLowerCase();
    const timeout = String(settings.session_timeout_minutes || 30);
    const currency = String(settings.currency || "COP").toUpperCase();

    const langEl = document.getElementById("clxCoreLanguage");
    const timeoutEl = document.getElementById("clxCoreTimeout");
    const currencyEl = document.getElementById("clxCoreCurrency");

    if (langEl) langEl.value = ["es", "en", "fr"].includes(lang) ? lang : "es";
    if (timeoutEl) timeoutEl.value = ["15", "30", "60"].includes(timeout) ? timeout : "30";
    if (currencyEl) currencyEl.value = ["COP", "USD", "EUR", "MXN", "CLP", "PEN"].includes(currency) ? currency : "COP";

    overlay.querySelector("[data-clx-core-close]")?.addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) overlay.remove();
    });

    document.getElementById("clxSaveCorePreferences")?.addEventListener("click", savePreferences);
    document.getElementById("clxSaveCoreEmail")?.addEventListener("click", changeEmail);
    document.getElementById("clxSaveCorePassword")?.addEventListener("click", changePassword);
    document.getElementById("clxCoreLogoutFromModal")?.addEventListener("click", doLogout);
  }

  async function savePreferences() {
    const node = document.getElementById("clxCorePreferencesStatus");
    try {
      const payload = {
        language: document.getElementById("clxCoreLanguage")?.value || "es",
        session_timeout_minutes: Number(document.getElementById("clxCoreTimeout")?.value || 30),
        currency: document.getElementById("clxCoreCurrency")?.value || "COP",
        timezone: document.getElementById("clxCoreTimezone")?.value || detectedTimezone(),
      };

      await saveCoreSettings(payload);
      status(node, "Ajustes guardados correctamente.", "ok");
    } catch (error) {
      status(node, error.message || "No se pudieron guardar los ajustes.", "err");
    }
  }

  async function changeEmail() {
    const node = document.getElementById("clxCoreEmailStatus");
    try {
      if (!token()) throw new Error("No hay sesión activa. Ingresa nuevamente desde /login.");

      const newEmail = String(document.getElementById("clxCoreNewEmail")?.value || "").trim();
      const currentPassword = String(document.getElementById("clxCoreEmailPassword")?.value || "");

      if (!newEmail || !newEmail.includes("@")) throw new Error("Ingresa un correo válido.");
      if (!currentPassword) throw new Error("Ingresa la contraseña actual.");

      await api("/auth/account/email", {
        method: "PATCH",
        auth: true,
        body: JSON.stringify({
          new_email: newEmail,
          current_password: currentPassword,
        }),
      });

      status(node, "Correo actualizado correctamente.", "ok");
    } catch (error) {
      status(node, error.message || "No se pudo cambiar el correo.", "err");
    }
  }

  async function changePassword() {
    const node = document.getElementById("clxCorePasswordStatus");
    try {
      if (!token()) throw new Error("No hay sesión activa. Ingresa nuevamente desde /login.");

      const currentPassword = String(document.getElementById("clxCoreCurrentPassword")?.value || "");
      const newPassword = String(document.getElementById("clxCoreNewPassword")?.value || "");
      const confirmPassword = String(document.getElementById("clxCoreConfirmPassword")?.value || "");

      if (!currentPassword) throw new Error("Ingresa la contraseña actual.");
      if (newPassword.length < 8) throw new Error("La nueva contraseña debe tener mínimo 8 caracteres.");
      if (newPassword !== confirmPassword) throw new Error("La confirmación no coincide.");

      await api("/auth/account/password", {
        method: "PATCH",
        auth: true,
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      status(node, "Contraseña actualizada correctamente.", "ok");
    } catch (error) {
      status(node, error.message || "No se pudo cambiar la contraseña.", "err");
    }
  }

  function clearSession() {
    const keys = [
      "clonexa_access_token",
      "clonexa_token",
      "clonexa_client_token",
      "access_token",
      "token",
      "auth_token",
      "jwt",
      "clonexa_logout_reason",
    ];

    keys.forEach((key) => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    });
  }

  async function doLogout() {
    try {
      if (token()) {
        await api("/auth/logout", {
          method: "POST",
          auth: true,
          body: JSON.stringify({}),
        });
      }
    } catch (_) {}

    clearSession();

    const id = companyId();
    const suffix = id ? `?company_id=${encodeURIComponent(id)}` : "";
    window.location.href = `/login${suffix}`;
  }

  let inactivityTimer = null;

  function installInactivityGuard() {
    const minutes = Number(localStorage.getItem(SESSION_KEY) || 30);
    const ms = [15, 30, 60].includes(minutes) ? minutes * 60 * 1000 : 30 * 60 * 1000;

    function reset() {
      clearTimeout(inactivityTimer);
      inactivityTimer = setTimeout(() => {
        localStorage.setItem("clonexa_logout_reason", "session_timeout");
        doLogout();
      }, ms);
    }

    ["click", "keydown", "mousemove", "scroll", "touchstart"].forEach((eventName) => {
      window.removeEventListener(eventName, reset, true);
      window.addEventListener(eventName, reset, true);
    });

    reset();
  }

  async function init() {
    installStyles();
    insertButtons();

    const settings = await loadCoreSettings();
    localStorage.setItem(LANG_KEY, settings.language || "es");
    localStorage.setItem(SESSION_KEY, String(settings.session_timeout_minutes || 30));
    localStorage.setItem(currencyKey(), settings.currency || "COP");
    localStorage.setItem(timezoneKey(), settings.timezone || detectedTimezone());

    installInactivityGuard();

    const observer = new MutationObserver(() => insertButtons());
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();


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

