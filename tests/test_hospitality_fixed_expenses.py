"""Inventario (049M): tamaño numero + unidad, Gastos fijos (suma mes a mes y
por concepto, recibo) y el estado de resultados de Reportes que los descuenta.
Codigo real con una base en memoria."""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import fixed_expenses as endpoint
from app.api.v1.endpoints import inventory
from app.services import fixed_expenses as engine
from app.services import inventory_size as size
from app.services import owner_report

ROOT = Path(__file__).resolve().parent.parent
COMPANY = str(uuid.uuid4())
OTHER = str(uuid.uuid4())


# -------------------------------------------------------------- tamaño ---
@pytest.mark.parametrize("raw,expected", [
    ("275gr", ("275 gr", Decimal("275"), "gr")), ("280 grm", ("280 gr", Decimal("280"), "gr")),
    ("250GR", ("250 gr", Decimal("250"), "gr")), ("1.5lt", ("1.5 litros", Decimal("1.5"), "litros")),
    ("500 ml", ("500 ml", Decimal("500"), "ml")), ("1,5 L", ("1.5 litros", Decimal("1.5"), "litros")),
    ("2 kilos", ("2 kg", Decimal("2"), "kg")), ("1 lb", ("1 lb", Decimal("1"), "lb")), ("750 cc", ("750 ml", Decimal("750"), "ml")),
    ("12 und", ("12 unidad", Decimal("12"), "unidad")), ("3 paq.", ("3 paquete", Decimal("3"), "paquete")),
    ("1 docena", ("1 docena", Decimal("1"), "docena")), ("2 cajas", ("2 caja", Decimal("2"), "caja")),
])
def test_hospitality_inventory_size_converts_existing_values(raw, expected):
    result = size.normalize_existing(raw)
    assert (result["text"], result["value"], result["unit"]) == expected and result["review"] is False


@pytest.mark.parametrize("raw", ["M", "XL", "20m", "500", "1.500 ml", "Gramos 5", "0 gr"])
def test_hospitality_inventory_size_unknown_values_are_kept_and_flagged(raw):
    result = size.normalize_existing(raw)
    assert result == {"text": raw, "value": None, "unit": None, "review": True}, "se deja tal cual, marcado para revision"


def test_hospitality_inventory_size_form_number_and_unit():
    payload = inventory.InventoryItemUpdate(size_value="275", size_unit="gr")
    assert inventory._size_fields_049M(payload) == {"item_size": "275 gr", "size_value": Decimal("275"), "size_unit": "gr", "size_review": False}
    liters = inventory._size_fields_049M(inventory.InventoryItemUpdate(size_value=1.5, size_unit="litros"))
    assert liters["item_size"] == "1.5 litros"
    with pytest.raises(HTTPException) as exc:
        inventory._size_fields_049M(inventory.InventoryItemUpdate(size_value="275", size_unit="onzas"))
    assert exc.value.status_code == 422
    assert inventory._size_fields_049M(inventory.InventoryItemUpdate(color="Azul")) is None, "sin tamaño en el cambio: no se toca"
    legacy = inventory._size_fields_049M(inventory.InventoryItemUpdate(size="1.5lt"))
    assert legacy["item_size"] == "1.5 litros", "el CSV o integraciones con texto tambien se normalizan"
    assert size.UNIT_GROUPS == {"peso": ["gr", "lb", "kg"], "volumen": ["ml", "litros"], "unidad": ["unidad", "paquete", "caja", "docena"]}


