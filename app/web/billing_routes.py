"""Consola v2+ · Facturacion (/admin-v2/api/billing/...).

Todo exige la sesion de Admin V2 (GUARD, validada en el servidor) salvo
/comprobante/{token}: el enlace firmado para el cliente, que vence a los 7
dias y abre SOLO ese comprobante (no es una sesion; nada mas lo acepta).
Solo empresas registradas: una demo responde 404 (las demos no facturan).
Los PDF (contratos y comprobantes) van a la zona privada del bucket
(billing/{company_id}/...), que ninguna ruta publica sirve.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import billing, billing_pdf
from app.services import company_kind as kinds
from app.services import brand_media as media
from app.web.admin_v2plus_companies import GUARD, _audit, _json, _uuid, load_company, v2

router = APIRouter()
LINK_TTL_SECONDS = 7 * 24 * 3600


def _plain(value: Any) -> Any:
    """Decimal/fecha -> JSON."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _actor(request: Request) -> str:
    payload = v2._session_payload(request) or {}
    return str(payload.get("email") or v2.ADMIN_V2_EMAIL)


def _bad(error: billing.BillingInvalid) -> HTTPException:
    return HTTPException(status_code=422, detail={"field": error.field, "message": error.message})


async def _registered(db: AsyncSession, company_id: str) -> dict:
    company = await load_company(db, _uuid(company_id))
    if company["kind"] != kinds.REGISTERED or not await billing.is_registered(db, company["id"]):
        raise HTTPException(status_code=404, detail="Las demos no facturan.")
    return company


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Cuerpo inválido.") from None
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Cuerpo inválido.")
    return data


# --------------------------------------------------------------- tablero ---
@router.get("/admin-v2/api/billing/board", include_in_schema=False, dependencies=GUARD)
async def board(db: AsyncSession = Depends(get_db)):
    data = await billing.board(db)
    return _json(_plain({**data, "types": await billing.contract_types(db), "methods": billing.METHODS}))


@router.get("/admin-v2/api/billing/alerts", include_in_schema=False, dependencies=GUARD)
async def alerts(db: AsyncSession = Depends(get_db)):
    return _json(_plain({"alerts": await billing.alerts(db)}))


@router.get("/admin-v2/api/billing/contract-types", include_in_schema=False, dependencies=GUARD)
async def list_types(db: AsyncSession = Depends(get_db)):
    return _json({"types": await billing.contract_types(db)})


@router.post("/admin-v2/api/billing/contract-types", include_in_schema=False, dependencies=GUARD)
async def add_type(request: Request, db: AsyncSession = Depends(get_db)):
    data = await _body(request)
    try:
        saved = await billing.add_contract_type(db, data.get("label"))
    except billing.BillingInvalid as error:
        raise _bad(error) from None
    await _audit(request, tipo=saved["label"])
    return _json({"ok": True, "type": saved, "types": await billing.contract_types(db)})


# --------------------------------------------------------------- empresa ---
@router.get("/admin-v2/api/billing/companies/{company_id}", include_in_schema=False, dependencies=GUARD)
async def company_detail(company_id: str, db: AsyncSession = Depends(get_db)):
    company = await _registered(db, company_id)
    view = await billing.company_view(db, company["id"])
    return _json(_plain({"company": {"id": company["id"], "name": company["name"], "slug": company["slug"]}, **view,
                         "types": await billing.contract_types(db), "methods": billing.METHODS}))


