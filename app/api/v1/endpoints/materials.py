from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

ORDER_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "delivered",
    "returned",
    "returned_partial",
    "cancelled",
}
FINAL_STATUSES = {"delivered", "returned", "returned_partial", "rejected", "cancelled"}


class MaterialStatusPayload(BaseModel):
    status: str
    notes: str | None = None


class MaterialRequestCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    employee_id: str | None = None
    employee_name: str | None = None
    employee_role: str | None = None
    inventory_item_id: str | None = None
    material_name: str | None = None
    quantity: float | int | str = 1
    unit: str | None = None
    notes: str | None = None
    source_channel: str | None = "client"


class MaterialApprovalPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    destination: str | None = None
    units: list[dict[str, Any]] | None = None
    notes: str | None = None


class MaterialReturnPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_number: str
    observation: str | None = None
    labels: list[str] | None = None


class MaterialReturnSelectedPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    observation: str | None = None
    unit_ids: list[str] | None = None
    order_number: str | None = None


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value is None or value == "":
            return default
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Cantidad inválida.")


def _num(value: Any) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except Exception:
        return 0.0


def _int_quantity(value: Any) -> int:
    q = _to_decimal(value, Decimal("1"))
    if q <= 0:
        raise HTTPException(status_code=422, detail="La cantidad debe ser mayor a cero.")
    if q != q.to_integral_value():
        raise HTTPException(status_code=422, detail="Para salida por label/SKU la cantidad debe ser entera.")
    if q > Decimal("500"):
        raise HTTPException(status_code=422, detail="Máximo 500 unidades por orden.")
    return int(q)


