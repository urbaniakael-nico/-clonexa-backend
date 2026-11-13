"""Galería de íconos de carta (iconos_carta_clonexa) contra Postgres REAL (pgserver).

- Migración 025r aditiva e idempotente (dos veces): enciende SOLO The Time Machine.
- inventory-lite: con el interruptor, cada artículo trae su ícono (foto > elegido >
  reconocido > genérico) y las palabras del genérico quedan registradas; apagado
  (cualquier otra empresa): la respuesta es exactamente la de antes.
- Menú de mesero/caja/domicilios: categorías con su ícono solo con el interruptor.
- Empresa A nunca ve los íconos elegidos ni las palabras de B.
"""
from __future__ import annotations

import asyncio
import importlib
import tempfile
import uuid
from unittest.mock import AsyncMock

import pytest

pgserver = pytest.importorskip("pgserver")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.main as app_main  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.api.v1.endpoints import waiter_ordering as wo  # noqa: E402
from app.services import carta_icons as ci  # noqa: E402

TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"
OTRA = "0b0b0b0b-0000-4000-8000-0000000000b2"
SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (id uuid PRIMARY KEY, name text NOT NULL, slug text, status text DEFAULT 'active',
  settings_json jsonb DEFAULT '{}'::jsonb, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text,
  category text, is_active boolean DEFAULT true);
CREATE TABLE IF NOT EXISTS company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
  module_id uuid REFERENCES modules(id), enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS inventory_items (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, sku text, name text, reference text,
  name_reference text, current_stock numeric DEFAULT 10, min_stock numeric DEFAULT 0, status text DEFAULT 'active', entry_price numeric DEFAULT 0,
  sale_price numeric DEFAULT 0, allows_portions boolean DEFAULT false, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS hospitality_categories (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, category_key varchar(120) NOT NULL,
  label varchar(160) NOT NULL DEFAULT '', station varchar(80) NOT NULL DEFAULT '', quick_notes jsonb NOT NULL DEFAULT '[]'::jsonb, image_bytes bytea NULL,
  image_content_type varchar(80) NULL, requires_term boolean NOT NULL DEFAULT false, UNIQUE (company_id, category_key));
CREATE TABLE IF NOT EXISTS hospitality_product_portions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL,
  product_group_key varchar(160) NOT NULL, group_label varchar(160) NOT NULL DEFAULT '', inventory_item_id uuid NOT NULL,
  portion_label varchar(40) NOT NULL, position int NOT NULL DEFAULT 0, UNIQUE (company_id, inventory_item_id));
CREATE TABLE IF NOT EXISTS hospitality_product_images (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, inventory_item_id uuid NOT NULL,
  image_bytes bytea NULL, image_content_type varchar(80) NULL, updated_at timestamptz DEFAULT now(), UNIQUE (company_id, inventory_item_id))
"""
NAMES = ["Aguardiente Antioqueño 375", "Hidratante Gatorade", "Paquete papas", "Tiket cover", "Ron Medellín", "Shot de tequila",
         "Tequila José Cuervo", "Whiskey Old Parr", "Vodka Absolut", "Agua Cristal", "Cerveza Águila", "Chiclets Trident", "Cigarrillo Marlboro",
         "Gaseosa Coca Cola", "Aguardientes Néctar", "AGUARDIENTE amarillo", "Papitas limón", "Hookah menta", "Hookah sandía"]
EXPECTED = ["aguardiente", "hidratante", "paquete", "tiket", "ron", "shot", "tequila", "whiskey", "vodka", "agua", "cerveza", "chiclets",
            "cigarrillo", "gaseosa", "aguardiente", "aguardiente", "paquete", "bebida", "bebida"]


def _migration() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.025r_iconos_carta")
    module.op = Op()
    module.upgrade()
    return statements


def _run(url, sql, params=None, fetch=True):
    async def go():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            rows = [dict(r) for r in result.mappings().all()] if fetch else None
        await engine.dispose()
        return rows
    return asyncio.run(go())


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_iconos_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
                await conn.execute(text(stmt))
            await conn.execute(text("INSERT INTO companies (id, name) VALUES (:a, 'THE TIME MACHINE'), (:b, 'Otra Empresa')"), {"a": TTM, "b": OTRA})
            await conn.execute(text("INSERT INTO modules (code, name) VALUES ('qr', 'QR'), ('waiter_ordering', 'Mesero')"))
            for cid in (TTM, OTRA):
                await conn.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
                    SELECT CAST(:c AS uuid), id, true, '{"qr_bar_menu": true}'::jsonb FROM modules"""), {"c": cid})
            for stmt in _migration() + _migration():  # idempotente
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


