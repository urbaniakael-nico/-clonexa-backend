from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import extract_bearer_token, get_db
from app.schemas.auth import ChangePasswordRequest, LoginRequest, MeResponse, TokenResponse
from app.services.auth_service import (
    authenticate_user,
    change_password as change_password_service,
    company_mini_payload,
    company_modules_payload,
    company_user_out_payload,
    create_access_token,
    decode_access_token,
    get_access_token_expire_minutes,
    get_current_company_user,
)
from app.services.access_sessions import close_access_session, register_access_session

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await authenticate_user(db, payload.email, payload.password)
    expires_in_minutes = get_access_token_expire_minutes()
    session_key = await register_access_session(
        db,
        company_id=user.company_id,
        scope="client",
        subject_id=user.id,
        subject_label=user.email or user.full_name or "panel cliente",
        request=request,
    )
    access_token = create_access_token(
        {
            "sub": str(user.id),
            "user_id": str(user.id),
            "email": user.email,
            "company_id": str(user.company_id),
            "role": user.role,
            "scope": "client",
            "sid": session_key,
        },
        expires_minutes=expires_in_minutes,
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in_minutes * 60,
        user=await company_user_out_payload(db, user),
    )


@router.get("/me", response_model=MeResponse)
async def me(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    token = extract_bearer_token(authorization)
    user = await get_current_company_user(db, token)
    return MeResponse(
        user=await company_user_out_payload(db, user),
        company=await company_mini_payload(db, user.company_id),
        modules=await company_modules_payload(db, user.company_id),
    )


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    token = extract_bearer_token(authorization)
    user = await get_current_company_user(db, token)
    return await change_password_service(db, user, payload.current_password, payload.new_password)


@router.post("/logout")
async def logout(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    if authorization:
        try:
            payload = decode_access_token(extract_bearer_token(authorization))
            session_key = payload.get("sid") or payload.get("session_key")
            if session_key:
                await close_access_session(db, str(session_key), "logout")
        except Exception:
            pass
    return {"ok": True}


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
    try:
        token = _020a_bearer_token(request)
        payload = _decode_access_token(token)
        session_key = payload.get("sid") or payload.get("session_key")
        if session_key:
            await close_access_session(db, str(session_key), "logout", commit=False)
    except Exception:
        pass

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
