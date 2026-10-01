"""Pulso de todas las empresas para la consola maestra (Admin V2 / V2+).

El Dashboard viejo hacia 5 + 6xN peticiones y solo miraba ventas, cotizaciones,
notas y referencias de los mini paneles: ASADERO y The Time Machine salian
"Sin actividad" aunque vendieran, y la "Ultima señal" caia en
companies.updated_at, que no es actividad real.

Aqui todo sale en pocas consultas agregadas (una por fuente, nunca una por
empresa):
- Ventas: hospitality_orders, sin cancelados/merma. El momento de la venta es
  el de app/services/sales_ledger.py: closed_at si se cobro (cerrado); si no,
  created_at. "Hoy" es el dia en America/Bogota.
- Mini paneles: registros de venta y cotizaciones (si las tablas existen).
- Sesiones: clonexa_access_sessions por empresa.
- Ultima señal real: lo mas reciente entre ventas, mini paneles y sesiones.
  NUNCA updated_at.

Semaforo (calculado aqui, no en la pantalla), en este orden:
- operando: hubo venta u operacion de mini panel hoy.
- riesgo: la empresa esta inactiva pero con modulos encendidos, o esta activa
  sin un dueño con acceso.
- dormida: activa y su ultima señal real tiene mas de 7 dias (o nunca tuvo).
- sin_operacion_hoy: activa, sin operacion hoy, pero con señal real en los
  ultimos 7 dias.
- inactiva: SOLO empresas con status inactivo (y sin modulos encendidos; con
  modulos es riesgo).
Una tabla que no existe cuenta como 0: nunca rompe el endpoint.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales_ledger import CANCELLED, PAID

BOGOTA = ZoneInfo("America/Bogota")
DORMANT_DAYS = 7
OWNER_ROLES = ("company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario")
TABLES = ("hospitality_orders", "company_modules", "modules", "company_package_assignments", "packages",
          "mini_panel_sales_records", "mini_panel_quotes", "clonexa_access_sessions", "company_users")


def bogota_day_bounds(now: datetime) -> tuple[date, datetime, datetime]:
    """El dia de hoy en Bogota y sus limites en UTC."""
    today = now.astimezone(BOGOTA).date()
    start = datetime.combine(today, time.min, BOGOTA).astimezone(timezone.utc)
    return today, start, start + timedelta(days=1)


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _money(value: Any) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def _iso(value: Any) -> str | None:
    moment = _aware(value)
    return moment.isoformat() if moment else None


def _ago(moment: datetime | None, now: datetime) -> str:
    if moment is None:
        return "Sin señales reales"
    days = (now.astimezone(BOGOTA).date() - moment.astimezone(BOGOTA).date()).days
    if days <= 0:
        return "Hoy"
    if days == 1:
        return "Ayer"
    return f"Hace {days} días"


def classify(company: dict, now: datetime) -> tuple[str, str]:
    """(estado, motivo) de una empresa ya agregada."""
    active = str(company.get("status") or "").lower() == "active"
    modules = int(company.get("modules_enabled") or 0)
    signal = _aware(company.get("_signal"))
    if company.get("orders_today") or company.get("mini_panel_today"):
        parts = []
        if company.get("orders_today"):
            parts.append(f"{company['orders_today']} venta(s) hoy")
        if company.get("mini_panel_today"):
            parts.append(f"{company['mini_panel_today']} registro(s) de mini panel hoy")
        return "operando", " · ".join(parts)
    if not active and modules:
        return "riesgo", f"Inactiva con {modules} módulo{'s' if modules != 1 else ''}"
    if active and not company.get("owners_with_access"):
        return "riesgo", "Activa sin dueño con acceso"
    if active and (signal is None or now - signal > timedelta(days=DORMANT_DAYS)):
        return "dormida", _ago(signal, now)
    if not active:
        return "inactiva", "Inactiva sin módulos"
    return "sin_operacion_hoy", f"Última señal {_ago(signal, now).lower()}"


async def _existing(db: AsyncSession) -> set[str]:
    rows = (await db.execute(text(
        "SELECT name FROM unnest(CAST(:names AS text[])) AS name WHERE to_regclass('public.' || name) IS NOT NULL"
    ), {"names": list(TABLES)})).mappings().all()
    return {str(r["name"]) for r in rows}


async def _rows(db: AsyncSession, sql: str, params: dict | None = None) -> list[dict]:
    return [dict(r) for r in (await db.execute(text(sql), params or {})).mappings().all()]


async def build_overview(db: AsyncSession, *, now: datetime | None = None, master_access_mode: str = "unset") -> dict:
    now = _aware(now) or datetime.now(timezone.utc)
    _today, day_start, day_end = bogota_day_bounds(now)
    week_start = day_start - timedelta(days=6)
    have = await _existing(db)

    package_sql = ""
    if {"company_package_assignments", "packages"} <= have:
        package_sql = """,
               (SELECT p.name FROM company_package_assignments a JOIN packages p ON p.id = a.package_id
                 WHERE a.company_id = c.id AND LOWER(COALESCE(a.status, '')) = 'active'
                 ORDER BY a.activated_at DESC NULLS LAST, a.created_at DESC LIMIT 1) AS package_name"""
    companies = await _rows(db, f"""
        SELECT c.id, c.name, c.slug, c.status, c.plan{package_sql}
        FROM companies c
        WHERE LOWER(COALESCE(c.status, '')) NOT IN ('archived', 'deleted')
        ORDER BY c.name
    """)
    by_id: dict[str, dict] = {}
    for c in companies:
        by_id[str(c["id"])] = {
            "id": str(c["id"]), "name": c.get("name") or "", "slug": c.get("slug") or "",
            "status": str(c.get("status") or ""), "plan": c.get("package_name") or c.get("plan") or "",
            "modules_enabled": 0, "flags_on": [],
            "sales_today_total": 0.0, "orders_today": 0, "sales_7d_total": 0.0, "last_sale_at": None,
            "mini_panel_today": 0, "mini_panel_last_at": None,
            "open_sessions": 0, "owners_with_access": 0, "_signal": None,
        }

    def bump_signal(row: dict, moment: Any) -> None:
        moment = _aware(moment)
        if moment and (row["_signal"] is None or moment > row["_signal"]):
            row["_signal"] = moment

    if {"company_modules"} <= have:
        for r in await _rows(db, """
            SELECT company_id, COUNT(*) FILTER (WHERE enabled IS TRUE) AS enabled
            FROM company_modules GROUP BY company_id
        """):
            if str(r["company_id"]) in by_id:
                by_id[str(r["company_id"])]["modules_enabled"] = int(r["enabled"] or 0)
        for r in await _rows(db, """
            SELECT DISTINCT cm.company_id, flag.key AS flag
            FROM company_modules cm
            CROSS JOIN LATERAL jsonb_each(CASE WHEN jsonb_typeof(cm.settings) = 'object' THEN cm.settings ELSE '{}'::jsonb END) AS flag
            WHERE cm.enabled IS TRUE AND flag.value = 'true'::jsonb
        """):
            if str(r["company_id"]) in by_id:
                by_id[str(r["company_id"])]["flags_on"].append(str(r["flag"]))

    if "hospitality_orders" in have:
        for r in await _rows(db, """
            SELECT company_id,
                   COALESCE(SUM(total) FILTER (WHERE moment >= :day_start AND moment < :day_end), 0) AS today_total,
                   COUNT(*) FILTER (WHERE moment >= :day_start AND moment < :day_end) AS orders_today,
                   COALESCE(SUM(total) FILTER (WHERE moment >= :week_start AND moment < :day_end), 0) AS week_total,
                   MAX(moment) AS last_sale_at
            FROM (
                SELECT company_id, total,
                       CASE WHEN LOWER(COALESCE(status, '')) = :paid AND closed_at IS NOT NULL THEN closed_at ELSE created_at END AS moment
                FROM hospitality_orders
                WHERE LOWER(COALESCE(status, '')) <> ALL(CAST(:cancelled AS text[]))
            ) sales
            GROUP BY company_id
        """, {"day_start": day_start, "day_end": day_end, "week_start": week_start, "paid": PAID,
              "cancelled": sorted(CANCELLED)}):
            row = by_id.get(str(r["company_id"]))
            if not row:
                continue
            row.update(sales_today_total=_money(r["today_total"]), orders_today=int(r["orders_today"] or 0),
                       sales_7d_total=_money(r["week_total"]), last_sale_at=_aware(r["last_sale_at"]))
            bump_signal(row, r["last_sale_at"])

    for table in ("mini_panel_sales_records", "mini_panel_quotes"):
        if table not in have:
            continue
        for r in await _rows(db, f"""
            SELECT company_id, COUNT(*) FILTER (WHERE created_at >= :day_start AND created_at < :day_end) AS today,
                   MAX(created_at) AS last_at
            FROM {table} GROUP BY company_id
        """, {"day_start": day_start, "day_end": day_end}):
            row = by_id.get(str(r["company_id"]))
            if not row:
                continue
            row["mini_panel_today"] += int(r["today"] or 0)
            last = _aware(r["last_at"])
            if last and (row["mini_panel_last_at"] is None or last > row["mini_panel_last_at"]):
                row["mini_panel_last_at"] = last
            bump_signal(row, last)

    if "clonexa_access_sessions" in have:
        for r in await _rows(db, """
            SELECT company_id, COUNT(*) FILTER (WHERE status = 'active') AS open_sessions, MAX(last_seen_at) AS last_seen
            FROM clonexa_access_sessions WHERE company_id IS NOT NULL GROUP BY company_id
        """):
            row = by_id.get(str(r["company_id"]))
            if not row:
                continue
            row["open_sessions"] = int(r["open_sessions"] or 0)
            bump_signal(row, r["last_seen"])

    if "company_users" in have:
        for r in await _rows(db, """
            SELECT company_id, COUNT(*) AS owners FROM company_users
            WHERE LOWER(COALESCE(status, '')) = 'active' AND LOWER(COALESCE(role, '')) = ANY(CAST(:roles AS text[]))
            GROUP BY company_id
        """, {"roles": list(OWNER_ROLES)}):
            if str(r["company_id"]) in by_id:
                by_id[str(r["company_id"])]["owners_with_access"] = int(r["owners"] or 0)

    out = []
    totals = {"operando": 0, "sin_operacion_hoy": 0, "dormida": 0, "riesgo": 0, "inactiva": 0}
    for row in by_id.values():
        state, reason = classify(row, now)
        totals[state] += 1
        row["flags_on"] = sorted(set(row["flags_on"]))
        signal = row.pop("_signal")
        out.append({**row, "state": state, "state_reason": reason, "last_real_signal_at": _iso(signal),
                    "last_sale_at": _iso(row["last_sale_at"]), "mini_panel_last_at": _iso(row["mini_panel_last_at"])})
    return {
        "ok": True,
        "generated_at": now.isoformat(),
        "timezone": "America/Bogota",
        "master_access_mode": master_access_mode,
        "totals": {
            "companies": len(out),
            "operating_today": totals["operando"], "no_operation_today": totals["sin_operacion_hoy"],
            "dormant": totals["dormida"],
            "at_risk": totals["riesgo"], "inactive": totals["inactiva"],
            "sales_today_total": _money(sum(Decimal(str(c["sales_today_total"])) for c in out)),
            "open_sessions": sum(c["open_sessions"] for c in out),
            "generated_at": now.isoformat(),
        },
        "companies": out,
    }
