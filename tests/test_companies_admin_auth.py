"""SECURITY (2026-09-22): companies.py had zero authentication on its whole
admin surface -- anyone who knew a company_id (visible in the portal's own
URL) could read or rewrite that company's IP allowlist, session policy,
active sessions, status (including archiving/deleting it), branding, and
more. Flagged specifically for /access-policy; this file locks down every
endpoint in companies.py that has no legitimate non-admin caller, and
documents (without touching) the one that still does.

Includes two follow-up fixes:
- GET /companies (list ALL companies, no filter) had no auth either, and
  every tenant's /client portal leaned on that to boot (client.js's
  loadByCompanyId listed every company just to find its own row by id) --
  which also meant any company could see every other company's
  name/slug/status/settings. list_companies is now admin-only; client.js
  calls the scoped GET /companies/{id} instead, which accepts either an
  Admin V2 session or that company's own logged-in staff.
- GET/PUT /{id}/client-settings also had no auth: client.js's
  cxFetchSettings/cxSavePayrollHours (a separate IIFE with no access to the
  main one's authToken()) sent no Authorization header at all, so anyone
  could read or rewrite a company's payroll overtime hours with no
  credentials. Both ends fixed together: client.js now sends its session
  token there too (cxAuthHeaders), GET accepts any of that company's
  logged-in staff, and PUT (payroll hours is a company-wide rule) requires
  an admin session specifically.

These tests hit the real ASGI app with fastapi.testclient.TestClient and no
credentials at all, so they prove the fix at the actual HTTP boundary -- not
just that some Python helper exists. The protected endpoints must reject the
request before ever touching the database (this repo has no test database),
so a passing 401/403 here also proves the auth dependency runs first.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.v1.endpoints import companies

client = TestClient(app_main.app)
API = "/api/v1/companies"


def _cid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Every one of these must 401/403 with no Admin V2 session and no bearer
# token -- and must do so without needing a live database connection.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("get", API),
        ("get", f"{API}/{{cid}}"),
        ("patch", f"{API}/{{cid}}"),
        ("patch", f"{API}/{{cid}}/status"),
        ("patch", f"{API}/{{cid}}/archive"),
        ("patch", f"{API}/{{cid}}/restore"),
        ("delete", f"{API}/{{cid}}"),
        ("post", f"{API}/{{cid}}/operational-reset"),
        ("get", f"{API}/{{cid}}/access-policy"),
        ("put", f"{API}/{{cid}}/access-policy"),
        ("get", f"{API}/{{cid}}/session-policy"),
        ("put", f"{API}/{{cid}}/session-policy"),
        ("get", f"{API}/{{cid}}/access-sessions"),
        ("post", f"{API}/{{cid}}/access-sessions/close"),
        ("post", f"{API}/{{cid}}/access-sessions/fake-session-key/close"),
        ("get", f"{API}/{{cid}}/experience"),
        ("put", f"{API}/{{cid}}/experience/branding"),
        ("put", f"{API}/{{cid}}/branding"),
        ("get", f"{API}/{{cid}}/client-settings"),
        ("put", f"{API}/{{cid}}/client-settings"),
    ],
)
def test_admin_endpoint_rejects_a_request_with_no_credentials(method, path):
    url = path.format(cid=_cid())
    response = client.request(method.upper(), url, json={})
    assert response.status_code in (401, 403), f"{method.upper()} {path} -> {response.status_code}: {response.text}"


def test_create_company_rejects_a_request_with_no_credentials():
    response = client.post(API, json={"name": "Espia SA", "slug": f"espia-{uuid.uuid4().hex[:8]}"})
    assert response.status_code in (401, 403)


def test_access_policy_body_never_reaches_the_database_without_auth():
    # The specific bug reported: PUT /access-policy let anyone rewrite the
    # IP allowlist. Confirm the malicious payload is rejected outright.
    response = client.put(
        f"{API}/{_cid()}/access-policy",
        json={"enabled": True, "scopes": {"mini_panel": {"enabled": True, "allowed_ips": ["6.6.6.6"]}}},
    )
    assert response.status_code in (401, 403)
    assert response.json()["detail"]


def test_a_stale_or_forged_admin_v2_cookie_is_also_rejected():
    forged_client = TestClient(app_main.app, cookies={"clonexa_admin_v2_session": "not-a-real-signed-session"})
    response = forged_client.get(f"{API}/{_cid()}/access-policy")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Endpoints deliberately left open (real, confirmed non-admin callers with
# no compatible auth today) -- proven here by asserting the route has no
# admin/tenant dependency wired in, so a future refactor can't silently
# "fix" one without updating this test (and the code comment explaining
# why) at the same time. See the module docstring and code comments for the
# reasoning on each.
# ---------------------------------------------------------------------------

def _dependant_names(route):
    return {dep.call.__name__ for dep in route.dependant.dependencies if dep.call}


def _route(path, method="GET"):
    for r in app_main.app.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set()):
            return r
    raise AssertionError(f"route not found: {method} {path}")


def test_get_company_branding_stays_open_the_public_qr_page_depends_on_it():
    route = _route("/api/v1/companies/{company_id}/branding", "GET")
    names = _dependant_names(route)
    assert "require_admin_v2_api_session" not in names
    assert "require_admin_v2_or_tenant_company_user" not in names
    assert "require_company_user_admin_access" not in names


def test_client_settings_get_is_lenient_any_tenant_staff_put_is_admin_only():
    get_route = _route("/api/v1/companies/{company_id}/client-settings", "GET")
    assert "require_admin_v2_or_tenant_company_user" in _dependant_names(get_route)

    put_route = _route("/api/v1/companies/{company_id}/client-settings", "PUT")
    put_names = _dependant_names(put_route)
    assert "require_company_user_admin_access" in put_names
    # Stricter than the GET on purpose (payroll hours is a company-wide rule).
    assert "require_admin_v2_or_tenant_company_user" not in put_names


def test_list_companies_is_now_admin_only():
    route = _route("/api/v1/companies", "GET")
    assert "require_admin_v2_api_session" in _dependant_names(route)


def test_get_company_accepts_admin_v2_or_tenant_not_admin_only():
    route = _route("/api/v1/companies/{company_id}", "GET")
    names = _dependant_names(route)
    assert "require_admin_v2_or_tenant_company_user" in names
    assert "require_admin_v2_api_session" not in names


# ---------------------------------------------------------------------------
# require_admin_v2_or_tenant_company_user: Admin V2 short-circuits; otherwise
# falls through to a normal tenant-scoped company_user check (any role, not
# just admin roles -- viewing your own company's basic profile shouldn't
# require being that company's admin).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dual_check_short_circuits_on_an_active_admin_v2_session(monkeypatch):
    monkeypatch.setattr(companies, "require_company_user_for_tenant", AsyncMock(side_effect=AssertionError("must not check tenant auth when Admin V2 is active")))

    async def fake_admin_v2_routes_active(request, db):
        return True

    import app.web.admin_v2_routes as admin_v2_routes
    monkeypatch.setattr(admin_v2_routes, "_active_session", fake_admin_v2_routes_active)

    company_id = uuid.uuid4()
    request = SimpleNamespace(headers={}, cookies={}, client=None)
    await companies.require_admin_v2_or_tenant_company_user(company_id, request, None, SimpleNamespace())


@pytest.mark.asyncio
async def test_dual_check_falls_back_to_tenant_company_user(monkeypatch):
    import app.web.admin_v2_routes as admin_v2_routes

    async def fake_inactive(request, db):
        return False

    monkeypatch.setattr(admin_v2_routes, "_active_session", fake_inactive)
    tenant_check = AsyncMock()
    monkeypatch.setattr(companies, "require_company_user_for_tenant", tenant_check)

    company_id = uuid.uuid4()
    request = SimpleNamespace(headers={}, cookies={}, client=None)
    await companies.require_admin_v2_or_tenant_company_user(company_id, request, "Bearer abc", SimpleNamespace())

    tenant_check.assert_awaited_once()
    args, kwargs = tenant_check.await_args
    assert args[2] == company_id
    assert kwargs.get("allowed_roles") is None  # any authenticated staff of that company, not just admins


# ---------------------------------------------------------------------------
# Saving payroll hours (and reading client-settings) still works end to end
# with a valid session -- only the "no credentials at all" path changed.
# ---------------------------------------------------------------------------

def _fake_company(company_id):
    return SimpleNamespace(id=company_id, settings_json={}, timezone="America/Bogota")


@pytest.mark.asyncio
async def test_get_client_settings_still_works_with_a_valid_session(monkeypatch):
    company_id = uuid.uuid4()
    monkeypatch.setattr(companies, "_get_company_or_404", AsyncMock(return_value=_fake_company(company_id)))

    result = await companies.get_company_client_settings(company_id, db=SimpleNamespace(), _actor=None)

    assert result["company_id"] == str(company_id)
    assert result["payroll_regular_hours_limit"] == 48  # default, nothing saved yet


@pytest.mark.asyncio
async def test_save_payroll_hours_still_works_with_a_valid_admin_session(monkeypatch):
    company_id = uuid.uuid4()
    company = _fake_company(company_id)
    monkeypatch.setattr(companies, "_get_company_or_404", AsyncMock(return_value=company))
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    payload = companies.CompanyClientSettingsRequest(payroll_regular_hours_limit=44, payroll={"ordinary_hours_limit": 44})
    result = await companies.update_company_client_settings(company_id, payload, db=db, _admin=None)

    assert result["payroll_regular_hours_limit"] == 44
    db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# client.js: the frontend sides of both fixes.
# ---------------------------------------------------------------------------

def test_client_js_no_longer_lists_every_company_to_boot_its_own_dashboard():
    from pathlib import Path

    source = Path("app/web/client.js").read_text(encoding="utf-8")
    body = source.split("async function loadByCompanyId", 1)[1].split("\n  async function ", 1)[0]
    assert 'api("/companies")' not in body
    assert "api(`/companies/${encodeURIComponent(companyId)}`)" in body


def test_client_js_payroll_settings_module_now_sends_the_session_token():
    from pathlib import Path

    source = Path("app/web/client.js").read_text(encoding="utf-8")
    start = source.index("CX_017I_PAYROLL_SETTINGS_FINAL_START")
    stop = source.index("CX_017I_PAYROLL_SETTINGS_FINAL_END", start)
    module = source[start:stop]

    assert "function cxAuthHeaders" in module
    # Both fetch calls in this module must go through cxAuthHeaders now.
    fetch_calls = [line for line in module.splitlines() if "fetch(`${API}" in line]
    assert len(fetch_calls) == 2
    assert 'headers: { "Accept": "application/json" }' not in module
    assert module.count("cxAuthHeaders(") >= 2
