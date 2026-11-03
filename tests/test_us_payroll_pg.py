"""Nomina EE. UU. (us_payroll) contra Postgres REAL (pgserver), con las marcaciones reales
de Colaboradora Caso 2 Nov del 2 nov 2026 (VOLTAGE, Virginia):
entrada 11:45:41 UTC, pausa 15:34:55-16:29:10, salida 21:25:20 (resumen de la jornada).

El bot, Reportes, Nomina, el PDF y el CSV dan las MISMAS cifras (una sola funcion):
06:45 ET -> 16:25 ET, 9h40 en turno, 55 min de pausa sin pago, 8h45 pagables, 0 overtime,
"Pendiente" sin tarifa (nunca $0.00). Otra empresa con el interruptor apagado: el
calculo de siempre (tope de 8 h por dia). Si pgserver no esta instalado, se salta."""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import payroll as core  # noqa: E402
from app.services import reports_v2, us_payroll, us_payroll_export  # noqa: E402

UTC = timezone.utc
SCHEMA = """
CREATE TABLE companies (id uuid PRIMARY KEY, name text NOT NULL, slug text, status text DEFAULT 'active', settings_json jsonb DEFAULT '{}'::jsonb, timezone text);
CREATE TABLE modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text, category text, is_active boolean DEFAULT true);
CREATE TABLE company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
  module_id uuid REFERENCES modules(id), enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb);
CREATE TABLE work_locations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  name varchar(80) NOT NULL, timezone varchar(64) NOT NULL DEFAULT 'America/Bogota');
CREATE TABLE employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  full_name varchar(200), role varchar(80), status varchar(40) DEFAULT 'active', telegram_user_id varchar(120),
  hourly_rate_regular numeric(12,2) DEFAULT 0, hourly_rate_extra numeric(12,2) DEFAULT 0, deduction_1 numeric(12,2) DEFAULT 0, deduction_2 numeric(12,2) DEFAULT 0,
  work_location_id uuid NULL REFERENCES work_locations(id));
CREATE TABLE workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid,
  event_type varchar(80) NOT NULL, event_label varchar(180) NOT NULL, employee_name varchar(180), employee_role varchar(80), status_after varchar(40) NOT NULL,
  source varchar(80) NOT NULL DEFAULT 'client', notes text, module_code varchar(80) NOT NULL DEFAULT 'workforce',
  source_channel varchar(80) NOT NULL DEFAULT 'client', source_ref varchar(180), detail text,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb, metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  latitude numeric(12,8), longitude numeric(12,8), occurred_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz DEFAULT now());
CREATE TABLE workforce_session_policy (company_id uuid PRIMARY KEY, cutoff_time varchar(5), alert_after_hours numeric)
"""
SUMMARY = "Etiquetado rack A \nCables:\n1-1\n1-2"


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_us_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
                await conn.execute(text(stmt))
            for code in ("payroll", "reports", "workforce"):
                await conn.execute(text("INSERT INTO modules (code, name) VALUES (:c, :c)"), {"c": code})
        await engine.dispose()

    asyncio.run(setup())
    yield url


@pytest.fixture()
async def maker(pg_url):
    engine = create_async_engine(pg_url)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _company(db, *, us: bool, tz: str = "America/Chicago", rules: dict | None = None) -> str:
    cid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO companies (id, name, timezone, settings_json) VALUES (CAST(:i AS uuid), :n, :tz, CAST(:s AS jsonb))"),
                     {"i": cid, "n": "VOLTAGE" if us else "Otra", "tz": tz,
                      "s": json.dumps({"client_settings": {"payroll": {"ordinary_hours_limit": 40.0, "ordinary_hours_scope": "week"}}})})
    settings = {"payroll_v2": True, **({"us_payroll": True} if us else {}), **({"us_payroll_rules": rules} if rules else {})}
    await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
                             SELECT CAST(:c AS uuid), id, true, CAST(:s AS jsonb) FROM modules WHERE code = 'payroll'"""),
                     {"c": cid, "s": json.dumps(settings)})
    await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
                             SELECT CAST(:c AS uuid), id, true, CAST('{"reports_v2": true}' AS jsonb) FROM modules WHERE code = 'reports'"""), {"c": cid})
    await db.commit()
    return cid


async def _place(db, cid, name, tz) -> str:
    pid = (await db.execute(text("INSERT INTO work_locations (company_id, name, timezone) VALUES (CAST(:c AS uuid), :n, :t) RETURNING id::text"),
                            {"c": cid, "n": name, "t": tz})).scalar()
    await db.commit()
    return pid


