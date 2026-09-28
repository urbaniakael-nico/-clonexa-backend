"""Nomina por dias de corte (049L), hoy solo VELVET: del 26 al 10 y del 11 al
25, corte automatico a las 00:01 del 11 y del 26, cada turno en el periodo
en el que EMPEZO. Otra empresa (sin fila en payroll_period_config) no cambia.
Codigo real de payroll.py con una base en memoria."""
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
from app.api.v1.endpoints import payroll
from app.services import payroll_colombia as co_engine
from app.services import payroll_periods as periods

ROOT = Path(__file__).resolve().parent.parent
VELVET = "d63cf68c-be5b-4a30-aee4-341973018db1"
OTHER = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"  # The Time Machine: sin dias de corte
EMP = {VELVET: str(uuid.uuid4()), OTHER: str(uuid.uuid4())}
BOGOTA = timezone(timedelta(hours=-5))
CUTOFFS = [10, 25]


def local(day: str, hh: int, mm: int = 0, ss: int = 0) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hh, minute=mm, second=ss, tzinfo=BOGOTA)


# ------------------------------------------------------------ periodos ---
def test_hospitality_payroll_cutoffs_proposes_26_sep_to_10_oct_on_28_sep():
    assert periods.period_for(date(2026, 9, 28), CUTOFFS) == (date(2026, 9, 26), date(2026, 10, 10))
    assert periods.period_for(date(2026, 10, 10), CUTOFFS) == (date(2026, 9, 26), date(2026, 10, 10)), "el 10 aun es del periodo"
    assert periods.period_for(date(2026, 10, 11), CUTOFFS) == (date(2026, 10, 11), date(2026, 10, 25))
    assert periods.period_for(date(2026, 10, 25), CUTOFFS) == (date(2026, 10, 11), date(2026, 10, 25))
    assert periods.period_for(date(2026, 10, 26), CUTOFFS) == (date(2026, 10, 26), date(2026, 11, 10))
    info = periods.describe(date(2026, 9, 26), date(2026, 10, 10), date(2026, 9, 28))
    assert info["headline"] == "Periodo del 26 sep al 10 oct · cierra el 10 de octubre"
    assert info["auto_close_label"] == "el corte se procesa solo el 11 de octubre a las 00:01"
    assert periods.closes_label(date(2026, 10, 10), date(2026, 10, 12)) == "cerró el 10 de octubre"


def test_hospitality_payroll_cutoffs_period_across_new_year():
    for day in (date(2026, 12, 26), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 10)):
        assert periods.period_for(day, CUTOFFS) == (date(2026, 12, 26), date(2027, 1, 10)), day
    assert periods.period_for(date(2027, 1, 11), CUTOFFS) == (date(2027, 1, 11), date(2027, 1, 25))
    assert periods.period_for(date(2026, 12, 25), CUTOFFS) == (date(2026, 12, 11), date(2026, 12, 25))
    assert periods.period_label(date(2026, 12, 26), date(2027, 1, 10)) == "Periodo del 26 dic 2026 al 10 ene 2027"
    assert periods.auto_close_at(date(2027, 1, 10)) == datetime(2027, 1, 11, 0, 1)
    assert periods.due_period(datetime(2027, 1, 11, 0, 1), CUTOFFS) == (date(2026, 12, 26), date(2027, 1, 10))
    # el tramo de diciembre: del 11 al 25
    assert periods.due_period(datetime(2026, 12, 26, 0, 1), CUTOFFS) == (date(2026, 12, 11), date(2026, 12, 25))


def test_hospitality_payroll_cutoffs_due_exactly_at_00_01_of_the_11th_and_26th():
    assert periods.due_period(datetime(2026, 10, 11, 0, 0, 59), CUTOFFS) == (date(2026, 9, 11), date(2026, 9, 25)), "a las 00:00 aun no"
    assert periods.due_period(datetime(2026, 10, 11, 0, 1), CUTOFFS) == (date(2026, 9, 26), date(2026, 10, 10))
    assert periods.due_period(datetime(2026, 10, 26, 0, 0, 30), CUTOFFS) == (date(2026, 9, 26), date(2026, 10, 10))
    assert periods.due_period(datetime(2026, 10, 26, 0, 1), CUTOFFS) == (date(2026, 10, 11), date(2026, 10, 25))


