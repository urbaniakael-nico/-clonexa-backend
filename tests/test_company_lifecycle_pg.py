"""Integracion OPCIONAL de clonar/eliminar contra un Postgres desechable.

Se salta si no existe CLONEXA_TEST_PG_URL (la suite normal no tiene base de
datos). Solo corre si el nombre de la base contiene "test": crea y borra sus
propias tablas en el esquema public. Ejemplo:

    docker run -d -p 55432:5432 -e POSTGRES_PASSWORD=x -e POSTGRES_DB=clonexa_test postgres:16
    set CLONEXA_TEST_PG_URL=postgresql+asyncpg://postgres:x@localhost:55432/clonexa_test
"""
from __future__ import annotations

import os
import uuid

import pytest

URL = os.getenv("CLONEXA_TEST_PG_URL", "")
pytestmark = pytest.mark.skipif(not URL or "test" not in URL.rsplit("/", 1)[-1],
                                reason="sin CLONEXA_TEST_PG_URL (base desechable con 'test' en el nombre)")

SCHEMA = [
    "CREATE TABLE companies (id uuid PRIMARY KEY, name text, slug text, status text, settings_json jsonb NOT NULL DEFAULT '{}')",
    "CREATE TABLE company_modules (id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE, module_id uuid, enabled boolean, settings jsonb NOT NULL DEFAULT '{}')",
    "CREATE TABLE carta_categories (id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE, parent_id uuid NULL REFERENCES carta_categories(id) ON DELETE CASCADE, label varchar(80) NOT NULL, created_at timestamptz NOT NULL DEFAULT now())",
    "CREATE TABLE carta_items (id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE, category_id uuid NULL REFERENCES carta_categories(id) ON DELETE SET NULL, name text, price numeric(14,2), inventory_item_id uuid NULL)",
    "CREATE TABLE employees (id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES companies(id))",
    "CREATE TABLE hospitality_orders (id uuid PRIMARY KEY, company_id uuid NOT NULL, employee_id uuid REFERENCES employees(id), total numeric)",
    "CREATE TABLE reference_work_sessions (id uuid PRIMARY KEY, company_id text NOT NULL)",
]


@pytest.mark.asyncio
async def test_clone_and_purge_against_real_postgres():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.services import company_lifecycle as lc

    engine = create_async_engine(URL)
    src, other, demo = (str(uuid.uuid4()) for _ in range(3))
    async with engine.begin() as conn:
        for table in ("reference_work_sessions", "hospitality_orders", "employees", "carta_items", "carta_categories",
                      "company_modules", "companies"):
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        for ddl in SCHEMA:
            await conn.execute(text(ddl))
        for cid in (src, other, demo):
            await conn.execute(text("INSERT INTO companies (id, name, slug, status) VALUES (CAST(:i AS uuid), :i, :i, 'active')"), {"i": cid})
        parent, child, emp = (str(uuid.uuid4()) for _ in range(3))
        await conn.execute(text("INSERT INTO company_modules VALUES (gen_random_uuid(), CAST(:c AS uuid), gen_random_uuid(), true, CAST(:s AS jsonb))"),
                           {"c": src, "s": '{"x": true, "bot_token": "123"}'})
        await conn.execute(text("INSERT INTO carta_categories (id, company_id, parent_id, label) VALUES (CAST(:p AS uuid), CAST(:c AS uuid), NULL, 'Bebidas'), (CAST(:h AS uuid), CAST(:c AS uuid), CAST(:p AS uuid), 'Cervezas')"),
                           {"p": parent, "h": child, "c": src})
        await conn.execute(text("INSERT INTO carta_items VALUES (gen_random_uuid(), CAST(:c AS uuid), CAST(:h AS uuid), 'Club', 9000, gen_random_uuid())"), {"c": src, "h": child})
        await conn.execute(text("INSERT INTO employees VALUES (CAST(:e AS uuid), CAST(:c AS uuid)), (gen_random_uuid(), CAST(:o AS uuid))"), {"e": emp, "c": src, "o": other})
        await conn.execute(text("INSERT INTO hospitality_orders VALUES (gen_random_uuid(), CAST(:c AS uuid), CAST(:e AS uuid), 10)"), {"c": src, "e": emp})
        await conn.execute(text("INSERT INTO reference_work_sessions VALUES (gen_random_uuid(), :c), (gen_random_uuid(), :o)"), {"c": src, "o": other})

    async with AsyncSession(engine) as db:
        copied = await lc.clone_config(lc.PgStore(db), src, demo)
        await db.commit()
        assert copied["carta_categories"] == 2 and copied["carta_items"] == 1 and copied["company_modules"] == 1
        n = (await db.execute(text("SELECT COUNT(*) FROM employees WHERE company_id = CAST(:d AS uuid)"), {"d": demo})).scalar()
        assert n == 0
        tree = (await db.execute(text("SELECT c.label, p.label AS parent FROM carta_categories c LEFT JOIN carta_categories p ON p.id = c.parent_id WHERE c.company_id = CAST(:d AS uuid) ORDER BY c.label"), {"d": demo})).all()
        assert [tuple(r) for r in tree] == [("Bebidas", None), ("Cervezas", "Bebidas")]
        settings = (await db.execute(text("SELECT settings FROM company_modules WHERE company_id = CAST(:d AS uuid)"), {"d": demo})).scalar()
        assert settings == {"x": True}

        plan = await lc.purge_plan(lc.PgStore(db), src)
        assert {p["table"] for p in plan} >= {"hospitality_orders", "employees", "reference_work_sessions"}
        await lc.purge_execute(lc.PgStore(db), src)  # employees antes que la orden falla y se reintenta
        await db.commit()
        left = (await db.execute(text("SELECT COUNT(*) FROM companies WHERE id = CAST(:s AS uuid)"), {"s": src})).scalar()
        assert left == 0
        others = (await db.execute(text("SELECT (SELECT COUNT(*) FROM employees WHERE company_id = CAST(:o AS uuid)) + (SELECT COUNT(*) FROM reference_work_sessions WHERE company_id = :o)"), {"o": other})).scalar()
        assert others == 2
    await engine.dispose()
