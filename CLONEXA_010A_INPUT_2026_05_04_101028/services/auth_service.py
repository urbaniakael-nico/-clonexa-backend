from __future__ import annotations
from datetime import datetime, timezone

import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import CompanyUser
from app.models.core import Company

try:
    from app.core.config import settings
except Exception:  # pragma: no cover
    settings = None


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
MAX_BCRYPT_PASSWORD_BYTES = 72
VALID_ROLES = {"company_admin", "manager", "operator", "viewer", "supervisor", "staff"}
VALID_STATUS = {"active", "inactive", "blocked"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _settings_value(*names: str, default: Any = None) -> Any:
    for name in names:
        if settings is not None and hasattr(settings, name):
            value = getattr(settings, name)
            if value not in (None, ""):
                return value
        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value
    return default


def get_jwt_secret() -> str:
    secret = _settings_value("SECRET_KEY", "CLONEXA_JWT_SECRET", default="")
    if not secret:
        # Local fallback keeps development running, but production must set a real secret.
        secret = "clonexa-local-development-secret-change-me"
    return str(secret)


def get_access_token_expire_minutes() -> int:
    raw = _settings_value("ACCESS_TOKEN_EXPIRE_MINUTES", default="480")
    try:
        return int(raw)
    except Exception:
        return 480


def _looks_like_bcrypt_hash(value: str) -> bool:
    return str(value or "").startswith(BCRYPT_PREFIXES)


def _password_bytes_len(password: str) -> int:
    return len(str(password or "").encode("utf-8"))


def hash_password(password: str) -> str:
    clean_password = str(password or "")

    if not clean_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña no puede estar vacía.",
        )

    if _looks_like_bcrypt_hash(clean_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña enviada parece un hash y fue rechazada.",
        )

    if _password_bytes_len(clean_password) > MAX_BCRYPT_PASSWORD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña es demasiado larga.",
        )

    return pwd_context.hash(clean_password)


def verify_password(password: str, password_hash: str) -> bool:
    clean_password = str(password or "")
    stored_hash = str(password_hash or "")

    if not clean_password or not stored_hash:
        return False

    # Critical guard: never pass a stored hash as the plain password to bcrypt.
    if _looks_like_bcrypt_hash(clean_password):
        return False

    # bcrypt rejects passwords above 72 bytes. Do not truncate silently.
    if _password_bytes_len(clean_password) > MAX_BCRYPT_PASSWORD_BYTES:
        return False

    if not _looks_like_bcrypt_hash(stored_hash):
        return False

    try:
        return bool(pwd_context.verify(clean_password, stored_hash))
    except Exception:
        return False


def generate_temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"Clonexa-{token}-2026!"


def create_access_token(data: Dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    expire_minutes = expires_minutes or get_access_token_expire_minutes()
    payload = dict(data)
    payload["exp"] = utc_now() + timedelta(minutes=expire_minutes)
    payload["iat"] = utc_now()
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
        )


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _payload_to_dict(payload: Any, exclude_unset: bool = True) -> Dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return dict(payload)
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=exclude_unset)
    return dict(payload)


async def get_company_or_404(db: AsyncSession, company_id: UUID) -> Company:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada.")
    return company


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[CompanyUser]:
    normalized = normalize_email(email)
    result = await db.execute(select(CompanyUser).where(CompanyUser.email == normalized))
    return result.scalar_one_or_none()


