from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BotFlowContext:
    company_id: str
    employee_id: str
    employee_name: str
    telegram_user_id: str
    telegram_username: str | None
    language: str
    status_key: str
    enabled_modules: set[str]


@dataclass
class BotFlowResult:
    handled: bool
    ok: bool = True
    action: str = ""
    message: str = ""
    reply_text: str | None = None
    reply_markup: dict[str, Any] | None = None
    event_created: bool = False


class BaseBotFlow:
    code = "base"

    async def can_handle(self, ctx: BotFlowContext) -> bool:
        return False

    async def handle(self, db: Any, ctx: BotFlowContext, update_data: dict[str, Any]) -> BotFlowResult:
        return BotFlowResult(handled=False)
