"""Pulso de todas las empresas para la consola maestra (Admin V2 / V2+).

Decision del dueño (Fase 2): las ventas de los clientes NO son un dato del
Centro de mando. Varias empresas no registran ventas sino produccion o
conexion, y medirlas por ventas las marcaba "dormidas" por error. La señal de
vida es la CONEXION.

Todo sale en pocas consultas agregadas (una por fuente, nunca una por empresa):
- Sesiones: clonexa_access_sessions (cualquier scope de esa empresa).
- Usuarios: company_users.last_login_at y dueños con acceso.
- Operacion: el ultimo registro (created_at) de cada tabla operativa que
  exista: pedidos, mini paneles, referencias de produccion, asistencia.
- Ventas (hospitality_orders): siguen POR EMPRESA en la respuesta, pero no
  cuentan en los totales ni en el semaforo.
Una tabla (o columna) que no existe cuenta como nada: nunca rompe el endpoint.
last_real_signal_at = lo mas reciente entre sesiones, last_login_at y
operacion. NUNCA updated_at.

Semaforo, en este orden:
- inactiva: status inactivo y sin modulos (con modulos es riesgo).
- riesgo: inactiva con modulos encendidos, o activa sin dueño con acceso.
- conectada: sesion activa con last_seen_at en los ultimos 15 minutos.
- activa_hoy: señal hoy (dia en America/Bogota).
- sin_actividad_hoy: señal en los ultimos 7 dias.
- dormida: mas de 7 dias, o nunca.

Totales: SOLO empresas registradas (las demos se cuentan aparte en health).
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.company_kind import DEMO, REGISTERED, resolve_kind
from app.services.sales_ledger import CANCELLED, PAID

BOGOTA = ZoneInfo("America/Bogota")
DORMANT_DAYS = 7
CONNECTED_MINUTES = 15
# Una sesion "abierta" sin actividad en 24 h no cuenta como abierta: nadie la
# cerro (ver docs/sesiones_viejas.md), se muestra aparte como "sin actividad".
OPEN_RECENT_HOURS = 24
DB_LIMIT_MB = 500
DB_WARN_PCT = 80
OWNER_ROLES = ("company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario")
STATES = ("conectada", "activa_hoy", "sin_actividad_hoy", "dormida", "riesgo", "inactiva")
# Tablas operativas: su ultimo registro es señal de vida. Lista explicita.
OPERATION_TABLES = (
    "mini_panel_sales_records", "mini_panel_quotes", "mini_panel_notes", "mini_panel_work_sessions",
    "reference_work_sessions", "reference_production_closures", "workforce_attendance_events",
)
TABLES = ("hospitality_orders", "company_modules", "modules", "company_package_assignments", "packages",
          "clonexa_access_sessions", "company_users", *OPERATION_TABLES)


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
    if not active:
        if modules:
            return "riesgo", f"Inactiva con {modules} módulo{'s' if modules != 1 else ''}"
        return "inactiva", "Inactiva sin módulos"
    if not company.get("owners_with_access"):
        return "riesgo", "Activa sin dueño con acceso"
    live = int(company.get("connected_sessions") or 0)
    if live:
        users = int(company.get("users_connected") or 0) or live
        return "conectada", f"{users} usuario{'s' if users != 1 else ''} conectado{'s' if users != 1 else ''} ahora"
    if signal is None:
        return "dormida", "Sin señales reales"
    today = now.astimezone(BOGOTA).date()
    if signal.astimezone(BOGOTA).date() == today:
        return "activa_hoy", f"Última señal hoy a las {signal.astimezone(BOGOTA).strftime('%H:%M')}"
    if now - signal <= timedelta(days=DORMANT_DAYS):
        return "sin_actividad_hoy", f"Última señal {_ago(signal, now).lower()}"
    return "dormida", _ago(signal, now)


async def _columns(db: AsyncSession) -> dict[str, set[str]]:
    """Tablas que existen y sus columnas (una sola consulta)."""
    rows = (await db.execute(text(
        "SELECT table_name, array_agg(column_name::text) AS cols FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = ANY(CAST(:names AS text[])) GROUP BY table_name"
    ), {"names": list(TABLES)})).mappings().all()
    return {str(r["table_name"]): set(r["cols"] or []) for r in rows}


async def _rows(db: AsyncSession, sql: str, params: dict | None = None) -> list[dict]:
    return [dict(r) for r in (await db.execute(text(sql), params or {})).mappings().all()]


def deploy_info() -> dict:
    commit = next((os.getenv(k, "").strip() for k in ("RAILWAY_GIT_COMMIT_SHA", "SOURCE_COMMIT", "GIT_COMMIT")
                   if os.getenv(k, "").strip()), "")
    return {
        "commit": commit[:12] or None,
        "branch": os.getenv("RAILWAY_GIT_BRANCH", "").strip() or None,
        "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID", "").strip() or None,
    }


async def _db_size(db: AsyncSession) -> dict:
    try:
        size = (await db.execute(text("SELECT pg_database_size(current_database()) AS bytes"))).scalar()
    except Exception:
        return {"used_mb": None, "limit_mb": DB_LIMIT_MB, "used_pct": None, "warn": False}
    used_mb = round(int(size or 0) / 1024 / 1024, 1)
    pct = round(used_mb * 100 / DB_LIMIT_MB, 1)
    return {"used_mb": used_mb, "limit_mb": DB_LIMIT_MB, "used_pct": pct, "warn": pct >= DB_WARN_PCT}


async def build_overview(db: AsyncSession, *, now: datetime | None = None, master_access_mode: str = "unset") -> dict:
    now = _aware(now) or datetime.now(timezone.utc)
    _today, day_start, day_end = bogota_day_bounds(now)
    week_start = day_start - timedelta(days=6)
    live_since = now - timedelta(minutes=CONNECTED_MINUTES)
    recent_since = now - timedelta(hours=OPEN_RECENT_HOURS)
    cols = await _columns(db)
    have = set(cols)

    package_sql = ""
    if {"company_package_assignments", "packages"} <= have:
        package_sql = """,
               (SELECT p.name FROM company_package_assignments a JOIN packages p ON p.id = a.package_id
                 WHERE a.company_id = c.id AND LOWER(COALESCE(a.status, '')) = 'active'
                 ORDER BY a.activated_at DESC NULLS LAST, a.created_at DESC LIMIT 1) AS package_name"""
    companies = await _rows(db, f"""
        SELECT c.id, c.name, c.slug, c.status, c.plan, c.settings_json->>'kind' AS kind{package_sql}
        FROM companies c
        WHERE LOWER(COALESCE(c.status, '')) NOT IN ('archived', 'deleted')
        ORDER BY c.name
    """)
    by_id: dict[str, dict] = {}
    for c in companies:
        by_id[str(c["id"])] = {
            "id": str(c["id"]), "name": c.get("name") or "", "slug": c.get("slug") or "",
            "status": str(c.get("status") or ""), "plan": c.get("package_name") or c.get("plan") or "",
            "kind": resolve_kind(c["id"], c.get("kind")),
            "modules_enabled": 0, "flags_on": [],
            "open_sessions": 0, "stale_sessions": 0, "connected_sessions": 0, "users_connected": 0, "logins_today": 0,
            "last_seen_at": None, "last_login_at": None, "operation_last_at": None,
            "owners_with_access": 0,
            # Ventas: solo informativas por empresa (no van a totales ni al semaforo).
            "sales_today_total": 0.0, "orders_today": 0, "sales_7d_total": 0.0, "last_sale_at": None,
            "_signal": None,
        }

    def bump(row: dict, key: str | None, moment: Any) -> None:
        moment = _aware(moment)
        if not moment:
            return
        if key and (row[key] is None or moment > row[key]):
            row[key] = moment
        if row["_signal"] is None or moment > row["_signal"]:
            row["_signal"] = moment

    if "company_modules" in have:
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

    if "clonexa_access_sessions" in have:
        for r in await _rows(db, """
            SELECT company_id::text AS company_id,
                   COUNT(*) FILTER (WHERE status = 'active' AND last_seen_at >= :recent_since) AS open_sessions,
                   COUNT(*) FILTER (WHERE status = 'active' AND last_seen_at < :recent_since) AS stale_sessions,
                   COUNT(*) FILTER (WHERE status = 'active' AND last_seen_at >= :live_since) AS live_sessions,
                   COUNT(DISTINCT COALESCE(subject_id::text, session_key))
                     FILTER (WHERE status = 'active' AND last_seen_at >= :live_since) AS live_users,
                   COUNT(*) FILTER (WHERE created_at >= :day_start AND created_at < :day_end) AS logins_today,
                   MAX(last_seen_at) AS last_seen
            FROM clonexa_access_sessions WHERE company_id IS NOT NULL GROUP BY company_id
        """, {"live_since": live_since, "recent_since": recent_since, "day_start": day_start, "day_end": day_end}):
            row = by_id.get(str(r["company_id"]))
            if not row:
                continue
            row.update(open_sessions=int(r["open_sessions"] or 0), stale_sessions=int(r["stale_sessions"] or 0), connected_sessions=int(r["live_sessions"] or 0),
                       users_connected=int(r["live_users"] or 0), logins_today=int(r["logins_today"] or 0))
            bump(row, "last_seen_at", r["last_seen"])

    if "company_users" in have:
        last_login = "MAX(last_login_at)" if "last_login_at" in cols["company_users"] else "NULL"
        for r in await _rows(db, f"""
            SELECT company_id::text AS company_id,
                   COUNT(*) FILTER (WHERE LOWER(COALESCE(status, '')) = 'active'
                                      AND LOWER(COALESCE(role, '')) = ANY(CAST(:roles AS text[]))) AS owners,
                   {last_login} AS last_login
            FROM company_users GROUP BY company_id
        """, {"roles": list(OWNER_ROLES)}):
            row = by_id.get(str(r["company_id"]))
            if row:
                row["owners_with_access"] = int(r["owners"] or 0)
                bump(row, "last_login_at", r["last_login"])

    operation = [t for t in OPERATION_TABLES if {"company_id", "created_at"} <= cols.get(t, set())]
    if operation:
        union = " UNION ALL ".join(
            f"SELECT company_id::text AS company_id, MAX(created_at) AS last_at FROM {t} GROUP BY company_id"
            for t in operation)
        for r in await _rows(db, f"SELECT company_id, MAX(last_at) AS last_at FROM ({union}) ops GROUP BY company_id"):
            row = by_id.get(str(r["company_id"]))
            if row:
                bump(row, "operation_last_at", r["last_at"])

    if "hospitality_orders" in have:
        for r in await _rows(db, """
            SELECT company_id::text AS company_id,
                   COALESCE(SUM(total) FILTER (WHERE moment >= :day_start AND moment < :day_end), 0) AS today_total,
                   COUNT(*) FILTER (WHERE moment >= :day_start AND moment < :day_end) AS orders_today,
                   COALESCE(SUM(total) FILTER (WHERE moment >= :week_start AND moment < :day_end), 0) AS week_total,
                   MAX(moment) AS last_sale_at, MAX(created_at) AS last_order_at
            FROM (
                SELECT company_id, total, created_at,
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
            # Un pedido es un registro operativo: cuenta como señal (no como venta).
            bump(row, "operation_last_at", r["last_order_at"])

    out = []
    states = {name: 0 for name in STATES}
    demo_count = 0
    totals = {"registered": 0, "registered_active": 0, "connected_now": 0, "users_connected_now": 0,
              "logins_today": 0, "dormant": 0, "at_risk": 0, "open_sessions": 0, "stale_sessions": 0}
    for row in by_id.values():
        state, reason = classify(row, now)
        row["flags_on"] = sorted(set(row["flags_on"]))
        signal = row.pop("_signal")
        item = {**row, "state": state, "state_reason": reason, "last_real_signal_at": _iso(signal)}
        for key in ("last_seen_at", "last_login_at", "operation_last_at", "last_sale_at"):
            item[key] = _iso(row[key])
        out.append(item)
        if row["kind"] == DEMO:
            demo_count += 1
            continue
        states[state] += 1
        totals["registered"] += 1
        totals["registered_active"] += 1 if row["status"].lower() == "active" else 0
        totals["connected_now"] += 1 if row["connected_sessions"] else 0
        totals["users_connected_now"] += row["users_connected"]
        totals["logins_today"] += row["logins_today"]
        totals["open_sessions"] += row["open_sessions"]
        totals["stale_sessions"] += row["stale_sessions"]
        totals["dormant"] += 1 if state == "dormida" else 0
        totals["at_risk"] += 1 if state == "riesgo" else 0
    return {
        "ok": True,
        "generated_at": now.isoformat(),
        "timezone": "America/Bogota",
        "master_access_mode": master_access_mode,
        "connected_minutes": CONNECTED_MINUTES,
        "totals": {**totals, "states": states, "generated_at": now.isoformat()},
        "health": {
            "database": await _db_size(db),
            "demo_companies": demo_count,
            "deploy": deploy_info(),
            "master_access_mode": master_access_mode,
        },
        "companies": out,
    }


__all__ = ["build_overview", "classify", "bogota_day_bounds", "REGISTERED", "DEMO"]
