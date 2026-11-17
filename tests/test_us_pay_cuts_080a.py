"""080A: cortes de pago cada 2 semanas (lunes a domingo) con ancla el lunes 02/11/2026 y overtime
por semana laboral dentro del corte. Regla pura (app.services.us_time), sin base de datos."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services import us_time

CT = ZoneInfo("America/Chicago")
RULES = us_time.rules_of({"week_start_day": "monday", "week_start_time": "00:00", "pay_period": {"type": "biweekly", "anchor": "2026-11-02"}})
# La tabla del ajuste de Alabama (02-14 nov 2026): dia -> (entrada, almuerzo, salida)
TABLE = {
    2: ("06:00", "12:00", "13:00", "16:30"), 3: ("06:00", "11:00", "12:00", "18:30"), 4: ("06:00", "11:00", "12:00", "16:30"),
    5: ("06:00", "11:00", "12:00", "16:30"), 6: ("06:00", "11:00", "12:00", "18:30"), 9: ("06:00", "11:00", "12:00", "17:30"),
    10: ("06:00", "11:00", "12:00", "17:30"), 11: ("06:00", "11:00", "12:00", "17:30"), 12: ("07:00", "11:00", "12:00", "17:30"),
    13: ("07:00", "11:00", "12:00", "17:30"), 14: ("07:00", "11:00", "12:00", "17:30"),
}


def at(day: int, hhmm: str) -> datetime:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime(2026, 11, day, hh, mm, tzinfo=CT)


def shifts(days) -> list[dict]:
    return [{"employee_id": "x", "start": at(d, TABLE[d][0]), "end": at(d, TABLE[d][3]), "breaks": [(at(d, TABLE[d][1]), at(d, TABLE[d][2]))],
             "tz": "America/Chicago"} for d in days]


def totals(days, start=date(2026, 11, 2), end=date(2026, 11, 15)):
    period = us_time.in_period(us_time.compute(shifts(days), RULES), start, end)
    weeks = us_time.weeks_of(period)
    return ([(w["week_start"].date().isoformat(), w["payable"], w["regular"], w["overtime"], w["pause"]) for w in weeks],
            sum(s["payable"] for s in period), sum(s["regular"] for s in period), sum(s["overtime"] for s in period))


def test_cuts_every_two_weeks_from_the_anchor_including_30_nov():
    D = date
    assert us_time.cut_for(D(2026, 11, 2), RULES) == (D(2026, 11, 2), D(2026, 11, 15))
    assert us_time.cut_for(D(2026, 11, 15), RULES) == (D(2026, 11, 2), D(2026, 11, 15))
    assert us_time.cut_for(D(2026, 11, 16), RULES) == (D(2026, 11, 16), D(2026, 11, 29))
    assert us_time.cut_for(D(2026, 11, 29), RULES) == (D(2026, 11, 16), D(2026, 11, 29))
    assert us_time.cut_for(D(2026, 11, 30), RULES) == (D(2026, 11, 30), D(2026, 12, 13)), "30/11 abre corte"
    assert us_time.cut_for(D(2026, 12, 14), RULES) == (D(2026, 12, 14), D(2026, 12, 27))
    assert us_time.cut_for(D(2026, 12, 28), RULES) == (D(2026, 12, 28), D(2027, 1, 10))
    assert us_time.cut_for(D(2026, 11, 1), RULES) == (D(2026, 10, 19), D(2026, 11, 1)), "antes del ancla: el corte anterior"
    for n in range(60):  # siempre lunes a domingo
        start, end = us_time.cut_for(D(2026, 11, 2) + timedelta(days=n), RULES)
        assert start.weekday() == 0 and end.weekday() == 6 and (end - start).days == 13


def test_labels_and_cut_info_only_for_an_exact_cut():
    assert us_time.cut_label(date(2026, 11, 16), date(2026, 11, 29)) == "Corte 16/11 - 29/11"
    assert us_time.cut_label(date(2026, 12, 28), date(2027, 1, 10)) == "Corte 28/12/2026 - 10/01/2027"
    assert us_time.cut_label(date(2026, 11, 16), date(2026, 11, 29), "en") == "Pay period 16/11 - 29/11"
    assert us_time.cut_info(date(2026, 11, 2), date(2026, 11, 15), RULES) == {"start": "2026-11-02", "end": "2026-11-15", "label": "Corte 02/11 - 15/11"}
    assert us_time.cut_info(date(2026, 11, 2), date(2026, 11, 8), RULES) is None, "una semana no es un corte"
    assert us_time.cut_info(date(2026, 11, 2), date(2026, 11, 15), us_time.rules_of({})) is None, "sin ajuste no hay cortes"


def test_pay_period_is_a_company_setting_and_bad_values_are_ignored():
    assert RULES["pay_period"] == {"type": "biweekly", "anchor": "2026-11-02"} and RULES["week_start_day"] == "monday"
    assert "pay_period" not in us_time.rules_of({}), "otras empresas: nada cambia"
    for bad in ({"type": "biweekly"}, {"type": "monthly", "anchor": "2026-11-02"}, {"type": "biweekly", "anchor": "02/11/2026"}, "x", None):
        assert "pay_period" not in us_time.rules_of({"pay_period": bad})
    assert us_time.cut_for(date(2026, 11, 20), us_time.rules_of({"pay_period": {"type": "weekly", "anchor": "2026-11-02"}})) == (date(2026, 11, 16), date(2026, 11, 22))


def test_overtime_is_per_week_inside_the_cut_alabama_table():
    weeks, payable, regular, overtime = totals(TABLE)
    assert weeks == [("2026-11-02", 3090, 2400, 690, 300), ("2026-11-09", 3600, 2400, 1200, 360)], "51.5 h (11.5 OT) + 60 h (20 OT)"
    assert (payable, regular, overtime) == (6690, 4800, 1890), "111.5 h = 80 regulares + 31.5 overtime"


def test_brandon_and_giselle_without_9_10_11_nov():
    weeks, payable, regular, overtime = totals([d for d in TABLE if d not in (9, 10, 11)])
    assert weeks == [("2026-11-02", 3090, 2400, 690, 300), ("2026-11-09", 1710, 1710, 0, 180)], "51.5 h (11.5 OT) + 28.5 h (0 OT)"
    assert (payable, regular, overtime) == (4800, 4110, 690), "80 h = 68.5 regulares + 11.5 overtime"


def test_sunday_week_start_would_split_differently_so_the_rule_matters():
    sunday = us_time.rules_of({"week_start_day": "sunday"})
    period = us_time.in_period(us_time.compute(shifts(TABLE), sunday), date(2026, 11, 2), date(2026, 11, 15))
    assert [w["week_start"].date().isoformat() for w in us_time.weeks_of(period)] == ["2026-11-01", "2026-11-08"]
    # con domingo los 11 dias caen igual en 2 semanas; con lunes la semana 2 incluye el domingo 15
    assert us_time.week_start(at(15, "10:00"), RULES).date() == date(2026, 11, 9)
    assert us_time.week_start(at(15, "10:00"), sunday).date() == date(2026, 11, 15)
