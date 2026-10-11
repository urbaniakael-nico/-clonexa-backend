"""Roles de empleado por empresa (capa B) — registro, permisos y rutas.

- El registro (role_catalog.json) tiene todos los roles que ofrece hoy el
  selector de Personal y el codigo nuevo "otro".
- Los permisos salen del CODIGO interno: Supervisor y Logistica (inventario)
  piden materiales en el bot; Director (gerencia), Operario y Otro no. "otro"
  no lo reconoce ningun panel (no choca con el mini panel "Otro").
- Sin configuracion nada cambia: el nombre visible, el selector y las
  respuestas de reportes son las de siempre.
- Las rutas exigen sesion: Admin V2 para la consola, usuario de ESA empresa o
  Admin V2 para el portal.
- El saludo del bot dice el rol visible solo con configuracion.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.api.v1.endpoints import bots, company_users, crm_core_v1
from app.api.v1.endpoints import employee_roles as client_route
from app.api.v1.endpoints import employees as employees_ep
from app.services import employee_roles as roles
from app.web import admin_v2plus_companies as ep
from app.web import employee_roles_routes as admin_route

ROOT = Path(__file__).resolve().parent.parent
URBANIA = {"roles": [{"code": "gerencia", "label": "Director"}, {"code": "supervisor", "label": "Supervisor"},
                     {"code": "inventario", "label": "Logística"}, {"code": "operario", "label": "Operario"}, {"code": "otro", "label": "Otro"}]}


# ------------------------------------------------------------- registro
def test_catalog_has_every_role_the_selector_offers_today_plus_otro():
    source = (ROOT / "app" / "web" / "client.js").read_text(encoding="utf-8")
    offered = set()
    for name in ("CX_PERSONAL_ROLES_DEFAULT_030S", "CX_PERSONAL_ROLES_WAITER_ORDERING_030S"):
        block = source[source.index(f"const {name} = ["):]
        block = block[: block.index("];")]
        offered |= set(re.findall(r'\["([a-z_]+)",', block))
    offered.add("domiciliario")
    codes = set(roles.codes())
    assert offered <= codes, f"faltan en el registro: {offered - codes}"
    assert codes - offered == {"otro"}, "el unico codigo nuevo es otro"
    for role in roles.catalog()["roles"]:
        assert role["permits"] and role["evidence"], role["code"]


def emp(role):
    return SimpleNamespace(role=role, employee_type=role)


def test_permissions_come_from_the_internal_code_for_urbania_roles():
    # Bot de materiales: Supervisor y Logistica si; Director, Operario y Otro no.
    assert bots._employee_can_request_material(emp("supervisor")) is True
    assert bots._employee_can_request_material(emp("inventario")) is True
    for code in ("gerencia", "operario", "otro"):
        assert bots._employee_can_request_material(emp(code)) is False, code
    # El nombre visible no da permisos: "Logística" como texto no pide materiales... salvo que sea su codigo.
    assert bots._employee_can_request_material(emp("Director")) is False


def test_otro_has_no_special_permission_and_is_not_the_other_mini_panel():
    otro = SimpleNamespace(role="otro", employee_type="otro")
    assert company_users._cx_employee_is_sales_019c(otro) is False
    assert company_users._cx_employee_is_store_023s(otro) is False
    assert company_users._cx_is_kitchen_role_044d("otro") is False
    assert company_users._cx_employee_is_transport_agent_028n(otro) is False
    assert not (company_users._cx_role_tokens_028n("otro") & company_users.TRANSPORT_MONITOR_ROLE_TOKENS_028N)
    assert crm_core_v1.hospitality_area_code_048f("otro") == ""
    # El tipo de mini panel "otro" sigue siendo el panel Otro, como siempre.
    assert company_users._cx_panel_type_019d("otro") == "other"


# ------------------------------------------------------- reglas puras
def test_without_configuration_nothing_changes():
    assert roles.parse_config({}) is None
    assert roles.parse_config({"employee_roles": {"roles": None}}) is None
    payload = {"rows": [{"role": "gerencia", "employee_role": "supervisor"}]}
    assert roles.relabel(payload, None) is payload
    assert roles.display(None, "gerencia") == "gerencia"
    assert roles.allowed_change(None, "cualquiera") is True
    assert roles.client_view(None) == {"configured": False, "roles": []}


def test_configuration_labels_order_and_relabel():
    config = roles.parse_config({"employee_roles": {"roles": list(reversed(URBANIA["roles"])) + [{"code": "no_existe", "label": "X"}]}})
    assert [r["code"] for r in config["roles"]] == ["gerencia", "supervisor", "inventario", "operario", "otro"], "orden del registro, sin desconocidos"
    out = roles.relabel({"employees": [{"role": "gerencia", "x": {"employee_role": "inventario"}}, {"role": "tecnico"}], "role": 3}, config)
    assert out == {"employees": [{"role": "Director", "x": {"employee_role": "Logística"}}, {"role": "tecnico"}], "role": 3}
    assert roles.display(config, "Supervisor") == "Supervisor"


def test_validate_body_rules():
    body = {"roles": [{"code": "gerencia", "enabled": True, "label": " Director "}, {"code": "tecnico", "enabled": False, "label": "x"},
                      {"code": "otro", "enabled": True, "label": ""}]}
    config = roles.validate_body(body)
    assert config["roles"] == [{"code": "gerencia", "label": "Director"}, {"code": "otro", "label": "Otro"}]
    with pytest.raises(roles.Invalid):
        roles.validate_body({"roles": [{"code": "gerencia", "enabled": False}]})
    with pytest.raises(roles.Invalid):
        roles.validate_body({"roles": [{"code": "inventado", "enabled": True}]})
    with pytest.raises(roles.Invalid):
        roles.validate_body({"roles": [{"code": "gerencia", "label": "Mismo"}, {"code": "operario", "label": "mismo"}]})
    with pytest.raises(roles.Invalid):
        roles.validate_body({"roles": [{"code": "gerencia", "label": "x" * 41}]})


def test_allowed_change_keeps_a_turned_off_role_but_never_assigns_one():
    config = roles.parse_config({"employee_roles": URBANIA})
    assert roles.allowed_change(config, "supervisor", "tecnico") is True
    assert roles.allowed_change(config, "tecnico", "tecnico") is True, "rol no habilitado: se puede guardar la fila sin cambiarlo"
    assert roles.allowed_change(config, "tecnico", "operario") is False
    assert roles.allowed_change(config, "vendedor") is False


def test_view_marks_counts_and_unknown_roles():
    config = roles.parse_config({"employee_roles": URBANIA})
    view = roles.view(config, {"supervisor": 2, "tecnico": 1, "rol_raro": 4})
    by = {r["code"]: r for r in view["roles"]}
    assert by["gerencia"]["enabled"] and by["gerencia"]["visible_label"] == "Director"
    assert by["tecnico"]["enabled"] is False and by["tecnico"]["employees"] == 1
    assert view["unknown_roles"] == {"rol_raro": 4}
    assert all(r["enabled"] for r in roles.view(None, {})["roles"]), "sin configuracion: todos como siempre"


# ------------------------------------------------------------- rutas
@pytest.fixture
def client(monkeypatch):
    async def fake_db():
        yield SimpleNamespace()

    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(c=TestClient(app_main.app), mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


CID = str(uuid.uuid4())


def test_console_routes_require_admin_v2_session_and_save_with_audit(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    assert client.c.get(f"/admin-v2/api/companies/{CID}/employee-roles").status_code == 401
    assert client.c.put(f"/admin-v2/api/companies/{CID}/employee-roles", json={"roles": []}).status_code == 401

    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    client.mp.setattr(admin_route, "load_company", AsyncMock(return_value={"id": CID, "name": "URBANIA", "kind": "registrada"}))
    client.mp.setattr(roles, "load_config", AsyncMock(return_value=None))
    client.mp.setattr(roles, "role_counts", AsyncMock(return_value={"supervisor": 1, "tecnico": 2}))
    saved = AsyncMock(return_value=True)
    client.mp.setattr(roles, "save_config", saved)
    audit = AsyncMock()
    client.mp.setattr(admin_route, "_audit", audit)

    view = client.c.get(f"/admin-v2/api/companies/{CID}/employee-roles").json()
    assert view["configured"] is False and len(view["roles"]) == len(roles.codes())

    body = {"roles": [{"code": r["code"], "enabled": r["code"] in {"gerencia", "supervisor", "inventario", "operario", "otro"},
                       "label": {"gerencia": "Director", "inventario": "Logística"}.get(r["code"], r["label"])} for r in view["roles"]]}
    res = client.c.put(f"/admin-v2/api/companies/{CID}/employee-roles", json=body)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["not_enabled_employees"] == {"tecnico": 2}, "avisa cuantos quedan con rol no habilitado"
    stored = saved.await_args.args[2]
    assert [r["code"] for r in stored["roles"]] == ["gerencia", "supervisor", "inventario", "operario", "otro"]
    assert audit.await_args.kwargs["empleados_rol_no_habilitado"] == 2

    bad = client.c.put(f"/admin-v2/api/companies/{CID}/employee-roles", json={"roles": [{"code": "gerencia", "enabled": False}]})
    assert bad.status_code == 422
    reset = client.c.put(f"/admin-v2/api/companies/{CID}/employee-roles", json={"reset": True})
    assert reset.status_code == 200 and saved.await_args.args[2] == {"roles": None, "updated_at": None}


def test_portal_route_requires_a_session_of_that_company(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    assert client.c.get(f"/api/v1/employee-roles/companies/{CID}").status_code == 401

    client.mp.setattr(client_route, "require_company_user_for_tenant", AsyncMock(side_effect=HTTPException(status_code=403, detail="tenant_not_allowed")))
    assert client.c.get(f"/api/v1/employee-roles/companies/{CID}", headers={"Authorization": "Bearer x"}).status_code == 403

    client.mp.setattr(client_route, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace()))
    client.mp.setattr(roles, "load_config", AsyncMock(return_value=roles.parse_config({"employee_roles": URBANIA})))
    data = client.c.get(f"/api/v1/employee-roles/companies/{CID}", headers={"Authorization": "Bearer x"}).json()
    assert data["configured"] is True and [r["label"] for r in data["roles"]] == ["Director", "Supervisor", "Logística", "Operario", "Otro"]


@pytest.mark.asyncio
async def test_employee_save_rejects_a_role_the_company_does_not_use(monkeypatch):
    monkeypatch.setattr(roles, "load_config", AsyncMock(return_value=roles.parse_config({"employee_roles": URBANIA})))
    with pytest.raises(HTTPException) as err:
        await employees_ep._cx_check_company_role_051A(SimpleNamespace(), CID, "vendedor")
    assert err.value.status_code == 422
    await employees_ep._cx_check_company_role_051A(SimpleNamespace(), CID, "otro")
    await employees_ep._cx_check_company_role_051A(SimpleNamespace(), CID, "tecnico", "tecnico")
    monkeypatch.setattr(roles, "load_config", AsyncMock(return_value=None))
    await employees_ep._cx_check_company_role_051A(SimpleNamespace(), CID, "vendedor")  # sin configuracion: como siempre


# ------------------------------------------------------------- bot
@pytest.mark.asyncio
@pytest.mark.parametrize("config,expected", [
    (None, "Hola Ana 👋\nEmpresa: URBANIA\n\nSelecciona una acción:"),
    (URBANIA, "Hola Ana 👋\nEmpresa: URBANIA\nRol: Director\n\nSelecciona una acción:"),
])
async def test_bot_greeting_shows_the_visible_role_only_with_configuration(monkeypatch, config, expected):
    sent = AsyncMock()
    monkeypatch.setattr(bots, "_send_telegram_message", sent)
    monkeypatch.setattr(bots, "_enabled_module_codes", AsyncMock(return_value={"workforce", "materials", "inventory"}))
    monkeypatch.setattr(bots, "_get_current_attendance_status", AsyncMock(return_value=None))
    monkeypatch.setattr(roles, "load_config", AsyncMock(return_value=roles.parse_config({"employee_roles": config}) if config else None))
    employee = SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), full_name="Ana", role="gerencia", employee_type="gerencia")
    company = SimpleNamespace(id=uuid.uuid4(), name="URBANIA")
    await bots._send_dynamic_menu(SimpleNamespace(), token="t", chat_id="1", company=company, employee=employee, language="es", greet=True)
    assert sent.await_args.args[2] == expected
    keyboard = json.dumps(sent.await_args.kwargs["reply_markup"])
    assert "clx:cmd:material" not in keyboard, "Director (gerencia) no pide materiales"
