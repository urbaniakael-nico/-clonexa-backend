"""Lider de operacion, sin base de datos: la lista blanca cubre TODAS las rutas del API (Nomina,
tarifas y cualquier escritura = 403 con la sesion del lider), las demas sesiones no cambian, y
las reglas puras de operacion, semana y estados."""
from __future__ import annotations

import re
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.v1.endpoints import company_users as cu
from app.api.v1.endpoints import lider_operacion as api
from app.api.v1.router import api_router
from app.services import auth_service
from app.services import lider_operacion as svc
from app.services.auth_service import create_access_token

CID = uuid.uuid4()
VA = str(uuid.uuid4())
AL = str(uuid.uuid4())
PLACES = [{"id": VA, "name": "Virginia", "code": "VA", "slug": "virginia", "accent": 0}, {"id": AL, "name": "Alabama", "code": "AL", "slug": "alabama", "accent": 1}]


def token(panel_type="lider_operacion", scope="mini_panel", company=CID, place=AL, sid="s1"):
    return create_access_token({"sub": str(uuid.uuid4()), "company_id": str(company), "scope": scope, "panel_type": panel_type, "sid": sid, "work_location_id": place}, expires_minutes=5)


def guard_app() -> FastAPI:
    """Las rutas reales con el guardia real. El guardia responde antes de tocar la base."""
    app = FastAPI()
    app.middleware("http")(app_main._clonexa_leader_guard)
    app.include_router(api_router, prefix="/api/v1")
    return app


def api_routes():
    for route in api_router.routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, "/api/v1" + re.sub(r"\{[^}]+\}", str(CID), route.path)


def test_la_lista_blanca_es_exacta():
    allowed = {(m, p) for m, p in api_routes() if svc.request_allowed(m, p)}
    assert allowed == {
        ("GET", f"/api/v1/lider-operacion/companies/{CID}/inicio"),
        ("GET", f"/api/v1/lider-operacion/companies/{CID}/crm"),
        ("GET", f"/api/v1/lider-operacion/companies/{CID}/reportes"),
        ("GET", f"/api/v1/lider-operacion/companies/{CID}/crm/lista.pdf"),
        ("GET", f"/api/v1/lider-operacion/companies/{CID}/reportes/export.pdf"),
        ("POST", f"/api/v1/lider-operacion/companies/{CID}/pin/verificar"),
        ("POST", f"/api/v1/lider-operacion/companies/{CID}/pin/marcar"),
        ("POST", f"/api/v1/lider-operacion/companies/{CID}/crm/{CID}/finalizar"),
        ("POST", "/api/v1/auth/logout"),
    }


def test_toda_ruta_del_api_rechaza_al_lider():
    client = TestClient(guard_app(), raise_server_exceptions=False)
    headers = {"Authorization": f"Bearer {token()}"}
    checked = writes = 0
    for method, path in api_routes():
        if svc.request_allowed(method, path):
            continue
        response = client.request(method, path, headers=headers)
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
        assert response.json()["detail"] == auth_service.LEADER_ONLY_DETAIL
        checked += 1
        writes += method != "GET"
    assert checked > 300 and writes > 100, "la prueba debe recorrer el API completo"


@pytest.mark.parametrize("method,path", [
    ("GET", f"/api/v1/payroll/companies/{CID}/period"),
    ("GET", f"/api/v1/us-payroll/companies/{CID}/rates"),
    ("GET", f"/api/v1/reports-board/companies/{CID}"),
    ("GET", f"/api/v1/reports-board/companies/{CID}/export.pdf"),
    ("GET", f"/api/v1/work-locations/companies/{CID}/board"),
    ("PUT", f"/api/v1/reports-board/companies/{CID}/places/{VA}"),
    ("POST", f"/api/v1/companies/{CID}/mini-panel-change-password"),
    ("GET", "/admin-v2/api/companies"),
])
def test_rutas_sensibles_tambien_con_el_token_en_la_url(method, path):
    client = TestClient(guard_app(), raise_server_exceptions=False)
    assert client.request(method, path, headers={"Authorization": f"Bearer {token()}"}).status_code == 403
    assert client.request(method, f"{path}?access_token={token()}").status_code == 403


@pytest.mark.parametrize("auth", ["otro_panel", "portal", "invalido", "sin_token"])
def test_las_demas_sesiones_no_pasan_por_el_guardia(auth):
    app = FastAPI()
    app.middleware("http")(app_main._clonexa_leader_guard)
    app.get("/api/v1/algo")(lambda: {"ok": True})
    headers = {"otro_panel": {"Authorization": f"Bearer {token('mesero')}"}, "portal": {"Authorization": f"Bearer {token('', scope='client')}"},
               "invalido": {"Authorization": "Bearer xxx"}, "sin_token": {}}[auth]
    assert TestClient(app).get("/api/v1/algo", headers=headers).status_code == 200


