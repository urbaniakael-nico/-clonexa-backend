"""waiter ordering role fix (production data repair)

Revision ID: 021f_wo_role_fix
Revises: 021e_waiter_ordering_segs
Create Date: 2026-09-25

_cx_create_minipanel_user_from_employee_026j used to hardcode role="operator"
for every mini panel type it created, including mesero/cocina/caja -- but
those three panels' own auth (_require_mesero/_require_cocina/_require_caja
in waiter_ordering.py) require the literal role "mesero"/"cocina"/"caja".
Any mesero/cocina/caja mini panel user created before the code fix got 403
"role_not_allowed" on every single waiter-ordering request despite a valid
session. This repairs any already-created account for ASADERO EL SOCIO
whose role doesn't match its own mini_panel.type. Scoped to that one company
(the only one with waiter_ordering) and only to rows whose mini_panel.type
is exactly mesero/cocina/caja -- never touches sales/store/other accounts,
and never touches any other company's data.

Downgrade cannot recover the original (broken) "operator" value in a
meaningful way -- there is nothing to roll back to that isn't the bug
itself, so downgrade is a no-op.
"""
from __future__ import annotations

from alembic import op

revision = "021f_wo_role_fix"
down_revision = "021e_waiter_ordering_segs"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE company_users
        SET role = settings_json->'mini_panel'->>'type',
            updated_at = NOW()
        WHERE company_id = '{TARGET_COMPANY_ID}'::uuid
          AND settings_json->'mini_panel'->>'type' IN ('mesero', 'cocina', 'caja')
          AND role <> settings_json->'mini_panel'->>'type'
        """
    )


def downgrade() -> None:
    # No-op: there is no non-buggy prior state to restore.
    pass
