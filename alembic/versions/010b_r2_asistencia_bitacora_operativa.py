"""010B-R2 asistencia como bitacora operativa

Revision ID: 010b_r2_asistencia_bitacora
Revises: 010b_workforce_attendance
Create Date: 2026-05-04
"""

from typing import Sequence, Union

from alembic import op


revision: str = "010b_r2_asistencia_bitacora"
down_revision: Union[str, None] = "010b_workforce_attendance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS module_code varchar(80) NOT NULL DEFAULT 'workforce';
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS source_channel varchar(80) NOT NULL DEFAULT 'client';
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS source_ref varchar(180) NULL;
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS bot_instance_id uuid NULL;
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS detail text NULL;
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS payload_json jsonb NOT NULL DEFAULT '{}'::jsonb;
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb;
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS latitude numeric(12,8) NULL;
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS longitude numeric(12,8) NULL;
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS evidence_url text NULL;
    """)
    op.execute("""
        ALTER TABLE workforce_attendance_events
        ADD COLUMN IF NOT EXISTS occurred_at timestamptz NOT NULL DEFAULT now();
    """)

    op.execute("""
        UPDATE workforce_attendance_events
           SET occurred_at = COALESCE(occurred_at, created_at),
               source_channel = COALESCE(NULLIF(source_channel, ''), NULLIF(source, ''), 'client'),
               detail = COALESCE(NULLIF(detail, ''), notes),
               module_code = COALESCE(NULLIF(module_code, ''), 'workforce')
         WHERE occurred_at IS NULL
            OR source_channel IS NULL
            OR module_code IS NULL
            OR detail IS NULL;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_workforce_attendance_events_company_occurred
        ON workforce_attendance_events(company_id, occurred_at);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_workforce_attendance_events_company_module
        ON workforce_attendance_events(company_id, module_code);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_workforce_attendance_events_company_source
        ON workforce_attendance_events(company_id, source_channel);
    """)


def downgrade() -> None:
    # No destructivo: no elimina columnas para no perder auditoría operativa.
    op.execute("DROP INDEX IF EXISTS ix_workforce_attendance_events_company_source;")
    op.execute("DROP INDEX IF EXISTS ix_workforce_attendance_events_company_module;")
    op.execute("DROP INDEX IF EXISTS ix_workforce_attendance_events_company_occurred;")
