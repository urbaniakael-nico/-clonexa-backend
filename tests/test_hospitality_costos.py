"""Modulo COSTOS (049I): egresos, compras que actualizan inventario con costo
promedio, aprobaciones, cuentas por pagar, recurrentes, presupuesto y ARQUEO a
ciegas. Codigo real de los endpoints con una base en memoria."""
from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import costos as endpoint
from app.api.v1.endpoints import hospitality
from app.services import costos as engine

ROOT = Path(__file__).resolve().parent.parent
ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"
CAJERO_ID, OTRO_CAJERO_ID = uuid.uuid4(), uuid.uuid4()
POLLO = str(uuid.uuid4())
NOW = datetime.now(timezone.utc)


# ------------------------------------------------------------ motor ---
def test_hospitality_costos_totals_roles_and_approval_rules():
    assert engine.totals(100000, 19000, 2500)["total"] == Decimal("116500")
    with pytest.raises(ValueError):
        engine.totals(1000, 0, 2000)
    assert engine.role_kind("company_admin") == "owner" and engine.role_kind("dueno") == "owner"
    assert engine.role_kind("administrador") == "manager" and engine.role_kind("caja") == "cashier"
    assert engine.initial_status("owner", 9_000_000, 500000) == "aprobado"
    assert engine.initial_status("manager", 400000, 500000) == "aprobado"
    assert engine.initial_status("manager", 600000, 500000) == "pendiente", "por encima del tope: lo aprueba el dueño"
    assert engine.initial_status("cashier", 5000, 500000) == "pendiente", "el cajero siempre queda pendiente"
    assert engine.can_approve("manager", 600000, 500000) is False and engine.can_approve("owner", 600000, 500000) is True


def test_hospitality_costos_expected_cash_formula_and_denominations():
    assert engine.expected_cash(200000, 850000, 30000, 100000) == Decimal("920000")
    assert engine.count_from_denominations({50000: 3, 20000: 2, 1000: 5}) == Decimal("195000")
    with pytest.raises(ValueError):
        engine.count_from_denominations({30000: 1})
    assert engine.difference_label(-5000) == "faltante" and engine.difference_label(0) == "cuadrado"


def test_hospitality_costos_budget_price_variation_and_recurring():
    rows = engine.budget_status({"aseo": 100000}, {"aseo": 130000, "internet": 90000})
    aseo = next(r for r in rows if r["category"] == "aseo")
    assert aseo["over"] is True and aseo["pct"] == 130.0
    prices = engine.price_variation([{"date": "2026-09-02", "unit_cost": 22}, {"date": "2026-09-01", "unit_cost": 20}])
    assert [p["change_pct"] for p in prices] == [None, 10.0]
    assert engine.recurring_due(5, "2026-08", date(2026, 9, 5)) and not engine.recurring_due(5, "2026-09", date(2026, 9, 20))
    assert not engine.recurring_due(10, "2026-08", date(2026, 9, 5))


# ---------------------------------------------------- base en memoria ---
class Result:
    def __init__(self, rows=None, rowcount=1):
        self.rows, self.rowcount = rows or [], rowcount

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def fetchall(self):
        return [SimpleNamespace(_mapping=r) for r in self.rows]

    def first(self):
        return self.rows[0] if self.rows else None


