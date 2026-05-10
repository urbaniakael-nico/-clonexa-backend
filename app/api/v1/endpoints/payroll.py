from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


MONEY = Decimal("0.01")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0")


def date_from_payload(value: Any, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{field}_invalid") from exc


def as_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value.quantize(MONEY, rounding=ROUND_HALF_UP))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize_value(v) for v in value]
    return value


def row_to_dict(row: Any) -> dict:
    if row is None:
        return {}
    mapping = getattr(row, "_mapping", row)
    data = dict(mapping)
    return {key: serialize_value(value) for key, value in data.items()}


def uuid_or_none(value: Any) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(str(value)))
    except Exception:
        return None


async def ensure_payroll_storage(db: AsyncSession) -> None:
    """
    CLONEXA 013-R2:
    Storage idempotente y compatible con tablas parciales creadas por hotfixes anteriores.
    Si payroll_periods/payroll_period_items ya existen incompletas, agrega columnas faltantes
    antes de crear índices. No borra datos.
    """
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS payroll_periods (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name varchar(180) NOT NULL DEFAULT 'Nómina',
            period_start date,
            period_end date,
            status varchar(40) NOT NULL DEFAULT 'closed',
            currency varchar(12) NOT NULL DEFAULT 'USD',
            totals_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            closed_at timestamptz NULL
        );
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS payroll_period_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            period_id uuid NULL REFERENCES payroll_periods(id) ON DELETE CASCADE,
            company_id uuid NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NULL REFERENCES employees(id) ON DELETE SET NULL,
            employee_name varchar(180) NOT NULL DEFAULT 'Sin nombre',
            employee_role varchar(80) NULL,
            closed_shifts integer NOT NULL DEFAULT 0,
            regular_minutes integer NOT NULL DEFAULT 0,
            extra_minutes integer NOT NULL DEFAULT 0,
            hourly_rate_regular numeric(14,2) NOT NULL DEFAULT 0,
            hourly_rate_extra numeric(14,2) NOT NULL DEFAULT 0,
            deduction_1 numeric(14,2) NOT NULL DEFAULT 0,
            deduction_2 numeric(14,2) NOT NULL DEFAULT 0,
            gross_amount numeric(14,2) NOT NULL DEFAULT 0,
            discount_amount numeric(14,2) NOT NULL DEFAULT 0,
            net_amount numeric(14,2) NOT NULL DEFAULT 0,
            item_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """))

    # Compatibilidad con tablas ya creadas incompletas.
    # PostgreSQL no agrega columnas ni defaults cuando CREATE TABLE IF NOT EXISTS encuentra una tabla previa.
    # 013-R3: si las tablas parciales existen con id NOT NULL pero sin DEFAULT, el cierre fallaba.
    await db.execute(text("ALTER TABLE payroll_periods ALTER COLUMN id SET DEFAULT gen_random_uuid();"))
    await db.execute(text("ALTER TABLE payroll_period_items ALTER COLUMN id SET DEFAULT gen_random_uuid();"))
    await db.execute(text("UPDATE payroll_periods SET id = gen_random_uuid() WHERE id IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET id = gen_random_uuid() WHERE id IS NULL;"))

    # PostgreSQL no agrega columnas cuando CREATE TABLE IF NOT EXISTS encuentra una tabla previa.
    payroll_period_columns = [
        ("company_id", "uuid"),
        ("name", "varchar(180)"),
        ("period_start", "date"),
        ("period_end", "date"),
        ("status", "varchar(40)"),
        ("currency", "varchar(12)"),
        ("totals_json", "jsonb"),
        ("snapshot_json", "jsonb"),
        ("created_at", "timestamptz"),
        ("updated_at", "timestamptz"),
        ("closed_at", "timestamptz"),
    ]
    for column_name, column_type in payroll_period_columns:
        await db.execute(text(f"ALTER TABLE payroll_periods ADD COLUMN IF NOT EXISTS {column_name} {column_type};"))

    await db.execute(text("UPDATE payroll_periods SET name = COALESCE(NULLIF(name, ''), 'Nómina') WHERE name IS NULL OR name = '';"))
    await db.execute(text("UPDATE payroll_periods SET status = COALESCE(NULLIF(status, ''), 'closed') WHERE status IS NULL OR status = '';"))
    await db.execute(text("UPDATE payroll_periods SET currency = COALESCE(NULLIF(currency, ''), 'USD') WHERE currency IS NULL OR currency = '';"))
    await db.execute(text("UPDATE payroll_periods SET totals_json = '{}'::jsonb WHERE totals_json IS NULL;"))
    await db.execute(text("UPDATE payroll_periods SET snapshot_json = '{}'::jsonb WHERE snapshot_json IS NULL;"))
    await db.execute(text("UPDATE payroll_periods SET created_at = now() WHERE created_at IS NULL;"))
    await db.execute(text("UPDATE payroll_periods SET updated_at = now() WHERE updated_at IS NULL;"))

    payroll_item_columns = [
        ("period_id", "uuid"),
        ("company_id", "uuid"),
        ("employee_id", "uuid"),
        ("employee_name", "varchar(180)"),
        ("employee_role", "varchar(80)"),
        ("closed_shifts", "integer"),
        ("regular_minutes", "integer"),
        ("extra_minutes", "integer"),
        ("hourly_rate_regular", "numeric(14,2)"),
        ("hourly_rate_extra", "numeric(14,2)"),
        ("deduction_1", "numeric(14,2)"),
        ("deduction_2", "numeric(14,2)"),
        ("gross_amount", "numeric(14,2)"),
        ("discount_amount", "numeric(14,2)"),
        ("net_amount", "numeric(14,2)"),
        ("item_json", "jsonb"),
        ("created_at", "timestamptz"),
    ]
    for column_name, column_type in payroll_item_columns:
        await db.execute(text(f"ALTER TABLE payroll_period_items ADD COLUMN IF NOT EXISTS {column_name} {column_type};"))

    await db.execute(text("UPDATE payroll_period_items SET employee_name = COALESCE(NULLIF(employee_name, ''), 'Sin nombre') WHERE employee_name IS NULL OR employee_name = '';"))
    await db.execute(text("UPDATE payroll_period_items SET closed_shifts = 0 WHERE closed_shifts IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET regular_minutes = 0 WHERE regular_minutes IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET extra_minutes = 0 WHERE extra_minutes IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET hourly_rate_regular = 0 WHERE hourly_rate_regular IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET hourly_rate_extra = 0 WHERE hourly_rate_extra IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET deduction_1 = 0 WHERE deduction_1 IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET deduction_2 = 0 WHERE deduction_2 IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET gross_amount = 0 WHERE gross_amount IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET discount_amount = 0 WHERE discount_amount IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET net_amount = 0 WHERE net_amount IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET item_json = '{}'::jsonb WHERE item_json IS NULL;"))
    await db.execute(text("UPDATE payroll_period_items SET created_at = now() WHERE created_at IS NULL;"))

    # Índices seguros. El índice único es parcial para no fallar con filas antiguas incompletas.
    await db.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_periods_company_range
          ON payroll_periods(company_id, period_start, period_end)
          WHERE company_id IS NOT NULL AND period_start IS NOT NULL AND period_end IS NOT NULL;
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_payroll_periods_company ON payroll_periods(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_payroll_periods_range ON payroll_periods(company_id, period_start, period_end);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_payroll_items_period ON payroll_period_items(period_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_payroll_items_company_employee ON payroll_period_items(company_id, employee_id);"))
    await db.commit()


def event_type(value: Any) -> str:
    return str(value or "").strip().lower()


def is_check_in(value: str) -> bool:
    return value in {"check_in", "entrada", "start_shift", "shift_start"}


def is_break_start(value: str) -> bool:
    return value in {"break_start", "pausa", "pause", "on_break"}


def is_break_end(value: str) -> bool:
    return value in {"break_end", "reanudar", "resume", "retomar"}


def is_check_out(value: str) -> bool:
    return value in {"check_out", "salida", "end_shift", "shift_end"}


def parse_payload(value: Any) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def payroll_projection_from_event(event: dict) -> dict | None:
    payload = parse_payload(event.get("payload_json")) or parse_payload(event.get("metadata_json"))
    projection = payload.get("payroll_projection") or payload.get("payroll") or payload
    if not isinstance(projection, dict):
        return None

    regular_minutes = int(Decimal(str(projection.get("regular_minutes") or projection.get("regularMinutes") or 0)))
    extra_minutes = int(Decimal(str(projection.get("extra_minutes") or projection.get("extraMinutes") or 0)))
    projected_pay = money(projection.get("projected_pay") or projection.get("projectedPay") or 0)

    if not regular_minutes and not extra_minutes and not projected_pay:
        return None

    return {
        "regular_minutes": max(0, regular_minutes),
        "extra_minutes": max(0, extra_minutes),
        "projected_pay": projected_pay,
    }


def build_closed_shifts(events: list[dict]) -> list[dict]:
    sorted_events = sorted(
        [ev for ev in events if ev.get("occurred_at")],
        key=lambda ev: ev["occurred_at"],
    )

    open_shifts: dict[str, dict] = {}
    closed: list[dict] = []

    for ev in sorted_events:
        employee_id = str(ev.get("employee_id") or "")
        if not employee_id:
            continue

        etype = event_type(ev.get("event_type"))
        occurred_at = ev.get("occurred_at")
        if not isinstance(occurred_at, datetime):
            continue

        if is_check_in(etype):
            open_shifts[employee_id] = {
                "employee_id": employee_id,
                "start": occurred_at,
                "end": None,
                "pauses_seconds": 0,
                "pause_start": None,
                "check_out_event": None,
            }
            continue

        shift = open_shifts.get(employee_id)
        if not shift:
            continue

        if is_break_start(etype):
            if not shift["pause_start"]:
                shift["pause_start"] = occurred_at
            continue

        if is_break_end(etype):
            if shift["pause_start"]:
                shift["pauses_seconds"] += max(0, int((occurred_at - shift["pause_start"]).total_seconds()))
                shift["pause_start"] = None
            continue

        if is_check_out(etype):
            if shift["pause_start"]:
                shift["pauses_seconds"] += max(0, int((occurred_at - shift["pause_start"]).total_seconds()))
                shift["pause_start"] = None

            shift["end"] = occurred_at
            shift["check_out_event"] = ev
            closed.append(shift)
            open_shifts.pop(employee_id, None)

    return closed




# CLONEXA CORE_PAYROLL_CONFIG_01
def _cx_payroll_number(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(str(value).replace(",", "."))
    except Exception:
        return float(default)


def _cx_payroll_money(value) -> float:
    return round(_cx_payroll_number(value, 0.0), 2)


async def _cx_ensure_company_settings_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_settings (
            company_id text PRIMARY KEY,
            settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))


async def _cx_company_payroll_rule(db: AsyncSession, company_id) -> dict:
    await _cx_ensure_company_settings_storage(db)

    result = await db.execute(
        text("""
            SELECT settings_json
            FROM company_settings
            WHERE company_id = :company_id
            LIMIT 1
        """),
        {"company_id": str(company_id)},
    )

    row = result.mappings().first()
    settings = {}

    if row:
        raw = row.get("settings_json") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        if isinstance(raw, dict):
            settings = raw

    payroll_settings = settings.get("payroll") if isinstance(settings.get("payroll"), dict) else {}
    hours_limit = payroll_settings.get("ordinary_hours_limit")

    if hours_limit is None or hours_limit == "":
        return {
            "enabled": False,
            "source": "legacy_payroll_calculation",
            "label": "Regla actual del sistema",
            "ordinary_hours_limit": None,
            "ordinary_minutes_limit": None,
            "pause_policy": "exclude",
        }

    hours = _cx_payroll_number(hours_limit, 0.0)

    if hours <= 0:
        return {
            "enabled": False,
            "source": "invalid_company_settings",
            "label": "Configuración inválida: total de horas ordinarias no válido",
            "ordinary_hours_limit": None,
            "ordinary_minutes_limit": None,
            "pause_policy": "exclude",
        }

    minutes = int(round(hours * 60))

    return {
        "enabled": True,
        "source": "company_settings",
        "label": f"Hasta {hours:g}h ordinarias; después extra. Pausas excluidas.",
        "ordinary_hours_limit": hours,
        "ordinary_minutes_limit": minutes,
        "pause_policy": "exclude",
    }


async def _cx_apply_payroll_config_rule(db: AsyncSession, company_id, snapshot: dict) -> dict:
    rule = await _cx_company_payroll_rule(db, company_id)

    snapshot["payroll_rule"] = rule

    if not rule.get("enabled"):
        totals = snapshot.get("totals") if isinstance(snapshot.get("totals"), dict) else {}
        totals["payroll_rule"] = rule
        snapshot["totals"] = totals
        return snapshot

    limit_minutes = int(rule.get("ordinary_minutes_limit") or 0)
    rows = snapshot.get("rows") if isinstance(snapshot.get("rows"), list) else []

    total_regular = 0
    total_extra = 0
    total_gross = 0.0
    total_discounts = 0.0
    total_net = 0.0

    for row in rows:
        current_regular = int(_cx_payroll_number(row.get("regular_minutes"), 0))
        current_extra = int(_cx_payroll_number(row.get("extra_minutes"), 0))
        effective_minutes = current_regular + current_extra

        regular_minutes = min(effective_minutes, limit_minutes)
        extra_minutes = max(effective_minutes - limit_minutes, 0)

        regular_rate = _cx_payroll_money(row.get("hourly_rate_regular"))
        extra_rate = _cx_payroll_money(row.get("hourly_rate_extra"))

        regular_amount = round((regular_minutes / 60.0) * regular_rate, 2)
        extra_amount = round((extra_minutes / 60.0) * extra_rate, 2)
        gross_amount = round(regular_amount + extra_amount, 2)

        discount_amount = _cx_payroll_money(
            row.get("discount_amount", row.get("deduction_amount", row.get("discounts", 0)))
        )
        net_amount = round(gross_amount - discount_amount, 2)

        row["regular_minutes"] = regular_minutes
        row["extra_minutes"] = extra_minutes
        row["regular_amount"] = regular_amount
        row["extra_amount"] = extra_amount
        row["gross_amount"] = gross_amount
        row["discount_amount"] = discount_amount
        row["net_amount"] = net_amount
        row["payroll_rule"] = rule

        total_regular += regular_minutes
        total_extra += extra_minutes
        total_gross += gross_amount
        total_discounts += discount_amount
        total_net += net_amount

    totals = snapshot.get("totals") if isinstance(snapshot.get("totals"), dict) else {}

    totals["regular_minutes"] = total_regular
    totals["extra_minutes"] = total_extra
    totals["gross_amount"] = round(total_gross, 2)
    totals["discount_amount"] = round(total_discounts, 2)
    totals["net_amount"] = round(total_net, 2)
    totals["payroll_rule"] = rule

    snapshot["rows"] = rows
    snapshot["totals"] = totals
    return snapshot


async def calculate_period_snapshot(db: AsyncSession, company_id: UUID, period_start: date, period_end: date) -> dict:
    start_dt = datetime.combine(period_start, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(period_end, time.max).replace(tzinfo=timezone.utc)
    lookback_dt = start_dt - timedelta(days=2)

    employees_result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                full_name,
                role,
                hourly_rate_regular,
                hourly_rate_extra,
                deduction_1,
                deduction_2,
                status
            FROM employees
            WHERE company_id = :company_id
              AND COALESCE(status, 'active') != 'archived'
        """),
        {"company_id": str(company_id)},
    )
    employee_map = {
        str(row["id"]): dict(row)
        for row in employees_result.mappings().all()
    }

    events_result = await db.execute(
        text("""
            SELECT
                ev.id,
                ev.company_id,
                ev.employee_id,
                ev.event_type,
                ev.event_label,
                COALESCE(ev.employee_name, e.full_name) AS employee_name,
                COALESCE(ev.employee_role, e.role) AS employee_role,
                ev.status_after,
                ev.source,
                ev.module_code,
                ev.source_channel,
                ev.detail,
                ev.notes,
                ev.payload_json,
                ev.metadata_json,
                COALESCE(ev.occurred_at, ev.created_at) AS occurred_at,
                ev.created_at
            FROM workforce_attendance_events ev
            LEFT JOIN employees e
              ON e.id = ev.employee_id
             AND e.company_id = ev.company_id
            WHERE ev.company_id = :company_id
              AND COALESCE(ev.occurred_at, ev.created_at) >= :lookback_dt
              AND COALESCE(ev.occurred_at, ev.created_at) <= :end_dt
              AND ev.event_type IN ('check_in', 'break_start', 'break_end', 'check_out')
            ORDER BY COALESCE(ev.occurred_at, ev.created_at) ASC
        """),
        {
            "company_id": str(company_id),
            "lookback_dt": lookback_dt,
            "end_dt": end_dt,
        },
    )
    events = [dict(row) for row in events_result.mappings().all()]

    rows_by_employee: dict[str, dict] = {}

    for shift in build_closed_shifts(events):
        if not shift.get("end") or shift["end"] < start_dt or shift["end"] > end_dt:
            continue

        employee_id = str(shift["employee_id"])
        employee = employee_map.get(employee_id, {})
        check_out_event = shift.get("check_out_event") or {}
        projection = payroll_projection_from_event(check_out_event)

        if projection:
            regular_minutes = int(projection["regular_minutes"])
            extra_minutes = int(projection["extra_minutes"])
            projected_pay = money(projection["projected_pay"])
        else:
            total_seconds = max(0, int((shift["end"] - shift["start"]).total_seconds()) - int(shift["pauses_seconds"]))
            payable_minutes = max(0, round(total_seconds / 60))
            regular_minutes = min(payable_minutes, 480)
            extra_minutes = max(0, payable_minutes - 480)
            projected_pay = Decimal("0")

        row = rows_by_employee.get(employee_id)
        if not row:
            regular_rate = money(employee.get("hourly_rate_regular"))
            extra_rate = money(employee.get("hourly_rate_extra"))
            deduction_1 = money(employee.get("deduction_1"))
            deduction_2 = money(employee.get("deduction_2"))
            row = {
                "employee_id": employee_id,
                "employee_name": employee.get("full_name") or check_out_event.get("employee_name") or "Colaborador",
                "employee_role": employee.get("role") or check_out_event.get("employee_role") or "",
                "closed_shifts": 0,
                "regular_minutes": 0,
                "extra_minutes": 0,
                "hourly_rate_regular": regular_rate,
                "hourly_rate_extra": extra_rate,
                "deduction_1": deduction_1,
                "deduction_2": deduction_2,
                "gross_amount": Decimal("0"),
                "discount_amount": Decimal("0"),
                "net_amount": Decimal("0"),
                "shifts": [],
            }
            rows_by_employee[employee_id] = row

        if projected_pay:
            gross = projected_pay
        else:
            gross = ((Decimal(regular_minutes) / Decimal(60)) * row["hourly_rate_regular"])
            gross += ((Decimal(extra_minutes) / Decimal(60)) * row["hourly_rate_extra"])
            gross = gross.quantize(MONEY, rounding=ROUND_HALF_UP)

        row["closed_shifts"] += 1
        row["regular_minutes"] += regular_minutes
        row["extra_minutes"] += extra_minutes
        row["gross_amount"] += gross
        row["shifts"].append({
            "start": shift["start"].isoformat(),
            "end": shift["end"].isoformat(),
            "regular_minutes": regular_minutes,
            "extra_minutes": extra_minutes,
            "gross_amount": str(gross),
        })

    rows = []
    for row in rows_by_employee.values():
        row["gross_amount"] = money(row["gross_amount"])
        row["discount_amount"] = money(row["deduction_1"] + row["deduction_2"]) if row["closed_shifts"] else Decimal("0")
        row["net_amount"] = money(max(Decimal("0"), row["gross_amount"] - row["discount_amount"]))
        rows.append(row)

    rows.sort(key=lambda item: str(item.get("employee_name") or ""))

    totals = {
        "people": len(rows),
        "closed_shifts": sum(int(row["closed_shifts"]) for row in rows),
        "regular_minutes": sum(int(row["regular_minutes"]) for row in rows),
        "extra_minutes": sum(int(row["extra_minutes"]) for row in rows),
        "gross_amount": money(sum((row["gross_amount"] for row in rows), Decimal("0"))),
        "discount_amount": money(sum((row["discount_amount"] for row in rows), Decimal("0"))),
        "net_amount": money(sum((row["net_amount"] for row in rows), Decimal("0"))),
    }

    serializable_rows = []
    for row in rows:
        item = dict(row)
        for key in ["hourly_rate_regular", "hourly_rate_extra", "deduction_1", "deduction_2", "gross_amount", "discount_amount", "net_amount"]:
            item[key] = float(money(item[key]))
        serializable_rows.append(item)

    serializable_totals = {
        **totals,
        "gross_amount": float(totals["gross_amount"]),
        "discount_amount": float(totals["discount_amount"]),
        "net_amount": float(totals["net_amount"]),
    }

    snapshot_payload = {
        "period": {
            "company_id": str(company_id),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "status": "open",
        },
        "rows": serializable_rows,
        "totals": serializable_totals,
    }

    snapshot_payload = await _cx_apply_payroll_config_rule(db, company_id, snapshot_payload)
    return snapshot_payload


