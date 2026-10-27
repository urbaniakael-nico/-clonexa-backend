"""Menu video contra Postgres REAL (pgserver), la app completa y un bucket en memoria.

- Regreso de n8n: sin variable 503, sin token o token malo 401, JSON invalido 422,
  importacion de otra empresa 404; bien -> tabla "lista" con ref por plato.
- Publicar COMBINA: actualiza lo que coincide por nombre dentro de su categoria,
  crea lo nuevo con "receta pendiente" y nunca borra.
- Cupo: 3 nuevos y 3 cambios por mes; precio/nombre/descripcion no gastan; mes
  nuevo reinicia; sin cupo 409 "sin_cupo" y "Solicitar mas" llama al aviso de n8n.
- Cola: la peticion no espera; el trabajo deja remasterizada, clip y portada.
- /menu-media: lo de un plato real es publico (con rangos para el video); un
  borrador solo con firma o Admin V2.
- QR (inventory-lite): con carta_video, carta_video=true y video por plato; sin
  el interruptor, la otra empresa no cambia (solo foto si la tiene).
- Consola: 401 sin Admin V2; recorrido importar a mano -> fotos por nombre ->
  clips -> plan -> publicar.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pgserver = pytest.importorskip("pgserver")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.main as app_main  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.api.v1.endpoints import carta as carta_api  # noqa: E402
from app.api.v1.endpoints import hospitality as hsp  # noqa: E402
from app.services import brand_media  # noqa: E402
from app.services import menu_media as mm  # noqa: E402
from app.services import menu_video as mv  # noqa: E402
from app.web import admin_v2_routes  # noqa: E402
from app.web import menu_video_routes  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from tests import menu_video_fixtures as fx  # noqa: E402
from tests.test_menu_video_media_hospitality import dish_photo  # noqa: E402

TOKEN = "carta-" + "y" * 40
SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (id uuid PRIMARY KEY, name text NOT NULL, slug text, status text DEFAULT 'active',
  settings_json jsonb DEFAULT '{}'::jsonb, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text,
  category text, is_active boolean DEFAULT true);
CREATE TABLE IF NOT EXISTS company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
  module_id uuid REFERENCES modules(id), enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS inventory_items (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, sku text, name text, reference text,
  name_reference text, current_stock numeric DEFAULT 0, min_stock numeric DEFAULT 0, status text DEFAULT 'active', entry_price numeric DEFAULT 0,
  sale_price numeric DEFAULT 0, avg_cost numeric DEFAULT 0, item_type text DEFAULT 'venta_directa', purchase_unit text DEFAULT 'unidad',
  consumption_unit text DEFAULT 'unidad', units_per_purchase numeric DEFAULT 1, size_value numeric NULL, size_unit text NULL,
  allows_portions boolean DEFAULT false, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS carta_categories (id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  parent_id uuid NULL, label varchar(80) NOT NULL, position integer NOT NULL DEFAULT 0, station varchar(80) NOT NULL DEFAULT '',
  quick_notes jsonb NOT NULL DEFAULT '[]'::jsonb, requires_term boolean NOT NULL DEFAULT false, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS carta_items (id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  name varchar(220) NOT NULL, price numeric(14,2) NOT NULL DEFAULT 0, category_key varchar(80) NOT NULL DEFAULT '',
  station varchar(80) NOT NULL DEFAULT '', requires_term boolean NOT NULL DEFAULT false, allows_portions boolean NOT NULL DEFAULT false,
  kind varchar(20) NOT NULL DEFAULT 'directo', inventory_item_id uuid NULL, direct_qty numeric(14,4) NOT NULL DEFAULT 1,
  active boolean NOT NULL DEFAULT true, position integer NOT NULL DEFAULT 0, presentation varchar(60) NOT NULL DEFAULT '',
  category_id uuid NULL REFERENCES carta_categories(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS carta_recipe_lines (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL,
  carta_item_id uuid NOT NULL REFERENCES carta_items(id) ON DELETE CASCADE, inventory_item_id uuid NULL, component_item_id uuid NULL,
  quantity numeric(14,4) NOT NULL, yield_pct numeric(6,2) NOT NULL DEFAULT 100, position integer NOT NULL DEFAULT 0, unit varchar(12) NULL);
CREATE TABLE IF NOT EXISTS hospitality_orders (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, items jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar(40) NOT NULL DEFAULT 'pendiente', created_at timestamptz NOT NULL DEFAULT now(), cancelled_at timestamptz NULL);
CREATE TABLE IF NOT EXISTS hospitality_table_access (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, table_key text NOT NULL,
  table_number text, access_code text, status text, activated_at timestamptz DEFAULT now(), expires_at timestamptz, closes_with_table boolean DEFAULT false,
  created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now())
"""


class MemoryBucket:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key, data):
        self.objects[key] = data

    def get(self, key):
        if key not in self.objects:
            raise brand_media.StorageUnavailable("no existe")
        return self.objects[key]

    def delete(self, keys):
        for key in keys:
            self.objects.pop(key, None)

    def list(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]


def _migration() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    for name in ("024s_menu_video", "024t_menu_media_v2", "024u_menu_media_v3"):
        module = importlib.import_module(f"migrations.versions.{name}")
        module.op = Op()
        module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_menuvideo_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            for stmt in [s for s in SCHEMA.split(";") if s.strip()] + _migration() + _migration():  # idempotente
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


def _run(url: str, sql: str, params: dict | None = None, fetch: bool = True):
    async def go():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            rows = [dict(r) for r in result.mappings().all()] if fetch else None
        await engine.dispose()
        return rows
    return asyncio.run(go())


def _db(url: str):
    """Corre fn(db) con una sesion propia (para llamar servicios directo)."""
    def call(fn):
        async def go():
            engine = create_async_engine(url, poolclass=NullPool)
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with maker() as db:
                out = await fn(db)
            await engine.dispose()
            return out
        return asyncio.run(go())
    return call


def _company(url: str, name: str, settings: dict | None = None, carta: bool = True) -> str:
    cid = str(uuid.uuid4())
    _run(url, "INSERT INTO companies (id, name, slug) VALUES (CAST(:i AS uuid), :n, :s)", {"i": cid, "n": name, "s": name.lower()}, fetch=False)
    for code, on, extra in (("carta", carta, settings or {}), ("waiter_ordering", True, {})):
        _run(url, "INSERT INTO modules (code, name) VALUES (:c, :c) ON CONFLICT (code) DO NOTHING", {"c": code}, fetch=False)
        _run(url, """INSERT INTO company_modules (company_id, module_id, enabled, settings)
                     SELECT CAST(:i AS uuid), id, :e, CAST(:s AS jsonb) FROM modules WHERE code = :c""",
             {"i": cid, "c": code, "e": on, "s": json.dumps(extra)}, fetch=False)
    return cid


def _category(url, cid, label, parent=None) -> str:
    cat = str(uuid.uuid4())
    _run(url, """INSERT INTO carta_categories (id, company_id, parent_id, label, position)
                 VALUES (CAST(:i AS uuid), CAST(:c AS uuid), CAST(NULLIF(:p, '') AS uuid), :l, 1)""",
         {"i": cat, "c": cid, "p": parent or "", "l": label}, fetch=False)
    return cat


def _dish(url, cid, name, price, category_id) -> str:
    did = str(uuid.uuid4())
    _run(url, """INSERT INTO carta_items (id, company_id, name, price, category_id, category_key, kind)
                 VALUES (CAST(:i AS uuid), CAST(:c AS uuid), :n, :p, CAST(:cat AS uuid), '', 'preparado')""",
         {"i": did, "c": cid, "n": name, "p": price, "cat": category_id}, fetch=False)
    return did


@pytest.fixture
def client(pg_url, monkeypatch):
    _run(pg_url, "TRUNCATE companies, modules, company_modules, inventory_items, carta_categories, carta_items, carta_recipe_lines, "
                 "menu_media_assets, menu_dish_media, menu_media_jobs, menu_video_imports, menu_video_quota_log, hospitality_orders, "
                 "hospitality_table_access CASCADE", fetch=False)

    async def db_dep():
        engine = create_async_engine(pg_url, poolclass=NullPool)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            yield session
        await engine.dispose()

    bucket = MemoryBucket()
    brand_media.set_backend(bucket)
    monkeypatch.setenv(mv.TOKEN_ENV, TOKEN)
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    menu_video_routes.CACHE.items.clear()
    menu_video_routes.CACHE.used = 0
    app_main.app.dependency_overrides[get_db] = db_dep
    app_main.app.dependency_overrides[carta_api.require_carta_admin] = lambda: "Dueña de prueba"
    c = TestClient(app_main.app)
    c.bucket = bucket
    yield c
    app_main.app.dependency_overrides.pop(get_db, None)
    app_main.app.dependency_overrides.pop(carta_api.require_carta_admin, None)
    brand_media.set_backend(None)


def _admin(monkeypatch, ok=True):
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=ok))


