"""mesero/cocina/caja login must be gated by the waiter_ordering module and
the local-network IP allowlist, and must kick this same user's other active
sessions -- all without touching the other 7 mini panel types' login flow.
Also covers the per-type user-limit enforcement on creation.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import company_users


def _fake_user(panel_type="mesero", company_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        company_id=company_id or uuid.uuid4(),
        email="mesero1@clonexa.local",
        full_name="Mesero Uno",
        role="operator",
        status="active",
        password_hash="hash",
        failed_login_attempts=0,
        settings_json={"mini_panel": {"enabled": True, "type": panel_type, "username": "mesero1"}},
    )


def _patch_happy_login(monkeypatch, company_id, user):
    monkeypatch.setattr(company_users, "_cx_company_or_404_019d", AsyncMock(return_value=SimpleNamespace(id=company_id, name="Asadero")))
    monkeypatch.setattr(company_users, "_cx_find_minipanel_login_user_019d", AsyncMock(return_value=user))
    monkeypatch.setattr(company_users, "verify_password", lambda raw, hashed: True)
    monkeypatch.setattr(company_users, "register_access_session", AsyncMock(return_value="new-session-key"))
    monkeypatch.setattr(company_users, "create_access_token", lambda data, expires_minutes=None: "jwt-token")
    monkeypatch.setattr(company_users, "get_access_token_expire_minutes", lambda: 480)
    monkeypatch.setattr(company_users, "_cx_minipanel_session_payload_019d", AsyncMock(return_value={"ok": True}))


def _db():
    return SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())


@pytest.mark.asyncio
async def test_login_blocked_without_the_waiter_ordering_module(monkeypatch):
    company_id = uuid.uuid4()
    monkeypatch.setattr(
        company_users, "_cx_require_waiter_ordering_module_026k",
        AsyncMock(side_effect=HTTPException(status_code=403, detail="module_not_enabled_for_tenant")),
    )
    monkeypatch.setattr(company_users, "_cx_company_or_404_019d", AsyncMock(return_value=SimpleNamespace(id=company_id)))
    monkeypatch.setattr(
        company_users, "_cx_find_minipanel_login_user_019d",
        AsyncMock(side_effect=AssertionError("must not check credentials before the module gate")),
    )

    payload = company_users.MiniPanelLoginRequest(username="mesero1", password="x", panel_type="mesero")
    request = SimpleNamespace(headers={"x-forwarded-for": "10.0.0.5"}, client=None)

    with pytest.raises(HTTPException) as exc:
        await company_users.mini_panel_login(company_id, payload, request, _db())
    assert exc.value.status_code == 403
    assert exc.value.detail == "module_not_enabled_for_tenant"


@pytest.mark.asyncio
async def test_login_blocked_outside_the_registered_network(monkeypatch):
    company_id = uuid.uuid4()
    monkeypatch.setattr(company_users, "_cx_require_waiter_ordering_module_026k", AsyncMock())
    monkeypatch.setattr(
        company_users, "_cx_require_local_network_026k",
        AsyncMock(side_effect=HTTPException(status_code=403, detail="Conectate al WiFi del restaurante.")),
    )
    monkeypatch.setattr(company_users, "_cx_company_or_404_019d", AsyncMock(return_value=SimpleNamespace(id=company_id)))
    monkeypatch.setattr(
        company_users, "_cx_find_minipanel_login_user_019d",
        AsyncMock(side_effect=AssertionError("must not check credentials before the network gate")),
    )

    payload = company_users.MiniPanelLoginRequest(username="cocina1", password="x", panel_type="cocina")
    request = SimpleNamespace(headers={"x-forwarded-for": "8.8.8.8"}, client=None)

    with pytest.raises(HTTPException) as exc:
        await company_users.mini_panel_login(company_id, payload, request, _db())
    assert exc.value.detail == "Conectate al WiFi del restaurante."


@pytest.mark.asyncio
async def test_login_kicks_this_same_users_other_sessions_only(monkeypatch):
    company_id = uuid.uuid4()
    user = _fake_user("caja", company_id)
    monkeypatch.setattr(company_users, "_cx_require_waiter_ordering_module_026k", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_require_local_network_026k", AsyncMock())
    _patch_happy_login(monkeypatch, company_id, user)
    kick = AsyncMock(return_value=1)
    monkeypatch.setattr(company_users, "close_other_sessions_for_subject", kick)

    payload = company_users.MiniPanelLoginRequest(username="caja1", password="x", panel_type="caja")
    request = SimpleNamespace(headers={"x-forwarded-for": "10.0.0.5"}, client=None)

    result = await company_users.mini_panel_login(company_id, payload, request, _db())

    assert result["access_token"] == "jwt-token"
    kick.assert_awaited_once()
    _, kwargs = kick.await_args
    assert kwargs["subject_id"] == user.id
    assert kwargs["scope"] == "mini_panel"
    assert kwargs["company_id"] == company_id


@pytest.mark.asyncio
async def test_other_panel_types_never_hit_the_waiter_ordering_gates(monkeypatch):
    company_id = uuid.uuid4()
    user = _fake_user("sales", company_id)
    monkeypatch.setattr(
        company_users, "_cx_require_waiter_ordering_module_026k",
        AsyncMock(side_effect=AssertionError("sales login must not check the waiter_ordering module")),
    )
    monkeypatch.setattr(
        company_users, "_cx_require_local_network_026k",
        AsyncMock(side_effect=AssertionError("sales login must not check the local-network IP")),
    )
    kick = AsyncMock(side_effect=AssertionError("sales login must not run the single-session kick"))
    monkeypatch.setattr(company_users, "close_other_sessions_for_subject", kick)
    _patch_happy_login(monkeypatch, company_id, user)

    payload = company_users.MiniPanelLoginRequest(username="vendedor1", password="x", panel_type="sales")
    request = SimpleNamespace(headers={"x-forwarded-for": "8.8.8.8"}, client=None)

    result = await company_users.mini_panel_login(company_id, payload, request, _db())
    assert result["access_token"] == "jwt-token"


# ---------------------------------------------------------------------------
# Per-type creation limits
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_creating_a_cocina_user_past_the_limit_is_rejected(monkeypatch):
    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    employee = SimpleNamespace(id=employee_id, full_name="Chef", role="cocinero", employee_type="cocinero")

    monkeypatch.setattr(company_users, "_cx_employee_or_404_019c", AsyncMock(return_value=employee))
    monkeypatch.setattr(company_users, "_cx_find_minipanel_user_019c", AsyncMock(return_value=None))
    monkeypatch.setattr(company_users, "_cx_require_waiter_ordering_module_026k", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_segment_enabled_031t", lambda settings, panel_type: True)
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_module_settings_026k", AsyncMock(return_value={}))
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_user_limit_026k", AsyncMock(return_value=2))
    monkeypatch.setattr(company_users, "_cx_count_minipanel_users_of_type_026k", AsyncMock(return_value=2))

    payload = company_users.SalesMiniPanelUserCreateRequest(employee_id=employee_id)
    with pytest.raises(HTTPException) as exc:
        await company_users._cx_create_minipanel_user_from_employee_026j(
            company_id=company_id, payload=payload, panel_type="cocina", db=_db(), source="workforce",
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_mesero_limit_is_independent_from_cocina_and_caja(monkeypatch):
    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    employee = SimpleNamespace(id=employee_id, full_name="Ana", role="mesero", employee_type="mesero")

    monkeypatch.setattr(company_users, "_cx_employee_or_404_019c", AsyncMock(return_value=employee))
    monkeypatch.setattr(company_users, "_cx_find_minipanel_user_019c", AsyncMock(return_value=None))
    monkeypatch.setattr(company_users, "_cx_require_waiter_ordering_module_026k", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_segment_enabled_031t", lambda settings, panel_type: True)
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_module_settings_026k", AsyncMock(return_value={}))

    async def fake_limit(db, cid, panel_type):
        return {"mesero": 10, "cocina": 2, "caja": 1}[panel_type]

    async def fake_count(db, cid, panel_type):
        # cocina and caja are already full; mesero has plenty of room.
        return {"mesero": 1, "cocina": 2, "caja": 1}[panel_type]

    monkeypatch.setattr(company_users, "_cx_waiter_ordering_user_limit_026k", fake_limit)
    monkeypatch.setattr(company_users, "_cx_count_minipanel_users_of_type_026k", fake_count)

    db = _db()
    db.add = lambda obj: None
    payload = company_users.SalesMiniPanelUserCreateRequest(employee_id=employee_id)

    result = await company_users._cx_create_minipanel_user_from_employee_026j(
        company_id=company_id, payload=payload, panel_type="mesero", db=db, source="workforce",
    )
    assert result["panel_type"] == "mesero"


# ---------------------------------------------------------------------------
# Mesero/cocina/caja Admin V2 "mini panel segments" (settings.segments):
# off by default, must be explicitly turned on to create a new user for that
# segment. Never blocks an existing user's login (that gate is untouched).
# ---------------------------------------------------------------------------

def test_segment_enabled_helper_defaults_to_false_for_a_brand_new_company():
    assert company_users._cx_waiter_ordering_segment_enabled_031t({}, "mesero") is False
    assert company_users._cx_waiter_ordering_segment_enabled_031t({"segments": {}}, "mesero") is False
    assert company_users._cx_waiter_ordering_segment_enabled_031t(
        {"segments": {"mesero": {"enabled": False}}}, "mesero",
    ) is False


def test_segment_enabled_helper_reads_its_own_type_only():
    settings = {"segments": {"mesero": {"enabled": True}, "cocina": {"enabled": False}}}
    assert company_users._cx_waiter_ordering_segment_enabled_031t(settings, "mesero") is True
    assert company_users._cx_waiter_ordering_segment_enabled_031t(settings, "cocina") is False
    assert company_users._cx_waiter_ordering_segment_enabled_031t(settings, "caja") is False


@pytest.mark.asyncio
async def test_creating_a_mesero_user_is_rejected_when_the_segment_is_off(monkeypatch):
    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    employee = SimpleNamespace(id=employee_id, full_name="Ana", role="mesero", employee_type="mesero")

    monkeypatch.setattr(company_users, "_cx_employee_or_404_019c", AsyncMock(return_value=employee))
    monkeypatch.setattr(company_users, "_cx_find_minipanel_user_019c", AsyncMock(return_value=None))
    monkeypatch.setattr(company_users, "_cx_require_waiter_ordering_module_026k", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_waiter_ordering_module_settings_026k", AsyncMock(return_value={"segments": {}}))

    payload = company_users.SalesMiniPanelUserCreateRequest(employee_id=employee_id)
    with pytest.raises(HTTPException) as exc:
        await company_users._cx_create_minipanel_user_from_employee_026j(
            company_id=company_id, payload=payload, panel_type="mesero", db=_db(), source="workforce",
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_creating_a_mesero_user_succeeds_once_the_segment_is_on(monkeypatch):
    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    employee = SimpleNamespace(id=employee_id, full_name="Ana", role="mesero", employee_type="mesero")

    monkeypatch.setattr(company_users, "_cx_employee_or_404_019c", AsyncMock(return_value=employee))
    monkeypatch.setattr(company_users, "_cx_find_minipanel_user_019c", AsyncMock(return_value=None))
    monkeypatch.setattr(company_users, "_cx_require_waiter_ordering_module_026k", AsyncMock())
    monkeypatch.setattr(
        company_users, "_cx_waiter_ordering_module_settings_026k",
        AsyncMock(return_value={"segments": {"mesero": {"enabled": True}}, "waiter_user_limit": 5}),
    )
    monkeypatch.setattr(company_users, "_cx_count_minipanel_users_of_type_026k", AsyncMock(return_value=0))

    db = _db()
    db.add = lambda obj: None
    payload = company_users.SalesMiniPanelUserCreateRequest(employee_id=employee_id)

    result = await company_users._cx_create_minipanel_user_from_employee_026j(
        company_id=company_id, payload=payload, panel_type="mesero", db=db, source="workforce",
    )
    assert result["panel_type"] == "mesero"
