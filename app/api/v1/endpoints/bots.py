from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
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

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover
    Fernet = None


router = APIRouter()

logger = logging.getLogger("clonexa.telegram_listener")
TELEGRAM_LISTENER_TASKS: dict[str, asyncio.Task] = {}
TELEGRAM_LISTENER_DEFAULT_INTERVAL = 3


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
    "/entrada": {
        "event_type": "check_in",
        "event_label": "Entrada",
        "module_code": "workforce",
        "status_after": "working",
        "reply": "Entrada registrada.",
    },
    "/inicio": {
        "event_type": "check_in",
        "event_label": "Entrada",
        "module_code": "workforce",
        "status_after": "working",
        "reply": "Entrada registrada.",
    },
    "/pausa": {
        "event_type": "break_start",
        "event_label": "Pausa",
        "module_code": "workforce",
        "status_after": "on_break",
        "reply": "Pausa registrada.",
    },
    "/reanudar": {
        "event_type": "break_end",
        "event_label": "Reanudar",
        "module_code": "workforce",
        "status_after": "working",
        "reply": "Reanudación registrada.",
    },
    "/salida": {
        "event_type": "check_out",
        "event_label": "Salida",
        "module_code": "workforce",
        "status_after": "checked_out",
        "reply": "Salida registrada.",
    },
    "/observacion": {
        "event_type": "observation",
        "event_label": "Observación",
        "module_code": "workforce",
        "status_after": "registered",
        "reply": "Observación registrada.",
        "requires_text": True,
    },
    "/obs": {
        "event_type": "observation",
        "event_label": "Observación",
        "module_code": "workforce",
        "status_after": "registered",
        "reply": "Observación registrada.",
        "requires_text": True,
    },
    "/material": {
        "event_type": "material_request",
        "event_label": "Solicitud de material",
        "module_code": "materials",
        "status_after": "requested",
        "reply": "Solicitud de material registrada.",
        "requires_text": True,
    },
    "/materiales": {
        "event_type": "material_request",
        "event_label": "Solicitud de material",
        "module_code": "materials",
        "status_after": "requested",
        "reply": "Solicitud de material registrada.",
        "requires_text": True,
    },
    "/estado": {
        "event_type": "status_query",
        "event_label": "Consulta de estado",
        "module_code": "workforce",
        "status_after": "registered",
        "reply": "Estado consultado.",
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
    if not isinstance(message, dict):
        return None
    return message


def _telegram_identity(message: dict[str, Any]) -> tuple[str, str | None, str | None, str | None]:
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}
    telegram_user_id = str(from_user.get("id") or "")
    username = from_user.get("username")
    first_name = from_user.get("first_name")
    chat_id = str(chat.get("id") or "")
    return telegram_user_id, username, first_name, chat_id


