from __future__ import annotations

import json
import re
from html import escape
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()
MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PRODUCT_IMAGES = 3
ALLOWED_PRODUCT_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


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


class ShoplinkOrderUpdate(BaseModel):
    status: str | None = None
    guide_number: str | None = None
    guide_url: str | None = None
    guide_note: str | None = None


class ShoplinkProductIn(BaseModel):
    name: str | None = ""
    category: str | None = ""
    sku: str | None = ""
    size: str | None = ""
    color: str | None = ""
    description: str | None = ""
    price: float | int | str | None = 0
    stock: float | int | str | None = 0
    image_url: str | None = ""
    image_urls: list[str] | None = None
    inventory_item_id: str | None = ""
    published: bool | None = True
    archived: bool | None = False
    featured: bool | None = False


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
            invoice_code text NOT NULL DEFAULT '',
            guide_number text NOT NULL DEFAULT '',
            guide_url text NOT NULL DEFAULT '',
            guide_note text NOT NULL DEFAULT '',
            source text NOT NULL DEFAULT 'shoplink_public',
            created_at timestamptz NOT NULL DEFAULT now(),
            invoiced_at timestamptz NULL,
            separated_at timestamptz NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    for stmt in [
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS invoice_code text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_number text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_url text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_note text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS invoiced_at timestamptz NULL",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS separated_at timestamptz NULL",
    ]:
        await db.execute(text(stmt))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_shoplink_orders_company_created
        ON shoplink_orders (company_id, created_at DESC)
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_shoplink_orders_company_status
        ON shoplink_orders (company_id, lower(status), created_at DESC)
    """))
    await db.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_shoplink_orders_company_invoice
        ON shoplink_orders (company_id, invoice_code)
        WHERE invoice_code <> ''
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS shoplink_products (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            category text NOT NULL DEFAULT 'General',
            name text NOT NULL DEFAULT '',
            sku text NOT NULL DEFAULT '',
            size text NOT NULL DEFAULT '',
            color text NOT NULL DEFAULT '',
            description text NOT NULL DEFAULT '',
            price double precision NOT NULL DEFAULT 0,
            stock double precision NOT NULL DEFAULT 0,
            image_url text NOT NULL DEFAULT '',
            image_content_type text NOT NULL DEFAULT '',
            image_file_bytes bytea NULL,
            image_file_size integer NOT NULL DEFAULT 0,
            image_url_2 text NOT NULL DEFAULT '',
            image_2_content_type text NOT NULL DEFAULT '',
            image_2_file_bytes bytea NULL,
            image_2_file_size integer NOT NULL DEFAULT 0,
            image_url_3 text NOT NULL DEFAULT '',
            image_3_content_type text NOT NULL DEFAULT '',
            image_3_file_bytes bytea NULL,
            image_3_file_size integer NOT NULL DEFAULT 0,
            inventory_item_id text NOT NULL DEFAULT '',
            published boolean NOT NULL DEFAULT true,
            archived boolean NOT NULL DEFAULT false,
            featured boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    for stmt in [
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS category text NOT NULL DEFAULT 'General'",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS name text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS sku text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS size text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS color text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS description text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS price double precision NOT NULL DEFAULT 0",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS stock double precision NOT NULL DEFAULT 0",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_url text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_content_type text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_file_bytes bytea NULL",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_file_size integer NOT NULL DEFAULT 0",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_url_2 text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_2_content_type text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_2_file_bytes bytea NULL",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_2_file_size integer NOT NULL DEFAULT 0",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_url_3 text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_3_content_type text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_3_file_bytes bytea NULL",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS image_3_file_size integer NOT NULL DEFAULT 0",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS inventory_item_id text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS published boolean NOT NULL DEFAULT true",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS archived boolean NOT NULL DEFAULT false",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS featured boolean NOT NULL DEFAULT false",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()",
        "ALTER TABLE shoplink_products ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()",
    ]:
        await db.execute(text(stmt))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_shoplink_products_company_category
        ON shoplink_products (company_id, lower(category), lower(name))
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


def _image_slot_columns(position: int) -> tuple[str, str, str, str]:
    if position == 1:
        return ("image_url", "image_content_type", "image_file_bytes", "image_file_size")
    if position in {2, 3}:
        return (f"image_url_{position}", f"image_{position}_content_type", f"image_{position}_file_bytes", f"image_{position}_file_size")
    raise HTTPException(status_code=422, detail="Posicion de imagen invalida.")


def _image_slot_url(row: dict[str, Any], position: int) -> str:
    url_col, _, bytes_col, _ = _image_slot_columns(position)
    if row.get(bytes_col):
        return f"/api/v1/shoplink/products/{row.get('id')}/images/{position}"
    return _clean(row.get(url_col), 1000)


def _image_urls(row: dict[str, Any]) -> list[str]:
    urls = [_image_slot_url(row, position) for position in range(1, MAX_PRODUCT_IMAGES + 1)]
    return [url for url in urls if url]


def _image_url(row: dict[str, Any]) -> str:
    urls = _image_urls(row)
    return urls[0] if urls else ""


def _shoplink_product_out(row: dict[str, Any], public_id: bool = True) -> dict[str, Any]:
    raw_id = _clean(row.get("id"), 80)
    return {
        "id": f"shoplink:{raw_id}" if public_id else raw_id,
        "raw_id": raw_id,
        "source": "shoplink",
        "name": _clean(row.get("name"), 180) or "Producto",
        "category": _clean(row.get("category") or "General", 80) or "General",
        "sku": _clean(row.get("sku"), 80),
        "size": _clean(row.get("size"), 80),
        "color": _clean(row.get("color"), 80),
        "description": _clean(row.get("description"), 700),
        "price": _money(row.get("price")),
        "stock": _money(row.get("stock")),
        "status": "archivado" if bool(row.get("archived")) else ("agotado" if _money(row.get("stock")) <= 0 else "disponible"),
        "image_url": _image_url(row),
        "image_urls": _image_urls(row),
        "inventory_item_id": _clean(row.get("inventory_item_id"), 80),
        "published": bool(row.get("published")),
        "archived": bool(row.get("archived")),
        "featured": bool(row.get("featured")),
        "has_image": bool(_image_urls(row)),
        "image_file_size": sum(int(row.get(_image_slot_columns(position)[3]) or 0) for position in range(1, MAX_PRODUCT_IMAGES + 1)),
    }


async def _shoplink_products(db: AsyncSession, company_id: str, public_only: bool = True) -> list[dict[str, Any]]:
    await ensure_shoplink_storage(db)
    where = ["company_id = :company_id"]
    if public_only:
        where.append("published IS TRUE")
        where.append("archived IS NOT TRUE")
    result = await db.execute(
        text(f"""
            SELECT *
            FROM shoplink_products
            WHERE {" AND ".join(where)}
            ORDER BY featured DESC, lower(category), lower(name), updated_at DESC
            LIMIT 1000
        """),
        {"company_id": company_id},
    )
    return [_shoplink_product_out(dict(row), public_id=True) for row in result.mappings().all()]


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
    managed_rows = await _shoplink_products(db, company_id, public_only=False)
    if managed_rows:
        return [row for row in managed_rows if row.get("published") and not row.get("archived")]
    rows: list[dict[str, Any]] = []
    seen = {f"{r['name']}|{r['size']}|{r['color']}".lower() for r in rows}
    for row in await _inventory_products(db, company_id):
        key = f"{row['name']}|{row['size']}|{row['color']}".lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
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
            SELECT order_code, invoice_code, customer_json, total_amount, currency, status, guide_number, guide_url, created_at
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
            "invoice_code": row.get("invoice_code") or _invoice_code_for_order(row.get("order_code")),
            "customer_name": customer.get("name") or "",
            "customer_phone": customer.get("phone") or "",
            "total_amount": float(row.get("total_amount") or 0),
            "currency": row.get("currency") or "COP",
            "status": row.get("status") or "new",
            "guide_number": row.get("guide_number") or "",
            "guide_url": row.get("guide_url") or "",
            "created_at": str(row.get("created_at") or ""),
        })
    return rows


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _json_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value or "[]")
            return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _invoice_code_for_order(order_code: Any) -> str:
    token = re.sub(r"[^A-Z0-9]", "", _clean(order_code, 40).upper())
    if token.startswith("SL"):
        token = token[2:]
    return f"FV-{token or uuid4().hex[:8].upper()}"


def _order_status(value: Any) -> str:
    raw = _clean(value, 40).lower()
    aliases = {
        "nuevo": "new",
        "pendiente": "pending",
        "separado": "separated",
        "separada": "separated",
        "confirmado": "confirmed",
        "confirmada": "confirmed",
        "pagado": "paid",
        "pagada": "paid",
        "enviado": "shipped",
        "enviada": "shipped",
        "entregado": "delivered",
        "entregada": "delivered",
        "cancelado": "cancelled",
        "cancelada": "cancelled",
        "archivado": "archived",
        "archivada": "archived",
    }
    raw = aliases.get(raw, raw)
    allowed = {"new", "pending", "separated", "confirmed", "paid", "shipped", "delivered", "cancelled", "archived"}
    return raw if raw in allowed else "new"


def _order_status_label(value: Any) -> str:
    labels = {
        "new": "Nuevo",
        "pending": "Pendiente",
        "separated": "Separado",
        "confirmed": "Confirmado",
        "paid": "Pagado",
        "shipped": "Enviado",
        "delivered": "Entregado",
        "cancelled": "Cancelado",
        "archived": "Archivado",
    }
    return labels.get(_order_status(value), "Nuevo")


def _format_invoice_money(value: Any, currency: str = "COP") -> str:
    number = _money(value)
    formatted = f"{number:,.0f}".replace(",", ".")
    return f"{_clean(currency, 8).upper() or 'COP'} {formatted}"


def _shoplink_order_out(row: dict[str, Any], company_id: str | None = None) -> dict[str, Any]:
    customer = _json_dict(row.get("customer_json"))
    items = _json_list(row.get("items_json"))
    order_id = _clean(row.get("id"), 80)
    source_company_id = company_id or _clean(row.get("company_id"), 80)
    order_code = _clean(row.get("order_code"), 60)
    invoice_code = _clean(row.get("invoice_code"), 60) or _invoice_code_for_order(order_code)
    status = _order_status(row.get("status"))
    return {
        "id": order_id,
        "company_id": source_company_id,
        "order_code": order_code,
        "invoice_code": invoice_code,
        "invoice_url": f"/api/v1/shoplink/companies/{source_company_id}/orders/{order_id}/invoice",
        "customer": customer,
        "customer_name": customer.get("name") or "",
        "customer_phone": customer.get("phone") or "",
        "customer_city": customer.get("city") or "",
        "customer_address": customer.get("address") or "",
        "customer_note": customer.get("note") or "",
        "items": items,
        "items_count": sum(int(item.get("qty") or 0) for item in items),
        "items_summary": ", ".join([_clean(item.get("name"), 80) for item in items[:3] if item.get("name")]),
        "total_amount": float(row.get("total_amount") or 0),
        "currency": row.get("currency") or "COP",
        "status": status,
        "status_label": _order_status_label(status),
        "guide_number": _clean(row.get("guide_number"), 120),
        "guide_url": _clean(row.get("guide_url"), 500),
        "guide_note": _clean(row.get("guide_note"), 500),
        "source": row.get("source") or "shoplink_public",
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "invoiced_at": str(row.get("invoiced_at") or ""),
        "separated_at": str(row.get("separated_at") or ""),
    }


async def _shoplink_order_rows(db: AsyncSession, company_id: str, limit: int = 300) -> list[dict[str, Any]]:
    await ensure_shoplink_storage(db)
    safe_limit = max(1, min(int(limit or 300), 1000))
    result = await db.execute(
        text("""
            SELECT *
            FROM shoplink_orders
            WHERE company_id = :company_id
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"company_id": company_id, "limit": safe_limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def _shoplink_order_by_id(db: AsyncSession, company_id: str, order_id: str) -> dict[str, Any]:
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT *
            FROM shoplink_orders
            WHERE company_id = :company_id
              AND id = :id
            LIMIT 1
        """),
        {"company_id": company_id, "id": _clean(order_id, 80)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")
    return dict(row)


def _shoplink_invoice_html(company: dict[str, Any], settings: dict[str, Any], order: dict[str, Any]) -> str:
    customer = order.get("customer") or {}
    items = order.get("items") or []
    store_name = settings.get("store_name") or company.get("name") or "Tienda CLONEXA"
    currency = order.get("currency") or settings.get("currency") or "COP"
    item_rows = "".join(
        f"""
        <tr>
          <td>{escape(_clean(item.get("name"), 180))}<br><small>{escape(_clean(item.get("sku"), 80))}</small></td>
          <td>{escape(_clean(item.get("qty"), 20))}</td>
          <td>{escape(_format_invoice_money(item.get("unit_price"), currency))}</td>
          <td>{escape(_format_invoice_money(item.get("subtotal"), currency))}</td>
        </tr>
        """
        for item in items
    )
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(order.get("invoice_code") or "Factura ShopLink")}</title>
  <style>
    body{{margin:0;background:#f3f5f8;color:#111827;font-family:Arial,Helvetica,sans-serif}}
    .page{{max-width:860px;margin:24px auto;background:#fff;border:1px solid #e5e7eb;border-radius:18px;padding:32px;box-shadow:0 20px 50px rgba(15,23,42,.12)}}
    header{{display:flex;justify-content:space-between;gap:24px;border-bottom:3px solid #111827;padding-bottom:18px;margin-bottom:22px}}
    h1{{margin:0;font-size:34px;letter-spacing:.02em}} h2{{margin:0 0 8px;font-size:20px}} p{{margin:4px 0;color:#4b5563}}
    .tag{{display:inline-block;background:#111827;color:#fff;border-radius:999px;padding:8px 12px;font-weight:800}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:18px 0}}
    .box{{border:1px solid #e5e7eb;border-radius:14px;padding:16px;background:#f9fafb}}
    table{{width:100%;border-collapse:collapse;margin-top:18px}} th,td{{border-bottom:1px solid #e5e7eb;padding:12px;text-align:left}} th{{background:#111827;color:#fff}}
    .total{{display:flex;justify-content:flex-end;margin-top:20px}} .total strong{{font-size:26px}}
    .actions{{display:flex;gap:10px;margin-top:24px}} button{{border:0;border-radius:12px;background:#111827;color:#fff;padding:12px 16px;font-weight:800;cursor:pointer}}
    small{{color:#6b7280}} @media print{{body{{background:#fff}}.page{{box-shadow:none;margin:0;border:0}}.actions{{display:none}}}}
  </style>
</head>
<body>
  <main class="page">
    <header>
      <div>
        <span class="tag">{escape(_order_status_label(order.get("status")))}</span>
        <h1>Factura ShopLink</h1>
        <p>{escape(store_name)}</p>
      </div>
      <div>
        <h2>{escape(order.get("invoice_code") or "")}</h2>
        <p>Pedido: {escape(order.get("order_code") or "")}</p>
        <p>Fecha: {escape(str(order.get("created_at") or "")[:19])}</p>
      </div>
    </header>
    <section class="grid">
      <div class="box">
        <h2>Cliente</h2>
        <p><strong>{escape(customer.get("name") or "Cliente")}</strong></p>
        <p>Telefono: {escape(customer.get("phone") or "")}</p>
        <p>Ciudad: {escape(customer.get("city") or "")}</p>
        <p>Direccion: {escape(customer.get("address") or "")}</p>
      </div>
      <div class="box">
        <h2>Entrega</h2>
        <p>Guia: {escape(order.get("guide_number") or "Pendiente")}</p>
        <p>{escape(order.get("guide_url") or "")}</p>
        <p>{escape(order.get("guide_note") or "")}</p>
      </div>
    </section>
    <table>
      <thead><tr><th>Articulo</th><th>Cant.</th><th>Unitario</th><th>Subtotal</th></tr></thead>
      <tbody>{item_rows}</tbody>
    </table>
    <div class="total"><strong>Total {escape(_format_invoice_money(order.get("total_amount"), currency))}</strong></div>
    <p><small>Documento generado automaticamente desde CLONEXA ShopLink.</small></p>
    <div class="actions"><button onclick="window.print()">Imprimir / PDF</button></div>
  </main>
</body>
</html>"""


