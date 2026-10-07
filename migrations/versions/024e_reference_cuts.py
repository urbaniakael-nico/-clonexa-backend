"""referencias v2: clasificacion opcional y movimientos de corte (solo aditivo)

Revision ID: 024e_reference_cuts
Revises: 024d_billing
Create Date: 2026-10-06

- product_references: gender, body_part y garment_type, opcionales y SIN
  valor por defecto (las referencias actuales quedan sin clasificar). La
  tabla la crea references_v1.ensure_storage; si aun no existe, se omite.
- reference_cut_movements: solo se agregan filas (ingreso | novedad |
  despliegue). Un movimiento nunca se borra: se anula (voided_at) y queda en
  el historial. Nunca cambian el producido, la meta ni los cierres.
No renombra ni borra nada.
"""
from __future__ import annotations

from alembic import op

revision = "024e_reference_cuts"
down_revision = "024d_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("gender", "body_part", "garment_type"):
        op.execute(f"ALTER TABLE IF EXISTS product_references ADD COLUMN IF NOT EXISTS {column} text NULL")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reference_cut_movements (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id text NOT NULL,
            reference_id text NOT NULL,
            kind varchar(12) NOT NULL CHECK (kind IN ('ingreso', 'novedad', 'despliegue')),
            section varchar(10) NULL CHECK (section IS NULL OR section IN ('corte', 'bordado', 'taller', 'lavado', 'otro')),
            size text NOT NULL DEFAULT '',
            quantity integer NOT NULL CHECK (quantity > 0 AND quantity <= 100000),
            note text NOT NULL DEFAULT '',
            event_date date NOT NULL,
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            voided_at timestamptz NULL,
            voided_by varchar(200) NULL,
            void_reason text NULL,
            CHECK ((kind = 'novedad') = (section IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reference_cut_movements_company_ref_date "
        "ON reference_cut_movements (company_id, reference_id, event_date)"
    )


def downgrade() -> None:
    # Solo aditivo: bajar no borra datos de referencias ni movimientos.
    pass
