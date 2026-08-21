from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from starlette.requests import Request

from app.api.v1.endpoints import hospitality


class ScalarResult:
    def __init__(self, value=None, row=None):
        self.value = value
        self.row = row

    def scalar(self):
        return self.value

    def first(self):
        return self.row


@pytest.mark.asyncio
async def test_close_qr_access_refuses_tables_with_active_orders(monkeypatch):
    company_id = uuid.uuid4()
    db = SimpleNamespace(execute=AsyncMock(return_value=ScalarResult(value=2)), commit=AsyncMock())
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))

    with pytest.raises(hospitality.HTTPException) as exc:
        await hospitality.close_hospitality_table_access(
            company_id,
            hospitality.HospitalityTableAccessCloseIn(table="Mesa 3"),
            db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "mesa_tiene_pedidos_activos"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_order_is_registered_as_loss_and_closes_idle_access(monkeypatch):
    company_id = uuid.uuid4()
    order_id = uuid.uuid4()
    pending = {
        "id": str(order_id),
        "status": "pendiente",
        "table_key": "mesa 3",
        "table_number": "Mesa 3",
        "inventory_deducted": False,
        "metadata": {},
    }
    cancelled = {**pending, "status": "cancelado", "metadata": {"loss": True}}
    db = SimpleNamespace(execute=AsyncMock(return_value=ScalarResult()), commit=AsyncMock())
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    fetch_order = AsyncMock(side_effect=[pending, cancelled])
    close_idle = AsyncMock()
    monkeypatch.setattr(hospitality, "_fetch_order", fetch_order)
    monkeypatch.setattr(hospitality, "_close_table_access_if_idle", close_idle)

    response = await hospitality.cancel_hospitality_order(
        company_id,
        order_id,
        hospitality.HospitalityCancelIn(reason="Cliente desistio"),
        db,
    )

    statement = str(db.execute.await_args.args[0])
    params = db.execute.await_args.args[1]
    assert "status = 'cancelado'" in statement
    assert "cancelled_at" in statement
    assert '"loss": true' in params["metadata"]
    assert "Cliente desistio" in params["metadata"]
    close_idle.assert_awaited_once_with(db, company_id, "mesa 3")
    db.commit.assert_awaited_once()
    assert response["loss_registered"] is True
    assert response["order"]["status"] == "cancelado"


def test_day_closure_excludes_cancelled_orders_from_revenue():
    backend = Path("app/api/v1/endpoints/hospitality.py").read_text(encoding="utf-8")
    closure = backend.split("async def _create_day_closure", 1)[1].split("async def _active_loyalty_campaign", 1)[0]

    assert "revenue_orders =" in closure
    assert "cancelled_orders =" in closure
    assert "total_sold = _money(sum" in closure
    assert "for order in revenue_orders" in closure
    assert '"loss_total": loss_total' in closure
    assert '"orders_count": len(revenue_orders)' in closure


def test_qr_options_and_assistant_workflows_are_connected():
    panel = Path("app/web/client.js").read_text(encoding="utf-8")
    backend = Path("app/api/v1/endpoints/hospitality.py").read_text(encoding="utf-8")
    html = Path("app/web/client.html").read_text(encoding="utf-8")

    assert 'data-hsp-qr-close-access' in panel
    assert 'data-hsp-qr-cancel-order' in panel
    assert 'data-hsp-qr-show-losses' in panel
    assert "Merma / perdida" in panel
    assert 'router.post("/companies/{company_id}/qr-tables/access/close")' in backend
    assert 'router.post("/companies/{company_id}/orders/{order_id}/cancel")' in backend
    assert "cxAssistantQrCloseIntent031H" in panel
    assert "cxAssistantCloseQr031H" in panel
    assert 'data-cxai-qr-close-031h' in panel
    assert "cxAssistantLooksReorderQuery031H" in panel
    assert "cxAssistantReplyReorder031H" in panel
    assert "reorder-suggestion.pdf" in panel
    assert "031H_QR_OPTIONS_REORDER" in html


def test_hospitality_qr_can_be_saved_as_a_scalable_image():
    panel = Path("app/web/client.js").read_text(encoding="utf-8")
    backend = Path("app/api/v1/endpoints/hospitality.py").read_text(encoding="utf-8")
    html = Path("app/web/client.html").read_text(encoding="utf-8")

    assert "cxHspQrImage032C" in panel
    assert "data-hsp-qr-save-image" in panel
    assert "imagen SVG de alta definicion" in panel
    assert 'router.get("/companies/{company_id}/qr-tables/image.svg")' in backend
    assert "build_hospitality_qr_svg" in backend
    assert "031M_QR_SCALABLE_IMAGE" in html


def test_hospitality_qr_svg_has_large_canvas_and_quiet_zone():
    svg = hospitality.build_hospitality_qr_svg(
        "https://clonexa.example/ordenar?company_id=demo&mesa=Mesa%203"
    )

    assert svg.startswith(b"<?xml")
    assert b"<svg" in svg
    assert b'width="1024"' in svg
    assert b'height="1024"' in svg
    assert len(svg) > 5000


@pytest.mark.asyncio
async def test_hospitality_qr_download_preserves_exact_table_target(monkeypatch):
    company_id = uuid.uuid4()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "scheme": "https",
            "server": ("clonexa.example", 443),
            "client": ("127.0.0.1", 50000),
            "query_string": b"",
        }
    )
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))

    response = await hospitality.hospitality_qr_table_image(
        company_id,
        request,
        table="Mesa 3",
        base_url="https://clonexa.example",
        download=True,
        db=SimpleNamespace(),
    )

    target = f"https://clonexa.example/ordenar?company_id={company_id}&mesa=Mesa%203"
    assert response.status_code == 200
    assert response.media_type == "image/svg+xml"
    assert response.headers["x-qr-target"] == target
    assert response.headers["content-disposition"] == 'attachment; filename="qr-mesa-3.svg"'


def test_reorder_pdf_contains_invoice_style_order_content():
    payload = {
        "company": {"name": "Radio Despecho", "logo_url": "", "primary_color": "#eab308"},
        "generated_at": "2026-08-08T15:30:00+00:00",
        "order_items": [
            {
                "name": "Cerveza Aguila",
                "sku": "AG-001",
                "current_stock": 1,
                "min_stock": 5,
                "suggested_quantity": 9,
                "unit_value": 5000,
                "line_total": 45000,
            }
        ],
        "suggested_units": 9,
        "estimated_total": 45000,
    }

    pdf = hospitality.build_hospitality_reorder_pdf(payload)

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2500
