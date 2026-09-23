"""waiter ordering: menu emojis switch

Revision ID: 021j_wo_menu_emojis
Revises: 021i_wo_kitchen_roster
Create Date: 2026-09-23

Turns ON menu_emojis for ASADERO EL SOCIO only (the company that asked for
it, and today the only one with the waiter_ordering module): the mesero
panel shows a representative emoji per category and product (pollo, carne,
hamburguesa, bebida...) instead of the same generic plate icon; a photo
uploaded in Admin V2 still replaces the emoji.

Absent (= off) for every other company. Settings JSON only. Downgrade
removes exactly this key.
"""
from __future__ import annotations

from alembic import op

revision = "021j_wo_menu_emojis"
down_revision = "021i_wo_kitchen_roster"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"

SETTINGS_PATCH = '{"menu_emojis": true}'


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
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - 'menu_emojis',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
