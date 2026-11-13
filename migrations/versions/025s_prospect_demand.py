"""prospeccion por demanda: registro de cada corrida (interno de Clonexa, sin company_id)

Revision ID: 025s_prospect_demand
Revises: 025r_iconos_carta
Create Date: 2026-11-13

Aditiva e idempotente: prospect_demand_log guarda, por corrida del plan de busquedas, cuantos
prospectos "listos" habia, el umbral, cuantas busquedas se pidieron y el motivo
("hay N listos, no se busco"). El umbral vive en prospect_settings (ready_target).
"""
from __future__ import annotations

from alembic import op

revision = "025s_prospect_demand"
down_revision = "025r_iconos_carta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_demand_log (
          id BIGSERIAL PRIMARY KEY,
          local_date DATE NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          listos INTEGER NOT NULL DEFAULT 0,
          umbral INTEGER NOT NULL DEFAULT 0,
          busquedas INTEGER NOT NULL DEFAULT 0,
          motivo VARCHAR(200) NOT NULL DEFAULT ''
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospect_demand_log_day ON prospect_demand_log (local_date, id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prospect_demand_log")
