from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

# CX_019E_INVENTORY_INVOICE_BACKEND_START
MAX_INVOICE_BYTES = 8 * 1024 * 1024
ALLOWED_INVOICE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


def _invoice_content_type(upload: UploadFile) -> str:
    content_type = (upload.content_type or "").strip().lower()
    filename = (upload.filename or "").lower()

    if content_type in ALLOWED_INVOICE_TYPES:
        return content_type
    if filename.endswith(".jpg") or filename.endswith(".jpeg"):
        return "image/jpeg"
    if filename.endswith(".png"):
        return "image/png"
    if filename.endswith(".webp"):
        return "image/webp"
    if filename.endswith(".pdf"):
        return "application/pdf"

    raise HTTPException(status_code=422, detail="Factura inválida. Usa JPG, PNG, WEBP o PDF.")


async def _read_invoice_upload(upload: UploadFile | None) -> dict[str, Any] | None:
    if upload is None:
        return None

    original_name = (upload.filename or "").strip()
    if not original_name:
        return None

    content_type = _invoice_content_type(upload)
    content = await upload.read()

    if not content:
        return None
    if len(content) > MAX_INVOICE_BYTES:
        raise HTTPException(status_code=422, detail="La factura supera el máximo permitido de 8 MB.")

    return {
        "invoice_original_name": original_name[:260],
        "invoice_content_type": content_type,
        "invoice_file_bytes": content,
        "invoice_file_size": len(content),
    }


def _movement_invoice_url(movement_id: Any, original_name: Any = None) -> str | None:
    if not movement_id or not original_name:
        return None
    return f"/api/v1/inventory/movements/{movement_id}/invoice"


def inventory_movement_out(row: dict[str, Any]) -> dict[str, Any]:
    def iso(key: str) -> str | None:
        value = row.get(key)
        return value.isoformat() if hasattr(value, "isoformat") else None

    movement_id = row.get("id")
    original_name = row.get("invoice_original_name")
    return {
        "id": str(movement_id),
        "company_id": str(row.get("company_id")),
        "item_id": str(row.get("item_id")) if row.get("item_id") else None,
        "movement_type": row.get("movement_type") or row.get("type") or "entry",
        "quantity_delta": _float(row.get("quantity_delta")),
        "quantity": _float(row.get("quantity") if row.get("quantity") is not None else row.get("quantity_delta")),
        "stock_before": _float(row.get("stock_before")),
        "stock_after": _float(row.get("stock_after")),
        "source_module": row.get("source_module") or "inventory",
        "source_ref": row.get("source_ref") or "",
        "notes": row.get("notes") or "",
        "name_reference": row.get("name_reference") or "",
        "size": row.get("item_size") or "",
        "color": row.get("color") or "",
        "invoice_original_name": original_name or "",
        "invoice_content_type": row.get("invoice_content_type") or "",
        "invoice_file_size": int(row.get("invoice_file_size") or 0),
        "invoice_file_url": _movement_invoice_url(movement_id, original_name),
        "created_at": iso("created_at"),
    }


