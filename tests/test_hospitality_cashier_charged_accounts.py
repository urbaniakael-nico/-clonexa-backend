"""049Z: lo cobrado del turno para el buscador de «Cobrados» de la caja.
Una fila por cuenta (una mesa con varios pedidos cobrados juntos = una
cuenta), solo lo cobrado, con numero, cliente, metodo, detalle y los pedidos
para reimprimir."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import cashier_summary

NOW = datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc)


def _order(oid, *, status="cerrado", closed=NOW, **extra):
    return {"id": oid, "order_number": f"QR-20260930-{oid[-4:]}", "status": status, "total": 10000, "payment_method": "cash",
            "created_at": NOW - timedelta(hours=1), "closed_at": closed if status == "cerrado" else None,
            "order_type": "table", "table_key": "mesa 7", "table_number": "Mesa 7", "metadata": {},
            "items": [{"name": "Cerveza", "quantity": 2, "subtotal": 10000}], **extra}


def test_hospitality_charged_accounts_one_row_per_account_only_paid():
    mesa_a = _order("m-0001", metadata={"waiter": {"name": "Laura"}})
    mesa_b = _order("m-0002", closed=NOW + timedelta(milliseconds=300), total=74000, payment_method="card",
                    items=[{"name": "Parrillada", "quantity": 1, "subtotal": 74000}])
    delivery = _order("d-0042", order_type="domicilio", table_number="Domicilio 4F2A", table_key="domicilio 4f2a", total=45000,
                      payment_method="transfer", closed=NOW - timedelta(minutes=5),
                      metadata={"delivery": {"customer_name": "Ana Pérez"}, "sale_document": {"number": "CC-000031"}})
    direct = _order("v-0014", table_number="Venta 014", table_key="venta 014", closed=NOW - timedelta(minutes=10),
                    metadata={"cashier_sale": {"kind": "independiente"}})
    still_open = _order("m-0003", status="entregado", table_key="mesa 2", table_number="Mesa 2")
    cancelled = _order("c-0001", status="cancelado")

    summary = cashier_summary.shift_summary([mesa_a, mesa_b, delivery, direct, still_open, cancelled], NOW - timedelta(hours=3))
    rows = summary["charged_accounts"]
    assert [r["label"] for r in rows] == ["Mesa 7", "Domicilio 0042", "Venta 014"], "lo mas reciente primero; solo lo cobrado"

    mesa = rows[0]
    assert sorted(mesa["order_ids"]) == ["m-0001", "m-0002"], "una mesa cobrada = una cuenta con todos sus pedidos"
    assert mesa["total"] == 84000 and mesa["waiter"] == "Laura" and mesa["channel"] == "mesa"
    assert [i["name"] for i in mesa["items"]] == ["Cerveza", "Parrillada"]

    dom = rows[1]
    assert dom["customer"] == "Ana Pérez" and dom["method"] == "transfer" and dom["method_label"] == "Transferencia"
    assert dom["document_number"] == "CC-000031" and dom["numbers"] == ["0042"]
    assert rows[2]["channel"] == "venta_directa"
    # Los indicadores de arriba no cambian: siguen siendo el resumen del turno.
    assert summary["charged"] == 84000 + 45000 + 10000 and summary["pending"] == 10000