def _jobs(url):
    """Lo que hace el trabajador de la cola, una vez por trabajo pendiente."""
    async def go(db):
        done = []
        while True:
            job = await mv.claim(db)
            if not job:
                return done
            done.append(await mv.run_job(db, job))
    return _db(url)(go)


def _photo_files(seed, side=False):
    files = [("front", (f"plato{seed}.jpg", dish_photo(seed), "image/jpeg"))]
    if side:
        files.append(("side", (f"plato{seed}-perfil.jpg", dish_photo(seed + 50), "image/jpeg")))
    return files


# ------------------------------------------------------------- callback
def _import(url, cid) -> str:
    return _db(url)(lambda db: _create_import(db, cid))


async def _create_import(db, cid):
    import_id = await mv.create_import(db, cid, "archivos", [])
    await db.commit()
    return import_id


CARTA = {"categorias": [{"nombre": "Fuertes", "subcategorias": [{"nombre": "Carnes"}]}, {"nombre": "Bebidas", "subcategorias": []}],
         "platos": [{"categoria": "Fuertes", "subcategoria": "Carnes", "nombre": "Lomo al trapo", "descripcion": "Con papa criolla",
                     "precio": "$ 42.000", "opciones": "Término"},
                    {"categoria": "Bebidas", "subcategoria": None, "nombre": "Limonada de coco", "descripcion": None, "precio": 12000,
                     "opciones": None}]}


def _callback(c, body, token=TOKEN, raw=None):
    headers = {"X-Carta-Token": token} if token is not None else {}
    if raw is not None:
        return c.post("/api/v1/menu-video/import-callback", content=raw, headers={**headers, "Content-Type": "application/json"})
    return c.post("/api/v1/menu-video/import-callback", json=body, headers=headers)


def test_callback_token_variable_y_json(client, pg_url, monkeypatch):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    job = _import(pg_url, cid)
    body = {"job_id": job, "company_id": cid, **CARTA}
    assert _callback(client, body, token=None).status_code == 401
    r = _callback(client, {"nada": 1}, token="otro")
    assert r.status_code == 401 and TOKEN not in r.text, "sin token valido no se valida el cuerpo"
    monkeypatch.delenv(mv.TOKEN_ENV)
    assert _callback(client, body).status_code == 503
    monkeypatch.setenv(mv.TOKEN_ENV, TOKEN)
    assert _callback(client, None, raw=b"{no es json").status_code == 422
    assert _callback(client, {"job_id": "x", "company_id": cid}).status_code == 422
    assert _callback(client, {"job_id": job, "company_id": cid, "platos": [{"nombre": ""}]}).status_code == 422
    other = _company(pg_url, "Otra")
    assert _callback(client, {**body, "company_id": other}).status_code == 404, "la importacion es de otra empresa"
    r = _callback(client, {"job_id": job, "company_id": cid, "resultado": CARTA})
    assert r.status_code == 200 and r.json() == {"ok": True, "status": "lista", "categorias": 2, "platos": 2}
    row = _run(pg_url, "SELECT status, table_data FROM menu_video_imports WHERE id = CAST(:i AS uuid)", {"i": job})[0]
    assert row["status"] == "lista"
    lomo = row["table_data"]["platos"][0]
    assert lomo["precio"] == 42000 and lomo["subcategoria"] == "CARNES" and uuid.UUID(lomo["ref"])
    r = _callback(client, {"job_id": job, "company_id": cid, "error": "PDF ilegible"})
    assert r.json()["status"] == "error"
    assert _run(pg_url, "SELECT error FROM menu_video_imports WHERE id = CAST(:i AS uuid)", {"i": job})[0]["error"] == "PDF ilegible"


# ------------------------------------------------------------- publicar
def test_publicar_combina_sin_borrar_y_marca_receta_pendiente(client, pg_url):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    fuertes = _category(pg_url, cid, "FUERTES")
    lomo = _dish(pg_url, cid, "Lomo al Trapo", 39000, fuertes)
    queda = _dish(pg_url, cid, "Sopa del día", 15000, fuertes)
    job = _import(pg_url, cid)
    _callback(client, {"job_id": job, "company_id": cid, **CARTA})
    table = _run(pg_url, "SELECT table_data FROM menu_video_imports WHERE id = CAST(:i AS uuid)", {"i": job})[0]["table_data"]
    plan = _db(pg_url)(lambda db: mv.plan_publish(db, cid, table))
    assert plan["counts"] == {"new": 1, "updated": 1, "unchanged": 0, "deleted": 0}
    assert plan["updated"][0]["id"] == lomo and plan["updated"][0]["changes"] == ["precio", "descripción"]
    assert plan["new_categories"] == ["BEBIDAS"]

    async def go(db):
        out = await mv.publish(db, cid, job, table)
        await db.commit()
        return out
    summary = _db(pg_url)(go)
    assert (summary["new"], summary["updated"], summary["deleted"]) == (1, 1, 0)
    rows = {r["name"]: r for r in _run(pg_url, "SELECT id::text AS id, name, price, description, recipe_pending, kind, active FROM carta_items WHERE company_id = CAST(:c AS uuid)", {"c": cid})}
    assert set(rows) == {"Lomo al Trapo", "Sopa del día", "Limonada de coco"}, "nunca borra"
    assert float(rows["Lomo al Trapo"]["price"]) == 42000 and rows["Lomo al Trapo"]["description"] == "Con papa criolla · Opciones: Término"
    assert rows["Lomo al Trapo"]["recipe_pending"] is False, "un plato que ya existia no cambia su receta"
    assert rows["Limonada de coco"]["recipe_pending"] is True and rows["Limonada de coco"]["kind"] == "preparado" and rows["Limonada de coco"]["active"]
    assert rows["Sopa del día"]["id"] == queda
    cats = [r["label"] for r in _run(pg_url, "SELECT label FROM carta_categories WHERE company_id = CAST(:c AS uuid) ORDER BY label", {"c": cid})]
    assert cats == ["BEBIDAS", "FUERTES"], "BEBIDAS se crea; FUERTES no se duplica (y CARNES no se crea: el lomo ya existia)"
    assert _run(pg_url, "SELECT status FROM menu_video_imports WHERE id = CAST(:i AS uuid)", {"i": job})[0]["status"] == "publicada"
    # guardar "¿Cómo se arma?" quita la marca
    pending = rows["Limonada de coco"]["id"]

    async def clear(db):
        await carta_api._clear_recipe_pending(db, uuid.UUID(cid), uuid.UUID(pending))
        await db.commit()
    _db(pg_url)(clear)
    assert _run(pg_url, "SELECT recipe_pending FROM carta_items WHERE id = CAST(:i AS uuid)", {"i": pending})[0]["recipe_pending"] is False


