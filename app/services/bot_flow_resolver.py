from __future__ import annotations

from typing import Any

from app.services.bot_flows.base import BotFlowContext, BotFlowResult
from app.services.bot_flows.velvet_references_flow import VelvetReferencesFlow


class BotFlowResolver:
    def __init__(self) -> None:
        self.flows = [
            VelvetReferencesFlow(),
        ]

    async def resolve(self, ctx: BotFlowContext):
        for flow in self.flows:
            if await flow.can_handle(ctx):
                return flow
        return None

    async def handle(self, db: Any, ctx: BotFlowContext, update_data: dict[str, Any]) -> BotFlowResult:
        flow = await self.resolve(ctx)

        if flow is None:
            return BotFlowResult(handled=False)

        return await flow.handle(db, ctx, update_data)


bot_flow_resolver = BotFlowResolver()
