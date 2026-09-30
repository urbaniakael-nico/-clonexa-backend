"""pedidos: selector de cantidad libre (entero + fraccion) (049W)

Revision ID: 022k_quantity_picker
Revises: 022j_cashier_redesign
Create Date: 2026-09-29

Enciende para ASADERO EL SOCIO (la empresa que lo pidio) el interruptor
quantity_picker del modulo waiter_ordering: en el mesero, la caja, el link de
domicilios y el QR de mesa la cantidad se elige con un entero (+ / -) mas una
fraccion opcional (1/8, 1/4, 1/2, 3/4) en los productos que se venden por
porciones. Ausente (= apagado) para las demas. Solo settings JSON.
"""
from __future__ import annotations

from alembic import op

revision = "022k_quantity_picker"
down_revision = "022j_cashier_redesign"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
SETTINGS_PATCH = '{"quantity_picker": true}'


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
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - 'quantity_picker',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
