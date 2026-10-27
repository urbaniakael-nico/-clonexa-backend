"""Consola v2+ · Menu video (solo Admin V2) y la ruta de archivos /menu-media.

- GET  /menu-media/{company_id}/{asset_id}.webp|.mp4
      Sirve fotos, portadas y clips desde el bucket por el MISMO origen, con
      rangos (Safari en iPhone pide el video por partes). Se ve si: lo usa hoy
      un plato real de ESA empresa (es lo que muestra el QR), o hay sesion de
      Admin V2, o la URL viene firmada (vistas previas, 6 h). Si no, 404.
- /admin-v2/api/menu-video/...  (sesion de Admin V2, 401 sin ella):
  empresas con Carta, salud (version de ffmpeg), importar (PDF, fotos o
  enlace) y la tabla editable, fotos por plato (emparejadas por nombre de
  archivo), cola de remasterizado y clips, publicar (combinar) y el cupo.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import ipaddress
import json
import re
import socket
import uuid
from collections import OrderedDict
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import brand_media
from app.services import menu_media as mm
from app.services import menu_video as mv
from app.web import admin_v2_routes as v2
from app.web.admin_v2plus_companies import GUARD, _audit, _json, _uuid, load_company

router = APIRouter()
API = "/admin-v2/api/menu-video"
_FILE_RE = re.compile(r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.(webp|mp4)$")
MAX_IMPORT_FILES = 10
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PAGE_BYTES = 5 * 1024 * 1024


# ------------------------------------------------------------ /menu-media ---
class _Cache:
    """Bytes recientes en memoria (los clips pesan < 400 KB): el bucket no se
    consulta en cada rango que pide el celular."""

    def __init__(self, limit_bytes: int = 48 * 1024 * 1024):
        self.limit, self.used, self.items = limit_bytes, 0, OrderedDict()

    def get(self, key: str) -> Optional[bytes]:
        data = self.items.get(key)
        if data is not None:
            self.items.move_to_end(key)
        return data

    def put(self, key: str, data: bytes) -> None:
        if len(data) > self.limit // 8 or key in self.items:
            return
        self.items[key] = data
        self.used += len(data)
        while self.used > self.limit and self.items:
            _k, old = self.items.popitem(last=False)
            self.used -= len(old)


CACHE = _Cache()


def _range(header: str, size: int) -> Optional[tuple[int, int]]:
    match = re.match(r"^bytes=(\d*)-(\d*)$", (header or "").strip())
    if not match or size <= 0:
        return None
    start_s, end_s = match.groups()
    if start_s == "" and end_s == "":
        return None
    if start_s == "":
        length = int(end_s)
        start, end = max(0, size - length), size - 1
    else:
        start = int(start_s)
        end = min(int(end_s), size - 1) if end_s else size - 1
    if start > end or start >= size:
        raise HTTPException(status_code=416, detail="Rango inválido.", headers={"Content-Range": f"bytes */{size}"})
    return start, end


@router.get("/menu-media/{company_id}/{media_file}", include_in_schema=False)
async def serve_media(company_id: str, media_file: str, request: Request, e: str = "", s: str = "",
                      db: AsyncSession = Depends(get_db)):
    match = _FILE_RE.match(media_file or "")
    if not match:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    asset_id, ext = match.group(1), match.group(2)
    try:
        cid = str(uuid.UUID(company_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.") from None
    row = await mv.asset(db, cid, asset_id)
    if not row or (row["content_type"] == "video/mp4") != (ext == "mp4"):
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    public = await mv.is_public(db, cid, asset_id)
    if not public and not (e and s and mv.signature_ok(cid, asset_id, e, s)) and not await v2._active_session(request, db):
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    data = CACHE.get(row["storage_key"])
    if data is None:
        try:
            data = await mv.read_bytes(row)
        except brand_media.StorageUnavailable:
            raise HTTPException(status_code=503, detail="Archivo no disponible por ahora.") from None
        CACHE.put(row["storage_key"], data)
    headers = {"Cache-Control": "public, max-age=604800, immutable" if public else "private, max-age=3600",
               "Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff"}
    span = _range(request.headers.get("range", ""), len(data))
    if span:
        start, end = span
        headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
        return Response(content=data[start:end + 1], status_code=206, media_type=row["content_type"], headers=headers)
    return Response(content=data, media_type=row["content_type"], headers=headers)


# ------------------------------------------------------------ utilidades ---
def _storage_error(error: Exception) -> HTTPException:
    if isinstance(error, brand_media.StorageUnavailable):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


async def _carta_company(db: AsyncSession, company_id: str) -> dict:
    company = await load_company(db, _uuid(company_id))
    module = await mv.carta_module(db, company["id"])
    if not module or not module["enabled"]:
        raise HTTPException(status_code=409, detail="Esta empresa no tiene el módulo Carta activo.")
    company["settings"] = module["settings"]
    return company


async def _import_or_404(db: AsyncSession, company_id: str, import_id: str) -> dict:
    current = await mv.get_import(db, company_id, import_id)
    if not current:
        raise HTTPException(status_code=404, detail="Importación no encontrada.")
    return current


async def _photos(db: AsyncSession, company_id: str, import_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, dish_ref::text AS dish_ref, role, source_name, size_bytes, width, height, meta
        FROM menu_media_assets
        WHERE company_id = CAST(:c AS uuid) AND variant = 'original' AND meta->>'import_id' = :i
        ORDER BY created_at
    """), {"c": company_id, "i": import_id})).mappings().all()
    return [{**dict(r), "meta": mv._json(r["meta"], {}), "url": mv.media_url(company_id, r["id"], signed=True)} for r in rows]


