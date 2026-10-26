"""Bots de Telegram (todas las empresas): base configurable, timeouts cortos con
1 reintento, webhook que responde 200 de inmediato, sin duplicados ni updates viejos."""
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.v1.endpoints import company_bots_v1
from app.integrations.telegram import api as tg_api

TOKEN = "123456:SECRETO-de-prueba"
COMPANY = "d63cf68c-be5b-4a30-aee4-341973018db1"


def mock_client(monkeypatch, handler):
    real = httpx.AsyncClient
    seen = []

    def factory(**kwargs):
        seen.append(kwargs)
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(tg_api.httpx, "AsyncClient", factory)
    return seen


def test_base_por_defecto_y_por_variable(monkeypatch):
    monkeypatch.delenv("TELEGRAM_API_BASE", raising=False)
    monkeypatch.delenv("TELEGRAM_PROXY_KEY", raising=False)
    assert tg_api.telegram_method_url("t", "getMe") == "https://api.telegram.org/bott/getMe"
    assert tg_api.telegram_headers() == {}

    monkeypatch.setenv("TELEGRAM_API_BASE", "https://tg-proxy.example.workers.dev/")
    monkeypatch.setenv("TELEGRAM_PROXY_KEY", "clave")
    assert tg_api.telegram_method_url("t", "sendMessage") == "https://tg-proxy.example.workers.dev/bott/sendMessage"
    assert tg_api.telegram_file_url("t", "/photos/a.jpg") == "https://tg-proxy.example.workers.dev/file/bott/photos/a.jpg"
    assert tg_api.telegram_headers() == {"X-Proxy-Key": "clave"}


