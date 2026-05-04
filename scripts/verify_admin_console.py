from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"

REQUIRED = [
    ROOT / "app" / "web" / "admin_routes.py",
    ROOT / "app" / "web" / "admin.html",
    ROOT / "app" / "web" / "admin.css",
    ROOT / "app" / "web" / "admin.js",
]


def main() -> None:
    missing = [str(p.relative_to(ROOT)) for p in REQUIRED if not p.exists()]
    if missing:
        raise SystemExit("Faltan archivos:\n" + "\n".join(missing))

    text = MAIN.read_text(encoding="utf-8")
    checks = {
        "import register_admin_console": "from app.web.admin_routes import register_admin_console" in text,
        "call register_admin_console(app)": "register_admin_console(app)" in text,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("Fallaron validaciones:\n" + "\n".join(f"- {x}" for x in failed))

    print("OK: Admin Console instalado.")
    print("Abre: http://localhost:8000/admin")


if __name__ == "__main__":
    main()