async def _person(db, cid, name, place=None, rate="0") -> str:
    eid = (await db.execute(text("""INSERT INTO employees (company_id, full_name, role, work_location_id, hourly_rate_regular)
                                    VALUES (CAST(:c AS uuid), :n, 'operario', CAST(:p AS uuid), CAST(:r AS numeric)) RETURNING id::text"""),
                            {"c": cid, "n": name, "p": place, "r": rate})).scalar()
    await db.commit()
    return eid


async def _ev(db, cid, eid, kind, at, *, label=None, detail=None, payload=None, lat=None, lng=None, channel="telegram"):
    status = {"check_in": "working", "break_start": "on_break", "break_end": "working", "check_out": "checked_out", "gps_location": "registered",
              "material_request": "requested"}[kind]
    await db.execute(text("""
        INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, event_label, status_after, source, source_channel,
                                                 detail, notes, payload_json, latitude, longitude, occurred_at)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :k, :l, :s, 'telegram', :ch, :d, :d, CAST(:p AS jsonb), :lat, :lng, :at)
    """), {"c": cid, "e": eid, "k": kind, "l": label or kind, "s": status, "ch": channel, "d": detail, "p": json.dumps(payload or {}),
           "lat": lat, "lng": lng, "at": at})
    await db.commit()


def T(s: str) -> datetime:
    return datetime.fromisoformat(s)


async def _caso(db, cid, eid):
    """Sus marcaciones reales del 2 nov (produccion, solo lectura)."""
    await _ev(db, cid, eid, "gps_location", T("2026-11-02T11:45:41.215661+00:00"), lat=38.900000, lng=-77.000000,
              payload={"gps_status": "unconfigured", "gps_status_label": "Sin perímetro"})
    await _ev(db, cid, eid, "check_in", T("2026-11-02T11:45:41.218018+00:00"), label="Inicio de turno", detail="Ubicación GPS validada",
              payload={"command": "/entrada", "args": "Ubicación GPS validada"})
    await _ev(db, cid, eid, "break_start", T("2026-11-02T15:34:55.518899+00:00"), label="Pausa", detail="clx:cmd:pausa", payload={"text": "clx:cmd:pausa"})
    await _ev(db, cid, eid, "break_end", T("2026-11-02T16:29:10.314277+00:00"), label="Retomar labores", detail="clx:cmd:reanudar")
    await _ev(db, cid, eid, "check_out", T("2026-11-02T21:25:20.056547+00:00"), label="Finalizar turno", detail=SUMMARY, lat=38.901000, lng=-77.001000,
              payload={"args": SUMMARY, "punch_location": {"latitude": 38.901000, "longitude": -77.001000, "gps_status": "unconfigured"},
                       "payroll_projection": {"regular_minutes": 480, "extra_minutes": 45, "projected_pay": "0.00"}})


