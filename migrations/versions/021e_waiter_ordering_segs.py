"""waiter ordering mini panel segments

Revision ID: 021e_waiter_ordering_segs
Revises: 021d_waiter_ordering_p2
Create Date: 2026-09-24

Turns the mesero/cocina/caja mini panel segments ON for ASADERO EL SOCIO
(today the only company with the waiter_ordering module) with the exact
per-segment maximum the user asked for: Meseros 5, Cocina 2, Caja 1. Adds
the new "segments" key that settings JSON never had before (defaults to
disabled everywhere else -- this is the only company touched).

kitchen_user_limit/cashier_user_limit already equal 2/1 since 021c, so this
only actually changes waiter_user_limit (was never set, fell back to the
code default of 10) and stations/timer_thresholds/shift_max_hours from
Fase 2 are left completely untouched by the jsonb merge below.

Downgrade removes exactly what this migration added (segments,
waiter_user_limit), letting waiter_user_limit fall back to its prior
code-default behaviour.
"""
from __future__ import annotations

from alembic import op

revision = "021e_waiter_ordering_segs"
down_revision = "021d_waiter_ordering_p2"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"

SEGMENTS_PATCH = (
    '{"segments": {'
    '"mesero": {"enabled": true, "modules": []}, '
    '"cocina": {"enabled": true, "modules": []}, '
    '"caja": {"enabled": true, "modules": []}'
    '}, "waiter_user_limit": 5}'
)


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE company_modules cm
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) || '{SEGMENTS_PATCH}'::jsonb,
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
        SET settings = (COALESCE(cm.settings, '{{}}'::jsonb) - 'segments') - 'waiter_user_limit',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
