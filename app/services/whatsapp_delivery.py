"""Domicilios por WhatsApp: horario, sesiones de link y textos al cliente.

Module "domicilios_whatsapp" (off for every company by default). The bot
never takes the order by chat: when a customer writes to the company's
CUSTOMER line (see whatsapp_customer_line.py) it answers once with a
personal link to the delivery carta -- or, out of hours, with the schedule.

The link carries a random code bound to that phone: single use, expires in
30 minutes, and only its sha256 is stored. The public carta endpoints
accept nothing else as credentials (same idea as the QR table key).

This module is imported by the customer line, so -- like it -- it must never
import nomina, CRM, produccion, Workforce or the internal agent.

WARNING: automating WhatsApp Web is against WhatsApp's terms and the number
can be banned. Use a dedicated number, never the business's main one.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MODULE_CODE = "domicilios_whatsapp"
LINK_MINUTES = 30
# One answer per burst of messages: a customer who writes "hola", "buenas",
# "quiero pedir" gets one link, not three.
LINK_COOLDOWN_SECONDS = 90
CLOSED_COOLDOWN_SECONDS = 600

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_LABELS = {
    "mon": "Lunes", "tue": "Martes", "wed": "Miercoles", "thu": "Jueves",
    "fri": "Viernes", "sat": "Sabado", "sun": "Domingo",
}
PAYMENT_LABELS = {"cash": "Efectivo contra entrega", "card": "Datafono contra entrega", "qr": "Pago por QR"}

DEFAULT_GREETING = (
    "Hola{nombre}! Bienvenido a {empresa}. Haz tu pedido a domicilio aqui:\n{link}\n"
    "El enlace es personal y vence en 30 minutos."
)
DEFAULT_CLOSED = (
    "Hola{nombre}. En este momento no tenemos servicio a domicilio.\n"
    "Nuestro horario de atencion es:\n{horario}"
)
DEFAULT_SETTINGS: dict[str, Any] = {
    "schedule": {day: [] for day in DAYS},
    "delivery_fee": 0,
    "eta_minutes": 45,
    "greeting_message": DEFAULT_GREETING,
    "closed_message": DEFAULT_CLOSED,
    "driver_role": "domiciliario",
    "public_base_url": "",
}

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def normalize_phone(value: Any) -> str:
    """Same rules as bridge.mjs normalizePhone (Colombian mobiles get 57)."""
    phone = re.sub(r"\D", "", str(value or ""))
    if phone.startswith("00"):
        phone = phone[2:]
    if len(phone) == 10 and phone.startswith("3"):
        phone = f"57{phone}"
    return phone


def contact_key(from_phone: Any, from_jid: Any = "") -> str:
    """Where to write back to a customer: their phone, or -- for newer
    chats that arrive as "<id>@lid" with no phone -- that chat id (the
    bridge can send to it). "" when there is neither."""
    phone = normalize_phone(from_phone)
    if len(phone) >= 7:
        return phone
    jid = str(from_jid or "").strip()
    return jid if re.fullmatch(r"\d{5,30}@lid", jid) else ""


def display_phone(contact: Any) -> str:
    """A contact key shown to people: the phone, never a raw chat id."""
    value = str(contact or "")
    return value if value.isdigit() else ""


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


# ------------------------------------------------------------- settings ---
def _clean_slots(raw: Any) -> list[dict[str, str]]:
    slots = []
    for slot in raw if isinstance(raw, list) else []:
        if not isinstance(slot, dict):
            continue
        start, end = clean(slot.get("from"), 5), clean(slot.get("to"), 5)
        if _HHMM.match(start) and _HHMM.match(end) and start != end:
            slots.append({"from": start, "to": end})
    return slots[:4]


def normalize_settings(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    schedule_raw = data.get("schedule") if isinstance(data.get("schedule"), dict) else {}
    try:
        fee = max(0.0, min(1_000_000.0, float(data.get("delivery_fee") or 0)))
    except (TypeError, ValueError):
        fee = 0.0
    try:
        eta = int(float(data.get("eta_minutes") or DEFAULT_SETTINGS["eta_minutes"]))
    except (TypeError, ValueError):
        eta = DEFAULT_SETTINGS["eta_minutes"]
    base_url = clean(data.get("public_base_url"), 200).rstrip("/")
    return {
        "schedule": {day: _clean_slots(schedule_raw.get(day)) for day in DAYS},
        "delivery_fee": round(fee),
        "eta_minutes": max(5, min(240, eta)),
        "greeting_message": str(data.get("greeting_message") or DEFAULT_GREETING)[:900],
        "closed_message": str(data.get("closed_message") or DEFAULT_CLOSED)[:900],
        "driver_role": clean(data.get("driver_role") or "domiciliario", 60).lower(),
        "public_base_url": base_url if base_url.startswith(("http://", "https://")) else "",
    }


async def module_settings(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any] | None:
    """The module's settings when it is enabled for this company, else None."""
    result = await db.execute(
        text(
            """
            SELECT cm.settings
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = :company_id AND m.code = :code
              AND cm.enabled IS TRUE AND COALESCE(m.is_active, TRUE) IS TRUE
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "code": MODULE_CODE},
    )
    row = result.mappings().first()
    if row is None:
        return None
    settings = row["settings"]
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except ValueError:
            settings = {}
    return normalize_settings(settings)


async def company_brief(db: AsyncSession, company_id: uuid.UUID) -> dict[str, str]:
    result = await db.execute(
        text("SELECT name, timezone FROM companies WHERE id = :company_id"),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first() or {}
    return {"name": clean(row.get("name")) or "el restaurante", "timezone": row.get("timezone") or "America/Bogota"}


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "America/Bogota")
    except Exception:
        return ZoneInfo("America/Bogota")


# ------------------------------------------------------------- schedule ---
def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def is_open(schedule: dict[str, list[dict[str, str]]], now_local: datetime) -> bool:
    """Open at `now_local` (company time). A slot whose end is before its
    start runs past midnight (18:00-02:00 belongs to the day it started)."""
    today = DAYS[now_local.weekday()]
    yesterday = DAYS[(now_local.weekday() - 1) % 7]
    current = now_local.hour * 60 + now_local.minute
    for slot in schedule.get(today) or []:
        start, end = _minutes(slot["from"]), _minutes(slot["to"])
        if start < end and start <= current < end:
            return True
        if start > end and current >= start:
            return True
    for slot in schedule.get(yesterday) or []:
        start, end = _minutes(slot["from"]), _minutes(slot["to"])
        if start > end and current < end:
            return True
    return False


def schedule_text(schedule: dict[str, list[dict[str, str]]]) -> str:
    """'Lunes a Viernes: 11:00-15:00 y 18:00-22:00' grouping equal days."""
    lines: list[str] = []
    run: list[str] = []

    def slots_label(day: str) -> str:
        return " y ".join(f"{slot['from']}-{slot['to']}" for slot in schedule.get(day) or [])

    def flush() -> None:
        if not run:
            return
        label = slots_label(run[0])
        if label:
            days = DAY_LABELS[run[0]] if len(run) == 1 else f"{DAY_LABELS[run[0]]} a {DAY_LABELS[run[-1]]}"
            lines.append(f"{days}: {label}")
        run.clear()

    for day in DAYS:
        if run and slots_label(day) != slots_label(run[0]):
            flush()
        run.append(day)
    flush()
    return "\n".join(lines) or "Por ahora no tenemos horario de domicilios publicado."


def render_message(template: str, **values: str) -> str:
    out = str(template or "")
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out.strip()


# ------------------------------------------------------------- sessions ---
def public_base_url(settings: dict[str, Any]) -> str:
    return (
        settings.get("public_base_url")
        or os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        or "https://clonexa-backend-production.up.railway.app"
    )


async def _recent_session(db: AsyncSession, company_id: uuid.UUID, phone: str, kind: str, seconds: int) -> bool:
    result = await db.execute(
        text(
            """
            SELECT 1 FROM whatsapp_delivery_sessions
            WHERE company_id = :company_id AND phone = :phone AND kind = :kind
              AND created_at > NOW() - make_interval(secs => :seconds)
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "phone": phone, "kind": kind, "seconds": seconds},
    )
    return result.first() is not None


