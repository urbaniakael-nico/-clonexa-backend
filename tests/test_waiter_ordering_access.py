"""Fase 1 mesero -> cocina -> caja: module gate, local-network IP gate,
single-session-per-user kick, per-type user limits and category naming.

These test the NEW pieces this feature adds (waiter_ordering.py and the
company_users.py/access_sessions.py additions), not the pre-existing
hospitality order/inventory machinery those pieces call into (already
covered by the rest of tests/test_hospitality_*.py).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import company_users, waiter_ordering
from app.services import access_sessions


class MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class MappingListResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


# ---------------------------------------------------------------------------
# Category naming (server-side twin of hospitality_order.js's productCategory)
# ---------------------------------------------------------------------------

def test_category_key_uses_first_word_like_the_qr_client():
    assert waiter_ordering._category_key("CERVEZA Aguila") == "cerveza"
    assert waiter_ordering._category_key("hamburguesa doble carne") == "hamburguesa"


def test_category_key_falls_back_to_otros_for_empty_name():
    assert waiter_ordering._category_key("") == "otros"
    assert waiter_ordering._category_key(None) == "otros"


def test_category_key_strips_accents_for_a_stable_url_safe_id():
    assert waiter_ordering._category_key("Limonada") == "limonada"
    assert waiter_ordering._category_key("Ñame frito") == "name"


def test_pretty_label_title_cases_and_defaults_to_otros():
    assert waiter_ordering._pretty_label("cerveza") == "Cerveza"
    assert waiter_ordering._pretty_label("") == "Otros"


# ---------------------------------------------------------------------------
# Local-network IP allowlist (mirrors app.main's page guard, callable inline)
# ---------------------------------------------------------------------------

def _policy_db(policy):
    return SimpleNamespace(execute=AsyncMock(return_value=MappingResult({"settings_json": {"security": {"ip_allowlist": policy}}})))


@pytest.mark.asyncio
async def test_ip_allowed_when_policy_disabled():
    db = _policy_db({"enabled": False, "scopes": {"mini_panel": {"enabled": True, "allowed_ips": ["1.2.3.4"]}}})
    assert await access_sessions.ip_allowed_for_scope(db, uuid.uuid4(), "mini_panel", "9.9.9.9") is True


@pytest.mark.asyncio
async def test_ip_blocked_from_an_unregistered_address():
    db = _policy_db({"enabled": True, "scopes": {"mini_panel": {"enabled": True, "allowed_ips": ["10.0.0.5"]}}})
    assert await access_sessions.ip_allowed_for_scope(db, uuid.uuid4(), "mini_panel", "10.0.0.9") is False


@pytest.mark.asyncio
async def test_ip_allowed_from_the_registered_address():
    db = _policy_db({"enabled": True, "scopes": {"mini_panel": {"enabled": True, "allowed_ips": ["10.0.0.5"]}}})
    assert await access_sessions.ip_allowed_for_scope(db, uuid.uuid4(), "mini_panel", "10.0.0.5") is True


@pytest.mark.asyncio
async def test_ip_allowed_from_a_registered_cidr_range():
    db = _policy_db({"enabled": True, "scopes": {"mini_panel": {"enabled": True, "allowed_ips": ["10.0.0.0/24"]}}})
    assert await access_sessions.ip_allowed_for_scope(db, uuid.uuid4(), "mini_panel", "10.0.0.200") is True


# ---------------------------------------------------------------------------
# Single-session-per-user kick
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close_other_sessions_for_subject_targets_only_that_user():
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(rowcount=1)), commit=AsyncMock())
    company_id = uuid.uuid4()
    subject_id = uuid.uuid4()

    closed = await access_sessions.close_other_sessions_for_subject(
        db, company_id=company_id, scope="mini_panel", subject_id=subject_id,
    )

    assert closed == 1
    statement = str(db.execute.await_args.args[0])
    params = db.execute.await_args.args[1]
    assert "subject_id = CAST(:subject_id AS uuid)" in statement
    assert "company_id = CAST(:company_id AS uuid)" in statement
    assert params["subject_id"] == str(subject_id)
    assert params["company_id"] == str(company_id)


@pytest.mark.asyncio
async def test_validate_access_session_surfaces_the_kick_reason(monkeypatch):
    monkeypatch.setattr(access_sessions, "ensure_access_sessions_storage", AsyncMock())
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=MappingResult(
                {
                    "session_key": "abc",
                    "company_id": "11111111-1111-1111-1111-111111111111",
                    "scope": "mini_panel",
                    "status": "closed",
                    "subject_label": "mesero",
                    "closed_reason": "Tu sesion se abrio en otro dispositivo.",
                }
            )
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await access_sessions.validate_access_session(db, "abc")
    assert exc.value.detail == "Tu sesion se abrio en otro dispositivo."


# ---------------------------------------------------------------------------
# Module + local-network gate wired into every mesero/cocina/caja endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_other_company_without_the_module_gets_403(monkeypatch):
    monkeypatch.setattr(
        waiter_ordering, "require_enabled_module",
        AsyncMock(side_effect=HTTPException(status_code=403, detail="module_not_enabled_for_tenant")),
    )
    request = SimpleNamespace(headers={}, client=None)
    with pytest.raises(HTTPException) as exc:
        await waiter_ordering._require_waiter_ordering_user(uuid.uuid4(), request, "Bearer x", SimpleNamespace(), {"mesero"})
    assert exc.value.status_code == 403
    assert exc.value.detail == "module_not_enabled_for_tenant"


@pytest.mark.asyncio
async def test_blocked_outside_the_registered_local_network(monkeypatch):
    monkeypatch.setattr(waiter_ordering, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(waiter_ordering, "ip_allowed_for_scope", AsyncMock(return_value=False))
    request = SimpleNamespace(headers={"x-forwarded-for": "8.8.8.8"}, client=None)
    with pytest.raises(HTTPException) as exc:
        await waiter_ordering._require_waiter_ordering_user(uuid.uuid4(), request, "Bearer x", SimpleNamespace(), {"caja"})
    assert exc.value.status_code == 403
    assert exc.value.detail == "Conectate al WiFi del restaurante."


@pytest.mark.asyncio
async def test_allowed_inside_the_registered_network_delegates_to_role_check(monkeypatch):
    monkeypatch.setattr(waiter_ordering, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(waiter_ordering, "ip_allowed_for_scope", AsyncMock(return_value=True))
    fake_user = SimpleNamespace(id=uuid.uuid4(), role="mesero")
    require_tenant = AsyncMock(return_value=fake_user)
    monkeypatch.setattr(waiter_ordering, "require_company_user_for_tenant", require_tenant)
    request = SimpleNamespace(headers={"x-forwarded-for": "10.0.0.5"}, client=None)

    company_id = uuid.uuid4()
    result = await waiter_ordering._require_waiter_ordering_user(company_id, request, "Bearer x", SimpleNamespace(), {"mesero"})

    assert result is fake_user
    require_tenant.assert_awaited_once()
    _, kwargs = require_tenant.await_args
    assert kwargs["allowed_roles"] == {"mesero"}
    assert kwargs["module_codes"] == "waiter_ordering"


# ---------------------------------------------------------------------------
# Per-type user limits: mesero / cocina / caja are counted independently
# ---------------------------------------------------------------------------

def _minipanel_user(panel_type):
    return SimpleNamespace(settings_json={"mini_panel": {"enabled": True, "type": panel_type}})


@pytest.mark.asyncio
async def test_kitchen_and_cashier_limits_default_low_and_do_not_share_a_bucket():
    db = SimpleNamespace(execute=AsyncMock(return_value=MappingResult(None)))
    company_id = uuid.uuid4()
    assert await company_users._cx_waiter_ordering_user_limit_026k(db, company_id, "mesero") == 10
    assert await company_users._cx_waiter_ordering_user_limit_026k(db, company_id, "cocina") == 2
    assert await company_users._cx_waiter_ordering_user_limit_026k(db, company_id, "caja") == 1


@pytest.mark.asyncio
async def test_user_limit_reads_the_configured_module_settings():
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=MappingResult({"settings": {"kitchen_user_limit": 5, "cashier_user_limit": 3}})
        )
    )
    company_id = uuid.uuid4()
    assert await company_users._cx_waiter_ordering_user_limit_026k(db, company_id, "cocina") == 5
    assert await company_users._cx_waiter_ordering_user_limit_026k(db, company_id, "caja") == 3


@pytest.mark.asyncio
async def test_count_minipanel_users_of_type_only_counts_that_exact_type():
    users = [_minipanel_user("mesero"), _minipanel_user("mesero"), _minipanel_user("cocina")]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: users))))
    company_id = uuid.uuid4()
    assert await company_users._cx_count_minipanel_users_of_type_026k(db, company_id, "mesero") == 2
    assert await company_users._cx_count_minipanel_users_of_type_026k(db, company_id, "cocina") == 1
    assert await company_users._cx_count_minipanel_users_of_type_026k(db, company_id, "caja") == 0


def test_panel_type_aliases_mesero_cocina_caja_without_colliding_with_store():
    assert company_users._cx_panel_type_019d("mesero") == "mesero"
    assert company_users._cx_panel_type_019d("waiter") == "mesero"
    assert company_users._cx_panel_type_019d("cocina") == "cocina"
    assert company_users._cx_panel_type_019d("kitchen") == "cocina"
    assert company_users._cx_panel_type_019d("caja") == "caja"
    assert company_users._cx_panel_type_019d("cajero") == "caja"
    # "caja"/"cajero" must stay their own panel type, not fold into "store".
    assert company_users._cx_panel_type_019d("tiendas") == "store"


# ---------------------------------------------------------------------------
# Kitchen board: a cocina user only sees comandas for their own stations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kitchen_board_filters_items_by_the_cocina_users_stations(monkeypatch):
    order = {
        "id": "order-1",
        "table_number": "Mesa 4",
        "status": "alistando",
        "notes": "",
        "created_at": "2026-09-22T10:00:00Z",
        "metadata": {"waiter": {"name": "Laura"}},
        "items": [
            {"id": "line_1", "name": "Carne", "station": "parrilla", "quantity": 1},
            {"id": "line_2", "name": "Papas", "station": "freidora", "quantity": 1},
        ],
    }
    monkeypatch.setattr(
        waiter_ordering, "list_hospitality_orders",
        AsyncMock(return_value={"orders": [order]}),
    )
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value={}))

    grill_user = SimpleNamespace(settings_json={"mini_panel": {"stations": ["parrilla"]}})
    result = await waiter_ordering.waiter_ordering_kitchen_board(uuid.uuid4(), db=SimpleNamespace(), user=grill_user)

    assert len(result["comandas"]) == 1
    items = result["comandas"][0]["items"]
    assert [item["name"] for item in items] == ["Carne"]
    assert result["comandas"][0]["waiter"] == {"name": "Laura"}


@pytest.mark.asyncio
async def test_kitchen_board_with_no_stations_assigned_sees_everything(monkeypatch):
    order = {
        "id": "order-1",
        "table_number": "Mesa 4",
        "status": "pendiente",
        "notes": "",
        "created_at": "2026-09-22T10:00:00Z",
        "metadata": {},
        "items": [
            {"id": "line_1", "name": "Carne", "station": "parrilla", "quantity": 1},
            {"id": "line_2", "name": "Gaseosa", "station": "bebidas", "quantity": 2},
        ],
    }
    monkeypatch.setattr(waiter_ordering, "list_hospitality_orders", AsyncMock(return_value={"orders": [order]}))
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value={}))

    no_station_user = SimpleNamespace(settings_json={})
    result = await waiter_ordering.waiter_ordering_kitchen_board(uuid.uuid4(), db=SimpleNamespace(), user=no_station_user)

    assert len(result["comandas"][0]["items"]) == 2
