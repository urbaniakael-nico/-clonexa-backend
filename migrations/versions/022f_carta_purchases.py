"""carta: compras con cantidad + total pagado y datos cargados reinterpretados (049Q)

Revision ID: 022f_carta_purchases
Revises: 022e_unit_equivalences
Create Date: 2026-09-28

- carta_purchases: cada compra como la escribe el dueño (80 kg por
  $1.120.000) y el costo que calcula el sistema ($14 por gramo).
- Empresas con el modulo Carta (hoy solo ASADERO): lo ya cargado se lee con
  esa misma regla. El "precio de entrada" que se escribio es lo que se PAGO
  por la cantidad registrada, no el precio de una unidad:
    costo por unidad base = precio de entrada / (cantidad comprada x
    unidades base por unidad natural).
  La cantidad comprada es la del primer ingreso del insumo (lo que se
  escribio al crearlo); sin ingreso, su existencia.
- Insumo que se pesa pero estaba como "unidad" (compra por unidad, consumo en
  gramos con "1 unidad = 1 g"; o contado por unidad y usado en gramos en las
  recetas, sin equivalencia): pasa a comprarse por kilo (o litro, o la unidad
  de su tamaño) y su existencia se reexpresa en gramos: 80 -> 80.000 g.
  Los platos directos de ese insumo descuentan lo mismo que antes.
- Salvaguarda: si el precio de entrada es menor o igual que el precio de
  venta del mismo insumo, no puede ser el total de varias unidades (ya era el
  precio de una): se conserva como costo de la unidad.
- Unidades viejas de compra (libra, kilo, gramo, litro) pasan a la lista
  unica (lb, kg, g, l).
- Cada compra reinterpretada queda en carta_purchases con source
  'reinterpretada_022f' y se ve en Inventario para revisarla.
"""
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "022f_carta_purchases"
down_revision = "022e_unit_equivalences"
branch_labels = None
depends_on = None

QTY = Decimal("0.0001")
MONEY = Decimal("0.01")
# copia fija de las unidades de app/services/carta.py (una migracion no importa la app)
UNITS = {
    "g": ("masa", Decimal("1")), "kg": ("masa", Decimal("1000")), "lb": ("masa", Decimal("453.59237")),
    "oz": ("masa", Decimal("28.349523125")), "ml": ("volumen", Decimal("1")), "l": ("volumen", Decimal("1000")),
    "cucharada": ("volumen", Decimal("15")), "unidad": ("unidad", Decimal("1")), "par": ("unidad", Decimal("2")),
    "docena": ("unidad", Decimal("12")), "paquete": ("paquete", Decimal("1")), "pizca": ("pizca", Decimal("1")),
}
LEGACY = {"libra": "lb", "kilo": "kg", "gramo": "g", "litro": "l", "gr": "g", "litros": "l"}
SIZE_UNITS = {"gr": "g", "kg": "kg", "lb": "lb", "onza": "oz", "ml": "ml", "litros": "l"}
DEFAULT_BY_DIM = {"masa": "kg", "volumen": "l"}
BASE_BY_DIM = {"masa": "g", "volumen": "ml"}


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else 0))
    except Exception:
        return Decimal("0")


def _std(a: str, b: str) -> Decimal | None:
    ua, ub = UNITS.get(a), UNITS.get(b)
    if not ua or not ub or ua[0] != ub[0]:
        return None
    return ua[1] / ub[1]