class CostosDb:
    def __init__(self):
        self.modules = {ASADERO: {"costos", "carta", "waiter_ordering"}, TTM: {"hospitality"}}
        self.settings = {"approval_threshold": 500000, "drawer_base": 200000, "iva_is_cost": True}
        self.centers = []
        self.expenses: dict[str, dict] = {}
        self.lines: list[dict] = []
        self.inventory = {POLLO: {"id": uuid.UUID(POLLO), "company_id": ASADERO, "name": "Pollo crudo", "name_reference": "",
                                  "reference": "", "sku": "", "current_stock": Decimal("1000"), "min_stock": Decimal("0"),
                                  "status": "active", "entry_price": Decimal("0"), "sale_price": Decimal("0"),
                                  "avg_cost": Decimal("20"), "item_type": "ingrediente", "purchase_unit": "libra",
                                  "consumption_unit": "g", "units_per_purchase": Decimal("453.59237")}}
        self.movements = []
        self.sessions = {str(uuid.uuid4()): {"user_id": CAJERO_ID, "started_at": NOW - timedelta(hours=6), "ended_at": None, "status": "active"}}
        self.orders = []
        self.counts: dict[str, dict] = {}
        self.recurring = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    @property
    def session_id(self):
        return next(iter(self.sessions))

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        cid = str(p.get("company_id", p.get("c", "")))
        if "FROM company_modules cm JOIN modules m" in sql and "LOWER(m.code) AS code" in sql:
            return Result([{"code": c} for c in self.modules.get(cid, set())])
        if sql.startswith("SELECT cm.settings FROM company_modules cm"):
            return Result([{"settings": self.settings}] if "costos" in self.modules.get(cid, set()) else [])
        if "FROM companies c LEFT JOIN workforce_session_policy p" in sql:
            return Result([{"timezone": "America/Bogota", "cutoff_time": None, "alert_after_hours": None}])
        if sql.startswith("SELECT id FROM cost_centers"):
            return Result([{"id": c} for c in self.centers])
        if sql.startswith("INSERT INTO cost_centers"):
            self.centers.append(p["id"])
            return Result()
        if "FROM inventory_items WHERE company_id = CAST(:company_id AS uuid) AND COALESCE(status, 'active') NOT IN" in sql:
            return Result([v for v in self.inventory.values() if v["company_id"] == cid])
        if sql.startswith("SELECT id, user_id, started_at, ended_at, status FROM mini_panel_work_sessions WHERE company_id = CAST(:company_id AS uuid) AND panel_type = 'caja' AND status IN"):
            rows = [{"id": uuid.UUID(k), **v} for k, v in self.sessions.items() if v["status"] in ("active", "break")
                    and (not p.get("user_id") or str(v["user_id"]) == str(p["user_id"]))]
            return Result(rows[:1])
        if sql.startswith("INSERT INTO expenses"):
            self.expenses[p["id"]] = {"id": uuid.UUID(p["id"]), "company_id": cid, "cost_center_id": None, "expense_date": p["d"],
                                      "category": p["category"], "supplier_id": None, "supplier_name": p["supplier_name"],
                                      "description": p["description"], "subtotal": p["subtotal"], "iva": p["iva"], "retention": p["retention"],
                                      "total": p["total"], "payment_method": p["pm"], "paid_from": p["pf"], "status": p["status"],
                                      "due_date": p["due"], "paid_at": None if p["pm"] == "credito" else NOW, "recurring_id": p["rec"] or None,
                                      "cashier_session_id": p["sess"] or None, "petty_fund_id": None, "created_by_id": p["by_id"],
                                      "created_by_name": p["by_name"], "created_by_kind": p["by_kind"],
                                      "approved_by_name": p["by_name"] if p["status"] == "aprobado" else "", "rejected_reason": "",
                                      "inventory_applied": False}
            return Result()
        if sql.startswith("INSERT INTO expense_lines"):
            self.lines.append({"expense_id": p["e"], "inventory_item_id": uuid.UUID(p["i"]), "quantity": p["q"], "purchase_unit": p["pu"],
                               "unit_price": p["up"], "total": p["t"], "consumption_qty": p["cq"], "unit_cost": p["uc"]})
            return Result()
        if sql.startswith("SELECT * FROM expenses WHERE id"):
            row = self.expenses.get(p["id"])
            return Result([dict(row)] if row and row["company_id"] == cid else [])
        if sql.startswith("SELECT * FROM expense_lines WHERE"):
            return Result([l for l in self.lines if l["expense_id"] == p["e"]])
        if sql.startswith("SELECT l.*, COALESCE(NULLIF(i.name_reference"):
            return Result([{**l, "insumo": "Pollo crudo"} for l in self.lines if l["expense_id"] == p["id"]])
        if sql.startswith("SELECT id, current_stock, min_stock, avg_cost, units_per_purchase, status FROM inventory_items"):
            row = self.inventory.get(p["id"])
            return Result([row] if row else [])
        if sql.startswith("UPDATE inventory_items SET current_stock = :after, avg_cost = :avg"):
            self.inventory[p["id"]].update(current_stock=Decimal(str(p["after"])), avg_cost=Decimal(str(p["avg"])))
            return Result()
        if sql.startswith("INSERT INTO inventory_movements"):
            self.movements.append(p)
            return Result()
        if sql.startswith("UPDATE expenses SET inventory_applied = true"):
            self.expenses[p["e"]]["inventory_applied"] = True
            return Result()
        if sql.startswith("UPDATE expenses SET status = 'aprobado'"):
            row = self.expenses[p["id"]]
            if row["status"] != "pendiente":
                return Result(rowcount=0)
            row.update(status="aprobado", approved_by_name=p["n"])
            return Result()
        if sql.startswith("UPDATE expenses SET status = 'rechazado'"):
            self.expenses[p["id"]].update(status="rechazado", rejected_reason=p["r"])
            return Result()
        if sql.startswith("SELECT * FROM expenses WHERE company_id = CAST(:c AS uuid) AND payment_method = 'credito'"):
            return Result([dict(e) for e in self.expenses.values() if e["payment_method"] == "credito" and not e["paid_at"] and e["status"] != "rechazado"])
        if sql.startswith("SELECT COALESCE(SUM(total), 0) AS total FROM hospitality_orders"):
            total = Decimal("0")
            for o in self.orders:
                meta = o["metadata"]
                closer = (meta.get("closed_by") or {}).get("id")
                sale_by = ((meta.get("cashier_sale") or {}).get("by") or {}).get("id")
                mine = closer == p["u"] or (closer is None and sale_by == p["u"]) or (closer is None and "cashier_sale" not in meta)
                if o["payment_method"] == "cash" and p["s"] <= o["closed_at"] <= p["e"] and mine:
                    total += Decimal(str(o["total"]))
            return Result([{"total": total}])
        if sql.startswith("SELECT COALESCE(SUM(total) FILTER (WHERE category <> 'retiro_dueno'), 0) AS expenses"):
            rel = [e for e in self.expenses.values() if str(e["cashier_session_id"]) == p["sid"] and e["paid_from"] == "cajon" and e["status"] != "rechazado"]
            return Result([{"expenses": sum((Decimal(str(e["total"])) for e in rel if e["category"] != "retiro_dueno"), Decimal("0")),
                            "withdrawals": sum((Decimal(str(e["total"])) for e in rel if e["category"] == "retiro_dueno"), Decimal("0"))}])
        if sql.startswith("SELECT full_name FROM company_users"):
            return Result([{"full_name": "Carla Caja" if str(p["u"]) == str(CAJERO_ID) else "Otro"}])
        if sql.startswith("INSERT INTO cash_counts"):
            if any(c["cashier_session_id"] == p["sid"] for c in self.counts.values()):
                raise RuntimeError("duplicate key uq_cash_count_session")
            self.counts[p["id"]] = {"id": uuid.UUID(p["id"]), "company_id": cid, "cashier_session_id": p["sid"], "cashier_user_id": p["uid"],
                                    "cashier_name": p["cname"], "shift_start": p["ss"], "shift_end": p["se"], "base": p["base"],
                                    "cash_sales": p["sales"], "drawer_expenses": p["exp"], "withdrawals": p["wd"], "expected": p["expected"],
                                    "counted": p["counted"], "difference": p["diff"], "denominations": json.loads(p["den"]),
                                    "observation": p["obs"], "status": p["status"], "blind": p["blind"], "performed_by_name": p["by"],
                                    "performed_by_kind": p["kind"], "created_at": NOW}
            return Result()
        if sql.startswith("SELECT * FROM cash_counts WHERE id = CAST(:id AS uuid) AND company_id"):
            row = self.counts.get(p["id"])
            return Result([row] if row and row["company_id"] == cid else [])
        if sql.startswith("SELECT * FROM cash_counts WHERE id"):
            return Result([self.counts[p["id"]]])
        if sql.startswith("SELECT * FROM cash_counts WHERE company_id = CAST(:c AS uuid) AND cashier_session_id"):
            return Result([c for c in self.counts.values() if c["cashier_session_id"] == p["s"]])
        if sql.startswith("UPDATE cash_counts SET observation"):
            row = self.counts[p["id"]]
            if row["status"] != "pendiente_observacion":
                raise RuntimeError("cash_count_locked")
            row.update(observation=p["o"], status="cerrado")
            return Result()
        if sql.startswith("SELECT * FROM recurring_expenses WHERE company_id = CAST(:c AS uuid) AND active IS TRUE"):
            return Result([dict(r) for r in self.recurring])
        if sql.startswith("UPDATE recurring_expenses SET last_generated_month"):
            row = next(r for r in self.recurring if str(r["id"]) == p["id"])
            if row["last_generated_month"] == p["m"]:
                return Result(rowcount=0)
            row["last_generated_month"] = p["m"]
            return Result()
        if sql.startswith("SELECT e.*, (a.image_bytes IS NOT NULL) AS has_attachment FROM expenses e"):
            return Result([{**e, "has_attachment": False} for e in self.expenses.values() if e["company_id"] == cid])
        raise AssertionError(f"SQL no esperado: {sql[:160]}")


