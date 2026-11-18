"""Segunda parte del ajuste de Virginia (lote virginia-2026-11-01-14-b) contra Postgres REAL. Datos
inventados: 4 personas mas por tabla (entrada 6:00), el resto de Virginia en 0, turnos sin cerrar del
primer corte quitados en toda la empresa (Virginia 01-14 ET, Alabama 02-15 CT) sin tocar el corte
actual; idempotente, --undo propio, no toca el lote anterior ni otras empresas. Sin pgserver, se salta."""
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

ROOT = Path(__file__).resolve().parents[1]
ET, CT = ZoneInfo("America/New_York"), ZoneInfo("America/Chicago")
NOW = datetime(2026, 11, 18, 22, 0, tzinfo=timezone.utc)
COMPANY = {"week_start_day": "monday", "week_start_time": "00:00", "overtime_after_minutes": 2400, "overtime_factor": 1.5,
           "pay_period": {"type": "biweekly", "anchor": "2026-11-02"}}
VA_RULES = {"week_start_day": "sunday", "week_start_time": "00:00", "pay_period": {"type": "biweekly", "anchor": "2026-11-01"}}
FIRST = ["Helen Omonte Villca", "Kewin Rios", "Jose Cardenas", "Luis Vladimir Rodriguez Ortiz", "Kerim Munoz", "Roberto Camacho",
         "Mery Rondal", "Yessenia Ortiz", "Jesus Castellon", "Jhoselin Vasquez", "Jacob Lopez"]
NEW = {"diego": "Diego Alejandro Ruiz Chavez", "jaime": "Jaime David Marca Rioz", "noe": "Noe Daniel Ponce Mamani", "mijail": "Mijail Navor Illanes Salas"}
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


part_a = _load("ajuste_virginia_01_14_parte1", ROOT / "scripts" / "ajuste_virginia_01_14_nov_2026.py")
script = _load("ajuste_virginia_01_14_b", ROOT / "scripts" / "ajuste_virginia_01_14_nov_2026_b.py")
seedmod = _load("ajuste_seed_vab", ROOT / "tests" / "fixtures" / "reports_board_seed.py")


def _migration() -> list[str]:
    module = _load("m025a_vab", ROOT / "migrations" / "versions" / "025a_attendance_adjustments.py")
    out: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: out.append(str(sql)))
    module.upgrade()
    return out


def at(day: int, hhmm: str, tz=ET) -> datetime:
    return datetime.fromisoformat(f"2026-11-{day:02d}T{hhmm}:00").replace(tzinfo=tz)


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_ajuste_vab_"), cleanup_mode="stop")
    yield server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)


async def _day(db, cid, eid, day, start, end, tz=ET, pause=None):
    await seedmod.ev(db, cid, eid, "check_in", at(day, start, tz))
    if pause:
        await seedmod.ev(db, cid, eid, "break_start", at(day, pause[0], tz))
        await seedmod.ev(db, cid, eid, "break_end", at(day, pause[1], tz))
    await seedmod.ev(db, cid, eid, "check_out", at(day, end, tz))


