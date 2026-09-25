"""session cutoff: corte diario de sesiones y turnos abiertos (049D)

Revision ID: 021u_session_cutoff
Revises: 021t_nomina_colombia
Create Date: 2026-09-25

Aplica a TODAS las empresas.

- workforce_session_policy: hora del corte diario por empresa (00:00 por
  defecto; sin fila = 00:00) y horas tras las que una sesion abierta sale
  como alerta en vivo (12 por defecto).
- workforce_session_closures: cada turno que cerro el sistema (corte diario,
  cierre automatico o historico larguisimo) con la hora real de salida.
  Una vez confirmada, la fila no se puede modificar (trigger); solo se
  borra si se borra la empresa.
- Historico: los turnos de mini panel ya cerrados que duraron mas de 12 h
  quedan marcados closed_reason = 'historico_largo' para que la nomina no
  los pague en silencio. No se borra ni se cambia ninguna hora.
"""
from __future__ import annotations

from alembic import op

revision = "021u_session_cutoff"
down_revision = "021t_nomina_colombia"
branch_labels = None
depends_on = None

HISTORIC_HOURS = 12


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workforce_session_policy (
            company_id uuid PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            cutoff_time varchar(5) NOT NULL DEFAULT '00:00',
            alert_after_hours numeric(5,2) NOT NULL DEFAULT 12,
            last_cutoff_at timestamptz NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workforce_session_closures (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NULL,
            employee_name varchar(180) NOT NULL DEFAULT '',
            source varchar(20) NOT NULL,
            session_ref varchar(64) NOT NULL,
            panel_type varchar(40) NOT NULL DEFAULT '',
            reason varchar(40) NOT NULL,
            started_at timestamptz NOT NULL,
            system_end_at timestamptz NOT NULL,
            status varchar(20) NOT NULL DEFAULT 'pending',
            declared_end_at timestamptz NULL,
            declared_by_name varchar(180) NOT NULL DEFAULT '',
            declared_at timestamptz NULL,
            real_end_at timestamptz NULL,
            confirmed_by_name varchar(180) NOT NULL DEFAULT '',
            confirmed_by_user_id varchar(64) NOT NULL DEFAULT '',
            confirmed_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_session_closure_ref UNIQUE (company_id, source, session_ref)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_session_closures_company_status "
        "ON workforce_session_closures (company_id, status, system_end_at DESC)"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cx_session_closure_lock() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'confirmed' THEN
                RAISE EXCEPTION 'session_closure_locked';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_session_closure_lock ON workforce_session_closures")
    op.execute(
        """
        CREATE TRIGGER trg_session_closure_lock
        BEFORE UPDATE ON workforce_session_closures
        FOR EACH ROW EXECUTE FUNCTION cx_session_closure_lock()
        """
    )
    op.execute(
        f"""
        UPDATE mini_panel_work_sessions
           SET closed_reason = 'historico_largo'
         WHERE status = 'finished'
           AND ended_at IS NOT NULL
           AND COALESCE(closed_reason, '') = ''
           AND ended_at - started_at > INTERVAL '{HISTORIC_HOURS} hours'
        """
    )


def downgrade() -> None:
    op.execute("UPDATE mini_panel_work_sessions SET closed_reason = '' WHERE closed_reason = 'historico_largo'")
    op.execute("DROP TRIGGER IF EXISTS trg_session_closure_lock ON workforce_session_closures")
    op.execute("DROP FUNCTION IF EXISTS cx_session_closure_lock()")
    op.execute("DROP TABLE IF EXISTS workforce_session_closures")
    op.execute("DROP TABLE IF EXISTS workforce_session_policy")
