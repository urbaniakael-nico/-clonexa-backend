from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import inventory


ROOT = Path(__file__).resolve().parents[1]
CLIENT_JS = (ROOT / "app" / "web" / "client.js").read_text(encoding="utf-8")
SETTINGS_JS = (ROOT / "app" / "web" / "client_core_settings.js").read_text(encoding="utf-8")
INVENTORY_BACKEND = (ROOT / "app" / "api" / "v1" / "endpoints" / "inventory.py").read_text(encoding="utf-8")


def test_inventory_output_keeps_entry_and_sale_values_separate():
    row = inventory.inventory_item_out(
        {
            "id": uuid4(),
            "company_id": uuid4(),
            "name_reference": "Cerveza",
            "current_stock": 10,
            "min_stock": 2,
            "entry_price": 3000,
            "sale_price": 5000,
            "unit_value": 5000,
            "status": "active",
        }
    )

    assert row["entry_price"] == 3000
    assert row["sale_price"] == 5000
    assert row["entry_stock_value"] == 30000
    assert row["sale_stock_value"] == 50000
    assert row["unit_value"] == 5000
    assert row["stock_value"] == 50000


def test_inventory_summary_reports_both_total_values():
    rows = [
        {"status": "active", "current_stock": 2, "entry_stock_value": 6000, "sale_stock_value": 10000},
        {"status": "inactive", "current_stock": 1, "entry_stock_value": 2500, "sale_stock_value": 4000},
    ]

    summary = inventory.inventory_summary(rows)

    assert summary["total_entry_value"] == 8500
    assert summary["total_sale_value"] == 14000
    assert summary["total_stock_value"] == 14000


@pytest.mark.asyncio
async def test_bulk_inventory_update_uses_one_commit(monkeypatch):
    company_id = uuid4()
    items = [
        inventory.InventoryBulkItemUpdate(id=uuid4(), name_reference="A", entry_price=1, sale_price=2),
        inventory.InventoryBulkItemUpdate(id=uuid4(), name_reference="B", entry_price=3, sale_price=4),
    ]
    db = SimpleNamespace(commit=AsyncMock())
    ensure = AsyncMock()
    update = AsyncMock(
        side_effect=[
            {"status": "active", "current_stock": 1, "entry_stock_value": 1, "sale_stock_value": 2},
            {"status": "active", "current_stock": 1, "entry_stock_value": 3, "sale_stock_value": 4},
        ]
    )
    monkeypatch.setattr(inventory, "ensure_inventory_storage", ensure)
    monkeypatch.setattr(inventory, "_update_inventory_item_record", update)

    result = await inventory.bulk_update_inventory_items(
        company_id,
        inventory.InventoryBulkUpdate(items=items),
        db,
    )

    assert result["updated"] == 2
    assert result["summary"]["total_entry_value"] == 4
    assert result["summary"]["total_sale_value"] == 6
    ensure.assert_awaited_once_with(db)
    assert update.await_count == 2
    db.commit.assert_awaited_once()


def test_inventory_ui_has_both_prices_and_mass_save():
    assert 'id="inventoryCreateEntryPrice"' in CLIENT_JS
    assert 'id="inventoryCreateSalePrice"' in CLIENT_JS
    assert 'data-inventory-field="entry_price"' in CLIENT_JS
    assert 'data-inventory-field="sale_price"' in CLIENT_JS
    assert "data-inventory-save-all" in CLIENT_JS
    assert "/items/bulk" in CLIENT_JS
    assert '@router.patch("/companies/{company_id}/items/bulk")' in INVENTORY_BACKEND


def test_stock_is_read_only_and_shows_entry_and_sale_totals():
    stock = CLIENT_JS.split("/* CLONEXA_024T_STOCK_PANEL_START */", 1)[1].split(
        "/* CLONEXA_024T_STOCK_PANEL_END */", 1
    )[0]

    assert "Valor entrada" in stock
    assert "Valor salida" in stock
    assert "Precio entrada" in stock
    assert "Precio salida" in stock
    assert "Editar en Inventario" in stock
    assert 'data-stock-field="min_stock"' not in stock
    assert 'data-stock-field="unit_value"' not in stock
    assert "data-stock-save" not in stock


def test_account_settings_send_the_required_credentials():
    email_flow = SETTINGS_JS.split("async function changeEmail", 1)[1].split(
        "async function changePassword", 1
    )[0]
    password_flow = SETTINGS_JS.split("async function changePassword", 1)[1].split(
        "function clearSession", 1
    )[0]

    assert 'api("/auth/account/email"' in email_flow
    assert "new_email: newEmail" in email_flow
    assert "current_password: currentPassword" in email_flow
    assert 'api("/auth/account/password"' in password_flow
    assert "new_password: newPassword" in password_flow
    assert "confirm_password: confirmPassword" in password_flow
