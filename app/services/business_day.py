"""Jornada de negocio de una empresa: UNA sola regla para todo el sistema.

companies.settings_json.hospitality_business_day = {"open": "18:00", "close": "04:00"}
(048C). Con jornada nocturna (cierre antes de la apertura) el dia de negocio
termina a la hora de cierre: una venta a las 02:00 del 12/10 es del 11/10.
Sin jornada (o con jornada de un solo dia, p. ej. 08:00-22:00) el dia termina
a medianoche en la zona de la empresa.

La usan Hospitality (reportes, analitica, reporte del dueno), el libro de
ventas (sales_ledger), Reportes, KPIs y los filtros de dias del portal (que la
reciben en /companies/{id}/locale).
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

SETTING = "hospitality_business_day"


def parse_clock(value: Any) -> time | None:
    raw = str(value or "").strip()
    try:
        hours, minutes = raw.split(":")[:2]
        return time(int(hours), int(minutes))
    except Exception:
        return None


def config(settings: Any) -> dict[str, Any] | None:
    """La jornada configurada en settings_json de la empresa, o None si no hay."""
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except Exception:
            settings = {}
    raw = settings.get(SETTING) if isinstance(settings, dict) else None
    if not isinstance(raw, dict) or raw.get("enabled") is False:
        return None
    opens, closes = parse_clock(raw.get("open")), parse_clock(raw.get("close"))
    if not opens or not closes or opens == closes:
        return None
    return {
        "open": opens, "close": closes,
        "open_text": opens.strftime("%H:%M"), "close_text": closes.strftime("%H:%M"),
        "overnight": closes < opens,
    }


def overnight_close(cfg: dict[str, Any] | None) -> time | None:
    """Hora en que termina el dia de negocio, solo si la jornada cruza la medianoche."""
    return cfg["close"] if cfg and cfg.get("overnight") else None


def business_date(moment: datetime, tz: ZoneInfo, cfg: dict[str, Any] | None = None) -> date:
    """Dia de negocio de un momento (aware) en la zona tz."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(tz)
    close = overnight_close(cfg)
    if close is not None and local.time() < close:
        return local.date() - timedelta(days=1)
    return local.date()


def day_start(day: date, tz: ZoneInfo, cfg: dict[str, Any] | None = None) -> datetime:
    """Inicio del dia de negocio `day` (aware, en tz): medianoche, o la hora de
    cierre de la jornada nocturna."""
    return datetime.combine(day, overnight_close(cfg) or time.min, tzinfo=tz)


def day_end(day: date, tz: ZoneInfo, cfg: dict[str, Any] | None = None) -> datetime:
    """Ultimo instante del dia de negocio `day` (aware, en tz)."""
    return day_start(day + timedelta(days=1), tz, cfg) - timedelta(microseconds=1)


def public(cfg: dict[str, Any] | None) -> dict[str, Any] | None:
    """Forma serializable para el portal (CxLocale)."""
    if not cfg:
        return None
    return {"open": cfg["open_text"], "close": cfg["close_text"], "overnight": bool(cfg["overnight"])}
