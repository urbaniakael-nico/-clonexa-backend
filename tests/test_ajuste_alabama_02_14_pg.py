"""Ajuste masivo de Alabama 02-14 nov 2026 (semanas de prueba del bot) contra Postgres REAL. Datos
inventados: PRUEBA solo lee y cuadra con los totales esperados; aplicar deja la tabla exacta
(111.5 h = 80 + 31.5 OT; Brandon/Giselle 80 h = 68.5 + 11.5 OT), reemplaza lo del bot y el ajuste
anterior del 2-3 nov, vacia sab 07 / dom 08 y los dias excluidos, es idempotente, se deshace, y no
toca Virginia, inactivos, otra empresa ni nada desde el domingo 15. Si pgserver no esta, se salta."""
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
CT = ZoneInfo("America/Chicago")
NOW = datetime(2026, 11, 17, 22, 0, tzinfo=timezone.utc)
RULES = {"week_start_day": "monday", "week_start_time": "00:00", "overtime_after_minutes": 2400, "overtime_factor": 1.5,
         "pay_period": {"type": "biweekly", "anchor": "2026-11-02"}}
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


script = _load("ajuste_alabama_02_14", ROOT / "scripts" / "ajuste_alabama_02_14_nov_2026.py")
old = _load("ajuste_alabama_2_3_b", ROOT / "scripts" / "ajuste_alabama_2_3_nov_2026.py")
seedmod = _load("ajuste_seed_b", ROOT / "tests" / "fixtures" / "reports_board_seed.py")


def _migration() -> list[str]:
    module = _load("m025a_b", ROOT / "migrations" / "versions" / "025a_attendance_adjustments.py")
    out: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: out.append(str(sql)))
    module.upgrade()
    return out


def ct(day: int, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"2026-11-{day:02d}T{hhmm}:00").replace(tzinfo=CT)


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_ajuste14_"), cleanup_mode="stop")
    yield server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)


async def _day(db, cid, eid, day, start, end, pause=None):
    await seedmod.ev(db, cid, eid, "check_in", ct(day, start), point=(32.3, -86.3))
    if pause:
        await seedmod.ev(db, cid, eid, "break_start", ct(day, pause[0]), point=(32.3, -86.3))
        await seedmod.ev(db, cid, eid, "break_end", ct(day, pause[1]), point=(32.3, -86.3))
    await seedmod.ev(db, cid, eid, "check_out", ct(day, end), point=(32.3, -86.3), detail="Resumen real del bot")


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
        for company in (cid, other):
            await db.execute(text("""UPDATE company_modules SET settings = settings || CAST(:s AS jsonb)
                                     WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE code = 'payroll')"""),
                             {"c": company, "s": json.dumps({"us_payroll_rules": RULES})})
        await db.execute(text("INSERT INTO workforce_session_policy (company_id, alert_after_hours) VALUES (CAST(:c AS uuid), 15)"), {"c": cid})
        va = await seedmod.place(db, cid, "Virginia", "VA", "America/New_York", 1)
        al = await seedmod.place(db, cid, "Alabama", "AL", "America/Chicago", 2)
        other_al = await seedmod.place(db, other, "Alabama", "AL", "America/Chicago", 1)
        ids = SimpleNamespace(cid=cid, other=other)
        ids.ana = await seedmod.person(db, cid, "Ana Normal", "A1", al)
        ids.none = await seedmod.person(db, cid, "Caro Sin Marcas", "A2", al)
        ids.brandon = await seedmod.person(db, cid, "Brandon Patrick Vía Illanes", "A3", al)
        ids.giselle = await seedmod.person(db, cid, "Giselle del Carmen Reyna", "A4", al)
        ids.old_brandon = await seedmod.person(db, cid, "Brandon Via Illanes", "A5", al)
        ids.vic = await seedmod.person(db, cid, "Vic Virginia", "V1", va)
        ids.foreign = await seedmod.person(db, other, "Gina Otra", "O1", other_al)
        await db.execute(text("UPDATE employees SET status = 'archived' WHERE id = CAST(:e AS uuid)"), {"e": ids.old_brandon})
        # Ana: semanas de prueba del bot (horas al azar), el ajuste viejo del 2-3 nov, un sabado 07,
        # un dia 13 por confirmar (16 h) y un turno real del lunes 16 que NO se toca.
        await db.commit()
        await old_apply(db, cid)
        for d in (4, 5, 6, 9, 10, 11, 12, 14):
            await _day(db, cid, ids.ana, d, "06:31", "15:02", pause=("11:10", "11:40"))
        await _day(db, cid, ids.ana, 7, "08:00", "12:00")
        await _day(db, cid, ids.ana, 13, "06:00", "22:30")
        await _day(db, cid, ids.ana, 16, "06:00", "16:30", pause=("11:00", "12:00"))
        await db.execute(text("""INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at, check_out_at)
                                 VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'checked_out', 'check_out', :o, :i, :o)"""), {"c": cid, "e": ids.ana, "i": ct(16, "06:00"), "o": ct(16, "16:30")})
        # Brandon y Giselle marcaron el 9-11 (se vacia) y el 12; Brandon deja el turno del 14 abierto
        for who in (ids.brandon, ids.giselle):
            for d in (9, 10, 11, 12):
                await _day(db, cid, who, d, "06:00", "14:00")
        await seedmod.ev(db, cid, ids.brandon, "check_in", ct(14, "07:03"))
        await db.execute(text("""INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at)
                                 VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'working', 'check_in', :i, :i)"""), {"c": cid, "e": ids.brandon, "i": ct(14, "07:03")})
        await db.execute(text("INSERT INTO gps_tracking_sessions (company_id, employee_id) VALUES (CAST(:c AS uuid), CAST(:e AS uuid))"), {"c": cid, "e": ids.brandon})
        # Los que no entran
        for who, company in ((ids.vic, cid), (ids.old_brandon, cid), (ids.foreign, other)):
            await _day(db, company, who, 9, "06:00", "19:30")
        await db.commit()
    yield SimpleNamespace(maker=maker, **vars(ids))
    await engine.dispose()


