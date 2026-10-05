"""versiones de la marca por empresa (company_brand_themes)

Revision ID: 024b_brand_themes
Revises: 024a_brand_images
Create Date: 2026-10-05

Una fila por version de la marca de una empresa: draft (a lo sumo una),
published (a lo sumo una) o archived. tokens son solo valores validados
(colores hex, numeros con rango, opciones cerradas). Maximo 10 versiones por
empresa (el servicio borra las archivadas mas viejas). Sin tema publicado la
empresa se ve exactamente igual que hoy.
"""
from __future__ import annotations

from alembic import op

revision = "024b_brand_themes"
down_revision = "024a_brand_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_brand_themes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            version integer NOT NULL,
            status varchar(12) NOT NULL CHECK (status IN ('draft', 'published', 'archived')),
            tokens jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            published_at timestamptz NULL,
            UNIQUE (company_id, version)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_brand_themes_one_draft ON company_brand_themes (company_id) WHERE status = 'draft'")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_brand_themes_one_published ON company_brand_themes (company_id) WHERE status = 'published'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_brand_themes")
