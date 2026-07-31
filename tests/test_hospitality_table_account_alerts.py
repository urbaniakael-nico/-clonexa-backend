from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from app.api.v1.endpoints import hospitality


class MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


@pytest.mark.asyncio
async def test_qr_table_account_uses_all_open_orders_for_the_same_table(monkeypatch):
    company_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=MappingResult(
                {
                    "orders_count": 3,
                    "total": 42000,
                    "accounts_count": 3,
                    "last_activity": now,
                }
            )
        )
    )
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))
    require_access = AsyncMock()
    monkeypatch.setattr(hospitality, "_require_table_access", require_access)

    response = await hospitality.get_hospitality_table_account(
        company_id,
        hospitality.HospitalityTableAccessVerifyIn(table="Mesa 8", access_code="ABCDE"),
        db,
    )

    require_access.assert_awaited_once_with(db, company_id, "Mesa 8", "ABCDE")
    statement = str(db.execute.await_args.args[0])
    params = db.execute.await_args.args[1]
    assert "status IN ('pendiente', 'alistando', 'entregado')" in statement
    assert "SUM(total)" in statement
    assert params["table_key"] == "mesa 8"
    assert response["account"] == {
        "total": 42000.0,
        "orders_count": 3,
        "accounts_count": 3,
        "last_activity": now.isoformat(),
    }


def test_mobile_qr_renders_and_refreshes_the_server_table_total():
    source = Path("app/web/hospitality_order.js").read_text(encoding="utf-8")

    assert "Cuenta total de la mesa" in source
    assert "/qr-tables/account`" in source
    assert 'body: JSON.stringify({ table: state.table, access_code: accessCode })' in source
    assert "refreshTableAccount({ render: false })" in source
    assert "refreshTableAccount().catch" in source
    assert "paintTableAccount()" in source
    assert 'document.getElementById("qrTableAccountTotal030B")' in source


def test_mobile_qr_recovers_the_existing_menu_without_cached_empty_responses():
    source = Path("app/web/hospitality_order.js").read_text(encoding="utf-8")
    html = Path("app/web/hospitality_order.html").read_text(encoding="utf-8")

    assert "fetchHospitalityInventory" in source
    assert 'cache: "no-store"' in source
    assert "recoverHospitalityInventory" in source
    assert "Reconectando el menu de la mesa" in source
    assert "v=030C_MENU_RECOVERY" in html


def test_orders_and_dashboard_alert_for_new_table_orders_after_initial_load():
    source = Path("app/web/client.js").read_text(encoding="utf-8")

    assert "cxHspOrderAlertsReady030B" in source
    assert "!cxHspKnownOrderIds030B.has(String(order.id))" in source
    assert '!["bar_manual", "barra"].includes(source)' in source
    assert "cxHspPlayNewOrderSound030B" in source
    assert "cxHspStartDashboardMonitor030D" in source
    assert "hsp-dashboard-pending-banner-030d" in source
    assert "pendingTables" in source
    assert "Activar alertas" in source
    assert 'aria-live="assertive"' in source


def test_mobile_qr_remembers_customer_name_on_the_same_device():
    source = Path("app/web/hospitality_order.js").read_text(encoding="utf-8")
    html = Path("app/web/hospitality_order.html").read_text(encoding="utf-8")

    assert "clonexa_hospitality_customer_" in source
    assert "storedCustomerName" in source
    assert "rememberCustomerName(customer)" in source
    assert 'target.id === "qrCustomer024S"' in source
    assert "Nombre recordado en este dispositivo" in source
    assert "030D_CUSTOMER_MEMORY" in html


def test_manual_bar_form_can_charge_products_to_a_table_account():
    source = Path("app/web/client.js").read_text(encoding="utf-8")
    html = Path("app/web/client.html").read_text(encoding="utf-8")

    assert 'id="hspSaleDestination030D"' in source
    assert 'id="hspTargetTable030D"' in source
    assert 'source: destination === "table" ? "table_manual" : "bar_manual"' in source
    assert 'table: manualTable' in source
    assert "El pedido activara la mesa" in source
    assert "030D_HOSPITALITY_LIVE_ORDERS" in html
