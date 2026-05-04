from __future__ import annotations

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def get_database_url() -> str:
    try:
        from app.core.config import settings  # type: ignore

        for attr in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "POSTGRES_DSN"):
            value = getattr(settings, attr, None)
            if value:
                return str(value)
    except Exception:
        pass

    value = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("POSTGRES_DSN")
    if not value:
        raise RuntimeError("DATABASE_URL no encontrada.")
    return value


def normalize_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def main() -> None:
    engine = create_async_engine(normalize_url(get_database_url()), future=True)
    async with engine.begin() as conn:
        exists = await conn.execute(
            text("select exists (select 1 from information_schema.tables where table_name='company_branding')")
        )
        print(f"company_branding_table={exists.scalar()}")

        result = await conn.execute(
            text(
                """
                select c.name, c.slug, cb.primary_color, cb.secondary_color, cb.background_color,
                       cb.card_color, cb.text_color, cb.button_color, cb.success_color,
                       cb.danger_color, cb.warning_color, cb.industry_theme, cb.visual_preset
                from companies c
                left join company_branding cb on cb.company_id = c.id
                where c.slug in ('voltage','radio-despecho','mundo-case','velvet')
                order by c.slug
                """
            )
        )
        for row in result.mappings().all():
            print(dict(row))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
