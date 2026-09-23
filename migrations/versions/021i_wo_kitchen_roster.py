"""waiter ordering: kitchen roster switch

Revision ID: 021i_wo_kitchen_roster
Revises: 021h_wo_cashier_direct
Create Date: 2026-09-23

Turns ON kitchen_roster for ASADERO EL SOCIO only (the company that asked
for it, and today the only one with the waiter_ordering module): the
kitchen panel gets "Registro entrada" (Iniciar / Pausar / Salir turno per
person assigned to cocina, each feeding Workforce attendance and payroll on
its own) and a cocina login starts that cook's shift.

Absent (= off) for every other company. Settings JSON only. The two small
column changes the roster needs on mini_panel_work_sessions (user_id
nullable, action_log jsonb) are applied at runtime by the roster itself,
like the rest of that runtime-owned table. Downgrade removes this key.
"""
from __future__ import annotations

from alembic import op

revision = "021i_wo_kitchen_roster"
down_revision = "021h_wo_cashier_direct"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"

SETTINGS_PATCH = '{"kitchen_roster": true}'


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
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - 'kitchen_roster',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
