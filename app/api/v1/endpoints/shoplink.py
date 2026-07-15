from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.shoplink_whatsapp_web import whatsapp_logout, whatsapp_send, whatsapp_start, whatsapp_status

router = APIRouter()
MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PRODUCT_IMAGES = 3
ALLOWED_PRODUCT_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_GUIDE_FILE_BYTES = 8 * 1024 * 1024
ALLOWED_GUIDE_FILE_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


class ShoplinkSettingsIn(BaseModel):
    public_enabled: bool | None = True
    store_name: str | None = ""
    headline: str | None = ""
    description: str | None = ""
    whatsapp_number: str | None = ""
    cta_message: str | None = ""
    checkout_enabled: bool | None = True
    support_whatsapp_enabled: bool | None = False
    payment_proof_whatsapp: str | None = ""
    payment_proof_message: str | None = ""
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
    campaign_slug: str | None = ""
    coupon_code: str | None = ""
    payment_method: str | None = ""
    items: list[ShoplinkOrderItemIn] | None = None


class ShoplinkCouponValidateIn(BaseModel):
    campaign_slug: str | None = ""
    coupon_code: str | None = ""
    items: list[ShoplinkOrderItemIn] | None = None


class ShoplinkOrderUpdate(BaseModel):
    status: str | None = None
    guide_number: str | None = None
    guide_url: str | None = None
    guide_note: str | None = None


class ShoplinkWhatsAppTestIn(BaseModel):
    message: str | None = ""


class ShoplinkCustomerIn(BaseModel):
    name: str | None = ""
    phone: str | None = ""
    city: str | None = ""
    address: str | None = ""
    status: str | None = "nuevo"
    tag: str | None = ""
    note: str | None = ""
    source: str | None = "client_panel"
    mark_contacted: bool | None = False


class ShoplinkCampaignIn(BaseModel):
    title: str | None = ""
    slug: str | None = ""
    objective: str | None = ""
    status: str | None = "active"
    starts_at: str | None = ""
    ends_at: str | None = ""
    headline: str | None = ""
    description: str | None = ""
    banner_url: str | None = ""
    discount_label: str | None = ""
    coupon_code: str | None = ""
    discount_type: str | None = "none"
    discount_value: float | int | str | None = 0
    min_order: float | int | str | None = 0
    max_uses: int | str | None = 0
    product_ids: list[str] | None = None
    customer_segment: str | None = "todos"
    whatsapp_message: str | None = ""
    notes: str | None = ""
    landing_enabled: bool | None = True


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


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, Decimal):
        number = float(value)
        return number if math.isfinite(number) else 0.0
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return ""
    return value


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
        "payment_proof_whatsapp": "",
        "payment_proof_message": "Hola, envio el comprobante de pago de mi pedido:",
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
            payment_method text NOT NULL DEFAULT '',
            guide_number text NOT NULL DEFAULT '',
            guide_url text NOT NULL DEFAULT '',
            guide_note text NOT NULL DEFAULT '',
            guide_file_name text NOT NULL DEFAULT '',
            guide_file_content_type text NOT NULL DEFAULT '',
            guide_file_bytes bytea NULL,
            guide_file_size integer NOT NULL DEFAULT 0,
            source text NOT NULL DEFAULT 'shoplink_public',
            created_at timestamptz NOT NULL DEFAULT now(),
            invoiced_at timestamptz NULL,
            separated_at timestamptz NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    for stmt in [
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS invoice_code text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS payment_method text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_number text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_url text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_note text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_file_name text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_file_content_type text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_file_bytes bytea NULL",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS guide_file_size integer NOT NULL DEFAULT 0",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS invoiced_at timestamptz NULL",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS separated_at timestamptz NULL",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS campaign_slug text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS coupon_code text NOT NULL DEFAULT ''",
        "ALTER TABLE shoplink_orders ADD COLUMN IF NOT EXISTS discount_amount double precision NOT NULL DEFAULT 0",
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
        CREATE TABLE IF NOT EXISTS shoplink_customer_profiles (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            phone_key text NOT NULL,
            customer_name text NOT NULL DEFAULT '',
            customer_phone text NOT NULL DEFAULT '',
            customer_city text NOT NULL DEFAULT '',
            customer_address text NOT NULL DEFAULT '',
            status text NOT NULL DEFAULT 'nuevo',
            tag text NOT NULL DEFAULT '',
            note text NOT NULL DEFAULT '',
            source text NOT NULL DEFAULT 'shoplink',
            archived boolean NOT NULL DEFAULT false,
            last_contacted_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_shoplink_customer_profiles_company_phone
        ON shoplink_customer_profiles (company_id, phone_key)
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_shoplink_customer_profiles_company_status
        ON shoplink_customer_profiles (company_id, lower(status), updated_at DESC)
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS shoplink_campaigns (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            slug text NOT NULL DEFAULT '',
            title text NOT NULL DEFAULT '',
            objective text NOT NULL DEFAULT '',
            status text NOT NULL DEFAULT 'active',
            starts_at timestamptz NULL,
            ends_at timestamptz NULL,
            headline text NOT NULL DEFAULT '',
            description text NOT NULL DEFAULT '',
            banner_url text NOT NULL DEFAULT '',
            discount_label text NOT NULL DEFAULT '',
            coupon_code text NOT NULL DEFAULT '',
            discount_type text NOT NULL DEFAULT 'none',
            discount_value double precision NOT NULL DEFAULT 0,
            min_order double precision NOT NULL DEFAULT 0,
            max_uses integer NOT NULL DEFAULT 0,
            product_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            customer_segment text NOT NULL DEFAULT 'todos',
            whatsapp_message text NOT NULL DEFAULT '',
            notes text NOT NULL DEFAULT '',
            landing_enabled boolean NOT NULL DEFAULT true,
            archived boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_shoplink_campaigns_company_slug
        ON shoplink_campaigns (company_id, slug)
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_shoplink_campaigns_company_status
        ON shoplink_campaigns (company_id, lower(status), updated_at DESC)
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
        "payment_proof_whatsapp": "",
        "payment_proof_message": "Hola, envio el comprobante de pago de mi pedido:",
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


def _campaign_public_url(settings: dict[str, Any], company_id: str, slug: str) -> str:
    return f"{_public_url(settings, company_id)}&campaign={_clean(slug, 100)}"


def _campaign_status(value: Any) -> str:
    raw = _clean(value, 40).lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "activo": "active",
        "activa": "active",
        "active": "active",
        "live": "active",
        "programada": "scheduled",
        "programado": "scheduled",
        "scheduled": "scheduled",
        "borrador": "draft",
        "draft": "draft",
        "pausada": "paused",
        "pausado": "paused",
        "paused": "paused",
        "finalizada": "finished",
        "finalizado": "finished",
        "finished": "finished",
        "archivada": "archived",
        "archivado": "archived",
        "archived": "archived",
    }
    normalized = aliases.get(raw, raw)
    allowed = {"active", "scheduled", "draft", "paused", "finished", "archived"}
    return normalized if normalized in allowed else "active"


def _campaign_status_label(value: Any) -> str:
    labels = {
        "active": "Activa",
        "scheduled": "Programada",
        "draft": "Borrador",
        "paused": "Pausada",
        "finished": "Finalizada",
        "archived": "Archivada",
    }
    return labels.get(_campaign_status(value), "Activa")


def _campaign_segment_label(value: Any) -> str:
    labels = {
        "todos": "Todos los clientes",
        "nuevos": "Clientes nuevos",
        "recurrentes": "Clientes recurrentes",
        "vip": "VIP",
        "seguimiento": "Seguimiento pendiente",
        "ciudad": "Por ciudad",
    }
    return labels.get(_clean(value, 40).lower(), "Todos los clientes")


def _campaign_product_ids(value: Any) -> list[str]:
    raw = value
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "[]")
            raw = parsed
        except json.JSONDecodeError:
            raw = [part.strip() for part in raw.split(",")]
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    ids: list[str] = []
    for item in raw:
        product_id = _clean(item, 120)
        if not product_id or product_id in seen:
            continue
        seen.add(product_id)
        ids.append(product_id)
    return ids[:120]


def _campaign_slug(value: Any, title: Any = "") -> str:
    return _slug(_clean(value, 100) or _clean(title, 120) or f"campana-{uuid4().hex[:6]}")


def _campaign_discount_type(value: Any) -> str:
    raw = _clean(value, 40).lower()
    if raw in {"percent", "porcentaje", "%"}:
        return "percent"
    if raw in {"amount", "fixed", "valor", "fijo"}:
        return "amount"
    return "none"


def _campaign_payload(payload: ShoplinkCampaignIn, current: dict[str, Any] | None = None) -> dict[str, Any]:
    current = current or {}
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    title = _clean(data.get("title", current.get("title")), 140)
    if not title:
        raise HTTPException(status_code=422, detail="Nombre de campana requerido.")
    slug = _campaign_slug(data.get("slug", current.get("slug")), title)
    discount_type = _campaign_discount_type(data.get("discount_type", current.get("discount_type")))
    discount_value = max(0.0, _money(data.get("discount_value", current.get("discount_value"))))
    if discount_type == "percent":
        discount_value = min(discount_value, 90.0)
    return {
        "title": title,
        "slug": slug,
        "objective": _clean(data.get("objective", current.get("objective")), 160),
        "status": _campaign_status(data.get("status", current.get("status"))),
        "starts_at": _clean(data.get("starts_at", current.get("starts_at")), 40),
        "ends_at": _clean(data.get("ends_at", current.get("ends_at")), 40),
        "headline": _clean(data.get("headline", current.get("headline")), 180),
        "description": _clean(data.get("description", current.get("description")), 700),
        "banner_url": _clean(data.get("banner_url", current.get("banner_url")), 1000),
        "discount_label": _clean(data.get("discount_label", current.get("discount_label")), 120),
        "coupon_code": _clean(data.get("coupon_code", current.get("coupon_code")), 40).upper(),
        "discount_type": discount_type,
        "discount_value": discount_value,
        "min_order": max(0.0, _money(data.get("min_order", current.get("min_order")))),
        "max_uses": max(0, min(int(float(data.get("max_uses", current.get("max_uses")) or 0)), 100000)),
        "product_ids": _campaign_product_ids(data.get("product_ids", current.get("product_ids"))),
        "customer_segment": _clean(data.get("customer_segment", current.get("customer_segment")) or "todos", 40).lower() or "todos",
        "whatsapp_message": _clean(data.get("whatsapp_message", current.get("whatsapp_message")), 700),
        "notes": _clean(data.get("notes", current.get("notes")), 700),
        "landing_enabled": bool(data.get("landing_enabled", current.get("landing_enabled", True))),
    }


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


def _customer_phone_key(value: Any) -> str:
    return re.sub(r"\D+", "", _clean(value, 60))


def _customer_fallback_key(name: Any, city: Any = "") -> str:
    seed = " ".join([_clean(name, 100), _clean(city, 80)]).strip().lower()
    key = re.sub(r"[^a-z0-9]+", "-", seed).strip("-")
    return f"name-{key}" if key else ""


def _customer_key(customer: dict[str, Any]) -> str:
    return _customer_phone_key(customer.get("phone")) or _customer_fallback_key(customer.get("name"), customer.get("city"))


def _customer_status(value: Any) -> str:
    raw = _clean(value, 40).lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "nuevo": "nuevo",
        "new": "nuevo",
        "lead": "prospecto",
        "prospect": "prospecto",
        "prospecto": "prospecto",
        "seguimiento": "seguimiento",
        "follow_up": "seguimiento",
        "pendiente": "seguimiento",
        "recurrente": "recurrente",
        "repeat": "recurrente",
        "vip": "vip",
        "frio": "frio",
        "cold": "frio",
        "bloqueado": "bloqueado",
        "blocked": "bloqueado",
        "archivado": "archivado",
        "archived": "archivado",
    }
    normalized = aliases.get(raw, raw)
    allowed = {"nuevo", "prospecto", "seguimiento", "recurrente", "vip", "frio", "bloqueado", "archivado"}
    return normalized if normalized in allowed else "nuevo"


