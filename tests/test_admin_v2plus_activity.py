"""GET /admin-v2/api/companies/{id}/activity (Ficha · Resumen visual).

Solo lectura, con sesion de Admin V2, y SOLO datos de esa empresa:
ingresos por dia (14 dias, America/Bogota), resumen de sesiones (abiertas en
24 h vs. sin actividad, conectadas ahora) y usuarios por mini panel.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import company_activity as ca
from app.web import admin_v2plus_companies as ep

# 23:30 del 30/09 en Bogota = 04:30 UTC del 01/10.
NOW = datetime(2026, 10, 1, 4, 30, tzinfo=timezone.utc)
CID, OTHER = str(uuid.uuid4()), str(uuid.uuid4())


class Result:
    def __init__(self, rows=None, scalar=None):
        self.rows, self._scalar = rows or [], scalar

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def scalar(self):
        return self._scalar


class FakeDb:
    """Aplica en Python cada consulta y exige que SIEMPRE filtre por la empresa pedida."""

    def __init__(self, missing=()):
        self.missing = set(missing)
        self.queries = []
        s = lambda cid, status, created, seen, subject: {"company_id": cid, "status": status, "created_at": created,  # noqa: E731
                                                         "last_seen_at": seen, "subject_id": subject, "session_key": f"k{created}{subject}"}
        self.sessions = [
            s(CID, "active", NOW - timedelta(minutes=30), NOW - timedelta(minutes=5), "u1"),   # hoy (Bogota), conectada
            s(CID, "active", NOW - timedelta(hours=10), NOW - timedelta(hours=3), "u2"),      # abierta reciente
            s(CID, "active", NOW - timedelta(days=20), NOW - timedelta(days=12), "u1"),       # vieja sin cerrar
            s(CID, "closed", NOW - timedelta(days=13, hours=23), NOW - timedelta(days=13), "u3"),
            s(CID, "closed", datetime(2026, 9, 30, 4, 0, tzinfo=timezone.utc), NOW, "u3"),    # 23:00 del 29/09 en Bogota
            s(OTHER, "active", NOW - timedelta(minutes=1), NOW, "x"),                         # otra empresa: nunca
        ]
        self.users = [
            {"company_id": CID, "status": "active", "settings_json": {"mini_panel": {"enabled": True, "type": "mesero"}}},
            {"company_id": CID, "status": "inactive", "settings_json": {"mini_panel": {"enabled": True, "type": "mesero"}}},
            {"company_id": CID, "status": "active", "settings_json": {"mini_panel": {"enabled": True, "type": "sales"}}},
            {"company_id": CID, "status": "active", "settings_json": {"mini_panel": {"enabled": False, "type": "caja"}}},
            {"company_id": CID, "status": "active", "settings_json": {}},
            {"company_id": OTHER, "status": "active", "settings_json": {"mini_panel": {"enabled": True, "type": "mesero"}}},
        ]

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        self.queries.append((sql, p))
        if "to_regclass" in sql:
            return Result(scalar=p["name"].split(".")[1] not in self.missing)
        assert p.get("cid") == CID and "company_id = CAST(:cid AS uuid)" in sql, "toda consulta filtra por la empresa"
        mine = [x for x in self.sessions if x["company_id"] == p["cid"]]
        if "GROUP BY 1" in sql and "clonexa_access_sessions" in sql:
            out = {}
            for x in mine:
                if x["created_at"] >= p["since"]:
                    day = x["created_at"].astimezone(ca.BOGOTA).date()
                    out[day] = out.get(day, 0) + 1
            return Result([{"day": d, "logins": n} for d, n in out.items()])
        if "FROM clonexa_access_sessions" in sql:
            active = [x for x in mine if x["status"] == "active"]
            live = [x for x in active if x["last_seen_at"] >= p["live"]]
            return Result([{"open": len(active), "open_recent": len([x for x in active if x["last_seen_at"] >= p["recent"]]),
                            "connected": len(live), "users_connected": len({x["subject_id"] for x in live}),
                            "last_seen": max(x["last_seen_at"] for x in mine)}])
        if "FROM company_users" in sql:
            out = {}
            for u in self.users:
                mp = u["settings_json"].get("mini_panel")
                if u["company_id"] != p["cid"] or not isinstance(mp, dict) or mp.get("enabled") is not True:
                    continue
                r = out.setdefault(mp["type"], {"panel_type": mp["type"], "users": 0, "active": 0})
                r["users"] += 1
                r["active"] += u["status"] == "active"
            return Result(list(out.values()))
        raise AssertionError(sql)


@pytest.mark.asyncio
async def test_activity_counts_logins_by_bogota_day_for_14_days():
    data = await ca.company_activity(FakeDb(), CID, now=NOW)
    days = {d["date"]: d["logins"] for d in data["days"]}
    assert len(data["days"]) == 14
    assert data["days"][0]["date"] == "2026-09-17" and data["days"][-1]["date"] == "2026-09-30", "hoy es 30/09 en Bogota"
    assert days["2026-09-30"] == 2 and days["2026-09-29"] == 1, "las 23:00 del 29/09 en Bogota cuentan el 29"
    assert days["2026-09-17"] == 1 and sum(days.values()) == 4, "la de hace 20 dias queda fuera; la de otra empresa nunca"


@pytest.mark.asyncio
async def test_activity_session_summary_separates_recent_from_stale():
    data = await ca.company_activity(FakeDb(), CID, now=NOW)
    assert data["sessions"] == {"open": 3, "open_recent": 2, "stale": 1, "connected_now": 1, "users_connected": 1,
                                "last_seen_at": NOW.isoformat(), "recent_hours": 24}


@pytest.mark.asyncio
async def test_activity_counts_users_per_panel_only_for_that_company():
    data = await ca.company_activity(FakeDb(), CID, now=NOW)
    assert data["panels"] == {"mesero": {"users": 2, "active": 1}, "sales": {"users": 1, "active": 1}}


@pytest.mark.asyncio
async def test_activity_with_missing_tables_is_empty_not_broken():
    data = await ca.company_activity(FakeDb(missing={"clonexa_access_sessions", "company_users"}), CID, now=NOW)
    assert data["ok"] and sum(d["logins"] for d in data["days"]) == 0 and data["panels"] == {}
    assert data["sessions"]["open"] == 0 and data["sessions"]["last_seen_at"] is None


@pytest.fixture
def api(monkeypatch):
    db = FakeDb()

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(db=db, client=TestClient(app_main.app), mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


def test_activity_endpoint_requires_admin_v2_session(api):
    api.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    load = AsyncMock()
    api.mp.setattr(ep, "load_company", load)
    assert api.client.get(f"/admin-v2/api/companies/{CID}/activity").status_code == 401
    load.assert_not_awaited()
    assert api.db.queries == []


def test_activity_endpoint_returns_only_that_company(api, monkeypatch):
    api.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    api.mp.setattr(ep, "load_company", AsyncMock(return_value={"id": CID}))
    body = api.client.get(f"/admin-v2/api/companies/{CID}/activity").json()
    assert body["company_id"] == CID and len(body["days"]) == 14 and "no-store" in api.client.get(
        f"/admin-v2/api/companies/{CID}/activity").headers["cache-control"]
    assert all(q[1].get("cid") == CID for q in api.db.queries if "to_regclass" not in q[0])
    assert api.client.get("/admin-v2/api/companies/no-es-uuid/activity").status_code == 404