def test_hospitality_payroll_cutoffs_validation_and_short_months():
    assert periods.clean_cutoffs(["25", 10, 10]) == [10, 25]
    for bad in ([], [0], [32], [1, 2, 3, 4, 5], ["x"]):
        with pytest.raises(ValueError):
            periods.clean_cutoffs(bad)
    assert periods.period_for(date(2026, 2, 20), [15, 31]) == (date(2026, 2, 16), date(2026, 2, 28)), "31 en febrero = fin de mes"


# ------------------------------------------------------ base en memoria ---
class Result:
    def __init__(self, rows=None, scalar=None):
        self.rows, self._scalar = rows or [], scalar

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def fetchall(self):
        return [SimpleNamespace(_mapping=row) for row in self.rows]


class PayDb:
    """Ana entra el 10/10 a las 10 p.m. y sale el 11/10 a las 3 a.m. (5 h)."""

    def __init__(self, source="attendance"):
        self.config = {VELVET: {"company_id": uuid.UUID(VELVET), "cutoff_days": json.dumps(CUTOFFS), "auto_close": True,
                                "active_from": local("2026-09-28", 12)}}
        self.source = source
        self.closed: dict[tuple, dict] = {}
        self.open_sessions: list[dict] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.sql: list[str] = []

    def events(self, cid, lo, hi):
        if self.source != "attendance":
            return []
        rows = [
            {"id": uuid.uuid4(), "employee_id": EMP[cid], "event_type": "check_in", "event_label": "Entrada",
             "status_after": "working", "occurred_at": local("2026-10-10", 22).astimezone(timezone.utc)},
            {"id": uuid.uuid4(), "employee_id": EMP[cid], "event_type": "check_out", "event_label": "Salida",
             "status_after": "checked_out", "occurred_at": local("2026-10-11", 3).astimezone(timezone.utc)},
        ]
        return [r for r in rows if lo <= r["occurred_at"] <= hi]

    def sessions(self, cid, start_dt, end_dt, as_of):
        if self.source != "mini_panel":
            return []
        row = {"id": uuid.uuid4(), "company_id": cid, "employee_id": uuid.UUID(EMP[cid]), "panel_type": "bar", "status": "finished",
               "started_at": local("2026-10-10", 22).astimezone(timezone.utc), "ended_at": local("2026-10-11", 3).astimezone(timezone.utc),
               "active_seconds": 5 * 3600, "break_seconds": 0, "active_started_at": None, "current_break_started_at": None,
               "closed_reason": "", "employee_name": "Ana", "employee_role": "bartender"}
        # misma regla que el SQL real
        return [row] if row["started_at"] <= end_dt and (row["ended_at"] or as_of) >= start_dt else []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        cid = str(p.get("company_id", ""))
        self.sql.append(sql)
        if sql.startswith(("CREATE", "ALTER", "UPDATE payroll_periods SET", "UPDATE payroll_period_items SET")):
            return Result()
        if sql.startswith("SELECT to_regclass"):
            return Result([{"exists": True}], scalar=True)
        if "FROM payroll_period_config WHERE company_id" in sql:
            return Result([self.config[cid]] if cid in self.config else [])
        if sql.startswith("SELECT company_id FROM payroll_period_config"):
            return Result([{"company_id": c["company_id"]} for c in self.config.values() if c["auto_close"]])
        if "LOWER(m.code) = 'nomina_colombia'" in sql:
            return Result([])
        if "FROM company_modules cm JOIN modules m" in sql:
            return Result([])
        if "FROM employees WHERE company_id = :company_id" in sql:
            return Result([{"id": uuid.UUID(EMP[cid]), "company_id": cid, "full_name": "Ana", "role": "bartender",
                            "hourly_rate_regular": Decimal("10000"), "hourly_rate_extra": Decimal("15000"),
                            "deduction_1": Decimal("0"), "deduction_2": Decimal("0"), "status": "active"}] if cid in EMP else [])
        if "FROM workforce_attendance_events ev" in sql:
            return Result(self.events(cid, p["lookback_dt"], p["end_dt"]) if cid in EMP else [])
        if "FROM mini_panel_work_sessions s" in sql:
            return Result(self.sessions(cid, p["start_dt"], p["end_dt"], p["as_of"]) if cid in EMP else [])
        if sql.startswith("SELECT count(*) FROM mini_panel_work_sessions"):
            return Result(scalar=sum(1 for s in self.open_sessions if s["company_id"] == cid and p["start_dt"] <= s["started_at"] <= p["end_dt"]))
        if sql.startswith("SELECT count(*) FROM workforce_attendance_status"):
            return Result(scalar=0)
        if sql.startswith("SELECT id, source, session_ref, status, reason, real_end_at, declared_end_at FROM workforce_session_closures"):
            return Result([])
        if "FROM companies c LEFT JOIN workforce_session_policy p" in sql:
            return Result([{"timezone": "America/Bogota", "cutoff_time": None, "alert_after_hours": None}])
        if "FROM information_schema.columns" in sql:
            return Result([])
        if sql.startswith("SELECT settings_json FROM company_settings"):
            return Result([])
        if sql.startswith("SELECT id, closed_at FROM payroll_periods"):
            row = self.closed.get((cid, p["period_start"], p["period_end"]))
            return Result([row] if row else [])
        raise AssertionError(f"SQL no esperado: {sql[:140]}")


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def _shift_minutes(snapshot):
    return sum(int(r["regular_minutes"]) + int(r["extra_minutes"]) for r in snapshot["rows"])