async def old_apply(db, cid):
    """El ajuste del 2-3 nov ya aplicado en produccion (solo hay personas sin marcas aun)."""
    people = await old.cohort(db, cid)
    assert people  # Ana, Caro, Brandon, Giselle
    await old.apply(db, cid, now=datetime(2026, 11, 4, tzinfo=timezone.utc))


async def _rows(db, cid, eid=None):
    return [dict(r) for r in (await db.execute(text("""
        SELECT id::text AS id, employee_id::text AS employee_id, event_type, event_label, status_after, source_channel, source_ref, notes, payload_json, latitude, occurred_at
        FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid) AND (:e = '' OR employee_id::text = :e) ORDER BY occurred_at, id
    """), {"c": cid, "e": eid or ""})).mappings().all()]


def _tot(fig, eid):
    f = fig.get(eid, {})
    return (f.get("payable"), f.get("regular"), f.get("overtime"), f.get("pause"))


async def test_prueba_solo_lee_cuadra_y_lista_personas(env):
    async with env.maker() as db:
        before = await _rows(db, env.cid)
        r = await script.report(db, env.cid)
        assert await _rows(db, env.cid) == before, "PRUEBA no escribe"
        names = [x["name"] for x in r["people"]]
        assert names == ["Ana Normal", "Brandon Patrick Vía Illanes", "Caro Sin Marcas", "Giselle del Carmen Reyna"], "solo activos de Alabama"
        assert r["matches_expected"] is True
        by = {x["name"]: x for x in r["people"]}
        assert by["Ana Normal"]["after"] == (6690, 4800, 1890) and by["Caro Sin Marcas"]["after"] == (6690, 4800, 1890)
        assert by["Brandon Patrick Vía Illanes"]["after"] == (4800, 4110, 690) and by["Brandon Patrick Vía Illanes"]["excluded"] == ["2026-11-09", "2026-11-10", "2026-11-11"]
        assert by["Ana Normal"]["weeks_after"] == [("2026-11-02", 3090, 690), ("2026-11-09", 3600, 1200)]
        assert by["Ana Normal"]["days_to_empty"] == 1, "sabado 07 queda sin horas"
        assert [h["employee_name"] for h in r["held_in_range"]] == ["Ana Normal"], "el dia 13 por confirmar se reporta"


