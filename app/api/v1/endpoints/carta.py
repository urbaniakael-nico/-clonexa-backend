"""Modulo CARTA (049H): platos, recetas e insumos.

Solo para empresas con el modulo "carta" (hoy ASADERO EL SOCIO, migracion
021w). Sin el modulo, la carta del mesero, la caja, los domicilios y el QR
siguen saliendo del inventario como siempre (The Time Machine no cambia).

Con el modulo:
- hospitality_inventory_lite / build_waiter_menu leen los PLATOS de
  carta_items (nunca un consumible).
- 049K: la Carta es la UNICA fuente de categorias del menu (mesero, caja,
  domicilios y QR): categoria -> subcategoria opcional, cada una con su
  imagen, estacion de cocina, notas rapidas y termino; los platos van sin
  foto y heredan la estacion de su categoria.
- Al armar un pedido, cada linea guarda que insumos consume y a que costo
  (attach_consumption); _deduct_inventory y la edicion de pedidos pendientes
  descuentan esos insumos.

Endpoints /carta/companies/{company_id}/...: sesion de la empresa con rol
administrador/dueño/gerente (o Admin V2) y el modulo activo.
"""
from __future__ import annotations

import io
import json
import logging
import secrets
import unicodedata
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.services import carta as engine
from app.services import media_storage
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()

MODULE_CODE = "carta"
CARTA_ADMIN_ROLES = ADMIN_ROLES | {"manager", "gerencia", "gerente", "dueno", "dueño", "owner", "propietario", "administrador"}


# ------------------------------------------------------------ helpers ---
async def carta_enabled(db: AsyncSession, company_id: Any) -> bool:
    try:
        await require_enabled_module(db, uuid.UUID(str(company_id)), MODULE_CODE)
        return True
    except HTTPException:
        return False
    except Exception as exc:  # sin poder leer los modulos: camino de siempre
        logging.getLogger("clonexa.carta").warning("No se pudo verificar el modulo carta: %s", exc)
        return False


def _clean(value: Any, limit: int = 220) -> str:
    return " ".join(str(value or "").split())[:limit]


def category_slug(label: Any) -> str:
    """"PLATOS A LA CARTA" -> "platos_a_la_carta" (llave de la categoria)."""
    text_value = unicodedata.normalize("NFKD", str(label or "")).encode("ascii", "ignore").decode("ascii").lower()
    return "_".join("".join(ch if ch.isalnum() else " " for ch in text_value).split())[:80]


def display_name(dish: dict) -> str:
    presentation = _clean(dish.get("presentation"), 60)
    return f"{dish['name']} {presentation}".strip() if presentation else dish["name"]


async def load_insumos(db: AsyncSession, company_id: Any) -> dict[str, dict]:
    result = await db.execute(text("""
        SELECT id, COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), NULLIF(reference, ''), sku, id::text) AS name,
               sku, current_stock, min_stock, status, entry_price, sale_price, avg_cost,
               item_type, purchase_unit, consumption_unit, units_per_purchase, size_value, size_unit
        FROM inventory_items
        WHERE company_id = CAST(:company_id AS uuid) AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
        ORDER BY lower(COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), sku, id::text))
    """), {"company_id": str(company_id)})
    insumos = {str(r["id"]): dict(r) for r in result.mappings().all()}
    for key, equivalences in (await load_equivalences(db, company_id)).items():
        if key in insumos:
            insumos[key]["equivalences"] = equivalences
    return insumos


async def load_equivalences(db: AsyncSession, company_id: Any) -> dict[str, dict[str, Decimal]]:
    """049O: "1 <unidad> = N <unidad del inventario>" guardado por insumo
    (cuanto pesa una unidad, cuantos gramos tiene una cucharada...)."""
    exists = (await db.execute(text("SELECT to_regclass('public.carta_unit_equivalences') IS NOT NULL AS exists"))).mappings().first()
    if not exists or not exists.get("exists"):
        return {}
    rows = (await db.execute(text("""
        SELECT inventory_item_id, unit, amount FROM carta_unit_equivalences WHERE company_id = CAST(:company_id AS uuid)
    """), {"company_id": str(company_id)})).mappings().all()
    out: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        out.setdefault(str(row["inventory_item_id"]), {})[row["unit"]] = Decimal(str(row["amount"]))
    return out


async def load_dishes(db: AsyncSession, company_id: Any) -> tuple[list[dict], dict[str, list[dict]]]:
    dishes = [dict(r) for r in (await db.execute(text("""
        SELECT id, name, price, category_key, station, requires_term, allows_portions, kind,
               inventory_item_id, direct_qty, active, position, presentation, category_id
        FROM carta_items WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY position, lower(name)
    """), {"company_id": str(company_id)})).mappings().all()]
    lines: dict[str, list[dict]] = {}
    for row in (await db.execute(text("""
        SELECT carta_item_id, inventory_item_id, component_item_id, quantity, yield_pct, position, unit
        FROM carta_recipe_lines WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY position
    """), {"company_id": str(company_id)})).mappings().all():
        lines.setdefault(str(row["carta_item_id"]), []).append(dict(row))
    return dishes, lines


def _available(dish: dict, insumos: dict[str, dict], catalog: tuple[dict, dict] | None = None, depth: int = 0) -> bool:
    if not dish.get("active") and depth == 0:
        return False
    if dish.get("kind") == "preparado":
        return True  # los preparados no bloquean la venta por existencias
    if dish.get("kind") == "combo":
        by_id, lines_map = catalog or ({}, {})
        lines = lines_map.get(str(dish["id"]), [])
        if not lines or depth >= engine.MAX_COMBO_DEPTH:
            return False
        for line in lines:
            if line.get("component_item_id"):
                part = by_id.get(str(line["component_item_id"]))
                if not part or not _available(part, insumos, catalog, depth + 1):
                    return False
            else:
                insumo = insumos.get(str(line.get("inventory_item_id")))
                if not insumo or str(insumo.get("status") or "active") != "active":
                    return False
        return True
    insumo = insumos.get(str(dish.get("inventory_item_id")))
    return bool(insumo) and str(insumo.get("status") or "active") == "active"


def _catalog(dishes: list[dict], lines: dict[str, list[dict]]) -> tuple[dict, dict]:
    return {str(d["id"]): d for d in dishes}, lines


# ---------------------------------------------------------- categorias ---
# 049K: la carta de la empresa es un arbol de dos niveles con imagen
# (categoria -> subcategoria opcional); los platos van sin imagen. Es la
# unica fuente de las categorias del mesero, la caja, el QR y domicilios.
async def load_categories(db: AsyncSession, company_id: Any) -> list[dict]:
    result = await db.execute(text("""
        SELECT id, parent_id, label, position, station, quick_notes, requires_term
        FROM carta_categories WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY position, lower(label)
    """), {"company_id": str(company_id)})
    out = []
    for raw in result.mappings().all():
        row = dict(raw)
        notes = row.get("quick_notes")
        if isinstance(notes, str):
            try:
                notes = json.loads(notes or "[]")
            except ValueError:
                notes = []
        out.append({"id": str(row["id"]), "parent_id": str(row["parent_id"]) if row.get("parent_id") else None,
                    "label": row["label"], "position": int(row.get("position") or 0), "station": row.get("station") or "",
                    "quick_notes": [n for n in notes if isinstance(n, str)] if isinstance(notes, list) else [],
                    "requires_term": bool(row.get("requires_term"))})
    return out


