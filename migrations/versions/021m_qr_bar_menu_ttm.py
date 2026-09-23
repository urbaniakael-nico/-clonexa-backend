"""qr bar menu: the time machine

Revision ID: 021m_qr_bar_menu_ttm
Revises: 021l_sale_document_settings
Create Date: 2026-09-23

Turns ON qr_bar_menu for THE TIME MACHINE only (the company that asked for
it): the customer QR table screen shows the "carta de bar" redesign (clean
"Mesa X" + logo header, compact account/song lines, category grid with
icons, CONFIRMA TU PEDIDO and the "¡Pedido enviado a la barra!" notice).

Absent (= off) for every other company, so Asadero El Socio and Velvet keep
today's screen. Settings JSON only, on the company's QR module row(s).
Downgrade removes exactly this key.
"""
from __future__ import annotations

from alembic import op

revision = "021m_qr_bar_menu_ttm"
down_revision = "021l_sale_document_settings"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"

SETTINGS_PATCH = '{"qr_bar_menu": true}'

QR_MODULE_CODES = "('qr', 'mesa_qr', 'mesas_qr', 'qr_mesas', 'hospitality_qr', 'voting_qr')"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE company_modules cm
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) || '{SETTINGS_PATCH}'::jsonb,
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code IN {QR_MODULE_CODES}
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE company_modules cm
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - 'qr_bar_menu',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code IN {QR_MODULE_CODES}
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
