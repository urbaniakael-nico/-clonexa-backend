"""Corte diario (049D) contra Postgres REAL con asyncpg.

La prueba con base falsa no veia el error de produccion: en la consulta de la
entrada de asistencia, ":check_in_at + INTERVAL '1 minute'" hacia que asyncpg
tipara el parametro como interval y Postgres respondia "operator does not
exist: timestamp with time zone <= interval". Toda la empresa fallaba (rollback)
y el turno quedaba abierto para siempre (Urbania, desde el 6 de julio).

Aqui corre el codigo real del corte, con la migracion 021u tal cual, para dos
empresas: una con un turno de bot viejo y otra con un turno de mini panel.
Si pgserver no esta instalado (p. ej. en Railway) la prueba se salta.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import tempfile
import uuid
from datetime import datetime, timezone

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.services import session_cutoff as cutoff  # noqa: E402

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (id uuid PRIMARY KEY, name text NOT NULL, timezone text);
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES companies(id), full_name text NOT NULL);
CREATE TABLE IF NOT EXISTS company_users (id uuid PRIMARY KEY, full_name text);
CREATE TABLE IF NOT EXISTS mini_panel_work_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid, user_id uuid,
  panel_type varchar(40), status varchar(20), started_at timestamptz, active_started_at timestamptz,
  current_break_started_at timestamptz, ended_at timestamptz, active_seconds integer DEFAULT 0,
  break_seconds integer DEFAULT 0, closed_reason varchar(40) DEFAULT '', updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS workforce_attendance_status (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid NOT NULL,
  status varchar(30), last_event_type varchar(60), last_event_at timestamptz, check_in_at timestamptz,
  break_started_at timestamptz, check_out_at timestamptz, worked_minutes integer DEFAULT 0,
  break_minutes integer DEFAULT 0, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS workforce_attendance_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid,
  event_type varchar(60), event_label varchar(120), employee_name varchar(180), status_after varchar(30),
  source varchar(40), module_code varchar(60), source_channel varchar(60), detail text,
  payload_json jsonb DEFAULT '{}'::jsonb, metadata_json jsonb DEFAULT '{}'::jsonb,
  occurred_at timestamptz, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS clonexa_access_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, scope varchar(30), status varchar(20),
  created_at timestamptz DEFAULT now(), closed_at timestamptz, closed_reason text, last_seen_at timestamptz);
"""


def _migration_sql() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.021u_session_cutoff")
    module.op = Op()
    module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_cut_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in BASE_SCHEMA.split(";") if s.strip()] + _migration_sql():
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


def utc(text_value: str) -> datetime:
    return datetime.fromisoformat(text_value).replace(tzinfo=timezone.utc)


async def _seed(db) -> dict:
    ids = {k: str(uuid.uuid4()) for k in ("urb", "otra", "nico", "ana", "checkin", "panel")}
    await db.execute(text("TRUNCATE workforce_session_closures, workforce_session_policy, workforce_attendance_events, "
                          "workforce_attendance_status, mini_panel_work_sessions, clonexa_access_sessions, employees, companies CASCADE"))
    for key, name in (("urb", "URBANIA"), ("otra", "Otra")):
        await db.execute(text("INSERT INTO companies (id, name, timezone) VALUES (CAST(:i AS uuid), :n, 'America/Bogota')"),
                         {"i": ids[key], "n": name})
    await db.execute(text("INSERT INTO employees (id, company_id, full_name) VALUES (CAST(:e AS uuid), CAST(:c AS uuid), 'NICOLAS'),"
                          " (CAST(:a AS uuid), CAST(:o AS uuid), 'ANA')"),
                     {"e": ids["nico"], "c": ids["urb"], "a": ids["ana"], "o": ids["otra"]})
    # Turno de bot abierto desde el 6 de julio (12:49 hora Colombia), con su evento de entrada.
    checkin_at = utc("2026-07-06T17:49:20")
    await db.execute(text("""INSERT INTO workforce_attendance_events (id, company_id, employee_id, event_type, status_after, source, occurred_at, payload_json)
                             VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:e AS uuid), 'check_in', 'working', 'telegram', :at, '{}'::jsonb)"""),
                     {"id": ids["checkin"], "c": ids["urb"], "e": ids["nico"], "at": checkin_at})
    await db.execute(text("""INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at)
                             VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'working', 'break_end', :at, :at)"""),
                     {"c": ids["urb"], "e": ids["nico"], "at": checkin_at})
    # Otra empresa: turno de mini panel de anoche.
    await db.execute(text("""INSERT INTO mini_panel_work_sessions (id, company_id, employee_id, panel_type, status, started_at, active_started_at)
                             VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:e AS uuid), 'caja', 'active', :at, :at)"""),
                     {"id": ids["panel"], "c": ids["otra"], "e": ids["ana"], "at": utc("2026-10-10T22:00:00")})
    await db.commit()
    return ids


