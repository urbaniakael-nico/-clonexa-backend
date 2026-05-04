"""create core tables

Revision ID: 0001
Revises:
Create Date: 2026-04-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def uuid_pk():
    return sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "companies",
        uuid_pk(),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("plan", sa.String(length=50), nullable=False),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_companies_status", "companies", ["status"])

    op.create_table(
        "employees",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=180), nullable=False),
        sa.Column("document_id", sa.String(length=80), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=180), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("employee_type", sa.String(length=50), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "document_id", name="uq_employees_company_document_id"),
        sa.UniqueConstraint("company_id", "phone", name="uq_employees_company_phone"),
    )
    op.create_index("ix_employees_company_status", "employees", ["company_id", "status"])

    op.create_table(
        "roles",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("permissions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "code", name="uq_roles_company_code"),
    )

    op.create_table(
        "employee_roles",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "employee_id", "role_id", name="uq_employee_roles_company_employee_role"),
    )

    op.create_table(
        "bot_users",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("external_user_id", sa.String(length=120), nullable=False),
        sa.Column("chat_id", sa.String(length=120), nullable=True),
        sa.Column("username", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "channel", "external_user_id", name="uq_bot_users_company_channel_external"),
    )
    op.create_index("ix_bot_users_company_employee", "bot_users", ["company_id", "employee_id"])

    op.create_table(
        "work_events",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_id", sa.String(length=160), nullable=False),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("source_channel", sa.String(length=50), nullable=False),
        sa.Column("source_ref", sa.String(length=180), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "event_id", name="uq_work_events_company_event_id"),
    )
    op.create_index("ix_work_events_company_type_time", "work_events", ["company_id", "event_type", "occurred_at"])
    op.create_index("ix_work_events_company_employee_time", "work_events", ["company_id", "employee_id", "occurred_at"])
    op.create_index("ix_work_events_company_module_time", "work_events", ["company_id", "module", "occurred_at"])
    op.create_index("ix_work_events_company_status", "work_events", ["company_id", "status"])

    op.create_table(
        "work_sessions",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_event_db_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("end_event_db_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Numeric(12, 2), nullable=True),
        sa.Column("work_type", sa.String(length=80), nullable=True),
        sa.Column("reference_type", sa.String(length=80), nullable=True),
        sa.Column("reference_id", sa.String(length=120), nullable=True),
        sa.Column("location_id", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["start_event_db_id"], ["work_events.id"]),
        sa.ForeignKeyConstraint(["end_event_db_id"], ["work_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_sessions_company_employee_started", "work_sessions", ["company_id", "employee_id", "started_at"])
    op.create_index("ix_work_sessions_company_module_status", "work_sessions", ["company_id", "module", "status"])
    op.create_index("ix_work_sessions_company_status", "work_sessions", ["company_id", "status"])
    op.create_index("ix_work_sessions_company_started", "work_sessions", ["company_id", "started_at"])
    op.create_index("ix_work_sessions_company_ended", "work_sessions", ["company_id", "ended_at"])
    op.create_index(
        "uq_work_sessions_one_active_per_employee",
        "work_sessions",
        ["company_id", "employee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "employee_current_status",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("module", sa.String(length=50), nullable=True),
        sa.Column("active_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_id", sa.String(length=160), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["active_session_id"], ["work_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "employee_id", name="uq_employee_current_status_company_employee"),
    )
    op.create_index("ix_employee_current_status_company_status", "employee_current_status", ["company_id", "status"])
    op.create_index("ix_employee_current_status_company_module_status", "employee_current_status", ["company_id", "module", "status"])

    op.create_table(
        "inventory_items",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("min_stock", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "sku", name="uq_inventory_items_company_sku"),
    )
    op.create_index("ix_inventory_items_company_category", "inventory_items", ["company_id", "category"])
    op.create_index("ix_inventory_items_company_status", "inventory_items", ["company_id", "status"])

    op.create_table(
        "inventory_locations",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("module", sa.String(length=50), nullable=True),
        sa.Column("reference_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_locations_company_type", "inventory_locations", ["company_id", "type"])
    op.create_index("ix_inventory_locations_company_module", "inventory_locations", ["company_id", "module"])

    op.create_table(
        "inventory_movements",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_db_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("movement_type", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["inventory_items.id"]),
        sa.ForeignKeyConstraint(["from_location_id"], ["inventory_locations.id"]),
        sa.ForeignKeyConstraint(["to_location_id"], ["inventory_locations.id"]),
        sa.ForeignKeyConstraint(["event_db_id"], ["work_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_movements_company_item_time", "inventory_movements", ["company_id", "item_id", "occurred_at"])
    op.create_index("ix_inventory_movements_company_type", "inventory_movements", ["company_id", "movement_type"])
    op.create_index("ix_inventory_movements_company_from", "inventory_movements", ["company_id", "from_location_id"])
    op.create_index("ix_inventory_movements_company_to", "inventory_movements", ["company_id", "to_location_id"])
    op.create_index("ix_inventory_movements_company_time", "inventory_movements", ["company_id", "occurred_at"])

    op.create_table(
        "payroll_periods",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("period_type", sa.String(length=40), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "starts_at", "ends_at", name="uq_payroll_periods_company_range"),
    )
    op.create_index("ix_payroll_periods_company_range", "payroll_periods", ["company_id", "starts_at", "ends_at"])

    op.create_table(
        "payroll_entries",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("regular_minutes", sa.Numeric(12, 2), nullable=False),
        sa.Column("overtime_minutes", sa.Numeric(12, 2), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("deductions", sa.Numeric(14, 2), nullable=False),
        sa.Column("adjustments", sa.Numeric(14, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["period_id"], ["payroll_periods.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "period_id", "employee_id", name="uq_payroll_entries_company_period_employee"),
    )
    op.create_index("ix_payroll_entries_company_employee", "payroll_entries", ["company_id", "employee_id"])
    op.create_index("ix_payroll_entries_company_status", "payroll_entries", ["company_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_payroll_entries_company_status", table_name="payroll_entries")
    op.drop_index("ix_payroll_entries_company_employee", table_name="payroll_entries")
    op.drop_table("payroll_entries")
    op.drop_index("ix_payroll_periods_company_range", table_name="payroll_periods")
    op.drop_table("payroll_periods")
    op.drop_index("ix_inventory_movements_company_time", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_company_to", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_company_from", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_company_type", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_company_item_time", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_index("ix_inventory_locations_company_module", table_name="inventory_locations")
    op.drop_index("ix_inventory_locations_company_type", table_name="inventory_locations")
    op.drop_table("inventory_locations")
    op.drop_index("ix_inventory_items_company_status", table_name="inventory_items")
    op.drop_index("ix_inventory_items_company_category", table_name="inventory_items")
    op.drop_table("inventory_items")
    op.drop_index("ix_employee_current_status_company_module_status", table_name="employee_current_status")
    op.drop_index("ix_employee_current_status_company_status", table_name="employee_current_status")
    op.drop_table("employee_current_status")
    op.drop_index("uq_work_sessions_one_active_per_employee", table_name="work_sessions")
    op.drop_index("ix_work_sessions_company_ended", table_name="work_sessions")
    op.drop_index("ix_work_sessions_company_started", table_name="work_sessions")
    op.drop_index("ix_work_sessions_company_status", table_name="work_sessions")
    op.drop_index("ix_work_sessions_company_module_status", table_name="work_sessions")
    op.drop_index("ix_work_sessions_company_employee_started", table_name="work_sessions")
    op.drop_table("work_sessions")
    op.drop_index("ix_work_events_company_status", table_name="work_events")
    op.drop_index("ix_work_events_company_module_time", table_name="work_events")
    op.drop_index("ix_work_events_company_employee_time", table_name="work_events")
    op.drop_index("ix_work_events_company_type_time", table_name="work_events")
    op.drop_table("work_events")
    op.drop_index("ix_bot_users_company_employee", table_name="bot_users")
    op.drop_table("bot_users")
    op.drop_table("employee_roles")
    op.drop_table("roles")
    op.drop_index("ix_employees_company_status", table_name="employees")
    op.drop_table("employees")
    op.drop_index("ix_companies_status", table_name="companies")
    op.drop_table("companies")