async def ensure_categories(db: AsyncSession, company_id: Any) -> list[dict]:
    """Una empresa que estrena Carta arranca con las categorias sugeridas."""
    categories = await load_categories(db, company_id)
    if categories:
        return categories
    for position, (label, _hint) in enumerate(engine.PRESET_CATEGORIES, start=1):
        await db.execute(text("""
            INSERT INTO carta_categories (id, company_id, parent_id, label, position)
            VALUES (CAST(:id AS uuid), CAST(:company_id AS uuid), NULL, :label, :position)
        """), {"id": str(uuid.uuid4()), "company_id": str(company_id), "label": label, "position": position})
    await db.commit()
    return await load_categories(db, company_id)


def resolve_category(dish: dict, by_id: dict[str, dict]) -> tuple[dict | None, dict | None]:
    """(categoria, subcategoria) del plato; la subcategoria puede faltar."""
    leaf = by_id.get(str(dish.get("category_id") or ""))
    if not leaf:
        return None, None
    if leaf.get("parent_id"):
        top = by_id.get(leaf["parent_id"])
        return (top, leaf) if top else (leaf, None)
    return leaf, None


def effective_kitchen(dish: dict, top: dict | None, sub: dict | None) -> dict:
    """Estacion, termino y notas rapidas: los del plato y si no, los de su
    subcategoria o categoria. Sin estacion la comanda no le llega a una
    cocina que trabaja por estaciones."""
    return {
        "station": _clean(dish.get("station"), 80) or (sub or {}).get("station") or (top or {}).get("station") or "",
        "requires_term": bool(dish.get("requires_term") or (sub or {}).get("requires_term") or (top or {}).get("requires_term")),
        "quick_notes": (sub or {}).get("quick_notes") or (top or {}).get("quick_notes") or [],
    }


async def carta_inventory_lite(db: AsyncSession, company_id: Any) -> list[dict]:
    """Platos de la carta con la misma forma que devuelve inventory-lite."""
    insumos = await load_insumos(db, company_id)
    dishes, lines = await load_dishes(db, company_id)
    categories = {c["id"]: c for c in await load_categories(db, company_id)}
    catalog = _catalog(dishes, lines)
    out = []
    for dish in dishes:
        insumo = insumos.get(str(dish.get("inventory_item_id"))) if dish.get("kind") == "directo" else None
        price = float(Decimal(str(dish.get("price") or 0)))
        top, sub = resolve_category(dish, categories)
        out.append({
            "id": str(dish["id"]), "sku": (insumo or {}).get("sku") or "", "name": display_name(dish),
            "price": price, "unit_price": price,
            "stock": float(Decimal(str((insumo or {}).get("current_stock") or 0))) if insumo else 0.0,
            "active": _available(dish, insumos, catalog), "allows_portions": bool(dish.get("allows_portions")),
            "category_key": top["id"] if top else "", "category_label": top["label"] if top else "",
            "subcategory_key": sub["id"] if sub else "", "subcategory_label": sub["label"] if sub else "",
            **effective_kitchen(dish, top, sub), "carta_kind": dish.get("kind") or "directo",
        })
    return out


async def _image_versions(db: AsyncSession, company_id: Any) -> dict[str, str]:
    """Imagenes guardadas (id -> version para que el celular no muestre una vieja)."""
    result = await db.execute(text("SELECT to_regclass('public.hospitality_product_images') IS NOT NULL AS exists"))
    row = result.mappings().first()
    if not row or not row.get("exists"):
        return {}
    rows = await db.execute(text("""
        SELECT inventory_item_id, updated_at FROM hospitality_product_images
        WHERE company_id = CAST(:company_id AS uuid) AND image_bytes IS NOT NULL
    """), {"company_id": str(company_id)})
    out = {}
    for r in rows.mappings().all():
        stamp = r.get("updated_at")
        out[str(r["inventory_item_id"])] = str(int(stamp.timestamp())) if hasattr(stamp, "timestamp") else "1"
    return out


def _category_node(category: dict, images: dict[str, str]) -> dict:
    return {"key": category["id"], "label": category["label"], "station": category["station"],
            "quick_notes": category["quick_notes"], "requires_term": category["requires_term"],
            "has_image": category["id"] in images, "image_item_id": category["id"],
            "image_version": images.get(category["id"], ""), "image_fit": "contain"}


async def carta_menu_categories(db: AsyncSession, company_id: Any, products: list[dict]) -> list[dict]:
    """Categorias del menu (mesero, caja, QR, domicilios) desde la Carta:
    cada categoria trae TODOS sus platos en `products` (asi un panel que no
    conoce subcategorias sigue funcionando igual) y sus `subcategories` con
    los platos de cada una. Un plato sin categoria cae en OTROS: nunca se
    pierde de la carta."""
    categories = await ensure_categories(db, company_id)
    images = await _image_versions(db, company_id)
    tops = [c for c in categories if not c["parent_id"]]
    top_ids = {c["id"] for c in tops}
    out = []
    for top in tops:
        entry = {**_category_node(top, images), "subcategories": [],
                 "products": [p for p in products if p.get("category_key") == top["id"]]}
        for sub in (c for c in categories if c["parent_id"] == top["id"]):
            sub_products = [p for p in entry["products"] if p.get("subcategory_key") == sub["id"]]
            if sub_products:
                entry["subcategories"].append({**_category_node(sub, images), "products": sub_products})
        if entry["products"]:
            out.append(entry)
    loose = [p for p in products if p.get("category_key") not in top_ids]
    if loose:
        out.append({"key": "otros", "label": "OTROS", "station": "", "quick_notes": [], "requires_term": False,
                    "has_image": False, "image_item_id": "", "image_version": "", "image_fit": "contain",
                    "subcategories": [], "products": loose})
    return out


async def attach_consumption(db: AsyncSession, company_id: Any, rows: list[dict]) -> list[dict]:
    """Congela en cada linea del pedido los insumos que consume y su costo."""
    insumos = await load_insumos(db, company_id)
    dishes, lines = await load_dishes(db, company_id)
    catalog = _catalog(dishes, lines)
    by_id = catalog[0]
    for row in rows:
        dish = by_id.get(str(row.get("inventory_item_id") or row.get("product_id") or ""))
        if not dish:
            continue
        dish_lines = lines.get(str(dish["id"]), [])
        entries = engine.consumption(dish, dish_lines, row.get("quantity"), catalog, insumos=insumos)
        cost, priced = engine.cost_of(entries, insumos)
        # 049O: con una unidad sin equivalencia o un costo desproporcionado, la
        # venta queda "sin costo" (los reportes la marcan) en vez de una cifra falsa.
        sale_price = engine.dec(dish.get("price")) * engine.dec(row.get("quantity") or 1)
        if engine.suspect_lines(priced, insumos, sale_price) or any(
                l.get("inventory_item_id") and engine.line_need(l, insumos) is None for l in dish_lines if dish.get("kind") != "directo"):
            cost = None
        row["menu_item_id"] = str(dish["id"])
        row["carta_kind"] = dish.get("kind") or "directo"
        row["consumption"] = priced
        row["cost"] = float(cost) if cost is not None else None
    return rows


def consumption_quantities(items: list[dict] | None) -> tuple[dict[str, float], set[str]]:
    """Insumo -> cantidad consumida por lineas con carta, y los insumos que no
    bloquean la venta (ingredientes de platos preparados)."""
    quantities: dict[str, float] = {}
    soft: set[str] = set()
    for item in items or []:
        for entry in item.get("consumption") or []:
            key = str(entry.get("inventory_item_id") or "")
            if not key:
                continue
            quantities[key] = round(quantities.get(key, 0.0) + float(entry.get("quantity") or 0), 4)
            if not entry.get("blocking"):
                soft.add(key)
    return quantities, soft


