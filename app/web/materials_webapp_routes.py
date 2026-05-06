from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/webapp/materials")
async def materials_webapp() -> FileResponse:
    return FileResponse("app/web/materials_webapp.html")
