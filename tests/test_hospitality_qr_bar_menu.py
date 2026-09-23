"""Carta de bar en la pantalla QR del cliente (interruptor qr_bar_menu).

El interruptor vive en los ajustes del módulo QR de cada empresa (apagado
por defecto) y llega a la página pública por GET qr-tables/access -> ui.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import hospitality

TIME_MACHINE = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"
ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"


class _Result:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _SettingsDb:
    def __init__(self, settings):
        self.settings = settings
        self.queries = []

    async def execute(self, statement, params=None):
        self.queries.append((str(statement), params or {}))
        if self.settings is None:
            return _Result(None)
        return _Result({"settings": self.settings})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings, expected",
    [
        ({"qr_bar_menu": True, "qr_config": {"orders_board": "mesas"}}, True),
        ({"qr_config": {"orders_board": "mesas"}}, False),
        ({"qr_bar_menu": "true"}, False),
        ('{"qr_bar_menu": true}', True),
        (None, False),
    ],
)
async def test_hospitality_qr_bar_menu_switch_is_off_by_default(settings, expected):
    db = _SettingsDb(settings)
    company_id = uuid.uuid4()

    ui = await hospitality._qr_customer_ui(db, company_id)

    assert ui == {"bar_menu": expected}
    sql, params = db.queries[0]
    assert "cm.company_id = :company_id" in sql
    assert params == {"company_id": str(company_id)}


@pytest.mark.asyncio
async def test_hospitality_qr_access_status_carries_the_switch_and_company_name(monkeypatch):
    company_id = uuid.UUID(TIME_MACHINE)
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(hospitality, "_fetch_active_table_access", AsyncMock(return_value=None))
    monkeypatch.setattr(hospitality, "_qr_company_name", AsyncMock(return_value="The Time Machine"))
    ui = AsyncMock(return_value={"bar_menu": True})
    monkeypatch.setattr(hospitality, "_qr_customer_ui", ui)

    response = await hospitality.get_hospitality_table_access(company_id, table="Mesa 5", db=object())

    assert response["access"]["active"] is False
    assert response["access"]["access_code"] is None  # nunca expone la clave
    assert response["company_name"] == "The Time Machine"
    assert response["ui"] == {"bar_menu": True}
    assert ui.await_args.args[1] == company_id


def _load_migration():
    path = Path("migrations/versions/021m_qr_bar_menu_ttm.py")
    spec = importlib.util.spec_from_file_location("mig_021m", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hospitality_qr_bar_menu_migration_targets_only_the_time_machine(monkeypatch):
    module = _load_migration()
    assert len(module.revision) <= 32
    assert module.down_revision == "021l_sale_document_settings"

    executed = []
    monkeypatch.setattr(module.op, "execute", executed.append, raising=False)
    module.upgrade()
    module.downgrade()

    up, down = executed
    assert f"cm.company_id = '{TIME_MACHINE}'::uuid" in up
    assert '{"qr_bar_menu": true}' in up
    assert ASADERO not in up
    assert "- 'qr_bar_menu'" in down
    assert f"cm.company_id = '{TIME_MACHINE}'::uuid" in down


def test_hospitality_qr_page_loads_the_shared_menu_kit_before_the_page():
    html = Path("app/web/hospitality_order.html").read_text(encoding="utf-8")
    kit = html.index("/client-static/hsp_menu_kit.js")
    page = html.index("/client-static/hospitality_order.js")
    assert kit < page
    # versiones anteriores se conservan (otras pruebas las buscan)
    assert "033H_SHARED_TABLE_ACCOUNTS" in html
    assert "047A_QR_BAR_MENU" in html


def test_hospitality_qr_bar_icons_do_not_change_other_panels():
    kit = Path("app/web/hsp_menu_kit.js").read_text(encoding="utf-8")
    assert "const tables = opts.bar ? [...BAR_MENU_EMOJIS, ...MENU_EMOJIS] : MENU_EMOJIS;" in kit
    # el panel mesero y la caja no piden { bar: true }
    for panel in ("app/web/hsp_waiter.js", "app/web/hsp_cashier.js"):
        assert "bar: true" not in Path(panel).read_text(encoding="utf-8")