# ---------------------------------------------------------------- auth ---
async def require_carta_admin(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> str:
    await require_enabled_module(db, company_id, MODULE_CODE)
    if await active_admin_v2_session(request, db):
        return "Admin V2"
    user = await require_company_user_for_tenant(db, authorization, company_id, allowed_roles=CARTA_ADMIN_ROLES)
    return str(getattr(user, "full_name", "") or "Administrador")


# ------------------------------------------------------------- lectura ---
async def load_last_purchases(db: AsyncSession, company_id: Any) -> dict[str, dict]:
    """049Q: ultima compra de cada insumo (cantidad, unidad, total pagado y el
    costo que calculo el sistema). Las que vienen de la migracion 022f quedan
    marcadas como "reinterpretada" para que el dueño las revise."""
    exists = (await db.execute(text("SELECT to_regclass('public.carta_purchases') IS NOT NULL AS exists"))).mappings().first()
    if not exists or not exists.get("exists"):
        return {}
    rows = (await db.execute(text("""
        SELECT DISTINCT ON (inventory_item_id) inventory_item_id, quantity, unit, total_paid, base_quantity, unit_cost, source, created_at
        FROM carta_purchases WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY inventory_item_id, created_at DESC
    """), {"company_id": str(company_id)})).mappings().all()
    out = {}
    for row in rows:
        stamp = row.get("created_at")
        out[str(row["inventory_item_id"])] = {
            "quantity": float(Decimal(str(row["quantity"]))), "unit": row["unit"],
            "unit_label": engine.RECIPE_UNITS.get(row["unit"], row["unit"]),
            "total_paid": float(Decimal(str(row["total_paid"]))), "base_quantity": float(Decimal(str(row["base_quantity"]))),
            "unit_cost": float(Decimal(str(row["unit_cost"]))), "reinterpreted": row.get("source") == "reinterpretada_022f",
            "created_at": stamp.isoformat() if hasattr(stamp, "isoformat") else None,
        }
    return out


def _insumo_payload(row: dict, last_purchase: dict | None = None) -> dict:
    unit = engine.unit_cost(row)
    natural = engine.natural_unit(row)
    factor = engine.natural_factor(row)
    stock_nat = engine.stock_natural(row)
    return {
        "id": str(row["id"]), "name": row["name"], "item_type": row.get("item_type") or "venta_directa",
        "purchase_unit": row.get("purchase_unit") or "unidad", "consumption_unit": row.get("consumption_unit") or "unidad",
        "units_per_purchase": float(Decimal(str(row.get("units_per_purchase") or 1))),
        "stock": float(Decimal(str(row.get("current_stock") or 0))), "min_stock": float(Decimal(str(row.get("min_stock") or 0))),
        "avg_cost": float(unit) if unit is not None else None, "status": row.get("status") or "active",
        # 049K: precio de venta cargado en el insumo (un "producto del
        # inventario" lo trae al asistente para no pedirlo dos veces).
        "sale_price": float(Decimal(str(row.get("sale_price") or 0))),
        # 049O: equivalencias guardadas (1 <unidad> = N <unidad del inventario>)
        # y el tamaño del articulo, que sirve de sugerencia al pedirlas.
        "equivalences": {k: float(v) for k, v in (row.get("equivalences") or {}).items()},
        "size_value": float(row["size_value"]) if row.get("size_value") is not None else None,
        "size_unit": row.get("size_unit") or "",
        # 049P: se compra por unidad y se consume en g/ml sin saber cuanto pesa
        # la unidad: la pantalla lo pregunta una vez.
        "purchase_weight_missing": engine.purchase_weight_missing(row),
        "purchase_price": float(Decimal(str((row.get("avg_cost") or 0) if engine.dec(row.get("avg_cost")) > 0 else (row.get("entry_price") or 0)))),
        # 049Q: la existencia en su unidad natural (80 kg) con su equivalente en
        # la unidad base (80.000 g), el costo por unidad natural y la ultima compra.
        "unit": natural, "unit_label": engine.RECIPE_UNITS.get(natural, natural),
        "natural_factor": float(factor) if factor is not None else None,
        "stock_natural": float(stock_nat) if stock_nat is not None else None,
        "min_stock_natural": float((engine.dec(row.get("min_stock")) / factor).quantize(engine.QTY)) if factor else None,
        "cost_per_unit": float((unit * factor).quantize(engine.MONEY)) if unit is not None and factor else None,
        "last_purchase": last_purchase,
    }


async def _settings(db: AsyncSession, company_id: uuid.UUID) -> dict:
    result = await db.execute(text("""
        SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:company_id AS uuid) AND LOWER(m.code) = 'carta' LIMIT 1
    """), {"company_id": str(company_id)})
    row = result.mappings().first()
    raw = (row or {}).get("settings") or {}
    if isinstance(raw, str):
        raw = json.loads(raw or "{}")
    return raw if isinstance(raw, dict) else {}


async def _save_settings(db: AsyncSession, company_id: uuid.UUID, patch: dict) -> None:
    await db.execute(text("""
        UPDATE company_modules SET settings = COALESCE(settings, '{}'::jsonb) || CAST(:s AS jsonb), updated_at = now()
        WHERE company_id = CAST(:company_id AS uuid) AND module_id = (SELECT id FROM modules WHERE LOWER(code) = 'carta' LIMIT 1)
    """), {"s": json.dumps(patch, ensure_ascii=False), "company_id": str(company_id)})


async def _stations(db: AsyncSession, company_id: uuid.UUID, categories: list[dict]) -> list[str]:
    """Estaciones de cocina que ya usa la empresa (las del mesero/cocina y
    las de sus categorias), para elegirlas sin escribirlas."""
    from app.api.v1.endpoints.waiter_ordering import _module_settings

    configured = (await _module_settings(db, company_id)).get("stations")
    out: list[str] = []
    for name in [*(configured if isinstance(configured, list) else []), *[c["station"] for c in categories]]:
        clean = _clean(name, 80)
        if clean and clean.lower() not in {s.lower() for s in out}:
            out.append(clean)
    return out


def _category_tree(categories: list[dict], images: dict[str, str], dishes: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for dish in dishes:
        key = str(dish.get("category_id") or "")
        counts[key] = counts.get(key, 0) + 1
    hints = dict(engine.PRESET_CATEGORIES)

    def node(c: dict) -> dict:
        return {**c, "hint": hints.get(c["label"], ""), "has_image": c["id"] in images,
                "image_version": images.get(c["id"], ""), "dish_count": counts.get(c["id"], 0)}

    return [{**node(top), "children": [node(sub) for sub in categories if sub["parent_id"] == top["id"]]}
            for top in categories if not top["parent_id"]]


async def _carta_payload(db: AsyncSession, company_id: uuid.UUID) -> dict:
    insumos = await load_insumos(db, company_id)
    dishes, lines = await load_dishes(db, company_id)
    categories = await ensure_categories(db, company_id)
    by_category = {c["id"]: c for c in categories}
    catalog = _catalog(dishes, lines)
    images = await _image_versions(db, company_id)
    settings = await _settings(db, company_id)
    items = []
    for dish in dishes:
        dish_lines = lines.get(str(dish["id"]), [])
        summary = engine.dish_summary(dish, dish_lines, insumos, catalog)
        top, sub = resolve_category(dish, by_category)
        items.append({
            "id": str(dish["id"]), "name": dish["name"], "price": float(Decimal(str(dish["price"] or 0))),
            "presentation": dish.get("presentation") or "", "display_name": display_name(dish),
            "category_id": str(dish["category_id"]) if dish.get("category_id") and top else None,
            "category_label": top["label"] if top else "", "subcategory_label": sub["label"] if sub else "",
            "top_category_id": top["id"] if top else None,
            "station": dish.get("station") or "", "effective_station": effective_kitchen(dish, top, sub)["station"],
            "requires_term": bool(dish.get("requires_term")), "allows_portions": bool(dish.get("allows_portions")),
            "kind": dish.get("kind") or "directo", "active": bool(dish.get("active")),
            "inventory_item_id": str(dish["inventory_item_id"]) if dish.get("inventory_item_id") else None,
            "direct_qty": float(Decimal(str(dish.get("direct_qty") or 1))),
            "available": _available(dish, insumos, catalog),
            "recipe": _with_shares([_line_payload(l, insumos, catalog[0]) for l in dish_lines], dish.get("price")),
            **{k: summary[k] for k in ("cost", "margin", "margin_pct", "below_cost", "missing_cost", "no_recipe",
                                       "missing_equivalence", "cost_suspect")},
        })
    purchases = await load_last_purchases(db, company_id)
    return {"items": items, "insumos": [_insumo_payload(r, purchases.get(key)) for key, r in insumos.items()],
            "item_types": engine.ITEM_TYPES, "purchase_units": engine.PURCHASE_UNITS,
            "consumption_units": engine.CONSUMPTION_UNITS, "recipe_units": engine.RECIPE_UNITS,
            "categories": _category_tree(categories, images, dishes),
            "stations": await _stations(db, company_id, categories),
            "company_id": str(company_id), "qr_ready": bool(settings.get("qr_token"))}


def _line_payload(line: dict, insumos: dict[str, dict], dishes_by_id: dict[str, dict]) -> dict:
    if line.get("component_item_id"):
        part = dishes_by_id.get(str(line["component_item_id"])) or {}
        return {"component_item_id": str(line["component_item_id"]), "inventory_item_id": None,
                "insumo": display_name(part) if part else "Plato borrado", "unit": "plato",
                "quantity": float(Decimal(str(line["quantity"]))), "yield_pct": 100.0}
    insumo = insumos.get(str(line.get("inventory_item_id"))) or {}
    unit = engine.recipe_unit(line.get("unit")) or engine.default_recipe_unit(insumo)
    need = engine.line_need({**line, "unit": unit}, insumos)
    if need is not None:
        need = need.quantize(engine.QTY)  # lo mismo que se descuenta y que suma el costo del plato
    unit_cost = engine.unit_cost(insumo) if insumo else None
    return {"component_item_id": None, "inventory_item_id": str(line["inventory_item_id"]),
            "insumo": insumo.get("name") or "Insumo borrado", "unit": unit, "unit_label": engine.RECIPE_UNITS[unit],
            "stock_unit": insumo.get("consumption_unit") or "unidad",
            "quantity": float(Decimal(str(line["quantity"]))), "yield_pct": float(Decimal(str(line.get("yield_pct") or 100))),
            # 049N/049O: lo que descuenta del inventario por porcion y cuanto
            # cuesta; sin equivalencia, ninguna de las dos (se pide en pantalla)
            "needs_equivalence": need is None,
            "stock_quantity": float(need.quantize(engine.QTY)) if need is not None else None,
            "cost": float((unit_cost * need).quantize(engine.MONEY)) if unit_cost is not None and need is not None else None}


def _with_shares(recipe: list[dict], price: Any = 0) -> list[dict]:
    """Aporte de cada ingrediente al costo del plato (para ver cual pesa mas)
    y el aviso cuando un ingrediente solo cuesta mas que el plato."""
    total = sum((Decimal(str(l["cost"])) for l in recipe if l.get("cost") is not None), Decimal("0"))
    price = engine.dec(price)
    for line in recipe:
        cost = line.get("cost")
        line["share_pct"] = float((Decimal(str(cost)) / total * 100).quantize(Decimal("0.1"))) if cost is not None and total > 0 else None
        line["cost_suspect"] = bool(cost is not None and price > 0 and Decimal(str(cost)) > price * engine.SUSPECT_SHARE_OF_PRICE)
    return recipe


@router.get("/companies/{company_id}")
async def get_carta(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: str = Depends(require_carta_admin)) -> dict:
    return await _carta_payload(db, company_id)


@router.get("/companies/{company_id}/alerts")
async def carta_alerts(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: str = Depends(require_carta_admin)) -> dict:
    data = await _carta_payload(db, company_id)
    return {
        "negative_stock": [{"name": i["name"], "stock": i["stock"], "unit": i["consumption_unit"]}
                           for i in data["insumos"] if i["stock"] < 0],
        "below_cost": [{"name": d["name"], "price": d["price"], "cost": d["cost"]} for d in data["items"] if d["below_cost"]],
        "no_recipe": [d["name"] for d in data["items"] if d["no_recipe"] and d["active"]],
    }


# ------------------------------------------------------------ platos ---
class DishIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=220)
    presentation: str = Field(default="", max_length=60)
    price: float = Field(default=0, ge=0)
    category_id: str | None = Field(default=None, max_length=40)
    station: str = Field(default="", max_length=80)
    requires_term: bool = False
    allows_portions: bool = False
    kind: str = Field(default="directo")
    inventory_item_id: str | None = None
    direct_qty: float = Field(default=1, gt=0)
    active: bool = True


async def _check_category(db: AsyncSession, company_id: uuid.UUID, category_id: str | None) -> tuple[str, str]:
    """(id, etiqueta de la categoria principal); vacio = sin categoria."""
    if not category_id:
        return "", ""
    categories = {c["id"]: c for c in await load_categories(db, company_id)}
    leaf = categories.get(str(category_id))
    if not leaf:
        raise HTTPException(status_code=400, detail="Esa categoría no existe en tu carta.")
    top, _sub = resolve_category({"category_id": leaf["id"]}, categories)
    return leaf["id"], (top or leaf)["label"]


async def _validate_dish(db: AsyncSession, company_id: uuid.UUID, payload: DishIn) -> dict:
    kind = payload.kind if payload.kind in engine.DISH_KINDS else None
    if not kind:
        raise HTTPException(status_code=400, detail="Tipo de plato inválido (directo, preparado o combo).")
    insumo_id = None
    if kind == "directo":
        insumos = await load_insumos(db, company_id)
        insumo = insumos.get(str(payload.inventory_item_id or ""))
        try:
            engine.validate_link(insumo)
        except ValueError as exc:
            detail = ("Un consumible (gas, servilletas...) no se vende: no puede ser un plato."
                      if "consumible" in str(exc) else "Elige el insumo que descuenta este plato.")
            raise HTTPException(status_code=400, detail=detail) from exc
        insumo_id = str(insumo["id"])
    category_id, category_label = await _check_category(db, company_id, payload.category_id)
    return {"name": _clean(payload.name), "presentation": _clean(payload.presentation, 60), "price": payload.price,
            "category_id": category_id, "category_key": category_label,
            "station": _clean(payload.station, 80), "requires_term": payload.requires_term,
            "allows_portions": payload.allows_portions, "kind": kind, "inventory_item_id": insumo_id,
            "direct_qty": payload.direct_qty, "active": payload.active}


@router.post("/companies/{company_id}/items")
async def create_dish(company_id: uuid.UUID, payload: DishIn, db: AsyncSession = Depends(get_db),
                      _a: str = Depends(require_carta_admin)) -> dict:
    values = await _validate_dish(db, company_id, payload)
    new_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO carta_items (id, company_id, name, presentation, price, category_key, category_id, station, requires_term,
                                 allows_portions, kind, inventory_item_id, direct_qty, active, position)
        VALUES (CAST(:id AS uuid), CAST(:company_id AS uuid), :name, :presentation, :price, :category_key,
                CAST(NULLIF(:category_id, '') AS uuid), :station, :requires_term,
                :allows_portions, :kind, CAST(NULLIF(:inventory_item_id, '') AS uuid), :direct_qty, :active,
                (SELECT COALESCE(MAX(position), 0) + 1 FROM carta_items WHERE company_id = CAST(:company_id AS uuid)))
    """), {**values, "inventory_item_id": values["inventory_item_id"] or "", "id": new_id, "company_id": str(company_id)})
    await db.commit()
    return {**await _carta_payload(db, company_id), "created_id": new_id}


@router.put("/companies/{company_id}/items/{item_id}")
async def update_dish(company_id: uuid.UUID, item_id: uuid.UUID, payload: DishIn, db: AsyncSession = Depends(get_db),
                      _a: str = Depends(require_carta_admin)) -> dict:
    values = await _validate_dish(db, company_id, payload)
    result = await db.execute(text("""
        UPDATE carta_items SET name = :name, presentation = :presentation, price = :price, category_key = :category_key,
               category_id = CAST(NULLIF(:category_id, '') AS uuid), station = :station,
               requires_term = :requires_term, allows_portions = :allows_portions, kind = :kind,
               inventory_item_id = CAST(NULLIF(:inventory_item_id, '') AS uuid), direct_qty = :direct_qty,
               active = :active, updated_at = now()
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)
    """), {**values, "inventory_item_id": values["inventory_item_id"] or "", "id": str(item_id), "company_id": str(company_id)})
    if not getattr(result, "rowcount", 1):
        raise HTTPException(status_code=404, detail="Plato no encontrado.")
    await db.commit()
    return await _carta_payload(db, company_id)


class RecipeLineIn(BaseModel):
    inventory_item_id: str | None = None
    component_item_id: str | None = None
    quantity: float = Field(..., gt=0)
    unit: str | None = Field(default=None, max_length=12)
    yield_pct: float = Field(default=100, gt=0, le=100)


class RecipeIn(BaseModel):
    lines: list[RecipeLineIn] = Field(default_factory=list)


@router.put("/companies/{company_id}/items/{item_id}/recipe")
async def save_recipe(company_id: uuid.UUID, item_id: uuid.UUID, payload: RecipeIn, db: AsyncSession = Depends(get_db),
                      _a: str = Depends(require_carta_admin)) -> dict:
    dishes, _lines = await load_dishes(db, company_id)
    by_id = {str(d["id"]): d for d in dishes}
    dish = by_id.get(str(item_id))
    if not dish:
        raise HTTPException(status_code=404, detail="Plato no encontrado.")
    insumos = await load_insumos(db, company_id)
    for line in payload.lines:
        if line.component_item_id:
            part = by_id.get(str(line.component_item_id))
            if dish.get("kind") != "combo":
                raise HTTPException(status_code=400, detail="Solo un combo lleva otros platos.")
            if not part or str(part["id"]) == str(item_id):
                raise HTTPException(status_code=400, detail="Elige un plato de tu carta para el combo.")
            if part.get("kind") == "combo":
                raise HTTPException(status_code=400, detail="Un combo no puede llevar otro combo.")
            continue
        insumo = insumos.get(str(line.inventory_item_id or ""))
        try:
            engine.validate_link(insumo)
        except ValueError as exc:
            detail = ("Un consumible no va en una receta: cuenta como gasto, no como ingrediente."
                      if "consumible" in str(exc) else "Insumo no encontrado en tu inventario.")
            raise HTTPException(status_code=400, detail=detail) from exc
        if line.unit is not None and not engine.recipe_unit(line.unit):
            raise HTTPException(status_code=400, detail=f"Unidad inválida: usa {', '.join(engine.RECIPE_UNITS.values())}.")
    await db.execute(text("DELETE FROM carta_recipe_lines WHERE company_id = CAST(:c AS uuid) AND carta_item_id = CAST(:i AS uuid)"),
                     {"c": str(company_id), "i": str(item_id)})
    for position, line in enumerate(payload.lines):
        await db.execute(text("""
            INSERT INTO carta_recipe_lines (company_id, carta_item_id, inventory_item_id, component_item_id, quantity, yield_pct, position, unit)
            VALUES (CAST(:c AS uuid), CAST(:i AS uuid), CAST(NULLIF(:insumo, '') AS uuid), CAST(NULLIF(:component, '') AS uuid),
                    :quantity, :yield_pct, :position, NULLIF(:unit, ''))
        """), {"c": str(company_id), "i": str(item_id), "insumo": line.inventory_item_id or "",
               "component": line.component_item_id or "", "quantity": line.quantity,
               "yield_pct": line.yield_pct if not line.component_item_id else 100, "position": position,
               "unit": "" if line.component_item_id else (engine.recipe_unit(line.unit)
                                                           or engine.default_recipe_unit(insumos.get(str(line.inventory_item_id or ""))))})
    await db.commit()
    return await _carta_payload(db, company_id)


# ----------------------------------------------------------- insumos ---
class InsumoIn(BaseModel):
    """049Q: se configura en Inventario. Solo el tipo y LA unidad (de la lista
    unica); la conversion la deduce el sistema. `convert_amount` solo se pide
    al pasar de contar a pesar (o al reves) con existencia: cuantas <unidad
    nueva> hay en 1 <unidad anterior>. `min_stock` va en la unidad natural."""
    item_type: str
    unit: str | None = Field(default=None, max_length=12)
    purchase_unit: str | None = Field(default=None, max_length=12)  # nombre anterior de `unit`
    convert_amount: float | None = Field(default=None, gt=0, le=1_000_000)
    min_stock: float | None = Field(default=None, ge=0)


@router.put("/companies/{company_id}/insumos/{insumo_id}")
async def update_insumo(company_id: uuid.UUID, insumo_id: uuid.UUID, payload: InsumoIn, db: AsyncSession = Depends(get_db),
                        _a: str = Depends(require_carta_admin)) -> dict:
    """Tipo y unidad del insumo. Si la unidad cambia de dimension, la
    existencia, el costo promedio y las equivalencias se reexpresan (misma
    cantidad fisica, mismo valor total)."""
    insumos = await load_insumos(db, company_id)
    current = insumos.get(str(insumo_id))
    if not current:
        raise HTTPException(status_code=404, detail="Insumo no encontrado.")
    if payload.item_type not in engine.ITEM_TYPES:
        raise HTTPException(status_code=400, detail="Tipo inválido.")
    unit = engine.purchase_unit_key(payload.unit or payload.purchase_unit) if (payload.unit or payload.purchase_unit) else engine.natural_unit(current)
    if not unit:
        raise HTTPException(status_code=400, detail=f"Unidad inválida: usa {', '.join(engine.RECIPE_UNITS.values())}.")
    try:
        config = engine.configure_unit(current, unit, payload.convert_amount)
    except ValueError as exc:
        before = "unidad" if engine.purchase_weight_missing(current) else engine.RECIPE_UNITS.get(engine.natural_unit(current), "unidad")
        raise HTTPException(status_code=400, detail=(
            f"{current['name']} se contaba por {before} y ahora se medirá en {engine.RECIPE_UNITS[unit]}: "
            f"¿cuántos {engine.RECIPE_UNITS[unit]} hay en 1 {before}? Escríbelo una vez y se convierten la existencia y el costo.")) from exc
    if payload.item_type == "consumible":
        dishes, lines = await load_dishes(db, company_id)
        used = [d["name"] for d in dishes if str(d.get("inventory_item_id")) == str(insumo_id)]
        used += [d["name"] for d in dishes if any(str(l["inventory_item_id"]) == str(insumo_id) for l in lines.get(str(d["id"]), []))]
        if used:
            raise HTTPException(status_code=409, detail=f"Está en la carta ({', '.join(sorted(set(used))[:5])}): un consumible no puede venderse.")
    ratio, factor = config["ratio"], config["units_per_purchase"]
    old_cost = engine.dec(current.get("avg_cost")) if engine.purchase_weight_missing(current) else (engine.unit_cost(current) or Decimal("0"))
    new_cost = (old_cost / ratio).quantize(engine.QTY) if ratio > 0 else old_cost
    stock = (engine.dec(current.get("current_stock")) * ratio).quantize(engine.QTY)
    min_stock = (Decimal(str(payload.min_stock)) * factor if payload.min_stock is not None
                 else engine.dec(current.get("min_stock")) * ratio).quantize(engine.QTY)
    await db.execute(text("""
        UPDATE inventory_items
           SET item_type = :item_type, purchase_unit = :purchase_unit, consumption_unit = :consumption_unit,
               units_per_purchase = :factor, current_stock = :stock, min_stock = :min_stock,
               avg_cost = :avg_cost, entry_price = :entry_price, updated_at = now()
         WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)
    """), {"item_type": payload.item_type, "purchase_unit": config["purchase_unit"], "consumption_unit": config["consumption_unit"],
           "factor": factor, "stock": stock, "min_stock": min_stock, "avg_cost": new_cost,
           # precio de entrada = costo de UNA unidad natural (el kilo), el que ve Inventario
           "entry_price": (new_cost * factor).quantize(engine.MONEY),
           "id": str(insumo_id), "company_id": str(company_id)})
    if ratio != 1:
        await db.execute(text("""
            UPDATE carta_unit_equivalences SET amount = amount * :ratio, updated_at = now()
            WHERE company_id = CAST(:c AS uuid) AND inventory_item_id = CAST(:i AS uuid)
        """), {"ratio": ratio, "c": str(company_id), "i": str(insumo_id)})
    await db.execute(text("""
        DELETE FROM carta_unit_equivalences WHERE company_id = CAST(:c AS uuid) AND inventory_item_id = CAST(:i AS uuid) AND unit = :base
    """), {"c": str(company_id), "i": str(insumo_id), "base": config["consumption_unit"]})
    await db.commit()
    return await _carta_payload(db, company_id)


class PurchaseIn(BaseModel):
    """Lo que el dueño ve en la factura: cuanto compro y cuanto pago en total."""
    quantity: float = Field(..., gt=0, le=10_000_000)
    unit: str = Field(..., min_length=1, max_length=12)
    total_paid: float = Field(..., ge=0, le=10_000_000_000)
    notes: str = Field(default="", max_length=200)


@router.post("/companies/{company_id}/insumos/{insumo_id}/purchases")
async def register_purchase(company_id: uuid.UUID, insumo_id: uuid.UUID, payload: PurchaseIn, db: AsyncSession = Depends(get_db),
                            actor: str = Depends(require_carta_admin)) -> dict:
    """049Q: registra una compra. 80 kg por $1.120.000 -> entran 80.000 g a
    $14 el gramo; el costo promedio se pondera con lo que ya habia."""
    insumos = await load_insumos(db, company_id)
    insumo = insumos.get(str(insumo_id))
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado.")
    try:
        result = engine.register_purchase(insumo, payload.quantity, payload.unit, payload.total_paid)
    except ValueError as exc:
        reason = str(exc)
        if reason == "sin_equivalencia":
            detail = (f"{insumo['name']} se cuenta en {engine.RECIPE_UNITS.get(engine.natural_unit(insumo), 'unidad')}: "
                      f"registra la compra en esa unidad o guarda antes cuánto es 1 {engine.RECIPE_UNITS.get(engine.recipe_unit(payload.unit) or '', payload.unit)}.")
        elif reason == "unidad_invalida":
            detail = f"Unidad inválida: usa {', '.join(engine.RECIPE_UNITS.values())}."
        else:
            detail = "Escribe la cantidad comprada (mayor que cero) y el total pagado."
        raise HTTPException(status_code=400, detail=detail) from exc
    factor = engine.natural_factor(insumo) or Decimal("1")
    stock_before = engine.dec(insumo.get("current_stock"))
    await db.execute(text("""
        UPDATE inventory_items
           SET current_stock = :stock, avg_cost = :avg_cost, entry_price = :entry_price, updated_at = now()
         WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)
    """), {"stock": result["new_stock"], "avg_cost": result["avg_cost"], "entry_price": (result["avg_cost"] * factor).quantize(engine.MONEY),
           "id": str(insumo_id), "company_id": str(company_id)})
    label = engine.RECIPE_UNITS[result["unit"]]
    base_label = engine.RECIPE_UNITS.get(result["base_unit"], result["base_unit"])
    note = (f"Compra: {engine.dec(payload.quantity).normalize():f} {label} por ${int(result['total_paid']):,} "
            f"(${result['unit_cost'].normalize():f} por {base_label})").replace(",", ".")
    if payload.notes.strip():
        note = f"{note} · {_clean(payload.notes, 200)}"
    await db.execute(text("""
        INSERT INTO inventory_movements (id, company_id, item_id, movement_type, quantity_delta, quantity, stock_before, stock_after,
                                         source_module, notes, created_at, updated_at)
        VALUES (CAST(:id AS uuid), CAST(:company_id AS uuid), CAST(:item_id AS uuid), 'entry', :delta, :delta, :before, :after,
                'carta_compra', :notes, now(), now())
    """), {"id": str(uuid.uuid4()), "company_id": str(company_id), "item_id": str(insumo_id), "delta": result["base_quantity"],
           "before": stock_before, "after": result["new_stock"], "notes": note[:500]})
    await db.execute(text("""
        INSERT INTO carta_purchases (id, company_id, inventory_item_id, quantity, unit, total_paid, base_quantity, unit_cost, source, created_by)
        VALUES (CAST(:id AS uuid), CAST(:company_id AS uuid), CAST(:item_id AS uuid), :quantity, :unit, :total_paid, :base_quantity,
                :unit_cost, 'compra', :actor)
    """), {"id": str(uuid.uuid4()), "company_id": str(company_id), "item_id": str(insumo_id), "quantity": result["quantity"],
           "unit": result["unit"], "total_paid": result["total_paid"], "base_quantity": result["base_quantity"],
           "unit_cost": result["unit_cost"], "actor": _clean(actor, 120)})
    await db.commit()
    return {**await _carta_payload(db, company_id), "purchase": {
        "base_quantity": float(result["base_quantity"]), "unit_cost": float(result["unit_cost"]),
        "avg_cost": float(result["avg_cost"]), "cost_per_unit": float(result["cost_per_unit"])}}


class EquivalenceIn(BaseModel):
    unit: str = Field(..., min_length=1, max_length=12)
    amount: float = Field(..., gt=0, le=1_000_000)  # unidades del inventario que hay en 1 <unit>


@router.put("/companies/{company_id}/insumos/{insumo_id}/equivalences")
async def save_equivalence(company_id: uuid.UUID, insumo_id: uuid.UUID, payload: EquivalenceIn, db: AsyncSession = Depends(get_db),
                           _a: str = Depends(require_carta_admin)) -> dict:
    """Se pide una sola vez y queda para el insumo: "1 unidad de carne = 1 lb",
    "1 cucharada de sal = 12 g", "1 paquete de pan = 24 unidades"."""
    insumos = await load_insumos(db, company_id)
    insumo = insumos.get(str(insumo_id))
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado.")
    unit = engine.recipe_unit(payload.unit)
    if not unit:
        raise HTTPException(status_code=400, detail="Unidad inválida.")
    if unit == str(insumo.get("consumption_unit") or "unidad"):
        raise HTTPException(status_code=400, detail="Esa ya es la unidad del inventario.")
    await db.execute(text("""
        INSERT INTO carta_unit_equivalences (company_id, inventory_item_id, unit, amount, updated_at)
        VALUES (CAST(:c AS uuid), CAST(:i AS uuid), :unit, :amount, now())
        ON CONFLICT (company_id, inventory_item_id, unit) DO UPDATE SET amount = EXCLUDED.amount, updated_at = now()
    """), {"c": str(company_id), "i": str(insumo_id), "unit": unit, "amount": Decimal(str(payload.amount))})
    await db.commit()
    return await _carta_payload(db, company_id)


# --------------------------------------- eliminar, categorias e imagenes ---
@router.delete("/companies/{company_id}/items/{item_id}")
async def delete_dish(company_id: uuid.UUID, item_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                      _a: str = Depends(require_carta_admin)) -> dict:
    """Quita el plato de la carta. Los pedidos historicos guardan su nombre y
    su costo, asi que los reportes no cambian; el insumo sigue en inventario."""
    dishes, lines = await load_dishes(db, company_id)
    used_in = [d["name"] for d in dishes if any(str(l.get("component_item_id")) == str(item_id) for l in lines.get(str(d["id"]), []))]
    if used_in:
        raise HTTPException(status_code=409, detail=f"Está dentro del combo {', '.join(used_in[:3])}: quítalo del combo primero.")
    result = await db.execute(text("DELETE FROM carta_items WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)"),
                              {"id": str(item_id), "c": str(company_id)})
    if not getattr(result, "rowcount", 1):
        raise HTTPException(status_code=404, detail="Plato no encontrado.")
    # su foto se va con el; si el plato comparte id con un insumo (directos
    # migrados), la foto es tambien la del insumo y se queda.
    await db.execute(text("""
        DELETE FROM hospitality_product_images WHERE company_id = CAST(:c AS uuid) AND inventory_item_id = CAST(:id AS uuid)
          AND NOT EXISTS (SELECT 1 FROM inventory_items WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid))
    """), {"id": str(item_id), "c": str(company_id)})
    await db.commit()
    return await _carta_payload(db, company_id)


class CategoryIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    parent_id: str | None = Field(default=None, max_length=40)


class CategoryUpdateIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    station: str = Field(default="", max_length=80)
    quick_notes: list[str] = Field(default_factory=list)
    requires_term: bool = False


def _same_label(a: Any, b: Any) -> bool:
    return category_slug(a) == category_slug(b)


@router.post("/companies/{company_id}/categories")
async def add_category(company_id: uuid.UUID, payload: CategoryIn, db: AsyncSession = Depends(get_db),
                       _a: str = Depends(require_carta_admin)) -> dict:
    """Categoria (sin parent_id) o subcategoria. Solo dos niveles: una
    subcategoria no lleva subcategorias."""
    label = _clean(payload.label, 80).upper()
    categories = await ensure_categories(db, company_id)
    by_id = {c["id"]: c for c in categories}
    parent_id = str(payload.parent_id) if payload.parent_id else None
    if parent_id:
        parent = by_id.get(parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Categoría no encontrada.")
        if parent["parent_id"]:
            raise HTTPException(status_code=400, detail="Una subcategoría no lleva subcategorías.")
    siblings = [c for c in categories if c["parent_id"] == parent_id]
    if any(_same_label(c["label"], label) for c in siblings):
        raise HTTPException(status_code=409, detail=f"Ya existe {label}.")
    new_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO carta_categories (id, company_id, parent_id, label, position)
        VALUES (CAST(:id AS uuid), CAST(:company_id AS uuid), CAST(NULLIF(:parent_id, '') AS uuid), :label, :position)
    """), {"id": new_id, "company_id": str(company_id), "parent_id": parent_id or "", "label": label,
           "position": max([c["position"] for c in siblings] or [0]) + 1})
    await db.commit()
    return {**await _carta_payload(db, company_id), "created_category_id": new_id}