async def _status(db, cid, eid, status, check_in):
    await db.execute(text("""INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at)
                             VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :s, 'check_in', :i, :i)"""), {"c": cid, "e": eid, "s": status, "i": check_in})


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
        ids = SimpleNamespace(cid=cid, other=other)
        ids.first = [await seedmod.person(db, cid, n, f"F{i}", va) for i, n in enumerate(FIRST)]
        for key, name in NEW.items():
            setattr(ids, key, await seedmod.person(db, cid, name, key, va))
        ids.oscar = await seedmod.person(db, cid, "Oscar Diaz Vargas", "Z1", va)
        ids.nico = await seedmod.person(db, cid, "NICOLAS GOMEZ", "Z2", va)
        ids.ana = await seedmod.person(db, cid, "Ana Alabama", "A1", al)
        ids.beto = await seedmod.person(db, cid, "Beto Alabama", "A2", al)
        ids.foreign = await seedmod.person(db, other, "Oscar Diaz Vargas", "O1", other_va)
        await db.commit()
        # primera parte ya aplicada (las 11)
        await part_a.apply(db, cid, now=NOW)
        # bot: Diego algunos dias; Mijail un por confirmar (16 h) el 05; Oscar 2 dias; Nicolas una entrada sin salida
        for d in (2, 3, 9):
            await _day(db, cid, ids.diego, d, "06:20", "17:10", pause=("12:00", "12:30"))
        await _day(db, cid, ids.mijail, 5, "06:00", "22:30")
        await _day(db, cid, ids.oscar, 4, "07:00", "19:00")
        await _day(db, cid, ids.oscar, 12, "07:00", "20:51")
        await seedmod.ev(db, cid, ids.nico, "check_in", at(10, "09:00"))
        # Alabama: un turno normal del 15 (se queda), uno abierto del 15 (sale) y uno abierto del 16 (corte actual: se queda)
        await _day(db, cid, ids.ana, 15, "08:00", "12:00", tz=CT)
        await seedmod.ev(db, cid, ids.beto, "check_in", at(15, "07:00", CT))
        await _status(db, cid, ids.beto, "working", at(15, "07:00", CT))
        await db.execute(text("INSERT INTO gps_tracking_sessions (company_id, employee_id) VALUES (CAST(:c AS uuid), CAST(:e AS uuid))"), {"c": cid, "e": ids.beto})
        await seedmod.ev(db, cid, ids.ana, "check_in", at(16, "06:00", CT))
        await _status(db, cid, ids.ana, "working", at(16, "06:00", CT))
        # desde el 15 en Virginia: real del bot (no se toca)
        await _day(db, cid, ids.diego, 15, "06:00", "14:30", pause=("12:00", "12:30"))
        await _day(db, cid, ids.foreign, 4, "07:00", "19:00")
        await db.commit()
    yield SimpleNamespace(maker=maker, **vars(ids))
    await engine.dispose()


async def _rows(db, cid, eid=None):
    return [dict(r) for r in (await db.execute(text("""
        SELECT id::text AS id, employee_id::text AS employee_id, event_type, status_after, source_channel, source_ref, occurred_at
        FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid) AND (:e = '' OR employee_id::text = :e) ORDER BY occurred_at, id
    """), {"c": cid, "e": eid or ""})).mappings().all()]


async def test_prueba_solo_lee_y_cuadra_parcial(env):
    async with env.maker() as db:
        before = await _rows(db, env.cid)
        r = await script.report(db, env.cid)
        assert await _rows(db, env.cid) == before
        by = {x["label"]: x for x in r["new"]}
        assert by["Diego Ruiz"]["after"] == (6480, 4800, 1680) and by["Diego Ruiz"]["weeks_after"] == [3600, 2880]
        assert by["Jaime Marca"]["after"] == (1440, 1440, 0) and by["Jaime Marca"]["weeks_after"] == [1440]
        assert by["Noe Ponce"]["after"] == (5035, 4800, 235) and by["Mijail Illanes"]["after"] == (5400, 4680, 720)
        assert all(x["ok"] for x in r["new"])
        assert r["first_part"] == script.EXPECTED_FIRST_PART and r["virginia_after"] == script.EXPECTED_VIRGINIA
        assert sorted(z["name"] for z in r["zero"]) == ["NICOLAS GOMEZ", "Oscar Diaz Vargas"]
        assert [u["name"] for u in r["unclosed"]["Alabama"]] == ["Beto Alabama"] and r["unclosed"]["Virginia"] == []
        assert r["open_statuses"] == {"Virginia": [], "Alabama": ["Beto Alabama"]}


