"""create packages modules

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "modules",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_modules_code"),
    )

    op.create_table(
        "packages",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_packages_code"),
    )

    op.create_table(
        "package_modules",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("package_id", UUID, sa.ForeignKey("packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_id", UUID, sa.ForeignKey("modules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("package_id", "module_id", name="uq_package_modules_package_module"),
    )
    op.create_index("ix_package_modules_package_id", "package_modules", ["package_id"])
    op.create_index("ix_package_modules_module_id", "package_modules", ["module_id"])

    op.create_table(
        "company_modules",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_id", UUID, sa.ForeignKey("modules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "module_id", name="uq_company_modules_company_module"),
    )
    op.create_index("ix_company_modules_company_id", "company_modules", ["company_id"])
    op.create_index("ix_company_modules_module_id", "company_modules", ["module_id"])

    op.create_table(
        "company_package_assignments",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package_id", UUID, sa.ForeignKey("packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "package_id", name="uq_company_package_assignments_company_package"),
    )
    op.create_index("ix_company_package_assignments_company_id", "company_package_assignments", ["company_id"])
    op.create_index("ix_company_package_assignments_package_id", "company_package_assignments", ["package_id"])


def downgrade() -> None:
    op.drop_index("ix_company_package_assignments_package_id", table_name="company_package_assignments")
    op.drop_index("ix_company_package_assignments_company_id", table_name="company_package_assignments")
    op.drop_table("company_package_assignments")

    op.drop_index("ix_company_modules_module_id", table_name="company_modules")
    op.drop_index("ix_company_modules_company_id", table_name="company_modules")
    op.drop_table("company_modules")

    op.drop_index("ix_package_modules_module_id", table_name="package_modules")
    op.drop_index("ix_package_modules_package_id", table_name="package_modules")
    op.drop_table("package_modules")

    op.drop_table("packages")
    op.drop_table("modules")
