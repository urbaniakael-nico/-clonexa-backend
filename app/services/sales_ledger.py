"""La venta, leida de UNA sola forma (049Z).

Tres veces la misma falla: la cocina que no veia comandas, el Z en $0 y los
Reportes vacios. Cada pantalla decidia por su cuenta que pedidos eran "venta"
y de que dia. En Reportes, sin horario de jornada, la jornada en curso tomaba
la fecha del pedido MAS ANTIGUO sin "cierre de dia" de hospitality; el
Asadero cierra con el Z (no con ese cierre), asi que las ventas de hoy
quedaban fechadas dias atras y hoy/ayer salian vacios.

Reglas (las usan el panel de caja, el Z y Reportes):
- Pedido: una fila de hospitality_orders (mesa, venta directa de caja y
  domicilio son todos pedidos; channel_of dice cual es).
- Venta: todo pedido no cancelado. Cobrada: status "cerrado".
- Momento de la venta: cuando se cobro (closed_at); si aun no se cobra,
  cuando se creo.
- Dia de la venta: la fecha local de ese momento; con horario de jornada que
  cruza la medianoche, lo cobrado antes del cierre es del dia anterior.
- Se leen los pedidos CREADOS o COBRADOS en la ventana (una mesa abierta ayer
  y cobrada hoy es venta de hoy).

Interruptor por empresa: "sales_ledger" del modulo waiter_ordering (hoy
ASADERO). Apagado, Reportes calcula la jornada como antes.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FLAG = "sales_ledger"
CANCELLED = {"cancelado", "cancelled", "canceled", "merma"}
PAID = "cerrado"
ORDER_COLUMNS = (
    "id, order_number, created_at, updated_at, closed_at, cancelled_at, archived_at, status, order_type, source, "
    "table_key, table_number, customer_name, payment_method, total, items, metadata, inventory_deducted"
)


def _aware(value: Any) -> datetime | None:
    from app.services.owner_report import aware

    return aware(value)


def is_cancelled(order: dict) -> bool:
    return str(order.get("status") or "").lower() in CANCELLED


def is_sale(order: dict) -> bool:
    return not is_cancelled(order)


def is_paid(order: dict) -> bool:
    return str(order.get("status") or "").lower() == PAID


def sale_moment(order: dict) -> datetime | None:
    """Cuando cuenta la venta: al cobrarse; si sigue abierta, al crearse."""
    closed = _aware(order.get("closed_at")) if is_paid(order) else None
    return closed or _aware(order.get("created_at"))


def business_date(moment: datetime, tz: ZoneInfo, business_day: dict | None = None) -> date:
    local = moment.astimezone(tz)
    if business_day and business_day.get("overnight") and local.time() < business_day["close"]:
        return local.date() - timedelta(days=1)
    return local.date()


def sale_day(order: dict, tz: ZoneInfo, business_day: dict | None = None) -> date | None:
    moment = sale_moment(order)
    return business_date(moment, tz, business_day) if moment else None


def day_resolver(tz: ZoneInfo, business_day: dict | None = None) -> Callable[[dict], date | None]:
    return lambda order: sale_day(order, tz, business_day)


async def load_orders(db: AsyncSession, company_id: Any, start: datetime, end: datetime | None = None) -> list[dict]:
    """Los pedidos creados o cobrados en [start, end) de ESTA empresa."""
    params: dict[str, Any] = {"company_id": str(company_id), "start": start}
    created, closed = "created_at >= :start", "closed_at >= :start"
    if end is not None:
        params["end"] = end
        created, closed = f"{created} AND created_at < :end", f"{closed} AND closed_at < :end"
    result = await db.execute(text(f"""
        SELECT {ORDER_COLUMNS} FROM hospitality_orders
        WHERE company_id = CAST(:company_id AS uuid) AND (({created}) OR ({closed}))
    """), params)
    return [dict(row) for row in result.mappings().all()]


async def enabled(db: AsyncSession, company_id: Any) -> bool:
    try:
        row = (await db.execute(text("""
            SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:company_id AS uuid) AND LOWER(m.code) = 'waiter_ordering' AND cm.enabled IS TRUE
            LIMIT 1
        """), {"company_id": str(company_id)})).mappings().first()
    except Exception:
        return False
    raw = (row or {}).get("settings") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            return False
    return isinstance(raw, dict) and raw.get(FLAG) is True
