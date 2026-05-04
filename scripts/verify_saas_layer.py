from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def get_database_url() -> str:
    value = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("POSTGRES_URL")
    if not value:
        raise RuntimeError("Falta DATABASE_URL, SQLALCHEMY_DATABASE_URI o POSTGRES_URL.")
    if value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


async def main() -> None:
    engine = create_async_engine(get_database_url(), future=True, pool_pre_ping=True)
    async with engine.connect() as conn:
        version = await conn.scalar(text("select version_num from alembic_version"))
        print(f"alembic current db: {version}")

        tables = await conn.execute(
            text(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                  and table_name in (
                    'modules',
                    'packages',
                    'package_modules',
                    'company_modules',
                    'company_package_assignments'
                  )
                order by table_name
                """
            )
        )
        found = [row[0] for row in tables.fetchall()]
        print("tables:", ", ".join(found) or "NONE")

        modules_count = await conn.scalar(text("select count(*) from modules")) if "modules" in found else 0
        packages_count = await conn.scalar(text("select count(*) from packages")) if "packages" in found else 0
        print(f"modules_count: {modules_count}")
        print(f"packages_count: {packages_count}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
