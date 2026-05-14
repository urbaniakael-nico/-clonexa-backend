"""020a mini panel notes calendar

Revision ID: 020a_mini_panel_notes_calendar
Revises: 020b_core_company_settings
Create Date: 2026-05-13
"""

from alembic import op

revision = "020a_mini_panel_notes_calendar"
down_revision = "020b_core_company_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_panel_notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            panel_type VARCHAR(50) NOT NULL DEFAULT 'sales',
            title VARCHAR(180) NOT NULL,
            description TEXT,
            note_type VARCHAR(30) NOT NULL DEFAULT 'reminder',
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            scheduled_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            created_by UUID NULL,
            created_by_label VARCHAR(180),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_notes_company_panel_time
        ON mini_panel_notes (company_id, panel_type, scheduled_at);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_notes_company_panel_status
        ON mini_panel_notes (company_id, panel_type, status);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mini_panel_notes;")
