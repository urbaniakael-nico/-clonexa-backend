"""Consola v2+ (/admin-v2plus): la nueva consola principal, en paralelo.

/admin-v2 no se toca y sigue funcionando hasta que esta haga todo lo que hace
la actual. Usa la MISMA sesion de Admin V2 (validada en el servidor con
_active_session); sin sesion, redirige a /admin-v2/login. Las imagenes salen de
la ruta que ya existe, /admin-v2-assets/.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.web.admin_v2_routes import _active_session, _no_store

router = APIRouter()
WEB_DIR = Path(__file__).resolve().parent


def _file(name: str, media_type: str | None = None) -> FileResponse:
    path = WEB_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo de la Consola v2+ no encontrado")
    return _no_store(FileResponse(path, media_type=media_type))


@router.get("/admin-v2plus", include_in_schema=False)
@router.get("/admin-v2plus/", include_in_schema=False)
async def admin_v2plus_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not await _active_session(request, db):
        return _no_store(RedirectResponse(url="/admin-v2/login", status_code=303))
    return _file("admin_v2plus.html", "text/html")


@router.get("/admin-v2plus.css", include_in_schema=False)
async def admin_v2plus_css():
    return _file("admin_v2plus.css", "text/css")


@router.get("/admin-v2plus.js", include_in_schema=False)
async def admin_v2plus_js():
    return _file("admin_v2plus.js", "application/javascript")
