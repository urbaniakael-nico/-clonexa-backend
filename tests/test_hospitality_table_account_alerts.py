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
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
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
    assert "!cxHspKnownOrderIds030B.has(id)" in source
    assert "!cxHspIsBarOnlyOrder031D(order)" in source
    assert "cxHspPlayNewOrderSound030B" in source
    assert "cxHspStartDashboardMonitor030D" in source
    assert "hsp-dashboard-pending-banner-030d" in source
    assert "pendingTables" in source
    assert "Alerta visual" in source
    assert "Sonido" in source
    assert 'aria-live="assertive"' in source
    monitor = source.split("function cxHspStartDashboardMonitor030D", 1)[1].split("async function loadClientDashboardMetrics", 1)[0]
    assert "cxHspPaintDashboardMetrics030D(next)" in monitor
    assert "render();" not in monitor


def test_mobile_qr_remembers_customer_name_on_the_same_device():
    source = Path("app/web/hospitality_order.js").read_text(encoding="utf-8")
    html = Path("app/web/hospitality_order.html").read_text(encoding="utf-8")

    assert "clonexa_hospitality_customer_" in source
    assert "storedCustomerName" in source
    assert "rememberCustomerName(customer)" in source
    assert 'target.id === "qrCustomer024S"' in source
    assert "Nombre recordado en este dispositivo" in source
    assert "030D_CUSTOMER_MEMORY" in html


def test_mobile_qr_keeps_table_access_until_the_backend_closes_the_table():
    source = Path("app/web/hospitality_order.js").read_text(encoding="utf-8")
    html = Path("app/web/hospitality_order.html").read_text(encoding="utf-8")

    assert "clonexa_hsp_table_access_" in source
    assert "function storedAccessCode()" in source
    assert "window.localStorage.getItem(key)" in source
    assert "window.localStorage.setItem(key, clean)" in source
    assert "function forgetAccessCode()" in source
    assert 'raw.includes("mesa_no_activada")' in source
    assert 'raw.includes("clave_de_mesa_invalida")' in source
    assert 'window.addEventListener("popstate"' in source
    assert "window.history.pushState" in source
    assert 'window.addEventListener("beforeunload"' in source
    assert "!isAssemblyMode()" in source
    assert "030G_TABLE_SESSION_LOCK" in html


def test_bar_accounts_have_independent_cards_and_product_loading():
    source = Path("app/web/client.js").read_text(encoding="utf-8")
    html = Path("app/web/client.html").read_text(encoding="utf-8")
    backend = Path("app/api/v1/endpoints/hospitality.py").read_text(encoding="utf-8")

    assert 'id="hspBarAccounts031D"' in source
    assert "Cuentas independientes" in source
    assert "data-hsp-bar-create" in source
    assert "data-hsp-bar-add" in source
    assert "data-hsp-bar-close" in source
    assert 'id="hspBarProductSearch031F"' in source
    assert 'list="hspBarInventoryList031F"' in source
    assert "cxHspFindInventoryBySearch031F" in source
    assert 'id="hspBarDestination031F"' in source
    assert 'id="hspBarTargetTable031F"' in source
    assert 'source: "table_manual"' in source
    assert "data-hsp-close-received" in source
    assert "cxHspUpdateCloseChange030F" in source
    assert "hspBarReference031D" not in source
    assert "Sin canciones solicitadas" not in source
    assert "cxHspIsBarAccount031D" in source
    assert 'router.post("/companies/{company_id}/bar-accounts"' in backend
    assert 'router.post("/companies/{company_id}/bar-accounts/{account_id}/items")' in backend
    assert "'bar_account', 'bar_account'" in backend
    assert "initial_items = await _build_order_items" in backend
    assert 'items: list[HospitalityOrderItemIn]' in backend
    assert "031D_BAR_ACCOUNTS_ALERTS_ARCHIVE" in html
    assert "031F_SMART_BAR_TABLES" in html


def test_repeated_bar_products_are_merged_into_one_quantity_and_total():
    items = [
        {"id": "line-1", "inventory_item_id": "aguila", "name": "CERVEZA Aguila", "quantity": 1, "unit_price": 5000, "subtotal": 5000},
        {"id": "line-2", "inventory_item_id": "poker", "name": "CERVEZA Poker", "quantity": 2, "unit_price": 5000, "subtotal": 10000},
        {"id": "line-3", "inventory_item_id": "aguila", "name": "CERVEZA Aguila", "quantity": 3, "unit_price": 5000, "subtotal": 15000},
        {"id": "line-4", "inventory_item_id": "aguila", "name": "CERVEZA Aguila", "quantity": 2, "unit_price": 5000, "subtotal": 10000},
    ]

    merged = hospitality._merge_hospitality_items(items)

    assert len(merged) == 2
    assert merged[0]["name"] == "CERVEZA Aguila"
    assert merged[0]["quantity"] == 6
    assert merged[0]["unit_price"] == 5000
    assert merged[0]["subtotal"] == 30000
    assert merged[1]["name"] == "CERVEZA Poker"
    assert merged[1]["quantity"] == 2
    assert merged[1]["subtotal"] == 10000
    assert sum(item["subtotal"] for item in merged) == 40000


