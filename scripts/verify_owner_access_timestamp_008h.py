from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import inspect, select

from app.models.auth import CompanyUser
from app.models.core import Company
from app.services.auth_service import create_company_user, verify_password

PLAIN_PASSWORD = "Clonexa-QA-008h!"


def get_session_factory() -> Any:
    module = importlib.import_module("app.core.database")
    for name in ("AsyncSessionLocal", "async_session_maker", "async_session", "SessionLocal"):
        factory = getattr(module, name, None)
        if factory is not None:
            return factory
    raise RuntimeError("No se encontró session factory async en app.core.database")


def now_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def company_columns() -> set[str]:
    return {col.key for col in inspect(Company).mapper.column_attrs}


async def create_qa_company(db, slug: str) -> Company:
    fields = company_columns()
    now = datetime.now(timezone.utc)
    data: dict[str, Any] = {}

    if "id" in fields:
        data["id"] = uuid4()
    if "name" in fields:
        data["name"] = "QA OWNER 008H"
    if "legal_name" in fields and "name" not in fields:
        data["legal_name"] = "QA OWNER 008H"
    if "slug" in fields:
        data["slug"] = slug
    if "timezone" in fields:
        data["timezone"] = "America/Bogota"
    if "status" in fields:
        data["status"] = "active"
    if "plan" in fields:
        data["plan"] = "qa"
    if "subscription_plan" in fields:
        data["subscription_plan"] = "qa"
    if "settings_json" in fields:
        data["settings_json"] = {}
    if "created_at" in fields:
        data["created_at"] = now
    if "updated_at" in fields:
        data["updated_at"] = now

    company = Company(**data)
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def main() -> int:
    session_factory = get_session_factory()
    stamp = now_key()
    slug = f"qa-008h-{stamp}"
    email = f"qa_owner_008h_{stamp}@clonexa.local"

    async with session_factory() as db:
        company = await create_qa_company(db, slug)

        payload = {
            "name": "QA OWNER 008H",
            "full_name": "QA OWNER 008H",
            "email": email,
            "password": PLAIN_PASSWORD,
            "temporary_password": PLAIN_PASSWORD,
            "role": "company_admin",
            "status": "active",
            "must_change_password": True,
        }

        created = await create_company_user(db, company.id, payload)

        result = await db.execute(
            select(CompanyUser).where(
                CompanyUser.company_id == company.id,
                CompanyUser.email == email,
            )
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise RuntimeError("No se creó el Acceso Maestro.")

        if not user.password_hash:
            raise RuntimeError("password_hash quedó vacío.")

        if user.password_hash == PLAIN_PASSWORD:
            raise RuntimeError("password_hash quedó igual a la contraseña plana.")

        if not verify_password(PLAIN_PASSWORD, user.password_hash):
            raise RuntimeError("La contraseña temporal no valida contra el hash guardado.")

        if str(user.role) != "company_admin":
            raise RuntimeError(f"Rol inválido: {user.role}")

        if str(user.status) != "active":
            raise RuntimeError(f"Status inválido: {user.status}")

        if getattr(user, "created_at", None) is None:
            raise RuntimeError("created_at quedó NULL.")

        if getattr(user, "updated_at", None) is None:
            raise RuntimeError("updated_at quedó NULL.")

        if hasattr(user, "last_password_reset_at") and getattr(user, "last_password_reset_at", None) is None:
            raise RuntimeError("last_password_reset_at quedó NULL.")

        print("✅ OWNER ACCESS CREATED")
        print("✅ TIMESTAMPS OK")
        print("✅ PASSWORD HASH OK")
        print("✅ OWNER ACCESS TIMESTAMP 008H PASSED")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"❌ OWNER ACCESS TIMESTAMP 008H FAILED: {exc}")
        raise SystemExit(1)
