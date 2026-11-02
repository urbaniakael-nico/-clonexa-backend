"""Bot VOLTAGE contra Postgres REAL (pgserver): causa del DBAPIError, 40 chats a la vez,
recordatorio de ubicacion a los 3 min, aviso de turno abierto (12 h) y "Cerrar turno".

- Causa: el DDL "por si acaso" de cada update (CREATE INDEX IF NOT EXISTS sobre
  gps_tracking_sessions) toma un ShareLock de la tabla hasta el commit; dos updates a
  la vez + UPDATE gps_tracking_sessions -> "deadlock detected" (40P01). Con ddl_once
  no se toma ningun bloqueo y no hay deadlock.
- 40 chats enviando marcaciones + actualizaciones en vivo a la vez: 0 errores, cada
  marcacion respondida, orden por chat respetado, las actualizaciones en vivo no tocan
  la base.
Si pgserver no esta instalado, se salta."""
from __future__ import annotations

import asyncio
import importlib
import json
import random
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import bots, company_bots_v1  # noqa: E402
from app.services import bot_punch_gps, ddl_once, open_shift_alert, telegram_chat_queue  # noqa: E402
from tests.test_brand_pg import BASE_SCHEMA  # noqa: E402

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
EXTRA = """
ALTER TABLE companies ADD COLUMN IF NOT EXISTS timezone text;
CREATE TABLE IF NOT EXISTS work_locations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  name varchar(80) NOT NULL, timezone varchar(64) NOT NULL DEFAULT 'America/Bogota');
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  full_name varchar(200), role varchar(80), status varchar(40) DEFAULT 'active', telegram_user_id varchar(120),
  work_location_id uuid NULL REFERENCES work_locations(id));
CREATE TABLE IF NOT EXISTS workforce_attendance_status (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid NOT NULL,
  status varchar(40), last_event_type varchar(80), last_event_at timestamptz, check_in_at timestamptz, check_out_at timestamptz,
  break_started_at timestamptz, worked_minutes integer, break_minutes integer, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid,
  event_type varchar(80) NOT NULL, event_label varchar(180) NOT NULL, employee_name varchar(180), employee_role varchar(80), status_after varchar(40) NOT NULL,
  source varchar(80) NOT NULL DEFAULT 'client', notes text, module_code varchar(80) NOT NULL DEFAULT 'workforce',
  source_channel varchar(80) NOT NULL DEFAULT 'client', source_ref varchar(180), detail text,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb, metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  latitude numeric(12,8), longitude numeric(12,8), occurred_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS workforce_session_policy (company_id uuid PRIMARY KEY, cutoff_time varchar(5), alert_after_hours numeric)
"""


def _migration_sql() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.024y_open_shift_alert")
    module.op = Op()
    module.upgrade()
    return statements


class NoExtension:
    """pgserver no trae pgcrypto (produccion si; gen_random_uuid es nativo desde PG 13):
    se omite SOLO esa sentencia; el resto del DDL corre tal cual."""

    def __init__(self, db):
        self.db = db

    async def execute(self, statement, *args, **kwargs):
        if "CREATE EXTENSION" in str(statement).upper():
            return None
        return await self.db.execute(statement, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.db, name)


async def _prime_checks() -> None:
    """Lo mismo que ddl_once graba, sin la extension (ver NoExtension)."""
    for fn in (bots.ensure_bot_storage, bots._ensure_gps_perimeter_storage):
        checks = await ddl_once._record(fn.ddl_fn)
        ddl_once._CHECKS[fn.ddl_key] = [c for c in checks if c[0] != "ext"]


def raw_ddl(fn):
    async def run(db):
        return await fn.ddl_fn(NoExtension(db))
    return run


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_punch_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in (BASE_SCHEMA + ";" + EXTRA).split(";") if s.strip()] + _migration_sql():
                await conn.execute(text(stmt))
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as db:  # las tablas del bot, con el DDL de siempre
            await bots.ensure_bot_storage.ddl_fn(NoExtension(db))
            await bots._ensure_gps_perimeter_storage.ddl_fn(NoExtension(db))
            await db.commit()
        await engine.dispose()

    asyncio.run(setup())
    yield url


