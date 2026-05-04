from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXPERIENCE_ENDPOINT_IMPORT = "from app.api.v1.endpoints import company_experience"
EXPERIENCE_ROUTER_LINE = 'api_router.include_router(company_experience.router, prefix="/companies", tags=["company_experience"])'

EXPERIENCE_MODEL_IMPORT = """from app.models.experience import (
    CompanyBranding,
    CompanyLocalization,
    CompanyCrmLayout,
    CompanyCrmLaunchpadCard,
    CompanyCrmWidget,
    CompanyCrmSection,
    CompanyCrmAction,
    CompanyCrmFieldConfig,
    CompanyAlertRule,
)
"""

ADMIN_IMPORT_LINE = "from app.web.admin_routes import register_admin_console"
ADMIN_CALL_LINE = "register_admin_console(app)"


def ensure_required_files() -> None:
    required = [
        ROOT / "migrations" / "versions" / "0003_create_company_experience.py",
        ROOT / "app" / "models" / "experience.py",
        ROOT / "app" / "schemas" / "experience.py",
        ROOT / "app" / "services" / "company_experience.py",
        ROOT / "app" / "api" / "v1" / "endpoints" / "company_experience.py",
        ROOT / "app" / "web" / "admin_routes.py",
        ROOT / "app" / "web" / "admin.html",
        ROOT / "app" / "web" / "admin.css",
        ROOT / "app" / "web" / "admin.js",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Faltan archivos del patch. Extrae el ZIP en la raíz del repo:\n"
            + "\n".join(f"- {p.relative_to(ROOT)}" for p in missing)
        )
    (ROOT / "app" / "web" / "assets").mkdir(parents=True, exist_ok=True)


def patch_router() -> None:
    path = ROOT / "app" / "api" / "v1" / "router.py"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")

    content = path.read_text(encoding="utf-8")
    if "api_router = APIRouter" not in content and "api_router=APIRouter" not in content.replace(" ", ""):
        raise RuntimeError("No encontré api_router = APIRouter en app/api/v1/router.py")

    if EXPERIENCE_ENDPOINT_IMPORT not in content:
        lines = content.splitlines()
        insert_at = 0
        for idx, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_at = idx + 1
        lines.insert(insert_at, EXPERIENCE_ENDPOINT_IMPORT)
        content = "\n".join(lines) + "\n"

    if "company_experience.router" not in content:
        content = content.rstrip() + "\n" + EXPERIENCE_ROUTER_LINE + "\n"

    path.write_text(content, encoding="utf-8")
    print("OK router.py: company_experience registrado bajo /api/v1/companies")


def patch_models_init() -> None:
    path = ROOT / "app" / "models" / "__init__.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")

    content = path.read_text(encoding="utf-8")
    required_names = [
        "CompanyBranding",
        "CompanyLocalization",
        "CompanyCrmLayout",
        "CompanyCrmLaunchpadCard",
        "CompanyCrmWidget",
        "CompanyCrmSection",
        "CompanyCrmAction",
        "CompanyCrmFieldConfig",
        "CompanyAlertRule",
    ]
    if not all(name in content for name in required_names):
        content = content.rstrip() + "\n\n" + EXPERIENCE_MODEL_IMPORT
        path.write_text(content, encoding="utf-8")

    print("OK app/models/__init__.py: modelos Experience exportados")


def patch_main_for_admin() -> None:
    path = ROOT / "app" / "main.py"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")

    content = path.read_text(encoding="utf-8")
    original = content

    if ADMIN_IMPORT_LINE not in content:
        lines = content.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_at = i + 1
        lines.insert(insert_at, ADMIN_IMPORT_LINE)
        content = "\n".join(lines) + ("\n" if original.endswith("\n") else "")

    if ADMIN_CALL_LINE not in content:
        content = content.rstrip() + (
            "\n\n# CLONEXA Admin Console\n"
            "# Serves GET /admin and static assets under /admin-static.\n"
            f"{ADMIN_CALL_LINE}\n"
        )

    if content != original:
        backup = path.with_suffix(".py.bak_company_experience")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print("OK app/main.py: /admin registrado")
    else:
        print("OK app/main.py: /admin ya estaba registrado")


def main() -> None:
    ensure_required_files()
    patch_router()
    patch_models_init()
    patch_main_for_admin()
    print("\nPatch Capítulo 3 aplicado. Ejecuta: alembic upgrade head")


if __name__ == "__main__":
    main()
