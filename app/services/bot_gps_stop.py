"""Bot de Telegram: GPS solo con turno abierto y moneda de la empresa (interruptor bot_gps_stop).

Interruptor por empresa ``bot_gps_stop`` (settings del modulo workforce; necesita
GPS). Encendido:
- Una ubicacion (en vivo o actual) sin turno abierto se descarta: no se guarda.
- "Turno finalizado" recuerda apagar la ubicacion en vivo, con boton
  "Apagar ubicacion" (Telegram no deja que un bot la apague: el boton da los pasos).
- Si despues del cierre siguen llegando ubicaciones en vivo: UN solo recordatorio
  por cierre (marcado con la hora de salida del estado de asistencia).
- El webhook recibe tambien edited_message (asi llegan las actualizaciones de la
  ubicacion en vivo); un texto editado se ignora, no repite la accion.
- Dinero en la moneda de la empresa ("$1.10 USD"); con COP, el texto de siempre.
  Sin la linea "Descuento del corte" cuando es 0.
Apagado: todo exactamente igual que antes.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

KEY = "bot_gps_stop"
MODULE = "workforce"
STOP_CALLBACK = "clx:gps:stop"
REMINDER_ACTION = "gps_stop_reminded"
LIVE_UPDATES = ["message", "edited_message", "callback_query"]
LEGACY_UPDATES = ["message", "callback_query"]


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


def allowed_updates(on: bool) -> list[str]:
    return list(LIVE_UPDATES if on else LEGACY_UPDATES)


def money(value: Any, currency: str | None, legacy: Callable[[Any], str]) -> str:
    """"$1.10 USD" en la moneda de la empresa; con COP (o sin moneda), el texto de siempre."""
    from app.services import company_locale

    cur = str(currency or company_locale.DEFAULT_CURRENCY).upper()
    if cur == "COP":
        return legacy(value)
    return f"{company_locale.money(value, cur)} {cur}"


def is_zero(value: Any) -> bool:
    from decimal import Decimal

    try:
        return Decimal(str(value if value is not None else 0)) == 0
    except Exception:
        return True


def close_marker(status: Any) -> str:
    """Identifica el cierre: la hora de salida del estado (o 'sin-salida')."""
    at = getattr(status, "check_out_at", None) if status is not None else None
    return at.isoformat() if hasattr(at, "isoformat") else "sin-salida"


async def claim_reminder(db: AsyncSession, company_id: Any, telegram_user_id: str, employee_id: Any, marker: str) -> bool:
    """True solo la primera vez para este cierre (atomico: dos ubicaciones a la vez no mandan dos)."""
    row = (await db.execute(text("""
        INSERT INTO company_telegram_pending_actions (company_id, telegram_user_id, employee_id, action, payload_json, updated_at)
        VALUES (CAST(:c AS uuid), :t, CAST(:e AS uuid), :a, CAST(:p AS jsonb), now())
        ON CONFLICT (company_id, telegram_user_id, action) DO UPDATE
           SET payload_json = EXCLUDED.payload_json, employee_id = EXCLUDED.employee_id, updated_at = now()
         WHERE company_telegram_pending_actions.payload_json->>'close' IS DISTINCT FROM EXCLUDED.payload_json->>'close'
        RETURNING id
    """), {"c": str(company_id), "t": str(telegram_user_id), "e": str(employee_id), "a": REMINDER_ACTION,
           "p": json.dumps({"close": marker})})).first()
    await db.commit()
    return row is not None


def edited_without_location(update: dict[str, Any]) -> bool:
    """Un texto editado (no una ubicacion en vivo) no debe repetir una accion."""
    edited = update.get("edited_message") if isinstance(update, dict) else None
    return isinstance(edited, dict) and not isinstance(edited.get("location"), dict)
