"""011A-0 company telegram bot instances

Revision ID: 011a0_company_bot_instances
Revises: 010b_r2_asistencia_bitacora
Create Date: 2026-05-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "011a0_company_bot_instances"
down_revision: Union[str, None] = "010b_r2_asistencia_bitacora"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    op.create_table(
        "company_bot_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False, server_default=sa.text("'telegram'")),
        sa.Column("name", sa.String(length=180), nullable=True),
        sa.Column("bot_username", sa.String(length=180), nullable=True),
        sa.Column("bot_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_mask", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default=sa.text("'configured'")),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "channel", name="uq_company_bot_instances_company_channel"),
    )

    op.create_index("ix_company_bot_instances_company_id", "company_bot_instances", ["company_id"])
    op.create_index("ix_company_bot_instances_channel", "company_bot_instances", ["channel"])
    op.create_index("ix_company_bot_instances_status", "company_bot_instances", ["status"])


def downgrade() -> None:
    op.drop_index("ix_company_bot_instances_status", table_name="company_bot_instances")
    op.drop_index("ix_company_bot_instances_channel", table_name="company_bot_instances")
    op.drop_index("ix_company_bot_instances_company_id", table_name="company_bot_instances")
    op.drop_table("company_bot_instances")