async def _targets(db: AsyncSession, company_id: str, current: dict) -> dict[str, str]:
    """ref -> donde viven sus fotos: el borrador si tiene; si no, el plato ya publicado."""
    table = current.get("table_data") or {}
    media = await mv.media_map(db, company_id)
    published = await mv.published_targets(db, company_id, table)
    out = {}
    for d in table.get("platos") or []:
        ref = d["ref"]
        out[ref] = ref if (ref in media or ref not in published) else published[ref]
    return out


async def _import_state(db: AsyncSession, company_id: str, current: Optional[dict]) -> dict:
    if not current:
        return {"import": None, "media": {}, "jobs": {}, "photos": [], "targets": {}}
    refs = [d["ref"] for d in (current.get("table_data") or {}).get("platos") or []]
    targets = await _targets(db, company_id, current)
    media = await mv.media_map(db, company_id, signed=True)
    jobs = await mv.jobs_for(db, company_id, list(set(targets.values())))
    current = {**current, "files": [{k: v for k, v in f.items() if k != "key"} for f in current.get("files") or []]}
    return {"import": current, "media": {r: media[targets[r]] for r in refs if targets.get(r) in media},
            "jobs": {r: jobs[targets[r]] for r in refs if targets.get(r) in jobs},
            "published": {r: targets[r] for r in refs if targets.get(r) != r},
            "photos": await _photos(db, company_id, current["id"])}


# --------------------------------------------------------------- lectura ---
def page_text(raw_html: str) -> str:
    """Texto visible de una pagina (sin scripts ni estilos), maximo 60.000 caracteres."""
    body = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw_html)
    body = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", body)
    body = html_lib.unescape(re.sub(r"<[^>]+>", " ", body))
    lines = [" ".join(line.split()) for line in body.splitlines()]
    return "\n".join(line for line in lines if line)[:60000]


def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
            return False
    return bool(infos)


