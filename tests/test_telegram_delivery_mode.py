from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import bots


def test_dedicated_webhook_detection_is_explicit_and_case_insensitive() -> None:
    assert bots._uses_dedicated_telegram_webhook({"webhook_mode": "dedicated"})
    assert bots._uses_dedicated_telegram_webhook({"webhook_mode": " DEDICATED "})
    assert not bots._uses_dedicated_telegram_webhook({"webhook_mode": "polling"})
    assert not bots._uses_dedicated_telegram_webhook({})


@pytest.mark.asyncio
async def test_polling_is_rejected_and_disabled_for_dedicated_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid4()
    row = SimpleNamespace(
        bot_token_encrypted="encrypted-token",
        status="active",
        config_json={
            "webhook_mode": "dedicated",
            "listener_enabled": True,
            "listener_running": True,
            "listener_error": "stale conflict",
        },
        last_error="stale conflict",
        updated_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock())

    monkeypatch.setattr(bots, "ensure_company_exists", AsyncMock())
    monkeypatch.setattr(bots, "get_telegram_instance", AsyncMock(return_value=row))
    monkeypatch.setattr(bots, "decrypt_token", lambda _: "telegram-token")

    with pytest.raises(HTTPException) as exc_info:
        await bots._poll_telegram_updates_for_company(db, company_id=company_id)

    assert exc_info.value.status_code == 409
    assert row.config_json["listener_enabled"] is False
    assert row.config_json["listener_running"] is False
    assert "listener_error" not in row.config_json
    assert row.last_error is None
    db.commit.assert_awaited_once()
