from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import logging
from typing import Any
from urllib.parse import parse_qsl
from uuid import UUID, uuid4

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.materials import ensure_materials_storage, _generate_order_number, material_request_out
from app.api.v1.endpoints.bots import decrypt_token

router = APIRouter()
logger = logging.getLogger("clonexa.materials_webapp")

ALLOWED_MATERIAL_ROLES = {"admin", "admin_empresa", "supervisor", "inventario", "inventory"}


class WebAppCartItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inventory_item_id: str
    quantity: int | float | str


class WebAppContextIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    init_data: str | None = None
    telegram_user_id: str | None = None
    telegram_username: str | None = None


class WebAppOrderCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    init_data: str | None = None
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


async def _company_bot_token(db: AsyncSession, company_id: UUID) -> str:
    result = await db.execute(
        text("""
            SELECT bot_token_encrypted
            FROM company_bot_instances
            WHERE company_id = :company_id
              AND channel = 'telegram'
              AND bot_token_encrypted IS NOT NULL
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
        """),
        {"company_id": str(company_id)},
    )
    encrypted = result.scalar()
    if not encrypted:
        raise HTTPException(status_code=403, detail="La empresa no tiene bot Telegram configurado.")
    token = decrypt_token(str(encrypted))
    if not token:
        raise HTTPException(status_code=403, detail="No fue posible validar el bot Telegram.")
    return token


def _validate_telegram_init_data(init_data: str | None, bot_token: str) -> dict[str, Any]:
    raw = _clean(init_data)
    if not raw:
        raise HTTPException(status_code=401, detail="Web App no validada por Telegram.")

    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Firma Telegram ausente.")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Firma Telegram inválida.")

    try:
        user = json.loads(pairs.get("user") or "{}")
    except json.JSONDecodeError:
        user = {}

    telegram_user_id = str(user.get("id") or "").strip()
    if not telegram_user_id:
        raise HTTPException(status_code=401, detail="Telegram ID no disponible.")

    return {
        "telegram_user_id": telegram_user_id,
        "telegram_username": str(user.get("username") or "").strip(),
        "telegram_first_name": str(user.get("first_name") or "").strip(),
        "auth_date": pairs.get("auth_date"),
    }


async def _authorize_webapp_user(
    db: AsyncSession,
    company_id: UUID,
    init_data: str | None,
) -> dict[str, Any]:
    await _require_materials_inventory(db, company_id)
    bot_token = await _company_bot_token(db, company_id)
    telegram_user = _validate_telegram_init_data(init_data, bot_token)
    employee = await _employee_from_telegram(db, company_id, telegram_user["telegram_user_id"])
    return {
        "bot_token": bot_token,
        "telegram_user": telegram_user,
        "employee": employee,
    }


async def _send_telegram_order_confirmation(
    *,
    token: str,
    telegram_user_id: str,
    order_number: str,
) -> None:
    try:
        text_message = (
            "✅ Solicitud de material creada\n"
            f"Orden: {order_number}\n"
            "Queda pendiente en Materiales."
        )
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": telegram_user_id, "text": text_message},
            )
    except Exception as exc:  # No bloquear la orden si Telegram falla.
        logger.warning("No se pudo enviar confirmación Telegram de orden %s: %s", order_number, exc)


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



@router.post("/companies/{company_id}/context")
async def webapp_context(
    company_id: UUID,
    payload: WebAppContextIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)
    auth = await _authorize_webapp_user(db, company_id, payload.init_data)
    employee = auth["employee"]
    telegram_user = auth["telegram_user"]
    return {
        "ok": True,
        "company_id": str(company_id),
        "telegram_user_id": telegram_user["telegram_user_id"],
        "telegram_username": telegram_user.get("telegram_username") or "",
        "employee": {
            "id": str(employee.get("id")),
            "full_name": employee.get("full_name") or "",
            "role": employee.get("role") or "",
        },
        "allowed": True,
    }


@router.get("/companies/{company_id}/inventory")
async def webapp_inventory_search(
    company_id: UUID,
    request: Request,
    q: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)
    await _authorize_webapp_user(db, company_id, request.headers.get("x-telegram-init-data"))

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

    auth = await _authorize_webapp_user(db, company_id, payload.init_data)
    employee = auth["employee"]
    telegram_user = auth["telegram_user"]
    telegram_user_id = telegram_user["telegram_user_id"]

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
    source_batch = f"telegram_webapp:{telegram_user_id}:{uuid4()}"

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

    await _send_telegram_order_confirmation(
        token=auth["bot_token"],
        telegram_user_id=telegram_user_id,
        order_number=order_number,
    )

    return {
        "ok": True,
        "company_id": str(company_id),
        "order_number": order_number,
        "requests": [material_request_out(row) for row in rows],
    }
