"""081A: cortes por operacion contra Postgres REAL. Nomina con periodo por operacion (cada persona
con la semana o el corte de SU operacion), bot de Virginia que reinicia corte y semana el domingo
00:00 ET (y Alabama el lunes), turno que cruza el cambio de corte cuenta donde empezo, CSV/PDF con
las fechas de cada operacion y el script que guarda el ajuste de Virginia. Sin pgserver, se salta."""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402

from app.api.v1.endpoints import payroll as core  # noqa: E402
from app.services import us_payroll, us_payroll_export  # noqa: E402
from tests.test_us_payroll_pg import _company, _ev, _person, _place, maker, pg_url  # noqa: E402,F401

CT, ET = ZoneInfo("America/Chicago"), ZoneInfo("America/New_York")
COMPANY = {"week_start_day": "monday", "week_start_time": "00:00", "pay_period": {"type": "biweekly", "anchor": "2026-11-02"}}
VA_RULES = {"week_start_day": "sunday", "week_start_time": "00:00", "pay_period": {"type": "biweekly", "anchor": "2026-11-01"}}


def _money(v):
    return f"${v}"


async def _shift(db, cid, eid, tz, day, start, end, pause=None, end_day=None):
    def at(d, hhmm):
        hh, mm = (int(x) for x in hhmm.split(":"))
        return datetime(2026, 11, d, hh, mm, tzinfo=tz)

    await _ev(db, cid, eid, "check_in", at(day, start))
    if pause:
        await _ev(db, cid, eid, "break_start", at(day, pause[0]))
        await _ev(db, cid, eid, "break_end", at(day, pause[1]))
    await _ev(db, cid, eid, "check_out", at(end_day or day, end))


async def _setup(db):
    cid = await _company(db, us=True, rules=COMPANY)
    await db.execute(text("INSERT INTO workforce_session_policy (company_id, alert_after_hours) VALUES (CAST(:c AS uuid), 15)"), {"c": cid})
    await db.commit()
    va = await _place(db, cid, "Virginia", "America/New_York")
    al = await _place(db, cid, "Alabama", "America/Chicago")
    rules = {**COMPANY, "places": {va: VA_RULES}}
    await db.execute(text("""UPDATE company_modules SET settings = jsonb_set(settings, '{us_payroll_rules}', CAST(:r AS jsonb))
                             WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE code = 'payroll')"""),
                     {"c": cid, "r": __import__("json").dumps(rules)})
    await db.commit()
    return cid, va, al


@pytest.mark.asyncio
async def test_nomina_por_operacion_cada_persona_con_su_corte(maker):
    async with maker() as db:
        cid, va, al = await _setup(db)
        kewin = await _person(db, cid, "Kewin Virginia", va)
        ana = await _person(db, cid, "Ana Alabama", al)
        for d in (2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13):  # 12 h: 7:00-19:30, almuerzo 12:00-12:30
            await _shift(db, cid, kewin, ET, d, "07:00", "19:30", ("12:00", "12:30"))
        await _shift(db, cid, kewin, ET, 15, "07:00", "15:30", ("12:00", "12:30"))  # domingo 15: corte nuevo
        await _shift(db, cid, ana, CT, 15, "08:00", "12:00")  # domingo 15: aun corte 02-15 de Alabama
        await _shift(db, cid, ana, CT, 16, "06:00", "16:30", ("11:00", "12:00"))

        snap = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 1), date(2026, 11, 15), {"kind": "cut", "ref": date(2026, 11, 14)})
        rows = {r["employee_name"]: r for r in snap["rows"]}
        k = rows["Kewin Virginia"]["us"]
        assert (k["period_start"], k["period_end"], k["cut_label"]) == ("2026-11-01", "2026-11-14", "Corte 01/11 - 14/11")
        assert (k["payable_minutes"], k["regular_minutes"], k["overtime_minutes"]) == (132 * 60, 80 * 60, 52 * 60)
        assert [(w["week_start"], w["week_end"], w["payable"], w["overtime"]) for w in k["weeks"]] == [
            ("2026-11-01", "2026-11-07", 72 * 60, 32 * 60), ("2026-11-08", "2026-11-14", 60 * 60, 20 * 60)]
        a = rows["Ana Alabama"]["us"]
        assert (a["period_start"], a["period_end"], a["cut_label"], a["payable_minutes"]) == ("2026-11-02", "2026-11-15", "Corte 02/11 - 15/11", 240)
        ops = {o["name"]: o for o in snap["us_payroll"]["operations"]}
        assert ops["Virginia"]["cut"]["label"] == "Corte 01/11 - 14/11" and ops["Virginia"]["rules"]["week_start_day"] == "sunday"
        assert ops["Alabama"]["cut"]["label"] == "Corte 02/11 - 15/11" and ops["Alabama"]["rules"]["week_start_day"] == "monday"
        assert (snap["period"]["period_start"], snap["period"]["period_end"]) == ("2026-11-01", "2026-11-15")

        lines = us_payroll_export.build_csv(snap).splitlines()
        assert any(x.startswith("Virginia (ET),Kewin Virginia,,Semana 1 (01/11-07/11),,,") for x in lines)
        assert any(x.startswith("Virginia (ET),Kewin Virginia,,Total,,,") and ",132:00,80:00,52:00," in x for x in lines)
        assert not any(x.startswith("Virginia (ET),Kewin Virginia,,2026-11-15") for x in lines), "el 15 es del corte siguiente en Virginia"
        assert any(x.startswith("Alabama (CT),Ana Alabama,,2026-11-15") for x in lines), "el 15 es del corte 02-15 en Alabama"
        assert us_payroll_export.build_pdf(snap, "VOLTAGE")[:5] == b"%PDF-"

        nxt = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 15), date(2026, 11, 29), {"kind": "cut", "ref": date(2026, 11, 16)})
        rows = {r["employee_name"]: r["us"] for r in nxt["rows"]}
        assert (rows["Kewin Virginia"]["period_start"], rows["Kewin Virginia"]["payable_minutes"]) == ("2026-11-15", 480)
        assert (rows["Ana Alabama"]["period_start"], rows["Ana Alabama"]["payable_minutes"]) == ("2026-11-16", 570)

        week = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 15), date(2026, 11, 22), {"kind": "week", "ref": date(2026, 11, 18)})
        rows = {r["employee_name"]: r["us"] for r in week["rows"]}
        assert (rows["Kewin Virginia"]["period_start"], rows["Kewin Virginia"]["period_end"]) == ("2026-11-15", "2026-11-21"), "semana dom-sab"
        assert (rows["Ana Alabama"]["period_start"], rows["Ana Alabama"]["period_end"]) == ("2026-11-16", "2026-11-22"), "semana lun-dom"
        plain = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 1), date(2026, 11, 14))
        assert {r["employee_name"]: r["us"]["payable_minutes"] for r in plain["rows"]} == {"Kewin Virginia": 132 * 60}, "sin span: el periodo de siempre"


