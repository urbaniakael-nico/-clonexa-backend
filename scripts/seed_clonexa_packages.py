from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


BASE_MODULES: list[dict[str, str]] = [
    {"code": "core", "name": "Core", "category": "core"},
    {"code": "workforce", "name": "Workforce", "category": "core"},
    {"code": "field", "name": "Field", "category": "field"},
    {"code": "gps", "name": "GPS", "category": "field"},
    {"code": "materials", "name": "Materials", "category": "inventory"},
    {"code": "inventory", "name": "Inventory", "category": "inventory"},
    {"code": "payroll", "name": "Payroll", "category": "finance"},
    {"code": "bots", "name": "Bots", "category": "input"},
    {"code": "crm", "name": "CRM", "category": "read_model"},
    {"code": "kpis", "name": "KPIs", "category": "read_model"},
    {"code": "reports", "name": "Reports", "category": "read_model"},
    {"code": "hospitality", "name": "Hospitality", "category": "hospitality"},
    {"code": "orders", "name": "Orders", "category": "hospitality"},
    {"code": "tables", "name": "Tables", "category": "hospitality"},
    {"code": "stock", "name": "Stock", "category": "inventory"},
    {"code": "loyalty", "name": "Loyalty", "category": "hospitality"},
    {"code": "qr", "name": "QR", "category": "input"},
    {"code": "day_closing", "name": "Day Closing", "category": "hospitality"},
    {"code": "retail", "name": "Retail", "category": "retail"},
    {"code": "stores", "name": "Stores", "category": "retail"},
    {"code": "sales", "name": "Sales", "category": "retail"},
    {"code": "requests", "name": "Requests", "category": "retail"},
    {"code": "commercial_closing", "name": "Commercial Closing", "category": "retail"},
    {"code": "production", "name": "Production", "category": "production"},
    {"code": "references", "name": "References", "category": "production"},
    {"code": "costs", "name": "Costs", "category": "production"},
]


BASE_PACKAGES: list[dict[str, Any]] = [
    {
        "code": "field_pro_usa",
        "name": "Clonexa Field Pro USA",
        "description": "Paquete para Voltage: campo, técnicos, GPS, materiales, inventario, payroll, bots, CRM, KPIs y reportes.",
        "modules": ["core", "workforce", "field", "gps", "materials", "inventory", "payroll", "bots", "crm", "kpis", "reports"],
    },
    {
        "code": "hospitality_pro",
        "name": "Clonexa Hospitality Pro",
        "description": "Paquete para Radio Despecho: pedidos, mesas, inventario, stock, fidelización, bots, QR, CRM, KPIs y cierre diario.",
        "modules": ["core", "hospitality", "orders", "tables", "inventory", "stock", "loyalty", "bots", "qr", "crm", "kpis", "day_closing"],
    },
    {
        "code": "retail_ops",
        "name": "Clonexa Retail Ops",
        "description": "Paquete para Mundo Case: workforce, tiendas, ventas, solicitudes, inventario, payroll, bots, CRM, KPIs y cierre comercial.",
        "modules": ["core", "workforce", "retail", "stores", "sales", "requests", "inventory", "payroll", "bots", "crm", "kpis", "commercial_closing"],
    },
    {
        "code": "production_pro",
        "name": "Clonexa Production Pro",
        "description": "Paquete para Velvet: workforce, producción, referencias, payroll, CRM, KPIs, inventario y costos.",
        "modules": ["core", "workforce", "production", "references", "payroll", "crm", "kpis", "inventory", "costs"],
    },
]


def get_database_url() -> str:
    value = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("POSTGRES_URL")
    if not value:
        raise RuntimeError("Falta DATABASE_URL, SQLALCHEMY_DATABASE_URI o POSTGRES_URL en variables de entorno.")
    if value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


async def assert_tables_exist(conn) -> None:
    result = await conn.execute(
        text(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'public'
              and table_name in (
                'modules',
                'packages',
                'package_modules',
                'company_modules',
                'company_package_assignments'
              )
            """
        )
    )
    found = {row[0] for row in result.fetchall()}
    required = {
        "modules",
        "packages",
        "package_modules",
        "company_modules",
        "company_package_assignments",
    }
    missing = sorted(required - found)
    if missing:
        raise RuntimeError(
            "Faltan tablas SaaS: "
            + ", ".join(missing)
            + ". Ejecuta primero: alembic upgrade head"
        )


async def upsert_module(conn, item: dict[str, str]) -> uuid.UUID:
    module_id = uuid.uuid4()
    result = await conn.execute(
        text(
            """
            insert into modules (id, code, name, description, category, is_active)
            values (:id, :code, :name, :description, :category, true)
            on conflict (code) do update
            set name = excluded.name,
                description = excluded.description,
                category = excluded.category,
                is_active = true,
                updated_at = now()
            returning id
            """
        ),
        {
            "id": module_id,
            "code": item["code"],
            "name": item["name"],
            "description": item.get("description"),
            "category": item.get("category"),
        },
    )
    return result.scalar_one()


async def upsert_package(conn, item: dict[str, Any]) -> uuid.UUID:
    package_id = uuid.uuid4()
    result = await conn.execute(
        text(
            """
            insert into packages (id, code, name, description, is_active)
            values (:id, :code, :name, :description, true)
            on conflict (code) do update
            set name = excluded.name,
                description = excluded.description,
                is_active = true,
                updated_at = now()
            returning id
            """
        ),
        {
            "id": package_id,
            "code": item["code"],
            "name": item["name"],
            "description": item.get("description"),
        },
    )
    return result.scalar_one()


async def upsert_package_module(conn, package_id: uuid.UUID, module_id: uuid.UUID) -> None:
    await conn.execute(
        text(
            """
            insert into package_modules (id, package_id, module_id, settings)
            values (:id, :package_id, :module_id, '{}'::jsonb)
            on conflict (package_id, module_id) do nothing
            """
        ),
        {
            "id": uuid.uuid4(),
            "package_id": package_id,
            "module_id": module_id,
        },
    )


async def main() -> None:
    engine = create_async_engine(get_database_url(), future=True, pool_pre_ping=True)

    async with engine.begin() as conn:
        await assert_tables_exist(conn)

        module_ids: dict[str, uuid.UUID] = {}
        for item in BASE_MODULES:
            module_ids[item["code"]] = await upsert_module(conn, item)

        for package in BASE_PACKAGES:
            package_id = await upsert_package(conn, package)
            for module_code in package["modules"]:
                module_id = module_ids[module_code]
                await upsert_package_module(conn, package_id, module_id)

    await engine.dispose()
    print("Seed SaaS CLONEXA completado: modules, packages y package_modules OK.")


if __name__ == "__main__":
    asyncio.run(main())