async def ensure_materials_storage(db: AsyncSession) -> None:
    # Inventario compatible. Se replica aquí para que Materiales pueda operar incluso si no se abrió Inventario.
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name_reference text NULL,
            item_size varchar(120) NULL,
            color varchar(120) NULL,
            min_stock numeric(14,2) DEFAULT 0,
            current_stock numeric(14,2) DEFAULT 0,
            sku text NULL,
            name text NULL,
            reference text NULL,
            description text NULL,
            unit text NULL,
            category text NULL,
            minimum_stock numeric(14,2) DEFAULT 0,
            stock numeric(14,2) DEFAULT 0,
            stock_actual numeric(14,2) DEFAULT 0,
            status varchar(40) DEFAULT 'active',
            is_active boolean DEFAULT true,
            created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now()
        );
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL,
            item_id uuid NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            movement_type varchar(80),
            quantity_delta numeric(14,2) DEFAULT 0,
            source_module varchar(80) DEFAULT 'materials',
            source_ref varchar(220),
            notes text,
            quantity numeric(14,2) DEFAULT 0,
            type varchar(80),
            reason text,
            status varchar(40) DEFAULT 'active',
            created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now()
        );
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS material_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NULL REFERENCES employees(id) ON DELETE SET NULL,
            employee_name varchar(180) NULL,
            employee_role varchar(100) NULL,
            material_name text NOT NULL DEFAULT '',
            quantity numeric(14, 2) NOT NULL DEFAULT 1,
            unit varchar(40) NULL,
            notes text NULL,
            status varchar(40) NOT NULL DEFAULT 'pending',
            source_channel varchar(80) NOT NULL DEFAULT 'client',
            source_ref varchar(220) NULL,
            attendance_event_id uuid NULL,
            requested_at timestamptz NOT NULL DEFAULT now(),
            status_updated_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            order_number varchar(80) NULL,
            inventory_item_id uuid NULL REFERENCES inventory_items(id) ON DELETE SET NULL,
            destination text NULL,
            quantity_returned numeric(14,2) NOT NULL DEFAULT 0,
            approved_at timestamptz NULL,
            delivered_at timestamptz NULL,
            returned_at timestamptz NULL
        );
    """))

    # Upgrades for existing tables.
    for stmt in [
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS order_number varchar(80) NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS inventory_item_id uuid NULL REFERENCES inventory_items(id) ON DELETE SET NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS destination text NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS quantity_returned numeric(14,2) NOT NULL DEFAULT 0",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS approved_at timestamptz NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS delivered_at timestamptz NULL",
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS returned_at timestamptz NULL",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS quantity numeric(14,2) DEFAULT 0",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS quantity_delta numeric(14,2) DEFAULT 0",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS source_module varchar(80) DEFAULT 'materials'",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS source_ref varchar(220)",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS notes text",
        "ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS status varchar(40) DEFAULT 'active'",
    ]:
        await db.execute(text(stmt))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS material_order_units (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            request_id uuid NOT NULL REFERENCES material_requests(id) ON DELETE CASCADE,
            order_number varchar(80) NOT NULL,
            inventory_item_id uuid NULL REFERENCES inventory_items(id) ON DELETE SET NULL,
            unit_index integer NOT NULL,
            label_sku varchar(220) NULL,
            status varchar(40) NOT NULL DEFAULT 'reserved',
            destination text NULL,
            returned_observation text NULL,
            delivered_at timestamptz NULL,
            returned_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """))

    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_company ON material_requests(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_status ON material_requests(company_id, status);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_employee ON material_requests(company_id, employee_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_order ON material_requests(company_id, order_number);"))
    await db.execute(text("DROP INDEX IF EXISTS uq_material_requests_order;"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_order_number ON material_requests(company_id, order_number);"))
    await db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_material_requests_source_ref ON material_requests(company_id, source_ref) WHERE source_ref IS NOT NULL;"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_order_units_request ON material_order_units(request_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_order_units_order ON material_order_units(company_id, order_number);"))
    await db.commit()


async def _generate_order_number(db: AsyncSession, company_id: UUID) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"MAT-{today}-"
    for _ in range(20):
        result = await db.execute(
            text("""
                SELECT COALESCE(MAX(CAST(right(order_number, 6) AS integer)), 0) + 1
                FROM material_requests
                WHERE company_id = :company_id
                  AND order_number LIKE :prefix_like
            """),
            {"company_id": str(company_id), "prefix_like": f"{prefix}%"},
        )
        number = int(result.scalar() or 1)
        order_number = f"{prefix}{number:06d}"
        exists = await db.execute(
            text("SELECT 1 FROM material_requests WHERE company_id=:company_id AND order_number=:order_number LIMIT 1"),
            {"company_id": str(company_id), "order_number": order_number},
        )
        if not exists.first():
            return order_number
    return f"{prefix}{uuid4().hex[:6].upper()}"


async def _inventory_item(db: AsyncSession, company_id: UUID, item_id: str | None, material_name: str | None = None) -> dict[str, Any] | None:
    if item_id:
        result = await db.execute(
            text("""
                SELECT *
                FROM inventory_items
                WHERE id = :item_id
                  AND company_id = :company_id
                  AND COALESCE(status, 'active') = 'active'
                LIMIT 1
            """),
            {"item_id": item_id, "company_id": str(company_id)},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    name = (material_name or "").strip().lower()
    if not name:
        return None

    result = await db.execute(
        text("""
            SELECT *
            FROM inventory_items
            WHERE company_id = :company_id
              AND COALESCE(status, 'active') = 'active'
              AND (
                lower(COALESCE(name_reference, '')) = :name
                OR lower(COALESCE(sku, '')) = :name
                OR lower(COALESCE(name, '')) = :name
                OR lower(COALESCE(reference, '')) = :name
              )
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"company_id": str(company_id), "name": name},
    )
    row = result.mappings().first()
    return dict(row) if row else None


def material_request_out(row: dict[str, Any]) -> dict[str, Any]:
    def iso(key: str) -> str | None:
        value = row.get(key)
        return value.isoformat() if hasattr(value, "isoformat") else None

    quantity = _num(row.get("quantity"))
    returned = _num(row.get("quantity_returned"))
    return {
        "id": str(row.get("id")),
        "company_id": str(row.get("company_id")),
        "order_number": row.get("order_number") or "",
        "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None,
        "employee_name": row.get("employee_name") or "",
        "employee_role": row.get("employee_role") or "",
        "inventory_item_id": str(row.get("inventory_item_id")) if row.get("inventory_item_id") else None,
        "material_name": row.get("material_name") or "",
        "name_reference": row.get("name_reference") or row.get("material_name") or "",
        "item_size": row.get("item_size") or "",
        "color": row.get("color") or "",
        "quantity": quantity,
        "quantity_returned": returned,
        "unit": row.get("unit") or "",
        "destination": row.get("destination") or "",
        "notes": row.get("notes") or "",
        "status": row.get("status") or "pending",
        "source_channel": row.get("source_channel") or "",
        "source_ref": row.get("source_ref") or "",
        "attendance_event_id": str(row.get("attendance_event_id")) if row.get("attendance_event_id") else None,
        "requested_at": iso("requested_at"),
        "approved_at": iso("approved_at"),
        "delivered_at": iso("delivered_at"),
        "returned_at": iso("returned_at"),
        "status_updated_at": iso("status_updated_at"),
        "created_at": iso("created_at"),
        "updated_at": iso("updated_at"),
    }


def summary_from_requests(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(rows),
        "pending": 0,
        "approved": 0,
        "delivered": 0,
        "returned": 0,
        "returned_partial": 0,
        "rejected": 0,
        "active_orders": 0,
    }
    for row in rows:
        status = str(row.get("status") or "pending").lower()
        if status in summary:
            summary[status] += 1
        if status not in FINAL_STATUSES:
            summary["active_orders"] += 1
    summary["approved_or_delivered"] = summary["approved"] + summary["delivered"]
    return summary


async def _request_by_id(db: AsyncSession, request_id: UUID) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT mr.*, ii.name_reference, ii.item_size, ii.color, ii.current_stock
            FROM material_requests mr
            LEFT JOIN inventory_items ii ON ii.id = mr.inventory_item_id
            WHERE mr.id = :request_id
            LIMIT 1
        """),
        {"request_id": str(request_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Orden de material no encontrada.")
    return dict(row)


async def _ensure_request_units(
    db: AsyncSession,
    *,
    request: dict[str, Any],
    destination: str | None,
    units: list[dict[str, Any]] | None,
    default_status: str = "reserved",
) -> None:
    company_id = str(request["company_id"])
    request_id = str(request["id"])
    order_number = request.get("order_number")
    inventory_item_id = str(request.get("inventory_item_id")) if request.get("inventory_item_id") else None
    qty = _int_quantity(request.get("quantity"))

    await db.execute(text("DELETE FROM material_order_units WHERE request_id = :request_id"), {"request_id": request_id})

    units = units or []
    values: list[dict[str, Any]] = []
    for index in range(qty):
        item = units[index] if index < len(units) and isinstance(units[index], dict) else {}
        label = str(item.get("label_sku") or item.get("label") or item.get("sku") or "").strip()
        values.append({
            "company_id": company_id,
            "request_id": request_id,
            "order_number": order_number,
            "inventory_item_id": inventory_item_id,
            "unit_index": index + 1,
            "label_sku": label or None,
            "status": default_status,
            "destination": destination or "",
        })

    for value in values:
        await db.execute(
            text("""
                INSERT INTO material_order_units (
                    company_id, request_id, order_number, inventory_item_id,
                    unit_index, label_sku, status, destination, created_at, updated_at
                )
                VALUES (
                    :company_id, :request_id, :order_number, :inventory_item_id,
                    :unit_index, :label_sku, :status, :destination, now(), now()
                )
            """),
            value,
        )


@router.get("/companies/{company_id}/requests")
async def list_material_requests(
    company_id: UUID,
    status: str | None = None,
    limit: int = 300,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)
    limit = max(1, min(int(limit or 300), 1000))

    where_status = ""
    params: dict[str, Any] = {"company_id": str(company_id), "limit": limit}
    if status and status != "all":
        where_status = " AND mr.status = :status"
        params["status"] = status

    result = await db.execute(
        text(f"""
            SELECT
              mr.*,
              ii.name_reference,
              ii.item_size,
              ii.color,
              ii.current_stock
            FROM material_requests mr
            LEFT JOIN inventory_items ii ON ii.id = mr.inventory_item_id
            WHERE mr.company_id = :company_id
            {where_status}
            ORDER BY
              CASE mr.status
                WHEN 'pending' THEN 1
                WHEN 'approved' THEN 2
                WHEN 'delivered' THEN 3
                WHEN 'returned_partial' THEN 4
                WHEN 'returned' THEN 5
                WHEN 'rejected' THEN 6
                ELSE 7
              END,
              mr.requested_at DESC,
              mr.created_at DESC
            LIMIT :limit
        """),
        params,
    )

    rows = [material_request_out(dict(row)) for row in result.mappings().all()]
    return {
        "company_id": str(company_id),
        "summary": summary_from_requests(rows),
        "requests": rows,
    }


@router.post("/companies/{company_id}/requests")
async def create_material_request(
    company_id: UUID,
    payload: MaterialRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)

    qty = _to_decimal(payload.quantity, Decimal("1"))
    if qty <= 0:
        raise HTTPException(status_code=422, detail="La cantidad debe ser mayor a cero.")

    item = await _inventory_item(db, company_id, payload.inventory_item_id, payload.material_name)
    if not item:
        raise HTTPException(status_code=422, detail="Material no disponible en inventario activo.")

    current_stock = _to_decimal(item.get("current_stock"), Decimal("0"))
    if current_stock < qty:
        raise HTTPException(status_code=409, detail="Stock insuficiente para solicitar ese material.")

    order_number = await _generate_order_number(db, company_id)
    result = await db.execute(
        text("""
            INSERT INTO material_requests (
                company_id, employee_id, employee_name, employee_role,
                inventory_item_id, material_name, quantity, unit, notes,
                status, source_channel, source_ref, requested_at,
                status_updated_at, updated_at, order_number
            )
            VALUES (
                :company_id, :employee_id, :employee_name, :employee_role,
                :inventory_item_id, :material_name, :quantity, :unit, :notes,
                'pending', :source_channel, :source_ref, now(), now(), now(), :order_number
            )
            RETURNING *
        """),
        {
            "company_id": str(company_id),
            "employee_id": payload.employee_id,
            "employee_name": (payload.employee_name or "").strip(),
            "employee_role": (payload.employee_role or "").strip(),
            "inventory_item_id": str(item["id"]),
            "material_name": item.get("name_reference") or payload.material_name or "",
            "quantity": qty,
            "unit": (payload.unit or "").strip() or None,
            "notes": (payload.notes or "").strip() or None,
            "source_channel": (payload.source_channel or "client").strip() or "client",
            "source_ref": f"client:{uuid4()}",
            "order_number": order_number,
        },
    )
    row = dict(result.mappings().first())
    await db.commit()
    return material_request_out(row)


@router.post("/requests/{request_id}/approve")
async def approve_material_request(
    request_id: UUID,
    payload: MaterialApprovalPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)
    request = await _request_by_id(db, request_id)

    if str(request.get("status") or "").lower() in {"rejected", "delivered", "returned", "cancelled"}:
        raise HTTPException(status_code=409, detail="Esta orden no se puede aprobar en su estado actual.")

    destination = (payload.destination or "").strip()
    await _ensure_request_units(db, request=request, destination=destination, units=payload.units or [], default_status="reserved")

    result = await db.execute(
        text("""
            UPDATE material_requests
            SET status = 'approved',
                destination = :destination,
                notes = COALESCE(NULLIF(:notes, ''), notes),
                approved_at = COALESCE(approved_at, now()),
                status_updated_at = now(),
                updated_at = now()
            WHERE id = :request_id
            RETURNING *
        """),
        {"request_id": str(request_id), "destination": destination or None, "notes": (payload.notes or "").strip()},
    )
    row = dict(result.mappings().first())
    await db.commit()
    return material_request_out(row)


@router.post("/requests/{request_id}/deliver")
async def deliver_material_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)
    request = await _request_by_id(db, request_id)

    status = str(request.get("status") or "pending").lower()
    if status == "delivered":
        return material_request_out(request)
    if status in {"rejected", "returned", "cancelled"}:
        raise HTTPException(status_code=409, detail="Esta orden no se puede entregar.")

    if not request.get("inventory_item_id"):
        raise HTTPException(status_code=422, detail="La orden no está conectada a inventario.")

    qty = _to_decimal(request.get("quantity"), Decimal("0"))
    stock = _to_decimal(request.get("current_stock"), Decimal("0"))
    if qty <= 0:
        raise HTTPException(status_code=422, detail="Cantidad inválida.")
    if stock < qty:
        raise HTTPException(status_code=409, detail="Stock insuficiente para entregar la orden.")

    # Si no se aprobó antes, crea unidades sin labels para no bloquear operación.
    units_count = await db.execute(text("SELECT COUNT(*) FROM material_order_units WHERE request_id=:request_id"), {"request_id": str(request_id)})
    if int(units_count.scalar() or 0) == 0:
        await _ensure_request_units(db, request=request, destination=request.get("destination") or "", units=[], default_status="reserved")

    await db.execute(
        text("""
            UPDATE inventory_items
            SET current_stock = current_stock - :qty,
                stock = COALESCE(stock, current_stock) - :qty,
                stock_actual = COALESCE(stock_actual, current_stock) - :qty,
                updated_at = now()
            WHERE id = :item_id
        """),
        {"item_id": str(request["inventory_item_id"]), "qty": qty},
    )

    await db.execute(
        text("""
            INSERT INTO inventory_movements (
                id, company_id, item_id, movement_type, quantity_delta, quantity,
                source_module, source_ref, notes, type, reason, created_at, updated_at
            )
            VALUES (
                :id, :company_id, :item_id, 'delivery', :quantity_delta, :quantity,
                'materials', :source_ref, :notes, 'delivery', :reason, now(), now()
            )
        """),
        {
            "id": str(uuid4()),
            "company_id": str(request["company_id"]),
            "item_id": str(request["inventory_item_id"]),
            "quantity_delta": -qty,
            "quantity": qty,
            "source_ref": request.get("order_number"),
            "notes": f"Entrega orden {request.get('order_number')}",
            "reason": "materials_delivery",
        },
    )

    await db.execute(
        text("""
            UPDATE material_order_units
            SET status = 'delivered',
                delivered_at = now(),
                updated_at = now()
            WHERE request_id = :request_id
              AND status <> 'returned'
        """),
        {"request_id": str(request_id)},
    )

    result = await db.execute(
        text("""
            UPDATE material_requests
            SET status = 'delivered',
                delivered_at = COALESCE(delivered_at, now()),
                status_updated_at = now(),
                updated_at = now()
            WHERE id = :request_id
            RETURNING *
        """),
        {"request_id": str(request_id)},
    )
    row = dict(result.mappings().first())
    await db.commit()
    return material_request_out(row)




@router.get("/companies/{company_id}/orders/search")
async def search_material_return_orders(
    company_id: UUID,
    q: str = "",
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)

    query = (q or "").strip()
    if not query:
        return {"company_id": str(company_id), "orders": []}

    limit = max(1, min(int(limit or 10), 25))
    result = await db.execute(
        text("""
            SELECT
              mr.order_number,
              MIN(mr.requested_at) AS requested_at,
              MAX(COALESCE(mr.employee_name, '')) AS employee_name,
              MAX(COALESCE(mr.employee_role, '')) AS employee_role,
              MAX(COALESCE(mr.destination, '')) AS destination,
              COUNT(*) AS lines_count,
              COALESCE(SUM(mr.quantity), 0) AS quantity_total,
              COALESCE(SUM(GREATEST(mr.quantity - COALESCE(mr.quantity_returned, 0), 0)), 0) AS quantity_pending_return,
              BOOL_OR(mr.status = 'delivered') AS has_delivered,
              BOOL_OR(mr.status = 'returned_partial') AS has_partial
            FROM material_requests mr
            WHERE mr.company_id = :company_id
              AND COALESCE(mr.order_number, '') <> ''
              AND UPPER(mr.order_number) LIKE UPPER(:query)
              AND mr.status IN ('delivered', 'returned_partial')
            GROUP BY mr.order_number
            ORDER BY MAX(mr.created_at) DESC
            LIMIT :limit
        """),
        {"company_id": str(company_id), "query": f"%{query}%", "limit": limit},
    )

    orders = []
    for row in result.mappings().all():
        pending = _num(row.get("quantity_pending_return"))
        orders.append({
            "order_number": row.get("order_number") or "",
            "requested_at": row.get("requested_at").isoformat() if hasattr(row.get("requested_at"), "isoformat") else None,
            "employee_name": row.get("employee_name") or "",
            "employee_role": row.get("employee_role") or "",
            "destination": row.get("destination") or "",
            "lines_count": int(row.get("lines_count") or 0),
            "quantity_total": _num(row.get("quantity_total")),
            "quantity_pending_return": pending,
            "status": "delivered" if row.get("has_delivered") else "returned_partial",
        })

    return {"company_id": str(company_id), "orders": orders}


async def _ensure_return_units_for_requests(db: AsyncSession, requests: list[dict[str, Any]]) -> None:
    for request in requests:
        request_id = str(request["id"])
        count_result = await db.execute(
            text("SELECT COUNT(*) FROM material_order_units WHERE request_id = :request_id"),
            {"request_id": request_id},
        )
        if int(count_result.scalar() or 0) > 0:
            continue

        qty = _int_quantity(request.get("quantity"))
        for index in range(qty):
            await db.execute(
                text("""
                    INSERT INTO material_order_units (
                        company_id, request_id, order_number, inventory_item_id,
                        unit_index, label_sku, status, destination,
                        delivered_at, created_at, updated_at
                    )
                    VALUES (
                        :company_id, :request_id, :order_number, :inventory_item_id,
                        :unit_index, NULL, 'delivered', :destination,
                        COALESCE(:delivered_at, now()), now(), now()
                    )
                """),
                {
                    "company_id": str(request["company_id"]),
                    "request_id": request_id,
                    "order_number": request.get("order_number"),
                    "inventory_item_id": str(request.get("inventory_item_id")) if request.get("inventory_item_id") else None,
                    "unit_index": index + 1,
                    "destination": request.get("destination") or "",
                    "delivered_at": request.get("delivered_at"),
                },
            )


@router.get("/companies/{company_id}/orders/{order_number}/return-checklist")
async def get_material_return_checklist(
    company_id: UUID,
    order_number: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)

    order_number = (order_number or "").strip()
    if not order_number:
        raise HTTPException(status_code=422, detail="Número de orden obligatorio.")

    result = await db.execute(
        text("""
            SELECT
              mr.*,
              ii.name_reference,
              ii.item_size,
              ii.color
            FROM material_requests mr
            LEFT JOIN inventory_items ii ON ii.id = mr.inventory_item_id
            WHERE mr.company_id = :company_id
              AND mr.order_number = :order_number
              AND mr.status IN ('delivered', 'returned_partial')
            ORDER BY mr.created_at ASC, mr.id ASC
        """),
        {"company_id": str(company_id), "order_number": order_number},
    )
    requests = [dict(row) for row in result.mappings().all()]
    if not requests:
        return {
            "company_id": str(company_id),
            "order_number": order_number,
            "found": False,
            "message": "Orden de salida entregada no encontrada.",
            "lines": [],
        }

    await _ensure_return_units_for_requests(db, requests)
    await db.commit()

    request_ids = [str(r["id"]) for r in requests]
    placeholders = ", ".join([f":r{i}" for i in range(len(request_ids))])
    params = {f"r{i}": rid for i, rid in enumerate(request_ids)}

    units_result = await db.execute(
        text(f"""
            SELECT *
            FROM material_order_units
            WHERE request_id IN ({placeholders})
            ORDER BY request_id, unit_index ASC, created_at ASC
        """),
        params,
    )

    units_by_request: dict[str, list[dict[str, Any]]] = {}
    for unit in units_result.mappings().all():
        unit_dict = dict(unit)
        units_by_request.setdefault(str(unit_dict.get("request_id")), []).append(unit_dict)

    lines = []
    for request in requests:
        request_id = str(request["id"])
        units = []
        for unit in units_by_request.get(request_id, []):
            unit_status = str(unit.get("status") or "").lower()
            label = (unit.get("label_sku") or "").strip()
            index = int(unit.get("unit_index") or 0)
            units.append({
                "unit_id": str(unit.get("id")),
                "unit_index": index,
                "label_sku": label or f"Unidad {index}",
                "status": unit_status or "delivered",
                "available": unit_status == "delivered",
                "returned_observation": unit.get("returned_observation") or "",
                "returned_at": unit.get("returned_at").isoformat() if hasattr(unit.get("returned_at"), "isoformat") else None,
            })

        qty = _num(request.get("quantity"))
        returned = _num(request.get("quantity_returned"))
        lines.append({
            "request_id": request_id,
            "inventory_item_id": str(request.get("inventory_item_id")) if request.get("inventory_item_id") else None,
            "name_reference": request.get("name_reference") or request.get("material_name") or "",
            "material_name": request.get("material_name") or "",
            "item_size": request.get("item_size") or "",
            "color": request.get("color") or "",
            "quantity": qty,
            "quantity_returned": returned,
            "quantity_pending_return": max(qty - returned, 0),
            "status": request.get("status") or "",
            "destination": request.get("destination") or "",
            "units": units,
        })

    first = requests[0]
    return {
        "company_id": str(company_id),
        "order_number": order_number,
        "found": True,
        "employee_name": first.get("employee_name") or "",
        "employee_role": first.get("employee_role") or "",
        "destination": first.get("destination") or "",
        "requested_at": first.get("requested_at").isoformat() if hasattr(first.get("requested_at"), "isoformat") else None,
        "lines": lines,
    }


@router.post("/companies/{company_id}/orders/{order_number}/return-selected")
async def return_selected_material_units(
    company_id: UUID,
    order_number: str,
    payload: MaterialReturnSelectedPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)

    order_number = (order_number or payload.order_number or "").strip()
    if not order_number:
        raise HTTPException(status_code=422, detail="Número de orden obligatorio para devolución.")

    observation = (payload.observation or "").strip()
    if not observation:
        raise HTTPException(status_code=422, detail="Observación de devolución obligatoria.")

    raw_unit_ids = payload.unit_ids or []
    unit_ids: list[str] = []
    for raw in raw_unit_ids:
        try:
            unit_ids.append(str(UUID(str(raw))))
        except Exception:
            continue

    unit_ids = list(dict.fromkeys(unit_ids))
    if not unit_ids:
        raise HTTPException(status_code=422, detail="Selecciona al menos un Label/SKU para devolver.")

    placeholders = ", ".join([f":u{i}" for i in range(len(unit_ids))])
    params: dict[str, Any] = {
        "company_id": str(company_id),
        "order_number": order_number,
    }
    params.update({f"u{i}": uid for i, uid in enumerate(unit_ids)})

    result = await db.execute(
        text(f"""
            SELECT
              mou.id AS unit_id,
              mou.request_id,
              mou.inventory_item_id,
              mr.company_id,
              mr.order_number,
              mr.quantity,
              mr.quantity_returned
            FROM material_order_units mou
            JOIN material_requests mr ON mr.id = mou.request_id
            WHERE mr.company_id = :company_id
              AND mr.order_number = :order_number
              AND mr.status IN ('delivered', 'returned_partial')
              AND mou.status = 'delivered'
              AND mou.id IN ({placeholders})
            ORDER BY mou.request_id, mou.unit_index
        """),
        params,
    )
    selected_units = [dict(row) for row in result.mappings().all()]
    if not selected_units:
        raise HTTPException(status_code=404, detail="No hay Label/SKU entregados pendientes de devolución para esa orden.")

    grouped: dict[str, dict[str, Any]] = {}
    for unit in selected_units:
        request_id = str(unit["request_id"])
        item = grouped.setdefault(request_id, {
            "request_id": request_id,
            "inventory_item_id": str(unit.get("inventory_item_id")) if unit.get("inventory_item_id") else None,
            "quantity": _to_decimal(unit.get("quantity"), Decimal("0")),
            "quantity_returned": _to_decimal(unit.get("quantity_returned"), Decimal("0")),
            "unit_ids": [],
        })
        item["unit_ids"].append(str(unit["unit_id"]))

    updated_rows: list[dict[str, Any]] = []
    total_returned = Decimal("0")

    for request_id, group in grouped.items():
        qty = Decimal(len(group["unit_ids"])).quantize(Decimal("0.01"))
        total_returned += qty

        if group.get("inventory_item_id"):
            await db.execute(
                text("""
                    UPDATE inventory_items
                    SET current_stock = current_stock + :qty,
                        stock = COALESCE(stock, current_stock) + :qty,
                        stock_actual = COALESCE(stock_actual, current_stock) + :qty,
                        updated_at = now()
                    WHERE id = :item_id
                """),
                {"item_id": group["inventory_item_id"], "qty": qty},
            )

            await db.execute(
                text("""
                    INSERT INTO inventory_movements (
                        id, company_id, item_id, movement_type, quantity_delta, quantity,
                        source_module, source_ref, notes, type, reason, created_at, updated_at
                    )
                    VALUES (
                        :id, :company_id, :item_id, 'return', :quantity_delta, :quantity,
                        'materials', :source_ref, :notes, 'return', :reason, now(), now()
                    )
                """),
                {
                    "id": str(uuid4()),
                    "company_id": str(company_id),
                    "item_id": group["inventory_item_id"],
                    "quantity_delta": qty,
                    "quantity": qty,
                    "source_ref": order_number,
                    "notes": observation,
                    "reason": "materials_return_selected",
                },
            )

        unit_placeholders = ", ".join([f":ru{i}" for i in range(len(group["unit_ids"]))])
        unit_params = {f"ru{i}": uid for i, uid in enumerate(group["unit_ids"])}
        unit_params["observation"] = observation

        await db.execute(
            text(f"""
                UPDATE material_order_units
                SET status = 'returned',
                    returned_observation = :observation,
                    returned_at = now(),
                    updated_at = now()
                WHERE id IN ({unit_placeholders})
                  AND status = 'delivered'
            """),
            unit_params,
        )

        new_returned = group["quantity_returned"] + qty
        total = group["quantity"]
        new_status = "returned" if new_returned >= total else "returned_partial"

        update_result = await db.execute(
            text("""
                UPDATE material_requests
                SET status = CAST(:status AS varchar),
                    quantity_returned = :quantity_returned,
                    returned_at = CASE WHEN CAST(:status AS varchar) = 'returned' THEN now() ELSE returned_at END,
                    notes = COALESCE(notes, '') || CASE WHEN COALESCE(notes, '') = '' THEN '' ELSE E'\n' END || CAST(:return_note AS text),
                    status_updated_at = now(),
                    updated_at = now()
                WHERE id = :request_id
                RETURNING *
            """),
            {
                "request_id": request_id,
                "status": new_status,
                "quantity_returned": new_returned,
                "return_note": f"Devolución: {observation}",
            },
        )
        updated_rows.append(dict(update_result.mappings().first()))

    await db.commit()
    return {
        "company_id": str(company_id),
        "order_number": order_number,
        "returned_quantity": _num(total_returned),
        "updated": [material_request_out(row) for row in updated_rows],
    }


@router.post("/companies/{company_id}/returns")
async def return_material_order(
    company_id: UUID,
    payload: MaterialReturnPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)

    order_number = (payload.order_number or "").strip()
    if not order_number:
        raise HTTPException(status_code=422, detail="Número de orden obligatorio para devolución.")
    observation = (payload.observation or "").strip()
    if not observation:
        raise HTTPException(status_code=422, detail="Observación de devolución obligatoria.")

    result = await db.execute(
        text("""
            SELECT mr.*, ii.current_stock
            FROM material_requests mr
            LEFT JOIN inventory_items ii ON ii.id = mr.inventory_item_id
            WHERE mr.company_id = :company_id
              AND mr.order_number = :order_number
              AND mr.status IN ('delivered', 'returned_partial')
            ORDER BY mr.created_at ASC
        """),
        {"company_id": str(company_id), "order_number": order_number},
    )
    requests = [dict(row) for row in result.mappings().all()]
    if not requests:
        raise HTTPException(status_code=404, detail="Orden de salida entregada no encontrada.")

    labels = [str(x or "").strip() for x in (payload.labels or []) if str(x or "").strip()]
    total_returned = Decimal("0")
    updated_rows: list[dict[str, Any]] = []

    for request in requests:
        if not request.get("inventory_item_id"):
            continue

        unit_filter = ""
        params: dict[str, Any] = {"request_id": str(request["id"])}
        if labels:
            unit_filter = " AND label_sku = ANY(:labels)"
            params["labels"] = labels

        count_result = await db.execute(
            text(f"""
                SELECT COUNT(*)
                FROM material_order_units
                WHERE request_id = :request_id
                  AND status = 'delivered'
                  {unit_filter}
            """),
            params,
        )
        qty_units = int(count_result.scalar() or 0)

        if qty_units <= 0 and not labels:
            qty_remaining = _to_decimal(request.get("quantity"), Decimal("0")) - _to_decimal(request.get("quantity_returned"), Decimal("0"))
            qty_units = int(qty_remaining)

        if qty_units <= 0:
            continue

        qty = Decimal(qty_units).quantize(Decimal("0.01"))
        total_returned += qty

        await db.execute(
            text("""
                UPDATE inventory_items
                SET current_stock = current_stock + :qty,
                    stock = COALESCE(stock, current_stock) + :qty,
                    stock_actual = COALESCE(stock_actual, current_stock) + :qty,
                    updated_at = now()
                WHERE id = :item_id
            """),
            {"item_id": str(request["inventory_item_id"]), "qty": qty},
        )

        await db.execute(
            text("""
                INSERT INTO inventory_movements (
                    id, company_id, item_id, movement_type, quantity_delta, quantity,
                    source_module, source_ref, notes, type, reason, created_at, updated_at
                )
                VALUES (
                    :id, :company_id, :item_id, 'return', :quantity_delta, :quantity,
                    'materials', :source_ref, :notes, 'return', :reason, now(), now()
                )
            """),
            {
                "id": str(uuid4()),
                "company_id": str(company_id),
                "item_id": str(request["inventory_item_id"]),
                "quantity_delta": qty,
                "quantity": qty,
                "source_ref": order_number,
                "notes": observation,
                "reason": "materials_return",
            },
        )

        if labels:
            await db.execute(
                text("""
                    UPDATE material_order_units
                    SET status = 'returned',
                        returned_observation = :observation,
                        returned_at = now(),
                        updated_at = now()
                    WHERE request_id = :request_id
                      AND label_sku = ANY(:labels)
                      AND status = 'delivered'
                """),
                {"request_id": str(request["id"]), "labels": labels, "observation": observation},
            )
        else:
            await db.execute(
                text("""
                    UPDATE material_order_units
                    SET status = 'returned',
                        returned_observation = :observation,
                        returned_at = now(),
                        updated_at = now()
                    WHERE request_id = :request_id
                      AND status = 'delivered'
                """),
                {"request_id": str(request["id"]), "observation": observation},
            )

        new_returned = _to_decimal(request.get("quantity_returned"), Decimal("0")) + qty
        total = _to_decimal(request.get("quantity"), Decimal("0"))
        new_status = "returned" if new_returned >= total else "returned_partial"

        update_result = await db.execute(
            text("""
                UPDATE material_requests
                SET status = :status,
                    quantity_returned = :quantity_returned,
                    returned_at = now(),
                    notes = COALESCE(notes, '') || CASE WHEN COALESCE(notes, '') = '' THEN '' ELSE E'\n' END || :return_note,
                    status_updated_at = now(),
                    updated_at = now()
                WHERE id = :request_id
                RETURNING *
            """),
            {
                "request_id": str(request["id"]),
                "status": new_status,
                "quantity_returned": new_returned,
                "return_note": f"Devolución: {observation}",
            },
        )
        updated_rows.append(dict(update_result.mappings().first()))

    if total_returned <= 0:
        if labels:
            raise HTTPException(status_code=404, detail="No hay labels/SKU entregados pendientes de devolución para esa orden.")
        raise HTTPException(status_code=409, detail="La orden ya fue devuelta.")

    await db.commit()
    return {
        "company_id": str(company_id),
        "order_number": order_number,
        "returned_quantity": _num(total_returned),
        "updated": [material_request_out(row) for row in updated_rows],
    }


@router.patch("/requests/{request_id}/status")
async def update_material_request_status(
    request_id: UUID,
    payload: MaterialStatusPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)

    status = str(payload.status or "").strip().lower()
    if status not in ORDER_STATUSES:
        raise HTTPException(status_code=422, detail="Estado de material inválido.")

    if status == "delivered":
        return await deliver_material_request(request_id, db=db)

    if status in {"returned", "returned_partial"}:
        request = await _request_by_id(db, request_id)
        if not request.get("order_number"):
            raise HTTPException(status_code=422, detail="La devolución requiere número de orden.")
        return await return_material_order(
            request["company_id"],
            MaterialReturnPayload(order_number=request["order_number"], observation=payload.notes or "Devolución registrada"),
            db,
        )

    if status == "approved":
        return await approve_material_request(request_id, MaterialApprovalPayload(notes=payload.notes), db)

    result = await db.execute(
        text("""
            UPDATE material_requests
            SET status = :status,
                notes = COALESCE(NULLIF(:notes, ''), notes),
                status_updated_at = now(),
                updated_at = now()
            WHERE id = :request_id
            RETURNING *
        """),
        {
            "request_id": str(request_id),
            "status": status,
            "notes": (payload.notes or "").strip(),
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Solicitud de material no encontrada.")

    await db.commit()
    return material_request_out(dict(row))