async def test_aplicar_es_idempotente_y_deja_todo_como_se_pidio(env):
    async with env.maker() as db:
        first_rows = [r for r in await _rows(db, env.cid) if (r["source_ref"] or "").startswith("ajuste_masivo:virginia-2026-11-01-14:")]
        out = await script.apply(db, env.cid, now=NOW, expected=None)
        assert out["unclosed_by_place"] == {"Virginia": 0, "Alabama": 1} and out["statuses_closed"] == 1
        rows = await _rows(db, env.cid)
        again = await script.apply(db, env.cid, now=NOW)
        assert again["person_days"] == 0 and await _rows(db, env.cid) == rows, "dos veces da lo mismo"
        v = await script.verify(db, env.cid)
        assert v["wrong"] == [] and v["zero_with_hours"] == []
        assert v["virginia_01_14"] == script.EXPECTED_VIRGINIA and v["virginia_people"] == 15
        assert v["open_statuses"] == {"Virginia": [], "Alabama": []} and v["held_first_cut"] == {"Virginia": 0, "Alabama": 0}
        assert [r for r in await _rows(db, env.cid) if (r["source_ref"] or "").startswith("ajuste_masivo:virginia-2026-11-01-14:")] == first_rows, "lote anterior intacto"
        mij = [r for r in await _rows(db, env.cid, env.mijail) if r["source_channel"] == "ajuste_masivo"]
        sunday = [(r["event_type"], r["occurred_at"].astimezone(ET).strftime("%H:%M")) for r in mij if r["occurred_at"].astimezone(ET).day == 1]
        assert sunday == [("check_in", "06:00"), ("break_start", "12:00"), ("break_end", "12:30"), ("check_out", "20:30")]
        st = (await db.execute(text("SELECT status FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": env.beto})).scalar()
        assert st == "checked_out"


async def test_no_toca_el_corte_actual_ni_otra_empresa(env):
    async with env.maker() as db:
        keep_ana = await _rows(db, env.cid, env.ana)
        keep_diego15 = [r for r in await _rows(db, env.cid, env.diego) if r["occurred_at"] >= at(15, "00:00")]
        keep_foreign = await _rows(db, env.other, env.foreign)
        await script.apply(db, env.cid, now=NOW)
        assert await _rows(db, env.cid, env.ana) == keep_ana, "turno normal del 15 y abierto del 16 en Alabama: se quedan"
        assert [r for r in await _rows(db, env.cid, env.diego) if r["occurred_at"] >= at(15, "00:00") and r["source_channel"] != "ajuste_masivo"] == keep_diego15
        assert await _rows(db, env.other, env.foreign) == keep_foreign
        st = (await db.execute(text("SELECT status, check_in_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": env.ana})).mappings().first()
        assert st["status"] == "working" and st["check_in_at"] == at(16, "06:00", CT), "conectado de verdad hoy: no se toca"


async def test_deshacer_solo_este_lote(env):
    async with env.maker() as db:
        before = {r["id"]: (r["event_type"], r["status_after"]) for r in await _rows(db, env.cid)}
        await script.apply(db, env.cid, now=NOW)
        out = await script.undo(db, env.cid)
        assert out["rows"] > 0 and out["status_not_restored"] == 0
        after = {r["id"]: (r["event_type"], r["status_after"]) for r in await _rows(db, env.cid)}
        assert all(after[k] == v for k, v in before.items()), "todo como antes de este lote (el anterior sigue aplicado)"
        st = (await db.execute(text("SELECT status FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": env.beto})).scalar()
        assert st == "working"
        assert (await db.execute(text("SELECT count(*) FROM workforce_attendance_adjustments WHERE batch = 'virginia-2026-11-01-14' AND undone_at IS NULL"))).scalar() > 0
        assert (await script.undo(db, env.cid))["rows"] == 0


async def test_no_aplica_antes_del_fin_del_corte_de_alabama_ni_con_otro_numero(env):
    async with env.maker() as db:
        with pytest.raises(script.NeedsReview):
            await script.apply(db, env.cid, now=at(15, "20:00", CT))
        with pytest.raises(script.NeedsReview):
            await script.apply(db, env.cid, now=NOW, expected=16)
