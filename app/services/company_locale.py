"""Moneda, zona horaria e idioma de una empresa: UNA sola fuente de verdad.

get_company_locale(db, company_id) -> {currency, timezone, language, decimals}
- Lee company_core_settings (lo que guarda Ajustes) con respaldo en
  companies.timezone y valores por defecto (COP, America/Bogota, es).
- Ajustes guarda aqui y sincroniza companies.timezone (corte diario, cierre del
  dia, confirmar salida y hospitality lo siguen leyendo de alli).
- Las empresas en pesos y hora de Bogota (todas las vivas hoy salvo VOLTAGE)
  obtienen exactamente los valores de siempre: los formateadores de abajo, con
  COP, devuelven el mismo texto que cada lugar ya escribia.
"""
from __future__ import annotations

import contextvars
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Any, Callable
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_CURRENCY = "COP"
DEFAULT_TIMEZONE = "America/Bogota"
DEFAULT_LANGUAGE = "es"
# Monedas permitidas en Ajustes y sus decimales: COP y CLP sin centavos.
CURRENCY_DECIMALS = {"COP": 0, "CLP": 0, "USD": 2, "EUR": 2, "MXN": 2, "PEN": 2}
LANGUAGES = ("es", "en", "fr")

# Zona de la empresa en curso (p. ej. dentro del calculo de nomina). Sin valor:
# Bogota, como siempre.
CURRENT_TZ: contextvars.ContextVar[ZoneInfo | None] = contextvars.ContextVar("company_tz", default=None)
# Moneda de la empresa en curso. Sin valor: COP (cada lugar escribe su formato de siempre).
CURRENT_CURRENCY: contextvars.ContextVar[str | None] = contextvars.ContextVar("company_currency", default=None)
# Idioma de la empresa en curso (PDF y mensajes que no son de una persona). Sin valor: es.
CURRENT_LANGUAGE: contextvars.ContextVar[str | None] = contextvars.ContextVar("company_language", default=None)


def use(locale: dict) -> tuple:
    """Fija zona y moneda de la empresa; devuelve los tokens para restaurarlas con reset()."""
    return (CURRENT_TZ.set(zone(locale.get("timezone"))), CURRENT_CURRENCY.set(locale.get("currency") or DEFAULT_CURRENCY),
            CURRENT_LANGUAGE.set(locale.get("language") or DEFAULT_LANGUAGE))


def reset(tokens: tuple) -> None:
    CURRENT_TZ.reset(tokens[0])
    CURRENT_CURRENCY.reset(tokens[1])
    if len(tokens) > 2:
        CURRENT_LANGUAGE.reset(tokens[2])


def current_language() -> str:
    return CURRENT_LANGUAGE.get() or DEFAULT_LANGUAGE


def money_here(value: Any, legacy: Callable[[Any], str]) -> str:
    """Dinero en la moneda de la empresa en curso; con COP, el formato de siempre (legacy)."""
    return money(value, CURRENT_CURRENCY.get() or DEFAULT_CURRENCY, legacy)


@lru_cache(maxsize=1)
def timezone_choices() -> tuple[str, ...]:
    """Zonas IANA validas para Ajustes (sin las de compatibilidad tipo 'US/...' o 'Etc/...')."""
    names = [n for n in available_timezones() if "/" in n and not n.startswith(("Etc/", "SystemV/", "US/", "posix/", "right/"))]
    return tuple(sorted(names))


def valid_timezone(name: Any) -> bool:
    return str(name or "") in set(timezone_choices())


def zone(name: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or DEFAULT_TIMEZONE))
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def current_zone() -> ZoneInfo:
    return CURRENT_TZ.get() or ZoneInfo(DEFAULT_TIMEZONE)


def normalize(currency: Any = None, tz: Any = None, language: Any = None) -> dict:
    cur = str(currency or DEFAULT_CURRENCY).strip().upper()
    if cur not in CURRENCY_DECIMALS:
        cur = DEFAULT_CURRENCY
    tzname = str(tz or "").strip()
    if not valid_timezone(tzname):
        tzname = DEFAULT_TIMEZONE
    lang = str(language or DEFAULT_LANGUAGE).strip().lower()
    if lang not in LANGUAGES:
        lang = DEFAULT_LANGUAGE
    return {"currency": cur, "timezone": tzname, "language": lang, "decimals": CURRENCY_DECIMALS[cur]}


