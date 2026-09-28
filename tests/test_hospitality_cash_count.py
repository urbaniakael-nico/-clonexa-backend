"""Arqueo de caja a ciegas en el panel de caja (049M; antes dentro de Costos).
Codigo real de los endpoints /caja-arqueo con una base en memoria, y la
migracion que desmonta Costos sin perder datos."""
from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import datetime, timedelta, timezone
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
from app.api.v1.endpoints import cash_count as endpoint
from app.api.v1.endpoints import hospitality
from app.services import cash_count as engine

ROOT = Path(__file__).resolve().parent.parent
ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"
CAJERO_ID, OTRO_CAJERO_ID = uuid.uuid4(), uuid.uuid4()
NOW = datetime.now(timezone.utc)


def test_hospitality_cash_count_formula_and_denominations():
    assert engine.expected_cash(200000, 500000, 30000, 100000) == Decimal("570000")
    assert engine.count_from_denominations({50000: 13, 20000: 2}) == Decimal("690000")
    with pytest.raises(ValueError):
        engine.count_from_denominations({7000: 1})
    assert engine.difference_label(-1) == "faltante" and engine.difference_label(0) == "cuadrado"
    assert engine.role_kind("caja") == "cashier" and engine.role_kind("company_admin") == "owner"


class Result:
    def __init__(self, rows=None, rowcount=1):
        self.rows, self.rowcount = rows or [], rowcount

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)


class CashDb:
    def __init__(self):
        self.caja_settings = {ASADERO: {"cash_count": True, "cash_count_drawer_base": 200000}, TTM: {}}
        self.sessions = {str(uuid.uuid4()): {"user_id": CAJERO_ID, "started_at": NOW - timedelta(hours=6), "ended_at": None, "status": "active"}}
        self.orders = []
        self.legacy_expenses = []  # egresos del cajon que se registraron con Costos
        self.counts: dict[str, dict] = {}
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    @property
    def session_id(self):
        return next(iter(self.sessions))

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        cid = str(p.get("company_id", p.get("c", "")))
        if sql.startswith("SELECT cm.settings FROM company_modules cm JOIN modules m") and "waiter_ordering" in sql:
            return Result([{"settings": self.caja_settings[cid]}] if cid in self.caja_settings else [])
        if "FROM companies c LEFT JOIN workforce_session_policy p" in sql:
            return Result([{"timezone": "America/Bogota", "cutoff_time": None, "alert_after_hours": None}])
        if sql.startswith("SELECT id, user_id, started_at, ended_at, status FROM mini_panel_work_sessions WHERE company_id = CAST(:company_id AS uuid) AND panel_type = 'caja' AND status IN"):
            rows = [{"id": uuid.UUID(k), **v} for k, v in self.sessions.items() if v["status"] in ("active", "break")
                    and (not p.get("user_id") or str(v["user_id"]) == str(p["user_id"]))]
            return Result(rows[:1])
        if sql.startswith("SELECT to_regclass('public.expenses')"):
            return Result([{"exists": True}])
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
            rel = [e for e in self.legacy_expenses if e["sid"] == p["sid"]]
            return Result([{"expenses": sum((e["total"] for e in rel if e["category"] != "retiro_dueno"), Decimal("0")),
                            "withdrawals": sum((e["total"] for e in rel if e["category"] == "retiro_dueno"), Decimal("0"))}])
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
        if sql.startswith("SELECT * FROM cash_counts WHERE company_id = CAST(:c AS uuid) AND cashier_session_id"):
            return Result([c for c in self.counts.values() if c["cashier_session_id"] == p["s"]])
        if sql.startswith("UPDATE cash_counts SET observation"):
            row = self.counts[p["id"]]
            if row["status"] != "pendiente_observacion":
                raise RuntimeError("cash_count_locked")
            row.update(observation=p["o"], status="cerrado")
            return Result()
        raise AssertionError(f"SQL no esperado: {sql[:160]}")


