from __future__ import annotations

import csv
import io
import unicodedata
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, READ_ROLES, get_db, require_company_user_for_tenant

router = APIRouter()

TRANSPORT_CONTRACT_MANAGER_ROLES = ADMIN_ROLES | {"manager", "gerencia", "gerente", "supervisor", "tesoreria"}


async def require_transport_contracts_read(
    company_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    await require_company_user_for_tenant(
        db,
        authorization,
        company_id,
        allowed_roles=READ_ROLES,
        module_codes="transport_contracts",
    )


async def require_transport_contracts_manage(
    company_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    await require_company_user_for_tenant(
        db,
        authorization,
        company_id,
        allowed_roles=TRANSPORT_CONTRACT_MANAGER_ROLES,
        module_codes="transport_contracts",
    )


class TransportContractIn(BaseModel):
    client_name: str | None = Field(default="", max_length=180)
    client_type: str | None = Field(default="company", max_length=40)
    phone: str | None = Field(default="", max_length=80)
    email: str | None = Field(default="", max_length=160)
    document_id: str | None = Field(default="", max_length=80)
    contract_code: str | None = Field(default="", max_length=120)
    initial_balance: float | None = Field(default=0, ge=0)
    consumed_balance: float | None = Field(default=0, ge=0)
    alert_balance: float | None = Field(default=2_000_000, ge=0)
    status: str | None = Field(default="active", max_length=40)
    authorized_contacts: str | None = Field(default="", max_length=1200)
    notes: str | None = Field(default="", max_length=1600)


class TransportContractPatch(BaseModel):
    client_name: str | None = Field(default=None, max_length=180)
    client_type: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=160)
    document_id: str | None = Field(default=None, max_length=80)
    contract_code: str | None = Field(default=None, max_length=120)
    initial_balance: float | None = Field(default=None, ge=0)
    consumed_balance: float | None = Field(default=None, ge=0)
    alert_balance: float | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=40)
    authorized_contacts: str | None = Field(default=None, max_length=1200)
    notes: str | None = Field(default=None, max_length=1600)
    last_updated_by: str | None = Field(default=None, max_length=180)


def _clean(value: Any, limit: int = 255) -> str:
    return str(value or "").strip()[:limit]


def _money(value: Any) -> float:
    try:
        raw = str(value or "0").strip()
        if not raw:
            return 0.0
        clean = "".join(ch for ch in raw if ch.isdigit() or ch in {".", ",", "-"})
        if "," in clean and "." in clean:
            if clean.rfind(",") > clean.rfind("."):
                clean = clean.replace(".", "").replace(",", ".")
            else:
                clean = clean.replace(",", "")
        elif clean.count(".") > 1:
            clean = clean.replace(".", "")
        elif clean.count(",") > 1:
            clean = clean.replace(",", "")
        elif "," in clean:
            clean = clean.replace(",", ".")
        return max(0.0, float(clean or 0))
    except Exception:
        return 0.0


def _status(value: Any) -> str:
    clean = _clean(value or "active", 40).lower().replace(" ", "_")
    return clean if clean in {"active", "paused", "expired", "archived"} else "active"


def _row(row: Any) -> dict[str, Any]:
    data = dict(row._mapping if hasattr(row, "_mapping") else row)
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        elif isinstance(value, uuid.UUID):
            data[key] = str(value)
        elif isinstance(value, Decimal):
            data[key] = float(value)
    return data


