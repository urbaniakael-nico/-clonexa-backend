"""Roles por empresa contra Postgres REAL con asyncpg (no una base falsa).

Guardar mezcla la clave employee_roles en company_modules.settings del modulo
workforce de ESA empresa: no toca otras claves (p. ej. el interruptor
workforce_v2) ni otra empresa. Leer y contar empleados usan los tipos reales.
Si pgserver no esta instalado (p. ej. en Railway) la prueba se salta.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.services import employee_roles as roles  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (id uuid PRIMARY KEY, name text NOT NULL);
CREATE TABLE IF NOT EXISTS modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id),
  module_id uuid REFERENCES modules(id), enabled boolean DEFAULT true, settings jsonb NOT NULL DEFAULT '{}'::jsonb, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id), full_name text,
  role varchar(80) NOT NULL DEFAULT 'operator', employee_type varchar(50) NOT NULL DEFAULT 'operator', status varchar(30) NOT NULL DEFAULT 'active');
"""


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_roles_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


def test_save_load_and_count_with_real_types(pg_url):
    async def run():
        engine = create_async_engine(pg_url)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as db:
                urb, otra, nomod = (str(uuid.uuid4()) for _ in range(3))
                for cid, name in ((urb, "URBANIA"), (otra, "Velvet"), (nomod, "Sin personal")):
                    await db.execute(text("INSERT INTO companies (id, name) VALUES (CAST(:i AS uuid), :n)"), {"i": cid, "n": name})
                wid = (await db.execute(text("INSERT INTO modules (code) VALUES ('workforce') RETURNING id::text"))).scalar()
                for cid in (urb, otra):
                    await db.execute(text("INSERT INTO company_modules (company_id, module_id, settings) VALUES (CAST(:c AS uuid), CAST(:m AS uuid), CAST(:s AS jsonb))"),
                                     {"c": cid, "m": wid, "s": json.dumps({"workforce_v2": True, "otra_clave": [1, 2]})})
                for role, status in (("supervisor", "active"), ("Supervisor", "inactive"), ("tecnico", "active"), ("gerencia", "archived")):
                    await db.execute(text("INSERT INTO employees (company_id, full_name, role, employee_type, status) VALUES (CAST(:c AS uuid), 'x', :r, :r, :s)"),
                                     {"c": urb, "r": role, "s": status})
                await db.commit()

                assert await roles.load_config(db, urb) is None, "sin configuracion todavia"
                config = roles.validate_body({"roles": [{"code": "gerencia", "label": "Director"}, {"code": "supervisor"}, {"code": "otro"}]})
                assert await roles.save_config(db, urb, config) is True
                assert await roles.save_config(db, nomod, config) is False, "sin modulo workforce no guarda"

                loaded = await roles.load_config(db, urb)
                assert [(r["code"], r["label"]) for r in loaded["roles"]] == [("gerencia", "Director"), ("supervisor", "Supervisor"), ("otro", "Otro")]
                settings = (await db.execute(text("SELECT settings FROM company_modules WHERE company_id = CAST(:c AS uuid)"), {"c": urb})).scalar()
                assert settings["workforce_v2"] is True and settings["otra_clave"] == [1, 2], "las demas claves no cambian"
                other = (await db.execute(text("SELECT settings FROM company_modules WHERE company_id = CAST(:c AS uuid)"), {"c": otra})).scalar()
                assert other == {"workforce_v2": True, "otra_clave": [1, 2]}, "la otra empresa no cambia"
                assert await roles.load_config(db, otra) is None

                assert await roles.role_counts(db, urb) == {"supervisor": 2, "tecnico": 1}, "archivados no cuentan; mayusculas se normalizan"

                # Volver a "todos los roles": la clave queda sin roles y la empresa vuelve a como siempre.
                assert await roles.save_config(db, urb, {"roles": None, "updated_at": None}) is True
                assert await roles.load_config(db, urb) is None
        finally:
            await engine.dispose()

    asyncio.run(run())