# ---------------------------------------------------------------- cupo
def test_cupo_mensual_nuevos_cambios_y_solicitar_mas(client, pg_url, monkeypatch):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    cat = _category(pg_url, cid, "FUERTES")
    dishes = [_dish(pg_url, cid, f"Plato {i}", 10000 + i, cat) for i in range(4)]
    url = lambda d: f"/api/v1/menu-video/companies/{cid}/items/{d}/photo"  # noqa: E731
    for i, dish in enumerate(dishes[:3]):
        r = client.post(url(dish), files=_photo_files(i + 1))
        assert r.status_code == 200, r.text
        assert r.json()["quota"]["new"]["left"] == 2 - i
    assert r.json()["jobs"][dishes[0]]["status"] == "en_cola", "la peticion no espera al video"
    r = client.post(url(dishes[3]), files=_photo_files(9))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sin_cupo" and r.json()["detail"]["kind"] == "nuevo"
    assert not _run(pg_url, "SELECT 1 FROM menu_dish_media WHERE dish_ref = CAST(:d AS uuid)", {"d": dishes[3]}), "sin cupo no guarda nada"
    # 057D: cambiar de nuevo dentro de 30 min (se equivoco) = el mismo cambio, no gasta otro
    age = lambda: _run(pg_url, "UPDATE menu_video_quota_log SET created_at = created_at - interval '31 minutes'", fetch=False)  # noqa: E731
    r = client.post(url(dishes[0]), files=_photo_files(19))
    assert r.json()["quota"]["changes"]["left"] == 3, "recien subida (nuevo) y cambiada en 30 min: no gasta"
    age()
    # cambiar la foto de un plato que ya tenia = "cambio"
    for i in range(3):
        r = client.post(url(dishes[0]), files=_photo_files(20 + i))
        assert r.json()["quota"]["changes"]["left"] == 2 - i
        again = client.post(url(dishes[0]), files=_photo_files(40 + i))
        assert again.json()["quota"]["changes"]["left"] == 2 - i, "dos veces en 30 minutos gasta 1"
        age()
    assert client.post(url(dishes[0]), files=_photo_files(30)).status_code == 409
    # lo que no gasta cupo: precio, nombre, descripcion, quitar foto, rehacer, elegir version
    before = _run(pg_url, "SELECT COUNT(*) AS n FROM menu_video_quota_log WHERE company_id = CAST(:c AS uuid)", {"c": cid})[0]["n"]
    r = client.put(f"/api/v1/carta/companies/{cid}/items/{dishes[1]}", json={"name": "Plato nuevo nombre", "price": 99000,
                                                                              "category_id": cat, "kind": "preparado"})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/v1/menu-video/companies/{cid}/items/{dishes[1]}/redo", json={"style": "pan"}).status_code == 200
    assert client.post(f"/api/v1/menu-video/companies/{cid}/items/{dishes[1]}/choose", json={"use_remaster": False}).status_code == 200
    assert client.delete(url(dishes[2])).status_code == 200
    assert client.delete(f"{url(dishes[1])}/side").status_code == 422, "quitar una foto que no tiene: error claro"
    r = client.delete(f"{url(dishes[1])}/front")
    assert r.status_code == 200 and r.json()["undo"]["empty"] is True, "quitar la unica foto: el plato queda con su tarjeta"
    assert dishes[1] not in r.json()["media"]
    undo = r.json()["undo"]
    r = client.post(f"{url(dishes[1])}/front/restore", json={"original": undo["original"], "remaster": undo["remaster"]})
    assert r.status_code == 200 and r.json()["media"][dishes[1]]["has_photo"], "Deshacer"
    after = _run(pg_url, "SELECT COUNT(*) AS n FROM menu_video_quota_log WHERE company_id = CAST(:c AS uuid)", {"c": cid})[0]["n"]
    assert after == before == 6
    # mes nuevo: el cupo vuelve a empezar
    state = _db(pg_url)(lambda db: mv.quota_state(db, cid, mv.next_month_start() + timedelta(hours=6)))
    assert state["new"]["left"] == 3 and state["changes"]["left"] == 3
    # cupo editable desde la consola
    _admin(monkeypatch)
    r = client.put(f"/admin-v2/api/menu-video/{cid}/quota", json={"quota_new": 5, "quota_changes": 4})
    assert r.json()["quota"]["new"] == {"used": 3, "limit": 5, "left": 2}
    _admin(monkeypatch, False)
    # Solicitar mas -> aviso de n8n
    called = AsyncMock(return_value=(True, ""))
    monkeypatch.setattr(mv, "call_n8n", called)
    r = client.post(f"/api/v1/menu-video/companies/{cid}/quota/request", json={"detalle": "10 platos más"})
    assert r.status_code == 200 and r.json()["message"] == "Te contactaremos para ampliar tu plan." and r.json()["notified"]
    target, payload = called.call_args.args
    assert target == mv.quota_webhook_url() and payload["empresa"] == "Demo" and payload["pidio"] == "10 platos más"
    assert payload["ficha_url"].endswith(f"/admin-v2plus#empresa/{cid}")
    assert _run(pg_url, "SELECT kind FROM menu_video_quota_log WHERE kind = 'solicitud'")