@pytest.fixture()
async def maker(pg_url):
    engine = create_async_engine(pg_url, pool_size=50, max_overflow=20)
    ddl_once.reset()
    await _prime_checks()
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ddl_once.reset()
    await engine.dispose()


async def _company(db, cid: str, settings: dict | None, tz: str = "America/New_York") -> None:
    await db.execute(text("INSERT INTO companies (id, name, timezone) VALUES (CAST(:i AS uuid), :n, :tz) ON CONFLICT DO NOTHING"),
                     {"i": cid, "n": cid[:8], "tz": tz})
    mid = (await db.execute(text("SELECT id::text FROM modules WHERE code = 'workforce'"))).scalar()
    if not mid:
        mid = (await db.execute(text("INSERT INTO modules (code, name) VALUES ('workforce', 'workforce') RETURNING id::text"))).scalar()
    if settings is not None:
        await db.execute(text("DELETE FROM company_modules WHERE company_id = CAST(:c AS uuid)"), {"c": cid})
        await db.execute(text("INSERT INTO company_modules (company_id, module_id, enabled, settings) VALUES (CAST(:c AS uuid), CAST(:m AS uuid), true, CAST(:s AS jsonb))"),
                         {"c": cid, "m": mid, "s": json.dumps(settings)})
    await db.commit()


async def _employee(db, cid: str, name: str, role: str = "operario", tg: str | None = None, place: str | None = None) -> str:
    eid = (await db.execute(text("""
        INSERT INTO employees (company_id, full_name, role, telegram_user_id, work_location_id)
        VALUES (CAST(:c AS uuid), :n, :r, :t, CAST(:p AS uuid)) RETURNING id::text
    """), {"c": cid, "n": name, "r": role, "t": tg, "p": place})).scalar()
    await db.commit()
    return eid


async def _open_shift(db, cid: str, eid: str, started: datetime, status: str = "working") -> None:
    await db.execute(text("""
        INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :s, 'check_in', :at, :at)
    """), {"c": cid, "e": eid, "s": status, "at": started})
    await db.commit()


async def _modes(db, table: str) -> set[str]:
    rows = (await db.execute(text("""
        SELECT mode FROM pg_locks WHERE pid = pg_backend_pid() AND relation = to_regclass(:t)
    """), {"t": table})).all()
    return {r[0] for r in rows}


# ------------------------------------------------------------ 1) causa exacta
@pytest.mark.asyncio
async def test_cause_old_ddl_holds_table_locks_and_ddl_once_takes_none(maker):
    async with maker() as db:
        await raw_ddl(bots.ensure_bot_storage)(db)  # lo de siempre, en cada update
        assert "ShareLock" in await _modes(db, "gps_tracking_sessions"), "CREATE INDEX IF NOT EXISTS bloquea la tabla hasta el commit"
        await db.rollback()
    async with maker() as db:
        await bots.ensure_bot_storage(db)  # 060A
        await bots._ensure_gps_perimeter_storage(db)
        assert await _modes(db, "gps_tracking_sessions") == set()
        assert await _modes(db, "company_telegram_pending_actions") == set()
        await db.rollback()
    assert {"bot_storage", "gps_perimeter_storage"} <= ddl_once._READY


async def _two_updates_at_once(maker, storage, cid: str, eid: str) -> list[str]:
    async def one():
        async with maker() as db:
            try:
                await storage(db)
                await asyncio.sleep(0.2)  # los dos ya pasaron por el DDL
                await db.execute(text("""
                    UPDATE gps_tracking_sessions SET last_location_at = now(), updated_at = now()
                    WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND status = 'active'
                """), {"c": cid, "e": eid})
                await db.commit()
                return "ok"
            except DBAPIError as exc:
                await db.rollback()
                return telegram_chat_queue.sqlstate_of(exc) or type(exc).__name__

    return list(await asyncio.gather(one(), one()))


