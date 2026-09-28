"""carta: equivalencias de unidades por insumo y lineas de receta mal puestas (049O)

Revision ID: 022e_unit_equivalences
Revises: 022d_recipe_units
Create Date: 2026-09-28

- carta_unit_equivalences: "1 <unidad> = N <unidad del inventario>" por
  insumo (cuanto pesa una unidad de carne, cuantos gramos tiene una
  cucharada de sal). Se pide una sola vez en la receta y se reutiliza.
- Lineas de receta que hoy dan cifras absurdas: insumos que el inventario
  cuenta por "unidad" y una receta con 20 o mas "unidades" (275 de carne,
  250 de papa): era gramos, no unidades. Pasan a gramos; hasta que se diga
  cuanto pesa una unidad de ese insumo la linea queda "falta equivalencia"
  (no descuenta ni da costo) en vez de costar millones. Solo hay recetas en
  el modulo Carta (hoy solo ASADERO).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "022e_unit_equivalences"
down_revision = "022d_recipe_units"
branch_labels = None
depends_on = None

SUSPECT_UNITS = 20


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS carta_unit_equivalences (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            inventory_item_id uuid NOT NULL,
            unit varchar(12) NOT NULL,
            amount numeric(18, 8) NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, inventory_item_id, unit)
        )
        """
    )
    bind = op.get_bind()
    result = bind.execute(sa.text("""
        UPDATE carta_recipe_lines l SET unit = 'g'
          FROM inventory_items i
         WHERE i.id = l.inventory_item_id AND i.company_id = l.company_id
           AND COALESCE(i.consumption_unit, 'unidad') = 'unidad' AND l.unit = 'unidad' AND l.quantity >= :n
    """), {"n": SUSPECT_UNITS})
    print(f"[022e_unit_equivalences] lineas de receta pasadas de 'unidad' a gramos: {result.rowcount or 0}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS carta_unit_equivalences")
