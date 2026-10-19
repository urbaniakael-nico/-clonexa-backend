"""056I (todas las empresas): sesiones del portal iguales en todas las rutas.

- /mini-panel-quotes ya no deja pasar llamadas sin sesion: 401 sin sesion, 403 otra empresa.
- La vista previa "Entrar como empresa" (cookie firmada por Admin V2) vale SOLO para
  su empresa, en production_v1, references_v1, mini_panel_quotes, production_v2,
  quotes_v2 y el dueno de crm_lab; para otra empresa no abre nada.
- JWT de mini panel o del portal de ESA empresa: pasa.
- Contrato: el portal y mini_panel.js mandan su sesion a /mini-panel-quotes y el PDF
  se baja con la sesion (no un enlace sin sesion); Produccion v2 y Cotizaciones v2 se
  montan con authToken del mismo bloque de client.js (056G/056H usaban
  cxReportsToken053C de otro bloque: ReferenceError y pantalla en blanco).
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.v1.endpoints import mini_panel_quotes, production_v1, references_v1
from app.web import admin_v2_routes

client = TestClient(app_main.app)
CID = str(uuid.uuid4())
WEB = Path("app/web")


@pytest.mark.parametrize("method, path", [
    ("GET", f"/api/v1/mini-panel-quotes/companies/{CID}?panel_type=client"),
    ("GET", f"/api/v1/mini-panel-quotes/companies/{CID}/summary?panel_type=all"),
    ("POST", f"/api/v1/mini-panel-quotes/companies/{CID}?panel_type=client"),
    ("GET", f"/api/v1/mini-panel-quotes/companies/{CID}/{CID}?panel_type=client"),
    ("PATCH", f"/api/v1/mini-panel-quotes/companies/{CID}/{CID}?panel_type=client"),
    ("POST", f"/api/v1/mini-panel-quotes/companies/{CID}/{CID}/archive?panel_type=client"),
    ("POST", f"/api/v1/mini-panel-quotes/companies/{CID}/{CID}/convert?panel_type=client"),
    ("GET", f"/api/v1/mini-panel-quotes/companies/{CID}/{CID}/pdf?panel_type=client"),
])
def test_mini_panel_quotes_without_a_session_answers_401(method, path):
    response = client.request(method, path, json={"client_name": "x", "items": [{"description": "x"}]})
    assert response.status_code == 401, (path, response.status_code, response.text[:200])


def test_every_quotes_route_requires_the_session():
    assert mini_panel_quotes.router.routes
    for route in mini_panel_quotes.router.routes:
        calls = [d.call for d in route.dependant.dependencies]
        assert mini_panel_quotes.require_quotes_session in calls, route.path


def _request_with_preview(company_id) -> SimpleNamespace:
    token = admin_v2_routes._create_company_preview_token(str(company_id))
    return SimpleNamespace(cookies={admin_v2_routes.ADMIN_V2_CLIENT_PREVIEW_COOKIE: token}, headers={}, client=None)


@pytest.mark.asyncio
async def test_preview_cookie_opens_only_its_company(monkeypatch):
    from app.api import deps
    from app.api.v1.endpoints import crm_lab, production_v2, quotes_v2
    from app.services import crm_lab as crm_svc
    from app.services import production_v2 as prod_svc
    from app.services import quotes_v2 as quotes_svc

    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    for svc in (prod_svc, quotes_svc, crm_svc):
        monkeypatch.setattr(svc, "is_on", AsyncMock(return_value=True))
    company, other = uuid.uuid4(), uuid.uuid4()
    request = _request_with_preview(company)

    await production_v1.require_company_session(company, request, None, object())
    await references_v1.require_company_session(company, request, None, object())
    await mini_panel_quotes.require_quotes_session(company, request, None, object())
    await production_v2.owner(company, request, None, object())
    await quotes_v2.owner(company, request, None, object())
    assert (await crm_lab.owner(company, request, None, object())) == {"name": "Admin V2"}

    # La misma cookie no abre otra empresa: cae a la sesion por token, que no hay.
    monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(side_effect=HTTPException(status_code=401, detail="no_session")))
    for guard in (production_v1.require_company_session, references_v1.require_company_session, mini_panel_quotes.require_quotes_session,
                  production_v2.owner, quotes_v2.owner):
        with pytest.raises(HTTPException) as exc:
            await guard(other, request, None, object())
        assert exc.value.status_code == 401, guard

    # Cookie vencida o alterada: no vale.
    bad = SimpleNamespace(cookies={admin_v2_routes.ADMIN_V2_CLIENT_PREVIEW_COOKIE: request.cookies[admin_v2_routes.ADMIN_V2_CLIENT_PREVIEW_COOKIE] + "x"}, headers={})
    with pytest.raises(HTTPException):
        await mini_panel_quotes.require_quotes_session(company, bad, None, object())


@pytest.mark.asyncio
async def test_quotes_session_mini_panel_and_portal_tokens(monkeypatch):
    from app.api import deps

    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    monkeypatch.setattr(deps, "require_enabled_module", AsyncMock())
    request = SimpleNamespace(cookies={}, headers={})
    company = uuid.uuid4()
    own = SimpleNamespace(id=uuid.uuid4(), company_id=company, role="vendedor")
    foreign = SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), role="company_admin")
    monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(return_value=own))
    await mini_panel_quotes.require_quotes_session(company, request, "Bearer mini-panel", object())
    monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(return_value=foreign))
    with pytest.raises(HTTPException) as exc:
        await mini_panel_quotes.require_quotes_session(company, request, "Bearer otra", object())
    assert exc.value.status_code == 403
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=True))
    await mini_panel_quotes.require_quotes_session(company, request, None, object())  # Admin V2 (consola)


def test_callers_send_their_session_contract():
    portal = (WEB / "client.js").read_text(encoding="utf-8")
    universal = portal[portal.index("async function cxUniversalApi021D"):]
    universal = universal[:universal.index("\n  }\n")]
    assert "credentials: \"same-origin\"" in universal and "headers: authHeaders({" in universal
    assert not re.search(r"window\.open\(`\$\{API\}/mini-panel-quotes", portal), "el PDF ya no se abre sin sesion"
    assert 'data-client-quote-pdf="${h(quote.id)}" data-document-type="${h(flow.documentType)}" data-pdf-url="${h(pdfUrl)}"' in portal, "el PDF del asistente se baja con la sesion"
    assert portal.count("cxDownloadWithSession056D(") >= 4
    mini = (WEB / "mini_panel.js").read_text(encoding="utf-8")
    assert re.search(r"async function quotesApi021A[\s\S]{0,400}\.\.\.authHeaders\(\)", mini), "el mini panel de cotizaciones manda su JWT"


def test_v2_screens_mount_with_the_token_of_their_own_block():
    portal = (WEB / "client.js").read_text(encoding="utf-8")
    main_block_end = portal.index("\n})();\n")  # primer bloque (IIFE) de client.js
    main = portal[:main_block_end]
    block = main[main.index("CLONEXA_056I_V2_MOUNT_START"):main.index("CLONEXA_056I_V2_MOUNT_END")]
    assert "token: cxReportsToken053C" not in block
    assert "token: authToken" in block and "function authToken()" in main
    assert "data-cx-v2-retry" in block and "Reintentar" in block
    # Todo lo que llama el bloque existe en el mismo bloque principal (no en otro IIFE).
    called = set(re.findall(r"(?<![\w.$])([a-zA-Z_$][\w$]*)\(", block))
    builtin = {"if", "for", "while", "catch", "function", "return", "String", "Promise", "Error", "resolve", "reject", "attempt", "host", "await", "async",
               "cxT056I", "cxV2Load056I", "cxV2Mount056I", "cxV2ErrorText056I", "cxProductionV2On056G", "cxProductionV2Mount056G", "cxQuotesV2On056H",
               "cxQuotesV2Mount056H", "retry", "test"}
    for name in sorted(called - builtin):
        assert re.search(rf"(function\s+{re.escape(name)}\s*\(|(const|let|var)\s+{re.escape(name)}\s*=)", main), f"{name} no existe en el bloque principal"
