"""owner report: indices por fecha para el reporte del dueño (049G)

Revision ID: 021v_owner_report_idx
Revises: 021u_session_cutoff
Create Date: 2026-09-25

El reporte del dueño consulta pedidos y turnos de UNA empresa por rango de
fecha (tope de 93 dias). Estos indices hacen que "Este mes" siga rapido
cuando haya un año o mas de datos. Solo indices: ningun dato nuevo.
"""
from __future__ import annotations

from alembic import op

revision = "021v_owner_report_idx"
down_revision = "021u_session_cutoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_hospitality_orders_company_created "
        "ON hospitality_orders (company_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mp_work_sessions_company_started "
        "ON mini_panel_work_sessions (company_id, started_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mp_work_sessions_company_started")
    op.execute("DROP INDEX IF EXISTS ix_hospitality_orders_company_created")