async def _managed_shoplink_products(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT *
            FROM shoplink_products
            WHERE company_id = :company_id
            ORDER BY featured DESC, lower(category), lower(name), updated_at DESC
            LIMIT 1000
        """),
        {"company_id": company_id},
    )
    return [_shoplink_product_out(dict(row), public_id=False) for row in result.mappings().all()]


async def _inventory_candidates(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    if not await _table_exists(db, "inventory_items"):
        return []
    cols = await _columns(db, "inventory_items")
    name_expr = "COALESCE(NULLIF(name_reference, ''), NULLIF(name, ''), NULLIF(reference, ''), sku, 'Producto')" if "name_reference" in cols else "COALESCE(NULLIF(name, ''), NULLIF(reference, ''), sku, 'Producto')"
    size_expr = "COALESCE(item_size, '')" if "item_size" in cols else "''"
    color_expr = "COALESCE(color, '')" if "color" in cols else "''"
    sku_expr = "COALESCE(sku, '')" if "sku" in cols else "''"
    category_expr = "COALESCE(category, '')" if "category" in cols else "''"
    price_columns = [column for column in ("unit_value", "unit_price", "sale_price", "price") if column in cols]
    stock_columns = [column for column in ("current_stock", "quantity", "stock", "initial_quantity") if column in cols]
    price_expr = f"COALESCE({', '.join(price_columns + ['0'])})"
    stock_expr = f"COALESCE({', '.join(stock_columns + ['0'])})"
    result = await db.execute(
        text(f"""
            SELECT
              id::text AS id,
              {name_expr} AS name,
              {category_expr} AS category,
              {size_expr} AS size,
              {color_expr} AS color,
              {sku_expr} AS sku,
              {price_expr}::float AS price,
              {stock_expr}::float AS stock
            FROM inventory_items
            WHERE company_id::text = :company_id
            ORDER BY lower({name_expr})
            LIMIT 500
        """),
        {"company_id": company_id},
    )
    return [
        {
            "id": _clean(row.get("id"), 80),
            "name": _clean(row.get("name"), 180),
            "category": _clean(row.get("category"), 80),
            "size": _clean(row.get("size"), 80),
            "color": _clean(row.get("color"), 80),
            "sku": _clean(row.get("sku"), 80),
            "price": _money(row.get("price")),
            "stock": _money(row.get("stock")),
        }
        for row in result.mappings().all()
    ]


def _settings_categories(settings: dict[str, Any], products: list[dict[str, Any]] | None = None) -> list[str]:
    seen: set[str] = set()
    categories: list[str] = []
    for value in list(settings.get("categories") or []) + [p.get("category") for p in (products or [])]:
        category = _clean(value, 80) or "General"
        key = category.lower()
        if key in seen:
            continue
        seen.add(key)
        categories.append(category)
    return categories or ["General"]


def _product_payload(payload: ShoplinkProductIn, current: dict[str, Any] | None = None) -> dict[str, Any]:
    current = current or {}
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    name = _clean(data.get("name", current.get("name")), 180)
    if not name:
        raise HTTPException(status_code=422, detail="Nombre de producto requerido.")
    if "image_urls" in data and data.get("image_urls") is not None:
        image_urls = [_clean(url, 1000) for url in data.get("image_urls") or [] if _clean(url, 1000)]
    elif "image_url" in data:
        image_urls = [_clean(data.get("image_url"), 1000)] if _clean(data.get("image_url"), 1000) else []
    else:
        image_urls = [
            _clean(current.get("image_url"), 1000),
            _clean(current.get("image_url_2"), 1000),
            _clean(current.get("image_url_3"), 1000),
        ]
        image_urls = [url for url in image_urls if url]
    image_urls = image_urls[:MAX_PRODUCT_IMAGES]
    return {
        "name": name,
        "category": _clean(data.get("category", current.get("category")) or "General", 80) or "General",
        "sku": _clean(data.get("sku", current.get("sku")), 80),
        "size": _clean(data.get("size", current.get("size")), 80),
        "color": _clean(data.get("color", current.get("color")), 80),
        "description": _clean(data.get("description", current.get("description")), 700),
        "price": max(0.0, _money(data.get("price", current.get("price")))),
        "stock": max(0.0, _money(data.get("stock", current.get("stock")))),
        "image_url": image_urls[0] if len(image_urls) > 0 else "",
        "image_url_2": image_urls[1] if len(image_urls) > 1 else "",
        "image_url_3": image_urls[2] if len(image_urls) > 2 else "",
        "inventory_item_id": _clean(data.get("inventory_item_id", current.get("inventory_item_id")), 80),
        "published": bool(data.get("published", current.get("published", True))),
        "archived": bool(data.get("archived", current.get("archived", False))),
        "featured": bool(data.get("featured", current.get("featured", False))),
    }


@router.get("/companies/{company_id}/products")
async def get_shoplink_products(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    products = await _managed_shoplink_products(db, company["id"])
    categories = _settings_categories(settings, products)
    summary = {
        "products": len(products),
        "published": len([p for p in products if p.get("published") and not p.get("archived")]),
        "archived": len([p for p in products if p.get("archived")]),
        "featured": len([p for p in products if p.get("featured")]),
        "with_photo": len([p for p in products if p.get("has_image")]),
        "low_stock": len([p for p in products if p.get("published") and _money(p.get("stock")) <= 3]),
        "categories": len(categories),
    }
    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": company["slug"]},
        "settings": settings,
        "categories": categories,
        "summary": summary,
        "products": products,
        "inventory_items": await _inventory_candidates(db, company["id"]),
        "public_url": _public_url(settings, company["id"]),
    }


@router.get("/companies/{company_id}/orders")
async def get_shoplink_orders(
    company_id: UUID,
    status: str = "all",
    q: str = "",
    limit: int = 300,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    rows = [_shoplink_order_out(row, company["id"]) for row in await _shoplink_order_rows(db, company["id"], limit)]
    status_filter = _clean(status, 40).lower()
    if status_filter and status_filter not in {"all", "todos"}:
        wanted = _order_status(status_filter)
        rows = [row for row in rows if _order_status(row.get("status")) == wanted]
    query = _clean(q, 120).lower()
    if query:
        rows = [
            row for row in rows
            if query in " ".join([
                row.get("order_code") or "",
                row.get("invoice_code") or "",
                row.get("customer_name") or "",
                row.get("customer_phone") or "",
                row.get("customer_city") or "",
                row.get("guide_number") or "",
                row.get("items_summary") or "",
            ]).lower()
        ]
    summary = {
        "orders": len(rows),
        "new": len([row for row in rows if row.get("status") == "new"]),
        "pending": len([row for row in rows if row.get("status") in {"new", "pending", "confirmed"}]),
        "separated": len([row for row in rows if row.get("status") == "separated"]),
        "shipped": len([row for row in rows if row.get("status") in {"shipped", "delivered"}]),
        "cancelled": len([row for row in rows if row.get("status") == "cancelled"]),
        "total_sales": sum(float(row.get("total_amount") or 0) for row in rows if row.get("status") != "cancelled"),
    }
    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": company["slug"]},
        "settings": settings,
        "summary": summary,
        "orders": rows,
        "public_url": _public_url(settings, company["id"]),
    }


@router.patch("/companies/{company_id}/orders/{order_id}")
async def update_shoplink_order(
    company_id: UUID,
    order_id: str,
    payload: ShoplinkOrderUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    current = await _shoplink_order_by_id(db, company["id"], order_id)
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    next_status = _order_status(data["status"]) if "status" in data and data.get("status") is not None else _order_status(current.get("status"))
    invoice_code = _clean(current.get("invoice_code"), 60) or _invoice_code_for_order(current.get("order_code"))
    guide_number = _clean(data.get("guide_number", current.get("guide_number")), 120)
    guide_url = _clean(data.get("guide_url", current.get("guide_url")), 500)
    guide_note = _clean(data.get("guide_note", current.get("guide_note")), 500)
    result = await db.execute(
        text("""
            UPDATE shoplink_orders
            SET status = :status,
                invoice_code = :invoice_code,
                guide_number = :guide_number,
                guide_url = :guide_url,
                guide_note = :guide_note,
                invoiced_at = COALESCE(invoiced_at, now()),
                separated_at = CASE
                    WHEN :status = 'separated' THEN COALESCE(separated_at, now())
                    ELSE separated_at
                END,
                updated_at = now()
            WHERE company_id = :company_id
              AND id = :id
            RETURNING *
        """),
        {
            "company_id": company["id"],
            "id": _clean(order_id, 80),
            "status": next_status,
            "invoice_code": invoice_code,
            "guide_number": guide_number,
            "guide_url": guide_url,
            "guide_note": guide_note,
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")
    await db.commit()
    return {"ok": True, "order": _shoplink_order_out(dict(row), company["id"])}


@router.get("/companies/{company_id}/orders/{order_id}/invoice")
async def get_shoplink_order_invoice(
    company_id: UUID,
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    current = await _shoplink_order_by_id(db, company["id"], order_id)
    invoice_code = _clean(current.get("invoice_code"), 60) or _invoice_code_for_order(current.get("order_code"))
    if not _clean(current.get("invoice_code"), 60):
        result = await db.execute(
            text("""
                UPDATE shoplink_orders
                SET invoice_code = :invoice_code,
                    invoiced_at = COALESCE(invoiced_at, now()),
                    updated_at = now()
                WHERE company_id = :company_id
                  AND id = :id
                RETURNING *
            """),
            {"company_id": company["id"], "id": _clean(order_id, 80), "invoice_code": invoice_code},
        )
        current = dict(result.mappings().first() or current)
        await db.commit()
    order = _shoplink_order_out(current, company["id"])
    return Response(content=_shoplink_invoice_html(company, settings, order), media_type="text/html")


@router.post("/companies/{company_id}/products")
async def create_shoplink_product(
    company_id: UUID,
    payload: ShoplinkProductIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    await ensure_shoplink_storage(db)
    data = _product_payload(payload)
    product_id = str(uuid4())
    result = await db.execute(
        text("""
            INSERT INTO shoplink_products (
              id, company_id, category, name, sku, size, color, description,
              price, stock, image_url, image_url_2, image_url_3, inventory_item_id, published, archived, featured,
              created_at, updated_at
            )
            VALUES (
              :id, :company_id, :category, :name, :sku, :size, :color, :description,
              :price, :stock, :image_url, :image_url_2, :image_url_3, :inventory_item_id, :published, :archived, :featured,
              now(), now()
            )
            RETURNING *
        """),
        {"id": product_id, "company_id": company["id"], **data},
    )
    await db.commit()
    return {"ok": True, "product": _shoplink_product_out(dict(result.mappings().first()), public_id=False)}


@router.patch("/companies/{company_id}/products/{product_id}")
async def update_shoplink_product(
    company_id: UUID,
    product_id: str,
    payload: ShoplinkProductIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    await ensure_shoplink_storage(db)
    raw_id = _clean(product_id.replace("shoplink:", ""), 80)
    current_result = await db.execute(
        text("SELECT * FROM shoplink_products WHERE company_id = :company_id AND id = :id LIMIT 1"),
        {"company_id": company["id"], "id": raw_id},
    )
    current = current_result.mappings().first()
    if not current:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    data = _product_payload(payload, dict(current))
    result = await db.execute(
        text("""
            UPDATE shoplink_products
            SET category = :category,
                name = :name,
                sku = :sku,
                size = :size,
                color = :color,
                description = :description,
                price = :price,
                stock = :stock,
                image_url = :image_url,
                image_url_2 = :image_url_2,
                image_url_3 = :image_url_3,
                inventory_item_id = :inventory_item_id,
                published = :published,
                archived = :archived,
                featured = :featured,
                updated_at = now()
            WHERE company_id = :company_id
              AND id = :id
            RETURNING *
        """),
        {"company_id": company["id"], "id": raw_id, **data},
    )
    await db.commit()
    return {"ok": True, "product": _shoplink_product_out(dict(result.mappings().first()), public_id=False)}


@router.delete("/companies/{company_id}/products/{product_id}")
async def delete_shoplink_product(
    company_id: UUID,
    product_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    await ensure_shoplink_storage(db)
    raw_id = _clean(product_id.replace("shoplink:", ""), 80)
    result = await db.execute(
        text("""
            DELETE FROM shoplink_products
            WHERE company_id = :company_id
              AND id = :id
            RETURNING id
        """),
        {"company_id": company["id"], "id": raw_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    await db.commit()
    return {"ok": True, "deleted_id": raw_id}


def _product_image_content_type(upload: UploadFile) -> str:
    content_type = (upload.content_type or "").strip().lower()
    filename = (upload.filename or "").strip().lower()
    if content_type in ALLOWED_PRODUCT_IMAGE_TYPES:
        return content_type
    if filename.endswith(".jpg") or filename.endswith(".jpeg"):
        return "image/jpeg"
    if filename.endswith(".png"):
        return "image/png"
    if filename.endswith(".webp"):
        return "image/webp"
    raise HTTPException(status_code=422, detail="Imagen invalida. Usa JPG, PNG o WEBP.")


async def _read_product_image_upload(upload: UploadFile) -> dict[str, Any]:
    content_type = _product_image_content_type(upload)
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=422, detail="Imagen vacia.")
    if len(content) > MAX_PRODUCT_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="Una imagen supera 5 MB.")
    return {"content_type": content_type, "content": content, "size": len(content)}


def _image_slot_has_value(row: dict[str, Any], position: int) -> bool:
    url_col, _, bytes_col, _ = _image_slot_columns(position)
    return bool(row.get(bytes_col) or row.get(url_col))


async def _write_product_image_slots(
    db: AsyncSession,
    company_id: str,
    raw_id: str,
    uploads: list[dict[str, Any]],
    append: bool = True,
) -> dict[str, Any]:
    if not uploads:
        raise HTTPException(status_code=422, detail="Selecciona al menos una imagen.")
    uploads = uploads[:MAX_PRODUCT_IMAGES]
    current_result = await db.execute(
        text("SELECT * FROM shoplink_products WHERE company_id = :company_id AND id = :id LIMIT 1"),
        {"company_id": company_id, "id": raw_id},
    )
    current = current_result.mappings().first()
    if not current:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    current_row = dict(current)
    if append:
        empty_positions = [position for position in range(1, MAX_PRODUCT_IMAGES + 1) if not _image_slot_has_value(current_row, position)]
        fallback_positions = [position for position in range(1, MAX_PRODUCT_IMAGES + 1) if position not in empty_positions]
        positions = (empty_positions + fallback_positions)[:len(uploads)]
    else:
        positions = list(range(1, MAX_PRODUCT_IMAGES + 1))[:len(uploads)]

    set_parts = ["updated_at = now()"]
    params: dict[str, Any] = {"company_id": company_id, "id": raw_id}
    for upload, position in zip(uploads, positions):
        url_col, content_type_col, bytes_col, size_col = _image_slot_columns(position)
        set_parts.extend([
            f"{url_col} = ''",
            f"{content_type_col} = :content_type_{position}",
            f"{bytes_col} = :content_{position}",
            f"{size_col} = :size_{position}",
        ])
        params[f"content_type_{position}"] = upload["content_type"]
        params[f"content_{position}"] = upload["content"]
        params[f"size_{position}"] = upload["size"]

    result = await db.execute(
        text(f"""
            UPDATE shoplink_products
            SET {", ".join(set_parts)}
            WHERE company_id = :company_id
              AND id = :id
            RETURNING *
        """),
        params,
    )
    row = result.mappings().first()
    await db.commit()
    return dict(row)


@router.post("/companies/{company_id}/products/{product_id}/images")
async def upload_shoplink_product_images(
    company_id: UUID,
    product_id: str,
    images: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    await ensure_shoplink_storage(db)
    raw_id = _clean(product_id.replace("shoplink:", ""), 80)
    uploads = [await _read_product_image_upload(image) for image in list(images or [])[:MAX_PRODUCT_IMAGES]]
    row = await _write_product_image_slots(db, company["id"], raw_id, uploads, append=True)
    return {"ok": True, "product": _shoplink_product_out(row, public_id=False)}


@router.post("/companies/{company_id}/products/{product_id}/image")
async def upload_shoplink_product_image(
    company_id: UUID,
    product_id: str,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    await ensure_shoplink_storage(db)
    raw_id = _clean(product_id.replace("shoplink:", ""), 80)
    upload = await _read_product_image_upload(image)
    row = await _write_product_image_slots(db, company["id"], raw_id, [upload], append=False)
    return {"ok": True, "product": _shoplink_product_out(row, public_id=False)}


@router.get("/products/{product_id}/images/{position}")
async def get_shoplink_product_image_at_position(
    product_id: str,
    position: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await ensure_shoplink_storage(db)
    raw_id = _clean(product_id.replace("shoplink:", ""), 80)
    _, content_type_col, bytes_col, _ = _image_slot_columns(position)
    result = await db.execute(
        text(f"""
            SELECT {content_type_col} AS image_content_type, {bytes_col} AS image_file_bytes
            FROM shoplink_products
            WHERE id = :id
            LIMIT 1
        """),
        {"id": raw_id},
    )
    row = result.mappings().first()
    if not row or not row.get("image_file_bytes"):
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")
    content = row.get("image_file_bytes")
    if isinstance(content, memoryview):
        content = content.tobytes()
    return Response(content=bytes(content), media_type=str(row.get("image_content_type") or "image/jpeg"))


@router.get("/products/{product_id}/image")
async def get_shoplink_product_image(product_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    return await get_shoplink_product_image_at_position(product_id, 1, db)


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

    order_id = str(uuid4())
    order_code = f"SL-{uuid4().hex[:8].upper()}"
    invoice_code = _invoice_code_for_order(order_code)
    currency = _clean(settings.get("currency") or "COP", 8).upper() or "COP"
    await ensure_shoplink_storage(db)
    await db.execute(
        text("""
            INSERT INTO shoplink_orders (
              id, company_id, order_code, customer_json, items_json,
              total_amount, currency, status, invoice_code, source, invoiced_at, updated_at
            )
            VALUES (
              :id, :company_id, :order_code, CAST(:customer AS jsonb), CAST(:items AS jsonb),
              :total_amount, :currency, 'new', :invoice_code, 'shoplink_public', now(), now()
            )
        """),
        {
            "id": order_id,
            "company_id": company["id"],
            "order_code": order_code,
            "invoice_code": invoice_code,
            "customer": json.dumps(customer, ensure_ascii=False),
            "items": json.dumps(items, ensure_ascii=False),
            "total_amount": total,
            "currency": currency,
        },
    )
    await db.commit()
    return {
        "ok": True,
        "id": order_id,
        "order_code": order_code,
        "invoice_code": invoice_code,
        "invoice_url": f"/api/v1/shoplink/companies/{company['id']}/orders/{order_id}/invoice",
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
