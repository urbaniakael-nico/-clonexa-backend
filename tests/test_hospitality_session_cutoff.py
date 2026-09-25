"""Corte diario de sesiones (049D), todas las empresas.

El corte ocurre a la hora de cada empresa, el aviso nombra a la persona de
Workforce, la hora real se ajusta una sola vez y queda bloqueada, el empleado
solo propone, y las horas sin ajustar no se liquidan. Codigo real del corte y
de los endpoints contra una base en memoria.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import payroll, workforce_sessions
from app.services import session_cutoff as cutoff

ROOT = Path(__file__).resolve().parent.parent
BOG = ZoneInfo("America/Bogota")
A = str(uuid.uuid4())   # corte 00:00 (sin fila de politica = por defecto)
B = str(uuid.uuid4())   # corte 06:00 (jornada nocturna)
ANA = str(uuid.uuid4())   # empleada de A
BETO = str(uuid.uuid4())  # empleado de B
CARLA = str(uuid.uuid4())  # empleada de A, solo asistencia por bot


def local(day: str, hh: int, mm: int = 0) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=BOG).astimezone(timezone.utc)


class Result:
    def __init__(self, rows=None, scalar=None, rowcount=1):
        self.rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def fetchall(self):
        return [SimpleNamespace(_mapping=row) for row in self.rows]


class CutDb:
    def __init__(self):
        self.policy = {B: {"cutoff_time": "06:00", "alert_after_hours": Decimal("12")}}
        self.employees = {ANA: {"company_id": A, "full_name": "Ana Workforce", "role": "mesero"},
                          BETO: {"company_id": B, "full_name": "Beto Barra", "role": "barman"},
                          CARLA: {"company_id": A, "full_name": "Carla Campo", "role": "asesora"}}
        self.users = {}
        self.sessions: dict[str, dict] = {}
        self.attendance_status: dict[tuple, dict] = {}
        self.events: list[dict] = []
        self.closures: dict[str, dict] = {}
        self.access = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    def add_session(self, company, employee, started, status="active", user_name="login-mesero-1", **extra):
        sid = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        self.users[user_id] = user_name
        self.sessions[sid] = {"id": uuid.UUID(sid), "company_id": company, "user_id": user_id, "employee_id": employee,
                              "panel_type": "mesero", "status": status, "started_at": started, "ended_at": None,
                              "active_seconds": 0, "break_seconds": 0, "active_started_at": started if status == "active" else None,
                              "current_break_started_at": started if status == "break" else None, "closed_reason": "", **extra}
        return sid

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        cid = str(p.get("company_id", ""))
        if "FROM companies c LEFT JOIN workforce_session_policy p" in sql:
            pol = self.policy.get(cid, {})
            return Result([{"timezone": "America/Bogota", **pol}])
        if sql.startswith("SELECT s.id, s.employee_id, s.panel_type, s.status, s.started_at"):
            rows = [{**s, "user_name": self.users.get(s["user_id"])} for s in self.sessions.values()
                    if s["company_id"] == cid and s["status"] in ("active", "break") and s["started_at"] < p["cutoff"]]
            return Result(rows)
        if sql.startswith("UPDATE mini_panel_work_sessions SET status = 'finished', ended_at = :cutoff"):
            s = self.sessions[p["id"]]
            if s["company_id"] != cid or s["status"] not in ("active", "break"):
                return Result(rowcount=0)
            s.update(status="finished", ended_at=p["cutoff"], closed_reason="corte_diario",
                     active_seconds=s["active_seconds"] + p["active_delta"], break_seconds=s["break_seconds"] + p["break_delta"])
            return Result(rowcount=1)
        if sql.startswith("SELECT full_name FROM employees WHERE id"):
            e = self.employees.get(p["employee_id"])
            return Result([{"full_name": e["full_name"]}] if e and e["company_id"] == cid else [])
        if sql.startswith("INSERT INTO workforce_session_closures"):
            key = (cid, p["source"], p["session_ref"])
            if any((c["company_id"], c["source"], c["session_ref"]) == key for c in self.closures.values()):
                return Result(rowcount=0)
            new_id = uuid.uuid4()
            self.closures[str(new_id)] = {
                "id": new_id, "company_id": cid, "employee_id": p["employee_id"] or None, "employee_name": p["employee_name"],
                "source": p["source"], "session_ref": p["session_ref"], "panel_type": p["panel_type"], "reason": p["reason"],
                "started_at": p["started_at"], "system_end_at": p["system_end_at"], "status": "pending",
                "declared_end_at": None, "declared_by_name": "", "declared_at": None, "real_end_at": None,
                "confirmed_by_name": "", "confirmed_by_user_id": "", "confirmed_at": None}
            return Result()
        if sql.startswith("INSERT INTO workforce_attendance_events"):
            self.events.append({"id": uuid.uuid4(), "company_id": cid, "employee_id": p["employee_id"], "event_type": "check_out",
                                "payload_json": json.loads(p["payload"]), "occurred_at": p["cutoff"]})
            return Result()
        if sql.startswith("UPDATE workforce_attendance_status"):
            st = self.attendance_status.get((cid, p["employee_id"]))
            if st and st["status"] in ("working", "on_break"):
                st["status"] = "checked_out"
            return Result()
        if sql.startswith("SELECT st.employee_id, st.check_in_at, e.full_name"):
            limit = p.get("cutoff") or p.get("limit")
            rows = [{"employee_id": k[1], "check_in_at": v["check_in_at"], "full_name": self.employees[k[1]]["full_name"]}
                    for k, v in self.attendance_status.items()
                    if k[0] == cid and v["status"] in ("working", "on_break") and v["check_in_at"] < limit]
            return Result(rows)
        if sql.startswith("SELECT id, payload_json FROM workforce_attendance_events"):
            rows = [e for e in self.events if e["company_id"] == cid and e["employee_id"] == p["employee_id"] and e["event_type"] == "check_in"]
            return Result(rows[-1:])
        if "s.closed_reason = 'cierre_automatico'" in sql:
            return Result([])
        if sql.startswith("UPDATE clonexa_access_sessions"):
            closed = [a for a in self.access if a["company_id"] == cid and a["status"] == "active" and a["created_at"] < p["cutoff"]]
            for a in closed:
                a["status"] = "closed"
            return Result(rowcount=len(closed))
        if sql.startswith("INSERT INTO workforce_session_policy (company_id, last_cutoff_at)"):
            self.policy.setdefault(cid, {})["last_cutoff_at"] = p["cutoff"]
            return Result()
        if sql.startswith("INSERT INTO workforce_session_policy (company_id, cutoff_time"):
            self.policy.setdefault(cid, {}).update(cutoff_time=p["cutoff_time"], alert_after_hours=Decimal(str(p["hours"])))
            return Result()
        # ---- endpoints
        if sql.startswith("SELECT * FROM workforce_session_closures WHERE id"):
            c = self.closures.get(p["id"])
            return Result([dict(c)] if c and c["company_id"] == cid else [])
        if sql.startswith("SELECT * FROM workforce_session_closures WHERE company_id = CAST(:company_id AS uuid) AND source"):
            rows = [dict(c) for c in self.closures.values() if c["company_id"] == cid and c["source"] == p["source"] and c["session_ref"] == p["ref"]]
            return Result(rows)
        if sql.startswith("SELECT * FROM workforce_session_closures WHERE company_id = CAST(:company_id AS uuid) AND employee_id"):
            rows = [dict(c) for c in self.closures.values()
                    if c["company_id"] == cid and str(c["employee_id"]) == p["employee_id"] and c["status"] != "confirmed"]
            return Result(rows)
        if sql.startswith("SELECT * FROM workforce_session_closures WHERE company_id = CAST(:company_id AS uuid) AND status <> 'confirmed'"):
            rows = sorted([dict(c) for c in self.closures.values() if c["company_id"] == cid and c["status"] != "confirmed"],
                          key=lambda c: (c["employee_name"], c["system_end_at"]))
            return Result(rows)
        if sql.startswith("UPDATE workforce_session_closures SET status = 'declared'"):
            c = self.closures[p["id"]]
            assert c["status"] != "confirmed"
            c.update(status="declared", declared_end_at=p["end_at"], declared_by_name=p["name"], declared_at=datetime.now(timezone.utc))
            return Result()
        if sql.startswith("UPDATE workforce_session_closures SET status = 'confirmed'"):
            c = self.closures[p["id"]]
            if c["company_id"] != cid or c["status"] == "confirmed":
                return Result(rowcount=0)
            c.update(status="confirmed", real_end_at=p["end_at"], confirmed_by_name=p["name"],
                     confirmed_by_user_id=p["user_id"], confirmed_at=datetime.now(timezone.utc))
            return Result(rowcount=1)
        if sql.startswith("SELECT s.id, s.employee_id, s.panel_type, s.started_at, COALESCE(e.full_name, u.full_name)"):
            rows = [{"id": s["id"], "employee_id": s["employee_id"], "panel_type": s["panel_type"], "started_at": s["started_at"],
                     "name": self.employees.get(s["employee_id"], {}).get("full_name") or self.users.get(s["user_id"])}
                    for s in self.sessions.values()
                    if s["company_id"] == cid and s["status"] in ("active", "break") and s["started_at"] < p["limit"]]
            return Result(rows)
        if sql.startswith("SELECT s.id, s.employee_id, s.panel_type, s.started_at, s.ended_at, s.closed_reason, e.full_name"):
            s = self.sessions.get(p["id"])
            if not s or s["company_id"] != cid or s["status"] != "finished":
                return Result([])
            return Result([{**s, "full_name": self.employees.get(s["employee_id"], {}).get("full_name")}])
        raise AssertionError(f"SQL no esperado: {sql[:140]}")


# ------------------------------------------------------------ corte ---
def test_hospitality_cutoff_instant_is_the_company_local_hour():
    now = local("2026-09-25", 3)
    assert cutoff.last_cutoff_instant(now, time(0, 0), BOG) == local("2026-09-25", 0)
    assert cutoff.last_cutoff_instant(now, time(6, 0), BOG) == local("2026-09-24", 6)
    assert cutoff.last_cutoff_instant(local("2026-09-25", 7), time(6, 0), BOG) == local("2026-09-25", 6)
    with pytest.raises(ValueError):
        cutoff.parse_hhmm("25h")


@pytest.mark.asyncio
async def test_hospitality_cutoff_happens_at_each_company_own_hour():
    db = CutDb()
    ana_session = db.add_session(A, ANA, local("2026-09-24", 8))       # olvido salir
    beto_session = db.add_session(B, BETO, local("2026-09-24", 20))    # turno nocturno de B
    fresh = db.add_session(A, ANA, local("2026-09-25", 0, 30), user_name="otro")  # empezo despues del corte

    at3 = local("2026-09-25", 3)
    result_a = await cutoff.run_company_cutoff(db, A, at3)
    result_b = await cutoff.run_company_cutoff(db, B, at3)
    assert result_a["sessions"] == 1 and result_b["sessions"] == 0, "a las 3 a.m. B (corte 06:00) no se toca"
    assert db.sessions[ana_session]["status"] == "finished"
    assert db.sessions[ana_session]["ended_at"] == local("2026-09-25", 0)
    assert db.sessions[ana_session]["closed_reason"] == "corte_diario"
    assert db.sessions[ana_session]["active_seconds"] == 16 * 3600
    assert db.sessions[fresh]["status"] == "active", "lo que empezo despues del corte sigue abierto"
    assert db.sessions[beto_session]["status"] == "active"

    result_b = await cutoff.run_company_cutoff(db, B, local("2026-09-25", 7))
    assert result_b["sessions"] == 1
    assert db.sessions[beto_session]["ended_at"] == local("2026-09-25", 6)
    # Idempotente: correrlo otra vez no crea cierres nuevos.
    await cutoff.run_company_cutoff(db, A, at3)
    assert len(db.closures) == 2


@pytest.mark.asyncio
async def test_hospitality_cutoff_notice_names_the_workforce_person_and_closes_logins_and_attendance():
    db = CutDb()
    db.add_session(A, ANA, local("2026-09-24", 8), user_name="login-mesero-1")
    db.attendance_status[(A, CARLA)] = {"status": "working", "check_in_at": local("2026-09-24", 7)}
    db.events.append({"id": uuid.uuid4(), "company_id": A, "employee_id": CARLA, "event_type": "check_in",
                      "payload_json": {}, "occurred_at": local("2026-09-24", 7)})
    db.access = [{"company_id": A, "status": "active", "created_at": local("2026-09-24", 7)},
                 {"company_id": A, "status": "active", "created_at": local("2026-09-25", 1)}]
    result = await cutoff.run_company_cutoff(db, A, local("2026-09-25", 3))
    assert result["attendance"] == 1 and result["logins"] == 1
    names = sorted(c["employee_name"] for c in db.closures.values())
    assert names == ["Ana Workforce", "Carla Campo"], "nombre de Workforce, no el del login"
    ana = next(c for c in db.closures.values() if c["employee_name"] == "Ana Workforce")
    assert cutoff.closure_payload(ana, BOG)["message"] == "Ana Workforce fue desconectado por el sistema a las 00:00"
    assert db.attendance_status[(A, CARLA)]["status"] == "checked_out"
    checkout = [e for e in db.events if e["event_type"] == "check_out" and e["employee_id"] == CARLA][0]
    assert checkout["payload_json"]["system_cutoff"] is True and checkout["occurred_at"] == local("2026-09-25", 0)
    assert [a["status"] for a in db.access] == ["closed", "active"]


# -------------------------------------------------------- endpoints ---
client = TestClient(app_main.app)
USERS = {
    "admin-a": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(A), role="company_admin", full_name="Dueña A", email="", settings_json={}),
    "ana": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(A), role="mesero", full_name="login-mesero-1", email="",
                           settings_json={"mini_panel": {"employee_id": ANA}}),
    "carla": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(A), role="asesora", full_name="Carla", email="",
                             settings_json={"mini_panel": {"employee_id": CARLA}}),
    "admin-b": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(B), role="company_admin", full_name="Dueño B", email="", settings_json={}),
}


@pytest.fixture
def api_db(monkeypatch):
    fake = CutDb()

    async def get_user(_db, token):
        user = USERS.get(token)
        if not user:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Token requerido.")
        return user

    async def fake_db():
        yield fake

    monkeypatch.setattr(deps, "get_current_company_user", get_user)
    monkeypatch.setattr(workforce_sessions, "active_admin_v2_session", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    yield fake
    app_main.app.dependency_overrides.pop(get_db, None)


def call(method, company, path, token=None, body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, f"/api/v1/workforce-sessions/companies/{company}{path}", json=body, headers=headers)


async def _cut(db):
    db.add_session(A, ANA, local("2026-09-24", 8))
    db.add_session(A, ANA, local("2026-09-24", 9), panel_type="caja")
    await cutoff.run_company_cutoff(db, A, local("2026-09-25", 3))
    return sorted(db.closures.values(), key=lambda c: c["started_at"])


@pytest.mark.parametrize("method,path", [("GET", "/dashboard"), ("GET", "/closures/mine"), ("POST", "/closures/confirm"),
                                          ("POST", f"/closures/{uuid.uuid4()}/declare"), ("GET", "/policy"), ("PUT", "/policy")])
def test_hospitality_cutoff_endpoints_require_a_session(api_db, method, path):
    assert call(method, A, path, body={}).status_code == 401
    other = call(method, A, path, token="admin-b", body={})
    assert other.status_code == 403 and "tenant_not_allowed" in other.text


@pytest.mark.asyncio
async def test_hospitality_cutoff_dashboard_one_notice_per_person_and_only_for_admins(api_db):
    await _cut(api_db)
    assert call("GET", A, "/dashboard", token="ana").status_code == 403
    data = call("GET", A, "/dashboard", token="admin-a").json()
    assert len(data["people"]) == 1, "dos turnos de Ana = un solo aviso"
    assert data["people"][0]["message"] == "Ana Workforce fue desconectado por el sistema a las 00:00"
    assert len(data["people"][0]["closures"]) == 2


@pytest.mark.asyncio
async def test_hospitality_cutoff_real_end_can_be_set_once_then_locked(api_db):
    first, _second = await _cut(api_db)
    body = {"closure_id": str(first["id"]), "real_end_at": "2026-09-24T17:00"}
    too_late = call("POST", A, "/closures/confirm", token="admin-a", body={**body, "real_end_at": "2026-09-25T02:00"})
    assert too_late.status_code == 400 and "posterior al cierre del sistema" in too_late.text
    ok = call("POST", A, "/closures/confirm", token="admin-a", body=body)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "confirmed" and ok.json()["confirmed_by_name"] == "Dueña A"
    assert api_db.closures[str(first["id"])]["real_end_at"] == local("2026-09-24", 17)
    again = call("POST", A, "/closures/confirm", token="admin-a", body={**body, "real_end_at": "2026-09-24T18:00"})
    assert again.status_code == 409 and "no se puede cambiar" in again.text
    assert api_db.closures[str(first["id"])]["real_end_at"] == local("2026-09-24", 17)
    assert call("POST", A, f"/closures/{first['id']}/declare", token="ana", body={"end_at": "2026-09-24T18:00"}).status_code == 409
    remaining = call("GET", A, "/dashboard", token="admin-a").json()["people"][0]["closures"]
    assert len(remaining) == 1


@pytest.mark.asyncio
async def test_hospitality_cutoff_employee_only_proposes_admin_confirms(api_db):
    first, _second = await _cut(api_db)
    url = f"/closures/{first['id']}/declare"
    assert call("POST", A, url, token="carla", body={"end_at": "2026-09-24T17:00"}).status_code == 403, "no el de otro"
    assert call("POST", A, "/closures/confirm", token="ana", body={"closure_id": str(first["id"]), "real_end_at": "2026-09-24T17:00"}).status_code == 403
    declared = call("POST", A, url, token="ana", body={"end_at": "2026-09-24T16:30"})
    assert declared.status_code == 200
    assert declared.json()["status"] == "declared"
    assert "declarada por el empleado" in declared.json()["declared_by_name"]
    assert api_db.closures[str(first["id"])]["real_end_at"] is None, "la propuesta no fija el pago"
    mine = call("GET", A, "/closures/mine", token="ana").json()["closures"]
    assert {c["status"] for c in mine} == {"declared", "pending"}
    confirmed = call("POST", A, "/closures/confirm", token="admin-a", body={"closure_id": str(first["id"])})
    assert confirmed.status_code == 200 and confirmed.json()["real_end_at"] == local("2026-09-24", 16, 30).isoformat()


@pytest.mark.asyncio
async def test_hospitality_cutoff_historic_long_shift_can_be_adjusted_from_payroll(api_db):
    sid = api_db.add_session(A, ANA, local("2026-09-20", 8), status="finished", ended_at=local("2026-09-22", 8),
                             closed_reason="historico_largo")
    api_db.sessions[sid]["status"] = "finished"
    response = call("POST", A, "/closures/confirm", token="admin-a",
                    body={"source": "mini_panel", "session_ref": sid, "real_end_at": "2026-09-20T17:00"})
    assert response.status_code == 200, response.text
    assert response.json()["reason"] == "historico_largo" and response.json()["status"] == "confirmed"
    foreign = call("POST", A, "/closures/confirm", token="admin-a",
                   body={"source": "mini_panel", "session_ref": str(uuid.uuid4()), "real_end_at": "2026-09-20T17:00"})
    assert foreign.status_code == 404


def test_hospitality_cutoff_policy_is_per_company_and_validated(api_db):
    assert call("GET", A, "/policy", token="admin-a").json()["cutoff_time"] == "00:00"
    assert call("PUT", A, "/policy", token="admin-a", body={"cutoff_time": "99:00"}).status_code == 400
    assert call("PUT", A, "/policy", token="admin-a", body={"cutoff_time": "05:30", "alert_after_hours": 30}).status_code == 400
    saved = call("PUT", A, "/policy", token="admin-a", body={"cutoff_time": "05:30", "alert_after_hours": 10})
    assert saved.status_code == 200 and saved.json()["cutoff_time"] == "05:30"
    assert call("GET", B, "/policy", token="admin-b").json()["cutoff_time"] == "06:00"


def test_hospitality_cutoff_live_alert_for_sessions_open_too_long(api_db, monkeypatch):
    api_db.add_session(A, ANA, datetime.now(timezone.utc) - timedelta(hours=13))
    api_db.add_session(A, CARLA, datetime.now(timezone.utc) - timedelta(hours=2))
    alerts = call("GET", A, "/dashboard", token="admin-a").json()["live_alerts"]
    assert [a["employee_name"] for a in alerts] == ["Ana Workforce"]
    assert alerts[0]["hours_open"] >= 13


# --------------------------------------------------------- nomina ---
def test_hospitality_cutoff_unadjusted_hours_are_not_paid_and_adjusted_are_paid_until_real_end(monkeypatch):
    from test_hospitality_payroll_colombia import PayDb, PLAIN, utc, Result as PayResult

    class Db(PayDb):
        def __init__(self):
            super().__init__()
            self.closures = []

        def sessions(self, cid):
            rows = super().sessions(cid)
            # Olvido salir el miercoles 23/09 a las 8 a.m.; el corte lo cerro a las 00:00 del jueves (16 h).
            rows.append({**rows[0], "id": uuid.UUID(CUT_ID), "started_at": utc("2026-09-23", 8), "ended_at": utc("2026-09-24", 0),
                         "active_seconds": 16 * 3600, "break_seconds": 0, "closed_reason": "corte_diario"})
            return rows

        async def execute(self, statement, params=None):
            sql = " ".join(str(statement).split())
            if sql.startswith("SELECT id, source, session_ref, status, reason, real_end_at, declared_end_at FROM workforce_session_closures"):
                return PayResult(self.closures)
            if "FROM companies c LEFT JOIN workforce_session_policy p" in sql:
                return PayResult([{"timezone": "America/Bogota", "cutoff_time": None, "alert_after_hours": None}])
            return await super().execute(statement, params)

    CUT_ID = str(uuid.uuid4())
    fake = Db()

    async def fake_db():
        yield fake

    monkeypatch.setattr(payroll, "utcnow", lambda: datetime(2026, 9, 25, 12, tzinfo=timezone.utc))
    monkeypatch.setattr(payroll, "active_admin_v2_session", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    try:
        def calc():
            return client.post(f"/api/v1/payroll/companies/{PLAIN}/periods/calculate",
                               json={"period_start": "2026-09-16", "period_end": "2026-09-25"}).json()

        data = calc()
        assert data["rows"][0]["regular_minutes"] == 480, "solo el turno normal de 8 h; las 16 h cortadas no"
        [held] = data["unverified_shifts"]
        assert held["reason"] == "corte_diario" and held["minutes"] == 16 * 60 and held["session_ref"] == CUT_ID

        fake.closures = [{"id": uuid.uuid4(), "source": "mini_panel", "session_ref": CUT_ID, "status": "declared",
                          "reason": "corte_diario", "real_end_at": None, "declared_end_at": utc("2026-09-23", 17)}]
        still = calc()
        assert still["rows"][0]["regular_minutes"] == 480, "la hora declarada por el empleado no se paga"
        assert still["unverified_shifts"][0]["status"] == "declared"

        fake.closures[0].update(status="confirmed", real_end_at=utc("2026-09-23", 17))
        paid = calc()
        # 8 h del martes + 9 h del miercoles (8:00 a 17:00, hora real confirmada) = 17 h, 480 min ordinarios por dia.
        assert paid["rows"][0]["regular_minutes"] + paid["rows"][0]["extra_minutes"] == 17 * 60
        assert "unverified_shifts" not in paid
    finally:
        app_main.app.dependency_overrides.pop(get_db, None)


def test_hospitality_cutoff_migration_locks_confirmed_rows_and_marks_history():
    source = (ROOT / "migrations/versions/021u_session_cutoff.py").read_text(encoding="utf-8")
    spec = importlib.util.spec_from_file_location("mig_021u", ROOT / "migrations/versions/021u_session_cutoff.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "021t_nomina_colombia"
    assert "IF OLD.status = 'confirmed' THEN" in source and "BEFORE UPDATE ON workforce_session_closures" in source
    assert "SET closed_reason = 'historico_largo'" in source and module.HISTORIC_HOURS == 12
    assert "INTERVAL '{HISTORIC_HOURS} hours'" in source
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "start_cutoff_loop()" in main
