"""Fase 2: require_company_user_not_role is the gate behind Nomina/Ajustes
in a company with waiter_ordering enabled (payroll.py, core_settings.py both
depend on require_company_user_not_role({"administrador"})). It must be a
true no-op -- no auth requirement at all -- for the ~100+ other companies
that don't have the module, which is what keeps this change scoped to
Asadero El Socio only.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import company_users


@pytest.mark.asyncio
async def test_noop_when_the_company_has_no_waiter_ordering_module(monkeypatch):
    async def raise_not_enabled(db, company_id, code):
        raise HTTPException(status_code=403, detail="module_not_enabled")

    monkeypatch.setattr(company_users, "require_enabled_module", raise_not_enabled)
    tenant_check = AsyncMock()
    monkeypatch.setattr(company_users, "require_company_user_for_tenant", tenant_check)

    dependency = company_users.require_company_user_not_role({"administrador"})
    result = await dependency(company_id=uuid.uuid4(), authorization=None, db=SimpleNamespace())

    assert result is None
    tenant_check.assert_not_awaited()


@pytest.mark.asyncio
async def test_blocks_the_forbidden_role_when_module_is_enabled(monkeypatch):
    monkeypatch.setattr(company_users, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(
        company_users, "require_company_user_for_tenant",
        AsyncMock(return_value=SimpleNamespace(role="administrador")),
    )

    dependency = company_users.require_company_user_not_role({"administrador"})
    with pytest.raises(HTTPException) as exc:
        await dependency(company_id=uuid.uuid4(), authorization="Bearer tok", db=SimpleNamespace())

    assert exc.value.status_code == 403
    assert exc.value.detail == "role_not_allowed"


@pytest.mark.asyncio
async def test_allows_dueno_and_gerente_through(monkeypatch):
    monkeypatch.setattr(company_users, "require_enabled_module", AsyncMock())

    for role in ("dueno", "gerente"):
        monkeypatch.setattr(
            company_users, "require_company_user_for_tenant",
            AsyncMock(return_value=SimpleNamespace(role=role)),
        )
        dependency = company_users.require_company_user_not_role({"administrador"})
        result = await dependency(company_id=uuid.uuid4(), authorization="Bearer tok", db=SimpleNamespace())
        assert result is None


@pytest.mark.asyncio
async def test_requires_a_valid_session_when_module_is_enabled(monkeypatch):
    """Even a role outside forbidden_roles still needs real tenant auth --
    the no-op only kicks in when the module itself is off."""
    monkeypatch.setattr(company_users, "require_enabled_module", AsyncMock())

    async def reject(db, authorization, company_id, **kwargs):
        raise HTTPException(status_code=401, detail="missing_session")

    monkeypatch.setattr(company_users, "require_company_user_for_tenant", reject)

    dependency = company_users.require_company_user_not_role({"administrador"})
    with pytest.raises(HTTPException) as exc:
        await dependency(company_id=uuid.uuid4(), authorization=None, db=SimpleNamespace())

    assert exc.value.status_code == 401
