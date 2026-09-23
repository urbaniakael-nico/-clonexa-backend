"""Production regression: every mesero/cocina/caja mini panel account
created via "Generar usuario y clave" got role="operator" (hardcoded in
_cx_create_minipanel_user_from_employee_026j), but waiter_ordering.py's own
auth (_require_mesero/_require_cocina/_require_caja, via app.api.deps'
require_role) requires the literal role "mesero"/"cocina"/"caja". Every
waiter-ordering request from a correctly-logged-in mesero 403'd with
role_not_allowed.

Unlike the rest of the suite, these tests do NOT mock require_role or
require_company_user_for_tenant away -- they run the REAL dependency chain
(the endpoint's own _require_* functions -> the real require_company_user_
for_tenant -> the real require_role) with only the true I/O boundaries
stubbed (DB module-enabled lookup, IP allowlist, JWT->user resolution).
That's the "camino real" the user asked for: a mock-everything test would
have hidden this exact bug, which is exactly what happened before.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api import deps as api_deps
from app.api.v1.endpoints import company_users, waiter_ordering

ASADERO_ID = uuid.uuid4()
OTHER_COMPANY_ID = uuid.uuid4()


def _request():
    return SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.5"))


async def _create_mini_panel_user(panel_type: str, employee_role: str = None):
    """Exercises the real creation path (the one the "Generar usuario y
    clave" button calls) and returns the actual CompanyUser object that was
    constructed, so the role it ends up with is whatever the real code
    produces -- not something the test asserts by fiat."""
    employee_id = uuid.uuid4()
    employee = SimpleNamespace(
        id=employee_id, full_name="Samuel", role=employee_role or panel_type, employee_type=employee_role or panel_type,
    )

    async def fake_execute(stmt, params=None):
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: None))

    captured = {}

    def fake_add(obj):
        captured["user"] = obj

    db = SimpleNamespace(execute=fake_execute, add=fake_add, commit=AsyncMock(), refresh=AsyncMock())

    class _Patches:
        def __enter__(self_inner):
            self_inner.originals = {}
            for name, value in {
                "_cx_employee_or_404_019c": AsyncMock(return_value=employee),
                "_cx_find_minipanel_user_019c": AsyncMock(return_value=None),
                "_cx_require_waiter_ordering_module_026k": AsyncMock(),
                "_cx_waiter_ordering_module_settings_026k": AsyncMock(
                    return_value={"segments": {"mesero": {"enabled": True}, "cocina": {"enabled": True}, "caja": {"enabled": True}}}
                ),
                "_cx_count_minipanel_users_of_type_026k": AsyncMock(return_value=0),
            }.items():
                self_inner.originals[name] = getattr(company_users, name)
                setattr(company_users, name, value)
            return self_inner

        def __exit__(self_inner, *exc):
            for name, value in self_inner.originals.items():
                setattr(company_users, name, value)

    with _Patches():
        payload = company_users.SalesMiniPanelUserCreateRequest(employee_id=employee_id)
        await company_users._cx_create_minipanel_user_from_employee_026j(
            company_id=ASADERO_ID, payload=payload, panel_type=panel_type, db=db, source="workforce",
        )

    return captured["user"]


def _fake_current_user_resolver(users_by_token: dict):
    async def _fake(db, token):
        user = users_by_token.get(token)
        if not user:
            raise HTTPException(status_code=401, detail="invalid_token")
        return user
    return _fake


@pytest.fixture(autouse=True)
def _stub_io_boundaries(monkeypatch):
    """Only the true I/O (module-enabled DB lookup, IP allowlist) is
    stubbed; require_role and the tenant-match check run for real."""
    monkeypatch.setattr(waiter_ordering, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(api_deps, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(waiter_ordering, "ip_allowed_for_scope", AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_a_freshly_created_mesero_account_passes_its_own_real_auth_gate(monkeypatch):
    mesero_user = await _create_mini_panel_user("mesero")
    assert mesero_user.role == "mesero"  # this is the bug: it used to be "operator"

    monkeypatch.setattr(api_deps, "get_current_company_user", _fake_current_user_resolver({"tok": mesero_user}))

    resolved = await waiter_ordering._require_mesero(ASADERO_ID, _request(), authorization="Bearer tok", db=SimpleNamespace())
    assert resolved is mesero_user

    # Shared menu/board reader also accepts mesero.
    resolved2 = await waiter_ordering._require_menu_reader(ASADERO_ID, _request(), authorization="Bearer tok", db=SimpleNamespace())
    assert resolved2 is mesero_user


@pytest.mark.asyncio
async def test_a_freshly_created_cocina_account_passes_its_own_real_auth_gate(monkeypatch):
    cocina_user = await _create_mini_panel_user("cocina", employee_role="parrillero")
    assert cocina_user.role == "cocina"

    monkeypatch.setattr(api_deps, "get_current_company_user", _fake_current_user_resolver({"tok": cocina_user}))

    resolved = await waiter_ordering._require_cocina(ASADERO_ID, _request(), authorization="Bearer tok", db=SimpleNamespace())
    assert resolved is cocina_user


@pytest.mark.asyncio
async def test_a_freshly_created_caja_account_passes_its_own_real_auth_gate(monkeypatch):
    caja_user = await _create_mini_panel_user("caja", employee_role="cajero")
    assert caja_user.role == "caja"

    monkeypatch.setattr(api_deps, "get_current_company_user", _fake_current_user_resolver({"tok": caja_user}))

    resolved = await waiter_ordering._require_caja(ASADERO_ID, _request(), authorization="Bearer tok", db=SimpleNamespace())
    assert resolved is caja_user
    # Caja is also allowed on mesero-shared endpoints (edit/void orders).
    resolved2 = await waiter_ordering._require_mesero(ASADERO_ID, _request(), authorization="Bearer tok", db=SimpleNamespace())
    assert resolved2 is caja_user


@pytest.mark.asyncio
async def test_a_user_of_an_unrelated_mini_panel_type_is_rejected(monkeypatch):
    sales_user = SimpleNamespace(id=uuid.uuid4(), company_id=ASADERO_ID, role="operator", full_name="Vendedor")
    monkeypatch.setattr(api_deps, "get_current_company_user", _fake_current_user_resolver({"tok": sales_user}))

    for dep in (waiter_ordering._require_mesero, waiter_ordering._require_cocina, waiter_ordering._require_menu_reader):
        with pytest.raises(HTTPException) as exc:
            await dep(ASADERO_ID, _request(), authorization="Bearer tok", db=SimpleNamespace())
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_a_mesero_from_a_different_company_is_rejected(monkeypatch):
    other_company_mesero = SimpleNamespace(id=uuid.uuid4(), company_id=OTHER_COMPANY_ID, role="mesero", full_name="Otro")
    monkeypatch.setattr(api_deps, "get_current_company_user", _fake_current_user_resolver({"tok": other_company_mesero}))

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering._require_mesero(ASADERO_ID, _request(), authorization="Bearer tok", db=SimpleNamespace())
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Full endpoint calls (not just the auth gate) for the exact 4 URLs the
# production incident named: menu, mis-mesas, ventas-hoy, kitchen.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_menu_mis_mesas_and_ventas_hoy_succeed_for_a_real_mesero_account(monkeypatch):
    mesero_user = await _create_mini_panel_user("mesero")

    class EmptyRows:
        def mappings(self):
            return self

        def all(self):
            return []

    db = SimpleNamespace(execute=AsyncMock(return_value=EmptyRows()))

    monkeypatch.setattr(waiter_ordering, "hospitality_inventory_lite", AsyncMock(return_value={"inventory": []}))
    monkeypatch.setattr(waiter_ordering, "_category_rows", AsyncMock(return_value={}))
    monkeypatch.setattr(waiter_ordering, "_portion_membership", AsyncMock(return_value={}))
    menu = await waiter_ordering.waiter_ordering_menu(ASADERO_ID, db=db, _user=mesero_user)
    assert menu["ok"] is True

    monkeypatch.setattr(waiter_ordering, "list_hospitality_orders", AsyncMock(return_value={"orders": []}))
    mesas = await waiter_ordering.waiter_my_tables(ASADERO_ID, db=db, user=mesero_user)
    assert mesas["ok"] is True

    class FakeResult:
        def mappings(self):
            return self

        def first(self):
            return {"total": 0, "orders_count": 0}

    db2 = SimpleNamespace(execute=AsyncMock(return_value=FakeResult()))
    mesero_user.settings_json = {"mini_panel": {"daily_goal": 0}}
    ventas = await waiter_ordering.waiter_sales_today(ASADERO_ID, db=db2, user=mesero_user)
    assert ventas["ok"] is True


@pytest.mark.asyncio
async def test_kitchen_board_succeeds_for_a_real_cocina_account(monkeypatch):
    cocina_user = await _create_mini_panel_user("cocina")
    cocina_user.settings_json = {"mini_panel": {"stations": []}}
    db = SimpleNamespace(execute=AsyncMock())

    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value={}))
    monkeypatch.setattr(waiter_ordering, "list_hospitality_orders", AsyncMock(return_value={"orders": []}))

    board = await waiter_ordering.waiter_ordering_kitchen_board(ASADERO_ID, db=db, user=cocina_user)
    assert board["ok"] is True
