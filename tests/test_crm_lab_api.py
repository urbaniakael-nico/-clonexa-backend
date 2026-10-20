"""CRM VELVET-LAB: las rutas exigen sesion en el servidor desde el primer dia.

- Tableta: solo el JWT de mini panel crm_lab de ESA empresa (o Admin V2); otro
  tipo de mini panel 403, otra empresa 403, sin token 401, interruptor apagado 404.
- PIN: solo dueno o admin (o Admin V2).
- Mini paneles: crm_lab es un tipo valido con su nombre y su ingreso exige el interruptor.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import company_users as cu
from app.api.v1.endpoints import crm_lab as api
from app.services import crm_lab as svc
from app.services.auth_service import create_access_token

CID = uuid.uuid4()


def request():
    return SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4"), cookies={})


def patch(monkeypatch, *, admin=False, user_company=CID, on=True):
    import app.services.auth_service as auth
    import app.web.admin_v2_routes as admin_routes

    monkeypatch.setattr(admin_routes, "_active_session", AsyncMock(return_value=admin))
    monkeypatch.setattr(auth, "get_current_company_user", AsyncMock(return_value=SimpleNamespace(company_id=user_company, full_name="CRM VELVET-LAB", email="x")))
    monkeypatch.setattr(svc, "is_on", AsyncMock(return_value=on))


def token(panel_type="crm_lab", scope="mini_panel"):
    return "Bearer " + create_access_token({"sub": "u", "company_id": str(CID), "scope": scope, "panel_type": panel_type, "sid": "s"}, expires_minutes=5)


@pytest.mark.asyncio
async def test_tableta_con_el_mini_panel_crm_lab_de_esa_empresa(monkeypatch):
    patch(monkeypatch)
    who = await api.panel(CID, request(), token(), db=None)
    assert who["name"] == "CRM VELVET-LAB"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["sin_token", "otro_panel", "portal", "otra_empresa"])
async def test_tableta_rechaza(monkeypatch, case):
    patch(monkeypatch, user_company=uuid.uuid4() if case == "otra_empresa" else CID)
    auth = {"sin_token": None, "otro_panel": token("mesero"), "portal": token("", scope="company"), "otra_empresa": token()}[case]
    with pytest.raises(HTTPException) as e:
        await api.panel(CID, request(), auth, db=None)
    assert e.value.status_code == (401 if case == "sin_token" else 403)


@pytest.mark.asyncio
async def test_interruptor_apagado_404(monkeypatch):
    patch(monkeypatch, on=False)
    with pytest.raises(HTTPException) as e:
        await api.panel(CID, request(), token(), db=None)
    assert e.value.status_code == 404
    patch(monkeypatch, admin=True, on=False)
    with pytest.raises(HTTPException) as e:
        await api.panel(CID, request(), None, db=None)
    assert e.value.status_code == 404, "ni Admin V2 lo ve apagado"


@pytest.mark.asyncio
async def test_pin_solo_dueno_o_admin(monkeypatch):
    import app.api.v1.endpoints.companies as companies

    patch(monkeypatch)
    monkeypatch.setattr(companies, "require_admin_v2_or_tenant_company_admin", AsyncMock(side_effect=HTTPException(status_code=403, detail="role_not_allowed")))
    with pytest.raises(HTTPException) as e:
        await api.owner(CID, request(), token(), db=None)
    assert e.value.status_code == 403, "el mini panel del CRM no asigna PIN"
    monkeypatch.setattr(companies, "require_admin_v2_or_tenant_company_admin", AsyncMock(return_value=None))
    assert (await api.owner(CID, request(), "Bearer x", db=None))["name"] == "CRM VELVET-LAB"


def test_todas_las_rutas_exigen_sesion():
    deps = {r.path: [d.call for d in r.dependant.dependencies] for r in api.router.routes}
    for path, calls in deps.items():
        assert api.panel in calls or api.owner in calls, f"{path} sin sesion"
    for path in ("/companies/{company_id}/pins", "/companies/{company_id}/employees/{employee_id}/pin", "/companies/{company_id}/panel-user"):
        assert api.owner in deps[path], f"{path}: solo dueno o admin"


def test_crm_lab_es_un_tipo_de_mini_panel():
    for alias in ("crm_lab", "crmlab", "crm-lab", "velvet_lab", "CRM_LAB"):
        assert cu._cx_panel_type_019d(alias) == "crm_lab"
    assert cu._cx_minipanel_type_label_019d("crm_lab") == "CRM VELVET-LAB"
    assert "crm_lab" in cu.MINI_PANEL_ALLOWED_TYPES_019C
    assert "crm_lab" not in cu.WAITER_ORDERING_PANEL_TYPES_026K


@pytest.mark.asyncio
async def test_ingreso_del_crm_exige_el_interruptor(monkeypatch):
    monkeypatch.setattr(cu, "_cx_company_or_404_019d", AsyncMock(return_value=SimpleNamespace(id=CID)))
    monkeypatch.setattr(svc, "is_on", AsyncMock(return_value=False))
    payload = cu.MiniPanelLoginRequest(username="crm-velvet-lab", password="x", panel_type="crm_lab")
    with pytest.raises(HTTPException) as e:
        await cu.mini_panel_login(CID, payload, request(), db=None)
    assert e.value.status_code == 403


def test_link_del_panel():
    assert api._link(CID) == f"/mini-panel/login?company_id={CID}&type=crm_lab"


@pytest.mark.asyncio
async def test_tema_del_portal_para_el_crm(monkeypatch):
    """056K: sin marca publicada, la marca guardada de la empresa (Velvet: holografico,
    fondo aqua, principal morado); el fondo es el mismo que arma el portal."""
    import app.api.v1.endpoints.companies as companies
    from app.services import brand_store, portal_base_css

    api._THEME.clear()
    velvet = {"primary_color": "#a600ff", "secondary_color": "#8cff00", "background_color": "#00ffe1", "text_color": "#000000",
              "background_style": "holografico", "card_style": "glass_premium", "font_family": "Sora", "theme_mode": "dark"}
    monkeypatch.setattr(brand_store, "published_tokens", AsyncMock(return_value=None))
    monkeypatch.setattr(companies, "_get_company_or_404", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(companies, "_read_company_branding", lambda c: velvet)
    out = await api.theme(None, CID)
    assert out["primary"] == "#a600ff" and out["bg"] == "#00ffe1" and out["secondary"] == "#8cff00"
    assert out["background"].endswith("linear-gradient(135deg, #00ffe1, #a600ff)")
    from app.services import brand_theme
    assert out["background"] == " ".join(portal_base_css.branding_background(brand_theme.normalize_branding(velvet)).split())
    assert out["font"].startswith("Sora")
    api._THEME.clear()
