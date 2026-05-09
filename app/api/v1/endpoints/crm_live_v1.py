from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


def clean(value: Any) -> str:
    return str(value or "").strip()


def intval(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name})
    return bool(result.scalar())


async def table_columns(db: AsyncSession, table_name: str) -> set[str]:
    result = await db.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
        """),
        {"table_name": table_name},
    )
    return {str(row[0]) for row in result.all()}


async def safe_rows(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        result = await db.execute(text(sql), params)
        return [dict(row) for row in result.mappings().all()]
    except Exception:
        await db.rollback()
        return []


async def active_modules(db: AsyncSession, company_id: str) -> set[str]:
    rows = await safe_rows(
        db,
        """
        SELECT lower(m.code) AS code
        FROM company_modules cm
        JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :company_id
          AND COALESCE(cm.enabled, true) IS TRUE
          AND COALESCE(m.is_active, true) IS TRUE
        """,
        {"company_id": company_id},
    )

    return {clean(row.get("code")).lower() for row in rows}


async def company_profile(db: AsyncSession, company_id: str) -> dict[str, Any]:
    if not await table_exists(db, "companies"):
        return {"id": company_id, "name": "Empresa", "slug": ""}

    cols = await table_columns(db, "companies")
    name_expr = "COALESCE(name, 'Empresa')" if "name" in cols else "'Empresa'"
    slug_expr = "COALESCE(slug, '')" if "slug" in cols else "''"

    rows = await safe_rows(
        db,
        f"""
        SELECT
            id::text AS id,
            {name_expr} AS name,
            {slug_expr} AS slug
        FROM companies
        WHERE id::text = :company_id
        LIMIT 1
        """,
        {"company_id": company_id},
    )

    return rows[0] if rows else {"id": company_id, "name": "Empresa", "slug": ""}


async def employees_snapshot(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    if not await table_exists(db, "employees"):
        return []

    employee_cols = await table_columns(db, "employees")

    name_expr = "COALESCE(e.full_name, '')"
    if "full_name" not in employee_cols and "name" in employee_cols:
        name_expr = "COALESCE(e.name, '')"
    elif "full_name" not in employee_cols:
        name_expr = "'Empleado'"

    role_expr = "COALESCE(e.role, '')" if "role" in employee_cols else "''"
    status_filter = ""
    if "status" in employee_cols:
        status_filter = "AND lower(COALESCE(e.status, 'active')) IN ('active', 'activo')"

    status_join = ""
    status_fields = """
        'sin_turno' AS work_status,
        NULL::text AS status_started_at,
        '' AS last_event_type
    """

    if await table_exists(db, "workforce_attendance_status"):
        status_cols = await table_columns(db, "workforce_attendance_status")
        if {"company_id", "employee_id", "status"}.issubset(status_cols):
            last_event_at_expr = "s.last_event_at::text" if "last_event_at" in status_cols else "NULL::text"
            last_event_type_expr = "COALESCE(s.last_event_type, '')" if "last_event_type" in status_cols else "''"
            status_join = """
                LEFT JOIN workforce_attendance_status s
                  ON s.company_id = e.company_id
                 AND s.employee_id = e.id
            """
            status_fields = f"""
                COALESCE(s.status, 'sin_turno') AS work_status,
                {last_event_at_expr} AS status_started_at,
                {last_event_type_expr} AS last_event_type
            """

    employees = await safe_rows(
        db,
        f"""
        SELECT
            e.id::text AS employee_id,
            {name_expr} AS employee_name,
            {role_expr} AS employee_role,
            {status_fields}
        FROM employees e
        {status_join}
        WHERE e.company_id::text = :company_id
        {status_filter}
        ORDER BY employee_name ASC
        """,
        {"company_id": company_id},
    )

    return employees


async def active_reference_sessions(db: AsyncSession, company_id: str) -> dict[str, dict[str, Any]]:
    if not await table_exists(db, "reference_work_sessions"):
        return {}

    rows = await safe_rows(
        db,
        """
        SELECT DISTINCT ON (employee_id)
            id,
            employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            started_at::text AS reference_started_at,
            EXTRACT(EPOCH FROM (now() - started_at))::int AS reference_elapsed_seconds,
            COALESCE(status, '') AS status
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND status = 'active'
        ORDER BY employee_id, started_at DESC
        """,
        {"company_id": company_id},
    )

    return {clean(row.get("employee_id")): row for row in rows}


def status_label(status: str) -> str:
    value = clean(status).lower()

    if value == "working":
        return "Activo"
    if value == "on_break":
        return "En pausa"
    if value in {"checked_out", "not_started", "sin_turno"}:
        return "Fuera de turno"

    return value or "Fuera de turno"


def normalize_status(status: str) -> str:
    value = clean(status).lower()

    if value in {"working", "on_break", "checked_out"}:
        return value

    return "sin_turno"


@router.get("/companies/{company_id}/snapshot")
async def crm_live_snapshot(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company = await company_profile(db, company_id)
    modules = await active_modules(db, company_id)
    employees = await employees_snapshot(db, company_id)
    sessions = await active_reference_sessions(db, company_id)

    rows: list[dict[str, Any]] = []

    for employee in employees:
        employee_id = clean(employee.get("employee_id"))
        work_status = normalize_status(employee.get("work_status"))
        session = sessions.get(employee_id)

        has_production = bool(session)

        rows.append({
            "employee_id": employee_id,
            "employee_name": clean(employee.get("employee_name")) or "Empleado",
            "employee_role": clean(employee.get("employee_role")),
            "work_status": work_status,
            "work_status_label": status_label(work_status),
            "status_started_at": employee.get("status_started_at"),
            "last_event_type": clean(employee.get("last_event_type")),
            "has_active_reference": has_production,
            "reference_session_id": session.get("id") if session else None,
            "reference_id": session.get("reference_id") if session else None,
            "reference_name": session.get("reference_name") if session else None,
            "reference_started_at": session.get("reference_started_at") if session else None,
            "reference_elapsed_seconds": intval(session.get("reference_elapsed_seconds")) if session else 0,
        })

    active_count = sum(1 for row in rows if row["work_status"] == "working")
    break_count = sum(1 for row in rows if row["work_status"] == "on_break")
    with_reference = sum(1 for row in rows if row["has_active_reference"])

    return {
        "ok": True,
        "language": "es",
        "company_id": company_id,
        "company": company,
        "server_time": datetime.utcnow().isoformat() + "Z",
        "active_modules": sorted(modules),
        "module": "crm",
        "crm_mode": "live_shared_module",
        "summary": {
            "employees_total": len(rows),
            "active_now": active_count,
            "on_break": break_count,
            "with_active_reference": with_reference,
            "production_enabled": "production" in modules,
            "references_enabled": "references" in modules,
            "payroll_enabled": "payroll" in modules,
        },
        "employees": rows,
    }
