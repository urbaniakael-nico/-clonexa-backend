from __future__ import annotations

import base64
from typing import Any

import httpx

from app.core.config import get_settings


class TransactionalEmailConfigurationError(RuntimeError):
    pass


class TransactionalEmailDeliveryError(RuntimeError):
    pass


async def send_transactional_email(
    *,
    recipient: str,
    subject: str,
    html: str,
    text: str,
    sender_name: str = "",
    reply_to: str = "",
    cc: str = "",
    attachment_name: str = "",
    attachment_content: bytes = b"",
    idempotency_key: str = "",
) -> dict[str, Any]:
    settings = get_settings()
    api_key = settings.RESEND_API_KEY.strip()
    sender_email = settings.MAIL_DEFAULT_FROM.strip()
    visible_name = sender_name.strip() or settings.MAIL_DEFAULT_FROM_NAME.strip() or "CLONEXA"
    if not api_key or not sender_email:
        raise TransactionalEmailConfigurationError(
            "Configura RESEND_API_KEY y MAIL_DEFAULT_FROM en Railway para habilitar el correo."
        )

    payload: dict[str, Any] = {
        "from": f"{visible_name} <{sender_email}>",
        "to": [recipient],
        "subject": subject,
        "html": html,
        "text": text,
    }
    if reply_to:
        payload["reply_to"] = [reply_to]
    if cc:
        payload["cc"] = [cc]
    if attachment_name and attachment_content:
        payload["attachments"] = [
            {
                "filename": attachment_name,
                "content": base64.b64encode(attachment_content).decode("ascii"),
            }
        ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:256]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise TransactionalEmailDeliveryError("No fue posible conectar con el proveedor de correo.") from exc

    if response.status_code < 200 or response.status_code >= 300:
        raise TransactionalEmailDeliveryError(
            f"El proveedor de correo rechazo el envio (HTTP {response.status_code})."
        )
    data = response.json()
    return {
        "provider": "resend",
        "message_id": str(data.get("id") or ""),
        "status": "sent",
    }
