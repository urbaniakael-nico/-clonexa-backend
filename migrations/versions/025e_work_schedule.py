"""Horario de la semana por operacion, aviso de salida del bot y cierre con motivo (071A)

Revision ID: 025e_work_schedule
Revises: 025d_ref_lifecycle
Create Date: 2026-11-07

Solo aditiva e idempotente; filas pequenas (horas en texto corto, fechas y enteros; nada de
imagenes ni archivos). No toca ninguna fila existente.

- work_schedule_weeks: el horario de UNA operacion para UNA semana (lunes). Sin fila para una
  semana, vale la ultima semana anterior guardada: asi cada semana copia la anterior sola.
- employee_schedule_slots: que horario (1, 2, 3...) usa cada persona. Sin fila: Horario 1.
- shift_schedule_prompts: el aviso de salida del bot por turno (cuando se pregunto, la respuesta,
  los motivos de "Sigo trabajando", si quedo Fuera de horario y si ya se aviso al supervisor).
- shift_manual_closes: motivo, detalle, horario usado y por donde se cerro (portal / lider).
"""
from __future__ import annotations

from alembic import op

revision = "025e_work_schedule"
down_revision = "025d_ref_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS work_schedule_weeks (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            work_location_id uuid NOT NULL REFERENCES work_locations(id) ON DELETE CASCADE,
            week_start date NOT NULL,
            slots jsonb NOT NULL DEFAULT '[]'::jsonb,
            updated_by varchar(200) NULL,
            updated_by_user_id uuid NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, work_location_id, week_start)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_schedule_slots (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            slot smallint NOT NULL DEFAULT 1,
            updated_by varchar(200) NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, employee_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS shift_schedule_prompts (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            shift_started_at timestamptz NOT NULL,
            scheduled_end_at timestamptz NOT NULL,
            slot smallint NOT NULL DEFAULT 1,
            state varchar(20) NOT NULL DEFAULT 'asked',
            asked_at timestamptz NULL,
            asks integer NOT NULL DEFAULT 0,
            next_ask_at timestamptz NULL,
            reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
            out_of_schedule_at timestamptz NULL,
            boss_notified_at timestamptz NULL,
            recipients jsonb NOT NULL DEFAULT '[]'::jsonb,
            silent boolean NOT NULL DEFAULT false,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, employee_id, shift_started_at)
        )
    """)
    op.execute("ALTER TABLE shift_manual_closes ADD COLUMN IF NOT EXISTS reason_code varchar(40) NULL")
    op.execute("ALTER TABLE shift_manual_closes ADD COLUMN IF NOT EXISTS reason_detail text NULL")
    op.execute("ALTER TABLE shift_manual_closes ADD COLUMN IF NOT EXISTS schedule_json jsonb NULL")
    op.execute("ALTER TABLE shift_manual_closes ADD COLUMN IF NOT EXISTS closed_via varchar(40) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE shift_manual_closes DROP COLUMN IF EXISTS closed_via")
    op.execute("ALTER TABLE shift_manual_closes DROP COLUMN IF EXISTS schedule_json")
    op.execute("ALTER TABLE shift_manual_closes DROP COLUMN IF EXISTS reason_detail")
    op.execute("ALTER TABLE shift_manual_closes DROP COLUMN IF EXISTS reason_code")
    op.execute("DROP TABLE IF EXISTS shift_schedule_prompts")
    op.execute("DROP TABLE IF EXISTS employee_schedule_slots")
    op.execute("DROP TABLE IF EXISTS work_schedule_weeks")
