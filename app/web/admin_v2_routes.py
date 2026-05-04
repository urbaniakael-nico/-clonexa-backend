from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

router = APIRouter()

WEB_DIR = Path(__file__).resolve().parent
ASSETS_DIR = WEB_DIR / "assets"


@router.get("/admin-v2", response_class=HTMLResponse, include_in_schema=False)
async def admin_v2_page():
    html_path = WEB_DIR / "admin_v2.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Admin Console V2 no encontrada")
    return FileResponse(html_path)


@router.get("/admin-v2.css", include_in_schema=False)
async def admin_v2_css():
    css_path = WEB_DIR / "admin_v2.css"
    if not css_path.exists():
        raise HTTPException(status_code=404, detail="CSS Admin V2 no encontrado")
    return FileResponse(css_path, media_type="text/css")


@router.get("/admin-v2.js", include_in_schema=False)
async def admin_v2_js():
    js_path = WEB_DIR / "admin_v2.js"
    if not js_path.exists():
        raise HTTPException(status_code=404, detail="JS Admin V2 no encontrado")
    return FileResponse(js_path, media_type="application/javascript")


@router.get("/admin-v2-assets/{asset_path:path}", include_in_schema=False)
async def admin_v2_assets(asset_path: str):
    safe_path = (ASSETS_DIR / asset_path).resolve()
    assets_root = ASSETS_DIR.resolve()

    if assets_root not in safe_path.parents and safe_path != assets_root:
        raise HTTPException(status_code=404, detail="Asset inválido")

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Asset no encontrado")

    return FileResponse(safe_path)


@router.get("/admin-v2/ping", include_in_schema=False)
async def admin_v2_ping():
    return Response("OK", media_type="text/plain")
