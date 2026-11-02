"""Bot VOLTAGE: ubicacion solo en cada marcacion (bot_punch_gps), cola por chat con
respuesta de fallo (060A), aviso de turno abierto / Cerrar turno (open_shift_alert).

- Iniciar turno, Pausa, Retomar, Finalizar (con resumen) y Solicitar material: un
  teclado con un solo boton "📍 Enviar mi ubicacion"; al llegar la ubicacion se
  registra la marcacion con ella (lat/lng, precision, perimetro), se quita el teclado
  y sigue el flujo. Sin ubicacion, nada se registra.
- Ubicacion en vivo: la primera sirve; las actualizaciones se ignoran sin tocar la base.
- Recordatorio de apagar la ubicacion solo si la compartio en vivo en ese turno.
- Apagado (cualquier otra empresa): exactamente como antes.
- Un update que falla tras los reintentos responde "No pudimos registrar tu accion".
"""
from __future__ import annotations

import importlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import bots, company_bots_v1
from app.api.v1.endpoints import open_shifts as open_shifts_api
from app.services import bot_gps_stop, bot_punch_gps, ddl_once, open_shift_alert, telegram_chat_queue

ROOT = Path(__file__).resolve().parents[1]
COMPANY = uuid.UUID("f1e8f774-f052-49ca-880a-268805f07db0")
START = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)

PROMPT_ES = "Toca el botón para enviar tu ubicación de este momento."
KEYBOARD_ES = {"keyboard": [[{"text": "📍 Enviar mi ubicación", "request_location": True}]], "one_time_keyboard": True, "resize_keyboard": True}
REMOVE = {"remove_keyboard": True}


class Store:
    """company_telegram_pending_actions en memoria (marcacion pendiente y 'compartio en vivo')."""

    def __init__(self):
        self.pending: dict[str, dict] = {}
        self.live: set[str] = set()

    async def set_pending(self, db, *, company_id, telegram_user_id, username, employee_id, chat_id, language, command, args):
        self.pending[telegram_user_id] = {"employee_id": str(employee_id), "chat_id": chat_id, "language": language, "command": command, "args": args}

    async def get_pending(self, db, *, company_id, telegram_user_id):
        return self.pending.get(telegram_user_id)

    async def clear_pending(self, db, *, company_id, telegram_user_id):
        self.pending.pop(telegram_user_id, None)

    async def mark_live_shared(self, db, *, company_id, telegram_user_id, employee_id):
        self.live.add(telegram_user_id)

    async def take_live_shared(self, db, *, company_id, telegram_user_id, since):
        if telegram_user_id in self.live:
            self.live.discard(telegram_user_id)
            return True
        return False