@pytest.fixture
def client(pg_url):
    _run(pg_url, "TRUNCATE inventory_items, hospitality_product_images, carta_icon_misses", fetch=False)

    async def db_dep():
        engine = create_async_engine(pg_url, poolclass=NullPool)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            yield session
        await engine.dispose()

    app_main.app.dependency_overrides[get_db] = db_dep
    yield TestClient(app_main.app)
    app_main.app.dependency_overrides.pop(get_db, None)


def _items(pg_url, cid, names):
    ids = []
    for i, name in enumerate(names):
        ids.append(_run(pg_url, "INSERT INTO inventory_items (company_id, sku, name, name_reference, sale_price) VALUES (:c, :s, :n, :n, 5000) RETURNING id::text AS id",
                        {"c": cid, "s": f"S{i}", "n": name})[0]["id"])
    return ids


def _lite(client, cid):
    r = client.get(f"/api/v1/hospitality/companies/{cid}/inventory-lite?limit=300")
    assert r.status_code == 200
    return r.json()


def _with_db(pg_url, fn):
    async def go():
        engine = create_async_engine(pg_url, poolclass=NullPool)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            out = await fn(session)
        await engine.dispose()
        return out
    return asyncio.run(go())


def test_migracion_solo_the_time_machine_y_columna_nueva(pg_url):
    rows = _run(pg_url, "SELECT company_id::text AS c, settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id WHERE m.code = 'qr' ORDER BY c")
    by = {r["c"]: r["settings"] for r in rows}
    assert by[TTM].get("iconos_carta_clonexa") is True and by[TTM].get("qr_bar_menu") is True, "no pisa los otros ajustes"
    assert "iconos_carta_clonexa" not in by[OTRA]
    assert _run(pg_url, "SELECT 1 AS x FROM information_schema.columns WHERE table_name = 'inventory_items' AND column_name = 'icono_key'")


def test_encendido_cada_articulo_con_su_svg_y_genericos_registrados(client, pg_url):
    _items(pg_url, TTM, NAMES)
    data = _lite(client, TTM)
    assert data["iconos_carta"] is True
    got = {i["name"]: i["icon"] for i in data["inventory"]}
    for name, key in zip(NAMES, EXPECTED):
        assert got[name]["key"] == key, name
        assert got[name]["url"] == ci.url(key)
        assert got[name]["source"] == ("generic" if key == "bebida" else "auto")
    misses = _run(pg_url, "SELECT company_id::text AS c, word, items FROM carta_icon_misses")
    assert misses == [{"c": TTM, "word": "hookah", "items": 2}]
    # al ampliar o renombrar, la palabra sale de la lista
    _run(pg_url, "UPDATE inventory_items SET name = 'Cerveza Hookah', name_reference = 'Cerveza Hookah' WHERE name LIKE 'Hookah%'", fetch=False)
    _lite(client, TTM)
    assert _run(pg_url, "SELECT word FROM carta_icon_misses") == []


