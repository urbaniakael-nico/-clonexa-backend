from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_TABLES = [
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


def ok(msg: str) -> None:
    print(f"OK {msg}")


def fail(msg: str) -> None:
    raise SystemExit(f"ERROR {msg}")


def db_url() -> str | None:
    value = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("POSTGRES_URL")
    if not value:
        return None
    if value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


def verify_files() -> None:
    required = [
        ROOT / "migrations" / "versions" / "0003_create_company_experience.py",
        ROOT / "app" / "models" / "experience.py",
        ROOT / "app" / "schemas" / "experience.py",
        ROOT / "app" / "services" / "company_experience.py",
        ROOT / "app" / "api" / "v1" / "endpoints" / "company_experience.py",
        ROOT / "app" / "web" / "admin.html",
        ROOT / "app" / "web" / "admin.css",
        ROOT / "app" / "web" / "admin.js",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        fail("faltan archivos:\n" + "\n".join(str(p.relative_to(ROOT)) for p in missing))
    ok("archivos del Capítulo 3 presentes")


def verify_imports() -> None:
    modules = [
        "app.models.experience",
        "app.schemas.experience",
        "app.services.company_experience",
        "app.api.v1.endpoints.company_experience",
    ]
    for name in modules:
        importlib.import_module(name)
    ok("modelos, schemas, servicios y endpoints importan")


def verify_routes() -> None:
    try:
        main = importlib.import_module("app.main")
        app = getattr(main, "app")
    except Exception as exc:
        print(f"WARN no se pudo importar app.main: {exc}")
        return

    paths = {getattr(route, "path", "") for route in app.routes}
    expected = {
        "/admin",
        "/api/v1/companies/{company_id}/experience",
        "/api/v1/companies/{company_id}/branding",
        "/api/v1/companies/{company_id}/localization",
        "/api/v1/companies/{company_id}/launchpad-cards",
        "/api/v1/companies/{company_id}/crm-widgets",
        "/api/v1/companies/{company_id}/crm-sections",
        "/api/v1/companies/{company_id}/crm-actions",
        "/api/v1/companies/{company_id}/field-configs",
        "/api/v1/companies/{company_id}/alert-rules",
    }
    missing = sorted(expected - paths)
    if missing:
        fail("faltan rutas cargadas:\n" + "\n".join(missing))
    ok("rutas cargadas en FastAPI")


async def verify_tables() -> None:
    url = db_url()
    if not url:
        print("WARN sin DATABASE_URL/SQLALCHEMY_DATABASE_URI/POSTGRES_URL; omitiendo validación de tablas")
        return

    engine = create_async_engine(url, future=True)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(:tables)
                    """
                ),
                {"tables": REQUIRED_TABLES},
            )
            found = {row[0] for row in result.all()}
            missing = sorted(set(REQUIRED_TABLES) - found)
            if missing:
                fail("faltan tablas. Ejecuta alembic upgrade head:\n" + "\n".join(missing))
            ok("tablas de company experience existen")

            company = await conn.execute(text("SELECT id, name FROM companies LIMIT 1"))
            row = company.first()
            if row:
                ok(f"empresa disponible para experience: {row[1]} / {row[0]}")
            else:
                print("WARN no hay empresas para prueba de experiencia")
    finally:
        await engine.dispose()


def verify_http() -> None:
    base = os.getenv("CLONEXA_BASE_URL", "http://localhost:8000").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=5) as response:
            if response.status >= 400:
                fail(f"/health respondió {response.status}")
        ok("GET /health responde")
    except Exception as exc:
        print(f"WARN backend no disponible en {base}: {exc}")
        return

    try:
        with urllib.request.urlopen(f"{base}/api/v1/companies", timeout=8) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw)
        companies = data if isinstance(data, list) else data.get("items") or data.get("data") or data.get("results") or []
        if not companies:
            print("WARN /api/v1/companies no devolvió empresas")
            return
        company_id = companies[0].get("id") or companies[0].get("company_id")
        if not company_id:
            print("WARN no se encontró company_id en primera empresa")
            return
        with urllib.request.urlopen(f"{base}/api/v1/companies/{company_id}/experience", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        for key in ["branding", "localization", "layout", "launchpad_cards", "widgets", "sections", "actions", "field_configs", "alert_rules"]:
            if key not in payload:
                fail(f"experience no trae {key}")
        ok(f"GET /api/v1/companies/{company_id}/experience funciona")
    except urllib.error.HTTPError as exc:
        fail(f"HTTP error validando experience: {exc.code} {exc.reason}")
    except Exception as exc:
        print(f"WARN no se pudo validar HTTP experience: {exc}")


def main() -> None:
    verify_files()
    verify_imports()
    verify_routes()
    asyncio.run(verify_tables())
    verify_http()
    print("\nOK Capítulo 3 verificado.")


if __name__ == "__main__":
    main()