@pytest.fixture()
def bot_env(monkeypatch):
    sent: list[dict] = []
    state = {"status": "sin_turno"}
    store = Store()
    emp = SimpleNamespace(id=uuid.uuid4(), company_id=COMPANY, full_name="Ana Pérez", status="active", role="operario",
                          hourly_rate_regular=Decimal("0.55"), hourly_rate_extra=Decimal("0.80"))

    async def box(token, chat_id, text_value, reply_markup=None):
        sent.append({"chat_id": chat_id, "text": text_value, "reply_markup": reply_markup})

    events: list[dict] = []

    async def attendance(db, **kwargs):
        events.append(kwargs)
        cfg = kwargs["command_config"]
        state["status"] = cfg.get("status_after") or state["status"]
        return True, bots._txt(kwargs["language"], cfg.get("reply_key") or "status_checked")

    gps_events: list[dict] = []

    async def gps_event(db, **kwargs):
        gps_events.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), occurred_at=START, payload_json={
            "gps_status": "inside", "gps_status_label": "Dentro de perímetro", "matched_perimeter_name": "Virginia"})

    monkeypatch.setattr(bots, "_send_telegram_message", box)
    monkeypatch.setattr(bots, "_send_dynamic_menu", AsyncMock())
    monkeypatch.setattr(bots, "_answer_callback_query", AsyncMock())
    monkeypatch.setattr(bots, "_send_telegram_chat_action", AsyncMock())
    monkeypatch.setattr(bots, "_send_materials_webapp_button", AsyncMock())
    monkeypatch.setattr(bots, "_get_user_language", AsyncMock(return_value="es"))
    monkeypatch.setattr(bots, "_user_language_preference_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(bots, "_find_employee_by_telegram", AsyncMock(return_value=emp))
    monkeypatch.setattr(bots, "ensure_company_exists", AsyncMock(return_value=SimpleNamespace(id=COMPANY, name="VOLTAGE")))
    monkeypatch.setattr(bots, "_enabled_module_codes", AsyncMock(return_value={"workforce", "gps", "crm", "materials", "inventory"}))
    monkeypatch.setattr(bots, "_employee_can_request_material", lambda e: True)
    monkeypatch.setattr(bots, "_get_current_attendance_status",
                        AsyncMock(side_effect=lambda *a, **k: SimpleNamespace(status=state["status"], check_in_at=START, check_out_at=None)))
    monkeypatch.setattr(bots, "_create_bot_attendance_event", attendance)
    monkeypatch.setattr(bots, "_create_gps_location_event", gps_event)
    monkeypatch.setattr(bots, "_set_pending_end_shift_summary", AsyncMock())
    monkeypatch.setattr(bots, "_get_pending_end_shift_summary", AsyncMock(return_value=None))
    monkeypatch.setattr(bots, "_get_pending_material_request", AsyncMock(return_value=None))
    monkeypatch.setattr(bots, "_set_pending_gps_checkin", AsyncMock())
    monkeypatch.setattr(bots, "_get_pending_gps_checkin", AsyncMock(return_value=None))
    for name in ("set_pending", "get_pending", "clear_pending", "mark_live_shared", "take_live_shared"):
        monkeypatch.setattr(bot_punch_gps, name, getattr(store, name))
    tokens = [bots.PUNCH_GPS_060.set(True), bots.GPS_STOP_059C.set(False)]
    yield SimpleNamespace(sent=sent, state=state, store=store, emp=emp, events=events, gps_events=gps_events)
    bots.GPS_STOP_059C.reset(tokens[1])
    bots.PUNCH_GPS_060.reset(tokens[0])


DB = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), flush=AsyncMock())
BOT = SimpleNamespace(company_id=COMPANY, id=uuid.uuid4(), bot_username="voltage_bot")


def tap(command: str, update_id: int = 1, language_code: str = "es"):
    return {"update_id": update_id, "callback_query": {"id": f"cb{update_id}", "data": f"clx:cmd:{command}",
                                                      "from": {"id": 7, "language_code": language_code},
                                                      "message": {"message_id": 50, "chat": {"id": 7}}}}


def location(update_id: int = 2, *, live: bool = False, accuracy: float | None = 12.5):
    loc = {"latitude": 38.9072, "longitude": -77.0369}
    if accuracy is not None:
        loc["horizontal_accuracy"] = accuracy
    if live:
        loc["live_period"] = 28800
    return {"update_id": update_id, "message": {"message_id": 60 + update_id, "date": int(time.time()), "from": {"id": 7},
                                                "chat": {"id": 7}, "location": loc}}


def live_edit(update_id: int = 3):
    return {"update_id": update_id, "edited_message": {"message_id": 61, "date": int(time.time()) - 60, "edit_date": int(time.time()),
                                                       "from": {"id": 7}, "chat": {"id": 7},
                                                       "location": {"latitude": 38.9, "longitude": -77.0, "live_period": 28800}}}


async def handle(update):
    return await bots._process_telegram_update_052C(DB, bot=BOT, token="T", update=update, send_replies=True)


# ------------------------------------------------------------ botón de ubicación por marcación
@pytest.mark.asyncio
@pytest.mark.parametrize("command,status", [("entrada", "sin_turno"), ("pausa", "working"), ("reanudar", "on_break"),
                                            ("salida", "working"), ("material", "working")])