@pytest.mark.asyncio
async def test_two_updates_deadlock_before_and_not_after(maker):
    cid = str(uuid.uuid4())
    async with maker() as db:
        await _company(db, cid, {})
        eid = await _employee(db, cid, "Ana")
        await db.execute(text("INSERT INTO gps_tracking_sessions (company_id, employee_id, status) VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'active')"),
                         {"c": cid, "e": eid})
        await db.commit()
    before = await _two_updates_at_once(maker, raw_ddl(bots.ensure_bot_storage), cid, eid)
    assert "40P01" in before, f"el DBAPIError de produccion era un deadlock: {before}"
    after = await _two_updates_at_once(maker, bots.ensure_bot_storage, cid, eid)
    assert after == ["ok", "ok"]


# ------------------------------------------------------------ 2) 40 chats a la vez
@pytest.mark.asyncio
async def test_forty_chats_at_once_zero_errors_in_order_and_live_updates_skip_the_db(maker, monkeypatch):
    cid = str(uuid.uuid4())
    async with maker() as db:
        await _company(db, cid, {"bot_punch_gps": True, "bot_gps_stop": True})
        employees = {}
        for n in range(40):
            tg = str(9000 + n)
            employees[tg] = await _employee(db, cid, f"P{n}", tg=tg)
            await db.execute(text("INSERT INTO gps_tracking_sessions (company_id, employee_id, status) VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'active')"),
                             {"c": cid, "e": employees[tg]})
        await db.commit()

    order: dict[str, list[int]] = {tg: [] for tg in employees}
    replies: list[str] = []
    live_seen_by_processor: list[int] = []

    async def processor(db, *, bot, token, update, send_replies):
        msg = update.get("message") or update.get("edited_message") or {}
        tg = str(msg["from"]["id"])
        if "edited_message" in update:
            live_seen_by_processor.append(update["update_id"])
        await bots.ensure_bot_storage(db)
        await bots._ensure_gps_perimeter_storage(db)
        await db.execute(text("""
            UPDATE gps_tracking_sessions SET last_location_at = now(), updated_at = now()
            WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND status = 'active'
        """), {"c": cid, "e": employees[tg]})
        await asyncio.sleep(random.random() / 200)
        await db.execute(text("""
            INSERT INTO company_telegram_pending_actions (company_id, telegram_user_id, employee_id, action, payload_json, updated_at)
            VALUES (CAST(:c AS uuid), :t, CAST(:e AS uuid), 'gps_punch', CAST(:p AS jsonb), now())
            ON CONFLICT (company_id, telegram_user_id, action) DO UPDATE SET payload_json = EXCLUDED.payload_json, updated_at = now()
        """), {"c": cid, "t": tg, "e": employees[tg], "p": json.dumps({"u": update["update_id"]})})
        await db.commit()
        order[tg].append(update["update_id"])
        replies.append(tg)

    monkeypatch.setattr(company_bots_v1, "AsyncSessionLocal", maker)
    monkeypatch.setattr(company_bots_v1, "get_telegram_instance", AsyncMock(return_value=SimpleNamespace(bot_token_encrypted="x", company_id=cid)))
    monkeypatch.setattr(company_bots_v1, "_process_telegram_update", processor)
    failures = AsyncMock()
    monkeypatch.setattr(company_bots_v1, "send_failure_reply_060A", failures)

    # Webhook: el interruptor ya se vio (cache); las actualizaciones en vivo no tocan la base.
    bot_punch_gps.remember(cid, True, "s3cr3t")

    class NoDb:
        def __getattr__(self, name):
            raise AssertionError(f"la actualizacion en vivo toco la base ({name})")

    async def live_edit(tg: str, n: int):
        update = {"update_id": 500000 + int(tg) * 100 + n, "edited_message": {
            "message_id": 1, "date": 1, "edit_date": 2, "from": {"id": int(tg)}, "chat": {"id": int(tg)},
            "location": {"latitude": 38.9, "longitude": -77.0, "live_period": 28800}}}
        request = SimpleNamespace(json=AsyncMock(return_value=update))
        result = await company_bots_v1.company_telegram_webhook(cid, request, SimpleNamespace(add_task=None), db=NoDb(),
                                                                 x_telegram_bot_api_secret_token="s3cr3t")
        assert result == {"ok": True, "ignored": "live_location_update"}

    async def chat(tg: str):
        for k in range(5):  # Iniciar, ubicacion, Pausa, ubicacion, Retomar...
            update = {"update_id": int(tg) * 100 + k, "message": {"message_id": k, "date": 1, "from": {"id": int(tg)},
                                                                  "chat": {"id": int(tg)}, "text": "/pausa"}}
            await company_bots_v1.process_company_telegram_update(cid, "field_operations", "T", update)

    jobs = [chat(tg) for tg in employees] + [live_edit(tg, n) for tg in employees for n in range(10)]
    random.shuffle(jobs)
    await asyncio.wait_for(asyncio.gather(*jobs), timeout=120)

    failures.assert_not_awaited()  # 0 errores: nadie recibio "No pudimos registrar"
    assert len(replies) == 40 * 5, "cada marcacion respondida"
    for tg, seen in order.items():
        assert seen == sorted(seen), f"orden del chat {tg}"
    assert live_seen_by_processor == [], "las 400 actualizaciones en vivo no llegaron al procesamiento"
    assert telegram_chat_queue.pending_chats() == 0, "sin candados acumulados"


