"""Cierre automatico de sesiones sin actividad (TODAS las empresas).

Una fila de clonexa_access_sessions con status 'active' cuyo last_seen_at
tiene mas de N horas pasa a 'closed' con closed_reason
'expirada_por_inactividad'. Nadie que este trabajando la pierde: cada peticion
con sesion valida mueve last_seen_at (validate_access_session) y el token
vence mucho antes (8 h). Ver docs/sesiones_viejas.md.

- Interruptor: CLONEXA_SESSION_IDLE_HOURS. Vacio, 0 o invalido = apagado.
  Nunca menos de MIN_HOURS (la vida del token), para no cortar una sesion que
  todavia sirve.
- Corre dentro del ciclo del corte diario (session_cutoff.cutoff_loop), con
  su candado de una sola replica, como mucho una vez por hora.
- Solo toca filas de sesion: no cierra turnos, asistencia ni nada operativo.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("clonexa.session_idle")
ENV = "CLONEXA_SESSION_IDLE_HOURS"
REASON = "expirada_por_inactividad"
MIN_HOURS = 8
RUN_EVERY_SECONDS = 60 * 60


def idle_hours() -> int | None:
    """Horas configuradas, o None si esta apagado."""
    raw = os.getenv(ENV, "").strip()
    try:
        hours = int(float(raw)) if raw else 0
    except ValueError:
        log.warning("%s=%r no es un numero: cierre automatico apagado.", ENV, raw)
        return None
    if hours <= 0:
        return None
    return max(MIN_HOURS, hours)


async def preview_idle_sessions(db: AsyncSession, hours: int, now: datetime | None = None) -> list[dict]:
    """Cuantas cerraria, por empresa y alcance (solo lectura)."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=hours)
    rows = (await db.execute(text("""
        SELECT company_id::text AS company_id, scope, COUNT(*) AS sessions
        FROM clonexa_access_sessions
        WHERE status = 'active' AND last_seen_at < :cutoff
        GROUP BY company_id, scope
        ORDER BY COUNT(*) DESC
    """), {"cutoff": cutoff})).mappings().all()
    return [{"company_id": r["company_id"], "scope": r["scope"], "sessions": int(r["sessions"] or 0)} for r in rows]


async def close_idle_sessions(db: AsyncSession, hours: int, now: datetime | None = None) -> int:
    """Cierra las sesiones activas sin actividad en `hours` horas. Devuelve cuantas."""
    now = now or datetime.now(timezone.utc)
    result = await db.execute(text("""
        UPDATE clonexa_access_sessions
           SET status = 'closed', closed_at = :now, closed_reason = :reason
         WHERE status = 'active' AND last_seen_at < :cutoff
    """), {"now": now, "reason": REASON, "cutoff": now - timedelta(hours=hours)})
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


_last_run: datetime | None = None


async def maybe_close_idle_sessions(db: AsyncSession, now: datetime | None = None) -> int | None:
    """Paso del ciclo del corte diario: corre si esta encendido y paso una hora."""
    global _last_run
    hours = idle_hours()
    if hours is None:
        return None
    now = now or datetime.now(timezone.utc)
    if _last_run is not None and (now - _last_run).total_seconds() < RUN_EVERY_SECONDS:
        return None
    _last_run = now
    closed = await close_idle_sessions(db, hours, now)
    if closed:
        log.info("Sesiones sin actividad cerradas (%s h): %s", hours, closed)
    return closed
