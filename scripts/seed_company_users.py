from __future__ import annotations

import asyncio
import importlib
import os
from typing import Any

from sqlalchemy import select

from app.models.auth import CompanyUser
from app.models.core import Company
from app.services.auth_service import hash_password


SEED_USERS = [
    {
        "slug": "voltage",
        "email": "admin@voltage.com",
        "password": "Clonexa2026!Voltage",
        "full_name": "Voltage Admin",
        "role": "company_admin",
    },
    {
        "slug": "radio-despecho",
        "email": "admin@radiodespecho.com",
        "password": "Clonexa2026!Radio",
        "full_name": "Radio Despecho Admin",
        "role": "company_admin",
    },
    {
        "slug": "mundo-case",
        "email": "admin@mundocase.com",
        "password": "Clonexa2026!Mundo",
        "full_name": "Mundo Case Admin",
        "role": "company_admin",
    },
    {
        "slug": "velvet",
        "email": "admin@velvet.com",
        "password": "Clonexa2026!Velvet",
        "full_name": "Velvet Admin",
        "role": "company_admin",
    },
]


def get_session_factory() -> Any:
    module = importlib.import_module("app.core.database")
    for name in ("AsyncSessionLocal", "async_session_maker", "async_session", "SessionLocal"):
        factory = getattr(module, name, None)
        if factory is not None:
            return factory
    raise RuntimeError("No se encontró session factory async en app.core.database")


async def main() -> None:
    reset_passwords = str(os.getenv("RESET_PASSWORDS", "")).lower() in {"1", "true", "yes", "si"}
    SessionFactory = get_session_factory()

    created = 0
    existing = 0
    updated_passwords = 0

    async with SessionFactory() as db:
        for item in SEED_USERS:
            company_result = await db.execute(select(Company).where(Company.slug == item["slug"]))
            company = company_result.scalar_one_or_none()
            if not company:
                print(f"Empresa no encontrada: {item['slug']}")
                continue

            email = item["email"].strip().lower()
            user_result = await db.execute(select(CompanyUser).where(CompanyUser.email == email))
            user = user_result.scalar_one_or_none()

            if user:
                existing += 1
                user.company_id = company.id
                user.full_name = item["full_name"]
                user.role = item["role"]
                user.status = "active"
                user.failed_login_attempts = 0
                user.locked_until = None
                if reset_passwords:
                    user.password_hash = hash_password(item["password"])
                    user.must_change_password = False
                    updated_passwords += 1
                print(f"existente: {email}")
            else:
                created += 1
                user = CompanyUser(
                    company_id=company.id,
                    email=email,
                    password_hash=hash_password(item["password"]),
                    full_name=item["full_name"],
                    role=item["role"],
                    status="active",
                    must_change_password=False,
                    failed_login_attempts=0,
                    locked_until=None,
                    settings_json={},
                )
                db.add(user)
                print(f"creado: {email}")

        await db.commit()

    print("CLONEXA COMPANY USERS SEED")
    print(f"usuarios creados: {created}")
    print(f"usuarios existentes: {existing}")
    print(f"passwords actualizados: {updated_passwords}")


if __name__ == "__main__":
    asyncio.run(main())
