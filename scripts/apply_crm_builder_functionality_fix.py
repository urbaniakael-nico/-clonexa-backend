from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def patch_router():
    path = ROOT / "app" / "api" / "v1" / "router.py"
    text = path.read_text(encoding="utf-8")
    if "company_experience" not in text:
        lines = text.splitlines()
        idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from app.api.v1"):
                idx = i + 1
        lines.insert(idx, "from app.api.v1.endpoints import company_experience")
        text = "\n".join(lines) + "\n"
    include = 'api_router.include_router(company_experience.router, prefix="/companies", tags=["company_experience"])'
    if include not in text:
        text = text.rstrip() + "\n" + include + "\n"
    path.write_text(text, encoding="utf-8")
    print("[OK] app/api/v1/router.py")

def patch_models_init():
    path = ROOT / "app" / "models" / "__init__.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    block = """
from app.models.experience import (
    CompanyAlertRule,
    CompanyBranding,
    CompanyCrmAction,
    CompanyCrmFieldConfig,
    CompanyCrmLaunchpadCard,
    CompanyCrmLayout,
    CompanyCrmSection,
    CompanyCrmWidget,
    CompanyLocalization,
)
"""
    if "CompanyCrmLaunchpadCard" not in text:
        text = text.rstrip() + "\n\n" + block.strip() + "\n"
        path.write_text(text, encoding="utf-8")
    print("[OK] app/models/__init__.py")

def patch_admin_html():
    path = ROOT / "app" / "web" / "admin.html"
    if not path.exists():
        print("[WARN] app/web/admin.html no existe; no se inyectó UI incremental")
        return
    text = path.read_text(encoding="utf-8")
    css = '<link rel="stylesheet" href="/web/admin_experience.css">'
    js = '<script src="/web/admin_experience.js"></script>'
    if css not in text:
        text = text.replace("</head>", f"  {css}\n</head>") if "</head>" in text else css + "\n" + text
    if js not in text:
        text = text.replace("</body>", f"  {js}\n</body>") if "</body>" in text else text + "\n" + js + "\n"
    path.write_text(text, encoding="utf-8")
    print("[OK] app/web/admin.html")

def main():
    patch_router()
    patch_models_init()
    patch_admin_html()
    print("[DONE] Patch aplicado. Ejecuta alembic upgrade head")

if __name__ == "__main__":
    main()
