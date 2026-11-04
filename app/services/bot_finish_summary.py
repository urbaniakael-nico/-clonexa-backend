"""Bot de Telegram: Finalizar turno sin bucles (interruptor bot_finish_summary, 068A).

Interruptor por empresa ``bot_finish_summary`` (settings del modulo workforce; necesita
bot_punch_gps), apagado por defecto. Hoy solo VOLTAGE. Encendido:
- Mientras el bot espera el resumen, tocar Finalizar u otro boton (o mandar otra ubicacion)
  no reinicia nada: responde que falta el resumen, en el idioma de la persona.
- Sin resumen en 30 minutos: el turno se cierra con la hora de la ubicacion de Finalizar,
  nota "Sin resumen", auditoria en shift_manual_closes (la misma lista de los cierres del
  portal) y aviso por el bot. Solo los pendientes creados con el interruptor encendido
  llevan ``auto_close_at``; uno anterior nunca se cierra solo.
- Si el lider o el portal cerraron el turno mientras tanto, el pendiente se descarta.
Apagado: todo exactamente igual que antes.

La hora de salida con ubicacion (exit_time) NO depende de este interruptor: la usa toda
marcacion de Finalizar que traiga la ubicacion de ese momento (bot_punch_gps).
Toda consulta filtra por company_id.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("clonexa.bot_finish_summary")

KEY = "bot_finish_summary"
MODULE = "workforce"
PENDING_ACTION = "end_shift_summary"
AUTO_CLOSE_MINUTES = 30
NOTE = "Sin resumen"
CHANNEL = "bot_sin_resumen"
LABEL = "Turno cerrado sin resumen"
ACTOR = "Bot (sin resumen en 30 min)"
BATCH = 200


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


async def companies_on(db: AsyncSession) -> dict[str, str]:
    """{company_id: nombre} de las empresas con el interruptor."""
    rows = (await db.execute(text("""
        SELECT cm.company_id::text, COALESCE(c.name, '')
        FROM company_modules cm JOIN modules m ON m.id = cm.module_id JOIN companies c ON c.id = cm.company_id
        WHERE lower(m.code) = :m AND COALESCE(cm.enabled, true) IS TRUE AND (cm.settings::jsonb ->> :k) = 'true'
    """), {"m": MODULE, "k": KEY})).all()
    return {str(r[0]): str(r[1]) for r in rows}


# ------------------------------------------------------------ horas
def parse_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def exit_time(punch_location: Any, last_event_at: Any = None) -> datetime | None:
    """Hora de salida: la de la ubicacion de Finalizar, no la del resumen. Nunca antes de la
    ultima marcacion del turno (el panel del lider pudo marcar algo despues). None sin ubicacion."""
    located = parse_at(punch_location.get("located_at")) if isinstance(punch_location, dict) else None
    if located is None:
        return None
    last = parse_at(last_event_at)
    return max(located, last) if last is not None else located


def auto_close_at(punch_location: Any, now_utc: datetime | None = None) -> str:
    start = exit_time(punch_location) or now_utc or datetime.now(timezone.utc)
    return (start + timedelta(minutes=AUTO_CLOSE_MINUTES)).isoformat()


# ------------------------------------------------------------ cierre sin resumen
def _payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


async def due(db: AsyncSession, company_id: Any, now_utc: datetime) -> list[dict[str, Any]]:
    """Pendientes con el plazo vencido. Sin mirar expires_at: si el ciclo estuvo caido mas de lo
    que dura el pendiente, igual se cierran con su hora."""
    rows = (await db.execute(text("""
        SELECT id::text AS id, telegram_user_id, employee_id::text AS employee_id, payload_json
        FROM company_telegram_pending_actions
        WHERE company_id = CAST(:c AS uuid) AND action = :a AND payload_json ? 'auto_close_at'
          AND (payload_json ->> 'auto_close_at')::timestamptz <= :now
        ORDER BY updated_at
        LIMIT :l
    """), {"c": str(company_id), "a": PENDING_ACTION, "now": now_utc, "l": BATCH})).mappings().all()
    return [{**dict(r), "payload_json": _payload(r["payload_json"])} for r in rows]


async def _discard(db: AsyncSession, company_id: Any, row_id: str) -> bool:
    """Toma el pendiente (atomico). False si ya no estaba: la persona escribio el resumen."""
    taken = (await db.execute(text("""
        DELETE FROM company_telegram_pending_actions
        WHERE company_id = CAST(:c AS uuid) AND id = CAST(:i AS uuid) AND action = :a
        RETURNING id
    """), {"c": str(company_id), "i": row_id, "a": PENDING_ACTION})).first()
    return taken is not None


async def close_one(db: AsyncSession, company_id: Any, row: dict[str, Any], now_utc: datetime) -> dict[str, Any] | None:
    """Cierra UN turno vencido. Devuelve lo que hay que avisar, o None si no hubo cierre."""
    from app.services import open_shift_alert

    if not await _discard(db, company_id, row["id"]):
        await db.commit()
        return None
    employee_id = row.get("employee_id")
    shift = next((s for s in await open_shift_alert.open_shifts(db, company_id, now_utc=now_utc) if s["employee_id"] == employee_id), None)
    if shift is None:  # el lider o el portal ya lo cerraron: nada que cerrar
        await db.commit()
        return None
    payload = row["payload_json"]
    punch = payload.get("punch_location") if isinstance(payload.get("punch_location"), dict) else {}
    last_event_at = (await db.execute(text("""
        SELECT last_event_at FROM workforce_attendance_status WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)
    """), {"c": str(company_id), "e": employee_id})).scalar()
    end_at = exit_time(punch, last_event_at) or (parse_at(payload.get("auto_close_at")) or now_utc) - timedelta(minutes=AUTO_CLOSE_MINUTES)
    origin = {"channel": CHANNEL, "label": LABEL, "source": "telegram", "latitude": punch.get("latitude"), "longitude": punch.get("longitude"),
              "payload": {"auto_closed": True, "reason": "sin_resumen", "args": NOTE, "punch_location": punch or None, "exit_from_location": True}}
    try:
        await open_shift_alert.close_shift(db, company_id, employee_id, {"end_at": end_at.isoformat(), "note": NOTE}, actor=ACTOR,
                                           actor_user_id=None, now_utc=now_utc, origin=origin)
    except open_shift_alert.Invalid as exc:
        # Datos raros (salida antes de la entrada): el pendiente no se reintenta para siempre; queda en el turno abierto.
        await db.rollback()
        log.warning("Turno sin resumen no se pudo cerrar (%s): %s", company_id, exc.message)
        await _discard(db, company_id, row["id"])
        await db.commit()
        return None
    return {"employee_id": employee_id, "telegram_user_id": row["telegram_user_id"], "chat_id": payload.get("chat_id") or row["telegram_user_id"],
            "language": payload.get("language") or "es", "end_at": end_at,
            "time_label": open_shift_alert.local_label(end_at, shift.get("tz"))}


async def run_company(db: AsyncSession, company_id: Any, *, notify: Callable[[dict[str, Any]], Awaitable[None]],
                      now_utc: datetime | None = None) -> int:
    """Cierra los turnos vencidos de UNA empresa, con el turno del chat (mismo candado de los
    mensajes): si la persona escribe el resumen en ese instante, gana quien llego primero."""
    from app.services import telegram_chat_queue

    now_utc = now_utc or datetime.now(timezone.utc)
    closed = 0
    for row in await due(db, company_id, now_utc):
        chat = row["payload_json"].get("chat_id") or row["telegram_user_id"]
        async with telegram_chat_queue.chat_turn(f"{company_id}:{chat}"):
            done = await close_one(db, company_id, row, now_utc)
        if done is None:
            continue
        closed += 1
        try:  # el turno ya quedo cerrado: un aviso que falla no lo deshace
            await notify(done)
        except Exception as exc:
            await db.rollback()
            log.warning("Aviso de turno sin resumen no se pudo enviar (%s): %s", company_id, type(exc).__name__)
    return closed


async def run_all(db: AsyncSession) -> int:
    from uuid import UUID

    from app.api.v1.endpoints import bots
    from app.services import bot_processing_alert, bot_punch_gps

    companies = await companies_on(db)
    bot_processing_alert.watch(companies)
    total = 0
    for cid in companies:
        try:
            token = await bot_punch_gps.bot_token(db, cid)

            async def notify(done: dict[str, Any], _cid: str = cid, _token: str | None = token) -> None:
                if not _token:
                    log.warning("Turno sin resumen cerrado sin aviso: la empresa %s no tiene token del bot", _cid)
                    return
                await bots.notify_no_summary_close_068A(db, company_id=UUID(_cid), token=_token, done=done)

            total += await run_company(db, cid, notify=notify)
        except Exception as exc:  # una empresa con datos raros no frena a las demas
            await db.rollback()
            log.warning("Cierre de turnos sin resumen fallo para %s: %s", cid, type(exc).__name__)
            await bot_processing_alert.observe(cid, kind="cierre sin resumen", seconds=0.0, error=type(exc).__name__)
    return total
