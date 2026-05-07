from __future__ import annotations

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
