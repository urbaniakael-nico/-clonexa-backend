"""Domicilios por WhatsApp (module "domicilios_whatsapp", off by default).

Flow: the customer writes to the company's CUSTOMER WhatsApp line -> the bot
answers with a personal link (app/services/whatsapp_delivery.py) -> the
public carta (/domicilio) shows the same menu as the mesero/caja panels,
only products with stock -> the order is created through hospitality's own
create_hospitality_order (server-side prices, inventory deduction, kitchen,
caja) as order_type "domicilio" with metadata.delivery.

Auth:
  - /domicilios/public/...: no login; the link code is the credential
    (single use, 30 minutes, bound to the phone that wrote), like the QR
    table key.
  - configuration: Admin V2 or an admin/owner of the company.
  - caja actions (verify payment, send to the domiciliario, "salio"): Admin
    V2, an admin/owner, or the company's caja user (from the local network).
  Every endpoint 404s when the module is off for that company.

Pago por QR: the customer sends the receipt photo to the WhatsApp chat (it is
not stored here); the order stays "por_verificar" until the caja confirms
the money in the bank -- a receipt can be faked -- and until then it can be
neither dispatched nor closed.

WARNING: automating WhatsApp Web is against WhatsApp's terms and the number
can be banned. Use a dedicated number, never the business's main one.
"""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_company_user_for_tenant
from app.api.v1.endpoints.companies import COMPANY_ADMIN_ROLES
from app.api.v1.endpoints.hospitality import (
    HospitalityOrderCreateIn,
    HospitalityOrderItemIn,
    _fetch_order,
    create_hospitality_order,
)
from app.api.v1.endpoints.waiter_ordering import WaiterOrderItemIn, _client_ip, _priced_order_items, build_waiter_menu
from app.services import media_storage, whatsapp_delivery as wd
from app.services.access_sessions import ip_allowed_for_scope
from app.services.shoplink_whatsapp_web import whatsapp_send, whatsapp_status

router = APIRouter()
logger = logging.getLogger("clonexa.domicilios")

CAJA_ROLES = {"caja"}
MAX_QR_UPLOAD_BYTES = 8 * 1024 * 1024
HOSPITALITY_PAYMENT = {"cash": "cash", "card": "card", "qr": "transfer"}


# ------------------------------------------------------------------ auth ---
async def _module_or_404(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    settings = await wd.module_settings(db, company_id)
    if settings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="funcion_no_habilitada")
    return settings


