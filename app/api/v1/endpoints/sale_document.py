"""Configuración de documento de venta (waiter_ordering).

The portal's "Pedidos por mesero" module configures the document the caja
hands out: logo, nombre comercial, razón social, NIT, dirección, teléfono,
régimen, IVA, retenciones, prefijo + consecutivo, resolución and a footer.

Colombian law: a company that is not enabled by the DIAN as an electronic
invoicer cannot issue anything called or looking like a "factura". So the
document is ALWAYS titled "CUENTA DE COBRO" and says "NO ES FACTURA DE
VENTA", with an internal consecutive. The "Habilitado como facturador
electrónico ante la DIAN" switch (off by default) only keeps the legal data
ready: nothing is connected to the DIAN yet, and while no authorized
technology provider validates the document it still is NOT a factura -- the
document and the config screen say so explicitly.

Storage: one small row per company in sale_document_settings (config JSON
+ the consecutive counter). The logo is a URL (falls back to the company's
branding logo): no image bytes are stored here (CLAUDE.md, DB space).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.models.auth import CompanyUser
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

from app.api.v1.endpoints.hospitality import (
    PAYMENT_LABELS,
    _clean,
    _hospitality_company_identity,
    _payload,
    _payment_method,
)
from app.api.v1.endpoints.waiter_ordering import _require_caja

router = APIRouter()

MODULE_CODE = "waiter_ordering"
DOCUMENT_TITLE = "CUENTA DE COBRO"
NOT_INVOICE_NOTICE = "NO ES FACTURA DE VENTA"
DIAN_PENDING_NOTICE = (
    "Facturación electrónica activada en la configuración, pero falta integrar el proveedor "
    "tecnológico autorizado por la DIAN. Mientras tanto este documento sigue siendo una cuenta "
    "de cobro y no reemplaza la factura electrónica."
)
REGIMES = {
    "no_responsable_iva": "No responsable de IVA",
    "responsable_iva": "Responsable de IVA",
    "regimen_simple": "Régimen Simple de Tributación",
}
SALE_DOC_ADMIN_ROLES = ADMIN_ROLES | {
    "manager", "gerencia", "gerente", "dueno", "dueño", "owner", "propietario", "administrador",
}


class SaleDocumentConfigIn(BaseModel):
    logo_url: str = Field(default="", max_length=500)
    trade_name: str = Field(default="", max_length=160)
    legal_name: str = Field(default="", max_length=200)
    nit: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=240)
    phone: str = Field(default="", max_length=60)
    regime: str = Field(default="no_responsable_iva", max_length=40)
    iva_percent: float = Field(default=0, ge=0, le=100)
    prices_include_iva: bool = True
    withholdings: str = Field(default="", max_length=300)
    prefix: str = Field(default="", max_length=10)
    numbering_start: int = Field(default=1, ge=1, le=999_999_999)
    resolution: str = Field(default="", max_length=300)
    footer: str = Field(default="", max_length=600)
    dian_electronic_enabled: bool = False
    # Legal structure kept ready for the future DIAN integration (unused).
    dian_resolution_number: str = Field(default="", max_length=60)
    dian_resolution_date: str = Field(default="", max_length=20)
    dian_range_from: str = Field(default="", max_length=20)
    dian_range_to: str = Field(default="", max_length=20)
    dian_valid_until: str = Field(default="", max_length=20)

    @field_validator("regime")
    @classmethod
    def valid_regime(cls, value: str) -> str:
        clean = _clean(value).lower()
        if clean not in REGIMES:
            raise ValueError("Régimen inválido.")
        return clean

    @field_validator("prefix")
    @classmethod
    def valid_prefix(cls, value: str) -> str:
        clean = _clean(value).upper()
        if clean and not re.fullmatch(r"[A-Z0-9-]{1,10}", clean):
            raise ValueError("El prefijo solo admite letras, números y guion.")
        return clean

    @field_validator("logo_url")
    @classmethod
    def valid_logo(cls, value: str) -> str:
        clean = _clean(value)
        if clean and not re.match(r"^(https://|/)", clean):
            raise ValueError("El logo debe ser una dirección https:// o una ruta del sitio.")
        return clean


DEFAULT_CONFIG = SaleDocumentConfigIn().model_dump()


async def _require_sale_doc_admin(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Admin V2, or an admin/owner of THIS company; only with waiter_ordering."""
    await require_enabled_module(db, company_id, MODULE_CODE)
    if await active_admin_v2_session(request, db):
        return "Admin V2"
    user = await require_company_user_for_tenant(db, authorization, company_id, allowed_roles=SALE_DOC_ADMIN_ROLES)
    return str(getattr(user, "full_name", "") or getattr(user, "email", "") or "usuario")


