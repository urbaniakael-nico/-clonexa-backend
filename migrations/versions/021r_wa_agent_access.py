"""whatsapp: "puede consultar por WhatsApp" grants for the internal agent

Revision ID: 021r_wa_agent_access
Revises: 021q_sanidad_attachments
Create Date: 2026-09-24

SECURITY: the internal WhatsApp agent (nomina, CRM, produccion) answered
any number. It now answers only the linked number's own chat and the
Workforce phones listed here, which an admin grants one by one (nobody is
granted by default). The grant keeps the phone the employee had when it was
given; if that phone changes later, the grant stops working.
Text only, a handful of rows per company.
"""
from __future__ import annotations

from alembic import op

revision = "021r_wa_agent_access"
down_revision = "021q_sanidad_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_agent_access (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            phone varchar(20) NOT NULL,
            granted_by varchar(160) NOT NULL DEFAULT '',
            granted_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_whatsapp_agent_access UNIQUE (company_id, employee_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_whatsapp_agent_access_phone ON whatsapp_agent_access (company_id, phone)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS whatsapp_agent_access")
