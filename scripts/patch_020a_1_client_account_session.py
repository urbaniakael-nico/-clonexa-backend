from pathlib import Path

auth_path = Path("app/api/v1/endpoints/auth.py")
client_path = Path("app/web/client.js")
login_path = Path("app/web/login.js")

auth = auth_path.read_text(encoding="utf-8-sig")
client = client_path.read_text(encoding="utf-8-sig")
login = login_path.read_text(encoding="utf-8-sig")

AUTH_MARKER = "# CLONEXA 020A-1 CLIENT ACCOUNT SESSION LAYER"
CLIENT_MARKER = "/* CLONEXA 020A-1 CLIENT ACCOUNT SESSION LAYER */"
LOGIN_MARKER = "/* CLONEXA 020A-1 LOGIN SESSION MESSAGE */"

if AUTH_MARKER not in auth:
    auth += r'''

# CLONEXA 020A-1 CLIENT ACCOUNT SESSION LAYER
from typing import Any as _Any
from uuid import UUID as _UUID
from datetime import datetime as _datetime

from fastapi import Request as _Request
from fastapi import Depends as _Depends
from fastapi import HTTPException as _HTTPException
from fastapi import status as _status
from pydantic import BaseModel as _BaseModel
from sqlalchemy import text as _sql_text
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

from app.api.deps import get_db as _get_db
from app.services.auth_service import decode_access_token as _decode_access_token
from app.services.auth_service import verify_password as _verify_password
from app.services.auth_service import hash_password as _hash_password


class _ClientPasswordChangeIn(_BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class _ClientEmailChangeIn(_BaseModel):
    current_password: str
    new_email: str


class _ClientPreferencesIn(_BaseModel):
    language: str | None = None
    session_timeout_minutes: int | None = None


def _020a_now_iso(value: _Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, _datetime):
        return value.isoformat()
    return str(value)


async def _020a_ensure_client_account_storage(db: _AsyncSession) -> None:
    await db.execute(_sql_text("""
        ALTER TABLE company_users
        ADD COLUMN IF NOT EXISTS language varchar(8) NOT NULL DEFAULT 'es';
    """))
    await db.execute(_sql_text("""
        ALTER TABLE company_users
        ADD COLUMN IF NOT EXISTS session_timeout_minutes integer NOT NULL DEFAULT 30;
    """))
    await db.execute(_sql_text("""
        ALTER TABLE company_users
        ADD COLUMN IF NOT EXISTS temporary_password boolean NOT NULL DEFAULT false;
    """))
    await db.execute(_sql_text("""
        ALTER TABLE company_users
        ADD COLUMN IF NOT EXISTS last_email_change_at timestamp with time zone NULL;
    """))
    await db.execute(_sql_text("""
        ALTER TABLE company_users
        ADD COLUMN IF NOT EXISTS last_logout_at timestamp with time zone NULL;
    """))
    await db.execute(_sql_text("""
        ALTER TABLE company_users
        ALTER COLUMN must_change_password SET DEFAULT true;
    """))
    await db.execute(_sql_text("""
        CREATE TABLE IF NOT EXISTS company_user_security_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            company_user_id uuid NOT NULL,
            event_type varchar(80) NOT NULL,
            payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamp with time zone NOT NULL DEFAULT now()
        );
    """))
    await db.commit()


def _020a_bearer_token(request: _Request) -> str:
    raw = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    raw = raw.strip()
    if not raw.lower().startswith("bearer "):
        raise _HTTPException(
            status_code=_status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = raw.split(" ", 1)[1].strip()
    if not token:
        raise _HTTPException(
            status_code=_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
    return token


def _020a_payload_user_id(payload: dict[str, _Any]) -> str | None:
    for key in ("sub", "user_id", "company_user_id", "id"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _020a_payload_company_id(payload: dict[str, _Any]) -> str | None:
    for key in ("company_id", "tenant_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


async def _020a_current_user(db: _AsyncSession, request: _Request) -> dict[str, _Any]:
    await _020a_ensure_client_account_storage(db)

    token = _020a_bearer_token(request)
    try:
        payload = _decode_access_token(token)
    except Exception:
        raise _HTTPException(
            status_code=_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user_ref = _020a_payload_user_id(payload)
    company_ref = _020a_payload_company_id(payload)

    if not user_ref:
        raise _HTTPException(
            status_code=_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    params: dict[str, _Any] = {"user_ref": user_ref}
    company_filter = ""
    if company_ref:
        company_filter = "AND company_id = CAST(:company_ref AS uuid)"
        params["company_ref"] = company_ref

    query = """
        SELECT
            id,
            company_id,
            email,
            password_hash,
            full_name,
            role,
            status,
            must_change_password,
            temporary_password,
            failed_login_attempts,
            locked_until,
            last_login_at,
            password_changed_at,
            last_password_reset_at,
            last_email_change_at,
            last_logout_at,
            language,
            session_timeout_minutes,
            settings_json,
            created_at,
            updated_at
        FROM company_users
        WHERE (
            id::text = :user_ref
            OR lower(email) = lower(:user_ref)
        )
        {company_filter}
        LIMIT 1
    """.format(company_filter=company_filter)

    result = await db.execute(_sql_text(query), params)
    row = result.mappings().first()

    if not row:
        raise _HTTPException(
            status_code=_status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if str(row.get("status") or "").lower() not in {"active", "activo"}:
        raise _HTTPException(
            status_code=_status.HTTP_403_FORBIDDEN,
            detail="User inactive",
        )

    return dict(row)


async def _020a_log_security_event(
    db: _AsyncSession,
    *,
    user: dict[str, _Any],
    event_type: str,
    payload: dict[str, _Any] | None = None,
) -> None:
    await db.execute(
        _sql_text("""
            INSERT INTO company_user_security_events (
                company_id,
                company_user_id,
                event_type,
                payload_json
            )
            VALUES (
                :company_id,
                :company_user_id,
                :event_type,
                CAST(:payload_json AS jsonb)
            )
        """),
        {
            "company_id": str(user["company_id"]),
            "company_user_id": str(user["id"]),
            "event_type": event_type,
            "payload_json": __import__("json").dumps(payload or {}),
        },
    )


def _020a_account_response(user: dict[str, _Any]) -> dict[str, _Any]:
    language = (user.get("language") or "es").strip().lower()
    if language not in {"es", "en", "fr"}:
        language = "es"

    timeout = int(user.get("session_timeout_minutes") or 30)
    if timeout not in {15, 30, 60}:
        timeout = 30

    return {
        "id": str(user["id"]),
        "company_id": str(user["company_id"]),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "role": user.get("role"),
        "status": user.get("status"),
        "must_change_password": bool(user.get("must_change_password")),
        "temporary_password": bool(user.get("temporary_password")),
        "language": language,
        "session_timeout_minutes": timeout,
        "last_login_at": _020a_now_iso(user.get("last_login_at")),
        "password_changed_at": _020a_now_iso(user.get("password_changed_at")),
        "last_email_change_at": _020a_now_iso(user.get("last_email_change_at")),
    }


def _020a_validate_email(value: str) -> str:
    email = (value or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 180:
        raise _HTTPException(status_code=400, detail="Invalid email")
    return email


def _020a_validate_language(value: str | None) -> str | None:
    if value is None:
        return None
    lang = value.strip().lower()
    if lang not in {"es", "en", "fr"}:
        raise _HTTPException(status_code=400, detail="Invalid language")
    return lang


def _020a_validate_timeout(value: int | None) -> int | None:
    if value is None:
        return None
    timeout = int(value)
    if timeout not in {15, 30, 60}:
        raise _HTTPException(status_code=400, detail="Invalid session timeout")
    return timeout


@router.get("/account")
async def client_account(
    request: _Request,
    db: _AsyncSession = _Depends(_get_db),
) -> dict[str, _Any]:
    user = await _020a_current_user(db, request)
    return _020a_account_response(user)


@router.patch("/account/preferences")
async def client_account_preferences(
    payload: _ClientPreferencesIn,
    request: _Request,
    db: _AsyncSession = _Depends(_get_db),
) -> dict[str, _Any]:
    user = await _020a_current_user(db, request)

    language = _020a_validate_language(payload.language)
    timeout = _020a_validate_timeout(payload.session_timeout_minutes)

    updates = []
    params: dict[str, _Any] = {"user_id": str(user["id"])}

    if language is not None:
        updates.append("language = :language")
        params["language"] = language

    if timeout is not None:
        updates.append("session_timeout_minutes = :timeout")
        params["timeout"] = timeout

    if not updates:
        return _020a_account_response(user)

    updates.append("updated_at = now()")

    await db.execute(
        _sql_text(f"""
            UPDATE company_users
            SET {", ".join(updates)}
            WHERE id = CAST(:user_id AS uuid)
        """),
        params,
    )

    await _020a_log_security_event(
        db,
        user=user,
        event_type="preferences_changed",
        payload={"language": language, "session_timeout_minutes": timeout},
    )

    await db.commit()

    fresh = await _020a_current_user(db, request)
    return _020a_account_response(fresh)


@router.patch("/account/email")
async def client_account_email(
    payload: _ClientEmailChangeIn,
    request: _Request,
    db: _AsyncSession = _Depends(_get_db),
) -> dict[str, _Any]:
    user = await _020a_current_user(db, request)

    if not _verify_password(payload.current_password, str(user.get("password_hash") or "")):
        raise _HTTPException(status_code=400, detail="Current password is incorrect")

    new_email = _020a_validate_email(payload.new_email)

    existing = await db.execute(
        _sql_text("""
            SELECT id
            FROM company_users
            WHERE lower(email) = lower(:email)
              AND id <> CAST(:user_id AS uuid)
            LIMIT 1
        """),
        {"email": new_email, "user_id": str(user["id"])},
    )
    if existing.mappings().first():
        raise _HTTPException(status_code=409, detail="Email already exists")

    await db.execute(
        _sql_text("""
            UPDATE company_users
            SET email = :email,
                last_email_change_at = now(),
                updated_at = now()
            WHERE id = CAST(:user_id AS uuid)
        """),
        {"email": new_email, "user_id": str(user["id"])},
    )

    await _020a_log_security_event(
        db,
        user=user,
        event_type="email_changed",
        payload={"old_email": user.get("email"), "new_email": new_email},
    )

    await db.commit()

    fresh = await _020a_current_user(db, request)
    return _020a_account_response(fresh)


@router.patch("/account/password")
async def client_account_password(
    payload: _ClientPasswordChangeIn,
    request: _Request,
    db: _AsyncSession = _Depends(_get_db),
) -> dict[str, _Any]:
    user = await _020a_current_user(db, request)

    current_password = payload.current_password or ""
    new_password = payload.new_password or ""
    confirm_password = payload.confirm_password or ""

    if not _verify_password(current_password, str(user.get("password_hash") or "")):
        raise _HTTPException(status_code=400, detail="Current password is incorrect")

    if len(new_password) < 8:
        raise _HTTPException(status_code=400, detail="Password must have at least 8 characters")

    if new_password != confirm_password:
        raise _HTTPException(status_code=400, detail="Password confirmation does not match")

    await db.execute(
        _sql_text("""
            UPDATE company_users
            SET password_hash = :password_hash,
                must_change_password = false,
                temporary_password = false,
                password_changed_at = now(),
                failed_login_attempts = 0,
                locked_until = NULL,
                updated_at = now()
            WHERE id = CAST(:user_id AS uuid)
        """),
        {
            "password_hash": _hash_password(new_password),
            "user_id": str(user["id"]),
        },
    )

    await _020a_log_security_event(
        db,
        user=user,
        event_type="password_changed",
        payload={"forced": bool(user.get("must_change_password") or user.get("temporary_password"))},
    )

    await db.commit()

    fresh = await _020a_current_user(db, request)
    return _020a_account_response(fresh)


@router.post("/logout")
async def client_logout(
    request: _Request,
    db: _AsyncSession = _Depends(_get_db),
) -> dict[str, _Any]:
    user = await _020a_current_user(db, request)

    await db.execute(
        _sql_text("""
            UPDATE company_users
            SET last_logout_at = now(),
                updated_at = now()
            WHERE id = CAST(:user_id AS uuid)
        """),
        {"user_id": str(user["id"])},
    )

    await _020a_log_security_event(
        db,
        user=user,
        event_type="logout",
        payload={},
    )

    await db.commit()

    return {"ok": True}
'''