def _customer_status_label(value: Any) -> str:
    labels = {
        "nuevo": "Nuevo",
        "prospecto": "Prospecto",
        "seguimiento": "Seguimiento",
        "recurrente": "Recurrente",
        "vip": "VIP",
        "frio": "Frio",
        "bloqueado": "Bloqueado",
        "archivado": "Archivado",
    }
    return labels.get(_customer_status(value), "Nuevo")


def _format_invoice_money(value: Any, currency: str = "COP") -> str:
    number = _money(value)
    formatted = f"{number:,.0f}".replace(",", ".")
    return f"{_clean(currency, 8).upper() or 'COP'} {formatted}"


def _absolute_public_url(base_url: str, url: str) -> str:
    clean_url = _clean(url, 1000)
    if not clean_url:
        return ""
    if clean_url.startswith(("http://", "https://")):
        return clean_url
    return f"{base_url.rstrip('/')}/{clean_url.lstrip('/')}"


def _shoplink_whatsapp_phone(value: Any) -> str:
    phone = re.sub(r"\D", "", _clean(value, 60))
    if phone.startswith("00"):
        phone = phone[2:]
    if len(phone) == 10 and phone.startswith("3"):
        phone = f"57{phone}"
    return phone


def _shoplink_owner_alert(
    company: dict[str, Any],
    settings: dict[str, Any],
    order: dict[str, Any],
    base_url: str,
) -> dict[str, str]:
    phone = _shoplink_whatsapp_phone(settings.get("payment_proof_whatsapp") or settings.get("whatsapp_number"))
    if not phone:
        return {"phone": "", "message": "", "url": ""}
    items = order.get("items") or []
    item_lines = [
        f"- {int(item.get('qty') or 1)}x {_clean(item.get('name'), 90)}"
        for item in items[:6]
        if _clean(item.get("name"), 90)
    ]
    if len(items) > 6:
        item_lines.append(f"- +{len(items) - 6} articulos mas")
    invoice_pdf_url = _absolute_public_url(base_url, order.get("invoice_pdf_url") or "")
    customer = [
        _clean(order.get("customer_name"), 120),
        _clean(order.get("customer_phone"), 40),
    ]
    delivery = " / ".join([
        _clean(order.get("customer_city"), 120),
        _clean(order.get("customer_address"), 220),
    ]).strip(" /")
    message = "\n".join([
        "Nuevo pedido ShopLink",
        f"Tienda: {_clean(settings.get('store_name') or company.get('name'), 120)}",
        f"Pedido: {_clean(order.get('order_code'), 60)}",
        f"Factura: {_clean(order.get('invoice_code'), 60)}",
        f"Cliente: {' - '.join([part for part in customer if part]) or 'Cliente'}",
        f"Entrega: {delivery or 'Por confirmar'}",
        f"Pago: {_clean(order.get('payment_method'), 60) or 'Por confirmar'}",
        "Articulos:",
        *(item_lines or ["- Sin detalle"]),
        f"Total: {_format_invoice_money(order.get('total_amount'), order.get('currency') or settings.get('currency') or 'COP')}",
        f"Factura PDF: {invoice_pdf_url}" if invoice_pdf_url else "",
        "Entra al panel Carrito y Pedidos para revisar.",
    ]).strip()
    return {
        "phone": phone,
        "message": message,
        "url": f"https://wa.me/{phone}?text={quote(message)}",
    }


async def _send_shoplink_owner_alert(company_id: str, alert: dict[str, str]) -> dict[str, Any]:
    phone = alert.get("phone") or ""
    message = alert.get("message") or ""
    if not phone or not message:
        return {"ok": False, "status": "missing_phone", "detail": "WhatsApp receptor no configurado."}
    try:
        status = await whatsapp_status(company_id)
        if status.get("status") != "connected":
            return {
                "ok": False,
                "status": status.get("status") or "not_linked",
                "detail": "WhatsApp Web no esta vinculado.",
            }
        return await whatsapp_send(company_id, phone, message)
    except Exception as exc:
        return {"ok": False, "status": "send_error", "detail": str(exc)}


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
        "invoice_pdf_url": f"/api/v1/shoplink/companies/{source_company_id}/orders/{order_id}/invoice.pdf",
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
        "campaign_slug": _clean(row.get("campaign_slug"), 100),
        "coupon_code": _clean(row.get("coupon_code"), 40),
        "discount_amount": float(row.get("discount_amount") or 0),
        "payment_method": _clean(row.get("payment_method"), 60),
        "status": status,
        "status_label": _order_status_label(status),
        "guide_number": _clean(row.get("guide_number"), 120),
        "guide_url": _clean(row.get("guide_url"), 500),
        "guide_note": _clean(row.get("guide_note"), 500),
        "guide_file_name": _clean(row.get("guide_file_name"), 180),
        "guide_file_size": int(row.get("guide_file_size") or 0),
        "has_guide_file": bool(row.get("guide_file_bytes")),
        "guide_file_url": (
            f"/api/v1/shoplink/companies/{source_company_id}/orders/{order_id}/guide-file"
            if row.get("guide_file_bytes") else ""
        ),
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


