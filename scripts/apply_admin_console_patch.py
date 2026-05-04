from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"
WEB = ROOT / "app" / "web"

IMPORT_LINE = "from app.web.admin_routes import register_admin_console"
CALL_LINE = "register_admin_console(app)"


def ensure_files() -> None:
    required = [
        WEB / "admin_routes.py",
        WEB / "admin.html",
        WEB / "admin.css",
        WEB / "admin.js",
        WEB / "__init__.py",
        WEB / "assets",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Faltan archivos del Admin Console. Extrae el ZIP en la raíz del repo:\n"
            + "\n".join(f"- {p.relative_to(ROOT)}" for p in missing)
        )
    (WEB / "assets").mkdir(parents=True, exist_ok=True)


def patch_main() -> None:
    if not MAIN.exists():
        raise FileNotFoundError(f"No existe {MAIN}")

    text = MAIN.read_text(encoding="utf-8")
    if "FastAPI(" not in text:
        raise RuntimeError("No se detectó FastAPI en app/main.py.")

    original = text

    if IMPORT_LINE not in text:
        lines = text.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("from ") or stripped.startswith("import "):
                insert_at = i + 1
        lines.insert(insert_at, IMPORT_LINE)
        text = "\n".join(lines) + ("\n" if original.endswith("\n") else "")

    if CALL_LINE not in text:
        text = text.rstrip() + (
            "\n\n# CLONEXA Admin Console\n"
            "# Serves GET /admin and static assets under /admin-static.\n"
            f"{CALL_LINE}\n"
        )

    if text != original:
        backup = MAIN.with_suffix(".py.bak_admin_console")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        MAIN.write_text(text, encoding="utf-8")


def main() -> None:
    ensure_files()
    patch_main()
    print("CLONEXA Admin Console aplicado correctamente.")
    print("Ruta final: http://localhost:8000/admin")
    print("Backup creado si fue necesario: app/main.py.bak_admin_console")


if __name__ == "__main__":
    main()
