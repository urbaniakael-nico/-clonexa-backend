"""Referencias v2 (pantalla nueva detras del interruptor references_v2).

Solo agrega: nunca cambia el producido, la meta ni los cierres de produccion.
- Catalogo de prendas y tallas: garment_catalog.json (unico y editable).
- Clasificacion opcional (gender, body_part, garment_type): solo esas tres
  columnas; nunca se clasifica sola (las sugerencias solo se muestran).
- Movimientos de corte (reference_cut_movements): ingreso, novedad por
  seccion y envio a despliegue. Solo se agregan; anular no borra.
- Balance de la referencia (todas sus tallas: mismo NOMBRE, sin importar
  mayusculas, tildes ni espacios; el color va en cada talla): disponible =
  recibido - novedades - despliegue. La agrupacion es UNA sola (group_key)
  para Cortes, Orden operacional, Catalogo y Estado de referencias.
- Meta de cada talla = suma de sus cortes (ingresos vigentes); una talla sin
  cortes conserva su meta. Cada cambio de datos que no hace una persona campo
  por campo queda en reference_change_log y se puede revertir por lote.
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


def group_key(name: Any, color: Any = None) -> str:
    """Referencia = NOMBRE (todas sus tallas y colores). UNA sola regla para Cortes,
    Orden operacional, Catalogo y Estado: sin importar mayusculas, tildes ni
    espacios. El color se muestra en cada talla (no separa la referencia)."""
    return re.sub(r"\s+", "", _fold(name))


def key_of(row: dict) -> str:
    return group_key(row.get("name"))


async def group_of(db: AsyncSession, company_id: str, ref: dict) -> list[dict]:
    """Todas las tallas de la referencia (mismo group_key), incluidas las archivadas."""
    rows = (await db.execute(text(f"""
        SELECT {REF_COLS} FROM product_references WHERE company_id = :c ORDER BY size
    """), {"c": company_id})).mappings().all()
    key = key_of(ref)
    return [dict(r) for r in rows if key_of(dict(r)) == key]


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
    group.sort(key=lambda r: size_key(r["size"]))
    moves = await movements_for(db, company_id, [r["id"] for r in group])
    existing = sorted({s for r in group for s in sizes_of(r["size"])}, key=size_key)
    existing_folded = {_fold(s) for s in existing}
    for m in moves:  # "talla sin referencia": la talla aun no existe como fila de esta referencia
        m["size_without_reference"] = bool(m["size"]) and _fold(m["size"]) not in existing_folded
    sizes = sorted({m["size"] for m in moves if m["size"]}, key=size_key)
    per_size = {s: tally([m for m in moves if m["size"] == s]) for s in sizes}
    classified = next((r for r in group if r["gender"] and r["garment_type"]), None)
    catalog_sizes = sizes_for(classified["gender"], classified["garment_type"]) if classified else []
    received_by_date: dict = {}
    for m in moves:
        if m["kind"] == "ingreso" and not m.get("voided_at"):
            received_by_date[m["event_date"]] = received_by_date.get(m["event_date"], 0) + m["quantity"]
    return {"reference": ref, "group": group, **tally(moves), "per_size": per_size, "log": moves,
            "existing_sizes": existing, "catalog_sizes": catalog_sizes, "classified": bool(classified),
            "received_by_date": [{"date": d, "quantity": q} for d, q in sorted(received_by_date.items())]}


LETTER_ORDER = {"xxs": -1, "xs": 0, "s": 1, "m": 2, "l": 3, "xl": 4, "xxl": 5, "xxxl": 6}
_LETTER_TOKENS = re.compile(r"xxxl|xxl|xl|xxs|xs|s|m|l")


def size_key(value: str) -> tuple:
    """Orden del catalogo, de menor a mayor: numeros ascendentes (4, 6, 8...),
    luego letras XS, S, M, L, XL, XXL (SM antes que ML), luego talla unica y
    el resto. Una fila combinada ("4, 6, 8") se ordena por su primera talla."""
    v = _fold(value).strip()
    first = re.split(r"[,;/]", v)[0].strip()
    num = re.match(r"^(\d+(?:\.\d+)?)", first)
    if num:
        return (0, float(num.group(1)), (), v)
    letters = re.sub(r"[^a-z]", "", first)
    tokens = []
    rest = letters
    while rest:
        m = _LETTER_TOKENS.match(rest)
        if not m:
            break
        tokens.append(LETTER_ORDER[m.group(0)])
        rest = rest[m.end():]
    if tokens and not rest:
        return (1, tokens[0], tuple(tokens), v)
    if first in ("unica", "u", "tu", "talla unica"):
        return (2, 0, (), v)
    return (3, 0, (), v)


def sizes_of(size: Any) -> list[str]:
    """Tallas de una fila: una combinada ("4, 6, 8") aporta cada una (sin partir la fila)."""
    return [t.strip() for t in re.split(r"[,;]", str(size or "")) if t.strip()]


def _group_key(row: dict) -> str:
    return key_of(row)


def owner_row(rows: list[dict], movement: dict) -> Optional[str]:
    """Fila a la que pertenece un movimiento: la de su talla dentro de la misma
    referencia (nombre, categoria y color); si esa talla aun no existe como
    fila, la fila donde se registro. No cambia nada guardado."""
    by_id = {r["id"]: r for r in rows}
    anchor = by_id.get(movement["reference_id"])
    if not anchor or not movement.get("size"):
        return movement["reference_id"]
    key, size = _group_key(anchor), _fold(movement["size"]).strip()
    for r in rows:
        if _group_key(r) == key and size in [_fold(x) for x in sizes_of(r["size"])]:
            return r["id"]
    return movement["reference_id"]


async def board_extras(db: AsyncSession, company_id: str) -> dict:
    """Para Estado de referencias: clasificacion, sugerencia, tallas combinadas
    y la nota del ultimo envio a Bombon de cada fila, por su talla (nada mas)."""
    rows = [dict(r) for r in (await db.execute(text(f"""
        SELECT {REF_COLS} FROM product_references WHERE company_id = :c
    """), {"c": company_id})).mappings().all()]
    moves = (await db.execute(text("""
        SELECT reference_id, size, quantity, event_date
        FROM reference_cut_movements WHERE company_id = :c AND kind = 'despliegue' AND voided_at IS NULL
    """), {"c": company_id})).mappings().all()
    deployed: dict = {}
    for m in moves:
        rid = owner_row(rows, dict(m))
        d = deployed.setdefault(rid, {"quantity": 0, "last_date": None})
        d["quantity"] += int(m["quantity"])
        d["last_date"] = max(d["last_date"], m["event_date"]) if d["last_date"] else m["event_date"]
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


# ------------------------------------------------- referencia = nombre + color
async def finished_by_reference(db: AsyncSession, company_id: str) -> tuple[dict, dict]:
    """Producido por fila (ciclo actual e historico): la MISMA consulta del resumen
    de siempre (/summary). Devuelve ({id: actual}, {id: historico})."""
    finished: dict[str, int] = {}
    historical: dict[str, int] = {}
    cols = {r[0] for r in (await db.execute(text("""
        SELECT column_name FROM information_schema.columns WHERE table_name = 'reference_production_closures'
    """))).all()}
    if not {"company_id", "reference_name", "size", "quantity_finished"}.issubset(cols):
        return finished, historical
    rows = (await db.execute(text("""
        SELECT
            pr.id AS reference_id,
            COALESCE(sum(c.quantity_finished) FILTER (
                WHERE pr.activation_date IS NULL OR c.closed_at >= pr.activation_date
            ), 0) AS finished,
            COALESCE(sum(c.quantity_finished), 0) AS historical_finished
        FROM product_references pr
        LEFT JOIN reference_production_closures c
          ON c.company_id::text = :company_id
         AND (
            (COALESCE(c.reference_id, '') <> '' AND c.reference_id = pr.id)
            OR (
                COALESCE(c.reference_id, '') = ''
                AND lower(COALESCE(c.reference_name, '')) = lower(COALESCE(pr.name, ''))
                AND lower(COALESCE(c.size, '')) = lower(COALESCE(pr.size, ''))
            )
         )
        WHERE pr.company_id = :company_id
        GROUP BY pr.id
    """), {"company_id": company_id})).mappings().all()
    for r in rows:
        key = str(r["reference_id"] or "").strip()
        finished[key] = int(r["finished"] or 0)
        historical[key] = int(r["historical_finished"] or 0)
    return finished, historical


def build_groups(rows: list[dict], moves: list[dict], finished: dict) -> list[dict]:
    """Una tarjeta por referencia (nombre) con una linea por talla: las filas de
    product_references activas (con su color) y las tallas que solo tienen
    cortes ("solo corte"), en el orden del catalogo, y los cortes por fecha.
    Funcion pura."""
    groups: dict[str, dict] = {}
    key_by_id = {r["id"]: key_of(r) for r in rows}
    for r in sorted(rows, key=lambda x: size_key(x["size"])):
        if r.get("archived"):
            continue
        g = groups.setdefault(key_of(r), {"key": key_of(r), "name": r["name"], "color": r["color"], "lines": [], "unsized_received": 0, "cuts": {}})
        tokens = [_fold(t).strip() for t in sizes_of(r["size"])]
        meta, produced = int(r.get("initial_quantity") or 0), int(finished.get(r["id"], 0))
        g["lines"].append({
            "size": r["size"], "color": r.get("color") or "", "reference_id": r["id"], "solo_corte": False, "tokens": tokens,
            "combined": combined_sizes(r["size"]), "meta": meta, "produced": produced, "pending": max(meta - produced, 0),
            "bot_active": r.get("bot_active") is True, "received": 0, "anchor_id": None,
        })
    for m in moves:
        g = groups.get(key_by_id.get(m["reference_id"], ""))
        if not g or m.get("voided_at") or m.get("kind") != "ingreso":
            continue
        size = _fold(m.get("size") or "").strip()
        qty = int(m["quantity"])
        if m.get("event_date"):
            day = g["cuts"].setdefault(str(m["event_date"]), {"date": str(m["event_date"]), "sizes": {}, "total": 0, "last_at": None})
            label = str(m.get("size") or "").strip() or "—"
            day["sizes"][label] = day["sizes"].get(label, 0) + qty
            day["total"] += qty
            at = m.get("created_at")
            if at is not None and (day["last_at"] is None or at > day["last_at"]):
                day["last_at"] = at
        if not size:
            g["unsized_received"] += qty
            continue
        line = next((x for x in g["lines"] if size in x["tokens"]), None)
        if line is None:
            line = {"size": str(m["size"]).strip(), "color": "", "reference_id": None, "solo_corte": True, "tokens": [size], "combined": False,
                    "meta": 0, "produced": 0, "pending": 0, "bot_active": False, "received": 0, "anchor_id": m["reference_id"]}
            g["lines"].append(line)
        line["received"] += qty
    out = []
    for g in groups.values():
        g["lines"].sort(key=lambda x: size_key(x["size"]))
        anchor = next((x["reference_id"] for x in g["lines"] if x["reference_id"]), None)
        for line in g["lines"]:
            if line["solo_corte"]:
                line["anchor_id"] = anchor  # "Crear referencia en talla N" sobre una fila de la referencia
            line.pop("tokens", None)
        received = sum(x["received"] for x in g["lines"]) + g["unsized_received"]
        produced = sum(x["produced"] for x in g["lines"])
        meta = sum(x["meta"] for x in g["lines"])
        days = sorted(g.pop("cuts").values(), key=lambda d: d["date"], reverse=True)
        for d in days:
            d["sizes"] = [{"size": k, "quantity": v} for k, v in sorted(d["sizes"].items(), key=lambda kv: size_key(kv[0]))]
        g.update({
            "received": received, "produced": produced, "meta": meta,
            "pending": sum(x["pending"] for x in g["lines"]),
            "percent": pct1(produced, received),
            "solo_corte": [x["size"] for x in g["lines"] if x["solo_corte"]],
            "colors": sorted({x["color"] for x in g["lines"] if x["color"]}, key=_fold),
            "cuts_by_date": days,
        })
        out.append(g)
    out.sort(key=lambda g: _fold(g["name"]))
    return out


async def reference_groups(db: AsyncSession, company_id: str) -> list[dict]:
    rows = [dict(r) for r in (await db.execute(text(f"""
        SELECT {REF_COLS}, COALESCE(initial_quantity, 0) AS initial_quantity FROM product_references WHERE company_id = :c
    """), {"c": company_id})).mappings().all()]
    moves = [dict(r) for r in (await db.execute(text("""
        SELECT reference_id, kind, size, quantity, voided_at, event_date, created_at FROM reference_cut_movements
        WHERE company_id = :c AND kind = 'ingreso' AND voided_at IS NULL
    """), {"c": company_id})).mappings().all()]
    finished, _ = await finished_by_reference(db, company_id)
    return build_groups(rows, moves, finished)


# ------------------------------------------------- bitacora de cambios (revertible)
async def log_change(db: AsyncSession, company_id: str, batch_id: str, reason: str, table: str, row_id: Any, column: str,
                     old: Any, new: Any, actor: str) -> None:
    await db.execute(text("""
        INSERT INTO reference_change_log (company_id, batch_id, reason, table_name, row_id, column_name, old_value, new_value, actor)
        VALUES (:c, CAST(:b AS uuid), :r, :t, :i, :col, :o, :n, :a)
    """), {"c": company_id, "b": batch_id, "r": reason[:40], "t": table, "i": str(row_id), "col": column,
           "o": None if old is None else str(old), "n": None if new is None else str(new), "a": str(actor or "")[:200]})


_REVERTIBLE = {
    ("product_references", "initial_quantity"): "integer", ("product_references", "size"): "text",
    ("product_references", "archived"): "boolean", ("product_references", "bot_active"): "boolean",
    ("reference_cut_movements", "size"): "text", ("reference_cut_movements", "reference_id"): "text",
    ("reference_production_closures", "reference_id"): "text", ("reference_cycle_resets", "reference_id"): "text",
    ("reference_work_sessions", "reference_id"): "text", ("work_sessions", "reference_id"): "text",
    ("mini_panel_sales_records", "reference_id"): "text", ("inventory_locations", "reference_id"): "text",
}


async def revert_batch(db: AsyncSession, company_id: str, batch_id: str) -> int:
    """Deshace un lote de la bitacora, en orden inverso, y lo marca revertido."""
    rows = (await db.execute(text("""
        SELECT id, table_name, row_id, column_name, old_value FROM reference_change_log
        WHERE company_id = :c AND batch_id = CAST(:b AS uuid) AND reverted_at IS NULL ORDER BY id DESC
    """), {"c": company_id, "b": batch_id})).mappings().all()
    for r in rows:
        kind = _REVERTIBLE.get((r["table_name"], r["column_name"]))
        if not kind:
            raise Invalid("batch", f"no se puede revertir {r['table_name']}.{r['column_name']}")
        await db.execute(text(f"""UPDATE {r["table_name"]} SET {r["column_name"]} = CAST(CAST(:v AS text) AS {kind})
            WHERE id::text = CAST(:i AS text) AND company_id::text = CAST(:c AS text)"""),
                         {"v": r["old_value"], "i": r["row_id"], "c": company_id})
    await db.execute(text("""
        UPDATE reference_change_log SET reverted_at = now() WHERE company_id = :c AND batch_id = CAST(:b AS uuid) AND reverted_at IS NULL
    """), {"c": company_id, "b": batch_id})
    await db.commit()
    return len(rows)


# ------------------------------------------------- meta = suma de los cortes
async def _cut_totals(db: AsyncSession, company_id: str) -> tuple[list[dict], list[dict]]:
    rows = [dict(r) for r in (await db.execute(text(f"""
        SELECT {REF_COLS}, COALESCE(initial_quantity, 0) AS initial_quantity FROM product_references WHERE company_id = :c
    """), {"c": company_id})).mappings().all()]
    moves = [dict(r) for r in (await db.execute(text("""
        SELECT reference_id, size, quantity, voided_at FROM reference_cut_movements WHERE company_id = :c AND kind = 'ingreso'
    """), {"c": company_id})).mappings().all()]
    return rows, moves


def meta_plan(rows: list[dict], moves: list[dict], key: Optional[str] = None) -> list[dict]:
    """Por talla (fila activa), la meta = suma de sus ingresos vigentes. Solo las
    tallas que tienen cortes registrados (aunque esten anulados); las demas
    conservan su meta. Devuelve solo las que cambian. Funcion pura."""
    by_id = {r["id"]: r for r in rows}
    totals: dict[str, int] = {}
    seen: set[str] = set()
    for m in moves:
        anchor = by_id.get(m["reference_id"])
        if not anchor or not m.get("size"):
            continue
        rid = owner_row(rows, m)
        target = by_id.get(rid)
        if not target or target.get("archived") or _fold(m["size"]).strip() not in [_fold(t).strip() for t in sizes_of(target["size"])]:
            continue  # talla "solo corte": no tiene fila todavia
        seen.add(rid)
        if not m.get("voided_at"):
            totals[rid] = totals.get(rid, 0) + int(m["quantity"])
    out = []
    for rid in sorted(seen, key=lambda i: (_fold(by_id[i]["name"]), size_key(by_id[i]["size"]))):
        r = by_id[rid]
        if key is not None and key_of(r) != key:
            continue
        new = totals.get(rid, 0)
        if int(r.get("initial_quantity") or 0) != new:
            out.append({"reference_id": rid, "name": r["name"], "size": r["size"], "color": r.get("color") or "",
                        "old_meta": int(r.get("initial_quantity") or 0), "new_meta": new})
    return out


async def sync_meta(db: AsyncSession, company_id: str, actor: str, reason: str = "meta_cortes", key: Optional[str] = None,
                    apply: bool = True) -> dict:
    """Iguala la meta de cada talla con cortes a la suma de sus cortes vigentes
    (todas, o las de una referencia). Cada cambio queda en la bitacora."""
    rows, moves = await _cut_totals(db, company_id)
    plan = meta_plan(rows, moves, key)
    batch = str(uuid.uuid4())
    if apply and plan:
        for c in plan:
            await db.execute(text("""
                UPDATE product_references SET initial_quantity = :q, updated_at = now() WHERE company_id = :c AND id = :i
            """), {"q": c["new_meta"], "c": company_id, "i": c["reference_id"]})
            await log_change(db, company_id, batch, reason, "product_references", c["reference_id"], "initial_quantity", c["old_meta"], c["new_meta"], actor)
        await db.commit()
    return {"batch_id": batch if apply and plan else None, "changes": plan, "applied": bool(apply and plan)}


# ------------------------------------------------- conversion de tallas (prendas superiores)
TOP_SIZES = ("S", "M", "L")


def convert_size(size: Any) -> Optional[str]:
    """SM -> S, ML -> M; si no, la primera letra S, M o L. Otra talla: None (revisar)."""
    v = re.sub(r"\s+", "", _fold(size)).lower()
    if v.startswith("sm"):
        return "S"
    if v.startswith("ml"):
        return "M"
    for letter in ("s", "m", "l"):
        if v.startswith(letter) and not v.startswith("xs") and not v.startswith("xl"):
            return letter.upper()
    return None


def _letters(size: Any) -> bool:
    return size_key(sizes_of(size)[0] if sizes_of(size) else "")[0] == 1


def in_scope(row: dict) -> bool:
    """Prendas superiores, o sin clasificar con talla de letras."""
    if row.get("archived"):
        return False
    if row.get("body_part"):
        return row["body_part"] == "superior"
    return _letters(row.get("size")) or any(convert_size(t) for t in sizes_of(row.get("size")))


def conversion_plan(rows: list[dict]) -> dict:
    """Plan (sin escribir) de la conversion de tallas de una empresa:
    renames, uniones (dos filas de la misma referencia en la misma talla) y
    "revisar" (tallas que no se convierten o filas con varias tallas que no se
    pueden repartir). Funcion pura."""
    renames, review, merges = [], [], []
    target: dict[str, str] = {}  # id -> talla nueva
    for r in rows:
        if not in_scope(r):
            continue
        tokens = sizes_of(r["size"])
        new = [convert_size(t) for t in tokens]
        if not tokens or any(x is None for x in new):
            review.append({"reference_id": r["id"], "name": r["name"], "size": r["size"], "reason": "talla que no se convierte (revisar)"})
            continue
        if len(set(new)) > 1:
            review.append({"reference_id": r["id"], "name": r["name"], "size": r["size"],
                           "reason": "fila con varias tallas: no se sabe la meta ni el producido por talla (revisar)"})
            continue
        target[r["id"]] = new[0]
        if r["size"] != new[0]:
            renames.append({"reference_id": r["id"], "name": r["name"], "old_size": r["size"], "new_size": new[0]})
    # Uniones: dentro de una referencia (nombre), dos filas activas en la misma talla final.
    final: dict[tuple, list[dict]] = {}
    for r in rows:
        if r.get("archived"):
            continue
        size = target.get(r["id"], r["size"])
        final.setdefault((key_of(r), _fold(size).strip()), []).append(r)
    for (_, size), group in final.items():
        if len(group) < 2:
            continue
        keep = next((r for r in group if r["size"] == target.get(r["id"], r["size"]) and r["id"] not in {x["reference_id"] for x in renames}), None) \
            or sorted(group, key=lambda x: str(x["id"]))[0]
        for r in group:
            if r["id"] != keep["id"]:
                merges.append({"from_id": r["id"], "into_id": keep["id"], "name": r["name"], "old_size": r["size"],
                               "new_size": target.get(keep["id"], keep["size"])})
    # La fila que se une no se renombra: se archiva con su talla de siempre (asi no
    # choca con la que queda); sus movimientos si pasan a la talla nueva.
    losers = {m["from_id"] for m in merges}
    renames = [c for c in renames if c["reference_id"] not in losers]
    return {"renames": renames, "merges": merges, "review": review, "target": target}


REF_TABLES = ("reference_cut_movements", "reference_production_closures", "reference_cycle_resets", "reference_work_sessions",
              "work_sessions", "mini_panel_sales_records", "inventory_locations")


async def _group_totals(db: AsyncSession, company_id: str) -> dict:
    rows = [dict(r) for r in (await db.execute(text(f"""
        SELECT {REF_COLS}, COALESCE(initial_quantity, 0) AS initial_quantity FROM product_references WHERE company_id = :c
    """), {"c": company_id})).mappings().all()]
    finished, _ = await finished_by_reference(db, company_id)
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("archived"):
            continue
        t = out.setdefault(key_of(r), {"meta": 0, "produced": 0})
        t["meta"] += int(r["initial_quantity"])
        t["produced"] += int(finished.get(r["id"], 0))
    return out


async def convert_sizes(db: AsyncSession, company_id: str, actor: str, apply: bool = False) -> dict:
    """Convierte las tallas de prendas superiores (S, M, L) en UNA transaccion:
    renombra filas y los movimientos de corte, une filas duplicadas (suma meta,
    mueve todo lo que apunta a la que sobra y la archiva) y compara la suma de
    meta y producido por referencia antes y despues. Si no cuadra, deshace todo.
    Con apply=False solo calcula y deshace (dry-run)."""
    rows = [dict(r) for r in (await db.execute(text(f"""
        SELECT {REF_COLS}, COALESCE(initial_quantity, 0) AS initial_quantity FROM product_references WHERE company_id = :c
    """), {"c": company_id})).mappings().all()]
    plan = conversion_plan(rows)
    before = await _group_totals(db, company_id)
    batch = str(uuid.uuid4())
    by_id = {r["id"]: r for r in rows}
    moved: list[dict] = []
    try:
        for c in plan["renames"]:
            await db.execute(text("UPDATE product_references SET size = :s, updated_at = now() WHERE company_id = :c AND id = :i"),
                             {"s": c["new_size"], "c": company_id, "i": c["reference_id"]})
            await log_change(db, company_id, batch, "conversion_tallas", "product_references", c["reference_id"], "size", c["old_size"], c["new_size"], actor)
        # Movimientos de corte de las filas convertidas: su talla pasa a la nueva.
        ids = list(plan["target"])
        if ids:
            moves = (await db.execute(text("""
                SELECT id::text AS id, size FROM reference_cut_movements WHERE company_id = :c AND reference_id = ANY(CAST(:ids AS text[]))
            """), {"c": company_id, "ids": ids})).mappings().all()
            for m in moves:
                new = convert_size(m["size"]) if m["size"] else None
                if new and new != m["size"]:
                    await db.execute(text("UPDATE reference_cut_movements SET size = :s WHERE company_id = :c AND id = CAST(:i AS uuid)"),
                                     {"s": new, "c": company_id, "i": m["id"]})
                    await log_change(db, company_id, batch, "conversion_tallas", "reference_cut_movements", m["id"], "size", m["size"], new, actor)
        for mg in plan["merges"]:
            src, dst = by_id[mg["from_id"]], by_id[mg["into_id"]]
            total = int(dst["initial_quantity"]) + int(src["initial_quantity"])
            await db.execute(text("UPDATE product_references SET initial_quantity = :q, updated_at = now() WHERE company_id = :c AND id = :i"),
                             {"q": total, "c": company_id, "i": dst["id"]})
            await log_change(db, company_id, batch, "union_tallas", "product_references", dst["id"], "initial_quantity", dst["initial_quantity"], total, actor)
            dst["initial_quantity"] = total
            for table in REF_TABLES:
                exists = (await db.execute(text("SELECT to_regclass(:t)"), {"t": table})).scalar()
                if not exists:
                    continue
                hit = (await db.execute(text(f"""
                    UPDATE {table} SET reference_id = :dst WHERE company_id::text = :c AND reference_id = :src RETURNING id::text AS id
                """), {"dst": dst["id"], "c": company_id, "src": src["id"]})).scalars().all()
                for row_id in hit:
                    await log_change(db, company_id, batch, "union_tallas", table, row_id, "reference_id", src["id"], dst["id"], actor)
                moved.append({"table": table, "from_id": src["id"], "into_id": dst["id"], "rows": len(hit)})
            for col, new in (("archived", True), ("bot_active", False)):
                await db.execute(text(f"UPDATE product_references SET {col} = :v, updated_at = now() WHERE company_id = :c AND id = :i"),
                                 {"v": new, "c": company_id, "i": src["id"]})
                await log_change(db, company_id, batch, "union_tallas", "product_references", src["id"], col, src.get(col), new, actor)
        after = await _group_totals(db, company_id)
        mismatch = [{"key": k, "before": before.get(k), "after": after.get(k)} for k in set(before) | set(after)
                    if (before.get(k) or {"meta": 0, "produced": 0}) != (after.get(k) or {"meta": 0, "produced": 0})]
        ok = not mismatch
        if apply and ok:
            await db.commit()
        else:
            await db.rollback()
    except Exception:
        await db.rollback()
        raise
    return {"applied": bool(apply and ok), "ok": ok, "batch_id": batch if apply and ok else None, "plan": plan,
            "before": before, "after": after, "mismatch": mismatch, "moved": moved}


# ------------------------------------------------------- orden operacional
MAX_ITEM_MINUTES = 6000


def _applies(item: dict, size: str) -> bool:
    item_size = _fold(item.get("size") or "").strip()
    return not item_size or item_size == _fold(size).strip()


def minutes_for(items: list[dict], size: str = "") -> int:
    """Tiempo por prenda: items "Todas" + los de esa talla ("" = solo los de Todas)."""
    if not size:
        return sum(int(i["minutes"]) for i in items if not str(i.get("size") or "").strip())
    return sum(int(i["minutes"]) for i in items if _applies(i, size))


def pct1(part: Any, whole: Any) -> Optional[float]:
    """Porcentaje con un decimal, redondeo hacia arriba en .5 (igual que la pantalla)."""
    from decimal import ROUND_HALF_UP, Decimal

    if not whole:
        return None
    return float((Decimal(str(part)) / Decimal(str(whole)) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def hm(minutes: int) -> str:
    minutes = int(minutes or 0)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def op_calc(items: list[dict], value: Any, lines: list[dict], view: str = "", decimals: int = 0) -> dict:
    """Orden operacional (la misma formula que la pantalla, references_v2.js opCalc):
    - tiempo de una talla = items "Todas" + items de esa talla;
    - % de un item = sus minutos / tiempo de la talla que se ve;
    - valor del item = valor por prenda x su %; el ultimo item absorbe el
      redondeo para que la suma de exactamente el valor por prenda;
    - tiempo de la orden = suma por talla (tiempo de esa talla x cortes recibidos)."""
    from decimal import ROUND_HALF_UP, Decimal

    value_d = Decimal(str(value or 0))
    q = Decimal(1).scaleb(-decimals) if decimals else Decimal(1)
    total = minutes_for(items, view)
    applicable = [i for i in items if (_applies(i, view) if view else not str(i.get("size") or "").strip())]
    rows, acc = [], Decimal(0)
    for n, item in enumerate(items):
        on = any(x is item for x in applicable)
        pct = pct1(int(item["minutes"]), total) if on and total else None
        val = None
        if on and total:
            if item is applicable[-1]:
                val = value_d - acc
            else:
                val = (value_d * Decimal(int(item["minutes"])) / Decimal(total)).quantize(q, rounding=ROUND_HALF_UP)
                acc += val
        rows.append({**item, "applies": on, "percent": pct,
                     "value": float(val) if val is not None else None})
    per_size = [{"size": ln["size"], "minutes": minutes_for(items, ln["size"]), "received": int(ln.get("received") or 0),
                 "produced": int(ln.get("produced") or 0), "solo_corte": bool(ln.get("solo_corte"))} for ln in lines]
    order_minutes = sum(s["minutes"] * s["received"] for s in per_size)
    received = sum(s["received"] for s in per_size)
    produced = sum(s["produced"] for s in per_size)
    return {
        "view": view, "minutes": total, "minutes_label": hm(total), "value_per_garment": float(value_d),
        "value_per_minute": float((value_d / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if total else None,
        "items": rows, "per_size": per_size, "received": received, "produced": produced,
        "percent": pct1(produced, received),
        "order_minutes": order_minutes, "order_label": hm(order_minutes),
        "extra_sizes": sorted({s["size"] for s in per_size if s["minutes"] != minutes_for(items, "")}, key=size_key),
    }


def validate_op_item(raw: dict, sizes: list[str]) -> dict:
    if not isinstance(raw, dict):
        raise Invalid("item", "datos inválidos")
    name = str(raw.get("name") or "").strip()
    if not name or len(name) > 120:
        raise Invalid("name", "escribe el nombre del ítem")
    try:
        hours = int(raw.get("hours") or 0)
        mins = int(raw.get("minutes") or 0)
    except (TypeError, ValueError):
        raise Invalid("minutes", "horas y minutos deben ser números") from None
    if hours < 0 or mins < 0 or mins > 59 and hours:
        raise Invalid("minutes", "minutos entre 0 y 59")
    total = hours * 60 + mins
    if not 1 <= total <= MAX_ITEM_MINUTES:
        raise Invalid("minutes", "el tiempo debe ser mayor a cero")
    size = str(raw.get("size") or "").strip()
    if size.lower() in ("todas", "all"):
        size = ""
    if size:
        match = next((s for s in sizes if _fold(s).strip() == _fold(size).strip()), None)
        if not match:
            raise Invalid("size", f"la talla {size} no es de esta referencia")
        size = match
    return {"name": name, "minutes": total, "size": size}


def validate_op_value(raw: Any) -> float:
    try:
        value = float(str(raw if raw is not None else "").replace(",", "."))
    except ValueError:
        raise Invalid("value_per_garment", "escribe un valor") from None
    if not 0 <= value <= 1_000_000_000:
        raise Invalid("value_per_garment", "valor fuera de rango")
    return value


async def op_items(db: AsyncSession, company_id: str, key: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, name, minutes, size, position, created_by, created_at, updated_by, updated_at
        FROM reference_op_items WHERE company_id = :c AND group_key = :k ORDER BY position, created_at
    """), {"c": company_id, "k": key})).mappings().all()
    return [dict(r) for r in rows]


