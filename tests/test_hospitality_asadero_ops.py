"""Pendientes de ASADERO EL SOCIO (waiter_ordering): CRM por área y
"Operarios activos", día más movido, reportes sin horas ni canciones, y
reimpresión de la cuenta de un consumo pasado."""
from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.api.v1.endpoints import crm_core_v1, hospitality as hsp, sale_document

client = TestClient(app_main.app)


# ------------------------------------------------------------------ CRM ---
def test_hospitality_crm_area_follows_the_role():
    assert crm_core_v1.hospitality_area_code_048f("cocina") == "cocina"
    assert crm_core_v1.hospitality_area_code_048f("", "Cocinero de parrilla") == "cocina"
    assert crm_core_v1.hospitality_area_code_048f("", "Mesera") == "mesero"
    assert crm_core_v1.hospitality_area_code_048f("", "Cajero", "mesero") == "caja"
    assert crm_core_v1.hospitality_area_code_048f("", "Administrador", "caja") == "caja"  # por su turno abierto
    assert crm_core_v1.hospitality_area_code_048f("", "Administrador", "") == ""


@pytest.mark.asyncio
async def test_hospitality_crm_operators_are_only_open_shifts(monkeypatch):
    async def fake_rows(_db, sql, params):
        assert params == {"company_id": "c1"}
        if "FROM company_users" in sql:
            return [{"role": "cocina", "employee_id": "e1"}, {"role": "caja", "employee_id": "e3"}]
        assert "lower(COALESCE(status, '')) IN ('active', 'break')" in sql  # solo turnos abiertos
        return [
            {"employee_id": "e1", "panel_type": "cocina", "status": "active", "started_at": "2026-09-24T22:30:00+00:00"},
            {"employee_id": "e2", "panel_type": "mesero", "status": "break", "started_at": "2026-09-24T23:00:00+00:00"},
        ]

    monkeypatch.setattr(crm_core_v1, "safe_rows", fake_rows)
    staff = await crm_core_v1.hospitality_staff_048f(object(), "c1")
    cook = crm_core_v1.hospitality_person_048f(staff, "e1", "")
    waiter = crm_core_v1.hospitality_person_048f(staff, "e2", "")
    cashier = crm_core_v1.hospitality_person_048f(staff, "e3", "")
    assert (cook["area"], cook["shift_open"], cook["shift_status"]) == ("Cocina", True, "active")
    assert (waiter["area"], waiter["shift_open"], waiter["shift_status"]) == ("Mesas", True, "break")
    assert (cashier["area"], cashier["shift_open"]) == ("Caja", False)  # sin turno abierto: no cuenta


# ------------------------------------------------------ día más movido ---
def test_hospitality_busiest_weekday():
    sales = {
        date(2026, 9, 5): 500000, date(2026, 9, 12): 450000, date(2026, 9, 19): 600000, date(2026, 9, 26): 300000,  # 4 sábados
        date(2026, 9, 6): 900000,  # 1 domingo muy fuerte, pero menos acumulado
        date(2026, 9, 7): 0,
    }
    assert hsp._hsp_busiest_weekday(sales) == {"weekday": 5, "label": "Sábado", "total": 1850000.0, "days": 4}
    assert hsp._hsp_busiest_weekday({}) is None


def test_hospitality_busiest_weekday_from_closures():
    tz = "America/Bogota"
    closures = [
        {"id": "c1", "opened_at": "2026-09-19T23:00:00+00:00", "closed_at": "2026-09-20T06:00:00+00:00", "total_sold": 700000, "orders_count": 30},
        {"id": "c2", "opened_at": "2026-09-12T23:00:00+00:00", "closed_at": "2026-09-13T06:00:00+00:00", "total_sold": 500000, "orders_count": 20},
        {"id": "c3", "opened_at": "2026-09-17T23:00:00+00:00", "closed_at": "2026-09-18T05:00:00+00:00", "total_sold": 800000, "orders_count": 25},
    ]
    result = hsp._hsp_aggregate(closures, "daily", date(2026, 9, 10), date(2026, 9, 20), tz)
    assert result["totals"]["busiest_weekday"] == {"weekday": 5, "label": "Sábado", "total": 1200000.0, "days": 2}


