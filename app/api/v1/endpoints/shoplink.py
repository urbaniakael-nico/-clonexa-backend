from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


class ShoplinkSettingsIn(BaseModel):
    public_enabled: bool | None = True
    store_name: str | None = ""
    headline: str | None = ""
    description: str | None = ""
    whatsapp_number: str | None = ""
    cta_message: str | None = ""
    show_prices: bool | None = True
    show_stock: bool | None = True
    currency: str | None = "COP"
    theme: str | None = "shoplink_dark"
    categories: list[str] | None = None
    featured_terms: list[str] | None = None
    photos_per_category: int | None = 8
    hero_image_url: str | None = ""
    logo_url: str | None = ""


def _clean(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "tienda"


def _settings_defaults(company: dict[str, Any] | None = None) -> dict[str, Any]:
    company = company or {}
    name = company.get("name") or "Tienda CLONEXA"
    return {
        "public_enabled": True,
        "store_name": name,
        "headline": "Catálogo público",
        "description": "Explora productos, disponibilidad y consulta por WhatsApp.",
        "whatsapp_number": "",
        "cta_message": "Hola, quiero consultar este producto:",
        "show_prices": True,
        "show_stock": True,
        "currency": "COP",
        "theme": "shoplink_dark",
        "categories": [],
        "featured_terms": [],
        "photos_per_category": 8,
        "hero_image_url": "",
        "logo_url": "",
    }


async def _columns(db: AsyncSession, table_name: str) -> set[str]:
    result = await db.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
        """),
        {"table_name": table_name},
    )
    return {str(row[0]) for row in result.all()}


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:name)"), {"name": f"public.{table_name}"})
    return bool(result.scalar_one_or_none())


async def ensure_shoplink_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS shoplink_store_settings (
            company_id text PRIMARY KEY,
            store_slug text NOT NULL DEFAULT '',
            settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_shoplink_store_settings_slug
        ON shoplink_store_settings (lower(store_slug))
    """))
    await db.commit()


async def _company(db: AsyncSession, company_id: UUID | str) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT id::text AS id, name, slug, status, settings_json
            FROM companies
            WHERE id = CAST(:company_id AS uuid)
        """),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    return dict(row)


async def _settings(db: AsyncSession, company: dict[str, Any]) -> dict[str, Any]:
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT store_slug, settings_json
            FROM shoplink_store_settings
            WHERE company_id = :company_id
        """),
        {"company_id": company["id"]},
    )
    row = result.mappings().first()
    defaults = _settings_defaults(company)
    if not row:
        return {**defaults, "store_slug": _slug(company.get("slug") or company.get("name") or company["id"])}
    stored = row.get("settings_json") or {}
    if isinstance(stored, str):
        stored = json.loads(stored or "{}")
    return {**defaults, **stored, "store_slug": row.get("store_slug") or _slug(company.get("slug") or company["id"])}


def _product_key(source: str, row: dict[str, Any]) -> str:
    return f"{source}:{row.get('id') or row.get('name') or row.get('sku') or ''}"


