"""workforce attendance jornada

Revision ID: 010b_workforce_attendance
Revises: 010a_workforce_personnel_history
Create Date: 2026-05-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "010b_workforce_attendance"
down_revision: Union[str, None] = "010a_workforce_personnel_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    op.create_table(
        "workforce_attendance_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_label", sa.String(length=180), nullable=False),
        sa.Column("employee_name", sa.String(length=180), nullable=True),
        sa.Column("employee_role", sa.String(length=80), nullable=True),
        sa.Column("status_after", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False, server_default=sa.text("'client'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_workforce_attendance_events_company_id", "workforce_attendance_events", ["company_id"])
    op.create_index("ix_workforce_attendance_events_employee_id", "workforce_attendance_events", ["employee_id"])
    op.create_index("ix_workforce_attendance_events_event_type", "workforce_attendance_events", ["event_type"])
    op.create_index("ix_workforce_attendance_events_created_at", "workforce_attendance_events", ["created_at"])
    op.create_index("ix_workforce_attendance_events_company_created", "workforce_attendance_events", ["company_id", "created_at"])

    op.create_table(
        "workforce_attendance_status",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default=sa.text("'not_started'")),
        sa.Column("last_event_type", sa.String(length=80), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("break_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worked_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("break_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "employee_id", name="uq_workforce_attendance_status_company_employee"),
    )

    op.create_index("ix_workforce_attendance_status_company_id", "workforce_attendance_status", ["company_id"])
    op.create_index("ix_workforce_attendance_status_employee_id", "workforce_attendance_status", ["employee_id"])
    op.create_index("ix_workforce_attendance_status_status", "workforce_attendance_status", ["status"])


def downgrade() -> None:
    op.drop_index("ix_workforce_attendance_status_status", table_name="workforce_attendance_status")
    op.drop_index("ix_workforce_attendance_status_employee_id", table_name="workforce_attendance_status")
    op.drop_index("ix_workforce_attendance_status_company_id", table_name="workforce_attendance_status")
    op.drop_table("workforce_attendance_status")

    op.drop_index("ix_workforce_attendance_events_company_created", table_name="workforce_attendance_events")
    op.drop_index("ix_workforce_attendance_events_created_at", table_name="workforce_attendance_events")
    op.drop_index("ix_workforce_attendance_events_event_type", table_name="workforce_attendance_events")
    op.drop_index("ix_workforce_attendance_events_employee_id", table_name="workforce_attendance_events")
    op.drop_index("ix_workforce_attendance_events_company_id", table_name="workforce_attendance_events")
    op.drop_table("workforce_attendance_events")
