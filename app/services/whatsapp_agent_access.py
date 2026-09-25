"""Who may talk to a company's internal WhatsApp agent (nomina, CRM,
produccion).

SECURITY (2026-09-24): the agent used to answer any number that wrote to the
linked WhatsApp. Now the internal line only answers:
  - the linked number's own chat (the owner writing to themselves), and
  - phones of active Workforce employees an admin explicitly granted
    "puede consultar por WhatsApp" (off by default).
Anyone else gets silence.

The grant stores the phone the employee had when it was given. /employees
is still open (being closed in the endpoint auth sweep), so a grant must
never follow a phone that someone edits later: if the employee's current
phone no longer matches, the grant stops working until an admin renews it.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def normalize_phone(value: Any) -> str:
    """Same rules as bridge.mjs normalizePhone (Colombian mobiles get 57)."""
    phone = re.sub(r"\D", "", str(value or ""))
    if phone.startswith("00"):
        phone = phone[2:]
    if len(phone) == 10 and phone.startswith("3"):
        phone = f"57{phone}"
    return phone


async def is_agent_phone_authorized(db: AsyncSession, company_id: uuid.UUID, phone: Any) -> bool:
    wanted = normalize_phone(phone)
    if len(wanted) < 7:
        return False
    result = await db.execute(
        text(
            """
            SELECT e.phone
            FROM whatsapp_agent_access a
            JOIN employees e ON e.id = a.employee_id AND e.company_id = a.company_id
            WHERE a.company_id = :company_id
              AND a.phone = :phone
              AND e.status = 'active'
            """
        ),
        {"company_id": str(company_id), "phone": wanted},
    )
    return any(normalize_phone(row["phone"]) == wanted for row in result.mappings().all())


async def list_agent_access(db: AsyncSession, company_id: uuid.UUID) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT e.id, e.full_name, e.phone, e.role,
                   a.phone AS granted_phone, a.granted_by, a.granted_at
            FROM employees e
            LEFT JOIN whatsapp_agent_access a ON a.employee_id = e.id AND a.company_id = e.company_id
            WHERE e.company_id = :company_id
              AND e.status = 'active'
            ORDER BY e.full_name
            """
        ),
        {"company_id": str(company_id)},
    )
    rows = []
    for row in result.mappings().all():
        phone = normalize_phone(row["phone"])
        granted_phone = row["granted_phone"] or ""
        rows.append({
            "employee_id": str(row["id"]),
            "name": row["full_name"] or "Empleado",
            "role": row["role"] or "",
            "phone": phone,
            "enabled": bool(granted_phone) and granted_phone == phone,
            # The phone changed after the grant: it no longer works.
            "stale": bool(granted_phone) and granted_phone != phone,
            "granted_by": row["granted_by"] or "",
            "granted_at": row["granted_at"].isoformat() if row["granted_at"] else "",
        })
    return rows


async def set_agent_access(
    db: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    *,
    enabled: bool,
    granted_by: str,
) -> None:
    result = await db.execute(
        text("SELECT phone, status FROM employees WHERE id = :employee_id AND company_id = :company_id"),
        {"employee_id": str(employee_id), "company_id": str(company_id)},
    )
    employee = result.mappings().first()
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="employee_not_found")
    if not enabled:
        await db.execute(
            text("DELETE FROM whatsapp_agent_access WHERE company_id = :company_id AND employee_id = :employee_id"),
            {"company_id": str(company_id), "employee_id": str(employee_id)},
        )
        await db.commit()
        return
    phone = normalize_phone(employee["phone"])
    if len(phone) < 7:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El empleado no tiene un telefono valido en Workforce.",
        )
    if employee["status"] != "active":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El empleado no esta activo.")
    await db.execute(
        text(
            """
            INSERT INTO whatsapp_agent_access (company_id, employee_id, phone, granted_by, granted_at)
            VALUES (:company_id, :employee_id, :phone, :granted_by, NOW())
            ON CONFLICT (company_id, employee_id)
            DO UPDATE SET phone = EXCLUDED.phone, granted_by = EXCLUDED.granted_by, granted_at = NOW()
            """
        ),
        {
            "company_id": str(company_id),
            "employee_id": str(employee_id),
            "phone": phone,
            "granted_by": str(granted_by or "")[:160],
        },
    )
    await db.commit()
