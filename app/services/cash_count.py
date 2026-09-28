"""Arqueo de caja a ciegas (049M; antes vivia en el modulo Costos, 049I).

El cajero digita lo que cuenta SIN ver lo esperado; el sistema registra el
conteo (ya no se puede cambiar: trigger de la tabla cash_counts) y solo
entonces revela lo esperado y la diferencia. Lo esperado queda guardado con
el arqueo aunque el cajero no lo haya visto, para que el historico de
faltantes sea auditable.

    esperado = base del cajon
             + ventas en efectivo del turno (mesas, domicilios, ventas directas)
             - gastos pagados con efectivo del cajon (historico de Costos)
             - retiros de efectivo del cajon (historico de Costos)
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

MONEY = Decimal("0.01")
DENOMINATIONS = [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50]
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


def role_kind(role: Any, *, admin_v2: bool = False) -> str:
    clean = str(role or "").strip().lower()
    if admin_v2 or clean in OWNER_ROLES:
        return "owner"
    if clean in MANAGER_ROLES:
        return "manager"
    if clean in CASHIER_ROLES:
        return "cashier"
    return "other"


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
