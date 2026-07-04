import uuid
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import transport_payments


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency",
    [
        transport_payments.require_transport_payments_read,
        transport_payments.require_transport_payments_write,
    ],
)
async def test_admin_v2_preview_keeps_payments_module_protected(
    monkeypatch: pytest.MonkeyPatch,
    dependency,
) -> None:
    company_id = uuid.uuid4()
    calls = []

    async def active_admin_session(request, db) -> bool:
        return True

    async def enabled_module(db, tenant_id, module_code) -> None:
        calls.append((tenant_id, module_code))

    async def company_user(*args, **kwargs) -> None:
        raise AssertionError("Admin V2 preview must not require a tenant bearer token")

    monkeypatch.setattr(transport_payments, "active_admin_v2_session", active_admin_session)
    monkeypatch.setattr(transport_payments, "require_enabled_module", enabled_module)
    monkeypatch.setattr(transport_payments, "require_company_user_for_tenant", company_user)

    await dependency(company_id, SimpleNamespace(), authorization=None, db=SimpleNamespace())

    assert calls == [(company_id, "transport_payments")]


@pytest.mark.asyncio
async def test_regular_payments_access_still_requires_tenant_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid.uuid4()
    calls = []

    async def inactive_admin_session(request, db) -> bool:
        return False

    async def company_user(db, authorization, tenant_id, **kwargs) -> None:
        calls.append((authorization, tenant_id, kwargs["module_codes"]))

    monkeypatch.setattr(transport_payments, "active_admin_v2_session", inactive_admin_session)
    monkeypatch.setattr(transport_payments, "active_admin_company_preview", lambda request, tenant_id: False)
    monkeypatch.setattr(transport_payments, "require_company_user_for_tenant", company_user)

    await transport_payments.require_transport_payments_read(
        company_id,
        SimpleNamespace(),
        authorization=None,
        access_token="tenant-token",
        db=SimpleNamespace(),
    )

    assert calls == [("Bearer tenant-token", company_id, "transport_payments")]
