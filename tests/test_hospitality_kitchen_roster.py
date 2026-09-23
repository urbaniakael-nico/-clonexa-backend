"""Cocina "Registro entrada" (switch kitchen_roster, off by default).

Runs the real roster code and the real start/pause/resume/finish SQL paths
against an in-memory mini_panel_work_sessions. Only the Workforce
attendance sync (the CRM/nomina link) is replaced by a recorder, so each
test can check exactly what each person sends to CRM on their own.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import re
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import company_users, waiter_ordering


COMPANY_ID = uuid.uuid4()


def _employee(name, role, status="active"):
    return SimpleNamespace(id=uuid.uuid4(), company_id=COMPANY_ID, full_name=name, role=role, employee_type="operator", status=status)


def _login(employee, panel="cocina"):
    return SimpleNamespace(
        id=uuid.uuid4(), company_id=COMPANY_ID, full_name=employee.full_name, email="x@y", role=panel,
        settings_json={"mini_panel": {"enabled": True, "type": panel, "employee_id": str(employee.id)}},
    )


class WorkSessionsDb:
    def __init__(self, employees, users):
        self.employees = employees
        self.users = users
        self.rows: dict[str, dict] = {}
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.ddl: list[str] = []

    def _result(self, rows=None, scalars=None, rowcount=0):
        rows = rows or []
        mappings = SimpleNamespace(all=lambda: rows, first=lambda: rows[0] if rows else None)
        return SimpleNamespace(
            mappings=lambda: mappings,
            scalars=lambda: SimpleNamespace(all=lambda: list(scalars or [])),
            rowcount=rowcount,
        )

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        if sql.startswith(("CREATE", "ALTER")):
            self.ddl.append(sql)
            return self._result()
        if "FROM company_users" in sql:
            return self._result(scalars=self.users)
        if "FROM employees" in sql:
            return self._result(scalars=self.employees)
        if sql.startswith("INSERT INTO mini_panel_work_sessions"):
            self.rows[params["id"]] = {
                "id": params["id"], "company_id": params["company_id"], "user_id": params["user_id"],
                "employee_id": params["employee_id"], "panel_type": "cocina", "status": "active",
                "location_label": "Cocina", "started_at": params["now"], "active_started_at": params["now"],
                "ended_at": None, "current_break_started_at": None, "active_seconds": 0, "break_seconds": 0,
                "action_log": [],
            }
            return self._result(rowcount=1)
        if "SELECT DISTINCT ON (employee_id)" in sql:
            wanted = {v for k, v in params.items() if k.startswith("e_")}
            rows = [dict(r) for r in self.rows.values()
                    if r["company_id"] == params["company_id"] and r["employee_id"] in wanted and r["status"] in {"active", "break"}]
            return self._result(rows)
        if "SELECT * FROM mini_panel_work_sessions WHERE id" in sql:
            row = self.rows.get(params["id"])
            return self._result([dict(row)] if row else [])
        if "SET action_log" in sql:
            row = self.rows[params["id"]]
            assert row["company_id"] == params["company_id"]
            row["action_log"] = row["action_log"] + json.loads(params["entry"])
            return self._result(rowcount=1)
        m = re.search(r"SET status = '(\w+)'", sql)
        if m and "UPDATE mini_panel_work_sessions" in sql:
            row = self.rows[params["id"]]
            row["status"] = m.group(1)
            row["active_seconds"] += params.get("active_delta", 0)
            row["break_seconds"] += params.get("break_delta", 0)
            if m.group(1) == "break":
                row["active_started_at"], row["current_break_started_at"] = None, params["now"]
            elif m.group(1) == "active":
                row["active_started_at"], row["current_break_started_at"] = params["now"], None
            else:
                row["ended_at"], row["active_started_at"], row["current_break_started_at"] = params["now"], None, None
            return self._result(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql[:120]}")


@pytest.fixture
def kitchen(monkeypatch):
    pedro = _employee("Pedro Parrilla", "Parrillero")
    ana = _employee("Ana Cocina", "cocinera")
    luis = _employee("Luis Chef", "Chef")
    mesero = _employee("Laura Mesa", "Mesero")
    retirado = _employee("Viejo Cocinero", "cocinero", status="archived")
    tablet = _login(pedro)                      # Pedro has a cocina login
    db = WorkSessionsDb([pedro, ana, luis, mesero, retirado], [tablet, _login(mesero, "mesero")])

    monkeypatch.setattr(company_users, "_kitchen_roster_storage_ready_044d", False)
    monkeypatch.setattr(company_users, "_cx_company_or_404_019d", AsyncMock(return_value=SimpleNamespace(id=COMPANY_ID)))
    monkeypatch.setattr(company_users, "_cx_mp_shift_max_hours_028q", AsyncMock(return_value=12.0))
    crm = []

    async def sync(_db, company_id, user, mini_panel, row, *, event_type=None, event_at=None):
        crm.append({"employee_id": str(row["employee_id"]), "status": row["status"], "event": event_type, "by": getattr(user, "full_name", "")})

    monkeypatch.setattr(company_users, "_cx_mp_sync_attendance_023j", sync)
    return SimpleNamespace(db=db, pedro=pedro, ana=ana, luis=luis, mesero=mesero, retirado=retirado, tablet=tablet, crm=crm)


async def _roster(k):
    return {m["full_name"]: m for m in (await company_users.cx_kitchen_roster_payload_044d(k.db, COMPANY_ID))["members"]}


async def _press(k, employee, action):
    return await company_users.cx_kitchen_roster_action_044d(k.db, COMPANY_ID, str(employee.id), action, k.tablet)


@pytest.mark.asyncio
async def test_the_roster_lists_everyone_assigned_to_the_kitchen(kitchen):
    roster = await _roster(kitchen)
    assert sorted(roster) == ["Ana Cocina", "Luis Chef", "Pedro Parrilla"]
    assert roster["Pedro Parrilla"]["has_login"] is True
    assert roster["Ana Cocina"]["has_login"] is False
    assert all(m["state"] == "off" for m in roster.values())
    # the first use makes user_id nullable and adds the audit column, once
    assert any("DROP NOT NULL" in d for d in kitchen.db.ddl)
    assert any("action_log" in d for d in kitchen.db.ddl)


@pytest.mark.asyncio
async def test_iniciar_pausar_salir_per_person_each_sent_to_crm_on_its_own(kitchen):
    await _press(kitchen, kitchen.ana, "iniciar")
    await _press(kitchen, kitchen.luis, "iniciar")
    roster = await _roster(kitchen)
    assert roster["Ana Cocina"]["state"] == "working"
    assert roster["Luis Chef"]["state"] == "working"
    assert roster["Pedro Parrilla"]["state"] == "off"

    await _press(kitchen, kitchen.ana, "pausar")
    assert (await _roster(kitchen))["Ana Cocina"]["state"] == "on_break"
    assert (await _roster(kitchen))["Luis Chef"]["state"] == "working"   # independent

    await _press(kitchen, kitchen.ana, "iniciar")                         # resume
    assert (await _roster(kitchen))["Ana Cocina"]["state"] == "working"

    member = await _press(kitchen, kitchen.ana, "salir")
    assert member["state"] == "off"
    assert (await _roster(kitchen))["Luis Chef"]["state"] == "working"

    ana_events = [(e["status"], e["event"]) for e in kitchen.crm if e["employee_id"] == str(kitchen.ana.id)]
    assert ana_events == [("active", "start_shift"), ("break", "break_start"), ("active", "break_end"), ("finished", "check_out")]
    luis_events = [e["event"] for e in kitchen.crm if e["employee_id"] == str(kitchen.luis.id)]
    assert luis_events == ["start_shift"]


@pytest.mark.asyncio
async def test_each_press_records_who_pressed_it(kitchen):
    await _press(kitchen, kitchen.ana, "iniciar")
    await _press(kitchen, kitchen.ana, "pausar")
    row = next(r for r in kitchen.db.rows.values() if r["employee_id"] == str(kitchen.ana.id))
    assert [e["action"] for e in row["action_log"]] == ["iniciar", "pausar"]
    assert {e["by_name"] for e in row["action_log"]} == {"Pedro Parrilla"}
    assert row["user_id"] is None                     # Ana has no login of her own


@pytest.mark.asyncio
async def test_a_cook_with_a_login_shares_the_row_his_login_uses(kitchen):
    await _press(kitchen, kitchen.pedro, "iniciar")
    row = next(r for r in kitchen.db.rows.values() if r["employee_id"] == str(kitchen.pedro.id))
    assert row["user_id"] == str(kitchen.tablet.id)


@pytest.mark.asyncio
async def test_iniciar_twice_does_not_open_a_second_shift(kitchen):
    await _press(kitchen, kitchen.ana, "iniciar")
    await _press(kitchen, kitchen.ana, "iniciar")
    assert len([r for r in kitchen.db.rows.values() if r["employee_id"] == str(kitchen.ana.id)]) == 1
    assert len([e for e in kitchen.crm if e["employee_id"] == str(kitchen.ana.id)]) == 1


@pytest.mark.asyncio
async def test_pausar_or_salir_without_an_open_shift_is_a_conflict(kitchen):
    for action in ("pausar", "salir"):
        with pytest.raises(HTTPException) as exc:
            await _press(kitchen, kitchen.ana, action)
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_people_outside_the_kitchen_cannot_be_clocked_from_the_tablet(kitchen):
    for person in (kitchen.mesero, kitchen.retirado):
        with pytest.raises(HTTPException) as exc:
            await _press(kitchen, person, "iniciar")
        assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        await _press(kitchen, kitchen.ana, "borrar")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_a_forgotten_salir_turno_is_closed_after_the_max_shift(kitchen):
    await _press(kitchen, kitchen.ana, "iniciar")
    row = next(r for r in kitchen.db.rows.values() if r["employee_id"] == str(kitchen.ana.id))
    row["started_at"] = row["active_started_at"] = datetime.now(timezone.utc) - timedelta(hours=13)
    roster = await _roster(kitchen)
    assert roster["Ana Cocina"]["state"] == "off"
    assert row["status"] == "finished"
    assert kitchen.crm[-1]["event"] == "check_out"


# ---------------------------------------------------------------------------
# Entering the kitchen panel starts counting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kitchen_login_starts_that_cooks_shift_when_the_switch_is_on(kitchen, monkeypatch):
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_module_settings_026k", AsyncMock(return_value={"kitchen_roster": True}))
    await company_users._cx_kitchen_autostart_on_login_044d(kitchen.db, COMPANY_ID, kitchen.tablet)
    assert (await _roster(kitchen))["Pedro Parrilla"]["state"] == "working"
    assert kitchen.crm[0] == {"employee_id": str(kitchen.pedro.id), "status": "active", "event": "start_shift", "by": "Pedro Parrilla"}


@pytest.mark.asyncio
async def test_kitchen_login_does_nothing_without_the_switch(kitchen, monkeypatch):
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_module_settings_026k", AsyncMock(return_value={}))
    await company_users._cx_kitchen_autostart_on_login_044d(kitchen.db, COMPANY_ID, kitchen.tablet)
    assert kitchen.db.rows == {}
    assert kitchen.crm == []


@pytest.mark.asyncio
async def test_an_attendance_failure_never_blocks_the_kitchen_login(kitchen, monkeypatch):
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_module_settings_026k", AsyncMock(return_value={"kitchen_roster": True}))
    monkeypatch.setattr(company_users, "cx_kitchen_roster_action_044d", AsyncMock(side_effect=RuntimeError("db down")))
    await company_users._cx_kitchen_autostart_on_login_044d(kitchen.db, COMPANY_ID, kitchen.tablet)   # no raise


@pytest.mark.asyncio
async def test_mini_panel_login_calls_the_autostart_for_cocina_only(monkeypatch):
    autostart = AsyncMock()
    monkeypatch.setattr(company_users, "_cx_kitchen_autostart_on_login_044d", autostart)
    for panel, expected in (("cocina", 1), ("mesero", 0)):
        autostart.reset_mock()
        user = SimpleNamespace(
            id=uuid.uuid4(), company_id=COMPANY_ID, email="c@x", full_name="C", role=panel, status="active",
            password_hash="h", failed_login_attempts=0, settings_json={"mini_panel": {"enabled": True, "type": panel}},
        )
        monkeypatch.setattr(company_users, "_cx_require_waiter_ordering_module_026k", AsyncMock())
        monkeypatch.setattr(company_users, "_cx_require_local_network_026k", AsyncMock())
        monkeypatch.setattr(company_users, "_cx_company_or_404_019d", AsyncMock(return_value=SimpleNamespace(id=COMPANY_ID)))
        monkeypatch.setattr(company_users, "_cx_find_minipanel_login_user_019d", AsyncMock(return_value=user))
        monkeypatch.setattr(company_users, "verify_password", lambda raw, hashed: True)
        monkeypatch.setattr(company_users, "register_access_session", AsyncMock(return_value="s"))
        monkeypatch.setattr(company_users, "close_other_sessions_for_subject", AsyncMock(return_value=0))
        monkeypatch.setattr(company_users, "create_access_token", lambda data, expires_minutes=None: "jwt")
        monkeypatch.setattr(company_users, "get_access_token_expire_minutes", lambda: 480)
        monkeypatch.setattr(company_users, "_cx_minipanel_session_payload_019d", AsyncMock(return_value={"ok": True}))
        payload = company_users.MiniPanelLoginRequest(username="c", password="x", panel_type=panel)
        await company_users.mini_panel_login(
            COMPANY_ID, payload, SimpleNamespace(headers={}, client=None), SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock()),
        )
        assert autostart.await_count == expected, panel


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_roster_endpoints_are_off_without_the_switch(monkeypatch):
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value={}))
    cook = SimpleNamespace(id=uuid.uuid4(), full_name="Pedro", role="cocina")
    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.kitchen_team(COMPANY_ID, db=SimpleNamespace(), _user=cook)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.kitchen_team_action(COMPANY_ID, uuid.uuid4(), "iniciar", db=SimpleNamespace(), user=cook)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_roster_action_endpoint_passes_the_logged_in_cook_as_operator(monkeypatch):
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value={"kitchen_roster": True}))
    action = AsyncMock(return_value={"employee_id": "e", "state": "working"})
    monkeypatch.setattr(waiter_ordering, "cx_kitchen_roster_action_044d", action)
    cook = SimpleNamespace(id=uuid.uuid4(), full_name="Pedro", role="cocina")
    employee_id = uuid.uuid4()
    result = await waiter_ordering.kitchen_team_action(COMPANY_ID, employee_id, "pausar", db=SimpleNamespace(), user=cook)
    assert result["member"]["state"] == "working"
    assert action.await_args.args[1:] == (COMPANY_ID, str(employee_id), "pausar", cook)


def test_roster_endpoints_require_a_cocina_session():
    from fastapi.params import Depends as DependsParam
    import inspect

    for endpoint in (waiter_ordering.kitchen_team, waiter_ordering.kitchen_team_action):
        deps = [p.default.dependency for p in inspect.signature(endpoint).parameters.values() if isinstance(p.default, DependsParam)]
        assert waiter_ordering._require_cocina in deps, endpoint.__name__


def test_kitchen_roles_are_recognised():
    for role in ("Parrillero", "cocinera", "Cocinero", "Chef", "auxiliar de cocina", "Kitchen"):
        assert company_users._cx_is_kitchen_role_044d(role), role
    for role in ("Mesero", "Cajero", "Dueno", ""):
        assert not company_users._cx_is_kitchen_role_044d(role), role
