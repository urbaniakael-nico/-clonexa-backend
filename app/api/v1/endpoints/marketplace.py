from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.rest import Client as TwilioClient

from app.api.deps import ADMIN_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    get_jwt_secret,
    hash_password,
    verify_password,
)
from app.web.admin_v2_routes import _active_company_preview as active_admin_company_preview
from app.web.admin_v2_routes import _active_session as active_admin_v2_session


router = APIRouter()
MODULE_CODE = "marketplace_access"
TOKEN_MINUTES = 60 * 24 * 30
CODE_TTL_MINUTES = 5
MAX_PUBLICATION_IMAGES = 5
MAX_OFFER_IMAGES = 3
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024
MAX_VIDEO_SECONDS = 30
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
MARKETPLACE_CATEGORIES = {
    "tecnologia": "Tecnología",
    "juegos_consola": "Juegos de consola",
    "accesorios": "Accesorios",
    "gorras": "Gorras",
    "tenis": "Tenis",
    "ropa": "Ropa",
    "herramientas": "Herramientas",
    "relojes": "Relojes",
    "artesanias": "Artesanías",
    "otros": "Otros",
}
MARKETPLACE_CATEGORY_KEYWORDS = {
    "juegos_consola": ("videojuego", "juego ps", "juego xbox", "juego nintendo", "fifa", "ea fc", "eafc", "gta", "call of duty", "mario", "pokemon", "zelda", "fortnite", "minecraft"),
    "relojes": ("reloj", "smartwatch", "watch", "cronografo"),
    "gorras": ("gorra", "cachucha", "sombrero", "visera"),
    "tenis": ("tenis", "sneaker", "zapatilla", "zapato", "calzado", "botas"),
    "herramientas": ("herramienta", "taladro", "martillo", "destornillador", "llave inglesa", "pulidora", "sierra", "multimetro"),
    "artesanias": ("artesania", "hecho a mano", "tejido", "macrame", "ceramica", "manualidad"),
    "accesorios": ("accesorio", "bolso", "cartera", "gafas", "collar", "pulsera", "anillo", "cinturon", "maletin", "mochila"),
    "ropa": ("ropa", "camisa", "camiseta", "pantalon", "jean", "vestido", "chaqueta", "hoodie", "buzo", "falda", "short"),
    "tecnologia": ("tecnologia", "celular", "telefono", "iphone", "android", "tablet", "ipad", "portatil", "laptop", "computador", "pc", "monitor", "televisor", "audifono", "parlante", "camara", "playstation", "play 4", "play 5", "ps4", "ps5", "xbox", "nintendo", "switch", "consola"),
}


class VerificationRequestIn(BaseModel):
    phone: str = Field(..., min_length=7, max_length=30)
    purpose: Literal["register", "reset"] = "register"


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    phone: str = Field(..., min_length=7, max_length=30)
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
    bio: str = Field(default="", max_length=280)


class PasswordUpdateIn(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=72)
    new_password: str = Field(..., min_length=8, max_length=72)


class ChatMessageIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=1200)


class PublicationUpdateIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=140)
    description: str = Field(default="", max_length=2400)
    specifications: str = Field(default="", max_length=2400)
    price: float = Field(default=0, ge=0)
    offer_mode: str = Field(default="both", max_length=24)
    category: str = Field(default="auto", max_length=32)


