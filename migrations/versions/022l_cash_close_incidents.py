"""caja: registro de lo que falla al cerrar la jornada (049Y)

Revision ID: 022l_cash_close_incidents
Revises: 022k_quantity_picker
Create Date: 2026-09-30

El cierre de jornada de la caja ya no se bloquea nunca por el arqueo ni por
el Z: si algo falla, el cajero cierra igual y aqui queda lo que paso (paso,
mensaje, lo que alcanzo a contar). El dueño lo ve junto al turno pendiente
de arqueo. Filas pequeñas de texto; solo las escribe la caja con el arqueo
activo (hoy ASADERO).
"""
from __future__ import annotations

from alembic import op

revision = "022l_cash_close_incidents"
down_revision = "022k_quantity_picker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cash_close_incidents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            cashier_session_id uuid NULL,
            cashier_user_id varchar(64) NOT NULL DEFAULT '',
            cashier_name varchar(180) NOT NULL DEFAULT '',
            step varchar(40) NOT NULL DEFAULT '',
            error varchar(1000) NOT NULL DEFAULT '',
            counted numeric(14,2) NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cash_close_incidents_session ON cash_close_incidents (company_id, cashier_session_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cash_close_incidents")
