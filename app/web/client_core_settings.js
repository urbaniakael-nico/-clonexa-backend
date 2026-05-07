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
