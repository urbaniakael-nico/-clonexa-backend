"""Lider de operacion v2: PIN de marcacion, su auditoria y los intentos fallidos (067A)

Revision ID: 025c_lider_v2
Revises: 025b_lider_short_links
Create Date: 2026-11-04

Tres tablas de filas pequenas (solo texto corto y fechas; nada de imagenes ni archivos):
- employee_punch_pins: el PIN de marcacion de una persona, solo su HMAC. UNIQUE por empresa: la base
  misma impide que dos personas de la empresa tengan el mismo PIN.
- employee_punch_pin_audit: quien genero o quito un PIN y cuando (nunca el PIN).
- lider_pin_attempts: intentos fallidos por lider y operacion, para el bloqueo de 5 intentos / 15 min.

El cierre de un turno por el lider usa la tabla de auditoria de siempre: shift_manual_closes (024y).
"""
from __future__ import annotations

from alembic import op

revision = "025c_lider_v2"
down_revision = "025b_lider_short_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_punch_pins (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            pin_hash varchar(64) NOT NULL,
            created_by varchar(200) NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, employee_id),
            CONSTRAINT uq_employee_punch_pins_hash UNIQUE (company_id, pin_hash)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_punch_pin_audit (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL,
            employee_name varchar(200) NULL,
            action varchar(20) NOT NULL,
            actor varchar(200) NULL,
            at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_employee_punch_pin_audit_company ON employee_punch_pin_audit (company_id, at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS lider_pin_attempts (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            work_location_id uuid NOT NULL,
            device_key varchar(80) NOT NULL,
            failures int NOT NULL DEFAULT 0,
            first_failure_at timestamptz NULL,
            locked_until timestamptz NULL,
            PRIMARY KEY (company_id, work_location_id, device_key)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lider_pin_attempts")
    op.execute("DROP TABLE IF EXISTS employee_punch_pin_audit")
    op.execute("DROP TABLE IF EXISTS employee_punch_pins")
