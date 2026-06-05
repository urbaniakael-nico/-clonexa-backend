
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else default
    except Exception:
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value or 0)
        return parsed if parsed >= 0 else default
    except Exception:
        return default


def to_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value

    raw = clean(value).lower()

    if raw in {"true", "1", "yes", "si", "sí", "active", "activo"}:
        return True

    if raw in {"false", "0", "no", "inactive", "inactivo"}:
        return False

    return default


def normalize_reference_channel(value: Any, bot_active: Any = None, system_active: Any = None) -> str:
    raw = clean(value).lower().replace("-", "_").replace(" ", "_")
    if raw in {"bot", "bots", "telegram", "whatsapp"}:
        return "bot"
    if raw in {"system", "sistema", "panel", "paneles", "minipanel", "mini_panel", "mini-panel", "app"}:
        return "system"
    if raw in {"both", "ambos", "bot_system", "bot_sistema", "all", "todos"}:
        return "both"
    if bot_active is not None:
        bot = to_bool(bot_active, False)
        system = to_bool(system_active, False) if system_active is not None else False
        if bot and system:
            return "both"
        if system and not bot:
            return "system"
        if bot:
            return "bot"
    return "bot"


def reference_channel_flags(channel: str) -> tuple[bool, bool]:
    normalized = normalize_reference_channel(channel)
    if normalized == "system":
        return False, True
    if normalized == "both":
        return True, True
    return True, False


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name})
    return bool(result.scalar())


async def columns(db: AsyncSession, table_name: str) -> set[str]:
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


async def ensure_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS product_references (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            name text NOT NULL,
            size text NOT NULL,
            initial_quantity integer NOT NULL DEFAULT 0,
            activation_date timestamptz NULL,
            bot_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS category text NOT NULL DEFAULT ''
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS color text NOT NULL DEFAULT ''
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS sku text NOT NULL DEFAULT ''
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS unit_price numeric(14, 2) NOT NULL DEFAULT 0
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS archived boolean NOT NULL DEFAULT false
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS channel text NOT NULL DEFAULT 'bot'
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS system_active boolean NOT NULL DEFAULT false
    """))

    await db.execute(text("""
        DROP INDEX IF EXISTS ux_product_references_company_name_size
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_product_references_company_category
        ON product_references (company_id, lower(category), lower(name), lower(size), lower(color))
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_product_references_company_channel
        ON product_references (company_id, channel)
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_product_references_company_sku
        ON product_references (company_id, lower(COALESCE(sku, '')))
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_product_references_company_created
        ON product_references (company_id, created_at DESC)
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_product_references_company_bot
        ON product_references (company_id, bot_active)
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_cycle_resets (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            reference_id text NOT NULL,
            reference_name text NOT NULL,
            size text NOT NULL,
            previous_initial_quantity integer NOT NULL DEFAULT 0,
            previous_finished_quantity integer NOT NULL DEFAULT 0,
            historical_finished_quantity integer NOT NULL DEFAULT 0,
            new_initial_quantity integer NOT NULL DEFAULT 0,
            reset_at timestamptz NOT NULL DEFAULT now(),
            source text NOT NULL DEFAULT 'client_panel',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_reference_cycle_resets_company_ref
        ON reference_cycle_resets (company_id, reference_id, reset_at DESC)
    """))

    await db.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_product_references_company_category_name_size_color
        ON product_references (
            company_id,
            lower(COALESCE(category, '')),
            lower(name),
            lower(size),
            lower(COALESCE(color, ''))
        )
    """))

    await db.commit()


async def references_module_active(db: AsyncSession, company_id: str) -> bool:
    try:
        if await table_exists(db, "company_modules") and await table_exists(db, "modules"):
            cm_cols = await columns(db, "company_modules")
            m_cols = await columns(db, "modules")

            if "module_id" in cm_cols and "id" in m_cols and "code" in m_cols:
                enabled_expr = "COALESCE(cm.enabled, true) IS TRUE" if "enabled" in cm_cols else "true"

                result = await db.execute(
                    text(f"""
                        SELECT 1
                        FROM company_modules cm
                        JOIN modules m ON m.id = cm.module_id
                        WHERE cm.company_id::text = :company_id
                          AND m.code = 'references'
                          AND {enabled_expr}
                        LIMIT 1
                    """),
                    {"company_id": company_id},
                )

                return bool(result.scalar())

        if await table_exists(db, "company_modules"):
            cm_cols = await columns(db, "company_modules")

            if "module_code" in cm_cols:
                enabled_expr = "COALESCE(enabled, true) IS TRUE" if "enabled" in cm_cols else "true"

                result = await db.execute(
                    text(f"""
                        SELECT 1
                        FROM company_modules
                        WHERE company_id::text = :company_id
                          AND module_code = 'references'
                          AND {enabled_expr}
                        LIMIT 1
                    """),
                    {"company_id": company_id},
                )

                return bool(result.scalar())

    except Exception:
        await db.rollback()
        return False

    return True


