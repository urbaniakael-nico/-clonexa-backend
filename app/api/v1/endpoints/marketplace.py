from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import secrets
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.rest import Client as TwilioClient

from app.api.deps import get_db
from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    get_jwt_secret,
    hash_password,
    verify_password,
)


router = APIRouter()
MODULE_CODE = "marketplace_access"
TOKEN_MINUTES = 60 * 24 * 30
CODE_TTL_MINUTES = 5


class VerificationRequestIn(BaseModel):
    phone: str = Field(..., min_length=7, max_length=30)
    purpose: Literal["register", "reset"] = "register"


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    phone: str = Field(..., min_length=7, max_length=30)
    verification_code: str = Field(..., min_length=6, max_length=6)
    password: str = Field(..., min_length=8, max_length=72)


class LoginIn(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=1, max_length=72)


class ResetPasswordIn(BaseModel):
    phone: str = Field(..., min_length=7, max_length=30)
    verification_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=72)


class ProfileUpdateIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)


class PasswordUpdateIn(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=72)
    new_password: str = Field(..., min_length=8, max_length=72)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10 and digits.startswith("3"):
        digits = f"57{digits}"
    if not 10 <= len(digits) <= 15:
        raise HTTPException(status_code=400, detail="telefono_invalido")
    return f"+{digits}"


def normalize_username(value: str) -> tuple[str, str]:
    display = re.sub(r"\s+", " ", str(value or "").strip())
    if not 3 <= len(display) <= 40:
        raise HTTPException(status_code=400, detail="usuario_invalido")
    folded = unicodedata.normalize("NFD", display)
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    key = re.sub(r"[^a-z0-9_.-]+", "_", folded.lower()).strip("_.-")
    if not 3 <= len(key) <= 40:
        raise HTTPException(status_code=400, detail="usuario_invalido")
    return display, key


def validate_password(value: str) -> str:
    password = str(value or "")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="contrasena_minimo_8_caracteres")
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="contrasena_demasiado_larga")
    return password


def verification_hash(company_id: uuid.UUID, phone: str, purpose: str, code: str) -> str:
    payload = f"{company_id}:{phone}:{purpose}:{code}".encode("utf-8")
    return hmac.new(get_jwt_secret().encode("utf-8"), payload, hashlib.sha256).hexdigest()


async def ensure_marketplace_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            username varchar(40) NOT NULL,
            username_key varchar(40) NOT NULL,
            phone varchar(20) NOT NULL,
            password_hash text NOT NULL,
            phone_verified_at timestamptz NOT NULL DEFAULT now(),
            status varchar(24) NOT NULL DEFAULT 'active',
            failed_login_attempts integer NOT NULL DEFAULT 0,
            locked_until timestamptz NULL,
            last_login_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_marketplace_users_company_username UNIQUE (company_id, username_key),
            CONSTRAINT uq_marketplace_users_company_phone UNIQUE (company_id, phone)
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_marketplace_users_company_status
        ON marketplace_users(company_id, status, created_at DESC)
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_verification_codes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            phone varchar(20) NOT NULL,
            purpose varchar(24) NOT NULL,
            code_hash varchar(64) NOT NULL,
            attempts integer NOT NULL DEFAULT 0,
            request_ip varchar(80) NULL,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_marketplace_codes_lookup
        ON marketplace_verification_codes(company_id, phone, purpose, created_at DESC)
    """))
    await db.commit()


async def require_marketplace_company(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT c.id::text AS id, c.name, c.slug, c.status,
                   COALESCE(c.settings_json, '{}'::jsonb) AS settings_json,
                   COALESCE(cm.settings, '{}'::jsonb) AS module_settings
            FROM companies c
            JOIN company_modules cm ON cm.company_id = c.id AND cm.enabled IS TRUE
            JOIN modules m ON m.id = cm.module_id AND m.code = :module_code AND m.is_active IS TRUE
            WHERE c.id = CAST(:company_id AS uuid)
              AND c.status = 'active'
            LIMIT 1
        """),
        {"company_id": str(company_id), "module_code": MODULE_CODE},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="marketplace_no_disponible")
    return dict(row)


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "username": row.get("username") or "Usuario",
        "phone_masked": mask_phone(row.get("phone") or ""),
        "phone_verified": row.get("phone_verified_at") is not None,
        "status": row.get("status") or "active",
        "created_at": row.get("created_at").isoformat() if isinstance(row.get("created_at"), datetime) else row.get("created_at"),
    }


def mask_phone(phone: str) -> str:
    value = str(phone or "")
    if len(value) <= 6:
        return "***"
    return f"{value[:3]} *** {value[-4:]}"


