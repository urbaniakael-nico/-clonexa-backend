"""Modulo SANIDAD (048K): items por empresa, planilla inmutable al cerrar,
notas posteriores, historial y PDF, alerta del dashboard, sesion obligatoria
y catalogo de Admin V2. Contra la app HTTP real con una base en memoria."""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import module_catalog_v1, sanitation

client = TestClient(app_main.app)

ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
OTRA = str(uuid.uuid4())      # empresa a la que se le activa despues, sin codigo
SIN_MODULO = str(uuid.uuid4())
EMP_A = str(uuid.uuid4())
EMP_B = str(uuid.uuid4())


class Result:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or []
        self._scalar = scalar

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def scalar(self):
        return self._scalar

    def all(self):
        return [tuple(row.values()) for row in self.rows]

    def fetchall(self):
        return [SimpleNamespace(_mapping=row) for row in self.rows]

    def first(self):
        return self.rows[0] if self.rows else None


class SanDb:
    def __init__(self):
        self.modules = {ASADERO: {"sanidad"}, OTRA: set(), SIN_MODULO: set()}
        self.items: list[dict] = []
        self.sheets: dict[tuple, dict] = {}
        self.notes: list[dict] = []
        self.employees = [
            {"id": EMP_A, "company_id": ASADERO, "full_name": "Ana Cocina", "role": "cocina", "status": "active"},
            {"id": EMP_B, "company_id": OTRA, "full_name": "Beto Otra", "role": "mesero", "status": "active"},
        ]
        self.activated_at = {ASADERO: datetime.now(timezone.utc) - timedelta(days=10)}
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        cid = str(p.get("company_id", ""))
        if "FROM company_modules cm JOIN modules m" in sql and "LOWER(m.code)" in sql:
            return Result([{"code": code} for code in self.modules.get(cid, set())])
        if sql.startswith("SELECT cm.settings, cm.activated_at"):
            return Result([{"settings": {"alert_hour": "22:00"}, "activated_at": self.activated_at.get(cid)}])
        if sql.startswith("SELECT timezone FROM companies"):
            return Result(scalar="America/Bogota")
        if sql.startswith("SELECT * FROM sanitation_items"):
            rows = [i for i in self.items if i["company_id"] == cid and (i["active"] or "active IS TRUE" not in sql)]
            return Result(sorted(rows, key=lambda i: i["position"]))
        if sql.startswith("INSERT INTO sanitation_items"):
            same = [i for i in self.items if i["company_id"] == cid]
            row = {"id": uuid.uuid4(), "company_id": cid, "section": p["section"], "label": p["label"],
                   "requires_value": p["requires_value"], "value_label": p["value_label"],
                   "position": p.get("position") or (max([i["position"] for i in same], default=0) + 10),
                   "active": p.get("active", True), "created_at": datetime.now(timezone.utc)}
            self.items.append(row)
            return Result([row])
        if sql.startswith("UPDATE sanitation_items SET position"):
            for i in self.items:
                if str(i["id"]) == p["item_id"] and i["company_id"] == cid:
                    i["position"] = p["position"]
            return Result()
        if sql.startswith("UPDATE sanitation_items SET"):
            for i in self.items:
                if str(i["id"]) == p["item_id"] and i["company_id"] == cid:
                    i.update({k: v for k, v in p.items() if k in {"section", "label", "requires_value", "value_label", "active"}})
                    return Result([i])
            return Result()
        if sql.startswith("SELECT * FROM sanitation_sheets"):
            row = self.sheets.get((cid, p["day"]))
            return Result([row] if row else [])
        if sql.startswith("SELECT note, author_name, created_at FROM sanitation_sheet_notes"):
            return Result([n for n in self.notes if n["company_id"] == cid and n["sheet_id"] == p["sheet_id"]])
        if sql.startswith("SELECT id, full_name, role FROM employees"):
            return Result([e for e in self.employees if e["company_id"] == cid])
        if sql.startswith("SELECT full_name FROM employees"):
            match = [e for e in self.employees if e["id"] == p["employee_id"] and e["company_id"] == cid]
            return Result(scalar=match[0]["full_name"] if match else None)
        if sql.startswith("INSERT INTO sanitation_sheets"):
            key = (cid, p["day"])
            current = self.sheets.get(key)
            if current and current["status"] == "closed":
                return Result()
            import json as _json
            row = {"id": (current or {}).get("id") or uuid.uuid4(), "company_id": cid, "sheet_date": p["day"],
                   "status": p["status"], "responsible_employee_id": p["responsible_id"], "responsible_name": p["responsible"],
                   "entries": _json.loads(p["entries"]), "compliance": p["compliance"],
                   "closed_at": datetime.now(timezone.utc) if p["status"] == "closed" else None, "closed_by": p["closed_by"]}
            self.sheets[key] = row
            return Result([row])
        if sql.startswith("INSERT INTO sanitation_sheet_notes"):
            self.notes.append({"company_id": cid, "sheet_id": p["sheet_id"], "note": p["note"], "author_name": p["author"],
                               "created_at": datetime.now(timezone.utc)})
            return Result()
        if sql.startswith("SELECT sheet_date, status, responsible_name"):
            rows = [s for (c, _), s in self.sheets.items() if c == cid and s["status"] == "closed"]
            return Result(sorted(rows, key=lambda s: s["sheet_date"], reverse=True))
        if sql.startswith("SELECT sheet_date FROM sanitation_sheets"):
            days = {p["today"], p["yesterday"]}
            return Result([{"sheet_date": s["sheet_date"]} for (c, d), s in self.sheets.items()
                           if c == cid and s["status"] == "closed" and d in days])
        raise AssertionError(f"SQL no esperado: {sql[:120]}")


