from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from app.core import database as database_module
except Exception as exc:
    print(f"[ERROR] No se pudo importar app.core.database: {exc}")
    raise


def database_url() -> str:
    for attr in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "POSTGRES_DSN"):
        value = getattr(database_module, attr, None)
        if value:
            return str(value)

    try:
        from app.core.config import settings
        for attr in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "POSTGRES_DSN"):
            value = getattr(settings, attr, None)
            if value:
                return str(value)
    except Exception:
        pass

    raise RuntimeError("No se encontró URL de base de datos en app.core.database ni settings")


def sessionmaker_from_project():
    for attr in ("async_session_maker", "AsyncSessionLocal", "SessionLocal", "async_session"):
        factory = getattr(database_module, attr, None)
        if factory is not None:
            return factory

    engine = getattr(database_module, "engine", None) or getattr(database_module, "async_engine", None)
    if engine is not None:
        return async_sessionmaker(engine, expire_on_commit=False)

    engine = create_async_engine(database_url(), future=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def table_exists(db, table_name: str) -> bool:
    result = await db.execute(
        text("""
            select exists (
              select 1
              from information_schema.tables
              where table_schema = 'public'
                and table_name = :table_name
            )
        """),
        {"table_name": table_name},
    )
    return bool(result.scalar())


async def count_rows(db, table_name: str) -> int:
    if not await table_exists(db, table_name):
        return 0
    result = await db.execute(text(f"select count(*) from {table_name}"))
    return int(result.scalar() or 0)


async def sample_companies(db) -> list[dict[str, Any]]:
    if not await table_exists(db, "companies"):
        return []
    result = await db.execute(
        text("""
            select id::text as id, name, slug, status
            from companies
            order by created_at nulls last, name
            limit 12
        """)
    )
    return [dict(row._mapping) for row in result]


async def main() -> None:
    maker = sessionmaker_from_project()
    async with maker() as db:
        companies = await count_rows(db, "companies")
        modules = await count_rows(db, "modules")
        packages = await count_rows(db, "packages")
        company_users = await count_rows(db, "company_users")

        print("CLONEXA ADMIN DATA CHECK")
        print(f"companies: {companies}")
        print(f"modules: {modules}")
        print(f"packages: {packages}")
        print(f"company_users: {company_users}")

        rows = await sample_companies(db)
        if rows:
            print("\ncompanies sample:")
            for row in rows:
                print(f"- {row.get('name')} | {row.get('slug')} | {row.get('status')} | {row.get('id')}")
        else:
            print("\ncompanies sample: none")

        status = "OK" if companies > 0 and modules > 0 and packages > 0 else "CHECK_DATA"
        print(f"\nstatus: {status}")


if __name__ == "__main__":
    asyncio.run(main())