def token_response(row: dict[str, Any]) -> dict[str, Any]:
    token = create_access_token(
        {
            "sub": str(row["id"]),
            "company_id": str(row["company_id"]),
            "username": row.get("username") or "",
            "scope": "marketplace",
        },
        expires_minutes=TOKEN_MINUTES,
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_MINUTES * 60, "user": public_user(row)}


def bearer_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="sesion_requerida")
    token = raw.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="sesion_requerida")
    return token


async def current_marketplace_user(
    db: AsyncSession,
    company_id: uuid.UUID,
    authorization: str | None,
) -> dict[str, Any]:
    try:
        payload = decode_access_token(bearer_token(authorization))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="sesion_invalida")
    if payload.get("scope") != "marketplace" or str(payload.get("company_id") or "") != str(company_id):
        raise HTTPException(status_code=401, detail="sesion_invalida")
    try:
        user_id = uuid.UUID(str(payload.get("sub") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="sesion_invalida")
    result = await db.execute(
        text("""
            SELECT id, company_id, username, username_key, phone, password_hash,
                   phone_verified_at, status, failed_login_attempts, locked_until,
                   last_login_at, created_at, updated_at
            FROM marketplace_users
            WHERE id = CAST(:user_id AS uuid)
              AND company_id = CAST(:company_id AS uuid)
            LIMIT 1
        """),
        {"user_id": str(user_id), "company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row or row.get("status") != "active":
        raise HTTPException(status_code=401, detail="sesion_invalida")
    return dict(row)


def twilio_sender() -> str:
    explicit = os.getenv("TWILIO_SMS_FROM") or os.getenv("TWILIO_PHONE_NUMBER") or os.getenv("TWILIO_FROM_NUMBER")
    if explicit:
        return normalize_phone(explicit)
    for value in os.getenv("TWILIO_OUTGOING_NUMBERS", "").split(","):
        if value.strip():
            return normalize_phone(value)
    return ""


async def send_verification_message(phone: str, code: str, company_name: str) -> None:
    account_sid = str(os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
    auth_token = str(os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
    sender = twilio_sender()
    if not account_sid or not auth_token or not sender:
        raise HTTPException(status_code=503, detail="mensajeria_no_configurada")
    body = f"{company_name}: tu codigo de verificacion es {code}. Vence en {CODE_TTL_MINUTES} minutos. No lo compartas."

    def _send() -> None:
        TwilioClient(account_sid, auth_token).messages.create(body=body, from_=sender, to=phone)

    try:
        await asyncio.to_thread(_send)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="no_se_pudo_enviar_el_mensaje") from exc


async def consume_verification_code(
    db: AsyncSession,
    company_id: uuid.UUID,
    phone: str,
    purpose: str,
    code: str,
) -> None:
    result = await db.execute(
        text("""
            SELECT id, code_hash, attempts
            FROM marketplace_verification_codes
            WHERE company_id = CAST(:company_id AS uuid)
              AND phone = :phone
              AND purpose = :purpose
              AND consumed_at IS NULL
              AND expires_at > now()
            ORDER BY created_at DESC
            LIMIT 1
            FOR UPDATE
        """),
        {"company_id": str(company_id), "phone": phone, "purpose": purpose},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=400, detail="codigo_vencido_o_inexistente")
    expected = verification_hash(company_id, phone, purpose, str(code or ""))
    if not hmac.compare_digest(str(row["code_hash"]), expected):
        attempts = int(row.get("attempts") or 0) + 1
        await db.execute(
            text("""
                UPDATE marketplace_verification_codes
                SET attempts = :attempts,
                    consumed_at = CASE WHEN :attempts >= 5 THEN now() ELSE consumed_at END
                WHERE id = CAST(:id AS uuid)
            """),
            {"attempts": attempts, "id": str(row["id"])},
        )
        await db.commit()
        raise HTTPException(status_code=400, detail="codigo_incorrecto")
    await db.execute(
        text("UPDATE marketplace_verification_codes SET consumed_at = now() WHERE id = CAST(:id AS uuid)"),
        {"id": str(row["id"])},
    )


@router.get("/companies/{company_id}/public")
async def marketplace_public_config(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    company = await require_marketplace_company(db, company_id)
    count = await db.scalar(
        text("SELECT count(*) FROM marketplace_users WHERE company_id = CAST(:company_id AS uuid) AND status = 'active'"),
        {"company_id": str(company_id)},
    )
    module_settings = company.get("module_settings") if isinstance(company.get("module_settings"), dict) else {}
    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": company.get("slug") or ""},
        "marketplace": {
            "title": module_settings.get("public_title") or "Cambios y compras",
            "registered_users": int(count or 0),
            "registration": "phone_code_password",
            "browsing_requires_login": False,
            "publishing_requires_login": True,
            "offers_require_login": True,
        },
    }


@router.post("/companies/{company_id}/auth/verification/request")
async def request_verification(
    company_id: uuid.UUID,
    payload: VerificationRequestIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    company = await require_marketplace_company(db, company_id)
    phone = normalize_phone(payload.phone)
    existing = await db.scalar(
        text("SELECT count(*) FROM marketplace_users WHERE company_id = CAST(:company_id AS uuid) AND phone = :phone"),
        {"company_id": str(company_id), "phone": phone},
    )
    if payload.purpose == "register" and existing:
        raise HTTPException(status_code=409, detail="telefono_ya_registrado")
    if payload.purpose == "reset" and not existing:
        raise HTTPException(status_code=404, detail="telefono_no_registrado")
    recent = await db.scalar(
        text("""
            SELECT count(*) FROM marketplace_verification_codes
            WHERE company_id = CAST(:company_id AS uuid)
              AND phone = :phone AND created_at > now() - interval '15 minutes'
        """),
        {"company_id": str(company_id), "phone": phone},
    )
    if int(recent or 0) >= 5:
        raise HTTPException(status_code=429, detail="demasiados_codigos_solicitados")
    last_sent = await db.scalar(
        text("""
            SELECT created_at FROM marketplace_verification_codes
            WHERE company_id = CAST(:company_id AS uuid) AND phone = :phone
            ORDER BY created_at DESC LIMIT 1
        """),
        {"company_id": str(company_id), "phone": phone},
    )
    if isinstance(last_sent, datetime) and (utc_now() - (last_sent if last_sent.tzinfo else last_sent.replace(tzinfo=timezone.utc))).total_seconds() < 45:
        raise HTTPException(status_code=429, detail="espera_antes_de_solicitar_otro_codigo")
    code = f"{secrets.randbelow(1_000_000):06d}"
    await db.execute(
        text("""
            INSERT INTO marketplace_verification_codes
                (company_id, phone, purpose, code_hash, request_ip, expires_at)
            VALUES
                (CAST(:company_id AS uuid), :phone, :purpose, :code_hash, :request_ip, :expires_at)
        """),
        {
            "company_id": str(company_id),
            "phone": phone,
            "purpose": payload.purpose,
            "code_hash": verification_hash(company_id, phone, payload.purpose, code),
            "request_ip": (request.headers.get("x-forwarded-for") or (request.client.host if request.client else ""))[:80],
            "expires_at": utc_now() + timedelta(minutes=CODE_TTL_MINUTES),
        },
    )
    try:
        await send_verification_message(phone, code, company["name"])
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    response: dict[str, Any] = {"ok": True, "delivery": "sms", "expires_in": CODE_TTL_MINUTES * 60, "phone_masked": mask_phone(phone)}
    if not os.getenv("RAILWAY_ENVIRONMENT_NAME") and os.getenv("APP_ENV", "local").lower() != "production":
        response["verification_code"] = code
    return response


@router.post("/companies/{company_id}/auth/register", status_code=status.HTTP_201_CREATED)
async def register_marketplace_user(
    company_id: uuid.UUID,
    payload: RegisterIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    await require_marketplace_company(db, company_id)
    phone = normalize_phone(payload.phone)
    username, username_key = normalize_username(payload.username)
    password = validate_password(payload.password)
    duplicate = await db.execute(
        text("""
            SELECT phone = :phone AS phone_exists, username_key = :username_key AS username_exists
            FROM marketplace_users
            WHERE company_id = CAST(:company_id AS uuid)
              AND (phone = :phone OR username_key = :username_key)
            LIMIT 1
        """),
        {"company_id": str(company_id), "phone": phone, "username_key": username_key},
    )
    row = duplicate.mappings().first()
    if row:
        raise HTTPException(status_code=409, detail="telefono_ya_registrado" if row.get("phone_exists") else "usuario_no_disponible")
    await consume_verification_code(db, company_id, phone, "register", payload.verification_code)
    result = await db.execute(
        text("""
            INSERT INTO marketplace_users
                (company_id, username, username_key, phone, password_hash, phone_verified_at)
            VALUES
                (CAST(:company_id AS uuid), :username, :username_key, :phone, :password_hash, now())
            RETURNING id, company_id, username, username_key, phone, password_hash,
                      phone_verified_at, status, created_at
        """),
        {
            "company_id": str(company_id),
            "username": username,
            "username_key": username_key,
            "phone": phone,
            "password_hash": hash_password(password),
        },
    )
    user = dict(result.mappings().first())
    await db.commit()
    return token_response(user)


@router.post("/companies/{company_id}/auth/login")
async def login_marketplace_user(
    company_id: uuid.UUID,
    payload: LoginIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    await require_marketplace_company(db, company_id)
    identifier = str(payload.identifier or "").strip()
    try:
        phone = normalize_phone(identifier)
    except HTTPException:
        phone = ""
    _, username_key = normalize_username(identifier)
    result = await db.execute(
        text("""
            SELECT id, company_id, username, username_key, phone, password_hash,
                   phone_verified_at, status, failed_login_attempts, locked_until,
                   last_login_at, created_at, updated_at
            FROM marketplace_users
            WHERE company_id = CAST(:company_id AS uuid)
              AND (phone = :phone OR username_key = :username_key)
            LIMIT 1
        """),
        {"company_id": str(company_id), "phone": phone, "username_key": username_key},
    )
    row = result.mappings().first()
    if not row or row.get("status") != "active":
        raise HTTPException(status_code=401, detail="credenciales_invalidas")
    user = dict(row)
    locked_until = user.get("locked_until")
    if isinstance(locked_until, datetime):
        aware_locked = locked_until if locked_until.tzinfo else locked_until.replace(tzinfo=timezone.utc)
        if aware_locked > utc_now():
            raise HTTPException(status_code=423, detail="cuenta_temporalmente_bloqueada")
    if not verify_password(payload.password, user["password_hash"]):
        attempts = int(user.get("failed_login_attempts") or 0) + 1
        await db.execute(
            text("""
                UPDATE marketplace_users
                SET failed_login_attempts = :attempts,
                    locked_until = CASE WHEN :attempts >= 5 THEN now() + interval '15 minutes' ELSE NULL END,
                    updated_at = now()
                WHERE id = CAST(:id AS uuid)
            """),
            {"attempts": attempts, "id": str(user["id"])},
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="credenciales_invalidas")
    await db.execute(
        text("""
            UPDATE marketplace_users
            SET failed_login_attempts = 0, locked_until = NULL, last_login_at = now(), updated_at = now()
            WHERE id = CAST(:id AS uuid)
        """),
        {"id": str(user["id"])},
    )
    await db.commit()
    return token_response(user)


@router.get("/companies/{company_id}/auth/me")
async def marketplace_me(
    company_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    await require_marketplace_company(db, company_id)
    return {"ok": True, "user": public_user(await current_marketplace_user(db, company_id, authorization))}


@router.patch("/companies/{company_id}/auth/profile")
async def update_marketplace_profile(
    company_id: uuid.UUID,
    payload: ProfileUpdateIn,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    username, username_key = normalize_username(payload.username)
    existing = await db.scalar(
        text("""
            SELECT count(*) FROM marketplace_users
            WHERE company_id = CAST(:company_id AS uuid)
              AND username_key = :username_key AND id <> CAST(:user_id AS uuid)
        """),
        {"company_id": str(company_id), "username_key": username_key, "user_id": str(user["id"])},
    )
    if existing:
        raise HTTPException(status_code=409, detail="usuario_no_disponible")
    result = await db.execute(
        text("""
            UPDATE marketplace_users SET username = :username, username_key = :username_key, updated_at = now()
            WHERE id = CAST(:user_id AS uuid)
            RETURNING id, company_id, username, phone, phone_verified_at, status, created_at
        """),
        {"username": username, "username_key": username_key, "user_id": str(user["id"])},
    )
    fresh = dict(result.mappings().first())
    await db.commit()
    return {"ok": True, "user": public_user(fresh)}


@router.patch("/companies/{company_id}/auth/password")
async def update_marketplace_password(
    company_id: uuid.UUID,
    payload: PasswordUpdateIn,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="contrasena_actual_incorrecta")
    password = validate_password(payload.new_password)
    await db.execute(
        text("UPDATE marketplace_users SET password_hash = :password_hash, updated_at = now() WHERE id = CAST(:id AS uuid)"),
        {"password_hash": hash_password(password), "id": str(user["id"])},
    )
    await db.commit()
    return {"ok": True}


@router.post("/companies/{company_id}/auth/password-reset")
async def reset_marketplace_password(
    company_id: uuid.UUID,
    payload: ResetPasswordIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    await require_marketplace_company(db, company_id)
    phone = normalize_phone(payload.phone)
    password = validate_password(payload.new_password)
    user_id = await db.scalar(
        text("SELECT id FROM marketplace_users WHERE company_id = CAST(:company_id AS uuid) AND phone = :phone LIMIT 1"),
        {"company_id": str(company_id), "phone": phone},
    )
    if not user_id:
        raise HTTPException(status_code=404, detail="telefono_no_registrado")
    await consume_verification_code(db, company_id, phone, "reset", payload.verification_code)
    await db.execute(
        text("""
            UPDATE marketplace_users
            SET password_hash = :password_hash, failed_login_attempts = 0,
                locked_until = NULL, updated_at = now()
            WHERE id = CAST(:id AS uuid)
        """),
        {"password_hash": hash_password(password), "id": str(user_id)},
    )
    await db.commit()
    return {"ok": True}