async def op_value(db: AsyncSession, company_id: str, key: str) -> dict:
    row = (await db.execute(text("""
        SELECT value_per_garment, updated_by, updated_at FROM reference_op_settings WHERE company_id = :c AND group_key = :k
    """), {"c": company_id, "k": key})).mappings().first()
    return {"value_per_garment": float(row["value_per_garment"]) if row else 0.0,
            "updated_by": row["updated_by"] if row else "", "updated_at": row["updated_at"] if row else None}


async def set_op_value(db: AsyncSession, company_id: str, key: str, value: float, actor: str) -> None:
    await db.execute(text("""
        INSERT INTO reference_op_settings (company_id, group_key, value_per_garment, updated_by, updated_at)
        VALUES (:c, :k, :v, :by, now())
        ON CONFLICT (company_id, group_key) DO UPDATE SET value_per_garment = EXCLUDED.value_per_garment,
            updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": company_id, "k": key, "v": value, "by": actor[:200]})
    await db.commit()


async def add_op_item(db: AsyncSession, company_id: str, key: str, item: dict, actor: str) -> str:
    position = (await db.execute(text("""
        SELECT COALESCE(max(position), -1) + 1 FROM reference_op_items WHERE company_id = :c AND group_key = :k
    """), {"c": company_id, "k": key})).scalar() or 0
    new_id = (await db.execute(text("""
        INSERT INTO reference_op_items (company_id, group_key, name, minutes, size, position, created_by, updated_by)
        VALUES (:c, :k, :n, :m, :s, :p, :by, :by) RETURNING id::text
    """), {"c": company_id, "k": key, "n": item["name"], "m": item["minutes"], "s": item["size"], "p": int(position),
           "by": actor[:200]})).scalar()
    await db.commit()
    return new_id


async def update_op_item(db: AsyncSession, company_id: str, key: str, item_id: str, item: dict, actor: str) -> bool:
    result = await db.execute(text("""
        UPDATE reference_op_items SET name = :n, minutes = :m, size = :s, updated_by = :by, updated_at = now()
        WHERE company_id = :c AND group_key = :k AND id = CAST(:i AS uuid)
    """), {"c": company_id, "k": key, "i": item_id, "n": item["name"], "m": item["minutes"], "s": item["size"], "by": actor[:200]})
    await db.commit()
    return bool(result.rowcount)


async def delete_op_item(db: AsyncSession, company_id: str, key: str, item_id: str) -> bool:
    result = await db.execute(text("""
        DELETE FROM reference_op_items WHERE company_id = :c AND group_key = :k AND id = CAST(:i AS uuid)
    """), {"c": company_id, "k": key, "i": item_id})
    await db.commit()
    return bool(result.rowcount)


async def reorder_op_items(db: AsyncSession, company_id: str, key: str, ids: list[str], actor: str) -> None:
    current = [i["id"] for i in await op_items(db, company_id, key)]
    if sorted(current) != sorted(str(x) for x in ids):
        raise Invalid("ids", "el orden debe incluir todos los ítems de la referencia")
    for n, item_id in enumerate(ids):
        await db.execute(text("""
            UPDATE reference_op_items SET position = :p, updated_by = :by, updated_at = now()
            WHERE company_id = :c AND group_key = :k AND id = CAST(:i AS uuid)
        """), {"c": company_id, "k": key, "i": str(item_id), "p": n, "by": actor[:200]})
    await db.commit()
