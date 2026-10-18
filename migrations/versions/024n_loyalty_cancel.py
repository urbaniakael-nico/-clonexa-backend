"""juegos en vivo: quien y cuando cancelo una ronda (Cancelar y reiniciar)

Revision ID: 024n_loyalty_cancel
Revises: 024m_loyalty_retos_v2
Create Date: 2026-10-18

Aditiva: loyalty_game_rounds.cancelled_at y cancelled_by. Las rondas de antes
quedan en NULL. (Los retos guardan la cancelacion en closed_at / closed_by con
status 'cancelled', columnas que ya existen.)
"""
from __future__ import annotations

from alembic import op

revision = "024n_loyalty_cancel"
down_revision = "024m_loyalty_retos_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS loyalty_game_rounds ADD COLUMN IF NOT EXISTS cancelled_at timestamptz NULL")
    op.execute("ALTER TABLE IF EXISTS loyalty_game_rounds ADD COLUMN IF NOT EXISTS cancelled_by varchar(200) NULL")


def downgrade() -> None:
    # Aditiva: bajar no borra rondas.
    pass
