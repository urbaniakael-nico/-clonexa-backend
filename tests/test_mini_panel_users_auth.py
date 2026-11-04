"""Usuarios de mini panel: las rutas que estaban abiertas exigen Admin V2 o dueno / admin de ESA
empresa (401 sin sesion, 403 otra empresa o rol sin permiso). Bloqueo de 5 intentos y 15 minutos en
todos los mini paneles. Y ninguna ruta de company_users.py queda sin sesion, salvo el ingreso."""
from __future__ import annotations

import inspect
import re
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.api.deps as deps
from app.api.deps import get_db
from app.api.v1.endpoints import company_users as cu
from app.services import auth_service

CID = uuid.uuid4()
UID = uuid.uuid4()
EMP = uuid.uuid4()
BASE = f"/api/v1/companies/{CID}"
MANAGER_ROUTES = [
    ("GET", "/mini-panel-users", None),
    ("POST", "/mini-panel-users/sales/from-employee", {"employee_id": str(EMP)}),
    ("POST", "/mini-panel-users/store/from-employee", {"employee_id": str(EMP)}),
    ("POST", "/mini-panel-users/mesero/from-employee", {"employee_id": str(EMP)}),
    ("POST", f"/mini-panel-users/{UID}/reset-password", None),
    ("PUT", f"/mini-panel-users/{UID}/sales-goal", {"monthly_goal": 10}),
    ("GET", "/mini-panel-sales-message", None),
    ("PUT", "/mini-panel-sales-message", {"message": "x"}),
    ("GET", "/mini-panel-stores-message", None),
    ("PUT", "/mini-panel-stores-message", {"message": "x"}),
    ("PUT", "/store-login-config", {"stores": []}),
]
READ_CONFIG = ("GET", "/store-login-config", None)


@pytest.fixture()
def api(monkeypatch):
    """Rutas reales; la "base" es un doble que falla: pasar la sesion termina en 500, nunca en 200."""
    state = SimpleNamespace(admin=False, user=None)
    monkeypatch.setattr(cu, "active_admin_v2_session", AsyncMock(side_effect=lambda *_: state.admin))

    async def current(_db, _token):
        if state.user is None:
            raise HTTPException(status_code=401, detail="Token inválido.")
        return state.user

    monkeypatch.setattr(deps, "get_current_company_user", current)
    app = FastAPI()
    app.include_router(cu.router, prefix="/api/v1/companies")

    async def no_db():
        yield None

    app.dependency_overrides[get_db] = no_db
    state.client = TestClient(app, raise_server_exceptions=False)
    return state


def call(api, route, token="t"):
    method, path, body = route
    return api.client.request(method, BASE + path, json=body, headers={"Authorization": f"Bearer {token}"} if token else {})


@pytest.mark.parametrize("route", MANAGER_ROUTES + [READ_CONFIG], ids=lambda r: f"{r[0]} {r[1]}")
def test_sin_sesion_401(api, route):
    assert call(api, route, token=None).status_code == 401
    assert call(api, route, token="invalido").status_code == 401


@pytest.mark.parametrize("route", MANAGER_ROUTES + [READ_CONFIG], ids=lambda r: f"{r[0]} {r[1]}")
def test_otra_empresa_403(api, route):
    api.user = SimpleNamespace(company_id=uuid.uuid4(), role="company_admin")
    assert call(api, route).status_code == 403


@pytest.mark.parametrize("route", MANAGER_ROUTES, ids=lambda r: f"{r[0]} {r[1]}")
@pytest.mark.parametrize("role", ["operator", "mesero", "supervisor", "viewer", "gerencia", "manager", "lider_operacion"])
def test_rol_sin_permiso_403(api, route, role):
    api.user = SimpleNamespace(company_id=CID, role=role)
    assert call(api, route).status_code == 403


@pytest.mark.parametrize("route", MANAGER_ROUTES + [READ_CONFIG], ids=lambda r: f"{r[0]} {r[1]}")
@pytest.mark.parametrize("role", ["company_admin", "admin_empresa", "dueno", "owner", "administrador", "Company Admin"])
def test_dueno_o_admin_de_la_empresa_pasan(api, route, role):
    api.user = SimpleNamespace(company_id=CID, role=role)
    assert call(api, route).status_code not in (401, 403)


@pytest.mark.parametrize("route", MANAGER_ROUTES + [READ_CONFIG], ids=lambda r: f"{r[0]} {r[1]}")
def test_admin_v2_pasa_sin_token(api, route):
    api.admin = True
    assert call(api, route, token=None).status_code not in (401, 403)


@pytest.mark.parametrize("role", ["operator", "supervisor", "viewer", "gerencia"])
def test_el_crm_del_portal_sigue_leyendo_las_tiendas_con_cualquier_rol(api, role):
    api.user = SimpleNamespace(company_id=CID, role=role)
    assert call(api, READ_CONFIG).status_code not in (401, 403)