@pytest.mark.asyncio
async def test_same_chat_burst_is_processed_one_at_a_time_in_arrival_order(maker, monkeypatch):
    running = {"now": 0, "max": 0}
    seen: list[int] = []

    async def processor(db, *, bot, token, update, send_replies):
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        await asyncio.sleep(0.01)
        seen.append(update["update_id"])
        running["now"] -= 1

    monkeypatch.setattr(company_bots_v1, "AsyncSessionLocal", maker)
    monkeypatch.setattr(company_bots_v1, "get_telegram_instance", AsyncMock(return_value=SimpleNamespace(bot_token_encrypted="x")))
    monkeypatch.setattr(company_bots_v1, "_process_telegram_update", processor)
    cid = str(uuid.uuid4())
    updates = [{"update_id": i, "message": {"message_id": i, "from": {"id": 7}, "chat": {"id": 7}, "text": "x"}} for i in range(1, 16)]
    await asyncio.gather(*[company_bots_v1.process_company_telegram_update(cid, "field_operations", "T", u) for u in updates])
    assert running["max"] == 1 and seen == list(range(1, 16))


# ------------------------------------------------------------ 3) recordatorio a los 3 minutos
@pytest.mark.asyncio
async def test_location_reminder_once_after_three_minutes(maker):
    cid = str(uuid.uuid4())
    async with maker() as db:
        await _company(db, cid, {"bot_punch_gps": True})
        late = await _employee(db, cid, "Tarde", tg="71")
        fresh = await _employee(db, cid, "Reciente", tg="72")
        await bot_punch_gps.set_pending(db, company_id=cid, telegram_user_id="71", username=None, employee_id=late, chat_id="71",
                                        language="en", command="/pausa", args="")
        await bot_punch_gps.set_pending(db, company_id=cid, telegram_user_id="72", username=None, employee_id=fresh, chat_id="72",
                                        language="es", command="/entrada", args="")
        await db.execute(text("UPDATE company_telegram_pending_actions SET updated_at = now() - interval '4 minutes' WHERE telegram_user_id = '71'"))
        await db.commit()
        mine = lambda rows: [r for r in rows if r["company_id"] == cid]  # noqa: E731
        due = mine(await bot_punch_gps.claim_due_reminders(db))
        assert [(d["telegram_user_id"], d["chat_id"], d["language"]) for d in due] == [("71", "71", "en")]
        assert mine(await bot_punch_gps.claim_due_reminders(db)) == [], "un solo recordatorio"
        later = datetime.now(timezone.utc) + timedelta(minutes=10)
        assert [d["telegram_user_id"] for d in mine(await bot_punch_gps.claim_due_reminders(db, later))] == ["72"]
        pending = await bot_punch_gps.get_pending(db, company_id=cid, telegram_user_id="71")
        assert pending["command"] == "/pausa", "la marcacion sigue pendiente: sin ubicacion no se registra"


