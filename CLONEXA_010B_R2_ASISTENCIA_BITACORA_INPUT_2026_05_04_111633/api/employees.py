from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_db
from app.models.core import Company, Employee
from app.models.workforce_personnel_history import WorkforcePersonnelHistory
from app.models.workforce_attendance import WorkforceAttendanceEvent, WorkforceAttendanceStatus
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate
from app.schemas.workforce_personnel_history import WorkforcePersonnelHistoryOut

router = APIRouter()


def clean_empty(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def normalize_employee_payload(data: dict) -> dict:
    clean = {}
    for key, value in data.items():
        clean[key] = clean_empty(value)

    if clean.get("role") and not clean.get("employee_type"):
        clean["employee_type"] = clean["role"]

    if clean.get("employee_type") and not clean.get("role"):
        clean["role"] = clean["employee_type"]

    if not clean.get("role"):
        clean["role"] = "operator"

    if not clean.get("employee_type"):
        clean["employee_type"] = clean["role"]

    if not clean.get("status"):
        clean["status"] = "active"

    for money_field in ["hourly_rate_regular", "hourly_rate_extra", "deduction_1", "deduction_2"]:
        if clean.get(money_field) is None:
            clean[money_field] = 0

    return clean


PERSONAL_HISTORY_FIELDS = [
    "full_name",
    "document_id",
    "phone",
    "email",
    "status",
    "employee_type",
    "role",
    "telegram_user_id",
    "telegram_username",
    "hire_date",
    "hourly_rate_regular",
    "hourly_rate_extra",
    "deduction_1",
    "deduction_2",
    "notes",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def history_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def employee_snapshot(employee: Employee) -> dict:
    return {
        field: history_value(getattr(employee, field, None))
        for field in PERSONAL_HISTORY_FIELDS
    }


def changed_fields(before: dict, after: dict) -> list[dict]:
    changes = []
    for field in PERSONAL_HISTORY_FIELDS:
        old_value = before.get(field)
        new_value = after.get(field)
        if old_value != new_value:
            changes.append({
                "field": field,
                "old": old_value,
                "new": new_value,
            })
    return changes


def history_label(event_type: str) -> str:
    labels = {
        "employee_created": "Empleado creado",
        "employee_updated": "Empleado editado",
        "employee_activated": "Empleado activado",
        "employee_inactivated": "Empleado inactivado",
        "employee_archived": "Empleado archivado",
        "employee_restored": "Empleado restaurado",
    }
    return labels.get(event_type, event_type)


async def ensure_personnel_history_storage(db: AsyncSession) -> None:
    """
    Safety net 010A.1:
    Garantiza que la tabla exista aunque Alembic no haya corrido correctamente.
    Esto evita Internal Server Error en Historial y permite backfill operativo.
    """
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS workforce_personnel_history (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NULL REFERENCES employees(id) ON DELETE SET NULL,
            event_type varchar(80) NOT NULL,
            event_label varchar(180) NOT NULL,
            employee_name varchar(180) NULL,
            employee_role varchar(80) NULL,
            employee_status varchar(40) NULL,
            old_values_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            new_values_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            changed_fields_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            actor_user_id uuid NULL,
            source varchar(80) NOT NULL DEFAULT 'client',
            notes text NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_personnel_history_company_id ON workforce_personnel_history(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_personnel_history_employee_id ON workforce_personnel_history(employee_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_personnel_history_event_type ON workforce_personnel_history(event_type);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_personnel_history_created_at ON workforce_personnel_history(created_at);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_personnel_history_company_created ON workforce_personnel_history(company_id, created_at);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_personnel_history_company_employee ON workforce_personnel_history(company_id, employee_id);"))


async def backfill_personnel_history_for_company(db: AsyncSession, company_id: UUID) -> None:
    """
    Crea registros base para empleados existentes.
    Así Historial funciona también para empleados creados/archivados antes de instalar 010A.
    """
    await db.execute(
        text("""
            INSERT INTO workforce_personnel_history (
                company_id,
                employee_id,
                event_type,
                event_label,
                employee_name,
                employee_role,
                employee_status,
                old_values_json,
                new_values_json,
                changed_fields_json,
                source,
                notes,
                created_at
            )
            SELECT
                e.company_id,
                e.id,
                'employee_baseline',
                'Registro inicial',
                e.full_name,
                e.role,
                e.status,
                '{}'::jsonb,
                jsonb_build_object(
                    'full_name', e.full_name,
                    'document_id', e.document_id,
                    'phone', e.phone,
                    'email', e.email,
                    'status', e.status,
                    'employee_type', e.employee_type,
                    'role', e.role,
                    'telegram_user_id', e.telegram_user_id,
                    'telegram_username', e.telegram_username,
                    'hire_date', e.hire_date,
                    'hourly_rate_regular', e.hourly_rate_regular::text,
                    'hourly_rate_extra', e.hourly_rate_extra::text,
                    'deduction_1', e.deduction_1::text,
                    'deduction_2', e.deduction_2::text,
                    'notes', e.notes
                ),
                jsonb_build_array(
                    jsonb_build_object('field', 'registro', 'old', '', 'new', 'Registro inicial / estado actual')
                ),
                'history_backfill_010a1',
                'Registro base generado automáticamente para que Historial sea consultable.',
                COALESCE(e.updated_at, e.created_at, now())
            FROM employees e
            WHERE e.company_id = :company_id
              AND NOT EXISTS (
                  SELECT 1
                  FROM workforce_personnel_history h
                  WHERE h.company_id = e.company_id
                    AND h.employee_id = e.id
                    AND h.event_type = 'employee_baseline'
              );
        """),
        {"company_id": str(company_id)},
    )


def fallback_history_from_employee(employee: Employee) -> dict:
    snap = employee_snapshot(employee)
    return {
        "id": uuid4(),
        "company_id": employee.company_id,
        "employee_id": employee.id,
        "event_type": "employee_baseline",
        "event_label": "Registro actual",
        "employee_name": getattr(employee, "full_name", None),
        "employee_role": getattr(employee, "role", None),
        "employee_status": getattr(employee, "status", None),
        "old_values_json": {},
        "new_values_json": snap,
        "changed_fields_json": [{"field": "registro", "old": "", "new": "Registro reconstruido desde personal"}],
        "actor_user_id": None,
        "source": "employees_fallback",
        "notes": "Historial reconstruido desde la tabla de personal si la auditoría aún no estaba disponible.",
        "created_at": getattr(employee, "updated_at", None) or getattr(employee, "created_at", None) or utcnow(),
    }


async def fallback_personnel_history(
    db: AsyncSession,
    company_id: UUID,
    search: str | None = None,
    limit: int = 300,
    offset: int = 0,
) -> list[dict]:
    stmt = select(Employee).where(Employee.company_id == company_id).order_by(Employee.full_name.asc())

    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Employee.full_name.ilike(like),
                Employee.role.ilike(like),
                Employee.status.ilike(like),
                Employee.phone.ilike(like),
                Employee.email.ilike(like),
                Employee.telegram_user_id.ilike(like),
            )
        )

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return [fallback_history_from_employee(employee) for employee in result.scalars().all()]


async def add_personnel_history(
    db: AsyncSession,
    employee: Employee,
    event_type: str,
    old_values: dict | None = None,
    new_values: dict | None = None,
    changes: list[dict] | None = None,
    source: str = "client",
    notes: str | None = None,
) -> WorkforcePersonnelHistory | None:
    new_values = new_values or employee_snapshot(employee)
    old_values = old_values or {}

    try:
        await ensure_personnel_history_storage(db)
        history = WorkforcePersonnelHistory(
            company_id=employee.company_id,
            employee_id=employee.id,
            event_type=event_type,
            event_label=history_label(event_type),
            employee_name=new_values.get("full_name") or getattr(employee, "full_name", None),
            employee_role=new_values.get("role") or getattr(employee, "role", None),
            employee_status=new_values.get("status") or getattr(employee, "status", None),
            old_values_json=old_values,
            new_values_json=new_values,
            changed_fields_json=changes or changed_fields(old_values, new_values),
            source=source,
            notes=notes,
        )
        db.add(history)
        return history
    except SQLAlchemyError:
        # No bloquea guardar empleados si la tabla de historial presenta un problema puntual.
        await db.rollback()
        return None



async def get_employee_or_404(db: AsyncSession, employee_id: UUID) -> Employee:
    employee = await db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="employee_not_found")
    return employee


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(payload: EmployeeCreate, db: AsyncSession = Depends(get_db)) -> Employee:
    company = await db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company_not_found")

    data = normalize_employee_payload(payload.model_dump())
    employee = Employee(**data)

    db.add(employee)
    await db.flush()
    new_values = employee_snapshot(employee)
    await add_personnel_history(
        db,
        employee,
        event_type="employee_created",
        old_values={},
        new_values=new_values,
        changes=changed_fields({}, new_values),
        notes="Creado desde Workforce / Personal.",
    )
    await db.commit()
    await db.refresh(employee)
    return employee


@router.get("", response_model=list[EmployeeOut])
async def list_employees(
    company_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    include_archived: bool = False,
) -> list[Employee]:
    stmt = (
        select(Employee)
        .where(Employee.company_id == company_id)
        .order_by(Employee.full_name.asc())
    )

    if not include_archived:
        stmt = stmt.where(Employee.status != "archived")

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/history", response_model=list[WorkforcePersonnelHistoryOut])
async def list_personnel_history(
    company_id: UUID = Query(...),
    employee_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[WorkforcePersonnelHistory] | list[dict]:
    try:
        await ensure_personnel_history_storage(db)
        await backfill_personnel_history_for_company(db, company_id)
        await db.flush()

        stmt = select(WorkforcePersonnelHistory).where(WorkforcePersonnelHistory.company_id == company_id)

        if employee_id:
            stmt = stmt.where(WorkforcePersonnelHistory.employee_id == employee_id)

        if event_type:
            stmt = stmt.where(WorkforcePersonnelHistory.event_type == event_type)

        if date_from:
            stmt = stmt.where(WorkforcePersonnelHistory.created_at >= date_from)

        if date_to:
            stmt = stmt.where(WorkforcePersonnelHistory.created_at <= date_to)

        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    WorkforcePersonnelHistory.employee_name.ilike(like),
                    WorkforcePersonnelHistory.employee_role.ilike(like),
                    WorkforcePersonnelHistory.employee_status.ilike(like),
                    WorkforcePersonnelHistory.event_type.ilike(like),
                    WorkforcePersonnelHistory.event_label.ilike(like),
                    WorkforcePersonnelHistory.notes.ilike(like),
                )
            )

        stmt = stmt.order_by(desc(WorkforcePersonnelHistory.created_at)).offset(offset).limit(limit)
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        await db.commit()
        return rows

    except Exception:
        await db.rollback()
        return await fallback_personnel_history(
            db=db,
            company_id=company_id,
            search=search,
            limit=limit,
            offset=offset,
        )


@router.get("/history/{employee_id}", response_model=list[WorkforcePersonnelHistoryOut])
async def get_personnel_history_for_employee(
    employee_id: UUID,
    company_id: UUID = Query(...),
    limit: int = Query(default=300, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[WorkforcePersonnelHistory] | list[dict]:
    try:
        await ensure_personnel_history_storage(db)
        await backfill_personnel_history_for_company(db, company_id)
        await db.flush()

        stmt = (
            select(WorkforcePersonnelHistory)
            .where(
                WorkforcePersonnelHistory.company_id == company_id,
                WorkforcePersonnelHistory.employee_id == employee_id,
            )
            .order_by(desc(WorkforcePersonnelHistory.created_at))
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        await db.commit()
        return rows

    except Exception:
        await db.rollback()
        employee = await get_employee_or_404(db, employee_id)
        if employee.company_id != company_id:
            raise HTTPException(status_code=404, detail="employee_not_found_for_company")
        return [fallback_history_from_employee(employee)]




# =============================================================================
# 010B — Workforce Asistencia / Jornada MVP
# =============================================================================

ATTENDANCE_EVENT_LABELS = {
    "check_in": "Entrada",
    "break_start": "Pausa",
    "break_end": "Reanudar",
    "check_out": "Salida",
    "manual_adjustment": "Ajuste manual",
}

ATTENDANCE_STATUS_LABELS = {
    "not_started": "Sin iniciar",
    "working": "Trabajando",
    "on_break": "En pausa",
    "checked_out": "Finalizado",
}


async def ensure_attendance_storage(db: AsyncSession) -> None:
    """
    Safety net 010B:
    Crea tablas de asistencia si Alembic no corrió aún.
    Evita que el botón Asistencia falle por migración pendiente.
    """
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS workforce_attendance_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            event_type varchar(80) NOT NULL,
            event_label varchar(180) NOT NULL,
            employee_name varchar(180) NULL,
            employee_role varchar(80) NULL,
            status_after varchar(40) NOT NULL,
            source varchar(80) NOT NULL DEFAULT 'client',
            notes text NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS workforce_attendance_status (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            status varchar(40) NOT NULL DEFAULT 'not_started',
            last_event_type varchar(80) NULL,
            last_event_at timestamptz NULL,
            check_in_at timestamptz NULL,
            break_started_at timestamptz NULL,
            check_out_at timestamptz NULL,
            worked_minutes integer NOT NULL DEFAULT 0,
            break_minutes integer NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(company_id, employee_id)
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_attendance_events_company_id ON workforce_attendance_events(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_attendance_events_employee_id ON workforce_attendance_events(employee_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_attendance_events_created_at ON workforce_attendance_events(created_at);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_attendance_events_company_created ON workforce_attendance_events(company_id, created_at);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_attendance_status_company_id ON workforce_attendance_status(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_workforce_attendance_status_employee_id ON workforce_attendance_status(employee_id);"))


def minutes_between(start: datetime | None, end: datetime | None) -> int:
    if not start or not end:
        return 0
    try:
        delta = end - start
        return max(0, int(delta.total_seconds() // 60))
    except Exception:
        return 0


async def get_employee_for_company_or_404(db: AsyncSession, employee_id: UUID, company_id: UUID) -> Employee:
    employee = await get_employee_or_404(db, employee_id)
    if employee.company_id != company_id:
        raise HTTPException(status_code=404, detail="employee_not_found_for_company")
    if getattr(employee, "status", None) == "archived":
        raise HTTPException(status_code=400, detail="employee_archived")
    return employee


async def get_attendance_status(db: AsyncSession, company_id: UUID, employee_id: UUID) -> dict | None:
    result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                employee_id,
                status,
                last_event_type,
                last_event_at,
                check_in_at,
                break_started_at,
                check_out_at,
                worked_minutes,
                break_minutes,
                updated_at
            FROM workforce_attendance_status
            WHERE company_id = :company_id
              AND employee_id = :employee_id
            LIMIT 1
        """),
        {"company_id": str(company_id), "employee_id": str(employee_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def upsert_attendance_status(
    db: AsyncSession,
    employee: Employee,
    status: str,
    event_type: str,
    now: datetime,
    check_in_at: datetime | None = None,
    break_started_at: datetime | None = None,
    check_out_at: datetime | None = None,
    worked_minutes: int | None = None,
    break_minutes: int | None = None,
) -> None:
    await db.execute(
        text("""
            INSERT INTO workforce_attendance_status (
                company_id,
                employee_id,
                status,
                last_event_type,
                last_event_at,
                check_in_at,
                break_started_at,
                check_out_at,
                worked_minutes,
                break_minutes,
                updated_at
            )
            VALUES (
                :company_id,
                :employee_id,
                :status,
                :event_type,
                :now,
                :check_in_at,
                :break_started_at,
                :check_out_at,
                :worked_minutes,
                :break_minutes,
                :now
            )
            ON CONFLICT (company_id, employee_id)
            DO UPDATE SET
                status = EXCLUDED.status,
                last_event_type = EXCLUDED.last_event_type,
                last_event_at = EXCLUDED.last_event_at,
                check_in_at = EXCLUDED.check_in_at,
                break_started_at = EXCLUDED.break_started_at,
                check_out_at = EXCLUDED.check_out_at,
                worked_minutes = EXCLUDED.worked_minutes,
                break_minutes = EXCLUDED.break_minutes,
                updated_at = EXCLUDED.updated_at
        """),
        {
            "company_id": str(employee.company_id),
            "employee_id": str(employee.id),
            "status": status,
            "event_type": event_type,
            "now": now,
            "check_in_at": check_in_at,
            "break_started_at": break_started_at,
            "check_out_at": check_out_at,
            "worked_minutes": worked_minutes or 0,
            "break_minutes": break_minutes or 0,
        },
    )


async def add_attendance_event(
    db: AsyncSession,
    employee: Employee,
    event_type: str,
    status_after: str,
    source: str = "client",
    notes: str | None = None,
    now: datetime | None = None,
) -> None:
    now = now or utcnow()
    await db.execute(
        text("""
            INSERT INTO workforce_attendance_events (
                company_id,
                employee_id,
                event_type,
                event_label,
                employee_name,
                employee_role,
                status_after,
                source,
                notes,
                created_at
            )
            VALUES (
                :company_id,
                :employee_id,
                :event_type,
                :event_label,
                :employee_name,
                :employee_role,
                :status_after,
                :source,
                :notes,
                :created_at
            )
        """),
        {
            "company_id": str(employee.company_id),
            "employee_id": str(employee.id),
            "event_type": event_type,
            "event_label": ATTENDANCE_EVENT_LABELS.get(event_type, event_type),
            "employee_name": getattr(employee, "full_name", None),
            "employee_role": getattr(employee, "role", None),
            "status_after": status_after,
            "source": source or "client",
            "notes": notes,
            "created_at": now,
        },
    )


async def apply_attendance_action(
    db: AsyncSession,
    employee: Employee,
    action: str,
    source: str = "client",
    notes: str | None = None,
) -> dict:
    await ensure_attendance_storage(db)
    now = utcnow()
    current = await get_attendance_status(db, employee.company_id, employee.id)

    current_status = (current or {}).get("status") or "not_started"
    check_in_at = (current or {}).get("check_in_at")
    break_started_at = (current or {}).get("break_started_at")
    break_minutes = int((current or {}).get("break_minutes") or 0)

    if action == "check_in":
        if current_status in ("working", "on_break"):
            raise HTTPException(status_code=400, detail="attendance_already_open")

        await upsert_attendance_status(db, employee, "working", "check_in", now, now, None, None, 0, 0)
        await add_attendance_event(db, employee, "check_in", "working", source, notes, now)

    elif action == "break_start":
        if current_status != "working":
            raise HTTPException(status_code=400, detail="attendance_break_requires_working")

        await upsert_attendance_status(
            db,
            employee,
            "on_break",
            "break_start",
            now,
            check_in_at,
            now,
            None,
            max(0, minutes_between(check_in_at, now) - break_minutes),
            break_minutes,
        )
        await add_attendance_event(db, employee, "break_start", "on_break", source, notes, now)

    elif action == "break_end":
        if current_status != "on_break":
            raise HTTPException(status_code=400, detail="attendance_resume_requires_break")

        added_break = minutes_between(break_started_at, now)
        new_break_minutes = break_minutes + added_break
        await upsert_attendance_status(
            db,
            employee,
            "working",
            "break_end",
            now,
            check_in_at,
            None,
            None,
            max(0, minutes_between(check_in_at, now) - new_break_minutes),
            new_break_minutes,
        )
        await add_attendance_event(db, employee, "break_end", "working", source, notes, now)

    elif action == "check_out":
        if current_status not in ("working", "on_break"):
            raise HTTPException(status_code=400, detail="attendance_checkout_requires_open_shift")

        extra_break = minutes_between(break_started_at, now) if current_status == "on_break" else 0
        new_break_minutes = break_minutes + extra_break
        await upsert_attendance_status(
            db,
            employee,
            "checked_out",
            "check_out",
            now,
            check_in_at,
            None,
            now,
            max(0, minutes_between(check_in_at, now) - new_break_minutes),
            new_break_minutes,
        )
        await add_attendance_event(db, employee, "check_out", "checked_out", source, notes, now)

    else:
        raise HTTPException(status_code=400, detail="attendance_invalid_action")

    await db.commit()
    refreshed = await get_attendance_status(db, employee.company_id, employee.id)
    return {
        "employee_id": str(employee.id),
        "employee_name": employee.full_name,
        "status": (refreshed or {}).get("status"),
        "last_event_type": (refreshed or {}).get("last_event_type"),
        "last_event_at": (refreshed or {}).get("last_event_at"),
        "check_in_at": (refreshed or {}).get("check_in_at"),
        "check_out_at": (refreshed or {}).get("check_out_at"),
        "worked_minutes": (refreshed or {}).get("worked_minutes") or 0,
        "break_minutes": (refreshed or {}).get("break_minutes") or 0,
    }


@router.get("/attendance/today")
async def attendance_today(
    company_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await ensure_attendance_storage(db)

    result = await db.execute(
        text("""
            SELECT
                e.id AS employee_id,
                e.company_id,
                e.full_name AS employee_name,
                e.role AS employee_role,
                e.status AS employee_status,
                COALESCE(s.status, 'not_started') AS status,
                s.last_event_type,
                s.last_event_at,
                s.check_in_at,
                s.break_started_at,
                s.check_out_at,
                COALESCE(s.worked_minutes, 0) AS worked_minutes,
                COALESCE(s.break_minutes, 0) AS break_minutes
            FROM employees e
            LEFT JOIN workforce_attendance_status s
              ON s.company_id = e.company_id
             AND s.employee_id = e.id
            WHERE e.company_id = :company_id
              AND COALESCE(e.status, 'active') != 'archived'
            ORDER BY e.full_name ASC
        """),
        {"company_id": str(company_id)},
    )
    rows = [dict(row) for row in result.mappings().all()]
    await db.commit()
    return rows


@router.get("/attendance/history")
async def attendance_history(
    company_id: UUID = Query(...),
    employee_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await ensure_attendance_storage(db)

    stmt = """
        SELECT
            ev.id,
            ev.company_id,
            ev.employee_id,
            ev.event_type,
            ev.event_label,
            ev.employee_name,
            ev.employee_role,
            ev.status_after,
            ev.source,
            ev.notes,
            ev.created_at
        FROM workforce_attendance_events ev
        WHERE ev.company_id = :company_id
    """
    params = {"company_id": str(company_id), "limit": limit, "offset": offset}

    if employee_id:
        stmt += " AND ev.employee_id = :employee_id"
        params["employee_id"] = str(employee_id)

    if event_type:
        stmt += " AND ev.event_type = :event_type"
        params["event_type"] = event_type

    if date_from:
        stmt += " AND ev.created_at >= :date_from"
        params["date_from"] = date_from

    if date_to:
        stmt += " AND ev.created_at <= :date_to"
        params["date_to"] = date_to

    if search:
        stmt += """
            AND (
                ev.employee_name ILIKE :search
                OR ev.employee_role ILIKE :search
                OR ev.event_label ILIKE :search
                OR ev.status_after ILIKE :search
                OR ev.notes ILIKE :search
            )
        """
        params["search"] = f"%{search.strip()}%"

    stmt += " ORDER BY ev.created_at DESC OFFSET :offset LIMIT :limit"

    result = await db.execute(text(stmt), params)
    rows = [dict(row) for row in result.mappings().all()]
    await db.commit()
    return rows


@router.post("/attendance/{employee_id}/check-in")
async def attendance_check_in(
    employee_id: UUID,
    company_id: UUID = Query(...),
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    employee = await get_employee_for_company_or_404(db, employee_id, company_id)
    return await apply_attendance_action(db, employee, "check_in", (payload or {}).get("source", "client"), (payload or {}).get("notes"))


@router.post("/attendance/{employee_id}/break-start")
async def attendance_break_start(
    employee_id: UUID,
    company_id: UUID = Query(...),
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    employee = await get_employee_for_company_or_404(db, employee_id, company_id)
    return await apply_attendance_action(db, employee, "break_start", (payload or {}).get("source", "client"), (payload or {}).get("notes"))


@router.post("/attendance/{employee_id}/break-end")
async def attendance_break_end(
    employee_id: UUID,
    company_id: UUID = Query(...),
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    employee = await get_employee_for_company_or_404(db, employee_id, company_id)
    return await apply_attendance_action(db, employee, "break_end", (payload or {}).get("source", "client"), (payload or {}).get("notes"))


@router.post("/attendance/{employee_id}/check-out")
async def attendance_check_out(
    employee_id: UUID,
    company_id: UUID = Query(...),
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    employee = await get_employee_for_company_or_404(db, employee_id, company_id)
    return await apply_attendance_action(db, employee, "check_out", (payload or {}).get("source", "client"), (payload or {}).get("notes"))


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: UUID, db: AsyncSession = Depends(get_db)) -> Employee:
    return await get_employee_or_404(db, employee_id)


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
) -> Employee:
    employee = await get_employee_or_404(db, employee_id)
    before = employee_snapshot(employee)
    data = normalize_employee_payload(payload.model_dump(exclude_unset=True))

    for key, value in data.items():
        if hasattr(employee, key):
            setattr(employee, key, value)

    after = employee_snapshot(employee)
    changes = changed_fields(before, after)
    if changes:
        await add_personnel_history(
            db,
            employee,
            event_type="employee_updated",
            old_values=before,
            new_values=after,
            changes=changes,
            notes="Editado desde Workforce / Personal.",
        )

    await db.commit()
    await db.refresh(employee)
    return employee


@router.post("/{employee_id}/activate", response_model=EmployeeOut)
async def activate_employee(employee_id: UUID, db: AsyncSession = Depends(get_db)) -> Employee:
    employee = await get_employee_or_404(db, employee_id)
    before = employee_snapshot(employee)
    previous_status = employee.status
    employee.status = "active"
    after = employee_snapshot(employee)
    event_type = "employee_restored" if previous_status == "archived" else "employee_activated"
    await add_personnel_history(
        db,
        employee,
        event_type=event_type,
        old_values=before,
        new_values=after,
        changes=changed_fields(before, after),
        notes="Activado desde Workforce / Personal.",
    )
    await db.commit()
    await db.refresh(employee)
    return employee


@router.post("/{employee_id}/deactivate", response_model=EmployeeOut)
async def deactivate_employee(employee_id: UUID, db: AsyncSession = Depends(get_db)) -> Employee:
    employee = await get_employee_or_404(db, employee_id)
    before = employee_snapshot(employee)
    employee.status = "inactive"
    after = employee_snapshot(employee)
    await add_personnel_history(
        db,
        employee,
        event_type="employee_inactivated",
        old_values=before,
        new_values=after,
        changes=changed_fields(before, after),
        notes="Inactivado desde Workforce / Personal.",
    )
    await db.commit()
    await db.refresh(employee)
    return employee


@router.post("/{employee_id}/archive", response_model=EmployeeOut)
async def archive_employee(employee_id: UUID, db: AsyncSession = Depends(get_db)) -> Employee:
    employee = await get_employee_or_404(db, employee_id)
    before = employee_snapshot(employee)
    employee.status = "archived"
    after = employee_snapshot(employee)
    await add_personnel_history(
        db,
        employee,
        event_type="employee_archived",
        old_values=before,
        new_values=after,
        changes=changed_fields(before, after),
        notes="Archivado desde Workforce / Personal.",
    )
    await db.commit()
    await db.refresh(employee)
    return employee