async def _insert_session(
    db: AsyncSession, company_id: uuid.UUID, phone: str, kind: str, token: str, minutes: int,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO whatsapp_delivery_sessions (company_id, phone, kind, token_hash, expires_at)
            VALUES (:company_id, :phone, :kind, :token_hash, NOW() + make_interval(mins => :minutes))
            """
        ),
        {"company_id": str(company_id), "phone": phone, "kind": kind, "token_hash": token_hash(token), "minutes": minutes},
    )


async def customer_reply(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    from_phone: str,
    from_jid: str = "",
    push_name: str = "",
    now: datetime | None = None,
) -> str:
    """What the customer line answers to a text: the personal link, the
    out-of-hours message, or "" (module off, or already answered)."""
    settings = await module_settings(db, company_id)
    if settings is None:
        return ""
    phone = contact_key(from_phone, from_jid)
    if not phone:
        return ""
    company = await company_brief(db, company_id)
    now_local = (now or datetime.now(timezone.utc)).astimezone(_zone(company["timezone"]))
    name = clean(push_name, 40)
    values = {"nombre": f" {name}" if name else "", "empresa": company["name"], "horario": schedule_text(settings["schedule"])}

    if not is_open(settings["schedule"], now_local):
        if await _recent_session(db, company_id, phone, "closed", CLOSED_COOLDOWN_SECONDS):
            return ""
        await _insert_session(db, company_id, phone, "closed", secrets.token_urlsafe(16), 0)
        await db.commit()
        message = render_message(settings["closed_message"], **values)
        return message if values["horario"] in message else f"{message}\n{values['horario']}"

    if await _recent_session(db, company_id, phone, "link", LINK_COOLDOWN_SECONDS):
        return ""
    token = secrets.token_urlsafe(18)
    await _insert_session(db, company_id, phone, "link", token, LINK_MINUTES)
    await db.commit()
    link = f"{public_base_url(settings)}/domicilio?c={company_id}&s={token}"
    message = render_message(settings["greeting_message"], link=link, **values)
    return message if link in message else f"{message}\n{link}"


async def valid_session(db: AsyncSession, company_id: uuid.UUID, token: str, *, lock: bool = False) -> dict[str, Any] | None:
    """The unexpired, unused link session for this code, or None."""
    if not token or len(token) > 64:
        return None
    result = await db.execute(
        text(
            f"""
            SELECT id, phone, expires_at, location
            FROM whatsapp_delivery_sessions
            WHERE company_id = :company_id AND token_hash = :token_hash AND kind = 'link'
              AND used_at IS NULL AND expires_at > NOW()
            LIMIT 1 {"FOR UPDATE" if lock else ""}
            """
        ),
        {"company_id": str(company_id), "token_hash": token_hash(token)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def save_whatsapp_location(
    db: AsyncSession, company_id: uuid.UUID, phone: str, latitude: float, longitude: float, from_jid: str = "",
) -> dict[str, Any] | None:
    """A location the customer shared in the chat: kept on their latest link
    (and on its order, if already placed). Returns what it was attached to."""
    phone = contact_key(phone, from_jid)
    if not phone:
        return None
    location = {"latitude": latitude, "longitude": longitude, "url": maps_url(latitude, longitude)}
    result = await db.execute(
        text(
            """
            UPDATE whatsapp_delivery_sessions
            SET location = CAST(:location AS jsonb)
            WHERE id = (
                SELECT id FROM whatsapp_delivery_sessions
                WHERE company_id = :company_id AND phone = :phone AND kind = 'link'
                  AND created_at > NOW() - INTERVAL '3 hours'
                ORDER BY created_at DESC LIMIT 1
            )
            RETURNING id, order_id
            """
        ),
        {"company_id": str(company_id), "phone": phone, "location": json.dumps(location)},
    )
    row = result.mappings().first()
    if row is None:
        return None
    if row["order_id"]:
        await db.execute(
            text(
                """
                UPDATE hospitality_orders
                SET metadata = jsonb_set(metadata, '{delivery,whatsapp_location}', CAST(:location AS jsonb), true),
                    updated_at = NOW()
                WHERE id = :order_id AND company_id = :company_id AND metadata ? 'delivery'
                """
            ),
            {"order_id": str(row["order_id"]), "company_id": str(company_id), "location": json.dumps(location)},
        )
    await db.commit()
    return {"session_id": str(row["id"]), "order_id": str(row["order_id"] or "")}


def maps_url(latitude: float, longitude: float) -> str:
    return f"https://maps.google.com/?q={latitude:.6f},{longitude:.6f}"


# -------------------------------------------------------------- messages ---
def money(value: Any) -> str:
    try:
        amount = round(float(value or 0))
    except (TypeError, ValueError):
        amount = 0
    return "$" + f"{amount:,}".replace(",", ".")


def _items_lines(items: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in items or []:
        if item.get("station") == "domicilio":
            continue
        qty = item.get("quantity_label") or f"{float(item.get('quantity') or 0):g}"
        line = f"- {qty} x {item.get('name') or 'Producto'}"
        extras = [item.get("term") or "", *(item.get("quick_notes") or []), item.get("observations") or ""]
        extras = [clean(extra, 120) for extra in extras if clean(extra)]
        if extras:
            line += f" ({'; '.join(extras)})"
        lines.append(line)
    return lines


def payment_line(delivery: dict[str, Any]) -> str:
    method = delivery.get("payment_method")
    if method == "qr":
        if delivery.get("payment_status") == "verificado":
            return "Pago por QR: CONFIRMADO por caja. No cobrar."
        return "Pago por QR: POR VERIFICAR en caja (comprobante sin confirmar)."
    label = PAYMENT_LABELS.get(method, "Contra entrega")
    line = f"{label}: COBRAR {money(delivery.get('total'))}"
    if method == "cash" and delivery.get("pays_with"):
        line += f" - paga con {money(delivery['pays_with'])}, cambio {money(delivery.get('change'))}"
    return line


def confirmation_message(company_name: str, order: dict[str, Any], delivery: dict[str, Any]) -> str:
    lines = [
        f"Recibimos tu pedido #{order.get('order_number')} en {company_name}.",
        f"Total: {money(delivery.get('total'))} (incluye domicilio {money(delivery.get('fee'))}).",
        f"Tiempo estimado de entrega: {delivery.get('eta_minutes')} minutos.",
    ]
    if delivery.get("payment_method") == "qr":
        lines.append("Envia a este chat la foto del comprobante de pago. La caja lo confirmara antes del despacho.")
    elif delivery.get("payment_method") == "cash" and delivery.get("pays_with"):
        lines.append(f"Pagas en efectivo con {money(delivery['pays_with'])}; te llevamos {money(delivery.get('change'))} de cambio.")
    else:
        lines.append(f"Pagas al recibir: {PAYMENT_LABELS.get(delivery.get('payment_method'), 'contra entrega').lower()}.")
    return "\n".join(lines)


def dispatched_message(company_name: str, order: dict[str, Any], delivery: dict[str, Any]) -> str:
    lines = [f"Tu pedido #{order.get('order_number')} de {company_name} ya va en camino."]
    if delivery.get("payment_method") == "qr" and delivery.get("payment_status") == "verificado":
        lines.append("Tu pago ya esta confirmado.")
    elif delivery.get("payment_method") != "qr":
        lines.append(f"Ten listo el pago: {money(delivery.get('total'))}.")
    return "\n".join(lines)


def driver_message(company_name: str, order: dict[str, Any], delivery: dict[str, Any]) -> str:
    location = (delivery.get("whatsapp_location") or {}).get("url") or delivery.get("location_url") or ""
    lines = [
        f"DOMICILIO #{order.get('order_number')} - {company_name}",
        f"Cliente: {delivery.get('customer_name')} ({display_phone(delivery.get('customer_phone')) or 'por WhatsApp'})",
        f"Direccion: {delivery.get('address')}",
    ]
    if delivery.get("address_notes"):
        lines.append(f"Indicaciones: {delivery['address_notes']}")
    if location:
        lines.append(f"Ubicacion: {location}")
    lines += ["", "Productos:", *_items_lines(order.get("items") or []), ""]
    lines.append(f"Total: {money(delivery.get('total'))} (domicilio {money(delivery.get('fee'))})")
    lines.append(payment_line(delivery))
    return "\n".join(lines)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def local_now(zone_name: str) -> datetime:
    return now_utc().astimezone(_zone(zone_name))


__all__ = [
    "MODULE_CODE", "DEFAULT_SETTINGS", "LINK_MINUTES", "PAYMENT_LABELS",
    "normalize_settings", "module_settings", "company_brief", "is_open", "schedule_text",
    "customer_reply", "valid_session", "save_whatsapp_location", "maps_url", "money",
    "confirmation_message", "dispatched_message", "driver_message", "payment_line",
    "normalize_phone", "contact_key", "display_phone", "token_hash", "local_now", "now_utc",
]
