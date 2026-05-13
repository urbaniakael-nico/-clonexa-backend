from __future__ import annotations

from uuid import UUID, uuid4
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.auth import CompanyUser
from app.models.core import Company, Employee
from app.schemas.auth import (
    AdminCreateCompanyUserRequest,
    AdminResetPasswordRequest,
    AdminResetPasswordResponse,
    AdminUpdateCompanyUserRequest,
    CompanyUserOut,
    UnlockUserResponse,
)
from app.services.auth_service import (
    company_user_out_payload,
    create_access_token,
    create_company_user,
    get_access_token_expire_minutes,
    get_current_company_user,
    list_company_users,
    reset_company_user_password,
    unlock_company_user,
    update_company_user,
    generate_temporary_password,
    hash_password,
    verify_password,
)

router = APIRouter()

# CLONEXA_019C_SALES_MINIPANEL_USERS_BACKEND_START

class SalesMiniPanelUserCreateRequest(BaseModel):
    employee_id: UUID
    link: Optional[str] = None


# CLONEXA_019D_MINIPANEL_LOGIN_BACKEND_START

class MiniPanelLoginRequest(BaseModel):
    username: str
    password: str
    panel_type: str


def _cx_bearer_token_019d(authorization: Optional[str]) -> str:
    raw = str(authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido.")
    token = raw.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")
    return token


def _cx_panel_type_019d(value: Any) -> str:
    panel_type = str(value or "").strip().lower()
    aliases = {
        "ventas": "sales",
        "sales": "sales",
        "tiendas": "store",
        "store": "store",
        "stores": "store",
        "inventario": "inventory",
        "inventarios": "inventory",
        "inventory": "inventory",
        "logistica": "logistics",
        "logística": "logistics",
        "logistics": "logistics",
        "otro": "other",
        "otros": "other",
        "other": "other",
    }
    clean = aliases.get(panel_type, panel_type)
    if clean not in MINI_PANEL_ALLOWED_TYPES_019C:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de mini panel inválido.")
    return clean


def _cx_minipanel_type_label_019d(panel_type: str) -> str:
    return {
        "sales": "Ventas",
        "store": "Tiendas",
        "inventory": "Inventarios",
        "logistics": "Logística",
        "other": "Otros",
    }.get(panel_type, panel_type)


async def _cx_company_or_404_019d(db: AsyncSession, company_id: UUID) -> Company:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada.")
    if str(getattr(company, "status", "") or "").lower() not in {"active", "activo"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Empresa inactiva.")
    return company


def _cx_minipanel_user_matches_login_019d(user: CompanyUser, username: str, panel_type: str) -> bool:
    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    if mini_panel.get("enabled") is not True:
        return False
    if str(mini_panel.get("type") or "").strip().lower() != panel_type:
        return False

    login = str(username or "").strip().lower()
    candidates = {
        str(user.email or "").strip().lower(),
        str(mini_panel.get("username") or "").strip().lower(),
    }
    return login in candidates


async def _cx_find_minipanel_login_user_019d(
    db: AsyncSession,
    company_id: UUID,
    *,
    username: str,
    panel_type: str,
) -> Optional[CompanyUser]:
    result = await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    users = result.scalars().all()
    for user in users:
        if _cx_minipanel_user_matches_login_019d(user, username, panel_type):
            return user
    return None


async def _cx_minipanel_session_payload_019d(
    db: AsyncSession,
    company: Company,
    user: CompanyUser,
    panel_type: str,
) -> Dict[str, Any]:
    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    employee_payload: Dict[str, Any] | None = None

    raw_employee_id = mini_panel.get("employee_id")
    if raw_employee_id:
        try:
            employee_id = UUID(str(raw_employee_id))
            result = await db.execute(
                select(Employee).where(
                    Employee.company_id == company.id,
                    Employee.id == employee_id,
                )
            )
            employee = result.scalar_one_or_none()
            if employee:
                employee_payload = {
                    "id": str(employee.id),
                    "full_name": employee.full_name,
                    "phone": employee.phone,
                    "role": employee.role or employee.employee_type,
                    "status": employee.status,
                }
        except Exception:
            employee_payload = None

    return {
        "ok": True,
        "company": {
            "id": str(company.id),
            "name": company.name,
            "slug": company.slug,
            "status": company.status,
            "timezone": company.timezone,
        },
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "status": user.status,
            "must_change_password": bool(getattr(user, "must_change_password", False)),
        },
        "mini_panel": {
            "enabled": True,
            "type": panel_type,
            "type_label": _cx_minipanel_type_label_019d(panel_type),
            "username": mini_panel.get("username") or user.email,
            "employee_id": mini_panel.get("employee_id"),
            "link": mini_panel.get("link"),
            "source": mini_panel.get("source"),
        },
        "employee": employee_payload,
    }


@router.post("/{company_id}/mini-panel-login")
async def mini_panel_login(
    company_id: UUID,
    payload: MiniPanelLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    panel_type = _cx_panel_type_019d(payload.panel_type)
    company = await _cx_company_or_404_019d(db, company_id)

    user = await _cx_find_minipanel_login_user_019d(
        db,
        company_id,
        username=payload.username,
        panel_type=panel_type,
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o clave inválidos.")

    if str(user.status or "").lower() not in {"active", "activo"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo o bloqueado.")

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts = int(user.failed_login_attempts or 0) + 1
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o clave inválidos.")

    user.failed_login_attempts = 0
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    expires_in_minutes = get_access_token_expire_minutes()
    token = create_access_token(
        {
            "sub": str(user.id),
            "user_id": str(user.id),
            "company_id": str(company_id),
            "role": user.role,
            "mini_panel": True,
            "panel_type": panel_type,
        },
        expires_minutes=expires_in_minutes,
    )

    session = await _cx_minipanel_session_payload_019d(db, company, user, panel_type)
    session.update({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in_minutes * 60,
    })
    return session


@router.get("/{company_id}/mini-panel-session")
async def mini_panel_session(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    clean_type = _cx_panel_type_019d(panel_type)
    token = _cx_bearer_token_019d(authorization)
    user = await get_current_company_user(db, token)

    if str(user.company_id) != str(company_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El usuario no pertenece a esta empresa.")

    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    if mini_panel.get("enabled") is not True or str(mini_panel.get("type") or "") != clean_type:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso no autorizado para este mini panel.")

    company = await _cx_company_or_404_019d(db, company_id)
    return await _cx_minipanel_session_payload_019d(db, company, user, clean_type)


# CLONEXA_019D_MINIPANEL_LOGIN_BACKEND_END


MINI_PANEL_ALLOWED_TYPES_019C = {"sales", "store", "inventory", "logistics", "other"}
SALES_ROLE_TOKENS_019C = {"vendedor", "ventas", "sales", "comercial", "asesor_comercial", "asesor comercial"}


def _cx_slug_019c(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    text_value = (
        text_value
        .replace("Ã¡", "a").replace("Ã©", "e").replace("Ã­", "i")
        .replace("Ã³", "o").replace("Ãº", "u").replace("Ã±", "n")
    )
    text_value = re.sub(r"[^a-z0-9]+", ".", text_value).strip(".")
    return text_value or "usuario"


def _cx_employee_is_sales_019c(employee: Employee) -> bool:
    role_value = str(getattr(employee, "role", "") or "").strip().lower()
    employee_type = str(getattr(employee, "employee_type", "") or "").strip().lower()
    normalized = {
        role_value,
        employee_type,
        role_value.replace("_", " "),
        role_value.replace(" ", "_"),
        employee_type.replace("_", " "),
        employee_type.replace(" ", "_"),
    }
    return bool(normalized.intersection(SALES_ROLE_TOKENS_019C))


def _cx_operational_email_019c(company_id: UUID, panel_type: str, employee_id: UUID) -> str:
    return f"mini+{panel_type}+{employee_id.hex}@clonexa.local"


def _cx_operational_username_019c(employee: Employee, panel_type: str) -> str:
    name = _cx_slug_019c(getattr(employee, "full_name", "") or getattr(employee, "phone", ""))
    return f"{name}.{panel_type}"[:80]


def _cx_user_settings_019c(user: CompanyUser) -> Dict[str, Any]:
    raw = getattr(user, "settings_json", None)
    return raw if isinstance(raw, dict) else {}


def _cx_is_minipanel_user_019c(user: CompanyUser, panel_type: Optional[str] = None) -> bool:
    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    if not mini_panel.get("enabled"):
        return False
    if panel_type and str(mini_panel.get("type") or "") != str(panel_type):
        return False
    return True


async def _cx_employee_or_404_019c(db: AsyncSession, company_id: UUID, employee_id: UUID) -> Employee:
    result = await db.execute(
        select(Employee).where(
            Employee.company_id == company_id,
            Employee.id == employee_id,
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empleado no encontrado.")
    return employee


async def _cx_find_minipanel_user_019c(
    db: AsyncSession,
    company_id: UUID,
    employee_id: UUID,
    panel_type: str,
) -> Optional[CompanyUser]:
    result = await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    users = result.scalars().all()
    for user in users:
        settings = _cx_user_settings_019c(user)
        mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
        if (
            mini_panel.get("enabled") is True
            and str(mini_panel.get("type") or "") == panel_type
            and str(mini_panel.get("employee_id") or "") == str(employee_id)
        ):
            return user
    return None


def _cx_minipanel_user_payload_019c(user: CompanyUser, temporary_password: Optional[str] = None) -> Dict[str, Any]:
    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    return {
        "id": str(user.id),
        "company_id": str(user.company_id),
        "email": user.email,
        "username": mini_panel.get("username") or user.email,
        "full_name": user.full_name,
        "role": user.role,
        "status": user.status,
        "panel_type": mini_panel.get("type"),
        "employee_id": mini_panel.get("employee_id"),
        "link": mini_panel.get("link"),
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
        "updated_at": user.updated_at.isoformat() if getattr(user, "updated_at", None) else None,
        "temporary_password": temporary_password,
        "already_exists": temporary_password is None,
    }


@router.get("/{company_id}/mini-panel-users")
async def list_mini_panel_users(
    company_id: UUID,
    panel_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[Dict[str, Any]]:
    clean_type = str(panel_type or "").strip().lower() or None
    if clean_type and clean_type not in MINI_PANEL_ALLOWED_TYPES_019C:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de mini panel invalido.")

    result = await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    users = result.scalars().all()
    filtered = [user for user in users if _cx_is_minipanel_user_019c(user, clean_type)]
    return [_cx_minipanel_user_payload_019c(user) for user in filtered]


@router.post("/{company_id}/mini-panel-users/sales/from-employee")
async def create_sales_mini_panel_user(
    company_id: UUID,
    payload: SalesMiniPanelUserCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    employee = await _cx_employee_or_404_019c(db, company_id, payload.employee_id)

    if not _cx_employee_is_sales_019c(employee):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El empleado debe tener rol vendedor, ventas, comercial o asesor comercial.",
        )

    existing = await _cx_find_minipanel_user_019c(db, company_id, payload.employee_id, "sales")
    if existing:
        return _cx_minipanel_user_payload_019c(existing)

    temp_password = generate_temporary_password()
    now = datetime.now(timezone.utc)
    username = _cx_operational_username_019c(employee, "sales")
    email = _cx_operational_email_019c(company_id, "sales", payload.employee_id)

    user = CompanyUser(
        company_id=company_id,
        email=email,
        password_hash=hash_password(temp_password),
        full_name=str(getattr(employee, "full_name", "") or username),
        role="operator",
        status="active",
        must_change_password=True,
        failed_login_attempts=0,
        locked_until=None,
        last_password_reset_at=now,
        created_at=now,
        updated_at=now,
        settings_json={
            "mini_panel": {
                "enabled": True,
                "type": "sales",
                "employee_id": str(payload.employee_id),
                "username": username,
                "link": str(payload.link or ""),
                "source": "client_sales_module",
            }
        },
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return _cx_minipanel_user_payload_019c(user, temporary_password=temp_password)


# CLONEXA_019D_R2_MINIPANEL_PASSWORD_RESET_START
@router.post("/{company_id}/mini-panel-users/{user_id}/reset-password")
async def reset_mini_panel_user_password_019d_r2(
    company_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    result = await db.execute(
        select(CompanyUser).where(
            CompanyUser.company_id == company_id,
            CompanyUser.id == user_id,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario mini panel no encontrado.")

    if not _cx_is_minipanel_user_019c(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario no pertenece a mini panel.")

    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    panel_type = str(mini_panel.get("type") or "").strip().lower()
    if panel_type not in MINI_PANEL_ALLOWED_TYPES_019C:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de mini panel invalido.")

    temp_password = generate_temporary_password()
    now = datetime.now(timezone.utc)

    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_password_reset_at = now
    user.updated_at = now

    await db.commit()
    await db.refresh(user)

    return _cx_minipanel_user_payload_019c(user, temporary_password=temp_password)
# CLONEXA_019D_R2_MINIPANEL_PASSWORD_RESET_END

# CLONEXA_019F_MINI_PANEL_SALES_OPERATIVE_START

async def _cx_mp_work_ensure_019f(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS mini_panel_work_sessions (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL,
            user_id uuid NOT NULL,
            employee_id uuid NULL,
            panel_type text NOT NULL,
            status text NOT NULL DEFAULT 'active',
            location_label text NOT NULL DEFAULT 'Trabajo',
            started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz NULL,
            active_seconds integer NOT NULL DEFAULT 0,
            break_seconds integer NOT NULL DEFAULT 0,
            active_started_at timestamptz NULL,
            current_break_started_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mini_panel_work_sessions_company_user_type
        ON mini_panel_work_sessions (company_id, user_id, panel_type, started_at DESC)
    """))


def _cx_mp_dt_019f(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _cx_mp_seconds_between_019f(start: Any, end: datetime) -> int:
    started = _cx_mp_dt_019f(start)
    if not started:
        return 0
    return max(0, int((end - started).total_seconds()))


def _cx_mp_label_019f(value: Any) -> str | None:
    dt = _cx_mp_dt_019f(value)
    if not dt:
        return None
    return dt.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M")


async def _cx_mp_auth_context_019f(
    db: AsyncSession,
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str],
) -> tuple[Company, CompanyUser, Dict[str, Any]]:
    clean_type = _cx_panel_type_019d(panel_type)
    token = _cx_bearer_token_019d(authorization)
    user = await get_current_company_user(db, token)

    if str(user.company_id) != str(company_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El usuario no pertenece a esta empresa.")

    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    if mini_panel.get("enabled") is not True or str(mini_panel.get("type") or "") != clean_type:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso no autorizado para este mini panel.")

    company = await _cx_company_or_404_019d(db, company_id)
    return company, user, mini_panel


def _cx_mp_operational_payload_019f(row: Any) -> Dict[str, Any]:
    data = dict(row or {})
    now = datetime.now(timezone.utc)

    status_value = str(data.get("status") or "active").lower()
    active_seconds = int(data.get("active_seconds") or 0)
    break_seconds = int(data.get("break_seconds") or 0)

    if status_value == "active":
        active_seconds += _cx_mp_seconds_between_019f(data.get("active_started_at"), now)
    elif status_value == "break":
        break_seconds += _cx_mp_seconds_between_019f(data.get("current_break_started_at"), now)

    started_at = _cx_mp_dt_019f(data.get("started_at"))
    ended_at = _cx_mp_dt_019f(data.get("ended_at"))
    active_started_at = _cx_mp_dt_019f(data.get("active_started_at"))
    current_break_started_at = _cx_mp_dt_019f(data.get("current_break_started_at"))

    return {
        "id": str(data.get("id")),
        "company_id": str(data.get("company_id")),
        "user_id": str(data.get("user_id")),
        "employee_id": str(data.get("employee_id")) if data.get("employee_id") else None,
        "panel_type": str(data.get("panel_type") or ""),
        "status": status_value,
        "location_label": data.get("location_label") or "Trabajo",
        "started_at": started_at.isoformat() if started_at else None,
        "started_label": _cx_mp_label_019f(started_at),
        "ended_at": ended_at.isoformat() if ended_at else None,
        "active_started_at": active_started_at.isoformat() if active_started_at else None,
        "current_break_started_at": current_break_started_at.isoformat() if current_break_started_at else None,
        "active_seconds": active_seconds,
        "break_seconds": break_seconds,
        "paid_seconds": active_seconds,
        "server_time": now.isoformat(),
        "kpis": {
            "monthly_sales_total": 0,
            "monthly_goal": 0,
            "goal_currency": "COP",
            "promotions": [],
        },
    }


async def _cx_mp_fetch_open_session_019f(
    db: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    panel_type: str,
) -> Dict[str, Any] | None:
    await _cx_mp_work_ensure_019f(db)
    result = await db.execute(
        text("""
            SELECT *
            FROM mini_panel_work_sessions
            WHERE company_id = CAST(:company_id AS uuid)
              AND user_id = CAST(:user_id AS uuid)
              AND panel_type = :panel_type
              AND status IN ('active', 'break')
            ORDER BY started_at DESC
            LIMIT 1
        """),
        {
            "company_id": str(company_id),
            "user_id": str(user_id),
            "panel_type": panel_type,
        },
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _cx_mp_fetch_session_by_id_019f(db: AsyncSession, session_id: str) -> Dict[str, Any]:
    result = await db.execute(
        text("SELECT * FROM mini_panel_work_sessions WHERE id = CAST(:id AS uuid) LIMIT 1"),
        {"id": str(session_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SesiÃ³n operativa no encontrada.")
    return dict(row)


async def _cx_mp_create_session_019f(
    db: AsyncSession,
    company_id: UUID,
    user: CompanyUser,
    mini_panel: Dict[str, Any],
    panel_type: str,
) -> Dict[str, Any]:
    await _cx_mp_work_ensure_019f(db)
    now = datetime.now(timezone.utc)
    session_id = str(uuid4())
    employee_id = mini_panel.get("employee_id")

    await db.execute(
        text("""
            INSERT INTO mini_panel_work_sessions (
                id,
                company_id,
                user_id,
                employee_id,
                panel_type,
                status,
                location_label,
                started_at,
                active_started_at,
                active_seconds,
                break_seconds,
                created_at,
                updated_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:company_id AS uuid),
                CAST(:user_id AS uuid),
                CAST(:employee_id AS uuid),
                :panel_type,
                'active',
                'Trabajo',
                :now,
                :now,
                0,
                0,
                :now,
                :now
            )
        """),
        {
            "id": session_id,
            "company_id": str(company_id),
            "user_id": str(user.id),
            "employee_id": str(employee_id) if employee_id else None,
            "panel_type": panel_type,
            "now": now,
        },
    )
    await db.commit()
    return await _cx_mp_fetch_session_by_id_019f(db, session_id)


async def _cx_mp_get_or_create_session_019f(
    db: AsyncSession,
    company_id: UUID,
    user: CompanyUser,
    mini_panel: Dict[str, Any],
    panel_type: str,
) -> Dict[str, Any]:
    open_session = await _cx_mp_fetch_open_session_019f(db, company_id, user.id, panel_type)
    if open_session:
        return open_session
    return await _cx_mp_create_session_019f(db, company_id, user, mini_panel, panel_type)


@router.get("/{company_id}/mini-panel-operational-session")
async def mini_panel_operational_session_019f(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    _, user, mini_panel = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    clean_type = _cx_panel_type_019d(panel_type)
    row = await _cx_mp_get_or_create_session_019f(db, company_id, user, mini_panel, clean_type)
    return {"ok": True, "operational_session": _cx_mp_operational_payload_019f(row)}


@router.post("/{company_id}/mini-panel-operational-session/pause")
async def mini_panel_operational_pause_019f(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    _, user, _ = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    clean_type = _cx_panel_type_019d(panel_type)
    row = await _cx_mp_fetch_open_session_019f(db, company_id, user.id, clean_type)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay sesiÃ³n operativa activa.")
    if str(row.get("status") or "") == "break":
        return {"ok": True, "operational_session": _cx_mp_operational_payload_019f(row)}

    now = datetime.now(timezone.utc)
    active_delta = _cx_mp_seconds_between_019f(row.get("active_started_at"), now)
    await db.execute(
        text("""
            UPDATE mini_panel_work_sessions
            SET status = 'break',
                active_seconds = COALESCE(active_seconds, 0) + :active_delta,
                active_started_at = NULL,
                current_break_started_at = :now,
                updated_at = :now
            WHERE id = CAST(:id AS uuid)
        """),
        {"id": str(row["id"]), "active_delta": active_delta, "now": now},
    )
    await db.commit()
    updated = await _cx_mp_fetch_session_by_id_019f(db, str(row["id"]))
    return {"ok": True, "operational_session": _cx_mp_operational_payload_019f(updated)}


@router.post("/{company_id}/mini-panel-operational-session/resume")
async def mini_panel_operational_resume_019f(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    _, user, _ = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    clean_type = _cx_panel_type_019d(panel_type)
    row = await _cx_mp_fetch_open_session_019f(db, company_id, user.id, clean_type)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay sesiÃ³n operativa activa.")
    if str(row.get("status") or "") == "active":
        return {"ok": True, "operational_session": _cx_mp_operational_payload_019f(row)}

    now = datetime.now(timezone.utc)
    break_delta = _cx_mp_seconds_between_019f(row.get("current_break_started_at"), now)
    await db.execute(
        text("""
            UPDATE mini_panel_work_sessions
            SET status = 'active',
                break_seconds = COALESCE(break_seconds, 0) + :break_delta,
                current_break_started_at = NULL,
                active_started_at = :now,
                updated_at = :now
            WHERE id = CAST(:id AS uuid)
        """),
        {"id": str(row["id"]), "break_delta": break_delta, "now": now},
    )
    await db.commit()
    updated = await _cx_mp_fetch_session_by_id_019f(db, str(row["id"]))
    return {"ok": True, "operational_session": _cx_mp_operational_payload_019f(updated)}


@router.post("/{company_id}/mini-panel-operational-session/finish")
async def mini_panel_operational_finish_019f(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    _, user, _ = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    clean_type = _cx_panel_type_019d(panel_type)
    row = await _cx_mp_fetch_open_session_019f(db, company_id, user.id, clean_type)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay sesiÃ³n operativa activa.")

    now = datetime.now(timezone.utc)
    active_delta = 0
    break_delta = 0

    if str(row.get("status") or "") == "active":
        active_delta = _cx_mp_seconds_between_019f(row.get("active_started_at"), now)
    elif str(row.get("status") or "") == "break":
        break_delta = _cx_mp_seconds_between_019f(row.get("current_break_started_at"), now)

    await db.execute(
        text("""
            UPDATE mini_panel_work_sessions
            SET status = 'finished',
                ended_at = :now,
                active_seconds = COALESCE(active_seconds, 0) + :active_delta,
                break_seconds = COALESCE(break_seconds, 0) + :break_delta,
                active_started_at = NULL,
                current_break_started_at = NULL,
                updated_at = :now
            WHERE id = CAST(:id AS uuid)
        """),
        {
            "id": str(row["id"]),
            "active_delta": active_delta,
            "break_delta": break_delta,
            "now": now,
        },
    )
    await db.commit()
    updated = await _cx_mp_fetch_session_by_id_019f(db, str(row["id"]))
    return {"ok": True, "operational_session": _cx_mp_operational_payload_019f(updated)}

# CLONEXA_019F_MINI_PANEL_SALES_OPERATIVE_END

# CLONEXA_019C_SALES_MINIPANEL_USERS_BACKEND_END




@router.get("/{company_id}/users", response_model=list[CompanyUserOut])
async def list_users(company_id: UUID, db: AsyncSession = Depends(get_db)):
    users = await list_company_users(db, company_id)
    return [await company_user_out_payload(db, user) for user in users]


@router.post("/{company_id}/users", response_model=CompanyUserOut)
async def create_user(
    company_id: UUID,
    payload: AdminCreateCompanyUserRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await create_company_user(db, company_id, payload)
    return await company_user_out_payload(db, user)


@router.put("/{company_id}/users/{user_id}", response_model=CompanyUserOut)
async def update_user(
    company_id: UUID,
    user_id: UUID,
    payload: AdminUpdateCompanyUserRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await update_company_user(db, company_id, user_id, payload)
    return await company_user_out_payload(db, user)


@router.post("/{company_id}/users/{user_id}/reset-password", response_model=AdminResetPasswordResponse)
async def reset_password(
    company_id: UUID,
    user_id: UUID,
    payload: AdminResetPasswordRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    password = payload.password if payload else None
    return await reset_company_user_password(db, company_id, user_id, password)


@router.post("/{company_id}/users/{user_id}/unlock", response_model=UnlockUserResponse)
async def unlock_user(company_id: UUID, user_id: UUID, db: AsyncSession = Depends(get_db)):
    return await unlock_company_user(db, company_id, user_id)
