"""caja: rediseno, Z del dia y tema de la empresa en los mini paneles (049V)

Revision ID: 022j_cashier_redesign
Revises: 022i_purchase_invoices
Create Date: 2026-09-29

- cashier_z_reports: cada Z (cierre de caja del dia) que saca un cajero, con
  numero consecutivo por empresa, fecha y hora, cajero y el resumen calculado
  en el servidor (JSON de pocos KB: totales, metodos de pago y productos). Un
  Z por dia son ~1-2 MB al ano: no es un dato pesado.
- Enciende para ASADERO EL SOCIO (la empresa que lo pidio) los interruptores
  del modulo waiter_ordering:
    cashier_redesign  -> panel de caja rediseñado (indicadores, secciones, Z)
    mini_panel_brand  -> caja, mesero y cocina con el tema de Admin V2
  Ausentes (= apagados) para las demas empresas.
"""
from __future__ import annotations

from alembic import op

revision = "022j_cashier_redesign"
down_revision = "022i_purchase_invoices"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
SETTINGS_PATCH = '{"cashier_redesign": true, "mini_panel_brand": true}'


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cashier_z_reports (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            number integer NOT NULL,
            business_day date NOT NULL,
            cashier_user_id uuid NULL,
            cashier_name varchar(200) NOT NULL DEFAULT '',
            total numeric(14, 2) NOT NULL DEFAULT 0,
            summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_cashier_z_reports_number UNIQUE (company_id, number)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cashier_z_reports_day ON cashier_z_reports (company_id, business_day, number DESC)"
    )
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
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - 'cashier_redesign' - 'mini_panel_brand',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
    op.execute("DROP TABLE IF EXISTS cashier_z_reports")