@pytest.mark.asyncio
async def test_bot_virginia_reinicia_el_domingo_y_alabama_el_lunes(maker):
    async with maker() as db:
        cid, va, al = await _setup(db)
        vic = await _person(db, cid, "Vic", va)
        ana = await _person(db, cid, "Ana", al)
        await _shift(db, cid, vic, ET, 13, "07:00", "15:30", ("12:00", "12:30"))
        # sabado 14 20:00 -> domingo 15 04:00 ET: cruza el cambio de corte, cuenta en el corte 01-14
        await _shift(db, cid, vic, ET, 14, "20:00", "04:00", end_day=15)
        await _shift(db, cid, vic, ET, 15, "10:00", "14:00")
        await _shift(db, cid, ana, CT, 15, "08:00", "12:00")
        await _shift(db, cid, ana, CT, 16, "08:00", "10:00")

        cross = await us_payroll.bot_summary(db, cid, vic, datetime(2026, 11, 15, 4, 0, tzinfo=ET), "es", money_label=_money, name="Vic")
        assert "🗓 Corte 01/11 - 14/11: 16 h 00 min" in cross, "el turno que cruza cuenta entero donde empezo"
        sun = await us_payroll.bot_summary(db, cid, vic, datetime(2026, 11, 15, 14, 0, tzinfo=ET), "es", money_label=_money, name="Vic")
        assert "🗓 Corte 15/11 - 28/11: 4 h 00 min" in sun, "domingo 00:00 ET: corte nuevo"
        assert "Semana: 8 h 00 min de 40 h" in sun, "semana desde el domingo 00:00 ET (4 h del turno que cruzo + 4 h)"
        a_sun = await us_payroll.bot_summary(db, cid, ana, datetime(2026, 11, 15, 12, 0, tzinfo=CT), "es", money_label=_money, name="Ana")
        assert "Corte 02/11 - 15/11: 4 h 00 min" in a_sun, "Alabama: el domingo sigue en el corte viejo"
        a_mon = await us_payroll.bot_summary(db, cid, ana, datetime(2026, 11, 16, 10, 0, tzinfo=CT), "es", money_label=_money, name="Ana")
        assert "Corte 16/11 - 29/11: 2 h 00 min" in a_mon and "Semana: 2 h 00 min de 40 h" in a_mon, "Alabama reinicia el lunes"


@pytest.mark.asyncio
async def test_script_guarda_virginia_por_operacion(maker):
    spec = importlib.util.spec_from_file_location("voltage_cortes_pago_b", Path(__file__).resolve().parents[1] / "scripts" / "voltage_cortes_pago.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    async with maker() as db:
        await db.execute(text("""CREATE TABLE IF NOT EXISTS admin_audit_log (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), at timestamptz, actor text,
                                 ip text, method text, path text, company_id uuid, status_code int, surface text, detail jsonb)"""))
        await db.execute(text("ALTER TABLE company_modules ADD COLUMN IF NOT EXISTS updated_at timestamptz"))
        await db.commit()
        cid = await _company(db, us=True, rules=COMPANY)
        va = await _place(db, cid, "Virginia", "America/New_York")
        al = await _place(db, cid, "Alabama", "America/Chicago")
        out = await mod.apply(db, cid)
        await db.commit()
        assert out["changed"] and out["after"]["places"] == {va: VA_RULES}
        assert (await mod.apply(db, cid))["changed"] is False
        rules = await us_payroll.rules(db, cid)
        from app.services import us_time

        assert us_time.place_rules(rules, va)["week_start_day"] == "sunday" and us_time.place_rules(rules, al)["week_start_day"] == "monday"
        assert (await mod.undo(db, cid))["undone"]
        await db.commit()
        assert "places" not in await us_payroll.rules(db, cid)
