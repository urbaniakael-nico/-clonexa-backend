"""080A: cortes de pago de VOLTAGE contra Postgres REAL (pgserver): Nomina del corte 02-15 nov con
overtime por semana, CSV/PDF con las semanas del corte, contador del bot que arranca en cero el
lunes del corte (hora de cada operacion), "quincena" por chat = corte actual y el script que guarda
el ajuste de la empresa. Otra empresa sin el ajuste: nada cambia. Si pgserver no esta, se salta."""
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

CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")
CUT_RULES = {"week_start_day": "monday", "week_start_time": "00:00", "pay_period": {"type": "biweekly", "anchor": "2026-11-02"}}
TABLE = {2: ("06:00", ("12:00", "13:00"), "16:30"), 3: ("06:00", ("11:00", "12:00"), "18:30"), 4: ("06:00", ("11:00", "12:00"), "16:30"),
         5: ("06:00", ("11:00", "12:00"), "16:30"), 6: ("06:00", ("11:00", "12:00"), "18:30"), 9: ("06:00", ("11:00", "12:00"), "17:30"),
         10: ("06:00", ("11:00", "12:00"), "17:30"), 11: ("06:00", ("11:00", "12:00"), "17:30"), 12: ("07:00", ("11:00", "12:00"), "17:30"),
         13: ("07:00", ("11:00", "12:00"), "17:30"), 14: ("07:00", ("11:00", "12:00"), "17:30")}


def _money(v):
    return f"${v}"


async def _day(db, cid, eid, day: date, start: str, lunch: tuple, end: str, tz=CT):
    def at(hhmm):
        hh, mm = (int(x) for x in hhmm.split(":"))
        return datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)

    await _ev(db, cid, eid, "check_in", at(start))
    await _ev(db, cid, eid, "break_start", at(lunch[0]))
    await _ev(db, cid, eid, "break_end", at(lunch[1]))
    await _ev(db, cid, eid, "check_out", at(end))


@pytest.mark.asyncio
async def test_cut_02_15_nov_overtime_per_week_and_bot_counter_restarts_on_16_nov(maker):
    async with maker() as db:
        cid = await _company(db, us=True, rules=CUT_RULES)
        # como VOLTAGE: turno abierto hasta 15 h (06:00-18:30 no queda por confirmar)
        await db.execute(text("INSERT INTO workforce_session_policy (company_id, alert_after_hours) VALUES (CAST(:c AS uuid), 15)"), {"c": cid})
        await db.commit()
        al = await _place(db, cid, "Alabama", "America/Chicago")
        va = await _place(db, cid, "Virginia", "America/New_York")
        ana = await _person(db, cid, "Ana Alabama", al)
        vic = await _person(db, cid, "Vic Virginia", va)
        for d, (a, lunch, b) in TABLE.items():
            await _day(db, cid, ana, date(2026, 11, d), a, lunch, b)
        await _day(db, cid, ana, date(2026, 11, 16), "06:00", ("11:00", "12:00"), "16:30")  # corte nuevo: 9.5 h
        # Virginia: el corte arranca a las 00:00 de SU hora (domingo 15 23:30 ET es del corte viejo)
        await _day(db, cid, vic, date(2026, 11, 15), "20:00", ("21:00", "21:30"), "23:30", tz=ET)
        await _day(db, cid, vic, date(2026, 11, 16), "08:00", ("12:00", "12:30"), "12:30", tz=ET)

        snap = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 2), date(2026, 11, 15))
        assert snap["us_payroll"]["cut"] == {"start": "2026-11-02", "end": "2026-11-15", "label": "Corte 02/11 - 15/11"}
        assert snap["us_payroll"]["rules"]["pay_period"] == {"type": "biweekly", "anchor": "2026-11-02"}
        row = {r["employee_name"]: r for r in snap["rows"]}["Ana Alabama"]
        assert (row["us"]["payable_minutes"], row["regular_minutes"], row["extra_minutes"], row["us"]["pause_minutes"]) == (6690, 4800, 1890, 660)
        assert [(w["week_start"], w["week_end"], w["payable"], w["regular"], w["overtime"]) for w in row["us"]["weeks"]] == [
            ("2026-11-02", "2026-11-08", 3090, 2400, 690), ("2026-11-09", "2026-11-15", 3600, 2400, 1200)]
        lines = us_payroll_export.build_csv(snap).splitlines()
        assert any(x.startswith("Alabama (CT),Ana Alabama,,Semana 1 (02/11-08/11),,,56:30,5:00,51:30,40:00,11:30") for x in lines)
        assert any(x.startswith("Alabama (CT),Ana Alabama,,Semana 2 (09/11-15/11),,,66:00,6:00,60:00,40:00,20:00") for x in lines)
        assert any(x.startswith("Alabama (CT),Ana Alabama,,Total,,,122:30,11:00,111:30,80:00,31:30") for x in lines)
        assert us_payroll_export.build_pdf(snap, "VOLTAGE")[:5] == b"%PDF-"

        nxt = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 16), date(2026, 11, 29))
        assert nxt["us_payroll"]["cut"]["label"] == "Corte 16/11 - 29/11"
        assert {r["employee_name"]: r["us"]["payable_minutes"] for r in nxt["rows"]} == {"Ana Alabama": 570, "Vic Virginia": 240}
        week = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 9), date(2026, 11, 15))
        assert "cut" not in week["us_payroll"], "una semana no es un corte"
        assert not any(",Semana 1 (" in x for x in us_payroll_export.build_csv(week).splitlines()), "sin corte el CSV es el de siempre"

        old = await us_payroll.bot_summary(db, cid, ana, datetime(2026, 11, 14, 17, 30, tzinfo=CT), "es", money_label=_money, name="Ana")
        assert "🗓 Corte 02/11 - 15/11: 111 h 30 min" in old and "Semana: 60 h 00 min de 40 h" in old
        new = await us_payroll.bot_summary(db, cid, ana, datetime(2026, 11, 16, 16, 30, tzinfo=CT), "es", money_label=_money, name="Ana")
        assert "🗓 Corte 16/11 - 29/11: 9 h 30 min" in new and "Semana: 9 h 30 min de 40 h" in new, "arranca en cero el lunes 16"
        en = await us_payroll.bot_summary(db, cid, ana, datetime(2026, 11, 16, 16, 30, tzinfo=CT), "en", money_label=_money, name="Ana")
        assert "Pay period 16/11 - 29/11: 9 h 30 min" in en
        v_old = await us_payroll.bot_summary(db, cid, vic, datetime(2026, 11, 15, 23, 30, tzinfo=ET), "es", money_label=_money, name="Vic")
        v_new = await us_payroll.bot_summary(db, cid, vic, datetime(2026, 11, 16, 12, 30, tzinfo=ET), "es", money_label=_money, name="Vic")
        assert "Corte 02/11 - 15/11: 3 h 00 min" in v_old and "Corte 16/11 - 29/11: 4 h 00 min" in v_new, "lunes 00:00 hora de Virginia"

        other = await _company(db, us=True)
        bob = await _person(db, other, "Bob", await _place(db, other, "Alabama", "America/Chicago"))
        await _day(db, other, bob, date(2026, 11, 16), "06:00", ("11:00", "12:00"), "16:30")
        msg = await us_payroll.bot_summary(db, other, bob, datetime(2026, 11, 16, 16, 30, tzinfo=CT), "es", money_label=_money, name="Bob")
        assert "Corte" not in msg, "sin el ajuste de cortes nada cambia"
        assert "cut" not in (await core.calculate_period_snapshot(db, uuid.UUID(other), date(2026, 11, 2), date(2026, 11, 15)))["us_payroll"]


