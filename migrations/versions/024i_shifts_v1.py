"""turnos (modulo shifts): plantillas, reglas, cobertura, malla y cambios de turno

Revision ID: 024i_shifts_v1
Revises: 024h_ref_change_log
Create Date: 2026-10-13

Solo aditivo y todo por company_id. Usa los empleados de Personal (solo lee
employees); no toca Personal ni nomina.
- shift_templates: nombre, codigo, hora inicio/fin (fin <= inicio = nocturno), color, activo.
- shift_rules: descanso minimo, dias libres, maximo de dias y noches seguidas,
  tope semanal (vacio = el de Personal/nomina de la empresa) y tiempo de respuesta.
- shift_coverage: plantilla x rol -> personas minimas.
- shift_assignments: empleado, dia en que empieza el turno, plantilla, borrador/publicado.
- shift_change_requests: cambio de turno con candidatos ordenados, candidato actual,
  estado, vencimiento y bitacora.
- shift_bot_languages: ultimo idioma del celular de cada colaborador (para los avisos del bot).
"""
from __future__ import annotations

from alembic import op

revision = "024i_shifts_v1"
down_revision = "024h_ref_change_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_templates (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            name varchar(60) NOT NULL,
            code varchar(4) NOT NULL,
            start_time time NOT NULL,
            end_time time NOT NULL,
            color varchar(9) NOT NULL DEFAULT '#3b82f6',
            active boolean NOT NULL DEFAULT true,
            position integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_shift_templates_company ON shift_templates (company_id, position)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_rules (
            company_id uuid PRIMARY KEY,
            min_rest_hours integer NOT NULL DEFAULT 12 CHECK (min_rest_hours BETWEEN 0 AND 48),
            days_off_per_week integer NOT NULL DEFAULT 1 CHECK (days_off_per_week BETWEEN 0 AND 6),
            max_consecutive_days integer NOT NULL DEFAULT 6 CHECK (max_consecutive_days BETWEEN 1 AND 14),
            weekly_hours_cap numeric(5, 1) NULL CHECK (weekly_hours_cap IS NULL OR weekly_hours_cap BETWEEN 1 AND 112),
            max_consecutive_nights integer NOT NULL DEFAULT 3 CHECK (max_consecutive_nights BETWEEN 1 AND 14),
            response_hours numeric(4, 1) NOT NULL DEFAULT 2 CHECK (response_hours > 0 AND response_hours <= 72),
            updated_by varchar(200) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_coverage (
            company_id uuid NOT NULL,
            template_id uuid NOT NULL,
            role varchar(40) NOT NULL,
            min_people integer NOT NULL DEFAULT 0 CHECK (min_people BETWEEN 0 AND 50),
            PRIMARY KEY (company_id, template_id, role)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_assignments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            employee_id uuid NOT NULL,
            work_date date NOT NULL,
            week_start date NOT NULL,
            template_id uuid NOT NULL,
            status varchar(12) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (company_id, employee_id, work_date)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_shift_assignments_company_week ON shift_assignments (company_id, week_start)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_change_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            assignment_id uuid NOT NULL,
            requester_employee_id uuid NOT NULL,
            work_date date NOT NULL,
            template_id uuid NOT NULL,
            candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
            current_index integer NULL,
            status varchar(12) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'waiting', 'accepted', 'rejected', 'expired', 'cancelled')),
            uncovered boolean NOT NULL DEFAULT false,
            deadline_at timestamptz NULL,
            log jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_shift_change_requests_company ON shift_change_requests (company_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_shift_change_requests_waiting ON shift_change_requests (status, deadline_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_bot_languages (
            company_id uuid NOT NULL,
            employee_id uuid NOT NULL,
            language varchar(5) NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, employee_id)
        )
        """
    )


def downgrade() -> None:
    # Solo aditivo: bajar no borra la malla ni los cambios guardados.
    pass
