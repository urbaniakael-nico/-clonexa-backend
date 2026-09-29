"""inventario: costo por unidad con 8 decimales (049R)

Revision ID: 022g_avg_cost_precision
Revises: 022f_carta_purchases
Create Date: 2026-09-29

El inventario de las empresas con Carta es una cuenta con dos saldos,
cantidad y dinero, y el costo por unidad es dinero / cantidad. Con 4
decimales el saldo de dinero no cuadra al peso ($229.600 / 14.725 gr =
$15,59252971 por gr). Solo se amplia la columna: ningun valor cambia.
"""
from __future__ import annotations

from alembic import op

revision = "022g_avg_cost_precision"
down_revision = "022f_carta_purchases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE inventory_items ALTER COLUMN avg_cost TYPE numeric(18, 8)")


def downgrade() -> None:
    op.execute("ALTER TABLE inventory_items ALTER COLUMN avg_cost TYPE numeric(14, 4)")
