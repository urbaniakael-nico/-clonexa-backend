import uuid
from typing import Any
from uuid import UUID

from app.schemas.event import EventCreate


def parse_telegram_update(company_id: UUID, update: dict[str, Any]) -> EventCreate | None:
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    from_user = message.get("from") or {}
    telegram_user_id = str(from_user.get("id") or "")
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")

    if not telegram_user_id:
        return None

    event_type = "bot_message_received"
    payload: dict[str, Any] = {
        "text": text,
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "raw": update,
    }

    if text == "🟢 Iniciar turno" or text.lower() in {"/start_shift", "iniciar turno"}:
        event_type = "shift_started"
    elif text == "⏸ Pausa" or text.lower() in {"pausa", "/pause"}:
        event_type = "shift_paused"
    elif text == "▶️ Reanudar" or text.lower() in {"reanudar", "/resume"}:
        event_type = "shift_resumed"
    elif text == "🔴 Finalizar jornada" or text.lower() in {"finalizar", "/end_shift"}:
        event_type = "shift_ended"

    return EventCreate(
        company_id=company_id,
        employee_id=None,
        event_id=f"telegram-{telegram_user_id}-{uuid.uuid4().hex[:16]}",
        module="core",
        event_type=event_type,
        source_channel="telegram",
        source_ref=chat_id,
        payload=payload,
        metadata={"parser": "telegram.v1"},
    )
