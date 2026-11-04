"""Finalizar turno sin bucles (bot_finish_summary, 068A) contra Postgres REAL (pgserver), con el flujo
real del bot (process_company_telegram_update -> _process_telegram_update); solo Telegram es falso.

- Esperando el resumen, Finalizar u otro boton no reinician nada: "Te falta escribir el resumen".
- La salida es la hora de la ubicacion de Finalizar, no la del resumen.
- Sin resumen en 30 min: cierre con esa hora, nota "Sin resumen", auditoria y aviso, en su idioma.
- Prueba de carga: 100 chats en el mismo minuto (entrada, pausa, retomar, finalizar con ubicacion y
  resumen): 0 errores, p95 < 2 s, orden por chat. Con el pool de produccion (10 + 20).
Si pgserver no esta instalado, se salta."""
from __future__ import annotations

import asyncio
import importlib.util
import itertools
import json
import random
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.schema import CreateColumn  # noqa: E402

from app.api.v1.endpoints import bots, company_bots_v1  # noqa: E402
from app.models.core import Employee  # noqa: E402
from app.models.workforce_attendance import WorkforceAttendanceEvent, WorkforceAttendanceStatus  # noqa: E402
from app.services import bot_finish_summary, bot_processing_alert, bot_punch_gps, ddl_once, nexa_whatsapp, open_shift_alert, telegram_chat_queue  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reports_board_seed", ROOT / "tests" / "fixtures" / "reports_board_seed.py")
seedmod = importlib.util.module_from_spec(spec)
sys.modules.setdefault("reports_board_seed", seedmod)
spec.loader.exec_module(seedmod)

SWITCHES = {"work_locations": True, "bot_gps_stop": True, "bot_punch_gps": True, "bot_finish_summary": True}
EXTRA = """
ALTER TABLE companies ADD COLUMN IF NOT EXISTS settings jsonb DEFAULT '{}'::jsonb;
CREATE TABLE IF NOT EXISTS company_core_settings (company_id uuid PRIMARY KEY, currency text, timezone text, language text);
INSERT INTO modules (code, name) VALUES ('gps', 'gps')
"""
TELEGRAM_LATENCY = 0.12  # lo que tarda de verdad un sendMessage desde Railway, mas o menos
_ids = itertools.count(1000)


class NoExtension:
    """pgserver no trae pgcrypto (produccion si): se omite SOLO esa sentencia."""

    def __init__(self, db):
        self.db = db

    async def execute(self, statement, *args, **kwargs):
        if "CREATE EXTENSION" in str(statement).upper():
            return None
        return await self.db.execute(statement, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.db, name)


