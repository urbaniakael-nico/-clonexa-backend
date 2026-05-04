import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.core import database as database_module
from app.models.core import Company
from app.models.field import FieldBillingProject, FieldMaterial, FieldMaterialMovement, FieldTechnician
from app.services import field_engine


def get_session_factory():
    for name in ("AsyncSessionLocal", "async_session_maker", "SessionLocal", "async_session"):
        factory = getattr(database_module, name, None)
        if factory is not None:
            return factory
    raise RuntimeError("No se encontró session factory en app.core.database")


async def get_or_create_billing(db, company_id, code, name):
    result = await db.execute(select(FieldBillingProject).where(FieldBillingProject.company_id == company_id, FieldBillingProject.code == code))
    existing = result.scalar_one_or_none()
    if existing:
        print(f"billing existente: {code}")
        return existing
    obj = FieldBillingProject(company_id=company_id, code=code, name=name, client_name="Voltage Client", status="active")
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    print(f"billing creado: {code}")
    return obj


async def get_or_create_technician(db, company_id, full_name, role, is_supervisor, billing_id):
    result = await db.execute(select(FieldTechnician).where(FieldTechnician.company_id == company_id, FieldTechnician.full_name == full_name))
    existing = result.scalar_one_or_none()
    if existing:
        print(f"técnico existente: {full_name}")
        return existing
    obj = FieldTechnician(
        company_id=company_id,
        full_name=full_name,
        role=role,
        status="active",
        is_supervisor=is_supervisor,
        hourly_rate_regular=Decimal("18"),
        hourly_rate_extra=Decimal("27"),
        discount_1=Decimal("8"),
        discount_2=Decimal("0"),
        default_billing_project_id=billing_id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    print(f"técnico creado: {full_name}")
    return obj


async def get_or_create_material(db, company_id, sku, name, unit, stock_available, stock_min, unit_cost):
    result = await db.execute(select(FieldMaterial).where(FieldMaterial.company_id == company_id, FieldMaterial.name == name))
    existing = result.scalar_one_or_none()
    if existing:
        print(f"material existente: {name}")
        return existing
    obj = FieldMaterial(
        company_id=company_id,
        sku=sku,
        name=name,
        unit=unit,
        status="active",
        stock_available=Decimal(str(stock_available)),
        stock_min=Decimal(str(stock_min)),
        unit_cost=Decimal(str(unit_cost)),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    print(f"material creado: {name}")
    return obj


async def has_demo_movements(db, company_id):
    result = await db.execute(select(FieldMaterialMovement).where(FieldMaterialMovement.company_id == company_id, FieldMaterialMovement.notes == "seed_voltage_field_demo"))
    return result.scalars().first() is not None


async def main():
    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await db.execute(select(Company).where(Company.slug == "voltage"))
        company = result.scalar_one_or_none()
        if not company:
            raise RuntimeError("No existe empresa con slug voltage")

        billing_3 = await get_or_create_billing(db, company.id, "BILLING-3", "Billing 3")
        billing_5 = await get_or_create_billing(db, company.id, "BILLING-5", "Billing 5")

        nicolas = await get_or_create_technician(db, company.id, "Nicolas Gomez", "Lider", True, billing_5.id)
        await get_or_create_technician(db, company.id, "Angela Bonilla", "Tecnico", False, billing_3.id)
        await get_or_create_technician(db, company.id, "Sergio Gomez", "Tecnico", False, billing_3.id)

        tarjeta = await get_or_create_material(db, company.id, "RACK-CARD", "Tarjeta rack", "unit", 50, 10, 12)
        await get_or_create_material(db, company.id, "CONNECTOR", "Conector", "unit", 200, 40, 2.5)
        await get_or_create_material(db, company.id, "CABLE", "Cable", "ft", 1000, 150, 0.5)
        await get_or_create_material(db, company.id, "ROUTER", "Router", "unit", 20, 5, 80)

        if await has_demo_movements(db, company.id):
            print("movimientos demo existentes")
            return

        await field_engine.issue_material(db, company.id, {"technician_id": nicolas.id, "material_id": tarjeta.id, "billing_project_id": billing_5.id, "quantity": Decimal("2"), "notes": "seed_voltage_field_demo"})
        await field_engine.use_material(db, company.id, {"technician_id": nicolas.id, "material_id": tarjeta.id, "billing_project_id": billing_5.id, "quantity": Decimal("1"), "notes": "seed_voltage_field_demo"})
        await field_engine.return_material(db, company.id, {"technician_id": nicolas.id, "material_id": tarjeta.id, "billing_project_id": billing_5.id, "quantity": Decimal("1"), "condition": "good", "notes": "seed_voltage_field_demo"})
        print("movimientos demo creados")


if __name__ == "__main__":
    asyncio.run(main())
