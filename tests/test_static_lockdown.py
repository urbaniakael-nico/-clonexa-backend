"""Rutas estaticas cerradas (2026-10-14) y cierre de sesion de la consola.

/admin-static y /client-static montaban app/web completa: el codigo Python se
podia descargar sin sesion. Ahora toda ruta que sirve archivos usa la lista
blanca de app/web/safe_static.py y el middleware global de app/main.py.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock

import bcrypt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.routing import Mount

import app.main as app_main
from app.api.deps import get_db
from app.web import admin_v2_routes as routes
from app.web import safe_static

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "app" / "web"
client = TestClient(app_main.app)

STATIC_ROUTES = ("/client-static", "/assets", "/admin-v2-assets", "/admin-static")

# Lo que nunca debe salir, en cada ruta estatica (exista o no el archivo).
FORBIDDEN = (
    "admin_v2_routes.py", "client_routes.py", "__init__.py", "safe_static.py",
    "__pycache__/admin_v2_routes.cpython-311.pyc", "x.pyc",
    ".env", "x.env", ".git/config", ".gitkeep",
    "README.md", "notas.txt", "datos.sql", "config.ini", "pyproject.toml", "railway.yml", "poetry.lock",
    "brand_registry.json", "garment_catalog.json", "switch_registry.json", "package.json", "settings.json",
    "../main.py", "..%2fmain.py", "%2e%2e/main.py", "..%252fmain.py", "brand/../../main.py",
    "login.css.backup_20260429_110623",
    "admin_v2plus.html", "client.html",  # paginas: solo por sus rutas con sesion/marca
)


def _referenced(prefix: str) -> set[str]:
    """Archivos que hoy piden el portal, los mini paneles, la consola, el login y Juegos en vivo."""
    found: set[str] = set()
    pattern = re.compile(re.escape(prefix) + r"/([A-Za-z0-9_./-]+?\.(?:css|js|png|jpg|jpeg|svg|ico|webp|woff2|json))")
    for path in list(WEB.glob("*.html")) + list(WEB.glob("*.js")) + list(WEB.glob("*.py")) + list(WEB.glob("*.css")):
        for match in pattern.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            found.add(match.group(1))
    return found


def test_every_folder_mount_is_the_safe_whitelist():
    mounts = [r for r in app_main.app.routes if isinstance(r, Mount)]
    paths = {m.path for m in mounts}
    assert "/admin-static" not in paths, "la pagina /admin vieja y su montaje se retiraron"
    assert {"/client-static", "/assets"} <= paths
    for mount in mounts:
        if hasattr(mount.app, "directory") or mount.path in STATIC_ROUTES:
            assert isinstance(mount.app, safe_static.SafeStaticFiles), f"{mount.path} sirve una carpeta sin lista blanca"


@pytest.mark.parametrize("prefix", STATIC_ROUTES)
@pytest.mark.parametrize("name", FORBIDDEN)
def test_code_config_and_dotdot_are_404_on_every_static_route(prefix, name):
    r = client.get(f"{prefix}/{name}")
    assert r.status_code == 404, f"{prefix}/{name} -> {r.status_code}"
    assert "def " not in r.text and "import " not in r.text


def test_legit_portal_panel_console_login_and_games_assets_are_200():
    client_files = _referenced("/client-static")
    # El portal, los mini paneles, el login, Juegos en vivo y la Facturacion del panel.
    for must in ("client.js", "client.css", "login.js", "login.css", "mini_panel.js", "mini_panel.css", "hsp_waiter.js",
                 "hsp_kitchen.js", "hsp_cashier.js", "loyalty_games.js", "loyalty_games_play.js", "loyalty_games_screen.js",
                 "loyalty_games_live.css", "billing_reminder.js"):
        assert must in client_files, must
    for name in sorted(client_files):
        r = client.get(f"/client-static/{name}")
        assert r.status_code == 200, f"/client-static/{name} -> {r.status_code}"
    brand = _referenced("/assets")
    assert {"brand/favicon.ico", "brand/clonexa-icono.svg"} <= brand
    # Ya daba 404 en produccion antes de este cambio: login.css aun lo nombra,
    # pero el archivo no existe (el login usa el SVG de la marca desde abfcf1f).
    known_missing = {"clonexa-login-watermark.png"}
    assert not (WEB / "assets" / "clonexa-login-watermark.png").exists()
    for name in sorted(brand - known_missing):
        assert client.get(f"/assets/{name}").status_code == 200, name
    for name in sorted(_referenced("/admin-v2-assets")) or ["consola-panel.jpg", "consola-fondo.jpg"]:
        assert client.get(f"/admin-v2-assets/{name}").status_code == 200, name


def test_whitelist_rules():
    ok = safe_static.is_allowed_file
    assert ok("client.js") and ok("x.png") and ok("brand/x.svg", allowed_dirs=frozenset({"brand"}))
    assert not ok("brand/x.svg"), "subcarpeta no declarada"
    assert not ok("main.py") and not ok("a.env") and not ok("../x.js") and not ok(".hidden.js")
    assert not ok("garment_catalog.json") and ok("garment_catalog.json", allowed_names=frozenset({"garment_catalog.json"}))
    assert safe_static.blocks_request("/client-static/%2e%2e/main.py")
    assert safe_static.blocks_request("/client-static/brand_registry.json")
    assert not safe_static.blocks_request("/openapi.json"), "fuera de las rutas estaticas no aplica"


def test_old_admin_page_is_gone_and_redirects_to_console_v2plus():
    for name in ("admin.html", "admin.js", "admin.css", "admin_routes.py"):
        assert not (WEB / name).exists(), name
    for path in ("/admin", "/admin/"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 308 and r.headers["location"] == "/admin-v2plus"
    assert client.get("/admin-static/admin.js").status_code == 404
    assert client.get("/admin-static/admin_v2_routes.py").status_code == 404


# ------------------------------------------------- cerrar sesion (servidor)
@pytest.fixture
def sessions(monkeypatch):
    store: dict[str, str] = {}

    async def register(*_args, **_kwargs):
        store["sess-1"] = "active"
        return "sess-1"

    async def validate(_db, key, **_kwargs):
        if store.get(key) != "active":
            raise HTTPException(status_code=401, detail="Sesion cerrada.")
        return {"session_key": key}

    async def close(_db, key, _reason):
        store[key] = "closed"
        return True

    monkeypatch.setenv(routes.PASSWORD_BCRYPT_ENV, bcrypt.hashpw(b"clave-larga-de-prueba", bcrypt.gensalt(rounds=4)).decode())
    monkeypatch.delenv(routes.PASSWORD_SHA256_ENV, raising=False)
    routes._login_failures.clear()
    monkeypatch.setattr(routes, "register_access_session", register)
    monkeypatch.setattr(routes, "validate_access_session", validate)
    monkeypatch.setattr(routes, "close_access_session", close)
    monkeypatch.setattr(routes, "list_access_sessions", AsyncMock(return_value=[]))

    async def fake_db():
        yield None

    app_main.app.dependency_overrides[get_db] = fake_db
    yield store
    app_main.app.dependency_overrides.pop(get_db, None)
    routes._login_failures.clear()


def test_logout_closes_the_session_on_the_server(sessions):
    c = TestClient(app_main.app)
    login = c.post("/admin-v2plus/login", data={"email": routes.ADMIN_V2_EMAIL, "password": "clave-larga-de-prueba"},
                   headers={"x-forwarded-for": "200.1.1.9"}, follow_redirects=False)
    assert login.status_code == 303, login.text
    cookie = c.cookies.get(routes.ADMIN_V2_COOKIE)
    assert cookie and sessions["sess-1"] == "active"
    assert c.get("/admin-v2/api/sessions").status_code == 200

    out = c.post("/admin-v2/logout", follow_redirects=False)
    assert out.status_code == 303
    assert sessions["sess-1"] == "closed", "la sesion se cierra en el servidor, no solo en la pantalla"
    assert f'{routes.ADMIN_V2_COOKIE}=""' in out.headers.get("set-cookie", "") or "Max-Age=0" in out.headers.get("set-cookie", "")

    # Aunque alguien reenvie la cookie vieja, ya no sirve.
    replay = TestClient(app_main.app)
    replay.cookies.set(routes.ADMIN_V2_COOKIE, cookie)
    for path in ("/admin-v2/api/sessions", "/admin-v2/api/overview", "/admin-v2/api/switches", "/admin-v2/api/audit"):
        r = replay.get(path, follow_redirects=False)
        assert r.status_code == 401, f"{path} -> {r.status_code}"
    page = replay.get("/admin-v2plus", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/admin-v2plus/login"
    assert "no-store" in page.headers.get("cache-control", "")


def test_console_page_is_no_store():
    async def yes(*_a, **_k):
        return True

    import app.web.admin_v2plus_routes as plus

    original = plus._active_session
    plus._active_session = yes
    try:
        async def fake_db():
            yield None

        app_main.app.dependency_overrides[get_db] = fake_db
        r = client.get("/admin-v2plus", follow_redirects=False)
        assert r.status_code == 200 and "no-store" in r.headers["cache-control"]
        assert "data-vp-logout-open" in r.text
    finally:
        plus._active_session = original
        app_main.app.dependency_overrides.pop(get_db, None)


def test_crm_lab_manifest_is_the_only_extra_name():
    """056K: el manifest del CRM VELVET-LAB (pantalla de inicio sin barra) sale por
    /client-static; ningun otro .webmanifest ni las demas reglas cambian."""
    r = client.get("/client-static/crm_lab.webmanifest")
    assert r.status_code == 200
    assert r.json()["display"] == "fullscreen" and r.json()["start_url"].startswith("/mini-panel/crm-lab")
    assert client.get("/client-static/otro.webmanifest").status_code == 404
    assert client.get("/client-static/client_routes.py").status_code == 404