USERS = {
    "dueno": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="company_admin", full_name="Dueño", email="", settings_json={}),
    "admin": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="administrador", full_name="Adm", email="", settings_json={}),
    "cajero": SimpleNamespace(id=CAJERO_ID, company_id=uuid.UUID(ASADERO), role="caja", full_name="Carla Caja", email="",
                              settings_json={"mini_panel": {"type": "caja"}}),
    "mesero": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="mesero", full_name="Pedro", email="", settings_json={}),
    "ttm": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(TTM), role="company_admin", full_name="T", email="", settings_json={}),
}
client = TestClient(app_main.app)


@pytest.fixture
def api(monkeypatch):
    fake = CostosDb()

    async def get_user(_db, token):
        user = USERS.get(token)
        if not user:
            raise HTTPException(status_code=401, detail="Token requerido.")
        return user

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


def call(method, path, token=None, body=None, company=ASADERO):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, f"/api/v1/costos/companies/{company}{path}", json=body, headers=headers)


def cash_order(fake, total, closer=None, hours_ago=1, **meta):
    metadata = dict(meta)
    if closer is not None:
        metadata["closed_by"] = {"id": str(closer)}
    fake.orders.append({"total": total, "payment_method": "cash", "closed_at": NOW - timedelta(hours=hours_ago), "metadata": metadata})