def test_carta_simple_foto_sin_cupo_ni_video(client, pg_url):
    cid = _company(pg_url, "Simple")  # sin carta_video
    dish = _dish(pg_url, cid, "Bandeja", 25000, _category(pg_url, cid, "FUERTES"))
    for seed in (1, 2, 3, 4):
        r = client.post(f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo", files=_photo_files(seed))
        assert r.status_code == 200
    body = r.json()
    assert body["carta_video"] is False and "quota" not in body
    media = body["media"][dish]
    assert media["photo_url"].startswith(f"/menu-media/{cid}/") and media["video_url"] == ""
    assert not _run(pg_url, "SELECT 1 FROM menu_video_quota_log") and not _run(pg_url, "SELECT 1 FROM menu_media_jobs")
    live = _run(pg_url, "SELECT COUNT(*) AS n FROM menu_media_assets WHERE discarded_at IS NULL")[0]["n"]
    marked = _run(pg_url, "SELECT COUNT(*) AS n FROM menu_media_assets WHERE discarded_at IS NOT NULL")[0]["n"]
    assert live == 2 and marked == 6, "la foto cambiada reemplaza la anterior; las viejas quedan marcadas, no borradas"
    assert len(client.bucket.objects) == 8, "el bucket aun las tiene (se borran a los 30 dias)"
    assert client.post(f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo",
                       files=[("front", ("x.jpg", b"no es foto", "image/jpeg"))]).status_code == 422
    assert client.delete(f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo").json()["media"] == {}
    assert _run(pg_url, "SELECT COUNT(*) AS n FROM menu_media_assets WHERE discarded_at IS NULL")[0]["n"] == 0
    assert len(client.bucket.objects) == 8, "nada se borra de inmediato"
    # a los 30 dias se borran del bucket
    _run(pg_url, "UPDATE menu_media_assets SET discarded_at = now() - interval '31 days'", fetch=False)
    assert _db(pg_url)(lambda db: mv.purge_discarded(db)) == 8
    assert client.bucket.objects == {} and not _run(pg_url, "SELECT 1 FROM menu_media_assets")


# ------------------------------------------------------- cola y archivos
def test_cola_clip_y_menu_media_con_rangos(client, pg_url, monkeypatch):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    dish = _dish(pg_url, cid, "Ceviche", 30000, _category(pg_url, cid, "ENTRADAS"))
    r = client.post(f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo", files=_photo_files(3, side=True))
    assert r.status_code == 200
    done = _jobs(pg_url)
    # 058A: "frente" es la foto principal (la que se anima); "perfil" va a la galeria de Detalle
    assert len(done) == 1 and done[0]["status"] == "listo" and done[0]["style"] == "vida" and done[0]["photos"] == 1
    assert done[0]["gallery"] == 1 and done[0]["path"] == "foto"
    assert done[0]["size"] == "720x1280"
    assert done[0]["clip_bytes"] < 400 * 1024
    assert done[0]["ffmpeg"], "cada trabajo guarda la versión de ffmpeg que lo hizo"
    media = client.get(f"/api/v1/menu-video/companies/{cid}/portal").json()["media"][dish]
    assert media["status"] == "listo" and media["video_url"].endswith(".mp4") and media["poster_url"].endswith(".webp")
    assert media["main_original_url"] and media["main_remaster_url"], "antes y despues"
    assert len(media["gallery_urls"]) == 1 and media["gallery"][0]["remaster_url"], "la galeria tambien se remasteriza"
    video = client.get(media["video_url"])
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4" and "immutable" in video.headers["cache-control"]
    part = client.get(media["video_url"], headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100 and part.headers["content-range"].startswith("bytes 0-99/")
    assert client.get(media["video_url"], headers={"Range": "bytes=99999999-"}).status_code == 416
    assert client.get(media["video_url"].replace(".mp4", ".webp")).status_code == 404
    other = _company(pg_url, "Otra")
    assert client.get(media["video_url"].replace(cid, other)).status_code == 404, "nunca de otra empresa"
    # "Rehacer" con otro estilo
    client.post(f"/api/v1/menu-video/companies/{cid}/items/{dish}/redo", json={"style": "pan"})
    assert _jobs(pg_url)[0]["status"] == "listo", "Rehacer (los estilos viejos usan el proceso nuevo)"
    # foto dañada en la cola: error controlado
    _run(pg_url, "UPDATE menu_dish_media SET front_remaster = NULL, side_remaster = NULL", fetch=False)
    key = _run(pg_url, "SELECT storage_key FROM menu_media_assets ma JOIN menu_dish_media dm ON dm.front_original = ma.id")[0]["storage_key"]
    client.bucket.objects[key] = b"basura"
    client.post(f"/api/v1/menu-video/companies/{cid}/items/{dish}/redo", json={"style": "zoom"})
    failed = _jobs(pg_url)[0]
    assert failed["status"] == "error" and "dañada" in failed["error"]


def test_borrador_solo_con_firma_o_admin(client, pg_url, monkeypatch):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    draft = str(uuid.uuid4())

    async def go(db):
        asset_id = await mv.save_photo(db, cid, draft, "front", dish_photo(4))
        await db.commit()
        return asset_id
    asset_id = _db(pg_url)(go)
    plain = mv.media_url(cid, asset_id)
    assert client.get(plain).status_code == 404
    assert client.get(mv.media_url(cid, asset_id, signed=True)).status_code == 200
    assert client.get(plain + "?e=9999999999&s=" + "0" * 32).status_code == 404
    _admin(monkeypatch)
    assert client.get(plain).status_code == 200


# ------------------------------------------------------------------ QR
def test_qr_inventory_lite_con_y_sin_interruptor(client, pg_url):
    on = _company(pg_url, "Con video", {"carta_video": True})
    off = _company(pg_url, "Sin video")
    d_on = _dish(pg_url, on, "Arepa", 8000, _category(pg_url, on, "ENTRADAS"))
    d_off = _dish(pg_url, off, "Arepa", 8000, _category(pg_url, off, "ENTRADAS"))
    sin_foto = _dish(pg_url, off, "Empanada", 3000, _category(pg_url, off, "FRITOS"))
    client.post(f"/api/v1/menu-video/companies/{on}/items/{d_on}/photo", files=_photo_files(5))
    _jobs(pg_url)
    hsp._storage_ready = True
    r = client.get(f"/api/v1/hospitality/companies/{on}/inventory-lite?limit=300").json()
    assert r["carta_video"] is True
    item = next(i for i in r["inventory"] if i["id"] == d_on)
    assert item["video_url"].endswith(".mp4") and item["poster_url"] and item["photo_url"] and item["active"]
    assert client.get(item["video_url"]).status_code == 200, "el QR (sin sesion) puede ver el video del plato"
    r = client.get(f"/api/v1/hospitality/companies/{off}/inventory-lite?limit=300").json()
    assert r["carta_video"] is False
    for row in r["inventory"]:
        assert "video_url" not in row and "poster_url" not in row and row["photo_url"] == ""
    assert {row["id"] for row in r["inventory"]} == {d_off, sin_foto}


# ------------------------------------------------------------- consola
def test_consola_exige_admin_v2(client, pg_url):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    for method, path in (("get", "/admin-v2/api/menu-video/companies"), ("get", "/admin-v2/api/menu-video/health"),
                         ("get", f"/admin-v2/api/menu-video/{cid}"), ("post", f"/admin-v2/api/menu-video/{cid}/imports"),
                         ("put", f"/admin-v2/api/menu-video/{cid}/quota")):
        assert getattr(client, method)(path).status_code == 401, path


def test_consola_recorrido_completo(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    cid = _company(pg_url, "Demo", {"carta_video": True})
    _company(pg_url, "Sin carta", carta=False)
    companies = client.get("/admin-v2/api/menu-video/companies").json()["companies"]
    assert [c["name"] for c in companies] == ["Demo"], "solo empresas con Carta"
    health = client.get("/admin-v2/api/menu-video/health").json()
    assert health["ffmpeg"] and health["token"] is True and TOKEN not in json.dumps(health)
    # importar: si n8n falla, la tabla se llena a mano
    monkeypatch.setattr(mv, "call_n8n", AsyncMock(return_value=(False, "n8n respondió 500.")))
    r = client.post(f"/admin-v2/api/menu-video/{cid}/imports", files=[("files", ("carta.pdf", b"%PDF-1.4 carta", "application/pdf"))])
    assert r.status_code == 200 and r.json()["import"]["status"] == "error" and "a mano" in r.json()["import"]["error"]
    assert "key" not in r.json()["import"]["files"][0], "la llave del bucket no sale"
    assert client.post(f"/admin-v2/api/menu-video/{cid}/imports", files=[("files", ("x.txt", b"hola", "text/plain"))]).status_code == 422
    imp = client.post(f"/admin-v2/api/menu-video/{cid}/imports", data={"manual": "true"}).json()["import"]
    r = client.put(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/table", json={"table": CARTA})
    table = r.json()["import"]["table_data"]
    assert r.json()["import"]["status"] == "lista" and len(table["platos"]) == 2
    lomo, limonada = table["platos"]
    # fotos: varias a la vez, emparejadas por nombre de archivo
    files = [("files", ("lomo-al-trapo.jpg", dish_photo(11), "image/jpeg")), ("files", ("lomo al trapo perfil.jpg", dish_photo(12), "image/jpeg")),
             ("files", ("IMG_0001.jpg", dish_photo(13), "image/jpeg")), ("files", ("danada.jpg", b"\xff\xd8\xffroto", "image/jpeg"))]
    r = client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/photos", files=files).json()
    by_file = {x["file"]: x for x in r["results"]}
    assert by_file["lomo-al-trapo.jpg"]["ref"] == lomo["ref"] and by_file["lomo-al-trapo.jpg"]["role"] == "main"
    assert by_file["lomo al trapo perfil.jpg"]["role"] == "gallery", "las demas fotos van a la galeria de Detalle"
    assert by_file["IMG_0001.jpg"]["ref"] is None and not by_file["danada.jpg"]["ok"]
    # reasignar a mano la suelta a la limonada
    loose = by_file["IMG_0001.jpg"]["asset_id"]
    r = client.put(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/photos/{loose}", json={"ref": limonada["ref"], "role": "main"})
    assert r.json()["media"][limonada["ref"]]["has_photo"]
    # remasterizar y crear clips (todos)
    r = client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/process", json={"style": "auto"}).json()
    assert r["queued"] == 2
    styles = sorted(j["style"] for j in _jobs(pg_url))
    assert styles == ["vida", "vida"], "por defecto: Vida (la foto principal se anima)"
    state = client.get(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}").json()
    assert all(m["status"] == "listo" and "?e=" in m["video_url"] for m in state["media"].values()), "vista previa firmada"
    # elegir la original en la limonada rehace su clip
    client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/dish/{limonada['ref']}/choose", json={"use_remaster": False})
    assert len(_jobs(pg_url)) == 1
    # publicar = combinar
    plan = client.get(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/plan").json()["plan"]
    assert plan["counts"] == {"new": 2, "updated": 0, "unchanged": 0, "deleted": 0}
    summary = client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/publish").json()["summary"]
    assert summary["new"] == 2 and summary["deleted"] == 0
    assert client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/publish").status_code == 409
    _admin(monkeypatch, False)
    hsp._storage_ready = True
    inventory = client.get(f"/api/v1/hospitality/companies/{cid}/inventory-lite").json()["inventory"]
    assert all(i["video_url"].endswith(".mp4") for i in inventory), "lo publicado ya es lo que ve el QR"
    assert all(client.get(i["video_url"]).status_code == 200 for i in inventory)
    assert not _run(pg_url, "SELECT 1 FROM menu_video_quota_log"), "lo que hace Clonexa desde la consola no gasta el cupo del cliente"


# ------------------------------------------------------- 057C carta QR nueva
def _photo(client, cid, dish, seed=7):
    r = client.post(f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo", files=_photo_files(seed))
    assert r.status_code == 200, r.text


def test_carta_qr_nueva_marca_lo_mas_pedido_y_agotado(client, pg_url, monkeypatch):
    from app.api.v1.endpoints import waiter_ordering

    # la carta de siempre (respaldo) no cambia: aqui no se prueba
    monkeypatch.setattr(waiter_ordering, "build_waiter_menu", AsyncMock(return_value={"categories": [], "menu_emojis": False}))
    cid = _company(pg_url, "Brasa", {"carta_video": True, "qr_token": "token-de-la-carta-brasa-0001"})
    entradas = _category(pg_url, cid, "ENTRADAS")
    fuertes = _category(pg_url, cid, "FUERTES")
    lomo = _dish(pg_url, cid, "Lomo", 46000, fuertes)
    sopa = _dish(pg_url, cid, "Sopa", 15000, entradas)
    oculto = _dish(pg_url, cid, "Oculto", 9000, fuertes)
    _run(pg_url, "UPDATE carta_items SET active = false WHERE id = CAST(:i AS uuid)", {"i": oculto}, fetch=False)
    _run(pg_url, "UPDATE carta_items SET requires_term = true WHERE id = CAST(:i AS uuid)", {"i": lomo}, fetch=False)
    _photo(client, cid, lomo)
    _jobs(pg_url)
    other = _company(pg_url, "Otra")
    rows = ((cid, [{"menu_item_id": sopa, "quantity": 3}], "now()", "NULL"),
            (cid, [{"product_id": lomo, "quantity": "1"}], "now()", "NULL"),
            (cid, [{"menu_item_id": lomo, "quantity": 9}], "now()", "now()"),                       # anulado: no cuenta
            (cid, [{"menu_item_id": lomo, "quantity": 9}], "now() - interval '40 days'", "NULL"),   # viejo
            (other, [{"menu_item_id": lomo, "quantity": 50}], "now()", "NULL"))                      # otra empresa
    for company, items, when, cancelled in rows:
        _run(pg_url, f"INSERT INTO hospitality_orders (company_id, items, created_at, cancelled_at) VALUES (CAST(:c AS uuid), CAST(:i AS jsonb), {when}, {cancelled})",
             {"c": company, "i": json.dumps(items)}, fetch=False)
    body = client.get("/api/v1/carta/public/token-de-la-carta-brasa-0001").json()
    assert isinstance(body["categories"], list), "lo de siempre sigue (respaldo)"
    app = body["app"]
    assert app["company"]["name"] == "Brasa" and app["video"] is True and app["terms"] == ["Crudo", "Medio", "3/4", "Bien cocinado"]
    assert {"background", "primary", "bg", "font"} <= set(app["theme"]), "la marca del portal"
    ids = [p["id"] for p in app["products"]]
    assert oculto not in ids and set(ids) == {lomo, sopa}, "agotado u oculto: no aparece"
    assert app["top"] == [sopa, lomo] and app["top_source"] == "ventas", "ventas de 30 días de ESA empresa, sin anulados"
    by_key = {c["key"]: c for c in app["categories"]}
    assert "/menu-media/" in by_key[fuertes]["image_url"], "sin imagen de categoría: la portada de su primer plato"
    assert by_key[entradas]["image_url"] == "", "sin ninguna foto: la tarjeta usa los colores de la marca (nunca el ícono genérico)"
    lomo_p = next(p for p in app["products"] if p["id"] == lomo)
    assert lomo_p["requires_term"] is True and lomo_p["video_url"].endswith(".mp4")
    assert '"cost' not in json.dumps(app) and '"stock' not in json.dumps(app), "nunca costos ni existencias"
    _run(pg_url, "DELETE FROM hospitality_orders", fetch=False)
    assert client.get("/api/v1/carta/public/token-de-la-carta-brasa-0001").json()["app"]["top"] == [lomo], "sin ventas: los platos con video"


def test_carta_de_la_mesa_exige_la_clave(client, pg_url):
    cid = _company(pg_url, "Brasa", {"carta_video": False})
    _dish(pg_url, cid, "Lomo", 46000, _category(pg_url, cid, "FUERTES"))
    url = f"/api/v1/menu-video/qr/{cid}/carta"
    assert client.post(url, json={"table": "Mesa 4", "access_code": "ABC12"}).status_code == 403, "mesa no activada"
    _run(pg_url, """INSERT INTO hospitality_table_access (company_id, table_key, table_number, access_code, status, expires_at)
                    VALUES (CAST(:c AS uuid), 'mesa 4', 'Mesa 4', 'ABC12', 'active', now() + interval '1 hour')""", {"c": cid}, fetch=False)
    assert client.post(url, json={"table": "Mesa 4", "access_code": "ZZZZZ"}).status_code == 403, "clave mala"
    r = client.post(url, json={"table": "Mesa 4", "access_code": "abc12"})
    assert r.status_code == 200, r.text
    assert r.json()["table"] == "Mesa 4" and r.json()["video"] is False
    assert all(p["video_url"] == "" for p in r.json()["products"]), "sin carta_video: fotos"
    hsp._storage_ready = True
    assert client.get(f"/api/v1/hospitality/companies/{cid}/inventory-lite").json()["carta_app"] is True


def test_volver_a_publicar_cambio_de_video(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    cid = _company(pg_url, "Demo", {"carta_video": True})
    imp = client.post(f"/admin-v2/api/menu-video/{cid}/imports", data={"manual": "true"}).json()["import"]
    table = client.put(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/table", json={"table": CARTA}).json()["import"]["table_data"]
    client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/photos", files=[("files", ("lomo-al-trapo.jpg", dish_photo(11), "image/jpeg"))])
    client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/process", json={"style": "zoom"})
    _jobs(pg_url)
    first = client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/publish").json()
    assert first["summary"]["new"] == 2
    assert first["plan"]["counts"] == {"new": 0, "updated": 0, "unchanged": 2, "deleted": 0}, "el resumen se recalcula"
    again = client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/publish")
    assert again.status_code == 409 and again.json()["detail"] == "No hay cambios para publicar."
    hsp._storage_ready = True
    _admin(monkeypatch, False)
    before = {i["name"]: i["video_url"] for i in client.get(f"/api/v1/hospitality/companies/{cid}/inventory-lite").json()["inventory"]}
    _admin(monkeypatch)
    # cambiar el video de 1 plato (foto nueva en la consola) y volver a publicar (el caso de la captura)
    lomo = next(d for d in table["platos"] if d["nombre"] == "Lomo al trapo")
    client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/photos", files=[("files", ("lomo-al-trapo.jpg", dish_photo(21), "image/jpeg"))])
    client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/process", json={"refs": [lomo["ref"]], "style": "pan"})
    _jobs(pg_url)
    plan = client.get(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/plan").json()["plan"]
    assert plan["counts"] == {"new": 0, "updated": 1, "unchanged": 1, "deleted": 0}
    assert plan["updated"][0]["nombre"] == "Lomo al trapo" and plan["updated"][0]["changes"] == ["foto/video"]
    second = client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/publish")
    assert second.status_code == 200, second.text
    summary = second.json()["summary"]
    assert (summary["new"], summary["updated"]) == (0, 1)
    assert summary["history"][0]["new"] == 2 and summary["published_at"] > summary["history"][0]["published_at"], "aviso con la ÚLTIMA publicación"
    assert client.get(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}").json()["import"]["summary"]["updated"] == 1
    _admin(monkeypatch, False)
    after = {i["name"]: i["video_url"] for i in client.get(f"/api/v1/hospitality/companies/{cid}/inventory-lite").json()["inventory"]}
    assert after["Lomo al trapo"] and after["Lomo al trapo"] != before["Lomo al trapo"], "el QR muestra el video nuevo"
    assert client.get(after["Lomo al trapo"]).status_code == 200
    assert client.get(before["Lomo al trapo"]).status_code == 404, "el video viejo ya no se sirve"
    assert _run(pg_url, "SELECT COUNT(*) AS n FROM carta_items WHERE company_id = CAST(:c AS uuid)", {"c": cid})[0]["n"] == 2, "nunca duplica ni borra"


# ------------------------------------------- 057D/058A cambiar / quitar fotos
def test_consola_cambiar_quitar_deshacer_quitar_video_y_rehacer_todos(client, pg_url, monkeypatch):
    _admin(monkeypatch)
    cid = _company(pg_url, "Demo", {"carta_video": True})
    imp = client.post(f"/admin-v2/api/menu-video/{cid}/imports", data={"manual": "true"}).json()["import"]
    table = client.put(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/table", json={"table": CARTA}).json()["import"]["table_data"]
    lomo = next(d for d in table["platos"] if d["nombre"] == "Lomo al trapo")["ref"]
    base = f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/dish/{lomo}"
    state = lambda: client.get(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}").json()["media"][lomo]  # noqa: E731
    for role, seed in (("main", 51), ("gallery", 52), ("gallery", 53)):
        r = client.post(f"{base}/photo/{role}", files={"file": (f"{role}.jpg", dish_photo(seed), "image/jpeg")})
        assert r.status_code == 200, r.text
    _jobs(pg_url)
    m = state()
    assert m["roles"] == ["main", "gallery"] and len(m["gallery"]) == 2 and m["status"] == "listo"
    result = _run(pg_url, "SELECT result FROM menu_media_jobs ORDER BY finished_at DESC LIMIT 1")[0]["result"]
    assert result["photos"] == 1 and result["gallery"] == 2 and result["path"] == "foto", "con 3 fotos NO hay pase: se anima la principal"
    client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/publish")
    item = _run(pg_url, "SELECT id::text AS id FROM carta_items WHERE name = 'Lomo al trapo'")[0]["id"]
    clip_of = lambda: _run(pg_url, "SELECT clip_asset::text AS c FROM menu_dish_media WHERE dish_ref = CAST(:d AS uuid)", {"d": item})[0]["c"]  # noqa: E731
    old_clip = clip_of()
    # Cambiar la principal YA publicada: el clip viejo se sigue viendo hasta que el nuevo esta listo
    r = client.post(f"{base}/photo/main", files={"file": ("nuevo.jpg", dish_photo(60), "image/jpeg")})
    assert r.status_code == 200 and r.json()["published"][lomo] == item
    assert clip_of() == old_clip
    _jobs(pg_url)
    assert clip_of() != old_clip
    assert _run(pg_url, "SELECT discarded_at IS NOT NULL AS m FROM menu_media_assets WHERE id = CAST(:a AS uuid)", {"a": old_clip})[0]["m"], "el viejo queda marcado"
    # Quitar una de la galeria: el video NO se rehace; Deshacer la devuelve en su lugar
    first, second = [g["id"] for g in state()["gallery"]]
    r = client.delete(f"{base}/photo/gallery:{first}")
    assert r.status_code == 200 and r.json()["undo"]["empty"] is False and r.json()["undo"]["index"] == 0
    undo = r.json()["undo"]
    assert _jobs(pg_url) == [], "quitar de la galeria no toca el video"
    assert [g["id"] for g in state()["gallery"]] == [second]
    assert client.post(f"{base}/photo/gallery:{first}/restore", json={"original": undo["original"], "remaster": undo["remaster"], "index": 0}).status_code == 200
    assert [g["id"] for g in state()["gallery"]] == [first, second]
    # Cambiar una de la galeria
    r = client.post(f"{base}/photo/gallery:{second}", files={"file": ("otra.jpg", dish_photo(61), "image/jpeg")})
    assert r.status_code == 200 and [g["id"] for g in state()["gallery"]][0] == first and second not in [g["id"] for g in state()["gallery"]]
    _jobs(pg_url)
    # Camino 1: subir video -> modo video; estilo/fondo/velocidad + Rehacer (no gasta cupo)
    r = client.post(f"{base}/photo/video", files={"file": ("plato.mov", fx.dish_video("vertical", seconds=4, audio=True), "video/quicktime")})
    assert r.status_code == 200, r.text
    assert state()["mode"] == "video" and state()["has_video_source"]
    done = _jobs(pg_url)
    assert done[0]["status"] == "listo" and done[0]["path"] == "video" and done[0]["stabilizer"] in ("vidstab", "deshake"), done
    assert done[0]["clip_bytes"] < 1024 * 1024
    r = client.post(f"{base}/options", json={"background": "oscurecer", "speed": "rapido"})
    assert r.status_code == 200 and state()["options"]["background"] == "oscurecer" and state()["options"]["speed"] == "rapido"
    assert _jobs(pg_url)[0]["background"] == "oscurecer"
    # volver a la foto animada con otro estilo
    client.post(f"{base}/options", json={"mode": "foto", "style": "giro"})
    assert _jobs(pg_url)[0]["style"] == "giro" and state()["mode"] == "foto"
    # Quitar el video subido: queda la foto
    r = client.delete(f"{base}/photo/video")
    assert r.status_code == 200 and not state()["has_video_source"] and state()["mode"] == "foto"
    _jobs(pg_url)
    # Quitar video (el clip): queda la foto
    m = client.delete(f"{base}/video").json()["media"][lomo]
    assert m["video_url"] == "" and m["has_photo"] and m["status"] == "sin_video"
    # Rehacer todos: no gasta cupo del cliente
    assert client.post(f"/admin-v2/api/menu-video/{cid}/regenerate").json()["queued"] >= 1
    _jobs(pg_url)
    assert state()["video_url"]
    assert not _run(pg_url, "SELECT 1 FROM menu_video_quota_log"), "lo que rehace Clonexa no gasta cupo"
    # quitar todo -> sin foto ni video (tarjeta en el QR)
    for role in ["main"] + [f"gallery:{g['id']}" for g in state()["gallery"]]:
        r = client.delete(f"{base}/photo/{role}")
    assert r.json()["undo"]["empty"] is True and lomo not in r.json()["media"]
    hsp._storage_ready = True
    _admin(monkeypatch, False)
    inv = {i["name"]: i for i in client.get(f"/api/v1/hospitality/companies/{cid}/inventory-lite").json()["inventory"]}
    assert inv["Lomo al trapo"]["video_url"] == "" and inv["Lomo al trapo"]["photo_url"] == "", "sin fotos: la tarjeta del plato"


def test_portal_quitar_cambiar_queda_en_la_auditoria(client, pg_url, monkeypatch):
    from app.services import admin_audit

    entries = []
    monkeypatch.setattr(admin_audit, "write_entry", AsyncMock(side_effect=lambda e: entries.append(e)))
    cid = _company(pg_url, "Demo", {"carta_video": True})
    dish = _dish(pg_url, cid, "Pizza", 30000, _category(pg_url, cid, "PIZZAS"))
    url = f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo"
    assert client.post(url, files=[("main", ("pizza.jpg", dish_photo(70), "image/jpeg"))]).status_code == 200
    assert client.delete(f"{url}/main").status_code == 200
    assert [(e["company_id"], e["surface"], e["detail"]["foto"], e["detail"]["fotos"]) for e in entries] == [
        (cid, "portal", "subió", "principal"), (cid, "portal", "quitó", "principal")]
    assert entries[0]["actor"].startswith("Dueña de prueba") and entries[0]["detail"]["plato"] == "Pizza"


# ---------------------------------------------------------- 058A 2 caminos
def test_migracion_024u_conserva_todas_las_fotos(client, pg_url):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    ids = {k: str(uuid.uuid4()) for k in ("tf", "tr", "ff", "fr", "sf", "a_side", "b_top", "b_side")}
    full, only_side, top_side = (str(uuid.uuid4()) for _ in range(3))
    _run(pg_url, """INSERT INTO menu_dish_media (company_id, dish_ref, top_original, top_remaster, front_original, front_remaster, side_original)
                    VALUES (CAST(:c AS uuid), CAST(:d AS uuid), CAST(:tf AS uuid), CAST(:tr AS uuid), CAST(:ff AS uuid), CAST(:fr AS uuid), CAST(:sf AS uuid))""",
         {"c": cid, "d": full, **{k: ids[k] for k in ("tf", "tr", "ff", "fr", "sf")}}, fetch=False)
    _run(pg_url, "INSERT INTO menu_dish_media (company_id, dish_ref, side_original) VALUES (CAST(:c AS uuid), CAST(:d AS uuid), CAST(:s AS uuid))",
         {"c": cid, "d": only_side, "s": ids["a_side"]}, fetch=False)
    _run(pg_url, """INSERT INTO menu_dish_media (company_id, dish_ref, top_original, side_original)
                    VALUES (CAST(:c AS uuid), CAST(:d AS uuid), CAST(:t AS uuid), CAST(:s AS uuid))""",
         {"c": cid, "d": top_side, "t": ids["b_top"], "s": ids["b_side"]}, fetch=False)
    for stmt in _migration():  # 024u otra vez sobre datos viejos (idempotente)
        _run(pg_url, stmt, fetch=False)
    rows = {r["d"]: r for r in _run(pg_url, """SELECT dish_ref::text AS d, front_original::text AS f, front_remaster::text AS fr, gallery,
                                                       top_original, side_original FROM menu_dish_media WHERE company_id = CAST(:c AS uuid)""", {"c": cid})}
    assert rows[full]["f"] == ids["ff"] and rows[full]["fr"] == ids["fr"], "frente pasa a principal"
    assert rows[full]["gallery"] == [{"original": ids["tf"], "remaster": ids["tr"]}, {"original": ids["sf"], "remaster": ""}], "las demas, a la galeria"
    assert rows[only_side]["f"] == ids["a_side"] and rows[only_side]["gallery"] == [], "sin frente: la que haya es la principal"
    assert rows[top_side]["f"] == ids["b_top"] and rows[top_side]["gallery"] == [{"original": ids["b_side"], "remaster": ""}]
    assert all(r["top_original"] is None and r["side_original"] is None for r in rows.values())
    kept = set()
    for r in rows.values():
        kept |= {r["f"], r["fr"]} | {g["original"] for g in r["gallery"]} | {g["remaster"] for g in r["gallery"]}
    assert set(ids.values()) <= kept, "ninguna foto se pierde"


def test_portal_camino_1_video_cupo_y_opciones(client, pg_url):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    dish = _dish(pg_url, cid, "Picada", 52000, _category(pg_url, cid, "PICADAS"))
    url = f"/api/v1/menu-video/companies/{cid}/items/{dish}"
    raw = fx.dish_video("horizontal", seconds=4, hevc=True, audio=True)
    r = client.post(f"{url}/photo", files=[("video", ("IMG_0042.MOV", raw, "video/quicktime"))], data={"background": "desenfocar", "speed": "normal"})
    assert r.status_code == 200, r.text
    assert r.json()["quota"]["new"]["used"] == 1, "subir el video = 1 (plato nuevo)"
    done = _jobs(pg_url)
    assert done[0]["path"] == "video" and done[0]["status"] == "listo" and done[0]["clip_bytes"] < 1024 * 1024
    media = client.get(f"/api/v1/menu-video/companies/{cid}/portal").json()["media"][dish]
    assert media["mode"] == "video" and media["video_url"] and media["photo_url"] == media["poster_url"], "solo video: la portada hace de foto"
    assert client.get(mv.media_url(cid, _run(pg_url, "SELECT video_original::text AS v FROM menu_dish_media")[0]["v"])).status_code == 404, \
        "el video subido nunca es publico (solo su clip editado)"
    # estilo / fondo / velocidad: no gasta cupo
    r = client.post(f"{url}/options", json={"background": "ninguno", "speed": "lento", "start": 0.5, "length": 3})
    assert r.status_code == 200 and r.json()["quota"]["changes"]["used"] == 0
    # cambiar el video dos veces en 30 min = 1 cambio
    for _ in range(2):
        assert client.post(f"{url}/photo", files=[("video", ("v.mp4", fx.dish_video("vertical", seconds=3, audio=False), "video/mp4"))]).status_code == 200
    assert client.get(f"/api/v1/menu-video/companies/{cid}/portal").json()["quota"]["changes"]["used"] == 0,         "cambiar otra vez dentro de 30 min del primero = el mismo cambio"
    # mas de 30 s: mensaje claro y no gasta
    r = client.post(f"{url}/photo", files=[("video", ("largo.mp4", fx.long_video(31), "video/mp4"))])
    assert r.status_code == 422 and "máximo es 30 s" in r.json()["detail"]
    # carta sin video: subir video no se permite
    simple = _company(pg_url, "Simple")
    d2 = _dish(pg_url, simple, "Arepa", 8000, _category(pg_url, simple, "ENTRADAS"))
    r = client.post(f"/api/v1/menu-video/companies/{simple}/items/{d2}/photo", files=[("video", ("v.mp4", raw, "video/mp4"))])
    assert r.status_code == 403


def test_galeria_en_detalle_de_la_carta(client, pg_url):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    dish = _dish(pg_url, cid, "Lomo", 42000, _category(pg_url, cid, "FUERTES"))
    files = [("main", ("lomo.jpg", dish_photo(80), "image/jpeg")), ("gallery", ("lomo-2.jpg", dish_photo(81), "image/jpeg")),
             ("gallery", ("lomo-3.jpg", dish_photo(82), "image/jpeg"))]
    assert client.post(f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo", files=files).status_code == 200
    _jobs(pg_url)

    async def go(db):
        from app.services import carta_app
        return await carta_app.payload(db, cid)
    data = _db(pg_url)(go)
    product = next(p for p in data["products"] if p["id"] == dish)
    assert product["video_url"] and len(product["gallery_urls"]) == 2, "las otras fotos van a Detalle"
    assert product["photo_url"] not in product["gallery_urls"]


# ------------------------------------------------------------- 058A QR y piezas
def _links_company(pg_url, name="Brasa", extra=None):
    return _company(pg_url, name, {"carta_video": True, "carta_qr_piezas": True, **(extra or {})})


def test_qr_y_piezas_solo_con_interruptor(client, pg_url):
    off = _company(pg_url, "Sin interruptor", {"carta_video": True})
    assert client.get(f"/api/v1/carta-links/companies/{off}").status_code == 403
    assert client.get("/api/v1/carta/companies/" + off).json().get("qr_piezas") in (False, None)
    cid = _links_company(pg_url)
    data = client.get(f"/api/v1/carta-links/companies/{cid}").json()
    assert set(data["kinds"]) == {"mesa", "domicilio", "llevar", "mesero"} and all(k["on"] for k in data["kinds"].values())
    assert len(data["mesas"]) == 12 and "/ordenar?company_id=" in data["mesas"][0]["url"] and "&q=" in data["mesas"][0]["url"]
    assert "/pedir?k=" in data["kinds"]["domicilio"]["url"] and "/carta-mesero?company_id=" in data["kinds"]["mesero"]["url"]
    assert data["delivery"]["fee_text"] == "El restaurante te confirma el valor del domicilio."
    # la empresa sin interruptor: el QR de mesa sigue igual que hoy (sin codigo)
    async def guard(db):
        from app.services import carta_links
        await carta_links.mesa_guard(db, off, "")
        return True
    assert _db(pg_url)(guard)


def _order_items(dish):
    return [{"inventory_item_id": dish, "quantity": 2, "term": "3/4", "observations": "sin cebolla"}]


@pytest.fixture
def orders(monkeypatch):
    """create_hospitality_order de verdad se prueba en Domicilios/QR mesa; aqui se
    revisa lo que el QR le manda (destino, datos y consentimiento)."""
    from app.api.v1.endpoints import carta_links as links_api
    from app.api.v1.endpoints.hospitality import HospitalityOrderItemIn
    from app.services import carta_links

    carta_links._RATE.clear()
    calls = []

    async def priced(db, company_id, items):
        return [HospitalityOrderItemIn(name="Lomo", quantity=i.quantity, unit_price=42000, inventory_item_id=i.inventory_item_id, station="cocina")
                for i in items]

    async def create(company_id, payload, db, delivery=None):
        oid = str(uuid.uuid4())
        calls.append({"company_id": str(company_id), "payload": payload, "delivery": delivery, "id": oid})
        total = sum(float(i.quantity) * float(i.unit_price) for i in payload.items)
        meta = {"delivery": delivery} if delivery else {}
        await db.execute(text("""INSERT INTO hospitality_orders (id, company_id, items, order_number, status, total, metadata)
                                 VALUES (CAST(:i AS uuid), CAST(:c AS uuid), '[]'::jsonb, :n, 'pendiente', :t, CAST(:m AS jsonb))"""),
                         {"i": oid, "c": str(company_id), "n": f"QR-{len(calls):03d}", "t": total, "m": json.dumps(meta)})
        await db.commit()
        return {"order": {"id": oid, "order_number": f"QR-{len(calls):03d}", "total": total}}

    monkeypatch.setattr(links_api, "_priced_order_items", priced)
    monkeypatch.setattr(links_api, "create_hospitality_order", create)
    yield calls
    carta_links._RATE.clear()


def _dom_body(dish, **extra):
    return {"name": "Laura Gómez", "phone": "300 123 4567", "address": "Calle 10 # 5-20", "barrio": "Centro", "reference": "Portería",
            "payment": "transferencia", "note": "Timbre dañado", "consent": True, "website": "", "items": _order_items(dish), **extra}


def test_qr_domicilio_llega_a_domicilios_con_datos_y_consentimiento(client, pg_url, orders):
    for col in ("order_number text", "status text", "total numeric", "metadata jsonb"):
        _run(pg_url, f"ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS {col}", fetch=False)
    cid = _links_company(pg_url)
    dish = _dish(pg_url, cid, "Lomo", 42000, _category(pg_url, cid, "FUERTES"))
    data = client.get(f"/api/v1/carta-links/companies/{cid}").json()
    token = data["kinds"]["domicilio"]["url"].split("k=")[1]
    page = client.get(f"/api/v1/carta-links/public/{token}").json()
    assert page["kind"] == "domicilio" and page["policy_url"].startswith("/politica-de-datos?c=") and page["carta"]["company"]["name"] == "Brasa"
    assert page["delivery"]["fee_text"] == "El restaurante te confirma el valor del domicilio."
    # sin autorizacion de datos no sale; el campo oculto frena robots
    r = client.post(f"/api/v1/carta-links/public/{token}/orders", json=_dom_body(dish, consent=False))
    assert r.status_code == 422 and "autorización" in r.json()["detail"]
    assert client.post(f"/api/v1/carta-links/public/{token}/orders", json=_dom_body(dish, website="http://spam")).status_code == 422
    assert orders == []
    r = client.post(f"/api/v1/carta-links/public/{token}/orders", json=_dom_body(dish))
    assert r.status_code == 201, r.text
    out = r.json()
    call = orders[0]
    assert call["company_id"] == cid and call["payload"].source == "domicilio" and call["payload"].table.startswith("Domicilio ")
    d = call["delivery"]
    assert d["customer_name"] == "Laura Gómez" and d["customer_phone"] == "300 123 4567" and d["address"] == "Calle 10 # 5-20"
    assert d["barrio"] == "Centro" and d["reference"] == "Portería" and d["payment_status"] == "contra_entrega" and d["payment_kind"] == "transfer"
    assert d["consent"]["accepted"] is True and "Autorizo el tratamiento" in d["consent"]["text"] and d["fee_pending"] is True
    assert call["payload"].items[0].quantity == 2, "precios del servidor, nunca del cliente"
    assert out["fee_text"] == "El restaurante te confirma el valor del domicilio." and out["status_text"] == "Recibido"
    # estado del pedido solo con su clave
    st = client.get(f"/api/v1/carta-links/public/{token}/orders/{out['order_id']}?s={out['key']}").json()
    assert st["status_text"] == "Recibido"
    assert client.get(f"/api/v1/carta-links/public/{token}/orders/{out['order_id']}?s=otraclave123").status_code == 404
    _run(pg_url, "UPDATE hospitality_orders SET status = 'alistando'", fetch=False)
    assert client.get(f"/api/v1/carta-links/public/{token}/orders/{out['order_id']}?s={out['key']}").json()["status_text"] == "En preparación"
    # limite por celular: 2 por minuto
    assert client.post(f"/api/v1/carta-links/public/{token}/orders", json=_dom_body(dish)).status_code == 201
    r = client.post(f"/api/v1/carta-links/public/{token}/orders", json=_dom_body(dish))
    assert r.status_code == 429 and "Espera un minuto" in r.json()["detail"]
    # politica de datos con el nombre del restaurante
    policy = client.get(page["policy_url"])
    assert policy.status_code == 200 and "Brasa" in policy.text and "1581" in policy.text


def test_qr_para_llevar_a_caja_y_cocina_y_limite_por_ip(client, pg_url, orders):
    for col in ("order_number text", "status text", "total numeric", "metadata jsonb"):
        _run(pg_url, f"ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS {col}", fetch=False)
    cid = _links_company(pg_url)
    dish = _dish(pg_url, cid, "Lomo", 42000, _category(pg_url, cid, "FUERTES"))
    token = client.get(f"/api/v1/carta-links/companies/{cid}").json()["kinds"]["llevar"]["url"].split("k=")[1]
    body = {"name": "Pedro", "phone": "3105550000", "pickup": "7:30 p. m.", "items": _order_items(dish)}
    assert client.post(f"/api/v1/carta-links/public/{token}/orders", json={**body, "pickup": ""}).status_code == 422
    r = client.post(f"/api/v1/carta-links/public/{token}/orders", json=body)
    assert r.status_code == 201, r.text
    p = orders[0]["payload"]
    assert orders[0]["delivery"] is None, "no es domicilio: va a Caja y cocina como una cuenta"
    assert p.table.startswith("Para llevar Pedro") and p.source == "para_llevar" and "recoge 7:30 p. m." in p.notes and "3105550000" in p.notes
    meta = _run(pg_url, "SELECT metadata FROM hospitality_orders")[0]["metadata"]
    assert meta["takeaway"]["pickup"] == "7:30 p. m." and meta["takeaway"]["phone"] == "3105550000"
    # limite por IP: 4 por minuto (celulares distintos)
    codes = [client.post(f"/api/v1/carta-links/public/{token}/orders", json={**body, "phone": f"31055500{i:02d}"}).status_code for i in range(1, 6)]
    assert codes[:3] == [201, 201, 201] and codes[-1] == 429


def test_qr_apagar_y_regenerar_enlace(client, pg_url, orders):
    cid = _links_company(pg_url)
    data = client.get(f"/api/v1/carta-links/companies/{cid}").json()
    old = data["kinds"]["domicilio"]["url"].split("k=")[1]
    assert client.get(f"/api/v1/carta-links/public/{old}").status_code == 200
    # apagar Domicilio
    r = client.put(f"/api/v1/carta-links/companies/{cid}/kinds/domicilio", json={"on": False})
    assert r.json()["kinds"]["domicilio"]["on"] is False
    assert client.get(f"/api/v1/carta-links/public/{old}").status_code == 403
    client.put(f"/api/v1/carta-links/companies/{cid}/kinds/domicilio", json={"on": True})
    # regenerar: el viejo deja de funcionar, el nuevo si
    new = client.post(f"/api/v1/carta-links/companies/{cid}/kinds/domicilio/regenerate").json()["kinds"]["domicilio"]["url"].split("k=")[1]
    assert new != old and client.get(f"/api/v1/carta-links/public/{old}").status_code == 404
    assert client.get(f"/api/v1/carta-links/public/{new}").status_code == 200
    assert client.get(f"/pedir?k={new}").status_code == 200
    # mesa: antes de regenerar, los QR de mesa viejos (sin codigo) sirven; despues, solo el nuevo
    _run(pg_url, """INSERT INTO hospitality_table_access (company_id, table_key, table_number, access_code, status, expires_at)
                    VALUES (CAST(:c AS uuid), 'mesa 1', 'Mesa 1', 'ABC12', 'active', now() + interval '1 day')""", {"c": cid}, fetch=False)
    body = {"table": "Mesa 1", "access_code": "ABC12"}
    assert client.post(f"/api/v1/menu-video/qr/{cid}/carta", json=body).status_code == 200
    mesa_url = client.post(f"/api/v1/carta-links/companies/{cid}/kinds/mesa/regenerate").json()["mesas"][0]["url"]
    code = mesa_url.split("&q=")[1]
    r = client.post(f"/api/v1/menu-video/qr/{cid}/carta", json=body)
    assert r.status_code == 403 and "QR nuevo" in r.json()["detail"]
    assert client.post(f"/api/v1/menu-video/qr/{cid}/carta", json={**body, "link": code}).status_code == 200
    client.put(f"/api/v1/carta-links/companies/{cid}/kinds/mesa", json={"on": False})
    r = client.post(f"/api/v1/menu-video/qr/{cid}/carta", json={**body, "link": code})
    assert r.status_code == 403 and "apagado" in r.json()["detail"]


def test_qr_mesero_sin_sesion_no_abre_y_con_sesion_agrega_a_su_mesa(client, pg_url, monkeypatch):
    from app.api.v1.endpoints import carta_links as links_api
    from app.api.v1.endpoints import waiter_ordering

    cid = _links_company(pg_url)
    url = client.get(f"/api/v1/carta-links/companies/{cid}").json()["kinds"]["mesero"]["url"]
    k = url.split("k=")[1]
    assert client.get(f"/api/v1/carta-links/companies/{cid}/mesero?k={k}").status_code in (401, 403), "sin sesion de mesero no abre"
    assert client.get(f"/carta-mesero?company_id={cid}&k={k}").status_code == 200
    mesero = SimpleNamespace(id=uuid.uuid4(), full_name="Mesero Uno")
    app_main.app.dependency_overrides[waiter_ordering._require_mesero] = lambda: mesero
    monkeypatch.setattr(waiter_ordering, "waiter_my_tables", AsyncMock(return_value={"ok": True, "tables": [{"table_number": "Mesa 4", "total": 30000, "status": "entregada"}]}))
    try:
        r = client.get(f"/api/v1/carta-links/companies/{cid}/mesero?k={k}")
        assert r.status_code == 200 and r.json()["tables"][0]["table_number"] == "Mesa 4" and r.json()["mesero"] == "Mesero Uno"
        assert r.json()["carta"]["company"]["name"] == "Brasa"
        assert client.get(f"/api/v1/carta-links/companies/{cid}/mesero?k=" + "x" * 24).status_code == 404, "enlace viejo o falso"
        client.put(f"/api/v1/carta-links/companies/{cid}/kinds/mesero", json={"on": False})
        assert client.get(f"/api/v1/carta-links/companies/{cid}/mesero?k={k}").status_code == 403
        other = _links_company(pg_url, "Otra")
        assert client.get(f"/api/v1/carta-links/companies/{other}/mesero?k={k}").status_code == 404, "nunca el QR de otra empresa"
    finally:
        app_main.app.dependency_overrides.pop(waiter_ordering._require_mesero, None)
    assert links_api  # noqa: B018 (el mesero agrega con POST /waiter-ordering/orders de siempre)


def test_qr_con_logo_y_piezas_se_leen_con_dos_marcas(client, pg_url, monkeypatch):
    import io as _io
    import zipfile

    from app.api.v1.endpoints import carta_links as links_api
    from app.services import carta_links

    def logo(color):
        img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((10, 10, 290, 290), fill=color)
        buf = _io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    brands = {}
    a = _links_company(pg_url, "Brasa & Maíz")
    b = _links_company(pg_url, "Azul Mar")
    brands[a] = {"name": "Brasa & Maíz", "primary": "#c2410c", "logo": logo((194, 65, 12, 255))}
    brands[b] = {"name": "Azul Mar", "primary": "#1e3a8a", "logo": logo((30, 58, 138, 255))}
    monkeypatch.setattr(links_api, "_brand", AsyncMock(side_effect=lambda db, cid: brands[cid]))
    dish = _dish(pg_url, a, "Hamburguesa", 32000, _category(pg_url, a, "FUERTES"))
    _photo(client, a, dish)
    previews = {}
    for cid in (a, b):
        r = client.get(f"/api/v1/carta-links/companies/{cid}/qr/domicilio.png")
        assert r.status_code == 200 and r.headers["x-qr-verified"] == "1" and r.headers["x-qr-variant"] == "marca_logo"
        img = Image.open(_io.BytesIO(r.content)).convert("RGB")
        assert carta_links.read_qr(img).startswith("http") and "/pedir?k=" in carta_links.read_qr(img)
        for piece in ("hablador", "sticker", "instagram"):
            p = client.get(f"/api/v1/carta-links/companies/{cid}/piezas/{piece}.png")
            assert p.status_code == 200 and p.headers["x-qr-verified"] == "1", (cid, piece)
            previews[(cid, piece)] = p.content
        z = client.get(f"/api/v1/carta-links/companies/{cid}/piezas.zip")
        assert z.status_code == 200 and z.headers["x-qr-verified"] == "1"
        names = zipfile.ZipFile(_io.BytesIO(z.content)).namelist()
        assert len([n for n in names if n.startswith("habladores/")]) == 12
        assert "sticker-domicilio-8x8cm.pdf" in names and "instagram-pide-aqui-1080x1350.png" in names
        assert {"qr/qr-domicilio.png", "qr/qr-llevar.png", "qr/qr-mesero.png", "qr/qr-mesa-1.png"} <= set(names)
        pdf = zipfile.ZipFile(_io.BytesIO(z.content)).read("habladores/hablador-mesa-1.pdf")
        assert pdf.startswith(b"%PDF") and b"/MediaBox [ 0 0 283" in pdf, "10 x 15 cm (283 x 425 pt)"
        sticker = zipfile.ZipFile(_io.BytesIO(z.content)).read("sticker-domicilio-8x8cm.pdf")
        assert b"/MediaBox [ 0 0 226" in sticker, "8 x 8 cm (226 pt)"
        ig = Image.open(_io.BytesIO(zipfile.ZipFile(_io.BytesIO(z.content)).read("instagram-pide-aqui-1080x1350.png")))
        assert ig.size == (1080, 1350)
    assert previews[(a, "sticker")] != previews[(b, "sticker")], "cada marca con sus colores"
    sticker_a = Image.open(_io.BytesIO(previews[(a, "sticker")])).convert("RGB")
    assert sticker_a.getpixel((5, 5)) == (194, 65, 12), "fondo con el color de la marca"
    # contraste insuficiente (amarillo): el QR sale oscuro sobre claro y se sigue leyendo
    image, info = carta_links.qr_image("https://x.co/pedir?k=" + "a" * 24, "#facc15", brands[a]["logo"])
    assert info["verified"] and info["color"] == "#111111"