@router.post("/companies/{company_id}/periods/calculate")
async def calculate_payroll_period(
    company_id: UUID,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ensure_payroll_storage(db)

    data = payload or {}
    period_start = date_from_payload(data.get("period_start") or data.get("from") or data.get("date_from"), "period_start")
    period_end = date_from_payload(data.get("period_end") or data.get("to") or data.get("date_to"), "period_end")

    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end_before_start")

    snapshot = await calculate_period_snapshot(db, company_id, period_start, period_end)
    snapshot["source"] = "calculated"
    return snapshot


@router.get("/companies/{company_id}/periods")
async def list_payroll_periods(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await ensure_payroll_storage(db)

    result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                name,
                period_start,
                period_end,
                status,
                currency,
                totals_json,
                created_at,
                updated_at,
                closed_at,
                COALESCE((totals_json->>'net_amount')::numeric, 0) AS net_amount
            FROM payroll_periods
            WHERE company_id = :company_id
            ORDER BY period_start DESC, created_at DESC
            LIMIT 80
        """),
        {"company_id": str(company_id)},
    )
    return [row_to_dict(row) for row in result.mappings().all()]


@router.get("/companies/{company_id}/periods/{period_id}")
async def get_payroll_period(
    company_id: UUID,
    period_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ensure_payroll_storage(db)

    period_result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                name,
                period_start,
                period_end,
                status,
                currency,
                totals_json,
                snapshot_json,
                created_at,
                updated_at,
                closed_at
            FROM payroll_periods
            WHERE company_id = :company_id
              AND id = :period_id
            LIMIT 1
        """),
        {"company_id": str(company_id), "period_id": str(period_id)},
    )
    period = period_result.mappings().first()
    if not period:
        raise HTTPException(status_code=404, detail="payroll_period_not_found")

    items_result = await db.execute(
        text("""
            SELECT
                id,
                period_id,
                company_id,
                employee_id,
                employee_name,
                employee_role,
                closed_shifts,
                regular_minutes,
                extra_minutes,
                hourly_rate_regular,
                hourly_rate_extra,
                deduction_1,
                deduction_2,
                gross_amount,
                discount_amount,
                net_amount,
                item_json,
                created_at
            FROM payroll_period_items
            WHERE period_id = :period_id
              AND company_id = :company_id
            ORDER BY employee_name ASC
        """),
        {"company_id": str(company_id), "period_id": str(period_id)},
    )

    period_dict = row_to_dict(period)
    rows = [row_to_dict(row) for row in items_result.mappings().all()]
    return {
        "period": period_dict,
        "id": period_dict["id"],
        "name": period_dict["name"],
        "period_start": period_dict["period_start"],
        "period_end": period_dict["period_end"],
        "status": period_dict["status"],
        "totals": period_dict.get("totals_json") or {},
        "totals_json": period_dict.get("totals_json") or {},
        "rows": rows,
        "items": rows,
        "source": "closed",
    }


