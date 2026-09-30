"""049V: rediseno de la caja (ASADERO): indicadores del turno, Z del dia y el
tema de la empresa en los mini paneles. Motor puro + endpoints (interruptor,
sesion del rol y filtro por empresa) + migracion."""
from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import waiter_ordering as wo
from app.services import cashier_summary as cs

SINCE = datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc)
COMPANY_ID = uuid.UUID("7625872c-f941-4479-a27b-f8443be953c5")


def order(oid, *, status="cerrado", total=0, method="cash", created=10, closed=None, table="Mesa 1", items=None,
          meta=None, order_type="table"):
    return {
        "id": oid, "order_number": f"QR-20260929-{oid}", "status": status, "total": total, "payment_method": method,
        "created_at": SINCE + timedelta(minutes=created), "closed_at": (SINCE + timedelta(minutes=closed)) if closed is not None else None,
        "table_key": table.lower(), "table_number": table, "order_type": order_type,
        "items": items or [{"name": "Pollo", "quantity": 1, "unit_price": total, "subtotal": total}],
        "metadata": meta or {},
    }


DIRECT = {"cashier_sale": {"kind": "independiente", "send_to_kitchen": False, "by": {"name": "Caja Uno"}}}
DELIVERY_META = {"delivery": {"customer_name": "Marcela"}}


def shift_orders():
    return [
        order("1", total=50000, method="cash", created=5, closed=40, table="Mesa 1"),
        order("2", total=30000, method="transfer", created=10, closed=40, table="Mesa 1"),   # se cerro con la 1: misma cuenta
        order("3", total=20000, method="card", created=15, closed=30, table="Mesa 2"),
        order("4", status="entregado", total=40000, created=50, table="Mesa 3"),            # por cobrar
        order("5", total=9000, method="cash", created=20, closed=20, table="Venta 012", meta=DIRECT),
        order("6", total=61000, method="qr", created=25, closed=60, table="Domicilio A1", meta=DELIVERY_META, order_type="domicilio"),
        order("7", status="cancelado", total=99999, created=30, table="Mesa 4"),
        # Abierta antes del turno y cobrada dentro: es del turno.
        order("8", total=15000, method="cash", created=-90, closed=12, table="Mesa 5"),
        # Abierta y cobrada antes del turno: no.
        order("9", total=77000, method="cash", created=-200, closed=-100, table="Mesa 6"),
    ]


def test_hospitality_shift_indicators_add_up():
    s = cs.shift_summary(shift_orders(), SINCE)
    assert s["sold"] == 225000.0                       # 50+30+20+40+9+61+15
    assert s["charged"] == 185000.0
    assert s["pending"] == 40000.0
    assert s["charged"] + s["pending"] == s["sold"]     # cuadra
    methods = {m["method"]: m for m in s["methods"]}
    assert (methods["cash"]["total"], methods["cash"]["count"]) == (74000.0, 3)
    assert methods["transfer"]["total"] == 91000.0     # 30.000 + el QR del domicilio
    assert methods["card"]["total"] == 20000.0
    assert sum(m["total"] for m in s["methods"]) == s["charged"]
    assert s["orders"] == 7
    assert s["deliveries"] == 1
    assert s["tables"] == 4                            # Mesa 1 (dos pedidos, una cuenta), 2, 3 y 5
    assert s["accounts"] == 6
    assert s["ticket"] == round(225000 / 6, 2)
    assert [r["label"] for r in s["direct_sales"]] == ["Venta 012"]
    sale = s["direct_sales"][0]
    assert (sale["paid"], sale["method"], sale["method_label"], sale["cashier"]) == (True, "cash", "Efectivo", "Caja Uno")


def test_hospitality_shift_methods_always_show_the_three():
    s = cs.shift_summary([], SINCE)
    assert [m["method"] for m in s["methods"]] == ["cash", "transfer", "card"]
    assert s["sold"] == 0 and s["ticket"] == 0.0


