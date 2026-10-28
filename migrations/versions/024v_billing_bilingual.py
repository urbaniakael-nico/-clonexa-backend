"""facturacion: contrato bilingue (español | ingles), Zelle y "Redactar desde este contrato"

Revision ID: 024v_billing_bilingual
Revises: 024u_menu_media_v3
Create Date: 2026-10-27

Aditiva (ningun contrato existente cambia):
- billing_provider.zelle_name / zelle_contact: "Nombre del titular en Zelle" y
  "Zelle (correo o teléfono)" para el Anexo 2 cuando el contrato se paga por
  Zelle. Sin numeros de cuenta.
- billing_contract_history: el contrato registrado a mano que se reemplaza con
  "Redactar desde este contrato" queda guardado aqui (no se borra), con el
  documento redactado que lo reemplazo.
"""
from __future__ import annotations

from alembic import op

revision = "024v_billing_bilingual"
down_revision = "024u_menu_media_v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE billing_provider ADD COLUMN IF NOT EXISTS zelle_name varchar(160) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE billing_provider ADD COLUMN IF NOT EXISTS zelle_contact varchar(160) NOT NULL DEFAULT ''")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_contract_history (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            contract_id uuid NULL,
            source varchar(20) NOT NULL DEFAULT 'manual',
            snapshot jsonb NOT NULL,
            replaced_by uuid NULL,
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_billing_contract_history_company ON billing_contract_history (company_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS billing_contract_history")
    op.execute("ALTER TABLE billing_provider DROP COLUMN IF EXISTS zelle_contact")
    op.execute("ALTER TABLE billing_provider DROP COLUMN IF EXISTS zelle_name")