async def fetch_link(url: str) -> tuple[bytes, str]:
    """Descarga el enlace pegado (solo https a direcciones publicas, sin
    redirecciones a la red interna, maximo 5 MB / 20 MB si es PDF)."""
    import httpx

    current = url.strip()
    for _hop in range(4):
        parsed = urlparse(current)
        if parsed.scheme != "https" or not parsed.hostname:
            raise HTTPException(status_code=422, detail="El enlace debe empezar por https://")
        if not await asyncio.to_thread(_public_host, parsed.hostname):
            raise HTTPException(status_code=422, detail="Ese enlace no se puede abrir.")
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
            async with client.stream("GET", current, headers={"User-Agent": "Clonexa-Carta/1.0"}) as response:
                if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                    current = str(httpx.URL(current).join(response.headers["location"]))
                    continue
                if response.status_code >= 400:
                    raise HTTPException(status_code=422, detail=f"El enlace respondió {response.status_code}.")
                content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
                limit = MAX_PDF_BYTES if content_type == "application/pdf" else MAX_PAGE_BYTES
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(status_code=413, detail="El enlace pesa demasiado.")
                    chunks.append(chunk)
                return b"".join(chunks), content_type
    raise HTTPException(status_code=422, detail="El enlace redirige demasiadas veces.")


def _kind(raw: bytes, content_type: str = "") -> Optional[str]:
    if raw.startswith(b"%PDF"):
        return "pdf"
    sniffed = brand_media.sniff(raw)
    if sniffed:
        return "imagen"
    if content_type.startswith("text/html") or content_type.startswith("text/plain"):
        return "texto"
    return None


async def _send_to_n8n(db: AsyncSession, request: Request, company_id: str, import_id: str, files: list[dict]) -> tuple[bool, str]:
    archivos = []
    for f in files:
        if f["tipo"] == "texto":
            archivos.append({"tipo": "texto", "nombre": f["nombre"], "texto": f.get("texto", "")})
        else:
            archivos.append({"tipo": f["tipo"], "nombre": f["nombre"], "media_type": f["media_type"],
                             "url": await asyncio.to_thread(mv.presign, f["key"], 900)})
    base = str(request.base_url).rstrip("/").replace("http://", "https://", 1)
    ok, why = await mv.call_n8n(mv.read_webhook_url(), {
        "job_id": import_id, "company_id": company_id, "archivos": archivos,
        "callback_url": f"{base}/api/v1/menu-video/import-callback"})
    if not ok:
        await mv.mark_import(db, company_id, import_id, "error", f"No se pudo leer la carta automáticamente ({why}) Llénala a mano.")
        await db.commit()
    return ok, why


# -------------------------------------------------------------- endpoints ---
@router.get(f"{API}/health", include_in_schema=False, dependencies=GUARD)
async def health(db: AsyncSession = Depends(get_db)):
    import PIL

    try:
        stats = await mv.queue_stats(db)
    except Exception:
        await db.rollback()
        stats = {}
    return _json({"ok": True, "ffmpeg": mm.ffmpeg_version(), "pillow": PIL.__version__, "bucket": brand_media.configured(),
                  "token": bool(mv.token()), "n8n_read": mv.read_webhook_url(), "n8n_quota": mv.quota_webhook_url(),
                  "workers": mv.WORKERS, "queue": stats})


@router.get(f"{API}/companies", include_in_schema=False, dependencies=GUARD)
async def companies(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text("""
        SELECT c.id::text AS id, c.name, c.status, c.settings_json, cm.settings,
               (SELECT COUNT(*) FROM carta_items ci WHERE ci.company_id = c.id) AS dishes
        FROM companies c JOIN company_modules cm ON cm.company_id = c.id AND cm.enabled IS TRUE
        JOIN modules m ON m.id = cm.module_id AND LOWER(m.code) = 'carta'
        WHERE COALESCE(c.status, 'active') NOT IN ('archived', 'deleted')
        ORDER BY lower(c.name)
    """))).mappings().all()
    from app.services.company_kind import resolve_kind

    out = []
    for r in rows:
        settings = mv._json(r["settings"], {}) or {}
        out.append({"id": r["id"], "name": r["name"], "kind": resolve_kind(r["id"], r.get("settings_json")),
                    "carta_video": settings.get(mv.FLAG) is True, "dishes": int(r["dishes"] or 0),
                    "quota_new": mv._limit(settings, mv.QUOTA_NEW_KEY), "quota_changes": mv._limit(settings, mv.QUOTA_CHANGES_KEY)})
    return _json({"ok": True, "companies": out})


