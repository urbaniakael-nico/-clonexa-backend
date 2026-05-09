from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


MODULE_CATALOG_ES: dict[str, dict[str, Any]] = {
    "core": {
        "name": "Núcleo",
        "description": "Base operativa del tenant, empresa, permisos y servicios base.",
        "category": "core",
        "category_label": "Núcleo",
        "layer": "base",
        "module_type": "base",
        "badge": "COR",
        "is_transversal": False,
    },
    "core_settings": {
        "name": "Ajustes",
        "description": "Idioma, moneda, contraseña, preferencias y configuración general.",
        "category": "core",
        "category_label": "Núcleo",
        "layer": "base",
        "module_type": "base",
        "badge": "SET",
        "is_transversal": False,
    },
    "workforce": {
        "name": "Personal",
        "description": "Empleados, roles, estados, disponibilidad y bitácora operativa.",
        "category": "core",
        "category_label": "Núcleo operativo",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "WRK",
        "is_transversal": False,
    },
    "bots": {
        "name": "Bots",
        "description": "Canales de captura por Telegram, WhatsApp y automatizaciones.",
        "category": "input",
        "category_label": "Entrada de datos",
        "layer": "captura",
        "module_type": "input",
        "badge": "BOT",
        "is_transversal": False,
    },
    "references": {
        "name": "Referencias",
        "description": "Catálogo de referencias, productos, tallas o servicios medibles.",
        "category": "production",
        "category_label": "Producción",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "REF",
        "is_transversal": False,
    },
    "production": {
        "name": "Producción",
        "description": "Tiempos, referencias, productividad, cierres y costos productivos.",
        "category": "production",
        "category_label": "Producción",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "PRD",
        "is_transversal": False,
    },
    "costs": {
        "name": "Costos",
        "description": "Costeo por referencia, producción, servicio o pedido.",
        "category": "production",
        "category_label": "Producción",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "CST",
        "is_transversal": False,
    },
    "crm": {
        "name": "CRM Campo",
        "description": "Panel operativo adaptable en tiempo real según módulos activos.",
        "category": "general",
        "category_label": "General adaptable",
        "layer": "presentación",
        "module_type": "general_adapter",
        "badge": "CRM",
        "is_transversal": True,
    },
    "kpis": {
        "name": "KPIs",
        "description": "Indicadores ejecutivos dinámicos según módulos activos.",
        "category": "general",
        "category_label": "General adaptable",
        "layer": "inteligencia",
        "module_type": "general_adapter",
        "badge": "KPI",
        "is_transversal": True,
    },
    "reports": {
        "name": "Reportes",
        "description": "Históricos, auditoría, búsqueda y exportación. No modifica datos.",
        "category": "general",
        "category_label": "General adaptable",
        "layer": "inteligencia",
        "module_type": "general_adapter",
        "badge": "REP",
        "is_transversal": True,
    },
    "field": {
        "name": "Operación en campo",
        "description": "Equipos externos, rutas, evidencias, tareas y actividad en campo.",
        "category": "field",
        "category_label": "Campo",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "FLD",
        "is_transversal": False,
    },
    "gps": {
        "name": "GPS",
        "description": "Ubicación, rutas, perímetros y control de equipos en campo.",
        "category": "field",
        "category_label": "Campo",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "GPS",
        "is_transversal": False,
    },
    "materials": {
        "name": "Materiales",
        "description": "Solicitudes, aprobación, entrega, devolución y control de materiales.",
        "category": "inventory",
        "category_label": "Inventario y materiales",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "MAT",
        "is_transversal": False,
    },
    "inventory": {
        "name": "Inventario",
        "description": "Existencias, mínimos, máximos y disponibilidad operativa.",
        "category": "inventory",
        "category_label": "Inventario y materiales",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "INV",
        "is_transversal": False,
    },
    "stock": {
        "name": "Stock",
        "description": "Control de existencias, alertas, mínimos y stock cero.",
        "category": "inventory",
        "category_label": "Inventario y materiales",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "STK",
        "is_transversal": False,
    },
    "payroll": {
        "name": "Nómina",
        "description": "Cálculo de horas, cortes, extras, descuentos y pagos.",
        "category": "finance",
        "category_label": "Finanzas operativas",
        "layer": "inteligencia",
        "module_type": "operational",
        "badge": "PAY",
        "is_transversal": False,
    },
    "day_closing": {
        "name": "Cierre de día",
        "description": "Resumen operativo diario por jornada y módulos activos.",
        "category": "general",
        "category_label": "General adaptable",
        "layer": "inteligencia",
        "module_type": "general_adapter",
        "badge": "DAY",
        "is_transversal": True,
    },
    "commercial_closing": {
        "name": "Cierre comercial",
        "description": "Seguimiento de ventas, cierres y resultados comerciales.",
        "category": "retail",
        "category_label": "Comercial y retail",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "COM",
        "is_transversal": False,
    },
    "retail": {
        "name": "Retail",
        "description": "Tiendas, ventas, solicitudes e inventario comercial.",
        "category": "retail",
        "category_label": "Comercial y retail",
        "layer": "vertical",
        "module_type": "vertical",
        "badge": "RTL",
        "is_transversal": False,
    },
    "sales": {
        "name": "Ventas",
        "description": "Actividad comercial, ventas, conversión y resultados.",
        "category": "retail",
        "category_label": "Comercial y retail",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "SAL",
        "is_transversal": False,
    },
    "stores": {
        "name": "Tiendas",
        "description": "Sucursales, puntos de venta y operación retail.",
        "category": "retail",
        "category_label": "Comercial y retail",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "STR",
        "is_transversal": False,
    },
    "hospitality": {
        "name": "Hospitality",
        "description": "Bares, restaurantes, mesas, pedidos y atención comercial.",
        "category": "hospitality",
        "category_label": "Hospitality",
        "layer": "vertical",
        "module_type": "vertical",
        "badge": "HSP",
        "is_transversal": False,
    },
    "orders": {
        "name": "Pedidos",
        "description": "Creación, seguimiento y estados de pedidos.",
        "category": "hospitality",
        "category_label": "Hospitality",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "ORD",
        "is_transversal": False,
    },
    "tables": {
        "name": "Mesas",
        "description": "Mesas, cuentas, sesiones y operación por QR.",
        "category": "hospitality",
        "category_label": "Hospitality",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "TBL",
        "is_transversal": False,
    },
    "loyalty": {
        "name": "Fidelización",
        "description": "Clientes recurrentes, beneficios y seguimiento comercial.",
        "category": "retail",
        "category_label": "Comercial y retail",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "LOY",
        "is_transversal": False,
    },
    "qr": {
        "name": "QR",
        "description": "Accesos por QR para mesas, operaciones o formularios.",
        "category": "input",
        "category_label": "Entrada de datos",
        "layer": "captura",
        "module_type": "input",
        "badge": "QR",
        "is_transversal": False,
    },
    "requests": {
        "name": "Solicitudes",
        "description": "Solicitudes internas, aprobaciones y estados.",
        "category": "workflow",
        "category_label": "Flujo operativo",
        "layer": "operativo",
        "module_type": "operational",
        "badge": "REQ",
        "is_transversal": False,
    },
}


