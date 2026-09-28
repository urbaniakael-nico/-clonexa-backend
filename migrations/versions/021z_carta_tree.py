"""carta: categorias y subcategorias con imagen; reorganiza la carta del Asadero (049K)

Revision ID: 021z_carta_tree
Revises: 021y_carta_wizard
Create Date: 2026-09-28

- carta_categories: arbol de dos niveles (categoria -> subcategoria opcional)
  con estacion de cocina, notas rapidas y termino. Las imagenes van en el
  mismo almacen de fotos del menu (hospitality_product_images, por el id de
  la categoria): 8 o 10 en toda la carta, no una por plato.
- carta_items.category_id: la categoria o subcategoria del plato.
- SOLO ASADERO EL SOCIO (la unica empresa con el modulo Carta):
  * Siembra BEBIDAS, PLATOS A LA CARTA, POLLO, COMIDAS RAPIDAS y PORCIONES
    con la estacion / notas rapidas / termino que ya tenian sus categorias
    de inventario (pollo, carne, gaseosa...), para que la cocina siga
    recibiendo cada comanda en su estacion.
  * Reasigna los platos que quedaron sin categoria y elimina los dos combos.
The Time Machine y las demas empresas no tienen filas en estas tablas.
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "021z_carta_tree"
down_revision = "021y_carta_wizard"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"

# categoria -> llaves de las categorias de inventario de donde hereda estacion
PRESETS = [
    ("BEBIDAS", ["bebidas", "bebida", "gaseosa", "gaseosas", "jugo", "jugos", "cerveza"]),
    ("PLATOS A LA CARTA", ["carne", "carnes", "churrasco", "platos"]),
    ("POLLO", ["pollo", "pollos"]),
    ("COMIDAS RÁPIDAS", ["hamburguesa", "hamburguesas", "perro", "salchipapa", "comidas"]),
    ("PORCIONES", ["papa", "papas", "porcion", "porciones", "platano"]),
]

# nombre normalizado del plato (sin tildes, espacios ni signos) -> categoria
REASSIGN = {
    "carneasada": "PLATOS A LA CARTA",
    "carnechurrasco": "PLATOS A LA CARTA",
    "gaseosacocacola": "BEBIDAS",
    "gaseosamanzana": "BEBIDAS",
    "gaseosacolombiana": "BEBIDAS",
    "jugonaturalaguamaracuya": "BEBIDAS",
    "polloasado": "POLLO",
    "pollobroaster": "POLLO",
    "pollofrito": "POLLO",
    "papafrancesa": "PORCIONES",
    "papasalada": "PORCIONES",
    "hamburguesaranchera": "COMIDAS RÁPIDAS",
}

# lower + sin tildes + solo letras y numeros, en SQL
NORM_NAME = "regexp_replace(translate(lower(name), 'áéíóúüñ', 'aeiouun'), '[^a-z0-9]', '', 'g')"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS carta_categories (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            parent_id uuid NULL REFERENCES carta_categories(id) ON DELETE CASCADE,
            label varchar(80) NOT NULL,
            position integer NOT NULL DEFAULT 0,
            station varchar(80) NOT NULL DEFAULT '',
            quick_notes jsonb NOT NULL DEFAULT '[]'::jsonb,
            requires_term boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_carta_categories_company ON carta_categories (company_id, parent_id, position)")
    op.execute("ALTER TABLE carta_items ADD COLUMN IF NOT EXISTS category_id uuid NULL REFERENCES carta_categories(id) ON DELETE SET NULL")

    bind = op.get_bind()
    c = {"c": TARGET_COMPANY_ID}
    if not bind.execute(sa.text("SELECT 1 FROM companies WHERE id = CAST(:c AS uuid)"), c).first():
        return
    has_hsp_categories = bind.execute(sa.text("SELECT to_regclass('public.hospitality_categories') IS NOT NULL")).scalar()

    ids: dict[str, str] = {}
    for position, (label, keys) in enumerate(PRESETS, start=1):
        existing = bind.execute(sa.text(
            "SELECT id FROM carta_categories WHERE company_id = CAST(:c AS uuid) AND parent_id IS NULL AND upper(label) = :label"
        ), {**c, "label": label}).scalar()
        if existing:
            ids[label] = str(existing)
            continue
        inherited = None
        for key in keys if has_hsp_categories else []:
            row = bind.execute(sa.text("""
                SELECT COALESCE(station, '') AS station, COALESCE(quick_notes, '[]'::jsonb)::text AS quick_notes,
                       COALESCE(requires_term, false) AS requires_term
                FROM hospitality_categories
                WHERE company_id = CAST(:c AS uuid) AND category_key = :key
                LIMIT 1
            """), {**c, "key": key}).mappings().first()
            if row and (not inherited or (row["station"] and not inherited["station"])):
                inherited = dict(row)
            if inherited and inherited["station"]:
                break
        new_id = str(uuid.uuid4())
        bind.execute(sa.text("""
            INSERT INTO carta_categories (id, company_id, parent_id, label, position, station, quick_notes, requires_term)
            VALUES (CAST(:id AS uuid), CAST(:c AS uuid), NULL, :label, :position, :station, CAST(:notes AS jsonb), :term)
        """), {**c, "id": new_id, "label": label, "position": position,
               "station": (inherited or {}).get("station") or "", "notes": (inherited or {}).get("quick_notes") or "[]",
               "term": bool((inherited or {}).get("requires_term"))})
        ids[label] = new_id

    # Categorias propias que ya se habian creado en Carta (texto en el plato).
    position = len(PRESETS)
    for (label,) in bind.execute(sa.text("""
        SELECT DISTINCT upper(category_key) FROM carta_items
        WHERE company_id = CAST(:c AS uuid) AND COALESCE(category_key, '') <> ''
    """), c).all():
        if label in ids:
            continue
        existing = bind.execute(sa.text(
            "SELECT id FROM carta_categories WHERE company_id = CAST(:c AS uuid) AND parent_id IS NULL AND upper(label) = :label"
        ), {**c, "label": label}).scalar()
        if not existing:
            position += 1
            existing = str(uuid.uuid4())
            bind.execute(sa.text("""
                INSERT INTO carta_categories (id, company_id, parent_id, label, position)
                VALUES (CAST(:id AS uuid), CAST(:c AS uuid), NULL, :label, :position)
            """), {**c, "id": existing, "label": label, "position": position})
        ids[label] = str(existing)
    for label, category_id in ids.items():
        bind.execute(sa.text("""
            UPDATE carta_items SET category_id = CAST(:id AS uuid), category_key = :label
            WHERE company_id = CAST(:c AS uuid) AND category_id IS NULL AND upper(category_key) = :label
        """), {**c, "id": category_id, "label": label})

    # Los platos de la lista del dueño (quedaron en "Sin categoria").
    for key, label in REASSIGN.items():
        bind.execute(sa.text(f"""
            UPDATE carta_items SET category_id = CAST(:id AS uuid), category_key = :label, updated_at = now()
            WHERE company_id = CAST(:c AS uuid) AND ({NORM_NAME} = :key OR {NORM_NAME} LIKE :prefix)
        """), {**c, "id": ids[label], "label": label, "key": key, "prefix": f"{key}%"})

    # Los dos combos se eliminan (sus recetas se van en cascada). Si el combo
    # venia del inventario (mismo id), ese articulo se archiva: no es insumo.
    combos = [str(r[0]) for r in bind.execute(sa.text(f"""
        SELECT id FROM carta_items WHERE company_id = CAST(:c AS uuid) AND {NORM_NAME} LIKE 'combo%'
    """), c).all()]
    for combo_id in combos:
        bind.execute(sa.text("""
            DELETE FROM carta_recipe_lines WHERE company_id = CAST(:c AS uuid) AND component_item_id = CAST(:id AS uuid)
        """), {**c, "id": combo_id})
        bind.execute(sa.text("DELETE FROM carta_items WHERE company_id = CAST(:c AS uuid) AND id = CAST(:id AS uuid)"),
                     {**c, "id": combo_id})
        bind.execute(sa.text("""
            UPDATE inventory_items SET status = 'archived', updated_at = now()
            WHERE company_id = CAST(:c AS uuid) AND id = CAST(:id AS uuid)
        """), {**c, "id": combo_id})


def downgrade() -> None:
    op.execute("ALTER TABLE carta_items DROP COLUMN IF EXISTS category_id")
    op.execute("DROP TABLE IF EXISTS carta_categories")