async def test_aplicar_deja_la_tabla_exacta_y_es_idempotente(env):
    async with env.maker() as db:
        first = await script.apply(db, env.cid, now=NOW, expected=4)
        assert first["people"] == 4 and first["already_done"] == 0
        rows = await _rows(db, env.cid)
        second = await script.apply(db, env.cid, now=NOW, expected=4)
        assert second["person_days"] == 0 and second["new_events"] == 0
        assert await _rows(db, env.cid) == rows, "correrlo dos veces da lo mismo"
        fig = await script.figures(db, env.cid)
        for who in (env.ana, env.none):
            assert _tot(fig, who) == (6690, 4800, 1890, 660)
            assert fig[who]["weeks"] == [("2026-11-02", 3090, 690), ("2026-11-09", 3600, 1200)]
        for who in (env.brandon, env.giselle):
            assert _tot(fig, who) == (4800, 4110, 690, 480)
            assert fig[who]["weeks"] == [("2026-11-02", 3090, 690), ("2026-11-09", 1710, 0)]
        assert not [h for h in fig["_held"] if h["employee_id"] == env.ana], "el turno por confirmar del 13 quedo reemplazado"
        assert (await script.verify(db, env.cid))["wrong"] == []
        ana = [r for r in await _rows(db, env.cid, env.ana) if r["source_channel"] == "ajuste_masivo" and r["status_after"] != us_payroll.EVENT_REPLACED]
        assert len(ana) == 44 and all(r["payload_json"]["batch"] == script.BATCH for r in ana), "11 dias x 4 marcas, todas del lote nuevo"
        monday = [(r["event_type"], r["occurred_at"].astimezone(CT).strftime("%H:%M")) for r in ana if r["occurred_at"].astimezone(CT).day == 2]
        assert monday == [("check_in", "06:00"), ("break_start", "12:00"), ("break_end", "13:00"), ("check_out", "16:30")]
        audits = (await db.execute(text("SELECT count(*) FROM admin_audit_log WHERE path = '/scripts/ajuste_alabama_02_14_nov_2026/apply'"))).scalar()
        assert audits == 1


async def test_nada_se_borra_y_el_respaldo_tiene_lo_del_bot(env):
    async with env.maker() as db:
        before = await _rows(db, env.cid, env.ana)
        await script.apply(db, env.cid, now=NOW)
        after = {r["id"]: r for r in await _rows(db, env.cid, env.ana)}
        assert all(b["id"] in after for b in before), "ninguna marcacion se borra"
        replaced = [after[b["id"]] for b in before if b["occurred_at"] < ct(15, "00:00")]
        assert replaced and all(r["status_after"] == us_payroll.EVENT_REPLACED for r in replaced)
        audit = (await db.execute(text("""SELECT reason, created_at, before_json, after_json FROM workforce_attendance_adjustments
                                          WHERE batch = :b AND employee_id = CAST(:e AS uuid) AND work_date = :d"""),
                                  {"b": script.BATCH, "e": env.ana, "d": date(2026, 11, 4)})).mappings().first()
        assert audit["reason"] == script.NOTE and "semanas de prueba bot" in audit["reason"] and audit["created_at"]
        assert [e["occurred_at"][11:16] for e in audit["before_json"]["events"]] == ["12:31", "17:10", "17:40", "21:02"], "lo del bot (UTC) en el respaldo"
        assert audit["after_json"]["payable_minutes"] == 570 and audit["after_json"]["times"] == ["06:00", "11:00", "12:00", "16:30"]
        sat = (await db.execute(text("SELECT after_json FROM workforce_attendance_adjustments WHERE batch = :b AND employee_id = CAST(:e AS uuid) AND work_date = :d"),
                                {"b": script.BATCH, "e": env.ana, "d": date(2026, 11, 7)})).scalar()
        assert sat["events"] == [] and sat["payable_minutes"] == 0, "sabado 07 sin horas"