@router.put("/companies/{company_id}/categories/{category_id}")
async def update_category(company_id: uuid.UUID, category_id: uuid.UUID, payload: CategoryUpdateIn,
                          db: AsyncSession = Depends(get_db), _a: str = Depends(require_carta_admin)) -> dict:
    categories = await load_categories(db, company_id)
    current = next((c for c in categories if c["id"] == str(category_id)), None)
    if not current:
        raise HTTPException(status_code=404, detail="Categoría no encontrada.")
    label = _clean(payload.label, 80).upper()
    if any(c["id"] != current["id"] and c["parent_id"] == current["parent_id"] and _same_label(c["label"], label) for c in categories):
        raise HTTPException(status_code=409, detail=f"Ya existe {label}.")
    notes = [_clean(n, 80) for n in payload.quick_notes if _clean(n, 80)][:8]
    await db.execute(text("""
        UPDATE carta_categories SET label = :label, station = :station, quick_notes = CAST(:notes AS jsonb),
               requires_term = :requires_term, updated_at = now()
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)
    """), {"label": label, "station": _clean(payload.station, 80), "notes": json.dumps(notes, ensure_ascii=False),
           "requires_term": payload.requires_term, "id": str(category_id), "company_id": str(company_id)})
    if not current["parent_id"]:
        await db.execute(text("""
            UPDATE carta_items SET category_key = :label WHERE company_id = CAST(:company_id AS uuid)
              AND category_id IN (SELECT id FROM carta_categories WHERE company_id = CAST(:company_id AS uuid)
                                  AND (id = CAST(:id AS uuid) OR parent_id = CAST(:id AS uuid)))
        """), {"label": label, "id": str(category_id), "company_id": str(company_id)})
    await db.commit()
    return await _carta_payload(db, company_id)


