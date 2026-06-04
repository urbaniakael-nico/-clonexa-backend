from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID, uuid4

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
    checkout_enabled: bool | None = True
    support_whatsapp_enabled: bool | None = False
    show_prices: bool | None = True
    show_stock: bool | None = True
    currency: str | None = "COP"
    theme: str | None = "shoplink_dark"
    layout_mode: str | None = "marketplace"
    accent_color: str | None = "#ff7a00"
    categories: list[str] | None = None
    featured_terms: list[str] | None = None
    payment_methods: list[str] | None = None
    photos_per_category: int | None = 8
    hero_image_url: str | None = ""
    logo_url: str | None = ""
    announcement: str | None = ""
    delivery_notes: str | None = ""


class ShoplinkOrderItemIn(BaseModel):
    product_id: str | None = ""
    qty: int | None = 1


class ShoplinkOrderIn(BaseModel):
    customer_name: str | None = ""
    customer_phone: str | None = ""
    customer_city: str | None = ""
    customer_address: str | None = ""
    customer_note: str | None = ""
    items: list[ShoplinkOrderItemIn] | None = None


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
        "headline": "Tienda online",
        "description": "Explora productos, arma tu carrito y haz tu pedido en la web.",
        "whatsapp_number": "",
        "cta_message": "Hola, necesito ayuda con mi pedido:",
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
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS shoplink_orders (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            order_code text NOT NULL,
            customer_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            items_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            total_amount double precision NOT NULL DEFAULT 0,
            currency text NOT NULL DEFAULT 'COP',
            status text NOT NULL DEFAULT 'new',
            source text NOT NULL DEFAULT 'shoplink_public',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_shoplink_orders_company_created
        ON shoplink_orders (company_id, created_at DESC)
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
    defaults.update({
        "headline": "Tienda online",
        "description": "Explora productos, arma tu carrito y haz tu pedido en la web.",
        "cta_message": "Hola, necesito ayuda con mi pedido:",
        "checkout_enabled": True,
        "support_whatsapp_enabled": False,
        "theme": "marketplace_pop",
        "layout_mode": "marketplace",
        "accent_color": "#ff7a00",
        "payment_methods": ["Efectivo", "Transferencia", "Tarjeta"],
        "announcement": "",
        "delivery_notes": "Despachos y tiempos de entrega se confirman al aprobar el pedido.",
    })
    if not row:
        return {**defaults, "store_slug": _slug(company.get("slug") or company.get("name") or company["id"])}
    stored = row.get("settings_json") or {}
    if isinstance(stored, str):
        stored = json.loads(stored or "{}")
    legacy_settings = "checkout_enabled" not in stored and "layout_mode" not in stored
    merged = {**defaults, **stored, "store_slug": row.get("store_slug") or _slug(company.get("slug") or company["id"])}
    if "whatsapp" in str(merged.get("description") or "").lower():
        merged["description"] = defaults["description"]
    headline_norm = str(merged.get("headline") or "").lower()
    if "catalog" in headline_norm or ("cat" in headline_norm and "logo" in headline_norm):
        merged["headline"] = defaults["headline"]
    if legacy_settings and merged.get("theme") == "shoplink_dark":
        merged["theme"] = defaults["theme"]
    return merged


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


async def _orders_summary(db: AsyncSession, company_id: str) -> dict[str, Any]:
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT
              COUNT(*)::int AS total_orders,
              COALESCE(SUM(total_amount), 0)::float AS total_sales,
              COUNT(*) FILTER (WHERE status IN ('new', 'pending'))::int AS open_orders
            FROM shoplink_orders
            WHERE company_id = :company_id
        """),
        {"company_id": company_id},
    )
    row = result.mappings().first() or {}
    return {
        "orders": int(row.get("total_orders") or 0),
        "sales": float(row.get("total_sales") or 0),
        "open_orders": int(row.get("open_orders") or 0),
    }


async def _recent_orders(db: AsyncSession, company_id: str, limit: int = 8) -> list[dict[str, Any]]:
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT order_code, customer_json, total_amount, currency, status, created_at
            FROM shoplink_orders
            WHERE company_id = :company_id
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"company_id": company_id, "limit": limit},
    )
    rows = []
    for row in result.mappings().all():
        customer = row.get("customer_json") or {}
        if isinstance(customer, str):
            customer = json.loads(customer or "{}")
        rows.append({
            "order_code": row.get("order_code"),
            "customer_name": customer.get("name") or "",
            "customer_phone": customer.get("phone") or "",
            "total_amount": float(row.get("total_amount") or 0),
            "currency": row.get("currency") or "COP",
            "status": row.get("status") or "new",
            "created_at": str(row.get("created_at") or ""),
        })
    return rows


@router.get("/companies/{company_id}/settings")
async def get_shoplink_settings(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    products = await _products(db, company["id"])
    order_summary = await _orders_summary(db, company["id"])
    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": company["slug"]},
        "settings": settings,
        "public_url": _public_url(settings, company["id"]),
        "summary": {
            "products": len(products),
            "categories": len({p["category"] for p in products}),
            "featured": len(_featured_products(products, settings)),
            **order_summary,
        },
        "products": products[:40],
        "orders": await _recent_orders(db, company["id"]),
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
    for key in ("categories", "featured_terms", "payment_methods"):
        if key in data and data[key] is not None:
            clean_lists[key] = [_clean(item, 80) for item in data[key] if _clean(item, 80)]
    settings = {**current, **data, **clean_lists}
    settings["store_name"] = _clean(settings.get("store_name") or company["name"], 120)
    settings["headline"] = _clean(settings.get("headline"), 160)
    settings["description"] = _clean(settings.get("description"), 700)
    settings["announcement"] = _clean(settings.get("announcement"), 180)
    settings["delivery_notes"] = _clean(settings.get("delivery_notes"), 500)
    settings["whatsapp_number"] = re.sub(r"[^0-9+]", "", _clean(settings.get("whatsapp_number"), 40))
    settings["cta_message"] = _clean(settings.get("cta_message"), 180)
    settings["checkout_enabled"] = bool(settings.get("checkout_enabled", True))
    settings["support_whatsapp_enabled"] = bool(settings.get("support_whatsapp_enabled", False))
    settings["show_prices"] = bool(settings.get("show_prices", True))
    settings["show_stock"] = bool(settings.get("show_stock", True))
    settings["photos_per_category"] = max(1, min(int(settings.get("photos_per_category") or 8), 40))
    settings["currency"] = _clean(settings.get("currency") or "COP", 8).upper() or "COP"
    allowed_layouts = {"marketplace", "boutique", "compact"}
    settings["layout_mode"] = settings.get("layout_mode") if settings.get("layout_mode") in allowed_layouts else "marketplace"
    allowed_themes = {"marketplace_pop", "shoplink_dark", "shoplink_light", "retail_neon", "classic_store"}
    settings["theme"] = settings.get("theme") if settings.get("theme") in allowed_themes else "marketplace_pop"
    accent = _clean(settings.get("accent_color") or "#ff7a00", 16)
    settings["accent_color"] = accent if re.match(r"^#[0-9a-fA-F]{6}$", accent) else "#ff7a00"
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


def _order_payload(payload: ShoplinkOrderIn) -> dict[str, Any]:
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return {
        "name": _clean(data.get("customer_name"), 120),
        "phone": re.sub(r"[^0-9+]", "", _clean(data.get("customer_phone"), 40)),
        "city": _clean(data.get("customer_city"), 120),
        "address": _clean(data.get("customer_address"), 220),
        "note": _clean(data.get("customer_note"), 500),
    }


@router.post("/public/{company_id}/orders")
async def create_shoplink_order(
    company_id: UUID,
    payload: ShoplinkOrderIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    if not settings.get("public_enabled", True):
        raise HTTPException(status_code=403, detail="Tienda publica desactivada.")
    if not settings.get("checkout_enabled", True):
        raise HTTPException(status_code=403, detail="Pedidos web desactivados.")

    customer = _order_payload(payload)
    if not customer["name"] or not customer["phone"]:
        raise HTTPException(status_code=400, detail="Nombre y telefono son obligatorios.")

    catalog = {str(product["id"]): product for product in await _products(db, company["id"])}
    items = []
    total = 0.0
    for raw in payload.items or []:
        data = raw.model_dump() if hasattr(raw, "model_dump") else raw.dict()
        product = catalog.get(str(data.get("product_id") or ""))
        if not product:
            continue
        qty = max(1, min(int(data.get("qty") or 1), 99))
        if _money(product.get("stock")) <= 0:
            continue
        unit_price = _money(product.get("price"))
        subtotal = unit_price * qty
        total += subtotal
        items.append({
            "product_id": product["id"],
            "name": product["name"],
            "sku": product.get("sku") or "",
            "category": product.get("category") or "General",
            "size": product.get("size") or "",
            "color": product.get("color") or "",
            "qty": qty,
            "unit_price": unit_price,
            "subtotal": subtotal,
        })

    if not items:
        raise HTTPException(status_code=400, detail="El pedido no tiene productos disponibles.")

    order_code = f"SL-{uuid4().hex[:8].upper()}"
    currency = _clean(settings.get("currency") or "COP", 8).upper() or "COP"
    await ensure_shoplink_storage(db)
    await db.execute(
        text("""
            INSERT INTO shoplink_orders (
              id, company_id, order_code, customer_json, items_json,
              total_amount, currency, status, source, updated_at
            )
            VALUES (
              :id, :company_id, :order_code, CAST(:customer AS jsonb), CAST(:items AS jsonb),
              :total_amount, :currency, 'new', 'shoplink_public', now()
            )
        """),
        {
            "id": str(uuid4()),
            "company_id": company["id"],
            "order_code": order_code,
            "customer": json.dumps(customer, ensure_ascii=False),
            "items": json.dumps(items, ensure_ascii=False),
            "total_amount": total,
            "currency": currency,
        },
    )
    await db.commit()
    return {
        "ok": True,
        "order_code": order_code,
        "status": "new",
        "total_amount": total,
        "currency": currency,
        "items": items,
    }


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
