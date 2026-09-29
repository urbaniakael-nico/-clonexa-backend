"""Proximas compras, cobertura y valor del inventario (049T): motor puro.

Una sola fuente para las cifras de inventario de las empresas con Carta, la
misma en Stock, Inventario, Reportes y Proximas compras:

- Valor de un insumo = saldo de cantidad (en su unidad base: g, ml, unidad)
  x costo por unidad base (dinero / cantidad). Un insumo en cero o en
  negativo, o sin costo conocido, vale 0. 12.000 g a $16 = $192.000.
- Consumo real = lo que las ventas descontaron del inventario (movimientos
  'hospitality_sale' y las ediciones de pedidos, que suman o restan) en los
  ultimos WINDOW_DAYS dias. Nada de estimaciones por receta: lo que salio.
- Consumo diario = consumo / dias observados (desde el primer movimiento del
  insumo si es mas reciente que la ventana). Sin al menos MIN_ACTIVE_DAYS
  dias con consumo y MIN_OBSERVED_DAYS dias observados no hay proyeccion:
  se dice "sin historial suficiente" en vez de inventar.
- Dias de cobertura = existencia / consumo diario.
- Cuanto comprar = lo que falta para cubrir `days_to_cover` dias al ritmo
  actual y quedar sobre el minimo: consumo diario x dias + minimo - existencia.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from app.services import carta as engine

WINDOW_DAYS = 28
MIN_ACTIVE_DAYS = 3
MIN_OBSERVED_DAYS = 7
DEFAULT_DAYS_TO_COVER = 15
MAX_DAYS_TO_COVER = 90
SALE_MOVEMENTS = {"hospitality_sale", "hospitality_order_edit"}
MONEY = Decimal("0.01")


def dec(value: Any) -> Decimal:
    return engine.dec(value)


def as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------- valor ---
def item_value(insumo: dict | None) -> Decimal:
    """Saldo en dinero que cuenta en el valor del inventario (0 si esta en cero,
    en negativo o sin costo)."""
    if not insumo or dec(insumo.get("current_stock")) <= 0:
        return Decimal("0")
    value = engine.stock_value(insumo)
    return value if value is not None and value > 0 else Decimal("0")


def inventory_value(insumos: Iterable[dict]) -> Decimal:
    return sum((item_value(i) for i in insumos), Decimal("0")).quantize(MONEY, rounding=ROUND_HALF_UP)


# ----------------------------------------------------------- consumo ---
def consumption(movements: Iterable[dict], now: datetime, window_days: int = WINDOW_DAYS) -> dict[str, dict]:
    """Por insumo: consumo neto de la ventana (unidad base), dias con consumo y
    dias observados. `movements`: item_id, movement_type, quantity_delta,
    created_at (todos los del insumo, para saber desde cuando existe)."""
    start = now - timedelta(days=window_days)
    out: dict[str, dict] = defaultdict(lambda: {"consumed": Decimal("0"), "active_days": set(), "first_seen": None})
    for move in movements:
        key = str(move.get("item_id") or "")
        when = as_datetime(move.get("created_at"))
        if not key or when is None or when > now:
            continue
        row = out[key]
        if row["first_seen"] is None or when < row["first_seen"]:
            row["first_seen"] = when
        if when < start or str(move.get("movement_type") or "") not in SALE_MOVEMENTS:
            continue
        used = -dec(move.get("quantity_delta"))  # una venta descuenta (delta negativo)
        row["consumed"] += used
        if used > 0:
            row["active_days"].add(when.date())
    result = {}
    for key, row in out.items():
        first = row["first_seen"] or start
        observed = max(1, min(window_days, math.ceil((now - max(first, start)).total_seconds() / 86400)))
        consumed = max(row["consumed"], Decimal("0"))
        enough = len(row["active_days"]) >= MIN_ACTIVE_DAYS and observed >= MIN_OBSERVED_DAYS
        result[key] = {"consumed": consumed, "active_days": len(row["active_days"]), "observed_days": observed,
                       "daily": (consumed / observed) if enough else None, "enough_history": enough}
    return result


def coverage_days(stock: Any, daily: Decimal | None) -> Decimal | None:
    if daily is None or daily <= 0:
        return None
    stock = dec(stock)
    return Decimal("0") if stock <= 0 else (stock / daily)


# ------------------------------------------------- proximas compras ---
def _round_up(quantity: Decimal, unit: str) -> Decimal:
    """Cantidad a comprar en la unidad natural, hacia arriba: unidades
    enteras; kilos y litros de a 0,1."""
    if quantity <= 0:
        return Decimal("0")
    step = Decimal("1") if engine.UNITS.get(unit, ("unidad",))[0] not in {"masa", "volumen"} or unit in {"g", "ml"} else Decimal("0.1")
    return (quantity / step).to_integral_value(rounding="ROUND_CEILING") * step


def plan(insumos: dict[str, dict], usage: dict[str, dict], last_purchases: dict[str, dict] | None = None,
         days_to_cover: int = DEFAULT_DAYS_TO_COVER) -> dict:
    """Que hay que comprar hoy, ordenado por urgencia, con cantidad y costo."""
    days_to_cover = max(1, min(int(days_to_cover or DEFAULT_DAYS_TO_COVER), MAX_DAYS_TO_COVER))
    last_purchases = last_purchases or {}
    buy, ok = [], []
    for key, insumo in insumos.items():
        if str(insumo.get("status") or "active") in {"archived", "deleted"}:
            continue
        stock = dec(insumo.get("current_stock"))
        minimum = dec(insumo.get("min_stock"))
        use = usage.get(key) or {"consumed": Decimal("0"), "daily": None, "enough_history": False, "active_days": 0, "observed_days": 0}
        daily = use["daily"]
        days_left = coverage_days(stock, daily)
        factor = engine.natural_factor(insumo) or Decimal("1")
        unit = engine.natural_unit(insumo)
        if stock <= 0:
            reason, rank = "agotado", 0
        elif minimum > 0 and stock <= minimum:
            reason, rank = "bajo_minimo", 1
        elif days_left is not None and days_left <= days_to_cover:
            reason, rank = "se_acaba", 2
        else:
            reason, rank = "ok", 9
        if daily is not None:
            need_base = daily * days_to_cover + minimum - stock
            basis = "consumo"
        elif minimum > 0 and stock <= minimum:
            need_base = minimum - max(stock, Decimal("0"))  # sin historial: solo hasta el minimo
            basis = "minimo"
        else:
            need_base = Decimal("0")
            basis = "sin_historial" if reason != "ok" or not use["enough_history"] else "consumo"
        suggest_natural = _round_up(need_base / factor, unit) if need_base > 0 else Decimal("0")
        suggest_base = suggest_natural * factor
        cost = engine.unit_cost(insumo)
        estimated = (suggest_base * cost).quantize(MONEY, rounding=ROUND_HALF_UP) if cost is not None and suggest_base > 0 else None
        row = {
            "id": key, "name": insumo.get("name") or "Insumo", "reason": reason,
            "unit": unit, "unit_label": engine.RECIPE_UNITS.get(unit, unit),
            "base_unit": insumo.get("consumption_unit") or "unidad",
            "base_label": engine.RECIPE_UNITS.get(str(insumo.get("consumption_unit") or "unidad"), "unidad"),
            "stock": float(stock), "stock_natural": float((stock / factor).quantize(engine.QTY)),
            "min_natural": float((minimum / factor).quantize(engine.QTY)),
            "daily": float(daily) if daily is not None else None,
            "daily_natural": float((daily / factor).quantize(engine.QTY)) if daily is not None else None,
            "consumed_window": float(use["consumed"]),
            "days_left": float(days_left.quantize(Decimal("0.1"))) if days_left is not None else None,
            "enough_history": bool(use["enough_history"]), "active_days": use["active_days"], "observed_days": use["observed_days"],
            "basis": basis,
            "suggest_natural": float(suggest_natural), "suggest_base": float(suggest_base),
            "unit_cost": float(cost) if cost is not None else None,
            "cost_per_unit": float((cost * factor).quantize(MONEY)) if cost is not None else None,
            "estimated_cost": float(estimated) if estimated is not None else None,
            "value": float(item_value(insumo)),
            "last_purchase": last_purchases.get(key),
            "_rank": rank, "_days": float(days_left) if days_left is not None else math.inf,
        }
        (ok if reason == "ok" else buy).append(row)
    buy.sort(key=lambda r: (r["_rank"] if r["_rank"] < 2 else 2, r["_days"], r["name"].lower()))
    ok.sort(key=lambda r: (r["_days"], r["name"].lower()))
    for row in (*buy, *ok):
        row.pop("_rank")
        row.pop("_days")
    total = sum((Decimal(str(r["estimated_cost"])) for r in buy if r["estimated_cost"] is not None), Decimal("0"))
    return {"days_to_cover": days_to_cover, "window_days": WINDOW_DAYS, "buy": buy, "ok": ok,
            "total_estimated": float(total.quantize(MONEY)),
            "without_cost": [r["name"] for r in buy if r["suggest_natural"] > 0 and r["estimated_cost"] is None],
            "without_history": [r["name"] for r in buy if not r["enough_history"]]}


def qty_text(value: Any, unit_label: str = "") -> str:
    """11725.5 -> "11.725,5" (como se escriben las cantidades en Colombia)."""
    number = dec(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP).normalize()
    text = f"{number:,f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return f"{text} {unit_label}".strip()


def report_inventory(insumos: dict[str, dict], usage: dict[str, dict], buy_within_days: int = 3) -> dict:
    """La seccion de inventario de Reportes con las MISMAS cifras de Stock y
    Proximas compras (misma forma que ya pinta la pantalla)."""
    stats = summary(insumos, usage)
    coverage, idle = [], []
    for key, insumo in insumos.items():
        use = usage.get(key)
        factor = engine.natural_factor(insumo) or Decimal("1")
        label = engine.RECIPE_UNITS.get(engine.natural_unit(insumo), "unidad")
        stock = dec(insumo.get("current_stock"))
        if use and use["daily"] is not None and use["daily"] > 0:
            days = coverage_days(stock, use["daily"])
            coverage.append({"name": insumo.get("name") or "Insumo", "stock": qty_text(stock / factor, label),
                             "daily": qty_text(use["daily"] / factor, label), "days": float(days.quantize(Decimal("0.1"))),
                             "unit": label})
        elif stock > 0 and (not use or use["consumed"] <= 0) and str(insumo.get("item_type") or "") != "consumible":
            value = item_value(insumo)
            idle.append({"name": insumo.get("name") or "Insumo", "stock": qty_text(stock / factor, label),
                         "value": float(value) if value > 0 else None})
    coverage.sort(key=lambda r: r["days"])
    uncosted = sum(1 for i in insumos.values() if dec(i.get("current_stock")) > 0 and engine.unit_cost(i) is None)
    return {"value": stats["value"], "uncosted_items": uncosted, "coverage": coverage,
            "buy_today": [r for r in coverage if r["days"] < buy_within_days],
            "idle": sorted(idle, key=lambda r: -(r["value"] or 0)),
            "daily_consumption_cost": stats["daily_consumption_cost"], "inventory_days": stats["inventory_days"],
            "turns_per_month": stats["turns_per_month"], "window_days": WINDOW_DAYS,
            "without_history": [r["name"] for r in stats["items"] if not r["enough_history"]],
            "source": "movimientos"}


def summary(insumos: dict[str, dict], usage: dict[str, dict]) -> dict:
    """Cifras del inventario para Reportes y Stock: valor, consumo diario en
    dinero, dias de inventario (rotacion) y cobertura por insumo."""
    value = inventory_value(insumos.values())
    daily_cost = Decimal("0")
    rows = []
    for key, insumo in insumos.items():
        use = usage.get(key)
        daily = use["daily"] if use else None
        cost = engine.unit_cost(insumo)
        if daily is not None and cost is not None:
            daily_cost += daily * cost
        if use and use["consumed"] > 0:
            factor = engine.natural_factor(insumo) or Decimal("1")
            days_left = coverage_days(insumo.get("current_stock"), daily)
            rows.append({"id": key, "name": insumo.get("name") or "Insumo",
                         "unit_label": engine.RECIPE_UNITS.get(engine.natural_unit(insumo), "unidad"),
                         "consumed_natural": float((use["consumed"] / factor).quantize(engine.QTY)),
                         "daily_natural": float((daily / factor).quantize(engine.QTY)) if daily is not None else None,
                         "days_left": float(days_left.quantize(Decimal("0.1"))) if days_left is not None else None,
                         "enough_history": use["enough_history"]})
    rows.sort(key=lambda r: (r["days_left"] is None, r["days_left"] or 0))
    inventory_days = (value / daily_cost) if daily_cost > 0 else None
    return {"value": float(value), "daily_consumption_cost": float(daily_cost.quantize(MONEY)),
            "inventory_days": float(inventory_days.quantize(Decimal("0.1"))) if inventory_days is not None else None,
            "turns_per_month": float((Decimal("30") / inventory_days).quantize(Decimal("0.1"))) if inventory_days else None,
            "window_days": WINDOW_DAYS, "items": rows}
