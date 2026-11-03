"""Ajuste masivo de Alabama (2 y 3 nov 2026) contra Postgres REAL. Datos inventados: idempotente,
deshacer, no toca Virginia ni inactivos, crea el turno a quien no tenia, cierra turnos abiertos,
totales 10 h 00 / 10 h 15 en Nomina, Reportes (chip Ajustado, Ajuste manual), CSV y bot. Si pgserver
no esta instalado, se salta."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.services import reports_board, reports_board_export, us_payroll  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CT = ZoneInfo("America/Chicago")
NOW = datetime(2026, 11, 3, 23, 40, tzinfo=timezone.utc)
LATER = datetime(2026, 11, 5, 18, 0, tzinfo=timezone.utc)
MON, TUE = "2026-11-02", "2026-11-03"
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


script = _load("ajuste_alabama", ROOT / "scripts" / "ajuste_alabama_2_3_nov_2026.py")
seedmod = _load("ajuste_seed", ROOT / "tests" / "fixtures" / "reports_board_seed.py")


def _migration(direction: str = "upgrade") -> list[str]:
    module = _load("m025a", ROOT / "migrations" / "versions" / "025a_attendance_adjustments.py")
    out: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: out.append(str(sql)))
    getattr(module, direction)()
    assert len(module.revision) <= 32 and module.down_revision == "024z_reports_board"
    return out


def ct(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=CT)


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_ajuste_"), cleanup_mode="stop")
    yield server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)


async def _punch(db, cid, eid, kind, at, **kw):
    await seedmod.ev(db, cid, eid, kind, at, **kw)


async def _status(db, cid, eid, status, check_in, check_out=None):
    await db.execute(text("""
        INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at, check_out_at)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :s, 'check_in', :at, :at, :o)
    """), {"c": cid, "e": eid, "s": status, "at": check_in, "o": check_out})


@pytest.fixture()
async def env(pg_url):
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await seedmod.create_schema(conn)
        for stmt in [s for s in EXTRA.split(";") if s.strip()] + _migration() + _migration():
            await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        cid = await seedmod.company(db, "VOLTAGE", board=True)
        other = await seedmod.company(db, "Otra", board=False)
        va = await seedmod.place(db, cid, "Virginia", "VA", "America/New_York", 1)
        al = await seedmod.place(db, cid, "Alabama", "AL", "America/Chicago", 2)
        other_al = await seedmod.place(db, other, "Alabama", "AL", "America/Chicago", 1)
        ids = {"cid": cid, "other": other}
        ids["normal"] = await seedmod.person(db, cid, "Ana Normal", "A1", al)
        ids["open"] = await seedmod.person(db, cid, "Beto Abierto", "A2", al)
        ids["none"] = await seedmod.person(db, cid, "Caro Sin Marcas", "A3", al)
        ids["long"] = await seedmod.person(db, cid, "Dani Larga", "A4", al)
        ids["virginia"] = await seedmod.person(db, cid, "Eva Virginia", "V1", va)
        ids["inactive"] = await seedmod.person(db, cid, "Fito Inactivo", "A5", al)
        ids["foreign"] = await seedmod.person(db, other, "Gina Otra", "O1", other_al)
        await db.execute(text("UPDATE employees SET status = 'archived' WHERE id = CAST(:e AS uuid)"), {"e": ids["inactive"]})
        # Lunes con dos pausas y resumen; martes cerrado
        await _punch(db, cid, ids["normal"], "check_in", ct(MON, "06:12"), point=(32.3, -86.3))
        await _punch(db, cid, ids["normal"], "break_start", ct(MON, "09:00"), point=(32.3, -86.3))
        await _punch(db, cid, ids["normal"], "break_end", ct(MON, "09:10"), point=(32.3, -86.3))
        await _punch(db, cid, ids["normal"], "break_start", ct(MON, "12:00"), point=(32.3, -86.3))
        await _punch(db, cid, ids["normal"], "break_end", ct(MON, "13:00"), point=(32.3, -86.3))
        await _punch(db, cid, ids["normal"], "check_out", ct(MON, "19:00"), point=(32.3, -86.3), detail="Etiquetado del rack 9.")
        await _punch(db, cid, ids["normal"], "check_in", ct(TUE, "05:44"), point=(32.3, -86.3))
        await _punch(db, cid, ids["normal"], "check_out", ct(TUE, "17:14"), point=(32.3, -86.3))
        await _status(db, cid, ids["normal"], "checked_out", ct(TUE, "05:44"), ct(TUE, "17:14"))
        # Lunes sin salida marcada, martes sigue en turno y en pausa
        await _punch(db, cid, ids["open"], "check_in", ct(MON, "05:50"))
        await _punch(db, cid, ids["open"], "check_in", ct(TUE, "05:47"))
        await _punch(db, cid, ids["open"], "break_start", ct(TUE, "16:30"))
        await _status(db, cid, ids["open"], "on_break", ct(TUE, "05:47"))
        await db.execute(text("INSERT INTO gps_tracking_sessions (company_id, employee_id) VALUES (CAST(:c AS uuid), CAST(:e AS uuid))"), {"c": cid, "e": ids["open"]})
        await db.execute(text("""INSERT INTO company_telegram_pending_actions (company_id, employee_id, action, expires_at)
                                 VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'gps_punch', :x)"""), {"c": cid, "e": ids["open"], "x": datetime(2030, 1, 1, tzinfo=timezone.utc)})
        # Por confirmar: 15 h 25 con limite de 15 h
        await db.execute(text("INSERT INTO workforce_session_policy (company_id, alert_after_hours) VALUES (CAST(:c AS uuid), 15)"), {"c": cid})
        await _punch(db, cid, ids["long"], "check_in", ct(MON, "06:13"))
        await _punch(db, cid, ids["long"], "check_out", ct(MON, "21:38"))
        # Los que no entran
        for key, company in (("virginia", cid), ("inactive", cid), ("foreign", other)):
            await _punch(db, company, ids[key], "check_in", ct(MON, "06:00"), point=(38.9, -77.0))
            await _punch(db, company, ids[key], "check_out", ct(MON, "19:30"), point=(38.9, -77.0))
        await db.commit()
    yield SimpleNamespace(maker=maker, **ids)
    await engine.dispose()


async def _rows(db, cid, eid=None):
    return [dict(r) for r in (await db.execute(text("""
        SELECT id::text AS id, employee_id::text AS employee_id, event_type, event_label, status_after, source_channel, source, notes, payload_json, latitude, occurred_at
        FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid) AND (:e = '' OR employee_id::text = :e) ORDER BY occurred_at, id
    """), {"c": cid, "e": eid or ""})).mappings().all()]


async def _snapshot_of(db, cid):
    return await script.day_figures(db, cid)


async def test_el_plan_solo_lee_y_no_incluye_virginia_ni_inactivos(env):
    async with env.maker() as db:
        before = await _rows(db, env.cid)
        items = await script.plan(db, env.cid)
        assert {i.employee["id"] for i in items} == {env.normal, env.open, env.none, env.long}
        assert len(items) == 8
        none_days = [i for i in items if i.employee["id"] == env.none]
        assert all(i.without_punches for i in none_days), "a quien no marco se le crea el turno"
        assert [i.is_open for i in items if i.employee["id"] == env.open] == [True, True]
        assert await _rows(db, env.cid) == before


async def test_aplicar_deja_10_00_y_10_15_y_es_idempotente(env):
    async with env.maker() as db:
        first = await script.apply(db, env.cid, now=NOW, expected=4)
        assert first["person_days"] == 8 and first["new_events"] == 32 and first["created_shifts"] == 3, first
        assert first["closed_open_shifts"] == 1
        rows_after = await _rows(db, env.cid)
        second = await script.apply(db, env.cid, now=NOW, expected=4)
        assert second["person_days"] == 0 and second["new_events"] == 0 and second["already_done"] == 8
        assert await _rows(db, env.cid) == rows_after, "repetir no duplica ni cambia nada"
        figures = await _snapshot_of(db, env.cid)
        for key in ("normal", "open", "none", "long"):
            person = figures[getattr(env, key)]
            assert person["days"][MON] == 600 and person["days"][TUE] == 615, key
            assert person["week"] == 1215, "20 h 15 en la semana"
        audits = (await db.execute(text("SELECT count(*) FROM workforce_attendance_adjustments WHERE undone_at IS NULL"))).scalar()
        assert audits == 8
        logged = (await db.execute(text("SELECT actor, detail FROM admin_audit_log WHERE path LIKE '%/apply'"))).mappings().all()
        assert len(logged) == 1 and "autorizado por el dueño" in logged[0]["actor"]


async def test_nada_se_borra_originales_reemplazadas_y_ajuste_con_origen_y_nota(env):
    async with env.maker() as db:
        before = await _rows(db, env.cid, env.normal)
        await script.apply(db, env.cid, now=NOW)
        after = await _rows(db, env.cid, env.normal)
        originals = {r["id"]: r for r in after if r["id"] in {b["id"] for b in before}}
        assert len(originals) == len(before), "ninguna original se borra"
        assert all(r["status_after"] == us_payroll.EVENT_REPLACED and r["event_label"] == "Reemplazada por ajuste" for r in originals.values())
        assert all(a["occurred_at"] == originals[a["id"]]["occurred_at"] and a["latitude"] == originals[a["id"]]["latitude"] for a in before), "hora y GPS originales intactos"
        new = [r for r in after if r["source_channel"] == "ajuste_masivo"]
        assert len(new) == 8 and all(r["source"] == "ajuste_masivo" and r["notes"] == script.NOTE and r["latitude"] is None for r in new)
        monday = [r for r in new if r["occurred_at"].astimezone(CT).date().isoformat() == MON]
        assert [(r["event_type"], r["occurred_at"].astimezone(CT).strftime("%H:%M")) for r in monday] == [
            ("check_in", "05:45"), ("break_start", "11:00"), ("break_end", "12:00"), ("check_out", "16:45")]
        tuesday = [r for r in new if r["occurred_at"].astimezone(CT).date().isoformat() == TUE]
        assert tuesday[-1]["occurred_at"].astimezone(CT).strftime("%H:%M") == "17:00"
        audit = (await db.execute(text("""SELECT reason, actor, before_json, after_json, created_at FROM workforce_attendance_adjustments
                                          WHERE employee_id = CAST(:e AS uuid) AND work_date = :d"""), {"e": env.normal, "d": datetime(2026, 11, 2).date()})).mappings().first()
        assert audit["reason"] == script.NOTE and audit["created_at"] and "dueño" in audit["actor"]
        bj = audit["before_json"] if isinstance(audit["before_json"], dict) else json.loads(audit["before_json"])
        assert len(bj["events"]) == 6 and bj["events"][0]["latitude"] == pytest.approx(32.3), "ubicacion original en la auditoria"
        assert audit["after_json"]["payable_minutes"] == 600


async def test_cierra_turnos_abiertos_y_por_confirmar(env):
    async with env.maker() as db:
        snap = await us_payroll.snapshot(db, env.cid, datetime(2026, 11, 2).date(), datetime(2026, 11, 3).date())
        assert [u["employee_name"] for u in snap["unverified_shifts"]] == ["Dani Larga"], "por confirmar antes del ajuste"
        await script.apply(db, env.cid, now=NOW)
        snap = await us_payroll.snapshot(db, env.cid, datetime(2026, 11, 2).date(), datetime(2026, 11, 3).date())
        assert "unverified_shifts" not in snap or not [u for u in snap["unverified_shifts"] if u["employee_name"] == "Dani Larga"]
        st = (await db.execute(text("SELECT status, check_in_at, check_out_at, break_started_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": env.open})).mappings().first()
        assert st["status"] == "checked_out" and st["check_out_at"] == ct(TUE, "17:00") and st["check_in_at"] == ct(TUE, "05:45") and st["break_started_at"] is None
        assert (await db.execute(text("SELECT status FROM gps_tracking_sessions WHERE employee_id = CAST(:e AS uuid)"), {"e": env.open})).scalar() == "closed"
        exp = (await db.execute(text("SELECT expires_at FROM company_telegram_pending_actions WHERE employee_id = CAST(:e AS uuid)"), {"e": env.open})).scalar()
        assert exp < datetime(2030, 1, 1, tzinfo=timezone.utc), "el paso pendiente del bot ya no aplica"


async def test_no_toca_virginia_inactivos_ni_otra_empresa(env):
    async with env.maker() as db:
        protected = {k: await _rows(db, c, getattr(env, k)) for k, c in (("virginia", env.cid), ("inactive", env.cid), ("foreign", env.other))}
        await script.apply(db, env.cid, now=NOW)
        for (key, company) in (("virginia", env.cid), ("inactive", env.cid), ("foreign", env.other)):
            assert await _rows(db, company, getattr(env, key)) == protected[key], key
        figures = await _snapshot_of(db, env.cid)
        assert figures[env.virginia]["days"][MON] == 13 * 60 + 30


async def test_deshacer_vuelve_a_las_originales_y_se_puede_repetir(env):
    async with env.maker() as db:
        before_fig = await _snapshot_of(db, env.cid)
        before_rows = {r["id"]: (r["event_type"], r["event_label"], r["status_after"]) for r in await _rows(db, env.cid)}
        await script.apply(db, env.cid, now=NOW)
        undone = await script.undo(db, env.cid)
        assert undone["person_days"] == 8 and undone["undone_events"] == 32
        after_rows = await _rows(db, env.cid)
        for row in after_rows:
            if row["id"] in before_rows:
                assert (row["event_type"], row["event_label"], row["status_after"]) == before_rows[row["id"]]
        assert sum(1 for r in after_rows if r["status_after"] == us_payroll.EVENT_UNDONE) == 32, "las del ajuste quedan guardadas"
        figures = await _snapshot_of(db, env.cid)
        assert {k: v["days"] for k, v in figures.items()} == {k: v["days"] for k, v in before_fig.items()}
        st = (await db.execute(text("SELECT status, check_in_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": env.open})).mappings().first()
        assert st["status"] == "on_break" and st["check_in_at"] == ct(TUE, "05:47")
        assert (await db.execute(text("SELECT status FROM gps_tracking_sessions WHERE employee_id = CAST(:e AS uuid)"), {"e": env.open})).scalar() == "active"
        assert (await db.execute(text("SELECT expires_at FROM company_telegram_pending_actions WHERE employee_id = CAST(:e AS uuid)"), {"e": env.open})).scalar() == datetime(2030, 1, 1, tzinfo=timezone.utc)
        assert (await script.undo(db, env.cid))["person_days"] == 0, "deshacer dos veces no hace nada"
        again = await script.apply(db, env.cid, now=NOW)
        assert again["person_days"] == 8
        assert (await _snapshot_of(db, env.cid))[env.none]["week"] == 1215


async def test_un_turno_nuevo_de_mañana_no_se_pisa(env):
    async with env.maker() as db:
        await script.apply(db, env.cid, now=NOW)
        tomorrow = ct("2026-11-04", "05:45")
        await db.execute(text("UPDATE workforce_attendance_status SET status = 'working', check_in_at = :t, last_event_at = :t WHERE employee_id = CAST(:e AS uuid)"), {"t": tomorrow, "e": env.normal})
        await db.commit()
        undone = await script.undo(db, env.cid)
        assert undone["status_not_restored"] == 1
        st = (await db.execute(text("SELECT status, check_in_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)"), {"e": env.normal})).mappings().first()
        assert st["status"] == "working" and st["check_in_at"] == tomorrow


async def test_no_aplica_si_cambia_el_numero_de_personas_o_es_temprano(env):
    async with env.maker() as db:
        rows = await _rows(db, env.cid)
        with pytest.raises(script.NeedsReview):
            await script.apply(db, env.cid, now=NOW, expected=24)
        with pytest.raises(script.NeedsReview):
            await script.apply(db, env.cid, now=ct(TUE, "16:00"))
        await db.rollback()
        assert await _rows(db, env.cid) == rows


async def test_board_csv_y_bot_muestran_el_ajuste(env):
    async with env.maker() as db:
        await script.apply(db, env.cid, now=NOW)
        board = await reports_board.build(db, env.cid, datetime(2026, 11, 2).date(), datetime(2026, 11, 3).date(), now=LATER)
        people = {p["id"]: p for o in board["operations"] for p in o["people"]}
        person = people[env.normal]
        monday = next(d for d in person["days"] if d["date"] == MON)
        shift = monday["shifts"][0]
        assert shift["adjusted"] is True and shift["in"]["s"] == "adjusted" and shift["out"]["s"] == "adjusted" and shift["pauses"][0]["start"]["s"] == "adjusted"
        assert "lat" not in shift["in"], "la marca del ajuste no muestra mapa"
        assert len(shift["pauses"]) == 1 and shift["pauses"][0]["minutes"] == 60, "una sola pausa"
        assert shift["payable"] == 600
        assert [n["text"] for n in shift["notes"] if n["kind"] == "summary"] == ["Etiquetado del rack 9."], "el resumen de la persona sigue"
        assert [n["label"] for n in shift["notes"] if n["kind"] == "adjusted"] == ["Ajustado"]
        alerts = [a for o in board["operations"] for a in o["alerts"] if a["employee_id"] == env.normal]
        assert not [a for a in alerts if a["kind"] in ("no_location", "outside", "to_confirm")], "el ajuste no levanta alertas"
        csv_text = reports_board_export.build_marks_csv(board)
        lines = [line for line in csv_text.splitlines() if "Ana Normal" in line]
        assert len(lines) == 8 and all("Ajuste manual" in line for line in lines) and any("05:45 CT" in line for line in lines)

        ended = ct(TUE, "17:00")
        bot = await us_payroll.bot_summary(db, env.cid, env.normal, ended, "es", lambda v: f"${Decimal(v):.2f}", name="Ana")
        assert "Tiempo pagable de hoy: 10 h 15 min" in bot and "Semana: 20 h 15 min de 40 h" in bot
        # Mañana: el total de la semana suma el ajuste con el turno nuevo
        await seedmod.ev(db, env.cid, env.none, "check_in", ct("2026-11-04", "06:00"))
        await seedmod.ev(db, env.cid, env.none, "check_out", ct("2026-11-04", "16:00"))
        await db.commit()
        bot = await us_payroll.bot_summary(db, env.cid, env.none, ct("2026-11-04", "16:00"), "es", lambda v: f"${Decimal(v):.2f}", name="Caro")
        assert "Semana: 30 h 15 min de 40 h" in bot

