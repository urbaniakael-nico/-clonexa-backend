from types import SimpleNamespace

import pytest

from app.services import transactional_email


@pytest.mark.asyncio
async def test_transactional_email_requires_server_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        transactional_email,
        "get_settings",
        lambda: SimpleNamespace(RESEND_API_KEY="", MAIL_DEFAULT_FROM="", MAIL_DEFAULT_FROM_NAME="CLONEXA"),
    )

    with pytest.raises(transactional_email.TransactionalEmailConfigurationError):
        await transactional_email.send_transactional_email(
            recipient="cliente@example.com",
            subject="Factura",
            html="<p>Factura</p>",
            text="Factura",
        )


@pytest.mark.asyncio
async def test_transactional_email_sends_attachment_and_reply_to(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "email_123"}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, json, headers):
            captured.update({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr(
        transactional_email,
        "get_settings",
        lambda: SimpleNamespace(
            RESEND_API_KEY="secret-key",
            MAIL_DEFAULT_FROM="cobros@example.com",
            MAIL_DEFAULT_FROM_NAME="CLONEXA",
        ),
    )
    monkeypatch.setattr(transactional_email.httpx, "AsyncClient", FakeClient)

    result = await transactional_email.send_transactional_email(
        recipient="cliente@example.com",
        subject="Factura FAC-1",
        html="<p>Adjunta</p>",
        text="Adjunta",
        sender_name="Tesoreria Demo",
        reply_to="tesoreria@example.com",
        cc="contabilidad@example.com",
        attachment_name="factura.pdf",
        attachment_content=b"pdf-bytes",
        idempotency_key="invoice-1",
    )

    assert result == {"provider": "resend", "message_id": "email_123", "status": "sent"}
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["json"]["from"] == "Tesoreria Demo <cobros@example.com>"
    assert captured["json"]["reply_to"] == ["tesoreria@example.com"]
    assert captured["json"]["cc"] == ["contabilidad@example.com"]
    assert captured["json"]["attachments"][0]["filename"] == "factura.pdf"
    assert captured["headers"]["Idempotency-Key"] == "invoice-1"
