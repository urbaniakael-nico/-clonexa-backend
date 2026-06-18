from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles


def _read_html(path: Path) -> HTMLResponse:
    return HTMLResponse(
        path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


def register_client_portal(app: FastAPI) -> None:
    if getattr(app.state, "clonexa_client_portal_registered", False):
        return

    web_dir = Path(__file__).resolve().parent

    if not any(getattr(route, "name", None) == "clonexa_client_static" for route in app.routes):
        app.mount("/client-static", StaticFiles(directory=str(web_dir)), name="clonexa_client_static")

    if not any(getattr(route, "path", None) == "/login" for route in app.routes):
        @app.get("/login", response_class=HTMLResponse)
        async def login_page() -> HTMLResponse:
            return _read_html(web_dir / "login.html")

    if not any(getattr(route, "path", None) == "/client" for route in app.routes):
        @app.get("/client", response_class=HTMLResponse)
        async def client_page() -> HTMLResponse:
            return _read_html(web_dir / "client.html")

    if not any(getattr(route, "path", None) == "/ordenar" for route in app.routes):
        @app.get("/ordenar", response_class=HTMLResponse, include_in_schema=False)
        async def hospitality_order_page() -> HTMLResponse:
            return _read_html(web_dir / "hospitality_order.html")

    if not any(getattr(route, "path", None) == "/shoplink" for route in app.routes):
        @app.get("/shoplink", response_class=HTMLResponse, include_in_schema=False)
        async def shoplink_public_page() -> HTMLResponse:
            return _read_html(web_dir / "shoplink_public.html")

    # CLONEXA_019D_MINI_PANEL_ROUTES_START
    if not any(getattr(route, "path", None) == "/mini-panel/login" for route in app.routes):
        @app.get("/mini-panel/login", response_class=HTMLResponse, include_in_schema=False)
        async def mini_panel_login_page() -> HTMLResponse:
            return _read_html(web_dir / "mini_panel.html")

    if not any(getattr(route, "path", None) == "/mini-panel" for route in app.routes):
        @app.get("/mini-panel", response_class=HTMLResponse, include_in_schema=False)
        async def mini_panel_shell_page() -> HTMLResponse:
            return _read_html(web_dir / "mini_panel.html")
    # CLONEXA_019D_MINI_PANEL_ROUTES_END

    app.state.clonexa_client_portal_registered = True
