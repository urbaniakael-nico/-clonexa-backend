"""carta: inventario de insumos, carta de platos y recetas (049H)

Revision ID: 021w_carta_module
Revises: 021v_owner_report_idx
Create Date: 2026-09-27

- inventory_items: tipo (venta_directa / ingrediente / consumible), unidad de
  compra, unidad de consumo, conversion y costo promedio. Los valores por
  defecto (venta directa, unidad -> unidad, factor 1) no cambian nada para
  ninguna empresa; solo se usan con el modulo "carta".
- carta_items / carta_recipe_lines: platos (directo o preparado) y recetas.
- Modulo "carta" en el catalogo de Admin V2, activado SOLO para ASADERO EL
  SOCIO. The Time Machine y las demas empresas no tienen fila: su carta QR,
  precios y descuento de inventario siguen exactamente igual.
- ASADERO: cada producto actual pasa a ser un plato DIRECTO con el MISMO id de
  su insumo (precio, nombre y porciones copiados). Pedidos historicos,
  grupos de porciones, fotos y reportes que apuntan a ese id siguen igual.
  Costo promedio inicial = precio de entrada actual.
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "021w_carta_module"
down_revision = "021v_owner_report_idx"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
MODULE_CODE = "carta"


def upgrade() -> None:
    for column, ddl in [
        ("item_type", "varchar(20) NOT NULL DEFAULT 'venta_directa'"),
        ("purchase_unit", "varchar(20) NOT NULL DEFAULT 'unidad'"),
        ("consumption_unit", "varchar(20) NOT NULL DEFAULT 'unidad'"),
        ("units_per_purchase", "numeric(14,4) NOT NULL DEFAULT 1"),
        ("avg_cost", "numeric(14,4) NOT NULL DEFAULT 0"),
    ]:
        op.execute(f"ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS {column} {ddl}")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS carta_items (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name varchar(220) NOT NULL,
            price numeric(14,2) NOT NULL DEFAULT 0,
            category_key varchar(80) NOT NULL DEFAULT '',
            station varchar(80) NOT NULL DEFAULT '',
            requires_term boolean NOT NULL DEFAULT false,
            allows_portions boolean NOT NULL DEFAULT false,
            kind varchar(20) NOT NULL DEFAULT 'directo',
            inventory_item_id uuid NULL,
            direct_qty numeric(14,4) NOT NULL DEFAULT 1,
            active boolean NOT NULL DEFAULT true,
            position integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_carta_items_company ON carta_items (company_id, position)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS carta_recipe_lines (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            carta_item_id uuid NOT NULL REFERENCES carta_items(id) ON DELETE CASCADE,
            inventory_item_id uuid NOT NULL,
            quantity numeric(14,4) NOT NULL,
            yield_pct numeric(6,2) NOT NULL DEFAULT 100,
            position integer NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_carta_recipe_item ON carta_recipe_lines (company_id, carta_item_id)")

    bind = op.get_bind()
    module = bind.execute(sa.text("SELECT id FROM modules WHERE code = :code LIMIT 1"), {"code": MODULE_CODE}).mappings().first()
    module_id = module["id"] if module else str(uuid.uuid4())
    if not module:
        bind.execute(sa.text("""
            INSERT INTO modules (id, code, name, description, category, is_active, created_at, updated_at)
            VALUES (CAST(:id AS uuid), :code, 'Carta', :description, 'hospitality', TRUE, NOW(), NOW())
        """), {"id": module_id, "code": MODULE_CODE,
               "description": "Carta de platos separada del inventario, con recetas, costo y margen por plato."})
    company = bind.execute(sa.text("SELECT id FROM companies WHERE id = CAST(:id AS uuid)"), {"id": TARGET_COMPANY_ID}).first()
    if not company:
        return  # base de desarrollo sin el Asadero
    if not bind.execute(sa.text("SELECT id FROM company_modules WHERE company_id = CAST(:c AS uuid) AND module_id = :m"),
                        {"c": TARGET_COMPANY_ID, "m": module_id}).first():
        bind.execute(sa.text("""
            INSERT INTO company_modules (id, company_id, module_id, enabled, settings, activated_at, created_at, updated_at)
            VALUES (CAST(:id AS uuid), CAST(:c AS uuid), :m, TRUE, CAST(:s AS jsonb), NOW(), NOW(), NOW())
        """), {"id": str(uuid.uuid4()), "c": TARGET_COMPANY_ID, "m": module_id, "s": json.dumps({})})

    # Productos actuales -> platos directos con el mismo id. Mismo precio que
    # hoy lee la carta (sale_price), mismas porciones.
    columns = {r[0] for r in bind.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'inventory_items'")).fetchall()}
    portions = "COALESCE(allows_portions, false)" if "allows_portions" in columns else "false"
    bind.execute(sa.text(f"""
        INSERT INTO carta_items (id, company_id, name, price, kind, inventory_item_id, direct_qty, allows_portions, active, position)
        SELECT id, company_id,
               COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), NULLIF(reference, ''), NULLIF(sku, ''), id::text),
               COALESCE(sale_price, 0), 'directo', id, 1, {portions}, TRUE,
               ROW_NUMBER() OVER (ORDER BY lower(COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), NULLIF(reference, ''), sku, id::text)))
        FROM inventory_items
        WHERE company_id = CAST(:c AS uuid) AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
        ON CONFLICT (id) DO NOTHING
    """), {"c": TARGET_COMPANY_ID})
    bind.execute(sa.text("""
        UPDATE inventory_items SET avg_cost = entry_price
        WHERE company_id = CAST(:c AS uuid) AND avg_cost = 0 AND entry_price > 0
    """), {"c": TARGET_COMPANY_ID})


def downgrade() -> None:
    bind = op.get_bind()
    module = bind.execute(sa.text("SELECT id FROM modules WHERE code = :code LIMIT 1"), {"code": MODULE_CODE}).mappings().first()
    if module:
        bind.execute(sa.text("DELETE FROM company_modules WHERE module_id = :m"), {"m": module["id"]})
        bind.execute(sa.text("DELETE FROM modules WHERE id = :m"), {"m": module["id"]})
    op.execute("DROP TABLE IF EXISTS carta_recipe_lines")
    op.execute("DROP TABLE IF EXISTS carta_items")
    for column in ("avg_cost", "units_per_purchase", "consumption_unit", "purchase_unit", "item_type"):
        op.execute(f"ALTER TABLE inventory_items DROP COLUMN IF EXISTS {column}")
