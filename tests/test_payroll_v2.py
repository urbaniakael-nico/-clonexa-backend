"""Nomina v2 — rutas nuevas y reglas que no cambian.

- La vista previa de "confirmar salida" recalcula con ESE turno tratado como
  confirmado solo dentro de la peticion (contextvar) y no escribe nada;
  fuera de ella el calculo es el de siempre.
- Las rutas nuevas exigen sesion (Admin V2 o usuario de esa empresa).
- Documento: opcional y sin repetirse dentro de la empresa, con aviso claro.
"""
from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.api.v1.endpoints import employees as employees_ep
from app.api.v1.endpoints import payroll as core
from app.api.v1.endpoints import payroll_v2
from app.web import admin_v2plus_companies as ep

CID = str(uuid.uuid4())
ITEM = {"employee_id": "e1", "employee_name": "Ana", "source": "attendance", "session_ref": "ci-1", "closure_id": "cl-1",
        "start": "2026-10-05T12:00:00+00:00", "end": "2026-10-06T05:00:00+00:00", "minutes": 900, "status": "pending"}


def snapshot(extra: int, pending: bool) -> dict:
    return {"rows": [{"employee_id": "e1", "regular_minutes": 480, "extra_minutes": extra, "gross_amount": 100.0 + extra, "discount_amount": 0.0,
                      "net_amount": 100.0 + extra, "closed_shifts": 1}],
            "unverified_shifts": [ITEM] if pending else []}


@pytest.mark.asyncio
async def test_preview_recalculates_with_that_shift_confirmed_and_writes_nothing(monkeypatch):
    seen = []

    async def fake_calc(db, company_id, start, end):
        override = core.PREVIEW_CLOSURES_052A.get()
        seen.append(override)
        return snapshot(60, pending=False) if override else snapshot(0, pending=True)

    monkeypatch.setattr(core, "calculate_period_snapshot", fake_calc)
    monkeypatch.setattr(payroll_v2.sessions_ep, "_tz", AsyncMock(return_value=__import__("zoneinfo").ZoneInfo("America/Bogota")))
    db = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("no escribe nada")), commit=AsyncMock(side_effect=AssertionError("no confirma nada")))
    out = await payroll_v2.payroll_closure_preview(uuid.UUID(CID), {"period_start": "2026-10-01", "period_end": "2026-10-15", "source": "attendance",
                                                                    "session_ref": "ci-1", "real_end_at": "2026-10-05T16:00"}, db)
    assert out["before"]["extra_minutes"] == 0 and out["after"]["extra_minutes"] == 60
    assert seen[0] is None, "primero el calculo de siempre"
    override = seen[1][("attendance", "ci-1")]
    assert override["status"] == "confirmed" and override["real_end_at"].isoformat() == "2026-10-05T21:00:00+00:00"
    assert core.PREVIEW_CLOSURES_052A.get() is None, "fuera de la vista previa nada cambia"

    with pytest.raises(HTTPException) as bad:  # fuera del rango del turno
        await payroll_v2.payroll_closure_preview(uuid.UUID(CID), {"period_start": "2026-10-01", "period_end": "2026-10-15", "source": "attendance",
                                                                        "session_ref": "ci-1", "real_end_at": "2026-10-04T16:00"}, db)
    assert bad.value.status_code == 400
    with pytest.raises(HTTPException) as missing:
        await payroll_v2.payroll_closure_preview(uuid.UUID(CID), {"period_start": "2026-10-01", "period_end": "2026-10-15", "source": "attendance",
                                                                         "session_ref": "otro", "real_end_at": "2026-10-05T16:00"}, db)
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_verification_context_is_unchanged_without_preview():
    class Db:
        async def execute(self, *a, **k):
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: [], first=lambda: None), scalar=lambda: True)

    core.PREVIEW_CLOSURES_052A.set(None)
    ctx = await core._cx_verification_context_049D(Db(), CID)
    assert ctx["closures"] == {}, "sin vista previa: los cierres de siempre"


@pytest.fixture
def client(monkeypatch):
    async def fake_db():
        yield SimpleNamespace()

    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(c=TestClient(app_main.app), mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


def test_new_routes_require_a_session(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    client.mp.setattr(core, "active_admin_v2_session", AsyncMock(return_value=False))
    assert client.c.get(f"/api/v1/payroll/companies/{CID}/period-activity?period_start=2026-10-01&period_end=2026-10-15").status_code == 401
    assert client.c.post(f"/api/v1/payroll/companies/{CID}/closures/preview", json={}).status_code == 401


def test_activity_route_with_admin_v2_session(client):
    client.mp.setattr(core, "active_admin_v2_session", AsyncMock(return_value=True))
    client.mp.setattr(core, "require_enabled_module", AsyncMock(side_effect=HTTPException(status_code=403)), raising=False)
    client.mp.setattr(payroll_v2, "period_activity", AsyncMock(return_value={"modules": {}, "documents": {}}))
    from app.api.v1.endpoints import company_users
    client.mp.setattr(company_users, "require_enabled_module", AsyncMock(side_effect=HTTPException(status_code=403)))
    res = client.c.get(f"/api/v1/payroll/companies/{CID}/period-activity?period_start=2026-10-01&period_end=2026-10-15")
    assert res.status_code == 200, res.text
    assert client.c.get(f"/api/v1/payroll/companies/{CID}/period-activity?period_start=2026-10-15&period_end=2026-10-01").status_code == 400


@pytest.mark.asyncio
async def test_document_is_optional_and_unique_within_the_company():
    found = SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: {"full_name": "Ana"}))
    none = SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: None))
    db = SimpleNamespace(execute=AsyncMock(return_value=found))
    with pytest.raises(HTTPException) as err:
        await employees_ep._cx_check_document_052A(db, CID, "1020")
    assert err.value.status_code == 409 and "Ana" in err.value.detail
    sql, params = db.execute.await_args.args[0].text, db.execute.await_args.args[1]
    assert "company_id = CAST(:company_id AS uuid)" in sql and params["company_id"] == CID, "solo dentro de la empresa"
    db = SimpleNamespace(execute=AsyncMock(return_value=none))
    await employees_ep._cx_check_document_052A(db, CID, "1020", "e1")
    assert "id <> CAST(:employee_id AS uuid)" in db.execute.await_args.args[0].text, "el mismo empleado puede guardar su documento"
    db = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("vacío no consulta")))
    await employees_ep._cx_check_document_052A(db, CID, None)
