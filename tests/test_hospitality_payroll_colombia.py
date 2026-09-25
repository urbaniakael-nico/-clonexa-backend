"""Nomina con normativa laboral colombiana (049A).

Motor (app/services/payroll_colombia.py) con los parametros 2026 que carga la
migracion 021t -- los mismos datos que quedan en la tabla, no valores del
codigo -- y la integracion con /payroll y /payroll-co contra la app HTTP real
con una base en memoria.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import module_catalog_v1, payroll, payroll_colombia
from app.services import payroll_colombia as engine

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("mig_021t", ROOT / "migrations/versions/021t_nomina_colombia.py")
MIGRATION = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MIGRATION)
PARAMS = {2026: {"params": MIGRATION.PARAMS_2026, "changes": MIGRATION.CHANGES_2026}}
SMMLV = Decimal("1750905")


def resolver():
    return engine.ParamResolver(PARAMS)


def liquidate(intervals, day_from, day_to=None, **kwargs):
    kwargs.setdefault("monthly_salary", SMMLV)
    return engine.liquidate_employee(
        intervals=intervals, resolver=resolver(), pay_from=day_from, pay_to=day_to or day_from, **kwargs,
    )


def at(day: str, hh: int, mm: int = 0) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hh, minute=mm)


def line(result, kind):
    found = [item for item in result["lines"] if item["type"] == kind]
    assert found, f"sin linea {kind}: {[i['type'] for i in result['lines']]}"
    return found


# ------------------------------------------------------------ motor ---
def test_hospitality_payroll_co_8pm_hour_pays_35_percent_night_surcharge():
    # Martes 22/09/2026, 8:00 p.m. a 9:00 p.m.
    result = liquidate([(at("2026-09-22", 20), at("2026-09-22", 21))], date(2026, 9, 22))
    night = line(result, "ord_night")[0]
    base = SMMLV / Decimal(42 * 5)
    assert night["factor"] == 1.35
    assert night["minutes"] == 60
    assert night["amount"] == engine.money(base * Decimal("1.35"))
    assert "nocturno 35%" in night["surcharge"]
    # 6:59 p.m. todavia es diurna; la franja empieza a las 7:00 p.m.
    day_hour = liquidate([(at("2026-09-22", 18), at("2026-09-22", 19))], date(2026, 9, 22))
    assert [i["type"] for i in day_hour["lines"]] == ["ord_day"]


def test_hospitality_payroll_co_hour_value_changes_on_july_15_2026():
    july14 = liquidate([(at("2026-07-14", 10), at("2026-07-14", 11))], date(2026, 7, 14))
    july15 = liquidate([(at("2026-07-15", 10), at("2026-07-15", 11))], date(2026, 7, 15))
    assert line(july14, "ord_day")[0]["base_hour_value"] == engine.money(SMMLV / Decimal(44 * 5))
    assert line(july15, "ord_day")[0]["base_hour_value"] == engine.money(SMMLV / Decimal(42 * 5))
    # En un periodo que cruza la fecha salen dos lineas, una con cada valor.
    both = liquidate(
        [(at("2026-07-14", 10), at("2026-07-14", 11)), (at("2026-07-15", 10), at("2026-07-15", 11))],
        date(2026, 7, 14), date(2026, 7, 15),
    )
    values = sorted(item["base_hour_value"] for item in line(both, "ord_day"))
    assert values == sorted([engine.money(SMMLV / 220), engine.money(SMMLV / 210)])


def test_hospitality_payroll_co_sunday_pays_90_percent_from_july_2026():
    sunday = liquidate([(at("2026-09-20", 10), at("2026-09-20", 11))], date(2026, 9, 20))
    item = line(sunday, "ord_sun_day")[0]
    assert item["factor"] == 1.9
    assert item["amount"] == engine.money(SMMLV / 210 * Decimal("1.9"))
    # Antes del 1 de julio de 2026 el parametro vigente era 80%.
    june = liquidate([(at("2026-06-21", 10), at("2026-06-21", 11))], date(2026, 6, 21))
    assert line(june, "ord_sun_day")[0]["factor"] == 1.8
    # Festivo en dia habil (lunes 12/10/2026, Dia de la Raza) = dominical.
    holiday = liquidate([(at("2026-10-12", 10), at("2026-10-12", 11))], date(2026, 10, 12))
    assert line(holiday, "ord_sun_day")[0]["factor"] == 1.9


def test_hospitality_payroll_co_third_extra_hour_of_the_day_raises_alert_but_is_paid():
    two = liquidate([(at("2026-09-22", 8), at("2026-09-22", 18))], date(2026, 9, 22))
    assert two["extra_minutes"] == 120 and two["alerts"] == []
    three = liquidate([(at("2026-09-22", 8), at("2026-09-22", 19))], date(2026, 9, 22))
    assert three["regular_minutes"] == 480 and three["extra_minutes"] == 180
    assert line(three, "ext_day")[0]["minutes"] == 180  # se liquida lo trabajado
    assert [a["kind"] for a in three["alerts"]] == ["extra_daily"]
    assert "maximo legal 2 h" in three["alerts"][0]["message"]


def test_hospitality_payroll_co_transport_goes_to_bonus_base_not_to_contributions():
    result = liquidate([(at("2026-09-22", 8), at("2026-09-22", 16))], date(2026, 9, 22))
    transport = engine.money(Decimal("249095") / 30)
    assert result["transport_applies"] and result["transport_allowance"] == transport
    assert result["contribution_base"] == result["earned_amount"]
    assert result["benefits_base"] == result["earned_amount"] + transport
    assert result["vacation_base"] == result["earned_amount"]
    health = next(p for p in result["employee_deductions"] if p["label"] == "Salud empleado")
    assert health["base"] == result["earned_amount"]
    assert health["amount"] == engine.money(result["earned_amount"] * Decimal("0.04"))
    bonus = next(p for p in result["provisions"] if p["label"] == "Prima de servicios")
    assert bonus["base"] == result["earned_amount"] + transport
    assert result["gross_amount"] == result["earned_amount"] + transport
    # Por encima de 2 SMMLV no hay auxilio.
    high = liquidate([(at("2026-09-22", 8), at("2026-09-22", 16))], date(2026, 9, 22), monthly_salary=SMMLV * 3)
    assert not high["transport_applies"] and high["transport_allowance"] == 0


def test_hospitality_payroll_co_combinations_extra_night_on_sunday():
    # Domingo 12:00 a 23:00: 7 h dominical diurna, 1 h dominical nocturna, 3 h extra nocturna dominical.
    result = liquidate([(at("2026-09-20", 12), at("2026-09-20", 23))], date(2026, 9, 20))
    minutes = result["minutes_by_type"]
    assert minutes["ord_sun_day"] == 420 and minutes["ord_sun_night"] == 60 and minutes["ext_sun_night"] == 180
    assert line(result, "ord_sun_night")[0]["factor"] == pytest.approx(1 + 0.35 + 0.90)
    assert line(result, "ext_sun_night")[0]["factor"] == pytest.approx(1 + 0.75 + 0.90)
    assert result["alerts"] and result["alerts"][0]["kind"] == "extra_daily"


def test_hospitality_payroll_co_weekly_cap_turns_hours_into_extras():
    # Lunes 21 a sabado 26 de septiembre, 8 h diarias = 48 h > 42 h semanales.
    days = [date(2026, 9, 21) + timedelta(days=i) for i in range(6)]
    intervals = [(at(d.isoformat(), 8), at(d.isoformat(), 16)) for d in days]
    result = liquidate(intervals, days[0], days[-1])
    assert result["regular_minutes"] == 42 * 60 and result["extra_minutes"] == 6 * 60
    assert result["worked_days"] == 6


def test_hospitality_payroll_co_employee_deductions_and_employer_costs():
    result = liquidate([(at("2026-09-22", 8), at("2026-09-22", 16))], date(2026, 9, 22), arl_level=2)
    base = result["contribution_base"]
    employer = {p["label"]: p for p in result["employer_contributions"]}
    assert employer["Pension empleador"]["amount"] == engine.money(base * Decimal("0.12"))
    assert employer["Salud empleador"]["amount"] == engine.money(base * Decimal("0.085"))
    assert employer["ARL nivel 2"]["amount"] == engine.money(base * Decimal("0.01044"))
    assert employer["Caja de compensacion"]["pct"] == 4
    exonerated = liquidate([(at("2026-09-22", 8), at("2026-09-22", 16))], date(2026, 9, 22), exonerated=True)
    ex = {p["label"]: p for p in exonerated["employer_contributions"]}
    assert ex["Salud empleador"]["amount"] == 0 and ex["SENA"]["amount"] == 0 and ex["ICBF"]["amount"] == 0
    # Fondo de Solidaridad desde 4 SMMLV.
    assert all(p["label"] != "Fondo de Solidaridad Pensional" for p in result["employee_deductions"])
    rich = liquidate([(at("2026-09-22", 8), at("2026-09-22", 16))], date(2026, 9, 22), monthly_salary=SMMLV * 5)
    fsp = next(p for p in rich["employee_deductions"] if p["label"] == "Fondo de Solidaridad Pensional")
    assert fsp["pct"] == 1
    provisions = {p["label"]: p["pct"] for p in result["provisions"]}
    assert provisions == {"Cesantias": 8.33, "Intereses de cesantias": 1, "Prima de servicios": 8.33, "Vacaciones": 4.17}
    assert result["net_amount"] == result["gross_amount"] - result["employee_deductions_total"]


def test_hospitality_payroll_co_colombian_holidays_2026():
    holidays = engine.colombian_holidays(2026)
    expected = {"2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03", "2026-05-01", "2026-05-18",
                "2026-06-08", "2026-06-15", "2026-06-29", "2026-07-20", "2026-08-07", "2026-08-17", "2026-10-12",
                "2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25"}
    assert {d.isoformat() for d in holidays} == expected


def test_hospitality_payroll_co_values_come_from_the_table_not_the_code():
    source = (ROOT / "app/services/payroll_colombia.py").read_text(encoding="utf-8")
    for literal in ("1750905", "1.750.905", "249095", "249.095"):
        assert literal not in source
    with pytest.raises(engine.ParamsMissing):
        engine.ParamResolver(PARAMS).for_date(date(2027, 1, 4))
    template = engine.carry_forward(PARAMS[2026], 2027)
    assert template["params"]["weekly_hours"] == 42 and template["params"]["sunday_holiday_pct"] == 90
    assert template["changes"] == [{"from": "2027-07-01", "sunday_holiday_pct": 100}]
    assert engine.validate_year_row(PARAMS[2026]) == []
    assert "falta smmlv" in engine.validate_year_row({"params": {}, "changes": []})


def test_hospitality_payroll_co_missing_salary_is_flagged_not_assumed():
    result = liquidate([(at("2026-09-22", 20), at("2026-09-22", 22))], date(2026, 9, 22), monthly_salary=0, other_deductions=5000)
    assert result["salary_missing"] is True
    assert result["minutes_by_type"]["ord_night"] == 120, "las horas se clasifican igual"
    assert result["earned_amount"] == 0 and result["transport_allowance"] == 0
    assert result["gross_amount"] == 0 and result["net_amount"] == 0 and result["employer_contributions_total"] == 0
    assert liquidate([(at("2026-09-22", 8), at("2026-09-22", 9))], date(2026, 9, 22))["salary_missing"] is False


def test_hospitality_payroll_co_breaks_are_not_paid():
    pieces = engine.subtract_breaks(at("2026-09-22", 8), at("2026-09-22", 17), [(at("2026-09-22", 12), at("2026-09-22", 13))])
    assert pieces == [(at("2026-09-22", 8), at("2026-09-22", 12)), (at("2026-09-22", 13), at("2026-09-22", 17))]
    unplaced = engine.subtract_breaks(at("2026-09-22", 8), at("2026-09-22", 16), [], missing_break_seconds=3600)
    assert sum((b - a).total_seconds() for a, b in unplaced) == 7 * 3600


# -------------------------------------------------------- integracion ---
CO = str(uuid.uuid4())       # con el interruptor encendido
MANUAL = str(uuid.uuid4())   # lo tuvo y lo apago
PLAIN = str(uuid.uuid4())    # nunca lo tuvo: exactamente como hoy
EMP = {CO: str(uuid.uuid4()), MANUAL: str(uuid.uuid4()), PLAIN: str(uuid.uuid4())}
OTHER_EMP = str(uuid.uuid4())
SESSION = {cid: str(uuid.uuid4()) for cid in EMP}


class Result:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or []
        self._scalar = scalar

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def scalar_one_or_none(self):
        return self._scalar

    def fetchall(self):
        return [SimpleNamespace(_mapping=row) for row in self.rows]


def utc(day: str, hh: int, mm: int = 0) -> datetime:
    # Hora de Bogota (UTC-5) -> UTC
    return datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=timezone(timedelta(hours=-5))).astimezone(timezone.utc)


class PayDb:
    def __init__(self):
        self.module_rows = {CO: True, MANUAL: False}
        self.co_modules = {CO: {"nomina_colombia"}, MANUAL: set(), PLAIN: set()}
        self.params = {2026: dict(PARAMS[2026])}
        self.company_cfg: dict[str, dict] = {}
        self.employee_cfg: dict[tuple, dict] = {}
        self.sql: list[str] = []
        self.auto_closed: set[str] = set()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    def employees(self, cid):
        return [{"id": uuid.UUID(EMP[cid]), "company_id": cid, "full_name": "Ana Mesera", "role": "mesero",
                 "hourly_rate_regular": Decimal("10000"), "hourly_rate_extra": Decimal("15000"),
                 "deduction_1": Decimal("0"), "deduction_2": Decimal("0"), "status": "active"}]

    def sessions(self, cid):
        # Martes 22/09/2026 de 2:00 p.m. a 11:00 p.m., 1 h de pausa (5 p.m. a 6 p.m.).
        e = self.employees(cid)[0]
        rows = [{"id": uuid.UUID(SESSION[cid]), "company_id": cid, "user_id": None, "employee_id": e["id"],
                 "panel_type": "mesero", "status": "finished", "location_label": "", "started_at": utc("2026-09-22", 14),
                 "ended_at": utc("2026-09-22", 23), "active_seconds": 8 * 3600, "break_seconds": 3600,
                 "active_started_at": None, "current_break_started_at": None, "created_at": None, "updated_at": None,
                 "employee_name": e["full_name"], "employee_role": e["role"], "hourly_rate_regular": e["hourly_rate_regular"],
                 "hourly_rate_extra": e["hourly_rate_extra"], "deduction_1": 0, "deduction_2": 0, "closed_reason": ""}]
        if cid in self.auto_closed:
            # Olvido marcar salida el miercoles 23/09 a las 8:00 a.m.; el sistema lo cerro al abrir el panel 18 h despues.
            rows.append({**rows[0], "id": uuid.uuid4(), "started_at": utc("2026-09-23", 8), "ended_at": utc("2026-09-24", 2),
                         "active_seconds": 18 * 3600, "break_seconds": 0, "closed_reason": "cierre_automatico"})
        return rows

    def break_events(self, cid):
        payload = {"mini_panel_session_id": SESSION[cid]}
        return [
            {"id": uuid.uuid4(), "employee_id": EMP[cid], "event_type": "break_start", "event_label": "Pausa",
             "status_after": "on_break", "detail": "", "payload_json": payload, "metadata_json": None,
             "occurred_at": utc("2026-09-22", 17)},
            {"id": uuid.uuid4(), "employee_id": EMP[cid], "event_type": "break_end", "event_label": "Retomar",
             "status_after": "active", "detail": "", "payload_json": payload, "metadata_json": None,
             "occurred_at": utc("2026-09-22", 18)},
        ]

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        cid = str(p.get("company_id", ""))
        self.sql.append(sql)
        if sql.startswith(("CREATE", "ALTER", "UPDATE payroll_", "UPDATE company_settings")):
            return Result()
        if "LOWER(m.code) = 'nomina_colombia'" in sql:
            return Result([{"enabled": self.module_rows[cid]}] if cid in self.module_rows else [])
        if "FROM company_modules cm JOIN modules m" in sql and "LOWER(m.code) AS code" in sql:
            return Result([{"code": c} for c in self.co_modules.get(cid, set())])
        if sql.startswith("SELECT year, params, changes FROM payroll_co_params"):
            return Result([{"year": y, **row} for y, row in sorted(self.params.items())])
        if sql.startswith("INSERT INTO payroll_co_params"):
            import json
            self.params[p["year"]] = {"params": json.loads(p["params"]), "changes": json.loads(p["changes"])}
            return Result()
        if sql.startswith("SELECT arl_level, exonerated FROM payroll_co_company"):
            return Result([self.company_cfg[cid]] if cid in self.company_cfg else [])
        if sql.startswith("INSERT INTO payroll_co_company"):
            self.company_cfg[cid] = {"arl_level": p["arl_level"], "exonerated": p["exonerated"]}
            return Result()
        if sql.startswith("SELECT employee_id, monthly_salary, arl_level FROM payroll_co_employee"):
            return Result([{"employee_id": k[1], **v} for k, v in self.employee_cfg.items() if k[0] == cid])
        if sql.startswith("INSERT INTO payroll_co_employee"):
            self.employee_cfg[(cid, p["employee_id"])] = {"monthly_salary": Decimal(p["monthly_salary"]), "arl_level": p["arl_level"]}
            return Result()
        if sql.startswith("SELECT id, full_name, role FROM employees"):
            return Result(self.employees(cid) if cid in EMP else [])
        if "FROM employees WHERE company_id = :company_id" in sql:
            return Result(self.employees(cid) if cid in EMP else [])
        if "FROM workforce_attendance_events ev" in sql:
            return Result(self.break_events(cid) if cid in EMP else [])
        if sql.startswith("SELECT id, source, session_ref, status, reason, real_end_at, declared_end_at FROM workforce_session_closures"):
            return Result([])
        if "FROM companies c LEFT JOIN workforce_session_policy p" in sql:
            return Result([{"timezone": "America/Bogota", "cutoff_time": None, "alert_after_hours": None}])
        if sql.startswith("SELECT to_regclass"):
            return Result([{"exists": True}])
        if "FROM mini_panel_work_sessions s" in sql:
            return Result(self.sessions(cid) if cid in EMP else [])
        if "FROM information_schema.columns" in sql:
            return Result([])
        if sql.startswith("SELECT settings_json FROM company_settings"):
            return Result([])
        if sql.startswith("SELECT id FROM payroll_periods"):
            return Result(scalar=None)
        raise AssertionError(f"SQL no esperado: {sql[:140]}")


client = TestClient(app_main.app)
USERS = {
    "admin-co": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(CO), role="company_admin", full_name="Dueño", email="", status="active"),
    "mesero-co": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(CO), role="operador", full_name="Pedro", email="", status="active"),
    "admin-manual": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(MANUAL), role="company_admin", full_name="Otro", email="", status="active"),
    "admin-plain": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(PLAIN), role="company_admin", full_name="Plano", email="", status="active"),
}


@pytest.fixture
def db(monkeypatch):
    fake = PayDb()
    admin_v2 = AsyncMock(return_value=False)

    async def get_user(_db, token):
        user = USERS.get(token)
        if not user:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Token requerido.")
        return user

    async def fake_db():
        yield fake

    monkeypatch.setattr(deps, "get_current_company_user", get_user)
    monkeypatch.setattr(payroll_colombia, "active_admin_v2_session", admin_v2)
    monkeypatch.setattr(payroll, "active_admin_v2_session", admin_v2)
    monkeypatch.setattr(payroll, "utcnow", lambda: datetime(2026, 9, 25, 12, tzinfo=timezone.utc))
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    fake.admin_v2 = admin_v2
    yield fake
    app_main.app.dependency_overrides.pop(get_db, None)


def calculate(company, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(f"/api/v1/payroll/companies/{company}/periods/calculate",
                       json={"period_start": "2026-09-16", "period_end": "2026-09-25"}, headers=headers)


def test_hospitality_payroll_co_switch_off_calculates_exactly_as_today(db):
    response = calculate(PLAIN)  # sin token: hoy este endpoint no lo exige para esta empresa
    assert response.status_code == 200, response.text
    data = response.json()
    assert "legal_mode" not in data
    row = data["rows"][0]
    # 9 h de turno - 1 h de pausa = 8 h ordinarias a la tarifa manual del empleado, sin recargos.
    assert row["regular_minutes"] == 480 and row["extra_minutes"] == 0
    assert row["gross_amount"] == 80000.0 and row["net_amount"] == 80000.0
    assert "colombia" not in row
    assert not any("payroll_co_" in sql for sql in db.sql), "sin el modulo no se leen tablas nuevas"


def test_hospitality_payroll_co_switch_turned_off_is_the_simple_calculation_without_notices(db):
    plain = calculate(PLAIN).json()
    manual = calculate(MANUAL, token="admin-manual").json()
    assert manual["rows"] == [{**plain["rows"][0], "employee_id": manual["rows"][0]["employee_id"],
                               "shifts": manual["rows"][0]["shifts"]}]
    assert manual["totals"] == plain["totals"]
    assert "legal_mode" not in manual, "apagado no hay aviso de recargos"
    assert not hasattr(payroll, "CO_MANUAL_NOTICE_049A")


def test_hospitality_payroll_co_switch_on_liquidates_with_colombian_law(db):
    db.employee_cfg[(CO, EMP[CO])] = {"monthly_salary": SMMLV, "arl_level": None}
    response = calculate(CO, token="admin-co")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["legal_mode"]["state"] == "colombia"
    assert "no reemplaza la revisión de un contador" in data["legal_mode"]["notice"]
    row = data["rows"][0]
    detail = row["colombia"]
    # 2 p.m.-5 p.m. y 6 p.m.-7 p.m. diurnas (4 h); 7 p.m.-11 p.m. nocturnas (4 h). Pausa sin pagar.
    assert detail["minutes_by_type"]["ord_day"] == 240
    assert detail["minutes_by_type"]["ord_night"] == 240
    assert detail["monthly_salary"] == float(SMMLV) and detail["salary_missing"] is False
    assert data["missing_rate_employees"] == [] and data["unverified_shifts"] == []
    assert detail["transport_allowance"] == float(engine.money(Decimal("249095") / 30))
    hour = SMMLV / 210
    assert detail["earned_amount"] == float(engine.money(hour * 4) + engine.money(hour * 4 * Decimal("1.35")))
    assert data["totals"]["employer_contributions_total"] > 0


def test_hospitality_payroll_co_employee_without_salary_is_listed_and_not_paid(db):
    data = calculate(CO, token="admin-co").json()
    row = data["rows"][0]
    assert row["colombia"]["salary_missing"] is True and row["net_amount"] == 0
    assert row["colombia"]["minutes_by_type"]["ord_night"] == 240
    assert data["missing_rate_employees"] == [
        {"employee_id": EMP[CO], "employee_name": "Ana Mesera", "employee_role": "mesero", "minutes": 480}]


def test_hospitality_payroll_co_auto_closed_shift_is_set_apart_in_both_modes(db):
    db.auto_closed = {PLAIN, CO}
    plain = calculate(PLAIN).json()
    assert plain["rows"][0]["regular_minutes"] == 480, "las 18 h del cierre automatico no se pagan"
    assert plain["rows"][0]["gross_amount"] == 80000.0
    [item] = plain["unverified_shifts"]
    assert item["minutes"] == 18 * 60 and item["employee_name"] == "Ana Mesera" and item["panel_type"] == "mesero"
    assert item["reason"] == "cierre_automatico" and item["source"] == "mini_panel" and item["status"] == "pending"
    db.employee_cfg[(CO, EMP[CO])] = {"monthly_salary": SMMLV, "arl_level": None}
    co = calculate(CO, token="admin-co").json()
    assert co["rows"][0]["regular_minutes"] + co["rows"][0]["extra_minutes"] == 480
    assert co["unverified_shifts"][0]["minutes"] == 18 * 60
    assert co["totals"]["unverified_minutes"] == 18 * 60
    # Sin cierres automaticos la respuesta no cambia (sin la clave nueva).
    db.auto_closed = set()
    assert "unverified_shifts" not in calculate(PLAIN).json()


def test_hospitality_payroll_co_payroll_requires_session_once_the_company_has_the_module(db):
    assert calculate(CO).status_code == 401
    other = calculate(CO, token="admin-plain")
    assert other.status_code == 403 and "tenant_not_allowed" in other.text
    assert calculate(MANUAL).status_code == 401
    for path in ("/periods", f"/periods/{uuid.uuid4()}"):
        assert client.get(f"/api/v1/payroll/companies/{CO}{path}").status_code == 401


def test_hospitality_payroll_co_missing_year_params_is_a_clear_error(db):
    db.params = {}
    response = calculate(CO, token="admin-co")
    assert response.status_code == 409
    assert "No hay parametros de ley cargados para 2026" in response.text


def test_hospitality_payroll_co_params_are_admin_v2_only_and_validated(db):
    assert client.get("/api/v1/payroll-co/params").status_code == 401
    assert client.get("/api/v1/payroll-co/params", headers={"Authorization": "Bearer admin-co"}).status_code == 401
    assert client.put("/api/v1/payroll-co/params/2027", json={}).status_code == 401
    db.admin_v2.return_value = True
    listing = client.get("/api/v1/payroll-co/params").json()
    assert listing["years"][0]["year"] == 2026 and listing["years"][0]["params"]["smmlv"] == 1750905
    assert any(field["key"] == "sunday_holiday_pct" for field in listing["fields"])
    template = client.get("/api/v1/payroll-co/params/2027/template").json()
    assert template["exists"] is False and template["changes"] == [{"from": "2027-07-01", "sunday_holiday_pct": 100}]
    bad = client.put("/api/v1/payroll-co/params/2027", json={"params": {"smmlv": 1}, "changes": []})
    assert bad.status_code == 400 and "falta" in bad.text
    body = {**template, "params": {**template["params"], "smmlv": 1900000, "transport_allowance": 270000}}
    assert client.put("/api/v1/payroll-co/params/2027", json=body).status_code == 200
    assert db.params[2027]["params"]["smmlv"] == 1900000


def test_hospitality_payroll_co_company_config_needs_admin_and_module_and_stays_in_tenant(db):
    url = f"/api/v1/payroll-co/companies/{CO}/config"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer mesero-co"}).status_code == 403
    assert client.get(url, headers={"Authorization": "Bearer admin-plain"}).status_code == 403
    no_module = client.get(f"/api/v1/payroll-co/companies/{PLAIN}/config", headers={"Authorization": "Bearer admin-plain"})
    assert no_module.status_code == 403 and "module_not_enabled_for_tenant" in no_module.text
    saved = client.put(url, headers={"Authorization": "Bearer admin-co"}, json={
        "arl_level": 2, "exonerated": True,
        "employees": [{"id": EMP[CO], "monthly_salary": 2000000, "arl_level": ""}, {"id": OTHER_EMP, "monthly_salary": 9}],
    })
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data["arl_level"] == 2 and data["exonerated"] is True
    assert data["employees"][0]["monthly_salary"] == 2000000
    assert (CO, OTHER_EMP) not in db.employee_cfg, "no escribe empleados de otra empresa"
    assert client.put(url, headers={"Authorization": "Bearer admin-co"}, json={"arl_level": 9}).status_code == 400
    # El salario configurado se usa en el calculo.
    detail = calculate(CO, token="admin-co").json()["rows"][0]["colombia"]
    assert detail["monthly_salary"] == 2000000 and detail["salary_missing"] is False
    assert any(p["label"] == "ARL nivel 2" for p in detail["employer_contributions"])


def test_hospitality_payroll_co_module_is_in_both_catalogs_and_off_for_everyone():
    meta = module_catalog_v1.MODULE_CATALOG_ES["nomina_colombia"]
    assert meta["name"] == "APLICAR NORMATIVA LABORAL COLOMBIANA"
    admin_js = (ROOT / "app/web/admin_v2.js").read_text(encoding="utf-8")
    assert 'nomina_colombia: ["APLICAR NORMATIVA LABORAL COLOMBIANA"' in admin_js
    migration = (ROOT / "migrations/versions/021t_nomina_colombia.py").read_text(encoding="utf-8")
    assert "company_modules (" not in migration, "la migracion no activa el modulo para ninguna empresa"
    assert len(MIGRATION.revision) <= 32
