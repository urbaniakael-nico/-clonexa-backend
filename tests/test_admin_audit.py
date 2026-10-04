"""Auditoria de la consola maestra (admin_audit_log).

- Registra SOLO POST/PUT/PATCH/DELETE hechos con sesion de Admin V2 valida.
- No registra GET ni peticiones sin sesion.
- Un fallo del registro nunca rompe ni cambia la respuesta.
- Nunca guarda cuerpos ni claves; las acciones nuevas agregan un detalle corto.
"""
from __future__ import annotations

import ast
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import admin_audit as audit
from app.web import admin_v2plus_companies as ep

CID = str(uuid.uuid4())


def _mini_app():
    mini = FastAPI()

    @mini.api_route("/api/v1/companies/{company_id}/users", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def users(company_id: str, request: Request):
        if request.method == "POST":
            await request.json()
        return JSONResponse({"ok": True, "company_id": company_id})

    @mini.post("/admin-v2/api/companies/{company_id}/purge")
    async def purge(company_id: str, request: Request):
        audit.attach_detail(request, company_name="Demo Bar", deleted_rows=42, api_token="no-debe-quedar")
        return JSONResponse({"ok": True}, status_code=200)

    @mini.post("/api/v1/companies/{company_id}/status")
    async def bad(company_id: str):
        return JSONResponse({"detail": "Estado inválido."}, status_code=400)

    mini.add_middleware(audit.AdminAuditMiddleware)
    return mini


@pytest.fixture
def spy(monkeypatch):
    entries = []
    actor = AsyncMock(return_value="clonexasaas@gmail.com")

    async def write(entry):
        entries.append(entry)

    monkeypatch.setattr(audit, "admin_actor", actor)
    monkeypatch.setattr(audit, "write_entry", write)
    return SimpleNamespace(entries=entries, actor=actor, client=TestClient(_mini_app()))


def test_registers_writes_with_admin_session(spy):
    secret_body = {"email": "a@b.co", "password": "Clave-Super-Secreta-1!", "token": "123:ABC"}
    response = spy.client.post(f"/api/v1/companies/{CID}/users?debug=1", json=secret_body,
                               headers={"referer": "https://clonexa.app/admin-v2plus", "x-forwarded-for": "1.1.1.1, 181.50.2.3"})
    assert response.status_code == 200 and response.json() == {"ok": True, "company_id": CID}
    [entry] = spy.entries
    assert entry == {"actor": "clonexasaas@gmail.com", "ip": "181.50.2.3", "method": "POST",
                     "path": f"/api/v1/companies/{CID}/users", "company_id": CID, "status_code": 200,
                     "surface": "v2plus", "detail": None}
    flat = repr(entry)
    for secret in ("Clave-Super-Secreta-1!", "123:ABC", "debug=1", "a@b.co"):
        assert secret not in flat, "nunca cuerpos ni query strings"


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_registers_every_write_method(spy, method):
    spy.client.request(method, f"/api/v1/companies/{CID}/users", headers={"referer": "https://clonexa.app/admin-v2"})
    assert [e["method"] for e in spy.entries] == [method] and spy.entries[0]["surface"] == "v2"


def test_does_not_register_reads(spy):
    assert spy.client.get(f"/api/v1/companies/{CID}/users").status_code == 200
    assert spy.entries == []
    spy.actor.assert_not_awaited()


def test_does_not_register_without_admin_session(spy):
    spy.actor.return_value = None
    assert spy.client.post(f"/api/v1/companies/{CID}/users", json={}).status_code == 200
    assert spy.entries == []


def test_records_the_real_status_code(spy):
    assert spy.client.post(f"/api/v1/companies/{CID}/status", json={}).status_code == 400
    assert spy.entries[0]["status_code"] == 400


def test_new_actions_add_a_short_detail_without_secrets(spy):
    spy.client.post(f"/admin-v2/api/companies/{CID}/purge", json={"dry_run": False, "confirm_name": "Demo Bar"})
    [entry] = spy.entries
    assert entry["detail"] == {"company_name": "Demo Bar", "deleted_rows": 42}


def test_a_failing_logger_never_breaks_the_request(monkeypatch):
    async def boom(entry):
        raise RuntimeError("la base no responde")

    monkeypatch.setattr(audit, "admin_actor", AsyncMock(return_value="clonexasaas@gmail.com"))
    monkeypatch.setattr(audit, "write_entry", boom)
    response = TestClient(_mini_app()).post(f"/api/v1/companies/{CID}/users", json={"a": 1})
    assert response.status_code == 200 and response.json() == {"ok": True, "company_id": CID}


def test_a_failing_session_check_never_breaks_the_request(monkeypatch):
    writes = AsyncMock()
    monkeypatch.setattr(audit, "admin_actor", AsyncMock(side_effect=RuntimeError("sin base")))
    monkeypatch.setattr(audit, "write_entry", writes)
    response = TestClient(_mini_app()).post(f"/api/v1/companies/{CID}/users", json={"a": 1})
    assert response.status_code == 200
    writes.assert_not_awaited()


def test_the_app_registers_the_middleware():
    assert any(m.cls is audit.AdminAuditMiddleware for m in app_main.app.user_middleware)


def test_new_endpoints_leave_their_detail_through_the_real_app(monkeypatch):
    entries = []

    async def write(entry):
        entries.append(entry)

    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), execute=AsyncMock())

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    try:
        monkeypatch.setattr(audit, "admin_actor", AsyncMock(return_value="clonexasaas@gmail.com"))
        monkeypatch.setattr(audit, "write_entry", write)
        monkeypatch.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
        monkeypatch.setattr(ep, "load_company", AsyncMock(return_value={"id": CID, "name": "Demo Bar", "slug": "demo", "status": "active",
                                                                         "kind": "demo", "settings_json": {}}))
        response = TestClient(app_main.app).post(f"/admin-v2/api/companies/{CID}/kind", json={"kind": "registrada", "confirm": True})
        assert response.status_code == 200
        [entry] = entries
        assert entry["company_id"] == CID and entry["method"] == "POST"
        assert entry["detail"] == {"company_name": "Demo Bar", "kind_from": "demo", "kind_to": "registrada"}
    finally:
        app_main.app.dependency_overrides.pop(get_db, None)


