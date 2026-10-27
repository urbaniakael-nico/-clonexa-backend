"""QR y piezas (interruptor carta_qr_piezas): ver app/services/carta_links.py.

Sesion en el servidor desde el primer dia:
- /carta-links/companies/{company_id}/...: administrador de la Carta de ESA
  empresa (o Admin V2), igual que la Carta (require_carta_admin), y el
  interruptor encendido.
- /carta-links/companies/{company_id}/mesero: sesion de mesero (o caja) de ESA
  empresa (la misma del panel de mesero, con la red del local) Y el enlace del
  QR de mesero vigente. Sin sesion no abre.
- /carta-links/public/{token}: la carta y el pedido de Domicilio / Para
  llevar. La credencial es el enlace secreto del QR (se regenera y el viejo
  deja de servir), como el QR de la carta y el de la mesa; con limite de
  pedidos por minuto por IP y por celular y un campo oculto anti-robots.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
import secrets
import uuid
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.carta import require_carta_admin
from app.api.v1.endpoints.hospitality import HospitalityOrderCreateIn, HospitalityOrderItemIn, create_hospitality_order
from app.api.v1.endpoints.waiter_ordering import WaiterOrderItemIn, _client_ip, _priced_order_items, _require_mesero
from app.services import carta_links as cl

router = APIRouter()
PIECES = ("hablador", "sticker", "instagram")


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/").replace("http://", "https://", 1) if "localhost" not in str(request.base_url) \
        and "127.0.0.1" not in str(request.base_url) else str(request.base_url).rstrip("/")


async def require_qr_admin(company_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                           actor: str = Depends(require_carta_admin)) -> str:
    if not await cl.enabled(db, company_id):
        raise HTTPException(status_code=403, detail="QR y piezas no está activo para esta empresa.")
    return actor


def _kind(kind: str) -> str:
    if kind not in cl.KINDS:
        raise HTTPException(status_code=404, detail="Tipo de QR desconocido.")
    return kind


async def _brand(db: AsyncSession, company_id: str) -> dict:
    from app.api.v1.endpoints.loyalty_games import brand as panel_brand
    from app.services import panel_logo

    try:
        brand = await panel_brand(db, company_id)
    except Exception:
        await db.rollback()
        brand = {}
    name = brand.get("name") or (await db.execute(text("SELECT name FROM companies WHERE id = CAST(:c AS uuid)"), {"c": company_id})).scalar() or ""
    try:
        logo = await panel_logo.panel_logo_bytes(db, company_id, brand.get("logo_url") or "")
    except Exception:
        await db.rollback()
        logo = None
    return {"name": name, "primary": brand.get("primary") or "#111111", "logo": logo}


async def _delivery(db: AsyncSession, company_id: str) -> dict:
    """Costo del domicilio SOLO si el modulo Domicilios lo tiene configurado."""
    from app.services import whatsapp_delivery as wd

    try:
        async with db.begin_nested():
            settings = await wd.module_settings(db, uuid.UUID(company_id))
    except Exception:
        settings = None
    fee = float((settings or {}).get("delivery_fee") or 0)
    return {"module": settings is not None, "fee": fee,
            "fee_text": "" if fee > 0 else "El restaurante te confirma el valor del domicilio.",
            "eta_minutes": int((settings or {}).get("eta_minutes") or 0)}


async def _state(db: AsyncSession, request: Request, company_id: uuid.UUID) -> dict:
    from app.services import menu_video

    cid = str(company_id)
    current = await cl.links(db, cid)
    await db.commit()
    tables = await cl.mesa_labels(db, cid)
    links = cl.urls(_base(request), cid, current, tables)
    return {
        "ok": True, "company_id": cid, "carta": "video" if await menu_video.video_on(db, cid) else "fotos",
        "kinds": {k: {"label": cl.LABELS[k], "on": current[k]["on"], "rotated": current[k]["rotated"],
                      "url": links.get(k) if k != "mesa" else (links["mesas"][0]["url"] if links["mesas"] else "")} for k in cl.KINDS},
        "mesas": links["mesas"], "delivery": await _delivery(db, cid),
    }


# ------------------------------------------------------------ portal ---
@router.get("/companies/{company_id}")
async def qr_state(company_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                   _a: str = Depends(require_qr_admin)) -> dict:
    return await _state(db, request, company_id)


class OnIn(BaseModel):
    on: bool


@router.put("/companies/{company_id}/kinds/{kind}")
async def qr_set_on(company_id: uuid.UUID, kind: str, payload: OnIn, request: Request, db: AsyncSession = Depends(get_db),
                    _a: str = Depends(require_qr_admin)) -> dict:
    await cl.set_on(db, str(company_id), _kind(kind), payload.on)
    await db.commit()
    return await _state(db, request, company_id)


@router.post("/companies/{company_id}/kinds/{kind}/regenerate")
async def qr_regenerate(company_id: uuid.UUID, kind: str, request: Request, db: AsyncSession = Depends(get_db),
                        _a: str = Depends(require_qr_admin)) -> dict:
    """Enlace nuevo: el QR impreso anterior deja de funcionar."""
    await cl.regenerate(db, str(company_id), _kind(kind))
    await db.commit()
    return await _state(db, request, company_id)


async def _target(db: AsyncSession, request: Request, company_id: uuid.UUID, kind: str, mesa: str = "") -> str:
    cid = str(company_id)
    current = await cl.links(db, cid)
    await db.commit()
    tables = await cl.mesa_labels(db, cid)
    links = cl.urls(_base(request), cid, current, tables)
    if kind == "mesa":
        found = next((m for m in links["mesas"] if m["label"] == mesa), links["mesas"][0] if links["mesas"] else None)
        if not found:
            raise HTTPException(status_code=404, detail="No hay mesas configuradas.")
        return found["url"]
    return links[kind]


def _png(data: bytes, name: str, info: Optional[dict] = None) -> Response:
    headers = {"Cache-Control": "private, no-store", "Content-Disposition": f'inline; filename="{name}"'}
    if info:
        headers["X-QR-Verified"] = "1" if info.get("verified") else "0"
        headers["X-QR-Variant"] = str(info.get("variant") or "")
    return Response(content=data, media_type="image/png", headers=headers)


@router.get("/companies/{company_id}/qr/{kind}.png")
async def qr_png(company_id: uuid.UUID, kind: str, request: Request, mesa: str = Query(default="", max_length=60),
                 db: AsyncSession = Depends(get_db), _a: str = Depends(require_qr_admin)) -> Response:
    """El QR con el logo y los colores de la empresa, ya leido por el lector."""
    url = await _target(db, request, company_id, _kind(kind), mesa)
    brand = await _brand(db, str(company_id))
    image, info = await asyncio.to_thread(cl.qr_image, url, brand["primary"], brand["logo"])
    return _png(cl.png(image), f"qr-{kind}.png", info)


async def _featured(db: AsyncSession, company_id: str) -> tuple[Optional[bytes], str]:
    """Foto (o portada del video) del plato destacado: lo mas pedido o, sin ventas, el primero con foto."""
    from app.services import carta_app, menu_video

    data = await carta_app.payload(db, company_id)
    products = {p["id"]: p for p in data["products"]}
    order = [products[i] for i in data["top"] if i in products] + list(products.values())
    media = await menu_video.media_map(db, company_id)
    for product in order:
        m = media.get(product["id"]) or {}
        raw_url = m.get("poster_url") or m.get("photo_url") or ""
        match = re.match(r"^/menu-media/[0-9a-f-]+/([0-9a-f-]{36})\.webp", raw_url)
        if not match:
            continue
        row = await menu_video.asset(db, company_id, match.group(1))
        if row:
            try:
                return await menu_video.read_bytes(row), product["name"]
            except Exception:
                continue
    return None, ""


async def _pieces(db: AsyncSession, request: Request, company_id: uuid.UUID, only: str = "", mesa: str = "") -> dict[str, Any]:
    cid = str(company_id)
    current = await cl.links(db, cid)
    await db.commit()
    tables = await cl.mesa_labels(db, cid)
    links = cl.urls(_base(request), cid, current, tables)
    brand = await _brand(db, cid)
    out: dict[str, Any] = {}
    if only in ("", "hablador"):
        wanted = [m for m in links["mesas"] if not mesa or m["label"] == mesa] or links["mesas"][:1]
        pages = []
        for m in wanted:
            qr, _info = await asyncio.to_thread(cl.qr_image, m["url"], brand["primary"], brand["logo"])
            pages.append((m, await asyncio.to_thread(cl.hablador, brand, m["label"], m["url"], qr)))
        out["hablador"] = pages
    if only in ("", "sticker"):
        qr, _info = await asyncio.to_thread(cl.qr_image, links["domicilio"], brand["primary"], brand["logo"])
        out["sticker"] = await asyncio.to_thread(cl.sticker, brand, links["domicilio"], qr)
    if only in ("", "instagram"):
        photo, dish = await _featured(db, cid)
        qr, _info = await asyncio.to_thread(cl.qr_image, links["domicilio"], brand["primary"], brand["logo"])
        out["instagram"] = await asyncio.to_thread(cl.instagram, brand, links["domicilio"], qr, photo, dish)
    out["_links"] = links
    out["_brand"] = brand
    return out


@router.get("/companies/{company_id}/piezas/{piece}.png")
async def piece_preview(company_id: uuid.UUID, piece: str, request: Request, mesa: str = Query(default="", max_length=60),
                        db: AsyncSession = Depends(get_db), _a: str = Depends(require_qr_admin)) -> Response:
    """Vista previa de una pieza (PNG)."""
    if piece not in PIECES:
        raise HTTPException(status_code=404, detail="Pieza desconocida.")
    built = await _pieces(db, request, company_id, piece, mesa)
    image = built["hablador"][0][1] if piece == "hablador" else built[piece]
    target = built["hablador"][0][0]["url"] if piece == "hablador" else built["_links"]["domicilio"]
    verified = await asyncio.to_thread(cl.read_piece, image) == target
    preview = image.copy()
    preview.thumbnail((900, 900))
    return _png(cl.png(preview), f"{piece}.png", {"verified": verified, "variant": piece})


@router.get("/companies/{company_id}/piezas.zip")
async def pieces_zip(company_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                     _a: str = Depends(require_qr_admin)) -> Response:
    """Todas las piezas y los QR en un ZIP (hablador por mesa, sticker, Instagram)."""
    built = await _pieces(db, request, company_id)
    links, brand = built["_links"], built["_brand"]
    files: dict[str, bytes] = {}
    checks = []
    for m, page in built["hablador"]:
        files[f"habladores/hablador-{cl.slug(m['label'])}.pdf"] = await asyncio.to_thread(cl.pdf, [page], 10, 15)
        checks.append(await asyncio.to_thread(cl.read_piece, page) == m["url"])
    files["sticker-domicilio-8x8cm.pdf"] = await asyncio.to_thread(cl.pdf, [built["sticker"]], 8, 8)
    checks.append(await asyncio.to_thread(cl.read_piece, built["sticker"]) == links["domicilio"])
    files["instagram-pide-aqui-1080x1350.png"] = cl.png(built["instagram"])
    checks.append(await asyncio.to_thread(cl.read_piece, built["instagram"]) == links["domicilio"])
    for kind in ("domicilio", "llevar", "mesero"):
        image, _info = await asyncio.to_thread(cl.qr_image, links[kind], brand["primary"], brand["logo"])
        files[f"qr/qr-{kind}.png"] = cl.png(image)
    for m in links["mesas"]:
        image, _info = await asyncio.to_thread(cl.qr_image, m["url"], brand["primary"], brand["logo"])
        files[f"qr/qr-{cl.slug(m['label'])}.png"] = cl.png(image)
    name = f"piezas-{cl.slug(brand['name'])}.zip"
    return Response(content=cl.zip_bytes(files), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store",
                             "X-QR-Verified": "1" if all(checks) else "0"})


# ------------------------------------------------------------ mesero ---
@router.get("/companies/{company_id}/mesero")
async def mesero_carta(company_id: uuid.UUID, k: str = Query(..., min_length=16, max_length=64),
                       db: AsyncSession = Depends(get_db), user: Any = Depends(_require_mesero)) -> dict:
    """La carta en el celular del mesero: SOLO con su sesion de mesero de esta
    empresa y el enlace vigente del QR de mesero. Sus mesas abiertas para
    agregar a la cuenta (el pedido va por el envio de siempre del mesero)."""
    from app.api.v1.endpoints.waiter_ordering import waiter_my_tables
    from app.services import carta_app

    found = await cl.by_token(db, k, ("mesero",))
    if not found or found["company_id"] != str(company_id):
        raise HTTPException(status_code=404, detail="Este QR de mesero ya no es válido.")
    if found["off"]:
        raise HTTPException(status_code=403, detail="El QR de mesero está apagado en este restaurante.")
    tables = await waiter_my_tables(company_id, db=db, user=user)
    return {"ok": True, "carta": await carta_app.payload(db, str(company_id)), "tables": tables.get("tables") or [],
            "mesero": getattr(user, "full_name", "") or "Mesero"}


# ------------------------------------------------------------ publico ---
async def _public(db: AsyncSession, token: str) -> dict:
    found = await cl.by_token(db, token, ("domicilio", "llevar"))
    if not found:
        raise HTTPException(status_code=404, detail="Este enlace ya no es válido. Pide el QR nuevo al restaurante.")
    if found["off"]:
        raise HTTPException(status_code=403, detail="Este restaurante no está recibiendo pedidos por aquí en este momento.")
    return found


@router.get("/public/{token}")
async def public_carta(token: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    from app.services import carta_app

    found = await _public(db, token)
    cid = found["company_id"]
    data = await carta_app.payload(db, cid)
    return {"ok": True, "kind": found["kind"], "label": cl.LABELS[found["kind"]], "carta": data,
            "delivery": await _delivery(db, cid) if found["kind"] == "domicilio" else None,
            "policy_url": f"{cl.POLICY_PATH}?c={cid}"}


PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")


class PublicOrderIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    phone: str = Field(..., min_length=7, max_length=24)
    address: str = Field(default="", max_length=240)
    barrio: str = Field(default="", max_length=120)
    reference: str = Field(default="", max_length=240)
    payment: Literal["efectivo", "transferencia"] = "efectivo"
    pickup: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=500)
    consent: bool = False
    website: str = Field(default="", max_length=200)  # campo oculto anti-robots: una persona nunca lo llena
    items: list[WaiterOrderItemIn] = Field(default_factory=list)

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, value: str) -> str:
        value = " ".join(str(value or "").split())
        if not PHONE_RE.match(value) or sum(ch.isdigit() for ch in value) < 7:
            raise ValueError("Escribe un celular válido.")
        return value

    @field_validator("items")
    @classmethod
    def clean_items(cls, value: list[WaiterOrderItemIn]) -> list[WaiterOrderItemIn]:
        rows = [i for i in (value or []) if str(i.inventory_item_id or "").strip() and i.quantity > 0]
        if not rows:
            raise ValueError("Agrega al menos un plato.")
        return rows[:60]


def _line_total(item: HospitalityOrderItemIn) -> float:
    if item.line_total is not None:
        return round(float(item.line_total), 2)
    return round(float(item.quantity) * float(item.unit_price), 2)


STATUS_TEXT = {"pendiente": "Recibido", "alistando": "En preparación", "entregado": "Listo", "cerrado": "Entregado",
               "pagado": "Entregado", "cancelado": "Cancelado"}


@router.post("/public/{token}/orders", status_code=201)
async def public_order(token: str, payload: PublicOrderIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    found = await _public(db, token)
    cid, kind = found["company_id"], found["kind"]
    if payload.website.strip():
        raise HTTPException(status_code=422, detail="No se pudo enviar el pedido.")  # robot
    if kind == "domicilio":
        if not payload.consent:
            raise HTTPException(status_code=422, detail="Marca la casilla de autorización de datos para enviar el pedido.")
        if len(payload.address.strip()) < 5:
            raise HTTPException(status_code=422, detail="Escribe la dirección de entrega.")
    elif not payload.pickup.strip():
        raise HTTPException(status_code=422, detail="Elige la hora aproximada de recogida.")
    # limite de pedidos por minuto (solo cuentan los pedidos completos)
    digits = "".join(ch for ch in payload.phone if ch.isdigit())
    ip = _client_ip(request) or "sin-ip"
    if not cl.rate_ok(f"ip:{cid}:{ip}", limit=cl.RATE_PER_IP) or not cl.rate_ok(f"tel:{cid}:{digits}", limit=cl.RATE_PER_PHONE):
        raise HTTPException(status_code=429, detail="Ya recibimos tu pedido. Espera un minuto antes de enviar otro.")
    company_uuid = uuid.UUID(cid)
    items = await _priced_order_items(db, company_uuid, payload.items)
    name = " ".join(payload.name.split())[:120]
    secret = secrets.token_urlsafe(12)
    if kind == "domicilio":
        delivery_cfg = await _delivery(db, cid)
        fee = delivery_cfg["fee"]
        if fee > 0:
            items.append(HospitalityOrderItemIn(name="Valor domicilio", quantity=1, unit_price=fee, station="domicilio", ready=True))
        total = round(sum(_line_total(i) for i in items), 2)
        address = " ".join(payload.address.split())
        delivery = {
            "customer_name": name, "customer_phone": payload.phone, "address": address,
            "address_notes": " · ".join(x for x in (" ".join(payload.barrio.split()), " ".join(payload.reference.split())) if x),
            "barrio": " ".join(payload.barrio.split()), "reference": " ".join(payload.reference.split()),
            "location_url": "", "whatsapp_location": None,
            "payment_method": "cash" if payload.payment == "efectivo" else "qr",
            "payment_status": "contra_entrega", "payment_kind": "cash" if payload.payment == "efectivo" else "transfer",
            "payment_on_delivery": True, "ask_location": False, "pays_with": None, "change": None,
            "fee": fee, "fee_pending": fee <= 0, "eta_minutes": delivery_cfg["eta_minutes"] or None,
            "session_id": "", "driver": None, "assignments": [], "notified": {}, "channel": "qr_domicilio",
            "consent": {"accepted": True, "at": datetime.now(timezone.utc).isoformat(),
                        "policy": f"{cl.POLICY_PATH}?c={cid}", "text": "Autorizo el tratamiento de mis datos para gestionar mi pedido"},
            "public_key": secret,
        }
        created = await create_hospitality_order(company_uuid, HospitalityOrderCreateIn(
            table=f"Domicilio {secrets.token_hex(2).upper()}", customer=name, source="domicilio",
            payment_method="cash" if payload.payment == "efectivo" else "transfer",
            notes=" ".join(payload.note.split())[:500], items=items), db, delivery=delivery)
    else:
        total = round(sum(_line_total(i) for i in items), 2)
        pickup = " ".join(payload.pickup.split())[:40]
        notes = f"Para llevar · recoge {pickup} · cel {payload.phone}" + (f" · {' '.join(payload.note.split())}" if payload.note.strip() else "")
        created = await create_hospitality_order(company_uuid, HospitalityOrderCreateIn(
            table=f"Para llevar {name.split()[0][:20]} {secrets.token_hex(2).upper()}", customer=name, source="para_llevar",
            payment_method="other", notes=notes[:900], items=items), db)
        order_id = created["order"]["id"]
        await db.execute(text("""
            UPDATE hospitality_orders SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('takeaway',
                jsonb_build_object('name', CAST(:n AS text), 'phone', CAST(:p AS text), 'pickup', CAST(:t AS text), 'public_key', CAST(:k AS text), 'channel', 'qr_llevar'))
            WHERE id = CAST(:o AS uuid) AND company_id = CAST(:c AS uuid)
        """), {"n": name, "p": payload.phone, "t": pickup, "k": secret, "o": str(order_id), "c": cid})
        await db.commit()
    order = created["order"]
    return {"ok": True, "kind": kind, "order_id": str(order["id"]), "order_number": order.get("order_number"),
            "total": order.get("total") if kind == "domicilio" else total, "status": "pendiente", "status_text": STATUS_TEXT["pendiente"],
            "key": secret, "fee_text": "" if kind != "domicilio" or (await _delivery(db, cid))["fee"] > 0 else "El restaurante te confirma el valor del domicilio."}


@router.get("/public/{token}/orders/{order_id}")
async def public_order_status(token: str, order_id: uuid.UUID, s: str = Query(..., min_length=8, max_length=40),
                              db: AsyncSession = Depends(get_db)) -> dict:
    """Estado del pedido (solo con la clave que recibio quien lo hizo)."""
    found = await cl.by_token(db, token, ("domicilio", "llevar"))
    if not found:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")
    row = (await db.execute(text("""
        SELECT order_number, status, total, metadata FROM hospitality_orders
        WHERE id = CAST(:o AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"o": str(order_id), "c": found["company_id"]})).mappings().first()
    meta = (row or {}).get("metadata") or {}
    key = ((meta.get("delivery") or {}).get("public_key") or (meta.get("takeaway") or {}).get("public_key") or "") if isinstance(meta, dict) else ""
    if not row or not key or not secrets.compare_digest(key, s):
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")
    delivery = meta.get("delivery") or {}
    status_value = str(row["status"] or "pendiente")
    text_value = STATUS_TEXT.get(status_value, status_value)
    if (delivery.get("dispatched_at") or (delivery.get("notified") or {}).get("dispatched")) and status_value not in ("cancelado",):
        text_value = "En camino"
    return {"ok": True, "order_number": row["order_number"], "status": status_value, "status_text": text_value,
            "total": float(row["total"] or 0)}
