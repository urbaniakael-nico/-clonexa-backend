import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

try:
    from app.core import database as database_module
except Exception as exc:
    print(f"[ERROR] No se pudo importar app.core.database: {exc}")
    raise


def _database_url() -> str:
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
    raise RuntimeError("No se encontró DATABASE_URL en app.core.database ni app.core.config.settings")


def _engine():
    engine = getattr(database_module, "engine", None) or getattr(database_module, "async_engine", None)
    if engine is not None:
        return engine
    return create_async_engine(_database_url(), future=True)


STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",

    """
    CREATE TABLE IF NOT EXISTS company_branding (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        logo_url VARCHAR(1024),
        logo_palette_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        primary_color VARCHAR(32) NOT NULL DEFAULT '#ef233c',
        secondary_color VARCHAR(32) NOT NULL DEFAULT '#ff2bd6',
        background_color VARCHAR(32) NOT NULL DEFAULT '#050505',
        card_color VARCHAR(32) NOT NULL DEFAULT '#18181b',
        text_color VARCHAR(32) NOT NULL DEFAULT '#f8fafc',
        success_color VARCHAR(32) NOT NULL DEFAULT '#00ff88',
        button_color VARCHAR(32) NOT NULL DEFAULT '#ef233c',
        status_color VARCHAR(32) NOT NULL DEFAULT '#00ff88',
        theme_mode VARCHAR(32) NOT NULL DEFAULT 'dark',
        industry_theme VARCHAR(96) NOT NULL DEFAULT 'default',
        visual_preset VARCHAR(96) NOT NULL DEFAULT 'clonexa_default',
        font_family VARCHAR(160),
        custom_css_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(company_id)
    )
    """,

    "ALTER TABLE company_branding ADD COLUMN IF NOT EXISTS visual_preset VARCHAR(96) NOT NULL DEFAULT 'clonexa_default'",
    "ALTER TABLE company_branding ADD COLUMN IF NOT EXISTS button_color VARCHAR(32) NOT NULL DEFAULT '#ef233c'",
    "ALTER TABLE company_branding ADD COLUMN IF NOT EXISTS status_color VARCHAR(32) NOT NULL DEFAULT '#00ff88'",
    "ALTER TABLE company_branding ADD COLUMN IF NOT EXISTS logo_palette_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE company_branding ADD COLUMN IF NOT EXISTS custom_css_json JSONB NOT NULL DEFAULT '{}'::jsonb",

    """
    CREATE TABLE IF NOT EXISTS company_localization (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        default_language VARCHAR(8) NOT NULL DEFAULT 'es',
        enabled_languages JSONB NOT NULL DEFAULT '["es","en","fr"]'::jsonb,
        labels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(company_id)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS company_crm_layout (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        layout_name VARCHAR(96) NOT NULL DEFAULT 'default',
        sidebar_enabled BOOLEAN NOT NULL DEFAULT true,
        topbar_enabled BOOLEAN NOT NULL DEFAULT true,
        density VARCHAR(32) NOT NULL DEFAULT 'comfortable',
        home_view VARCHAR(96) NOT NULL DEFAULT 'launchpad',
        settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(company_id)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS company_crm_launchpad_cards (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        module_code VARCHAR(96) NOT NULL,
        card_code VARCHAR(128) NOT NULL,
        title_key VARCHAR(255) NOT NULL,
        subtitle_key VARCHAR(255),
        icon VARCHAR(96),
        route_path VARCHAR(512),
        enabled BOOLEAN NOT NULL DEFAULT true,
        position INTEGER NOT NULL DEFAULT 0,
        size VARCHAR(32) NOT NULL DEFAULT 'medium',
        action_type VARCHAR(32) NOT NULL DEFAULT 'navigate',
        settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS company_crm_widgets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        module_code VARCHAR(96) NOT NULL,
        widget_code VARCHAR(128) NOT NULL,
        title_key VARCHAR(255) NOT NULL,
        metric_source VARCHAR(255),
        enabled BOOLEAN NOT NULL DEFAULT true,
        position INTEGER NOT NULL DEFAULT 0,
        size VARCHAR(32) NOT NULL DEFAULT 'medium',
        icon VARCHAR(96),
        settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS company_crm_sections (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        module_code VARCHAR(96) NOT NULL,
        section_code VARCHAR(128) NOT NULL,
        title_key VARCHAR(255) NOT NULL,
        route_path VARCHAR(512),
        section_type VARCHAR(32) NOT NULL DEFAULT 'page',
        enabled BOOLEAN NOT NULL DEFAULT true,
        position INTEGER NOT NULL DEFAULT 0,
        icon VARCHAR(96),
        settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS company_crm_actions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        module_code VARCHAR(96) NOT NULL,
        action_code VARCHAR(128) NOT NULL,
        title_key VARCHAR(255) NOT NULL,
        target VARCHAR(512),
        action_type VARCHAR(32) NOT NULL DEFAULT 'navigate',
        enabled BOOLEAN NOT NULL DEFAULT true,
        position INTEGER NOT NULL DEFAULT 0,
        icon VARCHAR(96),
        settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS company_crm_field_configs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        module_code VARCHAR(96) NOT NULL,
        entity_code VARCHAR(128) NOT NULL,
        field_code VARCHAR(128) NOT NULL,
        label_key VARCHAR(255) NOT NULL,
        field_type VARCHAR(32) NOT NULL DEFAULT 'text',
        required BOOLEAN NOT NULL DEFAULT false,
        enabled BOOLEAN NOT NULL DEFAULT true,
        position INTEGER NOT NULL DEFAULT 0,
        options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        validation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS company_alert_rules (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        module_code VARCHAR(96) NOT NULL,
        rule_code VARCHAR(128) NOT NULL,
        event_type VARCHAR(128),
        condition_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        display_type VARCHAR(32) NOT NULL DEFAULT 'toast',
        severity VARCHAR(32) NOT NULL DEFAULT 'info',
        enabled BOOLEAN NOT NULL DEFAULT true,
        message_key VARCHAR(255) NOT NULL,
        settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    "CREATE UNIQUE INDEX IF NOT EXISTS ux_company_crm_launchpad_cards_company_module_card ON company_crm_launchpad_cards(company_id, module_code, card_code)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_company_crm_widgets_company_module_widget ON company_crm_widgets(company_id, module_code, widget_code)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_company_crm_sections_company_module_section ON company_crm_sections(company_id, module_code, section_code)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_company_crm_actions_company_module_action ON company_crm_actions(company_id, module_code, action_code)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_company_crm_field_configs_company_module_entity_field ON company_crm_field_configs(company_id, module_code, entity_code, field_code)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_company_alert_rules_company_module_rule ON company_alert_rules(company_id, module_code, rule_code)",
]


async def main():
    engine = _engine()
    print("\nCLONEXA CRM BUILDER DB REPAIR 002-D")
    print("=" * 72)
    async with engine.begin() as conn:
        for index, statement in enumerate(STATEMENTS, start=1):
            sql = statement.strip()
            if not sql:
                continue
            await conn.execute(text(sql))
            first_line = sql.splitlines()[0][:96]
            print(f"[OK {index:02d}] {first_line}")
    print("\n[OK] Repair idempotente completado")


if __name__ == "__main__":
    asyncio.run(main())