# ------------------------------------------------------------ arqueo ---
def test_hospitality_costos_blind_count_reveals_expected_only_after_counting(api):
    cash_order(api, 500000, closer=CAJERO_ID)
    cash_order(api, 300000, closer=OTRO_CAJERO_ID)  # lo cobro otro cajero: no es de este turno
    cash_order(api, 100000, closer=CAJERO_ID, hours_ago=9)  # antes del turno
    config = call("GET", "/caja/config", "cajero").json()
    assert config["enabled"] is True and "expected" not in json.dumps(config), "a ciegas: nunca muestra lo esperado antes"
    assert call("GET", "/arqueos/pending", "cajero").status_code == 403, "el cajero no ve los arqueos pendientes"
    res = call("POST", "/caja/arqueo", "cajero", {"denominations": {"50000": 13, "20000": 2}})
    assert res.status_code == 200, res.text
    data = res.json()
    # esperado = base 200.000 + ventas 500.000 = 700.000; contado 690.000
    assert data["counted"] == 690000 and data["expected"] == 700000 and data["difference"] == -10000
    assert data["result"] == "faltante" and data["needs_observation"] is True
    stored = next(iter(api.counts.values()))
    assert stored["expected"] == Decimal("700000") and stored["blind"] is True, "lo esperado queda registrado para auditoria"
    again = call("POST", "/caja/arqueo", "cajero", {"counted": 700000})
    assert again.status_code == 409, "el conteo no se puede repetir para cuadrar"


def test_hospitality_costos_observation_is_mandatory_and_then_locked(api):
    data = call("POST", "/caja/arqueo", "cajero", {"counted": 150000}).json()
    assert data["needs_observation"] is True
    empty = call("POST", f"/caja/arqueo/{data['id']}/observation", "cajero", {"observation": "   "})
    assert empty.status_code in (400, 422)
    ok = call("POST", f"/caja/arqueo/{data['id']}/observation", "cajero", {"observation": "Di vueltas de más a la mesa 4"})
    assert ok.status_code == 200 and ok.json()["status"] == "cerrado"
    assert call("POST", f"/caja/arqueo/{data['id']}/observation", "cajero", {"observation": "cambio"}).status_code == 409
    current = call("GET", "/caja/arqueo", "cajero").json()["count"]
    assert current["observation"] == "Di vueltas de más a la mesa 4"


def test_hospitality_costos_cash_expense_from_drawer_lowers_expected(api):
    cash_order(api, 500000, closer=CAJERO_ID)
    gasto = call("POST", "/caja/gastos", "cajero", {"category": "otros", "subtotal": 30000, "description": "Hielo"})
    assert gasto.status_code == 200 and gasto.json()["status"] == "pendiente" and gasto.json()["paid_from"] == "cajon"
    retiro = call("POST", "/expenses", "dueno", {"category": "retiro_dueno", "subtotal": 100000, "payment_method": "efectivo", "paid_from": "cajon"})
    assert retiro.status_code == 200
    data = call("POST", "/caja/arqueo", "cajero", {"counted": 570000}).json()
    # 200.000 + 500.000 - 30.000 (gasto) - 100.000 (retiro) = 570.000
    assert data["drawer_expenses"] == 30000 and data["withdrawals"] == 100000 and data["expected"] == 570000
    assert data["difference"] == 0 and data["needs_observation"] is False and data["status"] == "cerrado"