async def test_each_punch_asks_for_the_location_of_this_moment(bot_env, command, status):
    bot_env.state["status"] = status
    item = await handle(tap(command))
    assert item.action == "gps_punch_requested"
    assert bot_env.sent[-1] == {"chat_id": "7", "text": PROMPT_ES, "reply_markup": KEYBOARD_ES}
    assert bot_env.store.pending["7"]["command"] == f"/{command}"
    assert bot_env.events == [] and bot_env.gps_events == [], "sin ubicación no se registra la marcación"
    assert "tiempo real" not in PROMPT_ES and "en vivo" not in PROMPT_ES


@pytest.mark.asyncio
async def test_start_shift_registered_with_location_and_keyboard_removed(bot_env):
    await handle(tap("entrada"))
    item = await handle(location())
    assert item.action == "check_in" and item.ok
    assert bot_env.sent[-1] == {"chat_id": "7", "text": "✅ Ubicación recibida.\nInicio de turno registrado.", "reply_markup": REMOVE}
    punch = bot_env.events[-1]["punch_location"]
    assert punch["latitude"] == 38.9072 and punch["longitude"] == -77.0369 and punch["horizontal_accuracy"] == 12.5
    assert punch["gps_status"] == "inside" and punch["matched_perimeter_name"] == "Virginia" and punch["located_at"] == START.isoformat()
    assert punch["via_live_location"] is False
    assert bot_env.gps_events[-1]["source_ref_suffix"] == "gps_punch:check_in"
    assert "7" not in bot_env.store.pending
    bots._send_dynamic_menu.assert_awaited()


@pytest.mark.asyncio
async def test_pause_and_resume_with_location(bot_env):
    bot_env.state["status"] = "working"
    await handle(tap("pausa", 1))
    item = await handle(location(2, accuracy=None))
    assert item.action == "break_start"
    assert bot_env.sent[-1]["text"].startswith("☕ Pausa registrada.") and bot_env.sent[-1]["reply_markup"] == REMOVE
    assert bot_env.events[-1]["punch_location"]["horizontal_accuracy"] is None, "la precisión solo si viene"
    await handle(tap("reanudar", 3))
    item = await handle(location(4))
    assert item.action == "break_end" and bot_env.state["status"] == "working"


@pytest.mark.asyncio
async def test_end_shift_location_then_daily_summary(bot_env, monkeypatch):
    bot_env.state["status"] = "working"
    await handle(tap("salida"))
    item = await handle(location())
    assert item.action == "end_shift_summary_requested"
    assert bot_env.sent[-1] == {"chat_id": "7", "text": bots._txt("es", "end_shift_summary_prompt"), "reply_markup": REMOVE}
    assert bot_env.events == [], "la salida se registra con el resumen"
    punch = bots._set_pending_end_shift_summary.await_args.kwargs["punch_location"]
    assert punch["gps_status"] == "inside"

    # El resumen: la salida lleva la ubicación de la marcación.
    pending = {"employee_id": str(bot_env.emp.id), "payload_json": json.dumps({"punch_location": punch})}
    monkeypatch.setattr(bots, "_get_pending_end_shift_summary", AsyncMock(return_value=pending))
    monkeypatch.setattr(bots, "_clear_pending_end_shift_summary", AsyncMock())
    db = SimpleNamespace(commit=AsyncMock(), get=AsyncMock(return_value=bot_env.emp))
    message = {"message_id": 70, "from": {"id": 7}, "chat": {"id": 7}, "text": "Instalé 3 equipos"}
    item = await bots._process_end_shift_summary_text(db, bot=BOT, token="T", update={"update_id": 9, "message": message}, message=message,
                                                       telegram_user_id="7", username=None, chat_id="7", text_value="Instalé 3 equipos",
                                                       language="es", send_replies=True)
    assert item.action == "check_out"
    assert bot_env.events[-1]["args"] == "Instalé 3 equipos" and bot_env.events[-1]["punch_location"] == punch