@pytest.mark.asyncio
async def test_chat_quincena_is_the_current_cut(maker, monkeypatch):
    from app.api.v1.endpoints import bots

    monkeypatch.setattr(bots, "_today_business", lambda: date(2026, 11, 18))
    async with maker() as db:
        cid = uuid.UUID(await _company(db, us=True, rules=CUT_RULES))
        other = uuid.UUID(await _company(db, us=True))
        d16, d18 = date(2026, 11, 16), date(2026, 11, 18)
        assert await bots._cx_pay_cut_period_080a(db, cid, "nomina quincena", d16, d18, "quincena actual") == (d16, d18, "Corte 16/11 - 29/11")
        assert (await bots._cx_pay_cut_period_080a(db, cid, "nomina semana", d16, d18, "semana actual"))[2] == "semana actual"
        assert (await bots._cx_pay_cut_period_080a(db, other, "nomina quincena", d16, d18, "quincena actual"))[2] == "quincena actual"


@pytest.mark.asyncio
async def test_voltage_cortes_script_saves_rules_once_and_undo(maker):
    spec = importlib.util.spec_from_file_location("voltage_cortes_pago", Path(__file__).resolve().parents[1] / "scripts" / "voltage_cortes_pago.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    async with maker() as db:
        await db.execute(text("""CREATE TABLE IF NOT EXISTS admin_audit_log (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), at timestamptz, actor text,
                                 ip text, method text, path text, company_id uuid, status_code int, surface text, detail jsonb)"""))
        await db.execute(text("ALTER TABLE company_modules ADD COLUMN IF NOT EXISTS updated_at timestamptz"))
        await db.commit()
        cid = await _company(db, us=True, rules={"week_start_day": "sunday", "week_start_time": "00:00", "overtime_after_minutes": 2400, "overtime_factor": 1.5})
        other = await _company(db, us=True)
        first = await mod.apply(db, cid)
        await db.commit()
        assert first["changed"] and first["after"]["week_start_day"] == "monday" and first["before"]["week_start_day"] == "sunday"
        assert (await mod.apply(db, cid))["changed"] is False, "repetirlo no cambia nada"
        await db.commit()
        rules = await us_payroll.rules(db, cid)
        assert rules["week_start_day"] == "monday" and rules["pay_period"] == {"type": "biweekly", "anchor": "2026-11-02"} and rules["overtime_after_minutes"] == 2400
        assert "pay_period" not in await us_payroll.rules(db, other), "otra empresa no cambia"
        assert (await mod.undo(db, cid))["undone"]
        await db.commit()
        back = await us_payroll.rules(db, cid)
        assert back["week_start_day"] == "sunday" and "pay_period" not in back
