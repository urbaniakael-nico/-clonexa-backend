from pathlib import Path
import re

root = Path(".")
router_path = Path("app/api/v1/router.py")
client_js_path = Path("app/web/client.js")
client_html_path = Path("app/web/client.html")
endpoint_path = Path("app/api/v1/endpoints/core_settings.py")
client_settings_js_path = Path("app/web/client_core_settings.js")
migration_dir = Path("migrations/versions")

# ---------------------------------------------------------------------
# 1) Migration dinámica: company_core_settings
# ---------------------------------------------------------------------
def parse_assign(text, name):
    m = re.search(rf"^\s*{name}\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
    if m:
        return m.group(1)
    m = re.search(rf"^\s*{name}\s*=\s*\(([^)]*)\)", text, re.M)
    if m:
        return tuple(re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)))
    return None

revisions = set()
down_refs = set()

for f in migration_dir.glob("*.py"):
    t = f.read_text(encoding="utf-8", errors="ignore")
    rev = parse_assign(t, "revision")
    down = parse_assign(t, "down_revision")
    if rev:
        revisions.add(rev)
    if isinstance(down, tuple):
        down_refs.update([x for x in down if x])
    elif down:
        down_refs.add(down)

heads = sorted(revisions - down_refs)
if not heads:
    raise SystemExit("No pude detectar head de Alembic.")

if len(heads) == 1:
    down_revision_literal = repr(heads[0])
else:
    down_revision_literal = "(" + ", ".join(repr(x) for x in heads) + ",)"

migration_path = migration_dir / "020b_core_company_settings.py"

if not migration_path.exists():
    migration_path.write_text(f'''"""020b core company settings

Revision ID: 020b_core_company_settings
Revises: {", ".join(heads)}
Create Date: 2026-05-07
"""

from alembic import op

revision = "020b_core_company_settings"
down_revision = {down_revision_literal}
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS company_core_settings (
        company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
        language VARCHAR(5) NOT NULL DEFAULT 'es',
        session_timeout_minutes INTEGER NOT NULL DEFAULT 30,
        currency VARCHAR(12) NOT NULL DEFAULT 'COP',
        timezone VARCHAR(80),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)

    op.execute("""
    INSERT INTO company_core_settings (
        company_id,
        language,
        session_timeout_minutes,
        currency,
        timezone,
        created_at,
        updated_at
    )
    SELECT
        id,
        'es',
        30,
        'COP',
        NULL,
        NOW(),
        NOW()
    FROM companies
    ON CONFLICT (company_id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_core_settings;")
''', encoding="utf-8")

# ---------------------------------------------------------------------
# 2) Endpoint backend
# ---------------------------------------------------------------------
endpoint_path.write_text(r'''from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db


router = APIRouter()


class CoreSettingsIn(BaseModel):
    language: str | None = None
    session_timeout_minutes: int | None = None
    currency: str | None = None
    timezone: str | None = None


def _company_uuid(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid company_id")


def _normalize_language(value: str | None) -> str:
    lang = str(value or "es").strip().lower()
    if lang not in {"es", "en", "fr"}:
        raise HTTPException(status_code=400, detail="language must be es, en or fr")
    return lang


def _normalize_timeout(value: int | None) -> int:
    timeout = int(value or 30)
    if timeout not in {15, 30, 60}:
        raise HTTPException(status_code=400, detail="session_timeout_minutes must be 15, 30 or 60")
    return timeout


def _normalize_currency(value: str | None) -> str:
    currency = str(value or "COP").strip().upper()
    allowed = {"COP", "USD", "EUR", "MXN", "CLP", "PEN"}
    if currency not in allowed:
        raise HTTPException(status_code=400, detail=f"currency must be one of {sorted(allowed)}")
    return currency


def _normalize_timezone(value: str | None) -> str | None:
    tz = str(value or "").strip()
    if not tz:
        return None
    if len(tz) > 80:
        raise HTTPException(status_code=400, detail="timezone too long")
    return tz


async def _ensure_company_exists(db: AsyncSession, company_id: str) -> None:
    result = await db.execute(
        text("SELECT id FROM companies WHERE id = CAST(:company_id AS UUID) LIMIT 1"),
        {"company_id": company_id},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Company not found")


async def _ensure_settings_row(db: AsyncSession, company_id: str) -> None:
    await db.execute(
        text(
            """
            INSERT INTO company_core_settings (
                company_id,
                language,
                session_timeout_minutes,
                currency,
                timezone,
                created_at,
                updated_at
            )
            VALUES (
                CAST(:company_id AS UUID),
                'es',
                30,
                'COP',
                NULL,
                NOW(),
                NOW()
            )
            ON CONFLICT (company_id) DO NOTHING
            """
        ),
        {"company_id": company_id},
    )


def _row_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_id": str(row["company_id"]),
        "language": row.get("language") or "es",
        "session_timeout_minutes": int(row.get("session_timeout_minutes") or 30),
        "currency": row.get("currency") or "COP",
        "timezone": row.get("timezone"),
        "updated_at": row.get("updated_at").isoformat() if isinstance(row.get("updated_at"), datetime) else row.get("updated_at"),
    }


@router.get("/{company_id}/core-settings")
async def get_company_core_settings(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company_id = _company_uuid(company_id)
    await _ensure_company_exists(db, company_id)
    await _ensure_settings_row(db, company_id)

    result = await db.execute(
        text(
            """
            SELECT
                company_id,
                language,
                session_timeout_minutes,
                currency,
                timezone,
                updated_at
            FROM company_core_settings
            WHERE company_id = CAST(:company_id AS UUID)
            LIMIT 1
            """
        ),
        {"company_id": company_id},
    )
    row = result.mappings().first()
    await db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Core settings not found")

    return _row_payload(dict(row))


@router.put("/{company_id}/core-settings")
async def update_company_core_settings(
    company_id: str,
    payload: CoreSettingsIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company_id = _company_uuid(company_id)
    await _ensure_company_exists(db, company_id)

    language = _normalize_language(payload.language)
    timeout = _normalize_timeout(payload.session_timeout_minutes)
    currency = _normalize_currency(payload.currency)
    timezone_value = _normalize_timezone(payload.timezone)

    result = await db.execute(
        text(
            """
            INSERT INTO company_core_settings (
                company_id,
                language,
                session_timeout_minutes,
                currency,
                timezone,
                created_at,
                updated_at
            )
            VALUES (
                CAST(:company_id AS UUID),
                :language,
                :session_timeout_minutes,
                :currency,
                :timezone,
                NOW(),
                NOW()
            )
            ON CONFLICT (company_id)
            DO UPDATE SET
                language = EXCLUDED.language,
                session_timeout_minutes = EXCLUDED.session_timeout_minutes,
                currency = EXCLUDED.currency,
                timezone = EXCLUDED.timezone,
                updated_at = NOW()
            RETURNING
                company_id,
                language,
                session_timeout_minutes,
                currency,
                timezone,
                updated_at
            """
        ),
        {
            "company_id": company_id,
            "language": language,
            "session_timeout_minutes": timeout,
            "currency": currency,
            "timezone": timezone_value,
        },
    )

    row = result.mappings().first()
    await db.commit()

    if not row:
        raise HTTPException(status_code=500, detail="Could not update core settings")

    return _row_payload(dict(row))
''', encoding="utf-8")

