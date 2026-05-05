from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

VALID_MATERIAL_STATUSES = {"pending", "approved", "rejected", "delivered", "returned"}


class MaterialStatusPayload(BaseModel):
    status: str
    notes: str | None = None


async def ensure_materials_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS material_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NULL REFERENCES employees(id) ON DELETE SET NULL,
            employee_name varchar(180) NULL,
            employee_role varchar(100) NULL,
            material_name text NOT NULL DEFAULT '',
            quantity numeric(14, 2) NOT NULL DEFAULT 1,
            unit varchar(40) NULL,
            notes text NULL,
            status varchar(40) NOT NULL DEFAULT 'pending',
            source_channel varchar(80) NOT NULL DEFAULT 'client',
            source_ref varchar(220) NULL,
            attendance_event_id uuid NULL,
            requested_at timestamptz NOT NULL DEFAULT now(),
            status_updated_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_company ON material_requests(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_status ON material_requests(company_id, status);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_requests_employee ON material_requests(company_id, employee_id);"))
    await db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_material_requests_source_ref ON material_requests(company_id, source_ref) WHERE source_ref IS NOT NULL;"))
    await db.commit()


def _money_number(value: Any) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except Exception:
        return 0.0


def material_request_out(row: dict[str, Any]) -> dict[str, Any]:
    def iso(key: str) -> str | None:
        value = row.get(key)
        return value.isoformat() if hasattr(value, "isoformat") else None

    return {
        "id": str(row.get("id")),
        "company_id": str(row.get("company_id")),
        "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None,
        "employee_name": row.get("employee_name") or "",
        "employee_role": row.get("employee_role") or "",
        "material_name": row.get("material_name") or "",
        "quantity": _money_number(row.get("quantity")),
        "unit": row.get("unit") or "",
        "notes": row.get("notes") or "",
        "status": row.get("status") or "pending",
        "source_channel": row.get("source_channel") or "",
        "source_ref": row.get("source_ref") or "",
        "attendance_event_id": str(row.get("attendance_event_id")) if row.get("attendance_event_id") else None,
        "requested_at": iso("requested_at"),
        "status_updated_at": iso("status_updated_at"),
        "created_at": iso("created_at"),
        "updated_at": iso("updated_at"),
    }


def summary_from_requests(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(rows),
        "pending": 0,
        "approved": 0,
        "delivered": 0,
        "returned": 0,
        "rejected": 0,
        "approved_or_delivered": 0,
    }
    for row in rows:
        status = str(row.get("status") or "pending").lower()
        if status in summary:
            summary[status] += 1
        if status in {"approved", "delivered"}:
            summary["approved_or_delivered"] += 1
    return summary


@router.get("/companies/{company_id}/requests")
async def list_material_requests(
    company_id: UUID,
    status: str | None = None,
    limit: int = 300,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)
    limit = max(1, min(int(limit or 300), 1000))

    where_status = ""
    params: dict[str, Any] = {"company_id": str(company_id), "limit": limit}
    if status and status != "all":
        where_status = " AND status = :status"
        params["status"] = status

    result = await db.execute(
        text(f"""
            SELECT *
            FROM material_requests
            WHERE company_id = :company_id
            {where_status}
            ORDER BY
              CASE status
                WHEN 'pending' THEN 1
                WHEN 'approved' THEN 2
                WHEN 'delivered' THEN 3
                WHEN 'returned' THEN 4
                WHEN 'rejected' THEN 5
                ELSE 6
              END,
              requested_at DESC,
              created_at DESC
            LIMIT :limit
        """),
        params,
    )

    rows = [material_request_out(dict(row)) for row in result.mappings().all()]
    return {
        "company_id": str(company_id),
        "summary": summary_from_requests(rows),
        "requests": rows,
    }


@router.patch("/requests/{request_id}/status")
async def update_material_request_status(
    request_id: UUID,
    payload: MaterialStatusPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_materials_storage(db)

    status = str(payload.status or "").strip().lower()
    if status not in VALID_MATERIAL_STATUSES:
        raise HTTPException(status_code=422, detail="Estado de material inválido.")

    result = await db.execute(
        text("""
            UPDATE material_requests
            SET status = :status,
                notes = COALESCE(NULLIF(:notes, ''), notes),
                status_updated_at = now(),
                updated_at = now()
            WHERE id = :request_id
            RETURNING *
        """),
        {
            "request_id": str(request_id),
            "status": status,
            "notes": (payload.notes or "").strip(),
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Solicitud de material no encontrada.")

    await db.commit()
    return material_request_out(dict(row))