async def _send_telegram_message(token: str, chat_id: str | None, text_value: str) -> None:
    if not chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text_value},
            )
    except httpx.HTTPError:
        # No bloquea captura de eventos si Telegram no acepta la respuesta.
        return


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
) -> tuple[bool, str]:
    update_id = str(update.get("update_id") or "")
    message_id = str(message.get("message_id") or "")
    occurred_at = utcnow()
    source_ref = f"telegram:{update_id}:{message_id}"

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
    detail = args or text_value

    if command_config.get("requires_text") and not args:
        return False, f"Falta detalle. Usa: {command} texto"

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
            "telegram_update_id": update.get("update_id"),
            "telegram_message_id": message.get("message_id"),
            "telegram_user_id": (message.get("from") or {}).get("id"),
            "telegram_username": (message.get("from") or {}).get("username"),
            "chat_id": (message.get("chat") or {}).get("id"),
        },
        metadata_json={
            "source": "telegram_polling",
            "bot_instance_id": str(bot.id),
            "bot_username": bot.bot_username,
        },
        occurred_at=occurred_at,
    )
    db.add(event)
    await db.flush()
    await _upsert_attendance_status(db, employee, event_type, status_after, occurred_at)
    return True, command_config.get("reply") or "Evento registrado."


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

    text_value = (message.get("text") or "").strip()
    telegram_user_id, username, first_name, chat_id = _telegram_identity(message)

    if not text_value:
        return TelegramBotPollItem(update_id=update_id, ok=True, action="ignored", message="Mensaje sin texto.")

    command, args = _normalize_command(text_value)

    if command in {"/start", "/whoami"}:
        employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
        if employee is None:
            reply = (
                "CLONEXA recibió tu mensaje.\n"
                f"Telegram ID: {telegram_user_id}\n"
                + (f"Usuario: @{username}\n" if username else "")
                + "Pega este Telegram ID en Personal > Telegram ID para vincular el empleado."
            )
            if send_replies:
                await _send_telegram_message(token, chat_id, reply)
            return TelegramBotPollItem(
                update_id=update_id,
                ok=True,
                action="whoami",
                message="Telegram ID enviado. Empleado no vinculado.",
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        reply = (
            f"Hola {employee.full_name}.\n"
            f"Empresa vinculada: {employee.company_id}\n"
            "Comandos: /entrada, /pausa, /reanudar, /salida, /observacion texto, /material texto, /estado"
        )
        if send_replies:
            await _send_telegram_message(token, chat_id, reply)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="whoami",
            message="Empleado vinculado.",
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    command_config = TELEGRAM_COMMANDS.get(command)
    if command_config is None:
        command_config = {
            "event_type": "bot_message_received",
            "event_label": "Mensaje bot",
            "module_code": "bots",
            "status_after": "registered",
            "reply": "Mensaje recibido. Usa /entrada, /pausa, /reanudar, /salida, /observacion texto, /material texto o /estado.",
        }

    employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
    if employee is None:
        reply = (
            "No encontré un empleado activo vinculado a este Telegram.\n"
            f"Telegram ID: {telegram_user_id}\n"
            "Regístralo en Personal > Telegram ID y vuelve a intentar."
        )
        if send_replies:
            await _send_telegram_message(token, chat_id, reply)
        return TelegramBotPollItem(
            update_id=update_id,
            ok=False,
            action="not_linked",
            message="Empleado no vinculado.",
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if command == "/estado":
        current = await _get_current_attendance_status(db, employee.company_id, employee.id)
        status_text = current.status if current else "sin registro"
        created, message_text = await _create_bot_attendance_event(
            db,
            bot=bot,
            employee=employee,
            update=update,
            message=message,
            command=command,
            args=args,
            command_config=command_config,
        )
        reply = f"{employee.full_name}: estado actual = {status_text}."
        if send_replies:
            await _send_telegram_message(token, chat_id, reply)
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

    created, message_text = await _create_bot_attendance_event(
        db,
        bot=bot,
        employee=employee,
        update=update,
        message=message,
        command=command,
        args=args,
        command_config=command_config,
    )

    if send_replies:
        await _send_telegram_message(token, chat_id, message_text)

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
    await ensure_company_exists(db, company_id)
    row = await get_telegram_instance(db, company_id)
    if row is None or not row.bot_token_encrypted:
        raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")
    if row.status not in {"active", "configured"}:
        raise HTTPException(status_code=409, detail=f"Telegram bot is not active. Current status: {row.status}")

    token = decrypt_token(row.bot_token_encrypted)
    if not token:
        raise HTTPException(status_code=404, detail="Telegram bot token not configured for this company")

    config = dict(row.config_json or {})
    offset = config.get("telegram_update_offset")
    params: dict[str, Any] = {
        "timeout": 0,
        "limit": limit,
        "allowed_updates": '["message","edited_message"]',
    }
    if offset:
        params["offset"] = int(offset)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"https://api.telegram.org/bot{token}/getUpdates", params=params)
            telegram_payload = response.json()
    except httpx.HTTPError as exc:
        row.status = "error"
        row.last_error = f"Telegram polling error: {exc}"
        row.updated_at = utcnow()
        await db.commit()
        raise HTTPException(status_code=502, detail=row.last_error) from exc

    if not telegram_payload.get("ok"):
        row.status = "error"
        row.last_error = str(telegram_payload.get("description") or "Telegram getUpdates failed")
        row.updated_at = utcnow()
        await db.commit()
        raise HTTPException(status_code=502, detail=row.last_error)

    updates = telegram_payload.get("result") or []
    processed: list[TelegramBotPollItem] = []
    highest_update_id: int | None = None

    for update in updates:
        if isinstance(update.get("update_id"), int):
            highest_update_id = max(highest_update_id or update["update_id"], update["update_id"])
        item = await _process_telegram_update(db, bot=row, token=token, update=update, send_replies=send_replies)
        processed.append(item)

    if highest_update_id is not None:
        config["telegram_update_offset"] = highest_update_id + 1

    config["last_poll_at"] = utcnow().isoformat()
    config["last_poll_count"] = len(processed)
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
        next_offset=config.get("telegram_update_offset"),
        items=processed,
    )


