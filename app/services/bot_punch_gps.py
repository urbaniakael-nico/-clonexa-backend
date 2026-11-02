"""Bot de Telegram: ubicacion SOLO en cada marcacion (interruptor bot_punch_gps, 060B).

Interruptor por empresa ``bot_punch_gps`` (settings del modulo workforce; necesita
GPS), apagado por defecto. Hoy solo VOLTAGE. Encendido:
- Iniciar turno, Pausa, Retomar, Finalizar turno y Solicitar material piden la
  ubicacion de ESE momento con un teclado de un solo boton "📍 Enviar mi ubicacion"
  (request_location). Al llegar: se registra la marcacion con esa ubicacion y hora
  (lat/lng, precision, dentro / fuera / sin perimetro), se quita el teclado y sigue
  el flujo (Finalizar sigue pidiendo el resumen del dia).
- Ya no se pide ni se recomienda la ubicacion en tiempo real. Si alguien la comparte
  igual, la PRIMERA ubicacion sirve para la marcacion pendiente y todas las
  actualizaciones (edited_message con location) se ignoran al inicio del webhook,
  antes de tocar la base y sin responder.
- El recordatorio de apagar la ubicacion en vivo solo sale al finalizar si esa
  persona la compartio en ese turno (una sola vez, como bot_gps_stop).
- Sin ubicacion en 3 minutos: UN recordatorio. Sin ubicacion no hay marcacion.
Apagado: todo exactamente igual que antes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("clonexa.bot_punch_gps")

KEY = "bot_punch_gps"
MODULE = "workforce"
PENDING_ACTION = "gps_punch"
LIVE_SHARED_ACTION = "gps_live_shared"
PENDING_MINUTES = 30
REMINDER_AFTER_SECONDS = 180
CACHE_SECONDS = 120
LOOP_SECONDS = 30

# Marcaciones que piden la ubicacion del momento.
PUNCH_TURN_ACTIONS = {"start_shift", "start_break", "resume_work", "end_shift"}
MATERIAL_COMMANDS = {"/material", "/materiales"}

TEXTS = {
    "es": {
        "btn": "📍 Enviar mi ubicación",
        "prompt": "Toca el botón para enviar tu ubicación de este momento.",
        "reminder": "⏰ Aún no recibimos tu ubicación. Toca «📍 Enviar mi ubicación» para registrar tu marcación.",
        "material_ok": "📍 Ubicación registrada.",
        "no_pending": "📍 Ubicación recibida. Para marcar, toca primero una opción del menú.",
    },
    "en": {
        "btn": "📍 Send my location",
        "prompt": "Tap the button to send your current location.",
        "reminder": "⏰ We haven't received your location yet. Tap \"📍 Send my location\" to register your action.",
        "material_ok": "📍 Location registered.",
        "no_pending": "📍 Location received. To clock an action, first tap an option in the menu.",
    },
}


def t(language: str | None, key: str) -> str:
    lang = language if language in TEXTS else "es"
    return TEXTS[lang][key]


def switch_on(settings: Any) -> bool:
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except ValueError:
            return False
    return isinstance(settings, dict) and settings.get(KEY) is True


async def is_on(db: AsyncSession | None, company_id: Any) -> bool:
    """Nunca falla: ante cualquier error, apagado (el bot sigue como siempre)."""
    if db is None or not company_id:
        return False
    try:
        settings = (await db.execute(text("""
            SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:c AS uuid) AND lower(m.code) = :m AND COALESCE(cm.enabled, true) IS TRUE
            LIMIT 1
        """), {"c": str(company_id), "m": MODULE})).scalar()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return False
    return switch_on(settings)


def needs_location(command: str, command_config: dict[str, Any]) -> bool:
    return command_config.get("turn_action") in PUNCH_TURN_ACTIONS or command in MATERIAL_COMMANDS


def keyboard(language: str) -> dict[str, Any]:
    return {"keyboard": [[{"text": t(language, "btn"), "request_location": True}]],
            "one_time_keyboard": True, "resize_keyboard": True}


def is_live_edit(update: Any) -> bool:
    """Actualizacion de una ubicacion en vivo: edited_message con location."""
    edited = update.get("edited_message") if isinstance(update, dict) else None
    return isinstance(edited, dict) and isinstance(edited.get("location"), dict)


# ------------------------------------------------ webhook: descarte sin base
_CACHE: dict[str, tuple[bool, str, float]] = {}


def remember(company_id: str, on: bool, secret: str | None) -> None:
    _CACHE[str(company_id)] = (bool(on), str(secret or ""), time.monotonic() + CACHE_SECONDS)


def drop_early(company_id: str, update: Any, header_secret: str | None) -> bool:
    """True si es una actualizacion de ubicacion en vivo de una empresa con el
    interruptor (segun lo que se vio hace menos de 2 min) y trae el secreto correcto:
    se responde 200 sin tocar la base."""
    if not is_live_edit(update):
        return False
    cached = _CACHE.get(str(company_id))
    if not cached or cached[2] < time.monotonic() or not cached[0]:
        return False
    secret = cached[1]
    return not secret or header_secret == secret


# ------------------------------------------------ pendientes (por usuario)
async def set_pending(db: AsyncSession, *, company_id: Any, telegram_user_id: str, username: str | None, employee_id: Any,
                      chat_id: str | None, language: str, command: str, args: str) -> None:
    payload = {"chat_id": chat_id, "language": language, "command": command, "args": args or "",
               "requested_at": datetime.now(timezone.utc).isoformat()}
    await db.execute(text(f"""
        INSERT INTO company_telegram_pending_actions (company_id, telegram_user_id, telegram_username, employee_id, action,
                                                      payload_json, expires_at, updated_at)
        VALUES (CAST(:c AS uuid), :t, :u, CAST(:e AS uuid), :a, CAST(:p AS jsonb), now() + interval '{PENDING_MINUTES} minutes', now())
        ON CONFLICT (company_id, telegram_user_id, action) DO UPDATE
           SET telegram_username = EXCLUDED.telegram_username, employee_id = EXCLUDED.employee_id,
               payload_json = EXCLUDED.payload_json, expires_at = EXCLUDED.expires_at, updated_at = now()
    """), {"c": str(company_id), "t": str(telegram_user_id), "u": username, "e": str(employee_id), "a": PENDING_ACTION,
           "p": json.dumps(payload)})


async def get_pending(db: AsyncSession, *, company_id: Any, telegram_user_id: str) -> dict[str, Any] | None:
    row = (await db.execute(text("""
        SELECT employee_id::text AS employee_id, payload_json FROM company_telegram_pending_actions
        WHERE company_id = CAST(:c AS uuid) AND telegram_user_id = :t AND action = :a
          AND (expires_at IS NULL OR expires_at > now())
        LIMIT 1
    """), {"c": str(company_id), "t": str(telegram_user_id), "a": PENDING_ACTION})).mappings().first()
    if not row:
        return None
    payload = row["payload_json"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = {}
    return {"employee_id": row["employee_id"], **(payload if isinstance(payload, dict) else {})}


async def clear_pending(db: AsyncSession, *, company_id: Any, telegram_user_id: str) -> None:
    await db.execute(text("""
        DELETE FROM company_telegram_pending_actions
        WHERE company_id = CAST(:c AS uuid) AND telegram_user_id = :t AND action = :a
    """), {"c": str(company_id), "t": str(telegram_user_id), "a": PENDING_ACTION})


async def mark_live_shared(db: AsyncSession, *, company_id: Any, telegram_user_id: str, employee_id: Any) -> None:
    """Esta persona compartio ubicacion en vivo (para el recordatorio de apagarla)."""
    await db.execute(text("""
        INSERT INTO company_telegram_pending_actions (company_id, telegram_user_id, employee_id, action, payload_json, updated_at)
        VALUES (CAST(:c AS uuid), :t, CAST(:e AS uuid), :a, '{}'::jsonb, now())
        ON CONFLICT (company_id, telegram_user_id, action) DO UPDATE SET updated_at = now(), employee_id = EXCLUDED.employee_id
    """), {"c": str(company_id), "t": str(telegram_user_id), "e": str(employee_id), "a": LIVE_SHARED_ACTION})


async def take_live_shared(db: AsyncSession, *, company_id: Any, telegram_user_id: str, since: datetime | None) -> bool:
    """True si compartio en vivo en este turno (desde `since`); la marca se consume."""
    row = (await db.execute(text("""
        DELETE FROM company_telegram_pending_actions
        WHERE company_id = CAST(:c AS uuid) AND telegram_user_id = :t AND action = :a
        RETURNING updated_at
    """), {"c": str(company_id), "t": str(telegram_user_id), "a": LIVE_SHARED_ACTION})).first()
    if not row:
        return False
    at = row[0]
    if since is None or not isinstance(at, datetime):
        return True
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    since = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    return at >= since - timedelta(minutes=PENDING_MINUTES)


# ------------------------------------------------ recordatorio a los 3 minutos
async def claim_due_reminders(db: AsyncSession, now_utc: datetime | None = None) -> list[dict[str, Any]]:
    """Pendientes de mas de 3 min sin recordatorio: se marcan (atomico) y se devuelven.
    Cada pendiente recibe UN solo recordatorio."""
    now_utc = now_utc or datetime.now(timezone.utc)
    rows = (await db.execute(text("""
        UPDATE company_telegram_pending_actions
           SET payload_json = payload_json || jsonb_build_object('reminded_at', CAST(:now_txt AS text))
         WHERE action = :a
           AND (expires_at IS NULL OR expires_at > :now)
           AND NOT (payload_json ? 'reminded_at')
           AND updated_at <= :due
        RETURNING company_id::text AS company_id, telegram_user_id, payload_json
    """), {"a": PENDING_ACTION, "now": now_utc, "now_txt": now_utc.isoformat(), "due": now_utc - timedelta(seconds=REMINDER_AFTER_SECONDS)})).mappings().all()
    await db.commit()
    out = []
    for row in rows:
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload or "{}")
        out.append({"company_id": row["company_id"], "telegram_user_id": row["telegram_user_id"],
                    "chat_id": (payload or {}).get("chat_id") or row["telegram_user_id"],
                    "language": (payload or {}).get("language") or "es"})
    return out


async def send_reminders(db: AsyncSession) -> int:
    from app.api.v1.endpoints import bots

    sent = 0
    tokens: dict[str, str | None] = {}
    for item in await claim_due_reminders(db):
        cid = item["company_id"]
        if cid not in tokens:
            tokens[cid] = await bot_token(db, cid)
        if not tokens[cid]:
            continue
        try:
            await bots._send_telegram_message(tokens[cid], item["chat_id"], t(item["language"], "reminder"),
                                              reply_markup=keyboard(item["language"]))
            sent += 1
        except Exception as exc:
            log.warning("Recordatorio de ubicacion no se pudo enviar (%s): %s", cid, type(exc).__name__)
    return sent


async def bot_token(db: AsyncSession, company_id: str) -> str | None:
    from uuid import UUID

    from app.api.v1.endpoints import bots

    try:
        bot = await bots.get_telegram_instance(db, UUID(str(company_id)))
        return bots.decrypt_token(bot.bot_token_encrypted) if bot is not None and bot.bot_token_encrypted else None
    except Exception:
        await db.rollback()
        return None


async def loop() -> None:
    """Cada 30 s: recordatorios de ubicacion (3 min) y avisos de turno abierto.
    Sin advisory lock: cada recordatorio y cada aviso se reclama de forma atomica en la
    base (UPDATE ... RETURNING / INSERT ... ON CONFLICT DO NOTHING), asi que aunque
    corrieran dos copias (despliegue solapado) nadie recibe dos mensajes."""
    from app.core.database import AsyncSessionLocal
    from app.services import open_shift_alert

    last_alert = 0.0
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await send_reminders(db)
                if time.monotonic() - last_alert >= open_shift_alert.LOOP_SECONDS:
                    last_alert = time.monotonic()
                    await open_shift_alert.run_all(db)
        except Exception as exc:  # nunca tumba el servidor
            log.warning("Recordatorios del bot no pudieron correr: %s", type(exc).__name__)
        await asyncio.sleep(LOOP_SECONDS)


def start_loop() -> None:
    asyncio.get_event_loop().create_task(loop())
