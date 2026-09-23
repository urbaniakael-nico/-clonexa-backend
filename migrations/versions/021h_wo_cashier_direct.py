"""waiter ordering: caja direct sale switch

Revision ID: 021h_wo_cashier_direct
Revises: 021g_wo_kitchen_qty_btns
Create Date: 2026-09-23

Turns ON cashier_direct_sale for ASADERO EL SOCIO only (the company that
asked for it, and today the only one with the waiter_ordering module): the
caja panel can sell straight from the active inventory, as an independent
sale or added to a table, choosing per sale whether it goes to the kitchen.

Absent (= off) for every other company. Settings JSON only: no schema
change and no new stored bytes. Downgrade removes exactly this key.
"""
from __future__ import annotations

from alembic import op

revision = "021h_wo_cashier_direct"
down_revision = "021g_wo_kitchen_qty_btns"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"

SETTINGS_PATCH = '{"cashier_direct_sale": true}'


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE company_modules cm
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) || '{SETTINGS_PATCH}'::jsonb,
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE company_modules cm
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - 'cashier_direct_sale',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
