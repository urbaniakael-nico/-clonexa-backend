"""Board de gerencia: perimetros y supervisores por lugar de trabajo (interruptor reports_board)

Revision ID: 024z_reports_board
Revises: 024y_open_shift_alert
Create Date: 2026-11-03

Aditiva: dos tablas nuevas y pequenas (texto y numeros, sin archivos); no cambia datos y
no crea ningun perimetro: los carga el dueno desde Administrar lugares.
- work_location_perimeters: nombre, centro (lat/lng) y radio en metros por lugar.
- work_location_supervisors: quien supervisa cada lugar (empleados de la empresa).
"""
from __future__ import annotations

from alembic import op

revision = "024z_reports_board"
down_revision = "024y_open_shift_alert"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS work_location_perimeters (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id uuid NOT NULL REFERENCES work_locations(id) ON DELETE CASCADE,
            name varchar(80) NOT NULL,
            latitude numeric(10,7) NOT NULL,
            longitude numeric(10,7) NOT NULL,
            radius_m integer NOT NULL DEFAULT 300,
            created_by varchar(200) NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_work_location_perimeters_place ON work_location_perimeters (company_id, location_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS work_location_supervisors (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id uuid NOT NULL REFERENCES work_locations(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            created_by varchar(200) NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (location_id, employee_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_work_location_supervisors_company ON work_location_supervisors (company_id, employee_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS work_location_supervisors")
    op.execute("DROP TABLE IF EXISTS work_location_perimeters")
