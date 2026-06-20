from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.transport_contracts import ensure_transport_contracts_storage
from app.api.v1.endpoints.transport_quotes_tickets import ensure_transport_documents_storage

router = APIRouter()


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
        "CREATE INDEX IF NOT EXISTS ix_transport_invoices_company_status ON transport_invoice_records (company_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_transport_invoices_company_due ON transport_invoice_records (company_id, due_date)",
        "CREATE INDEX IF NOT EXISTS ix_transport_invoices_company_doc ON transport_invoice_records (company_id, document_id)",
    ]:
        await db.execute(text(statement))


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


@router.get("/companies/{company_id}/summary")
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


@router.get("/companies/{company_id}/queue")
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


@router.get("/companies/{company_id}/payments")
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
    payments = [_row(row) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "payments": payments, "count": len(payments)}


@router.patch("/companies/{company_id}/tickets/{document_id}/treasury-check")
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


@router.post("/companies/{company_id}/payments", status_code=status.HTTP_201_CREATED)
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
    payment = _row(result.first() or {})
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

@router.get("/companies/{company_id}/invoices")
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


@router.get("/companies/{company_id}/alerts")
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


@router.post("/companies/{company_id}/contracts/{contract_id}/credits", status_code=status.HTTP_201_CREATED)
async def create_transport_contract_credit(
    company_id: uuid.UUID,
    contract_id: uuid.UUID,
    payload: TransportCreditIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_payments_storage(db)
    amount = _money(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount_required")
    contract = await _contract_by_id(db, company_id, str(contract_id))
    result = await db.execute(
        text(
            """
            INSERT INTO transport_payment_records (
                company_id, document_id, contract_id, document_number, contract_code, client_name, record_type,
                payment_method, payment_reference, amount, status, paid_at, created_by, notes, created_at, updated_at
            )
            VALUES (
                CAST(:company_id AS uuid), NULL, CAST(:contract_id AS uuid), :document_number,
                :contract_code, :client_name, 'contract_credit', :payment_method, :payment_reference,
                :amount, 'paid', now(), :created_by, :notes, now(), now()
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
            "payment_method": _clean(payload.payment_method or "transfer", 60),
            "payment_reference": _clean(payload.payment_reference, 160),
            "amount": amount,
            "created_by": _clean(payload.created_by, 180),
            "notes": _clean(payload.notes, 1600),
        },
    )
    payment = _row(result.first() or {})
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
            "created_by": _clean(payload.created_by, 180),
            "notes": _clean(payload.notes or f"Credito agregado por {_clean(payload.created_by, 180) or 'Tesoreria'}: {amount}", 1600),
        },
    )
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "payment": payment, "contract": _row(updated.first() or {})}


@router.post("/companies/{company_id}/invoices", status_code=status.HTTP_201_CREATED)
async def create_transport_invoice(company_id: uuid.UUID, payload: TransportInvoiceIn, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
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
    result = await db.execute(
        text(
            """
            INSERT INTO transport_invoice_records (
                company_id, document_id, contract_id, invoice_number, document_number, contract_code, client_name,
                recipient, channel, amount, due_date, status, sent_at, paid_at, created_by, notes, created_at, updated_at
            )
            VALUES (
                CAST(:company_id AS uuid), CAST(:document_id AS uuid), CAST(:contract_id AS uuid), :invoice_number,
                :document_number, :contract_code, :client_name, :recipient, :channel, :amount,
                CAST(NULLIF(:due_date, '') AS date), :status,
                CASE WHEN :status IN ('sent','paid') THEN now() ELSE NULL END,
                CASE WHEN :status = 'paid' THEN now() ELSE NULL END,
                :created_by, :notes, now(), now()
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
            "channel": _channel(payload.channel),
            "amount": amount,
            "due_date": _clean(payload.due_date, 20),
            "status": status_value,
            "created_by": _clean(payload.created_by, 180),
            "notes": _clean(payload.notes, 1600),
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
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "invoice": invoice}
