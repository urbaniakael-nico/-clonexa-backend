"""inventario: factura de cada compra (049T)

Revision ID: 022i_purchase_invoices
Revises: 022h_fix_carnes_asadero
Create Date: 2026-09-29

- carta_purchase_invoices: la foto de la factura de una compra de Inventario
  (empresas con Carta). Se guarda con media_storage: redimensionada en el
  servidor y con tope de 200 KB; una por compra (una nueva reemplaza la
  anterior). Si la compra se borra, su factura tambien.
- Crecimiento esperado: ~100-200 KB por compra con factura. La base tiene
  500 MB (237,9 MB usados el 2026-09-29): el paso siguiente es un bucket.
"""
from __future__ import annotations

from alembic import op

revision = "022i_purchase_invoices"
down_revision = "022h_fix_carnes_asadero"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS carta_purchase_invoices (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            purchase_id uuid NOT NULL REFERENCES carta_purchases(id) ON DELETE CASCADE,
            original_name varchar(200) NULL,
            image_bytes bytea NULL,
            image_content_type varchar(40) NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, purchase_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS carta_purchase_invoices")
