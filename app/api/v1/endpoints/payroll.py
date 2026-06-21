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
DEFAULT_COMPANY_PAYROLL_ORDINARY_HOURS = Decimal("48")


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


def current_biweekly_period(reference: date | None = None) -> tuple[date, date]:
    today = reference or utcnow().date()
    start = today.replace(day=1 if today.day <= 15 else 16)
    return start, today


def period_from_payload(data: dict) -> tuple[date, date]:
    start_raw = data.get("period_start") or data.get("from") or data.get("date_from")
    end_raw = data.get("period_end") or data.get("to") or data.get("date_to")
    default_start, default_end = current_biweekly_period()
    period_start = date_from_payload(start_raw or default_start, "period_start")
    period_end = date_from_payload(end_raw or default_end, "period_end")
    return period_start, period_end


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


async def _cx_payroll_table_exists_023o(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("SELECT to_regclass(:table_name) IS NOT NULL AS exists"),
        {"table_name": f"public.{table_name}"},
    )
    row = result.mappings().first()
    return bool(row and row.get("exists"))


def _cx_payroll_dt_023o(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _cx_payroll_int_023o(value: Any) -> int:
    try:
        return max(0, int(Decimal(str(value or 0))))
    except Exception:
        return 0


def _cx_payroll_seconds_between_023o(start: Any, end: datetime) -> int:
    started = _cx_payroll_dt_023o(start)
    if not started:
        return 0
    return max(0, int((end - started).total_seconds()))


def _cx_payroll_session_payable_seconds_023o(session: dict, as_of: datetime) -> int:
    status_value = str(session.get("status") or "").strip().lower()
    active_seconds = _cx_payroll_int_023o(session.get("active_seconds"))
    break_seconds = _cx_payroll_int_023o(session.get("break_seconds"))

    if status_value == "active":
        active_seconds += _cx_payroll_seconds_between_023o(session.get("active_started_at"), as_of)

    if active_seconds <= 0:
        started_at = _cx_payroll_dt_023o(session.get("started_at"))
        ended_at = _cx_payroll_dt_023o(session.get("ended_at")) or as_of
        if started_at and ended_at:
            active_seconds = max(0, int((ended_at - started_at).total_seconds()) - break_seconds)

    return max(0, active_seconds)


def _cx_payroll_event_session_id_023o(event: dict) -> str | None:
    payload = parse_payload(event.get("payload_json")) or parse_payload(event.get("metadata_json"))
    if not isinstance(payload, dict):
        return None
    raw = (
        payload.get("mini_panel_session_id")
        or payload.get("session_id")
        or payload.get("operational_session_id")
    )
    return str(raw) if raw else None


async def _cx_payroll_mini_panel_sessions_023o(
    db: AsyncSession,
    company_id: UUID,
    start_dt: datetime,
    end_dt: datetime,
    as_of: datetime,
) -> list[dict]:
    if not await _cx_payroll_table_exists_023o(db, "mini_panel_work_sessions"):
        return []

    result = await db.execute(
        text("""
            SELECT
                s.id,
                s.company_id,
                s.user_id,
                s.employee_id,
                s.panel_type,
                s.status,
                s.location_label,
                s.started_at,
                s.ended_at,
                s.active_seconds,
                s.break_seconds,
                s.active_started_at,
                s.current_break_started_at,
                s.created_at,
                s.updated_at,
                e.full_name AS employee_name,
                e.role AS employee_role,
                e.hourly_rate_regular,
                e.hourly_rate_extra,
                e.deduction_1,
                e.deduction_2
            FROM mini_panel_work_sessions s
            JOIN employees e
              ON e.id = s.employee_id
             AND e.company_id = s.company_id
            WHERE s.company_id = CAST(:company_id AS uuid)
              AND s.employee_id IS NOT NULL
              AND COALESCE(e.status, 'active') != 'archived'
              AND s.started_at <= :end_dt
              AND COALESCE(s.ended_at, :as_of) >= :start_dt
              AND COALESCE(s.status, 'active') IN ('active', 'break', 'finished')
            ORDER BY s.started_at ASC
        """),
        {
            "company_id": str(company_id),
            "start_dt": start_dt,
            "end_dt": end_dt,
            "as_of": as_of,
        },
    )
    return [dict(row) for row in result.mappings().all()]




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
    """
    CLONEXA 017I:
    Source of truth de la regla de nÃ³mina por tenant.

    Primero lee companies.settings_json/client_settings, que es donde el portal /client
    guarda los ajustes por company_id. Mantiene fallback a company_settings para
    compatibilidad con hotfixes antiguos.
    """
    hours_limit = None
    source = None

    async def _json_from_row_value(value):
        if value is None:
            return {}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return value if isinstance(value, dict) else {}

    def _extract_hours(settings: dict):
        if not isinstance(settings, dict):
            return None

        client = settings.get("client_settings") if isinstance(settings.get("client_settings"), dict) else {}
        payroll = client.get("payroll") if isinstance(client.get("payroll"), dict) else {}
        direct_payroll = settings.get("payroll") if isinstance(settings.get("payroll"), dict) else {}

        candidates = [
            payroll.get("ordinary_hours_limit"),
            client.get("payroll_regular_hours_limit"),
            direct_payroll.get("ordinary_hours_limit"),
            settings.get("payroll_regular_hours_limit"),
        ]

        for candidate in candidates:
            if candidate is not None and candidate != "":
                return candidate
        return None

    allowed_company_json_columns = [
        "settings_json",
        "experience_json",
        "metadata_json",
        "branding_json",
    ]

    columns_result = await db.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'companies'
          AND column_name IN ('settings_json', 'experience_json', 'metadata_json', 'branding_json')
    """))
    existing_columns = [
        str(row["column_name"])
        for row in columns_result.mappings().all()
        if str(row["column_name"]) in allowed_company_json_columns
    ]

    for column in existing_columns:
        company_result = await db.execute(
            text(f"""
                SELECT {column} AS settings_json
                FROM companies
                WHERE id::text = :company_id
                LIMIT 1
            """),
            {"company_id": str(company_id)},
        )
        row = company_result.mappings().first()
        if not row:
            continue

        settings = await _json_from_row_value(row.get("settings_json"))
        extracted = _extract_hours(settings)
        if extracted is not None:
            hours_limit = extracted
            source = f"companies.{column}.client_settings"
            break

    if hours_limit is None:
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
        if row:
            settings = await _json_from_row_value(row.get("settings_json"))
            extracted = _extract_hours(settings)
            if extracted is None:
                legacy_payroll = settings.get("payroll") if isinstance(settings.get("payroll"), dict) else {}
                extracted = legacy_payroll.get("ordinary_hours_limit")
            if extracted is not None:
                hours_limit = extracted
                source = "company_settings.settings_json"

    if hours_limit is None or hours_limit == "":
        minutes = int(DEFAULT_COMPANY_PAYROLL_ORDINARY_HOURS * Decimal(60))
        return {
            "enabled": True,
            "source": "company_default_payroll_rule",
            "label": f"Valor base de empresa: hasta {DEFAULT_COMPANY_PAYROLL_ORDINARY_HOURS:g}h ordinarias; después extra. Pausas excluidas.",
            "ordinary_hours_limit": float(DEFAULT_COMPANY_PAYROLL_ORDINARY_HOURS),
            "ordinary_minutes_limit": minutes,
            "pause_policy": "exclude",
            "scope": "company_default_when_missing_settings",
        }

    hours = _cx_payroll_number(hours_limit, 0.0)

    if hours <= 0 or hours > 168:
        return {
            "enabled": False,
            "source": "invalid_company_settings",
            "label": "ConfiguraciÃ³n invÃ¡lida: total de horas ordinarias no vÃ¡lido",
            "ordinary_hours_limit": None,
            "ordinary_minutes_limit": None,
            "pause_policy": "exclude",
        }

    minutes = int(round(hours * 60))

    return {
        "enabled": True,
        "source": source or "company_client_settings",
        "label": f"Hasta {hours:g}h ordinarias; despuÃ©s extra. Pausas excluidas.",
        "ordinary_hours_limit": hours,
        "ordinary_minutes_limit": minutes,
        "pause_policy": "exclude",
        "scope": "company_override",
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
        row["payroll_rule"] = {**rule, "applied_by": "CX_017I_COMPANY_PAYROLL_RULE"}

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
    totals["payroll_rule"] = {**rule, "applied_by": "CX_017I_COMPANY_PAYROLL_RULE"}

    snapshot["rows"] = rows
    snapshot["totals"] = totals
    return snapshot


async def calculate_period_snapshot(db: AsyncSession, company_id: UUID, period_start: date, period_end: date) -> dict:
    start_dt = datetime.combine(period_start, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(period_end, time.max).replace(tzinfo=timezone.utc)
    lookback_dt = start_dt - timedelta(days=2)
    as_of = min(utcnow(), end_dt)

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
              AND ev.event_type IN (
                  'check_in', 'entrada', 'start_shift', 'shift_start',
                  'break_start', 'pausa', 'pause', 'on_break',
                  'break_end', 'reanudar', 'resume', 'retomar',
                  'check_out', 'salida', 'end_shift', 'shift_end'
              )
            ORDER BY COALESCE(ev.occurred_at, ev.created_at) ASC
        """),
        {
            "company_id": str(company_id),
            "lookback_dt": lookback_dt,
            "end_dt": end_dt,
        },
    )
    events = [dict(row) for row in events_result.mappings().all()]
    mini_panel_sessions = await _cx_payroll_mini_panel_sessions_023o(db, company_id, start_dt, end_dt, as_of)
    mini_panel_session_ids = {str(row.get("id")) for row in mini_panel_sessions if row.get("id")}

    rows_by_employee: dict[str, dict] = {}

    def ensure_employee_row(employee_id: str, employee: dict | None = None, fallback: dict | None = None) -> dict:
        employee = employee or {}
        fallback = fallback or {}
        row = rows_by_employee.get(employee_id)
        if row:
            return row

        row = {
            "employee_id": employee_id,
            "employee_name": employee.get("full_name") or employee.get("employee_name") or fallback.get("employee_name") or "Colaborador",
            "employee_role": employee.get("role") or employee.get("employee_role") or fallback.get("employee_role") or "",
            "closed_shifts": 0,
            "regular_minutes": 0,
            "extra_minutes": 0,
            "hourly_rate_regular": money(employee.get("hourly_rate_regular")),
            "hourly_rate_extra": money(employee.get("hourly_rate_extra")),
            "deduction_1": money(employee.get("deduction_1")),
            "deduction_2": money(employee.get("deduction_2")),
            "gross_amount": Decimal("0"),
            "discount_amount": Decimal("0"),
            "net_amount": Decimal("0"),
            "shifts": [],
        }
        rows_by_employee[employee_id] = row
        return row

    def add_payroll_shift(row: dict, regular_minutes: int, extra_minutes: int, gross: Decimal, shift_payload: dict) -> None:
        row["closed_shifts"] += 1
        row["regular_minutes"] += max(0, int(regular_minutes))
        row["extra_minutes"] += max(0, int(extra_minutes))
        row["gross_amount"] += money(gross)
        row["shifts"].append(shift_payload)

    for shift in build_closed_shifts(events):
        if not shift.get("end") or shift["end"] < start_dt or shift["end"] > end_dt:
            continue

        employee_id = str(shift["employee_id"])
        employee = employee_map.get(employee_id, {})
        check_out_event = shift.get("check_out_event") or {}
        event_session_id = _cx_payroll_event_session_id_023o(check_out_event)
        if event_session_id and event_session_id in mini_panel_session_ids:
            continue

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

        row = ensure_employee_row(employee_id, employee, check_out_event)

        if projected_pay:
            gross = projected_pay
        else:
            gross = ((Decimal(regular_minutes) / Decimal(60)) * row["hourly_rate_regular"])
            gross += ((Decimal(extra_minutes) / Decimal(60)) * row["hourly_rate_extra"])
            gross = gross.quantize(MONEY, rounding=ROUND_HALF_UP)

        add_payroll_shift(row, regular_minutes, extra_minutes, gross, {
            "start": shift["start"].isoformat(),
            "end": shift["end"].isoformat(),
            "regular_minutes": regular_minutes,
            "extra_minutes": extra_minutes,
            "gross_amount": str(gross),
            "source": "attendance",
            "mini_panel_session_id": event_session_id,
        })

    for session in mini_panel_sessions:
        employee_id = str(session.get("employee_id") or "")
        if not employee_id:
            continue

        status_value = str(session.get("status") or "active").strip().lower()
        session_start = _cx_payroll_dt_023o(session.get("started_at"))
        session_end = _cx_payroll_dt_023o(session.get("ended_at"))
        if status_value == "finished":
            if not session_end or session_end < start_dt or session_end > end_dt:
                continue
            session_as_of = session_end
        else:
            if not session_start or session_start > end_dt or as_of < start_dt:
                continue
            session_as_of = as_of

        payable_seconds = _cx_payroll_session_payable_seconds_023o(session, session_as_of)
        payable_minutes = max(0, round(payable_seconds / 60))
        if payable_minutes <= 0:
            continue

        employee = employee_map.get(employee_id, session)
        row = ensure_employee_row(employee_id, employee, session)
        regular_minutes = min(payable_minutes, 480)
        extra_minutes = max(0, payable_minutes - 480)
        gross = ((Decimal(regular_minutes) / Decimal(60)) * row["hourly_rate_regular"])
        gross += ((Decimal(extra_minutes) / Decimal(60)) * row["hourly_rate_extra"])
        gross = gross.quantize(MONEY, rounding=ROUND_HALF_UP)

        add_payroll_shift(row, regular_minutes, extra_minutes, gross, {
            "start": session_start.isoformat() if session_start else None,
            "end": session_end.isoformat() if session_end else session_as_of.isoformat(),
            "regular_minutes": regular_minutes,
            "extra_minutes": extra_minutes,
            "gross_amount": str(gross),
            "source": "mini_panel_work_sessions",
            "status": status_value,
            "panel_type": session.get("panel_type"),
            "mini_panel_session_id": str(session.get("id")) if session.get("id") else None,
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
    period_start, period_end = period_from_payload(data)

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
    period_start, period_end = period_from_payload(data)

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
