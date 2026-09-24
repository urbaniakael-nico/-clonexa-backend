"""qr table guests: automatic "Persona N" per phone

Revision ID: 021n_qr_table_guests
Revises: 021m_qr_bar_menu_ttm
Create Date: 2026-09-23

One small row per phone that opens a QR table (per table activation): the
order in which it arrived (guest_number, never reused or renumbered within
that activation) and the name the person typed, if any. Customers who don't
type a name show as "Persona <guest_number>". Only used by companies with
the qr_bar_menu switch (today The Time Machine). No data is inserted.
"""
from __future__ import annotations

from alembic import op

revision = "021n_qr_table_guests"
down_revision = "021m_qr_bar_menu_ttm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hospitality_table_guests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            access_id uuid NOT NULL,
            table_key varchar(120) NOT NULL,
            account_id varchar(120) NOT NULL,
            guest_number integer NOT NULL,
            name varchar(180) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_hsp_table_guest_account UNIQUE (company_id, access_id, account_id),
            CONSTRAINT uq_hsp_table_guest_number UNIQUE (company_id, access_id, guest_number)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS hospitality_table_guests")