async def _shoplink_customer_profile_rows(db: AsyncSession, company_id: str) -> dict[str, dict[str, Any]]:
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT *
            FROM shoplink_customer_profiles
            WHERE company_id = :company_id
              AND COALESCE(archived, false) IS NOT TRUE
        """),
        {"company_id": company_id},
    )
    return {
        _clean(row.get("phone_key"), 120): dict(row)
        for row in result.mappings().all()
        if _clean(row.get("phone_key"), 120)
    }


def _customer_profile_out(row: dict[str, Any] | None = None) -> dict[str, Any]:
    row = row or {}
    status = _customer_status(row.get("status"))
    return {
        "profile_id": _clean(row.get("id"), 80),
        "status": status,
        "status_label": _customer_status_label(status),
        "tag": _clean(row.get("tag"), 80),
        "note": _clean(row.get("note"), 700),
        "source": _clean(row.get("source"), 80),
        "last_contacted_at": str(row.get("last_contacted_at") or ""),
        "profile_updated_at": str(row.get("updated_at") or ""),
    }


async def _shoplink_customer_rows(db: AsyncSession, company_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    orders = [_shoplink_order_out(row, company_id) for row in await _shoplink_order_rows(db, company_id, limit)]
    profiles = await _shoplink_customer_profile_rows(db, company_id)
    grouped: dict[str, dict[str, Any]] = {}

    for order in orders:
        customer = order.get("customer") or {}
        key = _customer_key(customer)
        if not key:
            continue
        bucket = grouped.setdefault(key, {
            "customer_key": key,
            "name": "",
            "phone": "",
            "city": "",
            "address": "",
            "orders_count": 0,
            "total_amount": 0.0,
            "currency": order.get("currency") or "COP",
            "first_order_at": "",
            "last_order_at": "",
            "last_order_code": "",
            "last_order_id": "",
            "last_order_status": "",
            "last_order_status_label": "",
            "last_order_total": 0.0,
            "last_items_summary": "",
            "orders": [],
        })
        bucket["orders_count"] += 1
        if order.get("status") != "cancelled":
            bucket["total_amount"] += float(order.get("total_amount") or 0)
        if not bucket["name"]:
            bucket["name"] = _clean(customer.get("name"), 120) or order.get("customer_name") or ""
        if not bucket["phone"]:
            bucket["phone"] = _clean(customer.get("phone"), 40) or order.get("customer_phone") or ""
        if not bucket["city"]:
            bucket["city"] = _clean(customer.get("city"), 120) or order.get("customer_city") or ""
        if not bucket["address"]:
            bucket["address"] = _clean(customer.get("address"), 220) or order.get("customer_address") or ""
        created = str(order.get("created_at") or "")
        if not bucket["first_order_at"] or created < bucket["first_order_at"]:
            bucket["first_order_at"] = created
        if not bucket["last_order_at"] or created > bucket["last_order_at"]:
            bucket["last_order_at"] = created
            bucket["last_order_code"] = order.get("order_code") or ""
            bucket["last_order_id"] = order.get("id") or ""
            bucket["last_order_status"] = order.get("status") or ""
            bucket["last_order_status_label"] = order.get("status_label") or ""
            bucket["last_order_total"] = float(order.get("total_amount") or 0)
            bucket["last_items_summary"] = order.get("items_summary") or ""
        bucket["orders"].append({
            "id": order.get("id"),
            "order_code": order.get("order_code"),
            "invoice_code": order.get("invoice_code"),
            "status": order.get("status"),
            "status_label": order.get("status_label"),
            "total_amount": order.get("total_amount"),
            "created_at": order.get("created_at"),
            "items_summary": order.get("items_summary"),
        })

    for key, profile in profiles.items():
        bucket = grouped.setdefault(key, {
            "customer_key": key,
            "name": "",
            "phone": "",
            "city": "",
            "address": "",
            "orders_count": 0,
            "total_amount": 0.0,
            "currency": "COP",
            "first_order_at": "",
            "last_order_at": "",
            "last_order_code": "",
            "last_order_id": "",
            "last_order_status": "",
            "last_order_status_label": "",
            "last_order_total": 0.0,
            "last_items_summary": "",
            "orders": [],
        })
        bucket["name"] = _clean(profile.get("customer_name"), 120) or bucket["name"]
        bucket["phone"] = _clean(profile.get("customer_phone"), 40) or bucket["phone"]
        bucket["city"] = _clean(profile.get("customer_city"), 120) or bucket["city"]
        bucket["address"] = _clean(profile.get("customer_address"), 220) or bucket["address"]

    output: list[dict[str, Any]] = []
    for key, bucket in grouped.items():
        profile = profiles.get(key, {})
        profile_out = _customer_profile_out(profile)
        default_status = "recurrente" if int(bucket.get("orders_count") or 0) > 1 else "nuevo"
        if not profile:
            profile_out["status"] = default_status
            profile_out["status_label"] = _customer_status_label(default_status)
        output.append({
            **bucket,
            **profile_out,
            "orders": sorted(bucket.get("orders") or [], key=lambda item: str(item.get("created_at") or ""), reverse=True)[:8],
        })

    output.sort(key=lambda item: (str(item.get("last_order_at") or item.get("profile_updated_at") or ""), float(item.get("total_amount") or 0)), reverse=True)
    return output


async def _upsert_shoplink_customer_profile(
    db: AsyncSession,
    company_id: str,
    customer_key: str,
    payload: ShoplinkCustomerIn,
) -> dict[str, Any]:
    key = _clean(customer_key, 120)
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    phone = _clean(data.get("phone"), 40)
    if not key:
        key = _customer_phone_key(phone) or _customer_fallback_key(data.get("name"), data.get("city"))
    if not key:
        raise HTTPException(status_code=422, detail="Cliente requiere WhatsApp o nombre.")
    status = _customer_status(data.get("status"))
    result = await db.execute(
        text("""
            INSERT INTO shoplink_customer_profiles (
                id,
                company_id,
                phone_key,
                customer_name,
                customer_phone,
                customer_city,
                customer_address,
                status,
                tag,
                note,
                source,
                last_contacted_at,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :company_id,
                :phone_key,
                :customer_name,
                :customer_phone,
                :customer_city,
                :customer_address,
                :status,
                :tag,
                :note,
                :source,
                CASE WHEN :mark_contacted IS TRUE THEN now() ELSE NULL END,
                now(),
                now()
            )
            ON CONFLICT (company_id, phone_key) DO UPDATE
            SET
                customer_name = COALESCE(NULLIF(EXCLUDED.customer_name, ''), shoplink_customer_profiles.customer_name),
                customer_phone = COALESCE(NULLIF(EXCLUDED.customer_phone, ''), shoplink_customer_profiles.customer_phone),
                customer_city = COALESCE(NULLIF(EXCLUDED.customer_city, ''), shoplink_customer_profiles.customer_city),
                customer_address = COALESCE(NULLIF(EXCLUDED.customer_address, ''), shoplink_customer_profiles.customer_address),
                status = EXCLUDED.status,
                tag = EXCLUDED.tag,
                note = EXCLUDED.note,
                source = EXCLUDED.source,
                archived = false,
                last_contacted_at = CASE
                    WHEN :mark_contacted IS TRUE THEN now()
                    ELSE shoplink_customer_profiles.last_contacted_at
                END,
                updated_at = now()
            RETURNING *
        """),
        {
            "id": str(uuid4()),
            "company_id": company_id,
            "phone_key": key,
            "customer_name": _clean(data.get("name"), 120),
            "customer_phone": phone,
            "customer_city": _clean(data.get("city"), 120),
            "customer_address": _clean(data.get("address"), 220),
            "status": status,
            "tag": _clean(data.get("tag"), 80),
            "note": _clean(data.get("note"), 700),
            "source": _clean(data.get("source"), 80) or "client_panel",
            "mark_contacted": bool(data.get("mark_contacted", False)),
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    await db.commit()
    return dict(row)


def _campaign_product_match(product_id: Any, product_ids: list[str]) -> bool:
    value = _clean(product_id, 140)
    if not value:
        return False
    raw = value.replace("shoplink:", "")
    return value in product_ids or raw in product_ids or f"shoplink:{raw}" in product_ids


def _campaign_order_has_product(order: dict[str, Any], product_ids: list[str]) -> bool:
    if not product_ids:
        return True
    for item in order.get("items") or []:
        if _campaign_product_match(item.get("product_id"), product_ids):
            return True
    return False


def _campaign_order_base(order: dict[str, Any], product_ids: list[str]) -> float:
    if not product_ids:
        return float(order.get("total_amount") or 0) + float(order.get("discount_amount") or 0)
    total = 0.0
    for item in order.get("items") or []:
        if _campaign_product_match(item.get("product_id"), product_ids):
            total += float(item.get("subtotal") or 0)
    return total


def _shoplink_campaign_out(
    row: dict[str, Any],
    settings: dict[str, Any],
    products: list[dict[str, Any]] | None = None,
    orders: list[dict[str, Any]] | None = None,
    include_private: bool = True,
) -> dict[str, Any]:
    products = products or []
    orders = orders or []
    product_ids = _campaign_product_ids(row.get("product_ids"))
    slug = _campaign_slug(row.get("slug"), row.get("title"))
    linked_products = [
        product for product in products
        if _campaign_product_match(product.get("id") or product.get("raw_id"), product_ids)
    ] if product_ids else []
    direct_orders = [order for order in orders if _clean(order.get("campaign_slug"), 100) == slug]
    matched_orders = [
        order for order in orders
        if order not in direct_orders and _campaign_order_has_product(order, product_ids)
    ] if product_ids else []
    status = _campaign_status(row.get("status"))
    return {
        "id": _clean(row.get("id"), 80),
        "slug": slug,
        "title": _clean(row.get("title"), 140),
        "objective": _clean(row.get("objective"), 160),
        "status": status,
        "status_label": _campaign_status_label(status),
        "starts_at": str(row.get("starts_at") or ""),
        "ends_at": str(row.get("ends_at") or ""),
        "headline": _clean(row.get("headline"), 180),
        "description": _clean(row.get("description"), 700),
        "banner_url": _clean(row.get("banner_url"), 1000),
        "discount_label": _clean(row.get("discount_label"), 120),
        "coupon_code": _clean(row.get("coupon_code"), 40) if include_private else "",
        "coupon_required": bool(_clean(row.get("coupon_code"), 40)),
        "discount_type": _campaign_discount_type(row.get("discount_type")),
        "discount_value": float(row.get("discount_value") or 0),
        "min_order": float(row.get("min_order") or 0),
        "max_uses": int(row.get("max_uses") or 0),
        "product_ids": product_ids,
        "products_count": len(linked_products),
        "products_preview": linked_products[:8],
        "customer_segment": _clean(row.get("customer_segment") or "todos", 40),
        "customer_segment_label": _campaign_segment_label(row.get("customer_segment")),
        "whatsapp_message": _clean(row.get("whatsapp_message"), 700),
        "notes": _clean(row.get("notes"), 700),
        "landing_enabled": bool(row.get("landing_enabled")),
        "archived": bool(row.get("archived")) or status == "archived",
        "landing_url": _campaign_public_url(settings, _clean(row.get("company_id"), 80), slug),
        "direct_orders": len(direct_orders),
        "direct_sales": sum(float(order.get("total_amount") or 0) for order in direct_orders if order.get("status") != "cancelled"),
        "discounts_used": sum(float(order.get("discount_amount") or 0) for order in direct_orders),
        "matched_orders": len(matched_orders),
        "matched_sales": sum(float(order.get("total_amount") or 0) for order in matched_orders if order.get("status") != "cancelled"),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


async def _shoplink_campaign_rows(db: AsyncSession, company_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
    await ensure_shoplink_storage(db)
    archived_clause = "" if include_archived else "AND COALESCE(archived, false) IS NOT TRUE"
    result = await db.execute(
        text(f"""
            SELECT *
            FROM shoplink_campaigns
            WHERE company_id = :company_id
              {archived_clause}
            ORDER BY
              CASE lower(status)
                WHEN 'active' THEN 0
                WHEN 'scheduled' THEN 1
                WHEN 'draft' THEN 2
                WHEN 'paused' THEN 3
                ELSE 4
              END,
              updated_at DESC
            LIMIT 300
        """),
        {"company_id": company_id},
    )
    return [dict(row) for row in result.mappings().all()]


def _filter_shoplink_campaigns(campaigns: list[dict[str, Any]], q: str = "", status: str = "all") -> list[dict[str, Any]]:
    query = _clean(q, 140).lower()
    rows = campaigns
    if query:
        rows = [
            row for row in rows
            if query in " ".join([
                row.get("title") or "",
                row.get("slug") or "",
                row.get("status_label") or "",
                row.get("coupon_code") or "",
                row.get("discount_label") or "",
                row.get("customer_segment_label") or "",
                ", ".join([product.get("name") or "" for product in row.get("products_preview") or []]),
            ]).lower()
        ]
    status_filter = _clean(status, 40).lower()
    if status_filter and status_filter not in {"all", "todos"}:
        if status_filter in {"archivadas", "archivados", "archived"}:
            rows = [row for row in rows if row.get("archived") or row.get("status") == "archived"]
        else:
            wanted = _campaign_status(status_filter)
            rows = [row for row in rows if _campaign_status(row.get("status")) == wanted and not row.get("archived")]
    return rows


def _campaign_report_summary(
    campaigns: list[dict[str, Any]],
    all_campaigns: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    products: list[dict[str, Any]],
    customers: list[dict[str, Any]],
) -> dict[str, Any]:
    valid_orders = [row for row in orders if row.get("status") != "cancelled"]
    total_sales = sum(float(row.get("total_amount") or 0) for row in valid_orders)
    campaign_orders = sum(int(row.get("direct_orders") or 0) for row in campaigns)
    campaign_sales = sum(float(row.get("direct_sales") or 0) for row in campaigns)
    discounts = sum(float(row.get("discounts_used") or 0) for row in campaigns)
    product_stats: dict[str, dict[str, Any]] = {}
    for order in valid_orders:
        for item in order.get("items") or []:
            key = _clean(item.get("product_id") or item.get("name"), 160)
            if not key:
                continue
            bucket = product_stats.setdefault(key, {
                "name": _clean(item.get("name"), 180) or "Producto",
                "category": _clean(item.get("category"), 80),
                "qty": 0,
                "sales": 0.0,
            })
            bucket["qty"] += int(item.get("qty") or 0)
            bucket["sales"] += float(item.get("subtotal") or 0)
    top_products = sorted(product_stats.values(), key=lambda item: (float(item.get("sales") or 0), int(item.get("qty") or 0)), reverse=True)[:8]
    return {
        "campaigns": len(campaigns),
        "total_campaigns": len(all_campaigns),
        "active": len([row for row in all_campaigns if row.get("status") == "active" and row.get("landing_enabled") and not row.get("archived")]),
        "scheduled": len([row for row in all_campaigns if row.get("status") == "scheduled" and not row.get("archived")]),
        "archived": len([row for row in all_campaigns if row.get("archived") or row.get("status") == "archived"]),
        "direct_orders": campaign_orders,
        "direct_sales": campaign_sales,
        "matched_sales": sum(float(row.get("matched_sales") or 0) for row in campaigns),
        "discounts": discounts,
        "orders_total": len(orders),
        "paid_orders": len(valid_orders),
        "sales_total": total_sales,
        "avg_order": (total_sales / len(valid_orders)) if valid_orders else 0,
        "campaign_share": round((campaign_sales / total_sales) * 100, 1) if total_sales else 0,
        "products": len(products),
        "customers": len(customers),
        "repeat_customers": len([customer for customer in customers if int(customer.get("orders_count") or 0) > 1]),
        "top_products": top_products,
    }


async def _shoplink_campaign_by_id(db: AsyncSession, company_id: str, campaign_id: str) -> dict[str, Any]:
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT *
            FROM shoplink_campaigns
            WHERE company_id = :company_id
              AND id = :id
            LIMIT 1
        """),
        {"company_id": company_id, "id": _clean(campaign_id, 80)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Campana no encontrada.")
    return dict(row)


async def _active_shoplink_campaign_by_slug(db: AsyncSession, company_id: str, slug: str) -> dict[str, Any] | None:
    clean_slug = _slug(_clean(slug, 100))
    if not clean_slug:
        return None
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT *
            FROM shoplink_campaigns
            WHERE company_id = :company_id
              AND slug = :slug
              AND lower(status) = 'active'
              AND landing_enabled IS TRUE
              AND COALESCE(archived, false) IS NOT TRUE
              AND (starts_at IS NULL OR starts_at <= now())
              AND (ends_at IS NULL OR ends_at >= now())
            LIMIT 1
        """),
        {"company_id": company_id, "slug": clean_slug},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _active_shoplink_campaign_by_coupon(db: AsyncSession, company_id: str, coupon_code: str) -> dict[str, Any] | None:
    clean_coupon = _clean(coupon_code, 40).upper()
    if not clean_coupon:
        return None
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT *
            FROM shoplink_campaigns
            WHERE company_id = :company_id
              AND upper(coupon_code) = :coupon_code
              AND lower(status) = 'active'
              AND landing_enabled IS TRUE
              AND COALESCE(archived, false) IS NOT TRUE
              AND (starts_at IS NULL OR starts_at <= now())
              AND (ends_at IS NULL OR ends_at >= now())
            ORDER BY updated_at DESC
            LIMIT 1
        """),
        {"company_id": company_id, "coupon_code": clean_coupon},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _shoplink_campaign_uses(db: AsyncSession, company_id: str, campaign_slug: str) -> int:
    clean_slug = _slug(_clean(campaign_slug, 100))
    if not clean_slug:
        return 0
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            SELECT count(*)
            FROM shoplink_orders
            WHERE company_id = :company_id
              AND campaign_slug = :campaign_slug
              AND discount_amount > 0
              AND lower(status) <> 'cancelled'
        """),
        {"company_id": company_id, "campaign_slug": clean_slug},
    )
    return int(result.scalar() or 0)


async def _save_shoplink_campaign(
    db: AsyncSession,
    company_id: str,
    payload: ShoplinkCampaignIn,
    campaign_id: str = "",
) -> dict[str, Any]:
    current = await _shoplink_campaign_by_id(db, company_id, campaign_id) if campaign_id else {}
    data = _campaign_payload(payload, current)
    if campaign_id:
        result = await db.execute(
            text("""
                UPDATE shoplink_campaigns
                SET
                  slug = :slug,
                  title = :title,
                  objective = :objective,
                  status = :status,
                  starts_at = NULLIF(:starts_at, '')::timestamptz,
                  ends_at = NULLIF(:ends_at, '')::timestamptz,
                  headline = :headline,
                  description = :description,
                  banner_url = :banner_url,
                  discount_label = :discount_label,
                  coupon_code = :coupon_code,
                  discount_type = :discount_type,
                  discount_value = :discount_value,
                  min_order = :min_order,
                  max_uses = :max_uses,
                  product_ids = CAST(:product_ids AS jsonb),
                  customer_segment = :customer_segment,
                  whatsapp_message = :whatsapp_message,
                  notes = :notes,
                  landing_enabled = :landing_enabled,
                  archived = CASE WHEN :status = 'archived' THEN true ELSE false END,
                  updated_at = now()
                WHERE company_id = :company_id
                  AND id = :id
                RETURNING *
            """),
            {
                **data,
                "company_id": company_id,
                "id": _clean(campaign_id, 80),
                "product_ids": json.dumps(data["product_ids"], ensure_ascii=False),
            },
        )
    else:
        result = await db.execute(
            text("""
                INSERT INTO shoplink_campaigns (
                  id, company_id, slug, title, objective, status, starts_at, ends_at,
                  headline, description, banner_url, discount_label, coupon_code,
                  discount_type, discount_value, min_order, max_uses, product_ids,
                  customer_segment, whatsapp_message, notes, landing_enabled, archived,
                  created_at, updated_at
                )
                VALUES (
                  :id, :company_id, :slug, :title, :objective, :status,
                  NULLIF(:starts_at, '')::timestamptz, NULLIF(:ends_at, '')::timestamptz,
                  :headline, :description, :banner_url, :discount_label, :coupon_code,
                  :discount_type, :discount_value, :min_order, :max_uses, CAST(:product_ids AS jsonb),
                  :customer_segment, :whatsapp_message, :notes, :landing_enabled, false,
                  now(), now()
                )
                ON CONFLICT (company_id, slug) DO UPDATE
                SET
                  title = EXCLUDED.title,
                  objective = EXCLUDED.objective,
                  status = EXCLUDED.status,
                  starts_at = EXCLUDED.starts_at,
                  ends_at = EXCLUDED.ends_at,
                  headline = EXCLUDED.headline,
                  description = EXCLUDED.description,
                  banner_url = EXCLUDED.banner_url,
                  discount_label = EXCLUDED.discount_label,
                  coupon_code = EXCLUDED.coupon_code,
                  discount_type = EXCLUDED.discount_type,
                  discount_value = EXCLUDED.discount_value,
                  min_order = EXCLUDED.min_order,
                  max_uses = EXCLUDED.max_uses,
                  product_ids = EXCLUDED.product_ids,
                  customer_segment = EXCLUDED.customer_segment,
                  whatsapp_message = EXCLUDED.whatsapp_message,
                  notes = EXCLUDED.notes,
                  landing_enabled = EXCLUDED.landing_enabled,
                  archived = false,
                  updated_at = now()
                RETURNING *
            """),
            {
                **data,
                "company_id": company_id,
                "id": str(uuid4()),
                "product_ids": json.dumps(data["product_ids"], ensure_ascii=False),
            },
        )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Campana no encontrada.")
    await db.commit()
    return dict(row)


def _campaign_discount_amount(campaign: dict[str, Any] | None, items: list[dict[str, Any]], subtotal: float, coupon_code: str = "") -> float:
    if not campaign:
        return 0.0
    discount_type = _campaign_discount_type(campaign.get("discount_type"))
    value = float(campaign.get("discount_value") or 0)
    if discount_type == "none" or value <= 0:
        return 0.0
    expected_coupon = _clean(campaign.get("coupon_code"), 40).upper()
    provided_coupon = _clean(coupon_code, 40).upper()
    if expected_coupon and expected_coupon != provided_coupon:
        return 0.0
    if subtotal < float(campaign.get("min_order") or 0):
        return 0.0
    product_ids = _campaign_product_ids(campaign.get("product_ids"))
    base = subtotal
    if product_ids:
        base = sum(
            float(item.get("subtotal") or 0)
            for item in items
            if _campaign_product_match(item.get("product_id"), product_ids)
        )
    if base <= 0:
        return 0.0
    if discount_type == "percent":
        return min(base, round(base * min(value, 90.0) / 100, 2))
    if discount_type == "amount":
        return min(base, value)
    return 0.0


def _campaign_coupon_quote(
    campaign: dict[str, Any] | None,
    items: list[dict[str, Any]],
    subtotal: float,
    coupon_code: str,
    uses: int = 0,
) -> dict[str, Any]:
    provided = _clean(coupon_code, 40).upper()
    if not provided or not campaign:
        return {"valid": False, "discount_amount": 0.0, "message": "El cupon no existe o ya no esta activo."}
    expected = _clean(campaign.get("coupon_code"), 40).upper()
    if not expected or expected != provided:
        return {"valid": False, "discount_amount": 0.0, "message": "El cupon no existe o ya no esta activo."}
    max_uses = max(0, int(campaign.get("max_uses") or 0))
    if max_uses and uses >= max_uses:
        return {"valid": False, "discount_amount": 0.0, "message": "Este cupon alcanzo su limite de usos."}
    minimum = float(campaign.get("min_order") or 0)
    if subtotal < minimum:
        return {
            "valid": False,
            "discount_amount": 0.0,
            "message": f"El cupon aplica desde una compra de {_format_invoice_money(minimum, 'COP')}.",
        }
    product_ids = _campaign_product_ids(campaign.get("product_ids"))
    if product_ids and not any(_campaign_product_match(item.get("product_id"), product_ids) for item in items):
        return {"valid": False, "discount_amount": 0.0, "message": "El cupon no aplica a los productos del carrito."}
    discount = _campaign_discount_amount(campaign, items, subtotal, provided)
    if discount <= 0:
        return {"valid": False, "discount_amount": 0.0, "message": "Este cupon no tiene un descuento disponible."}
    return {
        "valid": True,
        "discount_amount": discount,
        "message": "Cupon aplicado correctamente.",
    }


def _shoplink_checkout_items(catalog: dict[str, dict[str, Any]], raw_items: list[Any] | None) -> tuple[list[dict[str, Any]], float]:
    items: list[dict[str, Any]] = []
    total = 0.0
    for raw in raw_items or []:
        data = raw.model_dump() if hasattr(raw, "model_dump") else (raw.dict() if hasattr(raw, "dict") else dict(raw or {}))
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
    return items, total


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
    discount_amount = float(order.get("discount_amount") or 0)
    discount_line = (
        f"<p>Descuento: {escape(_format_invoice_money(discount_amount, currency))}"
        f"{' / Cupon ' + escape(order.get('coupon_code') or '') if order.get('coupon_code') else ''}</p>"
        if discount_amount > 0 else ""
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
        <p>Pago: {escape(order.get("payment_method") or "Por confirmar")}</p>
        <p>{escape(order.get("guide_url") or "")}</p>
        <p>{escape(order.get("guide_note") or "")}</p>
      </div>
    </section>
    <table>
      <thead><tr><th>Articulo</th><th>Cant.</th><th>Unitario</th><th>Subtotal</th></tr></thead>
      <tbody>{item_rows}</tbody>
    </table>
    <div class="total"><div>{discount_line}<strong>Total {escape(_format_invoice_money(order.get("total_amount"), currency))}</strong></div></div>
    <p><small>Documento generado automaticamente desde CLONEXA ShopLink.</small></p>
    <div class="actions"><button onclick="window.print()">Imprimir / PDF</button></div>
  </main>
</body>
</html>"""


