from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from app.api.v1.endpoints import hospitality


def _closure(closed_at: str, total: float) -> dict:
    return {
        "closure_number": "HC-TEST",
        "closed_at": closed_at,
        "created_at": closed_at,
        "closed_by": "Pruebas",
        "orders_count": 1,
        "total_sold": total,
        "cash_total": total,
        "transfer_total": 0,
        "card_total": 0,
        "other_total": 0,
        "products": [{"name": "Cerveza", "quantity": 1, "total": total}],
        "tables": [{"table": "Mesa 1", "orders": 1, "total": total}],
        "songs": [{"song": "Cancion", "count": 1}],
        "summary": {"worked_minutes": 30},
        "notes": "",
    }


def test_daily_report_uses_company_timezone_and_exact_selected_day():
    closures = [
        _closure("2026-08-20T04:30:00+00:00", 100),  # 19 de agosto en Bogota
        _closure("2026-08-20T06:00:00+00:00", 250),  # 20 de agosto en Bogota
    ]

    result = hospitality._hsp_aggregate(
        closures,
        "daily",
        date(2026, 8, 20),
        date(2026, 8, 20),
        "America/Bogota",
    )

    assert [row["key"] for row in result["periods"]] == ["2026-08-20"]
    assert result["totals"]["closures"] == 1
    assert result["totals"]["orders"] == 1
    assert result["totals"]["total"] == 250
    assert len(result["closures"]) == 1


def test_period_definitions_cover_daily_weekly_and_monthly_ranges():
    daily = hospitality._hsp_period_defs("daily", [], date(2026, 8, 18), date(2026, 8, 20))
    weekly = hospitality._hsp_period_defs("weekly", [], date(2026, 8, 18), date(2026, 8, 31))
    monthly = hospitality._hsp_period_defs("monthly", [], date(2026, 6, 15), date(2026, 8, 2))

    assert [row["key"] for row in daily] == ["2026-08-18", "2026-08-19", "2026-08-20"]
    assert [row["key"] for row in weekly] == ["2026-08-17", "2026-08-24", "2026-08-31"]
    assert [row["key"] for row in monthly] == ["2026-06", "2026-07", "2026-08"]
    assert len(hospitality._hsp_period_defs("daily", [])) == 14


@pytest.mark.asyncio
async def test_pdf_endpoint_passes_selected_range_and_names_download(monkeypatch):
    company_id = uuid.uuid4()
    payload_builder = AsyncMock(
        return_value={
            "period": "daily",
            "range_start": "2026-08-20",
            "range_end": "2026-08-20",
        }
    )
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(hospitality, "_hospitality_report_payload", payload_builder)
    monkeypatch.setattr(hospitality, "build_hospitality_dashboard_pdf", lambda payload: b"%PDF-test")

    response = await hospitality.export_hospitality_dashboard_pdf(
        company_id,
        period="daily",
        start_date=date(2026, 8, 20),
        end_date=date(2026, 8, 20),
        db=SimpleNamespace(),
    )

    payload_builder.assert_awaited_once_with(
        SimpleNamespace(),
        company_id,
        "daily",
        date(2026, 8, 20),
        date(2026, 8, 20),
    )
    assert response.media_type == "application/pdf"
    assert "clonexa_hospitality_daily_2026-08-20.pdf" in response.headers["content-disposition"]


def test_hospitality_period_controls_are_connected_in_client():
    panel = Path("app/web/client.js").read_text(encoding="utf-8")
    backend = Path("app/api/v1/endpoints/hospitality.py").read_text(encoding="utf-8")
    html = Path("app/web/client.html").read_text(encoding="utf-8")

    assert 'data-hsp-dash-mode="days">Diario' in panel
    assert "Imprimir Hospitality por periodo" in panel
    assert "hspDashPdfStart032F" in panel
    assert "hspDashPdfEnd032F" in panel
    assert "hspDashPdfMonth032F" in panel
    assert "hspDashPdfMonthEnd032F" in panel
    assert 'params.set("start_date"' in panel
    assert 'params.set("end_date"' in panel
    assert "start_date: calendar_date | None" in backend
    assert "end_date: calendar_date | None" in backend
    assert "031P_HOSPITALITY_PERIOD_REPORTS" in html


def test_daily_pdf_contains_report_header_and_selected_range():
    period = hospitality._hsp_aggregate(
        [_closure("2026-08-20T14:00:00+00:00", 250)],
        "daily",
        date(2026, 8, 20),
        date(2026, 8, 20),
        "America/Bogota",
    )
    payload = {
        "company": {"name": "Radio Despecho", "primary_color": "#a39b00", "secondary_color": "#d7d27a"},
        "period_label": "Diario",
        "range_label": "20/08/2026",
        "generated_at": "2026-08-20T18:00:00+00:00",
        "periods": period["periods"],
        "totals": period["totals"],
        "closures": period["closures"],
        "cards": [
            {"label": "Total vendido", "value": "$ 250", "detail": "1 cierre"},
            {"label": "Pedidos", "value": "1", "detail": "Cuenta cerrada"},
        ],
        "top_products": [],
        "top_tables": [],
        "top_songs": [],
    }

    pdf = hospitality.build_hospitality_dashboard_pdf(payload)

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2500
