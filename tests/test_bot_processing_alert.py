"""Aviso al Telegram del dueno: mas de 5 s o errores, maximo 1 cada 15 min, solo empresas con el
interruptor y sin datos de personas."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import company_bots_v1
from app.services import bot_processing_alert as alert
from app.services import nexa_whatsapp

CID = "f1e8f774-f052-49ca-880a-268805f07db0"


@pytest.fixture()
def box(monkeypatch):
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(nexa_whatsapp, "_deliver_alert", sent)
    alert.reset()
    alert.watch({CID: "VOLTAGE"})
    yield sent
    alert.reset()


async def test_only_over_five_seconds_or_errors(box):
    assert await alert.observe(CID, kind="message.text", seconds=5.0, at=0.0) is False
    box.assert_not_awaited()
    assert await alert.observe(CID, kind="message.location", seconds=5.1, at=1.0) is True
    message = box.await_args.args[0]
    assert "VOLTAGE" in message and "5.1 s" in message and "message.location" in message


async def test_at_most_one_every_15_minutes_and_the_next_one_counts_what_was_held(box):
    assert await alert.observe(CID, kind="a", seconds=9, at=0.0) is True
    assert await alert.observe(CID, kind="b", seconds=12, at=10.0) is False
    assert await alert.observe(CID, kind="c", seconds=0.1, error="DBAPIError/40P01", at=899.0) is False
    assert box.await_count == 1
    assert await alert.observe(CID, kind="d", seconds=7, at=900.0) is True
    assert box.await_count == 2
    message = box.await_args.args[0]
    assert "2 lentos" in message and "1 con error" in message and "máximo 12.0 s" in message


async def test_errors_alert_even_when_fast(box):
    assert await alert.observe(CID, kind="callback_query", seconds=0.2, error="DBAPIError/40P01", at=0.0) is True
    assert "DBAPIError/40P01" in box.await_args.args[0]


async def test_company_without_the_switch_does_not_alert(box):
    assert await alert.observe("otra-empresa", kind="a", seconds=60, error="x", at=0.0) is False
    box.assert_not_awaited()


async def test_failed_delivery_retries_soon_and_never_raises(box):
    box.return_value = False
    assert await alert.observe(CID, kind="a", seconds=9, at=0.0) is False
    assert await alert.observe(CID, kind="b", seconds=9, at=30.0) is False
    assert box.await_count == 1, "no insiste en cada mensaje"
    assert await alert.observe(CID, kind="c", seconds=9, at=61.0) is False
    assert box.await_count == 2, "pero reintenta al minuto"
    box.side_effect = RuntimeError("n8n caido")
    alert.STATE["last"] = None
    assert await alert.observe(CID, kind="d", seconds=9, at=70.0) is False


async def test_webhook_processing_reports_slow_and_failed_updates(box, monkeypatch):
    class Session:
        async def __aenter__(self):
            return SimpleNamespace(rollback=AsyncMock())

        async def __aexit__(self, *_):
            return False

    update = {"update_id": 1, "message": {"message_id": 1, "from": {"id": 5, "first_name": "Sandy"}, "chat": {"id": 5}, "text": "hola"}}
    monkeypatch.setattr(company_bots_v1, "AsyncSessionLocal", Session)
    monkeypatch.setattr(company_bots_v1, "get_telegram_instance", AsyncMock(return_value=SimpleNamespace(bot_token_encrypted="x")))
    monkeypatch.setattr(company_bots_v1, "send_failure_reply_060A", AsyncMock())
    monkeypatch.setattr(company_bots_v1, "_process_telegram_update", AsyncMock(side_effect=ValueError("datos de Sandy")))

    await company_bots_v1.process_company_telegram_update(CID, "field_operations", "T", update)
    company_bots_v1.send_failure_reply_060A.assert_awaited_once()
    message = box.await_args.args[0]
    assert "ValueError" in message
    assert "Sandy" not in message, "sin datos de personas"

    box.reset_mock()
    alert.reset()
    alert.watch({CID: "VOLTAGE"})
    clock = iter([100.0, 106.5])
    monkeypatch.setattr(company_bots_v1.time, "monotonic", lambda: next(clock, 200.0))
    monkeypatch.setattr(company_bots_v1, "_process_telegram_update", AsyncMock())
    await company_bots_v1.process_company_telegram_update(CID, "field_operations", "T", update)
    assert "6.5 s" in box.await_args.args[0]
