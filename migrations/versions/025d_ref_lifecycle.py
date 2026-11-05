"""Referencias: corregir producido, renombrar y cerrar por talla (068A)

Revision ID: 025d_ref_lifecycle
Revises: 025c_lider_v2
Create Date: 2026-11-05

Solo aditiva e idempotente; cuatro tablas de filas pequenas (texto corto, enteros y fechas;
nada de imagenes ni archivos). No toca ninguna fila existente.

- reference_produced_corrections: cada correccion de lo producido (antes, despues, quien, cuando,
  motivo). Nada se borra: el ajuste es una fila de compensacion en reference_production_closures
  (source_channel = 'correccion') y closure_id apunta a ella.
- reference_name_history: nombre anterior, nuevo, quien y cuando.
- reference_size_closes: cierre final de una talla. El indice unico parcial deja un solo cierre
  vigente por talla; reabrir conserva la fila (reopened_*), asi queda la auditoria.
- reference_produced_requests: lo que el bot no registro por superar lo recibido, hasta que el
  portal lo apruebe o lo rechace.
"""
from __future__ import annotations

from alembic import op

revision = "025d_ref_lifecycle"
down_revision = "025c_lider_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS reference_produced_corrections (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id text NOT NULL,
            reference_id text NOT NULL,
            ref_key text NOT NULL,
            reference_name text NOT NULL,
            size text NOT NULL,
            before_qty integer NOT NULL,
            after_qty integer NOT NULL,
            reason text NOT NULL,
            closure_id text NULL,
            actor varchar(200) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ref_produced_corrections_company ON reference_produced_corrections (company_id, ref_key, created_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS reference_name_history (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id text NOT NULL,
            old_key text NOT NULL,
            new_key text NOT NULL,
            old_name text NOT NULL,
            new_name text NOT NULL,
            rows_changed jsonb NOT NULL DEFAULT '{}'::jsonb,
            actor varchar(200) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_reference_name_history_company ON reference_name_history (company_id, created_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS reference_size_closes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id text NOT NULL,
            ref_key text NOT NULL,
            size text NOT NULL,
            reference_id text NULL,
            closed_qty integer NOT NULL,
            meta integer NOT NULL DEFAULT 0,
            received integer NOT NULL DEFAULT 0,
            reason_code varchar(20) NULL,
            reason_note text NULL,
            prev_bot_active boolean NULL,
            prev_channel varchar(20) NULL,
            actor varchar(200) NOT NULL,
            closed_at timestamptz NOT NULL DEFAULT now(),
            reopened_at timestamptz NULL,
            reopened_by varchar(200) NULL,
            reopen_reason text NULL
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_reference_size_closes_live
        ON reference_size_closes (company_id, ref_key, lower(size)) WHERE reopened_at IS NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_reference_size_closes_company ON reference_size_closes (company_id, ref_key)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS reference_produced_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id text NOT NULL,
            reference_id text NOT NULL,
            ref_key text NOT NULL,
            reference_name text NOT NULL,
            size text NOT NULL,
            quantity integer NOT NULL,
            received integer NOT NULL,
            produced integer NOT NULL,
            employee_id text NOT NULL DEFAULT '',
            employee_name text NULL,
            telegram_user_id text NULL,
            source_channel varchar(20) NOT NULL DEFAULT 'telegram',
            status varchar(12) NOT NULL DEFAULT 'pending',
            decided_by varchar(200) NULL,
            decided_at timestamptz NULL,
            closure_id text NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ref_produced_requests_company ON reference_produced_requests (company_id, status, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reference_produced_requests")
    op.execute("DROP TABLE IF EXISTS reference_size_closes")
    op.execute("DROP TABLE IF EXISTS reference_name_history")
    op.execute("DROP TABLE IF EXISTS reference_produced_corrections")