async def require_references_module(db: AsyncSession, company_id: str) -> None:
    active = await references_module_active(db, company_id)

    if not active:
        raise HTTPException(status_code=403, detail="El módulo references no está activo para esta empresa.")


def row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)

    for key in ["created_at", "updated_at", "activation_date"]:
        if data.get(key) is not None:
            data[key] = str(data[key])

    return data


@router.get("/companies/{company_id}")
async def list_references(
    company_id: str,
    q: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    bot_active: str | None = Query(None),
    channel: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)
    await require_references_module(db, company_id)

    where = ["company_id = :company_id", "COALESCE(archived, false) IS NOT TRUE"]
    params: dict[str, Any] = {"company_id": company_id}

    search = clean(q)
    if search:
        where.append("(lower(name) LIKE :search OR lower(size) LIKE :search OR lower(COALESCE(category, '')) LIKE :search OR lower(COALESCE(color, '')) LIKE :search OR lower(COALESCE(sku, '')) LIKE :search OR lower(COALESCE(channel, '')) LIKE :search)")
        params["search"] = f"%{search.lower()}%"

    if clean(date_from):
        where.append("created_at::date >= CAST(:date_from AS date)")
        params["date_from"] = clean(date_from)

    if clean(date_to):
        where.append("created_at::date <= CAST(:date_to AS date)")
        params["date_to"] = clean(date_to)

    if bot_active is not None and clean(bot_active) != "":
        where.append("bot_active = :bot_active")
        params["bot_active"] = to_bool(bot_active)

    channel_value = clean(channel).lower()
    if channel_value:
        normalized_channel = normalize_reference_channel(channel_value)
        if normalized_channel == "system":
            where.append("system_active IS TRUE")
        elif normalized_channel == "bot":
            where.append("bot_active IS TRUE")
        elif normalized_channel == "both":
            where.append("bot_active IS TRUE AND system_active IS TRUE")

    result = await db.execute(
        text(f"""
            SELECT
                id,
                company_id,
                name,
                COALESCE(category, '') AS category,
                size,
                COALESCE(color, '') AS color,
                COALESCE(sku, '') AS sku,
                COALESCE(unit_price, 0)::float AS unit_price,
                COALESCE(archived, false) AS archived,
                initial_quantity,
                activation_date,
                bot_active,
                COALESCE(system_active, false) AS system_active,
                COALESCE(NULLIF(channel, ''), CASE WHEN bot_active IS TRUE THEN 'bot' ELSE 'system' END) AS channel,
                created_at,
                updated_at
            FROM product_references
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC, name ASC, size ASC
            LIMIT 2000
        """),
        params,
    )

    rows = [row_to_dict(row) for row in result.mappings().all()]

    return {
        "company_id": company_id,
        "count": len(rows),
        "items": rows,
    }