def test_existing_bar_accounts_are_grouped_when_returned_to_the_panel():
    payload = hospitality._payload(
        {
            "id": uuid.uuid4(),
            "company_id": uuid.uuid4(),
            "source": "bar_account",
            "status": "entregado",
            "items": [
                {"inventory_item_id": "light", "name": "CERVEZA Aguila Light", "quantity": 1, "unit_price": 6000, "subtotal": 6000},
                {"inventory_item_id": "light", "name": "CERVEZA Aguila Light", "quantity": 2, "unit_price": 6000, "subtotal": 12000},
            ],
            "people": [],
            "songs": [],
            "metadata": {},
            "total": 18000,
        }
    )

    assert payload["total"] == 18000
    assert len(payload["items"]) == 1
    assert payload["items"][0]["quantity"] == 3
    assert payload["items"][0]["subtotal"] == 18000


def test_bar_account_panel_shows_one_grouped_line_with_quantity_badge():
    source = Path("app/web/client.js").read_text(encoding="utf-8")
    html = Path("app/web/client.html").read_text(encoding="utf-8")

    assert "cxHspGroupBarItems031Q" in source
    assert "cxHspBarQuantity031Q" in source
    assert "Cantidad ${h(cxHspBarQuantity031Q(item.quantity))}" in source
    assert "hsp-bar-line-total-031q" in source
    assert "031Q_BAR_ITEM_AGGREGATION" in html


def test_closed_orders_are_grouped_once_per_table_without_changing_report_data():
    source = Path("app/web/client.js").read_text(encoding="utf-8")
    html = Path("app/web/client.html").read_text(encoding="utf-8")
    backend = Path("app/api/v1/endpoints/hospitality.py").read_text(encoding="utf-8")

    closed_renderer = source.split("function cxHspRenderGroup024R", 1)[1].split("function cxHspMergedOrderCard024Y", 1)[0]
    assert 'status === "cerrado"' in closed_renderer
    assert "cxHspClosedTableGroups031R(list)" in closed_renderer
    assert "closedTables.map(cxHspClosedTableCard031R)" in closed_renderer
    assert 'data-hsp-closed-table=' in closed_renderer
    assert 'data-hsp-closed-order=' in closed_renderer
    assert "Cierres registrados:" in closed_renderer
    assert "QR / consecutivo" in closed_renderer
    assert "Consecutivo manual" in closed_renderer
    assert "Factura" in closed_renderer
    assert "cxHspPaymentLabel024V(order.payment_method)" in closed_renderer
    assert "hsp-closed-table-total-031s" in closed_renderer
    assert "Total cierres" in closed_renderer
    assert "cxHspMoney024R(group.total || 0)" in closed_renderer
    assert 'text("hspCClosed024R", cxHspClosedTableGroups031R(groups.cerrado).length)' in source
    assert "031R_CLOSED_TABLE_HISTORY" in html
    assert "031S_CLOSED_TABLE_TOTAL" in html

    # La API conserva cada cierre individual para reportes, PDF y exportaciones.
    list_endpoint = backend.split('async def list_hospitality_orders(', 1)[1].split('@router.post("/companies/{company_id}/song-requests"', 1)[0]
    assert 'orders = [_payload(row) for row in result.mappings().all()]' in list_endpoint
    assert '"orders": orders' in list_endpoint
    assert '"closed": counts[STATUS_CLOSED]' in list_endpoint


def test_hospitality_auto_refresh_waits_90_seconds_while_the_operator_is_editing():
    source = Path("app/web/client.js").read_text(encoding="utf-8")

    assert "cxHspInteractionHoldUntil031G" in source
    assert "function cxHspHoldInteraction031G(durationMs = 90000)" in source
    assert 'document.addEventListener("pointerdown"' in source
    assert 'document.addEventListener("focusin"' in source
    assert "cxHspInteractionHoldUntil031G > requestStartedAt" in source
    assert "cxHspLoadOrders024R({ auto: true })" in source


