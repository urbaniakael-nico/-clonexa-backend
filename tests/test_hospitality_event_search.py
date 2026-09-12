from __future__ import annotations

import uuid
from unittest.mock import AsyncMock
import pytest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.api.v1.endpoints import hospitality


def _order(
    *,
    order_id: str,
    created_at: datetime,
    table: str,
    source: str,
    customer: str,
    item_name: str,
    quantity: int,
    unit_price: int,
    payment_method: str,
) -> dict:
    total = quantity * unit_price
    return {
        "id": order_id,
        "company_id": str(uuid.uuid4()),
        "order_number": f"QR-{order_id[-4:]}",
        "table_number": table,
        "table_key": table.lower(),
        "order_type": "bar_sale" if table == "Barra" else "table",
        "source": source,
        "payment_method": payment_method,
        "status": "cerrado",
        "customer_name": customer,
        "people": [],
        "items": [
            {
                "inventory_item_id": item_name.lower().replace(" ", "-"),
                "name": item_name,
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": total,
            }
        ],
        "songs": [],
        "total": total,
        "created_at": created_at,
        "updated_at": created_at + timedelta(hours=1),
        "closed_at": created_at + timedelta(hours=1),
        "archived_at": created_at + timedelta(hours=1),
        "metadata": {},
    }


def test_event_search_rebuilds_qr_activation_and_named_bar_account_from_archived_orders():
    first = _order(
        order_id="00000000-0000-0000-0000-000000000001",
        created_at=datetime(2026, 9, 1, 14, 10, tzinfo=timezone.utc),
        table="Mesa 8",
        source="qr",
        customer="Nicolas",
        item_name="CERVEZA Aguila Light",
        quantity=1,
        unit_price=5000,
        payment_method="transfer",
    )
    second = _order(
        order_id="00000000-0000-0000-0000-000000000002",
        created_at=datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc),
        table="Mesa 8",
        source="qr",
        customer="Nicolas",
        item_name="CERVEZA Aguila Light",
        quantity=2,
        unit_price=5000,
        payment_method="transfer",
    )
    bar = _order(
        order_id="00000000-0000-0000-0000-000000000003",
        created_at=datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc),
        table="Barra",
        source="bar_account",
        customer="Lucho",
        item_name="VODKA Smirnoff Original",
        quantity=1,
        unit_price=12000,
        payment_method="cash",
    )
    access = {
        "id": "10000000-0000-0000-0000-000000000008",
        "table_number": "Mesa 8",
        "table_key": "mesa 8",
        "status": "closed",
        "closes_with_table": True,
        "activation_number": 7,
        "activated_at": datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
        "expires_at": datetime(2026, 9, 2, 2, 0, tzinfo=timezone.utc),
    }

    events = hospitality._hsp_event_search_rows(
        [first, second, bar],
        [access],
        date(2026, 9, 1),
        "America/Bogota",
    )

    assert len(events) == 2
    qr_event = next(event for event in events if event["type"] == "qr")
    assert qr_event["location"] == "Mesa 8"
    assert qr_event["activation_number"] == 7
    assert qr_event["orders_count"] == 2
    assert qr_event["payment_label"] == "Transferencia"
    assert qr_event["total"] == 15000
    assert len(qr_event["items"]) == 1
    assert qr_event["items"][0]["name"] == "CERVEZA Aguila Light"
    assert qr_event["items"][0]["quantity"] == 3
    assert qr_event["items"][0]["subtotal"] == 15000

    bar_event = next(event for event in events if event["type"] == "bar")
    assert bar_event["customer_name"] == "Lucho"
    assert bar_event["location"] == "Barra"
    assert bar_event["payment_label"] == "Efectivo"
    assert bar_event["total"] == 12000


def test_event_search_keeps_legacy_qr_consumption_when_access_history_is_missing():
    legacy = _order(
        order_id="00000000-0000-0000-0000-000000000004",
        created_at=datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc),
        table="Mesa 3",
        source="qr",
        customer="Cliente mesa",
        item_name="Agua Cristal",
        quantity=2,
        unit_price=4000,
        payment_method="cash",
    )

    events = hospitality._hsp_event_search_rows([legacy], [], date(2026, 9, 1), "America/Bogota")

    assert len(events) == 1
    assert events[0]["historical"] is True
    assert events[0]["location"] == "Mesa 3"
    assert events[0]["total"] == 8000


@pytest.mark.asyncio
async def test_event_endpoint_uses_same_snapshot_as_analytics(monkeypatch):
    snapshot = {"event_search": {"date": "2026-09-10", "events": [], "summary": {"total": 0}}}
    analytics = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(hospitality, "hospitality_sales_analytics", analytics)
    company, db = uuid.uuid4(), object()
    result = await hospitality.list_hospitality_events(company, date(2026, 9, 10), db)
    analytics.assert_awaited_once_with(company, db, date(2026, 9, 10))
    assert result["summary"] == snapshot["event_search"]["summary"]


