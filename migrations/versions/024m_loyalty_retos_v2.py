"""retos para las mesas (interruptor loyalty_retos_v2): resultado, ganador y premio

Revision ID: 024m_loyalty_retos_v2
Revises: 024l_billing_drafts
Create Date: 2026-10-18

Aditiva (nada se borra ni se reescribe):
- hospitality_loyalty_campaigns: reglas con las que se creo el reto (rules_version:
  1 = de antes, 2 = Retos para las mesas), pronosticos hasta (polla), respuesta
  correcta en secreto (Si/No y V/F), resultado, ganador, cierre, estado del premio
  (pendiente / entregado, con hora y quien) y la ronda de desempate.
- loyalty_game_players: mesa del jugador (solo en rondas de desempate) con una
  persona por mesa (indice unico parcial: las rondas de siempre quedan en NULL).
Los retos de antes quedan con rules_version 1 y siguen igual.
"""
from __future__ import annotations

from alembic import op

revision = "024m_loyalty_retos_v2"
down_revision = "024l_billing_drafts"
branch_labels = None
depends_on = None

CAMPAIGN_COLUMNS = (
    "rules_version integer NOT NULL DEFAULT 1",
    "predictions_close_at timestamptz NULL",
    "secret_answer_key varchar(40) NOT NULL DEFAULT ''",
    "result_status varchar(20) NOT NULL DEFAULT ''",
    "result jsonb NOT NULL DEFAULT '{}'::jsonb",
    "winner jsonb NULL",
    "closed_at timestamptz NULL",
    "closed_by varchar(200) NULL",
    "prize_status varchar(20) NOT NULL DEFAULT ''",
    "prize_delivered_at timestamptz NULL",
    "prize_delivered_by varchar(200) NULL",
    "tiebreak_round_id uuid NULL",
)


def upgrade() -> None:
    for column in CAMPAIGN_COLUMNS:
        op.execute(f"ALTER TABLE IF EXISTS hospitality_loyalty_campaigns ADD COLUMN IF NOT EXISTS {column}")
    op.execute("ALTER TABLE IF EXISTS loyalty_game_players ADD COLUMN IF NOT EXISTS table_key varchar(120) NULL")
    op.execute("ALTER TABLE IF EXISTS loyalty_game_players ADD COLUMN IF NOT EXISTS table_number varchar(120) NULL")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_loyalty_game_players_round_table
        ON loyalty_game_players (round_id, table_key) WHERE table_key IS NOT NULL""")


def downgrade() -> None:
    # Aditiva: bajar no borra retos, resultados ni jugadores.
    pass
