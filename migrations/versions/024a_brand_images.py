"""imagenes de marca en el bucket (company_brand_images)

Revision ID: 024a_brand_images
Revises: 023b_admin_audit_log
Create Date: 2026-10-05

Indice de las imagenes de marca que viven en el bucket de Railway
(clonexa-media). Los bytes NO estan en Postgres: aqui solo el id, la empresa,
el peso de la version completa y la liviana y las dimensiones, para el tope
de espacio por empresa y para verificar que una imagen es de esa empresa.
Las claves del bucket se derivan de company_id e id (brand/{company}/{id}.webp).
"""
from __future__ import annotations

from alembic import op

revision = "024a_brand_images"
down_revision = "023b_admin_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_brand_images (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            size_bytes integer NOT NULL,
            lite_bytes integer NOT NULL,
            width integer NOT NULL,
            height integer NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_company_brand_images_company ON company_brand_images (company_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_brand_images")