def _statements(filename: str) -> list[str]:
    path = ROOT / "migrations" / "versions" / filename
    module_spec = importlib.util.spec_from_file_location(f"migration_{filename[:4]}", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    out: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: out.append(str(sql)))
    module.upgrade()
    return out


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_finish_"), cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    def _add_missing(sync, model) -> None:
        have = {r[0] for r in sync.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": model.__tablename__})}
        for column in model.__table__.columns:
            if column.name not in have:
                ddl = str(CreateColumn(column).compile(dialect=sync.dialect)).replace(" NOT NULL", "")
                sync.execute(text(f"ALTER TABLE {model.__tablename__} ADD COLUMN {ddl}"))

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await seedmod.create_schema(conn)
            for stmt in [s for s in EXTRA.split(";") if s.strip()]:
                await conn.execute(text(stmt))
            await conn.run_sync(lambda sync: WorkforceAttendanceStatus.__table__.create(sync))
            await conn.run_sync(_add_missing, WorkforceAttendanceEvent)
            await conn.run_sync(_add_missing, Employee)
            for stmt in [s for s in _statements("024y_open_shift_alert.py") if "shift_manual_closes" in s]:
                await conn.execute(text(stmt))
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as db:
            await bots.ensure_bot_storage.ddl_fn(NoExtension(db))
            await bots._ensure_gps_perimeter_storage.ddl_fn(NoExtension(db))
            await db.commit()
        await engine.dispose()

    asyncio.run(setup())
    yield url


@pytest.fixture()
async def maker(pg_url):
    # Igual que app/core/database.py: lo que importa en la prueba de carga.
    engine = create_async_engine(pg_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
    ddl_once.reset()
    for fn in (bots.ensure_bot_storage, bots._ensure_gps_perimeter_storage):
        checks = await ddl_once._record(fn.ddl_fn)
        ddl_once._CHECKS[fn.ddl_key] = [c for c in checks if c[0] != "ext"]
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ddl_once.reset()
    await engine.dispose()


@pytest.fixture()
async def world(maker, monkeypatch):
    sent: list[dict] = []
    state = SimpleNamespace(latency=0.0)

    async def box(token, chat_id, text_value, reply_markup=None):
        if state.latency:
            await asyncio.sleep(state.latency)
        sent.append({"chat": str(chat_id), "text": text_value, "markup": reply_markup})

    async def instance(_db, company_id):
        return SimpleNamespace(id=uuid.UUID(int=7), company_id=company_id, bot_username="voltage_bot", bot_token_encrypted="x")

    failures = AsyncMock()
    alerts = AsyncMock(return_value=True)
    monkeypatch.setattr(bots, "_send_telegram_message", box)
    monkeypatch.setattr(bots, "_answer_callback_query", AsyncMock())
    monkeypatch.setattr(bots, "_send_telegram_chat_action", AsyncMock())
    monkeypatch.setattr(bots, "ensure_company_exists", AsyncMock(side_effect=lambda _db, cid: SimpleNamespace(id=cid, name="VOLTAGE")))
    monkeypatch.setattr(company_bots_v1, "AsyncSessionLocal", maker)
    monkeypatch.setattr(company_bots_v1, "get_telegram_instance", instance)
    monkeypatch.setattr(company_bots_v1, "send_failure_reply_060A", failures)
    monkeypatch.setattr(nexa_whatsapp, "_deliver_alert", alerts)
    bot_processing_alert.reset()
    yield SimpleNamespace(maker=maker, sent=sent, state=state, failures=failures, alerts=alerts)
    bot_processing_alert.reset()


async def _company(w, switches: dict | None = None) -> str:
    async with w.maker() as db:
        cid = await seedmod.company(db, f"E{uuid.uuid4().hex[:6]}", board=False)
        await db.execute(text("""UPDATE company_modules cm SET settings = CAST(:s AS jsonb) FROM modules m
                                 WHERE m.id = cm.module_id AND m.code = 'workforce' AND cm.company_id = CAST(:c AS uuid)"""),
                         {"c": cid, "s": json.dumps(SWITCHES if switches is None else switches)})
        await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
                                 SELECT CAST(:c AS uuid), id, true, '{}'::jsonb FROM modules WHERE code = 'gps'"""), {"c": cid})
        place = await seedmod.place(db, cid, "Alabama", "AL", "America/Chicago", 1)
        await db.commit()
    return cid, place


async def _person(w, cid: str, place: str, tg: str, language: str | None = None, name: str = "Ana") -> str:
    async with w.maker() as db:
        eid = await seedmod.person(db, cid, name, f"D-{tg}", place)
        await db.execute(text("UPDATE employees SET telegram_user_id = :t WHERE id = CAST(:e AS uuid)"), {"t": tg, "e": eid})
        if language:
            await db.execute(text("""INSERT INTO company_telegram_user_preferences (company_id, telegram_user_id, language)
                                     VALUES (CAST(:c AS uuid), :t, :l)"""), {"c": cid, "t": tg, "l": language})
        await db.commit()
    return eid


def tap(tg: str, data: str, code: str = "es") -> dict:
    uid = next(_ids)
    who = {"id": int(tg), "language_code": code}
    return {"update_id": uid, "callback_query": {"id": str(uid), "from": who, "data": data,
                                                 "message": {"message_id": uid, "chat": {"id": int(tg)}, "from": {"id": 1, "is_bot": True}}}}


def loc(tg: str, code: str = "es", lat: float = 32.38, lng: float = -86.3) -> dict:
    uid = next(_ids)
    return {"update_id": uid, "message": {"message_id": uid, "from": {"id": int(tg), "language_code": code}, "chat": {"id": int(tg)},
                                          "location": {"latitude": lat, "longitude": lng, "horizontal_accuracy": 10}}}


def say(tg: str, value: str, code: str = "es") -> dict:
    uid = next(_ids)
    return {"update_id": uid, "message": {"message_id": uid, "from": {"id": int(tg), "language_code": code}, "chat": {"id": int(tg)}, "text": value}}


async def run(cid: str, update: dict) -> None:
    await company_bots_v1.process_company_telegram_update(cid, "field_operations", "T", update)


async def _start_and_finish(cid: str, tg: str, code: str = "es") -> None:
    """Entrada con ubicacion y Finalizar con ubicacion: queda esperando el resumen."""
    for update in (tap(tg, "clx:cmd:entrada", code), loc(tg, code), tap(tg, "clx:cmd:salida", code), loc(tg, code)):
        await run(cid, update)


async def _pending(w, cid: str, tg: str, action: str = "end_shift_summary") -> dict | None:
    async with w.maker() as db:
        row = (await db.execute(text("""SELECT payload_json, updated_at, expires_at FROM company_telegram_pending_actions
                                        WHERE company_id = CAST(:c AS uuid) AND telegram_user_id = :t AND action = :a"""),
                                {"c": cid, "t": tg, "a": action})).mappings().first()
    return dict(row) if row else None


async def _status(w, cid: str, eid: str) -> dict:
    async with w.maker() as db:
        row = (await db.execute(text("""SELECT status, check_in_at, check_out_at FROM workforce_attendance_status
                                        WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)"""), {"c": cid, "e": eid})).mappings().first()
    return dict(row)


async def _events(w, cid: str, eid: str, *kinds: str) -> list[dict]:
    async with w.maker() as db:
        rows = (await db.execute(text("""
            SELECT event_type, occurred_at, created_at, detail, notes, source_channel, payload_json FROM workforce_attendance_events
            WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND event_type = ANY(:k) ORDER BY occurred_at, created_at
        """), {"c": cid, "e": eid, "k": list(kinds)})).mappings().all()
    return [dict(r) for r in rows]


async def _backdate(w, cid: str, tg: str, minutes: float) -> datetime:
    """Finalizar con ubicacion hace `minutes`: mueve la hora de la ubicacion y su plazo."""
    located = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    async with w.maker() as db:
        row = (await db.execute(text("""SELECT payload_json FROM company_telegram_pending_actions
                                        WHERE company_id = CAST(:c AS uuid) AND telegram_user_id = :t AND action = 'end_shift_summary'"""),
                                {"c": cid, "t": tg})).scalar()
        payload = row if isinstance(row, dict) else json.loads(row)
        payload["punch_location"]["located_at"] = located.isoformat()
        if "auto_close_at" in payload:
            payload["auto_close_at"] = (located + timedelta(minutes=bot_finish_summary.AUTO_CLOSE_MINUTES)).isoformat()
        await db.execute(text("""UPDATE company_telegram_pending_actions SET payload_json = CAST(:p AS jsonb)
                                 WHERE company_id = CAST(:c AS uuid) AND telegram_user_id = :t AND action = 'end_shift_summary'"""),
                         {"c": cid, "t": tg, "p": json.dumps(payload)})
        await db.commit()
    return located


def texts(w, tg: str) -> list[str]:
    return [m["text"] for m in w.sent if m["chat"] == tg]


# ------------------------------------------------------------ 1) no reinicia
@pytest.mark.parametrize("language,code,expected", [
    ("es", "en", "Te falta escribir el resumen de hoy. Escríbelo en un solo mensaje."),
    ("en", "es", "You still need to write today's summary. Send it in a single message."),
    (None, "en", "You still need to write today's summary. Send it in a single message."),
    ("fr", "es", "Il vous reste à écrire le résumé d'aujourd'hui. Écrivez-le en un seul message."),
])
async def test_while_waiting_nothing_restarts_and_the_reply_is_in_the_person_language(world, language, code, expected):
    w = world
    cid, place = await _company(w)
    eid = await _person(w, cid, place, "501", language)
    await _start_and_finish(cid, "501", code)
    before = await _pending(w, cid, "501")
    assert before["payload_json"]["auto_close_at"], "con el interruptor lleva plazo"
    w.sent.clear()

    # El caso del reporte: vuelve a tocar Finalizar; tambien otro boton, comando, ubicacion y foto.
    photo = {"update_id": next(_ids), "message": {"message_id": 9, "from": {"id": 501, "language_code": code}, "chat": {"id": 501}, "photo": [{"file_id": "x"}]}}
    for update in (tap("501", "clx:cmd:salida", code), tap("501", "clx:cmd:pausa", code), tap("501", "clx:cmd:material", code),
                   say("501", "/salida", code), say("501", "/estado", code), loc("501", code), photo):
        await run(cid, update)
    assert texts(w, "501") == [expected] * 7, "ni ubicacion ni resumen de nuevo, y sin menu"
    assert await _pending(w, cid, "501", "gps_punch") is None, "no pide ubicacion otra vez"
    after = await _pending(w, cid, "501")
    assert after["updated_at"] == before["updated_at"] and after["payload_json"] == before["payload_json"], "el plazo y la ubicacion no se mueven"
    assert len(await _events(w, cid, eid, "gps_location")) == 2, "esa ubicacion extra no se registra"
    assert (await _status(w, cid, eid))["status"] == "working"
    w.failures.assert_not_awaited()


async def test_language_button_still_works_while_waiting(world):
    w = world
    cid, place = await _company(w)
    await _person(w, cid, place, "502", "es")
    await _start_and_finish(cid, "502")
    w.sent.clear()
    await run(cid, tap("502", "clx:language"))
    assert texts(w, "502") == [bots._txt("es", "choose_language")]
    await run(cid, tap("502", "clx:lang:en"))
    assert texts(w, "502")[1] == bots._txt("en", "language_saved")
    w.sent.clear()
    await run(cid, tap("502", "clx:cmd:salida"))
    assert texts(w, "502") == [bots._txt("en", "summary_missing_068A")], "ya en el idioma nuevo"


# ------------------------------------------------------------ 2) hora de salida
async def test_exit_time_is_the_location_of_finalizar_not_the_summary(world):
    w = world
    cid, place = await _company(w)
    eid = await _person(w, cid, place, "503", "en")
    await _start_and_finish(cid, "503", "en")
    located = await _backdate(w, cid, "503", 20)
    w.sent.clear()
    await run(cid, say("503", "Mal1 dressing", "en"))
    out = (await _events(w, cid, eid, "check_out"))[0]
    assert out["occurred_at"] == located, "20 minutos antes del resumen"
    assert out["detail"] == "Mal1 dressing"
    payload = out["payload_json"]
    assert payload["exit_from_location"] is True and datetime.fromisoformat(payload["summary_received_at"]) > located + timedelta(minutes=19)
    status = await _status(w, cid, eid)
    assert status["status"] == "checked_out" and status["check_out_at"] == located
    assert await _pending(w, cid, "503") is None
    assert bots._txt("en", "end_shift_summary_saved") in texts(w, "503")[0]


async def test_exit_is_never_before_a_later_punch(world):
    assert bot_finish_summary.exit_time({"located_at": "2026-11-04T21:56:00+00:00"}, datetime(2026, 11, 4, 22, 0, tzinfo=timezone.utc)) == datetime(2026, 11, 4, 22, 0, tzinfo=timezone.utc)
    assert bot_finish_summary.exit_time({"located_at": "2026-11-04T21:56:00+00:00"}, datetime(2026, 11, 4, 11, 0, tzinfo=timezone.utc)) == datetime(2026, 11, 4, 21, 56, tzinfo=timezone.utc)
    assert bot_finish_summary.exit_time({}, None) is None and bot_finish_summary.exit_time(None) is None


# ------------------------------------------------------------ 3) cierre sin resumen a los 30 min
@pytest.fixture()
def tokens(monkeypatch):
    monkeypatch.setattr(bot_punch_gps, "bot_token", AsyncMock(return_value="T"))


async def test_no_summary_in_30_minutes_closes_with_location_time_note_audit_and_notice(world, tokens):
    w = world
    cid, place = await _company(w)
    eid = await _person(w, cid, place, "504", "en", name="Sandy")
    await _start_and_finish(cid, "504", "en")
    located = await _backdate(w, cid, "504", 31)
    w.sent.clear()

    async with w.maker() as db:
        assert await bot_finish_summary.run_all(db) == 1

    status = await _status(w, cid, eid)
    assert status["status"] == "checked_out" and status["check_out_at"] == located
    event = (await _events(w, cid, eid, "check_out"))[0]
    assert event["occurred_at"] == located and event["detail"] == "Sin resumen" and event["notes"] == "Sin resumen"
    assert event["source_channel"] == bot_finish_summary.CHANNEL
    payload = event["payload_json"]
    assert payload["auto_closed"] is True and payload["manual_close"] is True and payload["note"] == "Sin resumen"
    assert payload["punch_location"]["latitude"] == 32.38, "la ubicacion de Finalizar queda en el evento"
    async with w.maker() as db:
        audit = await open_shift_alert.recent_closes(db, cid)
    assert len(audit) == 1 and audit[0]["note"] == "Sin resumen" and audit[0]["closed_by"] == bot_finish_summary.ACTOR
    assert await _pending(w, cid, "504") is None

    notice = texts(w, "504")
    label = open_shift_alert.local_label(located, "America/Chicago")
    assert notice[0] == bots._txt("en", "auto_closed_068A", time=label), "en su idioma, con la hora del lugar"
    menu = next(m for m in w.sent if m["markup"] and "inline_keyboard" in m["markup"])
    assert menu["markup"]["inline_keyboard"][0][0]["callback_data"] == "clx:cmd:entrada", "ya puede iniciar otro turno"

    w.sent.clear()
    async with w.maker() as db:
        assert await bot_finish_summary.run_all(db) == 0, "un solo cierre"
    assert w.sent == []
    await run(cid, say("504", "too late", "en"))
    assert len(await _events(w, cid, eid, "check_out")) == 1, "un texto tarde no marca otra salida"


async def test_before_the_deadline_nothing_closes_and_the_summary_still_wins(world, tokens):
    w = world
    cid, place = await _company(w)
    eid = await _person(w, cid, place, "505")
    await _start_and_finish(cid, "505")
    located = await _backdate(w, cid, "505", 29)
    async with w.maker() as db:
        assert await bot_finish_summary.run_all(db) == 0
    assert (await _status(w, cid, eid))["status"] == "working"
    await run(cid, say("505", "Hecho a tiempo"))
    async with w.maker() as db:
        assert await bot_finish_summary.run_all(db) == 0
    events = await _events(w, cid, eid, "check_out")
    assert len(events) == 1 and events[0]["detail"] == "Hecho a tiempo" and events[0]["occurred_at"] == located


async def test_old_pending_without_deadline_is_left_alone(world, tokens):
    """Lo que ya esperaba resumen antes de encender (sin auto_close_at): nunca se cierra solo."""
    w = world
    cid, place = await _company(w)
    eid = await _person(w, cid, place, "506")
    await _start_and_finish(cid, "506")
    async with w.maker() as db:
        await db.execute(text("""UPDATE company_telegram_pending_actions SET payload_json = payload_json - 'auto_close_at', updated_at = now() - interval '3 hours'
                                 WHERE company_id = CAST(:c AS uuid) AND telegram_user_id = '506'"""), {"c": cid})
        await db.commit()
    await _backdate(w, cid, "506", 180)
    async with w.maker() as db:
        assert await bot_finish_summary.run_all(db) == 0
    assert (await _status(w, cid, eid))["status"] == "working"
    assert await _pending(w, cid, "506") is not None


async def test_shift_closed_by_the_leader_meanwhile_drops_the_pending(world, tokens):
    w = world
    cid, place = await _company(w)
    eid = await _person(w, cid, place, "507")
    other = await _person(w, cid, place, "508", name="Luz")
    await _start_and_finish(cid, "507")
    await _start_and_finish(cid, "508")
    await _backdate(w, cid, "507", 31)
    async with w.maker() as db:
        for person in (eid, other):
            await open_shift_alert.close_shift(db, cid, person, {"end_at": datetime.now(timezone.utc).isoformat(), "note": "Finalizado por el lider"}, actor="Noel", actor_user_id=None)
        assert await bot_finish_summary.run_all(db) == 0, "ya estaba cerrado"
    assert len(await _events(w, cid, eid, "check_out")) == 1
    assert await _pending(w, cid, "507") is None

    # El otro aun no vence: al tocar un boton el pendiente se descarta y el menu sigue normal.
    w.sent.clear()
    await run(cid, tap("508", "clx:cmd:entrada"))
    assert await _pending(w, cid, "508") is None
    assert texts(w, "508") == [bot_punch_gps.t("es", "prompt")], "puede iniciar otro turno, sin pedirle el resumen"


async def test_two_closers_at_once_close_only_once(world):
    w = world
    cid, place = await _company(w)
    eid = await _person(w, cid, place, "509")
    await _start_and_finish(cid, "509")
    await _backdate(w, cid, "509", 40)
    notices = AsyncMock()

    async def closer():
        async with w.maker() as db:
            return await bot_finish_summary.run_company(db, cid, notify=notices)

    assert sorted(await asyncio.gather(closer(), closer(), closer())) == [0, 0, 1]
    assert len(await _events(w, cid, eid, "check_out")) == 1
    notices.assert_awaited_once()


# ------------------------------------------------------------ 4) interruptor por empresa
async def test_switch_off_keeps_everything_as_before(world, tokens):
    w = world
    switches = {k: v for k, v in SWITCHES.items() if k != "bot_finish_summary"}
    cid, place = await _company(w, switches)
    eid = await _person(w, cid, place, "510")
    async with w.maker() as db:
        assert await bot_finish_summary.is_on(db, cid) is False
        assert cid not in await bot_finish_summary.companies_on(db)
    await _start_and_finish(cid, "510")
    pending = await _pending(w, cid, "510")
    assert "auto_close_at" not in pending["payload_json"], "sin plazo: nunca se cierra solo"
    w.sent.clear()
    await run(cid, tap("510", "clx:cmd:salida"))
    assert texts(w, "510") == [bot_punch_gps.t("es", "prompt")], "lo de antes: vuelve a pedir la ubicacion"
    await _backdate(w, cid, "510", 45)
    async with w.maker() as db:
        await bot_finish_summary.run_all(db)
    assert (await _status(w, cid, eid))["status"] == "working"


async def test_other_company_rows_are_not_touched(world):
    w = world
    cid, place = await _company(w)
    other, other_place = await _company(w)
    await _person(w, cid, place, "511")
    other_eid = await _person(w, other, other_place, "512")
    await _start_and_finish(cid, "511")
    await _start_and_finish(other, "512")
    await _backdate(w, other, "512", 40)
    async with w.maker() as db:
        assert await bot_finish_summary.run_company(db, cid, notify=AsyncMock()) == 0, "solo mira lo de su empresa"
    assert (await _status(w, other, other_eid))["status"] == "working"


# ------------------------------------------------------------ 5) carga
def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


STEPS = ["clx:cmd:entrada", None, "clx:cmd:pausa", None, "clx:cmd:reanudar", None, "clx:cmd:salida", None, "summary"]


def _step(tg: str, step: str | None, code: str) -> dict:
    if step is None:
        return loc(tg, code)
    if step == "summary":
        return say(tg, f"Resumen de {tg}", code)
    return tap(tg, step, code)


async def _load(w, cid: str, people: dict[str, str], *, window: float, capsys, label: str) -> list[float]:
    rng = random.Random(68)
    latencies: list[float] = []
    w.state.latency = TELEGRAM_LATENCY
    bot_processing_alert.watch({cid: "VOLTAGE"})
    began = time.perf_counter()

    async def timed(update: dict) -> None:
        t0 = time.perf_counter()
        await run(cid, update)
        latencies.append(time.perf_counter() - t0)

    async def chat(tg: str, code: str) -> None:
        # Como un webhook: cada update sale a su hora sin esperar a que termine el anterior.
        marks = sorted(rng.uniform(0, window) for _ in STEPS)
        jobs = []
        for mark, step in zip(marks, STEPS):
            await asyncio.sleep(max(0.0, mark - (time.perf_counter() - began)))
            jobs.append(asyncio.create_task(timed(_step(tg, step, code))))
        await asyncio.gather(*jobs)

    await asyncio.wait_for(asyncio.gather(*[chat(tg, "en" if int(tg) % 2 else "es") for tg in people]), timeout=420)
    total = time.perf_counter() - began
    with capsys.disabled():
        print(f"\n[carga {label}] {len(people)} chats, {len(latencies)} updates en {total:.1f} s; "
              f"p50={percentile(latencies, .5):.3f} s p95={percentile(latencies, .95):.3f} s p99={percentile(latencies, .99):.3f} s "
              f"max={max(latencies):.3f} s; errores={w.failures.await_count}; avisos={w.alerts.await_count}; latencia Telegram simulada={TELEGRAM_LATENCY} s")
    return latencies


async def _assert_all_finished(w, cid: str, people: dict[str, str]) -> None:
    w.failures.assert_not_awaited()
    assert telegram_chat_queue.pending_chats() == 0
    for tg, eid in people.items():
        kinds = await _events(w, cid, eid, "check_in", "break_start", "break_end", "check_out")
        assert [k["event_type"] for k in kinds] == ["check_in", "break_start", "break_end", "check_out"], f"orden del chat {tg}"
        assert (await _status(w, cid, eid))["status"] == "checked_out"
        gps = await _events(w, cid, eid, "gps_location")
        assert len(gps) == 4, f"una ubicacion por marcacion en el chat {tg}"
        assert kinds[-1]["occurred_at"] == gps[-1]["occurred_at"], "salida con la hora de la ubicacion"
        assert kinds[-1]["detail"] == f"Resumen de {tg}"
        assert await _pending(w, cid, tg) is None
        replies = texts(w, tg)
        language = "en" if int(tg) % 2 else "es"
        assert replies[0] == bot_punch_gps.t(language, "prompt"), f"primera respuesta del chat {tg}"
        assert bots._txt(language, "summary_missing_068A") not in replies, "nadie queda en el bucle"
        assert bots._txt(language, "end_shift_summary_prompt") in replies and bots._txt(language, "end_shift_summary_saved") in replies[-2]


async def _crowd(w, base: int) -> tuple[str, dict[str, str]]:
    cid, place = await _company(w)
    people = {}
    for n in range(100):
        tg = str(base + n)
        people[tg] = await _person(w, cid, place, tg, name=f"P{n}")
    return cid, people


async def test_load_100_chats_in_the_same_minute(world, capsys):
    """Lo pedido: 100 chats, cada uno entrada, pausa, retomar y finalizar con ubicacion + resumen, todo en 1 minuto."""
    w = world
    cid, people = await _crowd(w, 70000)
    latencies = await _load(w, cid, people, window=55.0, capsys=capsys, label="mismo minuto")
    assert len(latencies) == 900
    await _assert_all_finished(w, cid, people)
    assert percentile(latencies, 0.95) < 2.0


async def test_load_burst_keeps_order_and_zero_errors(world, capsys):
    """Peor que lo pedido: los 900 updates en 5 s. El tiempo solo se reporta; el orden y los errores si se exigen."""
    w = world
    cid, people = await _crowd(w, 80000)
    await _load(w, cid, people, window=5.0, capsys=capsys, label="rafaga de 5 s")
    await _assert_all_finished(w, cid, people)