def _shoplink_invoice_pdf(company: dict[str, Any], settings: dict[str, Any], order: dict[str, Any]) -> bytes:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Motor PDF no disponible: {exc}") from exc

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 54
    currency = order.get("currency") or settings.get("currency") or "COP"
    customer = order.get("customer") or {}
    items = order.get("items") or []
    store_name = _clean(settings.get("store_name") or company.get("name") or "Tienda CLONEXA", 120)

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(54, y, "Factura ShopLink")
    pdf.setFont("Helvetica", 11)
    pdf.drawRightString(width - 54, y + 4, _clean(order.get("invoice_code"), 60))
    y -= 24
    pdf.drawString(54, y, store_name)
    pdf.drawRightString(width - 54, y, f"Pedido: {_clean(order.get('order_code'), 60)}")
    y -= 34

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(54, y, "Cliente")
    y -= 16
    pdf.setFont("Helvetica", 10)
    for line in [
        f"Nombre: {_clean(customer.get('name'), 120)}",
        f"Telefono: {_clean(customer.get('phone'), 40)}",
        f"Ciudad: {_clean(customer.get('city'), 120)}",
        f"Direccion: {_clean(customer.get('address'), 220)}",
        f"Pago: {_clean(order.get('payment_method'), 60) or 'Por confirmar'}",
    ]:
        pdf.drawString(54, y, line)
        y -= 14
    y -= 12

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(54, y, "Articulo")
    pdf.drawRightString(370, y, "Cant.")
    pdf.drawRightString(470, y, "Unitario")
    pdf.drawRightString(width - 54, y, "Subtotal")
    y -= 8
    pdf.line(54, y, width - 54, y)
    y -= 16
    pdf.setFont("Helvetica", 10)
    for item in items:
        if y < 100:
            pdf.showPage()
            y = height - 54
            pdf.setFont("Helvetica", 10)
        name = _clean(item.get("name") or "Articulo", 64)
        sku = _clean(item.get("sku"), 32)
        pdf.drawString(54, y, f"{name}{f' / {sku}' if sku else ''}")
        pdf.drawRightString(370, y, str(item.get("qty") or 1))
        pdf.drawRightString(470, y, _format_invoice_money(item.get("unit_price"), currency))
        pdf.drawRightString(width - 54, y, _format_invoice_money(item.get("subtotal"), currency))
        y -= 18
    y -= 8
    pdf.line(54, y, width - 54, y)
    y -= 28
    pdf.setFont("Helvetica-Bold", 16)
    if float(order.get("discount_amount") or 0) > 0:
        pdf.setFont("Helvetica", 11)
        pdf.drawRightString(width - 54, y, f"Descuento {_format_invoice_money(order.get('discount_amount'), currency)}")
        y -= 20
        pdf.setFont("Helvetica-Bold", 16)
    pdf.drawRightString(width - 54, y, f"Total {_format_invoice_money(order.get('total_amount'), currency)}")
    y -= 32
    pdf.setFont("Helvetica", 9)
    pdf.drawString(54, y, "Documento generado automaticamente desde CLONEXA ShopLink.")
    pdf.save()
    return buffer.getvalue()


