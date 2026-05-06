from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

try:
    from app.api.v1.endpoints.payroll import (
        calculate_period_snapshot as payroll_calculate_period_snapshot,
        ensure_payroll_storage as payroll_ensure_storage,
    )
except Exception:  # pragma: no cover - KPIs debe seguir vivo aunque Nómina cambie.
    payroll_calculate_period_snapshot = None
    payroll_ensure_storage = None

router = APIRouter()
UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize(v) for v in value]
    return value


def row_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    mapping = getattr(row, "_mapping", row)
    return {str(k): serialize(v) for k, v in dict(mapping).items()}


def normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def int_num(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def period_from_params(
    preset: str | None,
    start_date: date | None,
    end_date: date | None,
) -> tuple[datetime, datetime, str]:
    now = utcnow()
    end = datetime.combine(end_date, time.max, tzinfo=UTC) if end_date else now
    code = normalize(preset or "7d")

    if start_date:
        start = datetime.combine(start_date, time.min, tzinfo=UTC)
        code = "custom" if code == "custom" else code
    elif code in {"today", "hoy", "day"}:
        start = datetime.combine(now.date(), time.min, tzinfo=UTC)
        code = "today"
    elif code in {"15d", "15", "quincena"}:
        start = now - timedelta(days=15)
        code = "15d"
    elif code in {"30d", "month", "mes"}:
        start = now - timedelta(days=30)
        code = "month"
    elif code in {"7d", "week", "semana"}:
        start = now - timedelta(days=7)
        code = "7d"
    else:
        start = now - timedelta(days=7)
        code = "7d"

    if start > end:
        start, end = end - timedelta(days=1), start
    return start, end, code


async def safe_rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception:
        pass


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    try:
        result = await db.execute(
            text("SELECT to_regclass(:name) IS NOT NULL AS exists"),
            {"name": f"public.{table_name}"},
        )
        return bool(result.scalar())
    except Exception:
        await safe_rollback(db)
        return False


async def table_columns(db: AsyncSession, table_name: str) -> set[str]:
    try:
        result = await db.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
            """),
            {"table_name": table_name},
        )
        return {str(row[0]) for row in result.fetchall()}
    except Exception:
        await safe_rollback(db)
        return set()


async def scalar(db: AsyncSession, sql: str, params: dict[str, Any], default: Any = 0) -> Any:
    try:
        result = await db.execute(text(sql), params)
        value = result.scalar()
        return default if value is None else value
    except Exception:
        await safe_rollback(db)
        return default


async def rows(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        result = await db.execute(text(sql), params)
        return [row_dict(row) for row in result.fetchall()]
    except Exception:
        await safe_rollback(db)
        return []


async def ensure_dashboard_schema(db: AsyncSession) -> None:
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS company_kpi_dashboard_cards (
                company_id uuid NOT NULL,
                card_key varchar(140) NOT NULL,
                enabled boolean NOT NULL DEFAULT false,
                sort_order integer NOT NULL DEFAULT 100,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (company_id, card_key)
            )
        """))
        await db.commit()
    except Exception:
        await safe_rollback(db)


async def active_modules(db: AsyncSession, company_id: UUID) -> set[str]:
    modules: set[str] = set()

    if await table_exists(db, "company_modules"):
        cm_cols = await table_columns(db, "company_modules")

        if "module_id" in cm_cols and await table_exists(db, "modules"):
            rows_data = await rows(
                db,
                """
                SELECT LOWER(m.code)::text AS code
                FROM company_modules cm
                JOIN modules m ON m.id = cm.module_id
                WHERE cm.company_id = CAST(:company_id AS uuid)
                  AND COALESCE(cm.enabled, true) = true
                  AND COALESCE(m.is_active, true) = true
                """,
                {"company_id": str(company_id)},
            )
            modules.update(normalize(item.get("code")) for item in rows_data if item.get("code"))

        for col in ("module_code", "code"):
            if col in cm_cols:
                rows_data = await rows(
                    db,
                    f"""
                    SELECT LOWER({col}::text) AS code
                    FROM company_modules
                    WHERE company_id = CAST(:company_id AS uuid)
                      AND COALESCE(enabled, true) = true
                    """,
                    {"company_id": str(company_id)},
                )
                modules.update(normalize(item.get("code")) for item in rows_data if item.get("code"))

    # Fallback operativo: si el join de módulos falla, no dejamos la pantalla en cero.
    if not modules:
        if await table_exists(db, "employees"):
            modules.add("workforce")
        if await table_exists(db, "company_gps_perimeters"):
            modules.add("gps")
        if await table_exists(db, "inventory_items"):
            modules.add("inventory")
        if await table_exists(db, "material_requests"):
            modules.add("materials")
        if await table_exists(db, "payroll_period_items"):
            modules.add("payroll")
        if await table_exists(db, "company_bot_instances"):
            modules.add("bots")

    return {m for m in modules if m}


