"""Nomina v2 contra Postgres REAL con asyncpg (no una base falsa).

- period_activity trae SOLO lo de la empresa pedida: GPS, referencias (con
  company_id de texto), sesiones de mini panel y pedidos por persona
  (mesero / cocina / caja), y nunca los de otra empresa ni fuera del periodo.
- Confirmar salida con nota: migraciones 021u y 024f tal cual; la nota se
  guarda en el mismo UPDATE y el trigger sigue bloqueando un segundo cambio.
Si pgserver no esta instalado (p. ej. en Railway) la prueba se salta.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import tempfile
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import payroll_v2  # noqa: E402
from app.api.v1.endpoints import workforce_sessions  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (id uuid PRIMARY KEY, name text NOT NULL, timezone text);
CREATE TABLE IF NOT EXISTS modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, is_active boolean DEFAULT true);
CREATE TABLE IF NOT EXISTS company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, module_id uuid, enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb);
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY, company_id uuid, full_name text, document_id varchar(80));
CREATE TABLE IF NOT EXISTS workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, employee_id uuid, event_type varchar(60),
  detail text, payload_json jsonb DEFAULT '{}'::jsonb, occurred_at timestamptz, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS reference_work_sessions (id text PRIMARY KEY, company_id text, employee_id text, reference_name text, started_at timestamptz, ended_at timestamptz,
  duration_minutes numeric, status text);
CREATE TABLE IF NOT EXISTS reference_production_closures (id text PRIMARY KEY, company_id text, employee_id text, reference_name text, size text, quantity_finished integer, closed_at timestamptz);
CREATE TABLE IF NOT EXISTS mini_panel_work_sessions (id uuid PRIMARY KEY, company_id uuid, user_id uuid, employee_id uuid, panel_type text, status text,
  location_label text, started_at timestamptz, ended_at timestamptz, active_seconds integer DEFAULT 0, break_seconds integer DEFAULT 0, closed_reason text DEFAULT '');
CREATE TABLE IF NOT EXISTS hospitality_orders (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, status varchar(40), total numeric, metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz, closed_at timestamptz, cancelled_at timestamptz);
"""


