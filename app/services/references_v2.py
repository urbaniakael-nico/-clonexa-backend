"""Referencias v2 (pantalla nueva detras del interruptor references_v2).

Solo agrega: nunca cambia el producido, la meta ni los cierres de produccion.
- Catalogo de prendas y tallas: garment_catalog.json (unico y editable).
- Clasificacion opcional (gender, body_part, garment_type): solo esas tres
  columnas; nunca se clasifica sola (las sugerencias solo se muestran).
- Movimientos de corte (reference_cut_movements): ingreso, novedad por
  seccion y envio a despliegue. Solo se agregan; anular no borra.
- Balance de la referencia (todas sus tallas: mismo nombre, categoria y
  color): disponible = recibido - novedades - despliegue.
Toda consulta filtra por company_id.
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CATALOG_PATH = Path(__file__).with_name("garment_catalog.json")
KINDS = ("ingreso", "novedad", "despliegue")
SECTIONS = ("corte", "bordado", "taller", "lavado", "otro")
MAX_QTY = 100000


class Invalid(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


# ---------------------------------------------------------------- catalogo ---
@lru_cache(maxsize=1)
def catalog() -> dict:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    validate_catalog(data)
    return data


def validate_catalog(data: dict) -> None:
    genders = {g["code"] for g in data["genders"]}
    parts = {p["code"] for p in data["body_parts"]}
    codes = [g["code"] for g in data["garments"]]
    if len(codes) != len(set(codes)):
        raise ValueError("prenda repetida en el catalogo")
    for g in data["garments"]:
        if g["body_part"] not in parts:
            raise ValueError(f"{g['code']}: parte desconocida")
        for gender in genders:
            if g["size_set"] not in data["sizes"][gender]:
                raise ValueError(f"{g['code']}: sin tallas para {gender}")


def garment(code: str) -> Optional[dict]:
    return next((g for g in catalog()["garments"] if g["code"] == code), None)


def sizes_for(gender: str, garment_code: str) -> list[str]:
    g = garment(garment_code)
    if not g or gender not in catalog()["sizes"]:
        return []
    return list(catalog()["sizes"][gender][g["size_set"]])


def _fold(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(c for c in raw if unicodedata.category(c) != "Mn")


def _tokens(value: Any) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _fold(value)) if t]


def _hits(token: str, keyword: str) -> bool:
    return token == keyword or (len(keyword) >= 5 and token.startswith(keyword))


def suggest(category: Any, name: Any) -> dict:
    """Sugerencia (nunca se aplica sola) segun la categoria y el nombre actuales."""
    out: dict[str, Any] = {"gender": "mujer", "body_part": None, "garment_type": None}
    for source in (category, name):
        toks = _tokens(source)
        for g in catalog()["garments"]:
            if any(_hits(t, kw) for t in toks for kw in g["keywords"]):
                out.update(body_part=g["body_part"], garment_type=g["code"])
                return out
        if out["body_part"] is None:
            if any(t in ("superior", "superiores", "arriba") for t in toks):
                out["body_part"] = "superior"
            elif any(t in ("inferior", "inferiores", "abajo") for t in toks):
                out["body_part"] = "inferior"
    return out


def combined_sizes(size: Any) -> bool:
    """'4,6,8,10,12' es una sola fila con varias tallas: se muestra tal cual."""
    return "," in str(size or "")


def validate_classification(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise Invalid("clasificacion", "datos inválidos")
    gender = str(raw.get("gender") or "").strip()
    body_part = str(raw.get("body_part") or "").strip()
    garment_type = str(raw.get("garment_type") or "").strip()
    if gender not in {g["code"] for g in catalog()["genders"]}:
        raise Invalid("gender", "género no permitido")
    if body_part not in {p["code"] for p in catalog()["body_parts"]}:
        raise Invalid("body_part", "parte no permitida")
    g = garment(garment_type)
    if not g:
        raise Invalid("garment_type", "prenda no permitida")
    if g["body_part"] != body_part:
        raise Invalid("garment_type", "la prenda no es de esa parte")
    return {"gender": gender, "body_part": body_part, "garment_type": garment_type}


def validate_movement(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise Invalid("movimiento", "datos inválidos")
    kind = str(raw.get("kind") or "").strip()
    if kind not in KINDS:
        raise Invalid("kind", "tipo no permitido")
    section = str(raw.get("section") or "").strip() or None
    if kind == "novedad":
        if section not in SECTIONS:
            raise Invalid("section", "sección no permitida")
    else:
        section = None
    try:
        quantity = int(raw.get("quantity"))
    except (TypeError, ValueError):
        raise Invalid("quantity", "debe ser un número entero") from None
    if not 0 < quantity <= MAX_QTY:
        raise Invalid("quantity", "debe ser mayor que cero")
    try:
        event_date = date.fromisoformat(str(raw.get("event_date") or ""))
    except ValueError:
        raise Invalid("event_date", "fecha inválida (AAAA-MM-DD)") from None
    size = str(raw.get("size") or "").strip()[:40]
    if kind != "novedad" and not size:
        raise Invalid("size", "elige la talla")
    note = str(raw.get("note") or "").strip()
    if len(note) > 500:
        raise Invalid("note", "máximo 500 caracteres")
    try:
        reference_id = str(raw.get("reference_id") or "").strip()
    except Exception:
        reference_id = ""
    if not reference_id or len(reference_id) > 64:
        raise Invalid("reference_id", "referencia inválida")
    return {"reference_id": reference_id, "kind": kind, "section": section, "size": size, "quantity": quantity,
            "note": note, "event_date": event_date}


# -------------------------------------------------------------------- base ---
REF_COLS = """id, name, COALESCE(category, '') AS category, size, COALESCE(color, '') AS color,
    COALESCE(archived, false) AS archived, bot_active, gender, body_part, garment_type"""


async def reference(db: AsyncSession, company_id: str, reference_id: str) -> Optional[dict]:
    row = (await db.execute(text(f"""
        SELECT {REF_COLS} FROM product_references WHERE company_id = :c AND id = :r LIMIT 1
    """), {"c": company_id, "r": reference_id})).mappings().first()
    return dict(row) if row else None


async def group_of(db: AsyncSession, company_id: str, ref: dict) -> list[dict]:
    """Todas las tallas de la referencia: mismo nombre, categoria y color."""
    rows = (await db.execute(text(f"""
        SELECT {REF_COLS} FROM product_references
        WHERE company_id = :c AND lower(name) = lower(:n) AND lower(COALESCE(category, '')) = lower(:k)
          AND lower(COALESCE(color, '')) = lower(:col)
        ORDER BY size
    """), {"c": company_id, "n": ref["name"], "k": ref["category"], "col": ref["color"]})).mappings().all()
    return [dict(r) for r in rows]


async def classify(db: AsyncSession, company_id: str, reference_id: str, raw: dict) -> dict:
    data = validate_classification(raw)
    result = await db.execute(text("""
        UPDATE product_references SET gender = :g, body_part = :b, garment_type = :t
        WHERE company_id = :c AND id = :r
    """), {**{"g": data["gender"], "b": data["body_part"], "t": data["garment_type"]}, "c": company_id, "r": reference_id})
    if not result.rowcount:
        await db.rollback()
        raise Invalid("reference_id", "la referencia no es de esta empresa")
    await db.commit()
    return data


async def add_movements(db: AsyncSession, company_id: str, items: list, actor: str) -> list[dict]:
    """Varios movimientos de una vez (el boton Guardar registro): todo o nada."""
    if not isinstance(items, list) or not 1 <= len(items) <= 60:
        raise Invalid("items", "entre 1 y 60 movimientos")
    clean = [validate_movement(i) for i in items]
    ids = sorted({m["reference_id"] for m in clean})
    owned = (await db.execute(text("""
        SELECT id FROM product_references WHERE company_id = :c AND id = ANY(CAST(:ids AS text[]))
    """), {"c": company_id, "ids": ids})).scalars().all()
    if set(owned) != set(ids):
        raise Invalid("reference_id", "la referencia no es de esta empresa")
    out = []
    for m in clean:
        row = (await db.execute(text("""
            INSERT INTO reference_cut_movements (company_id, reference_id, kind, section, size, quantity, note, event_date, created_by)
            VALUES (:c, :r, :k, :s, :z, :q, :n, :d, :by) RETURNING id::text AS id, created_at
        """), {"c": company_id, "r": m["reference_id"], "k": m["kind"], "s": m["section"], "z": m["size"], "q": m["quantity"],
               "n": m["note"], "d": m["event_date"], "by": actor[:200]})).mappings().first()
        out.append({**m, "id": row["id"], "created_at": row["created_at"]})
    await db.commit()
    return out


async def void_movement(db: AsyncSession, company_id: str, movement_id: str, reason: str, actor: str) -> bool:
    reason = str(reason or "").strip()
    if len(reason) < 3:
        raise Invalid("reason", "escribe el motivo")
    try:
        mid = str(uuid.UUID(str(movement_id)))
    except ValueError:
        return False
    result = await db.execute(text("""
        UPDATE reference_cut_movements SET voided_at = now(), voided_by = :by, void_reason = :r
        WHERE company_id = :c AND id = CAST(:m AS uuid) AND voided_at IS NULL
    """), {"c": company_id, "m": mid, "by": actor[:200], "r": reason[:300]})
    await db.commit()
    return bool(result.rowcount)


def tally(movements: list[dict]) -> dict:
    live = [m for m in movements if not m.get("voided_at")]
    received = sum(m["quantity"] for m in live if m["kind"] == "ingreso")
    novelty = sum(m["quantity"] for m in live if m["kind"] == "novedad")
    deployed = sum(m["quantity"] for m in live if m["kind"] == "despliegue")
    by_section = {s: sum(m["quantity"] for m in live if m["kind"] == "novedad" and m["section"] == s) for s in SECTIONS}
    return {"received": received, "novelty": novelty, "deployed": deployed, "available": received - novelty - deployed,
            "by_section": by_section}


async def movements_for(db: AsyncSession, company_id: str, reference_ids: list[str]) -> list[dict]:
    if not reference_ids:
        return []
    rows = (await db.execute(text("""
        SELECT id::text AS id, reference_id, kind, section, size, quantity, note, event_date, created_by, created_at,
               voided_at, voided_by, void_reason
        FROM reference_cut_movements WHERE company_id = :c AND reference_id = ANY(CAST(:ids AS text[]))
        ORDER BY event_date DESC, created_at DESC
    """), {"c": company_id, "ids": reference_ids})).mappings().all()
    return [dict(r) for r in rows]


async def balance(db: AsyncSession, company_id: str, reference_id: str) -> Optional[dict]:
    ref = await reference(db, company_id, reference_id)
    if not ref:
        return None
    group = await group_of(db, company_id, ref)
    moves = await movements_for(db, company_id, [r["id"] for r in group])
    sizes = sorted({m["size"] for m in moves if m["size"]}, key=size_key)
    per_size = {s: tally([m for m in moves if m["size"] == s]) for s in sizes}
    return {"reference": ref, "group": group, **tally(moves), "per_size": per_size, "log": moves}


def size_key(value: str) -> tuple:
    """Orden de menor a mayor: numeros, luego XS..XXL, luego el resto."""
    order = {"xs": 0, "s": 1, "m": 2, "l": 3, "xl": 4, "xxl": 5, "unica": 6, "única": 6}
    v = str(value or "").strip().lower()
    if v.isdigit():
        return (0, int(v), v)
    if v in order:
        return (1, order[v], v)
    return (2, 0, v)


async def board_extras(db: AsyncSession, company_id: str) -> dict:
    """Para Estado de referencias: clasificacion, sugerencia, tallas combinadas
    y la nota del ultimo envio a despliegue de cada fila (nada mas)."""
    rows = (await db.execute(text(f"""
        SELECT {REF_COLS} FROM product_references WHERE company_id = :c
    """), {"c": company_id})).mappings().all()
    deploy = (await db.execute(text("""
        SELECT reference_id, SUM(quantity) AS qty, MAX(event_date) AS last_date
        FROM reference_cut_movements WHERE company_id = :c AND kind = 'despliegue' AND voided_at IS NULL
        GROUP BY reference_id
    """), {"c": company_id})).mappings().all()
    deployed = {r["reference_id"]: {"quantity": int(r["qty"]), "last_date": r["last_date"]} for r in deploy}
    out = {}
    for r in rows:
        classified = bool(r["gender"] and r["body_part"] and r["garment_type"])
        out[r["id"]] = {
            "gender": r["gender"], "body_part": r["body_part"], "garment_type": r["garment_type"],
            "classified": classified, "suggestion": None if classified else suggest(r["category"], r["name"]),
            "combined_sizes": combined_sizes(r["size"]), "deployed": deployed.get(r["id"]),
        }
    return out


async def catalog_counts(db: AsyncSession, company_id: str) -> dict:
    """Referencias activas clasificadas por genero, parte y prenda (por nombre)."""
    rows = (await db.execute(text("""
        SELECT gender, body_part, garment_type, COUNT(DISTINCT lower(name)) AS n FROM product_references
        WHERE company_id = :c AND COALESCE(archived, false) IS NOT TRUE AND gender IS NOT NULL
        GROUP BY gender, body_part, garment_type
    """), {"c": company_id})).mappings().all()
    out: dict = {}
    for r in rows:
        g = out.setdefault(r["gender"], {"parts": {}, "garments": {}})
        g["parts"][r["body_part"]] = g["parts"].get(r["body_part"], 0) + int(r["n"])
        g["garments"][r["garment_type"]] = g["garments"].get(r["garment_type"], 0) + int(r["n"])
    return out


def validate_catalog_create(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise Invalid("referencia", "datos inválidos")
    cls = validate_classification(raw)
    name = str(raw.get("name") or "").strip()
    if not name or len(name) > 120:
        raise Invalid("name", "escribe el nombre de la referencia")
    color = str(raw.get("color") or "").strip()[:60]
    allowed = sizes_for(cls["gender"], cls["garment_type"])
    lines = raw.get("sizes")
    if not isinstance(lines, list) or not lines:
        raise Invalid("sizes", "marca al menos una talla")
    seen, clean = set(), []
    for line in lines:
        size = str((line or {}).get("size") or "").strip()
        if size not in allowed:
            raise Invalid("sizes", f"la talla {size or '—'} no es de esta prenda")
        if size in seen:
            raise Invalid("sizes", f"talla {size} repetida")
        try:
            qty = int((line or {}).get("quantity"))
        except (TypeError, ValueError):
            raise Invalid("sizes", f"cantidad inválida en talla {size}") from None
        if not 0 <= qty <= MAX_QTY:
            raise Invalid("sizes", f"cantidad inválida en talla {size}")
        seen.add(size)
        clean.append({"size": size, "quantity": qty})
    clean.sort(key=lambda x: allowed.index(x["size"]))
    bot = raw.get("bot_visible", True) is not False
    return {**cls, "name": name, "color": color, "sizes": clean, "bot_visible": bot,
            "category": garment(cls["garment_type"])["label"]}