async def employee_kpis(db: AsyncSession, company_id: UUID) -> dict[str, Any]:
    out = {"total": 0, "active": 0, "inactive": 0, "archived": 0, "telegram_linked": 0, "by_role": []}
    if not await table_exists(db, "employees"):
        return out

    cols = await table_columns(db, "employees")
    if not {"company_id", "status"}.issubset(cols):
        return out

    telegram_expr = "telegram_user_id::text" if "telegram_user_id" in cols else "NULL"
    role_expr = "COALESCE(NULLIF(role,''), NULLIF(employee_type,''), 'sin_rol')" if "role" in cols and "employee_type" in cols else ("COALESCE(NULLIF(role,''), 'sin_rol')" if "role" in cols else "'sin_rol'")

    data = await rows(
        db,
        f"""
        SELECT
          COUNT(*)::int AS total,
          COUNT(*) FILTER (WHERE LOWER(COALESCE(status,'')) IN ('active','activo'))::int AS active,
          COUNT(*) FILTER (WHERE LOWER(COALESCE(status,'')) IN ('inactive','inactivo'))::int AS inactive,
          COUNT(*) FILTER (WHERE LOWER(COALESCE(status,'')) IN ('archived','archive','archivado'))::int AS archived,
          COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE({telegram_expr},'')), '') IS NOT NULL)::int AS telegram_linked
        FROM employees
        WHERE company_id = CAST(:company_id AS uuid)
        """,
        {"company_id": str(company_id)},
    )
    if data:
        out.update(data[0])

    out["by_role"] = await rows(
        db,
        f"""
        SELECT {role_expr}::text AS role, COUNT(*)::int AS total
        FROM employees
        WHERE company_id = CAST(:company_id AS uuid)
          AND LOWER(COALESCE(status,'')) IN ('active','activo')
        GROUP BY {role_expr}
        ORDER BY total DESC, role ASC
        LIMIT 8
        """,
        {"company_id": str(company_id)},
    )
    return out


async def attendance_kpis(db: AsyncSession, company_id: UUID, start: datetime, end: datetime) -> dict[str, Any]:
    out = {"active_now": 0, "paused_now": 0, "closed_now": 0, "events": 0, "checkins": 0, "checkouts": 0, "breaks": 0, "worked_minutes": 0}
    params = {"company_id": str(company_id), "start_ts": start, "end_ts": end}

    if await table_exists(db, "workforce_attendance_status"):
        cols = await table_columns(db, "workforce_attendance_status")
        status_col = "current_status" if "current_status" in cols else ("status" if "status" in cols else None)
        if status_col and "company_id" in cols:
            data = await rows(
                db,
                f"""
                SELECT LOWER(COALESCE({status_col}::text,'')) AS status, COUNT(*)::int AS total
                FROM workforce_attendance_status
                WHERE company_id = CAST(:company_id AS uuid)
                GROUP BY LOWER(COALESCE({status_col}::text,''))
                """,
                params,
            )
            for item in data:
                status = normalize(item.get("status"))
                total = int_num(item.get("total"))
                if status in {"working", "active", "activo", "checked_in", "check_in", "in_shift", "on_shift"}:
                    out["active_now"] += total
                elif status in {"break", "paused", "pause", "pausa", "en_pausa", "on_break"}:
                    out["paused_now"] += total
                elif status in {"closed", "checkout", "checked_out", "out", "finished", "finalizado"}:
                    out["closed_now"] += total

    if await table_exists(db, "workforce_attendance_events"):
        cols = await table_columns(db, "workforce_attendance_events")
        time_col = "occurred_at" if "occurred_at" in cols else ("created_at" if "created_at" in cols else None)
        event_col = "event_type" if "event_type" in cols else ("type" if "type" in cols else None)
        if time_col and event_col and "company_id" in cols:
            data = await rows(
                db,
                f"""
                SELECT LOWER(COALESCE({event_col}::text,'')) AS event_type, COUNT(*)::int AS total
                FROM workforce_attendance_events
                WHERE company_id = CAST(:company_id AS uuid)
                  AND {time_col} >= CAST(:start_ts AS timestamptz)
                  AND {time_col} <= CAST(:end_ts AS timestamptz)
                GROUP BY LOWER(COALESCE({event_col}::text,''))
                """,
                params,
            )
            out["events"] = sum(int_num(item.get("total")) for item in data)
            for item in data:
                event_type = normalize(item.get("event_type"))
                total = int_num(item.get("total"))
                if event_type in {"check_in", "entrada", "start_shift", "shift_started"}:
                    out["checkins"] += total
                elif event_type in {"check_out", "salida", "end_shift", "shift_closed"}:
                    out["checkouts"] += total
                elif event_type in {"break_start", "break_end", "pause", "resume", "pausa", "reanudacion"}:
                    out["breaks"] += total
    return out


