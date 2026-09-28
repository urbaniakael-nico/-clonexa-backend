"""inventario: tamaño como numero + unidad (049M) - TODAS las empresas

Revision ID: 022b_inventory_size
Revises: 022a_payroll_cutoffs
Create Date: 2026-09-28

- inventory_items.size_value / size_unit: el numero y la unidad del tamaño
  (gr, lb, kg, ml, litros, unidad, paquete, caja, docena).
- inventory_items.size_review: el texto que habia no se pudo interpretar
  ("M", "20m", "500" sin unidad...): se deja TAL CUAL y queda marcado para
  que alguien lo revise. Ningun dato se pierde.
- Lo que si se interpreta se normaliza en item_size ("275gr" -> "275 gr",
  "1.5lt" -> "1.5 litros", "280 grm" -> "280 gr"); el texto original queda
  en size_original.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "022b_inventory_size"
down_revision = "022a_payroll_cutoffs"
branch_labels = None
depends_on = None


def _engine():
    # la misma regla que usa la app (sin importar la app entera)
    path = Path(__file__).resolve().parents[2] / "app" / "services" / "inventory_size.py"
    spec = importlib.util.spec_from_file_location("cx_inventory_size_022b", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> None:
    op.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS size_value numeric(14, 4) NULL")
    op.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS size_unit varchar(20) NULL")
    op.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS size_review boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS size_original varchar(120) NULL")
    engine = _engine()
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT id, company_id, item_size FROM inventory_items
        WHERE COALESCE(btrim(item_size), '') <> '' AND size_unit IS NULL
    """)).mappings().all()
    for row in rows:
        result = engine.normalize_existing(row["item_size"])
        if result["review"]:
            bind.execute(sa.text("""
                UPDATE inventory_items SET size_review = true
                WHERE id = :id AND company_id = :company_id
            """), {"id": row["id"], "company_id": row["company_id"]})
        else:
            bind.execute(sa.text("""
                UPDATE inventory_items SET item_size = :text, size_value = :value, size_unit = :unit, size_review = false,
                       size_original = COALESCE(size_original, item_size)
                WHERE id = :id AND company_id = :company_id
            """), {"id": row["id"], "company_id": row["company_id"], "text": result["text"],
                   "value": result["value"], "unit": result["unit"]})


def downgrade() -> None:
    # vuelve el texto original de cada articulo convertido: nada se pierde.
    op.execute("UPDATE inventory_items SET item_size = size_original WHERE size_original IS NOT NULL")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS size_original")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS size_review")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS size_unit")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS size_value")
