"""workforce personnel history

Revision ID: 010a_workforce_personnel_history
Revises: 0002_create_packages_modules
Create Date: 2026-05-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "010a_workforce_personnel_history"
down_revision: Union[str, None] = "0002_create_packages_modules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    op.create_table(
        "workforce_personnel_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_label", sa.String(length=180), nullable=False),
        sa.Column("employee_name", sa.String(length=180), nullable=True),
        sa.Column("employee_role", sa.String(length=80), nullable=True),
        sa.Column("employee_status", sa.String(length=40), nullable=True),
        sa.Column("old_values_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("new_values_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("changed_fields_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False, server_default=sa.text("'client'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE", name="fk_workforce_personnel_history_company_id"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL", name="fk_workforce_personnel_history_employee_id"),
    )

    op.create_index("ix_workforce_personnel_history_company_id", "workforce_personnel_history", ["company_id"], unique=False)
    op.create_index("ix_workforce_personnel_history_employee_id", "workforce_personnel_history", ["employee_id"], unique=False)
    op.create_index("ix_workforce_personnel_history_event_type", "workforce_personnel_history", ["event_type"], unique=False)
    op.create_index("ix_workforce_personnel_history_created_at", "workforce_personnel_history", ["created_at"], unique=False)
    op.create_index("ix_workforce_personnel_history_company_created", "workforce_personnel_history", ["company_id", "created_at"], unique=False)
    op.create_index("ix_workforce_personnel_history_company_employee", "workforce_personnel_history", ["company_id", "employee_id"], unique=False)


    op.execute(
        """
        INSERT INTO workforce_personnel_history (
            company_id,
            employee_id,
            event_type,
            event_label,
            employee_name,
            employee_role,
            employee_status,
            old_values_json,
            new_values_json,
            changed_fields_json,
            source,
            notes,
            created_at
        )
        SELECT
            e.company_id,
            e.id,
            'employee_baseline',
            'Registro inicial',
            e.full_name,
            e.role,
            e.status,
            '{}'::jsonb,
            jsonb_build_object(
                'full_name', e.full_name,
                'document_id', e.document_id,
                'phone', e.phone,
                'email', e.email,
                'status', e.status,
                'employee_type', e.employee_type,
                'role', e.role,
                'telegram_user_id', e.telegram_user_id,
                'telegram_username', e.telegram_username,
                'hire_date', e.hire_date,
                'hourly_rate_regular', e.hourly_rate_regular::text,
                'hourly_rate_extra', e.hourly_rate_extra::text,
                'deduction_1', e.deduction_1::text,
                'deduction_2', e.deduction_2::text,
                'notes', e.notes
            ),
            '[]'::jsonb,
            'migration_010a',
            'Registro base generado al instalar Historial de Personal.',
            now()
        FROM employees e
        WHERE NOT EXISTS (
            SELECT 1
            FROM workforce_personnel_history h
            WHERE h.company_id = e.company_id
              AND h.employee_id = e.id
              AND h.event_type = 'employee_baseline'
        );
        """
    )


def downgrade() -> None:
    op.drop_index("ix_workforce_personnel_history_company_employee", table_name="workforce_personnel_history")
    op.drop_index("ix_workforce_personnel_history_company_created", table_name="workforce_personnel_history")
    op.drop_index("ix_workforce_personnel_history_created_at", table_name="workforce_personnel_history")
    op.drop_index("ix_workforce_personnel_history_event_type", table_name="workforce_personnel_history")
    op.drop_index("ix_workforce_personnel_history_employee_id", table_name="workforce_personnel_history")
    op.drop_index("ix_workforce_personnel_history_company_id", table_name="workforce_personnel_history")
    op.drop_table("workforce_personnel_history")
