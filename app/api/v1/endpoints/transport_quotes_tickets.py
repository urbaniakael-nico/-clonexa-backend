from __future__ import annotations

import io
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import READ_ROLES, WRITE_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.api.v1.endpoints.transport_contracts import ensure_transport_contracts_storage
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()


async def require_transport_quotes_read(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    if await active_admin_v2_session(request, db):
        await require_enabled_module(db, company_id, "transport_quotes_tickets")
        return
    await require_company_user_for_tenant(
        db,
        authorization,
        company_id,
        allowed_roles=READ_ROLES,
        module_codes="transport_quotes_tickets",
    )


async def require_transport_quotes_write(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    if await active_admin_v2_session(request, db):
        await require_enabled_module(db, company_id, "transport_quotes_tickets")
        return
    await require_company_user_for_tenant(
        db,
        authorization,
        company_id,
        allowed_roles=WRITE_ROLES,
        module_codes="transport_quotes_tickets",
    )


class TransportAuthorizedPerson(BaseModel):
    document_id: str | None = Field(default="", max_length=80)
    name: str | None = Field(default="", max_length=180)
    ticket_count: int | None = Field(default=1, ge=0, le=999)


class TransportDocumentIn(BaseModel):
    document_type: str | None = Field(default="quote", max_length=20)
    status: str | None = Field(default="pending", max_length=40)
    contract_id: str | None = Field(default="", max_length=80)
    client_name: str | None = Field(default="", max_length=180)
    client_type: str | None = Field(default="company", max_length=40)
    phone: str | None = Field(default="", max_length=80)
    email: str | None = Field(default="", max_length=160)
    document_id: str | None = Field(default="", max_length=80)
    contract_code: str | None = Field(default="", max_length=120)
    account_code: str | None = Field(default="", max_length=120)
    validity_date: str | None = Field(default="", max_length=40)
    origin: str | None = Field(default="", max_length=160)
    destination: str | None = Field(default="", max_length=160)
    route_detail: str | None = Field(default="", max_length=220)
    service_date: str | None = Field(default="", max_length=40)
    ticket_count: int | None = Field(default=1, ge=0, le=999)
    authorized_people: list[TransportAuthorizedPerson] | None = Field(default_factory=list)
    transporter: str | None = Field(default="", max_length=180)
    value_amount: float | None = Field(default=0, ge=0)
    discount_amount: float | None = Field(default=0, ge=0)
    total_amount: float | None = Field(default=0, ge=0)
    charged_to_contract: bool | None = False
    approval_code: str | None = Field(default="", max_length=120)
    advisor_name: str | None = Field(default="", max_length=180)
    supervisor_check: bool | None = False
    treasury_check: bool | None = False
    notes: str | None = Field(default="", max_length=1600)


class TransportDocumentPatch(TransportDocumentIn):
    pass


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


def _document_type(value: Any) -> str:
    clean = _clean(value or "quote", 20).lower().replace(" ", "_")
    return clean if clean in {"quote", "ticket"} else "quote"


def _status(value: Any) -> str:
    clean = _clean(value or "pending", 40).lower().replace(" ", "_")
    allowed = {"pending", "approved", "rejected", "converted", "scheduled", "in_route", "completed", "cancelled", "billed"}
    return clean if clean in allowed else "pending"


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


def _people_json(people: list[TransportAuthorizedPerson] | None, fallback_name: str = "", fallback_document: str = "", tickets: int = 1) -> str:
    clean_people = []
    for person in people or []:
        name = _clean(person.name, 180)
        document_id = _clean(person.document_id, 80)
        count = max(0, int(person.ticket_count or 0))
        if name or document_id:
            clean_people.append({"document_id": document_id, "name": name, "ticket_count": count or 1})
    if not clean_people and (fallback_name or fallback_document):
        clean_people.append({"document_id": _clean(fallback_document, 80), "name": _clean(fallback_name, 180), "ticket_count": max(1, int(tickets or 1))})
    return json.dumps(clean_people, ensure_ascii=True)


async def ensure_transport_documents_storage(db: AsyncSession) -> None:
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS transport_service_documents (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id uuid NOT NULL,
                document_type varchar(20) NOT NULL DEFAULT 'quote',
                document_number varchar(40) NOT NULL DEFAULT '',
                status varchar(40) NOT NULL DEFAULT 'pending',
                contract_id uuid NULL,
                client_name varchar(180) NOT NULL DEFAULT '',
                client_type varchar(40) NOT NULL DEFAULT 'company',
                phone varchar(80) NOT NULL DEFAULT '',
                email varchar(160) NOT NULL DEFAULT '',
                document_id varchar(80) NOT NULL DEFAULT '',
                contract_code varchar(120) NOT NULL DEFAULT '',
                account_code varchar(120) NOT NULL DEFAULT '',
                validity_date varchar(40) NOT NULL DEFAULT '',
                origin varchar(160) NOT NULL DEFAULT '',
                destination varchar(160) NOT NULL DEFAULT '',
                route_detail varchar(220) NOT NULL DEFAULT '',
                service_date varchar(40) NOT NULL DEFAULT '',
                ticket_count integer NOT NULL DEFAULT 1,
                authorized_people jsonb NOT NULL DEFAULT '[]'::jsonb,
                transporter varchar(180) NOT NULL DEFAULT '',
                value_amount numeric(14,2) NOT NULL DEFAULT 0,
                discount_amount numeric(14,2) NOT NULL DEFAULT 0,
                total_amount numeric(14,2) NOT NULL DEFAULT 0,
                charged_to_contract boolean NOT NULL DEFAULT false,
                approval_code varchar(120) NOT NULL DEFAULT '',
                advisor_name varchar(180) NOT NULL DEFAULT '',
                supervisor_check boolean NOT NULL DEFAULT false,
                treasury_check boolean NOT NULL DEFAULT false,
                notes text NOT NULL DEFAULT '',
                source_quote_id uuid NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                archived_at timestamptz NULL
            )
            """
        )
    )
    for statement in [
        "CREATE INDEX IF NOT EXISTS ix_transport_docs_company_type ON transport_service_documents (company_id, document_type)",
        "CREATE INDEX IF NOT EXISTS ix_transport_docs_company_status ON transport_service_documents (company_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_transport_docs_company_contract ON transport_service_documents (company_id, contract_code)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_transport_docs_company_number ON transport_service_documents (company_id, document_number)",
    ]:
        await db.execute(text(statement))


async def _company(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    result = await db.execute(
        text("SELECT id, name, slug FROM companies WHERE id = CAST(:company_id AS uuid) LIMIT 1"),
        {"company_id": str(company_id)},
    )
    return _row(result.first() or {"id": company_id, "name": "CLONEXA Transporte", "slug": ""})


async def _consume_contract_for_ticket(db: AsyncSession, company_id: uuid.UUID, contract_id: str, amount: float) -> None:
    if not contract_id or _money(amount) <= 0:
        return
    await db.execute(
        text(
            """
            UPDATE transport_contracts
            SET consumed_balance = LEAST(COALESCE(initial_balance, 0), COALESCE(consumed_balance, 0) + :amount),
                updated_at = now()
            WHERE company_id = CAST(:company_id AS uuid)
              AND id = CAST(:contract_id AS uuid)
            """
        ),
        {"company_id": str(company_id), "contract_id": contract_id, "amount": _money(amount)},
    )


async def _contract(db: AsyncSession, company_id: uuid.UUID, contract_id: str = "", contract_code: str = "") -> dict[str, Any] | None:
    await ensure_transport_contracts_storage(db)
    where = "id = CAST(:contract_id AS uuid)" if contract_id else "LOWER(contract_code) = LOWER(:contract_code)"
    params = {"company_id": str(company_id), "contract_id": contract_id or str(uuid.uuid4()), "contract_code": contract_code}
    result = await db.execute(
        text(
            f"""
            SELECT *, GREATEST(initial_balance - consumed_balance, 0) AS available_balance
            FROM transport_contracts
            WHERE company_id = CAST(:company_id AS uuid)
              AND {where}
            LIMIT 1
            """
        ),
        params,
    )
    row = result.first()
    return _row(row) if row else None


async def _next_number(db: AsyncSession, company_id: uuid.UUID, document_type: str) -> str:
    prefix = "TKT" if document_type == "ticket" else "COT"
    result = await db.execute(
        text(
            """
            SELECT COUNT(*) + 1 AS next_value
            FROM transport_service_documents
            WHERE company_id = CAST(:company_id AS uuid)
              AND document_type = :document_type
            """
        ),
        {"company_id": str(company_id), "document_type": document_type},
    )
    row = result.first()
    value = int((row._mapping.get("next_value") if row else 1) or 1)
    return f"{prefix}-{value:06d}"


def _select_documents_sql(where_extra: str = "") -> str:
    return f"""
        SELECT *
        FROM transport_service_documents
        WHERE company_id = CAST(:company_id AS uuid)
        {where_extra}
    """


@router.get("/companies/{company_id}/documents", dependencies=[Depends(require_transport_quotes_read)])
async def list_transport_documents(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=80, ge=1, le=300),
    document_type: str = Query(default="all", max_length=20),
    status_filter: str = Query(default="all", alias="status", max_length=40),
    search: str = Query(default="", max_length=120),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
) -> dict[str, Any]:
    await ensure_transport_documents_storage(db)
    where = """
      AND (:document_type = 'all' OR document_type = :document_type)
      AND (:status_filter = 'all' OR status = :status_filter)
      AND (:start_date = '' OR created_at >= CAST(:start_date AS date))
      AND (:end_date = '' OR created_at < (CAST(:end_date AS date) + INTERVAL '1 day'))
      AND (
        :query = '%%'
        OR LOWER(document_number) LIKE :query
        OR LOWER(client_name) LIKE :query
        OR LOWER(phone) LIKE :query
        OR LOWER(document_id) LIKE :query
        OR LOWER(contract_code) LIKE :query
        OR LOWER(origin) LIKE :query
        OR LOWER(destination) LIKE :query
      )
    """
    result = await db.execute(
        text(_select_documents_sql(where) + " ORDER BY updated_at DESC, created_at DESC LIMIT :limit"),
        {
            "company_id": str(company_id),
            "document_type": _document_type(document_type) if document_type != "all" else "all",
            "status_filter": _status(status_filter) if status_filter != "all" else "all",
            "query": f"%{_clean(search, 120).lower()}%",
            "start_date": _clean(start_date, 20),
            "end_date": _clean(end_date, 20),
            "limit": int(limit),
        },
    )
    docs = [_row(row) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "documents": docs, "count": len(docs)}


@router.get("/companies/{company_id}/summary", dependencies=[Depends(require_transport_quotes_read)])
async def transport_documents_summary(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
) -> dict[str, Any]:
    await ensure_transport_documents_storage(db)
    result = await db.execute(
        text(
            """
            SELECT
                COUNT(*) AS total_count,
                COUNT(*) FILTER (WHERE document_type = 'quote') AS quote_count,
                COUNT(*) FILTER (WHERE document_type = 'ticket') AS ticket_count,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
                COUNT(*) FILTER (WHERE status IN ('approved','scheduled','in_route')) AS active_count,
                COALESCE(SUM(total_amount), 0) AS total_amount
            FROM transport_service_documents
            WHERE company_id = CAST(:company_id AS uuid)
              AND archived_at IS NULL
              AND (:start_date = '' OR created_at >= CAST(:start_date AS date))
              AND (:end_date = '' OR created_at < (CAST(:end_date AS date) + INTERVAL '1 day'))
            """
        ),
        {"company_id": str(company_id), "start_date": _clean(start_date, 20), "end_date": _clean(end_date, 20)},
    )
    return {"ok": True, "company_id": str(company_id), "summary": _row(result.first() or {})}


@router.post("/companies/{company_id}/documents", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_transport_quotes_write)])
async def create_transport_document(company_id: uuid.UUID, payload: TransportDocumentIn, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_transport_documents_storage(db)
    doc_type = _document_type(payload.document_type)
    linked_contract = await _contract(db, company_id, _clean(payload.contract_id, 80), _clean(payload.contract_code, 120))
    total = _money(payload.total_amount) or max(0, _money(payload.value_amount) - _money(payload.discount_amount))
    ticket_count = max(0, int(payload.ticket_count or 1))
    document_number = await _next_number(db, company_id, doc_type)
    result = await db.execute(
        text(
            """
            INSERT INTO transport_service_documents (
                company_id, document_type, document_number, status, contract_id,
                client_name, client_type, phone, email, document_id, contract_code, account_code, validity_date,
                origin, destination, route_detail, service_date, ticket_count, authorized_people, transporter,
                value_amount, discount_amount, total_amount, charged_to_contract, approval_code, advisor_name,
                supervisor_check, treasury_check, notes, created_at, updated_at
            )
            VALUES (
                CAST(:company_id AS uuid), :document_type, :document_number, :status, CAST(:contract_id AS uuid),
                :client_name, :client_type, :phone, :email, :document_id, :contract_code, :account_code, :validity_date,
                :origin, :destination, :route_detail, :service_date, :ticket_count, CAST(:authorized_people AS jsonb), :transporter,
                :value_amount, :discount_amount, :total_amount, :charged_to_contract, :approval_code, :advisor_name,
                :supervisor_check, :treasury_check, :notes, now(), now()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "document_type": doc_type,
            "document_number": document_number,
            "status": _status(payload.status or ("scheduled" if doc_type == "ticket" else "pending")),
            "contract_id": str(linked_contract.get("id")) if linked_contract else None,
            "client_name": _clean(payload.client_name or (linked_contract or {}).get("client_name"), 180),
            "client_type": _clean(payload.client_type or (linked_contract or {}).get("client_type") or "company", 40),
            "phone": _clean(payload.phone or (linked_contract or {}).get("phone"), 80),
            "email": _clean(payload.email or (linked_contract or {}).get("email"), 160),
            "document_id": _clean(payload.document_id or (linked_contract or {}).get("document_id"), 80),
            "contract_code": _clean(payload.contract_code or (linked_contract or {}).get("contract_code"), 120),
            "account_code": _clean(payload.account_code, 120),
            "validity_date": _clean(payload.validity_date, 40),
            "origin": _clean(payload.origin, 160),
            "destination": _clean(payload.destination, 160),
            "route_detail": _clean(payload.route_detail, 220),
            "service_date": _clean(payload.service_date, 40),
            "ticket_count": ticket_count,
            "authorized_people": _people_json(payload.authorized_people, payload.client_name or (linked_contract or {}).get("client_name", ""), payload.document_id or (linked_contract or {}).get("document_id", ""), ticket_count),
            "transporter": _clean(payload.transporter, 180),
            "value_amount": _money(payload.value_amount),
            "discount_amount": _money(payload.discount_amount),
            "total_amount": total,
            "charged_to_contract": bool(payload.charged_to_contract or (doc_type == "ticket" and linked_contract)),
            "approval_code": _clean(payload.approval_code or str(uuid.uuid4().int)[-10:], 120),
            "advisor_name": _clean(payload.advisor_name, 180),
            "supervisor_check": bool(payload.supervisor_check),
            "treasury_check": bool(payload.treasury_check),
            "notes": _clean(payload.notes, 1600),
        },
    )
    row = result.first()
    if doc_type == "ticket" and linked_contract and total > 0:
        await _consume_contract_for_ticket(db, company_id, str(linked_contract.get("id") or ""), total)
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "document": _row(row)}