@router.get(API + "/{company_id}", include_in_schema=False, dependencies=GUARD)
async def company_state(company_id: str, db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    cid = company["id"]
    state = await _import_state(db, cid, await mv.latest_import(db, cid))
    dishes = (await db.execute(text("SELECT COUNT(*) FROM carta_items WHERE company_id = CAST(:c AS uuid)"), {"c": cid})).scalar()
    return _json({"ok": True, "company": {"id": cid, "name": company["name"], "kind": company["kind"]},
                  "carta_video": company["settings"].get(mv.FLAG) is True, "dishes": int(dishes or 0),
                  "quota": await mv.quota_state(db, cid), "styles": mm.STYLES, "backgrounds": mm.BACKGROUNDS,
                  "speeds": mm.SPEEDS, "gallery_max": mm.GALLERY_MAX, **state})


@router.post(API + "/{company_id}/imports", include_in_schema=False, dependencies=GUARD)
async def create_import(company_id: str, request: Request, files: list[UploadFile] = File(default=[]),
                        link: str = Form(default=""), manual: bool = Form(default=False), db: AsyncSession = Depends(get_db)):
    """Sube la carta (PDF, fotos o enlace) y la manda a leer a n8n; con
    manual=true arranca la tabla vacia para llenarla a mano."""
    company = await _carta_company(db, company_id)
    cid = company["id"]
    if manual:
        import_id = await mv.create_import(db, cid, "manual", [], status="manual")
        await db.commit()
        return _json({"ok": True, **await _import_state(db, cid, await mv.get_import(db, cid, import_id))})
    uploads = [f for f in files if getattr(f, "filename", None)]
    if not uploads and not link.strip():
        raise HTTPException(status_code=422, detail="Sube el PDF o las fotos de la carta, o pega un enlace.")
    if len(uploads) > MAX_IMPORT_FILES:
        raise HTTPException(status_code=422, detail=f"Máximo {MAX_IMPORT_FILES} archivos por carta.")
    if not brand_media.configured():
        raise HTTPException(status_code=503, detail="El almacenamiento de archivos no está configurado.")
    import_id = str(uuid.uuid4())
    stored: list[dict] = []
    pending: list[tuple[bytes, str, str]] = []
    for upload in uploads:
        raw = await upload.read(MAX_PDF_BYTES + 1)
        if len(raw) > MAX_PDF_BYTES:
            raise HTTPException(status_code=413, detail=f"{upload.filename} pesa más de 20 MB.")
        pending.append((raw, upload.filename or "carta", ""))
    if link.strip():
        raw, content_type = await fetch_link(link)
        pending.append((raw, link.strip()[:200], content_type))
    for index, (raw, name, content_type) in enumerate(pending):
        kind = _kind(raw, content_type)
        if kind is None:
            raise HTTPException(status_code=422, detail=f"{name}: usa PDF, JPG, PNG o WebP (o un enlace a una página).")
        if kind == "texto":
            text_value = page_text(raw.decode("utf-8", "replace"))
            if len(text_value) < 30:
                raise HTTPException(status_code=422, detail="La página del enlace no tiene texto de carta.")
            stored.append({"tipo": "texto", "nombre": name, "texto": text_value, "size": len(text_value)})
            continue
        media_type = "application/pdf" if kind == "pdf" else {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[brand_media.sniff(raw)]
        key = f"menuvideo-import/{cid}/{import_id}/{index}.{'pdf' if kind == 'pdf' else media_type.split('/')[1]}"
        try:
            await asyncio.to_thread(mv._put, key, raw, media_type, True)
        except brand_media.StorageUnavailable as error:
            raise _storage_error(error) from None
        stored.append({"tipo": kind, "nombre": name, "media_type": media_type, "key": key, "size": len(raw)})
    await db.execute(text("""
        INSERT INTO menu_video_imports (id, company_id, status, source, files, table_data)
        VALUES (CAST(:i AS uuid), CAST(:c AS uuid), 'leyendo', :src, CAST(:f AS jsonb), CAST(:t AS jsonb))
    """), {"i": import_id, "c": cid, "src": "enlace" if link.strip() and not uploads else "archivos",
           "f": json.dumps([{k: v for k, v in f.items() if k != "texto"} for f in stored]),
           "t": json.dumps({"categorias": [], "platos": []})})
    await db.commit()
    await _audit(request, company_name=company["name"], menu_video="importar carta", archivos=len(stored))
    await _send_to_n8n(db, request, cid, import_id, stored)
    return _json({"ok": True, **await _import_state(db, cid, await mv.get_import(db, cid, import_id))})


@router.get(API + "/{company_id}/imports/{import_id}", include_in_schema=False, dependencies=GUARD)
async def import_state(company_id: str, import_id: str, db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    current = await _import_or_404(db, company["id"], import_id)
    return _json({"ok": True, "quota": await mv.quota_state(db, company["id"]), **await _import_state(db, company["id"], current)})


class TableIn(BaseModel):
    table: dict = Field(default_factory=dict)


@router.put(API + "/{company_id}/imports/{import_id}/table", include_in_schema=False, dependencies=GUARD)
async def save_table(company_id: str, import_id: str, payload: TableIn, db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    current = await _import_or_404(db, company["id"], import_id)
    # 057C: una carta ya publicada se puede seguir corrigiendo y volver a publicar (combinar).
    status = "lista" if current["status"] in ("leyendo", "error", "manual") else None
    await mv.save_table(db, company["id"], import_id, payload.table, status=status)
    await db.commit()
    return _json({"ok": True, **await _import_state(db, company["id"], await mv.get_import(db, company["id"], import_id))})


@router.post(API + "/{company_id}/imports/{import_id}/photos", include_in_schema=False, dependencies=GUARD)
async def upload_photos(company_id: str, import_id: str, files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db)):
    """Varias fotos a la vez: cada una se empareja con su plato por el nombre
    del archivo ("lomo-saltado-perfil.jpg" -> Lomo saltado, perfil)."""
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    dishes = (current.get("table_data") or {}).get("platos") or []
    results = []
    for upload in files[:60]:
        raw = await upload.read(mm.MAX_UPLOAD_BYTES + 1)
        name = upload.filename or "foto"
        ref, role = mv.match_photo(name, dishes)
        try:
            image = await asyncio.to_thread(mm.load, raw)
            data, w, h = await asyncio.to_thread(mm.normalize, image)
            if ref:
                existing = await mv.dish_media(db, cid, ref) or {}
                if role == "main" and existing.get("front_original"):
                    role = "gallery"  # dos fotos del mismo plato: la segunda va a la galeria de Detalle
                asset_id = await mv.save_photo(db, cid, ref, role, raw, name, meta={"import_id": import_id})
            else:
                asset_id = await mv.store_asset(db, cid, None, role, "original", data, "image/webp", w, h, name, {"import_id": import_id})
            await db.commit()
            results.append({"file": name, "asset_id": asset_id, "ref": ref, "role": role, "ok": True})
        except (mm.MediaRejected, brand_media.ImageRejected, brand_media.StorageUnavailable) as error:
            await db.rollback()
            results.append({"file": name, "ok": False, "error": str(error)})
    return _json({"ok": True, "results": results, **await _import_state(db, cid, await mv.get_import(db, cid, import_id))})


class AssignIn(BaseModel):
    ref: str = Field(..., max_length=40)
    role: str = Field(default="main", pattern="^(main|gallery|front|side|top)$")


@router.put(API + "/{company_id}/imports/{import_id}/photos/{asset_id}", include_in_schema=False, dependencies=GUARD)
async def assign_photo(company_id: str, import_id: str, asset_id: str, payload: AssignIn, db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    refs = {d["ref"] for d in (current.get("table_data") or {}).get("platos") or []}
    if payload.ref not in refs:
        raise HTTPException(status_code=404, detail="Ese plato no está en la tabla.")
    try:
        await mv.assign_photo(db, cid, asset_id, payload.ref, payload.role)
        await db.commit()
    except brand_media.ImageRejected as error:
        await db.rollback()
        raise _storage_error(error) from None
    return _json({"ok": True, **await _import_state(db, cid, current)})


class ProcessIn(BaseModel):
    refs: Optional[list[str]] = None
    style: str = Field(default="auto", max_length=20)


@router.post(API + "/{company_id}/imports/{import_id}/process", include_in_schema=False, dependencies=GUARD)
async def process(company_id: str, import_id: str, payload: ProcessIn, db: AsyncSession = Depends(get_db)):
    """Remasterizar y crear clips (uno, varios o todos los que tienen foto)."""
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    targets = await _targets(db, cid, current)
    wanted = [r for r in targets if payload.refs is None or r in payload.refs]
    queued = 0
    for ref in wanted:
        media = await mv.dish_media(db, cid, targets[ref])
        if mv.has_source(media):
            await mv.enqueue(db, cid, targets[ref], "auto")
            queued += 1
    await db.commit()
    mv.wake()
    return _json({"ok": True, "queued": queued, **await _import_state(db, cid, current)})


# ------------------------------------------- cambiar / quitar fotos (057D)
async def _target_of(db: AsyncSession, cid: str, current: dict, ref: str) -> str:
    targets = await _targets(db, cid, current)
    if ref not in targets:
        raise HTTPException(status_code=404, detail="Ese plato no está en la tabla.")
    return targets[ref]


async def _requeue(db: AsyncSession, cid: str, target: str) -> None:
    if mv.has_source(await mv.dish_media(db, cid, target)):
        await mv.enqueue(db, cid, target, "auto")


@router.post(API + "/{company_id}/imports/{import_id}/dish/{ref}/photo/{role}", include_in_schema=False, dependencies=GUARD)
async def change_photo(company_id: str, import_id: str, ref: str, role: str, request: Request, file: UploadFile = File(...),
                       db: AsyncSession = Depends(get_db)):
    """Cambiar o subir: la foto principal, una de la galeria ("gallery" agrega,
    "gallery:<id>" cambia esa) o el video del plato ("video", Camino 1). Se
    rehace el clip. Lo que hace Clonexa desde la consola no gasta cupo."""
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    target = await _target_of(db, cid, current, ref)
    limit = mm.VIDEO_MAX_BYTES if role == "video" else mm.MAX_UPLOAD_BYTES
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(status_code=413, detail="El video pesa más de 150 MB: graba de 5 a 10 segundos." if role == "video"
                            else "La foto pesa más de 15 MB.")
    try:
        if role == "video":
            await mv.save_video(db, cid, target, raw, file.filename or "video")
        else:
            await mv.save_photo(db, cid, target, role, raw, file.filename or "foto", meta={"import_id": import_id})
        await mv.enqueue(db, cid, target, "auto")
        await db.commit()
    except (mm.MediaRejected, brand_media.ImageRejected, brand_media.StorageUnavailable) as error:
        await db.rollback()
        raise _storage_error(error) from None
    mv.wake()
    await _audit(request, company_name=company["name"], menu_video="cambió foto", plato=ref, foto=role)
    return _json({"ok": True, **await _import_state(db, cid, current)})


@router.delete(API + "/{company_id}/imports/{import_id}/dish/{ref}/photo/{role}", include_in_schema=False, dependencies=GUARD)
async def remove_photo(company_id: str, import_id: str, ref: str, role: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    target = await _target_of(db, cid, current, ref)
    try:
        undo = await mv.remove_role(db, cid, target, role)
        if not undo["empty"] and not role.startswith("gallery"):
            await mv.enqueue(db, cid, target, "auto")
        await db.commit()
    except brand_media.ImageRejected as error:
        await db.rollback()
        raise _storage_error(error) from None
    mv.wake()
    await _audit(request, company_name=company["name"], menu_video="quitó foto", plato=ref, foto=role)
    return _json({"ok": True, "undo": undo, **await _import_state(db, cid, current)})


class RestoreIn(BaseModel):
    original: str = Field(..., max_length=40)
    remaster: str = Field(default="", max_length=40)
    index: Optional[int] = Field(default=None, ge=0, le=20)


@router.post(API + "/{company_id}/imports/{import_id}/dish/{ref}/photo/{role}/restore", include_in_schema=False, dependencies=GUARD)
async def restore_photo(company_id: str, import_id: str, ref: str, role: str, payload: RestoreIn, request: Request,
                        db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    target = await _target_of(db, cid, current, ref)
    try:
        await mv.restore_role(db, cid, target, role, payload.original, payload.remaster, payload.index)
        if not role.startswith("gallery"):
            await mv.enqueue(db, cid, target, "auto")
        await db.commit()
    except brand_media.ImageRejected as error:
        await db.rollback()
        raise _storage_error(error) from None
    mv.wake()
    await _audit(request, company_name=company["name"], menu_video="deshizo quitar foto", plato=ref, foto=role)
    return _json({"ok": True, **await _import_state(db, cid, current)})


@router.delete(API + "/{company_id}/imports/{import_id}/dish/{ref}/video", include_in_schema=False, dependencies=GUARD)
async def remove_video(company_id: str, import_id: str, ref: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Quitar video: el plato queda solo con su foto."""
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    target = await _target_of(db, cid, current, ref)
    await mv.clear_video(db, cid, target)
    await db.commit()
    await _audit(request, company_name=company["name"], menu_video="quitó video", plato=ref)
    return _json({"ok": True, **await _import_state(db, cid, current)})


class OptionsIn(BaseModel):
    style: Optional[str] = Field(default=None, max_length=20)
    background: Optional[str] = Field(default=None, max_length=20)
    speed: Optional[str] = Field(default=None, max_length=20)
    start: Optional[float] = Field(default=None, ge=0, le=30)
    length: Optional[float] = Field(default=None, ge=0, le=30)
    mode: Optional[str] = Field(default=None, max_length=10)


@router.post(API + "/{company_id}/imports/{import_id}/dish/{ref}/options", include_in_schema=False, dependencies=GUARD)
async def dish_options(company_id: str, import_id: str, ref: str, payload: OptionsIn, request: Request,
                       db: AsyncSession = Depends(get_db)):
    """Camino, estilo, fondo, velocidad y tramo + "Rehacer" (no gasta cupo)."""
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    target = await _target_of(db, cid, current, ref)
    try:
        options = await mv.set_options(db, cid, target, payload.model_dump(exclude_unset=True))
        await mv.enqueue(db, cid, target, options["style"])
        await db.commit()
    except brand_media.ImageRejected as error:
        await db.rollback()
        raise _storage_error(error) from None
    mv.wake()
    await _audit(request, company_name=company["name"], menu_video="rehacer clip", plato=ref, **{k: v for k, v in options.items() if v is not None})
    return _json({"ok": True, **await _import_state(db, cid, current)})


@router.post(API + "/{company_id}/regenerate", include_in_schema=False, dependencies=GUARD)
async def regenerate(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Rehacer todos los clips de la empresa con el proceso actual. No gasta
    cupo; los clips publicados se siguen viendo hasta que el nuevo este listo."""
    company = await _carta_company(db, company_id)
    count = await mv.regenerate_company(db, company["id"])
    await db.commit()
    mv.wake()
    await _audit(request, company_name=company["name"], menu_video="rehacer todos", clips=count)
    return _json({"ok": True, "queued": count})


class ChooseIn(BaseModel):
    use_remaster: bool = True


@router.post(API + "/{company_id}/imports/{import_id}/dish/{ref}/choose", include_in_schema=False, dependencies=GUARD)
async def choose(company_id: str, import_id: str, ref: str, payload: ChooseIn, db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    ref = await _target_of(db, cid, current, ref)
    media = await mv.dish_media(db, cid, ref)
    if not media:
        raise HTTPException(status_code=404, detail="Ese plato no tiene foto.")
    await mv.upsert_media(db, cid, ref, use_remaster=payload.use_remaster)
    if media.get("clip_asset") or media.get("status") in ("en_cola", "listo"):
        await mv.enqueue(db, cid, ref, "auto")
    await db.commit()
    mv.wake()
    return _json({"ok": True, **await _import_state(db, cid, current)})


@router.get(API + "/{company_id}/imports/{import_id}/plan", include_in_schema=False, dependencies=GUARD)
async def plan(company_id: str, import_id: str, db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    current = await _import_or_404(db, company["id"], import_id)
    return _json({"ok": True, "plan": await mv.plan_publish(db, company["id"], current["table_data"])})


@router.post(API + "/{company_id}/imports/{import_id}/publish", include_in_schema=False, dependencies=GUARD)
async def publish(company_id: str, import_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    cid = company["id"]
    current = await _import_or_404(db, cid, import_id)
    if not (current.get("table_data") or {}).get("platos"):
        raise HTTPException(status_code=422, detail="La tabla no tiene platos.")
    # 057C: se puede publicar otra vez (combinar) mientras haya algo nuevo o actualizado.
    plan_now = await mv.plan_publish(db, cid, current["table_data"])
    if not plan_now["counts"]["new"] and not plan_now["counts"]["updated"]:
        raise HTTPException(status_code=409, detail="No hay cambios para publicar.")
    try:
        summary = await mv.publish(db, cid, import_id, current["table_data"])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await _audit(request, company_name=company["name"], menu_video="publicar", nuevos=summary["new"],
                 actualizados=summary["updated"], borrados=0)
    return _json({"ok": True, "summary": summary, "plan": await mv.plan_publish(db, cid, current["table_data"])})


class QuotaIn(BaseModel):
    quota_new: int = Field(..., ge=0, le=999)
    quota_changes: int = Field(..., ge=0, le=999)


@router.get(API + "/{company_id}/quota", include_in_schema=False, dependencies=GUARD)
async def quota(company_id: str, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    module = await mv.carta_module(db, company["id"])
    if not module:
        return _json({"ok": True, "available": False})
    return _json({"ok": True, "available": True, "carta_video": module["settings"].get(mv.FLAG) is True,
                  "quota": await mv.quota_state(db, company["id"]), "log": await mv.quota_log(db, company["id"])})


@router.put(API + "/{company_id}/quota", include_in_schema=False, dependencies=GUARD)
async def save_quota(company_id: str, payload: QuotaIn, request: Request, db: AsyncSession = Depends(get_db)):
    company = await _carta_company(db, company_id)
    await db.execute(text("""
        UPDATE company_modules SET settings = COALESCE(settings, '{}'::jsonb) || CAST(:s AS jsonb), updated_at = now()
        WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE LOWER(code) = 'carta' LIMIT 1)
    """), {"s": json.dumps({mv.QUOTA_NEW_KEY: payload.quota_new, mv.QUOTA_CHANGES_KEY: payload.quota_changes}),
           "c": company["id"]})
    await db.commit()
    await _audit(request, company_name=company["name"], cupo_nuevos=payload.quota_new, cupo_cambios=payload.quota_changes)
    return _json({"ok": True, "quota": await mv.quota_state(db, company["id"]), "log": await mv.quota_log(db, company["id"])})