USERS = {
    "admin-asadero": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="company_admin", full_name="Dueño Asadero", email="", status="active"),
    "mesero-asadero": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="operador", full_name="Pedro Operador", email="", status="active"),
    "admin-otra": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(OTRA), role="company_admin", full_name="Admin Otra", email="", status="active"),
    "admin-sin": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(SIN_MODULO), role="company_admin", full_name="Admin Sin", email="", status="active"),
}


@pytest.fixture
def db(monkeypatch):
    fake = SanDb()

    async def get_user(_db, token):
        user = USERS.get(token)
        if not user:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Token requerido.")
        return user

    async def fake_db():
        yield fake

    monkeypatch.setattr(deps, "get_current_company_user", get_user)
    monkeypatch.setattr(sanitation, "active_admin_v2_session", AsyncMock(return_value=False))
    monkeypatch.setattr(sanitation, "_company_details", AsyncMock(return_value={
        "name": "ASADERO EL SOCIO", "logo_url": "", "nit": "900.123.456-7", "address": "Calle 1", "phone": "300", "timezone": "America/Bogota"}))
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    yield fake
    app_main.app.dependency_overrides.pop(get_db, None)


def call(method, company, path, token=None, body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, f"/api/v1/sanitation/companies/{company}{path}", json=body, headers=headers)


def today():
    return datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("America/Bogota")).date()


ROUTES = [
    ("GET", "/items"), ("POST", "/items"), ("PATCH", f"/items/{uuid.uuid4()}"), ("POST", "/items/reorder"),
    ("GET", "/sheets"), ("GET", "/sheets/2026-09-20"), ("PUT", "/sheets/2026-09-20"), ("POST", "/sheets/2026-09-20/close"),
    ("POST", "/sheets/2026-09-20/notes"), ("GET", "/sheets/2026-09-20/pdf"), ("GET", "/status"),
]


@pytest.mark.parametrize("method,path", ROUTES)
def test_hospitality_sanidad_endpoints_require_a_session(db, method, path):
    assert call(method, ASADERO, path, body={}).status_code in (401, 403)
    other = call(method, ASADERO, path, token="admin-otra", body={})
    assert other.status_code == 403 and "tenant_not_allowed" in other.text


def test_hospitality_sanidad_company_without_module_sees_nothing(db):
    response = call("GET", SIN_MODULO, "/items", token="admin-sin")
    assert response.status_code == 403
    assert "module_not_enabled_for_tenant" in response.text
    assert call("GET", SIN_MODULO, "/status", token="admin-sin").status_code == 403


