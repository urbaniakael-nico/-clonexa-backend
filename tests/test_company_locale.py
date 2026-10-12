"""Fase A · moneda, zona horaria e idioma de la empresa (una sola fuente).

- Regla de oro: con COP los formateadores devuelven EXACTAMENTE el texto de siempre.
- USD con centavos ("$1,234.50"); COP "$ 1.234".
- Lector de cifras: "1.234,50" en COP y "1,234.50" en USD -> 1234.5; los
  formatos de siempre en COP ("29.000", "12.5", "14,5") dan lo mismo que antes.
- core-settings exige sesion SIEMPRE (401 sin sesion, 403 otra empresa) y solo
  el dueño o admin guarda; la zona se valida contra la lista IANA y se copia a
  companies.timezone.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.api.v1.endpoints import bots, carta, core_settings, hospitality, mini_panel_quotes, transport_quotes_tickets
from app.services import company_locale as cl
from app.services import company_tz_middleware as mw
from app.services import owner_report, whatsapp_delivery
from app.web import admin_v2plus_companies as ep

CID = str(uuid.uuid4())


# ------------------------------------------------------------- formatos
def test_money_formats_by_currency():
    assert cl.money(1234.5, "USD") == "$1,234.50"
    assert cl.money(-1234.5, "USD") == "-$1,234.50"
    assert cl.money(1234.5, "COP") == "$ 1.235"
    assert cl.money(1234.5, "CLP") == "$ 1.235"
    assert cl.money(1234.5, "EUR") == "1.234,50 €"
    assert cl.money(1234.5, "PEN") == "S/ 1,234.50"
    assert cl.money(1234, "COP", legacy=lambda v: "SIEMPRE") == "SIEMPRE", "con COP manda el formato de siempre"


@pytest.mark.parametrize("fn,legacy", [
    (bots._money_label, bots._money_label_cop), (hospitality._hsp_money_text, hospitality._hsp_money_text_cop),
    (owner_report.money_text, owner_report.money_text_cop), (carta._cop, carta._cop_cop),
    (mini_panel_quotes._format_cop, mini_panel_quotes._format_cop_cop),
    (transport_quotes_tickets._format_money, transport_quotes_tickets._format_money_cop),
    (whatsapp_delivery.money, whatsapp_delivery.money_cop),
])
def test_backend_money_is_unchanged_with_cop_and_follows_usd(fn, legacy):
    for value in (0, 15.59, 1234, 1120000, Decimal("2536000.00")):
        assert fn(value) == legacy(value), "sin empresa (COP): texto de siempre"
        tokens = cl.use({"currency": "COP", "timezone": "America/Bogota"})
        try:
            assert fn(value) == legacy(value), "empresa en COP: texto de siempre"
        finally:
            cl.reset(tokens)
    tokens = cl.use({"currency": "USD", "timezone": "America/Chicago"})
    try:
        assert fn(1234.5) == "$1,234.50"
    finally:
        cl.reset(tokens)


@pytest.mark.parametrize("raw,currency,expected", [
    ("1.234,50", "COP", Decimal("1234.50")), ("1,234.50", "USD", Decimal("1234.50")),
    ("1,234.50", "COP", Decimal("1234.50")), ("1.234,50", "USD", Decimal("1234.50")),
    ("29.000", "COP", Decimal("29000")), ("1.120.000", "COP", Decimal("1120000")), ("12.5", "COP", Decimal("12.5")),
    ("14,5", "COP", Decimal("14.5")), ("$ 1.234", "COP", Decimal("1234")), ("1,234", "USD", Decimal("1234")),
    ("1.5", "USD", Decimal("1.5")), ("-2.000", "COP", Decimal("-2000")), ("", "COP", Decimal("0")),
])
def test_parse_amount(raw, currency, expected):
    assert cl.parse_amount(raw, currency) == expected


def test_timezones_and_defaults():
    assert cl.valid_timezone("America/Chicago") and cl.valid_timezone("America/Bogota")
    assert not cl.valid_timezone("Bogota") and not cl.valid_timezone("US/Central") and not cl.valid_timezone("")
    assert cl.normalize(None, None, None) == {"currency": "COP", "timezone": "America/Bogota", "language": "es", "decimals": 0}
    assert cl.normalize("usd", "America/Chicago", "en") == {"currency": "USD", "timezone": "America/Chicago", "language": "en", "decimals": 2}
    assert cl.normalize("XXX", "Mars/Base", "zz")["currency"] == "COP"
    assert cl.current_zone().key == "America/Bogota", "sin empresa: Bogota"


def test_middleware_finds_the_company_of_the_request():
    assert mw.company_id_of(f"/api/v1/payroll/companies/{CID}/periods/calculate", b"") == CID
    assert mw.company_id_of("/api/v1/employees", f"company_id={CID}&x=1".encode()) == CID
    assert mw.company_id_of("/api/v1/health", b"") is None


# ------------------------------------------------------------ seguridad
@pytest.fixture
def client(monkeypatch):
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(c=TestClient(app_main.app), mp=monkeypatch, db=db)
    app_main.app.dependency_overrides.pop(get_db, None)


def test_core_settings_requires_a_session_always(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    client.mp.setattr(core_settings, "require_enabled_module", AsyncMock(side_effect=HTTPException(status_code=403)), raising=False)
    from app.api.v1.endpoints import company_users
    client.mp.setattr(company_users, "require_enabled_module", AsyncMock(side_effect=HTTPException(status_code=403)))
    url = f"/api/v1/companies/{CID}/core-settings"
    assert client.c.get(url).status_code == 401, "sin sesion"
    assert client.c.put(url, json={"currency": "COP"}).status_code == 401
    assert client.c.get(f"/api/v1/companies/{CID}/locale").status_code == 401
    client.mp.setattr(core_settings, "require_company_user_for_tenant", AsyncMock(side_effect=HTTPException(status_code=403, detail="tenant_not_allowed")))
    assert client.c.get(url, headers={"Authorization": "Bearer otra"}).status_code == 403, "usuario de otra empresa"


@pytest.mark.asyncio
async def test_only_owner_or_admin_saves():
    await core_settings.require_settings_writer({"admin_v2": True, "role": "admin_v2"})
    await core_settings.require_settings_writer({"admin_v2": False, "role": "company_admin"})
    await core_settings.require_settings_writer({"admin_v2": False, "role": "dueno"})
    for role in ("operator", "mesero", "caja", "administrador", "viewer"):
        with pytest.raises(HTTPException) as err:
            await core_settings.require_settings_writer({"admin_v2": False, "role": role})
        assert err.value.status_code == 403


def test_timezone_must_come_from_the_iana_list():
    assert core_settings._normalize_timezone("America/Chicago") == "America/Chicago"
    assert core_settings._normalize_timezone("") is None
    with pytest.raises(HTTPException) as err:
        core_settings._normalize_timezone("hora de Bogota")
    assert err.value.status_code == 400


def test_report_days_cut_at_local_midnight_for_every_company():
    """Fase B (bloque 6, cambio pedido): Reportes y KPIs cortan el dia a la medianoche
    de la zona de la empresa; Bogota tambien (antes cortaba en UTC, 7 pm local)."""
    from datetime import date

    from app.api.v1.endpoints import kpis, reports

    for module in (kpis, reports):
        fn = module.period_from_params if module is kpis else module.parse_period
        start, end, _ = fn("custom", date(2026, 11, 2), date(2026, 11, 2))
        assert start.utcoffset().total_seconds() == -5 * 3600 and start.hour == 0, "sin empresa / Bogota: medianoche de Bogota"
        assert end.utcoffset().total_seconds() == -5 * 3600 and (end.hour, end.minute) == (23, 59)
        tokens = cl.use({"currency": "USD", "timezone": "America/Chicago"})
        try:
            start, end, _ = fn("custom", date(2026, 11, 2), date(2026, 11, 2))
        finally:
            cl.reset(tokens)
        assert start.utcoffset().total_seconds() == -6 * 3600 and start.hour == 0, "medianoche de Chicago (CST)"
