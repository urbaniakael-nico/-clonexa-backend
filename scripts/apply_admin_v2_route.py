from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "app" / "main.py"

MARKER = "# CLONEXA_ADMIN_V2_ROUTE"

SNIPPET = f"""

{MARKER}
try:
    from app.web.admin_v2_routes import router as admin_v2_router
    app.include_router(admin_v2_router)
except Exception as exc:
    import logging
    logging.getLogger("clonexa.admin_v2").warning("Admin Console V2 no pudo registrarse: %s", exc)
# END_CLONEXA_ADMIN_V2_ROUTE
"""


def main() -> None:
    if not MAIN_PATH.exists():
        raise SystemExit(f"No existe {MAIN_PATH}")

    text = MAIN_PATH.read_text(encoding="utf-8")

    if MARKER in text:
        print("ADMIN V2 ya estaba registrado en app/main.py")
        return

    MAIN_PATH.write_text(text.rstrip() + SNIPPET, encoding="utf-8")
    print("ADMIN V2 registrado en app/main.py")


if __name__ == "__main__":
    main()