@router.post("/companies/{company_id}/periods/close")
async def close_payroll_period(
    company_id: UUID,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ensure_payroll_storage(db)

    data = payload or {}
    period_start = date_from_payload(data.get("period_start") or data.get("from") or data.get("date_from"), "period_start")
    period_end = date_from_payload(data.get("period_end") or data.get("to") or data.get("date_to"), "period_end")

    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end_before_start")

    existing = await db.execute(
        text("""
            SELECT id
            FROM payroll_periods
            WHERE company_id = :company_id
              AND period_start = :period_start
              AND period_end = :period_end
            LIMIT 1
        """),
        {
            "company_id": str(company_id),
            "period_start": period_start,
            "period_end": period_end,
        },
    )
    existing_id = existing.scalar_one_or_none()
    if existing_id:
        return await get_payroll_period(company_id, UUID(str(existing_id)), db)

    snapshot = await calculate_period_snapshot(db, company_id, period_start, period_end)
    name = str(data.get("name") or f"Nómina {period_start.isoformat()} / {period_end.isoformat()}").strip()
    totals = snapshot["totals"]
    rows = snapshot["rows"]

    period_id = uuid4()

    await db.execute(
        text("""
            INSERT INTO payroll_periods (
                id,
                company_id,
                name,
                period_start,
                period_end,
                status,
                currency,
                totals_json,
                snapshot_json,
                closed_at,
                updated_at
            )
            VALUES (
                :id,
                :company_id,
                :name,
                :period_start,
                :period_end,
                'closed',
                :currency,
                CAST(:totals_json AS jsonb),
                CAST(:snapshot_json AS jsonb),
                now(),
                now()
            )
        """),
        {
            "id": str(period_id),
            "company_id": str(company_id),
            "name": name,
            "period_start": period_start,
            "period_end": period_end,
            "currency": str(data.get("currency") or "USD"),
            "totals_json": as_json(totals),
            "snapshot_json": as_json(snapshot),
        },
    )

    for row in rows:
        await db.execute(
            text("""
                INSERT INTO payroll_period_items (
                    id,
                    period_id,
                    company_id,
                    employee_id,
                    employee_name,
                    employee_role,
                    closed_shifts,
                    regular_minutes,
                    extra_minutes,
                    hourly_rate_regular,
                    hourly_rate_extra,
                    deduction_1,
                    deduction_2,
                    gross_amount,
                    discount_amount,
                    net_amount,
                    item_json
                )
                VALUES (
                    :id,
                    :period_id,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :employee_role,
                    :closed_shifts,
                    :regular_minutes,
                    :extra_minutes,
                    :hourly_rate_regular,
                    :hourly_rate_extra,
                    :deduction_1,
                    :deduction_2,
                    :gross_amount,
                    :discount_amount,
                    :net_amount,
                    CAST(:item_json AS jsonb)
                )
            """),
            {
                "id": str(uuid4()),
                "period_id": str(period_id),
                "company_id": str(company_id),
                "employee_id": uuid_or_none(row.get("employee_id")),
                "employee_name": row.get("employee_name") or "Colaborador",
                "employee_role": row.get("employee_role") or "",
                "closed_shifts": int(row.get("closed_shifts") or 0),
                "regular_minutes": int(row.get("regular_minutes") or 0),
                "extra_minutes": int(row.get("extra_minutes") or 0),
                "hourly_rate_regular": str(money(row.get("hourly_rate_regular"))),
                "hourly_rate_extra": str(money(row.get("hourly_rate_extra"))),
                "deduction_1": str(money(row.get("deduction_1"))),
                "deduction_2": str(money(row.get("deduction_2"))),
                "gross_amount": str(money(row.get("gross_amount"))),
                "discount_amount": str(money(row.get("discount_amount"))),
                "net_amount": str(money(row.get("net_amount"))),
                "item_json": as_json(row),
            },
        )

    await db.commit()
    return await get_payroll_period(company_id, UUID(str(period_id)), db)
