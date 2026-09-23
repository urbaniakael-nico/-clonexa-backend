"""waiter ordering: kitchen 3-column board + quantity buttons

Revision ID: 021g_wo_kitchen_qty_btns
Revises: 021f_wo_role_fix
Create Date: 2026-09-23

Turns ON two new waiter_ordering switches for ASADERO EL SOCIO only (the
company that asked for them, and today the only one with the module):

- kitchen_board_columns: cocina board with Pedido nuevo / Preparando / Listo
  columns, the "Entregado" button + day history, and the mesero's
  "Mesa X lista para llevar" notices.
- quantity_buttons_enabled + quantity_buttons: the mesero picks 1/4, 1/2,
  3/4, 1, 2 with buttons instead of typing a number.

Both keys are absent (= off) for every other company. Only settings JSON
changes; no schema change and no new stored bytes.

Downgrade removes exactly the three keys this migration added.
"""
from __future__ import annotations

from alembic import op

revision = "021g_wo_kitchen_qty_btns"
down_revision = "021f_wo_role_fix"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"

SETTINGS_PATCH = (
    '{"kitchen_board_columns": true, '
    '"quantity_buttons_enabled": true, '
    '"quantity_buttons": ["1/4", "1/2", "3/4", "1", "2"]}'
)


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
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb)
                - 'kitchen_board_columns'
                - 'quantity_buttons_enabled'
                - 'quantity_buttons',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
