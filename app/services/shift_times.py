"""Tiempos de un turno: UNA sola definicion para el CRM VELVET-LAB, la nomina y el bot.

- Conectado = desde el inicio del turno hasta su cierre (o hasta ahora si sigue abierto).
- Pausas    = suma de todas las pausas dentro del turno (la pausa abierta cuenta hasta ahora).
- Trabajado = conectado - pausas. Es el tiempo real.

Solo lectura y presentacion: el calculo del pago de la nomina no pasa por aqui.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

Break = tuple[datetime, Optional[datetime]]


def _overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> int:
    lo, hi = max(a_start, b_start), min(a_end, b_end)
    return max(0, int((hi - lo).total_seconds()))


def pause_seconds_between(start: datetime, end: datetime, breaks: Iterable[Break], now: datetime) -> int:
    """Segundos de pausa dentro de [start, end]; una pausa sin fin corre hasta `now`."""
    if end <= start:
        return 0
    return sum(_overlap(start, end, b_start, b_end or now) for b_start, b_end in breaks if b_start)


def worked_seconds_between(start: datetime, end: datetime, breaks: Iterable[Break], now: datetime) -> int:
    """Tiempo trabajado en [start, end] = duracion - pausas dentro de ese rango."""
    if end <= start:
        return 0
    return max(0, int((end - start).total_seconds()) - pause_seconds_between(start, end, breaks, now))


def shift_times(start: datetime, breaks: Iterable[Break], *, end: Optional[datetime] = None, now: datetime) -> dict:
    """Conectado, pausas y trabajado (en segundos) de un turno."""
    breaks = list(breaks)
    finish = end or now
    connected = max(0, int((finish - start).total_seconds()))
    pause = pause_seconds_between(start, finish, breaks, now)
    return {"connected_seconds": connected, "pause_seconds": pause, "worked_seconds": max(0, connected - pause)}


def shift_minutes(start: datetime, end: datetime, pause_seconds: int) -> dict:
    """La misma definicion en minutos para un turno cerrado cuyas pausas ya estan sumadas."""
    connected = max(0, int((end - start).total_seconds()))
    pause = min(connected, max(0, int(pause_seconds or 0)))
    connected_minutes, pause_minutes = round(connected / 60), round(pause / 60)
    # Las tres columnas siempre cuadran: trabajado = conectado - pausas (ya redondeados).
    return {"connected_minutes": connected_minutes, "pause_minutes": pause_minutes,
            "worked_minutes": max(0, connected_minutes - pause_minutes)}