async def ensure_module_catalog_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        ALTER TABLE modules
        ADD COLUMN IF NOT EXISTS config_json jsonb NOT NULL DEFAULT '{}'::jsonb
    """))


@router.get("/catalog")
async def module_catalog() -> dict[str, Any]:
    return {
        "ok": True,
        "language": "es",
        "count": len(MODULE_CATALOG_ES),
        "items": MODULE_CATALOG_ES,
    }


@router.post("/sync")
async def sync_module_catalog(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_module_catalog_storage(db)

    updated = 0

    for code, meta in MODULE_CATALOG_ES.items():
        result = await db.execute(
            text("""
                UPDATE modules
                SET
                    name = :name,
                    description = :description,
                    category = :category,
                    config_json = COALESCE(config_json, '{}'::jsonb) || CAST(:config_json AS jsonb),
                    updated_at = now()
                WHERE code = :code
            """),
            {
                "code": code,
                "name": meta["name"],
                "description": meta["description"],
                "category": meta["category"],
                "config_json": __import__("json").dumps(meta, ensure_ascii=False),
            },
        )
        updated += int(result.rowcount or 0)

    await db.commit()

    return {
        "ok": True,
        "language": "es",
        "updated": updated,
        "catalog_count": len(MODULE_CATALOG_ES),
    }
