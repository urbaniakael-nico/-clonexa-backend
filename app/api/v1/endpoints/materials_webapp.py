from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.materials import ensure_materials_storage, _generate_order_number, material_request_out

router = APIRouter()

ALLOWED_MATERIAL_ROLES = {"admin", "admin_empresa", "supervisor", "inventario", "inventory"}


class WebAppCartItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inventory_item_id: str
    quantity: int | float | str


class WebAppOrderCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    telegram_user_id: str | None = None
    telegram_username: str | None = None
    items: list[WebAppCartItem]
    notes: str | None = None


def _to_decimal(value: Any) -> Decimal:
    try:
        qty = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Cantidad inválida.")
    if qty <= 0:
        raise HTTPException(status_code=422, detail="La cantidad debe ser mayor a cero.")
    return qty


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _role_allowed(role: str | None) -> bool:
    raw = _clean(role).lower().replace("-", "_").replace(" ", "_")
    return raw in ALLOWED_MATERIAL_ROLES


async def _enabled_module_codes(db: AsyncSession, company_id: UUID) -> set[str]:
    result = await db.execute(
        text("""
            SELECT lower(m.code) AS code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = :company_id
              AND cm.enabled IS TRUE
              AND m.is_active IS TRUE
        """),
        {"company_id": str(company_id)},
    )
    return {str(row[0]).lower() for row in result.all() if row[0]}


async def _employee_from_telegram(db: AsyncSession, company_id: UUID, telegram_user_id: str | None) -> dict[str, Any]:
    telegram_user_id = _clean(telegram_user_id)
    if not telegram_user_id:
        raise HTTPException(status_code=401, detail="No se recibió Telegram ID.")

    result = await db.execute(
        text("""
            SELECT id, company_id, full_name, role, telegram_user_id, status
            FROM employees
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND COALESCE(status, 'active') NOT IN ('archived', 'inactive')
            LIMIT 1
        """),
        {"company_id": str(company_id), "telegram_user_id": telegram_user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=403, detail="Empleado no vinculado a este Telegram ID.")
    employee = dict(row)
    if not _role_allowed(employee.get("role")):
        raise HTTPException(status_code=403, detail="Tu rol no tiene permiso para solicitar material.")
    return employee


async def _require_materials_inventory(db: AsyncSession, company_id: UUID) -> None:
    codes = await _enabled_module_codes(db, company_id)
    if "materials" not in codes or "inventory" not in codes:
        raise HTTPException(status_code=403, detail="Materiales e Inventario deben estar activos para esta empresa.")


def _item_out(row: dict[str, Any]) -> dict[str, Any]:
    name_reference = _clean(row.get("name_reference") or row.get("sku") or row.get("name") or row.get("reference"))
    item_size = _clean(row.get("item_size"))
    label = name_reference if not item_size else f"{name_reference} · {item_size}"
    return {
        "id": str(row.get("id")),
        "name_reference": name_reference,
        "item_size": item_size,
        "label": label,
    }


@router.get("/companies/{company_id}/inventory")
async def webapp_inventory_search(
    company_id: UUID,
    q: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)

    search = f"%{_clean(q).lower()}%"
    params: dict[str, Any] = {
        "company_id": str(company_id),
        "limit": limit,
        "offset": offset,
        "search": search,
    }

    where_search = ""
    if _clean(q):
        where_search = """
          AND (
            lower(COALESCE(name_reference, '')) LIKE :search
            OR lower(COALESCE(item_size, '')) LIKE :search
            OR lower(COALESCE(sku, '')) LIKE :search
            OR lower(COALESCE(name, '')) LIKE :search
            OR lower(COALESCE(reference, '')) LIKE :search
          )
        """

    count_result = await db.execute(
        text(f"""
            SELECT COUNT(*)
            FROM inventory_items
            WHERE company_id = :company_id
              AND COALESCE(status, 'active') = 'active'
              AND COALESCE(current_stock, stock_actual, stock, 0) > 0
              {where_search}
        """),
        params,
    )
    total = int(count_result.scalar() or 0)

    result = await db.execute(
        text(f"""
            SELECT id, name_reference, item_size, sku, name, reference
            FROM inventory_items
            WHERE company_id = :company_id
              AND COALESCE(status, 'active') = 'active'
              AND COALESCE(current_stock, stock_actual, stock, 0) > 0
              {where_search}
            ORDER BY lower(COALESCE(name_reference, sku, name, reference, '')) ASC, item_size ASC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    items = [_item_out(dict(row)) for row in result.mappings().all()]
    return {
        "company_id": str(company_id),
        "query": q or "",
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


@router.post("/companies/{company_id}/orders")
async def webapp_create_material_order(
    company_id: UUID,
    payload: WebAppOrderCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)
    await _require_materials_inventory(db, company_id)

    employee = await _employee_from_telegram(db, company_id, payload.telegram_user_id)

    if not payload.items:
        raise HTTPException(status_code=422, detail="El carrito está vacío.")

    normalized: list[dict[str, Any]] = []
    for raw in payload.items:
        item_id = _clean(raw.inventory_item_id)
        qty = _to_decimal(raw.quantity)

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
        item = result.mappings().first()
        if not item:
            raise HTTPException(status_code=422, detail="Uno de los materiales no existe o está inactivo.")

        item_dict = dict(item)
        stock = _to_decimal(item_dict.get("current_stock") or item_dict.get("stock_actual") or item_dict.get("stock") or 0)
        if stock < qty:
            label = _item_out(item_dict)["label"]
            raise HTTPException(status_code=409, detail=f"Stock insuficiente para {label}.")

        normalized.append({
            "item": item_dict,
            "quantity": qty,
        })

    order_number = await _generate_order_number(db, company_id)
    source_batch = f"telegram_webapp:{payload.telegram_user_id or 'unknown'}:{uuid4()}"

    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(normalized, start=1):
        item = entry["item"]
        qty = entry["quantity"]
        label = _item_out(item)
        request_id = str(uuid4())

        result = await db.execute(
            text("""
                INSERT INTO material_requests (
                    id,
                    company_id,
                    employee_id,
                    employee_name,
                    employee_role,
                    inventory_item_id,
                    material_name,
                    quantity,
                    unit,
                    notes,
                    status,
                    source_channel,
                    source_ref,
                    requested_at,
                    status_updated_at,
                    created_at,
                    updated_at,
                    order_number
                )
                VALUES (
                    :id,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :employee_role,
                    :inventory_item_id,
                    :material_name,
                    :quantity,
                    NULL,
                    :notes,
                    'pending',
                    'telegram_webapp',
                    :source_ref,
                    now(),
                    now(),
                    now(),
                    now(),
                    :order_number
                )
                RETURNING *
            """),
            {
                "id": request_id,
                "company_id": str(company_id),
                "employee_id": str(employee["id"]),
                "employee_name": employee.get("full_name") or "",
                "employee_role": employee.get("role") or "",
                "inventory_item_id": str(item["id"]),
                "material_name": label["name_reference"],
                "quantity": qty,
                "notes": _clean(payload.notes) or "Solicitud desde Telegram Web App",
                "source_ref": f"{source_batch}:line:{index}",
                "order_number": order_number,
            },
        )
        rows.append(dict(result.mappings().first()))

    await db.commit()

    return {
        "ok": True,
        "company_id": str(company_id),
        "order_number": order_number,
        "requests": [material_request_out(row) for row in rows],
    }