async def get_company_locale(db: AsyncSession, company_id: Any) -> dict:
    """Nunca falla: si algo no esta o la consulta falla, los valores por defecto."""
    try:
        row = (await db.execute(text("""
            SELECT s.currency, s.timezone AS settings_tz, s.language, c.timezone AS company_tz
            FROM companies c
            LEFT JOIN company_core_settings s ON s.company_id = c.id
            WHERE c.id = CAST(:company_id AS uuid)
            LIMIT 1
        """), {"company_id": str(company_id)})).mappings().first()
    except Exception:
        row = None
    row = dict(row) if row else {}
    return normalize(row.get("currency"), row.get("settings_tz") or row.get("company_tz"), row.get("language"))


async def company_zone(db: AsyncSession, company_id: Any) -> ZoneInfo:
    return zone((await get_company_locale(db, company_id))["timezone"])


# ------------------------------------------------------------- formatos
def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal(0)


def group(value: Any, decimals: int, thousands: str, point: str) -> str:
    q = Decimal(1).scaleb(-decimals) if decimals else Decimal(1)
    number = _decimal(value).quantize(q, rounding=ROUND_HALF_UP)
    sign = "-" if number < 0 else ""
    text_value = f"{abs(number):,.{decimals}f}"
    whole, _, frac = text_value.partition(".")
    whole = whole.replace(",", thousands)
    return f"{sign}{whole}{point + frac if decimals else ''}"


def money(value: Any, currency: str = DEFAULT_CURRENCY, legacy: Callable[[Any], str] | None = None) -> str:
    """Dinero en la moneda de la empresa. Con COP (o sin moneda) y un formato de
    siempre (legacy), devuelve EXACTAMENTE ese texto: la regla de oro."""
    cur = str(currency or DEFAULT_CURRENCY).upper()
    if cur == "COP" and legacy is not None:
        return legacy(value)
    decimals = CURRENCY_DECIMALS.get(cur, 2)
    if cur in ("USD", "MXN"):
        return f"$ {group(value, decimals, ',', '.')}".replace("$ -", "-$ ").replace("$ ", "$")
    if cur == "EUR":
        return f"{group(value, decimals, '.', ',')} €"
    if cur == "PEN":
        return f"S/ {group(value, decimals, ',', '.')}"
    return f"$ {group(value, decimals, '.', ',')}"  # COP, CLP: "$ 1.234"


def parse_amount(raw: Any, currency: str = DEFAULT_CURRENCY) -> Decimal:
    """Lee una cifra escrita por una persona: '1.234,50' (COP) o '1,234.50' (USD) -> 1234.50."""
    text_value = "".join(ch for ch in str(raw or "") if ch.isdigit() or ch in ",.-")
    if not text_value:
        return Decimal(0)
    neg = text_value.startswith("-")
    text_value = text_value.replace("-", "")
    last_dot, last_comma = text_value.rfind("."), text_value.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        dec = "." if last_dot > last_comma else ","  # con los dos, el ultimo es el decimal
    elif last_dot >= 0 or last_comma >= 0:
        # Un solo tipo de separador. Repetido = miles ("1.234.567"). Una vez: es de
        # miles solo si le siguen 3 cifras y es el separador de miles de la moneda
        # (COP/CLP/EUR "1.234", USD/MXN/PEN "1,234"); si no, es decimal ("12.5", "14,5").
        sep = "." if last_dot >= 0 else ","
        group_sep = "," if str(currency or "").upper() in ("USD", "MXN", "PEN") else "."
        tail = text_value.rsplit(sep, 1)[1]
        if text_value.count(sep) > 1 or (len(tail) == 3 and sep == group_sep):
            dec = None
        else:
            dec = sep
    else:
        dec = None
    if dec:
        whole, _, frac = text_value.rpartition(dec)
        whole = whole.replace(".", "").replace(",", "")
        number = Decimal(f"{whole or '0'}.{frac or '0'}")
    else:
        number = Decimal(text_value.replace(".", "").replace(",", ""))
    return -number if neg else number


def local_now(tz: ZoneInfo | None = None) -> datetime:
    return datetime.now(timezone.utc).astimezone(tz or current_zone())