def _migrations() -> list[str]:
    out: list[str] = []

    class Op:
        def execute(self, sql):
            out.append(str(sql))

    for name in ("021u_session_cutoff", "024f_closure_note"):
        module = importlib.import_module(f"migrations.versions.{name}")
        module.op = Op()
        module.upgrade()
    return [s for s in out if "mini_panel_work_sessions" not in s or "CREATE" in s]


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_pay2_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in SCHEMA.split(";") if s.strip()] + _migrations():
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_activity_returns_only_that_company_and_period(pg_url):
    async def run():
        engine = create_async_engine(pg_url)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as db:
                a, b = str(uuid.uuid4()), str(uuid.uuid4())
                ea, eb, waiter, cook = (str(uuid.uuid4()) for _ in range(4))
                s_mesero, s_cocina, s_otra = (str(uuid.uuid4()) for _ in range(3))
                for cid in (a, b):
                    await db.execute(text("INSERT INTO companies (id, name) VALUES (CAST(:c AS uuid), 'x')"), {"c": cid})
                for code in ("gps", "references", "waiter_ordering", "payroll"):
                    await db.execute(text("INSERT INTO modules (code) VALUES (:c)"), {"c": code})
                    for cid in (a, b):
                        await db.execute(text("INSERT INTO company_modules (company_id, module_id) SELECT CAST(:c AS uuid), id FROM modules WHERE code = :m"), {"c": cid, "m": code})
                await db.execute(text("INSERT INTO employees VALUES (CAST(:e AS uuid), CAST(:c AS uuid), 'Ana', '1020'), (CAST(:f AS uuid), CAST(:d AS uuid), 'Otra', '999')"),
                                 {"e": ea, "c": a, "f": eb, "d": b})
                gps = {"latitude": 4.6, "longitude": -74.1, "matched_perimeter_name": "EDIFICIO 1", "gps_status_label": "Dentro"}
                for cid, emp, when in ((a, ea, "2026-10-05T13:00:00"), (b, eb, "2026-10-05T13:00:00"), (a, ea, "2026-11-30T13:00:00")):
                    await db.execute(text("INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, payload_json, occurred_at) VALUES "
                                          "(CAST(:c AS uuid), CAST(:e AS uuid), 'gps_location', CAST(:p AS jsonb), :t)"),
                                     {"c": cid, "e": emp, "p": json.dumps(gps), "t": utc(when)})
                await db.execute(text("INSERT INTO reference_work_sessions VALUES ('r1', :a, :ea, 'PANT SET', :s, :e, 120, 'closed'), ('r2', :b, :eb, 'DE OTRA', :s, :e, 60, 'closed')"),
                                 {"a": a, "b": b, "ea": ea, "eb": eb, "s": utc("2026-10-05T12:00:00"), "e": utc("2026-10-05T14:00:00")})
                await db.execute(text("INSERT INTO reference_production_closures VALUES ('c1', :a, :ea, 'PANT SET', '10', 30, :t), ('c2', :b, :eb, 'DE OTRA', '8', 5, :t)"),
                                 {"a": a, "b": b, "ea": ea, "eb": eb, "t": utc("2026-10-05T14:00:00")})
                for sid, cid, user, panel in ((s_mesero, a, waiter, "mesero"), (s_cocina, a, cook, "cocina"), (s_otra, b, waiter, "mesero")):
                    await db.execute(text("INSERT INTO mini_panel_work_sessions (id, company_id, user_id, employee_id, panel_type, status, started_at, ended_at) VALUES "
                                          "(CAST(:s AS uuid), CAST(:c AS uuid), CAST(:u AS uuid), CAST(:e AS uuid), :p, 'finished', :st, :en)"),
                                     {"s": sid, "c": cid, "u": user, "e": ea if cid == a else eb, "p": panel, "st": utc("2026-10-05T16:00:00"), "en": utc("2026-10-06T01:00:00")})
                orders = [
                    (a, {"waiter": {"id": waiter}, "kitchen": {"ready_by": {"id": cook}, "ready_at": "2026-10-05T18:00:00+00:00"}}, 50000, None),
                    (a, {"waiter": {"id": waiter}}, 20000, None),
                    (a, {"waiter": {"id": waiter}}, 99999, utc("2026-10-05T18:30:00")),  # anulado: no cuenta
                    (b, {"waiter": {"id": waiter}}, 70000, None),  # otra empresa: no cuenta
                ]
                for cid, meta, total, cancelled in orders:
                    await db.execute(text("INSERT INTO hospitality_orders (company_id, status, total, metadata, created_at, cancelled_at) VALUES "
                                          "(CAST(:c AS uuid), 'closed', :t, CAST(:m AS jsonb), :at, :x)"),
                                     {"c": cid, "t": total, "m": json.dumps(meta), "at": utc("2026-10-05T17:00:00"), "x": cancelled})
                await db.commit()

                out = await payroll_v2.period_activity(db, uuid.UUID(a), date(2026, 10, 1), date(2026, 10, 15))
                dump = json.dumps(out)
                assert "DE OTRA" not in dump and eb not in dump and s_otra not in dump and "999" not in dump, "nada de la otra empresa"
                assert out["documents"] == {ea: "1020"}
                assert [g["perimeter"] for g in out["gps"][ea]] == ["EDIFICIO 1"], "solo el del periodo"
                assert out["references"][ea][0]["reference"] == "PANT SET" and out["reference_closures"][ea][0]["quantity"] == 30
                assert out["modules"] == {"gps": True, "references": True, "panels": True, "orders": True}
                assert out["panels"][s_mesero]["orders_taken"] == 2 and out["panels"][s_mesero]["orders_taken_total"] == 70000.0
                assert out["panels"][s_cocina]["orders_ready"] == 1 and out["panels"][s_cocina]["orders_taken"] == 0
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_confirm_with_note_writes_once_with_real_migrations(pg_url):
    async def run():
        engine = create_async_engine(pg_url)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as db:
                cid = uuid.uuid4()
                await db.execute(text("INSERT INTO companies (id, name, timezone) VALUES (CAST(:c AS uuid), 'x', 'America/Bogota')"), {"c": str(cid)})
                closure = (await db.execute(text("""INSERT INTO workforce_session_closures (company_id, employee_name, source, session_ref, reason, started_at, system_end_at)
                    VALUES (CAST(:c AS uuid), 'Ana', 'attendance', 'ref-1', 'corte_diario', :s, :e) RETURNING id::text"""),
                    {"c": str(cid), "s": utc("2026-10-05T12:00:00"), "e": utc("2026-10-06T05:00:00")})).scalar()
                await db.commit()
                actor = {"name": "Admin", "id": "u1"}
                res = await workforce_sessions.confirm_real_end(cid, {"closure_id": closure, "real_end_at": "2026-10-05T17:30", "note": "  Salió   a las 5:30  "}, db, actor)
                assert res["status"] == "confirmed"
                row = (await db.execute(text("SELECT real_end_note, real_end_at FROM workforce_session_closures WHERE id = CAST(:i AS uuid)"), {"i": closure})).mappings().first()
                assert row["real_end_note"] == "Salió a las 5:30"
                assert row["real_end_at"] == utc("2026-10-05T22:30:00"), "hora local de la empresa"
                with pytest.raises(Exception) as second:
                    await workforce_sessions.confirm_real_end(cid, {"closure_id": closure, "real_end_at": "2026-10-05T18:00", "note": "otra"}, db, actor)
                assert getattr(second.value, "status_code", None) == 409, "una sola vez"
        finally:
            await engine.dispose()

    asyncio.run(run())