async def get_company_user_or_404(db: AsyncSession, company_id: UUID, user_id: UUID) -> CompanyUser:
    result = await db.execute(
        select(CompanyUser).where(
            CompanyUser.company_id == company_id,
            CompanyUser.id == user_id,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> CompanyUser:
    normalized_email = normalize_email(email)
    user = await get_user_by_email(db, normalized_email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    if str(user.status or "").lower() != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo o bloqueado.",
        )

    locked_until = _aware(user.locked_until)
    if locked_until and locked_until > utc_now():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario temporalmente bloqueado.",
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts = int(user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= 5:
            user.locked_until = utc_now() + timedelta(minutes=15)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utc_now()
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_company_user(db: AsyncSession, token: str) -> CompanyUser:
    payload = decode_access_token(token)
    raw_user_id = payload.get("sub") or payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        )

    try:
        user_id = UUID(str(raw_user_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        )

    result = await db.execute(select(CompanyUser).where(CompanyUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado.",
        )

    if str(user.status or "").lower() != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo o bloqueado.",
        )

    return user


async def change_password(
    db: AsyncSession,
    user: CompanyUser,
    current_password: str,
    new_password: str,
) -> Dict[str, bool]:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La contraseña actual no es válida.",
        )

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = utc_now()
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()
    await db.refresh(user)
    return {"ok": True}


async def list_company_users(db: AsyncSession, company_id: UUID) -> List[CompanyUser]:
    await get_company_or_404(db, company_id)
    result = await db.execute(
        select(CompanyUser)
        .where(CompanyUser.company_id == company_id)
        .order_by(CompanyUser.created_at.desc())
    )
    return list(result.scalars().all())


async def create_company_user(db: AsyncSession, company_id: UUID, payload: Any) -> CompanyUser:
    await get_company_or_404(db, company_id)
    data = _payload_to_dict(payload)
    email = normalize_email(data.get("email", ""))
    password = str(data.get("password") or "")
    role = str(data.get("role") or "company_admin").strip()
    status_value = str(data.get("status") or "active").strip().lower()

    if role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rol inválido.")
    if status_value not in VALID_STATUS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Estado inválido.")
    if not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña es obligatoria.")

    existing = await get_user_by_email(db, email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya existe.")

    user = CompanyUser(
        company_id=company_id,
        email=email,
        password_hash=hash_password(password),
        full_name=str(data.get("full_name") or "").strip() or email,
        role=role,
        status=status_value,
        must_change_password=True,
        failed_login_attempts=0,
        locked_until=None,
        settings_json=data.get("settings_json") or {},
    )
    db.add(user)
    # CLONEXA_OWNER_TIMESTAMP_GUARD
    now = datetime.now(timezone.utc)

    if getattr(user, "created_at", None) is None:
        user.created_at = now

    if getattr(user, "updated_at", None) is None:
        user.updated_at = now

    if hasattr(user, "last_password_reset_at") and getattr(user, "last_password_reset_at", None) is None:
        user.last_password_reset_at = now
    await db.commit()
    await db.refresh(user)
    return user


async def update_company_user(db: AsyncSession, company_id: UUID, user_id: UUID, payload: Any) -> CompanyUser:
    user = await get_company_user_or_404(db, company_id, user_id)
    data = _payload_to_dict(payload)

    if "full_name" in data and data["full_name"] is not None:
        user.full_name = str(data["full_name"]).strip() or user.full_name

    if "role" in data and data["role"] is not None:
        role = str(data["role"]).strip()
        if role not in VALID_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rol inválido.")
        user.role = role

    if "status" in data and data["status"] is not None:
        status_value = str(data["status"]).strip().lower()
        if status_value not in VALID_STATUS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Estado inválido.")
        user.status = status_value

    user.updated_at = utc_now()
    await db.commit()
    await db.refresh(user)
    return user


async def reset_company_user_password(
    db: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    user = await get_company_user_or_404(db, company_id, user_id)

    temporary_password = str(password or "").strip() or generate_temporary_password()

    if _looks_like_bcrypt_hash(temporary_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña temporal no puede ser un hash.",
        )

    new_hash = hash_password(temporary_password)

    user.password_hash = new_hash
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.locked_until = None
    user.status = "active"
    user.last_password_reset_at = utc_now()
    user.updated_at = utc_now()

    await db.commit()
    await db.refresh(user)

    return {
        "ok": True,
        "temporary_password": temporary_password,
        "must_change_password": True,
    }


async def unlock_company_user(db: AsyncSession, company_id: UUID, user_id: UUID) -> Dict[str, bool]:
    user = await get_company_user_or_404(db, company_id, user_id)
    user.status = "active"
    user.failed_login_attempts = 0
    user.locked_until = None
    user.updated_at = utc_now()
    await db.commit()
    await db.refresh(user)
    return {"ok": True}


async def company_user_out_payload(db: AsyncSession, user: CompanyUser) -> Dict[str, Any]:
    company = await get_company_or_404(db, user.company_id)
    return {
        "id": user.id,
        "company_id": user.company_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "status": user.status,
        "must_change_password": bool(user.must_change_password),
        "failed_login_attempts": int(user.failed_login_attempts or 0),
        "locked_until": user.locked_until,
        "last_login_at": user.last_login_at,
        "password_changed_at": user.password_changed_at,
        "last_password_reset_at": user.last_password_reset_at,
        "company_name": company.name,
        "company_slug": company.slug,
    }


async def company_mini_payload(db: AsyncSession, company_id: UUID) -> Dict[str, Any]:
    company = await get_company_or_404(db, company_id)
    return {
        "id": company.id,
        "name": company.name,
        "slug": company.slug,
        "timezone": getattr(company, "timezone", None),
        "status": getattr(company, "status", None),
        "plan": getattr(company, "plan", None),
    }


async def company_modules_payload(db: AsyncSession, company_id: UUID) -> List[Dict[str, Any]]:
    try:
        result = await db.execute(
            text(
                """
                SELECT
                    m.id,
                    m.code,
                    m.name,
                    m.category,
                    m.is_active,
                    cm.enabled
                FROM company_modules cm
                JOIN modules m ON m.id = cm.module_id
                WHERE cm.company_id = :company_id
                ORDER BY m.category NULLS LAST, m.code
                """
            ),
            {"company_id": str(company_id)},
        )
        return [dict(row._mapping) for row in result.fetchall()]
    except Exception:
        return []

# =============================================================================
# CLONEXA HOTFIX 007C - DIRECT BCRYPT OVERRIDE
# Evita bug passlib/bcrypt: password cannot be longer than 72 bytes
# =============================================================================
import bcrypt as _clonexa_bcrypt


def _clonexa_extract_plain_password(password):
    if password is None:
        return None

    if isinstance(password, dict):
        password = (
            password.get("password")
            or password.get("new_password")
            or password.get("temporary_password")
            or password.get("current_password")
        )

    for attr in ("password", "new_password", "temporary_password", "current_password"):
        if hasattr(password, attr):
            value = getattr(password, attr)
            if value:
                password = value
                break

    if password is None:
        return None

    return str(password).strip()


def _clonexa_looks_like_bcrypt_hash(value: str) -> bool:
    return bool(value) and (
        value.startswith("$2a$")
        or value.startswith("$2b$")
        or value.startswith("$2y$")
    )


def hash_password(password: str) -> str:
    clean_password = _clonexa_extract_plain_password(password)

    if not clean_password:
        raise ValueError("Password is required.")

    if _clonexa_looks_like_bcrypt_hash(clean_password):
        raise ValueError("Refusing to hash an existing bcrypt hash as plain password.")

    password_bytes = clean_password.encode("utf-8")

    if len(password_bytes) > 72:
        raise ValueError("Password cannot be longer than 72 bytes.")

    return _clonexa_bcrypt.hashpw(
        password_bytes,
        _clonexa_bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    clean_password = _clonexa_extract_plain_password(password)

    if not clean_password or not password_hash:
        return False

    if _clonexa_looks_like_bcrypt_hash(clean_password):
        return False

    password_bytes = clean_password.encode("utf-8")

    if len(password_bytes) > 72:
        return False

    try:
        return _clonexa_bcrypt.checkpw(
            password_bytes,
            str(password_hash).encode("utf-8")
        )
    except Exception:
        return False

# =============================================================================
# END CLONEXA HOTFIX 007C
# =============================================================================