def _guide_file_content_type(upload: UploadFile) -> str:
    content_type = (upload.content_type or "").strip().lower()
    filename = (upload.filename or "").strip().lower()
    if content_type in ALLOWED_GUIDE_FILE_TYPES:
        return content_type
    if filename.endswith(".pdf"):
        return "application/pdf"
    if filename.endswith(".jpg") or filename.endswith(".jpeg"):
        return "image/jpeg"
    if filename.endswith(".png"):
        return "image/png"
    if filename.endswith(".webp"):
        return "image/webp"
    raise HTTPException(status_code=422, detail="Guia invalida. Usa PDF, JPG, PNG o WEBP.")


async def _read_guide_file_upload(upload: UploadFile) -> dict[str, Any]:
    content_type = _guide_file_content_type(upload)
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=422, detail="Guia vacia.")
    if len(content) > MAX_GUIDE_FILE_BYTES:
        raise HTTPException(status_code=422, detail="La guia supera 8 MB.")
    return {
        "content_type": content_type,
        "content": content,
        "name": _clean(upload.filename or "guia_envio", 180) or "guia_envio",
        "size": len(content),
    }


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
        "whatsapp_web": await whatsapp_status(company["id"]),
        "public_url": _public_url(settings, company["id"]),
    }


@router.get("/companies/{company_id}/whatsapp-web")
async def get_shoplink_whatsapp_web(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    company = await _company(db, company_id)
    return await whatsapp_status(company["id"])


@router.post("/companies/{company_id}/whatsapp-web/start")
async def start_shoplink_whatsapp_web(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    company = await _company(db, company_id)
    return await whatsapp_start(company["id"])


@router.post("/companies/{company_id}/whatsapp-web/logout")
async def logout_shoplink_whatsapp_web(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    company = await _company(db, company_id)
    return await whatsapp_logout(company["id"])


@router.post("/companies/{company_id}/whatsapp-web/test")
async def test_shoplink_whatsapp_web(
    company_id: UUID,
    payload: ShoplinkWhatsAppTestIn | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    phone = _shoplink_whatsapp_phone(settings.get("payment_proof_whatsapp") or settings.get("whatsapp_number"))
    message = _clean((payload.message if payload else "") or "", 700) or "\n".join([
        "Prueba alerta ShopLink",
        f"Tienda: {_clean(settings.get('store_name') or company.get('name'), 120)}",
        "Este numero ya puede recibir alertas automaticas de pedidos nuevos.",
    ])
    return await whatsapp_send(company["id"], phone, message)


@router.get("/companies/{company_id}/customers")
async def get_shoplink_customers(
    company_id: UUID,
    q: str = "",
    status: str = "all",
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    customers = await _shoplink_customer_rows(db, company["id"], limit)
    query = _clean(q, 120).lower()
    if query:
        customers = [
            customer for customer in customers
            if query in " ".join([
                customer.get("name") or "",
                customer.get("phone") or "",
                customer.get("city") or "",
                customer.get("address") or "",
                customer.get("status_label") or "",
                customer.get("tag") or "",
                customer.get("note") or "",
                customer.get("last_order_code") or "",
                customer.get("last_items_summary") or "",
            ]).lower()
        ]
    status_filter = _clean(status, 40).lower()
    if status_filter and status_filter not in {"all", "todos"}:
        wanted = _customer_status(status_filter)
        customers = [customer for customer in customers if _customer_status(customer.get("status")) == wanted]
    active_customers = [customer for customer in customers if _customer_status(customer.get("status")) not in {"archivado", "bloqueado"}]
    summary = {
        "customers": len(customers),
        "active": len(active_customers),
        "with_orders": len([customer for customer in customers if int(customer.get("orders_count") or 0) > 0]),
        "repeat": len([customer for customer in customers if int(customer.get("orders_count") or 0) > 1]),
        "follow_up": len([customer for customer in customers if _customer_status(customer.get("status")) == "seguimiento"]),
        "vip": len([customer for customer in customers if _customer_status(customer.get("status")) == "vip"]),
        "total_sales": sum(float(customer.get("total_amount") or 0) for customer in customers),
        "cities": len({(customer.get("city") or "").strip().lower() for customer in customers if (customer.get("city") or "").strip()}),
    }
    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": company["slug"]},
        "settings": settings,
        "summary": summary,
        "customers": customers,
        "public_url": _public_url(settings, company["id"]),
    }


async def _shoplink_campaigns_payload(
    db: AsyncSession,
    company_id: UUID,
    q: str = "",
    status: str = "all",
    include_archived: bool = False,
) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    products = await _products(db, company["id"])
    orders = [_shoplink_order_out(row, company["id"]) for row in await _shoplink_order_rows(db, company["id"], 1000)]
    all_campaigns = [
        _shoplink_campaign_out(row, settings, products, orders)
        for row in await _shoplink_campaign_rows(db, company["id"], include_archived=True)
    ]
    customers = await _shoplink_customer_rows(db, company["id"], 1000)
    visible_base = all_campaigns if include_archived or _clean(status, 40).lower() in {"archivadas", "archivados", "archived"} else [row for row in all_campaigns if not row.get("archived")]
    campaigns = _filter_shoplink_campaigns(visible_base, q, status)
    summary = _campaign_report_summary(campaigns, all_campaigns, orders, products, customers)
    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": company["slug"]},
        "settings": settings,
        "summary": summary,
        "campaigns": campaigns,
        "products": products,
        "segments": [
            {"value": value, "label": _campaign_segment_label(value)}
            for value in ["todos", "nuevos", "recurrentes", "vip", "seguimiento", "ciudad"]
        ],
        "public_url": _public_url(settings, company["id"]),
    }


@router.get("/companies/{company_id}/campaigns")
async def get_shoplink_campaigns(
    company_id: UUID,
    q: str = "",
    status: str = "all",
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    payload = await _shoplink_campaigns_payload(db, company_id, q, status, include_archived)
    return _json_safe(payload)


@router.get("/companies/{company_id}/campaigns/export.csv")
async def export_shoplink_campaigns(
    company_id: UUID,
    q: str = "",
    status: str = "all",
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
) -> Response:
    payload = await _shoplink_campaigns_payload(db, company_id, q, status, include_archived)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "campana",
        "estado",
        "cupon",
        "productos",
        "pedidos_link",
        "ventas_link",
        "descuentos",
        "ventas_potenciales_producto",
        "landing",
        "actualizado",
    ])
    for row in payload.get("campaigns") or []:
        writer.writerow([
            row.get("title") or "",
            row.get("status_label") or "",
            row.get("coupon_code") or "",
            row.get("products_count") or 0,
            row.get("direct_orders") or 0,
            row.get("direct_sales") or 0,
            row.get("discounts_used") or 0,
            row.get("matched_sales") or 0,
            row.get("landing_url") or "",
            row.get("updated_at") or "",
        ])
    filename = f"shoplink_campanas_{_clean(payload.get('company', {}).get('slug'), 60) or 'reporte'}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/companies/{company_id}/campaigns")
async def create_shoplink_campaign(
    company_id: UUID,
    payload: ShoplinkCampaignIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    products = await _products(db, company["id"])
    row = await _save_shoplink_campaign(db, company["id"], payload)
    return {
        "ok": True,
        "campaign": _shoplink_campaign_out(row, settings, products, []),
    }


@router.patch("/companies/{company_id}/campaigns/{campaign_id}")
async def update_shoplink_campaign(
    company_id: UUID,
    campaign_id: str,
    payload: ShoplinkCampaignIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    products = await _products(db, company["id"])
    row = await _save_shoplink_campaign(db, company["id"], payload, campaign_id)
    orders = [_shoplink_order_out(order, company["id"]) for order in await _shoplink_order_rows(db, company["id"], 1000)]
    return {
        "ok": True,
        "campaign": _shoplink_campaign_out(row, settings, products, orders),
    }


@router.delete("/companies/{company_id}/campaigns/{campaign_id}")
async def archive_shoplink_campaign(
    company_id: UUID,
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    await ensure_shoplink_storage(db)
    result = await db.execute(
        text("""
            UPDATE shoplink_campaigns
            SET archived = true, status = 'archived', updated_at = now()
            WHERE company_id = :company_id
              AND id = :id
            RETURNING id
        """),
        {"company_id": company["id"], "id": _clean(campaign_id, 80)},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Campana no encontrada.")
    await db.commit()
    return {"ok": True}


@router.post("/companies/{company_id}/customers")
async def create_shoplink_customer(
    company_id: UUID,
    payload: ShoplinkCustomerIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    row = await _upsert_shoplink_customer_profile(db, company["id"], "", payload)
    return {
        "ok": True,
        "customer": {
            "customer_key": _clean(row.get("phone_key"), 120),
            "name": _clean(row.get("customer_name"), 120),
            "phone": _clean(row.get("customer_phone"), 40),
            "city": _clean(row.get("customer_city"), 120),
            "address": _clean(row.get("customer_address"), 220),
            **_customer_profile_out(row),
        },
    }


@router.patch("/companies/{company_id}/customers/{customer_key}")
async def update_shoplink_customer(
    company_id: UUID,
    customer_key: str,
    payload: ShoplinkCustomerIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    row = await _upsert_shoplink_customer_profile(db, company["id"], customer_key, payload)
    return {
        "ok": True,
        "customer": {
            "customer_key": _clean(row.get("phone_key"), 120),
            "name": _clean(row.get("customer_name"), 120),
            "phone": _clean(row.get("customer_phone"), 40),
            "city": _clean(row.get("customer_city"), 120),
            "address": _clean(row.get("customer_address"), 220),
            **_customer_profile_out(row),
        },
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


@router.get("/companies/{company_id}/orders/{order_id}/invoice.pdf")
async def get_shoplink_order_invoice_pdf(
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
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", _clean(order.get("invoice_code"), 80)) or "factura_shoplink"
    return Response(
        content=_shoplink_invoice_pdf(company, settings, order),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


@router.post("/companies/{company_id}/orders/{order_id}/guide-file")
async def upload_shoplink_order_guide_file(
    company_id: UUID,
    order_id: str,
    guide_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    await ensure_shoplink_storage(db)
    await _shoplink_order_by_id(db, company["id"], order_id)
    upload = await _read_guide_file_upload(guide_file)
    result = await db.execute(
        text("""
            UPDATE shoplink_orders
            SET guide_file_name = :guide_file_name,
                guide_file_content_type = :guide_file_content_type,
                guide_file_bytes = :guide_file_bytes,
                guide_file_size = :guide_file_size,
                updated_at = now()
            WHERE company_id = :company_id
              AND id = :id
            RETURNING *
        """),
        {
            "company_id": company["id"],
            "id": _clean(order_id, 80),
            "guide_file_name": upload["name"],
            "guide_file_content_type": upload["content_type"],
            "guide_file_bytes": upload["content"],
            "guide_file_size": upload["size"],
        },
    )
    row = result.mappings().first()
    await db.commit()
    return {"ok": True, "order": _shoplink_order_out(dict(row), company["id"])}


@router.get("/companies/{company_id}/orders/{order_id}/guide-file")
async def get_shoplink_order_guide_file(
    company_id: UUID,
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    company = await _company(db, company_id)
    current = await _shoplink_order_by_id(db, company["id"], order_id)
    content = current.get("guide_file_bytes")
    if not content:
        raise HTTPException(status_code=404, detail="Guia no adjunta.")
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", _clean(current.get("guide_file_name"), 180)) or "guia_envio"
    return Response(
        content=content,
        media_type=current.get("guide_file_content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
    settings["payment_proof_whatsapp"] = re.sub(r"[^0-9+]", "", _clean(settings.get("payment_proof_whatsapp"), 40))
    settings["payment_proof_message"] = _clean(settings.get("payment_proof_message"), 220)
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


def _shoplink_public_categories(settings: dict[str, Any], products: list[dict[str, Any]]) -> list[str]:
    configured = [_clean(category, 80) for category in settings.get("categories") or [] if _clean(category, 80)]
    product_categories = sorted({_clean(product.get("category"), 80) for product in products if _clean(product.get("category"), 80)})
    return list(dict.fromkeys([*configured, *product_categories]))


def _shoplink_campaign_featured(campaign: dict[str, Any] | None, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    product_ids = _campaign_product_ids(campaign.get("product_ids")) if campaign else []
    if not product_ids:
        return []
    return [
        product for product in products
        if _campaign_product_match(product.get("id") or product.get("raw_id"), product_ids)
    ]


def _order_payload(payload: ShoplinkOrderIn) -> dict[str, Any]:
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return {
        "name": _clean(data.get("customer_name"), 120),
        "phone": re.sub(r"[^0-9+]", "", _clean(data.get("customer_phone"), 40)),
        "city": _clean(data.get("customer_city"), 120),
        "address": _clean(data.get("customer_address"), 220),
        "note": _clean(data.get("customer_note"), 500),
    }


@router.post("/public/{company_id}/coupons/validate")
async def validate_shoplink_coupon(
    company_id: UUID,
    payload: ShoplinkCouponValidateIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    if not settings.get("public_enabled", True):
        raise HTTPException(status_code=403, detail="Tienda publica desactivada.")
    coupon_code = _clean(payload.coupon_code, 40).upper()
    if not coupon_code:
        raise HTTPException(status_code=400, detail="Escribe un codigo de cupon.")
    products = await _products(db, company["id"])
    catalog = {str(product["id"]): product for product in products}
    items, subtotal = _shoplink_checkout_items(catalog, payload.items)
    if not items:
        raise HTTPException(status_code=400, detail="Agrega productos al carrito antes de aplicar el cupon.")
    campaign_row = await _active_shoplink_campaign_by_coupon(db, company["id"], coupon_code)
    uses = await _shoplink_campaign_uses(db, company["id"], campaign_row.get("slug")) if campaign_row else 0
    quote_out = _campaign_coupon_quote(campaign_row, items, subtotal, coupon_code, uses)
    campaign_out = (
        _shoplink_campaign_out(campaign_row, settings, products, [], include_private=False)
        if campaign_row else None
    )
    return {
        "ok": True,
        **quote_out,
        "coupon_code": coupon_code if quote_out["valid"] else "",
        "subtotal": subtotal,
        "total_amount": max(0.0, subtotal - float(quote_out["discount_amount"] or 0)),
        "campaign": campaign_out,
        "campaign_slug": _clean(campaign_row.get("slug"), 100) if campaign_row and quote_out["valid"] else "",
    }


@router.post("/public/{company_id}/orders")
async def create_shoplink_order(
    company_id: UUID,
    payload: ShoplinkOrderIn,
    request: Request,
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

    products = await _products(db, company["id"])
    catalog = {str(product["id"]): product for product in products}
    items, total = _shoplink_checkout_items(catalog, payload.items)

    if not items:
        raise HTTPException(status_code=400, detail="El pedido no tiene productos disponibles.")

    requested_campaign_slug = _slug(_clean(payload.campaign_slug, 100))
    campaign = await _active_shoplink_campaign_by_slug(db, company["id"], requested_campaign_slug) if requested_campaign_slug else None
    coupon_code = _clean(payload.coupon_code, 40).upper()
    if coupon_code:
        expected_coupon = _clean(campaign.get("coupon_code"), 40).upper() if campaign else ""
        if not campaign or expected_coupon != coupon_code:
            campaign = await _active_shoplink_campaign_by_coupon(db, company["id"], coupon_code)
        uses = await _shoplink_campaign_uses(db, company["id"], campaign.get("slug")) if campaign else 0
        coupon_quote = _campaign_coupon_quote(campaign, items, total, coupon_code, uses)
        if not coupon_quote["valid"]:
            raise HTTPException(status_code=422, detail=coupon_quote["message"])
        discount_amount = float(coupon_quote["discount_amount"] or 0)
    else:
        campaign_uses = await _shoplink_campaign_uses(db, company["id"], campaign.get("slug")) if campaign else 0
        max_uses = max(0, int(campaign.get("max_uses") or 0)) if campaign else 0
        discount_amount = (
            _campaign_discount_amount(campaign, items, total, "")
            if not max_uses or campaign_uses < max_uses else 0.0
        )
    configured_methods = [
        _clean(method, 60)
        for method in (settings.get("payment_methods") or ["Efectivo", "Transferencia", "Tarjeta"])
        if _clean(method, 60)
    ]
    requested_payment = _clean(payload.payment_method, 60)
    payment_method = next(
        (method for method in configured_methods if method.lower() == requested_payment.lower()),
        "",
    )
    if configured_methods and not payment_method:
        raise HTTPException(status_code=400, detail="Selecciona un metodo de pago valido.")
    total_after_discount = max(0.0, total - discount_amount)
    campaign_slug = _clean(campaign.get("slug"), 100) if campaign else ""
    order_id = str(uuid4())
    order_code = f"SL-{uuid4().hex[:8].upper()}"
    invoice_code = _invoice_code_for_order(order_code)
    currency = _clean(settings.get("currency") or "COP", 8).upper() or "COP"
    await ensure_shoplink_storage(db)
    await db.execute(
        text("""
            INSERT INTO shoplink_orders (
              id, company_id, order_code, customer_json, items_json,
              total_amount, currency, status, invoice_code, payment_method, campaign_slug, coupon_code,
              discount_amount, source, invoiced_at, updated_at
            )
            VALUES (
              :id, :company_id, :order_code, CAST(:customer AS jsonb), CAST(:items AS jsonb),
              :total_amount, :currency, 'new', :invoice_code, :payment_method, :campaign_slug, :coupon_code,
              :discount_amount, :source, now(), now()
            )
        """),
        {
            "id": order_id,
            "company_id": company["id"],
            "order_code": order_code,
            "invoice_code": invoice_code,
            "payment_method": payment_method,
            "customer": json.dumps(customer, ensure_ascii=False),
            "items": json.dumps(items, ensure_ascii=False),
            "total_amount": total_after_discount,
            "currency": currency,
            "campaign_slug": campaign_slug,
            "coupon_code": coupon_code if discount_amount > 0 else "",
            "discount_amount": discount_amount,
            "source": f"shoplink_campaign:{campaign_slug}" if campaign_slug else "shoplink_public",
        },
    )
    await db.commit()
    order_out = {
        "ok": True,
        "id": order_id,
        "order_code": order_code,
        "invoice_code": invoice_code,
        "invoice_url": f"/api/v1/shoplink/companies/{company['id']}/orders/{order_id}/invoice",
        "invoice_pdf_url": f"/api/v1/shoplink/companies/{company['id']}/orders/{order_id}/invoice.pdf",
        "customer_name": customer.get("name") or "",
        "customer_phone": customer.get("phone") or "",
        "customer_city": customer.get("city") or "",
        "customer_address": customer.get("address") or "",
        "customer_note": customer.get("note") or "",
        "status": "new",
        "total_amount": total_after_discount,
        "discount_amount": discount_amount,
        "campaign_slug": campaign_slug,
        "coupon_code": coupon_code if discount_amount > 0 else "",
        "payment_method": payment_method,
        "currency": currency,
        "items": items,
    }
    alert = _shoplink_owner_alert(company, settings, order_out, str(request.base_url))
    delivery = await _send_shoplink_owner_alert(company["id"], alert)
    order_out.update({
        "owner_alert_phone": alert.get("phone") or "",
        "owner_alert_message": alert.get("message") or "",
        "owner_alert_url": alert.get("url") or "",
        "owner_alert_delivery": delivery,
    })
    return order_out


@router.get("/public/{company_id}")
async def public_shoplink(
    company_id: UUID,
    campaign: str = "",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await _company(db, company_id)
    settings = await _settings(db, company)
    if not settings.get("public_enabled", True):
        raise HTTPException(status_code=403, detail="Tienda pública desactivada.")
    products = await _products(db, company["id"])
    campaign_row = await _active_shoplink_campaign_by_slug(db, company["id"], campaign) if campaign else None
    campaign_out = _shoplink_campaign_out(campaign_row, settings, products, [], include_private=False) if campaign_row else None
    categories = _shoplink_public_categories(settings, products)
    campaign_featured = _shoplink_campaign_featured(campaign_row, products)
    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": company["slug"]},
        "settings": settings,
        "public_url": _public_url(settings, company["id"]),
        "campaign": campaign_out,
        "categories": categories,
        "products": products,
        "featured": (campaign_featured or products[:8]) if campaign_out else _featured_products(products, settings),
    }
