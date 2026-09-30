"""caja: imprimir y reimprimir la cuenta de un domicilio (049Y)

Revision ID: 022o_delivery_print
Revises: 022n_asadero_sales_brand
Create Date: 2026-09-30

Enciende para ASADERO EL SOCIO (la empresa que lo pidio) el interruptor
delivery_print del modulo waiter_ordering: el detalle de un domicilio en el
panel de caja tiene "Imprimir cuenta" (el mismo documento de venta, con el
cliente, la direccion, el valor del domicilio aparte y el estado del pago) y
los domicilios cobrados del turno se pueden reimprimir. Ausente (= apagado)
para las demas. Solo settings JSON.
"""
from __future__ import annotations

from alembic import op

revision = "022o_delivery_print"
down_revision = "022n_asadero_sales_brand"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
SETTINGS_PATCH = '{"delivery_print": true}'


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
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - 'delivery_print',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
