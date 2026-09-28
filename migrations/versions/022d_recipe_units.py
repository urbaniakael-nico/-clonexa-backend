"""carta: unidad en cada linea de receta (049N)

Revision ID: 022d_recipe_units
Revises: 022c_fixed_expenses
Create Date: 2026-09-28

- carta_recipe_lines.unit: la unidad en que se escribio la linea (g, kg, lb,
  ml, l, unidad, par). Al vender, la cantidad se convierte sola a la unidad
  del inventario del insumo (3 g de un tomate cargado en kilos descuentan
  3 g de esos kilos).
- Las lineas que ya existen quedan con la unidad de su insumo (g, ml o
  unidad): su cantidad ya estaba en esa unidad, asi que nada cambia en lo
  que descuentan ni en su costo. Solo hay recetas en el modulo Carta (hoy
  solo ASADERO).
"""
from __future__ import annotations

from alembic import op

revision = "022d_recipe_units"
down_revision = "022c_fixed_expenses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE carta_recipe_lines ADD COLUMN IF NOT EXISTS unit varchar(12) NULL")
    op.execute(
        """
        UPDATE carta_recipe_lines l
           SET unit = CASE WHEN i.consumption_unit IN ('g', 'ml') THEN i.consumption_unit ELSE 'unidad' END
          FROM inventory_items i
         WHERE l.unit IS NULL AND l.inventory_item_id IS NOT NULL
           AND i.id = l.inventory_item_id AND i.company_id = l.company_id
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE carta_recipe_lines DROP COLUMN IF EXISTS unit")
