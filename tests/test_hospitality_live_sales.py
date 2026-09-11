from datetime import date, datetime, timezone
import pytest
from app.api.v1.endpoints import hospitality as hsp


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(hsp, "_now", lambda: datetime(2026, 9, 10, 14, tzinfo=timezone.utc))


def sale(key, created_at, total, **changes):
    return {"id": key, "created_at": created_at, "status": "cerrado", "metadata": {},
            "total": total, "payment_method": "cash", "table_number": "Mesa 1",
            "items": [{"name": "Producto", "quantity": 1, "subtotal": total}], **changes}


def shift(key, opened, closed, total, **changes):
    return {"id": key, "opened_at": opened, "closed_at": closed, "total_sold": total,
            "cash_total": total, "orders_count": 1, "summary": {}, **changes}


def aggregate(orders=(), closures=(), period="daily", zone="America/Bogota", **kwargs):
    return hsp._hsp_sales_aggregate(list(orders), list(closures), [], period, zone, **kwargs)


def test_overnight_shift_stays_on_opening_day_before_and_after_closure():
    orders = [sale("before", "2026-09-07T18:00:00-05:00", 15000),
              sale("after", "2026-09-08T02:00:00-05:00", 25000)]
    closed = shift("night", orders[0]["created_at"], "2026-09-08T04:00:00-05:00", 40000,
                   orders_count=2, order_ids=[row["id"] for row in orders])
    before = aggregate(orders)
    after = aggregate(orders, [closed, closed])  # Stale order copies cannot duplicate a closure.
    for result in (before, after):
        days = {row["key"]: row for row in result["periods"]}
        assert days["2026-09-07"]["total"] == 40000
        assert days["2026-09-08"]["total"] == 0
        assert result["totals"]["total"] == result["totals"]["cash"] == 40000
        assert result["totals"]["orders"] == 2
    assert before["totals"]["closures"] == 0
    assert before["totals"]["shifts"][0]["is_open"] is True
    assert after["totals"]["closures"] == 1
    assert after["totals"]["worked_minutes"] == 600


def test_live_shift_counts_consumption_once_and_excludes_cancelled_and_archived():
    closed = sale("closed", "2026-09-09T20:00:00Z", 15000)
    rows = [closed, closed, sale("cancelled", "2026-09-09T19:00:00Z", 90000, status="cancelado"),
            sale("served", "2026-09-10T06:00:00Z", 20000, status="entregado"),
            sale("pending", "2026-09-10T07:00:00Z", 30000, status="pendiente", payment_method="transfer"),
            sale("archived", "2026-09-09T20:00:00Z", 50000, archived_at="2026-09-10T08:00:00Z"),
            sale("linked", "2026-09-09T20:00:00Z", 60000, metadata='{"closure_id":"old"}')]
    result = aggregate(rows)["totals"]
    assert result["orders"] == 3
    assert (result["total"], result["cash"], result["transfer"]) == (65000, 35000, 30000)
    assert result["products"]["Producto"]["total"] == 65000
    assert result["worked_minutes"] == 19 * 60  # Same opening rule as saved closures.


def test_finalized_snapshot_preserves_reconciled_payments():
    result = aggregate(closures=[shift("cash-count", "2026-09-07T23:00:00Z", "2026-09-08T09:00:00Z", 40000,
                                      cash_total=10000, transfer_total=30000)])["totals"]
    assert (result["total"], result["cash"], result["transfer"]) == (40000, 10000, 30000)


def test_multiple_shifts_same_date_sum_sales_and_actual_worked_hours():
    result = aggregate(closures=[
        shift("lunch", "2026-09-07T12:00:00-05:00", "2026-09-07T14:00:00-05:00", 10000),
        shift("night", "2026-09-07T18:00:00-05:00", "2026-09-08T04:00:00-05:00", 40000),
    ])["totals"]
    assert result["total"] == 50000
    assert result["closures"] == len(result["shifts"]) == 2
    assert result["worked_minutes"] == 720


