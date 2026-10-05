"""Estudio de marca · imagenes (Fase 4, parte 1).

- GET  /brand-media/{company_id}/{image_id}.webp   (o {image_id}-lite.webp)
      Sirve la imagen desde el bucket por el MISMO origen (la CSP no se abre a
      otros dominios), con cache. Solo si la imagen es de ESA empresa y quien
      pide puede verla (hoy: sesion de Admin V2; la marca publicada y el enlace
      de vista previa se agregan en las partes 4 y 5). Si no, 404.
- GET    /admin-v2/api/brand/{company_id}/images          lista y espacio usado
- POST   /admin-v2/api/brand/{company_id}/images          subir (multipart, campo "file")
- DELETE /admin-v2/api/brand/{company_id}/images/{id}     borrar
- GET    /admin-v2/api/media/legacy-stats                 imagenes viejas en Postgres (solo cuenta)
Todo lo de /admin-v2/api exige sesion de Admin V2 (401 antes de leer el cuerpo).
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import brand_media as media
from app.web.admin_v2plus_companies import GUARD, _audit, _json, _uuid, load_company
from app.web import admin_v2_routes as v2

router = APIRouter()
_FILE_RE = re.compile(r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(-lite)?\.webp$")


def _storage_error(error: Exception) -> HTTPException:
    if isinstance(error, media.StorageUnavailable):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


async def can_view(request: Request, db: AsyncSession, company_id: str, image_id: str) -> bool:
    """Quien puede ver una imagen de marca. Las partes 4 y 5 agregan la marca
    publicada y el enlace de vista previa; aqui, solo la consola."""
    return bool(await v2._active_session(request, db))


@router.get("/brand-media/{company_id}/{image_file}", include_in_schema=False)
async def serve_image(company_id: str, image_file: str, request: Request, db: AsyncSession = Depends(get_db)):
    match = _FILE_RE.match(image_file)
    if not match:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")
    image_id, lite = match.group(1), bool(match.group(2))
    try:
        if not await can_view(request, db, company_id, image_id):
            raise HTTPException(status_code=404, detail="Imagen no encontrada.")
        data = await media.read(db, company_id, image_id, lite=lite)
    except media.ImageRejected:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.") from None
    except media.StorageUnavailable:
        raise HTTPException(status_code=503, detail="Imagen no disponible por ahora.") from None
    if data is None:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")
    # Los ids no cambian nunca (una imagen nueva es otro id): cache largo.
    return Response(content=data, media_type="image/webp", headers={
        "Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.get("/admin-v2/api/brand/{company_id}/images", include_in_schema=False, dependencies=GUARD)
async def list_images(company_id: str, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    return _json({"ok": True, "company_id": company["id"], "configured": media.configured(),
                  "usage": await media.usage(db, company["id"]), "images": await media.list_images(db, company["id"])})


@router.post("/admin-v2/api/brand/{company_id}/images", include_in_schema=False, dependencies=GUARD)
async def upload_image(company_id: str, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    if not media.configured():
        raise HTTPException(status_code=503, detail="El almacenamiento de imágenes no está configurado. Los paneles siguen funcionando; solo no se pueden subir imágenes.")
    lim = media.limits()
    raw = await file.read(lim.max_upload_bytes + 1)
    try:
        saved = await media.upload(db, company["id"], raw)
    except (media.StorageUnavailable, media.ImageRejected) as error:
        raise _storage_error(error) from None
    await _audit(request, company_name=company["name"], imagen=saved["id"], kb=round((saved["size_bytes"] + saved["lite_bytes"]) / 1024))
    return _json({"ok": True, "image": saved, "usage": await media.usage(db, company["id"])})


@router.delete("/admin-v2/api/brand/{company_id}/images/{image_id}", include_in_schema=False, dependencies=GUARD)
async def delete_image(company_id: str, image_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    try:
        done = await media.delete(db, company["id"], image_id)
    except (media.StorageUnavailable, media.ImageRejected) as error:
        raise _storage_error(error) from None
    if not done:
        raise HTTPException(status_code=404, detail="Imagen no encontrada en esta empresa.")
    await _audit(request, company_name=company["name"], imagen_borrada=image_id)
    return _json({"ok": True, "usage": await media.usage(db, company["id"])})


# ------------------------------------------------- imagenes viejas (Postgres)
LEGACY_LOGO_SQL = """
    SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(logo)), 0) AS bytes FROM (
        SELECT COALESCE(settings_json->'branding'->>'logo_url', settings_json->'company_branding'->>'logo_url',
                        settings_json->'experience'->'branding'->>'logo_url', '') AS logo
        FROM companies
    ) x WHERE logo LIKE 'data:image/%'
"""


async def legacy_stats(db: AsyncSession) -> dict[str, Any]:
    """Cuantas imagenes viejas hay en Postgres y cuanto pesan, por tabla. Solo cuenta."""
    from app.services.company_lifecycle import IMAGE_TABLES

    cols = (await db.execute(text("""
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND data_type = 'bytea' AND table_name = ANY(:t)
        ORDER BY table_name, column_name
    """), {"t": sorted(IMAGE_TABLES)})).mappings().all()
    tables = []
    for c in cols:
        table, column = str(c["table_name"]), str(c["column_name"])
        if not re.match(r"^[a-z_][a-z0-9_]*$", table) or not re.match(r"^[a-z_][a-z0-9_]*$", column):
            continue
        row = (await db.execute(text(
            f'SELECT COUNT("{column}") AS n, COALESCE(SUM(OCTET_LENGTH("{column}")), 0) AS bytes, '
            f'COUNT(DISTINCT company_id) FILTER (WHERE "{column}" IS NOT NULL) AS companies FROM "{table}"'
        ))).mappings().first()
        tables.append({"table": table, "column": column, "images": int(row["n"] or 0), "bytes": int(row["bytes"] or 0),
                       "companies": int(row["companies"] or 0)})
    logos = (await db.execute(text(LEGACY_LOGO_SQL))).mappings().first()
    tables.append({"table": "companies", "column": "settings_json (logo data:image)", "images": int(logos["n"] or 0),
                   "bytes": int(logos["bytes"] or 0), "companies": int(logos["n"] or 0)})
    return {"ok": True, "tables": tables, "total_images": sum(t["images"] for t in tables), "total_bytes": sum(t["bytes"] for t in tables)}


@router.get("/admin-v2/api/media/legacy-stats", include_in_schema=False, dependencies=GUARD)
async def legacy_stats_route(db: AsyncSession = Depends(get_db)):
    return _json(await legacy_stats(db))