def test_prioridad_foto_elegido_reconocido_y_volver_al_automatico(client, pg_url):
    ids = _items(pg_url, TTM, ["Aguardiente blanco", "Aguardiente sin azúcar", "Hookah", "Aguardiente con foto"])
    _run(pg_url, "UPDATE inventory_items SET icono_key = 'ron' WHERE id = CAST(:i AS uuid)", {"i": ids[1]}, fetch=False)
    _run(pg_url, "UPDATE inventory_items SET icono_key = 'tiket' WHERE id = CAST(:i AS uuid)", {"i": ids[2]}, fetch=False)
    _run(pg_url, "UPDATE inventory_items SET icono_key = 'ron' WHERE id = CAST(:i AS uuid)", {"i": ids[3]}, fetch=False)
    _run(pg_url, "INSERT INTO hospitality_product_images (company_id, inventory_item_id, image_bytes) VALUES (:c, CAST(:i AS uuid), '\\x89'::bytea)",
         {"c": TTM, "i": ids[3]}, fetch=False)
    icons = {i["id"]: i["icon"] for i in _lite(client, TTM)["inventory"]}
    assert icons[ids[0]]["source"] == "auto" and icons[ids[0]]["key"] == "aguardiente"
    assert icons[ids[1]]["source"] == "manual" and icons[ids[1]]["key"] == "ron"
    assert icons[ids[2]]["source"] == "manual", "elegido a mano: ya no cuenta como palabra sin ícono"
    assert icons[ids[3]]["source"] == "photo" and icons[ids[3]]["url"] == f"/api/v1/companies/{TTM}/waiter-ordering/products/{ids[3]}/image"
    assert _run(pg_url, "SELECT word FROM carta_icon_misses") == []
    _run(pg_url, "UPDATE inventory_items SET icono_key = NULL WHERE id = CAST(:i AS uuid)", {"i": ids[1]}, fetch=False)
    assert {i["id"]: i["icon"] for i in _lite(client, TTM)["inventory"]}[ids[1]]["source"] == "auto"


def test_apagado_otra_empresa_identica_a_hoy_y_sin_cruces(client, pg_url):
    _items(pg_url, TTM, ["Hookah"])
    other = _items(pg_url, OTRA, ["Aguardiente", "Hookah", "Cerveza"])
    _run(pg_url, "UPDATE inventory_items SET icono_key = 'ron' WHERE id = CAST(:i AS uuid)", {"i": other[0]}, fetch=False)
    data = _lite(client, OTRA)
    assert set(data) == {"ok", "company_id", "inventory", "quantity_picker"}, "sin campos nuevos"
    for item in data["inventory"]:
        assert set(item) == {"id", "sku", "name", "price", "unit_price", "stock", "active", "allows_portions"}
    ttm = _lite(client, TTM)
    assert [i["name"] for i in ttm["inventory"]] == ["Hookah"], "TTM no ve artículos de la otra empresa"
    assert all(i["icon"]["source"] != "manual" for i in ttm["inventory"]), "ni sus íconos elegidos"
    assert _run(pg_url, "SELECT company_id::text AS c, word FROM carta_icon_misses") == [{"c": TTM, "word": "hookah"}], "la otra empresa no registra palabras"


def test_menu_de_mesero_caja_y_domicilios_con_iconos_solo_encendido(client, pg_url):
    ids = _items(pg_url, TTM, ["Paquete papas", "Paquete chicle", "Ron viejo"])
    _run(pg_url, "UPDATE inventory_items SET icono_key = 'chiclets' WHERE id = CAST(:i AS uuid)", {"i": ids[1]}, fetch=False)
    _items(pg_url, OTRA, ["Paquete papas", "Ron viejo"])
    menu = _with_db(pg_url, lambda db: wo.build_waiter_menu(db, uuid.UUID(TTM)))
    assert menu["iconos_carta"] is True
    cats = {c["label"]: c for c in menu["categories"]}
    assert cats["Paquete"]["icon"]["key"] == "chiclets", "la categoría toma el elegido a mano"
    assert cats["Ron"]["icon"] == {"source": "auto", "url": ci.url("ron"), "key": "ron"}
    assert {p["name"]: p["icon"]["key"] for c in menu["categories"] for p in c["products"]} == {"Paquete papas": "paquete", "Paquete chicle": "chiclets", "Ron viejo": "ron"}
    off = _with_db(pg_url, lambda db: wo.build_waiter_menu(db, uuid.UUID(OTRA)))
    assert "iconos_carta" not in off and all("icon" not in c for c in off["categories"])
    assert all("icon" not in p for c in off["categories"] for p in c["products"])
