"""021a mini panel quotes module

Revision ID: 021a_mini_panel_quotes_module
Revises: 020a_mini_panel_notes_calendar
Create Date: 2026-05-14
"""

from alembic import op

revision = "021a_mini_panel_quotes_module"
down_revision = "020a_mini_panel_notes_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_panel_quotes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            panel_type VARCHAR(50) NOT NULL DEFAULT 'sales',
            quote_number VARCHAR(80) NOT NULL,
            client_name VARCHAR(220) NOT NULL,
            client_document VARCHAR(80),
            client_address VARCHAR(260),
            client_phone VARCHAR(80),
            client_email VARCHAR(180),
            items JSONB NOT NULL DEFAULT '[]'::jsonb,
            discounts JSONB NOT NULL DEFAULT '[]'::jsonb,
            payment JSONB NOT NULL DEFAULT '{}'::jsonb,
            notes TEXT,
            signature_data_url TEXT,
            subtotal NUMERIC(14, 2) NOT NULL DEFAULT 0,
            discount_total NUMERIC(14, 2) NOT NULL DEFAULT 0,
            total NUMERIC(14, 2) NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'issued',
            converted_at TIMESTAMPTZ,
            archived_at TIMESTAMPTZ,
            created_by UUID NULL,
            created_by_label VARCHAR(180),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, quote_number)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_quotes_company_panel_status
        ON mini_panel_quotes (company_id, panel_type, status, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mini_panel_quotes_company_panel_client
        ON mini_panel_quotes (company_id, panel_type, client_name);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mini_panel_quotes;")
