from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.integrations.telegram.parser import parse_telegram_update
from app.models.company_bot_instance import CompanyBotInstance
from app.models.core import Company
from app.schemas.bot import (
    BotResponse,
    TelegramBotConfigIn,
    TelegramBotConfigOut,
    TelegramBotTestOut,
)
from app.services.event_engine import EventEngine

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover
    Fernet = None


router = APIRouter()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def mask_token(token: str | None) -> str | None:
    if not token:
        return None
    value = str(token).strip()
    if len(value) <= 12:
        return f"{value[:4]}****"
    return f"{value[:8]}****{value[-6:]}"


def _fernet():
    if Fernet is None:
        return None
    secret = get_settings().JWT_SECRET_KEY or "clonexa-local-secret"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_token(token: str) -> str:
    token = token.strip()
    fernet = _fernet()
    if fernet is not None:
        return "fernet:" + fernet.encrypt(token.encode("utf-8")).decode("utf-8")
    return "b64:" + base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


def decrypt_token(stored: str | None) -> str | None:
    if not stored:
        return None
    if stored.startswith("fernet:"):
        fernet = _fernet()
        if fernet is None:
            raise HTTPException(status_code=500, detail="Token encryption backend unavailable")
        return fernet.decrypt(stored.removeprefix("fernet:").encode("utf-8")).decode("utf-8")
    if stored.startswith("b64:"):
        return base64.urlsafe_b64decode(stored.removeprefix("b64:").encode("utf-8")).decode("utf-8")
    return stored


async def ensure_company_exists(db: AsyncSession, company_id: UUID) -> Company:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


