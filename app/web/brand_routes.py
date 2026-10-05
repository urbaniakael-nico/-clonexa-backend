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


async def can_view(request: Request, db: AsyncSession, company_id: str, image_id: str) -> tuple[bool, bool]:
    """(puede verla, es publica). Puede verla:
    - cualquiera, si la imagen esta en la marca PUBLICADA de esa empresa (ya se
      ve en su pantalla de ingreso);
    - la consola (sesion de Admin V2);
    - quien abrio un enlace de vista previa vigente de ESA empresa (cookie), si
      la imagen esta en su borrador."""
    import uuid as _uuid_mod

    from app.services import brand_share as share_
    from app.services import brand_store as store_
    from app.services import brand_theme as bt_

    try:
        iid = str(_uuid_mod.UUID(str(image_id)))
    except ValueError:
        return False, False
    published = await store_.published_tokens(db, company_id)
    if published and iid in bt_.image_ids(published):
        return True, True
    if await v2._active_session(request, db):
        return True, False
    link = await share_.resolve(db, request.cookies.get(share_.COOKIE, ""))
    if link and link["company_id"] == str(company_id):
        draft = await store_.draft_tokens(db, company_id)
        return bool(draft and iid in bt_.image_ids(draft)), False
    return False, False


@router.get("/brand-media/{company_id}/{image_file}", include_in_schema=False)
async def serve_image(company_id: str, image_file: str, request: Request, db: AsyncSession = Depends(get_db)):
    match = _FILE_RE.match(image_file)
    if not match:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")
    image_id, lite = match.group(1), bool(match.group(2))
    try:
        allowed, public = await can_view(request, db, company_id, image_id)
        if not allowed:
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
        "Cache-Control": "public, max-age=86400" if public else "private, max-age=3600", "X-Content-Type-Options": "nosniff",
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
    in_use = (await db.execute(text("""
        SELECT version, status FROM company_brand_themes
        WHERE company_id = CAST(:c AS uuid) AND status IN ('draft', 'published') AND tokens::text LIKE :needle
    """), {"c": company["id"], "needle": f"%{str(image_id).lower()[:36]}%"})).mappings().all() if _FILE_RE.match(f"{str(image_id).lower()}.webp") else []
    if in_use:
        where = "la marca publicada" if any(r["status"] == "published" for r in in_use) else "el borrador"
        raise HTTPException(status_code=409, detail=f"La imagen se usa en {where}. Quítala de la marca antes de borrarla.")
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


# ================================================================ marca (parte 2)
# GET    /admin-v2/api/brand/templates
# GET    /admin-v2/api/brand/{company_id}                 borrador, publicado e historial
# PUT    /admin-v2/api/brand/{company_id}/draft           {tokens}
# POST   /admin-v2/api/brand/{company_id}/publish         {confirm_name}
# POST   /admin-v2/api/brand/{company_id}/rollback/{v}    {confirm_name}
# POST   /admin-v2/api/brand/{company_id}/unpublish       {confirm_name}
# POST   /admin-v2/api/brand/{company_id}/palette-from-logo  {image_id?}
# POST   /admin-v2/api/brand/{company_id}/copy-from/{source_id}
from pydantic import BaseModel  # noqa: E402

from app.services import brand_store as store  # noqa: E402
from app.services import brand_theme as bt  # noqa: E402


class DraftIn(BaseModel):
    tokens: dict


class ConfirmIn(BaseModel):
    confirm_name: str = ""


class PaletteIn(BaseModel):
    image_id: str = ""


def _invalid(error: bt.BrandInvalid) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": f"{error.message} ({error.path})", "field": error.path})


def _confirm(company: dict, payload: ConfirmIn) -> None:
    if payload.confirm_name.strip().casefold() != str(company["name"]).strip().casefold():
        raise HTTPException(status_code=400, detail="Escribe el nombre exacto de la empresa para confirmar.")


async def _branding(db: AsyncSession, company_id: str) -> dict:
    from app.api.v1.endpoints.companies import _get_company_or_404, _read_company_branding

    try:
        return _read_company_branding(await _get_company_or_404(db, _uuid(company_id)))
    except Exception:
        return {}


@router.get("/admin-v2/api/brand/templates", include_in_schema=False, dependencies=GUARD)
async def brand_templates():
    return _json({"ok": True, "templates": bt.templates(), "fonts": list(bt.FONTS), "registry": bt.registry()})


