"""Modulo CARTA (049H): platos, recetas e insumos.

Solo para empresas con el modulo "carta" (hoy ASADERO EL SOCIO, migracion
021w). Sin el modulo, la carta del mesero, la caja, los domicilios y el QR
siguen saliendo del inventario como siempre (The Time Machine no cambia).

Con el modulo:
- hospitality_inventory_lite / build_waiter_menu leen los PLATOS de
  carta_items (nunca un consumible).
- Al armar un pedido, cada linea guarda que insumos consume y a que costo
  (attach_consumption); _deduct_inventory y la edicion de pedidos pendientes
  descuentan esos insumos.

Endpoints /carta/companies/{company_id}/...: sesion de la empresa con rol
administrador/dueño/gerente (o Admin V2) y el modulo activo.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.services import carta as engine
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


async def load_insumos(db: AsyncSession, company_id: Any) -> dict[str, dict]:
    result = await db.execute(text("""
        SELECT id, COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), NULLIF(reference, ''), sku, id::text) AS name,
               sku, current_stock, min_stock, status, entry_price, sale_price, avg_cost,
               item_type, purchase_unit, consumption_unit, units_per_purchase
        FROM inventory_items
        WHERE company_id = CAST(:company_id AS uuid) AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
        ORDER BY lower(COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), sku, id::text))
    """), {"company_id": str(company_id)})
    return {str(r["id"]): dict(r) for r in result.mappings().all()}


async def load_dishes(db: AsyncSession, company_id: Any) -> tuple[list[dict], dict[str, list[dict]]]:
    dishes = [dict(r) for r in (await db.execute(text("""
        SELECT id, name, price, category_key, station, requires_term, allows_portions, kind,
               inventory_item_id, direct_qty, active, position
        FROM carta_items WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY position, lower(name)
    """), {"company_id": str(company_id)})).mappings().all()]
    lines: dict[str, list[dict]] = {}
    for row in (await db.execute(text("""
        SELECT carta_item_id, inventory_item_id, quantity, yield_pct, position
        FROM carta_recipe_lines WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY position
    """), {"company_id": str(company_id)})).mappings().all():
        lines.setdefault(str(row["carta_item_id"]), []).append(dict(row))
    return dishes, lines


def _available(dish: dict, insumos: dict[str, dict]) -> bool:
    if not dish.get("active"):
        return False
    if dish.get("kind") == "preparado":
        return True  # los preparados no bloquean la venta por existencias
    insumo = insumos.get(str(dish.get("inventory_item_id")))
    return bool(insumo) and str(insumo.get("status") or "active") == "active"


async def carta_inventory_lite(db: AsyncSession, company_id: Any) -> list[dict]:
    """Platos de la carta con la misma forma que devuelve inventory-lite."""
    insumos = await load_insumos(db, company_id)
    dishes, _lines = await load_dishes(db, company_id)
    out = []
    for dish in dishes:
        insumo = insumos.get(str(dish.get("inventory_item_id"))) if dish.get("kind") != "preparado" else None
        price = float(Decimal(str(dish.get("price") or 0)))
        out.append({
            "id": str(dish["id"]), "sku": (insumo or {}).get("sku") or "", "name": dish["name"],
            "price": price, "unit_price": price,
            "stock": float(Decimal(str((insumo or {}).get("current_stock") or 0))) if insumo else 0.0,
            "active": _available(dish, insumos), "allows_portions": bool(dish.get("allows_portions")),
            "category_key": dish.get("category_key") or "", "station": dish.get("station") or "",
            "requires_term": bool(dish.get("requires_term")), "carta_kind": dish.get("kind") or "directo",
        })
    return out


async def attach_consumption(db: AsyncSession, company_id: Any, rows: list[dict]) -> list[dict]:
    """Congela en cada linea del pedido los insumos que consume y su costo."""
    insumos = await load_insumos(db, company_id)
    dishes, lines = await load_dishes(db, company_id)
    by_id = {str(d["id"]): d for d in dishes}
    for row in rows:
        dish = by_id.get(str(row.get("inventory_item_id") or row.get("product_id") or ""))
        if not dish:
            continue
        entries = engine.consumption(dish, lines.get(str(dish["id"]), []), row.get("quantity"))
        cost, priced = engine.cost_of(entries, insumos)
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
def _insumo_payload(row: dict) -> dict:
    unit = engine.unit_cost(row)
    return {
        "id": str(row["id"]), "name": row["name"], "item_type": row.get("item_type") or "venta_directa",
        "purchase_unit": row.get("purchase_unit") or "unidad", "consumption_unit": row.get("consumption_unit") or "unidad",
        "units_per_purchase": float(Decimal(str(row.get("units_per_purchase") or 1))),
        "stock": float(Decimal(str(row.get("current_stock") or 0))), "min_stock": float(Decimal(str(row.get("min_stock") or 0))),
        "avg_cost": float(unit) if unit is not None else None, "status": row.get("status") or "active",
    }


async def _carta_payload(db: AsyncSession, company_id: uuid.UUID) -> dict:
    insumos = await load_insumos(db, company_id)
    dishes, lines = await load_dishes(db, company_id)
    items = []
    for dish in dishes:
        dish_lines = lines.get(str(dish["id"]), [])
        summary = engine.dish_summary(dish, dish_lines, insumos)
        items.append({
            "id": str(dish["id"]), "name": dish["name"], "price": float(Decimal(str(dish["price"] or 0))),
            "category_key": dish.get("category_key") or "", "station": dish.get("station") or "",
            "requires_term": bool(dish.get("requires_term")), "allows_portions": bool(dish.get("allows_portions")),
            "kind": dish.get("kind") or "directo", "active": bool(dish.get("active")),
            "inventory_item_id": str(dish["inventory_item_id"]) if dish.get("inventory_item_id") else None,
            "direct_qty": float(Decimal(str(dish.get("direct_qty") or 1))),
            "available": _available(dish, insumos),
            "recipe": [{"inventory_item_id": str(l["inventory_item_id"]),
                        "insumo": (insumos.get(str(l["inventory_item_id"])) or {}).get("name") or "Insumo borrado",
                        "unit": (insumos.get(str(l["inventory_item_id"])) or {}).get("consumption_unit") or "unidad",
                        "quantity": float(Decimal(str(l["quantity"]))), "yield_pct": float(Decimal(str(l["yield_pct"])))}
                       for l in dish_lines],
            **{k: summary[k] for k in ("cost", "margin", "margin_pct", "below_cost", "missing_cost", "no_recipe")},
        })
    return {"items": items, "insumos": [_insumo_payload(r) for r in insumos.values()],
            "item_types": engine.ITEM_TYPES, "purchase_units": engine.PURCHASE_UNITS,
            "consumption_units": engine.CONSUMPTION_UNITS}


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
    price: float = Field(default=0, ge=0)
    category_key: str = Field(default="", max_length=80)
    station: str = Field(default="", max_length=80)
    requires_term: bool = False
    allows_portions: bool = False
    kind: str = Field(default="directo")
    inventory_item_id: str | None = None
    direct_qty: float = Field(default=1, gt=0)
    active: bool = True


async def _validate_dish(db: AsyncSession, company_id: uuid.UUID, payload: DishIn) -> dict:
    kind = payload.kind if payload.kind in engine.DISH_KINDS else None
    if not kind:
        raise HTTPException(status_code=400, detail="Tipo de plato inválido (directo o preparado).")
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
    return {"name": _clean(payload.name), "price": payload.price, "category_key": _clean(payload.category_key, 80),
            "station": _clean(payload.station, 80), "requires_term": payload.requires_term,
            "allows_portions": payload.allows_portions, "kind": kind, "inventory_item_id": insumo_id,
            "direct_qty": payload.direct_qty, "active": payload.active}


@router.post("/companies/{company_id}/items")
async def create_dish(company_id: uuid.UUID, payload: DishIn, db: AsyncSession = Depends(get_db),
                      _a: str = Depends(require_carta_admin)) -> dict:
    values = await _validate_dish(db, company_id, payload)
    await db.execute(text("""
        INSERT INTO carta_items (id, company_id, name, price, category_key, station, requires_term, allows_portions,
                                 kind, inventory_item_id, direct_qty, active, position)
        VALUES (CAST(:id AS uuid), CAST(:company_id AS uuid), :name, :price, :category_key, :station, :requires_term,
                :allows_portions, :kind, CAST(NULLIF(:inventory_item_id, '') AS uuid), :direct_qty, :active,
                (SELECT COALESCE(MAX(position), 0) + 1 FROM carta_items WHERE company_id = CAST(:company_id AS uuid)))
    """), {**values, "inventory_item_id": values["inventory_item_id"] or "", "id": str(uuid.uuid4()), "company_id": str(company_id)})
    await db.commit()
    return await _carta_payload(db, company_id)


@router.put("/companies/{company_id}/items/{item_id}")
async def update_dish(company_id: uuid.UUID, item_id: uuid.UUID, payload: DishIn, db: AsyncSession = Depends(get_db),
                      _a: str = Depends(require_carta_admin)) -> dict:
    values = await _validate_dish(db, company_id, payload)
    result = await db.execute(text("""
        UPDATE carta_items SET name = :name, price = :price, category_key = :category_key, station = :station,
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
    inventory_item_id: str
    quantity: float = Field(..., gt=0)
    yield_pct: float = Field(default=100, gt=0, le=100)