USERS = {
    "dueno": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="company_admin", full_name="Dueño", email="", settings_json={}),
    "cajero": SimpleNamespace(id=CAJERO_ID, company_id=uuid.UUID(ASADERO), role="caja", full_name="Carla Caja", email="",
                              settings_json={"mini_panel": {"type": "caja"}}),
    "mesero": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="mesero", full_name="Pedro", email="", settings_json={}),
    "ttm": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(TTM), role="company_admin", full_name="T", email="", settings_json={}),
}
client = TestClient(app_main.app)


@pytest.fixture
def api(monkeypatch):
    fake = CashDb()

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
    return client.request(method, f"/api/v1/caja-arqueo/companies/{company}{path}", json=body, headers=headers)


def cash_order(fake, total, closer=None, hours_ago=1):
    metadata = {"closed_by": {"id": str(closer)}} if closer is not None else {}
    fake.orders.append({"total": total, "payment_method": "cash", "closed_at": NOW - timedelta(hours=hours_ago), "metadata": metadata})


def test_hospitality_cash_count_blind_count_from_the_cashier_panel(api):
    cash_order(api, 500000, closer=CAJERO_ID)
    cash_order(api, 300000, closer=OTRO_CAJERO_ID)  # lo cobro otro cajero
    cash_order(api, 100000, closer=CAJERO_ID, hours_ago=9)  # antes del turno
    config = call("GET", "/caja/config", "cajero").json()
    assert config["enabled"] is True and "expected" not in json.dumps(config), "a ciegas"
    assert call("GET", "/arqueos/pending", "cajero").status_code == 403, "el cajero no ve los pendientes"
    data = call("POST", "/caja/arqueo", "cajero", {"denominations": {"50000": 13, "20000": 2}}).json()
    # esperado = base 200.000 + ventas 500.000 = 700.000; contado 690.000
    assert data["counted"] == 690000 and data["expected"] == 700000 and data["difference"] == -10000
    assert data["result"] == "faltante" and data["needs_observation"] is True
    assert call("POST", "/caja/arqueo", "cajero", {"counted": 700000}).status_code == 409, "no se repite para cuadrar"


def test_hospitality_cash_count_observation_is_mandatory_and_then_locked(api):
    data = call("POST", "/caja/arqueo", "cajero", {"counted": 150000}).json()
    assert call("POST", f"/caja/arqueo/{data['id']}/observation", "cajero", {"observation": "   "}).status_code in (400, 422)
    ok = call("POST", f"/caja/arqueo/{data['id']}/observation", "cajero", {"observation": "Di vueltas de más"})
    assert ok.status_code == 200 and ok.json()["status"] == "cerrado"
    assert call("POST", f"/caja/arqueo/{data['id']}/observation", "cajero", {"observation": "x"}).status_code == 409
    assert call("GET", "/caja/arqueo", "cajero").json()["count"]["observation"] == "Di vueltas de más"


def test_hospitality_cash_count_legacy_drawer_expenses_from_costos_still_count(api):
    cash_order(api, 500000, closer=CAJERO_ID)
    api.legacy_expenses += [{"sid": api.session_id, "category": "otros", "total": Decimal("30000")},
                            {"sid": api.session_id, "category": "retiro_dueno", "total": Decimal("100000")}]
    data = call("POST", "/caja/arqueo", "cajero", {"counted": 570000}).json()
    assert data["drawer_expenses"] == 30000 and data["withdrawals"] == 100000 and data["expected"] == 570000
    assert data["difference"] == 0 and data["status"] == "cerrado"


