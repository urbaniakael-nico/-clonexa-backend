"""inventario: CARNE Asada y CARNE Churrasco con su compra real (049S)

Revision ID: 022h_fix_carnes_asadero
Revises: 022g_avg_cost_precision
Create Date: 2026-09-29

Solo ASADERO EL SOCIO. Las dos carnes se habian cargado en gramos como "20"
(eran kilos) y la migracion 022f las leyo como 20 g por $1.120.000 y
$1.200.000: $56.000 y $60.000 el gramo. Con los datos reales que dio el
dueño cada una queda como una cuenta nueva con dos saldos:

    12 kg por $192.000 -> 12.000 g y $192.000 ($16 el gramo; 275 g = $4.400)

Se borra lo que quedo mal cargado de esos dos insumos (sus compras en
carta_purchases y sus equivalencias) para que no arrastren el saldo viejo,
se registra la compra real y un movimiento de ajuste con el antes y el
despues. Solo se toca un insumo si su nombre aparece exactamente una vez.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "022h_fix_carnes_asadero"
down_revision = "022g_avg_cost_precision"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
# nombre -> compra real: (cantidad, unidad, total pagado)
REAL_PURCHASES = {
    "CARNE ASADA": (Decimal("12"), "kg", Decimal("192000")),
    "CARNE CHURRASCO": (Decimal("12"), "kg", Decimal("192000")),
}
GRAMS_PER_KG = Decimal("1000")


def corrected(quantity: Decimal, total: Decimal) -> dict:
    """Los dos saldos de una carne comprada por kilo: cantidad en gramos y
    dinero; costo por gramo = dinero / cantidad."""
    grams = quantity * GRAMS_PER_KG
    cost = total / grams
    return {"current_stock": grams, "avg_cost": cost, "entry_price": (cost * GRAMS_PER_KG).quantize(Decimal("0.01")),
            "purchase_unit": "kg", "consumption_unit": "g", "units_per_purchase": GRAMS_PER_KG,
            "base_quantity": grams, "unit_cost": cost}


def upgrade() -> None:
    bind = op.get_bind()
    params = {"c": TARGET_COMPANY_ID}
    if not bind.execute(sa.text("SELECT 1 FROM companies WHERE id = CAST(:c AS uuid)"), params).first():
        return  # base sin el Asadero (desarrollo)
    rows = [dict(r._mapping) for r in bind.execute(sa.text("""
        SELECT id, upper(trim(COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), sku, ''))) AS label, current_stock, avg_cost
        FROM inventory_items
        WHERE company_id = CAST(:c AS uuid) AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
    """), params).fetchall()]
    for label, (quantity, unit, total) in REAL_PURCHASES.items():
        matches = [r for r in rows if r["label"] == label]
        if len(matches) != 1:
            print(f"[022h_fix_carnes_asadero] {label}: {len(matches)} insumos con ese nombre; no se toca")
            continue
        item = matches[0]
        key = {"c": TARGET_COMPANY_ID, "i": str(item["id"])}
        new = corrected(quantity, total)
        # lo mal cargado de este insumo no debe arrastrar el saldo nuevo
        deleted = bind.execute(sa.text(
            "DELETE FROM carta_purchases WHERE company_id = CAST(:c AS uuid) AND inventory_item_id = CAST(:i AS uuid)"), key).rowcount
        bind.execute(sa.text(
            "DELETE FROM carta_unit_equivalences WHERE company_id = CAST(:c AS uuid) AND inventory_item_id = CAST(:i AS uuid)"), key)
        bind.execute(sa.text("""
            UPDATE inventory_items
               SET purchase_unit = :pu, consumption_unit = :cu, units_per_purchase = :f, current_stock = :stock,
                   avg_cost = :avg, entry_price = :entry, updated_at = now()
             WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
        """), {**key, "pu": new["purchase_unit"], "cu": new["consumption_unit"], "f": new["units_per_purchase"],
               "stock": new["current_stock"], "avg": new["avg_cost"], "entry": new["entry_price"]})
        bind.execute(sa.text("""
            INSERT INTO carta_purchases (id, company_id, inventory_item_id, quantity, unit, total_paid, base_quantity, unit_cost, source, created_by)
            VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:i AS uuid), :quantity, :unit, :total, :base, :cost, 'correccion', 'correccion 022h')
        """), {**key, "id": str(uuid.uuid4()), "quantity": quantity, "unit": unit, "total": total,
               "base": new["base_quantity"], "cost": new["unit_cost"]})
        before = Decimal(str(item["current_stock"] or 0))
        bind.execute(sa.text("""
            INSERT INTO inventory_movements (id, company_id, item_id, movement_type, quantity_delta, quantity, stock_before, stock_after,
                                             source_module, notes, created_at, updated_at)
            VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:i AS uuid), 'manual_adjustment', :delta, :delta, :before, :after,
                    'carta_compra', :notes, now(), now())
        """), {**key, "id": str(uuid.uuid4()), "delta": new["current_stock"] - before, "before": before, "after": new["current_stock"],
               "notes": "Corrección: 12 kg por $192.000 reemplaza el saldo mal cargado"})
        directos = [r[0] for r in bind.execute(sa.text("""
            SELECT name FROM carta_items WHERE company_id = CAST(:c AS uuid) AND kind = 'directo' AND inventory_item_id = CAST(:i AS uuid)
        """), key).fetchall()]
        print(f"[022h_fix_carnes_asadero] {label}: {before} -> {new['current_stock']} g, costo {item['avg_cost']} -> {new['avg_cost']} por g; "
              f"compras borradas: {deleted}" + (f"; platos directos que lo descuentan: {', '.join(directos)}" if directos else ""))


def downgrade() -> None:
    pass  # correccion de datos: no se deshace
