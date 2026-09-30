"""reportes con la venta unificada, tema en todos los enlaces y domicilios con transferencia (049Z)

Revision ID: 022n_asadero_sales_brand
Revises: 022m_short_links
Create Date: 2026-09-30

Enciende SOLO para ASADERO EL SOCIO (la empresa que lo pidio):
- waiter_ordering.sales_ledger: el reporte del dueño cuenta cada venta en el dia en que se
  cobro, leyendo los mismos pedidos que el panel de caja y el Z (antes, sin
  horario de jornada, fechaba las ventas sin "cierre de dia" con el pedido mas
  antiguo y hoy/ayer salian vacios).
- waiter_ordering.brand_everywhere: el tema de Admin V2 en el link de
  domicilios, el QR de la carta, el QR de mesa, los mini paneles y sus
  pantallas de ingreso.
- domicilios_whatsapp.checkout_v2: pago por transferencia con el QR del local
  (por verificar hasta que la caja confirme) y la ubicacion se pide por
  WhatsApp despues de confirmar, sin botones en el formulario.
Ausente (= apagado) para las demas. Solo settings JSON; downgrade quita
exactamente estas llaves.
"""
from __future__ import annotations

from alembic import op

revision = "022n_asadero_sales_brand"
down_revision = "022m_short_links"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
PATCHES = {
    "waiter_ordering": '{"sales_ledger": true, "brand_everywhere": true}',
    "domicilios_whatsapp": '{"checkout_v2": true}',
}
KEYS = {
    "waiter_ordering": ("sales_ledger", "brand_everywhere"),
    "domicilios_whatsapp": ("checkout_v2",),
}


def upgrade() -> None:
    for code, patch in PATCHES.items():
        op.execute(
            f"""
            UPDATE company_modules cm
            SET settings = COALESCE(cm.settings, '{{}}'::jsonb) || '{patch}'::jsonb,
                updated_at = NOW()
            FROM modules m
            WHERE cm.module_id = m.id
              AND m.code = '{code}'
              AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
            """
        )


def downgrade() -> None:
    for code, keys in KEYS.items():
        removal = " - ".join(f"'{key}'" for key in keys)
        op.execute(
            f"""
            UPDATE company_modules cm
            SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - {removal},
                updated_at = NOW()
            FROM modules m
            WHERE cm.module_id = m.id
              AND m.code = '{code}'
              AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
            """
        )