if CLIENT_MARKER not in client:
    client += r'''

/* CLONEXA 020A-1 CLIENT ACCOUNT SESSION LAYER */
(function clonexaClientAccountSessionLayer() {
  "use strict";

  const TOKEN_KEY = "clonexa_access_token";
  const COMPANY_KEY = "clonexa_company_id";
  const LEGACY_COMPANY_KEY = "company_id";

  const TEXT = {
    es: {
      settings: "Configuración",
      logout: "Salir",
      title: "Configuración de cuenta",
      firstLogin: "Primer ingreso: cambia tu contraseña",
      account: "Cuenta",
      email: "Correo",
      newEmail: "Nuevo correo",
      currentPassword: "Contraseña actual",
      newPassword: "Nueva contraseña",
      confirmPassword: "Confirmar contraseña",
      language: "Idioma",
      session: "Sesión",
      timeout: "Tiempo de ventana abierta",
      save: "Guardar cambios",
      close: "Cerrar",
      saved: "Configuración guardada.",
      passwordRequired: "Debes cambiar la contraseña para continuar.",
      sessionExpired: "Sesión expirada por inactividad.",
      adminHint: "Panel cliente CLONEXA",
      passwordHelp: "Deja nueva contraseña vacía si no deseas cambiarla.",
      emailHelp: "Deja nuevo correo vacío si no deseas cambiarlo."
    },
    en: {
      settings: "Settings",
      logout: "Log out",
      title: "Account settings",
      firstLogin: "First login: change your password",
      account: "Account",
      email: "Email",
      newEmail: "New email",
      currentPassword: "Current password",
      newPassword: "New password",
      confirmPassword: "Confirm password",
      language: "Language",
      session: "Session",
      timeout: "Open session window",
      save: "Save changes",
      close: "Close",
      saved: "Settings saved.",
      passwordRequired: "You must change your password to continue.",
      sessionExpired: "Session expired due to inactivity.",
      adminHint: "CLONEXA client panel",
      passwordHelp: "Leave new password empty if you do not want to change it.",
      emailHelp: "Leave new email empty if you do not want to change it."
    },
    fr: {
      settings: "Configuration",
      logout: "Quitter",
      title: "Configuration du compte",
      firstLogin: "Première connexion : changez votre mot de passe",
      account: "Compte",
      email: "E-mail",
      newEmail: "Nouvel e-mail",
      currentPassword: "Mot de passe actuel",
      newPassword: "Nouveau mot de passe",
      confirmPassword: "Confirmer le mot de passe",
      language: "Langue",
      session: "Session",
      timeout: "Fenêtre de session ouverte",
      save: "Enregistrer",
      close: "Fermer",
      saved: "Configuration enregistrée.",
      passwordRequired: "Vous devez changer votre mot de passe pour continuer.",
      sessionExpired: "Session expirée pour inactivité.",
      adminHint: "Panneau client CLONEXA",
      passwordHelp: "Laissez le nouveau mot de passe vide si vous ne souhaitez pas le changer.",
      emailHelp: "Laissez le nouvel e-mail vide si vous ne souhaitez pas le changer."
    }
  };

  let account = null;
  let idleTimer = null;
  let forced = false;

  function token() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function companyId() {
    const params = new URLSearchParams(window.location.search);
    return (
      params.get("company_id") ||
      params.get("companyId") ||
      localStorage.getItem(COMPANY_KEY) ||
      localStorage.getItem(LEGACY_COMPANY_KEY) ||
      ""
    );
  }

  function lang() {
    const value = (account && account.language) || localStorage.getItem("clonexa_client_language") || "es";
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function t(key) {
    const pack = TEXT[lang()] || TEXT.es;
    return pack[key] || TEXT.es[key] || key;
  }

  function headers() {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token()}`
    };
  }

  async function accountApi(path, options) {
    const response = await fetch(`/api/v1/auth${path}`, Object.assign({
      headers: headers()
    }, options || {}));

    let data = {};
    try {
      data = await response.json();
    } catch (_) {
      data = {};
    }

    if (!response.ok) {
      throw new Error(data.detail || data.message || `HTTP ${response.status}`);
    }

    return data;
  }

  function installStyles() {
    if (document.getElementById("clx-account-layer-style")) return;

    const style = document.createElement("style");
    style.id = "clx-account-layer-style";
    style.textContent = `
      .clx-account-bar {
        position: fixed;
        top: 14px;
        right: 14px;
        z-index: 99980;
        display: flex;
        gap: 8px;
        align-items: center;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .clx-account-pill {
        background: rgba(15, 23, 42, 0.92);
        color: #fff;
        border: 1px solid rgba(255,255,255,0.14);
        border-radius: 999px;
        padding: 9px 13px;
        font-size: 13px;
        box-shadow: 0 12px 30px rgba(0,0,0,0.18);
        cursor: pointer;
      }
      .clx-account-pill.secondary {
        background: rgba(255,255,255,0.96);
        color: #0f172a;
        border-color: rgba(15,23,42,0.12);
      }
      .clx-account-overlay {
        position: fixed;
        inset: 0;
        z-index: 99990;
        background: rgba(15, 23, 42, 0.52);
        display: none;
        align-items: center;
        justify-content: center;
        padding: 24px;
      }
      .clx-account-overlay.open {
        display: flex;
      }
      .clx-account-modal {
        width: min(560px, 96vw);
        max-height: 92vh;
        overflow: auto;
        background: #fff;
        color: #0f172a;
        border-radius: 24px;
        box-shadow: 0 30px 80px rgba(0,0,0,0.35);
        padding: 24px;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .clx-account-modal h2 {
        margin: 0 0 4px;
        font-size: 22px;
      }
      .clx-account-muted {
        color: #64748b;
        font-size: 13px;
        margin: 0 0 18px;
      }
      .clx-account-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 12px;
      }
      .clx-account-grid label {
        display: grid;
        gap: 6px;
        font-size: 13px;
        font-weight: 700;
      }
      .clx-account-grid input,
      .clx-account-grid select {
        width: 100%;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 11px 12px;
        font-size: 14px;
      }
      .clx-account-section {
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 16px;
        margin-top: 14px;
      }
      .clx-account-section h3 {
        margin: 0 0 10px;
        font-size: 15px;
      }
      .clx-account-actions {
        display: flex;
        gap: 10px;
        justify-content: flex-end;
        margin-top: 18px;
      }
      .clx-account-btn {
        border: 0;
        border-radius: 12px;
        padding: 11px 14px;
        font-weight: 800;
        cursor: pointer;
      }
      .clx-account-btn.primary {
        background: #111827;
        color: #fff;
      }
      .clx-account-btn.ghost {
        background: #f1f5f9;
        color: #0f172a;
      }
      .clx-account-status {
        margin-top: 12px;
        font-size: 13px;
        color: #166534;
      }
      .clx-account-status.error {
        color: #b91c1c;
      }
      .clx-account-forced .clx-account-close {
        display: none;
      }
    `;
    document.head.appendChild(style);
  }

  function renderShell() {
    if (document.getElementById("clx-account-bar")) return;

    const bar = document.createElement("div");
    bar.id = "clx-account-bar";
    bar.className = "clx-account-bar";
    bar.innerHTML = `
      <button type="button" class="clx-account-pill secondary" id="clxAccountSettingsBtn">⚙ ${t("settings")}</button>
      <button type="button" class="clx-account-pill" id="clxAccountLogoutBtn">⏻ ${t("logout")}</button>
    `;
    document.body.appendChild(bar);

    const overlay = document.createElement("div");
    overlay.id = "clx-account-overlay";
    overlay.className = "clx-account-overlay";
    overlay.innerHTML = `
      <div class="clx-account-modal" id="clx-account-modal">
        <h2 id="clxAccountTitle">${t("title")}</h2>
        <p class="clx-account-muted" id="clxAccountSubtitle">${t("adminHint")}</p>

        <div class="clx-account-section">
          <h3>${t("account")}</h3>
          <div class="clx-account-grid">
            <label>
              ${t("email")}
              <input id="clxAccountEmail" type="email" disabled>
            </label>
            <p class="clx-account-muted">${t("emailHelp")}</p>
            <label>
              ${t("newEmail")}
              <input id="clxAccountNewEmail" type="email" autocomplete="email">
            </label>
          </div>
        </div>

        <div class="clx-account-section">
          <h3>${t("session")}</h3>
          <div class="clx-account-grid">
            <label>
              ${t("language")}
              <select id="clxAccountLanguage">
                <option value="es">Español</option>
                <option value="en">English</option>
                <option value="fr">Français</option>
              </select>
            </label>
            <label>
              ${t("timeout")}
              <select id="clxAccountTimeout">
                <option value="15">15 min</option>
                <option value="30">30 min</option>
                <option value="60">60 min</option>
              </select>
            </label>
          </div>
        </div>

        <div class="clx-account-section">
          <h3>${t("newPassword")}</h3>
          <p class="clx-account-muted">${t("passwordHelp")}</p>
          <div class="clx-account-grid">
            <label>
              ${t("currentPassword")}
              <input id="clxAccountCurrentPassword" type="password" autocomplete="current-password">
            </label>
            <label>
              ${t("newPassword")}
              <input id="clxAccountNewPassword" type="password" autocomplete="new-password">
            </label>
            <label>
              ${t("confirmPassword")}
              <input id="clxAccountConfirmPassword" type="password" autocomplete="new-password">
            </label>
          </div>
        </div>

        <div id="clxAccountStatus" class="clx-account-status"></div>

        <div class="clx-account-actions">
          <button type="button" class="clx-account-btn ghost clx-account-close" id="clxAccountCloseBtn">${t("close")}</button>
          <button type="button" class="clx-account-btn primary" id="clxAccountSaveBtn">${t("save")}</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    document.getElementById("clxAccountSettingsBtn").addEventListener("click", () => openSettings(false));
    document.getElementById("clxAccountLogoutBtn").addEventListener("click", () => logout("manual"));
    document.getElementById("clxAccountCloseBtn").addEventListener("click", closeSettings);
    document.getElementById("clxAccountSaveBtn").addEventListener("click", saveSettings);
  }

  function refreshTexts() {
    const settingsBtn = document.getElementById("clxAccountSettingsBtn");
    const logoutBtn = document.getElementById("clxAccountLogoutBtn");
    if (settingsBtn) settingsBtn.textContent = `⚙ ${t("settings")}`;
    if (logoutBtn) logoutBtn.textContent = `⏻ ${t("logout")}`;
    document.documentElement.lang = lang();
  }

  function fillForm() {
    if (!account) return;
    const email = document.getElementById("clxAccountEmail");
    const newEmail = document.getElementById("clxAccountNewEmail");
    const langEl = document.getElementById("clxAccountLanguage");
    const timeoutEl = document.getElementById("clxAccountTimeout");
    const status = document.getElementById("clxAccountStatus");

    if (email) email.value = account.email || "";
    if (newEmail) newEmail.value = "";
    if (langEl) langEl.value = account.language || "es";
    if (timeoutEl) timeoutEl.value = String(account.session_timeout_minutes || 30);
    if (status) {
      status.textContent = "";
      status.classList.remove("error");
    }
  }

  function openSettings(force) {
    forced = Boolean(force);
    const overlay = document.getElementById("clx-account-overlay");
    const modal = document.getElementById("clx-account-modal");
    const title = document.getElementById("clxAccountTitle");
    const subtitle = document.getElementById("clxAccountSubtitle");

    if (!overlay || !modal) return;

    fillForm();

    modal.classList.toggle("clx-account-forced", forced);
    if (title) title.textContent = forced ? t("firstLogin") : t("title");
    if (subtitle) subtitle.textContent = forced ? t("passwordRequired") : t("adminHint");

    overlay.classList.add("open");
  }

  function closeSettings() {
    if (forced) return;
    const overlay = document.getElementById("clx-account-overlay");
    if (overlay) overlay.classList.remove("open");
  }

  function setStatus(message, isError) {
    const status = document.getElementById("clxAccountStatus");
    if (!status) return;
    status.textContent = message || "";
    status.classList.toggle("error", Boolean(isError));
  }

  async function saveSettings() {
    try {
      setStatus("", false);

      const currentPassword = document.getElementById("clxAccountCurrentPassword").value || "";
      const newPassword = document.getElementById("clxAccountNewPassword").value || "";
      const confirmPassword = document.getElementById("clxAccountConfirmPassword").value || "";
      const newEmail = (document.getElementById("clxAccountNewEmail").value || "").trim();
      const language = document.getElementById("clxAccountLanguage").value || "es";
      const sessionTimeout = Number(document.getElementById("clxAccountTimeout").value || 30);

      account = await accountApi("/account/preferences", {
        method: "PATCH",
        body: JSON.stringify({
          language: language,
          session_timeout_minutes: sessionTimeout
        })
      });

      localStorage.setItem("clonexa_client_language", account.language || "es");

      if (newEmail) {
        if (!currentPassword) throw new Error(t("currentPassword"));
        account = await accountApi("/account/email", {
          method: "PATCH",
          body: JSON.stringify({
            current_password: currentPassword,
            new_email: newEmail
          })
        });
      }

      if (newPassword || confirmPassword || forced) {
        if (!currentPassword) throw new Error(t("currentPassword"));
        account = await accountApi("/account/password", {
          method: "PATCH",
          body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword,
            confirm_password: confirmPassword
          })
        });
      }

      refreshTexts();
      configureIdleTimeout();
      fillForm();
      setStatus(t("saved"), false);

      if (!account.must_change_password && !account.temporary_password) {
        forced = false;
        setTimeout(closeSettings, 700);
      }
    } catch (error) {
      setStatus(error.message || String(error), true);
    }
  }

  async function logout(reason) {
    try {
      if (token()) {
        await accountApi("/logout", { method: "POST", body: JSON.stringify({}) });
      }
    } catch (_) {}

    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem("clonexa_login_payload");
    localStorage.removeItem("clonexa_company_id");
    localStorage.removeItem("company_id");

    if (reason === "timeout") {
      localStorage.setItem("clonexa_logout_reason", t("sessionExpired"));
    }

    window.location.href = "/login";
  }

  function configureIdleTimeout() {
    if (idleTimer) clearTimeout(idleTimer);

    const minutes = Number((account && account.session_timeout_minutes) || 30);
    const ms = minutes * 60 * 1000;

    const reset = () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => logout("timeout"), ms);
    };

    ["click", "keydown", "scroll", "mousemove", "touchstart"].forEach((eventName) => {
      window.removeEventListener(eventName, reset, { passive: true });
      window.addEventListener(eventName, reset, { passive: true });
    });

    reset();
  }

  async function init() {
    if (!token()) return;

    installStyles();
    renderShell();

    try {
      account = await accountApi("/account", { method: "GET" });
      localStorage.setItem("clonexa_client_language", account.language || "es");
      localStorage.setItem("clonexa_company_id", account.company_id || companyId());
      localStorage.setItem("company_id", account.company_id || companyId());

      refreshTexts();
      configureIdleTimeout();

      if (account.must_change_password || account.temporary_password) {
        openSettings(true);
      }
    } catch (error) {
      console.warn("CLONEXA account layer disabled:", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
'''

if LOGIN_MARKER not in login:
    login += r'''

/* CLONEXA 020A-1 LOGIN SESSION MESSAGE */
(function clonexaLoginSessionMessage() {
  "use strict";

  function showReason() {
    const reason = localStorage.getItem("clonexa_logout_reason");
    if (!reason) return;

    localStorage.removeItem("clonexa_logout_reason");

    const msg = document.getElementById("loginMessage");
    if (msg) {
      msg.textContent = reason;
      msg.classList.add("error");
      return;
    }

    const box = document.createElement("div");
    box.textContent = reason;
    box.style.cssText = "margin:12px auto;padding:10px 14px;border-radius:12px;background:#fff7ed;color:#9a3412;max-width:520px;font-family:system-ui;";
    document.body.prepend(box);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", showReason);
  } else {
    showReason();
  }
})();
'''

auth_path.write_text(auth, encoding="utf-8")
client_path.write_text(client, encoding="utf-8")
login_path.write_text(login, encoding="utf-8")

print("PATCH_OK: 020A-1 client account/session layer applied")