# ------------------------------------------- turno que cruza el corte ---
@pytest.mark.parametrize("source", ["attendance", "mini_panel"])
def test_hospitality_payroll_cutoffs_shift_across_cutoff_midnight_stays_whole_in_its_start_period(source):
    db = PayDb(source)
    first = asyncio_run(payroll.calculate_period_snapshot(db, uuid.UUID(VELVET), date(2026, 9, 26), date(2026, 10, 10)))
    second = asyncio_run(payroll.calculate_period_snapshot(db, uuid.UUID(VELVET), date(2026, 10, 11), date(2026, 10, 25)))
    assert _shift_minutes(first) == 300, "las 5 horas completas en el periodo en que empezo (26 sep - 10 oct)"
    assert first["rows"][0]["shifts"][0]["end"].startswith("2026-10-11T08:00"), "incluye hasta la salida de las 3 a.m."
    assert _shift_minutes(second) == 0, "nada del turno pasa al periodo siguiente"


def test_hospitality_payroll_cutoffs_other_company_keeps_assigning_by_shift_end():
    db = PayDb("attendance")
    first = asyncio_run(payroll.calculate_period_snapshot(db, uuid.UUID(OTHER), date(2026, 9, 26), date(2026, 10, 10)))
    second = asyncio_run(payroll.calculate_period_snapshot(db, uuid.UUID(OTHER), date(2026, 10, 11), date(2026, 10, 25)))
    assert _shift_minutes(first) == 0 and _shift_minutes(second) == 300, "como siempre: el turno cuenta donde termina"
    assert not any("end_dt" in s and "+" in s for s in db.sql)