def test_hospitality_costos_admin_pending_count_sees_expected(api):
    sid = api.session_id
    api.sessions[sid].update(status="finished", ended_at=NOW)

    async def pending(*_a, **_k):
        return None
    # el turno lo cerro el corte diario: el dueño hace el arqueo viendo lo esperado
    original = api.execute

    async def execute(statement, params=None):
        sql = " ".join(str(statement).split())
        if sql.startswith("SELECT s.id, s.user_id, s.started_at, s.ended_at, s.status, s.closed_reason, u.full_name"):
            return Result([{"id": uuid.UUID(sid), **api.sessions[sid], "closed_reason": "corte_diario", "full_name": "Carla Caja"}])
        if sql.startswith("SELECT id, user_id, started_at, ended_at, status FROM mini_panel_work_sessions WHERE id"):
            return Result([{"id": uuid.UUID(sid), **api.sessions[sid]}])
        return await original(statement, params)

    api.execute = execute
    cash_order(api, 300000, closer=CAJERO_ID)
    pend = call("GET", "/arqueos/pending", "dueno").json()["pending"]
    assert pend[0]["expected"] == 500000 and pend[0]["closed_reason"] == "corte_diario"
    no_obs = call("POST", "/arqueos/admin", "dueno", {"session_id": sid, "counted": 480000})
    assert no_obs.status_code == 400 and "observación" in no_obs.text
    ok = call("POST", "/arqueos/admin", "dueno", {"session_id": sid, "counted": 480000, "observation": "Faltaron 20 mil, se habló con Carla"})
    assert ok.status_code == 200 and ok.json()["blind"] is False and ok.json()["difference"] == -20000


# ------------------------------------------------------------ egresos ---
def test_hospitality_costos_purchase_updates_stock_with_weighted_average_in_grams(api):
    res = call("POST", "/expenses", "dueno", {"category": "compras", "supplier_name": "Avícola", "payment_method": "transferencia",
                                             "paid_from": "banco", "lines": [{"inventory_item_id": POLLO, "quantity": 2, "unit_price": 10000}]})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "aprobado" and res.json()["total"] == 20000
    item = api.inventory[POLLO]
    # 2 libras = 907.1847 g a 22.0462 $/g; antes 1.000 g a $20/g
    assert item["current_stock"] == Decimal("1907.1847")
    expected_avg = (Decimal("1000") * 20 + Decimal("907.1847") * (Decimal("20000") / Decimal("907.1847"))) / Decimal("1907.1847")
    assert abs(item["avg_cost"] - expected_avg) < Decimal("0.001")
    assert api.movements and api.movements[0]["qty"] == Decimal("907.1847")


def test_hospitality_costos_approval_threshold_and_inventory_applied_once(api):
    big = call("POST", "/expenses", "admin", {"category": "compras", "payment_method": "transferencia", "paid_from": "banco",
                                             "lines": [{"inventory_item_id": POLLO, "quantity": 100, "unit_price": 9000}]}).json()
    assert big["status"] == "pendiente" and api.inventory[POLLO]["current_stock"] == Decimal("1000"), "pendiente: no mueve inventario"
    assert call("POST", f"/expenses/{big['id']}/approve", "admin").status_code == 403, "por su valor lo aprueba el dueño"
    ok = call("POST", f"/expenses/{big['id']}/approve", "dueno")
    assert ok.status_code == 200 and ok.json()["status"] == "aprobado"
    stock = api.inventory[POLLO]["current_stock"]
    assert stock > Decimal("1000")
    assert call("POST", f"/expenses/{big['id']}/approve", "dueno").status_code == 409
    assert api.inventory[POLLO]["current_stock"] == stock, "se aplica una sola vez"


def test_hospitality_costos_cashier_limits(api):
    assert call("POST", "/expenses", "cajero", {"category": "aseo", "subtotal": 5000, "paid_from": "banco", "payment_method": "transferencia"}).status_code == 403
    assert call("GET", "/expenses", "cajero").status_code == 403
    assert call("GET", "/caja/config", "mesero").status_code == 403


