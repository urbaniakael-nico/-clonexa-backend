"""Estudio de marca contra Postgres REAL con asyncpg (no una base falsa).

Arranca un Postgres embebido (pgserver) en una carpeta temporal, crea las
tablas minimas de companies/modules/company_modules/admin_audit_log, corre las
migraciones 024a/b/c tal cual y prueba todas las consultas de marca: las que
la base falsa no puede validar (tipos de asyncpg, CAST, jsonb, LIKE...).
Si pgserver no esta instalado (p. ej. en Railway) la prueba se salta.
"""
from __future__ import annotations

import asyncio
import importlib
import io
import json
import tempfile
import uuid

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.services import brand_media, brand_screens, brand_share, brand_store  # noqa: E402
from app.services import brand_theme as bt  # noqa: E402

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (id uuid PRIMARY KEY, name text NOT NULL, slug text, status text DEFAULT 'active', settings_json jsonb DEFAULT '{}'::jsonb);
CREATE TABLE IF NOT EXISTS modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text, category text);
CREATE TABLE IF NOT EXISTS company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
  module_id uuid REFERENCES modules(id), enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb);
CREATE TABLE IF NOT EXISTS hospitality_product_images (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, image_bytes bytea NULL);
"""


def _migration_sql() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    for name in ("023b_admin_audit_log", "024a_brand_images", "024b_brand_themes", "024c_brand_share_links"):
        module = importlib.import_module(f"migrations.versions.{name}")
        module.op = Op()
        module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    uri = server.get_uri()
    url = uri.replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in BASE_SCHEMA.split(";") if s.strip()] + _migration_sql():
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


async def _session(url: str):
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE company_brand_share_links, company_brand_themes, company_brand_images, company_modules, admin_audit_log, hospitality_product_images, companies, modules CASCADE"))
    return engine, maker


async def _company(db, name="Empresa", modules=None) -> str:
    cid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO companies (id, name, slug) VALUES (CAST(:i AS uuid), :n, :s)"), {"i": cid, "n": name, "s": name.lower()})
    for code, enabled, settings in modules or []:
        await db.execute(text("INSERT INTO modules (code, name, category) VALUES (:c, :n, 'x') ON CONFLICT (code) DO NOTHING"), {"c": code, "n": code.title()})
        await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
            SELECT CAST(:i AS uuid), id, :e, CAST(:s AS jsonb) FROM modules WHERE code = :c"""), {"i": cid, "c": code, "e": enabled, "s": json.dumps(settings)})
    await db.commit()
    return cid


