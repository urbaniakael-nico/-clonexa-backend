"""Galería de íconos de carta de Clonexa (piloto The Time Machine, 2026-11).

UNA sola tabla (ICONS, una fila por ícono) para la pantalla QR del bar, el
mesero, la caja, domicilios y la vista previa de "Nuevo registro de inventario".
Reconoce la PRIMERA palabra del nombre (sin tildes, mayúsculas, singular o
plural), igual que menuEmoji() de hsp_menu_kit.js. Para ampliar: agrega
palabras a una fila, o una fila nueva con su SVG en app/web/assets/iconos-carta/.

Interruptor por empresa "iconos_carta_clonexa" (ajustes del módulo QR, apagado
por defecto): con el interruptor apagado no se agrega ningún campo y las
pantallas quedan idénticas (emojis como antes).

Prioridad de cada artículo: foto subida > ícono elegido a mano (icono_key) >
ícono reconocido por palabra > genérico (bebida-generica.svg, nunca el plato).
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SETTING = "iconos_carta_clonexa"
VERSION = "ic1"
URL_PREFIX = "/assets/iconos-carta/"
QR_MODULE_CODES = ("qr", "mesa_qr", "mesas_qr", "qr_mesas", "hospitality_qr", "voting_qr")

# key, etiqueta, archivo, palabras (sin tildes, en minúscula; singular y plural salen solos)
ICONS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("agua", "Agua", "agua.svg", ("agua", "cristal", "brisa", "manantial")),
    ("aguardiente", "Aguardiente", "aguardiente.svg", ("aguardiente", "guaro", "antioqueno", "nectar", "blanco", "amarillo")),
    ("cerveza", "Cerveza", "cerveza.svg", ("cerveza", "pola", "michelada", "aguila", "poker", "club", "corona", "costena", "costenita",
                                           "budweiser", "stella", "heineken", "redds")),
    ("chiclets", "Chiclets", "chiclets.svg", ("chicle", "chiclet", "chiclets", "dulce", "goma", "confite", "trident", "menta", "bombon",
                                              "colombina", "chupeta")),
    ("cigarrillo", "Cigarrillo", "cigarrillo.svg", ("cigarrillo", "cigarro", "tabaco", "marlboro", "lucky", "boston", "belmont", "pielroja")),
    ("gaseosa", "Gaseosa", "gaseosa.svg", ("gaseosa", "soda", "refresco", "cola", "coca", "pepsi", "postobon", "colombiana", "sprite",
                                           "manzana", "uva", "quatro")),
    ("hidratante", "Hidratante", "hidratante.svg", ("hidratante", "gatorade", "powerade", "suero", "electrolit", "sporade")),
    ("paquete", "Paquete", "paquete.svg", ("paquete", "snack", "mecato", "pasaboca", "papa", "papita", "chito", "dorito", "detodito", "mani",
                                           "tostaco", "crispeta")),
    ("ron", "Ron", "ron.svg", ("ron", "medellin", "caldas", "bacardi", "havana")),
    ("shot", "Shot", "shot.svg", ("shot", "chupito", "trago")),
    ("tequila", "Tequila", "tequila.svg", ("tequila", "jose", "cuervo", "jimador", "patron")),
    ("tiket", "Tiket", "tiket.svg", ("tiket", "ticket", "boleta", "entrada", "cover", "manilla", "evento")),
    ("vodka", "Vodka", "vodka.svg", ("vodka", "absolut", "smirnoff")),
    ("whiskey", "Whiskey", "whiskey.svg", ("whisky", "whiskey", "buchanans", "chivas", "old", "jack", "johnnie")),
)
GENERIC = ("bebida", "Bebida", "bebida-generica.svg", ())
GALLERY = ICONS + (GENERIC,)
BY_KEY = {row[0]: row for row in GALLERY}
WORD_TO_KEY = {word: row[0] for row in ICONS for word in row[3]}


def url(key: str) -> str:
    row = BY_KEY.get(key) or GENERIC
    return f"{URL_PREFIX}{row[2]}?v={VERSION}"


def first_word(name: Any) -> str:
    """Primera palabra como la lee menuEmoji(): sin tildes (ñ -> n), minúsculas, sin signos."""
    plain = unicodedata.normalize("NFD", str(name or ""))
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch)).lower()
    plain = re.sub(r"[^a-z0-9\s]", " ", plain).strip()
    return plain.split()[0] if plain else ""


def recognize(name: Any) -> tuple[Optional[str], str]:
    """(key o None, palabra). Prueba la palabra, sin 'es' y sin 's' (Papitas, Aguardientes)."""
    word = first_word(name)
    if not word:
        return None, ""
    for candidate in (word, re.sub(r"es$", "", word), re.sub(r"s$", "", word)):
        if candidate in WORD_TO_KEY:
            return WORD_TO_KEY[candidate], word
    return None, word


def resolve(name: Any, *, icono_key: Any = None, photo_url: str = "") -> dict[str, Any]:
    """Ícono final de un artículo. source: photo | manual | auto | generic."""
    auto_key, word = recognize(name)
    auto = {"key": auto_key or GENERIC[0], "url": url(auto_key or GENERIC[0]), "word": word, "recognized": bool(auto_key)}
    if photo_url:
        return {"source": "photo", "url": photo_url, "key": "", "word": word, "auto": auto}
    if isinstance(icono_key, str) and icono_key in BY_KEY:
        return {"source": "manual", "url": url(icono_key), "key": icono_key, "word": word, "auto": auto}
    return {"source": "auto" if auto_key else "generic", "url": auto["url"], "key": auto["key"], "word": word, "auto": auto}


def gallery() -> list[dict[str, Any]]:
    return [{"key": k, "label": label, "url": url(k), "words": list(words), "generic": k == GENERIC[0]} for k, label, _f, words in GALLERY]


def category_icon(items: Iterable[dict[str, Any]], label: Any) -> dict[str, Any]:
    """Ícono de una categoría: el elegido a mano que más se repite entre sus artículos;
    si ninguno lo tiene, el reconocido por el nombre de la categoría (o el genérico)."""
    manual: dict[str, int] = {}
    for item in items:
        icon = item.get("icon") or {}
        if icon.get("source") == "manual" and icon.get("key"):
            manual[icon["key"]] = manual.get(icon["key"], 0) + 1
    if manual:
        key = sorted(manual.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        return {"source": "manual", "url": url(key), "key": key}
    found = resolve(label)
    return {"source": found["source"], "url": found["url"], "key": found["key"]}


# ---------------------------------------------------------------- base de datos
def _settings(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


async def is_on(db: AsyncSession, company_id: uuid.UUID | str) -> bool:
    """Interruptor iconos_carta_clonexa en el módulo QR de ESA empresa (apagado por defecto)."""
    codes = ", ".join(f"'{c}'" for c in QR_MODULE_CODES)
    try:
        row = (await db.execute(text(f"""
            SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:c AS uuid) AND m.code IN ({codes}) AND cm.enabled IS TRUE
            ORDER BY cm.updated_at DESC NULLS LAST LIMIT 1"""), {"c": str(company_id)})).mappings().first()
    except Exception:
        return False
    return bool(row) and _settings(row["settings"]).get(SETTING) is True


async def _has_table(db: AsyncSession, name: str) -> bool:
    return bool((await db.execute(text("SELECT to_regclass(:n)"), {"n": f"public.{name}"})).scalar())


async def record_misses(db: AsyncSession, company_id: uuid.UUID | str, icons: Iterable[dict[str, Any]]) -> None:
    """Palabras que hoy caen en el genérico (empresa + palabra + número de artículos).
    Solo palabras: ningún dato personal. Las que ya tienen ícono salen de la lista."""
    if not await _has_table(db, "carta_icon_misses"):
        return
    counts: dict[str, int] = {}
    for icon in icons:
        if icon.get("source") == "generic" and icon.get("word"):
            word = str(icon["word"])[:40]
            counts[word] = counts.get(word, 0) + 1
    words = sorted(counts)
    await db.execute(text("DELETE FROM carta_icon_misses WHERE company_id = CAST(:c AS uuid) AND NOT (word = ANY(CAST(:w AS text[])))"),
                     {"c": str(company_id), "w": words})
    for word in words:
        await db.execute(text("""
            INSERT INTO carta_icon_misses (company_id, word, items, first_seen, last_seen)
            VALUES (CAST(:c AS uuid), :w, :n, now(), now())
            ON CONFLICT (company_id, word) DO UPDATE SET items = EXCLUDED.items, last_seen = now()
            WHERE carta_icon_misses.items <> EXCLUDED.items OR carta_icon_misses.last_seen < now() - interval '1 hour'"""),
                         {"c": str(company_id), "w": word, "n": counts[word]})


async def list_misses(db: AsyncSession, company_id: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
    if not await _has_table(db, "carta_icon_misses"):
        return []
    where = "WHERE m.company_id = CAST(:c AS uuid)" if company_id else ""
    rows = (await db.execute(text(f"""
        SELECT m.company_id::text AS company_id, COALESCE(c.name, '') AS company_name, m.word, m.items, m.first_seen, m.last_seen
        FROM carta_icon_misses m LEFT JOIN companies c ON c.id = m.company_id
        {where} ORDER BY company_name, m.items DESC, m.word LIMIT :l"""), {"c": company_id, "l": limit})).mappings().all()
    return [{**dict(r), "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
             "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None} for r in rows]
