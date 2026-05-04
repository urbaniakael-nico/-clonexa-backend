from __future__ import annotations

import asyncio
import importlib
import sys
from typing import Any

from sqlalchemy import select

from app.models.auth import CompanyUser
from app.models.core import Company
from app.services.auth_service import (
    authenticate_user,
    change_password,
    hash_password,
    reset_company_user_password,
    unlock_company_user,
    verify_password,
)


COMPANY_SLUG = "voltage"
USER_EMAIL = "admin@voltage.com"
TEMP_PASSWORD = "ClonexaTemp007!"
FINAL_PASSWORD = "ClonexaFinal007!"
DEV_PASSWORD = "Clonexa2026!Voltage"


def get_session_factory() -> Any:
    module = importlib.import_module("app.core.database")
    candidates = (
        "AsyncSessionLocal",
        "async_session_maker",
        "async_session",
        "SessionLocal",
    )
    for name in candidates:
        factory = getattr(module, name, None)
        if factory is not None:
            return factory
    raise RuntimeError("No se encontró session factory async en app.core.database")


async def get_company(db):
    result = await db.execute(select(Company).where(Company.slug == COMPANY_SLUG))
    company = result.scalar_one_or_none()
    if not company:
        raise RuntimeError(f"No existe empresa con slug {COMPANY_SLUG}")
    return company


async def get_user(db, company_id):
    result = await db.execute(
        select(CompanyUser).where(
            CompanyUser.company_id == company_id,
            CompanyUser.email == USER_EMAIL,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise RuntimeError(f"No existe usuario {USER_EMAIL}")
    return user


async def expect_auth_success(db, email: str, password: str):
    return await authenticate_user(db, email, password)


async def expect_auth_failure(db, email: str, password: str) -> bool:
    try:
        await authenticate_user(db, email, password)
    except Exception:
        return True
    return False


async def main() -> int:
    SessionFactory = get_session_factory()

    async with SessionFactory() as db:
        company = await get_company(db)
        user = await get_user(db, company.id)

        print("CLONEXA AUTH PASSWORD FLOW CHECK")
        print(f"company slug: {company.slug}")
        print(f"user: {user.email}")

        reset_result = await reset_company_user_password(db, company.id, user.id, TEMP_PASSWORD)
        temporary_password = reset_result.get("temporary_password")

        if not temporary_password or temporary_password.startswith("$2"):
            raise RuntimeError("Reset devolvió un valor inválido como temporary_password.")

        user = await get_user(db, company.id)
        if not verify_password(TEMP_PASSWORD, user.password_hash):
            raise RuntimeError("verify_password(temp_password, password_hash) falló después del reset.")
        print("reset password: OK")

        user = await expect_auth_success(db, USER_EMAIL, TEMP_PASSWORD)
        if not user.must_change_password:
            raise RuntimeError("must_change_password debe quedar true después del reset.")
        print("temporary login: OK")

        await change_password(db, user, TEMP_PASSWORD, FINAL_PASSWORD)
        print("change password: OK")

        old_rejected = await expect_auth_failure(db, USER_EMAIL, TEMP_PASSWORD)
        if not old_rejected:
            raise RuntimeError("La contraseña temporal anterior todavía permite login.")
        print("old password rejected: OK")

        user = await expect_auth_success(db, USER_EMAIL, FINAL_PASSWORD)
        if user.must_change_password:
            raise RuntimeError("must_change_password debe quedar false después de change-password.")
        print("new password accepted: OK")

        user.password_hash = hash_password(DEV_PASSWORD)
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.locked_until = None
        user.status = "active"
        await db.commit()
        await db.refresh(user)

        restored = await expect_auth_success(db, USER_EMAIL, DEV_PASSWORD)
        if restored.must_change_password:
            raise RuntimeError("La contraseña de desarrollo fue restaurada, pero must_change_password quedó true.")

        await unlock_company_user(db, company.id, restored.id)
        print("restore dev password: OK")
        print("status: OK")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"status: ERROR - {exc}")
        raise SystemExit(1)