def test_hospitality_dashboard_places_event_search_below_payment_methods():
    client = Path("app/web/client.js").read_text(encoding="utf-8")
    html = Path("app/web/client.html").read_text(encoding="utf-8")
    methods_position = client.index("<h2>Metodos de pago</h2>")
    events_position = client.index("${cxHspDashRenderEventSearch033B()}", methods_position)
    assert events_position > methods_position
    assert "BÚSQUEDA DE EVENTOS" in client
    assert "data-hsp-dash-event-date" in client
    assert "/analytics${query}" in client
    assert "Activación" in client
    assert "Cuenta de barra" in client
    assert "033B_HOSPITALITY_EVENT_SEARCH" in html


def test_events_chart_and_kpis_share_exact_overnight_orders_without_duplicates():
    def order(key, timestamp, table, source, total):
        return _order(order_id=key, created_at=datetime.fromisoformat(timestamp), table=table,
                      source=source, customer="Cliente", item_name="Cerveza", quantity=1,
                      unit_price=total, payment_method="cash")
    before = order("a", "2026-09-07T23:00:00+00:00", "Mesa 1", "qr", 15000)
    after = order("b", "2026-09-08T07:00:00+00:00", "Mesa 1", "qr", 25000)
    bar = order("c", "2026-09-08T06:00:00+00:00", "Barra", "bar_account", 10000)
    cancelled = {**after, "id": "cancelled", "status": "cancelado", "total": 90000}
    unrelated = order("other", "2026-09-08T01:00:00+00:00", "Mesa 1", "qr", 70000)
    closure = {"id": "night", "opened_at": before["created_at"], "closed_at": "2026-09-08T09:00:00Z",
               "order_ids": ["a", "b", "c", "cancelled"], "total_sold": 50000, "cash_total": 50000,
               "orders_count": 3}
    access = {"id": "access", "table_number": "Mesa 1", "table_key": "mesa 1", "status": "closed",
              "activated_at": "2026-09-07T22:00:00Z", "updated_at": "2026-09-08T09:00:00Z", "closes_with_table": True}
    orders = [before, after, bar, cancelled, unrelated, after]
    shifts = hospitality._hsp_shift_records(orders, [closure], [])
    day = date(2026, 9, 7)
    result = hospitality._hsp_shift_event_search(orders, [access, access], shifts, day, "America/Bogota")
    financial = hospitality._hsp_aggregate(shifts, "daily", day, day, "America/Bogota")
    assert result["summary"]["reconciled"] is True
    assert result["summary"]["total"] == financial["totals"]["total"] == financial["periods"][0]["total"] == 50000
    assert result["summary"]["orders"] == financial["totals"]["orders"] == 3
    ids = [key for event in result["events"] for key in event["order_ids"]]
    assert sorted(ids) == ["a", "b", "c"]
    assert sum(item["subtotal"] for event in result["events"] for item in event["items"]) == 50000
    next_day = hospitality._hsp_shift_event_search(orders, [access], shifts, date(2026, 9, 8), "America/Bogota")
    assert next_day["events"] == []
    assert next_day["summary"]["total"] == 0


def test_long_closure_events_are_selected_by_membership_not_calendar_overlap():
    from tests.test_hospitality_live_sales import sale, shift
    orders = [sale("8", "2026-09-08T21:23:00-05:00", 15000, source="bar_account", table_number="Barra"),
              sale("9", "2026-09-09T22:00:00-05:00", 283000, source="bar_account", table_number="Barra"),
              sale("10", "2026-09-10T01:00:00-05:00", 43000, source="bar_account", table_number="Barra")]
    closure = shift("long", orders[0]["created_at"], "2026-09-10T03:00:00-05:00", 341000,
                    order_ids=["8", "9", "10"], orders_count=3)
    shifts = hospitality._hsp_shift_records(orders, [closure], [])
    for day, expected in [(8, 341000), (9, 0), (10, 0)]:
        result = hospitality._hsp_shift_event_search(orders, [], shifts, date(2026, 9, day), "America/Bogota")
        assert result["summary"]["total"] == expected
        assert result["summary"]["reconciled"] is True


def test_missing_legacy_order_detail_is_reported_as_mismatch_not_fabricated():
    closure = {"id": "missing", "opened_at": "2026-09-07T23:00:00Z", "closed_at": "2026-09-08T09:00:00Z",
               "total_sold": 50000, "orders_count": 1, "order_ids": ["missing-order"]}
    result = hospitality._hsp_shift_event_search([], [], [closure], date(2026, 9, 7), "America/Bogota")
    assert result["summary"]["reconciled"] is False
    assert result["summary"]["total"] == 0
    assert result["summary"]["expected_total"] == 50000