@router.delete("/companies/{company_id}/categories/{category_id}")
async def delete_category(company_id: uuid.UUID, category_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                          _a: str = Depends(require_carta_admin)) -> dict:
    categories = await load_categories(db, company_id)
    current = next((c for c in categories if c["id"] == str(category_id)), None)
    if not current:
        raise HTTPException(status_code=404, detail="Categoría no encontrada.")
    ids = {current["id"], *[c["id"] for c in categories if c["parent_id"] == current["id"]]}
    dishes, _lines = await load_dishes(db, company_id)
    inside = [d["name"] for d in dishes if str(d.get("category_id") or "") in ids]
    if inside:
        raise HTTPException(status_code=409, detail=f"Tiene {len(inside)} plato(s) ({', '.join(inside[:3])}): muévelos a otra categoría primero.")
    for image_id in ids:
        await db.execute(text("""
            DELETE FROM hospitality_product_images WHERE company_id = CAST(:c AS uuid) AND inventory_item_id = CAST(:id AS uuid)
        """), {"c": str(company_id), "id": image_id})
    await db.execute(text("DELETE FROM carta_categories WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)"),
                     {"id": str(category_id), "c": str(company_id)})
    await db.commit()
    return await _carta_payload(db, company_id)


CATEGORY_IMAGE_BOX = (800, 800)  # lado mayor 800 px: nitida en cualquier celular, dentro del tope de 200 KB