class RecipeIn(BaseModel):
    lines: list[RecipeLineIn] = Field(default_factory=list)


@router.put("/companies/{company_id}/items/{item_id}/recipe")
async def save_recipe(company_id: uuid.UUID, item_id: uuid.UUID, payload: RecipeIn, db: AsyncSession = Depends(get_db),
                      _a: str = Depends(require_carta_admin)) -> dict:
    dishes, _lines = await load_dishes(db, company_id)
    if not any(str(d["id"]) == str(item_id) for d in dishes):
        raise HTTPException(status_code=404, detail="Plato no encontrado.")
    insumos = await load_insumos(db, company_id)
    for line in payload.lines:
        try:
            engine.validate_link(insumos.get(line.inventory_item_id))
        except ValueError as exc:
            detail = ("Un consumible no va en una receta: cuenta como gasto, no como ingrediente."
                      if "consumible" in str(exc) else "Insumo no encontrado en tu inventario.")
            raise HTTPException(status_code=400, detail=detail) from exc
    await db.execute(text("DELETE FROM carta_recipe_lines WHERE company_id = CAST(:c AS uuid) AND carta_item_id = CAST(:i AS uuid)"),
                     {"c": str(company_id), "i": str(item_id)})
    for position, line in enumerate(payload.lines):
        await db.execute(text("""
            INSERT INTO carta_recipe_lines (company_id, carta_item_id, inventory_item_id, quantity, yield_pct, position)
            VALUES (CAST(:c AS uuid), CAST(:i AS uuid), CAST(:insumo AS uuid), :quantity, :yield_pct, :position)
        """), {"c": str(company_id), "i": str(item_id), "insumo": line.inventory_item_id, "quantity": line.quantity,
               "yield_pct": line.yield_pct, "position": position})
    await db.commit()
    return await _carta_payload(db, company_id)