def test_hospitality_deactivates_inventory_at_the_configured_minimum():
    backend = Path("app/api/v1/endpoints/hospitality.py").read_text(encoding="utf-8")

    deduct = backend.split("async def _deduct_inventory", 1)[1].split("async def _create_day_closure", 1)[0]
    inventory_lite = backend.split("async def hospitality_inventory_lite", 1)[1].split('@router.get("/companies/{company_id}/orders")', 1)[0]
    assert "SELECT id, current_stock, min_stock, status" in deduct
    assert "deactivate_at_minimum = after <= minimum" in deduct
    assert "status = CASE WHEN :deactivate_at_minimum THEN 'inactive' ELSE status END" in deduct
    assert "COALESCE(current_stock, 0) <= COALESCE(min_stock, 0)" in inventory_lite
    assert "SET status = 'inactive'" in inventory_lite
    assert "allow_inactive_reserved: bool = False" in deduct
    assert 'and not allow_inactive_reserved' in deduct
    assert "await _deduct_inventory(db, company_id, order, allow_inactive_reserved=True)" in backend
    assert "Reserve stock as soon as an order is accepted" in backend
    assert "SET inventory_deducted = TRUE" in backend


@pytest.mark.asyncio
async def test_legacy_accepted_order_can_finish_after_minimum_auto_deactivation():
    company_id = uuid.uuid4()
    item_id = uuid.uuid4()
    order_id = uuid.uuid4()

    class ScalarOrMappingResult:
        def __init__(self, *, scalar_value=None, row=None):
            self.scalar_value = scalar_value
            self.row = row

        def scalar(self):
            return self.scalar_value

        def mappings(self):
            return self

        def first(self):
            return self.row

    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarOrMappingResult(scalar_value="inventory_items"),
                ScalarOrMappingResult(row={"id": item_id, "current_stock": 4, "min_stock": 4, "status": "inactive"}),
                ScalarOrMappingResult(),
                ScalarOrMappingResult(scalar_value=None),
            ]
        )
    )
    order = {
        "id": str(order_id),
        "order_number": "QR-TEST-1",
        "table_number": "Mesa 8",
        "inventory_deducted": False,
        "items": [{"inventory_item_id": str(item_id), "name": "Cerveza Costeña", "quantity": 1}],
    }

    await hospitality._deduct_inventory(db, company_id, order, allow_inactive_reserved=True)

    update_call = db.execute.await_args_list[2]
    assert "SET current_stock = :after" in str(update_call.args[0])
    assert update_call.args[1]["after"] == 3
    assert update_call.args[1]["deactivate_at_minimum"] is True


@pytest.mark.asyncio
async def test_legacy_accepted_order_still_refuses_negative_inventory():
    company_id = uuid.uuid4()
    item_id = uuid.uuid4()

    class ScalarOrMappingResult:
        def __init__(self, *, scalar_value=None, row=None):
            self.scalar_value = scalar_value
            self.row = row

        def scalar(self):
            return self.scalar_value

        def mappings(self):
            return self

        def first(self):
            return self.row

    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarOrMappingResult(scalar_value="inventory_items"),
                ScalarOrMappingResult(row={"id": item_id, "current_stock": 0, "min_stock": 4, "status": "inactive"}),
            ]
        )
    )
    order = {
        "inventory_deducted": False,
        "items": [{"inventory_item_id": str(item_id), "name": "Cerveza Costeña", "quantity": 1}],
    }

    with pytest.raises(hospitality.HTTPException) as exc:
        await hospitality._deduct_inventory(db, company_id, order, allow_inactive_reserved=True)

    assert exc.value.status_code == 409
    assert "Stock insuficiente" in exc.value.detail


