from __future__ import annotations

import json
import uuid

import pytest

from app.api.v1.endpoints import mini_panel_sales


TARGET_COMPANY_ID = uuid.UUID("7625872c-f941-4479-a27b-f8443be953c5")


class InventoryCatalogConnection:
    def __init__(self) -> None:
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchval_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchval(self, query: str, *args: object):
        self.fetchval_calls.append((query, args))
        if "to_regclass" in query:
            return "inventory_items"
        if "COUNT(*)" in query:
            return 2
        raise AssertionError(f"Consulta fetchval inesperada: {query}")

    async def fetch(self, query: str, *args: object):
        self.fetch_calls.append((query, args))
        return [
            {
                "id": TARGET_COMPANY_ID,
                "company_id": TARGET_COMPANY_ID,
                "item_name": "POLLO Asado",
                "item_size": "",
                "color": "",
                "sku": "POLLO-ASADO",
                "unit_price": 28000.0,
                "current_stock": 3.0,
                "status": "active",
            },
            {
                "id": uuid.UUID("91c48f73-34c5-4762-b36b-36113478f4f4"),
                "company_id": TARGET_COMPANY_ID,
                "item_name": "POLLO Broaster",
                "item_size": "",
                "color": "",
                "sku": "POLLO-BROASTER",
                "unit_price": 29000.0,
                "current_stock": 0.0,
                "status": "inactive",
            },
        ]


class ConfigConnection:
    def __init__(self) -> None:
        self.execute_args: tuple[object, ...] | None = None
        self.closed = False

    async def execute(self, _query: str, *args: object) -> None:
        self.execute_args = args

    async def close(self) -> None:
        self.closed = True


def test_catalog_source_defaults_to_references() -> None:
    payload = mini_panel_sales.SalesConfigIn()

    assert payload.occupation is None
    assert payload.catalog_source is None
    assert mini_panel_sales._catalog_source(None) == "references"
    assert mini_panel_sales._catalog_source("Inventario") == "inventory"


@pytest.mark.asyncio
async def test_inventory_categories_are_scoped_to_requested_company() -> None:
    conn = InventoryCatalogConnection()

    categories = await mini_panel_sales._inventory_categories(
        conn,
        TARGET_COMPANY_ID,
        include_inactive=True,
    )

    assert categories == [
        {
            "category": "Inventario",
            "slug": "inventario",
            "count": 2,
            "icon": "📦",
            "source": "inventory",
        }
    ]
    count_query, count_args = conn.fetchval_calls[-1]
    assert "company_id = $1::uuid" in count_query
    assert "status" not in count_query
    assert count_args == (TARGET_COMPANY_ID,)


@pytest.mark.asyncio
async def test_inventory_references_keep_tenant_filter_and_status() -> None:
    conn = InventoryCatalogConnection()

    items = await mini_panel_sales._inventory_references(
        conn,
        TARGET_COMPANY_ID,
        category="Inventario",
        q="pollo",
        limit=80,
        include_inactive=True,
    )

    query, args = conn.fetch_calls[0]
    assert "company_id = $1::uuid" in query
    assert "COALESCE(status, 'active') = 'active'" not in query
    assert args == (TARGET_COMPANY_ID, "%pollo%", 80)
    assert [item["name"] for item in items] == ["POLLO Asado", "POLLO Broaster"]
    assert items[0]["available"] is True
    assert items[1]["available"] is False
    assert all(item["source"] == "inventory" for item in items)


@pytest.mark.asyncio
async def test_inventory_references_exclude_inactive_by_default() -> None:
    conn = InventoryCatalogConnection()

    await mini_panel_sales._inventory_references(conn, TARGET_COMPANY_ID, limit=10)

    query, args = conn.fetch_calls[0]
    assert "company_id = $1::uuid" in query
    assert "COALESCE(status, 'active') = 'active'" in query
    assert args == (TARGET_COMPANY_ID, 10)


@pytest.mark.asyncio
async def test_inventory_references_reject_unrelated_category_without_query() -> None:
    conn = InventoryCatalogConnection()

    items = await mini_panel_sales._inventory_references(
        conn,
        TARGET_COMPANY_ID,
        category="Celulares",
        include_inactive=True,
    )

    assert items == []
    assert conn.fetch_calls == []


@pytest.mark.asyncio
async def test_save_config_preserves_existing_cut_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = ConfigConnection()

    async def fake_connect() -> ConfigConnection:
        return conn

    async def fake_ensure_storage(_conn: ConfigConnection) -> None:
        return None

    async def fake_company_exists(_conn: ConfigConnection, company_id: uuid.UUID) -> bool:
        return company_id == TARGET_COMPANY_ID

    async def fake_settings(_conn: ConfigConnection, _company_id: uuid.UUID) -> dict[str, object]:
        return {
            "occupation": "technology",
            "custom_categories": [],
            "catalog_source": "references",
            "inventory_include_inactive": False,
            "settings": {"sales_cut": {"period_type": "weekly"}},
        }

    monkeypatch.setattr(mini_panel_sales, "_connect", fake_connect)
    monkeypatch.setattr(mini_panel_sales, "_ensure_storage", fake_ensure_storage)
    monkeypatch.setattr(mini_panel_sales, "_company_exists", fake_company_exists)
    monkeypatch.setattr(mini_panel_sales, "_settings", fake_settings)

    result = await mini_panel_sales.save_sales_config(
        TARGET_COMPANY_ID,
        mini_panel_sales.SalesConfigIn(
            catalog_source="inventory",
            inventory_include_inactive=True,
        ),
    )

    assert conn.execute_args is not None
    assert conn.execute_args[0] == TARGET_COMPANY_ID
    stored = json.loads(str(conn.execute_args[2]))
    assert stored["sales_cut"] == {"period_type": "weekly"}
    assert stored["catalog_source"] == "inventory"
    assert stored["inventory_include_inactive"] is True
    assert result["company_id"] == str(TARGET_COMPANY_ID)
    assert conn.closed is True