# ----------------------------------------------------------- insumos ---
class InsumoIn(BaseModel):
    item_type: str
    purchase_unit: str
    consumption_unit: str
    units_per_purchase: float | None = Field(default=None, gt=0)


@router.put("/companies/{company_id}/insumos/{insumo_id}")
async def update_insumo(company_id: uuid.UUID, insumo_id: uuid.UUID, payload: InsumoIn, db: AsyncSession = Depends(get_db),
                        _a: str = Depends(require_carta_admin)) -> dict:
    """Tipo y unidades. Si cambia la conversion, la existencia y el costo
    promedio se reexpresan en la nueva unidad de consumo (misma cantidad
    fisica, mismo valor total)."""
    insumos = await load_insumos(db, company_id)
    current = insumos.get(str(insumo_id))
    if not current:
        raise HTTPException(status_code=404, detail="Insumo no encontrado.")
    if payload.item_type not in engine.ITEM_TYPES:
        raise HTTPException(status_code=400, detail="Tipo inválido.")
    try:
        purchase = engine.clean_unit(payload.purchase_unit, engine.PURCHASE_UNITS)
        consumption_unit = engine.clean_unit(payload.consumption_unit, engine.CONSUMPTION_UNITS)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unidad inválida.") from exc
    factor = engine.standard_factor("g" if purchase == "gramo" else purchase, consumption_unit)
    if factor is None:
        if not payload.units_per_purchase:
            raise HTTPException(status_code=400, detail="Indica cuántas unidades de consumo trae cada unidad de compra.")
        factor = Decimal(str(payload.units_per_purchase))
    if payload.item_type == "consumible":
        dishes, lines = await load_dishes(db, company_id)
        used = [d["name"] for d in dishes if str(d.get("inventory_item_id")) == str(insumo_id)]
        used += [d["name"] for d in dishes if any(str(l["inventory_item_id"]) == str(insumo_id) for l in lines.get(str(d["id"]), []))]
        if used:
            raise HTTPException(status_code=409, detail=f"Está en la carta ({', '.join(sorted(set(used))[:5])}): un consumible no puede venderse.")
    old_factor = Decimal(str(current.get("units_per_purchase") or 1)) or Decimal("1")
    ratio = factor / old_factor
    await db.execute(text("""
        UPDATE inventory_items
           SET item_type = :item_type, purchase_unit = :purchase_unit, consumption_unit = :consumption_unit,
               units_per_purchase = :factor,
               current_stock = current_stock * :ratio, min_stock = min_stock * :ratio,
               avg_cost = CASE WHEN :ratio > 0 THEN avg_cost / :ratio ELSE avg_cost END,
               updated_at = now()
         WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)
    """), {"item_type": payload.item_type, "purchase_unit": purchase, "consumption_unit": consumption_unit,
           "factor": factor, "ratio": ratio, "id": str(insumo_id), "company_id": str(company_id)})
    await db.commit()
    return await _carta_payload(db, company_id)
