from typing import Any

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
