"""Facturacion: rutas. Sesion de Admin V2 obligatoria, demos fuera, enlace
firmado del comprobante (vence, abre solo el suyo) y solo PDF reales."""
from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import billing
from app.services import brand_media as media
from app.web import admin_v2plus_companies as ep
from app.web import billing_routes as br

A, B = str(uuid.uuid4()), str(uuid.uuid4())
R_A, R_B = str(uuid.uuid4()), str(uuid.uuid4())


def _receipt(rid, cid):
    return {"id": rid, "number": 7, "status": "vigente", "storage_key": None, "created_at": datetime.now(timezone.utc), "voided_at": None,
            "void_reason": None, "amount": Decimal("250"), "paid_on": date(2026, 10, 16), "method": "transferencia", "reference": "TRX-1",
            "validated_at": datetime.now(timezone.utc), "validated_by": "admin", "period": date(2026, 10, 1), "seq": 2,
            "company_id": cid, "company_name": "The Time Machine", "company_slug": "ttm", "currency": "COP"}


@pytest.fixture
def client(monkeypatch):
    async def fake_db():
        yield SimpleNamespace()

    app_main.app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))

    async def receipt(db, cid, rid):
        return _receipt(rid, cid) if (cid, rid) in ((A, R_A), (B, R_B)) else None

    monkeypatch.setattr(billing, "receipt", receipt)
    yield SimpleNamespace(c=TestClient(app_main.app, base_url="https://testserver"), mp=monkeypatch)
    app_main.app.dependency_overrides.pop(get_db, None)


def test_every_billing_endpoint_requires_the_admin_session(client):
    c = client.c
    for method, path in [("get", "/admin-v2/api/billing/board"), ("get", "/admin-v2/api/billing/alerts"), ("get", "/admin-v2/api/billing/contract-types"),
                         ("post", "/admin-v2/api/billing/contract-types"), ("get", f"/admin-v2/api/billing/companies/{A}"),
                         ("put", f"/admin-v2/api/billing/companies/{A}/contract"), ("post", f"/admin-v2/api/billing/companies/{A}/payments"),
                         ("post", f"/admin-v2/api/billing/companies/{A}/payments/{R_A}/validate"), ("post", f"/admin-v2/api/billing/companies/{A}/payments/{R_A}/void"),
                         ("get", f"/admin-v2/api/billing/companies/{A}/receipts/{R_A}.pdf"), ("post", f"/admin-v2/api/billing/companies/{A}/receipts/{R_A}/link"),
                         ("post", f"/admin-v2/api/billing/companies/{A}/contract-file"), ("get", f"/admin-v2/api/billing/companies/{A}/contract-file/{R_A}")]:
        assert getattr(c, method)(path).status_code == 401, path
    paths = {r.path for r in app_main.app.routes if "billing/" in getattr(r, "path", "") and r.path.startswith("/admin-v2/api/billing")}
    assert len(paths) == 12, "si se agrega una ruta, se agrega aqui con su prueba de sesion"


def test_demos_do_not_bill(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))

    async def demo(db, cid):
        return {"id": A, "name": "Demo", "slug": "demo", "status": "active", "kind": "demo"}

    client.mp.setattr(br, "load_company", demo)
    assert client.c.get(f"/admin-v2/api/billing/companies/{A}").status_code == 404


def test_signed_receipt_link_expires_and_opens_only_its_receipt(client):
    token = br.receipt_token(R_A, A)
    res = client.c.get(f"/comprobante/{token}")
    assert res.status_code == 200 and res.content.startswith(b"%PDF-") and res.headers["content-type"] == "application/pdf"
    assert "no-store" in res.headers.get("cache-control", "")
    rid, cid, exp, sig = token.split(".")
    assert client.c.get(f"/comprobante/{R_B}.{cid}.{exp}.{sig}").status_code == 404, "cambiar el comprobante rompe la firma"
    assert client.c.get(f"/comprobante/{rid}.{B}.{exp}.{sig}").status_code == 404, "ni la empresa"
    assert client.c.get(f"/comprobante/{rid}.{cid}.{int(exp) + 999}.{sig}").status_code == 404, "ni el vencimiento"
    forged = br.receipt_token(R_A, B)  # bien firmado, pero ese comprobante no es de B
    assert client.c.get(f"/comprobante/{forged}").status_code == 404
    old = br.receipt_token(R_A, A, now=time.time() - 8 * 24 * 3600)
    assert client.c.get(f"/comprobante/{old}").status_code == 404, "vence a los 7 dias"
    assert br.parse_receipt_token(br.receipt_token(R_A, A), now=time.time() + 6 * 24 * 3600) == (R_A, A)
    assert client.c.get(f"/admin-v2/api/billing/companies/{A}/receipts/{R_A}.pdf", headers={"Authorization": f"Bearer {token}"}).status_code == 401, \
        "el enlace no sirve como sesion"


def test_contract_upload_rejects_a_file_that_is_not_a_real_pdf(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))

    async def registered(db, cid):
        return {"id": A, "name": "TTM", "slug": "ttm", "status": "active", "kind": "registrada"}

    client.mp.setattr(br, "_registered", registered)
    client.mp.setattr(media, "configured", lambda: True)
    res = client.c.post(f"/admin-v2/api/billing/companies/{A}/contract-file", content=b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                        headers={"Content-Type": "application/pdf", "X-File-Name": "contrato.pdf"})
    assert res.status_code == 422 and "PDF" in res.text
    big = client.c.post(f"/admin-v2/api/billing/companies/{A}/contract-file", content=b"%PDF-" + b"0" * (billing.MAX_PDF_BYTES + 10))
    assert big.status_code == 413