def test_hospitality_z_report_totals_products_and_methods():
    fee = {"name": "Domicilio", "quantity": 1, "unit_price": 5000, "subtotal": 5000, "station": "domicilio"}
    day = [
        order("1", total=40000, method="cash", items=[{"name": "Pollo", "quantity": 0.75, "quantity_label": "3/4", "unit_price": 40000, "subtotal": 30000},
                                                      {"name": "Gaseosa", "quantity": 2, "unit_price": 5000, "subtotal": 10000}]),
        order("2", total=25000, method="card", table="Mesa 2", items=[{"name": "Gaseosa", "quantity": 1, "unit_price": 5000, "subtotal": 5000},
                                                                       {"name": "Carne", "quantity": 1, "unit_price": 20000, "subtotal": 20000}]),
        order("3", total=45000, method="qr", table="Domicilio B", meta=DELIVERY_META, order_type="domicilio",
              items=[{"name": "Carne", "quantity": 2, "unit_price": 20000, "subtotal": 40000}, fee]),
        order("4", status="alistando", total=12000, table="Mesa 3"),
        order("5", status="cancelado", total=8000, table="Mesa 4"),
    ]
    z = cs.z_report(day)
    assert z["total"] == 110000.0
    assert z["sales"] == 3 and z["orders"] == 3
    assert z["products"] == 7.0                         # 1 porcion de pollo + 2 + 1 gaseosas + 1 + 2 carnes; el domicilio no
    methods = {m["method"]: m["total"] for m in z["methods"]}
    assert methods == {"cash": 40000.0, "transfer": 45000.0, "card": 25000.0}
    assert sum(methods.values()) == z["total"]
    assert (z["open_count"], z["open_total"]) == (1, 12000.0)
    assert (z["cancelled_count"], z["cancelled_total"]) == (1, 8000.0)
    items = {i["name"]: i for i in z["items"]}
    assert items["Gaseosa"]["units"] == 3.0 and items["Gaseosa"]["total"] == 15000.0
    assert "Domicilio" not in items
    assert {c["channel"]: c["count"] for c in z["channels"]} == {"mesa": 2, "domicilio": 1}


# ------------------------------------------------------------ endpoints ---
def _caja():
    return SimpleNamespace(id=uuid.uuid4(), full_name="Caja Uno", role="caja", settings_json={})


class ZDb:
    def __init__(self):
        self.calls = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.calls.append((sql, params or {}))
        rows = []
        if "INSERT INTO cashier_z_reports" in sql:
            rows = [{"id": params["id"], "number": 7, "business_day": params["day"], "cashier_name": params["cashier_name"],
                     "total": params["total"], "summary": json.loads(params["summary"]),
                     "created_at": datetime(2026, 9, 30, 3, 43, tzinfo=timezone.utc)}]
        elif "FROM companies" in sql:
            rows = [{"name": "ASADERO EL SOCIO"}]
        elif "FROM hospitality_orders" in sql:
            rows = shift_orders()
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: rows[0] if rows else None, all=lambda: rows))

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(wo, "_module_settings", AsyncMock(return_value={"cashier_redesign": True, "mini_panel_brand": True}))
    tz = ZoneInfo("America/Bogota")
    monkeypatch.setattr(wo, "_company_clock", AsyncMock(return_value=("America/Bogota", tz, None, date(2026, 9, 29))))
    from app.api.v1.endpoints import cash_count

    monkeypatch.setattr(cash_count, "open_cashier_session", AsyncMock(return_value={"id": "s1", "started_at": SINCE}))


@pytest.mark.asyncio
async def test_hospitality_redesign_endpoints_need_the_switch(monkeypatch):
    monkeypatch.setattr(wo, "_module_settings", AsyncMock(return_value={}))
    for call in (wo.cashier_shift_summary, wo.cashier_z_preview, wo.cashier_z_register):
        with pytest.raises(HTTPException) as err:
            await call(COMPANY_ID, db=ZDb(), user=_caja())
        assert err.value.status_code == 404
    theme = await wo.mini_panel_theme(COMPANY_ID, db=ZDb(), _user=_caja())
    assert theme == {"ok": True, "enabled": False, "branding": None}


@pytest.mark.asyncio
async def test_hospitality_z_register_is_computed_on_the_server_and_saved(on):
    db = ZDb()
    user = _caja()
    saved = await wo.cashier_z_register(COMPANY_ID, db=db, user=user)
    insert_sql, params = next((sql, p) for sql, p in db.calls if "INSERT INTO cashier_z_reports" in sql)
    assert params["company_id"] == str(COMPANY_ID)
    assert "WHERE company_id = CAST(:company_id AS uuid)" in insert_sql        # consecutivo por empresa
    assert params["user_id"] == str(user.id) and params["cashier_name"] == "Caja Uno"
    assert params["total"] == cs.z_report(shift_orders(), SINCE)["total"]
    assert db.commits == 1
    assert saved["number"] == 7
    assert saved["cashier_name"] == "Caja Uno"
    assert saved["created_local"].startswith("29/09/2026 10:43")               # hora de Colombia
    assert saved["summary"]["company_name"] == "ASADERO EL SOCIO"
    assert {m["method"] for m in saved["summary"]["methods"]} >= {"cash", "transfer", "card"}


