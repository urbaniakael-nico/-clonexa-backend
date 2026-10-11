"""closure note: nota opcional al confirmar la hora real de salida (Nomina v2)

Revision ID: 024f_closure_note
Revises: 024e_reference_cuts
Create Date: 2026-10-11

Solo aditivo: workforce_session_closures gana real_end_note (texto, vacio por
defecto). Se escribe en el MISMO UPDATE que confirma la hora real (una sola
vez); el trigger de bloqueo sigue igual. No cambia ninguna fila existente.
"""
from __future__ import annotations

from alembic import op

revision = "024f_closure_note"
down_revision = "024e_reference_cuts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workforce_session_closures ADD COLUMN IF NOT EXISTS real_end_note varchar(300) NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE workforce_session_closures DROP COLUMN IF EXISTS real_end_note")
