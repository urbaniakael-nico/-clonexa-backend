"""SECURITY (2026-09-24): POST /hospitality/companies/{id}/song-requests/
{request_id}/archive had no auth -- anyone with the ids could archive
another company's song requests. It now requires Admin V2 or a logged-in
user of that same company (the company panel already sends its session).

Hits the real ASGI app; the rejected requests must fail before touching the
database (this repo has no test database).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import hospitality
from app.web import admin_v2_routes

client = TestClient(app_main.app)


def _url(company_id: str, request_id: str | None = None) -> str:
    return f"/api/v1/hospitality/companies/{company_id}/song-requests/{request_id or uuid.uuid4()}/archive"


def test_hospitality_song_archive_rejects_a_request_with_no_credentials():
    response = client.post(_url(str(uuid.uuid4())), json={})
    assert response.status_code in (401, 403), response.text


def test_hospitality_song_archive_rejects_a_user_of_another_company(monkeypatch):
    company_id = str(uuid.uuid4())
    other_company_user = SimpleNamespace(company_id=uuid.uuid4(), role="company_admin", status="active")
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(return_value=other_company_user))

    response = client.post(_url(company_id), json={}, headers={"Authorization": "Bearer token-de-otra-empresa"})

    assert response.status_code == 403
    assert "tenant_not_allowed" in response.text


class _ArchiveDb:
    def __init__(self):
        self.params = None
        self.commit = AsyncMock()

    async def execute(self, statement, params=None):
        self.params = params
        row = {"id": params["request_id"], "company_id": params["company_id"], "song": "Querida", "status": "archivada"}
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))


def test_hospitality_song_archive_works_for_a_user_of_that_company(monkeypatch):
    company_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    own_user = SimpleNamespace(company_id=uuid.UUID(company_id), role="operador", status="active")
    db = _ArchiveDb()

    async def fake_db():
        yield db

    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    monkeypatch.setattr(deps, "get_current_company_user", AsyncMock(return_value=own_user))
    monkeypatch.setattr(deps, "require_role", lambda user, roles=None: None)
    monkeypatch.setattr(deps, "require_enabled_module", AsyncMock())
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_song_request_payload", lambda row: dict(row))
    app_main.app.dependency_overrides[get_db] = fake_db
    try:
        response = client.post(_url(company_id, request_id), json={}, headers={"Authorization": "Bearer token-propio"})
    finally:
        app_main.app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    assert db.params == {"request_id": request_id, "company_id": company_id}
    assert response.json()["song_request"]["status"] == "archivada"


def test_hospitality_public_qr_song_request_stays_open():
    # the customer's QR page sends songs without login: that route must not
    # get the company-user guard (it is protected by the table access code)
    route = next(
        r for r in app_main.app.routes
        if getattr(r, "path", "") == "/api/v1/hospitality/companies/{company_id}/song-requests"
        and "POST" in getattr(r, "methods", set())
    )
    names = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
    assert "require_admin_v2_or_tenant_company_user" not in names
