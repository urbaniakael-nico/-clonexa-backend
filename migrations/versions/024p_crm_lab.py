"""CRM VELVET-LAB (interruptor crm_velvet_lab): PIN por colaborador y bitacora

Revision ID: 024p_crm_lab
Revises: 024o_qr_guest_name_log
Create Date: 2026-10-19

Aditiva (tablas nuevas):
- employee_crm_pins: PIN de 4 digitos por colaborador, SOLO su hash (bcrypt),
  intentos fallidos y bloqueo (5 intentos -> 5 minutos); lo asigna el dueno o admin.
- crm_lab_log: bitacora de lo que se hace desde el CRM (quien, que, cuando y desde
  donde: usuario del panel, IP y equipo).
El turno y las referencias se guardan en las MISMAS tablas del bot
(workforce_attendance_*, reference_work_sessions, reference_production_closures)
con source_channel = 'crm_lab'.
"""
from __future__ import annotations

from alembic import op

revision = "024p_crm_lab"
down_revision = "024o_qr_guest_name_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_crm_pins (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL,
            pin_hash text NOT NULL,
            failed_attempts integer NOT NULL DEFAULT 0,
            locked_until timestamptz NULL,
            set_by varchar(200) NOT NULL DEFAULT '',
            set_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, employee_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_lab_log (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NULL,
            employee_name varchar(200) NOT NULL DEFAULT '',
            action varchar(40) NOT NULL,
            detail text NOT NULL DEFAULT '',
            panel_user varchar(200) NOT NULL DEFAULT '',
            ip varchar(120) NOT NULL DEFAULT '',
            device varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_lab_log_company ON crm_lab_log (company_id, created_at DESC)")


def downgrade() -> None:
    # Aditiva: bajar no borra PIN ni bitacora.
    pass
