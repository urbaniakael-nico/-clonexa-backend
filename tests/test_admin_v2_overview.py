"""GET /admin-v2/api/overview: pulso de todas las empresas en pocas consultas.

- Exige la sesion de Admin V2 (sin sesion: 303 al login).
- Ventas canceladas/merma no suman; el momento de la venta es closed_at si se
  cobro, si no created_at (regla de sales_ledger); "hoy" es el dia en Bogota.
- Semaforo: operando / riesgo / dormida / inactiva con su motivo.
- Una tabla que no existe no rompe el endpoint.
- Nunca una consulta por empresa; nunca companies.updated_at como señal.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import admin_overview as ov
from app.web import admin_v2_routes as routes

# 23:30 del 30/09 en Bogota = 04:30 UTC del 01/10.
NOW = datetime(2026, 10, 1, 4, 30, tzinfo=timezone.utc)
ASADERO, TTM, VIEJA, APAGADA, SIN_DUENO, CERRADA, SEMANA = (str(uuid.uuid4()) for _ in range(7))


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)


class OverviewDb:
    """Aplica en Python lo que pide cada consulta agregada, con SUS parametros."""

    def __init__(self, missing=()):
        self.missing = set(missing)
        self.queries = []
        self.companies = [
            {"id": ASADERO, "name": "Asadero El Socio", "slug": "asadero", "status": "active", "plan": "starter", "package_name": "Restaurante Pro"},
            {"id": TTM, "name": "The Time Machine", "slug": "ttm", "status": "active", "plan": "bar"},
            {"id": VIEJA, "name": "Vieja", "slug": "vieja", "status": "active", "plan": "starter"},
            {"id": APAGADA, "name": "Apagada", "slug": "apagada", "status": "inactive", "plan": "starter"},
            {"id": SIN_DUENO, "name": "Sin Dueño", "slug": "sin-dueno", "status": "active", "plan": "starter"},
            {"id": CERRADA, "name": "Cerrada", "slug": "cerrada", "status": "inactive", "plan": "starter"},
            {"id": SEMANA, "name": "Semana", "slug": "semana", "status": "active", "plan": "starter"},
            {"id": str(uuid.uuid4()), "name": "Archivada", "slug": "arch", "status": "archived", "plan": "starter"},
        ]
        self.modules = [
            {"company_id": ASADERO, "enabled": True, "settings": {"cashier_redesign": True, "short_links": True, "base": 200000}},
            {"company_id": ASADERO, "enabled": True, "settings": {"delivery_print": True, "x": False}},
            {"company_id": APAGADA, "enabled": True, "settings": {}},
            {"company_id": APAGADA, "enabled": True, "settings": {}},
            {"company_id": TTM, "enabled": False, "settings": {"apagado_pero_true": True}},
        ]
        h = lambda **kw: {"status": "cerrado", "total": 0, "closed_at": None, **kw}  # noqa: E731
        self.orders = [
            # ASADERO: cobrada hoy en Bogota (22:00 del 30/09 = 03:00 UTC del 01/10)
            h(company_id=ASADERO, total=100000, created_at=NOW - timedelta(hours=3), closed_at=NOW - timedelta(hours=1, minutes=30)),
            # abierta hoy (cuenta por created_at)
            h(company_id=ASADERO, status="entregado", total=20000, created_at=NOW - timedelta(minutes=20)),
            # cancelada y merma hoy: NO suman
            h(company_id=ASADERO, status="cancelado", total=999000, created_at=NOW - timedelta(minutes=10)),
            h(company_id=ASADERO, status="Merma", total=500000, created_at=NOW - timedelta(minutes=5)),
            # cobrada a las 18:00 del 29/09 en Bogota: 7 dias si, hoy no
            h(company_id=ASADERO, total=40000, created_at=NOW - timedelta(days=1, hours=5), closed_at=NOW - timedelta(days=1, hours=5)),
            # TTM: creada ayer a las 23:00 Bogota, cobrada hoy 00:30 Bogota -> es venta de HOY
            h(company_id=TTM, total=60000, created_at=NOW - timedelta(hours=29, minutes=30), closed_at=NOW - timedelta(hours=23)),
            # 04:00 UTC del 30/09 = 23:00 Bogota del 29/09 -> AYER en Bogota aunque en UTC sea el 30
            h(company_id=TTM, total=7000, created_at=datetime(2026, 9, 30, 4, 0, tzinfo=timezone.utc),
              closed_at=datetime(2026, 9, 30, 4, 0, tzinfo=timezone.utc)),
            # VIEJA: ultima venta hace 61 dias
            h(company_id=VIEJA, total=5000, created_at=NOW - timedelta(days=61), closed_at=NOW - timedelta(days=61)),
            # SEMANA: activa, vendio hace 3 dias y hoy no
            h(company_id=SEMANA, total=15000, created_at=NOW - timedelta(days=3), closed_at=NOW - timedelta(days=3)),
        ]
        self.mini = {"mini_panel_sales_records": [{"company_id": SIN_DUENO, "created_at": NOW - timedelta(days=2)}],
                     "mini_panel_quotes": []}
        self.sessions = [
            {"company_id": ASADERO, "status": "active", "last_seen_at": NOW - timedelta(minutes=2)},
            {"company_id": ASADERO, "status": "closed", "last_seen_at": NOW - timedelta(days=1)},
            {"company_id": CERRADA, "status": "closed", "last_seen_at": NOW - timedelta(days=3)},
        ]
        self.users = [
            {"company_id": ASADERO, "status": "active", "role": "company_admin"},
            {"company_id": TTM, "status": "active", "role": "owner"},
            {"company_id": VIEJA, "status": "active", "role": "propietario"},
            {"company_id": SEMANA, "status": "active", "role": "dueño"},
            {"company_id": SIN_DUENO, "status": "active", "role": "caja"},
            {"company_id": SIN_DUENO, "status": "inactive", "role": "company_admin"},
        ]

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        self.queries.append(sql)
        if "to_regclass" in sql:
            return Result([{"name": n} for n in p["names"] if n not in self.missing])
        if sql.startswith("SELECT c.id, c.name, c.slug, c.status, c.plan"):
            assert "updated_at" not in sql
            rows = [c for c in self.companies if c["status"].lower() not in ("archived", "deleted")]
            if "package_name" not in sql:
                rows = [{k: v for k, v in c.items() if k != "package_name"} for c in rows]
            return Result(rows)
        if "COUNT(*) FILTER (WHERE enabled IS TRUE)" in sql:
            out = {}
            for m in self.modules:
                out[m["company_id"]] = out.get(m["company_id"], 0) + (1 if m["enabled"] else 0)
            return Result([{"company_id": k, "enabled": v} for k, v in out.items()])
        if "jsonb_each" in sql:
            return Result([{"company_id": m["company_id"], "flag": k} for m in self.modules if m["enabled"]
                           for k, v in m["settings"].items() if v is True])
        if "FROM hospitality_orders" in sql:
            assert "CASE WHEN LOWER(COALESCE(status, '')) = :paid AND closed_at IS NOT NULL THEN closed_at ELSE created_at END" in sql
            out = {}
            for o in self.orders:
                if o["status"].lower() in p["cancelled"]:
                    continue
                moment = o["closed_at"] if o["status"].lower() == p["paid"] and o["closed_at"] else o["created_at"]
                row = out.setdefault(o["company_id"], {"company_id": o["company_id"], "today_total": 0, "orders_today": 0,
                                                       "week_total": 0, "last_sale_at": None})
                if p["day_start"] <= moment < p["day_end"]:
                    row["today_total"] += o["total"]
                    row["orders_today"] += 1
                if p["week_start"] <= moment < p["day_end"]:
                    row["week_total"] += o["total"]
                row["last_sale_at"] = max(filter(None, [row["last_sale_at"], moment]))
            return Result(list(out.values()))
        for table in ("mini_panel_sales_records", "mini_panel_quotes"):
            if f"FROM {table}" in sql:
                assert table not in self.missing
                out = {}
                for r in self.mini[table]:
                    row = out.setdefault(r["company_id"], {"company_id": r["company_id"], "today": 0, "last_at": None})
                    row["today"] += 1 if p["day_start"] <= r["created_at"] < p["day_end"] else 0
                    row["last_at"] = max(filter(None, [row["last_at"], r["created_at"]]))
                return Result(list(out.values()))
        if "FROM clonexa_access_sessions" in sql:
            out = {}
            for r in self.sessions:
                row = out.setdefault(r["company_id"], {"company_id": r["company_id"], "open_sessions": 0, "last_seen": None})
                row["open_sessions"] += 1 if r["status"] == "active" else 0
                row["last_seen"] = max(filter(None, [row["last_seen"], r["last_seen_at"]]))
            return Result(list(out.values()))
        if "FROM company_users" in sql:
            out = {}
            for u in self.users:
                if u["status"] == "active" and u["role"] in p["roles"]:
                    out[u["company_id"]] = out.get(u["company_id"], 0) + 1
            return Result([{"company_id": k, "owners": v} for k, v in out.items()])
        raise AssertionError(f"SQL no esperado: {sql[:120]}")


async def _overview(db=None, **kw):
    db = db or OverviewDb()
    data = await ov.build_overview(db, now=NOW, **kw)
    return data, {c["id"]: c for c in data["companies"]}, db


@pytest.mark.asyncio
async def test_admin_overview_sales_skip_cancelled_and_use_the_charge_moment():
    data, by, _db = await _overview()
    asadero = by[ASADERO]
    assert asadero["sales_today_total"] == 120000 and asadero["orders_today"] == 2, "sin cancelado ni merma"
    assert asadero["sales_7d_total"] == 160000
    assert asadero["plan"] == "Restaurante Pro" and asadero["modules_enabled"] == 2
    assert asadero["flags_on"] == ["cashier_redesign", "delivery_print", "short_links"]
    assert asadero["open_sessions"] == 1
    assert data["totals"]["sales_today_total"] == 180000
    assert "Archivada" not in {c["name"] for c in data["companies"]}


@pytest.mark.asyncio
async def test_admin_overview_today_is_the_bogota_day():
    today, start, end = ov.bogota_day_bounds(NOW)
    assert str(today) == "2026-09-30", "04:30 UTC del 1/10 sigue siendo 30/09 en Bogota"
    assert start == datetime(2026, 9, 30, 5, 0, tzinfo=timezone.utc) and end - start == timedelta(days=1)
    _data, by, _db = await _overview()
    ttm = by[TTM]
    # creada ayer y cobrada hoy = hoy; la de las 23:00 del 29/09 (Bogota) no.
    assert ttm["sales_today_total"] == 60000 and ttm["orders_today"] == 1
    assert ttm["flags_on"] == [], "modulos apagados no cuentan"


@pytest.mark.asyncio
async def test_admin_overview_traffic_light_states():
    data, by, _db = await _overview()
    assert (by[ASADERO]["state"], by[ASADERO]["state_reason"]) == ("operando", "2 venta(s) hoy")
    assert by[TTM]["state"] == "operando"
    assert (by[VIEJA]["state"], by[VIEJA]["state_reason"]) == ("dormida", "Hace 61 días")
    assert (by[APAGADA]["state"], by[APAGADA]["state_reason"]) == ("riesgo", "Inactiva con 2 módulos")
    assert (by[SIN_DUENO]["state"], by[SIN_DUENO]["state_reason"]) == ("riesgo", "Activa sin dueño con acceso")
    assert (by[CERRADA]["state"], by[CERRADA]["state_reason"]) == ("inactiva", "Inactiva sin módulos")
    assert (by[SEMANA]["state"], by[SEMANA]["state_reason"]) == ("sin_operacion_hoy", "Última señal hace 3 días")
    assert by[SEMANA]["sales_today_total"] == 0 and by[SEMANA]["sales_7d_total"] == 15000
    assert data["totals"] == {**data["totals"], "operating_today": 2, "no_operation_today": 1, "dormant": 1, "at_risk": 2,
                              "inactive": 1, "open_sessions": 1}
    # La ultima señal real sale de ventas/mini paneles/sesiones, nunca de updated_at.
    assert by[ASADERO]["last_real_signal_at"] == (NOW - timedelta(minutes=2)).isoformat()
    assert by[CERRADA]["last_real_signal_at"] == (NOW - timedelta(days=3)).isoformat()
    assert by[SIN_DUENO]["mini_panel_last_at"] == (NOW - timedelta(days=2)).isoformat()


def test_admin_overview_other_states():
    base = {"status": "active", "modules_enabled": 3, "owners_with_access": 1, "orders_today": 0, "mini_panel_today": 0}
    assert ov.classify({**base, "_signal": None}, NOW) == ("dormida", "Sin señales reales")
    # Activa que no opero hoy pero si esta semana: "sin_operacion_hoy", nunca "inactiva".
    assert ov.classify({**base, "_signal": NOW - timedelta(days=2)}, NOW) == ("sin_operacion_hoy", "Última señal hace 2 días")
    assert ov.classify({**base, "_signal": NOW - timedelta(days=1)}, NOW) == ("sin_operacion_hoy", "Última señal ayer")
    # "inactiva" queda solo para empresas con status inactivo.
    assert ov.classify({**base, "status": "inactive", "modules_enabled": 0, "_signal": NOW - timedelta(days=2)}, NOW) ==         ("inactiva", "Inactiva sin módulos")
    for signal in (None, NOW - timedelta(days=2), NOW - timedelta(days=30)):
        state, _reason = ov.classify({**base, "_signal": signal}, NOW)
        assert state != "inactiva", "una empresa activa nunca sale inactiva"
    assert ov.classify({**base, "mini_panel_today": 3, "_signal": NOW}, NOW)[0] == "operando"


@pytest.mark.asyncio
async def test_admin_overview_missing_tables_do_not_break_it():
    db = OverviewDb(missing={"mini_panel_sales_records", "mini_panel_quotes", "company_package_assignments"})
    data, by, db = await _overview(db)
    assert by[SIN_DUENO]["mini_panel_today"] == 0 and by[SIN_DUENO]["mini_panel_last_at"] is None
    assert by[ASADERO]["plan"] == "starter", "sin tabla de paquetes, el plan de la empresa"
    assert not any("mini_panel_quotes" in q for q in db.queries)


@pytest.mark.asyncio
async def test_admin_overview_never_queries_per_company():
    db = OverviewDb()
    await _overview(db)
    assert len(db.queries) <= 9, "unas pocas consultas agregadas, no una por empresa"
    assert not any("updated_at" in q for q in db.queries)


# ------------------------------------------------------------ endpoint ---
@pytest.fixture
def api(monkeypatch):
    fake = OverviewDb()

    async def fake_db():
        yield fake

    app_main.app.dependency_overrides[get_db] = fake_db
    yield monkeypatch
    app_main.app.dependency_overrides.pop(get_db, None)


def test_admin_overview_requires_the_admin_v2_session(api):
    client = TestClient(app_main.app)
    api.setattr(routes, "_active_session", AsyncMock(return_value=False))
    denied = client.get("/admin-v2/api/overview", follow_redirects=False)
    assert denied.status_code in (401, 303)
    if denied.status_code == 303:
        assert denied.headers["location"] == "/admin-v2/login"


def test_admin_overview_endpoint_returns_no_store_json(api):
    client = TestClient(app_main.app)
    api.setattr(routes, "_active_session", AsyncMock(return_value=True))
    api.setenv(routes.PASSWORD_BCRYPT_ENV, "$2b$12$abcdefghijklmnopqrstuuq5B6c1l0Qqf5r8h5bYp3x0V5Xn8Xo2")
    response = client.get("/admin-v2/api/overview")
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    body = response.json()
    assert body["master_access_mode"] == "bcrypt"
    assert {"operating_today", "no_operation_today", "dormant", "at_risk", "inactive", "sales_today_total", "open_sessions",
            "generated_at"} <= set(body["totals"])
    company = body["companies"][0]
    for key in ("id", "name", "slug", "status", "plan", "modules_enabled", "flags_on", "sales_today_total", "orders_today",
                "sales_7d_total", "last_sale_at", "open_sessions", "last_real_signal_at", "state", "state_reason"):
        assert key in company, key
