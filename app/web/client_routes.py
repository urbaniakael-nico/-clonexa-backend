from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.web.admin_v2_routes import _active_session as active_admin_v2_session
from app.web.admin_v2_routes import _set_company_preview_cookie
from fastapi.staticfiles import StaticFiles


def _read_html(path: Path) -> HTMLResponse:
    return HTMLResponse(
        path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


_SHORT_LINK_NOT_FOUND = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Link no encontrado</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;font:16px system-ui,sans-serif;background:#0b0a14;color:#fff;padding:16px}
main{max-width:360px;text-align:center}h1{font-size:20px}p{opacity:.8}</style></head>
<body><main><h1>Este link no existe o ya no sirve</h1><p>Pide a quien te lo envió un link nuevo.</p></main></body></html>"""


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
        async def client_page(
            request: Request,
            company_id: str = "",
            db: AsyncSession = Depends(get_db),
        ) -> HTMLResponse:
            response = _read_html(web_dir / "client.html")
            if company_id and await active_admin_v2_session(request, db):
                _set_company_preview_cookie(response, request, company_id)
            return response

    if not any(getattr(route, "path", None) == "/ordenar" for route in app.routes):
        @app.get("/ordenar", response_class=HTMLResponse, include_in_schema=False)
        async def hospitality_order_page() -> HTMLResponse:
            return _read_html(web_dir / "hospitality_order.html")

    # Domicilios por WhatsApp: public carta opened from the link the customer
    # line sends (the link code in ?s= is the only credential).
    if not any(getattr(route, "path", None) == "/domicilio" for route in app.routes):
        @app.get("/domicilio", response_class=HTMLResponse, include_in_schema=False)
        async def delivery_order_page() -> HTMLResponse:
            return _read_html(web_dir / "domicilio.html")

    # 049J: carta que abre el QR impreso de la carta (el codigo secreto ?t= es
    # la unica credencial; se cambia desde el portal y el anterior deja de servir).
    if not any(getattr(route, "path", None) == "/carta-qr" for route in app.routes):
        @app.get("/carta-qr", response_class=HTMLResponse, include_in_schema=False)
        async def carta_qr_page() -> HTMLResponse:
            return _read_html(web_dir / "carta_qr.html")

    if not any(getattr(route, "path", None) == "/shoplink" for route in app.routes):
        @app.get("/shoplink", response_class=HTMLResponse, include_in_schema=False)
        async def shoplink_public_page() -> HTMLResponse:
            return _read_html(web_dir / "shoplink_public.html")

    if not any(getattr(route, "path", None) == "/mercado" for route in app.routes):
        @app.get("/mercado", response_class=HTMLResponse, include_in_schema=False)
        async def marketplace_public_page(
            company_id: str = "",
            db: AsyncSession = Depends(get_db),
        ) -> Response:
            if not company_id:
                result = await db.execute(text("""
                    SELECT c.id::text AS id,
                           COALESCE(cm.settings->>'public_default', 'false') = 'true' AS is_default
                    FROM companies c
                    JOIN company_modules cm ON cm.company_id = c.id AND cm.enabled IS TRUE
                    JOIN modules m ON m.id = cm.module_id
                    WHERE m.code = 'marketplace_access' AND m.is_active IS TRUE
                      AND c.status = 'active'
                    ORDER BY is_default DESC, c.created_at ASC
                    LIMIT 2
                """))
                rows = result.mappings().all()
                selected = next((row for row in rows if row.get("is_default")), None)
                if selected is None and len(rows) == 1:
                    selected = rows[0]
                if selected is not None:
                    return RedirectResponse(url=f"/mercado?company_id={selected['id']}", status_code=307)
            return _read_html(web_dir / "marketplace_public.html")

    # 049Y: link corto /c/CODIGO -> el mini panel o la carta de domicilios de
    # siempre. Solo redirige a rutas internas ya existentes (que piden su
    # propio ingreso o su codigo de un solo uso); no entrega datos.
    if not any(getattr(route, "path", None) == "/c/{code}" for route in app.routes):
        @app.get("/c/{code}", include_in_schema=False)
        async def short_link_redirect(code: str, db: AsyncSession = Depends(get_db)) -> Response:
            from app.services import short_links

            try:
                target = await short_links.resolve(db, code)
            except Exception:
                await db.rollback()
                target = ""
            if not target:
                return HTMLResponse(_SHORT_LINK_NOT_FOUND, status_code=404, headers={"Cache-Control": "no-store"})
            return RedirectResponse(url=target, status_code=302, headers={"Cache-Control": "no-store"})

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

    # CLONEXA_026K_WAITER_ORDERING_ROUTES_START
    # Fase 1 mesero -> cocina -> caja: dedicated pages per role (not the
    # generic mini_panel.js shell), so the other 7 mini panel types keep
    # working unchanged. Still under /mini-panel/*, so the existing IP
    # allowlist middleware (app/main.py) covers these for free.
    _WAITER_ORDERING_PAGES = {
        "/mini-panel/mesero": "hsp_waiter.html",
        "/mini-panel/mesero/login": "hsp_waiter.html",
        "/mini-panel/cocina": "hsp_kitchen.html",
        "/mini-panel/cocina/login": "hsp_kitchen.html",
        "/mini-panel/caja": "hsp_cashier.html",
        "/mini-panel/caja/login": "hsp_cashier.html",
    }
    for _path, _file in _WAITER_ORDERING_PAGES.items():
        if any(getattr(route, "path", None) == _path for route in app.routes):
            continue

        def _make_waiter_ordering_page(file_name: str):
            async def _page() -> HTMLResponse:
                return _read_html(web_dir / file_name)
            return _page

        app.add_api_route(
            _path,
            _make_waiter_ordering_page(_file),
            methods=["GET"],
            response_class=HTMLResponse,
            include_in_schema=False,
        )
    # CLONEXA_026K_WAITER_ORDERING_ROUTES_END

    app.state.clonexa_client_portal_registered = True