@pytest.mark.asyncio
async def test_live_shared_mark_is_per_shift_and_consumed(maker):
    cid = str(uuid.uuid4())
    async with maker() as db:
        await _company(db, cid, {"bot_punch_gps": True})
        eid = await _employee(db, cid, "Ana", tg="81")
        start = datetime.now(timezone.utc) - timedelta(hours=3)
        assert await bot_punch_gps.take_live_shared(db, company_id=cid, telegram_user_id="81", since=start) is False
        await bot_punch_gps.mark_live_shared(db, company_id=cid, telegram_user_id="81", employee_id=eid)
        await db.commit()
        assert await bot_punch_gps.take_live_shared(db, company_id=cid, telegram_user_id="81", since=start) is True
        assert await bot_punch_gps.take_live_shared(db, company_id=cid, telegram_user_id="81", since=start) is False, "se consume"
        await bot_punch_gps.mark_live_shared(db, company_id=cid, telegram_user_id="81", employee_id=eid)
        await db.commit()
        next_shift = datetime.now(timezone.utc) + timedelta(hours=2)
        assert await bot_punch_gps.take_live_shared(db, company_id=cid, telegram_user_id="81", since=next_shift) is False, "de otro turno"


# ------------------------------------------------------------ 4) aviso de turno abierto
async def _alert_setup(maker):
    cid = str(uuid.uuid4())
    other = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    async with maker() as db:
        await _company(db, cid, {"open_shift_alert": True})
        await _company(db, other, {})
        va = (await db.execute(text("INSERT INTO work_locations (company_id, name, timezone) VALUES (CAST(:c AS uuid), 'Virginia', 'America/New_York') RETURNING id::text"), {"c": cid})).scalar()
        al = (await db.execute(text("INSERT INTO work_locations (company_id, name, timezone) VALUES (CAST(:c AS uuid), 'Alabama', 'America/Chicago') RETURNING id::text"), {"c": cid})).scalar()
        await db.commit()
        people = {
            "ana": await _employee(db, cid, "Ana", tg="101", place=va),
            "carl": await _employee(db, cid, "Carl", tg="103", place=al),
            "dan": await _employee(db, cid, "Dan", tg="104", place=va),
            "sup_va": await _employee(db, cid, "Sofía", role="supervisor", tg="201", place=va),
            "dir": await _employee(db, cid, "Diego", role="gerencia", tg="301"),
            "ext": await _employee(db, other, "Externo", tg="901"),
        }
        await _open_shift(db, cid, people["ana"], now - timedelta(hours=13))
        await _open_shift(db, cid, people["carl"], now - timedelta(hours=14), status="on_break")
        await _open_shift(db, cid, people["dan"], now - timedelta(hours=5))
        await _open_shift(db, other, people["ext"], now - timedelta(hours=30))
    return cid, other, people


@pytest.mark.asyncio
async def test_open_shift_over_12h_alerts_worker_and_place_supervisor_once(maker):
    cid, other, people = await _alert_setup(maker)
    sent: list[tuple[str, str]] = []

    async def send(chat_id, message):
        sent.append((chat_id, message))

    async def language_of(tg):
        return "en" if tg == "103" else "es"

    async with maker() as db:
        assert cid in await open_shift_alert.companies_on(db) and other not in await open_shift_alert.companies_on(db)
        assert await open_shift_alert.run_company(db, cid, send=send, language_of=language_of) == 2
        to = {}
        for chat, message in sent:
            to.setdefault(chat, []).append(message)
        assert set(to) == {"101", "201", "103", "301"}, "Ana + su supervisora; Carl (sin supervisor en Alabama) + el director"
        assert "Tu turno sigue abierto" in to["101"][0] and "13 h" in to["101"][0]
        assert "Your shift is still open" in to["103"][0], "en el idioma de cada colaborador"
        assert "👤 Ana" in to["201"][0] and "📍 Virginia" in to["201"][0] and "Inicio:" in to["201"][0]
        assert "👤 Carl" in to["301"][0] and "📍 Alabama" in to["301"][0]
        assert all(len(v) == 1 for v in to.values()), "un aviso por persona"
        assert "104" not in to, "Dan lleva 5 h"

        sent.clear()
        assert await open_shift_alert.run_company(db, cid, send=send, language_of=language_of) == 0
        assert sent == [], "sin repetir"
        status = (await db.execute(text("SELECT status FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"),
                                   {"e": people["ana"]})).scalar()
        assert status == "working", "nunca se cierra solo"

        await db.execute(text("INSERT INTO workforce_session_policy (company_id, alert_after_hours) VALUES (CAST(:c AS uuid), 4)"), {"c": cid})
        await db.commit()
        assert await open_shift_alert.run_company(db, cid, send=send, language_of=language_of) == 1, "limite configurable por empresa"
        assert {c for c, _ in sent} == {"104", "201"}