@pytest.mark.asyncio
async def test_hospitality_z_preview_and_detail_filter_by_company(on):
    db = ZDb()
    preview = await wo.cashier_z_preview(COMPANY_ID, db=db, user=_caja())
    assert preview["z"]["total"] == cs.z_report(shift_orders(), SINCE)["total"]
    history_sql, params = next((sql, p) for sql, p in db.calls if "FROM cashier_z_reports" in sql)
    assert "company_id = CAST(:company_id AS uuid)" in history_sql and params["company_id"] == str(COMPANY_ID)
    db = ZDb()
    with pytest.raises(HTTPException) as err:                                  # un Z de otra empresa no aparece
        await wo.cashier_z_detail(COMPANY_ID, uuid.uuid4(), db=db, _user=_caja())
    assert err.value.status_code == 404
    detail_sql, _params = next((sql, p) for sql, p in db.calls if "FROM cashier_z_reports" in sql)
    assert "AND company_id = CAST(:company_id AS uuid)" in detail_sql


@pytest.mark.asyncio
async def test_hospitality_shift_summary_uses_the_cashier_open_shift(on):
    db = ZDb()
    result = await wo.cashier_shift_summary(COMPANY_ID, db=db, user=_caja())
    sql, params = next((q, p) for q, p in db.calls if "FROM hospitality_orders" in q)
    assert "company_id = CAST(:company_id AS uuid)" in sql and params["company_id"] == str(COMPANY_ID)
    # 049Z: la misma lectura de ventas que Reportes (sales_ledger.load_orders)
    assert "((created_at >= :start) OR (closed_at >= :start))" in sql and params["start"] == SINCE
    assert result["shift_open"] is True
    assert result["sold"] == 225000.0


@pytest.mark.asyncio
async def test_hospitality_panel_theme_returns_only_the_brand(monkeypatch):
    from app.api.v1.endpoints import companies

    monkeypatch.setattr(wo, "_module_settings", AsyncMock(return_value={"mini_panel_brand": True}))
    monkeypatch.setattr(companies, "_get_company_or_404", AsyncMock(return_value=SimpleNamespace(id=COMPANY_ID)))
    monkeypatch.setattr(companies, "_read_company_branding", lambda _c: {
        "primary_color": "#51b6e1", "background_color": "#ffedbd", "theme_mode": "light", "custom_css_json": {"x": 1}, "logo_url": "data:image/webp;base64,AA"})
    theme = await wo.mini_panel_theme(COMPANY_ID, db=ZDb(), _user=_caja())
    assert theme["enabled"] is True
    assert theme["branding"] == {"logo_url": "data:image/webp;base64,AA", "primary_color": "#51b6e1", "background_color": "#ffedbd", "theme_mode": "light"}


def test_hospitality_redesign_routes_require_a_role_session():
    from app.main import app

    expected = {
        "/api/v1/companies/{company_id}/waiter-ordering/panel-theme": "_require_menu_reader",
        "/api/v1/companies/{company_id}/waiter-ordering/caja/resumen": "_require_caja",
        "/api/v1/companies/{company_id}/waiter-ordering/caja/z": "_require_caja",
        "/api/v1/companies/{company_id}/waiter-ordering/caja/z/{z_id}": "_require_caja",
    }
    seen = {}
    for route in app.routes:
        if getattr(route, "path", None) in expected:
            deps = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
            seen.setdefault(route.path, set()).update(deps)
    for path, dep in expected.items():
        assert dep in seen.get(path, set()), path
    # La caja es solo del rol caja; el tema lo leen mesero, cocina y caja.
    assert wo._require_caja.__name__ == "_require_caja"


# ------------------------------------------------------------ migracion ---
MIGRATION = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "022j_cashier_redesign.py"


class FakeOp:
    def __init__(self):
        self.statements = []

    def execute(self, stmt):
        self.statements.append(str(stmt))


def _migration():
    spec = importlib.util.spec_from_file_location("cashier_redesign_mig", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hospitality_redesign_migration_is_only_for_asadero(monkeypatch):
    module = _migration()
    assert len(module.revision) <= 32
    assert module.down_revision == "022i_purchase_invoices"
    op = FakeOp()
    monkeypatch.setattr(module, "op", op)
    module.upgrade()
    joined = "\n".join(op.statements)
    assert "CREATE TABLE IF NOT EXISTS cashier_z_reports" in joined
    assert "company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE" in joined
    assert "UNIQUE (company_id, number)" in joined
    assert f"cm.company_id = '{COMPANY_ID}'::uuid" in joined
    assert json.loads(module.SETTINGS_PATCH) == {"cashier_redesign": True, "mini_panel_brand": True}
    op = FakeOp()
    monkeypatch.setattr(module, "op", op)
    module.downgrade()
    joined = "\n".join(op.statements)
    assert "- 'cashier_redesign' - 'mini_panel_brand'" in joined
    assert "DROP TABLE IF EXISTS cashier_z_reports" in joined
