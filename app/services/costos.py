"""Modulo COSTOS (049I): reglas puras de egresos, aprobaciones, presupuesto,
variacion de precios y ARQUEO de caja.

Arqueo a ciegas: el cajero digita lo que cuenta SIN ver lo esperado; el
sistema registra el conteo (ya no se puede cambiar) y solo entonces revela lo
esperado y la diferencia. Lo esperado queda guardado con el arqueo aunque el
cajero no lo haya visto, para que el historico de faltantes sea auditable.

    esperado = base del cajon
             + ventas en efectivo del turno (mesas, domicilios, ventas directas)
             - gastos pagados con efectivo del cajon
             - retiros de efectivo del cajon (p. ej. el dueño saca plata)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

MONEY = Decimal("0.01")

CATEGORIES = {
    "compras": "Compra de insumos",
    "emergencia": "Compra de emergencia",
    "arriendo": "Arriendo",
    "servicios": "Servicios públicos",
    "internet": "Internet y telefonía",
    "seguros": "Seguros",
    "impuestos": "Impuestos",
    "mantenimiento": "Mantenimiento",
    "aseo": "Aseo",
    "retiro_dueno": "Retiro del dueño",
    "otros": "Otros",
}
PAYMENT_METHODS = {"efectivo": "Efectivo", "transferencia": "Transferencia", "tarjeta": "Tarjeta", "credito": "Crédito (por pagar)"}
PAID_FROM = {"cajon": "Efectivo del cajón de ventas", "caja_chica": "Caja chica", "banco": "Banco", "credito": "Por pagar"}
DENOMINATIONS = [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50]
DEFAULT_SETTINGS = {"approval_threshold": 500000, "drawer_base": 0, "iva_is_cost": True, "attachments_quota_mb": 40}

OWNER_ROLES = {"company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"}
MANAGER_ROLES = OWNER_ROLES | {"administrador", "gerente", "gerencia", "manager"}
CASHIER_ROLES = {"caja", "cajero", "cajera", "cashier"}


def dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else 0))
    except Exception:
        return Decimal("0")


def money(value: Any) -> Decimal:
    return dec(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def settings_of(raw: Any) -> dict:
    data = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        for key in DEFAULT_SETTINGS:
            if key in raw and raw[key] is not None:
                data[key] = raw[key]
    data["approval_threshold"] = float(money(data["approval_threshold"]))
    data["drawer_base"] = float(money(data["drawer_base"]))
    data["iva_is_cost"] = bool(data["iva_is_cost"])
    return data


def totals(subtotal: Any, iva: Any, retention: Any) -> dict:
    """Total pagado = subtotal + IVA - retencion (la retencion se le descuenta
    al proveedor y se paga a la DIAN)."""
    sub, tax, ret = money(subtotal), money(iva), money(retention)
    if sub < 0 or tax < 0 or ret < 0:
        raise ValueError("valores_negativos")
    total = sub + tax - ret
    if total < 0:
        raise ValueError("retencion_mayor_al_valor")
    return {"subtotal": sub, "iva": tax, "retention": ret, "total": total}


def role_kind(role: Any, *, admin_v2: bool = False) -> str:
    clean = str(role or "").strip().lower()
    if admin_v2 or clean in OWNER_ROLES:
        return "owner"
    if clean in MANAGER_ROLES:
        return "manager"
    if clean in CASHIER_ROLES:
        return "cashier"
    return "other"


def initial_status(kind: str, total: Any, threshold: Any) -> str:
    """Dueño: aprobado. Administrador: aprobado salvo que pase el tope (va al
    dueño). Cajero: siempre pendiente."""
    if kind == "owner":
        return "aprobado"
    if kind == "manager":
        return "pendiente" if money(total) > money(threshold) else "aprobado"
    return "pendiente"


def can_approve(kind: str, total: Any, threshold: Any) -> bool:
    if kind == "owner":
        return True
    return kind == "manager" and money(total) <= money(threshold)


def expected_cash(base: Any, cash_sales: Any, drawer_expenses: Any, withdrawals: Any) -> Decimal:
    return money(dec(base) + dec(cash_sales) - dec(drawer_expenses) - dec(withdrawals))


def count_from_denominations(denominations: dict | None) -> Decimal | None:
    if not denominations:
        return None
    total = Decimal("0")
    for value, qty in denominations.items():
        if int(value) not in DENOMINATIONS or int(qty) < 0:
            raise ValueError("denominacion_invalida")
        total += Decimal(int(value)) * int(qty)
    return money(total)


def difference_label(difference: Any) -> str:
    diff = money(difference)
    if diff == 0:
        return "cuadrado"
    return "sobrante" if diff > 0 else "faltante"


def budget_status(budgets: dict[str, Any], real: dict[str, Any]) -> list[dict]:
    rows = []
    for category in sorted(set(budgets) | set(real)):
        budget = money(budgets.get(category))
        spent = money(real.get(category))
        rows.append({
            "category": category, "label": CATEGORIES.get(category, category),
            "budget": float(budget), "real": float(spent),
            "pct": float((spent / budget * 100).quantize(Decimal("0.1"))) if budget > 0 else None,
            "over": bool(budget > 0 and spent > budget),
        })
    return rows


def price_variation(purchases: Iterable[dict]) -> list[dict]:
    """Compras de un insumo en orden: precio por unidad de consumo y cambio
    contra la compra anterior (cualquier proveedor)."""
    rows = sorted(purchases, key=lambda r: (str(r["date"]), str(r.get("created_at") or "")))
    out, previous = [], None
    for row in rows:
        unit = money(row["unit_cost"]) if dec(row["unit_cost"]) >= 1 else dec(row["unit_cost"]).quantize(Decimal("0.0001"))
        change = None
        if previous and previous > 0:
            change = float(((dec(unit) - previous) / previous * 100).quantize(Decimal("0.1")))
        out.append({**row, "unit_cost": float(unit), "change_pct": change})
        previous = dec(unit)
    return out


def due_this_week(due: date | None, today: date) -> bool:
    return bool(due and due <= today + timedelta(days=7))


def recurring_due(day_of_month: int, last_month: str | None, today: date) -> bool:
    month = today.strftime("%Y-%m")
    return (last_month or "") != month and today.day >= max(1, min(28, int(day_of_month or 1)))