async def material_kpis(db: AsyncSession, company_id: UUID, start: datetime, end: datetime) -> dict[str, Any]:
    out = {"total": 0, "pending": 0, "approved": 0, "delivered": 0, "returned": 0, "returned_partial": 0, "consigned": 0, "consigned_partial": 0, "rejected": 0, "active_orders": 0, "top_requested": []}
    if not await table_exists(db, "material_requests"):
        return out

    cols = await table_columns(db, "material_requests")
    if "company_id" not in cols or "status" not in cols:
        return out

    time_col = "created_at" if "created_at" in cols else ("requested_at" if "requested_at" in cols else ("updated_at" if "updated_at" in cols else None))
    if not time_col:
        return out

    archived_filter = "AND archived_at IS NULL" if "archived_at" in cols else ""
    params = {"company_id": str(company_id), "start_ts": start, "end_ts": end}

    data = await rows(
        db,
        f"""
        SELECT LOWER(COALESCE(status::text,'')) AS status, COUNT(*)::int AS total
        FROM material_requests
        WHERE company_id = CAST(:company_id AS uuid)
          AND {time_col} >= CAST(:start_ts AS timestamptz)
          AND {time_col} <= CAST(:end_ts AS timestamptz)
          {archived_filter}
        GROUP BY LOWER(COALESCE(status::text,''))
        """,
        params,
    )
    for item in data:
        status = normalize(item.get("status"))
        total = int_num(item.get("total"))
        out["total"] += total
        if status in {"pending", "requested", "solicitada", "solicitado"}:
            out["pending"] += total
        elif status in {"approved", "aprobada", "aprobado"}:
            out["approved"] += total
        elif status in {"delivered", "entregada", "entregado"}:
            out["delivered"] += total
        elif status in {"returned", "devuelta", "devuelto", "returned_total", "devuelta_total"}:
            out["returned"] += total
        elif status in {"returned_partial", "devuelta_parcial", "partial_return"}:
            out["returned_partial"] += total
        elif status in {"consigned", "consignada", "consignado"}:
            out["consigned"] += total
        elif status in {"consigned_partial", "consignada_parcial"}:
            out["consigned_partial"] += total
        elif status in {"rejected", "rechazada", "rechazado"}:
            out["rejected"] += total

    order_expr = "COALESCE(NULLIF(order_number,''), id::text)" if "order_number" in cols and "id" in cols else ("order_number" if "order_number" in cols else "status")
    out["active_orders"] = int_num(await scalar(
        db,
        f"""
        SELECT COUNT(DISTINCT {order_expr})::int
        FROM material_requests
        WHERE company_id = CAST(:company_id AS uuid)
          AND {time_col} >= CAST(:start_ts AS timestamptz)
          AND {time_col} <= CAST(:end_ts AS timestamptz)
          {archived_filter}
          AND LOWER(COALESCE(status::text,'')) IN ('pending','requested','solicitada','approved','aprobada','delivered','entregada','consigned','consigned_partial')
        """,
        params,
    ))

    name_expr = "COALESCE(NULLIF(name_reference,''), NULLIF(material_name,''), 'Material')" if "name_reference" in cols and "material_name" in cols else ("COALESCE(NULLIF(name_reference,''), 'Material')" if "name_reference" in cols else ("COALESCE(NULLIF(material_name,''), 'Material')" if "material_name" in cols else "'Material'"))
    size_expr = "COALESCE(NULLIF(item_size,''), '')" if "item_size" in cols else ("COALESCE(NULLIF(size,''), '')" if "size" in cols else "''")
    qty_expr = "COALESCE(quantity,0)" if "quantity" in cols else "1"

    out["top_requested"] = await rows(
        db,
        f"""
        SELECT
          {name_expr}::text AS name_reference,
          {size_expr}::text AS item_size,
          SUM({qty_expr})::float AS quantity
        FROM material_requests
        WHERE company_id = CAST(:company_id AS uuid)
          AND {time_col} >= CAST(:start_ts AS timestamptz)
          AND {time_col} <= CAST(:end_ts AS timestamptz)
          {archived_filter}
        GROUP BY {name_expr}, {size_expr}
        ORDER BY quantity DESC
        LIMIT 8
        """,
        params,
    )
    return out