def _money(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _inventory_products(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    if not await _table_exists(db, "inventory_items"):
        return []
    cols = await _columns(db, "inventory_items")
    name_expr = "COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), NULLIF(reference, ''), sku, 'Producto')" if "name_reference" in cols else "COALESCE(NULLIF(name, ''), NULLIF(reference, ''), sku, 'Producto')"
    size_expr = "COALESCE(item_size, '')" if "item_size" in cols else "''"
    color_expr = "COALESCE(color, '')" if "color" in cols else "''"
    category_expr = "COALESCE(category, '')" if "category" in cols else "''"
    sku_expr = "COALESCE(sku, '')" if "sku" in cols else "''"
    price_columns = [column for column in ("unit_value", "unit_price", "sale_price", "price") if column in cols]
    stock_columns = [column for column in ("current_stock", "quantity", "stock", "initial_quantity") if column in cols]
    price_expr = f"COALESCE({', '.join(price_columns + ['0'])})"
    stock_expr = f"COALESCE({', '.join(stock_columns + ['0'])})"
    status_expr = "COALESCE(status, 'active')" if "status" in cols else "'active'"

    result = await db.execute(
        text(f"""
            SELECT
              id::text AS id,
              {name_expr} AS name,
              {size_expr} AS size,
              {color_expr} AS color,
              {category_expr} AS category,
              {sku_expr} AS sku,
              {price_expr}::float AS price,
              {stock_expr}::float AS stock,
              {status_expr} AS status
            FROM inventory_items
            WHERE company_id::text = :company_id
            ORDER BY lower({category_expr}), lower({name_expr})
            LIMIT 800
        """),
        {"company_id": company_id},
    )
    rows = []
    for row in result.mappings().all():
        item = dict(row)
        if str(item.get("status") or "").lower() not in {"active", "available", "disponible"}:
            continue
        rows.append({
            "id": _product_key("inventory", item),
            "source": "inventory",
            "name": _clean(item.get("name"), 180),
            "size": _clean(item.get("size"), 80),
            "color": _clean(item.get("color"), 80),
            "category": _clean(item.get("category") or "General", 80) or "General",
            "sku": _clean(item.get("sku"), 80),
            "price": _money(item.get("price")),
            "stock": _money(item.get("stock")),
            "status": "agotado" if _money(item.get("stock")) <= 0 else "disponible",
            "image_url": "",
        })
    return rows


async def _reference_products(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    if not await _table_exists(db, "product_references"):
        return []
    result = await db.execute(
        text("""
            SELECT
              id,
              COALESCE(name, '') AS name,
              COALESCE(size, '') AS size,
              COALESCE(color, '') AS color,
              COALESCE(category, '') AS category,
              COALESCE(sku, '') AS sku,
              COALESCE(unit_price, 0)::float AS price,
              COALESCE(initial_quantity, 0)::float AS stock,
              COALESCE(archived, false) AS archived,
              COALESCE(system_active, false) AS system_active,
              COALESCE(channel, '') AS channel
            FROM product_references
            WHERE company_id = :company_id
            ORDER BY lower(COALESCE(category, '')), lower(name), lower(size)
            LIMIT 800
        """),
        {"company_id": company_id},
    )
    rows = []
    for row in result.mappings().all():
        item = dict(row)
        if item.get("archived"):
            continue
        rows.append({
            "id": _product_key("reference", item),
            "source": "references",
            "name": _clean(item.get("name"), 180),
            "size": _clean(item.get("size"), 80),
            "color": _clean(item.get("color"), 80),
            "category": _clean(item.get("category") or "General", 80) or "General",
            "sku": _clean(item.get("sku"), 80),
            "price": _money(item.get("price")),
            "stock": _money(item.get("stock")),
            "status": "disponible",
            "image_url": "",
        })
    return rows


async def _products(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    rows = await _inventory_products(db, company_id)
    seen = {f"{r['name']}|{r['size']}|{r['color']}".lower() for r in rows}
    for row in await _reference_products(db, company_id):
        key = f"{row['name']}|{row['size']}|{row['color']}".lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def _public_url(settings: dict[str, Any], company_id: str) -> str:
    return f"/shoplink?company_id={company_id}"


@router.get("/companies/{company_id}/settings")
async def get_shoplink_settings(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    products = await _products(db, company["id"])
    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": company["slug"]},
        "settings": settings,
        "public_url": _public_url(settings, company["id"]),
        "summary": {
            "products": len(products),
            "categories": len({p["category"] for p in products}),
            "featured": len(_featured_products(products, settings)),
        },
        "products": products[:40],
    }


@router.put("/companies/{company_id}/settings")
async def save_shoplink_settings(
    company_id: UUID,
    payload: ShoplinkSettingsIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    await ensure_shoplink_storage(db)
    current = await _settings(db, company)
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    clean_lists = {}
    for key in ("categories", "featured_terms"):
        if key in data and data[key] is not None:
            clean_lists[key] = [_clean(item, 80) for item in data[key] if _clean(item, 80)]
    settings = {**current, **data, **clean_lists}
    settings["store_name"] = _clean(settings.get("store_name") or company["name"], 120)
    settings["headline"] = _clean(settings.get("headline"), 160)
    settings["description"] = _clean(settings.get("description"), 700)
    settings["whatsapp_number"] = re.sub(r"[^0-9+]", "", _clean(settings.get("whatsapp_number"), 40))
    settings["photos_per_category"] = max(1, min(int(settings.get("photos_per_category") or 8), 40))
    settings["store_slug"] = _slug(company.get("slug") or settings["store_name"])
    await db.execute(
        text("""
            INSERT INTO shoplink_store_settings (company_id, store_slug, settings_json, updated_at)
            VALUES (:company_id, :store_slug, CAST(:settings AS jsonb), now())
            ON CONFLICT (company_id)
            DO UPDATE SET
              store_slug = EXCLUDED.store_slug,
              settings_json = EXCLUDED.settings_json,
              updated_at = now()
        """),
        {
            "company_id": company["id"],
            "store_slug": settings["store_slug"],
            "settings": json.dumps(settings, ensure_ascii=False),
        },
    )
    await db.commit()
    return {
        "ok": True,
        "settings": settings,
        "public_url": _public_url(settings, company["id"]),
    }


def _featured_products(products: list[dict[str, Any]], settings: dict[str, Any]) -> list[dict[str, Any]]:
    terms = [str(term or "").strip().lower() for term in settings.get("featured_terms") or [] if str(term or "").strip()]
    if not terms:
        return products[: min(6, len(products))]
    featured = []
    for product in products:
        haystack = " ".join([product.get("name", ""), product.get("category", ""), product.get("sku", "")]).lower()
        if any(term in haystack for term in terms):
            featured.append(product)
    return featured


@router.get("/public/{company_id}")
async def public_shoplink(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    if not settings.get("public_enabled", True):
        raise HTTPException(status_code=403, detail="Tienda pública desactivada.")
    products = await _products(db, company["id"])
    configured_categories = [c for c in settings.get("categories") or [] if c]
    product_categories = sorted({p["category"] for p in products if p.get("category")})
    categories = configured_categories or product_categories
    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": company["slug"]},
        "settings": settings,
        "public_url": _public_url(settings, company["id"]),
        "categories": categories,
        "products": products,
        "featured": _featured_products(products, settings),
    }
