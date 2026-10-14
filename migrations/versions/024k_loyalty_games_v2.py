"""juegos en vivo v2: reglas guardadas en la ronda, 7 diferencias y version del banco

Revision ID: 024k_loyalty_games_v2
Revises: 024j_loyalty_games
Create Date: 2026-10-14

Aditiva:
- loyalty_game_rounds.config: la configuracion con la que se creo la ronda
  (parejas, tiempo, reglas, escena y diferencias). Las rondas de antes quedan
  con {} y siguen con sus reglas originales (5 parejas / trivia de 5).
- loyalty_game_rounds.kind admite 'differences' (se amplia el CHECK; nada se borra).
- loyalty_game_settings.seed_version: hasta que version del banco inicial se
  sembro, para agregar solo preguntas nuevas sin duplicar ni tocar las editadas.
"""
from __future__ import annotations

from alembic import op

revision = "024k_loyalty_games_v2"
down_revision = "024j_loyalty_games"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE loyalty_game_rounds ADD COLUMN IF NOT EXISTS config jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE loyalty_game_rounds DROP CONSTRAINT IF EXISTS loyalty_game_rounds_kind_check")
    op.execute("ALTER TABLE loyalty_game_rounds ADD CONSTRAINT loyalty_game_rounds_kind_check CHECK (kind IN ('roulette', 'memory', 'trivia', 'differences'))")
    op.execute("ALTER TABLE loyalty_game_settings ADD COLUMN IF NOT EXISTS seed_version integer NOT NULL DEFAULT 1")


def downgrade() -> None:
    # Aditiva: bajar no borra rondas ni preguntas.
    pass
