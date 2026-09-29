"""Carta, recetas e insumos (049H): motor puro, sin base de datos.

Inventario = lo que se compra (insumos con tipo, unidad de compra, unidad de
consumo y costo promedio ponderado). Carta = lo que se vende (platos directos
ligados a un insumo, o preparados con receta). Al vender, cada linea del
pedido guarda que insumos consumio y a que costo en ese momento.

Reglas:
- Existencias y costo promedio van en la UNIDAD DE CONSUMO del insumo
  (g, ml o unidad). units_per_purchase = cuantas unidades de consumo trae
  una unidad de compra (1 lb = 453.59237 g; 1 pollo = 1600 g si la empresa
  lo define asi).
- Receta: la cantidad es lo que va en el plato. Lo que se descuenta y se
  cuesta es cantidad / rendimiento (250 g servidos con 65 % = 384.6 g crudos).
- Plato directo: descuenta su insumo x cantidad y bloquea la venta sin stock
  (igual que hoy). Plato preparado: descuenta los ingredientes sin bloquear;
  un ingrediente puede quedar en negativo y el Dashboard avisa.
- Un consumible (gas, servilletas) nunca va a un plato ni a una receta.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

ITEM_TYPES = {"venta_directa": "Venta directa", "ingrediente": "Ingrediente", "consumible": "Consumible"}
DISH_KINDS = {"directo", "preparado", "combo"}
# Categorias sugeridas del asistente (el dueño puede agregar las suyas).
PRESET_CATEGORIES = [
    ("BEBIDAS", "gaseosas, jugos, energizantes, cerveza"),
    ("PLATOS A LA CARTA", "churrasco, carne asada, pechuga a la plancha, costillitas"),
    ("POLLO", "frito, broaster, asado"),
    ("COMIDAS RÁPIDAS", "hamburguesas, perros calientes, salchipapas"),
    ("PORCIONES", "papa francesa, papa salada, ensalada, presa de pollo"),
]
MAX_COMBO_DEPTH = 3
# unidad -> (dimension, cuantas unidades base trae)
UNITS: dict[str, tuple[str, Decimal]] = {
    "g": ("masa", Decimal("1")), "gramo": ("masa", Decimal("1")), "kg": ("masa", Decimal("1000")),
    "kilo": ("masa", Decimal("1000")), "lb": ("masa", Decimal("453.59237")), "libra": ("masa", Decimal("453.59237")),
    "ml": ("volumen", Decimal("1")), "l": ("volumen", Decimal("1000")), "litro": ("volumen", Decimal("1000")),
    "unidad": ("unidad", Decimal("1")), "par": ("unidad", Decimal("2")),
    # 049O: onza, docena y cucharada (15 ml) tienen equivalencia fija; paquete y
    # pizca no: cuanto trae un paquete o cuanto pesa una pizca lo dice la empresa.
    "oz": ("masa", Decimal("28.349523125")), "docena": ("unidad", Decimal("12")),
    "cucharada": ("volumen", Decimal("15")), "paquete": ("paquete", Decimal("1")), "pizca": ("pizca", Decimal("1")),
}
# 049N/049O: las mismas unidades para TODOS los insumos (clave -> etiqueta).
# Cada linea se convierte sola a la unidad del inventario del insumo; si no
# hay forma, se pide una sola vez la equivalencia y se guarda para el insumo.
RECIPE_UNITS = {"g": "gr", "kg": "kg", "lb": "lb", "oz": "onza", "ml": "ml", "l": "litros", "unidad": "unidad",
                "par": "par", "docena": "docena", "paquete": "paquete", "cucharada": "cucharada", "pizca": "pizca"}
_RECIPE_ALIASES = {"gr": "g", "gramo": "g", "gramos": "g", "kilo": "kg", "kilos": "kg", "libra": "lb", "libras": "lb",
                   "onza": "oz", "onzas": "oz", "litro": "l", "litros": "l", "lt": "l", "und": "unidad", "unidades": "unidad",
                   "u": "unidad", "docenas": "docena", "paquetes": "paquete", "cucharadas": "cucharada", "pizcas": "pizca"}
# Un ingrediente que cuesta mas de 3 veces el plato casi siempre es una unidad
# mal puesta (275 "unidades" de carne en vez de 275 gr): se avisa en vez de
# mostrar la cifra como si fuera correcta.
SUSPECT_SHARE_OF_PRICE = Decimal("3")
# 049Q: Inventario y Carta usan EXACTAMENTE la misma lista (RECIPE_UNITS). La
# unidad de compra de un insumo es su "unidad natural" (80 kg); la existencia y
# el costo se guardan en su unidad base (g, ml, unidad...) y se muestran en la
# natural. Las claves viejas (libra, kilo, gramo, litro) se leen como su par.
PURCHASE_UNITS = list(RECIPE_UNITS)
LEGACY_PURCHASE_UNITS = {"libra": "lb", "kilo": "kg", "gramo": "g", "litro": "l"}
BASE_UNITS = {"masa": "g", "volumen": "ml", "unidad": "unidad", "paquete": "paquete", "pizca": "pizca"}
CONSUMPTION_UNITS = ["g", "ml", "unidad", "paquete", "pizca"]
QTY = Decimal("0.0001")
MONEY = Decimal("0.01")


def dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else 0))
    except Exception:
        return Decimal("0")


def clean_unit(value: Any, allowed: Iterable[str]) -> str:
    unit = str(value or "").strip().lower()
    aliases = {"gr": "g", "gramos": "g", "kilos": "kilo", "kilogramo": "kilo", "libras": "libra", "litros": "litro",
               "mililitro": "ml", "mililitros": "ml", "unidades": "unidad", "und": "unidad", "u": "unidad", "gramo": "g"}
    unit = aliases.get(unit, unit)
    allowed = list(allowed)
    if unit == "g" and "gramo" in allowed and "g" not in allowed:
        unit = "gramo"
    if unit not in allowed:
        raise ValueError(f"unidad_invalida:{value}")
    return unit


def standard_factor(purchase_unit: str, consumption_unit: str) -> Decimal | None:
    """Unidades de consumo por unidad de compra cuando ambas son de la misma
    dimension (libra -> g = 453.59237). None si la conversion la define la
    empresa (unidad -> g: cuanto pesa un pollo)."""
    p, c = UNITS.get(purchase_unit), UNITS.get(consumption_unit)
    if not p or not c or p[0] != c[0]:
        return None
    return p[1] / c[1]


def recipe_unit(value: Any) -> str | None:
    """Unidad de receta valida (acepta "gr", "kilos", "litros"...) o None."""
    unit = str(value or "").strip().lower()
    unit = _RECIPE_ALIASES.get(unit, unit)
    return unit if unit in RECIPE_UNITS else None


def default_recipe_unit(insumo: dict | None) -> str:
    consumption_unit = str((insumo or {}).get("consumption_unit") or "unidad")
    return consumption_unit if consumption_unit in RECIPE_UNITS else "unidad"


def line_factor(unit: Any, insumo: dict | None) -> Decimal | None:
    """Cuantas unidades de consumo del insumo hay en 1 unidad de la receta.

    1. Misma dimension: directo (1 kg = 1000 g; 1 lb = 453,59 g; 1 litro =
       1000 ml; 1 docena = 12 unidades; 1 cucharada = 15 ml, y al reves).
    2. Equivalencia guardada para el insumo ("1 unidad de carne = 1 lb",
       "1 cucharada de sal = 12 g"), para esa unidad o para una de su misma
       dimension (con "1 unidad = 1 lb" tambien sirven gr, kg y onza).
    3. La unidad de compra y su conversion (1 unidad de pollo = 1600 g).
    None si no hay forma: la pantalla pide la equivalencia una sola vez."""
    if purchase_weight_missing(insumo):
        return None  # la pantalla pregunta cuanto pesa 1 unidad de compra
    consumption_unit = str((insumo or {}).get("consumption_unit") or "unidad")
    unit = recipe_unit(unit) or consumption_unit
    if unit == consumption_unit:
        return Decimal("1")
    direct = standard_factor(unit, consumption_unit)
    if direct is not None:
        return direct
    equivalences = (insumo or {}).get("equivalences") or {}
    if dec(equivalences.get(unit)) > 0:
        return dec(equivalences[unit])
    for other, amount in equivalences.items():
        sibling = standard_factor(unit, other)
        if sibling is not None and dec(amount) > 0:
            return sibling * dec(amount)
    purchase_unit = str((insumo or {}).get("purchase_unit") or "unidad")
    via_purchase = standard_factor(unit, purchase_unit)
    per_purchase = dec((insumo or {}).get("units_per_purchase"))
    if via_purchase is not None and per_purchase > 0:
        return via_purchase * per_purchase
    return None


def line_need(line: dict, insumos: dict[str, dict] | None) -> Decimal | None:
    """Unidades de consumo que gasta UNA porcion de la linea (con su unidad y
    su rendimiento). None si la unidad no se puede convertir todavia (falta
    la equivalencia): esa linea ni descuenta ni tiene costo, nunca una cifra
    inventada."""
    if insumos is None:
        factor = Decimal("1")  # sin inventario a mano: la cantidad ya esta en unidad de consumo
    else:
        factor = line_factor(line.get("unit"), insumos.get(str(line.get("inventory_item_id"))))
        if factor is None:
            return None
    yield_pct = dec(line.get("yield_pct") or 100)
    if yield_pct <= 0:
        yield_pct = Decimal("100")
    return dec(line.get("quantity")) * factor * Decimal("100") / yield_pct


def to_consumption(quantity: Any, item: dict) -> Decimal:
    """Cantidad en unidad de compra -> unidad de consumo del insumo."""
    return (dec(quantity) * dec(item.get("units_per_purchase") or 1)).quantize(QTY, rounding=ROUND_HALF_UP)


def weighted_average(stock: Any, avg_cost: Any, qty_in: Any, unit_cost_in: Any) -> Decimal:
    """Costo promedio ponderado tras una entrada (todo en unidad de consumo).
    Con existencia en cero o negativa, el costo pasa a ser el de la compra."""
    stock, avg, qty, unit = dec(stock), dec(avg_cost), dec(qty_in), dec(unit_cost_in)
    if qty <= 0:
        return avg
    if stock <= 0:
        return unit.quantize(QTY, rounding=ROUND_HALF_UP)
    return ((stock * avg + qty * unit) / (stock + qty)).quantize(QTY, rounding=ROUND_HALF_UP)


def purchase_weight_missing(insumo: dict | None) -> bool:
    """049P: se compra por "unidad" pero se consume en g/ml y cada unidad de
    compra "trae" 1 g o 1 ml. Asi el precio de la unidad (una libra de carne
    a $14.000) queda como precio de UN gramo: 275 g = $3.850.000. Esa
    conversion es imposible; hasta que se diga cuanto pesa una unidad de
    compra, el insumo no da costo ni descuenta en las recetas."""
    if not insumo:
        return False
    return (str(insumo.get("purchase_unit") or "unidad") == "unidad"
            and str(insumo.get("consumption_unit") or "unidad") in {"g", "ml"}
            and dec(insumo.get("units_per_purchase") or 1) <= 1)


def purchase_unit_key(value: Any) -> str | None:
    """Unidad de compra en la lista unica ("libra" -> "lb", "Kilos" -> "kg")."""
    raw = str(value or "").strip().lower()
    return recipe_unit(LEGACY_PURCHASE_UNITS.get(raw, raw))


def base_unit_for(unit: str) -> str:
    """Unidad en la que se guarda la existencia de algo que se compra en `unit`:
    lo que se pesa en g, lo liquido en ml, lo que se cuenta en unidades."""
    return BASE_UNITS[UNITS[unit][0]]


def natural_unit(insumo: dict | None) -> str:
    """Unidad en la que la empresa compra y piensa el insumo (80 kg, no 80.000 g)."""
    return (purchase_unit_key((insumo or {}).get("purchase_unit"))
            or recipe_unit((insumo or {}).get("consumption_unit")) or "unidad")


def natural_factor(insumo: dict | None) -> Decimal | None:
    """Unidades base (de consumo) que trae 1 unidad natural: 1 kg = 1000 g.
    None mientras no se sepa cuanto pesa la unidad de compra."""
    if not insumo or purchase_weight_missing(insumo):
        return None
    factor = dec(insumo.get("units_per_purchase") or 1)
    return factor if factor > 0 else None


def stock_natural(insumo: dict | None) -> Decimal | None:
    """80.000 g de carne comprada por kilo -> 80 (kg)."""
    factor = natural_factor(insumo)
    if factor is None:
        return None
    return (dec((insumo or {}).get("current_stock")) / factor).quantize(QTY, rounding=ROUND_HALF_UP)


COST = Decimal("0.00000001")  # costo por unidad base: saldo de dinero / saldo de cantidad, sin perder pesos
# Un gramo o mililitro de algo de un asadero nunca cuesta mas de $500 ($500.000
# el kilo): un saldo asi quedo mal cargado (CARNE Asada: 16 g a $56.000 el g).
SUSPECT_COST_PER_BASE = Decimal("500")


def stock_value(insumo: dict | None) -> Decimal | None:
    """049R: saldo de dinero del insumo = saldo de cantidad x costo por unidad."""
    cost = unit_cost(insumo)
    if cost is None:
        return None
    return (dec((insumo or {}).get("current_stock")) * cost).quantize(MONEY, rounding=ROUND_HALF_UP)


def balance_suspect(insumo: dict | None) -> bool:
    """Saldo que no puede ser real: se corrige registrando la compra de nuevo."""
    if not insumo:
        return False
    if purchase_weight_missing(insumo):
        return True
    cost = unit_cost(insumo)
    return bool(cost is not None and str(insumo.get("consumption_unit") or "") in {"g", "ml"} and cost > SUSPECT_COST_PER_BASE)


def register_purchase(insumo: dict, quantity: Any, unit: Any, total_paid: Any, replace: bool = False) -> dict:
    """049Q/049R: el inventario es una cuenta con DOS saldos, cantidad y dinero.

    La compra se escribe como la hace el dueño: cantidad total comprada (con
    su unidad) y total pagado. Nadie escribe un precio unitario:
      12 kg por $192.000        -> 12.000 g y $192.000 ($16 por g)
      una receta consume 275 g  -> 11.725 g y $187.600 (costo del plato $4.400)
      3 kg mas por $42.000      -> 14.725 g y $229.600 (costo = dinero / cantidad)

    `replace`: la compra REEMPLAZA los saldos (corrige un insumo mal cargado) y
    su unidad pasa a ser la de esta compra."""
    qty, total = dec(quantity), dec(total_paid)
    if qty <= 0:
        raise ValueError("cantidad_invalida")
    if total < 0:
        raise ValueError("total_invalido")
    key = recipe_unit(unit)
    if not key:
        raise ValueError("unidad_invalida")
    if replace:
        base_unit = base_unit_for(key)
        factor = standard_factor(key, base_unit) or Decimal("1")
    else:
        base_unit = str(insumo.get("consumption_unit") or "unidad")
        factor = line_factor(key, insumo)
        if factor is None:
            raise ValueError("sin_equivalencia")
    base_qty = (qty * factor).quantize(QTY, rounding=ROUND_HALF_UP)
    if base_qty <= 0:
        raise ValueError("cantidad_invalida")
    purchase_cost = (total / base_qty).quantize(COST, rounding=ROUND_HALF_UP)
    stock = Decimal("0") if replace else dec(insumo.get("current_stock"))
    value = Decimal("0") if replace else (stock_value(insumo) if unit_cost(insumo) is not None else None)
    new_stock = stock + base_qty
    if value is None or new_stock <= 0:
        # sin saldo de dinero conocido (o la cuenta sigue en negativo): el costo es el de esta compra
        new_avg = purchase_cost
        new_value = (new_stock * new_avg).quantize(MONEY, rounding=ROUND_HALF_UP)
    else:
        new_value = value + total
        new_avg = (new_value / new_stock).quantize(COST, rounding=ROUND_HALF_UP)
    out = {"unit": key, "quantity": qty, "total_paid": total, "base_quantity": base_qty, "base_unit": base_unit,
           "unit_cost": purchase_cost, "avg_cost": new_avg, "new_stock": new_stock, "stock_value": new_value,
           "cost_per_unit": (total / qty).quantize(MONEY, rounding=ROUND_HALF_UP), "replace": bool(replace)}
    if replace:
        out.update(purchase_unit=key, consumption_unit=base_unit, units_per_purchase=factor)
    return out


def configure_unit(insumo: dict, unit: Any, convert_amount: Any = None) -> dict:
    """049Q: el insumo se configura en Inventario eligiendo SU unidad de la
    lista unica. Se deriva todo lo demas (ya no se escribe "consumo por unidad
    de compra", que fue donde nacio "1 unidad = 1 g"):

    - Misma dimension que la existencia (kg -> g, lb -> g, litros -> ml): la
      existencia no cambia; solo cambia en que unidad se ve y se compra.
    - Unidad que ya tiene equivalencia para el insumo (1 unidad de pollo =
      1600 g): igual, sin reexpresar nada.
    - Otra dimension (se contaba por unidad y ahora se pesa): la existencia
      pasa a la base nueva; si hay existencia, costo o equivalencias se pide
      `convert_amount` = cuantas <unidad nueva> hay en 1 <unidad anterior>, y
      existencia, costo y equivalencias se reexpresan sin perder valor.

    Devuelve purchase_unit, consumption_unit, units_per_purchase y `ratio`
    (unidades base nuevas por cada unidad base anterior)."""
    key = recipe_unit(unit)
    if not key:
        raise ValueError("unidad_invalida")
    base = str(insumo.get("consumption_unit") or "unidad")
    missing = purchase_weight_missing(insumo)
    if not missing:
        same = standard_factor(key, base)
        if same is None:
            same = line_factor(key, insumo)
        if same is not None:
            return {"purchase_unit": key, "consumption_unit": base, "units_per_purchase": same, "ratio": Decimal("1")}
    new_base = base_unit_for(key)
    factor = standard_factor(key, new_base) or Decimal("1")
    needs = missing or dec(insumo.get("current_stock")) != 0 or dec(insumo.get("avg_cost")) > 0 or bool(insumo.get("equivalences"))
    if not needs:
        return {"purchase_unit": key, "consumption_unit": new_base, "units_per_purchase": factor, "ratio": Decimal("1")}
    amount = dec(convert_amount)
    if amount <= 0:
        raise ValueError("falta_conversion")
    old_natural = Decimal("1") if missing else (dec(insumo.get("units_per_purchase")) or Decimal("1"))
    return {"purchase_unit": key, "consumption_unit": new_base, "units_per_purchase": factor,
            "ratio": amount * factor / old_natural}


def unit_cost(insumo: dict | None) -> Decimal | None:
    """Costo por unidad de consumo; None si el insumo no tiene costo cargado
    (o si no se sabe cuanto pesa su unidad de compra)."""
    if not insumo or purchase_weight_missing(insumo):
        return None
    avg = dec(insumo.get("avg_cost"))
    if avg > 0:
        return avg
    entry = dec(insumo.get("entry_price"))
    if entry > 0:
        return entry / (dec(insumo.get("units_per_purchase")) or Decimal("1"))
    return None


def consumption(dish: dict, lines: list[dict], quantity: Any, catalog: tuple[dict, dict] | None = None, depth: int = 0,
                insumos: dict[str, dict] | None = None) -> list[dict]:
    """Insumos que consume vender `quantity` del plato (0.25 = boton 1/4).

    Combo: no tiene existencia propia; descuenta sus partes (platos de la
    carta, con su propia receta o insumo, o insumos sueltos). `catalog` =
    (platos por id, lineas por plato) para resolver los platos del combo."""
    qty = dec(quantity)
    if qty <= 0:
        return []
    if dish.get("kind") == "combo":
        by_id, lines_map = catalog or ({}, {})
        out: list[dict] = []
        for line in lines:
            part_qty = qty * (dec(line.get("quantity")) or Decimal("1"))
            component = line.get("component_item_id")
            if component:
                part = by_id.get(str(component))
                if not part or depth >= MAX_COMBO_DEPTH:
                    continue
                out.extend(consumption(part, lines_map.get(str(component), []), part_qty, catalog, depth + 1, insumos))
            elif line.get("inventory_item_id"):
                per = line_need({**line, "quantity": dec(line.get("quantity")) or Decimal("1"), "yield_pct": 100}, insumos)
                if per is None:
                    continue
                need = qty * per
                out.append({"inventory_item_id": str(line["inventory_item_id"]),
                            "quantity": float(need.quantize(QTY, rounding=ROUND_HALF_UP)), "blocking": True})
        merged: dict[tuple, dict] = {}
        for entry in out:
            key = (entry["inventory_item_id"], entry["blocking"])
            row = merged.setdefault(key, {**entry, "quantity": 0.0})
            row["quantity"] = float((dec(row["quantity"]) + dec(entry["quantity"])).quantize(QTY, rounding=ROUND_HALF_UP))
        return list(merged.values())
    if dish.get("kind") == "preparado":
        out = []
        for line in lines:
            per = line_need(line, insumos)
            if per is None:
                continue
            need = qty * per
            if need > 0:
                out.append({"inventory_item_id": str(line.get("inventory_item_id")),
                            "quantity": float(need.quantize(QTY, rounding=ROUND_HALF_UP)), "blocking": False})
        return out
    insumo_id = dish.get("inventory_item_id")
    if not insumo_id:
        return []
    need = qty * (dec(dish.get("direct_qty")) or Decimal("1"))
    return [{"inventory_item_id": str(insumo_id), "quantity": float(need.quantize(QTY, rounding=ROUND_HALF_UP)),
             "blocking": True}]


def cost_of(entries: list[dict], insumos: dict[str, dict]) -> tuple[Decimal | None, list[dict]]:
    """Costo total de los insumos consumidos (None si alguno no tiene costo) y
    las entradas con su costo unitario congelado."""
    total = Decimal("0")
    complete = bool(entries)
    priced = []
    for entry in entries:
        unit = unit_cost(insumos.get(entry["inventory_item_id"]))
        row = dict(entry)
        if unit is None:
            complete = False
            row["unit_cost"] = None
        else:
            row["unit_cost"] = float(unit.quantize(QTY, rounding=ROUND_HALF_UP))
            total += unit * dec(entry["quantity"])
        priced.append(row)
    return (total.quantize(MONEY, rounding=ROUND_HALF_UP) if complete else None), priced


def dish_summary(dish: dict, lines: list[dict], insumos: dict[str, dict], catalog: tuple[dict, dict] | None = None) -> dict:
    """Costo y margen de UNA unidad del plato para la pantalla de Carta."""
    entries = consumption(dish, lines, 1, catalog, insumos=insumos)
    cost, priced = cost_of(entries, insumos)
    price = dec(dish.get("price"))
    missing = [insumos.get(e["inventory_item_id"], {}).get("name") or "Insumo" for e in priced if e["unit_cost"] is None]
    no_equivalence = [(insumos.get(str(l.get("inventory_item_id"))) or {}).get("name") or "Insumo" for l in lines
                      if dish.get("kind") != "directo" and l.get("inventory_item_id") and line_need(l, insumos) is None]
    suspect = suspect_lines(priced, insumos, price)
    if no_equivalence or suspect:
        cost = None  # no se muestra un costo que no es: se avisa
    margin = (price - cost) if cost is not None else None
    return {
        "cost": float(cost) if cost is not None else None,
        "margin": float(margin.quantize(MONEY)) if margin is not None else None,
        "margin_pct": float((margin / price * 100).quantize(Decimal("0.1"))) if margin is not None and price > 0 else None,
        "below_cost": bool(cost is not None and price < cost),
        "missing_cost": missing,
        "missing_equivalence": no_equivalence,
        "cost_suspect": suspect,
        "no_recipe": dish.get("kind") in {"preparado", "combo"} and not lines,
        "consumption": priced,
    }


def suspect_lines(priced: list[dict], insumos: dict[str, dict], price: Any) -> list[str]:
    """Ingredientes que por si solos cuestan mas de 3 veces el plato (umbral
    SUSPECT_SHARE_OF_PRICE del precio): casi seguro una unidad mal puesta."""
    price = dec(price)
    if price <= 0:
        return []
    out = []
    for entry in priced:
        if entry.get("unit_cost") is None:
            continue
        if dec(entry["unit_cost"]) * dec(entry["quantity"]) > price * SUSPECT_SHARE_OF_PRICE:
            out.append((insumos.get(entry["inventory_item_id"]) or {}).get("name") or "Insumo")
    return out


def validate_link(insumo: dict | None) -> None:
    if not insumo:
        raise ValueError("insumo_no_encontrado")
    if str(insumo.get("item_type") or "venta_directa") == "consumible":
        raise ValueError("consumible_no_va_a_la_carta")