@pytest.mark.asyncio
async def test_screens_and_modules_on_real_postgres(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        velvet = await _company(db, "Velvet", [("workforce", True, {}), ("payroll", True, {})])
        asadero = await _company(db, "Asadero", [("waiter_ordering", True, {"segments": {"mesero": {"enabled": True}, "caja": {"enabled": True}}, "mini_panel_brand": True}),
                                                 ("mini_panel", True, {"mini_panel_modules": {"panels": {"sales": {"enabled": True}}}}), ("carta", False, {})])
        v = await brand_screens.for_company(db, velvet)
        assert v["screens"] == ["portal_dashboard", "portal_modulo", "portal_ingreso"] and v["panels_branded_today"] is False
        a = await brand_screens.for_company(db, asadero)
        assert a["screens"] == ["portal_dashboard", "portal_modulo", "portal_ingreso", "ingreso", "mesero", "caja", "mini_ingreso", "mini_panel"]
        assert a["panels_branded_today"] is True and a["mini_types"] == ["sales"]
        mods = await brand_screens.enabled_modules(db, asadero)
        assert [m["code"] for m in mods] == ["mini_panel", "waiter_ordering"], "solo los encendidos de ESA empresa"
    await engine.dispose()


@pytest.mark.asyncio
async def test_versions_flow_on_real_postgres(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        a = await _company(db, "A")
        b = await _company(db, "B")
        st = await brand_store.state(db, a, {"primary_color": "#123456", "background_style": "cyber_grid"}, panels=True)
        assert st["draft"]["version"] == 1 and st["published"] is None
        assert st["draft"]["tokens"]["theme"]["portal"]["background_style"] == "cyber_grid" and st["draft"]["tokens"]["theme"]["panels"] is True
        t = st["draft"]["tokens"]
        t["theme"]["colors"]["primary"] = "#00ff00"
        await brand_store.save_draft(db, a, t)
        assert await brand_store.published_tokens(db, a) is None, "guardar no publica"
        v1 = await brand_store.publish(db, a)
        assert (await brand_store.published_tokens(db, a))["theme"]["colors"]["primary"] == "#00ff00"
        st = await brand_store.state(db, a, {})
        t2 = st["draft"]["tokens"]
        t2["theme"]["colors"]["primary"] = "#ff0000"
        await brand_store.save_draft(db, a, t2)
        await brand_store.publish(db, a)
        await brand_store.rollback(db, a, v1)
        assert (await brand_store.published_tokens(db, a))["theme"]["colors"]["primary"] == "#00ff00", "volver restaura"
        assert await brand_store.published_tokens(db, b) is None, "B nunca recibe la marca de A"
        copied = await brand_store.tokens_for_copy(db, a)
        assert copied["theme"]["colors"]["primary"] == "#00ff00" and bt.image_ids(copied) == set()
        await brand_store.unpublish(db, a)
        assert await brand_store.published_tokens(db, a) is None
        assert await brand_store.draft_tokens(db, a) is None, "publicar consume el borrador"
        await brand_store.state(db, a, {})
        assert (await brand_store.draft_tokens(db, a)) is not None, "abrir el estudio crea el siguiente"
        for i in range(12):
            t3 = (await brand_store.state(db, a, {}))["draft"]["tokens"]
            t3["theme"]["radius"] = i
            await brand_store.save_draft(db, a, t3)
            await brand_store.publish(db, a)
        n = (await db.execute(text("SELECT COUNT(*) FROM company_brand_themes WHERE company_id = CAST(:c AS uuid)"), {"c": a})).scalar()
        assert n <= bt.MAX_VERSIONS + 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_old_initial_draft_is_regenerated_only_if_nobody_edited_it(pg_url):
    engine, maker = await _session(pg_url)
    old = {"theme": {"colors": dict(bt.CLONEXA_DEFAULT), "font": {"family": "Inter", "size": 15, "heading_weight": 700}, "radius": 14, "shadow": 30, "glow": 0,
                     "logo": "11111111-2222-3333-4444-555555555555"},
           "backgrounds": {"general": {"base": {"kind": "solid", "color": "#000000"}, "image": None, "veil": None},
                           "ingreso": {"inherit": True}, "mesero": {"inherit": True}, "cocina": {"inherit": True}, "caja": {"inherit": True}},
           "components": {}, "pieces": {}}
    async with maker() as db:
        fresh, edited = await _company(db, "Fresca"), await _company(db, "Editada")
        for cid in (fresh, edited):
            await db.execute(text("INSERT INTO company_brand_themes (company_id, version, status, tokens) VALUES (CAST(:c AS uuid), 1, 'draft', CAST(:t AS jsonb))"),
                             {"c": cid, "t": json.dumps(old)})
        await db.execute(text("INSERT INTO admin_audit_log (actor, method, path, status_code) VALUES ('admin', 'PUT', :p, 200)"),
                         {"p": f"/admin-v2/api/brand/{edited}/draft"})
        await db.commit()
        branding = {"primary_color": "#7c3aed", "background_style": "neon_profundo", "card_style": "executive_glass"}
        st = await brand_store.state(db, fresh, branding)
        tk = st["draft"]["tokens"]
        assert tk["theme"]["colors"]["primary"] == "#7c3aed" and tk["theme"]["portal"]["card_style"] == "executive_glass"
        assert tk["theme"]["logo"] == "11111111-2222-3333-4444-555555555555", "conserva el logo"
        assert tk["backgrounds"]["general"]["base"] == {"kind": "preset"}
        st2 = await brand_store.state(db, edited, branding)
        assert st2["draft"]["tokens"]["theme"]["colors"]["primary"] == bt.CLONEXA_DEFAULT["primary"], "editado: no se toca"
        raw = (await db.execute(text("SELECT tokens FROM company_brand_themes WHERE company_id = CAST(:c AS uuid)"), {"c": edited})).scalar()
        assert "portal" not in (raw if isinstance(raw, dict) else json.loads(raw))["theme"], "en la base sigue igual"
    await engine.dispose()


@pytest.mark.asyncio
async def test_images_share_links_and_legacy_stats_on_real_postgres(pg_url):
    from PIL import Image

    class Mem:
        def __init__(self):
            self.objects = {}

        def put(self, k, d):
            self.objects[k] = d

        def get(self, k):
            return self.objects[k]

        def delete(self, ks):
            for k in ks:
                self.objects.pop(k, None)

        def list(self, p):
            return [k for k in self.objects if k.startswith(p)]

    engine, maker = await _session(pg_url)
    brand_media.set_backend(Mem())
    try:
        async with maker() as db:
            a, b = await _company(db, "A"), await _company(db, "B")
            buf = io.BytesIO()
            Image.new("RGB", (40, 40), "#ff0000").save(buf, format="PNG")
            img = await brand_media.upload(db, a, buf.getvalue())
            assert (await brand_media.usage(db, a))["images"] == 1 and (await brand_media.usage(db, b))["images"] == 0
            assert await brand_media.owns(db, a, img["id"]) and not await brand_media.owns(db, b, img["id"])
            assert [i["id"] for i in await brand_media.list_images(db, a)] == [img["id"]]
            t = bt.from_branding({})
            t["theme"]["logo"] = img["id"]
            await brand_store.save_draft(db, a, t)
            with pytest.raises(bt.BrandInvalid):
                await brand_store.save_draft(db, b, t)
            link = await brand_share.create(db, a)
            assert (await brand_share.resolve(db, link["token"]))["company_id"] == a
            assert len(await brand_share.list_links(db, a)) == 1 and await brand_share.list_links(db, b) == []
            assert await brand_share.revoke(db, a, link["id"]) and await brand_share.resolve(db, link["token"]) is None
            await db.execute(text("INSERT INTO hospitality_product_images (company_id, image_bytes) VALUES (CAST(:c AS uuid), :b)"), {"c": a, "b": b"x" * 100})
            await db.commit()
            from app.web import brand_routes

            stats = await brand_routes.legacy_stats(db)
            row = next(r for r in stats["tables"] if r["table"] == "hospitality_product_images")
            assert row["images"] == 1 and row["bytes"] == 100
            # El render de la ruta /admin-v2/api/brand/.../images en uso no deja borrar.
            in_use = (await db.execute(text("""
                SELECT version, status FROM company_brand_themes
                WHERE company_id = CAST(:c AS uuid) AND status IN ('draft', 'published') AND tokens::text LIKE :needle
            """), {"c": a, "needle": f"%{img['id']}%"})).mappings().all()
            assert in_use
    finally:
        brand_media.set_backend(None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_real_brand_for_the_ficha_on_real_postgres(pg_url, monkeypatch):
    from unittest.mock import AsyncMock

    from app.web import brand_routes

    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, "Ficha")
        monkeypatch.setattr(brand_routes, "_branding", AsyncMock(return_value={"primary_color": "#a600ff", "font_family": "Sora"}))
        company = {"id": cid, "name": "Ficha"}
        real = await brand_routes.real_brand(db, company)
        assert real["source"] == "siempre" and real["published"] is None and real["draft_pending"] is False
        st = await brand_store.state(db, cid, {"primary_color": "#a600ff", "font_family": "Sora"})
        t = st["draft"]["tokens"]
        t["theme"]["colors"]["primary"] = "#010203"
        await brand_store.save_draft(db, cid, t)
        real = await brand_routes.real_brand(db, company)
        assert real["draft_pending"] is True and real["tokens"]["theme"]["colors"]["primary"] == "#a600ff", "el borrador no es la marca real"
        await brand_store.publish(db, cid)
        real = await brand_routes.real_brand(db, company)
        assert real["source"] == "published" and real["published"]["version"] == 1 and real["tokens"]["theme"]["colors"]["primary"] == "#010203"
    await engine.dispose()
