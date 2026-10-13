"""referencias v2: orden operacional por referencia (solo aditivo)

Revision ID: 024g_ref_op_order
Revises: 024f_closure_note
Create Date: 2026-10-13

Una referencia = nombre + color (todas sus tallas). Para cada una:
- reference_op_settings: valor de confeccion por prenda (uno para todas las tallas).
- reference_op_items: items de confeccion (nombre, minutos, talla '' = Todas,
  orden, quien/cuando). Se editan, reordenan y eliminan desde la pantalla.
Todo por company_id. No toca product_references, cortes ni movimientos.
"""
from __future__ import annotations

from alembic import op

revision = "024g_ref_op_order"
down_revision = "024f_closure_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reference_op_settings (
            company_id text NOT NULL,
            group_key text NOT NULL,
            value_per_garment numeric(14, 2) NOT NULL DEFAULT 0 CHECK (value_per_garment >= 0),
            updated_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, group_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reference_op_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id text NOT NULL,
            group_key text NOT NULL,
            name varchar(120) NOT NULL,
            minutes integer NOT NULL CHECK (minutes > 0 AND minutes <= 6000),
            size text NOT NULL DEFAULT '',
            position integer NOT NULL DEFAULT 0,
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_by varchar(200) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reference_op_items_company_group "
        "ON reference_op_items (company_id, group_key, position)"
    )


def downgrade() -> None:
    # Solo aditivo: bajar no borra la orden operacional guardada.
    pass
