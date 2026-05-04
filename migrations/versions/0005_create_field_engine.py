"""create field engine phase 1

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "field_billing_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("client_name", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("budget_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("company_id", "code", name="uq_field_billing_projects_company_code"),
    )
    op.create_index("ix_field_billing_projects_company_id", "field_billing_projects", ["company_id"])
    op.create_index("ix_field_billing_projects_status", "field_billing_projects", ["status"])

    op.create_table(
        "field_technicians",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("default_billing_project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_billing_projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=96), nullable=False, server_default="technician"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_supervisor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hourly_rate_regular", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("hourly_rate_extra", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_1", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_2", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_field_technicians_company_id", "field_technicians", ["company_id"])
    op.create_index("ix_field_technicians_status", "field_technicians", ["status"])
    op.create_index("ix_field_technicians_is_supervisor", "field_technicians", ["is_supervisor"])
    op.create_index("ix_field_technicians_default_billing_project_id", "field_technicians", ["default_billing_project_id"])

    op.create_table(
        "field_materials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(length=96), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=False, server_default="unit"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("stock_available", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("stock_min", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("stock_in_field", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("stock_damaged", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("company_id", "name", name="uq_field_materials_company_name"),
    )
    op.create_index("ix_field_materials_company_id", "field_materials", ["company_id"])
    op.create_index("ix_field_materials_status", "field_materials", ["status"])
    op.create_index("ix_field_materials_sku", "field_materials", ["sku"])

    op.create_table(
        "field_technician_material_stock",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("technician_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_technicians.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("company_id", "technician_id", "material_id", name="uq_field_tech_material_stock_company_tech_material"),
    )
    op.create_index("ix_field_technician_material_stock_company_id", "field_technician_material_stock", ["company_id"])
    op.create_index("ix_field_technician_material_stock_technician_id", "field_technician_material_stock", ["technician_id"])
    op.create_index("ix_field_technician_material_stock_material_id", "field_technician_material_stock", ["material_id"])

    op.create_table(
        "field_material_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_technician_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_technicians.id"), nullable=False),
        sa.Column("billing_project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_billing_projects.id"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_field_material_requests_company_id", "field_material_requests", ["company_id"])
    op.create_index("ix_field_material_requests_requested_by_technician_id", "field_material_requests", ["requested_by_technician_id"])
    op.create_index("ix_field_material_requests_billing_project_id", "field_material_requests", ["billing_project_id"])
    op.create_index("ix_field_material_requests_status", "field_material_requests", ["status"])

    op.create_table(
        "field_material_request_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_material_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_materials.id"), nullable=False),
        sa.Column("quantity_requested", sa.Numeric(14, 2), nullable=False),
        sa.Column("quantity_delivered", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_field_material_request_items_company_id", "field_material_request_items", ["company_id"])
    op.create_index("ix_field_material_request_items_request_id", "field_material_request_items", ["request_id"])
    op.create_index("ix_field_material_request_items_material_id", "field_material_request_items", ["material_id"])

    op.create_table(
        "field_material_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_materials.id"), nullable=False),
        sa.Column("technician_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_technicians.id"), nullable=True),
        sa.Column("billing_project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_billing_projects.id"), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_material_requests.id"), nullable=True),
        sa.Column("movement_type", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("condition", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_field_material_movements_company_id", "field_material_movements", ["company_id"])
    op.create_index("ix_field_material_movements_material_id", "field_material_movements", ["material_id"])
    op.create_index("ix_field_material_movements_technician_id", "field_material_movements", ["technician_id"])
    op.create_index("ix_field_material_movements_billing_project_id", "field_material_movements", ["billing_project_id"])
    op.create_index("ix_field_material_movements_movement_type", "field_material_movements", ["movement_type"])
    op.create_index("ix_field_material_movements_created_at", "field_material_movements", ["created_at"])


def downgrade() -> None:
    op.drop_table("field_material_movements")
    op.drop_table("field_material_request_items")
    op.drop_table("field_material_requests")
    op.drop_table("field_technician_material_stock")
    op.drop_table("field_materials")
    op.drop_table("field_technicians")
    op.drop_table("field_billing_projects")
