"""049Y: la cuenta de un domicilio desde el panel de caja (solo ASADERO).

El mismo documento de venta de mesas y ventas de caja (logo, NIT, consecutivo,
"CUENTA DE COBRO · NO ES FACTURA DE VENTA") mas: cliente, direccion, el valor
del domicilio en su propia linea y el metodo de pago con su estado, para que
el domiciliario sepa si cobra o si ya esta pagado. Se reimprime desde los
domicilios cobrados del turno con el mismo numero."""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import hospitality, sale_document
from app.services import cashier_summary
from tests.test_hospitality_sale_document import COMPANY_ID, IDENTITY, DocDb, _issue

ROOT = Path(__file__).resolve().parent.parent
CONFIG = {**sale_document.DEFAULT_CONFIG, "trade_name": "Asadero El Socio", "nit": "900123456-7", "prefix": "CC"}


def _delivery(payment_method="cash", payment_status="contra_entrega", status="entregado", **extra):
    return {
        "id": str(uuid.uuid4()),
        "company_id": str(COMPANY_ID),
        "order_number": "HSP-0042",
        "table_number": "Domicilio 4F2A",
        "order_type": "domicilio",
        "status": status,
        "payment_method": "transfer" if payment_method == "qr" else payment_method,
        "items": [
            {"name": "Pollo asado", "quantity": 2, "unit_price": 20000, "subtotal": 40000, "station": "parrilla"},
            {"name": "Valor domicilio", "quantity": 1, "unit_price": 5000, "subtotal": 5000, "station": "domicilio"},
        ],
        "total": 45000,
        "metadata": {"delivery": {
            "customer_name": "Ana Perez", "customer_phone": "573001234567",
            "address": "Calle 10 # 20-30, apto 401", "address_notes": "Torre 2",
            "payment_method": payment_method, "payment_status": payment_status,
            "pays_with": 100000 if payment_method == "cash" else None, "change": 55000 if payment_method == "cash" else None,
            **extra,
        }},
        "created_at": "2026-09-30T18:00:00+00:00",
        "closed_at": None,
    }


def _doc(order, on=True):
    return sale_document.build_sale_document(CONFIG, IDENTITY, [hospitality._payload(order)], "CC-000010", "x",
                                             delivery_details=on)


def test_hospitality_delivery_prints_customer_address_fee_and_what_to_collect():
    doc = _doc(_delivery())
    # Mismo documento y mismas reglas que las mesas.
    assert doc["title"] == "CUENTA DE COBRO" and doc["not_invoice_notice"] == "NO ES FACTURA DE VENTA"
    assert doc["issuer"]["nit"] == "900123456-7" and doc["number"] == "CC-000010"
    d = doc["delivery"]
    assert d["customer_name"] == "Ana Perez" and d["customer_phone"] == "573001234567"
    assert d["address"] == "Calle 10 # 20-30, apto 401" and d["address_notes"] == "Torre 2"
    # El domicilio va en su propia linea, fuera de los productos.
    assert [line["name"] for line in doc["lines"]] == ["Pollo asado"]
    assert (doc["products_total"], doc["delivery_fee"], doc["total"]) == (40000, 5000, 45000)
    assert d["payment_method_label"] == "Efectivo contra entrega"
    assert d["collect"] is True and d["payment_state"] == "COBRAR AL ENTREGAR: $45.000"
    assert d["change"] == "Paga con $100.000 · cambio $55.000"


def test_hospitality_delivery_qr_not_verified_says_so_on_paper():
    doc = _doc(_delivery(payment_method="qr", payment_status="por_verificar", payment_kind="transfer"))
    d = doc["delivery"]
    assert d["payment_method_label"] == "Transferencia"
    assert d["pending_verification"] is True and d["collect"] is False
    assert "POR VERIFICAR" in d["payment_state"] and "No entregar como pagado" in d["payment_state"]


def test_hospitality_delivery_verified_or_closed_means_do_not_collect():
    verified = _doc(_delivery(payment_method="qr", payment_status="verificado"))["delivery"]
    assert verified["payment_state"].endswith("NO COBRAR") and verified["collect"] is False
    assert verified["payment_method_label"] == "Pago por QR"
    closed = _doc(_delivery(status="cerrado"))["delivery"]
    assert closed["payment_state"] == "PAGADO · NO COBRAR" and closed["collect"] is False


def test_hospitality_delivery_without_the_switch_prints_as_before():
    doc = _doc(_delivery(), on=False)
    assert "delivery" not in doc
    assert [line["name"] for line in doc["lines"]] == ["Pollo asado", "Valor domicilio"]
    assert doc["total"] == 45000


@pytest.mark.asyncio
async def test_hospitality_delivery_reprint_keeps_its_number(monkeypatch):
    from app.api.v1.endpoints import waiter_ordering

    monkeypatch.setattr(waiter_ordering, "_feature_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(sale_document, "_hospitality_company_identity", AsyncMock(return_value=IDENTITY))
    order = _delivery(payment_method="qr", payment_status="por_verificar")
    db = DocDb([order], config={"prefix": "CC"})
    first = await _issue(db, order)
    again = await _issue(db, order)                              # desde "Domicilios cobrados"
    assert first["number"] == again["number"] == "CC-000001"
    assert again["delivery"]["pending_verification"] is True
    assert db.settings["last_number"] == 1


def test_hospitality_delivery_paid_ones_are_listed_for_reprint():
    now = datetime.now(timezone.utc)
    paid = {**_delivery(status="cerrado"), "created_at": now - timedelta(hours=1), "closed_at": now}
    open_ = {**_delivery(), "id": str(uuid.uuid4()), "created_at": now}
    table = {"id": str(uuid.uuid4()), "status": "cerrado", "order_type": "table", "total": 30000, "payment_method": "cash",
             "metadata": {}, "items": [], "created_at": now, "closed_at": now}
    summary = cashier_summary.shift_summary([paid, open_, table], now - timedelta(hours=3))
    rows = summary["deliveries_paid"]
    assert [r["id"] for r in rows] == [paid["id"]]
    assert rows[0]["label"] == "Domicilio 0042" and rows[0]["customer"] == "Ana Perez" and rows[0]["total"] == 45000


def test_hospitality_delivery_print_migration():
    path = ROOT / "migrations/versions/022o_delivery_print.py"
    spec = importlib.util.spec_from_file_location("mig_022o", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "022n_asadero_sales_brand"
    assert module.TARGET_COMPANY_ID == "7625872c-f941-4479-a27b-f8443be953c5"
    assert module.SETTINGS_PATCH == '{"delivery_print": true}'
