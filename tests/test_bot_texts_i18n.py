"""Todos los textos del bot de campo en el idioma de la persona: ningun texto falta en un idioma,
ninguno se cae a otro y ninguna respuesta queda fija en el codigo."""
from __future__ import annotations

import ast
import re
import string
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import bots, company_bots_v1
from app.services import bot_punch_gps, lider_pin, open_shift_alert, shifts, us_payroll

ROOT = Path(__file__).resolve().parents[1]
BOTS_SOURCE = (ROOT / "app" / "api" / "v1" / "endpoints" / "bots.py").read_text(encoding="utf-8")
LANGUAGES = {"es", "en", "fr"}


def fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_bot_texts_exist_in_all_languages_with_the_same_placeholders():
    assert set(bots.BOT_TEXTS) == LANGUAGES == bots.SUPPORTED_LANGUAGES
    spanish = bots.BOT_TEXTS["es"]
    for language in ("en", "fr"):
        assert set(bots.BOT_TEXTS[language]) == set(spanish), f"textos que faltan o sobran en {language}"
        for key, template in spanish.items():
            assert fields(bots.BOT_TEXTS[language][key]) == fields(template), f"{language}.{key}"


def test_every_text_the_code_asks_for_exists():
    """_txt(lang, "clave") con una clave que no existe le mandaria la clave a la persona."""
    used = set(re.findall(r'_txt\(\s*[^,()]+,\s*"([A-Za-z0-9_]+)"', BOTS_SOURCE)) | set(re.findall(r"_txt\(\s*[^,()]+,\s*'([A-Za-z0-9_]+)'", BOTS_SOURCE))
    assert used, "la busqueda encontro las claves"
    assert not used - set(bots.BOT_TEXTS["es"])


def test_no_reply_is_hard_coded_in_the_field_bot():
    """El tercer argumento de _send_telegram_message nunca es un texto fijo."""
    offenders = []
    for node in ast.walk(ast.parse(BOTS_SOURCE)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_send_telegram_message" and len(node.args) >= 3):
            continue
        arg = node.args[2]
        literal = arg.value if isinstance(arg, ast.Constant) else "".join(
            v.value for v in arg.values if isinstance(v, ast.Constant)) if isinstance(arg, ast.JoinedStr) else ""
        if str(literal).strip():
            offenders.append((node.lineno, str(literal)[:50]))
    assert offenders == []


@pytest.mark.parametrize("texts,name", [
    (bot_punch_gps.TEXTS, "bot_punch_gps"),
    (open_shift_alert.TEXTS, "open_shift_alert"),
    (us_payroll.BOT_TEXTS, "us_payroll"),
    (shifts.SHIFT_TEXT, "shifts"),
])
def test_service_texts_cover_all_languages(texts, name):
    assert set(texts) == LANGUAGES, name
    for language in ("en", "fr"):
        assert set(texts[language]) == set(texts["es"]), f"{name}.{language}"
        for key, template in texts["es"].items():
            assert fields(texts[language][key]) == fields(template), f"{name}.{language}.{key}"


@pytest.mark.parametrize("texts", [lider_pin.NOTICE, company_bots_v1.FAILURE_REPLY_060A, company_bots_v1.STALE_UPDATE_REPLIES_068A, bots.SHIFTS_BUTTON])
def test_single_messages_cover_all_languages(texts):
    assert set(texts) == LANGUAGES


def test_summary_prompt_is_translated_the_bug_of_the_report():
    """Con el telefono o la eleccion en ingles, el resumen salia en espanol."""
    assert "summarize" in bots._txt("en", "end_shift_summary_prompt")
    assert "résumer" in bots._txt("fr", "end_shift_summary_prompt")
    assert bots._txt("es", "end_shift_summary_prompt") == "🏁 Para finalizar turno, por favor resume tu gestión de hoy.\n\nEscribe tu resumen en un solo mensaje."


def test_spanish_stays_exactly_as_it_was():
    assert bots._txt("es", "no_material_or_inventory") == "No tienes permisos para solicitar material o Inventario no está activo."
    assert bots._txt("es", "telegram_id_intro", telegram_user_id="7") == "🆔 Tu Telegram ID es: 7\n\nEntrega este número a la persona encargada para completar tu registro en CLONEXA."
    assert bots._txt("es", "material_order_created", order_number="M-1") == "📦 Solicitud registrada. Orden: M-1."
    assert bots._materials_webapp_keyboard(company_id="c", telegram_user_id="7")["inline_keyboard"][0][0]["text"] == "📦 Abrir inventario"
    assert bots._materials_webapp_keyboard(company_id="c", telegram_user_id="7", language="en")["inline_keyboard"][0][0]["text"] == "📦 Open inventory"


class Db:
    def __init__(self, chosen):
        self.chosen = chosen

    async def execute(self, *_args, **_kwargs):
        return SimpleNamespace(scalar=lambda: self.chosen)


@pytest.mark.parametrize("chosen,phone,expected", [
    (None, "en-US", "en"),
    ("es", "en", "es"),
    ("fr", "es", "fr"),
    (None, "pt", "es"),
    (None, None, "es"),
])
async def test_late_message_reply_uses_the_person_language(chosen, phone, expected):
    update = {"update_id": 1, "message": {"from": {"id": 7, "language_code": phone}, "chat": {"id": 7}, "text": "hola"}}
    reply = await company_bots_v1.stale_reply_068A(Db(chosen), "f1e8f774-f052-49ca-880a-268805f07db0", update)
    assert reply == company_bots_v1.STALE_UPDATE_REPLIES_068A[expected]


async def test_late_message_reply_survives_a_database_error():
    class Broken:
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("base caida")

    update = {"update_id": 1, "message": {"from": {"id": 7, "language_code": "en"}, "chat": {"id": 7}, "text": "hola"}}
    assert await company_bots_v1.stale_reply_068A(Broken(), "f1e8f774-f052-49ca-880a-268805f07db0", update) == company_bots_v1.STALE_UPDATE_REPLIES_068A["en"]