def test_saved_multi_night_shift_is_not_split_by_invented_cutoff():
    result = aggregate(closures=[shift("long", "2026-09-08T21:23:00-05:00", "2026-09-10T03:00:00-05:00", 341000)])
    days = {row["key"]: row for row in result["periods"]}
    assert days["2026-09-08"]["total"] == 341000
    assert days["2026-09-08"]["worked_minutes"] == 1777
    assert days["2026-09-09"]["total"] == days["2026-09-10"]["total"] == 0


@pytest.mark.parametrize("selected,expected", [(date(2026, 9, 7), 40000), (date(2026, 9, 8), 0)])
def test_selected_report_day_contains_whole_shift_only_on_opening_date(selected, expected):
    result = aggregate(closures=[shift("night", "2026-09-07T18:00:00-05:00", "2026-09-08T04:00:00-05:00", 40000)],
                       start_date=selected, end_date=selected)
    assert result["totals"]["total"] == expected
    assert len(result["periods"]) == 1


@pytest.mark.parametrize("period,opened,closed,key", [
    ("weekly", "2026-09-06T18:00:00-05:00", "2026-09-07T04:00:00-05:00", "2026-08-31"),
    ("monthly", "2026-08-31T18:00:00-05:00", "2026-09-01T04:00:00-05:00", "2026-08"),
])
def test_week_and_month_boundaries_use_opening_date(period, opened, closed, key):
    result = aggregate(closures=[shift("boundary", opened, closed, 40000)], period=period)
    assert next(row for row in result["periods"] if row["key"] == key)["total"] == 40000
    assert result["totals"]["total"] == 40000


@pytest.mark.parametrize("period,count,last", [("daily", 14, "2026-09-10"), ("weekly", 12, "2026-09-07"), ("monthly", 3, "2026-09")])
def test_empty_windows_continue_to_today_despite_old_closures(period, count, last):
    result = aggregate(closures=[{"closed_at": "2026-08-28T12:00:00Z"}], period=period)
    assert len(result["periods"]) == count
    assert result["periods"][-1]["key"] == last
    assert all(row["total"] == 0 for row in result["periods"])


def test_calendar_rolls_at_midnight_but_ongoing_sales_stay_on_opening_day(monkeypatch):
    orders = [sale("night", "2026-09-09T23:00:00Z", 15000)]
    monkeypatch.setattr(hsp, "_now", lambda: datetime(2026, 9, 10, 4, 59, tzinfo=timezone.utc))
    assert aggregate(orders)["periods"][-1]["total"] == 15000
    monkeypatch.setattr(hsp, "_now", lambda: datetime(2026, 9, 10, 5, 0, tzinfo=timezone.utc))
    days = aggregate(orders)["periods"]
    assert days[-1]["key"] == "2026-09-10"
    assert days[-1]["total"] == 0
    assert days[-2]["total"] == 15000


def test_out_of_window_and_future_orders_are_excluded():
    result = aggregate([sale("old", "2026-01-01T12:00:00Z", 100), sale("future", "2026-09-11T12:00:00Z", 200)])
    assert result["totals"]["total"] == 0


def test_opening_date_uses_company_timezone():
    row = sale("timezone", "2026-09-10T02:00:00Z", 15000)
    bogota = {day["key"]: day for day in aggregate([row])["periods"]}
    utc = {day["key"]: day for day in aggregate([row], zone="UTC")["periods"]}
    assert bogota["2026-09-09"]["total"] == 15000
    assert utc["2026-09-10"]["total"] == 15000


def test_legacy_and_direct_songs_follow_their_shift_without_double_counting():
    closures = [
        shift("legacy", "2026-09-01T00:00:00Z", "2026-09-01T12:00:00Z", 0, songs=[{"song": "Legacy", "count": 2}]),
        shift("night", "2026-09-07T23:00:00Z", "2026-09-08T09:00:00Z", 0, songs=[{"song": "Live", "count": 1}]),
    ]
    songs = [{"created_at": "2026-09-08T07:00:00Z", "archived_at": "2026-09-08T09:00:00Z", "song": "Live"}]
    result = hsp._hsp_sales_aggregate([], closures, songs, "daily", "America/Bogota")
    assert result["totals"]["songs"]["Legacy"]["count"] == 2
    assert result["totals"]["songs"]["Live"]["count"] == 1
    assert next(row for row in result["periods"] if row["key"] == "2026-09-07")["songs"]["Live"]["count"] == 1
