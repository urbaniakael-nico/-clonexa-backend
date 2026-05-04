import asyncio
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.core import Company
from app.models.auth import CompanyUser
from app.services.auth_service import hash_password


async def main():
    async with async_session_maker() as db:
        company_result = await db.execute(
            select(Company).where(Company.slug == "voltage")
        )
        company = company_result.scalar_one()

        user_result = await db.execute(
            select(CompanyUser).where(
                CompanyUser.company_id == company.id,
                CompanyUser.email == "admin@voltage.com",
            )
        )
        user = user_result.scalar_one()

        user.password_hash = hash_password("Clonexa2026!Voltage")
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.locked_until = None
        user.status = "active"

        await db.commit()

        print("OK - Voltage admin password restored")
        print("email: admin@voltage.com")
        print("password: Clonexa2026!Voltage")


if __name__ == "__main__":
    asyncio.run(main())