@router.post("/companies/{company_id}")
async def create_reference(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)
    await require_references_module(db, company_id)

    name = clean(payload.get("name"))
    category = clean(payload.get("category"))
    size = clean(payload.get("size"))
    color = clean(payload.get("color"))
    sku = clean(payload.get("sku") or payload.get("code") or payload.get("barcode"))
    unit_price = to_float(payload.get("unit_price") if "unit_price" in payload else payload.get("price"), 0.0)
    initial_quantity = to_int(payload.get("initial_quantity"), 0)
    channel = normalize_reference_channel(payload.get("channel"), payload.get("bot_active"), payload.get("system_active"))
    bot_active, system_active = reference_channel_flags(channel)

    if not name:
        raise HTTPException(status_code=422, detail="Nombre de referencia requerido.")

    if not size:
        raise HTTPException(status_code=422, detail="Talla requerida.")

    duplicate = await db.execute(
        text("""
            SELECT id
            FROM product_references
            WHERE company_id = :company_id
              AND lower(name) = lower(:name)
              AND lower(COALESCE(category, '')) = lower(:category)
              AND lower(size) = lower(:size)
              AND lower(COALESCE(color, '')) = lower(:color)
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "name": name,
            "category": category,
            "size": size,
            "color": color,
        },
    )

    if duplicate.scalar():
        raise HTTPException(status_code=409, detail="Ya existe una referencia con ese nombre, categoría, talla y color.")

    reference_id = str(uuid4())

    try:
        await db.execute(
            text("""
                INSERT INTO product_references (
                    id,
                    company_id,
                    name,
                    category,
                    size,
                    color,
                    sku,
                    unit_price,
                    initial_quantity,
                    activation_date,
                    bot_active,
                    system_active,
                    channel,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :name,
                    :category,
                    :size,
                    :color,
                    :sku,
                    :unit_price,
                    :initial_quantity,
                    CASE WHEN :initial_quantity > 0 THEN now() ELSE NULL END,
                    :bot_active,
                    :system_active,
                    :channel,
                    now(),
                    now()
                )
            """),
            {
                "id": reference_id,
                "company_id": company_id,
                "name": name,
                "category": category,
                "size": size,
                "color": color,
                "sku": sku,
                "unit_price": unit_price,
                "initial_quantity": initial_quantity,
                "bot_active": bot_active,
                "system_active": system_active,
                "channel": channel,
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"create_reference_failed: {type(exc).__name__}: {exc}")

    return {
        "id": reference_id,
        "company_id": company_id,
        "name": name,
        "category": category,
        "size": size,
        "color": color,
        "sku": sku,
        "unit_price": unit_price,
        "initial_quantity": initial_quantity,
        "bot_active": bot_active,
        "system_active": system_active,
        "channel": channel,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


@router.patch("/companies/{company_id}/{reference_id}")
async def update_reference(
    company_id: str,
    reference_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)
    await require_references_module(db, company_id)

    existing = await db.execute(
        text("""
            SELECT *
            FROM product_references
            WHERE company_id = :company_id
              AND id = :reference_id
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
        },
    )

    current = existing.mappings().first()

    if not current:
        raise HTTPException(status_code=404, detail="Referencia no encontrada.")

    name = clean(payload.get("name")) if "name" in payload else clean(current["name"])
    category = clean(payload.get("category")) if "category" in payload else clean(current.get("category"))
    size = clean(payload.get("size")) if "size" in payload else clean(current["size"])
    color = clean(payload.get("color")) if "color" in payload else clean(current.get("color"))
    sku = clean(payload.get("sku") or payload.get("code") or payload.get("barcode")) if ("sku" in payload or "code" in payload or "barcode" in payload) else clean(current.get("sku"))
    unit_price = to_float(payload.get("unit_price") if "unit_price" in payload else payload.get("price"), float(current.get("unit_price") or 0)) if ("unit_price" in payload or "price" in payload) else float(current.get("unit_price") or 0)
    initial_quantity = to_int(payload.get("initial_quantity"), int(current["initial_quantity"] or 0)) if "initial_quantity" in payload else int(current["initial_quantity"] or 0)

    current_channel = current.get("channel") or ("bot" if current.get("bot_active") else "system")
    channel = normalize_reference_channel(payload.get("channel", current_channel), payload.get("bot_active"), payload.get("system_active"))
    bot_active, system_active = reference_channel_flags(channel)

    if not name:
        raise HTTPException(status_code=422, detail="Nombre de referencia requerido.")

    if not size:
        raise HTTPException(status_code=422, detail="Talla requerida.")

    duplicate = await db.execute(
        text("""
            SELECT id
            FROM product_references
            WHERE company_id = :company_id
              AND lower(name) = lower(:name)
              AND lower(COALESCE(category, '')) = lower(:category)
              AND lower(size) = lower(:size)
              AND lower(COALESCE(color, '')) = lower(:color)
              AND id <> :reference_id
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
            "name": name,
            "category": category,
            "size": size,
            "color": color,
        },
    )

    if duplicate.scalar():
        raise HTTPException(status_code=409, detail="Ya existe otra referencia con ese nombre, categoría, talla y color.")

    try:
        await db.execute(
            text("""
                UPDATE product_references
                SET
                    name = :name,
                    category = :category,
                    size = :size,
                    color = :color,
                    sku = :sku,
                    unit_price = :unit_price,
                    initial_quantity = :initial_quantity,
                    activation_date = CASE
                        WHEN activation_date IS NULL AND :initial_quantity > 0 THEN now()
                        ELSE activation_date
                    END,
                    bot_active = :bot_active,
                    system_active = :system_active,
                    channel = :channel,
                    updated_at = now()
                WHERE company_id = :company_id
                  AND id = :reference_id
            """),
            {
                "company_id": company_id,
                "reference_id": reference_id,
                "name": name,
                "category": category,
                "size": size,
                "color": color,
                "sku": sku,
                "unit_price": unit_price,
                "initial_quantity": initial_quantity,
                "bot_active": bot_active,
                "system_active": system_active,
                "channel": channel,
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"update_reference_failed: {type(exc).__name__}: {exc}")

    return {
        "id": reference_id,
        "company_id": company_id,
        "name": name,
        "category": category,
        "size": size,
        "color": color,
        "sku": sku,
        "unit_price": unit_price,
        "initial_quantity": initial_quantity,
        "bot_active": bot_active,
        "system_active": system_active,
        "channel": channel,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.post("/companies/{company_id}/{reference_id}/reset")
async def reset_reference_cycle(
    company_id: str,
    reference_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)
    await require_references_module(db, company_id)

    existing = await db.execute(
        text("""
            SELECT *
            FROM product_references
            WHERE company_id = :company_id
              AND id = :reference_id
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
        },
    )

    current = existing.mappings().first()

    if not current:
        raise HTTPException(status_code=404, detail="Referencia no encontrada.")

    new_initial = to_int(
        payload.get("initial_quantity") if "initial_quantity" in payload else payload.get("new_initial_quantity"),
        int(current["initial_quantity"] or 0),
    )

    counts: dict[str, Any] = {"current_finished": 0, "historical_finished": 0}

    if await table_exists(db, "reference_production_closures"):
        counts_result = await db.execute(
            text("""
                SELECT
                    COALESCE(sum(quantity_finished) FILTER (
                        WHERE :activation_date IS NULL OR closed_at >= :activation_date
                    ), 0) AS current_finished,
                    COALESCE(sum(quantity_finished), 0) AS historical_finished
                FROM reference_production_closures
                WHERE company_id::text = :company_id
                  AND (
                    (COALESCE(reference_id, '') <> '' AND reference_id = :reference_id)
                    OR (
                        COALESCE(reference_id, '') = ''
                        AND lower(COALESCE(reference_name, '')) = lower(:reference_name)
                        AND lower(COALESCE(size, '')) = lower(:size)
                    )
                  )
            """),
            {
                "company_id": company_id,
                "reference_id": reference_id,
                "reference_name": clean(current.get("name")),
                "size": clean(current.get("size")),
                "activation_date": current.get("activation_date"),
            },
        )
        counts = dict(counts_result.mappings().first() or counts)

    try:
        reset_id = str(uuid4())
        await db.execute(
            text("""
                INSERT INTO reference_cycle_resets (
                    id,
                    company_id,
                    reference_id,
                    reference_name,
                    size,
                    previous_initial_quantity,
                    previous_finished_quantity,
                    historical_finished_quantity,
                    new_initial_quantity,
                    reset_at,
                    source,
                    created_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :reference_id,
                    :reference_name,
                    :size,
                    :previous_initial_quantity,
                    :previous_finished_quantity,
                    :historical_finished_quantity,
                    :new_initial_quantity,
                    now(),
                    :source,
                    now()
                )
            """),
            {
                "id": reset_id,
                "company_id": company_id,
                "reference_id": reference_id,
                "reference_name": clean(current.get("name")),
                "size": clean(current.get("size")),
                "previous_initial_quantity": int(current["initial_quantity"] or 0),
                "previous_finished_quantity": int(counts.get("current_finished") or 0),
                "historical_finished_quantity": int(counts.get("historical_finished") or 0),
                "new_initial_quantity": new_initial,
                "source": clean(payload.get("source")) or "client_panel",
            },
        )

        result = await db.execute(
            text("""
                UPDATE product_references
                SET
                    initial_quantity = :initial_quantity,
                    activation_date = now(),
                    updated_at = now()
                WHERE company_id = :company_id
                  AND id = :reference_id
                RETURNING *
            """),
            {
                "company_id": company_id,
                "reference_id": reference_id,
                "initial_quantity": new_initial,
            },
        )

        row = result.mappings().first()
        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"reset_reference_cycle_failed: {type(exc).__name__}: {exc}")

    return {
        "ok": True,
        "action": "reference_cycle_reset",
        "reset_id": reset_id,
        "reference": row_to_dict(row),
        "previous_initial_quantity": int(current["initial_quantity"] or 0),
        "previous_finished_quantity": int(counts.get("current_finished") or 0),
        "historical_finished_quantity": int(counts.get("historical_finished") or 0),
        "new_initial_quantity": new_initial,
        "message": "Ciclo reiniciado. El historial anterior se conserva y el conteo activo empieza desde cero.",
    }


