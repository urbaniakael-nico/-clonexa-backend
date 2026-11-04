"""Aviso al Telegram del dueno cuando el bot se atrasa o falla (con bot_finish_summary, 068A).

- Lento: un update de Telegram tarda mas de 5 s desde que se acepta hasta que termina (incluye
  la espera de su turno en el chat y las respuestas a Telegram).
- Error: un update falla despues de los reintentos, o falla el cierre de turnos sin resumen.
- Maximo UN aviso cada 15 minutos en total; lo que pase mientras tanto se cuenta y sale en el
  siguiente aviso. Siempre queda en el log.
- Solo mira las empresas con el interruptor (hoy VOLTAGE). Sale por el mismo camino de los avisos
  de Nexa (n8n -> Telegram del dueno): sin token de Telegram aqui.
- Sin datos de personas: empresa, tipo de update, segundos y tipo de error. Nunca levanta.
"""
from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("clonexa.bot_processing_alert")

SLOW_SECONDS = 5.0
EVERY_SECONDS = 15 * 60.0
RETRY_SECONDS = 60.0  # si el aviso no se pudo entregar

STATE: dict[str, Any] = {"last": None, "slow": 0, "errors": 0, "max": 0.0}
_WATCHED: dict[str, str] = {}


def watch(companies: dict[str, str]) -> None:
    """Las empresas con el interruptor; el ciclo del bot lo refresca cada 30 s."""
    _WATCHED.clear()
    _WATCHED.update({str(k): str(v) for k, v in companies.items()})


def reset() -> None:
    """Solo pruebas."""
    _WATCHED.clear()
    STATE.update({"last": None, "slow": 0, "errors": 0, "max": 0.0})


async def _deliver(message: str) -> bool:
    from app.services import nexa_whatsapp

    return await nexa_whatsapp._deliver_alert(message)


async def observe(company_id: Any, *, kind: str, seconds: float, error: str | None = None, at: float | None = None) -> bool:
    """Cada update procesado pasa por aqui. True si salio un aviso a Telegram."""
    try:
        name = _WATCHED.get(str(company_id))
        if name is None or (error is None and seconds <= SLOW_SECONDS):
            return False
        what = f"error {error}" if error else f"procesamiento lento: {seconds:.1f} s"
        log.warning("Bot de %s: %s (%s)", name, what, kind)
        STATE["errors" if error else "slow"] += 1
        STATE["max"] = max(STATE["max"], seconds)
        at = time.monotonic() if at is None else at
        last = STATE["last"]
        if last is not None and at - last < EVERY_SECONDS:
            return False
        STATE["last"] = at
        slow, errors, longest = STATE["slow"], STATE["errors"], STATE["max"]
        STATE.update({"slow": 0, "errors": 0, "max": 0.0})
        lines = [f"⚠️ Bot de Telegram ({name}): {what} ({kind}).",
                 f"Desde el último aviso: {slow} lentos, {errors} con error; máximo {longest:.1f} s.",
                 "Revisa los logs de Railway (clonexa.bot_processing_alert)."]
        ok = await _deliver("\n".join(lines))
        if not ok:
            STATE["last"] = at - EVERY_SECONDS + RETRY_SECONDS
            log.error("El aviso del bot no se pudo entregar a Telegram")
        return ok
    except Exception as exc:  # el aviso nunca tumba el bot
        log.error("Aviso del bot fallo (%s)", type(exc).__name__)
        return False