@router.put("/admin-v2/api/billing/companies/{company_id}/contract", include_in_schema=False, dependencies=GUARD)
async def save_contract(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await _registered(db, company_id)
    data = await _body(request)
    existed = await billing.get_contract(db, company["id"]) is not None
    try:
        contract = await billing.save_contract(db, company["id"], data)
    except billing.BillingInvalid as error:
        raise _bad(error) from None
    await _audit(request, company_name=company["name"], contrato="cambiado" if existed else "creado", tipo=contract["contract_type"],
                 estado=contract["status"])
    return _json(_plain({"ok": True, **await billing.company_view(db, company["id"])}))


@router.post("/admin-v2/api/billing/companies/{company_id}/payments", include_in_schema=False, dependencies=GUARD)
async def register_payment(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await _registered(db, company_id)
    try:
        saved = await billing.register_payment(db, company["id"], await _body(request), _actor(request))
    except billing.BillingInvalid as error:
        raise _bad(error) from None
    except billing.BillingConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    await _audit(request, company_name=company["name"], valor=str(saved["amount"]), estado="por validar")
    return _json(_plain({"ok": True, "payment": saved, **await billing.company_view(db, company["id"])}))


async def _store_receipt(db: AsyncSession, company_id: str, receipt_id: str) -> bytes:
    """Genera el PDF y lo guarda en la zona privada (si el bucket responde)."""
    row = await billing.receipt(db, company_id, receipt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado.")
    pdf = billing_pdf.render(row)
    if media.configured():
        key = billing.receipt_key(company_id, row["number"])
        try:
            await asyncio.to_thread(media.put_private, key, pdf, "application/pdf")
            await billing.set_receipt_key(db, company_id, receipt_id, key)
        except media.StorageUnavailable:
            pass  # se vuelve a generar al descargarlo
    return pdf


@router.post("/admin-v2/api/billing/companies/{company_id}/payments/{payment_id}/validate", include_in_schema=False, dependencies=GUARD)
async def validate_payment(company_id: str, payment_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await _registered(db, company_id)
    try:
        issued = await billing.validate_payment_and_issue(db, company["id"], str(_uuid(payment_id)), _actor(request))
    except billing.BillingConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    await _store_receipt(db, company["id"], issued["receipt_id"])
    await _audit(request, company_name=company["name"], comprobante=issued["code"])
    return _json(_plain({"ok": True, "receipt": issued, **await billing.company_view(db, company["id"])}))


@router.post("/admin-v2/api/billing/companies/{company_id}/payments/{payment_id}/void", include_in_schema=False, dependencies=GUARD)
async def void_payment(company_id: str, payment_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await _registered(db, company_id)
    data = await _body(request)
    try:
        voided = await billing.void_payment(db, company["id"], str(_uuid(payment_id)), data.get("reason"), _actor(request))
    except billing.BillingInvalid as error:
        raise _bad(error) from None
    except billing.BillingConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    rec = next((p for p in await billing.payments(db, company["id"]) if p["id"] == voided["payment_id"]), None)
    if rec and rec.get("receipt_id"):
        await _store_receipt(db, company["id"], rec["receipt_id"])  # el PDF queda marcado ANULADO
    await _audit(request, company_name=company["name"], comprobante=voided["code"] or "", motivo=str(data.get("reason") or "")[:120])
    return _json(_plain({"ok": True, **await billing.company_view(db, company["id"])}))


async def _receipt_pdf(db: AsyncSession, company_id: str, receipt_id: str) -> tuple[bytes, dict]:
    row = await billing.receipt(db, company_id, receipt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado.")
    if row.get("storage_key") and media.configured():
        try:
            return await asyncio.to_thread(media.backend().get, row["storage_key"]), row
        except Exception:
            pass
    return billing_pdf.render(row), row


def _pdf_response(pdf: bytes, filename: str) -> Response:
    return v2._no_store(Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{filename}"', "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex"}))


@router.get("/admin-v2/api/billing/companies/{company_id}/receipts/{receipt_id}.pdf", include_in_schema=False, dependencies=GUARD)
async def receipt_pdf(company_id: str, receipt_id: str, db: AsyncSession = Depends(get_db)):
    company = await _registered(db, company_id)
    pdf, row = await _receipt_pdf(db, company["id"], receipt_id)
    return _pdf_response(pdf, f"{billing.receipt_code(row['number'])}.pdf")


# ------------------------------------------------ enlace para el cliente ---
def _link_key() -> bytes:
    return hmac.new(v2._session_secret(), b"clonexa-billing-receipt-v1", hashlib.sha256).digest()


def _link_sig(receipt_id: str, company_id: str, expires: int) -> str:
    return hmac.new(_link_key(), f"{receipt_id}.{company_id}.{expires}".encode("ascii"), hashlib.sha256).hexdigest()[:40]


def receipt_token(receipt_id: str, company_id: str, now: float | None = None) -> str:
    expires = int((now or time.time()) + LINK_TTL_SECONDS)
    return f"{receipt_id}.{company_id}.{expires}.{_link_sig(receipt_id, company_id, expires)}"


def parse_receipt_token(token: str, now: float | None = None) -> tuple[str, str] | None:
    parts = str(token or "").split(".")
    if len(parts) != 4 or len(token) > 200:
        return None
    rid, cid, exp, sig = parts
    try:
        rid, cid, expires = str(uuid.UUID(rid)), str(uuid.UUID(cid)), int(exp)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _link_sig(rid, cid, expires)) or (now or time.time()) > expires:
        return None
    return rid, cid


@router.post("/admin-v2/api/billing/companies/{company_id}/receipts/{receipt_id}/link", include_in_schema=False, dependencies=GUARD)
async def receipt_link(company_id: str, receipt_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await _registered(db, company_id)
    row = await billing.receipt(db, company["id"], receipt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado.")
    token = receipt_token(row["id"], company["id"])
    await _audit(request, company_name=company["name"], comprobante=billing.receipt_code(row["number"]))
    return _json({"ok": True, "url": f"/comprobante/{token}", "expires_in_days": 7})


@router.get("/comprobante/{token}", include_in_schema=False)
async def public_receipt(token: str, db: AsyncSession = Depends(get_db)):
    """Enlace firmado: sin sesion, pero solo abre ESE comprobante y vence."""
    parsed = parse_receipt_token(token)
    if not parsed:
        raise HTTPException(status_code=404, detail="Este enlace ya no sirve. Pide uno nuevo.")
    rid, cid = parsed
    pdf, row = await _receipt_pdf(db, cid, rid)
    return _pdf_response(pdf, f"{billing.receipt_code(row['number'])}.pdf")


# --------------------------------------------------- contratos adjuntos ---
async def _read_limited(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + 4096:
        raise HTTPException(status_code=413, detail="El contrato pesa más de 10 MB.")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail="El contrato pesa más de 10 MB.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/admin-v2/api/billing/companies/{company_id}/contract-file", include_in_schema=False, dependencies=GUARD)
async def upload_contract(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Cuerpo = el PDF crudo (no multipart). Reemplazar guarda la version anterior."""
    company = await _registered(db, company_id)
    if not media.configured():
        raise HTTPException(status_code=503, detail="El almacenamiento no está configurado; no se pueden adjuntar contratos.")
    raw = await _read_limited(request, billing.MAX_PDF_BYTES)

    async def put(key: str, data: bytes) -> None:
        await asyncio.to_thread(media.put_private, key, data, "application/pdf")

    try:
        saved = await billing.add_contract_file(db, company["id"], raw, request.headers.get("x-file-name", "contrato.pdf"), _actor(request), put)
    except billing.BillingInvalid as error:
        raise _bad(error) from None
    except media.StorageUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    await _audit(request, company_name=company["name"], contrato_pdf=f"versión {saved['version']}", kb=round(saved["size_bytes"] / 1024))
    return _json(_plain({"ok": True, "file": saved, "files": await billing.contract_files(db, company["id"])}))


@router.get("/admin-v2/api/billing/companies/{company_id}/contract-file/{file_id}", include_in_schema=False, dependencies=GUARD)
async def download_contract(company_id: str, file_id: str, db: AsyncSession = Depends(get_db)):
    company = await _registered(db, company_id)
    row = await billing.contract_file(db, company["id"], file_id)
    if not row:
        raise HTTPException(status_code=404, detail="Contrato no encontrado.")
    try:
        pdf = await asyncio.to_thread(media.backend().get, billing.contract_file_key(company["id"], row["id"]))
    except Exception:
        raise HTTPException(status_code=503, detail="El almacenamiento no responde. Intenta de nuevo en un momento.") from None
    return _pdf_response(pdf, f"contrato-{company['slug'] or 'empresa'}-v{row['version']}.pdf")