class ProfileReviewIn(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=2, max_length=600)


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
    # Public pages load config, session and publications concurrently. Serialize the
    # idempotent DDL so simultaneous first requests cannot deadlock on ALTER TABLE.
    await db.execute(text("SELECT pg_advisory_xact_lock(7812394056123)"))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            username varchar(40) NOT NULL,
            username_key varchar(40) NOT NULL,
            bio varchar(280) NOT NULL DEFAULT '',
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
    await db.execute(text("ALTER TABLE marketplace_users ALTER COLUMN phone_verified_at DROP NOT NULL"))
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
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_publications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES marketplace_users(id) ON DELETE CASCADE,
            title varchar(140) NOT NULL,
            description text NOT NULL DEFAULT '',
            specifications text NOT NULL DEFAULT '',
            price numeric(16,2) NOT NULL DEFAULT 0,
            offer_mode varchar(24) NOT NULL DEFAULT 'both',
            category varchar(32) NULL,
            status varchar(24) NOT NULL DEFAULT 'published',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("ALTER TABLE marketplace_users ADD COLUMN IF NOT EXISTS bio varchar(280) NOT NULL DEFAULT ''"))
    await db.execute(text("ALTER TABLE marketplace_publications ADD COLUMN IF NOT EXISTS category varchar(32) NULL"))
    uncategorized = await db.execute(text("""
        SELECT id::text AS id, title, description, specifications
        FROM marketplace_publications
        WHERE category IS NULL OR btrim(category) = ''
    """))
    for raw in uncategorized.mappings().all():
        row = dict(raw)
        inferred = infer_marketplace_category(row.get("title"), row.get("description"), row.get("specifications"))
        await db.execute(
            text("UPDATE marketplace_publications SET category = :category WHERE id = CAST(:id AS uuid)"),
            {"category": inferred, "id": row["id"]},
        )
    await db.execute(text("ALTER TABLE marketplace_publications ALTER COLUMN category SET DEFAULT 'otros'"))
    await db.execute(text("ALTER TABLE marketplace_publications ALTER COLUMN category SET NOT NULL"))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_marketplace_publications_company_status
        ON marketplace_publications(company_id, status, created_at DESC)
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_marketplace_publications_company_category
        ON marketplace_publications(company_id, category, created_at DESC)
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_publication_media (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            publication_id uuid NOT NULL REFERENCES marketplace_publications(id) ON DELETE CASCADE,
            kind varchar(16) NOT NULL,
            position integer NOT NULL DEFAULT 0,
            content_type varchar(80) NOT NULL,
            file_bytes bytea NOT NULL,
            file_size integer NOT NULL,
            duration_seconds numeric(8,2) NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_marketplace_media_publication
        ON marketplace_publication_media(publication_id, kind, position)
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_conversations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            publication_id uuid NOT NULL REFERENCES marketplace_publications(id) ON DELETE CASCADE,
            buyer_user_id uuid NOT NULL REFERENCES marketplace_users(id) ON DELETE CASCADE,
            seller_user_id uuid NOT NULL REFERENCES marketplace_users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_marketplace_conversation UNIQUE (publication_id, buyer_user_id)
        )
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL REFERENCES marketplace_conversations(id) ON DELETE CASCADE,
            sender_user_id uuid NOT NULL REFERENCES marketplace_users(id) ON DELETE CASCADE,
            body text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_marketplace_messages_conversation
        ON marketplace_messages(conversation_id, created_at)
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_offers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            publication_id uuid NOT NULL REFERENCES marketplace_publications(id) ON DELETE CASCADE,
            buyer_user_id uuid NOT NULL REFERENCES marketplace_users(id) ON DELETE CASCADE,
            seller_user_id uuid NOT NULL REFERENCES marketplace_users(id) ON DELETE CASCADE,
            conversation_id uuid NOT NULL REFERENCES marketplace_conversations(id) ON DELETE CASCADE,
            offer_type varchar(16) NOT NULL CHECK (offer_type IN ('money', 'change')),
            amount numeric(16,2) NULL,
            description text NOT NULL DEFAULT '',
            status varchar(24) NOT NULL DEFAULT 'pending',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_marketplace_offers_participants
        ON marketplace_offers(company_id, seller_user_id, buyer_user_id, created_at DESC)
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_offer_media (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            offer_id uuid NOT NULL REFERENCES marketplace_offers(id) ON DELETE CASCADE,
            kind varchar(16) NOT NULL,
            position integer NOT NULL DEFAULT 0,
            content_type varchar(80) NOT NULL,
            file_bytes bytea NOT NULL,
            file_size integer NOT NULL,
            duration_seconds numeric(8,2) NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_marketplace_offer_media_offer
        ON marketplace_offer_media(offer_id, kind, position)
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS marketplace_profile_reviews (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            profile_user_id uuid NOT NULL REFERENCES marketplace_users(id) ON DELETE CASCADE,
            reviewer_user_id uuid NOT NULL REFERENCES marketplace_users(id) ON DELETE CASCADE,
            rating integer NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment varchar(600) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_marketplace_profile_review UNIQUE (profile_user_id, reviewer_user_id),
            CONSTRAINT ck_marketplace_profile_review_distinct CHECK (profile_user_id <> reviewer_user_id)
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_marketplace_profile_reviews_profile
        ON marketplace_profile_reviews(company_id, profile_user_id, updated_at DESC)
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
        "bio": row.get("bio") or "",
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
            SELECT id, company_id, username, username_key, bio, phone, password_hash,
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
            "registration": "phone_password",
            "sms_enabled": False,
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
    raise HTTPException(status_code=410, detail="verificacion_sms_temporalmente_deshabilitada")
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
    result = await db.execute(
        text("""
            INSERT INTO marketplace_users
                (company_id, username, username_key, phone, password_hash, phone_verified_at)
            VALUES
                (CAST(:company_id AS uuid), :username, :username_key, :phone, :password_hash, NULL)
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
            SELECT id, company_id, username, username_key, bio, phone, password_hash,
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
            UPDATE marketplace_users SET username = :username, username_key = :username_key,
                bio = :bio, updated_at = now()
            WHERE id = CAST(:user_id AS uuid)
            RETURNING id, company_id, username, bio, phone, phone_verified_at, status, created_at
        """),
        {"username": username, "username_key": username_key, "bio": _clean(payload.bio, 280), "user_id": str(user["id"])},
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


def _clean(value: Any, limit: int = 255) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _money(value: Any) -> float:
    try:
        return max(0.0, round(float(value or 0), 2))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="valor_invalido")


def _offer_mode(value: Any) -> str:
    clean = _clean(value, 24).lower()
    if clean not in {"money", "change", "both"}:
        raise HTTPException(status_code=422, detail="modalidad_invalida")
    return clean


def _category_text(*values: Any) -> str:
    raw = " ".join(str(value or "") for value in values).lower()
    folded = unicodedata.normalize("NFD", raw)
    return re.sub(r"\s+", " ", "".join(char for char in folded if unicodedata.category(char) != "Mn"))


def _request_origin(request: Request) -> str:
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip()
    forwarded_host = str(request.headers.get("x-forwarded-host") or "").split(",", 1)[0].strip()
    scheme = forwarded_proto or request.url.scheme or "https"
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}".rstrip("/")


def infer_marketplace_category(*values: Any) -> str:
    content = _category_text(*values)
    tokens = set(content.split())
    best_category = "otros"
    best_score = 0
    for category, keywords in MARKETPLACE_CATEGORY_KEYWORDS.items():
        matches = [keyword for keyword in keywords if (keyword in content if len(keyword) > 3 else keyword in tokens)]
        score = sum(2 if " " in keyword else 1 for keyword in matches)
        if score > best_score:
            best_category = category
            best_score = score
    return best_category


def normalize_marketplace_category(value: Any, *content: Any) -> str:
    clean = _clean(value, 32).lower()
    if clean in {"", "auto", "automatica", "automatico"}:
        return infer_marketplace_category(*content)
    if clean not in MARKETPLACE_CATEGORIES:
        raise HTTPException(status_code=422, detail="categoria_invalida")
    return clean


def _file_type(upload: UploadFile, allowed: set[str], kind: str) -> str:
    content_type = str(upload.content_type or "").strip().lower()
    if content_type in allowed:
        return content_type
    filename = str(upload.filename or "").lower()
    suffixes = {
        "image": {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"},
        "video": {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"},
    }
    for suffix, fallback in suffixes[kind].items():
        if filename.endswith(suffix):
            return fallback
    raise HTTPException(status_code=422, detail="imagen_invalida" if kind == "image" else "video_invalido")


def _mp4_duration_seconds(content: bytes) -> float | None:
    marker = content.find(b"mvhd")
    if marker < 0 or marker + 32 > len(content):
        return None
    try:
        version = content[marker + 4]
        if version == 0:
            timescale = int.from_bytes(content[marker + 16 : marker + 20], "big")
            duration = int.from_bytes(content[marker + 20 : marker + 24], "big")
        elif version == 1:
            timescale = int.from_bytes(content[marker + 24 : marker + 28], "big")
            duration = int.from_bytes(content[marker + 28 : marker + 36], "big")
        else:
            return None
        return round(duration / timescale, 2) if timescale else None
    except Exception:
        return None


async def _read_media(upload: UploadFile, kind: str, declared_duration: float = 0) -> dict[str, Any]:
    allowed = ALLOWED_IMAGE_TYPES if kind == "image" else ALLOWED_VIDEO_TYPES
    content_type = _file_type(upload, allowed, kind)
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=422, detail="archivo_vacio")
    limit = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
    if len(content) > limit:
        raise HTTPException(status_code=422, detail="imagen_supera_5mb" if kind == "image" else "video_supera_25mb")
    duration: float | None = None
    if kind == "video":
        duration = _mp4_duration_seconds(content) if content_type in {"video/mp4", "video/quicktime"} else None
        duration = duration if duration is not None else float(declared_duration or 0)
        if duration <= 0 or duration > MAX_VIDEO_SECONDS + 0.2:
            raise HTTPException(status_code=422, detail="video_maximo_30_segundos")
    return {"kind": kind, "content_type": content_type, "content": content, "size": len(content), "duration": duration}


async def _publication_media(db: AsyncSession, company_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    result = await db.execute(
        text("""
            SELECT m.id::text AS id, m.publication_id::text AS publication_id, m.kind,
                   m.position, m.content_type, m.file_size, m.duration_seconds
            FROM marketplace_publication_media m
            JOIN marketplace_publications p ON p.id = m.publication_id
            WHERE p.company_id = CAST(:company_id AS uuid)
            ORDER BY m.publication_id, m.kind, m.position
        """),
        {"company_id": str(company_id)},
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in result.mappings().all():
        row = dict(raw)
        publication_id = str(row.pop("publication_id"))
        row["url"] = f"/api/v1/marketplace/publications/{publication_id}/media/{row['id']}"
        if row.get("duration_seconds") is not None:
            row["duration_seconds"] = float(row["duration_seconds"])
        grouped.setdefault(publication_id, []).append(row)
    return grouped


def _publication_out(row: dict[str, Any], media: list[dict[str, Any]], request: Request | None = None, include_phone: bool = False) -> dict[str, Any]:
    publication_id = str(row["id"])
    company_id = str(row["company_id"])
    result = {
        "id": publication_id,
        "company_id": company_id,
        "title": row.get("title") or "Articulo",
        "description": row.get("description") or "",
        "specifications": row.get("specifications") or "",
        "price": float(row.get("price") or 0),
        "offer_mode": row.get("offer_mode") or "both",
        "category": row.get("category") or "otros",
        "category_label": MARKETPLACE_CATEGORIES.get(row.get("category") or "otros", "Otros"),
        "status": row.get("status") or "published",
        "seller": {"id": str(row.get("user_id") or ""), "username": row.get("username") or "Usuario"},
        "media": media,
        "image_urls": [item["url"] for item in media if item.get("kind") == "image"],
        "video_url": next((item["url"] for item in media if item.get("kind") == "video"), ""),
        "created_at": row.get("created_at").isoformat() if isinstance(row.get("created_at"), datetime) else row.get("created_at"),
    }
    result["seller"]["profile_url"] = f"/mercado?company_id={company_id}&profile={result['seller']['id']}"
    if include_phone:
        result["seller"]["phone"] = row.get("phone") or ""
    if request is not None:
        origin = _request_origin(request)
        result["public_url"] = f"{origin}/mercado?company_id={company_id}&publication={publication_id}"
    return result


async def _publication_rows(
    db: AsyncSession,
    company_id: uuid.UUID,
    include_all: bool = False,
    user_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    status_clause = "" if include_all else "AND p.status = 'published'"
    user_clause = "AND p.user_id = CAST(:user_id AS uuid)" if user_id else ""
    result = await db.execute(
        text(f"""
            SELECT p.*, u.username, u.phone
            FROM marketplace_publications p
            JOIN marketplace_users u ON u.id = p.user_id
            WHERE p.company_id = CAST(:company_id AS uuid) {status_clause} {user_clause}
            ORDER BY p.created_at DESC
            LIMIT 500
        """),
        {"company_id": str(company_id), "user_id": str(user_id) if user_id else ""},
    )
    return [dict(row) for row in result.mappings().all()]


async def _require_marketplace_owner_panel(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None,
    db: AsyncSession,
) -> None:
    if await active_admin_v2_session(request, db) or active_admin_company_preview(request, company_id):
        await require_enabled_module(db, company_id, MODULE_CODE)
        return
    await require_company_user_for_tenant(
        db,
        authorization,
        company_id,
        allowed_roles=ADMIN_ROLES | {"manager", "gerencia", "gerente", "supervisor"},
        module_codes=MODULE_CODE,
    )


@router.get("/companies/{company_id}/publications")
async def list_public_marketplace_publications(
    company_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    await require_marketplace_company(db, company_id)
    media = await _publication_media(db, company_id)
    rows = await _publication_rows(db, company_id)
    return {"ok": True, "publications": [_publication_out(row, media.get(str(row["id"]), []), request=request) for row in rows]}


@router.get("/companies/{company_id}/profiles/{profile_user_id}")
async def marketplace_public_profile(
    company_id: uuid.UUID,
    profile_user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    await require_marketplace_company(db, company_id)
    profile_result = await db.execute(
        text("""
            SELECT id::text AS id, company_id::text AS company_id, username, bio, created_at
            FROM marketplace_users
            WHERE id = CAST(:user_id AS uuid) AND company_id = CAST(:company_id AS uuid) AND status = 'active'
            LIMIT 1
        """),
        {"user_id": str(profile_user_id), "company_id": str(company_id)},
    )
    profile = profile_result.mappings().first()
    if not profile:
        raise HTTPException(status_code=404, detail="perfil_no_encontrado")
    rating_result = await db.execute(
        text("""
            SELECT COALESCE(round(avg(rating)::numeric, 1), 0) AS rating, count(*) AS review_count
            FROM marketplace_profile_reviews
            WHERE company_id = CAST(:company_id AS uuid) AND profile_user_id = CAST(:user_id AS uuid)
        """),
        {"company_id": str(company_id), "user_id": str(profile_user_id)},
    )
    rating = dict(rating_result.mappings().first())
    reviews_result = await db.execute(
        text("""
            SELECT r.id::text AS id, r.rating, r.comment, r.updated_at,
                   u.id::text AS reviewer_user_id, u.username AS reviewer_username
            FROM marketplace_profile_reviews r
            JOIN marketplace_users u ON u.id = r.reviewer_user_id
            WHERE r.company_id = CAST(:company_id AS uuid) AND r.profile_user_id = CAST(:user_id AS uuid)
            ORDER BY r.updated_at DESC
            LIMIT 100
        """),
        {"company_id": str(company_id), "user_id": str(profile_user_id)},
    )
    media = await _publication_media(db, company_id)
    rows = await _publication_rows(db, company_id, user_id=profile_user_id)
    origin = _request_origin(request)
    return {
        "ok": True,
        "profile": {
            "id": str(profile["id"]),
            "username": profile.get("username") or "Usuario",
            "bio": profile.get("bio") or "",
            "created_at": profile.get("created_at").isoformat() if isinstance(profile.get("created_at"), datetime) else profile.get("created_at"),
            "rating": float(rating.get("rating") or 0),
            "review_count": int(rating.get("review_count") or 0),
            "public_url": f"{origin}/mercado?company_id={company_id}&profile={profile_user_id}",
        },
        "reviews": [
            {
                **dict(item),
                "updated_at": item.get("updated_at").isoformat() if isinstance(item.get("updated_at"), datetime) else item.get("updated_at"),
            }
            for item in reviews_result.mappings().all()
        ],
        "publications": [_publication_out(row, media.get(str(row["id"]), []), request=request) for row in rows],
    }


@router.post("/companies/{company_id}/profiles/{profile_user_id}/reviews", status_code=status.HTTP_201_CREATED)
async def review_marketplace_profile(
    company_id: uuid.UUID,
    profile_user_id: uuid.UUID,
    payload: ProfileReviewIn,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    reviewer = await current_marketplace_user(db, company_id, authorization)
    if str(reviewer["id"]) == str(profile_user_id):
        raise HTTPException(status_code=422, detail="no_puedes_calificarte")
    target_exists = await db.scalar(
        text("SELECT count(*) FROM marketplace_users WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid) AND status = 'active'"),
        {"id": str(profile_user_id), "company_id": str(company_id)},
    )
    if not target_exists:
        raise HTTPException(status_code=404, detail="perfil_no_encontrado")
    comment = _clean(payload.comment, 600)
    result = await db.execute(
        text("""
            INSERT INTO marketplace_profile_reviews
                (company_id, profile_user_id, reviewer_user_id, rating, comment)
            VALUES
                (CAST(:company_id AS uuid), CAST(:profile_user_id AS uuid), CAST(:reviewer_user_id AS uuid), :rating, :comment)
            ON CONFLICT (profile_user_id, reviewer_user_id) DO UPDATE
            SET rating = EXCLUDED.rating, comment = EXCLUDED.comment, updated_at = now()
            RETURNING id::text AS id, rating, comment, updated_at
        """),
        {"company_id": str(company_id), "profile_user_id": str(profile_user_id), "reviewer_user_id": str(reviewer["id"]), "rating": payload.rating, "comment": comment},
    )
    review = dict(result.mappings().first())
    await db.commit()
    return {"ok": True, "review": review}


@router.get("/companies/{company_id}/auth/publications")
async def marketplace_my_publications(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    media = await _publication_media(db, company_id)
    rows = await _publication_rows(db, company_id, include_all=True, user_id=uuid.UUID(str(user["id"])))
    return {"ok": True, "publications": [_publication_out(row, media.get(str(row["id"]), []), request=request) for row in rows]}


@router.patch("/companies/{company_id}/publications/{publication_id}")
async def update_marketplace_publication(
    company_id: uuid.UUID,
    publication_id: uuid.UUID,
    payload: PublicationUpdateIn,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    clean_title = _clean(payload.title, 140)
    clean_description = _clean(payload.description, 2400)
    clean_specifications = _clean(payload.specifications, 2400)
    category = normalize_marketplace_category(payload.category, clean_title, clean_description, clean_specifications)
    result = await db.execute(
        text("""
            UPDATE marketplace_publications
            SET title = :title, description = :description, specifications = :specifications,
                price = :price, offer_mode = :offer_mode, category = :category, updated_at = now()
            WHERE id = CAST(:publication_id AS uuid) AND company_id = CAST(:company_id AS uuid)
              AND user_id = CAST(:user_id AS uuid)
            RETURNING *
        """),
        {"title": clean_title, "description": clean_description, "specifications": clean_specifications,
         "price": _money(payload.price), "offer_mode": _offer_mode(payload.offer_mode), "category": category,
         "publication_id": str(publication_id), "company_id": str(company_id), "user_id": str(user["id"])},
    )
    publication = result.mappings().first()
    if not publication:
        raise HTTPException(status_code=404, detail="publicacion_no_encontrada")
    await db.commit()
    media = await _publication_media(db, company_id)
    row = dict(publication)
    row.update({"username": user["username"], "phone": user["phone"]})
    return {"ok": True, "publication": _publication_out(row, media.get(str(publication_id), []), request=request)}


@router.post("/companies/{company_id}/publications", status_code=status.HTTP_201_CREATED)
async def create_marketplace_publication(
    company_id: uuid.UUID,
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    specifications: str = Form(default=""),
    price: float = Form(default=0),
    offer_mode: str = Form(default="both"),
    category: str = Form(default="auto"),
    video_duration: float = Form(default=0),
    images: list[UploadFile] = File(...),
    video: UploadFile | None = File(default=None),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    await require_marketplace_company(db, company_id)
    user = await current_marketplace_user(db, company_id, authorization)
    clean_title = _clean(title, 140)
    if len(clean_title) < 3:
        raise HTTPException(status_code=422, detail="titulo_requerido")
    clean_description = _clean(description, 2400)
    clean_specifications = _clean(specifications, 2400)
    clean_category = normalize_marketplace_category(category, clean_title, clean_description, clean_specifications)
    clean_price = _money(price)
    clean_offer_mode = _offer_mode(offer_mode)
    image_files = list(images or [])[: MAX_PUBLICATION_IMAGES + 1]
    if not image_files:
        raise HTTPException(status_code=422, detail="selecciona_una_foto")
    if len(image_files) > MAX_PUBLICATION_IMAGES:
        raise HTTPException(status_code=422, detail="maximo_5_fotos")
    uploads = [await _read_media(item, "image") for item in image_files]
    if video is not None and str(video.filename or "").strip():
        uploads.append(await _read_media(video, "video", video_duration))
    duplicate_result = await db.execute(
        text("""
            SELECT p.*, u.username, u.phone
            FROM marketplace_publications p
            JOIN marketplace_users u ON u.id = p.user_id
            WHERE p.company_id = CAST(:company_id AS uuid)
              AND p.user_id = CAST(:user_id AS uuid)
              AND p.status = 'published'
              AND p.created_at > now() - interval '90 seconds'
              AND lower(p.title) = lower(:title)
              AND p.description = :description
              AND p.specifications = :specifications
              AND p.price = :price
              AND p.offer_mode = :offer_mode
            ORDER BY p.created_at DESC
            LIMIT 1
        """),
        {"company_id": str(company_id), "user_id": str(user["id"]), "title": clean_title,
         "description": clean_description, "specifications": clean_specifications,
         "price": clean_price, "offer_mode": clean_offer_mode},
    )
    duplicate = duplicate_result.mappings().first()
    if duplicate:
        media = await _publication_media(db, company_id)
        return {"ok": True, "deduplicated": True, "publication": _publication_out(dict(duplicate), media.get(str(duplicate["id"]), []), request=request)}
    result = await db.execute(
        text("""
            INSERT INTO marketplace_publications
                (company_id, user_id, title, description, specifications, price, offer_mode, category, status)
            VALUES
                (CAST(:company_id AS uuid), CAST(:user_id AS uuid), :title, :description,
                 :specifications, :price, :offer_mode, :category, 'published')
            RETURNING *
        """),
        {
            "company_id": str(company_id),
            "user_id": str(user["id"]),
            "title": clean_title,
            "description": clean_description,
            "specifications": clean_specifications,
            "price": clean_price,
            "offer_mode": clean_offer_mode,
            "category": clean_category,
        },
    )
    publication = dict(result.mappings().first())
    media_out: list[dict[str, Any]] = []
    image_position = 0
    for upload in uploads:
        if upload["kind"] == "image":
            image_position += 1
            position = image_position
        else:
            position = 1
        media_result = await db.execute(
            text("""
                INSERT INTO marketplace_publication_media
                    (publication_id, kind, position, content_type, file_bytes, file_size, duration_seconds)
                VALUES
                    (CAST(:publication_id AS uuid), :kind, :position, :content_type, :file_bytes, :file_size, :duration)
                RETURNING id::text AS id, kind, position, content_type, file_size, duration_seconds
            """),
            {"publication_id": str(publication["id"]), "kind": upload["kind"], "position": position,
             "content_type": upload["content_type"], "file_bytes": upload["content"], "file_size": upload["size"], "duration": upload["duration"]},
        )
        item = dict(media_result.mappings().first())
        item["url"] = f"/api/v1/marketplace/publications/{publication['id']}/media/{item['id']}"
        if item.get("duration_seconds") is not None:
            item["duration_seconds"] = float(item["duration_seconds"])
        media_out.append(item)
    await db.commit()
    publication.update({"username": user["username"], "phone": user["phone"]})
    return {"ok": True, "publication": _publication_out(publication, media_out, request=request)}


@router.get("/publications/{publication_id}/media/{media_id}")
async def get_marketplace_publication_media(
    publication_id: uuid.UUID,
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await ensure_marketplace_storage(db)
    result = await db.execute(
        text("""
            SELECT m.content_type, m.file_bytes
            FROM marketplace_publication_media m
            JOIN marketplace_publications p ON p.id = m.publication_id
            WHERE m.id = CAST(:media_id AS uuid)
              AND m.publication_id = CAST(:publication_id AS uuid)
              AND p.status = 'published'
            LIMIT 1
        """),
        {"media_id": str(media_id), "publication_id": str(publication_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="archivo_no_encontrado")
    return Response(content=bytes(row["file_bytes"]), media_type=row["content_type"], headers={"Cache-Control": "public, max-age=86400"})


@router.get("/companies/{company_id}/manage/publications")
async def manage_marketplace_publications(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    await _require_marketplace_owner_panel(company_id, request, authorization, db)
    media = await _publication_media(db, company_id)
    rows = await _publication_rows(db, company_id, include_all=True)
    return {"ok": True, "publications": [_publication_out(row, media.get(str(row["id"]), []), request=request, include_phone=True) for row in rows]}


async def _conversation_for_user(db: AsyncSession, company_id: uuid.UUID, conversation_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT c.*, p.title,
                   buyer.username AS buyer_username, seller.username AS seller_username
            FROM marketplace_conversations c
            JOIN marketplace_publications p ON p.id = c.publication_id
            JOIN marketplace_users buyer ON buyer.id = c.buyer_user_id
            JOIN marketplace_users seller ON seller.id = c.seller_user_id
            WHERE c.id = CAST(:conversation_id AS uuid)
              AND c.company_id = CAST(:company_id AS uuid)
              AND (c.buyer_user_id = CAST(:user_id AS uuid) OR c.seller_user_id = CAST(:user_id AS uuid))
            LIMIT 1
        """),
        {"conversation_id": str(conversation_id), "company_id": str(company_id), "user_id": str(user_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="chat_no_encontrado")
    return dict(row)


@router.post("/companies/{company_id}/publications/{publication_id}/chat")
async def open_marketplace_chat(
    company_id: uuid.UUID,
    publication_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    seller_id = await db.scalar(
        text("SELECT user_id FROM marketplace_publications WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid) AND status = 'published'"),
        {"id": str(publication_id), "company_id": str(company_id)},
    )
    if not seller_id:
        raise HTTPException(status_code=404, detail="publicacion_no_encontrada")
    if str(seller_id) == str(user["id"]):
        raise HTTPException(status_code=422, detail="no_puedes_chatear_contigo")
    result = await db.execute(
        text("""
            INSERT INTO marketplace_conversations (company_id, publication_id, buyer_user_id, seller_user_id)
            VALUES (CAST(:company_id AS uuid), CAST(:publication_id AS uuid), CAST(:buyer_id AS uuid), CAST(:seller_id AS uuid))
            ON CONFLICT (publication_id, buyer_user_id) DO UPDATE SET updated_at = now()
            RETURNING id::text AS id
        """),
        {"company_id": str(company_id), "publication_id": str(publication_id), "buyer_id": str(user["id"]), "seller_id": str(seller_id)},
    )
    conversation_id = result.scalar_one()
    await db.commit()
    return {"ok": True, "conversation_id": conversation_id}


@router.post("/companies/{company_id}/publications/{publication_id}/offers", status_code=status.HTTP_201_CREATED)
async def create_marketplace_offer(
    company_id: uuid.UUID,
    publication_id: uuid.UUID,
    offer_type: str = Form(...),
    amount: str = Form(default=""),
    description: str = Form(default=""),
    images: list[UploadFile] | None = File(default=None),
    video: UploadFile | None = File(default=None),
    video_duration: float = Form(default=0),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    publication_result = await db.execute(
        text("""
            SELECT id::text AS id, user_id::text AS seller_id, title, offer_mode
            FROM marketplace_publications
            WHERE id = CAST(:publication_id AS uuid)
              AND company_id = CAST(:company_id AS uuid)
              AND status = 'published'
            LIMIT 1
        """),
        {"publication_id": str(publication_id), "company_id": str(company_id)},
    )
    publication = publication_result.mappings().first()
    if not publication:
        raise HTTPException(status_code=404, detail="publicacion_no_encontrada")
    if str(publication["seller_id"]) == str(user["id"]):
        raise HTTPException(status_code=422, detail="no_puedes_ofertar_tu_publicacion")

    clean_type = _clean(offer_type, 16).lower()
    if clean_type not in {"money", "change"}:
        raise HTTPException(status_code=422, detail="tipo_oferta_invalido")
    publication_mode = str(publication["offer_mode"] or "both")
    if publication_mode != "both" and publication_mode != clean_type:
        raise HTTPException(status_code=422, detail="tipo_oferta_no_aceptado")

    clean_description = _clean(description, 1200)
    clean_amount: float | None = None
    media_uploads: list[dict[str, Any]] = []
    if clean_type == "money":
        clean_amount = _money(amount)
        if clean_amount <= 0:
            raise HTTPException(status_code=422, detail="monto_oferta_requerido")
    else:
        if len(clean_description) < 3:
            raise HTTPException(status_code=422, detail="describe_el_cambio")
        image_files = list(images or [])[: MAX_OFFER_IMAGES + 1]
        if len(image_files) > MAX_OFFER_IMAGES:
            raise HTTPException(status_code=422, detail="maximo_3_fotos")
        media_uploads = [await _read_media(item, "image") for item in image_files]
        if video is not None and str(video.filename or "").strip():
            media_uploads.append(await _read_media(video, "video", video_duration))

    conversation_result = await db.execute(
        text("""
            INSERT INTO marketplace_conversations (company_id, publication_id, buyer_user_id, seller_user_id)
            VALUES (CAST(:company_id AS uuid), CAST(:publication_id AS uuid), CAST(:buyer_id AS uuid), CAST(:seller_id AS uuid))
            ON CONFLICT (publication_id, buyer_user_id) DO UPDATE SET updated_at = now()
            RETURNING id::text AS id
        """),
        {"company_id": str(company_id), "publication_id": str(publication_id),
         "buyer_id": str(user["id"]), "seller_id": str(publication["seller_id"])},
    )
    conversation_id = conversation_result.scalar_one()
    offer_result = await db.execute(
        text("""
            INSERT INTO marketplace_offers
                (company_id, publication_id, buyer_user_id, seller_user_id, conversation_id,
                 offer_type, amount, description, status)
            VALUES
                (CAST(:company_id AS uuid), CAST(:publication_id AS uuid), CAST(:buyer_id AS uuid),
                 CAST(:seller_id AS uuid), CAST(:conversation_id AS uuid), :offer_type, :amount,
                 :description, 'pending')
            RETURNING id::text AS id, offer_type, amount, description, status, created_at
        """),
        {"company_id": str(company_id), "publication_id": str(publication_id),
         "buyer_id": str(user["id"]), "seller_id": str(publication["seller_id"]),
         "conversation_id": conversation_id, "offer_type": clean_type,
         "amount": clean_amount, "description": clean_description},
    )
    offer = dict(offer_result.mappings().first())
    media_out: list[dict[str, Any]] = []
    for position, upload in enumerate(media_uploads):
        media_result = await db.execute(
            text("""
                INSERT INTO marketplace_offer_media
                    (offer_id, kind, position, content_type, file_bytes, file_size, duration_seconds)
                VALUES
                    (CAST(:offer_id AS uuid), :kind, :position, :content_type, :file_bytes, :file_size, :duration)
                RETURNING id::text AS id, kind, position, content_type, file_size, duration_seconds
            """),
            {"offer_id": offer["id"], "kind": upload["kind"], "position": position,
             "content_type": upload["content_type"], "file_bytes": upload["content"],
             "file_size": upload["size"], "duration": upload["duration"]},
        )
        item = dict(media_result.mappings().first())
        item["url"] = f"/api/v1/marketplace/companies/{company_id}/auth/offers/{offer['id']}/media/{item['id']}"
        media_out.append(item)

    if clean_type == "money":
        summary = f"Oferta de dinero: $ {clean_amount:,.0f}"
    else:
        attachments = []
        image_count = sum(1 for item in media_out if item["kind"] == "image")
        if image_count:
            attachments.append(f"{image_count} foto(s)")
        if any(item["kind"] == "video" for item in media_out):
            attachments.append("video")
        suffix = f" · Adjunta: {', '.join(attachments)}" if attachments else ""
        summary = f"Propuesta de cambio: {clean_description}{suffix}"
    await db.execute(
        text("""
            INSERT INTO marketplace_messages (conversation_id, sender_user_id, body)
            VALUES (CAST(:conversation_id AS uuid), CAST(:sender_id AS uuid), :body)
        """),
        {"conversation_id": conversation_id, "sender_id": str(user["id"]), "body": summary},
    )
    await db.execute(
        text("UPDATE marketplace_conversations SET updated_at = now() WHERE id = CAST(:id AS uuid)"),
        {"id": conversation_id},
    )
    await db.commit()
    if offer.get("amount") is not None:
        offer["amount"] = float(offer["amount"])
    offer["media"] = media_out
    return {"ok": True, "conversation_id": conversation_id, "offer": offer}


@router.get("/companies/{company_id}/auth/offers/{offer_id}/media/{media_id}")
async def get_marketplace_offer_media(
    company_id: uuid.UUID,
    offer_id: uuid.UUID,
    media_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    result = await db.execute(
        text("""
            SELECT m.content_type, m.file_bytes
            FROM marketplace_offer_media m
            JOIN marketplace_offers o ON o.id = m.offer_id
            WHERE m.id = CAST(:media_id AS uuid)
              AND m.offer_id = CAST(:offer_id AS uuid)
              AND o.company_id = CAST(:company_id AS uuid)
              AND (o.buyer_user_id = CAST(:user_id AS uuid) OR o.seller_user_id = CAST(:user_id AS uuid))
            LIMIT 1
        """),
        {"media_id": str(media_id), "offer_id": str(offer_id),
         "company_id": str(company_id), "user_id": str(user["id"])},
    )
    media = result.mappings().first()
    if not media:
        raise HTTPException(status_code=404, detail="archivo_no_encontrado")
    return Response(content=bytes(media["file_bytes"]), media_type=str(media["content_type"]))


@router.get("/companies/{company_id}/auth/chats")
async def list_marketplace_chats(
    company_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    result = await db.execute(
        text("""
            SELECT c.id::text AS id, c.publication_id::text AS publication_id, p.title,
                   CASE WHEN c.buyer_user_id = CAST(:user_id AS uuid) THEN seller.username ELSE buyer.username END AS other_username,
                   (SELECT body FROM marketplace_messages mm WHERE mm.conversation_id = c.id ORDER BY mm.created_at DESC LIMIT 1) AS last_message,
                   c.updated_at
            FROM marketplace_conversations c
            JOIN marketplace_publications p ON p.id = c.publication_id
            JOIN marketplace_users buyer ON buyer.id = c.buyer_user_id
            JOIN marketplace_users seller ON seller.id = c.seller_user_id
            WHERE c.company_id = CAST(:company_id AS uuid)
              AND (c.buyer_user_id = CAST(:user_id AS uuid) OR c.seller_user_id = CAST(:user_id AS uuid))
            ORDER BY c.updated_at DESC
            LIMIT 100
        """),
        {"company_id": str(company_id), "user_id": str(user["id"])},
    )
    return {"ok": True, "chats": [dict(row) for row in result.mappings().all()]}


@router.get("/companies/{company_id}/auth/chats/{conversation_id}/messages")
async def list_marketplace_messages(
    company_id: uuid.UUID,
    conversation_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    conversation = await _conversation_for_user(db, company_id, conversation_id, user["id"])
    result = await db.execute(
        text("""
            SELECT m.id::text AS id, m.sender_user_id::text AS sender_user_id, u.username, m.body, m.created_at
            FROM marketplace_messages m
            JOIN marketplace_users u ON u.id = m.sender_user_id
            WHERE m.conversation_id = CAST(:conversation_id AS uuid)
            ORDER BY m.created_at ASC LIMIT 500
        """),
        {"conversation_id": str(conversation_id)},
    )
    return {"ok": True, "conversation": {"id": str(conversation["id"]), "title": conversation["title"]}, "messages": [dict(row) for row in result.mappings().all()]}


@router.post("/companies/{company_id}/auth/chats/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_marketplace_message(
    company_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatMessageIn,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_marketplace_storage(db)
    user = await current_marketplace_user(db, company_id, authorization)
    await _conversation_for_user(db, company_id, conversation_id, user["id"])
    body = _clean(payload.body, 1200)
    if not body:
        raise HTTPException(status_code=422, detail="mensaje_vacio")
    result = await db.execute(
        text("""
            INSERT INTO marketplace_messages (conversation_id, sender_user_id, body)
            VALUES (CAST(:conversation_id AS uuid), CAST(:sender_id AS uuid), :body)
            RETURNING id::text AS id, sender_user_id::text AS sender_user_id, body, created_at
        """),
        {"conversation_id": str(conversation_id), "sender_id": str(user["id"]), "body": body},
    )
    await db.execute(text("UPDATE marketplace_conversations SET updated_at = now() WHERE id = CAST(:id AS uuid)"), {"id": str(conversation_id)})
    message = dict(result.mappings().first())
    message["username"] = user["username"]
    await db.commit()
    return {"ok": True, "message": message}
