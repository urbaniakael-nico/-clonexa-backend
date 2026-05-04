from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
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
        "requires_text": True,
    },
    "/materiales": {
        "event_type": "material_request",
        "event_label": "Solicitud de material",
        "module_code": "materials",
        "status_after": "requested",
        "turn_action": "inside_shift",
        "payroll_affects": False,
        "reply_key": "material_requested",
        "requires_text": True,
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
        return callback["message"]
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
        "commands_hint": "También puedes escribir comandos: /entrada, /pausa, /reanudar, /salida, /estado.",
        "shift_started": "✅ Inicio de turno registrado.\nTiempo de trabajo pagable iniciado.",
        "break_started": "☕ Pausa registrada.\nEste tiempo NO suma para nómina ni KPIs de producción.",
        "work_resumed": "✅ Retomaste labores.\nEl tiempo pagable vuelve a contar.",
        "shift_ended": "🏁 Turno finalizado.\nLas pausas registradas no suman como tiempo pagable.",
        "shift_summary": "⏱️ Resumen de turno\nTiempo bruto: {gross}\nPausas no pagables: {breaks}\nTiempo pagable: {payable}\nHoras ordinarias: {regular}\nHoras extra: {extra}\nValor acumulado: {amount}",
        "observation_saved": "📝 Observación registrada.",
        "material_requested": "📦 Solicitud de material registrada.",
        "location_requested": "📍 Solicitud de ubicación registrada. Para ubicación real, usa compartir ubicación en Telegram.",
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
        "commands_hint": "You can also type commands: /entrada, /pausa, /reanudar, /salida, /estado.",
        "shift_started": "✅ Shift started.\nPayable work time has started.",
        "break_started": "☕ Break registered.\nThis time does NOT count for payroll or production KPIs.",
        "work_resumed": "✅ Work resumed.\nPayable time is counting again.",
        "shift_ended": "🏁 Shift ended.\nRegistered breaks do not count as payable time.",
        "shift_summary": "⏱️ Shift summary\nGross time: {gross}\nNon-payable breaks: {breaks}\nPayable time: {payable}\nRegular hours: {regular}\nOvertime: {extra}\nAccumulated value: {amount}",
        "observation_saved": "📝 Observation saved.",
        "material_requested": "📦 Material request saved.",
        "location_requested": "📍 Location request saved. For real location, use Telegram location sharing.",
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
        "commands_hint": "Vous pouvez aussi écrire : /entrada, /pausa, /reanudar, /salida, /estado.",
        "shift_started": "✅ Début de service enregistré.\nLe temps de travail payable commence.",
        "break_started": "☕ Pause enregistrée.\nCe temps ne compte PAS pour la paie ni les KPIs de production.",
        "work_resumed": "✅ Reprise du travail.\nLe temps payable compte à nouveau.",
        "shift_ended": "🏁 Service terminé.\nLes pauses enregistrées ne comptent pas comme temps payable.",
        "shift_summary": "⏱️ Résumé du service\nTemps brut : {gross}\nPauses non payables : {breaks}\nTemps payable : {payable}\nHeures ordinaires : {regular}\nHeures extra : {extra}\nValeur accumulée : {amount}",
        "observation_saved": "📝 Observation enregistrée.",
        "material_requested": "📦 Demande de matériel enregistrée.",
        "location_requested": "📍 Demande de localisation enregistrée. Pour la localisation réelle, utilisez le partage de position Telegram.",
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
    template = BOT_TEXTS.get(lang, BOT_TEXTS[DEFAULT_LANGUAGE]).get(key, key)
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


def _menu_keyboard(language: str, enabled_modules: set[str], status_text: str | None = None) -> dict[str, Any]:
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
    if "materials" in enabled_modules:
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
) -> None:
    enabled_modules = await _enabled_module_codes(db, company.id)
    current = await _get_current_attendance_status(db, company.id, employee.id)
    status_text = _current_status_key(current)
    text_value = _txt(language, "menu_title", employee_name=employee.full_name, company_name=company.name)
    await _send_telegram_message(
        token,
        chat_id,
        text_value,
        reply_markup=_menu_keyboard(language, enabled_modules, status_text),
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


async def _shift_end_summary_message(
    db: AsyncSession,
    *,
    employee: Employee,
    started_at: datetime | None,
    ended_at: datetime,
    language: str,
) -> str:
    base = _txt(language, "shift_ended")
    if started_at is None:
        return base

    gross_minutes, break_minutes, payable_minutes = await _calculate_shift_minutes(
        db,
        employee=employee,
        started_at=started_at,
        ended_at=ended_at,
    )

    regular_minutes = min(payable_minutes, 8 * 60)
    extra_minutes = max(0, payable_minutes - regular_minutes)

    regular_rate = Decimal(str(employee.hourly_rate_regular or 0))
    extra_rate = Decimal(str(employee.hourly_rate_extra or 0))
    value = (Decimal(regular_minutes) / Decimal(60) * regular_rate) + (
        Decimal(extra_minutes) / Decimal(60) * extra_rate
    )

    summary = _txt(
        language,
        "shift_summary",
        gross=_format_minutes(gross_minutes),
        breaks=_format_minutes(break_minutes),
        payable=_format_minutes(payable_minutes),
        regular=_format_minutes(regular_minutes),
        extra=_format_minutes(extra_minutes),
        amount=_format_money(value),
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

    started_at: datetime | None = None
    if event_type == "check_out":
        current_before_close = await _get_current_attendance_status(db, employee.company_id, employee.id)
        started_at = current_before_close.check_in_at if current_before_close else None

    await _upsert_attendance_status(db, employee, event_type, status_after, occurred_at)

    if event_type == "check_out":
        return True, await _shift_end_summary_message(
            db,
            employee=employee,
            started_at=started_at,
            ended_at=occurred_at,
            language=language,
        )

    return True, _txt(language, command_config.get("reply_key") or "status_checked")




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

    if callback_query_id:
        await _answer_callback_query(token, callback_query_id)

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
                await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
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

    text_value = _callback_to_command(text_value)
    command, args = _normalize_command(text_value)
    language = await _get_user_language(db, bot.company_id, telegram_user_id)

    if command in {"/start", "/idioma", "/language", "/lang"}:
        employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
        has_language = await _user_language_preference_exists(db, bot.company_id, telegram_user_id)
        if send_replies:
            if not has_language:
                await _send_telegram_message(token, chat_id, _txt(language, "choose_language"), reply_markup=_language_keyboard())
            elif employee is not None:
                company = await ensure_company_exists(db, bot.company_id)
                await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
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
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)
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
        await _send_telegram_message(token, chat_id, _txt(language, "processing"))

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
        "allowed_updates": '["message","edited_message","callback_query"]',
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
