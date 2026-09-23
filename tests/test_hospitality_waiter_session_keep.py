"""Mesero panel must stay logged in the whole shift.

- /mini-panel-refresh renews the token (same session id) only while the
  shift is open and the session row is still active; never for a closed
  shift, a kicked session or a non waiter-ordering panel.
- A re-login from the SAME device must not kick that device's own open
  panel; only a login from another device does.
- The company-wide mini panel cap (replace_oldest) never evicts nor counts
  mesero/cocina/caja sessions.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import company_users
from app.services import access_sessions


COMPANY_ID = uuid.uuid4()


def _user(panel_type="mesero"):
    return SimpleNamespace(
        id=uuid.uuid4(), company_id=COMPANY_ID, email="m@x", full_name="Laura", role="mesero",
        status="active", password_hash="h", failed_login_attempts=0,
        settings_json={"mini_panel": {"enabled": True, "type": panel_type, "username": "laura"}},
    )


def _patch_refresh(monkeypatch, user, claims, open_shift=True):
    monkeypatch.setattr(company_users, "_cx_require_waiter_ordering_module_026k", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_require_local_network_026k", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_mp_auth_context_019f", AsyncMock(return_value=(SimpleNamespace(), user, {})))
    monkeypatch.setattr(company_users, "decode_access_token", lambda token: claims)
    monkeypatch.setattr(
        company_users, "_cx_mp_fetch_open_session_019f",
        AsyncMock(return_value={"status": "active"} if open_shift else None),
    )
    issued = []

    def create(data, expires_minutes=None):
        issued.append((data, expires_minutes))
        return "renewed-jwt"

    monkeypatch.setattr(company_users, "create_access_token", create)
    monkeypatch.setattr(company_users, "get_access_token_expire_minutes", lambda: 480)
    return issued


REQUEST = SimpleNamespace(headers={"x-forwarded-for": "10.0.0.5"}, client=None)


@pytest.mark.asyncio
async def test_refresh_renews_the_token_keeping_the_same_session_while_the_shift_is_open(monkeypatch):
    user = _user()
    claims = {"scope": "mini_panel", "panel_type": "mesero", "sid": "session-abc"}
    issued = _patch_refresh(monkeypatch, user, claims)

    result = await company_users.mini_panel_refresh_044a(COMPANY_ID, "mesero", REQUEST, "Bearer old", db=SimpleNamespace())

    assert result["access_token"] == "renewed-jwt"
    assert result["expires_in"] == 480 * 60
    data, minutes = issued[0]
    assert data["sid"] == "session-abc"          # same session: single-device rule intact
    assert data["user_id"] == str(user.id)
    assert data["panel_type"] == "mesero"
    assert minutes == 480


@pytest.mark.asyncio
async def test_refresh_is_refused_once_the_shift_is_closed(monkeypatch):
    issued = _patch_refresh(monkeypatch, _user(), {"scope": "mini_panel", "panel_type": "mesero", "sid": "s"}, open_shift=False)
    with pytest.raises(HTTPException) as exc:
        await company_users.mini_panel_refresh_044a(COMPANY_ID, "mesero", REQUEST, "Bearer old", db=SimpleNamespace())
    assert exc.value.status_code == 409
    assert issued == []


@pytest.mark.asyncio
async def test_a_kicked_or_expired_session_can_never_be_renewed(monkeypatch):
    _patch_refresh(monkeypatch, _user(), {"scope": "mini_panel", "panel_type": "mesero", "sid": "s"})
    monkeypatch.setattr(
        company_users, "_cx_mp_auth_context_019f",
        AsyncMock(side_effect=HTTPException(status_code=401, detail="Tu sesion se abrio en otro dispositivo.")),
    )
    with pytest.raises(HTTPException) as exc:
        await company_users.mini_panel_refresh_044a(COMPANY_ID, "mesero", REQUEST, "Bearer old", db=SimpleNamespace())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_a_token_for_another_panel(monkeypatch):
    _patch_refresh(monkeypatch, _user(), {"scope": "mini_panel", "panel_type": "cocina", "sid": "s"})
    with pytest.raises(HTTPException) as exc:
        await company_users.mini_panel_refresh_044a(COMPANY_ID, "mesero", REQUEST, "Bearer old", db=SimpleNamespace())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_does_not_exist_for_other_mini_panel_types(monkeypatch):
    _patch_refresh(monkeypatch, _user("sales"), {"scope": "mini_panel", "panel_type": "sales", "sid": "s"})
    with pytest.raises(HTTPException) as exc:
        await company_users.mini_panel_refresh_044a(COMPANY_ID, "sales", REQUEST, "Bearer old", db=SimpleNamespace())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_refresh_without_a_token_is_rejected_by_the_real_auth_context():
    with pytest.raises(HTTPException) as exc:
        await company_users._cx_mp_auth_context_019f(SimpleNamespace(), COMPANY_ID, "mesero", None)
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Same device vs another device
# ---------------------------------------------------------------------------

def _patch_login(monkeypatch, user):
    monkeypatch.setattr(company_users, "_cx_require_waiter_ordering_module_026k", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_require_local_network_026k", AsyncMock())
    monkeypatch.setattr(company_users, "_cx_company_or_404_019d", AsyncMock(return_value=SimpleNamespace(id=COMPANY_ID)))
    monkeypatch.setattr(company_users, "_cx_find_minipanel_login_user_019d", AsyncMock(return_value=user))
    monkeypatch.setattr(company_users, "verify_password", lambda raw, hashed: True)
    register = AsyncMock(return_value="new-session")
    monkeypatch.setattr(company_users, "register_access_session", register)
    monkeypatch.setattr(company_users, "create_access_token", lambda data, expires_minutes=None: "jwt")
    monkeypatch.setattr(company_users, "get_access_token_expire_minutes", lambda: 480)
    monkeypatch.setattr(company_users, "_cx_minipanel_session_payload_019d", AsyncMock(return_value={"ok": True}))
    kick = AsyncMock(return_value=0)
    monkeypatch.setattr(company_users, "close_other_sessions_for_subject", kick)
    return register, kick


@pytest.mark.asyncio
async def test_login_sends_the_device_id_so_the_same_phone_is_not_kicked(monkeypatch):
    register, kick = _patch_login(monkeypatch, _user())
    payload = company_users.MiniPanelLoginRequest(username="laura", password="x", panel_type="mesero", device_id="dabc123456789")

    await company_users.mini_panel_login(COMPANY_ID, payload, REQUEST, SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock()))

    assert kick.await_args.kwargs["keep_device_id"] == "dabc123456789"
    assert register.await_args.kwargs["metadata"] == {"panel_type": "mesero", "device_id": "dabc123456789"}


@pytest.mark.asyncio
async def test_login_without_or_with_a_garbage_device_id_kicks_every_other_session(monkeypatch):
    for bad in (None, "x", "'; DROP TABLE--", "a" * 200):
        register, kick = _patch_login(monkeypatch, _user())
        payload = company_users.MiniPanelLoginRequest(username="laura", password="x", panel_type="mesero", device_id=bad)
        await company_users.mini_panel_login(COMPANY_ID, payload, REQUEST, SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock()))
        assert kick.await_args.kwargs["keep_device_id"] is None
        assert register.await_args.kwargs["metadata"] == {"panel_type": "mesero"}


@pytest.mark.asyncio
async def test_close_other_sessions_spares_the_same_device_only(monkeypatch):
    monkeypatch.setattr(access_sessions, "ensure_access_sessions_storage", AsyncMock())
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(rowcount=1)), commit=AsyncMock())
    await access_sessions.close_other_sessions_for_subject(
        db, company_id=COMPANY_ID, scope="mini_panel", subject_id=uuid.uuid4(), keep_device_id="dabc123456789",
    )
    statement = str(db.execute.await_args.args[0])
    params = db.execute.await_args.args[1]
    assert "metadata_json->>'device_id'" in statement
    assert params["device_id"] == "dabc123456789"
    assert "subject_id = CAST(:subject_id AS uuid)" in statement


@pytest.mark.asyncio
async def test_close_other_sessions_without_device_closes_all_of_that_user(monkeypatch):
    monkeypatch.setattr(access_sessions, "ensure_access_sessions_storage", AsyncMock())
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(rowcount=2)), commit=AsyncMock())
    await access_sessions.close_other_sessions_for_subject(db, company_id=COMPANY_ID, scope="mini_panel", subject_id=uuid.uuid4())
    assert "device_id" not in str(db.execute.await_args.args[0])


# ---------------------------------------------------------------------------
# Company-wide cap never evicts a mesero mid-shift
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_company_cap_query_ignores_waiter_ordering_sessions():
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    await access_sessions._active_session_keys(db, COMPANY_ID, "mini_panel")
    statement = str(db.execute.await_args.args[0])
    assert "NOT IN ('mesero', 'cocina', 'caja')" in statement


@pytest.mark.asyncio
async def test_a_mesero_login_is_not_subject_to_the_company_cap(monkeypatch):
    monkeypatch.setattr(access_sessions, "ensure_access_sessions_storage", AsyncMock())
    policy = AsyncMock(side_effect=AssertionError("waiter logins must not read the shared cap"))
    monkeypatch.setattr(access_sessions, "read_company_session_policy", policy)
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    key = await access_sessions.register_access_session(
        db, company_id=COMPANY_ID, scope="mini_panel", subject_id=uuid.uuid4(), subject_label="Laura / mesero",
        request=None, metadata={"panel_type": "mesero"},
    )
    assert key


@pytest.mark.asyncio
async def test_other_mini_panels_still_follow_the_company_cap(monkeypatch):
    monkeypatch.setattr(access_sessions, "ensure_access_sessions_storage", AsyncMock())
    monkeypatch.setattr(access_sessions, "read_company_session_policy", AsyncMock(return_value={
        "enabled": True, "mode": "reject_new",
        "scopes": {"mini_panel": {"enabled": True, "max_sessions": 1}},
    }))
    monkeypatch.setattr(access_sessions, "_active_session_keys", AsyncMock(return_value=["old"]))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await access_sessions.register_access_session(
            db, company_id=COMPANY_ID, scope="mini_panel", subject_id=uuid.uuid4(), subject_label="v / sales",
            request=None, metadata={"panel_type": "sales"},
        )
    assert exc.value.status_code == 429
