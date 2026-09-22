"""2026-09-23 security sweep, PASO 1 + PASO 2.

Context: of ~443 endpoints, ~360 across whole modules (hospitality,
employees, inventory, mini_panel_sales, marketplace, shoplink,
company_experience, references_v1, bots, materials, assemblies) have no
auth at all, with no global filter covering them. Nothing is being closed
yet except the one narrow, already-agreed cut (archived companies). PASO 1
is pure measurement:

- app.main._clonexa_auth_audit_middleware logs "AUTH_AUDIT ..." for any
  /api/v1/* request with no valid session, and NEVER changes the response.
- app.main._clonexa_archived_company_guard returns 403 for an archived
  company's data endpoints, but leaves companies.py's own management
  endpoints reachable (so Admin V2 can still see/restore the company), and
  leaves inactive (not archived) companies untouched.

These tests hit the real ASGI app via TestClient (no live DB in this repo),
monkeypatching only the DB-touching leaves (_clonexa_company_is_archived,
_clonexa_has_valid_session, _clonexa_live_company_ids) so the middleware's
own control flow runs for real.
"""
import logging
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main

client = TestClient(app_main.app)

ASADERO_ID = "7625872c-f941-4479-a27b-f8443be953c5"
TIME_MACHINE_ID = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"


def _cid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# PASO 1 helper units
# ---------------------------------------------------------------------------

def test_company_id_extracted_from_a_companies_path_segment():
    class FakeRequest:
        url = type("U", (), {"path": "/api/v1/hospitality/companies/abc-123/orders"})()
        query_params = {}

    assert app_main._clonexa_company_id_from_request(FakeRequest()) == "abc-123"


def test_company_id_extracted_from_a_query_param_when_no_path_segment():
    class FakeRequest:
        url = type("U", (), {"path": "/api/v1/employees"})()
        query_params = {"company_id": "xyz-789"}

    assert app_main._clonexa_company_id_from_request(FakeRequest()) == "xyz-789"


def test_company_id_is_none_when_not_determinable():
    class FakeRequest:
        url = type("U", (), {"path": "/api/v1/health"})()
        query_params = {}

    assert app_main._clonexa_company_id_from_request(FakeRequest()) is None


@pytest.mark.asyncio
async def test_live_company_ids_always_includes_the_two_fixed_ids(monkeypatch):
    async def fake_execute(*args, **kwargs):
        class R:
            def scalars(self_inner):
                class S:
                    def all(self_inner2):
                        return []
                return S()
        return R()

    monkeypatch.setattr(app_main, "_clonexa_live_company_ids_cache", {"ids": None, "at": 0.0})
    fake_db = type("DB", (), {"execute": fake_execute})()
    monkeypatch.setattr(
        app_main, "AsyncSessionLocal",
        lambda: type("Ctx", (), {"__aenter__": AsyncMock(return_value=fake_db), "__aexit__": AsyncMock(return_value=False)})(),
    )

    ids = await app_main._clonexa_live_company_ids()
    assert ASADERO_ID in ids
    assert TIME_MACHINE_ID in ids


def test_audit_origin_prefers_the_token_scope():
    request = type("R", (), {"headers": {}})()
    assert app_main._clonexa_audit_origin(request, "client") == "client"
    assert app_main._clonexa_audit_origin(request, "mini_panel") == "mini_panel"


def test_audit_origin_falls_back_to_referer_for_the_public_qr_page():
    request = type("R", (), {"headers": {"referer": "https://clonexa.app/ordenar?company_id=x"}})()
    assert app_main._clonexa_audit_origin(request, None) == "qr_publico"


def test_audit_origin_is_desconocido_with_no_token_and_no_referer():
    request = type("R", (), {"headers": {}})()
    assert app_main._clonexa_audit_origin(request, None) == "desconocido"


def test_audit_enabled_by_default_and_toggled_by_env_var(monkeypatch):
    monkeypatch.delenv("CLONEXA_AUTH_AUDIT", raising=False)
    assert app_main._clonexa_auth_audit_enabled() is True
    monkeypatch.setenv("CLONEXA_AUTH_AUDIT", "false")
    assert app_main._clonexa_auth_audit_enabled() is False
    monkeypatch.setenv("CLONEXA_AUTH_AUDIT", "0")
    assert app_main._clonexa_auth_audit_enabled() is False
    monkeypatch.setenv("CLONEXA_AUTH_AUDIT", "true")
    assert app_main._clonexa_auth_audit_enabled() is True