def test_hospitality_sanidad_items_are_per_company_with_a_base_list(db):
    items = call("GET", ASADERO, "/items", token="admin-asadero").json()["items"]
    assert len(items) == len(sanitation.BASE_ITEMS)
    sections = [i["section"] for i in items]
    for section in ("Cocina", "Baños", "Neveras y temperaturas", "Áreas comunes", "Manipulación de alimentos", "Residuos"):
        assert section in sections
    fridge = next(i for i in items if i["label"].startswith("Temperatura de la nevera"))
    assert fridge["requires_value"] and fridge["value_label"] == "°C"

    # activado a otra empresa (sin tocar codigo): su propia lista, independiente
    db.modules[OTRA].add("sanidad")
    other = call("GET", OTRA, "/items", token="admin-otra").json()["items"]
    assert len(other) == len(sanitation.BASE_ITEMS)
    assert {i["id"] for i in other}.isdisjoint({i["id"] for i in items})

    created = call("POST", ASADERO, "/items", token="admin-asadero",
                   body={"section": "Bodega", "label": "Estibas sin contacto con el piso"}).json()["item"]
    edited = call("PATCH", ASADERO, f"/items/{created['id']}", token="admin-asadero",
                  body={"label": "Estibas a 15 cm del piso", "active": False}).json()["item"]
    assert (edited["label"], edited["active"]) == ("Estibas a 15 cm del piso", False)
    # otra empresa no puede tocar ese item
    assert call("PATCH", OTRA, f"/items/{created['id']}", token="admin-otra", body={"label": "x"}).status_code == 404
    # reordenar
    ids = [i["id"] for i in call("GET", ASADERO, "/items", token="admin-asadero").json()["items"]]
    reordered = call("POST", ASADERO, "/items/reorder", token="admin-asadero", body={"ids": [ids[1], ids[0], *ids[2:]]}).json()["items"]
    assert [i["id"] for i in reordered][:2] == [ids[1], ids[0]]
    # solo administradores configuran
    assert call("POST", ASADERO, "/items", token="mesero-asadero", body={"section": "A", "label": "B"}).status_code == 403


def test_hospitality_sanidad_sheet_closes_signed_and_immutable(db):
    day = today().isoformat()
    draft = call("GET", ASADERO, f"/sheets/{day}", token="mesero-asadero").json()
    assert draft["sheet"]["status"] == "open"
    assert [s["name"] for s in draft["staff"]] == ["Ana Cocina"]  # solo personal de esta empresa
    entries = draft["sheet"]["entries"]
    fridge = next(e for e in entries if e["requires_value"])
    filled = [{"item_id": e["item_id"], "checked": i % 2 == 0, "observation": "ok" if i == 0 else "",
               "value": 3.5 if e["item_id"] == fridge["item_id"] else None} for i, e in enumerate(entries)]

    assert call("PUT", ASADERO, f"/sheets/{day}", token="mesero-asadero", body={"entries": filled}).status_code == 200
    # cerrar exige responsable del personal de la empresa
    no_resp = call("POST", ASADERO, f"/sheets/{day}/close", token="mesero-asadero", body={"entries": filled})
    assert no_resp.status_code == 422
    foreign = call("POST", ASADERO, f"/sheets/{day}/close", token="mesero-asadero", body={"responsible_employee_id": EMP_B, "entries": filled})
    assert foreign.status_code == 422

    closed = call("POST", ASADERO, f"/sheets/{day}/close", token="mesero-asadero",
                  body={"responsible_employee_id": EMP_A, "entries": filled}).json()["sheet"]
    checked = sum(1 for e in filled if e["checked"])
    assert closed["status"] == "closed"
    assert closed["compliance"] == round(100 * checked / len(filled), 2)
    assert closed["responsible_name"] == "Ana Cocina"
    assert closed["closed_by"] == "Pedro Operador" and closed["closed_at"]
    assert next(e for e in closed["entries"] if e["item_id"] == fridge["item_id"])["value"] == 3.5

    # inmutable
    assert call("PUT", ASADERO, f"/sheets/{day}", token="admin-asadero", body={"entries": []}).status_code == 409
    assert call("POST", ASADERO, f"/sheets/{day}/close", token="admin-asadero",
                body={"responsible_employee_id": EMP_A, "entries": []}).status_code == 409
    # correcciones: nota posterior con autor y hora
    noted = call("POST", ASADERO, f"/sheets/{day}/notes", token="admin-asadero", body={"note": "La nevera se revisó de nuevo a las 20:00: 3 °C."}).json()["sheet"]
    assert noted["notes"][0]["author"] == "Dueño Asadero" and noted["notes"][0]["created_at"]
    assert noted["compliance"] == closed["compliance"]  # la nota no cambia la planilla