@router.delete("/companies/{company_id}/{reference_id}")
async def delete_reference(
    company_id: str,
    reference_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)
    await require_references_module(db, company_id)

    try:
        result = await db.execute(
            text("""
                UPDATE product_references
                SET archived = true, updated_at = now()
                WHERE company_id = :company_id
                  AND id = :reference_id
            """),
            {
                "company_id": company_id,
                "reference_id": reference_id,
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"delete_reference_failed: {type(exc).__name__}: {exc}")

    return {
        "deleted": True,
        "id": reference_id,
        "rows": result.rowcount,
    }


@router.get("/companies/{company_id}/bot-options")
async def bot_reference_options(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    if not await references_module_active(db, company_id):
        return {
            "company_id": company_id,
            "count": 0,
            "items": [],
        }

    result = await db.execute(
        text("""
            SELECT
                min(id) AS id,
                name,
                count(*) AS sizes_count,
                sum(initial_quantity) AS initial_quantity_total
            FROM product_references
            WHERE company_id = :company_id
              AND bot_active IS TRUE
            GROUP BY name
            ORDER BY name ASC
        """),
        {"company_id": company_id},
    )

    items = [
        {
            "id": clean(row["id"]),
            "name": clean(row["name"]),
            "sizes_count": int(row["sizes_count"] or 0),
            "initial_quantity_total": int(row["initial_quantity_total"] or 0),
        }
        for row in result.mappings().all()
    ]

    return {
        "company_id": company_id,
        "count": len(items),
        "items": items,
    }


@router.get("/companies/{company_id}/sizes")
async def bot_reference_sizes(
    company_id: str,
    name: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    if not await references_module_active(db, company_id):
        return {
            "company_id": company_id,
            "name": clean(name),
            "count": 0,
            "items": [],
        }

    result = await db.execute(
        text("""
            SELECT
                id,
                COALESCE(category, '') AS category,
                size,
                COALESCE(color, '') AS color,
                COALESCE(sku, '') AS sku,
                COALESCE(unit_price, 0)::float AS unit_price,
                COALESCE(archived, false) AS archived,
                initial_quantity,
                bot_active
            FROM product_references
            WHERE company_id = :company_id
              AND lower(name) = lower(:name)
              AND bot_active IS TRUE
            ORDER BY size ASC
        """),
        {
            "company_id": company_id,
            "name": clean(name),
        },
    )

    items = [
        {
            "id": clean(row["id"]),
            "category": clean(row["category"]),
            "size": clean(row["size"]),
            "color": clean(row["color"]),
            "initial_quantity": int(row["initial_quantity"] or 0),
            "bot_active": bool(row["bot_active"]),
        }
        for row in result.mappings().all()
    ]

    return {
        "company_id": company_id,
        "name": clean(name),
        "count": len(items),
        "items": items,
    }


@router.get("/companies/{company_id}/summary")
async def references_summary(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)
    await require_references_module(db, company_id)

    refs_result = await db.execute(
        text("""
            SELECT
                id,
                name,
                COALESCE(category, '') AS category,
                size,
                COALESCE(color, '') AS color,
                COALESCE(sku, '') AS sku,
                COALESCE(unit_price, 0)::float AS unit_price,
                COALESCE(archived, false) AS archived,
                initial_quantity,
                activation_date,
                bot_active,
                COALESCE(system_active, false) AS system_active,
                COALESCE(NULLIF(channel, ''), CASE WHEN bot_active IS TRUE THEN 'bot' ELSE 'system' END) AS channel,
                created_at,
                updated_at
            FROM product_references
            WHERE company_id = :company_id
            ORDER BY name ASC, size ASC
        """),
        {"company_id": company_id},
    )

    refs = [row_to_dict(row) for row in refs_result.mappings().all()]

    finished_map: dict[str, int] = {}
    historical_finished_map: dict[str, int] = {}

    if await table_exists(db, "reference_production_closures"):
        try:
            closure_cols = await columns(db, "reference_production_closures")

            if {"company_id", "reference_name", "size", "quantity_finished"}.issubset(closure_cols):
                prod_result = await db.execute(
                    text("""
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
                    """),
                    {"company_id": company_id},
                )

                for row in prod_result.mappings().all():
                    key = clean(row["reference_id"])
                    finished_map[key] = int(row["finished"] or 0)
                    historical_finished_map[key] = int(row["historical_finished"] or 0)

        except Exception:
            await db.rollback()

    by_reference_size = []
    initial_total = 0
    finished_total = 0
    bot_active_count = 0

    for ref in refs:
        initial = int(ref.get("initial_quantity") or 0)
        key = clean(ref.get("id"))
        finished = int(finished_map.get(key, 0))
        historical_finished = int(historical_finished_map.get(key, finished))
        pending = max(initial - finished, 0)

        initial_total += initial
        finished_total += finished

        if ref.get("bot_active"):
            bot_active_count += 1

        by_reference_size.append({
            "id": ref.get("id"),
            "name": ref.get("name"),
            "category": ref.get("category") or "",
            "size": ref.get("size"),
            "color": ref.get("color") or "",
            "initial_quantity": initial,
            "finished_quantity": finished,
            "historical_finished_quantity": historical_finished,
            "pending_quantity": pending,
            "progress_percent": round((finished / initial) * 100, 2) if initial > 0 else 0,
            "bot_active": bool(ref.get("bot_active")),
            "system_active": bool(ref.get("system_active")),
            "channel": ref.get("channel") or ("bot" if ref.get("bot_active") else "system"),
            "activation_date": ref.get("activation_date"),
        })

    pending_total = max(initial_total - finished_total, 0)

    return {
        "company_id": company_id,
        "references_total": len(refs),
        "bot_active_total": bot_active_count,
        "initial_quantity_total": initial_total,
        "finished_quantity_total": finished_total,
        "pending_quantity_total": pending_total,
        "progress_percent": round((finished_total / initial_total) * 100, 2) if initial_total > 0 else 0,
        "by_reference_size": by_reference_size,
    }


@router.get("/companies/{company_id}/export.csv")
async def export_references_csv(
    company_id: str,
    q: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    bot_active: str | None = Query(None),
    channel: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    data = await list_references(
        company_id=company_id,
        q=q,
        date_from=date_from,
        date_to=date_to,
        bot_active=bot_active,
        channel=channel,
        db=db,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "id",
        "company_id",
        "name",
        "category",
        "size",
        "color",
        "sku",
        "unit_price",
        "initial_quantity",
        "activation_date",
        "bot_active",
        "system_active",
        "channel",
        "created_at",
        "updated_at",
    ])

    for item in data["items"]:
        writer.writerow([
            item.get("id"),
            item.get("company_id"),
            item.get("name"),
            item.get("category"),
            item.get("size"),
            item.get("color"),
            item.get("sku"),
            item.get("unit_price"),
            item.get("initial_quantity"),
            item.get("activation_date"),
            item.get("bot_active"),
            item.get("system_active"),
            item.get("channel"),
            item.get("created_at"),
            item.get("updated_at"),
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="clonexa_references_{company_id}.csv"'
        },
    )


# CLONEXA REF_03A_REFERENCES_FLOW_ENGINE_SAFE
async def ensure_reference_flow_storage(db: AsyncSession) -> None:
    await ensure_storage(db)

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_work_sessions (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
            reference_id text NULL,
            reference_name text NOT NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz NULL,
            duration_minutes numeric NOT NULL DEFAULT 0,
            status text NOT NULL DEFAULT 'active',
            source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_reference_work_sessions_company_employee_status
        ON reference_work_sessions (company_id, employee_id, status)
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_production_closures (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
            reference_id text NULL,
            reference_name text NOT NULL,
            size text NOT NULL,
            quantity_finished integer NOT NULL DEFAULT 0,
            notes text NULL,
            closed_at timestamptz NOT NULL DEFAULT now(),
            source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_reference_production_closures_company_ref_size
        ON reference_production_closures (company_id, reference_name, size)
    """))

    await db.commit()


async def _reference_lookup(
    db: AsyncSession,
    *,
    company_id: str,
    reference_id: str | None = None,
    name: str | None = None,
    size: str | None = None,
) -> dict[str, Any] | None:
    await ensure_reference_flow_storage(db)

    params: dict[str, Any] = {"company_id": company_id}
    where = ["company_id = :company_id", "bot_active IS TRUE"]

    if clean(reference_id):
        where.append("id = :reference_id")
        params["reference_id"] = clean(reference_id)

    if clean(name):
        where.append("lower(name) = lower(:name)")
        params["name"] = clean(name)

    if clean(size):
        where.append("lower(size) = lower(:size)")
        params["size"] = clean(size)

    result = await db.execute(
        text(f"""
            SELECT id, company_id, name, size, initial_quantity, bot_active
            FROM product_references
            WHERE {" AND ".join(where)}
            ORDER BY name ASC, size ASC
            LIMIT 1
        """),
        params,
    )

    row = result.mappings().first()
    return dict(row) if row else None


async def _close_active_reference_session_sql(
    db: AsyncSession,
    *,
    company_id: str,
    employee_id: str,
    status: str,
) -> int:
    result = await db.execute(
        text("""
            UPDATE reference_work_sessions
            SET
                ended_at = now(),
                duration_minutes = GREATEST(EXTRACT(EPOCH FROM (now() - started_at)) / 60.0, 0),
                status = :status,
                updated_at = now()
            WHERE company_id = :company_id
              AND employee_id = :employee_id
              AND status = 'active'
        """),
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "status": status,
        },
    )
    return int(result.rowcount or 0)


@router.post("/companies/{company_id}/flow/start-reference")
async def flow_start_reference(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_reference_flow_storage(db)
    await require_references_module(db, company_id)

    employee_id = clean(payload.get("employee_id"))
    employee_name = clean(payload.get("employee_name"))
    telegram_user_id = clean(payload.get("telegram_user_id"))
    reference_id = clean(payload.get("reference_id"))
    reference_name = clean(payload.get("reference_name") or payload.get("name"))

    if not employee_id:
        raise HTTPException(status_code=422, detail="employee_id requerido.")

    ref = await _reference_lookup(
        db,
        company_id=company_id,
        reference_id=reference_id,
        name=reference_name,
    )

    if not ref:
        raise HTTPException(status_code=404, detail="Referencia activa para bot no encontrada.")

    session_id = str(uuid4())

    try:
        closed_previous = await _close_active_reference_session_sql(
            db,
            company_id=company_id,
            employee_id=employee_id,
            status="closed_by_new_start",
        )

        await db.execute(
            text("""
                INSERT INTO reference_work_sessions (
                    id,
                    company_id,
                    employee_id,
                    employee_name,
                    telegram_user_id,
                    reference_id,
                    reference_name,
                    started_at,
                    status,
                    source_channel,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :telegram_user_id,
                    :reference_id,
                    :reference_name,
                    now(),
                    'active',
                    'telegram',
                    now(),
                    now()
                )
            """),
            {
                "id": session_id,
                "company_id": company_id,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "telegram_user_id": telegram_user_id,
                "reference_id": clean(ref.get("id")),
                "reference_name": clean(ref.get("name")),
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"flow_start_reference_failed: {type(exc).__name__}: {exc}")

    return {
        "ok": True,
        "action": "reference_session_started",
        "session_id": session_id,
        "closed_previous": closed_previous,
        "company_id": company_id,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "telegram_user_id": telegram_user_id,
        "reference_id": clean(ref.get("id")),
        "reference_name": clean(ref.get("name")),
    }


@router.post("/companies/{company_id}/flow/switch-reference")
async def flow_switch_reference(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_reference_flow_storage(db)
    await require_references_module(db, company_id)

    employee_id = clean(payload.get("employee_id"))
    employee_name = clean(payload.get("employee_name"))
    telegram_user_id = clean(payload.get("telegram_user_id"))
    reference_id = clean(payload.get("reference_id"))
    reference_name = clean(payload.get("reference_name") or payload.get("name"))

    if not employee_id:
        raise HTTPException(status_code=422, detail="employee_id requerido.")

    ref = await _reference_lookup(
        db,
        company_id=company_id,
        reference_id=reference_id,
        name=reference_name,
    )

    if not ref:
        raise HTTPException(status_code=404, detail="Referencia activa para bot no encontrada.")

    session_id = str(uuid4())

    try:
        closed_previous = await _close_active_reference_session_sql(
            db,
            company_id=company_id,
            employee_id=employee_id,
            status="switched",
        )

        await db.execute(
            text("""
                INSERT INTO reference_work_sessions (
                    id,
                    company_id,
                    employee_id,
                    employee_name,
                    telegram_user_id,
                    reference_id,
                    reference_name,
                    started_at,
                    status,
                    source_channel,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :telegram_user_id,
                    :reference_id,
                    :reference_name,
                    now(),
                    'active',
                    'telegram',
                    now(),
                    now()
                )
            """),
            {
                "id": session_id,
                "company_id": company_id,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "telegram_user_id": telegram_user_id,
                "reference_id": clean(ref.get("id")),
                "reference_name": clean(ref.get("name")),
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"flow_switch_reference_failed: {type(exc).__name__}: {exc}")

    return {
        "ok": True,
        "action": "reference_session_switched",
        "session_id": session_id,
        "closed_previous": closed_previous,
        "company_id": company_id,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "telegram_user_id": telegram_user_id,
        "reference_id": clean(ref.get("id")),
        "reference_name": clean(ref.get("name")),
    }


@router.post("/companies/{company_id}/flow/close-production")
async def flow_close_production(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_reference_flow_storage(db)
    await require_references_module(db, company_id)

    employee_id = clean(payload.get("employee_id"))
    employee_name = clean(payload.get("employee_name"))
    telegram_user_id = clean(payload.get("telegram_user_id"))
    reference_id = clean(payload.get("reference_id"))
    reference_name = clean(payload.get("reference_name") or payload.get("name"))
    size = clean(payload.get("size"))
    notes = clean(payload.get("notes"))
    quantity_finished = to_int(payload.get("quantity_finished"), 0)

    if not employee_id:
        raise HTTPException(status_code=422, detail="employee_id requerido.")

    if not size and not reference_id:
        raise HTTPException(status_code=422, detail="size requerido si no se envía reference_id.")

    ref = await _reference_lookup(
        db,
        company_id=company_id,
        reference_id=reference_id,
        name=reference_name,
        size=size,
    )

    if not ref:
        raise HTTPException(status_code=404, detail="Referencia/talla activa para bot no encontrada.")

    closure_id = str(uuid4())

    try:
        await db.execute(
            text("""
                INSERT INTO reference_production_closures (
                    id,
                    company_id,
                    employee_id,
                    employee_name,
                    telegram_user_id,
                    reference_id,
                    reference_name,
                    size,
                    quantity_finished,
                    notes,
                    closed_at,
                    source_channel,
                    created_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :telegram_user_id,
                    :reference_id,
                    :reference_name,
                    :size,
                    :quantity_finished,
                    :notes,
                    now(),
                    'telegram',
                    now()
                )
            """),
            {
                "id": closure_id,
                "company_id": company_id,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "telegram_user_id": telegram_user_id,
                "reference_id": clean(ref.get("id")),
                "reference_name": clean(ref.get("name")),
                "size": clean(ref.get("size")),
                "quantity_finished": quantity_finished,
                "notes": notes,
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"flow_close_production_failed: {type(exc).__name__}: {exc}")

    return {
        "ok": True,
        "action": "reference_production_closed",
        "closure_id": closure_id,
        "company_id": company_id,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "telegram_user_id": telegram_user_id,
        "reference_id": clean(ref.get("id")),
        "reference_name": clean(ref.get("name")),
        "size": clean(ref.get("size")),
        "quantity_finished": quantity_finished,
    }


@router.get("/companies/{company_id}/flow/active-session")
async def flow_active_reference_session(
    company_id: str,
    employee_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_reference_flow_storage(db)
    await require_references_module(db, company_id)

    result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                employee_id,
                employee_name,
                telegram_user_id,
                reference_id,
                reference_name,
                started_at::text AS started_at,
                ended_at::text AS ended_at,
                duration_minutes,
                status,
                source_channel,
                created_at::text AS created_at,
                updated_at::text AS updated_at
            FROM reference_work_sessions
            WHERE company_id = :company_id
              AND employee_id = :employee_id
              AND status = 'active'
            ORDER BY started_at DESC
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "employee_id": clean(employee_id),
        },
    )

    row = result.mappings().first()

    return {
        "company_id": company_id,
        "employee_id": clean(employee_id),
        "active": bool(row),
        "session": dict(row) if row else None,
    }

