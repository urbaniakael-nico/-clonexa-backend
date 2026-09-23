"""sale document settings (caja: cuenta de cobro)

Revision ID: 021l_sale_document_settings
Revises: 021k_inv_allows_portions
Create Date: 2026-09-23

One small row per company: the configuration of the document the caja
prints (JSON: nombre comercial, NIT, régimen, IVA, prefijo, pie de página,
DIAN switch...) and the internal consecutive counter. The logo is a URL, so
no image bytes are stored. No data is inserted: every company starts with
no row (= defaults, DIAN switch off).
"""
from __future__ import annotations

from alembic import op

revision = "021l_sale_document_settings"
down_revision = "021k_inv_allows_portions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sale_document_settings (
            company_id uuid PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            config jsonb NOT NULL DEFAULT '{}'::jsonb,
            last_number integer NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT now(),
            updated_by text NOT NULL DEFAULT ''
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sale_document_settings;")