# ---------------------------------------------------------------------
# 3) Registrar router
# ---------------------------------------------------------------------
router_text = router_path.read_text(encoding="utf-8-sig")

if "core_settings_router" not in router_text:
    router_text = router_text.rstrip() + '''

# CLONEXA 020B core settings router
from app.api.v1.endpoints import core_settings as core_settings_router
api_router.include_router(core_settings_router.router, prefix="/companies", tags=["core_settings"])
'''
    router_path.write_text(router_text + "\n", encoding="utf-8")

# ---------------------------------------------------------------------
# 4) Ocultar core_settings/settings del menú normal de módulos cliente
# ---------------------------------------------------------------------
client_js = client_js_path.read_text(encoding="utf-8-sig")

old = 'return (Array.isArray(modules) ? modules : []).filter((item) => item.code !== "core");'
new = 'return (Array.isArray(modules) ? modules : []).filter((item) => !["core", "core_settings", "settings"].includes(item.code));'

if old in client_js:
    client_js = client_js.replace(old, new)
elif 'function visibleClientModules' in client_js and 'core_settings' not in client_js[client_js.find('function visibleClientModules'):client_js.find('function visibleClientModules') + 600]:
    client_js = client_js.replace(
        '.filter((item) => item.code !== "core")',
        '.filter((item) => !["core", "core_settings", "settings"].includes(item.code))'
    )

client_js_path.write_text(client_js, encoding="utf-8")

# ---------------------------------------------------------------------
# 5) JS seguro para botones Ajustes / Cerrar sesión + modal
# ---------------------------------------------------------------------
client_settings_js_path.write_text(r'''(function clonexaCoreSettingsClientModule() {
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
''', encoding="utf-8")

# ---------------------------------------------------------------------
# 6) Cargar client_core_settings.js después de client.js
# ---------------------------------------------------------------------
html = client_html_path.read_text(encoding="utf-8-sig")

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_core_settings\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

# Limpieza defensiva de traductores previos rotos si quedaran referenciados.
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_google_translate\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_i18n\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if matches:
    last = matches[-1]
    src = last.group(1)
    settings_src = re.sub(r'client\.js(?:\?[^"\']*)?', 'client_core_settings.js?v=020B', src)
    html = html[:last.end()] + f'\n<script src="{settings_src}"></script>\n' + html[last.end():]
else:
    tag = '\n<script src="/static/client_core_settings.js?v=020B"></script>\n'
    if re.search(r'</body\s*>', html, flags=re.IGNORECASE):
      html = re.sub(r'</body\s*>', tag + "\n</body>", html, flags=re.IGNORECASE)
    else:
      html = html.rstrip() + tag + "\n"

client_html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020B core settings backend + client module applied")