async def _actor(
    company_id: uuid.UUID, request: Request, authorization: str | None, db: AsyncSession, roles: set[str],
) -> dict[str, Any]:
    from app.web.admin_v2_routes import _active_session as admin_v2_session_active

    # Session first: an anonymous caller learns nothing, not even whether the
    # company has the module.
    if await admin_v2_session_active(request, db):
        return {"name": "Admin V2", "settings": await _module_or_404(db, company_id)}
    user = await require_company_user_for_tenant(db, authorization, company_id, allowed_roles=roles)
    settings = await _module_or_404(db, company_id)
    # The caja mini panel only works from the restaurant's network, as in
    # waiter_ordering.
    if str(getattr(user, "role", "")).strip().lower() in CAJA_ROLES:
        if not await ip_allowed_for_scope(db, company_id, "mini_panel", _client_ip(request)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conectate al WiFi del restaurante.")
    name = str(getattr(user, "full_name", "") or getattr(user, "email", "") or "Caja")[:160]
    return {"name": name, "settings": settings}


async def require_delivery_admin(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _actor(company_id, request, authorization, db, COMPANY_ADMIN_ROLES)


async def require_delivery_caja(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _actor(company_id, request, authorization, db, CAJA_ROLES | COMPANY_ADMIN_ROLES)


# -------------------------------------------------------------- settings ---
class ScheduleSlotIn(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str = Field(alias="from", max_length=5)
    to: str = Field(max_length=5)


class DeliverySettingsIn(BaseModel):
    schedule: dict[str, list[ScheduleSlotIn]] = Field(default_factory=dict)
    delivery_fee: float = Field(default=0, ge=0, le=1_000_000)
    eta_minutes: int = Field(default=45, ge=5, le=240)
    greeting_message: str = Field(default="", max_length=900)
    closed_message: str = Field(default="", max_length=900)
    driver_role: str = Field(default="domiciliario", max_length=60)


async def _qr_exists(db: AsyncSession, company_id: uuid.UUID) -> bool:
    result = await db.execute(
        text("SELECT 1 FROM whatsapp_delivery_payment_qr WHERE company_id = :company_id AND image_bytes IS NOT NULL"),
        {"company_id": str(company_id)},
    )
    return result.first() is not None


def _settings_out(settings: dict[str, Any], has_qr: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "settings": settings,
        "has_payment_qr": has_qr,
        "schedule_text": wd.schedule_text(settings["schedule"]),
        "warning": (
            "Automatizar WhatsApp Web no esta permitido por WhatsApp y el numero puede ser suspendido. "
            "Usa un numero dedicado, distinto al principal del local."
        ),
    }


@router.get("/companies/{company_id}/settings")
async def get_delivery_settings(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: dict[str, Any] = Depends(require_delivery_admin),
) -> dict[str, Any]:
    return _settings_out(actor["settings"], await _qr_exists(db, company_id))


@router.put("/companies/{company_id}/settings")
async def save_delivery_settings(
    company_id: uuid.UUID,
    payload: DeliverySettingsIn,
    db: AsyncSession = Depends(get_db),
    actor: dict[str, Any] = Depends(require_delivery_admin),
) -> dict[str, Any]:
    raw = payload.model_dump()
    raw["schedule"] = {
        day: [{"from": slot.from_, "to": slot.to} for slot in slots]
        for day, slots in payload.schedule.items()
    }
    settings = wd.normalize_settings({**actor["settings"], **raw})
    await db.execute(
        text(
            """
            UPDATE company_modules cm
            SET settings = COALESCE(cm.settings, '{}'::jsonb) || CAST(:settings AS jsonb), updated_at = NOW()
            FROM modules m
            WHERE m.id = cm.module_id AND m.code = :code AND cm.company_id = :company_id
            """
        ),
        {"company_id": str(company_id), "code": wd.MODULE_CODE, "settings": _json(settings)},
    )
    await db.commit()
    return _settings_out(settings, await _qr_exists(db, company_id))


@router.post("/companies/{company_id}/payment-qr")
async def upload_delivery_payment_qr(
    company_id: uuid.UUID,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _actor_: dict[str, Any] = Depends(require_delivery_admin),
) -> dict[str, Any]:
    # One image per company (<= 800 px / 200 KB after media_storage).
    content = await image.read(MAX_QR_UPLOAD_BYTES + 1)
    if len(content) > MAX_QR_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="La imagen pesa mas de 8 MB.")
    await db.execute(
        text("INSERT INTO whatsapp_delivery_payment_qr (company_id) VALUES (:company_id) ON CONFLICT (company_id) DO NOTHING"),
        {"company_id": str(company_id)},
    )
    await media_storage.save_image(
        db,
        table="whatsapp_delivery_payment_qr",
        key_columns={"company_id": str(company_id)},
        raw=content,
        content_type=(image.content_type or "").lower(),
    )
    await db.commit()
    return {"ok": True, "has_payment_qr": True}


async def _qr_response(db: AsyncSession, company_id: uuid.UUID) -> Response:
    found = await media_storage.get_image(
        db, table="whatsapp_delivery_payment_qr", key_columns={"company_id": str(company_id)},
    )
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sin_qr")
    content, content_type = found
    return Response(content=content, media_type=content_type, headers={"Cache-Control": "no-store"})


@router.get("/companies/{company_id}/payment-qr")
async def get_delivery_payment_qr(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _actor_: dict[str, Any] = Depends(require_delivery_admin),
) -> Response:
    return await _qr_response(db, company_id)


# ------------------------------------------------------------ public carta ---
async def _whatsapp_number(company_id: uuid.UUID) -> str:
    try:
        current = await whatsapp_status(str(company_id), "clientes")
    except Exception:
        return ""
    return str(current.get("connected_phone") or "") if current.get("status") == "connected" else ""


async def _public_session(db: AsyncSession, company_id: uuid.UUID, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = await _module_or_404(db, company_id)
    session = await wd.valid_session(db, company_id, token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace ya vencio o ya se uso. Escribenos de nuevo por WhatsApp para recibir uno nuevo.",
        )
    return settings, session


@router.get("/public/{company_id}")
async def public_delivery_carta(
    company_id: uuid.UUID,
    s: str = Query(default="", max_length=64),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    settings, session = await _public_session(db, company_id, s)
    company = await wd.company_brief(db, company_id)
    menu = await build_waiter_menu(db, company_id)
    return {
        "ok": True,
        "company_name": company["name"],
        "categories": menu["categories"],
        "quantity_buttons": menu["quantity_buttons"],
        "menu_emojis": menu["menu_emojis"],
        "delivery_fee": settings["delivery_fee"],
        "eta_minutes": settings["eta_minutes"],
        "has_payment_qr": await _qr_exists(db, company_id),
        "expires_at": session["expires_at"].isoformat() if session.get("expires_at") else "",
        "phone_hint": f"***{wd.display_phone(session['phone'])[-4:]}" if wd.display_phone(session["phone"]) else "",
        "whatsapp_location": bool(session.get("location")),
        "whatsapp_number": await _whatsapp_number(company_id),
    }


@router.get("/public/{company_id}/payment-qr")
async def public_delivery_payment_qr(
    company_id: uuid.UUID,
    s: str = Query(default="", max_length=64),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _public_session(db, company_id, s)
    return await _qr_response(db, company_id)


class DeliveryOrderIn(BaseModel):
    s: str = Field(..., min_length=10, max_length=64)
    customer_name: str = Field(..., min_length=2, max_length=120)
    address: str = Field(..., min_length=5, max_length=240)
    address_notes: str = Field(default="", max_length=240)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    payment_method: Literal["cash", "card", "qr"]
    pays_with: float | None = Field(default=None, ge=0, le=10_000_000)
    notes: str = Field(default="", max_length=500)
    items: list[WaiterOrderItemIn] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def clean_items(cls, value: list[WaiterOrderItemIn]) -> list[WaiterOrderItemIn]:
        rows = [item for item in (value or []) if str(item.inventory_item_id or "").strip() and item.quantity > 0]
        if not rows:
            raise ValueError("Agrega al menos un producto.")
        return rows[:80]


def _line_total(item: HospitalityOrderItemIn) -> float:
    if item.line_total is not None:
        return round(float(item.line_total), 2)
    return round(float(item.quantity) * float(item.unit_price), 2)


@router.post("/public/{company_id}/orders", status_code=status.HTTP_201_CREATED)
async def public_create_delivery_order(
    company_id: uuid.UUID,
    payload: DeliveryOrderIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    settings, session = await _public_session(db, company_id, payload.s)
    company = await wd.company_brief(db, company_id)
    if not wd.is_open(settings["schedule"], wd.local_now(company["timezone"])):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="En este momento no tenemos servicio a domicilio.")

    # Prices, names and stations always from the server's catalog.
    items = await _priced_order_items(db, company_id, payload.items)
    fee = float(settings["delivery_fee"])
    if fee > 0:
        items.append(HospitalityOrderItemIn(name="Valor domicilio", quantity=1, unit_price=fee, station="domicilio", ready=True))
    total = round(sum(_line_total(item) for item in items), 2)

    pays_with = change = None
    if payload.payment_method == "cash" and payload.pays_with:
        if payload.pays_with < total:
            raise HTTPException(status_code=422, detail=f"El valor con el que pagas es menor al total ({wd.money(total)}).")
        pays_with, change = round(payload.pays_with), round(payload.pays_with - total)

    # Claim the link first (atomic): a double tap or a replay can never
    # create two orders; if anything below fails, the claim rolls back.
    claimed = await db.execute(
        text(
            """
            UPDATE whatsapp_delivery_sessions SET used_at = NOW()
            WHERE id = :id AND company_id = :company_id AND used_at IS NULL AND expires_at > NOW()
            RETURNING id
            """
        ),
        {"id": str(session["id"]), "company_id": str(company_id)},
    )
    if claimed.first() is None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Este enlace ya se uso.")

    location = None
    if payload.latitude is not None and payload.longitude is not None:
        location = wd.maps_url(payload.latitude, payload.longitude)
    customer_name = wd.clean(payload.customer_name, 120)
    delivery = {
        "customer_name": customer_name,
        "customer_phone": session["phone"],
        "address": wd.clean(payload.address, 240),
        "address_notes": wd.clean(payload.address_notes, 240),
        "location_url": location or "",
        "whatsapp_location": session.get("location") or None,
        "payment_method": payload.payment_method,
        "payment_status": "por_verificar" if payload.payment_method == "qr" else "contra_entrega",
        "pays_with": pays_with,
        "change": change,
        "fee": fee,
        "eta_minutes": settings["eta_minutes"],
        "session_id": str(session["id"]),
        "driver": None,
        "assignments": [],
        "notified": {},
    }
    created = await create_hospitality_order(
        company_id,
        HospitalityOrderCreateIn(
            table=f"Domicilio {secrets.token_hex(2).upper()}",
            customer=customer_name,
            source="domicilio",
            payment_method=HOSPITALITY_PAYMENT[payload.payment_method],
            notes=wd.clean(payload.notes, 500),
            items=items,
        ),
        db,
        delivery=delivery,
    )
    order = created["order"]
    await db.execute(
        text("UPDATE whatsapp_delivery_sessions SET order_id = :order_id WHERE id = :id AND company_id = :company_id"),
        {"order_id": str(order["id"]), "id": str(session["id"]), "company_id": str(company_id)},
    )
    await db.commit()

    delivery = (order.get("metadata") or {}).get("delivery") or delivery
    sent = await _notify(company_id, session["phone"], wd.confirmation_message(company["name"], order, delivery))
    if sent:
        order = await _patch_delivery(db, company_id, uuid.UUID(str(order["id"])), lambda d: d["notified"].update(confirmed=_now_iso()))
    return {
        "ok": True,
        "order_number": order.get("order_number"),
        "total": order.get("total"),
        "eta_minutes": settings["eta_minutes"],
        "payment_status": delivery["payment_status"],
    }


# ------------------------------------------------------------------ caja ---
def _now_iso() -> str:
    return wd.now_utc().isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


async def _notify(company_id: uuid.UUID, phone: str, message: str) -> bool:
    """One WhatsApp message on the customer line; never breaks the flow."""
    if not phone:
        return False
    try:
        result = await whatsapp_send(str(company_id), phone, message, "clientes")
    except Exception as exc:  # bridge down: the order still stands
        logger.warning("domicilios whatsapp send failed: %s", exc)
        return False
    return bool(result.get("ok"))


async def _patch_delivery(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID, mutate) -> dict[str, Any]:
    result = await db.execute(
        text("SELECT metadata FROM hospitality_orders WHERE id = :order_id AND company_id = :company_id FOR UPDATE"),
        {"order_id": str(order_id), "company_id": str(company_id)},
    )
    row = result.mappings().first()
    metadata = (row or {}).get("metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    delivery = metadata.get("delivery")
    if not isinstance(delivery, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="domicilio_no_encontrado")
    delivery.setdefault("notified", {})
    delivery.setdefault("assignments", [])
    mutate(delivery)
    await db.execute(
        text(
            """
            UPDATE hospitality_orders
            SET metadata = jsonb_set(metadata, '{delivery}', CAST(:delivery AS jsonb), true), updated_at = NOW()
            WHERE id = :order_id AND company_id = :company_id
            """
        ),
        {"order_id": str(order_id), "company_id": str(company_id), "delivery": _json(delivery)},
    )
    await db.commit()
    return await _fetch_order(db, company_id, order_id)


async def _open_delivery(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID) -> tuple[dict[str, Any], dict[str, Any]]:
    order = await _fetch_order(db, company_id, order_id)
    delivery = (order.get("metadata") or {}).get("delivery")
    if not isinstance(delivery, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="domicilio_no_encontrado")
    if str(order.get("status") or "") in {"cerrado", "cancelado"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El domicilio ya esta cerrado.")
    return order, delivery


async def _drivers(db: AsyncSession, company_id: uuid.UUID, role: str) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT id, full_name, phone FROM employees
            WHERE company_id = :company_id AND status = 'active'
              AND lower(COALESCE(role, '')) = :role AND COALESCE(phone, '') <> ''
            ORDER BY full_name
            """
        ),
        {"company_id": str(company_id), "role": role},
    )
    return [
        {"employee_id": str(row["id"]), "name": row["full_name"] or "Domiciliario", "phone": wd.normalize_phone(row["phone"])}
        for row in result.mappings().all()
    ]


@router.get("/companies/{company_id}/drivers")
async def list_delivery_drivers(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: dict[str, Any] = Depends(require_delivery_caja),
) -> dict[str, Any]:
    return {"ok": True, "drivers": await _drivers(db, company_id, actor["settings"]["driver_role"])}


@router.post("/companies/{company_id}/orders/{order_id}/verify-payment")
async def verify_delivery_payment(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: dict[str, Any] = Depends(require_delivery_caja),
) -> dict[str, Any]:
    """Only the caja (or an admin) confirms a QR payment, after seeing the
    money in the bank account -- the receipt photo alone proves nothing."""
    _, delivery = await _open_delivery(db, company_id, order_id)
    if delivery.get("payment_status") != "por_verificar":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este domicilio no tiene un pago por verificar.")

    def mutate(d: dict[str, Any]) -> None:
        d["payment_status"] = "verificado"
        d["payment_verified_by"] = actor["name"]
        d["payment_verified_at"] = _now_iso()

    return {"ok": True, "order": await _patch_delivery(db, company_id, order_id, mutate)}


class AssignDriverIn(BaseModel):
    employee_id: uuid.UUID


@router.post("/companies/{company_id}/orders/{order_id}/assign")
async def assign_delivery_driver(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: AssignDriverIn,
    db: AsyncSession = Depends(get_db),
    actor: dict[str, Any] = Depends(require_delivery_caja),
) -> dict[str, Any]:
    order, delivery = await _open_delivery(db, company_id, order_id)
    driver = next(
        (d for d in await _drivers(db, company_id, actor["settings"]["driver_role"]) if d["employee_id"] == str(payload.employee_id)),
        None,
    )
    if driver is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domiciliario no encontrado en Workforce.")
    company = await wd.company_brief(db, company_id)
    sent = await _notify(company_id, driver["phone"], wd.driver_message(company["name"], order, delivery))
    record = {
        **driver,
        "assigned_at": _now_iso(),
        "assigned_by": actor["name"],
        "whatsapp_sent": sent,
    }

    def mutate(d: dict[str, Any]) -> None:
        d["driver"] = record
        d["assignments"] = [*(d.get("assignments") or []), record][-10:]

    saved = await _patch_delivery(db, company_id, order_id, mutate)
    return {
        "ok": True,
        "order": saved,
        "whatsapp_sent": sent,
        "detail": "" if sent else "Quedo asignado, pero no se pudo enviar por WhatsApp. Revisa el numero de clientes.",
    }


@router.post("/companies/{company_id}/orders/{order_id}/dispatched")
async def mark_delivery_dispatched(
    company_id: uuid.UUID,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: dict[str, Any] = Depends(require_delivery_caja),
) -> dict[str, Any]:
    order, delivery = await _open_delivery(db, company_id, order_id)
    if delivery.get("payment_status") == "por_verificar":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Confirma el pago por QR antes de despachar.")
    if not delivery.get("driver"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asigna un domiciliario antes de despachar.")
    if (delivery.get("notified") or {}).get("dispatched"):
        return {"ok": True, "order": order, "already_notified": True}
    company = await wd.company_brief(db, company_id)
    sent = await _notify(company_id, delivery.get("customer_phone") or "", wd.dispatched_message(company["name"], order, delivery))

    def mutate(d: dict[str, Any]) -> None:
        d["dispatched_at"] = _now_iso()
        d["dispatched_by"] = actor["name"]
        if sent:
            d["notified"]["dispatched"] = _now_iso()

    return {"ok": True, "order": await _patch_delivery(db, company_id, order_id, mutate), "whatsapp_sent": sent}
