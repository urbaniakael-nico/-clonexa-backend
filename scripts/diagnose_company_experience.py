import asyncio
import json
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

try:
    from app.core import database as database_module
except Exception as exc:
    print(f"[ERROR] No se pudo importar app.core.database: {exc}")
    raise

EXPECTED_TABLES = [
    "company_branding",
    "company_localization",
    "company_crm_layout",
    "company_crm_launchpad_cards",
    "company_crm_widgets",
    "company_crm_sections",
    "company_crm_actions",
    "company_crm_field_configs",
    "company_alert_rules",
]

BRANDING_COLUMNS = [
    "visual_preset",
    "button_color",
    "status_color",
    "logo_palette_json",
    "custom_css_json",
]

COUNT_TABLES = [
    ("branding", "company_branding"),
    ("localization", "company_localization"),
    ("layout", "company_crm_layout"),
    ("launchpad_cards", "company_crm_launchpad_cards"),
    ("widgets", "company_crm_widgets"),
    ("sections", "company_crm_sections"),
    ("actions", "company_crm_actions"),
    ("field_configs", "company_crm_field_configs"),
    ("alert_rules", "company_alert_rules"),
]


def _database_url() -> str:
    for attr in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "POSTGRES_DSN"):
        value = getattr(database_module, attr, None)
        if value:
            return str(value)
    try:
        from app.core.config import settings
        for attr in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "POSTGRES_DSN"):
            value = getattr(settings, attr, None)
            if value:
                return str(value)
    except Exception:
        pass
    raise RuntimeError("No se encontró DATABASE_URL en app.core.database ni app.core.config.settings")


def _sessionmaker():
    for attr in ("async_session_maker", "AsyncSessionLocal", "SessionLocal", "async_session"):
        factory = getattr(database_module, attr, None)
        if factory is not None:
            return factory
    engine = getattr(database_module, "engine", None) or getattr(database_module, "async_engine", None)
    if engine is None:
        engine = create_async_engine(_database_url(), future=True)
    return async_sessionmaker(engine, expire_on_commit=False)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "hex") and value.__class__.__name__ == "UUID":
        return str(value)
    return value


async def scalar(session, sql: str, params: dict | None = None):
    result = await session.execute(text(sql), params or {})
    return result.scalar()


async def rows(session, sql: str, params: dict | None = None):
    result = await session.execute(text(sql), params or {})
    return [dict(r) for r in result.mappings().all()]


async def main():
    Session = _sessionmaker()
    async with Session() as session:
        print("\nCLONEXA CRM BUILDER DIAGNOSE 002-D")
        print("=" * 72)

        try:
            version = await scalar(session, "SELECT version_num FROM alembic_version LIMIT 1")
        except Exception as exc:
            version = f"NO DISPONIBLE ({exc})"
        print(f"\n[ALEMBIC CURRENT] {version}")

        companies = await rows(
            session,
            """
            SELECT id::text AS id, name, slug
            FROM companies
            ORDER BY name
            """
        )
        print("\n[EMPRESAS]")
        if not companies:
            print("  - No hay empresas")
        for company in companies:
            print(f"  - {company['id']} | {company.get('name')} | {company.get('slug')}")

        print("\n[TABLAS EXPERIENCE]")
        table_status = {}
        for table in EXPECTED_TABLES:
            exists = await scalar(session, "SELECT to_regclass(:table_name)", {"table_name": f"public.{table}"})
            table_status[table] = bool(exists)
            print(f"  - {table}: {'OK' if exists else 'FALTA'}")

        print("\n[COLUMNAS company_branding]")
        for column in BRANDING_COLUMNS:
            exists = await scalar(
                session,
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'company_branding'
                  AND column_name = :column_name
                """,
                {"column_name": column},
            )
            print(f"  - {column}: {'OK' if exists else 'FALTA'}")

        print("\n[CONTEOS POR EMPRESA]")
        for company in companies:
            print(f"\n  {company.get('name')} ({company.get('slug')})")
            for label, table in COUNT_TABLES:
                if not table_status.get(table):
                    count = "TABLA_FALTANTE"
                else:
                    count = await scalar(
                        session,
                        f"SELECT COUNT(*) FROM {table} WHERE company_id = CAST(:company_id AS uuid)",
                        {"company_id": company["id"]},
                    )
                print(f"    - {label}: {count}")

        voltage = next((c for c in companies if (c.get("slug") or "").lower() == "voltage" or (c.get("name") or "").lower() == "voltage"), None)
        if voltage:
            print("\n[SAMPLE JSON VOLTAGE]")
            samples = {
                "launchpad_cards": ("company_crm_launchpad_cards", "position, card_code"),
                "widgets": ("company_crm_widgets", "position, widget_code"),
                "sections": ("company_crm_sections", "position, section_code"),
                "actions": ("company_crm_actions", "position, action_code"),
                "field_configs": ("company_crm_field_configs", "position, field_code"),
                "alert_rules": ("company_alert_rules", "rule_code"),
            }
            sample_payload = {}
            for label, (table, order_by) in samples.items():
                if not table_status.get(table):
                    sample_payload[label] = []
                    continue
                sample_payload[label] = await rows(
                    session,
                    f"""
                    SELECT *
                    FROM {table}
                    WHERE company_id = CAST(:company_id AS uuid)
                    ORDER BY {order_by}
                    LIMIT 3
                    """,
                    {"company_id": voltage["id"]},
                )
            print(json.dumps(sample_payload, ensure_ascii=False, indent=2, default=_jsonable))
        else:
            print("\n[SAMPLE JSON VOLTAGE] No se encontró empresa Voltage")

        print("\n[FIN DIAGNÓSTICO]")


if __name__ == "__main__":
    asyncio.run(main())