def _listener_key(company_id: UUID | str) -> str:
    return str(company_id)


def _is_listener_running(company_id: UUID | str) -> bool:
    task = TELEGRAM_LISTENER_TASKS.get(_listener_key(company_id))
    return bool(task and not task.done())


async def _mark_listener_state(company_id: UUID, *, enabled: bool, running: bool, error: str | None = None) -> None:
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
        elif "listener_error" in config:
            config.pop("listener_error", None)
        row.config_json = config
        row.updated_at = utcnow()
        if error:
            row.last_error = error
            row.status = "error"
        await db.commit()


async def _telegram_listener_loop(company_id: UUID) -> None:
    key = _listener_key(company_id)
    try:
        while True:
            interval = TELEGRAM_LISTENER_DEFAULT_INTERVAL
            try:
                async with AsyncSessionLocal() as db:
                    row = await get_telegram_instance(db, company_id)
                    if row is None or row.status == "inactive":
                        break

                    config = dict(row.config_json or {})
                    if not config.get("listener_enabled"):
                        break

                    interval = int(config.get("listener_interval_seconds") or TELEGRAM_LISTENER_DEFAULT_INTERVAL)
                    interval = max(2, min(interval, 30))

                    if not row.bot_token_encrypted:
                        config["listener_enabled"] = False
                        config["listener_running"] = False
                        row.config_json = config
                        row.last_error = "Telegram bot token not configured"
                        row.status = "error"
                        row.updated_at = utcnow()
                        await db.commit()
                        break

                    config["listener_running"] = True
                    config["listener_updated_at"] = utcnow().isoformat()
                    row.config_json = config
                    row.updated_at = utcnow()
                    await db.commit()

                    await _poll_telegram_updates_for_company(
                        db,
                        company_id=company_id,
                        limit=int(config.get("listener_poll_limit") or 20),
                        send_replies=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - safety loop
                logger.exception("Telegram listener error for company %s", company_id)
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
        with contextlib.suppress(Exception):
            await _mark_listener_state(company_id, enabled=False, running=False)


def _cancel_telegram_listener(company_id: UUID | str) -> None:
    task = TELEGRAM_LISTENER_TASKS.pop(_listener_key(company_id), None)
    if task and not task.done():
        task.cancel()


def _ensure_telegram_listener_task(company_id: UUID) -> bool:
    key = _listener_key(company_id)
    existing = TELEGRAM_LISTENER_TASKS.get(key)
    if existing and not existing.done():
        return False
    TELEGRAM_LISTENER_TASKS[key] = asyncio.create_task(_telegram_listener_loop(company_id))
    return True


@router.get("/companies/{company_id}/telegram", response_model=TelegramBotConfigOut)
async def get_company_telegram_bot(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TelegramBotConfigOut:
    await ensure_company_exists(db, company_id)
    row = await get_telegram_instance(db, company_id)
    return bot_out(row, company_id)


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

    # Procesa inmediatamente mensajes pendientes para que el usuario vea efecto sin PowerShell.
    with contextlib.suppress(Exception):
        await _poll_telegram_updates_for_company(db, company_id=company_id, limit=20, send_replies=True)
        await db.refresh(row)

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