def test_hospitality_cash_count_owner_counts_a_pending_shift_seeing_expected(api):
    sid = api.session_id
    api.sessions[sid].update(status="finished", ended_at=NOW)
    original = api.execute

    async def execute(statement, params=None):
        sql = " ".join(str(statement).split())
        if sql.startswith("SELECT s.id, s.user_id, s.started_at, s.ended_at, s.status, s.closed_reason, u.full_name"):
            return Result([{"id": uuid.UUID(sid), **api.sessions[sid], "closed_reason": "corte_diario", "full_name": "Carla Caja"}])
        if sql.startswith("SELECT id, user_id, started_at, ended_at, status FROM mini_panel_work_sessions WHERE id"):
            return Result([{"id": uuid.UUID(sid), **api.sessions[sid]}])
        if sql.startswith("SELECT * FROM cash_counts WHERE company_id = CAST(:c AS uuid) AND created_at::date"):
            return Result(list(api.counts.values()))
        return await original(statement, params)

    api.execute = execute
    cash_order(api, 300000, closer=CAJERO_ID)
    pend = call("GET", "/arqueos/pending", "dueno").json()["pending"]
    assert pend[0]["expected"] == 500000 and pend[0]["closed_reason"] == "corte_diario"
    assert call("POST", "/arqueos/admin", "dueno", {"session_id": sid, "counted": 480000}).status_code == 400
    ok = call("POST", "/arqueos/admin", "dueno", {"session_id": sid, "counted": 480000, "observation": "Faltaron 20 mil"})
    assert ok.status_code == 200 and ok.json()["blind"] is False and ok.json()["difference"] == -20000
    history = call("GET", "/arqueos", "dueno").json()
    assert history["by_cashier"][0]["shortage"] == 20000


@pytest.mark.parametrize("method,path", [("GET", "/caja/config"), ("GET", "/caja/arqueo"), ("POST", "/caja/arqueo"),
                                          ("GET", "/arqueos"), ("GET", "/arqueos/pending"), ("POST", "/arqueos/admin")])
def test_hospitality_cash_count_endpoints_require_session_and_the_switch(api, method, path):
    assert call(method, path, body={}).status_code == 401
    assert call(method, path, "ttm", body={}).status_code == 403, "nunca de otra empresa"
    assert call(method, path, "mesero", body={}).status_code == 403
    assert call(method, path, "ttm", body={}, company=TTM).status_code == 403, "sin el arqueo activo, la caja de siempre"


@pytest.mark.asyncio
async def test_hospitality_cash_count_close_table_records_who_charged_only_with_the_switch(monkeypatch):
    from starlette.requests import Request

    fake = CashDb()
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/"})
    monkeypatch.setattr("app.web.admin_v2_routes._active_session", AsyncMock(return_value=False))

    async def user_for(_db, token):
        if token != "cajero":
            raise HTTPException(status_code=401, detail="Token requerido.")
        return USERS["cajero"]

    monkeypatch.setattr(deps, "get_current_company_user", user_for)
    with pytest.raises(HTTPException):
        await hospitality._hsp_closer_049i(fake, uuid.UUID(ASADERO), request, None)
    closer = await hospitality._hsp_closer_049i(fake, uuid.UUID(ASADERO), request, "Bearer cajero")
    assert closer["id"] == str(CAJERO_ID)
    assert await hospitality._hsp_closer_049i(fake, uuid.UUID(TTM), request, None) is None, "The Time Machine: igual que hoy"


def test_hospitality_cash_count_costos_dismantle_migration_keeps_every_row():
    path = ROOT / "migrations/versions/022c_fixed_expenses.py"
    spec = importlib.util.spec_from_file_location("mig_022c", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = path.read_text(encoding="utf-8")
    assert len(module.revision) <= 32 and module.down_revision == "022b_inventory_size"
    # compras y retiros no son gastos fijos: se quedan en expenses
    assert "category NOT IN ('compras', 'retiro_dueno')" in source and "status <> 'rechazado'" in source
    assert set(module.CATEGORY_MAP) == {"arriendo", "internet", "aseo", "mantenimiento", "servicios", "seguros", "impuestos", "emergencia", "otros"}
    # ninguna tabla se borra (ni las vacias): se informa cuantas filas tiene cada una
    assert "DROP TABLE" not in source
    assert set(module.LEGACY_TABLES) == {"expenses", "expense_lines", "expense_attachments", "suppliers", "petty_cash_funds",
                                         "petty_cash_moves", "recurring_expenses", "budgets", "cost_centers"}
    assert "cash_counts" not in module.LEGACY_TABLES, "los arqueos siguen en uso"
    assert '"tablas_de_costos_vacias"' in source
    assert "ON CONFLICT (company_id, source, source_ref) WHERE source_ref IS NOT NULL DO NOTHING" in source, "se puede correr dos veces"
    assert '"cash_count": True' in source and "cash_count_drawer_base" in source
