"""011A3 bot UX turno core multiidioma

Revision ID: 011a3_bot_ux_turno_multiidioma
Revises: 011a0_company_bot_instances
Create Date: 2026-05-04

"""

from alembic import op


revision = "011a3_bot_ux_turno_multiidioma"
down_revision = "011a0_company_bot_instances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_telegram_user_preferences (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            telegram_user_id varchar(120) NOT NULL,
            telegram_username varchar(180) NULL,
            language varchar(10) NOT NULL DEFAULT 'es',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_company_telegram_user_preferences UNIQUE (company_id, telegram_user_id)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_company_telegram_user_preferences_company ON company_telegram_user_preferences(company_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_company_telegram_user_preferences_language ON company_telegram_user_preferences(language);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_company_telegram_user_preferences_language;")
    op.execute("DROP INDEX IF EXISTS ix_company_telegram_user_preferences_company;")
    op.execute("DROP TABLE IF EXISTS company_telegram_user_preferences;")
