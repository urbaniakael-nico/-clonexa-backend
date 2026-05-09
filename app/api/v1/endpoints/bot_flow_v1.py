from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.bot_flows.base import BotFlowContext
from app.services.bot_flow_resolver import bot_flow_resolver

router = APIRouter()


async def enabled_module_codes(db: AsyncSession, company_id: str) -> set[str]:
    result = await db.execute(
        text("""
            SELECT lower(m.code) AS code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id::text = :company_id
              AND cm.enabled IS TRUE
              AND m.is_active IS TRUE
        """),
        {"company_id": company_id},
    )

    return {str(row[0]).lower() for row in result.all()}


@router.post("/companies/{company_id}/dry-run")
async def bot_flow_dry_run(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    employee_id = str(payload.get("employee_id") or "DRY_RUN_EMPLOYEE")
    employee_name = str(payload.get("employee_name") or "DRY RUN")
    telegram_user_id = str(payload.get("telegram_user_id") or "DRY_RUN_TELEGRAM")
    telegram_username = payload.get("telegram_username")
    language = str(payload.get("language") or "es")
    status_key = str(payload.get("status_key") or "sin_turno")
    text_value = str(payload.get("text") or "")

    enabled_modules = await enabled_module_codes(db, company_id)

    ctx = BotFlowContext(
        company_id=company_id,
        employee_id=employee_id,
        employee_name=employee_name,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        language=language,
        status_key=status_key,
        enabled_modules=enabled_modules,
    )

    result = await bot_flow_resolver.handle(
        db,
        ctx,
        {
            "text": text_value,
            "source": "dry_run",
        },
    )

    return {
        "ok": True,
        "company_id": company_id,
        "enabled_modules": sorted(enabled_modules),
        "input": {
            "text": text_value,
            "status_key": status_key,
            "language": language,
        },
        "flow_result": {
            "handled": result.handled,
            "ok": result.ok,
            "action": result.action,
            "message": result.message,
            "reply_text": result.reply_text,
            "reply_markup": result.reply_markup,
            "event_created": result.event_created,
        },
    }
