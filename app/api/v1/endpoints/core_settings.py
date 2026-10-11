from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, get_db, require_company_user_for_tenant
from app.api.v1.endpoints.company_users import require_company_user_not_role
from app.services import company_locale


router = APIRouter()

# Fase 2: en empresas con waiter_ordering (hoy solo Asadero El Socio), el rol
# "administrador" no puede ver ni editar Ajustes de empresa. No-op para el
# resto de empresas (sin el módulo activo).
_NOT_ADMINISTRADOR = require_company_user_not_role({"administrador"})

# Fase A (todas las empresas): Ajustes exige sesion SIEMPRE, validada en el
# servidor: usuario de ESA empresa o Admin V2 (el portal abierto desde la
# consola). Guardar solo el dueño o el admin de la empresa (o Admin V2).
SETTINGS_WRITER_ROLES = ADMIN_ROLES | {"dueno", "dueño", "owner", "propietario"}


async def require_settings_reader(
    company_id: str, request: Request, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> dict:
    cid = _company_uuid(company_id)
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        return {"admin_v2": True, "role": "admin_v2"}
    user = await require_company_user_for_tenant(db, authorization, UUID(cid))
    return {"admin_v2": False, "role": str(getattr(user, "role", "") or "").strip().lower()}


async def require_settings_writer(actor: dict = Depends(require_settings_reader)) -> dict:
    if not actor["admin_v2"] and actor["role"] not in SETTINGS_WRITER_ROLES:
        raise HTTPException(status_code=403, detail="Solo el dueño o el administrador de la empresa puede guardar los ajustes.")
    return actor


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
    if not company_locale.valid_timezone(tz):
        raise HTTPException(status_code=400, detail="La zona horaria no es válida: elígela de la lista.")
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
    _not_admin: None = Depends(_NOT_ADMINISTRADOR),
    _actor: dict = Depends(require_settings_reader),
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

    payload = _row_payload(dict(row))
    # La zona efectiva (con respaldo en companies.timezone) y la lista de zonas validas.
    payload["effective_timezone"] = (await company_locale.get_company_locale(db, company_id))["timezone"]
    payload["timezone_choices"] = list(company_locale.timezone_choices())
    return payload


@router.put("/{company_id}/core-settings")
async def update_company_core_settings(
    company_id: str,
    payload: CoreSettingsIn,
    db: AsyncSession = Depends(get_db),
    _not_admin: None = Depends(_NOT_ADMINISTRADOR),
    _actor: dict = Depends(require_settings_writer),
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
    if row and timezone_value:
        # Una sola fuente: lo que ya lee companies.timezone (corte diario, cierre
        # del dia, confirmar salida, hospitality) sigue la zona de Ajustes.
        await db.execute(
            text("UPDATE companies SET timezone = :tz WHERE id = CAST(:company_id AS UUID)"),
            {"tz": timezone_value, "company_id": company_id},
        )
    await db.commit()
    from app.services import company_tz_middleware

    company_tz_middleware.invalidate(company_id)  # la zona/moneda nueva se ve en la siguiente peticion

    if not row:
        raise HTTPException(status_code=500, detail="Could not update core settings")

    return _row_payload(dict(row))


@router.get("/{company_id}/locale")
async def get_company_locale_view(
    company_id: str,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_settings_reader),
) -> dict[str, Any]:
    """Solo lectura para el portal: moneda, zona horaria, idioma y decimales de la empresa."""
    return await company_locale.get_company_locale(db, _company_uuid(company_id))
