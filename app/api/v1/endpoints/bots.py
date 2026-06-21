from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import re
import logging
import os
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.crm_core_v1 import crm_core_snapshot
from app.api.v1.endpoints.payroll import calculate_period_snapshot, ensure_payroll_storage
from app.api.v1.endpoints.production_v1 import production_summary
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.integrations.telegram.parser import parse_telegram_update
from app.models.company_bot_instance import CompanyBotInstance
from app.models.core import Company, Employee
from app.models.workforce_attendance import WorkforceAttendanceEvent, WorkforceAttendanceStatus
from app.schemas.bot import (
    BotResponse,
    TelegramBotConfigIn,
    TelegramBotConfigOut,
    TelegramBotPollItem,
    TelegramBotPollOut,
    TelegramBotTestOut,
)
from app.services.event_engine import EventEngine
from app.services.shoplink_whatsapp_web import whatsapp_logout, whatsapp_send, whatsapp_start, whatsapp_status

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover
    Fernet = None


router = APIRouter()

logger = logging.getLogger("clonexa.telegram_listener")
TELEGRAM_LISTENER_TASKS: dict[str, asyncio.Task] = {}
TELEGRAM_LISTENER_LOCKS: dict[str, asyncio.Lock] = {}
TELEGRAM_LISTENER_STOP_REQUESTED: set[str] = set()
TELEGRAM_LISTENER_DEFAULT_INTERVAL = 3


def _listener_lock(company_id: UUID | str) -> asyncio.Lock:
    key = _listener_key(company_id)
    lock = TELEGRAM_LISTENER_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        TELEGRAM_LISTENER_LOCKS[key] = lock
    return lock


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def mask_token(token: str | None) -> str | None:
    if not token:
        return None
    value = str(token).strip()
    if len(value) <= 12:
        return f"{value[:4]}****"
    return f"{value[:8]}****{value[-6:]}"


def _fernet():
    if Fernet is None:
        return None
    secret = get_settings().JWT_SECRET_KEY or "clonexa-local-secret"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_token(token: str) -> str:
    token = token.strip()
    fernet = _fernet()
    if fernet is not None:
        return "fernet:" + fernet.encrypt(token.encode("utf-8")).decode("utf-8")
    return "b64:" + base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


def decrypt_token(stored: str | None) -> str | None:
    if not stored:
        return None
    if stored.startswith("fernet:"):
        fernet = _fernet()
        if fernet is None:
            raise HTTPException(status_code=500, detail="Token encryption backend unavailable")
        return fernet.decrypt(stored.removeprefix("fernet:").encode("utf-8")).decode("utf-8")
    if stored.startswith("b64:"):
        return base64.urlsafe_b64decode(stored.removeprefix("b64:").encode("utf-8")).decode("utf-8")
    return stored


async def ensure_company_exists(db: AsyncSession, company_id: UUID) -> Company:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


