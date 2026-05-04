import asyncio
import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.core import Company, Employee


async def main() -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(Company).where(Company.slug == "demo"))
        if existing:
            company = existing
        else:
            company = Company(
                name="Clonexa Demo",
                slug="demo",
                timezone="America/Bogota",
                status="active",
                plan="starter",
                settings_json={"modules": ["core", "field", "production", "retail", "hospitality"]},
            )
            db.add(company)
            await db.flush()

        employee = await db.scalar(
            select(Employee).where(Employee.company_id == company.id, Employee.full_name == "Demo Operator")
        )
        if not employee:
            employee = Employee(
                company_id=company.id,
                full_name="Demo Operator",
                document_id="DEMO-001",
                phone="+570000000000",
                email="demo@clonexa.local",
                status="active",
                employee_type="operator",
            )
            db.add(employee)

        await db.commit()
        print("BOOTSTRAP_OK")
        print(f"COMPANY_ID={company.id}")
        print(f"EMPLOYEE_ID={employee.id}")


if __name__ == "__main__":
    asyncio.run(main())

