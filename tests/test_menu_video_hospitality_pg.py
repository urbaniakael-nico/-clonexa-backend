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
  quantity numeric(14,4) NOT NULL, yield_pct numeric(6,2) NOT NULL DEFAULT 100, position integer NOT NULL DEFAULT 0, unit varchar(12) NULL)
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

    module = importlib.import_module("migrations.versions.024s_menu_video")
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
                 "menu_media_assets, menu_dish_media, menu_media_jobs, menu_video_imports, menu_video_quota_log CASCADE", fetch=False)

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
    # cambiar la foto de un plato que ya tenia = "cambio"
    for i in range(3):
        assert client.post(url(dishes[0]), files=_photo_files(20 + i)).json()["quota"]["changes"]["left"] == 2 - i
    assert client.post(url(dishes[0]), files=_photo_files(30)).status_code == 409
    # lo que no gasta cupo: precio, nombre, descripcion, quitar foto, rehacer, elegir version
    before = _run(pg_url, "SELECT COUNT(*) AS n FROM menu_video_quota_log WHERE company_id = CAST(:c AS uuid)", {"c": cid})[0]["n"]
    r = client.put(f"/api/v1/carta/companies/{cid}/items/{dishes[1]}", json={"name": "Plato nuevo nombre", "price": 99000,
                                                                              "category_id": cat, "kind": "preparado"})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/v1/menu-video/companies/{cid}/items/{dishes[1]}/redo", json={"style": "pan"}).status_code == 200
    assert client.post(f"/api/v1/menu-video/companies/{cid}/items/{dishes[1]}/choose", json={"use_remaster": False}).status_code == 200
    assert client.delete(url(dishes[2])).status_code == 200
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
    assert len(client.bucket.objects) == 2, "la foto cambiada reemplaza la anterior (original + remasterizada)"
    assert client.post(f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo",
                       files=[("front", ("x.jpg", b"no es foto", "image/jpeg"))]).status_code == 422
    assert client.delete(f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo").json()["media"] == {}
    assert client.bucket.objects == {}


# ------------------------------------------------------- cola y archivos
def test_cola_clip_y_menu_media_con_rangos(client, pg_url, monkeypatch):
    cid = _company(pg_url, "Demo", {"carta_video": True})
    dish = _dish(pg_url, cid, "Ceviche", 30000, _category(pg_url, cid, "ENTRADAS"))
    r = client.post(f"/api/v1/menu-video/companies/{cid}/items/{dish}/photo", files=_photo_files(3, side=True))
    assert r.status_code == 200
    done = _jobs(pg_url)
    assert len(done) == 1 and done[0]["status"] == "listo" and done[0]["style"] == "front_side"
    assert done[0]["clip_bytes"] < 400 * 1024
    media = client.get(f"/api/v1/menu-video/companies/{cid}/portal").json()["media"][dish]
    assert media["status"] == "listo" and media["video_url"].endswith(".mp4") and media["poster_url"].endswith(".webp")
    assert media["front_original_url"] and media["front_remaster_url"], "antes y despues"
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
    assert _jobs(pg_url)[0]["style"] == "pan"
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
    assert by_file["lomo-al-trapo.jpg"]["ref"] == lomo["ref"] and by_file["lomo-al-trapo.jpg"]["role"] == "front"
    assert by_file["lomo al trapo perfil.jpg"]["role"] == "side"
    assert by_file["IMG_0001.jpg"]["ref"] is None and not by_file["danada.jpg"]["ok"]
    # reasignar a mano la suelta a la limonada
    loose = by_file["IMG_0001.jpg"]["asset_id"]
    r = client.put(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/photos/{loose}", json={"ref": limonada["ref"], "role": "front"})
    assert r.json()["media"][limonada["ref"]]["has_photo"]
    # remasterizar y crear clips (todos)
    r = client.post(f"/admin-v2/api/menu-video/{cid}/imports/{imp['id']}/process", json={"style": "auto"}).json()
    assert r["queued"] == 2
    styles = sorted(j["style"] for j in _jobs(pg_url))
    assert styles == ["front_side", "zoom"]
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
