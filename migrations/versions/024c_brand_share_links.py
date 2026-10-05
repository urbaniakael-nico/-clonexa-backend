"""enlaces de vista previa de la marca (company_brand_share_links)

Revision ID: 024c_brand_share_links
Revises: 024b_brand_themes
Create Date: 2026-10-05

Un enlace para que el cliente vea sus pantallas con el borrador, con datos de
muestra. Solo se guarda el hash de la parte secreta del token (nunca el
token); vence a los 7 dias y se puede revocar desde el estudio.
"""
from __future__ import annotations

from alembic import op

revision = "024c_brand_share_links"
down_revision = "024b_brand_themes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_brand_share_links (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            secret_hash varchar(64) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_brand_share_links_company ON company_brand_share_links (company_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_brand_share_links")