def test_hospitality_costos_credit_purchase_is_a_payable_due_this_week(api):
    due = (date.today() + timedelta(days=3)).isoformat()
    res = call("POST", "/expenses", "dueno", {"category": "aseo", "subtotal": 80000, "iva": 15200, "retention": 2000,
                                             "payment_method": "credito", "paid_from": "credito", "due_date": due})
    assert res.status_code == 200 and res.json()["paid"] is False and res.json()["total"] == 93200
    data = call("GET", "/payables", "dueno").json()
    assert data["payables"][0]["due_this_week"] is True and data["due_this_week_total"] == 93200
    assert call("POST", "/expenses", "dueno", {"category": "aseo", "subtotal": 1, "payment_method": "credito", "paid_from": "credito"}).status_code == 400


def test_hospitality_costos_recurring_expense_is_created_once_per_month(api):
    api.recurring = [{"id": uuid.uuid4(), "company_id": ASADERO, "cost_center_id": None, "category": "arriendo", "supplier_id": None,
                      "supplier_name": "Inmobiliaria", "description": "Arriendo local", "subtotal": Decimal("2500000"), "iva": Decimal("0"),
                      "retention": Decimal("0"), "payment_method": "transferencia", "paid_from": "banco", "day_of_month": 1,
                      "active": True, "last_generated_month": "2026-08"}]
    import asyncio
    created = asyncio.run(endpoint.generate_recurring(api, uuid.UUID(ASADERO), date(2026, 9, 3)))
    again = asyncio.run(endpoint.generate_recurring(api, uuid.UUID(ASADERO), date(2026, 9, 20)))
    assert created == 1 and again == 0
    rent = [e for e in api.expenses.values() if e["category"] == "arriendo"]
    assert len(rent) == 1 and rent[0]["status"] == "pendiente", "2.500.000 pasa el tope: queda para el dueño"


@pytest.mark.parametrize("method,path", [("GET", "/settings"), ("GET", "/expenses"), ("POST", "/expenses"), ("GET", "/payables"),
                                          ("GET", "/arqueos"), ("POST", "/caja/arqueo"), ("GET", "/caja/config"), ("POST", "/caja/gastos"),
                                          ("GET", "/export?start=2026-09-01&end=2026-09-30"), ("GET", "/alerts")])
def test_hospitality_costos_endpoints_require_session_and_module(api, method, path):
    assert call(method, path, body={}).status_code == 401
    other = call(method, path, "ttm", body={})
    assert other.status_code == 403 and "tenant_not_allowed" in other.text
    no_module = call(method, path, "ttm", body={}, company=TTM)
    assert no_module.status_code == 403 and "module_not_enabled_for_tenant" in no_module.text


# ------------------------------------------------------ cobro con sesion ---
@pytest.mark.asyncio
async def test_hospitality_costos_close_table_requires_session_and_records_who_charged(monkeypatch):
    from starlette.requests import Request

    fake = CostosDb()
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/"})
    monkeypatch.setattr("app.web.admin_v2_routes._active_session", AsyncMock(return_value=False))

    async def user_for(_db, token):
        if token != "cajero":
            raise HTTPException(status_code=401, detail="Token requerido.")
        return USERS["cajero"]

    monkeypatch.setattr(deps, "get_current_company_user", user_for)
    with pytest.raises(HTTPException) as exc:
        await hospitality._hsp_closer_049i(fake, uuid.UUID(ASADERO), request, None)
    assert exc.value.status_code == 401
    closer = await hospitality._hsp_closer_049i(fake, uuid.UUID(ASADERO), request, "Bearer cajero")
    assert closer["id"] == str(CAJERO_ID) and closer["name"] == "Carla Caja"
    assert await hospitality._hsp_closer_049i(fake, uuid.UUID(TTM), request, None) is None, "sin Costos: igual que hoy"
    assert await hospitality._hsp_closer_049i(fake, uuid.UUID(ASADERO), None, None) is None, "llamada interna de confianza"


def test_hospitality_costos_migration_only_asadero_and_locked_counts():
    source = (ROOT / "migrations/versions/021x_costos_module.py").read_text(encoding="utf-8")
    spec = importlib.util.spec_from_file_location("mig_021x", ROOT / "migrations/versions/021x_costos_module.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "021w_carta_module"
    assert TTM not in source and 'TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"' in source
    assert "IF OLD.status = 'cerrado' THEN" in source and "NEW.counted <> OLD.counted OR NEW.expected <> OLD.expected" in source
    assert "CONSTRAINT uq_cash_count_session UNIQUE (company_id, cashier_session_id)" in source
