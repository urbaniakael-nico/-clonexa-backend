"""GET /admin-v2/api/overview: pulso de todas las empresas por CONEXION.

Decision del dueño (Fase 2): las ventas de los clientes no son un dato del
Centro de mando. La señal de vida es la conexion:
- Sesiones (cualquier scope), company_users.last_login_at y el ultimo registro
  de las tablas operativas (pedidos, mini paneles, produccion, asistencia).
  NUNCA updated_at.
- Semaforo: conectada / activa_hoy / sin_actividad_hoy / dormida / riesgo /
  inactiva, calculado en el servidor con su motivo.
- Totales solo de empresas registradas; las demos van aparte en health.
- Una tabla (o columna) que no existe no rompe el endpoint.
- Exige la sesion de Admin V2; nunca una consulta por empresa.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import admin_overview as ov
from app.services import company_kind
from app.web import admin_v2_routes as routes

# 23:30 del 30/09 en Bogota = 04:30 UTC del 01/10.
NOW = datetime(2026, 10, 1, 4, 30, tzinfo=timezone.utc)
ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"  # viva: registrada sin kind guardado
TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"      # viva
PRODUCE, VIEJA, NUNCA, APAGADA, SIN_DUENO, CERRADA, DEMO_VIVA, DEMO_SIN_KIND, ARCHIVADA = (
    str(uuid.uuid4()) for _ in range(9))
ALL_COLUMNS = {
    "hospitality_orders": {"company_id", "created_at", "closed_at", "status", "total"},
    "company_modules": {"company_id", "enabled", "settings"}, "modules": {"id"},
    "company_package_assignments": {"company_id"}, "packages": {"id"},
    "clonexa_access_sessions": {"company_id", "status", "last_seen_at", "created_at", "subject_id", "session_key"},
    "company_users": {"company_id", "status", "role", "last_login_at"},
    **{t: {"company_id", "created_at"} for t in ov.OPERATION_TABLES},
}


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def scalar(self):
        return next(iter(self.rows[0].values())) if self.rows else None


class OverviewDb:
    """Aplica en Python lo que pide cada consulta agregada, con SUS parametros."""

    def __init__(self, missing=(), no_created_at=(), size_fails=False):
        self.missing = set(missing)
        self.no_created_at = set(no_created_at)
        self.size_fails = size_fails
        self.queries = []
        c = lambda id_, name, status="active", **kw: {"id": id_, "name": name, "slug": name.lower().replace(" ", "-"),  # noqa: E731
                                                     "status": status, "plan": "starter", "kind": None,
                                                     "updated_at": NOW, **kw}
        self.companies = [
            c(ASADERO, "Asadero", package_name="Restaurante Pro"),
            c(TTM, "TTM", plan="bar"),
            c(PRODUCE, "Produce", kind="registrada"),
            c(VIEJA, "Vieja", kind="registrada"),
            c(NUNCA, "Nunca", kind="registrada"),
            c(APAGADA, "Apagada", "inactive", kind="registrada"),
            c(SIN_DUENO, "Sin Dueno", kind="registrada"),
            c(CERRADA, "Cerrada", "inactive", kind="registrada"),
            c(DEMO_VIVA, "Demo Viva", kind="demo"),
            c(DEMO_SIN_KIND, "Demo Sin Kind"),
            c(ARCHIVADA, "Archivada", "archived", kind="registrada"),
        ]
        self.modules = [
            {"company_id": ASADERO, "enabled": True, "settings": {"cashier_redesign": True, "short_links": True, "base": 200000}},
            {"company_id": ASADERO, "enabled": True, "settings": {"delivery_print": True, "x": False}},
            {"company_id": APAGADA, "enabled": True, "settings": {}},
            {"company_id": APAGADA, "enabled": True, "settings": {}},
            {"company_id": TTM, "enabled": False, "settings": {"apagado_pero_true": True}},
        ]
        o = lambda **kw: {"status": "cerrado", "total": 0, "closed_at": None, **kw}  # noqa: E731
        self.orders = [
            o(company_id=ASADERO, total=100000, created_at=NOW - timedelta(hours=3), closed_at=NOW - timedelta(hours=1)),
            o(company_id=ASADERO, status="cancelado", total=999000, created_at=NOW - timedelta(minutes=10)),
            # VIEJA vendio hace 61 dias: un pedido viejo es señal vieja, nada mas.
            o(company_id=VIEJA, total=5000, created_at=NOW - timedelta(days=61), closed_at=NOW - timedelta(days=61)),
        ]
        self.ops = {
            # TTM: mini panel hoy (22:30 Bogota), sin ventas hoy
            "mini_panel_sales_records": [{"company_id": TTM, "created_at": NOW - timedelta(hours=1)}],
            # PRODUCE no vende: produce. Cierre de produccion hace 3 dias.
            "reference_production_closures": [{"company_id": PRODUCE, "created_at": NOW - timedelta(days=3)}],
            "workforce_attendance_events": [{"company_id": SIN_DUENO, "created_at": NOW - timedelta(days=2)}],
        }
        self.sessions = [
            {"company_id": ASADERO, "status": "active", "last_seen_at": NOW - timedelta(minutes=2), "created_at": NOW - timedelta(hours=2), "subject_id": "u1", "session_key": "s1"},
            {"company_id": ASADERO, "status": "active", "last_seen_at": NOW - timedelta(minutes=14), "created_at": NOW - timedelta(hours=1), "subject_id": "u2", "session_key": "s2"},
            {"company_id": ASADERO, "status": "active", "last_seen_at": NOW - timedelta(minutes=5), "created_at": NOW - timedelta(minutes=30), "subject_id": "u1", "session_key": "s3"},
            # abierta hace dias y nunca cerrada: no cuenta como abierta, va a "sin actividad"
            {"company_id": ASADERO, "status": "active", "last_seen_at": NOW - timedelta(days=3), "created_at": NOW - timedelta(days=4), "subject_id": "u1", "session_key": "s0"},
            # abierta pero sin moverse hace 40 min: no es "conectada"
            {"company_id": TTM, "status": "active", "last_seen_at": NOW - timedelta(minutes=40), "created_at": NOW - timedelta(days=1), "subject_id": "u3", "session_key": "s4"},
            {"company_id": CERRADA, "status": "closed", "last_seen_at": NOW - timedelta(days=3), "created_at": NOW - timedelta(days=3), "subject_id": "u4", "session_key": "s5"},
            # demo conectada con 3 usuarios: NO cuenta en los totales
            *({"company_id": DEMO_VIVA, "status": "active", "last_seen_at": NOW - timedelta(minutes=1), "created_at": NOW - timedelta(minutes=50),
               "subject_id": f"d{i}", "session_key": f"ds{i}"} for i in range(3)),
        ]
        self.users = [
            {"company_id": ASADERO, "status": "active", "role": "company_admin", "last_login_at": NOW - timedelta(hours=2)},
            {"company_id": TTM, "status": "active", "role": "owner", "last_login_at": None},
            {"company_id": PRODUCE, "status": "active", "role": "dueño", "last_login_at": None},
            {"company_id": VIEJA, "status": "active", "role": "propietario", "last_login_at": NOW - timedelta(days=61, hours=1)},
            {"company_id": NUNCA, "status": "active", "role": "company_admin", "last_login_at": None},
            {"company_id": SIN_DUENO, "status": "active", "role": "caja", "last_login_at": NOW - timedelta(days=1)},
            {"company_id": SIN_DUENO, "status": "inactive", "role": "company_admin", "last_login_at": None},
            {"company_id": DEMO_VIVA, "status": "active", "role": "company_admin", "last_login_at": NOW},
            {"company_id": DEMO_SIN_KIND, "status": "active", "role": "company_admin", "last_login_at": None},
        ]

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        self.queries.append(sql)
        if "information_schema.columns" in sql:
            rows = []
            for name in p["names"]:
                if name in self.missing:
                    continue
                cols = set(ALL_COLUMNS[name])
                if name in self.no_created_at:
                    cols.discard("created_at")
                rows.append({"table_name": name, "cols": sorted(cols)})
            return Result(rows)
        if sql.startswith("SELECT c.id, c.name, c.slug, c.status, c.plan"):
            assert "updated_at" not in sql
            rows = [dict(c) for c in self.companies if c["status"].lower() not in ("archived", "deleted")]
            for r in rows:
                r.pop("updated_at")
                if "package_name" not in sql:
                    r.pop("package_name", None)
            return Result(rows)
        if "COUNT(*) FILTER (WHERE enabled IS TRUE)" in sql:
            out = {}
            for m in self.modules:
                out[m["company_id"]] = out.get(m["company_id"], 0) + (1 if m["enabled"] else 0)
            return Result([{"company_id": k, "enabled": v} for k, v in out.items()])
        if "jsonb_each" in sql:
            return Result([{"company_id": m["company_id"], "flag": k} for m in self.modules if m["enabled"]
                           for k, v in m["settings"].items() if v is True])
        if "FROM clonexa_access_sessions" in sql:
            out = {}
            for s in self.sessions:
                r = out.setdefault(s["company_id"], {"company_id": s["company_id"], "open_sessions": 0, "stale_sessions": 0,
                                                     "live_sessions": 0, "live_users": set(), "logins_today": 0, "last_seen": None})
                live = s["status"] == "active" and s["last_seen_at"] >= p["live_since"]
                r["open_sessions"] += s["status"] == "active" and s["last_seen_at"] >= p["recent_since"]
                r["stale_sessions"] += s["status"] == "active" and s["last_seen_at"] < p["recent_since"]
                r["live_sessions"] += live
                if live:
                    r["live_users"].add(s["subject_id"] or s["session_key"])
                r["logins_today"] += p["day_start"] <= s["created_at"] < p["day_end"]
                r["last_seen"] = max(filter(None, [r["last_seen"], s["last_seen_at"]]))
            return Result([{**r, "live_users": len(r["live_users"])} for r in out.values()])
        if "FROM company_users" in sql:
            out = {}
            for u in self.users:
                r = out.setdefault(u["company_id"], {"company_id": u["company_id"], "owners": 0, "last_login": None})
                r["owners"] += u["status"] == "active" and u["role"] in p["roles"]
                if "MAX(last_login_at)" in sql and u["last_login_at"]:
                    r["last_login"] = max(filter(None, [r["last_login"], u["last_login_at"]]))
            return Result(list(out.values()))
        if " ops GROUP BY company_id" in sql:
            tables = re.findall(r"FROM (\w+) GROUP BY company_id", sql)
            for t in tables:
                assert t not in self.missing and t not in self.no_created_at, t
            out = {}
            for t in tables:
                for r in self.ops.get(t, []):
                    out[r["company_id"]] = max(filter(None, [out.get(r["company_id"]), r["created_at"]]))
            return Result([{"company_id": k, "last_at": v} for k, v in out.items()])
        if "FROM hospitality_orders" in sql:
            out = {}
            for o in self.orders:
                if o["status"].lower() in p["cancelled"]:
                    continue
                moment = o["closed_at"] if o["status"].lower() == p["paid"] and o["closed_at"] else o["created_at"]
                r = out.setdefault(o["company_id"], {"company_id": o["company_id"], "today_total": 0, "orders_today": 0,
                                                     "week_total": 0, "last_sale_at": None, "last_order_at": None})
                if p["day_start"] <= moment < p["day_end"]:
                    r["today_total"] += o["total"]
                    r["orders_today"] += 1
                if p["week_start"] <= moment < p["day_end"]:
                    r["week_total"] += o["total"]
                r["last_sale_at"] = max(filter(None, [r["last_sale_at"], moment]))
                r["last_order_at"] = max(filter(None, [r["last_order_at"], o["created_at"]]))
            return Result(list(out.values()))
        if "pg_database_size" in sql:
            if self.size_fails:
                raise RuntimeError("permiso denegado")
            return Result([{"bytes": 420 * 1024 * 1024}])
        raise AssertionError(f"SQL no esperado: {sql[:120]}")


async def _overview(db=None, **kw):
    db = db or OverviewDb()
    data = await ov.build_overview(db, now=NOW, **kw)
    return data, {c["id"]: c for c in data["companies"]}, db


# ------------------------------------------------------------ semaforo ---
@pytest.mark.asyncio
async def test_each_traffic_light_state_with_its_reason():
    _data, by, _db = await _overview()
    assert (by[ASADERO]["state"], by[ASADERO]["state_reason"]) == ("conectada", "2 usuarios conectados ahora")
    assert (by[TTM]["state"], by[TTM]["state_reason"]) == ("activa_hoy", "Última señal hoy a las 22:50")
    assert (by[PRODUCE]["state"], by[PRODUCE]["state_reason"]) == ("sin_actividad_hoy", "Última señal hace 3 días")
    assert (by[VIEJA]["state"], by[VIEJA]["state_reason"]) == ("dormida", "Hace 61 días")
    assert (by[NUNCA]["state"], by[NUNCA]["state_reason"]) == ("dormida", "Sin señales reales")
    assert (by[APAGADA]["state"], by[APAGADA]["state_reason"]) == ("riesgo", "Inactiva con 2 módulos")
    assert (by[SIN_DUENO]["state"], by[SIN_DUENO]["state_reason"]) == ("riesgo", "Activa sin dueño con acceso")
    assert (by[CERRADA]["state"], by[CERRADA]["state_reason"]) == ("inactiva", "Inactiva sin módulos")
    assert ARCHIVADA not in by


def test_classify_boundaries():
    base = {"status": "active", "modules_enabled": 3, "owners_with_access": 1, "connected_sessions": 0, "users_connected": 0}
    assert ov.classify({**base, "connected_sessions": 1, "users_connected": 1, "_signal": NOW}, NOW) == \
        ("conectada", "1 usuario conectado ahora")
    # 00:10 de hoy en Bogota = activa_hoy; 23:50 de ayer = sin_actividad_hoy.
    assert ov.classify({**base, "_signal": datetime(2026, 9, 30, 5, 10, tzinfo=timezone.utc)}, NOW)[0] == "activa_hoy"
    assert ov.classify({**base, "_signal": datetime(2026, 9, 30, 4, 50, tzinfo=timezone.utc)}, NOW) == \
        ("sin_actividad_hoy", "Última señal ayer")
    assert ov.classify({**base, "_signal": NOW - timedelta(days=7)}, NOW)[0] == "sin_actividad_hoy"
    assert ov.classify({**base, "_signal": NOW - timedelta(days=7, minutes=1)}, NOW)[0] == "dormida"
    assert ov.classify({**base, "_signal": None}, NOW) == ("dormida", "Sin señales reales")
    # riesgo manda sobre la conexion; inactiva solo con status inactivo y sin modulos.
    assert ov.classify({**base, "owners_with_access": 0, "connected_sessions": 2, "_signal": NOW}, NOW)[0] == "riesgo"
    assert ov.classify({**base, "status": "inactive", "modules_enabled": 0, "connected_sessions": 1, "_signal": NOW}, NOW)[0] == "inactiva"
    for signal in (None, NOW, NOW - timedelta(days=2), NOW - timedelta(days=30)):
        assert ov.classify({**base, "_signal": signal}, NOW)[0] != "inactiva", "una empresa activa nunca sale inactiva"


@pytest.mark.asyncio
async def test_signal_is_connection_and_operation_never_sales_or_updated_at():
    _data, by, db = await _overview()
    # PRODUCE no tiene ni una venta y aun asi no esta dormida: produce.
    assert by[PRODUCE]["sales_today_total"] == 0 and by[PRODUCE]["last_sale_at"] is None
    assert by[PRODUCE]["last_real_signal_at"] == (NOW - timedelta(days=3)).isoformat()
    assert by[ASADERO]["last_real_signal_at"] == (NOW - timedelta(minutes=2)).isoformat()
    assert by[ASADERO]["last_login_at"] == (NOW - timedelta(hours=2)).isoformat()
    assert by[CERRADA]["last_real_signal_at"] == (NOW - timedelta(days=3)).isoformat(), "sesion cerrada tambien es señal"
    assert by[NUNCA]["last_real_signal_at"] is None, "updated_at existe pero NUNCA cuenta"
    assert not any("updated_at" in q for q in db.queries)
    # Las ventas siguen por empresa (informativas) pero no deciden nada.
    assert by[ASADERO]["sales_today_total"] == 100000 and by[ASADERO]["orders_today"] == 1


@pytest.mark.asyncio
async def test_totals_count_only_registered_companies():
    data, by, _db = await _overview()
    t = data["totals"]
    assert by[DEMO_VIVA]["kind"] == "demo" and by[DEMO_VIVA]["state"] == "conectada"
    assert by[DEMO_SIN_KIND]["kind"] == "demo", "sin kind guardado y no es viva: demo"
    assert by[ASADERO]["kind"] == "registrada" and by[TTM]["kind"] == "registrada"
    assert t["registered"] == 8 and t["registered_active"] == 6
    assert t["connected_now"] == 1, "la demo conectada no suma"
    assert t["users_connected_now"] == 2, "u1 con dos sesiones cuenta una vez; los 3 de la demo no suman"
    assert t["logins_today"] == 3, "sesiones abiertas hoy (Bogota) en registradas"
    assert t["dormant"] == 2 and t["at_risk"] == 2
    assert t["states"] == {"conectada": 1, "activa_hoy": 1, "sin_actividad_hoy": 1, "dormida": 2, "riesgo": 2, "inactiva": 1}
    for removed in ("sales_today_total", "sales_7d_total", "orders_today", "operating_today"):
        assert removed not in t
    assert data["health"]["demo_companies"] == 2


@pytest.mark.asyncio
async def test_health_block(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "863eaf5326f2e8cef34fbee96c5d180b54ce9dc2")
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "main")
    data, _by, _db = await _overview(master_access_mode="sha256_legacy")
    health = data["health"]
    assert health["database"] == {"used_mb": 420.0, "limit_mb": 500, "used_pct": 84.0, "warn": True}
    assert health["deploy"]["commit"] == "863eaf5326f2" and health["deploy"]["branch"] == "main"
    assert health["master_access_mode"] == "sha256_legacy"


@pytest.mark.asyncio
async def test_health_survives_when_database_size_is_not_readable(monkeypatch):
    for key in ("RAILWAY_GIT_COMMIT_SHA", "SOURCE_COMMIT", "GIT_COMMIT"):
        monkeypatch.delenv(key, raising=False)
    data, _by, _db = await _overview(OverviewDb(size_fails=True))
    assert data["health"]["database"]["used_mb"] is None and data["health"]["deploy"]["commit"] is None


@pytest.mark.asyncio
async def test_missing_tables_or_columns_do_not_break_it():
    db = OverviewDb(missing={"hospitality_orders", "mini_panel_sales_records", "company_package_assignments",
                             "workforce_attendance_events"},
                    no_created_at={"reference_production_closures"})
    data, by, db = await _overview(db)
    assert data["ok"] is True
    assert by[TTM]["operation_last_at"] is None and by[TTM]["state"] == "activa_hoy", "le queda la sesion de hoy"
    assert by[PRODUCE]["last_real_signal_at"] is None and by[PRODUCE]["state"] == "dormida"
    assert by[ASADERO]["plan"] == "starter" and by[ASADERO]["sales_today_total"] == 0
    for table in ("mini_panel_sales_records", "workforce_attendance_events", "reference_production_closures", "hospitality_orders"):
        assert not any(f"FROM {table}" in q for q in db.queries), table


@pytest.mark.asyncio
async def test_everything_missing_still_answers():
    db = OverviewDb(missing=set(ALL_COLUMNS))
    data, by, _db = await _overview(db)
    assert data["ok"] is True and by[ASADERO]["state"] == "riesgo", "sin company_users no hay dueño con acceso"


@pytest.mark.asyncio
async def test_never_queries_per_company():
    db = OverviewDb()
    await _overview(db)
    assert len(db.queries) <= 9, "unas pocas consultas agregadas, no una por empresa"


def test_today_is_the_bogota_day():
    today, start, end = ov.bogota_day_bounds(NOW)
    assert str(today) == "2026-09-30", "04:30 UTC del 1/10 sigue siendo 30/09 en Bogota"
    assert start == datetime(2026, 9, 30, 5, 0, tzinfo=timezone.utc) and end - start == timedelta(days=1)


def test_live_company_ids_match_main():
    assert set(company_kind.LIVE_COMPANY_IDS) == set(app_main._CLONEXA_LIVE_COMPANY_IDS)


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
    assert body["master_access_mode"] == "bcrypt" and body["health"]["master_access_mode"] == "bcrypt"
    assert {"registered_active", "connected_now", "users_connected_now", "logins_today", "dormant", "at_risk",
            "states", "generated_at"} <= set(body["totals"])
    assert "sales_today_total" not in body["totals"]
    company = body["companies"][0]
    for key in ("id", "name", "slug", "status", "plan", "kind", "modules_enabled", "flags_on", "open_sessions",
                "connected_sessions", "users_connected", "last_seen_at", "last_login_at", "operation_last_at",
                "last_real_signal_at", "state", "state_reason"):
        assert key in company, key


@pytest.mark.asyncio
async def test_open_sessions_count_only_last_24h_and_stale_go_apart():
    data, by, _db = await _overview()
    assert by[ASADERO]["open_sessions"] == 3 and by[ASADERO]["stale_sessions"] == 1
    assert by[TTM]["open_sessions"] == 1 and by[TTM]["stale_sessions"] == 0
    assert data["totals"]["open_sessions"] == 4 and data["totals"]["stale_sessions"] == 1
    assert by[ASADERO]["state"] == "conectada", "una sesion vieja no cambia el semaforo"
