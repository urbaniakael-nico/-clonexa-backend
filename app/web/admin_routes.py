from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles


def register_admin_console(app: FastAPI) -> None:
    """Serve CLONEXA Admin Console from FastAPI without creating an external frontend."""
    web_dir = Path(__file__).resolve().parent
    assets_dir = web_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    static_name = "clonexa_admin_static"
    if not any(getattr(route, "name", None) == static_name for route in app.routes):
        app.mount("/admin-static", StaticFiles(directory=str(web_dir)), name=static_name)

    if not any(getattr(route, "path", None) == "/admin" for route in app.routes):
        @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
        async def clonexa_admin_console() -> HTMLResponse:
            html_path = web_dir / "admin.html"
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