@pytest.mark.asyncio
async def test_material_request_with_location(bot_env):
    bot_env.state["status"] = "working"
    await handle(tap("material"))
    item = await handle(location())
    assert item.action == "materials_webapp_button"
    assert bot_env.sent[-1] == {"chat_id": "7", "text": "📍 Ubicación registrada.", "reply_markup": REMOVE}
    bots._send_materials_webapp_button.assert_awaited()
    assert bot_env.gps_events[-1]["source_ref_suffix"] == "gps_punch:material_request"


@pytest.mark.asyncio
async def test_english_worker_sees_english(bot_env, monkeypatch):
    monkeypatch.setattr(bots, "_get_user_language", AsyncMock(return_value="en"))
    await handle(tap("entrada", language_code="en"))
    assert bot_env.sent[-1]["text"] == "Tap the button to send your current location."
    assert bot_env.sent[-1]["reply_markup"]["keyboard"][0][0] == {"text": "📍 Send my location", "request_location": True}
    await handle(location())
    assert bot_env.sent[-1]["text"] == "✅ Location received.\nShift started."


# ------------------------------------------------------------ ubicación en vivo
@pytest.mark.asyncio
async def test_first_live_location_serves_the_pending_punch_and_marks_it(bot_env):
    await handle(tap("entrada"))
    item = await handle(location(live=True))
    assert item.action == "check_in"
    assert bot_env.events[-1]["punch_location"]["via_live_location"] is True
    assert "7" in bot_env.store.live


@pytest.mark.asyncio
async def test_live_updates_are_ignored_without_reading_anything(bot_env):
    bot_env.state["status"] = "working"
    for n in range(20):
        item = await handle(live_edit(100 + n))
        assert item.action == "gps_live_update_ignored"
    bots._get_user_language.assert_not_awaited()
    bots._find_employee_by_telegram.assert_not_awaited()
    assert bot_env.sent == [] and bot_env.gps_events == []


@pytest.mark.asyncio
async def test_live_location_without_pending_is_silent_and_not_saved(bot_env):
    bot_env.state["status"] = "working"
    item = await handle(location(live=True))
    assert item.action == "gps_live_ignored_no_punch"
    assert bot_env.sent == [] and bot_env.gps_events == [] and bot_env.events == []
    assert "7" in bot_env.store.live, "para recordarle apagarla al finalizar"


@pytest.mark.asyncio
async def test_current_location_without_pending_points_to_the_menu(bot_env):
    item = await handle(location())
    assert item.action == "gps_no_pending"
    assert bot_env.sent[-1]["text"] == "📍 Ubicación recibida. Para marcar, toca primero una opción del menú."
    assert bot_env.gps_events == []


@pytest.mark.asyncio
async def test_location_for_an_invalid_transition_is_not_registered(bot_env):
    bot_env.state["status"] = "working"
    await handle(tap("pausa"))
    bot_env.state["status"] = "on_break"  # ya pausó desde otro lado
    item = await handle(location())
    assert item.action == "turn_validation_failed" and bot_env.events == []
    assert bot_env.sent[-1]["reply_markup"] == REMOVE and "7" not in bot_env.store.pending


@pytest.mark.asyncio
async def test_tracking_command_and_button_are_gone(bot_env):
    bot_env.state["status"] = "working"
    item = await handle(tap("ubicacion"))
    assert item.action == "unknown"
    menu = bots._menu_keyboard("es", {"workforce", "gps"}, "working")
    assert "clx:cmd:ubicacion" not in json.dumps(menu)
    bots.PUNCH_GPS_060.set(False)
    assert "clx:cmd:ubicacion" in json.dumps(bots._menu_keyboard("es", {"workforce", "gps"}, "working")), "apagado: igual que antes"


