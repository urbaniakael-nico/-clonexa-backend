"""Aviso de turno abierto y cierre manual con auditoria (interruptor open_shift_alert)

Revision ID: 024y_open_shift_alert
Revises: 024x_work_locations
Create Date: 2026-11-02

Aditiva: dos tablas nuevas, pequenas (texto y fechas, sin archivos); no cambia datos.
- open_shift_alerts: un aviso por turno (empresa, empleado, hora de inicio del turno)
  para no repetirlo; guarda a quien se envio.
- shift_manual_closes: cada "Cerrar turno" del portal: quien, cuando, hora de inicio
  original, hora de salida puesta, estado original y la nota obligatoria.
"""
from __future__ import annotations

from alembic import op

revision = "024y_open_shift_alert"
down_revision = "024x_work_locations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS open_shift_alerts (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            shift_started_at timestamptz NOT NULL,
            alerted_at timestamptz NOT NULL DEFAULT now(),
            hours_open numeric(8,2) NULL,
            recipients jsonb NOT NULL DEFAULT '[]'::jsonb,
            PRIMARY KEY (company_id, employee_id, shift_started_at)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS shift_manual_closes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            employee_name varchar(200) NULL,
            original_status varchar(40) NULL,
            shift_started_at timestamptz NULL,
            end_at timestamptz NOT NULL,
            note text NOT NULL,
            closed_by varchar(200) NULL,
            closed_by_user_id uuid NULL,
            closed_at timestamptz NOT NULL DEFAULT now(),
            attendance_event_id uuid NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_shift_manual_closes_company ON shift_manual_closes (company_id, closed_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shift_manual_closes")
    op.execute("DROP TABLE IF EXISTS open_shift_alerts")
