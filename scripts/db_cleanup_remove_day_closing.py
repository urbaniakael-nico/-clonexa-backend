import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

MODULE_CODE = "day_closing"

def db_url():
    raw = (
        os.getenv("DATABASE_URL")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("RAILWAY_DATABASE_URL")
        or ""
    ).strip()

    if not raw:
        raise RuntimeError("No DATABASE_URL / DATABASE_PUBLIC_URL / POSTGRES_URL found.")

    if raw.startswith("postgres://"):
        raw = "postgresql+asyncpg://" + raw[len("postgres://"):]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://"):]
    elif raw.startswith("postgresql+psycopg://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql+psycopg://"):]

    return raw

async def table_exists(conn, table):
    result = await conn.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table})
    return bool(result.scalar())

async def columns(conn, table):
    result = await conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table
    """), {"table": table})
    return {row[0] for row in result.all()}

async def safe_exec(conn, sql, params=None):
    try:
        await conn.execute(text(sql), params or {})
        print("OK:", sql.splitlines()[0][:120])
    except Exception as exc:
        print("SKIP/ERROR:", type(exc).__name__, str(exc)[:300])

async def cleanup():
    engine = create_async_engine(db_url(), future=True)

    async with engine.begin() as conn:
        print("=== DB CLEANUP DAY_CLOSING START ===")

        relation_tables = [
            "company_modules",
            "package_modules",
            "tenant_modules",
            "company_enabled_modules",
            "enabled_modules",
        ]

        for table in relation_tables:
            if not await table_exists(conn, table):
                continue

            cols = await columns(conn, table)

            if "module_code" in cols:
                await safe_exec(conn, f"DELETE FROM {table} WHERE module_code = :code", {"code": MODULE_CODE})

            if "code" in cols:
                await safe_exec(conn, f"DELETE FROM {table} WHERE code = :code", {"code": MODULE_CODE})

            if "module_id" in cols and await table_exists(conn, "modules"):
                await safe_exec(conn, f"""
                    DELETE FROM {table}
                    WHERE module_id IN (
                        SELECT id FROM modules WHERE code = :code
                    )
                """, {"code": MODULE_CODE})

            if "global_module_id" in cols and await table_exists(conn, "global_modules"):
                await safe_exec(conn, f"""
                    DELETE FROM {table}
                    WHERE global_module_id IN (
                        SELECT id FROM global_modules WHERE code = :code
                    )
                """, {"code": MODULE_CODE})

        if await table_exists(conn, "modules"):
            mod_cols = await columns(conn, "modules")
            if "code" in mod_cols:
                await safe_exec(conn, "DELETE FROM modules WHERE code = :code", {"code": MODULE_CODE})

        if await table_exists(conn, "global_modules"):
            gm_cols = await columns(conn, "global_modules")
            if "code" in gm_cols:
                await safe_exec(conn, "DELETE FROM global_modules WHERE code = :code", {"code": MODULE_CODE})

        # Tablas basura creadas durante pruebas del módulo.
        for table in [
            "day_closing_v1",
            "clonexa_day_closures",
            "clonexa_day_closures_v2",
            "clonexa_closure_store",
        ]:
            if await table_exists(conn, table):
                await safe_exec(conn, f"DROP TABLE IF EXISTS {table}")

        print("=== DB CLEANUP DAY_CLOSING DONE ===")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(cleanup())
