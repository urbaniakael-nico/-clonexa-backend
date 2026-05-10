from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

DEFAULT_SETTINGS = {
    "payroll": {
        "ordinary_hours_limit": None,
        "pause_policy": "exclude",
    },
    "payroll_cuts": {
        "allow_close": True,
        "allow_export": True,
        "allow_archive": True,
    },
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_hours(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        number = float(str(value).replace(",", "."))
    except Exception:
        raise HTTPException(status_code=400, detail="ordinary_hours_limit must be numeric")

    if number <= 0:
        raise HTTPException(status_code=400, detail="ordinary_hours_limit must be greater than zero")

    if number > 744:
        raise HTTPException(status_code=400, detail="ordinary_hours_limit too high")

    return round(number, 2)


def merge_settings(current: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    base = json.loads(json.dumps(DEFAULT_SETTINGS))

    if isinstance(current, dict):
        for key, value in current.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key].update(value)
            else:
                base[key] = value

    if isinstance(incoming, dict):
        payroll = incoming.get("payroll")
        if isinstance(payroll, dict):
            if "ordinary_hours_limit" in payroll:
                base["payroll"]["ordinary_hours_limit"] = normalize_hours(payroll.get("ordinary_hours_limit"))
            if "pause_policy" in payroll:
                base["payroll"]["pause_policy"] = "exclude"

        cuts = incoming.get("payroll_cuts")
        if isinstance(cuts, dict):
            for field in ["allow_close", "allow_export", "allow_archive"]:
                if field in cuts:
                    base["payroll_cuts"][field] = bool(cuts.get(field))

    base["payroll"]["pause_policy"] = "exclude"
    return base


async def ensure_company_settings_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_settings (
            company_id text PRIMARY KEY,
            settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.commit()


async def read_settings_row(db: AsyncSession, company_id: str) -> dict[str, Any]:
    await ensure_company_settings_storage(db)

    result = await db.execute(
        text("""
            SELECT settings_json, updated_at
            FROM company_settings
            WHERE company_id = :company_id
            LIMIT 1
        """),
        {"company_id": company_id},
    )

    row = result.mappings().first()

    if not row:
        settings = merge_settings(None, None)

        await db.execute(
            text("""
                INSERT INTO company_settings (company_id, settings_json, created_at, updated_at)
                VALUES (:company_id, CAST(:settings AS jsonb), now(), now())
                ON CONFLICT (company_id) DO NOTHING
            """),
            {
                "company_id": company_id,
                "settings": json.dumps(settings),
            },
        )
        await db.commit()

        return {
            "company_id": company_id,
            "settings": settings,
            "updated_at": None,
        }

    raw = row.get("settings_json") or {}

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}

    return {
        "company_id": company_id,
        "settings": merge_settings(raw, None),
        "updated_at": row.get("updated_at").isoformat() if isinstance(row.get("updated_at"), datetime) else row.get("updated_at"),
    }


@router.get("/companies/{company_id}")
async def get_company_settings(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await read_settings_row(db, company_id)
    return {
        "ok": True,
        **data,
    }


@router.put("/companies/{company_id}")
async def put_company_settings(
    company_id: str,
    payload: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    current = await read_settings_row(db, company_id)
    settings = merge_settings(current.get("settings"), payload)

    await db.execute(
        text("""
            INSERT INTO company_settings (company_id, settings_json, created_at, updated_at)
            VALUES (:company_id, CAST(:settings AS jsonb), now(), now())
            ON CONFLICT (company_id)
            DO UPDATE SET settings_json = EXCLUDED.settings_json, updated_at = now()
        """),
        {
            "company_id": company_id,
            "settings": json.dumps(settings),
        },
    )
    await db.commit()

    fresh = await read_settings_row(db, company_id)

    return {
        "ok": True,
        **fresh,
    }
