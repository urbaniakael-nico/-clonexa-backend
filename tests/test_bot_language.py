"""Fase B · bot de Telegram: idioma de cada colaborador.

- Sin eleccion manual: el idioma de SU celular (language_code de Telegram; es,
  en o fr; cualquier otro -> espanol).
- Con eleccion manual: se respeta. "Auto" la borra y vuelve al celular.
- Nomina por mensaje: en espanol exactamente el texto de siempre; en ingles
  traducida; dinero en la moneda de la empresa.
"""
from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import bots
from app.services import company_locale as cl


def update(code, callback=False):
    who = {"id": 7, "language_code": code}
    if callback:
        return {"callback_query": {"from": who, "data": "x", "id": "1", "message": {"chat": {"id": 7}}}}
    return {"message": {"from": who, "chat": {"id": 7}, "text": "hola"}}


def test_phone_language_from_telegram():
    assert bots._phone_language_052D(update("en-US")) == "en"
    assert bots._phone_language_052D(update("es")) == "es"
    assert bots._phone_language_052D(update("fr", callback=True)) == "fr"
    assert bots._phone_language_052D(update("pt-BR")) == "es", "otro idioma -> espanol"
    assert bots._phone_language_052D({"message": {"from": {}}}) == "es"


class Db:
    def __init__(self, stored):
        self.stored = stored
        self.sql = []

    async def execute(self, statement, params=None):
        self.sql.append(str(statement))
        row = {"language": self.stored} if self.stored else None
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row), first=lambda: row)

    async def commit(self):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("stored,phone,expected", [(None, "en", "en"), (None, "es", "es"), ("es", "en", "es"), ("fr", "es", "fr"), (None, None, "es")])
async def test_manual_choice_wins_over_phone(monkeypatch, stored, phone, expected):
    monkeypatch.setattr(bots, "ensure_bot_storage", AsyncMock())
    token = bots.PHONE_LANGUAGE_052D.set(phone)
    try:
        assert await bots._get_user_language(Db(stored), uuid.uuid4(), "7") == expected
    finally:
        bots.PHONE_LANGUAGE_052D.reset(token)


@pytest.mark.asyncio
async def test_auto_clears_the_manual_choice(monkeypatch):
    monkeypatch.setattr(bots, "ensure_bot_storage", AsyncMock())
    db = Db("fr")
    await bots._clear_user_language_052D(db, uuid.uuid4(), "7")
    assert any("DELETE FROM company_telegram_user_preferences" in s for s in db.sql)
    assert {"callback_data": "clx:lang:auto", "text": "🌐 Auto"} in bots._language_keyboard()["inline_keyboard"][1]


ROW = {"employee_name": "Ana", "closed_shifts": 2, "regular_minutes": 960, "extra_minutes": 60, "gross_amount": 400000, "discount_amount": 10000, "net_amount": 390000}


def test_payroll_message_spanish_is_unchanged_and_english_is_translated():
    old_es = "\n".join([
        "Nomina individual 2026-10-01 / 2026-10-15:", "Ana", "Turnos/sesiones: 2", "Tiempo del periodo: 17h 0m",
        "Ordinarias: 16h 0m", "Extras: 1h 0m", "Bruto: $ 400.000", "Descuentos: $ 10.000", "Total a pagar: $ 390.000",
    ])
    assert bots._format_payroll_row(ROW, date(2026, 10, 1), date(2026, 10, 15)) == old_es, "en espanol (COP) el texto de siempre"
    tokens = cl.use({"currency": "USD", "timezone": "America/Chicago", "language": "en"})
    try:
        text_en = bots._format_payroll_row(ROW, date(2026, 10, 1), date(2026, 10, 15))
    finally:
        cl.reset(tokens)
    assert text_en.splitlines()[0] == "Individual payroll 2026-10-01 / 2026-10-15:"
    assert "Total to pay: $390,000.00" in text_en and "Overtime: 1h 0m" in text_en