async def _read_settings(db: AsyncSession, company_id: uuid.UUID) -> tuple[dict[str, Any], int]:
    result = await db.execute(
        text("SELECT config, last_number FROM sale_document_settings WHERE company_id = :company_id"),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    raw = row["config"] if row else {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    config = {**DEFAULT_CONFIG, **{k: v for k, v in (raw or {}).items() if k in DEFAULT_CONFIG}}
    return config, int(row["last_number"]) if row else 0


def format_document_number(prefix: str, number: int) -> str:
    return f"{prefix}-{number:06d}" if prefix else f"{number:06d}"


def _pesos(value: Any) -> int:
    return int(Decimal(str(value or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def document_totals(items_total: Any, iva_percent: Any, prices_include_iva: bool) -> dict[str, int]:
    """IVA breakdown in pesos. Prices with IVA included: the total stays the
    table total and the IVA is carved out of it. Not included: IVA is added."""
    total = Decimal(str(items_total or 0))
    rate = Decimal(str(iva_percent or 0)) / Decimal(100)
    if rate <= 0:
        return {"subtotal": _pesos(total), "iva": 0, "total": _pesos(total)}
    if prices_include_iva:
        base = _pesos(total / (Decimal(1) + rate))
        return {"subtotal": base, "iva": _pesos(total) - base, "total": _pesos(total)}
    iva = _pesos(total * rate)
    return {"subtotal": _pesos(total), "iva": iva, "total": _pesos(total) + iva}


def _qty_label(item: dict[str, Any]) -> str:
    if _clean(item.get("quantity_label")):
        return _clean(item.get("quantity_label"))
    quantity = Decimal(str(item.get("quantity") or 0))
    return str(int(quantity)) if quantity == quantity.to_integral_value() else str(quantity.normalize())


def build_sale_document(
    config: dict[str, Any],
    identity: dict[str, Any],
    orders: list[dict[str, Any]],
    number: str,
    issued_at: str,
) -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    for order in orders:
        for item in order.get("items") or []:
            if not isinstance(item, dict):
                continue
            lines.append(
                {
                    "qty": _qty_label(item),
                    "name": _clean(item.get("name")) or "Producto",
                    "unit_price": _pesos(item.get("unit_price")),
                    "subtotal": _pesos(item.get("subtotal")),
                    "observations": _clean(item.get("observations")),
                    "term": _clean(item.get("term")),
                }
            )
    items_total = sum(Decimal(str(line["subtotal"])) for line in lines)
    methods = {
        _payment_method(order.get("payment_method"))
        for order in orders
        if order.get("status") == "cerrado"
    }
    first = min(orders, key=lambda order: str(order.get("created_at") or "")) if orders else {}
    waiter = ((first.get("metadata") or {}).get("waiter") or {}).get("name") or ""
    return {
        "title": DOCUMENT_TITLE,
        "not_invoice_notice": NOT_INVOICE_NOTICE,
        "dian_pending_notice": DIAN_PENDING_NOTICE if config.get("dian_electronic_enabled") else "",
        "number": number,
        "number_label": "Consecutivo interno",
        "issued_at": issued_at,
        "issuer": {
            "logo_url": config.get("logo_url") or identity.get("logo_url") or "",
            "trade_name": config.get("trade_name") or identity.get("name") or "",
            "legal_name": config.get("legal_name") or "",
            "nit": config.get("nit") or "",
            "address": config.get("address") or "",
            "phone": config.get("phone") or "",
            "regime": REGIMES.get(config.get("regime") or "", ""),
        },
        "table": _clean(first.get("table_number")),
        "waiter": _clean(waiter),
        "opened_at": first.get("created_at") or "",
        "payment_label": PAYMENT_LABELS.get(methods.pop(), "") if len(methods) == 1 else "",
        "lines": lines,
        "iva_percent": float(config.get("iva_percent") or 0),
        "prices_include_iva": bool(config.get("prices_include_iva")),
        **document_totals(items_total, config.get("iva_percent"), bool(config.get("prices_include_iva"))),
        "withholdings": config.get("withholdings") or "",
        "resolution": config.get("resolution") or "",
        "footer": config.get("footer") or "",
    }


# Sample table for the portal preview: the same build_sale_document the caja
# prints with, so the preview can't drift from the real document.
SAMPLE_ORDERS = [
    {
        "table_number": "Mesa 5",
        "status": "entregado",
        "created_at": "",
        "metadata": {"waiter": {"name": "Mesero de ejemplo"}},
        "items": [
            {"name": "POLLO Asado", "quantity": 0.75, "quantity_label": "3/4", "unit_price": 40000, "subtotal": 30000},
            {"name": "GASEOSA 400 ml", "quantity": 2, "unit_price": 4500, "subtotal": 9000},
        ],
    }
]


def _preview(config: dict[str, Any], identity: dict[str, Any], next_number: str) -> dict[str, Any]:
    return build_sale_document(config, identity, SAMPLE_ORDERS, next_number, datetime.now(timezone.utc).isoformat())


@router.get("/{company_id}/waiter-ordering/sale-document/config")
async def get_sale_document_config(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _actor: str = Depends(_require_sale_doc_admin),
) -> dict[str, Any]:
    config, last_number = await _read_settings(db, company_id)
    identity = await _hospitality_company_identity(db, company_id)
    next_number = format_document_number(config["prefix"], max(last_number + 1, int(config["numbering_start"])))
    return {
        "ok": True,
        "config": config,
        "last_number": last_number,
        "next_number": next_number,
        "preview": _preview(config, identity, next_number),
        "branding_logo_url": identity.get("logo_url") or "",
        "company_name": identity.get("name") or "",
        "title": DOCUMENT_TITLE,
        "not_invoice_notice": NOT_INVOICE_NOTICE,
        "dian_pending_notice": DIAN_PENDING_NOTICE if config["dian_electronic_enabled"] else "",
    }


@router.put("/{company_id}/waiter-ordering/sale-document/config")
async def save_sale_document_config(
    company_id: uuid.UUID,
    payload: SaleDocumentConfigIn,
    db: AsyncSession = Depends(get_db),
    actor: str = Depends(_require_sale_doc_admin),
) -> dict[str, Any]:
    config = payload.model_dump()
    await db.execute(
        text("""
            INSERT INTO sale_document_settings (company_id, config, last_number, updated_at, updated_by)
            VALUES (CAST(:company_id AS uuid), CAST(:config AS jsonb), 0, NOW(), :actor)
            ON CONFLICT (company_id) DO UPDATE
            SET config = EXCLUDED.config, updated_at = NOW(), updated_by = EXCLUDED.updated_by
        """),
        {"company_id": str(company_id), "config": json.dumps(config, ensure_ascii=False), "actor": actor[:120]},
    )
    await db.commit()
    return await get_sale_document_config(company_id, db=db, _actor=actor)


class SaleDocumentRequest(BaseModel):
    order_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("order_ids")
    @classmethod
    def some_orders(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        unique = list(dict.fromkeys(value or []))
        if not unique:
            raise ValueError("Indica los pedidos del documento.")
        return unique[:200]


async def _next_number(db: AsyncSession, company_id: uuid.UUID, start: int) -> int:
    """Atomic: the row lock of the UPSERT serializes concurrent cajas."""
    result = await db.execute(
        text("""
            INSERT INTO sale_document_settings (company_id, config, last_number, updated_at)
            VALUES (CAST(:company_id AS uuid), '{}'::jsonb, :start, NOW())
            ON CONFLICT (company_id) DO UPDATE
            SET last_number = GREATEST(sale_document_settings.last_number + 1, :start), updated_at = NOW()
            RETURNING last_number
        """),
        {"company_id": str(company_id), "start": int(start)},
    )
    return int(result.scalar())


async def _issue_sale_document(
    db: AsyncSession, company_id: uuid.UUID, order_ids: list[uuid.UUID], by: dict[str, str],
) -> dict[str, Any]:
    """Printable document for a set of orders (caja, or a reprint from the
    portal's event search). A reprint of the same set keeps its number;
    anything else gets the next consecutive."""
    ids = [str(order_id) for order_id in order_ids]
    result = await db.execute(
        text("""
            SELECT * FROM hospitality_orders
            WHERE company_id = :company_id
              AND id = ANY(CAST(:ids AS uuid[]))
              AND status <> 'cancelado'
            FOR UPDATE
        """),
        {"company_id": str(company_id), "ids": ids},
    )
    orders = [_payload(row) for row in result.mappings().all()]
    if len(orders) != len(ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado para esta empresa.")

    config, _last = await _read_settings(db, company_id)
    previous = [((order.get("metadata") or {}).get("sale_document") or {}) for order in orders]
    numbers = {doc.get("number") for doc in previous}
    if len(numbers) == 1 and None not in numbers and all(doc.get("order_ids") == sorted(ids) for doc in previous):
        number = previous[0]["number"]
        issued_at = previous[0].get("issued_at") or ""
    else:
        number = format_document_number(config["prefix"], await _next_number(db, company_id, config["numbering_start"]))
        issued_at = datetime.now(timezone.utc).isoformat()
        stamp = {
            "number": number,
            "issued_at": issued_at,
            "order_ids": sorted(ids),
            "by": by,
        }
        await db.execute(
            text("""
                UPDATE hospitality_orders
                SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('sale_document', CAST(:stamp AS jsonb)),
                    updated_at = NOW()
                WHERE company_id = :company_id AND id = ANY(CAST(:ids AS uuid[]))
            """),
            {"company_id": str(company_id), "ids": ids, "stamp": json.dumps(stamp, ensure_ascii=False)},
        )
    await db.commit()
    identity = await _hospitality_company_identity(db, company_id)
    return {"ok": True, "document": build_sale_document(config, identity, orders, number, issued_at)}


@router.post("/{company_id}/waiter-ordering/caja/documento")
async def issue_sale_document(
    company_id: uuid.UUID,
    payload: SaleDocumentRequest,
    db: AsyncSession = Depends(get_db),
    user: CompanyUser = Depends(_require_caja),
) -> dict[str, Any]:
    return await _issue_sale_document(
        db, company_id, payload.order_ids, {"id": str(user.id), "name": user.full_name or ""},
    )


@router.post("/{company_id}/waiter-ordering/sale-document/reprint")
async def reprint_sale_document(
    company_id: uuid.UUID,
    payload: SaleDocumentRequest,
    db: AsyncSession = Depends(get_db),
    actor: str = Depends(_require_sale_doc_admin),
) -> dict[str, Any]:
    """048G: reprint the bill of a past consumption from the portal's event
    search (Reportes). Same document, same number when it was already
    printed; Admin V2 or an admin of this company, only with waiter_ordering."""
    return await _issue_sale_document(db, company_id, payload.order_ids, {"id": "", "name": actor[:120]})
