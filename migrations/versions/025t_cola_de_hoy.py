"""cola de hoy en la consola v2+ (interno de Clonexa, sin company_id)

Revision ID: 025t_cola_de_hoy
Revises: 025s_prospect_demand
Create Date: 2026-11-13

Aditiva e idempotente: prospect_contacts.liked_at guarda el paso opcional "Seguir y dar like" de la
tarjeta de la Cola de hoy (Instagram/Facebook se envian A MANO; nada automatico).
"""
from __future__ import annotations

from alembic import op

revision = "025t_cola_de_hoy"
down_revision = "025s_prospect_demand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE prospect_contacts ADD COLUMN IF NOT EXISTS liked_at TIMESTAMPTZ NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE prospect_contacts DROP COLUMN IF EXISTS liked_at")