async def inventory_kpis(db: AsyncSession, company_id: UUID, start: datetime, end: datetime) -> dict[str, Any]:
    out = {"items": 0, "active": 0, "low_stock": 0, "zero_stock": 0, "total_stock_units": 0.0, "movements_in": 0.0, "movements_out": 0.0}
    if await table_exists(db, "inventory_items"):
        cols = await table_columns(db, "inventory_items")
        if "company_id" in cols:
            status_expr = "LOWER(COALESCE(status,''))" if "status" in cols else "'active'"
            stock_expr = "COALESCE(current_stock,0)" if "current_stock" in cols else "0"
            min_expr = "COALESCE(min_stock,0)" if "min_stock" in cols else "0"
            data = await rows(
                db,
                f"""
                SELECT
                  COUNT(*)::int AS items,
                  COUNT(*) FILTER (WHERE {status_expr} IN ('active','activo'))::int AS active,
                  COUNT(*) FILTER (WHERE {stock_expr} <= {min_expr} AND {stock_expr} > 0)::int AS low_stock,
                  COUNT(*) FILTER (WHERE {stock_expr} <= 0)::int AS zero_stock,
                  COALESCE(SUM({stock_expr}),0)::float AS total_stock_units
                FROM inventory_items
                WHERE company_id = CAST(:company_id AS uuid)
                """,
                {"company_id": str(company_id)},
            )
            if data:
                out.update(data[0])

    if await table_exists(db, "inventory_movements"):
        cols = await table_columns(db, "inventory_movements")
        if {"company_id", "created_at"}.issubset(cols):
            qty_col = "quantity_delta" if "quantity_delta" in cols else ("quantity" if "quantity" in cols else None)
            if qty_col:
                data = await rows(
                    db,
                    f"""
                    SELECT
                      COALESCE(SUM(CASE WHEN COALESCE({qty_col},0) > 0 THEN {qty_col} ELSE 0 END),0)::float AS movements_in,
                      ABS(COALESCE(SUM(CASE WHEN COALESCE({qty_col},0) < 0 THEN {qty_col} ELSE 0 END),0))::float AS movements_out
                    FROM inventory_movements
                    WHERE company_id = CAST(:company_id AS uuid)
                      AND created_at >= CAST(:start_ts AS timestamptz)
                      AND created_at <= CAST(:end_ts AS timestamptz)
                    """,
                    {"company_id": str(company_id), "start_ts": start, "end_ts": end},
                )
                if data:
                    out["movements_in"] = num(data[0].get("movements_in"))
                    out["movements_out"] = num(data[0].get("movements_out"))
    return out


async def gps_kpis(db: AsyncSession, company_id: UUID, start: datetime, end: datetime) -> dict[str, Any]:
    out = {"perimeters": 0, "locations": 0, "inside": 0, "outside": 0, "unconfigured": 0}
    if await table_exists(db, "company_gps_perimeters"):
        cols = await table_columns(db, "company_gps_perimeters")
        if "company_id" in cols:
            active_filter = "AND COALESCE(is_active, true) = true" if "is_active" in cols else ""
            out["perimeters"] = int_num(await scalar(
                db,
                f"""
                SELECT COUNT(*)::int
                FROM company_gps_perimeters
                WHERE company_id = CAST(:company_id AS uuid)
                {active_filter}
                """,
                {"company_id": str(company_id)},
            ))

    if await table_exists(db, "workforce_attendance_events"):
        cols = await table_columns(db, "workforce_attendance_events")
        time_col = "occurred_at" if "occurred_at" in cols else ("created_at" if "created_at" in cols else None)
        event_col = "event_type" if "event_type" in cols else None
        module_col = "module_code" if "module_code" in cols else None
        status_expr = "COALESCE(status_after::text,'')" if "status_after" in cols else "''"
        payload_expr = "COALESCE(payload_json::text,'')" if "payload_json" in cols else "''"
        if time_col and "company_id" in cols and (event_col or module_col):
            where_event = []
            if module_col:
                where_event.append(f"LOWER(COALESCE({module_col}::text,'')) = 'gps'")
            if event_col:
                where_event.append(f"LOWER(COALESCE({event_col}::text,'')) IN ('gps_location','gps_ping','location','ubicacion')")
            data = await rows(
                db,
                f"""
                SELECT
                  COUNT(*)::int AS locations,
                  COUNT(*) FILTER (WHERE LOWER({status_expr}) LIKE '%inside%' OR LOWER({payload_expr}) LIKE '%inside%' OR LOWER({payload_expr}) LIKE '%dentro%')::int AS inside,
                  COUNT(*) FILTER (WHERE LOWER({status_expr}) LIKE '%outside%' OR LOWER({payload_expr}) LIKE '%outside%' OR LOWER({payload_expr}) LIKE '%fuera%')::int AS outside
                FROM workforce_attendance_events
                WHERE company_id = CAST(:company_id AS uuid)
                  AND {time_col} >= CAST(:start_ts AS timestamptz)
                  AND {time_col} <= CAST(:end_ts AS timestamptz)
                  AND ({' OR '.join(where_event)})
                """,
                {"company_id": str(company_id), "start_ts": start, "end_ts": end},
            )
            if data:
                out.update(data[0])
    return out