@router.get("/admin-v2/api/brand/{company_id}", include_in_schema=False, dependencies=GUARD)
async def brand_state(company_id: str, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    data = await store.state(db, company["id"], await _branding(db, company["id"]))
    return _json({"ok": True, "company": {"id": company["id"], "name": company["name"], "kind": company["kind"]}, **data,
                  "registry": bt.registry(), "fonts": list(bt.FONTS), "storage": {"configured": media.configured(), **await media.usage(db, company["id"])},
                  "images": await media.list_images(db, company["id"])})


@router.put("/admin-v2/api/brand/{company_id}/draft", include_in_schema=False, dependencies=GUARD)
async def brand_save_draft(company_id: str, payload: DraftIn, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    try:
        tokens = await store.save_draft(db, company["id"], payload.tokens)
    except bt.BrandInvalid as error:
        raise _invalid(error) from None
    return _json({"ok": True, "tokens": tokens})


@router.post("/admin-v2/api/brand/{company_id}/publish", include_in_schema=False, dependencies=GUARD)
async def brand_publish(company_id: str, payload: ConfirmIn, request: Request, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    _confirm(company, payload)
    try:
        version = await store.publish(db, company["id"])
    except bt.BrandInvalid as error:
        raise _invalid(error) from None
    except store.BrandConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    await _audit(request, company_name=company["name"], marca="publicada", version=version)
    return _json({"ok": True, "published_version": version})


@router.post("/admin-v2/api/brand/{company_id}/rollback/{version}", include_in_schema=False, dependencies=GUARD)
async def brand_rollback(company_id: str, version: int, payload: ConfirmIn, request: Request, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    _confirm(company, payload)
    try:
        done = await store.rollback(db, company["id"], version)
    except bt.BrandInvalid as error:
        raise _invalid(error) from None
    except store.BrandConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    await _audit(request, company_name=company["name"], marca="vuelta_a_version", version=done)
    return _json({"ok": True, "published_version": done})


@router.post("/admin-v2/api/brand/{company_id}/unpublish", include_in_schema=False, dependencies=GUARD)
async def brand_unpublish(company_id: str, payload: ConfirmIn, request: Request, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    _confirm(company, payload)
    await store.unpublish(db, company["id"])
    await _audit(request, company_name=company["name"], marca="despublicada")
    return _json({"ok": True})


@router.post("/admin-v2/api/brand/{company_id}/palette-from-logo", include_in_schema=False, dependencies=GUARD)
async def brand_palette_from_logo(company_id: str, payload: PaletteIn, db: AsyncSession = Depends(get_db)):
    """Propone la paleta desde una imagen de ESTA empresa (no guarda nada)."""
    company = await load_company(db, _uuid(company_id))
    image = payload.image_id
    if not image:
        data = await store.state(db, company["id"], await _branding(db, company["id"]))
        image = (data["draft"]["tokens"]["theme"] or {}).get("logo") or ""
    if not image:
        raise HTTPException(status_code=409, detail="Primero sube el logo de la empresa.")
    try:
        raw = await media.read(db, company["id"], image, lite=True)
    except (media.StorageUnavailable, media.ImageRejected) as error:
        raise _storage_error(error) from None
    if raw is None:
        raise HTTPException(status_code=404, detail="Imagen no encontrada en esta empresa.")
    import asyncio

    return _json({"ok": True, "image_id": image, "colors": await asyncio.to_thread(bt.palette_from_image, raw)})


@router.post("/admin-v2/api/brand/{company_id}/copy-from/{source_id}", include_in_schema=False, dependencies=GUARD)
async def brand_copy_from(company_id: str, source_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Copia SOLO los tokens de otra empresa al borrador de esta, sin sus imagenes."""
    company = await load_company(db, _uuid(company_id))
    source = await load_company(db, _uuid(source_id))
    if source["id"] == company["id"]:
        raise HTTPException(status_code=400, detail="Elige otra empresa.")
    tokens = await store.tokens_for_copy(db, source["id"])
    if tokens is None:
        raise HTTPException(status_code=404, detail=f"{source['name']} todavía no tiene marca en el estudio.")
    saved = await store.save_draft(db, company["id"], tokens)
    await _audit(request, company_name=company["name"], marca="copiada_de", origen=source["name"])
    return _json({"ok": True, "tokens": saved})


# ============================================================ vista previa (parte 3)
# GET  /admin-v2/brand-preview/{company_id}?screen=   la pantalla con el borrador (sesion de Admin V2)
# POST /admin-v2/api/brand/{company_id}/render         CSS del borrador sin guardar (vista previa en vivo)
from fastapi.responses import HTMLResponse  # noqa: E402

from app.web import brand_preview  # noqa: E402

PREVIEW_HEADERS = {"Content-Security-Policy": brand_preview.PREVIEW_CSP, "Cache-Control": "no-store",
                   "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"}


@router.get("/admin-v2/brand-preview/{company_id}", include_in_schema=False)
async def studio_preview(company_id: str, request: Request, screen: str = "ingreso", db: AsyncSession = Depends(get_db)):
    if not await v2._active_session(request, db):
        return HTMLResponse("<!doctype html><title>Sesión requerida</title><p>Sesión de Admin V2 requerida.</p>", status_code=401, headers=PREVIEW_HEADERS)
    company = await load_company(db, _uuid(company_id))
    data = await store.state(db, company["id"], await _branding(db, company["id"]))
    tokens = data["draft"]["tokens"]
    return HTMLResponse(brand_preview.page(screen=screen, company_id=company["id"], css=bt.css_for(tokens, company["id"], states=True),
                                           branding=bt.branding_for_panels(tokens, company["id"]), mode="studio"), headers=PREVIEW_HEADERS)


@router.post("/admin-v2/api/brand/{company_id}/render", include_in_schema=False, dependencies=GUARD)
async def brand_render(company_id: str, payload: DraftIn, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    try:
        tokens = bt.validate(payload.tokens)
        await store.check_images(db, company["id"], tokens)
        css = bt.css_for(tokens, company["id"], states=True)
    except bt.BrandInvalid as error:
        raise _invalid(error) from None
    return _json({"ok": True, "css": css, "branding": bt.branding_for_panels(tokens, company["id"])})


# ============================================================ enlace para el cliente (parte 4)
# GET    /admin-v2/api/brand/{company_id}/share          enlaces (sin el token)
# POST   /admin-v2/api/brand/{company_id}/share          crea uno (el token se muestra UNA vez)
# DELETE /admin-v2/api/brand/{company_id}/share/{id}     revoca
# GET    /vista-marca/{token}?screen=                     la vista previa para el cliente (solo lectura)
from app.services import brand_share as share  # noqa: E402

SHARE_GONE = ('<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
              '<meta name="robots" content="noindex"><title>Vista previa no disponible</title></head><body><main><h1>Este enlace ya no sirve</h1>'
              '<p>Venció o fue revocado. Pide a Clonexa un enlace nuevo.</p></main></body></html>')


@router.get("/admin-v2/api/brand/{company_id}/share", include_in_schema=False, dependencies=GUARD)
async def share_list(company_id: str, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    return _json({"ok": True, "links": await share.list_links(db, company["id"])})


@router.post("/admin-v2/api/brand/{company_id}/share", include_in_schema=False, dependencies=GUARD)
async def share_create(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    if await store.draft_tokens(db, company["id"]) is None:
        raise HTTPException(status_code=409, detail="Abre y guarda el borrador antes de compartirlo.")
    link = await share.create(db, company["id"])
    await _audit(request, company_name=company["name"], marca="enlace_vista_previa", enlace=link["id"])
    return _json({"ok": True, **link})


@router.delete("/admin-v2/api/brand/{company_id}/share/{link_id}", include_in_schema=False, dependencies=GUARD)
async def share_revoke(company_id: str, link_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    if not await share.revoke(db, company["id"], link_id):
        raise HTTPException(status_code=404, detail="Enlace no encontrado.")
    await _audit(request, company_name=company["name"], marca="enlace_revocado", enlace=link_id)
    return _json({"ok": True})


@router.get("/vista-marca/{token}", include_in_schema=False)
async def share_page(token: str, screen: str = "ingreso", db: AsyncSession = Depends(get_db)):
    link = await share.resolve(db, token)
    tokens = await store.draft_tokens(db, link["company_id"]) if link else None
    if not link or tokens is None:
        return HTMLResponse(SHARE_GONE, status_code=404, headers=PREVIEW_HEADERS)
    cid = link["company_id"]
    response = HTMLResponse(brand_preview.page(screen=screen, company_id=cid, css=bt.css_for(tokens, cid),
                                               branding=bt.branding_for_panels(tokens, cid), mode="share",
                                               banner="Vista previa · aún no publicada", nav_token=token), headers=PREVIEW_HEADERS)
    # La cookie solo viaja a las imagenes de ESTA empresa (path); nunca a /api/v1.
    from datetime import datetime, timezone

    max_age = max(0, int((link["expires_at"] - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(share.COOKIE, token, max_age=max_age, path=f"/brand-media/{cid}/", httponly=True, secure=True, samesite="strict")
    return response