@router.patch("/companies/{company_id}/documents/{document_id}", dependencies=[Depends(require_transport_quotes_write)])
async def update_transport_document(company_id: uuid.UUID, document_id: uuid.UUID, payload: TransportDocumentPatch, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_transport_documents_storage(db)
    data = payload.model_dump(exclude_unset=True)
    allowed = {
        "status", "client_name", "client_type", "phone", "email", "document_id", "contract_code", "account_code",
        "validity_date", "origin", "destination", "route_detail", "service_date", "ticket_count", "authorized_people",
        "transporter", "value_amount", "discount_amount", "total_amount", "charged_to_contract", "approval_code",
        "advisor_name", "supervisor_check", "treasury_check", "notes",
    }
    params: dict[str, Any] = {"company_id": str(company_id), "document_id_param": str(document_id)}
    updates: list[str] = []
    for key, value in data.items():
        if key not in allowed:
            continue
        db_key = "document_id" if key == "document_id" else key
        if key in {"value_amount", "discount_amount", "total_amount"}:
            params[key] = _money(value)
        elif key == "ticket_count":
            params[key] = max(0, int(value or 0))
        elif key == "authorized_people":
            params[key] = _people_json([TransportAuthorizedPerson(**item) if isinstance(item, dict) else item for item in (value or [])])
            updates.append(f"{db_key} = CAST(:{key} AS jsonb)")
            continue
        elif key in {"charged_to_contract", "supervisor_check", "treasury_check"}:
            params[key] = bool(value)
        elif key == "status":
            params[key] = _status(value)
        else:
            params[key] = _clean(value, 1600 if key == "notes" else 220)
        updates.append(f"{db_key} = :{key}")
    if not updates:
        raise HTTPException(status_code=400, detail="no_fields_to_update")
    updates.append("updated_at = now()")
    result = await db.execute(
        text(
            f"""
            UPDATE transport_service_documents
            SET {', '.join(updates)}
            WHERE id = CAST(:document_id_param AS uuid)
              AND company_id = CAST(:company_id AS uuid)
            RETURNING *
            """
        ),
        params,
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="document_not_found")
    await db.commit()
    return {"ok": True, "company_id": str(company_id), "document": _row(row)}


@router.post("/companies/{company_id}/documents/{document_id}/convert-ticket", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_transport_quotes_write)])
async def convert_quote_to_ticket(company_id: uuid.UUID, document_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_transport_documents_storage(db)
    result = await db.execute(
        text(_select_documents_sql("AND id = CAST(:document_id AS uuid) LIMIT 1")),
        {"company_id": str(company_id), "document_id": str(document_id)},
    )
    quote = _row(result.first() or {})
    if not quote:
        raise HTTPException(status_code=404, detail="quote_not_found")
    payload = TransportDocumentIn(**{**quote, "document_type": "ticket", "status": "scheduled"})
    created = await create_transport_document(company_id, payload, db)
    await update_transport_document(company_id, document_id, TransportDocumentPatch(status="converted"), db)
    return created


def _format_money(value: Any) -> str:
    return f"$ {int(round(_money(value))):,}".replace(",", ".")


def _pdf_text(value: Any, limit: int = 90) -> str:
    return _clean(value, limit) or "-"


def _build_service_document_pdf(company: dict[str, Any], document: dict[str, Any], inline_copy: str = "both") -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Motor PDF no disponible: {exc}") from exc

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(letter))
    width, height = landscape(letter)
    margin = 28
    gap = 18
    box_w = (width - (margin * 2) - gap) / 2
    box_h = height - 72
    y0 = 44
    doc_type = "Orden de Servicio" if document.get("document_type") == "ticket" else "Cotizacion de Servicio"
    people = document.get("authorized_people") or []
    if isinstance(people, str):
        try:
            people = json.loads(people)
        except Exception:
            people = []

    def draw_copy(x: float, label: str) -> None:
        pdf.setStrokeColor(colors.HexColor("#9ca3af"))
        pdf.setLineWidth(1)
        pdf.rect(x, y0, box_w, box_h)
        y = y0 + box_h - 28
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(x + 14, y, _pdf_text(company.get("name") or "CLONEXA Transporte", 28))
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawRightString(x + box_w - 14, y, doc_type)
        y -= 18
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawRightString(x + box_w - 14, y, _pdf_text(document.get("document_number"), 24))
        y -= 22
        pdf.setFont("Helvetica", 10)
        pdf.drawString(x + 14, y, f"Cliente: {_pdf_text(document.get('client_name'), 48)}")
        pdf.drawRightString(x + box_w - 14, y, f"Cuenta: {_pdf_text(document.get('account_code'), 24)}")
        y -= 14
        pdf.drawString(x + 14, y, f"Contrato: {_pdf_text(document.get('contract_code'), 38)}")
        pdf.drawRightString(x + box_w - 14, y, f"Vigencia: {_pdf_text(document.get('validity_date'), 20)}")
        y -= 14
        pdf.drawString(x + 14, y, f"Fecha: {_pdf_text(document.get('service_date') or document.get('created_at'), 28)}")
        y -= 18
        pdf.setFillColor(colors.HexColor("#d1d5db"))
        pdf.rect(x, y - 4, box_w, 16, fill=1, stroke=0)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawCentredString(x + box_w / 2, y, "Ruta")
        y -= 20
        pdf.setFont("Helvetica", 10)
        pdf.drawString(x + 14, y, f"Origen: {_pdf_text(document.get('origin'), 58)}")
        y -= 14
        pdf.drawString(x + 14, y, f"Destino: {_pdf_text(document.get('destination'), 58)}")
        y -= 18
        pdf.setFillColor(colors.HexColor("#d1d5db"))
        pdf.rect(x, y - 4, box_w, 16, fill=1, stroke=0)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawCentredString(x + box_w / 2, y, "Personas Autorizadas")
        y -= 20
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(x + 14, y, "Id")
        pdf.drawString(x + 92, y, "Nombre")
        pdf.drawRightString(x + box_w - 18, y, "Tiquetes")
        y -= 12
        pdf.setFont("Helvetica", 8.5)
        rows = people if people else [{"document_id": document.get("document_id"), "name": document.get("client_name"), "ticket_count": document.get("ticket_count") or 1}]
        for person in rows[:7]:
            pdf.drawString(x + 14, y, _pdf_text(person.get("document_id"), 16))
            pdf.drawString(x + 92, y, _pdf_text(person.get("name"), 42))
            pdf.drawRightString(x + box_w - 20, y, str(person.get("ticket_count") or 1))
            y -= 12
        y -= 14
        pdf.setFont("Helvetica", 8.5)
        for line in [
            "Si presenta alguna novedad o inconveniente, comuniquese al PBX",
            "o escriba al canal operativo disponible las 24 horas del dia.",
            "La informacion recolectada se trata segun la Ley 1581 de 2012.",
        ]:
            pdf.drawString(x + 14, y, line)
            y -= 11
        y -= 10
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(x + 14, y, "Valor")
        pdf.drawRightString(x + box_w - 14, y, _format_money(document.get("total_amount")))
        y -= 20
        pdf.drawString(x + 14, y, "Autorizacion")
        pdf.line(x + 14, y - 22, x + box_w - 14, y - 22)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x + 14, y - 48, "Autorizado")
        pdf.drawCentredString(x + box_w / 2, y - 48, _pdf_text(document.get("approval_code"), 24))
        pdf.drawRightString(x + box_w - 14, y - 48, label)

    draw_copy(margin, "Original")
    draw_copy(margin + box_w + gap, "Copia")
    pdf.save()
    return buffer.getvalue()


@router.get("/companies/{company_id}/documents/{document_id}/print.pdf")
async def print_transport_document_pdf(
    company_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    inline: bool = Query(default=True),
) -> Response:
    await ensure_transport_documents_storage(db)
    result = await db.execute(
        text(_select_documents_sql("AND id = CAST(:document_id AS uuid) LIMIT 1")),
        {"company_id": str(company_id), "document_id": str(document_id)},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="document_not_found")
    document = _row(row)
    company = await _company(db, company_id)
    filename = f"{_clean(document.get('document_number'), 40) or 'documento_transporte'}.pdf"
    disposition = "inline" if inline else "attachment"
    return Response(
        content=_build_service_document_pdf(company, document),
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
