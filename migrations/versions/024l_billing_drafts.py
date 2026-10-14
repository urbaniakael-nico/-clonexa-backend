"""facturacion: datos del proveedor, contratos redactados y recordatorio de pago

Revision ID: 024l_billing_drafts
Revises: 024k_loyalty_games_v2
Create Date: 2026-10-14

Aditiva (no toca filas existentes; el contrato de The Time Machine queda igual):
- billing_provider: UNA fila con los datos de Clonexa como proveedor (los
  contratos nuevos los toman de aqui; se editan en Facturacion). El QR de pago
  vive en el bucket (zona privada); aqui solo su llave.
- billing_contract_documents: contratos redactados desde la consola (numero
  CX-AAAA-NNN, version y codigo de verificacion; los datos del formulario para
  volver a generarlo). Editar crea la version siguiente; la anterior queda en
  el historial. El PDF es un billing_contract_files (bucket).
- billing_contracts.reminder_enabled: "Recordatorio en el panel" por contrato
  (encendido por defecto).
- billing_payments.source / proof_key / proof_type: el pago que reporta el
  cliente desde su panel ("Ya pagué") con su comprobante en el bucket.
"""
from __future__ import annotations

from alembic import op

revision = "024l_billing_drafts"
down_revision = "024k_loyalty_games_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_provider (
            id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            name varchar(160) NOT NULL DEFAULT '',
            trade_name varchar(80) NOT NULL DEFAULT '',
            doc_id varchar(60) NOT NULL DEFAULT '',
            email varchar(160) NOT NULL DEFAULT '',
            phones varchar(300) NOT NULL DEFAULT '',
            city varchar(80) NOT NULL DEFAULT '',
            qr_key text NULL,
            qr_type varchar(40) NULL,
            updated_by varchar(200) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO billing_provider (id, name, trade_name, doc_id, email, phones, city)
        VALUES (1, 'Oscar Nicolas Gomez', 'CLONEXA', '1.026.550.749-2', 'clonexasaas@gmail.com',
                'Colombia +57 302 847 3926 · EE. UU. +1 346 824 4098', '')
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_contract_documents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            number varchar(20) NOT NULL,
            version integer NOT NULL CHECK (version >= 1),
            verification varchar(16) NOT NULL,
            data jsonb NOT NULL,
            file_id uuid NULL REFERENCES billing_contract_files(id) ON DELETE SET NULL,
            is_current boolean NOT NULL DEFAULT true,
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (number, version)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_billing_contract_documents_company ON billing_contract_documents (company_id, version DESC)")
    op.execute("ALTER TABLE billing_contracts ADD COLUMN IF NOT EXISTS reminder_enabled boolean NOT NULL DEFAULT true")
    op.execute("ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS source varchar(12) NOT NULL DEFAULT 'consola'")
    op.execute("ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS proof_key text NULL")
    op.execute("ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS proof_type varchar(40) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE billing_payments DROP COLUMN IF EXISTS proof_type")
    op.execute("ALTER TABLE billing_payments DROP COLUMN IF EXISTS proof_key")
    op.execute("ALTER TABLE billing_payments DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE billing_contracts DROP COLUMN IF EXISTS reminder_enabled")
    op.execute("DROP TABLE IF EXISTS billing_contract_documents")
    op.execute("DROP TABLE IF EXISTS billing_provider")
