"""create packages and modules SaaS layer

Revision ID: 0002_create_packages_modules
Revises: 0001_initial
Create Date: 2026-04-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_create_packages_modules"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    op.create_table(
        "modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("code", name="uq_modules_code"),
    )
    op.create_index("ix_modules_code", "modules", ["code"], unique=False)
    op.create_index("ix_modules_category", "modules", ["category"], unique=False)

    op.create_table(
        "packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("code", name="uq_packages_code"),
    )
    op.create_index("ix_packages_code", "packages", ["code"], unique=False)

    op.create_table(
        "package_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["package_id"], ["packages.id"], ondelete="CASCADE", name="fk_package_modules_package_id"),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"], ondelete="CASCADE", name="fk_package_modules_module_id"),
        sa.UniqueConstraint("package_id", "module_id", name="uq_package_modules_package_module"),
    )
    op.create_index("ix_package_modules_package_id", "package_modules", ["package_id"], unique=False)
    op.create_index("ix_package_modules_module_id", "package_modules", ["module_id"], unique=False)

    op.create_table(
        "company_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE", name="fk_company_modules_company_id"),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"], ondelete="CASCADE", name="fk_company_modules_module_id"),
        sa.UniqueConstraint("company_id", "module_id", name="uq_company_modules_company_module"),
    )
    op.create_index("ix_company_modules_company_id", "company_modules", ["company_id"], unique=False)
    op.create_index("ix_company_modules_module_id", "company_modules", ["module_id"], unique=False)
    op.create_index("ix_company_modules_enabled", "company_modules", ["enabled"], unique=False)

    op.create_table(
        "company_package_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_company_package_assignments_status"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE", name="fk_company_package_assignments_company_id"),
        sa.ForeignKeyConstraint(["package_id"], ["packages.id"], ondelete="CASCADE", name="fk_company_package_assignments_package_id"),
        sa.UniqueConstraint("company_id", "package_id", name="uq_company_package_assignments_company_package"),
    )
    op.create_index("ix_company_package_assignments_company_id", "company_package_assignments", ["company_id"], unique=False)
    op.create_index("ix_company_package_assignments_package_id", "company_package_assignments", ["package_id"], unique=False)
    op.create_index("ix_company_package_assignments_status", "company_package_assignments", ["status"], unique=False)

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_company_one_active_package
        ON company_package_assignments(company_id)
        WHERE status = 'active';
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_company_one_active_package;")
    op.drop_index("ix_company_package_assignments_status", table_name="company_package_assignments")
    op.drop_index("ix_company_package_assignments_package_id", table_name="company_package_assignments")
    op.drop_index("ix_company_package_assignments_company_id", table_name="company_package_assignments")
    op.drop_table("company_package_assignments")

    op.drop_index("ix_company_modules_enabled", table_name="company_modules")
    op.drop_index("ix_company_modules_module_id", table_name="company_modules")
    op.drop_index("ix_company_modules_company_id", table_name="company_modules")
    op.drop_table("company_modules")

    op.drop_index("ix_package_modules_module_id", table_name="package_modules")
    op.drop_index("ix_package_modules_package_id", table_name="package_modules")
    op.drop_table("package_modules")

    op.drop_index("ix_packages_code", table_name="packages")
    op.drop_table("packages")

    op.drop_index("ix_modules_category", table_name="modules")
    op.drop_index("ix_modules_code", table_name="modules")
    op.drop_table("modules")
