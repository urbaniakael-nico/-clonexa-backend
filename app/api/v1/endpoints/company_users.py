from __future__ import annotations

from uuid import UUID, uuid4
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import json
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.employees import (
    add_attendance_event,
    ensure_attendance_storage,
    upsert_attendance_status,
)
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
from app.services.access_sessions import ensure_access_sessions_storage, register_access_session
from app.api.v1.endpoints.transport_calls import ensure_transport_calls_storage

router = APIRouter()

# CLONEXA_019C_SALES_MINIPANEL_USERS_BACKEND_START

class SalesMiniPanelUserCreateRequest(BaseModel):
    employee_id: UUID
    link: Optional[str] = None


class SalesMiniPanelGoalUpdateRequest(BaseModel):
    monthly_goal: float = 0
    goal_currency: str | None = "COP"


class SalesMiniPanelMessageUpdateRequest(BaseModel):
    message: str | None = ""


class StoreLoginSlot023V(BaseModel):
    id: str
    name: str
    employee_ids: list[str] = []


class StoreLoginConfigUpdateRequest023V(BaseModel):
    stores: list[StoreLoginSlot023V] = []


class StoreTeamMemberLoginRequest023W(BaseModel):
    username: str = ""
    password: str = ""


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
        "call": "call_center",
        "call_center": "call_center",
        "callcenter": "call_center",
        "call center": "call_center",
        "llamadas": "call_center",
        "externo": "external",
        "externos": "external",
        "external": "external",
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
        "call_center": "Call Center",
        "external": "Externo",
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
    request: Request,
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
    session_key = await register_access_session(
        db,
        company_id=company_id,
        scope="mini_panel",
        subject_id=user.id,
        subject_label=f"{user.full_name or user.email or 'mini panel'} / {panel_type}",
        request=request,
        metadata={"panel_type": panel_type},
    )
    token = create_access_token(
        {
            "sub": str(user.id),
            "user_id": str(user.id),
            "company_id": str(company_id),
            "role": user.role,
            "mini_panel": True,
            "panel_type": panel_type,
            "scope": "mini_panel",
            "sid": session_key,
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


MINI_PANEL_ALLOWED_TYPES_019C = {"sales", "store", "inventory", "logistics", "call_center", "external", "other"}
SALES_ROLE_TOKENS_019C = {"vendedor", "ventas", "sales", "comercial", "asesor_comercial", "asesor comercial"}
STORE_ROLE_TOKENS_023S = {
    "cajero",
    "cajera",
    "caja",
    "cashier",
    "tienda",
    "tiendas",
    "store",
    "stores",
    "retail",
    "punto_venta",
    "punto de venta",
    "punto_de_venta",
}


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


def _cx_employee_is_store_023s(employee: Employee) -> bool:
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
    return bool(normalized.intersection(STORE_ROLE_TOKENS_023S)) or any(
        "cajer" in token
        or "caja" in token
        or "tienda" in token
        or "store" in token
        or "retail" in token
        for token in normalized
    )


def _cx_operational_email_019c(company_id: UUID, panel_type: str, employee_id: UUID) -> str:
    return f"mini+{panel_type}+{employee_id.hex}@clonexa.local"


def _cx_operational_username_019c(employee: Employee, panel_type: str) -> str:
    name = _cx_slug_019c(getattr(employee, "full_name", "") or getattr(employee, "phone", ""))
    return f"{name}.{panel_type}"[:80]


def _cx_user_settings_019c(user: CompanyUser) -> Dict[str, Any]:
    raw = getattr(user, "settings_json", None)
    return raw if isinstance(raw, dict) else {}


def _cx_money_023p(value: Any) -> float:
    try:
        amount = float(value or 0)
    except Exception:
        return 0.0
    if amount < 0:
        return 0.0
    return round(amount, 2)


def _cx_goal_currency_023p(value: Any) -> str:
    raw = str(value or "COP").strip().upper()
    clean = re.sub(r"[^A-Z]", "", raw)[:3]
    return clean or "COP"


def _cx_minipanel_goal_023p(mini_panel: Dict[str, Any]) -> Dict[str, Any]:
    goal = _cx_money_023p(
        mini_panel.get("monthly_goal")
        or mini_panel.get("sales_goal")
        or mini_panel.get("goal")
        or 0
    )
    return {
        "monthly_goal": goal,
        "goal_currency": _cx_goal_currency_023p(mini_panel.get("goal_currency")),
    }


def _cx_company_settings_023p(company: Company | None) -> Dict[str, Any]:
    raw = getattr(company, "settings_json", None) if company is not None else None
    return raw if isinstance(raw, dict) else {}


def _cx_store_login_default_slots_023v() -> list[Dict[str, Any]]:
    return [
        {
            "id": f"store_{index}",
            "name": f"Tienda {index}",
            "employee_ids": [],
        }
        for index in range(1, 6)
    ]


def _cx_store_login_sanitize_023v(raw_stores: Any) -> list[Dict[str, Any]]:
    source = raw_stores if isinstance(raw_stores, list) else []
    by_id: Dict[str, Dict[str, Any]] = {}
    for item in source:
        if not isinstance(item, dict):
            continue
        raw_id = str(item.get("id") or "").strip().lower()
        slot_id = raw_id if raw_id in {f"store_{index}" for index in range(1, 6)} else ""
        if not slot_id:
            continue
        by_id[slot_id] = item

    assigned: set[str] = set()
    clean_slots: list[Dict[str, Any]] = []
    for index in range(1, 6):
        slot_id = f"store_{index}"
        item = by_id.get(slot_id, {})
        name = str(item.get("name") or f"Tienda {index}").strip()[:60] or f"Tienda {index}"
        employee_ids: list[str] = []
        raw_employee_ids = item.get("employee_ids") if isinstance(item.get("employee_ids"), list) else []
        for employee_id in raw_employee_ids:
            clean_id = str(employee_id or "").strip()
            if not clean_id or clean_id in assigned:
                continue
            assigned.add(clean_id)
            employee_ids.append(clean_id)
            if len(employee_ids) >= 12:
                break
        clean_slots.append({
            "id": slot_id,
            "name": name,
            "employee_ids": employee_ids,
        })
    return clean_slots


def _cx_store_login_config_023v(company: Company | None) -> Dict[str, Any]:
    store = _cx_company_settings_023p(company)
    config = store.get("client_store_login") if isinstance(store.get("client_store_login"), dict) else {}
    stores = _cx_store_login_sanitize_023v(config.get("stores"))
    if not stores:
        stores = _cx_store_login_default_slots_023v()
    return {
        "stores": stores,
        "updated_at": config.get("updated_at"),
    }


def _cx_panel_settings_key_023s(panel_type: Any) -> str:
    raw = str(panel_type or "sales").strip().lower()
    if raw in {"store", "stores", "tienda", "tiendas"}:
        return "client_stores"
    return "client_sales"


def _cx_panel_message_title_023s(panel_type: Any) -> str:
    raw = str(panel_type or "sales").strip().lower()
    if raw in {"store", "stores", "tienda", "tiendas"}:
        return "Mensaje de tiendas"
    return "Mensaje de ventas"


def _cx_panel_record_types_023s(panel_type: Any) -> list[str]:
    raw = str(panel_type or "sales").strip().lower()
    if raw in {"store", "stores", "tienda", "tiendas"}:
        return ["store", "stores", "tienda", "tiendas"]
    return ["sales", "venta", "ventas"]


def _cx_panel_promotions_023s(company: Company | None, panel_type: Any = "sales") -> list[Dict[str, Any]]:
    store = _cx_company_settings_023p(company)
    key = _cx_panel_settings_key_023s(panel_type)
    client_panel = store.get(key) if isinstance(store.get(key), dict) else {}
    raw_promotions = client_panel.get("promotions")
    if isinstance(raw_promotions, list):
        items = [item for item in raw_promotions if isinstance(item, dict) and str(item.get("message") or item.get("title") or "").strip()]
        if items:
            return items[:3]

    message = str(client_panel.get("promotion_message") or "").strip()
    if not message:
        return []
    return [{
        "title": client_panel.get("promotion_title") or _cx_panel_message_title_023s(panel_type),
        "message": message,
        "status": "active",
        "updated_at": client_panel.get("promotion_updated_at"),
    }]


def _cx_sales_promotions_023p(company: Company | None) -> list[Dict[str, Any]]:
    return _cx_panel_promotions_023s(company, "sales")


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


async def _cx_sales_user_stats_023q(
    db: AsyncSession,
    company_id: UUID,
    users: list[CompanyUser],
    panel_type: str = "sales",
) -> Dict[str, Dict[str, Any]]:
    clean_panel = "store" if str(panel_type or "").strip().lower() in {"store", "stores", "tienda", "tiendas"} else "sales"
    sales_users = [user for user in users if _cx_is_minipanel_user_019c(user, clean_panel)]
    if not sales_users:
        return {}
    if not await _cx_table_exists_023p(db, "mini_panel_sales_records"):
        return {}

    params: Dict[str, Any] = {"company_id": str(company_id)}
    placeholders: list[str] = []
    for index, user in enumerate(sales_users):
        key = f"user_{index}"
        params[key] = str(user.id)
        placeholders.append(f"CAST(:{key} AS uuid)")

    panel_types = _cx_panel_record_types_023s(clean_panel)
    panel_placeholders: list[str] = []
    for index, panel_alias in enumerate(panel_types):
        key = f"panel_{index}"
        params[key] = panel_alias
        panel_placeholders.append(f":{key}")

    where = [
        "company_id = CAST(:company_id AS uuid)",
        f"panel_type IN ({', '.join(panel_placeholders)})",
        f"created_by IN ({', '.join(placeholders)})",
    ]

    started_at = await _cx_sales_cut_started_at_023p(db, company_id)
    if started_at:
        where.append("created_at >= :started_at")
        params["started_at"] = started_at

    result = await db.execute(
        text(f"""
            SELECT
                created_by::text AS user_id,
                COALESCE(SUM(total), 0)::float AS sales_total,
                COUNT(*)::int AS sales_count,
                COUNT(*) FILTER (WHERE status <> 'archived')::int AS visible_sales_count
            FROM mini_panel_sales_records
            WHERE {" AND ".join(where)}
            GROUP BY created_by
        """),
        params,
    )

    stats: Dict[str, Dict[str, Any]] = {}
    for row in result.mappings().all():
        stats[str(row.get("user_id") or "")] = {
            "sales_total": _cx_money_023p(row.get("sales_total")),
            "sales_count": int(row.get("sales_count") or 0),
            "visible_sales_count": int(row.get("visible_sales_count") or 0),
        }
    return stats


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


def _cx_goal_percent_023q(total: Any, goal: Any) -> int:
    goal_amount = _cx_money_023p(goal)
    if goal_amount <= 0:
        return 0
    return max(0, min(100, round((_cx_money_023p(total) / goal_amount) * 100)))


def _cx_minipanel_user_payload_019c(
    user: CompanyUser,
    temporary_password: Optional[str] = None,
    sales_stats: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    goal = _cx_minipanel_goal_023p(mini_panel)
    stats = sales_stats if isinstance(sales_stats, dict) else {}
    sales_total = _cx_money_023p(stats.get("sales_total") or stats.get("monthly_sales_total") or 0)
    sales_count = int(stats.get("sales_count") or stats.get("monthly_sales_count") or 0)
    visible_count = int(stats.get("visible_sales_count") or 0)
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
        "monthly_goal": goal["monthly_goal"],
        "goal_currency": goal["goal_currency"],
        "monthly_sales_total": sales_total,
        "monthly_sales_count": sales_count,
        "visible_sales_count": visible_count,
        "goal_progress_percent": _cx_goal_percent_023q(sales_total, goal["monthly_goal"]),
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
    stats_panel = clean_type or "sales"
    sales_stats = await _cx_sales_user_stats_023q(db, company_id, filtered, stats_panel) if stats_panel in {"sales", "store"} else {}
    return [
        _cx_minipanel_user_payload_019c(user, sales_stats=sales_stats.get(str(user.id)))
        for user in filtered
    ]


async def _cx_create_minipanel_user_from_employee_026j(
    *,
    company_id: UUID,
    payload: SalesMiniPanelUserCreateRequest,
    panel_type: str,
    db: AsyncSession,
    source: str,
) -> Dict[str, Any]:
    clean_type = _cx_panel_type_019d(panel_type)
    employee = await _cx_employee_or_404_019c(db, company_id, payload.employee_id)

    if clean_type == "sales" and not _cx_employee_is_sales_019c(employee):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El empleado debe tener rol vendedor, ventas, comercial o asesor comercial.",
        )

    if clean_type == "store" and not _cx_employee_is_store_023s(employee):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El empleado debe tener rol cajero, tienda, punto de venta o retail.",
        )

    existing = await _cx_find_minipanel_user_019c(db, company_id, payload.employee_id, clean_type)
    if existing:
        return _cx_minipanel_user_payload_019c(existing)

    temp_password = generate_temporary_password()
    now = datetime.now(timezone.utc)
    username = _cx_operational_username_019c(employee, clean_type)
    email = _cx_operational_email_019c(company_id, clean_type, payload.employee_id)

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
                "type": clean_type,
                "employee_id": str(payload.employee_id),
                "username": username,
                "link": str(payload.link or ""),
                "source": source,
                "monthly_goal": 0,
                "goal_currency": "COP",
            }
        },
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return _cx_minipanel_user_payload_019c(user, temporary_password=temp_password)


