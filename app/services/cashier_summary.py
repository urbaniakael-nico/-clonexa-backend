"""Caja (049V): indicadores del turno y el Z del dia. Motor puro.

- Indicadores del turno (franja de arriba del panel de caja): los pedidos del
  turno del cajero = los creados o cobrados desde que abrio su turno. Vendido
  = cobrado + por cobrar (nunca cancelados), y el desglose por metodo de pago
  es de lo YA cobrado, asi las cifras cuadran entre si. Cuentas y mesas
  atendidas con la misma regla de Reportes (una mesa desde que se abre hasta
  que se cierra = una cuenta).
- Z (cierre de caja del dia): lo cobrado en la jornada de hoy: numero de
  ventas, productos vendidos, total en dinero y desglose por metodo (efectivo,
  transferencia, tarjeta). Lo que sigue abierto y lo cancelado se informan
  aparte, sin sumar al total.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable

from app.services import owner_report as report
from app.services import sales_ledger as ledger

METHOD_LABELS = {"cash": "Efectivo", "transfer": "Transferencia", "card": "Tarjeta", "other": "Otro"}
MAIN_METHODS = ("cash", "transfer", "card")


def _dec(value: Any) -> Decimal:
    return report.dec(value)


def _sum(orders: Iterable[dict]) -> Decimal:
    return sum((_dec(o.get("total")) for o in orders), Decimal("0"))


def method_of(order: dict) -> str:
    """El pago por QR de un domicilio se cierra como transferencia."""
    method = str(order.get("payment_method") or "other").lower()
    if method == "qr":
        return "transfer"
    return method if method in METHOD_LABELS else "other"


def is_paid(order: dict) -> bool:
    return ledger.is_paid(order)


def is_direct_sale(order: dict) -> bool:
    return bool(report.as_dict(order.get("metadata")).get("cashier_sale"))


def methods(paid: list[dict]) -> list[dict]:
    """Efectivo, transferencia y tarjeta siempre (aunque sea en 0); "Otro"
    solo si hubo algo cobrado asi."""
    totals = {key: Decimal("0") for key in METHOD_LABELS}
    counts = {key: 0 for key in METHOD_LABELS}
    for order in paid:
        key = method_of(order)
        totals[key] += _dec(order.get("total"))
        counts[key] += 1
    return [{"method": key, "label": METHOD_LABELS[key], "total": report.money(totals[key]), "count": counts[key]}
            for key in METHOD_LABELS if key in MAIN_METHODS or counts[key]]


def _is_fee(item: dict) -> bool:
    """El valor del domicilio se cobra, pero no es un producto vendido."""
    return str(item.get("station") or "").strip().lower() == "domicilio"


def line_units(item: dict) -> Decimal:
    """Productos de una linea: "2 x gaseosa" = 2; "3/4 de pollo" = 1 (una
    porcion es un producto vendido, no 0,75)."""
    qty = _dec(item.get("quantity"))
    if qty <= 0:
        return Decimal("0")
    return qty if qty == qty.to_integral_value() else Decimal("1")


def _lines(orders: Iterable[dict]) -> list[dict]:
    return [i for o in orders for i in report.as_list(o.get("items")) if isinstance(i, dict) and not _is_fee(i)]


def product_rows(orders: Iterable[dict]) -> list[dict]:
    """Productos vendidos agrupados por nombre (para el Z impreso)."""
    rows: dict[str, dict] = {}
    for item in _lines(orders):
        name = str(item.get("name") or "Producto").strip() or "Producto"
        row = rows.setdefault(name.lower(), {"name": name, "units": Decimal("0"), "total": Decimal("0")})
        row["units"] += line_units(item)
        subtotal = item.get("subtotal")
        row["total"] += _dec(subtotal) if subtotal is not None else _dec(item.get("unit_price")) * _dec(item.get("quantity"))
    ordered = sorted(rows.values(), key=lambda r: (-r["units"], r["name"].lower()))
    return [{"name": r["name"], "units": float(r["units"]), "total": report.money(r["total"])} for r in ordered]


def in_shift(order: dict, since: datetime | None) -> bool:
    if since is None:
        return True
    created = report.aware(order.get("created_at"))
    closed = report.aware(order.get("closed_at"))
    return bool((created and created >= since) or (closed and closed >= since))


def _direct_label(order: dict) -> str:
    tail = str(order.get("order_number") or "").rsplit("-", 1)[-1].strip()
    table = str(order.get("table_number") or "").strip()
    if table and not table.lower().startswith("venta"):
        return table
    return table or (f"Venta {tail}" if tail else "Venta caja")


def _iso(value: Any) -> str | None:
    moment = report.aware(value)
    return moment.isoformat() if moment else None


def direct_sale_row(order: dict) -> dict:
    sale = report.as_dict(report.as_dict(order.get("metadata")).get("cashier_sale"))
    paid = is_paid(order)
    return {
        "id": str(order.get("id")),
        "label": _direct_label(order),
        "kind": str(sale.get("kind") or ""),
        "to_kitchen": bool(sale.get("send_to_kitchen")),
        "total": report.money(order.get("total")),
        "status": str(order.get("status") or ""),
        "paid": paid,
        "method": method_of(order) if paid else None,
        "method_label": METHOD_LABELS[method_of(order)] if paid else None,
        "created_at": _iso(order.get("created_at")),
        "closed_at": _iso(order.get("closed_at")),
        "cashier": str(report.as_dict(sale.get("by")).get("name") or ""),
        "products": float(sum((line_units(i) for i in _lines([order])), Decimal("0"))),
    }


def delivery_row(order: dict) -> dict:
    """049Y: un domicilio cobrado en el turno (para reimprimir su cuenta)."""
    delivery = report.as_dict(report.as_dict(order.get("metadata")).get("delivery"))
    tail = str(order.get("order_number") or "").rsplit("-", 1)[-1].strip()
    return {
        "id": str(order.get("id")),
        "label": f"Domicilio {tail}" if tail else str(order.get("table_number") or "Domicilio"),
        "customer": str(delivery.get("customer_name") or ""),
        "total": report.money(order.get("total")),
        "method": method_of(order),
        "method_label": METHOD_LABELS[method_of(order)],
        "closed_at": _iso(order.get("closed_at")),
    }


def _tail(order: dict) -> str:
    return str(order.get("order_number") or "").rsplit("-", 1)[-1].strip()


def _item_rows(orders: list[dict]) -> list[dict]:
    rows = []
    for item in (i for o in orders for i in report.as_list(o.get("items")) if isinstance(i, dict)):
        subtotal = item.get("subtotal")
        amount = _dec(subtotal) if subtotal is not None else _dec(item.get("unit_price")) * _dec(item.get("quantity"))
        qty = item.get("quantity_label") or f"{float(_dec(item.get('quantity'))):g}"
        rows.append({"qty": str(qty), "name": str(item.get("name") or "Producto"), "subtotal": report.money(amount)})
    return rows


def charged_accounts(paid: list[dict]) -> list[dict]:
    """049Z: lo YA cobrado del turno, una fila por cuenta (una mesa desde que
    se abre hasta que se cobra = una cuenta, como en Reportes), con lo que el
    buscador de la caja necesita: numero, monto, cliente, metodo y detalle
    para reimprimir. Lo mas reciente primero."""
    groups: dict[tuple, list[dict]] = {}
    for order in paid:
        channel = report.channel_of(order)
        if channel == "mesa":
            closed = report.aware(order.get("closed_at"))
            key = ("mesa", str(order.get("table_key") or order.get("table_number") or ""),
                   closed.replace(microsecond=0).isoformat() if closed else "")
        else:
            key = (channel, str(order.get("id")))
        groups.setdefault(key, []).append(order)
    rows = []
    for (channel, _ref, *_rest), orders in groups.items():
        first = orders[0]
        meta = report.as_dict(first.get("metadata"))
        delivery = report.as_dict(meta.get("delivery"))
        numbers = [t for t in (_tail(o) for o in orders) if t]
        if channel == "domicilio":
            label = f"Domicilio {numbers[0]}" if numbers else "Domicilio"
        elif channel == "venta_directa":
            label = _direct_label(first)
        else:
            label = str(first.get("table_number") or "Mesa")
        closed = max((report.aware(o.get("closed_at")) for o in orders if report.aware(o.get("closed_at"))), default=None)
        document = report.as_dict(meta.get("sale_document"))
        rows.append({
            "key": "|".join(sorted(str(o.get("id")) for o in orders)),
            "order_ids": [str(o.get("id")) for o in orders],
            "label": label,
            "channel": channel,
            "channel_label": report.CHANNEL_LABELS.get(channel, channel),
            "numbers": numbers,
            "document_number": str(document.get("number") or ""),
            "customer": str(delivery.get("customer_name") or first.get("customer_name") or ""),
            "waiter": str(report.as_dict(meta.get("waiter")).get("name") or ""),
            "total": report.money(_sum(orders)),
            "method": method_of(first),
            "method_label": METHOD_LABELS[method_of(first)],
            "closed_at": closed.isoformat() if closed else None,
            "items": _item_rows(orders),
        })
    return sorted(rows, key=lambda r: str(r["closed_at"] or ""), reverse=True)


def window(orders: list[dict], since: datetime | None) -> dict:
    """049W: el UNICO filtro de pedidos de la caja. Indicadores y Z parten de
    aqui, asi el Z suma exactamente lo que el panel muestra como cobrado."""
    inside = [o for o in orders if in_shift(o, since)]
    rows = [o for o in inside if not report.is_cancelled(o)]
    return {
        "rows": rows,
        "paid": [o for o in rows if is_paid(o)],
        "pending": [o for o in rows if not is_paid(o)],
        "cancelled": [o for o in inside if report.is_cancelled(o)],
    }


def shift_summary(orders: list[dict], since: datetime | None) -> dict:
    """La franja de indicadores: lo del turno abierto del cajero."""
    w = window(orders, since)
    rows, paid, pending = w["rows"], w["paid"], w["pending"]
    sold = _sum(rows)
    accts = report.accounts(rows)
    direct = [o for o in rows if is_direct_sale(o) and report.channel_of(o) == "venta_directa"]
    return {
        "since": since.isoformat() if since else None,
        "sold": report.money(sold),
        "charged": report.money(_sum(paid)),
        "pending": report.money(_sum(pending)),
        "orders": len(rows),
        "accounts": len(accts),
        "ticket": report.money(sold / len(accts)) if accts else 0.0,
        "deliveries": len([o for o in rows if report.channel_of(o) == "domicilio"]),
        "tables": len([a for a in accts if a["channel"] == "mesa"]),
        "direct_count": len(direct),
        "methods": methods(paid),
        "direct_sales": [direct_sale_row(o) for o in sorted(direct, key=lambda o: str(_iso(o.get("created_at")) or ""), reverse=True)],
        "charged_accounts": charged_accounts(paid),
        "deliveries_paid": [delivery_row(o) for o in sorted(
            (o for o in paid if report.channel_of(o) == "domicilio"),
            key=lambda o: str(_iso(o.get("closed_at")) or ""), reverse=True)],
    }


def z_report(orders: list[dict], since: datetime | None = None) -> dict:
    """El Z: lo cobrado en la ventana de la caja (la misma de los indicadores),
    cuantos productos y por que metodo."""
    w = window(orders, since)
    paid, open_orders, cancelled = w["paid"], w["pending"], w["cancelled"]
    units = sum((line_units(i) for i in _lines(paid)), Decimal("0"))
    by_channel: dict[str, dict] = {}
    for account in report.accounts(paid):
        row = by_channel.setdefault(account["channel"], {"channel": account["channel"],
                                                          "label": report.CHANNEL_LABELS.get(account["channel"], account["channel"]),
                                                          "count": 0, "total": Decimal("0")})
        row["count"] += 1
        row["total"] += account["total"]
    return {
        "sales": len(report.accounts(paid)),
        "orders": len(paid),
        "products": float(units),
        "total": report.money(_sum(paid)),
        "methods": methods(paid),
        "channels": [{**r, "total": report.money(r["total"])} for r in by_channel.values()],
        "items": product_rows(paid),
        "open_count": len(open_orders),
        "open_total": report.money(_sum(open_orders)),
        "cancelled_count": len(cancelled),
        "cancelled_total": report.money(_sum(cancelled)),
    }