async def _insert_inventory_entry(
    db: AsyncSession,
    item_id: UUID,
    quantity: Decimal,
    notes: str | None = None,
    invoice_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if quantity <= 0:
        raise HTTPException(status_code=422, detail="La cantidad ingresada debe ser mayor a cero.")

    result = await db.execute(
        text("""
            UPDATE inventory_items
            SET current_stock = current_stock + :quantity,
                stock = COALESCE(stock, current_stock + :quantity),
                stock_actual = COALESCE(stock_actual, current_stock + :quantity),
                updated_at = now()
            WHERE id = :item_id
            RETURNING *
        """),
        {"item_id": str(item_id), "quantity": quantity},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Material no encontrado.")

    item = dict(row)
    stock_after = _to_decimal(item.get("current_stock"))
    stock_before = stock_after - quantity
    movement_id = str(uuid4())
    invoice_data = invoice_data or {}

    await db.execute(
        text("""
            INSERT INTO inventory_movements (
                id,
                company_id,
                item_id,
                movement_type,
                quantity_delta,
                quantity,
                stock_before,
                stock_after,
                source_module,
                notes,
                invoice_original_name,
                invoice_content_type,
                invoice_file_bytes,
                invoice_file_size,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :company_id,
                :item_id,
                'entry',
                :quantity_delta,
                :quantity_delta,
                :stock_before,
                :stock_after,
                'inventory',
                :notes,
                :invoice_original_name,
                :invoice_content_type,
                :invoice_file_bytes,
                :invoice_file_size,
                now(),
                now()
            )
        """),
        {
            "id": movement_id,
            "company_id": str(item["company_id"]),
            "item_id": str(item["id"]),
            "quantity_delta": quantity,
            "stock_before": stock_before,
            "stock_after": stock_after,
            "notes": (notes or "").strip() or "Entrada desde Inventario",
            "invoice_original_name": invoice_data.get("invoice_original_name"),
            "invoice_content_type": invoice_data.get("invoice_content_type"),
            "invoice_file_bytes": invoice_data.get("invoice_file_bytes"),
            "invoice_file_size": invoice_data.get("invoice_file_size"),
        },
    )

    await db.commit()
    output = inventory_item_out(item)
    output["movement_id"] = movement_id
    return output
# CX_019E_INVENTORY_INVOICE_BACKEND_END


VALID_ITEM_STATUSES = {"active", "inactive"}
VALID_MOVEMENT_TYPES = {"initial", "entry", "delivery", "return", "manual_adjustment"}


class InventoryItemCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name_reference: str | None = None
    name: str | None = None
    reference: str | None = None
    size: str | None = None
    item_size: str | None = None
    color: str | None = None
    initial_quantity: float | int | str | None = 0
    min_stock: float | int | str | None = None
    minimum_stock: float | int | str | None = None


class InventoryItemUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name_reference: str | None = None
    name: str | None = None
    reference: str | None = None
    size: str | None = None
    item_size: str | None = None
    color: str | None = None
    min_stock: float | int | str | None = None
    minimum_stock: float | int | str | None = None
    status: str | None = None


class InventoryEntryPayload(BaseModel):
    quantity: float | int | str
    notes: str | None = None


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value is None or value == "":
            return default
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Cantidad inválida.")


def _float(value: Any) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except Exception:
        return 0.0


async def ensure_inventory_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            sku text NULL,
            name text NULL,
            reference text NULL,
            name_reference text NOT NULL DEFAULT '',
            item_size varchar(120) NULL,
            color varchar(120) NULL,
            min_stock numeric(14, 2) NOT NULL DEFAULT 0,
            current_stock numeric(14, 2) NOT NULL DEFAULT 0,
            status varchar(40) NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id uuid NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            movement_type varchar(60) NOT NULL DEFAULT 'entry',
            quantity_delta numeric(14, 2) NOT NULL DEFAULT 0,
            source_module varchar(80) NOT NULL DEFAULT 'inventory',
            source_ref varchar(220) NULL,
            notes text NULL,
            stock_before numeric(14,2) NULL,
            stock_after numeric(14,2) NULL,
            invoice_original_name text NULL,
            invoice_content_type varchar(140) NULL,
            invoice_file_bytes bytea NULL,
            invoice_file_size integer NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """))

    # Defensive upgrades for tables created by previous local patches or older migrations.
    for stmt in [
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS sku text NULL",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS name text NULL",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS reference text NULL",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS name_reference text NOT NULL DEFAULT ''",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS item_size varchar(120) NULL",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS color varchar(120) NULL",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS min_stock numeric(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS current_stock numeric(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS status varchar(40) NOT NULL DEFAULT 'active'",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()",
        "ALTER TABLE inventory_items ALTER COLUMN sku SET DEFAULT ''",
        "ALTER TABLE inventory_items ALTER COLUMN name SET DEFAULT ''",
        "ALTER TABLE inventory_items ALTER COLUMN reference SET DEFAULT ''",
        "UPDATE inventory_items SET name_reference = COALESCE(NULLIF(name_reference, ''), NULLIF(sku, ''), NULLIF(name, ''), NULLIF(reference, ''), id::text) WHERE name_reference IS NULL OR trim(name_reference) = ''",
        "UPDATE inventory_items SET sku = COALESCE(NULLIF(sku, ''), NULLIF(name_reference, ''), NULLIF(name, ''), NULLIF(reference, ''), id::text) WHERE sku IS NULL OR trim(sku) = ''",
        "UPDATE inventory_items SET name = COALESCE(NULLIF(name, ''), NULLIF(name_reference, ''), NULLIF(sku, ''), NULLIF(reference, ''), id::text) WHERE name IS NULL OR trim(name) = ''",
        "UPDATE inventory_items SET reference = COALESCE(NULLIF(reference, ''), NULLIF(name_reference, ''), NULLIF(sku, ''), NULLIF(name, ''), id::text) WHERE reference IS NULL OR trim(reference) = ''",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS movement_type varchar(60) NOT NULL DEFAULT 'entry'",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS quantity_delta numeric(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS quantity numeric(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS source_module varchar(80) NOT NULL DEFAULT 'inventory'",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS source_ref varchar(220) NULL",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS notes text NULL",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS stock_before numeric(14,2) NULL",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS stock_after numeric(14,2) NULL",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS invoice_original_name text NULL",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS invoice_content_type varchar(140) NULL",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS invoice_file_bytes bytea NULL",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS invoice_file_size integer NULL",
        "SELECT 1 /* CX_019E_INVENTORY_STORAGE_COLUMNS */",
        "ALTER TABLE inventory_movements ALTER COLUMN quantity SET DEFAULT 0",
        "UPDATE inventory_movements SET quantity = COALESCE(quantity, quantity_delta, 0)",
        "UPDATE inventory_movements SET quantity_delta = COALESCE(quantity_delta, quantity, 0)",
    ]:
        await db.execute(text(stmt))

    # Remove blocking NOT NULL constraints left by old experimental schemas.
    await db.execute(text("""
        DO $$
        DECLARE col_name text;
        BEGIN
          FOREACH col_name IN ARRAY ARRAY['sku','name','reference','category','unit','description']
          LOOP
            IF EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = 'inventory_items'
                AND column_name = col_name
            ) THEN
              EXECUTE format('ALTER TABLE inventory_items ALTER COLUMN %I DROP NOT NULL', col_name);
            END IF;
          END LOOP;
        END $$;
    """))

    # Remove blocking NOT NULL constraints left by old inventory_movements schemas.
    await db.execute(text("""
        DO $$
        DECLARE col_name text;
        BEGIN
          FOREACH col_name IN ARRAY ARRAY['quantity','before_quantity','after_quantity','unit_cost','total_cost','source_ref','notes']
          LOOP
            IF EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = 'inventory_movements'
                AND column_name = col_name
            ) THEN
              EXECUTE format('ALTER TABLE inventory_movements ALTER COLUMN %I DROP NOT NULL', col_name);
            END IF;
          END LOOP;
        END $$;
    """))

    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_inventory_items_company ON inventory_items(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_inventory_items_status ON inventory_items(company_id, status);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_inventory_items_name ON inventory_items(company_id, lower(name_reference));"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_inventory_movements_company_item ON inventory_movements(company_id, item_id);"))
    await db.commit()


def inventory_item_out(row: dict[str, Any]) -> dict[str, Any]:
    def iso(key: str) -> str | None:
        value = row.get(key)
        return value.isoformat() if hasattr(value, "isoformat") else None

    current_stock = _float(row.get("current_stock"))
    min_stock = _float(row.get("min_stock"))
    return {
        "id": str(row.get("id")),
        "company_id": str(row.get("company_id")),
        "name_reference": row.get("name_reference") or "",
        "size": row.get("item_size") or "",
        "color": row.get("color") or "",
        "min_stock": min_stock,
        "current_stock": current_stock,
        "status": row.get("status") or "active",
        "alert_low": (row.get("status") or "active") == "active" and current_stock <= min_stock,
        "created_at": iso("created_at"),
        "updated_at": iso("updated_at"),
    }


def inventory_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    active = [row for row in rows if str(row.get("status") or "").lower() == "active"]
    inactive = [row for row in rows if str(row.get("status") or "").lower() == "inactive"]
    low_stock = [row for row in active if bool(row.get("alert_low"))]
    total_stock = sum(_float(row.get("current_stock")) for row in rows)
    return {
        "total": len(rows),
        "active": len(active),
        "inactive": len(inactive),
        "low_stock": len(low_stock),
        "total_stock_units": total_stock,
    }


@router.get("/companies/{company_id}/items")
async def list_inventory_items(
    company_id: UUID,
    include_inactive: bool = Query(True),
    q: str | None = Query(None),
    limit: int = Query(500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_inventory_storage(db)

    limit = max(1, min(int(limit or 500), 1000))
    filters = ["company_id = :company_id"]
    params: dict[str, Any] = {"company_id": str(company_id), "limit": limit}

    if not include_inactive:
        filters.append("status = 'active'")

    if q:
        filters.append("""
            (
              lower(name_reference) LIKE :q
              OR lower(COALESCE(item_size, '')) LIKE :q
              OR lower(COALESCE(color, '')) LIKE :q
            )
        """)
        params["q"] = f"%{q.strip().lower()}%"

    result = await db.execute(
        text(f"""
            SELECT *
            FROM inventory_items
            WHERE {" AND ".join(filters)}
            ORDER BY
              CASE status WHEN 'active' THEN 1 ELSE 2 END,
              lower(name_reference),
              item_size NULLS LAST,
              color NULLS LAST
            LIMIT :limit
        """),
        params,
    )
    rows = [inventory_item_out(dict(row)) for row in result.mappings().all()]
    return {"company_id": str(company_id), "summary": inventory_summary(rows), "items": rows}


@router.post("/companies/{company_id}/items")
async def create_inventory_item(
    company_id: UUID,
    payload: InventoryItemCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_inventory_storage(db)

    name = (payload.name_reference or payload.name or payload.reference or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Nombre / referencia es obligatorio.")

    initial_qty = _to_decimal(payload.initial_quantity)
    min_stock_source = payload.min_stock if payload.min_stock is not None else payload.minimum_stock
    min_stock = _to_decimal(min_stock_source)
    if initial_qty < 0:
        raise HTTPException(status_code=422, detail="La cantidad inicial no puede ser negativa.")
    if min_stock < 0:
        raise HTTPException(status_code=422, detail="El mínimo no puede ser negativo.")

    result = await db.execute(
        text("""
            INSERT INTO inventory_items (
                id, company_id, sku, name, reference, name_reference, item_size, color, min_stock, current_stock, status, created_at, updated_at
            )
            VALUES (
                :id, :company_id, :sku, :name, :reference, :name_reference, :item_size, :color, :min_stock, :current_stock, 'active', now(), now()
            )
            RETURNING *
        """),
        {
            "id": str(uuid4()),
            "company_id": str(company_id),
            "sku": name,
            "name": name,
            "reference": name,
            "name_reference": name,
            "item_size": (payload.size or payload.item_size or "").strip() or None,
            "color": (payload.color or "").strip() or None,
            "min_stock": min_stock,
            "current_stock": initial_qty,
        },
    )
    item = dict(result.mappings().first())

    if initial_qty != 0:
        await db.execute(
            text("""
                INSERT INTO inventory_movements (
                    id, company_id, item_id, movement_type, quantity_delta, quantity, stock_before, stock_after, source_module, notes, created_at, updated_at
                )
                VALUES (
                    :id, :company_id, :item_id, 'initial', :quantity_delta, :quantity_delta, 0, :quantity_delta, 'inventory', 'Cantidad inicial', now(), now()
                )
            """),
            {
                "id": str(uuid4()),
                "company_id": str(company_id),
                "item_id": str(item["id"]),
                "quantity_delta": initial_qty,
            },
        )

    await db.commit()
    return inventory_item_out(item)


@router.patch("/items/{item_id}")
async def update_inventory_item(
    item_id: UUID,
    payload: InventoryItemUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_inventory_storage(db)

    status = payload.status.strip().lower() if payload.status else None
    if status and status not in VALID_ITEM_STATUSES:
        raise HTTPException(status_code=422, detail="Estado inválido.")

    min_stock = None
    min_stock_source = payload.min_stock if payload.min_stock is not None else payload.minimum_stock
    if min_stock_source is not None:
        min_stock = _to_decimal(min_stock_source)
        if min_stock < 0:
            raise HTTPException(status_code=422, detail="El mínimo no puede ser negativo.")

    result = await db.execute(
        text("""
            UPDATE inventory_items
            SET
              sku = COALESCE(NULLIF(:name_reference, ''), sku),
              name = COALESCE(NULLIF(:name_reference, ''), name),
              reference = COALESCE(NULLIF(:name_reference, ''), reference),
              name_reference = COALESCE(NULLIF(:name_reference, ''), name_reference),
              item_size = :item_size,
              color = :color,
              min_stock = COALESCE(:min_stock, min_stock),
              status = COALESCE(:status, status),
              updated_at = now()
            WHERE id = :item_id
            RETURNING *
        """),
        {
            "item_id": str(item_id),
            "name_reference": (payload.name_reference or payload.name or payload.reference or "").strip() if (payload.name_reference is not None or payload.name is not None or payload.reference is not None) else "",
            "item_size": (payload.size or payload.item_size or "").strip() if (payload.size is not None or payload.item_size is not None) else None,
            "color": (payload.color or "").strip() if payload.color is not None else None,
            "min_stock": min_stock,
            "status": status,
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Material no encontrado.")

    await db.commit()
    return inventory_item_out(dict(row))



@router.post("/items/{item_id}/entry")
async def add_inventory_entry(
    item_id: UUID,
    payload: InventoryEntryPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_inventory_storage(db)

    quantity = _to_decimal(payload.quantity)
    return await _insert_inventory_entry(
        db=db,
        item_id=item_id,
        quantity=quantity,
        notes=payload.notes or "Entrada desde Inventario",
        invoice_data=None,
    )


@router.post("/items/{item_id}/entry-with-invoice")
async def add_inventory_entry_with_invoice(
    item_id: UUID,
    quantity: str = Form(...),
    notes: str | None = Form(None),
    invoice: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_inventory_storage(db)

    qty = _to_decimal(quantity)
    invoice_data = await _read_invoice_upload(invoice)
    return await _insert_inventory_entry(
        db=db,
        item_id=item_id,
        quantity=qty,
        notes=notes or "Entrada desde Inventario",
        invoice_data=invoice_data,
    )


@router.get("/companies/{company_id}/movements")
async def list_inventory_movements(
    company_id: UUID,
    item_id: UUID | None = Query(None),
    limit: int = Query(120),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_inventory_storage(db)

    limit = max(1, min(int(limit or 120), 500))
    filters = ["m.company_id = :company_id"]
    params: dict[str, Any] = {"company_id": str(company_id), "limit": limit}

    if item_id:
        filters.append("m.item_id = :item_id")
        params["item_id"] = str(item_id)

    result = await db.execute(
        text(f"""
            SELECT
                m.id,
                m.company_id,
                m.item_id,
                m.movement_type,
                m.quantity_delta,
                m.quantity,
                m.stock_before,
                m.stock_after,
                m.source_module,
                m.source_ref,
                m.notes,
                m.invoice_original_name,
                m.invoice_content_type,
                m.invoice_file_size,
                m.created_at,
                i.name_reference,
                i.item_size,
                i.color
            FROM inventory_movements m
            LEFT JOIN inventory_items i ON i.id = m.item_id
            WHERE {" AND ".join(filters)}
            ORDER BY m.created_at DESC
            LIMIT :limit
        """),
        params,
    )

    movements = [inventory_movement_out(dict(row)) for row in result.mappings().all()]
    return {"company_id": str(company_id), "movements": movements}


@router.get("/movements/{movement_id}/invoice")
async def get_inventory_movement_invoice(
    movement_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await ensure_inventory_storage(db)

    result = await db.execute(
        text("""
            SELECT invoice_original_name, invoice_content_type, invoice_file_bytes
            FROM inventory_movements
            WHERE id = :movement_id
            LIMIT 1
        """),
        {"movement_id": str(movement_id)},
    )
    row = result.mappings().first()
    if not row or not row.get("invoice_file_bytes"):
        raise HTTPException(status_code=404, detail="Factura no encontrada.")

    original_name = str(row.get("invoice_original_name") or "factura")
    safe_name = original_name.replace("\\", "_").replace("/", "_").replace('"', "")
    content_type = str(row.get("invoice_content_type") or "application/octet-stream")
    content = row.get("invoice_file_bytes")
    if isinstance(content, memoryview):
        content = content.tobytes()

    return Response(
        content=bytes(content),
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.post("/items/{item_id}/disable")
async def disable_inventory_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_inventory_storage(db)

    result = await db.execute(
        text("""
            UPDATE inventory_items
            SET status = 'inactive',
                updated_at = now()
            WHERE id = :item_id
            RETURNING *
        """),
        {"item_id": str(item_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Material no encontrado.")

    await db.commit()
    return inventory_item_out(dict(row))
