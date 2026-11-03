"""Reglas de tiempo de EE. UU. (FLSA) - app.services.us_time (interruptor us_payroll).

Una sola funcion para el bot, Reportes, Nomina, PDF y CSV. Pura: sin base de datos."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.services import us_payroll, us_time

UTC = timezone.utc
RULES = us_time.rules_of({})


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def shift(eid, start, end, breaks=(), tz="America/New_York", **extra):
    return {"employee_id": eid, "start": at(start), "end": at(end), "breaks": [(at(a), at(b)) for a, b in breaks], "tz": tz, **extra}


# ------------------------------------------------------------ caso real: Caso, 2 nov 2026
YESSENIA = shift("y", "2026-11-02T11:45:41.218018+00:00", "2026-11-02T21:25:20.056547+00:00",
                 [("2026-11-02T15:34:55.518899+00:00", "2026-11-02T16:29:10.314277+00:00")])


def test_caso_real_punches_8h45_payable_no_overtime_in_virginia_time():
    [s] = us_time.in_period(us_time.compute([YESSENIA], RULES), date(2026, 11, 2), date(2026, 11, 2))
    assert (s["connected"], s["pause"], s["payable"]) == (9 * 60 + 40, 55, 8 * 60 + 45), "9h40 en turno - 55 min de pausa = 8h45"
    assert (s["regular"], s["overtime"]) == (525, 0), "sin extra por dia: 8h45 son regulares (semana < 40 h)"
    tz = us_time.zone("America/New_York")
    assert s["split"]["start"].astimezone(tz).strftime("%H:%M") == "06:45", "entrada 06:45 ET (el reporte mostraba 05:45, hora de Chicago)"
    assert s["split"]["end"].astimezone(tz).strftime("%H:%M") == "16:25", "salida 16:25 ET = 4:25 PM que vio en su celular"
    assert us_time.abbr("America/New_York") == "ET" and us_time.abbr("America/Chicago") == "CT"
    (b0, b1), = s["split"]["breaks"]
    assert (b0.astimezone(tz).strftime("%H:%M"), b1.astimezone(tz).strftime("%H:%M")) == ("10:34", "11:29")


def _week(hours_by_day: list[float], tz="America/Chicago", start="2026-11-01"):
    """Un turno por dia desde el domingo `start` a las 07:00 locales, sin pausas."""
    zone = us_time.zone(tz)
    out = []
    base = datetime.fromisoformat(start)
    for i, h in enumerate(hours_by_day):
        if not h:
            continue
        a = (base + timedelta(days=i)).replace(hour=7, tzinfo=zone)
        out.append({"employee_id": "w", "start": a.astimezone(UTC), "end": (a + timedelta(minutes=round(h * 60))).astimezone(UTC), "breaks": [], "tz": tz})
    return out


def test_45_hours_in_a_week_is_40_regular_plus_5_overtime_chronologically():
    shifts = us_time.in_period(us_time.compute(_week([0, 9, 9, 9, 9, 9]), RULES), date(2026, 11, 1), date(2026, 11, 7))
    assert sum(s["payable"] for s in shifts) == 45 * 60
    assert sum(s["regular"] for s in shifts) == 40 * 60 and sum(s["overtime"] for s in shifts) == 5 * 60
    friday = shifts[-1]
    assert (friday["regular"], friday["overtime"]) == (4 * 60, 5 * 60), "las horas despues de la 40 (viernes) son overtime"
    assert all(s["overtime"] == 0 for s in shifts[:-1])


def test_9_hours_in_one_day_of_a_36_hour_week_has_no_overtime():
    shifts = us_time.in_period(us_time.compute(_week([0, 9, 9, 9, 9]), RULES), date(2026, 11, 1), date(2026, 11, 7))
    assert sum(s["payable"] for s in shifts) == 36 * 60 and sum(s["overtime"] for s in shifts) == 0


def test_15_and_45_minute_breaks_are_both_unpaid():
    s = shift("p", "2026-11-03T07:00:00-05:00", "2026-11-03T16:00:00-05:00",
              [("2026-11-03T09:00:00-05:00", "2026-11-03T09:15:00-05:00"), ("2026-11-03T12:00:00-05:00", "2026-11-03T12:45:00-05:00")])
    [r] = us_time.in_period(us_time.compute([s], RULES), None, None)
    assert (r["connected"], r["pause"], r["payable"]) == (540, 60, 480), "15 + 45 min: ninguna pausa se paga"


def test_exact_minutes_no_rounding_to_quarter_hours():
    s = shift("m", "2026-11-03T07:07:59-05:00", "2026-11-03T15:14:01-05:00")
    [r] = us_time.in_period(us_time.compute([s], RULES), None, None)
    assert r["payable"] == 8 * 60 + 7, "07:07 -> 15:14 = 8h07, sin redondear a 15 min"


def test_virginia_and_alabama_show_their_own_local_time_and_day():
    va = shift("va", "2026-11-03T04:30:00+00:00", "2026-11-03T12:30:00+00:00", tz="America/New_York")
    al = shift("al", "2026-11-03T04:30:00+00:00", "2026-11-03T12:30:00+00:00", tz="America/Chicago")
    r_va, r_al = us_time.in_period(us_time.compute([va, al], RULES), None, None)
    assert [d["date"] for d in r_va["days"]] == [date(2026, 11, 2), date(2026, 11, 3)], "Virginia: 23:30 ET del 2 -> cruza la medianoche"
    assert [d["date"] for d in r_al["days"]] == [date(2026, 11, 2), date(2026, 11, 3)]
    assert r_va["days"][0]["payable"] == 30 and r_al["days"][0]["payable"] == 90, "medianoche de cada lugar"


def test_shift_crossing_midnight_and_week_start_splits_days_and_weeks():
    # Sabado 7 nov 20:00 CT -> domingo 8 nov 04:00 CT; esa semana ya tenia 38 h.
    shifts = _week([0, 9.5, 9.5, 9.5, 9.5]) + [shift("w", "2026-11-07T20:00:00-06:00", "2026-11-08T04:00:00-06:00", tz="America/Chicago")]
    computed = us_time.compute(shifts, RULES)
    night = us_time.in_period(computed, None, None)[-1]
    assert [(d["date"], d["payable"], d["regular"], d["overtime"]) for d in night["days"]] == [
        (date(2026, 11, 7), 240, 120, 120),   # sabado: 38 h + 2 h = 40; las otras 2 h son overtime
        (date(2026, 11, 8), 240, 240, 0),     # domingo 00:00: semana nueva, el contador vuelve a 0
    ]
    weeks = us_time.weeks_of(us_time.in_period(computed, None, None))
    assert [(w["week_start"].date(), w["payable"], w["regular"], w["overtime"]) for w in weeks] == [
        (date(2026, 11, 1), 42 * 60, 40 * 60, 2 * 60), (date(2026, 11, 8), 4 * 60, 4 * 60, 0)]


def test_week_start_is_configurable_day_and_hour():
    rules = us_time.rules_of({"week_start_day": "monday", "week_start_time": "06:00"})
    tz = us_time.zone("America/Chicago")
    assert us_time.week_start(datetime(2026, 11, 2, 5, 59, tzinfo=tz), rules) == datetime(2026, 10, 26, 6, 0, tzinfo=tz)
    assert us_time.week_start(datetime(2026, 11, 2, 6, 0, tzinfo=tz), rules) == datetime(2026, 11, 2, 6, 0, tzinfo=tz)
    assert us_time.week_start(datetime(2026, 11, 4, 12, 0, tzinfo=tz), RULES) == datetime(2026, 11, 1, 0, 0, tzinfo=tz), "por defecto domingo 00:00"
    assert us_time.rules_of({"week_start_day": "funday", "week_start_time": "25:00", "overtime_after_minutes": "x"}) == us_time.DEFAULT_RULES


def test_dst_change_week_counts_real_minutes():
    # 1 nov 2026 termina el horario de verano: 01:00-02:00 se repite (25 h ese dia).
    s = shift("d", "2026-11-01T00:00:00-05:00", "2026-11-01T03:00:00-06:00", tz="America/Chicago")
    [r] = us_time.in_period(us_time.compute([s], RULES), None, None)
    assert r["payable"] == 4 * 60, "00:00 CDT -> 03:00 CST son 4 horas reales"


def test_money_pending_without_rate_never_zero_and_overtime_at_one_and_a_half():
    pending = us_payroll.pay(40 * 60, 5 * 60, Decimal("0"), 1.5, Decimal("0"))
    assert pending["rate_pending"] and pending["gross"] is None and pending["net"] is None and pending["regular_amount"] is None
    paid = us_payroll.pay(40 * 60, 5 * 60, Decimal("20.00"), 1.5, Decimal("50.00"))
    assert (paid["regular_amount"], paid["overtime_rate"], paid["overtime_amount"], paid["gross"], paid["net"]) == (800.0, 30.0, 150.0, 950.0, 900.0)


# ------------------------------------------------------------ rutas PDF / CSV: sesion desde el primer dia
def test_export_routes_require_session_and_are_registered():
    from app.api.v1 import router as v1
    from app.api.v1.endpoints import us_payroll as api

    routes = list(api.router.routes)
    assert len(routes) == 2
    for r in routes:
        assert api.reader in [d.call for d in r.dependant.dependencies], f"{r.path} sin sesión"
    paths = {getattr(r, "path", "") for r in v1.api_router.routes}
    assert {"/us-payroll/companies/{company_id}/export.pdf", "/us-payroll/companies/{company_id}/export.csv"} <= paths


def test_reader_401_without_session_403_other_role_404_switch_off(monkeypatch):
    import asyncio
    import uuid
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.api import deps
    from app.api.v1.endpoints import us_payroll as api
    from app.web import admin_v2_routes

    async def no_admin(request, db):
        return False

    monkeypatch.setattr(admin_v2_routes, "_active_session", no_admin)
    cid = uuid.uuid4()

    async def no_token(db, authorization, company_id, **kw):
        raise HTTPException(status_code=401, detail="missing_token")

    monkeypatch.setattr(deps, "require_company_user_for_tenant", no_token)
    for expected, user, on in [(401, None, True), (403, SimpleNamespace(role="operario", full_name="x"), True),
                               (404, SimpleNamespace(role="gerencia", full_name="Dir"), False)]:
        if user is not None:
            async def as_user(db, authorization, company_id, _u=user, **kw):
                return _u
            monkeypatch.setattr(deps, "require_company_user_for_tenant", as_user)

        async def switch(db, company_id, _on=on):
            return _on
        monkeypatch.setattr(us_payroll, "is_on", switch)
        try:
            asyncio.run(api.reader(cid, SimpleNamespace(), None, None))
            raise AssertionError("debía fallar")
        except HTTPException as exc:
            assert exc.status_code == expected

    async def switch_on(db, company_id):
        return True
    monkeypatch.setattr(us_payroll, "is_on", switch_on)
    assert asyncio.run(api.reader(cid, SimpleNamespace(), None, None)) == "Dir", "dueño / director con el interruptor: pasa"


def test_bot_shift_end_uses_the_same_rule_and_never_fails_the_checkout(monkeypatch):
    import asyncio
    import contextlib
    import uuid
    from types import SimpleNamespace

    from app.api.v1.endpoints import bots

    class DB:
        def begin_nested(self):
            return contextlib.AsyncExitStack()

    employee = SimpleNamespace(company_id=uuid.uuid4(), id=uuid.uuid4(), full_name="Caso ")
    calls = []

    async def on(db, company_id):
        return True

    async def summary(db, company_id, employee_id, ended_at, language, money_label, name=""):
        calls.append((language, name))
        return "Feliz descanso, Caso.\n✅ Tiempo pagable de hoy: 8 h 45 min"

    monkeypatch.setattr(us_payroll, "is_on", on)
    monkeypatch.setattr(us_payroll, "bot_summary", summary)
    ended = datetime(2026, 11, 2, 21, 25, tzinfo=UTC)
    msg = asyncio.run(bots._shift_end_summary_message(DB(), employee=employee, started_at=None, ended_at=ended, language="es"))
    assert msg.startswith("🏁 Turno finalizado.\n\nFeliz descanso, Caso.") and calls == [("es", "Caso")]

    async def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(us_payroll, "bot_summary", boom)
    assert asyncio.run(bots._shift_end_summary_message(DB(), employee=employee, started_at=None, ended_at=ended, language="es")) == "🏁 Turno finalizado."

    async def off(db, company_id):
        return False

    monkeypatch.setattr(us_payroll, "is_on", off)
    assert asyncio.run(bots._shift_end_summary_message(DB(), employee=employee, started_at=None, ended_at=ended, language="es")) == "🏁 Turno finalizado.", \
        "apagado: el flujo de siempre (sin inicio no hay proyeccion)"


def test_whatsapp_payroll_reply_says_pending_without_rate():
    from datetime import date as d_

    from app.api.v1.endpoints import bots

    row = {"employee_name": "Caso", "closed_shifts": 1, "regular_minutes": 525, "extra_minutes": 0, "gross_amount": 0.0, "discount_amount": 0.0,
           "net_amount": 0.0, "rate_pending": True}
    text_ = bots._format_payroll_row(row, d_(2026, 11, 1), d_(2026, 11, 7))
    assert "Pendiente" in text_ and "$0" not in text_.replace("$0,", "")
    plain = bots._format_payroll_row({**row, "rate_pending": False, "gross_amount": 10, "net_amount": 10}, d_(2026, 11, 1), d_(2026, 11, 7))
    assert "Pendiente" not in plain, "con tarifa (u otra empresa): el dinero de siempre"
