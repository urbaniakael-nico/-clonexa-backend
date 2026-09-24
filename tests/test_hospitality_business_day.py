"""Jornada por horario (hospitality_business_day), hoy solo The Time Machine.

Bogotá es UTC-5. Jornada 18:00 -> 04:00: una venta a las 02:00 del 24 es de
la jornada del 23; una a las 14:00 del 24 (fuera de la franja) es del 24.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import hospitality as hsp

TZ = "America/Bogota"
CONFIG = hsp._hsp_business_day_config({"hospitality_business_day": {"open": "18:00", "close": "04:00"}})
NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)  # 10:00 del 24 en Bogotá -> jornada del 24


def _order(order_id, created, total, table="Mesa 1", method="cash", status="cerrado", items=None, **extra):
    return {
        "id": order_id, "order_number": f"QR-{order_id}", "created_at": created, "status": status,
        "total": total, "payment_method": method, "table_number": table, "table_key": table.lower(),
        "source": "qr", "items": items or [{"name": "Cerveza Aguila", "quantity": 1, "unit_price": total, "subtotal": total}],
        "metadata": extra.pop("metadata", {}), **extra,
    }


ORDERS = [
    _order("o1", "2026-09-23T23:30:00+00:00", 20000, "Mesa 1", "cash",
           items=[{"name": "Cerveza Aguila", "inventory_item_id": "inv-aguila", "quantity": 4, "unit_price": 5000, "subtotal": 20000}]),
    _order("o2", "2026-09-24T07:00:00+00:00", 30000, "Mesa 2", "transfer",   # 02:00 del 24 -> jornada 23
           items=[{"name": "Aguardiente media", "quantity": 1, "unit_price": 30000, "subtotal": 30000}]),
    _order("o3", "2026-09-24T19:00:00+00:00", 5000, "Mesa 3", "card"),       # 14:00 del 24 -> fuera de franja, jornada 24
    _order("o4", "2026-09-21T23:30:00+00:00", 10000, "Mesa 1", "cash"),      # jornada 21
    _order("o5", "2026-09-24T02:00:00+00:00", 8000, "Mesa 2", status="cancelado",
           cancelled_at="2026-09-24T02:10:00+00:00", metadata={"loss_reason": "Vaso roto"}),  # 21:00 del 23
    _order("o6", "2026-09-16T23:30:00+00:00", 15000, "Mesa 1", "cash"),      # misma jornada semana anterior al 23
]
ACCESSES = [
    {"id": "a1", "table_key": "mesa 1", "table_number": "Mesa 1", "status": "closed", "closes_with_table": True,
     "activated_at": "2026-09-23T23:00:00+00:00", "updated_at": "2026-09-24T01:00:00+00:00",
     "expires_at": "2026-09-24T11:00:00+00:00"},
]
SONGS = [{"id": "s1", "song": "Querida", "created_at": "2026-09-24T06:00:00+00:00"}]  # 01:00 del 24 -> jornada 23
INVENTORY = [{"id": "inv-aguila", "name": "Cerveza Aguila", "stock": 40}, {"id": "inv-agua", "name": "Agua Cristal", "stock": 12}]


def _daily():
    return hsp._hsp_business_aggregate(ORDERS, SONGS, ACCESSES, INVENTORY, "daily", TZ, CONFIG, now=NOW)


def test_hospitality_sale_at_2am_belongs_to_the_previous_jornada():
    assert hsp._hsp_business_date(datetime(2026, 9, 24, 7, 0, tzinfo=timezone.utc), TZ, CONFIG) == date(2026, 9, 23)
    assert hsp._hsp_business_date(datetime(2026, 9, 24, 8, 59, tzinfo=timezone.utc), TZ, CONFIG) == date(2026, 9, 23)  # 03:59
    assert hsp._hsp_business_date(datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc), TZ, CONFIG) == date(2026, 9, 24)   # 04:00
    assert hsp._hsp_business_date(datetime(2026, 9, 24, 19, 0, tzinfo=timezone.utc), TZ, CONFIG) == date(2026, 9, 24)  # 14:00
    start, end = hsp._hsp_business_window(date(2026, 9, 23), TZ, CONFIG)
    assert (start.isoformat(), end.isoformat()) == ("2026-09-23T23:00:00+00:00", "2026-09-24T09:00:00+00:00")


def test_hospitality_jornada_without_closure_does_not_absorb_the_following_days():
    by_day = {row["key"]: row for row in _daily()["periods"]}
    assert by_day["2026-09-21"]["total"] == 10000
    assert by_day["2026-09-22"]["total"] == 0
    assert by_day["2026-09-23"]["total"] == 50000  # 18:30 + la de las 02:00
    assert by_day["2026-09-24"]["total"] == 5000   # 14:00, fuera de franja, no se pierde
    assert by_day["2026-09-23"]["shifts"] == [{
        "id": "2026-09-23", "business_date": "2026-09-23",
        "opened_at": "2026-09-23T23:00:00+00:00", "closed_at": "2026-09-24T09:00:00+00:00", "is_open": False,
    }]


def test_hospitality_recalculated_history_matches_the_orders():
    result = _daily()
    totals, periods = result["totals"], result["periods"]
    real = [o for o in ORDERS if o["status"] != "cancelado"]
    assert totals["total"] == sum(o["total"] for o in real)
    assert totals["orders"] == len(real)
    assert sum(p["total"] for p in periods) == totals["total"]
    assert sum(p["orders"] for p in periods) == totals["orders"]
    assert totals["cash"] + totals["transfer"] + totals["card"] + totals["other"] == totals["total"]
    assert (totals["cash"], totals["transfer"], totals["card"]) == (45000, 30000, 5000)
    day = next(p for p in periods if p["key"] == "2026-09-23")
    assert day["cash"] + day["transfer"] + day["card"] + day["other"] == day["total"]
    assert hsp._hsp_top(day["tables"], "total", 1)[0]["name"] == "Mesa 2"  # mesa lider de la jornada
    assert "worked_minutes" not in totals  # "Horas operadas" eliminado


def test_hospitality_business_day_indicators():
    result = _daily()
    totals = result["totals"]
    day = next(p for p in result["periods"] if p["key"] == "2026-09-23")
    # ventas por hora en orden de jornada: 18h antes que 2h
    assert [(h["hour"], h["total"]) for h in day["hours"]] == [(18, 20000), (2, 30000)]
    # top 10 por unidades y por plata
    assert totals["top_products_quantity"][0]["name"] == "Cerveza Aguila"
    assert totals["top_products_total"][0]["name"] in {"Cerveza Aguila", "Aguardiente media"}
    assert len(totals["top_products_quantity"]) <= 10
    # sin rotacion: el agua no se vendio
    assert [row["name"] for row in totals["no_rotation"]] == ["Agua Cristal"]
    # misma jornada de la semana anterior (23 vs 16)
    assert (day["prev_week_date"], day["prev_week_total"]) == ("2026-09-16", 15000)
    # consumo promedio y duracion promedio de mesa
    assert day["table_sessions"]["sessions"] == 1
    assert day["table_sessions"]["avg_consumption"] == 20000
    assert day["table_sessions"]["avg_minutes"] == 120
    # cancelaciones y mermas
    assert (day["cancelled_count"], day["cancelled_total"]) == (1, 8000)
    assert day["cancelled"][0]["reason"] == "Vaso roto"
    # canciones por jornada
    assert day["songs"]["Querida"]["count"] == 1


def test_hospitality_weekly_and_monthly_use_the_same_jornadas():
    weekly = hsp._hsp_business_aggregate(ORDERS, SONGS, ACCESSES, INVENTORY, "weekly", TZ, CONFIG, now=NOW)
    monthly = hsp._hsp_business_aggregate(ORDERS, SONGS, ACCESSES, INVENTORY, "monthly", TZ, CONFIG, now=NOW)
    week = next(p for p in weekly["periods"] if p["key"] == "2026-09-21")
    assert week["total"] == 65000 and week["jornadas"] == 3
    assert monthly["totals"]["total"] == 80000


def test_hospitality_event_search_follows_the_jornada_and_reconciles():
    daily_totals = _daily()["daily_totals"]
    search = hsp._hsp_business_event_search(ORDERS, ACCESSES, date(2026, 9, 23), TZ, CONFIG, daily_totals["2026-09-23"], now=NOW)
    assert search["summary"]["total"] == 50000
    assert search["summary"]["orders"] == 2
    assert search["summary"]["reconciled"] is True
    ids = sorted(i for event in search["events"] for i in event["order_ids"])
    assert ids == ["o1", "o2"]  # incluye la venta de las 02:00, nunca la cancelada
    assert search["summary"]["message"] == ""


def test_hospitality_event_search_without_data_says_so():
    search = hsp._hsp_business_event_search(ORDERS, ACCESSES, date(2026, 9, 22), TZ, CONFIG, {}, now=NOW)
    assert search["events"] == []
    assert search["summary"]["message"] == "No hubo ventas en la jornada del 22/09/2026 (22/09 18:00 a 23/09 04:00)."


def test_hospitality_event_search_never_raises(monkeypatch):
    monkeypatch.setattr(hsp, "_hsp_event_search_rows", lambda *a, **k: (_ for _ in ()).throw(ValueError("dato raro")))
    search = hsp._hsp_business_event_search(ORDERS, ACCESSES, date(2026, 9, 23), TZ, CONFIG, {"total": 50000, "orders": 2}, now=NOW)
    assert search["events"] == []
    assert "No se pudo reconstruir la jornada del 23/09/2026" in search["summary"]["message"]


@pytest.mark.asyncio
async def test_hospitality_analytics_uses_business_day_only_with_the_switch(monkeypatch):
    company_id = uuid.uuid4()
    monkeypatch.setattr(hsp, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hsp, "_now", lambda: NOW)
    monkeypatch.setattr(hsp, "_hsp_company_report_settings", AsyncMock(return_value=(TZ, CONFIG)))
    monkeypatch.setattr(hsp, "_hsp_load_business_sources", AsyncMock(return_value=(ORDERS, ACCESSES, SONGS, INVENTORY)))
    legacy = AsyncMock(side_effect=AssertionError("no debe usar la jornada por cierres"))
    monkeypatch.setattr(hsp, "_hsp_load_shift_sources", legacy)

    data = await hsp.hospitality_sales_analytics(company_id, db=object(), event_date=date(2026, 9, 23))

    assert data["business_day"] == {"enabled": True, "open": "18:00", "close": "04:00"}
    assert data["today"] == "2026-09-24"
    assert set(data["analytics"]) == {"days", "weeks", "months"}
    history = data["analytics"]["days"]["history"]  # tabla KPI: hasta 30 jornadas
    assert len(history) == 30
    assert (history[0]["key"], history[-1]["key"]) == ("2026-08-26", "2026-09-24")
    assert next(row for row in history if row["key"] == "2026-09-23")["total"] == 50000
    assert len(data["analytics"]["days"]["periods"]) == 14  # la gráfica no cambia
    assert data["event_search"]["summary"]["total"] == 50000
    assert data["week_compare"] == {
        "date": "2026-09-23", "total": 50000, "orders": 2,
        "previous_date": "2026-09-16", "previous_total": 15000, "previous_orders": 1,
    }
    import json
    json.dumps(data)  # todo serializable (sin sets ni fechas crudas)


@pytest.mark.asyncio
async def test_hospitality_other_companies_keep_closure_based_reports(monkeypatch):
    company_id = uuid.uuid4()
    monkeypatch.setattr(hsp, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hsp, "_hsp_company_report_settings", AsyncMock(return_value=(TZ, None)))
    monkeypatch.setattr(hsp, "_hsp_business_analytics", AsyncMock(side_effect=AssertionError("no aplica")))
    monkeypatch.setattr(hsp, "_hsp_load_shift_sources", AsyncMock(return_value=([], [], [], [])))

    data = await hsp.hospitality_sales_analytics(company_id, db=object(), event_date=date(2026, 9, 23))

    assert "business_day" not in data
    assert "worked_minutes" in data["analytics"]["days"]["totals"]  # sin cambios para las demas


def test_hospitality_business_day_is_off_by_default():
    assert hsp._hsp_business_day_config({}) is None
    assert hsp._hsp_business_day_config(None) is None
    assert hsp._hsp_business_day_config({"hospitality_business_day": {"open": "18:00", "close": "18:00"}}) is None
    assert hsp._hsp_business_day_config({"hospitality_business_day": {"enabled": False, "open": "18:00", "close": "04:00"}}) is None
    day = hsp._hsp_business_day_config({"hospitality_business_day": {"open": "08:00", "close": "20:00"}})
    assert day["overnight"] is False
    assert hsp._hsp_business_date(datetime(2026, 9, 24, 7, 0, tzinfo=timezone.utc), TZ, day) == date(2026, 9, 24)


def test_hospitality_business_day_migration_only_the_time_machine(monkeypatch):
    import importlib.util

    path = Path("migrations/versions/021o_hsp_business_day_ttm.py")
    spec = importlib.util.spec_from_file_location("mig_021o", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32
    assert module.down_revision == "021n_qr_table_guests"
    executed = []
    monkeypatch.setattr(module.op, "execute", executed.append, raising=False)
    module.upgrade()
    module.downgrade()
    assert "WHERE id = '21a3065e-38ee-4fc3-96ed-ae1707a3b8e4'::uuid" in executed[0]
    assert '"open": "18:00", "close": "04:00"' in executed[0]
    assert "- 'hospitality_business_day'" in executed[1]


@pytest.mark.asyncio
async def test_hospitality_business_day_pdf_has_no_worked_hours(monkeypatch):
    company_id = uuid.uuid4()
    monkeypatch.setattr(hsp, "_now", lambda: NOW)
    monkeypatch.setattr(hsp, "_hospitality_company_identity", AsyncMock(return_value={"name": "The Time Machine", "timezone": TZ}))
    monkeypatch.setattr(hsp, "_hsp_company_report_settings", AsyncMock(return_value=(TZ, CONFIG)))
    monkeypatch.setattr(hsp, "_hsp_load_business_sources", AsyncMock(return_value=(ORDERS, ACCESSES, SONGS, INVENTORY)))

    payload = await hsp._hospitality_report_payload(object(), company_id, "daily", date(2026, 9, 21), date(2026, 9, 24))

    labels = [card["label"] for card in payload["cards"]]
    assert "Horas operadas" not in labels
    assert "Mermas y cancelaciones" in labels
    assert payload["totals"]["total"] == 65000  # 21 + 23 + 24 (el 16 queda fuera del rango)
    assert [row["closure_number"] for row in payload["closures"]] == ["21/09/2026", "23/09/2026", "24/09/2026"]
    pdf = hsp.build_hospitality_dashboard_pdf(payload)
    assert pdf[:4] == b"%PDF"
