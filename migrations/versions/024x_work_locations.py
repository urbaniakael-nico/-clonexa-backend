"""Lugares de trabajo por empresa (interruptor work_locations)

Revision ID: 024x_work_locations
Revises: 024w_nexa_whatsapp
Create Date: 2026-11-01

Aditiva: tablas nuevas y una columna nullable; no borra ni cambia datos.
- work_locations: lugares de cada empresa (nombre, sigla, zona horaria IANA,
  activo, orden). Nunca se borran: se desactivan.
- employees.work_location_id: lugar actual del empleado (NULL = sin asignar).
  Ningun empleado queda asignado por esta migracion.
- work_location_changes: historial de traslados (empleado, lugar anterior,
  lugar nuevo, fecha, quien lo cambio) para que la nomina no mezcle lugares.
- work_location_perimeters: relacion preparada lugar -> geocercas
  (company_gps_perimeters). La logica del GPS no la usa todavia.
- Siembra para VOLTAGE (f1e8f774-...): Virginia (VA, America/New_York) y
  Alabama (AL, America/Chicago), solo si la empresa existe.
"""
from __future__ import annotations

from alembic import op

revision = "024x_work_locations"
down_revision = "024w_nexa_whatsapp"
branch_labels = None
depends_on = None

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS work_locations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name varchar(80) NOT NULL,
            code varchar(8) NULL,
            timezone varchar(64) NOT NULL DEFAULT 'America/Bogota',
            is_active boolean NOT NULL DEFAULT true,
            sort_order integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_work_locations_company_name ON work_locations (company_id, lower(name))")
    op.execute("CREATE INDEX IF NOT EXISTS ix_work_locations_company ON work_locations (company_id, sort_order)")

    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS work_location_id uuid NULL REFERENCES work_locations(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_employees_work_location ON employees (company_id, work_location_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS work_location_changes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            from_location_id uuid NULL REFERENCES work_locations(id) ON DELETE SET NULL,
            to_location_id uuid NULL REFERENCES work_locations(id) ON DELETE SET NULL,
            from_name varchar(80) NULL,
            to_name varchar(80) NULL,
            changed_at timestamptz NOT NULL DEFAULT now(),
            changed_by varchar(200) NULL,
            changed_by_user_id uuid NULL,
            source varchar(40) NOT NULL DEFAULT 'personal'
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_work_location_changes_emp ON work_location_changes (company_id, employee_id, changed_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS work_location_perimeters (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            work_location_id uuid NOT NULL REFERENCES work_locations(id) ON DELETE CASCADE,
            perimeter_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_work_location_perimeters_perimeter UNIQUE (perimeter_id)
        )
    """)

    op.execute(f"""
        INSERT INTO work_locations (company_id, name, code, timezone, is_active, sort_order)
        SELECT c.id, v.name, v.code, v.tz, true, v.ord
        FROM companies c
        CROSS JOIN (VALUES ('Virginia', 'VA', 'America/New_York', 1), ('Alabama', 'AL', 'America/Chicago', 2)) AS v(name, code, tz, ord)
        WHERE c.id = CAST('{VOLTAGE}' AS uuid)
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS work_location_perimeters")
    op.execute("DROP TABLE IF EXISTS work_location_changes")
    op.execute("DROP INDEX IF EXISTS ix_employees_work_location")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS work_location_id")
    op.execute("DROP TABLE IF EXISTS work_locations")
