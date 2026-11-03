"""Board de gerencia: perimetros y supervisores por lugar de trabajo (interruptor reports_board)

Revision ID: 024z_reports_board
Revises: 024y_open_shift_alert
Create Date: 2026-11-03

Aditiva e idempotente; no borra datos y no crea ningun perimetro: los carga el dueno desde
Administrar lugares.
- work_location_perimeters YA EXISTE desde 024x (relacion lugar -> geocerca, sin uso y vacia
  en produccion). Se le agregan nombre, centro (lat/lng) y radio; el lugar sigue siendo su
  columna work_location_id. perimeter_id pasa a opcional porque los perimetros nuevos no
  apuntan a una geocerca; una fila vieja conserva su perimeter_id y queda con latitud NULL,
  por eso el Board solo lee y reemplaza filas con latitud.
- work_location_supervisors (nueva): quien supervisa cada lugar (empleados de la empresa).
"""
from __future__ import annotations

from alembic import op

revision = "024z_reports_board"
down_revision = "024y_open_shift_alert"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE work_location_perimeters
            ADD COLUMN IF NOT EXISTS name varchar(80) NULL,
            ADD COLUMN IF NOT EXISTS latitude numeric(10,7) NULL,
            ADD COLUMN IF NOT EXISTS longitude numeric(10,7) NULL,
            ADD COLUMN IF NOT EXISTS radius_m integer NOT NULL DEFAULT 300,
            ADD COLUMN IF NOT EXISTS created_by varchar(200) NULL,
            ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()
    """)
    op.execute("ALTER TABLE work_location_perimeters ALTER COLUMN perimeter_id DROP NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_work_location_perimeters_place ON work_location_perimeters (company_id, work_location_id)")
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
    """Vuelve al esquema de 024x. La tabla es de 024x: no se borra; solo salen los perimetros
    del Board, que no caben en ese esquema (no tienen perimeter_id)."""
    op.execute("DROP TABLE IF EXISTS work_location_supervisors")
    op.execute("DROP INDEX IF EXISTS ix_work_location_perimeters_place")
    op.execute("DELETE FROM work_location_perimeters WHERE perimeter_id IS NULL")
    op.execute("ALTER TABLE work_location_perimeters ALTER COLUMN perimeter_id SET NOT NULL")
    op.execute("""
        ALTER TABLE work_location_perimeters
            DROP COLUMN IF EXISTS name,
            DROP COLUMN IF EXISTS latitude,
            DROP COLUMN IF EXISTS longitude,
            DROP COLUMN IF EXISTS radius_m,
            DROP COLUMN IF EXISTS created_by,
            DROP COLUMN IF EXISTS updated_at
    """)
