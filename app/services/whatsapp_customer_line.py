"""Replies for a company's CUSTOMER WhatsApp line (linea "clientes").

SECURITY (2026-09-24): this line is published to the public, so it must
never reach internal data. By design this module imports nothing from
nomina, CRM, produccion, Workforce or the internal agent (bots.py), and
tests/test_whatsapp_agent_security.py checks that its imports stay that
way. Anything a customer line answers is built here, from customer-facing
modules only.

Until a customer-facing module (domicilios) is active for the company, the
line stays silent.

WARNING: automating WhatsApp Web is against WhatsApp's terms and the number
can be banned. Use a dedicated number, never the business's main one.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession


async def customer_line_reply(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    from_phone: str,
    text_value: str,
    event_type: str = "",
) -> str:
    """Text to answer on the customer line; "" means stay silent."""
    return ""
