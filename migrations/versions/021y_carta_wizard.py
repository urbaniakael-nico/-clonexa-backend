"""carta: presentacion del plato y combos (049J)

Revision ID: 021y_carta_wizard
Revises: 021x_costos_module
Create Date: 2026-09-27

- carta_items.presentation: cantidad o presentacion visible (275 gr, 500 ml).
- carta_recipe_lines.component_item_id: linea de un COMBO que apunta a otro
  plato de la carta (el combo descuenta sus partes, sin existencia propia);
  por eso inventory_item_id deja de ser obligatorio.
Solo columnas nuevas o mas flexibles en tablas del modulo Carta, que hoy
solo tiene ASADERO EL SOCIO.
"""
from __future__ import annotations

from alembic import op

revision = "021y_carta_wizard"
down_revision = "021x_costos_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE carta_items ADD COLUMN IF NOT EXISTS presentation varchar(60) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE carta_recipe_lines ALTER COLUMN inventory_item_id DROP NOT NULL")
    op.execute("ALTER TABLE carta_recipe_lines ADD COLUMN IF NOT EXISTS component_item_id uuid NULL")


def downgrade() -> None:
    op.execute("DELETE FROM carta_recipe_lines WHERE inventory_item_id IS NULL")
    op.execute("ALTER TABLE carta_recipe_lines DROP COLUMN IF EXISTS component_item_id")
    op.execute("ALTER TABLE carta_recipe_lines ALTER COLUMN inventory_item_id SET NOT NULL")
    op.execute("ALTER TABLE carta_items DROP COLUMN IF EXISTS presentation")
