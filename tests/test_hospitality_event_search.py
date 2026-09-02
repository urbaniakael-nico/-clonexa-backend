from __future__ import annotations

import inspect
import uuid
from datetime import date, datetime, timezone
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
        "updated_at": created_at.replace(hour=created_at.hour + 1),
        "closed_at": created_at.replace(hour=created_at.hour + 1),
        "archived_at": created_at.replace(hour=created_at.hour + 1),
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


def test_event_endpoint_reads_archived_history_without_mutating_reports():
    source = inspect.getsource(hospitality.list_hospitality_events)
    assert "FROM hospitality_orders" in source
    assert "archived_at IS NULL" not in source
    assert "INSERT INTO hospitality_day_closures" not in source
    assert "UPDATE hospitality_orders" not in source


def test_hospitality_dashboard_places_event_search_below_payment_methods():
    client = Path("app/web/client.js").read_text(encoding="utf-8")
    html = Path("app/web/client.html").read_text(encoding="utf-8")
    methods_position = client.index("<h2>Metodos de pago</h2>")
    events_position = client.index("${cxHspDashRenderEventSearch033B()}", methods_position)
    assert events_position > methods_position
    assert "BÚSQUEDA DE EVENTOS" in client
    assert "data-hsp-dash-event-date" in client
    assert "/events?date=" in client
    assert "Activación" in client
    assert "Cuenta de barra" in client
    assert "033B_HOSPITALITY_EVENT_SEARCH" in html