# ---------------------------------------------------------------------------
# PASO 1 middleware end to end: never changes the response, only logs, and
# only logs when there is no valid session.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_middleware_does_not_log_when_a_valid_session_exists(monkeypatch, caplog):
    monkeypatch.setattr(app_main, "_clonexa_has_valid_session", AsyncMock(return_value=True))
    monkeypatch.setattr(
        app_main, "AsyncSessionLocal",
        lambda: type("Ctx", (), {"__aenter__": AsyncMock(return_value=object()), "__aexit__": AsyncMock(return_value=False)})(),
    )

    async def call_next(request):
        return object()

    class FakeRequest:
        url = type("U", (), {"path": "/api/v1/companies"})()
        method = "GET"
        headers = {}
        query_params = {}

    with caplog.at_level(logging.INFO, logger="clonexa.auth_audit"):
        await app_main._clonexa_auth_audit_middleware(FakeRequest(), call_next)
    assert "AUTH_AUDIT" not in caplog.text


@pytest.mark.asyncio
async def test_audit_middleware_logs_when_there_is_no_valid_session(monkeypatch, caplog):
    monkeypatch.setattr(app_main, "_clonexa_has_valid_session", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_live_company_ids", AsyncMock(return_value={ASADERO_ID}))
    monkeypatch.setattr(
        app_main, "AsyncSessionLocal",
        lambda: type("Ctx", (), {"__aenter__": AsyncMock(return_value=object()), "__aexit__": AsyncMock(return_value=False)})(),
    )

    async def call_next(request):
        return "UNCHANGED_RESPONSE"

    class FakeRequest:
        url = type("U", (), {"path": f"/api/v1/hospitality/companies/{ASADERO_ID}/orders"})()
        method = "GET"
        headers = {}
        query_params = {}

    with caplog.at_level(logging.INFO, logger="clonexa.auth_audit"):
        response = await app_main._clonexa_auth_audit_middleware(FakeRequest(), call_next)

    assert response == "UNCHANGED_RESPONSE"
    assert "AUTH_AUDIT" in caplog.text
    assert f"company_id={ASADERO_ID}" in caplog.text
    assert "empresa_viva=true" in caplog.text


@pytest.mark.asyncio
async def test_audit_middleware_flags_a_demo_company_as_not_live(monkeypatch, caplog):
    monkeypatch.setattr(app_main, "_clonexa_has_valid_session", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_live_company_ids", AsyncMock(return_value={ASADERO_ID}))
    monkeypatch.setattr(
        app_main, "AsyncSessionLocal",
        lambda: type("Ctx", (), {"__aenter__": AsyncMock(return_value=object()), "__aexit__": AsyncMock(return_value=False)})(),
    )
    demo_id = _cid()

    async def call_next(request):
        return "UNCHANGED_RESPONSE"

    class FakeRequest:
        url = type("U", (), {"path": f"/api/v1/hospitality/companies/{demo_id}/orders"})()
        method = "GET"
        headers = {}
        query_params = {}

    with caplog.at_level(logging.INFO, logger="clonexa.auth_audit"):
        await app_main._clonexa_auth_audit_middleware(FakeRequest(), call_next)
    assert "empresa_viva=false" in caplog.text


@pytest.mark.asyncio
async def test_audit_middleware_skips_non_api_paths_entirely(monkeypatch):
    has_session_check = AsyncMock(return_value=False)
    monkeypatch.setattr(app_main, "_clonexa_has_valid_session", has_session_check)

    async def call_next(request):
        return "PASSTHROUGH"

    class FakeRequest:
        url = type("U", (), {"path": "/client"})()
        method = "GET"
        headers = {}
        query_params = {}

    response = await app_main._clonexa_auth_audit_middleware(FakeRequest(), call_next)
    assert response == "PASSTHROUGH"
    has_session_check.assert_not_called()


@pytest.mark.asyncio
async def test_audit_middleware_disabled_by_env_var_does_nothing(monkeypatch):
    monkeypatch.setenv("CLONEXA_AUTH_AUDIT", "false")
    has_session_check = AsyncMock(return_value=False)
    monkeypatch.setattr(app_main, "_clonexa_has_valid_session", has_session_check)

    async def call_next(request):
        return "PASSTHROUGH"

    class FakeRequest:
        url = type("U", (), {"path": "/api/v1/companies"})()
        method = "GET"
        headers = {}
        query_params = {}

    response = await app_main._clonexa_auth_audit_middleware(FakeRequest(), call_next)
    assert response == "PASSTHROUGH"
    has_session_check.assert_not_called()


@pytest.mark.asyncio
async def test_audit_middleware_never_raises_even_if_its_own_logic_breaks(monkeypatch):
    monkeypatch.setattr(app_main, "_clonexa_has_valid_session", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(
        app_main, "AsyncSessionLocal",
        lambda: type("Ctx", (), {"__aenter__": AsyncMock(return_value=object()), "__aexit__": AsyncMock(return_value=False)})(),
    )

    async def call_next(request):
        return "UNCHANGED_RESPONSE"

    class FakeRequest:
        url = type("U", (), {"path": "/api/v1/companies"})()
        method = "GET"
        headers = {}
        query_params = {}

    response = await app_main._clonexa_auth_audit_middleware(FakeRequest(), call_next)
    assert response == "UNCHANGED_RESPONSE"


# ---------------------------------------------------------------------------
# Middleware never changes a response: the already-protected companies.py
# endpoints must still answer exactly like before this sweep.
# ---------------------------------------------------------------------------

def test_already_protected_endpoints_still_answer_the_same_with_the_sweep_active():
    response = client.get(f"/api/v1/companies/{_cid()}/access-policy")
    assert response.status_code in (401, 403)
    assert response.json()["detail"]


# ---------------------------------------------------------------------------
# PASO 2: archived companies
# ---------------------------------------------------------------------------

def test_company_management_paths_are_exempt_from_the_archived_guard():
    cid = _cid()
    assert app_main._clonexa_is_company_management_path("/api/v1/companies") is True
    assert app_main._clonexa_is_company_management_path(f"/api/v1/companies/{cid}") is True
    assert app_main._clonexa_is_company_management_path(f"/api/v1/companies/{cid}/access-policy") is True
    assert app_main._clonexa_is_company_management_path(f"/api/v1/companies/{cid}/restore") is True
    assert app_main._clonexa_is_company_management_path(f"/api/v1/companies/{cid}/access-sessions/close") is True
    assert app_main._clonexa_is_company_management_path(f"/api/v1/companies/{cid}/access-sessions/abc/close") is True


def test_operational_data_paths_under_companies_are_not_exempt():
    cid = _cid()
    # waiter_ordering.py and company_users.py share the /companies/{id}/...
    # URL shape with companies.py, but are NOT company management.
    assert app_main._clonexa_is_company_management_path(f"/api/v1/companies/{cid}/waiter-ordering/menu") is False
    assert app_main._clonexa_is_company_management_path(f"/api/v1/companies/{cid}/mini-panel-login") is False
    assert app_main._clonexa_is_company_management_path(f"/api/v1/companies/{cid}/orders") is False


def test_non_companies_endpoint_is_never_exempt():
    assert app_main._clonexa_is_company_management_path("/api/v1/employees") is False


def test_archived_guard_blocks_a_data_endpoint_for_an_archived_company(monkeypatch):
    cid = _cid()
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=True))

    response = client.get(f"/api/v1/hospitality/companies/{cid}/orders")
    assert response.status_code == 403
    assert response.json() == {"detail": "Empresa archivada."}


def test_archived_guard_does_not_touch_company_management_endpoints(monkeypatch):
    cid = _cid()
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=True))

    response = client.get(f"/api/v1/companies/{cid}/access-policy")
    # Blocked by the (pre-existing, unrelated) auth requirement, not by the
    # archived guard -- proves the exemption, not just "some 4xx happened".
    assert response.status_code in (401, 403)
    assert response.json() != {"detail": "Empresa archivada."}


def test_archived_guard_lets_a_non_archived_company_through(monkeypatch):
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    called = AsyncMock(return_value=False)
    monkeypatch.setattr(app_main, "_clonexa_has_valid_session", called)

    response = client.get(f"/api/v1/companies/{ASADERO_ID}/access-policy")
    assert response.status_code in (401, 403)
    assert response.json() != {"detail": "Empresa archivada."}


@pytest.mark.asyncio
async def test_archived_check_defaults_to_not_archived_when_company_id_is_unparseable():
    assert await app_main._clonexa_company_is_archived("not-a-uuid") is False


@pytest.mark.asyncio
async def test_archived_check_never_raises_when_the_database_is_unreachable():
    # No live DB in this test environment -- confirms the guard fails open
    # (does not block) rather than raising and 500-ing every request.
    result = await app_main._clonexa_company_is_archived(str(uuid.uuid4()))
    assert result is False
