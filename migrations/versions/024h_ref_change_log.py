"""referencias v2: bitacora de cambios de datos (para revertir) y referencia = nombre

Revision ID: 024h_ref_change_log
Revises: 024g_ref_op_order
Create Date: 2026-10-13

- reference_change_log: cada cambio de datos de Referencias v2 que no hace una
  persona campo por campo (meta = suma de cortes, igualar meta, conversion de
  tallas, union de filas) queda con su valor viejo y nuevo, por lote (batch_id),
  para poder revertirlo exacto. Solo se agregan filas.
- La orden operacional pasa a agruparse por nombre (antes nombre + color): la
  clave "nombre|color" queda como "nombre". Hoy no hay filas; si hubiera dos de
  la misma referencia con colores distintos, la segunda conserva su clave vieja.
No borra nada.
"""
from __future__ import annotations

from alembic import op

revision = "024h_ref_change_log"
down_revision = "024g_ref_op_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reference_change_log (
            id bigserial PRIMARY KEY,
            company_id text NOT NULL,
            batch_id uuid NOT NULL,
            reason varchar(40) NOT NULL,
            table_name varchar(80) NOT NULL,
            row_id text NOT NULL,
            column_name varchar(80) NOT NULL,
            old_value text NULL,
            new_value text NULL,
            actor varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            reverted_at timestamptz NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_reference_change_log_company_batch ON reference_change_log (company_id, batch_id)")
    op.execute("UPDATE reference_op_items SET group_key = split_part(group_key, '|', 1) WHERE position('|' in group_key) > 0")
    op.execute(
        """
        UPDATE reference_op_settings s SET group_key = split_part(s.group_key, '|', 1)
        WHERE position('|' in s.group_key) > 0
          AND NOT EXISTS (SELECT 1 FROM reference_op_settings o WHERE o.company_id = s.company_id AND o.group_key = split_part(s.group_key, '|', 1))
        """
    )


def downgrade() -> None:
    # Solo aditivo: bajar no borra la bitacora.
    pass