def test_cutoff_closes_old_bot_shift_and_other_companies(pg_url):
    async def run():
        engine = create_async_engine(pg_url)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as db:
                ids = await _seed(db)
                now = utc("2026-10-11T16:00:00")  # 11:00 en Bogota
                done = await cutoff.run_all_cutoffs(db, now)
                by_company = {d["company_id"]: d for d in done}
                # Las dos empresas cierran: ninguna falla.
                assert by_company[ids["urb"]]["attendance"] == 1
                assert by_company[ids["otra"]]["sessions"] == 1

                status = (await db.execute(text("SELECT status, check_out_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"),
                                           {"e": ids["nico"]})).mappings().first()
                assert status["status"] == "checked_out"
                out = (await db.execute(text("""SELECT occurred_at, source_channel, payload_json FROM workforce_attendance_events
                                                WHERE employee_id = CAST(:e AS uuid) AND event_type = 'check_out'"""),
                                        {"e": ids["nico"]})).mappings().all()
                assert len(out) == 1 and out[0]["source_channel"] == "system_cutoff"
                payload = out[0]["payload_json"]
                payload = json.loads(payload) if isinstance(payload, str) else payload
                assert payload["check_in_event_id"] == ids["checkin"]  # encontro su entrada (la consulta que fallaba)

                closures = (await db.execute(text("SELECT company_id::text AS c, source, reason, session_ref FROM workforce_session_closures ORDER BY source"))).mappings().all()
                assert {(r["c"], r["source"], r["reason"]) for r in closures} == {
                    (ids["urb"], "attendance", "corte_diario"), (ids["otra"], "mini_panel", "corte_diario")}

                # Idempotente: correr otra vez no cierra nada nuevo.
                again = await cutoff.run_all_cutoffs(db, now)
                assert all(not (d["sessions"] or d["attendance"]) for d in again)
        finally:
            await engine.dispose()

    asyncio.run(run())


MODULES_SCHEMA = """
CREATE TABLE IF NOT EXISTS modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text);
CREATE TABLE IF NOT EXISTS company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, module_id uuid,
  enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb)
"""


def test_cutoff_skips_companies_with_open_shift_alert(pg_url):
    """060C: con open_shift_alert (VOLTAGE) el turno nunca se cierra solo a las 00:00;
    otra empresa con el mismo turno viejo y sin el interruptor se corta como siempre."""
    async def run():
        engine = create_async_engine(pg_url)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as db:
                for stmt in [s for s in MODULES_SCHEMA.split(";") if s.strip()]:
                    await db.execute(text(stmt))
                await db.execute(text("TRUNCATE company_modules, modules"))
                ids = await _seed(db)  # urb: turno de bot abierto; otra: mini panel abierto
                mid = (await db.execute(text("INSERT INTO modules (code, name) VALUES ('workforce', 'Personal') RETURNING id::text"))).scalar()
                await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings) VALUES
                                         (CAST(:u AS uuid), CAST(:m AS uuid), true, '{"open_shift_alert": true, "bot_punch_gps": true}'::jsonb),
                                         (CAST(:o AS uuid), CAST(:m AS uuid), true, '{"open_shift_alert": false}'::jsonb)"""),
                                 {"u": ids["urb"], "o": ids["otra"], "m": mid})
                await db.commit()
                assert await cutoff.companies_without_cutoff(db) == {ids["urb"]}

                done = await cutoff.run_all_cutoffs(db, utc("2026-10-11T16:00:00"))
                by_company = {d["company_id"]: d for d in done}
                assert ids["urb"] not in by_company, "con open_shift_alert no hay corte de las 00:00"
                assert by_company[ids["otra"]]["sessions"] == 1, "las demás empresas siguen igual"
                status = (await db.execute(text("SELECT status, check_out_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"),
                                           {"e": ids["nico"]})).mappings().first()
                assert status["status"] == "working" and status["check_out_at"] is None, "el turno sigue abierto"
                closed = (await db.execute(text("SELECT count(*) FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid) AND event_type = 'check_out'"),
                                           {"c": ids["urb"]})).scalar()
                assert closed == 0
                await db.execute(text("DROP TABLE company_modules"))
                await db.execute(text("DROP TABLE modules"))
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(run())
