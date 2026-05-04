from pathlib import Path
import sys
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "app/web/admin_v2.html",
    "app/web/admin_v2.css",
    "app/web/admin_v2.js",
    "app/web/admin_v2_routes.py",
]

FORBIDDEN = [
    "app." + "db",
    "app.models." + "company",
]


def check_files() -> bool:
    ok = True
    print("CLONEXA ADMIN V2 FILE CHECK")
    for rel in REQUIRED_FILES:
        path = ROOT / rel
        exists = path.exists()
        print(f"- {rel}: {'OK' if exists else 'MISSING'}")
        ok = ok and exists
    return ok


def check_forbidden_strings() -> bool:
    ok = True
    print("\nFORBIDDEN IMPORT CHECK")
    for rel in REQUIRED_FILES + ["scripts/apply_admin_v2_route.py"]:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for forbidden in FORBIDDEN:
            if forbidden in text:
                print(f"- ERROR: {forbidden} aparece en {rel}")
                ok = False
    if ok:
        print("- OK: no hay imports prohibidos")
    return ok


def check_local_http() -> None:
    print("\nHTTP CHECK")
    urls = [
        "http://127.0.0.1:8000/health",
        "http://127.0.0.1:8000/admin-v2",
        "http://127.0.0.1:8000/api/v1/companies",
        "http://127.0.0.1:8000/api/v1/packages",
        "http://127.0.0.1:8000/api/v1/modules",
    ]

    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=4) as response:
                print(f"- {url}: HTTP {response.status}")
        except Exception as exc:
            print(f"- {url}: no disponible ahora ({exc})")


def main() -> None:
    ok = check_files()
    ok = check_forbidden_strings() and ok

    try:
        import app.web.admin_v2_routes  # noqa: F401
        print("\nIMPORT CHECK\n- app.web.admin_v2_routes: OK")
    except Exception as exc:
        print(f"\nIMPORT CHECK\n- app.web.admin_v2_routes: ERROR {exc}")
        ok = False

    check_local_http()

    print("\nRESULTADO:", "OK" if ok else "REVISAR")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
