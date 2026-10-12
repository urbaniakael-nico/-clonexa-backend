"""Fase B · moneda y zona unicas (bloque 4): Shoplink y Hospitality leen Ajustes
(company_locale) cuando el modulo no guardo un valor propio. Hoy ninguna
empresa tiene zona propia en los modulos y la unica tienda con moneda propia
(PREMIUM SHOPPERCO.) guarda COP: lo guardado se respeta tal cual."""
from __future__ import annotations

from datetime import datetime, timezone

from app.api.v1.endpoints import shoplink, waiter_ordering
from app.services import company_locale as cl


def test_shoplink_default_currency_comes_from_settings():
    assert shoplink._settings_defaults({"name": "X"})["currency"] == "COP", "sin empresa en curso: COP como siempre"
    tokens = cl.use({"currency": "USD", "timezone": "America/Chicago", "language": "en"})
    try:
        assert shoplink._settings_defaults({"name": "X"})["currency"] == "USD"
    finally:
        cl.reset(tokens)


def test_waiter_today_starts_at_company_midnight():
    start_bog = waiter_ordering._local_day_start({})
    assert start_bog.astimezone(cl.zone("America/Bogota")).hour == 0
    tokens = cl.use({"currency": "USD", "timezone": "America/Chicago"})
    try:
        start_chi = waiter_ordering._local_day_start({})
        stored = waiter_ordering._local_day_start({"timezone": "America/Bogota"})
    finally:
        cl.reset(tokens)
    assert start_chi.astimezone(cl.zone("America/Chicago")).hour == 0
    assert stored.astimezone(cl.zone("America/Bogota")).hour == 0, "una zona guardada en el modulo se respeta"
    assert start_chi.tzinfo is not None and start_chi <= datetime.now(timezone.utc)


def test_company_language_rides_with_currency_and_zone():
    assert cl.current_language() == "es"
    tokens = cl.use({"currency": "EUR", "timezone": "Europe/Paris", "language": "fr"})
    try:
        assert cl.current_language() == "fr"
    finally:
        cl.reset(tokens)
    assert cl.current_language() == "es"
