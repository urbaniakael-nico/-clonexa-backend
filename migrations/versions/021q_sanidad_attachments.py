"""sanidad: photo attachments per checklist item

Revision ID: 021q_sanidad_attachments
Revises: 021p_sanidad_module
Create Date: 2026-09-24

- sanitation_items.requires_support: optional "requiere soporte" flag
  (closing without it only warns, never blocks).
- sanitation_attachments: one photo per company, day and item, stored
  through app.services.media_storage (resized to <= 800 px and <= 200 KB;
  images only, PDFs wait for an object bucket), with a per-company quota
  enforced by the endpoint. Frozen once the day's sheet is closed.
"""
from __future__ import annotations

from alembic import op

revision = "021q_sanidad_attachments"
down_revision = "021p_sanidad_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sanitation_items ADD COLUMN IF NOT EXISTS requires_support boolean NOT NULL DEFAULT false")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sanitation_attachments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            sheet_date date NOT NULL,
            item_id uuid NOT NULL,
            file_name varchar(160) NOT NULL DEFAULT '',
            image_bytes bytea NULL,
            image_content_type varchar(40) NULL,
            size_bytes integer NOT NULL DEFAULT 0,
            uploaded_by varchar(160) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_sanitation_attachment UNIQUE (company_id, sheet_date, item_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sanitation_attachments")
    op.execute("ALTER TABLE sanitation_items DROP COLUMN IF EXISTS requires_support")
