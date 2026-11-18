"""Ajuste de Virginia 01-14 nov 2026 (tabla del supervisor, 11 personas) contra Postgres REAL. Datos
inventados con la forma de produccion: PRUEBA solo lee y cuadra (1024 h = 760 + 264 OT, semanas
domingo a sabado); aplicar deja la tabla exacta, cierra un turno abierto viejo y quita los por
confirmar, es idempotente, se deshace, y no toca a otras personas de Virginia, Alabama, otra empresa
ni nada desde el domingo 15. Nombres con alias (Villca, Kevin, Yesenia, Vazquez) y un segundo
"Luis Rodriguez" que NO es el de la tabla. Si pgserver no esta, se salta."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.services import us_payroll  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ET, CT = ZoneInfo("America/New_York"), ZoneInfo("America/Chicago")
NOW = datetime(2026, 11, 18, 22, 0, tzinfo=timezone.utc)
COMPANY = {"week_start_day": "monday", "week_start_time": "00:00", "overtime_after_minutes": 2400, "overtime_factor": 1.5,
           "pay_period": {"type": "biweekly", "anchor": "2026-11-02"}}
VA_RULES = {"week_start_day": "sunday", "week_start_time": "00:00", "pay_period": {"type": "biweekly", "anchor": "2026-11-01"}}
NAMES = {"Helen Omonte": "Helen Villca", "Kewin Rios": "Kevin Mauricio Rios Lindo", "Jose Cardenas": "José Julián Cárdenas Beltrán",
         "Luis Rodriguez": "Luis Vladimir Rodriguez Ortiz", "Kerim Munoz": "Kerim Gigliola Muñoz Rojas", "Roberto Camacho": "Roberto Carlos Camacho Rondal",
         "Mery Rondal": "Mery Rondal Rocha", "Yessenia Ortiz": "Yesenia Ortiz Garcia", "Jesus Castellon": "Jesús Castellón Escobar",
         "Jhoselin Vasquez": "Jhoselin Vazquez Mercado", "Jacob Lopez": "Jacob Cameron Lopez"}
EXTRA = """
CREATE TABLE workforce_attendance_status (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid NOT NULL, status varchar(40) NOT NULL DEFAULT 'not_started',
  last_event_type varchar(80), last_event_at timestamptz, check_in_at timestamptz, break_started_at timestamptz, check_out_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE (company_id, employee_id));
