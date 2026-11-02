"""Bot de Telegram · interruptor bot_gps_stop (VOLTAGE).

- Ubicación que llega sin turno abierto (en vivo o actual): se descarta, no se guarda.
- "Turno finalizado" con el recordatorio y el botón "📍 Apagar ubicación", una sola
  vez por turno (marcado en la base); el botón da los pasos y el menú, y si se
  toca otra vez solo los pasos. Las ubicaciones después del cierre: en silencio.
- Inicio de turno: recomienda 8 horas. Dinero "$1.10 USD"; sin "Descuento del
  corte" cuando es 0. Español / inglés.
- Webhook: con el interruptor recibe edited_message (ubicación en vivo), mide la
  edad por edit_date y se re-registra solo una vez con la misma URL y secreto.
- Apagado (cualquier otra empresa): exactamente como antes.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks

from app.api.v1.endpoints import bots, company_bots_v1
from app.services import bot_gps_stop
from app.services import company_locale as cl

COMPANY = uuid.UUID("f1e8f774-f052-49ca-880a-268805f07db0")
CLOSED_AT = datetime(2026, 11, 1, 22, 0, tzinfo=timezone.utc)


@pytest.fixture()
def switch():
    def set_on(value: bool):
        bots.GPS_STOP_059C.set(value)

    yield set_on
    bots.GPS_STOP_059C.set(False)  # apagado por defecto para las demás pruebas


@pytest.fixture()
def outbox(monkeypatch):
    sent: list[dict] = []

    async def box(token, chat_id, text_value, reply_markup=None):
        sent.append({"chat_id": chat_id, "text": text_value, "reply_markup": reply_markup})

    monkeypatch.setattr(bots, "_send_telegram_message", box)
    monkeypatch.setattr(bots, "_send_dynamic_menu", AsyncMock())
    monkeypatch.setattr(bots, "_answer_callback_query", AsyncMock())
    return sent


def employee():
    return SimpleNamespace(id=uuid.uuid4(), company_id=COMPANY, full_name="Ana Pérez", status="active",
                           hourly_rate_regular=Decimal("0.55"), hourly_rate_extra=Decimal("0.80"), deduction_1=0, deduction_2=0)


def location_setup(monkeypatch, status: str, *, language: str = "es"):
    emp = employee()
    monkeypatch.setattr(bots, "_get_user_language", AsyncMock(return_value=language))
    monkeypatch.setattr(bots, "_find_employee_by_telegram", AsyncMock(return_value=emp))
    monkeypatch.setattr(bots, "ensure_company_exists", AsyncMock(return_value=SimpleNamespace(id=COMPANY, name="VOLTAGE")))
    monkeypatch.setattr(bots, "_enabled_module_codes", AsyncMock(return_value={"workforce", "gps", "crm"}))
    monkeypatch.setattr(bots, "_get_pending_gps_checkin", AsyncMock(return_value=None))
    current = SimpleNamespace(status=status, check_in_at=None, check_out_at=CLOSED_AT if status == "checked_out" else None)
    monkeypatch.setattr(bots, "_get_current_attendance_status", AsyncMock(return_value=current))
    saved = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), occurred_at=CLOSED_AT))
    monkeypatch.setattr(bots, "_create_gps_location_event", saved)
    monkeypatch.setattr(bots, "_touch_gps_tracking_session", AsyncMock())
    return emp, saved


def live_update(edit=True):
    msg = {"message_id": 10, "date": int(time.time()) - 3 * 3600, "from": {"id": 7}, "chat": {"id": 7},
           "location": {"latitude": 38.9, "longitude": -77.0, "live_period": 28800}}
    if edit:
        msg["edit_date"] = int(time.time())
        return {"update_id": 1, "edited_message": msg}
    return {"update_id": 1, "message": msg}


def current_location_update():
    return {"update_id": 2, "message": {"message_id": 11, "date": int(time.time()), "from": {"id": 7}, "chat": {"id": 7},
                                        "location": {"latitude": 38.9, "longitude": -77.0}}}


async def run_location(update, db=None):
    message = update.get("message") or update.get("edited_message")
    return await bots._process_telegram_location(db or SimpleNamespace(commit=AsyncMock()), bot=SimpleNamespace(company_id=COMPANY), token="T",
                                                 update=update, message=message, telegram_user_id="7", username=None, chat_id="7", send_replies=True)


# ------------------------------------------------------------ marcas en la base (059D)
class Marks:
    """Como company_telegram_pending_actions: una marca por (acción, turno)."""

    def __init__(self):
        self.rows: dict[tuple, str] = {}
        self.calls: list[tuple] = []

    async def claim(self, db, company_id, telegram_user_id, employee_id, marker, action=bot_gps_stop.REMINDER_ACTION):
        self.calls.append((action, marker))
        key = (str(company_id), str(telegram_user_id), action)
        if self.rows.get(key) == marker:
            return False
        self.rows[key] = marker
        return True


@pytest.fixture()
def marks(monkeypatch):
    m = Marks()
    monkeypatch.setattr(bot_gps_stop, "claim_reminder", m.claim)
    return m


REMINDER = "📍 Recuerda apagar tu ubicación en vivo. Ya no la estamos registrando."
BUTTON = {"inline_keyboard": [[{"text": "📍 Apagar ubicación", "callback_data": "clx:gps:stop"}]]}


# ------------------------------------------------------------ 1) y 3) ubicaciones
@pytest.mark.asyncio
async def test_twenty_live_locations_after_shift_are_silent_and_not_saved(monkeypatch, switch, outbox, marks):
    switch(True)
    _emp, saved = location_setup(monkeypatch, "checked_out")
    for _ in range(20):
        item = await run_location(live_update())
        assert item.action == "gps_live_ignored_closed_shift"
    saved.assert_not_awaited()  # no se guarda: no sale en CRM ni en GPS
    assert outbox == [], "sin recordatorio aparte: en silencio"
    assert marks.calls == []
    bots._send_dynamic_menu.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_location_without_shift_is_not_saved(monkeypatch, switch, outbox):
    switch(True)
    _emp, saved = location_setup(monkeypatch, "checked_out")
    item = await run_location(current_location_update())
    assert item.action == "gps_no_pending" and item.ok is False
    saved.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_location_during_shift_is_still_saved(monkeypatch, switch, outbox):
    switch(True)
    _emp, saved = location_setup(monkeypatch, "working")
    item = await run_location(live_update())
    assert item.action == "gps_location" and item.event_created is True
    saved.assert_awaited_once()
    assert outbox == []  # en vivo durante el turno: en silencio, como siempre


@pytest.mark.asyncio
async def test_switch_off_live_location_after_shift_is_as_before(monkeypatch, switch, outbox, marks):
    switch(False)
    _emp, saved = location_setup(monkeypatch, "checked_out")
    item = await run_location(live_update())
    assert item.action == "gps_live_ignored_closed_shift"
    saved.assert_not_awaited()
    assert outbox == [] and marks.calls == []


# ------------------------------------------------------------ 2) y 4) cierre y botón
def checkout_setup(monkeypatch, close_at=CLOSED_AT):
    emp = employee()
    monkeypatch.setattr(bots, "_get_current_attendance_status",
                        AsyncMock(return_value=SimpleNamespace(status="checked_out", check_in_at=None, check_out_at=close_at)))
    return emp


@pytest.mark.asyncio
async def test_checkout_message_reminds_once_per_shift(monkeypatch, switch, outbox, marks):
    switch(True)
    emp = checkout_setup(monkeypatch)
    db = SimpleNamespace(commit=AsyncMock())
    await bots._send_checkout_message_059C("T", "7", "🏁 Turno finalizado.", "es", db=db, employee=emp, telegram_user_id="7")
    await bots._send_checkout_message_059C("T", "7", "🏁 Turno finalizado.", "es", db=db, employee=emp, telegram_user_id="7")
    assert outbox[0]["text"] == f"🏁 Turno finalizado.\n\n{REMINDER}" and outbox[0]["reply_markup"] == BUTTON
    assert outbox[1] == {"chat_id": "7", "text": "🏁 Turno finalizado.", "reply_markup": None}, "mismo turno: nunca se repite"
    assert marks.rows == {(str(COMPANY), "7", "gps_stop_reminded"): CLOSED_AT.isoformat()}

    checkout_setup(monkeypatch, datetime(2026, 11, 2, 22, 0, tzinfo=timezone.utc))  # turno nuevo: otra vez, una sola
    await bots._send_checkout_message_059C("T", "7", "🏁 Shift ended.", "en", db=db, employee=emp, telegram_user_id="7")
    assert outbox[2]["text"].endswith("📍 Remember to turn off your live location. We are no longer recording it.")
    assert outbox[2]["reply_markup"]["inline_keyboard"][0][0]["text"] == "📍 Turn off location"


@pytest.mark.asyncio
async def test_checkout_message_switch_off_is_as_before(monkeypatch, switch, outbox, marks):
    switch(False)
    emp = checkout_setup(monkeypatch)
    await bots._send_checkout_message_059C("T", "7", "🏁 Turno finalizado.", "es", db=SimpleNamespace(), employee=emp, telegram_user_id="7")
    assert outbox == [{"chat_id": "7", "text": "🏁 Turno finalizado.", "reply_markup": None}] and marks.calls == []


def stop_update(n=9):
    return {"update_id": n, "callback_query": {"id": f"cb{n}", "data": "clx:gps:stop", "from": {"id": 7},
                                              "message": {"message_id": 40, "chat": {"id": 7}, "text": REMINDER}}}


async def finish_shift(monkeypatch, emp):
    monkeypatch.setattr(bots, "_get_pending_end_shift_summary", AsyncMock(return_value={"employee_id": str(emp.id)}))
    monkeypatch.setattr(bots, "_clear_pending_end_shift_summary", AsyncMock())
    monkeypatch.setattr(bots, "ensure_company_exists", AsyncMock(return_value=SimpleNamespace(name="VOLTAGE")))
    close = AsyncMock(return_value=(True, "🏁 Turno finalizado."))
    monkeypatch.setattr(bots, "_create_bot_attendance_event", close)
    db = SimpleNamespace(get=AsyncMock(return_value=emp), commit=AsyncMock())
    item = await bots._process_end_shift_summary_text(db, bot=SimpleNamespace(company_id=COMPANY), token="T", update={"update_id": 5}, message={},
                                                      telegram_user_id="7", username=None, chat_id="7", text_value="Instalé 3 tableros",
                                                      language="es", send_replies=True)
    assert item.action == "check_out" and item.ok is True
    close.assert_awaited_once()  # el cierre se registra antes de cualquier mensaje: nunca se pierde
    return db


@pytest.mark.asyncio
async def test_full_flow_finish_twenty_locations_and_button_twice(monkeypatch, switch, outbox, marks):
    """Finalizar + 20 ubicaciones en vivo + tocar el botón 2 veces: un recordatorio, sin bucle."""
    switch(True)
    emp, saved = location_setup(monkeypatch, "checked_out")
    edits = []

    async def tg(token, method, payload=None):
        edits.append((method, payload))

    monkeypatch.setattr(bots, "telegram_call", tg)
    db = await finish_shift(monkeypatch, emp)
    assert outbox[0]["text"] == ("🏁 Turno finalizado.\n\n📝 Resumen de gestión guardado en el cierre de jornada.\n\n" + REMINDER)
    assert outbox[0]["reply_markup"] == BUTTON
    assert bots._send_dynamic_menu.await_count == 1

    for _ in range(20):
        await run_location(live_update(), db=db)
    assert len(outbox) == 1, "20 ubicaciones después: 0 mensajes extra"
    saved.assert_not_awaited()

    first = await bots._process_telegram_update_052C(db, bot=SimpleNamespace(company_id=COMPANY), token="T", update=stop_update(9), send_replies=True)
    assert first.action == "gps_stop_steps"
    assert outbox[1]["text"] == ("Telegram no permite que un bot apague tu ubicación. Para detenerla:\n1. Toca el mapa de ubicación en vivo arriba en este chat.\n"
                                 "2. Toca 'Dejar de compartir'.\n\n✅ Clonexa ya no registra tu ubicación.")
    assert outbox[1]["reply_markup"] is None
    assert bots._send_dynamic_menu.await_count == 2, "después de las instrucciones, el menú"
    assert edits == [("editMessageReplyMarkup", {"chat_id": "7", "message_id": 40, "reply_markup": {"inline_keyboard": []}})], "el botón se quita"

    again = await bots._process_telegram_update_052C(db, bot=SimpleNamespace(company_id=COMPANY), token="T", update=stop_update(10), send_replies=True)
    assert again.action == "gps_stop_steps_again"
    assert outbox[2]["text"] == outbox[1]["text"] and outbox[2]["reply_markup"] is None, "solo las instrucciones"
    assert bots._send_dynamic_menu.await_count == 2, "sin menú ni recordatorio otra vez"
    assert len(outbox) == 3 and sum(REMINDER in m["text"] for m in outbox) == 1, "el recordatorio salió una sola vez"
    assert marks.rows == {(str(COMPANY), "7", "gps_stop_reminded"): CLOSED_AT.isoformat(),
                          (str(COMPANY), "7", "gps_stop_attended"): CLOSED_AT.isoformat()}

    for _ in range(20):  # y si siguen llegando ubicaciones, tampoco
        await run_location(live_update(), db=db)
    assert len(outbox) == 3


@pytest.mark.asyncio
async def test_stop_button_in_english(monkeypatch, switch, outbox, marks):
    switch(True)
    emp, _saved = location_setup(monkeypatch, "checked_out", language="en")
    monkeypatch.setattr(bots, "telegram_call", AsyncMock())
    item = await bots._process_telegram_update_052C(SimpleNamespace(commit=AsyncMock()), bot=SimpleNamespace(company_id=COMPANY), token="T",
                                                    update=stop_update(), send_replies=True)
    assert item.action == "gps_stop_steps"
    assert "1. Tap the live location map above in this chat.\n2. Tap 'Stop sharing'." in outbox[0]["text"]
    assert outbox[0]["text"].endswith("✅ Clonexa is no longer recording your location.")
    bots._answer_callback_query.assert_awaited_once_with("T", "cb9", "✅ Clonexa is no longer recording your location.")


@pytest.mark.asyncio
async def test_edited_text_is_ignored_only_with_switch(monkeypatch, switch, outbox):
    switch(True)
    monkeypatch.setattr(bots, "_get_user_language", AsyncMock(return_value="es"))
    update = {"update_id": 3, "edited_message": {"from": {"id": 7}, "chat": {"id": 7}, "text": "/salida", "edit_date": int(time.time())}}
    item = await bots._process_telegram_update_052C(None, bot=SimpleNamespace(company_id=COMPANY), token="T", update=update, send_replies=True)
    assert item.action == "edited_ignored" and outbox == []


# ------------------------------------------------------------ 5) inicio de turno
def test_start_message_recommends_eight_hours():
    es = bots._txt("es", "gps_required_for_start_059C")
    en = bots._txt("en", "gps_required_for_start_059C")
    assert "«8 horas»" in es and "Hasta que la desactive" in es
    assert '"8 hours"' in en and "Until I turn it off" in en
    assert bots._txt("es", "gps_required_for_start").startswith("📍 Para iniciar turno, comparte tu ubicación.\nRecomendado"), "apagado: el de siempre"


def test_start_shift_uses_new_text_only_with_switch():
    import inspect

    src = inspect.getsource(bots._process_telegram_update_052C)
    assert '("gps_required_for_start_059C" if GPS_STOP_059C.get() else "gps_required_for_start")' in src


# ------------------------------------------------------------ 6) moneda y descuento
def summary_setup(monkeypatch, discount="0.00"):
    shift = {"regular_minutes": 120, "extra_minutes": 0, "projected_pay": "1.10", "discount_total": discount,
             "estimated_total": str(max(Decimal("0"), Decimal("1.10") - Decimal(discount)))}
    monkeypatch.setattr(bots, "_shift_end_projection", AsyncMock(return_value=shift))
    monkeypatch.setattr(bots, "_payroll_cutoff_projection", AsyncMock(return_value=shift))


async def summary(language="es"):
    return await bots._shift_end_summary_message(None, employee=employee(), started_at=CLOSED_AT, ended_at=CLOSED_AT, language=language)


@pytest.mark.asyncio
async def test_usd_and_no_zero_discount(monkeypatch, switch):
    switch(True)
    summary_setup(monkeypatch)
    tokens = cl.use(cl.normalize("USD", "America/New_York", "es"))
    try:
        text_es = await summary("es")
        text_en = await summary("en")
    finally:
        cl.reset(tokens)
    assert "Proyección pago: $1.10 USD" in text_es and "Total estimado: $1.10 USD" in text_es
    assert "Descuento del corte" not in text_es
    assert "Projected pay: $1.10 USD" in text_en and "Period discount" not in text_en


@pytest.mark.asyncio
async def test_usd_with_discount_shows_line(monkeypatch, switch):
    switch(True)
    summary_setup(monkeypatch, discount="0.50")
    tokens = cl.use(cl.normalize("USD", "America/New_York", "es"))
    try:
        text_es = await summary("es")
    finally:
        cl.reset(tokens)
    assert "Proyección pago: $1.10 USD\nDescuento del corte: $0.50 USD\nTotal estimado: $0.60 USD" in text_es


@pytest.mark.asyncio
async def test_switch_off_summary_is_exactly_as_before(monkeypatch, switch):
    switch(False)
    summary_setup(monkeypatch)
    tokens = cl.use(cl.normalize("USD", "America/New_York", "es"))
    try:
        text_es = await summary("es")
    finally:
        cl.reset(tokens)
    assert text_es == ("🏁 Turno finalizado.\n\nFeliz descanso, Ana Pérez.\n\nTotal acumulado del corte:\nOrdinarias: 2h 00m\nExtras: 0h 00m\n\n"
                       "Proyección pago: 1.10\nDescuento del corte: 0.00\nTotal estimado: 1.10")


def test_money_formats():
    assert bot_gps_stop.money(Decimal("1.1"), "USD", bots._format_money) == "$1.10 USD"
    assert bot_gps_stop.money(Decimal("1234.5"), "USD", bots._format_money) == "$1,234.50 USD"
    assert bot_gps_stop.money(Decimal("1234.5"), "COP", bots._format_money) == bots._format_money(Decimal("1234.5")), "COP: el texto de siempre"
    assert bot_gps_stop.money(Decimal("10"), None, bots._format_money) == bots._format_money(Decimal("10"))
    assert bot_gps_stop.is_zero("0.00") and not bot_gps_stop.is_zero("0.01")


# ------------------------------------------------------------ webhook
def webhook_setup(monkeypatch, *, on: bool, flag: bool = False, claim: bool = True):
    config = {"flow_code": "field_operations", "webhook_secret": "s3", "webhook_url": "https://x/api/v1/company-bots-v1/telegram/webhook/" + str(COMPANY)}
    if flag:
        config["live_updates_059C"] = True
    monkeypatch.setattr(company_bots_v1, "ensure_company_bot_storage", AsyncMock())
    monkeypatch.setattr(company_bots_v1, "bot_config_row", AsyncMock(return_value={"bot_token_encrypted": "x", "config_json": config}))
    monkeypatch.setattr(company_bots_v1, "decrypt_token", lambda _v: "TOKEN")
    monkeypatch.setattr(company_bots_v1, "claim_telegram_update", AsyncMock(return_value=claim))
    monkeypatch.setattr(bot_gps_stop, "is_on", AsyncMock(return_value=on))


def request_with(update):
    return SimpleNamespace(json=AsyncMock(return_value=update))


@pytest.mark.asyncio
async def test_webhook_live_update_counts_from_edit_date_and_self_heals_once(monkeypatch):
    webhook_setup(monkeypatch, on=True)
    tasks = BackgroundTasks()
    result = await company_bots_v1.company_telegram_webhook(str(COMPANY), request_with(live_update()), tasks, db=SimpleNamespace(),
                                                            x_telegram_bot_api_secret_token="s3")
    assert result["queued"] is True, "3 h desde el mensaje, pero editado ahora: no es tarde"
    funcs = [t.func for t in tasks.tasks]
    assert funcs == [company_bots_v1.ensure_live_location_updates_059C, company_bots_v1.process_company_telegram_update]
    assert tasks.tasks[0].args == (str(COMPANY), "TOKEN", "https://x/api/v1/company-bots-v1/telegram/webhook/" + str(COMPANY), "s3")

    webhook_setup(monkeypatch, on=True, flag=True)
    tasks = BackgroundTasks()
    await company_bots_v1.company_telegram_webhook(str(COMPANY), request_with(live_update()), tasks, db=SimpleNamespace(), x_telegram_bot_api_secret_token="s3")
    assert [t.func for t in tasks.tasks] == [company_bots_v1.process_company_telegram_update], "ya registrado: no se repite"


@pytest.mark.asyncio
async def test_webhook_late_live_update_is_silent_with_switch(monkeypatch):
    webhook_setup(monkeypatch, on=True, flag=True)
    update = live_update()
    update["edited_message"]["edit_date"] = int(time.time()) - 20 * 60
    tasks = BackgroundTasks()
    result = await company_bots_v1.company_telegram_webhook(str(COMPANY), request_with(update), tasks, db=SimpleNamespace(), x_telegram_bot_api_secret_token="s3")
    assert result == {"ok": True, "ignored": "stale_update"} and tasks.tasks == []


@pytest.mark.asyncio
async def test_webhook_switch_off_is_as_before(monkeypatch):
    webhook_setup(monkeypatch, on=False)
    tasks = BackgroundTasks()
    result = await company_bots_v1.company_telegram_webhook(str(COMPANY), request_with(live_update()), tasks, db=SimpleNamespace(), x_telegram_bot_api_secret_token="s3")
    assert result == {"ok": True, "ignored": "stale_update"}, "apagado: edad por la fecha del mensaje, como siempre"
    assert [t.func for t in tasks.tasks] == [company_bots_v1.send_message]
    assert company_bots_v1.update_age_seconds(live_update(), now=time.time()) > 3 * 3600 - 5


@pytest.mark.asyncio
async def test_self_heal_keeps_url_and_secret(monkeypatch):
    calls = []

    async def post(token, method, payload):
        calls.append((token, method, payload))
        return {"ok": True}

    executed = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, stmt, params=None):
            executed.append((str(stmt), params))

        async def commit(self):
            executed.append(("commit", None))

    monkeypatch.setattr(company_bots_v1, "telegram_post", post)
    monkeypatch.setattr(company_bots_v1, "AsyncSessionLocal", Session)
    await company_bots_v1.ensure_live_location_updates_059C(str(COMPANY), "TOKEN", "https://x/hook", "s3")
    assert calls == [("TOKEN", "setWebhook", {"url": "https://x/hook", "allowed_updates": ["message", "edited_message", "callback_query"],
                                              "drop_pending_updates": False, "secret_token": "s3"})]
    assert "live_updates_059C" in executed[0][0] and executed[0][1] == {"company_id": str(COMPANY)}


@pytest.mark.asyncio
@pytest.mark.parametrize("on,expected", [(True, ["message", "edited_message", "callback_query"]), (False, ["message", "callback_query"])])
async def test_activate_webhook_allowed_updates(monkeypatch, on, expected):
    posted = []

    async def post(token, method, payload):
        posted.append((method, payload))
        return {"ok": True, "result": {"username": "voltage_bot"}}

    monkeypatch.setattr(company_bots_v1, "ensure_company_bot_storage", AsyncMock())
    monkeypatch.setattr(company_bots_v1, "bot_config_row", AsyncMock(return_value={"bot_token_encrypted": "x", "config_json": {}}))
    monkeypatch.setattr(company_bots_v1, "decrypt_token", lambda _v: "TOKEN")
    monkeypatch.setattr(company_bots_v1, "active_modules", AsyncMock(return_value={"workforce", "gps"}))
    monkeypatch.setattr(company_bots_v1, "telegram_post", post)
    monkeypatch.setattr(company_bots_v1, "_cancel_telegram_listener", lambda _c: None)
    monkeypatch.setattr(company_bots_v1, "public_config", lambda row: {})
    monkeypatch.setattr(bot_gps_stop, "is_on", AsyncMock(return_value=on))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    await company_bots_v1.activate_company_telegram_webhook(str(COMPANY), SimpleNamespace(), {"flow_code": "field_operations"}, db=db)
    hook = [p for m, p in posted if m == "setWebhook"][0]
    assert hook["allowed_updates"] == expected
    saved = db.execute.await_args_list[0].args[1]["config_json"]
    assert ('"live_updates_059C": true' in saved) is on


def test_is_on_without_db_is_off():
    import asyncio

    assert asyncio.run(bot_gps_stop.is_on(None, COMPANY)) is False
    assert bot_gps_stop.switch_on({"bot_gps_stop": True}) is True
    assert bot_gps_stop.switch_on('{"bot_gps_stop": true}') is True
    assert bot_gps_stop.switch_on({"bot_gps_stop": "true"}) is False
    assert bot_gps_stop.switch_on(None) is False
