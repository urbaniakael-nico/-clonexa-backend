from __future__ import annotations

import html
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, READ_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.api.v1.endpoints.transport_contracts import ensure_transport_contracts_storage
from app.api.v1.endpoints.transport_quotes_tickets import (
    _build_service_document_pdf,
    _company,
    ensure_transport_documents_storage,
)
from app.core.config import get_settings
from app.services.transactional_email import (
    TransactionalEmailConfigurationError,
    TransactionalEmailDeliveryError,
    send_transactional_email,
)
from app.web.admin_v2_routes import _active_company_preview as active_admin_company_preview
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()

TRANSPORT_PAYMENT_WRITE_ROLES = ADMIN_ROLES | {"manager", "gerencia", "gerente", "tesoreria", "treasury"}


def _authorization_from_query_028s(authorization: str | None, access_token: str | None = "") -> str | None:
    token = str(access_token or "").strip()
    return authorization or (f"Bearer {token}" if token else None)


async def require_transport_payments_read(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str = Query(default="", max_length=2048),
    db: AsyncSession = Depends(get_db),
) -> None:
    if await active_admin_v2_session(request, db) or active_admin_company_preview(request, company_id):
        await require_enabled_module(db, company_id, "transport_payments")
        return
    await require_company_user_for_tenant(
        db,
        _authorization_from_query_028s(authorization, access_token),
        company_id,
        allowed_roles=READ_ROLES,
        module_codes="transport_payments",
    )


async def require_transport_payments_write(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    if await active_admin_v2_session(request, db) or active_admin_company_preview(request, company_id):
        await require_enabled_module(db, company_id, "transport_payments")
        return
    await require_company_user_for_tenant(
        db,
        authorization,
        company_id,
        allowed_roles=TRANSPORT_PAYMENT_WRITE_ROLES,
        module_codes="transport_payments",
    )

MAX_PAYMENT_PROOF_BYTES = 8 * 1024 * 1024
MAX_INVOICE_ATTACHMENT_BYTES = 8 * 1024 * 1024
ALLOWED_PAYMENT_PROOF_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}


class TransportPaymentIn(BaseModel):
    document_id: str | None = Field(default="", max_length=80)
    amount: float | None = Field(default=0, ge=0)
    payment_method: str | None = Field(default="transfer", max_length=60)
    payment_reference: str | None = Field(default="", max_length=160)
    status: str | None = Field(default="paid", max_length=40)
    created_by: str | None = Field(default="", max_length=180)
    notes: str | None = Field(default="", max_length=1600)


class TransportCreditIn(BaseModel):
    amount: float | None = Field(default=0, ge=0)
    payment_method: str | None = Field(default="transfer", max_length=60)
    payment_reference: str | None = Field(default="", max_length=160)
    created_by: str | None = Field(default="", max_length=180)
    notes: str | None = Field(default="", max_length=1600)


class TransportInvoiceIn(BaseModel):
    document_id: str | None = Field(default="", max_length=80)
    contract_id: str | None = Field(default="", max_length=80)
    amount: float | None = Field(default=0, ge=0)
    due_date: str | None = Field(default="", max_length=20)
    recipient: str | None = Field(default="", max_length=180)
    channel: str | None = Field(default="whatsapp", max_length=40)
    status: str | None = Field(default="sent", max_length=40)
    created_by: str | None = Field(default="", max_length=180)
    notes: str | None = Field(default="", max_length=1600)


class TreasuryCheckIn(BaseModel):
    treasury_check: bool | None = True
    status: str | None = Field(default="", max_length=40)
    created_by: str | None = Field(default="", max_length=180)
    notes: str | None = Field(default="", max_length=1600)


class TransportMailSettingsIn(BaseModel):
    sender_name: str | None = Field(default="", max_length=120)
    reply_to_email: str | None = Field(default="", max_length=180)
    cc_email: str | None = Field(default="", max_length=180)
    signature: str | None = Field(default="", max_length=1200)
    updated_by: str | None = Field(default="", max_length=180)


def _clean(value: Any, limit: int = 255) -> str:
    return str(value or "").strip()[:limit]


def _money(value: Any) -> float:
    try:
        raw = str(value or "0").strip()
        clean = "".join(ch for ch in raw if ch.isdigit() or ch in {".", ",", "-"})
        if "," in clean and "." in clean:
            clean = clean.replace(".", "").replace(",", ".") if clean.rfind(",") > clean.rfind(".") else clean.replace(",", "")
        elif clean.count(".") > 1:
            clean = clean.replace(".", "")
        elif clean.count(",") > 1:
            clean = clean.replace(",", "")
        elif "," in clean:
            clean = clean.replace(",", ".")
        return max(0.0, float(clean or 0))
    except Exception:
        return 0.0


def _row(row: Any) -> dict[str, Any]:
    data = dict(row._mapping if hasattr(row, "_mapping") else row)
    for key, value in list(data.items()):
        if isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
        elif isinstance(value, uuid.UUID):
            data[key] = str(value)
        elif isinstance(value, Decimal):
            data[key] = float(value)
    return data



def _payment_proof_content_type(upload: UploadFile | None) -> str:
    if not upload or not upload.filename:
        return ""
    content_type = _clean(upload.content_type, 120).lower()
    if content_type:
        return content_type
    name = str(upload.filename or "").lower()
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"


