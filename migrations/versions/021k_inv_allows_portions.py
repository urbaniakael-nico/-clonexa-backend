"""inventory: "Permite porciones" per product (pollo at Asadero El Socio)

Revision ID: 021k_inv_allows_portions
Revises: 021j_wo_menu_emojis
Create Date: 2026-09-23

Adds inventory_items.allows_portions (boolean, default false -> OFF for
every product of every company) and turns it ON only for ASADERO EL SOCIO's
pollo products: those whose name starts with the word "pollo"/"pollos"
(accents and case ignored). Everything else stays whole units, in this
and any other company.

inventory_items is created at runtime by the inventory module, so on a
brand-new database it may not exist yet when alembic runs: then this is a
no-op and ensure_inventory_storage adds the same column later (default off).

Downgrade only turns those products back off; the column stays (dropping
it would lose any value set by hand since).
"""
from __future__ import annotations

from alembic import op

revision = "021k_inv_allows_portions"
down_revision = "021j_wo_menu_emojis"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"

# First word of the name, lowercased, with the accented vowels folded.
FIRST_WORD_SQL = (
    "translate(lower(split_part(btrim(COALESCE(NULLIF(name_reference, ''), name, '')), ' ', 1)),"
    " 'áéíóúü', 'aeiouu')"
)


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF to_regclass('public.inventory_items') IS NOT NULL THEN
            ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS allows_portions boolean NOT NULL DEFAULT false;
            UPDATE inventory_items
            SET allows_portions = TRUE, updated_at = NOW()
            WHERE company_id = '{TARGET_COMPANY_ID}'::uuid
              AND {FIRST_WORD_SQL} IN ('pollo', 'pollos');
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF to_regclass('public.inventory_items') IS NOT NULL THEN
            UPDATE inventory_items
            SET allows_portions = FALSE, updated_at = NOW()
            WHERE company_id = '{TARGET_COMPANY_ID}'::uuid
              AND {FIRST_WORD_SQL} IN ('pollo', 'pollos');
          END IF;
        END $$;
        """
    )
