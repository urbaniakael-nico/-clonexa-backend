"""Parte 0 (todas las empresas): production_v1 y references_v1 exigen sesion.

- Sin sesion: 401 en todas las rutas; usuario de OTRA empresa: 403.
- Admin V2 (cookie), usuario del portal y JWT de mini panel de ESA empresa: pasan.
- Contrato: el bot de Telegram no usa HTTP (bot_flows va a la base y bots.py
  llama production_summary como funcion), el mini panel de cotizaciones y el
  portal ya mandan su sesion, y las descargas CSV ahora van con la sesion.
"""
from __future__ import annotations

import inspect
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.v1.endpoints import production_v1, references_v1

client = TestClient(app_main.app)
CID = str(uuid.uuid4())
WEB = Path("app/web")


@pytest.mark.parametrize("method, path", [
    ("GET", f"/api/v1/production-v1/companies/{CID}/summary"),
    ("GET", f"/api/v1/production-v1/companies/{CID}/closures"),
    ("GET", f"/api/v1/production-v1/companies/{CID}/export.csv"),
    ("POST", f"/api/v1/production-v1/companies/{CID}/references/{CID}/archive"),
    ("GET", f"/api/v1/references-v1/companies/{CID}"),
    ("POST", f"/api/v1/references-v1/companies/{CID}"),
    ("GET", f"/api/v1/references-v1/companies/{CID}/bot-options"),
    ("GET", f"/api/v1/references-v1/companies/{CID}/summary"),
    ("GET", f"/api/v1/references-v1/companies/{CID}/export.csv"),
    ("POST", f"/api/v1/references-v1/companies/{CID}/flow/start-reference"),
    ("POST", f"/api/v1/references-v1/companies/{CID}/flow/switch-reference"),
    ("POST", f"/api/v1/references-v1/companies/{CID}/flow/close-production"),
    ("GET", f"/api/v1/references-v1/companies/{CID}/flow/active-session?employee_id=x"),
    ("DELETE", f"/api/v1/references-v1/companies/{CID}/{CID}"),
])
def test_without_a_session_every_route_answers_401(method, path):
    response = client.request(method, path, json={})
    assert response.status_code == 401, (path, response.status_code, response.text[:200])


def test_every_route_has_the_company_session_dependency():
    for module in (production_v1, references_v1):
        assert module.router.routes
        for route in module.router.routes:
            calls = [d.call for d in route.dependant.dependencies]
            assert module.require_company_session in calls, route.path


@pytest.mark.asyncio
async def test_the_session_must_belong_to_that_company(monkeypatch):
    from app.api import deps
    from app.web import admin_v2_routes

    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    request = SimpleNamespace(cookies={}, headers={})
    company = uuid.uuid4()
    other = SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), role="company_admin")
    own_mini_panel = SimpleNamespace(id=uuid.uuid4(), company_id=company, role="vendedor")
    monkeypatch.setattr(deps, "require_enabled_module", AsyncMock())
    for user, ok in ((other, False), (own_mini_panel, True)):
        monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(return_value=user))
        if ok:
            await production_v1.require_company_session(company, request, "Bearer x", object())
            await references_v1.require_company_session(company, request, "Bearer x", object())
        else:
            for module in (production_v1, references_v1):
                with pytest.raises(HTTPException) as exc:
                    await module.require_company_session(company, request, "Bearer x", object())
                assert exc.value.status_code == 403
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=True))
    await production_v1.require_company_session(company, request, None, object())  # Admin V2


def test_callers_keep_working_contract():
    from app.api.v1.endpoints import bots

    # El bot llama la funcion (no HTTP): la firma no cambio.
    params = inspect.signature(production_v1.production_summary).parameters
    assert {"company_id", "date_from", "date_to", "preset", "view", "db"} <= set(params)
    assert "production_summary(" in inspect.getsource(bots)
    flow = Path("app/services/bot_flows/velvet_references_flow.py").read_text(encoding="utf-8-sig")
    assert "references-v1" not in flow and "httpx" not in flow, "el flujo del bot va directo a la base"
    # Mini panel de cotizaciones y portal: con su sesion.
    mini = (WEB / "mini_panel.js").read_text(encoding="utf-8")
    assert re.search(r"fetch\(`/api/v1/references-v1/companies/\$\{encodeURIComponent\(companyId\)\}`, \{\s*headers: authHeaders\(\),", mini)
    portal = (WEB / "client.js").read_text(encoding="utf-8")
    assert "a.href = cxProdDownloadUrl018E(filters);" not in portal, "la descarga CSV ya no es un enlace sin sesion"
    assert "cxDownloadWithSession056D(cxProdDownloadUrl018E(filters)" in portal
    assert "cxDownloadWithSession056D(`${API}/references-v1/companies/" in portal
    assert "const res = await fetch(url, { headers: authHeaders(), credentials: \"same-origin\" });" in portal