async def ensure_transport_contracts_storage(db: AsyncSession) -> None:
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS transport_contracts (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id uuid NOT NULL,
                client_name varchar(180) NOT NULL DEFAULT '',
                client_type varchar(40) NOT NULL DEFAULT 'company',
                phone varchar(80) NOT NULL DEFAULT '',
                email varchar(160) NOT NULL DEFAULT '',
                document_id varchar(80) NOT NULL DEFAULT '',
                contract_code varchar(120) NOT NULL DEFAULT '',
                initial_balance numeric(14,2) NOT NULL DEFAULT 0,
                consumed_balance numeric(14,2) NOT NULL DEFAULT 0,
                alert_balance numeric(14,2) NOT NULL DEFAULT 2000000,
                status varchar(40) NOT NULL DEFAULT 'active',
                authorized_contacts text NOT NULL DEFAULT '',
                notes text NOT NULL DEFAULT '',
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                archived_at timestamptz NULL
            )
            """
        )
    )
    for statement in [
        "ALTER TABLE transport_contracts ADD COLUMN IF NOT EXISTS authorized_contacts text NOT NULL DEFAULT ''",
        "ALTER TABLE transport_contracts ADD COLUMN IF NOT EXISTS archived_at timestamptz NULL",
        "ALTER TABLE transport_contracts ADD COLUMN IF NOT EXISTS last_updated_by VARCHAR(180) NOT NULL DEFAULT '';",
        "CREATE INDEX IF NOT EXISTS ix_transport_contracts_company_status ON transport_contracts (company_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_transport_contracts_company_code ON transport_contracts (company_id, contract_code)",
        "CREATE INDEX IF NOT EXISTS ix_transport_contracts_company_client ON transport_contracts (company_id, client_name)",
    ]:
        await db.execute(text(statement))


def _select_contracts_sql(where_extra: str = "") -> str:
    return f"""
        SELECT
            *,
            GREATEST(initial_balance - consumed_balance, 0) AS available_balance,
            CASE
                WHEN status = 'archived' THEN 'archived'
                WHEN GREATEST(initial_balance - consumed_balance, 0) <= alert_balance THEN 'low_balance'
                ELSE 'ok'
            END AS balance_alert
        FROM transport_contracts
        WHERE company_id = CAST(:company_id AS uuid)
        {where_extra}
    """


@router.get("/companies/{company_id}/contracts", dependencies=[Depends(require_transport_contracts_read)])
async def list_transport_contracts(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=80, ge=1, le=300),
    search: str = Query(default="", max_length=120),
    status_filter: str = Query(default="active", alias="status", max_length=40),
) -> dict[str, Any]:
    await ensure_transport_contracts_storage(db)
    query = f"%{_clean(search, 120).lower()}%"
    status_value = _clean(status_filter, 40).lower()
    where = """
      AND (:status_filter = 'all' OR status = :status_filter)
      AND (
        :query = '%%'
        OR LOWER(client_name) LIKE :query
        OR LOWER(phone) LIKE :query
        OR LOWER(email) LIKE :query
        OR LOWER(document_id) LIKE :query
        OR LOWER(contract_code) LIKE :query
      )
    """
    result = await db.execute(
        text(_select_contracts_sql(where) + " ORDER BY updated_at DESC, created_at DESC LIMIT :limit"),
        {
            "company_id": str(company_id),
            "query": query,
            "status_filter": status_value or "active",
            "limit": int(limit),
        },
    )
    rows = [_row(row) for row in result.fetchall()]
    return {"ok": True, "company_id": str(company_id), "contracts": rows, "count": len(rows)}


@router.get("/companies/{company_id}/summary", dependencies=[Depends(require_transport_contracts_read)])
async def transport_contracts_summary(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_contracts_storage(db)
    result = await db.execute(
        text(
            """
            WITH base AS (
                SELECT
                    *,
                    GREATEST(initial_balance - consumed_balance, 0) AS available_balance
                FROM transport_contracts
                WHERE company_id = CAST(:company_id AS uuid)
            )
            SELECT
                COUNT(*) AS contracts_total,
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE status = 'paused') AS paused_count,
                COUNT(*) FILTER (WHERE status = 'expired') AS expired_count,
                COUNT(*) FILTER (WHERE status = 'archived') AS archived_count,
                COUNT(*) FILTER (WHERE status <> 'archived' AND available_balance <= alert_balance) AS low_balance_count,
                COALESCE(SUM(initial_balance) FILTER (WHERE status <> 'archived'), 0) AS initial_total,
                COALESCE(SUM(consumed_balance) FILTER (WHERE status <> 'archived'), 0) AS consumed_total,
                COALESCE(SUM(available_balance) FILTER (WHERE status <> 'archived'), 0) AS available_total
            FROM base
            """
        ),
        {"company_id": str(company_id)},
    )
    return {"ok": True, "company_id": str(company_id), "summary": _row(result.first() or {})}


@router.post("/companies/{company_id}/contracts", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_transport_contracts_manage)])
async def create_transport_contract(
    company_id: uuid.UUID,
    payload: TransportContractIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_contracts_storage(db)
    if not _clean(payload.client_name, 180) and not _clean(payload.contract_code, 120):
        raise HTTPException(status_code=400, detail="client_or_contract_required")
    result = await db.execute(
        text(
            """
            INSERT INTO transport_contracts (
                company_id, client_name, client_type, phone, email, document_id, contract_code,
                initial_balance, consumed_balance, alert_balance, status, authorized_contacts, notes,
                created_at, updated_at
            )
            VALUES (
                CAST(:company_id AS uuid), :client_name, :client_type, :phone, :email, :document_id, :contract_code,
                :initial_balance, :consumed_balance, :alert_balance, :status, :authorized_contacts, :notes,
                now(), now()
            )
            RETURNING *
            """
        ),
        {
            "company_id": str(company_id),
            "client_name": _clean(payload.client_name, 180),
            "client_type": _clean(payload.client_type or "company", 40),
            "phone": _clean(payload.phone, 80),
            "email": _clean(payload.email, 160),
            "document_id": _clean(payload.document_id, 80),
            "contract_code": _clean(payload.contract_code, 120),
            "initial_balance": _money(payload.initial_balance),
            "consumed_balance": _money(payload.consumed_balance),
            "alert_balance": _money(payload.alert_balance),
            "status": _status(payload.status),
            "authorized_contacts": _clean(payload.authorized_contacts, 1200),
            "notes": _clean(payload.notes, 1600),
        },
    )
    await db.commit()
    created = _row(result.first())
    created["available_balance"] = max(0, _money(created.get("initial_balance")) - _money(created.get("consumed_balance")))
    created["balance_alert"] = "low_balance" if created["available_balance"] <= _money(created.get("alert_balance")) else "ok"
    return {"ok": True, "company_id": str(company_id), "contract": created}


@router.patch("/companies/{company_id}/contracts/{contract_id}", dependencies=[Depends(require_transport_contracts_manage)])
async def update_transport_contract(
    company_id: uuid.UUID,
    contract_id: uuid.UUID,
    payload: TransportContractPatch,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_contracts_storage(db)
    data = payload.model_dump(exclude_unset=True)
    allowed = {"alert_balance", "status", "notes", "last_updated_by"}
    updates: list[str] = []
    params: dict[str, Any] = {"company_id": str(company_id), "contract_id": str(contract_id)}
    for key, value in data.items():
        if key not in allowed:
            continue
        if key in {"initial_balance", "consumed_balance", "alert_balance"}:
            params[key] = _money(value)
        elif key == "status":
            params[key] = _status(value)
        elif key == "notes":
            params[key] = _clean(value, 1600)
        else:
            params[key] = _clean(value, 180)
        updates.append(f"{key} = :{key}")
    if not updates:
        raise HTTPException(status_code=400, detail="no_fields_to_update")
    updates.append("updated_at = now()")
    updates.append("archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, now()) ELSE NULL END" if "status" in data else "archived_at = archived_at")
    result = await db.execute(
        text(
            f"""
            UPDATE transport_contracts
            SET {', '.join(updates)}
            WHERE id = CAST(:contract_id AS uuid)
              AND company_id = CAST(:company_id AS uuid)
            RETURNING *
            """
        ),
        params,
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="contract_not_found")
    await db.commit()
    contract = _row(row)
    contract["available_balance"] = max(0, _money(contract.get("initial_balance")) - _money(contract.get("consumed_balance")))
    contract["balance_alert"] = "low_balance" if contract["available_balance"] <= _money(contract.get("alert_balance")) else "ok"
    return {"ok": True, "company_id": str(company_id), "contract": contract}


@router.post("/companies/{company_id}/contracts/{contract_id}/archive", dependencies=[Depends(require_transport_contracts_manage)])
async def archive_transport_contract(
    company_id: uuid.UUID,
    contract_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await update_transport_contract(
        company_id,
        contract_id,
        TransportContractPatch(status="archived"),
        db,
    )


def _csv_value(row: dict[str, str], *names: str) -> str:
    def key_for(value: Any) -> str:
        return (
            unicodedata.normalize("NFD", str(value or ""))
            .encode("ascii", "ignore")
            .decode("ascii")
            .strip()
            .lower()
            .replace(" ", "_")
        )

    normalized = {key_for(k): v for k, v in row.items()}
    for name in names:
        key = key_for(name)
        if key in normalized:
            return str(normalized[key] or "").strip()
    return ""


@router.post("/companies/{company_id}/contracts/import-csv", dependencies=[Depends(require_transport_contracts_manage)])
async def import_transport_contracts_csv(
    company_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_contracts_storage(db)
    raw = await file.read()
    text_value = raw.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text_value))
    created = 0
    skipped = 0
    for row in reader:
        payload = TransportContractIn(
            client_name=_csv_value(row, "client_name", "cliente", "nombre", "empresa"),
            client_type=_csv_value(row, "client_type", "tipo_cliente") or "company",
            phone=_csv_value(row, "phone", "telefono", "whatsapp"),
            email=_csv_value(row, "email", "correo"),
            document_id=_csv_value(row, "document_id", "nit", "cc", "documento"),
            contract_code=_csv_value(row, "contract_code", "contrato", "aval", "numero_contrato"),
            initial_balance=_money(_csv_value(row, "initial_balance", "saldo_inicial", "valor_contrato")),
            consumed_balance=_money(_csv_value(row, "consumed_balance", "saldo_consumido", "consumido")),
            alert_balance=_money(_csv_value(row, "alert_balance", "alerta_saldo", "saldo_alerta") or 2_000_000),
            status=_csv_value(row, "status", "estado") or "active",
            authorized_contacts=_csv_value(row, "authorized_contacts", "contactos_autorizados", "contactos"),
            notes=_csv_value(row, "notes", "notas", "observaciones"),
        )
        if not payload.client_name and not payload.contract_code:
            skipped += 1
            continue
        await create_transport_contract(company_id, payload, db)
        created += 1
    return {"ok": True, "company_id": str(company_id), "created": created, "skipped": skipped}
