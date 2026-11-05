"""Cierre administrativo de turnos viejos ya pagados, contra Postgres real. Datos inventados.

- Salida = ultima marca real del dia de la entrada; solo la entrada -> salida habitual, estimado.
- No entra a ninguna nomina ni sale como turno por confirmar; el tiempo cuenta en la referencia.
- Idempotente y con deshacer. Otra empresa, turnos abiertos, normales y confirmados, intactos.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import payroll as core  # noqa: E402
from app.services import company_locale  # noqa: E402
from app.services import reference_time as rt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BOG = ZoneInfo("America/Bogota")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


script = _load("velvet_cierre_administrativo", ROOT / "scripts" / "velvet_cierre_administrativo.py")
seedmod = _load("cierre_seed", ROOT / "tests" / "fixtures" / "reports_board_seed.py")
REFS = """
CREATE TABLE IF NOT EXISTS reference_work_sessions (id text PRIMARY KEY DEFAULT gen_random_uuid()::text, company_id text NOT NULL, employee_id text NOT NULL, employee_name text, telegram_user_id text,
  reference_id text, reference_name text NOT NULL, started_at timestamptz NOT NULL, ended_at timestamptz, duration_minutes numeric NOT NULL DEFAULT 0, status text NOT NULL DEFAULT 'closed',
  source_channel text NOT NULL DEFAULT 'telegram', created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS workforce_session_closures (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid NULL, employee_name varchar(180) NOT NULL DEFAULT '',
  source varchar(20) NOT NULL, session_ref varchar(64) NOT NULL, panel_type varchar(40) NOT NULL DEFAULT '', reason varchar(40) NOT NULL, started_at timestamptz NOT NULL, system_end_at timestamptz NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'pending', declared_end_at timestamptz NULL, declared_by_name varchar(180) NOT NULL DEFAULT '', declared_at timestamptz NULL, real_end_at timestamptz NULL,
  real_end_note varchar(300) NULL, confirmed_by_name varchar(180) NOT NULL DEFAULT '', confirmed_by_user_id varchar(64) NOT NULL DEFAULT '', confirmed_at timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_session_closure_ref UNIQUE (company_id, source, session_ref));
CREATE TABLE IF NOT EXISTS workforce_session_policy (company_id uuid PRIMARY KEY, cutoff_time varchar(5), alert_after_hours numeric)
"""


def bog(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=BOG)


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_cierre_"), cleanup_mode="stop")
    yield server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)


async def _session(db, cid, eid, name, ref, start, end):
    await db.execute(text("""INSERT INTO reference_work_sessions (company_id, employee_id, employee_name, reference_name, started_at, ended_at)
        VALUES (:c, :e, :n, :r, :s, :f)"""), {"c": cid, "e": eid, "n": name, "r": ref, "s": start, "f": end})


@pytest.fixture()
async def env(pg_url):
    company_locale.CURRENT_TZ.set(ZoneInfo("UTC"))  # pgserver no trae la base de zonas horarias
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await seedmod.create_schema(conn)
        await conn.execute(text("DROP TABLE IF EXISTS workforce_session_closures"))
        await conn.execute(text("DROP TABLE IF EXISTS workforce_session_policy"))
        for stmt in [s for s in REFS.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        cid = await seedmod.company(db, "Velvet", board=False)
        other = await seedmod.company(db, "Otra", board=False)
        place = await seedmod.place(db, cid, "Taller", "BO", "America/Bogota", 1)
        place2 = await seedmod.place(db, other, "Otro", "BO", "America/Bogota", 1)
        kris = await seedmod.person(db, cid, "KRIS", "K1", place)
        tata = await seedmod.person(db, cid, "TATA", "T1", place)
        ajena = await seedmod.person(db, other, "Ajena", "O1", place2)
        ev = seedmod.ev
        # Turnos normales: salida habitual de KRIS 18:00
        for day in ("2026-05-04", "2026-05-05", "2026-05-06"):
            await ev(db, cid, kris, "check_in", bog(day, "08:00"))
            await ev(db, cid, kris, "check_out", bog(day, "18:00"))
        # Olvidado: la ultima marca del dia es una pausa
        await ev(db, cid, kris, "check_in", bog("2026-06-05", "09:00"))
        await ev(db, cid, kris, "break_start", bog("2026-06-05", "17:00"))
        await ev(db, cid, kris, "check_out", bog("2026-06-06", "14:00"))
        await _session(db, cid, kris, "KRIS", "Dreamy", bog("2026-06-05", "09:00"), bog("2026-06-06", "14:00"))
        # Solo la entrada ese dia: salida habitual, estimado
        await ev(db, cid, kris, "check_in", bog("2026-07-03", "13:00"))
        await ev(db, cid, kris, "check_out", bog("2026-07-04", "14:00"))
        # Larga pero con salida real el mismo dia: se conserva
        await ev(db, cid, tata, "check_in", bog("2026-07-09", "07:00"))
        await ev(db, cid, tata, "check_out", bog("2026-07-09", "20:30"))
        # Despues del limite (como el 30-oct): retenido, pero no entra
        await ev(db, cid, tata, "check_in", bog("2026-10-20", "07:00"))
        await ev(db, cid, tata, "check_out", bog("2026-10-21", "07:00"))
        # Otra empresa con un turno largo
        await ev(db, other, ajena, "check_in", bog("2026-07-09", "07:00"))
        await ev(db, other, ajena, "check_out", bog("2026-07-10", "07:00"))
        await db.commit()
    yield SimpleNamespace(maker=maker, cid=cid, other=other, kris=kris, tata=tata)
    await engine.dispose()


async def _unverified(db, cid, start, end):
    snap = await core.calculate_period_snapshot(db, __import__("uuid").UUID(str(cid)), start, end)
    return snap.get("unverified_shifts") or [], snap


@pytest.mark.asyncio
async def test_tabla_aplica_nomina_referencia_idempotente_y_deshacer(env):
    async with env.maker() as db:
        items = await script.plan(db, env.cid)
        by_start = {x["start"].astimezone(BOG).strftime("%m-%d"): x for x in items}
        assert sorted(by_start) == ["06-05", "07-03", "07-09"], "solo los viejos retenidos; nada de octubre ni normales"
        assert by_start["06-05"]["end"] == bog("2026-06-05", "17:00") and by_start["06-05"]["mark"] == "break_start" and not by_start["06-05"]["estimated"]
        assert by_start["07-03"]["end"] == bog("2026-07-03", "18:00") and by_start["07-03"]["estimated"] and by_start["07-03"]["mark"] == "salida habitual"
        assert by_start["07-09"]["end"] == bog("2026-07-09", "20:30") and by_start["07-09"]["mark"] == "check_out"

        held, snap0 = await _unverified(db, env.cid, date(2026, 6, 1), date(2026, 7, 31))
        assert len(held) == 3, "antes salen por confirmar"
        minutes_before = {str(r["employee_id"]): int(r["regular_minutes"]) + int(r["extra_minutes"]) for r in snap0["rows"]}
        out_of_range = (await _unverified(db, env.cid, date(2026, 10, 1), date(2026, 10, 31)))[0]
        before_ref = rt.summarize([i for i in await rt.load(db, env.cid) if i["name"] == "Dreamy"], None, None)["dreamy"]
        assert before_ref["total_seconds"] == 0 and before_ref["unclosed"][0]["reason"] == rt.HOLD

        result = await script.apply_plan(db, items, env.cid, expected=3)
        assert result["applied"] == 3

        held, snap1 = await _unverified(db, env.cid, date(2026, 6, 1), date(2026, 7, 31))
        assert held == [], "ya no salen por confirmar"
        assert {str(r["employee_id"]): int(r["regular_minutes"]) + int(r["extra_minutes"]) for r in snap1["rows"]} == minutes_before, "no entran a ninguna nomina"
        assert (await _unverified(db, env.cid, date(2026, 10, 1), date(2026, 10, 31)))[0] == out_of_range, "lo de octubre sigue igual"

        after_ref = rt.summarize([i for i in await rt.load(db, env.cid) if i["name"] == "Dreamy"], None, None)["dreamy"]
        assert after_ref["unclosed"] == [] and after_ref["total_seconds"] == 8 * 3600, "cuenta en la referencia hasta la salida"

        notes = (await db.execute(text("SELECT status, reason, real_end_note, confirmed_by_name FROM workforce_session_closures WHERE company_id = CAST(:c AS uuid) ORDER BY started_at"), {"c": env.cid})).mappings().all()
        assert {n["status"] for n in notes} == {"admin_closed"} and {n["reason"] for n in notes} == {"cierre_administrativo"}
        assert script.NOTE in notes[0]["real_end_note"] and "hora estimada" not in notes[0]["real_end_note"]
        assert notes[1]["real_end_note"].endswith("hora estimada"), "el estimado queda marcado"

        # Idempotente: ya no hay nada que aplicar.
        assert await script.plan(db, env.cid) == []
        assert (await script.apply_plan(db, [], env.cid))["applied"] == 0

        # Marcas originales intactas.
        assert (await db.execute(text("SELECT count(*) FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid) AND event_type = 'check_out'"), {"c": env.cid})).scalar() == 7

        # La otra empresa no cambia.
        assert not (await db.execute(text("SELECT 1 FROM workforce_session_closures WHERE company_id = CAST(:c AS uuid)"), {"c": env.other})).first()
        assert len((await _unverified(db, env.other, date(2026, 7, 1), date(2026, 7, 31)))[0]) == 1

        # Deshacer: todo vuelve a por confirmar.
        assert (await script.undo(db, result["batch"], env.cid))["rows"] == 3
        assert len((await _unverified(db, env.cid, date(2026, 6, 1), date(2026, 7, 31)))[0]) == 3
        assert len(await script.plan(db, env.cid)) == 3


@pytest.mark.asyncio
async def test_no_aplica_si_el_numero_no_cuadra_o_hay_por_revisar(env):
    async with env.maker() as db:
        items = await script.plan(db, env.cid)
        with pytest.raises(ValueError):
            await script.apply_plan(db, items, env.cid)  # se esperaban 38
        with pytest.raises(ValueError):
            await script.apply_plan(db, [{**items[0], "review": True}], env.cid, expected=1)
        assert not (await db.execute(text("SELECT 1 FROM workforce_session_closures WHERE company_id = CAST(:c AS uuid)"), {"c": env.cid})).first()


def test_regla_de_la_salida_es_pura():
    start = bog("2026-07-03", "13:00").astimezone(timezone.utc)
    shift = {"start": start, "end": start + timedelta(days=1)}
    only_entry = [{"at": start, "kind": "check_in"}, {"at": start + timedelta(days=1), "kind": "check_out"}]
    assert script.proposal(shift, only_entry, {}, "x")["review"] is True, "sin salida habitual se revisa"
    late = bog("2026-07-03", "13:00").astimezone(BOG)
    assert script.proposal(shift, only_entry, {"x": late.hour * 60 - 60}, "x")["mark"] == "habitual antes de la entrada"
    assert script.proposal(shift, only_entry, {"x": 18 * 60}, "x")["estimated"] is True
    with_switch = only_entry + [{"at": start + timedelta(hours=2), "kind": "reference_switch"}]
    picked = script.proposal(shift, with_switch, {"x": 18 * 60}, "x")
    assert picked["end"] == start + timedelta(hours=2) and picked["estimated"] is False