def test_hospitality_sanidad_rules(db):
    future = (today() + timedelta(days=1)).isoformat()
    assert call("PUT", ASADERO, f"/sheets/{future}", token="mesero-asadero", body={"entries": []}).status_code == 422
    assert call("POST", ASADERO, f"/sheets/{today().isoformat()}/notes", token="mesero-asadero", body={"note": "x"}).status_code == 409
    assert call("GET", ASADERO, "/sheets/2026-13-40", token="mesero-asadero").status_code == 422


def test_hospitality_sanidad_history_download_and_print(db):
    day = (today() - timedelta(days=1)).isoformat()
    sheet = call("GET", ASADERO, f"/sheets/{day}", token="mesero-asadero").json()["sheet"]
    entries = [{"item_id": e["item_id"], "checked": True} for e in sheet["entries"]]
    call("POST", ASADERO, f"/sheets/{day}/close", token="mesero-asadero", body={"responsible_employee_id": EMP_A, "entries": entries})

    history = call("GET", ASADERO, "/sheets", token="mesero-asadero").json()["sheets"]
    assert [(h["date"], h["responsible_name"], h["compliance"]) for h in history] == [(day, "Ana Cocina", 100.0)]

    pdf = call("GET", ASADERO, f"/sheets/{day}/pdf", token="mesero-asadero")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert f'planilla_sanidad_{day}.pdf' in pdf.headers["content-disposition"]
    assert pdf.content[:4] == b"%PDF"
    assert call("GET", ASADERO, "/sheets/2020-01-01/pdf", token="mesero-asadero").status_code == 404


def test_hospitality_sanidad_dashboard_alert(db):
    status = call("GET", ASADERO, "/status", token="mesero-asadero").json()
    yesterday = (today() - timedelta(days=1)).isoformat()
    assert status["alert"] is True and yesterday in status["pending_dates"]
    assert "Falta diligenciar la planilla de Sanidad" in status["message"]

    sheet = call("GET", ASADERO, f"/sheets/{yesterday}", token="mesero-asadero").json()["sheet"]
    call("POST", ASADERO, f"/sheets/{yesterday}/close", token="mesero-asadero",
         body={"responsible_employee_id": EMP_A, "entries": [{"item_id": e["item_id"], "checked": True} for e in sheet["entries"]]})
    after = call("GET", ASADERO, "/status", token="mesero-asadero").json()
    assert yesterday not in after["pending_dates"]


def test_hospitality_sanidad_pdf_has_company_data_and_logo_slot():
    sheet = {"date": "2026-09-23", "responsible_name": "Ana Cocina", "compliance": 90.0, "closed_at": "2026-09-23T23:00:00+00:00",
             "closed_by": "Pedro", "entries": [{"section": "Cocina", "label": "Mesones limpios", "checked": True, "value": None},
                                               {"section": "Neveras", "label": "Temperatura", "checked": False, "value": 3.5, "value_label": "°C"}],
             "notes": [{"note": "Revisado", "author": "Dueño", "created_at": "2026-09-24T01:00:00+00:00"}]}
    pdf = sanitation.build_sheet_pdf({"name": "ASADERO EL SOCIO", "logo_url": "", "nit": "900", "address": "", "phone": "", "timezone": "America/Bogota"}, sheet)
    assert pdf[:4] == b"%PDF"
    assert b"Planilla de Sanidad 2026-09-23" in pdf  # titulo del documento


def test_hospitality_sanidad_in_admin_v2_catalog_and_migration():
    assert module_catalog_v1.MODULE_CATALOG_ES["sanidad"]["name"] == "Sanidad"
    assert 'sanidad: ["Sanidad"' in Path("app/web/admin_v2.js").read_text(encoding="utf-8")
    assert any("/api/v1/sanitation/companies/{company_id}/items" == getattr(r, "path", "") for r in app_main.app.routes)

    path = Path("migrations/versions/021p_sanidad_module.py")
    spec = importlib.util.spec_from_file_location("mig_021p", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "021o_hsp_business_day_ttm"
    assert module.TARGET_COMPANY_ID == ASADERO and module.MODULE_CODE == "sanidad"
    source = path.read_text(encoding="utf-8")
    # el modulo queda en el catalogo (tabla modules) y solo Asadero recibe company_modules
    assert "INSERT INTO modules" in source and source.count("INSERT INTO company_modules") == 1
    assert "UNIQUE (company_id, sheet_date)" in source
