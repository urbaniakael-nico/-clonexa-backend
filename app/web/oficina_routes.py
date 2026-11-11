"""Oficina 3D (Consola v2+ · "🏢 Ir a la oficina"): interno de Clonexa, SOLO Admin V2.

Pagina y archivos (sin sesion: la pagina lleva al ingreso; lo demas responde 401):
- GET /admin-v2plus/oficina                       la oficina a pantalla completa (CSP propia).
- GET /admin-v2plus/oficina/{app.js|app.css|logo-*.png}
- GET /admin-v2plus/oficina/vendor/three/...      copia local fija de three@0.160.0 (sin CDN).
API (GUARD: 401 sin sesion, antes de leer el cuerpo):
- GET  /admin-v2/api/oficina/estado               todo en una respuesta (cache de n8n 30 s).
- GET  /admin-v2/api/oficina/personajes           lo guardado en el editor (enlaces firmados).
- PUT  /admin-v2/api/oficina/personajes           guardar un personaje {clave, company_id?, ...}.
- POST /admin-v2/api/oficina/personajes/archivo   ?clave=&company_id=&tipo=cara|completa|modelo, cuerpo = el archivo.
- DELETE /admin-v2/api/oficina/personajes/archivo  quitar ese archivo.
- GET  /admin-v2/api/oficina/archivos/{ambito}/{id}.{ext}?e=&s=   archivo privado del bucket (firma 15 min).
- PUT  /admin-v2/api/oficina/pisos/orden          {company_ids: [...]} (de arriba hacia abajo).
- PUT  /admin-v2/api/oficina/pisos/{company_id}   {plantilla?, privacidad?}.
Las imagenes y modelos van al bucket clonexa-media (privados), nunca a Postgres.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import brand_media
from app.services import oficina as of
from app.services import oficina_data as od
from app.web import admin_v2_routes as v2
from app.web.admin_v2plus_companies import GUARD, _audit, _json

router = APIRouter()
WEB = Path(__file__).resolve().parent
PAGE = WEB / "oficina" / "oficina.html"
API = "/admin-v2/api/oficina"
ACTOR = "admin_v2"

ASSETS = {
    "app.js": ("oficina/oficina_app.js", "application/javascript"),
    "app.css": ("oficina/oficina.css", "text/css"),
    "logo-simbolo.png": ("oficina/logo-simbolo.png", "image/png"),
    "logo-nombre.png": ("oficina/logo-nombre.png", "image/png"),
}
THREE_DIR = "vendor/three-0.160.0"
THREE = {
    "build/three.module.js",
    "examples/jsm/environments/RoomEnvironment.js",
    "examples/jsm/geometries/RoundedBoxGeometry.js",
    "examples/jsm/loaders/GLTFLoader.js",
    "examples/jsm/utils/BufferGeometryUtils.js",
}


def importmap_hash(html: str) -> str:
    """sha256 del importmap en linea (el unico script en linea de la pagina) para la CSP."""
    start = html.index('<script type="importmap">') + len('<script type="importmap">')
    body = html[start:html.index("</script>", start)]
    return "sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")


def page_csp(html: str) -> str:
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' '{importmap_hash(html)}'",
        "style-src 'self' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        # blob: para las texturas que trae un modelo .glb (GLTFLoader las abre como blob:)
        "img-src 'self' data: blob:",
        "connect-src 'self' blob:",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ])


async def _session(request: Request, db: AsyncSession) -> bool:
    return await v2._active_session(request, db)


async def _require(request: Request, db: AsyncSession) -> None:
    if not await _session(request, db):
        raise HTTPException(status_code=401, detail="Sesión de Admin V2 requerida.", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ pagina y archivos
@router.get("/admin-v2plus/oficina", include_in_schema=False)
async def oficina_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not await _session(request, db):
        return v2._no_store(RedirectResponse(url="/admin-v2plus/login", status_code=303))
    html = PAGE.read_text(encoding="utf-8")
    return v2._no_store(Response(html, media_type="text/html; charset=utf-8", headers={"Content-Security-Policy": page_csp(html)}))


@router.get("/admin-v2plus/oficina/vendor/three/{path:path}", include_in_schema=False)
async def oficina_three(path: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _require(request, db)
    if path not in THREE:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(WEB / THREE_DIR / path, media_type="application/javascript", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/admin-v2plus/oficina/{name}", include_in_schema=False)
async def oficina_asset(name: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _require(request, db)
    item = ASSETS.get(name)
    if not item:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return v2._no_store(FileResponse(WEB / item[0], media_type=item[1]))


# ------------------------------------------------------------------ estado
_DB_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
DB_TTL = 10.0


def reset_cache() -> None:
    _DB_CACHE.update(at=0.0, data=None)
    of.N8N.reset()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get(f"{API}/estado", include_in_schema=False, dependencies=GUARD)
async def estado(db: AsyncSession = Depends(get_db)):
    now = _now()
    n8n = await of.N8N.get()
    if _DB_CACHE["data"] is not None and time.monotonic() - _DB_CACHE["at"] < DB_TTL:
        base = _DB_CACHE["data"]
    else:
        r = od.Reader(db)
        floors = await od.floors(r, now)
        block = await od.clonexa_block(r, now)
        shifts = await od.shift_feed(r, floors, now)
        base = {"floors": floors, "block": block, "shift_feed": shifts}
        _DB_CACHE.update(at=time.monotonic(), data=base)
    block, floors = base["block"], base["floors"]
    agents = of.build_agents(n8n, block["lines"], now)
    cal = n8n.get("calendar") if n8n.get("ok") else None
    approvals = {
        "pieces": (cal or {}).get("ready_items") or [] if cal and cal.get("ok") else None,
        "pieces_count": int((cal or {}).get("ready") or 0) if cal and cal.get("ok") else None,
        "batch": block["approvals"]["batch"], "batch_known": block["approvals"]["batch_known"],
        "replied": block["approvals"]["replied"], "replied_known": block["approvals"]["replied_known"],
    }
    director = next(a for a in agents if a["id"] == "director")
    director["today"] = [
        f"{approvals['pieces_count']} piezas por aprobar" if approvals["pieces_count"] is not None else "Piezas por aprobar: sin datos de la hoja",
        ("Lote de correos de hoy por aprobar" if approvals["batch"] else "Sin lote de correos pendiente") if approvals["batch_known"] else "Lote de correos: sin datos",
        f"{len(approvals['replied'])} leads respondieron" if approvals["replied_known"] else "Leads: sin datos",
    ]
    ideas = n8n.get("ideas") if n8n.get("ok") else None
    feed = sorted(of.n8n_feed(n8n, now) + block["feed"] + base["shift_feed"], key=lambda e: e.get("at") or "", reverse=True)[:12]
    return _json({
        "ok": True, "generated_at": now.isoformat(),
        "n8n": {"ok": bool(n8n.get("ok")), "error": None if n8n.get("ok") else n8n.get("error"), "fetched_at": n8n.get("fetched_at")},
        "agents": agents, "approvals": approvals,
        "calendar": {k: cal.get(k) for k in ("ready", "approved", "next", "week_pieces")} if cal and cal.get("ok") else None,
        "ideas": {"pending": int(ideas.get("pending") or 0), "items": (ideas.get("items") or [])[:5]} if ideas and ideas.get("ok") else None,
        "floors": floors, "feed": feed,
        "cast": {"agents": len(of.AGENTS), "reps": len(floors), "templates": len(of.UNIFORMS), "on_shift": od.counts_now(floors),
                 "by_floor": [{"name": f["name"], "on_shift": (f.get("staff") or {}).get("total")} for f in floors]},
        "templates": [{"key": k, "label": of.TEMPLATE_LABEL[k]} for k in of.TEMPLATES],
        "uniforms": [{"key": k, "label": of.UNIFORM_LABEL[k]} for k in of.UNIFORMS],
    })


# ------------------------------------------------------------------ editor
def _scope(company_id: Optional[str]) -> Optional[str]:
    if company_id in (None, "", "clonexa", "null"):
        return None
    try:
        return str(uuid.UUID(str(company_id)))
    except ValueError:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.") from None


async def _check_scope(db: AsyncSession, clave: str, company_id: Optional[str]) -> None:
    if clave.startswith("agente:") and company_id is not None:
        raise HTTPException(status_code=422, detail="Los agentes de Clonexa no son de una empresa.")
    if (clave == "rep" or clave.startswith("persona:")) and company_id is None:
        raise HTTPException(status_code=422, detail="Este personaje necesita su empresa.")
    if company_id is not None and company_id not in await od.registered_ids(db):
        raise HTTPException(status_code=404, detail="Empresa no encontrada (solo empresas registradas).")


def _rejected(error: of.Rejected) -> HTTPException:
    return HTTPException(status_code=error.status, detail=error.message)


@router.get(f"{API}/personajes", include_in_schema=False, dependencies=GUARD)
async def personajes(db: AsyncSession = Depends(get_db)):
    return _json({"ok": True, "items": await od.characters(od.Reader(db)),
                  "limits": {"image_mb": of.IMAGE_MAX // (1024 * 1024), "model_mb": of.MODEL_MAX // (1024 * 1024)},
                  "storage": brand_media.configured()})


@router.put(f"{API}/personajes", include_in_schema=False, dependencies=GUARD)
async def guardar_personaje(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Datos no válidos.") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Datos no válidos.")
    try:
        clave = of.check_key(body.get("clave"))
        fields = of.clean_character(body)
    except of.Rejected as error:
        raise _rejected(error) from None
    cid = _scope(body.get("company_id"))
    await _check_scope(db, clave, cid)
    if not fields:
        raise HTTPException(status_code=422, detail="Nada que guardar.")
    row = await od.save_character(db, cid, clave, fields, ACTOR)
    await _audit(request, oficina_personaje=clave, empresa=cid or "clonexa", campos=",".join(sorted(fields)))
    return _json({"ok": True, "item": od.character_out(row)})


COLUMN = {"cara": "cara_key", "completa": "completa_key", "modelo": "modelo_key"}


def _put(key: str, data: bytes, content_type: str) -> None:
    store = brand_media.backend()
    if isinstance(store, brand_media.S3Backend):
        store.put(key, data, content_type=content_type, private=True)
    else:
        store.put(key, data)


def _delete(keys: list[str]) -> None:
    keys = [k for k in keys if k]
    if keys:
        brand_media.backend().delete(keys)


async def _read_limited(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail="El archivo es muy grande.")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail="El archivo es muy grande.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(f"{API}/personajes/archivo", include_in_schema=False, dependencies=GUARD)
async def subir_archivo(request: Request, clave: str = Query(...), tipo: str = Query(...), company_id: str = Query(""),
                        db: AsyncSession = Depends(get_db)):
    try:
        clave = of.check_key(clave)
    except of.Rejected as error:
        raise _rejected(error) from None
    if tipo not in COLUMN:
        raise HTTPException(status_code=404, detail="Tipo de archivo no válido.")
    cid = _scope(company_id)
    await _check_scope(db, clave, cid)
    if not brand_media.configured():
        raise HTTPException(status_code=503, detail="El almacenamiento de archivos no está configurado.")
    limit = of.MODEL_MAX if tipo == "modelo" else of.IMAGE_MAX
    raw = await _read_limited(request, limit)
    try:
        content_type, ext = of.check_file(tipo, raw)
    except of.Rejected as error:
        raise _rejected(error) from None
    key = f"oficina/{cid or 'clonexa'}/{uuid.uuid4().hex}.{ext}"
    old = await od.get_character(db, cid, clave)
    try:
        await asyncio.to_thread(_put, key, raw, content_type)
    except brand_media.StorageUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    fields: dict[str, Any] = {COLUMN[tipo]: key, "archivos_bytes": len(raw)}
    if tipo == "completa":
        fields["estilo"] = "imagen"
    if tipo == "modelo":
        fields["estilo"] = "modelo"
    row = await od.save_character(db, cid, clave, fields, ACTOR)
    if old and old.get(COLUMN[tipo]) and old[COLUMN[tipo]] != key:
        try:
            await asyncio.to_thread(_delete, [old[COLUMN[tipo]]])
        except Exception:
            pass
    await _audit(request, oficina_personaje=clave, empresa=cid or "clonexa", archivo=tipo, kb=round(len(raw) / 1024))
    return _json({"ok": True, "item": od.character_out(row)})


@router.delete(f"{API}/personajes/archivo", include_in_schema=False, dependencies=GUARD)
async def quitar_archivo(request: Request, clave: str = Query(...), tipo: str = Query(...), company_id: str = Query(""),
                         db: AsyncSession = Depends(get_db)):
    try:
        clave = of.check_key(clave)
    except of.Rejected as error:
        raise _rejected(error) from None
    if tipo not in COLUMN:
        raise HTTPException(status_code=404, detail="Tipo de archivo no válido.")
    cid = _scope(company_id)
    old = await od.get_character(db, cid, clave)
    if not old or not old.get(COLUMN[tipo]):
        raise HTTPException(status_code=404, detail="No hay archivo que quitar.")
    fields: dict[str, Any] = {COLUMN[tipo]: ""}
    if (tipo == "completa" and old.get("estilo") == "imagen") or (tipo == "modelo" and old.get("estilo") == "modelo"):
        fields["estilo"] = "anime"
    row = await od.save_character(db, cid, clave, fields, ACTOR)
    try:
        await asyncio.to_thread(_delete, [old[COLUMN[tipo]]])
    except Exception:
        pass
    await _audit(request, oficina_personaje=clave, empresa=cid or "clonexa", archivo_quitado=tipo)
    return _json({"ok": True, "item": od.character_out(row)})


MEDIA = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "glb": "model/gltf-binary"}


@router.get(API + "/archivos/{scope}/{name}", include_in_schema=False, dependencies=GUARD)
async def archivo(scope: str, name: str, e: str = Query(""), s: str = Query("")):
    path = f"{scope}/{name}"
    if not of.FILE_NAME_RE.match(path) or not of.signature_ok(path, e, s):
        raise HTTPException(status_code=404, detail="Archivo no encontrado o enlace vencido.")
    try:
        data = await asyncio.to_thread(brand_media.backend().get, f"oficina/{path}")
    except brand_media.StorageUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    except Exception:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.") from None
    return Response(data, media_type=MEDIA[name.rsplit(".", 1)[1]], headers={"Cache-Control": "private, max-age=600",
                                                                           "Content-Security-Policy": "default-src 'none'; sandbox"})


# ------------------------------------------------------------------ pisos
@router.put(f"{API}/pisos/orden", include_in_schema=False, dependencies=GUARD)
async def orden(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Datos no válidos.") from None
    ids = body.get("company_ids") if isinstance(body, dict) else None
    if not isinstance(ids, list) or not ids or len(ids) > 200:
        raise HTTPException(status_code=422, detail="Envía la lista de pisos en orden.")
    clean = [_scope(x) for x in ids]
    known = await od.registered_ids(db)
    if len(set(clean)) != len(clean) or any(c is None or c not in known for c in clean):
        raise HTTPException(status_code=422, detail="La lista tiene pisos que no son empresas registradas.")
    await od.save_order(db, clean, ACTOR)
    reset_db_cache()
    await _audit(request, oficina_orden=len(clean))
    return _json({"ok": True})


@router.put(API + "/pisos/{company_id}", include_in_schema=False, dependencies=GUARD)
async def piso(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    cid = _scope(company_id)
    if cid is None or cid not in await od.registered_ids(db):
        raise HTTPException(status_code=404, detail="Empresa no encontrada (solo empresas registradas).")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Datos no válidos.") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Datos no válidos.")
    kwargs: dict[str, Any] = {}
    if "plantilla" in body:
        if body["plantilla"] not in (*of.TEMPLATES, None):
            raise HTTPException(status_code=422, detail="Plantilla no válida.")
        kwargs["plantilla"] = body["plantilla"]
    if "privacidad" in body:
        if body["privacidad"] not in of.PRIVACY:
            raise HTTPException(status_code=422, detail="Privacidad no válida.")
        kwargs["privacidad"] = body["privacidad"]
    if not kwargs:
        raise HTTPException(status_code=422, detail="Nada que guardar.")
    await od.save_floor(db, cid, actor=ACTOR, **kwargs)
    reset_db_cache()
    await _audit(request, oficina_piso=cid, **{k: str(v) for k, v in kwargs.items()})
    return _json({"ok": True})


def reset_db_cache() -> None:
    _DB_CACHE.update(at=0.0, data=None)
