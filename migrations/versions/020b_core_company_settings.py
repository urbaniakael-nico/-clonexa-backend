"""020b core company settings

Revision ID: 020b_core_company_settings
Revises: 011c_personal_employee_fields
Create Date: 2026-05-07
"""

from alembic import op

revision = "020b_core_company_settings"
down_revision = '011c_personal_employee_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS company_core_settings (
        company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
        language VARCHAR(5) NOT NULL DEFAULT 'es',
        session_timeout_minutes INTEGER NOT NULL DEFAULT 30,
        currency VARCHAR(12) NOT NULL DEFAULT 'COP',
        timezone VARCHAR(80),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)

    op.execute("""
    INSERT INTO company_core_settings (
        company_id,
        language,
        session_timeout_minutes,
        currency,
        timezone,
        created_at,
        updated_at
    )
    SELECT
        id,
        'es',
        30,
        'COP',
        NULL,
        NOW(),
        NOW()
    FROM companies
    ON CONFLICT (company_id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_core_settings;")
