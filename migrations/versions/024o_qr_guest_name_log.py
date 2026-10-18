"""bitacora de correcciones del nombre de un invitado del QR (las hace el bar)

Revision ID: 024o_qr_guest_name_log
Revises: 024n_loyalty_cancel
Create Date: 2026-10-18

Aditiva: tabla nueva hospitality_guest_name_log (nombre anterior, nombre nuevo,
quien y cuando). Con el interruptor qr_welcome_name el nombre del invitado queda
fijo en el QR; solo el bar (dueno, admin o barman) lo corrige desde su panel.
"""
from __future__ import annotations

from alembic import op

revision = "024o_qr_guest_name_log"
down_revision = "024n_loyalty_cancel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS hospitality_guest_name_log (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            access_id uuid NULL,
            table_key varchar(120) NOT NULL DEFAULT '',
            account_id varchar(120) NOT NULL DEFAULT '',
            old_name varchar(180) NOT NULL DEFAULT '',
            new_name varchar(180) NOT NULL DEFAULT '',
            changed_by varchar(200) NOT NULL DEFAULT '',
            changed_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_hospitality_guest_name_log_company ON hospitality_guest_name_log (company_id, changed_at DESC)")


def downgrade() -> None:
    # Aditiva: bajar no borra la bitacora.
    pass
