from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


SAAS_ENDPOINT_IMPORT = "from app.api.v1.endpoints import company_modules, modules, packages"
SAAS_ROUTER_LINES = [
    'api_router.include_router(modules.router, prefix="/modules", tags=["modules"])',
    'api_router.include_router(packages.router, prefix="/packages", tags=["packages"])',
    'api_router.include_router(company_modules.router, prefix="/companies", tags=["company-modules"])',
]

SAAS_MODEL_IMPORT = """from app.models.saas import (
    Module,
    Package,
    PackageModule,
    CompanyModule,
    CompanyPackageAssignment,
)
"""


def patch_router() -> None:
    path = ROOT / "app" / "api" / "v1" / "router.py"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")

    content = path.read_text(encoding="utf-8")

    if "api_router = APIRouter" not in content and "api_router=APIRouter" not in content.replace(" ", ""):
        raise RuntimeError("No encontré api_router = APIRouter en app/api/v1/router.py")

    if SAAS_ENDPOINT_IMPORT not in content:
        lines = content.splitlines()
        insert_at = 0
        for idx, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_at = idx + 1
        lines.insert(insert_at, SAAS_ENDPOINT_IMPORT)
        content = "\n".join(lines) + "\n"

    for router_line in SAAS_ROUTER_LINES:
        if router_line not in content:
            content = content.rstrip() + "\n" + router_line + "\n"

    path.write_text(content, encoding="utf-8")
    print("OK router.py: SaaS routers registrados bajo /api/v1")


def patch_models_init() -> None:
    path = ROOT / "app" / "models" / "__init__.py"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    content = path.read_text(encoding="utf-8")
    if "CompanyPackageAssignment" not in content:
        content = content.rstrip() + "\n\n" + SAAS_MODEL_IMPORT
        path.write_text(content, encoding="utf-8")

    print("OK app/models/__init__.py: modelos SaaS exportados")


def verify_main() -> None:
    path = ROOT / "app" / "main.py"
    if not path.exists():
        print("WARN app/main.py no existe")
        return

    content = path.read_text(encoding="utf-8")
    has_router = "include_router(api_router" in content or ".include_router(api_router" in content
    has_prefix = "settings.API_V1_PREFIX" in content or '"/api/v1"' in content or "'/api/v1'" in content

    if has_router and has_prefix:
        print("OK main.py: api_router incluido con prefix /api/v1")
        return

    print(
        "WARN main.py: revisa que tenga algo equivalente a "
        'app.include_router(api_router, prefix=settings.API_V1_PREFIX or "/api/v1")'
    )


def main() -> None:
    patch_router()
    patch_models_init()
    verify_main()
    print("Fix SaaS aplicado. Ejecuta: alembic upgrade head")


if __name__ == "__main__":
    main()