def fit_to_box(raw: bytes) -> bytes:
    """La imagen COMPLETA dentro del recuadro: se reduce en proporcion (nunca
    se recorta, deforma ni agranda) y se guarda con la mejor calidad que
    quepa en el tope de la base."""
    from PIL import Image, ImageOps

    try:
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            image = Image.new("RGB", rgba.size, (18, 16, 32))  # fondo oscuro de los paneles
            image.paste(rgba, mask=rgba.split()[-1])
        image = image.convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=422, detail="No se pudo leer la imagen (usa JPG, PNG o WEBP).") from exc
    image.thumbnail(CATEGORY_IMAGE_BOX, Image.LANCZOS)
    encoded = b""
    for quality in (92, 88, 84, 80, 74, 68, 60):
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=quality, optimize=True, progressive=True, subsampling=0 if quality >= 84 else 2)
        encoded = out.getvalue()
        if len(encoded) <= media_storage.MAX_IMAGE_BYTES:
            break
    return encoded


@router.post("/companies/{company_id}/categories/{category_id}/image")
async def upload_category_image(company_id: uuid.UUID, category_id: uuid.UUID, image: UploadFile = File(...),
                                db: AsyncSession = Depends(get_db), _a: str = Depends(require_carta_admin)) -> dict:
    """Imagen de la categoria o subcategoria (8 o 10 en toda la carta, no una
    por plato). Se sirve por la misma ruta publica de fotos del menu."""
    categories = await load_categories(db, company_id)
    if not any(c["id"] == str(category_id) for c in categories):
        raise HTTPException(status_code=404, detail="Categoría no encontrada.")
    raw = await image.read(12 * 1024 * 1024 + 1)
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="La imagen es demasiado grande.")
    fitted = fit_to_box(raw)
    await db.execute(text("""
        INSERT INTO hospitality_product_images (company_id, inventory_item_id) VALUES (CAST(:c AS uuid), CAST(:i AS uuid))
        ON CONFLICT (company_id, inventory_item_id) DO NOTHING
    """), {"c": str(company_id), "i": str(category_id)})
    await media_storage.save_image(db, table="hospitality_product_images",
                                   key_columns={"company_id": str(company_id), "inventory_item_id": str(category_id)},
                                   raw=fitted, content_type="image/jpeg", pre_encoded=True)
    await db.commit()
    return await _carta_payload(db, company_id)