def test_hospitality_payroll_cutoffs_colombia_engine_pays_the_whole_shift_in_its_start_period():
    spec = importlib.util.spec_from_file_location("mig_021t", ROOT / "migrations/versions/021t_nomina_colombia.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resolver = co_engine.ParamResolver({2026: {"params": module.PARAMS_2026, "changes": module.CHANGES_2026}})
    shift = [(datetime(2026, 10, 10, 22), datetime(2026, 10, 11, 3))]
    by_start = co_engine.classify_intervals(shift, resolver, date(2026, 9, 26), date(2026, 10, 10), assign_by_start=True)
    assert sum(by_start["minutes"].values()) == 300 and by_start["worked_days"] == [date(2026, 10, 10)]
    nxt = co_engine.classify_intervals(shift, resolver, date(2026, 10, 11), date(2026, 10, 25), assign_by_start=True)
    assert sum(nxt["minutes"].values()) == 0 and nxt["worked_days"] == []
    legacy = co_engine.classify_intervals(shift, resolver, date(2026, 9, 26), date(2026, 10, 10))
    assert sum(legacy["minutes"].values()) == 120, "sin la opcion, igual que siempre (por dia calendario)"
    # los recargos siguen siendo los del dia real: las horas del domingo 11 son dominicales nocturnas
    assert any(kind.startswith("ord_sun_night") and day == date(2026, 10, 11) for kind, day in by_start["minutes"])


def test_hospitality_payroll_cutoffs_default_period_comes_from_config():
    db = PayDb()
    payroll._local_today_049L = lambda: date(2026, 9, 28)  # noqa: E731  (se restaura abajo)
    try:
        assert asyncio_run(payroll.period_from_payload_049L(db, VELVET, {})) == (date(2026, 9, 26), date(2026, 10, 10))
        assert asyncio_run(payroll.period_from_payload_049L(db, VELVET, {"period_start": "2026-08-01", "period_end": "2026-08-15"})) == (
            date(2026, 8, 1), date(2026, 8, 15)), "se puede consultar un periodo viejo a mano"
        other = asyncio_run(payroll.period_from_payload_049L(db, OTHER, {}))
        assert other == payroll.period_from_payload({}), "otra empresa: el periodo por defecto de siempre"
    finally:
        payroll._local_today_049L = lambda: datetime.now(payroll.BUSINESS_TIMEZONE).date()  # noqa: E731


# ------------------------------------------------------ corte automatico ---
def _run_close(db, now_local, monkeypatch):
    closed = []

    async def fake_close(_db, company_id, start, end, *, name=None, currency="USD"):
        closed.append((str(company_id), start, end, name))
        db.closed[(str(company_id), start, end)] = {"id": uuid.uuid4(), "closed_at": now_local}
        return "p1"

    monkeypatch.setattr(payroll, "close_period_core_049L", fake_close)
    result = asyncio_run(payroll.run_payroll_autoclose_049L(db, now_local.astimezone(timezone.utc)))
    return result, closed


def test_hospitality_payroll_cutoffs_autoclose_runs_at_00_01_of_the_11th(monkeypatch):
    db = PayDb()
    result, closed = _run_close(db, local("2026-10-11", 0, 0, 59), monkeypatch)
    assert closed == [] and result == [], "a las 00:00:59 no corta (el periodo anterior es de antes de activar)"
    result, closed = _run_close(db, local("2026-10-11", 0, 1), monkeypatch)
    assert closed == [(VELVET, date(2026, 9, 26), date(2026, 10, 10), "Nómina del 26 sep al 10 oct (corte automático)")]
    result, closed = _run_close(db, local("2026-10-11", 0, 5), monkeypatch)
    assert closed == [], "una sola vez"
    result, closed = _run_close(db, local("2026-10-26", 0, 1), monkeypatch)
    assert closed == [(VELVET, date(2026, 10, 11), date(2026, 10, 25), "Nómina del 11 oct al 25 oct (corte automático)")]
    result, closed = _run_close(db, local("2027-01-11", 0, 1), monkeypatch)
    assert closed[0][1:3] == (date(2026, 12, 26), date(2027, 1, 10)), "cruza el año"


def test_hospitality_payroll_cutoffs_autoclose_waits_for_a_shift_that_started_before_the_cutoff(monkeypatch):
    db = PayDb()
    db.open_sessions.append({"company_id": VELVET, "started_at": local("2026-10-10", 22).astimezone(timezone.utc)})
    result, closed = _run_close(db, local("2026-10-11", 0, 1), monkeypatch)
    assert closed == [] and result[0]["status"] == "waiting_open_shifts", "no lo parte: espera a que cierre el turno"
    db.open_sessions.clear()  # Ana marco salida a las 3 a.m.
    result, closed = _run_close(db, local("2026-10-11", 3, 1), monkeypatch)
    assert closed[0][1:3] == (date(2026, 9, 26), date(2026, 10, 10))


def test_hospitality_payroll_cutoffs_autoclose_never_touches_other_companies(monkeypatch):
    db = PayDb()
    db.config.clear()
    result, closed = _run_close(db, local("2026-10-11", 0, 1), monkeypatch)
    assert result == [] and closed == []
    # y un periodo de antes de activar los dias de corte no se cierra solo
    db2 = PayDb()
    db2.config[VELVET]["active_from"] = local("2026-10-20", 12)
    _result, closed = _run_close(db2, local("2026-10-21", 9), monkeypatch)
    assert closed == []


# ------------------------------------------------------------- endpoints ---
USERS = {
    "admin": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(VELVET), role="company_admin", full_name="Dueño", email=""),
    "mesero": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(VELVET), role="mesero", full_name="Pedro", email=""),
    "other": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(OTHER), role="company_admin", full_name="T", email=""),
}
client = TestClient(app_main.app)