async def test_reintenta_una_vez_con_conexion_nueva(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_API_BASE", "https://proxy.test")
    monkeypatch.setenv("TELEGRAM_PROXY_KEY", "k1")
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("lento", request=request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    seen = mock_client(monkeypatch, handler)
    with caplog.at_level(logging.WARNING, logger="clonexa.telegram_api"):
        response = await tg_api.telegram_call(TOKEN, "sendMessage", payload={"chat_id": 1, "text": "hola"})

    assert response.json()["ok"] is True
    assert len(calls) == 2 and len(seen) == 2  # un cliente (conexion) nuevo por intento
    assert str(calls[1].url) == f"https://proxy.test/bot{TOKEN}/sendMessage"
    assert calls[1].headers["X-Proxy-Key"] == "k1"
    timeout = seen[0]["timeout"]
    assert (timeout.connect, timeout.read) == (5.0, 10.0)
    assert "ReadTimeout" in caplog.text and TOKEN not in caplog.text


async def test_tras_dos_fallas_relanza_sin_token_en_el_aviso(monkeypatch, caplog):
    monkeypatch.delenv("TELEGRAM_API_BASE", raising=False)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("sin ruta", request=request)

    mock_client(monkeypatch, handler)
    with caplog.at_level(logging.WARNING, logger="clonexa.telegram_api"), pytest.raises(httpx.ConnectError):
        await tg_api.telegram_call(TOKEN, "getMe", http_method="GET")
    assert len(calls) == 2
    assert TOKEN not in caplog.text


async def test_send_message_no_tumba_la_peticion_si_telegram_no_responde(monkeypatch, caplog):
    def handler(request):
        raise httpx.ReadTimeout("lento", request=request)

    mock_client(monkeypatch, handler)
    with caplog.at_level(logging.WARNING):
        await company_bots_v1.send_message(TOKEN, "42", "hola")  # no lanza
    assert "sendMessage no entregado" in caplog.text
    assert TOKEN not in caplog.text

    with pytest.raises(HTTPException) as exc:
        await company_bots_v1.telegram_post(TOKEN, "getMe", {})
    assert exc.value.status_code == 502 and "Telegram no responde" in str(exc.value.detail)


def test_edad_del_update_por_fecha_del_mensaje():
    now = 1_800_000_000
    assert company_bots_v1.update_age_seconds({"message": {"date": now - 30}}, now=now) == 30
    assert company_bots_v1.update_age_seconds({"edited_message": {"date": now - 700}}, now=now) == 700
    # un callback no trae fecha propia: no se puede medir
    assert company_bots_v1.update_age_seconds({"callback_query": {"message": {"date": now - 9999}}}, now=now) is None


class FakeResult:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


async def test_claim_update_nuevo_y_repetido():
    executed = []

    class Db:
        commit = AsyncMock()

        async def execute(self, statement, params):
            executed.append((str(statement), params))
            return FakeResult((1,) if len(executed) == 2 else None)

    db = Db()
    assert await company_bots_v1.claim_telegram_update(db, COMPANY, 501) is True
    delete_sql, delete_params = executed[0]
    assert "DELETE FROM company_bot_telegram_updates" in delete_sql and "company_id" in delete_sql
    assert "24 hours" in delete_sql and delete_params == {"company_id": COMPANY}
    assert executed[1][1] == {"company_id": COMPANY, "update_id": 501}
    assert "ON CONFLICT DO NOTHING" in executed[1][0]

    executed.clear()
    executed.append(("primero", {}))  # la segunda llamada a execute devuelve None
    executed.append(("segundo", {}))
    assert await company_bots_v1.claim_telegram_update(db, COMPANY, 501) is False
    # sin update_id no se puede deduplicar: se procesa
    assert await company_bots_v1.claim_telegram_update(db, COMPANY, None) is True


def webhook_setup(monkeypatch, *, flow="velvet_references", claim=True):
    row = {"bot_token_encrypted": "fernet:x", "config_json": {"flow_code": flow, "webhook_secret": "s3"}}
    monkeypatch.setattr(company_bots_v1, "ensure_company_bot_storage", AsyncMock())
    monkeypatch.setattr(company_bots_v1, "bot_config_row", AsyncMock(return_value=row))
    monkeypatch.setattr(company_bots_v1, "decrypt_token", lambda _value: TOKEN)
    claim_mock = AsyncMock(return_value=claim)
    monkeypatch.setattr(company_bots_v1, "claim_telegram_update", claim_mock)
    handler = AsyncMock(side_effect=AssertionError("no debe procesarse dentro de la peticion"))
    monkeypatch.setattr(company_bots_v1, "handle_velvet_references", handler)
    return claim_mock, handler


def request_with(update):
    return SimpleNamespace(json=AsyncMock(return_value=update))


async def test_webhook_responde_de_inmediato_y_procesa_en_segundo_plano(monkeypatch):
    claim_mock, handler = webhook_setup(monkeypatch)
    update = {"update_id": 77, "message": {"date": int(time.time()), "from": {"id": 1}, "chat": {"id": 1}, "text": "/start"}}
    tasks = BackgroundTasks()

    result = await company_bots_v1.company_telegram_webhook(
        COMPANY, request_with(update), tasks, db=SimpleNamespace(), x_telegram_bot_api_secret_token="s3"
    )

    assert result == {"ok": True, "queued": True, "flow_code": "velvet_references"}
    handler.assert_not_awaited()
    claim_mock.assert_awaited_once()
    assert claim_mock.await_args.args[1:] == (COMPANY, 77)
    assert len(tasks.tasks) == 1
    task = tasks.tasks[0]
    assert task.func is company_bots_v1.process_company_telegram_update
    assert task.args == (COMPANY, "velvet_references", TOKEN, update)


async def test_webhook_update_repetido_no_se_procesa_otra_vez(monkeypatch):
    webhook_setup(monkeypatch, claim=False)
    tasks = BackgroundTasks()
    update = {"update_id": 77, "message": {"date": int(time.time())}}
    result = await company_bots_v1.company_telegram_webhook(
        COMPANY, request_with(update), tasks, db=SimpleNamespace(), x_telegram_bot_api_secret_token="s3"
    )
    assert result == {"ok": True, "ignored": "duplicate_update"}
    assert tasks.tasks == []


async def test_webhook_mensaje_de_hace_mas_de_10_minutos_no_se_procesa_y_avisa(monkeypatch):
    claim_mock, handler = webhook_setup(monkeypatch)
    tasks = BackgroundTasks()
    update = {"update_id": 78, "message": {"date": int(time.time()) - 11 * 60, "text": "velvet:start", "chat": {"id": 555}, "from": {"id": 555}}}
    result = await company_bots_v1.company_telegram_webhook(
        COMPANY, request_with(update), tasks, db=SimpleNamespace(), x_telegram_bot_api_secret_token="s3"
    )
    assert result == {"ok": True, "ignored": "stale_update"}
    handler.assert_not_awaited()
    claim_mock.assert_awaited_once()  # un aviso por update, aunque Telegram lo repita
    assert len(tasks.tasks) == 1
    task = tasks.tasks[0]
    assert task.func is company_bots_v1.send_message
    assert task.args == (TOKEN, "555", "Este mensaje llegó tarde, vuelve a intentarlo.")


async def test_webhook_mensaje_viejo_repetido_no_avisa_dos_veces(monkeypatch):
    webhook_setup(monkeypatch, claim=False)
    tasks = BackgroundTasks()
    update = {"update_id": 78, "message": {"date": int(time.time()) - 11 * 60, "chat": {"id": 555}}}
    result = await company_bots_v1.company_telegram_webhook(
        COMPANY, request_with(update), tasks, db=SimpleNamespace(), x_telegram_bot_api_secret_token="s3"
    )
    assert result == {"ok": True, "ignored": "duplicate_update"}
    assert tasks.tasks == []


async def test_webhook_sigue_exigiendo_el_secreto(monkeypatch):
    webhook_setup(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await company_bots_v1.company_telegram_webhook(
            COMPANY, request_with({"update_id": 1}), BackgroundTasks(), db=SimpleNamespace(), x_telegram_bot_api_secret_token="otro"
        )
    assert exc.value.status_code == 403


async def test_segundo_plano_usa_su_propia_sesion_y_no_revienta(monkeypatch, caplog):
    sessions = []

    class Session:
        async def __aenter__(self):
            sessions.append(self)
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(company_bots_v1, "AsyncSessionLocal", Session)
    handler = AsyncMock(side_effect=RuntimeError("fallo"))
    monkeypatch.setattr(company_bots_v1, "handle_velvet_references", handler)

    with caplog.at_level(logging.WARNING, logger="clonexa.company_bots_v1"):
        await company_bots_v1.process_company_telegram_update(COMPANY, "velvet_references", TOKEN, {"update_id": 9})

    assert len(sessions) == 1
    assert handler.await_args.kwargs["db"] is sessions[0]
    assert "fallo en segundo plano" in caplog.text and TOKEN not in caplog.text


def test_ninguna_llamada_a_telegram_queda_fuera_de_la_base_configurable():
    from pathlib import Path

    offenders = []
    for path in Path("app").rglob("*.py"):
        if path.as_posix().endswith("integrations/telegram/api.py"):
            continue
        if "api.telegram.org" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(path.as_posix())
    assert offenders == []
