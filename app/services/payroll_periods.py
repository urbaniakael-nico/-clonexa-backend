"""Periodos de nomina por dias de corte (049L).

Una empresa con fila en payroll_period_config (hoy solo VELVET) paga por
periodos definidos por sus dias de corte. Con cortes [10, 25]:
  - del 26 de un mes al 10 del mes siguiente (cierra el 10),
  - del 11 al 25 del mismo mes (cierra el 25).
El corte se procesa solo a las 00:01 del dia siguiente al cierre (11 y 26),
para que el ultimo dia entre completo, y cada turno pertenece al periodo en
el que EMPEZO (un turno que cruza la medianoche del corte no se parte).
Sin fila, la empresa sigue exactamente como antes.

Todo aqui es puro (fechas locales de la empresa) para poder probarlo solo.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Iterable

AUTO_CLOSE_TIME = time(0, 1)  # 00:01 del dia siguiente al cierre
MAX_CUTOFFS = 4

MONTHS_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MONTHS_LONG = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
               "octubre", "noviembre", "diciembre"]


def clean_cutoffs(days: Iterable) -> list[int]:
    """Dias de corte validos: 1 a 31, sin repetir, de 1 a 4 cortes al mes."""
    out: set[int] = set()
    for raw in days or []:
        try:
            day = int(str(raw).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("dia_de_corte_invalido") from exc
        if not 1 <= day <= 31:
            raise ValueError("dia_de_corte_invalido")
        out.add(day)
    if not 1 <= len(out) <= MAX_CUTOFFS:
        raise ValueError("cantidad_de_cortes_invalida")
    return sorted(out)


def _cutoff_in_month(year: int, month: int, day: int) -> date:
    # un corte el 31 en febrero cae el ultimo dia del mes
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _month_cutoffs(year: int, month: int, cutoffs: list[int]) -> list[date]:
    return sorted({_cutoff_in_month(year, month, day) for day in cutoffs})


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def period_for(reference: date, cutoffs: Iterable[int]) -> tuple[date, date]:
    """(inicio, cierre) del periodo que contiene `reference`: cierra en el
    primer corte >= reference y empieza el dia despues del corte anterior.
    Cruza mes y año sin casos especiales (26 dic -> 10 ene)."""
    days = clean_cutoffs(cutoffs)
    end = next((c for c in _month_cutoffs(reference.year, reference.month, days) if c >= reference), None)
    if end is None:
        year, month = _shift_month(reference.year, reference.month, 1)
        end = _month_cutoffs(year, month, days)[0]
    previous = [c for c in _month_cutoffs(end.year, end.month, days) if c < end]
    if not previous:
        year, month = _shift_month(end.year, end.month, -1)
        previous = _month_cutoffs(year, month, days)
    return previous[-1] + timedelta(days=1), end


def auto_close_at(period_end: date) -> datetime:
    """Momento (hora local) en que el periodo se procesa solo."""
    return datetime.combine(period_end + timedelta(days=1), AUTO_CLOSE_TIME)


def due_period(now_local: datetime, cutoffs: Iterable[int]) -> tuple[date, date]:
    """El ultimo periodo cuyo corte automatico ya llego (00:01 del dia
    siguiente al cierre)."""
    start, end = period_for(now_local.date() - timedelta(days=1), cutoffs)
    if auto_close_at(end) > now_local.replace(tzinfo=None):
        start, end = period_for(start - timedelta(days=1), cutoffs)
    return start, end


def _short(day: date, with_year: bool) -> str:
    return f"{day.day} {MONTHS_SHORT[day.month - 1]}" + (f" {day.year}" if with_year else "")


def period_label(start: date, end: date) -> str:
    """"Periodo del 26 sep al 10 oct" (con el año si cruza de año)."""
    cross = start.year != end.year
    return f"Periodo del {_short(start, cross)} al {_short(end, cross)}"


def closes_label(end: date, today: date) -> str:
    verb = "cerró" if end < today else "cierra"
    return f"{verb} el {end.day} de {MONTHS_LONG[end.month - 1]}"


def auto_close_label(end: date) -> str:
    moment = auto_close_at(end)
    return f"el corte se procesa solo el {moment.day} de {MONTHS_LONG[moment.month - 1]} a las 00:01"


def describe(start: date, end: date, today: date) -> dict:
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "label": period_label(start, end),
        "closes_label": closes_label(end, today),
        "auto_close_at": auto_close_at(end).isoformat(),
        "auto_close_label": auto_close_label(end),
        "headline": f"{period_label(start, end)} · {closes_label(end, today)}",
    }