async def payroll_kpis(db: AsyncSession, company_id: UUID, start: datetime, end: datetime) -> dict[str, Any]:
    """
    016A-R2:
    KPIs de Nómina deben leer la misma fuente real que usa el módulo Nómina.

    Orden de verdad:
    1) Cálculo vivo del módulo Nómina para el rango solicitado.
    2) Periodos cerrados que se solapen con el rango.
    3) Totales JSON de payroll_periods como fallback.
    4) Items históricos como último fallback.

    No filtra por created_at de payroll_period_items porque eso devuelve 0 cuando
    el corte fue creado fuera del rango operativo.
    """
    out = {
        "periods": 0,
        "regular_minutes": 0,
        "extra_minutes": 0,
        "net_amount": 0.0,
        "gross_amount": 0.0,
        "discount_amount": 0.0,
        "closed_shifts": 0,
        "people": 0,
        "source": "empty",
    }

    period_start = start.date()
    period_end = end.date()
    params = {
        "company_id": str(company_id),
        "period_start": period_start,
        "period_end": period_end,
        "start_ts": start,
        "end_ts": end,
    }

    # 1) Fuente viva: misma función usada por /payroll/periods/calculate.
    if payroll_ensure_storage and payroll_calculate_period_snapshot:
        try:
            await payroll_ensure_storage(db)
            snapshot = await payroll_calculate_period_snapshot(db, company_id, period_start, period_end)
            totals = snapshot.get("totals") or {}
            out.update({
                "periods": 1 if (num(totals.get("regular_minutes")) or num(totals.get("extra_minutes")) or num(totals.get("net_amount"))) else 0,
                "regular_minutes": int_num(totals.get("regular_minutes")),
                "extra_minutes": int_num(totals.get("extra_minutes")),
                "gross_amount": num(totals.get("gross_amount")),
                "discount_amount": num(totals.get("discount_amount")),
                "net_amount": num(totals.get("net_amount")),
                "closed_shifts": int_num(totals.get("closed_shifts")),
                "people": int_num(totals.get("people")),
                "source": "live_payroll_calculation",
            })
            if (
                out["regular_minutes"]
                or out["extra_minutes"]
                or out["gross_amount"]
                or out["discount_amount"]
                or out["net_amount"]
                or out["closed_shifts"]
            ):
                return out
        except Exception:
            await safe_rollback(db)

    # 2) Periodos cerrados + items por solape de fechas del periodo.
    if await table_exists(db, "payroll_periods") and await table_exists(db, "payroll_period_items"):
        period_cols = await table_columns(db, "payroll_periods")
        item_cols = await table_columns(db, "payroll_period_items")
        if {"company_id", "id"}.issubset(period_cols) and "period_id" in item_cols:
            period_start_expr = "COALESCE(p.period_start, p.created_at::date)" if "period_start" in period_cols and "created_at" in period_cols else ("p.period_start" if "period_start" in period_cols else "p.created_at::date")
            period_end_expr = "COALESCE(p.period_end, p.created_at::date)" if "period_end" in period_cols and "created_at" in period_cols else ("p.period_end" if "period_end" in period_cols else "p.created_at::date")
            company_filter = "p.company_id = CAST(:company_id AS uuid)"
            if "company_id" in item_cols:
                company_filter += " AND COALESCE(i.company_id, p.company_id) = CAST(:company_id AS uuid)"
            regular_expr = "COALESCE(i.regular_minutes,0)" if "regular_minutes" in item_cols else "0"
            extra_expr = "COALESCE(i.extra_minutes,0)" if "extra_minutes" in item_cols else "0"
            gross_expr = "COALESCE(i.gross_amount,0)" if "gross_amount" in item_cols else "0"
            discount_expr = "COALESCE(i.discount_amount,0)" if "discount_amount" in item_cols else "0"
            net_expr = "COALESCE(i.net_amount,0)" if "net_amount" in item_cols else "0"
            shifts_expr = "COALESCE(i.closed_shifts,0)" if "closed_shifts" in item_cols else "0"
            employee_expr = "i.employee_id" if "employee_id" in item_cols else "i.id"

            data = await rows(
                db,
                f"""
                SELECT
                  COUNT(DISTINCT p.id)::int AS periods,
                  COUNT(DISTINCT {employee_expr})::int AS people,
                  COALESCE(SUM({regular_expr}),0)::int AS regular_minutes,
                  COALESCE(SUM({extra_expr}),0)::int AS extra_minutes,
                  COALESCE(SUM({shifts_expr}),0)::int AS closed_shifts,
                  COALESCE(SUM({gross_expr}),0)::float AS gross_amount,
                  COALESCE(SUM({discount_expr}),0)::float AS discount_amount,
                  COALESCE(SUM({net_expr}),0)::float AS net_amount
                FROM payroll_periods p
                JOIN payroll_period_items i ON i.period_id = p.id
                WHERE {company_filter}
                  AND {period_end_expr} >= CAST(:period_start AS date)
                  AND {period_start_expr} <= CAST(:period_end AS date)
                """,
                params,
            )
            if data:
                candidate = data[0]
                if (
                    int_num(candidate.get("regular_minutes"))
                    or int_num(candidate.get("extra_minutes"))
                    or num(candidate.get("gross_amount"))
                    or num(candidate.get("discount_amount"))
                    or num(candidate.get("net_amount"))
                    or int_num(candidate.get("closed_shifts"))
                ):
                    out.update(candidate)
                    out["source"] = "closed_period_items"
                    return out

    # 3) Totales JSON por periodo cerrado.
    if await table_exists(db, "payroll_periods"):
        period_cols = await table_columns(db, "payroll_periods")
        if {"company_id", "totals_json"}.issubset(period_cols):
            period_start_expr = "COALESCE(period_start, created_at::date)" if "period_start" in period_cols and "created_at" in period_cols else ("period_start" if "period_start" in period_cols else "created_at::date")
            period_end_expr = "COALESCE(period_end, created_at::date)" if "period_end" in period_cols and "created_at" in period_cols else ("period_end" if "period_end" in period_cols else "created_at::date")
            data = await rows(
                db,
                f"""
                SELECT
                  COUNT(*)::int AS periods,
                  COALESCE(SUM(NULLIF(totals_json->>'people','')::numeric),0)::int AS people,
                  COALESCE(SUM(NULLIF(totals_json->>'closed_shifts','')::numeric),0)::int AS closed_shifts,
                  COALESCE(SUM(NULLIF(totals_json->>'regular_minutes','')::numeric),0)::int AS regular_minutes,
                  COALESCE(SUM(NULLIF(totals_json->>'extra_minutes','')::numeric),0)::int AS extra_minutes,
                  COALESCE(SUM(NULLIF(totals_json->>'gross_amount','')::numeric),0)::float AS gross_amount,
                  COALESCE(SUM(NULLIF(totals_json->>'discount_amount','')::numeric),0)::float AS discount_amount,
                  COALESCE(SUM(NULLIF(totals_json->>'net_amount','')::numeric),0)::float AS net_amount
                FROM payroll_periods
                WHERE company_id = CAST(:company_id AS uuid)
                  AND {period_end_expr} >= CAST(:period_start AS date)
                  AND {period_start_expr} <= CAST(:period_end AS date)
                """,
                params,
            )
            if data:
                candidate = data[0]
                if (
                    int_num(candidate.get("regular_minutes"))
                    or int_num(candidate.get("extra_minutes"))
                    or num(candidate.get("gross_amount"))
                    or num(candidate.get("discount_amount"))
                    or num(candidate.get("net_amount"))
                    or int_num(candidate.get("closed_shifts"))
                ):
                    out.update(candidate)
                    out["source"] = "period_totals_json"
                    return out

    # 4) Último fallback: items históricos por created_at.
    if await table_exists(db, "payroll_period_items"):
        cols = await table_columns(db, "payroll_period_items")
        if "company_id" in cols and "created_at" in cols:
            regular_expr = "COALESCE(regular_minutes,0)" if "regular_minutes" in cols else "0"
            extra_expr = "COALESCE(extra_minutes,0)" if "extra_minutes" in cols else "0"
            gross_expr = "COALESCE(gross_amount,0)" if "gross_amount" in cols else "0"
            discount_expr = "COALESCE(discount_amount,0)" if "discount_amount" in cols else "0"
            net_expr = "COALESCE(net_amount,0)" if "net_amount" in cols else "0"
            shifts_expr = "COALESCE(closed_shifts,0)" if "closed_shifts" in cols else "0"
            period_expr = "period_id" if "period_id" in cols else "id"
            employee_expr = "employee_id" if "employee_id" in cols else "id"
            data = await rows(
                db,
                f"""
                SELECT
                  COUNT(DISTINCT {period_expr})::int AS periods,
                  COUNT(DISTINCT {employee_expr})::int AS people,
                  COALESCE(SUM({regular_expr}),0)::int AS regular_minutes,
                  COALESCE(SUM({extra_expr}),0)::int AS extra_minutes,
                  COALESCE(SUM({shifts_expr}),0)::int AS closed_shifts,
                  COALESCE(SUM({gross_expr}),0)::float AS gross_amount,
                  COALESCE(SUM({discount_expr}),0)::float AS discount_amount,
                  COALESCE(SUM({net_expr}),0)::float AS net_amount
                FROM payroll_period_items
                WHERE company_id = CAST(:company_id AS uuid)
                  AND created_at >= CAST(:start_ts AS timestamptz)
                  AND created_at <= CAST(:end_ts AS timestamptz)
                """,
                params,
            )
            if data:
                out.update(data[0])
                out["source"] = "period_items_created_at_fallback"

    return out