@router.post("/{company_id}/mini-panel-users/sales/from-employee")
async def create_sales_mini_panel_user(
    company_id: UUID,
    payload: SalesMiniPanelUserCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    return await _cx_create_minipanel_user_from_employee_026j(
        company_id=company_id,
        payload=payload,
        panel_type="sales",
        db=db,
        source="client_sales_module",
    )


@router.post("/{company_id}/mini-panel-users/store/from-employee")
async def create_store_mini_panel_user_023s(
    company_id: UUID,
    payload: SalesMiniPanelUserCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    return await _cx_create_minipanel_user_from_employee_026j(
        company_id=company_id,
        payload=payload,
        panel_type="store",
        db=db,
        source="client_stores_module",
    )

@router.post("/{company_id}/mini-panel-users/{panel_type}/from-employee")
async def create_generic_mini_panel_user_026j(
    company_id: UUID,
    panel_type: str,
    payload: SalesMiniPanelUserCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    return await _cx_create_minipanel_user_from_employee_026j(
        company_id=company_id,
        payload=payload,
        panel_type=panel_type,
        db=db,
        source="client_mini_panel_module",
    )


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


# CLONEXA_023P_SALES_GOALS_MESSAGES_START
@router.put("/{company_id}/mini-panel-users/{user_id}/sales-goal")
async def update_sales_mini_panel_goal_023p(
    company_id: UUID,
    user_id: UUID,
    payload: SalesMiniPanelGoalUpdateRequest,
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

    settings = dict(_cx_user_settings_019c(user))
    mini_panel = dict(settings.get("mini_panel") or {})
    panel_type = str(mini_panel.get("type") or "").strip().lower()
    if mini_panel.get("enabled") is not True or panel_type not in {"sales", "store"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario no pertenece a mini panel de ventas o tiendas.")

    mini_panel["monthly_goal"] = _cx_money_023p(payload.monthly_goal)
    mini_panel["goal_currency"] = _cx_goal_currency_023p(payload.goal_currency)
    mini_panel["goal_updated_at"] = datetime.now(timezone.utc).isoformat()
    settings["mini_panel"] = mini_panel
    user.settings_json = settings
    user.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)
    return _cx_minipanel_user_payload_019c(user)


@router.get("/{company_id}/mini-panel-sales-message")
async def get_sales_mini_panel_message_023p(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _cx_company_or_404_019d(db, company_id)
    promotions = _cx_sales_promotions_023p(company)
    first = promotions[0] if promotions else {}
    return {
        "company_id": str(company_id),
        "message": first.get("message") or "",
        "promotions": promotions,
    }


@router.put("/{company_id}/mini-panel-sales-message")
async def update_sales_mini_panel_message_023p(
    company_id: UUID,
    payload: SalesMiniPanelMessageUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _cx_company_or_404_019d(db, company_id)
    message = str(payload.message or "").strip()[:280]
    now = datetime.now(timezone.utc).isoformat()

    store = dict(_cx_company_settings_023p(company))
    client_sales = dict(store.get("client_sales") or {})
    client_sales["promotion_message"] = message
    client_sales["promotion_title"] = "Mensaje de ventas"
    client_sales["promotion_updated_at"] = now if message else None
    client_sales["promotions"] = ([{
        "title": "Mensaje de ventas",
        "message": message,
        "status": "active",
        "updated_at": now,
    }] if message else [])
    store["client_sales"] = client_sales
    company.settings_json = store
    if hasattr(company, "updated_at"):
        company.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(company)
    promotions = _cx_sales_promotions_023p(company)
    return {
        "company_id": str(company_id),
        "message": message,
        "promotions": promotions,
    }


@router.get("/{company_id}/mini-panel-stores-message")
async def get_stores_mini_panel_message_023s(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _cx_company_or_404_019d(db, company_id)
    promotions = _cx_panel_promotions_023s(company, "store")
    first = promotions[0] if promotions else {}
    return {
        "company_id": str(company_id),
        "message": first.get("message") or "",
        "promotions": promotions,
    }


@router.put("/{company_id}/mini-panel-stores-message")
async def update_stores_mini_panel_message_023s(
    company_id: UUID,
    payload: SalesMiniPanelMessageUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _cx_company_or_404_019d(db, company_id)
    message = str(payload.message or "").strip()[:280]
    now = datetime.now(timezone.utc).isoformat()

    store = dict(_cx_company_settings_023p(company))
    client_stores = dict(store.get("client_stores") or {})
    client_stores["promotion_message"] = message
    client_stores["promotion_title"] = "Mensaje de tiendas"
    client_stores["promotion_updated_at"] = now if message else None
    client_stores["promotions"] = ([{
        "title": "Mensaje de tiendas",
        "message": message,
        "status": "active",
        "updated_at": now,
    }] if message else [])
    store["client_stores"] = client_stores
    company.settings_json = store
    if hasattr(company, "updated_at"):
        company.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(company)
    promotions = _cx_panel_promotions_023s(company, "store")
    return {
        "company_id": str(company_id),
        "message": message,
        "promotions": promotions,
    }


@router.get("/{company_id}/store-login-config")
async def get_store_login_config_023v(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _cx_company_or_404_019d(db, company_id)
    config = _cx_store_login_config_023v(company)
    return {
        "company_id": str(company_id),
        **config,
    }


@router.put("/{company_id}/store-login-config")
async def update_store_login_config_023v(
    company_id: UUID,
    payload: StoreLoginConfigUpdateRequest023V,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _cx_company_or_404_019d(db, company_id)
    now = datetime.now(timezone.utc).isoformat()
    store = dict(_cx_company_settings_023p(company))
    clean_stores = _cx_store_login_sanitize_023v([slot.model_dump() for slot in payload.stores])
    store["client_store_login"] = {
        "stores": clean_stores,
        "updated_at": now,
    }
    company.settings_json = store
    if hasattr(company, "updated_at"):
        company.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(company)
    config = _cx_store_login_config_023v(company)
    return {
        "company_id": str(company_id),
        **config,
    }
# CLONEXA_023P_SALES_GOALS_MESSAGES_END

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


async def _cx_table_exists_023p(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
            ) AS exists
        """),
        {"table_name": table_name},
    )
    row = result.mappings().first()
    return bool(row and row.get("exists"))


def _cx_json_dict_023p(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


async def _cx_sales_cut_started_at_023p(db: AsyncSession, company_id: UUID) -> datetime | None:
    if not await _cx_table_exists_023p(db, "mini_panel_sales_settings"):
        return None
    result = await db.execute(
        text("""
            SELECT settings
            FROM mini_panel_sales_settings
            WHERE company_id = CAST(:company_id AS uuid)
            LIMIT 1
        """),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    settings = _cx_json_dict_023p(row.get("settings") if row else None)
    sales_cut = settings.get("sales_cut") if isinstance(settings.get("sales_cut"), dict) else {}
    started = sales_cut.get("started_at") or settings.get("sales_cut_started_at")
    return _cx_mp_dt_019f(started)


async def _cx_mp_sales_kpis_023p(
    db: AsyncSession,
    company: Company,
    user: CompanyUser,
    mini_panel: Dict[str, Any],
) -> Dict[str, Any]:
    goal = _cx_minipanel_goal_023p(mini_panel)
    panel_type = str(mini_panel.get("type") or "").strip().lower()
    kpis: Dict[str, Any] = {
        "monthly_sales_total": 0,
        "monthly_sales_count": 0,
        "visible_sales_count": 0,
        "monthly_goal": goal["monthly_goal"],
        "goal_currency": goal["goal_currency"],
        "promotions": _cx_panel_promotions_023s(company, panel_type),
    }

    if panel_type not in {"sales", "store"}:
        return kpis
    if not await _cx_table_exists_023p(db, "mini_panel_sales_records"):
        return kpis

    params: Dict[str, Any] = {
        "company_id": str(company.id),
        "user_id": str(user.id),
    }
    panel_types = _cx_panel_record_types_023s(panel_type)
    panel_placeholders: list[str] = []
    for index, panel_alias in enumerate(panel_types):
        key = f"panel_{index}"
        params[key] = panel_alias
        panel_placeholders.append(f":{key}")

    where = [
        "company_id = CAST(:company_id AS uuid)",
        "created_by = CAST(:user_id AS uuid)",
        f"panel_type IN ({', '.join(panel_placeholders)})",
    ]
    started_at = await _cx_sales_cut_started_at_023p(db, company.id)
    if started_at:
        where.append("created_at >= :started_at")
        params["started_at"] = started_at

    result = await db.execute(
        text(f"""
            SELECT
                COALESCE(SUM(total), 0)::float AS total_amount,
                COUNT(*)::int AS period_count,
                COUNT(*) FILTER (WHERE status <> 'archived')::int AS visible_count
            FROM mini_panel_sales_records
            WHERE {" AND ".join(where)}
        """),
        params,
    )
    row = result.mappings().first()
    if row:
        kpis["monthly_sales_total"] = _cx_money_023p(row.get("total_amount"))
        kpis["monthly_sales_count"] = int(row.get("period_count") or 0)
        kpis["visible_sales_count"] = int(row.get("visible_count") or 0)
    return kpis


def _cx_mp_workforce_status_023j(value: Any) -> str:
    status_value = str(value or "active").strip().lower()
    if status_value == "break":
        return "on_break"
    if status_value == "finished":
        return "checked_out"
    return "working"


def _cx_mp_event_label_023j(event_type: str, panel_type: str) -> str:
    panel_label = _cx_minipanel_type_label_019d(panel_type)
    return {
        "start_shift": f"Inicio mini panel {panel_label}",
        "break_start": f"Pausa mini panel {panel_label}",
        "break_end": f"Retorno mini panel {panel_label}",
        "check_out": f"Cierre mini panel {panel_label}",
    }.get(event_type, f"Mini panel {panel_label}")


async def _cx_mp_employee_for_attendance_023j(
    db: AsyncSession,
    company_id: UUID,
    employee_id: Any,
) -> Employee | None:
    if not employee_id:
        return None
    try:
        employee_uuid = UUID(str(employee_id))
    except Exception:
        return None
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_uuid,
            Employee.company_id == company_id,
        )
    )
    employee = result.scalar_one_or_none()
    if not employee or str(getattr(employee, "status", "") or "").lower() == "archived":
        return None
    return employee


async def _cx_mp_sync_attendance_023j(
    db: AsyncSession,
    company_id: UUID,
    user: CompanyUser,
    mini_panel: Dict[str, Any],
    session_row: Dict[str, Any],
    *,
    event_type: str | None = None,
    event_at: datetime | None = None,
) -> None:
    employee = await _cx_mp_employee_for_attendance_023j(
        db,
        company_id,
        session_row.get("employee_id") or mini_panel.get("employee_id"),
    )
    if not employee:
        return

    await ensure_attendance_storage(db)

    payload = _cx_mp_operational_payload_019f(session_row)
    status_after = _cx_mp_workforce_status_023j(session_row.get("status"))
    started_at = _cx_mp_dt_019f(session_row.get("started_at")) or datetime.now(timezone.utc)
    ended_at = _cx_mp_dt_019f(session_row.get("ended_at"))
    break_started_at = _cx_mp_dt_019f(session_row.get("current_break_started_at")) if status_after == "on_break" else None

    if not event_type:
        event_type = {
            "working": "start_shift",
            "on_break": "break_start",
            "checked_out": "check_out",
        }.get(status_after, "start_shift")

    event_time = event_at
    if not event_time:
        if status_after == "on_break":
            event_time = break_started_at or _cx_mp_dt_019f(session_row.get("updated_at")) or datetime.now(timezone.utc)
        elif status_after == "checked_out":
            event_time = ended_at or _cx_mp_dt_019f(session_row.get("updated_at")) or datetime.now(timezone.utc)
        else:
            event_time = started_at

    await upsert_attendance_status(
        db,
        employee,
        status_after,
        event_type,
        event_time,
        check_in_at=started_at,
        break_started_at=break_started_at,
        check_out_at=ended_at if status_after == "checked_out" else None,
        worked_minutes=int((payload.get("active_seconds") or 0) // 60),
        break_minutes=int((payload.get("break_seconds") or 0) // 60),
    )

    if event_at:
        source_ref = f"mini_panel:{payload.get('panel_type') or mini_panel.get('type') or ''}"
        event_payload = {
            "mini_panel_session_id": payload.get("id"),
            "mini_panel_type": payload.get("panel_type") or mini_panel.get("type"),
            "mini_panel_label": _cx_minipanel_type_label_019d(payload.get("panel_type") or mini_panel.get("type") or "other"),
            "company_user_id": str(getattr(user, "id", "")),
            "company_user_email": str(getattr(user, "email", "") or ""),
            "location_label": payload.get("location_label"),
            "active_seconds": payload.get("active_seconds"),
            "break_seconds": payload.get("break_seconds"),
        }
        await add_attendance_event(
            db,
            employee,
            event_type,
            status_after,
            source="mini_panel",
            notes=_cx_mp_event_label_023j(event_type, payload.get("panel_type") or mini_panel.get("type") or "other"),
            now=event_time,
            module_code="workforce",
            event_label=_cx_mp_event_label_023j(event_type, payload.get("panel_type") or mini_panel.get("type") or "other"),
            source_ref=source_ref,
            payload_json=event_payload,
            metadata_json={"source_patch": "023J_minipanel_crm_sync"},
        )


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


def _cx_mp_operational_payload_019f(row: Any, kpis: Dict[str, Any] | None = None) -> Dict[str, Any]:
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
        "kpis": kpis or {
            "monthly_sales_total": 0,
            "monthly_goal": 0,
            "goal_currency": "COP",
            "promotions": [],
        },
    }


async def _cx_mp_operational_response_023p(
    db: AsyncSession,
    company: Company,
    user: CompanyUser,
    mini_panel: Dict[str, Any],
    row: Dict[str, Any],
) -> Dict[str, Any]:
    kpis = await _cx_mp_sales_kpis_023p(db, company, user, mini_panel)
    return _cx_mp_operational_payload_019f(row, kpis)


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
    await _cx_mp_sync_attendance_023j(
        db,
        company_id,
        user,
        mini_panel,
        {
            "id": session_id,
            "company_id": str(company_id),
            "user_id": str(user.id),
            "employee_id": str(employee_id) if employee_id else None,
            "panel_type": panel_type,
            "status": "active",
            "location_label": "Trabajo",
            "started_at": now,
            "active_started_at": now,
            "active_seconds": 0,
            "break_seconds": 0,
            "created_at": now,
            "updated_at": now,
        },
        event_type="start_shift",
        event_at=now,
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


# CLONEXA_023W_STORE_TEAM_MINI_PANEL_START
def _cx_store_team_slot_023w(company: Company, employee_id: Any) -> Dict[str, Any] | None:
    clean_employee_id = str(employee_id or "").strip()
    if not clean_employee_id:
        return None
    config = _cx_store_login_config_023v(company)
    for raw_slot in config.get("stores") or []:
        ids = [str(item or "").strip() for item in (raw_slot.get("employee_ids") or []) if str(item or "").strip()]
        if clean_employee_id in ids:
            slot = dict(raw_slot)
            slot["employee_ids"] = ids
            return slot
    return None


def _cx_store_team_ids_023w(company: Company, employee_id: Any) -> tuple[Dict[str, Any], list[str]]:
    clean_employee_id = str(employee_id or "").strip()
    slot = _cx_store_team_slot_023w(company, clean_employee_id)
    if slot:
        return slot, [str(item or "").strip() for item in (slot.get("employee_ids") or []) if str(item or "").strip()]
    fallback_ids = [clean_employee_id] if clean_employee_id else []
    return {
        "id": "store_current",
        "name": "Tienda actual",
        "employee_ids": fallback_ids,
    }, fallback_ids


def _cx_uuid_list_023w(values: list[str]) -> list[UUID]:
    clean_values: list[UUID] = []
    for value in values:
        try:
            clean_values.append(UUID(str(value)))
        except Exception:
            continue
    return clean_values


async def _cx_store_team_employee_map_023w(
    db: AsyncSession,
    company_id: UUID,
    employee_ids: list[str],
) -> Dict[str, Employee]:
    uuids = _cx_uuid_list_023w(employee_ids)
    if not uuids:
        return {}
    result = await db.execute(
        select(Employee).where(
            Employee.company_id == company_id,
            Employee.id.in_(uuids),
        )
    )
    return {str(employee.id): employee for employee in result.scalars().all()}


async def _cx_store_team_users_by_employee_023w(
    db: AsyncSession,
    company_id: UUID,
    employee_ids: list[str],
) -> Dict[str, CompanyUser]:
    wanted = {str(item or "").strip() for item in employee_ids if str(item or "").strip()}
    if not wanted:
        return {}
    result = await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    users: Dict[str, CompanyUser] = {}
    for user in result.scalars().all():
        settings = _cx_user_settings_019c(user)
        mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
        employee_id = str(mini_panel.get("employee_id") or "").strip()
        if (
            mini_panel.get("enabled") is True
            and str(mini_panel.get("type") or "") == "store"
            and employee_id in wanted
        ):
            users[employee_id] = user
    return users


def _cx_store_member_mini_panel_023w(user: CompanyUser | None) -> Dict[str, Any]:
    if not user:
        return {}
    settings = _cx_user_settings_019c(user)
    mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    return mini_panel if isinstance(mini_panel, dict) else {}


async def _cx_store_team_open_sessions_023w(
    db: AsyncSession,
    company_id: UUID,
    users_by_employee: Dict[str, CompanyUser],
) -> Dict[str, Dict[str, Any]]:
    await _cx_mp_work_ensure_019f(db)
    user_to_employee = {str(user.id): employee_id for employee_id, user in users_by_employee.items()}
    if not user_to_employee:
        return {}

    params: Dict[str, Any] = {"company_id": str(company_id)}
    placeholders: list[str] = []
    for index, user_id in enumerate(user_to_employee):
        key = f"user_{index}"
        params[key] = user_id
        placeholders.append(f"CAST(:{key} AS uuid)")

    result = await db.execute(
        text(f"""
            SELECT DISTINCT ON (user_id) *
            FROM mini_panel_work_sessions
            WHERE company_id = CAST(:company_id AS uuid)
              AND user_id IN ({', '.join(placeholders)})
              AND panel_type = 'store'
              AND status IN ('active', 'break')
            ORDER BY user_id, started_at DESC
        """),
        params,
    )
    sessions: Dict[str, Dict[str, Any]] = {}
    for row in result.mappings().all():
        employee_id = user_to_employee.get(str(row.get("user_id")))
        if employee_id:
            sessions[employee_id] = dict(row)
    return sessions


async def _cx_store_team_sales_stats_023w(
    db: AsyncSession,
    company_id: UUID,
    users_by_employee: Dict[str, CompanyUser],
) -> Dict[str, Dict[str, Any]]:
    if not await _cx_table_exists_023p(db, "mini_panel_sales_records"):
        return {}

    employee_ids = set(users_by_employee.keys())
    user_to_employee = {str(user.id): employee_id for employee_id, user in users_by_employee.items()}
    if not employee_ids:
        return {}

    params: Dict[str, Any] = {"company_id": str(company_id)}
    panel_placeholders: list[str] = []
    for index, panel_alias in enumerate(_cx_panel_record_types_023s("store")):
        key = f"panel_{index}"
        params[key] = panel_alias
        panel_placeholders.append(f":{key}")

    where = [
        "company_id = CAST(:company_id AS uuid)",
        f"panel_type IN ({', '.join(panel_placeholders)})",
    ]
    started_at = await _cx_sales_cut_started_at_023p(db, company_id)
    if started_at:
        where.append("created_at >= :started_at")
        params["started_at"] = started_at

    result = await db.execute(
        text(f"""
            SELECT
                created_by::text AS user_id,
                COALESCE(metadata, '{{}}'::jsonb) AS metadata,
                COALESCE(total, 0)::float AS total,
                status
            FROM mini_panel_sales_records
            WHERE {" AND ".join(where)}
        """),
        params,
    )

    stats: Dict[str, Dict[str, Any]] = {}
    for row in result.mappings().all():
        metadata = _cx_json_dict_023p(row.get("metadata"))
        actor = metadata.get("store_actor") if isinstance(metadata.get("store_actor"), dict) else {}
        employee_id = str(actor.get("employee_id") or "").strip() or user_to_employee.get(str(row.get("user_id") or ""), "")
        if employee_id not in employee_ids:
            continue
        target = stats.setdefault(employee_id, {
            "sales_total": 0.0,
            "sales_count": 0,
            "visible_sales_count": 0,
        })
        target["sales_total"] = round(_cx_money_023p(target.get("sales_total")) + _cx_money_023p(row.get("total")), 2)
        target["sales_count"] = int(target.get("sales_count") or 0) + 1
        if str(row.get("status") or "").lower() != "archived":
            target["visible_sales_count"] = int(target.get("visible_sales_count") or 0) + 1
    return stats


def _cx_store_member_payload_023w(
    employee_id: str,
    *,
    employee: Employee | None,
    user: CompanyUser | None,
    session_row: Dict[str, Any] | None,
    sales_stats: Dict[str, Any] | None,
    is_admin: bool,
    is_current: bool,
) -> Dict[str, Any]:
    mini_panel = _cx_store_member_mini_panel_023w(user)
    goal = _cx_minipanel_goal_023p(mini_panel)
    stats = sales_stats if isinstance(sales_stats, dict) else {}
    sales_total = _cx_money_023p(stats.get("sales_total") or 0)
    session_payload = None
    if session_row:
        session_payload = _cx_mp_operational_payload_019f(session_row, {
            "monthly_sales_total": sales_total,
            "monthly_sales_count": int(stats.get("sales_count") or 0),
            "visible_sales_count": int(stats.get("visible_sales_count") or 0),
            "monthly_goal": goal["monthly_goal"],
            "goal_currency": goal["goal_currency"],
            "promotions": [],
        })
    return {
        "employee_id": employee_id,
        "full_name": str(getattr(employee, "full_name", "") or getattr(user, "full_name", "") or "Colaborador"),
        "phone": str(getattr(employee, "phone", "") or ""),
        "role": str(getattr(employee, "role", "") or getattr(employee, "employee_type", "") or "cajero"),
        "status": str(getattr(employee, "status", "") or getattr(user, "status", "") or "active"),
        "user_id": str(user.id) if user else "",
        "username": str(mini_panel.get("username") or getattr(user, "email", "") or ""),
        "has_login": bool(user),
        "is_admin": is_admin,
        "is_current": is_current,
        "monthly_goal": goal["monthly_goal"],
        "goal_currency": goal["goal_currency"],
        "sales_total": sales_total,
        "sales_count": int(stats.get("sales_count") or 0),
        "visible_sales_count": int(stats.get("visible_sales_count") or 0),
        "goal_progress_percent": _cx_goal_percent_023q(sales_total, goal["monthly_goal"]),
        "session": session_payload,
    }


async def _cx_store_team_payload_023w(
    db: AsyncSession,
    company: Company,
    current_user: CompanyUser,
    current_mini_panel: Dict[str, Any],
) -> Dict[str, Any]:
    current_employee_id = str(current_mini_panel.get("employee_id") or "").strip()
    slot, team_ids = _cx_store_team_ids_023w(company, current_employee_id)
    if current_employee_id and current_employee_id not in team_ids:
        team_ids.insert(0, current_employee_id)

    employees = await _cx_store_team_employee_map_023w(db, company.id, team_ids)
    users_by_employee = await _cx_store_team_users_by_employee_023w(db, company.id, team_ids)
    sessions = await _cx_store_team_open_sessions_023w(db, company.id, users_by_employee)
    sales_stats = await _cx_store_team_sales_stats_023w(db, company.id, users_by_employee)
    admin_employee_id = team_ids[0] if team_ids else current_employee_id

    members = [
        _cx_store_member_payload_023w(
            employee_id,
            employee=employees.get(employee_id),
            user=users_by_employee.get(employee_id),
            session_row=sessions.get(employee_id),
            sales_stats=sales_stats.get(employee_id),
            is_admin=(employee_id == admin_employee_id),
            is_current=(employee_id == current_employee_id),
        )
        for employee_id in team_ids
    ]

    return {
        "store": {
            "id": str(slot.get("id") or "store_current"),
            "name": str(slot.get("name") or "Tienda actual"),
            "admin_employee_id": admin_employee_id,
            "current_employee_id": current_employee_id,
            "is_current_admin": current_employee_id == admin_employee_id,
        },
        "members": members,
    }


async def _cx_store_team_target_023w(
    db: AsyncSession,
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str],
    employee_id: str,
) -> tuple[Company, CompanyUser, Dict[str, Any], Dict[str, Any], CompanyUser, Dict[str, Any]]:
    company, current_user, current_mini_panel = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    clean_type = _cx_panel_type_019d(panel_type)
    if clean_type != "store":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Control de turno disponible solo para mini panel tienda.")

    current_employee_id = str(current_mini_panel.get("employee_id") or "").strip()
    target_employee_id = str(employee_id or "").strip()
    slot, team_ids = _cx_store_team_ids_023w(company, current_employee_id)
    if target_employee_id not in team_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Colaborador fuera de la tienda asignada.")

    users_by_employee = await _cx_store_team_users_by_employee_023w(db, company_id, team_ids)
    target_user = users_by_employee.get(target_employee_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Este colaborador no tiene clave de mini panel tienda.")

    target_mini_panel = _cx_store_member_mini_panel_023w(target_user)
    return company, current_user, current_mini_panel, slot, target_user, target_mini_panel


async def _cx_mp_apply_operational_action_023w(
    db: AsyncSession,
    company: Company,
    user: CompanyUser,
    mini_panel: Dict[str, Any],
    panel_type: str,
    action: str,
    *,
    allow_missing: bool = False,
) -> Dict[str, Any] | None:
    clean_action = str(action or "").strip().lower()
    clean_type = _cx_panel_type_019d(panel_type)

    if clean_action == "start":
        row = await _cx_mp_get_or_create_session_019f(db, company.id, user, mini_panel, clean_type)
        await _cx_mp_sync_attendance_023j(db, company.id, user, mini_panel, row)
        await db.commit()
        return await _cx_mp_operational_response_023p(db, company, user, mini_panel, row)

    if clean_action not in {"pause", "resume", "finish"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Accion de turno invalida.")

    row = await _cx_mp_fetch_open_session_019f(db, company.id, user.id, clean_type)
    if not row:
        if allow_missing:
            return None
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay sesion operativa activa.")

    current_status = str(row.get("status") or "").lower()
    now = datetime.now(timezone.utc)

    if clean_action == "pause":
        if current_status == "break":
            return await _cx_mp_operational_response_023p(db, company, user, mini_panel, row)
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
        event_type = "break_start"
    elif clean_action == "resume":
        if current_status == "active":
            return await _cx_mp_operational_response_023p(db, company, user, mini_panel, row)
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
        event_type = "break_end"
    else:
        active_delta = _cx_mp_seconds_between_019f(row.get("active_started_at"), now) if current_status == "active" else 0
        break_delta = _cx_mp_seconds_between_019f(row.get("current_break_started_at"), now) if current_status == "break" else 0
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
        event_type = "check_out"

    await db.commit()
    updated = await _cx_mp_fetch_session_by_id_019f(db, str(row["id"]))
    await _cx_mp_sync_attendance_023j(db, company.id, user, mini_panel, updated, event_type=event_type, event_at=now)
    await db.commit()
    return await _cx_mp_operational_response_023p(db, company, user, mini_panel, updated)


async def _cx_store_finish_other_team_sessions_023w(
    db: AsyncSession,
    company: Company,
    slot: Dict[str, Any],
    exclude_user_id: UUID,
) -> None:
    team_ids = [str(item or "").strip() for item in (slot.get("employee_ids") or []) if str(item or "").strip()]
    users_by_employee = await _cx_store_team_users_by_employee_023w(db, company.id, team_ids)
    for user in users_by_employee.values():
        if str(user.id) == str(exclude_user_id):
            continue
        mini_panel = _cx_store_member_mini_panel_023w(user)
        await _cx_mp_apply_operational_action_023w(
            db,
            company,
            user,
            mini_panel,
            "store",
            "finish",
            allow_missing=True,
        )


async def _cx_store_finish_team_if_admin_023w(
    db: AsyncSession,
    company: Company,
    user: CompanyUser,
    mini_panel: Dict[str, Any],
) -> None:
    employee_id = str(mini_panel.get("employee_id") or "").strip()
    slot, team_ids = _cx_store_team_ids_023w(company, employee_id)
    if not team_ids or team_ids[0] != employee_id:
        return
    await _cx_store_finish_other_team_sessions_023w(db, company, slot, user.id)


@router.get("/{company_id}/mini-panel-store-team")
async def mini_panel_store_team_023w(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, user, mini_panel = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    if _cx_panel_type_019d(panel_type) != "store":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Equipo disponible solo para mini panel tienda.")
    payload = await _cx_store_team_payload_023w(db, company, user, mini_panel)
    return {
        "ok": True,
        "company_id": str(company_id),
        **payload,
    }


@router.post("/{company_id}/mini-panel-store-team/{employee_id}/login")
async def mini_panel_store_team_login_023w(
    company_id: UUID,
    employee_id: str,
    panel_type: str,
    payload: StoreTeamMemberLoginRequest023W,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, current_user, current_mini_panel, _, target_user, _ = await _cx_store_team_target_023w(
        db,
        company_id,
        panel_type,
        authorization,
        employee_id,
    )
    if not _cx_minipanel_user_matches_login_019d(target_user, payload.username, "store"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario de tienda invalido.")
    if not verify_password(str(payload.password or ""), target_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clave de tienda invalida.")
    team = await _cx_store_team_payload_023w(db, company, current_user, current_mini_panel)
    return {"ok": True, "authenticated": True, "team": team}


@router.post("/{company_id}/mini-panel-store-team/{employee_id}/session/{action}")
async def mini_panel_store_team_session_action_023w(
    company_id: UUID,
    employee_id: str,
    action: str,
    panel_type: str,
    cascade_team: bool = False,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, current_user, current_mini_panel, slot, target_user, target_mini_panel = await _cx_store_team_target_023w(
        db,
        company_id,
        panel_type,
        authorization,
        employee_id,
    )
    operational = await _cx_mp_apply_operational_action_023w(
        db,
        company,
        target_user,
        target_mini_panel,
        "store",
        action,
    )
    admin_employee_id = str((slot.get("employee_ids") or [""])[0] or "")
    if cascade_team and str(action or "").strip().lower() == "finish" and str(employee_id) == admin_employee_id:
        await _cx_store_finish_other_team_sessions_023w(db, company, slot, target_user.id)

    team = await _cx_store_team_payload_023w(db, company, current_user, current_mini_panel)
    return {
        "ok": True,
        "operational_session": operational,
        "team": team,
    }
# CLONEXA_023W_STORE_TEAM_MINI_PANEL_END


@router.get("/{company_id}/mini-panel-operational-session")
async def mini_panel_operational_session_019f(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, user, mini_panel = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    clean_type = _cx_panel_type_019d(panel_type)
    row = await _cx_mp_get_or_create_session_019f(db, company_id, user, mini_panel, clean_type)
    await _cx_mp_sync_attendance_023j(db, company_id, user, mini_panel, row)
    await db.commit()
    return {"ok": True, "operational_session": await _cx_mp_operational_response_023p(db, company, user, mini_panel, row)}


@router.post("/{company_id}/mini-panel-operational-session/pause")
async def mini_panel_operational_pause_019f(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, user, mini_panel = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    clean_type = _cx_panel_type_019d(panel_type)
    row = await _cx_mp_fetch_open_session_019f(db, company_id, user.id, clean_type)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay sesiÃ³n operativa activa.")
    if str(row.get("status") or "") == "break":
        return {"ok": True, "operational_session": await _cx_mp_operational_response_023p(db, company, user, mini_panel, row)}

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
    await _cx_mp_sync_attendance_023j(db, company_id, user, mini_panel, updated, event_type="break_start", event_at=now)
    await db.commit()
    return {"ok": True, "operational_session": await _cx_mp_operational_response_023p(db, company, user, mini_panel, updated)}


@router.post("/{company_id}/mini-panel-operational-session/resume")
async def mini_panel_operational_resume_019f(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, user, mini_panel = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    clean_type = _cx_panel_type_019d(panel_type)
    row = await _cx_mp_fetch_open_session_019f(db, company_id, user.id, clean_type)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay sesiÃ³n operativa activa.")
    if str(row.get("status") or "") == "active":
        return {"ok": True, "operational_session": await _cx_mp_operational_response_023p(db, company, user, mini_panel, row)}

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
    await _cx_mp_sync_attendance_023j(db, company_id, user, mini_panel, updated, event_type="break_end", event_at=now)
    await db.commit()
    return {"ok": True, "operational_session": await _cx_mp_operational_response_023p(db, company, user, mini_panel, updated)}


@router.post("/{company_id}/mini-panel-operational-session/finish")
async def mini_panel_operational_finish_019f(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, user, mini_panel = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
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
    await _cx_mp_sync_attendance_023j(db, company_id, user, mini_panel, updated, event_type="check_out", event_at=now)
    await db.commit()
    if clean_type == "store":
        await _cx_store_finish_team_if_admin_023w(db, company, user, mini_panel)
    return {"ok": True, "operational_session": await _cx_mp_operational_response_023p(db, company, user, mini_panel, updated)}


# CLONEXA_028N_TRANSPORT_SUPERVISOR_MONITOR_START

class TransportMonitorSettingsRequest028N(BaseModel):
    call_alert_minutes: int = 10
    break_alert_minutes: int = 15
    idle_alert_minutes: int = 30


TRANSPORT_AGENT_ROLE_TOKENS_028N = {
    "agente_call",
    "agentecall",
    "agente_call_center",
    "agentecallcenter",
    "asesor_call",
    "asesorcall",
    "asesor_call_center",
    "asesorcallcenter",
    "call_center",
    "callcenter",
    "llamadas",
    "telefono",
    "telefonico",
    "operador_call",
    "operadorcall",
    "agente_externo",
    "agenteexterno",
    "asesor_externo",
    "asesorexterno",
}

TRANSPORT_MONITOR_ROLE_TOKENS_028N = {
    "supervisor",
    "supervisora",
    "gerencia",
    "gerente",
    "manager",
    "admin",
    "admin_empresa",
    "adminempresa",
    "company_admin",
    "companyadmin",
    "tesoreria",
}

TRANSPORT_FORCE_LOGOUT_TOKENS_028N = {
    "supervisor",
    "supervisora",
    "gerencia",
    "gerente",
    "manager",
    "admin",
    "admin_empresa",
    "adminempresa",
    "company_admin",
    "companyadmin",
}


def _cx_norm_token_028n(value: Any) -> str:
    clean = str(value or "").strip().lower()
    clean = (
        clean.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    return re.sub(r"[^a-z0-9]+", "_", clean).strip("_")


def _cx_role_tokens_028n(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        normalized = _cx_norm_token_028n(value)
        if not normalized:
            continue
        tokens.add(normalized)
        tokens.add(normalized.replace("_", ""))
        for part in normalized.split("_"):
            if part:
                tokens.add(part)
    return tokens


def _cx_clamp_minutes_028n(value: Any, default: int, maximum: int = 240) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(1, min(maximum, parsed))


def _cx_transport_monitor_settings_028n(company: Company) -> Dict[str, Any]:
    store = dict(company.settings_json or {})
    transport = store.get("transport_calls") if isinstance(store.get("transport_calls"), dict) else {}
    monitor = transport.get("monitor") if isinstance(transport.get("monitor"), dict) else {}
    call_minutes = _cx_clamp_minutes_028n(monitor.get("call_alert_minutes"), 10)
    break_minutes = _cx_clamp_minutes_028n(monitor.get("break_alert_minutes"), 15)
    idle_minutes = _cx_clamp_minutes_028n(monitor.get("idle_alert_minutes"), 30)
    return {
        "call_alert_minutes": call_minutes,
        "break_alert_minutes": break_minutes,
        "idle_alert_minutes": idle_minutes,
        "call_alert_seconds": call_minutes * 60,
        "break_alert_seconds": break_minutes * 60,
        "idle_alert_seconds": idle_minutes * 60,
    }


def _cx_set_transport_monitor_settings_028n(
    company: Company,
    payload: TransportMonitorSettingsRequest028N,
) -> Dict[str, Any]:
    settings = _cx_transport_monitor_settings_028n(company)
    settings.update({
        "call_alert_minutes": _cx_clamp_minutes_028n(payload.call_alert_minutes, 10),
        "break_alert_minutes": _cx_clamp_minutes_028n(payload.break_alert_minutes, 15),
        "idle_alert_minutes": _cx_clamp_minutes_028n(payload.idle_alert_minutes, 30),
    })
    settings["call_alert_seconds"] = settings["call_alert_minutes"] * 60
    settings["break_alert_seconds"] = settings["break_alert_minutes"] * 60
    settings["idle_alert_seconds"] = settings["idle_alert_minutes"] * 60

    store = dict(company.settings_json or {})
    transport = dict(store.get("transport_calls") or {})
    transport["monitor"] = {
        "call_alert_minutes": settings["call_alert_minutes"],
        "break_alert_minutes": settings["break_alert_minutes"],
        "idle_alert_minutes": settings["idle_alert_minutes"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    store["transport_calls"] = transport
    company.settings_json = store
    if hasattr(company, "updated_at"):
        company.updated_at = datetime.now(timezone.utc)
    return settings


def _cx_transport_mode_028n(user: CompanyUser, mini_panel: Dict[str, Any], employee: Employee | None) -> Dict[str, Any]:
    tokens = _cx_role_tokens_028n(
        getattr(user, "role", ""),
        mini_panel.get("type"),
        getattr(employee, "role", "") if employee else "",
        getattr(employee, "employee_type", "") if employee else "",
    )
    if not (tokens & TRANSPORT_MONITOR_ROLE_TOKENS_028N):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mini panel sin permisos de supervisor.")
    is_supervisor = bool(tokens & {"supervisor", "supervisora"})
    is_management = bool(tokens & {"gerencia", "gerente", "manager", "admin", "admin_empresa", "adminempresa", "company_admin", "companyadmin", "tesoreria"})
    return {
        "view_mode": "supervisor" if is_supervisor else "management",
        "can_force_logout": bool(tokens & TRANSPORT_FORCE_LOGOUT_TOKENS_028N),
        "role_tokens": sorted(tokens),
        "is_management": is_management,
    }


async def _cx_transport_monitor_context_028n(
    db: AsyncSession,
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str],
) -> tuple[Company, CompanyUser, Dict[str, Any], Employee | None, Dict[str, Any]]:
    company, user, mini_panel = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)
    employee = await _cx_mp_employee_for_attendance_023j(db, company_id, mini_panel.get("employee_id"))
    mode = _cx_transport_mode_028n(user, mini_panel, employee)
    return company, user, mini_panel, employee, mode


async def _cx_transport_minipanel_users_028n(db: AsyncSession, company_id: UUID) -> Dict[str, tuple[CompanyUser, Dict[str, Any]]]:
    result = await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    users_by_employee: Dict[str, tuple[CompanyUser, Dict[str, Any]]] = {}
    for user in result.scalars().all():
        settings = _cx_user_settings_019c(user)
        mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
        if mini_panel.get("enabled") is not True:
            continue
        panel_type = _cx_panel_type_019d(mini_panel.get("type"))
        employee_id = str(mini_panel.get("employee_id") or "").strip()
        if panel_type not in {"call_center", "external"} or not employee_id:
            continue
        if employee_id not in users_by_employee:
            users_by_employee[employee_id] = (user, mini_panel)
    return users_by_employee


def _cx_employee_is_transport_agent_028n(employee: Employee, mini_panel: Dict[str, Any] | None = None) -> bool:
    panel_type = _cx_panel_type_019d((mini_panel or {}).get("type")) if mini_panel else ""
    tokens = _cx_role_tokens_028n(
        getattr(employee, "role", ""),
        getattr(employee, "employee_type", ""),
    )
    if tokens & TRANSPORT_MONITOR_ROLE_TOKENS_028N:
        return False
    if panel_type == "call_center":
        return True
    if tokens & TRANSPORT_AGENT_ROLE_TOKENS_028N:
        return True
    return False


async def _cx_transport_employees_028n(
    db: AsyncSession,
    company_id: UUID,
    users_by_employee: Dict[str, tuple[CompanyUser, Dict[str, Any]]],
) -> list[Employee]:
    result = await db.execute(
        select(Employee)
        .where(Employee.company_id == company_id)
        .order_by(Employee.full_name.asc())
    )
    employees = []
    for employee in result.scalars().all():
        status_value = str(getattr(employee, "status", "") or "active").strip().lower()
        if status_value in {"archived", "inactive", "inactivo"}:
            continue
        employee_id = str(employee.id)
        user_tuple = users_by_employee.get(employee_id)
        mini_panel = user_tuple[1] if user_tuple else {}
        if _cx_employee_is_transport_agent_028n(employee, mini_panel):
            employees.append(employee)
    return employees


async def _cx_transport_open_sessions_028n(
    db: AsyncSession,
    company_id: UUID,
    users_by_employee: Dict[str, tuple[CompanyUser, Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    await _cx_mp_work_ensure_019f(db)
    user_to_employee = {str(user.id): employee_id for employee_id, (user, _) in users_by_employee.items()}
    if not user_to_employee:
        return {}

    params: Dict[str, Any] = {"company_id": str(company_id)}
    placeholders: list[str] = []
    for index, user_id in enumerate(user_to_employee):
        key = f"user_{index}"
        params[key] = user_id
        placeholders.append(f"CAST(:{key} AS uuid)")

    result = await db.execute(
        text(f"""
            SELECT DISTINCT ON (user_id) *
            FROM mini_panel_work_sessions
            WHERE company_id = CAST(:company_id AS uuid)
              AND user_id IN ({', '.join(placeholders)})
              AND status IN ('active', 'break')
            ORDER BY user_id, started_at DESC
        """),
        params,
    )
    rows: Dict[str, Dict[str, Any]] = {}
    for row in result.mappings().all():
        employee_id = user_to_employee.get(str(row.get("user_id") or ""))
        if employee_id:
            rows[employee_id] = dict(row)
    return rows


async def _cx_transport_access_sessions_028n(
    db: AsyncSession,
    company_id: UUID,
    users_by_employee: Dict[str, tuple[CompanyUser, Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    await ensure_access_sessions_storage(db)
    user_to_employee = {str(user.id): employee_id for employee_id, (user, _) in users_by_employee.items()}
    if not user_to_employee:
        return {}
    params: Dict[str, Any] = {"company_id": str(company_id)}
    placeholders: list[str] = []
    for index, user_id in enumerate(user_to_employee):
        key = f"user_{index}"
        params[key] = user_id
        placeholders.append(f"CAST(:{key} AS uuid)")
    result = await db.execute(
        text(f"""
            SELECT DISTINCT ON (subject_id)
                subject_id::text AS user_id,
                session_key,
                status,
                last_seen_at,
                created_at,
                ip_address
            FROM clonexa_access_sessions
            WHERE company_id = CAST(:company_id AS uuid)
              AND scope = 'mini_panel'
              AND status = 'active'
              AND subject_id IN ({', '.join(placeholders)})
            ORDER BY subject_id, last_seen_at DESC, created_at DESC
        """),
        params,
    )
    rows: Dict[str, Dict[str, Any]] = {}
    for row in result.mappings().all():
        data = dict(row)
        employee_id = user_to_employee.get(str(data.get("user_id") or ""))
        if not employee_id:
            continue
        for key in ("last_seen_at", "created_at"):
            if data.get(key) and isinstance(data.get(key), datetime):
                data[key] = data[key].isoformat()
        rows[employee_id] = data
    return rows


async def _cx_transport_latest_calls_028n(db: AsyncSession, company_id: UUID) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    await ensure_transport_calls_storage(db)
    result = await db.execute(
        text("""
            SELECT *
            FROM transport_call_logs
            WHERE company_id = CAST(:company_id AS uuid)
              AND created_at >= now() - interval '24 hours'
            ORDER BY created_at DESC
            LIMIT 500
        """),
        {"company_id": str(company_id)},
    )
    latest: Dict[str, Dict[str, Any]] = {}
    summary = {
        "calls_today": 0,
        "duration_today": 0,
        "quotes_today": 0,
        "tickets_today": 0,
        "missed_today": 0,
    }
    now = datetime.now(timezone.utc)
    for row in result.mappings().all():
        data = dict(row)
        created_at = data.get("created_at")
        if isinstance(created_at, datetime):
            data["created_at"] = created_at.isoformat()
        updated_at = data.get("updated_at")
        if isinstance(updated_at, datetime):
            data["updated_at"] = updated_at.isoformat()
        if isinstance(created_at, datetime) and created_at.date() == now.date():
            summary["calls_today"] += 1
            summary["duration_today"] += int(data.get("duration_seconds") or 0)
            if data.get("quote_requested"):
                summary["quotes_today"] += 1
            if data.get("ticket_requested"):
                summary["tickets_today"] += 1
            if str(data.get("call_status") or "").lower() == "missed":
                summary["missed_today"] += 1
        advisor_key = _cx_norm_token_028n(data.get("advisor_name"))
        if advisor_key and advisor_key not in latest:
            latest[advisor_key] = data
    summary["avg_duration_today"] = int(summary["duration_today"] / summary["calls_today"]) if summary["calls_today"] else 0
    return latest, summary


def _cx_transport_agent_payload_028n(
    employee: Employee,
    user_tuple: tuple[CompanyUser, Dict[str, Any]] | None,
    session_row: Dict[str, Any] | None,
    access_row: Dict[str, Any] | None,
    latest_call: Dict[str, Any] | None,
    monitor_settings: Dict[str, Any],
    mode: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    user = user_tuple[0] if user_tuple else None
    mini_panel = user_tuple[1] if user_tuple else {}
    session_payload = _cx_mp_operational_payload_019f(session_row) if session_row else None
    session_status = session_payload.get("status") if session_payload else "offline"
    call_status = str((latest_call or {}).get("call_status") or "").lower()
    advisor_status = str((latest_call or {}).get("advisor_status") or "").lower()
    in_call = call_status == "pending" or advisor_status == "in_call"
    created_at = _cx_mp_dt_019f((latest_call or {}).get("created_at"))
    call_seconds = int((latest_call or {}).get("duration_seconds") or 0)
    if in_call and created_at:
        call_seconds = max(call_seconds, int((now - created_at).total_seconds()))

    live_status = "offline"
    if in_call:
        live_status = "in_call"
    elif session_status == "break":
        live_status = "break"
    elif session_status == "active":
        live_status = "available"

    active_seconds = int((session_payload or {}).get("active_seconds") or 0)
    break_seconds = int((session_payload or {}).get("break_seconds") or 0)
    alert_reasons: list[str] = []
    if in_call and call_seconds >= int(monitor_settings.get("call_alert_seconds") or 600):
        alert_reasons.append("llamada_larga")
    if session_status == "break" and break_seconds >= int(monitor_settings.get("break_alert_seconds") or 900):
        alert_reasons.append("pausa_larga")

    return {
        "employee_id": str(employee.id),
        "full_name": str(employee.full_name or "Agente"),
        "phone": str(employee.phone or ""),
        "role": str(employee.role or employee.employee_type or ""),
        "employee_status": str(employee.status or "active"),
        "user_id": str(user.id) if user else "",
        "username": str((mini_panel or {}).get("username") or getattr(user, "email", "") or ""),
        "panel_type": _cx_panel_type_019d((mini_panel or {}).get("type") or "call_center") if mini_panel else "",
        "has_login": bool(user),
        "session": session_payload,
        "access_session": access_row or None,
        "live_status": live_status,
        "call_status": call_status or "none",
        "current_call_seconds": call_seconds,
        "active_seconds": active_seconds,
        "break_seconds": break_seconds,
        "last_seen_at": (access_row or {}).get("last_seen_at") or (session_payload or {}).get("server_time"),
        "latest_call": latest_call or None,
        "alert": bool(alert_reasons),
        "alert_reasons": alert_reasons,
        "can_force_logout": bool(mode.get("can_force_logout") and user and (session_payload or access_row)),
    }


def _cx_transport_monitor_summary_028n(agents: list[Dict[str, Any]], call_summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **call_summary,
        "agents_total": len(agents),
        "agents_online": sum(1 for item in agents if item.get("live_status") != "offline"),
        "agents_available": sum(1 for item in agents if item.get("live_status") == "available"),
        "agents_in_call": sum(1 for item in agents if item.get("live_status") == "in_call"),
        "agents_paused": sum(1 for item in agents if item.get("live_status") == "break"),
        "agents_offline": sum(1 for item in agents if item.get("live_status") == "offline"),
        "alerts": sum(1 for item in agents if item.get("alert")),
    }


async def _cx_transport_monitor_payload_028n(
    db: AsyncSession,
    company: Company,
    mode: Dict[str, Any],
) -> Dict[str, Any]:
    users_by_employee = await _cx_transport_minipanel_users_028n(db, company.id)
    employees = await _cx_transport_employees_028n(db, company.id, users_by_employee)
    sessions = await _cx_transport_open_sessions_028n(db, company.id, users_by_employee)
    access_sessions = await _cx_transport_access_sessions_028n(db, company.id, users_by_employee)
    latest_calls, call_summary = await _cx_transport_latest_calls_028n(db, company.id)
    settings = _cx_transport_monitor_settings_028n(company)
    agents = [
        _cx_transport_agent_payload_028n(
            employee,
            users_by_employee.get(str(employee.id)),
            sessions.get(str(employee.id)),
            access_sessions.get(str(employee.id)),
            latest_calls.get(_cx_norm_token_028n(employee.full_name)),
            settings,
            mode,
        )
        for employee in employees
    ]
    agents.sort(key=lambda item: (
        0 if item.get("alert") else 1,
        {"in_call": 0, "break": 1, "available": 2, "offline": 3}.get(str(item.get("live_status")), 9),
        str(item.get("full_name") or "").lower(),
    ))
    return {
        "ok": True,
        "company_id": str(company.id),
        "view_mode": mode.get("view_mode") or "supervisor",
        "can_force_logout": bool(mode.get("can_force_logout")),
        "settings": settings,
        "summary": _cx_transport_monitor_summary_028n(agents, call_summary),
        "agents": agents,
    }


@router.get("/{company_id}/mini-panel-agent-monitor")
async def mini_panel_agent_monitor_028n(
    company_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, _, _, _, mode = await _cx_transport_monitor_context_028n(db, company_id, panel_type, authorization)
    return await _cx_transport_monitor_payload_028n(db, company, mode)


@router.put("/{company_id}/mini-panel-agent-monitor/settings")
async def update_mini_panel_agent_monitor_settings_028n(
    company_id: UUID,
    panel_type: str,
    payload: TransportMonitorSettingsRequest028N,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, _, _, _, mode = await _cx_transport_monitor_context_028n(db, company_id, panel_type, authorization)
    settings = _cx_set_transport_monitor_settings_028n(company, payload)
    await db.commit()
    return {
        "ok": True,
        "settings": settings,
        "monitor": await _cx_transport_monitor_payload_028n(db, company, mode),
    }


@router.post("/{company_id}/mini-panel-agent-monitor/{target_user_id}/force-logout")
async def force_logout_mini_panel_agent_028n(
    company_id: UUID,
    target_user_id: UUID,
    panel_type: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company, _, _, _, mode = await _cx_transport_monitor_context_028n(db, company_id, panel_type, authorization)
    if not mode.get("can_force_logout"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para cerrar agentes.")

    result = await db.execute(select(CompanyUser).where(CompanyUser.id == target_user_id, CompanyUser.company_id == company_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario mini panel no encontrado.")

    settings = _cx_user_settings_019c(target_user)
    target_mini_panel = settings.get("mini_panel") if isinstance(settings.get("mini_panel"), dict) else {}
    if target_mini_panel.get("enabled") is not True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin mini panel activo.")
    target_type = _cx_panel_type_019d(target_mini_panel.get("type"))
    if target_type not in {"call_center", "external"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario fuera de call center.")

    await _cx_mp_apply_operational_action_023w(
        db,
        company,
        target_user,
        target_mini_panel,
        target_type,
        "finish",
        allow_missing=True,
    )

    await ensure_access_sessions_storage(db)
    closed = await db.execute(
        text("""
            UPDATE clonexa_access_sessions
            SET status = 'closed',
                closed_at = COALESCE(closed_at, NOW()),
                closed_reason = 'closed_from_supervisor',
                last_seen_at = NOW()
            WHERE company_id = CAST(:company_id AS uuid)
              AND scope = 'mini_panel'
              AND subject_id = CAST(:user_id AS uuid)
              AND status = 'active'
        """),
        {"company_id": str(company_id), "user_id": str(target_user_id)},
    )
    await db.commit()
    return {
        "ok": True,
        "closed_sessions": int(getattr(closed, "rowcount", 0) or 0),
        "monitor": await _cx_transport_monitor_payload_028n(db, company, mode),
    }

# CLONEXA_028N_TRANSPORT_SUPERVISOR_MONITOR_END



# CLONEXA_019F_R1_CHANGE_PASSWORD_BACKEND_START
class MiniPanelChangePasswordRequest019FR1(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


@router.post("/{company_id}/mini-panel-change-password")
async def mini_panel_change_password_019f_r1(
    company_id: UUID,
    panel_type: str,
    payload: MiniPanelChangePasswordRequest019FR1,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    _, user, _ = await _cx_mp_auth_context_019f(db, company_id, panel_type, authorization)

    current_password = str(payload.current_password or "")
    new_password = str(payload.new_password or "")
    confirm_password = str(payload.confirm_password or "")

    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clave actual incorrecta.")

    if len(new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La nueva clave debe tener mÃ­nimo 8 caracteres.")

    if new_password != confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La confirmaciÃ³n no coincide.")

    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_password_reset_at = now
    user.updated_at = now

    await db.commit()

    return {"ok": True, "message": "ContraseÃ±a actualizada."}
# CLONEXA_019F_R1_CHANGE_PASSWORD_BACKEND_END

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