class BulkCategoryIn(BaseModel):
    item_ids: list[str] = Field(..., min_length=1, max_length=300)
    category_id: str | None = Field(default=None, max_length=40)


@router.put("/companies/{company_id}/items-category")
async def move_dishes(company_id: uuid.UUID, payload: BulkCategoryIn, db: AsyncSession = Depends(get_db),
                      _a: str = Depends(require_carta_admin)) -> dict:
    """Reasigna varios platos a la vez a una categoria o subcategoria."""
    category_id, category_label = await _check_category(db, company_id, payload.category_id)
    dishes, _lines = await load_dishes(db, company_id)
    known = {str(d["id"]) for d in dishes}
    ids = [str(i) for i in payload.item_ids if str(i) in known]
    if not ids:
        raise HTTPException(status_code=404, detail="Elige platos de tu carta.")
    for item_id in ids:
        await db.execute(text("""
            UPDATE carta_items SET category_id = CAST(NULLIF(:category_id, '') AS uuid), category_key = :label, updated_at = now()
            WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)
        """), {"category_id": category_id, "label": category_label, "id": item_id, "company_id": str(company_id)})
    await db.commit()
    return {**await _carta_payload(db, company_id), "moved": len(ids)}


# ---------------------------------------------------------- QR de la carta ---
def public_carta_url(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/carta-qr?t={token}"


async def _qr_token(db: AsyncSession, company_id: uuid.UUID, *, regenerate: bool = False) -> str:
    settings = await _settings(db, company_id)
    token = settings.get("qr_token")
    if regenerate or not token:
        token = secrets.token_urlsafe(24)
        await _save_settings(db, company_id, {"qr_token": token})
        await db.commit()
    return str(token)


@router.get("/companies/{company_id}/qr")
async def carta_qr_info(company_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                        _a: str = Depends(require_carta_admin)) -> dict:
    token = await _qr_token(db, company_id)
    return {"url": public_carta_url(request, token)}


@router.post("/companies/{company_id}/qr/regenerate")
async def carta_qr_regenerate(company_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                              _a: str = Depends(require_carta_admin)) -> dict:
    """Cambia el codigo: el QR anterior deja de abrir la carta."""
    token = await _qr_token(db, company_id, regenerate=True)
    return {"url": public_carta_url(request, token)}


@router.get("/companies/{company_id}/qr.png")
async def carta_qr_png(company_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                       _a: str = Depends(require_carta_admin)) -> Response:
    import segno

    token = await _qr_token(db, company_id)
    buffer = io.BytesIO()
    segno.make(public_carta_url(request, token), error="m").save(buffer, kind="png", scale=12, border=3)
    return Response(content=buffer.getvalue(), media_type="image/png",
                    headers={"Content-Disposition": 'attachment; filename="qr_carta.png"'})


async def _company_by_qr_token(db: AsyncSession, token: str) -> dict | None:
    clean = _clean(token, 80)
    if len(clean) < 20:
        return None
    result = await db.execute(text("""
        SELECT c.id, c.name FROM company_modules cm JOIN modules m ON m.id = cm.module_id JOIN companies c ON c.id = cm.company_id
        WHERE LOWER(m.code) = 'carta' AND cm.enabled IS TRUE AND COALESCE(m.is_active, TRUE) IS TRUE
          AND cm.settings->>'qr_token' = :token
        LIMIT 1
    """), {"token": clean})
    row = result.mappings().first()
    return dict(row) if row else None


@router.get("/public/{token}")
async def public_carta(token: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Carta que abre el QR impreso: protegida por el codigo secreto del QR
    (se cambia desde el portal y el anterior deja de servir). Solo lo que ve
    un cliente: categorias, platos visibles, precio y foto; nunca costos ni
    existencias."""
    company = await _company_by_qr_token(db, token)
    if not company:
        raise HTTPException(status_code=404, detail="Esta carta ya no está disponible.")
    from app.api.v1.endpoints.waiter_ordering import build_waiter_menu

    menu = await build_waiter_menu(db, company["id"])

    def product(p: dict) -> dict:
        return {"id": str(p.get("id")), "name": p.get("name") or "", "price": p.get("price") or 0,
                "has_image": bool(p.get("has_image")), "image_item_id": p.get("image_item_id") or p.get("id"),
                "subcategory_key": p.get("subcategory_key") or "", "is_portioned": bool(p.get("is_portioned")),
                "portions": [{"label": x.get("label") or x.get("portion_label") or "", "price": x.get("price") or 0}
                             for x in (p.get("portions") or [])]}

    def art(node: dict) -> dict:
        return {"key": node.get("key"), "label": node.get("label"), "has_image": bool(node.get("has_image")),
                "image_item_id": node.get("image_item_id") or "", "image_version": node.get("image_version") or "",
                "image_fit": node.get("image_fit") or ""}

    categories = []
    for category in menu.get("categories") or []:
        products = [product(p) for p in category.get("products") or []]
        if products:
            categories.append({**art(category), "products": products,
                               "subcategories": [{**art(sub), "products": [product(p) for p in sub.get("products") or []]}
                                                 for sub in category.get("subcategories") or []]})
    return {"company_id": str(company["id"]), "company_name": company["name"], "categories": categories,
            "menu_emojis": bool(menu.get("menu_emojis"))}