def build_alerts(data: dict[str, Any], modules: set[str]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    inv = data.get("inventory", {})
    if "inventory" in modules or "stock" in modules:
        if int_num(inv.get("zero_stock")) > 0:
            alerts.append({"level": "critical", "module": "inventory", "title": "Stock en cero", "value": int_num(inv.get("zero_stock"))})
        if int_num(inv.get("low_stock")) > 0:
            alerts.append({"level": "warning", "module": "inventory", "title": "Stock bajo", "value": int_num(inv.get("low_stock"))})
    gps = data.get("gps", {})
    if "gps" in modules and int_num(gps.get("outside")) > 0:
        alerts.append({"level": "warning", "module": "gps", "title": "Ubicaciones fuera de perímetro", "value": int_num(gps.get("outside"))})
    mats = data.get("materials", {})
    if "materials" in modules and int_num(mats.get("pending")) > 0:
        alerts.append({"level": "info", "module": "materials", "title": "Solicitudes pendientes", "value": int_num(mats.get("pending"))})
    attendance = data.get("attendance", {})
    if "workforce" in modules and int_num(attendance.get("paused_now")) > 0:
        alerts.append({"level": "info", "module": "workforce", "title": "Personal en pausa", "value": int_num(attendance.get("paused_now"))})
    return alerts[:10]


def build_cards(data: dict[str, Any], modules: set[str]) -> list[dict[str, Any]]:
    employees = data.get("employees", {})
    attendance = data.get("attendance", {})
    gps = data.get("gps", {})
    materials = data.get("materials", {})
    inventory = data.get("inventory", {})
    payroll = data.get("payroll", {})

    cards = [
        {"key": "workforce.active_employees", "label": "Personal activo", "value": int_num(employees.get("active")), "module": "workforce", "format": "number"},
        {"key": "workforce.active_now", "label": "Activos ahora", "value": int_num(attendance.get("active_now")), "module": "workforce", "format": "number"},
        {"key": "workforce.paused_now", "label": "En pausa", "value": int_num(attendance.get("paused_now")), "module": "workforce", "format": "number"},
        {"key": "workforce.events", "label": "Eventos del periodo", "value": int_num(attendance.get("events")), "module": "workforce", "format": "number"},
    ]

    if "gps" in modules:
        cards += [
            {"key": "gps.locations", "label": "Ubicaciones enviadas", "value": int_num(gps.get("locations")), "module": "gps", "format": "number"},
            {"key": "gps.inside", "label": "GPS dentro", "value": int_num(gps.get("inside")), "module": "gps", "format": "number"},
            {"key": "gps.outside", "label": "GPS fuera", "value": int_num(gps.get("outside")), "module": "gps", "format": "number"},
        ]

    if "materials" in modules:
        cards += [
            {"key": "materials.total", "label": "Solicitudes material", "value": int_num(materials.get("total")), "module": "materials", "format": "number"},
            {"key": "materials.delivered", "label": "Material entregado", "value": int_num(materials.get("delivered")), "module": "materials", "format": "number"},
            {"key": "materials.returned", "label": "Material devuelto", "value": int_num(materials.get("returned")) + int_num(materials.get("returned_partial")), "module": "materials", "format": "number"},
            {"key": "materials.consigned", "label": "Material en consigna", "value": int_num(materials.get("consigned")) + int_num(materials.get("consigned_partial")), "module": "materials", "format": "number"},
            {"key": "materials.pending", "label": "Material pendiente", "value": int_num(materials.get("pending")), "module": "materials", "format": "number"},
        ]

    if "inventory" in modules or "stock" in modules:
        cards += [
            {"key": "inventory.active", "label": "Items inventario", "value": int_num(inventory.get("active")), "module": "inventory", "format": "number"},
            {"key": "inventory.low_stock", "label": "Stock bajo", "value": int_num(inventory.get("low_stock")), "module": "inventory", "format": "number"},
            {"key": "inventory.zero_stock", "label": "Stock en cero", "value": int_num(inventory.get("zero_stock")), "module": "inventory", "format": "number"},
            {"key": "inventory.movements_out", "label": "Salidas inventario", "value": num(inventory.get("movements_out")), "module": "inventory", "format": "number"},
        ]

    if "payroll" in modules:
        cards += [
            {"key": "payroll.regular_hours", "label": "Horas ordinarias", "value": round(num(payroll.get("regular_minutes")) / 60, 2), "module": "payroll", "format": "number"},
            {"key": "payroll.extra_hours", "label": "Horas extra", "value": round(num(payroll.get("extra_minutes")) / 60, 2), "module": "payroll", "format": "number"},
            {"key": "payroll.closed_shifts", "label": "Turnos con corte", "value": int_num(payroll.get("closed_shifts")), "module": "payroll", "format": "number"},
            {"key": "payroll.gross_amount", "label": "Bruto nómina", "value": round(num(payroll.get("gross_amount")), 2), "module": "payroll", "format": "money"},
            {"key": "payroll.discount_amount", "label": "Descuentos nómina", "value": round(num(payroll.get("discount_amount")), 2), "module": "payroll", "format": "money"},
            {"key": "payroll.net_amount", "label": "Nómina estimada", "value": round(num(payroll.get("net_amount")), 2), "module": "payroll", "format": "money"},
        ]

    return cards


async def dashboard_card_config(db: AsyncSession, company_id: UUID) -> dict[str, bool]:
    await ensure_dashboard_schema(db)
    data = await rows(
        db,
        """
        SELECT card_key, enabled
        FROM company_kpi_dashboard_cards
        WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY sort_order ASC, card_key ASC
        """,
        {"company_id": str(company_id)},
    )
    return {str(item.get("card_key")): bool(item.get("enabled")) for item in data}


async def apply_dashboard_config(db: AsyncSession, company_id: UUID, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cfg = await dashboard_card_config(db, company_id)

    # Default visual para dashboard principal si todavía no hay configuración.
    if not cfg:
        default_keys = {"workforce.active_now", "gps.inside", "materials.delivered", "inventory.low_stock", "payroll.net_amount"}
    else:
        default_keys = set()

    output = []
    for item in cards:
        key = str(item.get("key") or "")
        selected = bool(cfg.get(key, key in default_keys))
        clone = dict(item)
        clone["show_on_dashboard"] = selected
        output.append(clone)
    return output


@router.get("/companies/{company_id}/summary")
async def kpi_summary(
    company_id: UUID,
    preset: str = Query("7d"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    start, end, period_code = period_from_params(preset, start_date, end_date)
    modules = await active_modules(db, company_id)

    data: dict[str, Any] = {
        "company_id": str(company_id),
        "period": {"preset": period_code, "start": start.isoformat(), "end": end.isoformat()},
        "modules": sorted(modules),
        "employees": {},
        "attendance": {},
        "gps": {},
        "inventory": {},
        "materials": {},
        "payroll": {},
        "alerts": [],
        "cards": [],
        "dashboard_cards": [],
    }

    # Cada bloque falla aislado. KPIs nunca debe tumbar /client.
    try:
        data["employees"] = await employee_kpis(db, company_id)
    except Exception:
        await safe_rollback(db)
        data["employees"] = {}
    try:
        data["attendance"] = await attendance_kpis(db, company_id, start, end)
    except Exception:
        await safe_rollback(db)
        data["attendance"] = {}
    if "gps" in modules:
        try:
            data["gps"] = await gps_kpis(db, company_id, start, end)
        except Exception:
            await safe_rollback(db)
            data["gps"] = {}
    if "inventory" in modules or "stock" in modules:
        try:
            data["inventory"] = await inventory_kpis(db, company_id, start, end)
        except Exception:
            await safe_rollback(db)
            data["inventory"] = {}
    if "materials" in modules:
        try:
            data["materials"] = await material_kpis(db, company_id, start, end)
        except Exception:
            await safe_rollback(db)
            data["materials"] = {}
    if "payroll" in modules:
        try:
            data["payroll"] = await payroll_kpis(db, company_id, start, end)
        except Exception:
            await safe_rollback(db)
            data["payroll"] = {}

    data["alerts"] = build_alerts(data, modules)
    cards = build_cards(data, modules)
    cards = await apply_dashboard_config(db, company_id, cards)
    data["cards"] = cards
    data["dashboard_cards"] = [card for card in cards if card.get("show_on_dashboard")][:4]
    return data




@router.get("/companies/{company_id}/dashboard-cards")
async def get_dashboard_cards(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_dashboard_schema(db)
    cfg = await dashboard_card_config(db, company_id)
    return {"company_id": str(company_id), "cards": [{"key": key, "enabled": enabled} for key, enabled in cfg.items()]}


@router.post("/companies/{company_id}/dashboard-cards")
async def save_dashboard_cards(
    company_id: UUID,
    payload: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_dashboard_schema(db)
    cards_raw = payload.get("cards", [])
    if not isinstance(cards_raw, list):
        cards_raw = []

    selected = []
    for item in cards_raw:
        if isinstance(item, str):
            key = item.strip()
            enabled = True
        elif isinstance(item, dict):
            key = str(item.get("key") or item.get("card_key") or "").strip()
            enabled = bool(item.get("enabled", True))
        else:
            continue
        if key and len(key) <= 140:
            selected.append({"key": key, "enabled": enabled})

    # Limpieza lógica: primero apaga todo y luego prende lo seleccionado.
    await db.execute(
        text("""
            UPDATE company_kpi_dashboard_cards
            SET enabled = false, updated_at = now()
            WHERE company_id = CAST(:company_id AS uuid)
        """),
        {"company_id": str(company_id)},
    )

    for idx, item in enumerate(selected[:12]):
        await db.execute(
            text("""
                INSERT INTO company_kpi_dashboard_cards (company_id, card_key, enabled, sort_order, created_at, updated_at)
                VALUES (CAST(:company_id AS uuid), CAST(:card_key AS varchar), :enabled, :sort_order, now(), now())
                ON CONFLICT (company_id, card_key)
                DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    sort_order = EXCLUDED.sort_order,
                    updated_at = now()
            """),
            {
                "company_id": str(company_id),
                "card_key": item["key"],
                "enabled": bool(item["enabled"]),
                "sort_order": idx + 1,
            },
        )

    await db.commit()
    cfg = await dashboard_card_config(db, company_id)
    return {"company_id": str(company_id), "cards": [{"key": key, "enabled": enabled} for key, enabled in cfg.items()]}
