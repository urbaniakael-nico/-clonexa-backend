"""Reportes para el dueño (049G): motor puro, sin base de datos.

Se usa en los restaurantes con waiter_ordering (hoy ASADERO EL SOCIO). Recibe
los pedidos (mesero, caja, domicilios), las jornadas, el inventario con precio
de entrada, las porciones, los turnos de los meseros y devuelve cada seccion
de la pantalla: indicadores con variacion, venta y margen por dia, mapa de
calor, analisis de carta, equipo, cocina, operacion, inventario y lecturas.

Reglas que definen los numeros:
- Venta: total de los pedidos no cancelados. Cada pedido cuenta en el dia de
  su JORNADA (no en el dia calendario): un pedido de la 1 a.m. es de la
  jornada que abrio la noche anterior.
- Costo de una linea = precio de entrada x cantidad descontada del inventario.
  * Fraccion del producto (boton 1/4 sobre "POLLO Asado"): el inventario
    descuenta 0.25 pollos, asi que cuesta 0.25 x precio de entrada del pollo.
  * Porcion propia (grupo de porciones de Admin V2, p. ej. "Cuarto de pollo"
    con su propio item): su precio de entrada; si no lo tiene y el grupo tiene
    el entero con precio de entrada, 1/4 x el del entero, marcado "derivado
    del entero".
  * Sin precio de entrada: la linea NO tiene costo, no entra al margen y el
    producto sale en "sin costear".
- Merma: pedido cancelado cuando el inventario ya se habia descontado (el
  producto se perdio: cuenta su costo). Cancelacion: antes de descontar.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

MONEY = Decimal("0.01")
WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
WEEKDAYS_PLURAL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]
MIN_WEEKDAY_REPEATS = 3
SLOW_KITCHEN_MINUTES = 20
BUY_WITHIN_DAYS = 3
MAX_PERIOD_DAYS = 93
POPULARITY_FACTOR = Decimal("0.7")  # umbral clasico de ingenieria de menu
SYSTEM_CLOSE_REASONS = {"corte_diario", "cierre_automatico", "historico_largo"}


# ------------------------------------------------------------- helpers ---
def dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else 0))
    except Exception:
        return Decimal("0")


def money(value: Any) -> float:
    return float(dec(value).quantize(MONEY, rounding=ROUND_HALF_UP))


def aware(value: Any) -> datetime | None:
    if not value:
        return None
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        import json
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith("["):
        import json
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except ValueError:
            return []
    return []


def parse_fraction(label: Any) -> Fraction | None:
    words = {"entero": "1", "entera": "1", "completo": "1", "unidad": "1", "medio": "1/2", "media": "1/2",
             "mitad": "1/2", "cuarto": "1/4"}
    raw = str(label or "").strip().lower().replace(",", ".").replace(" ", "")
    raw = words.get(raw.split("de")[0] if raw.startswith(tuple(words)) else raw, raw)
    try:
        value = Fraction(raw)
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def fraction_text(value: Fraction) -> str:
    return {Fraction(1, 4): "1/4", Fraction(1, 2): "1/2", Fraction(3, 4): "3/4", Fraction(1, 3): "1/3",
            Fraction(2, 3): "2/3", Fraction(1): "entero"}.get(value, f"{value.numerator}/{value.denominator}")


def units_text(total: Fraction) -> str:
    """1.75 -> "1 y 3/4"; 0.5 -> "1/2"; 3 -> "3"."""
    whole = int(total)
    rest = total - whole
    if rest == 0:
        return f"{whole}"
    nice = min([Fraction(1, 4), Fraction(1, 3), Fraction(1, 2), Fraction(2, 3), Fraction(3, 4)],
               key=lambda f: abs(f - rest))
    if abs(nice - rest) > Fraction(1, 50):
        return f"{float(total):.2f}".rstrip("0").rstrip(".")
    return f"{whole} y {fraction_text(nice)}" if whole else fraction_text(nice)


def pct_change(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


# ------------------------------------------------------------ periodos ---
def resolve_period(kind: str, today: date, start: date | None = None, end: date | None = None) -> dict:
    """Periodo en dias de jornada y su anterior equivalente."""
    kind = (kind or "7d").lower()
    if kind == "today":
        start = end = today
        prev_start = prev_end = today - timedelta(days=1)
        label = "Hoy"
    elif kind == "yesterday":
        start = end = today - timedelta(days=1)
        prev_start = prev_end = today - timedelta(days=2)
        label = "Ayer"
    elif kind == "month":
        start, end = today.replace(day=1), today
        prev_last = start - timedelta(days=1)
        prev_start = prev_last.replace(day=1)
        prev_end = min(prev_start + (end - start), prev_last)
        label = "Este mes"
    elif kind == "custom":
        if not start or not end or end < start:
            raise ValueError("periodo_invalido")
        span = end - start
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - span
        label = "Personalizado"
    else:
        start, end = today - timedelta(days=6), today
        prev_start, prev_end = start - timedelta(days=7), start - timedelta(days=1)
        label = "Últimos 7 días"
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise ValueError("periodo_muy_largo")
    return {"kind": kind, "label": label, "start": start, "end": end, "prev_start": prev_start, "prev_end": prev_end,
            "days": (end - start).days + 1}


# ------------------------------------------------------------ jornadas ---
def jornada_resolver(
    orders: list[dict], closures: list[dict], tz: ZoneInfo, business_day: dict | None = None,
) -> Callable[[dict], date | None]:
    """Dia de jornada de cada pedido.

    - Con horario configurado (open/close): la fecha de negocio de la hora del
      pedido (antes del cierre de madrugada = jornada anterior).
    - Sin horario: la jornada es el cierre del dia al que pertenece el pedido
      (su fecha de apertura = primer pedido); los pedidos aun sin cerrar forman
      la jornada en curso, que abre con el primero de ellos.
    """
    if business_day:
        close_time = business_day["close"]
        overnight = business_day.get("overnight")

        def by_hours(order: dict) -> date | None:
            created = aware(order.get("created_at"))
            if not created:
                return None
            local = created.astimezone(tz)
            if overnight and local.time() < close_time:
                return local.date() - timedelta(days=1)
            return local.date()

        return by_hours

    closure_of: dict[str, str] = {}
    for closure in closures:
        for order_id in as_list(closure.get("order_ids")):
            closure_of[str(order_id)] = str(closure.get("id"))
    first_created: dict[str, datetime] = {}
    opened: dict[str, datetime] = {
        str(c.get("id")): aware(c.get("opened_at")) for c in closures if aware(c.get("opened_at"))
    }

    def key_of(order: dict) -> str | None:
        meta = as_dict(order.get("metadata"))
        cid = str(meta.get("closure_id") or closure_of.get(str(order.get("id"))) or "")
        if cid:
            return cid
        if not order.get("archived_at"):
            return "__live__"
        return None

    for order in orders:
        key = key_of(order)
        created = aware(order.get("created_at"))
        if key and created and (key not in first_created or created < first_created[key]):
            first_created[key] = created

    def by_closure(order: dict) -> date | None:
        key = key_of(order)
        start = opened.get(key) if key else None
        start = min(filter(None, [start, first_created.get(key)])) if key and (start or first_created.get(key)) else None
        start = start or aware(order.get("created_at"))
        return start.astimezone(tz).date() if start else None

    return by_closure


# --------------------------------------------------------------- costo ---
class Costing:
    def __init__(self, inventory: dict[str, dict], portions: dict[str, dict]):
        self.inventory = inventory
        self.portions = portions
        self.whole_of_group: dict[str, str] = {}
        for item_id, member in portions.items():
            if parse_fraction(member.get("portion_label")) == 1:
                self.whole_of_group[str(member.get("group_key"))] = item_id

    def family(self, item: dict) -> tuple[str, str, Fraction]:
        """(clave, nombre, fraccion de la unidad) del producto vendido."""
        item_id = str(item.get("inventory_item_id") or item.get("product_id") or "")
        qty = Fraction(str(dec(item.get("quantity") or 0))).limit_denominator(100)
        member = self.portions.get(item_id)
        if member:
            frac = parse_fraction(member.get("portion_label")) or Fraction(1)
            return f"grp:{member.get('group_key')}", str(member.get("group_label") or item.get("name") or ""), frac
        name = str((self.inventory.get(item_id) or {}).get("name") or item.get("name") or "Producto")
        label_frac = parse_fraction(item.get("quantity_label"))
        if label_frac and label_frac != 1:
            return f"inv:{item_id or name}", name, label_frac
        return f"inv:{item_id or name}", name, qty if 0 < qty < 1 else Fraction(1)

    def line(self, item: dict) -> dict:
        item_id = str(item.get("inventory_item_id") or item.get("product_id") or "")
        qty = dec(item.get("quantity") or 0)
        sale = dec(item.get("subtotal") if item.get("subtotal") is not None else dec(item.get("unit_price")) * qty)
        key, name, frac = self.family(item)
        entry = dec((self.inventory.get(item_id) or {}).get("entry_price"))
        cost, derived = None, False
        if entry > 0:
            cost = entry * qty
        else:
            member = self.portions.get(item_id)
            whole_id = self.whole_of_group.get(str(member.get("group_key"))) if member else None
            whole_entry = dec((self.inventory.get(whole_id) or {}).get("entry_price")) if whole_id else Decimal("0")
            portion = parse_fraction(member.get("portion_label")) if member else None
            if whole_entry > 0 and portion:
                cost = whole_entry * Decimal(portion.numerator) / Decimal(portion.denominator) * qty
                derived = True
        # unidades equivalentes: 1/4 de pollo vendido una vez = 0.25 pollos
        if key.startswith("grp:"):
            count = int(qty) if qty == int(qty) else qty
            equiv = frac * Fraction(str(count))
            pieces = Fraction(str(count))
        elif frac != 1 and item.get("quantity_label"):
            # boton 1/4: quantity = fraccion descontada (0.25; 0.5 si se unieron dos 1/4)
            equiv = Fraction(str(qty)).limit_denominator(100)
            pieces = equiv / frac
        else:
            equiv = Fraction(str(qty)).limit_denominator(100)
            pieces = Fraction(1) if 0 < equiv < 1 else equiv
        return {"key": key, "name": name, "sale": sale, "cost": cost, "derived": derived, "fraction": frac,
                "equiv": equiv, "pieces": pieces, "inventory_item_id": item_id, "qty": qty,
                "station": str(item.get("station") or ""), "created_at": item.get("created_at"),
                "ready_at": item.get("ready_at")}


# -------------------------------------------------------------- pedidos ---
def channel_of(order: dict) -> str:
    meta = as_dict(order.get("metadata"))
    if str(order.get("order_type") or "") == "domicilio":
        return "domicilio"
    if as_dict(meta.get("cashier_sale")).get("kind") == "independiente":
        return "venta_directa"
    if str(order.get("order_type") or "") == "bar_sale":
        return "barra"
    return "mesa"


CHANNEL_LABELS = {"mesa": "Mesa", "domicilio": "Domicilio", "venta_directa": "Venta directa en caja", "barra": "Barra"}
PAYMENT_LABELS = {"cash": "Efectivo", "transfer": "Transferencia", "card": "Tarjeta / datáfono", "qr": "QR",
                  "other": "Otro / sin registrar"}


def is_cancelled(order: dict) -> bool:
    return str(order.get("status") or "").lower() in {"cancelado", "cancelled", "canceled", "merma"}


def is_merma(order: dict) -> bool:
    meta = as_dict(order.get("metadata"))
    if "inventory_was_deducted" in meta:
        return bool(meta.get("inventory_was_deducted"))
    return bool(order.get("inventory_deducted"))


def accounts(orders: list[dict]) -> list[dict]:
    """Cuentas: una mesa desde que se abre hasta que se cierra (los pedidos
    que se cerraron juntos), un domicilio o una venta directa."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for order in orders:
        channel = channel_of(order)
        if channel == "mesa":
            closed = aware(order.get("closed_at"))
            key = ("mesa", str(order.get("table_key") or order.get("table_number") or ""),
                   order.get("_jornada"), closed.replace(microsecond=0).isoformat() if closed else "abierta")
        else:
            key = (channel, str(order.get("id")))
        groups[key].append(order)
    result = []
    for key, items in groups.items():
        first = min(items, key=lambda o: aware(o.get("created_at")) or datetime.max.replace(tzinfo=timezone.utc))
        closed = aware(items[0].get("closed_at")) if key[0] == "mesa" else None
        opened = aware(first.get("created_at"))
        waiter = as_dict(as_dict(first.get("metadata")).get("waiter"))
        result.append({
            "channel": key[0], "table": str(first.get("table_number") or ""), "jornada": first.get("_jornada"),
            "total": sum((dec(o.get("total")) for o in items), Decimal("0")), "orders": len(items),
            "opened_at": opened, "closed_at": closed,
            "minutes": int((closed - opened).total_seconds() // 60) if closed and opened and closed > opened else None,
            "waiter_id": str(waiter.get("id") or ""), "waiter_name": str(waiter.get("name") or ""),
            "cashier": bool(as_dict(first.get("metadata")).get("cashier_sale")),
            "payment_method": str(first.get("payment_method") or "other"),
        })
    return result


# ---------------------------------------------------------------- nucleo ---
class Report:
    def __init__(
        self, *, orders: list[dict], closures: list[dict], inventory: dict[str, dict], portions: dict[str, dict],
        tz: ZoneInfo, period: dict, business_day: dict | None = None, sessions: list[dict] | None = None,
        confirmed_ends: dict[str, Any] | None = None, now: datetime | None = None,
    ):
        self.tz = tz
        self.period = period
        self.costing = Costing(inventory, portions)
        self.inventory = inventory
        self.now = now or datetime.now(timezone.utc)
        jornada_of = jornada_resolver(orders, closures, tz, business_day)
        for order in orders:
            order["_jornada"] = jornada_of(order)
        self.orders = [o for o in orders if o.get("_jornada") and period["start"] <= o["_jornada"] <= period["end"]]
        self.prev_orders = [o for o in orders if o.get("_jornada") and period["prev_start"] <= o["_jornada"] <= period["prev_end"]]
        self.sales = [o for o in self.orders if not is_cancelled(o)]
        self.cancelled = [o for o in self.orders if is_cancelled(o)]
        self.sessions = sessions or []
        self.confirmed_ends = confirmed_ends or {}
        self._lines = None

    # --- lineas de producto
    def lines(self, orders: Iterable[dict] | None = None) -> list[dict]:
        if orders is None and self._lines is not None:
            return self._lines
        out = []
        for order in (self.sales if orders is None else orders):
            for item in as_list(order.get("items")):
                if isinstance(item, dict):
                    row = self.costing.line(item)
                    row["order"] = order
                    out.append(row)
        if orders is None:
            self._lines = out
        return out

    def _totals(self, sales_orders: list[dict], cancelled: list[dict], lines: list[dict]) -> dict:
        sales = sum((dec(o.get("total")) for o in sales_orders), Decimal("0"))
        accts = accounts(sales_orders)
        costed_sales = sum((l["sale"] for l in lines if l["cost"] is not None), Decimal("0"))
        cost = sum((l["cost"] for l in lines if l["cost"] is not None), Decimal("0"))
        uncosted_sales = sum((l["sale"] for l in lines if l["cost"] is None), Decimal("0"))
        merma_orders = [o for o in cancelled if is_merma(o)]
        merma_cost = sum((l["cost"] or Decimal("0") for l in self.lines(merma_orders)), Decimal("0"))
        return {
            "sales": sales, "accounts": len(accts), "orders": len(sales_orders),
            "ticket": (sales / len(accts)) if accts else Decimal("0"),
            "cost": cost, "costed_sales": costed_sales, "uncosted_sales": uncosted_sales,
            "margin": costed_sales - cost,
            "cost_pct": (cost / costed_sales * 100) if costed_sales else None,
            "cancelled_total": sum((dec(o.get("total")) for o in cancelled if not is_merma(o)), Decimal("0")),
            "cancelled_count": len([o for o in cancelled if not is_merma(o)]),
            "merma_total": sum((dec(o.get("total")) for o in merma_orders), Decimal("0")),
            "merma_cost": merma_cost, "merma_count": len(merma_orders),
        }

    # --- 1-2. indicadores
    def kpis(self) -> dict:
        cur = self._totals(self.sales, self.cancelled, self.lines())
        prev_sales = [o for o in self.prev_orders if not is_cancelled(o)]
        prev = self._totals(prev_sales, [o for o in self.prev_orders if is_cancelled(o)], self.lines(prev_sales))
        uncosted = {}
        for line in self.lines():
            if line["cost"] is None:
                row = uncosted.setdefault(line["key"], {"name": line["name"], "sales": Decimal("0")})
                row["sales"] += line["sale"]
        derived = sorted({l["name"] for l in self.lines() if l["derived"]})

        def card(key: str, label: str, value: Any, kind: str, better: str = "up") -> dict:
            current = float(value) if value is not None else None
            previous = prev.get(key)
            previous = float(previous) if previous is not None else None
            return {"key": key, "label": label, "value": current, "kind": kind, "previous": previous,
                    "change_pct": pct_change(current or 0, previous or 0) if current is not None else None,
                    "better": better}

        cards = [
            card("sales", "Ventas", cur["sales"], "money"),
            card("accounts", "Cuentas", cur["accounts"], "count"),
            card("ticket", "Ticket promedio", cur["ticket"], "money"),
            card("margin", "Margen bruto estimado", cur["margin"], "money"),
            card("cost_pct", "Costo de mercancía / venta", cur["cost_pct"], "pct", "down"),
            card("losses", "Mermas y cancelaciones", cur["cancelled_total"] + cur["merma_total"], "money", "down"),
        ]
        for c in cards:
            if c["key"] == "losses":
                c["previous"] = float(prev["cancelled_total"] + prev["merma_total"])
                c["change_pct"] = pct_change(c["value"], c["previous"])
        costed_share = (cur["costed_sales"] / (cur["costed_sales"] + cur["uncosted_sales"]) * 100) if (cur["costed_sales"] + cur["uncosted_sales"]) else None
        return {
            "cards": cards,
            "losses": {"cancelled_total": money(cur["cancelled_total"]), "cancelled_count": cur["cancelled_count"],
                       "merma_total": money(cur["merma_total"]), "merma_cost": money(cur["merma_cost"]),
                       "merma_count": cur["merma_count"]},
            "costing": {
                "complete": not uncosted,
                "uncosted_count": len(uncosted),
                "uncosted_sales": money(cur["uncosted_sales"]),
                "costed_share_pct": round(float(costed_share), 1) if costed_share is not None else None,
                "uncosted": [{"name": v["name"], "sales": money(v["sales"])}
                             for v in sorted(uncosted.values(), key=lambda v: v["sales"], reverse=True)],
                "derived": derived,
            },
            "_raw": cur, "_prev": prev,
        }

    # --- 3. venta y margen por dia + tabla de dias con movimiento (corr. c)
    def daily(self) -> dict:
        by_day: dict[date, dict] = {}
        for order in self.sales:
            row = by_day.setdefault(order["_jornada"], {"sales": Decimal("0"), "orders": 0})
            row["sales"] += dec(order.get("total"))
            row["orders"] += 1
        for line in self.lines():
            row = by_day.setdefault(line["order"]["_jornada"], {"sales": Decimal("0"), "orders": 0})
            if line["cost"] is not None:
                row["margin"] = row.get("margin", Decimal("0")) + line["sale"] - line["cost"]
        days = []
        cursor = self.period["start"]
        while cursor <= self.period["end"]:
            row = by_day.get(cursor, {})
            days.append({"date": cursor.isoformat(), "weekday": WEEKDAYS[cursor.weekday()], "sales": money(row.get("sales")),
                         "margin": money(row.get("margin")) if "margin" in row else None, "orders": row.get("orders", 0)})
            cursor += timedelta(days=1)
        with_sales = [d for d in days if d["sales"] > 0]
        return {"days": days, "table": with_sales, "idle_days": len(days) - len(with_sales)}

    # --- corr. a: dia mas movido solo con >= 3 repeticiones
    def busiest_weekday(self) -> dict:
        per_day: dict[date, Decimal] = defaultdict(Decimal)
        for order in self.sales:
            per_day[order["_jornada"]] += dec(order.get("total"))
        by_weekday: dict[int, list[Decimal]] = defaultdict(list)
        for day, total in per_day.items():
            if total > 0:
                by_weekday[day.weekday()].append(total)
        eligible = {wd: vals for wd, vals in by_weekday.items() if len(vals) >= MIN_WEEKDAY_REPEATS}
        if not eligible:
            return {"enough": False, "message": "Datos insuficientes, se necesitan al menos 3 semanas"}
        averages = {wd: sum(vals, Decimal("0")) / len(vals) for wd, vals in eligible.items()}
        best = max(averages, key=lambda wd: (averages[wd], -wd))
        worst = min(averages, key=lambda wd: (averages[wd], wd))
        return {"enough": True, "weekday": WEEKDAYS[best], "average": money(averages[best]), "days": len(eligible[best]),
                "plural": WEEKDAYS_PLURAL[best], "worst_weekday": WEEKDAYS[worst], "worst_average": money(averages[worst]),
                "averages": {WEEKDAYS[wd]: money(v) for wd, v in averages.items()}}

    # --- 4. mapa de calor: dia de la jornada x hora local del pedido
    def heatmap(self) -> dict:
        cells: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
        for order in self.sales:
            created = aware(order.get("created_at"))
            if not created:
                continue
            cells[(order["_jornada"].weekday(), created.astimezone(self.tz).hour)] += dec(order.get("total"))
        hours = sorted({h for _, h in cells})
        # orden de jornada: si hay horas de madrugada, van al final de la fila
        if hours:
            first = min(hours, key=lambda h: (h < 6, h))
            hours = sorted(hours, key=lambda h: (h - first) % 24)
        peak = max(cells.values(), default=Decimal("0"))
        return {"weekdays": WEEKDAYS, "hours": hours,
                "cells": [{"weekday": wd, "hour": h, "sales": money(v)} for (wd, h), v in sorted(cells.items())],
                "max": money(peak)}

    # --- 5. analisis de carta (+ corr. b: unidades enteras y porciones)
    def menu(self) -> dict:
        products: dict[str, dict] = {}
        for line in self.lines():
            row = products.setdefault(line["key"], {"name": line["name"], "units": Fraction(0), "sold": Fraction(0), "sales": Decimal("0"),
                                                    "cost": Decimal("0"), "costed": True, "derived": False,
                                                    "portions": defaultdict(Fraction)})
            row["units"] += line["equiv"]
            row["sold"] += line["pieces"]
            row["sales"] += line["sale"]
            row["derived"] = row["derived"] or line["derived"]
            if line["cost"] is None:
                row["costed"] = False
            else:
                row["cost"] += line["cost"]
            row["portions"][line["fraction"]] += line["pieces"]
        rows = []
        for key, row in products.items():
            units = row["units"]
            portions = {f: n for f, n in row["portions"].items() if n}
            breakdown = ""
            if len(portions) > 1 or any(f != 1 for f in portions):
                parts = []
                for f in sorted(portions, key=lambda f: f):
                    n = portions[f]
                    parts.append(f"{units_text(n)} {'entero' if f == 1 else 'de ' + fraction_text(f)}"
                                 f"{'s' if f == 1 and n > 1 else ''}")
                breakdown = ", ".join(parts)
            margin = (row["sales"] - row["cost"]) if row["costed"] else None
            units_dec = Decimal(units.numerator) / Decimal(units.denominator) if units else Decimal("0")
            # Carta: cada porción vendida es una venta (un 1/4 de pollo es un plato),
            # asi que popularidad y margen por unidad se miden por venta.
            sold = row["sold"]
            sold_dec = Decimal(sold.numerator) / Decimal(sold.denominator) if sold else Decimal("0")
            rows.append({
                "key": key, "name": row["name"], "units": float(units_dec), "units_text": units_text(units),
                "sold": float(sold_dec),
                "portions_text": breakdown, "sales": money(row["sales"]),
                "cost": money(row["cost"]) if row["costed"] else None,
                "margin_unit": money(margin / sold_dec) if margin is not None and sold_dec else None,
                "margin_total": money(margin) if margin is not None else None,
                "costed": row["costed"], "derived_cost": row["derived"],
            })
        costed = [r for r in rows if r["costed"] and r["sold"] > 0]
        quadrant_note = ""
        if len(costed) >= 3:
            total_units = sum(dec(r["sold"]) for r in costed)
            pop_line = (Decimal(1) / len(costed)) * POPULARITY_FACTOR
            avg_margin = sum(dec(r["margin_total"]) for r in costed) / total_units if total_units else Decimal("0")
            for r in costed:
                popular = (dec(r["sold"]) / total_units) >= pop_line if total_units else False
                profitable = dec(r["margin_unit"]) >= avg_margin
                r["quadrant"] = ("estrella" if popular and profitable else "vaca" if popular else
                                 "enigma" if profitable else "perro")
                r["share_pct"] = round(float(dec(r["sold"]) / total_units * 100), 1) if total_units else 0
            thresholds = {"popularity_share_pct": round(float(pop_line * 100), 1), "avg_margin_unit": money(avg_margin)}
        else:
            thresholds = None
            quadrant_note = "Se necesitan al menos 3 productos con costo para clasificar la carta."
        rows.sort(key=lambda r: r["sales"], reverse=True)
        return {"products": rows, "thresholds": thresholds, "note": quadrant_note}

    # --- 6. equipo y cocina
    def _worked_hours(self) -> tuple[dict[str, float], float]:
        hours: dict[str, float] = defaultdict(float)
        excluded = 0.0
        for s in self.sessions:
            start = aware(s.get("started_at"))
            if not start:
                continue
            if not (self.period["start"] <= start.astimezone(self.tz).date() <= self.period["end"]):
                continue
            reason = str(s.get("closed_reason") or "")
            seconds = float(s.get("active_seconds") or 0)
            if str(s.get("status") or "") in {"active", "break"}:
                active_from = aware(s.get("active_started_at"))
                if active_from:
                    seconds += max(0.0, (self.now - active_from).total_seconds())
            if reason in SYSTEM_CLOSE_REASONS:
                real_end = aware(self.confirmed_ends.get(str(s.get("id"))))
                if not real_end:
                    excluded += seconds / 3600
                    continue
                seconds = max(0.0, (real_end - start).total_seconds() - float(s.get("break_seconds") or 0))
            hours[str(s.get("user_id") or "")] += seconds / 3600
        return hours, excluded

    def team(self) -> dict:
        hours, excluded = self._worked_hours()
        waiters: dict[str, dict] = {}
        for acct in accounts(self.sales):
            if acct["cashier"] or not acct["waiter_id"]:
                continue
            row = waiters.setdefault(acct["waiter_id"], {"name": acct["waiter_name"] or "Mesero", "sales": Decimal("0"),
                                                         "tables": 0})
            row["sales"] += acct["total"]
            row["tables"] += 1
        rows = []
        for wid, row in waiters.items():
            h = hours.get(wid, 0.0)
            rows.append({"waiter_id": wid, "name": row["name"], "sales": money(row["sales"]), "tables": row["tables"],
                         "ticket": money(row["sales"] / row["tables"]) if row["tables"] else 0,
                         "hours": round(h, 1), "sales_per_hour": money(row["sales"] / Decimal(str(h))) if h >= 0.5 else None})
        rows.sort(key=lambda r: (r["sales_per_hour"] is None, -(r["sales_per_hour"] or 0), -r["sales"]))
        return {"waiters": rows, "excluded_hours": round(excluded, 1)}

    def kitchen(self) -> dict:
        by_product: dict[str, list[float]] = defaultdict(list)
        by_station: dict[str, list[float]] = defaultdict(list)
        order_delay: dict[str, float] = {}
        for line in self.lines():
            start = aware(line["created_at"]) or aware(line["order"].get("created_at"))
            ready = aware(line["ready_at"])
            if not start or not ready or ready < start:
                continue
            minutes = (ready - start).total_seconds() / 60
            by_product[line["name"]].append(minutes)
            by_station[line["station"] or "Sin estación"].append(minutes)
            oid = str(line["order"].get("id"))
            order_delay[oid] = max(order_delay.get(oid, 0.0), minutes)

        def stats(source: dict[str, list[float]]) -> list[dict]:
            return sorted([{"name": k, "avg_minutes": round(sum(v) / len(v), 1), "max_minutes": round(max(v), 1),
                            "count": len(v)} for k, v in source.items()], key=lambda r: -r["avg_minutes"])

        slow = len([m for m in order_delay.values() if m > SLOW_KITCHEN_MINUTES])
        return {"products": stats(by_product), "stations": stats(by_station), "comandas": len(order_delay),
                "slow_pct": round(slow / len(order_delay) * 100, 1) if order_delay else None,
                "slow_minutes": SLOW_KITCHEN_MINUTES}

    # --- 7. operacion (+ corr. d: mesas y domicilios separados)
    def operations(self) -> dict:
        accts = accounts(self.sales)
        channels: dict[str, dict] = {}
        for a in accts:
            row = channels.setdefault(a["channel"], {"sales": Decimal("0"), "accounts": 0})
            row["sales"] += a["total"]
            row["accounts"] += 1
        payments: dict[str, Decimal] = defaultdict(Decimal)
        for order in self.sales:
            payments[str(order.get("payment_method") or "other")] += dec(order.get("total"))
        tables = [a for a in accts if a["channel"] == "mesa"]
        durations = [a["minutes"] for a in tables if a["minutes"] is not None]
        per_jornada: dict[date, dict] = defaultdict(lambda: {"visits": 0, "tables": set()})
        for a in tables:
            per_jornada[a["jornada"]]["visits"] += 1
            per_jornada[a["jornada"]]["tables"].add(a["table"])
        rotations = [v["visits"] / len(v["tables"]) for v in per_jornada.values() if v["tables"]]
        top_tables: dict[str, Decimal] = defaultdict(Decimal)
        for a in tables:
            top_tables[a["table"]] += a["total"]
        deliveries = sorted([a for a in accts if a["channel"] == "domicilio"], key=lambda a: a["total"], reverse=True)
        return {
            "channels": [{"channel": k, "label": CHANNEL_LABELS.get(k, k), "sales": money(v["sales"]),
                          "accounts": v["accounts"], "ticket": money(v["sales"] / v["accounts"]) if v["accounts"] else 0}
                         for k, v in sorted(channels.items(), key=lambda kv: -kv[1]["sales"])],
            "payments": [{"method": k, "label": PAYMENT_LABELS.get(k, k), "sales": money(v)}
                         for k, v in sorted(payments.items(), key=lambda kv: -kv[1])],
            "avg_table_minutes": round(sum(durations) / len(durations)) if durations else None,
            "rotation_per_jornada": round(sum(rotations) / len(rotations), 1) if rotations else None,
            "top_tables": [{"name": k, "sales": money(v)} for k, v in sorted(top_tables.items(), key=lambda kv: -kv[1])[:6]],
            "top_deliveries": [{"name": a["table"] or "Domicilio", "sales": money(a["total"])} for a in deliveries[:6]],
        }

    # --- 8. inventario y compras
    def inventory_report(self) -> dict:
        sold: dict[str, Decimal] = defaultdict(Decimal)
        for line in self.lines():
            if line["inventory_item_id"]:
                sold[line["inventory_item_id"]] += line["qty"]
        days = Decimal(max(1, self.period["days"]))
        value = Decimal("0")
        uncosted = 0
        coverage, idle = [], []
        for item_id, item in self.inventory.items():
            stock = dec(item.get("current_stock"))
            entry = dec(item.get("entry_price"))
            if stock > 0:
                if entry > 0:
                    value += stock * entry
                else:
                    uncosted += 1
            rate = sold.get(item_id, Decimal("0")) / days
            if rate > 0:
                cover = stock / rate if stock > 0 else Decimal("0")
                coverage.append({"name": item.get("name") or "Producto", "stock": float(stock), "daily": round(float(rate), 2),
                                 "days": round(float(cover), 1)})
            elif stock > 0:
                idle.append({"name": item.get("name") or "Producto", "stock": float(stock),
                             "value": money(stock * entry) if entry > 0 else None})
        coverage.sort(key=lambda r: r["days"])
        return {"value": money(value), "uncosted_items": uncosted, "coverage": coverage,
                "buy_today": [r for r in coverage if r["days"] < BUY_WITHIN_DAYS],
                "idle": sorted(idle, key=lambda r: -(r["value"] or 0))}

    # --- 9. lecturas automaticas (solo con datos suficientes)
    def readings(self, kpis: dict | None = None, menu: dict | None = None, inventory: dict | None = None) -> list[str]:
        kpis = kpis or self.kpis()
        out: list[str] = []
        cur, prev = kpis["_raw"], kpis["_prev"]
        if prev["sales"] > 0 and cur["sales"] > 0:
            change = pct_change(float(cur["sales"]), float(prev["sales"]))
            if change is not None and abs(change) >= 10:
                text_ = f"Vendiste {abs(change):.0f}% {'más' if change > 0 else 'menos'} que en el periodo anterior"
                m_change = pct_change(float(cur["margin"]), float(prev["margin"])) if prev["margin"] else None
                if m_change is not None and (m_change > 0) != (change > 0) and abs(m_change) >= 5:
                    text_ += f", pero el margen {'subió' if m_change > 0 else 'bajó'} {abs(m_change):.0f}%"
                out.append(text_ + ".")
        busy = self.busiest_weekday()
        if busy["enough"] and busy["worst_average"] > 0 and busy["weekday"] != busy["worst_weekday"]:
            ratio = busy["average"] / busy["worst_average"]
            if ratio >= 1.5:
                times = "el doble de" if 1.9 <= ratio < 2.1 else f"{ratio:.1f}".rstrip("0").rstrip(".") + " veces lo"
                out.append(f"El {busy['weekday'].lower()} vendes {times} del {busy['worst_weekday'].lower()}.")
        menu = menu or self.menu()
        costed = [p for p in menu["products"] if p["costed"] and p["margin_unit"] is not None and p["sold"] > 0]
        if len(costed) >= 3:
            top = max(costed, key=lambda p: p["sold"])
            low = min(costed, key=lambda p: p["margin_unit"])
            high = max(costed, key=lambda p: p["margin_unit"])
            if top["key"] == low["key"]:
                out.append(f"{top['name']} es tu producto más vendido pero el de menor margen.")
            elif top["key"] == high["key"]:
                out.append(f"{top['name']} es tu producto más vendido y el de mayor margen: protégelo.")
        losses = self.cancelled
        loss_total = cur["cancelled_total"] + cur["merma_total"]
        if len(losses) >= 3 and loss_total > 0:
            by_hour: dict[int, Decimal] = defaultdict(Decimal)
            for order in losses:
                at = aware(order.get("cancelled_at") or order.get("updated_at") or order.get("created_at"))
                if at:
                    by_hour[at.astimezone(self.tz).hour] += dec(order.get("total"))
            text_ = f"Se cancelaron {money_text(loss_total)} en {len(losses)} pedidos"
            if by_hour:
                hour, value = max(by_hour.items(), key=lambda kv: kv[1])
                if value / loss_total >= Decimal("0.6"):
                    text_ += f", casi todo entre las {hour_text(hour)} y las {hour_text((hour + 1) % 24)}"
            out.append(text_ if text_.endswith(".") else text_ + ".")
        costing = kpis["costing"]
        if costing["uncosted_count"] and costing["costed_share_pct"] is not None and costing["costed_share_pct"] < 80:
            out.append(f"El {100 - costing['costed_share_pct']:.0f}% de tu venta es de productos sin precio de entrada: "
                       "el margen está incompleto.")
        inventory = inventory or self.inventory_report()
        if inventory["buy_today"]:
            names = [r["name"] for r in inventory["buy_today"][:3]]
            joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]
            out.append(f"Se acaban en menos de 3 días: {joined}.")
        return out[:4]


def money_text(value: Any) -> str:
    return "$" + f"{int(round(float(dec(value)))):,}".replace(",", ".")


def hour_text(hour: int) -> str:
    suffix = "a.m." if hour < 12 else "p.m."
    shown = hour % 12 or 12
    return f"{shown} {suffix}"


def public(data: Any) -> Any:
    """Sin claves internas (_raw, _prev) y con fechas en texto."""
    if isinstance(data, dict):
        return {k: public(v) for k, v in data.items() if not str(k).startswith("_")}
    if isinstance(data, list):
        return [public(v) for v in data]
    if isinstance(data, Decimal):
        return money(data)
    if isinstance(data, (date, datetime)):
        return data.isoformat()
    return data
