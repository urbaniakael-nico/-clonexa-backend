"""Referencias v2 (pantalla nueva detras del interruptor references_v2).

Solo agrega: nunca cambia el producido, la meta ni los cierres de produccion.
- Catalogo de prendas y tallas: garment_catalog.json (unico y editable).
- Clasificacion opcional (gender, body_part, garment_type): solo esas tres
  columnas; nunca se clasifica sola (las sugerencias solo se muestran).
- Movimientos de corte (reference_cut_movements): ingreso, novedad por
  seccion y envio a despliegue. Solo se agregan; anular no borra.
- Balance de la referencia (todas sus tallas: mismo nombre y color, sin
  importar mayusculas, tildes ni espacios): disponible = recibido - novedades
  - despliegue. La agrupacion es UNA sola (group_key) para Cortes, Orden
  operacional y Estado de referencias.
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


def group_key(name: Any, color: Any) -> str:
    """Referencia = nombre + color. UNA sola regla para Cortes, Orden operacional
    y Estado: sin importar mayusculas, tildes ni espacios."""
    norm = lambda v: re.sub(r"\s+", "", _fold(v))  # noqa: E731
    return f"{norm(name)}|{norm(color)}"


def key_of(row: dict) -> str:
    return group_key(row.get("name"), row.get("color"))


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
    """Una tarjeta por referencia (nombre + color) con una linea por talla:
    las filas de product_references activas y las tallas que solo tienen
    cortes ("solo corte"), en el orden del catalogo. Funcion pura."""
    groups: dict[str, dict] = {}
    key_by_id = {r["id"]: key_of(r) for r in rows}
    for r in sorted(rows, key=lambda x: size_key(x["size"])):
        if r.get("archived"):
            continue
        g = groups.setdefault(key_of(r), {"key": key_of(r), "name": r["name"], "color": r["color"], "lines": [], "unsized_received": 0})
        tokens = [_fold(t).strip() for t in sizes_of(r["size"])]
        g["lines"].append({
            "size": r["size"], "reference_id": r["id"], "solo_corte": False, "tokens": tokens,
            "combined": combined_sizes(r["size"]), "meta": int(r.get("initial_quantity") or 0),
            "produced": int(finished.get(r["id"], 0)), "bot_active": r.get("bot_active") is True, "received": 0,
            "anchor_id": None,
        })
    for m in moves:
        g = groups.get(key_by_id.get(m["reference_id"], ""))
        if not g or m.get("voided_at") or m.get("kind") != "ingreso":
            continue
        size = _fold(m.get("size") or "").strip()
        if not size:
            g["unsized_received"] += int(m["quantity"])
            continue
        line = next((x for x in g["lines"] if size in x["tokens"]), None)
        if line is None:
            line = {"size": str(m["size"]).strip(), "reference_id": None, "solo_corte": True, "tokens": [size], "combined": False,
                    "meta": 0, "produced": 0, "bot_active": False, "received": 0, "anchor_id": m["reference_id"]}
            g["lines"].append(line)
        line["received"] += int(m["quantity"])
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
        g.update({
            "received": received, "produced": produced, "meta": sum(x["meta"] for x in g["lines"]),
            "percent": pct1(produced, received),
            "solo_corte": [x["size"] for x in g["lines"] if x["solo_corte"]],
        })
        out.append(g)
    out.sort(key=lambda g: (_fold(g["name"]), _fold(g["color"])))
    return out


async def reference_groups(db: AsyncSession, company_id: str) -> list[dict]:
    rows = [dict(r) for r in (await db.execute(text(f"""
        SELECT {REF_COLS}, COALESCE(initial_quantity, 0) AS initial_quantity FROM product_references WHERE company_id = :c
    """), {"c": company_id})).mappings().all()]
    moves = [dict(r) for r in (await db.execute(text("""
        SELECT reference_id, kind, size, quantity, voided_at FROM reference_cut_movements
        WHERE company_id = :c AND kind = 'ingreso' AND voided_at IS NULL
    """), {"c": company_id})).mappings().all()]
    finished, _ = await finished_by_reference(db, company_id)
    return build_groups(rows, moves, finished)


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