# ------------------------------------------------------------ escritura ---
class FakeSession:
    def __init__(self):
        self.statements = []
        self.commit = AsyncMock()

    async def execute(self, statement, params=None):
        self.statements.append((" ".join(str(statement).split()), params))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_write_entry_inserts_only_metadata_and_prunes_180_days(monkeypatch):
    import app.core.database as database

    session = FakeSession()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(audit, "_last_prune", 0.0)
    await audit.write_entry({"actor": "x", "ip": "1.1.1.1", "method": "POST", "path": "/a", "company_id": None,
                             "status_code": 200, "surface": "v2plus", "detail": {"company_name": "Demo"}})
    insert, params = session.statements[0]
    assert insert.startswith("INSERT INTO admin_audit_log (actor, ip, method, path, company_id, status_code, surface, detail)")
    assert params["detail"] == '{"company_name": "Demo"}'
    assert session.statements[1][0] == "DELETE FROM admin_audit_log WHERE at < NOW() - INTERVAL '180 days'"
    session.statements.clear()
    await audit.write_entry({"actor": "x", "ip": "", "method": "POST", "path": "/a", "company_id": None,
                             "status_code": 200, "surface": "api", "detail": None})
    assert len(session.statements) == 1, "la poda corre como mucho cada 12 h"


# --------------------------------------------------------------- lectura ---
def test_build_query_filters():
    sql, params = audit.build_query(company_id=CID.upper(), date_from="2026-10-01", date_to="2026-10-03", action="purge", limit=9999)
    assert "company_id = CAST(:company_id AS uuid)" in sql and params["company_id"] == CID
    assert params["date_from"] == datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc), "dia en Bogota"
    assert params["date_to"] == datetime(2026, 10, 4, 5, 0, tzinfo=timezone.utc)
    assert "path ILIKE :action" in sql and params["action"] == "%purge%"
    assert params["limit"] == 500 and sql.endswith("ORDER BY at DESC LIMIT :limit")
    sql, params = audit.build_query(action="delete")
    assert "method = :method" in sql and params["method"] == "DELETE"
    sql, params = audit.build_query()
    assert "WHERE" not in sql and params == {"limit": 100}
    with pytest.raises(ValueError):
        audit.build_query(company_id="1 OR 1=1")


def test_audit_endpoint_requires_session_and_filters(monkeypatch):
    async def fake_db():
        yield SimpleNamespace()

    app_main.app.dependency_overrides[get_db] = fake_db
    try:
        client = TestClient(app_main.app)
        monkeypatch.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
        listing = AsyncMock(return_value=[])
        monkeypatch.setattr(audit, "list_entries", listing)
        assert client.get("/admin-v2/api/audit").status_code == 401
        listing.assert_not_awaited()
        monkeypatch.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
        listing.return_value = [{"id": "1", "method": "POST"}]
        body = client.get(f"/admin-v2/api/audit?company_id={CID}&action=purge&date_from=2026-10-01").json()
        assert body == {"ok": True, "entries": [{"id": "1", "method": "POST"}], "retention_days": 180}
        assert listing.await_args.kwargs == {"company_id": CID, "date_from": "2026-10-01", "date_to": "", "action": "purge", "limit": 100}
        listing.side_effect = ValueError("company_id invalido")
        assert client.get("/admin-v2/api/audit?company_id=x").status_code == 400
    finally:
        app_main.app.dependency_overrides.pop(get_db, None)


def test_helpers():
    assert audit.company_id_from_path(f"/admin-v2/api/companies/{CID}/purge") == CID
    assert audit.company_id_from_path("/api/v1/companies") is None
    assert audit.company_id_from_path("/api/v1/companies/not-a-uuid/users") is None
    assert audit.surface_of("", "/admin-v2plus/api/passkeys/1") == "v2plus"
    assert audit.surface_of("https://x/client", "/api/v1/x") == "api"
    assert audit.clean_detail({"password": "x", "n": 1, "name": "y" * 500}) == {"n": 1, "name": "y" * 200}


def test_audit_migration():
    source = Path("migrations/versions/023b_admin_audit_log.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    values = {n.targets[0].id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
              and isinstance(n.value, ast.Constant) and isinstance(n.targets[0], ast.Name)}
    assert values["revision"] == "023b_admin_audit_log" and len(values["revision"]) <= 32
    assert values["down_revision"] == "023a_company_kind"
    for column in ("id uuid", "at timestamptz", "actor", "ip", "method", "path", "company_id uuid NULL", "status_code", "surface", "detail jsonb"):
        assert column in source
    assert "body" not in source.split('"""', 2)[2] and "password" not in source.lower()