def test_el_guardia_esta_en_la_app_real():
    client = TestClient(app_main.app, raise_server_exceptions=False)
    response = client.get(f"/api/v1/payroll/companies/{CID}/period", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 403 and response.json()["detail"] == auth_service.LEADER_ONLY_DETAIL


# ------------------------------------------------------------------ usuario, no solo token
@pytest.mark.asyncio
async def test_el_usuario_lider_no_sirve_en_rutas_comunes_aunque_el_token_no_lo_diga(monkeypatch):
    user = SimpleNamespace(settings_json={"mini_panel": {"type": "lider_operacion"}}, status="active")
    monkeypatch.setattr(auth_service, "user_from_token_claims", AsyncMock(return_value=user))
    with pytest.raises(HTTPException) as e:
        await auth_service.get_current_company_user(None, token("", scope="client"))
    assert e.value.status_code == 403
    other = SimpleNamespace(settings_json={"mini_panel": {"type": "mesero"}}, status="active")
    monkeypatch.setattr(auth_service, "user_from_token_claims", AsyncMock(return_value=other))
    assert await auth_service.get_current_company_user(None, token("mesero")) is other


def test_bloqueo_tras_cinco_intentos():
    user = SimpleNamespace(failed_login_attempts=0, locked_until=None)
    for _ in range(4):
        auth_service.note_failed_login(user)
    assert not auth_service.is_locked(user)
    auth_service.note_failed_login(user)
    assert auth_service.is_locked(user)


def test_tipo_de_mini_panel():
    assert cu._cx_panel_type_019d("lider_operacion") == "lider_operacion"
    assert cu._cx_minipanel_type_label_019d("lider_operacion") == "Líder de operación"
    assert "lider_operacion" not in cu.WAITER_ORDERING_PANEL_TYPES_026K
    for other in ("sales", "store", "mesero", "caja", "crm_lab"):
        assert cu._cx_panel_type_019d(other) == other


@pytest.mark.asyncio
async def test_no_se_crea_por_la_ruta_generica_de_mini_paneles():
    with pytest.raises(HTTPException) as e:
        await cu._cx_create_minipanel_user_from_employee_026j(company_id=CID, payload=cu.SalesMiniPanelUserCreateRequest(employee_id=uuid.uuid4()),
                                                              panel_type="lider_operacion", db=None, source="x")
    assert e.value.status_code == 400


# ------------------------------------------------------------------ dependencia del panel
@pytest.mark.asyncio
@pytest.mark.parametrize("case,code", [("sin_token", 401), ("otro_panel", 403), ("portal", 403), ("otra_empresa", 403), ("sin_sid", 401)])
async def test_sesion_del_panel(case, code):
    auth = {"sin_token": None, "otro_panel": f"Bearer {token('mesero')}", "portal": f"Bearer {token(scope='client')}",
            "otra_empresa": f"Bearer {token(company=uuid.uuid4())}", "sin_sid": f"Bearer {token(sid='')}"}[case]
    with pytest.raises(HTTPException) as e:
        await api.leader(CID, auth, db=None)
    assert e.value.status_code == code


def test_pedir_la_otra_operacion_es_403():
    who = {"place": {**PLACES[1]}}
    assert api.only_mine(who) is who
    assert api.only_mine(who, AL) is who
    assert api.only_mine(who, None, "alabama") is who
    for kw in ((VA, None), (None, "virginia"), (None, "VA")):
        with pytest.raises(HTTPException) as e:
            api.only_mine(who, *kw)
        assert e.value.status_code == 403


# ------------------------------------------------------------------ reglas puras
def test_operacion_del_enlace():
    for wanted in ("alabama", "Alabama", "AL", AL.upper()):
        assert svc.resolve_place(PLACES, wanted)["id"] == AL
    for wanted in ("", None, "texas"):
        assert svc.resolve_place(PLACES, wanted) is None
    assert svc.slug("São Paulo Norte") == "sao-paulo-norte"
    assert svc.entry_link(CID, PLACES[1]) == f"/mini-panel/login?company_id={CID}&type=lider_operacion&lugar=alabama"
    assert svc.denied_message("Alabama") == "Este panel es solo para el líder de Alabama"


def test_semana_de_la_empresa():
    assert svc.week_of(date(2026, 11, 5), "sunday") == (date(2026, 11, 1), date(2026, 11, 7))
    assert svc.week_of(date(2026, 11, 1), "sunday") == (date(2026, 11, 1), date(2026, 11, 7))
    assert svc.week_of(date(2026, 11, 7), "sunday") == (date(2026, 11, 1), date(2026, 11, 7))
    assert svc.week_of(date(2026, 11, 5), "monday") == (date(2026, 11, 2), date(2026, 11, 8))
    assert svc.week_of(date(2026, 11, 5), "desconocido") == (date(2026, 11, 1), date(2026, 11, 7))


def test_estados_de_crm():
    people = [{"now": {"state": s}} for s in ("working", "on_break", "to_confirm", "no_shift", "done")]
    assert svc.count_states(people) == {"total": 5, "working": 1, "on_break": 1, "no_shift": 2, "to_confirm": 1}


def test_lider_de_esa_operacion():
    user = SimpleNamespace(settings_json={"mini_panel": {"enabled": True, "type": "lider_operacion", "work_location_id": AL, "employee_id": "e"}})
    assert svc.is_leader_of(user, AL) and not svc.is_leader_of(user, VA)
    user.settings_json["mini_panel"]["enabled"] = False
    assert not svc.is_leader_of(user, AL)