CREATE TABLE gps_tracking_sessions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid NOT NULL, status varchar(40) NOT NULL DEFAULT 'active', ended_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE company_telegram_pending_actions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, telegram_user_id varchar(120) NOT NULL DEFAULT 'x', employee_id uuid, action varchar(80) NOT NULL,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb, expires_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE admin_audit_log (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), at timestamptz NOT NULL, actor text, ip text, method text, path text, company_id uuid, status_code integer, surface text, detail jsonb)
"""


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


script = _load("ajuste_virginia_01_14", ROOT / "scripts" / "ajuste_virginia_01_14_nov_2026.py")
seedmod = _load("ajuste_seed_va", ROOT / "tests" / "fixtures" / "reports_board_seed.py")


def _migration() -> list[str]:
    module = _load("m025a_va", ROOT / "migrations" / "versions" / "025a_attendance_adjustments.py")
    out: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: out.append(str(sql)))
    module.upgrade()
    return out


def et(day: int, hhmm: str, tz=ET) -> datetime:
    return datetime.fromisoformat(f"2026-11-{day:02d}T{hhmm}:00").replace(tzinfo=tz)


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_ajuste_va_"), cleanup_mode="stop")
    yield server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)


async def _day(db, cid, eid, day, start, end, pause=None, tz=ET):
    await seedmod.ev(db, cid, eid, "check_in", et(day, start, tz), point=(38.9, -77.0))
    if pause:
        await seedmod.ev(db, cid, eid, "break_start", et(day, pause[0], tz), point=(38.9, -77.0))
        await seedmod.ev(db, cid, eid, "break_end", et(day, pause[1], tz), point=(38.9, -77.0))
    await seedmod.ev(db, cid, eid, "check_out", et(day, end, tz), point=(38.9, -77.0), detail="Resumen del bot")


@pytest.fixture()
async def env(pg_url):
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await seedmod.create_schema(conn)
        for stmt in [s for s in EXTRA.split(";") if s.strip()] + _migration():
            await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        cid = await seedmod.company(db, "VOLTAGE", board=True)
        other = await seedmod.company(db, "Otra", board=False)
        va = await seedmod.place(db, cid, "Virginia", "VA", "America/New_York", 1)
        al = await seedmod.place(db, cid, "Alabama", "AL", "America/Chicago", 2)
        other_va = await seedmod.place(db, other, "Virginia", "VA", "America/New_York", 1)
        for company, rules in ((cid, {**COMPANY, "places": {va: VA_RULES}}), (other, {**COMPANY, "places": {other_va: VA_RULES}})):
            await db.execute(text("""UPDATE company_modules SET settings = settings || CAST(:s AS jsonb)
                                     WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE code = 'payroll')"""),
                             {"c": company, "s": json.dumps({"us_payroll_rules": rules})})
        await db.execute(text("INSERT INTO workforce_session_policy (company_id, alert_after_hours) VALUES (CAST(:c AS uuid), 15)"), {"c": cid})
        ids = SimpleNamespace(cid=cid, other=other, people={})
        for i, (label, name) in enumerate(NAMES.items()):
            ids.people[label] = await seedmod.person(db, cid, name, f"V{i}", va)
        ids.luis2 = await seedmod.person(db, cid, "luis Miguel Rodriguez Aponte", "V90", va)
        ids.otro_va = await seedmod.person(db, cid, "Otra Persona Virginia", "V91", va)
        ids.ana = await seedmod.person(db, cid, "Ana Alabama", "A1", al)
        ids.foreign = await seedmod.person(db, other, "Kewin Rios", "O1", other_va)
        kewin, kerim, jacob = ids.people["Kewin Rios"], ids.people["Kerim Munoz"], ids.people["Jacob Lopez"]
        # Bot: dias al azar, un por confirmar (16 h) de Kewin el 03, un sabado 07 que la tabla deja vacio a Jacob,
        # Kerim con un turno ABIERTO desde el jueves 12 y un turno real del domingo 15 que no se toca.
        for d in (2, 4, 5, 9):
            await _day(db, cid, kewin, d, "06:47", "18:02", ("12:10", "12:40"))
        await _day(db, cid, kewin, 3, "06:00", "22:30")
        await _day(db, cid, jacob, 7, "08:00", "14:00")
        await seedmod.ev(db, cid, kerim, "check_in", et(12, "07:05"))
        await db.execute(text("""INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at)
                                 VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'working', 'check_in', :i, :i)"""), {"c": cid, "e": kerim, "i": et(12, "07:05")})
        await db.execute(text("INSERT INTO gps_tracking_sessions (company_id, employee_id) VALUES (CAST(:c AS uuid), CAST(:e AS uuid))"), {"c": cid, "e": kerim})
        await db.execute(text("""INSERT INTO company_telegram_pending_actions (company_id, employee_id, action, expires_at)
                                 VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'end_shift_summary', :x)"""), {"c": cid, "e": kerim, "x": datetime(2030, 1, 1, tzinfo=timezone.utc)})
        await _day(db, cid, jacob, 15, "07:00", "15:30", ("12:00", "12:30"))
        await db.execute(text("""INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at, check_out_at)
                                 VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'checked_out', 'check_out', :o, :i, :o)"""), {"c": cid, "e": jacob, "i": et(15, "07:00"), "o": et(15, "15:30")})
        # Los que no entran
        for who, company, tz in ((ids.otro_va, cid, ET), (ids.luis2, cid, ET), (ids.ana, cid, CT), (ids.foreign, other, ET)):
            await _day(db, company, who, 9, "07:00", "17:00", tz=tz)
        await db.commit()
    yield SimpleNamespace(maker=maker, **vars(ids))
    await engine.dispose()


async def _rows(db, cid, eid=None):
    return [dict(r) for r in (await db.execute(text("""
        SELECT id::text AS id, employee_id::text AS employee_id, event_type, event_label, status_after, source_channel, source_ref, payload_json, occurred_at
        FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid) AND (:e = '' OR employee_id::text = :e) ORDER BY occurred_at, id
    """), {"c": cid, "e": eid or ""})).mappings().all()]


async def test_prueba_solo_lee_encuentra_alias_y_cuadra(env):
    async with env.maker() as db:
        before = await _rows(db, env.cid)
        r = await script.report(db, env.cid)
        assert await _rows(db, env.cid) == before, "PRUEBA no escribe"
        assert r["count"] == 11 and r["matches_expected"] is True
        by = {x["label"]: x for x in r["people"]}
        assert by["Helen Omonte"]["name"] == "Helen Villca" and by["Kewin Rios"]["name"] == "Kevin Mauricio Rios Lindo"
        assert by["Luis Rodriguez"]["name"] == "Luis Vladimir Rodriguez Ortiz", "el otro Luis Rodriguez no es el de la tabla"
        assert sorted(r["luis_rodriguez_records"]) == ["Luis Vladimir Rodriguez Ortiz", "luis Miguel Rodriguez Aponte"]
        assert by["Kewin Rios"]["after"] == (132 * 60, 80 * 60, 52 * 60) and by["Kewin Rios"]["weeks_after"] == [("2026-11-01", 72 * 60, 32 * 60), ("2026-11-08", 60 * 60, 20 * 60)]
        assert by["Kerim Munoz"]["open_old_shift"] is True and by["Jacob Lopez"]["days_to_empty"] == 1
        assert by["Jacob Lopez"]["sunday_15_payable"] == 480, "se informa quien tiene horas el domingo 15"
        assert [h["employee_name"] for h in r["held_in_range"]] == ["Kevin Mauricio Rios Lindo"]
        assert r["totals"]["after"] == [1024 * 60, 760 * 60, 264 * 60]
        assert [o["name"] for o in r["other_virginia_with_hours"]] == ["luis Miguel Rodriguez Aponte", "Otra Persona Virginia"]


async def test_aplicar_deja_la_tabla_exacta_es_idempotente_y_cierra_el_abierto(env):
    async with env.maker() as db:
        first = await script.apply(db, env.cid, now=NOW, expected=11)
        assert first["people"] == 11 and first["open_shifts_closed"] == 1 and first["bot_steps_expired"] == 1
        rows = await _rows(db, env.cid)
        second = await script.apply(db, env.cid, now=NOW, expected=11)
        assert second["person_days"] == 0 and await _rows(db, env.cid) == rows, "dos veces da lo mismo"
        v = await script.verify(db, env.cid)
        assert v["wrong"] == [] and v["total_01_14"] == [1024 * 60, 760 * 60, 264 * 60] and v["virginia_week_start"] == "sunday"
        fig = await script.figures(db, env.cid)
        assert not [h for h in fig["_held"] if h["employee_id"] == env.people["Kewin Rios"]], "el por confirmar quedo reemplazado"
        kerim = env.people["Kerim Munoz"]
        new = [r for r in await _rows(db, env.cid, kerim) if r["source_channel"] == "ajuste_masivo"]
        friday = [(r["event_type"], r["occurred_at"].astimezone(ET).strftime("%H:%M")) for r in new if r["occurred_at"].astimezone(ET).day == 6]
        assert friday == [("check_in", "07:00"), ("check_out", "09:00")], "dia de 2 h sin almuerzo"
        st = (await db.execute(text("SELECT status, check_out_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": kerim})).mappings().first()
        assert st["status"] == "checked_out" and st["check_out_at"] == et(13, "15:30"), "ya no queda un turno abierto viejo"
        assert (await db.execute(text("SELECT status FROM gps_tracking_sessions WHERE employee_id = CAST(:e AS uuid)"), {"e": kerim})).scalar() == "closed"
        audit = (await db.execute(text("SELECT reason FROM workforce_attendance_adjustments WHERE batch = :b LIMIT 1"), {"b": script.BATCH})).scalar()
        assert "ajuste Virginia tabla supervisor 01-14/11" in audit


async def test_no_toca_a_otros_ni_desde_el_15(env):
    async with env.maker() as db:
        protected = {k: await _rows(db, c, getattr(env, k)) for k, c in (("otro_va", env.cid), ("luis2", env.cid), ("ana", env.cid), ("foreign", env.other))}
        jacob = env.people["Jacob Lopez"]
        sunday = [r for r in await _rows(db, env.cid, jacob) if r["occurred_at"] >= et(15, "00:00")]
        await script.apply(db, env.cid, now=NOW)
        for key, company in (("otro_va", env.cid), ("luis2", env.cid), ("ana", env.cid), ("foreign", env.other)):
            assert await _rows(db, company, getattr(env, key)) == protected[key], key
        assert [r for r in await _rows(db, env.cid, jacob) if r["occurred_at"] >= et(15, "00:00")] == sunday
        st = (await db.execute(text("SELECT check_in_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": jacob})).scalar()
        assert st == et(15, "07:00"), "su estado del turno real del 15 no se pisa"
        nxt = await script.figures(db, env.cid, date(2026, 11, 15), date(2026, 11, 28))
        assert nxt[jacob]["payable"] == 480


async def test_deshacer_deja_todo_como_antes(env):
    async with env.maker() as db:
        rows0 = {r["id"]: (r["event_type"], r["status_after"]) for r in await _rows(db, env.cid)}
        fig0 = await script.figures(db, env.cid)
        await script.apply(db, env.cid, now=NOW)
        out = await script.undo(db, env.cid)
        assert out["person_days"] > 0 and out["status_not_restored"] == 0
        rows1 = {r["id"]: (r["event_type"], r["status_after"]) for r in await _rows(db, env.cid)}
        assert all(rows1[k] == v for k, v in rows0.items())
        fig1 = await script.figures(db, env.cid)
        assert {k: fig1[k]["payable"] for k in fig0 if not k.startswith("_")} == {k: fig0[k]["payable"] for k in fig0 if not k.startswith("_")}
        kerim = env.people["Kerim Munoz"]
        st = (await db.execute(text("SELECT status, check_in_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": kerim})).mappings().first()
        assert st["status"] == "working" and st["check_in_at"] == et(12, "07:05")
        assert (await db.execute(text("SELECT status FROM gps_tracking_sessions WHERE employee_id = CAST(:e AS uuid)"), {"e": kerim})).scalar() == "active"
        assert (await script.undo(db, env.cid))["person_days"] == 0


async def test_para_si_un_nombre_falta_o_se_duplica_o_cambia_el_numero(env):
    async with env.maker() as db:
        with pytest.raises(script.NeedsReview):
            await script.apply(db, env.cid, now=NOW, expected=10)
        with pytest.raises(script.NeedsReview):
            await script.apply(db, env.cid, now=et(14, "22:00"))
        await db.rollback()
        await seedmod.person(db, env.cid, "Mery Rondal", "V99", (await db.execute(text("SELECT id::text FROM work_locations WHERE company_id = CAST(:c AS uuid) AND name = 'Virginia'"), {"c": env.cid})).scalar())
        await db.commit()
        with pytest.raises(script.NeedsReview, match="Mery Rondal"):
            await script.plan(db, env.cid)