async def ensure_bot_storage(db: AsyncSession) -> None:
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_bot_instances (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel varchar(40) NOT NULL DEFAULT 'telegram',
            name varchar(180) NULL,
            bot_username varchar(180) NULL,
            bot_token_encrypted text NULL,
            token_mask varchar(80) NULL,
            status varchar(40) NOT NULL DEFAULT 'configured',
            last_validated_at timestamptz NULL,
            last_error text NULL,
            config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_company_bot_instances_company_channel UNIQUE (company_id, channel)
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_bot_instances_company_id ON company_bot_instances(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_bot_instances_channel ON company_bot_instances(channel);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_bot_instances_status ON company_bot_instances(status);"))


def bot_out(row: CompanyBotInstance | None, company_id: UUID | None = None) -> TelegramBotConfigOut:
    if not row:
        return TelegramBotConfigOut(
            configured=False,
            ok=True,
            company_id=company_id,
            status="not_configured",
            masked_token=None,
        )

    return TelegramBotConfigOut(
        configured=bool(row.bot_token_encrypted),
        ok=row.status != "error",
        id=row.id,
        company_id=row.company_id,
        channel=row.channel,
        name=row.name,
        bot_username=row.bot_username,
        masked_token=row.token_mask,
        status=row.status or "configured",
        last_validated_at=row.last_validated_at,
        last_error=row.last_error,
        config_json=row.config_json or {},
    )


async def get_telegram_instance(db: AsyncSession, company_id: UUID) -> CompanyBotInstance | None:
    await ensure_bot_storage(db)
    result = await db.execute(
        select(CompanyBotInstance).where(
            CompanyBotInstance.company_id == company_id,
            CompanyBotInstance.channel == "telegram",
        )
    )
    return result.scalar_one_or_none()


@router.get("/companies/{company_id}/telegram", response_model=TelegramBotConfigOut)
async def get_company_telegram_bot(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotConfigOut:
    await ensure_company_exists(db, company_id)
    row = await get_telegram_instance(db, company_id)
    return bot_out(row, company_id)


@router.put("/companies/{company_id}/telegram", response_model=TelegramBotConfigOut)
async def save_company_telegram_bot(
    company_id: UUID,
    payload: TelegramBotConfigIn,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotConfigOut:
    company = await ensure_company_exists(db, company_id)
    await ensure_bot_storage(db)

    token = (payload.token or "").strip()
    name = (payload.name or "").strip() or f"{company.name} Telegram Bot"

    row = await get_telegram_instance(db, company_id)
    if row is None:
        if not token:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Telegram token is required")
        row = CompanyBotInstance(
            company_id=company_id,
            channel="telegram",
            name=name,
            bot_token_encrypted=encrypt_token(token),
            token_mask=mask_token(token),
            status="configured",
            config_json={},
            updated_at=utcnow(),
        )
        db.add(row)
    else:
        row.name = name
        row.updated_at = utcnow()
        if token:
            row.bot_token_encrypted = encrypt_token(token)
            row.token_mask = mask_token(token)
            row.bot_username = None
            row.last_validated_at = None
            row.last_error = None
        if not row.bot_token_encrypted:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Telegram token is required")
        row.status = "configured"

    await db.commit()
    await db.refresh(row)
    return bot_out(row, company_id)


@router.post("/companies/{company_id}/telegram/test", response_model=TelegramBotTestOut)
async def test_company_telegram_bot(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotTestOut:
    await ensure_company_exists(db, company_id)
    row = await get_telegram_instance(db, company_id)
    if row is None or not row.bot_token_encrypted:
        raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")

    token = decrypt_token(row.bot_token_encrypted)
    if not token:
        raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")

    telegram_payload: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            telegram_payload = response.json()
            if response.status_code >= 400 or not telegram_payload.get("ok"):
                row.status = "error"
                row.last_error = str(telegram_payload.get("description") or f"HTTP {response.status_code}")
                row.last_validated_at = utcnow()
                row.updated_at = utcnow()
                await db.commit()
                await db.refresh(row)
                out = bot_out(row, company_id).model_dump()
                return TelegramBotTestOut(**out, telegram_response=telegram_payload)

            user = telegram_payload.get("result") or {}
            row.bot_username = user.get("username")
            row.name = row.name or user.get("first_name") or "Telegram Bot"
            row.status = "active"
            row.last_error = None
            row.last_validated_at = utcnow()
            row.updated_at = utcnow()
            row.config_json = {
                **(row.config_json or {}),
                "telegram_bot_id": user.get("id"),
                "can_join_groups": user.get("can_join_groups"),
                "can_read_all_group_messages": user.get("can_read_all_group_messages"),
                "supports_inline_queries": user.get("supports_inline_queries"),
            }
            await db.commit()
            await db.refresh(row)
            out = bot_out(row, company_id).model_dump()
            return TelegramBotTestOut(**out, telegram_response={"ok": True, "result": user})

    except httpx.HTTPError as exc:
        row.status = "error"
        row.last_error = f"Telegram connection error: {exc}"
        row.last_validated_at = utcnow()
        row.updated_at = utcnow()
        await db.commit()
        await db.refresh(row)
        out = bot_out(row, company_id).model_dump()
        return TelegramBotTestOut(**out, telegram_response={"ok": False, "description": str(exc)})


@router.post("/companies/{company_id}/telegram/deactivate", response_model=TelegramBotConfigOut)
async def deactivate_company_telegram_bot(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotConfigOut:
    await ensure_company_exists(db, company_id)
    row = await get_telegram_instance(db, company_id)
    if row is None:
        return bot_out(None, company_id)

    row.status = "inactive"
    row.updated_at = utcnow()
    await db.commit()
    await db.refresh(row)
    return bot_out(row, company_id)


@router.post("/telegram/{company_id}/webhook", response_model=BotResponse)
async def telegram_webhook(
    company_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    update: dict[str, Any] = await request.json()
    event = parse_telegram_update(company_id, update)

    if event is None:
        return BotResponse(
            ok=True,
            action="ignored",
            message="Telegram update ignored",
        )

    result = await EventEngine().process(db, event)
    return BotResponse(
        ok=True,
        action=result.event_type,
        message="Event received",
        data=result.model_dump(mode="json"),
    )