# ------------------------------------------------------------ recordatorio de apagar la ubicación
@pytest.mark.asyncio
async def test_turn_off_reminder_only_if_live_was_shared_this_shift(bot_env, monkeypatch):
    bots.GPS_STOP_059C.set(True)
    claims = []

    async def claim(db, company_id, telegram_user_id, employee_id, marker, action=bot_gps_stop.REMINDER_ACTION):
        claims.append(marker)
        return True

    monkeypatch.setattr(bot_gps_stop, "claim_reminder", claim)
    await bots._send_checkout_message_059C("T", "7", "Feliz descanso", "es", db=DB, employee=bot_env.emp, telegram_user_id="7")
    assert bot_env.sent[-1] == {"chat_id": "7", "text": "Feliz descanso", "reply_markup": None}, "no compartió en vivo: sin recordatorio"
    assert claims == []
    bot_env.store.live.add("7")
    await bots._send_checkout_message_059C("T", "7", "Feliz descanso", "es", db=DB, employee=bot_env.emp, telegram_user_id="7")
    assert "Recuerda apagar tu ubicación en vivo" in bot_env.sent[-1]["text"]
    assert bot_env.sent[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == bot_gps_stop.STOP_CALLBACK


# ------------------------------------------------------------ apagado: como antes
@pytest.mark.asyncio
async def test_switch_off_keeps_the_old_flow(bot_env):
    bots.PUNCH_GPS_060.set(False)
    item = await handle(tap("entrada"))
    assert item.action == "gps_required_for_check_in"
    assert bot_env.sent[-1]["text"] == bots._txt("es", "gps_required_for_start") and bot_env.sent[-1]["reply_markup"] == REMOVE
    bots._set_pending_gps_checkin.assert_awaited()
    assert bot_env.store.pending == {}
    bot_env.state["status"] = "working"
    item = await handle(tap("pausa", 2))
    assert item.action == "break_start", "Pausa sin pedir ubicación"
    assert bot_env.events[-1].get("punch_location") is None


# ------------------------------------------------------------ webhook: descarte antes de la base
def test_early_drop_needs_switch_cache_and_secret():
    cid = str(uuid.uuid4())
    edit = live_edit()
    assert bot_punch_gps.drop_early(cid, edit, "s") is False, "sin haber visto el interruptor: no se descarta"
    bot_punch_gps.remember(cid, True, "s")
    assert bot_punch_gps.drop_early(cid, edit, "s") is True
    assert bot_punch_gps.drop_early(cid, edit, "otro") is False, "secreto incorrecto: sigue al 403 de siempre"
    assert bot_punch_gps.drop_early(cid, location(), "s") is False, "una ubicación nueva sí se procesa"
    assert bot_punch_gps.drop_early(cid, tap("pausa"), "s") is False
    other = str(uuid.uuid4())
    bot_punch_gps.remember(other, False, "s")
    assert bot_punch_gps.drop_early(other, edit, "s") is False, "otra empresa: como siempre"
    bot_punch_gps._CACHE[cid] = (True, "s", time.monotonic() - 1)
    assert bot_punch_gps.drop_early(cid, edit, "s") is False, "cache vencida"


# ------------------------------------------------------------ cola por chat: fallos y reintentos
class FakeSession:
    async def __aenter__(self):
        return SimpleNamespace(rollback=AsyncMock())

    async def __aexit__(self, *exc):
        return False


class Deadlock(Exception):
    sqlstate = "40P01"

    def __str__(self):
        return "deadlock detected"


@pytest.fixture()
def queue_env(monkeypatch):
    out = []

    async def send_message(token, chat_id, text_value, reply_markup=None):
        out.append((chat_id, text_value))

    monkeypatch.setattr(company_bots_v1, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(company_bots_v1, "get_telegram_instance", AsyncMock(return_value=SimpleNamespace(bot_token_encrypted="x")))
    monkeypatch.setattr(company_bots_v1, "send_message", send_message)
    monkeypatch.setattr(company_bots_v1, "telegram_post", AsyncMock())
    monkeypatch.setattr(telegram_chat_queue, "RETRY_DELAY_SECONDS", 0)
    return out


@pytest.mark.asyncio
async def test_failed_action_never_goes_silent_and_logs_the_real_error(queue_env, monkeypatch, caplog):
    async def boom(db, **kwargs):
        raise RuntimeError("column x does not exist bot123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAA")

    monkeypatch.setattr(company_bots_v1, "_process_telegram_update", boom)
    with caplog.at_level(logging.WARNING):
        await company_bots_v1.process_company_telegram_update(str(COMPANY), "field_operations", "T", tap("pausa", 77))
    assert queue_env == [("7", "⚠️ No pudimos registrar tu acción, intenta de nuevo.")]
    log = caplog.text
    assert "77" in log and "RuntimeError" in log and "tipo=callback_query" in log and "usuario_telegram=7" in log
    assert "column x does not exist" in log and "AAAAAAAA" not in log, "el error real, sin secretos"

    queue_env.clear()
    await company_bots_v1.process_company_telegram_update(str(COMPANY), "field_operations", "T", tap("pausa", 78, language_code="en"))
    assert queue_env == [("7", "⚠️ We couldn't register your action, please try again.")]
    queue_env.clear()
    await company_bots_v1.process_company_telegram_update(str(COMPANY), "field_operations", "T", live_edit())
    assert queue_env == [], "una actualización en vivo no es una acción: sin mensaje"


@pytest.mark.asyncio
async def test_concurrency_error_is_retried_then_answered(queue_env, monkeypatch, caplog):
    calls = []

    async def flaky(db, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise Deadlock()

    monkeypatch.setattr(company_bots_v1, "_process_telegram_update", flaky)
    with caplog.at_level(logging.WARNING):
        await company_bots_v1.process_company_telegram_update(str(COMPANY), "field_operations", "T", tap("salida", 80))
    assert len(calls) == 3 and queue_env == [], "2 reintentos y salió bien"
    assert "40P01" in caplog.text and "reintento 2" in caplog.text

    calls.clear()

    async def always(db, **kwargs):
        calls.append(1)
        raise Deadlock()

    monkeypatch.setattr(company_bots_v1, "_process_telegram_update", always)
    await company_bots_v1.process_company_telegram_update(str(COMPANY), "field_operations", "T", tap("salida", 81))
    assert len(calls) == 3 and queue_env == [("7", "⚠️ No pudimos registrar tu acción, intenta de nuevo.")]


def test_update_kinds_and_actions():
    assert telegram_chat_queue.update_kind(live_edit()) == "edited_message.location"
    assert telegram_chat_queue.update_kind(location()) == "message.location"
    assert telegram_chat_queue.update_kind(tap("pausa")) == "callback_query"
    assert telegram_chat_queue.is_action(location()) and not telegram_chat_queue.is_action(live_edit())
    assert telegram_chat_queue.chat_id_of(tap("pausa")) == "7" and telegram_chat_queue.chat_id_of(live_edit()) == "7"
    assert telegram_chat_queue.is_concurrency_error(Deadlock()) and not telegram_chat_queue.is_concurrency_error(ValueError("x"))


# ------------------------------------------------------------ ddl_once
def test_ddl_checks_parse_and_unknown_statements_fall_back():
    checks = ddl_once.checks_from_sql([
        'CREATE EXTENSION IF NOT EXISTS "pgcrypto";',
        "CREATE TABLE IF NOT EXISTS gps_tracking_sessions (\n id uuid)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_a ON t(a) WHERE x",
        "ALTER TABLE company_bot_instances ADD COLUMN IF NOT EXISTS last_error text NULL",
        "DROP INDEX IF EXISTS uq_material_requests_order;",
    ])
    assert checks == [("ext", "pgcrypto"), ("rel", "gps_tracking_sessions"), ("rel", "ux_a"),
                      ("col", "company_bot_instances", "last_error"), ("absent", "uq_material_requests_order")]
    assert ddl_once.checks_from_sql(["UPDATE t SET a = 1"]) is None, "lo que no se sabe verificar corre como siempre"


@pytest.mark.asyncio
async def test_every_bot_storage_function_is_guarded_and_verifiable():
    for fn in (bots.ensure_bot_storage, bots._ensure_gps_perimeter_storage, bots._ensure_material_requests_storage,
               company_bots_v1.ensure_company_bot_storage):
        assert getattr(fn, "ddl_key", None), fn
        checks = await ddl_once._record(fn.ddl_fn)
        assert checks, f"{fn.ddl_key}: todo su DDL se puede verificar sin bloqueos"


@pytest.mark.asyncio
async def test_guard_runs_the_old_ddl_when_it_cannot_verify():
    ddl_once.reset()
    ran = []

    @ddl_once.ddl_once("prueba_fallback")
    async def storage(db):
        if not isinstance(db, ddl_once._Recorder):  # la grabación del SQL no cuenta
            ran.append(1)

    await storage(SimpleNamespace())  # sesión falsa: no se puede verificar
    await storage(SimpleNamespace())
    assert ran == [1, 1] and "prueba_fallback" not in ddl_once._READY
    ddl_once.reset()


# ------------------------------------------------------------ aviso de turno abierto: reglas, rutas, migración
def test_open_shift_texts_and_labels():
    assert open_shift_alert.hours_label(13.0) == "13" and open_shift_alert.hours_label(12.5) == "12:30"
    label = open_shift_alert.local_label(START, "America/New_York")
    assert label.startswith("02/11 07:00") and "EST" in label
    boss = open_shift_alert.tr("es", "boss", hours="13", name="Ana", place="Virginia", start=label)
    assert "👤 Ana" in boss and "📍 Virginia" in boss and "Cerrar turno" in boss
    assert "Close shift" in open_shift_alert.tr("en", "boss", hours="13", name="Ana", place="Virginia", start=label)
    with pytest.raises(open_shift_alert.Invalid):
        open_shift_alert.clean_note("ok")
    assert open_shift_alert.clean_note("  salió   a las 6 ") == "salió a las 6"


def test_open_shift_routes_require_session_and_are_registered():
    routes = list(open_shifts_api.router.routes)
    assert len(routes) == 3
    for r in routes:
        assert open_shifts_api.actor in [d.call for d in r.dependant.dependencies], f"{r.path} sin sesión"
    from app.api.v1 import router as v1

    paths = {getattr(r, "path", "") for r in v1.api_router.routes}
    for p in ("", "/employees/{employee_id}/close", "/closes"):
        assert f"/open-shifts/companies/{{company_id}}{p}" in paths
    assert {"supervisor", "gerencia", "company_admin"} <= open_shift_alert.CLOSE_ROLES
    assert not {"operario", "mesero", "cocina", "caja"} & open_shift_alert.CLOSE_ROLES


def test_migration_is_additive_small_and_short_revision():
    module = importlib.import_module("migrations.versions.024y_open_shift_alert")
    assert len(module.revision) <= 32 and module.down_revision == "024x_work_locations"
    src = (ROOT / "migrations" / "versions" / "024y_open_shift_alert.py").read_text(encoding="utf-8")
    upgrade = src.split("def upgrade")[1].split("def downgrade")[0]
    for verb in ("DROP ", "DELETE FROM", "UPDATE ", "TRUNCATE", "ALTER COLUMN", "BYTEA"):
        assert verb not in upgrade.upper(), verb


def test_switch_registry_entries():
    reg = json.loads((ROOT / "app" / "services" / "switch_registry.json").read_text(encoding="utf-8"))
    punch = next(s for s in reg["switches"] if s["key"] == "bot_punch_gps")
    assert punch["module"] == "workforce" and punch["delicate"] is True and "gps" in punch["requires_modules"]
    alert = next(s for s in reg["switches"] if s["key"] == "open_shift_alert")
    assert alert["module"] == "workforce" and alert["delicate"] is True
    assert bot_punch_gps.switch_on({"bot_punch_gps": True}) and not bot_punch_gps.switch_on({}) and not bot_punch_gps.switch_on({"bot_punch_gps": "true"})


def test_loop_is_started_at_boot():
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "from app.services.bot_punch_gps import start_loop" in src
