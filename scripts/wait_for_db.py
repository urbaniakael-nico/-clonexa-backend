import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not configured", file=sys.stderr)
        raise SystemExit(1)

    engine = create_async_engine(database_url, pool_pre_ping=True)
    for attempt in range(1, 31):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            return
        except Exception as exc:
            print(f"Database not ready attempt={attempt} error={exc}")
            await asyncio.sleep(1)

    await engine.dispose()
    raise SystemExit("Database unavailable")


if __name__ == "__main__":
    asyncio.run(main())