@pytest.mark.asyncio
async def test_hospitality_asadero_pdf_without_hours_and_songs(monkeypatch):
    company_id = uuid.uuid4()
    closures = [{"id": "c1", "opened_at": "2026-09-19T23:00:00+00:00", "closed_at": "2026-09-20T06:00:00+00:00",
                 "total_sold": 700000, "orders_count": 30, "cash_total": 700000, "songs": [{"song": "Querida", "count": 2}]}]
    monkeypatch.setattr(hsp, "_hospitality_company_identity", AsyncMock(return_value={"name": "ASADERO EL SOCIO", "timezone": "America/Bogota"}))
    monkeypatch.setattr(hsp, "_hsp_company_report_settings", AsyncMock(return_value=("America/Bogota", None)))
    monkeypatch.setattr(hsp, "_hsp_load_shift_sources", AsyncMock(return_value=([], closures, [], [])))
    monkeypatch.setattr(hsp, "_hsp_has_waiter_ordering", AsyncMock(return_value=True))

    payload = await hsp._hospitality_report_payload(object(), company_id, "daily", date(2026, 9, 14), date(2026, 9, 20))

    labels = [card["label"] for card in payload["cards"]]
    assert "Horas operadas" not in labels
    busiest = next(card for card in payload["cards"] if card["label"] == "Dia mas movido")
    assert busiest["value"] == "Sábado"
    assert payload["top_songs"] == []
    assert hsp.build_hospitality_dashboard_pdf(payload)[:4] == b"%PDF"

    monkeypatch.setattr(hsp, "_hsp_has_waiter_ordering", AsyncMock(return_value=False))
    other = await hsp._hospitality_report_payload(object(), company_id, "daily", date(2026, 9, 14), date(2026, 9, 20))
    assert "Horas operadas" in [card["label"] for card in other["cards"]], "otras empresas sin cambios"
    assert other["top_songs"]


# ------------------------------------------------------- reimpresión ---
def test_hospitality_reprint_requires_a_session(monkeypatch):
    class ModuleOnDb:  # the company has waiter_ordering; only the session is missing
        async def execute(self, *_args, **_kwargs):
            row = SimpleNamespace(_mapping={"code": "waiter_ordering"})
            return SimpleNamespace(fetchall=lambda: [row])

    async def fake_db():
        yield ModuleOnDb()

    monkeypatch.setattr(sale_document, "active_admin_v2_session", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    try:
        cid = str(uuid.uuid4())
        response = client.post(f"/api/v1/companies/{cid}/waiter-ordering/sale-document/reprint", json={"order_ids": [str(uuid.uuid4())]})
    finally:
        app_main.app.dependency_overrides.pop(get_db, None)
    assert response.status_code in (401, 403), response.text


class _OrdersDb:
    def __init__(self, orders):
        self.orders = orders
        self.commit = AsyncMock()
        self.stamped = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if sql.startswith("SELECT * FROM hospitality_orders"):
            assert "company_id = :company_id" in sql and "status <> 'cancelado'" in sql
            rows = [o for o in self.orders if o["id"] in params["ids"] and o["company_id"] == params["company_id"]]
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
        if sql.startswith("UPDATE hospitality_orders SET metadata"):
            self.stamped.append(params)
            return SimpleNamespace()
        raise AssertionError(sql[:80])


@pytest.mark.asyncio
async def test_hospitality_reprint_of_an_old_consumption_uses_the_sale_document(monkeypatch):
    company_id = uuid.uuid4()
    old = {
        "id": str(uuid.uuid4()), "company_id": str(company_id), "status": "cerrado", "payment_method": "cash",
        "table_number": "Mesa 4", "created_at": "2026-09-12T23:10:00+00:00", "metadata": {},
        "items": [{"name": "POLLO Asado", "quantity": 1, "unit_price": 40000, "subtotal": 40000}],
    }
    db = _OrdersDb([old])
    monkeypatch.setattr(sale_document, "_read_settings", AsyncMock(return_value=({"prefix": "CC", "numbering_start": 1, "dian_electronic_enabled": False}, 6)))
    monkeypatch.setattr(sale_document, "_next_number", AsyncMock(return_value=7))
    monkeypatch.setattr(sale_document, "_hospitality_company_identity", AsyncMock(return_value={"name": "ASADERO EL SOCIO"}))

    result = await sale_document.reprint_sale_document(
        company_id, sale_document.SaleDocumentRequest(order_ids=[uuid.UUID(old["id"])]), db=db, actor="Dueño",
    )

    doc = result["document"]
    assert doc["title"] == sale_document.DOCUMENT_TITLE
    assert doc["not_invoice_notice"] == sale_document.NOT_INVOICE_NOTICE  # "NO ES FACTURA" sin DIAN
    assert doc["table"] == "Mesa 4"
    assert [line["name"] for line in doc["lines"]] == ["POLLO Asado"]
    assert db.stamped and '"name": "Dueño"' in db.stamped[0]["stamp"]