def test_song_request_is_independent_from_the_qr_cart_and_visible_to_bartender():
    public = Path("app/web/hospitality_order.js").read_text(encoding="utf-8")
    public_html = Path("app/web/hospitality_order.html").read_text(encoding="utf-8")
    panel = Path("app/web/client.js").read_text(encoding="utf-8")
    panel_html = Path("app/web/client.html").read_text(encoding="utf-8")
    backend = Path("app/api/v1/endpoints/hospitality.py").read_text(encoding="utf-8")

    assert "¿Qué deseas escuchar?" in public
    assert "Música de plancha, Simplemente amigos, Juan Gabriel" in public
    assert 'id="qrSongRequest031C"' in public
    assert "data-submit-song" in public
    assert "/song-requests`" in public
    assert "qrSongs024S" not in public
    assert "Salsa choque" not in public
    assert "Provenza" not in public

    assert 'router.post("/companies/{company_id}/song-requests"' in backend
    assert 'router.patch("/companies/{company_id}/song-requests/{request_id}/status")' in backend
    assert "CREATE TABLE IF NOT EXISTS hospitality_song_requests" in backend
    assert '"song_requests": song_requests' in backend

    assert "Solicitudes musicales" in panel
    assert "Nueva solicitud musical" in panel
    assert "data-hsp-song-status" not in panel
    assert "Marcar sonando" not in panel
    assert "Marcar reproducida" not in panel
    assert "data-hsp-song-archive" in panel
    assert "data-hsp-song-search" in panel
    assert "hsp-song-table-head-031h" in panel
    assert "max-height:310px;overflow-y:auto" in panel
    assert "031L_LIVE_QR_ORDERS_KANBAN" in panel_html
    assert "cxHspPaintSongQueue031K(songs)" in panel
    assert "cxHspPaintLiveOrders031L(orders)" in panel
    live_orders = panel.split("function cxHspPaintLiveOrders031L", 1)[1].split("function cxHspIsBarAccount031D", 1)[0]
    assert 'fill("hspPending024R"' in live_orders
    assert 'fill("hspPreparing024R"' in live_orders
    assert 'fill("hspServed024R"' in live_orders
    assert 'fill("hspClosed024R"' in live_orders
    assert 'text("hspSOpenTables031D"' in live_orders
    assert 'text("hspSTotal024R"' in live_orders
    assert "if (signature(nextOrders) === signature(cxHspOrders024R)) return" in live_orders
    assert 'cxHspApi024R("/orders?status=all&limit=500")' in panel
    assert "window.setInterval(cxHspPollGlobalAlerts031H, 2000)" in panel
    song_card = panel.split("function cxHspSongRequestCard031C", 1)[1].split("function cxHspRenderSongRequests031C", 1)[0]
    song_list = panel.split("function cxHspRenderSongRequests031C", 1)[1].split("function cxHspPaintSongQueue031K", 1)[0]
    assert "customer_name" not in song_card
    assert "created_at" not in song_card
    assert "hsp-song-time-031h" not in song_card
    assert "Mesa / cliente" not in song_list
    assert "<span>Hora</span>" not in song_list
    assert "<span>Mesa</span>" in song_list
    assert "overflow-wrap:anywhere;white-space:normal" in panel
    assert 'router.post("/companies/{company_id}/song-requests/{request_id}/archive")' in backend
    assert "CAST(:next_status AS VARCHAR)" in backend
    assert "pg_advisory_xact_lock" in backend
    assert '"song_requests": song_requests' in backend
    assert "cxHspDashSongRequests031D" in panel
    assert "firstDirectSongAt" in panel
    assert "031E_DASHBOARD_SONG_ARCHIVE" in panel_html
    assert "031C_FREE_SONG_REQUESTS" in public_html
    assert "031C_FREE_SONG_REQUESTS" in panel_html


def test_qr_hides_stock_and_panel_has_independent_alert_switches_and_new_kpis():
    public = Path("app/web/hospitality_order.js").read_text(encoding="utf-8")
    public_html = Path("app/web/hospitality_order.html").read_text(encoding="utf-8")
    panel = Path("app/web/client.js").read_text(encoding="utf-8")

    product_card = public.split("const productCards =", 1)[1].split("const itemCount =", 1)[0]
    assert "Stock ${" not in product_card
    assert "· Stock" not in product_card
    assert "031D_HIDE_QR_STOCK" in public_html
    assert "data-hsp-toggle-visual-alerts" in panel
    assert "data-hsp-toggle-sound-alerts" in panel
    assert "cxHspStartGlobalMonitor031H" in panel
    assert "cxHspPollGlobalAlerts031H" in panel
    assert 'source: "qr_table"' in panel
    assert "Nueva mesa activa" in panel
    assert "Próximo en acabar" in panel
    assert "Cantidad disponible" in panel
    assert "Mesas abiertas" in panel


@pytest.mark.asyncio
async def test_song_status_query_uses_one_explicit_parameter_type(monkeypatch):
    company_id = uuid.uuid4()
    request_id = uuid.uuid4()
    current = {
        "id": request_id,
        "company_id": company_id,
        "status": "pendiente",
        "song": "Juan Gabriel",
    }
    updated = {**current, "status": "sonando"}
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[MappingResult(current), MappingResult(updated)]),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())

    response = await hospitality.update_hospitality_song_request_status(
        company_id,
        request_id,
        hospitality.HospitalitySongRequestStatusIn(status="sonando"),
        db,
    )

    statement = str(db.execute.await_args_list[1].args[0])
    params = db.execute.await_args_list[1].args[1]
    assert statement.count("CAST(:next_status AS VARCHAR)") == 3
    assert ":status" not in statement
    assert params["next_status"] == "sonando"
    assert response["song_request"]["status"] == "sonando"
