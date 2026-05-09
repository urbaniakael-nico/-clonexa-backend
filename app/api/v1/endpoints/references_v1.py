
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


def to_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value

    raw = clean(value).lower()

    if raw in {"true", "1", "yes", "si", "sí", "active", "activo"}:
        return True

    if raw in {"false", "0", "no", "inactive", "inactivo"}:
        return False

    return default


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
        CREATE INDEX IF NOT EXISTS ix_product_references_company_created
        ON product_references (company_id, created_at DESC)
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_product_references_company_bot
        ON product_references (company_id, bot_active)
    """))

    await db.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_product_references_company_name_size
        ON product_references (company_id, lower(name), lower(size))
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)
    await require_references_module(db, company_id)

    where = ["company_id = :company_id"]
    params: dict[str, Any] = {"company_id": company_id}

    search = clean(q)
    if search:
        where.append("(lower(name) LIKE :search OR lower(size) LIKE :search)")
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

    result = await db.execute(
        text(f"""
            SELECT
                id,
                company_id,
                name,
                size,
                initial_quantity,
                activation_date,
                bot_active,
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
    size = clean(payload.get("size"))
    initial_quantity = to_int(payload.get("initial_quantity"), 0)
    bot_active = to_bool(payload.get("bot_active"), True)

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
              AND lower(size) = lower(:size)
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "name": name,
            "size": size,
        },
    )

    if duplicate.scalar():
        raise HTTPException(status_code=409, detail="Ya existe una referencia con ese nombre y talla.")

    reference_id = str(uuid4())

    try:
        await db.execute(
            text("""
                INSERT INTO product_references (
                    id,
                    company_id,
                    name,
                    size,
                    initial_quantity,
                    activation_date,
                    bot_active,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :name,
                    :size,
                    :initial_quantity,
                    CASE WHEN :initial_quantity > 0 THEN now() ELSE NULL END,
                    :bot_active,
                    now(),
                    now()
                )
            """),
            {
                "id": reference_id,
                "company_id": company_id,
                "name": name,
                "size": size,
                "initial_quantity": initial_quantity,
                "bot_active": bot_active,
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
        "size": size,
        "initial_quantity": initial_quantity,
        "bot_active": bot_active,
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
    size = clean(payload.get("size")) if "size" in payload else clean(current["size"])
    initial_quantity = to_int(payload.get("initial_quantity"), int(current["initial_quantity"] or 0)) if "initial_quantity" in payload else int(current["initial_quantity"] or 0)
    bot_active = to_bool(payload.get("bot_active"), bool(current["bot_active"])) if "bot_active" in payload else bool(current["bot_active"])

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
              AND lower(size) = lower(:size)
              AND id <> :reference_id
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
            "name": name,
            "size": size,
        },
    )

    if duplicate.scalar():
        raise HTTPException(status_code=409, detail="Ya existe otra referencia con ese nombre y talla.")

    try:
        await db.execute(
            text("""
                UPDATE product_references
                SET
                    name = :name,
                    size = :size,
                    initial_quantity = :initial_quantity,
                    activation_date = CASE
                        WHEN activation_date IS NULL AND :initial_quantity > 0 THEN now()
                        ELSE activation_date
                    END,
                    bot_active = :bot_active,
                    updated_at = now()
                WHERE company_id = :company_id
                  AND id = :reference_id
            """),
            {
                "company_id": company_id,
                "reference_id": reference_id,
                "name": name,
                "size": size,
                "initial_quantity": initial_quantity,
                "bot_active": bot_active,
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
        "size": size,
        "initial_quantity": initial_quantity,
        "bot_active": bot_active,
        "updated_at": datetime.utcnow().isoformat() + "Z",
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
                DELETE FROM product_references
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
                size,
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
            "size": clean(row["size"]),
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
                size,
                initial_quantity,
                activation_date,
                bot_active,
                created_at,
                updated_at
            FROM product_references
            WHERE company_id = :company_id
            ORDER BY name ASC, size ASC
        """),
        {"company_id": company_id},
    )

    refs = [row_to_dict(row) for row in refs_result.mappings().all()]

    finished_map: dict[tuple[str, str], int] = {}

    if await table_exists(db, "reference_production_closures"):
        try:
            closure_cols = await columns(db, "reference_production_closures")

            if {"company_id", "reference_name", "size", "quantity_finished"}.issubset(closure_cols):
                prod_result = await db.execute(
                    text("""
                        SELECT
                            reference_name,
                            size,
                            COALESCE(sum(quantity_finished), 0) AS finished
                        FROM reference_production_closures
                        WHERE company_id::text = :company_id
                        GROUP BY reference_name, size
                    """),
                    {"company_id": company_id},
                )

                for row in prod_result.mappings().all():
                    key = (clean(row["reference_name"]).lower(), clean(row["size"]).lower())
                    finished_map[key] = int(row["finished"] or 0)

        except Exception:
            await db.rollback()

    by_reference_size = []
    initial_total = 0
    finished_total = 0
    bot_active_count = 0

    for ref in refs:
        initial = int(ref.get("initial_quantity") or 0)
        key = (clean(ref.get("name")).lower(), clean(ref.get("size")).lower())
        finished = int(finished_map.get(key, 0))
        pending = max(initial - finished, 0)

        initial_total += initial
        finished_total += finished

        if ref.get("bot_active"):
            bot_active_count += 1

        by_reference_size.append({
            "id": ref.get("id"),
            "name": ref.get("name"),
            "size": ref.get("size"),
            "initial_quantity": initial,
            "finished_quantity": finished,
            "pending_quantity": pending,
            "progress_percent": round((finished / initial) * 100, 2) if initial > 0 else 0,
            "bot_active": bool(ref.get("bot_active")),
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
    db: AsyncSession = Depends(get_db),
) -> Response:
    data = await list_references(
        company_id=company_id,
        q=q,
        date_from=date_from,
        date_to=date_to,
        bot_active=bot_active,
        db=db,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "id",
        "company_id",
        "name",
        "size",
        "initial_quantity",
        "activation_date",
        "bot_active",
        "created_at",
        "updated_at",
    ])

    for item in data["items"]:
        writer.writerow([
            item.get("id"),
            item.get("company_id"),
            item.get("name"),
            item.get("size"),
            item.get("initial_quantity"),
            item.get("activation_date"),
            item.get("bot_active"),
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
