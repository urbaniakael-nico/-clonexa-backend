"""Consola v2+ · Empresas: tipo, clonar como demo y eliminar definitivo.

La logica corre contra un almacen en memoria con varias empresas y llaves
foraneas (sin base de datos real en las pruebas). Lo obligatorio:
- tras clonar, ninguna tabla operativa de la demo tiene filas y ninguna fila
  de la demo conserva el company_id de origen;
- eliminar no borra filas de otra empresa, respeta los candados y la
  simulacion no borra nada.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

import app.main as app_main
from app.api.deps import get_db
from app.services import company_kind as kinds
from app.services import company_lifecycle as lc
from app.web import admin_v2plus_companies as ep

SOURCE = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"  # The Time Machine (viva)
OTHER = str(uuid.uuid4())
OPERATIONAL = ("hospitality_orders", "employees", "payroll_periods", "inventory_items", "inventory_movements",
               "clonexa_access_sessions", "company_users", "company_bot_instances", "mini_panel_sales_records",
               "shoplink_customer_profiles", "hospitality_product_images", "hospitality_categories",
               "carta_recipe_lines", "workforce_attendance_events", "company_settings")


class MemoryStore(lc.Store):
    """Tablas en memoria con llaves foraneas SIN cascada: (hija, columna, madre)."""

    def __init__(self, tables, fks=()):
        self.tables = {name: [dict(r) for r in rows] for name, rows in tables.items()}
        self.fks = list(fks)
        self.deleted_company = None
        self.inserted = set()

    def _cols(self, table):
        cols = {}
        for row in self.tables.get(table, []):
            cols.update({k: ("uuid" if k.endswith("id") else "jsonb" if isinstance(v, (dict, list)) else "text") for k, v in row.items()})
        cols.setdefault("company_id", "uuid")
        return cols

    async def columns(self, tables):
        return {t: self._cols(t) for t in tables if t in self.tables}

    async def rows(self, table, company_id):
        return [dict(r) for r in self.tables[table] if str(r.get("company_id")) == str(company_id)]

    async def insert(self, table, row, types):
        self.tables[table].append(dict(row))
        if "id" in row:
            self.inserted.add((table, str(row["id"])))

    def has_inserted(self, table, row_id):
        return (table, str(row_id)) in self.inserted

    async def company_tables(self):
        return sorted(self.tables)

    async def count(self, table, company_id):
        return len(await self.rows(table, company_id))

    async def delete(self, table, company_id):
        doomed = [r for r in self.tables[table] if str(r.get("company_id")) == str(company_id)]
        ids = {str(r.get("id")) for r in doomed}
        for child, col, parent in self.fks:
            if parent == table and any(str(r.get(col)) in ids for r in self.tables.get(child, [])):
                raise IntegrityError("DELETE", {}, Exception(f"{child}.{col} -> {table}"))
        self.tables[table] = [r for r in self.tables[table] if r not in doomed]
        return len(doomed)

    async def delete_company(self, company_id):
        self.deleted_company = str(company_id)


def _dataset():
    def rows(cid, n=1, **extra):
        return [{"id": str(uuid.uuid4()), "company_id": cid, **extra} for _ in range(n)]

    parent = {"id": str(uuid.uuid4()), "company_id": SOURCE, "parent_id": None, "label": "Bebidas"}
    child = {"id": str(uuid.uuid4()), "company_id": SOURCE, "parent_id": parent["id"], "label": "Cervezas"}
    item = {"id": str(uuid.uuid4()), "company_id": SOURCE, "category_id": child["id"], "name": "Club Colombia",
            "inventory_item_id": str(uuid.uuid4()), "price": "9000"}
    tables = {
        "company_package_assignments": rows(SOURCE, package_id=str(uuid.uuid4()), status="active", settings={}),
        "company_modules": rows(SOURCE, 2, module_id=str(uuid.uuid4()), enabled=True,
                                settings={"cashier_redesign": True, "telegram_bot_token": "123:ABC",
                                          "qr_config": {"title": "Pide aqui", "webhook_secret": "x", "api_key": "k"}}),
        "company_branding": rows(SOURCE, logo_url="data:image/png;base64," + "A" * 5000, primary_color="#ff0000",
                                 custom_css_json={"font_family": "Sora"}),
        "company_localization": rows(SOURCE, default_language="es"),
        "company_crm_layout": rows(SOURCE, settings_json={"density": "compact"}),
        "company_crm_launchpad_cards": rows(SOURCE, 3, card_code="ventas", settings_json={}),
        "roles": rows(SOURCE, 2, code="mesero", name="Mesero"),
        # hija ANTES que la madre: el clon debe ordenar el arbol
        "carta_categories": [child, parent] + rows(OTHER, label="Otra"),
        "carta_items": [item],
    }
    for table in OPERATIONAL:
        tables[table] = rows(SOURCE, 2, secret_token="tok") + rows(OTHER, 1)
    for table in lc.CLONE_TABLES:
        tables.setdefault(table, []).extend(rows(OTHER, 1) if table not in ("carta_categories",) else [])
    return tables, parent, child, item


def _walk(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)
    else:
        yield value


# ---------------------------------------------------------------- clonar ---
@pytest.mark.asyncio
async def test_clone_copies_only_configuration_and_never_the_source_company_id():
    tables, parent, child, item = _dataset()
    store = MemoryStore(tables)
    demo = str(uuid.uuid4())
    copied = await lc.clone_config(store, SOURCE, demo)

    # OBLIGATORIO 1: ninguna tabla operativa de la demo tiene filas.
    for table in OPERATIONAL:
        assert await store.count(table, demo) == 0, table
    # OBLIGATORIO 2: ninguna fila de la demo conserva el company_id de origen (en ningun valor).
    for table, rows in store.tables.items():
        for row in rows:
            if str(row.get("company_id")) == demo:
                assert SOURCE not in [str(v) for v in _walk(row)], (table, row)
    # Lo de la lista blanca si se copio, con ids nuevos.
    assert copied == {"company_package_assignments": 1, "company_modules": 2, "company_branding": 1,
                      "company_localization": 1, "company_crm_layout": 1, "company_crm_launchpad_cards": 3,
                      "roles": 2, "carta_categories": 2, "carta_items": 1}
    source_ids = {str(r["id"]) for rows in tables.values() for r in rows}
    for table in lc.CLONE_TABLES:
        for row in await store.rows(table, demo):
            assert str(row["id"]) not in source_ids, table
    # El origen y la otra empresa quedan iguales.
    for table in lc.CLONE_TABLES:
        assert await store.count(table, SOURCE) == len([r for r in tables[table] if r["company_id"] == SOURCE])
        assert await store.count(table, OTHER) == len([r for r in tables[table] if r["company_id"] == OTHER])


@pytest.mark.asyncio
async def test_clone_rebuilds_the_menu_tree_without_images_or_inventory():
    tables, parent, child, item = _dataset()
    store = MemoryStore(tables)
    demo = str(uuid.uuid4())
    await lc.clone_config(store, SOURCE, demo)
    cats = {r["label"]: r for r in await store.rows("carta_categories", demo)}
    assert cats["Bebidas"]["parent_id"] is None
    assert cats["Cervezas"]["parent_id"] == cats["Bebidas"]["id"], "el arbol apunta a los ids nuevos"
    [plate] = await store.rows("carta_items", demo)
    assert plate["category_id"] == cats["Cervezas"]["id"] and plate["name"] == "Club Colombia"
    assert plate["inventory_item_id"] is None, "el inventario no se copia"
    assert await store.count("hospitality_product_images", demo) == 0
    [brand] = await store.rows("company_branding", demo)
    assert brand["logo_url"] is None, "sin imagenes pesadas (data:)"
    assert brand["primary_color"] == "#ff0000"


@pytest.mark.asyncio
async def test_clone_strips_tokens_and_secrets_from_module_settings():
    tables, *_ = _dataset()
    store = MemoryStore(tables)
    demo = str(uuid.uuid4())
    await lc.clone_config(store, SOURCE, demo)
    for row in await store.rows("company_modules", demo):
        keys = [k for k in _walk(row["settings"]) if isinstance(k, str)]
        assert "cashier_redesign" in keys and "qr_config" in keys
        assert not any(lc.SECRET_KEY.search(k) for k in keys), keys
    assert "123:ABC" not in [v for r in await store.rows("company_modules", demo) for v in _walk(r)]


def test_clone_whitelist_is_explicit_and_never_operational():
    assert lc.CLONE_TABLES == ("company_package_assignments", "company_modules", "company_branding",
                               "company_localization", "company_crm_layout", "company_crm_launchpad_cards",
                               "roles", "carta_categories", "carta_items")
    forbidden = {"hospitality_orders", "employees", "payroll_periods", "inventory_items", "clonexa_access_sessions",
                 "company_users", "company_bot_instances", "hospitality_product_images", "shoplink_customer_profiles"}
    assert not forbidden & set(lc.CLONE_TABLES)


def test_clone_settings_keep_only_brand_and_localization():
    settings = {"branding": {"logo_url": "data:image/png;base64,AAA", "primary_color": "#123456"},
                "client_settings": {"language": "es", "api_token": "zzz"},
                "security": {"ip_allowlist": {"enabled": True}}, "kind": "registrada",
                "whatsapp": {"access_token": "secret"}, "experience": {"branding": {"x": 1}, "other": 2}}
    out = lc.clone_settings(settings, SOURCE)
    assert set(out) == {"branding", "client_settings", "experience", "kind", "cloned_from"}
    assert out["kind"] == "demo" and out["branding"]["logo_url"] == "" and out["branding"]["primary_color"] == "#123456"
    assert out["client_settings"] == {"language": "es"} and out["experience"] == {"branding": {"x": 1}}


# --------------------------------------------------------------- eliminar ---
@pytest.mark.asyncio
async def test_purge_dry_run_deletes_nothing():
    tables, *_ = _dataset()
    store = MemoryStore(tables)
    before = {t: list(r) for t, r in store.tables.items()}
    plan = await lc.purge_plan(store, SOURCE)
    assert store.tables == before and store.deleted_company is None
    by = {p["table"]: p for p in plan}
    assert by["hospitality_orders"]["rows"] == 2 and by["hospitality_product_images"]["images"] is True
    assert "companies" not in by


@pytest.mark.asyncio
async def test_purge_deletes_only_this_company_in_foreign_key_order():
    tables, *_ = _dataset()
    store = MemoryStore(tables, fks=[("hospitality_orders", "employee_ref", "employees")])
    emp = store.tables["employees"][0]
    store.tables["hospitality_orders"][0]["employee_ref"] = emp["id"]
    other_before = {t: [r for r in rows if r["company_id"] == OTHER] for t, rows in store.tables.items()}
    deleted = await lc.purge_execute(store, SOURCE)
    for table, rows in store.tables.items():
        assert not [r for r in rows if r["company_id"] == SOURCE], table
        assert [r for r in rows if r["company_id"] == OTHER] == other_before[table], f"{table}: tocó otra empresa"
    assert store.deleted_company == SOURCE
    assert {"table": "hospitality_product_images", "rows": 2, "images": True} in deleted


@pytest.mark.asyncio
async def test_purge_keeps_audit_tables():
    store = MemoryStore({"admin_audit_log": [{"id": "1", "company_id": SOURCE}], "employees": [{"id": "2", "company_id": SOURCE}]})
    await lc.purge_execute(store, SOURCE)
    assert store.tables["admin_audit_log"] == [{"id": "1", "company_id": SOURCE}]


@pytest.mark.asyncio
async def test_purge_blocked_by_an_outside_reference_raises():
    store = MemoryStore({"employees": [{"id": "e1", "company_id": SOURCE}], "externa": []},
                        fks=[("ajena", "employee_id", "employees")])
    store.tables["ajena"] = [{"id": "x", "employee_id": "e1"}]  # sin company_id: nunca se borra
    with pytest.raises(lc.PurgeBlocked):
        await lc.purge_execute(store, SOURCE)
    assert store.deleted_company is None


# ------------------------------------------------------------- candados ---
def _company(cid, kind, status="active", name="Demo Bar"):
    return {"id": cid, "name": name, "slug": "demo-bar", "status": status, "kind": kind, "settings_json": {"kind": kind}}


def test_purge_locks():
    live = next(iter(kinds.LIVE_COMPANY_IDS))
    assert ep.purge_lock(_company(live, "registrada", "archived"))[0] == 403
    assert ep.purge_lock(_company(live, "demo", "archived"))[0] == 403, "protegida aunque la marquen demo"
    assert ep.purge_lock(_company(OTHER, "registrada", "active"))[0] == 409
    assert ep.purge_lock(_company(OTHER, "registrada", "inactive"))[0] == 409
    assert ep.purge_lock(_company(OTHER, "registrada", "archived")) is None
    for status in ("active", "inactive", "archived"):
        assert ep.purge_lock(_company(OTHER, "demo", status)) is None


# ------------------------------------------------------------- endpoints ---
class FakeDb:
    def __init__(self):
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.executed = []

    async def execute(self, statement, params=None):
        self.executed.append((" ".join(str(statement).split()), params))
        return SimpleNamespace()


@pytest.fixture
def api(monkeypatch):
    db = FakeDb()

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    yield SimpleNamespace(db=db, client=TestClient(app_main.app), mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path", ["kind", "clone-demo", "purge"])
def test_new_endpoints_require_the_admin_v2_session(api, path):
    api.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    load = AsyncMock()
    api.mp.setattr(ep, "load_company", load)
    response = api.client.post(f"/admin-v2/api/companies/{OTHER}/{path}", json={"kind": "demo", "dry_run": True},
                               follow_redirects=False)
    assert response.status_code == 401
    load.assert_not_awaited()
    assert api.db.executed == []


def test_purge_endpoint_dry_run_and_confirmation(api):
    tables, *_ = _dataset()
    store = MemoryStore(tables)
    api.mp.setattr(ep, "store_for", lambda db: store)
    api.mp.setattr(ep, "load_company", AsyncMock(return_value=_company(SOURCE.replace("2", "3"), "demo", name="Demo Bar")))
    sim = api.client.post(f"/admin-v2/api/companies/{OTHER}/purge", json={"dry_run": True}).json()
    assert sim["dry_run"] is True and sim["confirmation_required"] == {"confirm_name": "Demo Bar"}
    assert store.deleted_company is None
    bad = api.client.post(f"/admin-v2/api/companies/{OTHER}/purge", json={"dry_run": False, "confirm_name": "demo bar"})
    assert bad.status_code == 400 and store.deleted_company is None
    api.db.commit.assert_not_awaited()


def test_purge_endpoint_executes_in_one_transaction(api):
    cid = str(uuid.uuid4())
    store = MemoryStore({"employees": [{"id": "1", "company_id": cid}], "roles": [{"id": "2", "company_id": OTHER}]})
    api.mp.setattr(ep, "store_for", lambda db: store)
    api.mp.setattr(ep, "load_company", AsyncMock(return_value=_company(cid, "demo")))
    done = api.client.post(f"/admin-v2/api/companies/{cid}/purge", json={"dry_run": False, "confirm_name": "Demo Bar"}).json()
    assert done["executed"] is True and done["total_rows"] == 1 and store.deleted_company == cid
    assert store.tables["roles"] == [{"id": "2", "company_id": OTHER}]
    api.db.commit.assert_awaited_once()


def test_purge_endpoint_rolls_back_everything_when_blocked(api):
    cid = str(uuid.uuid4())
    store = MemoryStore({"employees": [{"id": "e1", "company_id": cid}]}, fks=[("ajena", "employee_id", "employees")])
    store.tables["ajena"] = [{"id": "x", "employee_id": "e1"}]
    api.mp.setattr(ep, "store_for", lambda db: store)
    api.mp.setattr(ep, "load_company", AsyncMock(return_value=_company(cid, "demo")))
    blocked = api.client.post(f"/admin-v2/api/companies/{cid}/purge", json={"dry_run": False, "confirm_name": "Demo Bar"})
    assert blocked.status_code == 409 and "No se borró nada" in blocked.json()["detail"]
    api.db.rollback.assert_awaited_once()
    api.db.commit.assert_not_awaited()


@pytest.mark.parametrize("company, status", [
    (lambda: _company(next(iter(kinds.LIVE_COMPANY_IDS)), "registrada", "archived"), 403),
    (lambda: _company(OTHER, "registrada", "active"), 409),
])
def test_purge_endpoint_locks(api, company, status):
    api.mp.setattr(ep, "load_company", AsyncMock(return_value=company()))
    store = MemoryStore({})
    api.mp.setattr(ep, "store_for", lambda db: store)
    for dry in (True, False):
        response = api.client.post(f"/admin-v2/api/companies/{OTHER}/purge", json={"dry_run": dry, "confirm_name": "Demo Bar"})
        assert response.status_code == status


def test_kind_change_rules(api):
    api.mp.setattr(ep, "load_company", AsyncMock(return_value=_company(OTHER, "demo")))
    ask = api.client.post(f"/admin-v2/api/companies/{OTHER}/kind", json={"kind": "registrada"})
    assert ask.status_code == 409 and ask.json()["confirmation_required"] is True
    assert api.db.executed == []
    ok = api.client.post(f"/admin-v2/api/companies/{OTHER}/kind", json={"kind": "registrada", "confirm": True})
    assert ok.status_code == 200 and ok.json()["kind"] == "registrada"
    sql, params = api.db.executed[-1]
    assert "jsonb_set" in sql and "'{kind}'" in sql and params == {"id": OTHER, "kind": "registrada"}
    api.db.commit.assert_awaited_once()
    assert api.client.post(f"/admin-v2/api/companies/{OTHER}/kind", json={"kind": "otra"}).status_code == 400
    live = next(iter(kinds.LIVE_COMPANY_IDS))
    api.mp.setattr(ep, "load_company", AsyncMock(return_value=_company(live, "registrada")))
    assert api.client.post(f"/admin-v2/api/companies/{live}/kind", json={"kind": "demo"}).status_code == 403


def test_clone_endpoint_creates_demo_with_owner(api):
    tables, *_ = _dataset()
    store = MemoryStore(tables)
    new_id = uuid.uuid4()
    api.mp.setattr(ep, "store_for", lambda db: store)
    api.mp.setattr(ep, "load_company", AsyncMock(return_value=_company(SOURCE, "registrada", name="The Time Machine")))
    create = AsyncMock(return_value=(new_id, "demo@clonexa.app"))
    api.mp.setattr(ep, "create_demo_company_and_owner", create)
    body = {"name": "TTM Demo", "slug": "ttm-demo", "owner_full_name": "Dueño Demo", "owner_email": "demo@clonexa.app",
            "owner_password": "Clonexa-demo-a7k2!"}
    data = api.client.post(f"/admin-v2/api/companies/{SOURCE}/clone-demo", json=body).json()
    assert data["ok"] is True and data["kind"] == "demo" and data["company_id"] == str(new_id)
    assert data["copied"]["carta_items"] == 1 and data["owner_email"] == "demo@clonexa.app"
    assert all(n == 0 for t in OPERATIONAL for n in [len([r for r in store.tables[t] if r["company_id"] == str(new_id)])])
    api.db.commit.assert_awaited_once()


def test_clone_endpoint_rolls_back_when_copy_fails(api):
    api.mp.setattr(ep, "load_company", AsyncMock(return_value=_company(SOURCE, "registrada")))
    api.mp.setattr(ep, "create_demo_company_and_owner", AsyncMock(return_value=(uuid.uuid4(), "a@b.co")))

    async def boom(*_a, **_k):
        raise RuntimeError("fallo a mitad")

    api.mp.setattr(ep.lifecycle, "clone_config", boom)
    body = {"name": "X", "slug": "x", "owner_full_name": "Y", "owner_email": "a@b.co", "owner_password": "12345678"}
    with pytest.raises(RuntimeError):
        api.client.post(f"/admin-v2/api/companies/{SOURCE}/clone-demo", json=body)
    api.db.rollback.assert_awaited_once()
    api.db.commit.assert_not_awaited()


def test_company_kind_defaults():
    live = next(iter(kinds.LIVE_COMPANY_IDS))
    assert kinds.resolve_kind(live, {}) == "registrada"
    assert kinds.resolve_kind(OTHER, {}) == "demo"
    assert kinds.resolve_kind(OTHER, {"kind": "Registrada"}) == "registrada"
    assert kinds.resolve_kind(live, {"kind": "demo"}) == "demo"
    assert kinds.resolve_kind(OTHER, {"kind": "raro"}) == "demo"


def test_kind_migration_is_idempotent_and_short():
    import ast
    from pathlib import Path

    source = Path("migrations/versions/023a_company_kind.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    values = {n.targets[0].id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
              and isinstance(n.value, ast.Constant) and isinstance(n.targets[0], ast.Name)}
    assert values["revision"] == "023a_company_kind" and len(values["revision"]) <= 32
    assert values["down_revision"] == "022p_admin_passkeys"
    assert "NOT IN ('demo', 'registrada')" in source, "solo llena las que no tienen kind"
    for cid in kinds.LIVE_COMPANY_IDS:
        assert cid in source
