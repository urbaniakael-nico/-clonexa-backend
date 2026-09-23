from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


SESSION_POLICY_SCOPES = {
    "client": {"label": "Panel cliente", "default": 2, "max": 20},
    "mini_panel": {"label": "Mini paneles", "default": 5, "max": 100},
}
SESSION_POLICY_MODES = {"replace_oldest", "reject_new"}

# Mesero/cocina/caja have their own rule: one device per user (see
# close_other_sessions_for_subject). The company-wide mini panel cap must not
# count them nor evict them: with replace_oldest, the 6th person logging in
# used to close whichever mini panel session was oldest -- often a mesero in
# the middle of his shift.
SINGLE_DEVICE_PANEL_TYPES = ("mesero", "cocina", "caja")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client_ip(request: Request | None) -> str:
    if not request:
        return ""
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()[:120]
    if request.client and request.client.host:
        return request.client.host[:120]
    return ""


def _user_agent(request: Request | None) -> str:
    if not request:
        return ""
    return str(request.headers.get("user-agent") or "")[:1000]


def _json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _clamp_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(maximum, parsed))


def default_session_policy() -> Dict[str, Any]:
    return {
        "enabled": False,
        "mode": "replace_oldest",
        "scopes": {
            code: {
                "label": meta["label"],
                "enabled": False,
                "max_sessions": meta["default"],
            }
            for code, meta in SESSION_POLICY_SCOPES.items()
        },
    }


def normalise_session_policy(raw: Any) -> Dict[str, Any]:
    base = default_session_policy()
    if not isinstance(raw, dict):
        return base

    mode = str(raw.get("mode") or "replace_oldest").strip().lower()
    if mode not in SESSION_POLICY_MODES:
        mode = "replace_oldest"

    base["enabled"] = bool(raw.get("enabled"))
    base["mode"] = mode

    scopes = raw.get("scopes") if isinstance(raw.get("scopes"), dict) else {}
    for code, meta in SESSION_POLICY_SCOPES.items():
        scoped = scopes.get(code) if isinstance(scopes.get(code), dict) else {}
        base["scopes"][code] = {
            "label": meta["label"],
            "enabled": bool(scoped.get("enabled")),
            "max_sessions": _clamp_int(scoped.get("max_sessions"), meta["default"], meta["max"]),
        }

    if raw.get("updated_at"):
        base["updated_at"] = str(raw.get("updated_at"))
    return base