def reinterpret(item: dict, typed_qty: Any = None, recipe_dim: str | None = None) -> dict:
    """Lo que queda de un insumo al leer su precio de entrada como TOTAL pagado.

    item: purchase_unit, consumption_unit, units_per_purchase, current_stock,
    min_stock, entry_price, avg_cost, size_unit, has_equivalences.
    typed_qty: la cantidad que se escribio en su primer ingreso (en la unidad
    en que la piensa el dueño). recipe_dim: "masa"/"volumen" si alguna receta
    lo usa en gramos o mililitros."""
    pu = str(item.get("purchase_unit") or "unidad").lower()
    pu = LEGACY.get(pu, pu)
    cu = str(item.get("consumption_unit") or "unidad")
    factor = _dec(item.get("units_per_purchase") or 1)
    size_key = SIZE_UNITS.get(str(item.get("size_unit") or ""))
    weighs_as_unit = pu == "unidad" and cu in {"g", "ml"} and factor <= 1
    counted_but_weighed = (pu == "unidad" and cu == "unidad" and factor <= 1 and recipe_dim in BASE_BY_DIM
                           and not item.get("has_equivalences"))
    stock_mult = Decimal("1")
    if weighs_as_unit or counted_but_weighed:
        dim = "masa" if (cu == "g" or (cu == "unidad" and recipe_dim == "masa")) else "volumen"
        unit = size_key if size_key and UNITS[size_key][0] == dim else DEFAULT_BY_DIM[dim]
        cu = BASE_BY_DIM[dim]
        factor = _std(unit, cu)
        stock_mult = factor  # la existencia estaba en kilos (o litros) escritos como numero suelto
        reason = "se pesa: pasa a comprarse por " + unit
    else:
        unit = pu if pu in UNITS else "unidad"
        same = _std(unit, cu)
        factor = same if same is not None else (factor if factor > 0 else Decimal("1"))
        reason = "precio de entrada leido como total pagado"
    stock = (_dec(item.get("current_stock")) * stock_mult).quantize(QTY)
    min_stock = (_dec(item.get("min_stock")) * stock_mult).quantize(QTY)
    total = _dec(item.get("entry_price"))
    qty = _dec(typed_qty)
    if qty <= 0 and stock > 0:
        qty = (stock / factor).quantize(QTY)
    out = {"purchase_unit": unit, "consumption_unit": cu, "units_per_purchase": factor, "current_stock": stock,
           "min_stock": min_stock, "stock_mult": stock_mult, "reason": reason, "purchase": None}
    sale = _dec(item.get("sale_price"))
    if total > 0 and qty > 1 and 0 < total <= sale:
        # pagar por TODA la compra menos de lo que vale UNA unidad vendida no
        # es un total: ese precio ya era el de una unidad (una gaseosa a $2.500
        # que se vende a $4.000). Se conserva como costo de la unidad natural.
        out.update(avg_cost=(total / factor).quantize(QTY, rounding=ROUND_HALF_UP), entry_price=total.quantize(MONEY),
                   reason=reason.replace("precio de entrada leido como total pagado", "precio de entrada ya era por unidad"))
        return out
    if total > 0 and qty > 0:
        base_qty = (qty * factor).quantize(QTY)
        avg = (total / base_qty).quantize(QTY, rounding=ROUND_HALF_UP)
        out.update(avg_cost=avg, entry_price=(total / qty).quantize(MONEY, rounding=ROUND_HALF_UP),
                   purchase={"quantity": qty, "unit": unit, "total_paid": total, "base_quantity": base_qty, "unit_cost": avg})
    else:
        avg = _dec(item.get("avg_cost")) / stock_mult
        out.update(avg_cost=avg.quantize(QTY), entry_price=(avg * factor).quantize(MONEY))
    return out


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS carta_purchases (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            inventory_item_id uuid NOT NULL,
            quantity numeric(14, 4) NOT NULL,
            unit varchar(12) NOT NULL,
            total_paid numeric(14, 2) NOT NULL,
            base_quantity numeric(18, 4) NOT NULL,
            unit_cost numeric(18, 4) NOT NULL,
            source varchar(30) NOT NULL DEFAULT 'compra',
            created_by varchar(120) NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_carta_purchases_item ON carta_purchases (company_id, inventory_item_id, created_at DESC)")
    bind = op.get_bind()
    companies = [str(r[0]) for r in bind.execute(sa.text("""
        SELECT cm.company_id FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE LOWER(m.code) = 'carta' AND cm.enabled IS TRUE
    """)).fetchall()]
    for company_id in companies:
        _reinterpret_company(bind, company_id)


def _reinterpret_company(bind, company_id: str) -> None:
    params = {"c": company_id}
    items = [dict(r._mapping) for r in bind.execute(sa.text("""
        SELECT id, COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), sku, id::text) AS name, purchase_unit, consumption_unit,
               units_per_purchase, current_stock, min_stock, entry_price, sale_price, avg_cost, size_unit
        FROM inventory_items
        WHERE company_id = CAST(:c AS uuid) AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
    """), params).fetchall()]
    first_qty = {str(r[0]): r[1] for r in bind.execute(sa.text("""
        SELECT DISTINCT ON (item_id) item_id, COALESCE(quantity_delta, quantity)
        FROM inventory_movements
        WHERE company_id = CAST(:c AS uuid) AND movement_type IN ('initial', 'entry') AND COALESCE(quantity_delta, quantity, 0) > 0
        ORDER BY item_id, created_at
    """), params).fetchall()}
    recipe_units = {}
    for row in bind.execute(sa.text("""
        SELECT inventory_item_id, unit FROM carta_recipe_lines
        WHERE company_id = CAST(:c AS uuid) AND inventory_item_id IS NOT NULL
    """), params).fetchall():
        dim = UNITS.get(str(row[1] or ""), (None,))[0]
        if dim in BASE_BY_DIM:
            recipe_units.setdefault(str(row[0]), dim)
    with_equivalences = {str(r[0]) for r in bind.execute(sa.text(
        "SELECT DISTINCT inventory_item_id FROM carta_unit_equivalences WHERE company_id = CAST(:c AS uuid)"), params).fetchall()}
    already = {str(r[0]) for r in bind.execute(sa.text(
        "SELECT DISTINCT inventory_item_id FROM carta_purchases WHERE company_id = CAST(:c AS uuid)"), params).fetchall()}
    for item in items:
        key = str(item["id"])
        if key in already:
            continue  # ya tiene compras con la regla nueva
        new = reinterpret({**item, "has_equivalences": key in with_equivalences}, first_qty.get(key), recipe_units.get(key))
        bind.execute(sa.text("""
            UPDATE inventory_items
               SET purchase_unit = :pu, consumption_unit = :cu, units_per_purchase = :f, current_stock = :stock,
                   min_stock = :min_stock, avg_cost = :avg, entry_price = :entry, updated_at = now()
             WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)
        """), {"pu": new["purchase_unit"], "cu": new["consumption_unit"], "f": new["units_per_purchase"],
               "stock": new["current_stock"], "min_stock": new["min_stock"], "avg": new["avg_cost"], "entry": new["entry_price"],
               "id": key, "c": company_id})
        if new["stock_mult"] != 1:
            # un plato directo de este insumo descuenta lo mismo que antes (1 kg, ahora 1000 g)
            bind.execute(sa.text("""
                UPDATE carta_items SET direct_qty = direct_qty * :m
                WHERE company_id = CAST(:c AS uuid) AND kind = 'directo' AND inventory_item_id = CAST(:id AS uuid)
            """), {"m": new["stock_mult"], "c": company_id, "id": key})
        purchase = new["purchase"]
        if purchase:
            bind.execute(sa.text("""
                INSERT INTO carta_purchases (id, company_id, inventory_item_id, quantity, unit, total_paid, base_quantity, unit_cost, source)
                VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:item AS uuid), :quantity, :unit, :total_paid, :base_quantity,
                        :unit_cost, 'reinterpretada_022f')
            """), {"id": str(uuid.uuid4()), "c": company_id, "item": key, **purchase})
        print(f"[022f_carta_purchases] {item['name']}: {new['reason']}; existencia {item['current_stock']} -> "
              f"{new['current_stock']} {new['consumption_unit']}; costo {new['avg_cost']} por {new['consumption_unit']}"
              + (f" ({purchase['quantity']} {purchase['unit']} por {purchase['total_paid']})" if purchase else " (sin compra para leer)"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS carta_purchases")