@pytest.fixture
def api(monkeypatch):
    fake = PayDb()
    updates = []
    original = fake.execute

    async def execute(statement, params=None):
        sql = " ".join(str(statement).split())
        if sql.startswith("UPDATE payroll_period_config"):
            updates.append(params)
            fake.config[params["company_id"]]["cutoff_days"] = params["days"]
            return Result()
        return await original(statement, params)

    fake.execute = execute
    fake.updates = updates

    async def get_user(_db, token):
        if token not in USERS:
            raise HTTPException(status_code=401, detail="Token requerido.")
        return USERS[token]

    async def fake_db():
        yield fake

    monkeypatch.setattr(deps, "get_current_company_user", get_user)
    monkeypatch.setattr(payroll, "active_admin_v2_session", AsyncMock(return_value=False))
    monkeypatch.setattr(payroll, "ensure_payroll_storage", AsyncMock())
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    yield fake
    app_main.app.dependency_overrides.pop(get_db, None)


def call(method, company, token=None, body=None, query=""):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, f"/api/v1/payroll/companies/{company}/period-config{query}", json=body, headers=headers)


def test_hospitality_payroll_cutoffs_config_endpoints_need_a_session(api):
    for method in ("GET", "PUT"):
        assert call(method, VELVET, body={"cutoff_days": [10, 25]}).status_code == 401
        assert call(method, VELVET, "other", body={"cutoff_days": [10, 25]}).status_code == 403, "nunca de otra empresa"
    assert call("PUT", VELVET, "mesero", body={"cutoff_days": [5]}).status_code == 403, "solo el dueño o la administracion"


def test_hospitality_payroll_cutoffs_config_shows_the_period_and_saves_new_days(api):
    data = call("GET", VELVET, "admin", query="?date_ref=2026-09-28").json()
    assert data["enabled"] is True and data["cutoff_days"] == [10, 25]
    assert data["period"]["period_start"] == "2026-09-26" and data["period"]["period_end"] == "2026-10-10"
    assert data["period"]["label"] == "Periodo del 26 sep al 10 oct"
    old = call("GET", VELVET, "admin", query="?date_ref=2026-08-05").json()["period"]
    assert (old["period_start"], old["period_end"]) == ("2026-07-26", "2026-08-10"), "periodos viejos a mano"
    bad = call("PUT", VELVET, "admin", body={"cutoff_days": [40]})
    assert bad.status_code == 400
    ok = call("PUT", VELVET, "admin", body={"cutoff_days": ["15", 30], "auto_close": True})
    assert ok.status_code == 200 and json.loads(api.updates[-1]["days"]) == [15, 30]
    # otra empresa: sin dias de corte, nada cambia y no se puede prender desde el portal
    assert call("GET", OTHER, "other").json() == {"enabled": False}
    assert call("PUT", OTHER, "other", body={"cutoff_days": [10, 25]}).status_code == 409


def test_hospitality_payroll_cutoffs_migration_targets_only_velvet():
    spec = importlib.util.spec_from_file_location("mig_022a", ROOT / "migrations/versions/022a_payroll_cutoffs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "021z_carta_tree"
    assert module.TARGET_COMPANY_ID == VELVET and json.loads(module.CUTOFF_DAYS) == [10, 25]
    source = (ROOT / "migrations/versions/022a_payroll_cutoffs.py").read_text(encoding="utf-8")
    assert source.count("INSERT INTO payroll_period_config") == 1 and OTHER not in source
