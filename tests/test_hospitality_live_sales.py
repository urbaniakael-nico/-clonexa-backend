from datetime import datetime, timezone
import pytest

from app.api.v1.endpoints import hospitality as hsp


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(hsp, "_now", lambda: datetime(2026, 9, 10, 14, tzinfo=timezone.utc))


def sale(key, created_at, total, **changes):
    return {
        "id": key, "created_at": created_at, "status": "cerrado",
        "closed_at": "2026-09-10T05:30:00Z", "metadata": {},
        "total": total, "payment_method": "cash", "table_number": "Mesa 1",
        "items": [{"name": "Producto", "quantity": 1, "subtotal": total}],
        **changes,
    }


def aggregate(orders=(), closures=(), period="daily", zone="America/Bogota"):
    return hsp._hsp_sales_aggregate(list(orders), list(closures), [], period, zone)


def test_sales_on_8_and_9_stay_on_registration_day_when_closed_on_10():
    orders = [
        sale("8", "2026-09-09T02:23:00Z", 15000),
        sale("9", "2026-09-10T04:09:00Z", 283000),
        sale("10", "2026-09-10T05:15:00Z", 43000),
    ]
    before = aggregate(orders)
    archived = [{**row, "metadata": {"closure_id": "closing-10"}, "archived_at": "2026-09-10T06:00:00Z"} for row in orders]
    after = aggregate(archived, [{"closed_at": "2026-09-10T06:00:00Z", "total_sold": 341000, "orders_count": 3}])
    for result in (before, after):
        days = {row["key"]: row for row in result["periods"]}
        assert days["2026-09-07"]["total"] == 0
        assert days["2026-09-08"]["total"] == 15000
        assert days["2026-09-09"]["total"] == 283000
        assert days["2026-09-10"]["total"] == 43000
        assert result["totals"]["total"] == result["totals"]["cash"] == 341000
        assert result["totals"]["orders"] == 3
    assert after["totals"]["closures"] == 1


def test_cancelled_and_open_accounts_do_not_become_sales_or_duplicate_closed_orders():
    closed = sale("closed", "2026-09-09T20:00:00Z", 15000)
    rows = [closed, closed, sale("cancelled", "2026-09-09T20:00:00Z", 90000, status="cancelado", metadata={"closure_id": "old"}),
            sale("open", "2026-09-09T20:00:00Z", 20000, status="entregado"),
            sale("legacy", "2026-09-09T20:00:00Z", 30000, status="entregado", metadata='{"closure_id":"old"}', payment_method="transfer")]
    result = aggregate(rows)["totals"]
    assert result["orders"] == 2
    assert result["total"] == 45000
    assert result["cash"] == 15000
    assert result["transfer"] == 30000
    assert result["products"]["Producto"]["total"] == 45000


@pytest.mark.parametrize("period,count,last", [("daily", 14, "2026-09-10"), ("weekly", 12, "2026-09-07"), ("monthly", 3, "2026-09")])
def test_empty_windows_continue_to_today_despite_old_closures(period, count, last):
    result = aggregate(closures=[{"closed_at": "2026-08-28T12:00:00Z"}], period=period)
    assert len(result["periods"]) == count
    assert result["periods"][-1]["key"] == last
    assert all(row["total"] == 0 for row in result["periods"])


def test_calendar_rolls_over_at_tenant_midnight_without_new_sales(monkeypatch):
    monkeypatch.setattr(hsp, "_now", lambda: datetime(2026, 9, 10, 4, 59, tzinfo=timezone.utc))
    assert aggregate()["periods"][-1]["key"] == "2026-09-09"
    monkeypatch.setattr(hsp, "_now", lambda: datetime(2026, 9, 10, 5, 0, tzinfo=timezone.utc))
    assert aggregate()["periods"][-1]["key"] == "2026-09-10"


def test_out_of_window_and_future_orders_are_excluded():
    result = aggregate([
        sale("old", "2026-01-01T12:00:00Z", 100),
        sale("future", "2026-09-11T12:00:00Z", 200),
    ])
    assert result["totals"]["total"] == 0


def test_sales_grouping_uses_company_timezone_not_browser_or_utc():
    row = sale("timezone", "2026-09-10T02:00:00Z", 15000)
    bogota = {day["key"]: day for day in aggregate([row])["periods"]}
    utc = {day["key"]: day for day in aggregate([row], zone="UTC")["periods"]}
    assert bogota["2026-09-09"]["total"] == 15000
    assert utc["2026-09-10"]["total"] == 15000


def test_legacy_songs_are_preserved_without_double_counting_direct_requests():
    closures = [
        {"closed_at": "2026-09-01T12:00:00Z", "songs": [{"song": "Legacy", "count": 2}]},
        {"closed_at": "2026-09-10T12:00:00Z", "songs": [{"song": "Live", "count": 1}]},
    ]
    songs = [{"created_at": "2026-09-09T12:00:00Z", "song": "Live"}]
    result = hsp._hsp_sales_aggregate([], closures, songs, "daily", "America/Bogota")
    assert result["totals"]["songs"]["Legacy"]["count"] == 2
    assert result["totals"]["songs"]["Live"]["count"] == 1