def test_hospitality_inventory_size_migration_keeps_every_value():
    path = ROOT / "migrations/versions/022b_inventory_size.py"
    spec = importlib.util.spec_from_file_location("mig_022b", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = path.read_text(encoding="utf-8")
    assert len(module.revision) <= 32 and module.down_revision == "022a_payroll_cutoffs"
    assert module._engine().normalize_existing("275gr")["text"] == "275 gr", "usa la misma regla que la app"
    assert "size_original = COALESCE(size_original, item_size)" in source, "el texto original queda guardado"
    assert "UPDATE inventory_items SET size_review = true" in source and "WHERE id = :id AND company_id = :company_id" in source


# ------------------------------------------------------- gastos fijos ---
def rec(key, month, amount, label=None, group="servicios"):
    return {"concept_key": key, "concept_label": label or key.title(), "group_key": group, "month": month, "amount": Decimal(str(amount))}


CONCEPTS = {k: {"key": k, "label": label, "group": group} for k, label, group in engine.PRESET_CONCEPTS}


def test_hospitality_fixed_expenses_sum_by_month_and_concept():
    months = engine.months_back(date(2026, 9, 1), 3)
    assert months == [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]
    records = [rec("luz", date(2026, 8, 1), 180000), rec("luz", date(2026, 9, 1), 216000), rec("gas", date(2026, 9, 1), 90000),
               rec("gas", date(2026, 9, 1), 10000), rec("arriendo", date(2026, 9, 1), 2500000, group="arriendo"),
               rec("luz", date(2026, 3, 1), 999999)]  # fuera de la ventana
    table = engine.monthly_table(records, months, CONCEPTS)
    rows = {r["concept_key"]: r for r in table["rows"]}
    assert rows["luz"]["by_month"] == {"2026-07": 0.0, "2026-08": 180000.0, "2026-09": 216000.0}
    assert rows["luz"]["change_pct"] == 20.0, "la luz subio 20% contra agosto"
    assert rows["gas"]["by_month"]["2026-09"] == 100000.0 and rows["gas"]["total"] == 100000.0, "dos pagos del mismo mes se suman"
    assert table["totals_by_month"] == {"2026-07": 0.0, "2026-08": 180000.0, "2026-09": 2816000.0}
    assert table["total"] == 2996000.0
    assert [r["group"] for r in table["rows"]] == ["servicios", "servicios", "arriendo"], "servicios, arriendo, otros"


def test_hospitality_fixed_expenses_prorate_for_the_report_period():
    records = [rec("arriendo", date(2026, 9, 1), 3000000, group="arriendo"), rec("luz", date(2026, 8, 1), 310000)]
    week = engine.prorated(records, date(2026, 9, 1), date(2026, 9, 7))
    assert week["total"] == Decimal("700000.00"), "7/30 del arriendo de septiembre"
    across = engine.prorated(records, date(2026, 8, 25), date(2026, 9, 3))
    assert across["total"] == Decimal("370000.00"), "7/31 de la luz de agosto + 3/30 del arriendo de septiembre"


def test_hospitality_fixed_expenses_income_statement_deducts_them():
    bog = ZoneInfo("America/Bogota")
    closed = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    inv = str(uuid.uuid4())
    orders = [{"id": "a", "created_at": closed, "closed_at": closed, "status": "cerrado", "order_type": "table", "total": 1000000,
               "table_key": "m1", "table_number": "Mesa 1", "metadata": {}, "archived_at": closed,
               "items": [{"inventory_item_id": inv, "name": "Pollo", "quantity": 1, "subtotal": 1000000}]}]
    period = owner_report.resolve_period("custom", date(2026, 9, 25), date(2026, 9, 1), date(2026, 9, 30))
    report = owner_report.Report(orders=orders, closures=[], inventory={inv: {"name": "Pollo", "entry_price": 400000}},
                                 portions={}, tz=bog, period=period)
    kpis = report.kpis()
    fixed = engine.prorated([rec("arriendo", date(2026, 9, 1), 300000, group="arriendo"), rec("luz", date(2026, 9, 1), 100000)],
                            period["start"], period["end"])
    statement = owner_report.income_statement(kpis, fixed, {"total": 0})
    assert statement["gross_margin"] == 600000.0, "antes esta era la 'utilidad': ventas - mercancia"
    assert statement["fixed_expenses"] == 400000.0
    assert statement["operating_profit"] == 200000.0, "ahora descuenta arriendo y servicios"
    assert [c["label"] for c in statement["fixed_by_concept"]] == ["Arriendo", "Luz"]
    card = owner_report.profit_card(statement)
    assert card["key"] == "profit" and card["value"] == 200000.0
    assert card["label"] == "Utilidad después de gastos fijos" and card["note"] is None and statement["has_fixed_expenses"] is True
    # sin gastos fijos cargados: lo dice explicitamente, es margen bruto
    bare = owner_report.income_statement(kpis, {"total": 0}, {"total": 0})
    assert bare["has_fixed_expenses"] is False and bare["operating_profit"] == bare["gross_margin"] == 600000.0
    assert bare["warning"] == "Sin gastos fijos cargados, esta cifra es margen bruto, no utilidad real."
    bare_card = owner_report.profit_card(bare)
    assert bare_card["label"] == "Utilidad (sin gastos fijos: es margen bruto)" and bare_card["note"] == bare["warning"]


# ------------------------------------------------------------ endpoints ---
class Result:
    def __init__(self, rows=None, rowcount=1):
        self.rows, self.rowcount = rows or [], rowcount

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def fetchall(self):
        return [SimpleNamespace(_mapping=r) for r in self.rows]


class FixedDb:
    def __init__(self):
        self.modules = {COMPANY: {"inventory"}, OTHER: set()}
        self.concepts: list[dict] = []
        self.records: dict[str, dict] = {}
        self.receipts: dict[str, dict] = {}
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        cid = str(p.get("company_id", p.get("c", "")))
        if "FROM company_modules cm JOIN modules m" in sql:
            return Result([{"code": c} for c in self.modules.get(cid, set())])
        if sql.startswith("SELECT key, label, group_key FROM fixed_expense_concepts"):
            return Result([c for c in self.concepts if c["company_id"] == cid])
        if sql.startswith("INSERT INTO fixed_expense_concepts"):
            self.concepts.append({"company_id": cid, "key": p["key"], "label": p["label"], "group_key": p["group"]})
            return Result()
        if sql.startswith("SELECT e.id, e.concept_key"):
            rows = [{**r, "has_receipt": r["id"] in self.receipts and self.receipts[r["id"]].get("image_bytes") is not None}
                    for r in self.records.values() if r["company_id"] == cid and p["first"] <= r["month"] <= p["last"]]
            return Result(rows)
        if sql.startswith("INSERT INTO fixed_expenses"):
            self.records[p["id"]] = {"id": p["id"], "company_id": cid, "concept_key": p["concept_key"], "concept_label": p["concept_label"],
                                     "group_key": p["group_key"], "month": p["month"], "amount": p["amount"], "observation": p["observation"],
                                     "source": "manual", "created_by_name": p["by"], "created_at": datetime.now(timezone.utc)}
            return Result()
        if sql.startswith("DELETE FROM fixed_expense_receipts"):
            self.receipts.pop(p["id"], None)
            return Result()
        if sql.startswith("DELETE FROM fixed_expenses"):
            row = self.records.get(p["id"])
            if not row or row["company_id"] != cid:
                return Result(rowcount=0)
            del self.records[p["id"]]
            return Result()
        if sql.startswith("SELECT 1 AS ok FROM fixed_expenses"):
            row = self.records.get(p["id"])
            return Result([{"ok": 1}] if row and row["company_id"] == cid else [])
        if sql.startswith("SELECT COALESCE(SUM(size_bytes), 0) AS used FROM fixed_expense_receipts"):
            return Result([{"used": sum(r.get("size", 0) for k, r in self.receipts.items() if k != p["id"])}])
        if sql.startswith("INSERT INTO fixed_expense_receipts"):
            self.receipts.setdefault(p["id"], {})
            return Result()
        if sql.startswith("UPDATE fixed_expense_receipts SET image_bytes"):
            self.receipts[p["expense_id"]].update(image_bytes=p["image_bytes"], content_type=p["image_content_type"])
            return Result()
        if sql.startswith("UPDATE fixed_expense_receipts SET size_bytes"):
            row = self.receipts[p["id"]]
            row["size"] = len(row["image_bytes"])
            return Result()
        if sql.startswith("SELECT image_bytes, image_content_type FROM fixed_expense_receipts"):
            row = self.receipts.get(p["expense_id"])
            return Result([{"image_bytes": row["image_bytes"], "image_content_type": row["content_type"]}] if row else [])
        raise AssertionError(f"SQL no esperado: {sql[:160]}")


USERS = {
    "admin": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(COMPANY), role="company_admin", full_name="Dueña", email=""),
    "mesero": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(COMPANY), role="mesero", full_name="Pedro", email=""),
    "other": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(OTHER), role="company_admin", full_name="Otra", email=""),
}
client = TestClient(app_main.app)


