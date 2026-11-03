"""Auditoria de ajustes masivos de marcaciones (antes y despues, quien y cuando)

Revision ID: 025a_attendance_adjustments
Revises: 024z_reports_board
Create Date: 2026-11-03

Aditiva: una tabla nueva y pequena (texto y JSON, una fila por persona y dia ajustado). No toca
datos. La llena un script aprobado por el dueno; sin script queda vacia.
"""
from __future__ import annotations

from alembic import op

revision = "025a_attendance_adjustments"
down_revision = "024z_reports_board"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS workforce_attendance_adjustments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            batch varchar(80) NOT NULL,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            work_date date NOT NULL,
            reason text NOT NULL,
            actor varchar(200) NOT NULL,
            before_json jsonb NOT NULL,
            after_json jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            undone_at timestamptz NULL,
            undone_by varchar(200) NULL
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_adjustment_active
        ON workforce_attendance_adjustments (company_id, batch, employee_id, work_date) WHERE undone_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workforce_attendance_adjustments")
