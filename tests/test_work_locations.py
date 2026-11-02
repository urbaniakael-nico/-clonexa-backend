"""Lugares de trabajo (work_locations): reglas puras, rutas protegidas,
migracion aditiva y registro del interruptor. Sin base de datos."""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.api.v1.endpoints import work_locations as api
from app.services import work_locations as svc

ROOT = Path(__file__).resolve().parents[1]


def test_switch_only_true_with_module_enabled():
    assert svc.switch_on(True, {"work_locations": True}) is True
    assert svc.switch_on(True, json.dumps({"work_locations": True})) is True
    assert svc.switch_on(False, {"work_locations": True}) is False, "modulo apagado"
    assert svc.switch_on(True, {"work_locations": "true"}) is False, "solo true de verdad"
    assert svc.switch_on(True, {}) is False, "apagado por defecto"


def test_validate_locations_rules():
    rows = svc.validate_locations({"locations": [
        {"name": "  Virginia ", "code": "v-a", "timezone": "America/New_York"},
        {"name": "Alabama", "code": "AL", "timezone": "America/Chicago", "is_active": False},
    ]}, [])
    assert rows == [
        {"id": None, "name": "Virginia", "code": "VA", "timezone": "America/New_York", "is_active": True, "sort_order": 1},
        {"id": None, "name": "Alabama", "code": "AL", "timezone": "America/Chicago", "is_active": False, "sort_order": 2},
    ]
    for body in ({}, {"locations": []}, {"locations": [{"name": "X", "timezone": "America/Chicago"}]},
                 {"locations": [{"name": "Uno", "timezone": "Mars/Olympus"}]}, {"locations": [{"name": "Uno", "timezone": "UTC; DROP"}]},
                 {"locations": [{"name": "Uno", "timezone": "America/Chicago", "is_active": False}]},
                 {"locations": [{"name": "Uno", "timezone": "America/Chicago"}, {"name": "UNO", "timezone": "America/Chicago"}]},
                 {"locations": [{"id": "ajeno", "name": "Uno", "timezone": "America/Chicago"}]}):
        with pytest.raises(svc.Invalid):
            svc.validate_locations(body, ["propio"])


def _row(name, status, place=None, gps=None, sup=False):
    return {"employee_name": name, "work_location_id": place, "gps_place": gps or "none", "is_supervisor": sup, "core": {"status": status}}


def test_sort_and_group_never_lose_anyone():
    locs = [{"id": "va", "name": "Virginia", "code": "VA", "timezone": "America/New_York", "is_active": True, "sort_order": 1},
            {"id": "al", "name": "Alabama", "code": "AL", "timezone": "America/Chicago", "is_active": True, "sort_order": 2},
            {"id": "tx", "name": "Texas", "code": "TX", "timezone": "America/Chicago", "is_active": False, "sort_order": 3}]
    rows = [_row("zeta", "sin_turno", "va"), _row("Beto", "on_break", "va"), _row("ana", "working", "va", "inside", True),
            _row("Carla", "working", "va"), _row("Dora", "checked_out", "gone"), _row("Eva", "working", None)]
    groups = svc.group_rows(rows, locs)
    assert [g["key"] for g in groups] == ["va", "al", "none"], "inactivo sin gente no sale; Sin asignar al final"
    assert [r["employee_name"] for r in groups[0]["people"]] == ["ana", "Carla", "Beto", "zeta"]
    assert groups[0]["counts"] == {"total": 4, "working": 2, "on_break": 1, "no_shift": 1, "in_perimeter": 1}
    assert groups[0]["supervisors"] == ["ana"]
    assert groups[1]["counts"]["total"] == 0
    assert [r["employee_name"] for r in groups[2]["people"]] == ["Eva", "Dora"], "lugar que ya no existe -> Sin asignar"
    assert sum(g["counts"]["total"] for g in groups) == len(rows)
    assert all(g["key"] != "none" for g in svc.group_rows(rows[:4], locs)), "sin nadie sin lugar no hay seccion Sin asignar"


