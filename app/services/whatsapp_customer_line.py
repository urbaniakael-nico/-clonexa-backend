"""Replies for a company's CUSTOMER WhatsApp line (linea "clientes").

SECURITY (2026-09-24): this line is published to the public, so it must
never reach internal data. By design this module imports nothing from
nomina, CRM, produccion, Workforce or the internal agent (bots.py), and
tests/test_whatsapp_agent_security.py checks that its imports (and those of
whatsapp_delivery, which it uses) stay that way. Anything a customer line
answers is built here, from customer-facing modules only.

Today the only customer-facing module is Domicilios por WhatsApp: the line
answers with the personal carta link (or the schedule when closed). Without
that module active for the company, the line stays silent.

WARNING: automating WhatsApp Web is against WhatsApp's terms and the number
can be banned. Use a dedicated number, never the business's main one.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import whatsapp_delivery


async def customer_line_reply(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    from_phone: str,
    text_value: str,
    event_type: str = "",
    push_name: str = "",
    from_jid: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> str:
    """Text to answer on the customer line; "" means stay silent."""
    if event_type == "connected":
        return ""
    if event_type == "location":
        if latitude is None or longitude is None:
            return ""
        if await whatsapp_delivery.module_settings(db, company_id) is None:
            return ""
        saved = await whatsapp_delivery.save_whatsapp_location(db, company_id, from_phone, latitude, longitude, from_jid)
        return "Recibimos tu ubicacion. Gracias!" if saved else ""
    if not str(text_value or "").strip():
        return ""
    return await whatsapp_delivery.customer_reply(
        db, company_id=company_id, from_phone=from_phone, from_jid=from_jid, push_name=push_name,
    )
