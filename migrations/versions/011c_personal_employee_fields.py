"""011c personal employee fields

Revision ID: 011c_personal_employee_fields
Revises: 0005
Create Date: 2026-05-02T22:02:48.338558
"""

from alembic import op

revision = "011c_personal_employee_fields"
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS role VARCHAR(80) NOT NULL DEFAULT 'operator'")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS telegram_user_id VARCHAR(120)")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(120)")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS hire_date VARCHAR(20)")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS hourly_rate_regular NUMERIC(14, 2) NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS hourly_rate_extra NUMERIC(14, 2) NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS deduction_1 NUMERIC(14, 2) NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS deduction_2 NUMERIC(14, 2) NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS notes TEXT")
    op.execute("UPDATE employees SET role = employee_type WHERE role IS NULL OR role = ''")


def downgrade() -> None:
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS notes")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS deduction_2")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS deduction_1")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS hourly_rate_extra")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS hourly_rate_regular")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS hire_date")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS telegram_username")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS telegram_user_id")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS role")