# ------------------------------------------------------------ 5) cerrar turno desde el portal
@pytest.mark.asyncio
async def test_manual_close_with_real_time_note_and_audit(maker):
    cid, _other, people = await _alert_setup(maker)
    now = datetime.now(timezone.utc)
    ana = people["ana"]
    async with maker() as db:
        shift = next(s for s in await open_shift_alert.open_shifts(db, cid) if s["employee_id"] == ana)
        started = shift["check_in_at"]
        for body, field in [
            ({"end_at": (started - timedelta(minutes=5)).isoformat(), "note": "olvidó finalizar"}, "end_at"),
            ({"end_at": (now + timedelta(hours=1)).isoformat(), "note": "olvidó finalizar"}, "end_at"),
            ({"end_at": (started + timedelta(hours=8)).isoformat(), "note": "  "}, "note"),
            ({"end_at": "2026-11-02T10:00", "note": "olvidó finalizar"}, "end_at"),
        ]:
            with pytest.raises(open_shift_alert.Invalid) as exc:
                await open_shift_alert.close_shift(db, cid, ana, body, actor="Sofía", actor_user_id=None)
            assert exc.value.field == field
            await db.rollback()

        end = started + timedelta(hours=8, minutes=30)
        result = await open_shift_alert.close_shift(db, cid, ana, {"end_at": end.isoformat(), "note": "Olvidó finalizar; salió 6:30 pm"},
                                                    actor="Sofía (supervisor)", actor_user_id=None)
        assert result["original_status"] == "working" and result["closed_by"] == "Sofía (supervisor)"
        row = (await db.execute(text("SELECT status, check_out_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"),
                                {"e": ana})).mappings().first()
        assert row["status"] == "checked_out" and row["check_out_at"] == end
        event = (await db.execute(text("""
            SELECT event_type, source_channel, occurred_at, payload_json FROM workforce_attendance_events
            WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)
        """), {"c": cid, "e": ana})).mappings().first()
        payload = event["payload_json"] if isinstance(event["payload_json"], dict) else json.loads(event["payload_json"])
        assert event["event_type"] == "check_out" and event["source_channel"] == "portal_manual_close" and event["occurred_at"] == end
        assert payload["note"] == "Olvidó finalizar; salió 6:30 pm" and payload["closed_by"] == "Sofía (supervisor)"
        audit = await open_shift_alert.recent_closes(db, cid)
        assert len(audit) == 1
        a = audit[0]
        assert a["closed_by"] == "Sofía (supervisor)" and a["original_status"] == "working" and a["note"].startswith("Olvidó")
        assert a["shift_started_at"] and a["end_at"] and a["closed_at"], "quién, cuándo, hora original y hora puesta"

        with pytest.raises(open_shift_alert.Invalid):
            await open_shift_alert.close_shift(db, cid, ana, {"end_at": end.isoformat(), "note": "otra vez"}, actor="x", actor_user_id=None)
        await db.rollback()
        with pytest.raises(open_shift_alert.Invalid):  # otra empresa: no lo encuentra
            await open_shift_alert.close_shift(db, _other, people["carl"], {"end_at": now.isoformat(), "note": "de otra empresa"},
                                               actor="x", actor_user_id=None)
        await db.rollback()
