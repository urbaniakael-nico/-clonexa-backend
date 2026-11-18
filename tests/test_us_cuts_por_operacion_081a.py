"""081A: semana laboral y cortes POR OPERACION dentro de la empresa (VOLTAGE). Virginia domingo a
sabado con ancla domingo 01/11/2026; Alabama sin ajuste propio = la empresa (lunes, ancla 02/11).
Regla pura (app.services.us_time), sin base de datos."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services import us_time

ET = ZoneInfo("America/New_York")
VA, AL = "place-va", "place-al"
COMPANY = us_time.rules_of({"week_start_day": "monday", "week_start_time": "00:00", "pay_period": {"type": "biweekly", "anchor": "2026-11-02"},
                            "places": {VA: {"week_start_day": "sunday", "pay_period": {"type": "biweekly", "anchor": "2026-11-01"}}}})
D = date


def test_each_operation_has_its_own_week_and_cut_and_falls_back_to_the_company():
    va, al = us_time.place_rules(COMPANY, VA), us_time.place_rules(COMPANY, AL)
    assert va["week_start_day"] == "sunday" and va["pay_period"] == {"type": "biweekly", "anchor": "2026-11-01"}
    assert al["week_start_day"] == "monday" and al["pay_period"] == {"type": "biweekly", "anchor": "2026-11-02"}, "sin ajuste propio: la empresa"
    assert us_time.place_rules(COMPANY, None) == al
    assert "places" not in va and va["overtime_after_minutes"] == 2400


def test_virginia_cuts_sunday_to_saturday_from_01_nov():
    va = us_time.place_rules(COMPANY, VA)
    assert us_time.span_for(D(2026, 11, 1), va, "cut") == (D(2026, 11, 1), D(2026, 11, 14))
    assert us_time.span_for(D(2026, 11, 14), va, "cut") == (D(2026, 11, 1), D(2026, 11, 14))
    assert us_time.span_for(D(2026, 11, 15), va, "cut") == (D(2026, 11, 15), D(2026, 11, 28))
    assert us_time.span_for(D(2026, 11, 29), va, "cut") == (D(2026, 11, 29), D(2026, 12, 12))
    assert us_time.span_for(D(2026, 12, 13), va, "cut") == (D(2026, 12, 13), D(2026, 12, 26))
    assert us_time.span_for(D(2026, 11, 18), va, "week") == (D(2026, 11, 15), D(2026, 11, 21)), "semana domingo a sabado"
    assert us_time.cut_label(D(2026, 11, 15), D(2026, 11, 28)) == "Corte 15/11 - 28/11"


def test_alabama_cuts_unchanged():
    al = us_time.place_rules(COMPANY, AL)
    assert us_time.span_for(D(2026, 11, 15), al, "cut") == (D(2026, 11, 2), D(2026, 11, 15))
    assert us_time.span_for(D(2026, 11, 16), al, "cut") == (D(2026, 11, 16), D(2026, 11, 29))
    assert us_time.span_for(D(2026, 11, 30), al, "cut") == (D(2026, 11, 30), D(2026, 12, 13))
    assert us_time.span_for(D(2026, 11, 18), al, "week") == (D(2026, 11, 16), D(2026, 11, 22))


def test_bad_place_overrides_are_ignored():
    r = us_time.rules_of({"week_start_day": "monday", "places": {VA: {"week_start_day": "funday", "pay_period": {"type": "x"}}, "": {"week_start_day": "sunday"}, AL: "x"}})
    assert us_time.place_rules(r, VA)["week_start_day"] == "monday"
    assert "pay_period" not in us_time.place_rules(r, VA)


def _day(d, hours):
    """Turno de la tabla del supervisor: 7:00, almuerzo 12:00-12:30 (salvo 2 h), salida segun horas."""
    start = datetime(2026, 11, d, 7, 0, tzinfo=ET)
    if hours == 2:
        return {"employee_id": "kewin", "start": start, "end": datetime(2026, 11, d, 9, 0, tzinfo=ET), "breaks": [], "tz": "America/New_York"}
    end_h = {12: (19, 30), 10: (17, 30), 8: (15, 30)}[hours]
    return {"employee_id": "kewin", "start": start, "end": datetime(2026, 11, d, *end_h, tzinfo=ET),
            "breaks": [(datetime(2026, 11, d, 12, 0, tzinfo=ET), datetime(2026, 11, d, 12, 30, tzinfo=ET))], "tz": "America/New_York"}


def test_overtime_per_virginia_week_kewin_132_h():
    va = us_time.place_rules(COMPANY, VA)
    shifts = [_day(d, 12) for d in (2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13)]
    for s in shifts:
        s["rules"] = va
    period = us_time.in_period(us_time.compute(shifts, COMPANY), D(2026, 11, 1), D(2026, 11, 14))
    weeks = [(w["week_start"].date().isoformat(), w["payable"], w["overtime"]) for w in us_time.weeks_of(period)]
    assert weeks == [("2026-11-01", 72 * 60, 32 * 60), ("2026-11-08", 60 * 60, 20 * 60)]
    assert (sum(s["payable"] for s in period), sum(s["regular"] for s in period), sum(s["overtime"] for s in period)) == (132 * 60, 80 * 60, 52 * 60)
    # con la semana de la empresa (lunes) el reparto seria otro: la regla de la operacion manda
    mon = us_time.in_period(us_time.compute([{k: v for k, v in s.items() if k != "rules"} for s in shifts], COMPANY), D(2026, 11, 1), D(2026, 11, 14))
    assert [w["week_start"].date().isoformat() for w in us_time.weeks_of(mon)] == ["2026-11-02", "2026-11-09"]


def test_kerim_2_hour_day_and_mixed_days():
    va = us_time.place_rules(COMPANY, VA)
    table = {1: 8, 2: 12, 3: 12, 4: 12, 5: 8, 6: 2, 9: 8, 10: 8, 11: 8, 12: 8, 13: 8}
    shifts = [{**_day(d, h), "rules": va} for d, h in table.items()]
    period = us_time.in_period(us_time.compute(shifts, COMPANY), D(2026, 11, 1), D(2026, 11, 14))
    assert [(w["payable"], w["overtime"]) for w in us_time.weeks_of(period)] == [(54 * 60, 14 * 60), (40 * 60, 0)]
