"""Referencias: recepcion inicial al crear y "Referencia creada" en la bitacora (077A)

Revision ID: 025g_ref_initial_cut
Revises: 025f_ref_cycles
Create Date: 2026-11-09

Solo aditiva e idempotente; filas pequenas (texto corto, enteros y fechas; nada de imagenes ni
archivos). No toca ninguna fila existente.

- reference_cut_movements.origin: de donde viene un ingreso ('recepcion_inicial' al crear la
  referencia, 'carga_inicial' de la carga automatica de datos existentes; NULL = corte normal).
- reference_cut_movements.batch_id: el lote de la carga automatica (para revisarla o anularla).
- reference_events: lo que pasa a una referencia que no es un movimiento de corte ("Referencia
  creada", "Recepcion inicial corregida"), con quien, cuando y el detalle.
La carga de datos existentes la hace scripts/velvet_recepcion_inicial.py (vista previa y aplicar).
"""
from __future__ import annotations

from alembic import op

revision = "025g_ref_initial_cut"
down_revision = "025f_ref_cycles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE reference_cut_movements ADD COLUMN IF NOT EXISTS origin varchar(20) NULL")
    op.execute("ALTER TABLE reference_cut_movements ADD COLUMN IF NOT EXISTS batch_id uuid NULL")
    op.execute("""
        CREATE TABLE IF NOT EXISTS reference_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id text NOT NULL,
            ref_key text NOT NULL,
            reference_id text NULL,
            kind varchar(30) NOT NULL,
            actor varchar(200) NOT NULL,
            detail jsonb NOT NULL DEFAULT '{}'::jsonb,
            batch_id uuid NULL,
            at timestamptz NOT NULL DEFAULT now(),
            voided_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_reference_events_company ON reference_events (company_id, ref_key, at)")


def downgrade() -> None:
    # Nada se borra: la bitacora es auditoria.
    pass
