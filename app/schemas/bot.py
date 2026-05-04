from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TelegramWebhookPayload(BaseModel):
    update_id: int | None = None
    message: dict[str, Any] | None = None
    callback_query: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class BotResponse(BaseModel):
    ok: bool
    action: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class TelegramBotConfigIn(BaseModel):
    token: str | None = None
    name: str | None = None


class TelegramBotConfigOut(BaseModel):
    configured: bool = False
    ok: bool = True
    id: UUID | None = None
    company_id: UUID | None = None
    channel: str = "telegram"
    name: str | None = None
    bot_username: str | None = None
    masked_token: str | None = None
    status: str = "not_configured"
    last_validated_at: datetime | None = None
    last_error: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)


class TelegramBotTestOut(TelegramBotConfigOut):
    telegram_response: dict[str, Any] = Field(default_factory=dict)