@pytest.mark.asyncio
async def test_caso_same_numbers_in_payroll_reports_pdf_csv_and_bot(maker):
    async with maker() as db:
        cid = await _company(db, us=True)
        va = await _place(db, cid, "Virginia", "America/New_York")
        yes = await _person(db, cid, "Colaboradora Caso 2 Nov", va)
        await _caso(db, cid, yes)

        snap = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 1), date(2026, 11, 7))
        [row] = snap["rows"]
        assert (row["regular_minutes"], row["extra_minutes"]) == (525, 0), "8h45 regulares, sin extra por dia (antes 8h00 + 0h45)"
        assert row["rate_pending"] is True and row["us"]["net"] is None, "sin tarifa: Pendiente, nunca $0.00"
        assert snap["totals"]["rate_pending"] is True and snap["missing_rate_employees"][0]["employee_name"] == "Colaboradora Caso 2 Nov"
        u = row["us"]
        assert (u["place"], u["abbr"], u["days_worked"], u["connected_minutes"], u["pause_minutes"], u["payable_minutes"]) == \
            ("Virginia", "ET", 1, 580, 55, 525)
        assert u["weeks"][0]["week_start"] == "2026-11-01", "semana laboral desde el domingo"
        [sh] = row["shifts"]
        t = sh["us"]
        assert (t["check_in"]["local"], t["check_out"]["local"], t["abbr"]) == ("06:45", "16:25", "ET"), "hora de Virginia, no de Chicago"
        assert t["check_in"]["location"]["label"] == "Sin perímetro" and t["check_in"]["location"]["map"].startswith("https://www.google.com/maps?q=38.900000")
        assert [(p["start"]["local"], p["end"]["local"], p["minutes"]) for p in t["pauses"]] == [("10:34", "11:29", 55)]
        assert [n["kind"] for n in t["notes"]] == ["summary"] and t["notes"][0]["text"].startswith("Etiquetado rack A")

        # Reportes v2: misma cifra en la tarjeta, la ventana del turno, horas por dia e indicadores.
        payload = {"summary": {"period": {"start": "2026-11-01", "end": "2026-11-07"}},
                   "details": {"payroll": snap["rows"], "employees": [{"id": yes, "full_name": "Colaboradora Caso 2 Nov", "status": "active"}]}}
        ins = await reports_v2.insights_for(db, cid, payload, now=T("2026-11-03T00:00:00+00:00"))
        [p] = ins["people"]
        assert (p["payable"], p["pause"], p["extra"], p["rate_pending"]) == (525, 55, 0, True)
        assert (p["shifts"][0]["regular"], p["shifts"][0]["extra"], p["shifts"][0]["payable"]) == (525, 0, 525), "la ventana ya no dice Extra 0h45"
        assert (ins["us"]["payable_minutes"], ins["us"]["overtime_minutes"]) == (525, 0) and ins["figures"]["extra_minutes"] == 0
        assert [d for d in ins["hours_by_day"] if d["payable"]] == [{"date": "2026-11-02", "regular": 525, "extra": 0, "payable": 525, "pause": 55}]

        csv_text = us_payroll_export.build_csv(snap)
        line = next(x for x in csv_text.splitlines() if x.startswith("turno,"))
        assert "06:45 ET" in line and "16:25 ET" in line and "10:34 ET–11:29 ET (55 min)" in line and ",580,55,525,525,0," in line
        assert "Resumen de la jornada: Etiquetado rack A" in line
        total = next(x for x in csv_text.splitlines() if x.startswith("total,"))
        assert "Tarifa pendiente" in total and "Pendiente" in total and "$0.00" not in csv_text
        assert us_payroll_export.build_pdf(snap, "VOLTAGE")[:5] == b"%PDF-"
        assert reports_v2.build_pdf(payload, ins, reports_v2.ZoneInfo("America/Chicago"))[:5] == b"%PDF-"

        msg = await us_payroll.bot_summary(db, cid, yes, T("2026-11-02T21:25:20+00:00"), "es", money_label=lambda v: f"${v}", name="Caso")
        assert "Entrada 06:45 ET · Salida 16:25 ET" in msg and "Pausas: 0 h 55 min (sin pago)" in msg
        assert "Tiempo pagable de hoy: 8 h 45 min" in msg and "Semana: 8 h 45 min de 40 h" in msg
        assert "según tarifa (pendiente)" in msg and "Proyección" not in msg and "Overtime" not in msg
        en = await us_payroll.bot_summary(db, cid, yes, T("2026-11-02T21:25:20+00:00"), "en", money_label=lambda v: f"${v}", name="Caso")
        assert "In 06:45 ET · Out 16:25 ET" in en and "Breaks: 0 h 55 min (unpaid)" in en and "Week: 8 h 45 min of 40 h" in en


@pytest.mark.asyncio
async def test_alabama_local_time_no_place_uses_company_zone_and_overtime_with_rate(maker):
    async with maker() as db:
        cid = await _company(db, us=True)
        al = await _place(db, cid, "Alabama", "America/Chicago")
        carl = await _person(db, cid, "Carl", al, rate="20")
        nop = await _person(db, cid, "Sin Lugar")
        for i in range(5):  # lunes a viernes 9 h = 45 h
            day = datetime(2026, 11, 2 + i, 13, 0, tzinfo=UTC)
            await _ev(db, cid, carl, "check_in", day)
            await _ev(db, cid, carl, "check_out", day + timedelta(hours=9))
        await _ev(db, cid, nop, "check_in", datetime(2026, 11, 3, 14, 0, tzinfo=UTC))
        await _ev(db, cid, nop, "check_out", datetime(2026, 11, 3, 18, 0, tzinfo=UTC))
        snap = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 1), date(2026, 11, 7))
        rows = {r["employee_name"]: r for r in snap["rows"]}
        c = rows["Carl"]
        assert (c["regular_minutes"], c["extra_minutes"]) == (2400, 300), "45 h -> 40 regulares + 5 overtime"
        assert c["shifts"][0]["us"]["check_in"]["local"] == "07:00" and c["us"]["abbr"] == "CT"
        assert (c["us"]["regular_amount"], c["us"]["overtime_rate"], c["us"]["overtime_amount"], c["gross_amount"]) == (800.0, 30.0, 150.0, 950.0)
        n = rows["Sin Lugar"]
        assert n["us"]["place_missing"] and n["shifts"][0]["us"]["check_in"]["local"] == "08:00", "zona de la empresa (Chicago)"
        assert [m["employee_name"] for m in snap["us_payroll"]["missing_place"]] == ["Sin Lugar"]
        msg = await us_payroll.bot_summary(db, cid, carl, datetime(2026, 11, 6, 22, 0, tzinfo=UTC), "es", money_label=lambda v: f"${v:.2f}", name="Carl")
        assert "Semana: 45 h 00 min de 40 h" in msg and "Overtime de la semana: 5 h 00 min" in msg and "Proyección de la semana: $950.00" in msg