def test_gps_place_labels():
    assert svc.gps_place(None) == "none"
    assert svc.gps_place({"gps_status": "inside"}) == "inside"
    assert svc.gps_place({"gps_status": "outside"}) == "outside"
    assert svc.gps_place({"gps_status": "unconfigured"}) == "unconfigured"


def test_location_on_date_for_payroll():
    t0 = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    changes = [{"from_location_id": None, "to_location_id": "va", "changed_at": t0},
               {"from_location_id": "va", "to_location_id": "al", "changed_at": t0 + timedelta(days=3)}]
    assert svc.location_on([], "va", t0) == "va"
    assert svc.location_on(changes, "al", t0 - timedelta(hours=1)) is None
    assert svc.location_on(changes, "al", t0 + timedelta(days=1)) == "va"
    assert svc.location_on(changes, "al", t0 + timedelta(days=4)) == "al"


def test_worked_time_uses_the_crm_definition():
    now = datetime(2026, 11, 1, 18, tzinfo=timezone.utc)
    events = [{"event_type": "check_in", "event_at": now - timedelta(hours=4)},
              {"event_type": "break_start", "event_at": now - timedelta(hours=2)},
              {"event_type": "break_end", "event_at": now - timedelta(hours=1, minutes=30)}]
    row = svc.person_row({"employee_id": "e", "employee_name": "Ana", "employee_role": "supervisor", "work_status": "working",
                          "status_started_at": now - timedelta(hours=1, minutes=30)}, events, None, {"gps", "materials"}, now)
    assert row["core"]["shift_effective_seconds"] == 3 * 3600 + 1800, "conectado - pausas"
    assert row["is_supervisor"] is True and row["gps_place"] == "none"
    assert [a["code"] for a in row["adapters"]] == ["gps", "materials"]
    idle = svc.person_row({"employee_id": "f", "employee_name": "Beto", "work_status": "sin_turno"}, events, None, set(), now)
    assert idle["core"]["shift_effective_seconds"] == 0 and idle["gps_place"] == "none"


def test_every_route_requires_session_and_is_registered():
    routes = list(api.router.routes)
    assert len(routes) == 5
    for r in routes:
        assert api.actor in [d.call for d in r.dependant.dependencies], f"{r.path} sin sesion"
    from app.api.v1 import router as v1

    paths = {getattr(r, "path", "") for r in v1.api_router.routes}
    for p in ("", "/locations", "/assign", "/employees/{employee_id}/history", "/board"):
        assert f"/work-locations/companies/{{company_id}}{p}" in paths


def test_roles():
    assert "company_admin" in svc.MANAGE_ROLES and "supervisor" not in svc.MANAGE_ROLES
    assert {"supervisor", "gerencia"} <= svc.ASSIGN_ROLES and "operario" not in svc.ASSIGN_ROLES
    assert not {"mesero", "cocina", "caja"} & svc.READ_ROLES, "los mini paneles no entran"


def test_migration_is_additive_and_short_revision():
    module = importlib.import_module("migrations.versions.024x_work_locations")
    assert len(module.revision) <= 32 and module.down_revision == "024w_nexa_whatsapp"
    src = (ROOT / "migrations" / "versions" / "024x_work_locations.py").read_text(encoding="utf-8")
    upgrade = src.split("def upgrade")[1].split("def downgrade")[0]
    for verb in ("DROP ", "DELETE FROM", "UPDATE ", "TRUNCATE", "ALTER COLUMN"):
        assert verb not in upgrade.upper(), verb
    assert "ADD COLUMN IF NOT EXISTS work_location_id uuid NULL" in upgrade
    assert "f1e8f774-f052-49ca-880a-268805f07db0" in src and "76974191" not in src


def test_switch_registry_entry():
    reg = json.loads((ROOT / "app" / "services" / "switch_registry.json").read_text(encoding="utf-8"))
    sw = next(s for s in reg["switches"] if s["key"] == "work_locations")
    assert sw["module"] == "workforce" and sw["delicate"] is True and "crm" in sw["requires_modules"]
    assert [d["key"] for d in sw["depends_on"]] == ["workforce_v2"]