def _uses_session(route: APIRoute) -> bool:
    """Una dependencia de sesion, o authorization que el cuerpo valida de verdad."""
    names = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies} - {"get_db"}
    if names & {"require_mini_panel_manager", "require_tenant_session", "require_company_user_admin_access"}:
        return True
    params = inspect.signature(route.endpoint).parameters
    source = inspect.getsource(route.endpoint)
    return "authorization" in params and bool(re.search(r"\(\s*db,[^)]*authorization|authorization,|_cx_bearer_token_019d\(authorization\)", source))


def test_ninguna_ruta_de_este_archivo_queda_sin_sesion():
    open_routes = [f"{sorted(r.methods)[0]} {r.path}" for r in cu.router.routes if isinstance(r, APIRoute) and not _uses_session(r)]
    assert open_routes == ["POST /{company_id}/mini-panel-login"], "el ingreso es la unica ruta publica"


# ------------------------------------------------------------------ bloqueo por intentos
def _user(panel="sales", **extra):
    return SimpleNamespace(id=uuid.uuid4(), company_id=CID, email="a@x", full_name="A", role="operator", status="active", password_hash="h", failed_login_attempts=0,
                           locked_until=None, last_login_at=None, must_change_password=False, settings_json={"mini_panel": {"enabled": True, "type": panel, "username": "a"}}, **extra)


def _login_mocks(monkeypatch, user):
    monkeypatch.setattr(cu, "_cx_company_or_404_019d", AsyncMock(return_value=SimpleNamespace(id=CID, name="X")))
    monkeypatch.setattr(cu, "_cx_find_minipanel_login_user_019d", AsyncMock(return_value=user))
    monkeypatch.setattr(cu, "_cx_require_waiter_ordering_module_026k", AsyncMock())
    monkeypatch.setattr(cu, "_cx_require_local_network_026k", AsyncMock())
    monkeypatch.setattr(cu, "register_access_session", AsyncMock(return_value="sid"))
    monkeypatch.setattr(cu, "close_other_sessions_for_subject", AsyncMock())
    monkeypatch.setattr(cu, "_cx_minipanel_session_payload_019d", AsyncMock(return_value={"ok": True}))
    return SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())


async def _try(user_type, db, password="mala"):
    return await cu.mini_panel_login(CID, cu.MiniPanelLoginRequest(username="a", password=password, panel_type=user_type), SimpleNamespace(headers={}, client=None), db=db)


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", ["sales", "store", "inventory", "logistics", "call_center", "external", "other", "mesero", "cocina", "caja"])
async def test_cinco_fallos_bloquean_15_minutos(monkeypatch, panel):
    user = _user(panel)
    db = _login_mocks(monkeypatch, user)
    monkeypatch.setattr(cu, "verify_password", lambda p, _h: p == "buena")
    for _ in range(4):
        with pytest.raises(HTTPException) as e:
            await _try(panel, db)
        assert e.value.status_code == 401
    assert user.locked_until is None
    with pytest.raises(HTTPException) as e:
        await _try(panel, db)
    assert e.value.status_code == 401
    minutes = (user.locked_until - auth_service.utc_now()).total_seconds() / 60
    assert 14.9 < minutes <= 15
    # Bloqueado: ni con la clave correcta.
    with pytest.raises(HTTPException) as e:
        await _try(panel, db, "buena")
    assert e.value.status_code == 403 and e.value.detail == "Usuario temporalmente bloqueado."
    # Pasado el tiempo entra, y el contador vuelve a cero.
    user.locked_until = auth_service.utc_now() - timedelta(seconds=1)
    assert (await _try(panel, db, "buena"))["ok"] is True
    assert user.failed_login_attempts == 0 and user.locked_until is None


@pytest.mark.asyncio
async def test_un_contador_viejo_no_castiga_el_primer_error(monkeypatch):
    user = _user()
    user.failed_login_attempts = 37  # contado cuando los mini paneles no bloqueaban
    db = _login_mocks(monkeypatch, user)
    monkeypatch.setattr(cu, "verify_password", lambda p, _h: False)
    with pytest.raises(HTTPException) as e:
        await _try("sales", db)
    assert e.value.status_code == 401 and user.failed_login_attempts == 1 and user.locked_until is None


@pytest.mark.asyncio
async def test_clave_de_companero_de_tienda_tambien_bloquea(monkeypatch):
    target = _user("store")
    monkeypatch.setattr(cu, "_cx_store_team_target_023w", AsyncMock(return_value=(SimpleNamespace(), _user("store"), {}, None, target, {})))
    monkeypatch.setattr(cu, "verify_password", lambda p, _h: p == "buena")
    db = SimpleNamespace(commit=AsyncMock())
    body = cu.StoreTeamMemberLoginRequest023W(username="a", password="mala")
    for _ in range(5):
        with pytest.raises(HTTPException) as e:
            await cu.mini_panel_store_team_login_023w(CID, "e1", "store", body, "Bearer t", db=db)
        assert e.value.status_code == 401
    good = cu.StoreTeamMemberLoginRequest023W(username="a", password="buena")
    with pytest.raises(HTTPException) as e:
        await cu.mini_panel_store_team_login_023w(CID, "e1", "store", good, "Bearer t", db=db)
    assert e.value.status_code == 403