async def _read_payment_proof_upload(upload: UploadFile | None) -> tuple[str, str, bytes | None, int]:
    if not upload or not upload.filename:
        return "", "", None, 0
    content_type = _payment_proof_content_type(upload)
    if content_type not in ALLOWED_PAYMENT_PROOF_TYPES:
        raise HTTPException(status_code=400, detail="proof_type_not_supported")
    data = await upload.read()
    if not data:
        return "", "", None, 0
    if len(data) > MAX_PAYMENT_PROOF_BYTES:
        raise HTTPException(status_code=400, detail="proof_file_too_large")
    return _clean(upload.filename, 260), content_type, data, len(data)


def _payment_proof_url(company_id: uuid.UUID | str, payment_id: Any, original_name: Any) -> str:
    if not payment_id or not original_name:
        return ""
    return f"/api/v1/transport-payments/companies/{company_id}/payments/{payment_id}/proof"


def _payment_payload(row: Any, company_id: uuid.UUID | str) -> dict[str, Any]:
    data = _row(row)
    data.pop("proof_file_bytes", None)
    data["proof_file_url"] = _payment_proof_url(company_id, data.get("id"), data.get("proof_original_name"))
    return data

def _payment_status(value: Any) -> str:
    clean = _clean(value or "paid", 40).lower().replace(" ", "_")
    return clean if clean in {"pending", "paid", "rejected", "archived"} else "paid"


def _document_status(value: Any) -> str:
    clean = _clean(value or "", 40).lower().replace(" ", "_")
    allowed = {"pending", "approved", "rejected", "converted", "scheduled", "in_route", "completed", "cancelled", "billed"}
    return clean if clean in allowed else ""


def _invoice_status(value: Any) -> str:
    clean = _clean(value or "sent", 40).lower().replace(" ", "_")
    return clean if clean in {"draft", "sent", "paid", "overdue", "cancelled", "archived"} else "sent"


def _channel(value: Any) -> str:
    clean = _clean(value or "whatsapp", 40).lower().replace(" ", "_")
    return clean if clean in {"whatsapp", "email", "manual", "link"} else "whatsapp"


async def ensure_transport_payments_storage(db: AsyncSession) -> None:
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    await ensure_transport_documents_storage(db)
    await ensure_transport_contracts_storage(db)
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS transport_payment_records (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id uuid NOT NULL,
                document_id uuid NULL,
                contract_id uuid NULL,
                document_number varchar(60) NOT NULL DEFAULT '',
                contract_code varchar(120) NOT NULL DEFAULT '',
                client_name varchar(180) NOT NULL DEFAULT '',
                payment_method varchar(60) NOT NULL DEFAULT 'transfer',
                payment_reference varchar(160) NOT NULL DEFAULT '',
                amount numeric(14,2) NOT NULL DEFAULT 0,
                status varchar(40) NOT NULL DEFAULT 'paid',
                paid_at timestamptz NULL,
                created_by varchar(180) NOT NULL DEFAULT '',
                notes text NOT NULL DEFAULT '',
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                archived_at timestamptz NULL
            )
            """
        )
    )
    for statement in [
        "ALTER TABLE transport_payment_records ADD COLUMN IF NOT EXISTS record_type VARCHAR(40) NOT NULL DEFAULT 'ticket_payment';",
        "ALTER TABLE transport_payment_records ADD COLUMN IF NOT EXISTS proof_original_name varchar(260) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_payment_records ADD COLUMN IF NOT EXISTS proof_content_type varchar(120) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_payment_records ADD COLUMN IF NOT EXISTS proof_file_bytes bytea NULL;",
        "ALTER TABLE transport_payment_records ADD COLUMN IF NOT EXISTS proof_file_size integer NOT NULL DEFAULT 0;",
        "CREATE INDEX IF NOT EXISTS ix_transport_payments_company_status ON transport_payment_records (company_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_transport_payments_company_doc ON transport_payment_records (company_id, document_id)",
        "CREATE INDEX IF NOT EXISTS ix_transport_payments_company_created ON transport_payment_records (company_id, created_at DESC)",
    ]:
        await db.execute(text(statement))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS transport_invoice_records (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id uuid NOT NULL,
                document_id uuid NULL,
                contract_id uuid NULL,
                invoice_number varchar(60) NOT NULL DEFAULT '',
                document_number varchar(60) NOT NULL DEFAULT '',
                contract_code varchar(120) NOT NULL DEFAULT '',
                client_name varchar(180) NOT NULL DEFAULT '',
                recipient varchar(180) NOT NULL DEFAULT '',
                channel varchar(40) NOT NULL DEFAULT 'whatsapp',
                amount numeric(14,2) NOT NULL DEFAULT 0,
                due_date date NULL,
                status varchar(40) NOT NULL DEFAULT 'sent',
                sent_at timestamptz NULL,
                paid_at timestamptz NULL,
                created_by varchar(180) NOT NULL DEFAULT '',
                notes text NOT NULL DEFAULT '',
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                archived_at timestamptz NULL
            )
            """
        )
    )
    for statement in [
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS document_id uuid NULL;",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS contract_id uuid NULL;",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS invoice_number varchar(60) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS document_number varchar(60) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS contract_code varchar(120) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS client_name varchar(180) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS recipient varchar(180) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS channel varchar(40) NOT NULL DEFAULT 'whatsapp';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS amount numeric(14,2) NOT NULL DEFAULT 0;",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS due_date date NULL;",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS status varchar(40) NOT NULL DEFAULT 'sent';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS sent_at timestamptz NULL;",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS paid_at timestamptz NULL;",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS created_by varchar(180) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS notes text NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS archived_at timestamptz NULL;",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS provider_message_id varchar(180) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS delivery_status varchar(40) NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS delivery_error text NOT NULL DEFAULT '';",
        "ALTER TABLE transport_invoice_records ADD COLUMN IF NOT EXISTS attachment_name varchar(260) NOT NULL DEFAULT '';",
        "CREATE INDEX IF NOT EXISTS ix_transport_invoices_company_status ON transport_invoice_records (company_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_transport_invoices_company_due ON transport_invoice_records (company_id, due_date)",
        "CREATE INDEX IF NOT EXISTS ix_transport_invoices_company_doc ON transport_invoice_records (company_id, document_id)",
    ]:
        await db.execute(text(statement))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS transport_payment_mail_settings (
                company_id uuid PRIMARY KEY,
                sender_name varchar(120) NOT NULL DEFAULT '',
                reply_to_email varchar(180) NOT NULL DEFAULT '',
                cc_email varchar(180) NOT NULL DEFAULT '',
                signature text NOT NULL DEFAULT '',
                updated_by varchar(180) NOT NULL DEFAULT '',
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )


def _valid_optional_email(value: Any) -> str:
    email = _clean(value, 180)
    if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
        raise HTTPException(status_code=400, detail="email_invalid")
    return email


async def _transport_mail_settings(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT sender_name, reply_to_email, cc_email, signature, updated_by, updated_at
            FROM transport_payment_mail_settings
            WHERE company_id = CAST(:company_id AS uuid)
            LIMIT 1
            """
        ),
        {"company_id": str(company_id)},
    )
    saved = _row(result.first() or {})
    settings = get_settings()
    saved.update(
        {
            "from_email": settings.MAIL_DEFAULT_FROM.strip(),
            "provider": "resend",
            "provider_configured": bool(settings.RESEND_API_KEY.strip() and settings.MAIL_DEFAULT_FROM.strip()),
        }
    )
    return saved


async def _read_invoice_attachment(upload: UploadFile | None) -> tuple[str, bytes]:
    if not upload or not upload.filename:
        return "", b""
    content_type = _payment_proof_content_type(upload)
    if content_type not in ALLOWED_PAYMENT_PROOF_TYPES:
        raise HTTPException(status_code=400, detail="invoice_attachment_type_not_supported")
    content = await upload.read()
    if not content:
        return "", b""
    if len(content) > MAX_INVOICE_ATTACHMENT_BYTES:
        raise HTTPException(status_code=400, detail="invoice_attachment_too_large")
    return _clean(upload.filename, 260), content


async def _contract_by_id(db: AsyncSession, company_id: uuid.UUID, contract_id: str) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT *, GREATEST(initial_balance - consumed_balance, 0) AS available_balance
            FROM transport_contracts
            WHERE company_id = CAST(:company_id AS uuid)
              AND id = CAST(:contract_id AS uuid)
              AND archived_at IS NULL
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "contract_id": contract_id},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="contract_not_found")
    return _row(row)


async def _next_invoice_number(db: AsyncSession, company_id: uuid.UUID) -> str:
    result = await db.execute(
        text(
            """
            SELECT COUNT(*) + 1 AS next_value
            FROM transport_invoice_records
            WHERE company_id = CAST(:company_id AS uuid)
            """
        ),
        {"company_id": str(company_id)},
    )
    row = result.first()
    value = int((row._mapping.get("next_value") if row else 1) or 1)
    return f"FAC-{value:06d}"


async def _ticket_document(db: AsyncSession, company_id: uuid.UUID, document_id: str) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT
                d.*,
                COALESCE(p.paid_amount, 0) AS paid_amount
            FROM transport_service_documents d
            LEFT JOIN (
                SELECT document_id, COALESCE(SUM(amount) FILTER (WHERE status = 'paid'), 0) AS paid_amount
                FROM transport_payment_records
                WHERE company_id = CAST(:company_id AS uuid)
                  AND archived_at IS NULL
                GROUP BY document_id
            ) p ON p.document_id = d.id
            WHERE d.company_id = CAST(:company_id AS uuid)
              AND d.id = CAST(:document_id AS uuid)
              AND d.document_type = 'ticket'
              AND d.archived_at IS NULL
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "document_id": document_id},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="ticket_not_found")
    return _row(row)


@router.get("/companies/{company_id}/summary", dependencies=[Depends(require_transport_payments_read)])
async def transport_payments_summary(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
    search: str = Query(default="", max_length=120),
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    query = f"%{_clean(search, 120).lower()}%"
    result = await db.execute(
        text(
            """
            WITH docs AS (
                SELECT *
                FROM transport_service_documents
                WHERE company_id = CAST(:company_id AS uuid)
                  AND document_type = 'ticket'
                  AND archived_at IS NULL
                  AND (:start_date = '' OR created_at >= CAST(:start_date AS date))
                  AND (:end_date = '' OR created_at < (CAST(:end_date AS date) + INTERVAL '1 day'))
                  AND (
                    :query = '%%'
                    OR LOWER(document_number) LIKE :query
                    OR LOWER(client_name) LIKE :query
                    OR LOWER(contract_code) LIKE :query
                    OR LOWER(origin) LIKE :query
                    OR LOWER(destination) LIKE :query
                  )
            ),
            payments AS (
                SELECT *
                FROM transport_payment_records
                WHERE company_id = CAST(:company_id AS uuid)
                  AND archived_at IS NULL
                  AND (:start_date = '' OR COALESCE(paid_at, created_at) >= CAST(:start_date AS date))
                  AND (:end_date = '' OR COALESCE(paid_at, created_at) < (CAST(:end_date AS date) + INTERVAL '1 day'))
                  AND (
                    :query = '%%'
                    OR LOWER(document_number) LIKE :query
                    OR LOWER(client_name) LIKE :query
                    OR LOWER(contract_code) LIKE :query
                    OR LOWER(payment_reference) LIKE :query
                  )
            ),
            contracts AS (
                SELECT *, GREATEST(initial_balance - consumed_balance, 0) AS available_balance
                FROM transport_contracts
                WHERE company_id = CAST(:company_id AS uuid)
                  AND archived_at IS NULL
            ),
            invoices AS (
                SELECT *
                FROM transport_invoice_records
                WHERE company_id = CAST(:company_id AS uuid)
                  AND archived_at IS NULL
                  AND (:start_date = '' OR created_at >= CAST(:start_date AS date))
                  AND (:end_date = '' OR created_at < (CAST(:end_date AS date) + INTERVAL '1 day'))
                  AND (
                    :query = '%%'
                    OR LOWER(invoice_number) LIKE :query
                    OR LOWER(document_number) LIKE :query
                    OR LOWER(client_name) LIKE :query
                    OR LOWER(contract_code) LIKE :query
                    OR LOWER(recipient) LIKE :query
                  )
            )
            SELECT
                (SELECT COUNT(*) FROM docs) AS ticket_count,
                (SELECT COUNT(*) FROM docs WHERE treasury_check = false) AS pending_treasury_count,
                (SELECT COUNT(*) FROM docs WHERE supervisor_check = false) AS pending_supervisor_count,
                (SELECT COUNT(*) FROM docs WHERE supervisor_check = true AND treasury_check = true AND status NOT IN ('billed','completed','cancelled')) AS ready_to_bill_count,
                (SELECT COUNT(*) FROM docs WHERE status = 'billed') AS billed_count,
                (SELECT COALESCE(SUM(total_amount), 0) FROM docs) AS ticket_total,
                (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid') AS paid_total,
                (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid' AND record_type = 'contract_credit') AS credit_total,
                (SELECT COALESCE(SUM(available_balance), 0) FROM contracts WHERE status <> 'archived') AS contracts_available_total,
                (SELECT COUNT(*) FROM contracts WHERE status <> 'archived' AND available_balance <= alert_balance) AS low_balance_count,
                (SELECT COUNT(*) FROM invoices WHERE status IN ('draft','sent') AND due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days') AS due_soon_count,
                (SELECT COUNT(*) FROM invoices WHERE status IN ('draft','sent') AND due_date < CURRENT_DATE) AS overdue_invoice_count,
                (SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status IN ('draft','sent')) AS invoice_pending_total
            """
        ),
        {"company_id": str(company_id), "start_date": _clean(start_date, 20), "end_date": _clean(end_date, 20), "query": query},
    )
    return {"ok": True, "company_id": str(company_id), "summary": _row(result.first() or {})}


@router.get("/companies/{company_id}/queue", dependencies=[Depends(require_transport_payments_read)])
async def list_transport_payment_queue(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=80, ge=1, le=300),
    search: str = Query(default="", max_length=120),
    status_filter: str = Query(default="all", alias="status", max_length=40),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    status_value = _clean(status_filter, 40).lower()
    query = f"%{_clean(search, 120).lower()}%"
    result = await db.execute(
        text(
            """
            SELECT
                d.*,
                COALESCE(p.paid_amount, 0) AS paid_amount,
                GREATEST(COALESCE(d.total_amount, 0) - COALESCE(p.paid_amount, 0), 0) AS pending_amount,
                GREATEST(COALESCE(c.initial_balance, 0) - COALESCE(c.consumed_balance, 0), 0) AS contract_available_balance,
                c.alert_balance AS contract_alert_balance,
                c.status AS contract_status
            FROM transport_service_documents d
            LEFT JOIN (
                SELECT document_id, COALESCE(SUM(amount) FILTER (WHERE status = 'paid'), 0) AS paid_amount
                FROM transport_payment_records
                WHERE company_id = CAST(:company_id AS uuid)
                  AND archived_at IS NULL
                GROUP BY document_id
            ) p ON p.document_id = d.id
            LEFT JOIN transport_contracts c ON c.id = d.contract_id AND c.company_id = d.company_id
            WHERE d.company_id = CAST(:company_id AS uuid)
              AND d.document_type = 'ticket'
              AND d.archived_at IS NULL
              AND (:start_date = '' OR d.created_at >= CAST(:start_date AS date))
              AND (:end_date = '' OR d.created_at < (CAST(:end_date AS date) + INTERVAL '1 day'))
              AND (
                :status_filter = 'all'
                OR (:status_filter = 'pending_treasury' AND d.treasury_check = false)
                OR (:status_filter = 'ready' AND d.supervisor_check = true AND d.treasury_check = true AND d.status NOT IN ('billed','completed','cancelled'))
                OR (:status_filter = 'billed' AND d.status = 'billed')
                OR d.status = :status_filter
              )
              AND (
                :query = '%%'
                OR LOWER(d.document_number) LIKE :query
                OR LOWER(d.client_name) LIKE :query
                OR LOWER(d.phone) LIKE :query
                OR LOWER(d.document_id) LIKE :query
                OR LOWER(d.contract_code) LIKE :query
                OR LOWER(d.origin) LIKE :query
                OR LOWER(d.destination) LIKE :query
              )
            ORDER BY d.updated_at DESC, d.created_at DESC
            LIMIT :limit
            """
        ),
        {
            "company_id": str(company_id),
            "query": query,
            "status_filter": status_value or "all",
            "start_date": _clean(start_date, 20),
            "end_date": _clean(end_date, 20),
            "limit": int(limit),
        },
    )
    tickets = [_row(row) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "tickets": tickets, "count": len(tickets)}


@router.get("/companies/{company_id}/payments", dependencies=[Depends(require_transport_payments_read)])
async def list_transport_payments(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=80, ge=1, le=300),
    search: str = Query(default="", max_length=120),
    status_filter: str = Query(default="all", alias="status", max_length=40),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    query = f"%{_clean(search, 120).lower()}%"
    result = await db.execute(
        text(
            """
            SELECT *
            FROM transport_payment_records
            WHERE company_id = CAST(:company_id AS uuid)
              AND archived_at IS NULL
              AND (:status_filter = 'all' OR status = :status_filter)
              AND (:start_date = '' OR COALESCE(paid_at, created_at) >= CAST(:start_date AS date))
              AND (:end_date = '' OR COALESCE(paid_at, created_at) < (CAST(:end_date AS date) + INTERVAL '1 day'))
              AND (
                :query = '%%'
                OR LOWER(document_number) LIKE :query
                OR LOWER(client_name) LIKE :query
                OR LOWER(contract_code) LIKE :query
                OR LOWER(payment_reference) LIKE :query
              )
            ORDER BY COALESCE(paid_at, created_at) DESC
            LIMIT :limit
            """
        ),
        {
            "company_id": str(company_id),
            "query": query,
            "status_filter": _payment_status(status_filter) if status_filter != "all" else "all",
            "start_date": _clean(start_date, 20),
            "end_date": _clean(end_date, 20),
            "limit": int(limit),
        },
    )
    payments = [_payment_payload(row, company_id) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "payments": payments, "count": len(payments)}


@router.patch("/companies/{company_id}/tickets/{document_id}/treasury-check", dependencies=[Depends(require_transport_payments_write)])
async def update_transport_treasury_check(
    company_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: TreasuryCheckIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    status_value = _document_status(payload.status)
    result = await db.execute(
        text(
            """
            UPDATE transport_service_documents
            SET treasury_check = :treasury_check,
                status = CASE WHEN :status_value = '' THEN status ELSE :status_value END,
                notes = CASE
                    WHEN :notes = '' THEN notes
                    WHEN notes = '' THEN :notes
                    ELSE notes || E'\n' || :notes
                END,
                updated_at = now()
            WHERE company_id = CAST(:company_id AS uuid)
              AND id = CAST(:document_id AS uuid)
              AND document_type = 'ticket'
              AND archived_at IS NULL
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "document_id": str(document_id),
            "treasury_check": bool(payload.treasury_check),
            "status_value": status_value,
            "notes": _clean(payload.notes or (f"Check tesoreria por {_clean(payload.created_by, 180)}" if payload.created_by else ""), 1600),
        },
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="ticket_not_found")
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "ticket": _row(row)}


@router.post("/companies/{company_id}/payments", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_transport_payments_write)])
async def create_transport_payment(company_id: uuid.UUID, payload: TransportPaymentIn, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    document_id = _clean(payload.document_id, 80)
    if not document_id:
        raise HTTPException(status_code=400, detail="document_id_required")
    ticket = await _ticket_document(db, company_id, document_id)
    total = _money(ticket.get("total_amount"))
    paid_before = _money(ticket.get("paid_amount"))
    remaining = max(total - paid_before, 0)
    amount = _money(payload.amount) or remaining or total
    payment_status = _payment_status(payload.status)
    result = await db.execute(
        text(
            """
            INSERT INTO transport_payment_records (
                company_id, document_id, contract_id, document_number, contract_code, client_name, record_type,
                payment_method, payment_reference, amount, status, paid_at, created_by, notes, created_at, updated_at
            )
            VALUES (
                CAST(:company_id AS uuid), CAST(:document_id AS uuid), CAST(:contract_id AS uuid), :document_number,
                :contract_code, :client_name, 'ticket_payment', :payment_method, :payment_reference, :amount, :status,
                CASE WHEN :status = 'paid' THEN now() ELSE NULL END, :created_by, :notes, now(), now()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "document_id": document_id,
            "contract_id": ticket.get("contract_id"),
            "document_number": _clean(ticket.get("document_number"), 60),
            "contract_code": _clean(ticket.get("contract_code"), 120),
            "client_name": _clean(ticket.get("client_name"), 180),
            "payment_method": _clean(payload.payment_method or "transfer", 60),
            "payment_reference": _clean(payload.payment_reference, 160),
            "amount": amount,
            "status": payment_status,
            "created_by": _clean(payload.created_by, 180),
            "notes": _clean(payload.notes, 1600),
        },
    )
    payment = _payment_payload(result.first() or {}, company_id)
    document_status = "billed" if payment_status == "paid" and (paid_before + amount) >= total else ""
    if payment_status == "paid":
        await db.execute(
            text(
                """
                UPDATE transport_service_documents
                SET treasury_check = true,
                    status = CASE WHEN :document_status = '' THEN status ELSE :document_status END,
                    updated_at = now()
                WHERE company_id = CAST(:company_id AS uuid)
                  AND id = CAST(:document_id AS uuid)
                """
            ),
            {"company_id": str(company_id), "document_id": document_id, "document_status": document_status},
        )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "payment": payment}

@router.get("/companies/{company_id}/mail-settings", dependencies=[Depends(require_transport_payments_read)])
async def get_transport_mail_settings(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    return {"ok": True, "company_id": str(company_id), "mail_settings": await _transport_mail_settings(db, company_id)}


@router.put("/companies/{company_id}/mail-settings", dependencies=[Depends(require_transport_payments_write)])
async def update_transport_mail_settings(
    company_id: uuid.UUID,
    payload: TransportMailSettingsIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    await db.execute(
        text(
            """
            INSERT INTO transport_payment_mail_settings (
                company_id, sender_name, reply_to_email, cc_email, signature, updated_by, created_at, updated_at
            )
            VALUES (
                CAST(:company_id AS uuid), :sender_name, :reply_to_email, :cc_email,
                :signature, :updated_by, now(), now()
            )
            ON CONFLICT (company_id) DO UPDATE SET
                sender_name = EXCLUDED.sender_name,
                reply_to_email = EXCLUDED.reply_to_email,
                cc_email = EXCLUDED.cc_email,
                signature = EXCLUDED.signature,
                updated_by = EXCLUDED.updated_by,
                updated_at = now()
            """
        ),
        {
            "company_id": str(company_id),
            "sender_name": _clean(payload.sender_name, 120),
            "reply_to_email": _valid_optional_email(payload.reply_to_email),
            "cc_email": _valid_optional_email(payload.cc_email),
            "signature": _clean(payload.signature, 1200),
            "updated_by": _clean(payload.updated_by, 180),
        },
    )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "mail_settings": await _transport_mail_settings(db, company_id)}


@router.get("/companies/{company_id}/invoices", dependencies=[Depends(require_transport_payments_read)])
async def list_transport_invoices(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=80, ge=1, le=300),
    search: str = Query(default="", max_length=120),
    status_filter: str = Query(default="all", alias="status", max_length=40),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    query = f"%{_clean(search, 120).lower()}%"
    status_value = _invoice_status(status_filter) if status_filter != "all" else "all"
    result = await db.execute(
        text(
            """
            SELECT *
            FROM transport_invoice_records
            WHERE company_id = CAST(:company_id AS uuid)
              AND archived_at IS NULL
              AND (:status_filter = 'all' OR status = :status_filter)
              AND (:start_date = '' OR created_at >= CAST(:start_date AS date))
              AND (:end_date = '' OR created_at < (CAST(:end_date AS date) + INTERVAL '1 day'))
              AND (
                :query = '%%'
                OR LOWER(invoice_number) LIKE :query
                OR LOWER(document_number) LIKE :query
                OR LOWER(client_name) LIKE :query
                OR LOWER(contract_code) LIKE :query
                OR LOWER(recipient) LIKE :query
              )
            ORDER BY due_date NULLS LAST, created_at DESC
            LIMIT :limit
            """
        ),
        {
            "company_id": str(company_id),
            "query": query,
            "status_filter": status_value,
            "start_date": _clean(start_date, 20),
            "end_date": _clean(end_date, 20),
            "limit": int(limit),
        },
    )
    invoices = [_row(row) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "invoices": invoices, "count": len(invoices)}


@router.get("/companies/{company_id}/alerts", dependencies=[Depends(require_transport_payments_read)])
async def list_transport_payment_alerts(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    low_result = await db.execute(
        text(
            """
            SELECT *, GREATEST(initial_balance - consumed_balance, 0) AS available_balance
            FROM transport_contracts
            WHERE company_id = CAST(:company_id AS uuid)
              AND archived_at IS NULL
              AND status <> 'archived'
              AND GREATEST(initial_balance - consumed_balance, 0) <= alert_balance
            ORDER BY available_balance ASC, updated_at DESC
            LIMIT :limit
            """
        ),
        {"company_id": str(company_id), "limit": int(limit)},
    )
    invoice_result = await db.execute(
        text(
            """
            SELECT *
            FROM transport_invoice_records
            WHERE company_id = CAST(:company_id AS uuid)
              AND archived_at IS NULL
              AND status IN ('draft','sent')
              AND (due_date IS NULL OR due_date <= CURRENT_DATE + INTERVAL '7 days')
            ORDER BY due_date NULLS LAST, created_at DESC
            LIMIT :limit
            """
        ),
        {"company_id": str(company_id), "limit": int(limit)},
    )
    low_contracts = [_row(row) for row in low_result.fetchall()]
    due_invoices = [_row(row) for row in invoice_result.fetchall()]
    return {
        "ok": True,
        "company_id": str(company_id),
        "low_balance_contracts": low_contracts,
        "due_invoices": due_invoices,
        "low_balance_count": len(low_contracts),
        "due_invoice_count": len(due_invoices),
    }


async def _create_transport_contract_credit_record(
    company_id: uuid.UUID,
    contract_id: uuid.UUID,
    amount_value: Any,
    payment_method: Any,
    payment_reference: Any,
    created_by: Any,
    notes: Any,
    db: AsyncSession,
    proof: UploadFile | None = None,
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    amount = _money(amount_value)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount_required")
    proof_name, proof_type, proof_bytes, proof_size = await _read_payment_proof_upload(proof)
    contract = await _contract_by_id(db, company_id, str(contract_id))
    result = await db.execute(
        text(
            """
            INSERT INTO transport_payment_records (
                company_id, document_id, contract_id, document_number, contract_code, client_name, record_type,
                payment_method, payment_reference, amount, status, paid_at, created_by, notes,
                proof_original_name, proof_content_type, proof_file_bytes, proof_file_size, created_at, updated_at
            )
            VALUES (
                CAST(:company_id AS uuid), NULL, CAST(:contract_id AS uuid), :document_number,
                :contract_code, :client_name, 'contract_credit', :payment_method, :payment_reference,
                :amount, 'paid', now(), :created_by, :notes,
                :proof_original_name, :proof_content_type, :proof_file_bytes, :proof_file_size, now(), now()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "contract_id": str(contract_id),
            "document_number": "CREDITO",
            "contract_code": _clean(contract.get("contract_code"), 120),
            "client_name": _clean(contract.get("client_name"), 180),
            "payment_method": _clean(payment_method or "transfer", 60),
            "payment_reference": _clean(payment_reference, 160),
            "amount": amount,
            "created_by": _clean(created_by, 180),
            "notes": _clean(notes, 1600),
            "proof_original_name": proof_name,
            "proof_content_type": proof_type,
            "proof_file_bytes": proof_bytes,
            "proof_file_size": proof_size,
        },
    )
    payment = _payment_payload(result.first() or {}, company_id)
    updated = await db.execute(
        text(
            """
            UPDATE transport_contracts
            SET initial_balance = COALESCE(initial_balance, 0) + :amount,
                last_updated_by = :created_by,
                notes = CASE
                    WHEN :notes = '' THEN notes
                    WHEN notes = '' THEN :notes
                    ELSE notes || E'\n' || :notes
                END,
                updated_at = now()
            WHERE company_id = CAST(:company_id AS uuid)
              AND id = CAST(:contract_id AS uuid)
            RETURNING *, GREATEST(initial_balance - consumed_balance, 0) AS available_balance
            """
        ),
        {
            "company_id": str(company_id),
            "contract_id": str(contract_id),
            "amount": amount,
            "created_by": _clean(created_by, 180),
            "notes": _clean(notes or f"Credito agregado por {_clean(created_by, 180) or 'Tesoreria'}: {amount}", 1600),
        },
    )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "payment": payment, "contract": _row(updated.first() or {})}


@router.post("/companies/{company_id}/contracts/{contract_id}/credits", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_transport_payments_write)])
async def create_transport_contract_credit(
    company_id: uuid.UUID,
    contract_id: uuid.UUID,
    payload: TransportCreditIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _create_transport_contract_credit_record(
        company_id,
        contract_id,
        payload.amount,
        payload.payment_method,
        payload.payment_reference,
        payload.created_by,
        payload.notes,
        db,
    )


@router.post("/companies/{company_id}/contracts/{contract_id}/credits-with-proof", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_transport_payments_write)])
async def create_transport_contract_credit_with_proof(
    company_id: uuid.UUID,
    contract_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    amount: float = Form(default=0),
    payment_method: str = Form(default="transfer"),
    payment_reference: str = Form(default=""),
    created_by: str = Form(default=""),
    notes: str = Form(default=""),
    proof: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    return await _create_transport_contract_credit_record(
        company_id,
        contract_id,
        amount,
        payment_method,
        payment_reference,
        created_by,
        notes,
        db,
        proof=proof,
    )


@router.get("/companies/{company_id}/payments/{payment_id}/proof", dependencies=[Depends(require_transport_payments_read)])
async def get_transport_payment_proof(company_id: uuid.UUID, payment_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    await ensure_transport_payments_storage(db)
    result = await db.execute(
        text(
            """
            SELECT proof_original_name, proof_content_type, proof_file_bytes
            FROM transport_payment_records
            WHERE company_id = CAST(:company_id AS uuid)
              AND id = CAST(:payment_id AS uuid)
              AND archived_at IS NULL
            LIMIT 1
            """
        ),
        {"company_id": str(company_id), "payment_id": str(payment_id)},
    )
    row = _row(result.first() or {})
    content = row.get("proof_file_bytes")
    if not row or not content:
        raise HTTPException(status_code=404, detail="proof_not_found")
    filename = _clean(row.get("proof_original_name") or "comprobante", 260).replace('"', "")
    return Response(
        content=bytes(content),
        media_type=_clean(row.get("proof_content_type") or "application/octet-stream", 120),
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


async def _create_transport_invoice_record(
    company_id: uuid.UUID,
    payload: TransportInvoiceIn,
    db: AsyncSession,
    attachment: UploadFile | None = None,
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    document_id = _clean(payload.document_id, 80)
    contract_id = _clean(payload.contract_id, 80)
    ticket: dict[str, Any] | None = None
    contract: dict[str, Any] | None = None
    if document_id:
        ticket = await _ticket_document(db, company_id, document_id)
        contract_id = _clean(ticket.get("contract_id"), 80) or contract_id
    if contract_id:
        contract = await _contract_by_id(db, company_id, contract_id)
    if not ticket and not contract:
        raise HTTPException(status_code=400, detail="document_or_contract_required")

    amount = _money(payload.amount)
    if amount <= 0 and ticket:
        amount = max(_money(ticket.get("total_amount")) - _money(ticket.get("paid_amount")), 0) or _money(ticket.get("total_amount"))
    if amount <= 0 and contract:
        amount = _money(contract.get("available_balance"))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount_required")

    invoice_number = await _next_invoice_number(db, company_id)
    status_value = _invoice_status(payload.status)
    document_number = _clean((ticket or {}).get("document_number"), 60)
    contract_code = _clean((ticket or contract or {}).get("contract_code"), 120)
    client_name = _clean((ticket or contract or {}).get("client_name"), 180)
    recipient = _clean(payload.recipient or (ticket or contract or {}).get("email") or (ticket or contract or {}).get("phone"), 180)
    channel_value = _channel(payload.channel)
    attachment_name, attachment_content = await _read_invoice_attachment(attachment)
    company: dict[str, Any] = {}
    if channel_value == "email":
        recipient = _valid_optional_email(recipient)
        if not recipient:
            raise HTTPException(status_code=400, detail="recipient_email_required")
        company = await _company(db, company_id)
        if not attachment_content and ticket:
            attachment_name = f"{document_number or invoice_number}.pdf"
            attachment_content = _build_service_document_pdf(company, ticket)

    result = await db.execute(
        text(
            """
            INSERT INTO transport_invoice_records (
                company_id, document_id, contract_id, invoice_number, document_number, contract_code, client_name,
                recipient, channel, amount, due_date, status, sent_at, paid_at, created_by, notes,
                delivery_status, attachment_name, created_at, updated_at
            )
            VALUES (
                CAST(:company_id AS uuid), CAST(:document_id AS uuid), CAST(:contract_id AS uuid), :invoice_number,
                :document_number, :contract_code, :client_name, :recipient, :channel, :amount,
                CAST(NULLIF(:due_date, '') AS date), CAST(:status AS varchar),
                CASE WHEN CAST(:status AS varchar) IN ('sent','paid') THEN now() ELSE NULL END,
                CASE WHEN CAST(:status AS varchar) = 'paid' THEN now() ELSE NULL END,
                :created_by, :notes, :delivery_status, :attachment_name, now(), now()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "document_id": document_id or None,
            "contract_id": contract_id or None,
            "invoice_number": invoice_number,
            "document_number": document_number,
            "contract_code": contract_code,
            "client_name": client_name,
            "recipient": recipient,
            "channel": channel_value,
            "amount": amount,
            "due_date": _clean(payload.due_date, 20),
            "status": status_value,
            "created_by": _clean(payload.created_by, 180),
            "notes": _clean(payload.notes, 1600),
            "delivery_status": "pending" if channel_value == "email" else "prepared",
            "attachment_name": attachment_name,
        },
    )
    invoice = _row(result.first() or {})
    if document_id:
        await db.execute(
            text(
                """
                UPDATE transport_service_documents
                SET status = CASE WHEN status IN ('completed','cancelled') THEN status ELSE 'billed' END,
                    updated_at = now()
                WHERE company_id = CAST(:company_id AS uuid)
                  AND id = CAST(:document_id AS uuid)
                """
            ),
            {"company_id": str(company_id), "document_id": document_id},
        )
        invoice["invoice_url"] = f"/api/v1/transport-quotes-tickets/companies/{company_id}/documents/{document_id}/print.pdf?inline=false"

    if channel_value == "email":
        mail_settings = await _transport_mail_settings(db, company_id)
        sender_name = _clean(mail_settings.get("sender_name") or company.get("name") or "CLONEXA", 120)
        signature = _clean(mail_settings.get("signature"), 1200)
        due_text = f" con vencimiento {payload.due_date}" if _clean(payload.due_date, 20) else ""
        amount_text = f"$ {amount:,.0f}".replace(",", ".")
        plain_message = "\n".join(
            part for part in [
                f"Hola {client_name or 'cliente'},",
                f"Adjuntamos el cobro {invoice_number} por {amount_text}{due_text}.",
                _clean(payload.notes, 1600),
                signature,
            ] if part
        )
        html_message = "".join(
            [
                f"<p>Hola {html.escape(client_name or 'cliente')},</p>",
                f"<p>Adjuntamos el cobro <strong>{html.escape(invoice_number)}</strong> por "
                f"<strong>{html.escape(amount_text)}</strong>{html.escape(due_text)}.</p>",
                f"<p>{html.escape(_clean(payload.notes, 1600)).replace(chr(10), '<br>')}</p>" if _clean(payload.notes, 1600) else "",
                f"<p>{html.escape(signature).replace(chr(10), '<br>')}</p>" if signature else "",
            ]
        )
        try:
            delivery = await send_transactional_email(
                recipient=recipient,
                subject=f"Cobro {invoice_number} - {company.get('name') or 'CLONEXA'}",
                html=html_message,
                text=plain_message,
                sender_name=sender_name,
                reply_to=_clean(mail_settings.get("reply_to_email"), 180),
                cc=_clean(mail_settings.get("cc_email"), 180),
                attachment_name=attachment_name,
                attachment_content=attachment_content,
                idempotency_key=f"clonexa-transport-invoice-{company_id}-{invoice_number}",
            )
        except TransactionalEmailConfigurationError as exc:
            await db.rollback()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except TransactionalEmailDeliveryError as exc:
            await db.rollback()
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        await db.execute(
            text(
                """
                UPDATE transport_invoice_records
                SET provider_message_id = :message_id,
                    delivery_status = 'sent',
                    delivery_error = '',
                    status = 'sent',
                    sent_at = now(),
                    updated_at = now()
                WHERE company_id = CAST(:company_id AS uuid)
                  AND id = CAST(:invoice_id AS uuid)
                """
            ),
            {
                "company_id": str(company_id),
                "invoice_id": str(invoice.get("id") or ""),
                "message_id": _clean(delivery.get("message_id"), 180),
            },
        )
        invoice.update(
            {
                "provider_message_id": _clean(delivery.get("message_id"), 180),
                "delivery_status": "sent",
                "delivery_error": "",
                "status": "sent",
            }
        )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "invoice": invoice}


@router.post("/companies/{company_id}/invoices", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_transport_payments_write)])
async def create_transport_invoice(company_id: uuid.UUID, payload: TransportInvoiceIn, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await _create_transport_invoice_record(company_id, payload, db)


@router.post(
    "/companies/{company_id}/invoices-with-attachment",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_transport_payments_write)],
)
async def create_transport_invoice_with_attachment(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    document_id: str = Form(default=""),
    contract_id: str = Form(default=""),
    amount: float = Form(default=0),
    due_date: str = Form(default=""),
    recipient: str = Form(default=""),
    channel: str = Form(default="email"),
    status_value: str = Form(default="sent", alias="status"),
    created_by: str = Form(default=""),
    notes: str = Form(default=""),
    attachment: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    payload = TransportInvoiceIn(
        document_id=document_id,
        contract_id=contract_id,
        amount=amount,
        due_date=due_date,
        recipient=recipient,
        channel=channel,
        status=status_value,
        created_by=created_by,
        notes=notes,
    )
    return await _create_transport_invoice_record(company_id, payload, db, attachment=attachment)
