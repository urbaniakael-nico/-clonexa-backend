"""Tamaño de un articulo de inventario: numero + unidad (049M).

Antes era texto libre y quedaban valores como "275gr", "280 grm", "250GR",
"1.5lt" o "500 ml". Ahora se guarda el numero y una unidad de una lista
corta, y el texto (item_size, que usan el bot, reportes y etiquetas) queda
normalizado: "275 gr", "1.5 litros". Lo que no se pueda interpretar se deja
tal cual y se marca para revision: nunca se pierde el dato.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

UNIT_GROUPS = {
    "peso": ["gr", "lb", "kg"],
    "volumen": ["ml", "litros"],
    "unidad": ["unidad", "paquete", "caja", "docena"],
}
UNITS = [unit for units in UNIT_GROUPS.values() for unit in units]
# 049Q: las empresas con Carta eligen el tamaño en la misma lista que las
# recetas (gr, kg, lb, onza, ml, litros, unidad, par, docena, paquete,
# cucharada, pizca). Se aceptan al elegirlas; el texto viejo se sigue
# interpretando igual para todas.
FORM_UNITS = UNITS + ["onza", "par", "cucharada", "pizca"]

# como lo escribe la gente -> unidad de la lista
ALIASES = {
    "gr": ["g", "gr", "grs", "grm", "grms", "gm", "gms", "gramo", "gramos", "grams", "gram"],
    "lb": ["lb", "lbs", "libra", "libras"],
    "kg": ["kg", "kgs", "kilo", "kilos", "kilogramo", "kilogramos"],
    "ml": ["ml", "mls", "mililitro", "mililitros", "cc"],
    "litros": ["l", "lt", "lts", "ltr", "ltrs", "litro", "litros"],
    "unidad": ["u", "un", "und", "unds", "unid", "unidad", "unidades"],
    "paquete": ["paq", "paqs", "pqt", "paquete", "paquetes"],
    "caja": ["cj", "caja", "cajas"],
    "docena": ["doc", "dz", "docena", "docenas"],
}
_BY_ALIAS = {alias: unit for unit, aliases in ALIASES.items() for alias in aliases}
_PATTERN = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([a-z]+)\.?$")


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def parse(text: Any) -> tuple[Decimal, str] | None:
    """"275gr" -> (275, "gr"); "1.5lt" -> (1.5, "litros"); si no se puede
    interpretar con seguridad, None (p. ej. "M", "20m", "500" sin unidad o
    "1.500 ml", que podria ser 1,5 o 1.500)."""
    clean = _plain(str(text or ""))
    match = _PATTERN.match(clean)
    if not match:
        return None
    number, alias = match.groups()
    unit = _BY_ALIAS.get(alias)
    if not unit:
        return None
    if "." in number and len(number.split(".")[1]) == 3:
        return None  # "1.500": miles o decimal? mejor que lo revise una persona
    try:
        value = Decimal(number.replace(",", "."))
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    return value, unit


def number_text(value: Any) -> str:
    value = Decimal(str(value))
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_size(value: Any, unit: str) -> str:
    return f"{number_text(value)} {unit}"


def clean(value: Any, unit: Any) -> tuple[Decimal, str]:
    """Numero y unidad elegidos en el formulario; ValueError si no sirven."""
    unit = str(unit or "").strip().lower()
    if unit not in FORM_UNITS:
        raise ValueError("unidad_invalida")
    try:
        number = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("tamano_invalido") from exc
    if number <= 0 or number > Decimal("1000000"):
        raise ValueError("tamano_invalido")
    return number, unit


def normalize_existing(text: Any) -> dict:
    """Para la migracion y para lo que llegue como texto: {text, value, unit,
    review}. Sin texto -> todo vacio y sin revision."""
    raw = " ".join(str(text or "").split())
    if not raw:
        return {"text": None, "value": None, "unit": None, "review": False}
    parsed = parse(raw)
    if not parsed:
        return {"text": raw, "value": None, "unit": None, "review": True}
    value, unit = parsed
    return {"text": format_size(value, unit), "value": value, "unit": unit, "review": False}