async def ensure_bot_storage(db: AsyncSession) -> None:
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_bot_instances (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel varchar(40) NOT NULL DEFAULT 'telegram',
            name varchar(180) NULL,
            bot_username varchar(180) NULL,
            bot_token_encrypted text NULL,
            token_mask varchar(80) NULL,
            status varchar(40) NOT NULL DEFAULT 'configured',
            last_validated_at timestamptz NULL,
            last_error text NULL,
            config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_company_bot_instances_company_channel UNIQUE (company_id, channel)
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_bot_instances_company_id ON company_bot_instances(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_bot_instances_channel ON company_bot_instances(channel);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_bot_instances_status ON company_bot_instances(status);"))

    # 011A3: preferencias por usuario Telegram. Se crea aquí para mantener el patch ejecutable
    # sin depender de migración manual. No almacena tokens ni datos sensibles.
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_telegram_user_preferences (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            telegram_user_id varchar(120) NOT NULL,
            telegram_username varchar(180) NULL,
            language varchar(10) NOT NULL DEFAULT 'es',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_company_telegram_user_preferences UNIQUE (company_id, telegram_user_id)
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_telegram_user_preferences_company ON company_telegram_user_preferences(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_telegram_user_preferences_language ON company_telegram_user_preferences(language);"))

    # 014A: acciones pendientes por usuario Telegram.
    # Se usa para GPS Gate: si la empresa tiene GPS activo, /entrada queda pendiente
    # hasta que Telegram entregue una ubicación real.
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_telegram_pending_actions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            telegram_user_id varchar(120) NOT NULL,
            telegram_username varchar(180) NULL,
            employee_id uuid NULL REFERENCES employees(id) ON DELETE CASCADE,
            action varchar(80) NOT NULL,
            payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            expires_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_company_telegram_pending_action UNIQUE (company_id, telegram_user_id, action)
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_telegram_pending_actions_company ON company_telegram_pending_actions(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_telegram_pending_actions_action ON company_telegram_pending_actions(action);"))

    # CLONEXA_019D_C1_TELEGRAM_LIVE_LOCATION_TRACKING_START
    # Sesiones internas de seguimiento GPS por turno.
    # Importante: esto NO fuerza ni cancela la ubicación en vivo del teléfono.
    # CLONEXA abre/cierra su sesión operativa y procesa updates solo mientras el turno esté activo.
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS gps_tracking_sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            telegram_user_id varchar(120) NULL,
            chat_id varchar(120) NULL,
            source_channel varchar(80) NOT NULL DEFAULT 'telegram_live_location',
            status varchar(40) NOT NULL DEFAULT 'active',
            started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz NULL,
            last_location_at timestamptz NULL,
            last_event_id uuid NULL,
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_gps_tracking_sessions_company ON gps_tracking_sessions(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_gps_tracking_sessions_employee ON gps_tracking_sessions(company_id, employee_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_gps_tracking_sessions_status ON gps_tracking_sessions(company_id, status);"))
    await db.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_gps_tracking_sessions_active_employee
        ON gps_tracking_sessions(company_id, employee_id)
        WHERE status = 'active';
    """))
    # CLONEXA_019D_C1_TELEGRAM_LIVE_LOCATION_TRACKING_END




def bot_out(row: CompanyBotInstance | None, company_id: UUID | None = None) -> TelegramBotConfigOut:
    if not row:
        return TelegramBotConfigOut(
            configured=False,
            ok=True,
            company_id=company_id,
            status="not_configured",
            masked_token=None,
        )

    return TelegramBotConfigOut(
        configured=bool(row.bot_token_encrypted),
        ok=row.status != "error",
        id=row.id,
        company_id=row.company_id,
        channel=row.channel,
        name=row.name,
        bot_username=row.bot_username,
        masked_token=row.token_mask,
        status=row.status or "configured",
        last_validated_at=row.last_validated_at,
        last_error=row.last_error,
        config_json=row.config_json or {},
    )


class WhatsAppWebTestIn(BaseModel):
    to: str | None = None
    message: str | None = None


class WhatsAppWebInboundIn(BaseModel):
    company_id: str
    event_type: str | None = None
    from_jid: str | None = None
    from_phone: str | None = None
    push_name: str | None = None
    message_id: str | None = None
    text: str | None = None
    timestamp: Any | None = None


def _wa_agent_name(company: Company | None) -> str:
    name = str(getattr(company, "name", "") or "Empresa").strip() or "Empresa"
    return f"Agente {name}"


def _wa_module_tokens(modules: list[Any] | set[Any] | tuple[Any, ...]) -> set[str]:
    tokens: set[str] = set()
    for item in modules or []:
        raw = _text_norm(item)
        compact = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
        if raw:
            tokens.add(raw)
        if compact:
            tokens.add(compact)
    return tokens


def _wa_has_any(tokens: set[str], values: set[str]) -> bool:
    return any(value in tokens for value in values)


def _wa_capabilities(modules: list[Any] | set[Any] | tuple[Any, ...]) -> dict[str, bool]:
    tokens = _wa_module_tokens(modules)
    return {
        "quotes": _wa_has_any(tokens, {"cot", "cotizacion", "cotizaciones", "quotes", "quote"}),
        "crm": _wa_has_any(tokens, {"crm", "crm_campo", "field_crm", "cli", "clientes_crm_landing"}),
        "payroll": _wa_has_any(tokens, {"pay", "payroll", "nomina", "nómina", "payroll_biweekly"}),
        "production": _wa_has_any(tokens, {"production", "produccion", "producción", "prd"}),
        "workforce": _wa_has_any(tokens, {"workforce", "wrk"}),
        "shoplink": _wa_has_any(tokens, {"shoplink", "lan", "pro", "car", "catalogo_tienda_publica", "productos_inventario_landing", "carrito_y_pedidos_landing"}),
    }


def _wa_active_examples(modules: list[Any] | set[Any] | tuple[Any, ...]) -> str:
    caps = _wa_capabilities(modules)
    examples: list[str] = []
    if caps["payroll"]:
        examples.extend(["nomina del mes", "nomina de una persona"])
    if caps["crm"] or caps["workforce"]:
        examples.extend(["estado CRM", "conexiones del equipo", "tiempo de Nicolas"])
    if caps["production"]:
        examples.extend(["produccion de hoy", "avance por referencia", "cierres del mes"])
    if caps["quotes"]:
        examples.extend(["cuenta de cobro", "cotizacion"])
    if caps["shoplink"]:
        examples.extend(["pedidos activos", "stock bajo"])
    return ", ".join(examples[:8]) or "modulos activos"


def _text_norm(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(char for char in raw if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", raw).strip()


def _contains_any(text_value: str, words: list[str]) -> bool:
    text_norm = _text_norm(text_value)
    return any(_text_norm(word) in text_norm for word in words)


def _seconds_label(value: Any) -> str:
    try:
        total = max(0, int(float(value or 0)))
    except Exception:
        total = 0
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _minutes_label(value: Any) -> str:
    try:
        minutes_total = max(0, int(float(value or 0)))
    except Exception:
        minutes_total = 0
    hours = minutes_total // 60
    minutes = minutes_total % 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _money_label(value: Any) -> str:
    try:
        amount = float(value or 0)
    except Exception:
        amount = 0.0
    return "$ " + f"{amount:,.0f}".replace(",", ".")


def _today_business() -> date:
    return datetime.now(timezone.utc).date()


def _last_day_of_month(value: date) -> date:
    if value.month == 12:
        return date(value.year, 12, 31)
    return date(value.year, value.month + 1, 1) - timedelta(days=1)


def _parse_date_token(value: str) -> date | None:
    raw = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except Exception:
            continue
    return None


def _payroll_period_from_text(text_value: str) -> tuple[date, date, str]:
    normalized = _text_norm(text_value)
    today = _today_business()

    explicit = [_parse_date_token(item) for item in re.findall(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", text_value)]
    explicit = [item for item in explicit if item]
    if len(explicit) >= 2:
        start, end = min(explicit[0], explicit[1]), max(explicit[0], explicit[1])
        return start, end, "rango indicado"
    if len(explicit) == 1:
        return explicit[0], explicit[0], "fecha indicada"

    if "hoy" in normalized:
        return today, today, "hoy"

    if "semana" in normalized or "semanal" in normalized:
        start = today - timedelta(days=today.weekday())
        return start, today, "semana actual"

    if "quincena" in normalized or "quincenal" in normalized:
        if "primera" in normalized or "1ra" in normalized or "1a" in normalized:
            return date(today.year, today.month, 1), date(today.year, today.month, 15), "primera quincena"
        if "segunda" in normalized or "2da" in normalized or "2a" in normalized:
            return date(today.year, today.month, 16), _last_day_of_month(today), "segunda quincena"
        if today.day <= 15:
            return date(today.year, today.month, 1), today, "quincena actual"
        return date(today.year, today.month, 16), today, "quincena actual"

    if "ayer" in normalized:
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday, "ayer"

    if today.day <= 15:
        return date(today.year, today.month, 1), today, "quincena actual"
    return date(today.year, today.month, 16), today, "quincena actual"


def _payroll_employee_match_from_text(text_value: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    query = _text_norm(text_value)
    best: tuple[int, dict[str, Any]] | None = None
    ignored = {
        "nomina", "payroll", "corte", "periodo", "quincena", "semana", "mes", "actual",
        "cuanto", "debo", "debe", "pagar", "total", "individual", "persona", "empleado",
    }
    for row in rows:
        name = _text_norm(row.get("employee_name") or row.get("name"))
        if not name:
            continue
        tokens = [token for token in re.split(r"[^a-z0-9]+", name) if len(token) >= 3 and token not in ignored]
        score = sum(1 for token in tokens if token in query)
        if score and (best is None or score > best[0]):
            best = (score, row)
    return best[1] if best else None


def _format_payroll_row(row: dict[str, Any], period_start: date, period_end: date) -> str:
    regular_minutes = int(row.get("regular_minutes") or row.get("regularMinutes") or 0)
    extra_minutes = int(row.get("extra_minutes") or row.get("extraMinutes") or 0)
    period_label = "Tiempo de hoy" if period_start == period_end == _today_business() else "Tiempo del periodo"
    return "\n".join([
        f"Nomina individual {period_start.isoformat()} / {period_end.isoformat()}:",
        f"{row.get('employee_name') or row.get('name') or 'Colaborador'}",
        f"Turnos/sesiones: {int(row.get('closed_shifts') or row.get('shifts') or 0)}",
        f"{period_label}: {_minutes_label(regular_minutes + extra_minutes)}",
        f"Ordinarias: {_minutes_label(regular_minutes)}",
        f"Extras: {_minutes_label(extra_minutes)}",
        f"Bruto: {_money_label(row.get('gross_amount') or row.get('gross'))}",
        f"Descuentos: {_money_label(row.get('discount_amount') or row.get('discount'))}",
        f"Total a pagar: {_money_label(row.get('net_amount') or row.get('net'))}",
    ])


def _format_payroll_summary(company: Company, snapshot: dict[str, Any], text_value: str, period_label: str) -> str:
    period = snapshot.get("period") or {}
    period_start = _parse_date_token(str(period.get("period_start") or "")) or _today_business()
    period_end = _parse_date_token(str(period.get("period_end") or "")) or period_start
    rows = list(snapshot.get("rows") or snapshot.get("items") or [])
    matched = _payroll_employee_match_from_text(text_value, rows)
    if matched:
        return _format_payroll_row(matched, period_start, period_end)

    totals = snapshot.get("totals") or {}
    top_rows = sorted(rows, key=lambda row: float(row.get("net_amount") or row.get("net") or 0), reverse=True)[:6]
    lines = [
        f"Nomina de {company.name} ({period_label})",
        f"Periodo: {period_start.isoformat()} / {period_end.isoformat()}",
        f"Colaboradores con corte: {int(totals.get('people') or len(rows) or 0)}",
        f"Turnos/sesiones: {int(totals.get('closed_shifts') or totals.get('shifts') or 0)}",
        f"Ordinarias: {_minutes_label(totals.get('regular_minutes') or totals.get('regularMinutes'))}",
        f"Extras: {_minutes_label(totals.get('extra_minutes') or totals.get('extraMinutes'))}",
        f"Bruto: {_money_label(totals.get('gross_amount') or totals.get('gross'))}",
        f"Descuentos: {_money_label(totals.get('discount_amount') or totals.get('discount'))}",
        f"Total a pagar: {_money_label(totals.get('net_amount') or totals.get('net'))}",
    ]
    if top_rows:
        lines.append("")
        lines.append("Detalle visible:")
        for row in top_rows:
            lines.append(
                f"- {row.get('employee_name') or row.get('name') or 'Colaborador'}: "
                f"{_money_label(row.get('net_amount') or row.get('net'))} "
                f"({_minutes_label(row.get('regular_minutes') or row.get('regularMinutes'))} ord / "
                f"{_minutes_label(row.get('extra_minutes') or row.get('extraMinutes'))} ext)"
            )
    return "\n".join(lines)


async def _whatsapp_payroll_reply(
    *,
    company_id: UUID,
    company: Company,
    db: AsyncSession,
    text_value: str,
) -> str:
    period_start, period_end, period_label = _payroll_period_from_text(text_value)
    await ensure_payroll_storage(db)
    snapshot = await calculate_period_snapshot(db, company_id, period_start, period_end)
    return _format_payroll_summary(company, snapshot, text_value, period_label)


def _looks_today_payroll_time_query(normalized: str) -> bool:
    if "hoy" not in normalized:
        return False
    return any(
        token in normalized
        for token in (
            "cuanto tiempo",
            "cuanto lleva",
            "tiempo lleva",
            "tiempo trabajado",
            "horas de hoy",
            "horas lleva",
            "lleva hoy",
        )
    )


def _production_day_range_from_text(normalized: str, today: date) -> tuple[date, date, str] | None:
    match = re.search(r"(?:desde|del|de)\s+(?:el\s+)?(\d{1,2})\s+(?:al|a|hasta)\s+(?:la\s+fecha|hoy|(?:el\s+)?(\d{1,2}))", normalized)
    if match:
        try:
            start = date(today.year, today.month, int(match.group(1)))
            end = date(today.year, today.month, int(match.group(2))) if match.group(2) else today
        except Exception:
            return None
        start, end = min(start, end), max(start, end)
        return start, end, f"desde {start.isoformat()} hasta {end.isoformat()}"

    start_only = re.search(r"(?:desde|del)\s+(?:el\s+)?(\d{1,2})(?:\s|$)", normalized)
    if start_only and ("fecha" in normalized or "hoy" in normalized):
        try:
            start = date(today.year, today.month, int(start_only.group(1)))
        except Exception:
            return None
        return start, today, f"desde {start.isoformat()} hasta hoy"

    return None


def _production_period_from_text(text_value: str) -> tuple[date, date, str, str, bool]:
    normalized = _text_norm(text_value)
    today = _today_business()
    explicit = [_parse_date_token(item) for item in re.findall(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", text_value)]
    explicit = [item for item in explicit if item]
    view = "archived" if "archiv" in normalized else ("all" if "todas" in normalized or "todo" in normalized else "active")
    if len(explicit) >= 2:
        start, end = min(explicit[0], explicit[1]), max(explicit[0], explicit[1])
        return start, end, "rango indicado", view, True
    if len(explicit) == 1:
        return explicit[0], explicit[0], "fecha indicada", view, True
    day_range = _production_day_range_from_text(normalized, today)
    if day_range:
        return day_range[0], day_range[1], day_range[2], view, True
    if "hoy" in normalized:
        return today, today, "hoy", view, True
    if "mes" in normalized:
        return date(today.year, today.month, 1), today, "mes actual", view, True
    if "30" in normalized:
        return today - timedelta(days=29), today, "ultimos 30 dias", view, True
    return today - timedelta(days=6), today, "ultimos 7 dias", view, False


def _production_ref_match_from_text(text_value: str, refs: list[dict[str, Any]]) -> dict[str, Any] | None:
    query = _text_norm(text_value)
    ignored = {"produccion", "referencia", "referencias", "avance", "pendiente", "cerrada", "cierre", "cierres"}
    best: tuple[int, dict[str, Any]] | None = None
    for row in refs:
        label = _text_norm(f"{row.get('name') or ''} {row.get('size') or ''}")
        tokens = [token for token in re.split(r"[^a-z0-9]+", label) if len(token) >= 3 and token not in ignored]
        score = sum(1 for token in tokens if token in query)
        if score and (best is None or score > best[0]):
            best = (score, row)
    return best[1] if best else None


def _production_seconds(row: dict[str, Any]) -> int:
    for key in ("total_effective_seconds", "effective_seconds", "seconds"):
        try:
            return max(0, int(float(row.get(key) or 0)))
        except Exception:
            continue
    return 0


def _production_time_label(row: dict[str, Any]) -> str:
    return str(row.get("total_effective_label") or row.get("effective_label") or _seconds_label(_production_seconds(row)))


def _production_score(text_value: str, label: str) -> int:
    query = _text_norm(text_value)
    ignored = {"produccion", "referencia", "referencias", "tiempo", "cuanto", "lleva", "detalle"}
    tokens = [token for token in re.split(r"[^a-z0-9]+", _text_norm(label)) if len(token) >= 3 and token not in ignored]
    return sum(1 for token in tokens if token in query)


def _production_time_ref_match_from_text(text_value: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: tuple[int, dict[str, Any]] | None = None
    for row in rows:
        score = _production_score(text_value, f"{row.get('reference_name') or row.get('name') or ''} {row.get('size') or ''}")
        if score and (best is None or score > best[0]):
            best = (score, row)
    return best[1] if best else None


def _production_operator_match_from_text(text_value: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: tuple[int, dict[str, Any]] | None = None
    for row in rows:
        score = _production_score(text_value, f"{row.get('employee_name') or ''} {row.get('telegram_user_id') or ''}")
        if score and (best is None or score > best[0]):
            best = (score, row)
    return best[1] if best else None


def _production_operator_reference_match_from_text(text_value: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        employee = str(row.get("employee_name") or row.get("telegram_user_id") or "Colaborador")
        reference = str(row.get("reference_name") or row.get("name") or "Referencia")
        operator_score = _production_score(text_value, employee)
        reference_score = _production_score(text_value, f"{reference} {row.get('size') or ''}")
        if operator_score > 0 and reference_score > 0:
            candidates.append((operator_score + reference_score, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], _production_seconds(item[1])), reverse=True)
    selected = candidates[0][1]
    employee_key = _text_norm(selected.get("employee_name") or selected.get("telegram_user_id") or "Colaborador")
    reference_key = _text_norm(selected.get("reference_name") or selected.get("name") or "Referencia")
    grouped = [
        row for row in rows
        if _text_norm(row.get("employee_name") or row.get("telegram_user_id") or "Colaborador") == employee_key
        and _text_norm(row.get("reference_name") or row.get("name") or "Referencia") == reference_key
    ]
    seconds = sum(_production_seconds(row) for row in grouped)
    sessions = sum(int(row.get("sessions_count") or row.get("sessions") or 0) for row in grouped)
    sizes = sorted({str(row.get("size") or "").strip() for row in grouped if str(row.get("size") or "").strip()})
    return {
        "employee": selected.get("employee_name") or selected.get("telegram_user_id") or "Colaborador",
        "reference": selected.get("reference_name") or selected.get("name") or "Referencia",
        "rows": grouped,
        "seconds": seconds,
        "sessions": sessions,
        "sizes": sizes,
    }


def _production_mode(text_value: str, data: dict[str, Any]) -> str:
    normalized = _text_norm(text_value)
    time_rows = list(data.get("time_by_reference") or [])
    operator_rows = list(data.get("time_by_operator_reference") or [])
    if _production_operator_reference_match_from_text(text_value, operator_rows):
        return "time_operator_reference"
    if "cierre" in normalized or "cierres" in normalized or "coerres" in normalized or "cerrada" in normalized or "cerradas" in normalized:
        return "closures"
    if "pendiente" in normalized or "faltan" in normalized or "falta" in normalized:
        return "pending"
    if "avance" in normalized or "progreso" in normalized or "porcentaje" in normalized:
        return "progress"
    if (
        "tiempo por colaborador" in normalized
        or "tiempos por colaborador" in normalized
        or "tiempo por empleado" in normalized
        or "tiempos por empleado" in normalized
        or "tiempo por persona" in normalized
        or "colaborador" in normalized
    ):
        return "time_operator"
    if (
        "tiempo por referencia" in normalized
        or "tiempos por referencia" in normalized
        or "cuanto tiempo" in normalized
        or "cuanto lleva" in normalized
        or "tiempo lleva" in normalized
        or _production_time_ref_match_from_text(text_value, time_rows)
    ):
        return "time_reference"
    return "summary"


def _format_production_time_reference(data: dict[str, Any], text_value: str, period_label: str) -> str:
    rows = sorted(list(data.get("time_by_reference") or []), key=_production_seconds, reverse=True)
    matched = _production_time_ref_match_from_text(text_value, rows)
    if matched:
        return "\n".join([
            f"Tiempo por referencia ({period_label})",
            f"{matched.get('reference_name') or matched.get('name') or 'Referencia'}{(' / ' + str(matched.get('size'))) if matched.get('size') else ''}",
            f"Tiempo productivo: {_production_time_label(matched)}",
            f"Sesiones: {int(matched.get('sessions_count') or matched.get('sessions') or 0)}",
            f"Colaboradores: {int(matched.get('operators_count') or 0)}",
        ])
    lines = [f"Tiempos por referencia ({period_label})"]
    if not rows:
        lines.append("Sin tiempos por referencia en este periodo.")
        return "\n".join(lines)
    for row in rows[:10]:
        lines.append(
            f"- {row.get('reference_name') or row.get('name') or 'Referencia'}"
            f"{(' / ' + str(row.get('size'))) if row.get('size') else ''}: "
            f"{_production_time_label(row)} ({int(row.get('sessions_count') or row.get('sessions') or 0)} sesiones)"
        )
    return "\n".join(lines)


def _format_production_time_operator(data: dict[str, Any], text_value: str, period_label: str) -> str:
    rows = list(data.get("time_by_operator_reference") or [])
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("employee_name") or row.get("telegram_user_id") or "Colaborador")
        current = grouped.setdefault(key, {"name": key, "seconds": 0, "sessions": 0, "references": set(), "rows": []})
        current["seconds"] += _production_seconds(row)
        current["sessions"] += int(row.get("sessions_count") or row.get("sessions") or 0)
        if row.get("reference_name"):
            current["references"].add(f"{row.get('reference_name')}{(' / ' + str(row.get('size'))) if row.get('size') else ''}")
        current["rows"].append(row)
    matched = _production_operator_match_from_text(text_value, rows)
    if matched:
        group = grouped.get(str(matched.get("employee_name") or matched.get("telegram_user_id") or "Colaborador"))
        lines = [
            f"Tiempo por colaborador ({period_label})",
            str(group.get("name") if group else "Colaborador"),
            f"Tiempo productivo: {_seconds_label(group.get('seconds') if group else 0)}",
            f"Sesiones: {int(group.get('sessions') if group else 0)}",
            f"Referencias: {', '.join(list(group.get('references') or [])[:4]) or '-'}",
        ]
        for row in list(group.get("rows") or [])[:8]:
            lines.append(f"- {row.get('reference_name') or 'Referencia'}: {_production_time_label(row)}")
        return "\n".join(lines)
    groups = sorted(grouped.values(), key=lambda row: int(row.get("seconds") or 0), reverse=True)
    lines = [f"Tiempos por colaborador ({period_label})"]
    if not groups:
        lines.append("Sin tiempos por colaborador en este periodo.")
        return "\n".join(lines)
    for group in groups[:10]:
        lines.append(f"- {group['name']}: {_seconds_label(group['seconds'])} - {group['sessions']} sesiones - {len(group['references'])} referencias")
    return "\n".join(lines)


def _format_production_operator_reference(data: dict[str, Any], text_value: str, period_label: str) -> str:
    rows = list(data.get("time_by_operator_reference") or [])
    matched = _production_operator_reference_match_from_text(text_value, rows)
    if not matched:
        return _format_production_time_operator(data, text_value, period_label)
    total_label = _production_time_label(matched["rows"][0]) if len(matched["rows"]) == 1 else _seconds_label(matched["seconds"])
    lines = [
        f"Tiempo de colaborador en referencia ({period_label})",
        f"{matched['employee']} en {matched['reference']}",
        f"Tiempo productivo: {total_label}",
        f"Sesiones: {int(matched['sessions'] or 0)}",
        f"Tallas / variantes: {', '.join(matched['sizes']) or '-'}",
    ]
    if len(matched["rows"]) > 1:
        for row in matched["rows"][:8]:
            lines.append(f"- {row.get('size') or 'Sin talla'}: {_production_time_label(row)} - {int(row.get('sessions_count') or row.get('sessions') or 0)} sesiones")
    return "\n".join(lines)


def _production_closure_source(data: dict[str, Any], period_label: str, strict_period: bool) -> tuple[list[dict[str, Any]], str, bool]:
    period_rows = list(data.get("closures_period") or [])
    if period_rows or strict_period:
        return period_rows, period_label, False
    display_rows = list(data.get("closures_display") or [])
    all_rows = list(data.get("closures_all_time") or [])
    fallback_rows = display_rows or all_rows
    if fallback_rows:
        return fallback_rows, "historial disponible", True
    return period_rows, period_label, False


def _production_closure_filter(text_value: str, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, str]:
    employee_matches = [
        row for row in rows
        if _production_score(text_value, f"{row.get('employee_name') or ''} {row.get('telegram_user_id') or ''}") > 0
    ]
    reference_matches = [
        row for row in rows
        if _production_score(text_value, f"{row.get('reference_name') or ''} {row.get('size') or ''}") > 0
    ]
    employee_keys = {
        _text_norm(row.get("employee_name") or row.get("telegram_user_id") or "Colaborador")
        for row in employee_matches
    }
    reference_keys = {
        _text_norm(f"{row.get('reference_name') or ''} {row.get('size') or ''}")
        for row in reference_matches
    }
    filtered = rows
    if employee_keys:
        filtered = [
            row for row in filtered
            if _text_norm(row.get("employee_name") or row.get("telegram_user_id") or "Colaborador") in employee_keys
        ]
    if reference_keys:
        filtered = [
            row for row in filtered
            if _text_norm(f"{row.get('reference_name') or ''} {row.get('size') or ''}") in reference_keys
        ]
    employee_label = str(employee_matches[0].get("employee_name") or employee_matches[0].get("telegram_user_id") or "") if employee_matches else ""
    if reference_matches:
        reference_label = str(reference_matches[0].get("reference_name") or "")
        if reference_matches[0].get("size"):
            reference_label += f" / {reference_matches[0].get('size')}"
    else:
        reference_label = ""
    return filtered, employee_label, reference_label


def _production_closure_groups(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    employees: dict[str, dict[str, Any]] = {}
    references: dict[str, dict[str, Any]] = {}
    for row in rows:
        employee = str(row.get("employee_name") or row.get("telegram_user_id") or "Colaborador")
        reference = f"{row.get('reference_name') or 'Referencia'}{(' / ' + str(row.get('size'))) if row.get('size') else ''}"
        quantity = int(row.get("quantity_finished") or 0)
        emp = employees.setdefault(employee, {"label": employee, "closures": 0, "quantity": 0})
        emp["closures"] += 1
        emp["quantity"] += quantity
        ref = references.setdefault(reference, {"label": reference, "closures": 0, "quantity": 0})
        ref["closures"] += 1
        ref["quantity"] += quantity

    sorter = lambda row: (int(row.get("quantity") or 0), int(row.get("closures") or 0))
    return (
        sorted(employees.values(), key=sorter, reverse=True),
        sorted(references.values(), key=sorter, reverse=True),
    )


def _production_closure_date_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return raw[:16]


def _format_production_closures(data: dict[str, Any], text_value: str, period_label: str, strict_period: bool = False) -> str:
    source_rows, source_label, fallback = _production_closure_source(data, period_label, strict_period)
    rows, employee_label, reference_label = _production_closure_filter(text_value, source_rows)
    rows.sort(key=lambda row: str(row.get("closed_at") or ""), reverse=True)
    total_quantity = sum(int(row.get("quantity_finished") or 0) for row in rows)
    employee_groups, reference_groups = _production_closure_groups(rows)
    lines = [f"Cierres de produccion ({source_label})"]
    if fallback:
        lines.append(f"No encontre cierres en {period_label}; muestro el historial disponible.")
    filters = [label for label in (f"colaborador: {employee_label}" if employee_label else "", f"referencia: {reference_label}" if reference_label else "") if label]
    if filters:
        lines.append("Filtro: " + " - ".join(filters))
    lines.append(f"Cierres encontrados: {len(rows)}")
    lines.append(f"Cantidad cerrada total: {total_quantity}")
    if not rows:
        lines.append("Sin cierres en este periodo.")
        return "\n".join(lines)
    if employee_groups:
        lines.append("")
        lines.append("Por colaborador:")
        for row in employee_groups[:4]:
            lines.append(f"- {row['label']}: {row['closures']} cierres - {row['quantity']} unidades")
    if reference_groups:
        lines.append("")
        lines.append("Por referencia:")
        for row in reference_groups[:4]:
            lines.append(f"- {row['label']}: {row['closures']} cierres - {row['quantity']} unidades")
    lines.append("")
    lines.append("Detalle:")
    for row in rows[:12]:
        lines.append(
            f"- {_production_closure_date_label(row.get('closed_at'))}: "
            f"{row.get('employee_name') or 'Colaborador'} cerro {int(row.get('quantity_finished') or 0)} "
            f"de {row.get('reference_name') or 'referencia'}{(' / ' + str(row.get('size'))) if row.get('size') else ''}"
        )
    return "\n".join(lines)


def _format_production_pending(data: dict[str, Any], period_label: str, sort_key: str) -> str:
    refs = list(data.get("references") or [])
    refs.sort(key=lambda row: float(row.get(sort_key) or 0), reverse=True)
    title = "Avance por referencia" if sort_key == "progress_percent" else "Pendientes por referencia"
    lines = [f"{title} ({period_label})"]
    if not refs:
        lines.append("Sin referencias para este periodo.")
        return "\n".join(lines)
    for row in refs[:12]:
        lines.append(
            f"- {row.get('name') or 'Referencia'}{(' / ' + str(row.get('size'))) if row.get('size') else ''}: "
            f"{float(row.get('progress_percent') or 0):g}% - cerrada {int(row.get('finished_quantity') or 0)} - pendiente {int(row.get('pending_quantity') or 0)}"
        )
    return "\n".join(lines)


def _production_can_answer(data: dict[str, Any], text_value: str) -> bool:
    normalized = _text_norm(text_value)
    if any(token in normalized for token in ("produccion", "referencia", "avance", "pendiente", "cierre", "cierres", "coerres", "cerrada")):
        return True
    mode = _production_mode(text_value, data)
    if mode == "time_operator_reference":
        return _production_operator_reference_match_from_text(text_value, list(data.get("time_by_operator_reference") or [])) is not None
    if mode == "time_reference":
        return _production_time_ref_match_from_text(text_value, list(data.get("time_by_reference") or [])) is not None
    if mode == "time_operator":
        return "colaborador" in normalized or "empleado" in normalized
    return False


def _format_production_summary(company: Company, data: dict[str, Any], text_value: str, period_label: str, strict_period: bool = False) -> str:
    mode = _production_mode(text_value, data)
    if mode == "time_operator_reference":
        return _format_production_operator_reference(data, text_value, period_label)
    if mode == "time_reference":
        return _format_production_time_reference(data, text_value, period_label)
    if mode == "time_operator":
        return _format_production_time_operator(data, text_value, period_label)
    if mode == "closures":
        return _format_production_closures(data, text_value, period_label, strict_period)
    if mode == "pending":
        return _format_production_pending(data, period_label, "pending_quantity")
    if mode == "progress":
        return _format_production_pending(data, period_label, "progress_percent")

    totals = data.get("totals") or {}
    refs = list(data.get("references") or [])
    matched = _production_ref_match_from_text(text_value, refs)
    if matched:
        lines = [
            f"Produccion por referencia ({period_label})",
            f"{matched.get('name') or 'Referencia'}{(' / ' + str(matched.get('size'))) if matched.get('size') else ''}",
            f"Total: {int(matched.get('initial_quantity') or 0)}",
            f"Cerrada: {int(matched.get('finished_quantity') or 0)}",
            f"Pendiente: {int(matched.get('pending_quantity') or 0)}",
            f"Sobreproducida: {int(matched.get('over_finished_quantity') or 0)}",
            f"Avance: {float(matched.get('progress_percent') or 0):g}%",
        ]
        return "\n".join(lines)

    top_refs = sorted(refs, key=lambda row: int(row.get("pending_quantity") or 0), reverse=True)[:6]
    closures = list(data.get("closures_period") or [])[:5]
    lines = [
        f"Produccion de {company.name} ({period_label})",
        f"Periodo: {data.get('date_from')} / {data.get('date_to')}",
        f"Referencias: {int(totals.get('references_total') or len(refs) or 0)}",
        f"Tiempo productivo: {totals.get('effective_label_period') or _seconds_label(totals.get('effective_seconds_period'))}",
        f"Cantidad cerrada: {int(totals.get('finished_quantity_total') or 0)}",
        f"Pendiente: {int(totals.get('pending_quantity_total') or 0)}",
        f"Avance: {float(totals.get('progress_percent') or 0):g}%",
        f"Sesiones activas: {int(totals.get('active_sessions') or 0)}",
    ]
    if top_refs:
        lines.append("")
        lines.append("Referencias con pendiente:")
        for row in top_refs:
            lines.append(
                f"- {row.get('name') or 'Referencia'}"
                f"{(' / ' + str(row.get('size'))) if row.get('size') else ''}: "
                f"{float(row.get('progress_percent') or 0):g}% - pendiente {int(row.get('pending_quantity') or 0)}"
            )
    if closures:
        lines.append("")
        lines.append("Ultimos cierres:")
        for row in closures:
            lines.append(
                f"- {row.get('employee_name') or 'Colaborador'} cerro "
                f"{int(row.get('quantity_finished') or 0)} de {row.get('reference_name') or 'referencia'}"
            )
    return "\n".join(lines)


async def _whatsapp_production_reply(
    *,
    company_id: UUID,
    company: Company,
    db: AsyncSession,
    text_value: str,
    only_if_specific: bool = False,
) -> str | None:
    period_start, period_end, period_label, view, strict_period = _production_period_from_text(text_value)
    data = await production_summary(
        company_id=str(company_id),
        date_from=period_start.isoformat(),
        date_to=period_end.isoformat(),
        preset="custom",
        view=view,
        db=db,
    )
    if only_if_specific and not _production_can_answer(data, text_value):
        return None
    return _format_production_summary(company, data, text_value, period_label, strict_period)


def _employee_match_from_text(text_value: str, employees: list[dict[str, Any]]) -> dict[str, Any] | None:
    query = _text_norm(text_value)
    best: tuple[int, dict[str, Any]] | None = None
    for employee in employees:
        name = _text_norm(employee.get("employee_name"))
        if not name:
            continue
        tokens = [token for token in re.split(r"[^a-z0-9]+", name) if len(token) >= 3]
        score = sum(1 for token in tokens if token and token in query)
        if score and (best is None or score > best[0]):
            best = (score, employee)
    return best[1] if best else None


def _employee_reference_label(employee: dict[str, Any]) -> str:
    for adapter in employee.get("adapters") or []:
        if adapter.get("code") != "production_references":
            continue
        for item in adapter.get("items") or []:
            if item.get("is_active"):
                return str(item.get("title") or item.get("name") or item.get("reference_name") or "").strip()
    return ""


def _format_employee_status(employee: dict[str, Any]) -> str:
    name = str(employee.get("employee_name") or "Empleado").strip()
    core = employee.get("core") or {}
    status_label_value = str(core.get("status_label") or core.get("status") or "Sin estado").strip()
    if core.get("pause_running"):
        time_label = f"Tiempo en pausa: {_seconds_label(core.get('current_pause_seconds'))}."
    elif core.get("shift_running"):
        time_label = f"Tiempo activo: {_seconds_label(core.get('shift_effective_seconds'))}."
    else:
        time_label = "No tiene turno activo."
    pieces = [f"{name}: {status_label_value}.", time_label]
    reference = _employee_reference_label(employee)
    if reference:
        pieces.append(f"Referencia activa: {reference}.")
    gps = employee.get("gps") or {}
    if gps:
        pieces.append(f"GPS: {gps.get('gps_label') or gps.get('gps_status') or 'reportado'}.")
    return " ".join(piece for piece in pieces if piece)


def _format_crm_summary(company: Company, snapshot: dict[str, Any], text_value: str) -> str:
    employees = list(snapshot.get("employees") or [])
    matched = _employee_match_from_text(text_value, employees)
    if matched:
        return _format_employee_status(matched)

    summary = snapshot.get("summary") or {}
    lines = [
        f"CRM Campo de {company.name}:",
        f"Personal total: {summary.get('employees_total', len(employees))}",
        f"Activos: {summary.get('active_now', 0)}",
        f"En pausa: {summary.get('on_break', 0)}",
        f"Fuera: {summary.get('out', 0)}",
    ]
    if summary.get("gps_adapter"):
        lines.append(f"GPS reportado: {summary.get('gps_sent_location', 0)}")
    if summary.get("with_reference"):
        lines.append(f"Con referencia: {summary.get('with_reference', 0)}")

    visible = employees[:8]
    if visible:
        lines.append("")
        lines.append("Estados visibles:")
        for employee in visible:
            core = employee.get("core") or {}
            lines.append(f"- {employee.get('employee_name') or 'Empleado'}: {core.get('status_label') or core.get('status') or 'Sin estado'}")
    if len(employees) > len(visible):
        lines.append(f"...y {len(employees) - len(visible)} mas.")
    return "\n".join(lines)


def _whatsapp_agent_welcome(company: Company) -> str:
    return (
        f"Hola. Soy tu asistente de CLONEXA dentro de {company.name}. "
        "Pideme lo que necesites gestionar sobre tus modulos."
    )


async def _whatsapp_agent_reply(
    *,
    company_id: UUID,
    company: Company,
    db: AsyncSession,
    text_value: str,
    push_name: str | None = None,
) -> str:
    normalized = _text_norm(text_value)
    sender = str(push_name or "").strip()
    prefix_name = f" {sender}" if sender and len(sender) <= 40 else ""

    crm_words = [
        "crm",
        "estado",
        "estados",
        "conexion",
        "conexiones",
        "gente",
        "personal",
        "equipo",
        "turno",
        "pausa",
        "activo",
        "activos",
        "donde esta",
        "en que esta",
        "resumen",
        "reporte",
        "reportes",
        "operativo",
        "operativa",
        "tiempo",
        "tiempos",
        "hora",
        "horas",
        "conectado",
        "conectados",
        "conectada",
        "laborado",
        "lleva",
    ]
    module_words = ["modulo", "modulos", "herramientas", "funciones", "que puedes", "que sabes"]
    quote_words = ["cuenta de cobro", "cotizacion", "cotizacion", "cobro"]
    payroll_words = [
        "nomina",
        "payroll",
        "corte",
        "liquidacion",
        "sueldo",
        "salario",
        "pagar",
        "pago",
        "pagos",
        "total a pagar",
        "cuanto debo",
        "cuanto debe",
        "cuanto le debo",
        "horas a pagar",
    ]
    production_words = [
        "produccion",
        "productivo",
        "avance",
        "pendiente",
        "pendientes",
        "terminada",
        "terminadas",
        "cerrada",
        "cerradas",
        "cierre",
        "cierres",
        "coerres",
        "sobreproducida",
        "sobreproducidas",
    ]
    production_maybe_words = [
        "cuanto tiempo",
        "cuanto lleva",
        "tiempo lleva",
        "tiempos",
        "lleva",
        "demora",
        "duracion",
    ]

    try:
        snapshot = await crm_core_snapshot(str(company_id), db)
    except Exception as exc:
        logger.warning("whatsapp agent snapshot failed: %s", exc, exc_info=True)
        snapshot = {"active_modules": [], "employees": [], "summary": {}}

    modules = list(snapshot.get("active_modules") or [])
    caps = _wa_capabilities(modules)
    active_examples = _wa_active_examples(modules)

    if _contains_any(normalized, module_words):
        module_label = ", ".join(modules) if modules else "sin modulos activos detectados"
        return (
            f"Hola{prefix_name}. Soy {_wa_agent_name(company)}. "
            f"Estoy vinculado a CLONEXA para {company.name}. "
            f"Modulos activos: {module_label}. "
            f"Puedes pedirme: {active_examples}."
        )

    if _looks_today_payroll_time_query(normalized) and caps["payroll"]:
        try:
            return await _whatsapp_payroll_reply(
                company_id=company_id,
                company=company,
                db=db,
                text_value=text_value,
            )
        except Exception as exc:
            logger.warning("whatsapp today payroll reply failed: %s", exc, exc_info=True)

    if _contains_any(normalized, payroll_words):
        if not caps["payroll"]:
            return "Nomina no aparece activa para esta empresa. Activa el modulo Nomina para consultar cortes, totales e individuales desde WhatsApp."
        try:
            return await _whatsapp_payroll_reply(
                company_id=company_id,
                company=company,
                db=db,
                text_value=text_value,
            )
        except Exception as exc:
            logger.warning("whatsapp payroll reply failed: %s", exc, exc_info=True)
            return "No pude consultar Nomina en este momento. Revisa que existan turnos cerrados o sesiones del periodo."

    if _contains_any(normalized, production_words):
        if not caps["production"]:
            return "Produccion no aparece activa para esta empresa. Solo puedo gestionar los modulos activos de este tenant."
        try:
            return await _whatsapp_production_reply(
                company_id=company_id,
                company=company,
                db=db,
                text_value=text_value,
            )
        except Exception as exc:
            logger.warning("whatsapp production reply failed: %s", exc, exc_info=True)
            return "No pude consultar Produccion en este momento. Revisa que existan referencias, cierres o sesiones productivas."

    if _contains_any(normalized, production_maybe_words) and caps["production"]:
        try:
            production_reply = await _whatsapp_production_reply(
                company_id=company_id,
                company=company,
                db=db,
                text_value=text_value,
                only_if_specific=True,
            )
            if production_reply:
                return production_reply
        except Exception as exc:
            logger.warning("whatsapp production probe failed: %s", exc, exc_info=True)

    if _contains_any(normalized, crm_words):
        if not (caps["crm"] or caps["workforce"]):
            return "CRM/Workforce no aparece activo para esta empresa. Solo puedo consultar conexiones y estados cuando ese modulo esta activo."
        return _format_crm_summary(company, snapshot, text_value)

    if _contains_any(normalized, quote_words):
        if not caps["quotes"]:
            return "Cotizaciones no aparece activo para esta empresa. Solo puedo generar cuentas de cobro o cotizaciones si ese modulo esta activo."
        return (
            f"Perfecto{prefix_name}. Soy {_wa_agent_name(company)}. "
            "Para cuenta de cobro o cotizacion por WhatsApp necesito activar el flujo guiado con PDF en este canal. "
            "Ya puedo responder consultas operativas; el siguiente paso es conectar este chat al generador de PDF."
        )

    return (
        f"Hola{prefix_name}. Soy {_wa_agent_name(company)}, conectado al panel CLONEXA de {company.name}. "
        f"Escribeme por ejemplo: {active_examples}."
    )


def _whatsapp_web_out(company: Company, payload: dict[str, Any]) -> dict[str, Any]:
    status_value = str(payload.get("status") or "not_linked")
    return {
        "ok": bool(payload.get("ok", True)),
        "company_id": str(company.id),
        "channel": "whatsapp_web",
        "name": _wa_agent_name(company),
        "configured": status_value not in {"not_linked", "missing_phone"},
        "status": status_value,
        "qr_data_url": payload.get("qr_data_url") or "",
        "connected_phone": payload.get("connected_phone") or "",
        "last_error": payload.get("last_error") or payload.get("detail") or "",
        "last_inbound_at": payload.get("last_inbound_at") or "",
        "last_inbound_from": payload.get("last_inbound_from") or "",
        "last_inbound_text": payload.get("last_inbound_text") or "",
        "last_reply_at": payload.get("last_reply_at") or "",
        "last_inbound_error": payload.get("last_inbound_error") or "",
        "updated_at": payload.get("updated_at") or "",
    }


def _ensure_whatsapp_inbound_secret(request: Request) -> None:
    expected = str(os.getenv("WHATSAPP_INBOUND_SECRET") or get_settings().JWT_SECRET_KEY or "").strip()
    if not expected:
        return
    received = str(request.headers.get("x-clonexa-whatsapp-secret") or "").strip()
    if received != expected:
        raise HTTPException(status_code=403, detail="WhatsApp inbound no autorizado.")


async def get_telegram_instance(db: AsyncSession, company_id: UUID) -> CompanyBotInstance | None:
    await ensure_bot_storage(db)
    result = await db.execute(
        select(CompanyBotInstance).where(
            CompanyBotInstance.company_id == company_id,
            CompanyBotInstance.channel == "telegram",
        )
    )
    return result.scalar_one_or_none()


TELEGRAM_COMMANDS: dict[str, dict[str, Any]] = {
    # Turno core obligatorio: todos los bots CLONEXA lo tienen.
    "/entrada": {
        "event_type": "check_in",
        "event_label": "Inicio de turno",
        "module_code": "workforce",
        "status_after": "working",
        "turn_action": "start_shift",
        "payroll_affects": True,
        "reply_key": "shift_started",
    },
    "/inicio": {
        "event_type": "check_in",
        "event_label": "Inicio de turno",
        "module_code": "workforce",
        "status_after": "working",
        "turn_action": "start_shift",
        "payroll_affects": True,
        "reply_key": "shift_started",
    },
    "/inicio_turno": {
        "event_type": "check_in",
        "event_label": "Inicio de turno",
        "module_code": "workforce",
        "status_after": "working",
        "turn_action": "start_shift",
        "payroll_affects": True,
        "reply_key": "shift_started",
    },
    "/pausa": {
        "event_type": "break_start",
        "event_label": "Pausa",
        "module_code": "workforce",
        "status_after": "on_break",
        "turn_action": "start_break",
        "payroll_affects": False,
        "reply_key": "break_started",
    },
    "/reanudar": {
        "event_type": "break_end",
        "event_label": "Retomar labores",
        "module_code": "workforce",
        "status_after": "working",
        "turn_action": "resume_work",
        "payroll_affects": False,
        "reply_key": "work_resumed",
    },
    "/retomar": {
        "event_type": "break_end",
        "event_label": "Retomar labores",
        "module_code": "workforce",
        "status_after": "working",
        "turn_action": "resume_work",
        "payroll_affects": False,
        "reply_key": "work_resumed",
    },
    "/salida": {
        "event_type": "check_out",
        "event_label": "Finalizar turno",
        "module_code": "workforce",
        "status_after": "checked_out",
        "turn_action": "end_shift",
        "payroll_affects": True,
        "reply_key": "shift_ended",
    },
    "/finalizar": {
        "event_type": "check_out",
        "event_label": "Finalizar turno",
        "module_code": "workforce",
        "status_after": "checked_out",
        "turn_action": "end_shift",
        "payroll_affects": True,
        "reply_key": "shift_ended",
    },
    "/finalizar_turno": {
        "event_type": "check_out",
        "event_label": "Finalizar turno",
        "module_code": "workforce",
        "status_after": "checked_out",
        "turn_action": "end_shift",
        "payroll_affects": True,
        "reply_key": "shift_ended",
    },
    "/observacion": {
        "event_type": "observation",
        "event_label": "Observación",
        "module_code": "workforce",
        "status_after": "registered",
        "turn_action": "inside_shift",
        "payroll_affects": False,
        "reply_key": "observation_saved",
        "requires_text": True,
    },
    "/obs": {
        "event_type": "observation",
        "event_label": "Observación",
        "module_code": "workforce",
        "status_after": "registered",
        "turn_action": "inside_shift",
        "payroll_affects": False,
        "reply_key": "observation_saved",
        "requires_text": True,
    },
    "/material": {
        "event_type": "material_request",
        "event_label": "Solicitud de material",
        "module_code": "materials",
        "status_after": "requested",
        "turn_action": "inside_shift",
        "payroll_affects": False,
        "reply_key": "material_requested",
        "requires_text": False,
    },
    "/materiales": {
        "event_type": "material_request",
        "event_label": "Solicitud de material",
        "module_code": "materials",
        "status_after": "requested",
        "turn_action": "inside_shift",
        "payroll_affects": False,
        "reply_key": "material_requested",
        "requires_text": False,
    },
    "/ubicacion": {
        "event_type": "gps_ping",
        "event_label": "Ubicación",
        "module_code": "gps",
        "status_after": "registered",
        "turn_action": "inside_shift",
        "payroll_affects": False,
        "reply_key": "location_requested",
    },
    "/tarea": {
        "event_type": "task_started",
        "event_label": "Tarea",
        "module_code": "field",
        "status_after": "started",
        "turn_action": "inside_shift",
        "payroll_affects": False,
        "reply_key": "task_started",
    },
    "/produccion": {
        "event_type": "production_started",
        "event_label": "Producción",
        "module_code": "production",
        "status_after": "started",
        "turn_action": "inside_shift",
        "payroll_affects": False,
        "reply_key": "production_registered",
    },
    "/venta": {
        "event_type": "sale_reported",
        "event_label": "Venta",
        "module_code": "sales",
        "status_after": "registered",
        "turn_action": "inside_shift",
        "payroll_affects": False,
        "reply_key": "sale_registered",
        "requires_text": True,
    },
    "/estado": {
        "event_type": "status_query",
        "event_label": "Consulta de estado",
        "module_code": "workforce",
        "status_after": "registered",
        "turn_action": "status",
        "payroll_affects": False,
        "reply_key": "status_checked",
    },
}




def _normalize_command(text_value: str) -> tuple[str, str]:
    text_value = (text_value or "").strip()
    if not text_value:
        return "", ""
    parts = text_value.split(maxsplit=1)
    command = parts[0].split("@", 1)[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return command, args


def _telegram_message(update: dict[str, Any]) -> dict[str, Any] | None:
    message = update.get("message") or update.get("edited_message")
    if isinstance(message, dict):
        return message

    callback = update.get("callback_query")
    if isinstance(callback, dict) and isinstance(callback.get("message"), dict):
        # CLONEXA 019C-L1:
        # Telegram callback_query.message.from usually belongs to the bot.
        # Legacy paths that call _telegram_identity(message) must see the real user.
        callback_message = dict(callback["message"])

        callback_from = callback.get("from") or {}
        if isinstance(callback_from, dict) and callback_from:
            callback_message["from"] = callback_from

        callback_data = str(callback.get("data") or "").strip()
        if callback_data:
            callback_message["text"] = callback_data

        return callback_message

    return None


def _telegram_identity_from_update(update: dict[str, Any]) -> tuple[str, str | None, str | None, str | None, str | None, str | None]:
    """
    Devuelve:
    telegram_user_id, username, first_name, chat_id, text_value, callback_query_id
    Soporta mensajes normales y botones inline.
    """
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        from_user = callback.get("from") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        telegram_user_id = str(from_user.get("id") or "")
        username = from_user.get("username")
        first_name = from_user.get("first_name")
        chat_id = str(chat.get("id") or "")
        data = str(callback.get("data") or "").strip()
        callback_query_id = str(callback.get("id") or "")
        return telegram_user_id, username, first_name, chat_id, data, callback_query_id

    message = update.get("message") or update.get("edited_message") or {}
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}
    telegram_user_id = str(from_user.get("id") or "")
    username = from_user.get("username")
    first_name = from_user.get("first_name")
    chat_id = str(chat.get("id") or "")
    text_value = (message.get("text") or "").strip()
    return telegram_user_id, username, first_name, chat_id, text_value, None


def _telegram_identity(message: dict[str, Any]) -> tuple[str, str | None, str | None, str | None]:
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}
    telegram_user_id = str(from_user.get("id") or "")
    username = from_user.get("username")
    first_name = from_user.get("first_name")
    chat_id = str(chat.get("id") or "")
    return telegram_user_id, username, first_name, chat_id


async def _send_telegram_message(
    token: str,
    chat_id: str | None,
    text_value: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    if not chat_id:
        return
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text_value}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
    except httpx.HTTPError:
        # No bloquea captura de eventos si Telegram no acepta la respuesta.
        return


async def _send_telegram_chat_action(token: str, chat_id: str | None, action: str = "typing") -> None:
    if not chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendChatAction",
                json={"chat_id": chat_id, "action": action},
            )
    except httpx.HTTPError:
        return


async def _answer_callback_query(token: str, callback_query_id: str | None, text_value: str | None = None) -> None:
    if not callback_query_id:
        return
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text_value:
        payload["text"] = text_value[:180]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json=payload)
    except httpx.HTTPError:
        return


SUPPORTED_LANGUAGES = {"es", "en", "fr"}
DEFAULT_LANGUAGE = "es"


BOT_TEXTS: dict[str, dict[str, str]] = {
    "es": {
        "choose_language": "🌐 Selecciona tu idioma:",
        "language_saved": "✅ Idioma configurado en Español.",
        "language_updating": "⏳ Actualizando idioma…",
        "language_already": "✅ El idioma ya estaba actualizado.",
        "processing": "⏳ Procesando tu solicitud…\nEspera un momento, estoy validando la información.",
        "not_linked": "No encontré un empleado activo vinculado a este Telegram.\nTelegram ID: {telegram_user_id}\nRegístralo en Personal > Telegram ID y vuelve a intentar.",
        "whoami_unlinked": "CLONEXA recibió tu mensaje.\nTelegram ID: {telegram_user_id}\n{username_line}Pega este Telegram ID en Personal > Telegram ID para vincular el empleado.",
        "menu_title": "Hola {employee_name} 👋\nEmpresa: {company_name}\n\nSelecciona una acción:",
        "menu_next": "Selecciona la siguiente acción:",
        "commands_hint": "También puedes escribir comandos: /entrada, /pausa, /reanudar, /salida, /estado.",
        "shift_started": "✅ Inicio de turno registrado.\nTiempo de trabajo pagable iniciado.",
        "break_started": "☕ Pausa registrada.\nEste tiempo NO suma para nómina ni KPIs de producción.",
        "work_resumed": "✅ Retomaste labores.\nEl tiempo pagable vuelve a contar.",
        "shift_ended": "🏁 Turno finalizado.",
        "end_shift_summary_prompt": "🏁 Para finalizar turno, por favor resume tu gestión de hoy.\n\nEscribe tu resumen en un solo mensaje.",
        "end_shift_summary_saved": "📝 Resumen de gestión guardado en el cierre de jornada.",
        "end_shift_summary_required": "Para cerrar la jornada necesito tu resumen de gestión de hoy.",
        "shift_summary": "Feliz descanso, {employee_name}.\n\nTotal acumulado del corte:\nOrdinarias: {regular}\nExtras: {extra}\n\nProyección pago: {projected_pay}\nDescuento del corte: {discount}\nTotal estimado: {estimated_total}",
        "observation_saved": "📝 Observación registrada.",
        "material_requested": "📦 Solicitud de material registrada.",
        "material_request_prompt": "📦 Selecciona el material disponible:",
        "material_request_pending": "📦 Ya tienes una solicitud de material abierta.",
        "material_inventory_empty": "📦 No hay materiales disponibles en inventario.",
        "material_select_prompt": "📦 Selecciona el material que necesitas:",
        "material_quantity_prompt": "📦 Cantidad para {item_label}:\nEscribe solo el número.",
        "material_quantity_invalid": "📦 Cantidad inválida. Escribe un número mayor a cero.",
        "material_quantity_exceeds": "📦 Stock insuficiente. Disponible: {stock}",
        "material_cart_added": "📦 Agregado al carrito.",
        "material_cart_empty": "📦 El carrito está vacío. Selecciona un material.",
        "material_cart_cancelled": "📦 Solicitud de material cancelada.",
        "material_cart_confirmed": "📦 Solicitud enviada a Materiales. Orden: {order_number}.",
        "material_cart_title": "📦 Carrito de materiales",
        "btn_cart_add": "➕ Agregar otro",
        "btn_cart_confirm": "✅ Confirmar solicitud",
        "btn_cart_cancel": "❌ Cancelar",
        "location_requested": "📍 Solicitud de ubicación registrada. Para ubicación real, usa compartir ubicación en Telegram.",
        "gps_required_for_start": "📍 Para iniciar turno, comparte tu ubicación.\nRecomendado: usa ubicación en vivo durante la jornada. Si tu Telegram solo permite ubicación actual, envíala para iniciar y mantén actualizado el GPS desde /ubicacion.",
        "gps_location_pending": "📍 Ya estoy esperando tu ubicación para iniciar turno.\nComparte tu ubicación con el botón inferior.",
        "gps_location_received_shift_started": "✅ Ubicación recibida.\nInicio de turno registrado con GPS validado. CLONEXA procesará ubicaciones en vivo mientras el turno esté activo.",
        "gps_location_received": "📍 Ubicación registrada.",
        "gps_no_pending": "No tengo una solicitud de ubicación pendiente. Usa el menú para continuar.",
        "btn_share_location": "📍 Compartir ubicación",
        "task_started": "🛠️ Acción de tarea registrada.",
        "production_registered": "🏭 Acción de producción registrada.",
        "sale_registered": "💰 Venta registrada.",
        "status_checked": "Estado consultado.",
        "unknown": "No reconocí esa acción. Usa el menú o escribe /estado.",
        "need_detail": "Falta detalle. Escribe: {command} detalle",
        "module_inactive": "Esta opción no está activa para tu empresa.",
        "must_start_shift": "Primero debes iniciar turno.",
        "already_working": "Ya tienes un turno activo.",
        "cannot_pause": "Solo puedes pausar cuando estás trabajando.",
        "cannot_resume": "Solo puedes retomar labores si estás en pausa.",
        "cannot_end_shift": "No tienes un turno activo para finalizar.",
        "only_resume_or_end": "Estás en pausa. Solo puedes retomar labores o finalizar turno.",
        "status_line": "{employee_name}: estado actual = {status_text}.",
        "btn_start_shift": "🚀 Iniciar turno",
        "btn_break": "☕ Pausa",
        "btn_resume": "▶️ Retomar labores",
        "btn_end_shift": "🏁 Finalizar turno",
        "btn_status": "📊 Estado",
        "btn_observation": "📝 Observación",
        "btn_material": "📦 Solicitar material",
        "btn_location": "📍 Ubicación",
        "btn_task": "🛠️ Tarea",
        "btn_production": "🏭 Producción",
        "btn_sale": "💰 Venta",
        "btn_language": "🌐 Idioma",
    },
    "en": {
        "choose_language": "🌐 Choose your language:",
        "language_saved": "✅ Language set to English.",
        "language_updating": "⏳ Updating language…",
        "language_already": "✅ Language was already updated.",
        "processing": "⏳ Processing your request…\nPlease wait while I validate the information.",
        "not_linked": "I could not find an active employee linked to this Telegram.\nTelegram ID: {telegram_user_id}\nRegister it in Personal > Telegram ID and try again.",
        "whoami_unlinked": "CLONEXA received your message.\nTelegram ID: {telegram_user_id}\n{username_line}Paste this Telegram ID in Personal > Telegram ID to link the employee.",
        "menu_title": "Hi {employee_name} 👋\nCompany: {company_name}\n\nSelect an action:",
        "menu_next": "Select the next action:",
        "commands_hint": "You can also type commands: /entrada, /pausa, /reanudar, /salida, /estado.",
        "shift_started": "✅ Shift started.\nPayable work time has started.",
        "break_started": "☕ Break registered.\nThis time does NOT count for payroll or production KPIs.",
        "work_resumed": "✅ Work resumed.\nPayable time is counting again.",
        "shift_ended": "🏁 Shift ended.",
        "shift_summary": "Rest well, {employee_name}.\n\nCurrent payroll period total:\nRegular: {regular}\nOvertime: {extra}\n\nProjected pay: {projected_pay}\nPeriod discount: {discount}\nEstimated total: {estimated_total}",
        "observation_saved": "📝 Observation saved.",
        "material_requested": "📦 Material request saved.",
        "material_request_prompt": "📦 Select an available material:",
        "material_request_pending": "📦 You already have an open material request.",
        "material_inventory_empty": "📦 No available materials in inventory.",
        "material_select_prompt": "📦 Select the material you need:",
        "material_quantity_prompt": "📦 Quantity for {item_label}:\nType only the number.",
        "material_quantity_invalid": "📦 Invalid quantity. Type a number greater than zero.",
        "material_quantity_exceeds": "📦 Not enough stock. Available: {stock}",
        "material_cart_added": "📦 Added to cart.",
        "material_cart_empty": "📦 Cart is empty. Select a material.",
        "material_cart_cancelled": "📦 Material request cancelled.",
        "material_cart_confirmed": "📦 Request sent to Materials. Order: {order_number}.",
        "material_cart_title": "📦 Materials cart",
        "btn_cart_add": "➕ Add another",
        "btn_cart_confirm": "✅ Confirm request",
        "btn_cart_cancel": "❌ Cancel",
        "location_requested": "📍 Location request saved. For real location, use Telegram location sharing.",
        "gps_required_for_start": "📍 To start your shift, share your current location.\nUse the button below: Share location.",
        "gps_location_pending": "📍 I am already waiting for your location to start the shift.\nShare your location using the button below.",
        "gps_location_received_shift_started": "✅ Location received.\nShift started with GPS validation.",
        "gps_location_received": "📍 Location saved.",
        "gps_no_pending": "I do not have a pending location request. Use the menu to continue.",
        "btn_share_location": "📍 Share location",
        "task_started": "🛠️ Task action saved.",
        "production_registered": "🏭 Production action saved.",
        "sale_registered": "💰 Sale saved.",
        "status_checked": "Status checked.",
        "unknown": "I did not recognize that action. Use the menu or type /estado.",
        "need_detail": "Missing detail. Type: {command} detail",
        "module_inactive": "This option is not active for your company.",
        "must_start_shift": "You must start your shift first.",
        "already_working": "You already have an active shift.",
        "cannot_pause": "You can only start a break while working.",
        "cannot_resume": "You can only resume work while on break.",
        "cannot_end_shift": "You do not have an active shift to end.",
        "only_resume_or_end": "You are on break. You can only resume work or end your shift.",
        "status_line": "{employee_name}: current status = {status_text}.",
        "btn_start_shift": "🚀 Start shift",
        "btn_break": "☕ Break",
        "btn_resume": "▶️ Resume work",
        "btn_end_shift": "🏁 End shift",
        "btn_status": "📊 Status",
        "btn_observation": "📝 Observation",
        "btn_material": "📦 Material request",
        "btn_location": "📍 Location",
        "btn_task": "🛠️ Task",
        "btn_production": "🏭 Production",
        "btn_sale": "💰 Sale",
        "btn_language": "🌐 Language",
    },
    "fr": {
        "choose_language": "🌐 Sélectionnez votre langue :",
        "language_saved": "✅ Langue configurée en Français.",
        "language_updating": "⏳ Mise à jour de la langue…",
        "language_already": "✅ La langue était déjà mise à jour.",
        "processing": "⏳ Traitement de votre demande…\nVeuillez patienter pendant la validation.",
        "not_linked": "Je n’ai pas trouvé d’employé actif lié à ce Telegram.\nTelegram ID : {telegram_user_id}\nEnregistrez-le dans Personal > Telegram ID et réessayez.",
        "whoami_unlinked": "CLONEXA a reçu votre message.\nTelegram ID : {telegram_user_id}\n{username_line}Collez cet ID dans Personal > Telegram ID pour lier l’employé.",
        "menu_title": "Bonjour {employee_name} 👋\nEntreprise : {company_name}\n\nSélectionnez une action :",
        "menu_next": "Sélectionnez la prochaine action :",
        "commands_hint": "Vous pouvez aussi écrire : /entrada, /pausa, /reanudar, /salida, /estado.",
        "shift_started": "✅ Début de service enregistré.\nLe temps de travail payable commence.",
        "break_started": "☕ Pause enregistrée.\nCe temps ne compte PAS pour la paie ni les KPIs de production.",
        "work_resumed": "✅ Reprise du travail.\nLe temps payable compte à nouveau.",
        "shift_ended": "🏁 Service terminé.",
        "shift_summary": "Bon repos, {employee_name}.\n\nTotal cumulé de la période :\nOrdinaires : {regular}\nSupplémentaires : {extra}\n\nProjection paiement : {projected_pay}\nRemise de la période : {discount}\nTotal estimé : {estimated_total}",
        "observation_saved": "📝 Observation enregistrée.",
        "material_requested": "📦 Demande de matériel enregistrée.",
        "material_request_prompt": "📦 Sélectionnez le matériel disponible:",
        "material_request_pending": "📦 Vous avez déjà une demande de matériel ouverte.",
        "material_inventory_empty": "📦 Aucun matériel disponible en inventaire.",
        "material_select_prompt": "📦 Sélectionnez le matériel nécessaire:",
        "material_quantity_prompt": "📦 Quantité pour {item_label}:\nÉcrivez seulement le nombre.",
        "material_quantity_invalid": "📦 Quantité invalide. Écrivez un nombre supérieur à zéro.",
        "material_quantity_exceeds": "📦 Stock insuffisant. Disponible: {stock}",
        "material_cart_added": "📦 Ajouté au panier.",
        "material_cart_empty": "📦 Le panier est vide. Sélectionnez un matériel.",
        "material_cart_cancelled": "📦 Demande de matériel annulée.",
        "material_cart_confirmed": "📦 Demande envoyée aux Matériaux. Ordre: {order_number}.",
        "material_cart_title": "📦 Panier de matériaux",
        "btn_cart_add": "➕ Ajouter un autre",
        "btn_cart_confirm": "✅ Confirmer la demande",
        "btn_cart_cancel": "❌ Annuler",
        "location_requested": "📍 Demande de localisation enregistrée. Pour la localisation réelle, utilisez le partage de position Telegram.",
        "gps_required_for_start": "📍 Pour commencer le service, partagez votre position actuelle.\nUtilisez le bouton ci-dessous : Partager la position.",
        "gps_location_pending": "📍 J’attends déjà votre position pour commencer le service.\nPartagez votre position avec le bouton inférieur.",
        "gps_location_received_shift_started": "✅ Position reçue.\nDébut de service enregistré avec GPS validé.",
        "gps_location_received": "📍 Position enregistrée.",
        "gps_no_pending": "Je n’ai pas de demande de position en attente. Utilisez le menu pour continuer.",
        "btn_share_location": "📍 Partager la position",
        "task_started": "🛠️ Action de tâche enregistrée.",
        "production_registered": "🏭 Action de production enregistrée.",
        "sale_registered": "💰 Vente enregistrée.",
        "status_checked": "Statut consulté.",
        "unknown": "Je n’ai pas reconnu cette action. Utilisez le menu ou écrivez /estado.",
        "need_detail": "Détail manquant. Écrivez : {command} détail",
        "module_inactive": "Cette option n’est pas active pour votre entreprise.",
        "must_start_shift": "Vous devez d’abord commencer votre service.",
        "already_working": "Vous avez déjà un service actif.",
        "cannot_pause": "Vous ne pouvez faire une pause que lorsque vous travaillez.",
        "cannot_resume": "Vous ne pouvez reprendre que si vous êtes en pause.",
        "cannot_end_shift": "Vous n’avez pas de service actif à terminer.",
        "only_resume_or_end": "Vous êtes en pause. Vous pouvez seulement reprendre ou terminer le service.",
        "status_line": "{employee_name} : statut actuel = {status_text}.",
        "btn_start_shift": "🚀 Début service",
        "btn_break": "☕ Pause",
        "btn_resume": "▶️ Reprendre",
        "btn_end_shift": "🏁 Fin service",
        "btn_status": "📊 Statut",
        "btn_observation": "📝 Observation",
        "btn_material": "📦 Matériel",
        "btn_location": "📍 Position",
        "btn_task": "🛠️ Tâche",
        "btn_production": "🏭 Production",
        "btn_sale": "💰 Vente",
        "btn_language": "🌐 Langue",
    },
}


def _lang(value: str | None) -> str:
    value = (value or DEFAULT_LANGUAGE).lower().strip()
    return value if value in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def _txt(language: str | None, key: str, **kwargs: Any) -> str:
    lang = _lang(language)
    template = BOT_TEXTS.get(lang, BOT_TEXTS[DEFAULT_LANGUAGE]).get(key)
    if template is None:
        template = BOT_TEXTS[DEFAULT_LANGUAGE].get(key, key)
    return template.format(**kwargs)


def _language_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Español", "callback_data": "clx:lang:es"},
                {"text": "English", "callback_data": "clx:lang:en"},
                {"text": "Français", "callback_data": "clx:lang:fr"},
            ]
        ]
    }


def _location_request_keyboard(language: str) -> dict[str, Any]:
    return {
        "keyboard": [[{"text": _txt(language, "btn_share_location"), "request_location": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
        "selective": True,
    }


def _remove_reply_keyboard() -> dict[str, Any]:
    return {"remove_keyboard": True}


def _callback_to_command(data: str) -> str:
    data = (data or "").strip()
    if data.startswith("clx:cmd:"):
        return "/" + data.removeprefix("clx:cmd:").strip().lower()
    return data


async def _get_user_language(
    db: AsyncSession,
    company_id: UUID,
    telegram_user_id: str | None,
) -> str:
    await ensure_bot_storage(db)
    if not telegram_user_id:
        return DEFAULT_LANGUAGE
    result = await db.execute(
        text("""
            SELECT language
            FROM company_telegram_user_preferences
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
            LIMIT 1
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )
    row = result.mappings().first()
    return _lang(row["language"] if row else DEFAULT_LANGUAGE)


async def _user_language_preference_exists(
    db: AsyncSession,
    company_id: UUID,
    telegram_user_id: str | None,
) -> bool:
    await ensure_bot_storage(db)
    if not telegram_user_id:
        return False
    result = await db.execute(
        text("""
            SELECT 1
            FROM company_telegram_user_preferences
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
            LIMIT 1
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )
    return result.first() is not None



async def _set_user_language(
    db: AsyncSession,
    company_id: UUID,
    telegram_user_id: str,
    telegram_username: str | None,
    language: str,
) -> str:
    await ensure_bot_storage(db)
    language = _lang(language)
    await db.execute(
        text("""
            INSERT INTO company_telegram_user_preferences (
                company_id,
                telegram_user_id,
                telegram_username,
                language,
                created_at,
                updated_at
            )
            VALUES (
                :company_id,
                :telegram_user_id,
                :telegram_username,
                :language,
                now(),
                now()
            )
            ON CONFLICT (company_id, telegram_user_id)
            DO UPDATE SET
                telegram_username = EXCLUDED.telegram_username,
                language = EXCLUDED.language,
                updated_at = now()
        """),
        {
            "company_id": str(company_id),
            "telegram_user_id": str(telegram_user_id),
            "telegram_username": telegram_username,
            "language": language,
        },
    )
    await db.commit()
    return language


async def _enabled_module_codes(db: AsyncSession, company_id: UUID) -> set[str]:
    result = await db.execute(
        text("""
            SELECT m.code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = :company_id
              AND cm.enabled IS TRUE
              AND m.is_active IS TRUE
        """),
        {"company_id": str(company_id)},
    )
    codes = {str(row[0]).lower() for row in result.all()}
    codes.add("core")
    codes.add("workforce")
    codes.add("bots")
    return codes


MATERIAL_REQUEST_ALLOWED_ROLES = {"admin", "admin_empresa", "supervisor", "inventario", "inventory"}


def _role_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def _employee_can_request_material(employee: Employee | None) -> bool:
    if employee is None:
        return False
    role = _role_key(getattr(employee, "role", None) or getattr(employee, "employee_type", None))
    if role in MATERIAL_REQUEST_ALLOWED_ROLES:
        return True
    return role.startswith("admin") or "supervisor" in role or "inventario" in role or "inventory" in role



async def _ensure_gps_perimeter_storage(db: AsyncSession) -> None:
    """
    014B GPS:
    La validación de perímetro pertenece al sistema CLONEXA, no al bot.
    El bot solo solicita/recibe la ubicación; backend clasifica inside/outside.
    """
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_gps_perimeters (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            slot integer NOT NULL,
            name varchar(140) NOT NULL DEFAULT '',
            latitude_min numeric(12,8) NULL,
            latitude_max numeric(12,8) NULL,
            longitude_min numeric(12,8) NULL,
            longitude_max numeric(12,8) NULL,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_company_gps_perimeters_company_slot UNIQUE (company_id, slot),
            CONSTRAINT ck_company_gps_perimeters_slot CHECK (slot >= 1 AND slot <= 5)
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_gps_perimeters_company ON company_gps_perimeters(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_gps_perimeters_active ON company_gps_perimeters(company_id, is_active);"))


def _gps_point_inside_perimeter(latitude: float, longitude: float, perimeter: dict[str, Any]) -> bool:
    try:
        lat_min = float(perimeter.get("latitude_min"))
        lat_max = float(perimeter.get("latitude_max"))
        lng_min = float(perimeter.get("longitude_min"))
        lng_max = float(perimeter.get("longitude_max"))
    except Exception:
        return False

    if lat_min > lat_max:
        lat_min, lat_max = lat_max, lat_min
    if lng_min > lng_max:
        lng_min, lng_max = lng_max, lng_min

    return lat_min <= latitude <= lat_max and lng_min <= longitude <= lng_max


async def _validate_gps_location_for_company(
    db: AsyncSession,
    *,
    company_id: UUID,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    await _ensure_gps_perimeter_storage(db)

    result = await db.execute(
        text("""
            SELECT id, slot, name, latitude_min, latitude_max, longitude_min, longitude_max
            FROM company_gps_perimeters
            WHERE company_id = :company_id
              AND is_active IS TRUE
              AND latitude_min IS NOT NULL
              AND latitude_max IS NOT NULL
              AND longitude_min IS NOT NULL
              AND longitude_max IS NOT NULL
            ORDER BY slot ASC
            LIMIT 5
        """),
        {"company_id": str(company_id)},
    )

    perimeters = [dict(row) for row in result.mappings().all()]
    if not perimeters:
        return {
            "gps_status": "unconfigured",
            "gps_status_label": "Sin perímetro",
            "matched_perimeter_id": None,
            "matched_perimeter_name": None,
            "matched_perimeter_slot": None,
        }

    for perimeter in perimeters:
        if _gps_point_inside_perimeter(latitude, longitude, perimeter):
            return {
                "gps_status": "inside",
                "gps_status_label": "Dentro de perímetro",
                "matched_perimeter_id": str(perimeter.get("id")),
                "matched_perimeter_name": perimeter.get("name") or f"Punto {perimeter.get('slot')}",
                "matched_perimeter_slot": perimeter.get("slot"),
            }

    return {
        "gps_status": "outside",
        "gps_status_label": "Fuera de perímetro",
        "matched_perimeter_id": None,
        "matched_perimeter_name": None,
        "matched_perimeter_slot": None,
    }




# CLONEXA 015C-R7 — URL pública configurable para Telegram Web App.
# Prioridad:
# 1) PUBLIC_BASE_URL
# 2) CLONEXA_PUBLIC_BASE_URL
# 3) URL temporal de desarrollo / fallback
CLONEXA_MATERIALS_WEBAPP_BASE_URL = (
    os.getenv("PUBLIC_BASE_URL")
    or os.getenv("CLONEXA_PUBLIC_BASE_URL")
    or "https://reported-papers-catalogue-vii.trycloudflare.com"
).rstrip("/")


def _materials_webapp_url(*, company_id: Any, telegram_user_id: str | None = None) -> str:
    params = {
        "company_id": str(company_id),
    }
    if telegram_user_id:
        params["telegram_user_id"] = str(telegram_user_id)
    return f"{CLONEXA_MATERIALS_WEBAPP_BASE_URL}/webapp/materials?{urlencode(params)}"


def _materials_webapp_keyboard(*, company_id: Any, telegram_user_id: str | None = None) -> dict[str, Any]:
    return {
        "inline_keyboard": [[
            {
                "text": "📦 Abrir inventario",
                "web_app": {"url": _materials_webapp_url(company_id=company_id, telegram_user_id=telegram_user_id)},
            }
        ]]
    }


async def _send_materials_webapp_button(
    *,
    token: str,
    chat_id: str | None,
    company_id: Any,
    telegram_user_id: str | None,
) -> None:
    await _send_telegram_message(
        token,
        chat_id,
        "📦 Abre el inventario, busca el material, agrega cantidades al carrito y confirma la solicitud.",
        reply_markup=_materials_webapp_keyboard(company_id=company_id, telegram_user_id=telegram_user_id),
    )


def _menu_keyboard(language: str, enabled_modules: set[str], status_text: str | None = None, employee: Employee | None = None) -> dict[str, Any]:
    status_key = status_text or "sin_turno"
    if status_key in {"not_started", "checked_out"}:
        status_key = "sin_turno"

    rows: list[list[dict[str, str]]] = []

    # Menú lógico por estado: solo se muestra la siguiente acción válida.
    if status_key == "sin_turno":
        rows.append([{"text": _txt(language, "btn_start_shift"), "callback_data": "clx:cmd:entrada"}])
        rows.append([{"text": _txt(language, "btn_language"), "callback_data": "clx:language"}])
        return {"inline_keyboard": rows}

    if status_key == "on_break":
        rows.append([
            {"text": _txt(language, "btn_resume"), "callback_data": "clx:cmd:reanudar"},
            {"text": _txt(language, "btn_end_shift"), "callback_data": "clx:cmd:salida"},
        ])
        rows.append([{"text": _txt(language, "btn_language"), "callback_data": "clx:language"}])
        return {"inline_keyboard": rows}

    # Trabajando: pausa / cierre de turno; extras solo si encajan y están activos.
    rows.append([
        {"text": _txt(language, "btn_break"), "callback_data": "clx:cmd:pausa"},
        {"text": _txt(language, "btn_end_shift"), "callback_data": "clx:cmd:salida"},
    ])

    # Opciones internas del turno. No se muestran Estado ni Venta para evitar ruido operativo.
    extra_rows: list[list[dict[str, str]]] = []
    if "materials" in enabled_modules and "inventory" in enabled_modules and _employee_can_request_material(employee):
        extra_rows.append([{"text": _txt(language, "btn_material"), "callback_data": "clx:cmd:material"}])
    if "gps" in enabled_modules:
        extra_rows.append([{"text": _txt(language, "btn_location"), "callback_data": "clx:cmd:ubicacion"}])
    if "field" in enabled_modules:
        extra_rows.append([{"text": _txt(language, "btn_task"), "callback_data": "clx:cmd:tarea"}])
    if "production" in enabled_modules:
        extra_rows.append([{"text": _txt(language, "btn_production"), "callback_data": "clx:cmd:produccion"}])

    rows.extend(extra_rows)
    rows.append([{"text": _txt(language, "btn_language"), "callback_data": "clx:language"}])
    return {"inline_keyboard": rows}


async def _send_dynamic_menu(
    db: AsyncSession,
    *,
    token: str,
    chat_id: str | None,
    company: Company,
    employee: Employee,
    language: str,
    greet: bool = False,
) -> None:
    enabled_modules = await _enabled_module_codes(db, company.id)
    current = await _get_current_attendance_status(db, company.id, employee.id)
    status_text = _current_status_key(current)
    if greet:
        text_value = _txt(language, "menu_title", employee_name=employee.full_name, company_name=company.name)
    else:
        text_value = _txt(language, "menu_next")
    await _send_telegram_message(
        token,
        chat_id,
        text_value,
        reply_markup=_menu_keyboard(language, enabled_modules, status_text, employee),
    )


def _requires_active_shift(command_config: dict[str, Any]) -> bool:
    return command_config.get("turn_action") == "inside_shift"


def _current_status_key(current: WorkforceAttendanceStatus | None) -> str:
    if current is None or not current.status:
        return "sin_turno"
    if current.status == "not_started":
        return "sin_turno"
    return current.status


def _validate_turn_transition(
    *,
    current: WorkforceAttendanceStatus | None,
    command_config: dict[str, Any],
    language: str,
) -> tuple[bool, str | None]:
    status_key = _current_status_key(current)
    action = command_config.get("turn_action")

    if action == "start_shift":
        if status_key in {"working", "on_break"}:
            return False, _txt(language, "already_working")
        return True, None

    if action == "start_break":
        if status_key != "working":
            return False, _txt(language, "cannot_pause")
        return True, None

    if action == "resume_work":
        if status_key != "on_break":
            return False, _txt(language, "cannot_resume")
        return True, None

    if action == "end_shift":
        if status_key not in {"working", "on_break"}:
            return False, _txt(language, "cannot_end_shift")
        return True, None

    if action == "inside_shift":
        if status_key == "sin_turno" or status_key == "checked_out":
            return False, _txt(language, "must_start_shift")
        if status_key == "on_break":
            return False, _txt(language, "only_resume_or_end")
        return True, None

    return True, None


async def _set_pending_gps_checkin(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
    telegram_username: str | None,
    employee_id: UUID,
    chat_id: str | None,
    language: str,
) -> None:
    await ensure_bot_storage(db)
    await db.execute(
        text("""
            INSERT INTO company_telegram_pending_actions (
                company_id,
                telegram_user_id,
                telegram_username,
                employee_id,
                action,
                payload_json,
                expires_at,
                updated_at
            )
            VALUES (
                :company_id,
                :telegram_user_id,
                :telegram_username,
                :employee_id,
                'gps_check_in',
                CAST(:payload_json AS jsonb),
                now() + interval '30 minutes',
                now()
            )
            ON CONFLICT (company_id, telegram_user_id, action)
            DO UPDATE SET
                telegram_username = EXCLUDED.telegram_username,
                employee_id = EXCLUDED.employee_id,
                payload_json = EXCLUDED.payload_json,
                expires_at = EXCLUDED.expires_at,
                updated_at = now()
        """),
        {
            "company_id": str(company_id),
            "telegram_user_id": str(telegram_user_id),
            "telegram_username": telegram_username,
            "employee_id": str(employee_id),
            "payload_json": json.dumps(
                {
                    "chat_id": chat_id,
                    "language": _lang(language),
                    "reason": "gps_required_before_check_in",
                }
            ),
        },
    )


async def _get_pending_gps_checkin(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
) -> dict[str, Any] | None:
    await ensure_bot_storage(db)
    result = await db.execute(
        text("""
            SELECT id, employee_id, payload_json, expires_at
            FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'gps_check_in'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY updated_at DESC
            LIMIT 1
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )
    row = result.mappings().first()
    if not row:
        return None
    return dict(row)


async def _clear_pending_gps_checkin(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
) -> None:
    await db.execute(
        text("""
            DELETE FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'gps_check_in'
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )


# CLONEXA_019D_C1_TELEGRAM_LIVE_LOCATION_TRACKING_START
def _is_live_location_message(message: dict[str, Any] | None) -> bool:
    """
    Telegram envía ubicaciones en vivo como message.location y luego como edited_message.location.
    No todos los clientes conservan live_period en cada update; edit_date también es señal útil.
    """
    if not isinstance(message, dict):
        return False

    location = message.get("location")
    if not isinstance(location, dict):
        return False

    return bool(location.get("live_period") or message.get("edit_date"))


async def _open_gps_tracking_session(
    db: AsyncSession,
    *,
    company_id: UUID,
    employee: Employee,
    telegram_user_id: str | None,
    chat_id: str | None,
    event: WorkforceAttendanceEvent,
    message: dict[str, Any],
) -> None:
    await ensure_bot_storage(db)

    location = message.get("location") or {}
    metadata = {
        "source": "telegram_live_location",
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "telegram_message_id": message.get("message_id"),
        "live_period": location.get("live_period"),
        "opened_by": "check_in_gps_location",
        "last_event_id": str(event.id),
    }

    await db.execute(
        text("""
            UPDATE gps_tracking_sessions
               SET status = 'closed',
                   ended_at = COALESCE(ended_at, now()),
                   updated_at = now(),
                   metadata_json = COALESCE(metadata_json, '{}'::jsonb) || CAST(:closed_metadata AS jsonb)
             WHERE company_id = :company_id
               AND employee_id = :employee_id
               AND status = 'active'
        """),
        {
            "company_id": str(company_id),
            "employee_id": str(employee.id),
            "closed_metadata": json.dumps({"closed_reason": "new_check_in_reopened"}),
        },
    )

    await db.execute(
        text("""
            INSERT INTO gps_tracking_sessions (
                company_id,
                employee_id,
                telegram_user_id,
                chat_id,
                source_channel,
                status,
                started_at,
                last_location_at,
                last_event_id,
                metadata_json,
                updated_at
            )
            VALUES (
                :company_id,
                :employee_id,
                :telegram_user_id,
                :chat_id,
                'telegram_live_location',
                'active',
                :started_at,
                :last_location_at,
                :last_event_id,
                CAST(:metadata_json AS jsonb),
                now()
            )
        """),
        {
            "company_id": str(company_id),
            "employee_id": str(employee.id),
            "telegram_user_id": str(telegram_user_id or ""),
            "chat_id": str(chat_id or ""),
            "started_at": event.occurred_at,
            "last_location_at": event.occurred_at,
            "last_event_id": str(event.id),
            "metadata_json": json.dumps(metadata, ensure_ascii=False, default=str),
        },
    )


async def _touch_gps_tracking_session(
    db: AsyncSession,
    *,
    company_id: UUID,
    employee: Employee,
    event: WorkforceAttendanceEvent,
    message: dict[str, Any],
) -> None:
    await ensure_bot_storage(db)

    location = message.get("location") or {}
    metadata = {
        "last_event_id": str(event.id),
        "last_live_period": location.get("live_period"),
        "last_telegram_message_id": message.get("message_id"),
        "last_telegram_edit_date": message.get("edit_date"),
    }

    await db.execute(
        text("""
            UPDATE gps_tracking_sessions
               SET last_location_at = :last_location_at,
                   last_event_id = :last_event_id,
                   updated_at = now(),
                   metadata_json = COALESCE(metadata_json, '{}'::jsonb) || CAST(:metadata_json AS jsonb)
             WHERE company_id = :company_id
               AND employee_id = :employee_id
               AND status = 'active'
        """),
        {
            "company_id": str(company_id),
            "employee_id": str(employee.id),
            "last_location_at": event.occurred_at,
            "last_event_id": str(event.id),
            "metadata_json": json.dumps(metadata, ensure_ascii=False, default=str),
        },
    )


async def _close_gps_tracking_session(
    db: AsyncSession,
    *,
    company_id: UUID,
    employee: Employee,
    ended_at: datetime,
    reason: str = "check_out",
) -> None:
    await ensure_bot_storage(db)

    await db.execute(
        text("""
            UPDATE gps_tracking_sessions
               SET status = 'closed',
                   ended_at = :ended_at,
                   updated_at = now(),
                   metadata_json = COALESCE(metadata_json, '{}'::jsonb) || CAST(:metadata_json AS jsonb)
             WHERE company_id = :company_id
               AND employee_id = :employee_id
               AND status = 'active'
        """),
        {
            "company_id": str(company_id),
            "employee_id": str(employee.id),
            "ended_at": ended_at,
            "metadata_json": json.dumps({"closed_reason": reason}, ensure_ascii=False),
        },
    )
# CLONEXA_019D_C1_TELEGRAM_LIVE_LOCATION_TRACKING_END


async def _set_pending_end_shift_summary(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
    telegram_username: str | None,
    employee_id: UUID,
    chat_id: str | None,
    language: str,
) -> None:
    await ensure_bot_storage(db)
    await db.execute(
        text("""
            INSERT INTO company_telegram_pending_actions (
                company_id,
                telegram_user_id,
                telegram_username,
                employee_id,
                action,
                payload_json,
                expires_at,
                updated_at
            )
            VALUES (
                :company_id,
                :telegram_user_id,
                :telegram_username,
                :employee_id,
                'end_shift_summary',
                CAST(:payload_json AS jsonb),
                now() + interval '90 minutes',
                now()
            )
            ON CONFLICT (company_id, telegram_user_id, action)
            DO UPDATE SET
                telegram_username = EXCLUDED.telegram_username,
                employee_id = EXCLUDED.employee_id,
                payload_json = EXCLUDED.payload_json,
                expires_at = EXCLUDED.expires_at,
                updated_at = now()
        """),
        {
            "company_id": str(company_id),
            "telegram_user_id": str(telegram_user_id),
            "telegram_username": telegram_username,
            "employee_id": str(employee_id),
            "payload_json": json.dumps(
                {
                    "chat_id": chat_id,
                    "language": _lang(language),
                    "reason": "end_shift_summary_required",
                }
            ),
        },
    )


async def _get_pending_end_shift_summary(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
) -> dict[str, Any] | None:
    await ensure_bot_storage(db)
    result = await db.execute(
        text("""
            SELECT id, employee_id, payload_json, expires_at
            FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'end_shift_summary'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY updated_at DESC
            LIMIT 1
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _clear_pending_end_shift_summary(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
) -> None:
    await db.execute(
        text("""
            DELETE FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'end_shift_summary'
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )


async def _process_end_shift_summary_text(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    token: str,
    update: dict[str, Any],
    message: dict[str, Any],
    telegram_user_id: str,
    username: str | None,
    chat_id: str | None,
    text_value: str,
    language: str,
    send_replies: bool,
) -> TelegramBotPollItem | None:
    pending = await _get_pending_end_shift_summary(
        db,
        company_id=bot.company_id,
        telegram_user_id=telegram_user_id,
    )
    if pending is None:
        return None

    summary = (text_value or "").strip()

    if not summary or summary.startswith("/") or summary.startswith("clx:"):
        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "end_shift_summary_prompt"))
        return TelegramBotPollItem(
            update_id=update.get("update_id"),
            ok=False,
            action="end_shift_summary_required",
            message=_txt(language, "end_shift_summary_required"),
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    employee = None
    pending_employee_id = pending.get("employee_id")
    if pending_employee_id:
        try:
            employee = await db.get(Employee, UUID(str(pending_employee_id)))
        except Exception:
            employee = None

    if employee is None:
        employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)

    employee_status = str(getattr(employee, "status", "") or "").lower() if employee is not None else ""
    if employee is None or str(employee.company_id) != str(bot.company_id) or employee_status not in {"active", "activo"}:
        await _clear_pending_end_shift_summary(
            db,
            company_id=bot.company_id,
            telegram_user_id=telegram_user_id,
        )
        await db.commit()
        if send_replies:
            await _send_telegram_message(
                token,
                chat_id,
                _txt(language, "not_linked", telegram_user_id=telegram_user_id),
                reply_markup=_language_keyboard(),
            )
        return TelegramBotPollItem(
            update_id=update.get("update_id"),
            ok=False,
            action="not_linked",
            message="Empleado no vinculado.",
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    command_config = TELEGRAM_COMMANDS["/salida"]
    created, message_text = await _create_bot_attendance_event(
        db,
        bot=bot,
        employee=employee,
        update=update,
        message=message,
        command="/salida",
        args=summary,
        command_config=command_config,
        language=language,
    )

    await _clear_pending_end_shift_summary(
        db,
        company_id=bot.company_id,
        telegram_user_id=telegram_user_id,
    )
    await db.commit()

    if send_replies:
        company = await ensure_company_exists(db, bot.company_id)
        await _send_telegram_message(
            token,
            chat_id,
            f"{message_text}\n\n{_txt(language, 'end_shift_summary_saved')}",
        )
        await _send_dynamic_menu(
            db,
            token=token,
            chat_id=chat_id,
            company=company,
            employee=employee,
            language=language,
        )

    return TelegramBotPollItem(
        update_id=update.get("update_id"),
        ok=created,
        action="check_out",
        message=message_text,
        employee_id=employee.id,
        employee_name=employee.full_name,
        event_created=created,
        telegram_user_id=telegram_user_id,
        telegram_username=username,
    )


async def _ensure_material_requests_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS material_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NULL REFERENCES employees(id) ON DELETE SET NULL,
            employee_name varchar(180) NULL,
            employee_role varchar(100) NULL,
            material_name text NOT NULL DEFAULT '',
            quantity numeric(14, 2) NOT NULL DEFAULT 1,
            unit varchar(40) NULL,
            notes text NULL,
            status varchar(40) NOT NULL DEFAULT 'pending',
            source_channel varchar(80) NOT NULL DEFAULT 'telegram',
            source_ref varchar(220) NULL,
            attendance_event_id uuid NULL,
            requested_at timestamptz NOT NULL DEFAULT now(),
            status_updated_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """))
    for stmt in [
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS order_number varchar(80) NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS inventory_item_id uuid NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS destination text NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS quantity_returned numeric(14,2) NOT NULL DEFAULT 0",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS approved_at timestamptz NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS delivered_at timestamptz NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS returned_at timestamptz NULL",
    ]:
        await db.execute(text(stmt))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS material_order_units (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            request_id uuid NOT NULL REFERENCES material_requests(id) ON DELETE CASCADE,
            order_number varchar(80) NOT NULL,
            inventory_item_id uuid NULL,
            unit_index integer NOT NULL,
            label_sku varchar(220) NULL,
            status varchar(40) NOT NULL DEFAULT 'reserved',
            destination text NULL,
            returned_observation text NULL,
            delivered_at timestamptz NULL,
            returned_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_company ON material_requests(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_status ON material_requests(company_id, status);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_employee ON material_requests(company_id, employee_id);"))
    await db.execute(text("DROP INDEX IF EXISTS uq_material_requests_order;"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_order ON material_requests(company_id, order_number);"))
    await db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_material_requests_source_ref ON material_requests(company_id, source_ref) WHERE source_ref IS NOT NULL;"))


def _parse_material_request_text(raw: str) -> dict[str, Any]:
    text_value = (raw or "").strip()
    if not text_value:
        return {"material_name": "", "quantity": Decimal("1.00"), "unit": "", "notes": ""}

    parts = text_value.split()
    quantity = Decimal("1.00")
    quantity_index: int | None = None

    for index, part in enumerate(parts):
        normalized = part.replace(",", ".")
        try:
            quantity = Decimal(normalized)
            quantity_index = index
            break
        except Exception:
            continue

    if quantity_index is None:
        return {
            "material_name": text_value[:240],
            "quantity": quantity,
            "unit": "",
            "notes": "",
        }

    material_name = " ".join(parts[:quantity_index]).strip() or text_value
    unit = parts[quantity_index + 1].strip() if quantity_index + 1 < len(parts) else ""
    notes = " ".join(parts[quantity_index + 2:]).strip() if quantity_index + 2 < len(parts) else ""

    return {
        "material_name": material_name[:240],
        "quantity": quantity,
        "unit": unit[:40],
        "notes": notes[:600],
    }





def _format_material_decimal(value: Any) -> str:
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
        if amount == amount.to_integral_value():
            return str(int(amount))
        return str(amount).rstrip("0").rstrip(".")
    except Exception:
        return str(value or "0")


def _inventory_item_label(item: dict[str, Any] | None) -> str:
    item = item or {}
    base = (
        item.get("name_reference")
        or item.get("name")
        or item.get("reference")
        or item.get("sku")
        or "Material"
    )
    size = (item.get("item_size") or item.get("size") or "").strip() if isinstance(item.get("item_size") or item.get("size") or "", str) else ""
    return f"{base} · {size}" if size else str(base)


async def _list_inventory_items_for_material_cart(
    db: AsyncSession,
    *,
    company_id: UUID,
    limit: int = 12,
) -> list[dict[str, Any]]:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL,
            name_reference text NULL,
            item_size varchar(120) NULL,
            sku text NULL,
            name text NULL,
            reference text NULL,
            current_stock numeric(14,2) DEFAULT 0,
            status varchar(40) DEFAULT 'active',
            is_active boolean DEFAULT true,
            created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now()
        );
    """))
    result = await db.execute(
        text("""
            SELECT id, company_id, name_reference, item_size, sku, name, reference, current_stock, status
            FROM inventory_items
            WHERE company_id = :company_id
              AND COALESCE(status, 'active') = 'active'
              AND COALESCE(is_active, true) IS TRUE
              AND COALESCE(current_stock, 0) > 0
            ORDER BY lower(COALESCE(name_reference, name, reference, sku, '')), created_at DESC
            LIMIT :limit
        """),
        {"company_id": str(company_id), "limit": max(1, min(int(limit or 12), 30))},
    )
    return [dict(row) for row in result.mappings().all()]


async def _get_inventory_item_for_material_cart(
    db: AsyncSession,
    *,
    company_id: UUID,
    item_id: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        text("""
            SELECT id, company_id, name_reference, item_size, sku, name, reference, current_stock, status
            FROM inventory_items
            WHERE company_id = :company_id
              AND id = :item_id
              AND COALESCE(status, 'active') = 'active'
              AND COALESCE(current_stock, 0) > 0
            LIMIT 1
        """),
        {"company_id": str(company_id), "item_id": str(item_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


def _material_inventory_keyboard(items: list[dict[str, Any]], language: str) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    for item in items:
        rows.append([{
            "text": _inventory_item_label(item)[:60],
            "callback_data": f"clx:mat:item:{item.get('id')}",
        }])
    rows.append([{"text": _txt(language, "btn_cart_cancel"), "callback_data": "clx:mat:cancel"}])
    return {"inline_keyboard": rows}


def _material_cart_keyboard(language: str, has_items: bool = True) -> dict[str, Any]:
    rows = [[{"text": _txt(language, "btn_cart_add"), "callback_data": "clx:mat:add"}]]
    if has_items:
        rows.append([{"text": _txt(language, "btn_cart_confirm"), "callback_data": "clx:mat:confirm"}])
    rows.append([{"text": _txt(language, "btn_cart_cancel"), "callback_data": "clx:mat:cancel"}])
    return {"inline_keyboard": rows}


def _pending_payload(pending: dict[str, Any] | None) -> dict[str, Any]:
    if not pending:
        return {}
    payload = pending.get("payload_json") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    return dict(payload or {})


def _material_cart_summary(language: str, cart: list[dict[str, Any]]) -> str:
    if not cart:
        return _txt(language, "material_cart_empty")
    lines = [_txt(language, "material_cart_title")]
    for index, item in enumerate(cart, start=1):
        lines.append(f"{index}. {item.get('label') or 'Material'} x {_format_material_decimal(item.get('quantity'))}")
    return "\n".join(lines)


async def _set_pending_material_payload(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
    telegram_username: str | None,
    employee_id: UUID,
    payload: dict[str, Any],
) -> None:
    await ensure_bot_storage(db)
    await db.execute(
        text("""
            INSERT INTO company_telegram_pending_actions (
                company_id,
                telegram_user_id,
                telegram_username,
                employee_id,
                action,
                payload_json,
                expires_at,
                updated_at
            )
            VALUES (
                :company_id,
                :telegram_user_id,
                :telegram_username,
                :employee_id,
                'material_request',
                CAST(:payload_json AS jsonb),
                now() + interval '45 minutes',
                now()
            )
            ON CONFLICT (company_id, telegram_user_id, action)
            DO UPDATE SET
                telegram_username = EXCLUDED.telegram_username,
                employee_id = EXCLUDED.employee_id,
                payload_json = EXCLUDED.payload_json,
                expires_at = EXCLUDED.expires_at,
                updated_at = now()
        """),
        {
            "company_id": str(company_id),
            "telegram_user_id": str(telegram_user_id),
            "telegram_username": telegram_username,
            "employee_id": str(employee_id),
            "payload_json": json.dumps(payload),
        },
    )


async def _begin_material_cart_flow(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
    telegram_username: str | None,
    employee_id: UUID,
    chat_id: str | None,
    language: str,
) -> list[dict[str, Any]]:
    items = await _list_inventory_items_for_material_cart(db, company_id=company_id)
    await _set_pending_material_payload(
        db,
        company_id=company_id,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        employee_id=employee_id,
        payload={
            "chat_id": chat_id,
            "language": _lang(language),
            "step": "select_item",
            "cart": [],
        },
    )
    return items


async def _create_material_cart_order_records(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    employee: Employee,
    update: dict[str, Any],
    message: dict[str, Any],
    cart: list[dict[str, Any]],
    language: str,
) -> str:
    await _ensure_material_requests_storage(db)
    if not cart:
        raise HTTPException(status_code=422, detail="Carrito vacío.")

    update_id = str(update.get("update_id") or "")
    message_id = str(message.get("message_id") or "")
    callback = update.get("callback_query") if isinstance(update.get("callback_query"), dict) else None
    if callback and not message_id:
        message_id = str((callback.get("message") or {}).get("message_id") or "")
    source_ref = f"telegram:{update_id}:{message_id}:material_cart_confirm"

    duplicate = await db.execute(
        select(WorkforceAttendanceEvent).where(
            WorkforceAttendanceEvent.company_id == employee.company_id,
            WorkforceAttendanceEvent.source_ref == source_ref,
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        return "duplicado"

    validated: list[dict[str, Any]] = []
    for item in cart:
        item_id = str(item.get("inventory_item_id") or "")
        db_item = await _get_inventory_item_for_material_cart(db, company_id=employee.company_id, item_id=item_id)
        if not db_item:
            raise HTTPException(status_code=409, detail="Uno de los materiales ya no está disponible.")
        qty = Decimal(str(item.get("quantity") or "0")).quantize(Decimal("0.01"))
        stock = Decimal(str(db_item.get("current_stock") or "0")).quantize(Decimal("0.01"))
        if qty <= 0:
            raise HTTPException(status_code=422, detail="Cantidad inválida en carrito.")
        if stock < qty:
            raise HTTPException(status_code=409, detail=f"Stock insuficiente para {_inventory_item_label(db_item)}. Disponible: {_format_material_decimal(stock)}.")
        validated.append({"item": db_item, "quantity": qty})

    order_number = await _generate_material_order_number(db, employee.company_id)
    detail = _material_cart_summary(language, [
        {"label": _inventory_item_label(v["item"]), "quantity": v["quantity"]} for v in validated
    ])

    event = WorkforceAttendanceEvent(
        company_id=employee.company_id,
        employee_id=employee.id,
        event_type="material_request",
        event_label="Solicitud de material",
        employee_name=employee.full_name,
        employee_role=employee.role,
        status_after="requested",
        source="telegram",
        source_channel="telegram",
        source_ref=source_ref,
        bot_instance_id=bot.id,
        module_code="materials",
        detail=detail,
        notes=detail,
        payload_json={
            "language": _lang(language),
            "order_number": order_number,
            "cart": [
                {
                    "inventory_item_id": str(v["item"].get("id")),
                    "label": _inventory_item_label(v["item"]),
                    "quantity": str(v["quantity"]),
                }
                for v in validated
            ],
            "telegram_update_id": update.get("update_id"),
            "telegram_message_id": message.get("message_id"),
            "telegram_user_id": (message.get("from") or {}).get("id") or ((callback or {}).get("from") or {}).get("id"),
            "telegram_username": (message.get("from") or {}).get("username") or ((callback or {}).get("from") or {}).get("username"),
            "chat_id": (message.get("chat") or {}).get("id"),
        },
        metadata_json={
            "source": "telegram_listener",
            "bot_instance_id": str(bot.id),
            "bot_username": bot.bot_username,
            "module_code": "materials",
            "order_number": order_number,
            "cart_items": len(validated),
        },
        occurred_at=utcnow(),
    )
    db.add(event)
    await db.flush()

    for index, value in enumerate(validated, start=1):
        db_item = value["item"]
        qty = value["quantity"]
        await db.execute(
            text("""
                INSERT INTO material_requests (
                    company_id,
                    employee_id,
                    employee_name,
                    employee_role,
                    inventory_item_id,
                    material_name,
                    quantity,
                    unit,
                    notes,
                    status,
                    source_channel,
                    source_ref,
                    attendance_event_id,
                    requested_at,
                    status_updated_at,
                    updated_at,
                    order_number
                )
                VALUES (
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :employee_role,
                    :inventory_item_id,
                    :material_name,
                    :quantity,
                    NULL,
                    :notes,
                    'pending',
                    'telegram',
                    :source_ref,
                    :attendance_event_id,
                    :requested_at,
                    now(),
                    now(),
                    :order_number
                )
                ON CONFLICT (company_id, source_ref)
                WHERE source_ref IS NOT NULL
                DO NOTHING
            """),
            {
                "company_id": str(employee.company_id),
                "employee_id": str(employee.id),
                "employee_name": employee.full_name,
                "employee_role": employee.role,
                "inventory_item_id": str(db_item["id"]),
                "material_name": db_item.get("name_reference") or db_item.get("name") or db_item.get("reference") or db_item.get("sku") or "Material",
                "quantity": qty,
                "notes": f"Orden generada desde carrito Telegram. Línea {index}.",
                "source_ref": f"{source_ref}:line:{index}",
                "attendance_event_id": str(event.id),
                "requested_at": event.occurred_at,
                "order_number": order_number,
            },
        )

    return order_number


async def _material_cart_context(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    telegram_user_id: str,
    username: str | None,
    language: str,
) -> tuple[Employee | None, Company | None, set[str], str | None]:
    employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
    if employee is None:
        return None, None, set(), "not_linked"
    company = await ensure_company_exists(db, bot.company_id)
    enabled_modules = await _enabled_module_codes(db, bot.company_id)
    if "materials" not in enabled_modules or "inventory" not in enabled_modules:
        return employee, company, enabled_modules, "module_inactive"
    if not _employee_can_request_material(employee):
        return employee, company, enabled_modules, "material_not_allowed"
    current = await _get_current_attendance_status(db, employee.company_id, employee.id)
    material_config = TELEGRAM_COMMANDS["/material"]
    transition_ok, _ = _validate_turn_transition(current=current, command_config=material_config, language=language)
    if not transition_ok:
        return employee, company, enabled_modules, "turn_validation_failed"
    return employee, company, enabled_modules, None


async def _process_material_cart_callback(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    token: str,
    update: dict[str, Any],
    message: dict[str, Any],
    telegram_user_id: str,
    username: str | None,
    chat_id: str | None,
    text_value: str,
    language: str,
    send_replies: bool,
) -> TelegramBotPollItem:
    update_id = update.get("update_id")

    employee, company, _, error = await _material_cart_context(
        db,
        bot=bot,
        telegram_user_id=telegram_user_id,
        username=username,
        language=language,
    )

    # IMPORTANTE:
    # AsyncSession expira objetos ORM al hacer commit/rollback. Si luego se accede
    # a employee.full_name, company.name o bot.company_id se dispara MissingGreenlet.
    # Por eso cacheamos primitivos antes de cualquier commit.
    company_id_value = bot.company_id
    employee_id_value = employee.id if employee is not None else None
    employee_name_value = employee.full_name if employee is not None else None

    if error:
        if send_replies:
            if error == "not_linked":
                await _send_telegram_message(
                    token,
                    chat_id,
                    _txt(language, "not_linked", telegram_user_id=telegram_user_id),
                    reply_markup=_language_keyboard(),
                )
            elif error == "module_inactive":
                await _send_telegram_message(token, chat_id, _txt(language, "module_inactive"))
            elif error == "turn_validation_failed":
                await _send_telegram_message(token, chat_id, _txt(language, "must_start_shift"))
            else:
                await _send_telegram_message(token, chat_id, "No tienes permisos para solicitar material.")

            if employee is not None and company is not None:
                await _send_dynamic_menu(
                    db,
                    token=token,
                    chat_id=chat_id,
                    company=company,
                    employee=employee,
                    language=language,
                )

        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action=error,
            message=error,
            employee_id=employee_id_value,
            employee_name=employee_name_value,
        )

    assert employee is not None and company is not None

    action = text_value.removeprefix("clx:mat:").strip()
    pending = await _get_pending_material_request(
        db,
        company_id=company_id_value,
        telegram_user_id=telegram_user_id,
    )
    payload = _pending_payload(pending)
    cart = list(payload.get("cart") or [])

    if action == "cancel":
        await _clear_pending_material_request(
            db,
            company_id=company_id_value,
            telegram_user_id=telegram_user_id,
        )
        await db.commit()

        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "material_cart_cancelled"))
            fresh_employee = await _find_employee_by_telegram(db, company_id_value, telegram_user_id, username)
            fresh_company = await ensure_company_exists(db, company_id_value)
            if fresh_employee is not None and fresh_company is not None:
                await _send_dynamic_menu(
                    db,
                    token=token,
                    chat_id=chat_id,
                    company=fresh_company,
                    employee=fresh_employee,
                    language=language,
                )

        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="material_cart_cancelled",
            message="Carrito cancelado.",
            employee_id=employee_id_value,
            employee_name=employee_name_value,
        )

    if action == "add" or pending is None:
        items = await _begin_material_cart_flow(
            db,
            company_id=company_id_value,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
            employee_id=employee_id_value,
            chat_id=chat_id,
            language=language,
        )
        await db.commit()

        if send_replies:
            if items:
                await _send_telegram_message(
                    token,
                    chat_id,
                    _txt(language, "material_select_prompt"),
                    reply_markup=_material_inventory_keyboard(items, language),
                )
            else:
                await _send_telegram_message(token, chat_id, _txt(language, "material_inventory_empty"))
                fresh_employee = await _find_employee_by_telegram(db, company_id_value, telegram_user_id, username)
                fresh_company = await ensure_company_exists(db, company_id_value)
                if fresh_employee is not None and fresh_company is not None:
                    await _send_dynamic_menu(
                        db,
                        token=token,
                        chat_id=chat_id,
                        company=fresh_company,
                        employee=fresh_employee,
                        language=language,
                    )

        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="material_select_item",
            message="Lista de inventario enviada.",
            employee_id=employee_id_value,
            employee_name=employee_name_value,
        )

    if action.startswith("item:"):
        item_id = action.removeprefix("item:").strip()
        item = await _get_inventory_item_for_material_cart(
            db,
            company_id=company_id_value,
            item_id=item_id,
        )

        if not item:
            items = await _list_inventory_items_for_material_cart(db, company_id=company_id_value)
            if send_replies:
                await _send_telegram_message(
                    token,
                    chat_id,
                    _txt(language, "material_inventory_empty") if not items else _txt(language, "material_select_prompt"),
                    reply_markup=_material_inventory_keyboard(items, language) if items else None,
                )
            return TelegramBotPollItem(
                update_id=update_id,
                ok=False,
                action="material_item_unavailable",
                message="Material no disponible.",
                employee_id=employee_id_value,
                employee_name=employee_name_value,
            )

        item_label = _inventory_item_label(item)
        stock_value = str(item.get("current_stock") or "0")

        payload.update({
            "step": "waiting_quantity",
            "selected_item": {
                "inventory_item_id": str(item["id"]),
                "label": item_label,
                "stock": stock_value,
            },
            "cart": cart,
            "chat_id": chat_id,
            "language": _lang(language),
        })

        await _set_pending_material_payload(
            db,
            company_id=company_id_value,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
            employee_id=employee_id_value,
            payload=payload,
        )
        await db.commit()

        if send_replies:
            await _send_telegram_message(
                token,
                chat_id,
                _txt(language, "material_quantity_prompt", item_label=item_label, stock=_format_material_decimal(stock_value)),
            )

        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="material_quantity_required",
            message="Esperando cantidad.",
            employee_id=employee_id_value,
            employee_name=employee_name_value,
        )

    if action == "confirm":
        if not cart:
            if send_replies:
                await _send_telegram_message(
                    token,
                    chat_id,
                    _txt(language, "material_cart_empty"),
                    reply_markup=_material_cart_keyboard(language, has_items=False),
                )
            return TelegramBotPollItem(
                update_id=update_id,
                ok=False,
                action="material_cart_empty",
                message="Carrito vacío.",
                employee_id=employee_id_value,
                employee_name=employee_name_value,
            )

        try:
            order_number = await _create_material_cart_order_records(
                db,
                bot=bot,
                employee=employee,
                update=update,
                message=message,
                cart=cart,
                language=language,
            )
        except HTTPException as exc:
            await db.rollback()
            if send_replies:
                await _send_telegram_message(token, chat_id, str(exc.detail))
                fresh_employee = await _find_employee_by_telegram(db, company_id_value, telegram_user_id, username)
                fresh_company = await ensure_company_exists(db, company_id_value)
                if fresh_employee is not None and fresh_company is not None:
                    await _send_dynamic_menu(
                        db,
                        token=token,
                        chat_id=chat_id,
                        company=fresh_company,
                        employee=fresh_employee,
                        language=language,
                    )
            return TelegramBotPollItem(
                update_id=update_id,
                ok=False,
                action="material_cart_confirm_failed",
                message=str(exc.detail),
                employee_id=employee_id_value,
                employee_name=employee_name_value,
            )

        await _clear_pending_material_request(
            db,
            company_id=company_id_value,
            telegram_user_id=telegram_user_id,
        )
        await db.commit()

        if send_replies:
            await _send_telegram_message(
                token,
                chat_id,
                _txt(language, "material_cart_confirmed", order_number=order_number),
            )
            fresh_employee = await _find_employee_by_telegram(db, company_id_value, telegram_user_id, username)
            fresh_company = await ensure_company_exists(db, company_id_value)
            if fresh_employee is not None and fresh_company is not None:
                await _send_dynamic_menu(
                    db,
                    token=token,
                    chat_id=chat_id,
                    company=fresh_company,
                    employee=fresh_employee,
                    language=language,
                )

        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="material_cart_confirmed",
            message=f"Orden {order_number}",
            employee_id=employee_id_value,
            employee_name=employee_name_value,
            event_created=True,
        )

    if send_replies:
        await _send_telegram_message(
            token,
            chat_id,
            _material_cart_summary(language, cart),
            reply_markup=_material_cart_keyboard(language, has_items=bool(cart)),
        )

    return TelegramBotPollItem(
        update_id=update_id,
        ok=True,
        action="material_cart_review",
        message="Carrito mostrado.",
        employee_id=employee_id_value,
        employee_name=employee_name_value,
    )

async def _process_material_cart_text(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    token: str,
    update: dict[str, Any],
    message: dict[str, Any],
    telegram_user_id: str,
    username: str | None,
    chat_id: str | None,
    text_value: str,
    language: str,
    send_replies: bool,
) -> TelegramBotPollItem:
    update_id = update.get("update_id")

    employee, company, _, error = await _material_cart_context(
        db,
        bot=bot,
        telegram_user_id=telegram_user_id,
        username=username,
        language=language,
    )

    company_id_value = bot.company_id
    employee_id_value = employee.id if employee is not None else None
    employee_name_value = employee.full_name if employee is not None else None

    if error:
        await _clear_pending_material_request(
            db,
            company_id=company_id_value,
            telegram_user_id=telegram_user_id,
        )
        await db.commit()

        if send_replies:
            if error == "not_linked":
                await _send_telegram_message(
                    token,
                    chat_id,
                    _txt(language, "not_linked", telegram_user_id=telegram_user_id),
                    reply_markup=_language_keyboard(),
                )
            else:
                await _send_telegram_message(token, chat_id, "No tienes permisos o el módulo no está activo.")

            if employee is not None and company is not None:
                fresh_employee = await _find_employee_by_telegram(db, company_id_value, telegram_user_id, username)
                fresh_company = await ensure_company_exists(db, company_id_value)
                if fresh_employee is not None and fresh_company is not None:
                    await _send_dynamic_menu(
                        db,
                        token=token,
                        chat_id=chat_id,
                        company=fresh_company,
                        employee=fresh_employee,
                        language=language,
                    )

        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action=error,
            message=error,
            employee_id=employee_id_value,
            employee_name=employee_name_value,
        )

    assert employee is not None and company is not None

    pending = await _get_pending_material_request(
        db,
        company_id=company_id_value,
        telegram_user_id=telegram_user_id,
    )
    payload = _pending_payload(pending)
    cart = list(payload.get("cart") or [])
    step = str(payload.get("step") or "select_item")
    selected = payload.get("selected_item") or {}

    if step != "waiting_quantity" or not selected:
        items = await _list_inventory_items_for_material_cart(db, company_id=company_id_value)
        if send_replies:
            await _send_telegram_message(
                token,
                chat_id,
                _txt(language, "material_select_prompt") if items else _txt(language, "material_inventory_empty"),
                reply_markup=_material_inventory_keyboard(items, language) if items else None,
            )
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="material_select_item",
            message="Lista de inventario enviada.",
            employee_id=employee_id_value,
            employee_name=employee_name_value,
        )

    amount_match = re.search(r"\d+(?:[.,]\d+)?", text_value or "")
    if not amount_match:
        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "material_quantity_invalid"))
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="material_quantity_invalid",
            message="Cantidad inválida.",
            employee_id=employee_id_value,
            employee_name=employee_name_value,
        )

    quantity = Decimal(amount_match.group(0).replace(",", ".")).quantize(Decimal("0.01"))
    stock = Decimal(str(selected.get("stock") or "0")).quantize(Decimal("0.01"))

    if quantity <= 0:
        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "material_quantity_invalid"))
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="material_quantity_invalid",
            message="Cantidad inválida.",
            employee_id=employee_id_value,
            employee_name=employee_name_value,
        )

    if stock < quantity:
        if send_replies:
            await _send_telegram_message(
                token,
                chat_id,
                _txt(language, "material_quantity_exceeds", stock=_format_material_decimal(stock)),
            )
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="material_quantity_exceeds",
            message="Stock insuficiente.",
            employee_id=employee_id_value,
            employee_name=employee_name_value,
        )

    selected_id = str(selected.get("inventory_item_id"))
    merged = False
    for existing in cart:
        if str(existing.get("inventory_item_id")) == selected_id:
            existing["quantity"] = str(
                (Decimal(str(existing.get("quantity") or "0")) + quantity).quantize(Decimal("0.01"))
            )
            merged = True
            break

    if not merged:
        cart.append({
            "inventory_item_id": selected_id,
            "label": selected.get("label") or "Material",
            "quantity": str(quantity),
        })

    payload.update({
        "step": "cart_review",
        "selected_item": None,
        "cart": cart,
        "chat_id": chat_id,
        "language": _lang(language),
    })

    await _set_pending_material_payload(
        db,
        company_id=company_id_value,
        telegram_user_id=telegram_user_id,
        telegram_username=username,
        employee_id=employee_id_value,
        payload=payload,
    )
    await db.commit()

    if send_replies:
        await _send_telegram_message(
            token,
            chat_id,
            _txt(language, "material_cart_added") + "\n\n" + _material_cart_summary(language, cart),
            reply_markup=_material_cart_keyboard(language, has_items=True),
        )

    return TelegramBotPollItem(
        update_id=update_id,
        ok=True,
        action="material_cart_added",
        message="Material agregado al carrito.",
        employee_id=employee_id_value,
        employee_name=employee_name_value,
    )

async def _find_inventory_item_for_material_request(
    db: AsyncSession,
    *,
    company_id: UUID,
    material_name: str,
) -> dict[str, Any] | None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL,
            name_reference text NULL,
            sku text NULL,
            name text NULL,
            reference text NULL,
            current_stock numeric(14,2) DEFAULT 0,
            status varchar(40) DEFAULT 'active',
            created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now()
        );
    """))
    name = (material_name or "").strip().lower()
    if not name:
        return None
    result = await db.execute(
        text("""
            SELECT id, company_id, name_reference, sku, name, reference, current_stock, status
            FROM inventory_items
            WHERE company_id = :company_id
              AND COALESCE(status, 'active') = 'active'
              AND (
                lower(COALESCE(name_reference, '')) = :name
                OR lower(COALESCE(sku, '')) = :name
                OR lower(COALESCE(name, '')) = :name
                OR lower(COALESCE(reference, '')) = :name
                OR lower(COALESCE(name_reference, '')) LIKE :name_like
              )
            ORDER BY
              CASE WHEN lower(COALESCE(name_reference, '')) = :name THEN 1 ELSE 2 END,
              created_at DESC
            LIMIT 1
        """),
        {
            "company_id": str(company_id),
            "name": name,
            "name_like": f"%{name}%",
        },
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _generate_material_order_number(db: AsyncSession, company_id: UUID) -> str:
    prefix = f"MAT-{utcnow().strftime('%Y%m%d')}-"
    result = await db.execute(
        text("""
            SELECT COALESCE(MAX(CAST(right(order_number, 6) AS integer)), 0) + 1
            FROM material_requests
            WHERE company_id = :company_id
              AND order_number LIKE :prefix_like
        """),
        {"company_id": str(company_id), "prefix_like": f"{prefix}%"},
    )
    seq = int(result.scalar() or 1)
    return f"{prefix}{seq:06d}"


async def _set_pending_material_request(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
    telegram_username: str | None,
    employee_id: UUID,
    chat_id: str | None,
    language: str,
) -> None:
    await _set_pending_material_payload(
        db,
        company_id=company_id,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        employee_id=employee_id,
        payload={
            "chat_id": chat_id,
            "language": _lang(language),
            "step": "select_item",
            "cart": [],
        },
    )


async def _get_pending_material_request(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
) -> dict[str, Any] | None:
    await ensure_bot_storage(db)
    result = await db.execute(
        text("""
            SELECT id, employee_id, payload_json, expires_at
            FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'material_request'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY updated_at DESC
            LIMIT 1
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _clear_pending_material_request(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
) -> None:
    await db.execute(
        text("""
            DELETE FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'material_request'
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )


async def _create_material_request_record(
    db: AsyncSession,
    *,
    event: WorkforceAttendanceEvent,
    employee: Employee,
    detail: str,
) -> str:
    await _ensure_material_requests_storage(db)
    parsed = _parse_material_request_text(detail)
    material_name = (parsed["material_name"] or "").strip()
    if not material_name:
        return "📦 Falta el nombre o referencia del material."

    item = await _find_inventory_item_for_material_request(
        db,
        company_id=employee.company_id,
        material_name=material_name,
    )
    if not item:
        return "📦 Material no disponible en inventario activo. Solicita una referencia existente."

    requested_qty = Decimal(str(parsed["quantity"] or "1")).quantize(Decimal("0.01"))
    current_stock = Decimal(str(item.get("current_stock") or "0")).quantize(Decimal("0.01"))
    if requested_qty <= 0:
        return "📦 La cantidad debe ser mayor a cero."
    if current_stock < requested_qty:
        return f"📦 Stock insuficiente. Disponible: {current_stock}."

    order_number = await _generate_material_order_number(db, employee.company_id)
    await db.execute(
        text("""
            INSERT INTO material_requests (
                company_id,
                employee_id,
                employee_name,
                employee_role,
                inventory_item_id,
                material_name,
                quantity,
                unit,
                notes,
                status,
                source_channel,
                source_ref,
                attendance_event_id,
                requested_at,
                status_updated_at,
                updated_at,
                order_number
            )
            VALUES (
                :company_id,
                :employee_id,
                :employee_name,
                :employee_role,
                :inventory_item_id,
                :material_name,
                :quantity,
                :unit,
                :notes,
                'pending',
                'telegram',
                :source_ref,
                :attendance_event_id,
                :requested_at,
                now(),
                now(),
                :order_number
            )
            ON CONFLICT (company_id, source_ref)
            WHERE source_ref IS NOT NULL
            DO NOTHING
        """),
        {
            "company_id": str(employee.company_id),
            "employee_id": str(employee.id),
            "employee_name": employee.full_name,
            "employee_role": employee.role,
            "inventory_item_id": str(item["id"]),
            "material_name": item.get("name_reference") or material_name,
            "quantity": requested_qty,
            "unit": parsed["unit"],
            "notes": parsed["notes"],
            "source_ref": event.source_ref,
            "attendance_event_id": str(event.id),
            "requested_at": event.occurred_at,
            "order_number": order_number,
        },
    )
    return f"📦 Solicitud registrada. Orden: {order_number}."


async def _create_gps_location_event(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    employee: Employee,
    update: dict[str, Any],
    message: dict[str, Any],
    latitude: float,
    longitude: float,
    language: str,
    source_ref_suffix: str = "gps_location",
) -> WorkforceAttendanceEvent:
    update_id = str(update.get("update_id") or "")
    message_id = str(message.get("message_id") or "")
    source_ref = f"telegram:{update_id}:{message_id}:{source_ref_suffix}"
    duplicate_result = await db.execute(
        select(WorkforceAttendanceEvent).where(
            WorkforceAttendanceEvent.company_id == employee.company_id,
            WorkforceAttendanceEvent.source_ref == source_ref,
        )
    )
    existing = duplicate_result.scalar_one_or_none()
    if existing is not None:
        return existing

    location = message.get("location") or {}
    gps_validation = await _validate_gps_location_for_company(
        db,
        company_id=employee.company_id,
        latitude=latitude,
        longitude=longitude,
    )
    event = WorkforceAttendanceEvent(
        company_id=employee.company_id,
        employee_id=employee.id,
        event_type="gps_location",
        event_label="Ubicación GPS",
        employee_name=employee.full_name,
        employee_role=employee.role,
        status_after="registered",
        source="telegram",
        source_channel="telegram",
        source_ref=source_ref,
        bot_instance_id=bot.id,
        module_code="gps",
        detail=f"{latitude},{longitude}",
        notes="Ubicación compartida por Telegram.",
        latitude=Decimal(str(latitude)),
        longitude=Decimal(str(longitude)),
        payload_json={
            "language": _lang(language),
            "telegram_update_id": update.get("update_id"),
            "telegram_message_id": message.get("message_id"),
            "telegram_user_id": (message.get("from") or {}).get("id"),
            "telegram_username": (message.get("from") or {}).get("username"),
            "chat_id": (message.get("chat") or {}).get("id"),
            "latitude": latitude,
            "longitude": longitude,
            "coordinates": f"{latitude},{longitude}",
            "horizontal_accuracy": location.get("horizontal_accuracy"),
            "live_period": location.get("live_period"),
            **gps_validation,
        },
        metadata_json={
            "source": "telegram_listener",
            "bot_instance_id": str(bot.id),
            "bot_username": bot.bot_username,
            "module_code": "gps",
            **gps_validation,
        },
        occurred_at=utcnow(),
    )
    db.add(event)
    await db.flush()
    return event



async def _find_employee_by_telegram(
    db: AsyncSession,
    company_id: UUID,
    telegram_user_id: str,
    username: str | None,
) -> Employee | None:
    if not telegram_user_id and not username:
        return None

    filters = []
    if telegram_user_id:
        filters.append(Employee.telegram_user_id == telegram_user_id)
    if username:
        filters.append(Employee.telegram_username == username)
        filters.append(Employee.telegram_username == f"@{username}")

    result = await db.execute(
        select(Employee)
        .where(Employee.company_id == company_id)
        .where(Employee.status == "active")
        .where(*([filters[0]] if len(filters) == 1 else []))
    )
    if len(filters) == 1:
        return result.scalar_one_or_none()

    # SQLAlchemy or_ se importa tarde para no tocar imports existentes si no hay username.
    from sqlalchemy import or_

    result = await db.execute(
        select(Employee)
        .where(Employee.company_id == company_id)
        .where(Employee.status == "active")
        .where(or_(*filters))
        .order_by(Employee.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_current_attendance_status(
    db: AsyncSession,
    company_id: UUID,
    employee_id: UUID,
) -> WorkforceAttendanceStatus | None:
    result = await db.execute(
        select(WorkforceAttendanceStatus).where(
            WorkforceAttendanceStatus.company_id == company_id,
            WorkforceAttendanceStatus.employee_id == employee_id,
        )
    )
    return result.scalar_one_or_none()



def _format_minutes(total_minutes: int) -> str:
    total_minutes = max(0, int(total_minutes or 0))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours}h {minutes:02d}m"


def _format_money(value: Decimal | float | int | None) -> str:
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        amount = Decimal("0.00")
    return f"{amount:,.2f}"


async def _calculate_shift_minutes(
    db: AsyncSession,
    *,
    employee: Employee,
    started_at: datetime,
    ended_at: datetime,
) -> tuple[int, int, int]:
    gross_minutes = max(0, int((ended_at - started_at).total_seconds() // 60))

    result = await db.execute(
        select(WorkforceAttendanceEvent)
        .where(
            WorkforceAttendanceEvent.company_id == employee.company_id,
            WorkforceAttendanceEvent.employee_id == employee.id,
            WorkforceAttendanceEvent.occurred_at >= started_at,
            WorkforceAttendanceEvent.occurred_at <= ended_at,
            WorkforceAttendanceEvent.event_type.in_(["break_start", "break_end"]),
        )
        .order_by(WorkforceAttendanceEvent.occurred_at.asc())
    )
    events = list(result.scalars().all())

    break_minutes = 0
    break_started_at: datetime | None = None
    for event in events:
        if event.event_type == "break_start" and break_started_at is None:
            break_started_at = event.occurred_at
        elif event.event_type == "break_end" and break_started_at is not None:
            break_minutes += max(0, int((event.occurred_at - break_started_at).total_seconds() // 60))
            break_started_at = None

    if break_started_at is not None:
        break_minutes += max(0, int((ended_at - break_started_at).total_seconds() // 60))

    payable_minutes = max(0, gross_minutes - break_minutes)
    return gross_minutes, break_minutes, payable_minutes


def _money_decimal(value: Decimal | float | int | str | None) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


async def _shift_end_projection(
    db: AsyncSession,
    *,
    employee: Employee,
    started_at: datetime | None,
    ended_at: datetime,
) -> dict[str, Any] | None:
    """
    CLONEXA 011A3-R4:
    Calcula la proyección de la jornada cerrada y deja datos estructurados para Nómina.
    Los descuentos son del corte/periodo, no descuento por cada jornada.
    """
    if started_at is None:
        return None

    gross_minutes, break_minutes, payable_minutes = await _calculate_shift_minutes(
        db,
        employee=employee,
        started_at=started_at,
        ended_at=ended_at,
    )

    regular_minutes = min(payable_minutes, 8 * 60)
    extra_minutes = max(0, payable_minutes - regular_minutes)

    regular_rate = _money_decimal(employee.hourly_rate_regular)
    extra_rate = _money_decimal(employee.hourly_rate_extra)
    deduction_1 = _money_decimal(getattr(employee, "deduction_1", 0))
    deduction_2 = _money_decimal(getattr(employee, "deduction_2", 0))

    regular_amount = _money_decimal(Decimal(regular_minutes) / Decimal(60) * regular_rate)
    extra_amount = _money_decimal(Decimal(extra_minutes) / Decimal(60) * extra_rate)
    projected_pay = _money_decimal(regular_amount + extra_amount)
    discount_total = _money_decimal(deduction_1 + deduction_2)
    estimated_total = _money_decimal(max(Decimal("0.00"), projected_pay - discount_total))

    return {
        "gross_minutes": gross_minutes,
        "break_minutes": break_minutes,
        "payable_minutes": payable_minutes,
        "regular_minutes": regular_minutes,
        "extra_minutes": extra_minutes,
        "hourly_rate_regular": str(regular_rate),
        "hourly_rate_extra": str(extra_rate),
        "regular_amount": str(regular_amount),
        "extra_amount": str(extra_amount),
        "projected_pay": str(projected_pay),
        "deduction_1": str(deduction_1),
        "deduction_2": str(deduction_2),
        "discount_total": str(discount_total),
        "estimated_total": str(estimated_total),
        "discount_scope": "payroll_period",
        "source": "workforce_personal",
    }


def _current_payroll_cutoff_start(moment: datetime) -> datetime:
    """
    Corte estándar CLONEXA:
    - día 1 al 15
    - día 16 al último día del mes

    Se usa para que el bot muestre acumulado del corte, no liquidación aislada por jornada.
    """
    if moment.day <= 15:
        return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return moment.replace(day=16, hour=0, minute=0, second=0, microsecond=0)


def _projection_from_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    projection = payload.get("payroll_projection") or payload.get("payroll")
    if not isinstance(projection, dict):
        return None
    try:
        return {
            "regular_minutes": int(Decimal(str(projection.get("regular_minutes") or 0))),
            "extra_minutes": int(Decimal(str(projection.get("extra_minutes") or 0))),
            "projected_pay": _money_decimal(projection.get("projected_pay") or 0),
        }
    except Exception:
        return None


async def _payroll_cutoff_projection(
    db: AsyncSession,
    *,
    employee: Employee,
    ended_at: datetime,
    fallback_projection: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Suma todos los check_out del empleado dentro del corte actual.
    El descuento se aplica una sola vez al corte.
    """
    period_start = _current_payroll_cutoff_start(ended_at)

    result = await db.execute(
        select(WorkforceAttendanceEvent)
        .where(
            WorkforceAttendanceEvent.company_id == employee.company_id,
            WorkforceAttendanceEvent.employee_id == employee.id,
            WorkforceAttendanceEvent.event_type == "check_out",
            WorkforceAttendanceEvent.occurred_at >= period_start,
            WorkforceAttendanceEvent.occurred_at <= ended_at,
        )
        .order_by(WorkforceAttendanceEvent.occurred_at.asc())
    )
    events = list(result.scalars().all())

    regular_minutes = 0
    extra_minutes = 0
    projected_pay = Decimal("0.00")

    for event in events:
        projection = _projection_from_payload(event.payload_json)
        if not projection:
            continue
        regular_minutes += max(0, int(projection["regular_minutes"]))
        extra_minutes += max(0, int(projection["extra_minutes"]))
        projected_pay += _money_decimal(projection["projected_pay"])

    # Fallback: si por cualquier razón el evento actual todavía no quedó visible en la sesión,
    # respondemos al menos con la jornada recién cerrada.
    if not events and fallback_projection:
        regular_minutes = max(0, int(fallback_projection.get("regular_minutes") or 0))
        extra_minutes = max(0, int(fallback_projection.get("extra_minutes") or 0))
        projected_pay = _money_decimal(fallback_projection.get("projected_pay") or 0)

    if regular_minutes == 0 and extra_minutes == 0 and projected_pay == Decimal("0.00"):
        return None

    deduction_1 = _money_decimal(getattr(employee, "deduction_1", 0))
    deduction_2 = _money_decimal(getattr(employee, "deduction_2", 0))
    discount_total = _money_decimal(deduction_1 + deduction_2)
    estimated_total = _money_decimal(max(Decimal("0.00"), projected_pay - discount_total))

    return {
        "period_start": period_start.isoformat(),
        "period_end": ended_at.isoformat(),
        "regular_minutes": regular_minutes,
        "extra_minutes": extra_minutes,
        "projected_pay": str(_money_decimal(projected_pay)),
        "deduction_1": str(deduction_1),
        "deduction_2": str(deduction_2),
        "discount_total": str(discount_total),
        "estimated_total": str(estimated_total),
        "discount_scope": "payroll_period",
        "source": "workforce_personal_cutoff",
    }


async def _shift_end_summary_message(
    db: AsyncSession,
    *,
    employee: Employee,
    started_at: datetime | None,
    ended_at: datetime,
    language: str,
) -> str:
    base = _txt(language, "shift_ended")
    shift_projection = await _shift_end_projection(
        db,
        employee=employee,
        started_at=started_at,
        ended_at=ended_at,
    )
    if shift_projection is None:
        return base

    cutoff_projection = await _payroll_cutoff_projection(
        db,
        employee=employee,
        ended_at=ended_at,
        fallback_projection=shift_projection,
    ) or shift_projection

    summary = _txt(
        language,
        "shift_summary",
        employee_name=(employee.full_name or "").strip() or "colaborador",
        regular=_format_minutes(int(cutoff_projection["regular_minutes"])),
        extra=_format_minutes(int(cutoff_projection["extra_minutes"])),
        projected_pay=_format_money(Decimal(str(cutoff_projection["projected_pay"]))),
        discount=_format_money(Decimal(str(cutoff_projection["discount_total"]))),
        estimated_total=_format_money(Decimal(str(cutoff_projection["estimated_total"]))),
    )
    return f"{base}\n\n{summary}"


async def _upsert_attendance_status(
    db: AsyncSession,
    employee: Employee,
    event_type: str,
    status_after: str,
    occurred_at: datetime,
) -> None:
    status_events = {"check_in", "break_start", "break_end", "check_out"}
    if event_type not in status_events:
        return

    current = await _get_current_attendance_status(db, employee.company_id, employee.id)
    if current is None:
        current = WorkforceAttendanceStatus(
            company_id=employee.company_id,
            employee_id=employee.id,
            status=status_after,
            last_event_type=event_type,
            last_event_at=occurred_at,
            updated_at=occurred_at,
        )
        db.add(current)
        await db.flush()
    else:
        current.status = status_after
        current.last_event_type = event_type
        current.last_event_at = occurred_at
        current.updated_at = occurred_at

    if event_type == "check_in":
        current.check_in_at = occurred_at
        current.break_started_at = None
        current.check_out_at = None
    elif event_type == "break_start":
        current.break_started_at = occurred_at
    elif event_type == "break_end":
        current.break_started_at = None
    elif event_type == "check_out":
        current.check_out_at = occurred_at
        if current.check_in_at:
            gross_minutes, break_minutes, payable_minutes = await _calculate_shift_minutes(
                db,
                employee=employee,
                started_at=current.check_in_at,
                ended_at=occurred_at,
            )
            current.worked_minutes = payable_minutes
            current.break_minutes = break_minutes
        current.break_started_at = None


async def _create_bot_attendance_event(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    employee: Employee,
    update: dict[str, Any],
    message: dict[str, Any],
    command: str,
    args: str,
    command_config: dict[str, Any],
    language: str = DEFAULT_LANGUAGE,
) -> tuple[bool, str]:
    update_id = str(update.get("update_id") or "")
    message_id = str(message.get("message_id") or "")
    callback = update.get("callback_query") if isinstance(update.get("callback_query"), dict) else None
    if callback and not message_id:
        message_id = str((callback.get("message") or {}).get("message_id") or "")
    occurred_at = utcnow()
    source_ref = f"telegram:{update_id}:{message_id}:{command}"

    duplicate_result = await db.execute(
        select(WorkforceAttendanceEvent).where(
            WorkforceAttendanceEvent.company_id == employee.company_id,
            WorkforceAttendanceEvent.source_ref == source_ref,
        )
    )
    if duplicate_result.scalar_one_or_none() is not None:
        return False, "Evento duplicado ignorado."

    event_type = command_config["event_type"]
    event_label = command_config["event_label"]
    module_code = command_config.get("module_code") or "workforce"
    status_after = command_config.get("status_after") or "registered"
    text_value = (message.get("text") or "").strip()
    if callback:
        text_value = str(callback.get("data") or text_value or "").strip()
    detail = args or text_value

    if command_config.get("requires_text") and not args:
        return False, _txt(language, "need_detail", command=command)

    event = WorkforceAttendanceEvent(
        company_id=employee.company_id,
        employee_id=employee.id,
        event_type=event_type,
        event_label=event_label,
        employee_name=employee.full_name,
        employee_role=employee.role,
        status_after=status_after,
        source="telegram",
        source_channel="telegram",
        source_ref=source_ref,
        bot_instance_id=bot.id,
        module_code=module_code,
        detail=detail,
        notes=detail,
        payload_json={
            "text": text_value,
            "command": command,
            "args": args,
            "language": _lang(language),
            "payroll_affects": bool(command_config.get("payroll_affects")),
            "break_is_non_payable": event_type in {"break_start", "break_end"},
            "telegram_update_id": update.get("update_id"),
            "telegram_message_id": message.get("message_id"),
            "telegram_user_id": (message.get("from") or {}).get("id") or ((callback or {}).get("from") or {}).get("id"),
            "telegram_username": (message.get("from") or {}).get("username") or ((callback or {}).get("from") or {}).get("username"),
            "chat_id": (message.get("chat") or {}).get("id"),
        },
        metadata_json={
            "source": "telegram_listener",
            "bot_instance_id": str(bot.id),
            "bot_username": bot.bot_username,
            "turn_action": command_config.get("turn_action"),
            "module_code": module_code,
        },
        occurred_at=occurred_at,
    )
    db.add(event)
    await db.flush()

    material_reply: str | None = None
    if event_type == "material_request":
        material_reply = await _create_material_request_record(
            db,
            event=event,
            employee=employee,
            detail=detail,
        )

    started_at: datetime | None = None
    if event_type == "check_out":
        current_before_close = await _get_current_attendance_status(db, employee.company_id, employee.id)
        started_at = current_before_close.check_in_at if current_before_close else None

    await _upsert_attendance_status(db, employee, event_type, status_after, occurred_at)

    if event_type == "check_out":
        projection = await _shift_end_projection(
            db,
            employee=employee,
            started_at=started_at,
            ended_at=occurred_at,
        )
        if projection is not None:
            payload = dict(event.payload_json or {})
            payload["payroll_projection"] = projection
            cutoff_projection = await _payroll_cutoff_projection(
                db,
                employee=employee,
                ended_at=occurred_at,
                fallback_projection=projection,
            )
            if cutoff_projection is not None:
                payload["payroll_cutoff_projection"] = cutoff_projection
            payload["payroll_ready"] = True
            payload["payroll_note"] = "Descuentos informativos por corte; no se aplican como descuento por jornada."
            event.payload_json = payload
            metadata = dict(event.metadata_json or {})
            metadata["payroll_ready"] = True
            metadata["discount_scope"] = "payroll_period"
            if cutoff_projection is not None:
                metadata["payroll_cutoff_ready"] = True
            event.metadata_json = metadata
            await db.flush()

        await _close_gps_tracking_session(
            db,
            company_id=employee.company_id,
            employee=employee,
            ended_at=occurred_at,
            reason="check_out",
        )

        return True, await _shift_end_summary_message(
            db,
            employee=employee,
            started_at=started_at,
            ended_at=occurred_at,
            language=language,
        )

    return True, material_reply or _txt(language, command_config.get("reply_key") or "status_checked")



async def _process_telegram_location(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    token: str,
    update: dict[str, Any],
    message: dict[str, Any],
    telegram_user_id: str | None,
    username: str | None,
    chat_id: str | None,
    send_replies: bool,
) -> TelegramBotPollItem:
    update_id = update.get("update_id")
    location = message.get("location") or {}
    is_live_location = _is_live_location_message(message)
    if not telegram_user_id:
        return TelegramBotPollItem(update_id=update_id, ok=False, action="gps_location", message="Telegram user missing.")

    language = await _get_user_language(db, bot.company_id, telegram_user_id)
    employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
    if employee is None:
        reply = _txt(language, "not_linked", telegram_user_id=telegram_user_id)
        if send_replies:
            await _send_telegram_message(token, chat_id, reply, reply_markup=_language_keyboard())
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="not_linked",
            message="Empleado no vinculado.",
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    company = await ensure_company_exists(db, bot.company_id)
    enabled_modules = await _enabled_module_codes(db, bot.company_id)
    if "gps" not in enabled_modules:
        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "module_inactive"), reply_markup=_remove_reply_keyboard())
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="module_inactive",
            message="GPS inactive.",
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    try:
        latitude = float(location.get("latitude"))
        longitude = float(location.get("longitude"))
    except Exception:
        return TelegramBotPollItem(update_id=update_id, ok=False, action="gps_location_invalid", message="Ubicación inválida.")

    pending = await _get_pending_gps_checkin(db, company_id=bot.company_id, telegram_user_id=telegram_user_id)
    current = await _get_current_attendance_status(db, employee.company_id, employee.id)

    if pending is not None:
        pending_live_period = location.get("live_period")
        if not pending_live_period:
            if send_replies:
                await _send_telegram_message(
                    token,
                    chat_id,
                    _txt(language, "gps_live_required_strict"),
                    reply_markup=_remove_reply_keyboard(),
                )
            return TelegramBotPollItem(
                update_id=update_id,
                ok=False,
                action="gps_live_location_required_for_check_in",
                message="Ubicacion en vivo requerida para iniciar turno.",
                employee_id=employee.id,
                employee_name=employee.full_name,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        command_config = TELEGRAM_COMMANDS["/entrada"]
        transition_ok, transition_error = _validate_turn_transition(
            current=current,
            command_config=command_config,
            language=language,
        )
        if not transition_ok:
            await _clear_pending_gps_checkin(db, company_id=bot.company_id, telegram_user_id=telegram_user_id)
            await db.commit()
            if send_replies:
                await _send_telegram_message(
                    token,
                    chat_id,
                    transition_error or _txt(language, "already_working"),
                    reply_markup=_remove_reply_keyboard(),
                )
                await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
            return TelegramBotPollItem(
                update_id=update_id,
                ok=False,
                action="turn_validation_failed",
                message=transition_error or "Transición inválida.",
                employee_id=employee.id,
                employee_name=employee.full_name,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        gps_event = await _create_gps_location_event(
            db,
            bot=bot,
            employee=employee,
            update=update,
            message=message,
            latitude=latitude,
            longitude=longitude,
            language=language,
            source_ref_suffix="gps_check_in_location",
        )
        created, message_text = await _create_bot_attendance_event(
            db,
            bot=bot,
            employee=employee,
            update=update,
            message=message,
            command="/entrada",
            args="Ubicación GPS validada",
            command_config=command_config,
            language=language,
        )
        await _open_gps_tracking_session(
            db,
            company_id=bot.company_id,
            employee=employee,
            telegram_user_id=telegram_user_id,
            chat_id=chat_id,
            event=gps_event,
            message=message,
        )
        await _clear_pending_gps_checkin(db, company_id=bot.company_id, telegram_user_id=telegram_user_id)
        await db.commit()

        if send_replies:
            await _send_telegram_message(
                token,
                chat_id,
                _txt(language, "gps_location_received_shift_started"),
                reply_markup=_remove_reply_keyboard(),
            )
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)

        return TelegramBotPollItem(
            update_id=update_id,
            ok=created,
            action="check_in",
            message=message_text,
            employee_id=employee.id,
            employee_name=employee.full_name,
            event_created=created,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    # Ubicación espontánea durante turno activo: se registra como GPS, pero no inicia turno.
    status_key = _current_status_key(current)
    if status_key in {"working", "on_break"}:
        gps_event = await _create_gps_location_event(
            db,
            bot=bot,
            employee=employee,
            update=update,
            message=message,
            latitude=latitude,
            longitude=longitude,
            language=language,
            source_ref_suffix="gps_ping_location",
        )
        await _touch_gps_tracking_session(
            db,
            company_id=bot.company_id,
            employee=employee,
            event=gps_event,
            message=message,
        )
        await db.commit()
        if send_replies and not is_live_location:
            await _send_telegram_message(token, chat_id, _txt(language, "gps_location_received"), reply_markup=_remove_reply_keyboard())
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="gps_location",
            message="Ubicación GPS registrada.",
            employee_id=employee.id,
            employee_name=employee.full_name,
            event_created=True,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if is_live_location:
        # Si Telegram sigue enviando ubicación después de finalizar turno,
        # CLONEXA la ignora para no contaminar CRM/Reportes de una jornada cerrada.
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="gps_live_ignored_closed_shift",
            message="Ubicación en vivo ignorada porque no hay turno activo.",
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if send_replies:
        await _send_telegram_message(token, chat_id, _txt(language, "gps_no_pending"), reply_markup=_remove_reply_keyboard())
        await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
    return TelegramBotPollItem(
        update_id=update_id,
        ok=False,
        action="gps_no_pending",
        message="Ubicación recibida sin solicitud pendiente.",
        employee_id=employee.id,
        employee_name=employee.full_name,
        telegram_user_id=telegram_user_id,
        telegram_username=username,
    )



async def _process_telegram_update(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    token: str,
    update: dict[str, Any],
    send_replies: bool,
) -> TelegramBotPollItem:
    update_id = update.get("update_id")
    message = _telegram_message(update)

    if message is None:
        return TelegramBotPollItem(update_id=update_id, ok=True, action="ignored", message="Update sin mensaje.")

    telegram_user_id, username, first_name, chat_id, raw_text, callback_query_id = _telegram_identity_from_update(update)
    text_value = (raw_text or "").strip()

    # CLONEXA 015C-R5: language exists for every update, including Telegram callbacks.
    language = await _get_user_language(db, bot.company_id, telegram_user_id) if telegram_user_id else "es"

    if callback_query_id:
        await _answer_callback_query(token, callback_query_id)

    if isinstance(message.get("location"), dict):
        return await _process_telegram_location(
            db,
            bot=bot,
            token=token,
            update=update,
            message=message,
            telegram_user_id=telegram_user_id,
            username=username,
            chat_id=chat_id,
            send_replies=send_replies,
        )

    if not text_value:
        return TelegramBotPollItem(update_id=update_id, ok=True, action="ignored", message="Mensaje sin texto.")

    # Idioma: selector explícito desde botones.
    if text_value == "clx:language":
        language = await _get_user_language(db, bot.company_id, telegram_user_id)
        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "choose_language"), reply_markup=_language_keyboard())
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="language_menu",
            message="Selector de idioma enviado.",
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if text_value.startswith("clx:lang:"):
        selected_language = _lang(text_value.removeprefix("clx:lang:"))
        had_preference = await _user_language_preference_exists(db, bot.company_id, telegram_user_id)
        current_language = await _get_user_language(db, bot.company_id, telegram_user_id)

        if callback_query_id:
            await _answer_callback_query(token, callback_query_id, _txt(selected_language, "language_updating"))

        employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)

        # Si el usuario oprime el mismo idioma varias veces, no llenamos el chat.
        if had_preference and selected_language == current_language:
            if callback_query_id:
                await _answer_callback_query(token, callback_query_id, _txt(selected_language, "language_already"))
            return TelegramBotPollItem(
                update_id=update_id,
                ok=True,
                action="language_already",
                message=f"Idioma ya configurado: {selected_language}",
                employee_id=employee.id if employee else None,
                employee_name=employee.full_name if employee else None,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        language = await _set_user_language(db, bot.company_id, telegram_user_id, username, selected_language)
        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "language_saved"))
            if employee is not None:
                company = await ensure_company_exists(db, bot.company_id)
                await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language, greet=True)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="language_saved",
            message=f"Idioma configurado: {language}",
            employee_id=employee.id if employee else None,
            employee_name=employee.full_name if employee else None,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if text_value.startswith("clx:mat:"):
        # CLONEXA 015C-R5:
        # Desactivamos callbacks de selección de material. El flujo estable ahora es Telegram Web App.
        employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
        enabled_modules = await _enabled_module_codes(db, bot.company_id)
        if send_replies:
            if employee is None:
                await _send_telegram_message(token, chat_id, _txt(language, "not_linked", telegram_user_id=telegram_user_id), reply_markup=_language_keyboard())
            elif "materials" not in enabled_modules or "inventory" not in enabled_modules or not _employee_can_request_material(employee):
                await _send_telegram_message(token, chat_id, "No tienes permisos para solicitar material o Inventario no está activo.")
            else:
                await _send_materials_webapp_button(
                    token=token,
                    chat_id=chat_id,
                    company_id=bot.company_id,
                    telegram_user_id=telegram_user_id,
                )
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="materials_webapp_button",
            message="Botón Web App Materiales enviado.",
            employee_id=employee.id if employee else None,
            employee_name=employee.full_name if employee else None,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    text_value = _callback_to_command(text_value)
    command, args = _normalize_command(text_value)
    language = await _get_user_language(db, bot.company_id, telegram_user_id)

    if command in {"/start", "/idioma", "/language", "/lang"}:
        employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
        has_language = await _user_language_preference_exists(db, bot.company_id, telegram_user_id)
        if send_replies:
            if command == "/start" and employee is None:
                await _send_telegram_message(
                    token,
                    chat_id,
                    f"🆔 Tu Telegram ID es: {telegram_user_id or 'NO_DETECTADO'}\n\n"
                    "Entrega este número a la persona encargada para completar tu registro en CLONEXA.",
                )
            if not has_language:
                await _send_telegram_message(token, chat_id, _txt(language, "choose_language"), reply_markup=_language_keyboard())
            elif employee is not None:
                company = await ensure_company_exists(db, bot.company_id)
                await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language, greet=True)
            else:
                await _send_telegram_message(token, chat_id, _txt(language, "choose_language"), reply_markup=_language_keyboard())
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="start",
            message="Menú de idioma o acciones enviado.",
            employee_id=employee.id if employee else None,
            employee_name=employee.full_name if employee else None,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if command == "/whoami":
        employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
        if employee is None:
            username_line = f"Usuario: @{username}\n" if username else ""
            reply = _txt(
                language,
                "whoami_unlinked",
                telegram_user_id=telegram_user_id,
                username_line=username_line,
            )
            if send_replies:
                await _send_telegram_message(token, chat_id, reply, reply_markup=_language_keyboard())
            return TelegramBotPollItem(
                update_id=update_id,
                ok=True,
                action="whoami",
                message="Telegram ID enviado. Empleado no vinculado.",
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        company = await ensure_company_exists(db, bot.company_id)
        if send_replies:
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language, greet=True)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="whoami",
            message="Empleado vinculado. Menú enviado.",
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if command and not command.startswith("/") and telegram_user_id:
        end_shift_summary_result = await _process_end_shift_summary_text(
            db,
            bot=bot,
            token=token,
            update=update,
            message=message,
            telegram_user_id=telegram_user_id,
            username=username,
            chat_id=chat_id,
            text_value=text_value,
            language=language,
            send_replies=send_replies,
        )
        if end_shift_summary_result is not None:
            return end_shift_summary_result

        pending_material = await _get_pending_material_request(db, company_id=bot.company_id, telegram_user_id=telegram_user_id)
        if pending_material is not None:
            return await _process_material_cart_text(
                db,
                bot=bot,
                token=token,
                update=update,
                message=message,
                telegram_user_id=telegram_user_id,
                username=username,
                chat_id=chat_id,
                text_value=text_value,
                language=language,
                send_replies=send_replies,
            )

    command_config = TELEGRAM_COMMANDS.get(command)
    if command_config is None:
        employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
        reply = _txt(language, "unknown")
        if send_replies:
            if employee is not None:
                company = await ensure_company_exists(db, bot.company_id)
                await _send_telegram_message(token, chat_id, reply)
                await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
            else:
                await _send_telegram_message(token, chat_id, reply, reply_markup=_language_keyboard())
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="unknown",
            message="Acción no reconocida.",
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
    if employee is None:
        reply = _txt(language, "not_linked", telegram_user_id=telegram_user_id)
        if send_replies:
            await _send_telegram_message(token, chat_id, reply, reply_markup=_language_keyboard())
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="not_linked",
            message="Empleado no vinculado.",
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    company = await ensure_company_exists(db, bot.company_id)
    enabled_modules = await _enabled_module_codes(db, bot.company_id)
    module_code = command_config.get("module_code") or "workforce"

    # Módulos extra solo aparecen/funcionan si están activos para la empresa.
    if module_code not in {"workforce", "bots"} and module_code not in enabled_modules:
        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "module_inactive"))
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="module_inactive",
            message=f"Módulo inactivo: {module_code}",
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if command in {"/material", "/materiales"}:
        if "inventory" not in enabled_modules or not _employee_can_request_material(employee):
            if send_replies:
                await _send_telegram_message(token, chat_id, "No tienes permisos para solicitar material o Inventario no está activo.")
                await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
            return TelegramBotPollItem(
                update_id=update_id,
                ok=False,
                action="material_not_allowed",
                message="Material no permitido.",
                employee_id=employee.id,
                employee_name=employee.full_name,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

    current = await _get_current_attendance_status(db, employee.company_id, employee.id)
    transition_ok, transition_error = _validate_turn_transition(current=current, command_config=command_config, language=language)
    if not transition_ok:
        if send_replies:
            await _send_telegram_message(token, chat_id, transition_error or _txt(language, "must_start_shift"))
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="turn_validation_failed",
            message=transition_error or "Transición de turno inválida.",
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if command_config.get("turn_action") == "start_shift" and "gps" in enabled_modules:
        pending = await _get_pending_gps_checkin(db, company_id=bot.company_id, telegram_user_id=telegram_user_id)
        await _set_pending_gps_checkin(
            db,
            company_id=bot.company_id,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
            employee_id=employee.id,
            chat_id=chat_id,
            language=language,
        )
        await db.commit()
        if send_replies:
            await _send_telegram_message(
                token,
                chat_id,
                _txt(language, "gps_location_pending" if pending else "gps_required_for_start"),
                reply_markup=_remove_reply_keyboard(),
            )
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="gps_required_for_check_in",
            message="GPS requerido antes de iniciar turno.",
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if command in {"/material", "/materiales"}:
        # CLONEXA 015C-R5:
        # Materiales se solicita desde Telegram Web App para soportar inventarios grandes y evitar callbacks.
        if send_replies:
            await _send_materials_webapp_button(
                token=token,
                chat_id=chat_id,
                company_id=bot.company_id,
                telegram_user_id=telegram_user_id,
            )
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="materials_webapp_button",
            message="Botón Web App Materiales enviado.",
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if command_config.get("requires_text") and not args:
        reply = _txt(language, "need_detail", command=command)
        if send_replies:
            await _send_telegram_message(token, chat_id, reply)
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="missing_detail",
            message=reply,
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if send_replies:
        await _send_telegram_chat_action(token, chat_id)

    if command == "/estado":
        status_text = _current_status_key(current)
        created, message_text = await _create_bot_attendance_event(
            db,
            bot=bot,
            employee=employee,
            update=update,
            message=message,
            command=command,
            args=args,
            command_config=command_config,
            language=language,
        )
        await db.commit()
        reply = _txt(language, "status_line", employee_name=employee.full_name, status_text=status_text)
        if send_replies:
            await _send_telegram_message(token, chat_id, reply)
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action=command_config["event_type"],
            message=message_text,
            employee_id=employee.id,
            employee_name=employee.full_name,
            event_created=created,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if command_config.get("turn_action") == "end_shift" and not args:
        await _set_pending_end_shift_summary(
            db,
            company_id=bot.company_id,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
            employee_id=employee.id,
            chat_id=chat_id,
            language=language,
        )
        await db.commit()

        if callback_query_id:
            await _answer_callback_query(token, callback_query_id, _txt(language, "end_shift_summary_required"))

        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "end_shift_summary_prompt"))

        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="end_shift_summary_requested",
            message=_txt(language, "end_shift_summary_required"),
            employee_id=employee.id,
            employee_name=employee.full_name,
            event_created=False,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    created, message_text = await _create_bot_attendance_event(
        db,
        bot=bot,
        employee=employee,
        update=update,
        message=message,
        command=command,
        args=args,
        command_config=command_config,
        language=language,
    )
    await db.commit()

    if send_replies:
        await _send_telegram_message(token, chat_id, message_text)
        await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)

    return TelegramBotPollItem(
        update_id=update_id,
        ok=created,
        action=command_config["event_type"],
        message=message_text,
        employee_id=employee.id,
        employee_name=employee.full_name,
        event_created=created,
        telegram_user_id=telegram_user_id,
        telegram_username=username,
    )




async def _poll_telegram_updates_for_company(
    db: AsyncSession,
    *,
    company_id: UUID,
    limit: int = 20,
    send_replies: bool = True,
) -> TelegramBotPollOut:
    """
    Lee updates de Telegram para una empresa sin pisar otros bots.

    Regla 011A3-R2:
    - Un lock por company_id evita doble getUpdates del mismo bot.
    - Diferentes empresas/bots corren independientes.
    - Errores transitorios no desactivan el bot.
    - El offset vive en config_json por empresa.
    """
    async with _listener_lock(company_id):
        await ensure_company_exists(db, company_id)
        row = await get_telegram_instance(db, company_id)
        if row is None or not row.bot_token_encrypted:
            raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")
        if row.status == "inactive":
            raise HTTPException(status_code=409, detail="Telegram bot is inactive")

        token = decrypt_token(row.bot_token_encrypted)
        if not token:
            raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")

        config = dict(row.config_json or {})
        offset = config.get("telegram_update_offset")
        params: dict[str, Any] = {
            "timeout": 0,
            "limit": limit,
            "allowed_updates": '["message","edited_message","callback_query"]',
        }
        if offset:
            params["offset"] = int(offset)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"https://api.telegram.org/bot{token}/getUpdates", params=params)
                telegram_payload = response.json()
        except httpx.HTTPError as exc:
            error_text = f"Telegram polling error: {exc}"
            config["listener_error"] = error_text
            config["listener_running"] = False
            config["listener_updated_at"] = utcnow().isoformat()
            row.config_json = config
            row.last_error = error_text
            row.updated_at = utcnow()
            await db.commit()
            raise HTTPException(status_code=502, detail=error_text) from exc

        if not telegram_payload.get("ok"):
            description = str(telegram_payload.get("description") or "Telegram getUpdates failed")
            config["listener_error"] = description
            config["listener_running"] = False
            config["listener_updated_at"] = utcnow().isoformat()
            row.config_json = config
            row.last_error = description
            row.updated_at = utcnow()

            # Unauthorized / token inválido sí debe marcar error. Conflictos o timeouts no apagan el bot.
            lowered = description.lower()
            if "unauthorized" in lowered or "not found" in lowered or "token" in lowered:
                row.status = "error"
            else:
                row.status = "active"

            await db.commit()
            raise HTTPException(status_code=502, detail=description)

        updates = telegram_payload.get("result") or []
        processed: list[TelegramBotPollItem] = []
        next_offset = int(config.get("telegram_update_offset") or 0)

        for update in updates:
            update_id_value = update.get("update_id")
            try:
                item = await _process_telegram_update(db, bot=row, token=token, update=update, send_replies=send_replies)
                processed.append(item)
            except Exception as exc:  # pragma: no cover - listener safety
                logger.exception("Telegram update processing error for company %s update %s: %s", company_id, update_id_value, exc)
                await db.rollback()
                processed.append(
                    TelegramBotPollItem(
                        update_id=update_id_value,
                        ok=False,
                        action="processing_error",
                        message=str(exc),
                    )
                )

            # Avanzamos offset aunque el update falle para evitar reprocesar callbacks viejos.
            if isinstance(update_id_value, int):
                next_offset = max(next_offset, update_id_value + 1)

        # 013-R2:
        # Persistimos offset solo si hubo updates. No actualizamos last_poll_at cada 3 segundos,
        # porque eso genera lock churn/deadlocks en company_bot_instances cuando hay varios bots.
        if updates:
            config = dict(row.config_json or config)
            config["telegram_update_offset"] = next_offset
            config["last_poll_at"] = utcnow().isoformat()
            config["last_poll_count"] = len(processed)
            config["listener_running"] = True
            config["listener_error"] = None
            config["listener_updated_at"] = utcnow().isoformat()
            row.config_json = config
            row.status = "active"
            row.last_error = None
            row.updated_at = utcnow()
            await db.commit()

        return TelegramBotPollOut(
            ok=True,
            company_id=company_id,
            bot_username=row.bot_username,
            received=len(updates),
            processed=len(processed),
            next_offset=next_offset or config.get("telegram_update_offset"),
            items=processed,
        )


def _listener_key(company_id: UUID | str) -> str:
    return str(company_id)


def _is_listener_running(company_id: UUID | str) -> bool:
    task = TELEGRAM_LISTENER_TASKS.get(_listener_key(company_id))
    return bool(task and not task.done())


async def _mark_listener_state(company_id: UUID, *, enabled: bool, running: bool, error: str | None = None) -> None:
    async with _listener_lock(company_id):
        async with AsyncSessionLocal() as db:
            row = await get_telegram_instance(db, company_id)
            if row is None:
                return
            config = dict(row.config_json or {})
            config["listener_enabled"] = enabled
            config["listener_running"] = running
            config["listener_updated_at"] = utcnow().isoformat()
            if error:
                config["listener_error"] = error
                row.last_error = error
            else:
                config.pop("listener_error", None)
                row.last_error = None
            row.config_json = config
            row.updated_at = utcnow()
            if row.status != "inactive":
                # No marcar error por fallos transitorios; mantener el bot recuperable.
                row.status = "active" if row.bot_token_encrypted else "configured"
            await db.commit()


async def _telegram_listener_loop(company_id: UUID) -> None:
    key = _listener_key(company_id)
    keep_enabled_on_exit = True
    try:
        await _mark_listener_state(company_id, enabled=True, running=True, error=None)

        while True:
            interval = TELEGRAM_LISTENER_DEFAULT_INTERVAL
            should_stop = False

            async with AsyncSessionLocal() as db:
                row = await get_telegram_instance(db, company_id)
                if row is None:
                    should_stop = True
                    keep_enabled_on_exit = False
                elif row.status == "inactive":
                    should_stop = True
                    keep_enabled_on_exit = False
                else:
                    config = dict(row.config_json or {})
                    if not config.get("listener_enabled"):
                        should_stop = True
                        keep_enabled_on_exit = False
                    else:
                        interval = int(config.get("listener_interval_seconds") or TELEGRAM_LISTENER_DEFAULT_INTERVAL)
                        interval = max(2, min(interval, 30))
                        if not row.bot_token_encrypted:
                            should_stop = True
                            keep_enabled_on_exit = False
                            row.last_error = "Telegram bot token not configured"
                            row.status = "error"
                            config["listener_enabled"] = False
                            config["listener_running"] = False
                            config["listener_error"] = row.last_error
                            config["listener_updated_at"] = utcnow().isoformat()
                            row.config_json = config
                            row.updated_at = utcnow()
                            await db.commit()

            if should_stop:
                break

            try:
                async with AsyncSessionLocal() as poll_db:
                    await _poll_telegram_updates_for_company(
                        poll_db,
                        company_id=company_id,
                        limit=20,
                        send_replies=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - safety loop
                logger.warning("Telegram listener recoverable error for company %s: %s", company_id, exc)
                await _mark_listener_state(company_id, enabled=True, running=False, error=str(exc))
                await asyncio.sleep(max(5, interval))
                continue

            await asyncio.sleep(interval)

    except asyncio.CancelledError:
        logger.info("Telegram listener cancelled for company %s", company_id)
        raise
    finally:
        current = TELEGRAM_LISTENER_TASKS.get(key)
        if current is asyncio.current_task():
            TELEGRAM_LISTENER_TASKS.pop(key, None)

        stop_requested = key in TELEGRAM_LISTENER_STOP_REQUESTED
        TELEGRAM_LISTENER_STOP_REQUESTED.discard(key)

        with contextlib.suppress(Exception):
            await _mark_listener_state(
                company_id,
                enabled=False if stop_requested or not keep_enabled_on_exit else True,
                running=False,
            )


def _cancel_telegram_listener(company_id: UUID | str) -> None:
    key = _listener_key(company_id)
    TELEGRAM_LISTENER_STOP_REQUESTED.add(key)
    task = TELEGRAM_LISTENER_TASKS.pop(key, None)
    if task and not task.done():
        task.cancel()


def _ensure_telegram_listener_task(company_id: UUID) -> bool:
    key = _listener_key(company_id)
    existing = TELEGRAM_LISTENER_TASKS.get(key)
    if existing and not existing.done():
        return False
    TELEGRAM_LISTENER_STOP_REQUESTED.discard(key)
    TELEGRAM_LISTENER_TASKS[key] = asyncio.create_task(_telegram_listener_loop(company_id))
    return True


async def bootstrap_telegram_listeners() -> dict[str, Any]:
    """
    Levanta automáticamente todos los bots que quedaron con listener_enabled=true.
    Esto permite reiniciar API/Docker sin volver a presionar Iniciar escucha por empresa.
    """
    started: list[str] = []
    async with AsyncSessionLocal() as db:
        await ensure_bot_storage(db)
        result = await db.execute(
            select(CompanyBotInstance).where(
                CompanyBotInstance.channel == "telegram",
                CompanyBotInstance.bot_token_encrypted.is_not(None),
            )
        )
        rows = result.scalars().all()

    for row in rows:
        config = dict(row.config_json or {})
        if row.status != "inactive" and config.get("listener_enabled"):
            if _ensure_telegram_listener_task(row.company_id):
                started.append(str(row.company_id))

    return {"ok": True, "started": started, "count": len(started)}


@router.get("/companies/{company_id}/telegram", response_model=TelegramBotConfigOut)
async def get_company_telegram_bot(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotConfigOut:
    await ensure_company_exists(db, company_id)
    row = await get_telegram_instance(db, company_id)
    return bot_out(row, company_id)


@router.get("/companies/{company_id}/whatsapp-web")
async def get_company_whatsapp_web_agent(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await ensure_company_exists(db, company_id)
    payload = await whatsapp_status(str(company_id))
    return _whatsapp_web_out(company, payload)


@router.post("/companies/{company_id}/whatsapp-web/start")
async def start_company_whatsapp_web_agent(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await ensure_company_exists(db, company_id)
    payload = await whatsapp_start(str(company_id))
    return _whatsapp_web_out(company, payload)


@router.post("/companies/{company_id}/whatsapp-web/logout")
async def logout_company_whatsapp_web_agent(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await ensure_company_exists(db, company_id)
    payload = await whatsapp_logout(str(company_id))
    return _whatsapp_web_out(company, payload)


@router.post("/companies/{company_id}/whatsapp-web/test")
async def test_company_whatsapp_web_agent(
    company_id: UUID,
    payload: WhatsAppWebTestIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await ensure_company_exists(db, company_id)
    to = str(payload.to or "").strip()
    if not to:
        current = await whatsapp_status(str(company_id))
        to = str(current.get("connected_phone") or "").strip()
    if not to:
        raise HTTPException(status_code=422, detail="No hay numero destino ni WhatsApp vinculado para probar.")
    message = str(payload.message or "").strip() or _whatsapp_agent_welcome(company)
    sent = await whatsapp_send(str(company_id), to, message)
    if not sent.get("ok"):
        raise HTTPException(status_code=409, detail=sent.get("detail") or "No se pudo enviar la prueba WhatsApp.")
    return {"ok": True, "sent": sent}


@router.post("/whatsapp-web/inbound")
async def whatsapp_web_agent_inbound(
    payload: WhatsAppWebInboundIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _ensure_whatsapp_inbound_secret(request)
    try:
        company_id = UUID(str(payload.company_id))
    except Exception:
        raise HTTPException(status_code=422, detail="Empresa invalida.")
    company = await ensure_company_exists(db, company_id)
    if _text_norm(payload.event_type) == "connected":
        return {
            "ok": True,
            "company_id": str(company_id),
            "agent_name": _wa_agent_name(company),
            "reply": _whatsapp_agent_welcome(company),
        }
    text_value = str(payload.text or "").strip()
    if not text_value:
        return {"ok": True, "ignored": True, "reply": ""}
    reply = await _whatsapp_agent_reply(
        company_id=company_id,
        company=company,
        db=db,
        text_value=text_value,
        push_name=payload.push_name,
    )
    return {
        "ok": True,
        "company_id": str(company_id),
        "agent_name": _wa_agent_name(company),
        "reply": reply,
    }


@router.put("/companies/{company_id}/telegram", response_model=TelegramBotConfigOut)
async def save_company_telegram_bot(
    company_id: UUID,
    payload: TelegramBotConfigIn,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotConfigOut:
    company = await ensure_company_exists(db, company_id)
    await ensure_bot_storage(db)

    token = (payload.token or "").strip()
    name = (payload.name or "").strip() or f"{company.name} Telegram Bot"

    row = await get_telegram_instance(db, company_id)
    if row is None:
        if not token:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Telegram token is required")
        row = CompanyBotInstance(
            company_id=company_id,
            channel="telegram",
            name=name,
            bot_token_encrypted=encrypt_token(token),
            token_mask=mask_token(token),
            status="configured",
            config_json={},
            updated_at=utcnow(),
        )
        db.add(row)
    else:
        row.name = name
        row.updated_at = utcnow()
        if token:
            row.bot_token_encrypted = encrypt_token(token)
            row.token_mask = mask_token(token)
            row.bot_username = None
            row.last_validated_at = None
            row.last_error = None
        if not row.bot_token_encrypted:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Telegram token is required")
        row.status = "configured"

    await db.commit()
    await db.refresh(row)
    return bot_out(row, company_id)


@router.post("/companies/{company_id}/telegram/test", response_model=TelegramBotTestOut)
async def test_company_telegram_bot(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotTestOut:
    await ensure_company_exists(db, company_id)
    row = await get_telegram_instance(db, company_id)
    if row is None or not row.bot_token_encrypted:
        raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")

    token = decrypt_token(row.bot_token_encrypted)
    if not token:
        raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")

    telegram_payload: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            telegram_payload = response.json()
            if response.status_code >= 400 or not telegram_payload.get("ok"):
                row.status = "error"
                row.last_error = str(telegram_payload.get("description") or f"HTTP {response.status_code}")
                row.last_validated_at = utcnow()
                row.updated_at = utcnow()
                await db.commit()
                await db.refresh(row)
                out = bot_out(row, company_id).model_dump()
                return TelegramBotTestOut(**out, telegram_response=telegram_payload)

            user = telegram_payload.get("result") or {}
            row.bot_username = user.get("username")
            row.name = row.name or user.get("first_name") or "Telegram Bot"
            row.status = "active"
            row.last_error = None
            row.last_validated_at = utcnow()
            row.updated_at = utcnow()
            row.config_json = {
                **(row.config_json or {}),
                "telegram_bot_id": user.get("id"),
                "can_join_groups": user.get("can_join_groups"),
                "can_read_all_group_messages": user.get("can_read_all_group_messages"),
                "supports_inline_queries": user.get("supports_inline_queries"),
            }
            await db.commit()
            await db.refresh(row)
            out = bot_out(row, company_id).model_dump()
            return TelegramBotTestOut(**out, telegram_response={"ok": True, "result": user})

    except httpx.HTTPError as exc:
        row.status = "error"
        row.last_error = f"Telegram connection error: {exc}"
        row.last_validated_at = utcnow()
        row.updated_at = utcnow()
        await db.commit()
        await db.refresh(row)
        out = bot_out(row, company_id).model_dump()
        return TelegramBotTestOut(**out, telegram_response={"ok": False, "description": str(exc)})



@router.post("/companies/{company_id}/telegram/listener/start", response_model=TelegramBotConfigOut)
async def start_company_telegram_listener(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotConfigOut:
    """
    011A-2:
    Activa la escucha automática del bot Telegram para esta empresa.
    Reemplaza el polling manual por PowerShell. Admin V2 solo muestra estado técnico básico.
    """
    await ensure_company_exists(db, company_id)
    row = await get_telegram_instance(db, company_id)
    if row is None or not row.bot_token_encrypted:
        raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")
    if row.status == "inactive":
        row.status = "active"

    token = decrypt_token(row.bot_token_encrypted)
    if not token:
        raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")

    # Validación rápida. Si el token está mal, no arrancamos listener.
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            payload = response.json()
            if response.status_code >= 400 or not payload.get("ok"):
                row.status = "error"
                row.last_error = str(payload.get("description") or f"HTTP {response.status_code}")
                row.last_validated_at = utcnow()
                row.updated_at = utcnow()
                await db.commit()
                await db.refresh(row)
                return bot_out(row, company_id)

            user = payload.get("result") or {}
            row.bot_username = user.get("username") or row.bot_username
            row.name = row.name or user.get("first_name") or "Telegram Bot"
            row.last_validated_at = utcnow()
            row.last_error = None
    except httpx.HTTPError as exc:
        row.status = "error"
        row.last_error = f"Telegram connection error: {exc}"
        row.last_validated_at = utcnow()
        row.updated_at = utcnow()
        await db.commit()
        await db.refresh(row)
        return bot_out(row, company_id)

    config = dict(row.config_json or {})
    config["listener_enabled"] = True
    config["listener_running"] = True
    config.setdefault("listener_interval_seconds", TELEGRAM_LISTENER_DEFAULT_INTERVAL)
    config.setdefault("listener_poll_limit", 20)
    config["listener_started_at"] = utcnow().isoformat()
    config["listener_updated_at"] = utcnow().isoformat()
    row.config_json = config
    row.status = "active"
    row.updated_at = utcnow()
    await db.commit()
    await db.refresh(row)

    _ensure_telegram_listener_task(company_id)

    # 011A3-R2:
    # No hacemos poll inmediato dentro del request porque compite con el task de escucha
    # y puede producir deadlocks o doble getUpdates. El listener procesa en su ciclo propio.
    return bot_out(row, company_id)


@router.post("/companies/{company_id}/telegram/deactivate", response_model=TelegramBotConfigOut)
async def deactivate_company_telegram_bot(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotConfigOut:
    await ensure_company_exists(db, company_id)
    row = await get_telegram_instance(db, company_id)
    if row is None:
        return bot_out(None, company_id)

    _cancel_telegram_listener(company_id)
    config = dict(row.config_json or {})
    config["listener_enabled"] = False
    config["listener_running"] = False
    config["listener_updated_at"] = utcnow().isoformat()
    row.config_json = config
    row.status = "inactive"
    row.updated_at = utcnow()
    await db.commit()
    await db.refresh(row)
    return bot_out(row, company_id)



@router.post("/companies/{company_id}/telegram/poll", response_model=TelegramBotPollOut)
async def poll_company_telegram_bot(
    company_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    send_replies: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> TelegramBotPollOut:
    """
    Diagnóstico interno/manual. La operación normal debe usar Iniciar escucha en Admin V2.
    """
    return await _poll_telegram_updates_for_company(
        db,
        company_id=company_id,
        limit=limit,
        send_replies=send_replies,
    )


@router.post("/telegram/{company_id}/webhook", response_model=BotResponse)
async def telegram_webhook(
    company_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    update: dict[str, Any] = await request.json()
    event = parse_telegram_update(company_id, update)

    if event is None:
        return BotResponse(
            ok=True,
            action="ignored",
            message="Telegram update ignored",
        )

    result = await EventEngine().process(db, event)
    return BotResponse(
        ok=True,
        action=result.event_type,
        message="Event received",
        data=result.model_dump(mode="json"),
    )
