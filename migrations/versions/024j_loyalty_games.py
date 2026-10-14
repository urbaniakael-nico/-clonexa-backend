"""juegos en vivo de Fidelizacion (interruptor loyalty_games): ruleta, memoria y trivia

Revision ID: 024j_loyalty_games
Revises: 024i_shifts_v1
Create Date: 2026-10-13

Solo aditivo y todo por company_id. No toca las tablas de Fidelizacion de
siempre (hospitality_loyalty_*), ni Hospitality, pedidos o musica.
- loyalty_game_settings: duraciones, rangos y premios por defecto, textos y el
  token secreto de la pantalla del bar.
- loyalty_game_rounds: memoria / trivia (y ruleta), registro -> en juego -> cerrado,
  premio, semilla, preguntas elegidas, inicio, fin y dia de jornada.
- loyalty_game_players: nombre visible, HMAC del documento (nunca el numero),
  ultimos 4 digitos, consentimiento (Ley 1581), progreso y resultado. El HMAC y
  los 4 digitos se purgan a los 30 dias.
- loyalty_roulette_draws: un numero por rango y noche (indice unico: no repite).
- loyalty_trivia_questions: banco editable por empresa (nivel 1-5, 3 opciones).
"""
from __future__ import annotations

from alembic import op

revision = "024j_loyalty_games"
down_revision = "024i_shifts_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_game_settings (
            company_id uuid PRIMARY KEY,
            settings jsonb NOT NULL DEFAULT '{}'::jsonb,
            screen_token varchar(64) NULL,
            updated_by varchar(200) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_loyalty_game_settings_screen ON loyalty_game_settings (screen_token) WHERE screen_token IS NOT NULL")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_game_rounds (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            kind varchar(12) NOT NULL CHECK (kind IN ('roulette', 'memory', 'trivia')),
            status varchar(14) NOT NULL DEFAULT 'registration' CHECK (status IN ('registration', 'playing', 'closed', 'cancelled')),
            prize varchar(160) NOT NULL DEFAULT '',
            seed bigint NOT NULL,
            game_day date NOT NULL,
            duration_seconds integer NOT NULL DEFAULT 120,
            question_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            results jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz NULL,
            ends_at timestamptz NULL,
            closed_at timestamptz NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_loyalty_game_rounds_company ON loyalty_game_rounds (company_id, created_at DESC)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_game_players (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            round_id uuid NOT NULL,
            display_name varchar(20) NOT NULL,
            document_hmac varchar(64) NULL,
            document_last4 varchar(4) NULL,
            consent boolean NOT NULL DEFAULT false,
            consent_at timestamptz NULL,
            hidden boolean NOT NULL DEFAULT false,
            progress jsonb NOT NULL DEFAULT '{}'::jsonb,
            score integer NOT NULL DEFAULT 0,
            score_ms integer NULL,
            finished_at timestamptz NULL,
            result varchar(12) NOT NULL DEFAULT 'playing',
            place integer NULL,
            validated_at timestamptz NULL,
            validated_by varchar(200) NULL,
            joined_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_loyalty_game_players_round ON loyalty_game_players (company_id, round_id, joined_at)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_loyalty_game_players_doc ON loyalty_game_players (round_id, document_hmac) WHERE document_hmac IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_loyalty_game_players_purge ON loyalty_game_players (joined_at) WHERE document_hmac IS NOT NULL")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_roulette_draws (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            game_day date NOT NULL,
            range_min integer NOT NULL,
            range_max integer NOT NULL,
            number integer NOT NULL,
            prize varchar(160) NOT NULL DEFAULT '',
            spun_by varchar(200) NOT NULL DEFAULT '',
            spun_at timestamptz NOT NULL DEFAULT now(),
            CHECK (range_min <= number AND number <= range_max)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_loyalty_roulette_draws_night ON loyalty_roulette_draws (company_id, game_day, range_min, range_max, number)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_trivia_questions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            level integer NOT NULL CHECK (level BETWEEN 1 AND 5),
            question varchar(240) NOT NULL,
            correct_answer varchar(120) NOT NULL,
            wrong_1 varchar(120) NOT NULL,
            wrong_2 varchar(120) NOT NULL,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_loyalty_trivia_questions_company ON loyalty_trivia_questions (company_id, level)")


def downgrade() -> None:
    # Solo aditivo: bajar no borra rondas, jugadores ni el banco de preguntas.
    pass