async def ensure_access_sessions_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS clonexa_access_sessions (
            session_key VARCHAR(120) PRIMARY KEY,
            company_id UUID NULL,
            scope VARCHAR(40) NOT NULL,
            subject_id UUID NULL,
            subject_label VARCHAR(220) NOT NULL DEFAULT '',
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            ip_address VARCHAR(120) NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ NULL,
            closed_reason VARCHAR(160) NOT NULL DEFAULT '',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        );
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_clonexa_access_sessions_company_scope
        ON clonexa_access_sessions(company_id, scope, status, last_seen_at DESC);
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_clonexa_access_sessions_scope_status
        ON clonexa_access_sessions(scope, status, last_seen_at DESC);
    """))


async def read_company_session_policy(db: AsyncSession, company_id: UUID | str) -> Dict[str, Any]:
    result = await db.execute(
        text("SELECT settings_json FROM companies WHERE id = CAST(:company_id AS uuid)"),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        return default_session_policy()

    store = _json(row.get("settings_json"))
    security = store.get("security") if isinstance(store.get("security"), dict) else {}
    return normalise_session_policy(security.get("session_limits"))


async def _active_session_keys(db: AsyncSession, company_id: UUID | str | None, scope: str) -> list[str]:
    if company_id:
        result = await db.execute(
            text("""
                SELECT session_key
                FROM clonexa_access_sessions
                WHERE company_id = CAST(:company_id AS uuid)
                  AND scope = :scope
                  AND status = 'active'
                  AND COALESCE(metadata_json->>'panel_type', '') NOT IN ('mesero', 'cocina', 'caja')
                ORDER BY last_seen_at ASC, created_at ASC
            """),
            {"company_id": str(company_id), "scope": scope},
        )
    else:
        result = await db.execute(
            text("""
                SELECT session_key
                FROM clonexa_access_sessions
                WHERE company_id IS NULL
                  AND scope = :scope
                  AND status = 'active'
                ORDER BY last_seen_at ASC, created_at ASC
            """),
            {"scope": scope},
        )
    return [str(row[0]) for row in result.all()]


async def close_access_session(
    db: AsyncSession,
    session_key: str,
    reason: str = "closed_from_admin_v2",
    *,
    commit: bool = True,
) -> bool:
    await ensure_access_sessions_storage(db)
    result = await db.execute(
        text("""
            UPDATE clonexa_access_sessions
            SET status = 'closed',
                closed_at = COALESCE(closed_at, NOW()),
                closed_reason = :reason,
                last_seen_at = NOW()
            WHERE session_key = :session_key
              AND status = 'active'
        """),
        {"session_key": str(session_key), "reason": str(reason or "closed")[:160]},
    )
    if commit:
        await db.commit()
    return bool(getattr(result, "rowcount", 0))


async def close_other_sessions_for_subject(
    db: AsyncSession,
    *,
    company_id: UUID | str,
    scope: str,
    subject_id: UUID | str,
    reason: str = "Sesion cerrada desde otro dispositivo.",
    keep_device_id: str | None = None,
) -> int:
    """One-device-at-a-time login: close every OTHER active session of this same
    user (subject_id) in this scope, without touching sessions of other users
    of the same company/scope. Used by the mesero/cocina/caja login only, so it
    never changes the shared, company-wide session policy other mini panels use.

    keep_device_id: logging in again from the SAME phone/browser (a second
    tab, a reload that lost its token) must not kick that phone's own open
    panel -- only a login from a different device does.
    """
    await ensure_access_sessions_storage(db)
    device_filter = ""
    params = {
        "company_id": str(company_id),
        "scope": str(scope),
        "subject_id": str(subject_id),
        "reason": str(reason or "closed")[:160],
    }
    if keep_device_id:
        device_filter = "AND COALESCE(metadata_json->>'device_id', '') <> :device_id"
        params["device_id"] = str(keep_device_id)
    result = await db.execute(
        text(f"""
            UPDATE clonexa_access_sessions
            SET status = 'closed',
                closed_at = COALESCE(closed_at, NOW()),
                closed_reason = :reason,
                last_seen_at = NOW()
            WHERE company_id = CAST(:company_id AS uuid)
              AND scope = :scope
              AND subject_id = CAST(:subject_id AS uuid)
              AND status = 'active'
              {device_filter}
        """),
        params,
    )
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def ip_allowed_for_scope(
    db: AsyncSession,
    company_id: UUID | str,
    scope: str,
    ip_value: str,
) -> bool:
    """Mirrors app.main's page-load IP guard (companies.settings_json.security.
    ip_allowlist), but callable from inside an endpoint so mesero/cocina/caja
    routes enforce it themselves and do not rely only on the page middleware.
    """
    result = await db.execute(
        text("SELECT settings_json FROM companies WHERE id = CAST(:company_id AS uuid)"),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        return True

    store = _json(row.get("settings_json"))
    security = store.get("security") if isinstance(store.get("security"), dict) else {}
    policy = security.get("ip_allowlist") if isinstance(security.get("ip_allowlist"), dict) else {}
    if not policy.get("enabled"):
        return True

    scopes = policy.get("scopes") if isinstance(policy.get("scopes"), dict) else {}
    scoped = scopes.get(scope) if isinstance(scopes.get(scope), dict) else {}
    allowed_ips = scoped.get("allowed_ips") if isinstance(scoped.get("allowed_ips"), list) else []
    if not scoped.get("enabled") or not allowed_ips:
        return True

    import ipaddress

    try:
        candidate = ipaddress.ip_address(ip_value)
    except ValueError:
        return False

    for entry in allowed_ips:
        text_value = str(entry or "").strip()
        if not text_value:
            continue
        try:
            if "/" in text_value:
                if candidate in ipaddress.ip_network(text_value, strict=False):
                    return True
            elif candidate == ipaddress.ip_address(text_value):
                return True
        except ValueError:
            continue
    return False


async def close_company_access_sessions(
    db: AsyncSession,
    company_id: UUID | str,
    *,
    scope: str | None = None,
    reason: str = "closed_from_admin_v2",
) -> int:
    await ensure_access_sessions_storage(db)
    params = {"company_id": str(company_id), "reason": str(reason or "closed")[:160]}
    scope_filter = ""
    if scope:
        scope_filter = "AND scope = :scope"
        params["scope"] = str(scope)

    result = await db.execute(
        text(f"""
            UPDATE clonexa_access_sessions
            SET status = 'closed',
                closed_at = COALESCE(closed_at, NOW()),
                closed_reason = :reason,
                last_seen_at = NOW()
            WHERE company_id = CAST(:company_id AS uuid)
              AND status = 'active'
              {scope_filter}
        """),
        params,
    )
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def register_access_session(
    db: AsyncSession,
    *,
    company_id: UUID | str | None,
    scope: str,
    subject_id: UUID | str | None,
    subject_label: str,
    request: Request | None,
    enforce_policy: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    await ensure_access_sessions_storage(db)
    clean_scope = str(scope or "").strip().lower()
    if clean_scope not in {"client", "mini_panel", "admin_v2"}:
        raise HTTPException(status_code=400, detail="session_scope_invalid")

    single_device = str((metadata or {}).get("panel_type") or "") in SINGLE_DEVICE_PANEL_TYPES
    if enforce_policy and company_id and clean_scope in SESSION_POLICY_SCOPES and not single_device:
        policy = await read_company_session_policy(db, company_id)
        scoped = policy.get("scopes", {}).get(clean_scope, {})
        if policy.get("enabled") and scoped.get("enabled"):
            max_sessions = _clamp_int(
                scoped.get("max_sessions"),
                SESSION_POLICY_SCOPES[clean_scope]["default"],
                SESSION_POLICY_SCOPES[clean_scope]["max"],
            )
            active_keys = await _active_session_keys(db, company_id, clean_scope)
            if len(active_keys) >= max_sessions:
                if policy.get("mode") == "reject_new":
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Limite de sesiones activas alcanzado para este panel.",
                    )
                to_close = active_keys[: len(active_keys) - max_sessions + 1]
                for key in to_close:
                    await close_access_session(db, key, "replaced_by_new_login", commit=False)

    session_key = uuid4().hex
    metadata_json = json.dumps(metadata or {})
    await db.execute(
        text("""
            INSERT INTO clonexa_access_sessions (
                session_key, company_id, scope, subject_id, subject_label,
                status, ip_address, user_agent, metadata_json
            )
            VALUES (
                :session_key,
                CASE WHEN :company_id = '' THEN NULL ELSE CAST(:company_id AS uuid) END,
                :scope,
                CASE WHEN :subject_id = '' THEN NULL ELSE CAST(:subject_id AS uuid) END,
                :subject_label,
                'active',
                :ip_address,
                :user_agent,
                CAST(:metadata_json AS jsonb)
            )
        """),
        {
            "session_key": session_key,
            "company_id": str(company_id or ""),
            "scope": clean_scope,
            "subject_id": str(subject_id or ""),
            "subject_label": str(subject_label or "")[:220],
            "ip_address": _client_ip(request),
            "user_agent": _user_agent(request),
            "metadata_json": metadata_json,
        },
    )
    await db.commit()
    return session_key


async def validate_access_session(
    db: AsyncSession,
    session_key: str,
    *,
    expected_company_id: UUID | str | None = None,
    expected_scope: str | None = None,
) -> Dict[str, Any]:
    await ensure_access_sessions_storage(db)
    result = await db.execute(
        text("""
            SELECT session_key, company_id::text AS company_id, scope, status, subject_label, closed_reason
            FROM clonexa_access_sessions
            WHERE session_key = :session_key
        """),
        {"session_key": str(session_key or "")},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion no registrada.")

    if expected_company_id and str(row.get("company_id") or "") != str(expected_company_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion no pertenece a esta empresa.")

    if expected_scope and str(row.get("scope") or "") != str(expected_scope):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion no pertenece a este panel.")

    if str(row.get("status") or "").lower() != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(row.get("closed_reason") or "").strip() or "Sesion cerrada desde Admin V2.",
        )

    try:
        await db.execute(
            text("""
                UPDATE clonexa_access_sessions
                SET last_seen_at = NOW()
                WHERE session_key = :session_key
                  AND (last_seen_at IS NULL OR last_seen_at < NOW() - INTERVAL '30 seconds')
            """),
            {"session_key": str(session_key)},
        )
        await db.commit()
    except Exception:
        await db.rollback()
    return dict(row)


async def list_access_sessions(
    db: AsyncSession,
    *,
    company_id: UUID | str | None = None,
    scope: str | None = None,
    include_closed: bool = False,
    limit: int = 80,
) -> list[Dict[str, Any]]:
    await ensure_access_sessions_storage(db)
    params: Dict[str, Any] = {"limit": max(1, min(250, int(limit or 80)))}
    filters = []

    if company_id is not None:
        filters.append("company_id = CAST(:company_id AS uuid)")
        params["company_id"] = str(company_id)
    else:
        filters.append("company_id IS NULL")

    if scope:
        filters.append("scope = :scope")
        params["scope"] = str(scope)
    if not include_closed:
        filters.append("status = 'active'")

    where = " AND ".join(filters) if filters else "TRUE"
    result = await db.execute(
        text(f"""
            SELECT
                session_key,
                company_id::text AS company_id,
                scope,
                subject_id::text AS subject_id,
                subject_label,
                status,
                ip_address,
                LEFT(user_agent, 220) AS user_agent,
                created_at,
                last_seen_at,
                closed_at,
                closed_reason
            FROM clonexa_access_sessions
            WHERE {where}
            ORDER BY last_seen_at DESC, created_at DESC
            LIMIT :limit
        """),
        params,
    )
    rows: list[Dict[str, Any]] = []
    for row in result.mappings().all():
        item = dict(row)
        for key in ("created_at", "last_seen_at", "closed_at"):
            if item.get(key):
                item[key] = item[key].isoformat()
        rows.append(item)
    return rows