async def test_no_toca_virginia_inactivos_otra_empresa_ni_desde_el_15(env):
    async with env.maker() as db:
        protected = {k: await _rows(db, c, getattr(env, k)) for k, c in (("vic", env.cid), ("old_brandon", env.cid), ("foreign", env.other))}
        monday16 = [r for r in await _rows(db, env.cid, env.ana) if r["occurred_at"] >= ct(15, "00:00")]
        await script.apply(db, env.cid, now=NOW)
        for key, company in (("vic", env.cid), ("old_brandon", env.cid), ("foreign", env.other)):
            assert await _rows(db, company, getattr(env, key)) == protected[key], key
        assert [r for r in await _rows(db, env.cid, env.ana) if r["occurred_at"] >= ct(15, "00:00") and r["source_channel"] != "ajuste_masivo"] == monday16
        nxt = await script.figures(db, env.cid, date(2026, 11, 16), date(2026, 11, 29))
        assert nxt[env.ana]["payable"] == 570, "el corte 16-29 sigue con lo del bot"
        st = (await db.execute(text("SELECT status, check_in_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": env.ana})).mappings().first()
        assert st["status"] == "checked_out" and st["check_in_at"] == ct(16, "06:00"), "el estado de su turno real del 16 no se pisa"
        bst = (await db.execute(text("SELECT status, check_out_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": env.brandon})).mappings().first()
        assert bst["status"] == "checked_out" and bst["check_out_at"] == ct(14, "17:30"), "el turno abierto del 14 queda cerrado con la tabla"
        assert (await db.execute(text("SELECT status FROM gps_tracking_sessions WHERE employee_id = CAST(:e AS uuid)"), {"e": env.brandon})).scalar() == "closed"


async def test_deshacer_vuelve_a_lo_de_antes_y_el_ajuste_viejo_espera(env):
    async with env.maker() as db:
        fig0 = await script.figures(db, env.cid)
        rows0 = {r["id"]: (r["event_type"], r["status_after"]) for r in await _rows(db, env.cid)}
        await script.apply(db, env.cid, now=NOW)
        with pytest.raises(old.NeedsReview):
            await old.undo(db, env.cid)
        await db.rollback()
        undone = await script.undo(db, env.cid)
        assert undone["person_days"] > 0 and undone["status_not_restored"] == 0
        rows1 = {r["id"]: (r["event_type"], r["status_after"]) for r in await _rows(db, env.cid)}
        assert all(rows1[k] == v for k, v in rows0.items()), "todas las marcaciones vuelven a como estaban"
        fig1 = await script.figures(db, env.cid)
        assert {k: _tot(fig1, k) for k in (env.ana, env.none, env.brandon)} == {k: _tot(fig0, k) for k in (env.ana, env.none, env.brandon)}
        st = (await db.execute(text("SELECT status, check_in_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": env.brandon})).mappings().first()
        assert st["status"] == "working" and st["check_in_at"] == ct(14, "07:03")
        assert (await script.undo(db, env.cid))["person_days"] == 0
        again = await script.apply(db, env.cid, now=NOW, expected=4)
        assert again["already_done"] == 0 and (await script.verify(db, env.cid))["wrong"] == []


async def test_no_aplica_si_cambia_el_numero_de_personas_es_temprano_o_hay_duda_de_nombre(env):
    async with env.maker() as db:
        rows = await _rows(db, env.cid)
        with pytest.raises(script.NeedsReview):
            await script.apply(db, env.cid, now=NOW, expected=24)
        with pytest.raises(script.NeedsReview):
            await script.apply(db, env.cid, now=ct(14, "20:00"))
        await db.rollback()
        await db.execute(text("UPDATE employees SET status = 'active' WHERE id = CAST(:e AS uuid)"), {"e": env.old_brandon})
        await db.commit()
        with pytest.raises(script.NeedsReview, match="brandon via illanes"):
            await script.plan(db, env.cid)
        await db.rollback()
        assert await _rows(db, env.cid) == rows
