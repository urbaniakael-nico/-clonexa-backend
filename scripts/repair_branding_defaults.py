from __future__ import annotations

import asyncio
import os
from typing import Any

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


STATEMENTS = [
    """
    create table if not exists company_branding (
      id uuid primary key default gen_random_uuid(),
      company_id uuid not null references companies(id) on delete cascade,
      logo_url varchar(1024),
      logo_palette_json jsonb not null default '{}'::jsonb,
      primary_color varchar(32) not null default '#ef233c',
      secondary_color varchar(32) not null default '#ff2bd6',
      background_color varchar(32) not null default '#050505',
      card_color varchar(32) not null default '#18181b',
      text_color varchar(32) not null default '#f8fafc',
      success_color varchar(32) not null default '#00ff88',
      button_color varchar(32) not null default '#ef233c',
      status_color varchar(32) not null default '#00ff88',
      danger_color varchar(32) not null default '#ff4d6d',
      warning_color varchar(32) not null default '#ffc857',
      theme_mode varchar(32) not null default 'dark',
      industry_theme varchar(64) not null default 'default',
      visual_preset varchar(96) not null default 'clonexa_default',
      font_family varchar(255),
      custom_css_json jsonb not null default '{}'::jsonb,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique(company_id)
    )
    """,
    "alter table company_branding add column if not exists logo_url varchar(1024)",
    "alter table company_branding add column if not exists logo_palette_json jsonb not null default '{}'::jsonb",
    "alter table company_branding add column if not exists primary_color varchar(32) not null default '#ef233c'",
    "alter table company_branding add column if not exists secondary_color varchar(32) not null default '#ff2bd6'",
    "alter table company_branding add column if not exists background_color varchar(32) not null default '#050505'",
    "alter table company_branding add column if not exists card_color varchar(32) not null default '#18181b'",
    "alter table company_branding add column if not exists text_color varchar(32) not null default '#f8fafc'",
    "alter table company_branding add column if not exists success_color varchar(32) not null default '#00ff88'",
    "alter table company_branding add column if not exists button_color varchar(32) not null default '#ef233c'",
    "alter table company_branding add column if not exists status_color varchar(32) not null default '#00ff88'",
    "alter table company_branding add column if not exists danger_color varchar(32) not null default '#ff4d6d'",
    "alter table company_branding add column if not exists warning_color varchar(32) not null default '#ffc857'",
    "alter table company_branding add column if not exists theme_mode varchar(32) not null default 'dark'",
    "alter table company_branding add column if not exists industry_theme varchar(64) not null default 'default'",
    "alter table company_branding add column if not exists visual_preset varchar(96) not null default 'clonexa_default'",
    "alter table company_branding add column if not exists font_family varchar(255)",
    "alter table company_branding add column if not exists custom_css_json jsonb not null default '{}'::jsonb",
]


BRANDS = {
    "voltage": {
        "primary_color": "#00E5FF",
        "secondary_color": "#FF2D55",
        "background_color": "#070B14",
        "card_color": "#0F1726",
        "text_color": "#F5F7FF",
        "button_color": "#FF2D55",
        "success_color": "#00FFA3",
        "danger_color": "#FF4D6D",
        "warning_color": "#FFC857",
        "status_color": "#00FFA3",
        "industry_theme": "field",
        "visual_preset": "field_ops_futuristic",
        "theme_mode": "dark",
    },
    "radio-despecho": {
        "primary_color": "#FF1744",
        "secondary_color": "#FF2BD6",
        "background_color": "#08020D",
        "card_color": "#17091F",
        "text_color": "#FFF7FB",
        "button_color": "#FF1744",
        "success_color": "#FFD166",
        "danger_color": "#FF4D6D",
        "warning_color": "#FFC857",
        "status_color": "#FFD166",
        "industry_theme": "hospitality",
        "visual_preset": "hospitality_night_ops",
        "theme_mode": "dark",
    },
    "mundo-case": {
        "primary_color": "#7C3AED",
        "secondary_color": "#00E5FF",
        "background_color": "#070714",
        "card_color": "#141426",
        "text_color": "#F8FAFC",
        "button_color": "#7C3AED",
        "success_color": "#00FFA3",
        "danger_color": "#FF4D6D",
        "warning_color": "#FFC857",
        "status_color": "#00FFA3",
        "industry_theme": "retail",
        "visual_preset": "retail_pastel_performance",
        "theme_mode": "dark",
    },
    "velvet": {
        "primary_color": "#EF233C",
        "secondary_color": "#F8FAFC",
        "background_color": "#050505",
        "card_color": "#18181B",
        "text_color": "#F8FAFC",
        "button_color": "#EF233C",
        "success_color": "#00FFA3",
        "danger_color": "#FF4D6D",
        "warning_color": "#FFC857",
        "status_color": "#00FFA3",
        "industry_theme": "production",
        "visual_preset": "production_neon",
        "theme_mode": "dark",
    },
}


async def main() -> None:
    force = os.getenv("FORCE_BRANDING_DEFAULTS", "").lower() in {"1", "true", "yes", "si"}
    engine = create_async_engine(normalize_url(get_database_url()), future=True)

    async with engine.begin() as conn:
        for statement in STATEMENTS:
            await conn.execute(text(statement))

        companies = (await conn.execute(text("select id::text, name, slug from companies order by name"))).all()

        for company_id, name, slug in companies:
            brand = BRANDS.get(str(slug))
            if not brand:
                continue

            await conn.execute(
                text(
                    """
                    insert into company_branding (
                      company_id, primary_color, secondary_color, background_color, card_color, text_color,
                      button_color, success_color, danger_color, warning_color, status_color,
                      industry_theme, visual_preset, theme_mode, logo_palette_json, custom_css_json
                    )
                    values (
                      :company_id, :primary_color, :secondary_color, :background_color, :card_color, :text_color,
                      :button_color, :success_color, :danger_color, :warning_color, :status_color,
                      :industry_theme, :visual_preset, :theme_mode, '{}'::jsonb, '{}'::jsonb
                    )
                    on conflict (company_id) do nothing
                    """
                ),
                {"company_id": company_id, **brand},
            )

            if force:
                await conn.execute(
                    text(
                        """
                        update company_branding
                        set primary_color=:primary_color,
                            secondary_color=:secondary_color,
                            background_color=:background_color,
                            card_color=:card_color,
                            text_color=:text_color,
                            button_color=:button_color,
                            success_color=:success_color,
                            danger_color=:danger_color,
                            warning_color=:warning_color,
                            status_color=:status_color,
                            industry_theme=:industry_theme,
                            visual_preset=:visual_preset,
                            theme_mode=:theme_mode,
                            updated_at=now()
                        where company_id=:company_id
                        """
                    ),
                    {"company_id": company_id, **brand},
                )

            print(f"branding_ok slug={slug} company={name} force={force}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
