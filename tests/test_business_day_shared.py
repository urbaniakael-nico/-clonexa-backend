"""Fase B · una sola regla de jornada (app/services/business_day.py).

The Time Machine opera 18:00-04:00: toda la noche es UN dia de negocio. Una
venta a las 02:00 del 12/10 es del 11/10 en Reportes, KPIs y el reporte del
dueno, y los tres dan el mismo total por dia. Sin jornada: medianoche local.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.api.v1.endpoints import hospitality as hsp
from app.api.v1.endpoints import kpis, reports
from app.services import business_day
from app.services import company_locale as cl
from app.services import owner_report as engine

BOG = ZoneInfo("America/Bogota")
TTM_SETTINGS = {"hospitality_business_day": {"open": "18:00", "close": "04:00"}}
CFG = business_day.config(TTM_SETTINGS)
TTM = {"currency": "COP", "timezone": "America/Bogota", "language": "es", "business_day": business_day.public(CFG)}
PLAIN = {"currency": "COP", "timezone": "America/Bogota", "language": "es", "business_day": None}


def at(day: str, hh: int, mm: int = 0) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=BOG).astimezone(timezone.utc)


def order(oid: str, created: datetime, total: int) -> dict:
    return {"id": oid, "order_number": oid, "created_at": created.isoformat(), "closed_at": (created + timedelta(minutes=30)).isoformat(),
            "status": "cerrado", "total": total, "payment_method": "cash", "table_number": "Mesa 1", "table_key": "mesa 1", "source": "qr",
            "items": [{"name": "Cerveza", "quantity": 1, "unit_price": total, "subtotal": total}], "metadata": {}}


ORDERS = [
    order("a", at("2026-10-11", 20), 30000),   # noche del 11
    order("b", at("2026-10-12", 2), 50000),    # 02:00 del 12 -> noche del 11
    order("c", at("2026-10-12", 3, 59), 7000),  # 03:59 del 12 -> noche del 11
    order("d", at("2026-10-12", 4), 9000),     # 04:00 del 12 -> dia 12
    order("e", at("2026-10-12", 21), 12000),   # noche del 12
]
EXPECTED = {"2026-10-11": 87000.0, "2026-10-12": 21000.0}


def in_company(locale, fn, *args):
    tokens = cl.use(locale)
    try:
        return fn(*args)
    finally:
        cl.reset(tokens)


def test_one_rule_everywhere():
    assert business_day.business_date(at("2026-10-12", 2), BOG, CFG) == date(2026, 10, 11)
    assert business_day.business_date(at("2026-10-12", 4), BOG, CFG) == date(2026, 10, 12)
    assert business_day.business_date(at("2026-10-12", 2), BOG, None) == date(2026, 10, 12), "sin jornada: medianoche"
    # Hospitality, libro de ventas y reporte del dueno usan la misma funcion.
    assert hsp._hsp_business_day_config(TTM_SETTINGS) == CFG
    assert hsp._hsp_business_date(at("2026-10-12", 2), "America/Bogota", CFG) == date(2026, 10, 11)
    from app.services import sales_ledger

    assert sales_ledger.business_date(at("2026-10-12", 2), BOG, CFG) == date(2026, 10, 11)
    # Jornada de un solo dia (08:00-22:00): medianoche como siempre.
    day_only = business_day.config({"hospitality_business_day": {"open": "08:00", "close": "22:00"}})
    assert business_day.day_start(date(2026, 10, 11), BOG, day_only) == datetime(2026, 10, 11, tzinfo=BOG)


def test_reports_and_kpis_cut_at_the_close_of_the_jornada():
    for fn in (kpis.period_from_params, reports.parse_period):
        start, end, _ = in_company(TTM, fn, "custom", date(2026, 10, 11), date(2026, 10, 11))
        assert start == at("2026-10-11", 4) and end == at("2026-10-12", 4) - timedelta(microseconds=1), "el dia 11 va de 04:00 a 03:59:59 del 12"
        start, end, _ = in_company(PLAIN, fn, "custom", date(2026, 10, 11), date(2026, 10, 11))
        assert start == at("2026-10-11", 0) and end == at("2026-10-12", 0) - timedelta(microseconds=1), "sin jornada: medianoche"
    assert in_company(TTM, reports.day_key, at("2026-10-12", 2)) == "2026-10-11"
    assert in_company(PLAIN, reports.day_key, at("2026-10-12", 2)) == "2026-10-12"


def test_sale_at_2am_same_daily_totals_in_reports_kpis_and_owner_report():
    # Reportes de Hospitality (lo que ve The Time Machine en Reportes).
    hosp = hsp._hsp_business_aggregate([dict(o) for o in ORDERS], [], [], [], "daily", "America/Bogota", CFG,
                                       now=at("2026-10-13", 12))["daily_totals"]
    hosp_totals = {d: v["total"] for d, v in hosp.items()}
    # KPIs / Reportes del portal: la ventana de cada dia (period_from_params) y su dia (day_key).
    kpi_totals: dict[str, float] = defaultdict(float)
    for day in (date(2026, 10, 11), date(2026, 10, 12)):
        start, end, _ = in_company(TTM, kpis.period_from_params, "custom", day, day)
        for o in ORDERS:
            if start <= datetime.fromisoformat(o["created_at"]) <= end:
                kpi_totals[day.isoformat()] += o["total"]
    report_totals: dict[str, float] = defaultdict(float)
    for o in ORDERS:
        report_totals[in_company(TTM, reports.day_key, datetime.fromisoformat(o["created_at"]))] += o["total"]
    # Reporte del dueno.
    per = engine.resolve_period("custom", date(2026, 10, 13), date(2026, 10, 11), date(2026, 10, 12))
    rep = engine.Report(orders=[dict(o) for o in ORDERS], closures=[], inventory={}, portions={}, tz=BOG, period=per,
                        business_day={"open": time(18), "close": time(4), "overnight": True})
    owner_totals = {d["date"]: float(d["sales"]) for d in rep.daily()["days"]}
    assert hosp_totals == EXPECTED
    assert dict(kpi_totals) == EXPECTED
    assert dict(report_totals) == EXPECTED
    assert owner_totals == EXPECTED


def test_locale_carries_the_jornada_for_the_portal():
    assert TTM["business_day"] == {"open": "18:00", "close": "04:00", "overnight": True}
    assert in_company(TTM, cl.current_business_day) == CFG
    assert in_company(PLAIN, cl.current_business_day) is None
    assert cl.current_business_day() is None
