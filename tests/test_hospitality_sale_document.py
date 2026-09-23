"""Documento de venta de la caja (waiter_ordering).

- Always "CUENTA DE COBRO" + "NO ES FACTURA DE VENTA", internal consecutive.
- DIAN switch on: legal data kept, a pending-integration notice, and still
  NOT a factura (nothing is connected to the DIAN).
- The printed lines/total match what the table consumed.
- A reprint keeps its number; a different set of orders gets the next one.
- Sessions required; only with waiter_ordering; tenant-scoped.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import hospitality, sale_document, waiter_ordering


COMPANY_ID = uuid.uuid4()
IDENTITY = {"name": "Asadero El Socio", "logo_url": "https://cdn.example/logo.png"}


def _order(table="Mesa 4", status="entregado", items=None, created_at="2026-09-23T18:00:00+00:00", payment_method="other", company_id=COMPANY_ID):
    return {
        "id": str(uuid.uuid4()),
        "company_id": str(company_id),
        "table_number": table,
        "status": status,
        "payment_method": payment_method,
        "items": items if items is not None else [
            {"name": "POLLO Asado", "quantity": 0.75, "quantity_label": "3/4", "unit_price": 40000, "subtotal": 30000},
            {"name": "GASEOSA Coca Cola", "quantity": 2, "unit_price": 4500, "subtotal": 9000, "observations": "fria"},
        ],
        "total": 39000,
        "metadata": {"waiter": {"id": "w1", "name": "Laura"}},
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Pure document rules
# ---------------------------------------------------------------------------

def test_document_is_always_a_cuenta_de_cobro_and_says_it_is_not_a_factura():
    config = {**sale_document.DEFAULT_CONFIG, "trade_name": "El Socio", "nit": "900123456-7", "prefix": "CC"}
    doc = sale_document.build_sale_document(config, IDENTITY, [hospitality._payload(_order())], "CC-000001", "2026-09-23T19:00:00+00:00")
    assert doc["title"] == "CUENTA DE COBRO"
    assert doc["not_invoice_notice"] == "NO ES FACTURA DE VENTA"
    assert doc["dian_pending_notice"] == ""
    assert "factura" not in doc["title"].lower()
    assert doc["number"] == "CC-000001"
    assert doc["number_label"] == "Consecutivo interno"


def test_dian_switch_on_keeps_it_a_cuenta_de_cobro_with_a_pending_notice():
    config = {**sale_document.DEFAULT_CONFIG, "dian_electronic_enabled": True, "dian_resolution_number": "18760000001"}
    doc = sale_document.build_sale_document(config, IDENTITY, [hospitality._payload(_order())], "000001", "x")
    assert doc["title"] == "CUENTA DE COBRO"
    assert doc["not_invoice_notice"] == "NO ES FACTURA DE VENTA"
    assert "proveedor" in doc["dian_pending_notice"] and "DIAN" in doc["dian_pending_notice"]


def test_document_lines_and_total_match_what_the_table_consumed():
    orders = [hospitality._payload(_order()), hospitality._payload(_order(items=[
        {"name": "CERVEZA Aguila", "quantity": 3, "unit_price": 5000, "subtotal": 15000},
    ], created_at="2026-09-23T18:30:00+00:00"))]
    doc = sale_document.build_sale_document(sale_document.DEFAULT_CONFIG, IDENTITY, orders, "000007", "x")
    assert [(l["qty"], l["name"], l["subtotal"]) for l in doc["lines"]] == [
        ("3/4", "POLLO Asado", 30000), ("2", "GASEOSA Coca Cola", 9000), ("3", "CERVEZA Aguila", 15000),
    ]
    assert doc["lines"][1]["observations"] == "fria"
    assert doc["total"] == 54000 == sum(o["total"] for o in [{"total": 39000}, {"total": 15000}])
    assert doc["table"] == "Mesa 4"
    assert doc["waiter"] == "Laura"


def test_issuer_uses_the_configured_data_and_falls_back_to_branding():
    config = {**sale_document.DEFAULT_CONFIG, "legal_name": "Socio SAS", "nit": "900", "regime": "regimen_simple", "address": "Cra 1", "phone": "300"}
    doc = sale_document.build_sale_document(config, IDENTITY, [hospitality._payload(_order())], "1", "x")
    assert doc["issuer"] == {
        "logo_url": "https://cdn.example/logo.png", "trade_name": "Asadero El Socio", "legal_name": "Socio SAS",
        "nit": "900", "address": "Cra 1", "phone": "300", "regime": "Régimen Simple de Tributación",
    }
    own_logo = {**config, "logo_url": "https://cdn.example/otro.png", "trade_name": "El Socio"}
    doc = sale_document.build_sale_document(own_logo, IDENTITY, [hospitality._payload(_order())], "1", "x")
    assert doc["issuer"]["logo_url"] == "https://cdn.example/otro.png"
    assert doc["issuer"]["trade_name"] == "El Socio"


def test_payment_label_appears_once_charged():
    doc = sale_document.build_sale_document(sale_document.DEFAULT_CONFIG, IDENTITY, [hospitality._payload(_order(status="cerrado", payment_method="cash"))], "1", "x")
    assert doc["payment_label"] == "Efectivo"
    doc = sale_document.build_sale_document(sale_document.DEFAULT_CONFIG, IDENTITY, [hospitality._payload(_order())], "1", "x")
    assert doc["payment_label"] == ""


@pytest.mark.parametrize(
    "total, rate, included, expected",
    [
        (119000, 19, True, {"subtotal": 100000, "iva": 19000, "total": 119000}),
        (100000, 19, False, {"subtotal": 100000, "iva": 19000, "total": 119000}),
        (39000, 0, True, {"subtotal": 39000, "iva": 0, "total": 39000}),
        (10000, 8, True, {"subtotal": 9259, "iva": 741, "total": 10000}),   # impoconsumo-style 8%
    ],
)
def test_iva_breakdown(total, rate, included, expected):
    assert sale_document.document_totals(total, rate, included) == expected


def test_config_validation():
    ok = sale_document.SaleDocumentConfigIn(prefix="cc", regime="RESPONSABLE_IVA", logo_url="https://x/logo.png")
    assert ok.prefix == "CC" and ok.regime == "responsable_iva"
    for bad in ({"prefix": "C C!"}, {"regime": "otro"}, {"logo_url": "javascript:alert(1)"}, {"iva_percent": 120}):
        with pytest.raises(Exception):
            sale_document.SaleDocumentConfigIn(**bad)
    assert sale_document.DEFAULT_CONFIG["dian_electronic_enabled"] is False     # off by default


def test_number_format():
    assert sale_document.format_document_number("CC", 7) == "CC-000007"
    assert sale_document.format_document_number("", 123) == "000123"


# ---------------------------------------------------------------------------
# Issuing (numbering) against a small fake of the two tables
# ---------------------------------------------------------------------------

class DocDb:
    def __init__(self, orders, config=None):
        self.rows = {o["id"]: o for o in orders}
        self.settings = {"config": config or {}, "last_number": 0} if config is not None else None
        self.commit = AsyncMock()

    def _result(self, rows=None, scalar=None):
        rows = rows or []
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: rows[0] if rows else None, all=lambda: rows), scalar=lambda: scalar)

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if sql.startswith("SELECT * FROM hospitality_orders"):
            rows = [copy.deepcopy(r) for r in self.rows.values()
                    if r["company_id"] == params["company_id"] and r["id"] in params["ids"] and r["status"] != "cancelado"]
            return self._result(rows)
        if sql.startswith("SELECT config, last_number FROM sale_document_settings"):
            return self._result([self.settings] if self.settings else [])
        if sql.startswith("INSERT INTO sale_document_settings") and "RETURNING last_number" in sql:
            if self.settings is None:
                self.settings = {"config": {}, "last_number": params["start"]}
            else:
                self.settings["last_number"] = max(self.settings["last_number"] + 1, params["start"])
            return self._result(scalar=self.settings["last_number"])
        if sql.startswith("UPDATE hospitality_orders SET metadata"):
            stamp = json.loads(params["stamp"])
            for order_id in params["ids"]:
                row = self.rows[order_id]
                assert row["company_id"] == params["company_id"]
                row["metadata"]["sale_document"] = stamp
            return self._result()
        raise AssertionError(f"unexpected SQL: {sql[:100]}")


@pytest.fixture(autouse=True)
def _identity(monkeypatch):
    monkeypatch.setattr(sale_document, "_hospitality_company_identity", AsyncMock(return_value=IDENTITY))


def _caja():
    return SimpleNamespace(id=uuid.uuid4(), full_name="Caja Uno", role="caja")


async def _issue(db, *orders):
    payload = sale_document.SaleDocumentRequest(order_ids=[uuid.UUID(o["id"]) for o in orders])
    return (await sale_document.issue_sale_document(COMPANY_ID, payload, db=db, user=_caja()))["document"]


@pytest.mark.asyncio
async def test_first_print_takes_the_next_consecutive_and_a_reprint_keeps_it():
    a, b = _order(), _order()
    db = DocDb([a, b], config={"prefix": "CC", "numbering_start": 100})
    first = await _issue(db, a, b)
    assert first["number"] == "CC-000100"
    again = await _issue(db, b, a)                     # same set, any order
    assert again["number"] == "CC-000100"
    assert db.settings["last_number"] == 100            # no number consumed by the reprint


@pytest.mark.asyncio
async def test_a_different_set_of_orders_gets_the_next_number():
    a, b = _order(), _order()
    db = DocDb([a, b], config={"prefix": "CC"})
    assert (await _issue(db, a))["number"] == "CC-000001"
    assert (await _issue(db, a, b))["number"] == "CC-000002"   # table got another order


@pytest.mark.asyncio
async def test_a_company_without_settings_starts_at_one_with_defaults():
    a = _order()
    db = DocDb([a], config=None)
    doc = await _issue(db, a)
    assert doc["number"] == "000001"
    assert doc["title"] == "CUENTA DE COBRO"


@pytest.mark.asyncio
async def test_another_companys_or_a_cancelled_order_is_404():
    foreign = _order(company_id=uuid.uuid4())
    cancelled = _order(status="cancelado")
    db = DocDb([foreign, cancelled], config={})
    for order in (foreign, cancelled):
        with pytest.raises(HTTPException) as exc:
            await _issue(db, order)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_a_charged_sale_can_still_be_printed_with_its_payment_method():
    sale = _order(table="Venta 012", status="cerrado", payment_method="card")
    doc = await _issue(DocDb([sale], config={}), sale)
    assert doc["table"] == "Venta 012"
    assert doc["payment_label"] == "Tarjeta"


# ---------------------------------------------------------------------------
# Config endpoints + auth
# ---------------------------------------------------------------------------

class ConfigDb:
    def __init__(self, row=None):
        self.row = row
        self.saved = None
        self.commit = AsyncMock()

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if sql.startswith("SELECT config, last_number"):
            rows = [self.row] if self.row else []
            return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: rows[0] if rows else None))
        if sql.startswith("INSERT INTO sale_document_settings"):
            self.saved = json.loads(params["config"])
            self.row = {"config": self.saved, "last_number": 0}
            return SimpleNamespace()
        raise AssertionError(sql[:80])


@pytest.mark.asyncio
async def test_config_defaults_to_dian_off_and_branding_logo():
    out = await sale_document.get_sale_document_config(COMPANY_ID, db=ConfigDb(), _actor="x")
    assert out["config"]["dian_electronic_enabled"] is False
    assert out["branding_logo_url"] == "https://cdn.example/logo.png"
    assert out["next_number"] == "000001"
    assert out["dian_pending_notice"] == ""


@pytest.mark.asyncio
async def test_config_saves_every_field_and_reports_the_next_number():
    db = ConfigDb()
    payload = sale_document.SaleDocumentConfigIn(trade_name="El Socio", nit="900", iva_percent=8, prefix="CC", footer="Gracias", dian_electronic_enabled=True)
    await sale_document.save_sale_document_config(COMPANY_ID, payload, db=db, actor="Dueno")
    assert db.saved["trade_name"] == "El Socio" and db.saved["prefix"] == "CC" and db.saved["dian_electronic_enabled"] is True
    out = await sale_document.get_sale_document_config(COMPANY_ID, db=ConfigDb({"config": db.saved, "last_number": 41}), _actor="x")
    assert out["next_number"] == "CC-000042"
    assert "proveedor" in out["dian_pending_notice"]


@pytest.mark.asyncio
async def test_config_requires_the_module_and_an_admin_session(monkeypatch):
    monkeypatch.setattr(sale_document, "require_enabled_module", AsyncMock(side_effect=HTTPException(status_code=403, detail="module_not_enabled_for_tenant")))
    with pytest.raises(HTTPException) as exc:
        await sale_document._require_sale_doc_admin(COMPANY_ID, SimpleNamespace(), authorization=None, db=SimpleNamespace())
    assert exc.value.status_code == 403                    # any company without waiter_ordering

    monkeypatch.setattr(sale_document, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(sale_document, "active_admin_v2_session", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await sale_document._require_sale_doc_admin(COMPANY_ID, SimpleNamespace(), authorization=None, db=SimpleNamespace())
    assert exc.value.status_code == 401

    tenant = AsyncMock(return_value=SimpleNamespace(full_name="Dueno", email=""))
    monkeypatch.setattr(sale_document, "require_company_user_for_tenant", tenant)
    assert await sale_document._require_sale_doc_admin(COMPANY_ID, SimpleNamespace(), authorization="Bearer t", db=SimpleNamespace()) == "Dueno"
    roles = tenant.await_args.kwargs["allowed_roles"]
    assert {"dueno", "company_admin", "administrador"} <= roles and "caja" not in roles and "mesero" not in roles


def test_every_route_requires_a_session():
    from fastapi.params import Depends as DependsParam
    import inspect

    def deps(endpoint):
        return [p.default.dependency for p in inspect.signature(endpoint).parameters.values() if isinstance(p.default, DependsParam)]

    assert sale_document._require_sale_doc_admin in deps(sale_document.get_sale_document_config)
    assert sale_document._require_sale_doc_admin in deps(sale_document.save_sale_document_config)
    assert waiter_ordering._require_caja in deps(sale_document.issue_sale_document)


def test_router_is_registered():
    from app.api.v1.router import api_router
    paths = {getattr(r, "path", "") for r in api_router.routes}
    assert "/companies/{company_id}/waiter-ordering/caja/documento" in paths
    assert "/companies/{company_id}/waiter-ordering/sale-document/config" in paths


def test_migration_creates_the_small_settings_table():
    path = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "021l_sale_document_settings.py"
    spec = importlib.util.spec_from_file_location("sale_doc_mig", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "021k_inv_allows_portions"
    ops = []
    module.op = SimpleNamespace(execute=lambda s: ops.append(str(s)))
    module.upgrade()
    sql = "\n".join(ops)
    assert "CREATE TABLE IF NOT EXISTS sale_document_settings" in sql
    assert "bytea" not in sql                            # no image bytes (CLAUDE.md)
    assert "INSERT" not in sql                            # no company gets data


@pytest.mark.asyncio
async def test_the_portal_preview_is_built_by_the_same_document_builder():
    db = ConfigDb()
    payload = sale_document.SaleDocumentConfigIn(trade_name="El Socio", prefix="CC", iva_percent=8, footer="Gracias por su visita")
    out = await sale_document.save_sale_document_config(COMPANY_ID, payload, db=db, actor="Dueno")
    preview = out["preview"]
    assert preview["title"] == "CUENTA DE COBRO" and preview["not_invoice_notice"] == "NO ES FACTURA DE VENTA"
    assert preview["number"] == "CC-000001"
    assert preview["issuer"]["trade_name"] == "El Socio"
    assert preview["footer"] == "Gracias por su visita"
    assert preview["total"] == 39000 and preview["iva"] == 2889     # 8% included in 39.000