@pytest.fixture
def api(monkeypatch):
    fake = FixedDb()

    async def get_user(_db, token):
        if token not in USERS:
            raise HTTPException(status_code=401, detail="Token requerido.")
        return USERS[token]

    async def fake_db():
        yield fake

    monkeypatch.setattr(deps, "get_current_company_user", get_user)
    monkeypatch.setattr(endpoint, "active_admin_v2_session", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    yield fake
    app_main.app.dependency_overrides.pop(get_db, None)


def call(method, path, token=None, body=None, company=COMPANY):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, f"/api/v1/fixed-expenses/companies/{company}{path}", json=body, headers=headers)


def _png():
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 180, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_hospitality_fixed_expenses_register_compare_and_attach_receipt(api):
    data = call("GET", "?until=2026-09&months=3", "admin").json()
    labels = [c["label"] for c in data["concepts"]]
    assert labels[:8] == ["Agua", "Luz", "Gas", "Internet", "Arriendo", "Aseo", "Mantenimiento", "Fumigación"]
    assert data["groups"] == {"servicios": "Servicios públicos", "arriendo": "Arriendo", "otros": "Otros gastos"}
    for month, amount in (("2026-08", 180000), ("2026-09", 216000)):
        assert call("POST", "/records", "admin", {"concept_key": "luz", "month": month, "amount": amount}).status_code == 200
    custom = call("POST", "/concepts", "admin", {"label": "Vigilancia", "group": "otros"})
    assert custom.status_code == 200 and custom.json()["created_key"] == "vigilancia"
    assert call("POST", "/concepts", "admin", {"label": "vigilancia"}).status_code == 409
    created = call("POST", "/records", "admin", {"concept_key": "vigilancia", "month": "2026-09", "amount": 50000,
                                                  "observation": "Ronda nocturna"}).json()
    rid = created["created_id"]
    assert call("POST", "/records", "admin", {"concept_key": "no_existe", "month": "2026-09", "amount": 1}).status_code == 400
    upload = client.post(f"/api/v1/fixed-expenses/companies/{COMPANY}/records/{rid}/receipt",
                         headers={"Authorization": "Bearer admin"}, files={"image": ("recibo.png", _png(), "image/png")})
    assert upload.status_code == 200, upload.text
    assert next(r for r in upload.json()["records"] if r["id"] == rid)["has_receipt"] is True
    assert len(api.receipts[rid]["image_bytes"]) <= 200 * 1024, "recibo comprimido por media_storage"
    receipt = call("GET", f"/records/{rid}/receipt", "admin")
    assert receipt.status_code == 200 and receipt.headers["content-type"].startswith("image/")
    table = call("GET", "?until=2026-09&months=2", "admin").json()["table"]
    luz = next(r for r in table["rows"] if r["concept_key"] == "luz")
    assert luz["by_month"] == {"2026-08": 180000.0, "2026-09": 216000.0} and luz["change_pct"] == 20.0
    assert table["totals_by_month"] == {"2026-08": 180000.0, "2026-09": 266000.0}
    assert call("DELETE", f"/records/{rid}", "admin").status_code == 200 and rid not in api.receipts


def test_hospitality_fixed_expenses_need_a_session_and_stay_in_their_company(api):
    assert call("GET", "", body=None).status_code == 401
    assert call("GET", "", "mesero").status_code == 403, "los paneles de mesero/cocina/caja no los ven"
    assert call("GET", "", "other").status_code == 403, "nunca de otra empresa"
    assert call("GET", "", "other", company=OTHER).status_code == 403, "sin Inventario, no aplica"
    rid = call("POST", "/records", "admin", {"concept_key": "agua", "month": "2026-09", "amount": 1000}).json()["created_id"]
    api.records[rid]["company_id"] = OTHER
    assert call("DELETE", f"/records/{rid}", "admin").status_code == 404, "el filtro por empresa esta en el SQL"