@pytest.mark.asyncio
async def test_manual_close_and_material_note_in_timeline(maker):
    async with maker() as db:
        cid = await _company(db, us=True)
        va = await _place(db, cid, "Virginia", "America/New_York")
        ana = await _person(db, cid, "Ana", va)
        await _ev(db, cid, ana, "check_in", T("2026-11-03T11:00:00+00:00"), lat=39.1, lng=-77.1,
                  payload={"punch_location": {"latitude": 39.1, "longitude": -77.1, "gps_status": "inside", "matched_perimeter_name": "Sitio A"}})
        await _ev(db, cid, ana, "material_request", T("2026-11-03T13:00:00+00:00"), label="Solicitar material", detail="10 cajas de cable")
        await _ev(db, cid, ana, "check_out", T("2026-11-03T20:00:00+00:00"), label="Turno cerrado por supervisor", channel="portal_manual_close",
                  detail="Olvidó finalizar", payload={"manual_close": True, "note": "Olvidó finalizar", "closed_by": "Sofía (supervisor)",
                                                     "closed_at": "2026-11-04T02:00:00+00:00"})
        snap = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 1), date(2026, 11, 7))
        t = snap["rows"][0]["shifts"][0]["us"]
        assert t["check_in"]["location"]["label"] == "En perímetro" and t["check_in"]["location"]["perimeter"] == "Sitio A"
        assert t["manual_close"] == {"by": "Sofía (supervisor)", "note": "Olvidó finalizar", "closed_at": "2026-11-04T02:00:00+00:00"}
        assert [(n["kind"], n["text"]) for n in t["notes"]] == [("material", "10 cajas de cable"), ("manual_close", "Olvidó finalizar")]
        assert us_payroll_export.closed_by(t) == "Cerrado por Sofía (supervisor)"


@pytest.mark.asyncio
async def test_other_company_with_switch_off_keeps_the_old_calculation(maker):
    async with maker() as db:
        cid = await _company(db, us=False)
        va = await _place(db, cid, "Virginia", "America/New_York")
        yes = await _person(db, cid, "Otra Persona", va)
        await _caso(db, cid, yes)
        assert not await us_payroll.is_on(db, cid)
        snap = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 1), date(2026, 11, 7))
        assert "us_payroll" not in snap and "us" not in snap["rows"][0]
        assert (snap["rows"][0]["shifts"][0]["regular_minutes"], snap["rows"][0]["shifts"][0]["extra_minutes"]) == (480, 45), "proyeccion del bot de siempre"


@pytest.mark.asyncio
async def test_week_start_rule_is_read_from_settings(maker):
    async with maker() as db:
        cid = await _company(db, us=True, rules={"week_start_day": "monday", "week_start_time": "00:00"})
        assert (await us_payroll.rules(db, cid))["week_start_day"] == "monday"
        other = await _company(db, us=True)
        assert (await us_payroll.rules(db, other)) == {"week_start_day": "sunday", "week_start_time": "00:00", "overtime_after_minutes": 2400, "overtime_factor": 1.5}


@pytest.mark.asyncio
async def test_screen_fixture_is_exactly_what_the_server_calculates(maker):
    """Las pruebas de pantalla (tests/us_payroll.test.cjs) usan este archivo: si el calculo
    cambia, regenerarlo con tests/fixtures/make_us_payroll_fixture.py."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parent / "fixtures" / "make_us_payroll_fixture.py"
    spec = importlib.util.spec_from_file_location("make_us_payroll_fixture", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    async with maker() as db:
        fresh = await mod.build(db)
    saved = json.loads((Path(__file__).parent / "fixtures" / "us_payroll_caso.json").read_text(encoding="utf-8"))
    assert fresh == saved
